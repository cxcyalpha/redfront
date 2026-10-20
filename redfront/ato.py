"""План полётов на сутки (ATO) обеих сторон: каждый вылет - со временем взлёта, выхода на объект и посадки.

Задачи и пакеты - те же, что у плана дня (planner.plan_side): цели, исполнители, группы обеспечения. ATO добавляет
время. Сутки лётной работы - settings.flying_hours (по умолчанию FLYING_HOURS). Задачи стороны ставятся по порядку
приоритета, равномерно по лётному дню (со случайным сдвигом, если случайность кампании включена); вылет
ставится, только если у части хватает самолётов на всё время вылета плюс подготовку к повторному (turnaround_min
раздела sim доктрины) - иначе позже, шагом SLOT_MIN, до конца лётного дня; не влезает - не ставится.
Дежурства (method orbit: ДРЛО, заправщик) - сменами shift_h часов на весь лётный день, у каждой смены свой вылет;
не хватает самолётов - в дежурстве разрыв. Воздушные перевозки (method airlift) - sorties_per_day рейсов на направление;
груз довозят в конце суток (logistics.supply), минус борта, сбитые в миссии (ato['lost']).

Игрок выбирает вылет своей стороны (planner.plan -> state['tasks'], по времени); миссия - окно суток вокруг него
(build): вылеты обеих сторон, которые в это окно в воздухе, попадают в миссию - кто уже в воздухе, стоит на своём
маршруте, кто позже - взлетает по расписанию. Все числа - ОЦЕНКИ.
"""
from __future__ import annotations

from . import logistics, model, planner

FLYING_HOURS = (6, 20)      # ОЦЕНКА: лётный день (часы, местное время миссии); ночью летают только типы с night (aircraft.json)
TURNAROUND_MIN = 90         # ОЦЕНКА: подготовка к повторному вылету, если в доктрине нет sim.turnaround_min
SLOT_MIN = 15               # шаг сдвига вылета, если самолётов нет
ATO_MAX_TASKS = 40          # ОЦЕНКА: задач (кроме дежурств) в ATO стороны на сутки
ATO_PER_KIND = 8            # ОЦЕНКА: задач одного вида в ATO стороны на сутки
DWELL_S = 120               # ОЦЕНКА: время над объектом у ударных групп
MISSION_LEN_S = 75 * 60     # ОЦЕНКА: окно миссии игрока; вылеты в воздухе в это окно - в миссии


ATO_NIGHT_TASKS = 3         # ОЦЕНКА: задач (кроме дежурств) стороны ночью - из тех, где все исполнители летают ночью
NIGHT_KINDS = {"cas_helo", "strike_bridge", "strike_depot", "strike_factory", "strike_airfield", "strike_supply_route", "strike_fofa",
               "strike_sam_site", "air_assault", "air_evac"}   # ночью - глубокие удары и десант; поддержка войск, спасение - днём
DAY_S = 86400


def night_capable(state: dict, task: dict) -> bool:
    """Все группы задачи - типы, летающие ночью (aircraft.json night)."""
    return all(model.aircraft_info(state["units"][g["performer"]].get("type")).get("night") for g in task["package"])


def is_night(state: dict, t_s: float) -> bool:
    w0, w1 = flying_window(state)
    return not (w0 <= t_s % DAY_S < w1)


def flying_window(state: dict) -> tuple[int, int]:
    h0, h1 = (state.get("settings") or {}).get("flying_hours") or FLYING_HOURS
    return int(h0 * 3600), int(h1 * 3600)


def hhmm(t_s: float) -> str:
    t = int(t_s) % 86400
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}"


def _path_km(base: dict, route: list[dict]) -> float:
    pts = [base] + list(route)
    return sum(model.dist_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def rel_times(state: dict, tdef: dict, task: dict) -> dict[str, dict]:
    """Время групп пакета относительно выхода ударной группы на цель (0): взлёт, выход на свой объект, посадка, с.
    Группа обеспечения выходит на объект за lead_min до удара (как build.timeline). Скорость - задачи доктрины."""
    out = {}
    for g in task["package"]:
        spd = model.group_speed_kmh(state, g, tdef) / 3.6      # скорость задачи доктрины
        base = state["airbases"][g["base"]]
        fly = _path_km(base, planner.route_points(g)) * 1000 / spd
        back = model.dist_km(g["route"][-1], base) * 1000 / spd
        obj = -g.get("lead_min", 0) * 60
        kind = g["objective"]["kind"]
        if kind == "cap_zone":
            dwell = (g.get("cap_min") or 20) * 60
        elif kind == "sweep_zone":               # расчистка воздуха - до выхода ударной группы на цель
            dwell = -obj
        elif kind == "escort_lz":                # прикрытие вертолётов: пока транспортные на площадке
            dwell = -obj + (g.get("land_s") or 120) + 120
        elif kind == "feint":
            dwell = (g.get("orbit_min") or 6) * 60
        elif kind in ("cover_zone", "sam"):
            dwell = -obj + (g.get("hold_after_min") or 5) * 60
        else:
            dwell = DWELL_S
        out[g["group"]] = {"takeoff_s": obj - fly, "objective_s": obj, "land_s": obj + dwell + back}
    return out


HELO_HOURS_MONTH = 65   # ОЦЕНКА по аналогии (FM 101-20, табл. 1-5: AH-1 65 ч/мес в боевых условиях) - вертолётам без своего значения


class _Pool:
    """Занятость самолётов частей по времени: интервалы (с, по, сколько)."""
    def __init__(self, state: dict):
        self.state = state
        self.busy: dict[str, list[tuple[float, float, int]]] = {}

    def free(self, uid: str, t0: float, t1: float) -> int:
        cap = logistics.available(self.state, self.state["units"][uid])
        used = sum(n for a, b, n in self.busy.get(uid, []) if a < t1 and t0 < b)   # с запасом: все пересекающиеся
        return cap - used

    def hours_left(self, uid: str) -> float | None:
        """Налёт части на сутки, ч: вертолёты - число ЛА x combat_hours_month / 30 (FM 101-20, табл. 1-5); None - без предела."""
        u = self.state["units"][uid]
        if model.category(u) != "heli":
            return None
        per = model.aircraft_info(u.get("type", "")).get("combat_hours_month") or HELO_HOURS_MONTH
        done = sum(n * (b - a) / 3600 for a, b, n in self.busy.get(uid, []))
        return logistics.available(self.state, u) * per / 30 - done

    def fits(self, need: dict[str, tuple[float, float, int]]) -> bool:
        for uid, (t0, t1, n) in need.items():
            if self.free(uid, t0, t1) < n:
                return False
            h = self.hours_left(uid)
            if h is not None and h < n * (t1 - t0) / 3600:
                return False                     # налёт части на сутки исчерпан
        return True

    def book(self, need: dict[str, tuple[float, float, int]]) -> None:
        for uid, iv in need.items():
            self.busy.setdefault(uid, []).append(iv)


def _need(task: dict, times: dict, tot: float, turn_s: float) -> dict[str, tuple[float, float, int]]:
    need: dict[str, list] = {}
    for g in task["package"]:
        t = times[g["group"]]
        t0, t1 = tot + t["takeoff_s"], tot + t["land_s"] + turn_s
        if g["performer"] in need:
            a, b, n = need[g["performer"]]
            need[g["performer"]] = [min(a, t0), max(b, t1), n + g["size"]]
        else:
            need[g["performer"]] = [t0, t1, g["size"]]
    return {k: tuple(v) for k, v in need.items()}


def build(state: dict) -> dict:
    """ATO на текущие сутки обеих сторон -> state['ato'] = {'day', 'entries': [...], 'done': [...]}."""
    w0, w1 = flying_window(state)
    pool = _Pool(state)
    entries = []
    for side in model.SIDES:
        doc = model.doctrine(state, side)
        turn_s = doc["sim"].get("turnaround_min", TURNAROUND_MIN) * 60
        tasks, _why = planner.plan_side(state, side, max_tasks=ATO_MAX_TASKS, per_kind=ATO_PER_KIND)
        rnd = model.rng(state, f"ato-{side}")
        # дежурства - первыми: непрерывное покрытие (ДРЛО) важнее очередного удара
        for t in (t for t in tasks if t.get("ai_only") and doc["tasks"][t["kind"]].get("method") == "orbit"):
            tdef = doc["tasks"][t["kind"]]
            g = t["package"][0]
            transit = model.dist_km(state["airbases"][g["base"]], g["route"][0]) * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
            shift = tdef.get("shift_h", 4) * 3600
            d0, d1 = (transit, DAY_S - transit) if night_capable(state, t) else (w0, w1)   # ночью - если тип умеет
            s = d0
            while s < d1:
                e = min(d1, s + shift)
                times = {g["group"]: {"takeoff_s": s - transit, "objective_s": s, "land_s": e + transit, "station_end_s": e}}
                need = {g["performer"]: (s - transit, e + transit + turn_s, g["size"])}
                if g["size"] > 0 and pool.fits(need):
                    pool.book(need)
                    entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                    "title": t["title"], "task": t, "tot_s": s, "times": times, "ai_only": True})
                s = e
        # дежурные пары ПВО: сменами shift_h на аэродроме (самолёты на земле в готовности - заняты всю смену)
        for t in (t for t in tasks if t.get("ai_only") and doc["tasks"][t["kind"]].get("method") == "alert"):
            tdef = doc["tasks"][t["kind"]]
            g = t["package"][0]
            shift = tdef.get("shift_h", 4) * 3600
            d0, d1 = (0, DAY_S) if night_capable(state, t) else (w0, w1)   # круглосуточно - если тип летает ночью
            s = d0
            while s < d1:
                e = min(d1, s + shift)
                need = {g["performer"]: (s, e + turn_s, g["size"])}
                if pool.fits(need):
                    pool.book(need)
                    times = {g["group"]: {"takeoff_s": s, "objective_s": s, "land_s": e, "station_end_s": e}}
                    entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                    "title": t["title"], "task": t, "tot_s": s, "times": times, "ai_only": True})
                s = e
        # воздушные перевозки: sorties_per_day рейсов на направление, равномерно по лётному дню; рейс - до посадки
        # на аэродроме назначения, самолёты заняты ещё на обратный перелёт и подготовку
        for t in (t for t in tasks if t.get("ai_only") and doc["tasks"][t["kind"]].get("method") == "airlift"):
            tdef = doc["tasks"][t["kind"]]
            g = t["package"][0]
            if g["size"] <= 0:
                continue
            fly = t["distance_km"] * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
            n = tdef.get("sorties_per_day", 2)
            for i in range(n):
                tot = max(w0 + fly, w0 + (w1 - w0) * (i + 0.5) / n + (rnd.uniform(-0.3, 0.3) * (w1 - w0) / n if rnd else 0))
                while tot <= w1:
                    need = {g["performer"]: (tot - fly, tot + fly + turn_s, g["size"])}
                    if pool.fits(need):
                        pool.book(need)
                        times = {g["group"]: {"takeoff_s": tot - fly, "objective_s": tot, "land_s": tot}}
                        entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                        "title": t["title"], "task": t, "tot_s": tot, "times": times, "ai_only": True})
                        break
                    tot += SLOT_MIN * 60
        # разведка: sorties_per_day вылетов на маршрут - на рассвете и к вечеру (данные - к планированию следующих
        # ударов); вылет - по всему маршруту, самолёты заняты до посадки и подготовки
        for t in (t for t in tasks if t.get("ai_only") and doc["tasks"][t["kind"]].get("method") == "recon"):
            tdef = doc["tasks"][t["kind"]]
            g = t["package"][0]
            fly = t["distance_km"] * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
            n = int(tdef.get("sorties_per_day", 2))
            for i in range(n):
                tot = w0 + fly / 2 + max(0.0, w1 - w0 - fly) * (i / (n - 1) if n > 1 else 0.5)
                while tot + fly / 2 <= w1 + 3600:
                    need = {g["performer"]: (tot - fly / 2, tot + fly / 2 + turn_s, g["size"])}
                    if pool.fits(need):
                        pool.book(need)
                        times = {g["group"]: {"takeoff_s": tot - fly / 2, "objective_s": tot, "land_s": tot + fly / 2}}
                        entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                        "title": t["title"], "task": t, "tot_s": tot, "times": times, "ai_only": True})
                        break
                    tot += SLOT_MIN * 60
        reg = [t for t in tasks if not t.get("ai_only")]
        # ночь: до ATO_NIGHT_TASKS задач, где все группы летают ночью, - из младших по приоритету (глубокие удары -
        # ночью, поддержка войск - днём), вечером после лётного дня (утро суток - только дежурства)
        night = [t for t in reversed(reg) if t["kind"] in NIGHT_KINDS and night_capable(state, t)][:ATO_NIGHT_TASKS]
        for i, t in enumerate(night):
            tdef = doc["tasks"][t["kind"]]
            rel = rel_times(state, tdef, t)
            first = min(x["takeoff_s"] for x in rel.values())
            last = max(x["land_s"] for x in rel.values())
            lo, hi = w1 - first, DAY_S - last
            if hi <= lo:
                continue
            tot = lo + (hi - lo) * (i + 0.5) / len(night)
            while tot <= hi:
                need = _need(t, rel, tot, turn_s)
                if pool.fits(need):
                    pool.book(need)
                    times = {k: {kk: tot + vv for kk, vv in v.items()} for k, v in rel.items()}
                    entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                    "title": t["title"], "task": t, "tot_s": tot, "times": times, "ai_only": False,
                                    "night": True})
                    break
                tot += SLOT_MIN * 60
        reg = [t for t in reg if t not in night]
        span = w1 - w0
        for i, t in enumerate(reg):
            tdef = doc["tasks"][t["kind"]]
            rel = rel_times(state, tdef, t)
            first = min(x["takeoff_s"] for x in rel.values())
            last = max(x["land_s"] for x in rel.values())
            want = w0 + span * (i + 0.5) / max(1, len(reg))
            if rnd:
                want += rnd.uniform(-0.4, 0.4) * span / max(1, len(reg))
            tot = max(want, w0 - first)                  # взлёт - не раньше начала лётного дня
            while tot + last <= w1 + 3600:               # посадка - не позже часа после конца лётного дня
                need = _need(t, rel, tot, turn_s)
                if pool.fits(need):
                    pool.book(need)
                    times = {k: {kk: tot + vv for kk, vv in v.items()} for k, v in rel.items()}
                    entries.append({"id": f"{side}-{t['kind']}-{len(entries)}", "side": side, "kind": t["kind"],
                                    "title": t["title"], "task": t, "tot_s": tot, "times": times, "ai_only": False})
                    break
                tot += SLOT_MIN * 60
    entries.sort(key=lambda e: e["tot_s"])
    state["ato"] = {"day": state["day"], "entries": entries, "done": []}
    return state["ato"]


def ensure(state: dict) -> dict:
    """ATO текущих суток: построить, если его нет или он от прошлых суток."""
    a = state.get("ato")
    if not a or a.get("day") != state["day"]:
        a = build(state)
    return a


def in_window(e: dict, t0: float, t1: float, group: str = "strike") -> bool:
    t = e["times"].get(group) or next(iter(e["times"].values()))
    return t["takeoff_s"] < t1 and t["land_s"] > t0


def rows(state: dict, sides: tuple[str, ...] = model.SIDES) -> list[dict]:
    """План полётов для показа (окно, консоль): вылеты сторон sides по времени. План противника - отладка
    ("читы"): в игре его видеть не положено."""
    a = state.get("ato")
    if not a:
        return []
    units, clock = state["units"], state.get("clock_s") or 0
    out = []
    for e in a["entries"]:
        if e["side"] not in sides:
            continue
        g = e["task"]["package"][0]
        perf = units.get(g["performer"], {})
        t = e["times"][g["group"]]
        tgt = units.get(e["task"].get("target"), {})
        status = ("слетан игроком" if e["id"] in a["done"] else "прошёл" if t["land_s"] <= clock
                  else "в воздухе" if t["takeoff_s"] <= clock else "по плану")
        out.append({"id": e["id"], "side": e["side"], "kind": e["kind"], "title": e["title"], "night": is_night(state, e["tot_s"]),
                    "target": tgt.get("name", ""), "duty": e["ai_only"],
                    "takeoff": hhmm(t["takeoff_s"]), "tot": hhmm(e["tot_s"]), "land": hhmm(t["land_s"]),
                    "end": hhmm(t["station_end_s"]) if "station_end_s" in t else None,
                    "groups": [f"{x['title']}: {x['size']} x {units.get(x['performer'], {}).get('type', '?')} "
                               f"({units.get(x['performer'], {}).get('name', x['performer'])}, "
                               f"{state['airbases'].get(x['base'], {}).get('name', x['base'])})"
                               for x in e["task"]["package"]],
                    "threats": [units[x]["name"] for x in e["task"].get("threats", []) if x in units],
                    "status": status, "perf_type": perf.get("type", "")})
    return out

"""Суточный цикл наземной модели: бой частей в соприкосновении и марш.

Абстракция "карты и стрелки" - все коэффициенты в разделе sim пакета доктрины стороны, все - ОЦЕНКИ:
  1. Бой. Части противоположных сторон в соприкосновении (state 'battle', engaged - с кем) несут потери за сутки:
     доля = battle_loss_k * (сила противника / своя сила), не больше loss_cap; у обороняющейся (defend_factor) меньше.
     Сила - исправная техника с весами ролей (role_weight). Потери ложатся на типы пропорционально их числу.
     Часть ниже combat_ineffective_below выходит из боя (halted) и больше не держит противника.
  2. Марш. Части на марше и те, чей противник выбыл, идут по маршруту шагами step_km на daily_advance_km * боеспособность,
     пока не окажутся ближе contact_km к части противника - тогда бой. Дошла до конца маршрута - оборона (занят район).
"""
from __future__ import annotations

from . import farp, intel, logistics, model, ops, samroam

ACTIVE = ("march", "battle", "defend", "refit")


def _sim(state: dict, side: str) -> dict:
    return model.doctrine(state, side)["sim"]


def _maneuver(state: dict) -> list[dict]:
    return [u for u in state["units"].values() if model.category(u) == "ground" and "route" in u
            and u["state"] not in ("destroyed", "pending")]


def power(state: dict, unit: dict) -> float:
    """Боевая сила: исправная техника с весами ролей (ОЦЕНКА, sim.role_weight стороны части); без снабжения -
    x supply_power_factor, при части нормы (supply_frac, logistics.supply) - пропорционально между ним и 1."""
    sim = _sim(state, unit["side"])
    w = sim.get("role_weight", {})
    roles = {c["type"]: c["role"] for c in unit["composition"]}
    p = sum(n * w.get(roles[t], 0.0) for t, n in model.alive_by_type(unit).items())
    frac = unit.get("supply_frac", 1.0 if unit.get("supply", 1.0) >= 1.0 else 0.0)
    spf = sim.get("supply_power_factor", 1.0)
    return p * (spf + (1.0 - spf) * frac) * artillery_k(state, unit)


def artillery_k(state: dict, unit: dict) -> float:
    """Огонь артиллерии части (батарея поддержки, materialize.ART_GUNS; потерянные орудия - art_lost): сила x (1 +
    artillery_factor x доля исправных орудий) - ОЦЕНКА, sim.artillery_factor доктрины."""
    from .materialize import ART_GUNS
    k = _sim(state, unit["side"]).get("artillery_factor", 0.0)
    if not k or unit.get("role") == "air_assault":
        return 1.0
    return 1.0 + k * max(0, ART_GUNS - int(unit.get("art_lost", 0))) / ART_GUNS


def _take_losses(unit: dict, frac: float) -> float:
    """Списать долю frac исправной техники, по типам пропорционально. Возвращает число машин."""
    lost = 0.0
    for c in unit["composition"]:
        alive = max(0.0, c["count"] - unit["lost"].get(c["type"], 0.0))
        d = alive * frac
        unit["lost"][c["type"]] = unit["lost"].get(c["type"], 0.0) + d
        lost += d
    return lost


def _attached(state: dict, unit: dict) -> list[dict]:
    return [a for a in state["units"].values() if a.get("attached_to") == unit["id"] and a["state"] != "destroyed"]


def battles(state: dict, frac_day: float = 1.0, tag: str = "") -> list[str]:
    """Бой за frac_day суток (шаг наземной модели): потери - суточная доля x frac_day (и потолок loss_cap x frac_day).
    Строки о потерях - только за целые сутки (frac_day = 1); по часам сводку пишет advance."""
    lines = []
    units = state["units"]
    engaged = [u for u in _maneuver(state) if u["state"] == "battle"]
    pw = {u["id"]: power(state, u) for u in _maneuver(state)}    # сила на начало суток: потери сторон считаются одновременно
    for u in engaged:
        foes = [units[f] for f in u.get("engaged", []) if f in units]
        enemy = sum(pw.get(f["id"], 0.0) for f in foes if f["state"] in ACTIVE)
        if enemy <= 0 or pw[u["id"]] <= 0:
            continue
        sim = _sim(state, u["side"])
        frac = min(sim["loss_cap"], sim["battle_loss_k"] * enemy / pw[u["id"]])
        r = model.rng(state, f"battle-{u['id']}{tag}")
        if r:                                    # исход боя - с разбросом (ОЦЕНКА, sim.battle_variance)
            frac = min(sim["loss_cap"], frac * r.uniform(1 - sim["battle_variance"], 1 + sim["battle_variance"]))
        if u.get("defending"):
            frac *= sim["defend_factor"]
            if u.get("dig_h", 0) >= sim.get("prepared_h", 1e9):   # подготовленная оборона: окопы, заграждения, огневая система
                frac *= sim.get("prepared_factor", 1.0)
        frac *= frac_day
        s0 = model.strength(u)
        n = _take_losses(u, frac)
        for a in _attached(state, u):                            # приданная ПВО несёт те же потери
            _take_losses(a, frac)
        if frac_day >= 1.0:
            lines.append(f"{u['name']}: бой с {', '.join(f['name'] for f in foes)} - потеряно ~{n:.0f} машин, "
                         f"боеспособность {s0:.0%} -> {model.strength(u):.0%}.")
    for u in engaged:
        sim = _sim(state, u["side"])
        if model.strength(u) < sim["combat_ineffective_below"]:
            u["state"] = "halted"
            lines.append(f"{u['name']}: потерял боеспособность, вышел из боя.")
    for u in engaged:                                             # бой окончен, если против части никого не осталось
        if u["state"] != "battle":
            continue
        alive = [f for f in u.get("engaged", []) if units[f]["state"] == "battle"]
        if not alive:
            u["state"] = "defend" if u.get("defending") else "march"
            u["engaged"] = []
            lines.append(f"{u['name']}: противник выбыл - " + ("удержал район." if u.get("defending") else "продолжает марш."))
    return lines


def _length(state: dict, u: dict) -> float:
    return model.route_km(state, u)


def _contacts(state: dict, units: list[dict]) -> list[tuple[dict, dict]]:
    out = []
    act = [u for u in units if u["state"] in ACTIVE and u.get("order") != "withdraw"]   # отходящие разрывают соприкосновение
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            if a["side"] == b["side"]:
                continue
            ck = max(_sim(state, a["side"])["contact_km"], _sim(state, b["side"])["contact_km"])
            if model.dist_km(model.unit_pos(state, a), model.unit_pos(state, b)) <= ck:
                out.append((a, b))
    return out


def _engage(a: dict, b: dict) -> None:
    for x, y in ((a, b), (b, a)):
        if x["state"] in ("defend", "refit"):
            x["defending"] = True
        elif x["state"] == "march":
            x["defending"] = False
        x["state"] = "battle"
        x.setdefault("engaged", [])
        if y["id"] not in x["engaged"]:
            x["engaged"].append(y["id"])


def current_link(state: dict, u: dict) -> tuple[str, str] | None:
    """Связь маршрута, на которой сейчас часть (по пройденным км)."""
    r = u.get("route") or []
    km = 0.0
    for a, b in zip(r, r[1:]):
        km += model.route_km(state, {"route": [a, b]})
        if u["progress_km"] < km - 1e-6:
            return a, b
    return (r[-2], r[-1]) if len(r) > 1 else None


def movement(state: dict, frac_day: float = 1.0) -> list[str]:
    """Марш за frac_day суток: суточный отрыв x frac_day. Строки о продвижении - только за целые сутки."""
    lines = []
    units = _maneuver(state)
    budget, start = {}, {}
    foes = {s: [model.unit_pos(state, x) for x in units if x["side"] != s and x["state"] in ACTIVE] for s in model.SIDES}
    for u in units:
        if u["state"] == "march":
            sm = _sim(state, u["side"])
            pos = model.unit_pos(state, u)
            road = u.get("road_march_km", sm.get("road_march_km"))   # у части - своё (0 - всегда темп наступления)
            rear = road and all(model.dist_km(pos, f) > sm.get("road_clear_km", 15) for f in foes[u["side"]])
            if rear:                                 # марш по своему тылу - темпом колонны, а не наступления (ОЦЕНКА)
                budget[u["id"]] = road * u.get("supply", 1.0) * frac_day
            else:
                budget[u["id"]] = ((u.get("daily_advance_km") or sm["daily_advance_km"]) * model.strength(u)
                                   * u.get("supply", 1.0) * frac_day)         # без снабжения - медленнее
            budget[u["id"]] *= u.get("speed_k", 1.0)        # передовой отряд, ОМГ - быстрее (ops.py)
            cl = current_link(state, u)
            if cl and logistics.link_detour(state, *cl):                       # разрушен малый мост - объезд
                budget[u["id"]] *= _sim(state, u["side"]).get("bridge_detour_slow", 1.0)
            elif cl and not logistics.link_open(state, *cl):                   # большой мост разрушен - форсирование с ходу
                budget[u["id"]] *= _sim(state, u["side"]).get("crossing_slow", 0.3)
            start[u["id"]] = u["progress_km"]
    new_contacts = []
    for a, b in _contacts(state, units):                          # соприкосновение уже есть до марша
        if b["id"] not in a.get("engaged", []):
            _engage(a, b); new_contacts.append((a, b))
    moving = [u for u in units if u["state"] == "march" and budget.get(u["id"], 0) > 0]
    while moving:
        for u in moving:
            step = min(_sim(state, u["side"])["step_km"], budget[u["id"]])
            u["progress_km"] = min(_length(state, u), u["progress_km"] + step)
            budget[u["id"]] -= step
        for a, b in _contacts(state, units):
            if b["id"] not in a.get("engaged", []):
                _engage(a, b); new_contacts.append((a, b))
        for u in moving:
            if u["state"] == "march" and u["progress_km"] >= _length(state, u) - 1e-6 and u.get("order") == "withdraw":
                u["state"], u["order"] = "refit", None             # дошла до места отхода - сразу восстановление
                lines.append(f"{u['name']}: в тылу ({u['route'][-1]}), восстановление.")
            elif u["state"] == "march" and u["progress_km"] >= _length(state, u) - 1e-6:
                u["state"] = "defend"
                u["defending"] = True
                lines.append(f"{u['name']}: вышел в район {u['route'][-1]}, перешёл к обороне.")
        moving = [u for u in moving if u["state"] == "march" and budget[u["id"]] > 1e-6]
    for u in units if frac_day >= 1.0 else ():
        if u["id"] in start and u["progress_km"] - start[u["id"]] > 0.05:
            lines.append(f"{u['name']}: продвинулся на {u['progress_km'] - start[u['id']]:.0f} км "
                         f"(боеспособность {model.strength(u):.0%}).")
    for a, b in new_contacts:
        where = min((a, b), key=lambda x: 0 if x.get("defending") else 1)
        lines.append(f"Соприкосновение: {a['name']} и {b['name']} (район {where['route'][-1] if where.get('defending') else 'на марше'}).")
    return lines


def arrivals(state: dict) -> list[str]:
    """Резервы и вторые эшелоны: часть с arrives_day вводится в сектор в пункте route[0] в этот день."""
    lines = []
    used: dict[str, int] = {}                    # полосы успеха, куда уже вводятся части этих суток
    for u in state["units"].values():
        if u.get("state") == "pending" and "route" in u and state["day"] >= u.get("arrives_day", 0):
            u["state"] = "defend"
            entry = ops.success_entry(state, u, used) if _sim(state, u["side"]).get("commit_in_success") else None
            if entry and entry != u["route"][0]:   # второй эшелон - в полосе успеха, а не в назначенном заранее районе
                lines.append(f"{u['name']}: вводится в полосе успеха - район {entry} (вместо {u['route'][0]}).")
                u["route"] = [entry]
            u["route"] = [u["route"][0]]
            u["progress_km"] = 0.0
            for a in _attached(state, u):
                a["state"] = "defend"
            lines.append(f"{u['name']}: прибыл в район {u['route'][0]}.")
    return lines


STEP_H = 1            # шаг наземной модели, ч
COMMAND_H = 6         # командование сторон решает раз в столько часов (0, 6, 12, 18 ч)
DAY_S = 86400


def _checks(state: dict) -> list[str]:
    """Уничтожена (боеспособность до 5%) / на марше ниже combat_ineffective_below - остановилась."""
    lines = []
    for u in _maneuver(state):
        if model.strength(u) <= 0.05:
            u["state"] = "destroyed"
            for a in _attached(state, u):
                a["state"] = "destroyed"
            lines.append(f"{u['name']}: уничтожен.")
        elif (u["state"] == "march" and u.get("order") != "withdraw"
              and model.strength(u) < _sim(state, u["side"])["combat_ineffective_below"]):
            u["state"] = "halted"
            lines.append(f"{u['name']}: потерял боеспособность ({model.strength(u):.0%}), остановился.")
    return lines


def advance(state: dict, to_s: float, ground: bool = True) -> list[str]:
    """Наземная модель - до времени суток to_s (с) от state['ground_s'], шагами STEP_H до границы часа: события плана
    полётов (итоги вылетов ИИ, высадки, удары по путям подвоза - airwar.py) в своё время, бой и марш за долю суток,
    занятие пунктов; командование - на границах COMMAND_H. Назад время не идёт. Сводка (потери, продвижение за
    отрезок) - в конце; строки в журнал кампании пишет вызывающий. ground=False - только события плана полётов
    (окно слетанной миссии: бой и марш в нём уже прошли в DCS, дебриф их применил)."""
    from . import airwar
    t = float(state.get("ground_s") or 0)
    to_s = min(float(to_s), DAY_S)
    if to_s <= t + 1:
        return []
    s0 = {u["id"]: model.strength(u) for u in _maneuver(state)}
    p0 = {u["id"]: (tuple(u["route"]), u["progress_km"]) for u in _maneuver(state)}
    lines = []
    step = STEP_H * 3600
    while t < to_s - 1:
        dt = min(step - t % step, to_s - t)
        if ground and t % (COMMAND_H * 3600) < 1:   # оперативный уровень: задачи частям (ops.py)
            for side in model.SIDES:
                lines += ops.commander(state, side, COMMAND_H / 24)
        lines += airwar.resolve(state, t, t + dt)
        if ground:                               # ночью (вне лётного дня) марш и бой медленнее (night_*, доктрина)
            nm, nb = _night(state, t)
            lines += _checks(state)
            lines += battles(state, dt / DAY_S * nb, f"-{int(t // 3600)}")
            lines += movement(state, dt / DAY_S * nm)
            lines += ops.capture(state)
        t += dt
    state["ground_s"] = t
    for u in _maneuver(state):                   # сводка за отрезок
        if u["id"] in s0 and s0[u["id"]] - model.strength(u) > 0.005:
            lines.append(f"{u['name']}: бои к {ato_hhmm(t)} - боеспособность {s0[u['id']]:.0%} -> {model.strength(u):.0%}.")
        r, k = p0.get(u["id"], ((), 0.0))
        if tuple(u["route"]) == r and u["progress_km"] - k > 0.5:
            lines.append(f"{u['name']}: продвинулся на {u['progress_km'] - k:.0f} км.")
    return lines


def _night(state: dict, t: float) -> tuple[float, float]:
    """Множители марша и боя в момент t: ночью - night_march / night_battle доктрины игрока (одни на обе стороны -
    ОЦЕНКА), днём - 1."""
    from . import ato
    if not ato.is_night(state, t):
        return 1.0, 1.0
    sim_ = _sim(state, state["player_side"])
    return sim_.get("night_march", 1.0), sim_.get("night_battle", 1.0)


def ato_hhmm(t: float) -> str:
    if t >= DAY_S:
        return "24:00"
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}"


def tempo(state: dict) -> list[str]:
    """Темп за сутки для стороны в наступлении: занятые пункты и наибольшее продвижение части (по прямой от места
    на начало суток) против нормы доктрины (sim.tempo_km - ОЦЕНКА). Положения - на следующие сутки."""
    lines = []
    prev = state.get("_day_pos") or {}
    owners = state.get("_day_owner") or {}
    for side in model.SIDES:
        sim = _sim(state, side)
        if sim.get("posture") != "offense" or not prev:
            continue
        took = [p for p, o in owners.items() if o != side and state["places"].get(p, {}).get("side") == side]
        adv = max((model.dist_km({"lat": prev[u["id"]][0], "lon": prev[u["id"]][1]}, model.unit_pos(state, u))
                   for u in _maneuver(state) if u["side"] == side and u["id"] in prev
                   and u.get("role") != "air_assault"), default=0.0)   # десант переносится вертолётами - не темп
        norm = sim.get("tempo_km")
        lines.append(f"Темп наступления ({'красные' if side == 'red' else 'синие'}): за сутки занято пунктов {len(took)}, "
                     f"ведущие части продвинулись до {adv:.0f} км" + (f" (норма доктрины ~{norm} км/сутки)" if norm else "") + ".")
    return lines


def _day_snapshot(state: dict) -> None:
    state["_day_pos"] = {u["id"]: [model.unit_pos(state, u)["lat"], model.unit_pos(state, u)["lon"]] for u in _maneuver(state)}
    state["_day_owner"] = {p: q.get("side") for p, q in state["places"].items()}


def end_day(state: dict) -> list[str]:
    """Конец суток: наземная модель - до 24:00 (advance), затем суточный тыл: снабжение, соединение десанта, ремонт,
    ПВО, аэродромы, пополнение; судьба сбитых экипажей; новые сутки."""
    from . import assault, ato, csar             # ato -> planner -> logistics
    ato.ensure(state)                            # план полётов суток - события по часам, перевозки, расход авиации
    lines = advance(state, DAY_S)
    lines += _checks(state)
    lines += tempo(state)
    lines += csar.daily(state)                   # сбитые экипажи: выход к своим, плен
    lines += logistics.supply(state)
    lines += assault.linkup(state)
    lines += logistics.repairs(state)
    for u in state["units"].values():            # артиллерия частей: орудие в сутки из ремонта и пополнения (ОЦЕНКА)
        if u.get("art_lost"):
            u["art_lost"] -= 1
    lines += logistics.air_defence(state)
    lines += samroam.daily(state)               # смена позиций ЗРК по подвижности и близости к фронту
    intel.ensure(state)                         # новые ЗРК противника (из глубины) - в разведку
    lines += logistics.airfields(state)
    from . import command
    lines += command.apply_rebases(state)       # перебазирование по приказу командующего
    lines += farp.daily(state)                  # вертолётные части - на передовые площадки и с них
    lines += logistics.replacements(state)
    from . import pilots
    pilots.ensure_all(state)                    # пополнение экипажей - новые лётчики
    state["day"] += 1
    state["ground_s"] = 0
    lines += arrivals(state)
    _day_snapshot(state)                         # для темпа следующих суток
    for ln in lines:
        model.note(state, ln)
    state["task"] = None
    state["tasks"] = []
    state["ato"] = None                          # план полётов и часы - новых суток (ato.py)
    state["clock_s"] = 0
    state["manifest"] = None
    return lines

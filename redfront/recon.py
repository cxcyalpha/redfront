"""Разведывательные вылеты (задача recon плана полётов; только ИИ). Все числа - ОЦЕНКИ.

DCS разведку не моделирует (фотоаппаратура и РЛС бокового обзора в игре - для вида), поэтому итог - модель:
что попало в полосу датчиков вдоль маршрута, то видели (журнал разведки, intel.py) - если самолёт вернулся.

Датчики - по типу ЛА (aircraft.json, recon: ширина полосы в км от линии пути, на сторону):
  photo - аэрофотоаппараты (только днём), ir - ИК-аппаратура (день и ночь), tv - телевизионная (днём),
  slar - РЛС бокового обзора (день, ночь, облачность; видит технику с расстояния - можно не заходить за линию),
  elint - радиотехническая разведка (только работающие РЛС: ЗРК и КРУ, на большой дальности);
  profile - low (малая высота: ЗРК коридора опасны) или high (МиГ-25РБ: 20 км, скорость - опасны только дальние ЗРК).
Тип без recon - как фотоаппарат на малой высоте (photo 5 км).

Маршрут (planner): точки интереса - давние и примерные данные о частях противника (сначала давние), пункты
противника у линии фронта; цепочка до route_points точек не дальше leg_km друг от друга и в радиусе части. Вылеты -
sorties_per_day на маршрут, по лётному дню (ночью - тип с night и ночным датчиком).

Итог (airwar.resolve): после посадки и обработки (process_h) - части противника в полосе: видели с вероятностью
DETECT_P (колонна на марше заметнее, позиция в обороне - маскировка). Сбит весь вылет - данных нет. Вылет, слетанный
в миссии (группа ИИ), - потери по дебрифу; вне миссии - по ЗРК коридора, как удары ИИ.
Разведка противника - для вида (ИИ противника знает всё); потери - как у всех.
"""
from __future__ import annotations

from . import model

DEFAULT = {"photo": 5, "profile": "low"}
DETECT_P = {"march": 0.9, "battle": 0.9, "default": 0.7}   # ОЦЕНКА: вероятность заметить часть в полосе
HIGH_MIN_KM = 40         # ОЦЕНКА: высотного разведчика достают только ЗРК с радиусом не меньше
LOW_ALT_M = 150          # ОЦЕНКА: высота маршрута маловысотного разведчика (для угроз коридора)


def sensors(type_name: str) -> dict:
    return model.aircraft_info(type_name).get("recon") or DEFAULT


def swath_km(type_name: str, night: bool) -> tuple[float, float]:
    """(полоса по наземным частям, дальность по РЛС ЗРК и КРУ), км на сторону."""
    s = sensors(type_name)
    ground = max([s.get("ir", 0), s.get("slar", 0)] + ([] if night else [s.get("photo", 0), s.get("tv", 0)]))
    return float(ground), float(max(ground, s.get("elint", 0)))


def night_capable(type_name: str) -> bool:
    s = sensors(type_name)
    return bool(model.aircraft_info(type_name).get("night")) and (s.get("ir", 0) > 0 or s.get("slar", 0) > 0)


def legs(state: dict, g: dict) -> list[tuple[dict, dict]]:
    pts = [state["airbases"][g["base"]]] + list(g["route"]) + [state["airbases"][g["base"]]]
    return list(zip(pts, pts[1:]))


def points_of_interest(state: dict, side: str) -> list[tuple[float, dict, str]]:
    """(вес, точка, что) - куда смотреть разведке стороны side. Игрок: давние данные (присутствие 3, примерно 2),
    пункты противника у фронта (1, без свежих данных рядом - 2). Противник (для вида): наши части у фронта и пункты."""
    from . import intel, ops
    foe = model.enemy(side)
    out = []
    fresh = []
    if side == state.get("player_side"):
        for u in state["units"].values():
            if not intel.tracked_ground(state, u) or u["state"] in ("destroyed", "pending"):
                continue
            lv = intel.level(state, u["id"])
            if lv in ("approx", "presence"):
                out.append((3.0 if lv == "presence" else 2.0, intel.known_pos(state, u), u["name"]))
            elif lv == "exact":
                fresh.append(intel.known_pos(state, u))
    else:
        out += [(2.0, model.unit_pos(state, u), u["name"]) for u in ops._maneuver(state, foe)]
    g = ops.graph(state) if state.get("links") else {}
    near = {q for p in g if ops.owner(state, p) == side for q in g[p] if ops.owner(state, q) == foe}
    near |= {r for q in list(near) for r in g.get(q, []) if ops.owner(state, r) == foe}   # и на глубину ещё одного пункта
    for p in sorted(near):
        pos = state["places"][p]
        w = 1.0 if any(model.dist_km(pos, f) < 15 for f in fresh) else 2.0
        out.append((w, {"lat": pos["lat"], "lon": pos["lon"]}, p))
    return out


def plan_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict]) -> list[dict]:
    """Задачи разведки (method recon): маршруты по точкам интереса, исполнитель - ближняя часть разведки."""
    from . import planner
    s = tdef["strike"]
    pois = sorted(points_of_interest(state, side), key=lambda x: -x[0])
    out = []
    tasked: dict[str, int] = {}
    leg_km = tdef.get("leg_km", 60)
    for _ in range(int(tdef.get("routes", 3))):
        if not pois or not performers:
            break
        seed = pois[0]
        best = None
        for r in performers:
            if r.get("count", 0) <= 0:
                continue
            d = model.dist_km(state["airbases"][r["base"]], seed[1])
            radius = planner.strike_radius_km(r) or 300
            key = (tasked.get(r["id"], 0), d)
            if d <= radius and (best is None or key < best[0]):
                best = (key, r, radius)
        if best is None:
            pois.pop(0)
            continue
        _k, perf, radius = best
        base = state["airbases"][perf["base"]]
        route = [seed[1]]
        names = [seed[2]]
        rest = pois[1:]
        while len(route) < tdef.get("route_points", 4):
            cand = [x for x in rest if model.dist_km(route[-1], x[1]) <= leg_km and model.dist_km(base, x[1]) <= radius]
            if not cand:
                break
            nxt = max(cand, key=lambda x: (x[0], -model.dist_km(route[-1], x[1])))
            route.append(nxt[1])
            names.append(nxt[2])
            rest.remove(nxt)
        g = {"group": "strike", "title": s["title"], "performer": perf["id"], "size": s.get("size", 1),
             "base": perf["base"], "route": [dict(p) for p in route],
             "objective": {"kind": "recon", "pos": dict(route[0])}, "maintask": s["maintask"], "loadout": [],
             "lead_min": 0, "ai": {}, "roe": "return_fire",
             "alt_m": (tdef.get("high_alt_m", 18000) if sensors(perf["type"]).get("profile") == "high"
                       else tdef.get("low_alt_m_agl", 300))}
        ground_km, _elint = swath_km(perf["type"], False)
        covered = lambda p: min(planner._seg_dist_km(p, a, b) for a, b in legs(state, g)) <= max(ground_km, 5)
        pois = [x for x in rest if not covered(x[1])]
        tasked[perf["id"]] = tasked.get(perf["id"], 0) + 1
        path = sum(model.dist_km(a, b) for a, b in legs(state, g))
        out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {', '.join(names[:3])}",
                    "performer": perf["id"], "target": None, "group_size": g["size"], "base": perf["base"],
                    "target_pos": dict(route[0]), "ip": dict(route[0]), "distance_km": round(path, 1), "threats": [],
                    "package": [g], "package_notes": "", "ai_only": True})
    return out


def _detect(state: dict, r, u: dict, key: str) -> bool:
    p = DETECT_P.get(u.get("state", ""), DETECT_P["default"])
    return (r.random() < p) if r else p >= 0.5


def resolve(state: dict, t1: float) -> list[str]:
    """Итоги разведывательных вылетов, обработка данных которых закончена к t1 (секунды суток)."""
    from . import airwar, ato, csar, intel, planner
    a = state.get("ato") or {}
    lines = []
    for e in a.get("entries", []):
        if e["kind"] != "recon" or e.get("resolved"):
            continue
        tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        t = e["times"]["strike"]
        if t1 < ato.DAY_S and t["land_s"] + tdef.get("process_h", 1) * 3600 > t1:
            continue                             # конец суток (t1 = DAY_S) - все оставшиеся
        e["resolved"] = True
        g = e["task"]["package"][0]
        perf = state["units"].get(g["performer"])
        if not perf:
            continue
        r = model.rng(state, f"recon-{e['id']}")
        if e["id"] in a.get("played", []):       # слетан в миссии: потери - по дебрифу
            back = max(0, g["size"] - (a.get("lost") or {}).get(e["id"], 0))
        else:                                    # вне миссии: ЗРК коридора и дежурные пары, как удары ИИ
            high = sensors(perf["type"]).get("profile") == "high"
            threats = planner.corridor_threats(state, legs(state, g), model.enemy(e["side"]), None if high else LOW_ALT_M)
            if high:
                threats = [x for x in threats if planner.threat_radius_km(state["units"][x]) >= HIGH_MIN_KM]
            qra = airwar.alerts_near(state, model.enemy(e["side"]), g["route"][0], e["tot_s"])
            pl = min(0.5, airwar.LOSS_PER_THREAT * len(threats) + airwar.QRA_LOSS * qra)
            down = sum(1 for _ in range(g["size"]) if r.random() < pl) if r else 0
            if down:
                perf["count"] = max(0, perf.get("count", 0) - down)
                for k in range(down):
                    if (r.random() if r else 1.0) < airwar.EJECT_P:
                        csar.add_downed(state, perf, f"ai:{e['id']}:{k}", g["route"][0])
                    elif "crews" in perf:
                        perf["crews"] = max(0, perf["crews"] - 1)
                lines.append(f"ИИ, {e['title']}: потеряно {down} {perf['type']} ({perf['name']}).")
            back = g["size"] - down
        if e["side"] != state.get("player_side"):
            continue                             # разведка противника - для вида: он и так знает всё
        if back <= 0:
            lines.append(f"Разведка, {e['title']}: экипаж не вернулся - данных нет.")
            continue
        night = ato.is_night(state, e["tot_s"])
        t_obs = (state["day"] - 1) * ato.DAY_S + e["tot_s"]   # данные - на время пролёта
        ground_km, elint_km = swath_km(perf["type"], night)
        lg = legs(state, g)
        new, upd, sams = 0, 0, 0
        for u in state["units"].values():
            if not intel.tracked(state, u) or u["state"] in ("destroyed", "pending"):
                continue
            pos = model.unit_pos(state, u)
            d = min(planner._seg_dist_km(pos, x, y) for x, y in lg)
            lim = elint_km if intel.tracked_sam(state, u) else ground_km
            if d > lim or not _detect(state, r, u, e["id"]):
                continue
            if intel.tracked_sam(state, u):
                sams += 1
            elif intel.level(state, u["id"]) is None:
                new += 1
            else:
                upd += 1
            intel.seen(state, u["id"], f"разведка ({perf['type']})", t_obs)
        what = []
        if new:
            what.append(f"новых частей {new}")
        if upd:
            what.append(f"уточнено {upd}")
        if sams:
            what.append(f"ЗРК и РЛС {sams}")
        lines.append(f"Разведка, {e['title']}: " + (", ".join(what) if what else "противника в полосе не обнаружено")
                     + f" ({'ночь' if night else 'день'}, полоса {ground_km:.0f} км" + (f", РТР {elint_km:.0f} км" if elint_km > ground_km else "") + ").")
    return lines

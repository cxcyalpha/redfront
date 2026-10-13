"""Планировщик: план дня (список задач) для стороны игрока по её пакету доктрины.

Работает с ролями: исполнители - части стороны игрока с ролью из task.performers, цели - части противника нужной
категории и состояния. Тип техники планировщику не важен. Позже здесь будет цепочка
"наземная обстановка -> задачи авиации -> группы и боевые порядки".
"""
from __future__ import annotations

import math

from . import dcstypes, logistics, model


def strike_radius_km(unit: dict) -> float | None:
    """Радиус части: явный у части в составе сил, иначе по роли (roles.json). None - не задан нигде."""
    r = unit.get("strike_radius_km")
    return r if r is not None else model.role_info(unit["role"]).get("strike_radius_km")


def threat_radius_km(unit: dict) -> float:
    """Радиус угрозы ЗРК: явный у части, иначе по роли, иначе наибольший threat_range пусковых из pydcs."""
    r = unit.get("threat_radius_km")
    if r is None:
        r = model.role_info(unit["role"]).get("threat_radius_km")
    if r is None:
        r = dcstypes.threat_range_km([c["type"] for c in unit.get("composition", [])])
    return r


def _seg_dist_km(p: dict, a: dict, b: dict) -> float:
    k = math.cos(math.radians(p["lat"]))
    ax, ay, bx, by, px, py = a["lon"] * k, a["lat"], b["lon"] * k, b["lat"], p["lon"] * k, p["lat"]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return model.dist_km(p, model.lerp(a, b, t))


def ip_point(base: dict, target: dict, offset_km: float) -> dict:
    """Исходный пункт маршрута (ИПМ) на линии база-цель, offset_km не доходя до цели."""
    d = model.dist_km(base, target)
    return model.lerp(target, base, min(1.0, offset_km / d)) if d else dict(target)


def corridor_threats(state: dict, legs: list[tuple[dict, dict]], against: str) -> list[str]:
    """ЗРК стороны against, которые достают хотя бы один участок маршрута."""
    out = []
    for u in state["units"].values():
        if u["side"] != against or model.category(u) != "sam" or u["state"] == "destroyed" or model.strength(u) <= 0:
            continue
        r = threat_radius_km(u)
        if any(_seg_dist_km(model.unit_pos(state, u), a, b) <= r for a, b in legs):
            out.append(u["id"])
    return out


def detection_radius_km(unit: dict) -> float | None:
    """Дальность обнаружения РЛС ЗРК: явная у части (detection_radius_km), иначе наименьшая detection_range
    среди РЛС группы из pydcs. None - РЛС нет."""
    r = unit.get("detection_radius_km")
    return r if r is not None else dcstypes.detection_range_km([c["type"] for c in unit.get("composition", [])])


def launch_distance_km(sam: dict, g: dict) -> float:
    """Удаление рубежа пуска ПРР от ЗРК: min(standoff_km, дальность обнаружения его РЛС - detect_margin_km) -
    ПРР наводится на излучение, и рубеж должен быть там, где РЛС ЗРК самолёт видит (в DCS пара на 15 км
    от Gepard/Roland с дальностью обнаружения 15/12 км ушла без пуска, Alex). Без данных о РЛС - радиус угрозы
    + detect_margin_km. Если рубеж внутри зоны поражения (Patriot) - лучше нельзя: подход и ожидание на малой высоте."""
    det = detection_radius_km(sam)
    margin = g.get("detect_margin_km", 0)
    d = (det - margin) if det else threat_radius_km(sam) + margin
    return max(0.0, min(g["standoff_km"], d))


def _toward(pos: dict, base: dict, d_km: float) -> dict:
    total = model.dist_km(base, pos)
    return model.lerp(pos, base, min(1.0, d_km / total)) if total else dict(pos)


def launch_point(state: dict, sam: dict, base: dict, g: dict, at_s: float = 0) -> dict:
    """Рубеж пуска по ЗРК: на линии база-ЗРК, в launch_distance_km от того места, где ЗРК будет через at_s
    от начала миссии (приданная колонне ПВО идёт с ней; скорость - замеренная в DCS, без замера колонна считается
    стоящей). Без standoff_km в доктрине - сам ЗРК (поведение 0.2)."""
    pos = model.unit_pos_at(state, sam, at_s, default_kmh=0)
    if not g.get("standoff_km"):
        return dict(pos)
    return _toward(pos, base, launch_distance_km(sam, g))


def hold_point(state: dict, sam: dict, base: dict, g: dict, at_s: float = 0) -> dict:
    """Центр круга ожидания на рубеже: рубеж пуска, отодвинутый к базе на orbit_radius_km (ОЦЕНКА радиуса
    виража ИИ), чтобы круг не заходил ближе рубежа."""
    pos = model.unit_pos_at(state, sam, at_s, default_kmh=0)   # без замера скорости - где стоит: перелёт к ЗРК опаснее недолёта
    if not g.get("standoff_km"):
        return dict(pos)
    return _toward(pos, base, launch_distance_km(sam, g) + g.get("orbit_radius_km", 0))


MAX_TASKS = 8   # ОЦЕНКА: сколько задач показывать в плане дня
STRATEGIC = ("depot", "bridge", "airfield", "factory")
MAX_PER_KIND = 2   # ОЦЕНКА: задач по объектам тыла одного вида в плане дня   # объекты тыла: цель - точка (склад, мост, аэродром)


def plan(state: dict) -> dict | None:
    """План дня для стороны игрока: список задач (state['tasks']) в порядке приоритета - порядок задач в пакете
    доктрины (ОЦЕНКА), внутри - ближние цели первыми. Задачи - варианты вылета: игрок выбирает одну (build --task N),
    авиация на них считается независимо. Возвращает первую (она же state['task']); нет задач - None и причина
    в state['task_reason']."""
    state["task"] = None
    state["tasks"] = []
    tasks, reason = plan_side(state, state["player_side"])
    state["tasks"] = tasks
    if not tasks:
        state["task_reason"] = reason
        return None
    state["task"] = tasks[0]
    state["task_reason"] = None
    return tasks[0]


def plan_side(state: dict, side: str) -> tuple[list[dict], str]:
    """План дня стороны side (состояние кампании не меняет): (задачи, причина, если задач нет).
    Для стороны противника - так же: по нему в миссию ставятся его ИИ-группы (build.enemy_air)."""
    foe = model.enemy(side)
    doc = model.doctrine(state, side)
    if not doc["tasks"]:
        return [], f"у пакета '{doc['package']}' стороны {side} нет авиационных задач"
    reasons, tasks = [], []
    for kind, tdef in doc["tasks"].items():
        performers = [u for u in state["units"].values()
                      if u["side"] == side and u["role"] in tdef["performers"] and logistics.available(state, u) > 0]
        tside = side if tdef["target"].get("side") == "own" else foe      # прикрытие своих войск - цель своя
        cat = tdef["target"]["category"]
        if cat in STRATEGIC:                     # объекты тыла противника: целы и не потеряны; мост - в тылу противника
            targets = [u for u in state["units"].values() if model.category(u) == cat and u["state"] == "active"
                       and u.get("damage", 0) < 0.95
                       and (logistics.bridge_side(state, u) if cat == "bridge" else u["side"]) == tside]
        else:
            targets = [u for u in state["units"].values()
                       if u["side"] == tside and model.category(u) == cat and _state_ok(u, tdef["target"]["state"])]
        if not targets:
            continue
        found = False
        if cat in STRATEGIC:                     # объекты тыла: не больше MAX_PER_KIND ближних, чтобы не забить план дня
            ref = performers[0] if performers else None
            if ref:
                targets.sort(key=lambda t: model.dist_km(state["airbases"][ref["base"]], model.unit_pos(state, t)))
            targets = targets[:MAX_PER_KIND]
        for tgt in targets:
            tpos = model.unit_pos(state, tgt)
            best = None
            for r in performers:
                radius = strike_radius_km(r)
                if radius is None:
                    reasons.append(f"{r['name']}: не задан радиус (strike_radius_km у части или у роли {r['role']})")
                    continue
                d = model.dist_km(state["airbases"][r["base"]], tpos)
                if d <= radius and (best is None or d < best[0]):
                    best = (d, r)
            if best is None:
                reasons.append(f"{tdef['title']}: {tgt['name']} - нет исполнителей ({', '.join(tdef['performers'])}) в радиусе")
                continue
            d, perf = best
            base = state["airbases"][perf["base"]]
            ip = ip_point(base, tpos, tdef["ip_offset_km"])
            threats = corridor_threats(state, [(base, ip), (ip, tpos)], foe)
            groups, why = package(state, tdef, perf, tgt, tpos, ip, threats)
            if groups is None:
                reasons.append(f"{tdef['title']}: {tgt['name']} - {why}")
                continue
            found = True
            tasks.append({
                "kind": kind, "side": side, "title": f"{tdef['title']}: {tgt['name']}",
                "performer": perf["id"], "target": tgt["id"], "group_size": groups[0]["size"], "base": perf["base"],
                "target_pos": tpos, "ip": ip, "distance_km": round(d, 1), "threats": threats,
                "package": groups,          # тактическая группа: [ударная, обеспечения...] ('Тактика ВВС' 3.3.3)
                "package_notes": why,
            })
        if not found and not targets:
            reasons.append(f"{tdef['title']}: целей нет")
    return tasks[:MAX_TASKS], "; ".join(reasons) or "целей для задач доктрины нет"


def choose(state: dict, n: int) -> dict:
    """Выбрать задачу плана дня по номеру (с 1)."""
    tasks = state.get("tasks") or []
    if not 1 <= n <= len(tasks):
        raise ValueError(f"в плане дня задач {len(tasks)}; номер {n} вне списка (сначала plan)")
    state["task"] = tasks[n - 1]
    return state["task"]




ZONE_KEYS = ("alt_m", "zone_km", "cap_min", "hold_after_min")   # параметры зоны прикрытия из доктрины


def _state_ok(unit: dict, want) -> bool:
    return unit["state"] in want if isinstance(want, list) else unit["state"] == want


def enemy_fighters(state: dict, side: str, pos: dict) -> bool:
    """Есть ли у противника стороны side истребители, достающие до pos (роль fighter/interceptor, радиус части)."""
    for u in state["units"].values():
        if u["side"] == model.enemy(side) and u["role"] in ("fighter", "interceptor") and u.get("count", 0) > 0:
            r = strike_radius_km(u)
            if r is not None and model.dist_km(state["airbases"][u["base"]], pos) <= r:
                return True
    return False


def _can(unit: dict, maintask: str) -> bool:
    """Умеет ли тип части задачу DCS (planes.X.tasks), напр. Су-24М - SEAD, Су-25 - нет."""
    from dcs import task as _task
    t = getattr(_task, maintask, None)
    return t is not None and t in dcstypes.flying(unit["type"]).tasks


def package(state: dict, tdef: dict, perf: dict, tgt: dict, tpos: dict, ip: dict,
            threats: list[str]) -> tuple[list[dict] | None, str]:
    """Тактическая группа для задачи: ударная группа + группы обеспечения из доктрины (task.support).

    Группа обеспечения ставится, если выполнено её условие (when): threats - в коридоре есть ЗРК,
    moving_target - цель на марше. Исполнитель - часть своей стороны с ролью из performers, у которой хватает
    самолётов (с учётом уже отданных в пакет) и радиуса до объектов группы; сначала - та же часть, что и ударная.
    Если обязательную (required) группу собрать нельзя - пакета нет: (None, причина).
    """
    units = state["units"]
    avail = {u["id"]: logistics.available(state, u) for u in units.values() if model.category(u) in ("air", "heli")}
    s = tdef["strike"]
    size = min(s["size"], avail[perf["id"]])
    avail[perf["id"]] -= size
    if s.get("mode") == "cap_zone":              # прикрытие района (истребители): зона над своими войсками
        route, objective = [tpos], {"kind": "cap_zone", "unit": tgt["id"], "pos": tpos}
    elif model.category(tgt) in STRATEGIC:       # объект тыла: удар по точке (бомбы; по мосту - по объекту карты)
        route, objective = [ip, tpos], {"kind": "point", "unit": tgt["id"], "pos": tpos, "object": model.category(tgt)}
    else:
        route, objective = [ip, tpos], {"kind": "column", "unit": tgt["id"], "pos": tpos}
    groups = [{"group": "strike", "title": s["title"], "performer": perf["id"], "size": size,
               "base": perf["base"], "route": route, "objective": objective,
               "maintask": s["maintask"], "loadout": s.get("loadout", []), "lead_min": 0, "ai": s.get("ai") or {},
               **{k: s[k] for k in ZONE_KEYS if k in s}}]
    notes = []
    for g in tdef.get("support", []):
        if g["when"] == "threats" and not threats:
            continue
        if g["when"] == "moving_target" and tgt.get("state") != "march":
            continue
        if g["when"] == "enemy_fighters" and not enemy_fighters(state, perf["side"], tpos):
            continue
        if g["when"] == "threats":
            objs = sorted((units[t] for t in threats),
                          key=lambda u: model.dist_km(state["airbases"][perf["base"]], model.unit_pos(state, u)))
            objective = {"kind": "sam", "units": [u["id"] for u in objs]}
            # одно ожидание - на рубеже по ближнему ЗРК; атака - по всем (в бою ЗРК стоят рядом)
            route_of = lambda base, g=g, objs=objs: [hold_point(state, objs[0], base, g)]
        elif g.get("mode") == "cover_zone":       # прикрытие группы: зона над целью на время удара
            objective = {"kind": "cover_zone", "unit": tgt["id"], "pos": tpos}
            route_of = lambda base: [tpos]
        else:
            kind = "search_zone" if g.get("mode") == "search_zone" else "flyover"
            objective = {"kind": kind, "unit": tgt["id"], "pos": tpos}
            route_of = lambda base: [ip_point(base, tpos, tdef["ip_offset_km"]), tpos]
        flights = int(g.get("flights", 1))       # несколько пар - отдельные группы, у каждой своя задача атаки
        need = g["size"] * flights
        cands = [u for u in units.values()
                 if u["side"] == perf["side"] and u["role"] in g["performers"] and avail.get(u["id"], 0) >= need]
        # сначала те, чей тип умеет основную задачу группы (для подавления ПВО - SEAD), затем та же часть, что ударная, затем ближние
        cands.sort(key=lambda u: (not _can(u, g["maintask"][0]), u["id"] != perf["id"],
                                  model.dist_km(state["airbases"][u["base"]], tpos)))
        chosen = None
        for u in cands:
            base = state["airbases"][u["base"]]
            radius = strike_radius_km(u)
            if radius is not None and all(model.dist_km(base, p) <= radius for p in route_of(base)):
                chosen = u
                break
        if chosen is None:
            msg = f"нет исполнителя для группы '{g['title']}' ({need} ЛА с ролью {', '.join(g['performers'])} в радиусе)"
            if g.get("required"):
                return None, msg
            notes.append(msg + " - группа не назначена")
            continue
        avail[chosen["id"]] -= need
        for k in range(flights):
            groups.append({"group": g["id"] if k == 0 else f"{g['id']}{k + 1}", "support_id": g["id"],
                           "title": g["title"] if flights == 1 else f"{g['title']}, пара {k + 1}",
                           "performer": chosen["id"], "size": g["size"],
                           "base": chosen["base"], "route": route_of(state["airbases"][chosen["base"]]),
                           "objective": objective, "maintask": g["maintask"], "loadout": g["loadout"],
                           "lead_min": g.get("lead_min", 0), "roe": g.get("roe"), "ai": g.get("ai") or {},
                           "search_min": g.get("search_min"), "zone_margin_km": g.get("zone_margin_km"),
                           "search_alt_m": g.get("search_alt_m"), "launch_alt_m": g.get("launch_alt_m"),
                           **{k: g[k] for k in ZONE_KEYS if k in g}})
    return groups, "; ".join(notes)

"""Планировщик: план дня (список задач) для стороны игрока по её пакету доктрины.

Работает с ролями: исполнители - части стороны игрока с ролью из task.performers, цели - части противника нужной
категории и состояния. Тип техники планировщику не важен. Позже здесь будет цепочка
"наземная обстановка -> задачи авиации -> группы и боевые порядки".
"""
from __future__ import annotations

import copy
import math

from . import dcstypes, logistics, model, ops


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


RADAR_MAST_M = 10       # ОЦЕНКА: высота антенны РЛС ЗРК над местностью (для радиогоризонта)


def radar_horizon_km(h1_m: float, h2_m: float) -> float:
    """Дальность радиогоризонта (стандартная рефракция, 4/3 радиуса Земли) между антенной h1 и целью h2, км.
    Рельеф не учитывается - в холмах реальная дальность меньше."""
    return 4.12 * (math.sqrt(max(0.0, h1_m)) + math.sqrt(max(0.0, h2_m)))


def corridor_threats(state: dict, legs: list[tuple[dict, dict]], against: str, low_alt_m: float | None = None) -> list[str]:
    """ЗРК стороны against, которые достают хотя бы один участок маршрута. low_alt_m - высота маршрута в зонах ЗРК
    (low_alt_m_agl задачи): радиус угрозы не больше радиогоризонта РЛС по цели на этой высоте - иначе С-200 с
    дальностью 255 км по высотной цели "достаёт" любой маловысотный маршрут, и подавление назначается на всё подряд."""
    out = []
    for u in state["units"].values():
        if u["side"] != against or model.category(u) != "sam" or u["state"] == "destroyed" or model.strength(u) <= 0:
            continue
        r = threat_radius_km(u)
        if low_alt_m is not None:
            r = min(r, radar_horizon_km(RADAR_MAST_M, low_alt_m))
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
MAX_PER_KIND = 2   # ОЦЕНКА: задач одного вида в плане дня   # объекты тыла: цель - точка (склад, мост, аэродром)


def plan(state: dict) -> dict | None:
    """План дня для стороны игрока: список задач (state['tasks']) в порядке приоритета - порядок задач в пакете
    доктрины (ОЦЕНКА), внутри - ближние цели первыми. Задачи - варианты вылета: игрок выбирает одну (build --task N),
    авиация на них считается независимо. Возвращает первую (она же state['task']); нет задач - None и причина
    в state['task_reason']."""
    from . import ato                            # ato импортирует planner
    state["task"] = None
    state["tasks"] = []
    a = ato.ensure(state)
    clock = max(state.get("clock_s") or 0, state.get("ground_s") or 0)   # наземная модель не идёт назад
    tasks = []
    for e in a["entries"]:                       # вылеты своей стороны по времени; дежурства (ДРЛО, заправщик) - только ИИ
        if e["side"] != state["player_side"] or (e["ai_only"] and not player_lift(state, e)) or e["id"] in a["done"]:
            continue
        t = e["times"]["strike"]
        if t["takeoff_s"] < clock:
            continue
        tasks.append({**copy.deepcopy(e["task"]), "ato_id": e["id"], "tot_s": e["tot_s"], "takeoff_s": t["takeoff_s"],
                      "night": bool(e.get("night"))})
    state["tasks"] = tasks
    if not tasks:
        _t, reason = plan_side(state, state["player_side"])
        state["task_reason"] = (f"в плане полётов на сутки больше нет вылетов после {ato.hhmm(clock)}" if clock and _t
                                else reason)
        return None
    state["task"] = tasks[0]
    state["task_reason"] = None
    return tasks[0]


def player_lift(state: dict, e: dict) -> bool:
    """Перевозка снабжения вертолётом - её может слетать игрок (груз - ящики CTLD, build.py); самолётом - только ИИ."""
    g = e["task"]["package"][0]
    return g["objective"]["kind"] == "airlift" and model.category(state["units"][g["performer"]]) == "heli"


def _load(tasked: dict, unit: dict) -> int:
    """Загрузка исполнителя в этом плане: задач у его типа ЛА + у самой части. Сначала - менее загруженные: вылеты
    расходятся по типам, а не достаются пяти полкам МиГ-27 подряд (первый лог Германии)."""
    return tasked.get("type:" + str(unit.get("type")), 0) + tasked.get(unit["id"], 0)


def _book(state: dict, tasked: dict, uid: str) -> None:
    tasked[uid] = tasked.get(uid, 0) + 1
    t = "type:" + str(state["units"][uid].get("type"))
    tasked[t] = tasked.get(t, 0) + 1


def plan_side(state: dict, side: str, max_tasks: int = MAX_TASKS, per_kind: int = MAX_PER_KIND) -> tuple[list[dict], str]:
    """План дня стороны side (состояние кампании не меняет): (задачи, причина, если задач нет).
    Для стороны противника - так же: по нему в миссию ставятся его ИИ-группы (build.enemy_air)."""
    foe = model.enemy(side)
    doc = model.doctrine(state, side)
    if not doc["tasks"]:
        return [], f"у пакета '{doc['package']}' стороны {side} нет авиационных задач"
    reasons, tasks = [], []
    tasked: dict[str, int] = {}                  # задач у части в этом плане
    for kind, tdef in doc["tasks"].items():
        performers = [u for u in state["units"].values()
                      if u["side"] == side and u["role"] in tdef["performers"] and logistics.available(state, u) > 0]
        if tdef.get("method") == "orbit":        # дежурство в зоне над своей территорией (ДРЛО, заправщик)
            t = orbit_task(state, side, kind, tdef, performers)
            if t:
                tasks.append(t)
            continue
        if tdef.get("method") == "alert":        # дежурные пары ПВО на аэродромах у фронта (только ИИ)
            tasks += alert_tasks(state, side, kind, tdef, performers)
            continue
        if tdef.get("method") == "airlift":      # воздушные перевозки снабжения (только ИИ)
            tasks += airlift_tasks(state, side, kind, tdef, performers)
            continue
        if tdef.get("method") == "interdiction":   # удары по путям подвоза противника (convoys.py)
            tasks += interdiction_tasks(state, side, kind, tdef, performers, tasked, reasons, per_kind)
            continue
        if tdef.get("method") == "csar":         # поиск и спасение своих сбитых экипажей (csar.py)
            tasks += csar_tasks(state, side, kind, tdef, performers, tasked)
            continue
        if tdef.get("method") == "air_evac":     # эвакуация своего десанта из тыла противника (assault.py)
            tasks += evac_tasks(state, side, kind, tdef, performers, tasked)
            continue
        if tdef.get("method") == "air_assault":  # вертолётный десант в тыл противника (assault.py)
            t = assault_tasks(state, side, kind, tdef, performers, tasked)
            if not t:
                reasons.append(f"{tdef['title']}: нет готовой десантной роты, площадки или вертолётов")
            tasks += t
            continue
        tside = side if tdef["target"].get("side") == "own" else foe      # прикрытие своих войск - цель своя
        cat = tdef["target"]["category"]
        if cat in STRATEGIC:                     # объекты тыла противника: целы и не потеряны; мост - в тылу противника
            targets = [u for u in state["units"].values() if model.category(u) == cat and u["state"] == "active"
                       and u.get("damage", 0) < 0.95
                       and (logistics.bridge_side(state, u) if cat == "bridge" else u["side"]) == tside]
        elif cat == "sam":                       # позиции ЗРК противника (fixed - только объектовая ПВО): исправные
            targets = [u for u in state["units"].values() if u["side"] == tside and model.category(u) == "sam"
                       and not u.get("attached_to") and u["state"] not in ("destroyed", "pending")
                       and model.strength(u) >= tdef["target"].get("min_strength", 0.5)
                       and (u.get("fixed") or not tdef["target"].get("fixed"))]
        else:
            targets = [u for u in state["units"].values()
                       if u["side"] == tside and model.category(u) == cat and _state_ok(u, tdef["target"]["state"])]
        if not targets:
            continue
        found = False
        if cat in STRATEGIC or cat == "sam":     # объекты тыла, позиции ЗРК: не больше MAX_PER_KIND ближних к базам исполнителей
            bases = [state["airbases"][r["base"]] for r in performers]
            if bases:
                targets.sort(key=lambda t: min(model.dist_km(b, model.unit_pos(state, t)) for b in bases))
            targets = targets[:per_kind]
        n_kind = 0
        for tgt in targets:
            if n_kind >= per_kind:           # задач одного вида в плане дня - не больше (иначе план - 8 одинаковых)
                break
            tpos = model.unit_pos(state, tgt)
            best = None
            for r in performers:
                radius = strike_radius_km(r)
                if radius is None:
                    reasons.append(f"{r['name']}: не задан радиус (strike_radius_km у части или у роли {r['role']})")
                    continue
                d = model.dist_km(state["airbases"][r["base"]], tpos)
                # сначала - части с меньшим числом задач в этом плане (вылеты распределяются по полкам), затем ближние
                key = (_load(tasked, r), d)
                if d <= radius and (best is None or key < best[0]):
                    best = (key, r)
            if best is None:
                reasons.append(f"{tdef['title']}: {tgt['name']} - нет исполнителей ({', '.join(tdef['performers'])}) в радиусе")
                continue
            (_n, d), perf = best
            base = state["airbases"][perf["base"]]
            ip = ip_point(base, tpos, tdef["ip_offset_km"])
            threats = corridor_threats(state, [(base, ip), (ip, tpos)], foe, tdef.get("low_alt_m_agl"))
            groups, why = package(state, tdef, perf, tgt, tpos, ip, threats)
            if groups is None:
                reasons.append(f"{tdef['title']}: {tgt['name']} - {why}")
                continue
            found = True
            n_kind += 1
            for g in groups:
                _book(state, tasked, g["performer"])
            if not threats and tdef.get("medium_alt_m_agl"):   # угроз ЗРК в коридоре нет - переход на средних высотах
                for g in groups:
                    g["transit_alt_m_agl"] = tdef["medium_alt_m_agl"]
            tasks.append({
                "kind": kind, "side": side, "title": f"{tdef['title']}: {tgt['name']}",
                "performer": perf["id"], "target": tgt["id"], "group_size": groups[0]["size"], "base": perf["base"],
                "target_pos": tpos, "ip": ip, "distance_km": round(d, 1), "threats": threats,
                "package": groups,          # тактическая группа: [ударная, обеспечения...] ('Тактика ВВС' 3.3.3)
                "package_notes": why,
            })
        if not found and not targets:
            reasons.append(f"{tdef['title']}: целей нет")
    orbit = [t for t in tasks if t.get("ai_only")]   # дежурство - вне лимита плана дня (игрок его не летает)
    return [t for t in tasks if not t.get("ai_only")][:max_tasks] + orbit, "; ".join(reasons) or "целей для задач доктрины нет"


def orbit_point(state: dict, side: str, standoff_km: float) -> dict | None:
    """Зона дежурства: середина линии фронта (среднее середин связей между пунктами сторон), отнесённая на standoff_km
    в сторону своей территории (к среднему своих пунктов). Нет линии фронта - None."""
    fl = ops.front_links(state)
    if not fl:
        return None
    pl = state["places"]
    mids = [model.lerp(pl[a], pl[b], 0.5) for a, b in fl]
    c = {"lat": sum(p["lat"] for p in mids) / len(mids), "lon": sum(p["lon"] for p in mids) / len(mids)}
    own = [p for n, p in pl.items() if ops.owner(state, n) == side]
    if not own:
        return None
    home = {"lat": sum(p["lat"] for p in own) / len(own), "lon": sum(p["lon"] for p in own) / len(own)}
    return model.offset(c, model.bearing_deg(c, home), standoff_km * 1000)


def orbit_task(state: dict, side: str, kind: str, tdef: dict, performers: list[dict]) -> dict | None:
    """Задача дежурства (method orbit): одна группа ближней части с самолётами, достающей до зоны."""
    pos = orbit_point(state, side, tdef.get("standoff_km", 150))
    if pos is None:
        return None
    best = None
    for r in performers:
        radius = strike_radius_km(r)
        d = model.dist_km(state["airbases"][r["base"]], pos)
        if (radius is None or d <= radius) and (best is None or d < best[0]):
            best = (d, r)
    if best is None:
        return None
    d, perf = best
    s = tdef["strike"]
    g = {"group": "strike", "title": s["title"], "performer": perf["id"], "size": min(s["size"], logistics.available(state, perf)),
         "base": perf["base"], "route": [pos], "objective": {"kind": "orbit", "pos": pos, "maintask": s["maintask"][0]},
         "maintask": s["maintask"], "loadout": s.get("loadout", []), "lead_min": 0, "ai": {}, "alt_m": s.get("alt_m")}
    return {"kind": kind, "side": side, "title": tdef["title"], "performer": perf["id"], "target": f"orbit_{side}_{kind}",
            "group_size": g["size"], "base": perf["base"], "target_pos": pos, "ip": pos, "distance_km": round(d, 1),
            "threats": [], "package": [g], "package_notes": "", "ai_only": True}


def alert_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict]) -> list[dict]:
    """Дежурство ПВО (method alert): до qra_bases пар на разных аэродромах - истребительные части, ближние к линии
    фронта; зона после взлёта - в cap_offset_km от базы к фронту."""
    fl = ops.front_links(state)
    if not fl:
        return []
    pl = state["places"]
    mids = [model.lerp(pl[a], pl[b], 0.5) for a, b in fl]
    def front_km(p):
        return min(model.dist_km(p, q) for q in mids)
    s = tdef["strike"]
    out, bases = [], set()
    for r in sorted((r for r in performers if logistics.available(state, r) >= s["size"]),
                    key=lambda r: front_km(state["airbases"][r["base"]])):
        if r["base"] in bases:
            continue
        bases.add(r["base"])
        base = state["airbases"][r["base"]]
        q = min(mids, key=lambda q: model.dist_km(base, q))
        d = model.dist_km(base, q)
        cap = model.lerp(base, q, min(1.0, tdef.get("cap_offset_km", 30) / d)) if d > 0 else dict(base)
        g = {"group": "strike", "title": s["title"], "performer": r["id"], "size": s["size"], "base": r["base"],
             "route": [cap], "objective": {"kind": "alert", "pos": cap}, "maintask": s["maintask"],
             "loadout": s.get("loadout", []), "lead_min": 0, "ai": {}, "alt_m": tdef.get("cap_alt_m", 6000)}
        out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {base['name']} ({r['name']})",
                    "performer": r["id"], "target": f"qra_{side}_{r['base']}", "group_size": s["size"], "base": r["base"],
                    "target_pos": cap, "ip": cap, "distance_km": round(model.dist_km(base, cap), 1), "threats": [],
                    "package": [g], "package_notes": "", "ai_only": True})
        if len(out) >= tdef.get("qra_bases", 3):
            break
    return out


def airlift_needs(state: dict, side: str, tdef: dict) -> list[tuple[dict, str]]:
    """Куда везти: (склад, аэродром назначения) - свои склады с запасом ниже airlift_below, у которых есть свой
    открытый аэродром не дальше airlift_depot_km; отрезанные от подвоза из тыла - первыми, затем по запасу."""
    logistics.init_depots(state)
    conn = logistics.road_connected(state, side)
    out = []
    for d in logistics.objects(state, "depot"):
        if d["side"] != side or not logistics.supplies(d) or d.get("state") == "lost" or not d.get("place"):
            continue
        stock = logistics.depot_stock(d)
        if stock >= tdef.get("airlift_below", 0.9):
            continue
        pos = state["places"][d["place"]]
        bases = [(model.dist_km(b, pos), k) for k, b in state["airbases"].items()
                 if b.get("side") == side and b.get("state", "open") in ("open", "active")]
        bases = [x for x in bases if x[0] <= tdef.get("airlift_depot_km", 40)]
        if bases:
            out.append(((d["id"] in conn, stock), d, min(bases)[1]))
    out.sort(key=lambda x: x[0])
    return [(d, b) for _k, d, b in out]


def airlift_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict]) -> list[dict]:
    """Задачи воздушной перевозки (method airlift): по направлению (склад + аэродром назначения) - группа ближней
    транспортной части, достающей до аэродрома (не с него же); части распределяются по направлениям."""
    out = []
    tasked: dict[str, int] = {}
    s = tdef["strike"]
    for d, dest in airlift_needs(state, side, tdef)[:tdef.get("airlift_max", 4)]:
        dpos = state["airbases"][dest]
        best = None
        for r in performers:
            if r["base"] == dest or (state["airbases"][dest].get("kind") == "farp" and model.category(r) != "heli"):
                continue                         # на вертолётную площадку - только вертолётом
            km = model.dist_km(state["airbases"][r["base"]], dpos)
            radius = strike_radius_km(r)
            if radius is not None and km > radius:
                continue
            key = (tasked.get(r["id"], 0), km)
            if best is None or key < best[0]:
                best = (key, r)
        if best is None:
            continue
        (_n, km), perf = best
        tasked[perf["id"]] = tasked.get(perf["id"], 0) + 1
        helo = model.category(perf) == "heli"
        alt = tdef.get("helo_alt_m_agl", 150) if helo else tdef["transit_alt_m_agl"]
        g = {"group": "strike", "title": s["title"], "performer": perf["id"],
             "size": min(s["size"], logistics.available(state, perf)), "base": perf["base"], "route": [dict(dpos)],
             "objective": {"kind": "airlift", "airbase": dest, "depot": d["id"], "pos": {"lat": dpos["lat"], "lon": dpos["lon"]}},
             "maintask": s["maintask"], "loadout": [], "lead_min": 0, "ai": {}, "alt_m": alt}
        out.append({"kind": kind, "side": side,
                    "title": f"{tdef['title']}: {state['airbases'][perf['base']]['name']} -> {dpos['name']} ({d['name']})",
                    "performer": perf["id"], "target": d["id"], "group_size": g["size"], "base": perf["base"],
                    "target_pos": g["objective"]["pos"], "ip": g["objective"]["pos"], "distance_km": round(km, 1),
                    "threats": [], "package": [g], "package_notes": "", "ai_only": True})
    return out


def interdiction_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict], tasked: dict,
                       reasons: list[str], per_kind: int) -> list[dict]:
    """Удары по путям подвоза (method interdiction): участки путей подвоза противника с потоком не меньше
    convoys.MIN_FLOW_T, по убыванию потока; исполнитель - в радиусе, с меньшим числом задач; пакет - как у удара
    (группы обеспечения доктрины). Цель - псевдочасть роли supply_route (в составе сил её нет)."""
    from . import convoys
    foe = model.enemy(side)
    flows = sorted(((t, l) for l, t in convoys.link_flows(state, foe).items() if t >= convoys.MIN_FLOW_T), reverse=True)
    out = []
    for t, link in flows:
        if len(out) >= min(per_kind, tdef.get("per_day", per_kind)):
            break
        tpos = convoys.link_mid(state, link)
        best = None
        for r in performers:
            radius = strike_radius_km(r)
            d = model.dist_km(state["airbases"][r["base"]], tpos)
            if radius is not None and d <= radius and (best is None or (_load(tasked, r), d) < best[0]):
                best = ((_load(tasked, r), d), r)
        if best is None:
            continue
        (_n, d), perf = best
        cid = convoys.convoy_id(foe, link)
        tgt = {"id": cid, "role": "supply_route", "side": foe, "state": "march", "name": f"колонны снабжения {link.replace('>', ' - ')}"}
        base = state["airbases"][perf["base"]]
        ip = ip_point(base, tpos, tdef["ip_offset_km"])
        threats = corridor_threats(state, [(base, ip), (ip, tpos)], foe, tdef.get("low_alt_m_agl"))
        groups, why = package(state, tdef, perf, tgt, tpos, ip, threats)
        if groups is None:
            reasons.append(f"{tdef['title']}: {link} - {why}")
            continue
        for g in groups:
            _book(state, tasked, g["performer"])
        if not threats and tdef.get("medium_alt_m_agl"):
            for g in groups:
                g["transit_alt_m_agl"] = tdef["medium_alt_m_agl"]
        out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {link.replace('>', ' - ')} (~{t:.0f} т/сутки)",
                    "performer": perf["id"], "target": cid, "target_kind": "convoy", "link": link,
                    "group_size": groups[0]["size"], "base": perf["base"], "target_pos": tpos, "ip": ip,
                    "distance_km": round(d, 1), "threats": threats, "package": groups,
                    "package_notes": "; ".join(x for x in (f"поток ~{t / convoys.TRUCK_T:.0f} грузовиков в сутки", why) if x)})
    return out


def csar_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict], tasked: dict) -> list[dict]:
    """Задачи поиска и спасения (method csar): свои экипажи на земле не на своей территории (со своей выйдут сами),
    ближние к вертолётным частям первыми; группа - ближняя вертолётная часть в радиусе; не больше per_day."""
    from . import csar
    foe = model.enemy(side)
    out = []
    downed = [d for d in state.get("downed", []) if d["side"] == side and csar.owner_at(state, d["pos"]) != side]
    s = tdef["strike"]
    cands = []
    for d in downed:
        best = None
        for r in performers:
            km = model.dist_km(state["airbases"][r["base"]], d["pos"])
            radius = strike_radius_km(r)
            if (radius is not None and km > radius) or logistics.available(state, r) < 1:
                continue
            key = (tasked.get(r["id"], 0), km)
            if best is None or key < best[0]:
                best = (key, r)
        if best:
            cands.append((best[0][1], d, best[1]))
    for km, d, perf in sorted(cands, key=lambda x: x[0])[:tdef.get("per_day", 2)]:
        base = state["airbases"][perf["base"]]
        size = min(s["size"], logistics.available(state, perf))
        g = {"group": "strike", "title": s["title"], "performer": perf["id"], "size": size, "base": perf["base"],
             "route": [dict(d["pos"])], "objective": {"kind": "csar", "downed": d["id"], "pos": dict(d["pos"])},
             "maintask": s["maintask"], "loadout": [], "lead_min": 0, "ai": {}, "alt_m": tdef["transit_alt_m_agl"]}
        tasked[perf["id"]] = tasked.get(perf["id"], 0) + 1
        out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {csar.title(state, d)}",
                    "performer": perf["id"], "target": d["id"], "group_size": size, "base": perf["base"],
                    "target_pos": dict(d["pos"]), "ip": dict(d["pos"]), "distance_km": round(km, 1),
                    "threats": corridor_threats(state, [(base, d["pos"])], foe, tdef.get("low_alt_m_agl")),
                    "package": [g], "package_notes": f"маяк {d['freq_khz']} кГц (АРК / ADF); на земле с суток {d['day']}"})
    return out


GROUP_MAX = 4   # бортов в группе ЛА DCS


def assault_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict], tasked: dict) -> list[dict]:
    """Задачи вертолётного десанта (method air_assault): рота из резерва (assault.reserve) на лучший пункт
    (assault.candidates); группа - транспортная вертолётная часть, которая поднимает роту не больше чем max_helos
    бортами и достаёт до площадки; не больше per_day задач."""
    from . import assault
    res = sorted(assault.reserve(state, side), key=lambda u: -model.strength(u))
    if not res:
        return []
    foe = model.enemy(side)
    out, used = [], set()
    places = assault.candidates(state, side, tdef)
    for u in res:
        if len(out) >= tdef.get("per_day", 1):
            break
        for place in places:
            if place in used:
                continue
            lz = assault.lz_point(state, side, place, tdef)
            best = None
            for r in performers:
                need = assault.lift_need(u, r["type"])
                if need > min(logistics.available(state, r), tdef.get("max_helos", 8)):
                    continue
                km = model.dist_km(state["airbases"][r["base"]], lz)
                radius = strike_radius_km(r)
                if radius is not None and km > radius:
                    continue
                key = (tasked.get(r["id"], 0), km)
                if best is None or key < best[0]:
                    best = (key, r, need)
            if best is None:
                continue
            (_n, km), perf, need = best
            base = state["airbases"][perf["base"]]
            threats = corridor_threats(state, [(base, lz)], foe, tdef.get("low_alt_m_agl"))
            if len(threats) > tdef.get("max_threats", 1):   # вертолёты через насыщенную ПВО не идут - другая площадка
                continue
            s = tdef["strike"]
            groups = []                          # группа ЛА в DCS - не больше 4 бортов: подъём - волнами по 4, через минуту
            for k in range(0, need, GROUP_MAX):
                groups.append({"group": "strike" if not k else f"lift{k // GROUP_MAX + 1}",
                               "title": s["title"] + (f" ({k // GROUP_MAX + 1})" if k else ""), "performer": perf["id"],
                               "size": min(GROUP_MAX, need - k), "base": perf["base"], "route": [lz],
                               "objective": {"kind": "air_assault", "unit": u["id"], "place": place, "pos": lz},
                               "maintask": s["maintask"], "loadout": [], "lead_min": -k // GROUP_MAX, "ai": {},
                               "alt_m": tdef["transit_alt_m_agl"]})
            tasked[perf["id"]] = tasked.get(perf["id"], 0) + 1
            used.add(place)
            out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {u['name']} - {place}",
                        "performer": perf["id"], "target": u["id"], "group_size": need, "base": perf["base"],
                        "target_pos": lz, "ip": lz, "distance_km": round(km, 1), "threats": threats,
                        "package": groups, "package_notes": f"площадка в {tdef.get('lz_offset_km', 2)} км от {place}; "
                                                          f"{need} x {perf['type']} ({assault.troops(perf['type'])} десантников на борт)"})
            break
    return out


def evac_tasks(state: dict, side: str, kind: str, tdef: dict, performers: list[dict], tasked: dict) -> list[dict]:
    """Эвакуация десанта (method air_evac): рота в тылу противника (assault.evac_needed) - площадка у её пункта в
    сторону своих; группа - транспортная вертолётная часть, которая поднимает живых не больше чем max_helos бортами и
    достаёт до площадки; через насыщенную ПВО (больше max_threats ЗРК в коридоре) не идут."""
    from . import assault
    foe = model.enemy(side)
    out = []
    for u in assault.evac_needed(state, side, tdef)[:tdef.get("per_day", 1)]:
        place = u["route"][-1]
        lz = assault.lz_point(state, side, place, tdef)
        best = None
        for r in performers:
            need = assault.lift_need(u, r["type"], alive=True)
            if need > min(logistics.available(state, r), tdef.get("max_helos", 8)):
                continue
            km = model.dist_km(state["airbases"][r["base"]], lz)
            radius = strike_radius_km(r)
            if radius is not None and km > radius:
                continue
            threats = corridor_threats(state, [(state["airbases"][r["base"]], lz)], foe, tdef.get("low_alt_m_agl"))
            if len(threats) > tdef.get("max_threats", 1):
                continue
            key = (tasked.get(r["id"], 0), km)
            if best is None or key < best[0]:
                best = (key, r, need, threats)
        if best is None:
            continue
        (_n, km), perf, need, threats = best
        s = tdef["strike"]
        groups = []
        for k in range(0, need, GROUP_MAX):
            groups.append({"group": "strike" if not k else f"lift{k // GROUP_MAX + 1}",
                           "title": s["title"] + (f" ({k // GROUP_MAX + 1})" if k else ""), "performer": perf["id"],
                           "size": min(GROUP_MAX, need - k), "base": perf["base"], "route": [lz],
                           "objective": {"kind": "air_evac", "unit": u["id"], "place": place, "pos": lz},
                           "maintask": s["maintask"], "loadout": [], "lead_min": -k // GROUP_MAX, "ai": {},
                           "alt_m": tdef["transit_alt_m_agl"]})
        tasked[perf["id"]] = tasked.get(perf["id"], 0) + 1
        out.append({"kind": kind, "side": side, "title": f"{tdef['title']}: {u['name']} - {place}",
                    "performer": perf["id"], "target": u["id"], "group_size": need, "base": perf["base"],
                    "target_pos": lz, "ip": lz, "distance_km": round(km, 1), "threats": threats, "package": groups,
                    "package_notes": f"рота {model.strength(u):.0%}, в тылу противника с суток {u.get('airhead_day', '?')}; "
                                     f"{need} x {perf['type']} ({assault.troops(perf['type'])} человек на борт)"})
    return out


def refresh(state: dict, task: dict) -> list[str]:
    """Цель задачи - на её место сейчас (после шага наземной модели к времени миссии): точка цели, ИПМ и маршруты
    групп по цели (удар, прикрытие, доразведка). Рубежи подавления ПВО пересчитывает сборка (build). Цель выбыла
    (уничтожена, ушла в тыл) - строка-замечание, маршрут прежний."""
    units = state["units"]
    tdef = model.doctrine(state, task["side"])["tasks"][task["kind"]]
    obj0 = task["package"][0]["objective"]
    tgt = units.get(obj0.get("unit") or "")
    if not tgt or obj0["kind"] not in ("column", "site", "point", "cap_zone"):
        return []
    if tgt.get("state") in ("destroyed", "lost"):
        return [f"{task['title']}: цель выбыла к времени вылета."]
    tpos = model.unit_pos(state, tgt)
    if model.dist_km(tpos, task["target_pos"]) < 0.2:
        return []
    moved = model.dist_km(tpos, task["target_pos"])
    task["target_pos"] = tpos
    for g in task["package"]:
        o = g["objective"]
        base = state["airbases"][g["base"]]
        if o["kind"] in ("column", "site", "point"):
            ip = ip_point(base, tpos, tdef["ip_offset_km"])
            g["route"] = [ip, tpos]
            if g["group"] == "strike":
                task["ip"] = ip
        elif o["kind"] in ("cover_zone", "cap_zone"):
            g["route"] = [tpos]
        elif o["kind"] in ("search_zone", "flyover"):
            g["route"] = [ip_point(base, tpos, tdef["ip_offset_km"]), tpos]
        else:
            continue
        o["pos"] = tpos
    return [f"{task['title']}: цель сместилась на {moved:.0f} км к времени вылета - маршрут пересчитан."]


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
    elif model.category(tgt) == "sam":           # позиция ЗРК: атака группы на позиции
        route, objective = [ip, tpos], {"kind": "site", "unit": tgt["id"], "pos": tpos}
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

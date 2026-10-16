"""Материализация: какие части модели и в каком объёме появляются в миссии.

Окно вокруг вылета:
  1. район задачи - цель разворачивается кусками части по шаблону построения для её состояния;
  2. коридор маршрута - ЗРК, которые могут достать маршрут (planner.corridor_threats);
  3. остальное - не появляется.

Правило сохранения: развёрнутая машина несёт вес = (исправные машины этого типа в модели) / (развёрнуто этого типа).
Уничтожили машину весом 1.4 - модель теряет 1.4 машины. Так дебриф честен при любой плотности.
"""
from __future__ import annotations

import math

from . import model, planner


MAX_WEIGHT = 3.0        # ОЦЕНКА: одна машина в миссии - не больше стольких машин модели (иначе одно попадание слишком "дорого")
FAR_DENSITY = 0.35      # ОЦЕНКА: плотность частей вдали от района игрока (от бюджета колонны)
# Весь фронт в миссии (театр всей карты - десятки дивизий и бригад): число машин группы ограничено, а машина не
# "дороже" MAX_WEIGHT машин модели - поэтому большая часть показана в миссии частично (её передовая часть), остальное
# в миссии не появляется и в ней не гибнет. Все пороги - ОЦЕНКИ (нагрузка на DCS).
CAP_NEAR = 60           # машин в группе в районе задачи
CAP_MID = 24            # машин в группе ближе DETAIL_KM к цели
CAP_TOKEN = 4           # машин в группе дальше DETAIL_KM - присутствие на фронте, а не бой
CAP_AD_NEAR, CAP_AD_FAR = 8, 2   # приданная ПВО
DETAIL_KM = 60
CONVOY_KM = 40          # ОЦЕНКА: колонны снабжения в миссии - на участках ближе стольких км к цели
SAM_KM = 250            # ЗРК дальше от цели в миссию не ставятся
SAM_KM_ROLE = {"sam_short": 100}   # ПВО объекта (ближний ярус) - только ближе (ОЦЕНКА: нагрузка на DCS, по маршруту - window)


def _allocate(alive: dict[str, float], n: int) -> dict[str, int]:
    """Разбить n машин по типам пропорционально исправным (метод наибольшего остатка); тип с хотя бы 0.5 машины получает >= 1."""
    tot = sum(alive.values())
    if tot <= 0 or n <= 0:
        return {t: 0 for t in alive}
    raw = {t: a / tot * n for t, a in alive.items()}
    out = {t: int(math.floor(v)) for t, v in raw.items()}
    for t in sorted(raw, key=lambda t: raw[t] - out[t], reverse=True):
        if sum(out.values()) >= n:
            break
        out[t] += 1
    for t, a in alive.items():
        if a >= 0.5 and out[t] == 0:
            out[t] = 1
    return out


def _deploy(state: dict, alive: dict[str, float], density: float, cap: int | None) -> tuple[dict[str, int], dict[str, float]]:
    """Сколько машин каждого типа поставить и какой у машины вес. Без ограничения - как раньше: бюджет колонны, но не
    меньше alive / MAX_WEIGHT машин, вес = исправные / поставленные. С ограничением cap машин - показана доля части
    (share), вес машины - не больше MAX_WEIGHT."""
    n_alive = sum(alive.values())
    budget = max(1, int(round(state["settings"]["column_budget_units"] * density)), math.ceil(n_alive / MAX_WEIGHT))
    n = min(int(round(n_alive)), budget, cap if cap is not None else CAP_NEAR)
    counts = _allocate(alive, n)
    if n_alive <= 0 or sum(counts.values()) * MAX_WEIGHT >= n_alive:      # ограничение не мешает - как раньше
        return counts, {t: alive[t] / c for t, c in counts.items() if c > 0}
    return counts, {t: min(alive[t] / c, MAX_WEIGHT) for t, c in counts.items() if c > 0}   # показана часть части


def _deploy_ad(alive: dict[str, float], cap: int | None) -> tuple[dict[str, int], dict[str, float]]:
    """Приданная ПВО: без ограничения - все исправные (как раньше), с ограничением - cap машин, вес по доле."""
    n_alive = sum(alive.values())
    if cap is None or round(n_alive) <= cap:
        counts = {t: int(round(a)) for t, a in alive.items()}
        return counts, {t: alive[t] / c for t, c in counts.items() if c > 0}
    counts = _allocate(alive, cap)
    return counts, {t: min(alive[t] / c, MAX_WEIGHT) for t, c in counts.items() if c > 0}


def _ad_cap(cap: int | None) -> int | None:
    return None if cap is None else (CAP_AD_FAR if cap <= CAP_TOKEN else CAP_AD_NEAR)


def column(state: dict, unit: dict, density: float = 1.0, cap: int | None = None) -> dict:
    """Колонна на марше. Порядок следования и дистанция - из пакета доктрины стороны, которой принадлежит часть
    (ОЦЕНКИ в data/doctrine/*.json, раздел march); бюджет машин - настройка кампании (settings.column_budget_units)."""
    march = model.doctrine(state, unit["side"])["march"]
    rank = {r: i for i, r in enumerate(march["order"])}
    alive = model.alive_by_type(unit)
    counts, weight = _deploy(state, alive, density, cap)
    ad_cap = _ad_cap(cap)
    roles = {c["type"]: c["role"] for c in unit["composition"]}
    order = sorted((t for t in counts if counts[t] > 0), key=lambda t: rank.get(roles[t], len(rank)))
    pts = model.route_points(state, unit)
    head_km = unit["progress_km"]
    spacing_km = march["spacing_m"] / 1000.0
    # разрыв за танками под приданную войсковую ПВО (она идёт отдельной группой, см. attached_column)
    gap = sum(sum(_deploy_ad(model.alive_by_type(a), ad_cap)[0].values()) for a in state["units"].values()
              if a.get("attached_to") == unit["id"] and a.get("state") != "destroyed")   # так же, как в attached_column
    vehicles, i, slot = [], 0, 0
    gap_done = gap == 0
    for t in order:
        if not gap_done and roles[t] != "MBT":
            slot += gap
            gap_done = True
        w = weight[t]
        for _ in range(counts[t]):
            km = head_km - slot * spacing_km
            p, _seg = model.point_at_km(pts, km)
            vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": t, "lat": p["lat"], "lon": p["lon"], "weight": w,  # без округления: иначе сумма весов != модели
                             "km": km})
            i += 1
            slot += 1
    # Путевые точки - оставшиеся пункты маршрута, спроецированные на его геометрию (с дорогами - точка на дороге),
    # а не каждая вершина ломаной: между ними DCS ведёт колонну по дорогам сам (OnRoad).
    length = model.route_length_km(pts)
    wps = [model.point_at_km(pts, k)[0] for _p, k in model.place_km(state, unit) if k > head_km + 0.05]
    if length > head_km + 0.05 and (not wps or model.dist_km(wps[-1], pts[-1]) > 0.05):
        wps.append(dict(pts[-1]))            # конец маршрута, если последний пункт не на самом конце дороги
    return {
        "unit": unit["id"], "side": unit["side"], "kind": "column", "name": unit["id"],
        "vehicles": vehicles,
        "waypoints": wps,
        "speed_kmh": unit["march_kmh"],
        "ad_cap": ad_cap,
    }


def threat_axis_deg(state: dict, unit: dict) -> float:
    """Куда развёрнута позиция ЗРК: heading_deg из состава сил, иначе пеленг на ближайший аэродром противника
    (ОЦЕНКА: откуда придут самолёты). Важно для секторных РЛС и пусковых: развёрнутые не туда, они цель не видят."""
    if unit.get("heading_deg") is not None:
        return float(unit["heading_deg"])
    foe = model.enemy(unit["side"])
    bases = [b for b in state["airbases"].values() if b.get("side") == foe and b.get("kind") != "farp"]   # самолёты - с аэродромов
    if not bases:
        return 0.0
    pos = model.unit_pos(state, unit)
    near = min(bases, key=lambda b: model.dist_km(pos, b))
    return model.bearing_deg(pos, near)


def sam_site(state: dict, unit: dict) -> dict:
    """Шаблон позиции ЗРК: РЛС в центре, пункт управления рядом, пусковые по кругу (ОЦЕНКА: расстояния условные).
    Все машины развёрнуты на ось угрозы (threat_axis_deg)."""
    c = model.unit_pos(state, unit)
    axis = threat_axis_deg(state, unit)
    k = math.cos(math.radians(c["lat"]))
    def off(dx_m, dy_m):
        return {"lat": c["lat"] + dy_m / 111_320.0, "lon": c["lon"] + dx_m / (111_320.0 * k)}
    alive = model.alive_by_type(unit)
    vehicles, i = [], 0
    for comp in unit["composition"]:
        n = int(round(alive[comp["type"]]))
        for j in range(n):
            if comp["role"] == "radar":
                p = off(0, 0)
            elif comp["role"] == "launcher":
                a = 2 * math.pi * j / max(1, comp["count"])
                p = off(300 * math.cos(a), 300 * math.sin(a))
            else:
                p = off(80 + 20 * j, -60)
            vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": comp["type"], "lat": p["lat"], "lon": p["lon"],
                             "weight": 1.0, "heading": axis})
            i += 1
    return {"unit": unit["id"], "side": unit["side"], "kind": "sam_site", "name": unit["id"], "vehicles": vehicles, "waypoints": [], "speed_kmh": 0}


def gci_site(state: dict, unit: dict) -> dict:
    """КРУ (GCI): машина пункта на позиции; канал и радиус наведения - в группе (build ставит ActivateGCI)."""
    p = model.unit_pos(state, unit)
    vehicles = [{"name": f"{unit['id']}#{i + 1:02d}", "type": c["type"], "lat": p["lat"], "lon": p["lon"] + i * 0.0004,
                 "weight": 1.0} for i, c in enumerate(c for c in unit["composition"]
                                                      for _ in range(int(round(model.alive_by_type(unit)[c["type"]]))))]
    return {"unit": unit["id"], "side": unit["side"], "kind": "gci_site", "name": unit["id"], "vehicles": vehicles,
            "waypoints": [], "speed_kmh": 0, "channel": unit.get("channel", 1), "radius_km": unit.get("radius_km", 250),
            "core": True}                       # бюджет миссии КРУ не трогает: одна машина, нужна игроку


def attached_column(state: dict, unit: dict, parent_group: dict, cap: int | None = None) -> dict:
    """Приданная части группа (войсковая ПВО) - отдельной группой в той же колонне, сразу за танками части
    (ОЦЕНКА порядка следования). Отдельной - чтобы ограничение 'огонь только по наземным целям' не касалось ПВО.
    Веса - по правилу сохранения, как у колонны."""
    parent = state["units"][unit["attached_to"]]
    march = model.doctrine(state, parent["side"])["march"]
    spacing_km = march["spacing_m"] / 1000.0
    pts = model.route_points(state, parent)
    roles = {c["type"]: c["role"] for c in parent["composition"]}
    n_ahead = sum(1 for v in parent_group["vehicles"] if roles.get(v["type"]) == "MBT")
    start_km = parent["progress_km"] - n_ahead * spacing_km      # в разрыв, оставленный колонной за танками
    alive = model.alive_by_type(unit)
    counts, weight = _deploy_ad(alive, cap if cap is not None else parent_group.get("ad_cap"))
    vehicles, i = [], 0
    for comp in unit["composition"]:
        for _ in range(counts.get(comp["type"], 0)):
            km = start_km - i * spacing_km
            p, _seg = model.point_at_km(pts, km)
            vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": comp["type"], "lat": p["lat"], "lon": p["lon"],
                             "weight": weight[comp["type"]], "km": km})
            i += 1
    return {"unit": unit["id"], "side": unit["side"], "kind": "column", "name": unit["id"], "vehicles": vehicles,
            "waypoints": parent_group["waypoints"], "speed_kmh": parent_group["speed_kmh"], "route_owner": parent["id"]}


OTHER_DENSITY = 0.5     # ОЦЕНКА: доля бюджета для остальных частей боя, кроме цели
ATTACK_KMH = 15         # ОЦЕНКА: скорость наступающего боевого порядка
ATTACK_STANDOFF_KM = 1.2  # ОЦЕНКА: наступающий останавливается в стольких км от линии противника - в дальности огня
LINE_SPACING_M = 80     # ОЦЕНКА: интервал машин в боевом порядке
LINE_ROW_M = 150        # ОЦЕНКА: дистанция между линиями
LINE_WIDTH = 10         # ОЦЕНКА: машин в линии
AD_BEHIND_M = 800       # ОЦЕНКА: войсковая ПВО за боевым порядком


def battle_line(state: dict, unit: dict, density: float = 1.0, cap: int | None = None) -> list[dict]:
    """Часть в бою: боевой порядок линиями фронтом к противнику (танки впереди), в line_offset_km (ОЦЕНКА, раздел sim
    доктрины) от середины между ней и противником - так стороны в миссии стоят в дальности огня и ведут бой.
    Приданная ПВО - отдельной группой позади. Число машин - по бюджету колонны, веса - по правилу сохранения."""
    units = state["units"]
    sim = model.doctrine(state, unit["side"])["sim"]
    march = model.doctrine(state, unit["side"])["march"]
    own = model.unit_pos(state, unit)
    foes = [units[f] for f in unit.get("engaged", []) if f in units] or []
    if foes:
        fp = [model.unit_pos(state, f) for f in foes]
        enemy = {"lat": sum(p["lat"] for p in fp) / len(fp), "lon": sum(p["lon"] for p in fp) / len(fp)}
        axis = model.bearing_deg(own, enemy)
        mid = model.lerp(own, enemy, 0.5)
        center = model.offset(mid, axis, -sim.get("line_offset_km", 1.5) * 1000)
    else:
        axis, center = 0.0, own
    alive = model.alive_by_type(unit)
    counts, weight = _deploy(state, alive, density, cap)
    rank = {r: i for i, r in enumerate(march["order"])}
    roles = {c["type"]: c["role"] for c in unit["composition"]}
    order = sorted((t for t in counts if counts[t] > 0), key=lambda t: rank.get(roles[t], len(rank)))
    vehicles, i = [], 0
    for t in order:
        w = weight[t]
        for _ in range(counts[t]):
            row, col_ = divmod(i, LINE_WIDTH)
            p = model.offset(center, axis, -row * LINE_ROW_M, (col_ - (LINE_WIDTH - 1) / 2) * LINE_SPACING_M)
            vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": t, "lat": p["lat"], "lon": p["lon"], "weight": w, "heading": axis})
            i += 1
    # Наступающий (не обороняющийся) идёт развёрнутым строем на позицию противника - иначе в DCS линии стоят в 3 км
    # и не стреляют (camp4, день 2: ни одной потери в танках за 16 мин; рельеф и застройка закрывают видимость).
    wps, spd = [], 0
    attack = bool(foes) and not unit.get("defending")
    if attack:                                   # выход на рубеж огня перед линией противника
        wps = [model.offset(mid, axis, (sim.get("line_offset_km", 1.5) - ATTACK_STANDOFF_KM) * 1000)]
        spd = ATTACK_KMH
    out = [{"unit": unit["id"], "side": unit["side"], "kind": "battle", "name": unit["id"], "vehicles": vehicles,
            "waypoints": wps, "speed_kmh": spd, "formation": "line", "attack": attack, "center": center,
            "engaged": [f["id"] for f in foes]}]
    for a in units.values():
        if a.get("attached_to") != unit["id"] or a["state"] == "destroyed":
            continue
        av = []
        a_counts, a_weight = _deploy_ad(model.alive_by_type(a), _ad_cap(cap))
        for comp in a["composition"]:
            for _ in range(a_counts.get(comp["type"], 0)):
                k = len(av)
                p = model.offset(center, axis, -AD_BEHIND_M, (k - 1.5) * 200)
                av.append({"name": f"{a['id']}#{k + 1:02d}", "type": comp["type"], "lat": p["lat"], "lon": p["lon"],
                           "weight": a_weight[comp["type"]], "heading": axis})
        out.append({"unit": a["id"], "side": a["side"], "kind": "sam_site", "name": a["id"], "vehicles": av, "waypoints": [], "speed_kmh": 0,
                    "battle": True})                 # ПВО части в бою - сдвигается вместе с местом боя (cluster)
    return out


def airhead(state: dict, unit: dict, pos: dict, density: float = 1.0) -> dict:
    """Десант на площадке: пехота кругом в AIRHEAD_R_M от точки посадки; в миссии - с поздней активацией (выходит
    из вертолётов при посадке, lua/assault.lua). Веса - по правилу сохранения."""
    counts, weight = _deploy(state, model.alive_by_type(unit), density, CAP_NEAR)
    vehicles = []
    n = sum(counts.values())
    for t, c in counts.items():
        for _ in range(c):
            k = len(vehicles)
            p = model.offset(pos, 360.0 * k / max(1, n), AIRHEAD_R_M)
            vehicles.append({"name": f"{unit['id']}#{k + 1:02d}", "type": t, "lat": p["lat"], "lon": p["lon"],
                             "weight": weight[t], "heading": 360.0 * k / max(1, n)})
    return {"unit": unit["id"], "side": unit["side"], "kind": "airhead", "name": unit["id"], "vehicles": vehicles,
            "waypoints": [], "speed_kmh": 0, "late": True}


AIRHEAD_R_M = 60        # ОЦЕНКА: радиус, в котором пехота стоит после высадки


def downed_group(state: dict, d: dict) -> dict:
    """Сбитый экипаж на земле (csar.py): одна фигура пехотинца стороны у точки катапультирования; в манифест
    наземных частей не входит (это не часть модели) - его спасение пишет lua/csar.lua."""
    from . import csar
    return {"unit": d["id"], "side": d["side"], "kind": "downed", "name": d["id"], "waypoints": [], "speed_kmh": 0,
            "vehicles": [{"name": f"{d['id']}#01", "type": csar.PILOT_FIGURE[d["side"]], "lat": d["pos"]["lat"],
                          "lon": d["pos"]["lon"], "weight": 0.0}]}


def window(state: dict, task: dict, density: float = 1.0) -> list[dict]:
    units = state["units"]
    obj = (task.get("package") or [{}])[0].get("objective") or {}
    if task.get("target_kind") == "convoy":      # удар по пути подвоза: колонна на участке, ЗРК коридора
        from . import convoys
        side = model.enemy(task["side"])
        groups = [convoys.group(state, side, task["link"], convoys.link_flows(state, side).get(task["link"], 0.0), density)]
        groups += [sam_site(state, units[sid]) for sid in task["threats"] if not units[sid].get("attached_to")]
        groups += [sam_site(state, units[sid]) for sid in background_sams(state, task)]
        return [g for g in groups if g["vehicles"]]
    if obj.get("kind") == "csar":                # поиск и спасение: экипаж на земле, ЗРК коридора
        d = next((x for x in state.get("downed", []) if x["id"] == obj["downed"]), None)
        groups = [downed_group(state, d)] if d else []
        groups += [sam_site(state, units[sid]) for sid in task["threats"] if not units[sid].get("attached_to")]
        groups += [sam_site(state, units[sid]) for sid in background_sams(state, task)]
        return [g for g in groups if g["vehicles"]]
    target = units[task["target"]]
    if obj.get("kind") == "air_assault":         # десант: рота на площадке (появится при посадке), ЗРК коридора
        groups = [airhead(state, target, obj["pos"], density)]
        groups += [sam_site(state, units[sid]) for sid in task["threats"] if not units[sid].get("attached_to")]
        groups += [sam_site(state, units[sid]) for sid in background_sams(state, task)]
        return [g for g in groups if g["vehicles"]]
    if obj.get("kind") == "air_evac":            # эвакуация: рота у площадки (ждёт вертолёты), ЗРК коридора
        ev = airhead(state, target, obj["pos"], density)
        ev.update(kind="evac", late=False)
        groups = [ev]
        groups += [sam_site(state, units[sid]) for sid in task["threats"] if not units[sid].get("attached_to")]
        groups += [sam_site(state, units[sid]) for sid in background_sams(state, task)]
        return [g for g in groups if g["vehicles"]]
    if model.category(target) in ("depot", "bridge", "airfield", "factory", "sam"):   # объект тыла - сам в миссии как объекты карты
        groups = [sam_site(state, target)] if model.category(target) == "sam" else []   # позиция ЗРК - сама цель
        placed = set()
        for sid in task["threats"]:
            if sid == target["id"] or sid in placed:
                continue
            parent = units.get(units[sid].get("attached_to") or "")
            if parent and parent["id"] in placed:
                continue
            if parent and parent["state"] == "march":
                col = column(state, parent, density * OTHER_DENSITY)
                groups += [col, attached_column(state, units[sid], col)]
                placed |= {parent["id"], sid}
            elif parent:                         # часть на месте (оборона, бой) - позицией, её ПВО - с ней (цель подавления ПВО)
                cl = battle_cluster(state, parent["id"]) if parent["state"] == "battle" else [parent["id"]]
                for uid in cl:
                    if uid not in placed:
                        part = _tag(battle_line(state, units[uid], density * OTHER_DENSITY), cl)
                        groups += part
                        placed |= {g_["unit"] for g_ in part}
            else:
                groups.append(sam_site(state, units[sid]))
        for sid in background_sams(state, task):
            groups.append(sam_site(state, units[sid]))
        return [g for g in groups if g["vehicles"]]
    if target["state"] == "battle":              # войска в соприкосновении: весь бой (все связанные соприкосновением части)
        cluster = battle_cluster(state, target["id"])
        groups = []
        for uid in cluster:                      # цель - полным бюджетом, остальные - половиной (ОЦЕНКА: нагрузка на DCS)
            groups += _tag(battle_line(state, units[uid], density if uid == target["id"] else density * OTHER_DENSITY), cluster)
        placed = {g["unit"] for g in groups}
        for sid in task["threats"]:              # угрозы коридора, ещё не стоящие в бою
            if sid in placed:
                continue
            parent = units.get(units[sid].get("attached_to") or "")
            if parent and parent["state"] == "march" and parent["id"] not in placed:   # ПВО части на марше - вместе с колонной
                col = column(state, parent, density * OTHER_DENSITY)
                groups += [col, attached_column(state, units[sid], col)]
                placed |= {parent["id"], sid}
            else:
                groups.append(sam_site(state, units[sid]))
        for sid in background_sams(state, task):
            groups.append(sam_site(state, units[sid]))
        return [g for g in groups if g["vehicles"]]
    col = column(state, target, density)
    groups = [col]
    attached = [u for u in units.values() if u.get("attached_to") == target["id"] and u["state"] != "destroyed"]
    for u in attached:                           # приданная войсковая ПВО всегда идёт с колонной
        groups.append(attached_column(state, u, col))
    for sid in task["threats"]:
        if units[sid].get("attached_to") == target["id"]:   # приданная цели ПВО уже идёт с колонной
            continue
        groups.append(sam_site(state, units[sid]))
    for sid in background_sams(state, task):     # пузырь: ЗРК вокруг маршрутов, даже если до них не достают
        groups.append(sam_site(state, units[sid]))
    return [g for g in groups if g["vehicles"]]


def battle_cluster(state: dict, uid: str) -> list[str]:
    """Части, связанные соприкосновением с uid (один бой)."""
    units = state["units"]
    cluster, todo = [], [uid]
    while todo:
        x = todo.pop()
        if x in cluster or units[x]["state"] != "battle":
            continue
        cluster.append(x)
        todo += units[x].get("engaged", [])
    return sorted(cluster)


def cluster_key(ids: list[str]) -> str:
    return "+".join(sorted(ids))


def _tag(groups: list[dict], cluster: list[str]) -> list[dict]:
    for g in groups:
        g["cluster"] = cluster_key(cluster)      # бой (место боя по местности - одно на кластер)
    return groups


def theatre(state: dict, task: dict, density: float = 1.0) -> list[dict]:
    """Весь театр в миссии. Район задачи игрока - подробно (window); всё остальное - с плотностью FAR_DENSITY
    (ОЦЕНКА): бои - боевыми порядками, колонны на марше - на дорогах, части в обороне и в тылу - позициями,
    ЗРК - полностью. Веса - по правилу сохранения, машина не "дороже" MAX_WEIGHT машин модели."""
    units = state["units"]
    groups = window(state, task, density)
    for g in groups:
        g["core"] = True                         # окно задачи игрока - бюджет миссии его не трогает
    placed = {g["unit"] for g in groups}
    far = density * FAR_DENSITY
    center = task.get("target_pos") or model.unit_pos(state, units[task["target"]])
    def cap_of(u):                               # ближе DETAIL_KM - частью, дальше - знаком присутствия (ОЦЕНКИ)
        return CAP_MID if model.dist_km(model.unit_pos(state, u), center) <= DETAIL_KM else CAP_TOKEN
    for u in list(units.values()):
        if (model.category(u) != "ground" or "route" not in u or u["id"] in placed
                or u["state"] in ("destroyed", "pending") or model.strength(u) <= 0):
            continue
        if u["state"] == "battle":
            cl = battle_cluster(state, u["id"])
            for uid in cl:
                if uid not in placed:
                    groups += _tag(battle_line(state, units[uid], far, cap_of(units[uid])), cl)
            placed |= set(cl)
        elif u["state"] == "march":
            col = column(state, u, far, cap_of(u))
            groups.append(col)
            for a in units.values():
                if a.get("attached_to") == u["id"] and a["state"] != "destroyed":
                    groups.append(attached_column(state, a, col))
            placed.add(u["id"])
        else:                                    # оборона, тыл, небоеспособна - позиция у пункта
            groups += _tag(battle_line(state, u, far, cap_of(u)), [u["id"]])
            placed.add(u["id"])
    placed |= {g["unit"] for g in groups}
    for u in units.values():                     # ЗРК - полностью, но не дальше SAM_KM (по роли - SAM_KM_ROLE) от цели
        if (model.category(u) == "sam" and u["id"] not in placed and not u.get("attached_to")
                and u["state"] not in ("destroyed", "pending") and model.strength(u) > 0
                and model.dist_km(model.unit_pos(state, u), center) <= SAM_KM_ROLE.get(u["role"], SAM_KM)):
            groups.append(sam_site(state, u))
    from . import convoys                        # колонны снабжения на участках с потоком рядом (обе стороны)
    for side, link, t in convoys.near(state, center, CONVOY_KM):
        if convoys.convoy_id(side, link) not in placed:
            groups.append(convoys.group(state, side, link, t, far))
    for d in state.get("downed", []):           # сбитые экипажи обеих сторон рядом - их можно спасти (или перехватить спасателей)
        if d["id"] not in placed and model.dist_km(d["pos"], center) <= DETAIL_KM:
            groups.append({**downed_group(state, d), "core": True})   # одна фигура - бюджет её не трогает
    for u in units.values():                     # КРУ - все исправные (по одной машине; наведение - на 250 км)
        if model.category(u) == "gci" and u["state"] not in ("destroyed", "pending") and model.strength(u) > 0:
            groups.append(gci_site(state, u))
    groups = [g for g in groups if g["vehicles"]]
    budget = (state.get("settings") or {}).get("mission_budget", MISSION_BUDGET)
    return apply_budget(state, task, groups, budget)


MISSION_BUDGET = 600    # ОЦЕНКА: наземных машин в миссии по умолчанию (settings.mission_budget, build --budget)
BUDGET_MIN_KEEP = 2     # ОЦЕНКА: меньше машин в группе при прореживании не оставлять (иначе - убрать группу)


def _relevance_km(state: dict, task: dict, g: dict) -> float:
    """Удаление группы от того, что видит игрок: маршрутов групп пакета (от базы) и объекта задачи, км."""
    vs = g["vehicles"]
    c = {"lat": sum(v["lat"] for v in vs) / len(vs), "lon": sum(v["lon"] for v in vs) / len(vs)}
    legs = []
    for pg in task.get("package") or []:
        pts = [state["airbases"][pg["base"]]] + list(pg["route"])
        legs += list(zip(pts, pts[1:]))
    tpos = task.get("target_pos")
    d = model.dist_km(c, tpos) if tpos else float("inf")
    return min([d] + [planner._seg_dist_km(c, a, b) for a, b in legs])


def _thin(g: dict, keep: int) -> int:
    """Оставить в группе keep машин, пропорционально по типам; вес оставшихся растёт (правило сохранения), но не выше
    MAX_WEIGHT - остаток части в этой миссии не появляется (как у частей вдали). Возвращает, сколько машин убрано."""
    vs = g["vehicles"]
    if keep >= len(vs):
        return 0
    by_type: dict[str, list[dict]] = {}
    for v in vs:
        by_type.setdefault(v["type"], []).append(v)
    alive = {t: sum(v["weight"] for v in lst) for t, lst in by_type.items()}
    counts = _allocate(alive, keep)
    kept = []
    for t, lst in by_type.items():
        k = min(counts.get(t, 0), len(lst))
        if k <= 0:
            continue
        step = len(lst) / k                      # равномерно по строю/колонне: голова, середина, хвост
        chosen = [lst[int(i * step)] for i in range(k)]
        w = min(alive[t] / k, MAX_WEIGHT)
        for v in chosen:
            v["weight"] = w
        kept += chosen
    order = {id(v): i for i, v in enumerate(vs)}
    g["vehicles"] = sorted(kept, key=lambda v: order[id(v)])
    return len(vs) - len(g["vehicles"])


def apply_budget(state: dict, task: dict, groups: list[dict], budget: int | None) -> list[dict]:
    """Бюджет миссии: не больше budget наземных машин. Окно задачи игрока (core) не трогается; остальное - по
    удалённости от маршрутов пакета и объекта, дальние первыми: 1) колонны и боевые порядки прореживаются (меньше
    машин, вес больше - до MAX_WEIGHT); 2) если мало - дальние группы убираются целиком (бой - весь кластер, колонна -
    с приданной ПВО, ЗРК - позицией). Убранное живёт в модели, в этой миссии его нет. Все пороги - ОЦЕНКИ."""
    total = sum(len(g["vehicles"]) for g in groups)
    if not budget or total <= budget:
        return groups
    rel = {id(g): _relevance_km(state, task, g) for g in groups}
    free = sorted((g for g in groups if not g.get("core")), key=lambda g: -rel[id(g)])
    # 1. прореживание: дальние колонны и бои - до половины, затем до BUDGET_MIN_KEEP
    for frac in (0.5, 0.0):
        for g in free:
            if total <= budget:
                break
            if g["kind"] not in ("column", "battle"):
                continue
            keep = max(BUDGET_MIN_KEEP, int(len(g["vehicles"]) * frac))
            total -= _thin(g, keep)
    if total <= budget:
        return groups
    # 2. дальние группы целиком: связанные - вместе (бой - кластер, колонна - с приданной ПВО)
    def bundle_key(g):
        return g.get("cluster") or g.get("route_owner") or g["unit"]
    bundles: dict[str, list[dict]] = {}
    for g in groups:
        bundles.setdefault(bundle_key(g), []).append(g)
    drop = set()
    for g in free:
        if total <= budget:
            break
        b = bundles[bundle_key(g)]
        if any(x.get("core") for x in b) or id(g) in drop:
            continue
        for x in b:
            if id(x) not in drop:
                drop.add(id(x))
                total -= len(x["vehicles"])
    return [g for g in groups if id(g) not in drop]


def background_sams(state: dict, task: dict) -> list[str]:
    """ЗРК противника не дальше settings.bubble_km (ОЦЕНКА) от маршрута любой группы пакета (база - точки маршрута),
    кроме угроз коридора (они уже в окне) и приданных частям. В миссии они есть - стреляют, светятся на СПО, -
    но группа подавления на них не назначается: до маршрута ударной группы они не достают."""
    bubble = state["settings"].get("bubble_km", model.BUBBLE_KM)    # кампании до пузыря - значение по умолчанию
    legs = []
    for g in task.get("package") or []:
        pts = [state["airbases"][g["base"]]] + list(g["route"])
        legs += list(zip(pts, pts[1:]))
    foe = model.enemy(task["side"])
    out = []
    for u in state["units"].values():
        if (u["side"] != foe or model.category(u) != "sam" or u.get("attached_to") or u["id"] in task["threats"]
                or u["state"] == "destroyed" or model.strength(u) <= 0):
            continue
        pos = model.unit_pos(state, u)
        if any(planner._seg_dist_km(pos, a, b) <= bubble for a, b in legs):
            out.append(u["id"])
    return out

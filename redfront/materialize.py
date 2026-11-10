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
SAM_FULL_KM = 150       # ОЦЕНКА: ЗРК ближе - позицией целиком; дальше (до SAM_KM) - знаком: РЛС и SAM_TOKEN_LN пусковых
SAM_TOKEN_LN = 2        # (в сети ПВО и на СПО они есть, а нагрузка на DCS меньше; веса пусковых - по правилу сохранения)
# Войсковая ПВО частей вдали (дальше DETAIL_KM от цели, не в бою) в миссию не ставится: колонна в тылу - без ПВО.
# Машин с РЛС (ЗСУ, ЗРК с РЛС) в приданной ПВО не больше AD_RADAR_MAX - остальное место - ПЗРК/ЗРК с оптикой, пушки
# (ОЦЕНКА: нагрузка на DCS - РЛС опрашивают цели постоянно; в окне задачи - все, как раньше).
AD_RADAR_MAX = 2
AD_RADAR_TYPES = {"Gepard", "ZSU_23_4_Shilka", "X_2S6_Tunguska", "Osa_9A33_ln", "Roland_ADS", "Roland_Radar",
                  "Rapier_fsa_blindfire_radar", "SON_9", "Kub_1S91_str", "Tor 9A331", "M6 Linebacker"}
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
    """Приданная ПВО: без ограничения - все исправные (как раньше), с ограничением - cap машин (из них с РЛС - не
    больше AD_RADAR_MAX), вес по доле."""
    n_alive = sum(alive.values())
    radar = {t: a for t, a in alive.items() if t in AD_RADAR_TYPES}
    other = {t: a for t, a in alive.items() if t not in AD_RADAR_TYPES}
    if cap is None or (round(n_alive) <= cap and round(sum(radar.values())) <= AD_RADAR_MAX):
        counts = {t: int(round(a)) for t, a in alive.items()}
        return counts, {t: alive[t] / c for t, c in counts.items() if c > 0}
    n_r = min(int(round(sum(radar.values()))), AD_RADAR_MAX, cap)    # с РЛС - не больше AD_RADAR_MAX
    n_o = min(int(round(sum(other.values()))), cap - n_r)
    counts = {**_allocate(radar, n_r), **_allocate(other, n_o)}
    return counts, {t: min(alive[t] / c, MAX_WEIGHT) for t, c in counts.items() if c > 0}


def _ad_cap(cap: int | None) -> int | None:
    return None if cap is None else (CAP_AD_FAR if cap <= CAP_TOKEN else CAP_AD_NEAR)


def _ad_share(ad: dict, parent: dict, shown: int, cap: int | None) -> int | None:
    """Приданная ПВО - той же долей, что показана часть (иначе в бою видна почти одна ПВО: часть - 60 машин из 300,
    ПВО - вся); не меньше BUDGET_MIN_KEEP, не больше cap."""
    alive = sum(model.alive_by_type(parent).values())
    if alive <= 0:
        return cap
    ad_alive = sum(model.alive_by_type(ad).values())
    n = max(BUDGET_MIN_KEEP, math.ceil(ad_alive * shown / alive))
    if cap is None and n >= round(ad_alive):
        return None                              # часть показана целиком - и ПВО целиком (окно задачи, как раньше)
    return n if cap is None else min(cap, n)


def column(state: dict, unit: dict, density: float = 1.0, cap: int | None = None) -> dict:
    """Колонна на марше. Порядок следования и дистанция - из пакета доктрины стороны, которой принадлежит часть
    (ОЦЕНКИ в data/doctrine/*.json, раздел march); бюджет машин - настройка кампании (settings.column_budget_units)."""
    march = model.doctrine(state, unit["side"])["march"]
    rank = {r: i for i, r in enumerate(march["order"])}
    alive = model.alive_by_type(unit)
    roles = {c["type"]: c["role"] for c in unit["composition"]}
    # пехота на марше - в машинах (БМП, БТР, грузовики): в колонну не ставится - медленная и съедает бюджет машин;
    # пешая часть без техники (десант, пехота ДРВ) - как есть
    riding = {t: a for t, a in alive.items() if roles.get(t) != "infantry"}
    if riding:
        alive = riding
    counts, weight = _deploy(state, alive, density, cap)
    ad_cap = _ad_cap(cap)
    order = sorted((t for t in counts if counts[t] > 0), key=lambda t: rank.get(roles[t], len(rank)))
    pts = model.route_points(state, unit)
    head_km = unit["progress_km"]
    spacing_km = march["spacing_m"] / 1000.0
    # разрыв за танками под приданную войсковую ПВО (она идёт отдельной группой, см. attached_column)
    shown = sum(counts.values())
    gap = sum(sum(_deploy_ad(model.alive_by_type(a), _ad_share(a, unit, shown, ad_cap))[0].values())
              for a in state["units"].values()
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


# Расстановка пусковых вокруг РЛС наведения по системе: (радиус, м; сектор, град.; центр сектора: "ring" - круг,
# "front" - к оси угрозы, "rear" - от неё). ОЦЕНКИ по снимкам позиций и описаниям: С-75 - "звезда" из 6 обвалований,
# С-125 - 4 ПУ ближе к кабине, С-200 - ПУ полукругом у кабины, Куб - СПУ рассредоточены вокруг СОУ; HAWK - огневые
# взводы впереди РЛС; Patriot - ПУ веером позади РЛС (РЛС смотрит в сектор, ПУ до ~1 км от неё).
SITE_LAYOUT = {
    "S_75M_Volhov": (250, 360, "ring"), "5p73 s-125 ln": (150, 360, "ring"), "S_200_Launcher": (200, 180, "rear"),
    "Kub_2P25_ln": (400, 360, "ring"), "Hawk_ln": (250, 120, "front"), "Patriot_ln": (400, 140, "rear"),
}
# Геометрия по системе (ОЦЕНКИ по схемам и снимкам позиций): (вид, параметры). arc - пусковые дугой: радиус, сектор,
# центр сектора (ring - круг, front - к угрозе, rear - от неё); pairs - пары пусковых дугой (С-300П: ведущая 5П85С +
# ведомая 5П85Д, интервал пары); disp - машины рассредоточены кольцом от r1 до r2 в секторе (Бук: СОУ со своей РЛС -
# 2-5 км; самоходные ЗРК малой дальности - 0,5-1,5 км; ПЗРК - 0,8-2 км); hex - зенитная батарея шестиугольником.
SITE_LAYOUT_RX = [
    (r"S_75M_Volhov", ("arc", 250, 360, "ring")),                 # С-75 - 'звезда' из 6 обвалований
    (r"5p73", ("arc", 150, 360, "ring")),                         # С-125 - 4 ПУ ближе к кабине
    (r"S_200_Launcher", ("arc", 200, 180, "rear")),               # С-200 - ПУ полукругом у кабины
    (r"Kub_2P25", ("arc", 250, 180, "front")),                    # Куб - 4 СПУ дугой 200-300 м в переднем секторе
    (r"Hawk_ln", ("arc", 250, 120, "front")),                     # HAWK - огневые взводы впереди РЛС
    (r"Patriot_ln", ("arc", 400, 140, "rear")),                   # Patriot - ПУ веером позади РЛС
    (r"5P85", ("pairs", 200, 270, "rear", 35)),                   # С-300П - подкова пар СПУ 100-300 м вокруг КП и РПН
    (r"Buk.*LN|Buk_LN", ("disp", 2000, 4000, 200, "front")),     # Бук - СОУ со своей РЛС в 2-5 км друг от друга
    (r"S_60|S-60|KS_19|KS-19|M1939|Bofors|bofors|[Ff]lak", ("hex", 70)),   # зенитная батарея - 6 орудий шестиугольником
    (r"ZU-23|ZU_23", ("hex", 90)),                                # ЗУ-23 - парами вокруг объекта
    (r"manpad|Stinger|stinger|Igla|SA-18", ("disp", 800, 2000, 360, "ring")),
    (r"Osa|Roland|Gepard|Tor|Tunguska|Strela|Chaparral|ZSU_23_4|ZSU-23-4|Vulcan|rapier", ("disp", 500, 1500, 360, "ring")),
]
SITE_RADAR_GAP_M = 120   # ОЦЕНКА: РЛС позиции - не в одной точке (обнаружения - в стороне от наведения)


def site_layout(type_name: str, unit: dict) -> tuple:
    import re as _re
    for rx, lay in SITE_LAYOUT_RX:
        if _re.search(rx, type_name):
            return lay
    return ("arc", 300, 360, "ring")


def layout_point(lay: tuple, slot: float, full: int, rnd) -> tuple[float, float]:
    """Смещение машины (вперёд, вправо), м, по виду расстановки системы; slot - номер в штатном составе."""
    kind = lay[0]
    if kind == "hex":
        b = 2 * math.pi * slot / max(1, full)
        return lay[1] * math.cos(b), lay[1] * math.sin(b)
    if kind == "disp":                           # рассредоточение: равномерно по сектору, дальность - случайная в полосе
        r1, r2, arc, face = lay[1], lay[2], lay[3], lay[4]
        a = math.radians(-arc / 2 + arc * (slot + 0.5) / max(1, full)) + (math.pi if face == "rear" else 0.0)
        if arc >= 360:
            a = 2 * math.pi * (slot + rnd() * 0.5) / max(1, full)
        r = r1 + (r2 - r1) * rnd()
        return r * math.cos(a), r * math.sin(a)
    r, arc, face = lay[1], lay[2], lay[3]
    if kind == "pairs":                          # пары: центр пары на дуге, ведомая - в интервале от ведущей
        pair = int(slot // 2)
        n_pairs = max(1, (full + 1) // 2)
        b = math.radians(-arc / 2 + arc * (pair + 0.5) / n_pairs) + (math.pi if face == "rear" else 0.0)
        side = lay[4] if int(slot) % 2 else 0.0
        return r * math.cos(b) - side * math.sin(b), r * math.sin(b) + side * math.cos(b)
    if arc >= 360:
        b = 2 * math.pi * slot / max(1, full)
    else:
        b = math.radians(-arc / 2 + arc * (slot + 0.5) / max(1, full)) + (math.pi if face == "rear" else 0.0)
    return r * math.cos(b), r * math.sin(b)


def sam_site(state: dict, unit: dict, token: bool = False) -> dict:
    """Позиция ЗРК: РЛС в центре (каждая следующая - в SITE_RADAR_GAP_M в стороне), пункт управления рядом, пусковые -
    по SITE_LAYOUT системы (иначе - по кругу 300 м). Все машины развёрнуты на ось угрозы (threat_axis_deg).
    token - ЗРК вдали от задачи: РЛС и не больше SAM_TOKEN_LN пусковых, вес пусковой - не больше MAX_WEIGHT.
    Корабельная группа (угроза коридора) - не здесь: корабли в миссии - флотом (build.carrier_groups), группа пустая."""
    if model.category(unit) == "naval":
        return {"unit": unit["id"], "kind": "sam", "side": unit["side"], "vehicles": []}
    c = model.unit_pos(state, unit)
    cov = state["units"].get(unit.get("covers") or "")
    if unit.get("point") and cov and cov.get("pos"):   # ПВО объекта - кольцом вокруг самого объекта, а не сбоку от него
        c = dict(cov["pos"])
    axis = threat_axis_deg(state, unit)
    k = math.cos(math.radians(c["lat"]))
    def off(fwd_m, right_m):                     # смещение по оси угрозы: вперёд, вправо
        a = math.radians(axis)
        dx = fwd_m * math.sin(a) + right_m * math.cos(a)
        dy = fwd_m * math.cos(a) - right_m * math.sin(a)
        return {"lat": c["lat"] + dy / 111_320.0, "lon": c["lon"] + dx / (111_320.0 * k)}
    alive = model.alive_by_type(unit)
    r_ = model.rng(state, f"site-{unit['id']}")
    rnd = (lambda: r_.random()) if r_ else (lambda: 0.5)
    vehicles, i, n_radar, n_ctl = [], 0, 0, 0
    for comp in unit["composition"]:
        n = int(round(alive[comp["type"]]))
        if n <= 0:
            continue
        shown, w = n, 1.0
        if token and comp["role"] == "launcher" and n > SAM_TOKEN_LN:
            shown, w = SAM_TOKEN_LN, min(alive[comp["type"]] / SAM_TOKEN_LN, MAX_WEIGHT)   # остальное - не в миссии
        lay = site_layout(comp["type"], unit)
        full = max(comp.get("count", n), shown)
        for j in range(shown):
            if comp["role"] == "radar" and lay[0] not in ("disp",):
                p = off(0, n_radar * SITE_RADAR_GAP_M * (1 if n_radar % 2 else -1))
                n_radar += 1
            elif comp["role"] in ("launcher", "radar") or lay[0] == "disp":
                fwd, right = layout_point(lay, j * full / shown, full, rnd)
                p = off(fwd, right)
            else:
                p = off(-60, 80 + 20 * n_ctl)
                n_ctl += 1
            vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": comp["type"], "lat": p["lat"], "lon": p["lon"],
                             "weight": w, "heading": axis})
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


def ssm_site(state: dict, unit: dict) -> dict:
    """Пусковые ОТР (Скад, Точка, Искандер) на позиции: модель - по ракете части (мод - если включён)."""
    from . import strategic
    p = model.unit_pos(state, unit)
    m = strategic.MISSILES.get(unit.get("missile", "scud"), {})
    mods = set((state.get("settings") or {}).get("mods") or [])
    dcs_type = next((t for k, t in (m.get("mod_dcs") or {}).items() if k in mods), None)
    vehicles = []
    for c in unit["composition"]:
        for i in range(int(round(model.alive_by_type(unit)[c["type"]]))):
            t = dcs_type if (dcs_type and c.get("role") == "launcher") else c["type"]
            vehicles.append({"name": f"{unit['id']}#{len(vehicles) + 1:02d}", "type": t, "lat": p["lat"] + len(vehicles) * 0.0006,
                             "lon": p["lon"], "weight": 1.0})
    return {"unit": unit["id"], "side": unit["side"], "kind": "ssm_site", "name": unit["id"], "vehicles": vehicles,
            "waypoints": [], "speed_kmh": 0, "core": True}


def _on_foot(t: str) -> bool:
    """Пеший тип (расчёт ПЗРК, пехотинец) - на марше едет в машине, отдельно в колонне не ставится."""
    tl = t.lower()
    return "manpad" in tl or tl.startswith(("soldier", "infantry", "paratrooper")) or "stinger" in tl


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
    alive = {t: a for t, a in model.alive_by_type(unit).items() if not _on_foot(t)} or model.alive_by_type(unit)   # ПЗРК - в машинах
    counts, weight = _deploy_ad(alive, _ad_share(unit, parent, len(parent_group["vehicles"]),
                                                 cap if cap is not None else parent_group.get("ad_cap")))
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
AD_ECHELON = {   # глубина войсковой ПВО за боевым порядком по классу и школе, м (ОЦЕНКИ): ВД - Шилки при батальонах
    # первого эшелона 300-500 м, Стрела/Оса - 1,5-3 км; НАТО - Gepard при ротах 300 м, Roland/Chaparral - 2,5 км
    "wp": {"gun": 400, "manpad": 150, "sam": 2000},
    "nato": {"gun": 300, "manpad": 150, "sam": 2500},
}


def ad_class(t: str) -> str:
    import re as _re
    if _re.search(r"manpad|Stinger|stinger|Igla|SA-18", t):
        return "manpad"
    if _re.search(r"ZSU|Shilka|Gepard|Vulcan|ZU-23|ZU_23|S_60|S-60|KS|M163|Bofors|flak", t):
        return "gun"
    return "sam"


AD_SPREAD_M = 600       # ОЦЕНКА: интервал средств войсковой ПВО по фронту части
AD_BEHIND_M = 800       # ОЦЕНКА: войсковая ПВО за боевым порядком


ART_GUNS = 6            # ОЦЕНКА: орудий батареи в миссии (полк ОВД: дивизион 2С1 - 18; бригада НАТО: дивизион M109 - 18-24)
ART_BEHIND_M = 6000     # ОЦЕНКА: огневые позиции за боевым порядком (2С1 - до 15 км, M109 - до 18 км)
ART_TYPES = {"red": "SAU_Gvozdika", "blue": "M_109"}   # 2С1 "Гвоздика", M109


FIRES = {"missions": 4, "rounds": 24, "mrl": None}   # огонь по умолчанию (доктрина без раздела fires)


def fires(state: dict, side: str) -> dict:
    """Огневая поддержка стороны в бою - раздел fires доктрины (ОЦЕНКИ): налёты батареи (missions x rounds) и РСЗО."""
    return {**FIRES, **(model.doctrine(state, side).get("fires") or {})}


def mrl_ok(state: dict, unit: dict, mrl: dict | None) -> bool:
    """РСЗО у части: есть в доктрине, нация и год (nations: {нация: с какого года}; MLRS у армии США - с 1983)."""
    if not mrl:
        return False
    nat = mrl.get("nations")
    if not nat:
        return True
    from . import pilots
    n = pilots.nation(unit)
    return n in nat and (planner.campaign_year(state) or 9999) >= nat[n]


def artillery(state: dict, unit: dict, center: dict, axis: float, target: dict) -> list[dict]:
    """Артиллерия части в бою: батарея поддержки за боевым порядком, развёрнута к противнику, огонь - по линии
    противника; РСЗО (fires.mrl доктрины) - дальше в глубине, огонь по глубине (target depth: второй эшелон, резервы)
    или по артиллерии противника (counterbattery, build). FireAtPoint ставит build. Потери - у части (art_lost,
    mrl_lost), восстанавливаются по одной машине в сутки."""
    if model.category(unit) != "ground" or unit.get("role") == "air_assault":
        return []
    out = []
    n = max(0, ART_GUNS - int(unit.get("art_lost", 0)))
    t = ART_TYPES.get(unit["side"])
    fr = fires(state, unit["side"])
    if n and t:
        vs = []
        for k in range(n):
            p = model.offset(center, axis, -ART_BEHIND_M, (k - (n - 1) / 2) * 120)
            vs.append({"name": f"{unit['id']}@art#{k + 1:02d}", "type": t, "lat": p["lat"], "lon": p["lon"], "weight": 0.0,
                       "heading": axis})
        out.append({"unit": unit["id"], "side": unit["side"], "kind": "artillery", "name": f"{unit['id']} art", "vehicles": vs,
                    "waypoints": [], "speed_kmh": 0, "fire_at": dict(target), "missions": fr["missions"], "rounds": fr["rounds"]})
    mrl = fr.get("mrl")
    if mrl_ok(state, unit, mrl):
        m = max(0, int(mrl.get("n", 6)) - int(unit.get("mrl_lost", 0)))
        if m:
            vs = []
            for k in range(m):
                p = model.offset(center, axis, -mrl.get("behind_m", 9000), (k - (m - 1) / 2) * 150)
                vs.append({"name": f"{unit['id']}@mrl#{k + 1:02d}", "type": mrl["type"], "lat": p["lat"], "lon": p["lon"],
                           "weight": 0.0, "heading": axis})
            aim = model.offset(target, axis, mrl.get("depth_km", 3) * 1000) if mrl.get("target") == "depth" else dict(target)
            out.append({"unit": unit["id"], "side": unit["side"], "kind": "artillery", "mrl": True, "name": f"{unit['id']} mrl",
                        "vehicles": vs, "waypoints": [], "speed_kmh": 0, "fire_at": aim, "missions": int(mrl.get("missions", 1)),
                        "rounds": int(mrl.get("rounds", 120)), "target": mrl.get("target", "depth"),
                        "engaged": list(unit.get("engaged", []))})
    return out


def battle_line(state: dict, unit: dict, density: float = 1.0, cap: int | None = None, with_ad: bool = True) -> list[dict]:
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
    seq = [t for t in order for _ in range(counts[t])]
    # боевой порядок - по доктрине стороны (formations.py): роты, эшелоны, позиции; оборона или наступление
    from . import formations
    pkg = (state.get("doctrine") or {}).get(unit["side"], "")
    doc = model.doctrine(state, unit["side"])
    family = doc.get("base") or ("nato" if doc.get("units") == "imperial" else "wp" if pkg != "generic" else pkg)
    offs = formations.layout(family,                   # производные пакеты (arab, iaf73, us72) - по своей школе
                             "defend" if unit.get("defending") else "attack", len(seq), [roles[t] for t in seq])
    vehicles = []
    for i, (t, (fwd, right)) in enumerate(zip(seq, offs)):
        p = model.offset(center, axis, fwd, right)
        vehicles.append({"name": f"{unit['id']}#{i + 1:02d}", "type": t, "lat": p["lat"], "lon": p["lon"], "weight": weight[t], "heading": axis})
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
    if foes:                                     # для батареи поддержки (artillery, ставит build): ось и линия противника
        out[0]["axis"] = axis
        out[0]["fire_at"] = model.offset(mid, axis, sim.get("line_offset_km", 1.5) * 1000)
    for a in units.values():
        if a.get("attached_to") != unit["id"] or a["state"] == "destroyed" or not with_ad:
            continue
        av = []
        a_counts, a_weight = _deploy_ad(model.alive_by_type(a), _ad_share(a, unit, len(vehicles), _ad_cap(cap)))
        rights = [r_ for _f, r_ in offs] or [0.0]
        width = max(400.0, max(rights) - min(rights))    # фронт боевого порядка части
        by_cls: dict[str, int] = {}
        tot_cls: dict[str, int] = {}
        for comp in a["composition"]:
            c_ = ad_class(comp["type"])
            tot_cls[c_] = tot_cls.get(c_, 0) + a_counts.get(comp["type"], 0)
        for comp in a["composition"]:
            for _ in range(a_counts.get(comp["type"], 0)):
                k = len(av)
                # войсковая ПВО по доктрине (AD_ECHELON): пушки - парами за первым эшелоном, ПЗРК - с ротами, ЗРК
                # малой дальности - глубже; по фронту - равномерно по ширине боевого порядка (ОЦЕНКИ)
                cls_ = ad_class(comp["type"])
                j = by_cls.get(cls_, 0)
                by_cls[cls_] = j + 1
                n_c = max(1, tot_cls.get(cls_, 1))
                depth = AD_ECHELON.get(family, AD_ECHELON["wp"])[cls_]
                if cls_ == "gun":                    # парами: пара - одна точка по фронту, в паре - 80 м
                    slot, sub = j // 2, j % 2
                    n_slot = max(1, (n_c + 1) // 2)
                    right = (slot - (n_slot - 1) / 2) * width / n_slot + sub * 80
                else:
                    right = (j - (n_c - 1) / 2) * width / n_c
                p = model.offset(center, axis, -depth + (150 if k % 2 else -150), right)
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
    if model.category(target) in ("depot", "bridge", "airfield", "factory", "sam", "naval"):   # объект тыла, корабли - сами в миссии
        groups = [sam_site(state, target)] if model.category(target) == "sam" else []   # позиция ЗРК - сама цель
        placed = set()
        for sid in task["threats"]:
            if sid == target["id"] or sid in placed:
                continue
            parent = units.get(units[sid].get("attached_to") or "")
            if parent and parent["id"] in placed:
                continue
            if parent and parent["state"] == "march":
                col = column(state, parent, density * OTHER_DENSITY, CAP_MID)
                groups += [dict(col, free=True), attached_column(state, units[sid], col)]
                placed |= {parent["id"], sid}
            elif parent:                         # часть на месте (оборона, бой) - позицией, её ПВО - с ней (цель подавления ПВО)
                cl = battle_cluster(state, parent["id"]) if parent["state"] == "battle" else [parent["id"]]
                for uid in cl:                   # в ядре миссии - только ПВО (угроза); сама часть - как часть фронта (бюджет)
                    if uid not in placed:
                        part = _tag(battle_line(state, units[uid], density * OTHER_DENSITY, CAP_MID), cl)
                        groups += [dict(g_, free=True) if g_["kind"] == "battle" else g_ for g_ in part]
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
                col = column(state, parent, density * OTHER_DENSITY, CAP_MID)
                groups += [dict(col, free=True), attached_column(state, units[sid], col)]
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
        g["core"] = not g.pop("free", False)     # окно задачи игрока - бюджет миссии его не трогает (кроме частей угроз)
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
            for a in units.values():                 # вдали от задачи колонна - без ПВО (AD_RADAR_MAX)
                if a.get("attached_to") == u["id"] and a["state"] != "destroyed" and cap_of(u) != CAP_TOKEN:
                    groups.append(attached_column(state, a, col))
            placed.add(u["id"])
        else:                                    # оборона, тыл, небоеспособна - позиция у пункта (вдали - без ПВО)
            groups += _tag(battle_line(state, u, far, cap_of(u), with_ad=cap_of(u) != CAP_TOKEN), [u["id"]])
            placed.add(u["id"])
    placed |= {g["unit"] for g in groups}
    for u in units.values():                     # ЗРК - полностью, но не дальше SAM_KM (по роли - SAM_KM_ROLE) от цели
        if (model.category(u) == "sam" and u["id"] not in placed and not u.get("attached_to")
                and u["state"] not in ("destroyed", "pending") and model.strength(u) > 0
                and model.dist_km(model.unit_pos(state, u), center) <= SAM_KM_ROLE.get(u["role"], SAM_KM)):
            groups.append(sam_site(state, u, token=model.dist_km(model.unit_pos(state, u), center) > SAM_FULL_KM))
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
    fire = {pl["unit"] for pl in state.get("ssm_plan") or []}
    tgt_id = task.get("target")
    for u in units.values():                     # пусковые ОТР: с пусками суток, рядом с объектом задачи или цель задачи
        if (model.category(u) == "ssm" and u["state"] not in ("destroyed", "pending") and model.strength(u) > 0
                and u["id"] not in placed and (u["id"] in fire or u["id"] == tgt_id
                                               or model.dist_km(model.unit_pos(state, u), center) <= DETAIL_KM)):
            groups.append(ssm_site(state, u))
    core = {g["unit"] for g in groups if g.get("core")}
    # приданная ПВО части уже в окне (угроза коридора) - второй раз с частью не ставится (была двумя группами DCS)
    groups = [g for g in groups if g["vehicles"] and (g.get("core") or g["unit"] not in core)]
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
            if g["kind"] not in ("column", "battle") and not g.get("battle"):   # ПВО части в бою - вместе с ней
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

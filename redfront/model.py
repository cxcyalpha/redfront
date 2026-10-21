"""Модель кампании: части, их состояние, сохранение.

Три слоя данных: сектор (карта), состав сил (что выставил игрок - любые типы, у каждой части роль из roles.json)
и пакеты доктрины по сторонам (data/doctrine/*.json). Доктрина работает с ролями, не с типами.

Состояние - обычный JSON (state.json). Численность наземных частей хранится по типам техники: count (штат на начало
кампании) и lost (потери, дробные: развёрнутый в миссии кусок части несёт "вес", см. materialize.py).
"""
from __future__ import annotations

import bisect
import copy
import json
import math
import random
import uuid
from pathlib import Path

DATA = Path(__file__).parent / "data"
EARTH_R_KM = 6371.0
STATE_VERSION = 2
SIDES = ("red", "blue")


def load_json(name: str | Path) -> dict:
    """Файл игрока (если путь существует) или файл из data/ пакета."""
    p = Path(name)
    if not p.is_file():
        p = DATA / name
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- типы ЛА ----------

_AIRCRAFT: dict | None = None


def aircraft_info(type_name: str | None) -> dict:
    """Запись типа ЛА из data/aircraft.json (cargo_t, troops, crew, night); нет - {}."""
    global _AIRCRAFT
    if _AIRCRAFT is None:
        try:
            _AIRCRAFT = load_json("aircraft.json").get("types", {})
        except (OSError, ValueError):
            _AIRCRAFT = {}
    return _AIRCRAFT.get(type_name or "") or {}


def group_speed_kmh(state: dict, g: dict, tdef: dict) -> float:
    """Скорость группы на маршруте и в расчёте времени - скорость задачи доктрины (speed_kmh; ОЦЕНКА)."""
    return g.get("speed_kmh") or tdef["speed_kmh"]   # вертолёты в совместном пакете - своя скорость


# ---------- роли и доктрина ----------

_ROLES: dict | None = None


def roles() -> dict:
    global _ROLES
    if _ROLES is None:
        _ROLES = load_json("roles.json")
    return _ROLES


def role_info(role: str) -> dict:
    try:
        return roles()["units"][role]
    except KeyError:
        raise KeyError(f"роль '{role}' не описана в roles.json") from None


def category(unit: dict) -> str:
    """air / heli / ground / sam - по роли части."""
    return role_info(unit["role"])["category"]


def enemy(side: str) -> str:
    return "blue" if side == "red" else "red"


_DOCTRINE: dict = {}


def doctrine(state: dict, side: str) -> dict:
    """Пакет доктрины стороны (по state['doctrine'][side]). Кэш по файлу и времени изменения: на всём фронте
    доктрина спрашивается десятки тысяч раз за сутки. Результат только для чтения."""
    name = Path("doctrine") / f"{state['doctrine'][side]}.json"
    p = name if name.is_file() else DATA / name
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _DOCTRINE:
        _DOCTRINE[key] = json.loads(p.read_text(encoding="utf-8"))
    return _DOCTRINE[key]


# ---------- геометрия (широта/долгота, без проекции DCS) ----------

def dist_km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(h))


def lerp(a: dict, b: dict, t: float) -> dict:
    return {"lat": a["lat"] + (b["lat"] - a["lat"]) * t, "lon": a["lon"] + (b["lon"] - a["lon"]) * t}


def bearing_deg(a: dict, b: dict) -> float:
    """Начальный пеленг из a на b, градусы от севера по часовой."""
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlo = math.radians(b["lon"] - a["lon"])
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def offset(p: dict, bearing: float, fwd_m: float, right_m: float = 0.0) -> dict:
    """Точка в fwd_m вперёд по курсу bearing и right_m вправо от p (плоское приближение, для сотен метров - километров)."""
    b = math.radians(bearing)
    north = fwd_m * math.cos(b) - right_m * math.sin(b)
    east = fwd_m * math.sin(b) + right_m * math.cos(b)
    return {"lat": p["lat"] + north / 111_320.0, "lon": p["lon"] + east / (111_320.0 * math.cos(math.radians(p["lat"])))}


def route_points(state: dict, unit: dict) -> list[dict]:
    """Геометрия маршрута: по каждому участку "A>B" - ломаная по дорогам из state['roads'] (см. roads.py),
    если она есть, иначе прямая между пунктами (как в 0.1/0.2)."""
    places, roads = state["places"], state.get("roads") or {}
    route = unit["route"]
    if len(route) == 1:
        return [dict(lat=places[route[0]]["lat"], lon=places[route[0]]["lon"])] * 2
    pts: list[dict] = []
    for a, b in zip(route, route[1:]):
        seg = (roads.get(f"{a}>{b}") or list(reversed(roads.get(f"{b}>{a}") or []))      # дорога в обратную сторону - та же
               or [dict(lat=places[p]["lat"], lon=places[p]["lon"]) for p in (a, b)])
        if pts and dist_km(pts[-1], seg[0]) < 0.005:
            seg = seg[1:]
        pts.extend(dict(p) for p in seg)
    return pts


def place_km(state: dict, unit: dict) -> list[tuple[str, float]]:
    """Пункты маршрута и их удаление вдоль геометрии маршрута, км."""
    pts = route_points(state, unit)
    return [(p, project_km(pts, state["places"][p])) for p in unit["route"]]


def route_length_km(pts: list[dict]) -> float:
    return sum(dist_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_at_km(pts: list[dict], km: float) -> tuple[dict, int]:
    """Точка на маршруте через km от начала и индекс сегмента, на котором она лежит."""
    km = max(0.0, km)
    for i in range(len(pts) - 1):
        seg = dist_km(pts[i], pts[i + 1])
        if km <= seg or i == len(pts) - 2:
            return lerp(pts[i], pts[i + 1], min(1.0, km / seg if seg else 0.0)), i
        km -= seg
    return dict(pts[-1]), len(pts) - 2


def project_km(pts: list[dict], p: dict) -> float:
    """Расстояние вдоль маршрута до ближайшей к p точки маршрута (приближённо, в плоскости lat/lon с поправкой на широту)."""
    best, best_km, run = None, 0.0, 0.0
    k = math.cos(math.radians(p["lat"]))
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ax, ay, bx, by, px, py = a["lon"] * k, a["lat"], b["lon"] * k, b["lat"], p["lon"] * k, p["lat"]
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        q = lerp(a, b, t)
        d = dist_km(q, p)
        seg = dist_km(a, b)
        if best is None or d < best:
            best, best_km = d, run + seg * t
        run += seg
    return best_km


# ---------- численность ----------

def total(unit: dict) -> float:
    return float(sum(c["count"] for c in unit.get("composition", [])))


def alive_by_type(unit: dict) -> dict[str, float]:
    return {c["type"]: max(0.0, c["count"] - unit["lost"].get(c["type"], 0.0)) for c in unit.get("composition", [])}


def strength(unit: dict) -> float:
    """Доля исправной техники от штата, 0..1."""
    t = total(unit)
    return sum(alive_by_type(unit).values()) / t if t else 0.0


_GEOM: dict = {}


def _route_geom(state: dict, route: list[str]) -> tuple[list[dict], list[float]]:
    """Геометрия маршрута и накопленные км по точкам - с кэшем: место части спрашивается сотни тысяч раз за сутки
    (бой, марш, снабжение), а маршрут меняется редко. Только для чтения."""
    roads, places = state.get("roads") or {}, state["places"]
    links = [f"{a}>{b}" for a, b in zip(route, route[1:])]
    key = (tuple((places[p]["lat"], places[p]["lon"]) for p in route),        # не id словарей: кампаний за сеанс много
           tuple((len(roads.get(k) or ()), len(roads.get(">".join(reversed(k.split(">")))) or ())) for k in links))
    g = _GEOM.get(key)
    if g is None:
        if len(_GEOM) > 20000:
            _GEOM.clear()
        pts = route_points(state, {"route": route})
        cum = [0.0]
        for i in range(len(pts) - 1):
            cum.append(cum[-1] + dist_km(pts[i], pts[i + 1]))
        g = _GEOM[key] = (pts, cum)
    return g


def route_km(state: dict, unit: dict) -> float:
    """Длина маршрута части, км (route_length_km(route_points(...)) по кэшу геометрии)."""
    return _route_geom(state, unit["route"])[1][-1]


def unit_pos(state: dict, unit: dict) -> dict:
    if unit.get("attached_to"):                 # приданная часть (войсковая ПВО) - там же, где её часть
        return unit_pos(state, state["units"][unit["attached_to"]])
    if "route" in unit:                          # как point_at_km(route_points(...)), по кэшу геометрии
        pts, cum = _route_geom(state, unit["route"])
        km = max(0.0, unit["progress_km"])
        i = min(max(0, bisect.bisect_right(cum, km) - 1), len(pts) - 2)
        seg = cum[i + 1] - cum[i]
        return lerp(pts[i], pts[i + 1], min(1.0, (km - cum[i]) / seg if seg else 0.0))
    if "pos" in unit:
        return unit["pos"]
    base = state["airbases"][unit["base"]]
    return {"lat": base["lat"], "lon": base["lon"]}


def unit_pos_at(state: dict, unit: dict, seconds: float, default_kmh: float | None = None) -> dict:
    """Где часть будет через seconds от начала миссии. Колонна на марше идёт со скоростью, замеренной в прошлых
    миссиях (observed_kmh, пишет дебриф); пока замера нет - default_kmh (None - приказная march_kmh).
    В DCS колонна идёт заметно медленнее приказа: camp3, день 1 - около 6 км/ч при march_kmh 30 (Tacview).
    Остальные части стоят. Приданная часть - там же, где её часть."""
    if unit.get("attached_to"):
        return unit_pos_at(state, state["units"][unit["attached_to"]], seconds, default_kmh)
    if "route" in unit and unit.get("state") == "march":
        kmh = unit.get("observed_kmh")
        if kmh is None:
            kmh = unit.get("march_kmh", 0) if default_kmh is None else default_kmh
        pts = route_points(state, unit)
        km = min(route_length_km(pts), unit["progress_km"] + kmh * seconds / 3600.0)
        return point_at_km(pts, km)[0]
    return unit_pos(state, unit)


BUBBLE_KM = 150   # ОЦЕНКА: ЗРК противника, стоящие не дальше этого от маршрутов пакета, ставятся в миссию, даже если до маршрута не достают


# ---------- кампания ----------

def new_campaign(name: str, date: str | None = None, start_hour: int = 7,
                 sector: str | Path = "sector_hamburg.json", oob: str | Path = "oob_hamburg.json",
                 player_side: str = "red", packages: dict[str, str] | None = None,
                 column_budget_units: int = 40, seed: int | None = None, variant: str | None = None,
                 randomness: bool = True) -> dict:
    """Новая кампания. Вариант сценария (variants в составе сил) - заданный, иначе случайный по seed;
    randomness=False - без случайности: базовый вариант, без разброса в бою и в решениях командования."""
    from dcs.terrain.germany import Germany  # координаты аэродромов берём из терраина pydcs, а не вписываем руками
    if player_side not in SIDES:
        raise ValueError(f"сторона должна быть одной из {SIDES}")
    packages = {**{"red": "wp", "blue": "nato"}, **(packages or {})}   # синие - доктрина НАТО (data/doctrine/nato.json)
    for side, pkg in packages.items():
        if not (DATA / "doctrine" / f"{pkg}.json").is_file():
            raise FileNotFoundError(f"нет пакета доктрины '{pkg}' для стороны {side} (data/doctrine/{pkg}.json)")
    sec = load_json(sector)
    forces = load_json(oob)
    date = date or forces.get("date") or "2026-05-15"   # дата среза пресета состава сил (1985, 1987, 1989)
    if forces["countries"]["red"] == forces["countries"]["blue"]:
        raise ValueError("у сторон в составе сил одна и та же страна (countries)")
    terrain = Germany()
    bases = {}
    for bid, b in sec["airbases"].items():
        if not b.get("military", True):          # только военные аэродромы
            continue
        ll = terrain.airports[b["airport"]].position.latlng()
        bases[bid] = {**b, "lat": ll.lat, "lon": ll.lng, "state": "open"}
    # ---- вариант сценария и разброс ----
    if seed is None:
        seed = random.randrange(1, 10**6) if randomness else 0
    rng = random.Random(seed)
    variants = forces.get("variants") or []
    if variant:
        chosen = next((v for v in variants if v["name"] == variant), None)
        if chosen is None:
            raise ValueError(f"в составе сил нет варианта '{variant}'; есть: {', '.join(v['name'] for v in variants) or 'нет'}")
    elif variants and randomness:
        chosen = rng.choice(variants)
    else:
        chosen = variants[0] if variants else None
    objectives = copy.deepcopy(sec.get("objectives", {}))
    if chosen:
        objectives.update(chosen.get("objectives", {}))
    patches = (chosen or {}).get("units", {})
    units = {}
    for u in copy.deepcopy(forces["units"]):
        u.update(copy.deepcopy(patches.get(u["id"], {})))
        if randomness and u.get("arrives_jitter") and "arrives_day" in u:   # срок ввода резерва +-jitter суток
            u["arrives_day"] = max(1, u["arrives_day"] + rng.randint(-u["arrives_jitter"], u["arrives_jitter"]))
        role_info(u["role"])                       # роль должна быть известна - иначе ошибка сразу, а не в планировщике
        u.setdefault("lost", {})
        u.setdefault("state", "ready")
        u.pop("_about", None)
        if role_info(u["role"])["category"] in ("air", "heli"):
            u.setdefault("count0", u.get("count", 0))   # штат - до него идёт пополнение
        units[u["id"]] = u
    # объектовая ПВО: позиция сектора (ad_sites: место и ярус) + шаблон стороны из состава сил (ad_templates)
    tier_role = {"long": "sam_long", "medium": "sam_medium", "short": "sam_short", "gci": "gci"}
    for site in sec.get("ad_sites", []):
        variants = ((forces.get("ad_templates") or {}).get(site["side"]) or {}).get(site["tier"]) or []
        if not variants or site["id"] in units:
            continue                               # нет шаблона яруса у стороны - позиция пустая
        req = site.get("requires_types")          # КРУ: только если на аэродроме в этом составе сил базируется МиГ-29
        if req and not any(u.get("type") in req and site.get("covers") == f"af_{u.get('base')}" for u in forces["units"]):
            continue
        tpl = variants[site.get("variant", 0) % len(variants)]
        sname = site["name"] if tpl["name"] in site["name"] else f"{site['name']}: {tpl['name']}"   # не name: это имя кампании
        units[site["id"]] = {"id": site["id"], "name": sname, "side": site["side"],
                             "role": tier_role[site["tier"]], "state": "deployed", "fixed": True,
                             "pos": {"lat": site["lat"], "lon": site["lon"]}, "covers": site.get("covers"),
                             "composition": copy.deepcopy(tpl["composition"]), "lost": {},
                             "source": f"позиция - {site.get('rule', 'сектор')}; состав - шаблон стороны", "estimate": True}
        for k in ("channel", "radius_km"):         # КРУ: канал и радиус наведения
            if k in site:
                units[site["id"]][k] = site[k]
    # объекты в тылу - цели ударов: склады, мосты, аэродромы (повреждение 0..1, восстановление - sim)
    for d in [*sec.get("depots", []), *[{**f, "_role": "factory"} for f in sec.get("factories", [])]]:   # заводы - как склады
        pl = sec["places"][d["place"]]
        units[d["id"]] = {"id": d["id"], "name": d["name"], "side": d["side"], "role": d.get("_role", "depot"), "place": d["place"],
                          "pos": {"lat": d.get("lat", pl["lat"]), "lon": d.get("lon", pl["lon"])},   # уточнён - mapobj.py
                          "state": "active", "damage": 0.0, "lost": {}, "composition": []}
        for k in ("map_objects", "map_type", "pos_checked", "found", "supply"):
            if k in d:
                units[d["id"]][k] = d[k]
    for b in sec.get("bridges", []):
        units[b["id"]] = {"id": b["id"], "name": b["name"], "side": None, "role": "bridge", "links": b["links"],
                          "pos": {"lat": b["lat"], "lon": b["lon"]}, "state": "active", "damage": 0.0, "lost": {}, "composition": []}
        for k in ("map_objects", "map_type", "pos_checked", "found", "minor"):   # мост уточнён / найден зондом (mapobj.py)
            if k in b:
                units[b["id"]][k] = b[k]
    for bid, b in bases.items():
        units[f"af_{bid}"] = {"id": f"af_{bid}", "name": f"Аэродром {b['name']}", "side": b["side"], "role": "airfield", "base": bid,
                              "pos": {"lat": b["lat"], "lon": b["lon"]}, "state": "active", "damage": 0.0, "lost": {}, "composition": []}
    st = {
        "version": STATE_VERSION,
        "campaign_id": uuid.uuid4().hex[:8],
        "name": name,
        "theatre": sec["theatre"],
        "sector": str(sector), "oob": str(oob),   # файлы театра: зонды карты и дорог, окно - по ним
        "date": date,
        "start_hour": start_hour,
        "day": 1,
        "sortie": 0,
        "player_side": player_side,
        "doctrine": packages,
        "countries": forces["countries"],
        "settings": {"column_budget_units": column_budget_units,   # ОЦЕНКА версии 0.1: бюджет машин на колонну при плотности 1.0
                     "bubble_km": BUBBLE_KM, "randomness": randomness},
        "places": sec["places"],
        "links": sec.get("links", []),            # связи пунктов - граф оперативного уровня (ops.py)
        "replacements": forces.get("replacements", {}),
        "objectives": objectives,                 # цели операции сторон (по порядку), с учётом варианта
        "scenario": {"seed": seed, "variant": chosen["name"] if chosen else None,
                     "title": chosen.get("title") if chosen else None},
        "airbases": bases,
        "units": units,
        "task": None,
        "manifest": None,
        "log": [],
    }
    init_crews(st)
    from . import farp as _farp                  # передовые вертолётные площадки (готовые площадки карты)
    _farp.ensure(st)
    from . import intel as _intel                # туман войны: известные позиции ЗРК противника
    _intel.ensure(st)
    for side in (chosen or {}).get("assembly", []):   # вариант: первый эшелон стороны - в исходных районах у границы
        assembly_areas(st, side)
    return st


ASSEMBLY_PER_PLACE = 2   # ОЦЕНКА: дивизий (бригад) первого эшелона в исходном районе у одного пункта


def assembly_areas(state: dict, side: str) -> list[str]:
    """Первый эшелон стороны (части на месте с первого дня, не десант и не резерв) - в исходных районах: в пунктах
    своей стороны на линии фронта, ближних по дорогам к месту дислокации (не больше ASSEMBLY_PER_PLACE на пункт).
    Так внезапное наступление начинается с границы в первые часы, а не после марша из гарнизонов (ОЦЕНКА замысла:
    выход в исходные районы до начала операции)."""
    from . import ops
    front = ops.front_nodes(state, side)
    used: dict[str, int] = {}
    lines = []
    own = sorted((u for u in state["units"].values() if u["side"] == side and role_info(u["role"])["category"] == "ground"
                  and u.get("role") == "maneuver" and u["state"] == "defend" and not u.get("attached_to")
                  and u.get("order") not in ("reserve", "airhead") and len(u.get("route", [])) == 1), key=lambda u: u["id"])
    for u in own:
        here = u["route"][0]
        free = [p for p in front if used.get(p, 0) < ASSEMBLY_PER_PLACE] or front
        if not free or here in front:
            continue
        t = min(free, key=lambda p: ops.path_km(state, here, p))
        used[t] = used.get(t, 0) + 1
        u["route"], u["progress_km"] = [t], 0.0
        u["garrison"] = here
        lines.append(f"{u['name']}: исходный район у {t} (из {here}).")
    return lines


def rng(state: dict, purpose: str) -> random.Random | None:
    """Генератор случайных чисел для суток и цели (повторяемый по seed кампании); None - случайность выключена."""
    if not state.get("settings", {}).get("randomness"):
        return None
    return random.Random(f"{(state.get('scenario') or {}).get('seed', 0)}-{state['day']}-{purpose}")


def note(state: dict, text: str) -> None:
    state["log"].append(f"День {state['day']}: {text}")


def save(state: dict, path: Path) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load(path: Path) -> dict:
    st = json.loads(Path(path).read_text(encoding="utf-8"))
    if st.get("version") != STATE_VERSION:
        raise RuntimeError(f"файл кампании версии {st.get('version')}, нужна {STATE_VERSION}: создайте кампанию заново (new)")
    sync_ad_sites(st)
    for u in st.get("units", {}).values():       # МиГ-29А старой модели (ГС3) - модуль MiG-29A Fulcrum (Alex)
        if u.get("type") == "MiG_29A":
            u["type"] = "MiG_29_Fulcrum"
    init_crews(st)
    drop_dummy_depots(st)
    from . import farp as _farp                  # вертолётные площадки карты - и в старых кампаниях
    _farp.ensure(st)
    from . import intel as _intel                # разведка позиций ЗРК противника - и в старых кампаниях
    _intel.ensure(st)
    if st.get("roads"):                          # старые кампании: дороги-крюки DCS - убрать, части - на прежнем месте
        from . import roads as _roads
        marching = [u for u in st["units"].values() if "route" in u]
        before = {u["id"]: unit_pos(st, u) for u in marching}
        for ln in _roads.sanitize(st):
            note(st, ln)
        for u in marching:
            u["progress_km"] = project_km(route_points(st, u), before[u["id"]])
    return st


def drop_dummy_depots(st: dict) -> None:
    """Склады, найденные зондом карты (supply: false), - цели без последствий: путали игрока - убраны из кампании."""
    gone = [k for k, u in st.get("units", {}).items() if u.get("role") == "depot" and u.get("supply") is False]
    for uid in gone:
        del st["units"][uid]
    # только задачи по удалённым складам; цели дежурств, перевозок, разведки (orbit_..., qra_...) - не части
    ok = lambda t: t.get("target") not in gone
    st["tasks"] = [t for t in (st.get("tasks") or []) if ok(t)]
    if st.get("task") and not ok(st["task"]):
        st["task"] = None
    if st.get("ato"):
        st["ato"]["entries"] = [e for e in st["ato"].get("entries", []) if ok(e["task"])]


def init_crews(st: dict) -> None:
    """Экипажи авиачастей (crews, штат crews0): crew_ratio доктрины стороны на самолёт штата (ОЦЕНКА) - для новых
    кампаний и старых сохранений."""
    for u in st.get("units", {}).values():
        if role_info(u["role"])["category"] in ("air", "heli"):
            if "crews" not in u:
                ratio = doctrine(st, u["side"])["sim"].get("crew_ratio", 1.0)
                u["crews0"] = int(round(u.get("count0", u.get("count", 0)) * ratio))
                u["crews"] = u["crews0"]
    st.setdefault("downed", [])          # сбитые экипажи на земле (csar.py)
    from . import pilots                  # лётчики полков - по числу экипажей (имена в миссию)
    pilots.ensure_all(st)


def sync_ad_sites(st: dict) -> None:
    """Позиции объектовой ПВО (fixed) - из файла сектора: исправленные правила размещения доходят и до уже созданных
    кампаний. Объектовая ПВО позицию в модели не меняет, так что расхождение - только от правки сектора."""
    fixed = [u for u in st.get("units", {}).values() if u.get("fixed")]
    if not fixed or not st.get("sector"):
        return
    try:
        sites = {x["id"]: x for x in load_json(st["sector"]).get("ad_sites", [])}
    except (OSError, ValueError):
        return
    for u in fixed:
        x = sites.get(u["id"])
        if x:
            u["pos"] = {"lat": x["lat"], "lon": x["lon"]}

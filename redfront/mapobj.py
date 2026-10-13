"""Объекты карты как цели тыла - то же, что "Assign as..." в редакторе, но без ручной работы над каждым объектом.

Координаты мостов и складов в секторе - ОЦЕНКИ. Объекты карты (их имена, типы, положение) знает только DCS, поэтому,
как с дорогами, их спрашивают у DCS один раз на сектор:
  1. probe()  - служебная миссия; её скрипт (lua/map_probe.lua) проходит весь сектор сеткой и собирает все мосты
                (с признаком "над водой") и все объекты складов, пишет map_<сектор>.json;
  2. apply()  - мост: из найденных выбирается тот, что лежит на связи графа, которую он закрывает (ближе всего к линии
                связи - по дороге, если она известна, иначе по прямой между пунктами), с поправкой на близость к оценке;
                его положение становится точкой цели, имена всех пролётов того же типа рядом - объектами цели.
                склад: из объектов с ключевым словом склада (DEPOT_KEYS) у пункта берётся самое плотное скопление -
                его центр становится точкой цели, имена объектов скопления - объектами цели.
  3. discover - новые цели из того же зонда: мост над водой на связи графа, у которой своего моста ещё нет, - новый мост
                (его разрушение закрывает эту связь); скопление объектов склада у пункта без склада - новый склад стороны,
                владеющей пунктом (не больше одного на пункт).
Применяется к кампании (state) или прямо к файлу сектора - тогда все новые кампании сразу с точными целями.

Ручная правка - как в Retribution, через "Assign as..." в редакторе (import_miz): в любой миссии назначить объекты
карты и в свойствах зоны заполнить ROLE = depot | bridge | factory, VALUE = id объекта кампании (red_depot_1, br_lauenburg).
Все зоны с одинаковым VALUE - один объект; это заменяет найденное зондом.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript
from dcs.mapping import LatLng, Point
from dcs.terrain.germany import Germany
from dcs.translation import String
from dcs.triggers import TriggerStart

from . import model, roads

LUA = Path(__file__).parent / "lua" / "map_probe.lua"
BRIDGE_SEARCH_M = 3000      # ОЦЕНКА: радиус поиска моста вокруг оценочной точки
DEPOT_SEARCH_M = 2500       # ОЦЕНКА: радиус перечня объектов вокруг пункта склада
W_ESTIMATE = 0.3            # ОЦЕНКА: вес близости к оценочной точке против близости к линии связи
MAX_OFF_LINK_KM = 2.0       # ОЦЕНКА: мост дальше от линии связи - не тот, не применяется
SPAN_KM = 0.6               # пролёты того же типа ближе этого к выбранному - один мост
BRIDGE_EXCLUDE = ("wooden",)  # не цели: деревянные мостки через пруды и ручьи (Alex, по редактору)
# Типы объектов карты, которые считаются складом: имена типов - с карты Germany (редактор, "Assign as..."):
# silo_01/silo_03 - резервуары, stock - складское здание, safshungar02 - ангар, tube_pile - штабель труб.
# Что из этого "склад" - решение проекта (ОЦЕНКА), не документ.
DEPOT_KEYS = ("silo", "stock", "hungar", "hangar", "tube_pile")
# Заводы: industrial_eu_*, industrial_baltic_* (редактор, Alex: "все заводы на карте - industrial"). Отдельная роль
# factory, не склад: склад снабжает войска, завод - восстановление тыла и пополнение авиации (logistics.industry).
FACTORY_KEYS = ("industrial",)
FACTORY_CLUSTER_KM = 0.4    # ОЦЕНКА: корпуса завода ближе этого к центру - один завод
FACTORY_MIN_OBJECTS = 3     # ОЦЕНКА: меньше - отдельное здание, не завод
DEPOT_CLUSTER_KM = 0.3      # ОЦЕНКА: объекты склада ближе этого к центру скопления - один склад
DEPOT_MIN_OBJECTS = 3       # ОЦЕНКА: меньше - не склад (одиночный ангар в деревне)
DEPOT_MAX_OBJECTS = 12
TILE_R_M = 5000             # зонд: радиус поиска в ячейке сетки
TILE_STEP_M = 7000          # шаг сетки (не больше TILE_R * sqrt(2) - ячейки перекрываются, пропусков нет)
TILE_MARGIN_M = 15000       # запас вокруг пунктов сектора
TILES_PER_TICK = 2          # ячеек за такт скрипта (DCS не замирает надолго)
NEW_BRIDGE_LINK_KM = 1.0    # ОЦЕНКА: мост над водой ближе этого к линии связи - переправа этой связи
NEW_DEPOT_PLACE_KM = 6.0    # ОЦЕНКА: скопление объектов склада ближе этого к пункту - склад пункта
NEW_DEPOT_GAP_KM = 3.0      # ОЦЕНКА: ближе этого к уже известному складу - тот же склад, новый не создаётся


SECTOR_KEY = {"bridge": "bridges", "depot": "depots", "factory": "factories"}   # роль -> список в файле сектора


def _xy(ll: dict, terrain) -> tuple[float, float]:
    p = Point.from_latlng(LatLng(ll["lat"], ll["lon"]), terrain)
    return p.x, p.y


def tiles(sec: dict, terrain) -> list[tuple[float, float]]:
    """Ячейки сетки, нужные целям: у пунктов (склады, заводы - до NEW_DEPOT_PLACE_KM) и вдоль связей графа (мосты на
    связях) - не весь прямоугольник: на театре всей карты это в разы меньше ячеек. Любая точка ближе этих полос к
    пункту или связи покрыта: ближайший центр ячейки - не дальше TILE_STEP/sqrt(2) <= TILE_R."""
    pl = {n: _xy(p, terrain) for n, p in sec["places"].items()}
    pts = list(pl.values()) + [_xy(b, terrain) for b in sec.get("bridges", [])]
    segs = [(pl[a], pl[b]) for a, b in sec.get("links", []) if a in pl and b in pl]
    cell = TILE_STEP_M / math.sqrt(2)
    near_pt = cell + (NEW_DEPOT_PLACE_KM + 1.0) * 1000
    near_seg = cell + 3000                       # ОЦЕНКА: дорога отходит от прямой между пунктами
    def d_seg(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)
    x0, x1 = min(p[0] for p in pts) - near_pt, max(p[0] for p in pts) + near_pt
    y0, y1 = min(p[1] for p in pts) - near_pt, max(p[1] for p in pts) + near_pt
    out, x = [], x0
    while x <= x1 + TILE_STEP_M / 2:
        y = y0
        while y <= y1 + TILE_STEP_M / 2:
            if (any(math.hypot(x - px, y - py) <= near_pt for px, py in pts)
                    or any(d_seg(x, y, a, b) <= near_seg for a, b in segs)):
                out.append((x, y))
            y += TILE_STEP_M
        x += TILE_STEP_M
    return out


def probe(out_path: Path, sector: str | Path = "sector_hamburg.json") -> dict:
    sec = model.load_json(sector)
    sid = roads.sector_id(sector)
    terrain = Germany()
    tl = tiles(sec, terrain)
    dp = []
    for d in sec.get("depots", []):
        x, y = _xy(d if "lat" in d else sec["places"][d["place"]], terrain)
        dp.append(f'{{ id = "{d["id"]}", x = {x:.1f}, y = {y:.1f}, r = {DEPOT_SEARCH_M} }}')
    script = (LUA.read_text(encoding="utf-8").replace("@SECTOR@", sid)
              .replace("@TILES@", ", ".join(f"{{ x = {x:.0f}, y = {y:.0f} }}" for x, y in tl))
              .replace("@TILE_R@", str(TILE_R_M)).replace("@PER_TICK@", str(TILES_PER_TICK))
              .replace("@DEPOTS@", ", ".join(dp))
              .replace("@DEPOT_KEYS@", ", ".join(f'"{k}"' for k in DEPOT_KEYS))
              .replace("@FACTORY_KEYS@", ", ".join(f'"{k}"' for k in FACTORY_KEYS)))
    m = Mission(Germany())
    trig = TriggerStart(comment="redfront map probe")
    trig.add_action(DoScript(String(script)))
    m.triggerrules.triggers.append(trig)
    m.set_description_text(f"redfront: служебная миссия объектов карты для сектора '{sid}'. Запустите (можно "
                           f"наблюдателем), дождитесь сообщения 'объекты карты записаны' и выйдите.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    km2 = (len(tl) * TILE_STEP_M ** 2) / 1e6
    return {"file": str(out_path), "sector": sid, "tiles": len(tl), "area_km2": round(km2),
            "bridges": len(sec.get("bridges", [])), "depots": len(dp)}


def load(path: Path) -> dict:
    """Файл зонда -> объекты в широте/долготе: bridges_all [{name, type, lat, lon, water}], depot_objects_all,
    depots {id склада: {тип: {n, lat, lon}}}; старый формат - bridges/depot_objects по id цели."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    terrain = Germany()
    out = {"sector": raw.get("sector"), "bridges": {}, "depots": {}, "depot_objects": {}, "errors": raw.get("errors", {})}
    def objs_ll(objs):
        lst = []
        for name, tp, x, y in objs:
            ll = Point(x, y, terrain).latlng()
            lst.append({"name": str(name), "type": tp, "lat": ll.lat, "lon": ll.lng})
        return lst
    for bid, objs in (raw.get("bridges") or {}).items():      # старый формат зонда - по целям
        out["bridges"][bid] = objs_ll(objs)
    if "bridges_all" in raw:                                    # зонд всего сектора
        out["bridges_all"] = [{**o, "water": bool(r[4]) if len(r) > 4 else True}
                              for o, r in zip(objs_ll([r[:4] for r in raw["bridges_all"]]), raw["bridges_all"])
                              if not _excluded(r[1])]
    if "depot_objects_all" in raw:
        out["depot_objects_all"] = objs_ll(raw["depot_objects_all"])
    if "factory_objects_all" in raw:
        out["factory_objects_all"] = objs_ll(raw["factory_objects_all"])
    for did, objs in (raw.get("depot_objects") or {}).items():
        out["depot_objects"][did] = objs_ll(objs)
    for did, types in (raw.get("depots") or {}).items():
        out["depots"][did] = {tp: {"n": n, **dict(zip(("lat", "lon"), (lambda ll: (ll.lat, ll.lng))(Point(x, y, terrain).latlng())))}
                              for tp, (n, x, y) in types.items()}
    return out


def _excluded(tp: str) -> bool:
    return any(k in str(tp).lower() for k in BRIDGE_EXCLUDE)


def drop_excluded(target: dict) -> list[str]:
    """Убрать найденные зондом мосты исключённых типов (BRIDGE_EXCLUDE), если они уже стали целями."""
    lines = []
    for b in list(_items(target, "bridge")):
        if b.get("found") and _excluded(b.get("map_type", "")):
            if "units" in target:
                del target["units"][b["id"]]
            else:
                target["bridges"].remove(b)
            lines.append(f"{b['name']}: убран ({b.get('map_type')} - не цель).")
    return lines


def _seg_km(p: dict, a: dict, b: dict) -> float:
    """Расстояние от точки до отрезка, км (плоское приближение - на десятках км хватает)."""
    k = math.cos(math.radians(p["lat"])) * 111.32
    px, py = p["lon"] * k, p["lat"] * 110.57
    ax, ay, bx, by = a["lon"] * k, a["lat"] * 110.57, b["lon"] * k, b["lat"] * 110.57
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def link_lines(places: dict, links: list, roads_: dict | None = None) -> list[list[dict]]:
    out = []
    for a, b in links:
        line = (roads_ or {}).get(f"{a}>{b}") or (roads_ or {}).get(f"{b}>{a}")
        out.append(line or [places[a], places[b]])
    return out


def pick_bridge(est: dict, lines: list[list[dict]], objs: list[dict]) -> tuple[dict | None, list[dict], float]:
    """Выбрать мост: ближе всего к линии связи, с поправкой на оценочную точку. -> (объект, пролёты, км от связи)."""
    best, best_s, best_off = None, None, None
    for o in objs:
        off = min(_seg_km(o, ln[i], ln[i + 1]) for ln in lines for i in range(len(ln) - 1))
        s = off + W_ESTIMATE * model.dist_km(o, est)
        if best_s is None or s < best_s:
            best, best_s, best_off = o, s, off
    if best is None:
        return None, [], 0.0
    spans = [o for o in objs if o["type"] == best["type"] and model.dist_km(o, best) <= SPAN_KM]
    return best, spans, best_off


def _km_xy(o: dict, lat0: float) -> tuple[float, float]:
    return o["lon"] * 111.32 * math.cos(math.radians(lat0)), o["lat"] * 110.57


def clusters(objs: list[dict], radius_km: float = DEPOT_CLUSTER_KM, min_n: int = DEPOT_MIN_OBJECTS) -> list[list[dict]]:
    """Скопления объектов (по убыванию размера), каждое не меньше min_n. Сетка с ячейкой radius_km - быстро и на
    десятках тысяч объектов карты (зонд всего сектора): соседи ищутся только в 3x3 ячейках."""
    if not objs:
        return []
    lat0 = sum(o["lat"] for o in objs) / len(objs)
    xy = [_km_xy(o, lat0) for o in objs]
    grid: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(xy):
        grid.setdefault((int(x // radius_km), int(y // radius_km)), []).append(i)
    r2 = radius_km ** 2
    def near(i):
        x, y = xy[i]
        cx, cy = int(x // radius_km), int(y // radius_km)
        return [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((cx + dx, cy + dy), ())
                if (xy[j][0] - x) ** 2 + (xy[j][1] - y) ** 2 <= r2]
    nb = {i: near(i) for i in range(len(objs))}
    taken, out = set(), []
    for i in sorted(nb, key=lambda k: -len(nb[k])):
        if i in taken:
            continue
        members = [j for j in nb[i] if j not in taken]
        if len(members) < min_n:
            continue
        taken.update(members)
        cl = [objs[j] for j in members]
        c = _centre(cl)
        out.append(sorted(cl, key=lambda q: model.dist_km(q, c))[:DEPOT_MAX_OBJECTS])
    return out


def pick_depot(objs: list[dict], radius_km: float = DEPOT_CLUSTER_KM, min_n: int = DEPOT_MIN_OBJECTS) -> list[dict]:
    """Самое плотное скопление объектов: объект, у которого больше всего соседей в radius_km."""
    cl = clusters(objs, radius_km, min_n)
    return cl[0] if cl else []


def _centre(objs: list[dict]) -> dict:
    return {"lat": sum(q["lat"] for q in objs) / len(objs), "lon": sum(q["lon"] for q in objs) / len(objs)}


def _set(target: dict, item: dict, pos: dict, objs: list[dict]) -> None:
    if "units" in target:
        item["pos"] = pos
    else:
        item["lat"], item["lon"] = pos["lat"], pos["lon"]
        item.pop("estimate", None)
    item["pos_checked"] = True
    item["map_objects"] = [o["name"] for o in objs]
    item["map_type"] = ", ".join(sorted({o["type"] for o in objs if o.get("type")}))


def _items(target: dict, role: str) -> list[dict]:
    if "units" in target:
        return [u for u in target["units"].values() if u.get("role") == role]
    return target.get(SECTOR_KEY[role], [])


def _est(target: dict, item: dict) -> dict:
    if "units" in target:
        return item["pos"]
    return item if "lat" in item else target["places"][item["place"]]


def _near(objs: list[dict], p: dict, m: float) -> list[dict]:
    return [o for o in objs if model.dist_km(o, p) * 1000 <= m]


def _bridge_objs(probe_: dict, item: dict, est: dict) -> list[dict] | None:
    if item["id"] in probe_.get("bridges", {}):
        return probe_["bridges"][item["id"]]
    if "bridges_all" not in probe_:
        return None
    near = _near(probe_["bridges_all"], est, BRIDGE_SEARCH_M)
    wet = [o for o in near if o.get("water")]
    return wet or near                          # переправа - мост над водой, если такой рядом есть


def _depot_objs(probe_: dict, item: dict, est: dict) -> list[dict] | None:
    if item["id"] in probe_.get("depot_objects", {}):
        return probe_["depot_objects"][item["id"]]
    if "depot_objects_all" not in probe_:
        return None
    return _near(probe_["depot_objects_all"], est, DEPOT_SEARCH_M)


def _owner(target: dict, place: str) -> str | None:
    return target["places"][place].get("side")


def _add(target: dict, role: str, item: dict) -> None:
    """Новая цель тыла: в сектор - запись, в кампанию - объект, как их создаёт model.new_campaign."""
    if "units" not in target:
        target.setdefault(SECTOR_KEY[role], []).append(item)
        return
    u = {"id": item["id"], "name": item["name"], "side": item.get("side"), "role": role,
         "pos": {"lat": item["lat"], "lon": item["lon"]}, "state": "active", "damage": 0.0, "lost": {}, "composition": [],
         **{k: item[k] for k in ("links", "place", "map_objects", "map_type", "pos_checked", "found", "minor", "supply") if k in item}}
    target["units"][u["id"]] = u


def _pos(target: dict, item: dict) -> dict:
    p = _est(target, item)
    return {"lat": p["lat"], "lon": p["lon"]}


def discover_bridges(target: dict, probe_: dict, roads_: dict | None) -> list[str]:
    """Мост над водой на связи графа, у которой своей переправы ещё нет, - новая цель; закрывает эту связь."""
    if "bridges_all" not in probe_:
        return []
    places, lines = target["places"], []
    wet = [o for o in probe_["bridges_all"] if o.get("water")]
    used = {n for b in _items(target, "bridge") for n in b.get("map_objects", [])}
    for a, b in target.get("links", []):
        if any({a, b} == set(l) for br in _items(target, "bridge") for l in br.get("links", [])):
            continue
        line = link_lines(places, [[a, b]], roads_)[0]
        cand = [(min(_seg_km(o, line[i], line[i + 1]) for i in range(len(line) - 1)), o) for o in wet if o["name"] not in used]
        cand = [(d, o) for d, o in cand if d <= NEW_BRIDGE_LINK_KM]
        if not cand:
            continue
        _, best = min(cand, key=lambda c: c[0])
        old = next((br for br in _items(target, "bridge") if best["name"] in br.get("map_objects", [])
                    or model.dist_km(_pos(target, br), best) <= SPAN_KM), None)
        if old is not None:                       # тот же мост уже цель другой связи - добавить ей и эту связь
            old.setdefault("links", []).append([a, b])
            lines.append(f"{old['name']}: закрывает и связь {a} - {b}.")
            continue
        spans = [o for o in wet if o["type"] == best["type"] and model.dist_km(o, best) <= SPAN_KM]
        item = {"id": f"br_{a}_{b}".lower(), "name": f"Малый мост на пути {a} - {b}", "side": None, "links": [[a, b]],
                "lat": best["lat"], "lon": best["lon"], "found": True, "minor": True}
        _set({"units": {}} if "units" in target else target, item, {"lat": best["lat"], "lon": best["lon"]}, spans)
        item["lat"], item["lon"] = best["lat"], best["lon"]
        _add(target, "bridge", item)
        used |= {o["name"] for o in spans}
        lines.append(f"новый мост: {item['name']} ({best['type']}, пролётов {len(spans)}).")
    return lines


KINDS = {   # роль -> (объекты зонда, радиус скопления, минимум объектов, название)
    "depot": ("depot_objects_all", DEPOT_CLUSTER_KM, DEPOT_MIN_OBJECTS, "Склад"),
    "factory": ("factory_objects_all", FACTORY_CLUSTER_KM, FACTORY_MIN_OBJECTS, "Завод"),
}


def discover_depots(target: dict, probe_: dict, role: str = "depot") -> list[str]:
    """Скопление объектов склада (завода) у пункта без своего склада (завода) - новый объект стороны, владеющей
    пунктом (один на пункт)."""
    key, radius, min_n, title = KINDS[role]
    if key not in probe_:
        return []
    lines, places = [], target["places"]
    known = [_pos(target, d) for d in _items(target, role)]
    have = {d["place"] for d in _items(target, role)}
    lat0 = sum(p["lat"] for p in places.values()) / len(places)
    pxy = [_km_xy(p, lat0) for p in places.values()]
    lim = (NEW_DEPOT_PLACE_KM + 1.0) ** 2
    cand = [o for o in probe_[key] if any((x - px) ** 2 + (y - py) ** 2 <= lim
                                          for (x, y) in [_km_xy(o, lat0)] for px, py in pxy)]   # только у пунктов
    for cl in clusters(cand, radius, min_n):
        c = _centre(cl)
        if any(model.dist_km(c, k) <= NEW_DEPOT_GAP_KM for k in known):
            continue
        pl, d = min(((n, model.dist_km(c, p)) for n, p in places.items()), key=lambda x: x[1])
        side = _owner(target, pl)
        if d > NEW_DEPOT_PLACE_KM or pl in have or side not in model.SIDES:
            continue
        item = {"id": f"{role}_{pl}".lower(), "name": f"{title} ({pl})", "side": side, "place": pl,
                "lat": c["lat"], "lon": c["lon"], "found": True}
        if role == "depot":
            item["supply"] = False               # найденный склад - цель, снабжают только склады сценария (Alex)
        _set({"units": {}} if "units" in target else target, item, c, cl)
        item["lat"], item["lon"] = c["lat"], c["lon"]
        _add(target, role, item)
        have.add(pl)
        known.append(c)
        lines.append(f"новый {title.lower()}: {item['name']} ({side}), объектов {len(cl)} ({item['map_type']}), {d:.1f} км от пункта.")
    return lines


def apply_depots(target: dict, probe_: dict) -> list[str]:
    lines = []
    for d in _items(target, "depot"):
        if d.get("found") or d.get("map_objects"):   # уже на объектах карты - не уточнять снова (иначе точка "плывёт")
            continue
        objs = _depot_objs(probe_, d, _est(target, d))
        if objs is None:
            continue
        cl = pick_depot(objs)
        if not cl:
            lines.append(f"{d['name']}: у пункта нет скопления объектов склада ({', '.join(DEPOT_KEYS)}) - "
                         f"цель остаётся по оценке (Assign as... и map-import).")
            continue
        pos = _centre(cl)
        shift = model.dist_km(_est(target, d), pos) * 1000
        _set(target, d, pos, cl)
        lines.append(f"{d['name']}: {len(cl)} объектов ({d['map_type']}), сдвиг от пункта {shift:.0f} м.")
    return lines


def _props(z) -> dict:
    pr = z.properties or {}
    if isinstance(pr, dict) and all(isinstance(v, dict) for v in pr.values()):
        pr = list(pr.values())
    if isinstance(pr, list):
        return {str(i.get("key", "")).upper(): str(i.get("value", "")) for i in pr if isinstance(i, dict)}
    return {str(k).upper(): str(v) for k, v in pr.items()}


def import_miz(target: dict, miz: Path) -> list[str]:
    """Зоны "Assign as..." из миссии: ROLE = depot|bridge, VALUE = id объекта. Заменяют найденное зондом."""
    m = Mission(Germany())
    m.load_file(str(miz))
    groups: dict[str, list[dict]] = {}
    lines = []
    for z in m.triggers.zones():
        pr = _props(z)
        role, oid = pr.get("ROLE", "").strip().lower(), pr.get("VALUE", "").strip()
        if role not in SECTOR_KEY or not oid:
            continue
        if not pr.get("OBJECT ID"):
            lines.append(f"зона {z.name}: ROLE/VALUE есть, OBJECT ID нет - это не 'Assign as...', пропущена.")
            continue
        ll = z.position.latlng()
        groups.setdefault(f"{role}:{oid}", []).append({"name": pr["OBJECT ID"], "type": pr.get("NAME", ""),
                                                       "lat": ll.lat, "lon": ll.lng})
    for key, objs in groups.items():
        role, oid = key.split(":", 1)
        item = next((i for i in _items(target, role) if i["id"] == oid), None)
        if item is None:
            ids = ", ".join(i["id"] for i in _items(target, role))
            lines.append(f"{oid}: такого объекта ({role}) нет; есть: {ids}.")
            continue
        _set(target, item, _centre(objs), objs)
        lines.append(f"{item['name']}: назначено вручную, объектов {len(objs)} ({item['map_type']}).")
    if "units" in target and groups:
        target["tasks"] = []
    if not groups:
        lines.append("в миссии нет зон 'Assign as...' с ROLE = depot|bridge и VALUE = id объекта.")
    return lines


def apply(target: dict, probe_: dict, roads_: dict | None = None) -> list[str]:
    """target - кампания (state) или сектор (содержимое sector_*.json). Мосты получают точную точку и имена объектов."""
    is_state = "units" in target
    places = target["places"]
    if is_state:
        items = [u for u in target["units"].values() if u.get("role") == "bridge"]
        roads_ = roads_ if roads_ is not None else target.get("roads")
    else:
        items = target.get("bridges", [])
    lines = []
    for b in items:
        if b.get("found") or b.get("map_objects"):   # уже на объектах карты - не уточнять снова (иначе точка "плывёт")
            continue
        est = b["pos"] if is_state else b
        objs = _bridge_objs(probe_, b, est)
        if objs is None:
            continue
        if not objs:
            lines.append(f"{b['name']}: мостов на карте в {BRIDGE_SEARCH_M / 1000:.0f} км нет - цель остаётся по оценке.")
            continue
        best, spans, off = pick_bridge(est, link_lines(places, b["links"], roads_), objs)
        if off > MAX_OFF_LINK_KM:
            lines.append(f"{b['name']}: ближайший мост ({best['type']}) в {off:.1f} км от связи "
                         f"{', '.join('-'.join(l) for l in b['links'])} - не применён, проверить вручную.")
            continue
        shift = model.dist_km(est, best) * 1000
        _set(target, b, {"lat": best["lat"], "lon": best["lon"]}, spans)
        lines.append(f"{b['name']}: {best['type']}, пролётов {len(spans)}, сдвиг от оценки {shift:.0f} м, "
                     f"от линии связи {off * 1000:.0f} м (найдено мостов рядом: {len(objs)}).")
    lines += apply_depots(target, probe_)
    lines += drop_excluded(target)
    lines += discover_bridges(target, probe_, roads_)
    lines += discover_depots(target, probe_)
    lines += discover_depots(target, probe_, "factory")
    if is_state:
        target["tasks"] = []                    # маршруты плана дня посчитаны по старым точкам
    return lines


def summary(probe_: dict) -> str:
    """Что в файле зонда: старый формат (по целям) или весь сектор."""
    if "bridges_all" not in probe_:
        return ("старый формат (только известные цели, без поиска по сектору и без заводов) - "
                "пересоберите 'Зонд карты' и прогоните его в DCS заново")
    wet = sum(1 for o in probe_["bridges_all"] if o.get("water"))
    return (f"мостов {len(probe_['bridges_all'])} (над водой {wet}), объектов складов {len(probe_.get('depot_objects_all', []))}, "
            f"корпусов заводов {len(probe_.get('factory_objects_all', []))}")


def depot_report(probe_: dict, top: int = 12) -> list[str]:
    out = []
    for did, types in probe_["depots"].items():
        items = sorted(types.items(), key=lambda kv: -kv[1]["n"])[:top]
        out.append(f"{did}: " + ", ".join(f"{tp} x{t['n']}" for tp, t in items))
    return out

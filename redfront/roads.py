"""Дороги: геометрия маршрутов берётся у самого DCS.

В pydcs дорожной сети нет. Поэтому дороги спрашиваются у DCS один раз на сектор:
  1. probe()  - служебная миссия; её скрипт (lua/roads_probe.lua) вызывает land.getClosestPointOnRoads и
                land.findPathOnRoads для каждой пары соседних пунктов маршрутов и пишет roads_<сектор>.json;
  2. load()   - файл -> ломаные в широте/долготе по парам "A>B";
  3. apply()  - кладёт ломаные в кампанию (state["roads"]); продвижение частей на марше пересчитывается так,
                чтобы их положение на карте не сдвинулось.
Без файла дорог всё работает, как раньше: маршрут - прямые между пунктами.
"""
from __future__ import annotations

import json
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript
from dcs.mapping import LatLng, Point
from dcs.terrain.germany import Germany
from dcs.translation import String
from dcs.triggers import TriggerStart

from . import model

LUA = Path(__file__).parent / "lua" / "roads_probe.lua"
MIN_STEP_KM = 0.005     # соседние точки ближе 5 м сливаются


def sector_id(sector: str | Path) -> str:
    stem = Path(sector).stem
    return stem[len("sector_"):] if stem.startswith("sector_") else stem


def pairs_from_units(units: list[dict]) -> list[tuple[str, str]]:
    out = []
    for u in units:
        r = u.get("route") or []
        for a, b in zip(r, r[1:]):
            if (a, b) not in out:
                out.append((a, b))
    return out


def probe_script(sector: str, places: dict, pairs: list[tuple[str, str]]) -> str:
    terrain = Germany()
    def p(name):
        q = Point.from_latlng(LatLng(places[name]["lat"], places[name]["lon"]), terrain)
        return q.x, q.y
    items = []
    for a, b in pairs:
        (x1, y1), (x2, y2) = p(a), p(b)
        items.append(f'{{ id = "{a}>{b}", x1 = {x1:.1f}, y1 = {y1:.1f}, x2 = {x2:.1f}, y2 = {y2:.1f} }}')
    return LUA.read_text(encoding="utf-8").replace("@SECTOR@", sector).replace("@PAIRS@", ", ".join(items))


def probe(out_path: Path, sector: str | Path = "sector_hamburg.json", oob: str | Path = "oob_hamburg.json") -> dict:
    """Собрать служебную миссию для сектора. Пары пунктов - из маршрутов состава сил."""
    sec, forces = model.load_json(sector), model.load_json(oob)
    sid = sector_id(sector)
    pairs = pairs_from_units(forces["units"])
    if not pairs and sec.get("links"):          # театр всей карты: части стоят в пунктах - дороги по всем связям графа
        pairs = [tuple(l) for l in sec["links"]]
    if not pairs:
        raise ValueError("в составе сил нет маршрутов - спрашивать у DCS нечего")
    m = Mission(Germany())
    trig = TriggerStart(comment="redfront roads probe")
    trig.add_action(DoScript(String(probe_script(sid, sec["places"], pairs))))   # String(...), не m.string(...)
    m.triggerrules.triggers.append(trig)
    m.set_description_text(f"redfront: служебная миссия дорог для сектора '{sid}'. Запустите (можно наблюдателем), "
                           f"дождитесь сообщения 'дороги записаны' и выйдите. Летать не нужно.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return {"file": str(out_path), "sector": sid, "pairs": [f"{a}>{b}" for a, b in pairs]}


def bundled(sector_id_: str) -> Path | None:
    """Файл дорог из поставки (data/roads_<сектор>.json - зонд, сделанный автором и положенный в проект), если есть."""
    p = model.DATA / f"roads_{sector_id_}.json"
    return p if p.is_file() else None


def load(path: Path) -> dict:
    """Файл зонда -> {"sector", "paths": {"A>B": [{lat, lon}, ...]}, "errors": {...}}."""
    return from_raw(json.loads(Path(path).read_text(encoding="utf-8")))


def from_raw(raw: dict) -> dict:
    """{"paths": {"A>B": [[x, y], ...]}} в координатах карты DCS -> ломаные в широте/долготе.
    Тот же вид пишет и зонд дорог, и хук дебрифа (поле roads - пути, найденные скриптом колонны)."""
    terrain = Germany()
    paths = {}
    for pid, pts in raw.get("paths", {}).items():
        line = []
        for x, y in pts:
            ll = Point(x, y, terrain).latlng()
            q = {"lat": ll.lat, "lon": ll.lng}
            if not line or model.dist_km(line[-1], q) >= MIN_STEP_KM:
                line.append(q)
        if len(line) >= 2:
            paths[pid] = line
    return {"sector": raw.get("sector"), "paths": paths, "errors": raw.get("errors", {})}


ROAD_MAX_RATIO, ROAD_MAX_EXTRA_KM = 2.0, 15.0   # дорога длиннее 2 x прямой + 15 км - крюк DCS, участок - по прямой


def bad_road(state: dict, pid: str, line: list[dict]) -> float | None:
    """Длина дороги участка "A>B", если это крюк (DCS иногда даёт путь по дорогам в сотни км между соседними
    пунктами: 367 км на участке к Кронаху), иначе None."""
    a, b = pid.split(">", 1)
    pl = state.get("places") or {}
    if a not in pl or b not in pl:
        return None
    km = model.route_length_km(line)
    straight = model.dist_km(pl[a], pl[b])
    return km if km > ROAD_MAX_RATIO * straight + ROAD_MAX_EXTRA_KM else None


def sanitize(state: dict) -> list[str]:
    """Убрать из кампании дороги-крюки (bad_road) и пересчитать длины; части на марше остаются на месте карты
    только если вызывающий пересчитает progress (apply). -> строки о выброшенных участках."""
    lines = []
    for pid, line in list((state.get("roads") or {}).items()):
        km = bad_road(state, pid, line)
        if km is not None:
            del state["roads"][pid]
            lines.append(f"Дорога {pid.replace('>', ' - ')}: у DCS {km:.0f} км при "
                         f"{model.dist_km(*(state['places'][x] for x in pid.split('>', 1))):.0f} по прямой - крюк, участок по прямой.")
    state["road_km"] = {k: round(model.route_length_km(v), 2) for k, v in (state.get("roads") or {}).items()}   # для графа (ops)
    return lines


def apply(state: dict, roads: dict, note: bool = True) -> list[str]:
    """Положить дороги в кампанию (без крюков - sanitize). Части на марше остаются в той же точке карты: progress_km
    пересчитывается проекцией их текущего положения на новую геометрию маршрута."""
    marching = [u for u in state["units"].values() if "route" in u]
    before = {u["id"]: model.unit_pos(state, u) for u in marching}
    state["roads"] = {**state.get("roads", {}), **roads["paths"]}
    lines = sanitize(state)
    for u in marching:
        pts = model.route_points(state, u)
        u["progress_km"] = model.project_km(pts, before[u["id"]])
        if len(u["route"]) < 2:                 # часть на месте - маршрута нет, в журнал не пишем
            continue
        used = sum(1 for a, b in zip(u["route"], u["route"][1:]) if f"{a}>{b}" in state["roads"] or f"{b}>{a}" in state["roads"])
        lines.append(f"{u['name']}: участков по дорогам {used} из {len(u['route']) - 1}, "
                     f"длина маршрута {model.route_length_km(pts):.1f} км, пройдено {u['progress_km']:.1f} км.")
    for pid, err in roads.get("errors", {}).items():
        lines.append(f"DCS не нашёл дорогу {pid}: {err} - этот участок остаётся прямой.")
    for ln in lines if note else ():            # из дебрифа note=False: строки пишет в журнал сам дебриф
        model.note(state, ln)
    return lines

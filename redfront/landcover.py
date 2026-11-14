"""Тип поверхности под точкой (лес, вода, застройка) - по растру театра data/landcover/<театр>.png (tools/gen_landcover.py,
ESA WorldCover 2021). Генератор миссии (pydcs) рельефа и леса не знает, скрипты DCS лес не видят - без растра машины
ставятся по геометрии и попадают в лес и в водоёмы.

clear(state, p) - ближайшая к p точка открытой местности (не лес и не вода; застройка - по выбору) в пределах
SNAP_M; snap_group - то же для машин группы (позиции, огневые, склады, ПВО). Колонны на дорогах не трогаются: дорога
через лес - нормально. Нет растра театра или Pillow - точки не меняются.
"""
from __future__ import annotations

import json
import math

from . import model

FOREST, WATER, BUILT = 1, 2, 3
SNAP_M = 1500             # ОЦЕНКА: дальше не сдвигаем (позиция части - в своём районе)
MIN_GAP_M = 25            # машины после сдвига - не друг на друге
_CACHE: dict[str, tuple | None] = {}


def _grid(state: dict):
    th = state.get("theatre") or ""
    if th not in _CACHE:
        try:
            from PIL import Image
            meta = json.loads((model.DATA / "landcover" / f"{th}.json").read_text(encoding="utf-8"))
            im = Image.open(model.DATA / "landcover" / f"{th}.png")
            _CACHE[th] = (meta, im.tobytes(), im.width, im.height)
        except (OSError, ValueError, ImportError):
            _CACHE[th] = None
    return _CACHE[th]


def kind(state: dict, lat: float, lon: float) -> int | None:
    """Класс поверхности: 0 открытая, 1 лес, 2 вода, 3 застройка; нет растра или вне него - None."""
    g = _grid(state)
    if not g:
        return None
    meta, px, w, h = g
    x = int((lon - meta["west"]) / meta["step_lon"])
    y = int((meta["north"] - lat) / meta["step_lat"])
    if not (0 <= x < w and 0 <= y < h):
        return None
    return px[y * w + x]


def bad(state: dict, lat: float, lon: float, avoid=(FOREST, WATER)) -> bool:
    return kind(state, lat, lon) in avoid


def clear(state: dict, p: dict, max_m: float = SNAP_M, avoid=(FOREST, WATER), taken: list | None = None) -> dict:
    """Ближайшая к p точка не на avoid (поиск кольцами шагом в клетку растра) и не ближе MIN_GAP_M к taken; нет такой
    в max_m - p как есть."""
    g = _grid(state)
    if not g:
        return p
    meta = g[0]
    step = max(30.0, meta["step_lat"] * 111_320 * 0.7)

    def ok(q):
        return not bad(state, q["lat"], q["lon"], avoid) and all(
            model.dist_km(q, t) * 1000 >= MIN_GAP_M for t in (taken or ()))
    if ok(p):
        return p
    r = step
    while r <= max_m:
        n = max(8, int(2 * math.pi * r / step))
        for i in range(n):
            q = model.offset(p, 360.0 * i / n, r)
            if ok(q):
                return {**p, "lat": q["lat"], "lon": q["lon"]}
        r += step
    return p


def snap_group(state: dict, grp: dict, avoid=(FOREST, WATER)) -> int:
    """Машины группы (vehicles: lat, lon) - на открытую местность; возвращает, сколько сдвинуто."""
    if not _grid(state):
        return 0
    n, taken = 0, []
    for v in grp.get("vehicles") or []:
        q = clear(state, v, avoid=avoid, taken=taken)
        if (q["lat"], q["lon"]) != (v["lat"], v["lon"]):
            v["lat"], v["lon"] = q["lat"], q["lon"]
            n += 1
        taken.append({"lat": v["lat"], "lon": v["lon"]})
    return n

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


def _shift(state: dict, chunk: list[dict], max_m: float, avoid, taken: list) -> tuple[float, float] | None:
    """Сдвиг (на север м, на восток м) всего звена машин: ближайший, при котором ни одна машина не в avoid и не на
    чужой; нет такого в max_m - тот, где плохих меньше всего (None - и так хорошо)."""
    def bad_n(dn, de):
        n = 0
        for v in chunk:
            q = model.offset(v, 0.0, dn) if dn else v
            q = model.offset(q, 90.0, de) if de else q
            if bad(state, q["lat"], q["lon"], avoid) or any(model.dist_km(q, t) * 1000 < MIN_GAP_M for t in taken):
                n += 1
        return n
    best = (bad_n(0, 0), 0.0, 0.0)
    if best[0] == 0:
        return None
    step = max(30.0, _grid(state)[0]["step_lat"] * 111_320 * 0.7)
    r = step
    while r <= max_m:
        k = max(8, int(2 * math.pi * r / step))
        for i in range(k):
            a = 2 * math.pi * i / k
            dn, de = r * math.cos(a), r * math.sin(a)
            n = bad_n(dn, de)
            if n < best[0]:
                best = (n, dn, de)
                if n == 0:
                    return dn, de
        r += step
    return (best[1], best[2]) if best[1] or best[2] else None


def snap_group(state: dict, grp: dict, avoid=(FOREST, WATER), chunk: int | None = None) -> int:
    """Машины группы (vehicles: lat, lon) - на открытую местность звеньями по chunk машин (взвод боя - целиком, строй
    сохраняется; ПВО, артиллерия - по одной: они и так рассредоточены). Возвращает, сколько машин сдвинуто."""
    if not _grid(state):
        return 0
    vs = grp.get("vehicles") or []
    if chunk is None:
        chunk = 1 if grp.get("kind") in ("sam_site", "gci_site", "ssm_site", "art_site", "sam") else 4
    n, taken = 0, []
    for k in range(0, len(vs), chunk):
        part = vs[k:k + chunk]
        sh = _shift(state, part, SNAP_M, avoid, taken)
        for v in part:
            if sh:
                q = model.offset(model.offset(v, 0.0, sh[0]), 90.0, sh[1])
                v["lat"], v["lon"] = q["lat"], q["lon"]
                n += 1
            taken.append({"lat": v["lat"], "lon": v["lon"]})
    return n

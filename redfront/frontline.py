"""Линия соприкосновения и территории сторон на карте F10 миссии (рисунки редактора миссий, слои Red / Blue).

Тот же расчёт, что в окне программы (web/tactical.js, TAC.front): по пунктам сторон и частям в поле - поле
f = (до ближнего красного) - (до ближнего синего), км; линия соприкосновения - изолинии f = -GAP_KM (красная) и
+GAP_KM (синяя), только там, где пункты или части не дальше MAX_KM; территория стороны - область, где ближе её
пункты и части (и не дальше MAX_KM от них), - лёгкой заливкой. Каждая сторона видит своё: противник - по своей
разведке (туман войны, intel.py), только присутствие - не двигает линию. Пункты - точками с подписями, цели операции
своей стороны - выделены.
"""
from __future__ import annotations

import math

from . import intel, model, ops

COLS = 120              # клеток сетки по долготе (точность ~3-5 км на весь театр; рисунок сглаживается)
PAD_DEG = 0.5
MAX_KM = 45             # ОЦЕНКА (как в окне): дальше от пунктов и частей линия и заливка не рисуются
GAP_KM = 0.6
KM_LAT = 111.32
RED = (200, 16, 46)
BLUE = (31, 79, 191)


def sites(state: dict, side: str) -> list[tuple[float, float, str]]:
    """Пункты сторон и части в поле так, как их видит сторона side (противник - по разведке)."""
    out = [(p["lat"], p["lon"], ops.owner(state, n)) for n, p in state["places"].items() if ops.owner(state, n)]
    fog = side == state.get("player_side")
    for u in state["units"].values():
        if model.category(u) != "ground" or u.get("attached_to") or u["state"] in ("pending", "destroyed"):
            continue
        if fog and u["side"] != side:
            if intel.level(state, u["id"]) in (None, "presence"):
                continue
            pos = intel.known_pos(state, u)
        else:
            pos = model.unit_pos(state, u)
        if pos:
            out.append((pos["lat"], pos["lon"], u["side"]))
    return out


def _grid(pts: list[tuple[float, float, str]]):
    la0 = min(p[0] for p in pts) - PAD_DEG
    la1 = max(p[0] for p in pts) + PAD_DEG
    lo0 = min(p[1] for p in pts) - PAD_DEG
    lo1 = max(p[1] for p in pts) + PAD_DEG
    k = math.cos(math.radians((la0 + la1) / 2))
    rows = max(20, round(COLS * (la1 - la0) / ((lo1 - lo0) * k)))
    lat = [la1 - (la1 - la0) * (j + 0.5) / rows for j in range(rows)]
    lon = [lo0 + (lo1 - lo0) * (i + 0.5) / COLS for i in range(COLS)]
    R = [(p[0] * KM_LAT, p[1] * KM_LAT * k) for p in pts if p[2] == "red"]
    B = [(p[0] * KM_LAT, p[1] * KM_LAT * k) for p in pts if p[2] == "blue"]
    f = [[0.0] * COLS for _ in range(rows)]
    near = [[0.0] * COLS for _ in range(rows)]
    for j in range(rows):
        y = lat[j] * KM_LAT
        for i in range(COLS):
            x = lon[i] * KM_LAT * k
            dr = math.sqrt(min((a - y) ** 2 + (b - x) ** 2 for a, b in R))
            db = math.sqrt(min((a - y) ** 2 + (b - x) ** 2 for a, b in B))
            f[j][i] = dr - db
            near[j][i] = min(dr, db)
    return f, near, lat, lon


def _contour(v: list[list[float]], mask) -> list[list[tuple[float, float]]]:
    """Marching squares: изолиния v = 0 по клеткам (mask(i, j) - клетку рисовать); ломаные в координатах сетки."""
    rows, cols = len(v), len(v[0])
    segs = []
    def edge(i, j, a, b):
        P = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
        (xa, ya), (xb, yb) = P[a], P[b]
        va, vb = v[ya][xa], v[yb][xb]
        t = va / (va - vb) if va != vb else 0.5
        return (xa + (xb - xa) * t, ya + (yb - ya) * t)
    PAIRS = {1: "lt", 2: "tr", 3: "lr", 4: "rb", 6: "tb", 7: "lb", 8: "bl", 9: "bt", 11: "br", 12: "rl", 13: "rt", 14: "tl",
             5: "ltrb", 10: "trbl"}
    E = {"t": (0, 1), "r": (1, 2), "b": (2, 3), "l": (3, 0)}
    for j in range(rows - 1):
        for i in range(cols - 1):
            if not mask(i, j):
                continue
            c = (v[j][i] > 0) | (v[j][i + 1] > 0) << 1 | (v[j + 1][i + 1] > 0) << 2 | (v[j + 1][i] > 0) << 3
            if c in (0, 15):
                continue
            pr = PAIRS[c]
            for q in range(0, len(pr), 2):
                segs.append((edge(i, j, *E[pr[q]]), edge(i, j, *E[pr[q + 1]])))
    # склейка отрезков в ломаные по общим концам
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    ends: dict = {}
    for n, s in enumerate(segs):
        for p in s:
            ends.setdefault(key(p), []).append(n)
    used = [False] * len(segs)
    lines = []
    for n in range(len(segs)):
        if used[n]:
            continue
        used[n] = True
        line = list(segs[n])
        for grow_front in (False, True):
            while True:
                tip = line[0] if grow_front else line[-1]
                nxt = next((m for m in ends.get(key(tip), []) if not used[m]), None)
                if nxt is None:
                    break
                used[nxt] = True
                a, b = segs[nxt]
                p = b if key(a) == key(tip) else a
                if grow_front:
                    line.insert(0, p)
                else:
                    line.append(p)
        lines.append(line)
    return [l for l in lines if len(l) >= 3]


def _chaikin(line: list[tuple[float, float]], closed: bool = False) -> list[tuple[float, float]]:
    out = [] if closed else [line[0]]
    n = len(line)
    for k in range(n if closed else n - 1):
        (x0, y0), (x1, y1) = line[k], line[(k + 1) % n]
        out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
    if not closed:
        out.append(line[-1])
    return out


def compute(state: dict, side: str) -> dict:
    """Линии (красная, синяя) и территория стороны side в широте/долготе."""
    pts = sites(state, side)
    if not any(p[2] == "red" for p in pts) or not any(p[2] == "blue" for p in pts):
        return {"red": [], "blue": [], "own": []}
    f, near, lat, lon = _grid(pts)
    rows = len(lat)
    def ll(line):
        def one(x, y):
            j, i = min(rows - 1.0, max(0.0, y)), min(COLS - 1.0, max(0.0, x))
            j0, i0 = int(j), int(i)
            la = lat[j0] + (lat[min(rows - 1, j0 + 1)] - lat[j0]) * (j - j0)
            lo = lon[i0] + (lon[min(COLS - 1, i0 + 1)] - lon[i0]) * (i - i0)
            return {"lat": la, "lon": lo}
        return [one(x, y) for x, y in line]
    near_ok = lambda i, j: near[j][i] <= MAX_KM
    iso = lambda lvl: [ll(_chaikin(_chaikin(l))) for l in _contour([[x - lvl for x in r] for r in f], near_ok)]
    sgn = 1 if side == "red" else -1             # своя сторона: внутри области - отрицательно (f < 0 - красные)
    own = [[max(sgn * f[j][i], near[j][i] - MAX_KM) for i in range(COLS)] for j in range(rows)]
    terr = [ll(_chaikin(l, closed=True)) for l in _contour(own, lambda i, j: True) if len(l) >= 4]
    return {"red": iso(-GAP_KM), "blue": iso(GAP_KM), "own": terr}


def draw(m, state: dict, to_point) -> int:
    """Рисунки на карте F10: для каждой стороны - на своём слое. to_point(dict) -> dcs Point. Возвращает число фигур."""
    from dcs.drawing.drawings import StandardLayer
    from dcs.drawing.drawing import Rgba
    from dcs.mapping import Point
    n = 0
    for side, layer_id in (("red", StandardLayer.Red), ("blue", StandardLayer.Blue)):
        layer = m.drawings.get_layer(layer_id)
        fr = compute(state, side)
        own_col = RED if side == "red" else BLUE
        def rel(pts):
            p0 = to_point(pts[0])
            out = []
            for p in pts:
                q = to_point(p)
                out.append(Point(q.x - p0.x, q.y - p0.y, m.terrain))
            return p0, out
        for poly in fr["own"]:                   # своя территория - лёгкой заливкой, без контура
            p0, rp = rel(poly)
            layer.add_freeform_polygon(p0, rp, color=Rgba(*own_col, 0), fill=Rgba(*own_col, 28), line_thickness=0)
            n += 1
        for key, col in (("red", RED), ("blue", BLUE)):
            for line in fr[key]:
                p0, rp = rel(line)
                layer.add_line_segments(p0, rp, color=Rgba(*col, 230), line_thickness=6)
                n += 1
        objs = (state.get("objectives") or {}).get(side) or []
        if isinstance(objs, str):
            objs = [objs]
        if isinstance(objs, dict):
            objs = [o for l in objs.values() for o in l]
        for name, p in state["places"].items():  # пункты: точка с подписью; цели операции стороны - выделены
            own = ops.owner(state, name)
            col = RED if own == "red" else BLUE if own == "blue" else (90, 90, 90)
            q = to_point(p)
            goal = name in objs and own != side
            layer.add_circle(q, 900 if goal else 450, color=Rgba(20, 20, 20, 255), fill=Rgba(*col, 200),
                             line_thickness=4 if goal else 2)
            layer.add_text_box(Point(q.x + 900, q.y + 900, m.terrain), ("◎ " if goal else "") + name,
                               color=Rgba(20, 20, 20, 255), fill=Rgba(255, 255, 255, 120 if goal else 0),
                               font_size=14 if goal else 10, border_thickness=0)
            n += 2
    return n

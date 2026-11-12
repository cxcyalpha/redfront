"""Проекция реального театра на карту DCS с сохранением расстояний (условная география с настоящей глубиной).

Реальные координаты (широта, долгота) -> точка карты: смещение в км от центра реального театра, умноженное на
масштаб s, откладывается от центра суши карты. Масштаб - наибольший (не больше S_MAX), при котором театр с
аэродромами тыла помещается в сушу карты (LAND). Расстояния и направления театра сохраняются с точностью до s:
аэродромы тыла - на реальном удалении (сотни км), а не в 30 км от фронта.

Аэродромы: для реального аэродрома - ближайший к его проекции аэродром карты (не вертолётная площадка, с местами
для самолётов), каждый один раз.
"""
from __future__ import annotations

import math

S_MAX = 0.95
LAND = {"germany": {"lat": (49.45, 53.95), "lon": (6.7, 14.5), "center": (51.7, 10.6)}}


def _km(a, b):
    """Смещение b от a в км: (север, восток)."""
    return (b[0] - a[0]) * 111.32, (b[1] - a[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))


class Proj:
    def __init__(self, theatre: str, real_points: list[tuple[float, float]], s_max: float = S_MAX):
        land = LAND[theatre]
        la = [p[0] for p in real_points]
        lo = [p[1] for p in real_points]
        self.c_real = ((min(la) + max(la)) / 2, (min(lo) + max(lo)) / 2)
        h_real = (max(la) - min(la)) * 111.32
        w_real = (max(lo) - min(lo)) * 111.32 * math.cos(math.radians(self.c_real[0]))
        h_map = (land["lat"][1] - land["lat"][0]) * 111.32
        w_map = (land["lon"][1] - land["lon"][0]) * 111.32 * math.cos(math.radians(land["center"][0]))
        self.s = min(s_max, h_map / max(h_real, 1.0), w_map / max(w_real, 1.0))
        self.c_map = land["center"]
        self.land = land

    def __call__(self, lat: float, lon: float) -> tuple[float, float]:
        n, e = _km(self.c_real, (lat, lon))
        mla = self.c_map[0] + self.s * n / 111.32
        mlo = self.c_map[1] + self.s * e / (111.32 * math.cos(math.radians(mla)))
        mla = min(max(mla, self.land["lat"][0]), self.land["lat"][1])
        mlo = min(max(mlo, self.land["lon"][0]), self.land["lon"][1])
        return round(mla, 4), round(mlo, 4)


def affine(src: list[tuple[float, float]], dst: list[tuple[float, float]]):
    """Аффинное преобразование по точкам (наименьшие квадраты): старые условные координаты -> новые."""
    import numpy as np
    A = np.array([[a, b, 1.0] for a, b in src])
    X = np.linalg.lstsq(A, np.array(dst), rcond=None)[0]
    return lambda la, lo: tuple(round(float(v), 4) for v in np.array([la, lo, 1.0]) @ X)


def airfields(terrain, wanted: dict, proj: Proj, min_slots: int = 8) -> dict:
    """{ключ: (широта, долгота) реального аэродрома} -> {ключ: имя аэродрома карты}."""
    cand = {}
    for n, a in terrain.airports.items():
        if n.startswith(("H ", "Airracing")):
            continue
        if sum(1 for s in a.parking_slots if s.airplanes) < min_slots:
            continue
        p = a.position.latlng()
        cand[n] = (p.lat, p.lng)
    out, used = {}, set()
    for k, (la, lo) in wanted.items():
        mp = proj(la, lo)
        best = min((n for n in cand if n not in used), key=lambda n: sum(x * x for x in _km(mp, cand[n])))
        used.add(best)
        out[k] = best
    return out


def apply(G, real_places: dict, real_airbases: dict, bbox_extra: tuple = (), far: tuple = ()) -> Proj:
    """Перенос сценария gen_caucasus (модуль G) на проекцию реального театра: пункты - из real_places
    ({имя: (широта, долгота)}; сторона - прежняя), ЗРК, станции РЭБ, пусковые - аффинным преобразованием старых
    условных координат в новые (по пунктам), мосты - середины своих связей, аэродромы - ближайшие к проекции
    реальных (real_airbases: {прежнее имя аэродрома карты: (широта, долгота) реального}). bbox_extra - точки,
    которые тоже должны поместиться; far - пункты и аэродромы глубокого тыла вне масштаба (у края суши карты)."""
    from dcs.terrain.germany import Germany
    pts = [real_places[n] for n in G.PLACES if n not in far] + [real_airbases[k] for k in real_airbases if k not in far] + list(bbox_extra)
    P = Proj(G.THEATRE, pts)
    old = dict(G.PLACES)
    G.PLACES = {n: (*P(*real_places[n]), side) for n, (_la, _lo, side) in old.items()}
    f = affine([old[n][:2] for n in old], [G.PLACES[n][:2] for n in old])
    G.SAMS = [(*r[:5], *f(r[5], r[6])) + tuple(r[7:]) for r in G.SAMS]
    G.EW = [(*r[:5], *f(r[5], r[6])) + tuple(r[7:]) for r in G.EW]
    G.SSM = [(*r[:5], *f(r[5], r[6])) + tuple(r[7:]) for r in G.SSM]
    for b in G.BRIDGES:
        a_, c_ = (G.PLACES[x] for x in b["links"][0])
        b["lat"], b["lon"] = round((a_[0] + c_[0]) / 2, 4), round((a_[1] + c_[1]) / 2, 4)
    names = airfields(Germany(), real_airbases, P)
    G.AIRBASES = {s: [names.get(n, n) for n in ns] for s, ns in G.AIRBASES.items()}
    G.AIR = [r[:5] + (names.get(r[5], r[5]),) + tuple(r[6:]) for r in G.AIR]
    G.EXTERNAL_SUPPLY = {names.get(n, n) for n in G.EXTERNAL_SUPPLY}
    G.FRONT_KM = 120                             # пункты в реальном масштабе редкие - линия фронта рисуется дальше от них
    G.PROJ_NOTE = (f"масштаб {P.s:.2f} от реального (расстояния театра сохранены), аэродромы карты - ближайшие к "
                   "проекции реальных: " + ", ".join(f"{names[k]}" for k in real_airbases))
    return P

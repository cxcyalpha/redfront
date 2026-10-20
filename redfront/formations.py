"""Боевые порядки частей в бою по доктрине стороны (расстановка машин в миссии DCS).

Часть в бою делится на роты по COMPANY машин (машины раздаются по ротам по кругу - в каждой роте и танки, и БМП;
танки - в первой линии роты). Схемы - ОЦЕНКИ по смыслу уставов, расстояния ужаты под бюджет машин миссии:

* ОВД ("Боевой устав сухопутных войск", 1982-1989; Г.А. Ионин, "Тактика", 1987):
  - оборона: ротные опорные пункты, две трети рот - в первом эшелоне по фронту, треть - во втором (DEPTH_M позади);
    во взводах машины линией, БМП за танками;
  - наступление: роты линией в первом эшелоне по фронту ATTACK_FRONT_M на роту, танки в линии впереди, БМП в
    WP_IFV_BEHIND_M за танками; треть рот - второй эшелон (резерв) позади.
* НАТО (FM 71-1 Tank and Mechanized Infantry Company Team, 1988; FM 71-2 The Tank and Mechanized Infantry Battalion
  Task Force, 1988):
  - оборона: ротные тактические группы на позициях (battle positions) уступом: соседние позиции - вперёд и назад на
    NATO_STAGGER_M, интервал NATO_BP_M; в позиции машины дугой, интервал NATO_GAP_M;
  - наступление: ведущая ротная группа клином (wedge), остальные - позади уступом (overwatch: прикрывают огнём).
Прочие доктрины - прежняя схема: ряды по 10 машин.

Смещения - (вперёд к противнику, вправо), метры от центра боевого порядка.
"""
from __future__ import annotations

import math

COMPANY = 10            # ОЦЕНКА: машин на роту в миссии (рота: 10-13 машин; бюджет машин миссии)
DEPTH_M = 1500          # ОЦЕНКА: второй эшелон за первым
DEF_FRONT_M = 1000      # ОЦЕНКА: фронт ротного опорного пункта
ATTACK_FRONT_M = 700    # ОЦЕНКА: фронт наступления роты
WP_GAP_M = 90           # ОЦЕНКА: интервал машин в линии
WP_IFV_BEHIND_M = 150   # ОЦЕНКА: БМП за танками
NATO_BP_M = 1400        # ОЦЕНКА: интервал между позициями ротных групп
NATO_STAGGER_M = 600    # ОЦЕНКА: уступ позиций в глубину
NATO_GAP_M = 120        # ОЦЕНКА: интервал машин на позиции
LEGACY_WIDTH, LEGACY_SPACING, LEGACY_ROW = 10, 80, 150


def _companies(n: int) -> list[list[int]]:
    """Индексы машин по ротам: по кругу (порядок машин - танки первыми, значит и в роте танки первыми)."""
    k = max(1, math.ceil(n / COMPANY))
    out: list[list[int]] = [[] for _ in range(k)]
    for i in range(n):
        out[i % k].append(i)
    return out


def _echelons(k: int) -> tuple[int, int]:
    """Рот в первом и втором эшелоне: при трёх и больше - треть во втором."""
    second = k // 3 if k >= 3 else 0
    return k - second, second


def _line(m: int, gap: float) -> list[float]:
    return [(j - (m - 1) / 2) * gap for j in range(m)]


def layout(doctrine: str, posture: str, n: int, roles: list[str] | None = None) -> list[tuple[float, float]]:
    """Смещения n машин (вперёд, вправо), м. posture: 'defend' или 'attack'. roles - роль каждой машины
    (tank, ifv, ...) по порядку - для линии танков и БМП за ними у ОВД."""
    if n <= 0:
        return []
    roles = roles or [""] * n
    out: list[tuple[float, float] | None] = [None] * n
    comps = _companies(n)
    first, second = _echelons(len(comps))
    if doctrine == "wp":
        front = DEF_FRONT_M if posture == "defend" else ATTACK_FRONT_M
        centres = [(0.0, y) for y in _line(first, front)] + [(-DEPTH_M, y) for y in _line(second, front)]
        for (fx, fy), idx in zip(centres, comps):
            tanks = [i for i in idx if roles[i] in ("tank", "MBT")]
            rest = [i for i in idx if roles[i] not in ("tank", "MBT")]
            if not tanks or not rest:            # одного рода - две линии взводов
                tanks, rest = idx[:math.ceil(len(idx) / 2)], idx[math.ceil(len(idx) / 2):]
            for row, grp in ((0.0, tanks), (-WP_IFV_BEHIND_M, rest)):
                for i, y in zip(grp, _line(len(grp), WP_GAP_M)):
                    out[i] = (fx + row, fy + y)
    elif doctrine == "nato":
        if posture == "defend":                  # позиции уступом; машины дугой, края позиции выдвинуты вперёд
            ys = _line(len(comps), NATO_BP_M)
            for k, (y0, idx) in enumerate(zip(ys, comps)):
                x0 = 0.0 if k % 2 == 0 else -NATO_STAGGER_M
                for j, i in enumerate(idx):
                    y = (j - (len(idx) - 1) / 2) * NATO_GAP_M
                    out[i] = (x0 + abs(y) * 0.35, y0 + y)
        else:                                    # ведущая группа клином, остальные - уступом позади (overwatch)
            for k, idx in enumerate(comps):
                if k == 0:
                    x0, y0 = 0.0, 0.0
                else:
                    side = 1 if k % 2 else -1
                    x0, y0 = -NATO_STAGGER_M * ((k + 1) // 2), side * NATO_BP_M * ((k + 1) // 2) / 1.5
                for j, i in enumerate(idx):
                    r = (j + 1) // 2
                    y = r * NATO_GAP_M * (1 if j % 2 else -1)
                    out[i] = (x0 - r * NATO_GAP_M * 0.7, y0 + y)
    else:
        for i in range(n):
            row, col = divmod(i, LEGACY_WIDTH)
            out[i] = (-row * LEGACY_ROW, (col - (LEGACY_WIDTH - 1) / 2) * LEGACY_SPACING)
    return [p if p is not None else (0.0, 0.0) for p in out]

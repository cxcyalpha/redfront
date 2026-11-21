"""Мораль и сплочённость манёвренных частей (u['morale'], 0..1; нет поля - 1.0). Все числа - ОЦЕНКИ.

Мораль - не выучка (quality): выучка постоянна, мораль меняется по ходу боёв:
  * падает от потерь за сутки (LOSS_K x доля потерянной техники), в окружении без подвоза (CUT_PER_DAY; гарнизон
    города - вдвое меньше), при разгроме и отходе под ударом (ROUT_HIT), при надломе стороны (ops.morale);
  * растёт в покое - в обороне без боя и на восстановлении (REST_PER_DAY), при успехе - занят пункт рядом (WIN_GAIN).
Влияние: сила в бою x power_k (от POWER_FLOOR при нулевой морали до 1), отход раньше (withdraw_shift), разгром при
меньшем перевесе (rout_k). Ниже SHAKEN - часть "надломлена" (сообщение в журнал).
"""
from __future__ import annotations

from . import model

LOSS_K = 1.5          # мораль минус 1.5 x доля техники, потерянной за сутки (10% потерь - минус 0.15)
CUT_PER_DAY = 0.06    # в окружении без подвоза - в сутки
ROUT_HIT = 0.15       # разгром, отход под ударом
REST_PER_DAY = 0.08   # в покое (оборона без боя, восстановление) - в сутки
WIN_GAIN = 0.05       # пункт занят своей частью рядом
POWER_FLOOR = 0.6     # сила при нулевой морали - 60% (сплочённость, а не техника)
SHAKEN = 0.4          # ниже - "надломлена"
WITHDRAW_SHIFT = 0.25  # при нулевой морали отход - на столько раньше по боеспособности


def get(u: dict) -> float:
    return float(u.get("morale", 1.0))


def power_k(u: dict) -> float:
    return POWER_FLOOR + (1.0 - POWER_FLOOR) * get(u)


def withdraw_shift(u: dict) -> float:
    return WITHDRAW_SHIFT * (1.0 - get(u))


def rout_k(u: dict) -> float:
    """Множитель порога разгрома (ops.ROUT_RATIO): надломленная часть бежит при меньшем перевесе."""
    return max(0.35, get(u))


def hit(state: dict, u: dict, k: float, why: str = "") -> list[str]:
    """Удар по морали (разгром, надлом стороны): минус k; строка - когда часть надломлена впервые."""
    was = get(u)
    u["morale"] = round(max(0.0, was - k), 3)
    if was >= SHAKEN > u["morale"]:
        return [f"{u['name']}: мораль надломлена ({u['morale']:.0%})" + (f" - {why}" if why else "") + "."]
    return []


def daily(state: dict, start: dict) -> list[str]:
    """Сутки: потери (start - боеспособность на начало суток), окружение, отдых, успех рядом."""
    from . import ops
    lines = []
    took = {p for p, o in (state.get("_day_owner") or {}).items() if state["places"].get(p, {}).get("side") not in (None, o)}
    for u in ops._maneuver(state):
        if u.get("attached_to") or u["state"] == "destroyed":
            continue
        m0 = get(u)
        m = m0
        lost = max(0.0, start.get(u["id"], model.strength(u)) - model.strength(u))
        m -= LOSS_K * lost
        if u.get("supply_frac", 1.0) <= 0 and u.get("supply", 1.0) < 1.0:   # без подвоза (окружение, отрезан)
            m -= CUT_PER_DAY * (0.5 if u.get("order") == "garrison" else 1.0)
        if u["state"] in ("refit",) or (u["state"] == "defend" and not u.get("engaged") and lost < 0.01):
            m += REST_PER_DAY
        side_took = [p for p in took if state["places"][p].get("side") == u["side"]]
        if any(model.dist_km(model.unit_pos(state, u), state["places"][p]) <= 15 for p in side_took):
            m += WIN_GAIN
        m = round(min(1.0, max(0.0, m)), 3)
        if abs(m - m0) > 1e-9 or "morale" in u:
            u["morale"] = m
        if m0 >= SHAKEN > m:
            lines.append(f"{u['name']}: мораль надломлена ({m:.0%}) - потери и бои без отдыха.")
        elif m0 < SHAKEN <= m:
            lines.append(f"{u['name']}: мораль восстановлена ({m:.0%}).")
    return lines

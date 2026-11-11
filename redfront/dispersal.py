"""Рассредоточение авиации (ОЦЕНКИ): частое перебазирование и посадка не на аэродроме вылета.

ВВС Украины с 2022 года уводят самолёты из-под ударов ракетами: часть пар после задания садится на другой аэродром
(по интервью лётчиков - не в каждом вылете, но часто), части каждые несколько суток меняют аэродром. Настройка -
в составе сил сценария (dispersal: {сторона: {...}}):
  * land_other_p - доля вылетов группы с посадкой на другом своём аэродроме (в миссии - точка посадки там);
  * rebase_p - вероятность за сутки, что авиачасть перебазируется на другой свой аэродром (в конце суток; приказ
    командующего важнее - его не трогаем);
  * max_km - не дальше от прежнего аэродрома;
  * protect - защита рассредоточением (по умолчанию PROTECT): самолётов на земле под ударом по аэродрому - меньше
    (ground_losses), повреждение аэродрома меньше снижает вылеты (sortie_damage) - самолёты на запасных площадках,
    рулёжках и дорогах.

Удар по аэродрому (ракеты - strategic.resolve, авиация ИИ - airwar) уничтожает самолёты на стоянках: доля - прирост
повреждения x GROUND_K x (1 - защита). Считается только в сценариях с рассредоточением (dispersal задан): сторона без него теряет полную долю. В
сценариях 80-х (укреплённые укрытия НАТО и ОВД) потерь на земле в модели нет.
"""
from __future__ import annotations

import random

from . import model


def _rng(state: dict, purpose: str) -> random.Random:
    """Случайность сценария; выключена - всё равно повторяемая по кампании (рассредоточение - часть доктрины)."""
    return model.rng(state, purpose) or random.Random(f"{state.get('campaign_id')}-{state['day']}-{purpose}")


GROUND_K = 1.0     # ОЦЕНКА: доля самолётов части на стоянках, гибнущая при полном (1.0) приросте повреждения аэродрома
PROTECT = 0.8      # ОЦЕНКА: рассредоточение - самолётов под ударом в 5 раз меньше (24.02.2022: удары по аэродромам
                   # Украины уничтожили немного самолётов - их увели заранее)
SORTIE_PROTECT = 0.5   # ОЦЕНКА: повреждение аэродрома меньше снижает вылеты (взлёт с запасных площадок)


def protect(state: dict, side: str) -> float:
    c = cfg(state, side)
    return c.get("protect", PROTECT) if c else 0.0


def sortie_damage(state: dict, unit: dict, dmg: float) -> float:
    """Повреждение аэродрома для числа вылетов части: при рассредоточении - меньше."""
    return dmg * (1.0 - SORTIE_PROTECT * protect(state, unit.get("side", ""))) if dmg else dmg


def ground_losses(state: dict, af: dict, gain: float, why: str) -> list[str]:
    """Самолёты частей аэродрома af, уничтоженные на земле приростом повреждения gain (0..1)."""
    if gain <= 0 or not state.get("dispersal"):   # только в сценариях с рассредоточением (в 80-х - укрытия, не считаем)
        return []
    lines = []
    bid = af.get("base") or af["id"].removeprefix("af_")
    for u in state["units"].values():
        if u.get("base") != bid or model.category(u) != "air" or u.get("count", 0) <= 0:
            continue
        exp = u["count"] * gain * GROUND_K * (1.0 - protect(state, u["side"]))
        r = _rng(state, f"ground-{u['id']}-{why}-{af.get('damage', 0):.3f}")
        n = int(exp) + (1 if r.random() < exp - int(exp) else 0)
        n = min(n, u["count"])
        if n:
            u["count"] -= n
            lines.append(f"{u['name']}: уничтожено на земле {n} ({why}).")
    return lines


def cfg(state: dict, side: str) -> dict:
    return (state.get("dispersal") or {}).get(side) or {}


def _options(state: dict, u: dict, from_bid: str, max_km: float) -> list[str]:
    cur = state["airbases"][from_bid]
    out = []
    for bid, b in state["airbases"].items():
        if (bid == from_bid or b.get("side") != u["side"] or b.get("kind") in ("farp", "carrier") or not b.get("airport")
                or b.get("state", "open") not in ("open", "active") or "lat" not in b):
            continue
        if model.dist_km(cur, b) <= max_km:
            out.append(bid)
    return sorted(out)


def land_other(state: dict, u: dict, key: str) -> str | None:
    """Аэродром посадки группы не на базе вылета (или None - домой)."""
    c = cfg(state, u["side"])
    if not c.get("land_other_p") or model.category(u) != "air":
        return None
    r = _rng(state, f"disperse-{key}")
    if r.random() >= c["land_other_p"]:
        return None
    opts = _options(state, u, u["base"], c.get("max_km", 300))
    return r.choice(opts) if opts else None


def daily(state: dict) -> list[str]:
    """Конец суток: авиачасти стороны с рассредоточением меняют аэродром (приказ на завтра)."""
    lines = []
    for u in state["units"].values():
        c = cfg(state, u.get("side", ""))
        if not c.get("rebase_p") or model.category(u) != "air" or u.get("rebase_to") or u.get("count", 0) <= 0:
            continue
        r = _rng(state, f"rebase-{u['id']}")
        if r.random() >= c["rebase_p"]:
            continue
        opts = _options(state, u, u["base"], c.get("max_km", 300))
        if opts:
            u["rebase_to"] = r.choice(opts)
            lines.append(f"{u['name']}: рассредоточение - перебазирование на {state['airbases'][u['rebase_to']]['name']}.")
    return lines

"""Рассредоточение авиации (ОЦЕНКИ): частое перебазирование и посадка не на аэродроме вылета.

ВВС Украины с 2022 года уводят самолёты из-под ударов ракетами: часть пар после задания садится на другой аэродром
(по интервью лётчиков - не в каждом вылете, но часто), части каждые несколько суток меняют аэродром. Настройка -
в составе сил сценария (dispersal: {сторона: {...}}):
  * land_other_p - доля вылетов группы с посадкой на другом своём аэродроме (в миссии - точка посадки там);
  * rebase_p - вероятность за сутки, что авиачасть перебазируется на другой свой аэродром (в конце суток; приказ
    командующего важнее - его не трогаем);
  * max_km - не дальше от прежнего аэродрома.
"""
from __future__ import annotations

import random

from . import model


def _rng(state: dict, purpose: str) -> random.Random:
    """Случайность сценария; выключена - всё равно повторяемая по кампании (рассредоточение - часть доктрины)."""
    return model.rng(state, purpose) or random.Random(f"{state.get('campaign_id')}-{state['day']}-{purpose}")


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

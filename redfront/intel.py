"""Туман войны (пока - позиции ЗРК противника): игрок знает не где ЗРК стоит, а где его видели последний раз.

state['intel'][id] = {'pos', 'day'} - последнее известное положение самостоятельной позиции ЗРК и КРУ противника
(приданная ПВО идёт со своей частью, объектовая не двигается - их положение известно). В начале кампании известны все
(разведка мирного времени). После вылета - позиции ЗРК противника в миссии не дальше SEEN_KM от маршрутов пакета игрока
уточнены (видели на СПО, глазами). ЗРК сменил позицию (samroam.py) - игрок этого не знает, пока снова не увидит.

По известным позициям: карта окна, угрозы в коридоре и рубежи подавления ПВО в задачах игрока (planner). Миссия ставит
ЗРК туда, где он на самом деле: сменивший позицию ЗРК может оказаться не там, где его ждут.
Противник планирует по настоящим позициям наших ЗРК (туман - только для игрока).
"""
from __future__ import annotations

from . import model

STALE_DAYS = 2      # ОЦЕНКА: данные старше - "уточнить" (на карте - бледно, пунктиром)
SEEN_KM = 60        # ОЦЕНКА: ЗРК не дальше этого от маршрутов пакета игрока - видели в вылете (СПО, визуально)


def tracked(state: dict, u: dict) -> bool:
    return (u["side"] != state["player_side"] and model.category(u) in ("sam", "gci") and not u.get("attached_to")
            and not u.get("fixed") and "pos" in u)


def ensure(state: dict) -> None:
    intel = state.setdefault("intel", {})
    for u in state["units"].values():
        if tracked(state, u) and u["id"] not in intel and u["state"] != "pending":
            intel[u["id"]] = {"pos": dict(u["pos"]), "day": state["day"]}


def known_pos(state: dict, u: dict) -> dict:
    """Где игрок думает, что часть стоит (для своих и неотслеживаемых - где стоит)."""
    if tracked(state, u):
        rec = (state.get("intel") or {}).get(u["id"])
        if rec:
            return rec["pos"]
    return model.unit_pos(state, u)


def seen(state: dict, uid: str) -> None:
    u = state["units"].get(uid)
    if u and tracked(state, u):
        state.setdefault("intel", {})[uid] = {"pos": dict(u["pos"]), "day": state["day"]}


def after_debrief(state: dict, man: dict) -> list[str]:
    """Позиции ЗРК противника, бывших в миссии игрока, уточнены."""
    from . import planner
    lines = []
    legs = []                                    # видели - кто не дальше SEEN_KM от маршрутов пакета игрока
    for pg in (state.get("task") or {}).get("package") or []:
        pts = [state["airbases"][pg["base"]]] + list(pg["route"])
        legs += list(zip(pts, pts[1:]))
    for g in man.get("ground") or []:
        u = state["units"].get(g["unit"])
        if not u or not tracked(state, u):
            continue
        if legs and min(planner._seg_dist_km(u["pos"], a, b) for a, b in legs) > SEEN_KM:
            continue
        old = (state.get("intel") or {}).get(u["id"])
        if old and model.dist_km(old["pos"], u["pos"]) > 0.5:
            lines.append(f"Разведка: {u['name']} - новая позиция ({model.dist_km(old['pos'], u['pos']):.0f} км от известной).")
        seen(state, u["id"])
    return lines

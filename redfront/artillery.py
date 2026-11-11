"""Артиллерия как род войск (ОЦЕНКИ): артиллерийские бригады и полки (роль art_bde, категория art_site).

Батарея при каждой части (materialize.artillery) - огонь в её бою; артбригада - огонь по бою любой своей части в
досягаемости орудий:
  * поддержка: сила своей части в бою x (1 + SUPPORT_K x боеспособность бригады x обеспеченность снарядами ammo_k)
    по каждой бригаде в досягаемости, не больше MAX_K в сумме (огонь на один участок не складывается без конца);
  * контрбатарейная борьба: бригады противника в досягаемости друг друга теряют орудия каждые сутки
    (CB_LOSS x боеспособность противника x его cb_k - разведка, РЛС AN/TPQ-36/37, Зоопарк; не больше CB_MAX; не
    дальше CB_RANGE_KM); ремонт и пополнение - REPAIR в сутки;
  * позиция: каждые сутки - за своей частью, которую бригада поддерживает (supports), или за ближней своей частью
    в бою - BEHIND_KM в сторону своего тыла (пункта подвоза);
  * цель разведки и ударов (задача strike_art), в миссии - группой орудий; рядом с вылетом - огонь по ближней части
    противника в досягаемости (FireAtPoint, build).
"""
from __future__ import annotations

from . import model

# досягаемость, км (ОЦЕНКИ по открытым данным; обычные снаряды, без активно-реактивных и Excalibur)
RANGE_KM = {"SAU_Msta": 25, "SAU_Akatsia": 18, "SAU_Gvozdika": 15, "SAU_2_C9": 9, "M_109": 22, "SpGH_Dana": 20,
            "L118_Unit": 17, "Grad_URAL": 20, "Uragan_BM_27": 35, "Smerch": 70, "Smerch_HE": 70, "MLRS": 32,
            "CHAP_TOS1A": 6, "T155_Firtina": 30, "PLZ05": 30}
SUPPORT_K = 0.25     # ОЦЕНКА: прибавка к силе части от бригады в полном составе с полным боекомплектом
MAX_K = 0.45         # ОЦЕНКА: предел прибавки от всех бригад
CB_LOSS = 0.02       # ОЦЕНКА: доля орудий в сутки от контрбатарейного огня одной бригады противника
CB_MAX = 0.05
CB_RANGE_KM = 30.0   # ОЦЕНКА: глубина контрбатарейной разведки (РЛС, беспилотники) - дальше огонь не наводится
REPAIR = 0.015       # ОЦЕНКА: доля штата в сутки из ремонта и пополнения
BEHIND_KM = 10.0     # ОЦЕНКА: огневые позиции за своей частью
MIN_STRENGTH = 0.2


def is_art(u: dict) -> bool:
    return model.category(u) == "art_site"


def range_km(u: dict) -> float:
    alive = model.alive_by_type(u)
    rs = [RANGE_KM.get(t, 15) for t, n in alive.items() if n > 0]
    return max(rs) if rs else 0.0


def working(state: dict, side: str) -> list[dict]:
    return [u for u in state["units"].values() if u.get("side") == side and is_art(u)
            and u.get("state") not in ("destroyed", "pending") and model.strength(u) >= MIN_STRENGTH]


def support_k(state: dict, unit: dict) -> float:
    """Множитель силы части в бою от артбригад своей стороны в досягаемости."""
    if not unit.get("engaged") or model.category(unit) != "ground":
        return 1.0
    pos = model.unit_pos(state, unit)
    k = 0.0
    for a in working(state, unit["side"]):
        if model.dist_km(model.unit_pos(state, a), pos) <= range_km(a):
            k += SUPPORT_K * model.strength(a) * a.get("ammo_k", 1.0)
    return 1.0 + min(MAX_K, k)


def _rear(state: dict, side: str, pos: dict) -> dict | None:
    entries = [state["places"][p] for p in (state.get("supply_entry") or {}).get(side, []) if p in state["places"]]
    return min(entries, key=lambda p: model.dist_km(p, pos)) if entries else None


def _lose(u: dict, frac: float) -> None:
    for c in u["composition"]:
        u["lost"][c["type"]] = min(c["count"], u["lost"].get(c["type"], 0.0) + c["count"] * frac)


def fire_target(state: dict, a: dict) -> dict | None:
    """Ближняя часть противника в бою в досягаемости бригады (точка огня в миссии)."""
    pos, r = model.unit_pos(state, a), range_km(a)
    foes = [u for u in state["units"].values() if u.get("side") == model.enemy(a["side"]) and model.category(u) == "ground"
            and u.get("state") not in ("destroyed", "pending") and not u.get("attached_to")]
    foes = [(model.dist_km(model.unit_pos(state, u), pos), u) for u in foes]
    foes = [x for x in foes if x[0] <= r]
    if not foes:
        return None
    engaged = [x for x in foes if x[1].get("engaged")] or foes
    return dict(model.unit_pos(state, min(engaged, key=lambda x: x[0])[1]))


def daily(state: dict) -> list[str]:
    """Сутки артиллерии: контрбатарейная борьба, затем смена позиций."""
    lines = []
    arts = [u for s in model.SIDES for u in working(state, s)]
    loss = {}
    for a in arts:
        f = 0.0
        for b in arts:
            if b["side"] != a["side"] and model.dist_km(model.unit_pos(state, a), model.unit_pos(state, b)) <= min(range_km(b), CB_RANGE_KM):
                f += CB_LOSS * model.strength(b) * b.get("cb_k", 1.0)
        if f:
            loss[a["id"]] = min(CB_MAX, f)
    for a in arts:                               # ремонт и пополнение
        for c in a["composition"]:
            if a["lost"].get(c["type"]):
                a["lost"][c["type"]] = max(0.0, a["lost"][c["type"]] - c["count"] * REPAIR)
    for aid, f in loss.items():
        a = state["units"][aid]
        _lose(a, f)
        lines.append(f"{a['name']}: потери от контрбатарейного огня {f:.0%}.")
    for a in arts:
        units = state["units"]
        own = [u for u in units.values() if u.get("side") == a["side"] and model.category(u) == "ground"
               and u.get("state") not in ("destroyed", "pending") and not u.get("attached_to")]
        sup = units.get(a.get("supports") or "")
        if not sup or sup.get("state") in ("destroyed", "pending"):
            busy = [u for u in own if u.get("engaged")] or own
            if not busy:
                continue
            sup = min(busy, key=lambda u: model.dist_km(model.unit_pos(state, u), model.unit_pos(state, a)))
        sp = model.unit_pos(state, sup)
        rear = _rear(state, a["side"], sp)
        if rear and model.dist_km(rear, sp) > BEHIND_KM:
            a["pos"] = model.lerp(sp, rear, BEHIND_KM / model.dist_km(rear, sp))
        else:
            a["pos"] = dict(sp)
    return lines

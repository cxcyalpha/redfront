"""Тыл: снабжение, мосты, аэродромы, пополнение эскадрилий. Все коэффициенты - ОЦЕНКИ (раздел sim доктрины стороны,
logistics_note), не из документа.

  * Склады (роль depot) в пунктах. Запас = 1 - повреждение. Склад в пункте, который занял противник, потерян.
  * Снабжение части: есть путь по своей территории и открытым связям до своего склада с запасом от supply_min_stock,
    не длиннее supply_km - снабжение 1.0, иначе unsupplied (0.5): марш медленнее, бой слабее, восстановление медленнее.
  * Мосты (роль bridge) на связях графа: разрушенный (повреждение 1) закрывает свои связи, пока не починят.
    Малый мост (minor: найден зондом карты, не через Эльбу) связь не закрывает - объезд: путь снабжения по связи
    длиннее на bridge_detour_km, марш по ней медленнее (sim.py). Склад, найденный зондом (supply: false), - цель
    без влияния на снабжение: снабжают только склады сценария.
  * Аэродромы (роль airfield), только военные: противник ближе airfield_threat_km - аэродром закрыт, эскадрильи
    перебазируются на ближний открытый свой; часть противника ближе airfield_lost_km - аэродром потерян (к противнику
    не переходит). Повреждение аэродрома уменьшает число доступных к вылету самолётов.
  * Повреждения восстанавливаются за сутки на repair_* ; эскадрильи пополняются до штата (replacements.air_per_day).
  * Заводы (роль factory): среднее повреждение заводов стороны x industry_effect замедляет ей восстановление тыла
    и пополнение авиации (industry()). Завод в пункте, который занял противник, потерян (в расчёте - как повреждение 1).
"""
from __future__ import annotations

from . import model


def _sim(state: dict, side: str) -> dict:
    return model.doctrine(state, side)["sim"]


def objects(state: dict, role: str) -> list[dict]:
    return [u for u in state["units"].values() if u.get("role") == role]


def is_minor(br: dict) -> bool:
    return bool(br.get("minor", br.get("found", False)))


def supplies(d: dict) -> bool:
    """Склад снабжает войска: склады сценария - да, найденные зондом карты - нет (цель без влияния на снабжение)."""
    return bool(d.get("supply", not d.get("found", False)))


def _down(state: dict, a: str, b: str, minor: bool) -> bool:
    return any(br.get("damage", 0) >= 1.0 and is_minor(br) == minor and any({a, b} == set(l) for l in br.get("links", []))
               for br in objects(state, "bridge"))


def link_open(state: dict, a: str, b: str) -> bool:
    """Связь закрыта разрушенным большим мостом; малый мост связь не закрывает (link_detour_km)."""
    return not _down(state, a, b, minor=False)


def link_detour(state: dict, a: str, b: str) -> bool:
    """На связи разрушен малый мост - объезд."""
    return _down(state, a, b, minor=True)


def bridge_side(state: dict, br: dict) -> str | None:
    """Чей мост: если оба конца всех его связей у одной стороны - её, иначе (на фронте) ничей."""
    owners = {state["places"][p].get("side") for l in br.get("links", []) for p in l}
    return owners.pop() if len(owners) == 1 else None


def depot_stock(d: dict) -> float:
    return 0.0 if d.get("state") == "lost" else max(0.0, 1.0 - d.get("damage", 0.0))


def supply(state: dict) -> list[str]:
    """Снабжение частей (u['supply']): путь по своей территории и открытым связям до своего склада с запасом."""
    from . import ops
    lines = []
    sides_with_depots = {d["side"] for d in objects(state, "depot") if supplies(d)}
    for u in ops._maneuver(state):
        sim = _sim(state, u["side"])
        if u["side"] not in sides_with_depots:   # у стороны нет складов в секторе - тыл не моделируется
            u["supply"] = 1.0
            continue
        here = ops.node_of(state, u)
        best = None
        for d in objects(state, "depot"):
            if d["side"] != u["side"] or not supplies(d) or depot_stock(d) < sim["supply_min_stock"]:
                continue
            p = ops.path(state, here, d["place"], side=u["side"])
            if p is not None:
                km = sum(model.dist_km(state["places"][a], state["places"][b])
                         + (sim.get("bridge_detour_km", 0) if link_detour(state, a, b) else 0) for a, b in zip(p, p[1:]))
                best = km if best is None else min(best, km)
        was = u.get("supply", 1.0)
        u["supply"] = 1.0 if best is not None and best <= sim["supply_km"] else sim["unsupplied"]
        if u["supply"] < 1.0 and was >= 1.0:
            lines.append(f"{u['name']}: без снабжения (нет пути до склада).")
        elif u["supply"] >= 1.0 and was < 1.0:
            lines.append(f"{u['name']}: снабжение восстановлено.")
    return lines


def airfields(state: dict) -> list[str]:
    """Состояние аэродромов по близости противника; перебазирование эскадрилий с закрытых и потерянных."""
    from . import ops
    lines = []
    for af in objects(state, "airfield"):
        if af["state"] == "lost":
            continue
        sim = _sim(state, af["side"])
        foe = model.enemy(af["side"])
        units = [u for u in ops._maneuver(state, foe) if u["state"] not in ("halted",)]
        d_unit = min((model.dist_km(af["pos"], model.unit_pos(state, u)) for u in units), default=1e9)
        d_place = min((model.dist_km(af["pos"], pl) for pl in state["places"].values() if pl.get("side") == foe), default=1e9)
        before = af["state"]
        if d_unit <= sim["airfield_lost_km"]:
            af["state"] = "lost"
        elif min(d_unit, d_place) <= sim["airfield_threat_km"]:
            af["state"] = "closed"
        else:
            af["state"] = "active"
        state["airbases"][af["base"]]["state"] = af["state"]
        if af["state"] != before:
            lines.append({"lost": f"{af['name']}: потерян (противник на аэродроме).",
                          "closed": f"{af['name']}: закрыт - противник ближе {sim['airfield_threat_km']} км.",
                          "active": f"{af['name']}: снова открыт."}[af["state"]])
    for u in state["units"].values():                             # перебазирование
        if model.category(u) not in ("air", "heli"):
            continue
        base = state["airbases"].get(u["base"])
        if base and base.get("state", "open") in ("open", "active"):
            continue
        cands = [(k, b) for k, b in state["airbases"].items() if b.get("side") == u["side"] and b.get("state", "open") in ("open", "active")]
        if not cands:
            continue
        k, b = min(cands, key=lambda kb: model.dist_km(kb[1], base or kb[1]))
        lines.append(f"{u['name']}: перебазирование {base['name'] if base else u['base']} -> {b['name']}.")
        u["base"] = k
    return lines


def industry(state: dict, side: str) -> float:
    """Множитель восстановления и пополнения стороны по её заводам: 1 - industry_effect x среднее повреждение.
    Нет заводов в секторе - 1 (промышленность вне сектора)."""
    fs = [f for f in objects(state, "factory") if f["side"] == side]
    if not fs:
        return 1.0
    dmg = sum(1.0 if f["state"] == "lost" else f.get("damage", 0.0) for f in fs) / len(fs)
    return max(0.0, 1.0 - _sim(state, side).get("industry_effect", 0.0) * dmg)


def repairs(state: dict) -> list[str]:
    lines = []
    for o in [*objects(state, "depot"), *objects(state, "bridge"), *objects(state, "airfield"), *objects(state, "factory")]:
        side = o["side"] or state["player_side"]
        rate = _sim(state, side)[f"repair_{o['role']}"] * (1.0 if o["role"] == "factory" else industry(state, side))
        if o.get("damage", 0) > 0:
            was = o["damage"]
            o["damage"] = max(0.0, o["damage"] - rate)
            if was >= 1.0 and o["damage"] < 1.0 and o["role"] == "bridge":
                lines.append(f"{o['name']}: восстановлен, движение открыто.")
    for d in [*objects(state, "depot"), *objects(state, "factory")]:   # склад, завод в занятом противником пункте - потерян
        if d["state"] != "lost" and d.get("place") and state["places"][d["place"]].get("side") != d["side"]:
            d["state"] = "lost"
            lines.append(f"{d['name']}: потерян (пункт занят противником).")
    return lines


def replacements(state: dict) -> list[str]:
    rate = (state.get("replacements") or {}).get("air_per_day", 0)
    lines = []
    for u in state["units"].values():
        if model.category(u) not in ("air", "heli") or u.get("count", 0) >= u.get("count0", 0):
            continue
        u["repl_acc"] = u.get("repl_acc", 0.0) + rate * industry(state, u["side"])
        add = min(int(u["repl_acc"]), u["count0"] - u["count"])
        if add > 0:
            u["count"] += add
            u["repl_acc"] -= add
            lines.append(f"{u['name']}: пополнение +{add} ЛА, в строю {u['count']}.")
    return lines


def available(state: dict, unit: dict) -> int:
    """Самолётов к вылету: в строю, с поправкой на повреждение аэродрома; закрытый аэродром - 0."""
    base = state["airbases"].get(unit.get("base"), {})
    if base.get("state", "open") not in ("open", "active"):
        return 0
    af = state["units"].get(f"af_{unit.get('base')}")
    dmg = af.get("damage", 0.0) if af else 0.0
    return int(unit.get("count", 0) * (1.0 - dmg))

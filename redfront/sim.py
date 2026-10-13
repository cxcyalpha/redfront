"""Суточный цикл наземной модели: бой частей в соприкосновении и марш.

Абстракция "карты и стрелки" - все коэффициенты в разделе sim пакета доктрины стороны, все - ОЦЕНКИ:
  1. Бой. Части противоположных сторон в соприкосновении (state 'battle', engaged - с кем) несут потери за сутки:
     доля = battle_loss_k * (сила противника / своя сила), не больше loss_cap; у обороняющейся (defend_factor) меньше.
     Сила - исправная техника с весами ролей (role_weight). Потери ложатся на типы пропорционально их числу.
     Часть ниже combat_ineffective_below выходит из боя (halted) и больше не держит противника.
  2. Марш. Части на марше и те, чей противник выбыл, идут по маршруту шагами step_km на daily_advance_km * боеспособность,
     пока не окажутся ближе contact_km к части противника - тогда бой. Дошла до конца маршрута - оборона (занят район).
"""
from __future__ import annotations

from . import logistics, model, ops

ACTIVE = ("march", "battle", "defend", "refit")


def _sim(state: dict, side: str) -> dict:
    return model.doctrine(state, side)["sim"]


def _maneuver(state: dict) -> list[dict]:
    return [u for u in state["units"].values() if model.category(u) == "ground" and "route" in u
            and u["state"] not in ("destroyed", "pending")]


def power(state: dict, unit: dict) -> float:
    """Боевая сила: исправная техника с весами ролей (ОЦЕНКА, sim.role_weight стороны части); без снабжения -
    x supply_power_factor."""
    sim = _sim(state, unit["side"])
    w = sim.get("role_weight", {})
    roles = {c["type"]: c["role"] for c in unit["composition"]}
    p = sum(n * w.get(roles[t], 0.0) for t, n in model.alive_by_type(unit).items())
    return p * (1.0 if unit.get("supply", 1.0) >= 1.0 else sim.get("supply_power_factor", 1.0))


def _take_losses(unit: dict, frac: float) -> float:
    """Списать долю frac исправной техники, по типам пропорционально. Возвращает число машин."""
    lost = 0.0
    for c in unit["composition"]:
        alive = max(0.0, c["count"] - unit["lost"].get(c["type"], 0.0))
        d = alive * frac
        unit["lost"][c["type"]] = unit["lost"].get(c["type"], 0.0) + d
        lost += d
    return lost


def _attached(state: dict, unit: dict) -> list[dict]:
    return [a for a in state["units"].values() if a.get("attached_to") == unit["id"] and a["state"] != "destroyed"]


def battles(state: dict) -> list[str]:
    lines = []
    units = state["units"]
    engaged = [u for u in _maneuver(state) if u["state"] == "battle"]
    pw = {u["id"]: power(state, u) for u in _maneuver(state)}    # сила на начало суток: потери сторон считаются одновременно
    for u in engaged:
        foes = [units[f] for f in u.get("engaged", []) if f in units]
        enemy = sum(pw.get(f["id"], 0.0) for f in foes if f["state"] in ACTIVE)
        if enemy <= 0 or pw[u["id"]] <= 0:
            continue
        sim = _sim(state, u["side"])
        frac = min(sim["loss_cap"], sim["battle_loss_k"] * enemy / pw[u["id"]])
        r = model.rng(state, f"battle-{u['id']}")
        if r:                                    # исход суток боя - с разбросом (ОЦЕНКА, sim.battle_variance)
            frac = min(sim["loss_cap"], frac * r.uniform(1 - sim["battle_variance"], 1 + sim["battle_variance"]))
        if u.get("defending"):
            frac *= sim["defend_factor"]
        s0 = model.strength(u)
        n = _take_losses(u, frac)
        for a in _attached(state, u):                            # приданная ПВО несёт те же потери
            _take_losses(a, frac)
        lines.append(f"{u['name']}: бой с {', '.join(f['name'] for f in foes)} - потеряно ~{n:.0f} машин, "
                     f"боеспособность {s0:.0%} -> {model.strength(u):.0%}.")
    for u in engaged:
        sim = _sim(state, u["side"])
        if model.strength(u) < sim["combat_ineffective_below"]:
            u["state"] = "halted"
            lines.append(f"{u['name']}: потерял боеспособность, вышел из боя.")
    for u in engaged:                                             # бой окончен, если против части никого не осталось
        if u["state"] != "battle":
            continue
        alive = [f for f in u.get("engaged", []) if units[f]["state"] == "battle"]
        if not alive:
            u["state"] = "defend" if u.get("defending") else "march"
            u["engaged"] = []
            lines.append(f"{u['name']}: противник выбыл - " + ("удержал район." if u.get("defending") else "продолжает марш."))
    return lines


def _length(state: dict, u: dict) -> float:
    return model.route_length_km(model.route_points(state, u))


def _contacts(state: dict, units: list[dict]) -> list[tuple[dict, dict]]:
    out = []
    act = [u for u in units if u["state"] in ACTIVE and u.get("order") != "withdraw"]   # отходящие разрывают соприкосновение
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            if a["side"] == b["side"]:
                continue
            ck = max(_sim(state, a["side"])["contact_km"], _sim(state, b["side"])["contact_km"])
            if model.dist_km(model.unit_pos(state, a), model.unit_pos(state, b)) <= ck:
                out.append((a, b))
    return out


def _engage(a: dict, b: dict) -> None:
    for x, y in ((a, b), (b, a)):
        if x["state"] in ("defend", "refit"):
            x["defending"] = True
        elif x["state"] == "march":
            x["defending"] = False
        x["state"] = "battle"
        x.setdefault("engaged", [])
        if y["id"] not in x["engaged"]:
            x["engaged"].append(y["id"])


def current_link(state: dict, u: dict) -> tuple[str, str] | None:
    """Связь маршрута, на которой сейчас часть (по пройденным км)."""
    r = u.get("route") or []
    km = 0.0
    for a, b in zip(r, r[1:]):
        km += model.route_length_km(model.route_points(state, {"route": [a, b]}))
        if u["progress_km"] < km - 1e-6:
            return a, b
    return (r[-2], r[-1]) if len(r) > 1 else None


def movement(state: dict) -> list[str]:
    lines = []
    units = _maneuver(state)
    budget, start = {}, {}
    for u in units:
        if u["state"] == "march":
            budget[u["id"]] = ((u.get("daily_advance_km") or _sim(state, u["side"])["daily_advance_km"]) * model.strength(u)
                               * u.get("supply", 1.0))                        # без снабжения - медленнее
            cl = current_link(state, u)
            if cl and logistics.link_detour(state, *cl):                       # разрушен малый мост - объезд
                budget[u["id"]] *= _sim(state, u["side"]).get("bridge_detour_slow", 1.0)
            start[u["id"]] = u["progress_km"]
    new_contacts = []
    for a, b in _contacts(state, units):                          # соприкосновение уже есть до марша
        if b["id"] not in a.get("engaged", []):
            _engage(a, b); new_contacts.append((a, b))
    moving = [u for u in units if u["state"] == "march" and budget.get(u["id"], 0) > 0]
    while moving:
        for u in moving:
            step = min(_sim(state, u["side"])["step_km"], budget[u["id"]])
            u["progress_km"] = min(_length(state, u), u["progress_km"] + step)
            budget[u["id"]] -= step
        for a, b in _contacts(state, units):
            if b["id"] not in a.get("engaged", []):
                _engage(a, b); new_contacts.append((a, b))
        for u in moving:
            if u["state"] == "march" and u["progress_km"] >= _length(state, u) - 1e-6:
                u["state"] = "defend"
                u["defending"] = True
                lines.append(f"{u['name']}: вышел в район {u['route'][-1]}, перешёл к обороне.")
        moving = [u for u in moving if u["state"] == "march" and budget[u["id"]] > 1e-6]
    for u in units:
        if u["id"] in start and u["progress_km"] - start[u["id"]] > 0.05:
            lines.append(f"{u['name']}: продвинулся на {u['progress_km'] - start[u['id']]:.0f} км "
                         f"(боеспособность {model.strength(u):.0%}).")
    for a, b in new_contacts:
        where = min((a, b), key=lambda x: 0 if x.get("defending") else 1)
        lines.append(f"Соприкосновение: {a['name']} и {b['name']} (район {where['route'][-1] if where.get('defending') else 'на марше'}).")
    return lines


def arrivals(state: dict) -> list[str]:
    """Резервы и вторые эшелоны: часть с arrives_day вводится в сектор в пункте route[0] в этот день."""
    lines = []
    for u in state["units"].values():
        if u.get("state") == "pending" and "route" in u and state["day"] >= u.get("arrives_day", 0):
            u["state"] = "defend"
            u["route"] = [u["route"][0]]
            u["progress_km"] = 0.0
            for a in _attached(state, u):
                a["state"] = "defend"
            lines.append(f"{u['name']}: прибыл в район {u['route'][0]}.")
    return lines


def end_day(state: dict) -> list[str]:
    lines = []
    for u in _maneuver(state):
        if model.strength(u) <= 0.05:
            u["state"] = "destroyed"
            for a in _attached(state, u):
                a["state"] = "destroyed"
            lines.append(f"{u['name']}: уничтожен.")
        elif (u["state"] == "march" and u.get("order") != "withdraw"
              and model.strength(u) < _sim(state, u["side"])["combat_ineffective_below"]):
            u["state"] = "halted"
            lines.append(f"{u['name']}: потерял боеспособность ({model.strength(u):.0%}), остановился.")
    lines += logistics.supply(state)
    lines += battles(state)
    for side in model.SIDES:                     # оперативный уровень: задачи частям (ops.py)
        lines += ops.commander(state, side)
    lines += movement(state)
    lines += ops.capture(state)
    lines += logistics.repairs(state)
    lines += logistics.air_defence(state)
    lines += logistics.airfields(state)
    lines += logistics.replacements(state)
    state["day"] += 1
    lines += arrivals(state)
    for ln in lines:
        model.note(state, ln)
    state["task"] = None
    state["tasks"] = []
    state["ato"] = None                          # план полётов и часы - новых суток (ato.py)
    state["clock_s"] = 0
    state["manifest"] = None
    return lines

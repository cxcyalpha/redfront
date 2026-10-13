"""Воздушная война вокруг игрока: итоги вылетов плана полётов (ATO) в своё время суток - по шагам наземной модели
(sim.advance). Все числа - ОЦЕНКИ (airwar_note доктрины нет - константы здесь).

Вылет даёт итог, когда наступает его время на цели (tot_s):
  * десант, поиск и спасение, удар по пути подвоза - их модули (assault.py, csar.py, convoys.py);
  * удар ИИ по наземной цели (колонна или часть в бою, позиция ЗРК, объект тыла), не слетанный в миссии (не
    'done' игрока и не 'played' - не был группой ИИ в собранной и слетанной миссии): удача - с вероятностью
    STRIKE_P минус PER_THREAT на ЗРК в коридоре; потери цели - доля на пару самолётов (LOSS), объекту тыла -
    повреждение (DAMAGE). Сама группа теряет самолёты от ЗРК коридора (LOSS_PER_THREAT на борт); экипаж
    сбитого катапультируется (EJECT_P) - на земле у цели (csar.py), иначе погиб.
Дежурства, перевозки, прикрытие своих войск - без итога здесь (перевозки - в снабжении, logistics.supply).
"""
from __future__ import annotations

from . import model

STRIKE_P = 0.7
PER_THREAT = 0.1
LOSS = {"column": 0.04, "site": 0.25}            # доля исправной техники цели на пару ударной группы
DAMAGE = {"depot": 0.35, "factory": 0.25, "airfield": 0.3, "bridge": 0.5}
LOSS_PER_THREAT = 0.03                             # вероятность потерять борт на ЗРК коридора
EJECT_P = 0.7


def _tot(e: dict) -> float:
    return float(e.get("tot_s") or 0)


def _strike(state: dict, e: dict) -> list[str]:
    from . import csar, sim
    g = e["task"]["package"][0]
    obj = g["objective"]
    tgt = state["units"].get(obj.get("unit") or "")
    if not tgt or tgt.get("state") in ("destroyed", "lost"):
        return []
    threats = [t for t in e["task"].get("threats", []) if t in state["units"]]
    r = model.rng(state, f"airwar-{e['id']}")
    lines = []
    perf = state["units"].get(g["performer"])
    # потери группы от ЗРК коридора
    pl = min(0.5, LOSS_PER_THREAT * len(threats))
    down = sum(1 for _ in range(g["size"]) if r.random() < pl) if r else 0
    if perf and down:
        perf["count"] = max(0, perf.get("count", 0) - down)
        for k in range(down):
            if (r.random() if r else 1.0) < EJECT_P:
                csar.add_downed(state, perf, f"ai:{e['id']}:{k}", model.offset(obj["pos"], 90.0 * k, 2000 + 500 * k))
            elif "crews" in perf:
                perf["crews"] = max(0, perf["crews"] - 1)
        lines.append(f"ИИ, {e['title']}: потеряно {down} {perf['type']} ({perf['name']}).")
    p = max(0.1, min(0.9, STRIKE_P - PER_THREAT * len(threats)))
    if not ((r.random() < p) if r else p >= 0.5):
        lines.append(f"ИИ, {e['title']}: цель не поражена.")
        return lines
    size_k = max(0, g["size"] - down) / 2.0
    if obj["kind"] == "point":
        role = model.category(tgt)
        before = tgt.get("damage", 0.0)
        tgt["damage"] = min(1.0, before + DAMAGE.get(role, 0.3) * size_k)
        lines.append(f"ИИ, {e['title']}: повреждение {before:.0%} -> {tgt['damage']:.0%}.")
    elif obj["kind"] in LOSS:
        frac = min(0.5, LOSS[obj["kind"]] * size_k)
        s0 = model.strength(tgt)
        sim._take_losses(tgt, frac)
        lines.append(f"ИИ, {e['title']}: боеспособность цели {s0:.0%} -> {model.strength(tgt):.0%}.")
    return lines


def resolve(state: dict, t0: float, t1: float) -> list[str]:
    """Итоги вылетов плана полётов суток со временем на цели в (t0, t1]."""
    from . import assault, convoys, csar
    a = state.get("ato") or {}
    if not a.get("entries"):
        return []
    lines = []
    lines += assault.resolve(state, t1)
    lines += csar.resolve(state, t1)
    lines += convoys.daily(state, t1)
    skip = set(a.get("done", [])) | set(a.get("played", []))
    for e in a["entries"]:
        if e.get("ai_only") or e.get("resolved") or not (t0 < _tot(e) <= t1):
            continue
        if e["kind"] in ("air_assault", "csar", "strike_supply_route", "airlift"):
            continue
        e["resolved"] = True
        if e["id"] in skip:
            continue
        obj = e["task"]["package"][0]["objective"]
        if obj["kind"] in ("column", "site", "point"):
            lines += _strike(state, e)
    return lines

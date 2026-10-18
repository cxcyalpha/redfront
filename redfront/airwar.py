"""Воздушная война вокруг игрока: итоги вылетов плана полётов (ATO) в своё время суток - по шагам наземной модели
(sim.advance). Все числа - ОЦЕНКИ (airwar_note доктрины нет - константы здесь).

Вылет даёт итог, когда наступает его время на цели (tot_s):
  * десант, поиск и спасение, удар по пути подвоза - их модули (assault.py, csar.py, convoys.py);
  * удар ИИ по наземной цели (колонна или часть в бою, позиция ЗРК, объект тыла), не слетанный в миссии (не
    'done' игрока и не 'played' - не был группой ИИ в собранной и слетанной миссии): удача - с вероятностью
    STRIKE_P минус PER_THREAT на ЗРК в коридоре; потери цели - доля на пару самолётов (LOSS), объекту тыла -
    повреждение (DAMAGE); то и другое - с множителем пригодности типа (fitness.outcome_factor: лучший в кампании - 1.0). Сама группа теряет самолёты от ЗРК коридора (LOSS_PER_THREAT на борт); экипаж
    сбитого катапультируется (EJECT_P) - на земле у цели (csar.py), иначе погиб.
Дежурные пары ПВО противника на смене рядом с целью (alerts_near) снижают успех удара (QRA_P на пару) и повышают
потери (QRA_LOSS). Дежурства, перевозки, прикрытие своих войск - без итога здесь (перевозки - в снабжении, logistics.supply).
"""
from __future__ import annotations

from . import model

STRIKE_P = 0.7
PER_THREAT = 0.1
LOSS = {"column": 0.04, "site": 0.25}            # доля исправной техники цели на пару ударной группы
DAMAGE = {"depot": 0.35, "factory": 0.25, "airfield": 0.3, "bridge": 0.5}
LOSS_PER_THREAT = 0.03                             # вероятность потерять борт на ЗРК коридора
EJECT_P = 0.7


QRA_P = 0.05                                       # дежурная пара ПВО противника рядом с целью: минус к успеху
QRA_LOSS = 0.04                                    # и к вероятности потерять борт


def alerts_near(state: dict, side: str, pos: dict, t: float) -> int:
    """Дежурных пар ПВО стороны side на смене в момент t, чья база не дальше scramble_km от pos."""
    n = 0
    for e in (state.get("ato") or {}).get("entries", []):
        g = e["task"]["package"][0]
        if e["side"] != side or g["objective"]["kind"] != "alert":
            continue
        tm = e["times"][g["group"]]
        tdef = model.doctrine(state, side)["tasks"][e["kind"]]
        if tm["takeoff_s"] <= t <= tm["land_s"] and model.dist_km(state["airbases"][g["base"]], pos) <= tdef.get("scramble_km", 150):
            n += 1
    return n


def _tot(e: dict) -> float:
    return float(e.get("tot_s") or 0)


FIND_KM = 5        # ОЦЕНКА: цель в стольких км от точки, куда летела группа, - находят (поиск в районе цели)
LOST_KM = 20       # ОЦЕНКА: дальше - не находят (группа уходит с бомбами или бьёт по запасной цели)


def _find(state: dict, e: dict, tgt: dict, obj: dict) -> tuple[float, str]:
    """Множитель успеха по данным разведки - только сторона игрока (противник бьёт по настоящему положению):
    группа летит туда, где цель видели последний раз (intel.py); насколько та ушла - настолько труднее найти."""
    from . import intel
    if e["side"] != state.get("player_side") or not intel.tracked_ground(state, tgt) or "pos" not in obj:
        return 1.0, ""
    intel.update(state)
    aim = intel.aim_pos(state, tgt) or obj["pos"]
    d = model.dist_km(aim, model.unit_pos(state, tgt))
    if d <= FIND_KM:
        return 1.0, ""
    if d >= LOST_KM:
        return 0.0, f"ушла на {d:.0f} км от места по данным разведки"
    return 1.0 - (d - FIND_KM) / (LOST_KM - FIND_KM), ""


SEAD_KNOWN = 0.5        # ОЦЕНКА: потери от ЗРК коридора при подавлении по свежим данным разведки (пуск спланирован)
SEAD_SEARCH = 0.75      # ОЦЕНКА: подавление без свежих данных - поиск РЛС в полёте


def sead_factor(state: dict, e: dict, threats: list[str]) -> float:
    """Множитель потерь от ЗРК коридора: в пакете есть подавление ПВО - меньше; по свежим данным - ещё меньше."""
    if not threats or not any(g["objective"]["kind"] == "sam" for g in e["task"]["package"]):
        return 1.0
    from . import build
    known = e["side"] != state.get("player_side") or all(build.intel_exact(state, t) for t in threats)
    return SEAD_KNOWN if known else SEAD_SEARCH


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
    qra = alerts_near(state, model.enemy(e["side"]), obj["pos"], _tot(e))
    # потери группы от ЗРК коридора и дежурных пар ПВО противника
    pl = min(0.5, LOSS_PER_THREAT * len(threats) * sead_factor(state, e, threats) + QRA_LOSS * qra)
    down = sum(1 for _ in range(g["size"]) if r.random() < pl) if r else 0
    if perf and down:
        perf["count"] = max(0, perf.get("count", 0) - down)
        for k in range(down):
            if (r.random() if r else 1.0) < EJECT_P:
                csar.add_downed(state, perf, f"ai:{e['id']}:{k}", model.offset(obj["pos"], 90.0 * k, 2000 + 500 * k))
            elif "crews" in perf:
                from . import pilots
                pilots.killed(perf, pilots.take(perf), "погиб", state["day"])
                perf["crews"] = max(0, perf["crews"] - 1)
        lines.append(f"ИИ, {e['title']}: потеряно {down} {perf['type']} ({perf['name']}).")
    from . import fitness                       # пригодность типа для задачи - относительно лучшего в кампании
    fk = fitness.outcome_factor(state, perf.get("type", "") if perf else "", fitness.task_class(e["kind"]))
    ff, why = _find(state, e, tgt, obj)          # туман войны: нашли ли цель там, куда летели
    if ff <= 0:
        lines.append(f"ИИ, {e['title']}: цель не найдена ({why}).")
        return lines
    fk *= ff
    p = max(0.1, min(0.9, (STRIKE_P - PER_THREAT * len(threats) - QRA_P * qra) * fk))
    if not ((r.random() < p) if r else p >= 0.5):
        lines.append(f"ИИ, {e['title']}: цель не поражена.")
        return lines
    size_k = max(0, g["size"] - down) / 2.0 * fk
    if obj["kind"] == "point":
        role = model.category(tgt)
        before = tgt.get("damage", 0.0)
        tgt["damage"] = min(1.0, before + DAMAGE.get(role, 0.3) * size_k)
        from . import explain
        lines.append(f"ИИ, {e['title']}: повреждение {before:.0%} -> {tgt['damage']:.0%}." + explain.damage_effect(state, tgt, before))
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
    lines += assault.evac_resolve(state, t1)
    lines += csar.resolve(state, t1)
    lines += convoys.daily(state, t1)
    from . import recon
    lines += recon.resolve(state, t1)            # разведывательные вылеты - в журнал разведки после обработки данных
    skip = set(a.get("done", [])) | set(a.get("played", []))
    for e in a["entries"]:
        if e.get("ai_only") or e.get("resolved") or not (t0 < _tot(e) <= t1):
            continue
        if e["kind"] in ("air_assault", "air_evac", "csar", "strike_supply_route", "airlift"):
            continue
        e["resolved"] = True
        if e["id"] in skip:
            continue
        obj = e["task"]["package"][0]["objective"]
        if obj["kind"] in ("column", "site", "point"):
            lines += _strike(state, e)
    return lines

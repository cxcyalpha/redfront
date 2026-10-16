"""Вертолётный десант (задача air_assault доктрины; все числа - ОЦЕНКИ, assault_note доктрины).

Десантное подразделение (роль air_assault, рота) стоит в резерве (order reserve) в своём пункте и в бой фронта не
идёт. Задача плана дня: группа транспортных вертолётов поднимает роту и высаживает её на площадку у пункта
противника в тылу - узла, после взятия которого у противника больше всего складов отрезано от подвоза из тыла
(logistics.road_connected), затем - ближнего к цели своей оси. Рота держит пункт (order airhead), пока не
соединится со своими (получает снабжение со своих складов), затем - обычная часть.

Итог высадки - в своё время суток (resolve из шага наземной модели, airwar.py): вылет игрока - по файлу дебрифа (сколько бортов село на площадку,
lua/assault.lua); вылет ИИ - по потерям в миссиях (если был в окне) и по угрозам ЗРК в коридоре.
"""
from __future__ import annotations

import math

from . import logistics, model, ops


def troops(type_name: str) -> int:
    """Десантников на борт (aircraft.json troops), ОЦЕНКА по умолчанию - 10."""
    return int(model.aircraft_info(type_name).get("troops") or 10)


def men(unit: dict, alive: bool = False) -> float:
    """Человек в подразделении (men, иначе по 4 на фигуру пехоты); alive - с учётом потерь."""
    n = unit.get("men") or 4 * sum(c["count"] for c in unit["composition"])
    return n * model.strength(unit) if alive else n


def lift_need(unit: dict, heli_type: str, alive: bool = False) -> int:
    """Бортов, чтобы поднять подразделение (alive - только живых: эвакуация)."""
    return max(1, math.ceil(men(unit, alive) / troops(heli_type)))


def reserve(state: dict, side: str) -> list[dict]:
    """Десантные подразделения стороны в резерве, готовые к высадке (боеспособность не ниже refit_ready)."""
    ready = model.doctrine(state, side)["sim"].get("refit_ready", 0.8)
    return [u for u in state["units"].values() if u["side"] == side and u.get("air_mobile") and u.get("order") == "reserve"
            and u["state"] == "defend" and model.strength(u) >= ready]


def lz_point(state: dict, side: str, place: str, tdef: dict) -> dict:
    """Площадка: в lz_offset_km от пункта в сторону ближнего своего пункта (не в самом городе)."""
    p = state["places"][place]
    own = [q for q in state["places"].values() if q.get("side") == side]
    if not own:
        return dict(p)
    near = min(own, key=lambda q: model.dist_km(p, q))
    return model.offset(p, model.bearing_deg(p, near), tdef.get("lz_offset_km", 2) * 1000)


def candidates(state: dict, side: str, tdef: dict) -> list[str]:
    """Пункты для высадки, лучшие первыми: противника, в assault_min_km..assault_max_km от своих пунктов, без
    его частей ближе lz_clear_km, не соседний (по графу) со своими; ключ - (сколько его складов отрезается от подвоза, путь до цели своей оси, глубина)."""
    foe = model.enemy(side)
    pl = state["places"]
    own = [p for p in pl.values() if p.get("side") == side]
    if not own:
        return []
    g = ops.graph(state)
    base_conn = logistics.road_connected(state, foe, g)
    obj = ops.objective(state, side)
    out = []
    for name, p in pl.items():
        if p.get("side") != foe or any(pl[q].get("side") == side for q in g[name]):
            continue                             # соседний со своими пункт - не десант, а наступление
        depth = min(model.dist_km(p, q) for q in own)
        if not tdef.get("assault_min_km", 8) <= depth <= tdef.get("assault_max_km", 50):
            continue
        if ops._units_near(state, name, foe, tdef.get("lz_clear_km", 10)):
            continue
        p["side"] = side                         # что будет, если пункт возьмём: склады противника без подвоза
        try:
            cut = len(base_conn - logistics.road_connected(state, foe, g))
        finally:
            p["side"] = foe
        to_obj = ops.path_km(state, name, obj) if obj else 0.0
        out.append(((-cut, to_obj, depth), name))
    out.sort()
    return [n for _k, n in out]


def resolve(state: dict, until_s: float | None = None) -> list[str]:
    """Итог высадок плана полётов суток со временем на цели не позже until_s (шаг наземной модели, airwar.py)."""
    a = state.get("ato") or {}
    results = a.get("assault") or {}
    lost_by = a.get("lost") or {}
    lines = []
    for e in a.get("entries", []):
        if e["kind"] != "air_assault" or e.get("resolved") or (until_s is not None and e["tot_s"] > until_s):
            continue
        g = e["task"]["package"][0]
        obj = g["objective"]
        u = state["units"].get(obj.get("unit"))
        if not u or u.get("order") != "reserve" or u["state"] != "defend":
            continue
        tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        e["resolved"] = True
        size = sum(x["size"] for x in e["task"]["package"] if x["objective"]["kind"] == "air_assault")   # все волны
        if e["id"] in results:                   # вылет игрока: сколько бортов село на площадку (assault.lua)
            landed = min(size, int(results[e["id"]][0]))
            how = "по итогам вылета"
        elif e["id"] in a.get("done", []):       # игрок летал, но на площадку не сел никто
            landed = 0
            how = "по итогам вылета"
        else:                                    # ИИ: сбитые в миссиях, остальное - по угрозам ЗРК в коридоре
            left = max(0, size - lost_by.get(e["id"], 0))
            p = min(0.8, tdef.get("ai_loss_per_threat", 0.15) * len(e["task"].get("threats", [])))
            r = model.rng(state, f"assault-{e['id']}")
            down = sum(1 for _ in range(left) if r.random() < p) if r else round(left * p)
            landed = left - down
            how = "ИИ"
        # рота - поровну по бортам (загрузка, а не вместимость: 100 человек на 4 CH-53 - по 25, не по 37)
        frac = landed / size if size else 0.0
        lost_frac = (size - landed) / size if size else 0.0
        if lost_frac > 0:                        # рота в сбитых бортах
            for c in u["composition"]:
                alive = max(0.0, c["count"] - u["lost"].get(c["type"], 0.0))
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) + alive * lost_frac
        place = obj["place"]
        if frac < tdef.get("fail_below", 0.4):
            lines.append(f"{u['name']}: высадка у {place} сорвана ({how}: село {landed} из {size} бортов).")
            continue
        u["route"] = [place]
        u["progress_km"] = 0.0
        u["state"], u["order"], u["defending"], u["engaged"] = "defend", "airhead", True, []
        u["airhead_day"] = state["day"]
        lines.append(f"{u['name']}: высажена у {place} ({how}: село {landed} из {size} бортов), держит пункт до подхода своих.")
    return lines


def linkup(state: dict) -> list[str]:
    """Десант соединился со своими (получает снабжение со своих складов) - дальше обычная часть."""
    lines = []
    for u in state["units"].values():
        if (u.get("order") == "airhead" and u["state"] != "destroyed" and u.get("supply_frac", 0) > 0
                and state["places"][u["route"][-1]].get("side") == u["side"]):
            u["order"] = None
            lines.append(f"{u['name']}: соединилась со своими у {u['route'][-1]}.")
    return lines


def evac_needed(state: dict, side: str, tdef: dict) -> list[dict]:
    """Десант стороны в тылу противника, которому пора на эвакуацию: боеспособность ниже evac_below или держится
    evac_days суток и больше (не соединился со своими). Слабейшие первыми."""
    out = []
    for u in state["units"].values():
        if u["side"] != side or u.get("order") != "airhead" or u["state"] in ("destroyed", "halted"):
            continue
        if state["places"][u["route"][-1]].get("side") == side and u.get("supply_frac", 0) > 0:
            continue                             # соединился (linkup) - не десант
        days = state["day"] - u.get("airhead_day", state["day"])
        if model.strength(u) < tdef.get("evac_below", 0.5) or days >= tdef.get("evac_days", 3):
            out.append(u)
    return sorted(out, key=model.strength)


def evac_resolve(state: dict, until_s: float | None = None) -> list[str]:
    """Итог эвакуаций плана полётов суток со временем на цели не позже until_s. Вылет игрока - по дебрифу (сколько
    фигур роты вывезено из живых к моменту погрузки, lua/evac.lua), ИИ - по сбитым в миссиях и угрозам ЗРК в коридоре.
    Вывезенные - в резерв (order reserve) в своём пункте у аэродрома группы; кого не вывезли - потеряны (плен)."""
    a = state.get("ato") or {}
    results = a.get("evac") or {}
    lost_by = a.get("lost") or {}
    lines = []
    for e in a.get("entries", []):
        if e["kind"] != "air_evac" or e.get("resolved") or (until_s is not None and e["tot_s"] > until_s):
            continue
        g = e["task"]["package"][0]
        u = state["units"].get(g["objective"].get("unit"))
        if not u or u.get("order") != "airhead" or u["state"] == "destroyed":
            continue
        e["resolved"] = True
        tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        perf = state["units"].get(g["performer"])
        if e["id"] in results:                   # вылет игрока
            saved, total = results[e["id"]]
            frac = saved / total if total else 0.0
            how = "по итогам вылета"
        elif e["id"] in a.get("done", []):
            frac, how = 0.0, "по итогам вылета"
        else:                                    # ИИ: сбитые в миссиях, остальное - по угрозам ЗРК в коридоре
            size = sum(x["size"] for x in e["task"]["package"] if x["objective"]["kind"] == "air_evac")
            left = max(0, size - lost_by.get(e["id"], 0))
            p = min(0.8, tdef.get("ai_loss_per_threat", 0.15) * len(e["task"].get("threats", [])))
            r = model.rng(state, f"evac-{e['id']}")
            landed = left - (sum(1 for _ in range(left) if r.random() < p) if r else round(left * p))
            frac = min(1.0, landed * troops(perf["type"] if perf else "") / max(1.0, men(u, alive=True)))
            how = "ИИ"
        if frac <= 0:
            lines.append(f"{u['name']}: эвакуация сорвана ({how}), рота держится у {u['route'][-1]}.")
            continue
        for c in u["composition"]:               # не вывезенные - потеряны
            alive = max(0.0, c["count"] - u["lost"].get(c["type"], 0.0))
            u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) + alive * (1.0 - frac)
        base = state["airbases"].get((perf or {}).get("home") or g["base"]) or state["airbases"][g["base"]]
        own = [n for n, p in state["places"].items() if p.get("side") == e["side"]]
        home = min(own, key=lambda n: model.dist_km(base, state["places"][n])) if own else u["route"][-1]
        u["route"], u["progress_km"] = [home], 0.0
        u["state"], u["order"], u["defending"], u["engaged"] = "defend", "reserve", True, []
        u.pop("airhead_day", None)
        lines.append(f"{u['name']}: эвакуирована ({how}): вывезено {frac:.0%} живых, в резерве у {home}.")
    return lines

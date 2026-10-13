"""Пути подвоза и колонны снабжения на дорогах (все числа - ОЦЕНКИ, convoy_note доктрины).

Подвоз из тыла (logistics.supply) идёт к каждому складу по своему пути: от ближнего пункта входа (тыл сектора) по
своей территории - путь по графу пунктов, участки - по дорогам, где они известны (state['roads']). Сколько тонн
склад получил за сутки - прогноз потока на следующие сутки (state['supply_routes']). Поток участка - сумма потоков
путей через него; грузовиков в сутки - поток / TRUCK_T.

В миссии по участкам с потоком в районе задачи идут колонны грузовиков (доля суточного потока, бывшая на участке
во время миссии, - WINDOW_SHARE): машина колонны несёт вес = грузовиков потока / машин в миссии (правило
сохранения). Сожжённые машины - недовезённые тонны (дебриф -> state['convoy_losses']); в конце суток недовоз
ложится на склады, чьи пути идут через этот участок, по их доле потока. Удар ИИ по пути подвоза вне миссии - доля
INTERDICT_LOSS потока участка.
"""
from __future__ import annotations

import heapq
import math

from . import model

TRUCK_T = 8.0            # ОЦЕНКА: тонн на грузовик колонны снабжения
WINDOW_SHARE = 0.1       # ОЦЕНКА: доля суточного потока участка, бывшая на нём во время миссии (~2.5 ч движения)
CONVOY_MIN, CONVOY_MAX = 4, 16   # машин колонны в миссии
CONVOY_KMH = 40
SPACING_M = 60
MIN_FLOW_T = 30.0        # участок с меньшим потоком - без колонны и не цель
INTERDICT_LOSS = 0.15    # ОЦЕНКА: удачный удар ИИ по пути подвоза вне миссии - такая доля суточного потока участка
TRUCKS = {"red": ("Ural_375", "KAMAZ_Truck", "Ural_4320T"), "blue": ("M_818", "Bedford_MWD", "Land_Rover_101_FC")}


def key(a: str, b: str) -> str:
    return f"{a}>{b}"


def paths_from(state: dict, side: str, sources: list[str], g: dict) -> tuple[dict, dict]:
    """Дейкстра от sources по своей территории (как logistics._reach) с предками: (км, предок)."""
    dist = {p: 0.0 for p in sources if state["places"][p].get("side") == side}
    prev: dict[str, str] = {}
    q = [(0.0, p) for p in dist]
    while q:
        d, u = heapq.heappop(q)
        if d > dist.get(u, 1e18) or state["places"][u].get("side") != side:
            continue
        for v, w in g[u].items():
            if d + w < dist.get(v, 1e18):
                dist[v], prev[v] = d + w, u
                heapq.heappush(q, (d + w, v))
    return dist, prev


def path_to(prev: dict, src: set, dst: str) -> list[str]:
    out = [dst]
    while out[-1] not in src and out[-1] in prev:
        out.append(prev[out[-1]])
    return out[::-1]


def forecast(state: dict, side: str, delivered: dict[str, float], g: dict) -> list[dict]:
    """Пути подвоза стороны на следующие сутки: склад, путь от тыла, поток (т/сутки = подвезено за эти сутки)."""
    from . import logistics
    ent = logistics.entries(state, side)
    dist, prev = paths_from(state, side, ent, g)
    out = []
    for d in logistics.objects(state, "depot"):
        if d["side"] != side or d.get("place") not in dist or not delivered.get(d["id"]):
            continue
        out.append({"depot": d["id"], "path": path_to(prev, set(ent), d["place"]), "t": round(delivered[d["id"]], 1)})
    return out


def routes(state: dict, side: str) -> list[dict]:
    """Пути подвоза стороны (прогноз прошлых суток); их ещё нет (первые сутки) - по ёмкости складов (10% в сутки)."""
    r = (state.get("supply_routes") or {}).get(side)
    if r is not None:
        return r
    from . import logistics, ops
    logistics.init_depots(state)
    g = ops.graph(state)
    return forecast(state, side, {d["id"]: 0.1 * d.get("cap_t", 0) for d in logistics.objects(state, "depot")
                                  if d["side"] == side}, g)


def link_flows(state: dict, side: str) -> dict[str, float]:
    """Поток по участкам (т/сутки), ключ - направление подвоза 'A>B'."""
    out: dict[str, float] = {}
    for r in routes(state, side):
        for a, b in zip(r["path"], r["path"][1:]):
            out[key(a, b)] = out.get(key(a, b), 0.0) + r["t"]
    return out


def convoy_id(side: str, link: str) -> str:
    return f"conv_{side}_{link.replace('>', '_')}"


def link_mid(state: dict, link: str) -> dict:
    a, b = link.split(">")
    pts = model.route_points(state, {"route": [a, b]})
    return model.point_at_km(pts, model.route_length_km(pts) / 2)[0]


def group(state: dict, side: str, link: str, flow_t: float, density: float = 1.0, seed: str = "") -> dict:
    """Колонна снабжения на участке link в миссии: голова - на 30-70% длины участка (по дороге, если известна),
    машины позади через SPACING_M, путь - до конца участка. Вес машины - грузовиков потока на машину миссии."""
    a, b = link.split(">")
    pts = model.route_points(state, {"route": [a, b]})
    length = model.route_length_km(pts)
    trucks_day = flow_t / TRUCK_T
    n = max(CONVOY_MIN, min(CONVOY_MAX, int(math.ceil(trucks_day * WINDOW_SHARE * density))))
    w = trucks_day * WINDOW_SHARE / n
    r = model.rng(state, f"convoy-{link}-{state['day']}-{seed}")
    head = length * (r.uniform(0.3, 0.7) if r else 0.5)
    types = TRUCKS[side]
    vehicles = []
    cid = convoy_id(side, link)
    for i in range(n):
        km = max(0.0, head - i * SPACING_M / 1000)
        p, _seg = model.point_at_km(pts, km)
        vehicles.append({"name": f"{cid}#{i + 1:02d}", "type": types[i % len(types)], "lat": p["lat"], "lon": p["lon"],
                         "weight": w, "km": km})
    return {"unit": cid, "side": side, "kind": "convoy", "name": cid, "vehicles": vehicles, "waypoints": [dict(pts[-1])],
            "speed_kmh": CONVOY_KMH, "link": link, "flow_t": flow_t}


def near(state: dict, center: dict, km: float) -> list[tuple[str, str, float]]:
    """Участки с потоком не меньше MIN_FLOW_T ближе km к center: (сторона, участок, поток)."""
    out = []
    for side in model.SIDES:
        for link, t in link_flows(state, side).items():
            if t >= MIN_FLOW_T and model.dist_km(link_mid(state, link), center) <= km:
                out.append((side, link, t))
    return out


def add_loss(state: dict, side: str, link: str, t: float) -> None:
    lb = state.setdefault("convoy_losses", {}).setdefault(side, {})
    lb[link] = lb.get(link, 0.0) + t


def depot_losses(state: dict, side: str) -> dict[str, float]:
    """Недовоз за сутки по складам: потери участка - на пути через него, по доле их потока."""
    losses = (state.get("convoy_losses") or {}).get(side) or {}
    out: dict[str, float] = {}
    rs = routes(state, side)
    for link, t in losses.items():
        users = [r for r in rs if any(key(a, b) == link for a, b in zip(r["path"], r["path"][1:]))]
        tot = sum(r["t"] for r in users)
        for r in users if tot else ():
            out[r["depot"]] = out.get(r["depot"], 0.0) + t * r["t"] / tot
    return out


def daily(state: dict) -> list[str]:
    """Удары ИИ по путям подвоза плана полётов суток (не слетанные игроком): удачный (вероятность - как у ЗРК в
    коридоре) - INTERDICT_LOSS суточного потока участка в недовоз."""
    lines = []
    a = state.get("ato") or {}
    for e in a.get("entries", []):
        if e["kind"] != "strike_supply_route" or e.get("resolved") or e["id"] in a.get("done", []):
            continue
        e["resolved"] = True
        link, foe = e["task"].get("link"), model.enemy(e["side"])
        flow = link_flows(state, foe).get(link, 0.0)
        if not flow:
            continue
        p = max(0.1, min(0.9, 0.7 - 0.1 * len(e["task"].get("threats", []))))
        if (a.get("lost") or {}).get(e["id"]):
            p *= 0.5
        r = model.rng(state, f"interdict-{e['id']}")
        if (r.random() < p) if r else p >= 0.5:
            t = INTERDICT_LOSS * flow
            add_loss(state, foe, link, t)
            lines.append(f"{e['title']}: колонны снабжения на участке {link.replace('>', ' - ')} разбиты, недовоз ~{t:.0f} т.")
    return lines

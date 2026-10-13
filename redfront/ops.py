"""Оперативный уровень наземной войны: стороны сами ставят задачи своим частям.

Карта - граф пунктов сектора (places + links), у каждого пункта владелец (side). Линия фронта - связи между пунктами
разных сторон. Раз в сутки командование стороны (commander) по позе из пакета доктрины (sim.posture):
  * offense - свободные части с боеспособностью от attack_min_strength наступают на соседние с фронтом пункты
    противника, ближние к цели операции (objectives сектора) - первыми;
  * defense - свободные части занимают незанятые пункты на линии фронта; лишние сильные части возвращают
    пустые (без противника) соседние пункты.
Общее для обеих сторон: часть в бою ниже withdraw_below и потерявшая боеспособность выходит из боя и отходит в
ближний свой пункт не на фронте; в тылу восстанавливается (refit_rate потерь в сутки) и с refit_ready снова в строю.
Пункт занят стороной, если рядом (capture_km) её часть и нет части противника.
Все коэффициенты - ОЦЕНКИ (раздел sim пакета доктрины). Без графа в кампании (старые кампании) уровень выключен.
"""
from __future__ import annotations

import heapq

from . import model

HOLD_KM = 2.0     # ОЦЕНКА: часть "стоит в пункте", если ближе этого


def enabled(state: dict) -> bool:
    return bool(state.get("links"))


def _sim(state: dict, side: str) -> dict:
    return model.doctrine(state, side)["sim"]


def graph(state: dict) -> dict[str, dict[str, float]]:
    """Граф пунктов; связи с разрушенным большим мостом закрыты, с разрушенным малым - длиннее на объезд
    (logistics.link_open / link_detour - здесь то же правило одним проходом по мостам: граф строится часто)."""
    from . import logistics
    closed, detour = set(), set()
    for br in logistics.objects(state, "bridge"):
        if br.get("damage", 0) >= 1.0:
            for l in br.get("links", []):
                (detour if logistics.is_minor(br) else closed).add(frozenset(l))
    extra = model.doctrine(state, state["player_side"])["sim"].get("bridge_detour_km", 0) if detour else 0
    g: dict[str, dict[str, float]] = {p: {} for p in state["places"]}
    for a, b in state.get("links", []):
        k = frozenset((a, b))
        if k in closed:
            continue
        d = model.dist_km(state["places"][a], state["places"][b])
        if k in detour:                                  # разрушен малый мост - объезд (ОЦЕНКА, sim.bridge_detour_km)
            d += extra
        g[a][b] = g[b][a] = d
    return g


def path(state: dict, a: str, b: str, side: str | None = None) -> list[str] | None:
    """Кратчайший путь по графу пунктов (км по прямой между пунктами); side - только через пункты этой стороны
    (кроме начального)."""
    g = graph(state)
    if side:
        g = {p: {q: w for q, w in nb.items() if owner(state, q) == side} for p, nb in g.items()}
    dist, prev, q = {a: 0.0}, {}, [(0.0, a)]
    while q:
        d, u = heapq.heappop(q)
        if u == b:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in g[u].items():
            if d + w < dist.get(v, 1e18):
                dist[v], prev[v] = d + w, u
                heapq.heappush(q, (d + w, v))
    if b not in dist:
        return None
    out = [b]
    while out[-1] != a:
        out.append(prev[out[-1]])
    return out[::-1]


_PK: dict | None = None   # кэш path_km на время решения командования (граф за это время не меняется)


def path_km(state: dict, a: str, b: str) -> float:
    if _PK is not None and (a, b) in _PK:
        return _PK[(a, b)]
    p = path(state, a, b)
    km = sum(model.dist_km(state["places"][x], state["places"][y]) for x, y in zip(p, p[1:])) if p else 1e18
    if _PK is not None:
        _PK[(a, b)] = _PK[(b, a)] = km
    return km


def owner(state: dict, p: str) -> str | None:
    return state["places"][p].get("side")


def front_links(state: dict) -> list[tuple[str, str]]:
    return [(a, b) for a, b in state.get("links", []) if owner(state, a) != owner(state, b)]


def front_nodes(state: dict, side: str) -> list[str]:
    g = graph(state)
    return [p for p in g if owner(state, p) == side and any(owner(state, q) != side for q in g[p])]


def _active(u: dict) -> bool:
    return u["state"] in ("march", "battle", "defend", "refit")


def _maneuver(state: dict, side: str | None = None) -> list[dict]:
    return [u for u in state["units"].values() if model.category(u) == "ground" and "route" in u
            and u["state"] not in ("destroyed", "pending") and (side is None or u["side"] == side)]


def node_of(state: dict, u: dict) -> str:
    """Пункт, где часть стоит (конец маршрута), иначе ближайший."""
    pos = model.unit_pos(state, u)
    return min(state["places"], key=lambda p: model.dist_km(pos, state["places"][p]))


def _units_near(state: dict, p: str, side: str, km: float) -> list[dict]:
    """Части стороны у пункта (отходящие пункт не держат)."""
    return [u for u in _maneuver(state, side) if _active(u) and u.get("order") != "withdraw"
            and model.dist_km(model.unit_pos(state, u), state["places"][p]) <= km]


def set_route(state: dict, u: dict, places: list[str], order: str) -> None:
    """Новый маршрут части по пунктам; положение сохраняется (проекция на новый маршрут)."""
    pos = model.unit_pos(state, u)
    if model.dist_km(pos, state["places"][places[0]]) > 0.5:
        places = [node_of(state, u)] + places if node_of(state, u) != places[0] else places
    u["route"] = places
    pts = model.route_points(state, u)
    u["progress_km"] = model.project_km(pts, pos) if len(places) > 1 else 0.0
    u["state"] = "march"
    u["order"] = order
    u["engaged"] = []
    u["defending"] = False


def _disengage(state: dict, u: dict) -> None:
    for f in u.get("engaged", []):
        fu = state["units"].get(f)
        if fu and u["id"] in fu.get("engaged", []):
            fu["engaged"].remove(u["id"])
    u["engaged"] = []


AXIS_REACH_KM = 80   # ОЦЕНКА: наступающая часть выбирает цель не дальше стольких км по графу (длинный фронт)


def objective(state: dict, side: str, u: dict | None = None) -> str | None:
    """Ближайшая не взятая цель операции для части: objectives стороны - список (одна ось на всех) или словарь осей
    {ось: [пункты]} - тогда по оси части (u['axis']), без оси - по ближней оси."""
    objs = (state.get("objectives") or {}).get(side) or []
    if isinstance(objs, str):
        objs = [objs]
    if isinstance(objs, dict):
        axis = (u or {}).get("axis")
        if axis not in objs:
            if u is None:
                lists = list(objs.values())
            else:
                here = node_of(state, u)
                lists = sorted(objs.values(), key=lambda l: min((path_km(state, here, o) for o in l
                                                                 if owner(state, o) != side), default=1e18))[:1]
            for l in lists:
                o = next((o for o in l if owner(state, o) != side), None)
                if o:
                    return o
            return None
        objs = objs[axis]
    return next((o for o in objs if owner(state, o) != side), None)   # цели по порядку: первая не взятая


def commander(state: dict, side: str) -> list[str]:
    global _PK
    if not enabled(state):
        return []
    _PK = {}
    try:
        return _commander(state, side)
    finally:
        _PK = None


def _commander(state: dict, side: str) -> list[str]:
    sim = _sim(state, side)
    lines = []
    own = _maneuver(state, side)
    front = set(front_nodes(state, side))
    rear = [p for p in state["places"] if owner(state, p) == side and p not in front]
    # 1. отход: в бою ниже withdraw_below или небоеспособна
    for u in own:
        weak = model.strength(u) < sim["withdraw_below"]
        if (u["state"] == "battle" and weak) or u["state"] == "halted":
            here = node_of(state, u)
            pool = rear or [p for p in state["places"] if owner(state, p) == side and p != here]   # тыла нет - в ближний свой
            dest = min(pool, key=lambda p: path_km(state, here, p), default=None)
            if dest is None:
                continue
            if dest == here:                                      # уже в тылу - восстановление
                _disengage(state, u)
                u["state"], u["order"] = "refit", None
                lines.append(f"{u['name']}: в тылу ({here}), восстановление.")
                continue
            _disengage(state, u)
            set_route(state, u, path(state, here, dest), "withdraw")
            lines.append(f"{u['name']}: ({model.strength(u):.0%}) выходит из боя, отходит в {dest}.")
    # 2. тыл: дошедшие до места отхода - восстановление; восстановившиеся - в строй
    for u in own:
        if u.get("order") == "withdraw" and u["state"] == "defend":
            u["state"], u["order"] = "refit", None
            lines.append(f"{u['name']}: в тылу ({u['route'][-1]}), восстановление.")
        if u["state"] == "refit":                                 # без снабжения - вдвое медленнее
            for c in u["composition"]:
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) * (1 - sim["refit_rate"] * u.get("supply", 1.0))
            if model.strength(u) >= sim["refit_ready"]:
                u["state"] = "defend"
                lines.append(f"{u['name']}: восстановлена до {model.strength(u):.0%}, в строю.")
    # 3. свободные части - по позе стороны; не в бою - пополнение на месте (медленнее, чем в тылу)
    free = [u for u in own if u["state"] == "defend" and not u.get("engaged")]
    for u in free:
        if model.strength(u) < sim["refit_ready"]:
            for c in u["composition"]:
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) * (1 - sim["refit_rate"] * sim["refit_in_line"])
    posture = sim.get("posture") or "defense"
    if posture == "offense" and not any(objective(state, side, u) for u in free):
        posture = "defense"                                       # цели операции достигнуты - удерживать
    g = graph(state)
    if posture == "offense":
        all_targets = {q for p in front for q in g[p] if owner(state, q) != side}
        attackers = []
        for u in sorted(free, key=lambda u: -model.strength(u)):
            obj = objective(state, side, u)
            if model.strength(u) < sim["attack_min_strength"] or not all_targets or not obj:
                if obj is None and model.strength(u) >= sim["attack_min_strength"]:
                    attackers.append(u)                           # ось выполнена - часть в оборону (ниже)
                continue
            here = node_of(state, u)
            # фронт длинный: часть выбирает из пунктов в досягаемости (AXIS_REACH_KM, ОЦЕНКА), ближних к цели своей оси
            reach = [q for q in all_targets if q != here and path_km(state, here, q) <= AXIS_REACH_KM]
            targets = sorted(reach or [q for q in all_targets if q != here], key=lambda q: path_km(state, q, obj))
            top = targets[:sim.get("choice_width", 2)]            # ближние к цели
            if not top:
                continue
            r = model.rng(state, f"attack-{u['id']}")
            if r:                                # направление - с весами: ближе к части - вероятнее (ОЦЕНКА)
                w = [1.0 / max(1.0, path_km(state, here, q)) for q in top]
                t = r.choices(top, weights=w)[0]
            else:
                t = min(top, key=lambda q: path_km(state, here, q))
            p = path(state, here, t)
            if p and len(p) > 1:
                set_route(state, u, p, "attack")
                lines.append(f"{u['name']}: наступление на {t} ({' - '.join(p)}).")
    if posture != "offense" or attackers:
        free = attackers if posture == "offense" else free      # в наступлении - только части с выполненной осью
        holding = {node_of(state, u) for u in own if u["state"] in ("defend", "battle") and
                   model.dist_km(model.unit_pos(state, u), state["places"][node_of(state, u)]) <= HOLD_KM}
        need = [p for p in front if p not in holding and not _units_near(state, p, model.enemy(side), HOLD_KM)]
        spare = []
        for u in free:
            here = node_of(state, u)
            if here in front and here in holding and here not in [node_of(state, x) for x in free if x is not u and x["id"] < u["id"]]:
                continue                                          # держит свой пункт фронта
            if need:
                t = min(need, key=lambda p: path_km(state, here, p))
                need.remove(t)
                p = path(state, here, t)
                if p and len(p) > 1:
                    set_route(state, u, p, "hold")
                    lines.append(f"{u['name']}: выдвигается на рубеж {t}.")
                    continue
            spare.append(u)
        for u in spare:                                           # лишние сильные - вернуть пустые пункты
            if model.strength(u) < sim["attack_min_strength"]:
                continue
            here = node_of(state, u)
            empty = [q for q in g[here] if owner(state, q) != side and not _units_near(state, q, model.enemy(side), sim["contact_km"])]
            if empty:
                t = empty[0]
                set_route(state, u, [here, t], "attack")
                lines.append(f"{u['name']}: контратака - вернуть {t}.")
    return lines


def capture(state: dict) -> list[str]:
    """Владельцы пунктов после марша: рядом часть стороны и нет противника - пункт её."""
    if not enabled(state):
        return []
    lines = []
    for p in state["places"]:
        for side in model.SIDES:
            if owner(state, p) == side:
                continue
            km = _sim(state, side)["capture_km"]
            if _units_near(state, p, side, km) and not _units_near(state, p, model.enemy(side), _sim(state, side)["contact_km"]):
                state["places"][p]["side"] = side
                lines.append(f"Пункт {p} занят: {'красные' if side == 'red' else 'синие'}.")
                break
    return lines

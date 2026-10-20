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
    """Граф пунктов (км - по дороге, если она известна); связи с разрушенным большим мостом закрыты, с разрушенным малым - длиннее на объезд
    (logistics.link_open / link_detour - здесь то же правило одним проходом по мостам: граф строится часто)."""
    from . import logistics
    closed, detour = set(), set()
    for br in logistics.objects(state, "bridge"):
        if br.get("damage", 0) >= 1.0:
            for l in br.get("links", []):
                (detour if logistics.is_minor(br) else closed).add(frozenset(l))
    extra = model.doctrine(state, state["player_side"])["sim"].get("bridge_detour_km", 0) if detour else 0
    g: dict[str, dict[str, float]] = {p: {} for p in state["places"]}
    rk = state.get("road_km") or {}              # длина по дороге (roads.apply), иначе - по прямой
    for a, b in state.get("links", []):
        k = frozenset((a, b))
        if k in closed:
            if _CROSS is None:
                continue                                 # подвоз и колонны снабжения - не через разрушенный большой мост
            d_c = model.doctrine(state, _CROSS)["sim"].get("crossing_km")
            if not d_c:
                continue
            d = (rk.get(f"{a}>{b}") or rk.get(f"{b}>{a}") or model.dist_km(state["places"][a], state["places"][b])) + d_c
            g[a][b] = g[b][a] = d                        # форсирование с ходу (ОЦЕНКА, sim.crossing_km)
            continue
        d = rk.get(f"{a}>{b}") or rk.get(f"{b}>{a}") or model.dist_km(state["places"][a], state["places"][b])
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


_CROSS: str | None = None   # сторона, чья командование решает: разрушенный большой мост для её частей - форсирование
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
    u["dig_h"] = 0                               # на новом рубеже окапываться заново
    u["speed_k"] = 1.0
    u.pop("op_role", None)


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


def commander(state: dict, side: str, frac_day: float = 1.0) -> list[str]:
    global _PK, _CROSS
    if not enabled(state):
        return []
    _PK, _CROSS = {}, side
    try:
        lines = _commander(state, side, frac_day)
        lines += _operations(state, side, frac_day)
        return lines
    finally:
        _PK, _CROSS = None, None


def _commander(state: dict, side: str, frac_day: float = 1.0) -> list[str]:
    """frac_day - доля суток до следующего решения: восстановление в тылу и на месте - за неё (refit_rate в сутки)."""
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
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) * (1 - sim["refit_rate"] * frac_day * u.get("supply", 1.0))
            if model.strength(u) >= sim["refit_ready"]:
                u["state"] = "defend"
                lines.append(f"{u['name']}: восстановлена до {model.strength(u):.0%}, в строю.")
    # 3. свободные части - по позе стороны; не в бою - пополнение на месте (медленнее, чем в тылу)
    free = [u for u in own if u["state"] == "defend" and not u.get("engaged")]
    for u in free:
        if model.strength(u) < sim["refit_ready"]:
            for c in u["composition"]:
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) * (1 - sim["refit_rate"] * frac_day * sim["refit_in_line"])
    # десант в резерве и высаженный (держит пункт до подхода своих) - не в распоряжении командования фронта (assault.py)
    free = [u for u in free if u.get("order") not in ("reserve", "airhead")]
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


def _power_near(state: dict, side: str, pos: dict, km: float) -> float:
    from . import sim as _s
    return sum(_s.power(state, u) for u in _maneuver(state, side) if _active(u)
               and model.dist_km(model.unit_pos(state, u), pos) <= km)


COMMIT_KM = 100   # ОЦЕНКА: второй эшелон вводится не дальше стольких км от назначенного района (по прямой)


def success_entry(state: dict, u: dict, used: dict | None = None) -> str | None:
    """Полоса успеха для ввода второго эшелона: свой пункт фронта не дальше COMMIT_KM от назначенного района, где свои
    сильнее всего относительно противника (силы в 25 км; уже назначенные в эту полосу части - минус); вводится в свой
    пункт за ним (не на самом переднем крае), иначе в сам пункт. used - сколько частей уже вводится в каждую полосу."""
    side = u["side"]
    home = state["places"].get((u.get("route") or [None])[0])
    front = [p for p in front_nodes(state, side) if not home or model.dist_km(state["places"][p], home) <= COMMIT_KM]
    if not front:
        return None
    foe = model.enemy(side)
    used = used if used is not None else {}
    def score(p):
        pos = state["places"][p]
        return _power_near(state, side, pos, 25) - _power_near(state, foe, pos, 25) - 40.0 * used.get(p, 0)
    best = max(front, key=score)
    used[best] = used.get(best, 0) + 1
    g = graph(state)
    rear = [q for q in g[best] if owner(state, q) == side and q not in front_nodes(state, side)]
    return min(rear, key=lambda q: model.dist_km(state["places"][q], state["places"][best])) if rear else best


def _operations(state: dict, side: str, frac_day: float) -> list[str]:
    """Оперативные приёмы доктрины (sim стороны, ОЦЕНКИ): подготовка обороны, передовой отряд, ОМГ (ОВД);
    сдерживание и контрудар резервом (НАТО)."""
    from . import sim as _s
    sim = _sim(state, side)
    lines = []
    own = _maneuver(state, side)
    foe = model.enemy(side)
    g = graph(state)
    # подготовка обороны: часть в обороне без боя окапывается (часы)
    for u in own:
        if u["state"] == "defend" and not u.get("engaged"):
            u["dig_h"] = u.get("dig_h", 0) + 24 * frac_day
    # сдерживание (НАТО): против противника сильнее в delay_ratio раз - отход на следующий рубеж, не до разгрома
    if sim.get("delay_ratio"):
        for u in own:
            if u["state"] != "battle" or not u.get("defending") or model.strength(u) >= sim.get("delay_min_strength", 0):
                continue
            enemy = sum(_s.power(state, state["units"][f]) for f in u.get("engaged", []) if f in state["units"])
            if enemy < sim["delay_ratio"] * max(1e-6, _s.power(state, u)):
                continue
            here = node_of(state, u)
            back = [q for q in g[here] if owner(state, q) == side and q != here]
            if not back:
                continue
            t = max(back, key=lambda q: min((model.dist_km(state["places"][q], model.unit_pos(state, e))
                                              for e in _maneuver(state, foe) if _active(e)), default=0))
            _disengage(state, u)
            set_route(state, u, [here, t], "delay")
            lines.append(f"{u['name']}: сдерживание - отходит на следующий рубеж {t}.")
    free = [u for u in own if u["state"] == "defend" and not u.get("engaged") and u.get("order") not in ("reserve", "airhead")
            and model.strength(u) >= sim.get("attack_min_strength", 0.7)]
    # контрудар резервом (НАТО): по вклинившейся части противника, которая слабее
    if sim.get("counterattack"):
        for u in sorted(free, key=lambda x: -_s.power(state, x)):
            here = node_of(state, u)
            pw = _s.power(state, u)
            tgt = [e for e in _maneuver(state, foe) if _active(e) and e.get("order") != "withdraw"
                   and owner(state, node_of(state, e)) == side and pw >= sim.get("counter_ratio", 1.2) * _s.power(state, e)
                   and path_km(state, here, node_of(state, e)) <= sim.get("counter_km", 60)]
            if not tgt:
                continue
            e = min(tgt, key=lambda x: path_km(state, here, node_of(state, x)))
            p = path(state, here, node_of(state, e))
            if p and len(p) > 1:
                set_route(state, u, p, "attack")
                u["op_role"] = "counter"
                free.remove(u)
                lines.append(f"{u['name']}: контрудар по вклинившейся {e['name']} ({p[-1]}).")
    if sim.get("posture") != "offense":
        return lines
    # передовой отряд (ОВД): сильнейшая часть - на рубеж в глубине за фронтом, быстрее главных сил
    if sim.get("forward_detachment") and not any(u.get("op_role") == "forward" for u in own):
        cand = [u for u in own if u["state"] in ("defend", "march") and u.get("order") in (None, "attack", "hold")
                and model.strength(u) >= 0.85 and not u.get("engaged")]
        if cand:
            u = max(cand, key=lambda x: _s.power(state, x))
            obj = objective(state, side, u)
            here = node_of(state, u)
            p = path(state, here, obj) if obj else None
            if p and len(p) > 1:
                front = set(front_nodes(state, side))
                k = next((i for i, q in enumerate(p) if q not in front and owner(state, q) != side), len(p) - 1)
                p = p[:min(len(p), k + int(sim.get("forward_depth", 2)))]
                if len(p) > 1:
                    set_route(state, u, p, "attack")
                    u["op_role"], u["speed_k"] = "forward", sim.get("forward_speed", 1.5)
                    lines.append(f"{u['name']}: передовой отряд - выйти на рубеж {p[-1]} раньше противника ({' - '.join(p)}).")
    # ОМГ (ОВД): после прорыва - в глубину, на склады и мосты противника
    if sim.get("omg") and state.get("day", 1) >= sim.get("omg_from_day", 2) and not any(u.get("op_role") == "omg" for u in own):
        bk = sim.get("breakthrough_km", 15)
        enemy_units = [e for e in _maneuver(state, foe) if _active(e)]
        gap = [p for p in front_nodes(state, side) for q in g[p] if owner(state, q) == foe
               and not any(model.dist_km(state["places"][q], model.unit_pos(state, e)) <= bk for e in enemy_units)]
        targets = {d.get("place") for d in state["units"].values() if model.category(d) in ("depot", "bridge")
                   and d.get("side") == foe and d.get("state") != "lost" and d.get("place") in state["places"]}
        targets |= {q for d in state["units"].values() if model.category(d) == "bridge"
                    for l in d.get("links", []) for q in l if owner(state, q) == foe}
        cand = [u for u in own if u["state"] in ("defend", "march") and not u.get("engaged") and model.strength(u) >= 0.8
                and u.get("op_role") != "forward"]
        if gap and targets and cand:
            u = max(cand, key=lambda x: _s.power(state, x))
            here = node_of(state, u)
            t = min(targets, key=lambda q: path_km(state, here, q))
            p = path(state, here, t)
            if p and len(p) > 1 and path_km(state, here, t) < 1e17:
                set_route(state, u, p, "attack")
                u["op_role"], u["speed_k"] = "omg", sim.get("omg_speed", 1.3)
                lines.append(f"{u['name']}: оперативная маневренная группа - прорыв в глубину на {t} ({' - '.join(p)}).")
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
                for d in state["units"].values():       # склад в занятом пункте - потерян стороной
                    if model.category(d) == "depot" and d.get("place") == p and d.get("side") != side and d.get("state") != "lost":
                        d["state"] = "lost"
                        lines.append(f"{d['name']}: потерян - пункт {p} занят противником.")
                break
    return lines

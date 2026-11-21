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

GARRISON_CUT_DAYS = 4   # ОЦЕНКА: гарнизон без подвоза держится столько суток, затем прорывается к своим
GARRISON_HOLD = 0.5   # ОЦЕНКА: гарнизон города отходит при вдвое меньшей боеспособности, чем полевая часть
HOLD_KM = 2.0     # ОЦЕНКА: часть "стоит в пункте", если ближе этого


def enabled(state: dict) -> bool:
    return bool(state.get("links"))


def _sim(state: dict, side: str) -> dict:
    return model.doctrine(state, side)["sim"]


def graph(state: dict) -> dict[str, dict[str, float]]:
    """Граф пунктов (км - по дороге, если она известна); связи с разрушенным большим мостом закрыты, с разрушенным малым - длиннее на объезд
    (logistics.link_open / link_detour - здесь то же правило одним проходом по мостам: граф строится часто)."""
    if _G is not None and _G[0] == _CROSS:     # граф на время решения командования стороны - один
        return _G[1]
    from . import logistics
    closed, detour = set(), set()
    for br in logistics.objects(state, "bridge"):
        if br.get("damage", 0) >= 1.0:
            for l in br.get("links", []):
                (detour if logistics.is_minor(br) else closed).add(frozenset(l))
    extra = model.doctrine(state, _CROSS or state["player_side"])["sim"].get("bridge_detour_km", 0) if detour else 0   # объезд - по доктрине решающей стороны
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
    if _G is not None:
        _G[:] = [_CROSS, g]
    return g


def path(state: dict, a: str, b: str, side: str | None = None, avoid: set | None = None) -> list[str] | None:
    """Кратчайший путь по графу пунктов (км по прямой между пунктами); side - только через пункты этой стороны
    (кроме начального); avoid - в обход этих пунктов (политические ограничения сценария)."""
    g = graph(state)
    if side:
        g = {p: {q: w for q, w in nb.items() if owner(state, q) == side} for p, nb in g.items()}
    if avoid:
        g = {p: {q: w for q, w in nb.items() if q not in avoid or q == b} for p, nb in g.items()}
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
_G: list | None = None    # кэш графа на то же время: [сторона, граф]


def path_km(state: dict, a: str, b: str) -> float:
    """Длина кратчайшего пути по графу - по дорогам (road_km), с объездами и форсированием, как и сам путь (path)."""
    if _PK is not None and (a, b) in _PK:
        return _PK[(a, b)]
    p = path(state, a, b)
    g = graph(state)
    km = sum(g[x].get(y, model.dist_km(state["places"][x], state["places"][y])) for x, y in zip(p, p[1:])) if p else 1e18
    if _PK is not None:
        _PK[(a, b)] = _PK[(b, a)] = km
    return km


def owner(state: dict, p: str) -> str | None:
    return state["places"][p].get("side")


def banned(state: dict, side: str) -> set[str]:
    """Пункты, куда сторона по сценарию не идёт (off_limits: политические ограничения) - ни целью, ни транзитом."""
    return set((state.get("off_limits") or {}).get(side, []))


def own_path(state: dict, side: str, a: str, b: str) -> list[str] | None:
    """Путь в тылу/вдоль фронта: по своей земле, иначе - в обход запретных пунктов, иначе - кратчайший."""
    return path(state, a, b, side=side) or path(state, a, b, avoid=banned(state, side) - {b})   # запретные - никогда


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


_NODE: dict = {}


def node_of(state: dict, u: dict) -> str:
    """Ближайший к части пункт (кэш по месту: пункты не двигаются)."""
    pos = model.unit_pos(state, u)
    key = (id(state["places"]), len(state["places"]), round(pos["lat"], 4), round(pos["lon"], 4))
    n = _NODE.get(key)
    if n is None:
        if len(_NODE) > 50000:
            _NODE.clear()
        n = _NODE[key] = min(state["places"], key=lambda p: model.dist_km(pos, state["places"][p]))
    return n


def _units_near(state: dict, p: str, side: str, km: float) -> list[dict]:
    """Части стороны у пункта (отходящие пункт не держат)."""
    return [u for u in _maneuver(state, side) if _active(u) and u.get("order") != "withdraw"
            and model.dist_km(model.unit_pos(state, u), state["places"][p]) <= km]


def set_route(state: dict, u: dict, places: list[str], order: str) -> None:
    """Новый маршрут части по пунктам; положение сохраняется (проекция на новый маршрут)."""
    pos = model.unit_pos(state, u)
    on_route = False
    if len(places) > 1 and model.dist_km(pos, state["places"][places[0]]) > 0.5:   # уже на первом участке нового маршрута
        pts = model.route_points(state, {"route": places[:2]})
        on_route = model.dist_km(pos, model.point_at_km(pts, model.project_km(pts, pos))[0]) <= 0.5
    if not on_route and model.dist_km(pos, state["places"][places[0]]) > 0.5:
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


HOLD_REACH_KM = 150   # ОЦЕНКА: на пустой рубеж фронта выдвигается часть не дальше стольких км по своей земле


def _route_len(state: dict, p: list[str]) -> float:
    return sum(model.dist_km(state["places"][x], state["places"][y]) for x, y in zip(p, p[1:]))


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


def morale(state: dict, side: str) -> list[str]:
    """Надлом стороны (сценарий morale_break: [{side, place, quality_k, note}]): потерян ключевой пункт - выучка и
    стойкость всех её манёвренных частей падают в quality_k раз, один раз (Сухуми 27.09.1993 - распад грузинской
    группировки; ОЦЕНКА величины)."""
    lines = []
    for i, row in enumerate(state.get("morale_break") or []):
        if row.get("side") != side or row.get("done") or row.get("place") not in state["places"]:
            continue
        if owner(state, row["place"]) == side:
            continue
        row["done"] = state.get("day")
        k = float(row.get("quality_k", 0.7))
        from . import morale as _m
        for u in _maneuver(state, side):
            u["quality"] = u.get("quality", 1.0) * k
            _m.hit(state, u, float(row.get("morale_hit", 0.3)))
        lines.append(f"Потерян {row['place']}: надлом обороны - {row.get('note') or 'войска стороны деморализованы'}.")
    return lines


def commander(state: dict, side: str, frac_day: float = 1.0) -> list[str]:
    global _PK, _CROSS, _G
    if not enabled(state):
        return []
    _PK, _CROSS, _G = {}, side, [None, None]
    try:
        lines = morale(state, side)
        lines += _commander(state, side, frac_day)
        lines += _operations(state, side, frac_day)
        return lines
    finally:
        _PK, _CROSS, _G = None, None, None


def _commander(state: dict, side: str, frac_day: float = 1.0) -> list[str]:
    """frac_day - доля суток до следующего решения: восстановление в тылу и на месте - за неё (refit_rate в сутки)."""
    sim = _sim(state, side)
    lines = []
    own = _maneuver(state, side)
    front = set(front_nodes(state, side))
    rear = [p for p in state["places"] if owner(state, p) == side and p not in front]
    # 0. гарнизон без подвоза (окружён, logistics.supply) дольше GARRISON_CUT_DAYS - прорыв к своим, если путь по своей
    # земле есть (Лиман, 1.10.2022 - ОЦЕНКА срока); пути нет - держится до конца
    for u in own:
        if u.get("order") != "garrison":
            continue
        if u.get("supply_frac", 1.0 if u.get("supply", 1.0) >= 1.0 else 0.0) > 0:
            u.pop("cut_since", None)
            continue
        u.setdefault("cut_since", state["day"])
        if state["day"] - u["cut_since"] < GARRISON_CUT_DAYS:
            continue
        here = node_of(state, u)
        rear_ = [p for p in (rear or [q for q in state["places"] if owner(state, q) == side]) if p != here]
        # путь по своей земле, нет - напрямую (прорыв через кольцо)
        if rear_:
            dest = min(rear_, key=lambda p: path_km(state, here, p))
            p = own_path(state, side, here, dest)
            if not p:
                continue
            _disengage(state, u)
            set_route(state, u, p, "withdraw")
            lines.append(f"{u['name']}: гарнизон в окружении {state['day'] - u['cut_since']} сут. - прорыв к своим, отход в {dest}.")
    # 1. отход: в бою ниже withdraw_below или небоеспособна
    for u in own:
        from . import morale as _m               # низкая мораль - отход раньше
        weak = model.strength(u) < (sim["withdraw_below"] + _m.withdraw_shift(u)) * (GARRISON_HOLD if u.get("order") == "garrison" else 1.0)
        if (u["state"] == "battle" and weak) or u["state"] == "halted":
            here = node_of(state, u)
            pool = rear or [p for p in state["places"] if owner(state, p) == side and p != here]   # тыла нет - в ближний свой
            if _units_near(state, here, model.enemy(side), sim["contact_km"]):   # противник уже здесь - не восстанавливаться
                pool = [p for p in pool if p != here]                            # под огнём, а отходить дальше
            dest = min(pool, key=lambda p: path_km(state, here, p), default=None)
            if dest is None:
                continue
            if dest == here:                                      # уже в тылу - восстановление
                _disengage(state, u)
                u["state"], u["order"] = "refit", None
                lines.append(f"{u['name']}: в тылу ({here}), восстановление.")
                continue
            p = path(state, here, dest, side=side)  # отход - только по своей земле
            if not p:                                # окружена (Ткварчели 1993): через противника не отходит - держится
                if u["state"] == "halted":           # на месте и восстанавливается под огнём
                    u["state"], u["defending"] = "refit", True
                    lines.append(f"{u['name']}: ({model.strength(u):.0%}) в окружении - отхода нет, держится в районе {here}.")
                continue
            _disengage(state, u)
            set_route(state, u, p, "withdraw")
            lines.append(f"{u['name']}: ({model.strength(u):.0%}) выходит из боя, отходит в {dest}.")
    # 1а. закрепление: часть дошла до своего рубежа (dig_in_at, сценарий: плацдармы 1973) - гарнизон, дальше не идёт
    for u in own:
        if u.get("dig_in_at") and u["state"] == "defend" and u.get("order") != "garrison" \
                and node_of(state, u) in u["dig_in_at"] and owner(state, node_of(state, u)) == side:
            u["order"] = "garrison"
            u["route"], u["progress_km"] = [node_of(state, u)], 0.0
            lines.append(f"{u['name']}: закрепилась на рубеже {node_of(state, u)}.")
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
    # гарнизон (order garrison, сценарий) держит свой пункт: не выдвигается и не наступает
    free = [u for u in free if u.get("order") not in ("reserve", "airhead", "garrison")]
    if ground_control(state, side):              # части под приказом игрока - не в распоряжении командования стороны
        lines += player_orders(state, side)
        free = [u for u in free if not u.get("player_order")]
    posture = posture_of(state, side)
    if posture == "offense" and not any(objective(state, side, u) for u in free) and not objective(state, side, None):
        posture = "defense"                                       # цели операции достигнуты - удерживать
    g = graph(state)
    if posture == "offense":
        ban = banned(state, side)                # политические ограничения сценария
        all_targets = {q for p in front for q in g[p] if owner(state, q) != side and q not in ban}
        if ground_umbrella(state, side):         # доктрина "зонтика" (Египет 1973): наступать - только под своими ЗРК
            under = {q for q in all_targets if _under_sams(state, side, state["places"][q])}
            all_targets = under
        held = held_cities(state, model.enemy(side))   # города с гарнизоном - обход, не штурм (кроме цели оси)
        attackers = []
        for u in sorted(free, key=lambda u: -model.strength(u)):
            obj = objective(state, side, u)
            if obj is None and u.get("axis"):   # своя ось выполнена - на ближнюю невыполненную (Сухуми взят - на Очамчиру)
                obj = objective(state, side, {k: v for k, v in u.items() if k != "axis"})
            if model.strength(u) < sim["attack_min_strength"] or not all_targets or not obj:
                if obj is None and model.strength(u) >= sim["attack_min_strength"]:
                    attackers.append(u)                           # ось выполнена - часть в оборону (ниже)
                continue
            here = node_of(state, u)
            # фронт длинный: часть выбирает из пунктов в досягаемости (AXIS_REACH_KM, ОЦЕНКА), ближних к цели своей оси
            reach = [q for q in all_targets if q != here and path_km(state, here, q) <= AXIS_REACH_KM
                     and (q not in held or q == obj)] or \
                    [q for q in all_targets if q != here and path_km(state, here, q) <= AXIS_REACH_KM]
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
            p = path(state, here, t, avoid=ban | (held - {t})) or path(state, here, t, avoid=ban)
            if p and len(p) > 1:
                set_route(state, u, p, "attack")
                lines.append(f"{u['name']}: наступление на {t} ({' - '.join(p)}).")
    if posture != "offense" and halt_today(state, side):   # прекращение огня, срыв наступления (сценарий: halt) -
        from . import sim as _s                  # наступление на марше прекращается, рубеж - ближний свой пункт участка
        for u in free + [x for x in own if x["state"] == "march" and x.get("order") == "attack" and not x.get("engaged")
                         and not (ground_control(state, side) and x.get("player_order"))]:
            if u["state"] != "march" or u.get("order") != "attack":
                continue
            cl = _s.current_link(state, u)
            if not cl:
                continue
            stop = cl[0] if owner(state, cl[1]) != side else cl[1]
            if owner(state, stop) != side:
                continue
            set_route(state, u, [cl[0], cl[1]] if stop == cl[1] else [cl[1], cl[0]], "hold")
            lines.append(f"{u['name']}: наступление прекращено - отход на рубеж {stop}.")
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
                p = own_path(state, side, here, t)       # на рубеж - по своей земле, не через противника
                if p and len(p) > 1 and _route_len(state, p) <= HOLD_REACH_KM:   # не через полкарты в обход
                    need.remove(t)
                    set_route(state, u, p, "hold")
                    lines.append(f"{u['name']}: выдвигается на рубеж {t}.")
                    continue
            spare.append(u)
        for u in spare:                                           # лишние сильные - вернуть пустые пункты
            if model.strength(u) < sim["attack_min_strength"]:
                continue
            here = node_of(state, u)
            empty = [q for q in g[here] if owner(state, q) != side and state["places"][q].get("side0") == side   # только
                     and q not in banned(state, side)                                                           # свои исходно
                     and not _units_near(state, q, model.enemy(side), sim["contact_km"])]
            if empty:
                t = empty[0]
                set_route(state, u, [here, t], "attack")
                lines.append(f"{u['name']}: контратака - вернуть {t}.")
    return lines


ALT_OFFENSE_RATIO = 0.9   # ОЦЕНКА: альтернативный ход - переход в наступление по дате сценария, только если сила
ALT_CULMINATE = 0.5       # стороны не меньше этой доли силы противника; наступление выдыхается ниже ALT_CULMINATE


def _ground_power(state: dict, side: str) -> float:
    from . import sim as _s
    return sum(_s.power(state, u) for u in _maneuver(state, side) if _active(u))


# ---- управление наземными войсками игроком (настройка ground_control) ----
PLAYER_ORDERS = {"hold": "hold", "attack": "attack", "move": "hold", "withdraw": "withdraw"}   # приказ -> order модели


def ground_control(state: dict, side: str) -> bool:
    return side == state.get("player_side") and bool((state.get("settings") or {}).get("ground_control"))


def give_order(state: dict, uid: str, kind: str, place: str | None = None) -> str:
    """Приказ игрока части своей стороны: hold - держать пункт (где стоит или place), move - выйти в place и занять
    оборону, attack - наступать на place (пункт противника или свой), withdraw - отойти в place; auto - снова на
    усмотрение командования стороны. Выполняется командованием (player_orders) на ближайшем шаге модели."""
    u = state["units"].get(uid)
    side = state.get("player_side")
    if not u or u["side"] != side or "route" not in u or model.category(u) != "ground" or u.get("attached_to"):
        raise ValueError("приказ - только манёвренной части своей стороны")
    if not ground_control(state, side):
        raise ValueError("управление наземными войсками выключено в настройках кампании")
    if u["state"] in ("destroyed", "pending"):
        raise ValueError(f"{u['name']}: часть не в строю")
    if kind == "auto":
        u.pop("player_order", None)
        return f"{u['name']}: снова на усмотрение командования."
    if kind not in PLAYER_ORDERS:
        raise ValueError(f"нет приказа '{kind}'")
    if kind == "hold" and not place:
        place = node_of(state, u)
    if place not in state["places"]:
        raise ValueError("укажите пункт")
    if kind in ("move", "withdraw") and owner(state, place) != side:
        raise ValueError(f"{place}: пункт противника - для него приказ 'наступать'")
    if place in set((state.get("off_limits") or {}).get(side, [])):
        raise ValueError(f"{place}: по сценарию сторона туда не идёт")
    u["player_order"] = {"type": kind, "place": place, "day": state["day"], "done": False}
    return f"{u['name']}: приказ - {dict(hold='держать', move='выйти в', attack='наступать на', withdraw='отойти в')[kind]} {place}."


def player_orders(state: dict, side: str) -> list[str]:
    """Выполнить приказы игрока: маршрут к пункту (наступление - в обход городов с гарнизоном, отход - по своей
    земле). Часть в бою выходит из него (приказ отойти) или ведёт бой дальше (остальные приказы - после боя)."""
    lines = []
    for u in _maneuver(state, side):
        o = u.get("player_order")
        if not o or o.get("done") or u["state"] in ("destroyed", "pending", "halted"):
            continue
        if u["state"] == "battle" and o["type"] != "withdraw":
            continue                             # сначала бой; приказ - когда выйдет из него
        here = node_of(state, u)
        t = o["place"]
        if here == t and o["type"] in ("hold", "move"):
            u["route"], u["progress_km"] = [here], 0.0
            u["state"], u["order"], u["defending"] = "defend", "hold", True
            o["done"] = True
            lines.append(f"{u['name']}: по приказу держит {t}.")
            continue
        p = bypass_path(state, side, here, t) if o["type"] == "attack" else own_path(state, side, here, t)
        if not p or len(p) < 2:
            lines.append(f"{u['name']}: приказ не выполнить - нет пути до {t}.")
            o["done"] = True
            continue
        if u["state"] == "battle":
            _disengage(state, u)
        set_route(state, u, p, PLAYER_ORDERS[o["type"]])
        o["done"] = True
        lines.append(f"{u['name']}: по приказу - {' - '.join(p)}.")
    return lines


def halt_today(state: dict, side: str) -> bool:
    """Сегодня по сценарию наступление стороны прекращается (posture_days: "halt": [стороны] в день from_day)."""
    return any(row.get("from_day") == state.get("day") and side in (row.get("halt") or [])
               for row in state.get("posture_days") or [])


def ground_umbrella(state: dict, side: str) -> bool:
    """Наступление только под зонтиком своих ЗРК (doctrine umbrella.ground); сценарий может снять зонтик на сутки
    (posture_days: "umbrella": {сторона: false} - 14.10.1973, наступление к перевалам)."""
    umb = model.doctrine(state, side).get("umbrella") or {}
    if not umb.get("ground"):
        return False
    on = True
    for row in sorted(state.get("posture_days") or [], key=lambda r: r.get("from_day", 0)):
        if state["day"] >= row.get("from_day", 0) and side in (row.get("umbrella") or {}):
            on = bool(row["umbrella"][side])
    return on


def _under_sams(state: dict, side: str, pos: dict) -> bool:
    """Пункт под зонтиком ЗРК средней и большой дальности стороны (не войсковая ПВО и не объектовая)."""
    from . import planner
    km = (model.doctrine(state, side).get("umbrella") or {}).get("ground_km", 10)
    for u in state["units"].values():
        if (u["side"] == side and u.get("role") in ("sam_medium", "sam_long") and not u.get("attached_to")
                and not u.get("point") and u["state"] not in ("destroyed", "pending") and model.strength(u) >= 0.5):
            if model.dist_km(model.unit_pos(state, u), pos) <= km + float(planner.threat_radius_km(u) or 0):
                return True
    return False


def posture_of(state: dict, side: str) -> str:
    """Поза стороны: сценарий (posture, смена по дням posture_days) сильнее доктрины. Альтернативный ход
    (model.influence): смена позы по дате - только при достаточной силе, наступление выдыхается при её потере."""
    posture = (state.get("posture") or {}).get(side) or _sim(state, side).get("posture") or "defense"
    alt = model.influence(state) == "alternative"
    ratio = None
    def r_():
        own, foe = _ground_power(state, side), _ground_power(state, model.enemy(side))
        return own / foe if foe > 0 else 9.0
    for row in sorted(state.get("posture_days") or [], key=lambda r: r.get("from_day", 0)):
        if state["day"] >= row.get("from_day", 0) and row.get(side):
            if alt and row[side] == "offense":
                ratio = r_() if ratio is None else ratio
                if ratio < ALT_OFFENSE_RATIO:
                    continue                     # по дате - да, а сил нет: ждёт
            posture = row[side]
    if alt and posture == "offense":
        ratio = r_() if ratio is None else ratio
        if ratio < ALT_CULMINATE:
            posture = "defense"                  # наступление выдохлось
    return posture


def bypass_path(state: dict, side: str, a: str, b: str) -> list[str] | None:
    """Путь наступающего: в обход городов противника с гарнизоном (held_cities), кроме конечного; обхода нет - прямо."""
    held = held_cities(state, model.enemy(side)) - {b}
    ban = banned(state, side) - {b}
    return (path(state, a, b, avoid=held | ban) if held else None) or path(state, a, b, avoid=ban)   # запретные - никогда


def route_from(state: dict, side: str, u: dict, t: str) -> list[str] | None:
    """Новый маршрут части к t (bypass_path): стоящей - от её пункта; идущей - с текущего участка (не от ближайшего
    пункта: им может оказаться город противника рядом с дорогой)."""
    if u["state"] == "march":
        from . import sim as _s
        cl = _s.current_link(state, u)
        if cl:
            a, b = cl
            rest = [b] if b == t else bypass_path(state, side, b, t)
            if rest and len(rest) > 1 and rest[1] == a:   # к цели - назад по своему участку: разворот, без петли a-b-a
                return rest
            return [a] + rest if rest else None
    return bypass_path(state, side, node_of(state, u), t)


def held_cities(state: dict, side: str) -> set[str]:
    """Города стороны (поле urban пункта) с её гарнизоном (order garrison): наступающий их обходит и окружает, а не
    штурмует, если город - не цель его оси (Чернигов, Сумы, Ахтырка 2022 - ОЦЕНКА замысла)."""
    out = set()
    for name, p in state["places"].items():
        if (p.get("urban") or 1) > 1 and owner(state, name) == side and any(
                u.get("order") == "garrison" for u in _units_near(state, name, side, HOLD_KM)):
            out.add(name)
    return out


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


COUNTER_MAX_LOSS = 0.10   # ОЦЕНКА: контрудар прекращается, если с начала потеряно больше этой доли боеспособности
ROUT_RATIO = 6.0        # ОЦЕНКА: перевес, при котором часть в бою не держит пункт и отходит


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
    # разгром: часть в бою против противника сильнее в ROUT_RATIO раз (любая доктрина) - не держит пункт, отходит
    # на следующий рубеж (лёгкие формирования против дивизии: ООП в 1982, ОЦЕНКА порога)
    for u in own:
        if u["state"] != "battle" or u.get("order") in ("withdraw", "garrison"):
            continue                             # гарнизон города не бежит: окружён - держится (Чернигов, Сумы 2022)
        enemy = sum(_s.power(state, state["units"][f]) for f in u.get("engaged", []) if f in state["units"])
        from . import morale as _m               # надломленная часть бежит при меньшем перевесе
        if enemy < ROUT_RATIO * _m.rout_k(u) * max(1e-6, _s.power(state, u) * _s.urban_k(state, u)):
            continue
        lines += _m.hit(state, u, _m.ROUT_HIT, "разгром")
        here = node_of(state, u)
        back = [q for q in g[here] if owner(state, q) == side and q != here]
        if not back:
            continue
        t = max(back, key=lambda q: min((model.dist_km(state["places"][q], model.unit_pos(state, e))
                                          for e in _maneuver(state, foe) if _active(e)), default=0))
        _disengage(state, u)
        set_route(state, u, [here, t], "withdraw")
        lines.append(f"{u['name']}: не выдержала удара (перевес противника {enemy / max(1e-6, _s.power(state, u)):.0f}:1) - отходит в {t}.")
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
    pc = ground_control(state, side)             # части под приказом игрока - без приёмов командования стороны
    free = [u for u in own if u["state"] == "defend" and not u.get("engaged") and u.get("order") not in ("reserve", "airhead", "garrison")
            and model.strength(u) >= sim.get("attack_min_strength", 0.7) and not (pc and u.get("player_order"))]
    # контрудар захлебнулся: потери с начала больше COUNTER_MAX_LOSS - прекратить, отойти на свой ближний пункт (8.10.1973:
    # контрудар 162-й дивизии остановлен в тот же день; без этого резерв перемалывался неделю)
    offense = posture_of(state, side) == "offense" and bool(objective(state, side, None))
    for u in own:                                # в наступлении стороны (поза сценария) - не контрудар, а наступление
        if u.get("op_role") != "counter" or u["state"] != "battle" or offense:
            continue
        if u.get("counter_s0", 1.0) - model.strength(u) < COUNTER_MAX_LOSS:
            continue
        here = node_of(state, u)
        mine = [q for q in state["places"] if owner(state, q) == side and not _units_near(state, q, foe, sim["contact_km"])]
        dest = min(mine, key=lambda q: path_km(state, here, q), default=None)
        p = own_path(state, side, here, dest) if dest else None
        if not p or len(p) < 2:
            continue
        _disengage(state, u)
        set_route(state, u, p, "withdraw")      # отход разрывает соприкосновение (sim._contacts)
        lines.append(f"{u['name']}: контрудар не удался - выходит из боя, рубеж {dest}.")
    # контрудар резервом (НАТО): по вклинившейся части противника, которая слабее
    if sim.get("counterattack"):
        for u in sorted(free, key=lambda x: -_s.power(state, x)):
            here = node_of(state, u)
            pw = _s.power(state, u)
            tgt = [e for e in _maneuver(state, foe) if _active(e) and e.get("order") not in ("withdraw", "garrison")
                   and not (e.get("defending") and e.get("dig_h", 0) >= _sim(state, foe).get("prepared_h", 1e9))   # вклинился,
                   # а не закрепился: по подготовленной обороне контрудар резервом не наносят (8.10.1973 - 162-я дивизия)
                   and owner(state, node_of(state, e)) == side and pw >= sim.get("counter_ratio", 1.2) * _s.power(state, e)
                   and path_km(state, here, node_of(state, e)) <= sim.get("counter_km", 60)]
            if not tgt:
                continue
            e = min(tgt, key=lambda x: path_km(state, here, node_of(state, x)))
            p = own_path(state, side, here, node_of(state, e))
            if p and len(p) > 1:
                set_route(state, u, p, "attack")
                u["op_role"], u["counter_s0"] = "counter", model.strength(u)
                free.remove(u)
                lines.append(f"{u['name']}: контрудар по вклинившейся {e['name']} ({p[-1]}).")
    if posture_of(state, side) != "offense" or not objective(state, side, None):   # поза сценария (оборона), а не
        return lines                             # доктрины; целей операции нет или взяты - без ОМГ и передовых отрядов
    # передовой отряд (ОВД): сильнейшая часть - на рубеж в глубине за фронтом, быстрее главных сил
    if sim.get("forward_detachment") and not any(u.get("op_role") == "forward" for u in own):
        cand = [u for u in own if u["state"] in ("defend", "march") and u.get("order") in (None, "attack", "hold")
                and model.strength(u) >= 0.85 and not u.get("engaged") and not (pc and u.get("player_order"))]
        if cand:
            u = max(cand, key=lambda x: _s.power(state, x))
            obj = objective(state, side, u)
            p = route_from(state, side, u, obj) if obj else None
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
        targets -= banned(state, side)          # не за политические ограничения сценария (Тбилиси 2008)
        cand = [u for u in own if u["state"] in ("defend", "march") and not u.get("engaged") and model.strength(u) >= 0.8
                and u.get("op_role") != "forward" and u.get("order") != "garrison" and not (pc and u.get("player_order"))]
        if gap and targets and cand:
            u = max(cand, key=lambda x: _s.power(state, x))
            here = node_of(state, u)
            t = min(targets, key=lambda q: path_km(state, here, q))
            p = route_from(state, side, u, t)
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
    pos = {s: [model.unit_pos(state, u) for u in _maneuver(state, s) if _active(u) and u.get("order") != "withdraw"]
           for s in model.SIDES}                 # места частей - один раз на шаг (а не на каждый пункт)
    near = lambda p, s, km: any(model.dist_km(q, state["places"][p]) <= km for q in pos[s])
    ban = {s: banned(state, s) for s in model.SIDES}
    for p in state["places"]:
        for side in model.SIDES:
            if owner(state, p) == side:
                continue
            if p in ban[side]:
                continue                         # куда сторона по сценарию не идёт - и не занимает (Беларусь, Россия)
            km = _sim(state, side)["capture_km"]
            if near(p, side, km) and not near(p, model.enemy(side), _sim(state, side)["contact_km"]):
                state["places"][p]["side"] = side
                lines.append(f"Пункт {p} занят: {'красные' if side == 'red' else 'синие'}.")
                for d in state["units"].values():       # склад в занятом пункте - потерян стороной
                    if model.category(d) == "depot" and d.get("place") == p and d.get("side") != side and d.get("state") != "lost":
                        d["state"] = "lost"
                        lines.append(f"{d['name']}: потерян - пункт {p} занят противником.")
                break
    return lines

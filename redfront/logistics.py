"""Тыл: снабжение, мосты, аэродромы, пополнение эскадрилий. Все коэффициенты - ОЦЕНКИ (раздел sim доктрины стороны,
logistics_note), не из документа.

  * Склады (роль depot) в пунктах. Запас = 1 - повреждение. Склад в пункте, который занял противник, потерян.
  * Снабжение - в тоннах (supply): склады с запасом, подвоз из тыла по своей территории, воздушные перевозки
    транспортной авиацией (задача airlift плана полётов), расход частей (по состоянию: бой больше всего) и авиации
    (на вылет). Часть берёт со своих складов не дальше supply_km по своей территории; получила меньше нормы -
    снабжение ниже (до unsupplied): марш медленнее, бой слабее, восстановление медленнее. Аэродром без снабжения
    выпускает меньше самолётов.
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

from . import convoys, model


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


# ---------------------------------------------------------------- снабжение в тоннах (ОЦЕНКИ: раздел sim доктрины)
CONSUME_T = {"battle": 1.0, "march": 0.5, "refit": 0.3, "defend": 0.2, "halted": 0.2}   # т на исправную машину в сутки
PRIORITY = ("battle", "march", "refit", "defend", "halted")    # кто первым получает снабжение со склада
DEPOT_DAYS = 10            # ёмкость складов стороны - столько суток расхода всех частей в обороне
SUPPLY_INFLOW = 2.5        # подвоз из тыла в сутки - x расход всех частей в обороне (марш - 2.5x: держится; бой - 5x: склады тают)
SORTIE_T = {"air": 4.0, "heli": 1.5}   # т на один самолёто-/вертолёто-вылет (топливо, боеприпасы)
ENTRY_N = 3                # пунктов входа подвоза: дальние от фронта свои пункты (если в секторе нет supply_entry)
WARN_BELOW = 0.75          # о снабжении части - сообщение при переходе через эту долю


def depot_stock(d: dict) -> float:
    """Запас склада, доля ёмкости. Склад без учёта в тоннах (старая кампания до первых суток) - 1 - повреждение."""
    if d.get("state") == "lost":
        return 0.0
    if d.get("cap_t"):
        return max(0.0, d.get("stock_t", 0.0) / d["cap_t"])
    return max(0.0, 1.0 - d.get("damage", 0.0))


def _rate(state: dict, side: str, key: str, default):
    return _sim(state, side).get(key, default)


def demand_t(state: dict, u: dict, st: str | None = None) -> float:
    """Расход части в сутки, т: исправные машины (с приданными) x норма состояния (consume_t доктрины)."""
    rates = _rate(state, u["side"], "consume_t", CONSUME_T)
    n = sum(model.alive_by_type(u).values())
    n += sum(sum(model.alive_by_type(a).values()) for a in state["units"].values()
             if a.get("attached_to") == u["id"] and a["state"] != "destroyed")
    return n * rates.get(st or u["state"], rates.get("defend", 0.2))


def _side_base_t(state: dict, side: str) -> float:
    from . import ops
    return sum(demand_t(state, u, "defend") for u in ops._maneuver(state, side))


def init_depots(state: dict) -> None:
    """Ёмкость и запас складов в тоннах - при первом расчёте (новая кампания и старые сохранения): ёмкость
    depot_days суток расхода стороны в обороне, поровну по её складам; запас - полный (минус повреждение)."""
    for side in model.SIDES:
        ds = [d for d in objects(state, "depot") if d["side"] == side and supplies(d) and not d.get("cap_t")]
        if not ds:
            continue
        n = sum(1 for d in objects(state, "depot") if d["side"] == side and supplies(d))
        cap = max(100.0, _rate(state, side, "depot_days", DEPOT_DAYS) * _side_base_t(state, side) / n)
        for d in ds:
            d["cap_t"] = round(cap)
            d["stock_t"] = 0.0 if d.get("state") == "lost" else d["cap_t"] * (1.0 - d.get("damage", 0.0))


def _clip(d: dict) -> None:
    """Повреждение склада уничтожает запас: запас не больше ёмкости x (1 - повреждение)."""
    top = 0.0 if d.get("state") == "lost" else d["cap_t"] * max(0.0, 1.0 - d.get("damage", 0.0))
    d["stock_t"] = max(0.0, min(d.get("stock_t", 0.0), top))


def _room(d: dict) -> float:
    return 0.0 if d.get("state") == "lost" else max(0.0, d["cap_t"] * (1.0 - d.get("damage", 0.0)) - d.get("stock_t", 0.0))


def _reach(state: dict, side: str, sources: list[str], g: dict) -> dict[str, float]:
    """Км от ближайшего из sources (свои пункты) до каждого пункта: идти можно только через свои пункты (как
    ops.path(side=...)): чужой пункт получает расстояние, но дальше через него хода нет."""
    import heapq
    dist = {p: 0.0 for p in sources if state["places"][p].get("side") == side}
    q = [(0.0, p) for p in dist]
    while q:
        d, u = heapq.heappop(q)
        if d > dist.get(u, 1e18) or (state["places"][u].get("side") != side):
            continue
        for v, w in g[u].items():
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                heapq.heappush(q, (d + w, v))
    return dist


def entries(state: dict, side: str) -> list[str]:
    """Пункты входа подвоза из тыла (вне сектора): supply_entry сектора, иначе ENTRY_N своих пунктов, дальних от фронта."""
    from . import ops
    own = [p for p, pl in state["places"].items() if pl.get("side") == side]
    fixed = [p for p in (state.get("supply_entry") or {}).get(side, []) if p in own]
    if fixed:
        return fixed
    fl = ops.front_links(state)
    if not fl:
        return own
    mids = [model.lerp(state["places"][a], state["places"][b], 0.5) for a, b in fl]
    return sorted(own, key=lambda p: -min(model.dist_km(state["places"][p], m) for m in mids))[:ENTRY_N]


def road_connected(state: dict, side: str, g: dict | None = None) -> set[str]:
    """Склады стороны, до которых есть путь подвоза из тыла (по своей территории, открытым связям)."""
    from . import ops
    g = g or ops.graph(state)
    dist = _reach(state, side, entries(state, side), g)
    return {d["id"] for d in objects(state, "depot") if d["side"] == side and d.get("place") in dist}


def _depot_maps(state: dict, side: str, g: dict) -> dict[str, dict[str, float]]:
    return {d["id"]: _reach(state, side, [d["place"]], g) for d in objects(state, "depot")
            if d["side"] == side and supplies(d) and d.get("state") != "lost" and d.get("place") in state["places"]}


def _draw(state: dict, need: float, node: str, maps: dict, max_km: float | None) -> tuple[float, bool]:
    """Взять need т с ближних складов, до которых от node есть путь (не длиннее max_km). -> (взято, путь есть)."""
    got, any_path = 0.0, False
    for did, km in sorted(((did, m[node]) for did, m in maps.items() if node in m), key=lambda x: x[1]):
        if max_km is not None and km > max_km:
            break
        any_path = True
        d = state["units"][did]
        take = min(need - got, d.get("stock_t", 0.0))
        d["stock_t"] = d.get("stock_t", 0.0) - take
        got += take
        if got >= need - 1e-9:
            break
    return got, any_path


def _airbase_node(state: dict, bid: str) -> str:
    b = state["airbases"][bid]
    return min(state["places"], key=lambda p: model.dist_km(b, state["places"][p]))


def airlift_cargo_t(state: dict, unit: dict) -> float:
    """Груз одного борта, т: cargo_t типа (aircraft.json), иначе по роли (ОЦЕНКА)."""
    c = model.aircraft_info(unit.get("type", "")).get("cargo_t")
    return float(c) if c else (5.0 if unit["role"] == "transport" else 2.0)


def supply(state: dict) -> list[str]:
    """Снабжение за сутки (ОЦЕНКИ, logistics_note доктрины). Склад - запас в тоннах (stock_t) из ёмкости cap_t;
    повреждение склада уничтожает запас сверх cap_t x (1 - повреждение).
      1. Воздушные перевозки плана полётов суток (задача airlift): груз бортов (минус сбитые в миссии) - на склад
         у аэродрома назначения; рейс, слетанный игроком, - сколько он доставил ящиками CTLD (ato['lift']).
      2. Подвоз из тыла: supply_inflow x расход всех частей стороны в обороне - на склады, до которых есть путь от
         пунктов входа (тыл сектора) по своей территории; делится по недостаче. Отрезанный склад подвоза не получает.
      3. Расход: части - по порядку PRIORITY (бой первым), со своих складов не дальше supply_km по своей территории;
         авиация - sortie_t на самолёто-вылет плана полётов, со складов, до которых от аэродрома есть путь.
    Снабжение части u['supply'] = unsupplied + (1 - unsupplied) x доля полученного (supply_frac); аэродрома -
    airbases[...]['supply'] (доля к вылету в available)."""
    from . import ops
    lines = []
    sides_with_depots = {d["side"] for d in objects(state, "depot") if supplies(d)}
    init_depots(state)
    for d in objects(state, "depot"):
        if d.get("cap_t"):
            _clip(d)
    g = ops.graph(state)
    a = state.get("ato") or {}
    for side in model.SIDES:
        if side not in sides_with_depots:
            for u in ops._maneuver(state, side):
                u["supply"], u["supply_frac"] = 1.0, 1.0
            continue
        sim = _sim(state, side)
        unsup = sim["unsupplied"]
        ds = [d for d in objects(state, "depot") if d["side"] == side and supplies(d)]
        # 1. воздушные перевозки - первыми: груз уже на складе, дороги довозят остальное
        air = 0.0
        for e in a.get("entries", []):
            if e["side"] != side or e["kind"] != "airlift":
                continue
            grp = e["task"]["package"][0]
            perf = state["units"].get(grp["performer"])
            d = state["units"].get(grp["objective"].get("depot"))
            if not perf or not d or d.get("state") == "lost":
                continue
            n = max(0, grp["size"] - (a.get("lost") or {}).get(e["id"], 0))
            if e["id"] in a.get("done", []):     # слетал игрок: его груз - что доставлено ящиками CTLD (дебриф), ведомые - полный
                t = (a.get("lift") or {}).get(e["id"], 0.0) + max(0, n - 1) * airlift_cargo_t(state, perf)
            else:
                t = n * airlift_cargo_t(state, perf)
            t = min(_room(d), t)
            d["stock_t"] += t
            air += t
        # 2. подвоз из тыла (остаток места после воздушного груза)
        conn = road_connected(state, side, g)
        inflow = _rate(state, side, "supply_inflow", SUPPLY_INFLOW) * _side_base_t(state, side)
        rooms = {d["id"]: _room(d) for d in ds if d["id"] in conn}
        tot_room = sum(rooms.values())
        road = min(inflow, tot_room)
        lost_by = convoys.depot_losses(state, side)   # колонны, разбитые на путях подвоза (миссии и удары ИИ)
        convoy_lost = 0.0
        for d in ds:
            if rooms.get(d["id"]):
                share = road * rooms[d["id"]] / tot_room
                lost_here = min(share, lost_by.get(d["id"], 0.0))
                d["stock_t"] += share - lost_here
                convoy_lost += lost_here
        road -= convoy_lost
        (state.get("convoy_losses") or {}).pop(side, None)
        cut = [d for d in ds if d["id"] not in conn and d.get("state") != "lost"]
        for d in cut:
            if not d.get("_cut"):
                lines.append(f"{d['name']}: отрезан от подвоза из тыла (только воздухом).")
            d["_cut"] = True
        for d in ds:
            if d["id"] in conn and d.pop("_cut", None):
                lines.append(f"{d['name']}: подвоз из тыла восстановлен.")
        # 3. расход: части по приоритету, затем авиация
        maps = _depot_maps(state, side, g)
        used = 0.0
        units = sorted(ops._maneuver(state, side), key=lambda u: PRIORITY.index(u["state"]) if u["state"] in PRIORITY else 9)
        for u in units:
            need = demand_t(state, u)
            got, reach = _draw(state, need, ops.node_of(state, u), maps, sim["supply_km"]) if need > 0 else (0.0, True)
            used += got
            frac = 1.0 if need <= 1e-9 else got / need
            was = u.get("supply", 1.0)
            u["supply_frac"] = round(frac, 3)
            u["supply"] = round(unsup + (1.0 - unsup) * frac, 3)
            if u["supply"] < WARN_BELOW <= was:
                lines.append(f"{u['name']}: " + (f"не хватает снабжения ({frac:.0%} нормы) - склады пусты." if reach else
                             f"без снабжения - нет своего склада с запасом в {sim['supply_km']} км по своей территории."))
            elif u["supply"] >= WARN_BELOW > was:
                lines.append(f"{u['name']}: снабжение восстановлено ({frac:.0%} нормы).")
        sorties: dict[str, float] = {}
        for e in a.get("entries", []):
            if e["side"] != side or e["kind"] == "airlift":
                continue
            for grp in e["task"]["package"]:
                perf = state["units"].get(grp["performer"])
                if perf:
                    sorties[grp["base"]] = sorties.get(grp["base"], 0.0) + grp["size"] * \
                        _rate(state, side, "sortie_t", SORTIE_T).get(model.category(perf), 4.0)
        for bid, b in state["airbases"].items():
            if b.get("side") != side:
                continue
            need = sorties.get(bid, 0.0)
            if need <= 0:
                b["supply"] = 1.0 if b.get("supply") is None else min(1.0, b["supply"] + 0.5)   # без вылетов - копит
                continue
            got, _p = _draw(state, need, _airbase_node(state, bid), maps, None)
            used += got
            b["supply"] = round(got / need, 3)
        # потоки путей подвоза на следующие сутки (convoys.py): недостача складов после расхода, в пределах подвоза
        need = {d["id"]: _room(d) for d in ds if d["id"] in conn}
        tot_need = sum(need.values())
        k = min(1.0, inflow / tot_need) if tot_need else 0.0
        state.setdefault("supply_routes", {})[side] = convoys.forecast(state, side, {i: n * k for i, n in need.items()}, g)
        stock = sum(d.get("stock_t", 0.0) for d in ds)
        cap = sum(d["cap_t"] for d in ds) or 1.0
        state.setdefault("supply_log", {})[side] = {"day": state["day"], "road_t": round(road), "air_t": round(air),
                                                   "convoy_lost_t": round(convoy_lost),
                                                   "used_t": round(used), "stock_t": round(stock), "cap_t": round(cap),
                                                   "cut": [d["id"] for d in cut]}
        lines.append(f"Тыл ({'красные' if side == 'red' else 'синие'}): подвоз {road:.0f} т"
                     + (f" (колонны разбиты - недовезено {convoy_lost:.0f} т)" if convoy_lost >= 0.5 else "")
                     + f", воздухом {air:.0f} т, "
                     f"расход {used:.0f} т; запас складов {stock:.0f} т ({stock / cap:.0%}).")
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
    for u in state["units"].values():            # экипажи: crews_per_day доктрины до штата (из училищ и резерва)
        if "crews" in u and u["crews"] < u.get("crews0", 0):
            u["crews_acc"] = u.get("crews_acc", 0.0) + _sim(state, u["side"]).get("crews_per_day", 0) * industry(state, u["side"])
            add = min(int(u["crews_acc"]), u["crews0"] - u["crews"])
            if add > 0:
                u["crews"] += add
                u["crews_acc"] -= add
                lines.append(f"{u['name']}: пополнение +{add} экипаж(а), экипажей {u['crews']}.")
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
    sup = base.get("supply")                     # аэродром без снабжения (supply) - меньше самолётов к вылету
    k = 1.0 if sup is None else _sim(state, unit["side"])["unsupplied"] + (1.0 - _sim(state, unit["side"])["unsupplied"]) * sup
    n = int(unit.get("count", 0) * (1.0 - dmg) * k + 1e-9)
    return min(n, unit["crews"]) if "crews" in unit else n   # без экипажей самолёт не летит (csar.py)


def air_defence(state: dict) -> list[str]:
    """ЗРК за сутки (ОЦЕНКИ, sam_note доктрины): потери восстанавливаются на repair_sam в сутки (ремонт, подвоз
    пусковых и ракет; x промышленность и снабжение стороны), - иначе после первого удачного подавления ПВО в небе её
    больше нет. Приданная ПВО части в бою не восстанавливается. Подвижный ЗРК на позиции (не приданный и не
    объектовая ПВО - fixed), понёсший потери после
    прошлой смены позиции, - раскрыт: уходит на новую позицию в sam_relocate_km в сторону тыла (от оси угрозы;
    со случайностью - в пределах +-90 градусов)."""
    from . import materialize                                    # materialize импортирует planner -> logistics
    lines = []
    for u in state["units"].values():
        if model.category(u) not in ("sam", "gci") or u["state"] in ("destroyed", "pending"):
            continue
        sim = _sim(state, u["side"])
        parent = state["units"].get(u.get("attached_to") or "")
        lost_now = sum(u["lost"].values())
        if not parent and "pos" in u and not u.get("fixed") and lost_now > u.get("lost_at_move", 0.0) + 1e-6:
            r = model.rng(state, f"sam-move-{u['id']}")
            axis = materialize.threat_axis_deg(state, u)
            brg = (axis + 180.0 + (r.uniform(-90.0, 90.0) if r else 0.0)) % 360.0
            u["pos"] = model.offset(u["pos"], brg, sim.get("sam_relocate_km", 5) * 1000)
            lines.append(f"{u['name']}: позиция раскрыта, ЗРК сменил позицию ({sim.get('sam_relocate_km', 5)} км).")
        if parent and parent["state"] == "battle":
            u["lost_at_move"] = lost_now
            continue
        was = model.strength(u)
        if was < 1.0:
            rate = sim.get("repair_sam", 0.0) * industry(state, u["side"]) * min(1.0, (parent or u).get("supply", 1.0))
            for c in u["composition"]:
                u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) * (1 - rate)
            if was <= 0 < model.strength(u) or (was < 0.5 <= model.strength(u)):
                lines.append(f"{u['name']}: восстановлен до {model.strength(u):.0%}.")
        u["lost_at_move"] = sum(u["lost"].values())
    return lines

"""Передовые вертолётные площадки (FARP): готовые вертолётные площадки карты Германии ("H FRG nn", "H GDR nn"; без
медицинских "H Med" и радарных "H Radar") - базы вертолётных частей в модели. Все числа - ОЦЕНКИ (farp_* раздела
sim доктрины, иначе константы здесь).

Площадка - аэродром модели (state['airbases'], kind 'farp'): чья - по владельцу ближнего пункта; противник ближе
farp_min_km - закрыта, ближе airfield_lost_km - потеряна. Каждые сутки
вертолётные части (боевые и транспортные) выдвигаются на свою открытую площадку в farp_min_km..farp_max_km от
противника, если она хотя бы на farp_gain_km ближе к фронту, чем основной аэродром (u['home']), и не дальше
farp_reach_km от него; одна часть - одна площадка. Площадка закрыта, потеряна или противник подошёл ближе farp_min_km - часть уходит на другую или домой.
Снабжение площадки - как у аэродрома (logistics.supply: путь от площадки до своего склада).
В миссии вертолёты взлетают с площадки (стоянки площадки; не хватило - взлёт в воздухе над ней), садятся на неё.

Полевые площадки (field): готовой площадки карты в полосе нет (или доктрина их предпочитает - farp_field_prefer) -
часть разворачивает площадку в поле: точка между своим пунктом на фронте и основным аэродромом, в farp_min_km..
farp_max_km от противника, в стороне от населённого пункта (FIELD_OFFSET_KM). Площадка небольшая (farp_field_cap
вертолётов), без стоянок: в миссии - невидимая площадка DCS (Invisible FARP), взлёт с грунта у неё (From Ground
Area), посадка на неё. Доктрина может требовать частой смены площадок (farp_field_move_days, ВСУ 2022: малые
скрытые площадки в поле, смена через 1-3 суток - ОЦЕНКА). Опустевшая полевая площадка снимается.
"""
from __future__ import annotations

import re

from . import model

FARP_MIN_KM = 15          # ОЦЕНКА: ближе к противнику площадка не занимается (артиллерия, разведка)
FARP_MAX_KM = 50          # ОЦЕНКА: дальше - выигрыш в радиусе невелик
FARP_GAIN_KM = 25         # ОЦЕНКА: выдвигаться, если площадка ближе к фронту хотя бы на столько, чем основной аэродром
FARP_REACH_KM = 150       # ОЦЕНКА: площадка не дальше этого от основного аэродрома (часть работает на своём участке)
NAME = re.compile(r"^H (FRG|GDR) \d+$")
FARP_PER_SLOT = 2         # ОЦЕНКА: вертолётов на стоянку площадки (остальные рассредоточены рядом, взлёт по очереди)
FARP_MIN_HELOS = 4        # ОЦЕНКА: площадка принимает не меньше звена
FARP_MAX_HELOS = 12       # ОЦЕНКА: и не больше эскадрильи - полк целиком на площадку не уходит
FIELD_CAP = 8             # ОЦЕНКА: вертолётов на полевой площадке (подготовлена за часы: грунт, маскировка, ГСМ)
FIELD_OFFSET_KM = 3.0     # ОЦЕНКА: в стороне от пункта (не в городе, у дороги подвоза)
FIELD_STEP_KM = 4.0       # шаг поиска точки от фронта к основному аэродрому
FIELD_SPACING_KM = 4.0    # ОЦЕНКА: полевые площадки стороны - не ближе друг к другу (рассредоточение)


def capacity(b: dict) -> int:
    """Сколько вертолётов примет площадка: полевая - по доктрине (cap); готовая - по стоянкам, от звена до эскадрильи."""
    if b.get("field"):
        return int(b.get("cap") or FIELD_CAP)
    return max(FARP_MIN_HELOS, min(FARP_MAX_HELOS, int(b.get("slots", 1)) * FARP_PER_SLOT))


def field_site(state: dict, side: str, home: dict, lo: float, hi: float, salt: str = "") -> dict | None:
    """Точка полевой площадки: от своего пункта на фронте (ближнего к основному аэродрому) - к аэродрому, пока до
    противника не станет между lo и hi (ближе к середине), в стороне от дороги; на своей земле. Нет - None."""
    from . import ops
    front = [state["places"][p] for p in ops.front_nodes(state, side)]
    if not front:
        return None
    want = (lo + hi) / 2
    r = model.rng(state, f"field-{side}-{salt}")
    foe = model.enemy(side)
    for pl in sorted(front, key=lambda q: model.dist_km(q, home))[:3]:
        brg = model.bearing_deg(pl, home)
        total = model.dist_km(pl, home)
        if front_km(state, side, pl) > want:     # противник далеко от своего пункта (первые сутки) - к нему, по своей земле
            en = min((q for q in state["places"].values() if q.get("side") == foe), key=lambda q: model.dist_km(pl, q), default=None)
            if en:
                to = model.bearing_deg(pl, en)
                k = 0.0
                while k < model.dist_km(pl, en):
                    q = model.offset(pl, to, (k + FIELD_STEP_KM) * 1000)
                    if front_km(state, side, q) < want or owner(state, q) != side:
                        break
                    k += FIELD_STEP_KM
                pl = model.offset(pl, to, k * 1000)
                brg, total = to + 180, k + total
        k = 0.0
        while k <= total:
            pos = model.offset(pl, brg, k * 1000)
            d = front_km(state, side, pos)
            if d >= want or (k + FIELD_STEP_KM > total and lo <= d <= hi):
                first = 90 if (r.random() < 0.5 if r else len(salt) % 2) else -90
                for off in (FIELD_OFFSET_KM, 2 * FIELD_OFFSET_KM, 3 * FIELD_OFFSET_KM):   # в стороне, не у соседней площадки
                    for sb in (first, -first):
                        q = model.offset(pos, brg + sb, off * 1000)
                        from . import landcover   # полевая площадка - на открытом месте, не в лесу и не в воде
                        q = landcover.clear(state, q, max_m=800, avoid=(landcover.FOREST, landcover.WATER, landcover.BUILT))
                        d = front_km(state, side, q)
                        if lo <= d <= hi and owner(state, q) == side and all(
                                model.dist_km(q, b) >= FIELD_SPACING_KM for b in state["airbases"].values()
                                if b.get("field") and b.get("side") == side):
                            return {"lat": round(q["lat"], 5), "lon": round(q["lon"], 5), "front_km": round(d, 1)}
                break
            k += FIELD_STEP_KM
    return None


def add_field(state: dict, side: str, pos: dict, cap: int, near_unit: dict) -> str:
    """Полевая площадка в state['airbases'] (kind farp, field): без аэродрома карты."""
    n = state.setdefault("_field_n", 0) + 1
    state["_field_n"] = n
    near = min(state["places"], key=lambda q: model.dist_km(pos, state["places"][q]))
    bid = f"fs_{side}_{n}"
    state["airbases"][bid] = {"name": f"полевая площадка у {near}", "kind": "farp", "field": True, "military": True,
                              "lat": pos["lat"], "lon": pos["lon"], "state": "open", "side": side, "cap": cap,
                              "front_km": pos.get("front_km"), "day": state.get("day", 1), "slots": 0}
    return bid


def detach(state: dict, u: dict, bid: str) -> dict:
    """Часть - на площадку bid: помещается - целиком, нет - передовая группа (отдельная часть с parent) по вместимости,
    остальное - на прежнем аэродроме. Возвращает часть на площадке."""
    cap = capacity(state["airbases"][bid])
    if u.get("count", 0) <= cap:
        u["home"] = u.get("home") or u["base"]
        u["base"] = bid
        return u
    did = f"{u['id']}_fwd_{bid}"
    k = cap / u["count"]
    d = {key: val for key, val in u.items() if key not in ("rebase_to", "base_fixed", "home", "repl_acc", "crews_acc")}
    d.update({"id": did, "name": f"{u['name']}, передовая группа", "parent": u["id"], "base": bid, "home": u["base"],
              "count": cap, "count0": cap})
    from . import pilots
    pilots.ensure(state, u)                      # лётчики - до изменения числа экипажей (ensure режет по нему)
    n = min(u["crews"], round(u["crews"] * k)) if "crews" in u else cap
    d["crews"] = n
    pilots.split(u, d, cap)
    u["count"] -= cap
    u["count0"] = max(u["count"], u.get("count0", 0) - cap)
    if "crews" in u:                             # экипажи - по доле машин
        d["crews0"] = n
        u["crews"] -= n
        u["crews0"] = max(u["crews"], u.get("crews0", 0) - n)
    else:
        d.pop("crews")
    state["units"][did] = d
    return d


def merge(state: dict, d: dict) -> dict | None:
    """Передовая группа - обратно в свой полк (на его аэродром). Возвращает полк."""
    u = state["units"].get(d.get("parent") or "")
    if not u:
        return None
    u["count"] += d.get("count", 0)
    u["count0"] = u.get("count0", 0) + d.get("count0", 0)
    if "crews" in d:
        u["crews"] = u.get("crews", 0) + d["crews"]
        u["crews0"] = u.get("crews0", 0) + d.get("crews0", 0)
    from . import pilots
    pilots.join(u, d)
    for x in state.get("downed", []):            # сбитые экипажи группы - экипажи полка
        if x.get("unit") == d["id"]:
            x["unit"] = u["id"]
    del state["units"][d["id"]]
    return u


def _sim(state: dict, side: str, key: str, default: float) -> float:
    return model.doctrine(state, side)["sim"].get(key, default)


def front_km(state: dict, side: str, pos: dict) -> float:
    """До противника: ближний его пункт или часть в поле."""
    from . import ops
    foe = model.enemy(side)
    d_place = min((model.dist_km(pos, p) for p in state["places"].values() if p.get("side") == foe), default=1e9)
    d_unit = min((model.dist_km(pos, model.unit_pos(state, u)) for u in ops._maneuver(state, foe)
                  if u["state"] not in ("halted", "pending")), default=1e9)
    return min(d_place, d_unit)


def owner(state: dict, pos: dict) -> str | None:
    p = min(state["places"].values(), key=lambda q: model.dist_km(pos, q))
    return p.get("side")


def ensure(state: dict) -> int:
    """Площадки карты в state['airbases'] (новая кампания и старые - при загрузке). Возвращает, сколько добавлено."""
    have = {b.get("airport") for b in state["airbases"].values()}
    lat = [p["lat"] for p in state["places"].values()]
    lon = [p["lon"] for p in state["places"].values()]
    box = (min(lat) - 0.3, max(lat) + 0.3, min(lon) - 0.3, max(lon) + 0.3)   # театр кампании (сектор)
    n = 0
    for ap in model.terrain(state).airports.values():
        if not NAME.match(ap.name) or ap.name in have or not any(s.helicopter for s in ap.parking_slots):
            continue
        ll = ap.position.latlng()
        if not (box[0] <= ll.lat <= box[1] and box[2] <= ll.lng <= box[3]):
            continue
        pos = {"lat": ll.lat, "lon": ll.lng}
        near = min(state["places"], key=lambda q: model.dist_km(pos, state["places"][q]))
        state["airbases"][f"hp_{ap.id}"] = {"name": f"площадка {near} ({ap.name})", "airport": ap.name, "kind": "farp",
                                           "military": True, "lat": ll.lat, "lon": ll.lng, "state": "open",
                                           "side": state["places"][near].get("side"),
                                           "slots": sum(1 for s in ap.parking_slots if s.helicopter)}
        n += 1
    return n


def is_farp(b: dict | None) -> bool:
    return bool(b) and b.get("kind") == "farp"


def daily(state: dict) -> list[str]:
    """Конец суток: чьи площадки и открыты ли; вертолётные части - на площадки и с них."""
    lines = []
    bases = state["airbases"]
    for bid, b in bases.items():
        if not is_farp(b):
            continue
        side = owner(state, b)
        if side != b.get("side"):
            b["side"] = side
        if side not in model.SIDES:
            b["state"] = "lost"
            continue
        d = front_km(state, side, b)
        b["front_km"] = round(d, 1)
        b["state"] = ("lost" if d <= _sim(state, side, "airfield_lost_km", 3)
                      else "closed" if d < _sim(state, side, "farp_min_km", FARP_MIN_KM) else "open")
    taken = {u["base"] for u in state["units"].values() if model.category(u) == "heli" and is_farp(bases.get(u["base"]))}
    helos = [u for u in state["units"].values() if model.category(u) == "heli" and u.get("count", 0) > 0]
    for u in list(state["units"].values()):          # опустевшая передовая группа (все сбиты) - в полк
        if u.get("parent") and model.category(u) == "heli" and u.get("count", 0) <= 0 and u["parent"] in state["units"]:
            merge(state, u)
    left: set[str] = set()                              # ушли с площадки в эти сутки - снова выдвигаются не раньше завтра
    for u in helos:                                     # площадка закрыта, потеряна, чужая или фронт подошёл - уйти
        b = bases.get(u["base"])
        if not is_farp(b):
            continue
        lo = _sim(state, u["side"], "farp_min_km", FARP_MIN_KM)
        if b["side"] == u["side"] and b["state"] == "open" and b.get("front_km", 1e9) >= lo:
            continue
        home = u.get("home")
        if not home or bases.get(home, {}).get("state", "open") not in ("open", "active"):   # домой нельзя - ближний свой аэродром
            own = [(model.dist_km(b, x), k) for k, x in bases.items() if not is_farp(x) and x.get("side") == u["side"]
                   and x.get("state", "open") in ("open", "active")]
            if not own:
                continue
            home = min(own)[1]
        taken.discard(u["base"])
        left.add(u["id"])
        if u.get("parent") and u["parent"] in state["units"]:   # передовая группа - обратно в полк
            p = merge(state, u)
            left.add(p["id"])
            lines.append(f"{u['name']}: уход с площадки {b['name']} - в свой полк ({bases[p['base']]['name']}).")
            continue
        u.pop("base_fixed", None)                       # вынужденный уход - снова на усмотрение модели
        u["base"] = home
        lines.append(f"{u['name']}: уход с передовой площадки {b['name']} на {bases[home]['name']}.")
    for u in helos:                                     # смена полевой площадки (доктрина: farp_field_move_days)
        b = bases.get(u["base"])
        if not is_farp(b) or not b.get("field") or u["id"] in left or u["id"] not in state["units"]:
            continue
        every = _sim(state, u["side"], "farp_field_move_days", 0)
        lo = _sim(state, u["side"], "farp_min_km", FARP_MIN_KM)
        hi = _sim(state, u["side"], "farp_max_km", FARP_MAX_KM)
        behind = b.get("front_km", 0) > hi                # фронт ушёл вперёд - площадка следом
        if not behind and (not every or state.get("day", 1) - b.get("day", 1) < every):
            continue
        home = bases.get(u.get("home") or "")
        pos = field_site(state, u["side"], home or b, lo, hi, f"{u['id']}-{state.get('day')}") if home else None
        if not pos:
            continue
        nb = add_field(state, u["side"], pos, capacity(b), u)
        taken.discard(u["base"])
        u["base"] = nb
        taken.add(nb)
        lines.append(f"{u['name']}: " + ("площадка - за фронтом" if behind else "смена полевой площадки")
                     + f" - {bases[nb]['name']} ({pos['front_km']:.0f} км от противника).")
    for u in sorted(helos, key=lambda u: u["id"]):      # выдвижение на площадку ближе к фронту
        if is_farp(bases.get(u["base"])) or u["id"] in left or u.get("base_fixed") or u.get("parent") \
                or u["id"] not in state["units"] or any(x.get("parent") == u["id"] for x in state["units"].values()):
            continue                                    # перебазирована командующим - сама не выдвигается
        home = bases.get(u["base"])
        if not home or home.get("state", "open") not in ("open", "active"):
            continue
        lo = _sim(state, u["side"], "farp_min_km", FARP_MIN_KM)
        hi = _sim(state, u["side"], "farp_max_km", FARP_MAX_KM)
        gain = _sim(state, u["side"], "farp_gain_km", FARP_GAIN_KM)
        d_home = front_km(state, u["side"], home)
        cands = [(model.dist_km(home, b), bid, b) for bid, b in bases.items()
                 if is_farp(b) and b["side"] == u["side"] and b["state"] == "open" and bid not in taken
                 and lo <= b.get("front_km", 1e9) <= hi and b["front_km"] <= d_home - gain
                 and model.dist_km(home, b) <= _sim(state, u["side"], "farp_reach_km", FARP_REACH_KM)]
        if _sim(state, u["side"], "farp_field_prefer", 0):
            cands = []                                  # доктрина: малые скрытые площадки в поле, не готовые площадки карты
        if not cands and _sim(state, u["side"], "farp_field", 1):   # готовой нет - полевая площадка
            pos = field_site(state, u["side"], home, lo, hi, u["id"])
            if pos and pos["front_km"] <= d_home - gain and model.dist_km(home, pos) <= \
                    _sim(state, u["side"], "farp_reach_km", FARP_REACH_KM):
                bid = add_field(state, u["side"], pos, int(_sim(state, u["side"], "farp_field_cap", FIELD_CAP)), u)
                cands = [(model.dist_km(home, pos), bid, bases[bid])]
        if not cands:
            continue
        _d, bid, b = min(cands, key=lambda c: c[0])     # ближняя к своему аэродрому: часть работает на своём участке
        x = detach(state, u, bid)
        taken.add(bid)
        lines.append(f"{x['name']}: выдвижение на передовую {b['name']} ({x['count']} вертолётов, площадка - до "
                     f"{capacity(b)}; {b['front_km']:.0f} км от противника; основной аэродром {home['name']} - {d_home:.0f} км).")
    used = {u.get("base") for u in state["units"].values()}
    for bid in [k for k, b in bases.items() if b.get("field") and k not in used]:   # опустевшие полевые - снимаются
        del bases[bid]
    return lines

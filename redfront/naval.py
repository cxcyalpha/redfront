"""Флот: корабельные группы в модели и в миссии (роль naval, категория naval).

Часть флота - корабельная группа: авианосная ударная группа (авианосец и корабли охранения), отряд надводных
кораблей, ракетные катера, десантный отряд, конвой. Состав - корабли DCS (имя класса pydcs, dcs.ships) с именами
(composition[].names - реальные корабли этого класса); позиция - в море (pos). Авианосец группы - база авиации
(state['airbases'][...] kind carrier, поле naval - id группы): позиция базы - позиция группы; авианосец потерян -
база потеряна.

Корабли - цели (удар по кораблям, strike_ship доктрины) и угроза: ПВО кораблей (SHIP_INFO ad_km) входит в угрозы
коридора, как ЗРК. Все числа SHIP_INFO - ОЦЕНКИ по открытым справочникам (дальность ЗРК корабля, ПКР в залпе, груз).
"""
from __future__ import annotations

from . import model

SHIP_INFO = {   # класс pydcs -> вид (CV - авианосец, LH - универсальный десантный, CG/DDG/FFG/FF - охранение, FAC - катер,
    # LS - десантный, AK/AO - транспорт/танкер), ad_km - ЗРК корабля, asm - ПКР в залпе, cargo_t - груз. ОЦЕНКИ.
    "Forrestal": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1955},
    "VINSON": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1982}, "CVN_71": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1986},
    "CVN_72": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1989}, "CVN_73": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1992},
    "Stennis": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1995}, "CVN_75": {"kind": "CV", "ad_km": 15, "asm": 0, "year": 1998},
    "KUZNECOW": {"kind": "CV", "ad_km": 12, "asm": 12, "year": 1991}, "CV_1143_5": {"kind": "CV", "ad_km": 12, "asm": 12, "year": 2017},
    "Hms_invincible": {"kind": "CV", "ad_km": 40, "asm": 0, "year": 1980}, "Ara_vdm": {"kind": "CV", "ad_km": 0, "asm": 0, "year": 1969},
    "Essex": {"kind": "CV", "ad_km": 4, "asm": 0, "year": 1944},
    "LHA_Tarawa": {"kind": "LH", "ad_km": 15, "asm": 0, "year": 1976},
    "TICONDEROG": {"kind": "CG", "ad_km": 150, "asm": 8, "year": 1983},
    "USS_Arleigh_Burke_IIa": {"kind": "DDG", "ad_km": 150, "asm": 0, "year": 2000},
    "PERRY": {"kind": "FFG", "ad_km": 45, "asm": 4, "year": 1977},
    "Leander_gun_achilles": {"kind": "FF", "ad_km": 5, "asm": 0, "year": 1968},
    "Leander_gun_andromeda": {"kind": "FF", "ad_km": 10, "asm": 4, "year": 1968},
    "MOSCOW": {"kind": "CG", "ad_km": 90, "asm": 16, "year": 1982}, "PIOTR": {"kind": "CG", "ad_km": 120, "asm": 20, "year": 1998},
    "NEUSTRASH": {"kind": "FFG", "ad_km": 12, "asm": 0, "year": 1993}, "REZKY": {"kind": "FFG", "ad_km": 15, "asm": 4, "year": 1975},
    "ALBATROS": {"kind": "FF", "ad_km": 15, "asm": 0, "year": 1970},
    "MOLNIYA": {"kind": "FAC", "ad_km": 4, "asm": 4, "year": 1979}, "La_Combattante_II": {"kind": "FAC", "ad_km": 0, "asm": 4, "year": 1968},
    "Type_021_1": {"kind": "FAC", "ad_km": 0, "asm": 4, "year": 1960}, "Speedboat": {"kind": "FAC", "ad_km": 0, "asm": 0, "year": 1950},
    "Type_052B": {"kind": "DDG", "ad_km": 40, "asm": 16, "year": 2004}, "Type_052C": {"kind": "DDG", "ad_km": 100, "asm": 8, "year": 2004},
    "Type_054A": {"kind": "FFG", "ad_km": 40, "asm": 8, "year": 2008},
    "BDK_775": {"kind": "LS", "ad_km": 4, "asm": 0, "year": 1975, "cargo_t": 450}, "LST_Mk2": {"kind": "LS", "ad_km": 2, "asm": 0, "year": 1943, "cargo_t": 1500},
    "Type_071": {"kind": "LS", "ad_km": 5, "asm": 0, "year": 2007, "cargo_t": 1500},
    "Dry_cargo_ship_1": {"kind": "AK", "ad_km": 0, "asm": 0, "year": 1950, "cargo_t": 8000},
    "Dry_cargo_ship_2": {"kind": "AK", "ad_km": 0, "asm": 0, "year": 1950, "cargo_t": 5000},
    "HandyWind": {"kind": "AK", "ad_km": 0, "asm": 0, "year": 1960, "cargo_t": 20000},
    "ELNYA": {"kind": "AO", "ad_km": 0, "asm": 0, "year": 1960, "cargo_t": 6000},
    "Ship_Tilde_Supply": {"kind": "AK", "ad_km": 0, "asm": 0, "year": 1960, "cargo_t": 3000},
}
CARRIER_KINDS = ("CV", "LH")
RADAR_MAST_M = 30        # ОЦЕНКА: высота антенн РЛС корабля (радиогоризонт по маловысотной цели)


def info(ship_type: str) -> dict:
    return SHIP_INFO.get(ship_type, {"kind": "FF", "ad_km": 0, "asm": 0})


def ships(state: dict, side: str | None = None) -> list[dict]:
    """Корабельные группы (живые)."""
    return [u for u in state["units"].values() if model.category(u) == "naval"
            and u.get("state") not in ("destroyed", "sunk") and model.strength(u) > 0 and (side is None or u["side"] == side)]


def threat_km(unit: dict) -> float:
    """Радиус ПВО группы: наибольший ЗРК кораблей в строю (повреждённый - пропорционально урону)."""
    ss = ship_state(unit)
    return max((info(t)["ad_km"] * (1.0 - ss[n]["dmg"]) for t, n in ship_names(unit)), default=0.0)


def kind(unit: dict) -> str:
    """Вид группы по головному кораблю: CSG (с авианосцем), SAG (надводные), FAC (катера), ARG (десантные), CONVOY."""
    kinds = [info(c["type"])["kind"] for c in unit.get("composition", [])]
    if any(k in CARRIER_KINDS for k in kinds):
        return "CSG" if "CV" in kinds else "ARG"
    if kinds and all(k in ("AK", "AO") for k in kinds):
        return "CONVOY"
    if kinds and all(k == "FAC" for k in kinds):
        return "FAC"
    if any(k == "LS" for k in kinds):
        return "ARG"
    return "SAG"


def carrier_alive(unit: dict) -> bool:
    ss = ship_state(unit)
    return any(info(t)["kind"] in CARRIER_KINDS and ss[n]["status"] != "sunk" for t, n in ship_list(unit))


def carrier_ship(unit: dict) -> tuple[str, str] | None:
    return next(((t, n) for t, n in ship_list(unit) if info(t)["kind"] in CARRIER_KINDS), None)


def daily(state: dict) -> list[str]:
    """Конец суток: потопленные группы, авианосцы - базы (позиция и состояние базы - по группе)."""
    lines = []
    for u in state["units"].values():
        if model.category(u) != "naval" or u.get("state") in ("destroyed", "sunk"):
            continue
        if not any(st["status"] != "sunk" for st in ship_state(u).values()):
            u["state"] = "sunk"
            lines.append(f"{u['name']}: группа потоплена.")
    for b in state["airbases"].values():
        if b.get("kind") != "carrier" or not b.get("naval"):
            continue
        u = state["units"].get(b["naval"])
        if not u:
            continue
        b["lat"], b["lon"] = u["pos"]["lat"], u["pos"]["lon"]
        if b.get("state") != "lost" and (u.get("state") == "sunk" or not carrier_alive(u)):
            b["state"] = "lost"
            lines.append(f"{b['name']}: авианосец потерян - палуба недоступна, авиакрыло без базы.")
            continue
        cs = carrier_ship(u)
        st = ship_state(u).get(cs[1]) if cs else None
        if st and b.get("state") != "lost":           # палуба: закрыта при уроне больше DECK_LIMIT или не в строю
            shut = st["status"] != "ok" or st["dmg"] > DECK_LIMIT
            if shut and b.get("state") != "closed":
                b["state"], b["deck_closed"] = "closed", True
                lines.append(f"{b['name']}: палуба закрыта (повреждение {st['dmg']:.0%}" + (", в порту)." if st["status"] != "ok" else ")."))
            elif not shut and b.pop("deck_closed", None):
                b["state"] = "open"
                lines.append(f"{b['name']}: палуба снова открыта.")
    return lines


def ship_list(unit: dict) -> list[tuple[str, str]]:
    """Все корабли группы по составу: [(класс pydcs, имя)], головной (авианосец) - первым."""
    out = []
    comp = sorted(unit.get("composition", []), key=lambda c: info(c["type"])["kind"] not in CARRIER_KINDS)
    for c in comp:
        names = c.get("names") or []
        for k in range(int(c["count"])):
            out.append((c["type"], names[k] if k < len(names) else f"{unit['name']} {c['type']} {k + 1}"))
    return out


def ship_state(unit: dict) -> dict:
    """Состояние кораблей группы: имя -> {dmg 0..1, status ok|transit|port|returning|sunk, days}."""
    ss = unit.setdefault("ships_state", {})
    for _t, nm in ship_list(unit):
        ss.setdefault(nm, {"dmg": 0.0, "status": "ok", "days": 0})
    return ss


def ship_names(unit: dict) -> list[tuple[str, str]]:
    """Корабли группы в строю (не потоплены, не ушли в порт): [(класс, имя)] - в миссии, в ПВО и залпе группы."""
    ss = ship_state(unit)
    return [(t, n) for t, n in ship_list(unit) if ss[n]["status"] == "ok"]


# ---------- выход в море и бой кораблей (конец суток) ----------
SPEED_KM_DAY = {"FAC": 600, "default": 450}     # ОЦЕНКА: переход за сутки (катера ~25 уз., корабли ~18 уз. с манёврами)
ENGAGE_KM = 40          # ОЦЕНКА: бой кораблей - группы ближе этого (дальность П-15 'Термит' ~40 км, 'Габриэль' ~20 км)
P_HIT = 0.3             # ОЦЕНКА: доля попаданий ПКР залпа (без РЭБ и ЗРК цели)
AD_SAVE = 0.5           # ОЦЕНКА: ЗРК и артиллерия корабля-цели сбивают столько ракет
HITS_TO_SINK = {"CV": 4, "LH": 3, "CG": 2.5, "DDG": 2, "FFG": 1.5, "FF": 1.2, "FAC": 1, "LS": 1.5, "AK": 1.5, "AO": 1.5}


def _move(state: dict, u: dict) -> str | None:
    """Приказ группы на сутки (orders: [{day, to: {lat, lon}, until_day}]): переход к точке, после until_day - домой."""
    from . import model as _m
    home = u.setdefault("home_pos", dict(u["pos"]))
    goal = None
    for o in sorted(u.get("orders") or [], key=lambda o: o["day"]):
        if state["day"] >= o["day"]:
            goal = o["to"] if state["day"] < o.get("until_day", 10**6) else home
    if not goal:
        return None
    d = _m.dist_km(u["pos"], goal)
    if d < 1:
        return None
    step = SPEED_KM_DAY.get(kind(u), SPEED_KM_DAY["default"])
    u["pos"] = dict(goal) if d <= step else _m.lerp(u["pos"], goal, step / d)
    return f"{u['name']}: переход {'домой' if goal is home else 'в район'} ({min(d, step):.0f} км)."


def asm_left(unit: dict, typ: str, name: str) -> int:
    """ПКР на борту корабля (боекомплект - SHIP_INFO asm; расходуется залпом, пополняется в порту)."""
    return int(ship_state(unit)[name].get("asm", info(typ)["asm"]))


def _salvo(u: dict) -> float:
    ss = ship_state(u)
    return sum(asm_left(u, t, n) * (1.0 - ss[n]["dmg"]) for t, n in ship_names(u)) * u.get("quality", 1.0)


def _fire(state: dict, u: dict) -> str | None:
    """Залп группы: корабли расходуют все ПКР на борту (катер 'Оса' - 4 'Термита' за бой); перезарядка - переход в
    порт и обратно (ASM_RELOAD: 2 перехода - ОЦЕНКА), до неё корабль в строю как ПВО и охранение."""
    fired = 0
    for t, n in ship_names(u):
        k = asm_left(u, t, n)
        if k > 0:
            st = ship_state(u)[n]
            st["asm"], st["asm_days"] = 0, 2 * _transit_days(state, u)
            fired += k
    if not fired:
        return None
    return f"{u['name']}: ПКР израсходованы ({fired}), перезарядка ~{2 * _transit_days(state, u)} сут."


def reload_asm(state: dict) -> list[str]:
    """Конец суток: перезарядка ПКР (корабль в строю, срок asm_days); после ремонта в порту - полный боекомплект."""
    lines = []
    for u in ships(state):
        done = []
        for t, n in ship_list(u):
            st = ship_state(u)[n]
            if "asm" not in st or st["status"] == "sunk":
                continue
            if st["status"] in ("port", "returning"):
                st.pop("asm"), st.pop("asm_days", None)
                continue
            st["asm_days"] = st.get("asm_days", 0) - 1
            if st["asm_days"] <= 0:
                st.pop("asm"), st.pop("asm_days", None)
                done.append(n)
        if done:
            lines.append(f"{u['name']}: ПКР пополнены ({', '.join(done)}).")
    return lines


# ---------- повреждения кораблей (ОЦЕНКИ) ----------
CREW_LIMIT = 0.2         # до этого урона - ремонт силами экипажа, корабль в строю
CREW_REPAIR = 0.05       # ремонт экипажем в сутки
PORT_REPAIR = 0.02       # ремонт в порту в сутки (недели)
SINK_HEAVY = 0.6         # больше - корабль, скорее всего, не спасти
SINK_P_TRANSIT = 0.15    # шанс затонуть в сутки перехода в порт при уроне SINK_HEAVY (растёт от CREW_LIMIT линейно)
SINK_P_HEAVY = (0.5, 0.8)  # шанс затонуть при уроне больше SINK_HEAVY: от 0.5 (у порога) до 0.8 (почти разрушен)
DECK_LIMIT = 0.2         # авианосец: больше - палуба закрыта (пожар, полётная палуба)
AI_CARRIER_CAP = 0.15    # удар ИИ вне миссии (итог по модели): урон авианосцу за сутки - не больше, и всего - не выше
                         # DECK_LIMIT: от расчёта палуба не закрывается; вывести авианосец из строя может только бой в миссии DCS
PORT_KM_DAY = 400        # повреждённый корабль идёт в порт медленнее (ОЦЕНКА)
OFF_MAP_DAYS = 2         # порт за картой (Неаполь, Субик-Бей): переход туда - столько суток


def _rng(state: dict, key: str):
    return model.rng(state, key)


def port_of(state: dict, unit: dict) -> dict | None:
    """Ближний свой порт (sector naval_bases), иначе None - порт за картой."""
    ports = (state.get("naval_bases") or {}).get(unit["side"]) or []
    return min(ports, key=lambda p: model.dist_km(p, unit["pos"])) if ports else None


def _transit_days(state: dict, unit: dict) -> int:
    p = port_of(state, unit)
    if not p:
        return OFF_MAP_DAYS
    return max(1, -(-int(model.dist_km(p, unit["pos"])) // PORT_KM_DAY))


def sink_p(dmg: float) -> float:
    """Шанс затонуть за сутки при уроне dmg (в порт или на месте без хода)."""
    if dmg <= CREW_LIMIT:
        return 0.0
    if dmg <= SINK_HEAVY:
        return SINK_P_TRANSIT * (dmg - CREW_LIMIT) / (SINK_HEAVY - CREW_LIMIT)
    lo, hi = SINK_P_HEAVY
    return lo + (hi - lo) * min(1.0, (dmg - SINK_HEAVY) / (1.0 - SINK_HEAVY))


def damage(state: dict, unit: dict, name: str, add: float, why: str) -> str:
    """Урон кораблю (доля прочности): 1 и больше - потоплен; больше CREW_LIMIT - уходит в порт."""
    ss = ship_state(unit)
    st = ss.get(name)
    if not st or st["status"] == "sunk" or add <= 0:
        return ""
    st["dmg"] = min(1.0, st["dmg"] + add)
    typ = next((t for t, n in ship_list(unit) if n == name), None)
    if st["dmg"] >= 0.999:
        return sink(unit, name, why)
    if st["dmg"] > CREW_LIMIT and st["status"] == "ok":
        st["status"], st["days"] = "transit", _transit_days(state, unit)
        return f"{name} ({why}): повреждение {st['dmg']:.0%} - выходит из боя, идёт в порт."
    return f"{name} ({why}): повреждение {st['dmg']:.0%}" + (" - ремонт силами экипажа." if typ else ".")


def sink(unit: dict, name: str, why: str) -> str:
    ss = ship_state(unit)
    st = ss[name]
    st["status"], st["dmg"] = "sunk", 1.0
    typ = next((t for t, n in ship_list(unit) if n == name), None)
    if typ:
        unit["lost"][typ] = unit["lost"].get(typ, 0.0) + 1.0
    return f"{name} ({why}): потоплен."


def apply_hits(state: dict, unit: dict, hits: float, why: str, ai: bool = False) -> list[str]:
    """Попадания по группе - сначала по кораблям охранения (прикрывают главный), по одному кораблю за раз:
    попадание = 1 / HITS_TO_SINK прочности. ai - итог по модели (не бой в DCS): урон авианосцу - не больше AI_CARRIER_CAP."""
    lines = []
    order = sorted(ship_names(unit), key=lambda tn: (info(tn[0])["kind"] in CARRIER_KINDS, HITS_TO_SINK.get(info(tn[0])["kind"], 1.5)))
    ss = ship_state(unit)
    for typ, nm in order:
        if hits <= 0.01:
            break
        need = HITS_TO_SINK.get(info(typ)["kind"], 1.5)
        room = 1.0 - ss[nm]["dmg"]
        if ai and info(typ)["kind"] in CARRIER_KINDS:   # итог по модели: за сутки - не больше AI_CARRIER_CAP и не выше
            day_room = AI_CARRIER_CAP - (ss[nm].get("ai_day_dmg", 0.0) if ss[nm].get("ai_day") == state["day"] else 0.0)
            room = min(room, max(0.0, day_room), max(0.0, DECK_LIMIT - 0.01 - ss[nm]["dmg"]))   # палуба остаётся открытой
        take = min(room, hits / need)
        if take <= 0:
            continue
        if ai and info(typ)["kind"] in CARRIER_KINDS:
            if ss[nm].get("ai_day") != state["day"]:
                ss[nm]["ai_day"], ss[nm]["ai_day_dmg"] = state["day"], 0.0
            ss[nm]["ai_day_dmg"] += take
        ln = damage(state, unit, nm, take, why)
        if ln:
            lines.append(ln)
        hits -= take * need
    return lines


def air_strike(state: dict, unit: dict, pairs: float, why: str, asm_frac: float = 1.0) -> list[str]:
    """Удар ИИ с воздуха по группе (итог по модели): попаданий - HITS_PER_PAIR на пару ударной группы, ПВО группы
    (корабли с ЗРК) отражает часть: x 1 / (1 + сумма ad_km / AD_SCREEN_KM); asm_frac - доля самолётов с ПКР
    (остальные - бомбы, x BOMB_K). ОЦЕНКИ."""
    ad = sum(info(t)["ad_km"] for t, _n in ship_names(unit))
    hits = pairs * HITS_PER_PAIR * (asm_frac + (1.0 - asm_frac) * BOMB_K) / (1.0 + ad / AD_SCREEN_KM)
    return apply_hits(state, unit, hits, why, ai=True)


# ---------- запас авиационных ПКР стороны (sector asm_stock: {side: {count, per_day}}; нет стороны - без учёта) ----------
BOMB_K = 0.35            # ОЦЕНКА: без ПКР - бомбы с малой высоты: попаданий меньше (надо пройти над ордером)
BOMB_LOSS_P = 0.12       # ОЦЕНКА: добавка к потерям на самолёт при бомбометании по кораблям с ЗРК


def air_asm(state: dict, side: str) -> int | None:
    st = (state.get("asm_stock") or {}).get(side)
    return None if st is None else int(st.get("count", 0))


def use_air_asm(state: dict, side: str, need: int) -> float:
    """Списать ПКР на удар: доля самолётов с ПКР (1.0 - все, 0 - только бомбы). Без учёта у стороны - 1.0."""
    st = (state.get("asm_stock") or {}).get(side)
    if st is None or need <= 0:
        return 1.0
    take = min(int(st.get("count", 0)), need)
    st["count"] = int(st.get("count", 0)) - take
    return take / need


def air_asm_resupply(state: dict) -> list[str]:
    for st in (state.get("asm_stock") or {}).values():
        st["count"] = int(st.get("count", 0)) + int(st.get("per_day", 0))
    return []


HITS_PER_PAIR = 1.0      # ОЦЕНКА: попаданий (ПКР, бомб) на пару ударной группы без ПВО цели
AD_SCREEN_KM = 100       # ОЦЕНКА: на каждые 100 км суммарной дальности ЗРК кораблей группы - вдвое меньше попаданий


def repairs(state: dict) -> list[str]:
    """Конец суток: ремонт экипажем (урон до CREW_LIMIT), переход в порт (шанс затонуть), ремонт в порту, возврат."""
    lines = []
    for u in state["units"].values():
        if model.category(u) != "naval" or u.get("state") in ("destroyed", "sunk"):
            continue
        for typ, nm in ship_list(u):
            st = ship_state(u)[nm]
            if st["status"] == "ok" and st["dmg"] > 0:
                st["dmg"] = max(0.0, st["dmg"] - CREW_REPAIR)
                if st["dmg"] == 0:
                    lines.append(f"{nm}: повреждения устранены экипажем.")
            elif st["status"] == "transit":
                r = _rng(state, f"sink-{u['id']}-{nm}-{state['day']}")
                if (r.random() if r else 1.0) < sink_p(st["dmg"]):
                    lines.append(sink(u, nm, f"затонул на переходе в порт, повреждение {st['dmg']:.0%}"))
                    continue
                st["days"] -= 1
                if st["days"] <= 0:
                    p = port_of(state, u)
                    st["status"], st["days"] = "port", -(-int(st["dmg"] * 100) // int(PORT_REPAIR * 100))
                    lines.append(f"{nm}: дошёл до порта ({p['name'] if p else 'за картой'}), ремонт ~{st['days']} сут.")
            elif st["status"] == "port":
                st["dmg"] = max(0.0, st["dmg"] - PORT_REPAIR)
                st["days"] -= 1
                if st["dmg"] <= 0 or st["days"] <= 0:
                    st["dmg"], st["status"], st["days"] = 0.0, "returning", _transit_days(state, u)
            elif st["status"] == "returning":
                st["days"] -= 1
                if st["days"] <= 0:
                    st["status"] = "ok"
                    lines.append(f"{nm}: после ремонта вернулся в {u['name']}.")
    return lines


def from_mission(state: dict, unit: dict, life: dict[str, float]) -> list[str]:
    """Дебриф: остаток прочности кораблей в DCS (life 0..1) - урон за миссию прибавляется к урону модели (корабль
    в миссии появляется целым: повреждения модели DCS не передаются)."""
    lines = []
    for _t, nm in ship_names(unit):
        if nm in life and life[nm] < 0.999:
            ln = damage(state, unit, nm, 1.0 - life[nm], "бой в миссии")
            if ln:
                lines.append(ln)
    return lines


def engage(state: dict) -> list[str]:
    """Бой корабельных групп противников ближе ENGAGE_KM: залпы ПКР с обеих сторон (попадания - P_HIT, ЗРК цели -
    AD_SAVE, выучка - quality группы, РЭБ - ecm цели). Все числа - ОЦЕНКИ."""
    lines = []
    blue, red = ships(state, "blue"), ships(state, "red")
    for b in blue:
        for r in red:
            if model.dist_km(b["pos"], r["pos"]) > ENGAGE_KM:
                continue
            sb, sr = _salvo(b), _salvo(r)
            if sb <= 0 and sr <= 0:
                continue
            # ecm - доля ПКР противника, уведённых помехами (1973: все 'Термиты' по 'Сааръ' ушли в ловушки - ОЦЕНКА)
            hit_r = sb * P_HIT * (AD_SAVE if threat_km(r) > 0 else 1.0) * (1.0 - r.get("ecm", 0.0))
            hit_b = sr * P_HIT * (AD_SAVE if threat_km(b) > 0 else 1.0) * (1.0 - b.get("ecm", 0.0))
            lines.append(f"Бой кораблей: {b['name']} и {r['name']}.")
            lines += [x for x in (_fire(state, b) if sb > 0 else None, _fire(state, r) if sr > 0 else None) if x]
            lines += apply_hits(state, r, hit_r, f"бой с {b['name']}")
            lines += apply_hits(state, b, hit_b, f"бой с {r['name']}")
    return lines


def daily_moves(state: dict) -> list[str]:
    lines = []
    for u in ships(state):
        ln = _move(state, u)
        if ln:
            lines.append(ln)
    lines += reload_asm(state)                   # пополнение ПКР - до боя: перезарядка суток уже на борту
    return lines + engage(state) + repairs(state) + air_asm_resupply(state)


# ---------- морской подвоз ----------
BLOCKADE_KM = 60        # ОЦЕНКА: корабли противника у пути конвоя ближе этого - блокада
BLOCKADE_K = 0.5        # ОЦЕНКА: при блокаде доходит такая доля груза


def sea_supply(state: dict, side: str) -> dict[str, float]:
    """Морской подвоз суток стороны (sector sea_lanes: {id, side, port, convoy, t_per_day}): склад порта -> тонн. Груз -
    t_per_day x доля уцелевших транспортов конвоя (удары по конвою); блокада (корабли противника у конвоя) -
    x BLOCKADE_K. После - новый конвой следующих суток (потери конвоя сброшены)."""
    out: dict[str, float] = {}
    foe = model.enemy(side)
    for ln in state.get("sea_lanes") or []:
        if ln["side"] != side:
            continue
        cv = state["units"].get(ln.get("convoy") or "")
        k = model.strength(cv) if cv else 1.0
        if cv and not cv.get("protected") and any(model.dist_km(s["pos"], cv["pos"]) <= BLOCKADE_KM and _salvo(s) > 0
                                                  for s in ships(state, foe)):
            k *= BLOCKADE_K
        out[ln["port"]] = out.get(ln["port"], 0.0) + ln["t_per_day"] * k
        if cv:
            ln["_last"] = {"day": state["day"], "t": round(ln["t_per_day"] * k), "lost_frac": round(1 - model.strength(cv), 2)}
            cv["lost"] = {}                      # новый конвой следующих суток
            cv["ships_state"] = {}
            cv["state"] = "deployed"
    return out

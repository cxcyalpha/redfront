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
    """Радиус ПВО группы: наибольший ЗРК живых кораблей."""
    alive = model.alive_by_type(unit)
    return max((info(t)["ad_km"] for t, n in alive.items() if n >= 0.5), default=0.0)


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
    alive = model.alive_by_type(unit)
    return any(info(t)["kind"] in CARRIER_KINDS and n >= 0.5 for t, n in alive.items())


def daily(state: dict) -> list[str]:
    """Конец суток: потопленные группы, авианосцы - базы (позиция и состояние базы - по группе)."""
    lines = []
    for u in state["units"].values():
        if model.category(u) != "naval" or u.get("state") in ("destroyed", "sunk"):
            continue
        if model.strength(u) <= 0.01:
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
    return lines


def ship_names(unit: dict) -> list[tuple[str, str]]:
    """Живые корабли группы для миссии: [(тип pydcs, имя)], головной (авианосец) - первым."""
    out = []
    comp = sorted(unit.get("composition", []), key=lambda c: info(c["type"])["kind"] not in CARRIER_KINDS)
    for c in comp:
        alive = int(round(max(0.0, c["count"] - unit["lost"].get(c["type"], 0.0))))
        names = c.get("names") or []
        for k in range(alive):
            out.append((c["type"], names[k] if k < len(names) else f"{unit['name']} {c['type']} {k + 1}"))
    return out


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


def _salvo(u: dict) -> float:
    alive = model.alive_by_type(u)
    return sum(info(t)["asm"] * n for t, n in alive.items()) * u.get("quality", 1.0)


def _take_hits(u: dict, hits: float) -> float:
    """Попадания - по кораблям группы, сначала мелким (охранение прикрывает главный корабль): потеряно кораблей."""
    lost = 0.0
    for c in sorted(u["composition"], key=lambda c: HITS_TO_SINK.get(info(c["type"])["kind"], 1.5)):
        if hits <= 0:
            break
        alive = max(0.0, c["count"] - u["lost"].get(c["type"], 0.0))
        need = HITS_TO_SINK.get(info(c["type"])["kind"], 1.5)
        k = min(alive, hits / need)
        u["lost"][c["type"]] = u["lost"].get(c["type"], 0.0) + k
        hits -= k * need
        lost += k
    return lost


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
            lr, lb = _take_hits(r, hit_r), _take_hits(b, hit_b)
            lines.append(f"Бой кораблей: {b['name']} и {r['name']} - потоплено {lb:.1f} и {lr:.1f} корабля.")
    return lines


def daily_moves(state: dict) -> list[str]:
    lines = []
    for u in ships(state):
        ln = _move(state, u)
        if ln:
            lines.append(ln)
    return lines + engage(state)


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
            cv["state"] = "deployed"
    return out

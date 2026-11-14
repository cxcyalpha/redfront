"""Воздушный бой вне миссии (вылеты ИИ плана полётов, airwar.py). Все числа - ОЦЕНКИ.

Ударную группу у цели могут перехватить истребители противника: дежурство в зоне (cap_own_troops, fleet_cap -
орбита не дальше CAP_REACH_KM от цели, на смене во время удара) и дежурные пары на аэродромах (qra - база не дальше
scramble_km доктрины). Перехват удаётся с вероятностью P_INTERCEPT (дежурство - выше: уже в воздухе; ДРЛО стороны -
выше). Прикрытие пакета (cover, sweep, escort) связывает перехватчиков: часть их не доходит до ударной группы.

Бой - обмен потерями: каждая сторона сбивает KILL_PER_AIRCRAFT x борт x доля её качества (оценка типа air,
aircraft.json, и выучка стороны sim.air_skill доктрины) в паре. Перехватчики бьют сначала прикрытие, остальное - по
ударной; ударная группа отвечает слабо (STRIKER_AIR_K). Перехваченная ударная группа часть бортов теряет, часть
сбрасывает нагрузку - удар слабее (JETTISON_K). Расход ракет воздух-воздух - из запаса стороны (munitions).
"""
from __future__ import annotations

from . import model

CAP_REACH_KM = 60         # ОЦЕНКА: зона дежурства прикрывает цели в таком радиусе
P_INTERCEPT = {"cap": 0.45, "qra": 0.3}   # ОЦЕНКА: доля успешных перехватов (наведение, время, высота)
AWACS_BONUS = 0.15        # ОЦЕНКА: у стороны ДРЛО в воздухе - перехват вероятнее
ESCORT_TIE = 0.6          # ОЦЕНКА: доля перехватчиков, которых связывает прикрытие на один свой борт против их одного
KILL_PER_AIRCRAFT = 0.35  # ОЦЕНКА: сбитых на борт за бой при равных качествах (поровну - 0.35 x 0.5)
STRIKER_AIR_K = 0.3       # ОЦЕНКА: ударная группа в бою - слабее по воздуху (нагрузка, задача)
JETTISON_K = 0.5          # ОЦЕНКА: перехваченная ударная группа - удар вдвое слабее (сброс, срыв захода)
AAM_PER_KILL = 2.5        # ОЦЕНКА: пусков ракет на сбитый (с учётом промахов)
ESCORT_GROUPS = ("cover", "sweep", "escort")


# выучка лётчиков и тактика стороны в воздушном бою (ОЦЕНКИ по соотношениям потерь: Израиль 1967-1982 - десятки к
# одному против ВВС арабских стран, США во Вьетнаме 1972 - ~2:1 против ВНА); доктрина может задать sim.air_skill
AIR_SKILL = {"Israel": 1.8, "USA": 1.2, "UK": 1.2, "Germany": 1.1, "France": 1.1, "Syria": 0.6, "Egypt": 0.6,
             "Iraq": 0.6, "Iran": 0.8, "Vietnam": 1.0, "Russia": 1.0, "USSR": 1.0, "Ukraine": 1.0, "Georgia": 0.8}


def _quality(state: dict, side: str, type_name: str) -> float:
    from . import fitness
    a = fitness.absolute(type_name, "air")
    sk = model.doctrine(state, side)["sim"].get(
        "air_skill", AIR_SKILL.get((state.get("countries") or {}).get(side, ""), 1.0))
    return max(0.05, (a if a is not None else 0.5)) * sk


def interceptors(state: dict, side: str, pos: dict, t: float) -> list[dict]:
    """Группы истребителей стороны side, которые могут перехватить у pos в момент t: [{perf, size, how}]."""
    out = []
    for e in (state.get("ato") or {}).get("entries", []):
        if e["side"] != side:
            continue
        g = e["task"]["package"][0]
        tm = e["times"].get(g["group"]) or {}
        perf = state["units"].get(g["performer"])
        if not perf or perf.get("count", 0) <= 0:
            continue
        kind = g["objective"]["kind"]
        if kind == "alert":
            tdef = model.doctrine(state, side)["tasks"].get(e["kind"], {})
            if tm.get("takeoff_s", 0) <= t <= tm.get("land_s", 0) and \
                    model.dist_km(state["airbases"][g["base"]], pos) <= tdef.get("scramble_km", 150):
                out.append({"perf": perf, "size": min(g["size"], perf["count"]), "how": "qra", "entry": e})
        elif kind in ("cap_zone", "orbit") and e["kind"] in ("cap_own_troops", "fleet_cap", "cap", "barcap"):
            zone = g["objective"].get("pos") or (g.get("route") or [None])[0]
            if zone and tm.get("objective_s", 0) <= t <= tm.get("land_s", 0) and model.dist_km(zone, pos) <= CAP_REACH_KM:
                out.append({"perf": perf, "size": min(g["size"], perf["count"]), "how": "cap", "entry": e})
    return out


def _awacs_up(state: dict, side: str, t: float) -> bool:
    for e in (state.get("ato") or {}).get("entries", []):
        if e["side"] == side and e["kind"] == "awacs_orbit":
            tm = next(iter(e["times"].values()), {})
            if tm.get("takeoff_s", 0) <= t <= tm.get("land_s", 1e9):
                return True
    return bool((state.get("external_awacs") or {}).get(side))


def _lose(state: dict, perf: dict, n: int, pos: dict, tag: str, r) -> int:
    """n бортов части сбито в воздушном бою: экипажи - катапультирование или гибель (как в airwar)."""
    from . import airwar, csar
    n = min(n, perf.get("count", 0))
    if n <= 0:
        return 0
    perf["count"] -= n
    for k in range(n):
        if (r.random() if r else 1.0) < airwar.EJECT_P:
            csar.add_downed(state, perf, f"{tag}:{k}", model.offset(pos, 45.0 * k, 3000 + 700 * k))
        elif "crews" in perf:
            from . import pilots
            pilots.killed(perf, pilots.take(perf), "погиб", state["day"])
            perf["crews"] = max(0, perf["crews"] - 1)
    return n


def _rounds(x: float, r) -> int:
    """Целое из дробного ожидания: целая часть + случайный остаток (без случайности - округление)."""
    base = int(x)
    rest = x - base
    return base + (1 if (r.random() < rest if r else rest >= 0.5) else 0)


def _spend_aam(state: dict, side: str, shots: float) -> None:
    from . import munitions
    if shots <= 0:
        return
    got = munitions.take(state, side, "aam_r", shots * 0.6)
    munitions.take(state, side, "aam_ir", shots - got)


def engage(state: dict, e: dict, pos: dict, t: float, strike_size: int) -> tuple[int, float, list[str]]:
    """Воздушный бой у цели удара e (ударная группа strike_size бортов). -> (сбито ударных, множитель удара, строки)."""
    side, foe = e["side"], model.enemy(e["side"])
    r = model.rng(state, f"aircombat-{e['id']}")
    ints = interceptors(state, foe, pos, t)
    if not ints or strike_size <= 0:
        return 0, 1.0, []
    bonus = AWACS_BONUS if _awacs_up(state, foe, t) else 0.0
    came = []                                    # долетевшие до боя
    for it in ints:
        p = min(0.9, P_INTERCEPT[it["how"]] + bonus)
        if (r.random() < p) if r else p >= 0.5:
            came.append(it)
    if not came:
        return 0, 1.0, []
    pkg = e["task"]["package"]
    strike_perf = state["units"].get(pkg[0]["performer"])
    esc = [(state["units"][g["performer"]], g["size"]) for g in pkg[1:]
           if g["group"].rstrip("0123456789") in ESCORT_GROUPS and g["performer"] in state["units"]]
    n_esc = sum(min(n, u.get("count", 0)) for u, n in esc)
    n_int = sum(it["size"] for it in came)
    q_int = sum(_quality(state, foe, it["perf"]["type"]) * it["size"] for it in came) / max(1, n_int)
    q_esc = (sum(_quality(state, side, u["type"]) * min(n, u.get("count", 0)) for u, n in esc) / n_esc) if n_esc else 0.0
    q_str = _quality(state, side, strike_perf["type"]) * STRIKER_AIR_K if strike_perf else 0.05
    # прикрытие связывает часть перехватчиков; остальные - по ударной группе
    tied = min(n_int, n_esc * ESCORT_TIE * (q_esc / max(1e-6, q_esc + q_int)) * 2) if n_esc else 0.0
    free = n_int - tied
    # обмен: кто кого сбил (ожидания)
    k_int_esc = tied * KILL_PER_AIRCRAFT * q_int / max(1e-6, q_int + q_esc) if n_esc else 0.0
    k_esc_int = n_esc * KILL_PER_AIRCRAFT * q_esc / max(1e-6, q_int + q_esc) if n_esc else 0.0
    k_int_str = free * KILL_PER_AIRCRAFT * q_int / max(1e-6, q_int + q_str)
    k_str_int = strike_size * KILL_PER_AIRCRAFT * q_str / max(1e-6, q_int + q_str) * (free / max(1, n_int))
    lines = []
    lost_str = min(strike_size, _rounds(k_int_str, r))
    if strike_perf and lost_str:
        _lose(state, strike_perf, lost_str, pos, f"air:{e['id']}:s", r)
    lost_esc = 0
    for u, n in esc:                             # потери прикрытия - по группам пропорционально
        k = min(n, _rounds(k_int_esc * n / max(1, n_esc), r))
        lost_esc += _lose(state, u, k, pos, f"air:{e['id']}:e{u['id']}", r)
    lost_int = 0
    k_tot = k_esc_int + k_str_int
    for it in came:
        k = min(it["size"], _rounds(k_tot * it["size"] / max(1, n_int), r))
        lost_int += _lose(state, it["perf"], k, pos, f"air:{e['id']}:i{it['perf']['id']}", r)
    _spend_aam(state, foe, (k_int_esc + k_int_str) * AAM_PER_KILL)
    _spend_aam(state, side, k_tot * AAM_PER_KILL)
    names = ", ".join(sorted({it["perf"]["name"] for it in came}))
    lines.append(f"Воздушный бой у цели ({e['title']}): перехват - {n_int} ({names}); "
                 + (f"прикрытие {n_esc}; " if n_esc else "без прикрытия; ")
                 + f"сбито: ударных {lost_str}, прикрытия {lost_esc}, перехватчиков {lost_int}.")
    # перехваченная группа: удар слабее по доле бортов, до которых дошли перехватчики
    hit = min(1.0, free / max(1, strike_size))
    return lost_str, 1.0 - (1.0 - JETTISON_K) * hit, lines

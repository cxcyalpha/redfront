"""Стратегический уровень: удары баллистическими (Скад-Б, Точка-У, Искандер) и крылатыми (Томагавк с кораблей) ракетами.

Сутки: сторона с пусковыми и запасом ракет планирует пуски на следующие сутки (ssm_plan) - по аэродромам и складам
противника в досягаемости, ценные цели первыми; конец суток - исход: перехват ПРО (Patriot, С-300 у цели), попадание
по точности ракеты, повреждение объекта (аэродром - меньше вылетов, склад - меньше запаса; восстановление - logistics).
Пусковая уничтожена или подавлена в миссии - её пуски не состоялись. Пусковые после пусков меняют позицию в районе
(стрельба с переездом) - охота за ними в миссиях, как в 1991. В миссии игрока пуски того же дня идут по времени
(ssm.lua, FireAtPoint): ракеты летят по-настоящему. Все числа - ОЦЕНКИ, источники - в MISSILES.
"""
from __future__ import annotations

import math
import random
import re

from . import model

# ракета: дальность, км; круговое вероятное отклонение, м; боевая часть, кг; пусков с пусковой в сутки; модель DCS
MISSILES = {
    "scud": {"title": "Р-17 (Скад-Б)", "range_km": 300, "cep_m": 900, "warhead_kg": 985, "per_day": 1.0,
             "dcs": "Scud_B", "source": "Zaloga 'Scud Ballistic Missile' (2006): 300 км, КВО 450-1000 м; Ирак 1991 - ~88 пусков "
                                          "за 43 суток примерно с 30 пусковых (ОЦЕНКА темпа - не больше 1 в сутки)"},
    "tochka": {"title": "9К79-1 Точка-У", "range_km": 120, "cep_m": 150, "warhead_kg": 482, "per_day": 2.0,
               "dcs": "Scud_B", "stand_in": "в DCS Точки нет - модель Скада, дальность и точность - Точки-У",
               "source": "Точка-У (1989): 120 км, КВО ~50-150 м; темп - ОЦЕНКА"},
    "iskander": {"title": "9К720 Искандер-М", "range_km": 500, "cep_m": 10, "warhead_kg": 480, "per_day": 2.0,
                 "dcs": "CHAP_9K720_HE",       # CurrentHill - встроен в DCS (есть в pydcs)
                 "source": "Искандер-М: до 500 км, КВО 5-30 м (открытые оценки); темп - ОЦЕНКА"},
    "tlam": {"title": "BGM-109 Томагавк", "range_km": 1300, "cep_m": 10, "warhead_kg": 450, "per_day": 4.0,
             "source": "TLAM-C: ~1250-1600 км, КВО ~10 м; пуски с кораблей с бронированными пусковыми (ABL) или УВП"},
}
# доля повреждения объекта от одного попадания (ОЦЕНКА): аэродром - полосы и стоянки большие, одна ракета - немного
HIT_DAMAGE = {"airfield": 0.06, "depot": 0.10, "factory": 0.08}
LETHAL_R_M = {"airfield": 400, "depot": 150, "factory": 150}   # ОЦЕНКА: промах больше - урона нет
TARGET_VALUE = {"airfield": 3.0, "depot": 2.0, "factory": 1.0}
# ПРО: перехват ракеты у цели (ОЦЕНКА; Patriot PAC-2 1991 - спорно, по разным оценкам от 10% до 70%)
ABM = [(r"Patriot", 1991, {"scud": 0.4, "tochka": 0.3, "iskander": 0.15}),
       (r"S-300|S_300|5P85", 1985, {"scud": 0.4, "tochka": 0.3})]
ABM_KM = 40            # ОЦЕНКА: ЗРК прикрывает цель от баллистической ракеты в этом радиусе
CM_INTERCEPT = 0.15    # ОЦЕНКА: крылатую ракету сбивает каждый ЗРК средней/большой дальности у цели (не больше CM_MAX)
CM_MAX = 0.5
DAILY_SHARE = 0.25     # ОЦЕНКА: в сутки - не больше этой доли оставшегося запаса ракет (сценарий: strategic_per_day)
SCOOT_KM = (5, 15)     # ОЦЕНКА: смена позиции пусковой после пусков, км от района развёртывания
# корабли с Томагавком - по имени корабля (модели DCS бывают за другой класс): (образец имени, ракет)
TLAM_SHIPS = [(r"Merrill \(DD-976\)", 8),      # первый эсминец Spruance с ABL (1983)
              (r"New Jersey", 32), (r"Iowa \(BB-61\)", 32), (r"Missouri", 32), (r"Wisconsin", 32),
              (r"\(CG-5[2-9]\)|\(CG-[6-7]\d\)", 26),   # Ticonderoga с УВП Mk 41 (с CG-52, 1986)
              (r"\(DDG-5[1-9]\)|\(DDG-[6-9]\d\)", 8)]   # Arleigh Burke (с 1991)


def launchers(state: dict, side: str) -> list[dict]:
    """Пусковые стороны: части ssm (баллистика) и корабельные группы с кораблями, несущими Томагавк."""
    out = []
    for u in state["units"].values():
        if u.get("side") != side or u.get("state") in ("destroyed", "pending", "sunk"):
            continue
        if model.category(u) == "ssm":
            n = int(round(sum(model.alive_by_type(u).values())))
            if n > 0:
                out.append({"unit": u["id"], "missile": u.get("missile", "scud"), "n": n, "pos": model.unit_pos(state, u)})
        elif model.category(u) == "naval":
            from . import naval
            n = sum(1 for _t, nm in naval.ship_names(u) if any(re.search(rx, nm) for rx, _k in TLAM_SHIPS))
            if n:
                out.append({"unit": u["id"], "missile": "tlam", "n": n, "pos": model.unit_pos(state, u)})
    return out


def _targets(state: dict, side: str) -> list[dict]:
    lim = set((state.get("air_limits") or {}).get(side, []))
    out = []
    for u in state["units"].values():
        if u.get("side") != model.enemy(side) or u.get("role") not in TARGET_VALUE or u.get("state") == "lost":
            continue
        if u.get("place") in lim or u["id"] in lim:
            continue
        out.append(u)
    return out


def plan(state: dict) -> list[str]:
    """План пусков на сутки: каждая пусковая - по ценной цели в досягаемости (больше ценности - меньше повреждение
    цели), пока есть ракеты. Сторона без запаса (strategic_stock) ракет этого типа не пускает."""
    rng = random.Random(f"{state['campaign_id']}-ssm-{state['day']}")
    stock = state.setdefault("strategic_stock", {})
    plan_ = []
    for side in model.SIDES:
        left = dict(stock.get(side) or {})
        if not any(v > 0 for v in left.values()):
            continue
        per_day = (state.get("strategic_per_day") or {}).get(side) or {}
        left = {k: min(v, per_day.get(k, max(1, math.ceil(v * DAILY_SHARE)) if v > 0 else 0)) for k, v in left.items()}
        tg = _targets(state, side)
        for ln in launchers(state, side):
            m = MISSILES[ln["missile"]]
            shots = min(int(ln["n"] * m["per_day"]), int(left.get(ln["missile"], 0)))
            if shots <= 0:
                continue
            reach = [t for t in tg if model.dist_km(ln["pos"], model.unit_pos(state, t)) <= m["range_km"]]
            if not reach:
                continue
            reach.sort(key=lambda t: -TARGET_VALUE[t["role"]] * (1.0 - t.get("damage", 0.0)))
            for k in range(shots):
                t = reach[k % min(len(reach), 3)]          # не больше трёх целей на пусковую: удары сосредоточены
                plan_.append({"side": side, "unit": ln["unit"], "missile": ln["missile"], "target": t["id"],
                              "t_s": int(rng.uniform(5, 20) * 3600)})
                left[ln["missile"]] = left.get(ln["missile"], 0) - 1
    state["ssm_plan"] = plan_
    return [f"План пусков ракет на сутки - {sum(1 for p in plan_ if p['side'] == s)} ({s})." for s in model.SIDES
            if any(p["side"] == s for p in plan_)]


def _abm(state: dict, side_def: str, pos: dict, missile: str) -> float:
    year = int(str(state.get("date", "2000"))[:4])
    p_miss = 1.0
    if missile == "tlam":
        n = sum(1 for u in state["units"].values() if u.get("side") == side_def and u["role"] in ("sam_long", "sam_medium")
                and u["state"] not in ("destroyed", "pending") and model.dist_km(model.unit_pos(state, u), pos) <= 30)
        return min(CM_MAX, n * CM_INTERCEPT)
    for u in state["units"].values():
        if u.get("side") != side_def or model.category(u) != "sam" or u.get("state") in ("destroyed", "pending"):
            continue
        types = " ".join(c["type"] for c in u.get("composition", []))
        for rx, y0, p in ABM:
            if year >= y0 and re.search(rx, types) and model.dist_km(model.unit_pos(state, u), pos) <= ABM_KM:
                p_miss *= 1.0 - p.get(missile, 0.0)
    return 1.0 - p_miss


def _p_hit(cep_m: float, lethal_m: float) -> float:
    """Вероятность попасть в круг поражения при круговом нормальном рассеянии (КВО - медиана промаха)."""
    return 1.0 - math.exp(-math.log(2) * (lethal_m / cep_m) ** 2)


def resolve(state: dict) -> list[str]:
    """Исход пусков суток (ssm_plan): пусковая жива - пуск; перехват; попадание; повреждение; расход ракет; переезд."""
    rng = random.Random(f"{state['campaign_id']}-ssmres-{state['day']}")
    stock = state.setdefault("strategic_stock", {})
    lines, by = [], {}
    moved = set()
    for p in state.get("ssm_plan") or []:
        u = state["units"].get(p["unit"])
        t = state["units"].get(p["target"])
        if not u or not t or u["state"] in ("destroyed", "sunk") or (model.category(u) == "ssm" and model.strength(u) <= 0):
            continue
        s = stock.setdefault(p["side"], {})
        if s.get(p["missile"], 0) <= 0:
            continue
        s[p["missile"]] -= 1
        m = MISSILES[p["missile"]]
        key = (p["side"], t["id"], p["missile"])
        r = by.setdefault(key, {"n": 0, "int": 0, "hit": 0, "name": t["name"], "m": m["title"]})
        r["n"] += 1
        if rng.random() < _abm(state, t["side"], model.unit_pos(state, t), p["missile"]):
            r["int"] += 1
            continue
        if rng.random() < _p_hit(m["cep_m"], LETHAL_R_M[t["role"]]):
            r["hit"] += 1
            t["damage"] = min(1.0, t.get("damage", 0.0) + HIT_DAMAGE[t["role"]] * m["warhead_kg"] / 500.0)
        if model.category(u) == "ssm" and u["id"] not in moved:
            moved.add(u["id"])
            home = u.setdefault("home_pos", dict(u["pos"]))
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(*SCOOT_KM)
            u["pos"] = {"lat": home["lat"] + d * math.cos(a) / 111.32,
                        "lon": home["lon"] + d * math.sin(a) / (111.32 * math.cos(math.radians(home["lat"])))}
    for (side, _tid, _m), r in by.items():
        lines.append(f"Ракетный удар (сторона {side}) - {r['m']} по объекту {r['name']}, пусков {r['n']}, перехвачено "
                     f"{r['int']}, попаданий {r['hit']}.")
    for side, add in (state.get("strategic_resupply") or {}).items():
        for k, v in add.items():
            stock.setdefault(side, {})[k] = stock.get(side, {}).get(k, 0) + v
    state["ssm_plan"] = []
    return lines


def daily(state: dict) -> list[str]:
    """Конец суток: исход пусков суток, затем план на следующие."""
    return resolve(state) + plan(state)


def mission_launches(state: dict, start_s: int, dur_s: int) -> list[dict]:
    """Пуски суток, попадающие во время миссии: (пусковая, цель, время от начала миссии)."""
    return [dict(p, at_s=p["t_s"] - start_s) for p in state.get("ssm_plan") or []
            if start_s <= p["t_s"] <= start_s + dur_s and model.category(state["units"][p["unit"]]) == "ssm"]

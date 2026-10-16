"""Экипажи и поиск-спасение (CSAR). Механика в миссии (маяк ADF, дым и ракета по запросу, подбор посадкой рядом или
зависанием с лебёдкой, доставка на свой аэродром) - по мотивам DCS-CSAR (ciribob, github.com/ciribob/DCS-CSAR):
лицензии у него нет, поэтому код свой, без MIST (lua/csar.lua). Все числа - ОЦЕНКИ (crews_note доктрины).

Модель: у авиачасти crews экипажей (штат crews0 = crew_ratio x самолётов штата); к вылету - не больше экипажей
(logistics.available). Самолёт сбит:
  * без катапультирования - экипаж погиб (crews - 1);
  * катапультировался - экипаж на земле: state['downed'] (crews - 1, пока не вернётся). В той же миссии его может
    подобрать вертолёт (lua/csar.lua); иначе - в модели: на своей территории выходит к своим на следующие сутки,
    на чужой - каждые сутки попадает в плен с вероятностью capture_per_day, через downed_max_days суток - пропал.
  * спасён (CSAR) - экипаж снова в полку (crews + 1).
Задача csar доктрины ставит вылет за своим экипажем не на своей территории; вылет ИИ вне миссии - итог по угрозам.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from . import model

PILOT_FIGURE = {"red": "Infantry_AK", "blue": "Soldier_M4"}   # пилот на земле в миссии (пехотинец стороны)
ADF_KHZ = (200, 1200)        # маяк сбитого - в диапазоне АРК / ADF (Ми-8 АРК-9: 150-1300, UH-1H: 190-1750 кГц)


def crew_size(type_name: str) -> int:
    return int(model.aircraft_info(type_name).get("crew") or 1)


def owner_at(state: dict, pos: dict) -> str | None:
    """Чья территория в точке: владелец ближайшего пункта."""
    p = min(state["places"].values(), key=lambda q: model.dist_km(pos, q))
    return p.get("side")


def _freq(state: dict) -> int:
    """Частота маяка, кГц: свободная в ADF_KHZ шагом 10, по порядку."""
    used = {d["freq_khz"] for d in state.get("downed", [])}
    for f in range(ADF_KHZ[0], ADF_KHZ[1], 10):
        if f not in used:
            return f
    return ADF_KHZ[0]


def add_downed(state: dict, unit: dict, aircraft: str, pos: dict, note: str = "") -> dict:
    """Экипаж сбитого самолёта на земле (катапультировался, в миссии не подобран). Экипаж выбывает из части до возврата."""
    state.setdefault("downed", [])
    state["_downed_seq"] = state.get("_downed_seq", 0) + 1
    d = {"id": f"downed_{state['_downed_seq']}", "side": unit["side"], "unit": unit["id"], "type": unit.get("type", ""),
         "aircraft": aircraft, "crew": crew_size(unit.get("type", "")), "pos": {"lat": pos["lat"], "lon": pos["lon"]},
         "day": state["day"], "freq_khz": _freq(state)}
    from . import pilots
    p = pilots.take(unit, aircraft) if model.category(unit) in ("air", "heli") else None
    if p:
        d["pilot"] = p
    state["downed"].append(d)
    if "crews" in unit:
        unit["crews"] = max(0, unit["crews"] - 1)
    return d


def returned(state: dict, d: dict, how: str) -> str:
    """Экипаж вернулся в полк (спасён или вышел к своим)."""
    from . import pilots
    u = state["units"].get(d["unit"])
    if u and "crews" in u:
        u["crews"] = min(u.get("crews0", u["crews"] + 1), u["crews"] + 1)
    if u:
        pilots.back(u, d.get("pilot"))
    state["downed"] = [x for x in state["downed"] if x["id"] != d["id"]]
    who = pilots.title(u, d["pilot"]) + ", " if u and d.get("pilot") else ""
    return f"Экипаж {d['type']} ({who}{u['name'] if u else d['unit']}): {how}, вернулся в часть."


def lost(state: dict, d: dict, how: str) -> str:
    from . import pilots
    state["downed"] = [x for x in state["downed"] if x["id"] != d["id"]]
    u = state["units"].get(d["unit"])
    if u:
        pilots.killed(u, d.get("pilot"), how, state["day"])
    who = pilots.title(u, d["pilot"]) + ", " if u and d.get("pilot") else ""
    return f"Экипаж {d['type']} ({who}{u['name'] if u else d['unit']}): {how}."


def title(state: dict, d: dict) -> str:
    u = state["units"].get(d["unit"])
    return f"экипаж {d['type']} ({u['name'] if u else d['unit']})"


def resolve(state: dict, until_s: float | None = None) -> list[str]:
    """Итог вылетов CSAR плана полётов со временем на цели не позже until_s (свой - по дебрифу, ИИ - по угрозам)."""
    lines = []
    a = state.get("ato") or {}
    done = set(a.get("done", []))
    for e in a.get("entries", []):
        if e["kind"] != "csar" or e.get("resolved") or (until_s is not None and e["tot_s"] > until_s):
            continue
        g = e["task"]["package"][0]
        d = next((x for x in state.get("downed", []) if x["id"] == g["objective"]["downed"]), None)
        e["resolved"] = True
        if d is None or e["id"] in done:         # уже спасён / вылет игрока - итог в дебрифе
            continue
        tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        if (a.get("lost") or {}).get(e["id"]):
            continue                             # вертолёт сбит в миссии - экипаж не подобран
        p = max(0.1, min(0.9, tdef.get("ai_success", 0.7) - tdef.get("ai_loss_per_threat", 0.15) * len(e["task"].get("threats", []))))
        r = model.rng(state, f"csar-{e['id']}")
        if (r.random() < p) if r else p >= 0.5:
            lines.append(returned(state, d, f"спасён ({e['title']})"))
    return lines


def daily(state: dict) -> list[str]:
    """Конец суток - судьба экипажей на земле: на своей территории - вышли к своим, на чужой - плен с вероятностью
    capture_per_day, старше downed_max_days - пропали."""
    lines = []
    for d in list(state.get("downed", [])):
        sim = model.doctrine(state, d["side"])["sim"]
        side_here = owner_at(state, d["pos"])
        if side_here == d["side"]:
            lines.append(returned(state, d, "вышел к своим"))
            continue
        age = state["day"] - d["day"]
        r = model.rng(state, f"capture-{d['id']}-{state['day']}")
        p = sim.get("capture_per_day", 0.35)
        if (r.random() < p) if r else age >= 1:
            lines.append(lost(state, d, "в плену"))
        elif age + 1 >= sim.get("downed_max_days", 3):
            lines.append(lost(state, d, "пропал без вести"))
    return lines


def apply_debrief(state: dict, man: dict, data: dict, lost_names: set) -> list[str]:
    """Дебриф: экипажи сбитых в миссии самолётов (по журналу звеньев манифеста) и спасения в миссии (lua/csar.lua).
    Катапультировался и не подобран - на земле (downed), подобран и доставлен - в части, без катапультирования
    или погиб в сбитом вертолёте-спасателе - погиб."""
    from dcs.mapping import Point
    from dcs.terrain.germany import Germany
    lines = []
    ej = set(data.get("ejected", []))
    pos = data.get("ejectpos") or {}
    cs = data.get("csar") or {}
    rescued, killed = set(cs.get("rescued", [])), set(cs.get("lost", []))
    terrain = None
    for fl in man.get("flights") or []:
        perf = state["units"].get(fl["performer"])
        if not perf:
            continue
        for n in fl["units"]:
            if n not in lost_names:
                continue
            key = "ej:" + n
            if n in ej and key in rescued:
                lines.append(f"{perf['name']}: экипаж сбитого {perf['type']} спасён в миссии.")
            elif n in ej and n in pos and key not in killed:
                terrain = terrain or Germany()
                ll = Point(pos[n][0], pos[n][1], terrain).latlng()
                d = add_downed(state, perf, n, {"lat": ll.lat, "lon": ll.lng})
                lines.append(f"{perf['name']}: экипаж сбитого {perf['type']} катапультировался, на земле "
                             f"({'своя' if owner_at(state, d['pos']) == d['side'] else 'чужая'} территория), маяк {d['freq_khz']} кГц.")
            elif "crews" in perf:
                from . import pilots
                p = pilots.take(perf, n)
                pilots.killed(perf, p, "погиб", state["day"])
                perf["crews"] = max(0, perf["crews"] - 1)
                lines.append(f"{perf['name']}: экипаж сбитого {perf['type']} погиб"
                             + (f" ({pilots.title(perf, p)})" if p else "") + f"; экипажей {perf['crews']}.")
    for d in list(state.get("downed", [])):      # экипажи, спасённые из прошлых вылетов
        if d["id"] in rescued:
            lines.append(returned(state, d, "спасён в миссии"))
        elif d["id"] in killed:
            lines.append(lost(state, d, "погиб в сбитом вертолёте-спасателе"))
    return lines


def beacon_wav(path: Path) -> Path:
    """Звук маяка (lua/csar.lua, trigger.action.radioTransmission): 2 с - четыре сигнала 1020 Гц, 8 кГц моно 16 бит."""
    rate = 8000
    frames = bytearray()
    for i in range(rate * 2):
        t = i / rate
        on = (t % 0.5) < 0.25
        v = int(12000 * math.sin(2 * math.pi * 1020 * t)) if on else 0
        frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path

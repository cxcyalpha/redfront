"""Исторические подвески по задачам (конец 80-х - 1991) -> redfront/data/payloads_custom.json, поверх DCS Retribution.

Источник - таблицы подвесок dstorm.eu (Desert Storm, обн. 10.12.2023): не точная копия одного вылета, а типичная
подвеска для задачи; оружия и контейнеров, которых нет в DCS (AN/ASQ-173, AN/AAR-50, Mk-77, VER), - ближайшее в DCS
(VER -> BRU-33, TER -> TER-9/A) или бак. Подвеска действует до UNTIL (позже - подвески Retribution: JDAM, AMRAAM...).
Пилон - начало имени оружия в pydcs для этого пилона (без CLSID в коде). Запуск: python tools/hist_payloads.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dcs.planes as P  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "redfront" / "data" / "payloads_custom.json"
UNTIL = 1997
SRC = "dstorm.eu (Desert Storm loadouts, обн. 10.12.2023)"

# имена оружия pydcs (начало имени)
A9, A7, TANK = "AIM-9M Sidewinder", "AIM-7M Sparrow", "Fuel tank 370"
H = {   # F/A-18C: станции 1-9 (1, 9 - концы крыла; 4, 6 - борта фюзеляжа; 5 - под фюзеляжем)
    "cls": "FA_18C_hornet", "page": "f-18",
    "loads": {
        "Retribution Strike": ["AIM-9M", "BRU-33 with 2 x Mk-83 -", "FPU-8A", "AIM-7M", "Mk-83 -", "AIM-7M", "FPU-8A", "BRU-33 with 2 x Mk-83 -", "AIM-9M"],
        "Retribution OCA/Runway": ["AIM-9M", "Mk-84 -", "Mk-84 -", "AIM-7M", "FPU-8A", "AIM-7M", "Mk-84 -", "Mk-84 -", "AIM-9M"],
        "Retribution BAI": ["AIM-9M", "BRU-33 with 2 x Mk-82 -", "FPU-8A", "AIM-7M", "Mk-82 -", "AIM-7M", "FPU-8A", "BRU-33 with 2 x Mk-82 -", "AIM-9M"],
        "Retribution CAS": ["AIM-9M", "BRU-33 with 2 x Mk-20", "FPU-8A", "AIM-7M", "Mk-20", "AIM-7M", "FPU-8A", "BRU-33 with 2 x Mk-20", "AIM-9M"],
        "Retribution SEAD": ["AIM-9M", "AGM-88C", "FPU-8A", "AIM-7M", "FPU-8A", "AIM-7M", "FPU-8A", "AGM-88C", "AIM-9M"],
        "Retribution DEAD": ["AIM-9M", "AGM-88C", "Mk-84 -", "AIM-7M", "FPU-8A", "AIM-7M", "Mk-84 -", "AGM-88C", "AIM-9M"],
        "Retribution BARCAP": ["AIM-9M", "LAU-115C - AIM-7M", "FPU-8A", "AIM-7M", "FPU-8A", "AIM-7M", "FPU-8A", "LAU-115C - AIM-7M", "AIM-9M"],
        "Retribution Escort": ["AIM-9M", "LAU-115C - AIM-7M", "FPU-8A", "AIM-7M", "FPU-8A", "AIM-7M", "FPU-8A", "LAU-115C - AIM-7M", "AIM-9M"],
        # противокорабельной у dstorm нет: 4 Harpoon (как Retribution), ракеты - по эпохе (ОЦЕНКА)
        "Retribution Anti-ship": ["AIM-9M", "AGM-84D", "AGM-84D", "AIM-7M", "FPU-8A", "AIM-7M", "AGM-84D", "AGM-84D", "AIM-9M"],
    }}
F16C = {   # F-16C: 1, 9 - концы; 2, 8 - внешние; 3, 7 - средние; 4, 6 - внутренние (баки); 5 - центр (контейнер РЭБ)
    "cls": "F_16C_50", "page": "f-16",
    "loads": {
        "Retribution Strike": [A9, A9, "Mk-84 -", TANK, "ALQ-131", TANK, "Mk-84 -", A9, A9],
        "Retribution OCA/Runway": [A9, None, "Mk-84 -", "Mk-84 -", "ALQ-131", "Mk-84 -", "Mk-84 -", None, A9],
        "Retribution BAI": [A9, None, "TER-9/A - 3 x Mk-82 -", TANK, "ALQ-131", TANK, "TER-9/A - 3 x Mk-82 -", None, A9],
        "Retribution CAS": [A9, A9, "CBU-87", TANK, "ALQ-131", TANK, "CBU-87", A9, A9],
        "Retribution SEAD": [A9, A9, "AGM-88C", TANK, "ALQ-131", TANK, "AGM-88C", A9, A9],
        "Retribution DEAD": [A9, None, "AGM-88C", TANK, "ALQ-131", TANK, "Mk-84 -", None, A9],
        "Retribution BARCAP": [A9, A9, None, TANK, "ALQ-131", TANK, None, A9, A9],
        "Retribution Escort": [A9, A9, None, TANK, "ALQ-131", TANK, None, A9, A9],
    }}
F16A = {   # F-16A (ИИ): 1, 2, 9, 10 - ракеты; 3, 8 - средние; 4, 7 - баки; 6 - центр
    "cls": "F_16A", "page": "f-16",
    "pylons": [1, 2, 3, 4, 6, 7, 8, 9, 10],
    "loads": {
        "Retribution Strike": [A9, A9, "Mk-84 -", TANK, "ALQ-131", TANK, "Mk-84 -", A9, A9],
        "Retribution BAI": [A9, None, "BRU-42 - 3 x Mk-82 -", TANK, "ALQ-131", TANK, "BRU-42 - 3 x Mk-82 -", None, A9],
        "Retribution CAS": [A9, None, "MER2 with 2 x Mk-20", TANK, "ALQ-131", TANK, "MER2 with 2 x Mk-20", None, A9],
        "Retribution BARCAP": [A9, A9, None, TANK, "ALQ-131", TANK, None, A9, A9],
        "Retribution Escort": [A9, A9, None, TANK, "ALQ-131", TANK, None, A9, A9],
    }}
CAP15 = [A9, "Fuel tank 610", A9, A7, A7, "Fuel tank 610", A7, A7, A9, "Fuel tank 610", A9]
F15C = {"cls": "F_15C", "page": "f-15c",   # 4 AIM-9M, 4 AIM-7M, три бака
        "loads": {"Retribution BARCAP": CAP15, "Retribution Escort": CAP15, "Retribution Fighter Sweep": CAP15}}
# F-14A (Heatblur): 1, 10 - AIM-9; 2, 9 - под крылом; 3, 8 - баки; 4, 7 - передние под фюзеляжем, 5, 6 - задние
T_CAP = ["LAU-7 AIM-9M", "AIM-7M", "Fuel tank 300 gal", "AIM-54C-Mk47", "AIM-7M", None, "AIM-54C-Mk47", "Fuel tank 300 gal", "AIM-7M", "LAU-7 AIM-9M"]
T_ESC = ["LAU-7 AIM-9M", "LAU-7 AIM-9M", "Fuel tank 300 gal", "AIM-7M", "AIM-7M", "AIM-7M", "AIM-7M", "Fuel tank 300 gal", "LAU-7 AIM-9M", "LAU-7 AIM-9M"]
F14 = [{"cls": c, "page": "f-14",
        "loads": {"Retribution BARCAP": T_CAP, "Retribution Escort": T_ESC, "Retribution Fighter Sweep": T_ESC}}
       for c in ("F_14A_135_GR", "F_14A_135_GR_Early")]
# F-4E (ИИ DCS): 1, 9 - внешние (баки); 2, 8 - внутренние; 3, 4, 6, 7 - ниши AIM-7 (3 - контейнер РЭБ); 5 - центр (бак)
F4_ROW = lambda w: ["F-4 Fuel tank-W", w, "ALQ-131", "AIM-7M", "F-4 Fuel tank-C", "AIM-7M", "AIM-7M", w, "F-4 Fuel tank-W"]
F4E = {"cls": "F_4E", "page": "f-4",
       "loads": {"Retribution CAS": F4_ROW("BRU-42 - 3 x Mk-20"), "Retribution BAI": F4_ROW("BRU-42 - 3 x Mk-82"),
                 "Retribution Strike": F4_ROW("GBU-10"), "Retribution SEAD": F4_ROW("LAU-118A - AGM-45B"),
                 "Retribution BARCAP": ["F-4 Fuel tank-W", "LAU-7 - 2 x AIM-9M", "AIM-7M", "AIM-7M", "F-4 Fuel tank-C",
                                        "AIM-7M", "AIM-7M", "LAU-7 - 2 x AIM-9M", "F-4 Fuel tank-W"]}}
F4E["loads"]["Retribution Escort"] = F4E["loads"]["Retribution BARCAP"]
# F-4E (Heatblur): 1, 13 - внешние; 3, 11 - внутренние (2, 4, 10, 12 - направляющие AIM-9 на них); 5, 6, 8, 9 - ниши
# AIM-7 (6 - контейнер РЭБ); 7 - центр
HB = lambda w, a9=None: ["Fuel", a9, w, a9, None, "ALQ-131", "Fuel", "AIM-7M", "AIM-7M", a9, w, a9, "Fuel"]
F4HB = {"cls": "F_4E_45MC", "page": "f-4",
        "loads": {"Retribution CAS": HB("2x CBU-87", "AIM-9M"), "Retribution BAI": HB("2x AGM-65D", "AIM-9M"),
                  "Retribution Strike": HB("2x Mk-83 - 1000lb GP Bomb LD (TER)", "AIM-9M"),
                  "Retribution BARCAP": ["Fuel", "AIM-9M", None, "AIM-9M", "AIM-7M", "AIM-7M", "Fuel", "AIM-7M", "AIM-7M",
                                         "AIM-9M", None, "AIM-9M", "Fuel"]}}
F4HB["loads"]["Retribution Escort"] = F4HB["loads"]["Retribution BARCAP"]
# A-10A: 1 - 2 x AIM-9M, 11 - контейнер РЭБ, 3, 9 - Maverick, 4-8 - бомбы (6 - пусто), 2, 10 - пусто
A10 = lambda w3, w4, w5: ["LAU-105 - 2 x AIM-9M", None, w3, w4, w5, None, w5, w4, w3, None, "ALQ-131"]
A10A = {"cls": "A_10A", "page": "a-10",
        "loads": {"Retribution CAS": A10("LAU-117 - AGM-65D", "Mk-20", "Mk-20"),
                  "Retribution BAI": A10("LAU-88 - 2 x AGM-65D", "BRU-42 - 3 x Mk-82 -", None),
                  "Retribution Strike": A10("LAU-117 - AGM-65D", "BRU-42 - 3 x Mk-82 -", "Mk-82 -")}}
# AV-8B: 1, 8 - внешние (AIM-9M), 2, 3, 6, 7 - бомбы, 4 - пушка GAU-12, 5 - ALQ-164
AV = lambda w, a1=None: [a1, w, w, "GAU 12 Gunpod w/HE", "AN/ALQ-164", w, w, "AIM-9M"]
AV8 = {"cls": "AV8BNA", "page": "av-8b",
       "loads": {"Retribution CAS": AV("Mk-20"), "Retribution BAI": AV("Mk-82 Snakeye", "AIM-9M"),
                 "Retribution Strike": AV("Mk-83 - 1000lb", "AIM-9M")}}
SPECS = [H, F16C, F16A, F15C, *F14, F4E, F4HB, A10A, AV8]
# A-6E (описание из DCS Retribution, redfront.mods.a6e): 1, 5 - внешние; 2, 4 - внутренние; 3 - центр (бак почти всегда).
# Заменяет подвески по задачам из A6E.lua (там - максимальная загрузка: 28 Mk-82 без бака, 28 Rockeye и в CAS, и в BAI).
# Противокорабельная (2 Harpoon, ALQ-167, AIM-9M, бак) - остаётся как была: она реалистична.
try:
    from redfront.mods import a6e as _a6e
    T6 = "=AERO 1D 300 Gallons Fuel Tank"
    MER82, MER20 = "=6x Mk-82 - 500lb GP Bomb LD (MER)", "=6x Mk-20 Rockeye - 490lbs CBU, 247 x HEAT Bomblets (MER)"
    TER82 = "=3x Mk-82 Snakeye - 500lb GP Bomb HD (TER)"
    A6 = {"cls_obj": _a6e.A6E, "page": "a-6e",
          "loads": {"STRIKE": ["=Mk-83 - 1000lb GP Bomb LD"] * 2 + [T6] + ["=Mk-83 - 1000lb GP Bomb LD"] * 2,
                    "BAI": [MER82, None, T6, None, MER82],
                    "CAS": [MER20, "=GBU-12 - 500lb Laser Guided Bomb", T6, "=GBU-12 - 500lb Laser Guided Bomb", MER20],
                    "DEAD": [TER82, "AGM-88C", T6, "AGM-88C", TER82],
                    "SEAD": [TER82, "AGM-88C", T6, "AGM-88C", TER82],
                    "OCA/Runway": ["=Mk-84 - 2000lb GP Bomb LD"] * 2 + [T6] + ["=Mk-84 - 2000lb GP Bomb LD"] * 2}}
    SPECS.append(A6)
except ImportError:
    pass


def clsid(cls, n: int, prefix: str) -> str:
    py = getattr(cls, f"Pylon{n}")
    ws = [v[1] for v in vars(py).values() if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict)]
    tests = ([lambda nm: nm.strip() == prefix[1:].strip()] if prefix.startswith("=") else
             [lambda nm: nm.startswith(prefix), lambda nm: prefix in nm])    # "=имя" - точно; иначе начало, часть
    for test in tests:   # начало имени, затем - часть имени
        for w in ws:
            if test(w.get("name", "")):
                return w["clsid"]
    raise SystemExit(f"{cls.id} пилон {n}: нет оружия '{prefix}'")


def main() -> None:
    d = json.loads(OUT.read_text(encoding="utf-8"))
    ret = json.loads((OUT.parent / "payloads.json").read_text(encoding="utf-8"))["types"]
    for sp in SPECS:
        cls = sp.get("cls_obj") or getattr(P, sp["cls"])
        t = d["types"].setdefault(cls.id, {})
        nums = sp.get("pylons") or list(range(1, 20))
        for name, row in sp["loads"].items():
            tasks = (ret.get(cls.id, {}).get(name) or next(iter(ret.get(cls.id, {}).values()), {})).get("tasks", [])
            pyl = {str(nums[i]): {"CLSID": clsid(cls, nums[i], w)} for i, w in enumerate(row) if w}
            t[name] = {"tasks": tasks, "pylons": pyl, "until": UNTIL,
                       "note": f"{SRC}, https://www.dstorm.eu/pages/loadout/{sp['page']}.html: типичная подвеска для "
                               f"задачи (не копия одного вылета); нет в DCS - ближайшее или бак"}
        print(cls.id, len(sp["loads"]))
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

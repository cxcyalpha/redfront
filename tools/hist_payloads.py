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
SPECS = [H, F16C, F16A, F15C, *F14]


def clsid(cls, n: int, prefix: str) -> str:
    py = getattr(cls, f"Pylon{n}")
    for v in vars(py).values():
        if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict) and v[1].get("name", "").startswith(prefix):
            return v[1]["clsid"]
    raise SystemExit(f"{cls.id} пилон {n}: нет оружия '{prefix}'")


def main() -> None:
    d = json.loads(OUT.read_text(encoding="utf-8"))
    ret = json.loads((OUT.parent / "payloads.json").read_text(encoding="utf-8"))["types"]
    for sp in SPECS:
        cls = getattr(P, sp["cls"])
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

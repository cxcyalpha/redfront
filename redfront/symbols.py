"""Условные знаки для карты окна: род войск, звено и короткая подпись части.

Стиль карты - по стороне игрока: за красных - советская рабочая карта (свои красным, противник синим, подписи
сокращениями "94 гв. мсд", "1 тбр"), за синих - APP-6 НАТО (рамки, знак рода войск, звено над рамкой). Что рисовать -
решает страница (gui.html); здесь только классификация части по составу и названию.
"""
from __future__ import annotations

import re

TANKS = ("T_", "Leopard", "M_1_Abrams", "Chieftain", "Challenger", "M-60", "M60")
IFV = ("BMP", "Marder", "M_2_Bradley", "MCV_80", "Warrior")
APC = ("BTR", "M_113", "TPZ", "MTLB")
INFANTRY = ("Paratrooper", "Soldier", "Infantry")

# звено: подстроки названия -> (звено НАТО, советское окончание сокращения)
ECHELONS = [("дивизи", "XX"), ("бригад", "X"), ("полк", "III"), ("батальон", "II"), ("bataillon", "II"), ("рота", "I")]

# род войск и звено -> советское сокращение (свои и противник - одинаково, как на карте штаба)
SU_ABBR = {
    ("tank", "XX"): "тд", ("mech", "XX"): "мсд", ("inf", "XX"): "пд", ("airassault", "XX"): "вдд",
    ("tank", "X"): "тбр", ("mech", "X"): "мбр", ("inf", "X"): "пбр", ("airassault", "X"): "одшбр",
    ("tank", "III"): "тп", ("mech", "III"): "мсп", ("inf", "III"): "пп", ("airassault", "III"): "дшп",
    ("tank", "II"): "тб", ("mech", "II"): "мсб", ("inf", "II"): "пб", ("airassault", "II"): "пдб",
    ("tank", "I"): "тр", ("mech", "I"): "мср", ("inf", "I"): "пр", ("airassault", "I"): "дшр",
}


def _kind(t: str) -> str:
    if t.startswith(TANKS):
        return "tank"
    if t.startswith(IFV):
        return "ifv"
    if t.startswith(APC):
        return "apc"
    if t.startswith(INFANTRY):
        return "inf"
    return "other"


def branch(unit: dict) -> str:
    """Род войск части: tank (танки - большинство или почти половина брони), mech (мотострелки, механизированные),
    inf (пехота без брони), airassault (десант), sam, gci."""
    role = unit.get("role", "")
    if role.startswith("sam"):
        return "sam"
    if role == "gci":
        return "gci"
    if role == "air_assault":
        return "airassault"
    n = {"tank": 0, "ifv": 0, "apc": 0, "inf": 0, "other": 0}
    for c in unit.get("composition", []):
        n[_kind(c["type"])] += c["count"]
    armour = n["tank"] + n["ifv"] + n["apc"]
    name = unit.get("name", "").lower()
    head = r"(\d+-[яй]\s+(гв\.\s+)?)?"
    if re.match(head + r"(танков|бронетанков|панцербригад|учебная панцербригад)", name):
        return "tank"                            # род войск в названии части - главнее состава
    if re.match(head + r"(мотострелк|механизир|пехотн|панцергренадер|бронекавалер|кавалер)", name):
        return "mech"
    if armour == 0:
        return "inf"
    if n["tank"] >= 0.55 * armour:
        return "tank"
    return "mech"


def vehicle(unit: dict) -> str:
    """Знак техники части на советской карте: tank (ромб), bmp ("пуля" с чертой), btr ("пуля"), heli (десант),
    foot (пешие)."""
    b = branch(unit)
    if b == "tank":
        return "tank"
    if b == "airassault":
        return "heli"
    n = {"tank": 0, "ifv": 0, "apc": 0, "inf": 0, "other": 0}
    for c in unit.get("composition", []):
        n[_kind(c["type"])] += c["count"]
    if n["ifv"] + n["apc"] == 0:
        return "foot"
    return "bmp" if n["ifv"] >= n["apc"] else "btr"


def sam_tier(unit: dict) -> int:
    """Дальность ЗРК для знака пусковой: 1 - ближнего действия, 2 - малой дальности, 3 - средней и большой."""
    return {"sam_short": 1, "sam_medium": 2, "sam_long": 3}.get(unit.get("role", ""), 1)


def echelon(unit: dict) -> str:
    """Звено - по первому в названии слову звена ('1-я бригада 1-й бронетанковой дивизии' - бригада)."""
    name = unit.get("name", "").split(" (")[0].lower()
    found = [(name.find(key), e) for key, e in ECHELONS if key in name]
    if found:
        return min(found)[1]
    if unit.get("role") == "air_assault":
        return "I"
    return "II" if sum(c["count"] for c in unit.get("composition", [])) < 80 else "X"


def number(unit: dict) -> str:
    """Номер части из названия: '94-я гв. ...' -> '94 гв.', 'Панцербригада 1' -> '1', '2./Fallschirmjäger... 271' -> '2/271'."""
    name = unit.get("name", "").split(" (")[0]
    m = re.match(r"(\d+)\./\D*(\d+)", name)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"(\d+)-[яйе]\s*(гв\.)?", name)
    if m:
        return m.group(1) + (" гв." if m.group(2) else "")
    m = re.search(r"(\d+)\s*$", name)
    return m.group(1) if m else ""


def abbr(unit: dict) -> str:
    """Подпись по-советски: номер + сокращение рода войск и звена ('94 гв. мсд'); ННА, США - пометкой."""
    b, e = branch(unit), echelon(unit)
    if b in ("sam", "gci"):
        return unit.get("name", "")
    name = unit.get("name", "")
    low = name.lower()
    short = ("бкп" if "бронекавалер" in low else "кд" if "кавалерийская дивизия" in low else SU_ABBR.get((b, e), ""))
    if unit.get("side") == "blue" and b == "mech":   # мотопехота НАТО - как на советских картах: мпд, мпбр, мпб
        short = {"мсд": "мпд", "мбр": "мпбр", "мсп": "мпп", "мсб": "мпб", "мср": "мпр"}.get(short, short)
    dn = re.search(r"(\d+)-[йя] (бронетанковой|пехотной) дивизии", low)
    if dn and e == "X":                          # бригада дивизии: '1 тбр 1 тд'
        short += f" {dn.group(1)} {'тд' if dn.group(2) == 'бронетанковой' else 'мпд'}"
    note = " ННА" if "ННА" in name else " США" if "США" in name else ""
    return " ".join(x for x in (number(unit), short) if x) + note or name

"""Подвески по году кампании: оружие, которого ещё нет на вооружении, - замена своим по эпохе или снятие.

Год принятия на вооружение - ОЦЕНКИ по открытым справочным данным (первое серийное применение / поступление в части;
для экспорта и союзников бывает позже). Таблица YEARS - образец имени оружия pydcs (регулярное выражение) -> год;
первое совпадение. Оружие без строки - без ограничения (старое и общеупотребимое: Mk-82, ФАБ, НАР С-5...).

Замена (FALLBACK): семейство -> по порядку более старые образцы; из оружия, допустимого на этот пилон этого типа
(pydcs), берётся первое подходящее по году и ближайшее по имени (тот же держатель, то же число); нет - пилон пуст.
"""
from __future__ import annotations

import difflib
import re

YEARS = [   # (образец имени, год) - ОЦЕНКИ
    # воздух-воздух
    (r"AIM-120C", 1996), (r"AIM-120", 1991), (r"AIM-9X", 2003), (r"AIM-9M", 1982), (r"AIM-9L", 1978),
    (r"AIM-9P", 1978), (r"AIM-7MH", 1987), (r"AIM-7M", 1982), (r"AIM-7F", 1976), (r"AIM-54C", 1986),
    (r"R-77", 1994), (r"R-73", 1983), (r"R-27E[RT]", 1987), (r"R-27[RT]", 1984), (r"R-60M", 1982),
    (r"Python-?4|Python 4", 1993), (r"Magic ?(II|2)", 1986), (r"Super ?530D", 1987), (r"MICA", 1996),
    (r"IRIS-T", 2005), (r"ASRAAM", 2002), (r"Meteor", 2016), (r"Derby", 1995), (r"PL-12", 2005),
    # управляемое воздух-поверхность
    (r"AGM-65[LKH]", 1997), (r"AGM-65G", 1989), (r"AGM-65[EF]", 1985), (r"AGM-65D", 1983), (r"AGM-65B", 1975),
    (r"AGM-88", 1985),     # в DCS только AGM-88C - изображает HARM A/B (1985): допущение, иначе SEAD США до 1993 без ПРР
    (r"AGM-122", 1986), (r"AGM-154", 1999), (r"AGM-84[EHK]", 1990),
    (r"AGM-84", 1977), (r"AGM-114", 1985), (r"AGM-119", 1986), (r"AGM-130", 1994), (r"AGM-62", 1967),
    (r"Kh-31", 1990), (r"Kh-29", 1980), (r"Kh-25MPU", 1993), (r"Kh-25MP", 1981), (r"Kh-25ML", 1975),
    (r"Kh-58", 1978), (r"Kh-59M", 1990), (r"Kh-59", 1980), (r"Kh-35", 2003), (r"Kh-38", 2012),
    (r"Kh-41", 1995), (r"9M127|Vikhr", 1992), (r"9M120|Ataka", 1996), (r"9M114|Shturm", 1976),
    (r"ALARM", 1990), (r"Sea Eagle", 1985), (r"Kormoran ?2", 1991), (r"Storm Shadow|SCALP", 2002),
    (r"Brimstone", 2005), (r"Taurus", 2005), (r"AS-?30L", 1988), (r"Hellfire", 1985),
    # бомбы
    (r"GBU-3[1289]|JDAM", 1997), (r"GBU-5[0-9]|LJDAM", 2008), (r"GBU-39", 2006), (r"GBU-2[47]", 1985),
    (r"GBU-15", 1983), (r"GBU-1[0-6]", 1976), (r"CBU-9[7-9]|CBU-10[3-5]", 1997), (r"CBU-8[79]", 1986),
    (r"KAB-500S", 2010), (r"KAB-1500L", 1984), (r"KAB-500Kr|KAB-1500Kr", 1984), (r"KAB-500L", 1975),
    (r"BetAB-500ShP", 1983), (r"RBK-500U", 1990), (r"BLU-107|Durandal", 1983),
    # ракеты
    (r"APKWS", 2012), (r"S-8", 1984), (r"S-13", 1973),
    # контейнеры
    (r"LITENING|AAQ-28", 1999), (r"Sniper|AAQ-33", 2005), (r"ATFLIR|ASQ-228", 2003), (r"LANTIRN|AAQ-1[34]", 1987),
    (r"Pave ?Spike", 1974), (r"ALQ-184", 1989), (r"ALQ-131", 1976), (r"ALQ-119", 1970), (r"Damocles", 2007),
    (r"TGM-65|CATM", 0),
]
FALLBACK = {   # семейство (образец) -> замены по порядку (образцы); год проверяется по YEARS
    r"AIM-120": [r"AIM-7M\b", r"AIM-7F", r"AIM-7E", r"AIM-9M", r"AIM-9L", r"AIM-9P"],   # F-16A/C 80-х - только AIM-9
    r"AIM-9X|AIM-9M": [r"AIM-9M", r"AIM-9L", r"AIM-9P", r"AIM-9J", r"AIM-9E"],
    r"AIM-9L": [r"AIM-9P", r"AIM-9J", r"AIM-9E"],
    r"AIM-7M": [r"AIM-7F", r"AIM-7E"],
    r"R-77": [r"R-27ER", r"R-27R"],
    r"R-27E": [r"R-27R", r"R-27T"],
    r"R-27[RT]": [r"R-24", r"R-23"],
    r"R-73": [r"R-60M", r"R-60\b"],
    r"AGM-65": [r"AGM-65G", r"AGM-65D", r"AGM-65B", r"AGM-65A"],
    r"AGM-88": [r"AGM-88", r"AGM-45B", r"AGM-45A"],
    r"GBU-31|GBU-24|GBU-27": [r"GBU-24", r"GBU-10", r"Mk-84"],
    r"GBU-32": [r"GBU-16", r"Mk-83"],
    r"GBU-38|GBU-5[0-9]|GBU-39": [r"GBU-12", r"Mk-82\b"],
    r"CBU-9[7-9]|CBU-10[3-5]": [r"CBU-87", r"Mk-20"],
    r"CBU-8[79]": [r"Mk-20", r"CBU-52"],
    r"Kh-31P|Kh-25MPU": [r"Kh-58", r"Kh-25MP\b", r"Kh-28"],
    r"Kh-29|Kh-38|Kh-59": [r"Kh-29", r"Kh-25ML", r"Kh-23"],
    r"KAB-500S": [r"KAB-500Kr", r"KAB-500L"],
    r"9M127|Vikhr": [r"S-8KOM", r"S-5"],
    r"S-8": [r"S-5", r"S-24"],
    r"APKWS": [r"M151", r"Hydra", r"FFAR"],
    r"ALARM": [r"Shrike|AGM-45"],
    r"Brimstone": [r"BL-755", r"Mk-20"],
    r"LITENING|Sniper|ATFLIR|AAQ-28": [r"LANTIRN|AAQ-14", r"Pave ?Spike"],
    r"ALQ-184": [r"ALQ-131", r"ALQ-119"],
}


def campaign_year(state: dict | None) -> int | None:
    try:
        return int(str((state or {}).get("date") or "")[:4])
    except ValueError:
        return None


def year_of(name: str) -> int:
    for pat, y in YEARS:
        if re.search(pat, name, re.I):
            return y
    return 0


_BY_CLSID: dict | None = None


def by_clsid() -> dict:
    global _BY_CLSID
    if _BY_CLSID is None:
        import dcs.weapons_data as W
        _BY_CLSID = {v["clsid"]: v for v in vars(W.Weapons).values() if isinstance(v, dict) and "clsid" in v}
    return _BY_CLSID


def name_of(clsid: str) -> str:
    w = by_clsid().get(clsid)
    return w["name"] if w else ""


def _pylon_options(ac, num: int) -> list[dict]:
    p = getattr(ac, f"Pylon{num}", None)
    if p is None:
        return []
    return [v[1] for v in vars(p).values() if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict)]


def substitute(ac, num: int, name: str, year: int) -> dict | None:
    """Замена оружия name на пилоне num типа ac на год year: по FALLBACK - первое семейство, у которого есть
    допустимое по году оружие этого пилона, ближайшее по имени; None - замены нет."""
    opts = [w for w in _pylon_options(ac, num) if year_of(w["name"]) <= year]
    for fam, subs in FALLBACK.items():
        if not re.search(fam, name, re.I):
            continue
        for sub in subs:
            cands = [w for w in opts if re.search(sub, w["name"], re.I)]
            if cands:
                return max(cands, key=lambda w: difflib.SequenceMatcher(None, w["name"], name).ratio())
    return None


def degrade(fg, year: int | None) -> list[str]:
    """Подвеска группы - по году кампании: новее - замена или снятие. Возвращает строки 'было -> стало'."""
    if not year:
        return []
    notes = []
    for u in fg.units:
        ac = u.unit_type
        for num, d in list(u.pylons.items()):
            name = name_of(d.get("CLSID", ""))
            if not name or year_of(name) <= year:
                continue
            w = substitute(ac, int(num), name, year)
            if w:
                u.pylons[num] = {"CLSID": w["clsid"]}
                note = f"{name} -> {w['name']}"
            else:
                del u.pylons[num]
                note = f"{name} -> снято"
            if note not in notes:
                notes.append(note)
    if notes:
        fg.__dict__.setdefault("_rf_degraded", []).extend(notes)
    return notes

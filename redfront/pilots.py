"""Лётчики авиачастей: список по полку (u['pilots']), имена - в миссию (имя ЛА в DCS = звание и фамилия лётчика).

Число лётчиков = экипажей части (crews, csar.py), без них - самолётов. Новые экипажи (пополнение) - новые имена;
сбитый лётчик на земле (csar: downed) - вне списка до возвращения, погибший или пленный - выбывает
(u['pilots_lost'] - память полка). Вылеты (sorties) - по слетанным миссиям (debrief) и вылетам плана полётов ИИ.
Национальность - по составу сил (u['nation'], иначе по названию части: ННА, RAF, США, ФРГ...). Имена - вымышленные,
из частых фамилий; звания - по должности в группе (ведущий старше).
"""
from __future__ import annotations

import random
import re

from . import model

RANKS = {
    "su": ["л-т", "ст. л-т", "к-н", "м-р", "п/п-к"],
    "gdr": ["Ultn.", "Ltn.", "Oltn.", "Hptm.", "Maj."],
    "frg": ["Lt", "OLt", "Hptm", "Maj", "OTL"],
    "us": ["2Lt", "1Lt", "Capt", "Maj", "Lt Col"],
    "uk": ["Plt Off", "Fg Off", "Flt Lt", "Sqn Ldr", "Wg Cdr"],
    "be": ["Lt", "Lt", "Capt", "Cdt", "Maj"],
    "nl": ["Ltz", "Elt", "Kap", "Maj", "LtKol"],
    "ca": ["2Lt", "Lt", "Capt", "Maj", "LCol"],
}
SURNAMES = {
    "su": ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
           "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
           "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев",
           "Романов", "Воробьёв", "Сергеев", "Кузьмин", "Фролов", "Александров", "Дмитриев", "Королёв", "Гусев", "Киселёв",
           "Ильин", "Максимов", "Поляков", "Сорокин", "Виноградов", "Ковалёв", "Белов", "Медведев", "Антонов", "Тарасов",
           "Бондаренко", "Шевченко", "Коваленко", "Ткаченко", "Мельник", "Ахметов", "Сафин", "Гарипов", "Абрамян", "Гусейнов"],
    "gdr": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
            "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
            "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Krause", "Meier", "Lehmann", "Schmid", "Schulze",
            "Maier", "Köhler", "Herrmann", "König", "Walter", "Mayer", "Huber", "Kaiser", "Fuchs", "Peters"],
    "us": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Anderson", "Taylor",
           "Thomas", "Moore", "Martin", "Jackson", "Thompson", "White", "Harris", "Clark", "Lewis", "Robinson",
           "Walker", "Young", "Allen", "King", "Wright", "Scott", "Hill", "Green", "Adams", "Baker",
           "Nelson", "Carter", "Mitchell", "Roberts", "Turner", "Phillips", "Campbell", "Parker", "Evans", "Edwards",
           "Garcia", "Martinez", "Rodriguez", "Lopez", "O'Brien", "Murphy", "Kowalski", "Novak", "Russo", "Schultz"],
    "uk": ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Robinson", "Wright",
           "Thompson", "Evans", "Walker", "White", "Roberts", "Green", "Hall", "Wood", "Jackson", "Clarke",
           "Hughes", "Edwards", "Turner", "Hill", "Harris", "Lewis", "Morgan", "Cooper", "Ward", "Watson",
           "MacDonald", "Campbell", "Stewart", "Murray", "Fraser", "Reid", "Ross", "Kerr", "Pritchard", "Llewellyn"],
    "be": ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Goossens", "Wouters", "De Smet",
           "Dubois", "Lambert", "Dupont", "Martin", "Simon", "Laurent", "Leclercq", "Renard", "Lejeune", "Lemaire"],
    "nl": ["de Jong", "Jansen", "de Vries", "van den Berg", "van Dijk", "Bakker", "Janssen", "Visser", "Smit", "Meijer",
           "de Boer", "Mulder", "de Groot", "Bos", "Vos", "Peters", "Hendriks", "van Leeuwen", "Dekker", "Brouwer"],
}
SURNAMES["frg"] = SURNAMES["gdr"]
SURNAMES["ca"] = SURNAMES["uk"][:25] + ["Tremblay", "Gagnon", "Roy", "Côté", "Bouchard", "Gauthier", "Morin", "Lavoie",
                                        "Fortin", "Gagné", "Ouellet", "Pelletier", "Bélanger", "Lévesque", "Bergeron"]
INITIALS = {"su": "АБВГДЕИКЛМНОПРСТФЮЯ", "gdr": "ABCDEFGHJKLMNPRSTUW", "frg": "ABCDEFGHJKLMNPRSTUW",
            "us": "ABCDEFGHJKLMNPRSTW", "uk": "ABCDEFGHJKLMNPRSTW", "be": "ABCDEFGHJLMPRS", "nl": "ABCDEFGHJKLMNPRSW",
            "ca": "ABCDEFGHJKLMNPRSTW"}
NATION_RE = [("gdr", r"ННА|NVA|JBG-\d|JG-\d|KHG|THG|MFG"), ("uk", r"RAF|брит|Royal"), ("be", r"бельг|Belg"),
             ("nl", r"Нидерл|голланд|Dutch|KLu"), ("ca", r"Канад|Canad"),
             ("frg", r"нем\.|ФРГ|Bundes|Luftwaffe|JaboG|JBG \d|JG \d|LTG \d|AG \d|MFG \d|Хересфлигер|PAH|Панцер"),
             ("us", r"США|USAF|U\.S\.|TFW|TRW|trw|амер")]


def nation(u: dict) -> str:
    if u.get("nation") in RANKS:
        return u["nation"]
    for n, rx in NATION_RE:
        if re.search(rx, u.get("name", "")):
            return n
    return "su" if u["side"] == "red" else "us"


def _rng(u: dict, k: int) -> random.Random:
    return random.Random(f"{u['id']}-{k}")


def new_name(u: dict, used: set[str]) -> dict:
    """Новый лётчик полка: звание - чаще младшие (пополнение - из училищ)."""
    nat = nation(u)
    k = u.get("_pilot_seq", 0)
    for _ in range(50):
        k += 1
        r = _rng(u, k)
        sur = r.choice(SURNAMES[nat])
        ini = r.choice(INITIALS[nat])
        name = f"{sur} {ini}.{r.choice(INITIALS[nat])}." if nat == "su" else f"{ini}. {sur}"
        if name not in used:
            break
    u["_pilot_seq"] = k
    rank = r.choices(range(5), weights=[3, 4, 3, 1.5, 0.5])[0]
    return {"name": name, "rank": rank, "sorties": 0}


def title(u: dict, p: dict) -> str:
    return f"{RANKS[nation(u)][p.get('rank', 0)]} {p['name']}"


def ensure(state: dict, u: dict) -> list[dict]:
    """Список лётчиков части - по числу экипажей (без учёта экипажей - самолётов)."""
    if model.category(u) not in ("air", "heli"):
        return []
    roster = u.setdefault("pilots", [])
    want = u["crews"] if "crews" in u else u.get("count", 0)
    used = {p["name"] for p in roster} | {p["name"] for p in u.get("pilots_lost", [])}
    while len(roster) < want:
        p = new_name(u, used)
        used.add(p["name"])
        roster.append(p)
    while len(roster) > want:                    # экипажей стало меньше без имени (потери вне учёта) - младший
        roster.remove(min(roster, key=lambda p: (p.get("rank", 0), p.get("sorties", 0))))
    return roster


def ensure_all(state: dict) -> None:
    for u in state["units"].values():
        ensure(state, u)


def crew_for(state: dict, u: dict, n: int, taken: set[str]) -> list[dict]:
    """Лётчики на вылет группы из n: ведущий - старший по званию и налёту, ведомые - остальные (кто меньше летал)."""
    roster = [p for p in ensure(state, u) if p["name"] not in taken]
    if not roster:
        return []
    lead = max(roster, key=lambda p: (p.get("rank", 0), p.get("sorties", 0)))
    rest = sorted((p for p in roster if p is not lead), key=lambda p: (p.get("sorties", 0), p["name"]))
    return ([lead] + rest)[:n]


def find(u: dict, name: str) -> dict | None:
    """Лётчик по имени ЛА в миссии ("звание фамилия" или фамилия)."""
    for p in u.get("pilots", []):
        if name == p["name"] or name.endswith(" " + p["name"]) or name.split(" (")[0].endswith(p["name"]):
            return p
    return None


def take(u: dict, name: str = "") -> dict | None:
    """Лётчик выбыл из списка (сбит - на земле, погиб, в плену): по имени ЛА, иначе младший."""
    roster = u.get("pilots") or []
    p = find(u, name) if name else None
    if p is None and roster:
        p = min(roster, key=lambda x: (x.get("rank", 0), x.get("sorties", 0)))
    if p is not None:
        roster.remove(p)
    return p


def back(u: dict, p: dict | None) -> None:
    if p and p["name"] not in {x["name"] for x in u.setdefault("pilots", [])}:
        u["pilots"].append(p)


def killed(u: dict, p: dict | None, how: str, day: int) -> None:
    if p:
        u.setdefault("pilots_lost", []).append({**p, "how": how, "day": day})


def split(u: dict, d: dict, n: int) -> None:
    """Передовая группа (farp.detach): берёт n лётчиков полка (по числу экипажей группы)."""
    roster = u.get("pilots") or []
    k = d.get("crews", n)
    d["pilots"] = roster[:k]
    u["pilots"] = roster[k:]
    d.pop("pilots_lost", None)


def join(u: dict, d: dict) -> None:
    u.setdefault("pilots", []).extend(d.get("pilots", []))
    u.setdefault("pilots_lost", []).extend(d.get("pilots_lost", []))


def flown(state: dict, u: dict, names: list[str]) -> None:
    """Слетали: +1 вылет лётчикам по именам ЛА."""
    for n in names:
        p = find(u, n)
        if p:
            p["sorties"] = p.get("sorties", 0) + 1

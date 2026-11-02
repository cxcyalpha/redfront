"""Генератор театра Сирия (карта DCS Syria), июнь 1982: data/sector_syria.json и data/oob_syria.json.

Сценарий - Ливанская война 1982 г. (операция "Мир Галилее"): 6 июня Израиль наступает в Ливан тремя направлениями -
побережье (Тир, Сидон, Дамур, Бейрут), центр (Набатия, Джеззин, шоссе Бейрут - Дамаск у Айн-Жальты) и восток (Хасбайя,
Рашайя, Джуб-Джаннин - долина Бекаа); 9 июня - удар по группировке ЗРК Сирии в Бекаа ("Медведка 19") и воздушные бои.
Синие - Израиль (наступает: поза offense по сценарию), красные - Сирия и вооружённые формирования ООП (оборона).

Источники (общие, по памяти - проверять): Ch. Herzog, "The Arab-Israeli Wars"; Z. Schiff, E. Ya'ari, "Israel's
Lebanon War" (1984); B. Lambeth, "Moscow's Lessons from the 1982 Lebanon Air War" (RAND, 1984). Координаты - ОЦЕНКА
(+-2 км), составы и числа - ОЦЕНКИ по порядку величины. Типы DCS - ближайшие: Меркава Mk1 - Merkava Mk4, Магах - M-60,
Т-62 - Т-55, Т-72М - Т-72Б, F-15A - F-15C, МиГ-23МФ/МС - МиГ-23МЛД, Су-22 - Су-17М4, AH-1S - AH-1W; A-4 и Кфир в DCS нет.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Herzog / Schiff-Ya'ari / Lambeth (RAND 1984), по памяти - проверить"

PLACES = {   # (широта, долгота, сторона на 6.06.1982)
    # Израиль, Голаны (под контролем Израиля), пояс Хаддада (союзник Израиля)
    "Haifa": (32.794, 34.989, "blue"), "Nahariya": (33.006, 35.095, "blue"), "Safed": (32.965, 35.496, "blue"),
    "Tiberias": (32.795, 35.531, "blue"), "KiryatShmona": (33.207, 35.570, "blue"), "Metula": (33.278, 35.578, "blue"),
    "Katzrin": (32.993, 35.693, "blue"), "Masada": (33.233, 35.753, "blue"), "Naqoura": (33.118, 35.140, "blue"),
    "Marjayoun": (33.360, 35.592, "blue"),
    # Южный Ливан (ООП), Бейрут, горы Шуф, долина Бекаа (Сирия)
    "Tyre": (33.271, 35.196, "red"), "Nabatieh": (33.378, 35.484, "red"), "Sidon": (33.561, 35.371, "red"),
    "Damour": (33.729, 35.456, "red"), "Beirut": (33.893, 35.501, "red"), "Aley": (33.808, 35.600, "red"),
    "BeitEdDine": (33.695, 35.580, "red"), "Jezzine": (33.544, 35.584, "red"), "AinZhalta": (33.745, 35.690, "red"),
    "Hasbaya": (33.398, 35.685, "red"), "Rashaya": (33.501, 35.843, "red"), "JoubJannine": (33.630, 35.785, "red"),
    "Chtaura": (33.818, 35.854, "red"), "Zahle": (33.847, 35.902, "red"), "Baalbek": (34.006, 36.211, "red"),
    "Masnaa": (33.700, 36.070, "red"),
    # Сирия
    "Quneitra": (33.126, 35.824, "red"), "Qatana": (33.437, 36.080, "red"), "Kiswah": (33.360, 36.240, "red"),
    "Damascus": (33.513, 36.292, "red"), "Sanamayn": (33.070, 36.180, "red"), "Homs": (34.730, 36.710, "red"),
}
LINKS = [   # дороги (ОЦЕНКА по карте)
    ("Haifa", "Nahariya"), ("Haifa", "Tiberias"), ("Nahariya", "Naqoura"), ("Nahariya", "Safed"), ("Safed", "Tiberias"),
    ("Safed", "KiryatShmona"), ("KiryatShmona", "Metula"), ("Tiberias", "Katzrin"), ("Katzrin", "Masada"),
    ("KiryatShmona", "Masada"), ("Metula", "Marjayoun"), ("Naqoura", "Tyre"), ("Tyre", "Sidon"), ("Tyre", "Nabatieh"),
    ("Marjayoun", "Nabatieh"), ("Marjayoun", "Hasbaya"), ("Nabatieh", "Sidon"), ("Nabatieh", "Jezzine"),
    ("Sidon", "Damour"), ("Sidon", "Jezzine"), ("Damour", "Beirut"), ("Damour", "BeitEdDine"), ("BeitEdDine", "Aley"),
    ("BeitEdDine", "AinZhalta"), ("Jezzine", "BeitEdDine"), ("Jezzine", "JoubJannine"), ("Beirut", "Aley"),
    ("Aley", "AinZhalta"), ("AinZhalta", "Chtaura"), ("Masada", "Hasbaya"), ("Masada", "Quneitra"),
    ("Hasbaya", "Rashaya"), ("Hasbaya", "JoubJannine"), ("Rashaya", "JoubJannine"), ("Rashaya", "Qatana"),
    ("JoubJannine", "Chtaura"), ("Chtaura", "Zahle"), ("Chtaura", "Masnaa"), ("Zahle", "Baalbek"), ("Baalbek", "Homs"),
    ("Masnaa", "Damascus"), ("Quneitra", "Qatana"), ("Quneitra", "Sanamayn"), ("Qatana", "Damascus"),
    ("Damascus", "Kiswah"), ("Kiswah", "Sanamayn"), ("Damascus", "Homs"),
]
SUPPLY_ENTRY = {"red": ["Damascus", "Homs"], "blue": ["Haifa", "Tiberias"]}
OFF_LIMITS = {"blue": ["Quneitra", "Qatana", "Kiswah", "Sanamayn", "Damascus", "Homs", "Masnaa", "Baalbek"],
              "red": ["Haifa", "Tiberias", "Safed", "Nahariya", "KiryatShmona", "Metula", "Katzrin", "Masada"]}
# политика сценария: Израиль не наступает на территорию Сирии (Голанский фронт закрыт), Сирия - на Израиль

AIRBASES = {   # терраин pydcs Syria
    "red": ["Damascus", "Mezzeh", "Al-Dumayr", "Khalkhalah", "Marj Ruhayyil", "Shayrat", "Al Qusayr", "Rayak",
            "Qabr as Sitt", "Beirut-Rafic Hariri"],
    "blue": ["Ramat David", "Megiddo", "Haifa", "Rosh Pina", "Kiryat Shmona", "Eyn Shemer", "Tel Nof", "Hatzor",
             "Palmachim", "Ben Gurion"],
}
AXES = {   # оси наступления синих (ОЦЕНКА по ходу операции)
    "coast": {"title": "Побережье: Тир - Сидон - Дамур - Бейрут", "objectives": ["Tyre", "Sidon", "Damour", "Beirut"]},
    "center": {"title": "Центр: Набатия - Джеззин - Айн-Жальта", "objectives": ["Nabatieh", "Jezzine", "BeitEdDine", "AinZhalta"]},
    "bekaa": {"title": "Бекаа: Хасбайя - Рашайя - Джуб-Джаннин - Штора", "objectives": ["Hasbaya", "Rashaya", "JoubJannine", "Chtaura"]},
}


def comp(*rows):
    return [{"type": t, "count": c, "role": r} for t, c, r in rows if c > 0]

IDF_DIV = comp(("Merkava_Mk4", 80, "MBT"), ("M-60", 110, "MBT"), ("M-113", 160, "APC"))   # угда (2-3 бригады)
IDF_AD = {"Vulcan": 6, "M48 Chaparral": 6}
SY_AD = comp(("T_55", 180, "MBT"), ("T_72B", 40, "MBT"), ("BMP_1", 120, "IFV"), ("BTR-60", 90, "APC"))   # бтд
SY_TBDE = comp(("T_72B", 90, "MBT"), ("BMP_1", 40, "IFV"))       # тбр (Т-72М)
SY_BDE = comp(("T_55", 60, "MBT"), ("BMP_1", 40, "IFV"), ("BTR-60", 30, "APC"))
PLO = comp(("T_55", 10, "MBT"), ("BTR-60", 20, "APC"))            # бригада ООП (в основном пехота)
SY_ADD = {"ZSU_23_4_Shilka": 8, "Strela_1_9P31": 8}
PLO_ADD = {"Ural_375_ZU_23": 8}

GROUND = [   # (id, имя, сторона, пункт, состав, ПВО, день ввода, ось, примечание)
    ("blue_91div", "91-я дивизия (побережье)", "blue", "Naqoura", IDF_DIV, IDF_AD, 1, "coast", ""),
    ("blue_36div", "36-я дивизия (Набатия)", "blue", "Marjayoun", IDF_DIV, IDF_AD, 1, "center", ""),
    ("blue_162div", "162-я дивизия (Джеззин)", "blue", "Marjayoun", IDF_DIV, IDF_AD, 1, "center", ""),
    ("blue_252div", "252-я дивизия (Бекаа)", "blue", "Masada", IDF_DIV, IDF_AD, 1, "bekaa", "группа сил Бекаа (Бен-Галь)"),
    ("blue_90div", "90-я дивизия (Бекаа)", "blue", "Katzrin", IDF_DIV, IDF_AD, 1, "bekaa", ""),
    ("blue_880div", "880-я дивизия (резерв)", "blue", "KiryatShmona", IDF_DIV, IDF_AD, 3, "bekaa", ""),
    ("red_plo_kastel", "Бригада ООП 'Кастель' (Тир)", "red", "Tyre", PLO, PLO_ADD, 1, None, ""),
    ("red_plo_karameh", "Бригада ООП 'Карама' (Хасбайя)", "red", "Hasbaya", PLO, PLO_ADD, 1, None, ""),
    ("red_plo_yarmouk", "Бригада ООП 'Ярмук' (Набатия)", "red", "Nabatieh", PLO, PLO_ADD, 1, None, ""),
    ("red_plo_sidon", "Формирования ООП (Сидон, Айн-аль-Хильва)", "red", "Sidon", PLO, PLO_ADD, 1, None, ""),
    ("red_85bde", "85-я бригада Сирии (Бейрут)", "red", "Beirut", SY_BDE, SY_ADD, 1, None, ""),
    ("red_62bde", "62-я отдельная бригада Сирии (Бекаа)", "red", "JoubJannine", SY_BDE, SY_ADD, 1, None, ""),
    ("red_1ad", "1-я бронетанковая дивизия Сирии", "red", "Chtaura", SY_AD, SY_ADD, 2, None, "введена в Бекаа 7-9.06"),
    ("red_91tbde", "91-я танковая бригада Сирии", "red", "Masnaa", SY_TBDE, SY_ADD, 2, None, ""),
    ("red_cdo", "Сирийские коммандос (шоссе Бейрут - Дамаск)", "red", "AinZhalta", comp(("BTR-60", 20, "APC")), {}, 2, None, ""),
    ("red_3ad", "3-я бронетанковая дивизия Сирии", "red", "Damascus", SY_AD, SY_ADD, 4, None, "резерв, Т-72"),
    # Голанский фронт: сирийские дивизии на линии разъединения (в войну 1982 г. фронт там не открывался)
    ("red_7div", "7-я механизированная дивизия Сирии (Голаны)", "red", "Quneitra", SY_AD, SY_ADD, 1, None, ""),
    ("red_5div", "5-я механизированная дивизия Сирии (Голаны)", "red", "Sanamayn", SY_AD, SY_ADD, 1, None, ""),
    ("red_9div", "9-я механизированная дивизия Сирии (Голаны)", "red", "Kiswah", SY_AD, SY_ADD, 1, None, ""),
]

KUB = [("Kub_1S91_str", "radar", 1), ("Kub_2P25_ln", "launcher", 4)]
S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 6)]
S125 = [("p-19 s-125 sr", "radar", 1), ("snr s-125 tr", "radar", 1), ("5p73 s-125 ln", "launcher", 4)]
HAWK = [("Hawk_sr", "radar", 1), ("Hawk_tr", "radar", 1), ("Hawk_pcp", "control", 1), ("Hawk_ln", "launcher", 6)]
# ЗРК Сирии в Бекаа к 9.06 - 19 батарей (в основном Куб, С-75, С-125) - места ОЦЕНКА; ПВО Дамаска; HAWK Израиля
SAMS = [("red_bekaa_kub_%d" % i, "Батарея Куб (Бекаа) №%d" % i, "red", "sam_medium", KUB, la, lo) for i, (la, lo) in
        enumerate([(33.80, 35.86), (33.76, 35.80), (33.70, 35.82), (33.66, 35.88), (33.86, 35.95), (33.90, 35.98),
                   (33.74, 35.92), (33.62, 35.83), (33.82, 35.78), (33.95, 36.05), (33.58, 35.90), (33.88, 35.86)], 1)]
SAMS += [
    ("red_bekaa_s75_1", "Дивизион С-75 (Бекаа)", "red", "sam_medium", S75, 33.84, 35.92),
    ("red_bekaa_s75_2", "Дивизион С-75 (Бекаа)", "red", "sam_medium", S75, 33.72, 35.86),
    ("red_bekaa_s125_1", "Дивизион С-125 (Бекаа)", "red", "sam_medium", S125, 33.78, 35.95),
    ("red_bekaa_s125_2", "Дивизион С-125 (Бекаа)", "red", "sam_medium", S125, 33.68, 35.78),
    ("red_dam_s75_1", "Дивизион С-75 (Дамаск)", "red", "sam_medium", S75, 33.60, 36.20),
    ("red_dam_s75_2", "Дивизион С-75 (Дамаск)", "red", "sam_medium", S75, 33.42, 36.35),
    ("red_dam_s125_1", "Дивизион С-125 (Дамаск)", "red", "sam_medium", S125, 33.48, 36.15),
    ("red_dam_kub_1", "Батарея Куб (Катана)", "red", "sam_medium", KUB, 33.40, 36.05),
    ("blue_hawk_haifa", "Батарея HAWK (Хайфа)", "blue", "sam_medium", HAWK, 32.82, 35.05),
    ("blue_hawk_galil", "Батарея HAWK (Верхняя Галилея)", "blue", "sam_medium", HAWK, 33.00, 35.55),
    ("blue_hawk_golan", "Батарея HAWK (Голаны)", "blue", "sam_medium", HAWK, 33.05, 35.72),
    ("blue_hawk_ramat", "Батарея HAWK (Рамат-Давид)", "blue", "sam_medium", HAWK, 32.68, 35.20),
]

DEPOTS = [
    ("blue_depot_kiryat", "Склад снабжения (Кирьят-Шмона)", "blue", "KiryatShmona"),
    ("blue_depot_nahariya", "Склад снабжения (Нахария)", "blue", "Nahariya"),
    ("blue_depot_golan", "Склад снабжения (Кацрин)", "blue", "Katzrin"),
    ("red_depot_beirut", "Склады ООП (Бейрут)", "red", "Beirut"),
    ("red_depot_sidon", "Склады ООП (Сидон)", "red", "Sidon"),
    ("red_depot_chtaura", "Склад снабжения сирийских войск (Штора)", "red", "Chtaura"),
    ("red_depot_damascus", "Склад снабжения (Дамаск)", "red", "Damascus"),
]
BRIDGES = [
    {"id": "br_litani_qasmiyeh", "name": "Мост Касмия через Литани", "lat": 33.333, "lon": 35.232,
     "links": [["Tyre", "Sidon"]], "source": "по памяти - проверить (зонд карты)"},
    {"id": "br_litani_khardali", "name": "Мост Хардали через Литани", "lat": 33.345, "lon": 35.560,
     "links": [["Marjayoun", "Nabatieh"]], "source": "по памяти - проверить (зонд карты)"},
]

AIR = [   # (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
    ("i_f15", "106-я и 133-я эскадрильи (F-15A)", "blue", "fighter", "F_15C", "Tel Nof", 30, 600, "F-15A - F-15C"),
    ("i_f16", "110-я и 117-я эскадрильи (F-16A)", "blue", "fighter_bomber", "F_16A", "Ramat David", 36, 500, ""),
    ("i_f4", "69-я, 119-я, 201-я эскадрильи (F-4E 'Курнас')", "blue", "fighter_bomber", "F_4E_45MC", "Hatzor", 40, 500, ""),
    ("i_e2c", "192-я эскадрилья (E-2C)", "blue", "awacs", "E_2C", "Palmachim", 2, 1000, ""),
    ("i_tank", "120-я эскадрилья (Боинг 707 - заправщик)", "blue", "tanker", "KC_135", "Ben Gurion", 2, 2000, "707 - KC-135"),
    ("i_ah1", "160-я и 161-я эскадрильи (AH-1S)", "blue", "attack_helo", "AH_1W", "Megiddo", 16, 150, "AH-1S - AH-1W"),
    ("i_uh1", "Вертолётная эскадрилья (UH-1/Белл 212)", "blue", "transport_helo", "UH_1H", "Rosh Pina", 12, 150, ""),
    ("s_mig21_dum", "Истребительные эскадрильи (МиГ-21)", "red", "fighter", "MiG_21Bis", "Al-Dumayr", 30, 250, ""),
    ("s_mig21_kh", "Истребительные эскадрильи (МиГ-21)", "red", "fighter", "MiG_21Bis", "Khalkhalah", 24, 250, ""),
    ("s_mig23", "Истребительные эскадрильи (МиГ-23МФ/МС)", "red", "fighter", "MiG_23MLD", "Shayrat", 24, 300,
     "МиГ-23МФ/МС - МиГ-23МЛД"),
    ("s_su22", "Истребительно-бомбардировочные эскадрильи (Су-22/Су-20)", "red", "fighter_bomber", "Su_17M4",
     "Marj Ruhayyil", 18, 300, "Су-22 - Су-17М4"),
    ("s_mig25", "Эскадрилья МиГ-25", "red", "interceptor", "MiG_25PD", "Al-Dumayr", 8, 300, ""),
    ("s_gazelle", "Вертолёты 'Газель' (ПТУР HOT)", "red", "attack_helo", "SA342M", "Qabr as Sitt", 14, 120, ""),
    ("s_mi8", "Вертолёты Ми-8", "red", "transport_helo", "Mi_8MT", "Mezzeh", 12, 200, ""),
]
AD_TEMPLATES = {
    "red": {"short": [{"name": "Стрела-1, ЗСУ-23-4", "composition": [("Strela_1_9P31", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)]}]},
    "blue": {"short": [{"name": "Чапарэл, Вулкан", "composition": [("M48 Chaparral", "launcher", 2), ("Vulcan", "launcher", 2)]}]},
}
AD_AF_OFFSET_KM = 1.5


def dist_km(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * 111.32, (a[1] - b[1]) * 111.32 * k)


def main() -> None:
    from dcs.terrain import Syria
    terrain = Syria()
    places = {n: {"lat": la, "lon": lo, "estimate": True, "side": s} for n, (la, lo, s) in PLACES.items()}
    adj = {n: set() for n in places}
    for a, b in LINKS:
        assert a in places and b in places, (a, b)
        adj[a].add(b); adj[b].add(a)
    seen, todo = set(), ["Haifa"]
    while todo:
        x = todo.pop()
        if x not in seen:
            seen.add(x); todo += adj[x]
    assert seen == set(places), f"граф несвязный: {set(places) - seen}"
    airbases, af_pos = {}, {}
    for side, names in AIRBASES.items():
        for n in names:
            bid = n.lower().replace(" ", "_").replace("-", "_")
            airbases[bid] = {"name": n, "airport": n, "side": side, "military": True}
            ll = terrain.airports[n].position.latlng()
            af_pos[bid] = (ll.lat, ll.lng, side, n)
    border = [((places[a]["lat"] + places[b]["lat"]) / 2, (places[a]["lon"] + places[b]["lon"]) / 2)
              for a, b in LINKS if places[a]["side"] != places[b]["side"]]
    sites = []
    for bid, (la, lo, side, name) in sorted(af_pos.items()):
        q = min(border, key=lambda q: dist_km((la, lo), q))
        d = dist_km((la, lo), q) or 1.0
        f = min(1.0, AD_AF_OFFSET_KM / d)
        sites.append({"id": f"{side}_ad_af_{bid}", "name": f"ПВО аэродрома {name}", "side": side, "tier": "short",
                      "covers": f"af_{bid}", "lat": round(la + (q[0] - la) * f, 4), "lon": round(lo + (q[1] - lo) * f, 4),
                      "variant": 0, "rule": "ПВО объекта: у каждого военного аэродрома"})
    sector = {
        "_about": "Театр Сирия - Ливан, июнь 1982 г. Генерирован tools/gen_syria.py. Координаты пунктов - ОЦЕНКИ "
                  "(+-2 км), дороги - вручную по карте. Стороны - утро 6.06.1982.",
        "theatre": "syria",
        "places": places,
        "airbases": airbases,
        "links": [list(l) for l in LINKS],
        "supply_entry": SUPPLY_ENTRY,
        "off_limits": OFF_LIMITS,
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"blue": {k: v["objectives"] for k, v in AXES.items()}, "red": []},
        "_about_objectives": "Оси наступления Израиля - ОЦЕНКА по ходу операции, не документ.",
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": BRIDGES,
        "ad_sites": sites,
        "_about_ad_sites": "ПВО аэродромов (ярус short) - шаблоны сторон; ЗРК - части состава сил.",
    }
    (DATA / "sector_syria.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")

    units = []
    for uid, name, side, place, cmp_, ad, day, axis, note in GROUND:
        u = {"id": uid, "name": name, "side": side, "role": "maneuver", "state": "defend" if day <= 1 else "pending",
             "route": [place], "progress_km": 0.0, "march_kmh": 30, "daily_advance_km": 25,
             "composition": cmp_, "source": SRC + "; состав - ОЦЕНКА", "estimate": True}
        if day > 1:
            u["arrives_day"], u["arrives_jitter"] = day, 0
        if axis:
            u["axis"] = axis
        if note:
            u["note"] = note
        units.append(u)
        if ad:
            units.append({"id": f"{uid}_pvo", "name": f"Войсковая ПВО: {name}", "side": side, "role": "sam_short",
                          "attached_to": uid, "state": u["state"],
                          "composition": [{"type": t, "count": c, "role": "launcher"} for t, c in ad.items()],
                          "source": "ОЦЕНКА", "estimate": True})
    for sid, name, side, role, cmp_, la, lo in SAMS:
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed", "fixed": True,
                      "pos": {"lat": la, "lon": lo},
                      "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        bid = base.lower().replace(" ", "_").replace("-", "_")
        assert bid in airbases, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": bid, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True})
    oob = {
        "_about": "Состав сил Ливанской войны 1982 г. (Израиль - Сирия и ООП). Генерирован tools/gen_syria.py; источники "
                  "- в поле source. Числа - ОЦЕНКИ по порядку величины.",
        "theatre": "syria",
        "preset": {"title": "Июнь 1982: Ливан, долина Бекаа", "year": 1982, "date": "1982-06-06"},
        "date": "1982-06-06",
        "countries": {"red": "Syria", "blue": "Israel"},
        "units": units,
        "variants": [{"name": "base", "title": "Июнь 1982: Ливан, долина Бекаа",
                      "posture": {"blue": "offense", "red": "defense"},
                      "_about_posture": "наступает Израиль; Сирия и ООП - в обороне (ops: поза по сценарию)"}],
        "replacements": {"air_per_day": 1, "note": "Пополнение: самолётов в сутки до штата (ОЦЕНКА)."},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]}
                                       for v in vs] for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_not_included": "A-4 'Скайхок' и 'Кфир' (в DCS нет), БПЛА 'Скаут' и 'Мастиф', ВМС, морской десант у Сидона "
                         "(96-я дивизия), Армия Южного Ливана, многонациональные силы.",
    }
    (DATA / "oob_syria.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пунктов {len(places)}, связей {len(LINKS)}, аэродромов {len(airbases)}, частей {len(GROUND)}, "
          f"ЗРК {len(SAMS)}, авиачастей {len(AIR)}")


if __name__ == "__main__":
    main()

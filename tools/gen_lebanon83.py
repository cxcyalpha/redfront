"""Генератор сценария "Ливан, декабрь 1983" (карта DCS Syria, гипотетическая эскалация): data/sector_lebanon83.json,
data/oob_lebanon83.json.

История: после взрыва казарм морской пехоты (23.10.1983) 4 декабря 1983 г. палубная авиация США (авианосцы Independence
и John F. Kennedy) нанесла удар по позициям Сирии в горах Шуф и Метн (потеряны A-6E и A-7E под ЗРК и ПЗРК); линкор
New Jersey обстреливал высоты. Сценарий развивает это в кампанию: Сирия и друзские/шиитские формирования наступают
на Сук-эль-Гарб и аэропорт Бейрута (позиции морской пехоты и ливанской армии), США отвечают авиацией с моря.
Израиль (южнее реки Авали) - вне боёв: его пункты закрыты для обеих сторон.

Источники (общие, по памяти - проверять): B. Hammel, "The Root" (1985); J. Lehman, "Command of the Seas" (1988);
отчёт ВМС о налёте 4.12.1983. Координаты, составы и числа - ОЦЕНКИ. Типы DCS: A-6E - ИИ-юнит DCS (тип описан в redfront.mods.a6e); A-7E в DCS нет -
его место занимает F/A-18C (допущение; в 1983 г. на этих авианосцах его не было). Авианосцы класса Forrestal/Kitty Hawk
- Forrestal из DCS. Ливанская армия - в коалиции США (одна страна на сторону).
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Hammel / Lehman, по памяти - проверить"

PLACES = {
    # Бейрут и побережье (морская пехота США, ливанская армия)
    "BeirutAirport": (33.821, 35.488, "blue"), "Khalde": (33.784, 35.476, "blue"), "Baabda": (33.834, 35.544, "blue"),
    "EastBeirut": (33.890, 35.530, "blue"), "Jounieh": (33.980, 35.618, "blue"), "SoukElGharb": (33.806, 35.578, "blue"),
    "Damour": (33.729, 35.456, "blue"),
    # горы Шуф и Метн (друзы, Сирия), шиитские кварталы
    "WestBeirut": (33.880, 35.490, "red"), "Aley": (33.808, 35.600, "red"), "Bhamdoun": (33.808, 35.650, "red"),
    "BeitEdDine": (33.695, 35.580, "red"), "AinZhalta": (33.745, 35.690, "red"), "Sofar": (33.810, 35.705, "red"),
    "Dhour": (33.900, 35.760, "red"), "Chtaura": (33.818, 35.854, "red"), "Zahle": (33.847, 35.902, "red"),
    "Baalbek": (34.006, 36.211, "red"), "Masnaa": (33.700, 36.070, "red"), "Damascus": (33.513, 36.292, "red"),
    "Homs": (34.730, 36.710, "red"),
    # север Ливана и Сирия - глубина театра (пути резервов, аэродромы, порты)
    "Byblos": (34.120, 35.650, "blue"), "Tripoli": (34.430, 35.840, "red"), "Hermel": (34.390, 36.390, "red"),
    "Qusayr": (34.510, 36.580, "red"), "Tartus": (34.890, 35.890, "red"), "Hama": (35.130, 36.750, "red"),
    "Latakia": (35.520, 35.780, "red"), "Nabk": (34.020, 36.730, "red"),
    # юг: зона Израиля
    "Sidon": (33.561, 35.371, "blue"), "Jezzine": (33.544, 35.584, "blue"),
}
LINKS = [
    ("BeirutAirport", "Khalde"), ("BeirutAirport", "Baabda"), ("BeirutAirport", "WestBeirut"), ("Khalde", "Damour"),
    ("Khalde", "SoukElGharb"), ("Baabda", "EastBeirut"), ("Baabda", "SoukElGharb"), ("EastBeirut", "Jounieh"),
    ("EastBeirut", "WestBeirut"), ("Jounieh", "Dhour"), ("SoukElGharb", "Aley"), ("Aley", "Bhamdoun"),
    ("Bhamdoun", "Sofar"), ("Sofar", "Chtaura"), ("Sofar", "Dhour"), ("Damour", "BeitEdDine"), ("BeitEdDine", "AinZhalta"),
    ("AinZhalta", "Sofar"), ("Dhour", "Zahle"), ("Chtaura", "Zahle"), ("Chtaura", "Masnaa"), ("Zahle", "Baalbek"),
    ("Baalbek", "Homs"), ("Masnaa", "Damascus"), ("Damascus", "Homs"), ("Damour", "Sidon"), ("Sidon", "Jezzine"),
    ("Jezzine", "BeitEdDine"),
    ("Jounieh", "Byblos"), ("Byblos", "Tripoli"), ("Tripoli", "Tartus"), ("Tartus", "Homs"), ("Tartus", "Latakia"),
    ("Latakia", "Hama"), ("Hama", "Homs"), ("Baalbek", "Hermel"), ("Hermel", "Qusayr"), ("Qusayr", "Homs"),
    ("Damascus", "Nabk"), ("Nabk", "Homs"), ("Tripoli", "Hermel"),
]
# ---- общая карта с театром 1982 (tools/gen_syria.py): те же пункты и дороги, другая обстановка ----
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_syria as S82  # noqa: E402

ISRAEL = ["Haifa", "Nahariya", "Safed", "Tiberias", "KiryatShmona", "Metula", "Katzrin", "Masada"]
# юг Ливана, занятый Израилем в декабре 1983 (после отхода из Шуфа на реку Авали, сентябрь 1983)
ISRAEL_LEB = ["Naqoura", "Marjayoun", "Tyre", "Nabatieh", "Hasbaya", "Sidon", "Jezzine"]
NEUTRAL = ISRAEL + ISRAEL_LEB
for _n, (_la, _lo, _s) in S82.PLACES.items():
    if _n == "Beirut" or _n in PLACES:          # Бейрут 1983 - подробнее (аэропорт, Хальде, Баабда, Западный и Восточный)
        continue
    PLACES[_n] = (_la, _lo, "red")
# Турция и Кипр - страны баз США (Инджирлик, Акротири): пункты без дорог, Сирия по ним не бьёт (их аэродромы
# планировщик относит к ближайшему пункту - без этих пунктов они 'сирийские')
PLACES["Adana"] = (37.00, 35.33, "neutral")
PLACES["Cyprus"] = (34.67, 33.04, "neutral")
FOREIGN = ["Adana", "Cyprus"]
for _n in NEUTRAL:
    PLACES[_n] = (*PLACES[_n][:2], "neutral")
_seen = {tuple(sorted(l)) for l in LINKS}
for _a, _b in S82.LINKS:
    _a, _b = ("WestBeirut" if x == "Beirut" else x for x in (_a, _b))
    if tuple(sorted((_a, _b))) not in _seen and _a != _b:
        _seen.add(tuple(sorted((_a, _b))))
        LINKS.append((_a, _b))

SUPPLY_ENTRY = {"red": ["Damascus", "Homs", "Hama"], "blue": ["Jounieh"]}
OFF_LIMITS = {"blue": ["Damascus", "Homs", "Masnaa", "Baalbek", "Tripoli", "Hermel", "Qusayr", "Tartus", "Hama", "Latakia",
                       "Nabk", "Rashaya", "JoubJannine", "Quneitra", "Qatana", "Kiswah", "Sanamayn"], "red": list(NEUTRAL)}
# политика: США не наступают на суше за пределы Бейрута (только авиация); зона Израиля закрыта для Сирии

AIRBASES = {"red": ["Damascus", "Mezzeh", "Al-Dumayr", "Khalkhalah", "Marj Ruhayyil", "Shayrat", "Rayak", "Hama", "Tiyas"],
            # гипотетически: США получают наземные базы - Инджирлик (Турция, НАТО; в 1983 - ротации ВВС США в Европе) и
            # Акротири (Кипр, Великобритания; осенью 1983 оттуда летали над Бейрутом 'Буканиры' RAF). Снабжение - извне
            "blue": ["Incirlik", "Akrotiri"]}
EXTERNAL = {"Incirlik", "Akrotiri"}
CARRIERS = {   # авианосцы - реальные корабли DCS (имя, класс pydcs, широта, долгота, TACAN, позывной, ICLS, МГц, группа флота);
    # исторически у Ливана в декабре 1983 г. - Independence (CV-62) и John F. Kennedy (CV-67): в DCS их нет, вместо них -
    # Forrestal (CV-59, однотипный с Forrestal) и Carl Vinson (CVN-70) - ДОПУЩЕНИЕ. Позиции - ОЦЕНКА.
    "cv62": ("USS Forrestal (CV-59)", "Forrestal", 33.95, 35.20, 59, "FOR", 2, 127.5, "blue_csg_forrestal"),
    "cv67": ("USS Carl Vinson (CVN-70)", "VINSON", 33.72, 35.10, 70, "VIN", 7, 128.5, "blue_csg_vinson"),
    "lha1": ("USS Tarawa (LHA-1)", "LHA_Tarawa", 33.83, 35.36, 1, "TAR", 0, 129.5, "blue_arg_tarawa"),
}
from naval_common import from_template as T   # noqa: E402
NAVAL = [   # корабельные группы (tools/naval_common.group): охранение - корабли DCS с реальными именами класса
    ("blue_csg_forrestal", "Авианосная ударная группа USS Forrestal", "blue", 33.95, 35.20,
     T("us_csg_1983", ("Forrestal", "carrier", "USS Forrestal (CV-59)"),
       ["USS Ticonderoga (CG-47)", "USS Clark (FFG-11)", "USS John A. Moore (FFG-19)"]), "CSG 59"),
    ("blue_csg_vinson", "Авианосная ударная группа USS Carl Vinson", "blue", 33.72, 35.10,
     T("us_csg_1983", ("VINSON", "carrier", "USS Carl Vinson (CVN-70)"),
       ["USS Belknap (CG-26)", "USS Aubrey Fitch (FFG-34)", "USS Clifton Sprague (FFG-16)"]), "CSG 70"),
    ("blue_arg_tarawa", "Десантная группа USS Tarawa", "blue", 33.83, 35.36,
     T("us_arg_1983", ("LHA_Tarawa", "carrier", "USS Tarawa (LHA-1)"), ["USS Estocin (FFG-15)", "USS Wadsworth (FFG-9)"]), "ARG"),
    ("red_fac_tartus", "Ракетные катера ВМС Сирии (Тартус)", "red", 34.95, 35.80,
     [("Type_021_1", "boat", "Катер пр. 205 №1"), ("Type_021_1", "boat", "Катер пр. 205 №2"), ("Type_021_1", "boat", "Катер пр. 205 №3")],
     "пр. 205 'Оса' - в DCS Type 021-1 (китайская копия 'Осы')"),
    ("blue_convoy_jounieh", "Транспорты снабжения (Джуния)", "blue", 34.05, 35.45,
     [("Dry_cargo_ship_1", "transport", "Транспорт №1"), ("Ship_Tilde_Supply", "transport", "Транспорт №2")], ""),
]
SEA_LANES = [("lane_jounieh", "blue", "Jounieh", "blue_convoy_jounieh", 250)]   # т/сутки - ОЦЕНКА
AXES = {"shouf": {"title": "Шуф: Алей - Сук-эль-Гарб - аэропорт", "objectives": ["SoukElGharb", "Baabda", "BeirutAirport"]},
        "coast": {"title": "Побережье: Дамур - Хальде", "objectives": ["Damour", "Khalde", "BeirutAirport"]}}


def comp(*rows):
    return [{"type": t, "count": c, "role": r} for t, c, r in rows if c > 0]

LAF = comp(("M-60", 30, "MBT"), ("M-113", 60, "APC"))            # бригада ливанской армии
USMC = comp(("M-60", 5, "MBT"), ("AAV7", 12, "APC"))             # 22-й/24-й экспедиционный отряд МП
SY_BDE = comp(("T_55", 40, "MBT"), ("BMP_1", 30, "IFV"), ("BTR-60", 20, "APC"))
MIL = comp(("T_55", 8, "MBT"), ("BTR-60", 15, "APC"))             # ополчение (друзы ПСП, Амаль)
SY_ADD = {"ZSU_23_4_Shilka": 6, "Strela_1_9P31": 4}
MIL_ADD = {"Ural_375_ZU_23": 6}
GROUND = [   # (id, имя, сторона, пункт, состав, ПВО, день ввода, ось)
    ("blue_usmc", "24-й экспедиционный отряд МП США (аэропорт)", "blue", "BeirutAirport", USMC, {"Soldier stinger": 4}, 1, None),
    ("blue_laf8", "8-я бригада ливанской армии (Сук-эль-Гарб)", "blue", "SoukElGharb", LAF, {}, 1, None),
    ("blue_laf4", "4-я бригада ливанской армии (Баабда)", "blue", "Baabda", LAF, {}, 1, None),
    ("blue_laf5", "5-я бригада ливанской армии (Хальде)", "blue", "Khalde", LAF, {}, 1, None),
    ("red_psp", "Ополчение ПСП (друзы, Алей)", "red", "Aley", MIL, MIL_ADD, 1, "shouf"),
    ("red_psp2", "Ополчение ПСП (друзы, Бейт-эд-Дин)", "red", "BeitEdDine", MIL, MIL_ADD, 1, "coast"),
    ("red_amal", "Ополчение 'Амаль' (Западный Бейрут)", "red", "WestBeirut", MIL, MIL_ADD, 1, None),
    ("red_sy_bhamdoun", "Сирийская бригада (Бхамдун)", "red", "Bhamdoun", SY_BDE, SY_ADD, 1, "shouf"),
    ("red_sy_sofar", "Сирийская бригада (Софар)", "red", "Sofar", SY_BDE, SY_ADD, 2, "shouf"),
    ("red_sy_chtaura", "Сирийская бригада (Штора)", "red", "Chtaura", SY_BDE, SY_ADD, 1, None),
    ("red_sy_reserve", "Сирийская бронетанковая бригада (резерв)", "red", "Damascus", SY_BDE, SY_ADD, 4, "coast"),
]
KUB = [("Kub_1S91_str", "radar", 1), ("Kub_2P25_ln", "launcher", 4)]
S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 6)]
S200 = [("RLS_19J6", "radar", 1), ("RPC_5N62V", "radar", 1), ("S-200_Launcher", "launcher", 4)]
OSA = [("Osa 9A33 ln", "launcher", 2)]
SAMS = [
    ("red_metn_kub_1", "Батарея Куб (Метн)", "red", "sam_medium", KUB, 33.86, 35.80),
    ("red_bekaa_kub_1", "Батарея Куб (Бекаа)", "red", "sam_medium", KUB, 33.80, 35.86),
    ("red_bekaa_s75", "Дивизион С-75 (Бекаа)", "red", "sam_medium", S75, 33.84, 35.92),
    ("red_shouf_osa", "Батарея Оса (Софар)", "red", "sam_short", OSA, 33.80, 35.72),
    ("red_s200_dumayr", "Дивизион С-200 (Думайр)", "red", "sam_long", S200, 33.62, 36.70),
    ("red_s200_shinshar", "Дивизион С-200 (Шиншар)", "red", "sam_long", S200, 34.62, 36.72),
]
DEPOTS = [("blue_depot_jounieh", "Склад снабжения (Джуния)", "blue", "Jounieh"),
          ("red_depot_chtaura", "Склад снабжения сирийских войск (Штора)", "red", "Chtaura"),
          ("red_depot_aley", "Склады ПСП (Алей)", "red", "Aley")]
AIR = [   # (id, имя, сторона, роль, тип, база, число, радиус км, примечание)
    ("us_vf14", "VF-14, VF-32 (F-14A, Forrestal)", "blue", "fighter", "F_14A_135_GR", "cv62", 24, 500, ""),
    ("us_va_ind", "VA-15, VA-87 (A-7E, Forrestal)", "blue", "fighter_bomber", "FA_18C_hornet", "cv62", 24, 500,
     "A-7E в DCS нет - F/A-18C (допущение)"),
    ("us_va176", "VA-176 (A-6E, Forrestal)", "blue", "fighter_bomber", "A6E", "cv62", 10, 600, ""),
    ("us_e2_ind", "VAW-122 (E-2C)", "blue", "awacs", "E_2C", "cv62", 4, 1000, ""),
    ("us_s3_ind", "VS-28 (S-3A, заправщик)", "blue", "tanker", "S_3B_Tanker", "cv62", 4, 800, "S-3A - S-3B Tanker"),
    ("us_vf11", "VF-11, VF-31 (F-14A, Carl Vinson)", "blue", "fighter", "F_14A_135_GR", "cv67", 24, 500, ""),
    ("us_va_jfk", "VA-15 (A-7E, Carl Vinson)", "blue", "fighter_bomber", "FA_18C_hornet", "cv67", 12, 500,
     "A-7E в DCS нет - F/A-18C (допущение)"),
    ("us_va75", "VA-75, VA-85 (A-6E, Carl Vinson)", "blue", "fighter_bomber", "A6E", "cv67", 20, 600, ""),
    ("us_e2_jfk", "VAW-126 (E-2C)", "blue", "awacs", "E_2C", "cv67", 4, 1000, ""),
    ("us_hmm", "HMM-162 (CH-46/AH-1T, Тарава)", "blue", "attack_helo", "AH_1W", "lha1", 4, 120, "AH-1T - AH-1W"),
    # наземные базы (гипотетически): ротации ВВС США из Европы
    ("us_f4_incirlik", "Ротация F-4E ВВС США в Европе (Инджирлик)", "blue", "fighter_bomber", "F_4E_45MC", "Incirlik", 18, 700,
     "ОЦЕНКА: эскадрилья F-4E на ротации (в 1983 - учебные ротации в Инджирлике)"),
    ("us_f15_incirlik", "Ротация F-15C (36-е крыло, Битбург; Инджирлик)", "blue", "fighter", "F_15C", "Incirlik", 18, 800,
     "гипотетически: прикрытие ударов от истребителей Сирии"),
    ("us_kc135_akrotiri", "Заправщики KC-135A (Акротири)", "blue", "tanker", "KC_135", "Akrotiri", 4, 1500, "ОЦЕНКА"),
    ("s_mig21", "Истребительные эскадрильи (МиГ-21)", "red", "fighter", "MiG_21Bis", "Al-Dumayr", 24, 250, ""),
    ("s_mig23", "Истребительные эскадрильи (МиГ-23МЛ)", "red", "fighter", "MiG_23MLD", "Shayrat", 24, 300, ""),
    ("s_su22", "Истребительно-бомбардировочные эскадрильи (Су-22)", "red", "fighter_bomber", "Su_17M4", "Marj Ruhayyil", 18, 300, ""),
    ("s_gazelle", "Вертолёты 'Газель'", "red", "attack_helo", "SA342M", "Rayak", 10, 120, ""),
    ("s_mig23bn", "Истребительно-бомбардировочные эскадрильи (МиГ-23БН; в DCS - МиГ-23МЛД)", "red", "fighter_bomber",
     "MiG_23MLD", "Hama", 12, 300, "МиГ-23БН в DCS нет"),
    ("s_mig25", "Эскадрилья МиГ-25ПД (Тияс)", "red", "interceptor", "MiG_25PD", "Tiyas", 8, 400, ""),
]
AD_TEMPLATES = {"red": {"short": [{"name": "Стрела-1, ЗСУ-23-4", "composition": [("Strela_1_9P31", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)]}]}}


# Сирия 1983: дивизии на Голанах (линия разъединения) и ПВО Дамаска - как в 1982 (gen_syria), числа - ОЦЕНКА
GROUND += [(g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7]) for g in S82.GROUND if g[0] in ("red_7div", "red_5div", "red_9div")]
SAMS += [s_ for s_ in S82.SAMS if s_[0].startswith("red_dam_")] + [
    ("red_s200_dumayr2", "Дивизион С-200 (Дамаск)", "red", "sam_long", S200, 33.45, 36.45)]
DEPOTS += [("red_depot_damascus", "Склад снабжения (Дамаск)", "red", "Damascus")]
# Вариант 'Израиль вступает' (гипотетический; повод - соглашение о стратегическом сотрудничестве США и Израиля,
# ноябрь 1983): ВВС Израиля 1983 - как в 1982 (gen_syria.AIR), ЦАХАЛ на юге Ливана и Голанах - в обороне, HAWK
IL_AIR = [a for a in S82.AIR if a[2] == "blue"]
IL_GROUND = [
    ("blue_idf_awali", "Группа ЦАХАЛ на реке Авали (Сидон)", "blue", "Sidon", S82.IDF_DIV, S82.IDF_AD, 1, None),
    ("blue_idf_bekaa", "Группа ЦАХАЛ в Южной Бекаа (Хасбайя)", "blue", "Hasbaya", S82.IDF_DIV, S82.IDF_AD, 1, None),
    ("blue_idf_golan", "Дивизия ЦАХАЛ на Голанах", "blue", "Katzrin", S82.IDF_DIV, S82.IDF_AD, 1, None),
]
IL_SAMS = [s_ for s_ in S82.SAMS if s_[0].startswith("blue_hawk_")]
IL_DEPOTS = [d for d in S82.DEPOTS if d[2] == "blue"]


TITLE = "Декабрь 1983: Ливан, авианосцы и базы США"
TITLE_IL = "Декабрь 1983: Ливан, США и Израиль против Сирии (гипотетически)"


def bid_of(n):
    return n.lower().replace(" ", "_").replace("-", "_")


def main(il: bool = False) -> None:
    """il - вариант 'Израиль вступает' (sector/oob_lebanon83_il.json); иначе Израиль и занятый им юг Ливана -
    нейтральны: пункты на карте без стороны и без дорог в зону боёв (туда не наступают, по ним не бьют)."""
    scen = "lebanon83_il" if il else "lebanon83"
    from dcs.terrain import Syria
    terrain = Syria()
    places = {n: {"lat": la, "lon": lo, "estimate": True, "side": s} for n, (la, lo, s) in PLACES.items()}
    for a, b in LINKS:
        assert a in places and b in places, (a, b)
    for n in NEUTRAL:
        places[n]["side"] = "blue" if il else None
        if not il:
            places[n]["neutral"] = True
    for n in FOREIGN:
        places[n]["side"], places[n]["neutral"] = None, True
    links = [l for l in LINKS if il or not (set(l) & set(NEUTRAL))]
    abases = {s: list(v) + (S82.AIRBASES["blue"] if il and s == "blue" else []) for s, v in AIRBASES.items()}
    ground = GROUND + (IL_GROUND if il else [])
    sams = SAMS + (IL_SAMS if il else [])
    depots = DEPOTS + (IL_DEPOTS if il else [])
    air = AIR + (IL_AIR if il else [])
    airbases = {}
    for side, names in abases.items():
        for n in names:
            assert n in terrain.airports, n
            airbases[bid_of(n)] = {"name": n, "airport": n, "side": side, "military": True,
                                   **({"supply_external": True} if n in EXTERNAL else {})}
    carriers = {cid: {"name": n, "side": "blue", "ship": t, "lat": la, "lon": lo, "tacan": tc, "tacan_id": tid,
                      "icls": icls or None, "freq": f, "naval": nv, "estimate": True}
                for cid, (n, t, la, lo, tc, tid, icls, f, nv) in CARRIERS.items()}
    sector = {
        "_about": "Ливан, декабрь 1983 (гипотетическая эскалация). Генерирован tools/gen_lebanon83.py. Координаты - ОЦЕНКИ. "
                  "Театр - Ливан и запад Сирии до Латакии и Хамы; у США - авианосцы и наземные базы (Инджирлик, Акротири).",
        "air_limits": {"blue": ["Latakia", "Hama", "Tartus"], "red": FOREIGN + ([] if il else NEUTRAL)},
        "theatre": "syria", "places": places, "airbases": airbases, "carriers": carriers,
        "links": [list(l) for l in links], "supply_entry": SUPPLY_ENTRY, "off_limits": OFF_LIMITS,
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()}, "blue": []},
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in depots],
        "bridges": [], "ad_sites": [],
        "sea_lanes": [{"id": i, "side": sd, "port": pt, "convoy": cv, "t_per_day": t} for i, sd, pt, cv, t in SEA_LANES],
        "naval_bases": {"red": [{"name": "Тартус", "lat": 34.90, "lon": 35.86}]},
        "asm_stock": {"blue": {"count": 24, "per_day": 2, "type": "AGM-84 Harpoon (A-6E)", "note": "ОЦЕНКА: запас на 2 авианосцах, пополнение с транспорта боеприпасов"}, "red": {"count": 0, "per_day": 0, "note": "у ВВС Сирии 1983 г. авиационных ПКР нет - только бомбы"}},   # запас авиационных ПКР сторон (naval.use_air_asm; ОЦЕНКА)
    }
    (DATA / f"sector_{scen}.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")
    units = []
    for uid, name, side, place, cmp_, ad, day, axis in ground:
        u = {"id": uid, "name": name, "side": side, "role": "maneuver", "state": "defend" if day <= 1 else "pending",
             "route": [place], "progress_km": 0.0, "march_kmh": 25, "daily_advance_km": 10,
             "composition": cmp_, "source": SRC + "; состав - ОЦЕНКА", "estimate": True}
        if day > 1:
            u["arrives_day"], u["arrives_jitter"] = day, 0
        if axis:
            u["axis"] = axis
        units.append(u)
        if ad:
            units.append({"id": f"{uid}_pvo", "name": f"Войсковая ПВО: {name}", "side": side, "role": "sam_short",
                          "attached_to": uid, "state": u["state"],
                          "composition": [{"type": t, "count": c, "role": "launcher"} for t, c in ad.items()],
                          "source": "ОЦЕНКА", "estimate": True})
    for sid, name, side, role, cmp_, la, lo in sams:
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed", "fixed": True,
                      "pos": {"lat": la, "lon": lo}, "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from naval_common import group
    for row in NAVAL:
        uid, name, side, la, lo, ships, *rest = row
        units.append(group(uid, name, side, la, lo, ships, note=(rest[0] if rest and not rest[0].startswith(("CSG", "ARG")) else ""),
                           source=SRC + "; состав и место - ОЦЕНКА", abbr=(rest[0] if rest and rest[0].startswith(("CSG", "ARG")) else "")))
    il_ids = {r[0] for r in IL_AIR + IL_GROUND + IL_SAMS} | {r[0] for r in IL_DEPOTS}
    for u in units:                              # части Израиля в коалиции с США: своя национальность (ливреи)
        if u["id"] in il_ids or u.get("attached_to") in il_ids:
            u["nation"] = "il"
    for uid, name, side, role, typ, base, count, radius, note in air:
        b = base if base in carriers else bid_of(base)
        assert b in airbases or b in carriers, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": b, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True, **({"tasks_not": ["fleet_cap"]} if b in airbases and side == "blue" else {}),   # прикрытие флота - палубные
                      **({"mod": S82.MOD_TYPES[typ]} if typ in S82.MOD_TYPES else {}),
                      **({"nation": "il"} if uid in il_ids else {})})
    oob = {
        "_about": "Ливан, декабрь 1983: палубная авиация США против Сирии (гипотетическая кампания). tools/gen_lebanon83.py.",
        "theatre": "syria",
        "preset": {"title": TITLE_IL if il else TITLE, "year": 1983, "date": "1983-12-04"},
        "date": "1983-12-04", "doctrine": {"red": "arab"}, "countries": {"red": "Syria", "blue": "USA"}, "units": units,
        "variants": [{"name": "base", "title": TITLE_IL if il else TITLE,
                      "posture": {"red": "offense", "blue": "defense"},
                      "task_rules": {"blue": {"strike_factory": {"off": True, "why": "удары - только по войскам и ПВО в Ливане"}},
                                     "red": {"strike_ship": {"off": True, "why": "Сирия в 1983 г. по кораблям 6-го флота не била (огонь ЗРК - только по самолётам)"}}}}],
        "replacements": {"air_per_day": 1, "note": "ОЦЕНКА"},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]} for v in vs]
                                for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_not_included": "A-7E (нет в DCS - F/A-18C), линкор New Jersey, многонациональные силы "
                         "(Франция - 'Супер Этандары' с 'Клемансо', Великобритания - 'Буканиры' из Акротири: в DCS их нет), "
                         "F-111 (нет в DCS)" + ("." if il else "; Израиль и занятый им юг Ливана - нейтральны (на карте, вне боёв)."),
    }
    (DATA / f"oob_{scen}.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{scen}: пунктов {len(places)}, связей {len(links)}, частей {len(ground)}, ЗРК {len(sams)}, авиачастей {len(air)}")


if __name__ == "__main__":
    main()
    main(il=True)

"""Генератор сценария "Октябрь 1973: Голаны" (карта DCS Syria): data/sector_golan73.json, data/oob_golan73.json.

Октябрьская война (война Судного дня), северный фронт: 6 октября 1973 г. в 14:00 три пехотные дивизии Сирии (7-я,
9-я, 5-я) с танками прорывают оборону на Голанах ("Пурпурная линия" 1967 г.); вертолётный десант берёт опорный
пункт Хермон. Израиль держит две бронетанковые бригады (7-я - на севере, "Долина слёз"; 188-я "Барак" - на юге) и
вводит резервы по дням (дивизии Ланера и Пеледа - 7-9.10). 7.10 авиация Израиля пытается разом подавить ЗРК Сирии
(операция "Догман-5") - тяжёлые потери от Куба. С 11.10 - контрнаступление Израиля на Сасу (к Дамаску ~40 км);
13.10 подходит 3-я бронетанковая дивизия Ирака, 16.10 - 40-я бронетанковая бригада Иордании.

Источники (общие, по памяти - проверять): Ch. Herzog, "The War of Atonement" (1975); A. Rabinovich, "The Yom Kippur
War" (2004); D. Asher, "The Syrian Invasion of the Golan Heights" (2016); K. Pollack, "Arabs at War" (2002). Координаты - ОЦЕНКА (+-2 км), составы и числа - ОЦЕНКИ по
порядку величины. Типы DCS: "Центурион" (Шот Каль) - M-60; Т-62 - Т-55; БТР-152 - БТР-60; "Нешер"/"Мираж" III -
Mirage F1CE; МиГ-17 - МиГ-15бис; Су-7БМК - Су-17М4; A-4 - мод A-4E-C (если включён); Стрела-2 - Игла.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Herzog 'War of Atonement' / Rabinovich 'Yom Kippur War' / Asher / Pollack 'Arabs at War', по памяти - проверить"

PLACES = {   # (широта, долгота, сторона на 6.10.1973 до 14:00)
    # Израиль, Голаны (Израиль с 1967 г.)
    "Haifa": (32.794, 34.989, "blue"), "Afula": (32.607, 35.289, "blue"), "Tiberias": (32.795, 35.531, "blue"),
    "Safed": (32.965, 35.496, "blue"), "RoshPina": (32.970, 35.545, "blue"), "KiryatShmona": (33.207, 35.570, "blue"),
    "BnotYaakov": (33.003, 35.630, "blue"), "ArikBridge": (32.880, 35.630, "blue"), "Hermon": (33.312, 35.786, "blue"),
    "MajdalShams": (33.268, 35.770, "blue"), "Masada": (33.233, 35.753, "blue"), "Booster": (33.170, 35.790, "blue"),
    "Kuneitra": (33.126, 35.824, "blue"), "Nafah": (33.068, 35.752, "blue"), "Rafid": (32.950, 35.886, "blue"),
    "Hushniya": (32.979, 35.787, "blue"), "ElAl": (32.820, 35.735, "blue"), "Gamla": (32.900, 35.740, "blue"),
    # Сирия
    "KhanArnabah": (33.182, 35.883, "red"), "Kudne": (33.040, 35.890, "red"), "TelShams": (33.240, 35.950, "red"),
    "Sasa": (33.290, 36.010, "red"), "Kanaker": (33.270, 36.085, "red"), "Nawa": (32.888, 36.045, "red"),
    "Jassem": (32.990, 36.060, "red"), "SheikhMaskin": (32.830, 36.158, "red"), "Sanamayn": (33.070, 36.180, "red"),
    "Kiswah": (33.360, 36.240, "red"), "Katana": (33.437, 36.080, "red"), "Damascus": (33.513, 36.292, "red"),
    "Deraa": (32.625, 36.105, "red"), "Homs": (34.730, 36.710, "red"),
    "Tartus": (34.890, 35.890, "red"), "Latakia": (35.520, 35.790, "red"),
}
LINKS = [
    ("Haifa", "Afula"), ("Haifa", "Safed"), ("Afula", "Tiberias"), ("Tiberias", "RoshPina"), ("Safed", "RoshPina"),
    ("RoshPina", "KiryatShmona"), ("RoshPina", "BnotYaakov"), ("Tiberias", "ArikBridge"), ("KiryatShmona", "Masada"),
    ("BnotYaakov", "Nafah"), ("ArikBridge", "Gamla"), ("ArikBridge", "ElAl"), ("Gamla", "Nafah"), ("Gamla", "Hushniya"),
    ("Nafah", "Kuneitra"), ("Nafah", "Hushniya"), ("Nafah", "Booster"), ("Booster", "Masada"), ("Booster", "Kuneitra"),
    ("Masada", "MajdalShams"), ("MajdalShams", "Hermon"), ("Hushniya", "Rafid"), ("Hushniya", "ElAl"), ("ElAl", "Rafid"),
    ("Kuneitra", "KhanArnabah"), ("Booster", "KhanArnabah"), ("Rafid", "Kudne"), ("Kuneitra", "Kudne"), ("Rafid", "Nawa"),
    ("ElAl", "SheikhMaskin"), ("KhanArnabah", "TelShams"), ("TelShams", "Sasa"), ("Sasa", "Kanaker"), ("Kanaker", "Kiswah"),
    ("Sasa", "Katana"), ("Katana", "Damascus"), ("Kiswah", "Damascus"), ("Kudne", "Jassem"), ("Jassem", "Nawa"),
    ("Nawa", "SheikhMaskin"), ("Jassem", "Sanamayn"), ("SheikhMaskin", "Sanamayn"), ("SheikhMaskin", "Deraa"),
    ("Sanamayn", "Kiswah"), ("Damascus", "Homs"), ("MajdalShams", "TelShams"), ("Homs", "Tartus"), ("Tartus", "Latakia"),
]
SUPPLY_ENTRY = {"red": ["Damascus", "Homs", "Deraa"], "blue": ["Haifa", "Afula"]}
OFF_LIMITS = {"blue": ["Kiswah", "Katana", "Damascus", "Homs", "Sanamayn", "Deraa", "Tartus", "Latakia"],   # дальше Сасы и Канакера Израиль не шёл
              "red": ["Haifa", "Afula", "Tiberias", "Safed", "RoshPina", "KiryatShmona"]}   # Сирия - только Голаны

AIRBASES = {
    "red": ["Damascus", "Mezzeh", "Al-Dumayr", "Khalkhalah", "Marj Ruhayyil", "Sayqal", "An Nasiriyah", "Shayrat"],
    "blue": ["Ramat David", "Megiddo", "Rosh Pina", "Hatzor", "Tel Nof", "Hatzerim", "Eyn Shemer"],
}
AXES = {   # оси наступления Сирии (6-9.10)
    "north": {"title": "Север: Хан-Арнаба - Кунейтра - Нафах - мост Бнот-Яаков", "objectives": ["Kuneitra", "Booster", "Nafah", "BnotYaakov"]},
    "south": {"title": "Юг: Кудне - Рафид - Хушния - Эль-Аль - мост Арик", "objectives": ["Rafid", "Hushniya", "ElAl", "ArikBridge"]},
    "hermon": {"title": "Хермон", "objectives": ["Hermon", "MajdalShams"]},
}
BLUE_AXES = {   # контрнаступление Израиля (с 11.10)
    "sasa": {"title": "Контрнаступление: Кунейтра - Хан-Арнаба - Тель-Шамс - Саса", "objectives": ["KhanArnabah", "TelShams", "Sasa", "Kanaker"]},
}


def comp(*rows):
    return [{"type": t, "count": c, "role": r} for t, c, r in rows if c > 0]

SY_INF = comp(("T_55", 180, "MBT"), ("BMP_1", 30, "IFV"), ("BTR-60", 70, "APC"), ("Infantry AK", 200, "infantry"),
              ("Grad-URAL", 6, "MRL"))           # пехотная дивизия Сирии с танковой бригадой (~180 танков)
SY_ARM = comp(("T_55", 230, "MBT"), ("BMP_1", 60, "IFV"), ("BTR-60", 40, "APC"))     # бронетанковая дивизия (Т-62/Т-55)
SY_BDE = comp(("T_55", 90, "MBT"), ("BTR-60", 30, "APC"))
SY_ADD = {"ZSU_23_4_Shilka": 8, "Strela_1_9P31": 6, "SA-18 Igla manpad": 6}
IQ_ARM = comp(("T_55", 200, "MBT"), ("BTR-60", 60, "APC"))
JO_BDE = comp(("M-60", 100, "MBT"), ("M-113", 30, "APC"))                             # "Центурионы" - M-60
IL_BDE = comp(("M-60", 90, "MBT"), ("M-113", 25, "APC"))                              # бронетанковая бригада ("Шот Каль")
IL_BDE_S = comp(("M-60", 60, "MBT"), ("M-113", 15, "APC"))
IL_INF = comp(("Soldier M4", 60, "infantry"), ("M-113", 20, "APC"))
IL_ADD = {"Vulcan": 4}

GROUND = [   # (id, имя, сторона, пункт, состав, ПВО, день ввода, ось)
    ("red_7div", "7-я пехотная дивизия Сирии", "red", "KhanArnabah", SY_INF, SY_ADD, 1, "north"),
    ("red_9div", "9-я пехотная дивизия Сирии", "red", "Kudne", SY_INF, SY_ADD, 1, "south"),
    ("red_5div", "5-я пехотная дивизия Сирии", "red", "Nawa", SY_INF, SY_ADD, 1, "south"),
    ("red_1ad", "1-я бронетанковая дивизия Сирии", "red", "Jassem", SY_ARM, SY_ADD, 2, "south"),
    ("red_3ad", "3-я бронетанковая дивизия Сирии", "red", "TelShams", SY_ARM, SY_ADD, 2, "north"),
    ("red_47bde", "47-я отдельная бронетанковая бригада Сирии", "red", "Sasa", SY_BDE, SY_ADD, 1, "north"),
    ("red_51bde", "51-я отдельная бронетанковая бригада Сирии", "red", "SheikhMaskin", SY_BDE, SY_ADD, 1, "south"),
    ("red_iq3ad", "3-я бронетанковая дивизия Ирака", "red", "SheikhMaskin", IQ_ARM, SY_ADD, 8, None),
    ("red_jo40", "40-я бронетанковая бригада Иордании", "red", "Deraa", JO_BDE, {}, 11, None),
    ("blue_7bde", "7-я бронетанковая бригада", "blue", "Booster", IL_BDE, IL_ADD, 1, None),
    ("blue_188", "188-я бронетанковая бригада 'Барак'", "blue", "Hushniya", IL_BDE_S, IL_ADD, 1, None),
    ("blue_golani", "Бригада 'Голани' (опорные пункты)", "blue", "Kuneitra", IL_INF, {}, 1, None),
    ("blue_679", "679-я бронетанковая бригада (резерв)", "blue", "Nafah", IL_BDE, IL_ADD, 2, None),
    ("blue_17", "17-я бронетанковая бригада (резерв)", "blue", "ElAl", IL_BDE, IL_ADD, 2, None),
    ("blue_19", "19-я бронетанковая бригада (резерв)", "blue", "ArikBridge", IL_BDE, IL_ADD, 3, None),
    ("blue_205", "205-я бронетанковая бригада (резерв)", "blue", "Gamla", IL_BDE, IL_ADD, 3, None),
    ("blue_9", "9-я бронетанковая бригада (резерв)", "blue", "BnotYaakov", IL_BDE, IL_ADD, 3, None),
    ("blue_4", "4-я бронетанковая бригада (резерв)", "blue", "ArikBridge", IL_BDE, IL_ADD, 4, None),
    ("blue_31", "31-я парашютно-десантная бригада (резерв)", "blue", "RoshPina", IL_INF, {}, 4, None),
]
AIRMOBILE = [   # десант на Хермон (6.10, вертолёты Ми-8) - роты 82-го парашютного батальона: ОЦЕНКА численности
    ("red_82pb_1", "Рота 82-го парашютного батальона Сирии", "red", "TelShams", 100),
    ("red_82pb_2", "Рота 82-го парашютного батальона Сирии (вторая)", "red", "Sasa", 100),
]

KUB = [("Kub_1S91_str", "radar", 1), ("Kub_2P25_ln", "launcher", 4)]
S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 6)]
S125 = [("p-19 s-125 sr", "radar", 1), ("snr s-125 tr", "radar", 1), ("5p73 s-125 ln", "launcher", 4)]
HAWK = [("Hawk_sr", "radar", 1), ("Hawk_tr", "radar", 1), ("Hawk_pcp", "control", 1), ("Hawk_ln", "launcher", 6)]
# "Стена ЗРК" Сирии: Куб - у фронта (подвижные, за наступающими), С-75 и С-125 - от Сасы до Дамаска; места - ОЦЕНКА
KUB_POS = [(33.20, 35.95), (33.10, 35.93), (33.00, 35.95), (32.90, 36.05), (33.25, 36.02), (33.15, 36.05),
           (33.05, 36.08), (32.95, 36.12), (33.30, 36.10), (32.85, 36.20)]
SAMS = [(f"red_kub_{i}", f"Батарея Куб №{i}", "red", "sam_medium", KUB, la, lo) for i, (la, lo) in enumerate(KUB_POS, 1)]
SAMS += [(f"red_s75_{i}", f"Дивизион С-75 №{i}", "red", "sam_medium", S75, la, lo) for i, (la, lo) in
         enumerate([(33.35, 36.18), (33.45, 36.20), (33.55, 36.35), (33.25, 36.25), (33.10, 36.25), (33.60, 36.20)], 1)]
SAMS += [(f"red_s125_{i}", f"Дивизион С-125 №{i}", "red", "sam_medium", S125, la, lo) for i, (la, lo) in
         enumerate([(33.32, 36.08), (33.18, 36.15), (33.42, 36.12), (33.50, 36.28)], 1)]
SAMS += [("blue_hawk_roshpina", "Батарея HAWK (Рош-Пина)", "blue", "sam_medium", HAWK, 32.97, 35.56),
         ("blue_hawk_tiberias", "Батарея HAWK (Тверия)", "blue", "sam_medium", HAWK, 32.80, 35.50),
         ("blue_hawk_ramat", "Батарея HAWK (Рамат-Давид)", "blue", "sam_medium", HAWK, 32.68, 35.20)]

DEPOTS = [("blue_depot_roshpina", "Склад снабжения (Рош-Пина)", "blue", "RoshPina"),
          ("blue_depot_nafah", "Склад снабжения (Нафах)", "blue", "Nafah"),
          ("blue_depot_tiberias", "Склад снабжения (Тверия)", "blue", "Tiberias"),
          ("red_depot_kiswah", "Склады снабжения сирийской армии (Кисве)", "red", "Kiswah"),
          ("red_depot_katana", "Склад снабжения (Катана)", "red", "Katana"),
          ("red_depot_sanamayn", "Склад снабжения (Санамейн)", "red", "Sanamayn"),
          ("red_depot_tartus", "Порт и склады (Тартус)", "red", "Tartus"),
          ("blue_depot_haifa", "Порт и склады (Хайфа)", "blue", "Haifa")]
NAVAL = [   # флот 1973: бой у Латакии (6-7.10) - израильские катера 'Сааръ' (в DCS La Combattante IIa - тот же тип,
    # Сааръ 3 построен по проекту La Combattante II) против сирийских 'Оса' и 'Комар' (в DCS Type 021-1 - копия 'Осы');
    # израильские катера - 'Габриэль' и РЭБ (quality 1.5, ecm 0.97: у Латакии и Балтима ни одного попадания 'Термитов' - ОЦЕНКА;
    # при 16 ракетах залпа шанс хотя бы одного попадания ~13%: потеря катера возможна, но редка)
    ("blue_saar", "Катера ВМС Израиля 'Сааръ' (Хайфа)", "blue", 32.86, 34.92,
     [("La_Combattante_II", "boat", "INS Reshef"), ("La_Combattante_II", "boat", "INS Gaash"), ("La_Combattante_II", "boat", "INS Mivtach"),
      ("La_Combattante_II", "boat", "INS Miznak"), ("La_Combattante_II", "boat", "INS Hanit")],
     [{"day": 1, "to": {"lat": 35.50, "lon": 35.65}, "until_day": 2}], 1.5, 0.97),
    ("red_osa_latakia", "Ракетные катера ВМС Сирии (Латакия)", "red", 35.52, 35.70,
     [("Type_021_1", "boat", "Катер пр. 205 'Оса' №1"), ("Type_021_1", "boat", "Катер пр. 205 'Оса' №2"),
      ("Type_021_1", "boat", "Катер пр. 183Р 'Комар' №1"), ("Type_021_1", "boat", "Катер пр. 183Р 'Комар' №2")], None, None),
    ("red_osa_tartus", "Ракетные катера ВМС Сирии (Тартус)", "red", 34.92, 35.80,
     [("Type_021_1", "boat", "Катер пр. 205 'Оса' №3"), ("Type_021_1", "boat", "Катер пр. 205 'Оса' №4")], None, None),
    ("red_convoy_tartus", "Советские транспорты (морской мост в Тартус)", "red", 34.95, 35.40,
     [("Dry_cargo_ship_1", "transport", "Транспорт №1"), ("Dry_cargo_ship_2", "transport", "Транспорт №2")], None, None),
    ("blue_convoy_haifa", "Транспорты снабжения (Хайфа)", "blue", 32.90, 34.70,
     [("HandyWind", "transport", "Транспорт ZIM №1"), ("Dry_cargo_ship_1", "transport", "Транспорт ZIM №2")], None, None),
]
SEA_LANES = [("lane_tartus", "red", "Tartus", "red_convoy_tartus", 300), ("lane_haifa", "blue", "Haifa", "blue_convoy_haifa", 300)]
BRIDGES = [
    {"id": "br_bnot_yaakov", "name": "Мост Бнот-Яаков через Иордан", "lat": 33.003, "lon": 35.628,
     "links": [["RoshPina", "BnotYaakov"]], "source": "по памяти - проверить (зонд карты)"},
    {"id": "br_arik", "name": "Мост Арик через Иордан", "lat": 32.878, "lon": 35.628,
     "links": [["Tiberias", "ArikBridge"]], "source": "по памяти - проверить (зонд карты)"},
]

AIR = [   # (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
    ("i_f4_rd", "69-я и 107-я эскадрильи (F-4E 'Курнас')", "blue", "fighter_bomber", "F_4E_45MC", "Ramat David", 36, 500, ""),
    ("i_f4_hz", "119-я и 201-я эскадрильи (F-4E 'Курнас')", "blue", "fighter_bomber", "F_4E_45MC", "Hatzor", 36, 500, ""),
    ("i_f4_tn", "Эскадрильи F-4E (Тель-Ноф)", "blue", "fighter_bomber", "F_4E_45MC", "Tel Nof", 24, 500, ""),
    ("i_a4_hz", "Эскадрильи A-4E/H 'Скайхок' (102, 109, 110)", "blue", "fighter_bomber", "A_4E_C", "Hatzerim", 50, 400,
     "мод A-4E-C: без мода части в кампании нет"),
    ("i_a4_rd", "Эскадрильи A-4 'Скайхок' (115, 116, 140)", "blue", "fighter_bomber", "A_4E_C", "Ramat David", 40, 400,
     "мод A-4E-C: без мода части в кампании нет"),
    ("i_nesher", "101-я, 113-я, 117-я эскадрильи ('Нешер', 'Мираж' IIICJ)", "blue", "fighter", "Mirage_F1CE", "Hatzor", 60, 450,
     "Нешер/Мираж III - Mirage F1CE"),
    ("i_ch53", "114-я эскадрилья (CH-53)", "blue", "transport_helo", "CH_53E", "Eyn Shemer", 8, 200, "CH-53D - CH-53E"),
    ("i_uh1", "Вертолётные эскадрильи (Белл 205)", "blue", "transport_helo", "UH_1H", "Rosh Pina", 12, 150, ""),
    ("s_mig21_dum", "Истребительные эскадрильи (МиГ-21ПФМ/МФ)", "red", "fighter", "MiG_21Bis", "Al-Dumayr", 40, 250,
     "МиГ-21ПФМ/МФ - МиГ-21бис"),
    ("s_mig21_kh", "Истребительные эскадрильи (МиГ-21МФ)", "red", "fighter", "MiG_21Bis", "Khalkhalah", 30, 250, ""),
    ("s_mig21_nas", "Истребительная эскадрилья (МиГ-21)", "red", "fighter", "MiG_21Bis", "An Nasiriyah", 20, 250, ""),
    ("s_mig17", "Истребительно-бомбардировочные эскадрильи (МиГ-17Ф)", "red", "fighter_bomber", "MiG_15bis", "Marj Ruhayyil", 40, 200,
     "МиГ-17 - МиГ-15бис"),
    ("s_su7", "Истребительно-бомбардировочные эскадрильи (Су-7БМК)", "red", "fighter_bomber", "Su_17M4", "Sayqal", 30, 250,
     "Су-7БМК - Су-17М4"),
    ("s_mi8", "Вертолётная эскадрилья (Ми-8)", "red", "transport_helo", "Mi_8MT", "Mezzeh", 16, 150, ""),
]
MOD_TYPES = {"A_4E_C": "a4ec"}
AD_TEMPLATES = {
    # объектовая ПВО тыла Сирии 1973 (аэродромы, объекты): ЗУ-23 на грузовиках и ПЗРК ('Стрела-2' - в DCS 'Игла',
    # ДОПУЩЕНИЕ); 'Стрела-1' и ЗСУ-23-4 - войсковая ПВО дивизий (SY_ADD), не тыла (ОЦЕНКА)
    "red": {"short": [{"name": "ЗУ-23, ПЗРК", "composition": [("Ural_375_ZU_23", "launcher", 2), ("SA-18 Igla manpad", "launcher", 2)]}]},
    "blue": {"short": [{"name": "Вулкан", "composition": [("Vulcan", "launcher", 4)]}]},
}
AD_AF_OFFSET_KM = 1.5
QUALITY_BLUE = 2.5   # ОЦЕНКА: выучка израильских танкистов и огонь с подготовленных позиций (потери танков ~4:1, Herzog)


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
    assert seen == set(places), set(places) - seen
    airbases, af_pos = {}, {}
    for side, names in AIRBASES.items():
        for n in names:
            assert n in terrain.airports, n
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
        "_about": "Голаны, октябрь 1973. Генерирован tools/gen_golan73.py. Координаты - ОЦЕНКИ (+-2 км). Стороны - "
                  "6.10.1973 до начала войны (Пурпурная линия 1967 г.).",
        "theatre": "syria", "places": places, "airbases": airbases, "links": [list(l) for l in LINKS],
        "supply_entry": SUPPLY_ENTRY, "off_limits": OFF_LIMITS,
        "axes": {k: v["title"] for k, v in {**AXES, **BLUE_AXES}.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()},
                       "blue": {k: v["objectives"] for k, v in BLUE_AXES.items()}},
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": BRIDGES, "ad_sites": sites,
        "sea_lanes": [{"id": i, "side": sd, "port": pt, "convoy": cv, "t_per_day": t} for i, sd, pt, cv, t in SEA_LANES],
        "naval_bases": {"blue": [{"name": "Хайфа", "lat": 32.83, "lon": 35.00}], "red": [{"name": "Тартус", "lat": 34.90, "lon": 35.86}, {"name": "Латакия", "lat": 35.52, "lon": 35.76}]},
        "asm_stock": {"blue": {"count": 0, "per_day": 0, "note": "у ВВС Израиля 1973 г. авиационных ПКР нет ('Габриэль' - корабельная)"}, "red": {"count": 0, "per_day": 0, "note": "у ВВС Сирии 1973 г. авиационных ПКР нет"}},   # запас авиационных ПКР сторон (naval.use_air_asm; ОЦЕНКА)
    }
    (DATA / "sector_golan73.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")
    units = []
    for uid, name, side, place, cmp_, ad, day, axis in GROUND:
        u = {"id": uid, "name": name, "side": side, "role": "maneuver", "state": "defend" if day <= 1 else "pending",
             "route": [place], "progress_km": 0.0, "march_kmh": 25, "daily_advance_km": 15,
             "composition": cmp_, "source": SRC + "; состав - ОЦЕНКА", "estimate": True}
        if day > 1:
            u["arrives_day"], u["arrives_jitter"] = day, 0
        if axis:
            u["axis"] = axis
        if side == "blue":
            u["quality"] = QUALITY_BLUE
        units.append(u)
        if ad:
            units.append({"id": f"{uid}_pvo", "name": f"Войсковая ПВО: {name}", "side": side, "role": "sam_short",
                          "attached_to": uid, "state": u["state"],
                          "composition": [{"type": t, "count": c, "role": "launcher"} for t, c in ad.items()],
                          "source": "ОЦЕНКА", "estimate": True})
    for uid, name, side, place, men in AIRMOBILE:
        units.append({"id": uid, "name": name, "side": side, "role": "air_assault", "state": "defend", "order": "reserve",
                      "air_mobile": True, "home": place, "men": men, "route": [place], "progress_km": 0.0, "march_kmh": 5,
                      "daily_advance_km": 10, "composition": [{"type": "Paratrooper_AKS_74", "count": 20, "role": "infantry"},
                                                              {"type": "Paratrooper_RPG_16", "count": 5, "role": "infantry"}],
                      "source": SRC + "; рота - ОЦЕНКА", "estimate": True})
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from naval_common import group
    for uid, name, side, la, lo, ships, orders, q, *ecm in NAVAL:
        units.append(group(uid, name, side, la, lo, ships, source=SRC + "; состав и место - ОЦЕНКА", orders=orders, quality=q,
                           ecm=ecm[0] if ecm else None))
    for sid, name, side, role, cmp_, la, lo in SAMS:
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed", "fixed": True,
                      "pos": {"lat": la, "lon": lo}, "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        bid = base.lower().replace(" ", "_").replace("-", "_")
        assert bid in airbases, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": bid, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True, **({"mod": MOD_TYPES[typ]} if typ in MOD_TYPES else {}),
                      # F-4E ВВС Израиля 1973: в основном глубокие удары и подавление ЗРК, CAS у переднего края - чаще A-4
                      # (распределение задач ВВС Израиля): CAS 'Фантому' - только если нет A-4 (штраф к выбору, не
                      # запрет; вылет вручную - можно); контейнеры РЭБ - были (ecm_pods по умолчанию)
                      **({"task_penalty": {"cas_contact": 1.0, "cas_helo": 1.0}} if typ == "F_4E_45MC" else {})})
    oob = {
        "_about": "Октябрьская война 1973 г., Голанский фронт (Израиль - Сирия, Ирак, Иордания). tools/gen_golan73.py.",
        "theatre": "syria",
        "preset": {"title": "Октябрь 1973: Голаны", "year": 1973, "date": "1973-10-06"},
        "date": "1973-10-06", "doctrine": {"red": "arab", "blue": "iaf73"}, "countries": {"red": "Syria", "blue": "Israel"}, "units": units,
        "variants": [{"name": "base", "title": "Октябрь 1973: Голаны",
                      "posture": {"red": "offense", "blue": "defense"},
                      "posture_days": [{"from_day": 6, "red": "defense", "blue": "offense"}],
                      "_about_posture": "Сирия наступает 6-9.10; с 11.10 (6-й день) - контрнаступление Израиля на Сасу",
                      "task_rules": {"blue": {
                          "strike_factory": {"off": True, "why": "по промышленности Сирии в первые дни не били"},
                          "strike_airfield": {"from_day": 3, "why": "удары по аэродромам Сирии - с 8.10"}}}}],
        "replacements": {"air_per_day": 2, "note": "ОЦЕНКА; с 14.10 - американский воздушный мост (Nickel Grass)"},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]} for v in vs]
                                for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_not_included": "Синайский фронт (другая карта), 'Супер-Мистэры', Су-20, Хантеры Ирака, марокканская бригада, "
                         "наземный удар 'Голани' по Хермону 21-22.10, ракеты 'Луна' (FROG) по Израилю.",
    }
    (DATA / "oob_golan73.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пунктов {len(places)}, связей {len(LINKS)}, аэродромов {len(airbases)}, частей {len(GROUND)}, "
          f"ЗРК {len(SAMS)}, авиачастей {len(AIR)}")


if __name__ == "__main__":
    main()

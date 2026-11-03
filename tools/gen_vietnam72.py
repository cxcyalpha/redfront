"""Генератор сценария "Вьетнам, апрель 1972" на карте DCS Syria (условная география): data/sector_vietnam72.json,
data/oob_vietnam72.json.

Сценарий: Пасхальное наступление ДРВ (с 30.03.1972) через демилитаризованную зону на Куангчи и Хюэ и воздушная
кампания США: "Freedom Train" (с 6.04 - удары по ДРВ южнее 20-й параллели), "Freedom Porch Bravo" (16.04 - B-52 по
Хайфону), "Лайнбэкер" (с 10.05 - Ханой и Хайфон открыты для ударов). Старт - 6 апреля 1972 г.

Условная география (не перенос театра: масштаб боёв, не карта): Северный Вьетнам - побережье Сирии (Ханой - Хама,
Хайфон - Латакия, Тханьхоа - Баниас, Винь - Тартус, Донгхой - Хамидия), ДМЗ (река Бенхай) - река Нахр-эль-Кабир на
границе Сирии и Ливана, Южный Вьетнам - север Ливана (Донгха, Куангчи - Аккар, Хюэ - Триполи, Дананг - аэропорт
Бейрута). Тонкинский залив ("Янки-стейшн") - море у Тартуса. Таиланд - юг Турции (Хатай, Инджирлик), Гуам и У-Тапао
- Кипр (Акротири). Расстояния короче вьетнамских (ОЦЕНКА: вдвое); соотношение "авианосец - побережье - глубина"
сохранено.

Источники (общие, проверять): M. Michel, "Clashes: Air Combat over North Vietnam 1965-1972" (1997); D. Andrade,
"Trial by Fire: The 1972 Easter Offensive" (1995); W. Momyer, "Airpower in Three Wars" (1978); A. Lavalle (ред.),
"Airpower and the 1972 Spring Invasion" (USAF Southeast Asia Monograph, 1976). Составы и числа - ОЦЕНКИ по порядку
величины. Типы DCS: F-4J/B ВМС - F-14A (палубного F-4 в DCS нет; анахронизм); A-6A - A-6E (ИИ-юнит DCS, redfront.mods.a6e); A-7E - F/A-18C; KA-6D - S-3B Tanker;
F-105G "Дикая ласка" - F-4E; HH-53 - CH-53E; AH-1G - AH-1W; МиГ-21ПФ/МФ - МиГ-21бис; МиГ-17 - МиГ-15бис; J-6 - МиГ-19П;
Т-54 - Т-55; ПТ-76 есть; М-48 - М-60; Стрела-2 - Игла; АК, М16 - пехота DCS (Infantry AK, Soldier M4).
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Michel 'Clashes' / Andrade 'Trial by Fire' / Lavalle (USAF 1976), по памяти - проверить"

PLACES = {   # условное имя: (широта, долгота, сторона 6.04.1972) - точка на карте Syria (что это на карте - в комментарии)
    # Северный Вьетнам
    "Hanoi": (35.135, 36.750, "red"),          # Хама
    "ThaiNguyen": (35.250, 36.570, "red"),     # Мхарде
    "HaiDuong": (35.445, 36.060, "red"),       # Кардаха
    "Haiphong": (35.520, 35.790, "red"),       # Латакия
    "NamDinh": (35.360, 35.930, "red"),        # Джебла
    "PhuLy": (35.070, 36.340, "red"),          # Масьяф
    "ThanhHoa": (35.180, 35.950, "red"),       # Баниас
    "Vinh": (34.890, 35.890, "red"),           # Тартус
    "NinhBinh": (34.730, 36.710, "red"),       # Хомс
    "DongHoi": (34.720, 35.940, "red"),        # Хамидия
    "MuGia": (34.670, 36.260, "red"),          # Телль-Калах (перевал Мугиа - начало "Тропы Хо Ши Мина")
    # ДМЗ и Южный Вьетнам (север Ливана); занятое ДРВ к 6.04
    "GioLinh": (34.630, 35.985, "red"),        # Арида
    "CampCarroll": (34.560, 36.170, "red"),    # Аккар (лагерь Кэррол сдан 2.04)
    "KheSanh": (34.500, 36.400, "red"),        # Хермель-север
    "ALuoi": (34.330, 36.250, "red"),          # долина Ашау
    "DongHa": (34.555, 35.990, "blue"),        # Аабде - Кляят
    "QuangTri": (34.545, 36.080, "blue"),      # Халба
    "Hue": (34.436, 35.850, "blue"),           # Триполи
    "Bastogne": (34.350, 36.000, "blue"),      # огневая база "Бастонь" (горы Згарты)
    "PhuBai": (34.255, 35.660, "blue"),        # Батрун
    "HaiVan": (34.120, 35.650, "blue"),        # Библ (перевал Хайван)
    "DaNang": (33.900, 35.520, "blue"),        # Бейрут
}
LINKS = [
    ("Hanoi", "ThaiNguyen"), ("Hanoi", "PhuLy"), ("Hanoi", "NinhBinh"), ("ThaiNguyen", "HaiDuong"), ("HaiDuong", "Haiphong"),
    ("HaiDuong", "NamDinh"), ("Haiphong", "NamDinh"), ("NamDinh", "ThanhHoa"), ("PhuLy", "ThanhHoa"), ("ThanhHoa", "Vinh"),
    ("Vinh", "DongHoi"), ("NinhBinh", "MuGia"), ("Vinh", "MuGia"), ("DongHoi", "GioLinh"), ("MuGia", "CampCarroll"),
    ("MuGia", "KheSanh"), ("KheSanh", "CampCarroll"), ("KheSanh", "ALuoi"), ("GioLinh", "DongHa"), ("CampCarroll", "DongHa"),
    ("CampCarroll", "QuangTri"), ("DongHa", "QuangTri"), ("QuangTri", "Hue"), ("DongHa", "Hue"), ("ALuoi", "Bastogne"),
    ("Bastogne", "Hue"), ("Hue", "PhuBai"), ("PhuBai", "HaiVan"), ("HaiVan", "DaNang"),
]
NORTH = ["Hanoi", "ThaiNguyen", "HaiDuong", "Haiphong", "NamDinh", "PhuLy", "ThanhHoa", "Vinh", "NinhBinh", "DongHoi", "MuGia"]
SUPPLY_ENTRY = {"red": ["Hanoi", "ThaiNguyen"], "blue": ["DaNang"]}
OFF_LIMITS = {"blue": NORTH, "red": []}   # наземные войска США и Южного Вьетнама на Север не наступают
ZONES = [{"places": ["Hanoi", "ThaiNguyen", "HaiDuong", "Haiphong"], "until_day": 35,
          "why": "Ханой и Хайфон закрыты для ударов до 'Лайнбэкера' (10.05.1972); 'Freedom Train' - только юг ДРВ"}]

AIRBASES = {
    "red": ["Hama", "Bassel Al-Assad", "Abu al-Duhur", "Al Qusayr", "Shayrat"],   # Ной-Бай, Кеп, Йенбай, Куанглан, Байтхыонг
    "blue": ["Beirut-Rafic Hariri", "Rene Mouawad", "Hatay", "Incirlik", "Akrotiri"],   # Дананг, Фубай, Удорн, Корат, У-Тапао
}
BASE_ALIAS = {"Hama": "Ной-Бай (Хама)", "Bassel Al-Assad": "Кеп (Басиль-Асад)", "Abu al-Duhur": "Йенбай (Абу-аль-Духур)",
              "Al Qusayr": "Куанглан (Эль-Кусайр)", "Shayrat": "Байтхыонг (Шайрат)", "Beirut-Rafic Hariri": "Дананг (Бейрут)",
              "Rene Mouawad": "Фубай (Кляят)", "Hatay": "Удорн (Хатай)", "Incirlik": "Корат (Инджирлик)",
              "Akrotiri": "У-Тапао (Акротири)"}
CARRIERS = {   # 'Янки-стейшн': авианосцы - реальные корабли DCS (имя, класс, широта, долгота, TACAN, позывной, ICLS, МГц, группа).
    # Исторически в апреле 1972 г. - Kitty Hawk, Constellation, Coral Sea, Hancock: в DCS их нет. Вместо них - USS Forrestal
    # (CV-59; сам воевал у Вьетнама в 1967 г.) и USS Carl Vinson (CVN-70; в строю с 1982 г. - АНАХРОНИЗМ, ДОПУЩЕНИЕ).
    # Позиции - ОЦЕНКА.
    "cv63": ("USS Forrestal (CV-59)", "Forrestal", 35.05, 35.45, 59, "FOR", 3, 127.5, "blue_csg_forrestal"),
    "cv64": ("USS Carl Vinson (CVN-70)", "VINSON", 34.80, 35.40, 70, "VIN", 4, 128.5, "blue_csg_vinson"),
}
from naval_common import from_template as T   # noqa: E402
NAVAL = [   # корабельные группы: охранение - корабли DCS (Ticonderoga, Perry - в 1972 г. ещё не в строю: вместо крейсеров
    # Belknap/Leahy и эсминцев - ДОПУЩЕНИЕ), имена - реальные корабли класса
    ("blue_csg_forrestal", "Авианосная ударная группа USS Forrestal", "blue", 35.05, 35.45,
     T("us_csg_1972", ("Forrestal", "carrier", "USS Forrestal (CV-59)"),
       ["USS Sterett (DLG-31)", "USS Higbee (DD-806)", "USS Lloyd Thomas (DD-764)"]), "CSG 59"),
    ("blue_csg_vinson", "Авианосная ударная группа USS Carl Vinson", "blue", 34.80, 35.40,
     T("us_csg_1972", ("VINSON", "carrier", "USS Carl Vinson (CVN-70)"),
       ["USS Biddle (DLG-34)", "USS Berkeley (DDG-15)", "USS Buchanan (DDG-14)"]), "CSG 70"),
    ("red_fac_haiphong", "Торпедные катера ВМС ДРВ (Хайфон)", "red", 35.55, 35.70,
     [("Type_021_1", "boat", "Катер №1"), ("Type_021_1", "boat", "Катер №2"), ("Type_021_1", "boat", "Катер №3")],
     "пр. 183 (P-6) и пр. 123 - в DCS Type 021-1; 19.04.1972 у Донгхоя атаковали эсминцы США (с МиГ-17)"),
    ("red_convoy_haiphong", "Советские транспорты у Хайфона", "red", 35.62, 35.60,
     [("Dry_cargo_ship_1", "transport", "Транспорт №1"), ("Dry_cargo_ship_2", "transport", "Транспорт №2")],
     "морской подвоз ДРВ: удары по судам СССР были запрещены (с 9.05 - минирование Хайфона)"),
    ("blue_convoy_danang", "Транспорты снабжения (Дананг)", "blue", 33.95, 35.30,
     [("HandyWind", "transport", "SS Transcolumbia"), ("Dry_cargo_ship_1", "transport", "SS Green Wave")], ""),
]
SEA_LANES = [   # морской подвоз: (id, сторона, порт - пункт со складом, конвой - группа флота, т/сутки - ОЦЕНКА)
    ("lane_haiphong", "red", "Haiphong", "red_convoy_haiphong", 400),
    ("lane_danang", "blue", "DaNang", "blue_convoy_danang", 500),
]
AXES = {"dmz": {"title": "ДМЗ: Жолинь - Донгха - Куангчи - Хюэ", "objectives": ["DongHa", "QuangTri", "Hue"]},
        "west": {"title": "Запад: Ашау - Бастонь - Хюэ", "objectives": ["Bastogne", "Hue"]}}


def comp(*rows):
    return [{"type": t, "count": c, "role": r} for t, c, r in rows if c > 0]

# ВНА 1972: пехотные дивизии (~8-10 тыс. человек) с приданными танками и 122-мм реактивной артиллерией; ПВО - много
# стволов (ДШК, ЗУ, ЗСУ-57) и Стрела-2. Фигура пехоты в DCS - ~4 человека (ОЦЕНКА масштаба, как assault.men).
NVA_DIV = comp(("Infantry AK", 320, "infantry"), ("Soldier RPG", 60, "infantry"), ("T_55", 8, "MBT"), ("PT_76", 4, "MBT"),
               ("GAZ-66", 20, "truck"), ("Grad-URAL", 6, "MRL"))
NVA_ARM = comp(("T_55", 50, "MBT"), ("PT_76", 30, "MBT"), ("Infantry AK", 40, "infantry"))           # 202-й/203-й тп
NVA_ADD = {"ZSU_57_2": 4, "ZU_23_Emplacement": 6, "HL_DSHK": 8, "SA-18 Igla manpad": 6}            # Стрела-2 - Игла
# АРВН: пехотные дивизии и бригады морской пехоты на M113, танки M48 - в бронечастях
ARVN_DIV = comp(("Soldier M4", 320, "infantry"), ("Soldier M249", 40, "infantry"), ("M-113", 40, "APC"), ("M-60", 10, "MBT"))
ARVN_MAR = comp(("Soldier M4", 140, "infantry"), ("Soldier M249", 20, "infantry"), ("M-113", 12, "APC"))
ARVN_ARM = comp(("M-60", 40, "MBT"), ("M-113", 20, "APC"))                                                # 20-й тб (М-48)
GROUND = [   # (id, имя, сторона, пункт, состав, ПВО, день ввода, ось)
    ("red_308", "308-я дивизия ВНА", "red", "CampCarroll", NVA_DIV, NVA_ADD, 1, "dmz"),
    ("red_304", "304-я дивизия ВНА", "red", "KheSanh", NVA_DIV, NVA_ADD, 1, "dmz"),
    ("red_324b", "324B дивизия ВНА", "red", "ALuoi", NVA_DIV, NVA_ADD, 1, "west"),
    ("red_202", "202-й и 203-й танковые полки ВНА", "red", "GioLinh", NVA_ARM, NVA_ADD, 1, "dmz"),
    ("red_320b", "320B дивизия ВНА", "red", "DongHoi", NVA_DIV, NVA_ADD, 8, "dmz"),
    ("red_325", "325-я дивизия ВНА", "red", "MuGia", NVA_DIV, NVA_ADD, 20, "west"),
    ("blue_3div", "3-я дивизия АРВ", "blue", "QuangTri", ARVN_DIV, {}, 1, None),
    ("blue_258", "258-я бригада морской пехоты Южного Вьетнама", "blue", "DongHa", ARVN_MAR, {}, 1, None),
    ("blue_20tk", "20-й танковый батальон АРВ (М-48)", "blue", "DongHa", ARVN_ARM, {}, 1, None),
    ("blue_147", "147-я бригада морской пехоты Южного Вьетнама", "blue", "QuangTri", ARVN_MAR, {}, 1, None),
    ("blue_1div", "1-я дивизия АРВ", "blue", "Bastogne", ARVN_DIV, {}, 1, None),
    ("blue_369", "369-я бригада морской пехоты Южного Вьетнама", "blue", "Hue", ARVN_MAR, {}, 1, None),
    ("blue_1abde", "1-я бронетанковая бригада АРВ", "blue", "Hue", ARVN_ARM, {}, 1, None),
    ("blue_abn", "Воздушно-десантная дивизия Южного Вьетнама", "blue", "DaNang", ARVN_MAR, {}, 3, None),
]
AIRMOBILE = [   # (id, имя, пункт, человек) - аэромобильные роты АРВН в резерве (рейнджеры, десантники): ОЦЕНКА численности
    ("blue_rgr21", "Рота 21-го батальона рейнджеров АРВН", "Hue", 80),
    ("blue_rgr39", "Рота 39-го батальона рейнджеров АРВН", "PhuBai", 80),
    ("blue_abn2", "Рота 2-го воздушно-десантного батальона АРВН", "DaNang", 80),
]
S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 6)]
# 361-я, 363-я, 365-я дивизии ПВО: дивизионы С-75 (места - ОЦЕНКА, по районам: Ханой - Хайфон - юг ДРВ - у ДМЗ)
SAM_POS = {"Ханой": [(35.20, 36.70), (35.08, 36.82), (35.18, 36.85), (35.06, 36.66), (35.22, 36.78), (35.12, 36.60)],
           "Хайфон": [(35.55, 35.85), (35.47, 35.82), (35.58, 35.95)],
           "Тханьхоа": [(35.15, 36.00), (35.22, 35.98)],
           "Винь": [(34.92, 35.95), (34.86, 35.97)],
           "Донгхой": [(34.70, 36.02)]}
SAMS = [(f"red_s75_{i}_{k}", f"Дивизион С-75 ({area}) №{k}", "red", "sam_medium", S75, la, lo)
        for i, (area, pos) in enumerate(SAM_POS.items()) for k, (la, lo) in enumerate(pos, 1)]
DEPOTS = [("red_depot_haiphong", "Нефтебаза и порт Хайфона", "red", "Haiphong"),
          ("red_depot_hanoi", "Железнодорожный узел Ханоя (Йенвьен)", "red", "Hanoi"),
          ("red_depot_vinh", "Склады и перевалка Винь", "red", "Vinh"),
          ("red_depot_donghoi", "Перевалка Донгхой", "red", "DongHoi"),
          ("blue_depot_danang", "Склады Дананга", "blue", "DaNang"),
          ("blue_depot_hue", "Склады Хюэ", "blue", "Hue")]
BRIDGES = [   # мосты - места ОЦЕНКА (середина участка дороги)
    {"id": "br_thanhhoa", "name": "Мост Тханьхоа (Хамронг)", "lat": 35.27, "lon": 35.94, "links": [["NamDinh", "ThanhHoa"]],
     "source": "условно: середина участка Намдинь - Тханьхоа"},
    {"id": "br_doumer", "name": "Мост Думера (Ханой)", "lat": 35.19, "lon": 36.66, "links": [["Hanoi", "ThaiNguyen"]],
     "source": "условно: середина участка Ханой - Тхайнгуен"},
    {"id": "br_dongha", "name": "Мост Донгха", "lat": 34.59, "lon": 35.99, "links": [["GioLinh", "DongHa"]],
     "source": "условно: середина участка Жолинь - Донгха"},
]
F4_NOTE = "F-4J/B - F-14A: палубного F-4 в DCS нет (F-4E с авианосца не летает), F-14 - анахронизм (в строю с 1974)"
AIR = [   # (id, имя, сторона, роль, тип, база, число, радиус км, примечание)
    ("us_vf114", "VF-114, VF-213 (F-4J, Forrestal)", "blue", "fighter", "F_14A_135_GR_Early", "cv63", 24, 500, F4_NOTE),
    ("us_va_kh", "VA-192, VA-195 (A-7E), Forrestal", "blue", "fighter_bomber", "FA_18C_hornet", "cv63", 24, 500, "A-7E - F/A-18C"),
    ("us_va52", "VA-52 (A-6A, Forrestal)", "blue", "fighter_bomber", "A6E", "cv63", 12, 600, "A-6A - A-6E"),
    ("us_e2_kh", "VAW-114 (E-2B)", "blue", "awacs", "E_2C", "cv63", 4, 1000, "E-2B - E-2C"),
    ("us_ka6_kh", "KA-6D (Forrestal)", "blue", "tanker", "S_3B_Tanker", "cv63", 4, 800, "KA-6D - S-3B Tanker"),
    ("us_vf96", "VF-92, VF-96 (F-4J, Carl Vinson)", "blue", "fighter", "F_14A_135_GR_Early", "cv64", 24, 500, F4_NOTE),
    ("us_va_con", "VA-146, VA-147 (A-7E), Carl Vinson", "blue", "fighter_bomber", "FA_18C_hornet", "cv64", 24, 500, "A-7E - F/A-18C"),
    ("us_va165", "VA-165 (A-6A, Carl Vinson)", "blue", "fighter_bomber", "A6E", "cv64", 12, 600, "A-6A - A-6E"),
    ("us_e2_con", "VAW-116 (E-2B)", "blue", "awacs", "E_2C", "cv64", 4, 1000, "E-2B - E-2C"),
    ("us_366", "366-е тактическое крыло (F-4E, Дананг)", "blue", "fighter_bomber", "F_4E", "Beirut-Rafic Hariri", 36, 500, ""),
    ("us_432", "432-е разведывательное крыло (F-4D/E, Удорн): MiGCAP", "blue", "fighter", "F_4E", "Hatay", 36, 600, "F-4D - F-4E"),
    ("us_8tfw", "8-е тактическое крыло 'Волчья стая' (F-4D, Убон): управляемые бомбы", "blue", "fighter_bomber", "F_4E",
     "Incirlik", 36, 600, "F-4D - F-4E"),
    ("us_ww", "17-я эскадрилья 'Дикая ласка' (F-105G, Корат)", "blue", "fighter_bomber", "F_4E", "Incirlik", 12, 600,
     "F-105G - F-4E"),
    ("us_kc135", "KC-135 (Таиланд)", "blue", "tanker", "KC_135", "Incirlik", 4, 2000, ""),
    ("us_b52", "B-52D/G (У-Тапао, Гуам): 'Арк Лайт', 'Freedom Porch'", "blue", "bomber", "B_52H", "Akrotiri", 24, 2000,
     "B-52D/G - B-52H"),
    ("us_37arrs", "37-я спасательная эскадрилья (HH-53, Дананг)", "blue", "transport_helo", "CH_53E", "Beirut-Rafic Hariri", 6,
     200, "HH-53 - CH-53E"),
    ("us_ah1", "Армейские AH-1G (Фубай)", "blue", "attack_helo", "AH_1W", "Rene Mouawad", 24, 120,
     "AH-1G - AH-1W; два кавалерийских эскадрона армии США в I корпусе - ОЦЕНКА"),
    ("us_uh1", "Вертолётные роты армии США (UH-1H, Дананг)", "blue", "transport_helo", "UH_1H", "Beirut-Rafic Hariri", 24, 150,
     "1-я авиационная бригада: подъём рот АРВН"),
    ("vn_uh1", "ВВС Южного Вьетнама (UH-1H, Фубай)", "blue", "transport_helo", "UH_1H", "Rene Mouawad", 16, 150, ""),
    ("r_921", "921-й истребительный полк 'Красная звезда' (МиГ-21ПФ/МФ, Ной-Бай)", "red", "fighter", "MiG_21Bis", "Hama", 30, 250,
     "МиГ-21ПФ/МФ - МиГ-21бис"),
    ("r_927", "927-й истребительный полк 'Ламшон' (МиГ-21, Кеп)", "red", "fighter", "MiG_21Bis", "Bassel Al-Assad", 24, 250, ""),
    ("r_923", "923-й истребительный полк 'Йенбай' (МиГ-17, Кеп)", "red", "fighter", "MiG_15bis", "Bassel Al-Assad", 24, 200,
     "МиГ-17 - МиГ-15бис"),
    ("r_925", "925-й истребительный полк (J-6/МиГ-19, Йенбай)", "red", "fighter", "MiG_19P", "Abu al-Duhur", 20, 250, "J-6 - МиГ-19П"),
    ("r_fwd", "Передовая группа МиГ-21 (Куанглан)", "red", "fighter", "MiG_21Bis", "Al Qusayr", 8, 200, ""),
]
AD_TEMPLATES = {   # ствольная зенитка ДРВ - самая плотная ПВО эпохи: у каждого моста, склада и аэродрома
    "red": {"short": [{"name": "КС-19, С-60, ЗУ-23", "composition": [("KS_19", "launcher", 2), ("S_60_Type59_Artillery", "launcher", 4),
                                                                      ("ZU_23_Emplacement", "launcher", 2)]}]},
}


def bid_of(n):
    return n.lower().replace(" ", "_").replace("-", "_")


def main() -> None:
    from dcs.terrain import Syria
    terrain = Syria()
    places = {n: {"lat": la, "lon": lo, "estimate": True, "side": s} for n, (la, lo, s) in PLACES.items()}
    adj = {n: set() for n in places}
    for a, b in LINKS:
        assert a in places and b in places, (a, b)
        adj[a].add(b); adj[b].add(a)
    seen, todo = set(), ["Hanoi"]
    while todo:
        x = todo.pop()
        if x not in seen:
            seen.add(x); todo += adj[x]
    assert seen == set(places), set(places) - seen
    airbases = {}
    for side, names in AIRBASES.items():
        for n in names:
            assert n in terrain.airports, n
            airbases[bid_of(n)] = {"name": n, "airport": n, "side": side, "military": True, "alias": BASE_ALIAS[n]}
    af_ll = {bid: (lambda ll: (ll.lat, ll.lng))(terrain.airports[b["name"]].position.latlng()) for bid, b in airbases.items()}
    carriers = {cid: {"name": n, "side": "blue", "ship": t, "lat": la, "lon": lo, "tacan": tc, "tacan_id": tid,
                      "icls": icls or None, "freq": f, "naval": nv, "estimate": True}
                for cid, (n, t, la, lo, tc, tid, icls, f, nv) in CARRIERS.items()}
    sector = {
        "_about": "Вьетнам, апрель 1972 - условная география на карте Syria (см. tools/gen_vietnam72.py). Координаты - точки "
                  "карты Syria, имена - вьетнамские.",
        "theatre": "syria", "places": places, "airbases": airbases, "carriers": carriers,
        "links": [list(l) for l in LINKS], "supply_entry": SUPPLY_ENTRY, "off_limits": OFF_LIMITS,
        "sea_lanes": [{"id": i, "side": sd, "port": pt, "convoy": cv, "t_per_day": t} for i, sd, pt, cv, t in SEA_LANES],
        "naval_bases": {"red": [{"name": "Хайфон", "lat": 35.53, "lon": 35.76}]},
        "asm_stock": {"blue": {"count": 0, "per_day": 0, "note": "AGM-84 Harpoon - с 1977 г.; 1972 - бомбы (Mk 20 Rockeye)"}, "red": {"count": 0, "per_day": 0, "note": "у ВВС ДРВ ПКР нет: 19.04.1972 - бомбы МиГ-17"}},   # запас авиационных ПКР сторон (naval.use_air_asm; ОЦЕНКА)
        "air_limits": {"blue": [], "red": []},   # авиация бьёт по всему Северу (кроме зон по дням - task_rules _zones)
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()}, "blue": []},
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": BRIDGES,
        "ad_sites": [{"id": f"red_ad_af_{bid}", "name": f"Зенитная артиллерия аэродрома {BASE_ALIAS[b['name']]}", "side": "red",
                      "tier": "short", "covers": f"af_{bid}", "lat": round(af_ll[bid][0] + 0.012, 4), "lon": af_ll[bid][1],
                      "variant": 0, "rule": "ПВО объекта: у каждого аэродрома ДРВ"} for bid, b in airbases.items() if b["side"] == "red"],
    }
    (DATA / "sector_vietnam72.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")
    units = []
    for uid, name, side, place, cmp_, ad, day, axis in GROUND:
        u = {"id": uid, "name": name, "side": side, "role": "maneuver", "state": "defend" if day <= 1 else "pending",
             "route": [place], "progress_km": 0.0, "march_kmh": 20, "daily_advance_km": 8,
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
    for uid, name, place, men in AIRMOBILE:
        units.append({"id": uid, "name": name, "side": "blue", "role": "air_assault", "state": "defend", "order": "reserve",
                      "air_mobile": True, "home": place, "men": men, "route": [place], "progress_km": 0.0, "march_kmh": 5,
                      "daily_advance_km": 10, "composition": [{"type": "Soldier M4", "count": 16, "role": "infantry"},
                                                              {"type": "Soldier M249", "count": 4, "role": "infantry"}],
                      "source": SRC + "; рота - ОЦЕНКА; M16/M60 - в DCS Soldier M4/M249", "estimate": True})
    for sid, name, side, role, cmp_, la, lo in SAMS:
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed", "fixed": True,
                      "pos": {"lat": la, "lon": lo}, "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from naval_common import group
    for uid, name, side, la, lo, ships, note in NAVAL:
        u = group(uid, name, side, la, lo, ships, note="" if note.startswith("CSG") else note, source=SRC + "; состав и место - ОЦЕНКА",
                  abbr=note if note.startswith("CSG") else "")
        if uid == "red_convoy_haiphong":
            u["protected"] = True                # суда СССР - не цель (политика США до минирования)
        units.append(u)
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        b = base if base in carriers else bid_of(base)
        assert b in airbases or b in carriers, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": b, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True, **({"tasks_only": ["csar"]} if uid == "us_37arrs" else {})})
    oob = {
        "_about": "Вьетнам, апрель 1972: Пасхальное наступление и воздушная кампания США (условная география, карта Syria).",
        "theatre": "syria",
        "preset": {"title": "Апрель 1972: Вьетнам, Пасхальное наступление", "year": 1972, "date": "1972-04-06"},
        "date": "1972-04-06", "countries": {"red": "Vietnam", "blue": "USA"}, "doctrine": {"blue": "us72", "red": "vpaf72"}, "units": units,
        "variants": [{"name": "base", "title": "Апрель 1972: 'Freedom Train' и Пасхальное наступление",
                      "posture": {"red": "offense", "blue": "defense"},
                      "task_rules": {"blue": {
                          "_zones": ZONES,
                          "strike_airfield": {"from_day": 35, "why": "аэродромы МиГов - с 'Лайнбэкера' (10.05.1972)"}}}}],
        "replacements": {"air_per_day": 2, "note": "ОЦЕНКА"},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]} for v in vs]
                                for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "point_ad": {"red": [{"type": "KS_19", "role": "launcher", "count": 2}, {"type": "S_60_Type59_Artillery", "role": "launcher", "count": 4},
                             {"type": "ZU_23_Emplacement", "role": "launcher", "count": 2}]},
        "_about_point_ad": "ДРВ: у мостов и складов - зенитная артиллерия 57-100 мм и 23 мм (ОЦЕНКА состава), не ЗРК малой дальности.",
        "_not_included": "A-7E, F-105, F-8, A-1, A-37, AC-130, OV-10 (нет в DCS без модов - замены в source), МиГ-17 (МиГ-15бис), "
                         "Лаос и Камбоджа, минирование Хайфона, флот у побережья (обстрел крейсерами).",
    }
    (DATA / "oob_vietnam72.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    linebacker2(sector, oob)
    print(f"пунктов {len(places)}, авианосцев {len(carriers)}, частей {len(GROUND)}, С-75 {len(SAMS)}, авиачастей {len(AIR)}")


def linebacker2(sector: dict, oob: dict) -> None:
    """'Лайнбэкер-2' (18-29.12.1972): та же условная география, обстановка декабря. Куангчи отбит АРВ (16.09), фронт
    стоит по реке Тхатьхан (стороны в обороне); Ханой, Хайфон и аэродромы МиГов открыты; B-52 - ночью ячейками по три
    (729 вылетов за 11 суток, 15 сбито С-75 - Michel, 'The Eleven Days of Christmas'); палубные 'Альфы' - днём и ночью
    (A-6). Авианосцы декабря (Enterprise, Saratoga, America и др.) в DCS нет - те же Forrestal и Carl Vinson. Числа - ОЦЕНКИ."""
    import copy
    sec, ob = copy.deepcopy(sector), copy.deepcopy(oob)
    sec["_about"] = sec["_about"].replace("апрель", "декабрь") + " Обстановка 18.12.1972 ('Лайнбэкер-2')."
    sec["places"]["QuangTri"]["side"] = "blue"     # Куангчи отбит 16.09.1972
    sec["places"]["DongHa"]["side"] = "red"        # Донгха - у ВНА (фронт по реке Тхатьхан)
    sec["objectives"] = {"red": [], "blue": []}
    # авианосцы декабря (Enterprise, Saratoga, America...) - в DCS нет: те же Forrestal и Carl Vinson (ДОПУЩЕНИЕ)
    cmap = {}
    units = []
    for u in ob["units"]:
        u = dict(u)
        if u.get("base") in cmap:
            u["base"] = cmap[u["base"]]
            u["name"] = (u["name"].replace("Forrestal", "Enterprise").replace("Carl Vinson", "Saratoga")
                         .replace("Coral Sea", "America"))
        if u["id"] == "us_b52":
            u["count"] = 60                          # ОЦЕНКА: доля сил (в операции - ~200 B-52 с Гуама и У-Тапао)
            u["name"] = "B-52D/G (Гуам, У-Тапао): 'Лайнбэкер-2'"
        if u.get("role") == "maneuver":              # фронт стоит: части - в обороне на местах
            u["state"], u["axis"] = "defend", None
            u.pop("arrives_day", None); u.pop("arrives_jitter", None)
            if u["side"] == "blue" and u["route"][0] == "DongHa":
                u["route"] = ["QuangTri"]
        if u["id"].startswith("r_9") and u.get("count"):
            u["count"] = max(6, int(u["count"] * 0.7))   # ОЦЕНКА: к декабрю потери ВВС ДРВ
        units.append({k: v for k, v in u.items() if v is not None})
    ob["units"] = units
    ob["preset"] = {"title": "Декабрь 1972: 'Лайнбэкер-2'", "year": 1972, "date": "1972-12-18"}
    ob["date"] = "1972-12-18"
    ob["_about"] = "Вьетнам, 'Лайнбэкер-2' (18-29.12.1972): условная география на карте Syria. tools/gen_vietnam72.py."
    ob["variants"] = [{"name": "base", "title": "Декабрь 1972: 'Лайнбэкер-2'",
                       "posture": {"red": "defense", "blue": "defense"},
                       "task_rules": {"blue": {"cas_contact": {"off": True, "why": "фронт стоит; усилия - на Север"},
                                               "strike_supply_route": {"off": True, "why": "усилия - на объекты Ханоя и Хайфона"}}},
                       "_about": "Север открыт для ударов с первого дня; фронт стоит (стороны в обороне)"}]
    (DATA / "sector_vietnam72_lb2.json").write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "oob_vietnam72_lb2.json").write_text(json.dumps(ob, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

"""Генератор театра Кавказ (карта DCS Caucasus), август 2008: data/sector_caucasus.json и data/oob_caucasus.json.

Сценарий - война России и Грузии 8-12 августа 2008 г.: утро 8 августа, грузинские войска входят в Цхинвали,
58-я армия выдвигается через Рокский тоннель, в Абхазии - второй фронт (Зугдиди, Сенаки, Поти, Кодорское ущелье).
Красные - Россия, Южная Осетия, Абхазия; синие - Грузия.

Источники (общие, по памяти - проверять): Р. Пухов (ред.), "Танки августа", ЦАСТ, 2009 (Tanks of August, CAST 2010);
отчёт комиссии Тальявини (IIFFMCG, 2009); открытые справки о ВВС и ПВО Грузии 2008. Координаты пунктов - ОЦЕНКА
(+-2 км), составы частей и числа ЛА - ОЦЕНКИ по порядку величины, не документ. Типы DCS - ближайшие (Т-62 и БТР-Д
в DCS нет - Т-55 и БТР-80; Су-25КМ - Су-25).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Танки августа (ЦАСТ, 2009) / отчёт IIFFMCG (2009), по памяти - проверить"

# ---------------------------------------------------------------- пункты (широта, долгота, сторона на утро 8.08.2008)
PLACES = {
    # Россия (Северная Осетия, Кабардино-Балкария, Ингушетия), Сочи
    "Mozdok": (43.737, 44.654, "red"), "Prokhladny": (43.758, 44.035, "red"), "Nalchik": (43.485, 43.607, "red"),
    "Beslan": (43.193, 44.541, "red"), "Nazran": (43.226, 44.765, "red"), "Vladikavkaz": (43.025, 44.682, "red"),
    "Alagir": (43.042, 44.217, "red"), "Zaramag": (42.700, 44.030, "red"), "UpperLars": (42.744, 44.630, "red"),
    "Sochi": (43.430, 39.925, "red"),
    # Южная Осетия (под контролем Цхинвали), Цхинвали утром 8.08 - грузинские войска
    "Roki": (42.567, 44.118, "red"), "Java": (42.395, 43.926, "red"), "Tskhinvali": (42.227, 43.969, "blue"),
    # Абхазия
    "Gagra": (43.330, 40.250, "red"), "Gudauta": (43.104, 40.627, "red"), "NewAthos": (43.090, 40.810, "red"),
    "Sukhumi": (43.003, 41.015, "red"), "Ochamchire": (42.713, 41.468, "red"), "Tkvarcheli": (42.854, 41.684, "red"),
    "Gali": (42.627, 41.737, "red"),
    # Грузия
    "Azhara": (43.100, 41.760, "blue"),          # верхнее Кодорское ущелье (под контролем Тбилиси до 12.08)
    "Zugdidi": (42.509, 41.871, "blue"), "Khobi": (42.315, 41.898, "blue"), "Jvari": (42.720, 42.050, "blue"),
    "Mestia": (43.045, 42.727, "blue"), "Senaki": (42.270, 42.067, "blue"), "Poti": (42.146, 41.672, "blue"),
    "Samtredia": (42.163, 42.340, "blue"), "Lanchkhuti": (42.090, 42.030, "blue"), "Ozurgeti": (41.924, 42.007, "blue"),
    "Kobuleti": (41.820, 41.776, "blue"), "Batumi": (41.643, 41.640, "blue"), "Kutaisi": (42.267, 42.718, "blue"),
    "Tkibuli": (42.350, 42.998, "blue"), "Ambrolauri": (42.520, 43.150, "blue"), "Oni": (42.580, 43.440, "blue"),
    "Zestaponi": (42.110, 43.050, "blue"), "Sachkhere": (42.344, 43.418, "blue"), "Khashuri": (41.993, 43.599, "blue"),
    "Borjomi": (41.840, 43.381, "blue"), "Akhaltsikhe": (41.639, 42.983, "blue"), "Kareli": (42.022, 43.896, "blue"),
    "Gori": (41.985, 44.112, "blue"), "Kaspi": (41.925, 44.423, "blue"), "Akhalgori": (42.128, 44.483, "blue"),
    "Mtskheta": (41.845, 44.719, "blue"), "Tbilisi": (41.716, 44.783, "blue"), "Rustavi": (41.549, 44.993, "blue"),
    "Marneuli": (41.475, 44.808, "blue"), "Sagarejo": (41.734, 45.330, "blue"), "Telavi": (41.919, 45.473, "blue"),
    "Dusheti": (42.086, 44.694, "blue"), "Pasanauri": (42.351, 44.689, "blue"), "Kazbegi": (42.657, 44.643, "blue"),
}
# дороги (не граф Габриэля: Большой Кавказ проходим только по Транскаму (Рокский тоннель), Военно-Грузинской дороге и
# побережью; ОЦЕНКА дорожной сети по карте)
LINKS = [
    ("Mozdok", "Prokhladny"), ("Mozdok", "Beslan"), ("Prokhladny", "Nalchik"), ("Prokhladny", "Beslan"),
    ("Nalchik", "Alagir"), ("Beslan", "Vladikavkaz"), ("Beslan", "Nazran"), ("Nazran", "Vladikavkaz"),
    ("Vladikavkaz", "Alagir"), ("Alagir", "Zaramag"), ("Zaramag", "Roki"), ("Roki", "Java"), ("Java", "Tskhinvali"),
    ("Vladikavkaz", "UpperLars"), ("UpperLars", "Kazbegi"), ("Kazbegi", "Pasanauri"), ("Pasanauri", "Dusheti"),
    ("Dusheti", "Mtskheta"), ("Tskhinvali", "Gori"), ("Tskhinvali", "Kareli"), ("Kareli", "Gori"), ("Kareli", "Khashuri"),
    ("Gori", "Kaspi"), ("Kaspi", "Mtskheta"), ("Kaspi", "Akhalgori"), ("Mtskheta", "Tbilisi"), ("Tbilisi", "Rustavi"),
    ("Tbilisi", "Marneuli"), ("Tbilisi", "Sagarejo"), ("Sagarejo", "Telavi"), ("Khashuri", "Borjomi"),
    ("Borjomi", "Akhaltsikhe"), ("Khashuri", "Zestaponi"), ("Zestaponi", "Sachkhere"), ("Zestaponi", "Kutaisi"),
    ("Kutaisi", "Tkibuli"), ("Kutaisi", "Ambrolauri"), ("Ambrolauri", "Oni"), ("Kutaisi", "Samtredia"),
    ("Samtredia", "Senaki"), ("Samtredia", "Lanchkhuti"), ("Lanchkhuti", "Ozurgeti"), ("Ozurgeti", "Kobuleti"),
    ("Kobuleti", "Batumi"), ("Lanchkhuti", "Poti"), ("Senaki", "Poti"), ("Senaki", "Khobi"), ("Khobi", "Zugdidi"),
    ("Senaki", "Zugdidi"), ("Zugdidi", "Jvari"), ("Jvari", "Mestia"), ("Zugdidi", "Gali"), ("Gali", "Ochamchire"),
    ("Ochamchire", "Tkvarcheli"), ("Ochamchire", "Sukhumi"), ("Sukhumi", "NewAthos"), ("NewAthos", "Gudauta"),
    ("Gudauta", "Gagra"), ("Gagra", "Sochi"), ("Sukhumi", "Azhara"),
]
SUPPLY_ENTRY = {"red": ["Mozdok", "Nalchik", "Sochi"], "blue": ["Tbilisi", "Batumi", "Telavi"]}
OFF_LIMITS = {"blue": ["Mozdok", "Prokhladny", "Nalchik", "Beslan", "Nazran", "Vladikavkaz", "Alagir", "Zaramag",
                       "UpperLars", "Sochi"]}   # Грузия не действует на территории России (политика и возможности)

AIRBASES = {   # имена - как в терраине pydcs Caucasus
    "red": ["Mozdok", "Beslan", "Nalchik", "Mineralnye Vody", "Krymsk", "Maykop-Khanskaya", "Krasnodar-Center",
            "Sochi-Adler", "Gudauta", "Sukhumi-Babushara"],
    "blue": ["Vaziani", "Soganlug", "Tbilisi-Lochini", "Kutaisi", "Senaki-Kolkhi", "Kobuleti", "Batumi"],
}

AXES = {   # оси наступления красных (ОЦЕНКА по ходу войны: Цхинвали - Гори; Абхазия - Зугдиди, Сенаки, Поти)
    "south": {"title": "Южная Осетия: Цхинвали - Гори", "objectives": ["Tskhinvali", "Kareli", "Gori"]},
    "west": {"title": "Абхазия: Зугдиди - Сенаки - Поти", "objectives": ["Gali", "Zugdidi", "Senaki", "Poti"]},
    "kodori": {"title": "Кодорское ущелье", "objectives": ["Azhara"]},
}

# ---------------------------------------------------------------- составы (ОЦЕНКИ по порядку величины)
def comp(*rows):
    return [{"type": t, "count": c, "role": r} for t, c, r in rows if c > 0]

RU_MRR = comp(("T_72B", 31, "MBT"), ("BMP_2", 90, "IFV"), ("BTR_80", 30, "APC"))          # мсп (2 БТГ в бою)
RU_VDV = comp(("BMD_1", 90, "IFV"), ("BTR_80", 15, "APC"))                                 # пдп (БТР-Д - БТР-80)
OSSET = comp(("T_55", 10, "MBT"), ("BMP_1", 25, "IFV"), ("BTR_80", 10, "APC"))             # формирования Ю. Осетии
ABKHAZ = comp(("T_72B", 20, "MBT"), ("T_55", 15, "MBT"), ("BMP_1", 30, "IFV"), ("BTR_80", 15, "APC"))
GE_BDE = comp(("T_72B", 30, "MBT"), ("BMP_2", 30, "IFV"), ("BTR_80", 20, "APC"), ("MTLB", 30, "APC"))   # пбр Грузии
GE_TANK = comp(("T_72B", 30, "MBT"), ("BMP_2", 6, "IFV"))
GE_MVD = comp(("BTR_80", 20, "APC"))
RU_AD = {"Strela_10M3": 4, "ZSU_23_4_Shilka": 4, "SA_18_Igla_manpad": 6}
GE_AD = {"Ural_375_ZU_23": 4, "SA_18_Igla_manpad": 6}

# (id, имя, сторона, пункт, состав, ПВО, день ввода, ось, примечание)
GROUND = [
    ("red_135mrr", "135-й мсп 19-й мсд (58-я армия)", "red", "Java", RU_MRR, RU_AD, 1, "south",
     "батальонные тактические группы прошли Рокский тоннель 8.08"),
    ("red_693mrr", "693-й мсп 19-й мсд (58-я армия)", "red", "Zaramag", RU_MRR, RU_AD, 1, "south", ""),
    ("red_osset", "Вооружённые формирования Южной Осетии", "red", "Java", OSSET, {"ZU_23_Emplacement": 4}, 1, "south", ""),
    ("red_503mrr", "503-й мсп 19-й мсд", "red", "Alagir", RU_MRR, RU_AD, 2, "south", ""),
    ("red_104vdv", "104-й пдп 76-й вдд", "red", "Alagir", RU_VDV, {"SA_18_Igla_manpad": 6}, 2, "south", "переброшен по воздуху в Беслан"),
    ("red_234vdv", "234-й пдп 76-й вдд", "red", "Vladikavkaz", RU_VDV, {"SA_18_Igla_manpad": 6}, 3, "south", ""),
    ("red_70mrr", "70-й мсп 42-й мсд", "red", "Vladikavkaz", RU_MRR, RU_AD, 3, "south", ""),
    ("red_71mrr", "71-й мсп 42-й мсд", "red", "Alagir", RU_MRR, RU_AD, 3, "south", ""),
    ("red_abkhaz", "Вооружённые силы Абхазии", "red", "Ochamchire", ABKHAZ, {"ZU_23_Emplacement": 4}, 1, "west", ""),
    ("red_abkhaz_k", "Абхазские подразделения (Кодори)", "red", "Sukhumi", OSSET, {"ZU_23_Emplacement": 2}, 2, "kodori",
     "наступление в Кодорское ущелье 9-12.08"),
    ("red_7vdv_247", "247-й дшп 7-й вдд", "red", "Gudauta", RU_VDV, {"SA_18_Igla_manpad": 6}, 2, "west", "через Сочи и по морю"),
    ("red_7vdv_108", "108-й дшп 7-й вдд", "red", "Sukhumi", RU_VDV, {"SA_18_Igla_manpad": 6}, 3, "west", ""),
    ("blue_4bde", "4-я пехотная бригада (Вазиани)", "blue", "Tskhinvali", GE_BDE, GE_AD, 1, None,
     "в наступлении на Цхинвали с 7-8.08"),
    ("blue_3bde", "3-я пехотная бригада (Кутаиси)", "blue", "Gori", GE_BDE, GE_AD, 1, None, "переброшена к Цхинвали 8.08"),
    ("blue_tank", "Отдельный танковый батальон (Гори)", "blue", "Kareli", GE_TANK, {}, 1, None, ""),
    ("blue_mvd", "Спецназ МВД Грузии", "blue", "Tskhinvali", GE_MVD, {}, 1, None, ""),
    ("blue_2bde", "2-я пехотная бригада (Сенаки)", "blue", "Senaki", GE_BDE, GE_AD, 1, None, ""),
    ("blue_5bde", "5-я пехотная бригада (Хони)", "blue", "Kutaisi", GE_BDE, GE_AD, 2, None, ""),
    ("blue_1bde", "1-я пехотная бригада (возвращается из Ирака)", "blue", "Tbilisi", GE_BDE, GE_AD, 3, None,
     "переброшена самолётами ВВС США 10-11.08"),
    ("blue_kodori", "Силы МВД в Верхней Абхазии", "blue", "Azhara", comp(("BTR_80", 6, "APC")), {}, 1, None, ""),
]

BUK = [("SA_11_Buk_SR_9S18M1", "radar", 1), ("SA_11_Buk_CC_9S470M1", "control", 1), ("SA_11_Buk_LN_9A310M1", "launcher", 4)]
S125 = [("p-19 s-125 sr", "radar", 1), ("snr s-125 tr", "radar", 1), ("5p73 s-125 ln", "launcher", 4)]
OSA = [("Osa_9A33_ln", "launcher", 4)]
TOR = [("Tor_9A331", "launcher", 4)]
# (id, имя, сторона, роль, состав, широта, долгота) - ЗРК; ОЦЕНКИ мест: ПВО Грузии 2008 - Бук-М1 (у Гори; у Сенаки),
# С-125М "Печора-2М" (у Тбилиси), батареи Оса-АКМ; ПВО 58-й армии - Бук (зрбр), Тор
SAMS = [
    ("blue_buk_gori", "Дивизион Бук-М1 ПВО Грузии (Гори)", "blue", "sam_medium", BUK, 41.955, 44.040),
    ("blue_buk_senaki", "Дивизион Бук-М1 ПВО Грузии (Сенаки)", "blue", "sam_medium", BUK, 42.230, 42.120),
    ("blue_s125_tbilisi", "Дивизион С-125М ПВО Грузии (Тбилиси)", "blue", "sam_medium", S125, 41.650, 44.920),
    ("blue_osa_kaspi", "Батарея Оса-АКМ ПВО Грузии (Каспи)", "blue", "sam_short", OSA, 41.940, 44.360),
    ("blue_osa_kutaisi", "Батарея Оса-АКМ ПВО Грузии (Кутаиси)", "blue", "sam_short", OSA, 42.230, 42.640),
    ("red_buk_58", "Зенитная ракетная бригада 58-й армии (Бук)", "red", "sam_medium", BUK, 42.980, 44.300),
    ("red_tor_vlad", "Батарея Тор (Владикавказ)", "red", "sam_short", TOR, 43.050, 44.620),
]

DEPOTS = [  # (id, имя, сторона, пункт)
    ("red_depot_vlad", "Склад снабжения 58-й армии (Владикавказ)", "red", "Vladikavkaz"),
    ("red_depot_alagir", "Передовой склад (Алагир)", "red", "Alagir"),
    ("red_depot_java", "Передовой склад (Джава)", "red", "Java"),
    ("red_depot_gudauta", "Склад снабжения (Гудаута)", "red", "Gudauta"),
    ("red_depot_sukhumi", "Склад снабжения (Сухуми)", "red", "Sukhumi"),
    ("blue_depot_gori", "Склад снабжения (Гори)", "blue", "Gori"),
    ("blue_depot_tbilisi", "Склад снабжения (Тбилиси)", "blue", "Tbilisi"),
    ("blue_depot_kutaisi", "Склад снабжения (Кутаиси)", "blue", "Kutaisi"),
    ("blue_depot_senaki", "Склад снабжения (Сенаки)", "blue", "Senaki"),
    ("blue_depot_zugdidi", "Передовой склад (Зугдиди)", "blue", "Zugdidi"),
]
BRIDGES = [   # мосты на путях (координаты - ОЦЕНКА; уточняются зондом карты)
    {"id": "br_inguri", "name": "Мост через Ингури (Рухи)", "lat": 42.565, "lon": 41.790,
     "links": [["Zugdidi", "Gali"]], "source": "по памяти - проверить (зонд карты)"},
    {"id": "br_gori_liakhvi", "name": "Мост через Лиахви (Гори)", "lat": 41.995, "lon": 44.120,
     "links": [["Tskhinvali", "Gori"]], "source": "по памяти - проверить (зонд карты)"},
]

# ---------------------------------------------------------------- авиация (ОЦЕНКИ чисел; базы вне карты - на ближайший)
# (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
AIR = [
    ("r368shap", "368-й ошап (Су-25)", "red", "attack", "Su_25", "Mozdok", 16, 250, "Будённовск - вне карты, на Моздок"),
    ("r461shap", "461-й ошап (Су-25)", "red", "attack", "Su_25", "Krasnodar-Center", 12, 250, ""),
    ("r559bap", "559-й бап (Су-24М)", "red", "bomber", "Su_24M", "Mozdok", 12, 400, "Морозовск - вне карты"),
    ("r11orap", "11-й орап (Су-24МР)", "red", "recon", "Su_24MR", "Mozdok", 4, 400, "Мариновка - вне карты"),
    ("r52tbap", "52-й гв. тбап (Ту-22М3)", "red", "bomber", "Tu_22M3", "Mineralnye Vody", 6, 800, "Шайковка - вне карты"),
    ("r3iap", "3-й иап (Су-27)", "red", "fighter", "Su_27", "Krymsk", 12, 450, ""),
    ("r31iap", "31-й иап (МиГ-29)", "red", "fighter", "MiG_29S", "Maykop-Khanskaya", 12, 350, "Миллерово - вне карты"),
    ("r487ovp", "487-й овп (Ми-24П)", "red", "attack_helo", "Mi_24P", "Beslan", 10, 150, "Будённовск - вне карты"),
    ("r487ovp_8", "487-й овп, эскадрилья Ми-8", "red", "transport_helo", "Mi_8MT", "Beslan", 10, 200, ""),
    ("r_a50", "Отряд ДРЛО (А-50)", "red", "awacs", "A_50", "Mineralnye Vody", 1, 1500, "Иваново - вне карты"),
    ("abkhaz_air", "ВВС Абхазии (Л-39)", "red", "attack", "L_39C", "Sukhumi-Babushara", 2, 150, ""),
    ("abkhaz_heli", "ВВС Абхазии (Ми-8)", "red", "transport_helo", "Mi_8MT", "Sukhumi-Babushara", 3, 200, ""),
    ("g_su25", "Штурмовая эскадрилья ВВС Грузии (Су-25КМ)", "blue", "attack", "Su_25", "Vaziani", 10, 250,
     "база - Марнеули (в DCS нет) - Вазиани; Су-25КМ - Су-25"),
    ("g_l39", "Учебно-боевая эскадрилья (Л-39)", "blue", "attack", "L_39C", "Kutaisi", 6, 150, ""),
    ("g_mi24", "Вертолётная эскадрилья (Ми-24)", "blue", "attack_helo", "Mi_24P", "Soganlug", 8, 150, "Алексеевка - Соганлуг"),
    ("g_mi8", "Вертолётная эскадрилья (Ми-8)", "blue", "transport_helo", "Mi_8MT", "Kutaisi", 10, 200, ""),
    ("g_uh1", "Вертолётная эскадрилья (UH-1H)", "blue", "transport_helo", "UH_1H", "Tbilisi-Lochini", 10, 150, ""),
]

AD_TEMPLATES = {   # ПВО аэродромов (ярус short) - ОЦЕНКИ
    "red": {"short": [{"name": "Тор, ЗСУ-23-4", "composition": [("Tor_9A331", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)]}]},
    "blue": {"short": [{"name": "Оса-АКМ, ЗУ-23", "composition": [("Osa_9A33_ln", "launcher", 2), ("ZU_23_Emplacement", "launcher", 2)]}]},
}
AD_AF_OFFSET_KM = 1.5


def dist_km(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * 111.32, (a[1] - b[1]) * 111.32 * k)


SSM = [   # (id, имя, сторона, ракета, пусковых, широта, долгота, источник)
    ("r_tochka_58a", "Дивизион ОТР Точка-У 58-й армии (Джава)", "red", "tochka", 4, 42.40, 43.93,
     "HRW 'Up in Flames' (2009): применение Россией ракет Точка-У по целям в Грузии; место и число - ОЦЕНКА"),
    ("r_iskander_58a", "Дивизион ОТРК Искандер (Алагир)", "red", "iskander", 4, 43.04, 44.21,
     "применение Искандера в 2008 - спорно (сообщения о ударе по Гори, Россия отрицала); оставлен как возможность, ОЦЕНКА"),
]


# сценарий (переопределяет gen_abkhazia.py и др. генераторы карты Caucasus)
NAME = "caucasus"
THEATRE = "caucasus"                               # карта DCS (model.THEATRE_INFO): caucasus, germany, ...
ROOT = "Tbilisi"                                   # пункт для проверки связности графа
SECTOR_ABOUT = ("Театр Кавказ, война августа 2008 г. Генерирован tools/gen_caucasus.py. Координаты пунктов - ОЦЕНКИ "
                "(+-2 км); дороги - вручную (через Большой Кавказ - только Рокский тоннель и Военно-Грузинская "
                "дорога, в Абхазию - побережье и мост через Ингури). Стороны - утро 8.08.2008.")
OBJ_ABOUT = ("Оси красных - ОЦЕНКА по ходу войны (Цхинвали - Гори; Абхазия - Зугдиди, Сенаки, Поти; Кодори), не документ.")
OOB_ABOUT = ("Состав сил войны 8-12 августа 2008 г. (Россия, Южная Осетия, Абхазия - Грузия). Генерирован "
             "tools/gen_caucasus.py; источники - в поле source. Числа - ОЦЕНКИ по порядку величины.")
TITLE, YEAR, DATE = "Август 2008: Южная Осетия и Абхазия", 2008, "2008-08-08"
COUNTRIES = {"red": "Russia", "blue": "Georgia"}
# ракеты ОТР: ограниченный запас - политически ограниченная война (ОЦЕНКА); у Грузии ОТР в 2008 не было
STRATEGIC = {"red": {"tochka": 16, "iskander": 6}}
TASK_RULES = {"blue": {"strike_airfield": {"off": True, "why": "у ВВС Грузии нет средств для ударов по аэродромам России"}}}
NOT_INCLUDED = ("Черноморский флот (бой у Очамчире 10.08), спецназ ГРУ, батальоны 'Восток' и 'Запад', "
                "российские миротворцы в Цхинвали, ВМС Грузии.")
EXTRA_VARIANT: dict = {}
EXTERNAL_SUPPLY: set = set()                       # аэродромы со снабжением извне (не со складов стороны)
DOCTRINE: dict | None = None
SAM_FIXED = False
AIR_ASSAULT: list = []                             # аэромобильные роты: (id, имя, сторона, пункт, {тип: число}, человек, источник)                                  # позиции ЗРК известны (объектовая ПВО) - цели ударов по позициям                       # пакеты доктрины сторон (нет - по умолчанию)


def main() -> None:
    if THEATRE == "germany":
        from dcs.terrain.germany import Germany as _T
    else:
        from dcs.terrain import Caucasus as _T
    terrain = _T()
    places = {n: {"lat": la, "lon": lo, "estimate": True, "side": s} for n, (la, lo, s) in PLACES.items()}
    adj = {n: set() for n in places}
    for a, b in LINKS:
        assert a in places and b in places, (a, b)
        adj[a].add(b); adj[b].add(a)
    seen, todo = set(), [ROOT]
    while todo:
        x = todo.pop()
        if x not in seen:
            seen.add(x); todo += adj[x]
    assert seen == set(places), f"граф несвязный: {set(places) - seen}"
    airbases, af_pos = {}, {}
    for side, names in AIRBASES.items():
        for n in names:
            bid = n.lower().replace(" ", "_").replace("-", "_")
            airbases[bid] = {"name": n, "airport": n, "side": side, "military": True,
                             **({"supply_external": True} if n in EXTERNAL_SUPPLY else {})}
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
        "_about": SECTOR_ABOUT,
        "theatre": THEATRE,
        "places": places,
        "airbases": airbases,
        "links": [list(l) for l in LINKS],
        "supply_entry": SUPPLY_ENTRY,
        "off_limits": OFF_LIMITS,
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()}, "blue": []},
        "_about_objectives": OBJ_ABOUT,
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": BRIDGES,
        "ad_sites": sites,
        "_about_ad_sites": "ПВО аэродромов (ярус short) - шаблоны сторон; ЗРК средней дальности - части состава сил.",
    }
    (DATA / f"sector_{NAME}.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")

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
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed",
                      **({"fixed": True} if SAM_FIXED else {}), "pos": {"lat": la, "lon": lo},
                      "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    for uid, name, side, place, cmp_, men, src in AIR_ASSAULT:   # вертолётный десант (assault.py), как в gen_germany
        units.append({"id": uid, "name": name, "side": side, "role": "air_assault", "state": "defend", "order": "reserve",
                      "air_mobile": True, "home": place, "men": men, "route": [place], "progress_km": 0.0,
                      "march_kmh": 5, "daily_advance_km": 10,
                      "composition": [{"type": t, "count": c, "role": "infantry"} for t, c in cmp_.items()],
                      "source": src, "estimate": True})
    for sid, name, side, missile, n, la, lo, src in SSM:   # пусковые ОТР (strategic.py): модель DCS - по ракете
        units.append({"id": sid, "name": name, "side": side, "role": "ssm", "state": "deployed", "missile": missile,
                      "pos": {"lat": la, "lon": lo}, "composition": [{"type": "Scud_B", "count": n, "role": "launcher"}],
                      "source": src, "estimate": True})
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        bid = base.lower().replace(" ", "_").replace("-", "_")
        assert bid in airbases, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": bid, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True})
    oob = {
        "_about": OOB_ABOUT,
        "theatre": THEATRE,
        "preset": {"title": TITLE, "year": YEAR, "date": DATE},
        "date": DATE,
        "countries": COUNTRIES,
        **({"doctrine": DOCTRINE} if DOCTRINE else {}),
        "units": units,
        "strategic_stock": STRATEGIC,
        "variants": [{"name": "base", "title": TITLE, "task_rules": TASK_RULES, **EXTRA_VARIANT}],
        "replacements": {"air_per_day": 1, "note": "Пополнение: самолётов в сутки до штата (ОЦЕНКА)."},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]}
                                       for v in vs] for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_not_included": NOT_INCLUDED,
    }
    (DATA / f"oob_{NAME}.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пунктов {len(places)}, связей {len(LINKS)}, аэродромов {len(airbases)}, частей {len(GROUND)}, "
          f"ЗРК {len(SAMS)}, авиачастей {len(AIR)}")


if __name__ == "__main__":
    main()

"""Харьков, 06.09-~01.10.2022: контрнаступление ВСУ на Харьковщине (условная география на карте Cold War Germany)
-> sector_kharkiv22.json, oob_kharkiv22.json.

6.09 ВСУ прорвали тонкую оборону у Балаклеи (Росгвардия, части 2-го АК ЛНР), 8.09 - Шевченково, 10.09 - Купянск
(правый берег Оскола), 10-11.09 российская группировка оставила Изюм; к концу сентября - выход на Оскол, 1.10 -
Лиман. Россия перебрасывала к Купянску части ВДВ и резервы, удары авиацией и вертолётами по колоннам. HIMARS -
удары по складам и пунктам управления в тылу. Сценарий - около трёх недель (до Лимана).

Синие - Украина (наступают), красные - Россия (обороняются; территория России - вне ударов Украины).
Условная география (биом: лесостепь - равнина, перелески, реки Бранденбурга и Альтмарка): Харьков - Штендаль;
Чугуев - Ратенов, Змиев - Гентин; Балаклея - Фризак, Шевченково - Креммен, Купянск - Ораниенбург, Боровая - Науэн,
Изюм - Бранденбург-на-Хафеле, Лиман - Белиц, Славянск - Бад-Бельциг; Сватово - Бернау; Липцы - Хафельберг,
Волчанск - Кириц; Россия: Белгород - Притцвальк, Валуйки - Фюрстенберг; тыл Украины: Полтава - Зальцведель,
Днепр - Бург. Оскол на этой схеме не воспроизведён (ОЦЕНКА), мосты - условно.

Данные о составах и потерях неполны и спорны. Источники (по памяти - проверять): ISW (сводки 09.2022), RUSI
(Watling, Reynolds, 'Stormbreak', 2023), Oryx. Составы и числа - ОЦЕНКИ по порядку величины. Типы DCS: Т-64БВ -
CHAP_T64BV, Т-90М - CHAP_T90M, Тор-М2, Панцирь, HIMARS - CurrentHill; Ка-52 - Ка-50; МиГ-29МУ1 - МиГ-29С (ГС3), МиГ-29А - модуль MiG-29A Fulcrum; AGM-88 на МиГ-29 и Су-27 - подвеска вне списка DCS (на внутренних
крыльевых пилонах, как HARM на F-4E); Су-35С, Су-30СМ - моды
(без них - Су-27); С-400 - С-300ПС; Т-72М1 (Польша) - Т-72Б; M113 - есть.
"""
from __future__ import annotations

import json

import gen_caucasus as G

G.NAME = "kharkiv22"
G.THEATRE = "germany"
G.ROOT = "Kharkiv"
G.SRC = "ISW (09.2022) / RUSI 'Stormbreak' (2023) / Oryx, по памяти - проверить"
G.TITLE, G.YEAR, G.DATE = "Харьков, сентябрь 2022: контрнаступление ВСУ", 2022, "2022-09-06"
G.COUNTRIES = {"red": "Russia", "blue": "Ukraine"}
G.DOCTRINE = {"red": "wp", "blue": "wp"}
G.SECTOR_ABOUT = ("Харьковщина, 06.09.2022. Генерирован tools/gen_kharkiv22.py. Условная география на карте Cold War "
                  "Germany (Альтмарк - Бранденбург); координаты - точки карты, имена - украинские и российские.")
G.OBJ_ABOUT = "Оси ВСУ: Балаклея - Шевченково - Купянск; Балаклея - Изюм; Славянск - Лиман; север - Волчанск."
G.OOB_ABOUT = ("Состав сил 06.09.2022 (Харьковщина). Генерирован tools/gen_kharkiv22.py; источники - в поле source. "
               "Числа - ОЦЕНКИ по порядку величины.")
G.STRATEGIC = {"red": {"iskander": 16}, "blue": {"gmlrs": 120, "tochka": 6}}
G.TASK_RULES = {"blue": {"strike_airfield": {"off": True, "why": "аэродромы в России - вне ударов Украины в 2022 году"}}}
G.NOT_INCLUDED = ("Минирование, "
                  "FPV и малые беспилотники (в лётном симуляторе нет), удары Калибрами и Х-101 по энергосистеме, юг (Херсон) - вне сектора.")
G.EXTRA_VARIANT = {
    "posture": {"blue": "offense", "red": "defense"},
    "objectives": {"blue": {"kupiansk": ["Balakliia", "Shevchenkove", "Kupiansk"],
                            "izium": ["Balakliia", "Izium", "Borova"],
                            "lyman": ["Lyman"],
                            "north": ["Lyptsi", "Vovchansk"]},
                   "red": []},
}
G.SAM_FIXED = False

G.PLACES = {
    # Россия
    "Belgorod": (53.150, 12.180, "red"), "Valuyki": (53.185, 13.145, "red"),
    # занято Россией на 06.09
    "Lyptsi": (52.825, 12.075, "red"), "Vovchansk": (52.942, 12.395, "red"), "Balakliia": (52.737, 12.580, "red"),
    "Shevchenkove": (52.762, 13.027, "red"), "Kupiansk": (52.755, 13.237, "red"), "Borova": (52.605, 12.877, "red"),
    "Izium": (52.412, 12.556, "red"), "Lyman": (52.238, 12.971, "red"), "Svatove": (52.680, 13.588, "red"),
    # Украина
    "Kharkiv": (52.605, 11.858, "blue"), "Chuhuiv": (52.605, 12.337, "blue"), "Zmiiv": (52.405, 12.160, "blue"),
    "Sloviansk": (52.142, 12.592, "blue"), "Poltava": (52.850, 11.150, "blue"), "Dnipro": (52.272, 11.855, "blue"),
}
G.LINKS = [
    ("Belgorod", "Lyptsi"), ("Lyptsi", "Kharkiv"), ("Belgorod", "Vovchansk"), ("Vovchansk", "Chuhuiv"),
    ("Vovchansk", "Kupiansk"), ("Valuyki", "Kupiansk"), ("Valuyki", "Vovchansk"), ("Kharkiv", "Chuhuiv"),
    ("Kharkiv", "Zmiiv"), ("Chuhuiv", "Balakliia"), ("Zmiiv", "Balakliia"), ("Balakliia", "Shevchenkove"),
    ("Shevchenkove", "Kupiansk"), ("Balakliia", "Izium"), ("Izium", "Borova"), ("Borova", "Kupiansk"),
    ("Kupiansk", "Svatove"), ("Borova", "Svatove"), ("Izium", "Lyman"), ("Lyman", "Svatove"), ("Izium", "Sloviansk"),
    ("Sloviansk", "Lyman"), ("Kharkiv", "Poltava"), ("Zmiiv", "Dnipro"), ("Dnipro", "Sloviansk"), ("Poltava", "Dnipro"),
]
G.SUPPLY_ENTRY = {"red": ["Belgorod", "Valuyki", "Svatove"], "blue": ["Poltava", "Dnipro"]}
G.OFF_LIMITS = {"blue": ["Belgorod", "Valuyki"]}      # Украина не наступает в Россию (и не бьёт по ней HIMARS)
G.AIRBASES = {"red": ["Wittstock", "Templin", "Finow"],             # Белгород, Россошь (вертолёты), Миллерово - ОЦЕНКА
              "blue": ["Braunschweig", "Hannover", "Celle", "Gardelegen"]}   # Миргород, Канатово, Староконстантинов, вертолёты
G.AXES = {
    "kupiansk": {"title": "Балаклея - Шевченково - Купянск", "objectives": ["Balakliia", "Shevchenkove", "Kupiansk"]},
    "izium": {"title": "Балаклея - Изюм - Боровая", "objectives": ["Balakliia", "Izium", "Borova"]},
    "lyman": {"title": "Славянск - Лиман", "objectives": ["Lyman"]},
    "north": {"title": "Север: Липцы - Волчанск", "objectives": ["Lyptsi", "Vovchansk"]},
}

c = G.comp
RU_BTG = c(("T_72B3", 10, "MBT"), ("BMP_2", 20, "IFV"), ("BTR_82A", 10, "APC"))     # сильно некомплектные к сентябрю
RU_TANK = c(("T_72B3", 20, "MBT"), ("CHAP_T90M", 4, "MBT"), ("BMP_2", 10, "IFV"))
RU_VDV = c(("BMD_1", 25, "IFV"), ("BTR_D", 10, "APC"))
RU_RG = c(("BTR_82A", 10, "APC"), ("MTLB", 6, "APC"))                                 # Росгвардия, добровольцы БАРС
LNR = c(("T_72B", 6, "MBT"), ("BMP_1", 15, "IFV"), ("MTLB", 10, "APC"))               # 2-й АК (мобилизованные)
UA_MECH = c(("CHAP_T64BV", 25, "MBT"), ("T_72B", 10, "MBT"), ("BMP_1", 25, "IFV"), ("M_113", 15, "APC"))   # Т-72М1, M113
UA_TANK = c(("CHAP_T64BV", 30, "MBT"), ("T_72B", 20, "MBT"), ("BMP_2", 10, "IFV"))
UA_AIRASLT = c(("BMP_2", 15, "IFV"), ("BTR_80", 15, "APC"), ("M_113", 10, "APC"))   # десантно-штурмовые бригады
UA_LIGHT = c(("BTR_80", 10, "APC"), ("MTLB", 10, "APC"))                              # НГУ, теробороны - ОЦЕНКА
RU_AD = {"Strela_10M3": 2, "SA_18_Igla_manpad": 4}
UA_AD = {"Strela_10M3": 2, "SA_18_Igla_manpad": 6}

G.GROUND = [
    # Россия (оборона)
    ("red_rg_balakliia", "Росгвардия и отряды БАРС (Балаклея)", "red", "Balakliia", RU_RG, {"SA_18_Igla_manpad": 2}, 1,
     None, "оборона Балаклеи слабая - прорыв 6.09"),
    ("red_lnr_2ac", "Части 2-го АК ЛНР (Шевченково)", "red", "Shevchenkove", LNR, {"SA_18_Igla_manpad": 2}, 1, None, ""),
    ("red_1gta_kup", "Части 1-й гв. танковой армии (Купянск)", "red", "Kupiansk", RU_TANK, RU_AD, 1, None, ""),
    ("red_izium_3mrd", "3-я мотострелковая дивизия (Изюм)", "red", "Izium", RU_BTG, RU_AD, 1, None, ""),
    ("red_izium_144mrd", "144-я мотострелковая дивизия (Изюм)", "red", "Izium", RU_BTG, RU_AD, 1, None, ""),
    ("red_lyman", "Части 20-й ОА и БАРС (Лиман)", "red", "Lyman", RU_BTG, RU_AD, 1, None, ""),
    ("red_11ac", "11-й армейский корпус (Липцы)", "red", "Lyptsi", RU_BTG, RU_AD, 1, None, ""),
    ("red_6caa", "Части 6-й ОА (Волчанск)", "red", "Vovchansk", LNR, RU_AD, 1, None, ""),
    ("red_vdv_kup", "Части ВДВ (переброска к Купянску)", "red", "Valuyki", RU_VDV, {"SA_18_Igla_manpad": 4}, 3, None,
     "переброска 8-9.09 - ОЦЕНКА"),
    ("red_reserve_svatove", "Резерв (Сватово)", "red", "Svatove", RU_BTG, RU_AD, 4, None, "ОЦЕНКА"),
    # Украина (наступление)
    ("blue_92mb", "92-я механизированная бригада", "blue", "Chuhuiv", UA_MECH, UA_AD, 1, "kupiansk", ""),
    ("blue_25aab", "25-я десантная бригада", "blue", "Zmiiv", UA_AIRASLT, UA_AD, 1, "izium", ""),
    ("blue_80aab", "80-я десантно-штурмовая бригада", "blue", "Chuhuiv", UA_AIRASLT, UA_AD, 1, "kupiansk", ""),
    ("blue_3tb", "3-я танковая бригада", "blue", "Zmiiv", UA_TANK, UA_AD, 2, "izium", ""),
    ("blue_4tb", "4-я танковая бригада", "blue", "Kharkiv", UA_TANK, UA_AD, 3, "kupiansk", "ОЦЕНКА"),
    ("blue_14mb", "14-я механизированная бригада", "blue", "Kharkiv", UA_MECH, UA_AD, 1, "north", ""),
    ("blue_93mb", "93-я механизированная бригада (от Славянска)", "blue", "Sloviansk", UA_MECH, UA_AD, 1, "izium", ""),
    ("blue_95aab", "95-я десантно-штурмовая бригада", "blue", "Sloviansk", UA_AIRASLT, UA_AD, 1, "lyman", ""),
    ("blue_81amb", "81-я аэромобильная бригада", "blue", "Sloviansk", UA_AIRASLT, UA_AD, 2, "lyman", ""),
    ("blue_ngu_kharkiv", "НГУ и территориальная оборона Харькова", "blue", "Kharkiv", UA_LIGHT, UA_AD, 1, None, ""),
]
G.AIR_ASSAULT = []

S300 = [("S-300PS 64H6E sr", "radar", 1), ("S-300PS 40B6M tr", "radar", 1), ("S-300PS 54K6 cp", "control", 1),
        ("S-300PS 5P85C ln", "launcher", 4)]
BUK = [("SA-11 Buk SR 9S18M1", "radar", 1), ("SA-11 Buk CC 9S470M1", "control", 1), ("SA-11 Buk LN 9A310M1", "launcher", 4)]
G.SAMS = [
    ("blue_s300_kharkiv", "Дивизион С-300ПС (Харьков)", "blue", "sam_long", S300, 52.560, 11.780),
    ("blue_buk_chuhuiv", "Дивизион Бук-М1 (Чугуев)", "blue", "sam_medium", BUK, 52.570, 12.250),
    ("blue_osa_zmiiv", "Батарея Оса-АКМ (Змиев)", "blue", "sam_short", [("Osa_9A33_ln", "launcher", 4)], 52.420, 12.100),
    ("red_s400_belgorod", "Дивизион С-400 (Белгород; в DCS - С-300ПС)", "red", "sam_long", S300, 53.120, 12.300),
    ("red_buk_izium", "Дивизион Бук-М2 (Изюм; в DCS - Бук-М1)", "red", "sam_medium", BUK, 52.450, 12.680),
    ("red_tor_kup", "Батарея Тор-М2 (Купянск)", "red", "sam_short", [("CHAP_TorM2", "launcher", 3)], 52.770, 13.300),
    ("red_pantsir_belgorod", "Батарея Панцирь-С1 (Белгород)", "red", "sam_short", [("CHAP_PantsirS1", "launcher", 3)],
     53.130, 12.200),
]
G.DEPOTS = [
    ("red_depot_izium", "Склады изюмской группировки", "red", "Izium"),
    ("red_depot_kupiansk", "Железнодорожный узел и склады Купянска", "red", "Kupiansk"),
    ("red_depot_balakliia", "Арсенал в Балаклее (склады)", "red", "Balakliia"),
    ("red_depot_svatove", "Склад снабжения (Сватово)", "red", "Svatove"),
    ("red_depot_belgorod", "Склады Белгорода", "red", "Belgorod"),
    ("blue_depot_kharkiv", "Склады Харькова", "blue", "Kharkiv"),
    ("blue_depot_chuhuiv", "Склад снабжения (Чугуев)", "blue", "Chuhuiv"),
    ("blue_depot_sloviansk", "Склад снабжения (Славянск)", "blue", "Sloviansk"),
]
G.BRIDGES = [
    {"id": "br_oskil_kupiansk", "name": "Мост через Оскол (Купянск)", "links": [["Kupiansk", "Svatove"]],
     "source": "условно: Оскол между Купянском и Купянском-Узловым"},
    {"id": "br_donets_izium", "name": "Мост через Северский Донец (Изюм)", "links": [["Balakliia", "Izium"]],
     "source": "условно: середина участка"},
    {"id": "br_oskil_borova", "name": "Мост через Оскол (Боровая)", "links": [["Borova", "Svatove"]],
     "source": "условно: середина участка"},
]
for _b in G.BRIDGES:
    _a, _c = (G.PLACES[x] for x in _b["links"][0])
    _b["lat"], _b["lon"] = round((_a[0] + _c[0]) / 2, 3), round((_a[1] + _c[1]) / 2, 3)
G.AIR = [
    ("ru_su34", "Бомбардировочный полк (Су-34)", "red", "fighter_bomber", "Su_34", "Wittstock", 12, 400, ""),
    ("ru_su25", "Штурмовой полк (Су-25СМ3; в DCS - Су-25)", "red", "attack", "Su_25", "Finow", 12, 250, ""),
    ("ru_su35", "Истребительный полк (Су-35С; в DCS - Су-27)", "red", "fighter", "Su_27", "Wittstock", 12, 500,
     "мод Су-35С включён - Су-35С, иначе - Су-27", {"mod_alt": {"mod": "su35s", "type": "Su_35S", "name": "Истребительный полк (Су-35С)"}}),
    ("ru_su30", "Полк Су-30СМ (в DCS - Су-27)", "red", "fighter", "Su_27", "Finow", 8, 500,
     "мод Су-30 включён - Су-30СМ, иначе - Су-27", {"mod_alt": {"mod": "su30", "type": "Su_30SM", "name": "Полк Су-30СМ"}}),
    ("ru_ka52", "Вертолёты Ка-52 (в DCS - Ка-50)", "red", "attack_helo", "Ka_50", "Templin", 10, 150, "Ка-52 в pydcs нет"),
    ("ru_mi28", "Вертолёты Ми-28Н", "red", "attack_helo", "Mi_28N", "Templin", 8, 150, ""),
    ("ru_mi8", "Вертолёты Ми-8АМТШ", "red", "transport_helo", "Mi_8MT", "Templin", 12, 200, ""),
    # МиГ-29 ВСУ - смешанный парк: свои МиГ-29 и МиГ-29МУ1 (в DCS - МиГ-29С) и МиГ-29А, в т.ч. переданные Польшей и
    # Словакией (2023) - примерно поровну (ОЦЕНКА). МиГ-29А - модуль MiG-29A Fulcrum (ФФ), идёт первым: подавление ПВО
    # с HARM и задачи без предпочтения типа достаются ему
    ("ua_mig29a", "114-я бригада тактической авиации (МиГ-29А)", "blue", "fighter", "MiG_29_Fulcrum", "Braunschweig", 5, 300,
     "AGM-88 HARM с августа 2022 - на внутренних крыльевых пилонах (3, 5), как HARM на F-4E", {"arm_pylons": {"pylons": [3, 5]}}),
    ("ua_mig29s", "114-я бригада тактической авиации (МиГ-29С)", "blue", "fighter", "MiG_29S", "Braunschweig", 5, 300,
     "AGM-88 HARM с августа 2022 - на внутренних крыльевых пилонах (3, 5), как HARM на F-4E", {"arm_pylons": {"pylons": [3, 5]}}),
    ("ua_su27", "831-я бригада тактической авиации (Су-27)", "blue", "fighter", "Su_27", "Hannover", 8, 500,
     "AGM-88 HARM с августа 2022 - на внутренних крыльевых пилонах (3, 8)", {"arm_pylons": {"pylons": [3, 8]}}),
    ("ua_su25", "299-я бригада тактической авиации (Су-25)", "blue", "attack", "Su_25", "Hannover", 10, 250, ""),
    ("ua_su24", "7-я бригада тактической авиации (Су-24М)", "blue", "bomber", "Su_24M", "Celle", 8, 400, ""),
    ("ua_mi24", "Армейская авиация (Ми-24)", "blue", "attack_helo", "Mi_24P", "Gardelegen", 8, 150, ""),
    ("ua_mi8", "Армейская авиация (Ми-8)", "blue", "transport_helo", "Mi_8MT", "Gardelegen", 8, 200, ""),
]
G.AD_TEMPLATES = {
    "red": {"short": [{"name": "Тор-М2, Панцирь", "composition": [("CHAP_TorM2", "launcher", 1), ("CHAP_PantsirS1", "launcher", 1)]}]},
    "blue": {"short": [{"name": "Оса, ЗУ-23", "composition": [("Osa_9A33_ln", "launcher", 1), ("ZU_23_Emplacement", "launcher", 2)]}]},
}
G.EXTERNAL_SUPPLY = {"Wittstock", "Templin", "Finow"}   # аэродромы в России - снабжение не со складов фронта
G.EW = [
    ("red_ew_leer_izium", "Комплекс Леер-3 (Изюм; в DCS - КП СКП-11)", "red", "leer3", {"SKP_11": 1, "Ural_4320_31": 2},
     52.450, 12.620, "ОЦЕНКА"),
    ("red_ew_zhitel_kup", "Станция Р-330Ж Житель (Купянск; в DCS - Урал)", "red", "zhitel", {"Ural_4320_31": 2},
     52.760, 13.180, "ОЦЕНКА"),
    ("red_ew_krasukha", "Станция Красуха-4 (Белгород; в DCS - КП СКП-11)", "red", "krasukha", {"SKP_11": 1, "Ural_375_PBU": 1},
     53.100, 12.250, "ОЦЕНКА"),
    ("blue_ew_bukovel", "Буковель-АД (Харьков; в DCS - КрАЗ)", "blue", "bukovel", {"KrAZ6322": 1}, 52.620, 11.950, "ОЦЕНКА"),
    ("blue_ew_notch", "Нота (Чугуев; в DCS - КрАЗ)", "blue", "notch", {"KrAZ6322": 1}, 52.590, 12.300, "ОЦЕНКА"),
]
G.SSM = [
    ("red_iskander", "Ракетная бригада Искандер-М (Белгород)", "red", "iskander", 4, 53.200, 12.100, "ОЦЕНКА"),
    ("blue_himars", "Батарея HIMARS ВСУ", "blue", "gmlrs", 4, 52.550, 12.150,
     "к сентябрю 2022 у Украины 16 HIMARS (все фронты) - на направлении ОЦЕНКА"),
    ("blue_tochka", "Ракетная бригада Точка-У ВС Украины", "blue", "tochka", 3, 52.400, 11.700, "ОЦЕНКА"),
]

# артиллерия (artillery.py): (id, имя, сторона, {тип DCS: число}, поддерживает, пункт, ammo_k, cb_k, источник)
# Россия - перевес в стволах и снарядах (RUSI: ~20 000 выстрелов в сутки летом 2022 против ~6 000 у ВСУ), но на
# Харьковщине к сентябрю ослаблена: резервы и артиллерия ушли под Херсон (ammo_k 0.6-0.8); ВСУ -
# снарядный голод (ammo_k), но западные контрбатарейные РЛС AN/TPQ-36/37 и точные M777 (cb_k). ОЦЕНКИ.
ART = [
    ("red_art_izium", "Артбригада изюмской группировки (Мста-С, Ураган)", "red", {"SAU_Msta": 12, "Uragan_BM_27": 4},
     "red_izium_3mrd", "Izium", 0.6, 1.0, "к сентябрю - часть стволов и снарядов ушла на херсонское направление; ОЦЕНКА"),
    ("red_art_kup", "Артиллерия 1-й гв. танковой армии (Мста-С, Град)", "red", {"SAU_Msta": 8, "Grad_URAL": 6},
     "red_1gta_kup", "Kupiansk", 0.6, 1.0, "ОЦЕНКА"),
    ("red_art_lyman", "Артиллерия у Лимана (Акация, Град)", "red", {"SAU_Akatsia": 8, "Grad_URAL": 4},
     "red_lyman", "Lyman", 0.8, 1.0, "ОЦЕНКА"),
    ("red_art_north", "Артиллерия 11-го АК (Акация, Смерч)", "red", {"SAU_Akatsia": 8, "Smerch_HE": 2},
     "red_11ac", "Lyptsi", 1.0, 1.0, "ОЦЕНКА"),
    ("blue_art_44", "44-я артиллерийская бригада (M777 и Акация; M777 в DCS - M109)", "blue", {"M_109": 8, "SAU_Akatsia": 6},
     "blue_92mb", "Chuhuiv", 0.8, 1.3, "M777 в DCS нет - M109; ОЦЕНКА"),
    ("blue_art_south", "Артиллерия у Славянска (Гвоздика, Град)", "blue", {"SAU_Gvozdika": 8, "Grad_URAL": 4},
     "blue_93mb", "Sloviansk", 0.8, 1.3, "ОЦЕНКА"),
]

if __name__ == "__main__":
    G.main()
    # HIMARS и Точка-У не бьют по аэродромам и складам в России (air_limits: пункты и объекты)
    sp = G.DATA / "sector_kharkiv22.json"
    sec = json.loads(sp.read_text(encoding="utf-8"))
    sec["air_limits"] = {"blue": G.OFF_LIMITS["blue"] + [f"af_{n.lower()}" for n in G.AIRBASES["red"]]}
    sp.write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")
    op = G.DATA / "oob_kharkiv22.json"
    oob = json.loads(op.read_text(encoding="utf-8"))
    import math
    for aid, name, side, cmp_, sup, place, ammo, cb, src in ART:
        la, lo, _s = G.PLACES[place]
        ent = min((G.PLACES[e] for e in G.SUPPLY_ENTRY[side]), key=lambda e: math.hypot(e[0] - la, (e[1] - lo) * 0.6))
        d_km = math.hypot(ent[0] - la, (ent[1] - lo) * 0.6) * 111.0
        f = min(1.0, 10.0 / d_km) if d_km else 0.0
        oob["units"].append({"id": aid, "name": name, "side": side, "role": "art_bde", "state": "deployed", "supports": sup,
                             "pos": {"lat": round(la + (ent[0] - la) * f, 4), "lon": round(lo + (ent[1] - lo) * f, 4)},
                             "ammo_k": ammo, "cb_k": cb,
                             "composition": [{"type": t, "count": n, "role": "artillery"} for t, n in cmp_.items()],
                             "source": src, "estimate": True})
    oob["strategic_per_day"] = {"blue": {"gmlrs": 8, "tochka": 1}, "red": {"iskander": 2}}
    op.write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")

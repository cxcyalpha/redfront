"""Киев, 24.02-~20.03.2022: наступление на Киев (реальная география в масштабе на карте Cold War Germany) -> sector_kyiv22.json,
oob_kyiv22.json.

Первые недели войны: с 24.02 российская группировка из Беларуси идёт по правому берегу Днепра через зону
отчуждения (Чернобыль, Иванков) к Гостомелю, Буче, Ирпеню и Макарову; утром 24.02 - вертолётный десант ВДВ на
аэродром Гостомель (Ми-8 и Ка-52, отбит контратакой, затем занят). С востока - через Чернигов (окружён, не взят) и
от Сум через Конотоп и Нежин к Броварам. Украинская оборона: бригады у Киева, НГУ, территориальная оборона,
засады с ПТРК на дорогах, удары артиллерии. Удары ОТР (Искандер) и крылатыми ракетами (Калибр, Х-101, Х-555) по
аэродромам и ПВО в первые часы. Сценарий - первые недели (до перехода к обороне и отхода в конце марта).

Красные - Россия (и территория Беларуси), синие - Украина. География - реальная, спроецированная на сушу карты
Cold War Germany с сохранением расстояний (tools/theatre_proj.py, масштаб ~0.84): Беларусь - на севере
(Нижняя Саксония), Киев - около Гёттингена, Сумы и Курск - на востоке, тыл Украины (Житомир, Староконстантинов,
Львов у края карты) - на западе и юго-западе. Аэродромы карты - ближайшие к проекции реальных (Зябровка, Курск,
Мачулищи; Васильков, Озёрное, Староконстантинов, Канатово). Рельеф, леса и реки - карты, не Украины: Днепра нет.

Война идёт до сих пор: данные о составах и потерях неполны и спорны. Источники (по памяти - проверять): RUSI
(Watling, Reynolds, 'Operation Z', 2022), ISW (сводки 02-03.2022), Oryx (визуально подтверждённые потери). Составы и
числа - ОЦЕНКИ по порядку величины. Типы DCS: Т-64БВ (обр. 2017) - CHAP_T64BV, Т-90М - CHAP_T90M, Тор-М2, Панцирь -
CurrentHill; Ка-52 в pydcs нет - Ка-50; Су-35С, Су-30СМ - моды (не включены) - Су-27; С-400 - С-300ПС; TB2 - MQ-9.
"""
from __future__ import annotations

import gen_caucasus as G

G.NAME = "kyiv22"
G.THEATRE = "germany"
G.ROOT = "Kyiv"
G.SRC = "RUSI 'Operation Z' (2022) / ISW / Oryx, по памяти - проверить"
G.TITLE, G.YEAR, G.DATE = "Киев, февраль 2022: наступление на Киев (первые недели)", 2022, "2022-02-24"
G.COUNTRIES = {"red": "Russia", "blue": "Ukraine"}
G.DOCTRINE = {"red": "wp", "blue": "ua"}
G.SECTOR_ABOUT = ("Киев, 24.02.2022. Генерирован tools/gen_kyiv22.py. Условная география на карте Cold War Germany "
                  "(Гамбург - Шлезвиг-Гольштейн); координаты - точки карты, имена - украинские и белорусские.")
G.OBJ_ABOUT = "Оси наступления: правый берег (Гостомель - Буча - Ирпень - Киев; Макаров - Житомир), Чернигов, Сумы - Бровары."
G.OOB_ABOUT = ("Состав сил 24.02.2022 (направление на Киев). Генерирован tools/gen_kyiv22.py; источники - в поле source. "
               "Числа - ОЦЕНКИ по порядку величины.")
G.STRATEGIC = {"red": {"iskander": 24, "kh101": 12, "kh555": 12}, "blue": {"tochka": 8}}
G.TASK_RULES = {"blue": {"strike_airfield": {"off": True, "why": "аэродромы в Беларуси и России - вне ударов Украины в эти недели"}}}
G.NOT_INCLUDED = ("Калибры с Черноморского флота (флота на карте нет - их удары в модели вместо Х-101/Х-555 не считаются), "
                  "Байрактары в засадах на колонны (в модели - удары MQ-9), артиллерия как отдельный род войск, "
                  "минирование, массовая РЭБ, сбор тероборонами, юг (Херсон, Мариуполь) и восток (Харьков) - вне сектора.")
G.EXTRA_VARIANT = {"posture": {"red": "offense", "blue": "defense"},
                   # десант на Гостомель 24.02: ~100 км от границы Беларуси, вертолёты прошли через ПВО (ОЦЕНКА)
                   "task_params": {"red": {"air_assault": {"assault_max_km": 140, "max_threats": 3, "per_day": 2}}}}
G.SAM_FIXED = True       # стационарные позиции С-300 и Бук известны: по ним - первые удары 24.02

G.PLACES = {
    # Беларусь и Россия
    "Mozyr": (54.320, 10.130, "red"), "Khoiniki": (54.070, 9.980, "red"), "Gomel": (53.870, 10.690, "red"),
    "Sumy": (53.850, 10.930, "blue"),          # Сумы в 2022 не взяты: окружены, обойдены
    # Киевская область (север, правый берег)
    "Chernobyl": (53.920, 9.880, "blue"), "Ivankiv": (53.830, 9.960, "blue"), "Hostomel": (53.647, 9.704, "blue"),
    "Bucha": (53.660, 9.800, "blue"), "Irpin": (53.630, 9.860, "blue"), "Makariv": (53.750, 9.650, "blue"),
    "Vyshhorod": (53.700, 10.010, "blue"), "Kyiv": (53.550, 9.990, "blue"),
    # левый берег и Черниговщина
    "Chernihiv": (53.810, 10.370, "blue"), "Konotop": (53.700, 10.760, "blue"), "Nizhyn": (53.630, 10.690, "blue"),
    "Brovary": (53.670, 10.240, "blue"), "Boryspil": (53.510, 10.250, "blue"),
    # тыл Украины
    "Zhytomyr": (53.600, 9.480, "blue"), "BilaTserkva": (53.480, 9.700, "blue"), "Obukhiv": (53.360, 10.210, "blue"),
    "Lviv": (53.080, 8.800, "blue"),
}
G.LINKS = [
    ("Mozyr", "Khoiniki"), ("Khoiniki", "Chernobyl"), ("Chernobyl", "Ivankiv"), ("Ivankiv", "Hostomel"),
    ("Ivankiv", "Vyshhorod"), ("Ivankiv", "Makariv"), ("Hostomel", "Bucha"), ("Bucha", "Irpin"), ("Irpin", "Kyiv"),
    ("Hostomel", "Makariv"), ("Makariv", "Zhytomyr"), ("Vyshhorod", "Kyiv"), ("Gomel", "Chernihiv"),
    ("Chernihiv", "Brovary"), ("Chernihiv", "Nizhyn"), ("Sumy", "Konotop"), ("Konotop", "Nizhyn"), ("Nizhyn", "Brovary"),
    ("Brovary", "Kyiv"), ("Brovary", "Boryspil"), ("Boryspil", "Kyiv"), ("Boryspil", "Obukhiv"), ("Obukhiv", "Kyiv"),
    ("Kyiv", "BilaTserkva"), ("BilaTserkva", "Zhytomyr"), ("Zhytomyr", "Lviv"), ("BilaTserkva", "Lviv"),
    ("BilaTserkva", "Obukhiv"),
]
G.SUPPLY_ENTRY = {"red": ["Mozyr", "Gomel", "Sudzha", "Klintsy"], "blue": ["Lviv"]}
G.OFF_LIMITS = {"blue": ["Mozyr", "Khoiniki", "Gomel", "Sudzha", "Klintsy", "Glushkovo", "Trubchevsk", "Sevsk"]}   # Украина не наступает в Беларусь и Россию
G.AIRBASES = {"red": ["Kiel", "Lubeck", "Pinnow"],                  # Мачулищи / Зябровка / Курск - ОЦЕНКА
              "blue": ["Hamburg Finkenwerder", "Celle", "Wunstorf", "Hannover"]}   # Васильков, Озёрное, Староконстантинов, Канатово
G.AXES = {
    "west": {"title": "Правый берег: Гостомель - Буча - Ирпень - Киев", "objectives": ["Hostomel", "Bucha", "Irpin", "Kyiv"]},
    "makariv": {"title": "Макаров - Житомир", "objectives": ["Makariv", "Zhytomyr"]},
    "chernihiv": {"title": "Чернигов", "objectives": ["Chernihiv"]},
    "east": {"title": "Сумы - Конотоп - Нежин - Бровары", "objectives": ["Konotop", "Nizhyn", "Brovary", "Kyiv"]},
}

c = G.comp
RU_BTG = c(("T_72B3", 20, "MBT"), ("BMP_2", 30, "IFV"), ("BTR_82A", 10, "APC"))           # 2-3 БТГ мсбр/мсп - ОЦЕНКА
RU_TANK = c(("T_72B3", 30, "MBT"), ("CHAP_T90M", 6, "MBT"), ("BMP_2", 15, "IFV"))
RU_VDV = c(("BMD_1", 40, "IFV"), ("BTR_D", 15, "APC"))
UA_MECH = c(("CHAP_T64BV", 30, "MBT"), ("BMP_2", 40, "IFV"), ("BTR_80", 15, "APC"))      # БТР-4 - БТР-80
UA_TANK = c(("CHAP_T64BV", 60, "MBT"), ("BMP_2", 10, "IFV"))
UA_LIGHT = c(("BTR_80", 15, "APC"), ("MTLB", 10, "APC"))                                   # НГУ, ДШВ, теробороны - ОЦЕНКА
RU_AD = {"Strela_10M3": 2, "SA_18_Igla_manpad": 4}
UA_AD = {"Strela_10M3": 2, "SA_18_Igla_manpad": 6}      # Стингеры и Иглы - много (ОЦЕНКА)

G.GROUND = [
    ("red_35caa", "35-я общевойсковая армия (Беларусь - правый берег)", "red", "Khoiniki", RU_BTG, RU_AD, 1, "west", ""),
    ("red_36caa", "36-я общевойсковая армия", "red", "Khoiniki", RU_BTG, RU_AD, 1, "makariv", ""),
    ("red_vdv_76", "76-я десантно-штурмовая дивизия", "red", "Khoiniki", RU_VDV, {"SA_18_Igla_manpad": 4}, 1, "west",
     "Буча, Ирпень"),
    ("red_vdv_98", "98-я воздушно-десантная дивизия", "red", "Mozyr", RU_VDV, {"SA_18_Igla_manpad": 4}, 2, "west",
     "Гостомель (после захвата аэродрома)"),
    ("red_5caa", "5-я общевойсковая армия", "red", "Mozyr", RU_BTG, RU_AD, 3, "west", ""),
    ("red_41caa", "41-я общевойсковая армия (Чернигов)", "red", "Gomel", RU_BTG, RU_AD, 1, "chernihiv", ""),
    ("red_2gta", "2-я гв. танковая армия (Сумы - Конотоп)", "red", "Glushkovo", RU_TANK, RU_AD, 1, "east", ""),
    ("red_90td", "90-я гв. танковая дивизия", "red", "Sudzha", RU_TANK, RU_AD, 2, "east", ""),
    ("blue_72mb", "72-я механизированная бригада (Киев)", "blue", "Irpin", UA_MECH, UA_AD, 1, None, ""),
    ("blue_4ngu", "4-я бригада быстрого реагирования НГУ", "blue", "Kyiv", UA_LIGHT, UA_AD, 1, None,
     "контратака на аэродром Гостомель 24.02"),
    ("blue_tro_kyiv", "Территориальная оборона и НГУ Киева", "blue", "Kyiv", UA_LIGHT, UA_AD, 1, None, ""),
    ("blue_tro_bucha", "Территориальная оборона (Буча, Ирпень)", "blue", "Bucha", UA_LIGHT, UA_AD, 1, None, ""),
    ("blue_1tb", "1-я танковая бригада (Чернигов)", "blue", "Chernihiv", UA_TANK, UA_AD, 1, None, "оборона Чернигова"),
    ("blue_58mb", "58-я мотопехотная бригада (Конотоп - Нежин)", "blue", "Nizhyn", UA_MECH, UA_AD, 1, None, ""),
    ("blue_95daab", "95-я десантно-штурмовая бригада (Житомир)", "blue", "Zhytomyr", UA_LIGHT, UA_AD, 2, None, ""),
    ("blue_14mb", "14-я механизированная бригада (с запада)", "blue", "Lviv", UA_MECH, UA_AD, 5, None, "ОЦЕНКА"),
    ("blue_tro_sumy", "Территориальная оборона и 27-я реактивная артбригада (Сумы)", "blue", "Sumy", UA_LIGHT, UA_AD, 1, None,
     "Сумы не взяты: окружены и обойдены"),
    ("blue_brovary", "Части обороны Броваров", "blue", "Brovary", UA_LIGHT, UA_AD, 1, None, "засада у Скибина 10.03"),
]
G.AIR_ASSAULT = [   # (id, имя, сторона, пункт, {тип: число}, человек, источник): десант на Гостомель 24.02 (Ми-8 + Ка-52)
    ("red_vdv_hostomel1", "Рота 31-й одшбр (десант на Гостомель)", "red", "Khoiniki",
     {"Paratrooper_AKS_74": 20, "Paratrooper_RPG_16": 4}, 100, "по разным оценкам - до 200-300 человек в первой волне"),
    ("red_vdv_hostomel2", "Рота 45-й бригады спецназа ВДВ", "red", "Khoiniki",
     {"Paratrooper_AKS_74": 20, "Paratrooper_RPG_16": 4}, 100, "ОЦЕНКА"),
]

S300 = [("S-300PS 64H6E sr", "radar", 1), ("S-300PS 40B6M tr", "radar", 1), ("S-300PS 54K6 cp", "control", 1),
        ("S-300PS 5P85C ln", "launcher", 4)]
BUK = [("SA-11 Buk SR 9S18M1", "radar", 1), ("SA-11 Buk CC 9S470M1", "control", 1), ("SA-11 Buk LN 9A310M1", "launcher", 4)]
G.SAMS = [
    ("blue_s300_kyiv_n", "Дивизион С-300ПС (Киев, север)", "blue", "sam_long", S300, 53.680, 9.950),
    ("blue_s300_kyiv_s", "Дивизион С-300ПС (Киев, юг)", "blue", "sam_long", S300, 53.460, 10.050),
    ("blue_buk_kyiv", "Дивизион Бук-М1 (Киев)", "blue", "sam_medium", BUK, 53.560, 9.820),
    ("blue_buk_chernihiv", "Дивизион Бук-М1 (Чернигов)", "blue", "sam_medium", BUK, 53.780, 10.330),
    ("blue_osa_brovary", "Батарея Оса-АКМ (Бровары)", "blue", "sam_short", [("Osa_9A33_ln", "launcher", 4)], 53.660, 10.200),
    ("red_s400_belarus", "Дивизион С-400 (Беларусь; в DCS - С-300ПС)", "red", "sam_long", S300, 54.200, 10.050),
    ("red_buk_35caa", "Зенитная ракетная бригада 35-й армии (Бук)", "red", "sam_medium", BUK, 53.980, 9.930),
    ("red_tor_west", "Батарея Тор-М2 (правый берег)", "red", "sam_short", [("CHAP_TorM2", "launcher", 3)], 53.880, 9.900),
    ("red_pantsir_gomel", "Батарея Панцирь-С1 (Гомель)", "red", "sam_short", [("CHAP_PantsirS1", "launcher", 3)], 53.860, 10.650),
]
G.DEPOTS = [
    ("red_depot_khoiniki", "Склад снабжения (Хойники)", "red", "Khoiniki"),
    ("red_depot_gomel", "Склад снабжения (Гомель)", "red", "Gomel"),
    ("red_depot_sumy", "Склад снабжения (Суджа)", "red", "Sudzha"),
    ("blue_depot_kyiv", "Склады Киева", "blue", "Kyiv"),
    ("blue_depot_zhytomyr", "Склад снабжения (Житомир)", "blue", "Zhytomyr"),
    ("blue_depot_chernihiv", "Склад снабжения (Чернигов)", "blue", "Chernihiv"),
    ("blue_depot_bila", "Склад снабжения (Белая Церковь)", "blue", "BilaTserkva"),
]
G.BRIDGES = [
    {"id": "br_irpin", "name": "Мост через Ирпень (Романовка)", "links": [["Irpin", "Kyiv"]],
     "source": "условно: середина участка Ирпень - Киев (взорван 25.02)"},
    {"id": "br_teteriv", "name": "Мост через Тетерев (Иванков)", "links": [["Chernobyl", "Ivankiv"]],
     "source": "условно: середина участка Чернобыль - Иванков"},
    {"id": "br_desna", "name": "Мост через Десну (Чернигов)", "links": [["Chernihiv", "Brovary"]],
     "source": "условно: середина участка Чернигов - Бровары"},
]
for _b in G.BRIDGES:
    _a, _c = (G.PLACES[x] for x in _b["links"][0])
    _b["lat"], _b["lon"] = round((_a[0] + _c[0]) / 2, 3), round((_a[1] + _c[1]) / 2, 3)
# (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
G.AIR = [
    ("ru_su34", "Бомбардировочный полк (Су-34)", "red", "fighter_bomber", "Su_34", "Kiel", 16, 450, ""),
    ("ru_su25", "Штурмовой полк (Су-25СМ3; в DCS - Су-25)", "red", "attack", "Su_25", "Lubeck", 16, 250, ""),
    ("ru_su35", "Истребительный полк (Су-35С; в DCS - Су-27)", "red", "fighter", "Su_27", "Kiel", 16, 500,
     "мод Су-35С включён - Су-35С, иначе - Су-27", {"mod_alt": {"mod": "su35s", "type": "Su_35S", "name": "Истребительный полк (Су-35С)"}}),
    ("ru_su30", "Полк Су-30СМ (в DCS - Су-27)", "red", "fighter_bomber", "Su_27", "Lubeck", 12, 500,
     "мод Су-30 включён - Су-30СМ, иначе - Су-27", {"mod_alt": {"mod": "su30", "type": "Su_30SM", "name": "Полк Су-30СМ"}}),
    # Су-24М у ВКС в 2022 почти не летали: удары по земле - Су-34, затем Су-30СМ (Су-24 - у Украины)
    ("ru_ka52", "Вертолёты Ка-52 (в DCS - Ка-50)", "red", "attack_helo", "Ka_50", "Kiel", 12, 150, "Ка-52 в pydcs нет"),
    ("ru_mi28", "Вертолёты Ми-28Н", "red", "attack_helo", "Mi_28N", "Lubeck", 10, 150, ""),
    ("ru_mi8", "Вертолёты Ми-8АМТШ (десант)", "red", "transport_helo", "Mi_8MT", "Kiel", 20, 200, ""),
    ("ru_a50", "Самолёт ДРЛО А-50", "red", "awacs", "A_50", "Pinnow", 1, 1500, ""),
    ("ru_tu95", "Ту-95МС (удары крылатыми ракетами)", "red", "bomber", "Tu_95MS", "Pinnow", 6, 3000,
     "дальняя авиация; базы - вне сектора, здесь - Пиннов"),
    ("ru_tu22", "Ту-22М3", "red", "bomber", "Tu_22M3", "Pinnow", 6, 1500, ""),
    ("ua_mig29", "40-я бригада тактической авиации (МиГ-29, Васильков)", "blue", "fighter", "MiG_29A", "Hamburg Finkenwerder",
     12, 300, ""),
    ("ua_su27", "39-я бригада тактической авиации (Су-27, Озёрное)", "blue", "fighter", "Su_27", "Celle", 12, 500, ""),
    ("ua_su24", "7-я бригада тактической авиации (Су-24М, Староконстантинов)", "blue", "bomber", "Su_24M", "Wunstorf", 10, 400, ""),
    ("ua_su25", "299-я бригада тактической авиации (Су-25)", "blue", "attack", "Su_25", "Celle", 12, 250,
     "Канатово - далеко от Киева: в первые недели Су-25 летали с аэродромов ближе к фронту (рассредоточение) - здесь Озёрное"),
    ("ua_tb2", "Беспилотники Bayraktar TB2 (в DCS - MQ-9)", "blue", "fighter_bomber", "MQ_9_Reaper", "Celle", 6, 250, "ОЦЕНКА"),
    ("ua_mi24", "Армейская авиация (Ми-24)", "blue", "attack_helo", "Mi_24P", "Hannover", 10, 150, ""),
    ("ua_mi8", "Армейская авиация (Ми-8)", "blue", "transport_helo", "Mi_8MT", "Hannover", 10, 200, ""),
]
G.AD_TEMPLATES = {
    "red": {"short": [{"name": "Тор-М2, Панцирь", "composition": [("CHAP_TorM2", "launcher", 1), ("CHAP_PantsirS1", "launcher", 1)]}]},
    "blue": {"short": [{"name": "Оса, ЗУ-23", "composition": [("Osa_9A33_ln", "launcher", 1), ("ZU_23_Emplacement", "launcher", 2)]}]},
}
G.EXTERNAL_SUPPLY = {"Kiel", "Lubeck", "Pinnow"}   # аэродромы в Беларуси и России - снабжение не со складов фронта
G.EW = [   # станции РЭБ (ew.py); моделей в DCS нет - грузовики и КП (замена в имени); места и состав - ОЦЕНКА
    ("red_ew_leer_west", "Комплекс Леер-3 (правый берег; в DCS - КП СКП-11)", "red", "leer3", {"SKP_11": 1, "Ural_4320_31": 2},
     53.900, 9.920, "Леер-3 с Орлан-10 - ОЦЕНКА размещения"),
    ("red_ew_krasukha_by", "Станция Красуха-4 (Беларусь; в DCS - КП СКП-11)", "red", "krasukha", {"SKP_11": 1, "Ural_375_PBU": 1},
     54.150, 10.020, "ОЦЕНКА"),
    ("red_ew_zhitel_east", "Станция Р-330Ж Житель (восток; в DCS - Урал)", "red", "zhitel", {"Ural_4320_31": 2},
     53.820, 10.600, "ОЦЕНКА"),
    ("red_ew_pole21", "Поле-21 (подавление ГНСС; в DCS - Урал)", "red", "pole21", {"Ural_4320_31": 2}, 54.000, 10.300, "ОЦЕНКА"),
    ("blue_ew_bukovel", "Буковель-АД (Киев; в DCS - КрАЗ)", "blue", "bukovel", {"KrAZ6322": 1}, 53.600, 9.900,
     "в начале 2022 - немного; ОЦЕНКА"),
    ("blue_ew_notch", "Нота (Чернигов; в DCS - КрАЗ)", "blue", "notch", {"KrAZ6322": 1}, 53.790, 10.350, "ОЦЕНКА"),
]
G.SSM = [
    ("red_iskander_by", "Ракетная бригада Искандер-М (Беларусь)", "red", "iskander", 8, 54.250, 10.000,
     "удары по аэродромам и ПВО 24.02 - ОЦЕНКА числа"),
    ("red_iskander_ru", "Ракетная бригада Искандер-М (Россия)", "red", "iskander", 4, 53.900, 10.850, "ОЦЕНКА"),
    ("blue_tochka", "Ракетная бригада Точка-У ВС Украины", "blue", "tochka", 4, 53.400, 9.600, "ОЦЕНКА"),
]

# ---- реальная география с глубиной театра (theatre_proj): пункты и аэродромы - реальные координаты, спроецированные
# на сушу карты в одном масштабе; ЗРК, РЭБ, пусковые - перенесены тем же преобразованием
import theatre_proj  # noqa: E402

REAL = {   # широта, долгота (по памяти, +-2 км)
    "Mozyr": (52.05, 29.24), "Khoiniki": (51.89, 29.96), "Gomel": (52.44, 30.98), "Sumy": (50.91, 34.80),
    "Chernobyl": (51.27, 30.22), "Ivankiv": (50.94, 29.90), "Hostomel": (50.58, 30.20), "Bucha": (50.55, 30.22),
    "Irpin": (50.52, 30.25), "Makariv": (50.46, 29.81), "Vyshhorod": (50.58, 30.49), "Kyiv": (50.45, 30.52),
    "Chernihiv": (51.50, 31.29), "Konotop": (51.24, 33.20), "Nizhyn": (51.05, 31.89), "Brovary": (50.51, 30.79),
    "Boryspil": (50.35, 30.95), "Zhytomyr": (50.25, 28.66), "BilaTserkva": (49.80, 30.12), "Obukhiv": (50.11, 30.62),
    "Lviv": (49.84, 24.03),           # подвоз из Польши - глубокий тыл, у края карты
}
REAL_AB = {   # прежнее имя аэродрома карты -> реальный аэродром
    "Kiel": (53.77, 27.58),                   # Мачулищи (Минск) - у края карты
    "Lubeck": (52.30, 31.17),                 # Зябровка (Гомель)
    "Pinnow": (51.75, 36.30),                 # Курск (Халино)
    "Hamburg Finkenwerder": (50.23, 30.30),   # Васильков
    "Celle": (50.16, 28.74),                  # Озёрное (Житомир)
    "Wunstorf": (49.75, 27.27),               # Староконстантинов
    "Hannover": (48.55, 32.29),               # Канатово (Кропивницкий)
}
PROJ = theatre_proj.apply(G, REAL, REAL_AB, far=("Lviv", "Kiel"))
# граница 24.02: Беларусь и Россия - Украина (северо-восток: Черниговщина, Сумщина) - пункты по обе стороны, чтобы
# фронт первого дня шёл по границе, а не обрывался; в старой условной схеме их не было - сразу в проекции
BORDER = {   # имя: (широта, долгота, сторона)
    "Horodnia": (51.89, 31.60, "blue"), "NovhorodSiverskyi": (52.01, 33.26, "blue"), "Shostka": (51.86, 33.48, "blue"),
    "Okhtyrka": (50.31, 34.90, "blue"), "Klintsy": (52.76, 32.24, "red"), "Glushkovo": (51.34, 34.64, "red"),
    "Sudzha": (51.19, 35.27, "red"), "Trubchevsk": (52.58, 33.77, "red"), "Sevsk": (52.15, 34.49, "red"),
}
for _n, (_la, _lo, _sd) in BORDER.items():
    G.PLACES[_n] = (*PROJ(_la, _lo), _sd)
G.LINKS += [("Gomel", "Horodnia"), ("Horodnia", "Chernihiv"), ("Klintsy", "Horodnia"), ("Klintsy", "NovhorodSiverskyi"),
            ("NovhorodSiverskyi", "Shostka"), ("Shostka", "Konotop"), ("Glushkovo", "Shostka"), ("Glushkovo", "Konotop"),
            ("Sudzha", "Sumy"), ("Sumy", "Okhtyrka"), ("Sudzha", "Okhtyrka"), ("Klintsy", "Trubchevsk"),
            ("Trubchevsk", "NovhorodSiverskyi"), ("Trubchevsk", "Sevsk"), ("Sevsk", "Shostka"), ("Sevsk", "Glushkovo")]
_kla, _klo, _s = G.PLACES["Kyiv"]               # Буковель-АД - прикрывает сам Киев (радиус 15 км)
G.EW = [(r[:5] + (round(_kla + 0.03, 4), round(_klo - 0.03, 4)) + r[7:]) if r[0] == "blue_ew_bukovel" else r for r in G.EW]
G.SECTOR_ABOUT = ("Киев, 24.02.2022. Генерирован tools/gen_kyiv22.py. Реальная география, спроецированная на карту Cold "
                  f"War Germany: {G.PROJ_NOTE}. Рельеф и реки (Днепр) - карты, не Украины.")

if __name__ == "__main__":
    G.main()
    import json
    # рассредоточение ВВС Украины (dispersal.py): самолёты рассредоточены до ударов 24.02, затем - посадка на другом
    # аэродроме часто, перебазирование раз в несколько суток (интервью лётчиков). ОЦЕНКИ
    op = G.DATA / "oob_kyiv22.json"
    oob = json.loads(op.read_text(encoding="utf-8"))
    oob["dispersal"] = {"blue": {"land_other_p": 0.3, "rebase_p": 0.2, "max_km": 300}}
    # подвески ВКС (weapons.policy): по земле - неуправляемое (кроме ПРР у групп подавления ПВО), Р-37М - только у CAP
    oob["loadout_policy"] = {"red": {"ag_unguided": True, "aa_long_cap_only": True}}
    # ДРЛО НАТО (E-3A над Польшей и Румынией): своих самолётов ДРЛО у ВСУ нет, данные - от союзников; в миссии -
    # E-3A вне театра, в воздухе с начала миссии (не часть модели, не цель). На условной карте - за тылом Украины
    # (на западе карты), а не над настоящей Польшей (она на востоке карты, на стороне России)
    oob["external_awacs"] = {"blue": {"type": "E_3A", "standoff_km": 250, "title": "ДРЛО НАТО E-3A (за тылом Украины)"}}
    op.write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")

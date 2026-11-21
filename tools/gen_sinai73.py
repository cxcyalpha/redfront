"""Синай, 06-24.10.1973: Октябрьская война на Суэцком канале (карта DCS Sinai - реальная местность) -> sector_sinai73.json,
oob_sinai73.json.

6.10 (операция "Бадр") египетские 2-я и 3-я армии форсируют канал по всему фронту, берут опорные пункты линии Бар-Лева
(Кантара - 9.10, Порт-Тауфик - 13.10) и закрепляются на плацдармах в 10-15 км под "зонтиком" ЗРК (С-75, С-125, Куб) с
западного берега. 8.10 - контрудар израильских дивизий Адана и Шарона - неудача. 14.10 - наступление египетских
бронетанковых дивизий к перевалам (Митла, Гидди, Таса) - разгром. 15-16.10 - Израиль (Шарон) форсирует канал у
Девесуара (Китайская ферма), 18-22.10 - наступление на западном берегу (Фаид, Генейфа), окружение 3-й армии; Исмаилия и
Суэц не взяты (24.10 - неудачный штурм Суэца). Прекращение огня - 22 и 24.10.

Красные - Египет, синие - Израиль. Источники (по памяти - проверить): Ch. Herzog, "The War of Atonement" (1975);
A. Adan, "On the Banks of the Suez" (1980); S. El Shazly, "The Crossing of the Suez" (1980). Координаты - ОЦЕНКИ
(+-2 км), составы и числа - ОЦЕНКИ по порядку величины. Типы DCS: Т-55/Т-62 - Т-55, M48/M60 "Паттон" - M-60, "Шот" -
M-60; МиГ-21МФ - МиГ-21бис, Су-7БМК - Су-17М4, МиГ-17 - МиГ-15бис; "Мираж" III/"Нешер" - Mirage F1CE; A-4 - мод A-4E-C.
Мосты через канал - понтонные переправы (их разрушение замедляет переправу: форсирование с ходу).
"""
from __future__ import annotations

import gen_caucasus as G

G.NAME = "sinai73"
G.THEATRE = "sinai"
G.ROOT = "Ismailia"
G.SRC = "Herzog 'War of Atonement' / Adan 'On the Banks of the Suez' / El Shazly, по памяти - проверить"
G.TITLE, G.YEAR, G.DATE = "Синай, октябрь 1973: Суэцкий канал", 1973, "1973-10-06"
G.COUNTRIES = {"red": "Egypt", "blue": "Israel"}
G.DOCTRINE = {"red": "arab", "blue": "iaf73"}
G.SECTOR_ABOUT = ("Синай, 06.10.1973. Генерирован tools/gen_sinai73.py. Реальная местность карты Sinai; координаты - ОЦЕНКИ.")
G.OBJ_ABOUT = ("Оси Египта: плацдармы у Кантары, Фирдана, Девесуара, Порт-Тауфика, затем - перевалы (14.10). Оси Израиля "
               "(с 15.10): Китайская ферма - Девесуар - Фаид - Генейфа (окружение 3-й армии).")
G.OOB_ABOUT = ("Состав сил 06.10.1973 (Суэцкий фронт). Генерирован tools/gen_sinai73.py; источники - в поле source. Числа - "
               "ОЦЕНКИ по порядку величины.")
G.STRATEGIC = {}
G.TASK_RULES = {"blue": {"strike_factory": {"off": True, "why": "по промышленности Египта не били"}},
                "red": {"strike_factory": {"off": True, "why": "по Израилю за Синаем удары - единичные"}}}
G.NOT_INCLUDED = ("Флот (бой у Балтима и Дамьетты 8-9.10), Ту-16 с ракетами КСР-2, ОТР 'Скад' (16.10), "
                  "десанты египетских коммандос в Синае (вертолётами 6.10 - в модели нет), фронт на Красном море.")
G.SAM_FIXED = True

G.PLACES = {   # (широта, долгота, сторона на 06.10.1973)
    # Египет: Каир и тыл, западный берег канала
    "Cairo": (30.05, 31.24, "red"), "Bilbeis": (30.42, 31.56, "red"), "TellElKebir": (30.55, 31.78, "red"),
    "Ismailia": (30.60, 32.27, "red"), "QantaraWest": (30.86, 32.31, "red"), "PortSaid": (31.26, 32.30, "red"),
    "Deversoir": (30.42, 32.33, "red"), "Fayed": (30.32, 32.30, "red"), "Geneifa": (30.20, 32.43, "red"),
    "Suez": (29.97, 32.53, "red"), "Adabiya": (29.87, 32.47, "red"), "Km101": (30.08, 32.05, "red"),
    # Синай (под контролем Израиля с 1967): опорные пункты линии Бар-Лева, рокада, перевалы, тыл
    "QantaraEast": (30.85, 32.34, "blue"), "Firdan": (30.66, 32.36, "blue"), "ChineseFarm": (30.46, 32.42, "blue"),
    "Matzmed": (30.40, 32.38, "blue"),          # опорный пункт у северной оконечности Большого Горького озера (переправа 15-16.10)
    "PortTewfik": (29.95, 32.56, "blue"), "Baluza": (31.03, 32.58, "blue"), "Tasa": (30.50, 32.87, "blue"),
    "Refidim": (30.41, 33.15, "blue"), "Giddi": (30.21, 32.98, "blue"), "Mitla": (30.03, 32.92, "blue"),
    "RasSudr": (29.59, 32.71, "blue"), "AbuRudeis": (28.90, 33.20, "blue"), "BirHasana": (30.20, 33.42, "blue"),
    "Nakhl": (29.92, 33.75, "blue"), "ElArish": (31.13, 33.80, "blue"), "Beersheba": (31.25, 34.79, "blue"),
}
G.LINKS = [
    ("Cairo", "Bilbeis"), ("Bilbeis", "TellElKebir"), ("TellElKebir", "Ismailia"), ("Ismailia", "QantaraWest"),
    ("QantaraWest", "PortSaid"), ("Ismailia", "Deversoir"), ("Deversoir", "Fayed"), ("Fayed", "Geneifa"),
    ("Geneifa", "Suez"), ("Suez", "Adabiya"), ("Cairo", "Km101"), ("Km101", "Suez"), ("Km101", "Fayed"),
    # переправы через канал
    ("QantaraWest", "QantaraEast"), ("Ismailia", "Firdan"), ("Deversoir", "ChineseFarm"), ("Suez", "PortTewfik"),
    # Синай: рокада вдоль канала, "Артиллерийская дорога", перевалы, дороги в тыл
    ("QantaraEast", "Firdan"), ("Firdan", "ChineseFarm"), ("QantaraEast", "Baluza"), ("Firdan", "Tasa"),
    ("ChineseFarm", "Tasa"), ("ChineseFarm", "Giddi"), ("Tasa", "Matzmed"), ("Matzmed", "ChineseFarm"),
    ("Matzmed", "Deversoir"),                    # "Акавиш" и "Тиртур" - дороги Шарона к переправе
    ("PortTewfik", "Mitla"), ("PortTewfik", "RasSudr"),
    ("RasSudr", "AbuRudeis"), ("Mitla", "Giddi"), ("Giddi", "Refidim"), ("Tasa", "Refidim"), ("Mitla", "Nakhl"),
    ("Refidim", "BirHasana"), ("Nakhl", "BirHasana"), ("Baluza", "ElArish"), ("Refidim", "ElArish"),
    ("ElArish", "Beersheba"), ("BirHasana", "Beersheba"),
]
G.SUPPLY_ENTRY = {"red": ["Cairo"], "blue": ["Beersheba"]}
G.OFF_LIMITS = {"blue": ["Cairo", "Bilbeis", "PortSaid"],      # к Каиру не шли (Км 101 - переговоры)
                "red": ["Beersheba", "ElArish", "BirHasana", "Nakhl", "AbuRudeis"]}   # Египет - только к перевалам
G.AIRBASES = {"red": ["Inshas Airbase", "Bilbeis Air Base", "Abu Suwayr", "As Salihiyah", "Fayed", "Al Mansurah",
                      "Cairo West", "Beni Suef", "AzZaqaziq", "Wadi al Jandali"],
              "blue": ["Melez", "Bir Hasanah", "El Arish", "Hatzerim", "Hatzor", "Tel Nof", "Nevatim", "Ramon Airbase"]}
G.EXTERNAL_SUPPLY = {"Hatzerim", "Hatzor", "Tel Nof", "Nevatim", "Ramon Airbase", "Cairo West", "Beni Suef"}
G.AXES = {
    "qantara": {"title": "18-я пд: Кантара", "objectives": ["QantaraEast", "Baluza"]},
    "firdan": {"title": "2-я пд: Фирдан - Таса", "objectives": ["Firdan", "Tasa"]},
    "center": {"title": "16-я пд: Китайская ферма - Таса", "objectives": ["ChineseFarm", "Tasa"]},
    "south": {"title": "3-я армия: Порт-Тауфик - Митла - Гидди", "objectives": ["PortTewfik", "Mitla", "Giddi"]},
}

c = G.comp
EG_INF = c(("T_55", 120, "MBT"), ("BMP_1", 30, "IFV"), ("BTR-60", 80, "APC"), ("Infantry AK", 250, "infantry"))   # пд с тбр
EG_ARM = c(("T_55", 250, "MBT"), ("BMP_1", 50, "IFV"), ("BTR-60", 40, "APC"))                                      # тд
EG_MECH = c(("T_55", 160, "MBT"), ("BMP_1", 80, "IFV"), ("BTR-60", 60, "APC"))                                     # мд
IL_BDE = c(("M-60", 90, "MBT"), ("M-113", 25, "APC"))                     # бронетанковая бригада ("Магах", "Шот")
IL_DIV = c(("M-60", 220, "MBT"), ("M-113", 70, "APC"))                     # дивизия резерва (2-3 бригады)
IL_FORT = c(("M-113", 6, "APC"), ("Soldier M4", 30, "infantry"))           # опорный пункт линии Бар-Лева (резервисты)
IL_PARA = c(("M-113", 30, "APC"), ("Soldier M4", 120, "infantry"))         # 247-я пдбр (Мат) - переправа
EG_GAR = c(("BTR-60", 30, "APC"), ("Infantry AK", 200, "infantry"), ("Soldier RPG", 40, "infantry"))   # гарнизон города
EG_AD = {"ZSU_23_4_Shilka": 8, "Strela_1_9P31": 6, "SA-18 Igla manpad": 8}   # "Стрела-2" - Игла (ДОПУЩЕНИЕ)
IL_AD = {"Vulcan": 4}

G.GROUND = [
    # Египет: 2-я армия (север), 3-я армия (юг); бронетанковые дивизии - резерв на западном берегу
    ("red_18id", "18-я пехотная дивизия (Кантара)", "red", "QantaraWest", EG_INF, EG_AD, 1, "qantara", "форсирование 6.10"),
    ("red_2id", "2-я пехотная дивизия (Фирдан)", "red", "Ismailia", EG_INF, EG_AD, 1, "firdan", ""),
    ("red_16id", "16-я пехотная дивизия (Девесуар)", "red", "Deversoir", EG_INF, EG_AD, 1, "center", ""),
    ("red_7id", "7-я пехотная дивизия (3-я армия)", "red", "Suez", EG_INF, EG_AD, 1, "south", ""),
    ("red_19id", "19-я пехотная дивизия (3-я армия)", "red", "Geneifa", EG_INF, EG_AD, 1, "south", ""),
    ("red_21ad", "21-я бронетанковая дивизия", "red", "TellElKebir", EG_ARM, EG_AD, 7, "center", "переправа 13.10, удар 14.10"),
    ("red_4ad", "4-я бронетанковая дивизия", "red", "Km101", EG_ARM, EG_AD, 7, "south", "переправа частью сил 13.10"),
    ("red_23md", "23-я механизированная дивизия", "red", "TellElKebir", EG_MECH, EG_AD, 2, None, "резерв 2-й армии"),
    ("red_6md", "6-я механизированная дивизия", "red", "Km101", EG_MECH, EG_AD, 2, None, "резерв 3-й армии"),
    ("red_ismailia", "Гарнизон Исмаилии (коммандос, 182-я пдбр)", "red", "Ismailia", EG_GAR, {"SA-18 Igla manpad": 4}, 1, None,
     "Исмаилию 22.10 не взяли"),
    ("red_suez", "Гарнизон Суэца (19-я пд, ополчение)", "red", "Suez", EG_GAR, {"SA-18 Igla manpad": 4}, 1, None,
     "штурм 24.10 отбит"),
    ("red_qantara_w", "Тыловые части 2-й армии (Кантара-Запад)", "red", "QantaraWest", EG_GAR, {}, 1, None, ""),
    # Израиль: опорные пункты линии Бар-Лева, 252-я дивизия (Мандлер) в Синае, резервные дивизии
    ("blue_fort_qantara", "Опорные пункты Кантары (линия Бар-Лева)", "blue", "QantaraEast", IL_FORT, {}, 1, None, "сдан 9.10"),
    ("blue_fort_firdan", "Опорные пункты у Фирдана", "blue", "Firdan", IL_FORT, {}, 1, None, ""),
    ("blue_fort_matzmed", "Опорный пункт 'Мацмед'", "blue", "Matzmed", IL_FORT, {}, 1, None, ""),
    ("blue_fort_lakekan", "Опорный пункт 'Лакекан' (Китайская ферма)", "blue", "ChineseFarm", IL_FORT, {}, 1, None, ""),
    ("blue_fort_tewfik", "Опорный пункт 'Мезах' (Порт-Тауфик)", "blue", "PortTewfik", IL_FORT, {}, 1, None, "сдан 13.10"),
    ("blue_14bde", "14-я бронетанковая бригада (Амнон Решеф)", "blue", "Tasa", IL_BDE, IL_AD, 1, None, "252-я дивизия"),
    ("blue_401bde", "401-я бронетанковая бригада (Дан Шомрон)", "blue", "Mitla", IL_BDE, IL_AD, 1, None,
     "252-я дивизия; перевалы 14.10 удержаны"),
    ("blue_460bde", "460-я бронетанковая бригада (Габи Амир)", "blue", "Giddi", IL_BDE, IL_AD, 1, None, "252-я дивизия"),
    ("blue_162div", "162-я дивизия (Адан)", "blue", "Baluza", IL_DIV, IL_AD, 3, None, "резерв: подход 7-8.10"),
    ("blue_143div", "143-я дивизия (Шарон)", "blue", "Tasa", IL_DIV, IL_AD, 3, "gazelle", "резерв; переправа 15-16.10"),
    ("blue_146div", "146-я дивизия (Каланит)", "blue", "Refidim", IL_DIV, IL_AD, 6, None, "ОЦЕНКА"),
    ("blue_247para", "247-я парашютно-десантная бригада (Дани Мат)", "blue", "Tasa", IL_PARA, {}, 9, "gazelle", "первой - через канал"),
]
G.AIR_ASSAULT = []

KUB = [("Kub_1S91_str", "radar", 1), ("Kub_2P25_ln", "launcher", 4)]
S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 6)]
S125 = [("p-19 s-125 sr", "radar", 1), ("snr s-125 tr", "radar", 1), ("5p73 s-125 ln", "launcher", 4)]
HAWK = [("Hawk_sr", "radar", 1), ("Hawk_tr", "radar", 1), ("Hawk_pcp", "control", 1), ("Hawk_ln", "launcher", 6)]
# "зонтик" ЗРК Египта: Куб - у канала (переправлялись за войсками), С-75 и С-125 - на западном берегу (ОЦЕНКА мест)
G.SAMS = ([(f"red_kub_{i}", f"Батарея Куб №{i}", "red", "sam_medium", KUB, la, lo) for i, (la, lo) in
           enumerate([(30.78, 32.22), (30.58, 32.20), (30.38, 32.24), (30.12, 32.42), (29.98, 32.45), (30.70, 32.15)], 1)]
          + [(f"red_s75_{i}", f"Дивизион С-75 №{i}", "red", "sam_medium", S75, la, lo) for i, (la, lo) in
             enumerate([(30.65, 32.05), (30.35, 32.05), (30.05, 32.25), (30.45, 31.80), (30.10, 31.45)], 1)]
          + [(f"red_s125_{i}", f"Дивизион С-125 №{i}", "red", "sam_medium", S125, la, lo) for i, (la, lo) in
             enumerate([(30.80, 32.12), (30.48, 32.12), (30.22, 32.28), (30.60, 31.95)], 1)]
          + [("blue_hawk_refidim", "Батарея HAWK (Рефидим)", "blue", "sam_medium", HAWK, 30.38, 33.12),
             ("blue_hawk_tasa", "Батарея HAWK (Таса)", "blue", "sam_medium", HAWK, 30.48, 32.95)])
G.DEPOTS = [("red_depot_ismailia", "Склады 2-й армии (Исмаилия)", "red", "Ismailia"),
            ("red_depot_suez", "Склады 3-й армии (Суэц)", "red", "Suez"),
            ("red_depot_tellelkebir", "Склады (Тель-эль-Кебир)", "red", "TellElKebir"),
            ("blue_depot_refidim", "Склады Южного округа (Рефидим)", "blue", "Refidim"),
            ("blue_depot_tasa", "Склад снабжения (Таса)", "blue", "Tasa"),
            ("blue_depot_elarish", "Склад снабжения (Эль-Ариш)", "blue", "ElArish")]
G.BRIDGES = [   # понтонные переправы через канал (египетские - с 6.10; у Девесуара - израильская, 16-17.10)
    {"id": "br_qantara", "name": "Переправа у Кантары", "lat": 30.855, "lon": 32.325, "links": [["QantaraWest", "QantaraEast"]],
     "source": "ОЦЕНКА места"},
    {"id": "br_firdan", "name": "Переправа у Фирдана (Исмаилия)", "lat": 30.65, "lon": 32.33, "links": [["Ismailia", "Firdan"]],
     "source": "ОЦЕНКА места"},
    {"id": "br_deversoir", "name": "Переправа у Девесуара (египетская)", "lat": 30.44, "lon": 32.37, "links": [["Deversoir", "ChineseFarm"]],
     "source": "ОЦЕНКА места"},
    {"id": "br_matzmed", "name": "Переправа у Мацмеда (израильская, 16-17.10)", "lat": 30.41, "lon": 32.355,
     "links": [["Matzmed", "Deversoir"]], "source": "ОЦЕНКА места"},
    {"id": "br_suez", "name": "Переправа у Суэца", "lat": 29.96, "lon": 32.55, "links": [["Suez", "PortTewfik"]],
     "source": "ОЦЕНКА места"},
]
G.AIR = [   # (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание[, доп.])
    ("i_f4_hz", "Эскадрильи F-4E 'Курнас' (Хацор)", "blue", "fighter_bomber", "F_4E_45MC", "Hatzor", 36, 500, ""),
    ("i_f4_tn", "Эскадрильи F-4E (Тель-Ноф)", "blue", "fighter_bomber", "F_4E_45MC", "Tel Nof", 24, 500, ""),
    ("i_a4_hz", "Эскадрильи A-4 'Скайхок' (Хацерим)", "blue", "fighter_bomber", "A_4E_C", "Hatzerim", 50, 400,
     "мод A-4E-C: без мода части в кампании нет", {"mod": "a4ec"}),
    ("i_a4_rf", "Эскадрилья A-4 (Рефидим)", "blue", "fighter_bomber", "A_4E_C", "Melez", 16, 300,
     "мод A-4E-C", {"mod": "a4ec"}),
    ("i_nesher", "Эскадрильи 'Нешер' и 'Мираж' IIICJ", "blue", "fighter", "Mirage_F1CE", "Hatzor", 50, 450,
     "Нешер/Мираж III - Mirage F1CE"),
    ("i_nesher_rf", "Дежурное звено 'Мираж' (Рефидим)", "blue", "fighter", "Mirage_F1CE", "Melez", 12, 400, ""),
    ("i_ch53", "114-я эскадрилья (CH-53)", "blue", "transport_helo", "CH_53E", "Bir Hasanah", 8, 200, "CH-53D - CH-53E"),
    ("e_mig21_in", "Истребительные эскадрильи (МиГ-21МФ, Иншас)", "red", "fighter", "MiG_21Bis", "Inshas Airbase", 40, 250,
     "МиГ-21МФ - МиГ-21бис"),
    ("e_mig21_ab", "Истребительные эскадрильи (МиГ-21, Абу-Сувейр)", "red", "fighter", "MiG_21Bis", "Abu Suwayr", 30, 250, ""),
    ("e_mig21_ma", "Истребительные эскадрильи (МиГ-21, Мансура)", "red", "fighter", "MiG_21Bis", "Al Mansurah", 30, 250, ""),
    ("e_su7", "Истребительно-бомбардировочные эскадрильи (Су-7БМК)", "red", "fighter_bomber", "Su_17M4", "As Salihiyah", 40, 300,
     "Су-7БМК - Су-17М4"),
    ("e_mig17", "Истребительно-бомбардировочные эскадрильи (МиГ-17Ф)", "red", "fighter_bomber", "MiG_15bis", "Bilbeis Air Base", 40,
     200, "МиГ-17 - МиГ-15бис"),
    ("e_mi8", "Вертолётные эскадрильи (Ми-8)", "red", "transport_helo", "Mi_8MT", "Fayed", 20, 150, ""),
]
G.AD_TEMPLATES = {
    "red": {"short": [{"name": "ЗУ-23, ПЗРК", "composition": [("Ural_375_ZU_23", "launcher", 2), ("SA-18 Igla manpad", "launcher", 2)]}]},
    "blue": {"short": [{"name": "Вулкан", "composition": [("Vulcan", "launcher", 4)]}]},
}
G.SSM = []
G.EW = []
G.FRONT_KM = 30
# исторический ход (ОЦЕНКИ): Египет - "зонтик" ЗРК и плацдармы 6-9.10, оборона 10-13.10, наступление 14.10 (разгром),
# затем оборона; Израиль - контрудар 8.10 (неудача), оборона, с 15.10 - переправа и наступление на западном берегу
G.EXTRA_VARIANT = {
    "posture": {"red": "offense", "blue": "defense"},
    "objectives": {"red": {k: v["objectives"] for k, v in G.AXES.items()},
                   "blue": {"gazelle": ["Matzmed", "Deversoir", "Fayed", "Geneifa", "Adabiya"]}},   # "Абирей-Лев": переправа
}
G.POSTURE_DAYS = [{"from_day": 5, "red": "defense"}, {"from_day": 9, "red": "offense", "umbrella": {"red": False}},
                  {"from_day": 10, "red": "defense", "umbrella": {"red": True}, "halt": ["red"], "blue": "offense"},
                  {"from_day": 18, "blue": "defense"}]
G.URBAN = {"Suez": 3.0, "Ismailia": 3.0, "PortSaid": 2.5, "QantaraEast": 1.5, "PortTewfik": 3.0,
           "ChineseFarm": 1.5}   # Китайская ферма - оросительные каналы и позиции 16-й пд: обход к переправе южнее   # "Мезах" - неделя осады
G.GARRISON = {"blue_fort_qantara", "blue_fort_firdan", "blue_fort_matzmed", "blue_fort_lakekan", "blue_fort_tewfik", "blue_401bde", "blue_460bde",
              "red_ismailia", "red_suez", "red_qantara_w"}   # перевалы держат, египетские города - гарнизоны
# потери танков ~3:1 в пользу Израиля в маневренных боях (Herzog); опорные пункты линии Бар-Лева - малые
# гарнизоны без танков (ОЦЕНКИ)
G.QUALITY = {"*:blue": 2.0, "blue_fort_firdan": 0.8, "blue_fort_qantara": 1.0}
G.HISTORICAL = True

if __name__ == "__main__":
    G.main()
    import json
    op = G.DATA / "oob_sinai73.json"
    oob = json.loads(op.read_text(encoding="utf-8"))
    # воздушная война: "зонтик" ЗРК 6-7.10 - тяжёлые потери ВВС Израиля над каналом; в воздушных боях - ~10:1 в
    # пользу Израиля (Herzog). ОЦЕНКИ
    oob["air_war"] = {"air_skill": {"blue": 2.5, "red": 0.6}, "sam_loss_k": {"blue": 1.3}}
    # плацдармы: пехотные дивизии, взявшие свои опорные пункты, закрепляются (El Shazly: "оперативная пауза" 9-13.10)
    dig = {"red_18id": ["QantaraEast"], "red_2id": ["Firdan"], "red_16id": ["ChineseFarm"], "red_7id": ["PortTewfik"],
           "red_19id": ["PortTewfik"]}
    for u in oob["units"]:
        if u["id"] in dig:
            u["dig_in_at"] = dig[u["id"]]
    op.write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")

"""Абхазия, сентябрь 1993: последнее наступление на Сухуми (карта DCS Caucasus) -> sector_abkhazia.json, oob_abkhazia.json.

16-27 сентября 1993 г. абхазские силы с добровольцами Конфедерации горских народов Кавказа (КГНК) и армянским
батальоном им. Баграмяна нарушили перемирие (Сочинское соглашение, июль 1993) и наступали на Сухуми с рубежа реки
Гумиста и из осаждённого Ткварчели - на Очамчире (перерезать дорогу Сухуми - Зугдиди). 27.09 Сухуми взят, к 30.09
грузинские войска отошли за Ингури. Грузия перебрасывала подкрепления в Сухуми самолётами - в аэропорту Бабушара
21-23.09 сбиты Ту-134 и Ту-154 (ПЗРК). Российская помощь абхазской стороне (Гудаута, Су-25, Су-27; Су-27 сбит над
Сухуми 19.03.1993) - официально не признана, в сценарии - как скрытая поддержка (спорно, ОЦЕНКА).

Красные - Абхазия и союзники, синие - Грузия. Источники (по памяти - проверить): C. Zürcher, 'The Post-Soviet Wars'
(2007); HRW 'Georgia/Abkhazia: Violations of the Laws of War' (1995); С. Шамба / Т. Ачугба (абх.), Г. Лордкипанидзе
(груз.) - стороны оценивают по-разному. Координаты - ОЦЕНКИ (+-2 км), составы и числа - ОЦЕНКИ по порядку величины.
Генератор - gen_caucasus.py с данными этого сценария.
"""
from __future__ import annotations

import gen_caucasus as G

G.NAME = "abkhazia"
G.ROOT = "Sukhumi"
G.SRC = "Zürcher 'Post-Soviet Wars' (2007) / HRW (1995), по памяти - проверить"
G.TITLE, G.YEAR, G.DATE = "Абхазия, сентябрь 1993: штурм Сухуми", 1993, "1993-09-16"
G.COUNTRIES = {"red": "Abkhazia", "blue": "Georgia"}
G.DOCTRINE = {"red": "wp", "blue": "wp"}          # обе стороны - постсоветские армии (уставы ВС СССР)
G.SECTOR_ABOUT = ("Абхазия, сентябрь 1993. Генерирован tools/gen_abkhazia.py. Координаты - ОЦЕНКИ (+-2 км). Стороны - "
                  "16.09.1993: фронт по Гумисте у Сухуми, Ткварчели - абхазский анклав в окружении.")
G.OBJ_ABOUT = "Оси абхазской стороны - по ходу наступления 16-30.09.1993 (Сухуми; Ткварчели - Очамчире - Гали), ОЦЕНКА."
G.OOB_ABOUT = ("Состав сил 16.09.1993 (Абхазия, КГНК, скрытая поддержка России - Грузия). Генерирован tools/gen_abkhazia.py; "
               "источники - в поле source. Числа - ОЦЕНКИ по порядку величины.")
G.STRATEGIC = {}
G.TASK_RULES = {"blue": {"strike_airfield": {"off": True, "why": "Гудаута - база российских войск: удар по ней - война с Россией"}}}
G.NOT_INCLUDED = ("Морские десанты (Тамыш, 2.07.1993), катера; ополчение Мегрелии и сторонники Гамсахурдиа (гражданская "
                  "война в Грузии); Ту-134/Ту-154 транспортной авиации (в DCS - Ан-26 / Як-40); 'Мхедриони' - в составе "
                  "грузинских частей.")

G.PLACES = {
    # Россия (тыл абхазской стороны: добровольцы КГНК, снабжение через Псоу)
    "Sochi": (43.430, 39.925, "red"), "Adler": (43.440, 39.920, "red"),
    # Абхазия под контролем Гудауты
    "Gagra": (43.330, 40.250, "red"), "Gudauta": (43.104, 40.627, "red"), "NewAthos": (43.090, 40.810, "red"),
    "Eshera": (43.055, 40.925, "red"), "Tkvarcheli": (42.854, 41.684, "red"),
    # под контролем Тбилиси
    "Sukhumi": (43.003, 41.015, "blue"), "Babushara": (42.858, 41.128, "blue"), "Kelasuri": (42.985, 41.070, "blue"),
    "Ochamchire": (42.713, 41.468, "blue"), "Gali": (42.627, 41.737, "blue"), "Azhara": (43.100, 41.760, "blue"),
    "Zugdidi": (42.509, 41.871, "blue"), "Khobi": (42.315, 41.898, "blue"), "Jvari": (42.720, 42.050, "blue"),
    "Senaki": (42.270, 42.067, "blue"), "Poti": (42.146, 41.672, "blue"), "Samtredia": (42.163, 42.340, "blue"),
    "Kutaisi": (42.267, 42.718, "blue"), "Kobuleti": (41.820, 41.776, "blue"), "Batumi": (41.643, 41.640, "blue"),
}
G.LINKS = [
    ("Adler", "Sochi"), ("Adler", "Gagra"), ("Gagra", "Gudauta"), ("Gudauta", "NewAthos"), ("NewAthos", "Eshera"),
    ("Eshera", "Sukhumi"),                         # мост через Гумисту - линия фронта
    ("Sukhumi", "Kelasuri"), ("Kelasuri", "Babushara"), ("Babushara", "Ochamchire"), ("Kelasuri", "Azhara"),
    ("Ochamchire", "Tkvarcheli"), ("Ochamchire", "Gali"), ("Gali", "Zugdidi"), ("Zugdidi", "Jvari"),
    ("Zugdidi", "Khobi"), ("Khobi", "Senaki"), ("Senaki", "Poti"), ("Senaki", "Samtredia"), ("Samtredia", "Kutaisi"),
    ("Poti", "Kobuleti"), ("Kobuleti", "Batumi"),
]
G.SUPPLY_ENTRY = {"red": ["Adler"], "blue": ["Kutaisi", "Samtredia"]}
G.EXTERNAL_SUPPLY = {"Gudauta", "Sochi-Adler"}   # российские аэродромы: снабжение из России, не со складов Абхазии
G.OFF_LIMITS = {"blue": ["Sochi", "Adler"]}       # Грузия не действует на территории России
G.AIRBASES = {"red": ["Gudauta", "Sochi-Adler"], "blue": ["Sukhumi-Babushara", "Senaki-Kolkhi", "Kutaisi", "Kobuleti"]}
G.AXES = {
    "sukhumi": {"title": "Гумиста - Сухуми", "objectives": ["Sukhumi", "Kelasuri", "Babushara"]},
    "east": {"title": "Ткварчели - Очамчире - Гали", "objectives": ["Ochamchire", "Gali"]},
}

c = G.comp
ABKH = c(("T_72B", 6, "MBT"), ("T_55", 6, "MBT"), ("BMP_1", 15, "IFV"), ("BTR_70", 10, "APC"))   # абх. гвардия: бригада
KGNK = c(("BTR_70", 8, "APC"), ("BRDM_2", 4, "APC"))                     # добровольцы КГНК, батальон - лёгкий
ARMEN = c(("BMP_1", 6, "IFV"), ("BTR_70", 4, "APC"))
TKV = c(("T_55", 3, "MBT"), ("BMP_1", 6, "IFV"), ("BTR_70", 4, "APC"))     # гарнизон Ткварчели (в окружении)
GE_BDE = c(("T_55", 10, "MBT"), ("T_72B", 6, "MBT"), ("BMP_2", 12, "IFV"), ("BTR_70", 12, "APC"), ("MTLB", 10, "APC"))
GE_LIGHT = c(("BTR_70", 10, "APC"), ("MTLB", 6, "APC"))
AB_AD = {"ZU_23_Emplacement": 4, "SA_18_Igla_manpad": 4}
GE_AD = {"Ural_375_ZU_23": 4, "SA_18_Igla_manpad": 4}

# (id, имя, сторона, пункт, состав, ПВО, день ввода, ось, примечание)
G.GROUND = [
    ("red_ab_guard1", "Абхазская гвардия (Гумистинский фронт)", "red", "Eshera", ABKH, AB_AD, 1, "sukhumi",
     "наступление через Гумисту 16.09"),
    ("red_ab_guard2", "Абхазская гвардия (Гудаутская бригада)", "red", "NewAthos", ABKH, AB_AD, 1, "sukhumi", ""),
    ("red_kgnk", "Добровольцы КГНК (батальоны северокавказских добровольцев)", "red", "Eshera", KGNK, {"SA_18_Igla_manpad": 4},
     1, "sukhumi", "Конфедерация горских народов Кавказа; число - ОЦЕНКА"),
    ("red_bagramyan", "Батальон им. Баграмяна", "red", "NewAthos", ARMEN, {"SA_18_Igla_manpad": 2}, 2, "sukhumi",
     "армянский батальон; ввод - ОЦЕНКА"),
    ("red_tkv", "Гарнизон Ткварчели (Восточный фронт)", "red", "Tkvarcheli", TKV, {"ZU_23_Emplacement": 2}, 1, "east",
     "анклав в окружении; снабжение - вертолётами"),
    ("blue_ge_sukhumi", "Сухумская группировка грузинских войск (Нацгвардия, Мхедриони)", "blue", "Sukhumi", GE_BDE, GE_AD,
     1, None, "оборона Сухуми"),
    ("blue_ge_kelasuri", "Грузинская бригада (Келасури)", "blue", "Kelasuri", GE_BDE, GE_AD, 1, None, ""),
    ("blue_ge_ochamchire", "Грузинские части в Очамчире (блокада Ткварчели)", "blue", "Ochamchire", GE_LIGHT, GE_AD, 1, None, ""),
    ("blue_ge_gali", "Резерв (Гали)", "blue", "Gali", GE_LIGHT, {}, 1, None, ""),
    ("blue_ge_reinf", "Подкрепления из Грузии (воздушный мост на Бабушару)", "blue", "Zugdidi", GE_LIGHT, GE_AD, 3, None,
     "переброска самолётами 20-23.09 - ОЦЕНКА"),
    ("blue_ge_svan", "Сванские отряды (Кодори)", "blue", "Azhara", c(("BTR_70", 4, "APC")), {}, 1, None, ""),
]

S75 = [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1), ("S_75M_Volhov", "launcher", 3)]
G.SAMS = [   # Су-27 сбит над Сухуми 19.03.1993 - по сообщениям ракетой С-75 грузинской стороны (спорно); место - ОЦЕНКА
    ("blue_s75_sukhumi", "Дивизион С-75 (Сухуми)", "blue", "sam_medium", S75, 42.990, 41.060),
    ("red_strela_gudauta", "ПВО российского гарнизона Гудауты (Стрела-10, ЗСУ-23-4)", "red", "sam_short",
     [("Strela_10M3", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)], 43.110, 40.580),
]
G.DEPOTS = [
    ("red_depot_gudauta", "Склад снабжения (Гудаута)", "red", "Gudauta"),
    ("red_depot_tkv", "Склад гарнизона (Ткварчели)", "red", "Tkvarcheli"),
    ("blue_depot_sukhumi", "Склад снабжения (Сухуми)", "blue", "Sukhumi"),
    ("blue_depot_zugdidi", "Склад снабжения (Зугдиди)", "blue", "Zugdidi"),
    ("blue_depot_senaki", "Склад снабжения (Сенаки)", "blue", "Senaki"),
]
G.BRIDGES = [
    {"id": "br_gumista", "name": "Мост через Гумисту (Сухуми)", "lat": 43.030, "lon": 40.975,
     "links": [["Eshera", "Sukhumi"]], "source": "по памяти - проверить (зонд карты)"},
    {"id": "br_inguri", "name": "Мост через Ингури (Рухи)", "lat": 42.565, "lon": 41.790,
     "links": [["Gali", "Zugdidi"]], "source": "по памяти - проверить (зонд карты)"},
]
# (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
G.AIR = [
    ("ru_su25", "Су-25 (скрытая поддержка России, Гудаута)", "red", "attack", "Su_25", "Gudauta", 6, 250,
     "удары по Сухуми приписываются российской авиации; Россия отрицала - спорно, ОЦЕНКА"),
    ("ru_su27", "Су-27 (скрытая поддержка России, Гудаута)", "red", "fighter", "Su_27", "Gudauta", 4, 400,
     "Су-27 сбит над Сухуми 19.03.1993; число - ОЦЕНКА"),
    ("ab_l39", "ВВС Абхазии (Л-39)", "red", "attack", "L_39C", "Gudauta", 2, 150, ""),
    ("ab_mi8", "ВВС Абхазии (Ми-8: снабжение Ткварчели)", "red", "transport_helo", "Mi_8MT", "Gudauta", 4, 200,
     "Ми-8 с беженцами сбит у Лата 14.12.1992 - вертолёты летали в Ткварчели"),
    ("ge_su25", "ВВС Грузии (Су-25)", "blue", "attack", "Su_25", "Senaki-Kolkhi", 4, 250, "Марнеули - вне сцены, Сенаки"),
    ("ge_l39", "ВВС Грузии (Л-39)", "blue", "attack", "L_39C", "Kutaisi", 2, 150, ""),
    ("ge_mi24", "Вертолёты Грузии (Ми-24)", "blue", "attack_helo", "Mi_24P", "Sukhumi-Babushara", 8, 150, "число - ОЦЕНКА"),
    ("ge_mi8", "Вертолёты Грузии (Ми-8)", "blue", "transport_helo", "Mi_8MT", "Senaki-Kolkhi", 6, 200, ""),
    ("ge_airlift", "Воздушный мост на Сухуми (Ту-134/Ту-154; в DCS - Ан-26)", "blue", "transport", "An_26B", "Kutaisi", 4, 400,
     "21-23.09 в Бабушаре сбиты Ту-134 и Ту-154"),
]
G.AD_TEMPLATES = {
    "red": {"short": [{"name": "ЗУ-23, ПЗРК", "composition": [("ZU_23_Emplacement", "launcher", 2), ("SA_18_Igla_manpad", "launcher", 2)]}]},
    "blue": {"short": [{"name": "ЗУ-23, ПЗРК", "composition": [("ZU_23_Emplacement", "launcher", 2), ("SA_18_Igla_manpad", "launcher", 2)]}]},
}
G.SSM = []

if __name__ == "__main__":
    G.main()

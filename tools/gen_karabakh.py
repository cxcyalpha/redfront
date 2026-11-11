"""Карабах, 27.09-10.11.2020: 44-дневная война (условная география на карте Caucasus) -> sector_karabakh.json, oob_karabakh.json.

27.09-10.11.2020: наступление Азербайджана на Нагорный Карабах. Главное в войне - ударные беспилотники (Bayraktar TB2,
барражирующие боеприпасы "Харопа") против ПВО советских образцов (Оса, Стрела-10, Куб, С-300ПС) и бронетехники,
наступление на юге (Физули, Джебраил, Гадрут, Зангелан, Кубатлы) и выход к Шуше (взята 8.11). ОТР: Армения - Точка-У,
Скад ("Эльбрус"), по сообщениям - Искандер (спорно); удары по Гяндже и Барде. Война закончилась перемирием 10.11.

Красные - Азербайджан, синие - Армения и Нагорный Карабах. Условная география (биом, не перенос театра): низменность
у Куры - Квемо-Картли (Гянджа - Тбилиси, Барда - Рустави, Бейлаган - Марнеули), нагорье Карабаха - плато Тетрицкаро
и Триалети (Шуша - Тетрицкаро на плато, Степанакерт - Манглиси), Лачинский коридор - Цалка, Армения - Ахалкалаки.
Высоты похожи (низменность ~400 м, нагорье 1100-1700 м), расстояния - близки (ОЦЕНКА).

Источники (по памяти - проверять): М. Кофман и др. о войне 2020 (CNA), оценки Oryx (визуально подтверждённые потери),
отчёты HRW/Amnesty об ударах по Гяндже и Барде. Типы DCS - ближайшие: TB2 - MQ-9 Reaper (TB2 в DCS нет; MQ-9 крупнее,
с управляемыми бомбами - как MAM-L); Тор-М2КМ - CHAP_TorM2 (CurrentHill); С-300ПМУ2 - С-300ПС. Составы и числа - ОЦЕНКИ.
"""
from __future__ import annotations

import gen_caucasus as G

G.NAME = "karabakh"
G.ROOT = "Stepanakert"
G.SRC = "Kofman (CNA) / Oryx / HRW (2020-21), по памяти - проверить"
G.TITLE, G.YEAR, G.DATE = "Карабах, сентябрь 2020: 44-дневная война", 2020, "2020-09-27"
G.COUNTRIES = {"red": "Azerbaijan", "blue": "Armenia"}   # в DCS таких стран нет: части - в CJTF (как везде), имена - для ливрей
G.DOCTRINE = {"red": "wp", "blue": "wp"}          # постсоветские армии (Азербайджан - с турецким влиянием, ОЦЕНКА)
G.SECTOR_ABOUT = ("Карабах, 27.09.2020. Генерирован tools/gen_karabakh.py. Условная география на карте Caucasus "
                  "(Квемо-Картли и Триалети); координаты - ОЦЕНКИ.")
G.OBJ_ABOUT = "Оси Азербайджана - по ходу войны: юг (Физули - Джебраил - Гадрут - Шуша), Зангелан - Кубатлы - Лачин, Агдам."
G.OOB_ABOUT = ("Состав сил 27.09.2020 (Азербайджан - Армения и Нагорный Карабах). Генерирован tools/gen_karabakh.py; "
               "источники - в поле source. Числа - ОЦЕНКИ по порядку величины.")
G.STRATEGIC = {"blue": {"tochka": 12, "scud": 6, "iskander": 2}, "red": {"tochka": 6}}
G.TASK_RULES = {"red": {"strike_airfield": {"off": True, "why": "аэродромы Армении - вне войны (удары по Армении не наносились)"}}}
G.NOT_INCLUDED = ("барражирующие боеприпасы (Харопа, Скайстрайкер - в DCS нет), РСЗО (Смерч, Полонез), Ан-2 - ложные цели, "
                  "сирийские наёмники, удары по городам (в модели цели - склады и аэродромы).")
G.EXTRA_VARIANT = {"posture": {"red": "offense", "blue": "defense"}}
G.SAM_FIXED = True       # позиции ЗРК вскрыты разведкой и беспилотниками в первые дни - цели ударов

G.PLACES = {
    # Азербайджан (низменность у Куры)
    "Ganja": (41.716, 44.783, "red"),        # Тбилиси
    "Barda": (41.549, 44.993, "red"),        # Рустави
    "Tartar": (41.780, 44.650, "red"),       # север фронта
    "Beylagan": (41.475, 44.808, "red"),     # Марнеули
    "Horadiz": (41.300, 44.760, "red"),      # Садахло (юг, у Аракса - граница с Армянской ССР)
    # Нагорный Карабах и прилегающие районы
    "Agdam": (41.620, 44.500, "blue"),
    "Martakert": (41.800, 44.300, "blue"),
    "Stepanakert": (41.700, 44.260, "blue"),  # Манглиси (сдвиг на запад 0.12 - аэродромы Азербайджана дальше 30 км)
    "Shusha": (41.545, 44.340, "blue"),      # Тетрицкаро (на плато)
    "Fuzuli": (41.430, 44.480, "blue"),
    "Hadrut": (41.450, 44.240, "blue"),
    "Jabrayil": (41.330, 44.410, "blue"),
    "Zangilan": (41.250, 44.210, "blue"),
    "Kubatli": (41.380, 44.080, "blue"),
    "Lachin": (41.600, 43.970, "blue"),      # Цалка
    # Армения (тыл)
    "Goris": (41.420, 43.360, "blue"),       # Ахалкалаки
}
G.LINKS = [
    ("Ganja", "Barda"), ("Ganja", "Tartar"), ("Barda", "Beylagan"), ("Beylagan", "Horadiz"), ("Barda", "Agdam"),
    ("Tartar", "Martakert"), ("Agdam", "Stepanakert"), ("Martakert", "Stepanakert"), ("Beylagan", "Fuzuli"),
    ("Horadiz", "Jabrayil"), ("Fuzuli", "Jabrayil"), ("Fuzuli", "Hadrut"), ("Jabrayil", "Zangilan"), ("Zangilan", "Kubatli"),
    ("Hadrut", "Shusha"), ("Shusha", "Stepanakert"), ("Shusha", "Lachin"), ("Kubatli", "Lachin"), ("Lachin", "Goris"),
    ("Kubatli", "Goris"),
]
G.SUPPLY_ENTRY = {"red": ["Ganja"], "blue": ["Goris"]}
G.OFF_LIMITS = {"red": ["Goris"]}            # Армения - вне наступления
G.AIRBASES = {"red": ["Tbilisi-Lochini", "Vaziani", "Soganlug"], "blue": ["Kutaisi"]}   # Гянджа, Кюрдамир, ...; Ереван - Кутаиси
G.AXES = {
    "south": {"title": "Юг: Физули - Джебраил - Гадрут - Шуша", "objectives": ["Fuzuli", "Jabrayil", "Hadrut", "Shusha"]},
    "lachin": {"title": "Зангелан - Кубатлы - Лачин", "objectives": ["Zangilan", "Kubatli", "Lachin"]},
    "north": {"title": "Агдам - Мартакерт", "objectives": ["Agdam", "Martakert"]},
}

c = G.comp
AZ_BDE = c(("T_72B", 30, "MBT"), ("T_90", 10, "MBT"), ("BMP_2", 30, "IFV"), ("BTR_82A", 20, "APC"))
AZ_SF = c(("BTR_82A", 12, "APC"))
AR_BDE = c(("T_72B", 25, "MBT"), ("BMP_2", 20, "IFV"), ("BMP_1", 15, "IFV"), ("BTR_70", 10, "APC"))
AR_DEF = c(("T_72B", 10, "MBT"), ("BMP_1", 15, "IFV"), ("BTR_70", 10, "APC"))
AZ_AD = {"Strela_10M3": 2, "ZU_23_Emplacement": 2, "SA_18_Igla_manpad": 4}
AR_AD = {"Osa_9A33_ln": 2, "ZSU_23_4_Shilka": 2, "SA_18_Igla_manpad": 4}

G.GROUND = [
    ("red_az_1", "1-й армейский корпус ВС Азербайджана (бригады)", "red", "Tartar", AZ_BDE, AZ_AD, 1, "north", ""),
    ("red_az_2", "2-й армейский корпус (юг)", "red", "Horadiz", AZ_BDE, AZ_AD, 1, "south", "главный удар на юге"),
    ("red_az_2b", "2-й армейский корпус (Бейлаган)", "red", "Beylagan", AZ_BDE, AZ_AD, 1, "south", ""),
    ("red_az_3", "3-й армейский корпус (Барда)", "red", "Barda", AZ_BDE, AZ_AD, 1, "north", ""),
    ("red_az_sf", "Силы специальных операций Азербайджана", "red", "Horadiz", AZ_SF, {"SA_18_Igla_manpad": 2}, 5, "south",
     "лесом к Шуше (начало ноября)"),
    ("red_az_res", "Резерв (бригады из Гянджи)", "red", "Ganja", AZ_BDE, AZ_AD, 8, "lachin", ""),
    ("blue_ar_martakert", "Армия обороны НКР (Мартакертский район)", "blue", "Martakert", AR_DEF, AR_AD, 1, None, ""),
    ("blue_ar_agdam", "Армия обороны НКР (Агдамский район)", "blue", "Agdam", AR_DEF, AR_AD, 1, None, ""),
    ("blue_ar_fuzuli", "Армия обороны НКР (Физулинский район)", "blue", "Fuzuli", AR_BDE, AR_AD, 1, None, ""),
    ("blue_ar_jabrayil", "Армия обороны НКР (Джебраильский район)", "blue", "Jabrayil", AR_DEF, AR_AD, 1, None, ""),
    ("blue_ar_hadrut", "Армия обороны НКР (Гадрутский район)", "blue", "Hadrut", AR_DEF, AR_AD, 1, None, ""),
    ("blue_ar_shusha", "Гарнизон Шуши", "blue", "Shusha", AR_DEF, AR_AD, 1, None, ""),
    ("blue_ar_reserve", "Резерв ВС Армении (из Армении)", "blue", "Goris", AR_BDE, AR_AD, 4, None, "подход через Лачин"),
]

S300 = [("S-300PS 64H6E sr", "radar", 1), ("S-300PS 40B6M tr", "radar", 1), ("S-300PS 54K6 cp", "control", 1),
        ("S-300PS 5P85C ln", "launcher", 4)]
KUB = [("Kub 1S91 str", "radar", 1), ("Kub 2P25 ln", "launcher", 4)]
BUK = [("SA-11 Buk SR 9S18M1", "radar", 1), ("SA-11 Buk CC 9S470M1", "control", 1), ("SA-11 Buk LN 9A310M1", "launcher", 4)]
G.SAMS = [   # места - ОЦЕНКА; С-300ПС в Карабахе уничтожен в первые дни (по видео ВС Азербайджана)
    ("blue_s300_karabakh", "Дивизион С-300ПС (Карабах)", "blue", "sam_long", S300, 41.640, 44.180),
    ("blue_kub_stepanakert", "Батарея Куб (Степанакерт)", "blue", "sam_medium", KUB, 41.720, 44.300),
    ("blue_tor_lachin", "Батарея Тор-М2КМ (Лачин)", "blue", "sam_short", [("CHAP_TorM2", "launcher", 2)], 41.610, 44.030),
    ("blue_osa_shusha", "Батарея Оса (Шуша)", "blue", "sam_short", [("Osa_9A33_ln", "launcher", 3)], 41.560, 44.310),
    ("red_s300_ganja", "Дивизион С-300ПМУ2 (Гянджа; в DCS - С-300ПС)", "red", "sam_long", S300, 41.760, 44.840),
    ("red_buk_barda", "Дивизион Бук-МБ (Барда)", "red", "sam_medium", BUK, 41.560, 44.940),
]
G.DEPOTS = [
    ("red_depot_ganja", "Склад снабжения (Гянджа)", "red", "Ganja"),
    ("red_depot_barda", "Склад снабжения (Барда)", "red", "Barda"),
    ("red_depot_beylagan", "Передовой склад (Бейлаган)", "red", "Beylagan"),
    ("blue_depot_stepanakert", "Склад снабжения (Степанакерт)", "blue", "Stepanakert"),
    ("blue_depot_shusha", "Склад (Шуша)", "blue", "Shusha"),
    ("blue_depot_goris", "Склад снабжения (Горис)", "blue", "Goris"),
]
G.BRIDGES = [
    {"id": "br_lachin", "name": "Мост в Лачинском коридоре", "lat": 41.590, "lon": 44.150,
     "links": [["Shusha", "Lachin"]], "source": "условно: середина участка Шуша - Лачин"},
]
# (id, имя, сторона, роль, тип, аэродром, число, радиус км, примечание)
G.AIR = [
    ("az_tb2", "Ударные беспилотники Bayraktar TB2 (в DCS - MQ-9)", "red", "fighter_bomber", "MQ_9_Reaper", "Vaziani", 12, 250,
     "TB2 в DCS нет - MQ-9 Reaper; число - ОЦЕНКА (поставки 2020)"),
    ("az_su25", "Штурмовая эскадрилья ВВС Азербайджана (Су-25)", "red", "attack", "Su_25", "Vaziani", 10, 250, "Кюрдамир - Вазиани"),
    ("az_mig29", "Истребительная эскадрилья ВВС Азербайджана (МиГ-29)", "red", "fighter", "MiG_29A", "Tbilisi-Lochini", 10, 300, ""),
    ("az_mi24", "Вертолёты ВВС Азербайджана (Ми-35М; в DCS - Ми-24П)", "red", "attack_helo", "Mi_24P", "Soganlug", 10, 150, ""),
    ("az_mi17", "Вертолёты ВВС Азербайджана (Ми-17)", "red", "transport_helo", "Mi_8MT", "Soganlug", 8, 200, ""),
    ("ar_su25", "Штурмовая эскадрилья ВВС Армении (Су-25)", "blue", "attack", "Su_25", "Kutaisi", 8, 250,
     "Ереван (Эребуни) - Кутаиси"),
    ("ar_su30", "Истребители ВВС Армении (Су-30СМ)", "blue", "fighter", "Su_30SM", "Kutaisi", 4, 400,
     "мод Су-30: без мода части в кампании нет (у Армении нет замены); в войне почти не применялись", {"mod": "su30"}),
    ("ar_mi24", "Вертолёты ВВС Армении (Ми-24П)", "blue", "attack_helo", "Mi_24P", "Kutaisi", 8, 150, ""),
    ("ar_mi8", "Вертолёты ВВС Армении (Ми-8)", "blue", "transport_helo", "Mi_8MT", "Kutaisi", 6, 200, ""),
]
G.AD_TEMPLATES = {
    "red": {"short": [{"name": "Тор, ЗУ-23", "composition": [("Tor_9A331", "launcher", 1), ("ZU_23_Emplacement", "launcher", 2)]}]},
    "blue": {"short": [{"name": "Оса, ЗСУ-23-4", "composition": [("Osa_9A33_ln", "launcher", 1), ("ZSU_23_4_Shilka", "launcher", 2)]}]},
}
G.SSM = [   # (id, имя, сторона, ракета, пусковых, широта, долгота, источник)
    ("blue_tochka", "Дивизион ОТР Точка-У ВС Армении", "blue", "tochka", 4, 41.480, 43.700, "удары по Гяндже и Барде (HRW) - ОЦЕНКА числа"),
    ("blue_scud", "Бригада ОТР Р-17 'Эльбрус' ВС Армении", "blue", "scud", 2, 41.450, 43.600, ""),
    ("blue_iskander", "Дивизион ОТРК Искандер ВС Армении", "blue", "iskander", 2, 41.400, 43.550,
     "применение - спорно (заявления сторон 2021); ОЦЕНКА"),
    ("red_tochka", "Дивизион ОТР Точка-У ВС Азербайджана", "red", "tochka", 2, 41.700, 44.900, "ОЦЕНКА"),
]

if __name__ == "__main__":
    G.main()

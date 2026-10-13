"""Генератор театра всей карты: data/sector_germany.json и data/oob_germany.json.

Источники (в каждом объекте - поле source):
  * OOB-миссия "Germany_OOB_1989" (Schneefl0cke, 2025; сам автор - по Википедии, ошибки допускает): гарнизоны дивизий
    и бригад, аэродромы и численность авиаполков, позиции ЗРК HAWK/Patriot, составы полков 8-й гв. А (шаблоны
    составов советских дивизий). Координаты - из меток миссии, переведённые в широту/долготу.
  * Аэродромы - по терраину pydcs (координаты берёт model.new_campaign), только военные.
  * Координаты городов (пунктов графа) - по памяти, ОЦЕНКА +-2 км; пункты сектора Гамбурга - как в sector_hamburg.json.
  * Всё прочее (составы бригад НАТО, сроки ввода резервов, оси наступления, типы-заменители DCS) - ОЦЕНКИ, помечены.
Запуск: python tools/gen_germany.py  (перезаписывает оба файла).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
MISSION = "OOB-миссия Germany_OOB_1989 (метка)"
MEMORY = "по памяти - проверить"

# ---------------------------------------------------------------- пункты графа (ОЦЕНКА координат, кроме сектора Гамбурга)
PLACES_B = {   # ФРГ
    "Kiel": (54.323, 10.135), "Neumunster": (54.074, 9.982), "Rendsburg": (54.304, 9.663), "Itzehoe": (53.925, 9.516),
    "BadSegeberg": (53.936, 10.309), "Lubeck": (53.866, 10.687), "BadOldesloe": (53.810, 10.374), "Ratzeburg": (53.700, 10.758),
    "Molln": (53.627, 10.687), "Hamburg": (53.551, 9.994), "Stade": (53.600, 9.476), "Buxtehude": (53.477, 9.701),
    "Rotenburg": (53.111, 9.410), "Bremen": (53.079, 8.802), "Verden": (52.923, 9.234), "Nienburg": (52.640, 9.208),
    "Celle": (52.625, 10.081), "Gifhorn": (52.479, 10.546), "Wittingen": (52.727, 10.739), "Wolfsburg": (52.423, 10.787),
    "Hannover": (52.375, 9.732), "Braunschweig": (52.269, 10.521), "Helmstedt": (52.228, 11.010), "Salzgitter": (52.150, 10.330),
    "Hildesheim": (52.151, 9.951), "Goslar": (51.906, 10.429), "Osterode": (51.729, 10.252), "Northeim": (51.706, 9.999),
    "Gottingen": (51.541, 9.915), "Duderstadt": (51.512, 10.259), "Kassel": (51.312, 9.480), "Witzenhausen": (51.341, 9.856),
    "Eschwege": (51.188, 10.053), "BadHersfeld": (50.868, 9.707), "Hunfeld": (50.672, 9.767), "Fulda": (50.551, 9.676),
    "Alsfeld": (50.751, 9.271), "Giessen": (50.584, 8.678), "Frankfurt": (50.110, 8.682), "Hanau": (50.133, 8.917),
    "Gelnhausen": (50.202, 9.188), "BadKissingen": (50.200, 10.077), "BadNeustadt": (50.322, 10.216),
    "Schweinfurt": (50.049, 10.229), "Wurzburg": (49.791, 9.953), "Bamberg": (49.898, 10.902), "Coburg": (50.258, 10.965),
    "Kronach": (50.239, 11.328), "Hof": (50.313, 11.912), "Bayreuth": (49.945, 11.576), "Nurnberg": (49.452, 11.077),
    "Weiden": (49.677, 12.156), "Paderborn": (51.718, 8.757), "Bielefeld": (52.021, 8.532), "Osnabruck": (52.279, 8.047),
}
PLACES_R = {   # ГДР
    "Wismar": (53.893, 11.465), "Grevesmuhlen": (53.863, 11.187), "Schonberg": (53.850, 10.934), "Gadebusch": (53.703, 11.117),
    "Schwerin": (53.635, 11.401), "Hagenow": (53.430, 11.191), "Rostock": (54.092, 12.099), "Gustrow": (53.793, 12.175),
    "Parchim": (53.426, 11.848), "Perleberg": (53.075, 11.858), "Wittenberge": (53.000, 11.750), "Neustrelitz": (53.364, 13.063),
    "Neubrandenburg": (53.557, 13.261), "Neuruppin": (52.924, 12.804), "Kyritz": (52.942, 12.395), "Salzwedel": (52.851, 11.153),
    "Gardelegen": (52.526, 11.395), "Stendal": (52.606, 11.858), "Haldensleben": (52.290, 11.408), "Magdeburg": (52.131, 11.640),
    "Oschersleben": (52.030, 11.225), "Halberstadt": (51.896, 11.047), "Wernigerode": (51.835, 10.785), "Brandenburg": (52.412, 12.532),
    "Burg": (52.272, 11.855), "Dessau": (51.833, 12.246), "Halle": (51.483, 11.970), "Leipzig": (51.340, 12.375),
    "Nordhausen": (51.505, 10.791), "Sangerhausen": (51.473, 11.298), "Muhlhausen": (51.209, 10.455), "Heiligenstadt": (51.378, 10.138),
    "Eisenach": (50.975, 10.320), "Gotha": (50.947, 10.701), "Erfurt": (50.978, 11.029), "Weimar": (50.980, 11.329),
    "Jena": (50.927, 11.589), "Meiningen": (50.568, 10.416), "Suhl": (50.609, 10.692), "Hildburghausen": (50.425, 10.729),
    "Sonneberg": (50.360, 11.170), "Saalfeld": (50.648, 11.365), "Plauen": (50.495, 12.137), "Gera": (50.880, 12.081),
}
MAX_LINK_KM = 70     # ОЦЕНКА: связь графа не длиннее (иначе "дороги" через море и через полстраны)

# ---------------------------------------------------------------- аэродромы (имена - как в терраине pydcs)
AIRBASES = {
    "red": ["Damgarten", "Laage", "Peenemunde", "Neubrandenburg", "Tutow", "Parchim", "Wittstock", "Larz", "Neuruppin",
            "Templin", "Finow", "Werneuchen", "Marxwalde", "Altes Lager", "Brand", "Zerbst", "Kothen", "Merseburg", "Brandis",
            "Holzdorf", "Falkenberg", "Mahlwinkel", "Stendal", "Cochstedt", "Allstedt"],
    "blue": ["Wunstorf", "Celle", "Fassberg", "Buckeburg", "Hildesheim", "Gutersloh", "Norvenich", "Buchel", "Pferdsfeld",
             "Hahn", "Spangdahlem", "Bitburg", "Ramstein", "Sembach", "Zweibrucken", "Fritzlar", "Nordholz", "Uetersen",
             "Giebelstadt"],
}

# ---------------------------------------------------------------- оси наступления ОВД (ОЦЕНКА: общие представления, не документ)
AXES = {
    "north":   {"title": "Шлезвиг-Гольштейн", "objectives": ["Ratzeburg", "Hamburg", "Neumunster", "Kiel"]},
    "elbe":    {"title": "Нижняя Эльба", "objectives": ["Luneburg", "Soltau", "Rotenburg", "Bremen"]},
    "altmark": {"title": "Альтмарк - Целле", "objectives": ["Uelzen", "Celle", "Nienburg"]},
    "center":  {"title": "Хельмштедт - Ганновер", "objectives": ["Braunschweig", "Hildesheim", "Hannover"]},
    "harz":    {"title": "Гёттинген - Кассель", "objectives": ["Gottingen", "Kassel", "Paderborn"]},
    "fulda":   {"title": "Фульдский коридор", "objectives": ["BadHersfeld", "Fulda", "Gelnhausen", "Frankfurt"]},
    "main":    {"title": "Майн", "objectives": ["BadNeustadt", "Schweinfurt", "Wurzburg"]},
    "hof":     {"title": "Хоф - Нюрнберг", "objectives": ["Hof", "Bayreuth", "Nurnberg"]},
}

# ---------------------------------------------------------------- шаблоны составов
# Советские полки - из OOB-миссии (8-я гв. А): МСП на БМП: 142 БМП-2, 40 Т-80; МСП на БТР: 156 БТР-80, 40 Т-80;
# ТП: 94 Т-80, 43 БМП; отдельный тб: 51 Т-80. Дивизия: МСД = МСП(БМП) + 2 МСП(БТР) + ТП + отд. тб; ТД = 3 ТП + МСП(БМП)
# (структура дивизий - ОЦЕНКА по общим данным). ПВО дивизии - сумма ПВО полков из миссии (2С6, Стрела-10, Шилка, Стрела-1).
SOV_MRD = {"MBT": 40 + 80 + 94 + 51, "IFV": 142 + 43, "APC": 312}
SOV_TD = {"MBT": 94 * 3 + 40, "IFV": 43 * 3 + 142, "APC": 0}
SOV_AD_MRD = {"X_2S6_Tunguska": 6, "Strela_10M3": 8, "ZSU_23_4_Shilka": 8, "Strela_1_9P31": 8}
SOV_AD_TD = {"X_2S6_Tunguska": 14, "Strela_10M3": 16}
TANK = {"gsfg": "T_80B", "nva": "T_72B", "nva_res": "T_55"}         # Т-64 в DCS нет; Т-72М ННА - замена Т-72Б (ОЦЕНКА)
IFV = {"gsfg": "BMP_2", "nva": "BMP_1", "nva_res": "BMP_1"}
APC = {"gsfg": "BTR_80", "nva": "BTR_70", "nva_res": "BTR_60"}
# Бригады НАТО - ОЦЕНКА по общим данным (миссия составов не даёт): танки/БМП бригады и войсковая ПВО
NATO = {
    "de_pz":   ({"Leopard_2": 110, "Marder": 60}, {"Gepard": 12}),
    "de_pzg":  ({"Leopard_2": 55, "Marder": 95}, {"Gepard": 12}),
    "de_pzg1": ({"Leopard1A3": 55, "Marder": 95}, {"Gepard": 12}),
    "de_hsch": ({"Leopard1A3": 40, "M_113": 80}, {"Gepard": 6}),
    "uk_armd": ({"Chieftain_mk3": 100, "MCV_80": 45}, {"Rapier_fsa_launcher": 4, "Rapier_fsa_optical_tracker_unit": 2}),
    "us_armd": ({"M_1_Abrams": 116, "M_2_Bradley": 54}, {"Vulcan": 6, "M48_Chaparral": 6}),
    "us_mech": ({"M_1_Abrams": 58, "M_2_Bradley": 108}, {"Vulcan": 6, "M48_Chaparral": 6}),
    "us_acr":  ({"M_1_Abrams": 120, "M_2_Bradley": 115}, {"Vulcan": 6}),
    "nl_mech": ({"Leopard_2": 50, "M_113": 100}, {"Gepard": 9}),
    "be_mech": ({"Leopard1A3": 40, "M_113": 90}, {"Gepard": 6}),
    "dk_mech": ({"Leopard1A3": 30, "M_113": 80}, {}),
}
ROLE_OF = {"Leopard_2": "MBT", "Leopard1A3": "MBT", "Chieftain_mk3": "MBT", "M_1_Abrams": "MBT", "Marder": "IFV",
           "MCV_80": "IFV", "M_2_Bradley": "IFV", "M_113": "APC"}

# ---------------------------------------------------------------- ОВД: дивизии (гарнизоны - метки OOB-миссии)
# (id, имя, армия, тип, широта, долгота, день ввода, ось, примечание)
RED_DIVS = [
    ("94gmsd", "94-я гв. мотострелковая дивизия", "2 гв. ТА", "mrd", 53.636, 11.391, 1, "north", ""),
    ("21msd", "21-я мотострелковая дивизия", "2 гв. ТА", "mrd", 53.004, 11.686, 1, "altmark", ""),
    ("207msd", "207-я мотострелковая дивизия", "2 гв. ТА", "mrd", 53.627, 12.187, 2, "elbe", "метка у Гюстрова; по памяти - Стендаль"),
    ("16gtd", "16-я гв. танковая дивизия", "2 гв. ТА", "td", 53.372, 13.056, 3, "north", ""),
    ("47gtd", "47-я гв. танковая дивизия", "3 УА", "td", 52.337, 11.455, 1, "center", ""),
    ("10gtd", "10-я гв. танковая дивизия", "3 УА", "td", 52.202, 12.168, 2, "center", ""),
    ("12gtd", "12-я гв. танковая дивизия", "3 УА", "td", 53.083, 12.623, 2, "altmark", ""),
    ("7gtd", "7-я гв. танковая дивизия", "3 УА", "td", 52.910, 12.240, 3, "altmark", "метка '7/3'; по памяти гарнизон - Рослау"),
    ("27gmsd", "27-я гв. мотострелковая дивизия", "8 гв. А", "mrd", 51.496, 11.907, 1, "harz", ""),
    ("39gmsd", "39-я гв. мотострелковая дивизия", "8 гв. А", "mrd", 50.837, 10.776, 1, "fulda", ""),
    ("57gmsd", "57-я гв. мотострелковая дивизия", "8 гв. А", "mrd", 51.147, 11.764, 2, "fulda", ""),
    ("79gtd", "79-я гв. танковая дивизия", "8 гв. А", "td", 50.922, 11.573, 1, "main", ""),
    ("9td", "9-я танковая дивизия", "1 гв. ТА", "td", 51.329, 13.282, 3, "hof", ""),
    ("11gtd", "11-я гв. танковая дивизия", "1 гв. ТА", "td", 51.151, 13.873, 3, "hof", ""),
    ("20gmsd", "20-я гв. мотострелковая дивизия", "1 гв. ТА", "mrd", 51.241, 12.711, 2, "hof", ""),
    ("35msd", "35-я мотострелковая дивизия", "20 гв. А", "mrd", 52.619, 13.301, 4, "center", "резерв фронта"),
    ("90gtd", "90-я гв. танковая дивизия", "20 гв. А", "td", 52.719, 13.535, 4, "altmark", "резерв фронта"),
    ("25td", "25-я танковая дивизия", "20 гв. А", "td", 52.444, 14.366, 5, "center", "резерв фронта"),
    ("32gtd", "32-я гв. танковая дивизия", "20 гв. А", "td", 52.012, 13.051, 4, "harz", "резерв фронта"),
]
NVA_DIVS = [
    ("nva8msd", "8-я мотострелковая дивизия ННА", "5 А ННА", "mrd", "nva", 53.454, 11.136, 1, "north", ""),
    ("nva9pd", "9-я танковая дивизия ННА", "5 А ННА", "td", "nva", 53.662, 13.883, 2, "north", ""),
    ("nva1msd", "1-я мотострелковая дивизия ННА", "5 А ННА", "mrd", "nva", 52.472, 13.218, 3, "center", ""),
    ("nva20msd", "20-я мотострелковая дивизия ННА (резерв)", "5 А ННА", "mrd", "nva_res", 53.548, 13.291, 5, "north", ""),
    ("nva4msd", "4-я мотострелковая дивизия ННА", "3 А ННА", "mrd", "nva", 51.003, 11.025, 1, "fulda", ""),
    ("nva11msd", "11-я мотострелковая дивизия ННА", "3 А ННА", "mrd", "nva", 51.475, 11.966, 2, "harz", ""),
    ("nva7pd", "7-я танковая дивизия ННА", "3 А ННА", "td", "nva", 51.049, 13.965, 3, "hof", ""),
    ("nva17msd", "17-я мотострелковая дивизия ННА (резерв)", "3 А ННА", "mrd", "nva_res", 51.584, 12.263, 5, "harz", ""),
]
RED_DAY_NOTE = "день ввода: 1 - на месте, 2-5 - выдвижение из глубины (ОЦЕНКА)"

# ---------------------------------------------------------------- НАТО: бригады (метки OOB-миссии)
# (id, имя, корпус, шаблон, широта, долгота, день ввода, примечание)
BLUE_BDES = [
    ("pzgb16", "Панцергренадерская бригада 16", "LANDJUT", "de_pzg1", 53.444, 10.514, 1, ""),
    ("pzgb17", "Панцергренадерская бригада 17", "LANDJUT", "de_pzg1", 53.611, 10.072, 1, ""),
    ("pzgb18", "Панцергренадерская бригада 18", "LANDJUT", "de_pzg1", 54.082, 10.048, 1, ""),
    ("hschb51", "Бригада территориальной обороны 51", "LANDJUT", "de_hsch", 54.153, 10.552, 1, ""),
    ("pzb1", "Панцербригада 1", "I нем. АК", "de_pz", 52.116, 9.439, 1, ""),
    ("pzb2", "Панцербригада 2", "I нем. АК", "de_pz", 52.271, 10.610, 1, ""),
    ("pzb3", "Панцербригада 3", "I нем. АК", "de_pz", 52.671, 9.174, 1, ""),
    ("pzgb7", "Панцергренадерская бригада 7", "I нем. АК", "de_pzg", 53.574, 9.996, 1, ""),
    ("pzb8", "Панцербригада 8", "I нем. АК", "de_pz", 53.266, 10.377, 1, ""),
    ("pzlb9", "Учебная панцербригада 9", "I нем. АК", "de_pz", 52.955, 10.105, 1, ""),
    ("pzgb31", "Панцергренадерская бригада 31", "I нем. АК", "de_pzg", 53.143, 8.209, 2, ""),
    ("pzgb32", "Панцергренадерская бригада 32", "I нем. АК", "de_pzg", 53.276, 8.683, 2, ""),
    ("pzb33", "Панцербригада 33", "I нем. АК", "de_pz", 52.628, 10.042, 1, ""),
    ("pzgb4", "Панцергренадерская бригада 4", "III нем. АК", "de_pzg", 51.555, 9.901, 1, ""),
    ("pzgb5", "Панцергренадерская бригада 5", "III нем. АК", "de_pzg", 51.258, 9.372, 1, ""),
    ("pzb6", "Панцербригада 6", "III нем. АК", "de_pz", 51.513, 9.379, 1, ""),
    ("pzgb13", "Панцергренадерская бригада 13", "III нем. АК", "de_pzg", 50.576, 8.512, 2, ""),
    ("pzb15", "Панцербригада 15", "III нем. АК", "de_pz", 50.376, 7.562, 3, ""),
    ("pzb34", "Панцербригада 34", "III нем. АК", "de_pz", 50.448, 7.517, 3, ""),
    ("pzgb35", "Панцергренадерская бригада 35", "III нем. АК", "de_pzg", 50.054, 9.823, 1, ""),
    ("pzb36", "Панцербригада 36", "III нем. АК", "de_pz", 49.472, 9.750, 2, ""),
    ("pzgb10", "Панцергренадерская бригада 10", "II нем. АК", "de_pzg", 49.711, 12.164, 1, ""),
    ("pzgb12", "Панцергренадерская бригада 12", "II нем. АК", "de_pzg", 49.490, 11.876, 1, ""),
    ("uk7", "7-я бронетанковая бригада", "I брит. АК", "uk_armd", 53.152, 9.481, 1, ""),
    ("uk12", "12-я бронетанковая бригада", "I брит. АК", "uk_armd", 53.251, 8.491, 2, ""),
    ("uk22", "22-я бронетанковая бригада", "I брит. АК", "uk_armd", 52.815, 9.809, 1, "метка: учебный центр"),
    ("uk4", "4-я бронетанковая бригада", "I брит. АК", "uk_armd", 51.788, 7.891, 2, ""),
    ("uk6", "6-я бронетанковая бригада", "I брит. АК", "uk_armd", 51.554, 8.330, 2, ""),
    ("uk33", "33-я бронетанковая бригада", "I брит. АК", "uk_armd", 51.734, 8.778, 2, ""),
    ("uk11", "11-я бронетанковая бригада", "I брит. АК", "uk_armd", 52.207, 8.718, 2, ""),
    ("uk20", "20-я бронетанковая бригада", "I брит. АК", "uk_armd", 52.035, 8.895, 2, ""),
    ("us3ad1", "1-я бригада 3-й бронетанковой дивизии США", "V амер. АК", "us_armd", 50.528, 9.127, 1, ""),
    ("us3ad2", "2-я бригада 3-й бронетанковой дивизии США", "V амер. АК", "us_armd", 50.215, 9.148, 1, ""),
    ("us3ad3", "3-я бригада 3-й бронетанковой дивизии США", "V амер. АК", "us_armd", 50.398, 8.707, 1, ""),
    ("us11acr", "11-й бронекавалерийский полк США", "V амер. АК", "us_acr", 50.561, 9.598, 1, "прикрытие Фульдского коридора"),
    ("us8id1", "1-я бригада 8-й пехотной дивизии США", "V амер. АК", "us_mech", 50.025, 7.339, 2, ""),
    ("us8id2", "2-я бригада 8-й пехотной дивизии США", "V амер. АК", "us_mech", 49.618, 7.381, 2, ""),
    ("us8id3", "3-я бригада 8-й пехотной дивизии США", "V амер. АК", "us_mech", 49.582, 8.442, 2, ""),
    ("us1ad1", "1-я бригада 1-й бронетанковой дивизии США", "VII амер. АК", "us_armd", 49.488, 11.839, 1, ""),
    ("us1ad2", "2-я бригада 1-й бронетанковой дивизии США", "VII амер. АК", "us_armd", 49.615, 11.001, 1, ""),
    ("us1ad3", "3-я бригада 1-й бронетанковой дивизии США", "VII амер. АК", "us_armd", 49.927, 10.897, 1, ""),
    ("us3id1", "1-я бригада 3-й пехотной дивизии США", "VII амер. АК", "us_mech", 50.057, 10.165, 1, ""),
    ("us3id2", "2-я бригада 3-й пехотной дивизии США", "VII амер. АК", "us_mech", 49.767, 9.483, 1, ""),
    ("us3id3", "3-я бригада 3-й пехотной дивизии США", "VII амер. АК", "us_mech", 49.950, 8.915, 2, ""),
    ("us2acr", "2-й бронекавалерийский полк США", "VII амер. АК", "us_acr", 49.479, 11.075, 1, "прикрытие границы с ЧССР и ГДР"),
    ("us2adf", "Передовая бригада 2-й бронетанковой дивизии США", "III амер. АК", "us_armd", 53.318, 8.703, 1, "Гарльштедт"),
    ("nl41", "41-я бронетанковая бригада (Нидерланды)", "I нидерл. АК", "nl_mech", 53.111, 9.410, 1,
     "в миссии метка в Нидерландах; по памяти - гарнизон Зедорф, ставим в Ротенбург"),
    ("be4", "4-я механизированная бригада (Бельгия)", "I бельг. АК", "be_mech", 51.510, 9.061, 1, ""),
]
# Подкрепления из-за пределов карты (в миссии - в Северном море / в своих странах): вводятся в пункт на западе
REINF = [
    ("nl42", "42-я бронетанковая бригада (Нидерланды)", "I нидерл. АК", "nl_mech", "Verden", 3),
    ("nl43", "43-я механизированная бригада (Нидерланды)", "I нидерл. АК", "nl_mech", "Verden", 3),
    ("be1", "1-я механизированная бригада (Бельгия)", "I бельг. АК", "be_mech", "Paderborn", 3),
    ("be7", "7-я механизированная бригада (Бельгия)", "I бельг. АК", "be_mech", "Paderborn", 4),
    ("dk1", "1-я ютландская бригада (Дания)", "LANDJUT", "dk_mech", "Rendsburg", 2),
    ("dk2", "2-я ютландская бригада (Дания)", "LANDJUT", "dk_mech", "Rendsburg", 3),
    ("uk19", "19-я пехотная бригада (Великобритания)", "I брит. АК", "uk_armd", "Osnabruck", 6),
    ("us2ad1", "1-я бригада 2-й бронетанковой дивизии США", "III амер. АК", "us_armd", "Bremen", 7),
    ("us2ad2", "2-я бригада 2-й бронетанковой дивизии США", "III амер. АК", "us_armd", "Bremen", 8),
    ("us1cd", "1-я кавалерийская дивизия США (бригада)", "III амер. АК", "us_armd", "Osnabruck", 9),
    ("us1id1", "1-я бригада 1-й пехотной дивизии США", "VII амер. АК", "us_mech", "Wurzburg", 7),
    ("us4id1", "1-я бригада 4-й пехотной дивизии США", "V амер. АК", "us_mech", "Frankfurt", 7),
]

# ---------------------------------------------------------------- ЗРК (метки OOB-миссии)
HAWK = {"Hawk_sr": ("radar", 1), "Hawk_tr": ("radar", 1), "Hawk_pcp": ("control", 1), "Hawk_ln": ("launcher", 4)}
PATRIOT = {"Patriot_str": ("radar", 1), "Patriot_ECS": ("control", 1), "Patriot_ln": ("launcher", 6)}
BLUE_SAMS = [   # (id, имя, тип, широта, долгота); батальон = одна батарея в модели (ОЦЕНКА: нагрузка на DCS)
    ("sam39", "39-й зенитный ракетный батальон HAWK (Эккернфёрде)", "hawk", 54.481, 9.793),
    ("sam26", "26-й зенитный ракетный батальон Patriot (Хайде)", "patriot", 54.215, 9.075),
    ("sam37", "37-й зенитный ракетный батальон HAWK (Куксхафен)", "hawk", 53.841, 8.552),
    ("sam36", "36-й зенитный ракетный батальон HAWK (Бремерфёрде)", "hawk", 53.491, 9.134),
    ("sam31", "31-й зенитный ракетный батальон HAWK (Вестертимке)", "hawk", 53.235, 9.120),
    ("sam24", "24-й зенитный ракетный батальон Patriot (Дельменхорст)", "patriot", 53.047, 8.623),
    ("sam25", "25-й зенитный ракетный батальон Patriot (Эйдельштедт)", "patriot", 52.715, 8.536),
    ("sam21", "21-й зенитный ракетный батальон Patriot (Мёнезее)", "patriot", 51.486, 8.093),
    ("sam38", "38-й зенитный ракетный батальон HAWK (Бурбах)", "hawk", 50.745, 7.964),
    ("sam4_43", "4-я батарея 43-го полка Patriot (Гиссен)", "patriot", 50.577, 8.736),
    ("sam3_52", "3-я батарея 52-го полка HAWK (Вильдфлеккен)", "hawk", 50.393, 9.884),
    ("sam43_2", "43-й полк Patriot (Ханау)", "patriot", 50.177, 8.959),
    ("sam52_6", "52-й полк HAWK (Вюрцбург)", "hawk", 49.795, 9.945),
    ("sam8_43", "8-я батарея 43-го полка Patriot (Гибельштадт)", "patriot", 49.659, 9.991),
    ("sam60_3", "60-й полк HAWK (Графенвёр)", "hawk", 49.727, 11.908),
    ("sam43_6", "43-й полк Patriot (Ансбах)", "patriot", 49.317, 10.634),
]
# ЗРК армий ГСВГ: в миссии - "3 дивизиона по 27 SA-4". 2К11 "Круг" в DCS нет - замена "Куб" (ОЦЕНКА, другая система)
KUB = {"Kub_1S91_str": ("radar", 1), "Kub_2P25_ln": ("launcher", 4)}
RED_SAMS = [
    ("sam8ga", "Зенитная ракетная бригада 8-й гв. А (Круг; в DCS - Куб)", "kub", 50.690, 11.331),
    ("sam1gta", "Зенитная ракетная бригада 1-й гв. ТА (Круг; в DCS - Куб)", "kub", 51.014, 13.760),
]

# ---------------------------------------------------------------- объектовая ПВО: позиции по ярусам (ОЦЕНКА)
# Позиция - место и ярус (long / medium / short), без модели: тип ставит шаблон стороны (ad_templates в составе сил),
# часть создаётся при new (model.new_campaign). Правила размещения (все пороги - ОЦЕНКИ, не документ):
#   * short - ПВО объекта у каждого военного аэродрома обеих сторон (AD_AF_OFFSET_KM от центра в сторону фронта);
#   * medium (красные) - сеть ЗРК ПВО ГДР: жадное покрытие красных аэродромов и пунктов - каждый не дальше AD_MED_KM
#     от позиции (дальность С-75 ~43 км); позиции не ближе AD_MED_GAP_KM друг к другу и не ближе AD_FRONT_KM к границе;
#     позиция у аэродрома - в AD_MED_AF_OFFSET_KM от него к фронту, у пункта - в AD_MED_TOWN_OFFSET_KM (не на ВПП и не
#     в городе; на месте её ещё отодвигает от бетона battle_site.lua), не ближе AD_AIRPORT_CLEAR_KM к любому аэродрому;
#   * long (красные) - до AD_LONG_N позиций С-200 в глубине: дальние от границы пункты (не ближе AD_LONG_FRONT_KM
#     к ней), не ближе AD_LONG_GAP_KM друг к другу; позиция - в AD_LONG_OFFSET_KM от пункта в тыл.
# У синих средний и дальний ярус - пояс HAWK/Patriot из OOB-миссии (BLUE_SAMS), он не генерируется.
AD_AF_OFFSET_KM = 1.5
AD_MED_KM, AD_MED_GAP_KM, AD_FRONT_KM = 35, 30, 15
AD_MED_AF_OFFSET_KM = 5      # ОЦЕНКА: позиция ЗРК, прикрывающая аэродром, - не на нём, а в стольких км к фронту
AD_MED_TOWN_OFFSET_KM = 3    # ОЦЕНКА: позиция ЗРК у пункта - не в городе, а в стольких км к фронту
AD_LONG_OFFSET_KM = 4        # ОЦЕНКА: позиция С-200 у пункта - в стольких км в тыл (не там же, где С-75 этого пункта)
AD_AIRPORT_CLEAR_KM = 3      # позиции ЗРК (кроме ПВО аэродрома) - не ближе к любому аэродрому карты (и гражданскому)
AD_LONG_N, AD_LONG_GAP_KM, AD_LONG_FRONT_KM = 4, 100, 60
AD_TEMPLATES = {   # ярус -> варианты; позиция берёт вариант по номеру (variant). Составы - ОЦЕНКИ (одна батарея)
    "red": {
        "long": [{"name": "С-200", "composition": [("RLS_19J6", "radar", 1), ("RPC_5N62V", "radar", 1),
                                                    ("S_200_Launcher", "launcher", 4)]}],
        "medium": [{"name": "С-75", "composition": [("p-19 s-125 sr", "radar", 1), ("SNR_75V", "radar", 1),
                                                     ("S_75M_Volhov", "launcher", 4)]},
                   {"name": "С-125", "composition": [("p-19 s-125 sr", "radar", 1), ("snr s-125 tr", "radar", 1),
                                                      ("5p73 s-125 ln", "launcher", 4)]}],
        "short": [{"name": "Оса, ЗСУ-23-4", "composition": [("Osa_9A33_ln", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)]},
                  {"name": "С-60", "composition": [("SON_9", "radar", 1), ("S-60_Type59_Artillery", "launcher", 4)]}],
    },
    "blue": {
        "short": [{"name": "Roland, Gepard", "composition": [("Roland_Radar", "radar", 1), ("Roland_ADS", "launcher", 2),
                                                              ("Gepard", "launcher", 2)]}],
    },
}
AD_TIER_TITLE = {"long": "ЗРК большой дальности", "medium": "ЗРК средней дальности", "short": "ПВО объекта"}
# КРУ (GCI): в DCS наведением пользуется только игрок на МиГ-29 - пункт у каждого аэродрома красных, где базируется
# МиГ-29, рядом с ПВО аэродрома (в AD_GCI_OFFSET_KM от центра к фронту); у каждого - свой канал, радиус GCI_RADIUS_KM
AD_GCI_TYPES = ("MiG_29_Fulcrum", "MiG_29S", "MiG_29A")
AD_GCI_OFFSET_KM = 3
GCI_RADIUS_KM = 250
AD_TEMPLATES["red"]["gci"] = [{"name": "КРУ", "composition": [("GCI_station_MiG29", "control", 1)]}]


def gci_sites(places: dict, links: set, airbase_pos: dict, air: list) -> list[dict]:
    """КРУ у аэродромов красных, где по составу сил базируется МиГ-29 (AD_GCI_TYPES); канал - по порядку с 1."""
    border = [((places[a]["lat"] + places[b]["lat"]) / 2, (places[a]["lon"] + places[b]["lon"]) / 2)
              for a, b in links if places[a]["side"] != places[b]["side"]]
    bases = sorted({base.lower().replace(" ", "_") for _uid, _n, side, _r, typ, base, *_ in air
                    if side == "red" and typ in AD_GCI_TYPES})
    out = []
    for k, bid in enumerate(bases, 1):
        la, lo, _side, name = airbase_pos[bid]
        q = min(border, key=lambda q: dist_km((la, lo), q))
        f = min(1.0, AD_GCI_OFFSET_KM / (dist_km((la, lo), q) or 1.0))
        out.append({"id": f"red_gci_{bid}", "name": f"КРУ аэродрома {name}", "side": "red", "tier": "gci",
                    "covers": f"af_{bid}", "lat": round(la + (q[0] - la) * f, 4), "lon": round(lo + (q[1] - lo) * f, 4),
                    "variant": 0, "channel": k, "radius_km": GCI_RADIUS_KM,
                    "rule": "КРУ: у аэродрома, где базируется МиГ-29 (наведением в DCS пользуется только он)"})
    return out


def ad_sites(places: dict, links: set, airbase_pos: dict, airports: list[tuple[float, float]] = ()) -> list[dict]:
    """Позиции объектовой ПВО по правилам выше. airbase_pos: id аэродрома -> (широта, долгота, сторона, имя);
    airports - все аэродромы карты (широта, долгота): позиции ЗРК от них отодвигаются."""
    border = [((places[a]["lat"] + places[b]["lat"]) / 2, (places[a]["lon"] + places[b]["lon"]) / 2)
              for a, b in links if places[a]["side"] != places[b]["side"]]
    def front_km(p):
        return min(dist_km(p, q) for q in border)
    def toward_front(p, km):
        q = min(border, key=lambda q: dist_km(p, q))
        d = dist_km(p, q) or 1.0
        f = min(1.0, km / d)
        return (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
    def clear(p, km_step):                       # дальше от аэродромов карты: шагами в ту же сторону (к фронту / в тыл)
        for _ in range(4):
            if all(dist_km(p, a) >= AD_AIRPORT_CLEAR_KM for a in airports):
                break
            p = toward_front(p, km_step)
        return p
    sites = []
    for bid, (la, lo, side, name) in sorted(airbase_pos.items()):
        p = toward_front((la, lo), AD_AF_OFFSET_KM)
        sites.append({"id": f"{side}_ad_af_{bid}", "name": f"ПВО аэродрома {name}", "side": side, "tier": "short",
                      "covers": f"af_{bid}", "lat": round(p[0], 4), "lon": round(p[1], 4), "variant": len(sites) % 2,
                      "rule": "ПВО объекта: у каждого военного аэродрома"})
    red_pts = {n: (p["lat"], p["lon"]) for n, p in places.items() if p["side"] == "red"}
    red_pts.update({f"af_{b}": (la, lo) for b, (la, lo, s, _n) in airbase_pos.items() if s == "red"})
    # long: дальние от границы пункты, разнесённые
    longs = []
    for n in sorted(red_pts, key=lambda n: -front_km(red_pts[n])):
        if (n.startswith("af_") or front_km(red_pts[n]) < AD_LONG_FRONT_KM
                or any(dist_km(red_pts[n], red_pts[m]) < AD_LONG_GAP_KM for m in longs)):
            continue
        longs.append(n)
        if len(longs) == AD_LONG_N:
            break
    for i, n in enumerate(longs):
        la, lo = clear(toward_front(red_pts[n], -AD_LONG_OFFSET_KM), -AD_LONG_OFFSET_KM)
        sites.append({"id": f"red_ad_long_{n.lower()}", "name": f"ЗРК большой дальности ({n})", "side": "red", "tier": "long",
                      "lat": round(la, 4), "lon": round(lo, 4), "variant": 0, "rule": "дальний ярус: глубина, разнесены"})
    # medium: жадное покрытие красных аэродромов и пунктов; кандидаты - сами эти точки, не у самой границы
    todo = set(red_pts)
    meds = []
    cand = [n for n in red_pts if front_km(red_pts[n]) >= AD_FRONT_KM]
    while todo:
        valid = [c for c in cand if all(dist_km(red_pts[c], red_pts[m]) >= AD_MED_GAP_KM for m in meds)]
        cover = {c: {t for t in todo if dist_km(red_pts[c], red_pts[t]) <= AD_MED_KM} for c in valid}
        best = max(valid, key=lambda c: (len(cover[c]), c), default=None)
        if best is None or not cover[best]:
            break                                # остаток - у самой границы, его прикрывают войсковая ПВО и ярус short
        meds.append(best)
        todo -= cover[best]
    for i, n in enumerate(meds):
        la, lo = clear(toward_front(red_pts[n], AD_MED_AF_OFFSET_KM if n.startswith("af_") else AD_MED_TOWN_OFFSET_KM), 2)
        where = n[3:].replace("_", " ").title() if n.startswith("af_") else n
        sites.append({"id": f"red_ad_med_{n.lower()}", "name": f"ЗРК средней дальности ({where})", "side": "red",
                      "tier": "medium", "lat": round(la, 4), "lon": round(lo, 4), "variant": i % 2,
                      "rule": "средний ярус: покрытие аэродромов и пунктов"})
    return sites


# ---------------------------------------------------------------- авиация (метки OOB-миссии)
# (id, имя, роль, тип pydcs, аэродром, число, радиус, источник/примечание)
AIR = [
    ("r773iap", "773-й иап (МиГ-23МЛД)", "red", "fighter", "MiG_23MLD", "Damgarten", 40, 300, MISSION),
    ("r33iap", "33-й иап (МиГ-29)", "red", "fighter", "MiG_29_Fulcrum", "Wittstock", 40, 250,
     MISSION + "; метка у Лаге, аэродром Виттшток - " + MEMORY),
    ("r19apib", "19-й гв. апиб (МиГ-27К)", "red", "fighter_bomber", "MiG_27K", "Larz", 40, 300, MISSION),
    ("r20apib", "20-й апиб (Су-17М3; в DCS - Су-17М4)", "red", "fighter_bomber", "Su_17M4", "Neuruppin", 40, 300,
     MISSION + "; Су-17М3 в DCS нет - замена Су-17М4"),
    ("r787iap_23", "787-й иап, эскадрильи МиГ-23", "red", "fighter", "MiG_23MLD", "Finow", 20, 300,
     MISSION + "; МиГ-23М в DCS нет - замена МиГ-23МЛД"),
    ("r787iap_25", "787-й иап, эскадрилья МиГ-25ПД", "red", "interceptor", "MiG_25PD", "Finow", 20, 300, MISSION),
    ("r116bap", "Бомбардировочный полк (Су-24М), Бранд", "red", "bomber", "Su_24M", "Brand", 40, 400,
     MISSION + " ('116 Bomber ~30-60 Su-24M'); номер полка - " + MEMORY),
    ("r833iap", "833-й иап (МиГ-23)", "red", "fighter", "MiG_23MLD", "Altes Lager", 40, 300, MISSION),
    ("r73iap", "73-й гв. иап (МиГ-23)", "red", "fighter", "MiG_23MLD", "Kothen", 40, 300, MISSION),
    ("r85iap", "85-й гв. иап (МиГ-29)", "red", "fighter", "MiG_29_Fulcrum", "Merseburg", 40, 250, MISSION),
    ("r368oshap", "368-й ошап (Су-25)", "red", "attack", "Su_25", "Tutow", 36, 250, MEMORY + "; в миссии штурмовиков нет"),
    ("r357oshap", "357-й ошап (Су-25)", "red", "attack", "Su_25", "Brandis", 36, 250, MEMORY + "; в миссии штурмовиков нет"),
    ("nva_jbg77", "JBG-77 ВВС ННА (Су-22М4)", "red", "fighter_bomber", "Su_17M4", "Laage", 24, 300,
     MISSION + "; Су-22М4 - экспортный Су-17М4"),
    ("nva_mfg28", "MFG-28 ННА (Су-22М4)", "red", "fighter_bomber", "Su_17M4", "Laage", 24, 300, MISSION),
    ("nva_jg2", "JG-2 ВВС ННА (МиГ-21)", "red", "fighter", "MiG_21Bis", "Neubrandenburg", 36, 200, MISSION),
    ("nva_jg9", "JG-9 ВВС ННА (МиГ-23)", "red", "fighter", "MiG_23MLD", "Peenemunde", 36, 300, MISSION),
    ("nva_jg8", "JG-8 ВВС ННА (МиГ-21)", "red", "fighter", "MiG_21Bis", "Marxwalde", 36, 200, MISSION),
    ("nva_jg1", "JG-1 ВВС ННА (МиГ-21)", "red", "fighter", "MiG_21Bis", "Holzdorf", 36, 200, MISSION),
    ("b_jabog31", "JaboG 31 (Tornado IDS)", "blue", "fighter_bomber", "Tornado_IDS", "Norvenich", 32, 450, MISSION),
    ("b_jabog33", "JaboG 33 (Tornado IDS)", "blue", "fighter_bomber", "Tornado_IDS", "Buchel", 32, 450, MISSION),
    ("b_jabog35", "JaboG 35 (F-4F; в DCS - F-4E)", "blue", "fighter_bomber", "F_4E_45MC", "Pferdsfeld", 30, 350,
     MISSION + "; F-4F в DCS нет - замена F-4E-45MC"),
    ("b_jg71", "JG 71 (F-4F; в DCS - F-4E)", "blue", "fighter", "F_4E_45MC", "Nordholz", 30, 350,
     MISSION + "; Витмунд вне карты - перебазирован в Нордхольц (ОЦЕНКА)"),
    ("b_52tfw", "52-е тактическое авиакрыло (F-16C)", "blue", "fighter_bomber", "F_16C_50", "Spangdahlem", 36, 400,
     MISSION + "; F-16C блок 50 - замена блока 30 (ОЦЕНКА); F-4G крыла не включены: в DCS нет"),
    ("b_50tfw", "50-е тактическое авиакрыло (F-16C)", "blue", "fighter_bomber", "F_16C_50", "Hahn", 72, 400, MISSION),
    ("b_36tfw", "36-е тактическое истребительное крыло (F-15C)", "blue", "fighter", "F_15C", "Bitburg", 72, 450, MISSION),
    ("b_86tfw", "86-е тактическое истребительное крыло (F-16C)", "blue", "fighter_bomber", "F_16C_50", "Ramstein", 48, 400, MISSION),
    ("b_a10", "Передовое звено A-10A (81-е крыло)", "blue", "attack", "A_10A", "Norvenich", 8, 250, MISSION),
    ("b_raf_harrier", "3-я и 4-я эскадрильи RAF (Harrier GR5; в DCS - AV-8B)", "blue", "attack", "AV8BNA", "Gutersloh", 32, 200,
     MISSION + "; Harrier GR5 в DCS нет - замена AV-8B"),
    # армейская авиация: боевые вертолёты (задача доктрины "удар вертолётов"; полки, аэродромы, число - ОЦЕНКИ, по памяти).
    # Ми-24П - чтобы игрок мог лететь (в ГСВГ - Ми-24В и П); Bo-105 PAH-1 в DCS нет - замена SA342M (тоже с ПТУР HOT)
    ("r_ovp_2gta", "Отдельный вертолётный полк 2-й гв. ТА (Ми-24)", "red", "attack_helo", "Mi_24P", "Parchim", 20, 150,
     MEMORY + "; число - доля Ми-24 полка (ОЦЕНКА)"),
    ("r_ovp_3ua", "Отдельный вертолётный полк 3-й УА (Ми-24)", "red", "attack_helo", "Mi_24P", "Mahlwinkel", 20, 150,
     MEMORY + "; число - доля Ми-24 полка (ОЦЕНКА)"),
    ("r_ovp_1gta", "Отдельный вертолётный полк 1-й гв. ТА (Ми-24)", "red", "attack_helo", "Mi_24P", "Brandis", 20, 150,
     MEMORY + "; число - доля Ми-24 полка (ОЦЕНКА)"),
    ("r_ovp_8ga", "Отдельный вертолётный полк 8-й гв. А (Ми-24)", "red", "attack_helo", "Mi_24P", "Allstedt", 20, 150,
     MEMORY + "; Нора вне карты - Альштедт (ОЦЕНКА)"),
    ("b_pahr16", "Противотанковый вертолётный полк 16 (PAH-1; в DCS - SA342M)", "blue", "attack_helo", "SA342M", "Celle", 24, 120,
     MEMORY + "; Bo-105 PAH-1 в DCS нет - замена SA342M"),
    ("b_pahr36", "Противотанковый вертолётный полк 36 (PAH-1; в DCS - SA342M)", "blue", "attack_helo", "SA342M", "Fritzlar", 24, 120,
     MEMORY + "; Bo-105 PAH-1 в DCS нет - замена SA342M"),
    ("b_us_avn", "Батальон боевых вертолётов армии США (AH-64A)", "blue", "attack_helo", "AH_64A", "Giebelstadt", 18, 150,
     MEMORY + "; часть и аэродром - ОЦЕНКА"),
    # обеспечение: ДРЛО и заправщики (задача доктрины "дежурство в зоне"; аэродромы и число - ОЦЕНКИ)
    ("b_naew", "Силы ДРЛО НАТО (E-3A)", "blue", "awacs", "E_3A", "Norvenich", 3, 1500,
     MEMORY + "; Гайленкирхен вне карты - Нёрфених (ОЦЕНКА)"),
    ("b_kc135", "Заправщики ВВС США (KC-135)", "blue", "tanker", "KC_135", "Ramstein", 4, 1500,
     MEMORY + "; базы заправщиков (Милденхолл) вне карты - Рамштайн (ОЦЕНКА)"),
    ("r_a50", "Отряд ДРЛО (А-50)", "red", "awacs", "A_50", "Templin", 2, 1500,
     MEMORY + "; А-50 в ГСВГ на постоянной основе не было - ОЦЕНКА сценария (выдвинуты на время войны)"),
]

# ---------------------------------------------------------------- склады (снабжение; уточняются зондом карты)
DEPOTS = [  # (id, имя, сторона, пункт)
    ("red_depot_1", "Склад снабжения (Людвигслюст)", "red", "Ludwigslust"),
    ("red_depot_2", "Передовой склад (Бойценбург)", "red", "Boizenburg"),
    ("red_depot_schwerin", "Склад снабжения (Шверин)", "red", "Schwerin"),
    ("red_depot_stendal", "Склад снабжения (Стендаль)", "red", "Stendal"),
    ("red_depot_magdeburg", "Склад снабжения (Магдебург)", "red", "Magdeburg"),
    ("red_depot_halle", "Склад снабжения (Галле)", "red", "Halle"),
    ("red_depot_erfurt", "Склад снабжения (Эрфурт)", "red", "Erfurt"),
    ("red_depot_gera", "Склад снабжения (Гера)", "red", "Gera"),
    ("blue_depot_1", "Склад снабжения (Зольтау)", "blue", "Soltau"),
    ("blue_depot_2", "Склад снабжения (Ильцен)", "blue", "Uelzen"),
    ("blue_depot_nms", "Склад снабжения (Ноймюнстер)", "blue", "Neumunster"),
    ("blue_depot_han", "Склад снабжения (Ганновер)", "blue", "Hannover"),
    ("blue_depot_kas", "Склад снабжения (Кассель)", "blue", "Kassel"),
    ("blue_depot_ful", "Склад снабжения (Фульда)", "blue", "Fulda"),
    ("blue_depot_wue", "Склад снабжения (Вюрцбург)", "blue", "Wurzburg"),
    ("blue_depot_nue", "Склад снабжения (Нюрнберг)", "blue", "Nurnberg"),
]


def dist_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def gabriel(pos: dict) -> set[tuple[str, str]]:
    """Граф Габриэля: связь AB, если внутри круга на AB как на диаметре нет других пунктов (похоже на дорожную сеть)."""
    names = sorted(pos)
    out = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = dist_km(pos[a], pos[b])
            if d > MAX_LINK_KM:
                continue
            m = ((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2)
            if all(dist_km(m, pos[c]) >= d / 2 for c in names if c not in (a, b)):
                out.add((a, b))
    return out


def main() -> None:
    ham = json.loads((DATA / "sector_hamburg.json").read_text(encoding="utf-8"))
    places = {}
    for n, p in ham["places"].items():           # сектор Гамбурга - как был, стороны - по границе 1989 (Вендланд - ФРГ)
        side = "red" if n in ("Boizenburg", "Ludwigslust") else "blue"
        places[n] = {"lat": p["lat"], "lon": p["lon"], "estimate": True, "side": side}
    for d, side in ((PLACES_B, "blue"), (PLACES_R, "red")):
        for n, (la, lo) in d.items():
            places[n] = {"lat": la, "lon": lo, "estimate": True, "side": side}
    pos = {n: (p["lat"], p["lon"]) for n, p in places.items()}
    ham_set = set(ham["places"])
    links = {tuple(sorted(l)) for l in ham["links"]}
    for a, b in gabriel(pos):
        if a in ham_set and b in ham_set:        # внутри сектора Гамбурга - только его связи
            continue
        links.add(tuple(sorted((a, b))))
    # связность
    adj = {n: set() for n in places}
    for a, b in links:
        adj[a].add(b); adj[b].add(a)
    seen, todo = set(), [next(iter(places))]
    while todo:
        x = todo.pop()
        if x not in seen:
            seen.add(x); todo += adj[x]
    assert seen == set(places), f"граф несвязный: {set(places) - seen}"

    airbases = {}
    for side, names in AIRBASES.items():
        for n in names:
            airbases[n.lower().replace(" ", "_")] = {"name": n, "airport": n, "side": side, "military": True}
    from dcs.terrain.germany import Germany  # координаты аэродромов - из терраина pydcs (как model.new_campaign)
    terrain = Germany()
    af_pos = {}
    for bid, b in airbases.items():
        ll = terrain.airports[b["airport"]].position.latlng()
        af_pos[bid] = (ll.lat, ll.lng, b["side"], b["name"])
    all_af = [(ap.position.latlng().lat, ap.position.latlng().lng) for ap in terrain.airports.values()]
    sites = ad_sites(places, links, af_pos, all_af) + gci_sites(places, links, af_pos, AIR)
    sector = {
        "_about": "Театр всей карты Cold War Germany: внутригерманская граница от Балтики до Хофа. Генерирован "
                  "tools/gen_germany.py. Координаты пунктов - ОЦЕНКИ (по памяти, +-2 км), пункты и связи сектора "
                  "Гамбурга - из sector_hamburg.json; связи остального графа - граф Габриэля не длиннее "
                  f"{MAX_LINK_KM} км (ОЦЕНКА дорожной сети). Стороны пунктов - граница 1989 г.",
        "theatre": "germany",
        "places": places,
        "airbases": airbases,
        "links": [list(l) for l in sorted(links)],
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()}, "blue": []},
        "_about_objectives": "Оси наступления ОВД - ОЦЕНКА по общим представлениям о планах, не документ. У каждой "
                             "части красных - своя ось (axis); цели оси берутся по порядку, первая не взятая.",
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": ham["bridges"],
        "_about_targets": "Склады - в пунктах (уточняются зондом карты), мосты через Эльбу - из сектора Гамбурга.",
        "ad_sites": sites,
        "_about_ad_sites": "Позиции объектовой ПВО по ярусам (long / medium / short) - ОЦЕНКА по правилам "
                           "tools/gen_germany.py (ad_sites), не документ: у аэродромов, покрытие красных аэродромов и "
                           "пунктов, дальний ярус в глубине. Модель на позиции - шаблон стороны (ad_templates в составе сил).",
    }
    (DATA / "sector_germany.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")

    def near(lat, lon, side=None):
        return min((n for n in places if side is None or places[n]["side"] == side),
                   key=lambda n: dist_km((lat, lon), pos[n]))

    units = []
    def ground(uid, name, side, comp, ad, place, day, axis=None, note="", source=MISSION):
        u = {"id": uid, "name": name, "side": side, "role": "maneuver", "state": "defend" if day <= 1 else "pending",
             "route": [place], "progress_km": 0.0, "march_kmh": 30, "daily_advance_km": 25,
             "composition": [{"type": t, "count": c, "role": r} for t, c, r in comp if c > 0],
             "source": source, "estimate": True}
        if day > 1:
            u["arrives_day"] = day
            u["arrives_jitter"] = 1
        if axis:
            u["axis"] = axis
        if note:
            u["note"] = note
        units.append(u)
        if ad:
            units.append({"id": f"{uid}_pvo", "name": f"Войсковая ПВО: {name}", "side": side, "role": "sam_short",
                          "attached_to": uid, "state": u["state"],
                          "composition": [{"type": t, "count": c, "role": "launcher" if "tracker" not in t else "radar"}
                                          for t, c in ad.items()],
                          "source": "состав ПВО - " + ("OOB-миссия (сумма ПВО полков)" if side == "red" else "ОЦЕНКА"),
                          "estimate": True})

    for uid, name, army, kind, la, lo, day, axis, note in RED_DIVS:
        base, ad = (SOV_MRD, SOV_AD_MRD) if kind == "mrd" else (SOV_TD, SOV_AD_TD)
        comp = [(TANK["gsfg"], base["MBT"], "MBT"), (IFV["gsfg"], base["IFV"], "IFV"), (APC["gsfg"], base["APC"], "APC")]
        ground(f"red_{uid}", f"{name} ({army})", "red", comp, ad, near(la, lo, "red"), day, axis,
               "; ".join(x for x in (note, RED_DAY_NOTE) if x),
               MISSION + "; состав - шаблон полков 8-й гв. А из миссии, Т-64 в DCS нет - Т-80Б")
    for uid, name, army, kind, eq, la, lo, day, axis, note in NVA_DIVS:
        base, ad = (SOV_MRD, SOV_AD_MRD) if kind == "mrd" else (SOV_TD, SOV_AD_TD)
        comp = [(TANK[eq], base["MBT"], "MBT"), (IFV[eq], base["IFV"], "IFV"), (APC[eq], base["APC"], "APC")]
        ground(f"red_{uid}", f"{name} ({army})", "red", comp, {"Strela_10M3": 8, "ZSU_23_4_Shilka": 8}, near(la, lo, "red"),
               day, axis, "; ".join(x for x in (note, RED_DAY_NOTE) if x),
               MISSION + "; состав - советский шаблон (ОЦЕНКА для ННА), техника ННА: Т-72Б вместо Т-72М (ОЦЕНКА)")
    for uid, name, corps, tpl, la, lo, day, note in BLUE_BDES:
        comp, ad = NATO[tpl]
        ground(f"blue_{uid}", f"{name} ({corps})", "blue", [(t, c, ROLE_OF[t]) for t, c in comp.items()], ad,
               near(la, lo, "blue"), day, None, note, MISSION + "; состав бригады - ОЦЕНКА")
    for uid, name, corps, tpl, place, day in REINF:
        comp, ad = NATO[tpl]
        ground(f"blue_{uid}", f"{name} ({corps})", "blue", [(t, c, ROLE_OF[t]) for t, c in comp.items()], ad, place, day,
               None, "подкрепление из-за пределов карты; срок ввода - ОЦЕНКА", MISSION + " (вне карты); состав - ОЦЕНКА")
    for sid, name, kind, la, lo in BLUE_SAMS + RED_SAMS:
        tpl = {"hawk": HAWK, "patriot": PATRIOT, "kub": KUB}[kind]
        side = "red" if (sid, name, kind, la, lo) in RED_SAMS else "blue"
        units.append({"id": f"{side}_{sid}", "name": name, "side": side,
                      "role": "sam_long" if kind == "patriot" else "sam_medium",
                      "state": "deployed", "pos": {"lat": la, "lon": lo},
                      "composition": [{"type": t, "count": c, "role": r} for t, (r, c) in tpl.items()],
                      "source": MISSION + "; в модели - одна батарея на батальон/полк (ОЦЕНКА)", "estimate": True})
    for uid, name, side, role, typ, base, count, radius, src in AIR:
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": base.lower().replace(" ", "_"),
                      "type": typ, "count": count, "strike_radius_km": radius,
                      "source": src + "; радиус действия - ОЦЕНКА", "estimate": True})
    for u in units:
        if u.get("base"):
            assert u["base"] in airbases, u
    oob = {
        "_about": "Состав сил всего фронта, 1989. Генерирован tools/gen_germany.py; источники - в поле source каждой части.",
        "countries": {"red": "Russia", "blue": "Germany"},
        "units": units,
        "variants": [{"name": "base", "title": "Удар ОВД по всему фронту (1989)"}],
        "replacements": {"air_per_day": 2, "note": "Пополнение полков: самолётов в сутки до штата (ОЦЕНКА)."},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]}
                                       for v in vs] for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_about_ad_templates": "Объектовая ПВО: сторона -> ярус -> варианты состава батареи на позиции ad_sites сектора "
                               "(ОЦЕНКИ: одна батарея на позицию). Нет шаблона яруса - позиция стоит пустой.",
    }
    (DATA / "oob_germany.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    n_g = sum(1 for u in units if u["role"] == "maneuver")
    print(f"пунктов {len(places)}, связей {len(links)}, аэродромов {len(airbases)}, частей {n_g}, всего объектов {len(units)}")


if __name__ == "__main__":
    main()

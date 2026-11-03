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
]
SUPPLY_ENTRY = {"red": ["Damascus", "Homs"], "blue": ["Jounieh"]}
OFF_LIMITS = {"blue": ["Damascus", "Homs", "Masnaa", "Baalbek"], "red": ["Sidon", "Jezzine"]}
# политика: США не наступают на суше за пределы Бейрута (только авиация); зона Израиля закрыта для Сирии

AIRBASES = {"red": ["Damascus", "Mezzeh", "Al-Dumayr", "Khalkhalah", "Marj Ruhayyil", "Shayrat", "Rayak"], "blue": []}
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
    ("s_mig21", "Истребительные эскадрильи (МиГ-21)", "red", "fighter", "MiG_21Bis", "Al-Dumayr", 24, 250, ""),
    ("s_mig23", "Истребительные эскадрильи (МиГ-23МЛ)", "red", "fighter", "MiG_23MLD", "Shayrat", 24, 300, ""),
    ("s_su22", "Истребительно-бомбардировочные эскадрильи (Су-22)", "red", "fighter_bomber", "Su_17M4", "Marj Ruhayyil", 18, 300, ""),
    ("s_gazelle", "Вертолёты 'Газель'", "red", "attack_helo", "SA342M", "Rayak", 10, 120, ""),
]
AD_TEMPLATES = {"red": {"short": [{"name": "Стрела-1, ЗСУ-23-4", "composition": [("Strela_1_9P31", "launcher", 2), ("ZSU_23_4_Shilka", "launcher", 2)]}]}}


def bid_of(n):
    return n.lower().replace(" ", "_").replace("-", "_")


def main() -> None:
    from dcs.terrain import Syria
    terrain = Syria()
    places = {n: {"lat": la, "lon": lo, "estimate": True, "side": s} for n, (la, lo, s) in PLACES.items()}
    for a, b in LINKS:
        assert a in places and b in places, (a, b)
    airbases = {}
    for side, names in AIRBASES.items():
        for n in names:
            assert n in terrain.airports, n
            airbases[bid_of(n)] = {"name": n, "airport": n, "side": side, "military": True}
    carriers = {cid: {"name": n, "side": "blue", "ship": t, "lat": la, "lon": lo, "tacan": tc, "tacan_id": tid,
                      "icls": icls or None, "freq": f, "naval": nv, "estimate": True}
                for cid, (n, t, la, lo, tc, tid, icls, f, nv) in CARRIERS.items()}
    sector = {
        "_about": "Ливан, декабрь 1983 (гипотетическая эскалация). Генерирован tools/gen_lebanon83.py. Координаты - ОЦЕНКИ.",
        "theatre": "syria", "places": places, "airbases": airbases, "carriers": carriers,
        "links": [list(l) for l in LINKS], "supply_entry": SUPPLY_ENTRY, "off_limits": OFF_LIMITS,
        "axes": {k: v["title"] for k, v in AXES.items()},
        "objectives": {"red": {k: v["objectives"] for k, v in AXES.items()}, "blue": []},
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "bridges": [], "ad_sites": [],
        "sea_lanes": [{"id": i, "side": sd, "port": pt, "convoy": cv, "t_per_day": t} for i, sd, pt, cv, t in SEA_LANES],
        "naval_bases": {"red": [{"name": "Тартус", "lat": 34.90, "lon": 35.86}]},   # порты ремонта кораблей; нет стороны - порт за картой (Неаполь, Субик-Бей)
    }
    (DATA / "sector_lebanon83.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")
    units = []
    for uid, name, side, place, cmp_, ad, day, axis in GROUND:
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
    for sid, name, side, role, cmp_, la, lo in SAMS:
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
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        b = base if base in carriers else bid_of(base)
        assert b in airbases or b in carriers, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": b, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True})
    oob = {
        "_about": "Ливан, декабрь 1983: палубная авиация США против Сирии (гипотетическая кампания). tools/gen_lebanon83.py.",
        "theatre": "syria",
        "preset": {"title": "Декабрь 1983: Ливан, авианосцы США", "year": 1983, "date": "1983-12-04"},
        "date": "1983-12-04", "countries": {"red": "Syria", "blue": "USA"}, "units": units,
        "variants": [{"name": "base", "title": "Декабрь 1983: Ливан, авианосцы США",
                      "posture": {"red": "offense", "blue": "defense"},
                      "task_rules": {"blue": {"strike_factory": {"off": True, "why": "удары - только по войскам и ПВО в Ливане"}}}}],
        "replacements": {"air_per_day": 1, "note": "ОЦЕНКА"},
        "ad_templates": {side: {tier: [{"name": v["name"], "composition": [{"type": t, "role": r, "count": c}
                                                                           for t, r, c in v["composition"]]} for v in vs]
                                for tier, vs in tiers.items()} for side, tiers in AD_TEMPLATES.items()},
        "_not_included": "A-7E (нет в DCS - F/A-18C), линкор New Jersey, многонациональные силы "
                         "(Франция, Италия, Великобритания), Израиль.",
    }
    (DATA / "oob_lebanon83.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пунктов {len(places)}, авианосцев {len(carriers)}, частей {len(GROUND)}, ЗРК {len(SAMS)}, авиачастей {len(AIR)}")


if __name__ == "__main__":
    main()

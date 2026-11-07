"""Генератор сценария "Танкерная война, апрель 1988" (карта DCS Persian Gulf): data/sector_tankerwar88.json,
data/oob_tankerwar88.json.

История: с 1987 г. ВМС США сопровождают перерегистрированные кувейтские танкеры (операция Earnest Will); 14.04.1988
фрегат USS Samuel B. Roberts подорвался на иранской мине. 18.04.1988 - операция Praying Mantis: группы надводных
кораблей (SAG Bravo, Charlie, Delta) уничтожили иранские нефтяные платформы Сассан и Сирри (базы КСИР), в бою
потоплены фрегат Sahand, катер Joshan и катера КСИР, повреждён фрегат Sabalan; иранские F-4 атаковали корабли США;
палубная авиация (USS Enterprise, CVW-11: A-6E с Harpoon, A-7E) - удары по кораблям. Удары по территории Ирана
(материк) - запрещены политикой; ОАЭ и Оман - нейтральны.

Источники (общие, по памяти - проверять): D. Crist, "The Twilight War" (2012); B. Wise / H. Peniston, отчёты ВМС
о Praying Mantis; L. Zatarain, "Tanker War" (2008). Координаты, составы и числа - ОЦЕНКИ. Типы DCS - замены:
USS Enterprise (CVN-65) - Carl Vinson (CVN-70); эсминцы Spruance/Adams и фрегаты Knox - Perry; крейсер Wainwright
(Belknap) - Ticonderoga; A-7E - F/A-18C; KA-6D - S-3B Tanker; фрегаты Vosper Mk 5 (Sahand, Sabalan) - Leander;
катера Kaman (Joshan) - La Combattante IIa (тот же тип); катера Boghammar - Speedboat. ДОПУЩЕНИЯ.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
SRC = "Crist 'Twilight War' / Zatarain 'Tanker War', по памяти - проверить"

PLACES = {
    # Иран: материк и острова
    "BandarAbbas": (27.19, 56.27, "red"), "Qeshm": (26.95, 56.27, "red"), "Larak": (26.86, 56.36, "red"),
    "BandarLengeh": (26.56, 54.88, "red"), "AbuMusa": (25.87, 55.03, "red"), "Sirri": (25.90, 54.54, "red"),
    "Kish": (26.53, 53.98, "red"), "Jask": (25.64, 57.77, "red"),
    # нейтральные ОАЭ и Оман - побережье (опорные точки морских путей)
    "Fujairah": (25.12, 56.36, "blue"), "Khasab": (26.18, 56.24, "blue"), "RasAlKhaimah": (25.79, 55.94, "blue"),
    "Dubai": (25.27, 55.30, "blue"), "AbuDhabi": (24.47, 54.37, "blue"),
}
LINKS = [   # связи пунктов (через пролив - 'фронт' морской войны)
    ("BandarAbbas", "Qeshm"), ("Qeshm", "Larak"), ("BandarAbbas", "BandarLengeh"), ("BandarLengeh", "Kish"),
    ("BandarLengeh", "AbuMusa"), ("AbuMusa", "Sirri"), ("BandarAbbas", "Jask"),
    ("Fujairah", "Khasab"), ("Khasab", "RasAlKhaimah"), ("RasAlKhaimah", "Dubai"), ("Dubai", "AbuDhabi"),
    ("Khasab", "Larak"), ("RasAlKhaimah", "AbuMusa"), ("Dubai", "Sirri"), ("Fujairah", "Jask"),
]
SUPPLY_ENTRY = {"red": ["BandarAbbas"], "blue": ["Fujairah"]}
OFF_LIMITS = {"blue": ["BandarAbbas", "BandarLengeh", "Jask", "Qeshm", "Kish"],   # материк и крупные острова Ирана - нет
              "red": ["Fujairah", "Khasab", "RasAlKhaimah", "Dubai", "AbuDhabi"]}  # нейтральные - нет

AIRBASES = {"red": ["Bandar Abbas Intl", "Havadarya", "Shiraz Intl", "Bandar Lengeh"], "blue": []}
CARRIERS = {   # (имя, класс pydcs, широта, долгота, TACAN, позывной, ICLS, МГц, группа флота)
    "cvn65": ("USS Enterprise (CVN-65)", "VINSON", 25.10, 57.40, 65, "ENT", 5, 127.5, "blue_csg_enterprise"),
}
sys.path.insert(0, str(Path(__file__).resolve().parent))
from naval_common import from_template as T, group   # noqa: E402

NAVAL = [   # (id, имя, сторона, широта, долгота, корабли, приказы, выучка, РЭБ)
    ("blue_csg_enterprise", "Авианосная ударная группа USS Enterprise", "blue", 25.10, 57.40,
     T("us_csg_1983", ("VINSON", "carrier", "USS Enterprise (CVN-65)"),
       ["USS Truxtun (CGN-35)", "USS Reasoner (FF-1063)", "USS Rentz (FFG-46)"]), None, 1.3, 0.3),
    ("blue_sag_bravo", "SAG Bravo (платформа Сассан)", "blue", 25.75, 53.60,
     [("PERRY", "destroyer", "USS Merrill (DD-976)"), ("PERRY", "destroyer", "USS Lynde McCormick (DDG-8)")],
     [{"day": 1, "to": {"lat": 25.90, "lon": 53.15}, "until_day": 3}], 1.3, 0.3),
    ("blue_sag_charlie", "SAG Charlie (платформа Сирри)", "blue", 25.60, 54.40,
     [("TICONDEROG", "cruiser", "USS Wainwright (CG-28)"), ("PERRY", "frigate", "USS Simpson (FFG-56)"),
      ("PERRY", "frigate", "USS Bagley (FF-1069)")],
     [{"day": 1, "to": {"lat": 25.85, "lon": 54.45}, "until_day": 3}], 1.3, 0.3),
    ("blue_sag_delta", "SAG Delta (Ормузский пролив)", "blue", 26.20, 56.70,
     [("PERRY", "frigate", "USS Jack Williams (FFG-24)"), ("PERRY", "destroyer", "USS O'Brien (DD-975)"),
      ("PERRY", "destroyer", "USS Joseph Strauss (DDG-16)")], None, 1.3, 0.3),
    ("blue_convoy_earnestwill", "Конвой Earnest Will (кувейтские танкеры)", "blue", 25.40, 56.90,
     [("HandyWind", "transport", "MV Bridgeton"), ("HandyWind", "transport", "MV Gas Prince"),
      ("HandyWind", "transport", "MV Sea Isle City")],
     [{"day": 1, "to": {"lat": 25.70, "lon": 53.80}, "until_day": 4}], None, None),
    ("red_irin_sahand", "Фрегаты ВМС Ирана (Sahand, Sabalan)", "red", 26.70, 55.90,
     [("Leander_gun_andromeda", "frigate", "IRIS Sahand"), ("Leander_gun_andromeda", "frigate", "IRIS Sabalan")],
     None, 0.8, None),
    ("red_irin_joshan", "Ракетный катер Joshan (Бушер - Сирри)", "red", 26.10, 54.10,
     [("La_Combattante_II", "boat", "IRIS Joshan")], None, 0.8, None),
    ("red_irgcn_abumusa", "Катера КСИР (Абу-Муса)", "red", 25.90, 55.05,
     [("Speedboat", "boat", "Boghammar №1"), ("Speedboat", "boat", "Boghammar №2"), ("Speedboat", "boat", "Boghammar №3"),
      ("Speedboat", "boat", "Boghammar №4")], None, 0.8, None),
    ("red_irgcn_larak", "Катера КСИР (Ларак)", "red", 26.85, 56.40,
     [("Speedboat", "boat", "Boghammar №5"), ("Speedboat", "boat", "Boghammar №6"), ("Speedboat", "boat", "Boghammar №7")],
     None, 0.8, None),
]
FACTORIES = [   # нефтяные платформы - базы КСИР (цели США 18.04.1988): (id, имя, сторона, пункт, широта, долгота)
    ("red_platform_sassan", "Нефтяная платформа Сассан (база КСИР)", "red", "Sirri", 25.92, 53.10),
    ("red_platform_sirri", "Нефтяная платформа Сирри-D (база КСИР)", "red", "Sirri", 25.88, 54.42),
    ("red_platform_rostam", "Нефтяная платформа Ростам (база КСИР)", "red", "Kish", 26.10, 52.95),
]
DEPOTS = [("red_depot_bandarabbas", "Военно-морская база Бандар-Аббас (склады)", "red", "BandarAbbas")]
HAWK = [("Hawk_sr", "radar", 1), ("Hawk_tr", "radar", 1), ("Hawk_pcp", "control", 1), ("Hawk_ln", "launcher", 6)]
SAMS = [   # ПВО Ирана: HAWK (поставки до 1979), ЗУ-23 на островах - ОЦЕНКА
    ("red_hawk_bandarabbas", "Батарея HAWK (Бандар-Аббас)", "red", "sam_medium", HAWK, 27.16, 56.20),
    ("red_hawk_qeshm", "Батарея HAWK (Кешм)", "red", "sam_medium", HAWK, 26.80, 55.90),
    ("red_zu_abumusa", "Зенитная артиллерия (Абу-Муса)", "red", "sam_short",
     [("ZU-23 Emplacement", "launcher", 4), ("SA-18 Igla manpad", "launcher", 2)], 25.88, 55.02),
]
AIR = [   # (id, имя, сторона, роль, тип, база, число, радиус км, примечание)
    ("us_vf114", "VF-114, VF-213 (F-14A, Enterprise)", "blue", "fighter", "F_14A_135_GR", "cvn65", 20, 500, ""),
    ("us_va95", "VA-95 (A-6E, Enterprise)", "blue", "fighter_bomber", "A6E", "cvn65", 10, 600, "A-6E с Harpoon"),
    ("us_va22", "VA-22, VA-94 (A-7E, Enterprise)", "blue", "fighter_bomber", "FA_18C_hornet", "cvn65", 20, 500,
     "A-7E в DCS нет - F/A-18C (допущение)"),
    ("us_vaw117", "VAW-117 (E-2C)", "blue", "awacs", "E_2C", "cvn65", 4, 1000, ""),
    ("us_vaq135", "VAQ-135 (EA-6B, Enterprise)", "blue", "ew", "A6E", "cvn65", 4, 600, "EA-6B Prowler - в DCS нет, модель A-6E; постановщик помех вне зоны ПВО"),
    ("us_ka6", "VA-95 (KA-6D, заправщик)", "blue", "tanker", "S_3B_Tanker", "cvn65", 4, 800, "KA-6D - S-3B Tanker"),
    ("ir_tfb9_f4", "91-я тактическая эскадрилья (F-4E, Бандар-Аббас)", "red", "fighter_bomber", "F_4E_45MC",
     "Bandar Abbas Intl", 12, 400, "в строю - часть машин (эмбарго)"),
    ("ir_f14", "Эскадрилья F-14A (Шираз)", "red", "fighter", "F_14A_135_GR", "Shiraz Intl", 6, 500,
     "в строю немного F-14A (запчасти)"),
    ("ir_f5", "Эскадрилья F-5E (Бандар-Аббас)", "red", "fighter", "F_5E_3", "Bandar Abbas Intl", 10, 300, ""),
    ("ir_cobra", "Вертолёты AH-1J КСИР/армии (Бандар-Аббас)", "red", "attack_helo", "AH_1W", "Havadarya", 6, 150,
     "AH-1J - AH-1W"),
]


def bid_of(n):
    return n.lower().replace(" ", "_").replace("-", "_")


def main() -> None:
    from dcs.terrain import PersianGulf
    terrain = PersianGulf()
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
        "_about": "Танкерная война, апрель 1988 (Praying Mantis). Генерирован tools/gen_tankerwar88.py. Координаты - ОЦЕНКИ.",
        "theatre": "persiangulf", "places": places, "airbases": airbases, "carriers": carriers,
        "links": [list(l) for l in LINKS], "supply_entry": SUPPLY_ENTRY, "off_limits": OFF_LIMITS,
        "axes": {}, "objectives": {"red": {}, "blue": []},
        "depots": [{"id": i, "name": n, "side": s, "place": p} for i, n, s, p in DEPOTS],
        "factories": [{"id": i, "name": n, "side": s, "place": p, "lat": la, "lon": lo} for i, n, s, p, la, lo in FACTORIES],
        "bridges": [], "ad_sites": [], "sea_lanes": [],
        "naval_bases": {"red": [{"name": "Бандар-Аббас", "lat": 27.15, "lon": 56.25}]},   # США - ремонт за картой (Бахрейн)
        "asm_stock": {"blue": {"count": 30, "per_day": 2, "type": "AGM-84 Harpoon (A-6E)", "note": "ОЦЕНКА"},
                      "red": {"count": 12, "per_day": 0, "type": "AGM-65A Maverick (F-4E)",
                              "note": "ОЦЕНКА: Maverick иранских F-4 по танкерам; эмбарго - без пополнения"}},
    }
    (DATA / "sector_tankerwar88.json").write_text(json.dumps(sector, ensure_ascii=False, indent=1), encoding="utf-8")
    units = []
    for sid, name, side, role, cmp_, la, lo in SAMS:
        units.append({"id": sid, "name": name, "side": side, "role": role, "state": "deployed", "fixed": True,
                      "pos": {"lat": la, "lon": lo}, "composition": [{"type": t, "count": c, "role": r} for t, r, c in cmp_],
                      "source": SRC + "; место - ОЦЕНКА", "estimate": True})
    for uid, name, side, la, lo, ships, orders, q, ecm in NAVAL:
        units.append(group(uid, name, side, la, lo, ships, source=SRC + "; состав и место - ОЦЕНКА", orders=orders,
                           quality=q, ecm=ecm))
    for uid, name, side, role, typ, base, count, radius, note in AIR:
        b = base if base in carriers else bid_of(base)
        assert b in airbases or b in carriers, (uid, base)
        units.append({"id": uid, "name": name, "side": side, "role": role, "base": b, "type": typ, "count": count,
                      "strike_radius_km": radius, "source": SRC + "; число и радиус - ОЦЕНКА" + (f"; {note}" if note else ""),
                      "estimate": True, **({"quality": 0.8} if side == "red" else {})})
    oob = {
        "_about": "Танкерная война, апрель 1988: ВМС США против ВМС Ирана и КСИР (Praying Mantis). tools/gen_tankerwar88.py.",
        "theatre": "persiangulf",
        "preset": {"title": "Апрель 1988: Танкерная война (Praying Mantis)", "year": 1988, "date": "1988-04-18"},
        "date": "1988-04-18", "doctrine": {"blue": "nato", "red": "nato"}, "countries": {"red": "Iran", "blue": "USA"},
        "units": units,
        "variants": [{"name": "base", "title": "Апрель 1988: Танкерная война (Praying Mantis)",
                      "posture": {"red": "defense", "blue": "defense"},
                      "task_rules": {
                          "blue": {"strike_airfield": {"off": True, "why": "удары по территории Ирана запрещены"},
                                   "strike_depot": {"off": True, "why": "удары по территории Ирана запрещены"},
                                   "strike_sam_site": {"off": True, "why": "ПВО материка - вне ответного удара"},
                                   "strike_bridge": {"off": True, "why": "нет целей"}},
                          "red": {"strike_airfield": {"off": True, "why": "у США в районе нет аэродромов"},
                                  "strike_factory": {"off": True, "why": "нет целей"},
                                  "strike_depot": {"off": True, "why": "нет целей"}}}}],
        "replacements": {"air_per_day": 0, "note": "ОЦЕНКА: короткая операция"},
        "_not_included": "мины, береговые ПКР HY-2 'Silkworm', P-3C, вертолёты SH-60B и морская пехота, Бахрейн "
                         "и Кувейт (вне карты).",
    }
    (DATA / "oob_tankerwar88.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пунктов {len(places)}, авианосцев {len(carriers)}, кораблей групп {len(NAVAL)}, ЗРК {len(SAMS)}, "
          f"авиачастей {len(AIR)}")


if __name__ == "__main__":
    main()

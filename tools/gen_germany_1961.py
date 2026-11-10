"""Германия, октябрь 1961: Берлинский кризис (гипотетическая война) - состав сил на карте Cold War Germany.

27-28.10.1961 у Чекпойнт Чарли стояли друг против друга американские M48 и советские Т-54/55 - самый острый момент
кризиса. Сценарий: противостояние перешло в войну, ОВД наступает (как в пресетах 80-х). Наземные части - те же
соединения и пункты, что в пресете 1985 (tools/gen_germany.py), техника - эпохи (замены моделей DCS - в EQUIP);
авиация - эпохи (AIR_1961). Числа и составы - ОЦЕНКИ; номера частей 1961 - по памяти, проверить.
Запуск: python tools/gen_germany_1961.py (после gen_germany.py).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
import sys  # noqa: E402
sys.path.insert(0, str(DATA.parent.parent))
from redfront import i18n_en  # noqa: E402

# техника 80-х -> 1961 (модель DCS; нет исторической - ближайшая, ОЦЕНКА)
EQUIP = {
    "T_80B": "T_55", "T_72B": "T_55",                       # ГСВГ 1961: Т-54/Т-55
    "BMP_1": "BTR_60", "BMP_2": "BTR_60", "BTR_80": "BTR_60", "BTR_70": "BTR_60",   # БТР-152/БТР-60П - модель БТР-60
    "Leopard_2": "M_60", "Leopard1A3": "M_60", "M_1_Abrams": "M_60",   # M48 (США, бундесвер) - модель M-60
    "Chieftain_mk3": "Chieftain_mk3",                       # Centurion (Великобритания) - модели нет, Chieftain
    "Marder": "M_113", "M_2_Bradley": "M_113", "MCV_80": "M_113",   # HS-30, M59 - модель M-113
    "ZSU_23_4_Shilka": "ZSU_57_2", "X_2S6_Tunguska": "ZSU_57_2", "Strela_10M3": "ZSU_57_2", "Strela_1_9P31": "ZSU_57_2",
    "Gepard": "bofors40", "Vulcan": "bofors40", "M48_Chaparral": "bofors40", "Rapier_fsa_launcher": "bofors40",
    "Rapier_fsa_optical_tracker_unit": None, "Roland_ADS": "bofors40", "Roland_Radar": None,
    "Kub_1S91_str": None, "Kub_2P25_ln": "S_60_Type59_Artillery", "Osa_9A33_ln": "ZSU_57_2",
    "Patriot_str": "Hawk_sr", "Patriot_ECS": "Hawk_pcp", "Patriot_ln": "Hawk_ln",
}
# авиация 1961 (ОЦЕНКА): сторона, роль -> тип DCS и подпись
AIR_1961 = {
    ("red", "fighter"): ("MiG_19P", "МиГ-19П"),
    ("red", "interceptor"): ("MiG_19P", "МиГ-19П"),
    ("red", "fighter_bomber"): ("MiG_15bis", "МиГ-17; в DCS - МиГ-15бис"),
    ("red", "attack"): ("MiG_15bis", "МиГ-17; в DCS - МиГ-15бис"),
    ("red", "bomber"): ("MiG_15bis", "Ил-28; в DCS - МиГ-15бис"),
    ("red", "recon"): ("MiG_15bis", "МиГ-17Р; в DCS - МиГ-15бис"),
    ("blue", "fighter"): ("F_86F_Sabre", "F-86 Sabre, Hunter; в DCS - F-86F"),
    ("blue", "interceptor"): ("F_86F_Sabre", "F-86 Sabre; в DCS - F-86F"),
    ("blue", "fighter_bomber"): ("F_100D", "F-100D, F-84F; в DCS - F-100D"),
    ("blue", "attack"): ("F_100D", "F-100D"),
    ("blue", "bomber"): ("F_100D", "Canberra; в DCS - F-100D"),
    ("blue", "recon"): ("F_86F_Sabre", "RF-84F; в DCS - F-86F"),
}
LABEL_EN = {"МиГ-19П": "MiG-19P", "МиГ-17; в DCS - МиГ-15бис": "MiG-17; MiG-15bis in DCS",
            "Ил-28; в DCS - МиГ-15бис": "Il-28; MiG-15bis in DCS", "МиГ-17Р; в DCS - МиГ-15бис": "MiG-17R; MiG-15bis in DCS",
            "F-86 Sabre, Hunter; в DCS - F-86F": "F-86 Sabre, Hunter; F-86F in DCS", "F-86 Sabre; в DCS - F-86F": "F-86 Sabre; F-86F in DCS",
            "F-100D, F-84F; в DCS - F-100D": "F-100D, F-84F; F-100D in DCS", "F-100D": "F-100D",
            "Canberra; в DCS - F-100D": "Canberra; F-100D in DCS", "RF-84F; в DCS - F-86F": "RF-84F; F-86F in DCS",
            "Ми-4; в DCS - Ми-8МТ": "Mi-4; Mi-8MT in DCS", "H-34; в DCS - UH-1H": "H-34; UH-1H in DCS",
            "МиГ-21Ф-13; в DCS - МиГ-21бис": "MiG-21F-13; MiG-21bis in DCS"}
DROP_ROLES = {"awacs", "tanker", "attack_helo", "ew"}      # ДРЛО, заправщиков, боевых вертолётов ещё нет
HELI_1961 = {"red": ("Mi_8MT", "Ми-4; в DCS - Ми-8МТ"), "blue": ("UH_1H", "H-34; в DCS - UH-1H")}


def main() -> None:
    src = json.loads((DATA / "oob_germany_1985.json").read_text(encoding="utf-8"))
    oob = copy.deepcopy(src)
    units = []
    mig21 = 0
    for u in oob["units"]:
        if u.get("type"):                                 # авиачасть
            if u["role"] in DROP_ROLES:
                continue
            if u["role"] in ("transport_helo",):
                typ, label = HELI_1961[u["side"]]
            elif u["role"] == "transport":
                units.append(u)                   # транспорт - как есть
                continue
            else:
                typ, label = AIR_1961.get((u["side"], u["role"]), (None, None))
                if typ is None:
                    continue
                if (u["side"], u["role"]) == ("red", "fighter"):   # каждый второй истребительный полк - МиГ-21Ф-13
                    mig21 += 1
                    if mig21 % 2 == 0:
                        typ, label = "MiG_21Bis", "МиГ-21Ф-13; в DCS - МиГ-21бис"
            base_name = u["name"].split(" (")[0].replace("A-10A", "F-100D")
            base_en = i18n_en.en(u["name"]).split(" (")[0].replace("A-10A", "F-100D")
            u = dict(u, type=typ, name=f"{base_name} ({label})", name_en=f"{base_en} ({LABEL_EN.get(label, label)})",
                     source=(u.get("source") or "") + "; в 1961 году тип эпохи, часть и база как в 1985 (ОЦЕНКА)")
            u.pop("mod", None)
        elif u.get("composition"):
            comp = []
            for c in u["composition"]:
                t = EQUIP.get(c["type"], c["type"])
                if t is None:
                    continue
                comp.append(dict(c, type=t))
            if not comp:
                continue
            u = dict(u, composition=comp)
        if u.get("role") == "ssm":
            en = i18n_en.en(u["name"])
            u = dict(u, name=u["name"].replace("ракетная бригада", "ракетная бригада Р-11").replace("Ракетная бригада", "Ракетная бригада Р-11"),
                     name_en=en.replace("Missile Brigade", "R-11 Missile Brigade").replace("missile brigade", "R-11 missile brigade"))
        units.append(u)
    oob["units"] = units
    # объектовая ПВО 1961: С-200 (с 1967) нет - большая дальность пустует; С-75 есть, С-125 - первые полки (1961);
    # Оса/Шилка (с 1965-1972) - ЗСУ-57-2; у НАТО - Bofors вместо Roland/Gepard
    tpl = oob.get("ad_templates") or {}
    tpl.get("red", {}).pop("long", None)
    tpl.get("red", {})["short"] = [{"name": "ЗСУ-57-2, С-60", "composition": [
        {"type": "ZSU_57_2", "role": "launcher", "count": 2}, {"type": "SON_9", "role": "radar", "count": 1},
        {"type": "S-60_Type59_Artillery", "role": "launcher", "count": 4}]}]
    tpl.get("blue", {})["short"] = [{"name": "Bofors L/60", "composition": [{"type": "bofors40", "role": "launcher", "count": 4}]}]
    oob["date"] = "1961-10-28"
    oob["preset"] = {"title": "1961: Берлинский кризис (гипотетическая война)", "year": 1961, "date": "1961-10-28"}
    oob["_about"] = ("Германия, 28.10.1961 (Берлинский кризис, гипотетическая война). Генерирован tools/gen_germany_1961.py "
                     "из пресета 1985: соединения и пункты те же, техника и авиация - эпохи (замены моделей DCS - в "
                     "именах). Все числа - ОЦЕНКИ.")
    oob["variants"] = [{"name": "base", "title": oob["preset"]["title"], "assembly": ["red", "blue"]}]
    oob["strategic_stock"] = {"red": {"scud": 18}}
    oob["strategic_per_day"] = {"red": {"scud": 3}}
    oob["_not_included"] = ("Ил-28, Як-25/27, Canberra, F-104 (с 1962), Nike Hercules, ядерное оружие; Береговая охрана, "
                            "французские войска; составы частей 1961 - по шаблонам 80-х с заменой техники (ОЦЕНКА).")
    (DATA / "oob_germany_1961.json").write_text(json.dumps(oob, ensure_ascii=False, indent=1), encoding="utf-8")
    n_air = sum(1 for u in units if u.get("type"))
    print(f"1961: частей {len(units)}, авиачастей {n_air}")


if __name__ == "__main__":
    main()

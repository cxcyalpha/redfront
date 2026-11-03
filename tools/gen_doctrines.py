"""Национальные пакеты доктрины на основе базовых (data/doctrine/wp.json, nato.json): vpaf72, arab, iaf73.

Пакет = базовый пакет + отличия страны и эпохи: какие задачи авиации есть, доли задач по фазам, 'зонтик' ПВО,
параметры наземного боя (sim). Числа, не взятые из источника, - ОЦЕНКА (поле estimate / пометка в тексте).
Запуск: python tools/gen_doctrines.py (перезаписывает data/doctrine/{vpaf72,arab,iaf73}.json).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "redfront" / "data" / "doctrine"


def derive(base: str, name: str, title: str, about: str, drop: list[str], shares: list[dict] | None = None,
           sim: dict | None = None, tasks: dict | None = None, extra: dict | None = None) -> dict:
    d = copy.deepcopy(json.loads((DOC / f"{base}.json").read_text(encoding="utf-8")))
    d["package"], d["title"], d["_about"] = name, title, about
    d["base"] = base
    for k in drop:
        d["tasks"].pop(k, None)
    for k, patch in (tasks or {}).items():
        if k in d["tasks"]:
            d["tasks"][k].update(patch)
    if shares is not None and d.get("apportionment"):
        d["apportionment"]["shares"] = shares
        d["apportionment"]["source"] = about + " Доли задач - ОЦЕНКА."
        d["apportionment"]["classes"] = {c: [k for k in ks if k in d["tasks"]] for c, ks in d["apportionment"]["classes"].items()}
    d["sim"].update(sim or {})
    d.update(extra or {})
    return d


PACKAGES = [
    derive(
        "wp", "vpaf72", "ВВС ДРВ, 1972: перехват по наведению с земли",
        "ВВС Северного Вьетнама 1972 г. (на основе wp.json): оборонительная война в воздухе - перехват ударных групп "
        "США по наведению с земли (GCI), атака с одного захода и уход (МиГ-21 на скорости сзади-снизу, МиГ-17 на "
        "малой высоте); ударов по аэродромам и войскам Юга почти не было - единичный удар МиГ-17 по эсминцам у "
        "Донгхоя 19.04.1972 (USS Higbee). Главная ПВО - С-75 и зенитная артиллерия. Источники: M. Michel, Clashes: Air "
        "Combat over North Vietnam 1965-1972 (1997); R. Toperczer, MiG-21 Units of the Vietnam War (2001).",
        drop=["cap_own_troops", "strike_airfield", "strike_sam_site", "strike_bridge", "strike_depot", "strike_factory",
              "strike_supply_route", "strike_column_march", "cas_contact", "cas_helo", "fleet_cap", "awacs_orbit",
              "air_assault", "air_evac"],
        shares=[{"from_day": 1, "DCA": 0.9, "OCA": 0.0, "SEAD": 0.0, "APCLO": 0.1}],
        tasks={"strike_ship": {"strike": {**json.loads((DOC / "wp.json").read_text(encoding="utf-8"))["tasks"]["strike_ship"]["strike"],
                                          "size": 2},
                               "method_source": "19.04.1972: пара МиГ-17 бомбами с малой высоты по эсминцам у Донгхоя - "
                                                "единичный эпизод (размер группы - ОЦЕНКА)"}},
        sim={"night_power": 1.2, "attack_min_strength": 0.6, "withdraw_below": 0.45,
             "night_note": "Северовьетнамская армия: ночные действия и просачивание - сильная сторона (night_power 1.2 - "
                           "ОЦЕНКА); атаки - и при меньшей боеспособности (attack_min_strength 0.6, отход ниже 0.45 - ОЦЕНКА)"},
    ),
    derive(
        "wp", "arab", "ВВС и армии арабских стран (советская школа, 1967-1985): зонтик ПВО",
        "Египет и Сирия 1973 г. (на основе wp.json): после 1967 г. авиация бережётся, истребители держатся под зонтиком "
        "своих ЗРК (С-75, С-125, 'Куб'), управление жёсткое по наведению с земли; первый массированный удар 6.10 "
        "(по позициям и аэродромам) - потом удары вглубь редки и дороги, поддержка войск - вертолёты и Су-7/МиГ-17 "
        "у переднего края. Источники: K. Pollack, Arabs at War (2002); L. Nordeen, Air Warfare in the Missile Age "
        "(2002); C. Herzog, The War of Atonement (1975). Армия: слабость ночного боя и инициативы младших командиров "
        "(Pollack) - night_power, attack_min_strength, choice_width - ОЦЕНКИ.",
        drop=["awacs_orbit", "fleet_cap"],
        shares=[{"from_day": 1, "DCA": 0.3, "OCA": 0.3, "SEAD": 0.05, "APCLO": 0.35},
                {"from_day": 2, "DCA": 0.5, "OCA": 0.05, "SEAD": 0.05, "APCLO": 0.4}],
        sim={"night_power": 0.7, "choice_width": 1, "attack_min_strength": 0.75,
             "night_note": "Арабские армии 1973: ночной бой слабее дневного (night_power 0.7 - ОЦЕНКА по Pollack); "
                           "план держится жёстко - выбор цели без импровизации (choice_width 1)"},
        extra={"umbrella": {"km": 25, "tasks": ["cap_own_troops", "cas_contact", "cas_helo", "strike_column_march",
                                      "strike_supply_route", "strike_depot", "strike_bridge", "strike_factory"],
                            "source": "Pollack, Nordeen: 1973 - истребители и штурмовики над войсками только под "
                                      "зонтиком своих ЗРК; 25 км за кромкой зоны поражения - ОЦЕНКА"}},
    ),
    derive(
        "nato", "iaf73", "ВВС и армия Израиля, 1973",
        "Израиль 1973 г. (на основе nato.json): господство в воздухе - свободная охота истребителей (Мираж/Нешер, F-4E), "
        "удары по ЗРК 7.10 ('Тагар' на Суэце, 'Дугман 5' на Голанах - провал, 6 F-4E потеряно), массированная "
        "поддержка войск на Голанах 6-8.10 под огнём ЗРК, затем удары по аэродромам и объектам Сирии (с 8-9.10). "
        "Танкеров и ДРЛО в 1973 г. нет. Источники: S. Aloni, Israeli Phantoms (2004); Herzog (1975); Nordeen (2002). "
        "Армия: манёвр, контратаки, ночной бой - night_power, counter_ratio - ОЦЕНКИ.",
        drop=["awacs_orbit", "tanker_orbit", "strike_bai", "strike_fofa", "fleet_cap"],
        shares=[{"from_day": 1, "DCA": 0.25, "OCA": 0.05, "SEAD": 0.25, "APCLO": 0.45},
                {"from_day": 3, "DCA": 0.3, "OCA": 0.2, "SEAD": 0.15, "APCLO": 0.35}],
        sim={"night_power": 1.1, "counter_ratio": 0.9, "attack_min_strength": 0.6,
             "night_note": "Армия обороны Израиля: контратаки и при меньшинстве (counter_ratio 0.9), ночной бой (night_power "
                           "1.1) - ОЦЕНКИ"},
        extra={"nation_bonus": None},
    ),
]


YEAR_GATES = {   # задачи по году кампании в базовых пакетах (planner: tdef from_year): техники ещё нет в строю
    "wp": {"awacs_orbit": (1985, "А-50 - в строю с 1984-1985 гг.")},
    "nato": {"awacs_orbit": (1977, "E-3A ВВС США - с 1977 г. (НАТО - с 1982)")},
}


def main() -> None:
    for base, gates in YEAR_GATES.items():
        p = DOC / f"{base}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, (y, why) in gates.items():
            if k in d["tasks"]:
                d["tasks"][k]["from_year"], d["tasks"][k]["from_year_source"] = y, why
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    for d in PACKAGES:
        (DOC / f"{d['package']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(d["package"], len(d["tasks"]), "задач")


if __name__ == "__main__":
    main()

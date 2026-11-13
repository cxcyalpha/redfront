"""Доктрина ВВС Украины 2022 (data/doctrine/ua.json) - из советской (wp.json) с поправками на войну 2022 г.

Общее прошлое, но другая тактика (ОЦЕНКИ по интервью лётчиков ВСУ и открытым обзорам, RUSI 'Preliminary Lessons in
Conventional Warfighting', 2022):
  * плотная ПВО противника (С-300/С-400, Бук, Тор, Панцирь) и мало самолётов - ударные группы парами, а не звеньями;
  * полёт на предельно малой высоте на всём маршруте (средняя высота - только вне досягаемости ЗРК, которой почти нет);
  * ставка на скорость удара: без поочерёдных групп обеспечения (подавление, добивание, расчистка, демонстративная
    группа) - на них нет ни самолётов, ни времени под ПВО; подавление ПВО (HARM с августа 2022) - одна пара вместе с
    ударом, необязательная;
  * нехватка типов: Су-25 летает и как бомбардировщик (склады, мосты, группировки, колонны, ЗРК), наравне с Су-24М.
Наземная модель (sim, march, fires) - как у wp.json.
Запуск: python tools/gen_doctrine_ua.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "redfront" / "data" / "doctrine"
STRIKE_SIZE = 2           # ОЦЕНКА: пара
LOW_M = 30                # ОЦЕНКА: предельно малая высота на маршруте
DROP = {"kill", "sweep", "feint", "jam", "cover"}   # истребители ВСУ - на прикрытии войск и объектов, не в пакетах
PASSES = 2                # ОЦЕНКА: не больше двух заходов (как у всех сторон, build.ATTACK_PASSES)
SPEED = 900               # ОЦЕНКА: км/ч на маршруте у земли
SEAD_LEAD_MIN = 2         # ОЦЕНКА: пуск ПРР - за столько минут до удара (не одновременно)
# удары одной парой, без пакета (без пары ПРР): цели с малой ПВО - колонны, пути подвоза, артиллерия, РЭБ, пусковые ОТР
SINGLE = {"strike_column_march", "strike_supply_route", "strike_art", "strike_ew", "strike_ssm"}
ATTACK_TOO = {"strike_sam_site", "strike_ew", "strike_art", "strike_ssm", "strike_airfield", "strike_ship"}


def main() -> None:
    d = copy.deepcopy(json.loads((DOC / "wp.json").read_text(encoding="utf-8")))
    d["package"] = "ua"
    d["title"] = "ВВС Украины, 2022 (пары, предельно малая высота, удар без поочерёдных групп обеспечения)"
    d["_about"] = __doc__
    for kind, t in d["tasks"].items():
        s = t.get("strike") or {}
        if not t.get("support") and kind not in ATTACK_TOO:
            continue                             # дежурства, перевозки, вертолёты - как было
        if s.get("size", 0) > STRIKE_SIZE:
            s["size"] = STRIKE_SIZE
            s["group_name"] = "пара"
        if s.get("ai") is not None or t.get("support") is not None:
            ai = s.setdefault("ai", {})
            ai.setdefault("attack", {})["passes"] = PASSES
        if t.get("speed_kmh"):
            t["speed_kmh"] = max(t["speed_kmh"], SPEED)
        for k in ("transit_alt_m_agl", "attack_alt_m_agl", "low_alt_m_agl"):
            if t.get(k) is not None:
                t[k] = min(t[k], LOW_M if k != "attack_alt_m_agl" else 50)
        if t.get("medium_alt_m_agl") is not None:
            t["medium_alt_m_agl"] = LOW_M        # средней высоты нет - и вне зон ЗРК низко (ОЦЕНКА)
        sup = []
        for g in t.get("support") or []:
            if g.get("id") in DROP:
                continue
            g = dict(g, required=False, size=min(g.get("size", 2), 2))
            if g.get("id") == "sead":            # одна пара с ПРР: пуск незадолго до удара, без долгого ожидания
                g["lead_min"] = SEAD_LEAD_MIN
                g["need_unit_field"] = "arm_pylons|arm"   # только носители ПРР: HARM (с 08.2022), Х-58/Х-25 (Су-24М)
                g["hold_after_min"] = 0
                g.setdefault("ai", {}).setdefault("attack", {})["passes"] = PASSES
                g["required_note"] = "ВСУ 2022: подавление ПВО - не обязательное и не поочерёдное (ОЦЕНКА)"
            sup.append(g)
        t["support"] = [] if kind in SINGLE else sup   # одна пара без пакета
        if kind in ATTACK_TOO and "attack" not in t.get("performers", []):
            t["performers"] = list(t["performers"]) + ["attack"]   # Су-25 - вместо недостающих бомбардировщиков
    # вертолёты ВСУ - с малых скрытых площадок в поле (пара-две), смена площадки через 1-3 суток; ближе к фронту, чем
    # готовые площадки (farp.py). ОЦЕНКИ по открытым репортажам о работе армейской авиации ВСУ 2022
    d["sim"].update({"farp_field_prefer": 1, "farp_field_cap": 4, "farp_field_move_days": 2, "farp_min_km": 12,
                     "farp_max_km": 40, "farp_reach_km": 400})   # основные аэродромы далеко в тылу (рассредоточение)
    (DOC / "ua.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ua.json:", ", ".join(f"{k}:{(t.get('strike') or {}).get('size')}" for k, t in d["tasks"].items() if t.get("strike")))


if __name__ == "__main__":
    main()

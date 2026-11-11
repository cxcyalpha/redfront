"""Наземная РЭБ (ОЦЕНКИ): станции подавления навигации, управления беспилотниками и связи.

Станция - наземная часть (роль ew_site): цель разведки и ударов (задача strike_ew в доктринах), в миссии - группой
машин (моделей станций в DCS нет - грузовики/КП, замена в имени). Эффекты считаются в модели кампании, не в DCS
(ИИ DCS помех навигации не знает), и ограничены - помеха ухудшает, но не обнуляет:
  * gnss - подавление спутниковой навигации в радиусе: КВО ракет и бомб со спутниковой коррекцией - больше
    (инерциальные - нет; GNSS_SENS);
  * uav - подавление каналов управления и навигации беспилотников: удар беспилотника (crew 0) по цели в радиусе -
    реже успешен, потерь больше;
  * comms - подавление связи: темп части противника в радиусе - ниже (COMMS_SLOW), наступление вязнет.
Сильнее одной станции эффект не становится (зона - объединение кругов, не сумма). Боеспособность станции ниже
MIN_STRENGTH - станция не работает.
"""
from __future__ import annotations

from . import model

# станция: эффект -> радиус, км (открытые оценки порядка величины; ОЦЕНКА)
STATIONS = {
    "pole21": {"title": "Поле-21 (подавление ГНСС)", "gnss": 50},
    "zhitel": {"title": "Р-330Ж Житель (связь, ГНСС)", "comms": 25, "gnss": 25},
    "leer3": {"title": "Леер-3 (связь, беспилотники Орлан-10)", "comms": 30, "uav": 20},
    "krasukha": {"title": "Красуха-4 (РЛС, беспилотники с РЛС)", "uav": 40},
    "repellent": {"title": "Репеллент-1 (беспилотники)", "uav": 30},
    "bukovel": {"title": "Буковель-АД (беспилотники, ГНСС)", "uav": 15, "gnss": 15},
    "notch": {"title": "Нота (беспилотники, ГНСС)", "uav": 20, "gnss": 20},
}
# рост КВО ракеты в зоне подавления ГНСС (1 - не зависит: чисто инерциальные, радиокомандные)
GNSS_SENS = {"iskander": 1.5, "kh101": 1.5, "kh555": 2.0, "kh65": 1.5, "tlam": 2.0, "agm86c": 2.0, "kd20": 1.5,
             "scud": 1.0, "tochka": 1.0, "kh22": 1.0}
UAV_HIT_K = 0.6          # ОЦЕНКА: доля успеха удара беспилотника в зоне подавления (от обычной)
UAV_LOSS_ADD = 0.15      # ОЦЕНКА: добавка к вероятности потери беспилотника в зоне
COMMS_SLOW = 0.8         # ОЦЕНКА: темп наступления части в зоне подавления связи
MIN_STRENGTH = 0.3


def stations(state: dict, side: str) -> list[dict]:
    """Работающие станции стороны: [(часть, позиция, эффекты)]."""
    out = []
    for u in state["units"].values():
        if u.get("side") != side or model.category(u) != "ew_site" or u.get("state") in ("destroyed", "pending"):
            continue
        if model.strength(u) < MIN_STRENGTH:
            continue
        spec = STATIONS.get(u.get("station", ""), {})
        out.append({"unit": u, "pos": model.unit_pos(state, u), **{k: v for k, v in spec.items() if k != "title"}})
    return out


def covered(state: dict, jammer_side: str, pos: dict, effect: str) -> bool:
    """Точка в зоне подавления (effect) станций стороны jammer_side."""
    return any(s.get(effect) and model.dist_km(s["pos"], pos) <= s[effect] for s in stations(state, jammer_side))


def cep_factor(state: dict, defender: str, pos: dict, missile: str) -> float:
    """Рост КВО ракеты у цели в зоне подавления ГНСС обороняющейся стороны."""
    return GNSS_SENS.get(missile, 1.0) if covered(state, defender, pos, "gnss") else 1.0


def is_uav(unit: dict | None) -> bool:
    return bool(unit) and model.aircraft_info(unit.get("type", "")).get("crew") == 0


def uav_factors(state: dict, attacker: dict | None, pos: dict) -> tuple[float, float]:
    """(множитель успеха, добавка потерь) удара беспилотника по точке в зоне подавления противника."""
    if not is_uav(attacker) or not covered(state, model.enemy(attacker["side"]), pos, "uav"):
        return 1.0, 0.0
    return UAV_HIT_K, UAV_LOSS_ADD


def tempo_factor(state: dict, unit: dict) -> float:
    """Темп части в зоне подавления связи противника."""
    pos = model.unit_pos(state, unit)
    return COMMS_SLOW if pos and covered(state, model.enemy(unit["side"]), pos, "comms") else 1.0

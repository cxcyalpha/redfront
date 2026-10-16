"""Пригодность типа ЛА для задачи с учётом эпохи.

aircraft.json: fit - оценка типа по видам задач на одной шкале для всех эпох (0..1, ОЦЕНКИ): cas - удар по войскам,
interdiction - по колоннам и путям подвоза, strike - по объектам тыла, sead - по ПВО, air - воздушный бой и перехват.
Сравнивается не с лучшим самолётом вообще, а с лучшим из тех, кто есть в этой кампании (у обеих сторон): эпоху задаёт
состав сил. Условный A-4 в кампании 1965 года - лучший штурмовик (1.0); в кампании 1989 года рядом с A-10 - 0.6.

Где используется:
  * выбор исполнителя (planner): сначала пригодный - относительная оценка минус FIT_LOAD_PENALTY за каждую задачу,
    уже выданную его типу и полку в этом плане (лучший тип берёт больше, но не всё); ниже FIT_MIN - не назначается;
  * итог удара ИИ вне миссии (airwar, convoys): успех и потери цели - с множителем 0.6 + 0.4 x оценка.
Нет оценки у типа (или ни у кого в кампании для этого вида задач) - 1.0: как раньше, без учёта типа.
"""
from __future__ import annotations

from . import model

FIT_MIN = 0.3               # ОЦЕНКА: тип с относительной оценкой ниже - для задачи не назначается
FIT_LOAD_PENALTY = 0.15     # ОЦЕНКА: минус к оценке за каждую задачу типа и полка в этом плане (разнообразие вылетов)

KIND_CLASS = {               # вид задачи доктрины -> вид оценки (задача может задать свой: tdef["fit"])
    "cas_contact": "cas", "cas_helo": "cas",
    "strike_column_march": "interdiction", "strike_supply_route": "interdiction",
    "strike_bridge": "strike", "strike_depot": "strike", "strike_factory": "strike", "strike_airfield": "strike",
    "strike_sam_site": "strike",          # удар по позиции ЗРК - бомбами; подавление ПВО - группа обеспечения (sead)
    "cap_own_troops": "air", "qra": "air",
}
MAINTASK_CLASS = {"SEAD": "sead", "CAP": "air", "Escort": "air", "Intercept": "air", "Fighter Sweep": "air",
                  "CAS": "cas", "Ground Attack": "strike", "Pinpoint Strike": "strike", "Runway Attack": "strike"}


def task_class(kind: str, tdef: dict | None = None) -> str | None:
    return (tdef or {}).get("fit") or KIND_CLASS.get(kind)


def group_class(maintask: list[str] | str | None, default: str | None) -> str | None:
    """Вид оценки группы обеспечения - по её основной задаче DCS (подавление ПВО - sead, прикрытие - air)."""
    mt = maintask[0] if isinstance(maintask, list) and maintask else maintask
    return MAINTASK_CLASS.get(mt or "", default)


def absolute(type_name: str, cls: str | None) -> float | None:
    if not cls:
        return None
    fit = model.aircraft_info(type_name).get("fit")
    if fit is None:
        return None                              # тип без оценок - без учёта типа
    return fit.get(cls, 0.0)                     # оценки есть, а этого вида задач нет - тип для него не годится


def era_best(state: dict, cls: str) -> float | None:
    """Лучшая оценка этого вида задач среди типов кампании (обе стороны, в строю): эпоха - по составу сил."""
    vals = [absolute(u.get("type", ""), cls) for u in state["units"].values()
            if model.category(u) in ("air", "heli") and u.get("count", 0) > 0]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def relative(state: dict, type_name: str, cls: str | None) -> float:
    """Оценка типа относительно лучшего в кампании (0..1); нет данных - 1.0."""
    a = absolute(type_name, cls)
    best = era_best(state, cls) if cls else None
    if a is None or not best:
        return 1.0
    return a / best


def pick_key(state: dict, unit: dict, cls: str | None, load: int) -> float:
    """Чем меньше, тем раньше исполнитель: минус (относительная оценка - штраф за загрузку)."""
    return -(relative(state, unit.get("type", ""), cls) - FIT_LOAD_PENALTY * load)


def fits(state: dict, unit: dict, cls: str | None) -> bool:
    return relative(state, unit.get("type", ""), cls) >= FIT_MIN


def outcome_factor(state: dict, type_name: str, cls: str | None) -> float:
    """Множитель успеха удара ИИ вне миссии: 0.6 + 0.4 x относительная оценка (лучший в кампании - 1.0)."""
    return 0.6 + 0.4 * relative(state, type_name, cls)

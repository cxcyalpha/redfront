"""Поиск типов pydcs по имени из состава сил: имя класса pydcs (Su_25, Patriot_ln) или DCS id ("Su-25", "Patriot ln").

Моды: тип мода (Saved Games/Mods/Aircraft) pydcs не знает, пока он не зарегистрирован - это отдельный шаг.
"""
from __future__ import annotations

import functools
import logging

from dcs import helicopters, planes, vehicles
from dcs.liveries import livery as _livery

log = logging.getLogger("redfront")


def _skip_broken_livery(fn):
    """pydcs сканирует все ливреи (DCS и Saved Games) при создании ЛА и пробрасывает ошибку разбора description.lua:
    одна битая сторонняя ливрея роняла сборку любой миссии. Битая ливрея пропускается - в миссии просто не будет
    предложена как ливрея по умолчанию."""
    @functools.wraps(fn)
    def wrapper(path):
        try:
            return fn(path)
        except (IndexError, SyntaxError, ValueError, KeyError) as e:
            log.warning("redfront: ливрея пропущена, не удалось разобрать %s (%s)", path, type(e).__name__)
            return None
    return wrapper


if not getattr(_livery.Livery.from_path, "_redfront_patched", False):
    _livery.Livery.from_path = staticmethod(_skip_broken_livery(_livery.Livery.from_path))
    _livery.Livery.from_path._redfront_patched = True


def _index_vehicles() -> dict:
    idx = {}
    for grp in vars(vehicles).values():
        if isinstance(grp, type):
            for k, v in vars(grp).items():
                if isinstance(v, type) and hasattr(v, "id"):
                    idx.setdefault(k, v)
                    idx.setdefault(v.id, v)
    return idx


def _index_flying() -> dict:
    idx = {}
    for mod in (planes, helicopters):
        for k, v in vars(mod).items():
            if isinstance(v, type) and getattr(v, "__module__", "") == mod.__name__ and hasattr(v, "id") and hasattr(v, "pylons"):
                idx.setdefault(k, v)
                idx.setdefault(v.id, v)
    return idx


_V: dict | None = None
_F: dict | None = None


def vehicle(name: str):
    global _V
    if _V is None:
        _V = _index_vehicles()
    try:
        return _V[name]
    except KeyError:
        raise KeyError(f"pydcs не знает наземный тип '{name}' (имя класса или DCS id)") from None


def flying(name: str):
    global _F
    if _F is None:
        _F = _index_flying()
    try:
        return _F[name]
    except KeyError:
        raise KeyError(f"pydcs не знает летательный аппарат '{name}' (имя класса или DCS id). "
                       f"Типы модов пока не регистрируются.") from None


def detection_range_km(type_names: list[str]) -> float | None:
    """Наименьшая дальность обнаружения среди типов с РЛС (pydcs detection_range > 0, м -> км); None - РЛС ни у кого нет.
    Наименьшая - чтобы рубеж был в зоне обнаружения каждой РЛС группы."""
    r = [float(getattr(vehicle(n), "detection_range", 0) or 0) / 1000.0 for n in type_names]
    r = [x for x in r if x > 0]
    return min(r) if r else None


def threat_range_km(type_names: list[str]) -> float:
    """Наибольшая дальность поражения среди типов (pydcs threat_range, м -> км). 0, если ни у одного нет."""
    best = 0.0
    for n in type_names:
        best = max(best, float(getattr(vehicle(n), "threat_range", 0) or 0) / 1000.0)
    return best

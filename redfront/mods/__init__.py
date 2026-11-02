"""Моды DCS (самолёты сообщества): типы и оружие для pydcs, включаются по кампании (settings.mods).

Описание типа мода - модуль в этом пакете (из DCS Retribution, pydcs_extensions, LGPL-3.0): класс PlaneType с id,
пилонами и оружием, регистрация в pydcs (plane_map) и в индексе типов redfront (dcstypes). Часть состава сил на типе
мода - поля mod (id мода) и type (тип мода): мод выключен - части в кампании нет (count 0, mod_off), включён - есть.
Описания типа нет в пакете - мод нельзя включить (available() - False), части остаются вне кампании.
"""
from __future__ import annotations

import importlib
import importlib.util
from typing import Any

MODS = {   # id -> название, модуль, типы (имя класса pydcs -> DCS id), страница мода
    "a4ec": {"title": "A-4E-C Skyhawk (мод сообщества)", "module": "a4ec", "types": {"A_4E_C": "A-4E-C"},
             "url": "https://github.com/Community-A-4E/community-a4e-c"},
}
_LOADED: set[str] = set()


def _bundle() -> None:   # pragma: no cover - не вызывается: явный импорт, чтобы сборщик (PyInstaller) включил описания модов
    from . import a4ec, a6e  # noqa: F401


def planemod(plane):
    """Тип мода - в справочник pydcs (как game.modsupport.planemod в Retribution)."""
    from dcs.planes import plane_map
    plane_map[plane.id] = plane
    return plane


def inject_weapons(weapon_class: Any) -> None:
    """Оружие мода - в справочник оружия pydcs (как pydcs_extensions.weapon_injector в Retribution)."""
    from dcs.weapons_data import Weapons, weapon_ids
    for key, value in weapon_class.__dict__.items():
        if not key.startswith("__") and isinstance(value, dict) and value.get("clsid"):
            setattr(Weapons, key, value)
            weapon_ids[value["clsid"]] = value


def available(mod_id: str) -> bool:
    """Описание типа мода есть в пакете (его можно включить)."""
    return mod_id in MODS and importlib.util.find_spec(f"{__name__}.{MODS[mod_id]['module']}") is not None


def load(mod_id: str) -> bool:
    """Зарегистрировать типы мода в pydcs и в индексе redfront (один раз за сеанс). False - описания типа нет."""
    if mod_id in _LOADED:
        return True
    if not available(mod_id):
        return False
    m = importlib.import_module(f"{__name__}.{MODS[mod_id]['module']}")
    from .. import dcstypes
    for cls_name in MODS[mod_id]["types"]:
        dcstypes.register_flying(cls_name, getattr(m, cls_name))
    _LOADED.add(mod_id)
    return True


def apply(state: dict) -> list[str]:
    """Моды кампании: включённые - загрузить; части на типах модов - в строй (мод включён и описан) или вне кампании."""
    on = {m for m in ((state.get("settings") or {}).get("mods") or []) if load(m)}
    lines = []
    for u in state.get("units", {}).values():
        mid = u.get("mod")
        if not mid:
            continue
        if mid in on:
            if u.get("mod_off"):
                u["count"] = u.pop("mod_count", u.get("count0", 0))
                u.pop("mod_off")
                lines.append(f"{u['name']}: в строю (мод {MODS.get(mid, {}).get('title', mid)}).")
        elif not u.get("mod_off"):
            u["mod_count"], u["count"], u["mod_off"] = u.get("count", 0), 0, True
    return lines

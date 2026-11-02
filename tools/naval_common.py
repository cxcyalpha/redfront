"""Корабельные группы для генераторов сценариев (redfront.naval): часть флота с составом по кораблям DCS (класс pydcs и
реальные имена кораблей класса). Позиция - в море (ОЦЕНКА)."""
from __future__ import annotations


def group(uid: str, name: str, side: str, lat: float, lon: float, ships: list[tuple[str, str, str]], note: str = "",
          source: str = "", abbr: str = "", orders: list | None = None, quality: float | None = None,
          ecm: float | None = None) -> dict:
    """ships: [(класс pydcs, роль корабля, имя)] - одинаковые классы собираются в одну строку состава с именами."""
    comp: dict[str, dict] = {}
    for typ, role, nm in ships:
        c = comp.setdefault(typ, {"type": typ, "count": 0, "role": role, "names": []})
        c["count"] += 1
        c["names"].append(nm)
    u = {"id": uid, "name": name, "side": side, "role": "naval", "state": "deployed", "fixed": True,
         "pos": {"lat": lat, "lon": lon}, "composition": list(comp.values()), "abbr": abbr,
         "source": source + ("; " + note if note else ""), "estimate": True}
    if orders:
        u["orders"] = orders
    if quality:
        u["quality"] = quality
    if ecm:
        u["ecm"] = ecm
    return u

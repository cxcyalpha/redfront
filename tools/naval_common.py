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


# Шаблоны корабельных групп по эпохам: [(роль, класс DCS)] после головного корабля. В DCS нет кораблей охранения
# 1960-70-х (Leahy/Belknap, Adams, Knox): их замещают Ticonderoga и Perry - ДОПУЩЕНИЕ (ЗРК и ПКР в модели - по
# классу DCS, сильнее реальных). Имена кораблей - реальные корабли эпохи; число кораблей охранения - ОЦЕНКА по
# типовому составу (1972: ~4 корабля охранения, в DCS-миссии - 3; 1983: крейсер УРО и 2 фрегата).
TEMPLATES = {
    "us_csg_1972": [("cruiser", "TICONDEROG"), ("frigate", "PERRY"), ("frigate", "PERRY")],
    "us_csg_1983": [("cruiser", "TICONDEROG"), ("frigate", "PERRY"), ("frigate", "PERRY")],
    "us_arg_1983": [("frigate", "PERRY"), ("frigate", "PERRY")],
}
TEMPLATE_NOTE = {
    "us_csg_1972": "шаблон CSG 1972: авианосец, крейсер УРО (в DCS - Ticonderoga вместо Leahy/Belknap), 2 эсминца (в DCS - Perry)",
    "us_csg_1983": "шаблон CSG 1983: авианосец, крейсер УРО, 2 фрегата УРО",
    "us_arg_1983": "шаблон ARG 1983: УДК, 2 фрегата охранения",
}


def from_template(tpl: str, lead: tuple[str, str, str], names: list[str]) -> list[tuple[str, str, str]]:
    """Состав группы по шаблону: lead - (класс, роль, имя) головного корабля, names - имена охранения по порядку."""
    rows = TEMPLATES[tpl]
    if len(names) != len(rows):
        raise ValueError(f"{tpl}: нужно {len(rows)} имён охранения, дано {len(names)}")
    return [lead] + [(typ, role, nm) for (role, typ), nm in zip(rows, names)]

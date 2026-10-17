"""Сборка .miz через pydcs: звено игрока, развёрнутое окно наземной модели, хук дебрифа.

Манифест (что развёрнуто, с какими весами) сохраняется в состоянии кампании: по нему дебриф возвращает потери в модель.
"""
from __future__ import annotations

import copy
import datetime
import json
import math
import tempfile
from pathlib import Path

from dcs import Mission, task
from dcs.action import DoScript, DoScriptFile
from dcs.mapping import LatLng, Point, Vector2
from dcs.mission import StartType
from dcs.point import PointAction
from dcs.terrain.germany import Germany
from dcs.terrain.terrain import NoParkingSlotError
from dcs.translation import String
from dcs.triggers import TriggerStart
from dcs.unit import Skill

from . import csar, dcstypes, materialize, model, planner
from .ato import MISSION_LEN_S as ATO_LEN_S
from .ato import is_night as _ato_night

LUA = Path(__file__).parent / "lua" / "debrief_hook.lua"
COLUMN_LUA = Path(__file__).parent / "lua" / "column_road.lua"
FRONT_LUA = Path(__file__).parent / "lua" / "front.lua"
SITE_LUA = Path(__file__).parent / "lua" / "battle_site.lua"
ASSAULT_LUA = Path(__file__).parent / "lua" / "assault.lua"
EVAC_LUA = Path(__file__).parent / "lua" / "evac.lua"
CSAR_LUA = Path(__file__).parent / "lua" / "csar.lua"
LZ_LUA = Path(__file__).parent / "lua" / "lz.lua"
QRA_LUA = Path(__file__).parent / "lua" / "qra.lua"
BEACON_FILE = "redfront_beacon.wav"
# CTLD (lua/ctld/NOTICE.md): погрузка и высадка десанта игрока, ящики снабжения, авианаводчик. ОЦЕНКИ - размеры зон.
CTLD_DIR = Path(__file__).parent / "lua" / "ctld"
CTLD_CFG_LUA = Path(__file__).parent / "lua" / "ctld_cfg.lua"
CTLD_PICKUP_M = 800             # зона погрузки десанта вокруг стоянки игрока
CTLD_DROP_M = 2500              # зона выгрузки снабжения вокруг аэродрома назначения
CTLD_LOGISTIC_M = 50            # машина тыла (у неё берут ящики) - от стоянки игрока, в сторону от центра аэродрома
CTLD_LOGISTIC = {"red": "Ural-375", "blue": "M 818"}
CTLD_CRATE_UNIT = {"red": "Ural-375", "blue": "M 818"}   # ящик распакован - машина с грузом (скрипт её убирает: груз - на склад)
JTAC_TYPES = {"red": "UAZ-469", "blue": "Hummer"}         # пост авианаводчика у своего взвода в бою
JTAC_CODE = 1688

# Бой наземных частей в миссии (lua/front.lua). Все числа - ОЦЕНКИ.
PLATOON = 4                # машин во взводе (отдельная группа DCS: застрявшая машина не держит всю часть)
BATTLE_ZONE_M = 2000       # радиус района удара по части в бою (EngageTargetsInZone) вокруг её боевого порядка
FIRE_RANGE_MAX_M = 3000    # окна огня front.lua: цели не дальше 3 км (Alex: дальний выстрел танка), даже если у типа ПТУР дальше
FRONT_CFG = {
    "init_s": 3,                                          # с: начало после расстановки по местности (battle_site.lua)
    "period_min": 20, "period_max": 45, "first_min": 5,   # с между окнами огня взвода
    "burst_s": 6,                                         # длительность окна огня, с
    "salvo": 2,                                           # выстрелов на окно (expendQty)
    "aim_min": 25, "aim_max": 80, "aim_radius": 10,       # промах относительно цели, м
    "retreat_below": 0.6,                                 # наступающий отходит, если в миссии в строю меньше этой доли
    "retreat_speed": 6, "check_s": 30,                    # м/с, с
    "shift_m": 60, "shift_min": 90, "shift_max": 180, "shift_speed": 3,   # "живые" позиции обороны
}


def _pt(m: Mission, p: dict) -> Point:
    return Point.from_latlng(LatLng(p["lat"], p["lon"]), m.terrain)


MISSION_COUNTRIES = {"red": "Combined Joint Task Forces Red", "blue": "Combined Joint Task Forces Blue"}


def _country(m: Mission, state: dict, side: str):
    """Страна стороны в миссии: Combined Joint Task Forces Red / Blue (в них в DCS есть вся техника и авиация всех
    стран; национальность частей - в составе сил, countries, для модели). В pydcs у страны есть коалиция по умолчанию;
    если она не совпадает со стороной, страна переносится в коалицию стороны."""
    name = MISSION_COUNTRIES.get(side) or state["countries"][side]
    for cname, coal in m.coalition.items():
        if coal.country(name) is not None:
            if cname != side:
                coal.swap_country(m.coalition[side], name)
            return m.coalition[side].country(name)
    from dcs import countries as _countries   # CJTF в коалиции новой миссии pydcs нет - добавить
    try:
        m.coalition[side].add_country(_countries.get_by_name(name))   # pydcs отдаёт готовый объект страны
    except KeyError:
        raise KeyError(f"pydcs не знает страну '{name}'") from None
    return m.coalition[side].country(name)


def _loadout(type_name: str, category: str) -> dict | None:
    """Пилоны из loadouts.json для типа и категории подвески; None - оставить загрузку DCS по умолчанию для maintask."""
    return model.load_json("loadouts.json").get(type_name, {}).get(category)


def lua_hook(campaign_id: str, sortie: int, track: list[str]) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    return (LUA.read_text(encoding="utf-8")
            .replace("@CAMPAIGN@", campaign_id)
            .replace("@SORTIE@", str(int(sortie)))
            .replace("@TRACK@", ", ".join(q(n) for n in track)))


def column_spec(m: Mission, state: dict, g: dict, vg) -> dict | None:
    """Данные для column_road.lua: пункты оставшихся участков (от пункта позади головы до конца маршрута), голова,
    дистанция, скорость, машины по порядку, groupId и страна. None - все эти участки модели уже известны по дорогам
    (колонна и так поставлена на дорогу), перекладывать не нужно."""
    unit = state["units"][g.get("route_owner", g["unit"])]     # у приданной группы маршрут - её части
    head_km = g["vehicles"][0].get("km", unit["progress_km"])
    pk = model.place_km(state, unit)
    behind = max((i for i, (_p, k) in enumerate(pk) if k <= head_km + 1e-6), default=0)
    names = [p for p, _k in pk[behind:]]
    if len(names) < 2:
        return None
    pairs = [f"{a}>{b}" for a, b in zip(names, names[1:])]
    if all(pr in (state.get("roads") or {}) for pr in pairs):
        return None
    def xy(p):
        q = _pt(m, p)
        return q.x, q.y
    march = model.doctrine(state, unit["side"])["march"]
    country = _country(m, state, g["side"])
    return {
        "name": vg.name, "groupId": vg.id, "country": country.id,
        "places": [(n, *xy(state["places"][n])) for n in names],
        "head": xy(g["vehicles"][0]),
        "spacing": march["spacing_m"], "speed": g["speed_kmh"] / 3.6,
        "units": [(v["name"], dcstypes.vehicle(v["type"]).id, (head_km - v.get("km", head_km)) * 1000) for v in g["vehicles"]],
        "route": [xy(w) for w in g["waypoints"]],
        "options": ground_options(state, g),          # после пересоздания группы опции ставятся заново (в .miz они теряются)
    }


class ActivateGCI(task.WrappedAction):
    """Команда DCS: включить КРУ (GCI_station_MiG29) - канал наведения и радиус, м (как в редакторе миссий)."""
    Key = "ActivateGCI"

    def __init__(self, channel: int = 1, unit_id: int = 0, radius_m: int = 250000):
        super().__init__()
        self.auto = True                         # как ставит редактор миссий
        self.params = {"action": {"id": ActivateGCI.Key,
                                  "params": {"channel": int(channel), "unitId": int(unit_id), "radius": int(radius_m),
                                             "x": 0, "y": 0}}}


task.wrappedactions.setdefault(ActivateGCI.Key, ActivateGCI)   # pydcs читает миссии с КРУ (тесты, повторная загрузка)


def ground_options(state: dict, g: dict) -> list[tuple[int, int]]:
    """Опции наземной группы: всё, кроме ПВО, стреляет только по наземным целям (OptRestrictTargets = GroundUnitsOnly).
    Наземные юниты в DCS по ЛА бьют неестественно точно; ПВО (ЗРК, ЗА) - без ограничения."""
    if g["kind"] in ("downed", "convoy") or model.category(state["units"][g["unit"]]) in ("sam", "gci"):
        return []                                # экипаж на земле, колонна снабжения - не части модели, огонь не ведут
    return [(task.OptRestrictTargets.Key, int(task.OptRestrictTargets.Values.GroundUnitsOnly))]


def column_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = []
    for c in specs:
        places = ", ".join(f'{{ id = {q(n)}, x = {x:.1f}, y = {y:.1f} }}' for n, x, y in c["places"])
        units = ", ".join(f'{{ name = {q(n)}, type = {q(t)}, off = {off:.1f} }}' for n, t, off in c["units"])
        opts = ", ".join(f'{{ {int(k)}, {int(v)} }}' for k, v in c.get("options", []))
        route = ", ".join(f'{{ x = {x:.1f}, y = {y:.1f} }}' for x, y in c["route"])
        items.append(f'{{ name = {q(c["name"])}, groupId = {int(c["groupId"])}, country = {int(c["country"])}, '
                     f'head = {{ x = {c["head"][0]:.1f}, y = {c["head"][1]:.1f} }}, spacing = {c["spacing"]:.1f}, speed = {c["speed"]:.3f}, '
                     f'places = {{ {places} }}, units = {{ {units} }}, route = {{ {route} }}, options = {{ {opts} }} }}')
    return (COLUMN_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id)
            .replace("@SORTIE@", str(int(sortie))).replace("@COLUMNS@", ", ".join(items)))


# Расстановка боя по местности в миссии (lua/battle_site.lua). Все числа - ОЦЕНКИ; веса: дорога > у дороги > поле > застройка.
SITE_SEARCH_M = 2500       # в каких пределах сдвигать место боя целиком (если модель его ещё не помнит)
POSITION_SEARCH_M = 1000   # то же для части в обороне или в тылу (одна часть, без боя)
SITE_CFG = {
    "site_step": 500, "sample": 3,                         # шаг сетки места боя, м; оценка по каждой sample-й машине
    "snap_rings": "{ 0, 25, 50, 75, 100 }", "snap_dirs": 8, # куда можно сдвинуть машину от её точки, м
    "min_gap": 20,                                          # м между машинами
    "max_slope": 4, "slope_step": 15,                       # перепад высот больше max_slope на +-slope_step м - склон, нельзя
    "near_road": 60,                                        # м: "у дороги"
    "w_road": 3, "w_near_road": 2, "w_field": 1,            # оценка точки
    "w_building": 0.5, "building_r": 30, "building_cap": 6, # минус за строения (объекты карты) ближе building_r м
    "w_reject": -3,                                         # точка в воде или на склоне - при выборе места боя
    "w_distance": 0.3, "w_snap": 0.3,                       # минус за удаление от расчётного места (на км) и машины от своей точки (на 100 м)
    # ПВО (ЗРК, ЗА): открытое место - поле, можно у дороги; не на дороге и не в застройке (со двора не видно и не найти)
    "ad_rings": "{ 0, 50, 100, 200, 300, 400 }", "ad_dirs": 12,   # куда можно сдвинуть машину ПВО, м
    "ad_gap": 80,                                           # м между машинами ПВО
    "ad_runway_clear": 150,                                 # м от бетона аэродрома (ВПП, рулёжки, стоянки) - не ближе
    "ad_site_rings": "{ 500, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 8000 }",   # м: сдвиг всей позиции ПВО с аэродрома, из воды, из города
    "ad_town_r": 150, "ad_town_n": 5,                       # город: строений ближе ad_town_r м - не меньше ad_town_n
    "ad_building_r": 60, "ad_w_building": 3,                # минус за каждое строение ближе ad_building_r м
    "ad_w_field": 2, "ad_w_near_road": 0.5, "ad_near_road": 200, "ad_w_road": -1,
}


def battle_key(units: list[str]) -> str:
    """Ключ боя - части, связанные соприкосновением (по нему модель помнит выбранное в миссии место)."""
    return "+".join(sorted(units))


def site_script(campaign_id: str, sortie: int, battles: list[dict], ads: list[dict] | None = None) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    cfg = "{ " + ", ".join(f"{k} = {v}" for k, v in SITE_CFG.items()) + " }"
    items = []
    for b in battles:
        pls = []
        for p in b["platoons"]:
            units = ", ".join(f'{{ name = {q(u["name"])}, type = {q(u["type"])}, x = {u["x"]:.1f}, y = {u["y"]:.1f}, heading = {u["heading"]:.4f} }}'
                              for u in p["units"])
            route = ", ".join(f"{{ x = {x:.1f}, y = {y:.1f} }}" for x, y in p["route"])
            opts = ", ".join(f"{{ {k}, {v} }}" for k, v in p["options"])
            pls.append(f'{{ name = {q(p["name"])}, groupId = {p["groupId"]}, country = {p["country"]}, speed = {p["speed"]:.2f}, '
                       f'units = {{ {units} }}, route = {{ {route} }}, options = {{ {opts} }} }}')
        items.append(f'{{ key = {q(b["key"])}, search_r = {b["search_r"]:.0f}, shift = {{ x = {b["shift"][0]:.1f}, y = {b["shift"][1]:.1f} }}, '
                     f'platoons = {{ {", ".join(pls)} }} }}')
    ad_items = []
    for a in ads or []:
        units = ", ".join(f'{{ name = {q(u["name"])}, type = {q(u["type"])}, x = {u["x"]:.1f}, y = {u["y"]:.1f}, heading = {u["heading"]:.4f}'
                          + (f', unitId = {u["unitId"]}' if u.get("unitId") else "") + " }"
                          for u in a["units"])
        gci = (f'{{ channel = {a["gci"]["channel"]}, radius = {a["gci"]["radius"]} }}' if a.get("gci") else "nil")
        ad_items.append(f'{{ name = {q(a["name"])}, groupId = {a["groupId"]}, country = {a["country"]}, '
                        f'follow = {q(a["follow"]) if a.get("follow") else "nil"}, gci = {gci}, units = {{ {units} }} }}')
    return (SITE_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@CFG@", cfg).replace("@BATTLES@", ", ".join(items)).replace("@ADS@", ", ".join(ad_items)))


def _battle_platoons(m: Mission, state: dict, g: dict, shift_xy: tuple[float, float] = (0.0, 0.0)) -> list[tuple]:
    """Часть в бою - взводами по PLATOON машин, каждый - своя группа '<часть>/<k>' (имена машин - те же, что в модели).
    Огонь запрещён (ведёт его front.lua окнами), цели только наземные. Наступающий взвод идёт тем же вектором,
    что и боевой порядок. Возвращает [(группа, машины взвода)]."""
    country = _country(m, state, g["side"])
    vs = g["vehicles"]
    out = []
    shift = None
    sx, sy = shift_xy                            # место боя, запомненное моделью (сдвиг, м)
    if g["waypoints"]:
        c, w = _pt(m, g["center"]), _pt(m, g["waypoints"][0])
        shift = (w.x - c.x, w.y - c.y)
    for k in range(0, len(vs), PLATOON):
        part = vs[k:k + PLATOON]
        vg = None
        for v in part:
            p0 = _pt(m, v)
            pos = Point(p0.x + sx, p0.y + sy, m.terrain)
            if vg is None:
                vg = m.vehicle_group(country, f"{g['name']}/{k // PLATOON + 1}", dcstypes.vehicle(v["type"]), pos, group_size=1,
                                     move_formation=PointAction.OffRoad)
                vg.units[0].name = v["name"]
            else:
                u = m.vehicle(v["name"], dcstypes.vehicle(v["type"]))
                u.position = pos
                vg.add_unit(u)
            vg.units[-1].heading = v.get("heading", 0)
        if shift:
            x = sum(u.position.x for u in vg.units) / len(vg.units) + shift[0]
            y = sum(u.position.y for u in vg.units) / len(vg.units) + shift[1]
            vg.add_waypoint(Point(x, y, m.terrain), PointAction.LineAbreast, speed=g["speed_kmh"])
        vg.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponHold))
        for key, value in ground_options(state, g):
            vg.points[0].tasks.append(task.OptRestrictTargets(task.OptRestrictTargets.Values(value)))
        vg.set_skill(Skill.High)
        out.append((vg, part))
    return out


TARGETS_LUA = Path(__file__).parent / "lua" / "targets.lua"
TARGET_SCAN = {                            # ОЦЕНКИ: район поиска объектов карты и сколько их брать
    "depot": {"r": 150, "max": 12},
    "bridge": {"r": 150, "max": 4},        # только объекты типа "мост" (targets.lua), поэтому радиус шире
    "airfield": {"r": 600, "max": 25},
    "factory": {"r": 300, "max": 12},
}


NAMED_SCAN_M = 500                         # объекты карты цели известны по именам (mapobj.py) - радиус поиска с запасом


def targets_script(m: Mission, state: dict, objs: list[dict]) -> str:
    items = []
    for o in objs:
        p = _pt(m, o["pos"])
        sc = TARGET_SCAN[o["role"]]
        names = ", ".join(f'["{n}"] = true' for n in o.get("map_objects", []))   # имена объектов карты, если мост уточнён
        r = max(sc["r"], NAMED_SCAN_M) if o.get("map_objects") else sc["r"]          # по именам - шире, чужое не возьмётся
        items.append(f'{{ id = "{o["id"]}", role = "{o["role"]}", x = {p.x:.1f}, y = {p.y:.1f}, r = {r}, max = {max(sc["max"], len(o.get("map_objects", [])))}, '
                     f'names = {{ {names} }} }}')
    return (TARGETS_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@OBJECTS@", ", ".join(items)))


def front_script(campaign_id: str, sortie: int, platoons: list[dict]) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    cfg = "{ " + ", ".join(f"{k} = {v}" for k, v in FRONT_CFG.items()) + " }"
    items = [f'{{ name = {q(p["name"])}, formation = {q(p["formation"])}, attack = {"true" if p["attack"] else "false"}, '
             f'range = {p["range"]:.0f}, enemies = {{ {", ".join(q(e) for e in p["enemies"])} }} }}' for p in platoons]
    return (FRONT_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@CFG@", cfg).replace("@PLATOONS@", ", ".join(items)))


def qra_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    """lua/qra.lua: дежурные пары - группа (поздняя активация), коалиция, аэродром (x, y DCS), радиус взлёта."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ id = {q(a["id"])}, group = {q(a["group"])}, side = {a["side"]}, x = {a["x"]:.1f}, y = {a["y"]:.1f}, '
             f'r = {a["r"]:.0f}, title = {q(a["title"])} }}' for a in specs]
    return (QRA_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(items)))


def lz_script(campaign_id: str, sortie: int) -> str:
    """lua/lz.lua: открытые площадки для вертолётов, пересчёт маршрута ИИ (общий для csar.lua и assault.lua)."""
    return LZ_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))


def assault_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    """lua/assault.lua: высадка - борта и группы ИИ, рота (фигуры: имя и тип DCS), площадка (x, y DCS), радиус,
    страна и коалиция, посадка (с), аэродром возврата."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ id = {q(a["id"])}, title = {q(a["title"])}, side = {a["side"]}, country = {a["country"]}, '
             f'x = {a["x"]:.1f}, y = {a["y"]:.1f}, r = {a["r"]:.0f}, land = {int(a["land"])}, home = {a["home"]}, '
             f'helos = {{ {", ".join(q(n) for n in a["helos"])} }}, groups = {{ {", ".join(q(n) for n in a["groups"])} }}, '
             f'troops = {{ {", ".join(f"{{ name = {q(t[0])}, type = {q(t[1])} }}" for t in a["troops"])} }} }}' for a in specs]
    return (ASSAULT_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(items)))


def evac_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    """lua/evac.lua: эвакуация - борта и группы ИИ, площадка (x, y DCS), радиус, посадка (с), аэродром возврата, рота
    группами DCS (имена и типы фигур - пересоздаются у перенесённой площадки)."""
    return (EVAC_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(_lua(a) for a in specs)))


def csar_script(m: Mission, state: dict, downed: list[dict], rescuers: list[dict] | None = None) -> str:
    """lua/csar.lua: экипажи на земле из модели (группы в .miz), страны сторон для новых катапультировавшихся,
    аэродромы сторон (посадка с экипажем - спасён), звук маяка (ресурс миссии)."""
    from . import csar
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ id = {q(d["id"])}, group = {q(d["id"])}, side = {1 if d["side"] == "red" else 2}, '
             f'title = {q(csar.title(state, d))}, freq = {int(d["freq_khz"])} }}' for d in downed]
    bases = {side: ", ".join(f'[{q(b["airport"])}] = true' for b in state["airbases"].values() if b.get("side") == side)
             for side in ("red", "blue")}
    return (CSAR_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@SOUND@", BEACON_FILE)
            .replace("@DOWNED@", ", ".join(items))
            .replace("@RESCUERS@", ", ".join(f'{{ group = {q(r["group"])}, downed = {q(r["downed"])}, home = {r["home"]}, '
                                             f'land = {int(r["land"])} }}' for r in rescuers or []))
            .replace("@RED_COUNTRY@", str(_country(m, state, "red").id))
            .replace("@BLUE_COUNTRY@", str(_country(m, state, "blue").id))
            .replace("@RED_BASES@", bases["red"]).replace("@BLUE_BASES@", bases["blue"]))


def set_airbase_coalitions(m: Mission, state: dict) -> None:
    """Коалиция аэродромов в миссии - по модели: военные аэродромы сторон - их коалиции (потерянный - нейтральный:
    к противнику он не переходит), остальные аэродромы карты - нейтральные. По ней DCS даёт аэродрому сторону
    (связь, посадка "на свой" - спасение экипажа в csar.lua)."""
    for b in state["airbases"].values():
        ap = m.terrain.airports.get(b.get("airport") or "")
        if ap is None:
            continue
        ap.set_coalition("neutral" if b.get("state") == "lost" or b.get("side") not in ("red", "blue") else b["side"])


def airbase_script(m: Mission, state: dict) -> str:
    """Сторона аэродромов в DCS - и скриптом в начале миссии: без автозахвата (DCS иначе по своим правилам делает
    аэродромы без войск рядом нейтральными) и с явной стороной (Airbase.setCoalition)."""
    rows = []
    for b in state["airbases"].values():
        ap = m.terrain.airports.get(b.get("airport") or "")
        if ap is None:
            continue
        side = 0 if b.get("state") == "lost" or b.get("side") not in ("red", "blue") else (1 if b["side"] == "red" else 2)
        rows.append(f'{{{json.dumps(ap.name)}, {side}}}')
    return ("-- redfront airbases\nlocal L = {" + ", ".join(rows) + "}\n"
            "for _, r in ipairs(L) do\n"
            "  local ab = Airbase.getByName(r[1])\n"
            "  if ab then\n"
            "    pcall(function() ab:autoCapture(false) end)\n"
            "    pcall(function() ab:setCoalition(r[2]) end)\n"
            "  end\n"
            "end\n")


def _land(fg, airport, spd_kmh: float):
    """Посадка на аэродром. pydcs ставит точке посадки скорость 0 - ИИ на последнем участке гасит скорость до
    минимума (Су-17 и др. на возврате шли 300-400 км/ч и крутили фигуры, сбрасывая её). Скорость - как на маршруте:
    заход и посадку ИИ строит сам."""
    p = fg.land_at(airport)
    p.speed = spd_kmh / 3.6
    return p


def _ground_group(m: Mission, state: dict, g: dict, shift_xy: tuple[float, float] = (0.0, 0.0)):
    country = _country(m, state, g["side"])
    vs = g["vehicles"]
    vg = None
    for i, v in enumerate(vs):
        p0 = _pt(m, v)
        pos = Point(p0.x + shift_xy[0], p0.y + shift_xy[1], m.terrain)
        if vg is None:
            vg = m.vehicle_group(country, g["name"], dcstypes.vehicle(v["type"]), pos, group_size=1,
                                 move_formation=PointAction.OnRoad if g["kind"] in ("column", "convoy") else PointAction.OffRoad)
            vg.units[0].name = v["name"]
        else:
            u = m.vehicle(v["name"], dcstypes.vehicle(v["type"]))
            u.position = pos
            vg.add_unit(u)
        if "heading" in v:                         # курс задан шаблоном (позиция ЗРК развёрнута на ось угрозы)
            vg.units[-1].heading = v["heading"]
        elif g["kind"] in ("column", "convoy"):    # в колонне машина смотрит на впереди идущую (или на следующий пункт маршрута)
            nxt = vs[i - 1] if i > 0 else (g["waypoints"][0] if g["waypoints"] else None)
            if nxt is not None:
                vg.units[-1].heading = pos.heading_between_point(_pt(m, nxt))
    action = PointAction.LineAbreast if g.get("formation") == "line" else PointAction.OnRoad
    for wp in g["waypoints"]:
        p = vg.add_waypoint(_pt(m, wp), action, speed=g["speed_kmh"])
    for key, value in ground_options(state, g):  # не ПВО - огонь только по наземным целям
        vg.points[0].tasks.append(task.OptRestrictTargets(task.OptRestrictTargets.Values(value)))
    vg.set_skill(Skill.High)
    return vg


def _maintask(ac, prefs: list[str]):
    """Первая задача из списка доктрины, которую тип умеет (planes.X.tasks): у Су-25 в DCS нет SEAD - будет Ground Attack."""
    for name in prefs:
        t = getattr(task, name)
        if t in ac.tasks:
            return t
    return ac.task_default or getattr(task, prefs[0])


def _apply_loadout(fg, ac, type_name: str, cats: list[str]) -> str | None:
    """Первая категория подвески из списка, для которой есть запись в loadouts.json; None - загрузка DCS по умолчанию."""
    for cat in cats:
        lo = _loadout(type_name, cat)
        if lo:
            for u in fg.units:
                u.reset_loadout()                # flight_group_from_airport уже повесил загрузку DCS для maintask: без сброса пилоны смешиваются
                for pylon, wname in lo["pylons"].items():
                    u.load_pylon(getattr(getattr(ac, f"Pylon{pylon}"), wname))
            return cat
    return None


def _lua(v) -> str:
    """Значение Python -> литерал Lua (для таблиц настройки скриптов)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "/").replace('"', "'") + '"'
    if isinstance(v, dict):
        return "{ " + ", ".join(f"[{_lua(k)}] = {_lua(x)}" for k, x in v.items()) + " }"
    return "{ " + ", ".join(_lua(x) for x in v) + " }"


def troop_mix(type_ids: list[str]) -> dict:
    """Состав группы десанта для меню CTLD (inf, mg, at, aa) по типам фигур DCS."""
    out = {"inf": 0, "mg": 0, "at": 0, "aa": 0}
    for t in type_ids:
        low = t.lower()
        k = ("aa" if any(w in low for w in ("igla", "stinger", "manpad", "strela")) else
             "at" if "rpg" in low else "mg" if any(w in low for w in ("m249", "pkm", " mg")) else "inf")
        out[k] += 1
    return {k: n for k, n in out.items() if n}


def ctld_script(state: dict, cfg: dict) -> str:
    """lua/ctld_cfg.lua: настройка CTLD под вылет (борта игрока, зоны, группы десанта, ящики, авианаводчики)."""
    body = ", ".join(f"{k} = {_lua(cfg[k])}" for k in ("pilots", "actions", "limits", "cargo", "logistic", "pickup",
                                                       "groups", "crates", "lifts", "jtacs", "extract"))
    return (CTLD_CFG_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@CFG@", body))


def ctld_actions(m: Mission, state: dict, cfg: dict) -> list:
    """Скрипты CTLD в начале миссии: MIST, CTLD (копия с ctld.dontInitialize = true), настройка. Меню CTLD - как в
    оригинале, по-английски."""
    tmp = Path(tempfile.mkdtemp(prefix="redfront_ctld_"))
    src = (CTLD_DIR / "CTLD.lua").read_text(encoding="utf-8")
    patched = src.replace("ctld.dontInitialize = false", "ctld.dontInitialize = true", 1)
    if patched == src:
        raise RuntimeError("CTLD.lua: не найдено 'ctld.dontInitialize = false' - другая версия CTLD?")
    (tmp / "CTLD.lua").write_text(patched, encoding="utf-8")
    return [DoScriptFile(m.map_resource.add_resource_file(CTLD_DIR / "mist.lua")),
            DoScriptFile(m.map_resource.add_resource_file(tmp / "CTLD.lua")),
            DoScript(String(ctld_script(state, cfg)))]


def _away(m: Mission, p: Point, center: Point, d_m: float) -> Point:
    dx, dy = p.x - center.x, p.y - center.y
    n = math.hypot(dx, dy) or 1.0
    return Point(p.x + d_m * dx / n, p.y + d_m * dy / n, m.terrain)


_CREW: dict = {"names": set(), "pilots": {}}   # лётчики, уже посаженные в эту миссию (сброс - в начале build)


def _crew(state: dict, fg, perf: dict) -> None:
    """Экипажи группы - лётчики полка (pilots.py): имя ЛА в DCS = звание и фамилия; ливрея полка (u['livery'])."""
    from . import pilots
    taken = _CREW["pilots"].setdefault(perf["id"], set())
    for unit, p in zip(fg.units, pilots.crew_for(state, perf, len(fg.units), taken)):
        taken.add(p["name"])
        name = pilots.title(perf, p)
        if name in _CREW["names"]:               # однофамильцы в разных полках
            name = f"{name} ({perf['id']})"
        _CREW["names"].add(name)
        unit.name = name
    if perf.get("livery"):
        for unit in fg.units:
            unit.livery_id = perf["livery"]


def _set_player(unit, client: bool = False) -> bool:
    """Посадить игрока (client - место в мультиплеере). pydcs отказывает типам, которые в базовом DCS только для ИИ
    (Су-24М, МиГ-31): для мода, делающего такой тип летабельным на том же слоте, отказ лишний. Возвращает True, если
    слот требует мода."""
    if unit.unit_type.flyable:
        if client:
            unit.set_client()
        else:
            unit.set_player()
        return False
    unit.skill = Skill.Client if client else Skill.Player
    try:
        unit.set_radio_preset()
    except Exception:                            # пресетов радио для типа ИИ в pydcs может не быть - не критично
        pass
    return True


SEARCH_ORBIT_ALT_M = 600   # ОЦЕНКА: высота круга над районом поиска, если в доктрине нет search_alt_m (абсолютная; рельеф ~0-100 м)
RUNWAY_GAP_S = 30         # ОЦЕНКА: интервал взлёта групп ИИ с полосы одного аэродрома
AIR_START_MIN_M = 500      # ОЦЕНКА: высота появления группы, которая к началу миссии уже в воздухе
AI_LOW_MIN_M = 100         # ОЦЕНКА: точки маршрута групп ИИ не ниже этого (у игрока - как в доктрине, 50 м)
LOW_ENTRY_KM = 20         # ОЦЕНКА: группа подавления ПВО снижается до предельно малой за столько км до зоны ЗРК
EGRESS_KM = 15             # ОЦЕНКА: точка ухода группы подавления ПВО - на столько км от рубежа пуска в сторону базы


def _ai_options(ai: dict) -> list:
    """Опции поведения ИИ из доктрины (поле ai у группы пакета)."""
    out = []
    if ai.get("react_on_threat"):
        out.append(task.OptReactOnThreat(getattr(task.OptReactOnThreat.Values, ai["react_on_threat"])))
    if ai.get("restrict_jettison"):
        out.append(task.OptRestrictJettison(True))
    return out


def _attack(group_id: int, ai: dict, altitude: int | None = None):
    """AttackGroup с параметрами из доктрины: тип оружия, расход, атака всей группой, высота атаки (горка для пуска ПРР)."""
    a = ai.get("attack") or {}
    return task.AttackGroup(group_id, weapon_type=getattr(task.WeaponType, a.get("weapon", "Auto")),
                            group_attack=bool(a.get("group_attack", False)), expend=getattr(task.Expend, a.get("expend", "Auto")),
                            altitude=altitude)


def _engage(group_id: int, ai: dict, altitude: int | None = None):
    """EngageGroup - задача 'по пути' (en-route): действует всё время, пока группа выполняет другие задачи точки
    (здесь - круг ожидания), в отличие от AttackGroup, которая заканчивается, если цель не обнаружена сразу.
    pydcs задаёт только groupId/weaponType; расход, атаку группой и высоту дописываем полями DCS (те же, что у
    AttackGroup; в DCS ещё не проверено)."""
    a = ai.get("attack") or {}
    t = task.EngageGroup(group_id)
    t.params["weaponType"] = getattr(task.WeaponType, a.get("weapon", "Auto")).value
    t.params["expend"] = getattr(task.Expend, a.get("expend", "Auto")).value
    t.params["groupAttack"] = bool(a.get("group_attack", False))
    if altitude is not None:
        t.params["altitudeEnabled"] = True
        t.params["altitude"] = int(altitude)
    return t


def threat_circles(state: dict, ids: list[str]) -> list[tuple[dict, float]]:
    """Известные зоны ЗРК для этого вылета: (центр, радиус км) - угрозы коридора и ЗРК пузыря."""
    return [(model.unit_pos(state, state["units"][sid]), planner.threat_radius_km(state["units"][sid])) for sid in ids]


def in_threat(p: dict, circles: list[tuple[dict, float]]) -> bool:
    return any(model.dist_km(p, c) <= r for c, r in circles)


def search_zone(state: dict, unit: dict, objective_s: int, margin_km: float) -> tuple[dict, float]:
    """Район поиска подвижной цели: от её головы сейчас до расчётного положения к приходу группы (марш со скоростью
    march_kmh от начала миссии, ОЦЕНКА), плюс запас margin_km. Возвращает центр и радиус, км."""
    pts = model.route_points(state, unit)
    length = model.route_length_km(pts)
    h0 = unit["progress_km"]
    h1 = min(length, h0 + unit.get("march_kmh", 0) * objective_s / 3600.0) if unit.get("state") == "march" else h0
    center, _ = model.point_at_km(pts, (h0 + h1) / 2)
    return center, (h1 - h0) / 2 + margin_km


def _path_km(base: dict, route: list[dict]) -> float:
    pts = [base] + route
    return sum(model.dist_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


AI_FLIGHTS = {"own": 3, "enemy": 4}   # ОЦЕНКА: сколько групп ИИ по плану дня в миссии - своих (кроме пакета игрока) и противника
AI_RECON = 1                           # ОЦЕНКА: разведчиков каждой стороны в миссии (маршрут не дальше RECON_KM от цели игрока)
RECON_KM = 150
AI_AIRLIFT = 2                         # ОЦЕНКА: рейсов воздушной перевозки каждой стороны в миссии (ближние к удару игрока)


def air_activity(state: dict, tk: dict, times: dict, sortie: int, m0: float) -> list[dict]:
    """Воздушная война в миссии - по плану полётов на сутки (ato.py) обеих сторон: вылеты, которые в окне миссии
    [m0, m0 + ato.MISSION_LEN_S] в воздухе. Свои (кроме пакета игрока) - не больше AI_FLIGHTS["own"] групп, противника -
    AI_FLIGHTS["enemy"], ближние по времени и месту к удару игрока первыми; дежурства (ДРЛО, заправщик) - все, вне лимита.
    Кто к началу миссии уже в воздухе на пути к объекту - стоит на своём маршруте (в воздухе), кто позже - взлетает по
    расписанию, кто уже возвращается - в миссию не ставится. Летит ударная группа задачи (без групп обеспечения).
    Самолёты эскадрилий не расходуются сверх наличия (с учётом пакета игрока). Время - секунды от начала миссии."""
    from . import ato
    if "strike" not in times:
        return []
    a = ato.ensure(state)
    t0, t1 = m0, m0 + ato.MISSION_LEN_S
    tot = m0 + times["strike"]["objective_s"]
    used: dict[str, int] = {}
    for g in tk["package"]:
        used[g["performer"]] = used.get(g["performer"], 0) + g["size"]
    def rank(e):
        t = e["times"]["strike"]
        near_km = model.dist_km(e["task"]["target_pos"], tk["target_pos"])
        return (not e["ai_only"], abs(t["objective_s"] - tot) / 60 + near_km / 10)
    out = []
    n = {False: 0, True: 0}
    nl = {False: 0, True: 0}
    nr = {False: 0, True: 0}
    for e in sorted((e for e in a["entries"] if e["id"] != tk.get("ato_id") and ato.in_window(e, t0, t1)), key=rank):
        enemy = e["side"] != tk["side"]
        okind = e["task"]["package"][0]["objective"]["kind"]
        lift = e["kind"] == "airlift" or okind == "airlift"
        if okind == "alert":                     # дежурная пара ПВО: в миссии, если база не дальше mission_km от цели
            tdg = model.doctrine(state, e["side"])["tasks"][e["kind"]]
            g = dict(e["task"]["package"][0])
            perf = state["units"][g["performer"]]
            if (model.dist_km(state["airbases"][g["base"]], tk["target_pos"]) > tdg.get("mission_km", 300)
                    or used.get(perf["id"], 0) + g["size"] > perf.get("count", 0)):
                continue
            key = f"{'enemy' if enemy else 'ai'}_qra_{g['base']}"
            if key in times:
                continue
            times[key] = {"start_s": 0, "late_s": 0, "objective_s": 0}
            used[perf["id"]] = used.get(perf["id"], 0) + g["size"]
            g.update({"group": key, "_tdef": tdg, "_side": e["side"], "_enemy": enemy, "_ai": True,
                      "title": f"{'противник' if enemy else 'ИИ'}: {e['title']}", "_ato": e["id"]})
            out.append(g)
            continue
        if not e["ai_only"] and n[enemy] >= AI_FLIGHTS["enemy" if enemy else "own"]:
            continue
        if lift and nl[enemy] >= AI_AIRLIFT:
            continue
        rec = okind == "recon"                   # разведчик: один на сторону, маршрут рядом с районом удара игрока
        if rec and (nr[enemy] >= AI_RECON or min(model.dist_km(p, tk["target_pos"])
                                                   for p in e["task"]["package"][0]["route"]) > RECON_KM):
            continue
        etask = copy.deepcopy(e["task"])
        planner.refresh(state, etask)            # цель группы ИИ - на её место к времени миссии
        g = dict(etask["package"][0])
        perf = state["units"][g["performer"]]
        if g["size"] <= 0 or used.get(perf["id"], 0) + g["size"] > perf.get("count", 0):
            continue
        tdg = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        t = e["times"][g["group"]]
        if e["ai_only"] and not lift and not rec:
            key = f"{'enemy' if enemy else 'ai'}_{e['kind']}_{ato.hhmm(e['tot_s']).replace(':', '')}"
            times[key] = {"start_s": max(0, int(t["objective_s"] - m0)), "late_s": 0,
                          "objective_s": max(0, int(t["objective_s"] - m0)), "until_s": int(t["station_end_s"] - m0)}
        else:
            take, obj = t["takeoff_s"] - m0, t["objective_s"] - m0
            if take < 0 and obj <= 60:
                continue                         # уже над объектом (перевозка - садится) или возвращается - не ставится
            if lift:
                nl[enemy] += 1
                key = f"{'enemy' if enemy else 'ai'}_lift{nl[enemy]}"
            elif rec:
                nr[enemy] += 1
                key = f"{'enemy' if enemy else 'ai'}_recon{nr[enemy]}"
            else:
                n[enemy] += 1
                key = f"{'enemy' if enemy else 'ai'}{n[enemy]}"
            if take < 0:                         # в воздухе на пути к объекту: точка на участке база - первая точка маршрута
                base = state["airbases"][g["base"]]
                first = g["route"][0]
                leg = model.dist_km(base, first)
                done_km = -take * model.group_speed_kmh(state, g, tdg) / 3600
                g["_air_start"] = model.lerp(base, first, min(done_km, max(0.0, leg - 3)) / leg) if leg > 0 else dict(first)
            times[key] = {"start_s": max(0, int(take)), "late_s": 0, "objective_s": int(obj)}
        used[perf["id"]] = used.get(perf["id"], 0) + g["size"]
        g.update({"group": key, "_tdef": tdg, "_side": e["side"], "_enemy": enemy, "_ai": True,
                  "title": f"{'противник' if enemy else 'ИИ'}: {e['title']}", "_ato": e["id"]})
        out.append(g)
    return out


def orbit_group(m: Mission, state: dict, g: dict, perf: dict, ac, mt, side: str, sortie: int, spd_kmh: float,
                t: dict | None = None, airport=None):
    """Смена дежурства (ДРЛО, заправщик) по плану полётов: в воздухе в зоне с начала смены (или с начала миссии, если
    смена уже идёт), "ипподром" до конца смены, затем посадка; задача DCS - AWACS / Tanker. Смена, начинающаяся в
    миссии, появляется в зоне в своё время. Потери - через дебриф, как у всех групп (flights)."""
    alt = int(g.get("alt_m") or 8000)
    pos = _pt(m, g["route"][0])
    fg = m.flight_group_inflight(_country(m, state, side), f"{perf['id']} {g['group']} {sortie}", ac, pos, alt,
                                 speed=int(spd_kmh), maintask=mt, group_size=g["size"])
    _crew(state, fg, perf)
    fg.start_time = int((t or {}).get("start_s", 0))
    for u in fg.units:
        u.skill = Skill.High
    w = fg.points[0]
    role = g["objective"].get("maintask")
    want = {"AWACS": task.AWACSTaskAction, "Refueling": task.Tanker}.get(role)
    if want and not any(isinstance(t, want) for t in w.tasks):   # pydcs обычно ставит её сам по основной задаче
        w.tasks.append(want())
    orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=int(spd_kmh), pattern=task.OrbitAction.OrbitPattern.RaceTrack))
    if t and t.get("until_s") is not None:
        orbit.stop_after_time(int(t["until_s"]))   # конец смены - домой (смену сменяет следующий вылет плана)
    w.tasks.append(orbit)
    fg.add_waypoint(Point(pos.x + 40_000, pos.y, m.terrain), alt, speed=int(spd_kmh))   # второй конец "ипподрома"
    if airport is not None:
        _land(fg, airport, spd_kmh)
    return fg


def timeline(tdef: dict, state: dict, groups: list[dict], fly: str) -> dict[str, dict]:
    """Задержки взлёта групп пакета. Опорная - группа игрока: холодный старт (timing.player_cold_start_min, ОЦЕНКА)
    плюс полёт до объекта. Группа обеспечения выходит на свой объект за lead_min до выхода ударной группы на цель
    (ОЦЕНКИ из доктрины). Группы ИИ взлетают с полосы с задержкой start_s; если не успевают - late_s > 0."""
    fly_s = {g["group"]: _path_km(state["airbases"][g["base"]], g["route"]) * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
             for g in groups}                    # скорость задачи доктрины
    lead = {g["group"]: g.get("lead_min", 0) * 60 for g in groups}
    t_player = tdef["timing"]["player_cold_start_min"] * 60 + fly_s[fly]
    eta_strike = t_player + lead[fly]
    out = {}
    for g in groups:
        k = g["group"]
        start = eta_strike - lead[k] - fly_s[k]
        out[k] = {"start_s": 0 if k == fly else max(0, int(start)), "late_s": 0 if k == fly else max(0, int(-start)),
                  "objective_s": int(eta_strike - lead[k])}
    return out


def build(state: dict, out_path: Path, density: float = 1.0, player: bool = True, fly: str = "strike",
          task_no: int | None = None, humans: int = 1) -> dict:
    if task_no is not None:                      # задача плана дня по номеру (plan печатает список)
        planner.choose(state, task_no)
    tk = state["task"]
    if not tk:
        raise RuntimeError("нет задачи: сначала plan")
    tdef = model.doctrine(state, tk["side"])["tasks"][tk["kind"]]
    pkg = tk["package"]
    if fly not in {g["group"] for g in pkg}:
        raise ValueError(f"в пакете нет группы '{fly}'; есть: {', '.join(g['group'] for g in pkg)}")

    # наземная модель - к началу миссии (sim.advance: бой, марш, итоги вылетов ИИ по часам); цель - на её место
    pre_lines = []
    if tk.get("tot_s") is not None:
        from . import sim
        t_pre = timeline(tdef, state, pkg, fly)
        pre_lines = sim.advance(state, tk["tot_s"] - t_pre["strike"]["objective_s"])
        pre_lines += planner.refresh(state, tk)
        for ln in pre_lines:
            model.note(state, ln)

    m = Mission(Germany())
    set_airbase_coalitions(m, state)
    y, mo, d = map(int, state["date"].split("-"))
    start = datetime.datetime(y, mo, d, state["start_hour"], 0) + datetime.timedelta(days=state["day"] - 1)
    m.start_time = start

    # ---- весь театр: район задачи подробно, остальное - реже ----
    groups = materialize.theatre(state, tk, density)
    vg_by_unit, platoons = {}, {}
    keys = sorted({g["cluster"] for g in groups if g.get("cluster")})        # бои (кластеры) - у каждого своё место
    sites = {k: (state.get("battle_sites") or {}).get(k) for k in keys}
    def shift_of(g):
        s_ = sites.get(g.get("cluster")) if (g["kind"] == "battle" or g.get("battle")) else None
        return (s_["x"], s_["y"]) if s_ else (0.0, 0.0)
    gci_lines: list[str] = []
    tgt_group = next((g for g in groups if g["unit"] == tk["target"]), None)
    bkey = (tgt_group or {}).get("cluster")                                 # бой цели игрока
    airheads: dict[str, dict] = {}
    evac_groups: dict[str, list] = {}            # рота на эвакуацию: группы DCS по вместимости борта
    for g in groups:
        if g["kind"] == "battle":
            platoons[g["unit"]] = _battle_platoons(m, state, g, shift_of(g))
            vg_by_unit[g["unit"]] = platoons[g["unit"]][0][0]
        else:
            if g["kind"] == "airhead":           # рота десанта - в .miz её нет: появляется из севших бортов (assault.lua)
                airheads[g["unit"]] = g
                continue
            if g["kind"] == "evac":              # рота у площадки эвакуации - группами по вместимости борта (CTLD забирает
                from . import assault           # группу целиком; борт ИИ - свою долю, evac.lua)
                cap = assault.troops(state["units"][tk["package"][0]["performer"]]["type"]) // 4 or 1   # фигура - 4 человека
                evac_groups[g["unit"]] = []
                for k in range(0, len(g["vehicles"]), cap):
                    sub = dict(g, name=f"{g['name']} evac {k // cap + 1}", vehicles=g["vehicles"][k:k + cap])
                    evac_groups[g["unit"]].append(_ground_group(m, state, sub))
                vg_by_unit[g["unit"]] = evac_groups[g["unit"]][0]
                continue
            vg_by_unit[g["unit"]] = _ground_group(m, state, g, shift_of(g))
            if g["kind"] == "gci_site":          # КРУ: наведение включено с начала миссии
                vg = vg_by_unit[g["unit"]]
                vg.points[0].tasks.append(ActivateGCI(g["channel"], vg.units[0].id, int(g["radius_km"] * 1000)))
                if g["side"] == tk["side"]:
                    gci_lines.append(f"{state['units'][g['unit']]['name']}: канал {g['channel']}, радиус {g['radius_km']} км")
    missing = [u for g in pkg if g["objective"]["kind"] == "sam" for u in g["objective"]["units"] if u not in vg_by_unit]
    if missing:                                  # урок пузыря BMS: цель группы ИИ обязана быть развёрнута, иначе ей не по чему бить
        raise RuntimeError(f"цели группы подавления ПВО не развёрнуты в миссии: {', '.join(missing)}")

    # ---- тактическая группа: ударная + обеспечения ----
    sortie = state["sortie"] + 1
    times = timeline(tdef, state, pkg, fly)
    support = {s["id"]: s for s in tdef.get("support", [])}
    for _ in range(2):                           # рубеж - от места, где ЗРК будет к приходу группы; время подхода от рубежа зависит слабо
        for g in pkg:
            if g["objective"]["kind"] == "sam" and g.get("support_id") in support:
                base = state["airbases"][g["base"]]
                g["route"] = [planner.hold_point(state, state["units"][g["objective"]["units"][0]], base, support[g["support_id"]],
                                                 times[g["group"]]["objective_s"])]
        times = timeline(tdef, state, pkg, fly)
    # время суток миссии: удар игрока - в своё время по плану полётов (ato); задача без него - start_hour (как раньше)
    m0 = (tk["tot_s"] - times["strike"]["objective_s"]) if tk.get("tot_s") is not None else state["start_hour"] * 3600
    m.start_time = datetime.datetime(y, mo, d) + datetime.timedelta(days=state["day"] - 1, seconds=int(m0))
    sam_ids = list(dict.fromkeys(tk["threats"] + [g["unit"] for g in groups if g["unit"] in state["units"] and model.category(state["units"][g["unit"]]) == "sam"]))
    circles = threat_circles(state, sam_ids)
    runway_slots: set = set()
    spd = tdef["speed_kmh"]
    flights, lines, enemy_lines, ai_lines = [], [], [], []
    _CREW["names"], _CREW["pilots"] = set(), {}
    # люди в вылете: сначала группа игрока (fly), затем остальные группы тактической группы по порядку
    hum_left = max(1, int(humans or 1)) if player else 0
    hum_of: dict[str, int] = {}
    for g in sorted(pkg, key=lambda g: g["group"] != fly):
        k = min(hum_left, int(g["size"]))
        if k > 0:
            hum_of[g["group"]] = k
            hum_left -= k
    multi = sum(hum_of.values()) > 1             # несколько людей - мультиплеер: места Client
    assault_specs = []
    evac_specs: list[dict] = []                  # эвакуация десанта (evac.lua)
    qra_specs: list[dict] = []                   # дежурные пары ПВО (qra.lua)
    rescuers: list[dict] = []                    # вертолёты ИИ за экипажами (csar.lua пересчитает посадку)
    ctld = {"pilots": [], "actions": {}, "limits": {}, "cargo": {}, "logistic": [], "pickup": [], "groups": [],
            "crates": [], "lifts": [], "jtacs": [], "extract": []}   # CTLD (ctld_cfg.lua): борта игрока, зоны, ящики, авианаводчики
    ctld_assault: list[tuple[dict, str]] = []     # (высадка, борт игрока) - группа десанта CTLD по его доле роты
    ctld_lines: list[str] = []
    enemy = air_activity(state, tk, times, sortie, m0)
    for g in pkg + enemy:
        tdg = g.get("_tdef") or tdef             # группы противника - по его пакету доктрины
        side_g = g.get("_side", tk["side"])
        spd = model.group_speed_kmh(state, g, tdg)   # скорость задачи доктрины
        transit = g.get("transit_alt_m_agl") or tdg["transit_alt_m_agl"]   # средние высоты, если угроз в коридоре нет (planner)
        perf = state["units"][g["performer"]]
        base = state["airbases"][g["base"]]
        airport = m.terrain.airports[base["airport"]]
        ac = dcstypes.flying(perf["type"])
        hum = 0 if g.get("_ai") or g.get("_enemy") else hum_of.get(g["group"], 0)
        is_player = player and hum > 0
        helo = model.category(perf) == "heli"    # вертолёты: предельно малая высота и для ИИ
        mt = _maintask(ac, g["maintask"])
        if g["objective"]["kind"] == "alert":    # дежурная пара ПВО: на стоянке, взлёт по обнаружению (qra.lua)
            try:                                 # стоянка занята или для реактивных её нет - старт с полосы по тревоге
                fg = m.flight_group_from_airport(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                                 airport, maintask=mt, start_type=StartType.Warm, group_size=g["size"])
            except NoParkingSlotError:
                fg = m.flight_group_from_airport(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                                 airport, maintask=mt, start_type=StartType.Runway, group_size=g["size"])
            _crew(state, fg, perf)
            fg.late_activation = True
            _apply_loadout(fg, ac, perf["type"], g["loadout"])
            for u in fg.units:
                u.skill = Skill.High
            alt = int(g.get("alt_m") or tdg.get("cap_alt_m", 6000))
            w = fg.add_waypoint(_pt(m, g["route"][0]), alt, speed=int(spd), name="Зона дежурства")
            w.tasks.append(task.EngageTargets(max_distance=int(tdg.get("engage_km", 80) * 1000), targets=[task.Targets.All.Air]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=int(spd), pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_duration(int(tdg.get("cap_min", 40) * 60))
            w.tasks.append(orbit)
            _land(fg, airport, spd)
            ap = airport.position
            qra_specs.append({"id": g["_ato"], "group": fg.name, "side": 1 if side_g == "red" else 2,
                              "x": ap.x, "y": ap.y, "r": tdg.get("scramble_km", 150) * 1000, "title": g["title"]})
            (enemy_lines if g.get("_enemy") else ai_lines).append(
                f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, в готовности на стоянке")
            flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fg.units], "player": False,
                            "ato": g["_ato"], **({"side": side_g} if g.get("_enemy") else {})})
            continue
        if g["objective"]["kind"] == "orbit":    # дежурство: к началу миссии уже в зоне (в воздухе), до конца миссии
            t_ = times[g["group"]]
            orbit_group(m, state, g, perf, ac, mt, side_g, sortie, spd, t_, airport)
            line = (f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, в зоне "
                    + (f"с ~{t_['start_s'] // 60} мин миссии" if t_["start_s"] else "с начала миссии")
                    + f" до ~{t_['until_s'] // 60} мин")
            (enemy_lines if g.get("_enemy") else ai_lines).append(line)
            fl = m.find_group(f"{perf['id']} {g['group']} {sortie}")
            flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fl.units], "player": False,
                            **({"side": side_g} if g.get("_enemy") else {})})
            continue
        if g.get("_air_start"):                  # по плану полётов к началу миссии уже в воздухе, на пути к объекту
            fg = m.flight_group_inflight(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                         _pt(m, g["_air_start"]), max(int(transit), AIR_START_MIN_M), speed=int(spd),
                                         maintask=mt, group_size=g["size"])
        else:
            try:
                fg = m.flight_group_from_airport(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac, airport,
                                                 maintask=mt, start_type=StartType.Cold if is_player else StartType.Runway,
                                                 group_size=g["size"])
            except NoParkingSlotError:           # вертолётная площадка: стоянок мало - с площадки (взлёт с полосы)
                fg = m.flight_group_from_airport(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac, airport,
                                                 maintask=mt, start_type=StartType.Runway, group_size=g["size"])
        _crew(state, fg, perf)
        st_s = times[g["group"]]["start_s"]
        if not is_player and not g.get("_air_start"):   # группы ИИ с полосы одного аэродрома - не в одну секунду (столкновение при появлении)
            while (base["airport"], st_s) in runway_slots:
                st_s += RUNWAY_GAP_S
            runway_slots.add((base["airport"], st_s))
            times[g["group"]]["start_s"] = st_s
        fg.start_time = st_s
        cat = _apply_loadout(fg, ac, perf["type"], g["loadout"])
        needs_mod = False
        for u in fg.units[:hum] if is_player else []:
            needs_mod = _set_player(u, client=multi) or needs_mod
        for u in (fg.units[hum:] if is_player else fg.units):
            u.skill = Skill.High
        def wp(p, alt, name, keep_alt=False):
            if not keep_alt and side_g == tk["side"] and in_threat(p, circles):   # в известной зоне ЗРК - на предельно малой высоте
                alt = min(alt, tdg.get("low_alt_m_agl", alt))
            if not is_player and not helo and alt < AI_LOW_MIN_M:  # ИИ ниже этого бьётся о землю (Су-24М: 3 случая на 40-80 м)
                alt = AI_LOW_MIN_M
            w = fg.add_waypoint(_pt(m, p), alt, speed=spd, name=name)
            w.alt_type = "RADIO"
            return w
        if not is_player:                        # ИИ - только своя задача: без "поражать цели по пути" от основной задачи DCS
            # (pydcs вешает EngageTargets по maintask: SEAD - любые ПВО, CAS - любые наземные; camp8: Су-24М и Су-25
            # бросали задачу и шли на Patriot). Свои атаки - задачами точек маршрута (AttackGroup/EngageGroup/зона).
            fg.points[0].tasks = [t for t in fg.points[0].tasks if getattr(t, "id", None) != "EngageTargets"]
        if g.get("roe") == "return_fire":
            fg.points[0].tasks.append(task.OptROE(task.OptROE.Values.ReturnFire))
        ai = g.get("ai") or {}
        for opt in _ai_options(ai):              # поведение ИИ из доктрины (группа подавления ПВО: не бросать атаку)
            fg.points[0].tasks.append(opt)
        obj = g["objective"]
        land = airport
        if obj["kind"] == "airlift":             # воздушная перевозка: перелёт и посадка на аэродроме назначения
            dest = state["airbases"][obj["airbase"]]
            start_p = g.get("_air_start") or base
            alt = int(g.get("alt_m") or transit)
            wp(model.lerp(start_p, obj["pos"], 0.5), alt, "Маршрут", keep_alt=True)
            land = m.terrain.airports[dest["airport"]]
            g["_dest"] = dest["name"]
            if is_player and helo:               # игрок: груз - ящики CTLD у машины тыла, сдать - на аэродроме назначения
                sd = 1 if side_g == "red" else 2
                u0 = fg.units[0]
                lg = m.vehicle_group(_country(m, state, side_g), f"Тыл {sortie}", dcstypes.vehicle(CTLD_LOGISTIC[side_g]),
                                     _away(m, u0.position, airport.position, CTLD_LOGISTIC_M), heading=0)
                ctld["logistic"].append(lg.units[0].name)
                zone = f"Выгрузка {sortie}" + ("" if g["group"] == fly else f" {g['group']}")
                m.triggers.add_triggerzone(land.position, radius=CTLD_DROP_M, hidden=False, name=zone)
                cap = float(model.aircraft_info(perf["type"]).get("cargo_t") or 1.0)
                kg = 1000 if cap >= 2 else 500
                wt = kg + (0.11 if sd == 1 else 0.21)           # вес ящика CTLD - уникальный (по нему тип груза)
                ctld["crates"].append({"weight": wt, "desc": f"Supply {kg} kg", "unit": CTLD_CRATE_UNIT[side_g], "side": sd})
                ctld["pilots"] += [u.name for u in fg.units[:hum]]
                ctld["actions"][u0.unit_type.id] = {"crates": True, "troops": False}
                ctld["cargo"][u0.unit_type.id] = max(1, int(cap * 1000 // kg))
                d_obj = state["units"].get(obj.get("depot"), {})
                ctld["lifts"].append({"id": tk.get("ato_id") or f"task-{sortie}", "side": sd, "zone": zone,
                                      "title": f"{d_obj.get('name', '')} ({dest['name']})"})
                ctld_lines.append(f"Груз: ящики \"Supply {kg} kg\" (до {ctld['cargo'][u0.unit_type.id]} на борт) - у машины "
                                  f"тыла рядом со стоянкой: F10 -> CTLD -> Crates -> Supply; взять - висением над ящиком "
                                  f"или с земли (CTLD Commands -> Load Nearby Crate(s)). Сдать - на аэродроме {dest['name']} "
                                  f"(зона {CTLD_DROP_M / 1000:.1f} км): Drop Crate(s) или Unpack Any Crate. "
                                  f"На склад идёт то, что лежит в зоне к концу миссии.")
        elif obj["kind"] == "recon":             # разведка: по точкам маршрута и домой (итог - модель, recon.py)
            alt = int(g.get("alt_m") or transit)
            for i, p in enumerate(g["route"], 1):
                if alt >= 3000:
                    w = fg.add_waypoint(_pt(m, p), alt, speed=spd, name=f"Разведка {i}")
                    w.alt_type = "BARO"
                else:
                    wp(p, alt, f"Разведка {i}")
        elif obj["kind"] == "csar":              # поиск и спасение: на малой высоте к экипажу, посадка рядом, домой
            dp = obj["pos"]
            low = int(tdg.get("low_alt_m_agl", 50))
            start_p = g.get("_air_start") or base
            d = model.dist_km(start_p, dp)
            if d > 8:
                wp(model.lerp(dp, start_p, 5 / d), low, "Подход")
            w = wp(dp, low, "Экипаж")
            c = _pt(m, dp)
            w.tasks.append(task.Land(Vector2(c.x + 60, c.y), duration=int(tdg.get("land_s", 90))))   # рядом, не на нём
            if d > 8:
                wp(model.lerp(dp, base, 5 / model.dist_km(base, dp)), low, "Отход")
            if not is_player:                    # ИИ: посадку у пилота пересчитает csar.lua (пилот - на открытом месте)
                rescuers.append({"group": fg.name, "downed": obj["downed"], "home": airport.id,
                                 "land": tdg.get("land_s", 90)})
        elif obj["kind"] == "air_evac":          # эвакуация: на малой высоте к площадке у роты, посадка на land_s, домой
            lz = obj["pos"]
            low = int(tdg.get("low_alt_m_agl", 50))
            start_p = g.get("_air_start") or base
            d = model.dist_km(start_p, lz)
            if d > 8:
                wp(model.lerp(lz, start_p, 5 / d), low, "Подход")
            w = wp(lz, low, "Площадка")
            c = _pt(m, lz)
            w.tasks.append(task.Land(Vector2(c.x, c.y), duration=int(tdg.get("land_s", 300))))
            if d > 8:
                wp(model.lerp(lz, base, 5 / model.dist_km(base, lz)), low, "Отход")
            eg = evac_groups.get(obj["unit"])
            if eg:                               # рота в миссии - только у своей задачи
                sid = tk.get("ato_id") or f"task-{sortie}"
                spec = next((a for a in evac_specs if a["id"] == sid), None)
                if spec is None:
                    spec = {"id": sid, "title": state["units"][obj["unit"]]["name"], "x": c.x, "y": c.y,
                            "r": tdg.get("lz_radius_m", 800), "land": tdg.get("land_s", 300), "home": airport.id,
                            "side": 1 if side_g == "red" else 2, "country": _country(m, state, side_g).id,
                            "helos": [], "groups": [],
                            "troops": [{"group": vg.name, "units": [(u.name, u.type) for u in vg.units]} for vg in eg]}
                    evac_specs.append(spec)
                spec["helos"] += [u.name for u in fg.units]
                if not is_player:
                    spec["groups"].append(fg.name)
                else:                            # игрок: забрать группу - меню CTLD (Unload / Extract Troops)
                    from . import assault
                    u0 = fg.units[0]
                    ctld["pilots"] += [u.name for u in fg.units[:hum]]
                    ctld["actions"][u0.unit_type.id] = {"crates": False, "troops": True}
                    ctld["limits"][u0.unit_type.id] = max(1, assault.troops(perf["type"]) // 4)   # фигур (по 4 человека)
                    ctld["extract"] += [vg.name for vg in eg]
                    ctld_lines.append(f"Эвакуация: сядьте у роты (площадка, {spec['r']} м) - F10 -> CTLD -> Troop Transport -> "
                                      f"Unload / Extract Troops забирает ближнюю группу (до 125 м от вертолёта, по вместимости). "
                                      f"Вывезено - кто на борту, когда вертолёт цел; сбит - группа на борту погибла.")
            g["_lz"] = obj["place"]
        elif obj["kind"] == "air_assault":       # десант: на малой высоте к площадке, посадка на land_s, домой
            lz = obj["pos"]
            low = int(tdg.get("low_alt_m_agl", 50))
            start_p = g.get("_air_start") or base
            d = model.dist_km(start_p, lz)
            if d > 8:
                wp(model.lerp(lz, start_p, 5 / d), low, "Подход")
            w = wp(lz, low, "Площадка")
            c = _pt(m, lz)
            w.tasks.append(task.Land(Vector2(c.x, c.y), duration=int(tdg.get("land_s", 120))))
            if d > 8:
                wp(model.lerp(lz, base, 5 / model.dist_km(base, lz)), low, "Отход")
            ah = airheads.get(obj["unit"])
            if ah is not None:                   # рота в миссии - только у своей задачи (окно)
                sid = tk.get("ato_id") or f"task-{sortie}"
                spec = next((a for a in assault_specs if a["id"] == sid), None)
                if spec is None:                 # волны десанта (группы по 4 борта) - одна высадка
                    spec = {"id": sid, "title": state["units"][obj["unit"]]["name"], "x": c.x, "y": c.y,
                            "r": tdg.get("lz_radius_m", 800), "land": tdg.get("land_s", 120), "home": airport.id,
                            "side": 1 if side_g == "red" else 2, "country": _country(m, state, side_g).id,
                            "helos": [], "groups": [],
                            "troops": [(v["name"], dcstypes.vehicle(v["type"]).id) for v in ah["vehicles"]]}
                    assault_specs.append(spec)
                spec["helos"] += [u.name for u in fg.units]
                if not is_player:
                    spec["groups"].append(fg.name)
                else:                            # игрок: погрузка и высадка через меню CTLD, зона погрузки - у стоянки
                    u0 = fg.units[0]
                    for u in fg.units[:hum]:
                        ctld_assault.append((spec, u.name))
                        ctld["pilots"].append(u.name)
                    ctld["actions"][u0.unit_type.id] = {"crates": False, "troops": True}
                    ctld["limits"][u0.unit_type.id] = int(model.aircraft_info(perf["type"]).get("troops") or 10)
                    zone = f"Погрузка {sortie}" + ("" if g["group"] == fly else f" {g['group']}")
                    m.triggers.add_triggerzone(u0.position, radius=CTLD_PICKUP_M, hidden=False, name=zone)
                    ctld["pickup"].append({"zone": zone, "side": spec["side"], "limit": 1})
                    ctld_lines.append(f"Десант: погрузка у стоянки (зона {CTLD_PICKUP_M} м) - F10 -> CTLD -> Troop Transport -> "
                                      f"Load Assault...; высадка на площадке (ближе {spec['r']} м) - Unload / Extract Troops "
                                      f"(на земле или висением по тросу). Высадили не там - заберите (тот же пункт) и высадите снова.")
            g["_lz"] = obj["place"]
        elif obj["kind"] in ("column", "site"):    # ударная группа: колонна, часть в бою, позиция ЗРК
            ip, tgt = g["route"]
            wp(ip, transit, "ИПМ")
            w = wp(tgt, tdg["attack_alt_m_agl"], "Цель")
            if obj["unit"] in platoons:          # часть в бою - взводами: удар по району её боевого порядка
                bg = next(x for x in groups if x["unit"] == obj["unit"])
                c, sh = _pt(m, bg["center"]), shift_of(bg)
                w.tasks.append(task.EngageTargetsInZone(Vector2(c.x + sh[0], c.y + sh[1]), BATTLE_ZONE_M, [task.Targets.All.GroundUnits]))
            elif obj["unit"] in vg_by_unit:
                w.tasks.append(_attack(vg_by_unit[obj["unit"]].id, ai))
            else:                                # цель противника вне окна миссии - удар по району её положения
                c = _pt(m, obj["pos"])
                w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), BATTLE_ZONE_M, [task.Targets.All.GroundUnits]))
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
        elif obj["kind"] == "sam":               # группа подавления ПВО: рубеж пуска по каждому ЗРК, ближний первым
            low = tdg.get("low_alt_m_agl", transit)
            sup = support.get(g.get("support_id"), {})
            hold_until = times["strike"]["objective_s"] + int(sup.get("hold_after_min", 0) * 60)
            if not sup.get("standoff_km"):       # доктрина без рубежа - атака с прохода по каждому ЗРК (как в 0.2)
                for sid, p in zip(obj["units"], g["route"]):
                    w = wp(p, low, "Рубеж пуска")
                    w.tasks.append(_attack(vg_by_unit[sid].id, ai, g.get("launch_alt_m")))
            elif g["route"]:
                sam = state["units"][obj["units"][0]]                 # рубеж и ожидание - по ближнему ЗРК
                # от аэродрома - на высоте перелёта; снижение до предельно малой - за LOW_ENTRY_KM до зоны ЗРК
                # (camp4/camp7: ведомый Су-24М на 50 м сразу после взлёта дважды разбился в развороте у аэродрома)
                sam_pos = model.unit_pos(state, sam)
                entry_km = planner.threat_radius_km(sam) + LOW_ENTRY_KM
                total = model.dist_km(base, sam_pos)
                if total > entry_km + 5:
                    wp(model.lerp(sam_pos, base, entry_km / total), transit, "Снижение", keep_alt=True)
                w = wp(g["route"][0], low, "Рубеж пуска")             # подход к рубежу на предельно малой высоте
                for sid in obj["units"]:                              # атака - по всем ЗРК коридора, пока идёт ожидание
                    w.tasks.append(_engage(vg_by_unit[sid].id, ai, g.get("launch_alt_m")))
                # ожидание: на высоте пуска, если рубеж вне зоны поражения любого из ЗРК, иначе на малой (ОЦЕНКА)
                inside = any(model.dist_km(g["route"][0], model.unit_pos(state, state["units"][sid]))
                             - sup.get("orbit_radius_km", 0) <= planner.threat_radius_km(state["units"][sid]) for sid in obj["units"])
                alt = max(low, AI_LOW_MIN_M) if inside else int(g.get("launch_alt_m") or low)
                hold = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
                hold.stop_after_time(hold_until)
                w.tasks.append(hold)
                g["hold"] = {"alt_m": alt, "until_s": hold_until, "launch_km": round(planner.launch_distance_km(sam, sup), 1)}
            if g["route"]:                       # после пуска - уход к базе, без пролёта над ЗРК
                last = g["route"][-1]
                d = model.dist_km(base, last)
                wp(model.lerp(last, base, min(1.0, EGRESS_KM / d)) if d else base, low, "Уход")
        elif obj["kind"] == "search_zone":       # доразведка, поиск и поражение: район, где колонна будет к приходу группы
            center, radius_km = search_zone(state, state["units"][obj["unit"]], times[g["group"]]["objective_s"],
                                            g.get("zone_margin_km") or 0)
            ip = planner.ip_point(base, center, tdg["ip_offset_km"])
            wp(ip, transit, "ИПМ")
            w = wp(center, transit, "Район поиска")
            c = _pt(m, center)
            w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), int(radius_km * 1000), [task.Targets.All.GroundUnits]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=int(g.get("search_alt_m") or SEARCH_ORBIT_ALT_M), speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_duration(int((g.get("search_min") or 10) * 60))
            w.tasks.append(orbit)
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
            g["zone"] = {"center": center, "radius_km": round(radius_km, 1)}
        elif obj["kind"] == "point":             # объект тыла: мост - по объекту карты, склад и аэродром - бомбами по точке
            ip, tgt = g["route"]
            wp(ip, transit, "ИПМ")
            w = wp(tgt, tdg["attack_alt_m_agl"], "Цель")
            c = _pt(m, tgt)
            a_ = (g.get("ai") or {}).get("attack") or {}
            if obj.get("object") == "bridge":
                w.tasks.append(task.AttackMapObject(Vector2(c.x, c.y), group_attack=True))
            else:
                w.tasks.append(task.Bombing(Vector2(c.x, c.y), weapon_type=getattr(task.WeaponType, a_.get("weapon", "Auto")),
                                            expend=getattr(task.Expend, a_.get("expend", "Auto")), group_attack=True,
                                            altitude=int(tdg.get("bomb_alt_m", 1000))))
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
        elif obj["kind"] in ("cap_zone", "cover_zone"):   # прикрытие: зона над войсками / над районом удара
            alt = int(g.get("alt_m") or 3000)
            w = wp(obj["pos"], alt, "Зона прикрытия", keep_alt=True)
            w.alt_type = "BARO"
            c = _pt(m, obj["pos"])
            w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), int((g.get("zone_km") or 40) * 1000), [task.Targets.All.Air]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            until = (times[g["group"]]["objective_s"] + int((g.get("cap_min") or 20) * 60)) if obj["kind"] == "cap_zone" \
                else (times["strike"]["objective_s"] + int((g.get("hold_after_min") or 5) * 60))
            orbit.stop_after_time(until)
            w.tasks.append(orbit)
            g["until_s"] = until
        else:                                    # проход над целью без атаки
            ip, tgt = g["route"]
            wp(ip, transit, "ИПМ")
            wp(tgt, transit, "Цель")
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
        _land(fg, land, spd)
        t = times[g["group"]]
        when = (f"посадка в {g['_dest']} ~{t['objective_s'] // 60} мин" if g.get("_dest")
                else f"в районе ~{t['objective_s'] // 60} мин")
        if g.get("_enemy"):                      # авиация противника - в разведсводку, не в состав группы
            enemy_lines.append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, {when}")
            flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fg.units], "player": False,
                            "side": side_g, **({"ato": g["_ato"]} if g.get("_ato") else {})})
            continue
        (ai_lines if g.get("_ai") else lines).append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, "
                     + (("игрок, холодный старт" + (" (в базовом DCS тип только для ИИ - нужен мод)" if needs_mod else ""))
                        if is_player else f"ИИ, взлёт с полосы через {t['start_s'] // 60} мин")
                     + (f", {when}" if g.get("_dest") else f", на объекте через ~{t['objective_s'] // 60} мин")
                     + (f", переход на {transit} м (угроз ЗРК в коридоре нет)" if g.get("transit_alt_m_agl") else "")
                     + (f", ОПАЗДЫВАЕТ на {t['late_s'] // 60} мин" if t["late_s"] else "")
                     + (f", ожидание на рубеже пуска ({g['hold']['launch_km']:.0f} км от ЗРК) на {g['hold']['alt_m']} м до ~{g['hold']['until_s'] // 60} мин"
                        if g.get("hold") else "")
                     + f"; задача DCS {mt.name}, подвеска {cat or 'DCS по умолчанию'}")
        flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fg.units], "player": is_player,
                        "humans": [u.name for u in fg.units[:hum]] if is_player else [],
                        **({"ato": g["_ato"]} if g.get("_ato") else {})})

    # ---- хук дебрифа ----
    state["sortie"] = sortie
    track = [v["name"] for g in groups if g["kind"] in ("column", "battle") for v in g["vehicles"]]
    trig = TriggerStart(comment="redfront debrief hook")
    specs = [s for s in (column_spec(m, state, g, vg_by_unit[g["unit"]]) for g in groups if g["kind"] == "column") if s]
    if specs:                                    # сначала переложить колонну на дорогу, потом - хук (в одном триггере, по порядку)
        trig.add_action(DoScript(String(column_script(state["campaign_id"], state["sortie"], specs))))
    ads = []                                     # ПВО на позициях - на открытое место (battle_site.lua)
    for g in groups:
        if g["kind"] not in ("sam_site", "gci_site"):   # КРУ - тоже: позиция генератора бывает в воде (Дамгартен)
            continue
        vg = vg_by_unit[g["unit"]]
        ads.append({"name": vg.name, "groupId": vg.id, "country": _country(m, state, g["side"]).id,
                    "follow": g.get("cluster") if g.get("battle") else None,
                    "gci": ({"channel": g["channel"], "radius": int(g["radius_km"] * 1000)} if g["kind"] == "gci_site" else None),
                    "units": [{"name": u.name, "type": u.type, "x": u.position.x, "y": u.position.y, "unitId": u.id,
                               "heading": math.radians(u.heading)} for u in vg.units]})
    if platoons or ads:                          # расстановка боёв и ПВО по местности (до front.lua)
        center = tk.get("target_pos")             # дальние бои (театр всей карты) - без поиска места: дорого при старте миссии
        near = {g.get("cluster") for g in groups if g.get("cluster") and g["vehicles"] and (
            not center or model.dist_km(g["vehicles"][0], center) <= materialize.DETAIL_KM)}
        bats = {k: {"key": k, "search_r": 0 if (sites[k] or k not in near) else (SITE_SEARCH_M if "+" in k else POSITION_SEARCH_M),
                    "shift": (sites[k]["x"], sites[k]["y"]) if sites[k] else (0.0, 0.0), "platoons": []} for k in keys}
        for g in groups:
            for vg, part in platoons.get(g["unit"], []):
                bats[g["cluster"]]["platoons"].append({
                    "name": vg.name, "groupId": vg.id, "country": _country(m, state, g["side"]).id,
                    "speed": (g["speed_kmh"] or 0) / 3.6,
                    "units": [{"name": u.name, "type": u.type, "x": u.position.x, "y": u.position.y,
                               "heading": math.radians(u.heading)} for u in vg.units],
                    "route": [(p.position.x, p.position.y) for p in vg.points[1:]],
                    "options": [(0, 4)] + list(ground_options(state, g))})
        trig.add_action(DoScript(String(site_script(state["campaign_id"], state["sortie"],
                                                    [b for b in bats.values() if b["platoons"]], ads))))
    front = []
    for g in groups:
        if g["kind"] != "battle":
            continue
        enemies = [vg.name for f in g.get("engaged", []) for vg, _ in platoons.get(f, [])]
        for vg, part in platoons[g["unit"]]:
            rng = dcstypes.threat_range_km(sorted({v["type"] for v in part})) * 1000 or 2000.0   # ОЦЕНКА без данных pydcs: 2 км
            rng = min(rng, FIRE_RANGE_MAX_M)     # ПТУР (Т-80УД - 5 км в pydcs) - не дальше дистанции танкового огня
            front.append({"name": vg.name, "formation": g["unit"], "attack": g.get("attack", False), "range": rng, "enemies": enemies})
    if front:                                    # бой наземных частей (front.lua)
        trig.add_action(DoScript(String(front_script(state["campaign_id"], state["sortie"], front))))
    objs = [u for u in state["units"].values() if u.get("role") in TARGET_SCAN and u["state"] == "active"]
    if objs:                                     # объекты тыла - объекты карты в их районе (targets.lua)
        trig.add_action(DoScript(String(targets_script(m, state, objs))))
    # поиск и спасение (csar.lua) - в каждой миссии: катапультироваться может любой; звук маяка - ресурс миссии
    downed = [d for d in state.get("downed", []) if d["id"] in vg_by_unit]
    beacon = csar.beacon_wav(Path(tempfile.gettempdir()) / BEACON_FILE)
    m.map_resource.add_resource_file(beacon)
    trig.add_action(DoScript(String(airbase_script(m, state))))   # стороны аэродромов - первыми
    trig.add_action(DoScript(String(lz_script(state["campaign_id"], state["sortie"]))))   # площадки - до csar и десанта
    for spec, name in ctld_assault:              # группа десанта CTLD - доля роты на борту игрока (assault.lua делит по кругу)
        idx = spec["helos"].index(name)
        share = [t[1] for i, t in enumerate(spec["troops"]) if i % len(spec["helos"]) == idx]
        ctld["groups"].append({"name": f"Assault: {spec['title']}", **(troop_mix(share) or {"inf": 1}), "side": spec["side"]})
    if player and tdef.get("jtac") and bkey and tk["target"] in platoons:   # авианаводчик у своего взвода в бою цели
        tvg = platoons[tk["target"]][0][0]
        own = [vg for g in groups if g["kind"] == "battle" and g.get("cluster") == bkey and g["side"] == tk["side"]
               for vg, _part in platoons.get(g["unit"], [])]
        if own:
            tp = tvg.units[0].position
            vg = min(own, key=lambda v: v.units[0].position.distance_to_point(tp))
            sd = 1 if tk["side"] == "red" else 2
            code = int((tdef.get("jtac") or {}).get("code", JTAC_CODE)) if isinstance(tdef.get("jtac"), dict) else JTAC_CODE
            ctld["jtacs"].append({"id": f"JTAC {sortie}", "platoon": vg.name, "target": tvg.name, "side": sd,
                                  "country": _country(m, state, tk["side"]).id, "type": JTAC_TYPES[tk["side"]], "code": code,
                                  "tx": tp.x, "ty": tp.y, "title": vg.name})
            ctld_lines.append(f"Авианаводчик (позывной \"JTAC {sortie}\") - у нашего взвода в бою: подсвечивает цели "
                              f"лазером (код {code}) и дымом; F10 -> JTAC Status - цель, координаты.")
    if ctld["pilots"] or ctld["jtacs"]:          # CTLD - только если он нужен вылету
        for a_ in ctld_actions(m, state, ctld):
            trig.add_action(a_)
    trig.add_action(DoScript(String(csar_script(m, state, downed, rescuers))))
    if qra_specs:                                # дежурные пары ПВО: взлёт по обнаружению противника радарами стороны
        trig.add_action(DoScript(String(qra_script(state["campaign_id"], state["sortie"], qra_specs))))
    if evac_specs:                               # эвакуация: рота садится в борта на площадке (evac.lua; игрок - CTLD)
        trig.add_action(DoScript(String(evac_script(state["campaign_id"], state["sortie"], evac_specs))))
    if assault_specs:                            # десант: рота выходит при посадке бортов на площадку (assault.lua)
        trig.add_action(DoScript(String(assault_script(state["campaign_id"], state["sortie"], assault_specs))))
    trig.add_action(DoScript(String(lua_hook(state["campaign_id"], state["sortie"], track))))  # String(...), не m.string(...): иначе DCS исполняет ключ перевода
    m.triggerrules.triggers.append(trig)

    m.set_description_text(
        f"{tk['title']}\n\nДень {state['day']}" + (", НОЧНОЙ ВЫЛЕТ" if _ato_night(state, m0) else "")
        + ". Тактическая группа:\n" + "\n".join(f"- {ln}" for ln in lines)
        + f"\n\nУдаление цели: {tk['distance_km']:.0f} км. Угрозы на маршруте: "
        + (", ".join(state['units'][t]['name'] for t in tk['threats']) or "не выявлены")
        + (f"\nЗамечания планировщика: {tk['package_notes']}" if tk.get("package_notes") else "")
        + (("\n\nДругие вылеты наших сил в это время:\n" + "\n".join(f"- {ln}" for ln in ai_lines)) if ai_lines else "")
        + ("\nРазведка: в районе возможна активность авиации противника." if enemy_lines else "")
        + (("\n\nНаведение (КРУ, только МиГ-29):\n" + "\n".join(f"- {ln}" for ln in gci_lines)) if gci_lines else "")
        + (("\n\nПеревозки и наведение (CTLD):\n" + "\n".join(f"- {ln}" for ln in ctld_lines)) if ctld_lines else ""))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))

    manifest = {
        "sortie": state["sortie"],
        "file": str(out_path),
        "ato_id": tk.get("ato_id"),                      # вылет плана полётов, который летит игрок
        "start_s": int(m0),                              # начало миссии, с от полуночи суток кампании
        "end_s": int(m0) + ATO_LEN_S,                    # окно миссии (после дебрифа - часы кампании)
        "flights": flights,
        "package_lines": lines,
        "enemy_lines": enemy_lines,                      # авиация противника в миссии (в брифинг не выводится)
        "ai_lines": ai_lines,                            # свои группы ИИ по плану дня (в брифинге)
        "gci_lines": gci_lines,                          # КРУ своей стороны: канал, радиус (в брифинге)
        "column_road": [s["name"] for s in specs],      # колонны, которые миссия переложит на дорогу при старте
        "front": [p["name"] for p in front],             # взводы частей в бою под управлением front.lua
        "battle_key": bkey,                              # бой цели игрока
        "battle_keys": keys,
        "objects": [o["id"] for o in objs],              # объекты тыла, по которым миссия считает разрушения
        "ground_s": state.get("ground_s"),               # наземная модель - на это время суток (sim.advance)
        "pre_lines": pre_lines,                          # что изменилось к началу миссии (бой, марш, вылеты ИИ)
        "ground": [{"unit": g["unit"], "kind": g["kind"], "cluster": g.get("cluster"), "vehicles": [{"name": v["name"], "type": v["type"], "weight": v["weight"]} for v in g["vehicles"]]}
                   for g in groups if g["kind"] not in ("downed", "convoy")],   # экипажи, колонны снабжения - не части модели
        "convoys": [{"unit": g["unit"], "side": g["side"], "link": g["link"],      # колонны снабжения: потери - недовоз (convoys.py)
                     "vehicles": [{"name": v["name"], "weight": v["weight"]} for v in g["vehicles"]]}
                    for g in groups if g["kind"] == "convoy"],
        "downed": [d["id"] for d in downed],             # экипажи на земле в миссии (их может спасти вертолёт)
        "ctld": {"pilots": ctld["pilots"], "lifts": [x["id"] for x in ctld["lifts"]],   # CTLD в миссии (ctld_cfg.lua)
                 "jtacs": [x["id"] for x in ctld["jtacs"]], "extract": ctld["extract"]},
        "evac": [x["id"] for x in evac_specs],            # эвакуация десанта в миссии (evac.lua)
        "ctld_lines": ctld_lines,
    }
    state["manifest"] = manifest
    return manifest

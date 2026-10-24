"""Сборка .miz через pydcs: звено игрока, развёрнутое окно наземной модели, хук дебрифа.

Манифест (что развёрнуто, с какими весами) сохраняется в состоянии кампании: по нему дебриф возвращает потери в модель.
"""
from __future__ import annotations

import copy
import datetime
import json
import math
import re
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

from . import csar, dcstypes, i18n, intel, materialize, model, planner
from . import ato
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
PUSH_LUA = Path(__file__).parent / "lua" / "push.lua"
CAP_LUA = Path(__file__).parent / "lua" / "cap.lua"
IADS_LUA = Path(__file__).parent / "lua" / "iads.lua"
IADS_NET_KM = 150        # ОЦЕНКА: ЗРК на связи, если живой узел сети (РЛС, КРУ) не дальше
IADS_NET_MIN_KM = 15     # ЗРК с зоной поражения не меньше - в сети (средней и большой дальности); меньше - сами по себе
# вероятность распознать пуск ПРР и выключить РЛС (ОЦЕНКИ; идея - Skynet IADS): старые ЗРК замечают ПРР поздно
ARM_P = [(r"Patriot", None), (r"Kub|S-?75|SNR|S-?125|Hawk|Rapier", 0.3), (r"Roland|Osa|Tor|Tunguska|Gepard|Shilka|ZSU", 0.5),
         (r"Strela|Chaparral|Vulcan|Igla|Stinger", 0.0)]
ART_MISSIONS = 4         # ОЦЕНКА: огневых налётов батареи за миссию
ART_ROUNDS = 24          # ОЦЕНКА: снарядов на налёт (батарея)
ART_RADIUS_M = 250       # ОЦЕНКА: рассеивание по площади
PUSH_FLAG = 7001         # флаг DCS: ударные группы ИИ уходят с ИПМ на цель
PUSH_WAIT_S = 180        # ОЦЕНКА: сколько ударная группа ждёт пусков ПРР на ИПМ сверх расчётного времени
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


def iads_spec(m: Mission, state: dict, vg_by_unit: dict) -> tuple[list[dict], list[dict]]:
    """Сеть ПВО в миссии (iads.lua): ЗРК (группа, сторона, зона поражения, в сети ли, вероятность распознать ПРР,
    сбивает ли ПРР) и узлы сети (КРУ / РЛС обнаружения - наземные, ДРЛО - самолёты)."""
    import re as _re
    sams, net = [], []
    for uid, vg in vg_by_unit.items():
        u = state["units"].get(uid)
        if not u:
            continue
        cat = model.category(u)
        if cat == "gci":
            net.append({"group": vg.name, "side": 1 if u["side"] == "red" else 2, "air": False})
        elif cat == "sam":
            r = planner.threat_radius_km(u)
            types = " ".join(c["type"] for c in u.get("composition", []))
            p = next((x for rx, x in ARM_P if _re.search(rx, types, _re.I)), 0.4)
            sams.append({"group": vg.name, "side": 1 if u["side"] == "red" else 2, "r": r * 1000,
                         "net": r >= IADS_NET_MIN_KM, "arm_p": p or 0.0, "harm_ok": p is None})
    for side, sd in (("red", 1), ("blue", 2)):
        for c in m.coalition[side].countries.values():
            for g in c.plane_group:
                if "awacs" in g.name:
                    net.append({"group": g.name, "side": sd, "air": True})
    return sams, net


def iads_script(campaign_id: str, sortie: int, sams: list[dict], net: list[dict]) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    b = lambda v: "true" if v else "false"
    si = ", ".join(f'{{ group = {q(a["group"])}, side = {a["side"]}, r = {a["r"]:.0f}, net = {b(a["net"])}, '
                   f'arm_p = {a["arm_p"]:.2f}, harm_ok = {b(a["harm_ok"])} }}' for a in sams)
    ni = ", ".join(f'{{ group = {q(a["group"])}, side = {a["side"]}, air = {b(a["air"])} }}' for a in net)
    return (IADS_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@NET_M@", str(int(IADS_NET_KM * 1000))).replace("@SAMS@", si).replace("@NET@", ni))


def cap_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    """lua/cap.lua: пары прикрытия ИИ уходят домой, потеряв самолёт (группа, размер, точка зоны, точка посадки)."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ group = {q(c["group"])}, size = {int(c["size"])}, zone = {int(c["zone"])}, home = {int(c["home"])}, '
             f'side = {c["side"]}, title = {q(c["title"])} }}' for c in specs]
    return (CAP_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(items)))


def push_script(campaign_id: str, sortie: int, specs) -> str:
    """lua/push.lua: удар по готовности подавления ПВО - ударные группы (имя, точка ИПМ, точка посадки), группы
    подавления (имя, взлёт, с), флаг, срок (с от начала миссии)."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    lst = lambda xs, f=q: "{ " + ", ".join(f(x) for x in xs) + " }"
    if isinstance(specs, dict):
        specs = [specs]
    items = [(f'{{ id = {q(spec["id"])}, side = {spec["side"]}, title = {q(spec["title"])}, flag = {spec["flag"]}, strikes = {lst(spec["strikes"])}, ip = {lst(spec["ip"], str)}, '
              f'home = {lst(spec["home"], str)}, sead = {lst(spec["sead"])}, sead_start = {lst(spec["sead_start"], str)}, '
              f'deadline = {int(spec["deadline"])}, sams = {{ ' + ", ".join(f'{{ group = {q(g)}, radars = {lst(r)} }}' for g, r in (spec.get("sams") or {}).items()) + " } }")
             for spec in specs]
    return (PUSH_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
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


KIND_CATS = {   # категория подвески по виду задачи - первой (затем категории группы из доктрины)
    "strike_airfield": ["runway"], "strike_sam_site": ["dead"], "cas_contact": ["cas"], "cas_helo": ["cas"],
    "strike_column_march": ["bai"], "strike_bai": ["bai"], "strike_fofa": ["bai"], "strike_supply_route": ["bai"],
    "strike_bridge": ["strike"], "strike_depot": ["strike"], "strike_factory": ["strike"],
    "cap_own_troops": ["cap"], "qra": ["cap"],
}
GROUP_CATS = {"cover": ["escort", "cap"], "sead": ["sead"], "sead2": ["sead"], "kill": ["dead"], "escort": ["cas"], "helo": ["cas"], "sweep": ["cap"], "feint": ["cap", "escort"], "recon": ["bai", "cas"]}
PAYLOAD_NAMES = {   # категория -> имена подвесок DCS Retribution (data/payloads.json), по порядку предпочтения
    "cas": ["Retribution CAS", "CAS"],
    "anti_armor": ["Retribution BAI", "Retribution CAS", "CAS"],
    "bai": ["Retribution BAI", "Retribution CAS", "CAS", "Retribution Strike", "STRIKE"],
    "strike": ["Retribution Strike", "STRIKE", "Retribution BAI"],
    "bombs": ["Retribution Strike", "STRIKE", "Retribution BAI"],
    "runway": ["Retribution OCA/Runway", "Retribution Strike", "STRIKE"],
    "sead": ["Retribution SEAD", "SEAD", "Retribution SEAD Sweep", "Retribution SEAD Escort"],
    "dead": ["Retribution DEAD", "Retribution SEAD", "SEAD", "Retribution Strike", "STRIKE"],
    "cap": ["Retribution BARCAP", "Retribution TARCAP", "CAP", "Retribution Fighter Sweep"],
    "escort": ["Retribution Escort", "Retribution TARCAP", "CAP", "Retribution BARCAP"],
}


def loadout_cats(kind: str, g: dict) -> list[str]:
    """Категории подвески группы по порядку: вид задачи (для ударной группы) или роль группы обеспечения, затем
    категории доктрины (loadout группы)."""
    first = [] if g.get("loadout_user") else \
        GROUP_CATS.get(re.sub(r"\d+$", "", g.get("group", "")).split("_")[0], []) if g.get("group") != "strike" \
        else KIND_CATS.get(kind, [])
    out = []
    for c in first + list(g.get("loadout") or []):
        if c not in out:
            out.append(c)
    return out


def _payload(ac, cat: str, year: int | None = None) -> tuple[str, dict] | None:
    """Подвеска для типа и категории: (имя, пилоны) или None. Свои (payloads_custom.json) - первыми, затем DCS
    Retribution; из подвесок категории - первая, где всё оружие есть на год кампании, иначе первая (по году её
    поправит weapons.degrade)."""
    from . import weapons
    found = []
    for f in ("payloads_custom.json", "payloads.json"):
        try:
            pls = model.load_json(f).get("types", {}).get(ac.id) or {}
        except FileNotFoundError:
            continue
        low = {k.lower(): k for k in pls}
        for name in PAYLOAD_NAMES.get(cat, []) + ([cat] if f == "payloads_custom.json" else []):
            k = low.get(name.lower())
            if k and pls[k]["pylons"] and (k, f) not in [(x[0], x[2]) for x in found]:
                found.append((k, pls[k]["pylons"], f))
    if not found:
        return None
    k, pyl, _f = next((x for x in found if weapons.valid(x[1], year)), found[0])
    return k, pyl


def _apply_loadout(fg, ac, type_name: str, cats: list[str], state: dict | None = None) -> str | None:
    """Подвеска группы: первая категория, для которой есть подвеска по задачам DCS Retribution (payloads.json); затем -
    по году кампании (weapons.py: новее - замена своим по эпохе или снятие) и обязательные дополнения (weapons.fixups).
    Ничего - загрузка DCS по умолчанию для maintask (None)."""
    from . import weapons
    year = weapons.campaign_year(state) if state else None
    for cat in cats:
        if cat.startswith("rt:"):                # подвеска DCS Retribution по имени (выбор командующего)
            pls = (model.load_json("payloads.json").get("types", {}).get(ac.id) or {}).get(cat[3:])
            if pls and pls["pylons"]:
                for u in fg.units:
                    u.reset_loadout()
                    for num, d in pls["pylons"].items():
                        if int(num) in ac.pylons:
                            u.pylons[int(num)] = dict(d)
                weapons.degrade(fg, year)
                weapons.fixups(fg, year)
                return cat[3:]
    for cat in cats:
        pl = _payload(ac, cat, year)
        if pl:
            name, pylons = pl
            for u in fg.units:
                u.reset_loadout()
                for num, d in pylons.items():
                    if int(num) in ac.pylons:
                        u.pylons[int(num)] = dict(d)
            weapons.degrade(fg, year)
            weapons.fixups(fg, year)
            return f"{cat} ({name})"
    weapons.degrade(fg, year)
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


SEAD_SEARCH_KM = 5     # ОЦЕНКА: поиск РЛС ЗРК без свежих данных - район радиусом неточность места + столько


def sead_known(state: dict, side: str, sid: str) -> bool:
    """Позиция ЗРК известна точно (свежие данные разведки) - пуск по нему заранее спланирован. Противник игрока
    знает всё (как везде в модели)."""
    return side != state.get("player_side") or intel_exact(state, sid)


def intel_exact(state: dict, sid: str) -> bool:
    """Свежие данные по ЗРК: войсковая ПВО (attached_to) - по данным о своей части; объектовая (fixed) - известна."""
    u = state["units"][sid]
    if intel.tracked(state, u):
        return intel.level(state, sid) == "exact"
    if u.get("attached_to") in state["units"]:
        return intel_exact(state, u["attached_to"])
    return True


def _sead_zone(m, state: dict, sid: str):
    """Нет свежих данных: поиск и поражение средств ПВО в районе, где ЗРК видели (EngageTargetsInZone, Air Defence)."""
    u = state["units"][sid]
    c = _pt(m, intel.known_pos(state, u) or model.unit_pos(state, u))
    r = int((intel.unc_km(state, sid) + SEAD_SEARCH_KM) * 1000)
    return task.EngageTargetsInZone(Vector2(c.x, c.y), r, [task.Targets.All.GroundUnits.AirDefence])


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
BALANCE = 0.6                          # ОЦЕНКА: ЛА стороны в миссии - не меньше этой доли от другой (если есть вылеты в окне)
MISSION_AIR = 0                        # ЛА в миссии не больше (settings.mission_air, build --air; 0 - без ограничения)
AI_AIRLIFT = 2                         # ОЦЕНКА: рейсов воздушной перевозки каждой стороны в миссии (ближние к удару игрока)


def air_activity(state: dict, tk: dict, times: dict, sortie: int, m0: float, placed=None) -> list[dict]:
    """Воздушная война в миссии - по плану полётов на сутки (ato.py) обеих сторон: вылеты, которые в окне миссии
    [m0, m0 + ato.MISSION_LEN_S] в воздухе. Свои (кроме пакета игрока) - не больше AI_FLIGHTS["own"] групп, противника -
    AI_FLIGHTS["enemy"], ближние по времени и месту к удару игрока первыми; дежурства (ДРЛО, заправщик) - все, вне лимита.
    Кто к началу миссии уже в воздухе на пути к объекту - стоит на своём маршруте (в воздухе), кто позже - взлетает по
    расписанию, кто уже возвращается - в миссию не ставится. Летит весь пакет: ударная группа и группы обеспечения
    со своим временем (группа подавления ПВО - если её ЗРК развёрнуты в миссии: placed - развёрнутые части).
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
        ok = e["task"]["package"][0]["objective"]["kind"]   # при лимите ЛА: дежурства в зоне, пакеты, дежурные пары, прочее
        pri = 0 if ok == "orbit" else 1 if not e["ai_only"] else 2 if ok == "alert" else 3
        return (pri, abs(t["objective_s"] - tot) / 60 + near_km / 10)
    out = []
    n = {False: 0, True: 0}
    nl = {False: 0, True: 0}
    nr = {False: 0, True: 0}
    taken: set[str] = set()

    def add(e, capped: bool = True) -> int:
        """Вылет плана в миссию: число ЛА (0 - не ставится)."""
        enemy = e["side"] != tk["side"]
        okind = e["task"]["package"][0]["objective"]["kind"]
        lift = e["kind"] == "airlift" or okind == "airlift"
        if okind == "alert":                     # дежурная пара ПВО: в миссии, если база не дальше mission_km от цели
            tdg = model.doctrine(state, e["side"])["tasks"][e["kind"]]
            g = dict(e["task"]["package"][0])
            perf = state["units"][g["performer"]]
            if (model.dist_km(state["airbases"][g["base"]], tk["target_pos"]) > tdg.get("mission_km", 300)
                    or used.get(perf["id"], 0) + g["size"] > perf.get("count", 0)):
                return 0
            key = f"{'enemy' if enemy else 'ai'}_qra_{g['base']}"
            if key in times:
                return 0
            times[key] = {"start_s": 0, "late_s": 0, "objective_s": 0}
            used[perf["id"]] = used.get(perf["id"], 0) + g["size"]
            g.update({"group": key, "_tdef": tdg, "_side": e["side"], "_enemy": enemy, "_ai": True,
                      "title": i18n.L(i18n.lang(state), 'противник' if enemy else 'ИИ', 'enemy' if enemy else 'AI') + ": " + i18n.tr(e['title'], i18n.lang(state)), "_ato": e["id"], "_kind": e["kind"]})
            out.append(g)
            return g["size"]
        if capped and not e["ai_only"] and n[enemy] >= AI_FLIGHTS["enemy" if enemy else "own"]:
            return 0
        if lift and nl[enemy] >= AI_AIRLIFT:
            return 0
        rec = okind == "recon"                   # разведчик: один на сторону, маршрут рядом с районом удара игрока
        if rec and (nr[enemy] >= AI_RECON or min(model.dist_km(p, tk["target_pos"])
                                                   for p in e["task"]["package"][0]["route"]) > RECON_KM):
            return 0
        etask = copy.deepcopy(e["task"])
        planner.refresh(state, etask)            # цель группы ИИ - на её место к времени миссии
        g = dict(etask["package"][0])
        perf = state["units"][g["performer"]]
        if g["size"] <= 0 or used.get(perf["id"], 0) + g["size"] > perf.get("count", 0):
            return 0
        tdg = model.doctrine(state, e["side"])["tasks"][e["kind"]]
        t = e["times"][g["group"]]
        if e["ai_only"] and not lift and not rec:
            key = f"{'enemy' if enemy else 'ai'}_{e['kind']}_{ato.hhmm(e['tot_s']).replace(':', '')}"
            times[key] = {"start_s": max(0, int(t["objective_s"] - m0)), "late_s": 0,
                          "objective_s": max(0, int(t["objective_s"] - m0)),
                          "until_s": max(int(t["station_end_s"] - m0), ato.MISSION_LEN_S)}   # смена держит зону до конца окна
        else:
            take, obj = t["takeoff_s"] - m0, t["objective_s"] - m0
            if take < 0 and obj <= 60:
                return 0                         # уже над объектом (перевозка - садится) или возвращается - не ставится
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
        lg = i18n.lang(state)
        who = i18n.L(lg, 'противник' if enemy else 'ИИ', 'enemy' if enemy else 'AI') + ": " + i18n.tr(e['title'], lg)
        t_strike = int(e["times"]["strike"]["objective_s"] - m0)
        g.update({"group": key, "_tdef": tdg, "_side": e["side"], "_enemy": enemy, "_ai": True, "title": who,
                  "_ato": e["id"], "_kind": e["kind"], "_t_strike": t_strike})
        out.append(g)
        total = g["size"]
        # группы обеспечения вылета ИИ (подавление ПВО, прикрытие, расчистка...) - в миссии вместе с ударной, со своим
        # временем по плану полётов; группа подавления - только если её ЗРК развёрнуты в миссии
        if not e["ai_only"] and not lift and not rec:
            sup = {x["id"]: x for x in tdg.get("support", [])}
            for sg in etask["package"][1:]:
                st_ = e["times"].get(sg["group"])
                sp = state["units"].get(sg["performer"])
                if not st_ or not sp or sg["size"] <= 0 or used.get(sp["id"], 0) + sg["size"] > sp.get("count", 0):
                    continue
                if sg["objective"]["kind"] == "sam" and not all(x in (placed or ()) for x in sg["objective"]["units"]):
                    continue
                take, obj = st_["takeoff_s"] - m0, st_["objective_s"] - m0
                if take < 0 and obj <= 60:
                    continue
                g2 = dict(sg)
                k2 = f"{key}_{sg['group']}"
                if take < 0:
                    base = state["airbases"][g2["base"]]
                    first = g2["route"][0]
                    leg = model.dist_km(base, first)
                    done_km = -take * model.group_speed_kmh(state, g2, tdg) / 3600
                    g2["_air_start"] = model.lerp(base, first, min(done_km, max(0.0, leg - 3)) / leg) if leg > 0 else dict(first)
                times[k2] = {"start_s": max(0, int(take)), "late_s": 0, "objective_s": int(obj)}
                used[sp["id"]] = used.get(sp["id"], 0) + sg["size"]
                g2.update({"group": k2, "_tdef": tdg, "_side": e["side"], "_enemy": enemy, "_ai": True,
                           "title": f"{who} - {i18n.tr(sg['title'], lg)}", "_ato": e["id"], "_kind": e["kind"],
                           "_t_strike": t_strike, "_support": sup.get(sg.get("support_id"), {})})
                out.append(g2)
                total += sg["size"]
        return total
    cands = sorted((e for e in a["entries"] if e["id"] != tk.get("ato_id") and ato.in_window(e, t0, t1)), key=rank)
    # дежурство (ДРЛО, заправщик) - одна смена на зону: та, что дольше всех на станции в окне миссии; она держит зону
    # до конца миссии (смена смен - за кадром: иначе в миссии две машины в зоне и одна на обратном пути)
    def on_station(e):
        t = next(iter(e["times"].values()))
        return min(t1, t["station_end_s"]) - max(t0, t["objective_s"])
    best: dict = {}
    for e in cands:
        if e["task"]["package"][0]["objective"]["kind"] == "orbit":
            k = (e["side"], e["task"]["target"])
            if k not in best or on_station(e) > on_station(best[k]):
                best[k] = e
    cands = [e for e in cands if e["task"]["package"][0]["objective"]["kind"] != "orbit"
             or best.get((e["side"], e["task"]["target"])) is e]
    count = {False: sum(g["size"] for g in tk["package"]), True: 0}   # ЛА в миссии: свои (с пакетом игрока), противника
    cap = int((state.get("settings") or {}).get("mission_air", MISSION_AIR) or 0)
    air = [count[False]]                         # всего ЛА в миссии (с пакетом игрока и дежурствами)
    def fits(e):                                 # лимит ЛА миссии: вылет - весь пакет (оценка сверху), иначе не ставится
        pk = e["task"]["package"]
        return not cap or air[0] + sum(g["size"] for g in (pk[:1] if e["ai_only"] else pk)) <= cap
    for e in cands:
        k = add(e) if fits(e) else 0
        air[0] += k
        if k:
            taken.add(e["id"])
            if e["task"]["package"][0]["objective"]["kind"] not in ("alert", "orbit"):
                count[e["side"] != tk["side"]] += k
    # соотношение сил в миссии: у стороны с меньшим числом ЛА - ещё вылеты её плана в окне (сверх лимита групп),
    # пока не наберётся BALANCE от другой стороны (ОЦЕНКА; иначе 14 своих против двух Tornado)
    for weak in (True, False):
        for e in cands:
            if count[weak] >= BALANCE * count[not weak]:
                break
            if e["id"] in taken or (e["side"] != tk["side"]) != weak:
                continue
            k = add(e, capped=False) if fits(e) else 0
            air[0] += k
            if k:
                taken.add(e["id"])
                count[weak] += k
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


def _callsign(u) -> str:
    d = getattr(u, "callsign_dict", None)
    if isinstance(d, dict) and d.get("name"):
        return d["name"][:-1] if d["name"][-1:].isdigit() else d["name"]   # Enfield11 -> Enfield1 (группа)
    c = getattr(u, "callsign", None)
    return str(c) if c else ""


def radio_setup(m: Mission, state: dict, tk: dict, pkg: list[dict], sortie: int, player_air) -> list[str]:
    """Связь (comms.py): частоты групп (пакет игрока - одна частота, ДРЛО - своя), каналы радиостанций ЛА игрока,
    карточка связи и позывные групп для брифинга."""
    from . import comms
    from dcs.unit import Skill as _Sk
    nets = comms.plan(sortie, *(player_air or (None, None)))
    keys = {x["group"]: x for x in pkg}
    titles = []
    channels = False
    for side in ("red", "blue"):
        band = comms.PRIMARY[side]
        i = 0
        for c in m.coalition[side].countries.values():
            for grp in list(c.plane_group) + list(c.helicopter_group):
                parts = grp.name.split(" ")
                key = parts[1] if len(parts) >= 3 else ""
                if side == tk["side"] and key in keys:
                    grp.frequency = nets["pkg"][band]
                    titles.append(f"{i18n.tr(keys[key]['title'], i18n.lang(state))} - "
                                  + i18n.L(i18n.lang(state), "позывной ", "callsign ") + _callsign(grp.units[0]))
                elif "awacs" in grp.name:
                    grp.frequency = nets["awacs"][band]
                else:
                    i += 1
                    grp.frequency = comms.net(3 + sortie * 3 + 1 + i)[band]
                for u in grp.units:
                    if u.skill in (_Sk.Client, _Sk.Player):
                        channels = comms.set_presets(u, nets) or channels
    lg = i18n.lang(state)
    out = comms.card(nets, tk["side"], channels, lg)
    if not channels:
        out.append(i18n.L(lg, "каналы у этого типа в DCS не настраиваются - частоты выставить вручную",
                          "this type has no channel presets in DCS - set the frequencies manually"))
    return out + titles


def _kneeboard(m: Mission, state: dict, tk: dict, lines: list[str], order_lines: list[str], comm_lines: list[str],
               wx_text: str, lg: str) -> int:
    """Наколенный планшет ЛА игрока (kneeboard.py): задание и маршрут со временем, связь, погода и аэродромы."""
    from . import kneeboard
    L = lambda ru, en: i18n.L(lg, ru, en)
    hhmm = lambda s: (m.start_time + datetime.timedelta(seconds=int(s))).strftime("%H:%M")
    groups, seen = [], set()
    for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values()):
        for fg in list(c.plane_group) + list(c.helicopter_group):
            if not any(u.skill in (Skill.Client, Skill.Player) for u in fg.units):
                continue
            ut = fg.units[0].unit_type
            route, t, prev = [], float(getattr(fg.points[0], "ETA", 0) or 0), None
            for i, pt in enumerate(fg.points):     # время точек: заданное (ETA), иначе - по участкам и скорости точки
                if prev is not None:
                    eta = float(getattr(pt, "ETA", 0) or 0)
                    t = eta if getattr(pt, "ETA_locked", False) and eta else t + prev.position.distance_to_point(pt.position) / max(pt.speed or 150.0, 30.0)
                prev = pt
                route.append(f"{i:2d}  {hhmm(t)}  {pt.alt:>6.0f} {L('м', 'm')}  {pt.name or ''}")
            ab = [pt.airdrome_id for pt in fg.points if getattr(pt, "airdrome_id", None)]
            names = {a.id: a.name for a in m.terrain.airports.values()}
            fields = [L("Взлёт: ", "Departure: ") + names.get(ab[0], "-")] + ([L("Посадка: ", "Arrival: ") + names.get(ab[-1], "-")] if ab else [])
            sub = f"{fg.name} - {ut.id} x{len(fg.units)} - {L('день', 'day')} {state['day']}"
            pages = [
                (L("ЗАДАНИЕ", "MISSION"), [(i18n.tr(tk["title"], lg), [L(f"Удаление цели {tk['distance_km']:.0f} км", f"Target distance {tk['distance_km']:.0f} km"),
                                           L("Угрозы: ", "Threats: ") + (", ".join(state["units"][t]["name"] for t in tk["threats"]) or L("не выявлены", "none detected"))]),
                                          (L("Тактическая группа", "Package"), lines),
                                          (L("Порядок действий", "Sequence"), order_lines),
                                          (L("Маршрут (точка, время, высота)", "Route (point, time, altitude)"), route)]),
                (L("СВЯЗЬ", "COMMS"), [(L("Каналы и позывные", "Channels and callsigns"), comm_lines or ["-"])]),
                (L("ПОГОДА", "WEATHER"), [(L("Погода", "Weather"), wx_text.split("\n")), (L("Аэродромы", "Airfields"), fields)]),
            ]
            if (ut.id, fg.name) not in seen:
                seen.add((ut.id, fg.name))
                groups.append({"type": ut, "sub": sub, "pages": pages})
    return kneeboard.build(m, lg, groups)


def package_order(pkg: list[dict], times: dict, lg: str = "ru") -> list[str]:
    """Брифинг: сбор пакета (место, время каждой группы) и порядок выхода на объекты относительно удара (T)."""
    out = []
    mn = i18n.L(lg, "мин", "min")
    rv = [g for g in pkg if g.get("rv") and g["group"] in times and times[g["group"]].get("rv_s") is not None]
    if rv:
        out.append(i18n.L(lg, "Сбор (точка маршрута \"Сбор\"): ", "Rendezvous (waypoint \"Rendezvous\"): ") + "; ".join(
            f"{i18n.tr(g['title'], lg)} - ~{times[g['group']]['rv_s'] // 60} {mn}" for g in sorted(rv, key=lambda g: times[g["group"]]["rv_s"])))
    if len(pkg) > 1 and "strike" in times:
        t0 = times["strike"]["objective_s"]
        seq = sorted((g for g in pkg if g["group"] in times), key=lambda g: times[g["group"]]["objective_s"])
        out.append(i18n.L(lg, "Выход на объекты: ", "Push to objectives: ") + ", ".join(
            f"{i18n.tr(g['title'], lg)} T{(times[g['group']]['objective_s'] - t0) // 60:+d} {mn}" for g in seq)
            + i18n.L(lg, f" (T = ~{t0 // 60} мин от начала миссии)", f" (T = ~{t0 // 60} min after mission start)"))
    return out


ETA_POINTS = ("ИПМ", "Рубеж пуска", "Рубеж атаки", "Зона прикрытия", "Зона расчистки", "Демонстрация", "Район поиска",
              "Площадка", "Экипаж", "Зона дежурства")   # точки, к которым группа ИИ выходит ко времени


def _lock_eta(fg, objective_s: float, spd_kmh: float) -> None:
    """Время выхода группы ИИ на рубеж (ИПМ - время удара минус полёт ИПМ-цель; зона, рубеж пуска - время выхода на
    объект): ETA залочен, скорость - нет: DCS сама ускоряется или замедляется, чтобы успеть (как в планировщиках
    Liberation/Retribution - время на цели фиксировано, скорость свободна). Раньше залоченный сбор не трогаем."""
    pts = fg.points
    for i, w in enumerate(pts[1:], 1):
        if (w.name or "") in ETA_POINTS:
            eta = objective_s
            if w.name == "ИПМ" and i + 1 < len(pts) and (pts[i + 1].name or "") == "Цель":
                eta -= w.position.distance_to_point(pts[i + 1].position) / (spd_kmh / 3.6)
            if eta > 0:
                w.ETA, w.ETA_locked, w.speed_locked = int(eta), True, False
            return


def timeline(tdef: dict, state: dict, groups: list[dict], fly: str) -> dict[str, dict]:
    """Задержки взлёта групп пакета. Опорная - группа игрока: холодный старт (timing.player_cold_start_min, ОЦЕНКА)
    плюс полёт до объекта. Группа обеспечения выходит на свой объект за lead_min до выхода ударной группы на цель
    (ОЦЕНКИ из доктрины). Группы ИИ взлетают с полосы с задержкой start_s; если не успевают - late_s > 0."""
    fly_s = {g["group"]: _path_km(state["airbases"][g["base"]], planner.route_points(g)) * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
             + (0 if g["group"] == fly else ato.AI_TAKEOFF_S) for g in groups}   # скорость задачи доктрины; ИИ - разбег и сбор
    lead = {g["group"]: g.get("lead_min", 0) * 60 for g in groups}
    t_player = tdef["timing"]["player_cold_start_min"] * 60 + fly_s[fly]
    eta_strike = t_player + lead[fly]
    # время удара - по самой медленной группе: кто не успел бы к выходу игрока (вертолёты с дальней площадки), тот
    # взлетает с началом миссии, а удар сдвигается; остальные взлетают позже, игрок - тоже позже (по брифингу) или
    # ждёт в точке сбора: она гасит разницу во времени групп
    wait = max([0.0] + [-(eta_strike - lead[g["group"]] - fly_s[g["group"]]) for g in groups if g["group"] != fly])
    eta_strike += wait
    out = {}
    for g in groups:
        k = g["group"]
        start = eta_strike - lead[k] - fly_s[k]
        out[k] = {"start_s": 0 if k == fly else max(0, int(start)), "late_s": 0 if k == fly else max(0, int(-start)),
                  "objective_s": int(eta_strike - lead[k])}
        if k == fly and wait:                    # игрок: взлёт не раньше (слот в DCS доступен с начала миссии)
            out[k]["takeoff_s"] = int(tdef["timing"]["player_cold_start_min"] * 60 + wait)
        if g.get("rv"):                          # время в точке сбора: выход на объект минус полёт сбор - объект
            rest = _path_km(g["rv"], g["route"]) * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
            out[k]["rv_s"] = int(eta_strike - lead[k] - rest)
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
    from . import weather as wx_mod
    wx_now = wx_mod.apply(m, state, state["start_hour"])                  # погода суток (weather.py)

    # ---- весь театр: район задачи подробно, остальное - реже ----
    groups = materialize.theatre(state, tk, density)
    vg_by_unit, platoons = {}, {}
    keys = sorted({g["cluster"] for g in groups if g.get("cluster")})        # бои (кластеры) - у каждого своё место
    sites = {k: (state.get("battle_sites") or {}).get(k) for k in keys}
    def shift_of(g):
        s_ = sites.get(g.get("cluster")) if (g["kind"] in ("battle", "artillery") or g.get("battle")) else None
        return (s_["x"], s_["y"]) if s_ else (0.0, 0.0)
    gci_lines: list[str] = []
    tgt_group = next((g for g in groups if g["unit"] == tk["target"]), None)
    bkey = (tgt_group or {}).get("cluster")                                 # бой цели игрока
    airheads: dict[str, dict] = {}
    evac_groups: dict[str, list] = {}            # рота на эвакуацию: группы DCS по вместимости борта
    arts = [dict(a, cluster=g.get("cluster")) for g in groups if g["kind"] == "battle" and g.get("fire_at")
            for a in materialize.artillery(state, state["units"][g["unit"]], g["center"], g["axis"], g["fire_at"])]
    for g in groups + arts:
        if g["kind"] == "artillery":             # батарея части в бою: огневые налёты по линии противника
            vg = _ground_group(m, state, g, shift_of(g))
            sx, sy = shift_of(g)
            c = _pt(m, g["fire_at"])
            if g.get("target") == "counterbattery":  # РСЗО НАТО: по огневым позициям артиллерии противника в этом бою
                foe = next((a for a in arts if not a.get("mrl") and a["unit"] in g.get("engaged", [])), None)
                if foe:
                    fx, fy = shift_of(foe)
                    q = _pt(m, foe["vehicles"][len(foe["vehicles"]) // 2])
                    c, sx, sy = q, fx, fy
            n_m = int(g.get("missions", ART_MISSIONS))
            for k in range(n_m):                 # налёты подряд: по линии противника, со сдвигом по фронту (ОЦЕНКА)
                off = (k - (n_m - 1) / 2) * 300
                vg.points[0].tasks.append(task.FireAtPoint(Vector2(c.x + sx + off, c.y + sy), rounds=int(g.get("rounds", ART_ROUNDS)),
                                                           radius=ART_RADIUS_M * (2 if g.get("mrl") else 1)))
            continue
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
    from . import frontline                      # линия соприкосновения, территории, пункты и цели - на карте F10
    frontline.draw(m, state, lambda p: _pt(m, p))
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
    cap_specs: list[dict] = []                   # пары прикрытия ИИ (cap.lua)
    rescuers: list[dict] = []                    # вертолёты ИИ за экипажами (csar.lua пересчитает посадку)
    ctld = {"pilots": [], "actions": {}, "limits": {}, "cargo": {}, "logistic": [], "pickup": [], "groups": [],
            "crates": [], "lifts": [], "jtacs": [], "extract": []}   # CTLD (ctld_cfg.lua): борта игрока, зоны, ящики, авианаводчики
    ctld_assault: list[tuple[dict, str]] = []     # (высадка, борт игрока) - группа десанта CTLD по его доле роты
    ctld_lines: list[str] = []
    enemy = air_activity(state, tk, times, sortie, m0, set(vg_by_unit))
    # удар по готовности подавления ПВО (push.lua): ударные группы ИИ ждут на ИПМ пусков ПРР - в пакете игрока и в
    # каждом вылете ИИ с группой подавления (у каждого пакета - свой флаг)
    gby = {g["unit"]: g for g in groups if g["kind"] == "sam_site"}
    def _radars(uid):                            # РЛС позиции ЗРК в миссии: машины с ролью radar (у Осы, Роланда - сами ПУ)
        u, g = state["units"].get(uid), gby.get(uid)
        if not u or not g:
            return None
        roles = {c["type"]: c["role"] for c in u.get("composition", [])}
        names = [v["name"] for v in g["vehicles"] if roles.get(v["type"]) == "radar" or v["type"] in planner.RADAR_SAM_TYPES]
        return (g["name"], names) if names else None
    def _spec(pid, title, side, sead_groups, k):
        sams = {}
        for x in sead_groups:
            for uid in x["objective"].get("units", []):
                r = _radars(uid)
                if r:
                    sams[r[0]] = r[1]
        return {"id": f"push-{sortie}-{k}", "side": 1 if side == "red" else 2, "title": title, "flag": PUSH_FLAG + k,
                "strikes": [], "ip": [], "home": [], "deadline": 0,
                "sead": [f"{x['performer']} {x['group']} {sortie}" for x in sead_groups],
                "sead_start": [times[x["group"]]["start_s"] for x in sead_groups], "sams": sams}
    push_specs = {"player": _spec("player", tk["title"], tk["side"],
                                  [x for x in pkg if x["objective"]["kind"] == "sam"
                                   and support.get(x.get("support_id"), {}).get("mode") != "kill"], 0)}
    for x in enemy:
        if x.get("_ato") and x["objective"]["kind"] == "sam" and (x.get("_support") or {}).get("mode") != "kill":
            sp = push_specs.get(x["_ato"])
            if sp is None:
                sp = push_specs[x["_ato"]] = _spec(x["_ato"], x["title"].split(" - ")[0], x["_side"], [], len(push_specs))
            sp["sead"].append(f"{x['performer']} {x['group']} {sortie}")
            sp["sead_start"].append(times[x["group"]]["start_s"])
            for uid in x["objective"].get("units", []):
                r = _radars(uid)
                if r:
                    sp["sams"][r[0]] = r[1]
    player_air = None
    for g in pkg + enemy:
        tdg = g.get("_tdef") or (model.doctrine(state, g.get("_side", tk["side"]))["tasks"].get(g["jaat_kind"]) if g.get("jaat_kind") else None) \
            or tdef                              # группы противника - по его пакету доктрины; вертолёты совместного удара - по своей
        side_g = g.get("_side", tk["side"])
        t_strk = g.get("_t_strike", times["strike"]["objective_s"])   # время удара своего вылета (у ИИ - по плану полётов)
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
            _apply_loadout(fg, ac, perf["type"], loadout_cats(g.get("_kind") or tk["kind"], g), state)
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
                f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, "
                + i18n.L(i18n.lang(state), "в готовности на стоянке", "on alert at the parking area"))
            flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fg.units], "player": False,
                            "ato": g["_ato"], **({"side": side_g} if g.get("_enemy") else {})})
            continue
        if g["objective"]["kind"] == "orbit":    # дежурство: к началу миссии уже в зоне (в воздухе), до конца миссии
            t_ = times[g["group"]]
            orbit_group(m, state, g, perf, ac, mt, side_g, sortie, spd, t_, airport)
            lg_ = i18n.lang(state)
            line = (f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, " + i18n.L(lg_, "в зоне ", "on station ")
                    + (i18n.L(lg_, f"с ~{t_['start_s'] // 60} мин миссии", f"from ~{t_['start_s'] // 60} min") if t_["start_s"]
                       else i18n.L(lg_, "с начала миссии", "from mission start"))
                    + i18n.L(lg_, f" до ~{t_['until_s'] // 60} мин", f" until ~{t_['until_s'] // 60} min"))
            (enemy_lines if g.get("_enemy") else ai_lines).append(line)
            fl = m.find_group(f"{perf['id']} {g['group']} {sortie}")
            flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fl.units], "player": False,
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
        if is_player:
            player_air = (airport, airport)          # аэродром посадки уточняется ниже (перевозка - другой)
        st_s = times[g["group"]]["start_s"]
        if not is_player and not g.get("_air_start"):   # группы ИИ с полосы одного аэродрома - не в одну секунду (столкновение при появлении)
            while (base["airport"], st_s) in runway_slots:
                st_s += RUNWAY_GAP_S
            runway_slots.add((base["airport"], st_s))
            times[g["group"]]["start_s"] = st_s
        fg.start_time = st_s
        cat = _apply_loadout(fg, ac, perf["type"], loadout_cats(g.get("_kind") or tk["kind"], g), state)
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
        def push_hold(w, ip, tgt):               # ударная группа ИИ при подавлении ПВО - круг на ИПМ до флага (push.lua)
            if is_player:
                return
            if g.get("_ai"):                     # вылет ИИ: ударная группа - без группы обеспечения (_support)
                sp = push_specs.get(g.get("_ato")) if not g.get("_support") else None
            else:
                sp = push_specs["player"] if g["group"] == "strike" else None
            if not sp or not sp["sead"]:
                return
            hold = task.ControlledTask(task.OrbitAction(altitude=int(w.alt), speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            hold.stop_if_user_flag(sp["flag"], True)
            w.tasks.append(hold)
            sp["strikes"].append(fg.name)
            sp["ip"].append(len(fg.points) - 1)
            sp["deadline"] = int(t_strk - model.dist_km(ip, tgt) * 3600 / spd + PUSH_WAIT_S)
        obj = g["objective"]
        land = airport
        if g.get("rv") and obj["kind"] in planner.RV_KINDS:   # сбор пакета: ИИ приходит к своему времени (ETA), игрок - по брифингу
            w = wp(g["rv"], transit, "Сбор")
            rv_s = times[g["group"]].get("rv_s")
            if rv_s is not None and not is_player:
                w.ETA, w.ETA_locked, w.speed_locked = max(0, rv_s), True, False
            g["_rv_s"] = rv_s
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
            push_hold(wp(ip, transit, "ИПМ"), ip, tgt)
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
            sup = g.get("_support") or support.get(g.get("support_id"), {})
            hold_until = t_strk + int(sup.get("hold_after_min", 0) * 60)
            if sup.get("mode") == "kill" and g["route"]:   # добивание (killer): за hunter на рубеж, оттуда атака каждого ЗРК
                sam_pos = model.unit_pos(state, state["units"][obj["units"][0]])
                entry_km = planner.threat_radius_km(state["units"][obj["units"][0]]) + LOW_ENTRY_KM
                total = model.dist_km(base, sam_pos)
                if total > entry_km + 5:
                    wp(model.lerp(sam_pos, base, entry_km / total), transit, "Снижение", keep_alt=True)
                w = wp(g["route"][0], low, "Рубеж атаки")
                for sid in obj["units"]:
                    w.tasks.append(_attack(vg_by_unit[sid].id, ai) if sead_known(state, side_g, sid)
                                   else _sead_zone(m, state, sid))
            elif not sup.get("standoff_km"):     # доктрина без рубежа - атака с прохода по каждому ЗРК (как в 0.2)
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
                    # свежие данные разведки - по группе ЗРК (заранее спланированный пуск), иначе - поиск в районе
                    w.tasks.append(_engage(vg_by_unit[sid].id, ai, g.get("launch_alt_m")) if sead_known(state, side_g, sid)
                                   else _sead_zone(m, state, sid))
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
            push_hold(wp(ip, transit, "ИПМ"), ip, tgt)
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
        elif obj["kind"] == "escort_lz":         # прикрытие вертолётов: к площадке, обработка района, пока транспортные на земле
            w = wp(obj["pos"], int(g.get("alt_m") or transit), "Площадка (прикрытие)")
            c = _pt(m, obj["pos"])
            w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), int((g.get("zone_km") or 3) * 1000), [task.Targets.All.GroundUnits]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=int(g.get("alt_m") or transit), speed=spd,
                                                         pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_time(t_strk + int(g.get("land_s") or 120) + 120)
            w.tasks.append(orbit)
        elif obj["kind"] == "feint":            # демонстративная: на средней высоте к точке другим направлением, круг, домой
            alt = int(g.get("alt_m") or 4000)
            w = fg.add_waypoint(_pt(m, obj["pos"]), alt, speed=spd, name="Демонстрация")
            w.alt_type = "BARO"
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_duration(int((g.get("orbit_min") or 6) * 60))
            w.tasks.append(orbit)
        elif obj["kind"] in ("cap_zone", "cover_zone", "sweep_zone"):   # прикрытие / расчистка воздуха
            alt = int(g.get("alt_m") or 3000)
            w = wp(obj["pos"], alt, "Зона расчистки" if obj["kind"] == "sweep_zone" else "Зона прикрытия", keep_alt=True)
            w.alt_type = "BARO"
            c = _pt(m, obj["pos"])
            w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), int((g.get("zone_km") or 40) * 1000), [task.Targets.All.Air]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            until = (times[g["group"]]["objective_s"] + int((g.get("cap_min") or 20) * 60)) if obj["kind"] == "cap_zone" \
                else t_strk if obj["kind"] == "sweep_zone" \
                else (t_strk + int((g.get("hold_after_min") or 5) * 60))
            orbit.stop_after_time(until)
            w.tasks.append(orbit)
            g["until_s"] = until
            if not is_player and g["size"] > 1:   # ИИ: домой по остатку топлива и расходу ракет (DCS), без ведомого (cap.lua)
                fg.points[0].tasks += [task.OptRTBOnBingoFuel(True), task.OptRTBOnOutOfAmmo(task.OptRTBOnOutOfAmmo.Values.AAM)]
                g["_cap_zone_wp"] = len(fg.points) - 1
        else:                                    # проход над целью без атаки
            ip, tgt = g["route"]
            wp(ip, transit, "ИПМ")
            wp(tgt, transit, "Цель")
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
        if not is_player and not g.get("_air_start"):   # ИИ: ко времени на рубеже - ETA там, скорость DCS подберёт сама
            _lock_eta(fg, times[g["group"]]["objective_s"], spd)
        _land(fg, land, spd)
        if is_player:
            player_air = (airport, land)
        for sp in push_specs.values():
            if fg.name in sp["strikes"]:
                sp["home"].append(len(fg.points) - 1)
        if g.get("_cap_zone_wp") is not None:
            cap_specs.append({"group": fg.name, "size": g["size"], "zone": g.pop("_cap_zone_wp"), "home": len(fg.points) - 1,
                              "side": 1 if side_g == "red" else 2, "title": g.get("title", fg.name)})
        t = times[g["group"]]
        when = (i18n.L(i18n.lang(state), f"посадка в {g['_dest']} ~{t['objective_s'] // 60} мин", f"landing at {g['_dest']} ~{t['objective_s'] // 60} min")
                if g.get("_dest") else i18n.L(i18n.lang(state), f"в районе ~{t['objective_s'] // 60} мин", f"in the area ~{t['objective_s'] // 60} min"))
        if g.get("_enemy"):                      # авиация противника - в разведсводку, не в состав группы
            enemy_lines.append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, {when}")
            flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fg.units], "player": False,
                            "side": side_g, **({"ato": g["_ato"]} if g.get("_ato") else {})})
            continue
        lg = i18n.lang(state)
        Lx = lambda ru, en: i18n.L(lg, ru, en)
        (ai_lines if g.get("_ai") else lines).append(f"{i18n.tr(g['title'], lg)}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, "
                     + ((Lx("игрок, холодный старт", "player, cold start")
                         + (Lx(" (в базовом DCS тип только для ИИ - нужен мод)", " (AI-only type in base DCS - a mod is required)") if needs_mod else "")
                         + (Lx(f", ВЗЛЁТ через ~{t['takeoff_s'] // 60} мин (время удара - по самой медленной группе; раньше - ждать в точке сбора)",
                               f", TAKE OFF at ~{t['takeoff_s'] // 60} min (time on target is set by the slowest group; if early - hold at the rendezvous)")
                            if t.get("takeoff_s") else ""))
                        if is_player else Lx(f"ИИ, взлёт с полосы через {t['start_s'] // 60} мин", f"AI, runway takeoff at {t['start_s'] // 60} min"))
                     + (f", {when}" if g.get("_dest") else Lx(f", на объекте через ~{t['objective_s'] // 60} мин", f", on objective at ~{t['objective_s'] // 60} min"))
                     + (Lx(f", переход на {transit} м (угроз ЗРК в коридоре нет)", f", transit at {transit} m (no SAM threats in the corridor)")
                        if g.get("transit_alt_m_agl") else "")
                     + (Lx(f", ОПАЗДЫВАЕТ на {t['late_s'] // 60} мин", f", LATE by {t['late_s'] // 60} min") if t["late_s"] else "")
                     + (Lx(f", ожидание на рубеже пуска ({g['hold']['launch_km']:.0f} км от ЗРК) на {g['hold']['alt_m']} м до ~{g['hold']['until_s'] // 60} мин",
                           f", holding at the launch line ({g['hold']['launch_km']:.0f} km from the SAM) at {g['hold']['alt_m']} m until ~{g['hold']['until_s'] // 60} min")
                        if g.get("hold") else "")
                     + Lx(f"; задача DCS {mt.name}, подвеска {cat or 'DCS по умолчанию'}", f"; DCS task {mt.name}, loadout {cat or 'DCS default'}")
                     + (Lx(" (по году: ", " (by year: ") + f"{'; '.join(fg.__dict__.get('_rf_degraded', [])[:4])})" if fg.__dict__.get("_rf_degraded") else ""))
        flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fg.units], "player": is_player,
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
    iads_sams, iads_net = iads_spec(m, state, vg_by_unit)
    if iads_sams:                                # сеть ПВО: ЗРК на связи молчат до цели в зоне, реакция на ПРР
        trig.add_action(DoScript(String(iads_script(state["campaign_id"], state["sortie"], iads_sams, iads_net))))
    specs_p = [sp for sp in push_specs.values() if sp["strikes"]]
    if specs_p:                                  # удар по готовности подавления ПВО
        trig.add_action(DoScript(String(push_script(state["campaign_id"], state["sortie"], specs_p))))
    if cap_specs:                                # пары прикрытия ИИ: без ведомого - домой
        trig.add_action(DoScript(String(cap_script(state["campaign_id"], state["sortie"], cap_specs))))
    if qra_specs:                                # дежурные пары ПВО: взлёт по обнаружению противника радарами стороны
        trig.add_action(DoScript(String(qra_script(state["campaign_id"], state["sortie"], qra_specs))))
    if evac_specs:                               # эвакуация: рота садится в борта на площадке (evac.lua; игрок - CTLD)
        trig.add_action(DoScript(String(evac_script(state["campaign_id"], state["sortie"], evac_specs))))
    if assault_specs:                            # десант: рота выходит при посадке бортов на площадку (assault.lua)
        trig.add_action(DoScript(String(assault_script(state["campaign_id"], state["sortie"], assault_specs))))
    trig.add_action(DoScript(String(lua_hook(state["campaign_id"], state["sortie"], track))))  # String(...), не m.string(...): иначе DCS исполняет ключ перевода
    m.triggerrules.triggers.append(trig)

    comm_lines = radio_setup(m, state, tk, pkg, sortie, player_air)
    order_lines = package_order(pkg, times, i18n.lang(state))
    lg = i18n.lang(state)
    Lx = lambda ru, en: i18n.L(lg, ru, en)
    if lg == "en":                               # точки маршрута - на языке брифинга
        for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values()):
            for grp in list(c.plane_group) + list(c.helicopter_group):
                for pt in grp.points:
                    pt.name = i18n.waypoint(pt.name, lg)
    wx_text = wx_mod.summary(state, (m.start_time.hour + m.start_time.minute / 60), lg)
    m.set_description_text(
        f"{i18n.tr(tk['title'], lg)}\n\n{Lx('Погода', 'Weather')}: {wx_text}\n\n{Lx('День', 'Day')} {state['day']}" + (Lx(", НОЧНОЙ ВЫЛЕТ", ", NIGHT SORTIE") if _ato_night(state, m0) else "")
        + Lx(". Тактическая группа:\n", ". Package:\n") + "\n".join(f"- {ln}" for ln in lines)
        + ((Lx("\nПорядок действий группы:\n", "\nSequence of the package:\n") + "\n".join(f"- {ln}" for ln in order_lines)) if order_lines else "")
        + ((Lx("\n\nСвязь:\n", "\n\nCommunications:\n") + "\n".join(f"- {ln}" for ln in comm_lines)) if comm_lines else "")
        + Lx(f"\n\nУдаление цели: {tk['distance_km']:.0f} км. Угрозы на маршруте: ", f"\n\nTarget distance: {tk['distance_km']:.0f} km. Threats en route: ")
        + (", ".join(state['units'][t]['name'] for t in tk['threats']) or Lx("не выявлены", "none detected"))
        + (Lx("\nЗамечания планировщика: ", "\nPlanner notes: ") + tk['package_notes'] if tk.get("package_notes") else "")
        + ((Lx("\n\nДругие вылеты наших сил в это время:\n", "\n\nOther friendly sorties at this time:\n") + "\n".join(f"- {ln}" for ln in ai_lines)) if ai_lines else "")
        + (Lx("\nРазведка: в районе возможна активность авиации противника.", "\nIntelligence: enemy air activity is possible in the area.") if enemy_lines else "")
        + ((Lx("\n\nНаведение (КРУ, только МиГ-29):\n", "\n\nGround control intercept (GCI, MiG-29 only):\n") + "\n".join(f"- {ln}" for ln in gci_lines)) if gci_lines else "")
        + ((Lx("\n\nПеревозки и наведение (CTLD):\n", "\n\nTransport and JTAC (CTLD):\n") + "\n".join(f"- {ln}" for ln in ctld_lines)) if ctld_lines else ""))

    kb_pages = _kneeboard(m, state, tk, lines, order_lines, comm_lines, wx_text, lg)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))

    manifest = {
        "sortie": state["sortie"],
        "file": str(out_path),
        "weather": wx_now,                               # погода суток в миссии (weather.py)
        "kneeboard_pages": kb_pages,
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
        "artillery": [{"unit": g["unit"], "vehicles": [v["name"] for v in g["vehicles"]], "mrl": bool(g.get("mrl"))} for g in arts],
        "ground": [{"unit": g["unit"], "kind": g["kind"], "cluster": g.get("cluster"), "vehicles": [{"name": v["name"], "type": v["type"], "weight": v["weight"]} for v in g["vehicles"]]}
                   for g in groups if g["kind"] not in ("downed", "convoy", "artillery")],   # экипажи, колонны снабжения, батареи - не части модели
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

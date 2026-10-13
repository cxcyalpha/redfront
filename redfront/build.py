"""Сборка .miz через pydcs: звено игрока, развёрнутое окно наземной модели, хук дебрифа.

Манифест (что развёрнуто, с какими весами) сохраняется в состоянии кампании: по нему дебриф возвращает потери в модель.
"""
from __future__ import annotations

import datetime
import math
import random
from pathlib import Path

from dcs import Mission, task
from dcs.action import DoScript
from dcs.mapping import LatLng, Point, Vector2
from dcs.mission import StartType
from dcs.point import PointAction
from dcs.terrain.germany import Germany
from dcs.translation import String
from dcs.triggers import TriggerStart
from dcs.unit import Skill

from . import dcstypes, materialize, model, planner

LUA = Path(__file__).parent / "lua" / "debrief_hook.lua"
COLUMN_LUA = Path(__file__).parent / "lua" / "column_road.lua"
FRONT_LUA = Path(__file__).parent / "lua" / "front.lua"
SITE_LUA = Path(__file__).parent / "lua" / "battle_site.lua"

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


def _country(m: Mission, state: dict, side: str):
    """Страна стороны - из состава сил (countries), выбор игрока. В pydcs у страны есть коалиция по умолчанию
    (например, USA - blue); если она не совпадает со стороной, страна переносится в коалицию стороны."""
    name = state["countries"][side]
    for cname, coal in m.coalition.items():
        if coal.country(name) is not None:
            if cname != side:
                coal.swap_country(m.coalition[side], name)
            return m.coalition[side].country(name)
    raise KeyError(f"pydcs не знает страну '{name}'")


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


def ground_options(state: dict, g: dict) -> list[tuple[int, int]]:
    """Опции наземной группы: всё, кроме ПВО, стреляет только по наземным целям (OptRestrictTargets = GroundUnitsOnly).
    Наземные юниты в DCS по ЛА бьют неестественно точно; ПВО (ЗРК, ЗА) - без ограничения."""
    if model.category(state["units"][g["unit"]]) == "sam":
        return []
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
        units = ", ".join(f'{{ name = {q(u["name"])}, type = {q(u["type"])}, x = {u["x"]:.1f}, y = {u["y"]:.1f}, heading = {u["heading"]:.4f} }}'
                          for u in a["units"])
        ad_items.append(f'{{ name = {q(a["name"])}, groupId = {a["groupId"]}, country = {a["country"]}, '
                        f'follow = {q(a["follow"]) if a.get("follow") else "nil"}, units = {{ {units} }} }}')
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


def _ground_group(m: Mission, state: dict, g: dict, shift_xy: tuple[float, float] = (0.0, 0.0)):
    country = _country(m, state, g["side"])
    vs = g["vehicles"]
    vg = None
    for i, v in enumerate(vs):
        p0 = _pt(m, v)
        pos = Point(p0.x + shift_xy[0], p0.y + shift_xy[1], m.terrain)
        if vg is None:
            vg = m.vehicle_group(country, g["name"], dcstypes.vehicle(v["type"]), pos, group_size=1,
                                 move_formation=PointAction.OnRoad if g["kind"] == "column" else PointAction.OffRoad)
            vg.units[0].name = v["name"]
        else:
            u = m.vehicle(v["name"], dcstypes.vehicle(v["type"]))
            u.position = pos
            vg.add_unit(u)
        if "heading" in v:                         # курс задан шаблоном (позиция ЗРК развёрнута на ось угрозы)
            vg.units[-1].heading = v["heading"]
        elif g["kind"] == "column":                # в колонне машина смотрит на впереди идущую (или на следующий пункт маршрута)
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


def _set_player(unit) -> bool:
    """Посадить игрока. pydcs отказывает типам, которые в базовом DCS только для ИИ (Су-24М, МиГ-31): для мода,
    делающего такой тип летабельным на том же слоте, отказ лишний. Возвращает True, если слот требует мода."""
    if unit.unit_type.flyable:
        unit.set_player()
        return False
    unit.skill = Skill.Player
    try:
        unit.set_radio_preset()
    except Exception:                            # пресетов радио для типа ИИ в pydcs может не быть - не критично
        pass
    return True


SEARCH_ORBIT_ALT_M = 600   # ОЦЕНКА: высота круга над районом поиска, если в доктрине нет search_alt_m (абсолютная; рельеф ~0-100 м)
RUNWAY_GAP_S = 30         # ОЦЕНКА: интервал взлёта групп ИИ с полосы одного аэродрома
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
ENEMY_WINDOW_S = 300       # ОЦЕНКА: группы с объектом рядом с объектом игрока - в пределах +-5 мин от его удара
ENEMY_RADIUS_KM = 40       # ОЦЕНКА: "рядом с объектом игрока"
MISSION_WINDOW_S = (10 * 60, 60 * 60)   # ОЦЕНКА: остальные группы дня - на объекте между 10-й и 60-й минутой миссии


def air_activity(state: dict, tk: dict, times: dict, sortie: int) -> list[dict]:
    """Воздушная война в миссии: план дня обеих сторон (planner.plan_side). Свои задачи, кроме пакета игрока, летит ИИ
    (не больше AI_FLIGHTS["own"] групп), задачи противника - его ИИ (AI_FLIGHTS["enemy"]), по всему театру:
    группы с объектом рядом с объектом игрока - вокруг его удара, остальные - в окне миссии. Самолёты эскадрилий
    не расходуются сверх наличия (с учётом пакета игрока). Летит ударная группа задачи (без групп обеспечения).
    Время - со случайным разбросом, повторяемым для вылета."""
    if "strike" not in times:
        return []
    rnd = random.Random(f"{state['campaign_id']}-{sortie}")
    tot = times["strike"]["objective_s"]
    used: dict[str, int] = {}
    for g in tk["package"]:
        used[g["performer"]] = used.get(g["performer"], 0) + g["size"]
    out = []
    for side, limit, enemy in ((tk["side"], AI_FLIGHTS["own"], False), (model.enemy(tk["side"]), AI_FLIGHTS["enemy"], True)):
        tasks, _ = planner.plan_side(state, side)
        n = 0
        for t in tasks:
            if n >= limit:
                break
            if not enemy and t["kind"] == tk["kind"] and t["target"] == tk["target"]:
                continue                             # это задача игрока
            g = dict(t["package"][0])
            perf = state["units"][g["performer"]]
            if used.get(perf["id"], 0) + g["size"] > perf.get("count", 0):
                continue
            used[perf["id"]] = used.get(perf["id"], 0) + g["size"]
            tdg = model.doctrine(state, side)["tasks"][t["kind"]]
            n += 1
            g.update({"group": f"{'enemy' if enemy else 'ai'}{n}", "_tdef": tdg, "_side": side, "_enemy": enemy, "_ai": True,
                      "title": f"{'противник' if enemy else 'ИИ'}: {t['title']}"})
            fly_s = _path_km(state["airbases"][g["base"]], g["route"]) * 1000 / (tdg["speed_kmh"] / 3.6)
            near = model.dist_km(t["target_pos"], tk["target_pos"]) <= ENEMY_RADIUS_KM
            obj_s = tot + rnd.randint(-ENEMY_WINDOW_S, ENEMY_WINDOW_S) if near else rnd.randint(*MISSION_WINDOW_S)
            times[g["group"]] = {"start_s": max(0, int(obj_s - fly_s)), "late_s": max(0, int(fly_s - obj_s)), "objective_s": int(obj_s)}
            out.append(g)
    return out


def timeline(tdef: dict, state: dict, groups: list[dict], fly: str) -> dict[str, dict]:
    """Задержки взлёта групп пакета. Опорная - группа игрока: холодный старт (timing.player_cold_start_min, ОЦЕНКА)
    плюс полёт до объекта. Группа обеспечения выходит на свой объект за lead_min до выхода ударной группы на цель
    (ОЦЕНКИ из доктрины). Группы ИИ взлетают с полосы с задержкой start_s; если не успевают - late_s > 0."""
    spd = tdef["speed_kmh"] / 3.6
    fly_s = {g["group"]: _path_km(state["airbases"][g["base"]], g["route"]) * 1000 / spd for g in groups}
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
          task_no: int | None = None) -> dict:
    if task_no is not None:                      # задача плана дня по номеру (plan печатает список)
        planner.choose(state, task_no)
    tk = state["task"]
    if not tk:
        raise RuntimeError("нет задачи: сначала plan")
    tdef = model.doctrine(state, tk["side"])["tasks"][tk["kind"]]
    pkg = tk["package"]
    if fly not in {g["group"] for g in pkg}:
        raise ValueError(f"в пакете нет группы '{fly}'; есть: {', '.join(g['group'] for g in pkg)}")

    m = Mission(Germany())
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
    tgt_group = next((g for g in groups if g["unit"] == tk["target"]), None)
    bkey = (tgt_group or {}).get("cluster")                                 # бой цели игрока
    for g in groups:
        if g["kind"] == "battle":
            platoons[g["unit"]] = _battle_platoons(m, state, g, shift_of(g))
            vg_by_unit[g["unit"]] = platoons[g["unit"]][0][0]
        else:
            vg_by_unit[g["unit"]] = _ground_group(m, state, g, shift_of(g))
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
    sam_ids = list(dict.fromkeys(tk["threats"] + [g["unit"] for g in groups if model.category(state["units"][g["unit"]]) == "sam"]))
    circles = threat_circles(state, sam_ids)
    runway_slots: set = set()
    spd = tdef["speed_kmh"]
    flights, lines, enemy_lines, ai_lines = [], [], [], []
    enemy = air_activity(state, tk, times, sortie)
    for g in pkg + enemy:
        tdg = g.get("_tdef") or tdef             # группы противника - по его пакету доктрины
        side_g = g.get("_side", tk["side"])
        spd = tdg["speed_kmh"]
        perf = state["units"][g["performer"]]
        base = state["airbases"][g["base"]]
        airport = m.terrain.airports[base["airport"]]
        ac = dcstypes.flying(perf["type"])
        is_player = player and g["group"] == fly
        mt = _maintask(ac, g["maintask"])
        fg = m.flight_group_from_airport(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac, airport,
                                         maintask=mt, start_type=StartType.Cold if g["group"] == fly else StartType.Runway,
                                         group_size=g["size"])
        st_s = times[g["group"]]["start_s"]
        if g["group"] != fly:                    # группы ИИ с полосы одного аэродрома - не в одну секунду (столкновение при появлении)
            while (base["airport"], st_s) in runway_slots:
                st_s += RUNWAY_GAP_S
            runway_slots.add((base["airport"], st_s))
            times[g["group"]]["start_s"] = st_s
        fg.start_time = st_s
        cat = _apply_loadout(fg, ac, perf["type"], g["loadout"])
        needs_mod = is_player and _set_player(fg.units[0])
        for u in (fg.units[1:] if is_player else fg.units):
            u.skill = Skill.High
        def wp(p, alt, name, keep_alt=False):
            if not keep_alt and side_g == tk["side"] and in_threat(p, circles):   # в известной зоне ЗРК - на предельно малой высоте
                alt = min(alt, tdg.get("low_alt_m_agl", alt))
            if not is_player and alt < AI_LOW_MIN_M:  # ИИ ниже этого бьётся о землю (Су-24М: 3 случая на 40-80 м)
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
        if obj["kind"] == "column":              # ударная группа
            ip, tgt = g["route"]
            wp(ip, tdg["transit_alt_m_agl"], "ИПМ")
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
            wp(ip, tdg["transit_alt_m_agl"], "Отход")
        elif obj["kind"] == "sam":               # группа подавления ПВО: рубеж пуска по каждому ЗРК, ближний первым
            low = tdg.get("low_alt_m_agl", tdg["transit_alt_m_agl"])
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
                    wp(model.lerp(sam_pos, base, entry_km / total), tdg["transit_alt_m_agl"], "Снижение", keep_alt=True)
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
            wp(ip, tdg["transit_alt_m_agl"], "ИПМ")
            w = wp(center, tdg["transit_alt_m_agl"], "Район поиска")
            c = _pt(m, center)
            w.tasks.append(task.EngageTargetsInZone(Vector2(c.x, c.y), int(radius_km * 1000), [task.Targets.All.GroundUnits]))
            orbit = task.ControlledTask(task.OrbitAction(altitude=int(g.get("search_alt_m") or SEARCH_ORBIT_ALT_M), speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_duration(int((g.get("search_min") or 10) * 60))
            w.tasks.append(orbit)
            wp(ip, tdg["transit_alt_m_agl"], "Отход")
            g["zone"] = {"center": center, "radius_km": round(radius_km, 1)}
        elif obj["kind"] == "point":             # объект тыла: мост - по объекту карты, склад и аэродром - бомбами по точке
            ip, tgt = g["route"]
            wp(ip, tdg["transit_alt_m_agl"], "ИПМ")
            w = wp(tgt, tdg["attack_alt_m_agl"], "Цель")
            c = _pt(m, tgt)
            a_ = (g.get("ai") or {}).get("attack") or {}
            if obj.get("object") == "bridge":
                w.tasks.append(task.AttackMapObject(Vector2(c.x, c.y), group_attack=True))
            else:
                w.tasks.append(task.Bombing(Vector2(c.x, c.y), weapon_type=getattr(task.WeaponType, a_.get("weapon", "Auto")),
                                            expend=getattr(task.Expend, a_.get("expend", "Auto")), group_attack=True,
                                            altitude=int(tdg.get("bomb_alt_m", 1000))))
            wp(ip, tdg["transit_alt_m_agl"], "Отход")
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
            wp(ip, tdg["transit_alt_m_agl"], "ИПМ")
            wp(tgt, tdg["transit_alt_m_agl"], "Цель")
            wp(ip, tdg["transit_alt_m_agl"], "Отход")
        fg.land_at(airport)
        t = times[g["group"]]
        if g.get("_enemy"):                      # авиация противника - в разведсводку, не в состав группы
            enemy_lines.append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, в районе ~{t['objective_s'] // 60} мин")
            flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fg.units], "player": False, "side": side_g})
            continue
        (ai_lines if g.get("_ai") else lines).append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, "
                     + (("игрок, холодный старт" + (" (в базовом DCS тип только для ИИ - нужен мод)" if needs_mod else ""))
                        if is_player else f"ИИ, взлёт с полосы через {t['start_s'] // 60} мин")
                     + f", на объекте через ~{t['objective_s'] // 60} мин"
                     + (f", ОПАЗДЫВАЕТ на {t['late_s'] // 60} мин" if t["late_s"] else "")
                     + (f", ожидание на рубеже пуска ({g['hold']['launch_km']:.0f} км от ЗРК) на {g['hold']['alt_m']} м до ~{g['hold']['until_s'] // 60} мин"
                        if g.get("hold") else "")
                     + f"; задача DCS {mt.name}, подвеска {cat or 'DCS по умолчанию'}")
        flights.append({"group": g["group"], "performer": perf["id"], "units": [u.name for u in fg.units], "player": is_player})

    # ---- хук дебрифа ----
    state["sortie"] = sortie
    track = [v["name"] for g in groups if g["kind"] in ("column", "battle") for v in g["vehicles"]]
    trig = TriggerStart(comment="redfront debrief hook")
    specs = [s for s in (column_spec(m, state, g, vg_by_unit[g["unit"]]) for g in groups if g["kind"] == "column") if s]
    if specs:                                    # сначала переложить колонну на дорогу, потом - хук (в одном триггере, по порядку)
        trig.add_action(DoScript(String(column_script(state["campaign_id"], state["sortie"], specs))))
    ads = []                                     # ПВО на позициях - на открытое место (battle_site.lua)
    for g in groups:
        if g["kind"] != "sam_site":
            continue
        vg = vg_by_unit[g["unit"]]
        ads.append({"name": vg.name, "groupId": vg.id, "country": _country(m, state, g["side"]).id,
                    "follow": g.get("cluster") if g.get("battle") else None,
                    "units": [{"name": u.name, "type": u.type, "x": u.position.x, "y": u.position.y,
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
    trig.add_action(DoScript(String(lua_hook(state["campaign_id"], state["sortie"], track))))  # String(...), не m.string(...): иначе DCS исполняет ключ перевода
    m.triggerrules.triggers.append(trig)

    m.set_description_text(
        f"{tk['title']}\n\nДень {state['day']}. Тактическая группа:\n" + "\n".join(f"- {ln}" for ln in lines)
        + f"\n\nУдаление цели: {tk['distance_km']:.0f} км. Угрозы на маршруте: "
        + (", ".join(state['units'][t]['name'] for t in tk['threats']) or "не выявлены")
        + (f"\nЗамечания планировщика: {tk['package_notes']}" if tk.get("package_notes") else "")
        + (("\n\nДругие вылеты наших сил в это время:\n" + "\n".join(f"- {ln}" for ln in ai_lines)) if ai_lines else "")
        + ("\nРазведка: в районе возможна активность авиации противника." if enemy_lines else ""))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))

    manifest = {
        "sortie": state["sortie"],
        "file": str(out_path),
        "flights": flights,
        "package_lines": lines,
        "enemy_lines": enemy_lines,                      # авиация противника в миссии (в брифинг не выводится)
        "ai_lines": ai_lines,                            # свои группы ИИ по плану дня (в брифинге)
        "column_road": [s["name"] for s in specs],      # колонны, которые миссия переложит на дорогу при старте
        "front": [p["name"] for p in front],             # взводы частей в бою под управлением front.lua
        "battle_key": bkey,                              # бой цели игрока
        "battle_keys": keys,
        "objects": [o["id"] for o in objs],              # объекты тыла, по которым миссия считает разрушения
        "ground": [{"unit": g["unit"], "kind": g["kind"], "cluster": g.get("cluster"), "vehicles": [{"name": v["name"], "type": v["type"], "weight": v["weight"]} for v in g["vehicles"]]}
                   for g in groups],
    }
    state["manifest"] = manifest
    return manifest

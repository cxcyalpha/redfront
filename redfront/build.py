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
from . import natonames
from dcs.action import DoScript, DoScriptFile
from dcs.mapping import LatLng, Point, Vector2
from dcs.mission import StartType
from dcs.point import PointAction
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
ULIFT_LUA = Path(__file__).parent / "lua" / "unitlift.lua"
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
# развёртывание ЗРК с марша, с (ОЦЕНКИ по открытым ТТХ: время перевода из походного в боевое, с остановкой):
# с ходу ЗРК не стреляет, сразу после остановки - тоже; зенитные пушки (Шилка, Gepard, ЗУ) - с ходу, в таблице их нет
SAM_DEPLOY_S = {"Strela_10M3": 60, "Strela_1_9P31": 60, "SA_18_Igla_manpad": 60, "SA-18 Igla manpad": 60,
                "Soldier stinger": 60, "M1097 Avenger": 60, "Roland_ADS": 120, "Tor_9A331": 180, "CHAP_TorM2": 180,
                "M48 Chaparral": 180, "Osa_9A33_ln": 300, "Osa 9A33 ln": 300, "CHAP_PantsirS1": 300, "Kub_2P25_ln": 300,
                "SA-11 Buk LN 9A310M1": 300, "rapier_fsa_launcher": 600, "HQ-7_LN_SP": 180}
ART_MISSIONS = 4         # ОЦЕНКА: огневых налётов батареи за миссию
ART_ROUNDS = 24          # ОЦЕНКА: снарядов на налёт (батарея)
ART_RADIUS_M = 150       # ОЦЕНКА: рассеивание по площади (точка - машина противника)
ARTY_ACTIVE_KM = 30      # ОЦЕНКА: батареи ведут огонь в миссии только ближе к цели игрока (дальние - в модели)
MRL_MAX_ROUNDS = 40      # ОЦЕНКА: ракет РСЗО за миссию на сторону (один дивизионный залп Град - 240: нагрузка на DCS)
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


RAID_KMH = 800           # ОЦЕНКА: крейсерская скорость налёта бомбардировщиков
RAID_ALT_M = 9000        # ОЦЕНКА: высота налёта
RAID_LEAD_KM = 250       # ОЦЕНКА: группа появляется не дальше этого от рубежа пуска (успеть перехватить)


def raid_group(m: Mission, state: dict, r: dict):
    """Налёт бомбардировщиков (strategic.mission_raids): группа ИИ в воздухе идёт к рубежу пуска (на линии цель -
    аэродром части, не дальше LAUNCH_KM от цели), пускает крылатые ракеты по цели (Bombing, тип - крылатые ракеты)
    и уходит домой. Появляется так, чтобы выйти на рубеж ко времени пуска; перехватить её - задача ПВО противника."""
    from . import strategic
    u = state["units"][r["unit"]]
    t = state["units"][r["target"]]
    ms = strategic.MISSILES[r["missile"]]
    base = state["airbases"][u["base"]]
    tpos = model.unit_pos(state, t)
    d_bt = model.dist_km(base, tpos)
    launch = model.lerp(tpos, base, min(1.0, min(strategic.LAUNCH_KM, ms["range_km"] * 0.8, max(30.0, d_bt - 30)) / d_bt))
    lead = min(RAID_LEAD_KM, RAID_KMH * max(60, r["at_s"]) / 3600, model.dist_km(launch, base))
    start = model.lerp(launch, base, lead / max(1.0, model.dist_km(launch, base)))
    load = strategic.ALCM_CARRIERS.get(u.get("type"), (None, 1))[1]
    n_ac = max(1, min(4, -(-r["n"] // max(1, load))))
    ac = dcstypes.flying(u["type"])
    fg = m.flight_group_inflight(_country(m, state, u["side"]), f"{u['id']} raid {r['target']}", ac, _pt(m, start),
                                 RAID_ALT_M, speed=RAID_KMH, maintask=task.GroundAttack, group_size=n_ac)
    prefix = ms.get("pylon", "")
    for unit in fg.units:                        # подвеска: ракеты на все пилоны, где они вешаются
        unit.pylons.clear()
        for n in range(1, 30):
            py = getattr(ac, f"Pylon{n}", None)
            if not py:
                continue
            for v in vars(py).values():
                if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict) and prefix and prefix in v[1].get("name", ""):
                    unit.pylons[n] = {"CLSID": v[1]["clsid"]}
                    break
    fg.points[0].tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
    w = fg.add_waypoint(_pt(m, launch), RAID_ALT_M, RAID_KMH, name="Рубеж пуска")
    c = _pt(m, tpos)
    w.tasks.append(task.Bombing(Vector2(c.x, c.y), weapon_type=task.WeaponType.CruiseMissile, expend=task.Expend.All,
                                attack_qty=1, group_attack=True))
    fg.add_waypoint(_pt(m, base), RAID_ALT_M, RAID_KMH, name="Домой")
    return fg


def _set_script(act, src: str) -> None:
    """Текст DoScript: и поле text (редактор, trigrules), и params - из них pydcs собирает строку, которую исполняет
    DCS (trig.actions: a_do_script(...)); замена только text оставляла в игре прежний скрипт."""
    s = String(src)
    act.text = s
    act.params[:] = [s]


def _guard(src: str) -> str:
    """Скрипт миссии в pcall: ошибка - в DCS.log (env.error) и сообщением на экран, без остановки остальных."""
    head, _, rest = src.partition("\n")
    if not head.startswith("--"):                # первая строка - заголовок скрипта (комментарий): остаётся первой
        head, rest = "", src
    first = head[:80].replace("\\", "/").replace('"', "'")
    return (head + "\nlocal _rf_ok, _rf_err = pcall(function()\n" + rest + "\nend)\n"
            "if not _rf_ok then\n"
            f'  if env and env.error then env.error("redfront script error ({first}): " .. tostring(_rf_err)) end\n'
            f'  if trigger and trigger.action and trigger.action.outText then trigger.action.outText("redfront script error ({first}): " .. tostring(_rf_err), 30) end\n'
            "end\n")


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
        "spacing": round((g.get("spacing_km") or march["spacing_m"] / 1000.0) * 1000), "speed": g["speed_kmh"] / 3.6,
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


QRA_DEFAULT = {"per_flight": 4, "max_per_raid": 3, "reserve": 1, "base_km": 60}   # ОЦЕНКИ: подъём по налёту (qra.lua)


def qra_script(campaign_id: str, sortie: int, specs: list[dict], state: dict | None = None) -> str:
    """lua/qra.lua: дежурные звенья - группа (поздняя активация), коалиция, аэродром (x, y DCS), радиус взлёта; по
    сторонам - подъём по налёту (доктрина, задача qra: per_flight, max_per_raid, reserve, base_km). Нужен airpic.lua."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ id = {q(a["id"])}, group = {q(a["group"])}, side = {a["side"]}, x = {a["x"]:.1f}, y = {a["y"]:.1f}, '
             f'r = {a["r"]:.0f}, title = {q(a["title"])} }}' for a in specs]
    sides = []
    for c in sorted({a["side"] for a in specs}):
        t = {}
        if state is not None:
            t = model.doctrine(state, "red" if c == 1 else "blue")["tasks"].get("qra") or {}
        v = {k: t.get(k, d) for k, d in QRA_DEFAULT.items()}
        sides.append(f'[{c}] = {{ per_flight = {int(v["per_flight"])}, max_per_raid = {int(v["max_per_raid"])}, '
                     f'reserve = {int(v["reserve"])}, base_km = {float(v["base_km"]) * 1000:.0f} }}')
    return (QRA_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(items)).replace("@SIDES@", ", ".join(sides)))


GCI_LUA = Path(__file__).parent / "lua" / "gci.lua"


AIRPIC_LUA = Path(__file__).parent / "lua" / "airpic.lua"


def airpic_script(state: dict, m: Mission | None = None) -> str:
    """lua/airpic.lua: общая картина обстановки для qra.lua и gci.lua; свои объекты сторон (аэродромы, ЗРК) - для
    курса цели 'к своему объекту' (нужна миссия m: координаты DCS)."""
    prot = []
    for side in model.SIDES:
        pts = []
        if m is not None:
            objs = [b for b in state["airbases"].values() if b.get("side") == side and b.get("kind") != "carrier"]
            objs += [model.unit_pos(state, u) for u in state["units"].values()
                     if u["side"] == side and model.category(u) == "sam" and u.get("state") not in ("destroyed", "pending")]
            for o in objs:
                try:
                    pt = _pt(m, o)
                    pts.append(f"{{ x = {pt.x:.0f}, y = {pt.y:.0f} }}")
                except (KeyError, TypeError):
                    continue
        prot.append(f'[{1 if side == "red" else 2}] = {{ {", ".join(pts)} }}')
    return (AIRPIC_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@PROTECT@", ", ".join(prot)))


def gci_script(state: dict, fighters: list[dict]) -> str:
    """lua/gci.lua: наземное наведение истребителей ИИ сторон, у которых в доктрине есть gci (каналы, радиус, граница
    от своих РЛС, соотношение сил, атака с одного захода, вертолёты, bingo, пар на цель). Нужен airpic.lua."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    sides = []
    for side in model.SIDES:
        g = model.doctrine(state, side).get("gci")
        if not g:
            continue
        sides.append(f'[{1 if side == "red" else 2}] = {{ channels = {int(g.get("channels", 4))}, commit = {float(g.get("commit_km", 100)) * 1000:.0f}, '
                     f'leash = {float(g.get("leash_km", 40)) * 1000:.0f}, odds = {float(g.get("odds", 1.5))}, '
                     f'hit_run = {"true" if g.get("hit_run") else "false"}, heli = {"true" if g.get("heli") else "false"}, '
                     f'bingo = {float(g.get("bingo", 0.35))}, per_target = {int(g.get("per_target", 2))} }}')
    items = [f'{{ group = {q(f["group"])}, side = {f["side"]} }}' for f in fighters]
    return (GCI_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@FIGHTERS@", ", ".join(items))
            .replace("@SIDES@", ", ".join(sides)))


def gci_sides(state: dict) -> set[int]:
    return {1 if s == "red" else 2 for s in model.SIDES if model.doctrine(state, s).get("gci")}


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


SAMCTL_LUA = Path(__file__).parent / "lua" / "samctl.lua"
AAA_RX = r"ZU-23|ZU_23|S-60|S_60|KS-19|KS_19|Vulcan|Gepard|ZSU|M163|flak|Bofors|M1939|2A|Shilka"
MANPAD_RX = r"manpad|Stinger|Igla|Strela-2|SA-18|SA-7|Soldier stinger"
SAM_DELAY_S = {"long": 45, "medium": 25, "short": 12}   # ОЦЕНКА: реакция расчёта от обнаружения до огня (выучка 1)
SAM_AUTONOMOUS = {"Osa_9A33_ln", "Strela_1_9P31", "Strela_10M3", "X_2S6_Tunguska", "Tor 9A331", "Roland_ADS",
                  "M48 Chaparral", "M1097 Avenger", "HQ-7_LN_SP", "rapier_fsa_launcher"}   # РЛС/оптика - на пусковой
SAM_K_RANGE = 0.7     # ОЦЕНКА: пуск - ближе 70% зоны поражения
AAA_SKILL = "Average"  # ОЦЕНКА: зенитная артиллерия - средняя выучка (прицельный огонь ИИ DCS слишком точен)


# РЭБ (ОЦЕНКИ). Сила помехи 0..1 - насколько помеха удлиняет реакцию и сокращает рубеж пуска ЗРК (см. samctl.lua).
# Самолётная станция помех (самозащита) - только по своему самолёту и слабее; постановщик вне зоны - по всем целям
# в секторе ЗРК. Типы - с обычной для них станцией (ALQ-119/131/126, СПС-141/Сорбция, Remora/Barax...).
ECM_SELF = {"F-4E": 0.25, "F-4E-45MC": 0.25, "F-16A": 0.25, "F-16C_50": 0.3, "F-15C": 0.3, "F-14A": 0.2,
            "F-14A-135-GR": 0.2, "F-14A-135-GR-Early": 0.2, "F-14A-95-GR": 0.2, "FA-18C_hornet": 0.3, "A-6E": 0.25, "A-10A": 0.25,
            "AV8BNA": 0.2, "Tornado IDS": 0.3, "Tornado GR4": 0.3, "B-52H": 0.4, "Su-24M": 0.3, "Su-25": 0.2,
            "Su-25T": 0.25, "Su-17M4": 0.2, "MiG-27K": 0.25, "Tu-22M3": 0.35, "Su-27": 0.25, "MiG-29A": 0.15,
            "MiG-29S": 0.2, "Mirage-F1CE": 0.15, "AJS37": 0.25}
ECM_SELF_FROM = {"F-16C_50": 1984, "FA-18C_hornet": 1984, "MiG-29S": 1990, "Su-27": 1985}
SAM_ECCM = {"S-300": 0.6, "SA-11": 0.5, "Buk": 0.5, "Patriot": 0.6, "Tor": 0.5, "SA-15": 0.5, "Hawk": 0.3,
            "Kub": 0.1, "SA-6": 0.1, "S-125": 0.1, "S-75": 0.0, "Roland": 0.3, "Osa": 0.2, "Tunguska": 0.3}   # помехозащищённость


def samctl_spec(state: dict, vg_by_unit: dict) -> list[dict]:
    """ПВО в миссии для samctl.lua: вид (ЗРК / зенитки / ПЗРК), зона, задержка реакции (по зоне и выучке части),
    подвижность (стрельба с переездом)."""
    import re as _re
    from . import logistics as _lg
    out = []
    for uid, vg in vg_by_unit.items():
        u = state["units"].get(uid)
        if not u or model.category(u) != "sam":
            continue
        types = [x.type for x in vg.units]
        n_aaa = sum(1 for t in types if _re.search(AAA_RX, t, _re.I))
        n_mp = sum(1 for t in types if _re.search(MANPAD_RX, t, _re.I))
        kind = ("sam" if n_aaa + n_mp < len(types) else "aaa" if n_aaa else "manpad")   # есть ЗРК - ЗРК; пушки (+ПЗРК) - зенитки
        r = planner.threat_radius_km(u)
        tier = "long" if r >= 30 else "medium" if r >= 10 else "short"
        parent = state["units"].get(u.get("attached_to") or "") or {}
        q = float(u.get("quality") or parent.get("quality") or 1.0)
        if kind == "aaa":
            for x in vg.units:
                x.skill = Skill.Average if AAA_SKILL == "Average" else x.skill
        out.append({"group": vg.name, "kind": kind, "r": (r or 3) * 1000, "k": SAM_K_RANGE,
                    # переезд в миссии - только самоходные комплексы одной машиной (Оса, Стрела, Тунгуска); батарея
                    # с отдельной РЛС (Куб, Hawk) в бою не снимается - она меняет позицию между сутками (logistics)
                    "delay": SAM_DELAY_S[tier] / max(0.5, q),
                    "mobile": kind == "sam" and all(t in SAM_AUTONOMOUS or _re.search(AAA_RX + "|" + MANPAD_RX, t, _re.I)
                                                    for t in types),
                    "manpad": n_mp > 0,
                    "eccm": max([v for k_, v in SAM_ECCM.items()
                                 if any(k_.lower() in (t + " " + str(u.get("name", ""))).lower() for t in types)] or [0.2])})
    return out


def samctl_script(state: dict, specs: list[dict], jam_groups: list[str] | None = None) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = ", ".join(f'{{ group = {q(a["group"])}, kind = "{a["kind"]}", r = {a["r"]:.0f}, k_range = {a["k"]}, '
                      f'delay = {a["delay"]:.0f}, mobile = {"true" if a["mobile"] else "false"}, '
                      f'manpad = {"true" if a.get("manpad") else "false"}, eccm = {a.get("eccm", 0):.2f} }}' for a in specs)
    yr = int(str(state.get("date", "1985"))[:4])
    selfj = ", ".join(f'["{t}"] = {p:.2f}' for t, p in ECM_SELF.items() if yr >= ECM_SELF_FROM.get(t, 0))
    jams = ", ".join(q(n) for n in (jam_groups or []))
    return (SAMCTL_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", state["campaign_id"])
            .replace("@SORTIE@", str(int(state["sortie"]))).replace("@SPECS@", items)
            .replace("@SELFJ@", selfj).replace("@JAMS@", jams))


def iads_script(campaign_id: str, sortie: int, sams: list[dict], net: list[dict]) -> str:
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    b = lambda v: "true" if v else "false"
    si = ", ".join(f'{{ group = {q(a["group"])}, side = {a["side"]}, r = {a["r"]:.0f}, net = {b(a["net"])}, '
                   f'arm_p = {a["arm_p"]:.2f}, harm_ok = {b(a["harm_ok"])} }}' for a in sams)
    ni = ", ".join(f'{{ group = {q(a["group"])}, side = {a["side"]}, air = {b(a["air"])} }}' for a in net)
    return (IADS_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@NET_M@", str(int(IADS_NET_KM * 1000))).replace("@SAMS@", si).replace("@NET@", ni))


def cap_script(campaign_id: str, sortie: int, specs: list[dict], strict: bool = False) -> str:
    """lua/cap.lua: пары прикрытия ИИ уходят домой, потеряв самолёт (группа, размер, точка зоны, точка посадки)."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ group = {q(c["group"])}, size = {int(c["size"])}, zone = {int(c["zone"])}, home = {int(c["home"])}, '
             f'side = {c["side"]}, title = {q(c["title"])} }}' for c in specs]
    return (CAP_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
            .replace("@SPECS@", ", ".join(items)).replace("@STRICT@", "true" if strict else "false"))


def strict_abort(state: dict) -> bool:
    """Правила срыва (settings.abort_mode): strict - удар отменяется, если все группы подавления сбиты; пара домой,
    потеряв ведомого. soft (по умолчанию, играбельность) - удар идёт по сроку; группа домой, потеряв половину."""
    return (state.get("settings") or {}).get("abort_mode", "soft") == "strict"


def push_script(campaign_id: str, sortie: int, specs, strict: bool = False) -> str:
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
            .replace("@SPECS@", ", ".join(items)).replace("@STRICT@", "true" if strict else "false"))


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


def ulift_script(campaign_id: str, sortie: int, specs: list[dict]) -> str:
    """lua/unitlift.lua: вертолётом к части - вид (resupply, medevac), площадка (x, y DCS), радиус, посадка (с), борта."""
    q = lambda s: '"' + str(s).replace("\\", "/").replace('"', "'") + '"'
    items = [f'{{ id = {q(a["id"])}, mode = {q(a["mode"])}, title = {q(a["title"])}, x = {a["x"]:.1f}, y = {a["y"]:.1f}, '
             f'r = {a["r"]:.0f}, land = {int(a["land"])}, helos = {{ {", ".join(q(n) for n in a["helos"])} }} }}' for a in specs]
    return (ULIFT_LUA.read_text(encoding="utf-8").replace("@CAMPAIGN@", campaign_id).replace("@SORTIE@", str(int(sortie)))
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
    bases = {side: ", ".join(f'[{q(b["airport"])}] = true' for b in state["airbases"].values() if b.get("side") == side and b.get("airport"))
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


LUA_EN = {   # сообщения скриптов миссии по-английски (литералы Lua целиком)
    "Десант высаживается: ": "Air assault landing: ", "Загрузка - только на земле.": "Loading only on the ground.",
    "Ваша доля десанта уже высажена.": "Your share of the troops has already been landed.",
    "Загрузка - у своего аэродрома.": "Load at your own airfield.", "Десант на борту (": "Troops on board (",
    " фигур): ": " troops): ", ". Площадка - в меню.": ". Landing zone - in the menu.",
    "Десанта на борту нет - сначала загрузите у своего аэродрома.": "No troops on board - load them at your own airfield first.",
    "Высадка - только на земле.": "Unloading only on the ground.", "Вы не на площадке: до неё %.1f км.": "You are not at the landing zone: it is %.1f km away.",
    "Десант высажен. Возвращайтесь.": "Troops landed. Return to base.", "Площадка: пеленг %03d, %.1f км (дым)%s.": "Landing zone: bearing %03d, %.1f km (smoke)%s.",
    "; перенесена на открытое место (%.0f м)": "; moved to open ground (%.0f m)",
    "Десант высажен на площадке. Возвращайтесь.": "Troops landed at the landing zone. Return to base.", "Десант": "Air assault",
    "Загрузить десант": "Load troops", "Высадить десант": "Unload troops", "Площадка": "Landing zone",
    " на борту. Доставьте на свой аэродром.": " on board. Deliver to your own airfield.",
    ": слышу вас! Ракета и дым - в меню F10, CSAR. Садитесь рядом или зависните надо мной.":
        ": I hear you! Flare and smoke - F10 menu, CSAR. Land nearby or hover over me.",
    ": бегу к вам, ": ": running to you, ", " с.": " s.", "Лебёдка: держите зависание ещё ": "Hoist: keep hovering for another ",
    "%s: пеленг %03d, %.1f км, маяк %d кГц": "%s: bearing %03d, %.1f km, beacon %d kHz", "Сбитые экипажи:\n": "Downed crews:\n",
    "Сбитых экипажей нет.": "No downed crews.", ": дым!": ": smoke!", ": ракета!": ": flare!", "Сбитые экипажи": "Downed crews",
    "Ракета у ближнего": "Flare at the nearest", "Дым у ближнего": "Smoke at the nearest", "экипаж ": "crew ",
    " катапультировался, маяк ": " ejected, beacon ", " кГц.": " kHz.", "Экипажи доставлены. Отличная работа!": "Crews delivered. Well done!",
    ": площадка - зелёный дым. Сядьте и ждите ": ": landing zone - green smoke. Land and wait ",
    "Раненые доставлены. Рейс засчитан.": "Wounded delivered. Flight completed.",
    "Раненые на борту - на свой аэродром.": "Wounded on board - fly to your own airfield.",
    "Груз сдан части. Рейс засчитан.": "Cargo delivered to the unit. Flight completed.",
    "Погрузка раненых: ещё ": "Loading wounded: ", "Разгрузка: ещё ": "Unloading: ",
    "место боя сдвинуто на %.0f м (оценка %.2f), машин переставлено %d, без хорошего места %d":
        "battle site moved %.0f m (score %.2f), %d vehicles repositioned, %d without a good spot",
    "ошибка: ": "error: ", "ПВО на открытом месте: %d машин, у строений осталось %d%s": "air defence in the open: %d vehicles, %d left by buildings%s",
    ", позиция сдвинута на %.0f м (аэродром, вода, город)": ", position moved %.0f m (airfield, water, town)",
    " ВНИМАНИЕ: пролёты моста по именам не найдены": " WARNING: bridge spans not found by name",
    " ВНИМАНИЕ: мостов рядом нет, взят ближайший объект - проверьте координаты (set-pos)":
        " WARNING: no bridges nearby, the nearest object was taken - check the coordinates (set-pos)",
    "%s %.0fм": "%s %.0fm", "redfront targets %s: объектов карты %d (в радиусе %d): %s%s": "redfront targets %s: map objects %d (within radius %d): %s%s",
    "РЛС ЗРК у цели уничтожены или подавлены - удар разрешён": "SAM radars at the target destroyed or suppressed - strike cleared",
    "подавление ПВО ведёт пуски - удар в окне подавления": "SEAD is firing - strike inside the suppression window",
    "пусков подавления нет, РЛС ПВО молчат - удар по времени": "no SEAD launches, air defence radars silent - strike on time",
    "группы подавления ПВО сбиты - удар отменён, ударным группам - домой": "SEAD groups shot down - strike cancelled, strike groups return to base",
    "дорога для участка с головой колонны не найдена": "no road found for the segment with the column head",
    "на дороге: %d машин": "on the road: %d vehicles", "отход на исходную на %d с: в строю %d из %d": "withdrawal to the start line at %d s: %d of %d in action",
    "redfront front: %d взводов": "redfront front: %d platoons", "Эвакуация: группа на борту (": "Extraction: group on board (",
    "Снабжение сдано на склад: ": "Supplies delivered to the depot: ", "redfront ctld: авианаводчик ": "redfront ctld: JTAC ",
    " - взлёт по ": " - scramble against ", "redfront: результаты не сохранятся - MissionScripting.lua не разблокирован":
        "redfront: results will not be saved - MissionScripting.lua is not unlocked",
    ": потерян ведомый - уходим домой": ": wingman lost - returning to base",
    ": потеряна половина группы - уходим домой": ": half the flight lost - returning to base",
    "redfront: пакет собран - на маршрут": "redfront: package joined - pushing",
    " - взлёт по налёту ": " - scramble against a raid of ", " км)": " km)",
    "Вы не на площадке (до неё %.1f км): высадка не засчитана. Заберите группу обратно (Unload / Extract Troops) и высадите на площадке.":
        "You are not at the landing zone (%.1f km away): the landing does not count. Pick the group up again (Unload / Extract Troops) and land them at the zone.",
    "группы подавления ПВО сбиты - удар по сроку без подавления": "SEAD flights shot down - strike goes on time without suppression",
}


def lua_en(src: str) -> str:
    """Скрипт миссии по-английски: русские строковые литералы Lua - по словарю LUA_EN, иначе переводом i18n_en
    (подписи из модели: названия частей, задач). Комментарии не трогаются - их не видно."""
    from . import i18n_en

    def lit(mm):
        body = mm.group(1)
        if not i18n_en.CYR.search(body):
            return mm.group(0)
        txt = body.replace('\\"', '"')
        out = LUA_EN.get(txt) or LUA_EN.get(body) or i18n_en.en(txt)
        return '"' + out.replace('"', '\\"') + '"'
    lines = []
    for ln in src.split("\n"):
        code, sep, comment = ln.partition("--")
        lines.append(re.sub(r'"((?:[^"\\\n]|\\.)*)"', lit, code) + sep + comment)
    return "\n".join(lines)


class CarrierPad:
    """Авианосец как база группы (вместо аэродрома pydcs): группа кораблей, позиция, частота (TACAN/ICLS - в задачах
    корабля), id корабля-авианосца для посадки. Те же поля, что сборка берёт у аэродрома: position, id, name, atc_radio."""
    def __init__(self, group, info: dict):
        self.group = group
        self.unit = group.units[0]
        self.position = self.unit.position
        self.id = self.unit.id
        self.name = info["name"]
        self.info = info
        f = float(info.get("freq", 127.5)) * 1e6
        self.atc_radio = type("R", (), {"vhf_high_hz": f, "uhf_hz": f})()


NAVAL_GROUPS: dict = {}   # группы кораблей этой миссии: id части флота -> группа pydcs (цели ударов, дебриф)
NAVAL_SHIPS: dict = {}    # id части флота -> [(класс pydcs, имя корабля)]


def carrier_groups(m: Mission, state: dict, wind_from: float) -> dict[str, "CarrierPad"]:
    """Флот кампании в миссии (naval.py): каждая корабельная группа модели - группа кораблей DCS из живых кораблей
    (реальные имена). Группа с авианосцем - на галсах против ветра (курс - откуда дует ветер; 25 узлов, галс ~40 км -
    ОЦЕНКА), TACAN и ICLS авианосца включены с начала миссии; остальные - курсом галсами у своей позиции (10 узлов,
    катера - 25). Авианосец - база (state airbases kind carrier, поле naval). -> id базы: CarrierPad."""
    import dcs.ships as _ships
    from . import naval
    NAVAL_GROUPS.clear()
    NAVAL_SHIPS.clear()
    out = {}
    by_unit = {b.get("naval"): (bid, b) for bid, b in state["airbases"].items() if b.get("kind") == "carrier" and b.get("naval")}
    from . import i18n, i18n_en
    tr = i18n_en.en if i18n.lang(state) == "en" else (lambda x: x)   # английская миссия - имена кораблей и групп
    for u in naval.ships(state):
        lst = [(t, tr(n)) for t, n in naval.ship_names(u)]
        if not lst:
            continue
        pos = _pt(m, u["pos"])
        base = by_unit.get(u["id"])
        hdg = wind_from if base else (u.get("heading") or 0)
        sg = m.ship_group(_country(m, state, u["side"]), tr(u["name"]), getattr(_ships, lst[0][0]), pos, heading=hdg)
        sg.units[0].name = lst[0][1]
        for k, (typ, nm) in enumerate(lst[1:]):   # охранение - кольцом в 3-5 км (ОЦЕНКА)
            off = model.offset(u["pos"], hdg + 360 / max(1, len(lst) - 1) * k, 3000 + 1000 * (k % 2))
            sh = m.ship(nm, getattr(_ships, typ))
            q = _pt(m, off)
            sh.position = Point(q.x, q.y, m.terrain)
            sh.heading = hdg
            sg.add_unit(sh)
        kmh = CARRIER_KMH if base else (46 if naval.kind(u) == "FAC" else 19)
        for p_ in ship_route(state, u, hdg, bool(base)):
            sg.add_waypoint(_pt(m, p_), kmh)
        NAVAL_GROUPS[u["id"]] = sg
        NAVAL_SHIPS[u["id"]] = lst
        if base:
            bid, b = base
            sg.points[0].tasks.append(task.ActivateBeaconCommand(channel=int(b.get("tacan", 70)), modechannel="X",
                                                                 callsign=str(b.get("tacan_id", "CVN"))[:3], unit_id=sg.units[0].id,
                                                                 aa=False))
            if b.get("icls"):
                sg.points[0].tasks.append(task.ActivateICLSCommand(channel=int(b["icls"]), unit_id=sg.units[0].id))
            out[bid] = CarrierPad(sg, b)
    return out


SHIP_PATROL_M = 30_000   # ОЦЕНКА: галс патрулирования корабельной группы без приказа
PORT_STANDOFF_KM = 3     # ОЦЕНКА: конвой идёт к точке в стольких км от порта со стороны моря


def ship_route(state: dict, u: dict, hdg: float, carrier: bool) -> list[dict]:
    """Маршрут группы в миссии: авианосец - галсы против ветра; конвой - в порт назначения морского пути (sea_lanes);
    группа с приказом на сутки (orders) - к своей точке; остальные - патрулирование галсами вдоль позиции."""
    from . import naval
    pos = u["pos"]
    if carrier:
        leg = model.offset(pos, hdg, CARRIER_LEG_M)
        return [leg, pos, leg]
    lane = next((ln for ln in state.get("sea_lanes") or [] if ln.get("convoy") == u["id"]), None)
    if lane and lane.get("port") in state.get("places", {}):
        port = state["places"][lane["port"]]
        d = model.dist_km(pos, port)
        if d > PORT_STANDOFF_KM + 1:
            return [model.lerp(pos, port, 0.5), model.lerp(pos, port, 1 - PORT_STANDOFF_KM / d)]
    goal = naval.goal_today(state, u)
    if goal and model.dist_km(pos, goal) > 2:
        return [model.lerp(pos, goal, 0.5), dict(goal), model.offset(goal, hdg + 90, SHIP_PATROL_M / 2)]
    a = model.offset(pos, hdg + 90, SHIP_PATROL_M / 2)
    b = model.offset(pos, hdg - 90, SHIP_PATROL_M / 2)
    return [a, b, a, b]


def naval_manifest() -> list[dict]:
    """Корабли миссии для дебрифа: часть флота -> имена и типы кораблей."""
    return [{"unit": uid, "ships": [{"name": nm, "type": typ} for typ, nm in lst]} for uid, lst in NAVAL_SHIPS.items()]


BEACON_FILES = {"PersianGulf": "persiangulf", "Caucasus": "caucasus", "Syria": "syria", "GermanyCW": "germanycoldwar"}
_BEACONS: dict[str, dict] = {}


def navaid_lines(m: Mission, airport, lg: str) -> list[str]:
    """Радиосредства аэродрома для планшета: TACAN (канал), VOR/VORTAC, ILS (частота, позывной), РСБН (канал), ПРМГ,
    приводные (кГц). Данные - DCS Retribution, resources/dcs/beacons (LGPL-3.0); id маяков - airport.beacons (pydcs)."""
    if airport is None:
        return []
    key = BEACON_FILES.get(m.terrain.name)
    if not key:
        return []
    if key not in _BEACONS:
        try:
            _BEACONS[key] = model.load_json(f"beacons/{key}.json")
        except FileNotFoundError:
            _BEACONS[key] = {}
    db = _BEACONS[key]
    out = []
    seen = set()
    ids = [getattr(b, "id", "") for b in getattr(airport, "beacons", []) or []]
    ids += [k for k in db if k.startswith(f"airfield{airport.id}_") and k not in ids]   # ILS/ПРМГ - у полос, не в beacons
    for bid in sorted(ids, key=lambda k: (k.split("_")[0], int(k.split("_")[-1]) if k.split("_")[-1].isdigit() else 0)):
        x = db.get(bid)
        if not x:
            continue
        t, hz, ch, cs = x["beacon_type"], x.get("hertz") or 0, x.get("channel"), x.get("callsign", "")
        if t in (4, 5):
            s_ = f"TACAN {ch}X {cs}" + (" (VORTAC)" if t == 5 else "")
        elif t in (1, 3):
            s_ = f"VOR {hz / 1e6:.2f} {cs}"
        elif t == 16640:
            s_ = f"ILS {hz / 1e6:.2f} {cs}"
        elif t == 128:
            s_ = i18n.L(lg, f"РСБН канал {ch} {cs}", f"RSBN ch {ch} {cs}")
        elif t == 33024:
            s_ = i18n.L(lg, "ПРМГ " + (f"канал {ch} " if ch else "") + (f"{hz / 1e6:.2f} " if hz else "") + cs,
                        "PRMG " + (f"ch {ch} " if ch else "") + (f"{hz / 1e6:.2f} " if hz else "") + cs)
        elif t in (8, 4104, 4136, 16408, 16424):
            s_ = i18n.L(lg, f"привод {hz / 1e3:.0f} кГц {cs}", f"NDB {hz / 1e3:.0f} kHz {cs}")
        else:
            continue
        if s_ not in seen:
            seen.add(s_)
            out.append("  " + s_)
    return out


def carrier_lines(state: dict, side_pos=None) -> list[str]:
    """Строки брифинга и планшета: авианосцы кампании - TACAN, ICLS, частота (своей стороны)."""
    out = []
    for b in state["airbases"].values():
        if b.get("kind") == "carrier" and b.get("side") == state.get("player_side", "blue") and b.get("state") != "lost":
            out.append(f"{b['name']}: TACAN {b.get('tacan')}X {b.get('tacan_id', '')}"
                       + (f", ICLS {b['icls']}" if b.get("icls") else "") + f", {float(b.get('freq', 127.5)):.1f} МГц")
    return out


CARRIER_KMH = 46        # ОЦЕНКА: 25 узлов - ход авианосца при полётах (ветер над палубой)
CARRIER_LEG_M = 40_000  # ОЦЕНКА: длина галса


def _from_base(m: Mission, country, name: str, ac, base_obj, maintask, start_type, group_size: int):
    """Группа ЛА с аэродрома или с палубы авианосца (CarrierPad: старт с корабля; с полосы - с катапульты)."""
    if isinstance(base_obj, CarrierPad):
        st_ = StartType.Warm if start_type == StartType.Runway else start_type
        return m.flight_group_from_unit(country, name, ac, base_obj.group, maintask=maintask, start_type=st_,
                                        group_size=group_size)
    return m.flight_group_from_airport(country, name, ac, base_obj, maintask=maintask, start_type=start_type,
                                       group_size=group_size)


def _land(fg, airport, spd_kmh: float):
    """Посадка на аэродром или на палубу авианосца. pydcs ставит точке посадки скорость 0 - ИИ на последнем участке
    гасит скорость до минимума (Су-17 и др. на возврате шли 300-400 км/ч и крутили фигуры, сбрасывая её). Скорость -
    как на маршруте: заход и посадку ИИ строит сам."""
    if isinstance(airport, CarrierPad):
        from dcs.point import MovingPoint, PointProperties
        p = MovingPoint(airport.position)
        p.type, p.action, p.alt, p.ETA_locked = "Land", PointAction.Landing, 0, False
        p.helipad_id = p.link_unit = airport.unit.id
        p.properties = PointProperties()
        fg.add_point(p)
    else:
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
    "cap_own_troops": ["cap"], "qra": ["cap"], "fleet_cap": ["cap"], "strike_ship": ["antiship", "strike"],
}
GROUP_CATS = {"cover": ["escort", "cap"], "sead": ["sead"], "sead2": ["sead"], "kill": ["dead"], "escort": ["cas"], "helo": ["cas"], "sweep": ["cap"], "feint": ["cap", "escort"], "recon": ["bai", "cas"], "jam": ["jam"]}
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
    "antiship": ["Retribution Anti-ship", "Retribution Antiship", "ANTISHIP", "Anti-ship", "Retribution Strike", "STRIKE"],
}


def loadout_cats(kind: str, g: dict) -> list[str]:
    """Категории подвески группы по порядку: вид задачи (для ударной группы) или роль группы обеспечения, затем
    категории доктрины (loadout группы)."""
    gid = re.sub(r"\d+$", "", g.get("group", "")).split("_")[0]
    first = [] if g.get("loadout_user") else \
        GROUP_CATS.get(gid, []) if g.get("group") not in ("strike", "strike2") \
        else KIND_CATS.get(kind, [])
    # своя подвеска (payloads_custom.json) - и точнее категории: по задаче и группе ("strike_bridge", "strike_airfield/
    # cover", "sead"): сначала самая точная, затем роль группы, затем категория (масштабируется без кода)
    own = [] if g.get("loadout_user") else ([f"{kind}/{gid}", gid] if g.get("group") not in ("strike", "strike2") else [kind])
    out = []
    for c in own:
        if c not in out:
            out.append(c)
    for c in first + list(g.get("loadout") or []):
        if c not in out:
            out.append(c)
    return out


def _payload(ac, cat: str, year: int | None = None) -> tuple[str, dict] | None:
    """Подвеска для типа и категории: (имя, пилоны) или None. По порядку имён категории; при одном имени свои (payloads_custom.json) - раньше DCS
    Retribution; из подвесок категории - первая, где всё оружие есть на год кампании, иначе первая (по году её
    поправит weapons.degrade)."""
    from . import weapons
    found = []
    names = PAYLOAD_NAMES.get(cat, [])
    for f in ("payloads_custom.json", "payloads.json"):
        try:
            pls = model.load_json(f).get("types", {}).get(ac.id) or {}
        except FileNotFoundError:
            continue
        low = {k.lower(): k for k in pls}
        for name in PAYLOAD_NAMES.get(cat, []) + ([cat] if f == "payloads_custom.json" else []):
            k = low.get(name.lower())
            if k and year and pls[k].get("until") and year > pls[k]["until"]:
                continue                         # своя историческая подвеска - до года until (позже - подвеска Retribution)
            if k and pls[k]["pylons"] and (k, f) not in [(x[0], x[2]) for x in found]:
                found.append((k, pls[k]["pylons"], f))
    # порядок - по имени подвески категории, при одном имени своя - раньше Retribution: своя подвеска заменяет только
    # ту же (своя 'Strike' не перебивает противокорабельную Retribution с Harpoon)
    heads = {v[0].lower() for c, v in PAYLOAD_NAMES.items() if c != cat and v}
    own = set()                                  # свои имена категории - до первого имени, главного у другой категории
    for n in names:
        if n.lower() in heads:
            break
        own.add(n.lower())
    own.add(cat.lower())
    rank = {n.lower(): i for i, n in enumerate(names)}
    custom = lambda x: x[2] == "payloads_custom.json"
    found.sort(key=lambda x: (not (custom(x) and x[0].lower() in own), rank.get(x[0].lower(), len(names)), not custom(x)))
    if not found:
        return None
    k, pyl, _f = next((x for x in found if weapons.valid(x[1], year)), found[0])
    return k, pyl


def _arm_pylons(fg, ac, perf: dict, g: dict, state: dict) -> str | None:
    """ПРР на истребителе, у которого подвески ПРР в DCS нет (arm_pylons части: МиГ-29 и Су-27 ВСУ с AGM-88 с
    августа 2022, как F-4E с HARM на пилонах Shrike - weapons.SWAPS): группа подавления ПВО - подвеска прикрытия
    (ракеты воздух-воздух), на пилонах arm_pylons - HARM."""
    from . import weapons
    arm = perf.get("arm_pylons")
    if not arm or not (set(GROUP_CATS.get(re.sub(r"\d+$", "", g.get("group", "")).split("_")[0], [])) & {"sead"}):
        return None
    _apply_loadout(fg, ac, perf["type"], ["cap"], state)
    for u in fg.units:
        for n in arm["pylons"]:
            u.pylons[int(n)] = {"CLSID": weapons.HARM}
    return "SEAD (AGM-88 HARM)"


def _mun_swap(state: dict):
    """Замена управляемого оружия, которого нет в запасе (munitions.apply): по земле - неуправляемое того же пилона,
    ракета воздух-воздух с радиолокационным наведением - тепловая этого пилона, иначе - снять."""
    from . import munitions, weapons
    year = weapons.campaign_year(state) or 9999

    def swap(ac, num: int, name: str, cls: str):
        if cls == "aam_r":
            return next((w for w in weapons._pylon_options(ac, num) if munitions.classify(w["name"]) == "aam_ir"), None)
        if cls == "aam_ir":
            return None
        return weapons.dumb_substitute(ac, num, name, year)
    return swap


def _weapons_not(fg, perf: dict) -> None:
    """Вариант модели (F-16A на модели F-16C): оружие, которого у варианта не было (weapons_not - части имён
    оружия pydcs), снимается с пилонов."""
    import re as _re
    from dcs.weapons_data import weapon_ids
    pats = list(perf.get("weapons_not") or []) + model.variant(perf).get("weapons_not", [])
    if not pats:
        return
    rx = _re.compile("|".join(_re.escape(p) for p in pats), _re.I)
    for u in fg.units:
        for num in [n for n, d in u.pylons.items() if rx.search((weapon_ids.get(d.get("CLSID")) or {}).get("name", ""))]:
            del u.pylons[num]


def _apply_loadout(fg, ac, type_name: str, cats: list[str], state: dict | None = None) -> str | None:
    """Подвеска группы: первая категория, для которой есть подвеска по задачам DCS Retribution (payloads.json); затем -
    по году кампании (weapons.py: новее - замена своим по эпохе или снятие) и обязательные дополнения (weapons.fixups).
    Ничего - загрузка DCS по умолчанию для maintask (None)."""
    from . import weapons
    year = weapons.campaign_year(state) if state else None
    perf = ((state or {}).get("units") or {}).get(fg.name.split(" ")[0]) or {}
    ecm = perf.get("ecm_pods", True)             # часть летала с контейнерами РЭБ (нет - на их место ракета)
    for cat in cats:
        if cat.startswith(("rt:", "my:")):       # выбранная подвеска: по задаче (payloads.json) или своя (custom_loadouts)
            src = ((state or {}).get("custom_loadouts") or {}) if cat.startswith("my:") else model.load_json("payloads.json").get("types", {})
            pls = (src.get(ac.id) or {}).get(cat[3:])
            if pls is not None and (pls["pylons"] or cat.startswith("my:")):   # своя может быть и пустой (без подвески)
                for u in fg.units:
                    u.reset_loadout()
                    for num, d in pls["pylons"].items():
                        if int(num) in ac.pylons:
                            u.pylons[int(num)] = dict(d)
                weapons.degrade(fg, year, ecm)
                weapons.fixups(fg, year)
                _weapons_not(fg, perf)
                return cat[3:].replace("Retribution ", "")
    for cat in cats:
        pl = _payload(ac, cat, year)
        if pl:
            name, pylons = pl
            for u in fg.units:
                u.reset_loadout()
                for num, d in pylons.items():
                    if int(num) in ac.pylons:
                        u.pylons[int(num)] = dict(d)
            weapons.degrade(fg, year, ecm)
            weapons.fixups(fg, year)
            _weapons_not(fg, perf)
            return name.replace("Retribution ", "")   # подвеска - по функции (Strike, CAS, SEAD...)
    weapons.degrade(fg, year, ecm)
    _weapons_not(fg, perf)
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
        if i18n.lang(state) == "en":             # английская миссия: звание и фамилия латиницей (дебриф узнаёт и так)
            from . import i18n_en
            name = i18n_en.en(name)
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
RUNWAY_GAP_S = 30         # ОЦЕНКА: интервал взлёта групп ИИ с полосы одного аэродрома (если стоянок нет)
TAXI_S = 300              # ОЦЕНКА: с горячего старта на стоянке до взлёта (руление, выход на полосу)
AIR_START_MIN_M = 500      # ОЦЕНКА: высота появления группы, которая к началу миссии уже в воздухе
AI_LOW_MIN_M = 100         # ОЦЕНКА: точки маршрута групп ИИ не ниже этого (у игрока - как в доктрине, 50 м)
LOW_ENTRY_KM = 20         # ОЦЕНКА: группа подавления ПВО снижается до предельно малой за столько км до зоны ЗРК
SELF_DEFENSE_KM = 15       # ОЦЕНКА: группы ИИ (удар, подавление ПВО) вступают в бой с самолётами противника ближе (доктрина self_defense_km)
EGRESS_KM = 15             # ОЦЕНКА: точка ухода группы подавления ПВО - на столько км от рубежа пуска в сторону базы


def _ai_options(ai: dict) -> list:
    """Опции поведения ИИ из доктрины (поле ai у группы пакета)."""
    out = []
    if ai.get("react_on_threat"):
        out.append(task.OptReactOnThreat(getattr(task.OptReactOnThreat.Values, ai["react_on_threat"])))
    if ai.get("restrict_jettison"):
        out.append(task.OptRestrictJettison(True))
    return out


# Блок наведения AGM-45 Shrike (Heatblur F-4E: настройка NFP_rfgu_type) под РЛС цели: 1 Mk 22, 2 Mk 23, 3 Mk 24.5,
# 4 Mk 24.34, 5 Mk 25, 6 Mk 36, 7 Mk 37, 8 Mk 49.0, 9 Mk 49.1, 10 Mk 50. Источники: DCS Retribution, resources/weapons/
# standoff/AGM-45A.yaml (LGPL-3.0) - 2, 7, 9, 10; остальное - таблица головок руководства Heatblur F-4E (v3.10):
# РЛС, по которой у головки есть тон. Порядок - сверху вниз, первое совпадение типа РЛС.
SHRIKE_RFGU = [
    (r"snr s-125 tr|40B6M tr|30H6_tr|Kub.?1S91|RPC_5N62V|Osa.?9A33|Buk LN|Buk_LN|Buk SR|Buk_SR|Strela-10|Strela_10", 9),
    (r"Tor|Pantsir|Tunguska|SNR_75V|SNR-75|Patriot_str", 10),
    (r"64H6E|40B6MD|Tin Shield|Big Bird|SON_9|Gepard", 2),
    (r"p-19|P-19|Flat Face|Hawk_sr", 7),
    (r"Hawk_tr|Roland", 6),
    (r"Dog Ear|9S80|1L13|55G6", 1),
]


def tune_arm(state: dict, fg, g: dict) -> list[str]:
    """Головки Shrike группы - под РЛС её целей (ЗРК подавления, добивания, удара по ЗРК): у каждой ПРР - блок
    наведения по таблице SHRIKE_RFGU; несколько разных РЛС - по пилонам по очереди. Остальные ракеты и настройки
    подвески - как были. Возвращает строки 'РЛС -> блок' для брифинга."""
    import re as _re
    from . import weapons
    obj = g.get("objective") or {}
    sids = list(obj.get("units") or ([obj["unit"]] if obj.get("unit") else []))
    radars: list[str] = []
    for sid in sids:
        u = state["units"].get(sid)
        if not u or model.category(u) != "sam":
            continue
        comp = u.get("composition", [])
        rs = [c["type"] for c in comp if c.get("role") == "radar"] or [c["type"] for c in comp]
        tr = [t for t in rs if _re.search(r"tr\b|str|SNR|1S91|Hawk_tr|9A33|Buk LN|Tor|Tunguska", t, _re.I)] or rs
        radars += [t for t in tr if t not in radars]
    kits = []
    for t in radars:
        k = next((v for rx, v in SHRIKE_RFGU if _re.search(rx, t, _re.I)), None)
        if k and k not in kits:
            kits.append(k)
    if not kits:
        return []
    shrike = any(_re.search(r"AGM-45|Shrike", weapons.name_of(d.get("CLSID", "")), _re.I) for u in fg.units for d in u.pylons.values())
    if not shrike:                               # Shrike в подвеске нет - настраивать нечего (и в брифинг не писать)
        return []
    for u in fg.units:
        j = 0
        for num, d in list(u.pylons.items()):
            if _re.search(r"AGM-45|Shrike", weapons.name_of(d.get("CLSID", "")), _re.I):
                st = dict(d.get("settings") or {})
                st["NFP_rfgu_type"] = kits[j % len(kits)]
                d = dict(d, settings=st)
                u.pylons[num] = d
                j += 1
    names = {1: "Mk 22", 2: "Mk 23", 3: "Mk 24.5", 4: "Mk 24.34", 5: "Mk 25", 6: "Mk 36", 7: "Mk 37", 8: "Mk 49.0",
             9: "Mk 49.1", 10: "Mk 50"}
    note = "Shrike: " + ", ".join(names[k] for k in kits)
    fg.__dict__.setdefault("_rf_degraded", []).append(note)
    return [note]


def _attack(group_id: int, ai: dict, altitude: int | None = None):
    """AttackGroup с параметрами из доктрины: тип оружия, расход, атака всей группой, высота атаки (горка для пуска ПРР)."""
    a = ai.get("attack") or {}
    t = task.AttackGroup(group_id, weapon_type=getattr(task.WeaponType, a.get("weapon", "Auto")),
                         group_attack=bool(a.get("group_attack", False)), expend=getattr(task.Expend, a.get("expend", "Auto")),
                         altitude=altitude)
    # не больше ATTACK_PASSES заходов: группа не кружит над целью под огнём соседнего ЗРК, уходит по маршруту
    t.params["attackQtyLimit"], t.params["attackQty"] = True, int(a.get("passes", ATTACK_PASSES))
    return t


RV_FLAG = 9301          # флаг DCS: игрок пришёл на точку сбора пакета (rv.lua) - группы пакета уходят с круга
RV_WAIT_S = 600         # ОЦЕНКА: группы пакета ждут игрока на сборе не дольше (после своего времени сбора)
RV_NEAR_M = 8000        # ОЦЕНКА: игрок ближе к точке сбора - пакет собран
ALT_JITTER = 0.04         # ОЦЕНКА: разброс высоты группы от доктрины (+-4%: 3000 м - 2880..3120)
ALT_JITTER_MIN_M = 500    # ниже - без разброса (предельно малые высоты)
BARO_FROM_M = 1500        # ОЦЕНКА: точки выше - эшелон от уровня моря (BARO), ниже и у вертолётов - от земли (RADIO)
ATTACK_PASSES = 2      # ОЦЕНКА: заходов ИИ на цель (AttackGroup), затем - уход по маршруту
SEAD_AREA_KM = 20      # ОЦЕНКА: группы подавления после своих ЗРК - поиск и поражение любых РЛС ПВО в этом радиусе от цели пакета
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


SEAD_AREA_PRIORITY = 50   # приоритет DCS (меньше - важнее): запланированные ЗРК - 0, 1, 2... по плану, район - после них


def _sead_zone(m, state: dict, sid: str, prio: int = 0):
    """Нет свежих данных: поиск и поражение средств ПВО в районе, где ЗРК видели (EngageTargetsInZone, Air Defence).
    prio - место ЗРК в плане (0 - главная цель)."""
    u = state["units"][sid]
    c = _pt(m, intel.known_pos(state, u) or model.unit_pos(state, u))
    r = int((intel.unc_km(state, sid) + SEAD_SEARCH_KM) * 1000)
    t = task.EngageTargetsInZone(Vector2(c.x, c.y), r, [task.Targets.All.GroundUnits.AirDefence])
    t.params["priority"] = prio
    return t


def _sead_area(m, state: dict, g: dict, obj: dict):
    """Подавление в районе цели пакета: любые средства ПВО (РЛС ЗРК) ближе SEAD_AREA_KM - после назначенных ЗРК
    группа не слепнет к соседнему, который бьёт по ударной группе (en-route: действует, пока группа на рубеже)."""
    pts = [model.unit_pos(state, state["units"][sid]) for sid in obj["units"] if sid in state["units"]]
    c0 = pts[0] if pts else g["route"][0]
    c = _pt(m, {"lat": sum(p["lat"] for p in pts) / len(pts), "lon": sum(p["lon"] for p in pts) / len(pts)} if pts else c0)
    t = task.EngageTargetsInZone(Vector2(c.x, c.y), int(SEAD_AREA_KM * 1000), [task.Targets.All.GroundUnits.AirDefence])
    t.params["priority"] = SEAD_AREA_PRIORITY    # прочие РЛС ПВО - только после запланированных ЗРК
    return t


def _engage(group_id: int, ai: dict, altitude: int | None = None, prio: int = 1):
    """EngageGroup - задача 'по пути' (en-route): действует всё время, пока группа выполняет другие задачи точки
    (здесь - круг ожидания), в отличие от AttackGroup, которая заканчивается, если цель не обнаружена сразу.
    pydcs задаёт только groupId/weaponType; расход, атаку группой и высоту дописываем полями DCS (те же, что у
    AttackGroup; в DCS ещё не проверено)."""
    a = ai.get("attack") or {}
    t = task.EngageGroup(group_id)
    t.params["priority"] = prio                  # место цели в плане: 0 - главная (меньше - важнее)
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
            if take < 0:                         # в воздухе на пути к объекту - там, где по плану полётов
                _airborne(state, g, model.group_speed_kmh(state, g, tdg), -take)
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
                    _airborne(state, g2, model.group_speed_kmh(state, g2, tdg), -take)
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
    def is_alert(e):
        return e["task"]["package"][0]["objective"]["kind"] == "alert"
    def fits(e):                                 # лимит ЛА миссии: вылет - весь пакет (оценка сверху), иначе не ставится;
        if is_alert(e):                          # дежурные звенья - вне лимита: в мире DCS их нет до тревоги (qra.lua),
            return True                          # поднимаются по налёту, часть остаётся в резерве
        pk = e["task"]["package"]
        return not cap or air[0] + sum(g["size"] for g in (pk[:1] if e["ai_only"] else pk)) <= cap
    for e in cands:
        k = add(e) if fits(e) else 0
        air[0] += 0 if is_alert(e) else k
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
            air[0] += 0 if is_alert(e) else k
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


PLAYER_AWACS_STANDOFF_KM = 150   # ОЦЕНКА: зона E-2C игрока - за серединой фронта, как у ДРЛО доктрины НАТО


PLAYER_VARIANTS = {   # тип полка в сценарии (только ИИ в DCS) -> управляемая версия для группы игрока; (тип, мод или None)
    "AH_64A": ("AH_64D_BLK_II", None),
    "UH_60A": ("UH_60L", "uh60l"),
}


def player_variant(state: dict, type_name: str) -> str | None:
    """Игровое допущение: полк в сценарии на типе только для ИИ (AH-64A) - группа игрока летит на управляемой версии
    (AH-64D); ИИ и модель - на типе сценария. Мод версии (UH-60L) - только если он включён в кампании.
    Выключение - settings.player_variants = False."""
    if not (state.get("settings") or {}).get("player_variants", True):
        return None
    v = PLAYER_VARIANTS.get(type_name)
    if not v:
        return None
    pv, mod = v
    if mod and mod not in ((state.get("settings") or {}).get("mods") or []):
        return None
    return pv


def external_awacs(m: Mission, state: dict, tk: dict, sortie: int) -> list[str]:
    """ДРЛО извне театра (сценарий: external_awacs стороны): самолёт третьей стороны, не с аэродрома театра - в
    воздухе с начала миссии на standoff_km за фронтом своей стороны (ДРЛО НАТО E-3A над Польшей и Румынией - для ВСУ;
    на условной карте - за тылом своей стороны).
    Сбить его противник не может (вне театра, политически), поэтому бессмертный и невидимый; не часть модели - не
    цель, не потеря, не исполнитель задач. Картину ИИ своей стороны DCS видит, игроку - по радио (меню AWACS)."""
    out = []
    from dcs import planes as _planes
    for side, c in sorted((state.get("external_awacs") or {}).items()):
        pos = planner.orbit_point(state, side, c.get("standoff_km", 250))
        if pos is None:
            continue
        ac = getattr(_planes, c.get("type", "E_3A"))
        alt, spd = int(c.get("alt_m", 9000)), 600
        p = _pt(m, pos)
        fg = m.flight_group_inflight(_country(m, state, side), f"ext awacs {side} {sortie}", ac, p, alt,
                                     speed=spd, maintask=task.AWACS, group_size=1)
        w = fg.points[0]
        if not any(isinstance(t_, task.AWACSTaskAction) for t_ in w.tasks):
            w.tasks.append(task.AWACSTaskAction())
        w.tasks += [task.SetImmortalCommand(True), task.SetInvisibleCommand(True)]
        w.tasks.append(task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.RaceTrack)))
        fg.add_waypoint(Point(p.x, p.y + 60_000, m.terrain), alt, speed=spd)
        if side == tk["side"]:
            t = c.get("title", "ДРЛО извне театра")
            out.append(i18n.L(i18n.lang(state), f"{t}: вне театра, в воздухе с начала миссии - картина по радио (AWACS); "
                                                  "противник его не атакует",
                              f"{i18n.tr(t, 'en')}: outside the theatre, airborne from mission start - picture by radio "
                              "(AWACS); the enemy does not attack it"))
    return out


def player_awacs(m: Mission, state: dict, tk: dict, sortie: int) -> str | None:
    """Игровое допущение: у стороны игрока нет ДРЛО в миссии (Израиль 1973, ВВС ДРВ...) - E-2C над своей территорией
    до конца миссии, бессмертный и невидимый для противника (его нет в истории: не цель, не потеря). Через него игрок
    получает картину по радио (AWACS в меню связи); ИИ своей стороны DCS его данные тоже видит. Отключение -
    settings.player_awacs = False."""
    if not (state.get("settings") or {}).get("player_awacs", True):
        return None
    side = tk["side"]
    for c in m.coalition[side].countries.values():
        for grp in c.plane_group:
            if "awacs" in grp.name or any(getattr(u.unit_type, "id", "") in ("E-2C", "E-3A", "A-50", "KJ-2000") for u in grp.units):
                return None
    pos = planner.orbit_point(state, side, PLAYER_AWACS_STANDOFF_KM)
    if pos is None:
        return None
    from dcs import planes as _planes
    alt, spd = 8000, 500
    p = _pt(m, pos)
    ac = _planes.E_2C if side == "blue" else _planes.A_50          # красным - А-50 (Ту-126 в DCS нет)
    fg = m.flight_group_inflight(_country(m, state, side), f"player awacs {sortie}", ac, p, alt,
                                 speed=spd, maintask=task.AWACS, group_size=1)
    w = fg.points[0]
    if not any(isinstance(t_, task.AWACSTaskAction) for t_ in w.tasks):
        w.tasks.append(task.AWACSTaskAction())
    w.tasks += [task.SetImmortalCommand(True), task.SetInvisibleCommand(True)]
    w.tasks.append(task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.RaceTrack)))
    fg.add_waypoint(Point(p.x + 40_000, p.y, m.terrain), alt, speed=spd)
    return i18n.L(i18n.lang(state),
                  ("ДРЛО E-2C" if side == "blue" else "ДРЛО А-50") + " над своей территорией - игровое допущение (у стороны в этой войне ДРЛО не было): "
                  "картина по радио, бессмертный, противник его не видит",
                  ("E-2C" if side == "blue" else "A-50") + " AWACS over friendly territory - a gameplay concession (this side had no AWACS in this war): "
                  "picture by radio, immortal, invisible to the enemy")


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
               wx_text: str, lg: str, times_player: dict | None = None) -> int:
    """Наколенный планшет ЛА игрока (kneeboard.py) - тактическая карточка вылета: главное крупно и в рамках (время,
    цель и угрозы, звено, связь, погода, навигация), маршрут - таблицей, остальной пакет и подробности - в конце."""
    from . import kneeboard, weapons
    L = lambda ru, en: i18n.L(lg, ru, en)
    hhmm = lambda s: (m.start_time + datetime.timedelta(seconds=int(s))).strftime("%H:%M")
    side = tk["side"]
    groups, seen = [], set()
    for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values()):
        for fg in list(c.plane_group) + list(c.helicopter_group):
            if not any(u.skill in (Skill.Client, Skill.Player) for u in fg.units):
                continue
            ut = fg.units[0].unit_type
            if (ut.id, fg.name) in seen:
                continue
            seen.add((ut.id, fg.name))
            tp = times_player or {}
            # ---- маршрут: время точек - заданное (ETA), иначе по участкам; опорные - по плану пакета ----
            t_off = float(tp.get("takeoff_s", 0))
            route, t, prev, obj_done = [], max(float(getattr(fg.points[0], "ETA", 0) or 0), t_off), None, False
            for i, pt in enumerate(fg.points):
                if prev is not None:
                    eta = float(getattr(pt, "ETA", 0) or 0)
                    t = eta if getattr(pt, "ETA_locked", False) and eta else t + prev.position.distance_to_point(pt.position) / max(pt.speed or 150.0, 30.0)
                prev = pt
                key = False
                if tp and i > 0:
                    if pt.name in ("Сбор", "Rendezvous") and tp.get("rv_s") is not None:
                        t, key = float(tp["rv_s"]), True
                    elif (pt.name in ("Цель", "Target", "Рубеж атаки", "Attack line", "Рубеж пуска", "Launch line")
                          and tp.get("objective_s") and not obj_done):
                        t, obj_done, key = float(tp["objective_s"]), True, True
                ref = (" AGL" if getattr(pt, "alt_type", "BARO") == "RADIO" else "") if pt.alt else ""
                nm_ = pt.name or (L("Взлёт", "Takeoff") if i == 0 else
                                  L("Посадка", "Landing") if i == len(fg.points) - 1 else "")
                alt_ = (fmt_alt(state, side, pt.alt, lg, ut.id).strip() + ref) if pt.alt else ""
                spd_ = fmt_spd(state, side, (pt.speed or 0) * 3.6, lg, ut.id) if i > 0 and pt.speed else ""
                route.append(("!" if key else "") + "  ".join(x for x in (f"{i}. {nm_}", alt_, hhmm(t), spd_) if x))
            # ---- аэродромы и навигация ----
            ab = [pt.airdrome_id for pt in fg.points if getattr(pt, "airdrome_id", None)]
            names = {a.id: a.name for a in m.terrain.airports.values()}
            by_id = {a.id: a for a in m.terrain.airports.values()}
            nav = []
            if ab:
                nav += ["*" + L("ВЗЛЁТ: ", "DEP: ") + names.get(ab[0], "-")] + [x.strip() for x in navaid_lines(m, by_id.get(ab[0]), lg)]
                if ab[-1] != ab[0]:
                    nav += ["*" + L("ПОСАДКА: ", "ARR: ") + names.get(ab[-1], "-")] + [x.strip() for x in navaid_lines(m, by_id.get(ab[-1]), lg)]
                else:
                    nav.append(L("Посадка - там же", "Arrival - same field"))
            else:
                nav.append(L("Взлёт и посадка - палуба", "Deck launch and recovery"))
            nav += carrier_lines(state, fg.units[0].position)
            # ---- звено: позывной, тип, подвеска, старт ----
            cs = _callsign(fg.units[0]) or fg.name
            loads: dict[str, int] = {}
            for d_ in fg.units[0].pylons.values():
                n_ = weapons.name_of(d_.get("CLSID", "")).split(" - ")[0].strip()
                if n_:
                    loads[n_] = loads.get(n_, 0) + 1
            start = {"cold": L("холодный на стоянке", "cold, ramp"), "hot": L("горячий на стоянке", "hot, ramp"),
                     "runway": L("с полосы", "runway"), "air": L("в воздухе", "airborne")}[player_start(state)]
            flight = ["*" + f"{cs}  {ut.id} x{len(fg.units)}", L("Старт: ", "Start: ") + start] + \
                     [f"{v} x {k}" for k, v in sorted(loads.items(), key=lambda x: -x[1])]
            own_call = []
            # ---- цель и угрозы ----
            tpos = tk.get("target_pos") or {}
            tgt = ["*" + i18n.tr(natonames.text(state, model.enemy(side), tk["title"], side), lg)]
            if tpos:
                tgt.append(_dms(tpos["lat"], "NS") + "  " + _dms(tpos["lon"], "EW"))
            tgt.append(L("Удаление ", "Distance ") + fmt_dist(state, side, tk["distance_km"], lg, ut.id))
            def _short(n_: str) -> str:              # 'ЗРК средней дальности (Gotha): SA-2' -> 'SA-2 (Gotha)'
                if ": " not in n_:
                    return n_
                head_, tail_ = n_.rsplit(": ", 1)
                pl_ = re.search(r"\(([^)]*)\)", head_)
                if head_.startswith(("Войсковая ПВО", "Organic air defence")):
                    return L("ПВО ", "AD ") + tail_
                return f"{tail_} ({pl_.group(1)})" if pl_ else f"{tail_} - {head_}"
            thr_all = [_short(natonames.name(state, state["units"][x], side)) for x in tk["threats"]]
            thr = ["!" + x for x in thr_all[:6]] + ([L(f"и ещё {len(thr_all) - 6}", f"and {len(thr_all) - 6} more")]
                                                    if len(thr_all) > 6 else []) or [L("не выявлены", "none detected")]
            # ---- связь: каналы своего вылета; позывные остальных групп - на последний лист ----
            comm_main = [x for x in comm_lines if " - позывной " not in x and " - callsign " not in x]
            calls = [x for x in comm_lines if x not in comm_main]
            comm_rows = []
            for x in comm_main:
                if ": " in x:
                    k_, v_ = x.split(": ", 1)
                    comm_rows.append(["*" + k_ if "тактич" in k_ or "package" in k_.lower() else k_, v_])
                else:
                    own_call.append(x)               # примечание (каналы вручную) - в рамку звена
            # ---- погода: METAR и главное ----
            wx = [x for x in wx_text.split("\n") if x.strip()]
            wx_main = (["*" + wx[0]] if wx else []) + kb_weather(state, ut.id, lg, m.start_time.hour + m.start_time.minute / 60)
            # ---- время вылета ----
            cells = []
            if tp:
                cells.append((L("ЗАПУСК", "START"), hhmm(0)))
                cells.append((L("ВЗЛЁТ", "TAKEOFF"), hhmm(tp["takeoff_s"])))
                if tp.get("rv_s") is not None:
                    cells.append((L("СБОР", "PUSH/RV"), hhmm(tp["rv_s"])))
                cells.append((L("НА ЦЕЛИ (TOT)", "TOT"), hhmm(tp["objective_s"])))
            sub = f"{cs} | {ut.id} x{len(fg.units)} | {L('день', 'day')} {state['day']}, {m.start_time:%d.%m.%Y}"
            p1 = L("КАРТОЧКА ВЫЛЕТА", "MISSION CARD")
            card = {"lg": lg, "sub": sub, "pages": [
                {"title": p1, "items": [
                    ("times", cells),
                    ("boxes", [(L("ЦЕЛЬ", "TARGET"), tgt), (L("УГРОЗЫ", "THREATS"), thr)], [0.55, 0.45]),
                    ("table", L("СВЯЗЬ", "COMMS"), [(L("сеть", "net"), 0.42), (L("частоты", "frequencies"), 0.58)], comm_rows),
                    ("boxes", [(L("ЗВЕНО", "FLIGHT"), flight + own_call), (L("НАВИГАЦИЯ", "NAVIGATION"), nav)]),
                    ("boxes", [(L("ПОГОДА", "WEATHER"), wx_main)]),
                ]},
                {"title": L("МАРШРУТ", "ROUTE"), "items": [
                    ("boxes", [(L("ППМ: номер, точка, высота, время, скорость", "Waypoints: no., point, altitude, time, speed"), route)]),
                    ("boxes", [(L("ПОРЯДОК ДЕЙСТВИЙ ПАКЕТА", "PACKAGE SEQUENCE"), order_lines or ["-"])]),
                ]},
                {"title": L("ПАКЕТ И ОБСТАНОВКА", "PACKAGE AND SITUATION"), "items": [
                    ("boxes", [(L("Группы пакета", "Package flights"), lines or ["-"])]),
                    ("boxes", [(L("Позывные групп", "Flight callsigns"), calls or ["-"])]),
                    ("boxes", [(L("Погода полностью", "Full weather"), wx or ["-"])]),
                ]},
            ]}
            groups.append({"type": ut, "card": card})
    return kneeboard.build(m, lg, groups)


FT, KT, NM = 0.3048, 1.852, 1.852   # м в футе, км/ч в узле, км в морской миле
HPA_MMHG, HPA_INHG = 0.750062, 0.0295300   # гПа -> мм рт. ст., дюймы рт. ст.


def kb_weather(state: dict, ac: str, lg: str, hour: float) -> list[str]:
    """Погода на планшет - в единицах кабины ЛА игрока: советские типы - давление в мм рт. ст., ветер м/с, облака в м;
    западные - inHg, узлы, футы. Давление - первым (выставить высотомер)."""
    from . import weather
    w = weather.day(state)
    h = weather.at_hour(w, hour)
    base = weather.cloud_base(w)
    L = lambda ru, en: i18n.L(lg, ru, en)
    if imperial(state, "", ac):
        out = [f"QNH {w['qnh_hpa'] * HPA_INHG:.2f} inHg ({w['qnh_hpa']} hPa)",
               L(f"ветер {w['wind_dir']:03d}° {w['wind_mps'] * 1.944:.0f} уз (на 6500 фт - {w['wind_mps'] * 1.8 * 1.944:.0f})",
                 f"wind {w['wind_dir']:03d}° {w['wind_mps'] * 1.944:.0f} kt (at 6500 ft - {w['wind_mps'] * 1.8 * 1.944:.0f})"),
               (L(f"облачность {weather.cover(w)}, нижняя граница {round(base / FT, -2):.0f} фт", f"clouds {weather.cover(w)}, base {round(base / FT, -2):.0f} ft")
                if base else L("ясно", "clear sky"))]
    else:
        out = [L(f"QNH {w['qnh_hpa'] * HPA_MMHG:.0f} мм рт. ст. ({w['qnh_hpa']} гПа)", f"QNH {w['qnh_hpa'] * HPA_MMHG:.0f} mmHg ({w['qnh_hpa']} hPa)"),
               L(f"ветер {w['wind_dir']:03d}° {w['wind_mps']:.0f} м/с (на 2000 м - {w['wind_mps'] * 1.8:.0f})",
                 f"wind {w['wind_dir']:03d}° {w['wind_mps']:.0f} m/s (at 2000 m - {w['wind_mps'] * 1.8:.0f})"),
               (L(f"облачность {weather.cover(w)}, нижняя граница {base} м", f"clouds {weather.cover(w)}, base {base} m")
                if base else L("ясно", "clear sky"))]
    vis = (L(f"туман, видимость {w['fog_vis_m']} м", f"fog, visibility {w['fog_vis_m']} m") if h["fog"]
           else L(f"видимость {w['vis_km']} км", f"visibility {w['vis_km']} km"))
    return out + [vis + (L(", дождь", ", rain") if w["rain"] else "") + f", {h['temp_c']}°C"]


METRIC_COCKPIT_RX = r"^(MiG|Su-|Mi-|Ka-|Yak|L-39|Tu-|Il-|An-)"   # советская школа: метры, км/ч, км, мм рт. ст.


def imperial(state: dict, side: str, ac: str | None = None) -> bool:
    """ac - тип ЛА игрока: единицы - по его кабине (советские типы - метрические, западные - футы, узлы, мили, inHg)."""
    if ac:
        return not re.match(METRIC_COCKPIT_RX, ac)
    return _imperial_side(state, side)


def _imperial_side(state: dict, side: str) -> bool:
    """Единицы стороны (доктрина units): imperial - футы, узлы, мили (НАТО, США, Израиль); metric - метры, км/ч (ОВД)."""
    return model.doctrine(state, side).get("units", "metric") == "imperial"


def q_alt(state: dict, side: str, alt_m: float) -> float:
    """Высота точки - круглым числом в единицах стороны: футы - по 100 до 1000, по 500 до 10 000, выше по 1000;
    метры - по 10 до 300, по 50 до 1000, выше по 100."""
    if alt_m <= 0:
        return alt_m
    if imperial(state, side):
        ft = alt_m / FT
        step = 100 if ft < 1000 else 500 if ft < 10000 else 1000
        return round(max(step, round(ft / step) * step) * FT, 1)
    step = 10 if alt_m < 300 else 50 if alt_m < 1000 else 100
    return float(max(step, round(alt_m / step) * step))


def q_spd(state: dict, side: str, kmh: float) -> float:
    """Скорость - узлы по 10 (НАТО) или км/ч по 50 (ОВД)."""
    if imperial(state, side):
        return round(round(kmh / KT / 10) * 10 * KT, 1)
    return float(round(kmh / 50) * 50)


def fmt_alt(state: dict, side: str, alt_m: float, lg: str, ac: str | None = None) -> str:
    if imperial(state, side, ac):
        return f"{alt_m / FT:>6.0f} " + i18n.L(lg, "фт", "ft")
    return f"{alt_m:>6.0f} " + i18n.L(lg, "м", "m")


def fmt_dist(state: dict, side: str, km: float, lg: str, ac: str | None = None) -> str:
    if imperial(state, side, ac):
        return f"{km / NM:.0f} " + i18n.L(lg, "миль", "NM")
    return f"{km:.0f} " + i18n.L(lg, "км", "km")


def fmt_spd(state: dict, side: str, kmh: float, lg: str, ac: str | None = None) -> str:
    if imperial(state, side, ac):
        return f"{kmh / KT:.0f} " + i18n.L(lg, "уз", "kt")
    return f"{kmh:.0f} " + i18n.L(lg, "км/ч", "km/h")


def _dms(v: float, hemi: str) -> str:
    h = hemi[0] if v >= 0 else hemi[1]
    v = abs(v)
    d = int(v)
    mnt = (v - d) * 60
    return f"{h}{d:02d}°{mnt:06.3f}'"


def package_order(pkg: list[dict], times: dict, lg: str = "ru", clk=None) -> list[str]:
    """Брифинг: сбор пакета (место, время каждой группы) и порядок выхода на объекты - время и относительно удара
    (T0 - время удара ударной группы). clk(с от начала миссии) -> 'ЧЧ:ММ'."""
    out = []
    clk = clk or (lambda s_: f"+{int(s_) // 60}")
    rv = [g for g in pkg if g.get("rv") and g["group"] in times and times[g["group"]].get("rv_s") is not None]
    if rv:
        out.append(i18n.L(lg, "Сбор (точка маршрута \"Сбор\"): ", "Rendezvous (waypoint \"Rendezvous\"): ") + "; ".join(
            f"{i18n.tr(g['title'], lg)} - {clk(times[g['group']]['rv_s'])}" for g in sorted(rv, key=lambda g: times[g["group"]]["rv_s"])))
    if len(pkg) > 1 and "strike" in times:
        t0 = times["strike"]["objective_s"]
        seq = sorted((g for g in pkg if g["group"] in times), key=lambda g: times[g["group"]]["objective_s"])
        out.append(i18n.L(lg, "Выход на объекты: ", "Push to objectives: ") + ", ".join(
            f"{i18n.tr(g['title'], lg)} " + (f"T0{(times[g['group']]['objective_s'] - t0) // 60:+d}" if times[g['group']]['objective_s'] != t0 else "T0")
            + f" ({clk(times[g['group']]['objective_s'])})" for g in seq)
            + i18n.L(lg, f" - T0 = {clk(t0)}", f" - T0 = {clk(t0)}"))
    return out


ETA_POINTS = ("ИПМ", "Рубеж пуска", "Рубеж атаки", "Зона прикрытия", "Зона расчистки", "Зона постановки помех", "Демонстрация", "Район поиска",
              "Площадка", "Экипаж", "Зона дежурства")   # точки, к которым группа ИИ выходит ко времени


def _lock_eta(fg, objective_s: float, spd_kmh: float) -> dict | None:
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
                return {"group": fg.name, "x": w.position.x, "y": w.position.y, "eta": int(eta)}   # проверка (timing.lua)
            return None
    return None


CRAWL_S = 60          # ОЦЕНКА: группа приходит на точку раньше залоченного времени больше чем на столько - ждёт в круге


def _no_crawl(fg, spd_kmh: float) -> None:
    """Залоченное время точки (ETA) раньше, чем группа долетит своей скоростью, DCS выполняет, замедляя группу
    до 150-250 км/ч (мираж на 154 км/ч, 'Хьюи' на 76). Вместо этого: скорость - своя (speed_locked), на точке -
    круг ожидания до её времени; точка ждёт, а не маршрут ползёт. Позже - ETA остаётся (DCS ускорится)."""
    pts = fg.points
    if not pts:
        return
    t = float(getattr(fg, "start_time", 0) or 0) + float(getattr(pts[0], "ETA", 0) or 0)
    v = max(spd_kmh / 3.6, 15.0)
    for i in range(1, len(pts)):
        w, prev = pts[i], pts[i - 1]
        t_nat = t + prev.position.distance_to_point(w.position) / v
        if getattr(w, "ETA_locked", False) and w.ETA and w.ETA > t_nat + CRAWL_S:
            w.ETA_locked, w.speed_locked, w.speed = False, True, v
            if not any(getattr(x, "id", None) == "ControlledTask" and "Orbit" in str(getattr(x, "params", {}))
                       for x in w.tasks):
                hold = task.ControlledTask(task.OrbitAction(altitude=int(w.alt or 1000), speed=int(spd_kmh),
                                                            pattern=task.OrbitAction.OrbitPattern.Circle))
                hold.stop_after_time(int(w.ETA))
                w.tasks.insert(0, hold)
            t = float(w.ETA)
        else:
            t = max(t_nat, float(w.ETA or 0)) if getattr(w, "ETA_locked", False) else t_nat


def _airborne(state: dict, g: dict, spd_kmh: float, secs: float) -> bool:
    """Группа ИИ, взлетевшая по плану за secs до начала миссии, - в воздухе там, где она к этому времени (как в Falcon
    BMS: миссия начинается со взлёта игрока, остальные вылеты пакета и плана - уже в пути). Точка - по маршруту база -
    сбор - первая точка маршрута (за вычетом разбега и сбора; не дальше неё - задачу группы не срезаем). g меняется на
    месте (_air_start, rv). False - ещё на земле (взлетит с началом миссии)."""
    km = (secs - ato.AI_TAKEOFF_S) * spd_kmh / 3600
    if km <= 3:
        return False
    rv_ok = g.get("rv") and g["objective"]["kind"] in planner.RV_KINDS
    pts = [state["airbases"][g["base"]]] + ([g["rv"]] if rv_ok else []) + list(g["route"][:1])
    total = sum(model.dist_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    km = min(km, max(0.0, total - 3))            # не дальше первой точки маршрута (ИПМ, зона, рубеж - задача группы)
    run = 0.0
    for i in range(len(pts) - 1):
        leg = model.dist_km(pts[i], pts[i + 1])
        if run + leg >= km or i == len(pts) - 2:
            g["_air_start"] = model.lerp(pts[i], pts[i + 1], min(1.0, (km - run) / leg) if leg else 1.0)
            if rv_ok and i >= 1:                 # сбор пройден - его в маршруте нет
                g.pop("rv", None)
            return True
        run += leg
    return False


JOIN_MIN = 2     # ОЦЕНКА: сбор группы игрока после взлёта (вираж над аэродромом)


PLAYER_TAKEOFF_MIN = 15   # от начала миссии до взлёта игрока (запуск, руление), мин - настройка player_takeoff_min


def player_takeoff_s(state: dict, tdef: dict, groups: list[dict], fly: str, join: bool = True) -> int:
    """Взлёт группы игрока от начала миссии, с: настройка игрока (settings.player_takeoff_min - запуск и руление,
    по умолчанию PLAYER_TAKEOFF_MIN) + сбор группы (JOIN_MIN)."""
    mins = (state.get("settings") or {}).get("player_takeoff_min")
    if mins is None:
        mins = PLAYER_TAKEOFF_MIN
    start = player_start(state)
    if start != "cold":                          # горячий старт - руление; с полосы - сразу; в воздухе - уже взлетел
        mins = min(float(mins), PLAYER_START_MIN[start])
    return int((float(mins) + (JOIN_MIN if join else 0)) * 60)


PLAYER_STARTS = ("cold", "hot", "runway", "air")
PLAYER_START_MIN = {"hot": 4, "runway": 1, "air": 0}   # ОЦЕНКА: минут до взлёта при старте не с холодной стоянки
PLAYER_AIR_START_KM = 5                                # старт в воздухе - над аэродромом вылета, по пути к маршруту


def player_start(state: dict) -> str:
    """Старт игрока (настройка player_start): cold - холодный на стоянке, hot - горячий на стоянке, runway - с полосы,
    air - в воздухе над аэродромом вылета."""
    s = (state.get("settings") or {}).get("player_start", "cold")
    return s if s in PLAYER_STARTS else "cold"


def timeline(tdef: dict, state: dict, groups: list[dict], fly: str) -> dict[str, dict]:
    """Задержки взлёта групп пакета. Опорная - группа игрока: холодный старт (timing.player_cold_start_min, ОЦЕНКА)
    плюс полёт до объекта. Группа обеспечения выходит на свой объект за lead_min до выхода ударной группы на цель
    (ОЦЕНКИ из доктрины). Группы ИИ взлетают с полосы с задержкой start_s; если не успевают - late_s > 0."""
    fly_s = {g["group"]: _path_km(state["airbases"][g["base"]], planner.route_points(g)) * 1000 / (model.group_speed_kmh(state, g, tdef) / 3.6)
             + (0 if g["group"] == fly else ato.AI_TAKEOFF_S) for g in groups}   # скорость задачи доктрины; ИИ - разбег и сбор
    lead = {g["group"]: g.get("lead_min", 0) * 60 for g in groups}
    t_player = player_takeoff_s(state, tdef, groups, fly) + fly_s[fly]
    eta_strike = t_player + lead[fly]
    # миссия начинается с холодного старта игрока (как в Falcon BMS и Liberation: время на цели - по плану, группа
    # игрока - с земли); группы ИИ, которым по плану взлетать раньше начала миссии, к её началу уже в воздухе на своём
    # маршруте (air_s - сколько они уже летят, build._airborne), а не стартуют все с земли и опаздывают
    out = {}
    for g in groups:
        k = g["group"]
        start = eta_strike - lead[k] - fly_s[k]
        out[k] = {"start_s": 0 if k == fly else max(0, int(start)), "late_s": 0,
                  "air_s": 0 if k == fly else max(0, int(-start)), "objective_s": int(eta_strike - lead[k])}
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

    m = Mission(model.terrain_class(state)())
    set_airbase_coalitions(m, state)
    y, mo, d = map(int, state["date"].split("-"))
    start = datetime.datetime(y, mo, d, state["start_hour"], 0) + datetime.timedelta(days=state["day"] - 1)
    m.start_time = start
    from . import weather as wx_mod
    wx_now = wx_mod.apply(m, state, state["start_hour"])                  # погода суток (weather.py)

    # ---- весь театр: район задачи подробно, остальное - реже ----
    carriers = carrier_groups(m, state, (wx_now.get("wind_dir") or 0) % 360)   # авианосные группы - базы на море
    groups = materialize.theatre(state, tk, density)
    vg_by_unit, platoons = {}, {}
    col_parts: dict[int, list] = {}               # колонна ротами: id(группы модели) -> [(часть, группа DCS)]
    mrl_used: dict[str, bool] = {}              # РСЗО в миссии - одна на сторону (build, огонь батарей)
    rv_wait: list[dict] = []                     # точки сбора, где группы пакета ждут игрока (rv.lua)
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
        if g["kind"] == "artillery":             # батарея части в бою: огневые налёты по машинам противника в этом бою
            vg = _ground_group(m, state, g, shift_of(g))
            gp = _pt(m, g["vehicles"][len(g["vehicles"]) // 2])
            sx0, sy0 = shift_of(g)
            near_player = model.dist_km(g["vehicles"][0], tk["target_pos"]) <= ARTY_ACTIVE_KM if tk.get("target_pos") else True
            if g.get("mrl"):                     # РСЗО: одна на сторону в миссии (300 ракет разом - не реализм и не FPS)
                near_player = near_player and not mrl_used.get(g["side"])
            if not near_player:                  # вдали от вылета игрока - батарея стоит (цель), огонь - в модели
                continue
            own_b = next((b for b in groups if b["kind"] == "battle" and b["unit"] == g["unit"]), None)
            engaged = set(g.get("engaged") or (own_b or {}).get("engaged") or [])
            foes = [b for b in groups if b["kind"] == "battle" and b["unit"] in engaged and b["side"] != g["side"]]
            aims = []                            # точки налётов - машины противника (с его сдвигом позиции), а не середина линии
            if g.get("target") == "counterbattery":  # РСЗО НАТО: по огневым позициям артиллерии противника в этом бою
                foe = next((a for a in arts if not a.get("mrl") and a["unit"] in engaged), None)
                if foe:
                    fx, fy = shift_of(foe)
                    q = _pt(m, foe["vehicles"][len(foe["vehicles"]) // 2])
                    aims = [(q.x + fx, q.y + fy)]
            if not aims:
                for b in foes:
                    bx, by = shift_of(b)
                    for v in b["vehicles"][::max(1, len(b["vehicles"]) // 4)]:
                        q = _pt(m, v)
                        aims.append((q.x + bx, q.y + by))
            if not aims:
                c = _pt(m, g["fire_at"])
                aims = [(c.x + sx0, c.y + sy0)]
            aims.sort(key=lambda a: (a[0] - gp.x) ** 2 + (a[1] - gp.y) ** 2)   # ближние к батарее - первыми
            n_m = int(g.get("missions", ART_MISSIONS))
            rounds = int(g.get("rounds", ART_ROUNDS))
            if g.get("mrl"):
                mrl_used[g["side"]] = True
                n_m, rounds = 1, min(rounds, MRL_MAX_ROUNDS)
            for k in range(n_m):                 # налёты подряд - по разным машинам противника
                ax, ay = aims[k % len(aims)]
                vg.points[0].tasks.append(task.FireAtPoint(Vector2(ax, ay), rounds=rounds,
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
            pks = sorted({v.get("packet", 0) for v in g["vehicles"]}) if g["kind"] == "column" else []
            if len(pks) > 1:                     # длинная колонна - пакетами (роты): отдельные группы держат разрывы
                parts = [dict(g, name=f"{g['name']} c{k + 1}", vehicles=[v for v in g["vehicles"] if v.get("packet", 0) == k])
                         for k in pks]
                col_parts[id(g)] = [(p_, _ground_group(m, state, p_, shift_of(g))) for p_ in parts]
                vg_by_unit[g["unit"]] = col_parts[id(g)][0][1]
                continue
            vg_by_unit[g["unit"]] = _ground_group(m, state, g, shift_of(g))
            if g["kind"] == "art_site" and g.get("fire_at"):   # артбригада: налёты по ближней части противника
                c = _pt(m, g["fire_at"])
                for k in range(ART_MISSIONS):
                    vg_by_unit[g["unit"]].points[0].tasks.append(task.FireAtPoint(
                        Vector2(c.x + (k - 1.5) * 200, c.y), rounds=ART_ROUNDS, radius=ART_RADIUS_M * 2))
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
    ulift_specs: list[dict] = []                 # вертолётом к части: снабжение, раненые (unitlift.lua, игрок)
    qra_specs: list[dict] = []                   # дежурные пары ПВО (qra.lua)
    cap_specs: list[dict] = []                   # пары прикрытия ИИ (cap.lua)
    timing_specs: list[dict] = []                # выход групп ИИ на рубеж: факт против плана (timing.lua)
    jam_groups: list[str] = []                   # постановщики помех вне зоны ПВО (samctl.lua)
    sead_prio: list[dict] = []                   # группы подавления ПВО: запланированные ЗРК по порядку (seadprio.lua)
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
    # старт с полосы - только у самой ранней группы ИИ на аэродроме; остальные - горячий старт на стоянке (за TAXI_S до
    # взлёта по плану) или уже в воздухе по плану полётов. Решение - до создания групп, по всем группам миссии.
    first_rw: dict[str, str] = {}
    from . import munitions
    mun_spend: dict = {}                         # управляемое оружие миссии - списывается после неё (debrief)
    for g in pkg + enemy:
        if g["objective"]["kind"] in ("alert", "orbit") or g.get("_air_start") or g["base"] in carriers:
            continue
        hum_ = 0 if g.get("_ai") or g.get("_enemy") else hum_of.get(g["group"], 0)
        if player and hum_ > 0:
            continue
        if not g.get("_ai") and times[g["group"]].get("air_s") and _airborne(state, copy.deepcopy(g),
                model.group_speed_kmh(state, g, g.get("_tdef") or tdef), times[g["group"]]["air_s"]):
            continue                             # к началу миссии - уже в воздухе
        ap_key = state["airbases"][g["base"]].get("airport") or g["base"]
        cur = first_rw.get(ap_key)
        if cur is None or times[g["group"]]["start_s"] < times[cur]["start_s"]:
            first_rw[ap_key] = g["group"]
    for g in pkg + enemy:
        tdg = g.get("_tdef") or (model.doctrine(state, g.get("_side", tk["side"]))["tasks"].get(g["jaat_kind"]) if g.get("jaat_kind") else None) \
            or tdef                              # группы противника - по его пакету доктрины; вертолёты совместного удара - по своей
        side_g = g.get("_side", tk["side"])
        t_strk = g.get("_t_strike", times["strike"]["objective_s"])   # время удара своего вылета (у ИИ - по плану полётов)
        spd = model.group_speed_kmh(state, g, tdg)   # скорость задачи доктрины
        transit = g.get("transit_alt_m_agl") or tdg["transit_alt_m_agl"]   # средние высоты, если угроз в коридоре нет (planner)
        perf = state["units"][g["performer"]]
        base = state["airbases"][g["base"]]
        airport = carriers.get(g["base"]) or m.terrain.airports[base["airport"]]   # авианосец - CarrierPad
        ac = dcstypes.flying(perf["type"])
        hum = 0 if g.get("_ai") or g.get("_enemy") else hum_of.get(g["group"], 0)
        is_player = player and hum > 0
        pv = player_variant(state, perf["type"]) if is_player else None
        if pv:                                   # игроку - управляемая версия типа полка (ИИ и модель - тип сценария)
            ac = dcstypes.flying(pv)
            g["_variant"] = pv
        helo = model.category(perf) == "heli"    # вертолёты: предельно малая высота и для ИИ
        mt = _maintask(ac, g["maintask"])
        if g["objective"]["kind"] == "alert":    # дежурная пара ПВО: на стоянке, взлёт по обнаружению (qra.lua)
            try:                                 # стоянка занята или для реактивных её нет - старт с полосы по тревоге
                fg = _from_base(m, _country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                                 airport, maintask=mt, start_type=StartType.Warm, group_size=g["size"])
            except NoParkingSlotError:
                fg = _from_base(m, _country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                                 airport, maintask=mt, start_type=StartType.Runway, group_size=g["size"])
            _crew(state, fg, perf)
            fg.late_activation = True
            _apply_loadout(fg, ac, perf["type"], loadout_cats(g.get("_kind") or tk["kind"], g), state)
            from . import weapons as _w
            _w.policy(fg, state, side_g, ["qra"])   # дежурная пара - CAP (правило подвесок сценария)
            munitions.apply(fg, state, side_g, _mun_swap(state), mun_spend)
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
                    + (i18n.L(lg_, "с " + (m.start_time + datetime.timedelta(seconds=int(t_['start_s']))).strftime("%H:%M"),
                              "from " + (m.start_time + datetime.timedelta(seconds=int(t_['start_s']))).strftime("%H:%M")) if t_["start_s"]
                       else i18n.L(lg_, "с начала миссии", "from mission start"))
                    + i18n.L(lg_, " до ", " until ") + (m.start_time + datetime.timedelta(seconds=int(t_['until_s']))).strftime("%H:%M"))
            (enemy_lines if g.get("_enemy") else ai_lines).append(line)
            fl = m.find_group(f"{perf['id']} {g['group']} {sortie}")
            flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fl.units], "player": False,
                            **({"side": side_g} if g.get("_enemy") else {})})
            continue
        if not is_player and not g.get("_ai") and times[g["group"]].get("air_s"):   # группа пакета игрока, взлетевшая раньше
            g = copy.deepcopy(g)                 # (маршрут в плане не трогаем)
            _airborne(state, g, spd, times[g["group"]]["air_s"])
        if is_player and player_start(state) == "air" and g["base"] not in carriers:   # старт игрока в воздухе
            first = g.get("rv") or (g["route"][0] if g.get("route") else base)
            g = dict(g, _air_start=model.offset(base, model.bearing_deg(base, first), PLAYER_AIR_START_KM * 1000))
        if g.get("_air_start"):                  # по плану полётов к началу миссии уже в воздухе, на пути к объекту
            fg = m.flight_group_inflight(_country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac,
                                         _pt(m, g["_air_start"]), max(int(transit), AIR_START_MIN_M), speed=int(spd),
                                         maintask=mt, group_size=g["size"])
        else:
            ap_key = base.get("airport") or g["base"]
            on_rw = not is_player and first_rw.get(ap_key) == g["group"]   # самая ранняя группа аэродрома - с полосы
            parked = False
            try:
                fg = _from_base(m, _country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac, airport,
                                                 maintask=mt, start_type={"cold": StartType.Cold, "hot": StartType.Warm,
                                                                          "runway": StartType.Runway}.get(player_start(state), StartType.Cold)
                                                 if is_player else (StartType.Runway if on_rw else StartType.Warm), group_size=g["size"])
                parked = not is_player and not on_rw
            except NoParkingSlotError:           # стоянок нет (вертолётная площадка) - с полосы
                fg = _from_base(m, _country(m, state, side_g), f"{perf['id']} {g['group']} {sortie}", ac, airport,
                                                 maintask=mt, start_type=StartType.Runway, group_size=g["size"])
        _crew(state, fg, perf)
        if is_player:
            player_air = (airport, airport)          # аэродром посадки уточняется ниже (перевозка - другой)
        st_s = times[g["group"]]["start_s"]
        if not g.get("_air_start") and not is_player and parked:   # горячий старт: появиться раньше на руление
            rw_g = first_rw.get(ap_key)            # взлёт - не раньше группы с полосы этого аэродрома (+ интервал)
            if rw_g and rw_g in times and rw_g != g["group"]:
                st_s = max(st_s, times[rw_g]["start_s"] + RUNWAY_GAP_S * 2)
            times[g["group"]]["start_s"] = st_s
            g["_parked"] = True
            st_s = max(0, st_s - TAXI_S)
        elif not is_player and not g.get("_air_start"):   # группы ИИ с полосы одного аэродрома - не в одну секунду (столкновение при появлении)
            while (base.get("airport") or g["base"], st_s) in runway_slots:
                st_s += RUNWAY_GAP_S
            runway_slots.add((base.get("airport") or g["base"], st_s))
            times[g["group"]]["start_s"] = st_s
        fg.start_time = st_s
        cat = _apply_loadout(fg, ac, perf["type"], loadout_cats(g.get("_kind") or tk["kind"], g), state)
        cat = _arm_pylons(fg, ac, perf, g, state) or cat
        weapons_policy = __import__("redfront.weapons", fromlist=["x"]).policy   # правило подвесок сценария (ВКС 2022)
        weapons_policy(fg, state, side_g, loadout_cats(g.get("_kind") or tk["kind"], g))
        if g["group"].startswith(("sead", "kill")) or tk["kind"] == "strike_sam_site" and g["group"] == "strike":
            obj_u = g["objective"].get("units") or ([g["objective"]["unit"]] if g["objective"].get("unit") else [])
            munitions.choose_arm(fg, state, side_g, [state["units"][x] for x in obj_u if x in state["units"]], mun_spend)
        mun_notes = munitions.apply(fg, state, side_g, _mun_swap(state), mun_spend)   # запас управляемого оружия
        if mun_notes:
            fg.__dict__.setdefault("_rf_degraded", []).extend(mun_notes)
        tune_arm(state, fg, g)                   # головки ПРР (Shrike) - под РЛС ЗРК своей цели
        needs_mod = False
        for u in fg.units[:hum] if is_player else []:
            needs_mod = _set_player(u, client=multi) or needs_mod
        for u in (fg.units[hum:] if is_player else fg.units):
            u.skill = Skill.High
        r_alt = model.rng(state, f"alt-{perf['id']}-{g['group']}-{sortie}")
        jit = 1.0 + (r_alt.uniform(-ALT_JITTER, ALT_JITTER) if r_alt else 0.0)   # своя высота у каждой группы рядом с доктриной
        def wp(p, alt, name, keep_alt=False):
            if not keep_alt and side_g == tk["side"] and in_threat(p, circles):   # в известной зоне ЗРК - на предельно малой высоте
                alt = min(alt, tdg.get("low_alt_m_agl", alt))
            if alt >= ALT_JITTER_MIN_M:
                alt = alt * jit
            alt = q_alt(state, side_g, alt)          # круглые высоты в единицах стороны (футы НАТО / метры ОВД)
            if not is_player and not helo and alt < AI_LOW_MIN_M:  # ИИ ниже этого бьётся о землю (Су-24М: 3 случая на 40-80 м)
                alt = AI_LOW_MIN_M
            w = fg.add_waypoint(_pt(m, p), alt, speed=q_spd(state, side_g, spd), name=name)
            # вертолёты и маловысотные - от земли (RADIO), эшелоны выше - от уровня моря (BARO)
            w.alt_type = "RADIO" if helo or alt < BARO_FROM_M else "BARO"
            return w
        if not is_player:                        # ИИ - только своя задача: без "поражать цели по пути" от основной задачи DCS
            # (pydcs вешает EngageTargets по maintask: SEAD - любые ПВО, CAS - любые наземные; camp8: Су-24М и Су-25
            # бросали задачу и шли на Patriot). Свои атаки - задачами точек маршрута (AttackGroup/EngageGroup/зона).
            fg.points[0].tasks = [t for t in fg.points[0].tasks if getattr(t, "id", None) != "EngageTargets"]
            sd_km = float(tdg.get("self_defense_km", SELF_DEFENSE_KM))
            if sd_km > 0 and model.category(perf) == "air" and g["objective"]["kind"] not in ("orbit", "alert", "airlift"):
                # самооборона: истребитель противника ближе sd_km - бой (ударная группа не пролетает мимо Су-17 в 3 км);
                # дальше - своя задача. Приоритет ниже задач маршрута.
                sd = task.EngageTargets(max_distance=int(sd_km * 1000), targets=[task.Targets.All.Air.Planes])
                sd.params["priority"] = 1
                fg.points[0].tasks.append(sd)
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
                sp = push_specs["player"] if g["group"] in ("strike", "strike2") else None
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
                if player and not g.get("_ai") and not g.get("_enemy"):   # пакет игрока: ждать игрока на сборе (круг), уход -
                    hold_rv = task.ControlledTask(task.OrbitAction(altitude=int(w.alt), speed=spd,   # когда игрок подошёл
                                                                   pattern=task.OrbitAction.OrbitPattern.Circle))  # или срок
                    hold_rv.stop_if_user_flag(RV_FLAG, True)
                    hold_rv.stop_after_time(int(max(0, rv_s) + RV_WAIT_S))
                    w.tasks.append(hold_rv)
                    rv_wait.append(g["rv"])
            g["_rv_s"] = rv_s
        if obj["kind"] == "airlift":             # воздушная перевозка: перелёт и посадка на аэродроме назначения
            dest = state["airbases"][obj["airbase"]]
            start_p = g.get("_air_start") or base
            alt = int(g.get("alt_m") or transit)
            wp(model.lerp(start_p, obj["pos"], 0.5), alt, "Маршрут", keep_alt=True)
            land = carriers.get(obj["airbase"]) or (m.terrain.airports[dest["airport"]] if dest.get("airport") else None)
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
        elif obj["kind"] == "unit_lift":         # вертолётом к части (снабжение, раненые): малая высота, посадка, домой
            lz = obj["pos"]
            low = int(tdg.get("low_alt_m_agl", 50))
            start_p = g.get("_air_start") or base
            d = model.dist_km(start_p, lz)
            if d > 8:
                wp(model.lerp(lz, start_p, 5 / d), low, "Подход")
            w = wp(lz, low, "Площадка")
            c = _pt(m, lz)
            w.tasks.append(task.Land(Vector2(c.x, c.y), duration=int(tdg.get("land_s", 180))))
            if d > 8:
                wp(model.lerp(lz, base, 5 / model.dist_km(base, lz)), low, "Отход")
            if is_player:                        # игрок: посадка у части засчитывается скриптом (unitlift.lua)
                ulift_specs.append({"id": tk.get("ato_id") or f"task-{sortie}", "mode": obj.get("mode", "resupply"),
                                    "title": state["units"][obj["unit"]]["name"], "x": c.x, "y": c.y,
                                    "r": tdg.get("lz_radius_m", 500), "land": tdg.get("land_s", 180),
                                    "helos": [u.name for u in fg.units]})
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
                    zone = i18n.L(i18n.lang(state), "Погрузка", "Pickup") + f" {sortie}" + ("" if g["group"] == fly else f" {g['group']}")
                    m.triggers.add_triggerzone(u0.position, radius=CTLD_PICKUP_M, hidden=False, name=zone)
                    ctld["pickup"].append({"zone": zone, "side": spec["side"], "limit": 1})
                    ctld_lines.append(f"Десант: погрузка у стоянки (зона {CTLD_PICKUP_M} м) - F10 -> CTLD -> Troop Transport -> "
                                      f"Load Assault...; высадка на площадке (ближе {spec['r']} м) - Unload / Extract Troops "
                                      f"(на земле или висением по тросу). Высадили не там - заберите (тот же пункт) и высадите снова.")
            g["_lz"] = obj["place"]
        elif obj["kind"] == "ship":              # удар по кораблям: от ИПМ на малой высоте, атака группы кораблей
            ip, tgt = g["route"]
            push_hold(wp(ip, transit, "ИПМ"), ip, tgt)
            w = wp(tgt, tdg["attack_alt_m_agl"], "Цель")
            sg = NAVAL_GROUPS.get(obj["unit"])
            if sg is not None:
                w.tasks.append(_attack(sg.id, ai))
            wp(ip, tdg.get("egress_alt_m_agl") or transit, "Отход")
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
            med = sup.get("medium_alt_m") if sup.get("mode") != "kill" else None
            if med:                              # Wild Weasel / Iron Hand: на средних высотах - РЛС ЗРК видит и включается
                low = transit = med
            hold_until = t_strk + int(sup.get("hold_after_min", 0) * 60)
            if sup.get("mode") == "kill" and g["route"]:   # добивание (killer): за hunter на рубеж, оттуда атака каждого ЗРК
                sam_pos = model.unit_pos(state, state["units"][obj["units"][0]])
                entry_km = planner.threat_radius_km(state["units"][obj["units"][0]]) + LOW_ENTRY_KM
                total = model.dist_km(base, sam_pos)
                if total > entry_km + 5:
                    wp(model.lerp(sam_pos, base, entry_km / total), transit, "Снижение", keep_alt=True)
                w = wp(g["route"][0], low, "Рубеж атаки")
                for k, sid in enumerate(obj["units"]):   # по плану: главная цель - первой
                    w.tasks.append(_attack(vg_by_unit[sid].id, ai) if sead_known(state, side_g, sid)
                                   else _sead_zone(m, state, sid, k))
                w.tasks.append(_sead_area(m, state, g, obj))
                sead_prio.append({"group": fg.name, "sams": [vg_by_unit[sid].name for sid in obj["units"] if sid in vg_by_unit]})
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
                for k, sid in enumerate(obj["units"]):                # атака - по всем ЗРК коридора, пока идёт ожидание;
                    # приоритет - по плану (главная цель - 0): пока главный ЗРК жив, звено бьёт его, потом - следующие;
                    # свежие данные разведки - по группе ЗРК (заранее спланированный пуск), иначе - поиск в районе
                    w.tasks.append(_engage(vg_by_unit[sid].id, ai, g.get("launch_alt_m"), k) if sead_known(state, side_g, sid)
                                   else _sead_zone(m, state, sid, k))
                sead_prio.append({"group": fg.name, "sams": [vg_by_unit[sid].name for sid in obj["units"] if sid in vg_by_unit]})
                w.tasks.append(_sead_area(m, state, g, obj))   # свои ЗРК подавлены или сбили соседа - работать по соседним РЛС
                # ожидание: на высоте пуска, если рубеж вне зоны поражения любого из ЗРК, иначе на малой (ОЦЕНКА)
                inside = any(model.dist_km(g["route"][0], model.unit_pos(state, state["units"][sid]))
                             - sup.get("orbit_radius_km", 0) <= planner.threat_radius_km(state["units"][sid]) for sid in obj["units"])
                alt = max(low, AI_LOW_MIN_M) if inside else int(g.get("launch_alt_m") or low)
                hold = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
                hold.stop_after_time(hold_until)
                w.tasks.append(hold)
                g["hold"] = {"alt_m": alt, "until_s": hold_until, "launch_km": round(planner.launch_distance_km(sam, sup), 1)}
            if is_player:                        # игроку - точка на каждой цели (ЗРК известен - позиция, иначе последняя по
                for k, sid in enumerate(obj["units"]):   # разведке): для навигации и прицела; лететь на неё не обязательно
                    wp(model.unit_pos(state, state["units"][sid]), low, "Цель" if len(obj["units"]) == 1 else f"Цель {k + 1}")
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
        elif obj["kind"] == "jam_orbit":        # постановщик помех: круг вне зоны ЗРК до конца удара, станция помех включена
            alt = q_alt(state, side_g, int(g.get("alt_m") or 6000) * jit)
            w = wp(obj["pos"], alt, "Зона постановки помех", keep_alt=True)
            w.alt_type = "BARO"
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_time(t_strk + int((g.get("hold_after_min") or 5) * 60))
            w.tasks.append(orbit)
            fg.points[0].tasks.append(task.OptECMUsing(task.OptECMUsing.Values.AlwaysUse))
            fg.points[0].tasks.append(task.OptReactOnThreat(task.OptReactOnThreat.Values.EvadeFire))
            for u_ in fg.units:                  # оружия у постановщика нет (EA-6B на модели A-6E - без бомб и ПРР)
                u_.pylons.clear()
            fg.points[0].tasks = [t_ for t_ in fg.points[0].tasks if not isinstance(t_, task.EngageTargets)]
            fg.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponHold))
            jam_groups.append(fg.name)
        elif obj["kind"] == "feint":            # демонстративная: на средней высоте к точке другим направлением, круг, домой
            alt = int(g.get("alt_m") or 4000)
            w = fg.add_waypoint(_pt(m, obj["pos"]), alt, speed=spd, name="Демонстрация")
            w.alt_type = "BARO"
            orbit = task.ControlledTask(task.OrbitAction(altitude=alt, speed=spd, pattern=task.OrbitAction.OrbitPattern.Circle))
            orbit.stop_after_duration(int((g.get("orbit_min") or 6) * 60))
            w.tasks.append(orbit)
        elif obj["kind"] in ("cap_zone", "cover_zone", "sweep_zone"):   # прикрытие / расчистка воздуха
            alt = q_alt(state, side_g, int(g.get("alt_m") or 3000) * jit)
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
        if not is_player:                        # ИИ: ко времени на рубеже - ETA там, скорость DCS подберёт сама
            ts = _lock_eta(fg, times[g["group"]]["objective_s"], spd)
            if ts:
                timing_specs.append(ts)
            _no_crawl(fg, spd)                   # раньше времени - круг ожидания на точке, а не 150 км/ч по маршруту
        rc = g.get("reach") or ""
        if rc == "tanker":                       # за радиусом: дозаправка на обратном пути у зоны заправщика
            ttd = model.doctrine(state, side_g)["tasks"].get("tanker_orbit") or {}
            tp = planner.orbit_point(state, side_g, ttd.get("standoff_km", 200))
            if tp:
                w = wp(tp, int(ttd.get("transit_alt_m_agl") or 7000), "Заправка", keep_alt=True)
                w.tasks.append(task.RefuelingTaskAction())
                g["_reach_note"] = i18n.L(i18n.lang(state), "дозаправка на обратном пути (точка 'Заправка')",
                                          "air refuelling on the way back (waypoint 'Refuel')")
        elif rc.startswith("divert:"):           # не хватает топлива домой - посадка на своём аэродроме ближе к цели
            b = state["airbases"].get(rc.split(":", 1)[1])
            if b and b.get("airport") in m.terrain.airports:
                land = m.terrain.airports[b["airport"]]
                g["_reach_note"] = i18n.L(i18n.lang(state), f"посадка на запасном: {b['name']} (топлива домой не хватает)",
                                          f"recovery at {b['name']} (not enough fuel to return home)")
        if land is airport and not rc:           # рассредоточение (dispersal.py): посадка на другом своём аэродроме
            from . import dispersal
            ob = dispersal.land_other(state, perf, f"{perf['id']}-{g['group']}-{sortie}")
            b = state["airbases"].get(ob or "")
            if b and b.get("airport") in m.terrain.airports:
                land = m.terrain.airports[b["airport"]]
                g["_reach_note"] = i18n.L(i18n.lang(state), f"посадка на {b['name']} (рассредоточение)",
                                          f"landing at {b['name']} (dispersal)")
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
        clk = lambda s_: (m.start_time + datetime.timedelta(seconds=int(s_))).strftime("%H:%M")   # время миссии
        t0_ = times["strike"]["objective_s"] if "strike" in times else t["objective_s"]
        tt = lambda s_: f"{clk(s_)} (T0{(int(s_) - int(t0_)) // 60:+d})" if int(s_) != int(t0_) else f"{clk(s_)} (T0)"
        when = (i18n.L(i18n.lang(state), f"посадка в {g['_dest']} в {clk(t['objective_s'])}", f"landing at {g['_dest']} at {clk(t['objective_s'])}")
                if g.get("_dest") else i18n.L(i18n.lang(state), f"в районе в {clk(t['objective_s'])}", f"in the area at {clk(t['objective_s'])}"))
        if g.get("_enemy"):                      # авиация противника - в разведсводку, не в состав группы
            enemy_lines.append(f"{g['title']}: {g['size']} x {perf['type']} ({perf['name']}), {base['name']}, {when}")
            flights.append({"group": g["group"], "performer": perf["id"], "kind": g["objective"]["kind"], "units": [u.name for u in fg.units], "player": False,
                            "side": side_g, **({"ato": g["_ato"]} if g.get("_ato") else {})})
            continue
        lg = i18n.lang(state)
        Lx = lambda ru, en: i18n.L(lg, ru, en)
        (ai_lines if g.get("_ai") else lines).append(f"{i18n.tr(g['title'], lg)}: {g['size']} x {g.get('_variant') or perf['type']} ({perf['name']}), {base['name']}, "
                     + ((Lx("игрок, холодный старт", "player, cold start")
                         + (Lx(" (в базовом DCS тип только для ИИ - нужен мод)", " (AI-only type in base DCS - a mod is required)") if needs_mod else "")
                         + (Lx(f", ВЗЛЁТ в {clk(t['takeoff_s'])} (время удара - по самой медленной группе; раньше - ждать в точке сбора)",
                               f", TAKE OFF at {clk(t['takeoff_s'])} (time on target is set by the slowest group; if early - hold at the rendezvous)")
                            if t.get("takeoff_s") else ""))
                        if is_player else Lx("ИИ, к началу миссии уже в воздухе на маршруте", "AI, already airborne en route at mission start")
                        if g.get("_air_start") else
                        Lx(f"ИИ, со стоянки (двигатели запущены), взлёт в {clk(t['start_s'])}",
                           f"AI, from parking (engines running), takeoff at {clk(t['start_s'])}") if g.get("_parked") else
                        Lx(f"ИИ, взлёт с полосы в {clk(t['start_s'])}", f"AI, runway takeoff at {clk(t['start_s'])}"))
                     + (f", {when}" if g.get("_dest") else Lx(f", на объекте в {tt(t['objective_s'])}", f", on objective at {tt(t['objective_s'])}"))
                     + (Lx(f", переход на {transit} м (угроз ЗРК в коридоре нет)", f", transit at {transit} m (no SAM threats in the corridor)")
                        if g.get("transit_alt_m_agl") else "")
                     + (Lx(f", ОПАЗДЫВАЕТ на {t['late_s'] // 60} мин", f", LATE by {t['late_s'] // 60} min") if t["late_s"] else "")
                     + (Lx(f", ожидание на рубеже пуска ({g['hold']['launch_km']:.0f} км от ЗРК) на {g['hold']['alt_m']} м до {clk(g['hold']['until_s'])}",
                           f", holding at the launch line ({g['hold']['launch_km']:.0f} km from the SAM) at {g['hold']['alt_m']} m until {clk(g['hold']['until_s'])}")
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
    specs = [s for s in (column_spec(m, state, pg, vg) for g in groups if g["kind"] == "column"
                         for pg, vg in (col_parts.get(id(g)) or [(g, vg_by_unit[g["unit"]])])) if s]
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
    sc_specs = samctl_spec(state, vg_by_unit)    # огонь ПВО: реакция расчёта, дальность пуска, заграждение зениток,
    if sc_specs:                                 # переезд после пусков, ПЗРК - 2 пуска, помехи (постановщики и самолётные)
        trig.add_action(DoScript(String(samctl_script(state, sc_specs, jam_groups))))
    from . import strategic
    ssm = [l for l in strategic.mission_launches(state, int(m0), ato.MISSION_LEN_S) if l["unit"] in vg_by_unit]
    if ssm:                                      # пуски ОТР суток во время миссии - по-настоящему (ssm.lua)
        q_ = lambda x: '"' + str(x).replace('"', "'") + '"'
        items = []
        for l in ssm:
            tp = _pt(m, model.unit_pos(state, state["units"][l["target"]]))
            items.append(f'{{ group = {q_(vg_by_unit[l["unit"]].name)}, x = {tp.x:.0f}, y = {tp.y:.0f}, at = {l["at_s"]}, '
                         f'target = {q_(state["units"][l["target"]]["name"])} }}')
        trig.add_action(DoScript(String((Path(__file__).parent / "lua" / "ssm.lua").read_text(encoding="utf-8")
                                        .replace("@CAMPAIGN@", state["campaign_id"]).replace("@SORTIE@", str(int(state["sortie"])))
                                        .replace("@SPECS@", ", ".join(items)))))
    for r in strategic.mission_raids(state, int(m0), ato.MISSION_LEN_S):   # налёты бомбардировщиков с крылатыми ракетами
        raid_group(m, state, r)
    if sead_prio:                                # самооборона групп подавления: стреляющий по звену ЗРК - вне очереди
        q_ = lambda x: '"' + str(x).replace('"', "'") + '"'
        items = ", ".join("{ group = " + q_(s_["group"]) + ", sams = { " + ", ".join(q_(n) for n in s_["sams"]) + " } }"
                          for s_ in sead_prio)
        trig.add_action(DoScript(String((Path(__file__).parent / "lua" / "seadprio.lua").read_text(encoding="utf-8")
                                        .replace("@CAMPAIGN@", state["campaign_id"]).replace("@SORTIE@", str(int(state["sortie"])))
                                        .replace("@SPECS@", items))))
    deploy = []                                  # ЗРК в колоннах: огонь - после остановки и развёртывания (samdeploy.lua)
    for g in groups:
        if g["kind"] != "column":
            continue
        dep = max((SAM_DEPLOY_S.get(v["type"], 0) for v in g["vehicles"]), default=0)
        if not dep:
            continue
        for pg, vg in (col_parts.get(id(g)) or [(g, vg_by_unit.get(g["unit"]))]):
            if vg is not None:
                deploy.append((vg.name, dep))
    if deploy:
        q_ = lambda x: '"' + str(x).replace('"', "'") + '"'
        trig.add_action(DoScript(String((Path(__file__).parent / "lua" / "samdeploy.lua").read_text(encoding="utf-8")
                                        .replace("@CAMPAIGN@", state["campaign_id"]).replace("@SORTIE@", str(int(state["sortie"])))
                                        .replace("@SPECS@", ", ".join("{ group = " + q_(n) + ", deploy = " + str(int(d)) + " }"
                                                                      for n, d in deploy)))))
    specs_p = [sp for sp in push_specs.values() if sp["strikes"]]
    if specs_p:                                  # удар по готовности подавления ПВО
        trig.add_action(DoScript(String(push_script(state["campaign_id"], state["sortie"], specs_p, strict_abort(state)))))
    if timing_specs:                             # проверка плана по времени: факт выхода групп ИИ на рубеж
        q = lambda x: '"' + str(x).replace('"', "'") + '"'
        items = ", ".join(f'{{ group = {q(t["group"])}, x = {t["x"]:.0f}, y = {t["y"]:.0f}, eta = {t["eta"]} }}' for t in timing_specs)
        trig.add_action(DoScript(String((Path(__file__).parent / "lua" / "timing.lua").read_text(encoding="utf-8")
                                        .replace("@CAMPAIGN@", state["campaign_id"]).replace("@SORTIE@", str(state["sortie"]))
                                        .replace("@SPECS@", items))))
    if cap_specs:                                # пары прикрытия ИИ: без ведомого - домой
        trig.add_action(DoScript(String(cap_script(state["campaign_id"], state["sortie"], cap_specs, strict_abort(state)))))
    humans_all = [n for f in flights if f.get("player") for n in f.get("humans", [])]
    if rv_wait and humans_all:                   # сбор пакета: игрок ближе RV_NEAR_M к точке сбора - флаг, группы уходят с круга
        p0 = _pt(m, rv_wait[0])
        names = ", ".join('"' + n.replace('"', "'") + '"' for n in humans_all)
        trig.add_action(DoScript(String(
            f"-- redfront rv | campaign {state['campaign_id']} | sortie {state['sortie']}\n"
            f"-- Сбор пакета: игрок подошёл к точке сбора - флаг {RV_FLAG}: группы пакета уходят с круга ожидания.\n"
            f"local RV, NAMES, R = {{ x = {p0.x:.0f}, z = {p0.y:.0f} }}, {{ {names} }}, {RV_NEAR_M}\n"
            "local function chk()\n"
            "  for _, n in ipairs(NAMES) do\n"
            "    local u = Unit.getByName(n)\n"
            "    if u and u:isExist() and u:inAir() then\n"
            "      local p = u:getPoint()\n"
            "      if (p.x - RV.x) ^ 2 + (p.z - RV.z) ^ 2 <= R * R then\n"
            f"        trigger.action.setUserFlag({RV_FLAG}, true)\n"
            "        trigger.action.outText('redfront: пакет собран - на маршрут', 10)\n"
            "        return nil\n"
            "      end\n"
            "    end\n"
            "  end\n"
            "  return timer.getTime() + 5\n"
            "end\n"
            "timer.scheduleFunction(chk, nil, timer.getTime() + 5)\n")))
    gs = gci_sides(state)                        # наземное наведение (КРУ) истребителей ИИ: дежурные пары и пары прикрытия
    gci_f = [{"group": x["group"], "side": x["side"]} for x in qra_specs + cap_specs if x["side"] in gs]
    if qra_specs or gci_f:                       # общая картина обстановки (airpic.lua) - до qra.lua и gci.lua
        trig.add_action(DoScript(String(airpic_script(state, m))))
    if qra_specs:                                # дежурные звенья ПВО: подъём по налёту (соразмерно, с резервом)
        trig.add_action(DoScript(String(qra_script(state["campaign_id"], state["sortie"], qra_specs, state))))
    if gci_f:
        trig.add_action(DoScript(String(gci_script(state, gci_f))))
    if ulift_specs:                              # игрок везёт груз или раненых: посадка у части (unitlift.lua)
        trig.add_action(DoScript(String(ulift_script(state["campaign_id"], state["sortie"], ulift_specs))))
    if evac_specs:                               # эвакуация: рота садится в борта на площадке (evac.lua; игрок - CTLD)
        trig.add_action(DoScript(String(evac_script(state["campaign_id"], state["sortie"], evac_specs))))
    if assault_specs:                            # десант: рота выходит при посадке бортов на площадку (assault.lua)
        trig.add_action(DoScript(String(assault_script(state["campaign_id"], state["sortie"], assault_specs))))
    # хук - последним: колонна и позиции ПВО пересоздаются раньше (их снятие - не потери); ошибка любого скрипта до
    # хука его не останавливает - каждый скрипт в pcall. String(...), не m.string(...): иначе DCS исполняет ключ перевода
    trig.add_action(DoScript(String(lua_hook(state["campaign_id"], state["sortie"], track))))
    for act in trig.actions:                     # каждый скрипт - в pcall: ошибка одного - строка в DCS.log и на экране,
        if isinstance(act, DoScript):            # остальные работают
            _set_script(act, _guard(act.text.id))
    m.triggerrules.triggers.append(trig)

    for g in pkg:                                # дозаправка или запасной аэродром - строка в брифинге
        if g.get("_reach_note"):
            lines.append(f"{i18n.tr(g['title'], i18n.lang(state))}: {g['_reach_note']}")
    for g in pkg:                                # управляемая версия типа у группы игрока - строка в брифинге
        if g.get("_variant"):
            lines.append(i18n.L(i18n.lang(state),
                                f"игровое допущение: ваша группа - {g['_variant']} вместо {state['units'][g['performer']]['type']} "
                                "(тип полка только для ИИ); ИИ и потери - по типу полка",
                                f"gameplay concession: your flight flies {g['_variant']} instead of "
                                f"{state['units'][g['performer']]['type']} (AI-only type); AI and losses use the unit type"))
    ext_aw = external_awacs(m, state, tk, sortie)   # ДРЛО третьей стороны вне театра (НАТО для ВСУ)
    pa = player_awacs(m, state, tk, sortie) if player and player_air else None   # игроку - картина ДРЛО
    comm_lines = radio_setup(m, state, tk, pkg, sortie, player_air)
    comm_lines += ext_aw
    if pa:
        comm_lines.append(pa)
    order_lines = package_order(pkg, times, i18n.lang(state),
                                lambda s_: (m.start_time + datetime.timedelta(seconds=int(s_))).strftime("%H:%M"))
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
        + (", ".join(natonames.name(state, state['units'][t], tk['side']) for t in tk['threats']) or Lx("не выявлены", "none detected"))
        + (Lx("\nЗамечания планировщика: ", "\nPlanner notes: ") + tk['package_notes'] if tk.get("package_notes") else "")
        + ((Lx("\n\nДругие вылеты наших сил в это время:\n", "\n\nOther friendly sorties at this time:\n") + "\n".join(f"- {ln}" for ln in ai_lines)) if ai_lines else "")
        + (Lx("\nРазведка: в районе возможна активность авиации противника.", "\nIntelligence: enemy air activity is possible in the area.") if enemy_lines else "")
        + ((Lx("\n\nНаведение (КРУ, только МиГ-29):\n", "\n\nGround control intercept (GCI, MiG-29 only):\n") + "\n".join(f"- {ln}" for ln in gci_lines)) if gci_lines else "")
        + ((Lx("\n\nПеревозки и наведение (CTLD):\n", "\n\nTransport and JTAC (CTLD):\n") + "\n".join(f"- {ln}" for ln in ctld_lines)) if ctld_lines else ""))

    if lg == "en":                               # английская миссия: брифинг, сообщения скриптов - из русского текста модели
        from . import i18n_en
        m.set_description_text(i18n_en.en(m.description_text()))
        lines, order_lines, comm_lines = ([i18n_en.en(x) for x in ls] for ls in (lines, order_lines, comm_lines))
        for tr_ in m.triggerrules.triggers:
            for act in tr_.actions:
                if isinstance(act, DoScript):
                    _set_script(act, lua_en(act.text.id))
    tpl = dict(times.get(fly) or {})
    tpl["takeoff_s"] = player_takeoff_s(state, tdef, pkg, fly, join=False)   # в планшете - взлёт; сбор - отдельно
    kb_pages = _kneeboard(m, state, tk, lines, order_lines, comm_lines, wx_text, lg, tpl)

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
        "ships": naval_manifest(),                       # корабли флота в миссии (дебриф: потопленные - потери групп)
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
        "munitions": mun_spend,
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

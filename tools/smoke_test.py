"""Сквозной тест без DCS: два дня кампании.

1. new -> plan -> build: собирается .miz, он заново читается pydcs.
2. Lua-хук дебрифа исполняется настоящим интерпретатором Lua (lupa) с заглушками DCS API:
   имитируются гибель машин, взлёт/посадка, позиции колонны, конец миссии; проверяется JSON, который он пишет.
3. Этот JSON применяется к кампании: потери по весам (правило сохранения), продвижение колонны.
4. end-day -> день 2: колонна потрёпана и дальше по маршруту, задача и миссия строятся заново.
5. Слои: результаты состава сил по умолчанию совпадают с версией 0.1 (BASELINE); другой тип техники с той же ролью
   планируется и собирается; игра за сторону без авиационных задач даёт понятную причину; ЗРК без радиуса берёт pydcs.

Запуск: python tools/smoke_test.py   (нужен pydcs; lupa - по желанию, без неё проверки исполнения хука пропускаются)
"""
from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dcs  # noqa: E402
from dcs.mapping import LatLng, Point  # noqa: E402
from dcs.terrain.germany import Germany  # noqa: E402

from redfront import build, debrief, materialize, model, planner, roads, sim  # noqa: E402

# Проверки с точными числами - без случайности (базовый вариант сценария); случайность - отдельно (random_section).
_new_campaign = model.new_campaign
def _new_no_random(*a, **kw):
    kw.setdefault("randomness", False)
    return _new_campaign(*a, **kw)
model.new_campaign = _new_no_random

FAILS = []

# Части фронта (0.4) в составе сил по умолчанию. Проверки слоёв 0.1-0.3 (колонна, пакет, дороги) идут на составе сил
# без них - так их числа сравнимы с BASELINE; фронт проверяется отдельно (front_section) на полном составе.
FRONT_UNITS = {"red_msp_1", "red_pvo_msp_1", "red_tp_1", "red_pvo_tp_1", "blue_pz_bn_1", "blue_flak_2",
               "red_iap_1", "blue_jg_1", "blue_jbg_1",     # фронт (0.4) и воздушная война (0.5)
               "blue_pzgren_bn_2", "blue_flak_4", "blue_pzbrig_2", "blue_flak_5", "red_msp_2", "red_pvo_msp_2"}   # масштаб (0.8)
BASE_OOB = Path(tempfile.mkdtemp(prefix="redfront_oob_")) / "oob_base.json"


def base_oob() -> dict:
    o = model.load_json("oob_hamburg.json")
    o["units"] = [u for u in o["units"] if u["id"] not in FRONT_UNITS]
    return o


BASE_OOB.write_text(json.dumps(base_oob(), ensure_ascii=False), encoding="utf-8")
# Сектор слоёв 0.1-0.3 - без объектов тыла (0.8) и только с аэродромом этих слоёв: числа сравнимы с BASELINE.
BASE_SECTOR = BASE_OOB.parent / "sector_hamburg.json"
_sec = model.load_json("sector_hamburg.json")
_sec.pop("depots", None); _sec.pop("bridges", None)
_sec["airbases"] = {"parchim": _sec["airbases"]["parchim"]}
BASE_SECTOR.write_text(json.dumps(_sec, ensure_ascii=False), encoding="utf-8")

# Числа прогона версии 0.1 (до разделения на слои) с тем же составом сил: переделка не должна их сдвигать.
BASELINE = {"col_d1": 30, "col_half": 20, "lost": 8, "advance_d2_km": 18.33, "col_d2": 22, "big_deployed": 40}


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def all_flight_units(man: dict) -> list[str]:
    return [n for fl in man["flights"] for n in fl["units"]]


def plane_groups(m) -> list:
    return [g for c in m.coalition["red"].countries.values() for g in c.plane_group]


def strike_group(m):
    return next(g for g in plane_groups(m) if " strike " in g.name)


def pylons_match(unit) -> bool:
    """Пилоны юнита = ровно записи loadouts.json для Su_25/anti_armor, с теми же CLSID."""
    want = model.load_json("loadouts.json")["Su_25"]["anti_armor"]["pylons"]
    ac = dcs.planes.Su_25
    expect = {int(p): getattr(getattr(ac, f"Pylon{p}"), w)[1]["clsid"] for p, w in want.items()}
    got = {int(p): d["CLSID"] for p, d in unit.pylons.items()}
    return got == expect


class fake_default_loadout:
    """Подменяет загрузку DCS по умолчанию: на каждый пилон типа - первое доступное оружие."""
    def __init__(self, ac):
        self.ac = ac

    def __enter__(self) -> int:
        payload = []
        for n in sorted(self.ac.pylons):
            pc = getattr(self.ac, f"Pylon{n}", None)
            w = next((v for k, v in vars(pc).items() if not k.startswith("_") and isinstance(v, tuple)), None) if pc else None
            if w:
                payload.append(w)
        self.orig = self.ac.__dict__.get("loadout")
        self.ac.loadout = classmethod(lambda cls, _task: payload)
        return len(payload)

    def __exit__(self, *exc):
        if self.orig is None:
            del self.ac.loadout
        else:
            self.ac.loadout = self.orig
        return False


def have_lupa() -> bool:
    try:
        import lupa  # noqa: F401
        return True
    except ImportError:
        return False


def fake_hook(campaign: str, sortie: int, kill: list[str], positions: dict[str, tuple[float, float]], flight: list[str]) -> dict:
    """Без lupa: JSON того же вида, что пишет хук (debrief_hook.lua, функция dump) после этого сценария."""
    return {"campaign": campaign, "sortie": sortie, "mission_ended": True, "time": 3000,
            "dead": sorted(kill), "ejected": [], "landed": sorted(flight), "takeoff": sorted(flight),
            "positions": {n: list(p) for n, p in positions.items() if n not in kill}}


def run_hook(script: str, outdir: Path, kill: list[str], positions: dict[str, tuple[float, float]], flight: list[str]) -> dict:
    """Исполнить хук в Lua с заглушками DCS. Возвращает разобранный JSON, который он записал."""
    import lupa
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(r'''
      env = { warning = function(s) end }
      trigger = { action = { outText = function() end } }
      world = { event = { S_EVENT_DEAD = 8, S_EVENT_CRASH = 5, S_EVENT_PILOT_DEAD = 9, S_EVENT_EJECTION = 6,
                          S_EVENT_TAKEOFF = 3, S_EVENT_LAND = 4, S_EVENT_MISSION_END = 12, S_EVENT_UNIT_LOST = 30 },
                handlers = {} }
      function world.addEventHandler(h) world.handlers[#world.handlers + 1] = h end
      NOW = 0
      timer = { getTime = function() return NOW end, scheduleFunction = function() end }
      POS = {}
      Unit = { getByName = function(n)
        if POS[n] == nil then return nil end
        return { getPoint = function() return { x = POS[n][1], y = 0, z = POS[n][2] } end }
      end }
      Object = { Category = { UNIT = 1, WEAPON = 2, STATIC = 3, BASE = 4, SCENERY = 5, CARGO = 6 } }
      function obj(n, cat) return { getName = function() return n end, getCategory = function() return cat or Object.Category.UNIT end } end
      function fire(id, n, cat) for _, h in ipairs(world.handlers) do h:onEvent({ id = id, initiator = n and obj(n, cat) or nil }) end end
    ''')
    (outdir / "redfront").mkdir(parents=True, exist_ok=True)                 # lfs.mkdir в заглушке ничего не делает
    L.execute(f'lfs = {{ writedir = function() return "{outdir.as_posix()}/" end, mkdir = function() end }}')
    pos = L.globals().POS
    for n, (x, z) in positions.items():
        pos[n] = L.table(x, z)
    script = script.replace('DIR .. "\\\\debrief_', 'DIR .. "/debrief_')     # путь Windows -> POSIX только для теста
    L.execute(script)
    ev = L.globals().world.event
    fire = L.globals().fire
    for n in flight:
        fire(ev.S_EVENT_TAKEOFF, n)
    L.globals().NOW = 1500
    for n in kill:
        fire(ev.S_EVENT_DEAD, n)
    for n in ("1795383318", "3524780032"):                                   # дома/деревья: в DCS приходят числовыми именами
        fire(ev.S_EVENT_DEAD, n, L.globals().Object.Category.SCENERY)
    for n in flight:
        fire(ev.S_EVENT_LAND, n)
    L.globals().NOW = 3000
    fire(ev.S_EVENT_MISSION_END, None)
    files = list((outdir / "redfront").glob("debrief_*.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text(encoding="utf-8"))


def detour(a: Point, b: Point, off_m: float, n: int = 12) -> list[list[float]]:
    """Ломаная a -> (середина со смещением off_m вбок) -> b, n точек на плечо: 'дорога' с объездом."""
    import math
    dx, dy = b.x - a.x, b.y - a.y
    L = math.hypot(dx, dy)
    mx, my = (a.x + b.x) / 2 - dy / L * off_m, (a.y + b.y) / 2 + dx / L * off_m
    pts = []
    for (x0, y0), (x1, y1) in (((a.x, a.y), (mx, my)), ((mx, my), (b.x, b.y))):
        for i in range(n):
            t = i / n
            pts.append([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t])
    pts.append([b.x, b.y])
    return pts


def run_probe(script: str, outdir: Path, fail_id: str) -> dict:
    """Исполнить скрипт зонда в Lua с заглушками land.*: путь - объезд 1.5 км; одна пара - 'дорога не найдена';
    getClosestPointOnRoads отдаёт два числа, findPathOnRoads - таблицу {x=,y=} (обе формы API)."""
    import lupa
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute('trigger = { action = { outText = function(s) MSG = s end } }')
    L.execute(f'lfs = {{ writedir = function() return "{outdir.as_posix()}/" end, mkdir = function() end }}')
    (outdir / "redfront").mkdir(parents=True, exist_ok=True)
    py_detour = lambda x1, y1, x2, y2: detour(Point(x1, y1, None), Point(x2, y2, None), 1500.0)
    L.globals().py_detour = py_detour
    L.execute(r'''
      FAIL_ID = nil
      land = {}
      function land.getClosestPointOnRoads(kind, x, y) return x, y end
      function land.findPathOnRoads(kind, x1, y1, x2, y2)
        if CURRENT == FAIL_ID then return nil end
        local out = {}
        for p in python.iter(py_detour(x1, y1, x2, y2)) do out[#out + 1] = { x = p[0], y = p[1] } end
        return out
      end
    ''')
    L.globals().FAIL_ID = fail_id
    # пара, на которой "дорога не найдена", помечается до вызова findPathOnRoads
    script = script.replace("local ok, err = pcall(function()", "CURRENT = p.id\n  local ok, err = pcall(function()")
    script = script.replace('DIR .. "\\\\roads_', 'DIR .. "/roads_')
    L.execute(script)
    files = list((outdir / "redfront").glob("roads_*.json"))
    assert len(files) == 1, files
    return {"file": files[0], "msg": L.globals().MSG}


def package_section(tmp: Path) -> None:
    """Тактическая группа по доктрине ('Тактика ВВС' 3.3.3): ударная + подавление ПВО + доразведка."""
    st = model.new_campaign("pkg", oob=BASE_OOB, sector=BASE_SECTOR)
    tk = planner.plan(st)
    pk = {g["group"]: g for g in tk["package"]}
    check(list(pk) == ["strike", "sead", "sead2", "recon"] and all(g["size"] == 2 for g in pk.values()),
          "пакет: ударная 2 + подавление ПВО 2 пары (ЗРК в коридоре) + доразведка 2 (цель на марше)")
    check(pk["sead"]["objective"]["units"] == pk["sead2"]["objective"]["units"] == ["blue_flak_1"],
          "обе пары подавления ПВО нацелены на войсковую ПВО колонны")
    check(pk["strike"]["performer"] == "red_shap_1" and pk["sead"]["performer"] == pk["sead2"]["performer"] == "red_bap_1",
          "подавление ПВО - Су-24М (умеет SEAD), ударная - Су-25")
    flak = st["units"]["blue_flak_1"]
    det, thr = planner.detection_radius_km(flak), planner.threat_radius_km(flak)
    sup = next(x for x in model.doctrine(st, "red")["tasks"]["strike_column_march"]["support"] if x["id"] == "sead")
    d_line = planner.launch_distance_km(flak, sup)
    d_hold = model.dist_km(pk["sead"]["route"][0], model.unit_pos(st, flak))
    check(det == 12 and thr == 8 and d_line == 10 and abs(d_hold - 13) < 0.05,
          f"рубеж пуска ПРР {d_line:.0f} км = обнаружение Roland {det:.0f} - 2, вне зоны поражения {thr:.0f}; центр круга ожидания {d_hold:.1f} км (+3)")

    man = build.build(st, tmp / "pkg.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "pkg.miz"))
    pg = {g.name.split(" ")[1]: g for g in plane_groups(m)}
    vgs = {g.name: g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group}
    def attack_ids(g, kind="AttackGroup"):
        return [t.params["groupId"] for p in g.points for t in p.tasks if getattr(t, "id", None) == kind]
    check(set(pg) == {"strike", "sead", "sead2", "recon"}, "в .miz четыре группы тактической группы")
    check(attack_ids(pg["strike"]) == [vgs["blue_pzgren_bn_1"].id], "ударная группа: AttackGroup по колонне")
    check(attack_ids(pg["sead"], "EngageGroup") == attack_ids(pg["sead2"], "EngageGroup") == [vgs["blue_flak_1"].id]
          and attack_ids(pg["sead"]) == [],
          "каждая пара подавления ПВО - своей задачей EngageGroup (действует всё ожидание) по войсковой ПВО")
    t_ = build.timeline(model.doctrine(st, "red")["tasks"]["strike_column_march"], st, tk["package"], "strike")
    for k in ("sead", "sead2"):
        pts_ = pg[k].points
        names = [p.name for p in pts_[1:-1]]
        att_ = next(t for p in pts_ for t in p.tasks if getattr(t, "id", None) == "EngageGroup")
        hold_ = next(t for p in pts_ for t in p.tasks if getattr(t, "id", None) == "ControlledTask")
        check(names == ["Снижение", "Рубеж пуска", "Уход"] and pts_[1].alt == 300
              and all(p.alt == build.AI_LOW_MIN_M and p.alt_type == "RADIO" for p in pts_[2:-1])
              and att_.params["altitudeEnabled"] and att_.params["altitude"] == 1000
              and hold_.params["task"]["params"]["altitude"] == 1000
              and hold_.params["stopCondition"] == {"time": t_["strike"]["objective_s"] + 300},
              f"{k}: от аэродрома на 300 м, за 20 км до зоны ЗРК - снижение; подход и уход на {build.AI_LOW_MIN_M} м (ИИ не ниже); на рубеже круг на 1000 м до удара + 5 мин ({(t_['strike']['objective_s'] + 300) // 60} мин)")
    check(pg["sead2"].start_time == pg["sead"].start_time + build.RUNWAY_GAP_S,
          f"вторая пара взлетает через {build.RUNWAY_GAP_S} с после первой (не в одну секунду с одной полосы)")
    tgt = next(p for p in pg["strike"].points if p.name == "Цель")
    ipm = next(p for p in pg["strike"].points if p.name == "ИПМ")
    check(tgt.alt == 50 and ipm.alt == 300, "ударная группа: точка в зоне ЗРК - 50 м, вне зоны (ИПМ) - 300 м")
    check(attack_ids(pg["recon"]) == [], "доразведка: без AttackGroup по конкретной группе - цель ищет сама в районе")
    arm = {d["CLSID"] for d in pg["sead"].units[0].pylons.values()}
    want = {getattr(getattr(dcs.planes.Su_24M, f"Pylon{n}"), w)[1]["clsid"]
            for n, w in model.load_json("loadouts.json")["Su_24M"]["sead"]["pylons"].items()}
    check(pg["sead"].task == "SEAD" and arm == want, "Су-24М: задача DCS SEAD, подвеска ПРР из loadouts.json")
    roe = [t for p in pg["recon"].points for t in p.tasks if type(t).__name__ == "OptROE"]
    zone = [t for p in pg["recon"].points for t in p.tasks if getattr(t, "id", None) == "EngageTargetsInZone"]
    orbit = [t for p in pg["recon"].points for t in p.tasks if getattr(t, "id", None) == "ControlledTask"]
    center, radius_km = build.search_zone(st, st["units"]["blue_pzgren_bn_1"],
                                          build.timeline(model.doctrine(st, "red")["tasks"]["strike_column_march"], st, tk["package"], "strike")["recon"]["objective_s"], 3)
    check(not roe and len(zone) == 1 and abs(zone[0].params["zoneRadius"] - radius_km * 1000) < 1 and len(orbit) == 1
          and orbit[0].params.get("stopCondition", {}).get("duration") == 600,
          f"доразведка: поиск и поражение в районе радиусом {radius_km:.1f} км, круг 10 мин, без 'огня только в ответ'")
    opts = {type(t).__name__: t for t in pg["sead"].points[0].tasks}
    att = next(t for p in pg["sead"].points for t in p.tasks if getattr(t, "id", None) == "EngageGroup")
    check("OptReactOnThreat" in opts and "OptRestrictJettison" in opts
          and att.params["weaponType"] == dcs.task.WeaponType.ARM.value and att.params["groupAttack"] is True
          and att.params["expend"] == dcs.task.Expend.All.value,
          "Су-24М: залп ПРР всей группой (expend All), запрет сброса, только пассивная защита")
    pods = {n: d["CLSID"] for n, d in pg["sead"].units[0].pylons.items()}
    check(pods.get(5) == dcs.planes.Su_24M.Pylon5.L_081_Fantasmagoria_ELINT_pod[1]["clsid"], "Су-24М: контейнер 'Фантасмагория' на пилоне 5")
    jett = lambda g: any(type(t).__name__ == "OptRestrictJettison" for t in g.points[0].tasks)
    check(jett(pg["strike"]) and jett(pg["recon"]), "ударная группа и доразведка: запрет сброса подвески")
    check(pg["strike"].units[0].skill == dcs.unit.Skill.Player and pg["sead"].units[0].skill != dcs.unit.Skill.Player,
          "игрок - ведущий ударной группы, остальные звенья - ИИ")
    t = build.timeline(model.doctrine(st, "red")["tasks"]["strike_column_march"], st, tk["package"], "strike")
    check(t["strike"]["objective_s"] - t["sead"]["objective_s"] == 240 and t["strike"]["objective_s"] - t["recon"]["objective_s"] == 120,
          f"упреждение: подавление ПВО за 4 мин, доразведка за 2 мин до ударной группы (ОЦЕНКИ)")
    check(pg["sead"].start_time == t["sead"]["start_s"] and t["sead"]["late_s"] == 0,
          f"группа подавления ПВО взлетает через {t['sead']['start_s'] // 60} мин и успевает")

    # потери звена ИИ попадают в модель
    sead_units = next(fl["units"] for fl in man["flights"] if fl["group"] == "sead")
    sead_perf = next(fl["performer"] for fl in man["flights"] if fl["group"] == "sead")
    c0 = st["units"][sead_perf]["count"]
    debrief.apply(st, fake_hook(st["campaign_id"], man["sortie"], [sead_units[0]], {}, all_flight_units(man)))
    check(st["units"][sead_perf]["count"] == c0 - 1, f"дебриф: потеря в звене подавления ПВО списана со своей эскадрильи ({sead_perf})")

    # игрок в группе подавления ПВО
    st2 = model.new_campaign("pkg2", oob=BASE_OOB, sector=BASE_SECTOR)
    planner.plan(st2)
    build.build(st2, tmp / "pkg_sead.miz", fly="sead")
    m2 = dcs.Mission(Germany())
    m2.load_file(str(tmp / "pkg_sead.miz"))
    pg2 = {g.name.split(" ")[1]: g for g in plane_groups(m2)}
    check(pg2["sead"].units[0].skill == dcs.unit.Skill.Player and pg2["strike"].units[0].skill != dcs.unit.Skill.Player,
          "--fly sead: игрок ведёт группу подавления ПВО, ударная - ИИ")

    # обязательную группу подавления ПВО собрать не из кого - задачи нет
    oob = base_oob()
    oob["units"] = [u for u in oob["units"] if u["id"] != "red_bap_1"]
    oob["units"][0]["count"] = 3
    p = tmp / "oob_3.json"
    p.write_text(json.dumps(oob, ensure_ascii=False), encoding="utf-8")
    st3 = model.new_campaign("pkg3", oob=p, sector=BASE_SECTOR)
    check(planner.plan(st3) is None and "подавления ПВО" in st3["task_reason"],
          f"3 самолёта: удар в ПВО без подавления не ставится - {st3['task_reason']}")


def patriot_close_section(tmp: Path) -> None:
    """ЗРК, чья зона перекрывает рубеж пуска (Patriot рядом с маршрутом): ожидание на малой высоте, не на горке."""
    oob = base_oob()
    next(u for u in oob["units"] if u["id"] == "blue_patriot_1")["pos"] = {"lat": 53.10, "lon": 9.95}   # ~15 км от колонны
    p = tmp / "oob_patriot_close.json"
    p.write_text(json.dumps(oob, ensure_ascii=False), encoding="utf-8")
    st = model.new_campaign("pclose", oob=p, sector=BASE_SECTOR)
    tk = planner.plan(st)
    sead = next(g for g in tk["package"] if g["group"] == "sead")
    check(sorted(tk["threats"]) == ["blue_flak_1", "blue_patriot_1"] and set(sead["objective"]["units"]) == {"blue_flak_1", "blue_patriot_1"},
          "Patriot рядом с маршрутом: в коридоре, группа подавления - по обоим ЗРК")
    build.build(st, tmp / "pclose.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "pclose.miz"))
    g = next(g for g in plane_groups(m) if " sead " in g.name)
    vgs = {v.id: v.name for c in m.coalition["blue"].countries.values() for v in c.vehicle_group}
    holds = []
    for pt in g.points:
        eng = [vgs[t.params["groupId"]] for t in pt.tasks if getattr(t, "id", None) == "EngageGroup"]
        hold = [t for t in pt.tasks if getattr(t, "id", None) == "ControlledTask"]
        if eng:
            holds.append((sorted(eng), hold[0].params["task"]["params"]["altitude"]))
    check(holds == [(["blue_flak_1", "blue_patriot_1"], build.AI_LOW_MIN_M)],
          f"одно ожидание на рубеже по ближнему ЗРК, атака по обоим; круг на {build.AI_LOW_MIN_M} м - рубеж внутри зоны Patriot (60 км)")


def front_section(tmp: Path) -> None:
    """Фронт (0.4): марш до соприкосновения, бой за сутки, план дня, миссия по войскам в соприкосновении."""
    st = model.new_campaign("front")
    U = st["units"]
    tk = planner.plan(st)
    check([t["kind"] for t in st["tasks"]][0] == "strike_column_march" and tk["target"] == "blue_pzgren_bn_1"
          and "cas_contact" not in [t["kind"] for t in st["tasks"]],
          "день 1: в плане удар по колонне (боёв ещё нет), прикрытие своих колонн")
    sim.end_day(st)
    a, b = U["red_tp_1"], U["blue_pz_bn_1"]
    d = model.dist_km(model.unit_pos(st, a), model.unit_pos(st, b))
    check(a["state"] == b["state"] == "battle" and a["engaged"] == ["blue_pz_bn_1"] and b["engaged"] == ["red_tp_1"] and d <= 5.0,
          f"конец дня 1: танковый полк встретил танковый батальон (выдвинут командованием на рубеж) - соприкосновение на {d:.1f} км, марш остановлен")
    pw_a, pw_b = sim.power(st, a), sim.power(st, b)
    sa, sb = model.strength(a), model.strength(b)
    sim.end_day(st)
    fa = min(0.5, 0.15 * pw_b / pw_a) * (0.6 if a.get("defending") else 1)
    fb = min(0.5, 0.15 * pw_a / pw_b) * (0.6 if b.get("defending") else 1)
    check(abs((sa - model.strength(a)) - sa * fa) < 1e-6 and abs((sb - model.strength(b)) - sb * fb) < 1e-6,
          f"бой за сутки: потери одновременно, по соотношению сил ({pw_a:.1f} : {pw_b:.1f}); у обороны x0.6 (встречный бой - без) "
          f"- {sa:.0%}->{model.strength(a):.0%} и {sb:.0%}->{model.strength(b):.0%}")
    check(abs(model.strength(U["blue_flak_2"]) - model.strength(b)) < 1e-6, "приданная ПВО несёт потери вместе с частью")
    tasks = planner.plan(st) and st["tasks"]
    kinds = [t["kind"] for t in tasks]
    check(kinds and kinds[0] == "cas_contact" and all(t["package"][0]["objective"]["kind"] == "column" for t in tasks if t["kind"] == "cas_contact")
          and not any(g["group"] == "recon" for t in tasks if t["kind"] == "cas_contact" for g in t["package"]),
          f"день 3: в плане {len(tasks)} задач, первыми - войска в соприкосновении (без доразведки): "
          + ", ".join(t["title"].split(": ")[1] for t in tasks))
    n = next(i for i, t in enumerate(tasks, 1) if t["target"] == "blue_pz_bn_1")
    man = build.build(st, tmp / "front.miz", task_no=n)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "front.miz"))
    kinds = {g["unit"]: g["kind"] for g in man["ground"]}
    check(kinds.get("blue_pz_bn_1") == "battle" and kinds.get("red_tp_1") == "battle" and kinds.get("blue_flak_2") == "sam_site",
          f"миссия по задаче {n}: бой у Люнебурга - обе стороны боевыми порядками, ПВО при части позади ({len(man['ground'])} групп)")
    groups = materialize.window(st, st["task"])
    tgt = next(g for g in groups if g["unit"] == "blue_pz_bn_1")
    check(abs(sum(v["weight"] for v in tgt["vehicles"]) - sum(model.alive_by_type(b).values())) < 1e-6,
          "боевой порядок: сумма весов = исправной технике части (правило сохранения)")
    red = next(g for g in groups if g["unit"] == "red_tp_1")
    gap = model.dist_km(tgt["vehicles"][0], red["vehicles"][0])
    check(2.0 < gap < 4.5, f"передние линии сторон в {gap:.1f} км друг от друга - в дальности огня танков")
    vgs = {g.name: g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group}
    check(any(type(t).__name__ == "OptRestrictTargets" for t in vgs["blue_pz_bn_1/1"].points[0].tasks)
          and not any(type(t).__name__ == "OptRestrictTargets" for t in vgs["blue_flak_2"].points[0].tasks)
          and man["column_road"] == [], "в бою: огонь только по наземным, ПВО - без ограничения; перекладки на дорогу нет")
    allvg = {g.name: g for side_ in ("red", "blue") for c in m.coalition[side_].countries.values() for g in c.vehicle_group}
    bat = [g_ for g_ in groups if g_["kind"] == "battle"]
    ok_ = all((len(allvg[f"{g_['unit']}/1"].points) == 1) != g_["attack"] and
              (not g_["attack"] or [p.action.value for p in allvg[f"{g_['unit']}/1"].points[1:]] == ["Rank"]) for g_ in bat)
    check(ok_, "обороняющийся стоит, наступающий идёт развёрнутым строем на рубеж огня "
               f"({', '.join(g_['unit'] + (' наступает' if g_['attack'] else ' обороняется') for g_ in bat)})")
    zone = [t for g in plane_groups(m) if " strike " in g.name for p in g.points for t in p.tasks
            if getattr(t, "id", None) == "EngageTargetsInZone"]
    tc = Point.from_latlng(LatLng(tgt["center"]["lat"], tgt["center"]["lon"]), m.terrain)
    check(len(zone) == 1 and abs(zone[0].params["x"] - tc.x) < 1 and abs(zone[0].params["y"] - tc.y) < 1
          and zone[0].params["zoneRadius"] == build.BATTLE_ZONE_M,
          "ударная группа ИИ: удар по району боевого порядка части (взводы - отдельные группы)")
    pl = [g for g in vgs.values() if g.name.startswith("blue_pz_bn_1/")]
    roe = lambda g: [t.params["action"]["params"] for t in g.points[0].tasks if type(t).__name__ == "OptROE"]
    check(len(pl) == -(-len(tgt["vehicles"]) // build.PLATOON) and all(len(g.units) <= build.PLATOON for g in pl)
          and sorted(u.name for g in pl for u in g.units) == sorted(v["name"] for v in tgt["vehicles"])
          and all(roe(g) == [{"name": 0, "value": 4}] for g in pl),
          f"часть в бою - {len(pl)} взводов по {build.PLATOON}, имена машин из модели, огонь запрещён (ведёт front.lua)")
    front_lua_section(m, man, st)
    battle_site_section(tmp, m, man, st)
    s0 = model.strength(b)
    debrief.apply(st, fake_hook(st["campaign_id"], man["sortie"], [v["name"] for v in tgt["vehicles"][:5]], {}, all_flight_units(man)))
    lost = (s0 - model.strength(b)) * model.total(b)
    check(abs(lost - sum(v["weight"] for v in tgt["vehicles"][:5])) < 1e-6, f"дебриф: 5 машин боевого порядка = {lost:.2f} машин модели")
    ops_section(tmp)


def theatre_section(tmp: Path) -> None:
    """Весь театр в миссии (0.7): все части фронта и ЗРК; вдали - реже; вес машины ограничен; бои - каждый со своим местом."""
    st = model.new_campaign("th")
    for _ in range(3):
        sim.end_day(st)
    planner.plan(st)
    groups = materialize.theatre(st, st["task"])
    units = {g["unit"] for g in groups}
    want = {u["id"] for u in st["units"].values() if model.category(u) in ("ground", "sam") and u["state"] not in ("destroyed", "pending")
            and model.strength(u) > 0}
    check(want <= units, f"в миссии все части фронта и ЗРК: {len(units)} групп, машин {sum(len(g['vehicles']) for g in groups)}")
    ok = True
    for g in groups:
        u = st["units"][g["unit"]]
        if model.category(u) == "ground":
            ok &= abs(sum(v["weight"] for v in g["vehicles"]) - sum(model.alive_by_type(u).values())) < 1e-6
    wmax = max(v["weight"] for g in groups for v in g["vehicles"])
    check(ok and wmax <= materialize.MAX_WEIGHT + 1e-9, f"правило сохранения по всем частям; самая 'дорогая' машина - {wmax:.2f} машины модели")
    near = sum(len(g["vehicles"]) for g in groups if g["unit"] == st["task"]["target"])
    far = [len(g["vehicles"]) for g in groups if g.get("cluster") and st["task"]["target"] not in g["cluster"].split("+")
           and g["kind"] == "battle"]
    check(far and max(far) < near, f"цель игрока - {near} машин, части вдали - по {min(far)}-{max(far)}")
    keys = {g["cluster"] for g in groups if g.get("cluster")}
    man = build.build(st, tmp / "theatre.miz", task_no=1)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "theatre.miz"))
    s = next(a.text.id for a in m.triggerrules.triggers[0].actions if "redfront battle site" in a.text.id)
    check(set(man["battle_keys"]) == keys and all(f'key = "{k}"' in s for k in keys if any(g["kind"] == "battle" and g.get("cluster") == k for g in groups)),
          f"место по местности ищется для каждого боя и позиции отдельно ({len(keys)})")


def logistics_section(tmp: Path) -> None:
    """Тыл (0.8): снабжение, мосты, аэродромы, пополнение, удары по объектам тыла, учёт разрушений объектов карты."""
    from redfront import logistics, ops
    st = model.new_campaign("log")
    U = st["units"]
    # снабжение: склады синих уничтожены - синие части без снабжения, марш вдвое медленнее
    for d in ("blue_depot_1", "blue_depot_2"):
        U[d]["damage"] = 1.0
    logistics.supply(st)
    blue = [u for u in ops._maneuver(st, "blue")]
    red = [u for u in ops._maneuver(st, "red")]
    check(blue and all(u["supply"] < 1 for u in blue) and all(u["supply"] == 1 for u in red),
          "склады синих разрушены - синие части без снабжения, красные снабжаются")
    for _ in range(4):
        logistics.repairs(st)
    logistics.supply(st)
    check(all(u["supply"] == 1 for u in blue), f"склады восстанавливаются ({U['blue_depot_1']['damage']:.0%} через 4 суток) - снабжение вернулось")
    # мост: разрушен - связи закрыты, путь в обход; через 3 суток открыт
    U["br_lauenburg"]["damage"] = 1.0
    g = ops.graph(st)
    p_ = ops.path(st, "Lauenburg", "Luneburg")
    check("Luneburg" not in g["Lauenburg"] and "Winsen" not in g["Lauenburg"] and p_ and len(p_) > 2,
          f"мост у Лауэнбурга разрушен: связи закрыты, путь в обход ({' - '.join(p_)})")
    for _ in range(3):
        logistics.repairs(st)
    check(logistics.link_open(st, "Lauenburg", "Luneburg"), "мост восстановлен за 3 суток")
    # аэродром: противник рядом - закрыт, эскадрилья перебазируется
    U["blue_jbg_1"]["base"] = "fassberg"
    st["places"]["Munster"]["side"] = "red"
    lines = logistics.airfields(st)
    check(U["af_fassberg"]["state"] == "closed" and U["blue_jbg_1"]["base"] != "fassberg"
          and any("перебазирование" in ln for ln in lines),
          f"Мюнстер у красных - аэродром Фасберг (~10 км) закрыт, Tornado перебазированы в {st['airbases'][U['blue_jbg_1']['base']]['name']}")
    U["af_wunstorf"]["damage"] = 0.5
    U["blue_jbg_1"]["base"] = "wunstorf"
    check(logistics.available(st, U["blue_jbg_1"]) == U["blue_jbg_1"]["count"] // 2, "повреждённый аэродром - к вылету вдвое меньше самолётов")
    # пополнение
    U["red_shap_1"]["count"] = 6
    logistics.replacements(st); logistics.replacements(st)
    check(U["red_shap_1"]["count"] == 7, "пополнение эскадрилий: +1 ЛА за двое суток (ОЦЕНКА)")
    # удары по объектам тыла в плане дня
    st = model.new_campaign("log2")
    planner.plan(st)
    kinds = [t["kind"] for t in st["tasks"]]
    check({"strike_bridge", "strike_depot", "strike_airfield"} <= set(kinds),
          f"в плане дня удары по мосту, складу, аэродрому ({len(kinds)} задач)")
    n = kinds.index("strike_depot") + 1
    man = build.build(st, tmp / "depot.miz", task_no=n)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "depot.miz"))
    g = next(g for g in plane_groups(m) if " strike " in g.name)
    tasks_ = [getattr(t, "id", None) for p in g.points for t in p.tasks]
    script = next(a.text.id for a in m.triggerrules.triggers[0].actions if "redfront targets" in a.text.id)
    hook = next(a.text.id for a in m.triggerrules.triggers[0].actions if "redfront debrief hook" in a.text.id)
    check("Bombing" in tasks_ and st["task"]["target"] in man["objects"] and f'id = "{st["task"]["target"]}"' in script,
          "удар по складу: бомбометание по точке; склад - в списке целей миссии (объекты карты в его районе)")
    if not have_lupa():
        print("SKIP lupa не установлена: targets.lua и учёт разрушений не исполняются")
        return
    import lupa
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(r"""
      env = { info = function() end, warning = function() end }
      trigger = { action = { outText = function() end } }
      timer = { getTime = function() return 100 end, scheduleFunction = function() end }
      land = { getHeight = function() return 0 end }
      Object = { Category = { UNIT = 1, STATIC = 3, SCENERY = 5 } }
      world = { VolumeType = { SPHERE = 2 }, event = { S_EVENT_DEAD = 8, S_EVENT_CRASH = 5, S_EVENT_PILOT_DEAD = 9,
                S_EVENT_EJECTION = 6, S_EVENT_TAKEOFF = 3, S_EVENT_LAND = 4, S_EVENT_MISSION_END = 12 }, handlers = {} }
      SEQ = 0
      function world.searchObjects(cat, vol, f)          -- в каждом районе - 10 объектов карты
        for i = 1, 10 do SEQ = SEQ + 1; local nm = 1000 + SEQ; f({ getName = function() return nm end }) end   -- как в DCS: имя - число
      end
      function world.addEventHandler(h) world.handlers[#world.handlers + 1] = h end
      Unit = { getByName = function() return nil end }
      function scen(n) return { getName = function() return tonumber(n) end, getCategory = function() return 5 end } end
    """)
    outdir = tmp / "tgt_out"
    (outdir / "redfront").mkdir(parents=True, exist_ok=True)
    L.execute(f'lfs = {{ writedir = function() return "{outdir.as_posix()}/" end, mkdir = function() end }}')
    L.execute(script)
    L.execute(hook.replace('DIR .. "\\\\debrief_', 'DIR .. "/debrief_'))
    G = L.globals()
    tid = st["task"]["target"]
    names = [k for k, v in G.REDFRONT_TARGET_OF.items() if v == tid]
    for h in G.world.handlers.values():
        for nm_ in names[:4]:
            h.onEvent(h, L.table_from({"id": 8, "initiator": G.scen(nm_)}))
        h.onEvent(h, L.table_from({"id": 8, "initiator": G.scen("999999")}))     # посторонний объект карты - не в счёт
        h.onEvent(h, L.table_from({"id": 12}))
    out = json.loads(next((outdir / "redfront").glob("debrief_*.json")).read_text(encoding="utf-8"))
    check(out["targets"][tid] == [10, 4] and "999999" not in out["dead"],
          f"хук: в районе склада 10 объектов карты, разрушено 4; посторонние объекты карты не в счёт")
    debrief.apply(st, out)
    check(abs(st["units"][tid]["damage"] - 0.8) < 1e-9, f"дебриф: склад повреждён на {st['units'][tid]['damage']:.0%} (4 из 10 при пороге 50%)")
    # цель, уточнённая зондом: объекты по именам; в DCS getName объекта карты - число, в зонде - строка
    named = {"id": "br_named", "role": "bridge", "pos": st["units"][tid]["pos"], "map_objects": ["7003", "7004"]}
    L.execute("REDFRONT_TARGET_OF = {}; REDFRONT_TARGETS = {}; SEQ = 0\n"
              "function world.searchObjects(cat, vol, f) for i = 1, 6 do local nm = 7000 + i; "
              "f({ getName = function() return nm end, getTypeName = function() return 'CAR_BRIDGE_2LINE' end, "
              "getPoint = function() return { x = 0, y = 0, z = 0 } end }) end end")
    L.execute(build.targets_script(m, st, [named]))
    got = sorted(k for k, v in G.REDFRONT_TARGET_OF.items() if v == "br_named")
    check(got == ["7003", "7004"] and G.REDFRONT_TARGETS["br_named"].n == 2,
          f"цель по именам из зонда: числовые имена объектов карты DCS совпадают со строковыми ({got})")


def menu_section(tmp: Path) -> None:
    """Меню (run.bat): новая кампания, план, сборка, следующий день - вводом номеров."""
    import builtins
    from redfront import menu
    camp = tmp / "menu_camp.json"
    answers = iter([str(camp), "red", "5", "base",       # новая кампания
                    "2",                                  # план
                    "3", "1", "strike",                   # сборка: задача 1, группа strike
                    "5",                                  # конец дня
                    "0"])
    real = builtins.input
    builtins.input = lambda prompt="": next(answers)
    try:
        rc = menu.run(None, out_dir=tmp / "menu_missions")
    finally:
        builtins.input = real
    st = model.load(camp)
    check(rc == 0 and st["day"] == 2 and st["sortie"] == 1 and list((tmp / "menu_missions").glob("redfront_menu_camp_day1.miz")),
          "меню: новая кампания -> план -> сборка миссии -> конец дня, без набора команд")


def random_section(tmp: Path) -> None:
    """Случайность (0.6): повторяемость по seed, расхождение разных seed, варианты сценария, выключатель."""
    from redfront import ops
    def run(**kw):
        st = model.new_campaign("rnd", randomness=True, **kw)
        for _ in range(8):
            sim.end_day(st)
        return st, {u["id"]: round(model.strength(u), 4) for u in st["units"].values()}, \
               sorted(p for p in st["places"] if ops.owner(st, p) == "red")
    a1, s1, o1 = run(seed=11, variant="base")
    a2, s2, o2 = run(seed=11, variant="base")
    b1, s3, o3 = run(seed=12, variant="base")
    check(s1 == s2 and o1 == o2, "один seed - одна и та же кампания (повторяемо)")
    check(s1 != s3, f"другой seed - кампания расходится: красные держат {len(o1)} и {len(o3)} пунктов к 9-му дню")
    v = {model.new_campaign("v", randomness=True, seed=k)["scenario"]["variant"] for k in range(1, 30)}
    u = model.new_campaign("u", randomness=True, seed=5, variant="uelzen")
    check(v == {"base", "uelzen", "blue_early"} and u["objectives"]["red"][0] == "Uelzen"
          and u["units"]["red_msp_1"]["route"] == ["Dannenberg", "Uelzen"],
          f"варианты сценария выбираются случайно ({', '.join(sorted(v))}); --variant задаёт явно (uelzen: цель Ильцен)")
    days = {model.new_campaign("j", randomness=True, seed=k, variant="base")["units"]["red_tp_2"]["arrives_day"] for k in range(1, 30)}
    check(days == {4, 5, 6}, f"срок ввода резерва с разбросом: дни {sorted(days)}")
    n = model.new_campaign("n")
    check(n["scenario"]["variant"] == "base" and n["units"]["red_tp_2"]["arrives_day"] == 5 and model.rng(n, "x") is None,
          "без случайности: базовый вариант, сроки как в составе сил, генератор выключен")


def ops_section(tmp: Path) -> None:
    """Оперативный уровень (0.6): командование сторон, отход и восстановление, захват пунктов, резервы, цели операции."""
    from redfront import ops
    st = model.new_campaign("ops")
    log = []
    owners = []
    for _ in range(20):
        log += sim.end_day(st)
        planner.plan(st)
        owners.append({p for p in st["places"] if ops.owner(st, p) == "red"})
    U = st["units"]
    check(any("наступление на" in ln for ln in log) and any("выдвигается на рубеж" in ln for ln in log),
          "командование: красные (наступление) ставят частям задачи наступать, синие (оборона) - занимать рубежи")
    check(any("выходит из боя, отходит" in ln for ln in log) and any("восстановлена до" in ln for ln in log),
          "ослабевшие части выходят из боя, отходят в тыл и восстанавливаются")
    check(any("прибыл в район" in ln for ln in log) and U["red_tp_2"]["state"] != "pending" and U["blue_pzbrig_1"]["state"] != "pending",
          "резервы (второй эшелон, бригада) вводятся в свой день")
    took = sorted(owners[-1] - owners[0])
    check("Luneburg" in owners[-1] and len(took) >= 2, f"красные взяли пункты: {', '.join(took)}; за 20 дней кампания не встала")
    fl = ops.front_links(st)
    check(fl and all(ops.owner(st, a) != ops.owner(st, b) for a, b in fl), f"линия фронта: {len(fl)} связей между пунктами сторон")
    # отходящая часть разрывает соприкосновение и не держит пункт
    w = next((u for u in ops._maneuver(st) if u.get("order") == "withdraw"), None)
    check(w is None or w["state"] == "march", "отходящая часть - на марше, не в бою")


def front_lua_section(m, man: dict, st: dict) -> None:
    """front.lua в Lua с заглушками DCS: окна огня по противнику в дальности, запрет огня после окна, опция 28 не трогается,
    отход наступающего при потерях."""
    if not have_lupa():
        print("SKIP lupa не установлена: front.lua не исполняется")
        return
    import lupa, math
    script = next(a.text.id for a in m.triggerrules.triggers[0].actions if "redfront front" in a.text.id)
    groups = {g.name: g for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values())
              for g in c.vehicle_group if g.name in man["front"]}
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(r'''
      env = { info = function() end, warning = function() end }
      AI = { Option = { Ground = { id = { ROE = 0 }, val = { ROE = { OPEN_FIRE = 2, RETURN_FIRE = 3, WEAPON_HOLD = 4 } } } } }
      NOW = 0; Q = {}
      timer = { getTime = function() return NOW end,
                scheduleFunction = function(f, arg, t) Q[#Q + 1] = { f = f, arg = arg, t = t } end }
      function run_until(T)
        while true do
          local bi, bt = nil, nil
          for i, e in ipairs(Q) do if e.t <= T and (bt == nil or e.t < bt) then bi, bt = i, e.t end end
          if not bi then NOW = T; return end
          local e = table.remove(Q, bi); NOW = e.t
          local nt = e.f(e.arg, NOW)
          if nt then Q[#Q + 1] = { f = e.f, arg = e.arg, t = nt } end
        end
      end
      LOG = {}; DEAD = {}; G = {}
      function mkgroup(name, units)
        local ctl = { setOption = function(self, k, v) LOG[#LOG + 1] = { g = name, op = "opt", k = k, v = v, t = NOW } end,
                      pushTask = function(self, t) LOG[#LOG + 1] = { g = name, op = "push", task = t, t = NOW } end,
                      popTask = function(self) LOG[#LOG + 1] = { g = name, op = "pop", t = NOW } end,
                      setTask = function(self, t) LOG[#LOG + 1] = { g = name, op = "set", task = t, t = NOW } end }
        local us = {}
        for _, u in ipairs(units) do
          us[#us + 1] = { name = u.name, getPoint = function() return { x = u.x, y = 0, z = u.y } end,
                          isExist = function() return not DEAD[u.name] end, getLife = function() return DEAD[u.name] and 0 or 1 end }
        end
        G[name] = { isExist = function() return true end, getController = function() return ctl end,
                    getUnits = function() local out = {}; for _, x in ipairs(us) do if not DEAD[x.name] then out[#out + 1] = x end end; return out end }
      end
      Group = { getByName = function(n) return G[n] end }
      math.randomseed(7)
    ''')
    pos = {}
    for name, g in groups.items():
        # наступающий взвод - уже на рубеже огня (последняя точка маршрута): в начале миссии линии в 3 км, огня нет
        dx, dy = (g.points[-1].position.x - g.points[0].position.x, g.points[-1].position.y - g.points[0].position.y) \
            if len(g.points) > 1 else (0.0, 0.0)
        L.globals().mkgroup(name, L.table_from([L.table_from({"name": u.name, "x": u.position.x + dx, "y": u.position.y + dy})
                                                for u in g.units]))
        for u in g.units:
            pos[u.name] = (u.position.x + dx, u.position.y + dy)
    L.execute(script)
    G = L.globals()
    G.run_until(600)
    log = [dict(e) for e in G.LOG.values()]
    pushes = [e for e in log if e["op"] == "push"]
    opts = [e for e in log if e["op"] == "opt"]
    import re
    rng = {n: float(r) for n, r in re.findall(r'name = "([^"]+)", formation = "[^"]+", attack = \w+, range = (\d+)', script)}
    side = {name: c for c in ("red", "blue") for cc in m.coalition[c].countries.values() for g in cc.vehicle_group
            for name in [g.name] if name in groups}
    ok_target, ok_range = True, True
    for e in pushes:
        pt = e["task"]["params"]["point"]
        enemy = [pos[u.name] for n, g in groups.items() if side[n] != side[e["g"]] for u in g.units]
        own = [pos[u.name] for u in groups[e["g"]].units]
        cx, cy = sum(p[0] for p in own) / len(own), sum(p[1] for p in own) / len(own)
        tgt_ = min(enemy, key=lambda q: math.hypot(pt["x"] - q[0], pt["y"] - q[1]))
        ok_target &= math.hypot(pt["x"] - tgt_[0], pt["y"] - tgt_[1]) <= 80.01
        ok_range &= min(math.hypot(q[0] - cx, q[1] - cy) for q in enemy) <= rng[e["g"]]
    restored = all(any(o["g"] == e["g"] and o["k"] == 0 and o["v"] == 4 and 5.9 < o["t"] - e["t"] < 6.1 for o in opts)
                   for e in pushes if e["t"] < 590)      # окна в последние секунды ещё не закрыты
    check(len(pushes) > 20 and ok_target and ok_range and restored and not any(o["k"] == 28 for o in opts),
          f"front.lua: {len(pushes)} окон огня за 10 мин; точка прицеливания не дальше 80 м от машины противника в дальности оружия взвода; "
          "после окна - снова запрет огня; опция 28 (только наземные цели) не трогается")
    check(rng and max(rng.values()) <= build.FIRE_RANGE_MAX_M,
          f"дальность огня взводов не больше 3 км (ПТУР дальше не учитывается): макс. {max(rng.values()):.0f} м")
    shooters = {e["g"] for e in pushes}
    check(shooters <= set(groups), f"огонь ведут только взводы частей в бою ({len(shooters)} из {len(groups)})")
    # отход: у наступающего красного танкового полка убить 50% машин
    tp = [u.name for n, g in groups.items() if n.startswith("red_tp_1/") for u in g.units]
    for n in tp[: len(tp) // 2 + 1]:
        G.DEAD[n] = True
    G.run_until(700)
    sets = [dict(e) for e in G.LOG.values() if e["op"] == "set" and e["g"].startswith("red_tp_1/")]
    check(sets and "red_tp_1" in dict(G.REDFRONT_FRONT_LOG) and "отход" in G.REDFRONT_FRONT_LOG["red_tp_1"],
          f"наступающий при потерях в миссии отходит на исходную: {G.REDFRONT_FRONT_LOG['red_tp_1']}")


def battle_site_section(tmp: Path, m, man: dict, st: dict) -> None:
    """battle_site.lua с заглушками местности: место боя уходит от застройки и воды к дороге, машины не в воде и не на
    склоне, не теснее min_gap; взводы пересозданы с теми же именами и groupId; место пишется в дебриф и запоминается."""
    if not have_lupa():
        print("SKIP lupa не установлена: battle_site.lua не исполняется")
        return
    import lupa, math, re
    acts = m.triggerrules.triggers[0].actions
    script = next(a.text.id for a in acts if "redfront battle site" in a.text.id)
    hook = next(a.text.id for a in acts if "redfront debrief hook" in a.text.id)
    in_cl = {g["unit"] for g in man["ground"] if g["kind"] == "battle" and g.get("cluster") == man["battle_key"]}
    names = {n for n in man["front"] if n.split("/")[0] in in_cl}          # взводы боя цели игрока
    groups = {g.name: g for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values())
              for g in c.vehicle_group if g.name in names}
    xs = [u.position.x for g in groups.values() for u in g.units]
    ys = [u.position.y for g in groups.values() for u in g.units]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(r"""
      env = { info = function() end, warning = function() end }
      trigger = { action = { outText = function() end } }
      timer = { getTime = function() return 0 end, scheduleFunction = function() end }
      CX, CY = 0, 0
      land = { SurfaceType = { LAND = 1, SHALLOW_WATER = 2, WATER = 3, ROAD = 4, RUNWAY = 5 } }
      ROAD_X = 0                                  -- дорога: прямая x = ROAD_X через район боя
      function land.getSurfaceType(p)
        if (p.x - CX + 400) ^ 2 + (p.y - CY) ^ 2 < 300 ^ 2 then return 3 end          -- озеро у расчётного места
        if math.abs(p.x - ROAD_X) < 6 then return 4 end
        return 1
      end
      function land.getHeight(p)
        if math.abs(p.y - (CY - 1500)) < 400 then return 50 + (p.x - CX) * 0.5 end    -- склон к западу
        return 50
      end
      function land.getClosestPointOnRoads(kind, x, y) return ROAD_X, y end
      Object = { Category = { UNIT = 1, STATIC = 3, SCENERY = 5 } }
      world = { VolumeType = { SPHERE = 2 }, event = { S_EVENT_DEAD = 8, S_EVENT_CRASH = 5, S_EVENT_PILOT_DEAD = 9,
                S_EVENT_EJECTION = 6, S_EVENT_TAKEOFF = 3, S_EVENT_LAND = 4, S_EVENT_MISSION_END = 12 }, handlers = {} }
      BUILD = {}                                  -- застройка: квартал 1.2 x 1.2 км вокруг расчётного места, дом через 40 м
      for i = -15, 15 do for j = -15, 15 do BUILD[#BUILD + 1] = { x = CX + i * 40, y = CY + j * 40 } end end
      function world.searchObjects(cat, vol, f)
        local p, r = vol.params.point, vol.params.radius
        for _, b in ipairs(BUILD) do if (b.x - p.x) ^ 2 + (b.y - p.z) ^ 2 <= r * r then f() end end
      end
      function world.addEventHandler(h) world.handlers[#world.handlers + 1] = h end
      Unit = { getByName = function() return nil end }
      ADDED, OPTS = {}, {}
      Group = { Category = { GROUND = 2 }, getByName = function(n)
        return { getController = function() return { setOption = function(self, k, v)
          OPTS[n] = OPTS[n] or {}; OPTS[n][#OPTS[n] + 1] = { k, v } end } end } end }
      coalition = { addGroup = function(c, cat, d) ADDED[#ADDED + 1] = d end }
    """)
    G = L.globals()
    G.CX, G.CY = cx, cy
    G.ROAD_X = xs[0] + 30                        # дорога проходит в 30 м от одной из машин
    pat = next(g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group if g.name == "blue_patriot_1")
    px, py = pat.units[0].position.x, pat.units[0].position.y
    L.execute(f"for i = -6, 6 do for j = -6, 6 do BUILD[#BUILD + 1] = {{ x = {px} + i * 40, y = {py} + j * 40 }} end end")  # Patriot - в посёлке
    L.execute(f"""local base = land.getSurfaceType                   -- и через позицию Patriot идёт ВПП 3 км x 60 м
      function land.getSurfaceType(p)
        if math.abs(p.y - {py}) < 30 and math.abs(p.x - {px}) < 1500 then return 5 end
        return base(p)
      end""")
    L.execute(script)
    allg = {d.name: d for d in G.ADDED.values()}
    added = {n: d for n, d in allg.items() if n in names}
    ads = {n: d for n, d in allg.items() if n not in set(man["front"])}
    pts = [(u.x, u.y) for d in added.values() for u in d.units.values()]
    site = G.REDFRONT_SITES[man["battle_key"]]
    dx, dy = site.x, site.y
    wet = [p for p in pts if G.land.getSurfaceType(L.table_from({"x": p[0], "y": p[1]})) in (2, 3)]
    gap = min(math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1:])
    bld = lambda x, y: sum(1 for b in G.BUILD.values() if math.hypot(b.x - x, b.y - y) <= 30)
    in_town = sum(1 for p in pts if bld(*p) > 0)
    check(set(added) == names and all(int(added[n].groupId) == groups[n].id for n in names)
          and all(sorted(u.name for u in added[n].units.values()) == sorted(u.name for u in groups[n].units) for n in names),
          f"battle_site.lua: {len(added)} взводов пересозданы с теми же именами, groupId и машинами")
    slope = [p for p in pts if abs(p[1] - (cy - 1500)) < 400]
    check(math.hypot(dx, dy) >= 500 and not wet and not slope and gap >= 19.9 and in_town < len(pts) * 0.2,
          f"место боя ушло из квартала (сдвиг {dx:.0f}/{dy:.0f} м); в воде и на склоне 0 машин, "
          f"в застройке {in_town} из {len(pts)}, ближайшие машины в {gap:.0f} м")
    nominal = [(u.position.x + dx, u.position.y + dy) for g in groups.values() for u in g.units]
    near = [q for q in nominal if abs(q[0] - G.ROAD_X) <= 100]
    on_road = [q for q in pts if abs(q[0] - G.ROAD_X) < 6]
    check(len(near) >= 3 and len(on_road) >= len(near) * 0.5,
          f"машины, чья точка в 100 м от дороги, встают на дорогу: {len(on_road)} на дороге из {len(near)} рядом с ней")
    opts = {n: sorted((int(o[1]), int(o[2])) for o in G.OPTS[n].values()) for n in G.OPTS.keys()}
    check(all(opts.get(n) == [(0, 4), (28, 2)] for n in names), "после пересоздания: огонь запрещён, цели только наземные")
    adp = [(u.x, u.y) for d in ads.values() for u in d.units.values()]
    ad_names = {g["unit"] for g in man["ground"] if g["kind"] == "sam_site"}
    ad_gap = min(math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(adp) for b in adp[i + 1:])
    ad_bld = sum(1 for q in adp if any(math.hypot(b.x - q[0], b.y - q[1]) <= 60 for b in G.BUILD.values()))
    ad_road = sum(1 for q in adp if abs(q[0] - G.ROAD_X) < 6)
    ad_wet = [q for q in adp if G.land.getSurfaceType(L.table_from({"x": q[0], "y": q[1]})) in (2, 3)]
    adg = {g.name: g for c in list(m.coalition["red"].countries.values()) + list(m.coalition["blue"].countries.values())
           for g in c.vehicle_group if g.name in ad_names}
    follows = set(re.findall(r'name = "([^"]+)", groupId = \d+, country = \d+, follow = "', script))   # ПВО частей в бою - со сдвигом места боя
    ad_nom = [(u.position.x + (dx if n in follows else 0), u.position.y + (dy if n in follows else 0)) for n, g in adg.items() for u in g.units]
    ad_town0 = sum(1 for q in ad_nom if any(math.hypot(b.x - q[0], b.y - q[1]) <= 60 for b in G.BUILD.values()))
    town = max(sum(1 for b in G.BUILD.values() if math.hypot(b.x - q[0], b.y - q[1]) <= 150) for q in adp)
    check(town < build.SITE_CFG["ad_town_n"], f"ПВО не в городе: у любой машины ПВО строений ближе 150 м - {town} "
                                             f"(меньше {build.SITE_CFG['ad_town_n']})")
    rw_m = min(math.hypot(max(0.0, abs(q[0] - px) - 1500), max(0.0, abs(q[1] - py) - 30)) for q in adp)
    check(rw_m >= 149.9, f"ПВО не на аэродроме: Patriot стоял на ВПП - позиция сдвинута, до бетона не меньше {rw_m:.0f} м "
                         f"({G.REDFRONT_SITE_LOG['blue_patriot_1']})")
    check(ad_town0 >= 4 and set(ads) == ad_names and ad_bld == 0 and ad_road == 0 and not ad_wet and ad_gap >= 79.9,
          f"ПВО ({len(adp)} машин, {len(ads)} групп; Patriot стоял в посёлке - у строений было {ad_town0}): на открытом месте - у строений 0, на дороге 0, в воде 0, "
          f"между машинами не меньше {ad_gap:.0f} м")
    # хук пишет место; дебриф запоминает; следующая сборка ставит бой туда же и уже не ищет
    outdir = tmp / "site_out"
    (outdir / "redfront").mkdir(parents=True, exist_ok=True)
    L.execute(f'lfs = {{ writedir = function() return "{outdir.as_posix()}/" end, mkdir = function() end }}')
    L.execute(hook.replace('DIR .. "\\\\debrief_', 'DIR .. "/debrief_'))
    for h in G.world.handlers.values():
        h.onEvent(h, L.table_from({"id": 12}))
    out = json.loads(next((outdir / "redfront").glob("debrief_*.json")).read_text(encoding="utf-8"))
    check(abs(out["sites"][man["battle_key"]][0] - dx) < 0.2 and "место боя сдвинуто" in out["site_log"][man["battle_key"]],
          "хук: выбранное место боя и итог расстановки - в файле дебрифа")
    import copy as _c
    st2 = _c.deepcopy(st)
    st2["manifest"]["applied"] = False
    debrief.apply(st2, out)
    man2 = build.build(st2, tmp / "front2.miz", task_no=next(i for i, t in enumerate(st2["tasks"], 1) if t["target"] == st["task"]["target"]))
    m2 = dcs.Mission(Germany())
    m2.load_file(str(tmp / "front2.miz"))
    s2 = next(a.text.id for a in m2.triggerrules.triggers[0].actions if "redfront battle site" in a.text.id)
    g2 = {g.name: g for c in list(m2.coalition["red"].countries.values()) + list(m2.coalition["blue"].countries.values())
          for g in c.vehicle_group if g.name in names}
    n0 = sorted(names)[0]
    moved = (g2[n0].units[0].position.x - groups[n0].units[0].position.x, g2[n0].units[0].position.y - groups[n0].units[0].position.y)
    check(st2["battle_sites"][man["battle_key"]] == {"x": round(dx, 1), "y": round(dy, 1)} or abs(st2["battle_sites"][man["battle_key"]]["x"] - dx) < 0.2,
          "дебриф: модель запомнила место боя")
    check("search_r = 0" in s2 and abs(moved[0] - dx) < 0.5 and abs(moved[1] - dy) < 0.5,
          f"следующий вылет: бой сразу на запомненном месте (сдвиг {moved[0]:.0f}/{moved[1]:.0f} м), место заново не ищется")


def air_section(tmp: Path) -> None:
    """Воздушная война (0.5): прикрытие в пакете, задача прикрытия войск, авиация противника в миссии и её потери."""
    st = model.new_campaign("air")
    sim.end_day(st)
    planner.plan(st)
    t1 = st["tasks"][0]
    cov = [g for g in t1["package"] if g["group"] == "cover"]
    check(cov and cov[0]["performer"] == "red_iap_1" and cov[0]["objective"]["kind"] == "cover_zone",
          "истребители противника достают до цели - в пакете группа прикрытия МиГ-29")
    man = build.build(st, tmp / "air1.miz", task_no=1)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "air1.miz"))
    red = {g.name.split(" ")[1]: g for g in plane_groups(m)}
    blue = [g for c in m.coalition["blue"].countries.values() for g in c.plane_group]
    t = build.timeline(model.doctrine(st, "red")["tasks"][t1["kind"]], st, t1["package"], "strike")
    zone = [x for p in red["cover"].points for x in p.tasks if getattr(x, "id", None) == "EngageTargetsInZone"]
    orb = [x for p in red["cover"].points for x in p.tasks if getattr(x, "id", None) == "ControlledTask"]
    check(zone and list(dict(zone[0].params["targetTypes"]).values()) == ["Air"] and orb and orb[0].params["stopCondition"] == {"time": t["strike"]["objective_s"] + 300}
          and red["cover"].points[1].alt == 3000
          and {d["CLSID"] for d in red["cover"].units[0].pylons.values()} >= {dcs.planes.MiG_29_Fulcrum.Pylon3.R_27R__AA_10_Alamo_A____Semi_Act_Rdr_[1]["clsid"]},
          f"прикрытие: зона 40 км над целью на 3000 м, перехват воздушных целей, до удара + 5 мин; МиГ-29 с Р-27Р и Р-73")
    en = [fl for fl in man["flights"] if fl.get("side") == "blue"]
    own_ai = [fl for fl in man["flights"] if fl["group"].startswith("ai")]
    from redfront import ato
    win = [e for e in st["ato"]["entries"] if e["id"] != st["task"].get("ato_id") and not e["ai_only"]
           and ato.in_window(e, man["start_s"], man["end_s"])
           and not (e["times"]["strike"]["takeoff_s"] < man["start_s"] and e["times"]["strike"]["objective_s"] <= man["start_s"] + 60)]
    want = {side_: min(build.AI_FLIGHTS["enemy" if side_ == "blue" else "own"], sum(1 for e in win if e["side"] == side_))
            for side_ in ("red", "blue")}
    check(len(blue) == len(en) == len(man["enemy_lines"]) and 1 <= len(en) <= build.AI_FLIGHTS["enemy"]
          and len(en) <= want["blue"] and len(own_ai) <= want["red"] and len(man["ai_lines"]) == len(own_ai)
          and "Разведка: в районе возможна активность авиации противника." in m.description_text()
          and ("Другие вылеты наших сил" in m.description_text()) == bool(own_ai)
          and not any(st["units"][fl["performer"]]["name"] in m.description_text() for fl in en),
          f"воздушная война по плану полётов на сутки: в окне миссии {ato.hhmm(man['start_s'])}-{ato.hhmm(man['end_s'])} "
          f"{len(en)} групп противника и {len(own_ai)} своих групп ИИ (в окне вылетов: синих {want['blue']}, своих {want['red']}); "
          "свои - в брифинге, противник - только общим предупреждением")
    used = {}
    for g_ in st["task"]["package"]:
        used[g_["performer"]] = used.get(g_["performer"], 0) + g_["size"]
    for fl in man["flights"]:
        if fl["group"].startswith(("ai", "enemy")):
            used[fl["performer"]] = used.get(fl["performer"], 0) + len(fl["units"])
    check(all(n_ <= st["units"][k]["count"] for k, n_ in used.items()), f"самолёты эскадрилий не расходуются сверх наличия: {used}")
    allp = [g_ for side_ in ("red", "blue") for c in m.coalition[side_].countries.values() for g_ in c.plane_group]
    leak = [g_.name for g_ in allp if g_.units[0].skill != dcs.unit.Skill.Player
            and any(getattr(t_, "id", None) == "EngageTargets" for t_ in g_.points[0].tasks)]
    check(not leak, "у групп ИИ нет 'поражать цели по пути' от основной задачи DCS - только своя задача")
    jg0 = st["units"]["blue_jg_1"]["count"]
    jg = next(fl for fl in en if fl["performer"] == "blue_jg_1") if any(fl["performer"] == "blue_jg_1" for fl in en) else en[0]
    c0 = st["units"][jg["performer"]]["count"]
    debrief.apply(st, fake_hook(st["campaign_id"], man["sortie"], [jg["units"][0]], {}, all_flight_units(man)))
    check(st["units"][jg["performer"]]["count"] == c0 - 1, f"дебриф: сбитый ЛА противника списан с его эскадрильи ({jg['performer']})")
    # задача прикрытия войск - игрок на МиГ-29
    planner.plan(st)
    n = next(i for i, x in enumerate(st["tasks"], 1) if x["kind"] == "cap_own_troops")
    man2 = build.build(st, tmp / "air2.miz", task_no=n)
    m2 = dcs.Mission(Germany())
    m2.load_file(str(tmp / "air2.miz"))
    g2 = next(g for g in plane_groups(m2) if " strike " in g.name)
    orb2 = [x for p in g2.points for x in p.tasks if getattr(x, "id", None) == "ControlledTask"]
    t2 = build.timeline(model.doctrine(st, "red")["tasks"]["cap_own_troops"], st, st["task"]["package"], "strike")
    check(g2.units[0].type == "MiG-29 Fulcrum" and g2.units[0].skill == dcs.unit.Skill.Player and g2.task == "CAP"
          and orb2[0].params["stopCondition"] == {"time": t2["strike"]["objective_s"] + 25 * 60} and g2.points[1].alt == 4000,
          f"задача {n} 'прикрытие войск': игрок ведёт пару МиГ-29, зона на 4000 м, 25 мин; противник в районе: {len(man2['enemy_lines'])} групп")


def column_road_section(tmp: Path) -> None:
    """Перекладка колонны на дорогу в начале миссии (column_road.lua) + хук + дебриф, запоминающий дороги."""
    import math
    st = model.new_campaign("colroad", oob=BASE_OOB, sector=BASE_SECTOR)
    bn = st["units"]["blue_pzgren_bn_1"]
    planner.plan(st)
    man = build.build(st, tmp / "colroad.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "colroad.miz"))
    trig = m.triggerrules.triggers[0]
    heads = [a.text.id.splitlines()[0].split(" | ")[0] for a in trig.actions]
    check(man["column_road"] == ["blue_pzgren_bn_1", "blue_flak_1"]
          and heads == ["-- redfront column-on-road", "-- redfront battle site", "-- redfront targets", "-- redfront debrief hook"],
          "без известных дорог: в триггере старта скрипт перекладки колонны, затем хук")
    if not have_lupa():
        print("SKIP lupa не установлена: перекладка колонны в Lua не исполняется")
        return
    import lupa
    vg = next(g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group if g.name == "blue_pzgren_bn_1")
    col = man["ground"][0]
    col_lua, hook_lua = trig.actions[0].text.id, trig.actions[-1].text.id    # скрипты ровно такие, как в собранном .miz

    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.globals().py_detour = lambda x1, y1, x2, y2: detour(Point(x1, y1, None), Point(x2, y2, None), 1500.0)
    L.execute(r'''
      env = { info = function() end, warning = function() end }
      trigger = { action = { outText = function() end } }
      NOW = 0
      timer = { getTime = function() return NOW end, scheduleFunction = function() end }
      Group = { Category = { AIRPLANE = 0, HELICOPTER = 1, GROUND = 2 } }
      ADDED = {}
      coalition = { addGroup = function(c, cat, data) ADDED[#ADDED + 1] = { c = c, cat = cat, data = data } end }
      OPTS = {}
      function Group.getByName(n)
        return { getController = function() return { setOption = function(self, k, v)
          OPTS[n] = OPTS[n] or {}; OPTS[n][#OPTS[n] + 1] = { k, v } end } end }
      end
      land = {}
      function land.getClosestPointOnRoads(kind, x, y) return x, y end
      function land.findPathOnRoads(kind, x1, y1, x2, y2)
        local out = {}
        for p in python.iter(py_detour(x1, y1, x2, y2)) do out[#out + 1] = { x = p[0], y = p[1] } end
        return out
      end
      world = { event = { S_EVENT_DEAD = 8, S_EVENT_CRASH = 5, S_EVENT_PILOT_DEAD = 9, S_EVENT_EJECTION = 6,
                          S_EVENT_TAKEOFF = 3, S_EVENT_LAND = 4, S_EVENT_MISSION_END = 12 }, handlers = {} }
      function world.addEventHandler(h) world.handlers[#world.handlers + 1] = h end
      Unit = { getByName = function(n) return nil end }
      Object = { Category = { UNIT = 1, STATIC = 3, SCENERY = 5 } }
      function obj(n) return { getName = function() return n end, getCategory = function() return 1 end } end
      function fire(id, n) for _, h in ipairs(world.handlers) do h:onEvent({ id = id, initiator = n and obj(n) or nil }) end end
    ''')
    outdir = tmp / "colroad_out"
    (outdir / "redfront").mkdir(parents=True, exist_ok=True)
    L.execute(f'lfs = {{ writedir = function() return "{outdir.as_posix()}/" end, mkdir = function() end }}')
    L.execute(col_lua)
    L.execute(hook_lua.replace('DIR .. "\\\\debrief_', 'DIR .. "/debrief_'))
    G = L.globals()
    added = list(G.ADDED.values())
    check([x.data.name for x in added] == ["blue_pzgren_bn_1", "blue_flak_1"], "addGroup: батальон и войсковая ПВО")
    opts = {n: [(int(o[1]), int(o[2])) for o in G.OPTS[n].values()] for n in G.OPTS.keys()}
    check(opts == {"blue_pzgren_bn_1": [(28, 2)]},
          "после пересоздания: батальону заново 'огонь только по наземным целям', ПВО - без ограничения")
    a = added[0]
    data = a.data
    units = [data.units[i] for i in range(1, len(data.units) + 1)]
    country = m.country(build.MISSION_COUNTRIES["blue"])     # страна стороны в миссии - CJTF Blue
    check(data.name == "blue_pzgren_bn_1" and int(data.groupId) == vg.id and int(a.c) == country.id and int(a.cat) == 2,
          f"группа пересоздана с тем же именем, groupId {vg.id} и страной {country.name}")
    check([u.name for u in units] == [v["name"] for v in col["vehicles"]]
          and all(u.type == dcstypes_id(v["type"]) for u, v in zip(units, col["vehicles"])),
          f"те же {len(units)} машин, те же имена и типы, тот же порядок")
    pair = "Munster>Amelinghausen"
    path = [(G.REDFRONT_ROADS[pair][i].x, G.REDFRONT_ROADS[pair][i].y) for i in range(1, len(G.REDFRONT_ROADS[pair]) + 1)]
    def off_m(x, y):
        best = 1e18
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + dx * t - x, ay + dy * t - y))
        return best
    worst = max(off_m(u.x, u.y) for u in units)
    gaps = [math.hypot(units[i].x - units[i + 1].x, units[i].y - units[i + 1].y) for i in range(len(units) - 1)]
    flak = man["ground"][1]
    fu = [added[1].data.units[i] for i in range(1, len(added[1].data.units) + 1)]
    n_gap = len(flak["vehicles"])
    big = [g_ for g_ in gaps if g_ > 50.01]
    check(worst < 1.0 and max(off_m(u.x, u.y) for u in fu) < 1.0 and all(45 < g_ <= 50.01 for g_ in gaps if g_ not in big)
          and len(big) == 1 and abs(big[0] - 50 * (n_gap + 1)) < 1.0,
          f"машины на дороге (худшая {worst:.2f} м), дистанция {min(gaps):.0f}-50 м, за танками разрыв {big[0]:.0f} м под ПВО")
    allu = units + fu
    near = min(math.hypot(p_.x - q_.x, p_.y - q_.y) for i, p_ in enumerate(allu) for q_ in allu[i + 1:])
    check(near > 45, f"ПВО встала в разрыв: ближайшие машины двух групп в {near:.0f} м, наложений нет")
    check(len(list(G.REDFRONT_ROADS.keys())) == 3, "найдены дороги всех 3 оставшихся участков маршрута")
    pts = list(data.route.points.values())
    check(all(p.action == "On Road" for p in pts) and len(pts) == 1 + len(col_waypoints(vg)), "маршрут пересозданной группы - по дорогам")

    # хук: 'гибель' старых машин при замене группы - не потери; настоящая потеря позже - потеря
    ev = G.world.event
    G.fire(ev.S_EVENT_DEAD, col["vehicles"][0]["name"])
    G.NOW = 30
    G.fire(ev.S_EVENT_DEAD, col["vehicles"][5]["name"])
    G.fire(ev.S_EVENT_MISSION_END, None)
    out = json.loads(next((outdir / "redfront").glob("debrief_*.json")).read_text(encoding="utf-8"))
    check(out["dead"] == [col["vehicles"][5]["name"]], "хук: 'гибель' при замене группы (первые 5 с) не засчитана, потеря на 30 с - засчитана")
    check(set(out["roads"]) == {"Munster>Amelinghausen", "Amelinghausen>Luneburg", "Luneburg>Dahlenburg"}
          and "на дороге" in out["column_log"]["blue_pzgren_bn_1"], "хук: дороги и итог перекладки записаны в файл дебрифа")

    # дебриф запоминает дороги; следующая миссия колонну не перекладывает - она уже на дороге
    lines = debrief.apply(st, out)
    check(len(st.get("roads", {})) == 3 and any("участков по дорогам 3 из 3" in ln for ln in lines),
          "дебриф: модель запомнила дороги всех 3 участков")
    from redfront import sim
    sim.end_day(st)
    planner.plan(st)
    man2 = build.build(st, tmp / "colroad2.miz")
    m2 = dcs.Mission(Germany())
    m2.load_file(str(tmp / "colroad2.miz"))
    check(man2["column_road"] == [] and not any("column-on-road" in a.text.id for a in m2.triggerrules.triggers[0].actions),
          "следующая миссия: дороги известны, колонна сразу на дороге, скрипт перекладки не нужен")


def col_waypoints(vg) -> list:
    return vg.points[1:]


def dcstypes_id(type_name: str) -> str:
    from redfront import dcstypes
    return dcstypes.vehicle(type_name).id


def roads_section(tmp: Path) -> None:
    import math
    terrain = Germany()
    # ---- служебная миссия ----
    pr = roads.probe(tmp / "roads_probe.miz", oob=BASE_OOB, sector=BASE_SECTOR)
    check(pr["sector"] == "hamburg" and len(pr["pairs"]) == 3, f"зонд дорог: сектор hamburg, участки {', '.join(pr['pairs'])}")
    mp = dcs.Mission(Germany())
    mp.load_file(str(tmp / "roads_probe.miz"))
    check(len(mp.triggerrules.triggers) == 1, "зонд дорог: .miz собран и читается, скрипт в триггере старта")

    sec = model.load_json("sector_hamburg.json")
    pt = lambda n: Point.from_latlng(LatLng(sec["places"][n]["lat"], sec["places"][n]["lon"]), terrain)
    script = roads.probe_script("hamburg", sec["places"], [tuple(p.split(">")) for p in pr["pairs"]])
    if have_lupa():
        out = run_probe(script, tmp / "probe", "Luneburg>Dahlenburg")
        raw = json.loads(out["file"].read_text(encoding="utf-8"))
        check(set(raw["paths"]) == {"Munster>Amelinghausen", "Amelinghausen>Luneburg"} and "Luneburg>Dahlenburg" in raw["errors"],
              "зонд в Lua: 2 пути записаны, 1 ошибка ('дорога не найдена') записана отдельно")
        roads_file = out["file"]
    else:
        print("SKIP lupa не установлена: скрипт зонда не исполняется, файл дорог собран в Python")
        raw = {"sector": "hamburg", "errors": {"Luneburg>Dahlenburg": "путь по дорогам не найден"},
               "paths": {f"{a}>{b}": detour(pt(a), pt(b), 1500.0) for a, b in (("Munster", "Amelinghausen"), ("Amelinghausen", "Luneburg"))}}
        roads_file = tmp / "roads_hamburg.json"
        roads_file.write_text(json.dumps(raw), encoding="utf-8")

    # ---- применение к кампании ----
    st = model.new_campaign("roads", oob=BASE_OOB, sector=BASE_SECTOR)
    bn = st["units"]["blue_pzgren_bn_1"]
    pos0 = model.unit_pos(st, bn)
    len0 = model.route_length_km(model.route_points(st, bn))
    lines = roads.apply(st, roads.load(roads_file))
    pts = model.route_points(st, bn)
    near_km = min(planner._seg_dist_km(pos0, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    moved_km = model.dist_km(pos0, model.unit_pos(st, bn))
    check(abs(moved_km - near_km) < 0.01,
          f"дороги применены: голова колонны переехала в ближайшую точку дороги ({moved_km * 1000:.0f} м), пройдено {bn['progress_km']:.2f} км")
    check(model.route_length_km(pts) > len0 + 0.3, f"маршрут по дорогам длиннее прямых: {model.route_length_km(pts):.2f} км против {len0:.2f}")
    check(any("Luneburg>Dahlenburg" in ln for ln in lines), "участок без дороги остаётся прямой, об этом есть строка в журнале")

    col = materialize.column(st, bn)
    def off_route_m(v):
        return min(planner._seg_dist_km(v, pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * 1000
    worst = max(off_route_m(v) for v in col["vehicles"])
    check(worst < 5.0, f"колонна стоит на дороге: худшая машина в {worst:.1f} м от ломаной")
    check(len(col["waypoints"]) == 3, f"путевые точки колонны - оставшиеся пункты маршрута ({len(col['waypoints'])}), а не {len(pts)} вершин дороги")
    planner.plan(st)
    man = build.build(st, tmp / "roads_d1.miz")
    check(man["ground"][0]["kind"] == "column", "миссия с дорогами собирается")

    # дебриф: уцелевшие машины уехали на 3 км вперёд по дороге
    names = [v["name"] for v in man["ground"][0]["vehicles"]]
    positions = {}
    for i, n in enumerate(names):
        p, _ = model.point_at_km(pts, bn["progress_km"] + 3.0 - i * 0.05)
        q = Point.from_latlng(LatLng(p["lat"], p["lon"]), terrain)
        positions[n] = (q.x, q.y)
    km0 = bn["progress_km"]
    debrief.apply(st, fake_hook(st["campaign_id"], man["sortie"], [], positions, all_flight_units(man)))
    check(2.9 < bn["progress_km"] - km0 < 3.1, f"дебриф с дорогами: продвижение вдоль дороги {bn['progress_km'] - km0:.2f} км")


def mapobj_section(tmp: Path) -> None:
    """Зонд карты: выбор моста на линии связи, имена пролётов в скрипт целей."""
    from redfront import mapobj
    print("\n== объекты карты ==")
    terrain = Germany()
    xy = lambda lat, lon: (lambda q: (q.x, q.y))(Point.from_latlng(LatLng(lat, lon), terrain))
    b = 53 + 21 / 60 + 56 / 3600; l = 10 + 33 / 60 + 35 / 3600          # Эльба у Лауэнбурга, по редактору
    raw = {"sector": "hamburg", "bridges": {
        "br_lauenburg": [["111", "rw_bridge_2line", *xy(b, l)], ["112", "rw_bridge_2line", *xy(b + 0.0008, l + 0.0012)],
                         ["300", "bridge_small", *xy(53.3745, 10.575)], ["400", "rw_bridge_2line", *xy(53.39, 10.52)]],
        "br_doemitz": []}, "depots": {"red_depot_1": {"house": [10, 0.0, 0.0]}}, "errors": {}}
    dl = model.load_json("sector_hamburg.json")
    d1 = next(d for d in dl["depots"] if d["id"] == "red_depot_2")
    c0 = dl["places"][d1["place"]]
    raw["depot_objects"] = {"red_depot_2": [
        [str(900 + i), t, *xy(c0["lat"] + 0.012 + i * 0.0003, c0["lon"] + 0.008 + (i % 2) * 0.0004)]
        for i, t in enumerate(("silo_01", "silo_01", "silo_03", "stock", "safshungar02"))]
        + [["990", "stock", *xy(c0["lat"] - 0.01, c0["lon"])]],               # одиночный склад в стороне - не в счёт
        "red_depot_1": [["991", "silo_01", *xy(53.3, 11.5)]]}                  # один объект - не склад
    f = tmp / "map_hamburg.json"
    f.write_text(json.dumps(raw), encoding="utf-8")
    pr = mapobj.load(f)
    st = model.new_campaign("map", seed=5)
    lines = mapobj.apply(st, pr)
    br = st["units"]["br_lauenburg"]
    check(sorted(br.get("map_objects", [])) == ["111", "112"] and br.get("pos_checked"),
          "мост: выбраны пролёты на связи Лауэнбург-Люнебург (не канал, не дальний мост) - " + lines[0])
    check(not st["units"]["br_doemitz"].get("pos_checked"), "мост без объектов карты рядом остаётся по оценке")
    sec_ = model.load_json("sector_hamburg.json")
    mapobj.apply(sec_, pr)
    check(sec_["bridges"][0].get("map_objects") == br["map_objects"], "то же применяется к файлу сектора")
    s = build.targets_script(dcs.Mission(Germany()), st, [br])
    check('names = { ["111"] = true, ["112"] = true }' in s, "скрипт целей получает имена пролётов моста")
    d2 = st["units"]["red_depot_2"]
    check(sorted(d2.get("map_objects", [])) == [str(900 + i) for i in range(5)] and d2.get("pos_checked")
          and model.dist_km(d2["pos"], c0) > 1.0,
          "склад: скопление silo/stock/ангар у пункта, точка цели - его центр; одиночный объект в стороне не в счёт")
    check(not st["units"]["red_depot_1"].get("pos_checked"), "склад из одного объекта не принят - остаётся по оценке")
    s = build.targets_script(dcs.Mission(Germany()), st, [d2])
    check("r = 500" in s and '["904"] = true' in s, "скрипт целей: склад по именам объектов, радиус с запасом")
    # ручное назначение - зоны "Assign as..." с ROLE/VALUE
    mz = dcs.Mission(Germany())
    for i, (oid, role, val) in enumerate((("134455908", "depot", "blue_depot_1"), ("95690838", "depot", "blue_depot_1"),
                                          ("777", "bridge", "br_doemitz"), ("555", "", ""))):
        q = Point.from_latlng(LatLng(53.0 + i * 0.001, 10.0), Germany())
        props = [{"key": "ROLE", "value": role}, {"key": "VALUE", "value": val},
                 {"key": "OBJECT ID", "value": oid}, {"key": "NAME", "value": "silo_01"}]
        mz.triggers.add_triggerzone_quad(q, [Point(q.x + dx, q.y + dy, mz.terrain) for dx, dy in ((5, 5), (5, -5), (-5, -5), (-5, 5))],
                                         name=f"z{i}", properties=props)
    mz.save(str(tmp / "assign.miz"))
    lines = mapobj.import_miz(st, tmp / "assign.miz")
    b1, dm = st["units"]["blue_depot_1"], st["units"]["br_doemitz"]
    check(sorted(b1.get("map_objects", [])) == ["134455908", "95690838"] and dm.get("map_objects") == ["777"]
          and abs(b1["pos"]["lat"] - 53.0005) < 1e-3, "Assign as...: ROLE/VALUE назначают объекты карты складу и мосту - "
          + "; ".join(lines))
    probe = mapobj.probe(tmp / "map_probe.miz")
    check(probe["tiles"] > 50 and Path(probe["file"]).exists(), f"служебная миссия зонда всего сектора собрана: ячеек {probe['tiles']}")
    # зонд всего сектора: мосты с признаком "над водой", все объекты складов
    pl = sec_["places"]
    mid = lambda a, b: ((pl[a]["lat"] + pl[b]["lat"]) / 2, (pl[a]["lon"] + pl[b]["lon"]) / 2)
    link = next(l for l in sec_["links"] if not any(set(l) == set(x) for br in sec_["bridges"] for x in br["links"]))
    m1 = mid(*link)
    far = next(n for n in pl if model.dist_km(pl[n], {"lat": m1[0], "lon": m1[1]}) > 15)
    rawall = {"sector": "hamburg",
              "bridges_all": [["111", "rw_bridge_2line", *xy(b, l), 1], ["112", "rw_bridge_2line", *xy(b + 0.0008, l + 0.0012), 1],
                              ["500", "bridge_road", *xy(*m1), 1], ["501", "bridge_road", *xy(m1[0] + 0.001, m1[1]), 0]],
              "depot_objects_all": [[str(700 + i), "silo_01", *xy(pl[far]["lat"] + 0.01 + i * 0.0003, pl[far]["lon"])] for i in range(4)],
              "depots": {}, "errors": {}}
    fac = next(n for n in pl if pl[n].get("side") == "blue" and n != far)          # завод синих - цель для красных
    rawall["factory_objects_all"] = [[str(800 + i), "industrial_eu_0%d" % (i % 4 + 1), *xy(pl[fac]["lat"] - 0.008 + i * 0.0006, pl[fac]["lon"] + 0.004)]
                                     for i in range(5)] + [["899", "industrial_baltic_02", *xy(pl[fac]["lat"] + 0.03, pl[fac]["lon"])]]
    f2 = tmp / "map_hamburg_all.json"
    f2.write_text(json.dumps(rawall), encoding="utf-8")
    pr2 = mapobj.load(f2)
    st2 = model.new_campaign("map2", seed=5)
    lines = mapobj.apply(st2, pr2)
    nb = [u for u in st2["units"].values() if u.get("role") == "bridge" and u.get("found")]
    check(len(nb) == 1 and nb[0]["links"] == [list(link)] and nb[0]["map_objects"] == ["500"],
          f"новый мост над водой на связи {link[0]}-{link[1]} (мост не над водой не взят): " + "; ".join(l for l in lines if "новый мост" in l))
    check(sorted(st2["units"]["br_lauenburg"]["map_objects"]) == ["111", "112"], "известный мост уточнён из зонда всего сектора")
    nd = [u for u in st2["units"].values() if u.get("role") == "depot" and u.get("found")]
    has_depot = any(d.get("place") == far for d in sec_["depots"])
    check((len(nd) == 0) if has_depot else (len(nd) == 1 and nd[0]["place"] == far and nd[0]["side"] == st2["places"][far]["side"]),
          f"новый склад у пункта {far} из скопления объектов: " + "; ".join(l for l in lines if "новый склад" in l))
    nf = [u for u in st2["units"].values() if u.get("role") == "factory"]
    check(len(nf) == 1 and nf[0]["place"] == fac and nf[0]["side"] == "blue" and len(nf[0]["map_objects"]) == 5,
          f"завод из скопления industrial_* у пункта {fac} (отдельный корпус в стороне не в счёт): "
          + "; ".join(l for l in lines if "новый завод" in l))
    from redfront import logistics
    f0 = logistics.industry(st2, "blue")
    nf[0]["damage"] = 1.0
    check(f0 == 1.0 and abs(logistics.industry(st2, "blue") - 0.5) < 1e-9 and logistics.industry(st2, "red") == 1.0,
          "разрушенный завод: восстановление и пополнение синих x0.5 (industry_effect 0.5 - ОЦЕНКА)")
    nf[0]["damage"] = 0.0
    planner.plan(st2)
    kinds = [t["kind"] for t in st2["tasks"]]
    fk = [t for t in st2["tasks"] if t["kind"] == "strike_factory"]
    check(bool(fk) or len(kinds) >= planner.MAX_TASKS, f"в плане дня есть удар по заводу (или план заполнен): {kinds}")
    if fk:
        man = build.build(st2, tmp / "factory.miz", task_no=st2["tasks"].index(fk[0]) + 1)
        objs = [o if isinstance(o, str) else o.get("id") for o in man.get("objects", [])]
        check(nf[0]["id"] in objs and Path(man["file"]).exists(), f"миссия удара по заводу собрана, завод в целях миссии: {objs}")
    # малый мост: разрушен - связь открыта, объезд; найденный склад не снабжает
    from redfront import ops, sim as sim_
    a_, b_ = link
    g0 = ops.graph(st2)[a_][b_]
    nb[0]["damage"] = 1.0
    g1 = ops.graph(st2).get(a_, {}).get(b_)
    check(nb[0]["minor"] and logistics.link_open(st2, a_, b_) and g1 is not None and abs(g1 - g0 - 15) < 1e-6,
          f"разрушенный малый мост связь {a_}-{b_} не закрывает: объезд +15 км ({g0:.1f} -> {g1:.1f})")
    mover = {"id": "t", "route": [a_, b_], "progress_km": 1.0}
    check(sim_.current_link(st2, mover) == (a_, b_), "часть на связи с разрушенным малым мостом определяется (марш x0.5)")
    nb[0]["damage"] = 0.0
    d_new = next(u for u in st2["units"].values() if u.get("role") == "depot" and u.get("found"))
    check(not logistics.supplies(d_new) and logistics.supplies(st2["units"]["red_depot_1"]),
          "найденный склад - цель без снабжения, склады сценария снабжают")
    wood = {"id": "br_x_y", "name": "Малый мост на пути X - Y", "role": "bridge", "side": None, "found": True, "minor": True,
            "map_type": "WOODEN_BRIDGE_2LINE", "links": [], "pos": {"lat": 53.0, "lon": 10.5}, "state": "active", "damage": 0.0,
            "lost": {}, "composition": []}
    st2["units"]["br_x_y"] = wood
    pr_w = json.loads(json.dumps(rawall)); pr_w["bridges_all"].append(["600", "wooden_bridge_2line", *xy(*m1), 1])
    f3 = tmp / "map_wood.json"; f3.write_text(json.dumps(pr_w), encoding="utf-8")
    pw = mapobj.load(f3)
    check("br_x_y" in st2["units"] and not any(o["name"] == "600" for o in pw["bridges_all"]),
          "деревянные мосты (wooden_*) из зонда не берутся")
    mapobj.apply(st2, pw)
    check("br_x_y" not in st2["units"], "уже назначенный деревянный мост при повторном применении убран")
    pos0 = {k: dict(st2["units"][k]["pos"]) for k in ("br_lauenburg",)}
    n0 = len(st2["units"])
    mapobj.apply(st2, pr2)
    check(all(st2["units"][k]["pos"] == v for k, v in pos0.items()), "повторное применение зонда не сдвигает уже уточнённые цели")
    check(len(st2["units"]) == n0, "повторное применение зонда не плодит цели")
    secp = model.load_json("sector_hamburg.json")
    mapobj.apply(secp, pr2)
    sp = tmp / "sector_found.json"
    sp.write_text(json.dumps(secp, ensure_ascii=False), encoding="utf-8")
    st3 = model.new_campaign("map3", seed=5, sector=sp)
    check(nb[0]["id"] in st3["units"] and st3["units"][nb[0]["id"]]["links"] == [list(link)],
          "найденные цели, записанные в сектор, есть в новой кампании")
    planner.plan(st2)
    check(st2["tasks"] is not None, "план дня с найденными целями строится")


def gui_section(tmp: Path) -> None:
    """Окно кампании: весь цикл дня через App.do (то же, что кнопки страницы), без браузера."""
    from redfront import gui
    print("\n== окно кампании ==")
    home, root = tmp / "gui_home", tmp / "gui_camps"
    (home / "Saved Games" / "DCS" / "Missions").mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=True)
    app = gui.App(root, home)
    r = app.do("new", {"file": "g1", "side": "red", "seed": "42"})
    check(r["file"] == "g1.json" and r["state"]["day"] == 1 and r["state"]["places"], "новая кампания из окна")
    check(app.info()["campaigns"][0]["file"] == "g1.json", "кампания в списке окна")
    try:
        app.do("new", {"file": "g1"}); dup = False
    except ValueError:
        dup = True
    check(dup, "существующий файл без 'перезаписать' не затирается")
    r = app.do("plan", {"file": "g1.json"})
    check(r["state"]["tasks"] and r["state"]["tasks"][0]["target"], "план дня: задачи с целью для карты")
    r = app.do("build", {"file": "g1.json", "task": 1, "fly": "strike"})
    check((home / "Saved Games" / "DCS" / "Missions" / "redfront_g1_day1.miz").exists(), "миссия собрана в Saved Games\\DCS\\Missions")
    r = app.do("endday", {"file": "g1.json"})
    check(r["state"]["day"] == 2, "конец дня из окна")
    check(app.path("../x").parent == root, "имя файла кампании не выходит из папки проекта")


def germany_section(tmp: Path) -> None:
    """Театр всей карты: граф фронта, оси наступления, нагрузка миссии."""
    import collections
    from redfront import ops
    print("\n== театр всей карты ==")
    st = model.new_campaign("ger", sector="sector_germany.json", oob="oob_germany.json", seed=3)
    fl = ops.front_links(st)
    check(len(st["places"]) > 100 and len(fl) >= 25 and st["sector"] == "sector_germany.json",
          f"театр: {len(st['places'])} пунктов, линия фронта {len(fl)} связей от Любека до Хофа")
    srcs = [u for u in st["units"].values() if u.get("role") == "maneuver"]
    check(all(u.get("source") for u in srcs) and all(u.get("axis") for u in srcs if u["side"] == "red"),
          f"части: {len(srcs)}, у всех источник; у частей красных - ось наступления")
    own0 = {p: v["side"] for p, v in st["places"].items()}
    for _ in range(8):
        sim.end_day(st)
    took = [p for p, v in st["places"].items() if v["side"] == "red" and own0[p] == "blue"]
    axes = {a for a, objs in st["objectives"]["red"].items()
            if any(min(ops.path_km(st, p, o) for o in objs) < 60 for p in took)}
    check(len(took) >= 3 and len(axes) >= 2, f"за 8 дней красные взяли {len(took)} пунктов на {len(axes)} осях: {', '.join(sorted(took))}")
    planner.plan(st)
    tk = st["tasks"][0]
    st["settings"]["mission_budget"] = 0                               # без бюджета - весь театр
    full = materialize.theatre(st, tk)
    n_full = sum(len(g["vehicles"]) for g in full)
    st["settings"].pop("mission_budget")                               # по умолчанию - MISSION_BUDGET
    man = build.build(st, tmp / "germany.miz", task_no=1)
    veh = sum(len(g["vehicles"]) for g in man["ground"])
    heavy = max(v["weight"] for g in man["ground"] for v in g["vehicles"])
    check(veh <= materialize.MISSION_BUDGET < n_full and heavy <= materialize.MAX_WEIGHT * 1.1,
          f"миссия всего фронта: без бюджета {n_full} машин, с бюджетом {veh} (не больше {materialize.MISSION_BUDGET}), "
          f"{len(man['ground'])} групп, машина не дороже ~{materialize.MAX_WEIGHT} машин модели (макс. {heavy:.2f})")
    core = {g["unit"]: len(g["vehicles"]) for g in materialize.window(st, tk)}
    got = {g["unit"]: len(g["vehicles"]) for g in man["ground"]}
    check(all(got.get(u) == n for u, n in core.items() if n),
          f"бюджет не трогает окно задачи игрока ({len(core)} групп: цель, угрозы коридора, ЗРК у маршрута)")
    by_unit_full = {g["unit"]: sum(v["weight"] for v in g["vehicles"]) for g in full}
    thinned = [g for g in man["ground"] if len(g["vehicles"]) < len(next(f for f in full if f["unit"] == g["unit"])["vehicles"])]
    ok_w = all(sum(v["weight"] for v in g["vehicles"]) <= by_unit_full[g["unit"]] + 1e-6 for g in thinned)
    check(thinned and ok_w, f"дальние группы прорежены ({len(thinned)}): вес машин вырос, сумма не больше модели; "
                            f"убрано целиком {len(full) - len(man['ground'])} групп")


def helo_section(tmp: Path) -> None:
    """Боевые вертолёты: части модели, задача по войскам в соприкосновении, предельно малая высота и у ИИ."""
    import collections
    print("\n== вертолёты ==")
    st = model.new_campaign("helo", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    for _ in range(3):
        sim.end_day(st)
    kinds = {side: collections.Counter(t["kind"] for t in planner.plan_side(st, side)[0]) for side in model.SIDES}
    check(all(n <= planner.MAX_PER_KIND for c in kinds.values() for n in c.values()) and len(kinds["blue"]) >= 2,
          f"в плане дня не больше {planner.MAX_PER_KIND} задач одного вида: {dict(kinds['blue'])}")
    planner.plan(st)
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "cas_helo"), None)
    check(n is not None, "в плане дня есть удар вертолётов по войскам в соприкосновении")
    if n:
        build.build(st, tmp / "helo.miz", task_no=n)
        m = dcs.Mission(); m.load_file(str(tmp / "helo.miz"))
        hg = [g for c in m.coalition.values() for cn in c.countries.values() for g in cn.helicopter_group]
        check(hg and max(p.alt for g in hg for p in g.points) <= 60,
              f"вертолёты в миссии: {', '.join(g.units[0].type for g in hg)}, маршрут не выше 60 м")


def presets_section(tmp: Path) -> None:
    """Пресеты состава сил по годам (сводка игрока): авиация на дату пресета, КРУ только при МиГ-29, дата кампании;
    окно - список пресетов, копия для правки в presets/, кампания из своего пресета."""
    from redfront import gui
    print("\n== пресеты состава сил ==")
    camp = {}
    for f in ("oob_germany_1985.json", "oob_germany_1987.json", "oob_germany.json"):
        st = model.new_campaign("p", sector="sector_germany.json", oob=f, seed=1)
        camp[f] = st
    by = {f: {u["id"]: u for u in st["units"].values() if u.get("type")} for f, st in camp.items()}
    y85, y87, y89 = by["oob_germany_1985.json"], by["oob_germany_1987.json"], by["oob_germany.json"]
    check(camp["oob_germany_1985.json"]["date"] == "1985-06-01" and camp["oob_germany.json"]["date"] == "1989-09-01",
          "дата кампании - дата среза пресета (1985-06-01, 1989-09-01)")
    check(y85["r85iap"]["type"] == "MiG_23MLD" and y87["r85iap"]["type"] == "MiG_29_Fulcrum"
          and y85["r116bap"]["type"] == "Su_24M" and "r116bap" not in y89 and y89["r911apib"]["type"] == "MiG_27K"
          and "r368oshap" not in y87 and "r368oshap" in y89 and y87["r357oshap"]["count"] == 8,
          "авиация по годам: 85-й гв. иап МиГ-23 -> МиГ-29 (1986), Бранд: Су-24М -> 911 апиб МиГ-27К (7.1989), "
          "368 оштап с 12.1988, 357 оштап в 1987 почти весь в Афганистане")
    gci = {f: sorted(u["id"] for u in st["units"].values() if u["role"] == "gci") for f, st in camp.items()}
    check(not gci["oob_germany_1985.json"] and len(gci["oob_germany.json"]) == 7,
          f"КРУ только где МиГ-29: 1985 - нет, 1987 - {len(gci['oob_germany_1987.json'])}, 1989 - {len(gci['oob_germany.json'])}")
    root = tmp / "presets_gui"
    root.mkdir(exist_ok=True)
    app = gui.App(root, tmp / "home_presets")
    keys = [x["file"] for x in app.presets("germany")]
    app.do("presetcopy", {"theatre": "germany", "preset": "oob_germany_1985.json", "name": "мой 85"})
    mine = json.loads((root / "presets" / "мой 85.json").read_text(encoding="utf-8"))
    mine["units"] = [dict(u, count=5) if u["id"] == "r19apib" else u for u in mine["units"]]
    (root / "presets" / "мой 85.json").write_text(json.dumps(mine, ensure_ascii=False), encoding="utf-8")
    keys2 = [x["file"] for x in app.presets("germany")]
    r = app.do("new", {"file": "mine85", "theatre": "germany", "preset": "presets/мой 85.json", "side": "red"})
    st = model.load(root / "mine85.json")
    bad = None
    try:
        app.do("new", {"file": "x", "theatre": "germany", "preset": "../../etc/passwd"})
    except ValueError as e:
        bad = str(e)
    check(keys[0] == "oob_germany.json" and "oob_germany_1985.json" in keys and "presets/мой 85.json" in keys2
          and st["units"]["r19apib"]["count"] == 5 and st["date"] == "1985-06-01" and bad,
          f"окно: пресеты {keys}; копия для правки -> presets/, правка (19 апиб: 5 самолётов) попадает в кампанию; "
          "чужой путь вместо пресета - отказ")


def ato_section(tmp: Path) -> None:
    """План полётов на сутки (ato.py): время вылетов, занятость самолётов, смены дежурства, часы кампании,
    группы, которые к началу миссии уже в воздухе."""
    from redfront import ato, logistics
    print("\n== план полётов на сутки ==")
    st = model.new_campaign("ato", sector="sector_germany.json", oob="oob_germany.json", seed=11)
    planner.plan(st)
    a = st["ato"]
    w0, w1 = ato.flying_window(st)
    turn = {s_: model.doctrine(st, s_)["sim"].get("turnaround_min", ato.TURNAROUND_MIN) * 60 for s_ in model.SIDES}
    busy = {}
    for e in a["entries"]:
        for g in e["task"]["package"]:
            t = e["times"][g["group"]]
            busy.setdefault(g["performer"], []).append((t["takeoff_s"], t["land_s"] + turn[e["side"]], g["size"]))
    over = [u for u, ivs in busy.items() for t0, _t1, _n in ivs
            if sum(n for a_, b_, n in ivs if a_ <= t0 < b_) > logistics.available(st, st["units"][u])]
    sides = {s_: sum(1 for e in a["entries"] if e["side"] == s_ and not e["ai_only"]) for s_ in model.SIDES}
    check(all(sides.values()) and not over and all(w0 <= e["tot_s"] <= w1 for e in a["entries"]),
          f"ATO на сутки: вылетов красных {sides['red']}, синих {sides['blue']}, все в лётном дне "
          f"{ato.hhmm(w0)}-{ato.hhmm(w1)}, самолётов частей не больше наличия в любой момент")
    shifts = sorted(e["tot_s"] for e in a["entries"] if e["kind"] == "awacs_orbit" and e["side"] == "blue")
    check(shifts and shifts[0] == w0 and all(b_ - a_ == 4 * 3600 for a_, b_ in zip(shifts, shifts[1:])),
          f"дежурство ДРЛО синих - сменами по 4 ч весь лётный день: {', '.join(ato.hhmm(x) for x in shifts)}")
    from redfront import gui
    v = gui.view(st)
    enemy_rows = [r for r in v["ato"] if r["side"] == "blue"]
    check(len(v["ato"]) == len(a["entries"]) and enemy_rows and all(r["takeoff"] and r["groups"] for r in v["ato"]),
          f"окно: вкладка ATO - вылеты обеих сторон ({len(v['ato'])}, противника {len(enemy_rows)} - показ по галочке отладки)")
    tk = st["tasks"]
    check(tk and [t["takeoff_s"] for t in tk] == sorted(t["takeoff_s"] for t in tk) and not any(t.get("ai_only") for t in tk),
          f"игроку - вылеты своей стороны по времени ({len(tk)}: {ato.hhmm(tk[0]['takeoff_s'])} ... {ato.hhmm(tk[-1]['takeoff_s'])})")
    air = None
    for n in range(1, len(tk) + 1):
        man = build.build(st, tmp / "ato.miz", task_no=n)
        m = dcs.Mission(); m.load_file(str(tmp / "ato.miz"))
        late = [g for c in m.coalition.values() for cn in c.countries.values() for g in cn.plane_group
                if "_orbit" not in g.name and g.points[0].type == "Turning Point"]
        if late:
            air = (n, man, m, late)
            break
    check(air is not None and all(g.points[0].alt >= build.AIR_START_MIN_M for g in air[3]),
          "к началу миссии вылеты ATO, уже идущие к объекту, - в воздухе на своём маршруте"
          + (f" (задача {air[0]}: {', '.join(g.name for g in air[3])})" if air else ""))
    n, man, m, _late = air or (len(tk), man, m, [])
    used = {side_: sorted(cn.name for cn in m.coalition[side_].countries.values()
                          if cn.vehicle_group or cn.plane_group or cn.helicopter_group) for side_ in ("red", "blue")}
    check(used == {"red": ["Combined Joint Task Forces Red"], "blue": ["Combined Joint Task Forces Blue"]},
          f"коалиции миссии - Combined Joint Task Forces Red / Blue: {used}")
    sg = [g for c in m.coalition.values() for cn in c.countries.values() for g in cn.plane_group if " strike " in g.name][0]
    perf = st["units"][st["tasks"][n - 1]["performer"]]
    check(abs(sg.points[1].speed * 3.6 - model.cruise_kmh(perf["type"])) < 1,
          f"скорость ударной группы на маршруте - крейсерская типа {perf['type']}: {sg.points[1].speed * 3.6:.0f} км/ч "
          f"(data/aircraft.json)")
    t_ = st["tasks"][n - 1]
    check(m.start_time.hour * 3600 + m.start_time.minute * 60 + m.start_time.second == man["start_s"]
          and man["start_s"] <= t_["takeoff_s"] < man["start_s"] + 15 * 60,
          f"миссия начинается по плану полётов: {ato.hhmm(man['start_s'])} (взлёт по ATO {ato.hhmm(t_['takeoff_s'])})")
    debrief.apply(st, fake_hook(st["campaign_id"], man["sortie"], [], {}, all_flight_units(man)))
    planner.plan(st)
    check(st["clock_s"] == man["end_s"] and all(t["takeoff_s"] >= st["clock_s"] for t in st["tasks"])
          and all(t["ato_id"] != man["ato_id"] for t in st["tasks"]),
          f"после дебрифа часы кампании {ato.hhmm(st['clock_s'])}: в плане только вылеты позже, слетанный - не предлагается")
    sim.end_day(st)
    planner.plan(st)
    check(st["ato"]["day"] == st["day"] == 2 and not st["clock_s"], "новые сутки - новый план полётов, часы с начала дня")


def support_air_section(tmp: Path) -> None:
    """ДРЛО и заправщики: части модели, задача дежурства (только ИИ), в миссии - в зоне с начала, потери - в модель."""
    print("\n== ДРЛО и заправщики ==")
    st = model.new_campaign("sup", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    planner.plan(st)
    check(not any(t.get("ai_only") for t in st["tasks"]), "дежурство ДРЛО/заправщика в план игрока не попадает")
    man = build.build(st, tmp / "support.miz", task_no=1)
    m = dcs.Mission(); m.load_file(str(tmp / "support.miz"))
    orb = {g.units[0].type: g for c in m.coalition.values() for cn in c.countries.values() for g in cn.plane_group
           if "_orbit" in g.name}
    check({"E-3A", "A-50", "KC-135"} <= set(orb) and all(g.points[0].alt >= 7000 and g.points[0].type == "Turning Point"
                                                          for g in orb.values()),
          f"в миссии на дежурстве в воздухе: {', '.join(sorted(orb))}")
    fl = next(f for f in man["flights"] if f["performer"] == "b_naew")
    n0 = st["units"]["b_naew"]["count"]
    data = fake_hook(st["campaign_id"], st["sortie"], fl["units"], {}, [])
    debrief.apply(st, data)
    check(st["units"]["b_naew"]["count"] == n0 - len(fl["units"]),
          f"сбитый E-3A списан из модели: {n0} -> {st['units']['b_naew']['count']}")


def air_defence_section(tmp: Path) -> None:
    """Объектовая ПВО: позиции сектора + шаблоны стороны; радиогоризонт в коридоре; восстановление и смена позиции."""
    from redfront import logistics
    print("\n== объектовая ПВО ==")
    st = model.new_campaign("ad", sector="sector_germany.json", oob="oob_germany.json", seed=3)
    sec = model.load_json("sector_germany.json")
    ad = [u for u in st["units"].values() if u.get("fixed")]
    tiers = {r: sum(1 for u in ad if u["role"] == r) for r in ("sam_long", "sam_medium", "sam_short")}
    check(len(ad) == len(sec["ad_sites"]) and all(tiers.values()),
          f"позиции ПВО сектора заняты шаблонами сторон: {len(ad)} частей ({tiers})")
    afs = {u["covers"] for u in ad if u.get("covers")}
    check(afs == {f"af_{b}" for b in st["airbases"]}, f"ПВО объекта у каждого военного аэродрома ({len(afs)})")
    s200 = next(u for u in ad if u["role"] == "sam_long")
    p = model.unit_pos(st, s200)
    a, b = model.offset(p, 90, 80_000, -100_000), model.offset(p, 90, 80_000, 100_000)   # маршрут в 80 км от С-200
    hi = planner.corridor_threats(st, [(a, b)], "red")
    lo = planner.corridor_threats(st, [(a, b)], "red", 50)
    check(s200["id"] in hi and s200["id"] not in lo,
          f"С-200 в 80 км: угроза по высотной цели, по маршруту на 50 м - нет (радиогоризонт "
          f"{planner.radar_horizon_km(planner.RADAR_MAST_M, 50):.0f} км)")
    gci = [u for u in st["units"].values() if u["role"] == "gci"]
    mig_bases = {u["base"] for u in st["units"].values() if u["side"] == "red" and str(u.get("type", "")).startswith("MiG_29")}
    check(gci and {u["covers"] for u in gci} == {f"af_{b}" for b in mig_bases}
          and len({u["channel"] for u in gci}) == len(gci) and all(u["radius_km"] == 250 for u in gci),
          f"КРУ у аэродромов МиГ-29 ({', '.join(sorted(mig_bases))}): у каждого свой канал, радиус 250 км")
    planner.plan(st)
    man = build.build(st, tmp / "gci.miz", task_no=1)
    m = dcs.Mission(); m.load_file(str(tmp / "gci.miz"))
    gg = {g.name: g for c in m.coalition.values() for cn in c.countries.values() for g in cn.vehicle_group if g.name.startswith("red_gci")}
    acts = {n: [t.params["action"]["params"] for t in g.points[0].tasks if t.params.get("action", {}).get("id") == "ActivateGCI"]
            for n, g in gg.items()}
    check(set(gg) == {u["id"] for u in gci} and all(len(a) == 1 and a[0]["unitId"] == gg[n].units[0].id
                                                    and a[0]["channel"] == st["units"][n]["channel"] and a[0]["radius"] == 250000
                                                    for n, a in acts.items())
          and all(u["name"] in m.description_text() for u in gci),
          f"в миссии КРУ включены с начала (ActivateGCI: канал, радиус 250 км), каналы - в брифинге")
    hawk = st["units"]["blue_sam31"]
    for u in (hawk, s200):
        u["lost"] = {c["type"]: float(c["count"]) for c in u["composition"]}    # уничтожены целиком
    pos0 = {u["id"]: dict(u["pos"]) for u in (hawk, s200)}
    lines = logistics.air_defence(st)
    moved = model.dist_km(pos0[hawk["id"]], hawk["pos"])
    check(0 < model.strength(hawk) < 1 and 0 < model.strength(s200) < 1,
          f"разбитые ЗРК восстанавливаются: HAWK {model.strength(hawk):.0%}, С-200 {model.strength(s200):.0%} за сутки")
    check(abs(moved - model.doctrine(st, "blue")["sim"]["sam_relocate_km"]) < 0.5 and s200["pos"] == pos0[s200["id"]],
          f"раскрытый HAWK сменил позицию на {moved:.1f} км, объектовая ПВО (С-200) - на месте")
    logistics.air_defence(st)
    check(model.dist_km(pos0[hawk["id"]], hawk["pos"]) == moved, "без новых потерь ЗРК позицию не меняет")
    # план дня: удары по позициям ЗРК, полки по очереди, средние высоты без угроз в коридоре
    st = model.new_campaign("ad2", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    planner.plan(st)
    tasks = [t for t in planner.plan_side(st, "red")[0] if not t.get("ai_only")]
    perfs = [t["performer"] for t in tasks]
    check(len(set(perfs)) >= len(perfs) - 2, f"план дня: задачи распределены по полкам ({len(set(perfs))} частей на {len(perfs)} задач)")
    medium = [t for t in tasks if not t["threats"] and t["kind"].startswith("strike_")]
    check(medium and all(g.get("transit_alt_m_agl") == 4000 for t in medium for g in t["package"])
          and all(not g.get("transit_alt_m_agl") for t in tasks if t["threats"] for g in t["package"]),
          f"без угроз в коридоре - переход на 4000 м ({len(medium)} задач), с угрозами - на малой высоте")
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "strike_sam_site"), None)
    check(n is not None, "в плане дня есть удар по позиции ЗРК")
    if n:
        man = build.build(st, tmp / "sam_site.miz", task_no=n)
        m = dcs.Mission(); m.load_file(str(tmp / "sam_site.miz"))
        tgt = st["tasks"][n - 1]["target"]
        vg = next(g for c in m.coalition.values() for cn in c.countries.values() for g in cn.vehicle_group if g.name == tgt)
        sg = strike_group(m)
        attacks = [t for p_ in sg.points for t in p_.tasks if getattr(t, "id", None) == "AttackGroup"]
        check(any(t.params.get("groupId") == vg.id for t in attacks),
              f"удар по позиции ЗРК: позиция в миссии, у ударной группы атака по ней ({tgt})")


def core_section(tmp: Path) -> None:
    """Сквозной цикл двух дней на составе сил слоёв 0.1-0.3 (BASELINE) и проверки слоёв."""
    st = model.new_campaign("smoke", oob=BASE_OOB, sector=BASE_SECTOR)
    bn = st["units"]["blue_pzgren_bn_1"]

    # ---- день 1 ----
    tk = planner.plan(st)
    check(tk is not None and tk["target"] == bn["id"], "день 1: задача - удар по колонне батальона")
    check(tk["threats"] == ["blue_flak_1"],
          "угроза в коридоре - приданная батальону войсковая ПВО; Patriot в глубине (60 км) маршрут не достаёт")
    man = build.build(st, tmp / "d1.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "d1.miz"))
    vg = {g.name: g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group}
    col = man["ground"][0]
    check(len(vg[bn["id"]].units) == len(col["vehicles"]), f"колонна в .miz: {len(col['vehicles'])} машин")
    check(len(col["vehicles"]) == BASELINE["col_d1"], f"как в 0.1: {BASELINE['col_d1']} машин в колонне")
    check(abs(sum(v["weight"] for v in col["vehicles"]) - model.total(bn)) < 1e-6, "сумма весов колонны = исправной технике модели")
    fg = strike_group(m)
    check(pylons_match(fg.units[0]), "подвеска Su_25/anti_armor из loadouts.json: ровно её пилоны")

    # Позиция ЗРК развёрнута на ось угрозы. В 0.2 РЛС Patriot смотрела на север при угрозе с востока - в DCS не было ни засветки.
    sam = st["units"]["blue_patriot_1"]
    axis = model.bearing_deg(sam["pos"], st["airbases"]["parchim"])
    pat = materialize.sam_site(st, sam)["vehicles"]
    check(all(abs(v["heading"] - axis) < 0.01 for v in pat), f"Patriot: все {len(pat)} машин развёрнуты на Пархим ({axis:.0f}°)")
    pat_vg = vg.get("blue_patriot_1")
    check(pat_vg is not None and len(pat_vg.units) == 6 and all(abs(u.heading - axis) < 0.01 for u in pat_vg.units),
          "Patriot вне коридора, но в пузыре: в миссии, развёрнут на Пархим; группа подавления на него не назначена")
    bub = json.loads(json.dumps(st)); bub["settings"]["bubble_km"] = 50
    check(materialize.background_sams(st, tk) == ["blue_patriot_1"] and materialize.background_sams(bub, bub["task"]) == [],
          "пузырь 150 км ловит Patriot, пузырь 50 км - нет (settings.bubble_km)")
    old = json.loads(json.dumps(st)); del old["settings"]["bubble_km"]
    check(materialize.background_sams(old, old["task"]) == ["blue_patriot_1"], "кампания без bubble_km - значение по умолчанию")

    # огонь по ЛА: только ПВО; остальные наземные группы - только по наземным целям
    def restrict(g):
        return [t.params["action"]["params"] for t in g.points[0].tasks if type(t).__name__ == "OptRestrictTargets"]
    check(restrict(vg[bn["id"]]) == [{"name": 28, "value": 2}] and restrict(vg["blue_flak_1"]) == [] and restrict(vg["blue_patriot_1"]) == [],
          "батальон: OptRestrictTargets = только наземные цели; войсковая ПВО - без ограничения")

    # войсковая ПВО идёт в колонне сразу за танками, в оставленном разрыве, без наложения машин
    win = materialize.window(st, tk)             # то же окно, что собрано в .miz (в манифесте km машин нет)
    colw, flak = win[0], win[1]
    roles = {c["type"]: c["role"] for c in bn["composition"]}
    n_mbt = sum(1 for v in colw["vehicles"] if roles[v["type"]] == "MBT")
    kms = sorted([v["km"] for v in colw["vehicles"]] + [v["km"] for v in flak["vehicles"]], reverse=True)
    steps = [round((a - b) * 1000, 3) for a, b in zip(kms, kms[1:])]
    check(flak["unit"] == "blue_flak_1" and len(flak["vehicles"]) == 4 and len(vg["blue_flak_1"].units) == 4
          and all(abs(x - 50) < 0.01 for x in steps)
          and all(colw["vehicles"][n_mbt - 1]["km"] > v["km"] > colw["vehicles"][n_mbt]["km"] for v in flak["vehicles"]),
          f"войсковая ПВО: 4 машины между {n_mbt} танками и БМП, вся колонна через 50 м")
    sam_o = json.loads(json.dumps(sam)); sam_o["heading_deg"] = 120
    check(all(v["heading"] == 120 for v in materialize.sam_site(st, sam_o)["vehicles"]), "heading_deg из состава сил имеет приоритет")

    # С установленным DCS pydcs сначала вешает загрузку по умолчанию для maintask. Имитируем её (все пилоны заняты)
    # и проверяем, что своя подвеска её полностью заменяет, а не смешивается с ней.
    import copy as _copy
    st_dflt = _copy.deepcopy(st)
    st_dflt["sortie"] = 0
    st_dflt["manifest"] = None
    with fake_default_loadout(dcs.planes.Su_25) as n_default:
        build.build(st_dflt, tmp / "dflt.miz")
    md = dcs.Mission(Germany())
    md.load_file(str(tmp / "dflt.miz"))
    fgd = strike_group(md)
    check(n_default > 6 and pylons_match(fgd.units[0]),
          f"при загрузке DCS по умолчанию ({n_default} пилонов) остаются только 6 пилонов из loadouts.json")

    # плотность 0.5: машин меньше, сумма весов та же
    half = materialize.column(st, bn, density=0.5)
    check(len(half["vehicles"]) == BASELINE["col_half"] and abs(sum(v["weight"] for v in half["vehicles"]) - model.total(bn)) < 1e-6,
          f"плотность 0.5: {len(half['vehicles'])} машин (как в 0.1), сумма весов сохраняется")

    # ---- хук: 8 машин уничтожено, уцелевшие продвинулись ~3 км ----
    # позиции пишутся и для войсковой ПВО (у неё нет своего маршрута - дебриф не должен на ней падать)
    names = [v["name"] for v in col["vehicles"]] + [v["name"] for v in man["ground"][1]["vehicles"]]
    kill = names[:8]
    pts = model.route_points(st, bn)
    terrain = m.terrain
    positions = {}
    for i, n in enumerate(names):
        p, _ = model.point_at_km(pts, bn["progress_km"] + 3.0 - i * 0.05)
        q = Point.from_latlng(LatLng(p["lat"], p["lon"]), terrain)
        positions[n] = (q.x, q.y)
    script = build.lua_hook(st["campaign_id"], man["sortie"], names)
    if have_lupa():
        data = run_hook(script, tmp, kill, positions, all_flight_units(man))
        check(data["campaign"] == st["campaign_id"] and data["sortie"] == man["sortie"], "хук: JSON с верными campaign/sortie")
        check(sorted(data["dead"]) == sorted(kill), "хук: потери записаны, объекты карты (SCENERY) отброшены")
        check(sorted(data["landed"]) == sorted(all_flight_units(man)) and data["mission_ended"], "хук: посадка звена и конец миссии")
        check(len(data["positions"]) == len(names) - len(kill), "хук: позиции только уцелевших машин колонны")
    else:
        print("SKIP lupa не установлена: Lua-хук не исполняется, подставлен JSON того же вида (4 проверки хука пропущены)")
        data = fake_hook(st["campaign_id"], man["sortie"], kill, positions, all_flight_units(man))

    s0, km0 = model.strength(bn), bn["progress_km"]
    data["time"] = 3000                          # миссия 50 мин: по ней дебриф считает среднюю скорость марша
    lines = debrief.apply(st, data)
    print("     " + "\n     ".join(lines))
    check(abs((s0 - model.strength(bn)) * model.total(bn) - 8.0) < 1e-6, "дебриф: батальон потерял ровно 8 машин (веса 1.0)")
    check(2.5 < bn["progress_km"] - km0 < 3.5, f"дебриф: продвижение за вылет {bn['progress_km'] - km0:.2f} км")
    want_kmh = round((bn["progress_km"] - km0) / (3000 / 3600), 1)
    check(bn.get("observed_kmh") == want_kmh, f"дебриф: замерена средняя скорость марша в DCS {bn.get('observed_kmh')} км/ч (приказ {bn['march_kmh']})")
    fl = st["units"]["blue_flak_1"]
    moved = model.dist_km(model.unit_pos(st, fl), model.unit_pos_at(st, fl, 3600, default_kmh=0))
    check(abs(moved - want_kmh) < 0.3, f"прогноз положения ПВО колонны - по замеренной скорости: за час {moved:.1f} км")

    # ---- конец дня, день 2 ----
    km1 = bn["progress_km"]
    sim.end_day(st)
    adv = bn["progress_km"] - km1
    check(st["day"] == 2 and abs(adv - BASELINE["advance_d2_km"]) < 0.01, f"день 2: колонна прошла {adv:.2f} км за сутки (как в 0.1)")
    tk2 = planner.plan(st)
    check(tk2 is not None and tk2["target_pos"] != tk["target_pos"], "день 2: задача по колонне в новом месте")
    man2 = build.build(st, tmp / "d2.miz")
    col2 = man2["ground"][0]
    check(len(col2["vehicles"]) == BASELINE["col_d2"], f"день 2: в миссии {len(col2['vehicles'])} машин (было {len(col['vehicles'])}, как в 0.1)")
    check(man2["sortie"] == 2, "день 2: номер вылета 2")

    # ---- плотность и дробные веса: колонна больше бюджета ----
    big = json.loads(json.dumps(bn))
    for c in big["composition"]:
        c["count"] *= 3
    big["lost"] = {}
    colb = materialize.column(st, big)
    w = sum(v["weight"] for v in colb["vehicles"])
    check(len(colb["vehicles"]) == BASELINE["big_deployed"] and abs(w - model.total(big)) < 1e-6,
          f"колонна 90 машин -> {len(colb['vehicles'])} развёрнуто (как в 0.1), сумма весов {w:.1f}")

    # ---- слои: техника - выбор игрока, поведение - от стороны ----
    oob = base_oob()
    swapped = json.loads(json.dumps(oob))
    swapped["units"][0]["type"] = "A_10A"           # другой тип, та же роль attack
    swapped["countries"]["red"] = "USA"             # страна стороны - тоже выбор игрока
    p = tmp / "oob_swapped.json"
    p.write_text(json.dumps(swapped, ensure_ascii=False), encoding="utf-8")
    st3 = model.new_campaign("swap", oob=p, sector=BASE_SECTOR)
    tk3 = planner.plan(st3)
    check(tk3 is not None and tk3["performer"] == "red_shap_1", "другой тип с ролью attack: задача та же")
    man3 = build.build(st3, tmp / "swap.miz")
    m3 = dcs.Mission(Germany())
    m3.load_file(str(tmp / "swap.miz"))
    fg3 = strike_group(m3)
    check(fg3.units[0].type == "A-10A" and man3["sortie"] == 1,
          "A_10A собран в .miz; подвески в loadouts.json нет - остаётся загрузка DCS по умолчанию")

    st4 = model.new_campaign("blue", oob=BASE_OOB, sector=BASE_SECTOR, player_side="blue")
    check(planner.plan(st4) is None and st4["task_reason"], f"игрок за синих без своей авиации: задачи нет - {st4['task_reason']}")

    nolim = json.loads(json.dumps(oob))
    del next(u for u in nolim["units"] if u["id"] == "blue_patriot_1")["threat_radius_km"]   # ЗРК без явного радиуса
    p5 = tmp / "oob_nolim.json"
    p5.write_text(json.dumps(nolim, ensure_ascii=False), encoding="utf-8")
    st5 = model.new_campaign("nolim", oob=p5, sector=BASE_SECTOR)
    check(abs(planner.threat_radius_km(st5["units"]["blue_patriot_1"]) - 100.0) < 1e-6,
          "ЗРК без threat_radius_km: радиус из pydcs (Patriot_ln threat_range = 100 км)")


# Разделы теста по порядку: python tools/smoke_test.py - все; pytest (tests/test_smoke.py) - каждый отдельным тестом.
SECTIONS = [core_section, patriot_close_section, front_section, random_section, logistics_section, menu_section,
            theatre_section, air_section, package_section, roads_section, column_road_section, mapobj_section,
            gui_section, germany_section, air_defence_section, support_air_section, helo_section, ato_section, presets_section]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="redfront_"))
    for section in SECTIONS:
        section(tmp)

    print(f"\nФайлы теста: {tmp}")
    print("ИТОГ: " + ("всё прошло" if not FAILS else f"{len(FAILS)} провал(ов)"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

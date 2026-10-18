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


def pylons_match(unit, name: str = "CAS") -> bool:
    """Пилоны юнита = ровно подвеска name его типа (свои payloads_custom.json - первыми, затем DCS Retribution)."""
    own = model.load_json("payloads_custom.json")["types"].get(unit.unit_type.id, {}).get(name)
    want = (own or model.load_json("payloads.json")["types"][unit.unit_type.id][name])["pylons"]
    expect = {int(p): d["CLSID"] for p, d in want.items()}
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
    check(list(pk) == ["strike", "sead", "recon", "kill"] and [g["size"] for g in pk.values()] == [4, 2, 2, 2],
          "пакет: ударная - звено 4 + пара ПРР и пара добивания (ЗРК в коридоре) + доразведка 2 (цель на марше)")
    check(pk["sead"]["objective"]["units"] == pk["kill"]["objective"]["units"] == ["blue_flak_1"],
          "пара ПРР и пара добивания нацелены на войсковую ПВО колонны")
    check(pk["strike"]["performer"] == "red_shap_1" and pk["sead"]["performer"] == "red_bap_1" and pk["kill"]["performer"] == "red_shap_1",
          "подавление ПВО - Су-24М (умеет SEAD), добивание - другой тип (Су-25), ударная - Су-25")
    flak = st["units"]["blue_flak_1"]
    det, thr = planner.detection_radius_km(flak), planner.threat_radius_km(flak)
    sup = next(x for x in model.doctrine(st, "red")["tasks"]["strike_column_march"]["support"] if x["id"] == "sead")
    d_line = planner.launch_distance_km(flak, sup)
    d_hold = model.dist_km(pk["sead"]["route"][0], model.unit_pos(st, flak))
    check(det == 12 and thr == 8 and d_line == 10 and abs(d_hold - 13) < 0.05,
          f"рубеж пуска ПРР {d_line:.0f} км = обнаружение Roland {det:.0f} - 2, вне зоны поражения {thr:.0f}; центр круга ожидания {d_hold:.1f} км (+3)")

    import copy as _copy
    st_s = _copy.deepcopy(st)                   # без свежих данных разведки - поиск РЛС в районе
    st_s.get("intel", {}).pop("blue_pzgren_bn_1", None)
    build.build(st_s, tmp / "pkg_stale.miz")
    ms = dcs.Mission(Germany())
    ms.load_file(str(tmp / "pkg_stale.miz"))
    pgs = {g.name.split(" ")[1]: g for g in plane_groups(ms)}
    zs = [t for p in pgs["sead"].points for t in p.tasks if getattr(t, "id", None) == "EngageTargetsInZone"]
    check(zs and not any(getattr(t, "id", None) == "EngageGroup" for p in pgs["sead"].points for t in p.tasks)
          and "Air Defence" in str(zs[0].params["targetTypes"]),
          "нет свежих данных разведки по ЗРК: пара ПРР ищет средства ПВО в районе, где их видели (не по группе)")
    from redfront import intel as _intel
    for sid in tk["threats"] + ["blue_pzgren_bn_1"]:   # разведка только что видела колонну с её ПВО - пуск по группе
        _intel.seen(st, st["units"][sid].get("attached_to") or sid, "разведка", (st["day"] - 1) * 86400 + (tk.get("tot_s") or 0))
    man = build.build(st, tmp / "pkg.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "pkg.miz"))
    pg = {g.name.split(" ")[1]: g for g in plane_groups(m)}
    vgs = {g.name: g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group}
    def attack_ids(g, kind="AttackGroup"):
        return [t.params["groupId"] for p in g.points for t in p.tasks if getattr(t, "id", None) == kind]
    check(set(pg) == {"strike", "sead", "kill", "recon"}, "в .miz четыре группы тактической группы")
    check(attack_ids(pg["strike"]) == [vgs["blue_pzgren_bn_1"].id], "ударная группа: AttackGroup по колонне")
    check(attack_ids(pg["sead"], "EngageGroup") == [vgs["blue_flak_1"].id] and attack_ids(pg["sead"]) == []
          and attack_ids(pg["kill"]) == [vgs["blue_flak_1"].id]
          and [p.name for p in pg["kill"].points[1:-1]] == ["Снижение", "Рубеж атаки", "Уход"],
          "пара ПРР - EngageGroup на всё ожидание; пара добивания с её рубежа - AttackGroup по той же войсковой ПВО")
    t_ = build.timeline(model.doctrine(st, "red")["tasks"]["strike_column_march"], st, tk["package"], "strike")
    for k in ("sead",):
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
    tgt = next(p for p in pg["strike"].points if p.name == "Цель")
    ipm = next(p for p in pg["strike"].points if p.name == "ИПМ")
    check(tgt.alt == 50 and ipm.alt == 300, "ударная группа: точка в зоне ЗРК - 50 м, вне зоны (ИПМ) - 300 м")
    check(attack_ids(pg["recon"]) == [], "доразведка: без AttackGroup по конкретной группе - цель ищет сама в районе")
    check(pg["sead"].task == "SEAD" and pylons_match(pg["sead"].units[0], "Retribution SEAD"),
          "Су-24М: задача DCS SEAD, подвеска 'Retribution SEAD' (Х-58У, Р-60М, Л-081 на пилоне 5)")
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
    from redfront import intel as _intel
    for sid in tk["threats"]:                    # свежие данные разведки (перед вылетом) - пуск по группам ЗРК
        _intel.seen(st, st["units"][sid].get("attached_to") or sid, "разведка", (st["day"] - 1) * 86400 + (tk.get("tot_s") or 0))
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
    import copy as _copy
    one = _copy.deepcopy(st)                     # один часовой шаг боя: потери = суточная доля / 24, одновременно
    one["settings"]["randomness"] = False
    a1, b1 = one["units"][a["id"]], one["units"][b["id"]]
    pw_a, pw_b = sim.power(one, a1), sim.power(one, b1)
    sa, sb = model.strength(a1), model.strength(b1)
    sim.battles(one, 1 / 24)
    fa = min(0.5, 0.15 * pw_b / pw_a) * (0.6 if a1.get("defending") else 1) / 24
    fb = min(0.5, 0.15 * pw_a / pw_b) * (0.6 if b1.get("defending") else 1) / 24
    check(abs((sa - model.strength(a1)) - sa * fa) < 1e-6 and abs((sb - model.strength(b1)) - sb * fb) < 1e-6,
          f"бой за час: потери одновременно, по соотношению сил ({pw_a:.1f} : {pw_b:.1f}), 1/24 суточной доли; у обороны "
          f"x0.6 - {sa:.1%}->{model.strength(a1):.1%} и {sb:.1%}->{model.strength(b1):.1%}")
    check(abs(model.strength(one["units"]["blue_flak_2"]) - model.strength(b1)) < 1e-6, "приданная ПВО несёт потери вместе с частью")
    sa, sb = model.strength(a), model.strength(b)
    sim.end_day(st)
    check(model.strength(a) < sa and model.strength(b) < sb,
          f"сутки боя по часам: {sa:.0%}->{model.strength(a):.0%} и {sb:.0%}->{model.strength(b):.0%}")
    tasks = planner.plan(st) and st["tasks"]
    kinds = [t["kind"] for t in tasks]
    check(kinds and kinds[0] == "cas_contact" and all(t["package"][0]["objective"]["kind"] == "column" for t in tasks if t["kind"] == "cas_contact")
          and not any(g["group"] == "recon" for t in tasks if t["kind"] == "cas_contact" for g in t["package"]),
          f"день 3: в плане {len(tasks)} задач, первыми - войска в соприкосновении (без доразведки): "
          + ", ".join(t["title"].split(": ")[1] for t in tasks))
    n = next(i for i, t in enumerate(tasks, 1) if t["target"] == "blue_pz_bn_1")
    tasks[n - 1]["tot_s"] = None                 # без времени плана: модель к миссии не продвигается (это - advance_section)
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
    st["tasks"][0]["tot_s"] = None               # без продвижения модели к миссии: сравниваем с окном, построенным выше
    man = build.build(st, tmp / "theatre.miz", task_no=1)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "theatre.miz"))
    s = next(a.text.id for a in _do(m) if "redfront battle site" in a.text.id)
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
    script = next(a.text.id for a in _do(m) if "redfront targets" in a.text.id)
    hook = next(a.text.id for a in _do(m) if "redfront debrief hook" in a.text.id)
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
    check(any("Luneburg" in o for o in owners) and len(took) >= 2,   # к 20-м суткам Люнебург могут и отбить
          f"красные взяли пункты: {', '.join(took)} (Люнебург - на сутках "
          f"{', '.join(str(i + 1) for i, o in enumerate(owners) if 'Luneburg' in o) or '-'}); за 20 дней кампания не встала")
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
    script = next(a.text.id for a in _do(m) if "redfront front" in a.text.id)
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
    acts = _do(m)
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
    s2 = next(a.text.id for a in _do(m2) if "redfront battle site" in a.text.id)
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
    from redfront import weapons
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
    blue = [g for c in m.coalition["blue"].countries.values() for g in c.plane_group if "_qra_" not in g.name]   # дежурные пары - qra_section
    t = build.timeline(model.doctrine(st, "red")["tasks"][t1["kind"]], st, t1["package"], "strike")
    zone = [x for p in red["cover"].points for x in p.tasks if getattr(x, "id", None) == "EngageTargetsInZone"]
    orb = [x for p in red["cover"].points for x in p.tasks if getattr(x, "id", None) == "ControlledTask"]
    check(zone and list(dict(zone[0].params["targetTypes"]).values()) == ["Air"] and orb and orb[0].params["stopCondition"] == {"time": t["strike"]["objective_s"] + 300}
          and next(p for p in red["cover"].points if p.name == "Зона прикрытия").alt == 3000
          and any("R-27R" in weapons.name_of(d["CLSID"]) for d in red["cover"].units[0].pylons.values()),
          f"прикрытие: зона 40 км над целью на 3000 м, перехват воздушных целей, до удара + 5 мин; МиГ-29 с Р-27Р и Р-73")
    en = [fl for fl in man["flights"] if fl.get("side") == "blue" and "_qra_" not in fl["group"]]
    own_ai = [fl for fl in man["flights"] if fl["group"].startswith("ai") and "_qra_" not in fl["group"]]
    qra_lines = [ln for ln in man["enemy_lines"] + man["ai_lines"] if "в готовности на стоянке" in ln]
    from redfront import ato
    win = [e for e in st["ato"]["entries"] if e["id"] != st["task"].get("ato_id") and not e["ai_only"]
           and ato.in_window(e, man["start_s"], man["end_s"])
           and not (e["times"]["strike"]["takeoff_s"] < man["start_s"] and e["times"]["strike"]["objective_s"] <= man["start_s"] + 60)]
    want = {side_: min(build.AI_FLIGHTS["enemy" if side_ == "blue" else "own"], sum(1 for e in win if e["side"] == side_))
            for side_ in ("red", "blue")}
    en_lines = [ln for ln in man["enemy_lines"] if ln not in qra_lines]
    ai_lines = [ln for ln in man["ai_lines"] if ln not in qra_lines]
    check(len(blue) == len(en) == len(en_lines) and 1 <= len(en) <= build.AI_FLIGHTS["enemy"]
          and len(en) <= want["blue"] and len(own_ai) <= want["red"] and len(ai_lines) == len(own_ai)
          and "Разведка: в районе возможна активность авиации противника." in m.description_text()
          and ("Другие вылеты наших сил" in m.description_text()) == bool(man["ai_lines"])   # и свои дежурные пары
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
    st["task"]["tot_s"] = None                   # без продвижения модели к миссии: колонна там, где её посчитал тест
    man = build.build(st, tmp / "colroad.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "colroad.miz"))
    heads = [a.text.id.splitlines()[0].split(" | ")[0] for a in _do(m)]
    check(man["column_road"] == ["blue_pzgren_bn_1", "blue_flak_1"]
          and heads == ["-- redfront column-on-road", "-- redfront battle site", "-- redfront targets", "-- redfront airbases",
                        "-- redfront lz", "-- redfront csar", "-- redfront debrief hook"],
          "без известных дорог: в триггере старта скрипт перекладки колонны, ..., поиск и спасение, затем хук")
    if not have_lupa():
        print("SKIP lupa не установлена: перекладка колонны в Lua не исполняется")
        return
    import lupa
    vg = next(g for c in m.coalition["blue"].countries.values() for g in c.vehicle_group if g.name == "blue_pzgren_bn_1")
    col = man["ground"][0]
    col_lua, hook_lua = _do(m)[0].text.id, _do(m)[-1].text.id    # скрипты ровно такие, как в собранном .miz

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
    from redfront import intel, sim
    sim.end_day(st)
    intel.seen(st, "blue_pzgren_bn_1", "тест")    # колонну видели утром (иначе через сутки - туман, задачи нет)
    planner.plan(st)
    man2 = build.build(st, tmp / "colroad2.miz")
    m2 = dcs.Mission(Germany())
    m2.load_file(str(tmp / "colroad2.miz"))
    check(man2["column_road"] == [] and not any("column-on-road" in a.text.id for a in _do(m2)),
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
    check(not nd and not any("новый склад" in l for l in lines),
          f"скопление складских объектов у пункта {far} - не цель: найденные склады ни на что не влияли")
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
    nb[0]["damage"] = 0.0                        # удары ИИ до миссии (sim.advance) могли его уже повредить
    g0 = ops.graph(st2)[a_][b_]
    nb[0]["damage"] = 1.0
    g1 = ops.graph(st2).get(a_, {}).get(b_)
    check(nb[0]["minor"] and logistics.link_open(st2, a_, b_) and g1 is not None and abs(g1 - g0 - 15) < 1e-6,
          f"разрушенный малый мост связь {a_}-{b_} не закрывает: объезд +15 км ({g0:.1f} -> {g1:.1f})")
    mover = {"id": "t", "route": [a_, b_], "progress_km": 1.0}
    check(sim_.current_link(st2, mover) == (a_, b_), "часть на связи с разрушенным малым мостом определяется (марш x0.5)")
    nb[0]["damage"] = 0.0
    check(not any(u.get("role") == "depot" and u.get("found") for u in st2["units"].values())
          and logistics.supplies(st2["units"]["red_depot_1"]),
          "зонд новых складов не создаёт (цели без последствий только путали); склады сценария снабжают")
    dummy = {"id": "depot_x", "name": "Склад (X)", "role": "depot", "side": "blue", "found": True, "supply": False,
             "pos": {"lat": 53.0, "lon": 10.5}, "state": "active", "damage": 0.0}
    st2["units"]["depot_x"] = dummy
    model.drop_dummy_depots(st2)
    check("depot_x" not in st2["units"], "старая кампания: найденные зондом склады при загрузке убираются")
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
    tk["tot_s"] = None                           # без продвижения модели к миссии: окно и театр - на одно время
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
    core = {g["unit"]: len(g["vehicles"]) for g in materialize.window(st, tk)
            if g["kind"] != "downed"}            # сбитый экипаж - не часть модели, в манифест наземных частей не входит
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
    check(all(n <= planner.MAX_PER_KIND for c in kinds.values() for k, n in c.items() if k not in ("airlift", "qra", "recon"))   # перевозки, дежурства, разведка - вне лимита
          and len(kinds["blue"]) >= 2,
          f"в плане дня не больше {planner.MAX_PER_KIND} задач одного вида: {dict(kinds['blue'])}")
    planner.plan(st)
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "cas_helo"
              or any(g.get("jaat_kind") == "cas_helo" for g in t["package"])), None)   # или в совместном пакете с самолётами
    check(n is not None, "в плане дня есть удар вертолётов по войскам в соприкосновении (сам или совместно с самолётами)")
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
    check(not gci["oob_germany_1985.json"] and len(gci["oob_germany.json"]) == 8 and "red_gci_stendal" in gci["oob_germany.json"],
          f"КРУ только где МиГ-29: 1985 - нет, 1987 - {len(gci['oob_germany_1987.json'])}, 1989 - {len(gci['oob_germany.json'])} "
          "(в т.ч. Штендаль - МиГ-29 JG-3, перебазированные из Прешена)")
    oob89 = json.loads((model.DATA / "oob_germany.json").read_text(encoding="utf-8"))
    st89 = camp["oob_germany.json"]
    air = [u for u in st89["units"].values() if model.category(u) in ("air", "heli")]
    reloc = oob89["_relocated"]
    check(all(u["base"] in st89["airbases"] for u in air) and not any("OFF:" in u["base"] for u in air)
          and len(reloc) >= 25 and all(st89["units"][k]["base"] == v["to"].lower().replace(" ", "_") for k, v in reloc.items())
          and y89["r336obvp"]["base"] == y89["r336obvp_8"]["base"] and y89["nva_jg3"]["base"] == y89["nva_jg3_21"]["base"]
          and "перебазирован" in y89["b_raf_bruggen"]["source"],
          f"базы вне карты: перебазировано частей - {len(reloc)}, на аэродромы карты своей стороны (подразделения полка - "
          f"вместе), ни одной базы вне карты; Брюгген -> {reloc['b_raf_bruggen']['to']}, Прешен -> {reloc['nva_jg3']['to']}")
    per_base: dict[str, int] = {}                # боевые реактивные части по аэродромам, все годы (части - один раз)
    for uid, u in {u["id"]: u for st in camp.values() for u in st["units"].values() if u.get("base")}.items():
        if u["role"] not in ("attack_helo", "transport_helo", "transport", "awacs", "tanker"):
            per_base[u["base"]] = per_base.get(u["base"], 0) + 1
    empty_before = [b for b in ("cochstedt", "sperenberg", "briest", "wunstorf", "fassberg", "sembach", "nordholz", "kiel")
                    if not per_base.get(b)]
    check(not empty_before and max(per_base.values()) <= 4,
          f"пустующие аэродромы заняты (Кохштедт, Шперенберг, Бриест, Вунсторф, Фасберг, Зембах, Нордхольц, Киль), "
          f"не больше 4 боевых частей на аэродроме за все годы (max {max(per_base.values())})")
    trans = [u for u in air if u["role"] in ("transport", "transport_helo")]
    from redfront import ato as _ato
    a = _ato.build(st89)
    tasked = {g["performer"] for e in a["entries"] if e["kind"] not in ("airlift", "air_assault") for g in e["task"]["package"]}
    check({u["side"] for u in trans} == {"red", "blue"} and len(trans) >= 15 and not tasked & {u["id"] for u in trans},
          f"транспорт: {len(trans)} частей (самолёты и вертолёты обеих сторон) в составе сил; задачи - только перевозки и десант")
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
    day_ok = all(w0 <= e["tot_s"] <= w1 for e in a["entries"] if not e["ai_only"] and not e.get("night"))
    night = [e for e in a["entries"] if e.get("night")]
    night_ok = all(e["tot_s"] >= w1 and e["kind"] in ato.NIGHT_KINDS and ato.night_capable(st, e["task"])
                   and max(t["land_s"] for t in e["times"].values()) <= 86400 for e in night)
    check(all(sides.values()) and not over and day_ok and night_ok,
          f"ATO на сутки: вылетов красных {sides['red']}, синих {sides['blue']}; днём - в лётном дне "
          f"{ato.hhmm(w0)}-{ato.hhmm(w1)}, ночью - {len(night)} глубоких ударов вечером типами, летающими ночью; "
          "самолётов частей не больше наличия в любой момент")
    shifts = sorted(e["tot_s"] for e in a["entries"] if e["kind"] == "awacs_orbit" and e["side"] == "blue")
    check(shifts and shifts[0] < 3600 and shifts[-1] >= 20 * 3600 and all(abs(b_ - a_ - 4 * 3600) < 1 for a_, b_ in zip(shifts, shifts[1:])),
          f"дежурство ДРЛО синих (E-3A летает ночью) - сменами по 4 ч круглые сутки: {', '.join(ato.hhmm(x) for x in shifts)}")
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
    coal = {b["airport"]: m.terrain.airports[b["airport"]].coalition for b in st["airbases"].values()}
    check(all(coal[b["airport"]] == ("NEUTRAL" if b.get("state") == "lost" else b["side"].upper())
              for b in st["airbases"].values())
          and m.terrain.airports["Hamburg"].coalition == "NEUTRAL",
          f"коалиция аэродромов - по модели: красных {sum(1 for c in coal.values() if c == 'RED')}, синих "
          f"{sum(1 for c in coal.values() if c == 'BLUE')}; гражданские - нейтральные")
    sg = [g for c in m.coalition.values() for cn in c.countries.values() for g in list(cn.plane_group) + list(cn.helicopter_group)
          if " strike " in g.name][0]
    perf = st["units"][st["tasks"][n - 1]["performer"]]
    tdef_ = model.doctrine(st, "red")["tasks"][st["tasks"][n - 1]["kind"]]
    land = sg.points[-1]
    check(abs(sg.points[1].speed * 3.6 - tdef_["speed_kmh"]) < 1 and land.type == "Land"
          and abs(land.speed * 3.6 - tdef_["speed_kmh"]) < 1,
          f"скорость ударной группы на маршруте - задачи доктрины ({sg.points[1].speed * 3.6:.0f} км/ч), точка посадки - "
          f"с той же скоростью, не 0 (ИИ не гасит скорость на возврате)")
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
    check(afs == {f"af_{b}" for b, x in st["airbases"].items() if x.get("kind") != "farp"},
          f"ПВО объекта у каждого военного аэродрома ({len(afs)}; вертолётные площадки - без неё)")
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
    site = next(a_.text.id for a_ in _do(m) if "redfront battle site" in a_.text.id)
    check(all(f'name = "{n}"' in site and f'unitId = {g.units[0].id}' in site for n, g in gg.items())
          and site.count("gci = { channel") == len(gg),
          "КРУ - в расстановке battle_site.lua (из воды, с аэродрома, из города - на сушу; Дамгартен стоял в заливе): "
          "пересоздаётся с тем же unitId, включение наведения ставится заново")
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
    check(pylons_match(fg.units[0]), "подвеска Су-25 по колонне - 'CAS' (своя: 2 Х-25МЛ, 2 ОФАБ-250-270, С-8, Р-60М): ровно её пилоны")

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
          f"при загрузке DCS по умолчанию ({n_default} пилонов) остаётся только подвеска по задаче, без смешения")

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
    g0 = st.get("ground_s") or 0                 # наземная модель уже на конце окна миссии - до 24:00 остаток суток
    rest = sum(min(86400, (h + 1) * 3600) - max(g0, h * 3600) for h in range(int(g0 // 3600), 24)
               if (h + 1) * 3600 > g0 and sim._night(st, h * 3600)[0] == 1.0) / 86400
    rest += sum(min(86400, (h + 1) * 3600) - max(g0, h * 3600) for h in range(int(g0 // 3600), 24)
                if (h + 1) * 3600 > g0 and sim._night(st, h * 3600)[0] != 1.0) / 86400 * sim._night(st, 0)[0]   # ночью медленнее
    sim.end_day(st)
    adv = bn["progress_km"] - km1
    check(st["day"] == 2 and abs(adv - BASELINE["advance_d2_km"] * rest) < 0.05,
          f"день 2: колонна прошла {adv:.2f} км за остаток суток после вылета ({rest:.0%} суточного отрыва с учётом ночи; за сутки - "
          f"{BASELINE['advance_d2_km']} км, как в 0.1)")
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
    check(fg3.units[0].type == "A-10A" and man3["sortie"] == 1 and fg3.units[0].pylons,
          "A_10A собран в .miz с подвеской по задаче из DCS Retribution")

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
def supply_section(tmp: Path) -> None:
    """Снабжение в тоннах: запасы складов, подвоз из тыла, расход по состоянию, отрезанный склад, воздушные перевозки
    транспортной авиацией (план полётов, миссия, сбитые борта), аэродром без снабжения."""
    from redfront import ato, logistics
    print("\n== снабжение и перевозки ==")
    st = model.new_campaign("sup", sector="sector_germany.json", oob="oob_germany.json", seed=3)
    U = st["units"]
    logistics.init_depots(st)
    d = U["red_depot_stendal"]
    u = next(x for x in U.values() if model.category(x) == "ground" and x["side"] == "red" and "route" in x)
    check(d["cap_t"] > 0 and d["stock_t"] == d["cap_t"]
          and abs(logistics.demand_t(st, u, "battle") - 5 * logistics.demand_t(st, u, "defend")) < 1e-6,
          f"склад - запас в тоннах ({d['cap_t']} т), расход части в бою впятеро больше, чем в обороне "
          f"({logistics.demand_t(st, u, 'battle'):.0f} / {logistics.demand_t(st, u, 'defend'):.0f} т в сутки)")
    d["damage"] = 0.5
    logistics.supply(st)
    check(d["stock_t"] <= d["cap_t"] * 0.5 + 1e-6, f"повреждение склада 50% уничтожает запас сверх половины ёмкости ({d['stock_t']:.0f} т)")
    # отрезанный склад: вокруг Галле - противник (аэродром Мерзебург рядом - туда можно возить воздухом)
    cut = U["red_depot_halle"]
    for a_, b_ in st["links"]:
        if cut["place"] in (a_, b_):
            other = b_ if a_ == cut["place"] else a_
            st["places"][other]["side"] = "blue"
    cut["stock_t"] = cut["cap_t"] * 0.2
    conn = logistics.road_connected(st, "red")
    before = cut["stock_t"]
    lines = logistics.supply(st)
    check(cut["id"] not in conn and cut["stock_t"] <= before and any("отрезан" in ln for ln in lines),
          "склад в окружении (Галле) - отрезан от подвоза из тыла, запас не пополняется")
    tdef = model.doctrine(st, "red")["tasks"]["airlift"]
    needs = [x[0]["id"] for x in planner.airlift_needs(st, "red", tdef)]
    st["ato"] = None
    a = ato.ensure(st)
    lifts = [e for e in a["entries"] if e["kind"] == "airlift" and e["side"] == "red"]
    to_cut = [e for e in lifts if e["task"]["package"][0]["objective"]["depot"] == cut["id"]]
    check(needs and needs[0] == cut["id"] and to_cut,
          f"перевозки: отрезанный склад - первый в очереди, рейсов к нему {len(to_cut)} "
          f"({to_cut[0]['title'] if to_cut else '-'})")
    g = to_cut[0]["task"]["package"][0]
    cargo = logistics.airlift_cargo_t(st, U[g["performer"]])
    a["lost"] = {to_cut[0]["id"]: 1}             # один борт первого рейса сбит в миссии
    for e in lifts:
        if e not in to_cut:
            a["entries"].remove(e)
    del a["entries"][a["entries"].index(to_cut[0]) + 1:]   # вылеты после первого рейса - не нужны для подсчёта
    a["entries"] = [e for e in a["entries"] if e["kind"] == "airlift"]
    before = cut["stock_t"]
    logistics.supply(st)
    got = st["supply_log"]["red"]["air_t"]
    check(abs(got - (g["size"] - 1) * cargo) < 1.0,
          f"рейс довёз {got} т ({g['size']} x {U[g['performer']]['type']}, {cargo} т борт; один сбит - его груз не дошёл)")
    # аэродром без снабжения - меньше самолётов к вылету
    perf = next(x for x in U.values() if x.get("role") == "fighter" and x["side"] == "red")
    full = logistics.available(st, perf)
    st["airbases"][perf["base"]]["supply"] = 0.0
    check(logistics.available(st, perf) == int(full * model.doctrine(st, "red")["sim"]["unsupplied"]),
          f"аэродром без снабжения: к вылету {logistics.available(st, perf)} из {full}")
    st["airbases"][perf["base"]]["supply"] = 1.0
    # миссия: рейс перевозки в окне - садится на аэродроме назначения; в журнале вылетов - номер рейса плана
    st = model.new_campaign("sup2", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    logistics.init_depots(st)
    st["units"]["red_depot_stendal"]["stock_t"] *= 0.3
    st["units"]["blue_depot_han"]["stock_t"] *= 0.2
    planner.plan(st)
    found = None
    for i in range(1, len(st["tasks"]) + 1):
        man = build.build(st, tmp / "lift.miz", task_no=i)
        st["manifest"] = None
        lf = [f for f in man["flights"] if "_lift" in f["group"]]
        if lf:
            found = (i, lf[0])
            break
    ok = False
    if found:
        m = dcs.Mission(Germany())
        m.load_file(str(tmp / "lift.miz"))
        e = next(e for e in st["ato"]["entries"] if e["id"] == found[1]["ato"])
        dest = st["airbases"][e["task"]["package"][0]["objective"]["airbase"]]["airport"]
        grp = next(g for c in m.coalition.values() for cn in c.countries.values()
                   for g in list(cn.helicopter_group) + list(cn.plane_group) if g.name.startswith(found[1]["performer"] + " "))
        ok = grp.points[-1].type == "Land" and grp.points[-1].airdrome_id == m.terrain.airports[dest].id \
            and str(grp.task) == "Transport"
    check(ok, f"миссия: рейс перевозки в окне задачи {found[0] if found else '-'} - взлёт со своей базы, посадка на "
              f"аэродроме назначения, задача DCS Transport; в журнале вылетов - номер рейса плана")


def assault_section(tmp: Path) -> None:
    """Вертолётный десант: рота в резерве, площадка в тылу противника (отрезать его склады), задача в плане дня,
    миссия (посадка, рота с поздней активацией, assault.lua), итог высадки - вылет игрока и ИИ, соединение со своими."""
    from redfront import assault, ato, logistics
    print("\n== вертолётный десант ==")
    st = model.new_campaign("aa", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    U = st["units"]
    res = assault.reserve(st, "red")
    tdef = model.doctrine(st, "red")["tasks"]["air_assault"]
    cands = assault.candidates(st, "red", tdef)
    own = [p for p in st["places"].values() if p["side"] == "red"]
    g_ = __import__("redfront.ops", fromlist=["graph"]).graph(st)
    check(len(res) == 3 and cands and all(
        tdef["assault_min_km"] <= min(model.dist_km(st["places"][c], q) for q in own) <= tdef["assault_max_km"]
        and not any(st["places"][q]["side"] == "red" for q in g_[c]) for c in cands),
          f"резерв: {len(res)} роты 35-й одшбр; площадки - пункты противника в {tdef['assault_min_km']}-{tdef['assault_max_km']} км "
          f"от своих, не соседние со своими (лучшие: {', '.join(cands[:3])})")
    planner.plan(st)
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "air_assault"), None)
    tk = st["tasks"][n - 1] if n else None
    g = tk["package"][0] if tk else {}
    perf = U.get(g.get("performer"), {})
    sizes = [x["size"] for x in tk["package"] if x["objective"]["kind"] == "air_assault"] if tk else []   # без прикрытия
    check(tk and model.category(perf) == "heli" and sum(sizes) == assault.lift_need(U[tk["target"]], perf["type"])
          and sum(sizes) <= tdef["max_helos"] and max(sizes) <= 4,
          f"в плане дня - десант: {tk['title'] if tk else '-'}; {sum(sizes)} x {perf.get('type')} поднимают роту "
          f"(группы DCS по 4 борта: {sizes})")
    man = build.build(st, tmp / "assault.miz", task_no=n)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "assault.miz"))
    hgs = [gr for c in m.coalition.values() for cn in c.countries.values() for gr in cn.helicopter_group
           if gr.name.startswith(perf["id"] + " ")]
    hg = next(gr for gr in hgs if " strike " in gr.name)
    lands = [t for p in hg.points for t in p.tasks if getattr(t, "id", None) == "Land"]
    in_miz = [gr for c in m.coalition.values() for cn in c.countries.values() for gr in cn.vehicle_group if gr.name == tk["target"]]
    acts = [a.text.id for a in _do(m)]
    script = next(t for t in acts if "redfront assault" in t)
    lz_lua = next(t for t in acts if "redfront lz" in t)
    ah = next(x for x in man["ground"] if x["kind"] == "airhead")
    check(lands and not in_miz and str(hg.task) == "Transport" and acts.index(lz_lua) < acts.index(script)
          and all(v["name"] in script for v in ah["vehicles"]) and all(u.name in script for gr in hgs for u in gr.units)
          and sum(len(gr.units) for gr in hgs) == sum(sizes),
          f"миссия: {sum(len(gr.units) for gr in hgs)} x {perf['type']} ({len(hgs)} группы) летят на площадку (Land); роты "
          f"в .miz нет - {len(ah['vehicles'])} фигур с именами модели появятся из бортов; площадки (lz.lua) - раньше десанта")
    if have_lupa():
        import lupa
        L = lupa.LuaRuntime(unpack_returned_tuples=True)
        L.execute(CSAR_MOCK)
        import re as _re
        spec_x, spec_y = map(float, _re.search(r"\bx = ([-\d.]+), y = ([-\d.]+)", script).groups())
        L.execute(f"BUILDINGS = {{ {{ x = {spec_x}, z = {spec_y} }} }}")      # на площадке - строение
        names = [u.name for gr in hgs for u in gr.units]
        player, ai_n = names[0], names[1]
        L.execute(f'PL = mkUnit("{player}", {spec_x + 30000}, 0, {spec_y}, 1, "Mi-8MT", false, false)')
        L.execute(f'AI1 = mkUnit("{ai_n}", {spec_x + 5000}, 300, {spec_y}, 1, "Mi-8MT", true, true)')
        L.execute(f'AIRBASES[1] = {{ {{ getPoint = function() return {{ x = {spec_x + 30000}, y = 0, z = {spec_y} }} end }} }}')
        L.execute('UNITS = { ["' + player + '"] = PL, ["' + ai_n + '"] = AI1 }; Unit.getByName = function(n) return UNITS[n] end')
        L.execute(lz_lua)
        L.execute(script)
        Gl = L.globals()
        rec = Gl.REDFRONT_ASSAULT[tk["ato_id"]]
        L.execute('for _, h in ipairs(world.handlers) do h:onEvent({ id = 15, initiator = PL }) end')
        Gl.CMDS["Высадить десант"]()
        refused = any("нет" in str(x) for x in Gl.MSG.values())
        Gl.CMDS["Загрузить десант"]()
        loaded = any("на борту" in str(x) for x in Gl.MSG.values())
        lz = L.eval("(function() local x, y = REDFRONT_LZ.find(" + f"{spec_x}, {spec_y}" + ") return {x, y} end)()")
        L.execute(f"AI1.u.p = {{ x = {lz[1] + 50}, y = 0, z = {lz[2]} }}; AI1.u.air = false")
        Gl.T = 5; L.execute("runDue()")
        ai_out = rec.landed == 1 and len(Gl.ADDED) == 1
        L.execute(f"PL.u.p = {{ x = {lz[1] - 100}, y = 0, z = {lz[2]} }}; PL.u.air = false")
        Gl.CMDS["Высадить десант"]()
        added = [Gl.ADDED[k] for k in Gl.ADDED]
        check(refused and loaded and ai_out and rec.landed == 2 and len(added) == 2
              and (lz[1], lz[2]) != (spec_x, spec_y),
              f"assault.lua: площадка со строением перенесена на открытое место; борт ИИ, севший на неё, высадил свою долю "
              f"сам; игрок - меню F10: без загрузки высадка не идёт, загрузка у своего аэродрома, высадка на площадке "
              f"(село {rec.landed} из {rec.total})")
    else:
        print("SKIP lupa не установлена: assault.lua не исполняется")
    # итог вылета игрока: по дебрифу (село 0 - сорвана, рота в сбитых бортах гибнет)
    st2 = __import__("copy").deepcopy(st)
    st2["ato"]["assault"] = {tk["ato_id"]: [0, sum(sizes)]}
    lines = assault.resolve(st2)
    u2 = st2["units"][tk["target"]]
    check(any("сорвана" in ln for ln in lines) and u2["order"] == "reserve" and model.strength(u2) < 1e-6,
          f"вылет игрока: на площадку никто не сел - высадка сорвана, рота в бортах погибла ({model.strength(u2):.0%})")
    st["ato"]["assault"] = {tk["ato_id"]: [sum(sizes), sum(sizes)]}
    lines = assault.resolve(st)
    u = U[tk["target"]]
    place = g["objective"]["place"]
    check(u["order"] == "airhead" and u["route"] == [place] and any("высажена" in ln for ln in lines),
          f"вылет игрока: сели все {sum(sizes)} бортов - рота держит {place} (order airhead), фронт ею не распоряжается")
    ai = [e for e in st["ato"]["entries"] if e["kind"] == "air_assault" and e["side"] == "blue"]
    check(ai and all(e.get("resolved") for e in ai) and any(st["units"][e["task"]["target"]]["order"] in ("airhead", "reserve") for e in ai),
          f"вылет ИИ (синие): {ai[0]['title'] if ai else '-'} - итог по угрозам коридора")
    # соединение со своими: пункт свой и снабжение со своих складов
    st["places"][place]["side"] = "red"
    u["supply_frac"] = 1.0
    lines = assault.linkup(st)
    check(u["order"] is None and any("соединилась" in ln for ln in lines), "пункт взят и снабжение со своих складов - десант соединился со своими, обычная часть")


CSAR_MOCK = r"""
T = 0; SCHED = {}; MSG = {}; RADIO = {}; STOPPED = {}; ADDED = {}; G = {}; HELIS = { [1] = {}, [2] = {} }; MENUS = {}
timer = { getTime = function() return T end, scheduleFunction = function(f, a, t) SCHED[#SCHED + 1] = { f = f, a = a, t = t } end }
function runDue()
  local again = {}
  for _, s in ipairs(SCHED) do
    if s.t <= T then local r = s.f(s.a, T); if r then again[#again + 1] = { f = s.f, a = s.a, t = r } end
    else again[#again + 1] = s end
  end
  SCHED = again
end
env = { info = function() end, warning = function() end }
AI = { Option = { Ground = { id = { ROE = 0 }, val = { ROE = { WEAPON_HOLD = 4 } } } } }
Unit = { Category = { HELICOPTER = 1 } }
Group = { Category = { GROUND = 2, HELICOPTER = 1 } }
world = { event = { S_EVENT_BIRTH = 15, S_EVENT_EJECTION = 6, S_EVENT_LAND = 4, S_EVENT_DEAD = 8, S_EVENT_CRASH = 5 }, handlers = {},
          VolumeType = { SPHERE = 2 } }
Object = { Category = { SCENERY = 5 } }
BUILDINGS = {}; AIRBASES = { [1] = {}, [2] = {} }; CMDS = {}; TASKED = {}
land = { SurfaceType = { LAND = 1, SHALLOW_WATER = 2, WATER = 3, ROAD = 4, RUNWAY = 5 }, getHeight = function() return 0 end,
         getSurfaceType = function(p) return 1 end }
function world.searchObjects(cat, vol, f)
  local c = vol.params.point
  for _, b in ipairs(BUILDINGS) do
    local dx, dz = b.x - c.x, b.z - c.z
    if math.sqrt(dx * dx + dz * dz) <= vol.params.radius then if not f(b) then return end end
  end
end
function world.getAirbases() return {} end
function world.addEventHandler(h) world.handlers[#world.handlers + 1] = h end
trigger = { action = {
  radioTransmission = function(f, p, mod, loop, fr, pw, name) RADIO[name] = fr end,
  stopRadioTransmission = function(name) STOPPED[name] = true end,
  outTextForGroup = function(id, t) MSG[#MSG + 1] = t end, outTextForCoalition = function(s, t) MSG[#MSG + 1] = t end,
  smoke = function() end, signalFlare = function() end } }
missionCommands = { addSubMenuForGroup = function(g, n) MENUS[#MENUS + 1] = n; return {} end,
                    addCommandForGroup = function(g, n, root, f) CMDS[n] = f end }
function mkUnit(name, x, y, z, side, typ, air, ai)
  local u = { name = name, p = { x = x, y = y, z = z }, side = side, typ = typ, air = air, ai = ai }
  local o = {}
  function o:getName() return u.name end
  function o:getPoint() return u.p end
  function o:inAir() return u.air end
  function o:isExist() return true end
  function o:isActive() return true end
  function o:getCoalition() return u.side end
  function o:getTypeName() return u.typ end
  function o:getDesc() return { category = 1 } end
  function o:getGroup() return { getID = function() return 77 end } end
  function o:getPlayerName() if u.ai then return nil end return "Игрок" end
  o.u = u
  return o
end
function mkGroup(name, unit)
  local g = { dead = false }
  local o = {}
  function o:getUnit(i) if not g.dead then return unit end end
  function o:getUnits() return { unit } end
  function o:getController() return { setCommand = function() end, setOption = function() end,
                                        setTask = function(_, t) TASKED[name] = t end } end
  function o:destroy() g.dead = true end
  function o:isExist() return not g.dead end
  function o:getName() return name end
  G[name] = { g = g, o = o }
  return o
end
Group.getByName = function(n) local x = G[n]; if x and not x.g.dead then return x.o end end
coalition = { addGroup = function(c, cat, t) ADDED[#ADDED + 1] = { country = c, name = t.name, type = t.units[1].type }
                local u = mkUnit(t.units[1].name, t.units[1].x, 0, t.units[1].y, c, t.units[1].type, false); mkGroup(t.name, u) end,
              getGroups = function(side, cat) local out = {}; for _, h in ipairs(HELIS[side]) do out[#out + 1] = { getUnits = function() return { h } end } end; return out end,
              getAirbases = function(side) return AIRBASES[side] end }
"""


def csar_section(tmp: Path) -> None:
    """Экипажи и поиск-спасение: экипажи полка ограничивают вылеты; дебриф - катапультировался (на земле) / спасён в
    миссии / погиб; сутки - вышел к своим, плен, спасение ИИ; задача CSAR в плане; миссия (пилот, маяк, csar.lua)."""
    from redfront import csar, logistics
    print("\n== экипажи и поиск-спасение ==")
    st = model.new_campaign("cs", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    U = st["units"]
    u = U["r33iap"]
    full = logistics.available(st, u)
    u["crews"] = 10
    check(u["crews0"] == round(u["count0"] * 1.2) and logistics.available(st, u) == 10,
          f"экипажи: штат {u['crews0']} (1.2 на самолёт); осталось 10 экипажей - к вылету 10 из {full}")
    u["crews"] = u["crews0"]
    # дебриф: три сбитых МиГ-29 - один катапультировался над ФРГ, второго подобрали в миссии, третий без катапультирования
    man = {"flights": [{"group": "strike", "performer": "r33iap", "units": ["a", "b", "c"], "player": True}]}
    from dcs.terrain.germany import Germany as _G
    from dcs.mapping import LatLng as _LL, Point as _P
    pt = _P.from_latlng(_LL(53.45, 10.30), _G())
    data = {"ejected": ["a", "b"], "dead": ["a", "b", "c"], "ejectpos": {"a": [pt.x, pt.y], "b": [pt.x, pt.y]},
            "csar": {"rescued": ["ej:b"], "lost": []}}
    c0 = u["crews"]
    lines = csar.apply_debrief(st, man, data, {"a", "b", "c"})
    dn = st["downed"]
    check(len(dn) == 1 and dn[0]["unit"] == "r33iap" and csar.owner_at(st, dn[0]["pos"]) == "blue" and u["crews"] == c0 - 2
          and any("спасён в миссии" in ln for ln in lines) and any("погиб" in ln for ln in lines),
          f"дебриф: катапультировался над ФРГ - экипаж на земле (маяк {dn[0]['freq_khz']} кГц), подобран в миссии - в полку, "
          f"без катапультирования - погиб (экипажей {c0} -> {u['crews']})")
    # задача CSAR в плане - первой; миссия: пилот на земле, маяк - ресурс миссии, скрипт знает экипаж
    planner.plan(st)
    tk = st["tasks"][0]
    check(tk["kind"] == "csar" and tk["target"] == dn[0]["id"] and model.category(U[tk["performer"]]) == "heli",
          f"в плане дня первым - {tk['title']} ({tk['package_notes']})")
    man = build.build(st, tmp / "csar.miz", task_no=1)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "csar.miz"))
    script = next(a.text.id for a in _do(m) if "redfront csar" in a.text.id)
    pilot = [gr for c in m.coalition.values() for cn in c.countries.values() for gr in cn.vehicle_group if gr.name == dn[0]["id"]]
    hg = next(gr for c in m.coalition.values() for cn in c.countries.values() for gr in cn.helicopter_group if " strike " in gr.name)
    lands = [t for p in hg.points for t in p.tasks if getattr(t, "id", None) == "Land"]
    res = [f for files in m.map_resource.files.values() for f in files.values()]
    check(pilot and man["downed"] == [dn[0]["id"]] and lands and any(f.endswith(build.BEACON_FILE) for f in res)
          and dn[0]["id"] in script and all(dn[0]["id"] != g["unit"] for g in man["ground"]),
          "миссия: пилот на земле у точки катапультирования, вертолёт садится рядом (Land), звук маяка - ресурс миссии, "
          "экипаж в скрипте csar.lua, но не в манифесте наземных частей")
    if have_lupa():
        import lupa
        L = lupa.LuaRuntime(unpack_returned_tuples=True)
        L.execute(CSAR_MOCK)
        L.execute(f'mkGroup("{dn[0]["id"]}", mkUnit("{dn[0]["id"]}#01", 0, 0, 0, 1, "Infantry AK", false))')
        L.execute('H1 = mkUnit("H1", 2000, 300, 0, 1, "Mi-8MT", true); HELIS[1] = { H1 }')
        L.execute("BUILDINGS = { { x = 0, z = 0 } }")               # пилот у строения - перенесётся
        lz_lua = next(a.text.id for a in _do(m) if "redfront lz" in a.text.id)
        L.execute(lz_lua)
        L.execute(script)
        Gl = L.globals()
        moved = Gl.ADDED[1] and Gl.ADDED[1].name == dn[0]["id"]
        L.execute('mkGroup("AIH", mkUnit("AIH#1", 9000, 300, 0, 1, "Mi-8MT", true, true))')
        L.execute('REDFRONT_LZ.retask("AIH", 100, 0, 90, nil)')
        pts = Gl.TASKED["AIH"].params.route.points
        retask = pts[2].task.params.tasks[1].id == "Land" and pts[2].x == 100
        radio_ok = bool(Gl.RADIO["csar_" + dn[0]["id"]])
        Gl.T = 1; L.execute("runDue()")
        heard = any("слышу" in str(x) for x in Gl.MSG.values())
        L.execute("H1.u.p = { x = 150, y = 0, z = 0 }; H1.u.air = false")
        for t in range(2, 60):
            Gl.T = t; L.execute("runDue()")
        picked = Gl.Group.getByName(dn[0]["id"]) is None and bool(Gl.STOPPED["csar_" + dn[0]["id"]])
        red_base = next(b["airport"] for b in st["airbases"].values() if b["side"] == "red")
        L.execute(f'for _, h in ipairs(world.handlers) do h:onEvent({{ id = 4, initiator = H1, place = {{ getName = function() return "{red_base}" end, getCoalition = function() return 0 end }} }}) end')
        rescued = bool(Gl.REDFRONT_CSAR.rescued[dn[0]["id"]])
        # катапультирование в миссии: экипаж появляется у точки, маяк сверху диапазона
        L.execute('P1 = mkUnit("P1", 5000, 3000, 5000, 2, "F-16C_50", true)')
        L.execute('for _, h in ipairs(world.handlers) do h:onEvent({ id = 6, initiator = P1 }) end')
        Gl.T = 70; L.execute("runDue()")
        spawned = Gl.ADDED[2]
        check(moved and retask and radio_ok and heard and picked and rescued and spawned and spawned.type == "Soldier M4"
              and bool(Gl.RADIO["csar_ej:P1"]),
              "csar.lua: пилот у строения перенесён на открытое место (lz.lua), вертолёту ИИ маршрут - посадка там; маяк с "
              "начала миссии; вертолёт ближе 3 км - \"слышу\"; сел в 150 м - пилот добежал, на борту, маяк выключен; "
              "посадка на свой аэродром - спасён; катапультировавшийся в миссии синий - на земле с маяком")
    else:
        print("SKIP lupa не установлена: csar.lua не исполняется")
    # сутки: ИИ-спасение, выход к своим, плен
    st2 = model.new_campaign("cs2", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    st2["settings"]["randomness"] = False
    u2 = st2["units"]["r33iap"]
    own = csar.add_downed(st2, u2, "x", {"lat": 52.6, "lon": 11.86})        # Штендаль - своя территория
    foe = csar.add_downed(st2, u2, "y", {"lat": 50.9, "lon": 8.0})          # глубоко у синих, вертолётам не достать
    c1 = u2["crews"]
    lines = csar.daily(st2)
    st2["day"] += 1
    lines += csar.daily(st2)
    check(not st2["downed"] and u2["crews"] == c1 + 1 and any("вышел к своим" in ln for ln in lines)
          and any("в плену" in ln or "пропал" in ln for ln in lines),
          "сутки: экипаж на своей территории вышел к своим (в полку), на чужой - в плену (без случайности - на вторые сутки)")


def convoy_section(tmp: Path) -> None:
    """Дороги и пути подвоза: граф по длине дорог, потоки складов по путям из тыла, колонны снабжения в миссии,
    удар по пути подвоза (миссия и ИИ) - недовоз."""
    from redfront import ato, convoys, logistics, ops, roads
    print("\n== пути подвоза и колонны снабжения ==")
    st = model.new_campaign("cv", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    a, b = st["links"][0]
    pa, pb = st["places"][a], st["places"][b]
    straight = model.dist_km(pa, pb)
    bend = model.offset(model.lerp(pa, pb, 0.5), model.bearing_deg(pa, pb) + 90, straight * 300)   # дорога в объезд
    roads.apply(st, {"paths": {f"{a}>{b}": [dict(pa), bend, dict(pb)]}}, note=False)
    g = ops.graph(st)
    check(abs(g[a][b] - st["road_km"][f"{a}>{b}"]) < 1e-6 and g[a][b] > straight * 1.1,
          f"граф пунктов - по длине дороги, если она известна ({a} - {b}: {g[a][b]:.1f} км по дороге, {straight:.1f} по прямой)")
    a2, b2 = st["links"][1]
    p2, q2 = st["places"][a2], st["places"][b2]
    far = model.offset(model.lerp(p2, q2, 0.5), model.bearing_deg(p2, q2) + 90, 150_000)   # "дорога" DCS через 150 км
    lines = roads.apply(st, {"paths": {f"{b2}>{a2}": [dict(q2), far, dict(p2)]}}, note=False)
    unit = {"route": [a2, b2]}
    check(f"{b2}>{a2}" not in st["roads"] and any("крюк" in ln for ln in lines)
          and abs(model.route_length_km(model.route_points(st, unit)) - model.dist_km(p2, q2)) < 1e-6,
          f"дорога-крюк DCS ({b2} - {a2} через 150 км в сторону) не берётся: участок по прямой (в т.ч. в обратную сторону)")
    sim.end_day(st)
    flows = {side: convoys.link_flows(st, side) for side in model.SIDES}
    rs = convoys.routes(st, "red")
    check(all(flows.values()) and rs and all(st["places"][r["path"][0]]["side"] == "red"
                                             and st["units"][r["depot"]]["place"] == r["path"][-1] for r in rs),
          f"пути подвоза: от пунктов входа (тыл) до складов; участков с потоком - красные {len(flows['red'])}, синие "
          f"{len(flows['blue'])}; больше всего - {max(flows['blue'], key=flows['blue'].get)} (~{max(flows['blue'].values()):.0f} т/сутки)")
    planner.plan(st)
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "strike_supply_route"), None)
    tk = st["tasks"][n - 1] if n else None
    check(tk and tk["link"] in flows["blue"] and flows["blue"][tk["link"]] >= convoys.MIN_FLOW_T,
          f"в плане дня - {tk['title'] if tk else '-'} ({tk['package_notes'] if tk else ''})")
    man = build.build(st, tmp / "convoy.miz", task_no=n)
    cv = next(c for c in man["convoys"] if c["link"] == tk["link"])
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "convoy.miz"))
    vg = next(gr for c in m.coalition.values() for cn in c.countries.values() for gr in cn.vehicle_group if gr.name == cv["unit"])
    strike = next(gr for gr in plane_groups(m) if " strike " in gr.name)
    attacks = [t for p in strike.points for t in p.tasks if getattr(t, "id", None) == "AttackGroup"]
    w = sum(v["weight"] for v in cv["vehicles"])
    check(len(vg.units) == len(cv["vehicles"]) and abs(w - flows["blue"][tk["link"]] / convoys.TRUCK_T * convoys.WINDOW_SHARE) < 1e-6
          and attacks and all(g_["unit"] != cv["unit"] for g_ in man["ground"]),
          f"миссия: колонна {len(vg.units)} грузовиков на участке (вес - {w:.1f} грузовиков потока), ударная группа "
          "атакует её (AttackGroup); в манифесте частей её нет - отдельно, как колонна снабжения")
    # дебриф: сожжено 3 машины - недовоз; конец суток - склад получил меньше
    dead = [v["name"] for v in cv["vehicles"][:3]]
    data = {"campaign": st["campaign_id"], "sortie": man["sortie"], "dead": dead, "ejected": [], "mission_ended": True}
    lines = debrief.apply(st, data)
    lost_t = sum(v["weight"] for v in cv["vehicles"][:3]) * convoys.TRUCK_T
    got = st["convoy_losses"]["blue"][tk["link"]]
    check(abs(got - lost_t) < 1e-6 and any("Колонна снабжения" in ln for ln in lines),
          f"дебриф: сожжено 3 машины колонны - недовоз ~{got:.0f} т на участке")
    by_depot = convoys.depot_losses(st, "blue")
    check(abs(sum(by_depot.values()) - got) < 1e-6,
          f"недовоз ложится на склады, чьи пути идут через участок: {', '.join(f'{k} {v:.0f} т' for k, v in by_depot.items())}")
    # удар ИИ вне миссии (без случайности - удачный при вероятности от 50%)
    st2 = model.new_campaign("cv2", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    st2["settings"]["randomness"] = False
    sim.end_day(st2)
    a2 = ato.ensure(st2)
    e = next((e for e in a2["entries"] if e["kind"] == "strike_supply_route"), None)
    lines = convoys.daily(st2) if e else []
    foe = model.enemy(e["side"]) if e else "blue"
    check(e and (st2.get("convoy_losses") or {}).get(foe, {}).get(e["task"]["link"], 0) > 0 and lines,
          f"удар ИИ по пути подвоза вне миссии: {lines[0] if lines else '-'}")


def advance_section(tmp: Path) -> None:
    """Наземная модель по часам: шаг до времени, командование по 6 ч, итоги вылетов ИИ в своё время, сборка миссии
    продвигает модель и цель, окно слетанной миссии - только события, план не идёт назад."""
    from redfront import airwar, ato
    print("\n== наземная модель по часам ==")
    st = model.new_campaign("adv", sector="sector_germany.json", oob="oob_germany.json", seed=2)
    st["settings"]["randomness"] = False
    sim.end_day(st)
    a = ato.ensure(st)
    marching = [u for u in st["units"].values() if u.get("state") == "march"]
    km0 = {u["id"]: u["progress_km"] for u in marching}
    strikes = [e for e in a["entries"] if not e["ai_only"] and e["task"]["package"][0]["objective"]["kind"] in ("column", "point", "site")
               and e["side"] != st["player_side"]]
    e = min(strikes, key=lambda x: x["tot_s"])
    tgt = st["units"][e["task"]["package"][0]["objective"]["unit"]]
    s0, d0 = model.strength(tgt), tgt.get("damage", 0.0)
    lines = sim.advance(st, e["tot_s"] + 1)
    moved = [u for u in marching if u["progress_km"] > km0[u["id"]] + 0.1]
    check(abs(st["ground_s"] - (e["tot_s"] + 1)) < 1 and moved and e.get("resolved")
          and (model.strength(tgt) < s0 or tgt.get("damage", 0.0) > d0),
          f"шаг до {sim.ato_hhmm(st['ground_s'])}: на марше продвинулись {len(moved)} частей; вылет ИИ дал итог в своё время "
          f"({e['title']}: {next((ln for ln in lines if e['title'] in ln), '-')})")
    before = st["ground_s"]
    check(sim.advance(st, before - 3600) == [] and st["ground_s"] == before, "модель назад не идёт")
    # сборка миссии: модель - к её началу, цель - на место
    planner.plan(st)
    tasks = st["tasks"]
    check(tasks and all(t["takeoff_s"] >= before for t in tasks), f"план дня - вылеты не раньше обстановки ({sim.ato_hhmm(before)})")
    n = next((i for i, t in enumerate(tasks, 1) if t["package"][0]["objective"]["kind"] == "column"), 1)
    man = build.build(st, tmp / "adv.miz", task_no=n)
    tk = st["task"]
    tgt = st["units"].get(tk["package"][0]["objective"].get("unit") or "")
    check(man["ground_s"] >= before and (not tgt or model.dist_km(model.unit_pos(st, tgt), tk["target_pos"]) < 0.3),
          f"сборка: обстановка на {sim.ato_hhmm(man['ground_s'])} (начало миссии), цель задачи - на своём месте к этому времени")
    # окно слетанной миссии: только события, без марша
    km1 = {u["id"]: u["progress_km"] for u in st["units"].values() if u.get("state") == "march"}
    data = {"campaign": st["campaign_id"], "sortie": man["sortie"], "dead": [], "ejected": [], "mission_ended": True}
    debrief.apply(st, data)
    still = all(abs(st["units"][k]["progress_km"] - v) < 1e-9 for k, v in km1.items() if st["units"][k].get("state") == "march")
    check(still and st["ground_s"] >= man["end_s"] - 1 and set(st["ato"].get("played", [])) >= {f["ato"] for f in man["flights"] if f.get("ato")},
          f"дебриф: окно миссии пройдено только событиями (марша нет), обстановка на {sim.ato_hhmm(st['ground_s'])}; "
          f"группы ИИ миссии - слетаны ({len(st['ato'].get('played', []))})")


def qra_section(tmp: Path) -> None:
    """Дежурные пары ПВО: смены в плане суток, пара на стоянке (поздняя активация) в миссии, взлёт по обнаружению
    радарами своей стороны (qra.lua), влияние на удары ИИ вне миссии."""
    from redfront import airwar, ato
    print("\n== дежурные пары ПВО ==")
    st = model.new_campaign("qra", sector="sector_germany.json", oob="oob_germany.json", seed=1)
    a = ato.ensure(st)
    q = [e for e in a["entries"] if e["kind"] == "qra"]
    bases = {side: {e["task"]["base"] for e in q if e["side"] == side} for side in model.SIDES}
    tdef = model.doctrine(st, "red")["tasks"]["qra"]
    check(all(1 <= len(b) <= tdef["qra_bases"] for b in bases.values())
          and all(e["times"]["strike"]["land_s"] - e["times"]["strike"]["takeoff_s"] <= tdef["shift_h"] * 3600 for e in q),
          f"дежурство: пары на аэродромах у фронта сменами по {tdef['shift_h']} ч - красные {sorted(bases['red'])}, "
          f"синие {sorted(bases['blue'])}")
    planner.plan(st)
    n = next(i for i, t in enumerate(st["tasks"], 1) if t["package"][0]["objective"]["kind"] in ("column", "point"))
    man = build.build(st, tmp / "qra.miz", task_no=n)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "qra.miz"))
    qg = [g for g in plane_groups(m) if "_qra_" in g.name]
    script = next((a_.text.id for a_ in _do(m) if "redfront qra" in a_.text.id), "")
    eng = all(any(getattr(t, "id", None) == "EngageTargets" for p in g.points for t in p.tasks) for g in qg)
    check(qg and all(g.late_activation for g in qg) and eng and all(g.name in script for g in qg)
          and any(f.get("ato") and "_qra_" in f["group"] for f in man["flights"]),
          f"миссия: {len(qg)} дежурных пар на стоянках с поздней активацией, задача - атака воздушных целей; скрипт их знает")
    if have_lupa():
        import lupa
        L = lupa.LuaRuntime(unpack_returned_tuples=True)
        L.execute(CSAR_MOCK)
        L.execute("""
          Controller = { Detection = { RADAR = 4 } }
          Group.Category.AIRPLANE = 0
          ACTIVATED = {}; SEEN = false
          RADARS = { [1] = {}, [2] = {} }; AIR = { [1] = {}, [2] = {} }
          local function grp(units, ctrl) return { getUnits = function() return units end, getController = function() return ctrl end } end
          coalition.getGroups = function(side, cat)
            if cat == Group.Category.GROUND then return RADARS[side] end
            if cat == Group.Category.AIRPLANE then return AIR[side] end
            return {}
          end
          function radarGroup(side)
            local u = { isExist = function() return true end, hasAttribute = function(_, a) return a == "EWR" end }
            local c = { isTargetDetected = function(_, t, d) return SEEN end }
            RADARS[side][#RADARS[side] + 1] = grp({ u }, c)
          end
          function plane(side, x, z)
            local u = { isExist = function() return true end, inAir = function() return true end,
                        getPoint = function() return { x = x, y = 5000, z = z } end, getTypeName = function() return "Su-25" end }
            AIR[side][#AIR[side] + 1] = grp({ u }, nil)
          end
        """)
        import re as _re
        first = _re.search(r'\{ id = "([^"]+)", group = "([^"]+)", side = (\d), x = ([-\d.]+), y = ([-\d.]+), r = (\d+)', script)
        qid, gname, side, x, y, r = first.groups()
        side = int(side); foe = 2 if side == 1 else 1
        L.execute(f'radarGroup({side}); plane({foe}, {float(x) + float(r) * 0.5}, {y})')
        L.execute(f'G["{gname}"] = {{ g = {{ dead = false }}, o = {{ activate = function() ACTIVATED["{gname}"] = true end }} }}')
        L.execute(script)
        Gl = L.globals()
        Gl.T = 10; L.execute("runDue()")
        quiet = not Gl.ACTIVATED[gname]
        Gl.SEEN = True
        Gl.T = 20; L.execute("runDue()")
        check(quiet and Gl.ACTIVATED[gname] and Gl.REDFRONT_QRA[qid],
              "qra.lua: противник в радиусе, но радары стороны его не видят - пара стоит; увидели - пара поднята, время - в дебриф")
    else:
        print("SKIP lupa не установлена: qra.lua не исполняется")
    e = q[0]
    pos = st["airbases"][e["task"]["base"]]
    n_near = airwar.alerts_near(st, e["side"], pos, e["tot_s"] + 60)
    far = model.offset(pos, 270 if e["side"] == "red" else 90, 600_000)   # в 600 км в тылу противника
    check(n_near >= 1 and airwar.alerts_near(st, e["side"], far, e["tot_s"] + 60) == 0,
          f"вне миссии: удар ИИ рядом с базой дежурной пары на смене - её учитывают ({n_near}), далеко от баз - нет")


def _do(m) -> list:
    """Действия DoScript триггера начала миссии (без DoScriptFile - MIST и CTLD файлами)."""
    return [a for a in m.triggerrules.triggers[0].actions if hasattr(a, "text")]


def _miz_scripts(path: Path) -> list[tuple[str, str]]:
    """Действия триггера начала миссии из .miz: (предикат, текст скрипта или ключ ресурса)."""
    import zipfile

    import lupa
    L = lupa.LuaRuntime()
    L.execute(zipfile.ZipFile(path).read("mission").decode("utf-8"))
    tr = L.globals().mission.trigrules
    return [(a.predicate, a.text or a.file) for k in tr for _j, a in tr[k].actions.items()]


CTLD_MOCK = r"""
ctld = { i18n = { en = {} }, spawnedCratesRED = {}, spawnedCratesBLUE = {}, CB = {}, LASE = {} }
function ctld.initialize() ctld.INIT = true end
function ctld.addCallback(f) ctld.CB[#ctld.CB + 1] = f end
function ctld.JTACAutoLase(name, code, smoke, lock) ctld.LASE[name] = code end
ctld.MENU = {}
function ctld.addTransportF10MenuOptions(n) ctld.MENU[n] = true end
function fire(a) for _, f in ipairs(ctld.CB) do f(a) end end
ZONES = {}
trigger.misc = { getZone = function(n) return ZONES[n] end }
STATICS = {}
StaticObject = { getByName = function(n) return STATICS[n] end }
UNITS = {}
Unit.getByName = function(n) return UNITS[n] end
function crate(x, z) return { isExist = function() return true end, getPoint = function() return { x = x, y = 0, z = z } end } end
"""


def _ctld_lua(scripts: list[str]):
    import lupa
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(CSAR_MOCK)
    L.execute(CTLD_MOCK)
    for s_ in scripts:
        L.execute(s_)
    return L


def ctld_section(tmp: Path) -> None:
    """CTLD (lua/ctld): десант игрока - погрузка и высадка через меню CTLD, на площадке - доля роты из модели;
    перевозка снабжения игроком на вертолёте - ящики CTLD, доставленное - в дебриф и на склад; авианаводчик у своего
    взвода в бою цели (CAS). В .miz - MIST и CTLD с ctld.dontInitialize = true (инициализирует настройка redfront)."""
    import copy
    import re as _re
    import zipfile

    from redfront import logistics
    print("\n== CTLD: десант, перевозки, авианаводчик ==")
    st0 = model.new_campaign("ct", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    planner.plan(st0)
    for _ in range(2):                           # бои у фронта (удар по войскам в соприкосновении)
        sim.end_day(st0)
    logistics.init_depots(st0)
    for d in logistics.objects(st0, "depot"):    # склады пусты - перевозки снабжения
        if d["side"] == "red" and d.get("cap_t"):
            d["stock_t"] = 0.3 * d["cap_t"]
    st0.pop("ato", None)
    planner.plan(st0)
    kinds: dict[str, int] = {}
    for i, t in enumerate(st0["tasks"], 1):
        kinds.setdefault(t["kind"], i)
    need = {"airlift", "air_assault", "cas_contact"}
    check(need <= set(kinds), f"в плане игрока есть перевозка на вертолёте, десант и удар по войскам в соприкосновении ({sorted(kinds)})")
    if not need <= set(kinds):
        return
    built = {}
    for k in sorted(need):
        st = copy.deepcopy(st0)
        built[k] = (st, build.build(st, tmp / f"ctld_{k}.miz", task_no=kinds[k]))
    z = zipfile.ZipFile(tmp / "ctld_airlift.miz")
    ctld_src = z.read(next(n for n in z.namelist() if n.endswith("/CTLD.lua"))).decode("utf-8")
    check(any(n.endswith("/mist.lua") for n in z.namelist()) and "ctld.dontInitialize = true" in ctld_src
          and "ctld.dontInitialize = false" not in ctld_src, "в .miz - mist.lua и CTLD.lua (копия с ctld.dontInitialize = true)")
    st_a, man_a = built["air_assault"]
    st_l, man_l = built["airlift"]
    st_c, man_c = built["cas_contact"]
    check(man_a["ctld"]["pilots"] and not man_a["ctld"]["lifts"] and man_a["ctld_lines"],
          f"десант: борт игрока - в CTLD ({man_a['ctld']['pilots'][0]}), в брифинге - как грузить и высаживать")
    check(man_l["ctld"]["lifts"] == [st_l["task"]["ato_id"]], "перевозка: вылет игрока - зона выгрузки CTLD")
    check(man_c["ctld"]["jtacs"] and not man_c["ctld"]["pilots"], "удар по войскам в соприкосновении: авианаводчик, без перевозок")
    if not have_lupa():
        print("SKIP lupa не установлена: ctld_cfg.lua не исполняется")
        return
    # ---- десант: CTLD высадил группу у площадки - вместо неё доля роты из модели; далеко от площадки - не засчитано ----
    acts = _miz_scripts(tmp / "ctld_air_assault.miz")
    texts = [t for a, t in acts if a == "a_do_script"]
    heads = ("-- redfront ctld", "-- redfront assault")
    pos = [next(i for i, t in enumerate(texts) if t.startswith(h)) for h in heads]
    check([a for a, _t in acts].count("a_do_script_file") == 2 and pos == sorted(pos),
          "скрипты: MIST и CTLD файлами, затем настройка CTLD и десант (по порядку)")
    cfg, asl = (texts[i] for i in pos)
    L = _ctld_lua([cfg, asl])
    Gl = L.globals()
    pilot = man_a["ctld"]["pilots"][0]
    m_ = _re.search(r'x = ([-\d.]+), y = ([-\d.]+), r = (\d+)', asl)
    lx, ly = float(m_.group(1)), float(m_.group(2))
    sid = next(iter(Gl.REDFRONT_ASSAULT.keys()))
    L.execute(f'UNITS["{pilot}"] = mkUnit("{pilot}", {lx + 5000}, 0, {ly}, 1, "Mi-8MT", false)')
    L.execute('far = mkGroup("ctld far", mkUnit("c1", 0, 0, 0, 1, "Infantry", false))')
    L.execute(f'fire({{ action = "dropped_troops", unit = UNITS["{pilot}"], unloaded = far }})')
    off_lz = Gl.REDFRONT_ASSAULT[sid].landed == 0
    L.execute(f'UNITS["{pilot}"].u.p = {{ x = {lx + 100}, y = 0, z = {ly} }}')
    L.execute('near = mkGroup("ctld near", mkUnit("c2", 0, 0, 0, 1, "Infantry", false))')
    L.execute(f'fire({{ action = "dropped_troops", unit = UNITS["{pilot}"], unloaded = near }})')
    added = [Gl.ADDED[i].name for i in range(1, len(Gl.ADDED) + 1)]
    # борт игрока уже в кабине до скриптов (в одиночной игре BIRTH пропущен): меню CTLD и CSAR - по опросу
    csar_lua = next(t for t in texts if t.startswith("-- redfront csar"))
    L.execute(csar_lua)
    L.execute(f'coalition.getPlayers = function(side) if side == 1 then return {{ UNITS["{pilot}"] }} end return {{}} end')
    Gl.T = 6
    L.execute("runDue()")
    menus = [Gl.MENUS[i] for i in range(1, len(Gl.MENUS) + 1)]
    check(Gl.ctld.MENU[pilot] and "CSAR" in menus,
          "борт игрока родился до скриптов (событие пропущено): меню CTLD и CSAR добавлены опросом")
    check(Gl.ctld.INIT and Gl.REDFRONT_CTLD.pilots[pilot] and off_lz and Gl.REDFRONT_ASSAULT[sid].landed == 1
          and Gl.Group.getByName("ctld near") is None and Gl.Group.getByName("ctld far") is not None
          and any(str(n).startswith(sid) for n in added),
          "десант через CTLD: высадка в 5 км от площадки не засчитана (группа CTLD осталась - её можно забрать), "
          "на площадке - группа CTLD убрана, вместо неё доля роты из модели; борт засчитан")
    # ---- перевозка: ящики снабжения в зоне выгрузки и распакованные там - кг в REDFRONT_LIFT ----
    acts = _miz_scripts(tmp / "ctld_airlift.miz")
    cfg = next(t for a, t in acts if a == "a_do_script" and t.startswith("-- redfront ctld"))
    L = _ctld_lua([cfg])
    Gl = L.globals()
    lid = man_l["ctld"]["lifts"][0]
    zone = Gl.ctld.dropOffZones[1][1]
    w = Gl.ctld.spawnableCrates["Supply"][1].weight
    L.execute(f'ZONES["{zone}"] = {{ point = {{ x = 1000, y = 0, z = 1000 }}, radius = 2500 }}')
    L.execute(f'STATICS["in"] = crate(1500, 1000); STATICS["out"] = crate(9000, 1000); '
              f'ctld.spawnedCratesRED["in"] = {{ weight = {w} }}; ctld.spawnedCratesRED["out"] = {{ weight = {w} }}')
    Gl.T = 20
    L.execute("runDue()")
    kg1 = Gl.REDFRONT_LIFT[lid]
    pilot = man_l["ctld"]["pilots"][0]
    L.execute(f'UNITS["{pilot}"] = mkUnit("{pilot}", 1200, 0, 1000, 1, "Mi-8MT", false)')
    L.execute('truck = mkGroup("truck", mkUnit("t1", 0, 0, 0, 1, "Ural-375", false))')
    L.execute(f'fire({{ action = "unpack", unit = UNITS["{pilot}"], crate = {{ details = {{ weight = {w} }} }}, spawnedGroup = truck }})')
    kg2 = Gl.REDFRONT_LIFT[lid]
    check(kg1 == int(w) and kg2 == 2 * int(w) and Gl.Group.getByName("truck") is None,
          f"перевозка через CTLD: ящик в зоне выгрузки - {kg1} кг (вне зоны - не в счёт), распакованный в зоне - ещё "
          f"{int(w)} кг, машина груза убрана")
    # дебриф -> склад: груз игрока - доставленное, а не грузоподъёмность борта
    a = st_l["ato"]
    e = next(x for x in a["entries"] if x["id"] == lid)
    g = e["task"]["package"][0]
    d = st_l["units"][g["objective"]["depot"]]
    data = {"campaign": st_l["campaign_id"], "sortie": man_l["sortie"], "lift": {lid: 1000}, "dead": [], "ejected": [],
            "landed": [], "takeoff": [], "mission_ended": True}
    lines = debrief.apply(st_l, data)
    check(a["lift"].get(lid) == 1.0 and lid in a["done"] and any("доставлено 1.0 т" in ln for ln in lines),
          "дебриф: доставлено ящиками 1 т - в плане полётов, вылет слетан")
    g["size"] = 1
    for x in a["entries"]:                       # остальные перевозки дня - не в счёт
        if x["kind"] == "airlift" and x["id"] != lid:
            x["task"]["package"][0]["size"] = 0
    perf = st_l["units"][g["performer"]]
    cap = logistics.airlift_cargo_t(st_l, perf)
    logistics.supply(st_l)
    air = st_l["supply_log"]["red"]["air_t"]
    check(abs(air - 1.0) < 0.05, f"склад {d['name']}: воздухом за сутки {air} т - доставленное игроком, а не {cap} т грузоподъёмности")
    # ---- авианаводчик: у своего взвода, лазер с кодом, тип поста стороны ----
    acts = _miz_scripts(tmp / "ctld_cas_contact.miz")
    cfg = next(t for a, t in acts if a == "a_do_script" and t.startswith("-- redfront ctld"))
    j = _re.search(r'\["platoon"\] = "([^"]+)", \["target"\] = "([^"]+)"', cfg)
    L = _ctld_lua([f'mkGroup("{j.group(1)}", mkUnit("p1", 0, 0, 0, 1, "BMP-2", false)); '
                   f'mkGroup("{j.group(2)}", mkUnit("t1", 2000, 0, 0, 2, "M-1", false))', cfg])
    Gl = L.globals()
    jid = man_c["ctld"]["jtacs"][0]
    jt = next((Gl.ADDED[i] for i in range(1, len(Gl.ADDED) + 1) if Gl.ADDED[i].name == jid), None)
    check(jt is not None and Gl.ctld.LASE[jid] == build.JTAC_CODE and jt.type == build.JTAC_TYPES["red"],
          f"авианаводчик: пост у своего взвода, подсветка с кодом {build.JTAC_CODE}")


def command_section(tmp: Path) -> None:
    """Режим командующего (command.py): правка плана полётов своей стороны - перенос, смена части, бортов, подвески,
    снять вылет, поставить задачу вне плана; самолёты частей проверяются по всему плану."""
    from redfront import ato, command
    print("\n== режим командующего: правка плана полётов ==")
    st = model.new_campaign("cmd", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    planner.plan(st)
    a = st["ato"]
    mine = [e for e in a["entries"] if e["side"] == "red" and not command._is_duty(st, e)]
    # вылет с небольшим пакетом: у большого (расчистка, демонстрация) на 15:30 истребителей может не хватить - это верный отказ
    e = next((x for x in mine if len(x["task"]["package"]) <= 3
              and model.category(st["units"][x["task"]["package"][0]["performer"]]) == "air"), mine[0])
    o = command.options(st, e["id"])
    g = o["groups"][0]
    alt = next(p for p in g["performers"] if p["id"] != g["performer"] and p["type"] != st["units"][g["performer"]]["type"])
    lines = command.edit(st, e["id"], tot="15:30", groups={"strike": {"performer": alt["id"], "size": 3}})
    g0 = e["task"]["package"][0]
    check(ato.hhmm(e["tot_s"]) == "15:30" and g0["performer"] == alt["id"] and g0["size"] == 3
          and g0["base"] == st["units"][alt["id"]]["base"] and e["times"]["strike"]["objective_s"] == e["tot_s"],
          f"вылет перенесён на 15:30, ударная группа - 3 x {alt['type']}: {'; '.join(lines[1:])}")
    try:
        command.edit(st, e["id"], tot="23:55")
        late = False
    except ValueError:
        late = True
    check(late and ato.hhmm(e["tot_s"]) == "15:30" and g0["size"] == 3, "посадка после конца суток - вылет не изменён")
    # самолёты части - по всему плану: другой вылет в то же время той же частью сверх наличия не встаёт
    perf = st["units"][g0["performer"]]
    perf["count"] = 4                            # к вылету 4: 3 уже в этом вылете
    other = next(x for x in mine if x is not e and command.why_locked(st, x) is None
                 and perf["role"] in model.doctrine(st, "red")["tasks"][x["kind"]]["performers"]
                 and any(p_["id"] == perf["id"] for p_ in command.options(st, x["id"])["groups"][0]["performers"]))
    try:
        command.edit(st, other["id"], tot="15:30", groups={"strike": {"performer": perf["id"], "size": 2}})
        why = ""
    except ValueError as err:
        why = str(err)
    ok_later = ["не встал ни в какое время"]
    for h in range(7, 20):                       # в другое время (когда у части есть свободный борт) - встаёт
        try:
            ok_later = command.edit(st, other["id"], tot=f"{h:02d}:00", groups={"strike": {"performer": perf["id"], "size": 1}})
            break
        except ValueError:
            continue
    check("не хватает самолётов" in why and other["task"]["package"][0]["performer"] == perf["id"],
          f"самолёты части по всему плану: в 15:30 у неё 3 из 4 заняты - пара не встаёт ({why.split(': ', 1)[-1]}); "
          f"в другое время - встаёт ({ok_later[-1]})")
    n0 = len(a["entries"])
    c = command.candidates(st)
    add = command.add(st, c[0]["key"])
    check(len(a["entries"]) == n0 + 1 and any(x["id"].startswith("red-cmd") for x in a["entries"]), f"задача вне плана: {add[0]}")
    rm = command.remove(st, e["id"])
    planner.plan(st)
    check(all(x["id"] != e["id"] for x in a["entries"]) and all(t["ato_id"] != e["id"] for t in st["tasks"]),
          f"{rm} - его нет ни в плане полётов, ни в списке вылетов игрока")
    blue = next(x for x in a["entries"] if x["side"] == "blue")
    try:
        command.remove(st, blue["id"])
        locked = False
    except ValueError:
        locked = True
    check(locked, "план противника не правится")


def farp_section(tmp: Path) -> None:
    """Передовые вертолётные площадки (farp.py): площадки карты - базы модели; вертолётные части выдвигаются на свои
    ближе к фронту, при угрозе уходят; самолёты на площадки не перебазируются; вылет игрока - с площадки."""
    from redfront import farp, logistics
    print("\n== передовые вертолётные площадки ==")
    st = model.new_campaign("fp", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    fps = {k: b for k, b in st["airbases"].items() if b.get("kind") == "farp"}
    check(len(fps) > 20 and all(farp.NAME.match(b["airport"]) for b in fps.values()) and {b["side"] for b in fps.values()} == {"red", "blue"},
          f"площадки карты в модели: {len(fps)} (без медицинских и радарных), у обеих сторон")
    lines = farp.daily(st)
    moved = [u for u in st["units"].values() if farp.is_farp(st["airbases"].get(u.get("base")))]
    ok = all(model.category(u) == "heli" and u.get("home") and farp.FARP_MIN_KM <= st["airbases"][u["base"]]["front_km"] <= farp.FARP_MAX_KM
             for u in moved) and len({u["base"] for u in moved}) == len(moved)
    check(moved and ok, f"выдвинулись {len(moved)} вертолётных частей, каждая на свою площадку в {farp.FARP_MIN_KM}-{farp.FARP_MAX_KM} км от "
                        f"противника: {lines[0]}")
    u = moved[0]
    b = st["airbases"][u["base"]]
    foe = next(x for x in st["units"].values() if x["side"] != u["side"] and model.category(x) == "ground" and x["state"] != "pending")
    near = min(st["places"], key=lambda q: model.dist_km(b, st["places"][q]))
    foe["state"], foe["route"], foe["progress_km"] = "defend", [near], 0.0   # противник прорвался к площадке
    lines = farp.daily(st)
    check(u["base"] == u["home"] and b["state"] in ("closed", "lost") and any("уход" in ln for ln in lines),
          f"противник у площадки: она закрыта, часть ушла на основной аэродром ({st['airbases'][u['base']]['name']})")
    jet = next(x for x in st["units"].values() if model.category(x) == "air")
    st["airbases"][jet["base"]]["state"] = "closed"
    logistics.airfields(st)
    check(not farp.is_farp(st["airbases"][jet["base"]]), "самолёты с закрытого аэродрома на вертолётную площадку не уходят")


def evac_section(tmp: Path) -> None:
    """Эвакуация десанта (assault.evac_*, lua/evac.lua): рота в тылу противника дольше evac_days - задача плана; в
    миссии рота у площадки группами по вместимости борта, борт ИИ забирает группу сам, игрок - меню CTLD; сбитый борт -
    группа погибла; итог - вывезенные в резерве, остальные потеряны."""
    from redfront import assault
    print("\n== эвакуация десанта ==")
    st = model.new_campaign("ev", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    u = next(x for x in st["units"].values() if x["side"] == "red" and x.get("air_mobile"))
    u.update(route=["Uelzen"], progress_km=0.0, state="defend", order="airhead", airhead_day=st["day"] - 3)
    planner.plan(st)
    n = next((i for i, t in enumerate(st["tasks"], 1) if t["kind"] == "air_evac"), None)
    check(n is not None, "рота в тылу противника 3 суток - в плане полётов эвакуация")
    if n is None:
        return
    man = build.build(st, tmp / "evac.miz", task_no=n)
    g = next(x for x in man["ground"] if x["unit"] == u["id"])
    check(g["kind"] == "evac" and man["evac"] and man["ctld"]["extract"] and len(man["ctld"]["extract"]) * 6 >= len(g["vehicles"]),
          f"миссия: рота ({len(g['vehicles'])} фигур) у площадки группами для CTLD ({len(man['ctld']['extract'])}), игрок - через CTLD")
    if have_lupa():
        acts = _miz_scripts(tmp / "evac.miz")
        texts = [t for a, t in acts if a == "a_do_script"]
        ev = next(t for t in texts if t.startswith("-- redfront evac"))
        L = _ctld_lua([])
        L.execute("REDFRONT_LZ = nil")
        groups = man["ctld"]["extract"]
        import re as _re
        m_ = _re.search(r'\["x"\] = ([-\d.e]+), \["y"\] = ([-\d.e]+)', ev)
        lx, ly = float(m_.group(1)), float(m_.group(2))
        for k, gn in enumerate(groups):           # группы роты в миссии (заглушки)
            L.execute(f'mkGroup("{gn}", mkUnit("{gn} u", {lx}, 0, {ly}, 1, "Paratrooper", false))')
        L.execute(ev)
        Gl = L.globals()
        eid = man["evac"][0]
        helos = _re.findall(r'\["helos"\] = \{ ([^}]*) \}', ev)[0]
        names = _re.findall(r'"([^"]+)"', helos)
        player, ai = names[0], names[1]
        L.execute(f'UNITS["{ai}"] = mkUnit("{ai}", {lx + 100}, 0, {ly}, 1, "Mi-8MT", false, true)')
        Gl.T = 10
        L.execute("runDue()")
        one = Gl.REDFRONT_EVAC[eid].saved
        L.execute(f'REDFRONT_EVAC_CTLD("{player}", {{ details = {{ groupName = "{groups[1]}", units = {{ {{}}, {{}}, {{}} }} }} }})')
        two = Gl.REDFRONT_EVAC[eid].saved
        L.execute(f'for _, h in ipairs(world.handlers) do h:onEvent({{ id = world.event.S_EVENT_DEAD, initiator = UNITS["{ai}"] }}) end')
        check(one == 1 and two == 4 and Gl.REDFRONT_EVAC[eid].saved == 3 and Gl.Group.getByName(groups[0]) is None,
              "evac.lua: борт ИИ сел у площадки и забрал группу; игрок забрал группу через CTLD; борт ИИ сбит - его группа погибла")
    # дебриф: игрок забрал одну группу сам, ведомый ИИ разбился без огня противника (DCS) - не потеря, его доля - по модели
    a = st["ato"]
    eid = man["evac"][0]
    pkg = [fl for fl in man["flights"] if not fl.get("ato") and not fl.get("side")]
    me = next(fl["units"][0] for fl in pkg if fl.get("player"))
    wing = next(n for fl in pkg for n in fl["units"] if n != me)
    perf = st["units"][pkg[0]["performer"]]
    c0 = perf["count"]
    import copy
    st2 = copy.deepcopy(st)                      # для проверки частичной эвакуации - до дебрифа
    data = {"campaign": st["campaign_id"], "sortie": man["sortie"], "dead": [wing], "ejected": [], "landed": [], "takeoff": [],
            "hit": [], "evac": {eid: [6, 24, 0, 6]}, "mission_ended": True}
    lines = debrief.apply(st, data)
    n_ai = sum(len(fl["units"]) for fl in pkg) - 1
    want = min(24, 6 + 6 * n_ai)
    check(perf["count"] == c0 and any("без огня противника" in ln for ln in lines) and a["evac"][eid] == [want, 24],
          f"дебриф: ведомый ИИ разбился сам - не потеря; вывезено: ваши 6 фигур + доля {n_ai} ведомых ИИ по модели = {want} из 24")
    check(u["order"] == "reserve" and model.strength(u) > 0.99, "после дебрифа (окно миссии): рота вывезена вся, в резерве")
    # итог в модели: вывезена половина живых - рота в резерве, половина потеряна
    st = st2
    u = st["units"][u["id"]]
    st["ato"].setdefault("evac", {})[eid] = [12, 24]
    s0 = model.strength(u)
    e = next(x for x in st["ato"]["entries"] if x["id"] == eid)
    lines = assault.evac_resolve(st, e["tot_s"])
    check(u["order"] == "reserve" and st["places"][u["route"][0]]["side"] == "red" and abs(model.strength(u) - s0 * 0.5) < 0.02,
          f"итог: {lines[0] if lines else '-'} (боеспособность {s0:.0%} -> {model.strength(u):.0%})")
    # вместимость - от типа ЛА: Ми-24 берёт солдат, Апач - нет
    check(assault.troops("Mi_24P") == 8 and assault.troops("AH_64A") == 0 and assault.troops("SA342M") == 0,
          "солдат на борт - по типу: Ми-24П 8, AH-64A и SA342M - никого")


def fitness_section(tmp: Path) -> None:
    """Пригодность типа для задачи с учётом эпохи (fitness.py): оценка - относительно лучшего типа в кампании."""
    from redfront import fitness
    print("\n== пригодность типа ЛА ==")
    st = model.new_campaign("fit", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    with_a10 = fitness.relative(st, "Su_25", "cas")
    for u in st["units"].values():               # "другая эпоха": A-10 и Апачей в кампании нет
        if u.get("type") in ("A_10A", "AH_64A"):
            u["count"] = 0
    without = fitness.relative(st, "Su_25", "cas")
    check(abs(with_a10 - 0.85) < 1e-6 and abs(without - 1.0) < 1e-6,
          f"Су-25 для удара по войскам: рядом с A-10 - {with_a10:.2f}, без него (своя эпоха) - {without:.2f}")
    check(fitness.relative(st, "F_15C", "strike") == 0.0 and not fitness.fits(st, {"type": "F_15C"}, "strike")
          and fitness.relative(st, "Mi_8MT", "cas") == 1.0,
          "без оценки вида задач у типа с оценками - не годится (F-15C по объектам); тип без оценок - без учёта (Ми-8)")
    best = fitness.pick_key(st, {"type": "MiG_27K"}, "strike", 0)
    busy = fitness.pick_key(st, {"type": "MiG_27K"}, "strike", 3)
    other = fitness.pick_key(st, {"type": "Su_17M4"}, "strike", 0)
    check(best < other < busy, "выбор: лучший тип - первым, но после трёх задач его очередь уступает следующему типу")


def fog_section(tmp: Path) -> None:
    """Смена позиций ЗРК (samroam.py), туман войны (intel.py), перебазирование авиачастей командующим (command.py)."""
    from redfront import command, intel, samroam
    print("\n== ЗРК, разведка, перебазирование ==")
    st = model.new_campaign("fog", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    mob = {samroam.mobility({"composition": [{"type": t, "count": 1} for t in c]}) for c in
           (["Osa_9A33_ln"],)} | {samroam.mobility({"composition": [{"type": "Patriot_ln", "count": 1}, {"type": "Gepard", "count": 1}]})}
    check(mob == {"high", "low"} and samroam.front_factor(20) == 1.0 and samroam.front_factor(200) == 0.0,
          "подвижность - по самому медленному комплексу (Оса - высокая, Пэтриот с Гепардом - низкая); в глубоком тылу не двигаются")
    free = [u for u in st["units"].values() if model.category(u) == "sam" and not u.get("fixed") and not u.get("attached_to")]
    start = {u["id"]: dict(u["pos"]) for u in free}
    moves = 0
    for _ in range(6):
        moves += sum(1 for ln in sim.end_day(st) if "смена позиции (" in ln)
    far = [u for u in free if u["side"] == "blue" and u["state"] != "destroyed"]
    roam_ok = all(model.dist_km(u["pos"], u.get("anchor", start[u["id"]])) <= samroam.CLASSES[samroam.mobility(u)][3] + 0.1
                  for u in free if "anchor" in u)
    check(0 < moves < len(free) * 6 * 0.3 and roam_ok,
          f"за 6 суток {moves} смен позиций у {len(free)} самостоятельных ЗРК - не перетасовка, каждый в своём районе")
    moved = [u for u in far if model.dist_km(u["pos"], start[u["id"]]) > 0.5]
    if moved:
        u = moved[0]
        check(model.dist_km(intel.known_pos(st, u), start[u["id"]]) < 0.1,
              f"туман войны: {u['name']} сменил позицию - игрок видит прежнюю")
        st["task"] = {"package": [{"base": next(iter(st["airbases"])), "route": [dict(u["pos"])]}]}
        intel.after_debrief(st, {"ground": [{"unit": u["id"]}]})
        check(model.dist_km(intel.known_pos(st, u), u["pos"]) < 0.1, "после вылета рядом - позиция уточнена")
    su = next(u for u in st["units"].values() if u.get("type") == "Su_25" and u["side"] == "red")
    o = command.base_options(st, su["id"])
    tgt = o["options"][0]
    msg = command.rebase(st, su["id"], tgt["id"])
    base0 = su["base"]
    lines = sim.end_day(st)
    check(su["base"] == tgt["id"] != base0 and su.get("base_fixed") and any("перебазирована" in ln for ln in lines),
          f"командующий: {msg}")
    try:
        command.base_options(st, next(u["id"] for u in st["units"].values() if u["side"] == "blue" and model.category(u) == "air"))
        locked = False
    except ValueError:
        locked = True
    jet_farp = any(x["farp"] for x in o["options"])
    check(locked and not jet_farp, "чужие части не перебазируются; самолётам вертолётные площадки не предлагаются")


def ground_fog_section(tmp: Path) -> None:
    """Туман войны для наземных частей противника (intel.py): журнал, карта, цели игрока, удары своих ИИ."""
    from redfront import airwar, gui, intel
    print("\n== Туман войны: наземные части ==")
    st = model.new_campaign("gfog", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    foe = [u for u in st["units"].values() if intel.tracked_ground(st, u) and u["state"] != "pending"]
    check(foe and all(intel.level(st, u["id"]) == "exact" for u in foe),
          f"начало кампании: все {len(foe)} частей противника на местах известны (разведка мирного времени)")
    pend = [u for u in st["units"].values() if intel.tracked_ground(st, u) and u["state"] == "pending"]
    v = gui.view(st)
    shown = {g["id"] for g in v["ground"]}
    check(not (shown & {u["id"] for u in pend}), "резервы противника из глубины на карте не видны")
    a, b = foe[0], foe[1]
    st["intel"][a["id"]]["t"] = intel.now(st) - 30 * 3600          # видели 30 ч назад - примерно
    st["intel"][a["id"]]["pos"] = model.offset(model.unit_pos(st, a), 0, 25000)
    del st["intel"][b["id"]]                                        # не видели - неизвестна
    far = all(model.dist_km(model.unit_pos(st, x), model.unit_pos(st, o)) > intel.CONTACT_KM
              for x in (a, b) for o in st["units"].values() if o["side"] == st["player_side"] and model.category(o) == "ground")
    if far:
        v = gui.view(st)
        ga = next((g for g in v["ground"] if g["id"] == a["id"]), None)
        check(ga and ga["intel"] == "approx" and ga["strength"] is None and "route" not in ga and ga["unc_km"] > 0
              and model.dist_km({"lat": ga["pos"][0], "lon": ga["pos"][1]}, st["intel"][a["id"]]["pos"]) < 0.1
              and b["id"] not in {g["id"] for g in v["ground"]},
              f"карта: {a['name']} - где видели, 'примерно', без боеспособности и маршрута; неизвестная - не показана")
        check(not intel.can_target(st, b) and intel.can_target(st, a) == (a["state"] != "march"),
              "цели игрока: неизвестная - нет; по примерным данным - только стоящая (не колонна на марше)")
        tasks, _w = planner.plan_side(st, st["player_side"], max_tasks=99, per_kind=99)
        check(all(t.get("target") != b["id"] for t in tasks), "план стороны игрока: по неизвестной части задач нет")
        e = {"side": st["player_side"], "task": {"package": [{"objective": {"pos": st["intel"][a["id"]]["pos"]}}]}}
        ff, why = airwar._find(st, e, a, e["task"]["package"][0]["objective"])
        e2 = dict(e, side=model.enemy(st["player_side"]))
        check(ff == 0.0 and "ушла" in why and airwar._find(st, e2, a, {"pos": {}})[0] == 1.0,
              "удар своих ИИ по данным 25-км давности - цель не найдена; противник бьёт по настоящему положению")
    own = next(o for o in st["units"].values() if o["side"] == st["player_side"] and model.category(o) == "ground"
               and o["state"] not in ("pending", "destroyed") and not o.get("attached_to"))
    b["pos"] = model.offset(model.unit_pos(st, own), 90, 5000)      # подошла к нашей части - соприкосновение
    b.pop("route", None)
    b["state"] = "defend"
    lines = intel.update(st)
    check(intel.level(st, b["id"]) == "exact" and lines, f"соприкосновение: {b['name']} у наших - снова известна ({lines[0]})")
    st["intel"][b["id"]]["t"] = intel.now(st) - 60 * 3600
    lv0 = intel.level(st, b["id"])
    intel.update(st)
    check(lv0 == "presence" and intel.level(st, b["id"]) == "exact", "пока в соприкосновении - данные обновляются")


def recon_section(tmp: Path) -> None:
    """Разведывательные вылеты ИИ (recon.py): маршрут по давним данным, полоса датчиков по типу, сбитый - без данных."""
    from redfront import ato, intel, recon
    print("\n== Воздушная разведка ==")
    check(recon.swath_km("Su_24MR", True) == (25.0, 150.0) and recon.swath_km("MiG_25RBT", True)[0] == 0
          and recon.swath_km("MiG_25RBT", False) == (20.0, 250.0) and recon.swath_km("Tornado_GR4", True)[0] == 5,
          "датчики по типу: Су-24МР ночью - РЛС БО 25 км; МиГ-25РБ ночью наземных частей не видит (только фото); Tornado GR.1A - ИК")
    st = model.new_campaign("recon", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    foe = [u for u in st["units"].values() if intel.tracked_ground(st, u) and u["state"] != "pending"]
    for u in foe:
        st["intel"][u["id"]]["t"] = intel.now(st) - 60 * 3600          # всё давнее - только присутствие
    a = ato.ensure(st)
    rec = [e for e in a["entries"] if e["kind"] == "recon"]
    own = [e for e in rec if e["side"] == st["player_side"]]
    perf_ok = all(st["units"][e["task"]["performer"]]["role"] == "recon" for e in rec)
    check(own and perf_ok and all(e["ai_only"] for e in rec) and {e["side"] for e in rec} == {"red", "blue"},
          f"план полётов: {len(own)} разведывательных вылетов своей стороны (только ИИ, части разведки), у противника - тоже")
    check(not any(t["kind"] == "recon" for t in (planner.plan(st) and st["tasks"]) or []),
          "игроку разведка не предлагается")
    e = own[0]
    g = e["task"]["package"][0]
    check(len(g["route"]) >= 2 and all(model.dist_km(st["airbases"][g["base"]], p) <= planner.strike_radius_km(st["units"][g["performer"]])
                                       for p in g["route"]), f"маршрут: {e['title']} ({len(g['route'])} точек, в радиусе части)")
    lines = recon.resolve(st, ato.DAY_S)
    fresh = [u for u in foe if intel.level(st, u["id"]) == "exact"]
    check(fresh and any("Разведка" in ln for ln in lines), f"после вылетов уточнено {len(fresh)} частей: {next(ln for ln in lines if 'Разведка' in ln)}")
    t_rec = st["intel"][fresh[0]["id"]]["t"]
    check(any(abs(t_rec - x["tot_s"]) < 1 for x in own), "данные - на время пролёта, не на время итога")
    st2 = model.new_campaign("recon2", sector="sector_germany.json", oob="oob_germany.json", seed=525990)
    for u in st2["units"].values():
        if intel.tracked_ground(st2, u) and u["id"] in st2["intel"]:
            st2["intel"][u["id"]]["t"] = intel.now(st2) - 60 * 3600
    a2 = ato.ensure(st2)
    mine = [x for x in a2["entries"] if x["kind"] == "recon" and x["side"] == st2["player_side"]]
    a2["played"] = [x["id"] for x in mine]
    a2["lost"] = {x["id"]: x["task"]["package"][0]["size"] for x in mine}
    lines2 = recon.resolve(st2, ato.DAY_S)
    check(all("не вернулся" in ln for ln in lines2 if "Разведка" in ln) and lines2
          and not any(intel.level(st2, u["id"]) == "exact" for u in st2["units"].values() if intel.tracked_ground(st2, u)),
          "разведчик сбит в миссии - данных нет")


def explain_section(tmp: Path) -> None:
    """Пояснения для игрока (explain.py): цели задач, объекты тыла, пути подвоза, итог удара."""
    from redfront import explain, gui
    print("\n== Пояснения для игрока ==")
    st = model.new_campaign("expl", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    sim.end_day(st)
    planner.plan(st)
    v = gui.view(st)
    route = next((t for t in v["tasks"] if "путям подвоза" in t["title"]), None)
    dep = next((t for t in v["tasks"] if t["title"].startswith("Удар по складу")), None)
    check(route and any("грузовиков" in x and "подвоза" in x for x in route["goal"]),
          f"путь подвоза в задаче: {route and route['goal'][0]}")
    check(dep and any("Ёмкость" in x for x in dep["goal"]) and any("Удар" in x for x in dep["goal"]),
          f"склад в задаче: {dep and ' / '.join(dep['goal'][:2])}")
    check(v["rear"] and all(r["info"] for r in v["supply_routes"]) and all(o["info"] for o in v["objects"] if o["role"] != "airfield" or o.get("side")),
          "вкладка 'Тыл', подсказки путей подвоза и объектов - с пояснениями")
    check(not any(o.get("stock_t") is not None for o in v["objects"] if o["side"] != st["player_side"]),
          "запас складов противника - только оценка (без тонн)")
    d = next(o for o in st["units"].values() if o.get("role") == "depot" and o["side"] != st["player_side"] and o.get("cap_t"))
    d["stock_t"] = d["cap_t"]
    d["damage"] = 0.6
    msg = explain.damage_effect(st, d, 0.0)
    check("сгорело" in msg and abs(d["stock_t"] - d["cap_t"] * 0.4) < 1, f"итог удара по складу:{msg}")
    for i in (1, 2):                             # заводы - из зонда карты (в составе сил Германии их нет)
        st["units"][f"fac{i}"] = {"id": f"fac{i}", "name": f"Завод {i}", "role": "factory", "side": "blue",
                                  "state": "active", "damage": 0.0, "pos": dict(d["pos"])}
    f = st["units"]["fac1"]
    check(any("x1.00 -> x0.75" in x for x in explain.obj(st, f, "red")), f"завод: {explain.obj(st, f, 'red')[1]}")
    f["damage"] = 1.0
    check("->" in explain.damage_effect(st, f, 0.0), f"итог удара по заводу:{explain.damage_effect(st, f, 0.0)}")


def crew_section(tmp: Path) -> None:
    """Лётчики (pilots.py), ливрея полка, несколько людей в вылете, передовая группа на площадке (farp.py)."""
    from redfront import csar, farp, pilots
    print("\n== Лётчики, ливрея, люди, передовые группы ==")
    st = model.new_campaign("crew", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    u = st["units"]["r33iap"]
    check(len(u["pilots"]) == u["crews"] and pilots.nation(st["units"]["b_raf_2sqn"]) == "uk"
          and pilots.nation(st["units"]["b_ag51"]) == "frg" and len({p["name"] for p in u["pilots"]}) == len(u["pilots"]),
          f"лётчики по числу экипажей, имена без повторов, национальность по части: {pilots.title(u, u['pilots'][0])}")
    planner.plan(st)
    n = next(i for i, t in enumerate(st["tasks"], 1) if len(t["package"]) > 1 and t["package"][0]["size"] == 2)
    t = st["tasks"][n - 1]
    perf = st["units"][t["package"][0]["performer"]]
    perf["livery"] = "test livery"
    man = build.build(st, tmp / "crew.miz", task_no=n, humans=3)
    fl = man["flights"]
    hum = [x for f in fl for x in f.get("humans", [])]
    names = [x for f in fl for x in f["units"]]
    check(len(hum) == 3 and fl[0]["humans"] == fl[0]["units"] and len(fl[1]["humans"]) == 1,
          f"3 человека: группа игрока целиком ({', '.join(fl[0]['humans'])}), затем ведущий следующей группы")
    check(len(names) == len(set(names)) and all(pilots.find(st["units"][f["performer"]], fl[0]["units"][0]) or True for f in fl)
          and pilots.find(perf, fl[0]["units"][0]), "имена ЛА в миссии - лётчики полков, без повторов")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "crew.miz"))
    us = [x for c in m.coalition[t["side"]].countries.values() for g in c.plane_group for x in g.units if x.name in hum]
    import zipfile
    ms = zipfile.ZipFile(tmp / "crew.miz").read("mission").decode("utf-8", "replace")
    check("setCoalition" in ms and "autoCapture(false)" in ms, "стороны аэродромов - и скриптом в начале миссии (без автозахвата)")
    check(len(us) == 3 and all(x.skill.value == "Client" and x.livery_id == "test livery" for x in us[:2]),
          "в .miz: места людей - Client (мультиплеер), ливрея полка на самолётах")
    lead = fl[0]["units"][0]
    d = csar.add_downed(st, perf, lead, {"lat": 52.0, "lon": 11.0})
    gone = pilots.find(perf, lead) is None
    csar.returned(st, d, "спасён")
    check(gone and pilots.find(perf, lead) is not None, f"сбитый лётчик ({lead}) - вне списка, спасён - снова в полку")
    # передовая группа: полк Ми-24 (40) на площадку - сколько поместится
    h = next(x for x in st["units"].values() if x.get("type") == "Mi_24P" and x["side"] == "red" and x["count"] >= 24)
    bid = next(k for k, b in st["airbases"].items() if b.get("kind") == "farp" and b.get("side") == "red")
    cap = farp.capacity(st["airbases"][bid])
    c0, crews0, n0 = h["count"], h["crews"], len(h["pilots"])
    det = farp.detach(st, h, bid)
    check(det is not h and det["count"] == cap and h["count"] == c0 - cap and det["crews"] + h["crews"] == crews0
          and len(det["pilots"]) + len(h["pilots"]) == n0 and det["base"] == bid,
          f"на площадку ({st['airbases'][bid]['slots']} стоянок) - передовая группа {cap} из {c0}, остальные - на аэродроме")
    farp.merge(st, det)
    check(h["count"] == c0 and h["crews"] == crews0 and det["id"] not in st["units"], "передовая группа вернулась в полк")


def reinforce_section(tmp: Path) -> None:
    """Добавить полк: историческое допущение (Су-24М в 1989) и свой."""
    from redfront import ato, reinforce
    print("\n== Добавление полков ==")
    st = model.new_campaign("reinf", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    cat = {c["id"] for c in reinforce.catalog(st)}
    check({"r116bap", "r497bap"} <= cat, f"список допущений (части других пресетов): {sorted(cat)}")
    reinforce.add_historical(st, "r116bap")
    u = st["units"]["r116bap"]
    check(u["added"] == "historical" and u["crews"] > 0 and len(u["pilots"]) == u["crews"] and "r116bap" not in
          {c["id"] for c in reinforce.catalog(st)}, "116-й гв. бап добавлен: экипажи, лётчики, из списка убран")
    msg = reinforce.add_custom(st, {"name": "Свой полк", "side": "red", "role": "attack_helo", "type": "Mi_24P",
                                    "count": 12, "base": u["base"]})
    try:
        reinforce.add_custom(st, {"name": "x", "side": "red", "role": "bomber", "type": "Mi_24P", "count": 4, "base": u["base"]})
        bad = False
    except ValueError:
        bad = True
    check("add_red_1" in st["units"] and bad, f"свой полк: {msg}; вертолёт с самолётной ролью - отказ")
    sim.end_day(st)
    a = ato.ensure(st)
    n = sum(1 for e in a["entries"] for g in e["task"]["package"] if g["performer"] == "r116bap")
    check(n > 0, f"Су-24М добавленного полка в плане полётов следующих суток: {n} групп")


def nato_section(tmp: Path) -> None:
    """Доктрина НАТО (nato.json по RAND R-3385, ATP-27(C), AJP-3.3): годы, полосы глубины, доли, SEAD только у США."""
    from redfront import ato, farp, pilots
    print("\n== Доктрина НАТО ==")
    st = model.new_campaign("nato", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    check(st["doctrine"]["blue"] == "nato", "синие по умолчанию - доктрина НАТО")
    sim.end_day(st)
    ts, _w = planner.plan_side(st, "blue", max_tasks=ato.ATO_MAX_TASKS, per_kind=ato.ATO_PER_KIND)
    reg = [t for t in ts if not t.get("ai_only")]
    ap = model.doctrine(st, "blue")["apportionment"]
    dca = sum(1 for t in reg if t["kind"] in ap["classes"]["DCA"])
    check(reg and dca <= round(0.25 * ato.ATO_MAX_TASKS), f"доли категорий: DCA {dca} из {len(reg)} задач плана")
    bai = [t for t in reg if t["kind"] == "strike_bai"]
    ok = all(15 <= farp.front_km(st, "red", t["target_pos"]) <= 50 for t in bai)
    check(ok, f"BAI - колонны в 15-50 км за передним краем ({len(bai)} задач)")
    sead = [g for t in reg for g in t["package"] if g["group"].startswith("sead")]
    check(all(pilots.nation(st["units"][g["performer"]]) == "us" for g in sead + [g for t in reg for g in t["package"] if g["group"] == "kill"]),
          f"подавление ПВО - только части США ({len(sead)} групп), союзники - без него")
    hk = [t for t in reg if any(g["group"] == "kill" for g in t["package"])]
    pk_ = {g["group"]: g for g in hk[0]["package"]} if hk else {}
    check(hk and pk_["sead"]["performer"] == "b_52tfw" and pk_["kill"]["performer"] == "b_52tfw_f16"
          and pk_["sead"]["objective"]["units"] == pk_["kill"]["objective"]["units"],
          "hunter-killer: пара поиска с ПРР - 52-е крыло (F-4E вместо F-4G), пара добивания - F-16C того же крыла, по тем же ЗРК")
    st90 = model.new_campaign("nato90", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    st90["date"] = "1990-06-01"
    sim.end_day(st90)
    ts90, _w = planner.plan_side(st90, "blue", max_tasks=ato.ATO_MAX_TASKS, per_kind=ato.ATO_PER_KIND)
    nat90 = {pilots.nation(st90["units"][g["performer"]]) for t in ts90 for g in t["package"] if g["group"] == "sead"}
    solo = all(not any(g["group"] == "kill" for g in t["package"]) for t in ts90
               if any(g["group"] == "sead" and pilots.nation(st90["units"][g["performer"]]) != "us" for g in t["package"]))
    check(nat90 & {"frg", "uk"} and solo, f"с 1990 SEAD своими силами - Tornado ECR (ФРГ) и ALARM (RAF), без пары добивания: {sorted(nat90)}")
    st["date"] = "1979-06-01"
    ts79, _w = planner.plan_side(st, "blue", max_tasks=ato.ATO_MAX_TASKS, per_kind=ato.ATO_PER_KIND)
    check(not any(t["kind"] in ("strike_bai", "strike_fofa") for t in ts79), "в 1979 году BAI (с 1980) и FOFA (с 1983) нет")


def payload_section(tmp: Path) -> None:
    """Подвески по задачам (payloads.json из DCS Retribution) и по году кампании (weapons.py)."""
    from redfront import weapons
    print("\n== Подвески по задачам и по году ==")
    import dcs.planes as _P
    sub = weapons.substitute(_P.F_16C_50, 3, "AIM-120C AMRAAM - Active Radar AAM", 1985)
    check(sub and "AIM-9" in sub["name"], f"замена по роли на год: AIM-120C у F-16C в 1985 -> {sub and sub['name']}")
    check(weapons.year_of("AIM-120C AMRAAM - Active Radar AAM") == 1996 and weapons.year_of("Mk-82 - 500lb GP Bomb LD") == 0
          and weapons.year_of("AGM-65G - Maverick G") == 1989, "годы оружия: AIM-120C 1996, AGM-65G 1989, Mk-82 - без ограничения")
    st = model.new_campaign("pl", sector="sector_germany.json", oob="oob_germany_1985.json", seed=7, player_side="blue")
    planner.plan(st)
    man = build.build(st, tmp / "pl.miz", task_no=1)
    lines = [ln for ln in man["package_lines"] if "подвеска" in ln]
    check(any("Retribution" in ln or "STRIKE" in ln or "CAS" in ln for ln in lines),
          f"подвеска по виду задачи из payloads.json: {lines[0].split('подвеска')[-1][:80]}")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "pl.miz"))
    bad = [weapons.name_of(d["CLSID"]) for c in m.coalition["blue"].countries.values() for g in c.plane_group
           for u in g.units for d in u.pylons.values() if weapons.year_of(weapons.name_of(d["CLSID"])) > 1985]
    check(not bad, f"в .miz 1985 года нет оружия новее 1985 (было бы: {bad[:3]})")
    fg = m.flight_group_inflight(m.country("USA"), "f4", _P.F_4E_45MC, m.terrain.airports["Spangdahlem"].position, 1000,
                                 group_size=2)
    build._apply_loadout(fg, _P.F_4E_45MC, "F_4E_45MC", ["sead"], {"date": "1989-06-01"})
    arm = [d["CLSID"] for d in fg.units[1].pylons.values() if d["CLSID"] in (weapons.HARM,) or "AGM_45" in d["CLSID"]]
    fg2 = m.flight_group_inflight(m.country("USA"), "f4b", _P.F_4E_45MC, m.terrain.airports["Spangdahlem"].position, 1000,
                                  group_size=1)
    build._apply_loadout(fg2, _P.F_4E_45MC, "F_4E_45MC", ["sead"], {"date": "1983-06-01"})
    old_ = [d["CLSID"] for d in fg2.units[0].pylons.values() if "AGM_45" in d["CLSID"]]
    check(arm and all(c == weapons.HARM for c in arm) and old_,
          f"F-4E (вместо F-4G) в SEAD: с 1985 - HARM на пилонах Shrike ({len(arm)} шт.), в 1983 - Shrike ({len(old_)})")
    from redfront import command
    opts = command.loadouts("F_16C_50")
    check(any(o.startswith("rt:") for o in opts), f"в редакторе плана - подвески Retribution на выбор ({len(opts)} у F-16C)")


def mixed_section(tmp: Path) -> None:
    """Смешанный пакет: состав групп по доктрине, точка и время сбора, порядок выхода на объекты; дебриф самолётов ИИ."""
    print("\n== Смешанный пакет: сбор, порядок, состав ==")
    st = model.new_campaign("mix", oob=BASE_OOB, sector=BASE_SECTOR)
    tk = planner.plan(st)
    pk = {g["group"]: g for g in tk["package"]}
    check(pk["strike"]["size"] == 4 and pk["sead"]["size"] == 2,
          f"состав по доктрине ОВД: ударная по колонне - звено ({pk['strike']['size']}), подавление ПВО - пары")
    check(pk["strike"].get("rv") and pk["strike"].get("rv") == pk["recon"].get("rv") and not pk["sead"].get("rv"),
          "точка сбора: ударная и доразведка собираются в одной точке, подавление ПВО идёт на рубеж напрямую")
    man = build.build(st, tmp / "mix.miz")
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "mix.miz"))
    pg = {g.name.split(" ")[1]: g for g in plane_groups(m)}
    rv = next(p for p in pg["recon"].points if p.name == "Сбор")
    t_ = build.timeline(model.doctrine(st, "red")["tasks"]["strike_column_march"], st, tk["package"], "strike")
    check(rv.ETA == t_["recon"]["rv_s"] and rv.ETA_locked and "Сбор" in [p.name for p in pg["strike"].points],
          f"группа ИИ приходит в точку сбора ко времени (ETA {rv.ETA // 60} мин), у игрока точка сбора в маршруте")
    order = t_["sead"]["objective_s"] < t_["recon"]["objective_s"] < t_["strike"]["objective_s"]
    desc = m.description_text()
    check(order and "Порядок действий группы" in desc and "Выход на объекты" in desc,
          "порядок: подавление ПВО -> доразведка -> удар; в брифинге - сбор и порядок выхода (T-минуты)")
    from redfront import airwar
    e_ = {"side": "red", "task": tk}
    check(airwar.sead_factor(st, e_, tk["threats"]) in (airwar.SEAD_KNOWN, airwar.SEAD_SEARCH)
          and airwar.sead_factor(st, {"side": "red", "task": {**tk, "package": tk["package"][:1]}}, tk["threats"]) == 1.0,
          "вне миссии: подавление ПВО снижает потери от ЗРК коридора (по свежим данным - сильнее)")
    # удар по аэродрому (ОВД): расчистка воздуха и демонстративная группа
    sg = model.new_campaign("mixg", sector="sector_germany.json", oob="oob_germany_1987.json", seed=7)
    sim.end_day(sg)
    planner.plan(sg)
    af = next((t for t in sg["tasks"] if any(g["group"] == "feint" for g in t["package"])), None)
    if af:
        pk2 = {g["group"]: g for g in af["package"]}
        tdef2 = model.doctrine(sg, "red")["tasks"][af["kind"]]
        t2 = build.timeline(tdef2, sg, af["package"], "strike")
        fp = pk2["feint"]["route"][0]
        hot = [u["name"] for u in sg["units"].values() if u["side"] == "blue" and model.category(u) == "sam"
               and u["state"] != "destroyed" and model.dist_km(fp, model.unit_pos(sg, u)) <= planner.threat_radius_km(u)]
        check("sweep" in pk2 and t2["sweep"]["objective_s"] < t2["sead"]["objective_s"] < t2["strike"]["objective_s"]
              and t2["feint"]["objective_s"] < t2["strike"]["objective_s"] and pk2["feint"]["alt_m"] >= 3000,
              f"удар по аэродрому: расчистка воздуха и демонстративная группа (средняя высота, другим направлением) - до подавления ПВО и удара; точка демонстрации в зонах ЗРК: {hot or 'нет'}")
    else:
        check(False, "в плане ОВД нет удара по аэродрому с демонстративной группой")
    # дебриф: самолёт ИИ разбился без попадания (уходил от ПВО) - потеря; исключение - только вертолёты с посадкой в поле
    ai = next(n for fl in man["flights"] if fl["group"] == "sead" for n in fl["units"])
    perf = st["units"][next(fl["performer"] for fl in man["flights"] if fl["group"] == "sead")]
    c0 = perf["count"]
    data = {"campaign": st["campaign_id"], "sortie": man["sortie"], "dead": [ai], "ejected": [], "landed": [], "takeoff": [],
            "hit": [], "mission_ended": True}
    lines = debrief.apply(st, data)
    check(perf["count"] == c0 - 1 and not any("без огня противника" in ln for ln in lines),
          "дебриф: самолёт ИИ, разбившийся без попадания, - потеря (исключение только для вертолётов при посадке в поле)")


def heli_pkg_section(tmp: Path) -> None:
    """Вертолёты: прикрытие десанта и поиска-спасения, звено ударных, разведчик-наводчик НАТО, совместный удар, ночь."""
    from redfront import ato
    print("\n== Вертолёты: прикрытие, состав, совместный удар, ночь ==")
    st = model.new_campaign("heli", sector="sector_germany.json", oob="oob_germany.json", seed=7)
    sim.end_day(st)
    planner.plan(st)
    aa = next(t for t in st["tasks"] if t["kind"] == "air_assault")
    esc = next((g for g in aa["package"] if g["group"] == "escort"), None)
    check(esc and st["units"][esc["performer"]]["type"] == "Mi_24P" and esc["lead_min"] == 2 and esc["size"] >= 2,
          f"десант: прикрытие Ми-24 ({esc and esc['size']}) выходит на площадку за 2 мин до посадки Ми-8")
    man = build.build(st, tmp / "heli_aa.miz", task_no=st["tasks"].index(aa) + 1)
    m = dcs.Mission(Germany())
    m.load_file(str(tmp / "heli_aa.miz"))
    eg = next(g for c in m.coalition["red"].countries.values() for g in c.helicopter_group if " escort " in g.name)
    zt = [t for p in eg.points for t in p.tasks if getattr(t, "id", None) == "EngageTargetsInZone"]
    check([p.name for p in eg.points[1:-1]] == ["Площадка (прикрытие)"] and zt,
          "в .miz: прикрытие обрабатывает район площадки и держит его, пока транспортные на земле")
    cs = [t for t in st["tasks"] if t["kind"] == "csar"]
    check(not cs or any(g["group"] == "escort" for t in cs for g in t["package"]), "поиск и спасение - с парой прикрытия")
    jt = [t for t in st["tasks"] if any(g.get("jaat_kind") for g in t["package"])]
    check(jt and all(g["lead_min"] == 2 and g["size"] == 4 for t in jt for g in t["package"] if g.get("jaat_kind"))
          and not any(t["kind"] == "cas_helo" and t["target"] == jt[0]["target"] for t in st["tasks"]),
          f"совместный удар: звено Ми-24 сведено в пакет Су-25 по той же цели, выходит за 2 мин до самолётов ({len(jt)})")
    sb = model.new_campaign("helib", sector="sector_germany.json", oob="oob_germany.json", seed=7, player_side="blue")
    ah = next(u for u in sb["units"].values() if u.get("type") == "AH_64A")
    tgt = min((u for u in sb["units"].values() if u["side"] == "red" and model.category(u) == "ground"),
              key=lambda u: model.dist_km(sb["airbases"][ah["base"]], model.unit_pos(sb, u)))
    td = model.doctrine(sb, "blue")["tasks"]["cas_helo"]
    tp = model.unit_pos(sb, tgt)
    gs, _w = planner.package(sb, td, ah, tgt, tp, planner.ip_point(sb["airbases"][ah["base"]], tp, td["ip_offset_km"]), [])
    check([(g["group"], g["size"]) for g in gs] == [("strike", 4), ("scout", 2)] and "SA342" in sb["units"][gs[1]["performer"]]["type"],
          "НАТО: AH-64A ротой (4) с парой разведчиков-наводчиков SA342 впереди (3 мин)")
    night = ato.night_capable(sb, {"package": gs[:1]})
    mi24 = next(u for u in st["units"].values() if u.get("type") == "Mi_24P")
    check(night and "cas_helo" in ato.NIGHT_KINDS and not ato.night_capable(st, {"package": [{"performer": mi24["id"]}]}),
          "ночью из ударных вертолётов летает только AH-64A, Ми-24П - днём")


SECTIONS = [core_section, patriot_close_section, front_section, random_section, logistics_section, menu_section,
            theatre_section, air_section, package_section, roads_section, column_road_section, mapobj_section,
            gui_section, germany_section, air_defence_section, support_air_section, helo_section, ato_section, presets_section,
            supply_section, assault_section, csar_section, convoy_section, advance_section, qra_section, ctld_section,
            command_section, farp_section, evac_section, fitness_section, fog_section, ground_fog_section, recon_section, explain_section, crew_section, reinforce_section, nato_section, payload_section, mixed_section, heli_pkg_section]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="redfront_"))
    for section in SECTIONS:
        section(tmp)

    print(f"\nФайлы теста: {tmp}")
    print("ИТОГ: " + ("всё прошло" if not FAILS else f"{len(FAILS)} провал(ов)"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

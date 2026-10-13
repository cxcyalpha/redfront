"""Дебриф: файл, записанный хуком в миссии -> изменения в модели кампании.

Потери наземной части = сумма весов уничтоженных развёрнутых машин (см. materialize.py, правило сохранения).
Продвижение колонны = проекция головы уцелевшей части колонны на маршрут, если она ушла дальше, чем было.
"""
from __future__ import annotations

import json
from pathlib import Path

from dcs.mapping import Point
from dcs.terrain.germany import Germany

from . import model, roads

FULL_DAMAGE = {"depot": 0.5, "airfield": 0.3, "bridge": 0.01, "factory": 0.5}   # ОЦЕНКА: доля разрушенных объектов карты = полное повреждение


def find_file(state: dict, home: Path | None = None) -> Path:
    """Файл дебрифа последнего собранного вылета: <Saved Games>\\DCS*\\redfront\\debrief_<кампания>_<вылет>.json.
    Папка Saved Games может называться DCS, DCS.openbeta и т.п. - проверяются все."""
    man = state.get("manifest")
    if not man:
        raise RuntimeError("в кампании нет собранного вылета (manifest): сначала build")
    name = f"debrief_{state['campaign_id']}_{man['sortie']}.json"
    sg = (home or Path.home()) / "Saved Games"
    found = sorted(sg.glob(f"DCS*/redfront/{name}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not found:
        raise FileNotFoundError(f"не найден {name} в {sg}\\DCS*\\redfront - вылет не летали, или io/lfs не разблокированы "
                                f"в MissionScripting.lua; можно указать файл явно")
    return found[0]


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply(state: dict, data: dict) -> list[str]:
    man = state.get("manifest")
    if not man:
        raise RuntimeError("в кампании нет собранного вылета (manifest)")
    if data.get("campaign") != state["campaign_id"] or int(data.get("sortie", -1)) != man["sortie"]:
        raise RuntimeError(f"файл от другого вылета: campaign={data.get('campaign')} sortie={data.get('sortie')}, "
                           f"ожидался {state['campaign_id']} / {man['sortie']}")
    if man.get("applied"):
        raise RuntimeError(f"дебриф вылета {man['sortie']} уже применён - повторно потери не списываются")
    lost = set(data.get("dead", [])) | set(data.get("ejected", []))
    lines = []

    # ---- дороги, найденные миссией при перекладке колонны (column_road.lua): модель их запоминает ----
    for name, msg in (data.get("column_log") or {}).items():
        lines.append(f"Колонна {name}: {msg}.")
    if data.get("roads"):
        lines += roads.apply(state, roads.from_raw({"paths": data["roads"]}), note=False)
    # место боя, выбранное миссией по местности (battle_site.lua): следующие вылеты ставят бой туда же
    for key, (dx, dy) in (data.get("sites") or {}).items():
        state.setdefault("battle_sites", {})[key] = {"x": dx, "y": dy}
    for key, msg in (data.get("site_log") or {}).items():
        lines.append(f"Бой {key}: {msg}.")

    # ---- объекты тыла: разрушенные объекты карты в их районе -> повреждение (ОЦЕНКА порогов: FULL_DAMAGE) ----
    for oid, (n, dead_n) in (data.get("targets") or {}).items():
        o = state["units"].get(oid)
        if not o or n <= 0 or dead_n <= 0:
            if o and n <= 0 and oid in (man.get("objects") or []) and not o.get("_no_scenery_noted"):
                o["_no_scenery_noted"] = True
                lines.append(f"{o['name']}: объектов карты в районе не найдено - цель не засчитывается (проверить координаты).")
            continue
        before = o.get("damage", 0.0)
        gain = 1.0 if o["role"] == "bridge" else min(1.0, (dead_n / n) / FULL_DAMAGE[o["role"]])
        o["damage"] = min(1.0, before + gain)
        lines.append(f"{o['name']}: разрушено объектов {dead_n} из {n}, повреждение {before:.0%} -> {o['damage']:.0%}"
                     + ((" - объезд, марш и подвоз по этой связи медленнее." if o.get("minor", o.get("found")) else " - движение по мосту закрыто.")
                        if o["role"] == "bridge" and o["damage"] >= 1.0 else "."))

    # ---- наземные части ----
    terrain = Germany()
    for g in man["ground"]:
        u = state["units"][g["unit"]]
        before = model.strength(u)
        for v in g["vehicles"]:
            if v["name"] in lost:
                cap = next(c["count"] for c in u["composition"] if c["type"] == v["type"])
                u["lost"][v["type"]] = min(cap, u["lost"].get(v["type"], 0.0) + v["weight"])
        after = model.strength(u)
        n_dead = sum(1 for v in g["vehicles"] if v["name"] in lost)
        if n_dead:
            lines.append(f"{u['name']}: уничтожено {n_dead} из {len(g['vehicles'])} развёрнутых машин; "
                         f"боеспособность {before:.0%} -> {after:.0%}.")
        if g["kind"] == "column" and "route" in u:   # приданная группа (ПВО колонны) своего маршрута не имеет - идёт с частью
            pos = data.get("positions") or {}
            alive = [pos[v["name"]] for v in g["vehicles"] if v["name"] in pos and v["name"] not in lost]
            if alive:
                pts = model.route_points(state, u)
                kms = []
                for x, z in alive:
                    ll = Point(x, z, terrain).latlng()
                    kms.append(model.project_km(pts, {"lat": ll.lat, "lon": ll.lng}))
                head = max(kms)
                adv = max(0.0, head - u["progress_km"])
                # средняя скорость марша в DCS - для прогноза положения колонны (рубеж группы подавления ПВО).
                # Не замеряем, если колонну в этой миссии перекладывали на дорогу (сдвиг головы - не марш) или миссия короче 5 мин.
                t_s = float(data.get("time") or 0)
                if t_s >= 300 and g["unit"] not in (data.get("column_log") or {}):
                    u["observed_kmh"] = round(adv / (t_s / 3600.0), 1)
                    lines.append(f"{u['name']}: средняя скорость марша в миссии {u['observed_kmh']:.1f} км/ч (приказ {u.get('march_kmh', 0)}).")
                if head > u["progress_km"] + 0.2:
                    lines.append(f"{u['name']}: за время вылета продвинулся на {adv:.1f} км.")
                    u["progress_km"] = head

    # ---- своё звено ----
    flights = man.get("flights") or [{**man["flight"], "group": "strike"}]   # вылет, собранный до тактической группы: одно звено
    for fl in flights:                           # все звенья тактической группы, не только звено игрока
        perf = state["units"][fl["performer"]]
        lost_ac = [n for n in fl["units"] if n in lost]
        if lost_ac:
            perf["count"] = max(0, perf["count"] - len(lost_ac))
            lines.append(f"{perf['name']} ({fl['group']}): потеряно {len(lost_ac)} ЛА; в строю {perf['count']}.")
            if fl.get("ato") and state.get("ato"):   # вылет плана полётов: сбитые борта перевозки груз не довозят
                lost_by = state["ato"].setdefault("lost", {})
                lost_by[fl["ato"]] = lost_by.get(fl["ato"], 0) + len(lost_ac)
    from . import convoys                       # колонны снабжения: сожжённые машины - недовезённые тонны
    for cv in man.get("convoys") or []:
        dead_w = sum(v["weight"] for v in cv["vehicles"] if v["name"] in lost)
        if dead_w > 0:
            t = dead_w * convoys.TRUCK_T
            convoys.add_loss(state, cv["side"], cv["link"], t)
            n = sum(1 for v in cv["vehicles"] if v["name"] in lost)
            lines.append(f"Колонна снабжения {cv['link'].replace('>', ' - ')}: уничтожено {n} из {len(cv['vehicles'])} машин "
                         f"(~{dead_w:.1f} грузовиков потока), недовоз ~{t:.0f} т.")
    for qid in sorted(data.get("qra") or {}):    # дежурные пары, поднятые в миссии (qra.lua)
        e = next((x for x in (state.get("ato") or {}).get("entries", []) if x["id"] == qid), None)
        if e:
            lines.append(f"{e['title']}: пара поднята по тревоге на {int(data['qra'][qid]) // 60}-й минуте.")
    from . import csar                          # экипажи сбитых и спасения в миссии (csar.lua)
    lines += csar.apply_debrief(state, man, data, lost)
    for aid, (landed_n, total) in (data.get("assault") or {}).items():   # десант: сколько бортов село (assault.lua)
        if state.get("ato"):
            state["ato"].setdefault("assault", {})[aid] = [int(landed_n), int(total)]
        lines.append(f"Десант: на площадку село {landed_n} из {total} бортов" + (" - рота высажена." if landed_n else "."))
    if not data.get("mission_ended"):
        lines.append("Внимание: миссия не была завершена штатно - применён последний сохранённый срез.")
    if not lines:
        lines.append("Изменений нет.")
    for ln in lines:
        model.note(state, ln)
    state["manifest"]["applied"] = True
    if man.get("end_s") is not None:            # часы кампании: следующий вылет игрока - после этой миссии (ato.py)
        state["clock_s"] = max(state.get("clock_s") or 0, man["end_s"])
        a = state.get("ato")
        if man.get("ato_id") and a and man["ato_id"] not in a["done"]:
            a["done"].append(man["ato_id"])
        if a:                                    # группы ИИ этой миссии - слетаны в DCS: итог вне миссии им не считается
            a["played"] = sorted(set(a.get("played", [])) | {fl["ato"] for fl in flights if fl.get("ato")})
        from . import sim                        # окно миссии: бой и марш прошли в DCS - модели только события плана полётов
        ev = sim.advance(state, man["end_s"], ground=False)
        for ln in ev:
            model.note(state, ln)
        lines += ev
    return lines

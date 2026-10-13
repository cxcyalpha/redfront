"""Командная строка.

  python -m redfront new  <state.json> [--side red|blue] [--oob FILE] [--sector FILE] [--doctrine SIDE=PACKAGE ...]
                                       [--name NAME] [--date YYYY-MM-DD]
  python -m redfront status <state.json>
  python -m redfront plan   <state.json>
  python -m redfront build  <state.json> <out.miz> [--task N] [--fly GROUP] [--density 1.0] [--ai]
  python -m redfront debrief <state.json> <debrief_*.json>
  python -m redfront end-day <state.json>
  python -m redfront roads-probe <out.miz> [--sector FILE] [--oob FILE]   служебная миссия: дороги у DCS (один раз на сектор)
  python -m redfront roads-apply <state.json> <roads_*.json>             положить дороги в кампанию

--oob и --sector: свой файл или имя файла из redfront/data. Пакеты доктрины - redfront/data/doctrine/<имя>.json,
по умолчанию red=wp, blue=generic.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build as build_mod
from . import debrief, mapobj, model, ops, planner, roads, sim


def status(state: dict) -> str:
    out = [f"Кампания '{state['name']}' ({state['campaign_id']}), день {state['day']}, вылетов {state['sortie']}",
           f"Игрок за: {state['player_side']}; доктрина: " + ", ".join(f"{s}={p}" for s, p in state["doctrine"].items())]
    sc = state.get("scenario") or {}
    if sc.get("variant"):
        out.append(f"Сценарий: {sc.get('title') or sc['variant']} (вариант {sc['variant']}, seed {sc.get('seed')}"
                   + ("" if state["settings"].get("randomness") else ", без случайности") + ")")
    for u in state["units"].values():
        if model.category(u) in ("depot", "bridge", "airfield", "factory"):
            continue
        if model.category(u) in ("air", "heli"):
            b = state["airbases"].get(u["base"], {})
            out.append(f"  [{u['side']}] {u['name']} ({u['role']}, {u['type']}): {u['count']} ЛА, {b.get('name', u['base'])}")
        elif u.get("attached_to"):
            out.append(f"  [{u['side']}]   {u['name']} (при части): боеспособность {model.strength(u):.0%}")
        else:
            st_ = {"march": "марш", "battle": "бой", "defend": "оборона", "halted": "небоеспособна", "destroyed": "уничтожена",
                   "deployed": "на позиции", "refit": "восстановление в тылу",
                   "pending": f"резерв, прибудет на день {u.get('arrives_day')}"}.get(u["state"], u["state"])
            if u.get("order") in ("attack", "hold", "withdraw") and u["state"] == "march":
                st_ += {"attack": " (наступление)", "hold": " (на рубеж)", "withdraw": " (отход)"}[u["order"]]
            extra = ""
            if "route" in u and len(u["route"]) > 1:
                extra = f", {u['progress_km']:.0f}/{model.route_length_km(model.route_points(state, u)):.0f} км ({' - '.join(u['route'])})"
            elif "route" in u:
                extra = f", район {u['route'][0]}"
            if u["state"] == "battle":
                extra += "; против: " + ", ".join(state["units"][f]["name"] for f in u.get("engaged", []))
            if u.get("supply", 1.0) < 1.0:
                extra += "; БЕЗ СНАБЖЕНИЯ"
            out.append(f"  [{u['side']}] {u['name']}: {st_}, боеспособность {model.strength(u):.0%}{extra}")
    if ops.enabled(state):
        for side, nm in (("red", "красные"), ("blue", "синие")):
            out.append(f"Пункты ({nm}): " + ", ".join(p for p in state["places"] if ops.owner(state, p) == side))
        out.append("Линия фронта: " + ", ".join(f"{a}-{b}" for a, b in ops.front_links(state)))
    tgt = [u for u in state["units"].values() if model.category(u) in ("depot", "bridge", "airfield", "factory")
           and (u.get("damage", 0) > 0 or u["state"] != "active")]
    if tgt:
        out.append("Тыл: " + "; ".join(f"{u['name']} - " + ({"lost": "потерян", "closed": "закрыт"}.get(u["state"]) or
                                                          f"повреждение {u['damage']:.0%}") for u in tgt))
    unchecked = [u for u in state["units"].values() if u.get("role") in ("depot", "bridge", "factory") and not u.get("pos_checked")]
    if unchecked:
        out.append("Координаты - ОЦЕНКИ, проверить в редакторе (set-pos): " + ", ".join(
            f"{u['id']} ({u['pos']['lat']:.4f}, {u['pos']['lon']:.4f})" for u in unchecked))
    tk = state.get("task")
    out.append(f"Задача: {tk['title']} ({tk['distance_km']:.0f} км, угрозы: {', '.join(tk['threats']) or 'нет'})" if tk
               else "Задача: нет (plan)" + (f" ({state['task_reason']})" if state.get("task_reason") else ""))
    if state["log"]:
        out.append("Журнал (последнее):")
        out += [f"  {ln}" for ln in state["log"][-8:]]
    return "\n".join(out)


def parse_deg(text: str) -> float:
    """53.3701 | 53°22'12" | 53 22 12 | N53°22'12.5" -> градусы."""
    import re
    t = text.strip().upper()
    neg = t.startswith(("S", "W")) or t.endswith(("S", "W")) or t.startswith("-")
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", t)]
    if not nums or len(nums) > 3:
        raise SystemExit(f"не понял координату: {text}")
    v = sum(n / 60 ** i for i, n in enumerate(nums))
    return -v if neg else v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="redfront")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("state"); p.add_argument("--name", default="Гамбург"); p.add_argument("--date", default="2026-05-15")
    p.add_argument("--side", choices=model.SIDES, default="red", help="за какую сторону играет игрок")
    p.add_argument("--oob", default="oob_hamburg.json", help="состав сил")
    p.add_argument("--sector", default="sector_hamburg.json", help="сектор (карта)")
    p.add_argument("--doctrine", action="append", default=[], metavar="SIDE=PACKAGE", help="пакет доктрины стороны, напр. blue=generic")
    p.add_argument("--roads", help="файл дорог от roads-probe (roads_<сектор>.json)")
    p.add_argument("--seed", type=int, help="зерно случайности (повторить кампанию)")
    p.add_argument("--variant", help="вариант сценария из состава сил (по умолчанию - случайный)")
    p.add_argument("--no-random", action="store_true", help="без случайности: базовый вариант, бой и решения по формулам")
    p = sp.add_parser("roads-probe"); p.add_argument("out")
    p.add_argument("--sector", default="sector_hamburg.json"); p.add_argument("--oob", default="oob_hamburg.json")
    p = sp.add_parser("roads-apply"); p.add_argument("state"); p.add_argument("file")
    for c in ("status", "plan", "end-day"):
        sp.add_parser(c).add_argument("state")
    sp.add_parser("menu", help="меню: новая кампания, план, сборка, дебриф, следующий день").add_argument("state", nargs="?")
    p = sp.add_parser("gui", help="окно кампании в браузере (карта, план, сборка, дебриф)")
    p.add_argument("--port", type=int, default=8765); p.add_argument("--no-browser", action="store_true")
    p = sp.add_parser("build"); p.add_argument("state"); p.add_argument("out"); p.add_argument("--density", type=float, default=1.0)
    p.add_argument("--ai", action="store_true", help="звено без игрока (проверочный прогон)")
    p.add_argument("--fly", default="strike", help="в какой группе пакета летит игрок: strike (по умолчанию), sead, recon")
    p.add_argument("--task", type=int, help="номер задачи из плана дня (plan); по умолчанию - первая")
    p = sp.add_parser("map-probe", help="служебная миссия: найти на карте DCS объекты мостов и складов сектора")
    p.add_argument("out"); p.add_argument("--sector", default="sector_hamburg.json")
    p = sp.add_parser("map-apply", help="применить файл зонда карты к кампании или к файлу сектора")
    p.add_argument("target", help="кампания (camp.json) или сектор (sector_hamburg.json - для всех новых кампаний)")
    p.add_argument("file", help="map_<сектор>.json из Saved Games\\DCS\\redfront")
    p = sp.add_parser("map-import", help="цели из зон 'Assign as...' миссии: ROLE = depot|bridge, VALUE = id объекта")
    p.add_argument("target", help="кампания (camp.json) или сектор (sector_hamburg.json)"); p.add_argument("miz")
    p = sp.add_parser("set-damage", help="вручную задать повреждение объекта тыла (0..1), если дебриф его не засчитал")
    p.add_argument("state"); p.add_argument("id"); p.add_argument("damage", type=float)
    p = sp.add_parser("set-pos", help="поправить координаты объекта тыла (мост, склад, аэродром) по редактору DCS")
    p.add_argument("state"); p.add_argument("id", help="id объекта, напр. br_lauenburg (список - status)")
    p.add_argument("lat", help="широта: 53.3701 или 53°22'12\"N"); p.add_argument("lon", help="долгота: 10.5523 или 10°33'08\"E")
    p = sp.add_parser("debrief"); p.add_argument("state")
    p.add_argument("file", nargs="?", help="файл дебрифа; без него ищется сам в Saved Games\\DCS*\\redfront")
    a = ap.parse_args(argv)
    if a.cmd == "roads-probe":
        r = roads.probe(Path(a.out), a.sector, a.oob)
        print(f"Служебная миссия: {r['file']}\nСектор '{r['sector']}', участков: {len(r['pairs'])} ({', '.join(r['pairs'])}).\n"
              f"Запустите её в DCS, дождитесь сообщения 'дороги записаны', выйдите. Файл: "
              f"Saved Games\\DCS\\redfront\\roads_{r['sector']}.json")
        return 0
    if a.cmd == "map-probe":
        r = mapobj.probe(Path(a.out), a.sector)
        print(f"Служебная миссия: {r['file']}\nСектор '{r['sector']}': весь сектор, ячеек {r['tiles']} (~{r['area_km2']} км2).\n"
              f"Запустите её в DCS, дождитесь сообщения 'объекты карты записаны', выйдите. Файл: "
              f"Saved Games\\DCS\\redfront\\map_{r['sector']}.json")
        return 0
    if a.cmd in ("map-apply", "map-import"):
        tp = Path(a.target)
        if not tp.exists() and (model.DATA / tp.name).exists():
            tp = model.DATA / tp.name
        data = json.loads(tp.read_text(encoding="utf-8"))
        if "units" in data:
            data = model.load(tp)
        if a.cmd == "map-import":
            for ln in mapobj.import_miz(data, Path(a.miz)):
                print(ln)
        else:
            pr = mapobj.load(Path(a.file))
            print("Зонд карты: " + mapobj.summary(pr))
            for ln in mapobj.apply(data, pr):
                print(ln)
            for pid, err in pr["errors"].items():
                print(f"ошибка зонда {pid}: {err}")
            print("Склады - типы объектов карты рядом с пунктом (если склад не найден - дополнить DEPOT_KEYS):")
            for ln in mapobj.depot_report(pr):
                print(f"  {ln}")
        if "units" in data:
            model.save(data, tp)
        else:
            tp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Записано: {tp}")
        return 0
    if a.cmd == "gui":
        from . import gui
        return gui.serve(a.port, open_browser=not a.no_browser)
    if a.cmd == "menu":
        from . import menu
        return menu.run(Path(a.state) if a.state else None)
    path = Path(a.state)

    if a.cmd == "new":
        pk = dict(kv.split("=", 1) for kv in a.doctrine)
        st = model.new_campaign(a.name, a.date, sector=a.sector, oob=a.oob, player_side=a.side, packages=pk,
                                seed=a.seed, variant=a.variant, randomness=not a.no_random)
        if a.roads:
            for ln in roads.apply(st, roads.load(Path(a.roads))):
                print(ln)
        model.save(st, path)
        print(status(st))
        return 0
    st = model.load(path)
    if a.cmd == "set-damage":
        o = st["units"].get(a.id)
        if not o or o.get("role") not in ("depot", "bridge", "airfield", "factory"):
            print(f"нет объекта тыла {a.id}")
            return 1
        o["damage"] = max(0.0, min(1.0, a.damage))
        model.note(st, f"{o['name']}: повреждение задано вручную {o['damage']:.0%}.")
        model.save(st, path)
        print(f"{o['name']}: повреждение {o['damage']:.0%}")
        return 0
    if a.cmd == "set-pos":
        o = st["units"].get(a.id)
        if not o or o.get("role") not in ("depot", "bridge", "airfield", "factory"):
            ids = [u["id"] for u in st["units"].values() if u.get("role") in ("depot", "bridge", "airfield", "factory")]
            print(f"нет объекта тыла {a.id}; есть: {', '.join(ids)}")
            return 1
        old = dict(o["pos"])
        o["pos"] = {"lat": parse_deg(a.lat), "lon": parse_deg(a.lon)}
        o["pos_checked"] = True
        st["tasks"] = []                         # маршруты плана дня посчитаны по старой точке
        model.save(st, path)
        print(f"{o['name']}: {old['lat']:.5f}, {old['lon']:.5f} -> {o['pos']['lat']:.5f}, {o['pos']['lon']:.5f} "
              f"(сдвиг {model.dist_km(old, o['pos']) * 1000:.0f} м). План дня пересобрать: plan, build.")
        return 0
    if a.cmd == "status":
        print(status(st))
        return 0
    if a.cmd == "plan":
        tk = planner.plan(st)
        if not tk:
            print(f"Задач нет: {st['task_reason']}")
        else:
            print(f"План дня {st['day']} (build --task N, по умолчанию 1):")
            for i, t in enumerate(st["tasks"], 1):
                thr = ", ".join(st["units"][x]["name"] for x in t["threats"]) or "нет"
                print(f"{i}. {t['title']} - {t['distance_km']:.0f} км от {st['airbases'][t['base']]['name']}; ПВО: {thr}")
                for g in t["package"]:
                    print(f"     {g['group']:7s} {g['title']}: {g['size']} ЛА от {st['units'][g['performer']]['name']}")
                if t.get("package_notes"):
                    print(f"     замечания: {t['package_notes']}")
    elif a.cmd == "build":
        man = build_mod.build(st, Path(a.out), a.density, player=not a.ai, fly=a.fly, task_no=a.task)
        n = sum(len(g["vehicles"]) for g in man["ground"])
        print(f"Миссия: {man['file']} (вылет {man['sortie']}, наземных юнитов {n})")
        for ln in man["package_lines"]:
            print(f"  {ln}")
    elif a.cmd == "debrief":
        f = Path(a.file) if a.file else debrief.find_file(st)
        print(f"Файл дебрифа: {f}")
        for ln in debrief.apply(st, debrief.read(f)):
            print(ln)
    elif a.cmd == "roads-apply":
        for ln in roads.apply(st, roads.load(Path(a.file))):
            print(ln)
    elif a.cmd == "end-day":
        for ln in sim.end_day(st):
            print(ln)
    model.save(st, path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:   # ошибки данных - одной строкой, без трассировки
        print(f"Ошибка: {e.args[0] if e.args else e}", file=sys.stderr)
        sys.exit(2)

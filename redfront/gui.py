"""Окно кампании в браузере: карта сектора, план дня, сборка миссии, дебриф, следующий день.

    run.bat  (или python -m redfront gui [--port 8765])

Локальный сервер на стандартной библиотеке Python (127.0.0.1, только этот компьютер) и одна страница (gui.html).
Leaflet 1.9.4 (BSD-2, web/leaflet-LICENSE.txt) лежит в пакете; подложка карты - тайлы OpenStreetMap из интернета,
без сети подложки нет, но объекты кампании и всё остальное работают.
Кампании - файлы *.json в папке проекта (рядом с run.bat).
"""
from __future__ import annotations

import json
import re
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import build as build_mod, materialize
from . import ato, command, convoys, csar, dcstypes, debrief, explain, i18n, intel, logistics, mapobj, model, ops, planner, roads, sim, symbols
from .menu import missions_dir

HTML = Path(__file__).parent / "gui.html"
WEB = Path(__file__).parent / "web"
CTYPES = {".js": "application/javascript", ".css": "text/css", ".png": "image/png", ".txt": "text/plain; charset=utf-8"}
SECTOR = "sector_hamburg.json"     # кампании без поля sector (созданы до театра всей карты)
THEATRES = [   # (id, сектор, состав сил, название)
    ("germany", "sector_germany.json", "oob_germany.json", "Вся карта: фронт от Балтики до Хофа (1989)"),
    ("hamburg", "sector_hamburg.json", "oob_hamburg.json", "Сектор Гамбург - Люнебург (полигон)"),
]


def sector_of(st: dict | None) -> str:
    return (st or {}).get("sector") or SECTOR
LOCK = threading.Lock()


def saved_games_file(name: str, home: Path | None = None) -> Path | None:
    sg = (home or Path.home()) / "Saved Games"
    found = sorted(sg.glob(f"DCS*/redfront/{name}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else None


def campaigns(root: Path) -> list[dict]:
    out = []
    for f in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(st, dict) and "campaign_id" in st and "units" in st:
            out.append({"file": f.name, "name": st.get("name"), "day": st.get("day"), "side": st.get("player_side"),
                        "ok": st.get("version") == model.STATE_VERSION})
    return out


def _ll(p: dict) -> list[float]:
    return [round(p["lat"], 5), round(p["lon"], 5)]


def view(st: dict) -> dict:
    """Состояние кампании для страницы: только то, что рисуется и показывается. Названия задач и групп - на языке
    кампании (i18n.py)."""
    units = st["units"]
    lg = i18n.lang(st)
    tr = lambda x: i18n.tr(x, lg)
    use_ops = ops.enabled(st)
    front = {tuple(sorted(l)) for l in ops.front_links(st)} if use_ops else set()
    places = [{"name": n, "pos": _ll(p), "side": ops.owner(st, n) if use_ops else p.get("side")}
              for n, p in st["places"].items()]
    links = [{"a": a, "b": b, "front": tuple(sorted((a, b))) in front, "open": logistics.link_open(st, a, b)}
             for a, b in st.get("links", [])]
    ground, objects, air = [], [], []
    for u in units.values():
        cat = model.category(u)
        if cat in ("depot", "bridge", "airfield", "factory"):
            objects.append({"id": u["id"], "name": u["name"], "role": cat, "side": u.get("side"), "pos": _ll(u["pos"]),
                            "damage": round(u.get("damage", 0.0), 2), "state": u.get("state"),
                            "checked": bool(u.get("pos_checked")) or cat == "airfield",
                            "info": explain.obj(st, u, st["player_side"]),      # что это и что даст удар (explain.py)
                            **(({"stock": round(logistics.depot_stock(u), 2), "stock_t": round(u.get("stock_t", 0)),
                                 "cut": bool(u.get("_cut"))} if u["side"] == st["player_side"] else   # свой - точно
                                {"stock": round(logistics.depot_stock(u) * 4) / 4, "stock_est": True})   # противника - по оценке, четвертями
                               if cat == "depot" and u.get("cap_t") else {})})
        elif cat in ("air", "heli"):
            b = st["airbases"].get(u["base"], {})
            air.append({"id": u["id"], "name": u["name"], "side": u["side"], "type": u["type"], "role": u["role"],
                        "count": u.get("count", 0), "count0": u.get("count0", u.get("count", 0)),
                        "available": logistics.available(st, u), "base": b.get("name", u["base"]),
                        "crews": u.get("crews"), "crews0": u.get("crews0"),
                        "rebase_to": st["airbases"].get(u.get("rebase_to") or "", {}).get("name"),
                        "livery": u.get("livery") or "", "detached": bool(u.get("parent")), "added": u.get("added")})
        elif cat in ("ground", "sam", "gci"):
            fog = intel.tracked_ground(st, u)     # наземная часть противника - только по данным разведки
            lv = intel.level(st, u["id"]) if fog else None
            if fog and (u["state"] == "pending" or lv is None):
                continue                          # не видели - на карте её нет
            if u["state"] == "pending":
                pos = st["places"][u["route"][0]] if u.get("route") else u.get("pos")
            else:
                pos = intel.known_pos(st, u)   # ЗРК противника - где его видели последний раз (туман войны)
            if not pos:
                continue
            g = {"id": u["id"], "name": u["name"], "side": u["side"], "cat": cat, "state": u["state"],
                 "order": u.get("order"), "strength": round(model.strength(u), 2), "pos": _ll(pos),
                 "supply": u.get("supply", 1.0), "supply_frac": u.get("supply_frac", 1.0 if u.get("supply", 1.0) >= 1 else 0.0),
                 "attached": bool(u.get("attached_to")),
                 "arrives": u.get("arrives_day"),
                 "engaged": [units[f]["name"] for f in u.get("engaged", []) if f in units],
                 "types": ", ".join(f"{c['type']} x{c['count']}" for c in u.get("composition", [])),
                 "abbr": symbols.abbr(u), "branch": symbols.branch(u), "echelon": symbols.echelon(u),
                 "vehicle": symbols.vehicle(u), "tier": symbols.sam_tier(u)}   # условный знак
            if fog:                               # что известно: точно - как есть; примерно и присутствие - как видели
                rec = st["intel"][u["id"]]
                g.update({"intel": lv, "intel_age_h": round(intel.age_h(st, u["id"]) or 0), "intel_src": rec.get("src", ""),
                          "unc_km": round(intel.unc_km(st, u["id"]), 1)})
                if lv != "exact":
                    g.update({"state": rec.get("state", "active"), "strength": None, "seen_strength": rec.get("strength"),
                              "engaged": [], "supply": 1.0, "supply_frac": 1.0, "order": None})
                    if lv == "presence":
                        g["types"] = ""
            if cat == "sam":
                g["threat_km"] = round(planner.threat_radius_km(u), 1)
            if intel.tracked(st, u):                 # данные разведки: на какие сутки
                rec = (st.get("intel") or {}).get(u["id"]) or {}
                g["intel_day"] = rec.get("day")
                g["stale"] = st["day"] - rec.get("day", st["day"]) >= intel.STALE_DAYS
            if cat == "gci":
                g["types"] += f" · канал {u.get('channel')}, радиус {u.get('radius_km')} км"
            if "route" in u and len(u["route"]) > 1 and u["state"] in ("march", "battle") and lv in (None, "exact"):
                pts = model.route_points(st, u)
                here, i = model.point_at_km(pts, u["progress_km"])
                g["route"] = [_ll(here)] + [_ll(q) for q in pts[i + 1:]]          # остаток маршрута
            ground.append(g)
    tasks = []
    for i, t in enumerate(st.get("tasks") or [], 1):
        base = st["airbases"].get(t["base"], {})
        tasks.append({"n": i, "ato_id": t.get("ato_id"), "title": tr(t["title"]), "km": round(t["distance_km"]), "base": base.get("name", t["base"]),
                      "tot": ato.hhmm(t["tot_s"]) if t.get("tot_s") is not None else "",
                      "time": (i18n.L(lg, f"взлёт {ato.hhmm(t['takeoff_s'])}, на объекте {ato.hhmm(t['tot_s'])}",
                                      f"takeoff {ato.hhmm(t['takeoff_s'])}, time on target {ato.hhmm(t['tot_s'])}")
                               if t.get("tot_s") is not None else ""),
                      "base_pos": _ll(base) if "lat" in base else None,
                      "ip": _ll(t["ip"]) if t.get("ip") else None,
                      "target": _ll(t["target_pos"]) if t.get("target_pos") else None,
                      "threats": [units[x]["name"] for x in t.get("threats", []) if x in units],
                      "notes": t.get("package_notes", ""),
                      "goal": explain.task(st, t),                # цель: что это и что даст удар
                      "seats": sum(int(g["size"]) for g in t.get("package", [])),   # сколько людей может лететь
                      "package": [{"group": g["group"], "title": tr(g["title"]), "size": g["size"],
                                   "performer": units[g["performer"]]["name"] if g["performer"] in units else g["performer"]}
                                  for g in t.get("package", [])]})
    sc = st.get("scenario") or {}
    man = st.get("manifest") or {}
    ent = {e["id"]: e for e in (st.get("ato") or {}).get("entries", [])}
    return {
        "name": st["name"], "day": st["day"], "sortie": st["sortie"], "side": st["player_side"],
        "date": st.get("date"), "scenario": sc.get("title") or sc.get("variant"), "seed": sc.get("seed"),
        "randomness": st["settings"].get("randomness", True),
        "budget": st["settings"].get("mission_budget", materialize.MISSION_BUDGET),
        "places": places, "links": links, "ground": ground, "objects": objects, "air": air,
        "airbases": [{"id": k, "name": b["name"], "side": b.get("side"), "pos": _ll(b), "state": b.get("state", "open"),
                      "kind": b.get("kind", "airfield"),       # farp - вертолётная площадка (farp.py)
                      "units": [u["name"] for u in units.values() if u.get("base") == k and model.category(u) in ("air", "heli")]}
                     for k, b in st["airbases"].items()],
        "tasks": tasks, "task_reason": st.get("task_reason") if not tasks else None,
        "supply_log": st.get("supply_log") or {},
        "rear": explain.rear(st),
        "supply_routes": [{"pts": [_ll(q) for q in model.route_points(st, {"route": l.split(">")})], "t": round(t),
                           "link": l.replace(">", " - "), "info": explain.route(st, st["player_side"], l, t)}
                          for l, t in convoys.link_flows(st, st["player_side"]).items()],   # свои пути подвоза (поток, т/сутки)
        "downed": [{"id": d["id"], "side": d["side"], "pos": _ll(d["pos"]), "freq": d["freq_khz"], "day": d["day"],
                    "title": csar.title(st, d)} for d in st.get("downed", [])
                   if d["side"] == st["player_side"]],    # свои сбитые экипажи (чужие - не видны)
        "ato": [dict(r, title=tr(r["title"]), status=tr(r["status"]), groups=[tr(x) for x in r["groups"]],
                     locked=command.why_locked(st, ent[r["id"]]), duty_only=command._is_duty(st, ent[r["id"]]))
                for r in ato.rows(st)],
        "lang": lg,
        "clock": ato.hhmm(st.get("clock_s") or 0) if st.get("clock_s") else None,
        "ground_time": ato.hhmm(st.get("ground_s") or 0),          # наземная обстановка - на это время (sim.advance)
        "built": {"file": man.get("file"), "sortie": man.get("sortie")} if man else None,
        "log": st["log"][-80:],
    }


def liveries(st: dict, u: dict) -> list[dict]:
    """Ливреи типа части для страны её стороны в миссии - из установленного DCS (pydcs сканирует папки DCS и
    Saved Games), все страны: миссия ставит части в CJTF, а ливрея из .miz применяется к любой стране;
    DCS не найден - пусто (ливрею можно вписать вручную - имя папки ливреи)."""
    try:
        ac = dcstypes.flying(u["type"])
        return sorted(({"id": lv.id, "name": lv.name + (f" ({', '.join(sorted(lv.countries))})" if lv.countries else "")}
                       for lv in ac.iter_liveries()), key=lambda x: x["name"])
    except Exception:                            # DCS не установлен (или pydcs не нашёл папки) - вручную
        return []


def unit_info(st: dict, uid: str) -> dict:
    from . import pilots
    u = st["units"][uid]
    roster = pilots.ensure(st, u)
    return {"id": uid, "name": u["name"], "livery": u.get("livery") or "", "liveries": liveries(st, u),
            "pilots": [{"name": pilots.title(u, p), "sorties": p.get("sorties", 0)}
                       for p in sorted(roster, key=lambda p: (-p.get("rank", 0), -p.get("sorties", 0), p["name"]))],
            "down": [pilots.title(u, d["pilot"]) for d in st.get("downed", []) if d.get("unit") == uid and d.get("pilot")],
            "lost": [{"name": pilots.title(u, p), "how": p.get("how", ""), "day": p.get("day")} for p in u.get("pilots_lost", [])]}


class App:
    def __init__(self, root: Path, home: Path | None = None):
        self.root, self.home = root, home

    def path(self, name: str) -> Path:
        name = Path(str(name)).name
        if not name.endswith(".json"):
            name += ".json"
        if not re.fullmatch(r"[\w\-. а-яА-ЯёЁ]+\.json", name):
            raise ValueError(f"недопустимое имя файла кампании: {name}")
        return self.root / name

    def presets(self, tid: str) -> list[dict]:
        """Пресеты состава сил театра: data/oob_<театр>*.json (пресеты по годам) и свои - presets/*.json в папке
        проекта (копии для правки; театр - поле theatre в файле). file - то, что передаётся в new."""
        _t, _sec, default, _title = next(t for t in THEATRES if t[0] == tid)
        out = []
        files = sorted(model.DATA.glob(f"oob_{tid}*.json"), key=lambda f: (f.name != default, f.name))
        user = sorted((self.root / "presets").glob("*.json")) if (self.root / "presets").is_dir() else []
        for f, key in [(f, f.name) for f in files] + [(f, f"presets/{f.name}") for f in user]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if key.startswith("presets/") and d.get("theatre", tid) != tid:
                continue
            title = (d.get("preset") or {}).get("title") or f.stem
            out.append({"file": key, "title": title + (" (свой)" if key.startswith("presets/") else "")
                        + (" - по умолчанию" if key == default else ""),
                        "variants": [{"name": v["name"], "title": v.get("title", v["name"])} for v in d.get("variants", [])]})
        return out

    def preset_path(self, tid: str, key: str | None) -> str | Path:
        """Файл пресета по ключу из presets() (только из списка - путь извне не принимается)."""
        _t, _sec, default, _title = next(t for t in THEATRES if t[0] == tid)
        if not key:
            return default
        if key not in {p["file"] for p in self.presets(tid)}:
            raise ValueError(f"нет пресета '{key}' у театра {tid}")
        return self.root / key if key.startswith("presets/") else key

    def info(self) -> dict:
        th = []
        for tid, sec, oob, title in THEATRES:
            ps = self.presets(tid)
            th.append({"id": tid, "title": title, "presets": ps, "variants": ps[0]["variants"] if ps else []})
        return {"campaigns": campaigns(self.root), "theatres": th, "missions_dir": str(missions_dir(self.home))}

    def load(self, req: dict) -> tuple[Path, dict]:
        p = self.path(req["file"])
        return p, model.load(p)

    def do(self, action: str, req: dict) -> dict:
        lines: list[str] = []
        if action == "new":
            p = self.path(req.get("file") or "campaign")
            if p.exists() and not req.get("overwrite"):
                raise ValueError(f"{p.name} уже есть - другое имя или отметьте 'перезаписать'")
            seed = req.get("seed")
            _tid, sec_f, oob_f, _t = next((t for t in THEATRES if t[0] == req.get("theatre")), THEATRES[0])
            oob_f = self.preset_path(_tid, req.get("preset"))
            st = model.new_campaign(p.stem, player_side=req.get("side", "red"), sector=sec_f, oob=oob_f,
                                    seed=int(seed) if str(seed or "").strip() else None,
                                    variant=req.get("variant") or None, randomness=not req.get("norandom"))
            sid = roads.sector_id(sec_f)
            rf = saved_games_file(f"roads_{sid}.json", self.home) or roads.bundled(sid)   # свой зонд, иначе - из поставки
            if rf:
                roads.apply(st, roads.load(rf))
                lines.append(f"Дороги: {rf}")
            mf = saved_games_file(f"map_{sid}.json", self.home)
            if mf:
                try:
                    pr = mapobj.load(mf)
                    res = [f"Зонд карты {mf.name}: " + mapobj.summary(pr)] + mapobj.apply(st, pr)
                except Exception as e:                       # noqa: BLE001 - кампания создаётся и без зонда
                    traceback.print_exc()
                    res = [f"Зонд карты {mf.name} не применён ({type(e).__name__}: {e}) - цели по оценке."]
                for ln in res:
                    model.note(st, ln)
                lines += res
            else:
                lines.append("Зонда карты нет: склады и мосты по оценочным координатам (кнопка 'Зонд карты').")
            sc = st.get("scenario") or {}
            lines.append(f"Создана кампания {p.name}: {sc.get('title') or sc.get('variant')}, seed {sc.get('seed')}.")
            model.save(st, p)
            return {"lines": lines, "file": p.name, "state": view(st)}
        if action == "presetcopy":                   # копия пресета для правки: presets/<имя>.json в папке проекта
            tid = req.get("theatre") or THEATRES[0][0]
            src = self.preset_path(tid, req.get("preset"))
            name = (req.get("name") or "").strip()
            if not re.fullmatch(r"[\w\-. а-яА-ЯёЁ]+", name):
                raise ValueError("имя копии: буквы, цифры, пробел, '-', '.', '_'")
            dst = self.root / "presets" / f"{name}.json"
            if dst.exists() and not req.get("overwrite"):
                raise ValueError(f"{dst.name} уже есть - другое имя или отметьте 'перезаписать'")
            d = model.load_json(src)
            d["theatre"] = tid
            d["preset"] = {**(d.get("preset") or {}), "title": name, "copied_from": str(req.get("preset") or src)}
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            return {"lines": [f"Копия пресета: {dst}",
                              "Правьте в текстовом редакторе (части: units - тип type, число count, аэродром base, роль role); "
                              "в списке пресетов она появится как '(свой)'."]}
        if action in ("mapprobe", "roadsprobe"):
            sec_f = SECTOR
            if req.get("file"):
                try:
                    sec_f = sector_of(self.load(req)[1])
                except (OSError, ValueError, KeyError, RuntimeError):
                    pass
            sid = roads.sector_id(sec_f)
            if action == "roadsprobe":
                out = missions_dir(self.home) / f"redfront_roads_probe_{sid}.miz"
                st_ = self.load(req)[1] if req.get("file") else None
                r = roads.probe(out, sec_f, (st_ or {}).get("oob") or "oob_hamburg.json")
                return {"lines": [f"Служебная миссия дорог: {r['file']} (участков {len(r['pairs'])})",
                                  "Запустите её в DCS, дождитесь 'дороги записаны', выйдите. Новые кампании этого "
                                  "театра возьмут дороги сами; в текущую - кнопка 'Применить дороги'."]}
            out = missions_dir(self.home) / f"redfront_map_probe_{sid}.miz"
            r = mapobj.probe(out, sec_f)
            return {"lines": [f"Служебная миссия: {r['file']} (весь сектор: ячеек {r['tiles']}, ~{r['area_km2']} км2)",
                              "Запустите её в DCS (можно наблюдателем), дождитесь 'объекты карты записаны', выйдите, "
                              "затем 'Применить зонд'."]}
        p, st = self.load(req)
        if action == "state":
            return {"state": view(st)}
        if action == "setlang":                      # язык кампании: окно, брифинг миссии (i18n.py)
            st["settings"]["lang"] = "en" if req.get("lang") == "en" else "ru"
            model.save(st, p)
            return {"state": view(st)}
        if action == "atooptions":                   # режим командующего: что можно выбрать для вылета (без сохранения)
            return {"options": command.options(st, req["id"])}
        if action == "addoptions":                   # добавить полк: исторические допущения, типы, роли, аэродромы
            from . import reinforce
            return {"options": reinforce.options(st)}
        if action == "addunit":
            from . import reinforce
            if req.get("catalog"):
                lines.append(reinforce.add_historical(st, req["catalog"], req.get("base") or None))
            else:
                lines.append(reinforce.add_custom(st, req))
            model.note(st, lines[-1])
            model.save(st, p)
            return {"lines": lines, "state": view(st)}
        if action == "unitinfo":                     # авиачасть: лётчики, ливрея (pilots.py, ливреи DCS через pydcs)
            return {"info": unit_info(st, req["id"])}
        if action == "setlivery":                    # ливрея полка - во все его группы в миссиях, до смены
            u = st["units"][req["id"]]
            if model.category(u) not in ("air", "heli"):
                raise ValueError("ливрея - только у авиачасти")
            lv = str(req.get("livery") or "").strip()
            if lv:
                u["livery"] = lv
            else:
                u.pop("livery", None)
            lines.append(f"{u['name']}: ливрея {lv or 'по умолчанию DCS'}.")
            model.save(st, p)
            return {"lines": lines, "state": view(st)}
        if action == "rebaseoptions":                # режим командующего: куда можно перебазировать часть
            return {"options": command.base_options(st, req["id"])}
        if action == "rebase":
            lines.append(command.rebase(st, req["id"], req["base"]))
            model.save(st, p)
            return {"lines": lines, "state": view(st)}
        if action == "atocands":                     # задачи, не вошедшие в план
            return {"cands": command.candidates(st)}
        if action in ("atoedit", "atoremove", "atoadd"):
            if action == "atoedit":
                lines += command.edit(st, req["id"], tot=req.get("tot") or None, groups=req.get("groups") or {})
            elif action == "atoremove":
                lines.append(command.remove(st, req["id"]))
            else:
                lines += command.add(st, req["key"], tot=req.get("tot") or None)
            planner.plan(st)                         # вылеты игрока - из плана полётов
            model.save(st, p)
            return {"lines": lines, "state": view(st)}
        if action == "plan":
            if not planner.plan(st):
                lines.append(i18n.L(i18n.lang(st), "Задач нет: ", "No tasks: ") + st['task_reason'])
            else:
                lines.append(i18n.L(i18n.lang(st), f"План полётов на сутки {st['day']}: своих вылетов для игрока {len(st['tasks'])}",
                                    f"Air tasking order for day {st['day']}: {len(st['tasks'])} sorties available to the player")
                             + (f" ({i18n.L(i18n.lang(st), 'после', 'after')} {ato.hhmm(st['clock_s'])})" if st.get("clock_s") else "") + ".")
        elif action == "build":
            if not st.get("tasks"):
                planner.plan(st)
            out = missions_dir(self.home) / f"redfront_{p.stem}_day{st['day']}.miz"
            if str(req.get("budget") or "").strip():
                st["settings"]["mission_budget"] = max(0, int(req["budget"]))
            man = build_mod.build(st, out, fly=req.get("fly") or "strike", task_no=int(req.get("task") or 1),
                                  humans=int(req.get("humans") or 1))
            n = sum(len(g["vehicles"]) for g in man["ground"])
            lines.append(i18n.L(i18n.lang(st), f"Миссия: {man['file']} (наземных машин {n}, бюджет ",
                                f"Mission: {man['file']} (ground vehicles {n}, budget ")
                         + f"{st['settings'].get('mission_budget', materialize.MISSION_BUDGET)})")
            if man.get("pre_lines"):             # модель продвинута к началу миссии (sim.advance)
                lines.append(f"Обстановка на {sim.ato_hhmm(man['ground_s'] or 0)}:")
                lines += man["pre_lines"]
            lines += man["package_lines"]
            lines += man.get("ctld_lines") or []
        elif action == "debrief":
            f = debrief.find_file(st, self.home)
            lines.append(i18n.L(i18n.lang(st), "Файл дебрифа: ", "Debrief file: ") + str(f))
            lines += debrief.apply(st, debrief.read(f))
        elif action == "endday":
            lines += sim.end_day(st)
            if not lines:
                lines.append(i18n.L(i18n.lang(st), "День прошёл без событий.", "The day passed without events."))
        elif action == "roadsapply":
            rf = saved_games_file(f"roads_{roads.sector_id(sector_of(st))}.json", self.home)
            if not rf:
                raise FileNotFoundError("файла дорог нет: сначала 'Зонд дорог' и запуск служебной миссии в DCS")
            lines += roads.apply(st, roads.load(rf), note=False)[:5]
            lines.append(f"Дороги применены: {len(st.get('roads', {}))} участков.")
        elif action == "mapapply":
            mf = saved_games_file(f"map_{roads.sector_id(sector_of(st))}.json", self.home)
            if not mf:
                raise FileNotFoundError("файла зонда карты нет: сначала 'Зонд карты' и запуск служебной миссии в DCS")
            pr = mapobj.load(mf)
            res = [f"Зонд карты {mf.name}: " + mapobj.summary(pr)] + mapobj.apply(st, pr)
            res += [f"ошибка зонда {k}: {v}" for k, v in pr["errors"].items()]
            for ln in res:                       # в журнал кампании (вкладка "Журнал") и в окно вывода
                model.note(st, ln)
            lines += res
            lines.append("Типы объектов у пунктов складов:")
            lines += mapobj.depot_report(pr)
        elif action == "mapimport":
            res = mapobj.import_miz(st, Path(req["miz"]))
            for ln in res:
                model.note(st, ln)
            lines += res
        else:
            raise ValueError(f"неизвестное действие {action}")
        model.save(st, p)
        return {"lines": lines, "state": view(st)}


def handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def js(self, obj: dict, code: int = 200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def local(self) -> bool:
            # Только страница этого сервера: чужой сайт в браузере не должен слать сюда запросы (Origin)
            # или читать ответы через подмену DNS (Host).
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts or (origin is not None and origin not in
                                                          {f"http://{h}" for h in hosts}):
                self.send(403, b"forbidden", "text/plain")
                return False
            return True

        def do_GET(self):
            if not self.local():
                return
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self.send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/web/"):
                f = (WEB / u.path[len("/web/"):]).resolve()
                if WEB.resolve() in f.parents and f.is_file():
                    return self.send(200, f.read_bytes(), CTYPES.get(f.suffix, "application/octet-stream"))
                return self.send(404, b"not found", "text/plain")
            if u.path == "/api/info":
                return self.run(lambda: app.info())
            if u.path == "/api/state":
                q = parse_qs(u.query)
                return self.run(lambda: app.do("state", {"file": q.get("file", [""])[0]}))
            self.send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self.local():
                return
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self.send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            self.run(lambda: app.do(u.path[len("/api/"):], req))

        def run(self, fn):
            try:
                with LOCK:
                    self.js(fn())
            except (KeyError, ValueError, FileNotFoundError, RuntimeError, OSError) as e:
                self.js({"error": str(e.args[0] if e.args else e)}, 400)
            except Exception as e:                                  # noqa: BLE001 - показать в окне, не уронить сервер
                traceback.print_exc()
                self.js({"error": f"{type(e).__name__}: {e}"}, 500)
    return H


def serve(port: int = 8765, root: Path | None = None, open_browser: bool = True) -> int:
    app = App(Path(root or Path.cwd()))
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler(app))
    url = f"http://127.0.0.1:{port}/"
    print(f"redfront: окно кампании {url}  (закрыть - Ctrl+C или закрыть это окно)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0

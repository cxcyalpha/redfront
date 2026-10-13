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
from . import ato, debrief, logistics, mapobj, model, ops, planner, roads, sim
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
    """Состояние кампании для страницы: только то, что рисуется и показывается."""
    units = st["units"]
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
                            "checked": bool(u.get("pos_checked")) or cat == "airfield"})
        elif cat in ("air", "heli"):
            b = st["airbases"].get(u["base"], {})
            air.append({"id": u["id"], "name": u["name"], "side": u["side"], "type": u["type"], "role": u["role"],
                        "count": u.get("count", 0), "count0": u.get("count0", u.get("count", 0)),
                        "available": logistics.available(st, u), "base": b.get("name", u["base"])})
        elif cat in ("ground", "sam", "gci"):
            if u["state"] == "pending":
                pos = st["places"][u["route"][0]] if u.get("route") else u.get("pos")
            else:
                pos = model.unit_pos(st, u)
            if not pos:
                continue
            g = {"id": u["id"], "name": u["name"], "side": u["side"], "cat": cat, "state": u["state"],
                 "order": u.get("order"), "strength": round(model.strength(u), 2), "pos": _ll(pos),
                 "supply": u.get("supply", 1.0), "attached": bool(u.get("attached_to")),
                 "arrives": u.get("arrives_day"),
                 "engaged": [units[f]["name"] for f in u.get("engaged", []) if f in units],
                 "types": ", ".join(f"{c['type']} x{c['count']}" for c in u.get("composition", []))}
            if cat == "sam":
                g["threat_km"] = round(planner.threat_radius_km(u), 1)
            if cat == "gci":
                g["types"] += f" · канал {u.get('channel')}, радиус {u.get('radius_km')} км"
            if "route" in u and len(u["route"]) > 1 and u["state"] in ("march", "battle"):
                pts = model.route_points(st, u)
                here, i = model.point_at_km(pts, u["progress_km"])
                g["route"] = [_ll(here)] + [_ll(q) for q in pts[i + 1:]]          # остаток маршрута
            ground.append(g)
    tasks = []
    for i, t in enumerate(st.get("tasks") or [], 1):
        base = st["airbases"].get(t["base"], {})
        tasks.append({"n": i, "title": t["title"], "km": round(t["distance_km"]), "base": base.get("name", t["base"]),
                      "time": (f"взлёт {ato.hhmm(t['takeoff_s'])}, на объекте {ato.hhmm(t['tot_s'])}"
                               if t.get("tot_s") is not None else ""),
                      "base_pos": _ll(base) if "lat" in base else None,
                      "ip": _ll(t["ip"]) if t.get("ip") else None,
                      "target": _ll(t["target_pos"]) if t.get("target_pos") else None,
                      "threats": [units[x]["name"] for x in t.get("threats", []) if x in units],
                      "notes": t.get("package_notes", ""),
                      "package": [{"group": g["group"], "title": g["title"], "size": g["size"],
                                   "performer": units[g["performer"]]["name"] if g["performer"] in units else g["performer"]}
                                  for g in t.get("package", [])]})
    sc = st.get("scenario") or {}
    man = st.get("manifest") or {}
    return {
        "name": st["name"], "day": st["day"], "sortie": st["sortie"], "side": st["player_side"],
        "date": st.get("date"), "scenario": sc.get("title") or sc.get("variant"), "seed": sc.get("seed"),
        "randomness": st["settings"].get("randomness", True),
        "budget": st["settings"].get("mission_budget", materialize.MISSION_BUDGET),
        "places": places, "links": links, "ground": ground, "objects": objects, "air": air,
        "airbases": [{"id": k, "name": b["name"], "side": b.get("side"), "pos": _ll(b), "state": b.get("state", "open")}
                     for k, b in st["airbases"].items()],
        "tasks": tasks, "task_reason": st.get("task_reason") if not tasks else None,
        "ato": ato.rows(st), "clock": ato.hhmm(st.get("clock_s") or 0) if st.get("clock_s") else None,
        "built": {"file": man.get("file"), "sortie": man.get("sortie")} if man else None,
        "log": st["log"][-80:],
    }


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
            rf = saved_games_file(f"roads_{sid}.json", self.home)
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
        if action == "plan":
            if not planner.plan(st):
                lines.append(f"Задач нет: {st['task_reason']}")
            else:
                lines.append(f"План полётов на сутки {st['day']}: своих вылетов для игрока {len(st['tasks'])}"
                             + (f" (после {ato.hhmm(st['clock_s'])})" if st.get("clock_s") else "") + ".")
        elif action == "build":
            if not st.get("tasks"):
                planner.plan(st)
            out = missions_dir(self.home) / f"redfront_{p.stem}_day{st['day']}.miz"
            if str(req.get("budget") or "").strip():
                st["settings"]["mission_budget"] = max(0, int(req["budget"]))
            man = build_mod.build(st, out, fly=req.get("fly") or "strike", task_no=int(req.get("task") or 1))
            n = sum(len(g["vehicles"]) for g in man["ground"])
            lines.append(f"Миссия: {man['file']} (наземных машин {n}, бюджет {st['settings'].get('mission_budget', materialize.MISSION_BUDGET)})")
            lines += man["package_lines"]
        elif action == "debrief":
            f = debrief.find_file(st, self.home)
            lines.append(f"Файл дебрифа: {f}")
            lines += debrief.apply(st, debrief.read(f))
        elif action == "endday":
            lines += sim.end_day(st)
            if not lines:
                lines.append("День прошёл без событий.")
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

"""Аэродромы карты, которых ещё нет в pydcs (карта DCS обновилась раньше pydcs: Cold War Germany 2026 - Польша,
Франция). Данные - из служебной миссии lua/airbase_probe.lua (world.getAirbases: id, имя, место, полосы, стоянки).

  probe(out, theatre)  - служебная миссия; её запуск в DCS пишет Saved Games\\DCS\\redfront\\airbases_<theatre>.json;
  apply(file)          - кладёт файл в данные пакета (data/airbases/<theatre>.json) - для всех кампаний;
  install(terrain)     - добавляет в терраин pydcs аэродромы из файла, которых в нём нет (по id): классы Airport с
                         полосами и стоянками; model.terrain_class() отдаёт терраин уже с ними.
Стоянки без размеров (getParking их не даёт) - разрешение pydcs по старым правилам (slot_version 1: большая/нет,
вертолётная/нет): Term_Type 40 - только вертолёты, 68 - укрытие, 72 - только самолёты, 100/104 - все (104 - большая).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import model

LUA = Path(__file__).parent / "lua" / "airbase_probe.lua"
DATA_DIR = model.DATA / "airbases"
CAT_AIRDROME, CAT_HELIPAD = 0, 1
TERM_HELI, TERM_SHELTER, TERM_PLANE, TERM_BOTH, TERM_BIG, TERM_RUNWAY = 40, 68, 72, 100, 104, 16


def data_file(theatre: str) -> Path:
    return DATA_DIR / f"{model.theatre_id(theatre)}.json"


def load(theatre: str) -> list[dict]:
    p = data_file(theatre)
    if not p.is_file():
        return []
    try:
        return [a for a in json.loads(p.read_text(encoding="utf-8")).get("airbases", [])
                if a.get("category") in (CAT_AIRDROME, CAT_HELIPAD) and a.get("id", -1) >= 0]
    except (OSError, ValueError):
        return []


def _airport_class(a: dict):
    """Класс Airport pydcs по записи зонда."""
    from dcs import mapping
    from dcs.terrain.terrain import Airport, ParkingSlot, Runway, RunwayApproach

    def init(self, terrain):
        Airport.__init__(self, mapping.Point(a["x"], a["y"], terrain), terrain)
        for i, r in enumerate(a.get("runways") or []):
            hdg = round(math.degrees(r.get("course", 0.0))) % 360   # course DCS - радианы, направление взлёта
            name = r.get("name") or f"{hdg // 10:02d}"
            opp = (hdg + 180) % 360
            self.runways.append(Runway(id=i + 1, name=name,
                                       main=RunwayApproach(name=f"{round(hdg / 10) % 36 or 36:02d}", heading=hdg, beacons=[]),
                                       opposite=RunwayApproach(name=f"{round(opp / 10) % 36 or 36:02d}", heading=opp, beacons=[])))
        heli_only = a.get("category") == CAT_HELIPAD
        for s in a.get("parking") or []:
            t = s.get("type", TERM_BOTH)
            if t == TERM_RUNWAY:
                continue                         # старт с полосы - не стоянка
            self.parking_slots.append(ParkingSlot(
                crossroad_idx=s.get("idx", 0), position=mapping.Point(s["x"], s["y"], terrain),
                large=t in (TERM_BIG,) or not any(x.get("type") == TERM_BIG for x in a.get("parking") or []),
                heli=t in (TERM_HELI, TERM_BOTH, TERM_BIG), airplanes=not heli_only and t != TERM_HELI, slot_name=str(s.get("idx", 0)),
                shelter=t == TERM_SHELTER))

    return type(f"Ext_{a['id']}", (Airport,), {"id": int(a["id"]), "name": a["name"], "tacan": None, "unit_zones": [],
                                               "civilian": False, "slot_version": 1, "atc_radio": None, "__init__": init})


def install(terrain, theatre: str | None = None) -> list[str]:
    """Добавить в терраин недостающие аэродромы из данных зонда (по id; имя - как в DCS). -> имена добавленных."""
    have = {ap.id for ap in terrain.airports.values()}
    added = []
    for a in load(theatre or getattr(terrain, "name", "")):
        if int(a["id"]) in have or a["name"] in terrain.airports:
            continue
        try:
            ap = _airport_class(a)(terrain)
        except Exception:                        # noqa: BLE001 - кривая запись зонда не ломает терраин
            continue
        terrain.airports[a["name"]] = ap
        added.append(a["name"])
    return added


def missing(theatre: str) -> list[dict]:
    """Записи зонда, которых нет в pydcs (аэродромы, не площадки), с широтой/долготой."""
    from dcs.mapping import Point
    import dcs.terrain as _t
    base = getattr(_t, model.THEATRE_INFO[model.theatre_id(theatre)]["cls"])()
    have = {ap.id for ap in base.airports.values()}
    out = []
    for a in load(theatre):
        if int(a["id"]) in have:
            continue
        ll = Point(a["x"], a["y"], base).latlng()
        out.append({**{k: a[k] for k in ("id", "name", "category")}, "lat": round(ll.lat, 5), "lon": round(ll.lng, 5),
                    "runways": len(a.get("runways") or []), "parking": len(a.get("parking") or [])})
    return out


def probe(out_path: Path, theatre: str = "germany") -> dict:
    from dcs import Mission
    from dcs.action import DoScript
    from dcs.translation import String
    from dcs.triggers import TriggerStart
    tid = model.theatre_id(theatre)
    script = LUA.read_text(encoding="utf-8").replace("@THEATRE@", tid)
    import dcs.terrain as _t
    m = Mission(getattr(_t, model.THEATRE_INFO[tid]["cls"])())
    trig = TriggerStart(comment="redfront airbase probe")
    trig.add_action(DoScript(String(script)))
    m.triggerrules.triggers.append(trig)
    m.set_description_text(f"redfront: служебная миссия аэродромов карты '{tid}'. Запустите (можно наблюдателем), "
                           "дождитесь сообщения 'аэродромы записаны' и выйдите.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return {"file": str(out_path), "theatre": tid}


def apply(src: Path) -> dict:
    """Файл зонда -> data/airbases/<theatre>.json (для всех кампаний). -> {theatre, total, new: [...]}."""
    raw = json.loads(Path(src).read_text(encoding="utf-8"))
    tid = model.theatre_id(raw.get("theatre") or "germany")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file(tid).write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    model._TERRAINS.pop(tid, None)               # терраин пересоздать - уже с новыми аэродромами
    model._TCLS.pop(tid, None)
    return {"theatre": tid, "total": len(raw.get("airbases") or []), "new": missing(tid), "errors": raw.get("errors") or []}


NEAR_KM = 200     # аэродром зонда - в кампанию, если до пункта сектора не дальше: тыл сторон (Польша - ОВД, Франция - НАТО)


def campaign_bases(sec: dict, terrain, bases: dict) -> dict:
    """Аэродромы зонда, которых нет в секторе (и в pydcs), в пределах театра кампании: сторона - по владельцу
    ближайшего пункта на начало. -> {id базы: запись как в секторе}. Вертолётные площадки - нет (только аэродромы)."""
    places = sec.get("places") or {}
    if not places:
        return {}
    known = {b.get("airport") for b in bases.values()} | {b.get("airport") for b in (sec.get("airbases") or {}).values()}
    import dcs.terrain as _t
    tid = model.theatre_id(sec.get("theatre"))
    base_ids = {ap.id for ap in getattr(_t, model.THEATRE_INFO[tid]["cls"])().airports.values()}
    out = {}
    for a in load(tid):
        if a.get("category") != CAT_AIRDROME or int(a["id"]) in base_ids or a["name"] in known:
            continue
        ap = terrain.airports.get(a["name"])
        if ap is None:
            continue
        ll = ap.position.latlng()
        near = min(places.values(), key=lambda q: model.dist_km(q, {"lat": ll.lat, "lon": ll.lng}))
        if model.dist_km(near, {"lat": ll.lat, "lon": ll.lng}) > NEAR_KM or near.get("side") not in ("red", "blue"):
            continue
        bid = "x_" + "".join(c if c.isalnum() else "_" for c in a["name"].lower())
        out[bid] = {"name": a["name"], "airport": a["name"], "side": near["side"], "military": True, "lat": ll.lat,
                    "lon": ll.lng, "state": "open", "probed": True}
    return out

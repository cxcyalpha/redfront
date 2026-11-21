"""Проверка инвариантов движка: прогон кампаний без игрока (модель за обе стороны) и проверка состояния после
каждых суток - что не может быть ни при каком балансе: отрицательная техника, потери больше штата, доли вне 0..1,
NaN в координатах, маршрут по несуществующей связи, разбитая часть в бою, лишние лётчики, повторная выдача
одного id и т.п. Плюс воспроизводимость: два прогона с одним seed дают одно состояние.

Запуск: python tools/engine_check.py [кампания ...] [--days N] [--side red|blue]   (код возврата 1 - нарушения)
"""
from __future__ import annotations

import copy
import json
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redfront import model, ops, planner, sim  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "redfront" / "data"
DAYS = 6
STATES = {"defend", "march", "battle", "halted", "destroyed", "lost", "ready", "deployed", "active", "sunk",
          "garrison", "hold", "withdraw", "reserve", "dug_in", "moving", "repair", "standby", "closed", "open"}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _bad_nums(obj, path="") -> list[str]:
    """NaN и бесконечности в любом числе состояния."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _bad_nums(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:2000]):
            out += _bad_nums(v, f"{path}[{i}]")
    elif _num(obj) and (math.isnan(obj) or math.isinf(obj)):
        out.append(path)
    return out


def invariants(st: dict) -> list[str]:
    bad = []
    places, links = st["places"], {tuple(sorted(x)) for x in st.get("links", [])}
    for uid, u in st["units"].items():
        cat = model.category(u)
        tag = f"{uid} ({cat})"
        if u.get("id", uid) != uid:
            bad.append(f"{tag}: id в записи {u.get('id')} != ключ")
        if u.get("side") not in ("red", "blue") and not (cat == "bridge" and u.get("side") is None):   # мост - ничей
            bad.append(f"{tag}: сторона {u.get('side')}")
        for c in u.get("composition", []):
            lost = u.get("lost", {}).get(c["type"], 0.0)
            if c["count"] < 0 or lost < -1e-9:
                bad.append(f"{tag}: {c['type']} штат {c['count']} потери {lost}")
            if lost > c["count"] + 1e-6:
                bad.append(f"{tag}: {c['type']} потерь {lost:.2f} больше штата {c['count']}")
        for k in ("count", "crews"):
            if _num(u.get(k)) and u[k] < 0:
                bad.append(f"{tag}: {k} = {u[k]}")
        if _num(u.get("damage")) and not (0.0 <= u["damage"] <= 1.0 + 1e-9):
            bad.append(f"{tag}: damage {u['damage']}")
        if "route" in u:
            r = u["route"]
            if not r:
                bad.append(f"{tag}: пустой маршрут")
            for p in r:
                if p not in places:
                    bad.append(f"{tag}: пункт маршрута {p} не существует")
            if len(set(r)) != len(r):
                bad.append(f"{tag}: петля в маршруте {' - '.join(r)}")
            ban = set((st.get("off_limits") or {}).get(u.get("side"), []))
            if ban & set(r[1:]):
                bad.append(f"{tag}: маршрут через запретные по сценарию {sorted(ban & set(r[1:]))} ({u.get('order')})")
            for a, b in zip(r, r[1:]):
                if a == b:
                    bad.append(f"{tag}: маршрут стоит на месте {a}>{b}")
                elif tuple(sorted((a, b))) not in links:
                    bad.append(f"{tag}: маршрут по несуществующей связи {a}-{b}")
            if r and all(p in places for p in r):
                km = model.route_km(st, u)
                if u.get("progress_km", 0) < -1e-6 or u.get("progress_km", 0) > km + 0.5:
                    bad.append(f"{tag}: progress_km {u.get('progress_km'):.1f} вне маршрута 0..{km:.1f}")
        if u.get("base") and u["base"] not in st["airbases"] and not u.get("pos") and "route" not in u:
            bad.append(f"{tag}: база {u['base']} не существует")
        if u.get("attached_to") and u["attached_to"] not in st["units"]:
            bad.append(f"{tag}: придана несуществующей части {u['attached_to']}")
        if cat in ("air", "heli") and "crews" in u and u.get("pilots") is not None:
            if len(u["pilots"]) > max(u["crews"], 0):
                bad.append(f"{tag}: лётчиков {len(u['pilots'])} больше экипажей {u['crews']}")
            names = [p["name"] for p in u["pilots"]]
            if len(set(names)) != len(names):
                bad.append(f"{tag}: повторяющиеся имена лётчиков")
        if u.get("state") in ("destroyed", "lost", "sunk") and u.get("_in_battle"):
            bad.append(f"{tag}: уничтожена, но в бою")
        if cat == "ground" and "composition" in u and u.get("state") not in ("destroyed", "lost") and model.strength(u) <= 0:
            bad.append(f"{tag}: боеспособность 0, но состояние {u.get('state')}")
    for p, d in places.items():
        if d.get("side") not in ("red", "blue", None):
            bad.append(f"пункт {p}: сторона {d.get('side')}")
        if not (-90 <= d["lat"] <= 90 and -180 <= d["lon"] <= 180):
            bad.append(f"пункт {p}: координаты {d['lat']},{d['lon']}")
    for b, d in st["airbases"].items():
        if _num(d.get("damage")) and not (0 <= d["damage"] <= 1 + 1e-9):
            bad.append(f"аэродром {b}: damage {d['damage']}")
    for side, stock in (st.get("munitions") or {}).items():
        if isinstance(stock, dict):
            for k, v in stock.items():
                if _num(v) and v < -1e-6:
                    bad.append(f"боеприпасы {side}/{k}: {v}")
    bad += [f"NaN/inf: {x}" for x in _bad_nums(st)[:10]]
    return bad


def run(name: str, days: int, side: str, seed: int = 1) -> tuple[list[str], dict]:
    st = model.new_campaign("chk", sector=f"sector_{name}.json", oob=f"oob_{name}.json", seed=seed, player_side=side)
    problems = [f"сутки 0: {x}" for x in invariants(st)]
    for d in range(1, days + 1):
        try:
            planner.plan(st)
            sim.end_day(st)
        except Exception:                        # noqa: BLE001 - любое исключение - находка
            problems.append(f"сутки {d}: исключение\n{traceback.format_exc(limit=6)}")
            break
        problems += [f"сутки {d}: {x}" for x in invariants(st)]
    return problems, st


def _strip(st: dict) -> str:
    s = copy.deepcopy(st)
    for k in [k for k in s if k.startswith("_") or k == "campaign_id"]:
        s.pop(k)
    return json.dumps(s, sort_keys=True, ensure_ascii=False, default=str)


def main(argv: list[str]) -> int:
    days, side = DAYS, "red"
    if "--days" in argv:
        i = argv.index("--days")
        days = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if "--side" in argv:
        i = argv.index("--side")
        side = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = argv or sorted(p.stem[len("sector_"):] for p in DATA.glob("sector_*.json"))
    total = 0
    for n in names:
        probs, st1 = run(n, days, side)
        _, st2 = run(n, min(days, 2), side)
        _, st1b = run(n, min(days, 2), side)
        if _strip(st2) != _strip(st1b):
            probs.append("два прогона с одним seed разошлись (невоспроизводимость)")
        uniq = list(dict.fromkeys(p.split(": ", 1)[1] if ": " in p else p for p in probs))
        print(f"{'OK  ' if not uniq else 'FAIL'} {n}: {len(uniq)} нарушений за {days} сут.")
        for p in uniq[:15]:
            print("     ", p)
        total += len(uniq)
    print(f"ИТОГ: {total} нарушений")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

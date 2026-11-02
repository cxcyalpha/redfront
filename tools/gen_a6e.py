"""A-6E для pydcs из файлов DCS (Heatblur): tools/a6e_src/Pylons.lua (оружие по пилонам) и A6E_payloads.lua (штатные
подвески ИИ) -> redfront/mods/a6e.py (тип и оружие) и подвески A6E в data/payloads_custom.json.

Оружие, которое pydcs уже знает (почти всё: держатели HB_A6E_* с названиями и весами), - ссылкой на него;
недостающее - своим описанием, вес - ОЦЕНКА (по боеприпасу и числу на держателе). Названия - по комментариям
Pylons.lua, обозначения - через дефис (Mk-82, GBU-12): по ним weapons.py определяет год.

    python tools/gen_a6e.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "a6e_src"
GROUPS = ("A6_SHARED_weapons", "A6E_BASE_weapons", "A6E_TRAM_weapons", "A6E_SWIP_weapons")
UNIT_KG = {   # ОЦЕНКИ: вес одного боеприпаса, кг
    "BDU33": 11, "MK76": 11, "MK106": 2.3, "BDU45SE": 254, "BDU45": 241, "MK81": 118, "MK82SE": 254, "MK82": 241,
    "MK83": 447, "MK84": 894, "M117": 340, "GBU12": 277, "GBU16": 469, "GBU10": 934, "LAU10": 220, "LAU61MK151": 280,
    "LAU68MK5": 100, "LAU68MK151": 100, "MK20": 222, "SUU25": 220, "TALD": 180, "AERO1D_EMPTY": 130, "AERO1D": 1050,
    "D704": 680, "LAU7_AIM9": 90,
}
NICE = [(r"\bMk(\d+)\b", r"Mk-\1"), (r"\bGBU(\d+)\b", r"GBU-\1"), (r"\bBDU(\d+)", r"BDU-\1"), (r"\bLAU(\d+)", r"LAU-\1"),
        (r"\bSUU(\d+)", r"SUU-\1"), (r"\bM(1117|117)D?\b", r"M117"), (r"\bROCKEYE\b", "Mk-20 Rockeye"), (r"\bMk20\b", "Mk-20")]
RACK_KG = {"MER": 100, "TER": 50}


def entries() -> list[dict]:
    txt = (SRC / "Pylons.lua").read_text(encoding="utf-8")
    out = []
    for g in GROUPS:
        m = re.search(g + r"\s*=\s*\{(.*?)\n\}", txt, re.S)
        for ln in m.group(1).splitlines():
            mm = re.search(r'\{id\s*=\s*"([^"]+)".*?pylons\s*=\s*\{([01,]+)\}.*?--\s*(.*)$', ln)
            if mm:
                out.append({"id": mm.group(1), "pylons": [int(x) for x in mm.group(2).split(",")], "comment": mm.group(3).strip()})
    return out


def name_of(clsid: str, comment: str) -> str:
    n = comment
    for a, b in NICE:
        n = re.sub(a, b, n, flags=re.I)
    cnt = re.search(r"_(\d)x", clsid)
    side = " (left)" if clsid.endswith("_LEFT}") else " (right)" if clsid.endswith("_RIGHT}") else ""
    return f"{n}{' - ' + cnt.group(1) + ' pcs' if cnt else ''}{side} (A-6E)"


def weight(clsid: str) -> float:
    key = clsid.strip("{}").replace("HB_A6E_", "")
    base = next((v for k, v in sorted(UNIT_KG.items(), key=lambda kv: -len(kv[0])) if key.startswith(k)), 200)
    cnt = re.search(r"_(\d)x", clsid)
    rack = next((v for k, v in RACK_KG.items() if f"_{k}_" in key or key == k), 0)
    return round(base * (int(cnt.group(1)) if cnt else 1) + rack, 1)


def main() -> None:
    from dcs.weapons_data import weapon_ids
    ws, pylons = {}, {p: [] for p in range(1, 6)}
    for e in entries():
        for p in range(1, 6):
            if not e["pylons"][p - 1]:
                continue
            cid = e["id"]
            if "_RIGHT" in cid and p in (1, 2):
                cid = cid.replace("_RIGHT", "_LEFT")
            key = "w_" + re.sub(r"\W+", "_", cid.strip("{}")).strip("_")
            if cid in weapon_ids:                # оружие pydcs (Mk-82, HARM, Harpoon...) - как есть
                ref = f"weapon_ids[{cid!r}]"
            else:
                ws[key] = {"clsid": cid, "name": name_of(cid, e["comment"]), "weight": weight(cid)}
                ref = f"WeaponsA6E.{key}"
            if key not in [k for k, _r in pylons[p]]:
                pylons[p].append((key, ref))
    lines = ['# A-6E Intruder (Heatblur, ИИ-юнит базового DCS): тип для pydcs - в pydcs его нет. Сгенерировано tools/gen_a6e.py',
             '# из файлов DCS (Pylons.lua, A6E.lua). Веса оружия - ОЦЕНКИ.',
             "from typing import Set", "", "from dcs import task", "from dcs.planes import PlaneType",
             "from dcs.weapons_data import weapon_ids", "", "from redfront.mods import inject_weapons, planemod", "", "",
             "class WeaponsA6E:"]
    for k, w in sorted(ws.items()):
        lines.append(f"    {k} = {json.dumps(w, ensure_ascii=False)}")
    lines += ["", "", "inject_weapons(WeaponsA6E)", "", "", "@planemod", "class A6E(PlaneType):",
              '    id = "A6E"', "    flyable = False", "    height = 4.93", "    width = 16.15", "    length = 16.73",
              "    fuel_max = 7229.8", "    max_speed = 1037", "    chaff = 30", "    flare = 30", "    charge_total = 60",
              "    chaff_charge_size = 1", "    flare_charge_size = 1", "    radio_frequency = 305", '    livery_name = "A6E"', ""]
    for p in range(1, 6):
        lines.append(f"    class Pylon{p}:")
        for key, ref in pylons[p]:
            lines.append(f"        {key} = ({p}, {ref})")
        lines.append("")
    lines += ["    pylons: Set[int] = {1, 2, 3, 4, 5}",
              "    tasks = [task.SEAD, task.AFAC, task.GroundAttack, task.PinpointStrike, task.CAS, task.RunwayAttack,",
              "             task.AntishipStrike, task.Reconnaissance, task.Refueling]",
              "    task_default = task.GroundAttack", ""]
    (ROOT / "redfront" / "mods" / "a6e.py").write_text("\n".join(lines), encoding="utf-8")
    # штатные подвески ИИ -> payloads_custom.json (по имени) + подвески по функции для планировщика
    src = (SRC / "A6E_payloads.lua").read_text(encoding="utf-8")
    pls = {}
    for blk in re.split(r"\n\t\t\[\d+\] =\n", src)[1:]:
        nm = re.search(r'\["displayName"\] = "([^"]+)"', blk).group(1)
        pyl = {num: {"CLSID": c} for c, num in re.findall(r'\["CLSID"\] = "([^"]+)",\s*\["num"\] = (\d+)', blk)}
        pls[nm] = {"tasks": {}, "pylons": pyl}
    by_func = {   # функция -> штатная подвеска (по году: новее - weapons.degrade заменит или снимет)
        "STRIKE": "Mk82*28", "CAS": "Mk20*28", "BAI": "Mk20*28", "DEAD": "Mk20*28", "OCA/Runway": "Mk84*5",
        "SEAD": "HARM*2, Mk20*10, AERO-1D Fuel Tank 300 GAL", "Anti-ship": "HARPOON*2, AIM-9M, ALQ-167, AERO-1D Fuel Tank 300 GAL",
    }
    p = ROOT / "redfront" / "data" / "payloads_custom.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    t = {**pls, **{f: pls[n] for f, n in by_func.items()}}
    data.setdefault("types", {})["A6E"] = t
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"оружия A-6E {len(ws)}, подвесок {len(pls)}")


if __name__ == "__main__":
    main()

"""Импорт подвесок по задачам из DCS Retribution (resources/customized_payloads/*.lua, LGPL-3.0) в
redfront/data/payloads.json: {тип DCS id: {имя подвески: {"tasks": [...], "pylons": {номер: {"CLSID", "settings"?}}}}}.
Запуск: python tools/import_payloads.py <путь к dcs-retribution/resources/customized_payloads>.

Свои подвески: python tools/import_payloads.py --custom <папка> - файлы редактора миссий DCS (Saved Games\\DCS\\
MissionEditor\\UnitPayloads\\<тип>.lua); подвески с именем категории (cap, escort, strike, bombs, bai, cas,
anti_armor, sead, dead, runway, antiship) - в redfront/data/payloads_custom.json, поверх Retribution. Подвеска -
самая современная; по году кампании её поправит weapons.degrade."""
import json
import sys
from pathlib import Path

import lupa

CUSTOM = "--custom" in sys.argv
src = Path([a for a in sys.argv[1:] if a != "--custom"][0])
CATS = {"cap", "escort", "strike", "bombs", "bai", "cas", "anti_armor", "sead", "dead", "runway", "antiship"}
L = lupa.LuaRuntime(unpack_returned_tuples=True)


def py(v):
    if lupa.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [py(v[k]) for k in sorted(keys)]
        return {str(k): py(v[k]) for k in keys}
    return v


out = {}
for f in sorted(src.glob("*.lua")):
    try:
        t = py(L.execute(f.read_text(encoding="utf-8", errors="replace")))
    except Exception as e:                       # noqa: BLE001 - файл с ошибкой Lua пропускаем
        print("skip", f.name, e)
        continue
    pls = {}
    for p in t.get("payloads", {}) if isinstance(t.get("payloads"), dict) else t.get("payloads", []):
        p = t["payloads"][p] if isinstance(p, str) else p
        pyl = {}
        for x in p.get("pylons", []) if isinstance(p.get("pylons"), list) else p.get("pylons", {}).values():
            d = {"CLSID": x["CLSID"]}
            if x.get("settings"):
                d["settings"] = x["settings"]
            pyl[str(x["num"])] = d
        pls[p["name"]] = {"tasks": p.get("tasks", []), "pylons": pyl}
    out[t.get("unitType") or t.get("name") or f.stem] = pls
if CUSTOM:                                       # свои: только подвески с именем категории, слиянием в payloads_custom.json
    dst = Path(__file__).resolve().parent.parent / "redfront" / "data" / "payloads_custom.json"
    cur = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {"types": {}}
    n = 0
    for ty, pls in out.items():
        for name, p in pls.items():
            if name.strip().lower() in CATS:
                cur.setdefault("types", {}).setdefault(ty, {})[name.strip().lower()] = p
                n += 1
            else:
                print(f"пропуск {ty}: '{name}' - имя не категория ({', '.join(sorted(CATS))})")
    dst.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    print(n, "своих подвесок ->", dst)
    sys.exit(0)
dst = Path(__file__).resolve().parent.parent / "redfront" / "data" / "payloads.json"
dst.write_text(json.dumps({"_about": "Подвески по задачам из DCS Retribution (https://github.com/dcs-retribution/"
                           "dcs-retribution, resources/customized_payloads, LGPL-3.0), импорт tools/import_payloads.py. "
                           "Ключ - DCS id типа, затем имя подвески.", "types": out}, ensure_ascii=False, indent=0),
               encoding="utf-8")
print(len(out), "типов ->", dst)

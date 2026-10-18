"""Импорт подвесок по задачам из DCS Retribution (resources/customized_payloads/*.lua, LGPL-3.0) в
redfront/data/payloads.json: {тип DCS id: {имя подвески: {"tasks": [...], "pylons": {номер: {"CLSID", "settings"?}}}}}.
Запуск: python tools/import_payloads.py <путь к dcs-retribution/resources/customized_payloads>."""
import json
import sys
from pathlib import Path

import lupa

src = Path(sys.argv[1])
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
dst = Path(__file__).resolve().parent.parent / "redfront" / "data" / "payloads.json"
dst.write_text(json.dumps({"_about": "Подвески по задачам из DCS Retribution (https://github.com/dcs-retribution/"
                           "dcs-retribution, resources/customized_payloads, LGPL-3.0), импорт tools/import_payloads.py. "
                           "Ключ - DCS id типа, затем имя подвески.", "types": out}, ensure_ascii=False, indent=0),
               encoding="utf-8")
print(len(out), "типов ->", dst)

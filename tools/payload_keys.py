"""Полный список ключей своих подвесок (payloads_custom.json) и типов ЛА сценариев -> docs/payload_categories.md.

Ключ подвески = имя подвески в редакторе миссий DCS (tools/import_payloads.py --custom). Порядок поиска у группы:
задача/группа (strike_airfield/cover) -> группа (cover) или задача (strike_airfield) -> категории (escort, cap...).
Нет своей - подвеска DCS Retribution той же категории; оружие новее года кампании - замена (weapons.degrade).

    python tools/payload_keys.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from redfront import build, dcstypes, mods  # noqa: E402

CAT_TXT = {"cap": "прикрытие, дежурство ПВО, барражирование (воздух-воздух, топливо)",
           "escort": "сопровождение ударной группы (воздух-воздух)", "strike": "удар по объекту (мосты, склады, заводы)",
           "bombs": "бомбы общего назначения", "bai": "удар по колоннам и путям подвоза, изоляция",
           "cas": "непосредственная поддержка войск", "anti_armor": "противотанковое", "sead": "подавление ПВО (ПРР)",
           "dead": "уничтожение ЗРК", "runway": "удар по аэродрому (ВПП)", "antiship": "удар по кораблям"}


def main() -> None:
    kinds, groups = {}, {}
    for f in sorted(glob.glob(str(ROOT / "redfront" / "data" / "doctrine" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for k, t in d["tasks"].items():
            if build.KIND_CATS.get(k) or (t.get("strike") or {}).get("loadout"):
                kinds.setdefault(k, t["title"])
            for sp in t.get("support", []):
                groups.setdefault(f"{k}/{sp['id']}", f"{t['title']}: {sp.get('title', sp['id'])}")
    types: dict[str, set] = {}
    for f in sorted(glob.glob(str(ROOT / "redfront" / "data" / "oob_*.json"))):
        sc = Path(f).stem[4:]
        for u in json.loads(Path(f).read_text(encoding="utf-8"))["units"]:
            if u.get("type"):
                try:
                    tid = dcstypes.flying(u["type"]).id
                except Exception:   # noqa: BLE001 - тип мода без загрузки
                    tid = u["type"]
                types.setdefault(tid, set()).add(sc)
    for mid, m in mods.MODS.items():
        for _cls, tid in m["types"].items():
            types.setdefault(tid, set()).add(f"мод {mid}")
    for k, (pv, mod) in build.PLAYER_VARIANTS.items():
        if mod:
            mods.load(mod)
        types.setdefault(dcstypes.flying(pv).id, set()).add("версия для игрока")
    out = ["# Ключи своих подвесок\n",
           "Имя подвески в редакторе миссий DCS = ключ. Подвеска - самая современная: по году кампании оружие заменит "
           "weapons.degrade. Импорт: `python tools/import_payloads.py --custom <Saved Games\\DCS\\MissionEditor\\"
           "UnitPayloads>`.\n",
           "Порядок поиска: `задача/группа` -> `группа` или `задача` -> категория -> подвеска Retribution.\n",
           "## Категории (общие)\n", "| Ключ | Что |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in CAT_TXT.items()]
    out += ["\n## Задачи (ударная группа)\n", "| Ключ | Задача |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in sorted(kinds.items())]
    gr = sorted({g.split("/")[1] for g in groups})
    out += ["\n## Группы обеспечения\n", "Ключ группы для всех задач: " + ", ".join(f"`{g}`" for g in gr) + ".\n",
            "| Ключ | Группа |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in sorted(groups.items())]
    out += ["\n## Типы ЛА\n", "| Тип DCS | Где |", "|---|---|"]
    out += [f"| {t} | {', '.join(sorted(s))} |" for t, s in sorted(types.items())]
    p = ROOT / "docs" / "payload_categories.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(len(kinds), "задач,", len(groups), "групп,", len(types), "типов ->", p)


if __name__ == "__main__":
    main()

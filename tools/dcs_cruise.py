"""Крейсерские скорости ЛА из вашей установки DCS -> redfront/data/aircraft.json.

В Lua-описании каждого ЛА DCS есть V_opt - крейсерская скорость для ИИ, м/с ('Cruise speed (for AI)'). Утилита
читает Lua-файлы в папках DCS (и, если указать, модов из Saved Games), находит у каждого ЛА Name и V_opt и
записывает cruise_kmh = V_opt * 3.6 для типов, которые есть в aircraft.json или в составах сил (source - файл).
Остальные записи (ОЦЕНКИ) не трогает.

Запуск (Windows, PowerShell, в папке проекта):
    .venv\\Scripts\\python tools\\dcs_cruise.py "C:\\Program Files\\Eagle Dynamics\\DCS World"
    .venv\\Scripts\\python tools\\dcs_cruise.py "D:\\DCS World" "%USERPROFILE%\\Saved Games\\DCS\\Mods"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redfront import dcstypes  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "redfront" / "data"
SUBDIRS = ("CoreMods/aircraft", "Mods/aircraft", "Scripts/Database", "aircraft", "")   # где лежат описания ЛА
NAME = re.compile(r"""\bName\s*=\s*['"]([^'"]+)['"]""")
VOPT = re.compile(r"\bV_opt\s*=\s*([0-9]+(?:\.[0-9]+)?)")


def scan(roots: list[Path]) -> dict[str, tuple[float, str]]:
    """DCS id типа -> (V_opt, м/с; файл). V_opt относится к последнему Name перед ним в том же файле."""
    found: dict[str, tuple[float, str]] = {}
    seen = set()
    for root in roots:
        for sub in SUBDIRS:
            base = root / sub if sub else root
            if not base.is_dir():
                continue
            for f in base.rglob("*.lua"):
                if f in seen:
                    continue
                seen.add(f)
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "V_opt" not in text:
                    continue
                names = [(m.start(), m.group(1)) for m in NAME.finditer(text)]
                for m in VOPT.finditer(text):
                    prev = [n for pos, n in names if pos < m.start()]
                    if prev and prev[-1] not in found:
                        found[prev[-1]] = (float(m.group(1)), str(f))
    return found


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    roots = [Path(a) for a in argv]
    for r in roots:
        if not r.is_dir():
            print(f"нет папки: {r}")
            return 1
    found = scan(roots)
    p = DATA / "aircraft.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    types = data.setdefault("types", {})
    wanted = set(types)
    for oob in DATA.glob("oob_*.json"):
        wanted |= {u["type"] for u in json.loads(oob.read_text(encoding="utf-8"))["units"] if u.get("type")}
    changed = []
    for cls in sorted(wanted):
        try:
            dcs_id = dcstypes.flying(cls).id                 # имя класса pydcs -> id DCS (Name в Lua)
        except Exception:                                   # noqa: BLE001 - тип, которого pydcs не знает (мод)
            dcs_id = cls
        if dcs_id not in found:
            continue
        v, f = found[dcs_id]
        kmh = round(v * 3.6)
        old = types.get(cls, {}).get("cruise_kmh")
        types[cls] = {**types.get(cls, {}), "cruise_kmh": kmh, "source": f"DCS V_opt {v:g} м/с ({Path(f).name})"}   # cargo_t и др. - как были
        changed.append(f"{cls} ({dcs_id}): {old} -> {kmh} км/ч")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Найдено V_opt у {len(found)} ЛА; обновлено {len(changed)} типов в {p}:")
    for ln in changed:
        print("  " + ln)
    missing = sorted(c for c in wanted if not types.get(c, {}).get("source", "").startswith("DCS"))
    if missing:
        print("Без данных DCS (остаётся оценка или скорость задачи): " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

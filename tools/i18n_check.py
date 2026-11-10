"""Проверка полноты английского перевода: кампании всех театров (обе стороны) проходят через окно (gui.App) на
английском - создание, план, вылеты, правка, авиачасти, конец дня, сборка миссии; всё, что осталось с кириллицей
в ответах окна и в тексте миссии (.miz: брифинг, сообщения скриптов), - в отчёт.

    python tools/i18n_check.py [театр ...] [--out файл] [--days N]
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from redfront import gui, i18n_en  # noqa: E402

CYR = re.compile("[А-Яа-яЁё]")


def miz_text(path: Path) -> set[str]:
    """Строки миссии с кириллицей: брифинг, словарь, скрипты (строковые литералы Lua)."""
    out = set()
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not (n.endswith("dictionary") or n == "mission" or n.endswith(".lua")):
                continue
            t = z.read(n).decode("utf-8", "replace")
            for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', t):
                if CYR.search(m.group(1)):
                    out.add(f"[{n.split('/')[-1]}] " + m.group(1)[:300])
    return out


def run(theatres: list[str], days: int, preset: str | None = None) -> collections.Counter:
    seen: collections.Counter = collections.Counter()
    tmp = Path(tempfile.mkdtemp(prefix="redfront_i18n_"))
    (tmp / "Saved Games" / "DCS" / "Missions").mkdir(parents=True)   # миссии - сюда (menu.missions_dir)
    app = gui.App(tmp, home=tmp)

    def do(action, req):
        try:
            r = app.do(action, req)
        except Exception as e:  # noqa: BLE001
            r = {"error": str(e)}
        for s in i18n_en.missing(i18n_en.deep(r)):
            seen[s] += 1
        return r

    for s in i18n_en.missing(i18n_en.deep(app.info())):
        seen[s] += 1
    for tid, *_ in gui.THEATRES:
        if theatres and tid not in theatres:
            continue
        for side in ("red", "blue"):
            f = f"{tid}_{side}"
            print(f"  {f}", flush=True)
            do("new", {"file": f, "theatre": tid, "side": side, "seed": 7, "overwrite": True, "preset": preset})
            do("setlang", {"file": f, "lang": "en"})
            for day in range(days):
                r = do("plan", {"file": f})
                st = (r.get("state") or {})
                ents = [e for e in st.get("ato") or [] if e.get("id")] if isinstance(st.get("ato"), list) else []
                for e in ents[:12]:
                    do("sortie", {"file": f, "id": e["id"]})
                if ents:
                    do("atooptions", {"file": f, "id": ents[0]["id"]})
                do("atocands", {"file": f})
                do("addoptions", {"file": f})
                for a in (st.get("air") or [])[:4]:
                    do("unitinfo", {"file": f, "id": a["id"]})
                    do("rebaseoptions", {"file": f, "id": a["id"]})
                if day == 0:
                    r = do("build", {"file": f, "task": 1, "ai": True})
                    for m in sorted(tmp.rglob("*.miz")):
                        for s in miz_text(m):
                            seen[s] += 1
                        m.unlink()
                do("endday", {"file": f})
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("theatres", nargs="*")
    ap.add_argument("--out", default="i18n_missing.txt")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--preset", default=None, help="пресет состава сил (oob_germany_1961.json)")
    a = ap.parse_args()
    seen = run(a.theatres, a.days, a.preset)
    Path(a.out).write_text("\n".join(f"{n}\t{s}" for s, n in seen.most_common()), encoding="utf-8")
    print(f"непереведённых строк: {len(seen)} -> {a.out}")
    return 0 if not seen else 1


if __name__ == "__main__":
    sys.exit(main())

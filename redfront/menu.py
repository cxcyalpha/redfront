"""Текстовое меню: весь цикл кампании без набора команд.

    run.bat (или python -m redfront menu [кампания.json])
"""
from __future__ import annotations

from pathlib import Path

from . import build as build_mod
from . import debrief, model, planner, sim


def missions_dir(home: Path | None = None) -> Path:
    """Папка миссий DCS: <Saved Games>\\DCS*\\Missions (первая найденная), иначе ./missions."""
    sg = (home or Path.home()) / "Saved Games"
    found = sorted(sg.glob("DCS*/Missions"))
    return found[0] if found else Path("missions")


def _ask(prompt: str, default: str = "") -> str:
    s = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return s or default


def _status(st: dict) -> None:
    from .__main__ import status
    print(status(st))


def _new() -> Path:
    name = _ask("Файл кампании", "campaign.json")
    side = _ask("Сторона (red/blue)", "red")
    seed = _ask("Seed (пусто - случайный)", "")
    variant = _ask("Вариант сценария (пусто - случайный)", "")
    st = model.new_campaign(Path(name).stem, player_side=side, seed=int(seed) if seed else None, variant=variant or None)
    model.save(st, Path(name))
    _status(st)
    return Path(name)


def run(path: Path | None = None, out_dir: Path | None = None) -> int:
    if path is None or not path.is_file():
        print("Кампании нет - создаём новую.")
        path = _new()
    while True:
        st = model.load(path)
        print(f"\n=== {st['name']}: день {st['day']}, вылетов {st['sortie']} ===")
        print("1 - статус   2 - план дня   3 - собрать миссию   4 - дебриф вылета   5 - конец дня   6 - новая кампания   0 - выход")
        c = _ask("Выбор", "")
        try:
            if c == "0":
                return 0
            if c == "1":
                _status(st)
            elif c == "2":
                if not planner.plan(st):
                    print(f"Задач нет: {st['task_reason']}")
                else:
                    for i, t in enumerate(st["tasks"], 1):
                        print(f"{i}. {t['title']} - {t['distance_km']:.0f} км; группы: {', '.join(g['group'] for g in t['package'])}")
                model.save(st, path)
            elif c == "3":
                if not st.get("tasks"):
                    planner.plan(st)
                n = int(_ask("Номер задачи", "1"))
                fly = _ask("В какой группе летите", "strike")
                out = (out_dir or missions_dir()) / f"redfront_{path.stem}_day{st['day']}.miz"
                man = build_mod.build(st, out, fly=fly, task_no=n)
                print(f"Миссия: {man['file']}")
                for ln in man["package_lines"]:
                    print(f"  {ln}")
                model.save(st, path)
            elif c == "4":
                f = debrief.find_file(st)
                print(f"Файл дебрифа: {f}")
                for ln in debrief.apply(st, debrief.read(f)):
                    print(ln)
                model.save(st, path)
            elif c == "5":
                for ln in sim.end_day(st):
                    print(ln)
                model.save(st, path)
            elif c == "6":
                path = _new()
        except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:
            print(f"Ошибка: {e.args[0] if e.args else e}")

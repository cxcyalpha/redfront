"""Проверка "сценарий против истории": прогон исторических кампаний без игрока (модель за обе стороны) на несколько
seed и сравнение с контрольными датами реального хода. Нужна после любой правки баланса (бой, марш, авиация,
доктрины): модель не должна незаметно уйти от истории.

Контрольная точка:
  ("take", пункт, сторона, с суток, по сутки) - сторона впервые занимает пункт в этот промежуток (сутки 1 - дата начала);
  ("never", пункт, сторона)                   - за прогон сторона пункт не занимает;
  ("hold", пункт, сторона, до суток)           - пункт у стороны до этих суток включительно.
Точка проходит, если так вышло в большинстве прогонов (PASS_SHARE). Даты - по открытым источникам (в описании точки).

Запуск: python tools/history_check.py [кампания ...] [--seeds N]   (код возврата 1 - есть непройденные точки)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redfront import model, ops, planner, sim  # noqa: E402

PASS_SHARE = 0.5
SEEDS = 3

CHECKS = {
    # Кавказ, 08.08.2008: Цхинвали - 9-10.08, Зугдиди и Сенаки - 11-12.08, Гори - 13.08 (после прекращения огня
    # 12.08 - выход к Гори и Поти), на Тбилиси, Мцхету и через Военно-Грузинскую дорогу не шли
    "caucasus": {"days": 10, "checks": [
        ("take", "Tskhinvali", "red", 1, 3, "Цхинвали - 9-10 августа"),
        ("take", "Zugdidi", "red", 3, 7, "Зугдиди - 11-12 августа"),
        ("take", "Senaki", "red", 3, 7, "Сенаки - 11-12 августа"),
        ("take", "Gori", "red", 4, 7, "Гори - 13 августа"),
        ("never", "Tbilisi", "red", "Тбилиси не брали"),
        ("never", "Mtskheta", "red", "Мцхету не брали"),
        ("never", "Kazbegi", "red", "через Военно-Грузинскую дорогу не наступали"),
        ("never", "Kutaisi", "red", "Кутаиси не брали"),
    ]},
    # Абхазия, 16.09.1993: Сухуми - 27.09, к 30.09 - Очамчира, Гали, выход на Ингури
    "abkhazia": {"days": 16, "checks": [
        ("hold", "Sukhumi", "blue", 6, "Сухуми держится первую неделю"),
        ("take", "Sukhumi", "red", 8, 14, "Сухуми - 27 сентября"),
        ("take", "Ochamchire", "red", 10, 16, "Очамчира - 29-30 сентября"),
        ("never", "Zugdidi", "red", "за Ингури не пошли"),
    ]},
    # Голаны, 06.10.1973: Хермон - 6.10, к 7.10 - у Нафаха; к 10.10 Израиль на "фиолетовой линии", 11-14.10 -
    # наступление к Сасе (Хан-Арнаба, Тель-Шамс)
    "golan73": {"days": 12, "checks": [
        ("take", "Hermon", "red", 1, 2, "Хермон - 6 октября"),
        ("never", "BnotYaakov", "red", "к мосту Бнот-Яаков не вышли"),
        ("never", "ArikBridge", "red", "к мосту Арика не вышли"),
        ("take", "KhanArnabah", "blue", 5, 9, "Хан-Арнаба - 11-12 октября"),
        ("take", "TelShams", "blue", 6, 11, "Тель-Шамс - 12-13 октября"),
    ]},
    # Ливан, 06.06.1982 ("Мир Галилее"): Тир, Набатия - 6-7.06, Сидон - 7-8.06, Джеззин - 8.06, Дамур - 9.06,
    # Айн-Залта, Джуб-Дженнин - 10-11.06, прекращение огня 11.06; Бейрут - осада (не взят), Штора не взята
    "syria": {"days": 7, "checks": [
        ("take", "Tyre", "blue", 1, 2, "Тир - 6-7 июня"),
        ("take", "Nabatieh", "blue", 1, 3, "Набатия - 7 июня"),
        ("take", "Sidon", "blue", 2, 4, "Сидон - 8 июня"),
        ("take", "Jezzine", "blue", 2, 5, "Джеззин - 8 июня"),
        ("take", "Damour", "blue", 3, 5, "Дамур - 9 июня"),
        ("never", "Beirut", "blue", "Бейрут - осада, не взят"),
        ("never", "Chtaura", "blue", "к Шторе не вышли"),
    ]},
    # Синай, 06.10.1973: Кантара - 9.10, Порт-Тауфик - 13.10; перевалы, Таса и Рефидим Египет не взял (14.10 - разгром);
    # Израиль: Девесуар - 16.10, Фаид - 19-20.10, Генейфа - 22.10; Исмаилия и Суэц не взяты
    "sinai73": {"days": 18, "checks": [
        ("take", "QantaraEast", "red", 1, 5, "Кантара-Восток - 9 октября"),
        ("take", "Firdan", "red", 1, 4, "Фирдан - 7-8 октября"),
        ("take", "PortTewfik", "red", 3, 9, "Порт-Тауфик - 13 октября"),
        ("never", "Tasa", "red", "к Тасе не вышли"),
        ("never", "Mitla", "red", "перевал Митла удержан"),
        ("never", "Giddi", "red", "перевал Гидди удержан"),
        ("take", "Deversoir", "blue", 10, 13, "Девесуар (западный берег) - 16 октября"),
        ("take", "Fayed", "blue", 12, 17, "Фаид - 19-20 октября"),
        ("never", "Ismailia", "blue", "Исмаилия не взята"),
        ("never", "Suez", "blue", "Суэц не взят"),
    ]},
    # Ливан, декабрь 1983 (гипотетическая эскалация - проверка правдоподобия): армия Ливана, "Ливанские силы" и морская
    # пехота США при огне кораблей держат Бейрут; полный штурм Сирией - Баабда и Джуния не раньше второй недели
    "lebanon83": {"days": 10, "checks": [
        ("never", "EastBeirut", "red", "Восточный Бейрут не взят"),
        ("never", "BeirutAirport", "red", "аэропорт - у морской пехоты США"),
        ("hold", "Baabda", "blue", 6, "Баабда держится первую неделю"),
        ("hold", "Jounieh", "blue", 6, "Джуния держится первую неделю"),
        ("hold", "SoukElGharb", "blue", 5, "Сук-эль-Гарб держится (в сентябре 1983 выдержал штурм)"),
    ]},
    # Вьетнам, 06.04.1972: Донгха держится до 28.04, Куангчи пал 01.05 (сутки 26); Гиолинь и Кэмп-Кэрролл - у ВНА
    "vietnam72": {"days": 20, "checks": [
        ("never", "DongHa", "red", "Донгха держится до 28 апреля"),
        ("never", "Hue", "red", "Хюэ не взят"),
        ("never", "GioLinh", "blue", "Гиолинь - у ВНА"),
        ("never", "CampCarroll", "blue", "Кэмп-Кэрролл - у ВНА"),
    ]},
}


def run(name: str, seed: int, days: int) -> dict:
    """Прогон: {пункт: {сторона: первые сутки, когда пункт у неё (после начала)}} и владельцы по суткам."""
    st = model.new_campaign("h", sector=f"sector_{name}.json", oob=f"oob_{name}.json", seed=seed, player_side="red")
    first: dict = {}
    owners = []
    prev = {p: ops.owner(st, p) for p in st["places"]}
    for d in range(1, days + 1):
        planner.plan(st)
        sim.end_day(st)
        own = {p: ops.owner(st, p) for p in st["places"]}
        owners.append(own)
        for p, s in own.items():                 # занятие: пункт перешёл к стороне (впервые за прогон)
            if s and s != prev.get(p):
                first.setdefault(p, {}).setdefault(s, d)
        prev = own
    return {"first": first, "owners": owners}


def check(name: str, seeds: int = SEEDS) -> list[tuple[bool, str]]:
    cfg = CHECKS[name]
    runs = [run(name, s, cfg["days"]) for s in range(1, seeds + 1)]
    out = []
    for c in cfg["checks"]:
        kind, place, side = c[0], c[1], c[2]
        ok, got = 0, []
        for r in runs:
            d = r["first"].get(place, {}).get(side)
            if kind == "take":
                got.append(d)
                ok += d is not None and c[3] <= d <= c[4]
            elif kind == "never":
                got.append(d)
                ok += d is None
            elif kind == "hold":
                lost = next((i + 1 for i, o in enumerate(r["owners"]) if o.get(place) != side), None)
                got.append(lost)
                ok += lost is None or lost > c[3]
        passed = ok / len(runs) >= PASS_SHARE
        want = (f"сутки {c[3]}-{c[4]}" if kind == "take" else "никогда" if kind == "never" else f"держит до суток {c[3]}")
        out.append((passed, f"{'OK  ' if passed else 'FAIL'} {name}: {kind} {place} ({side}) - {want}; прогоны: "
                            f"{['-' if g is None else g for g in got]} - {c[-1]}"))
    return out


def main(argv: list[str]) -> int:
    seeds = SEEDS
    if "--seeds" in argv:
        i = argv.index("--seeds")
        seeds = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    names = argv or list(CHECKS)
    bad = 0
    for n in names:
        for passed, line in check(n, seeds):
            print(line)
            bad += not passed
    total = sum(len(CHECKS[n]["checks"]) for n in names)
    print(f"ИТОГ: {total - bad} из {total} контрольных точек")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

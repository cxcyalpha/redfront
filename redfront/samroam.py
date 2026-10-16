"""Смена позиций ЗРК по подвижности и удалению от фронта (все числа - ОЦЕНКИ).

Подвижность - по типам комплекса (DCS): самоходные ближнего действия (Оса, Стрела, Тунгуска, Гепард, Роланд,
Чапарэл) меняют позицию часто, Куб, Бук, Хок - реже, Пэтриот, С-75, С-125, С-200 - редко. Передвигаются только
самостоятельные позиции (не приданные частям - те идут с частью; не объектовая ПВО - fixed).

Чтобы это не выглядело перетасовкой:
  * переезд - с вероятностью p_day класса в сутки, умноженной на близость к фронту: ближе FRONT_NEAR_KM - полностью,
    дальше FRONT_FAR_KM - никогда (в глубоком тылу позиции стоят);
  * после переезда - пауза cooldown суток;
  * новая позиция - в move_km от прежней и не дальше roam_km от исходной (u['anchor']): ЗРК прикрывает свой район,
    а не бродит по карте; к фронту не ближе прежнего.
Вынужденная смена позиции после потерь (раскрыта, logistics.air_defence) - как раньше, отдельно.
"""
from __future__ import annotations

from . import model

FRONT_NEAR_KM = 40
FRONT_FAR_KM = 150
CLASSES = {     # класс: (вероятность в сутки у фронта, пауза суток, переезд км (от, до), район от исходной км)
    "high": (0.5, 1, (3, 6), 12),
    "medium": (0.3, 2, (4, 8), 20),
    "low": (0.08, 5, (5, 10), 25),
}
HIGH = ("Osa", "Strela", "Tunguska", "2S6", "Gepard", "Roland", "Chaparral", "Vulcan", "ZSU", "Rapier", "Tor", "Avenger")
MEDIUM = ("Kub", "Buk", "Hawk", "SA-6", "SA-11")


def mobility(unit: dict) -> str:
    """Класс подвижности позиции - по наименее подвижному комплексу в составе (самый медленный задаёт темп)."""
    order = ["high", "medium", "low"]
    worst = 0
    for c in unit.get("composition", []):
        t = c["type"]
        k = 0 if any(x in t for x in HIGH) else 1 if any(x in t for x in MEDIUM) else 2
        worst = max(worst, k)
    return order[worst]


def front_factor(km: float) -> float:
    if km <= FRONT_NEAR_KM:
        return 1.0
    if km >= FRONT_FAR_KM:
        return 0.0
    return (FRONT_FAR_KM - km) / (FRONT_FAR_KM - FRONT_NEAR_KM)


def daily(state: dict) -> list[str]:
    from . import farp
    lines = []
    for u in state["units"].values():
        if (model.category(u) != "sam" or u.get("fixed") or u.get("attached_to") or "pos" not in u
                or u["state"] in ("destroyed", "pending")):
            continue
        u.setdefault("anchor", dict(u["pos"]))
        p_day, cooldown, (k0, k1), roam = CLASSES[mobility(u)]
        if state["day"] - u.get("moved_day", -99) < cooldown:
            continue
        d_front = farp.front_km(state, u["side"], u["pos"])
        p = p_day * front_factor(d_front)
        r = model.rng(state, f"samroam-{u['id']}-{state['day']}")
        if p <= 0:
            continue
        if r is not None:
            if r.random() >= p:
                continue
        else:                                    # без случайности: накопленная вероятность (переезд, когда набралось 1)
            u["roam_acc"] = u.get("roam_acc", 0.0) + p
            if u["roam_acc"] < 1.0:
                continue
            u["roam_acc"] -= 1.0
        best = None
        for k in range(8):                       # точка в move_km, в своём районе, не ближе к фронту
            brg = (r.uniform(0, 360) if r else 45.0 * k)
            q = model.offset(u["pos"], brg, (r.uniform(k0, k1) if r else k1) * 1000)
            if model.dist_km(q, u["anchor"]) > roam:
                continue
            dq = farp.front_km(state, u["side"], q)
            if dq + 0.5 < min(d_front, FRONT_NEAR_KM):
                continue
            best = q
            break
        if best is None:
            continue
        moved = model.dist_km(u["pos"], best)
        u["pos"] = best
        u["moved_day"] = state["day"]
        lines.append(f"{u['name']}: смена позиции ({moved:.0f} км).")
    return lines

"""Смысл и конец кампании: фазы, ключевые даты, условия завершения и итог. Все пороги - ОЦЕНКИ.

Историческая кампания (model.historical) - историческая фаза до end_day (дата, после которой война на этом театре
закончилась или сменилась: прекращение огня, падение ключевого пункта). В её ходе - ключевые события по датам
(журнал). Кампания завершается:
  * по дате конца исторической фазы (end_day);
  * раньше - если сторона достигла целей своей операции (objectives сектора/варианта) или фронт стороны развалился.
Альтернативный ход (model.influence == 'alternative') исторической кампании после end_day продолжается - "что было
бы дальше": политические ограничения сценария (off_limits, air_limits) для стороны снимаются, если она сильнее
противника в LIFT_RATIO раз; цели операции прежние (у гипотетической кампании ограничения не снимаются). Конец
альтернативного хода и гипотетической кампании (без исторической фазы):
  * цели операции стороны достигнуты (победа);
  * развал фронта: у стороны меньше COLLAPSE_OWN её начальной силы наземных войск и меньше COLLAPSE_RATIO от
    противника - COLLAPSE_DAYS суток подряд;
  * позиционный тупик: STALEMATE_DAYS суток ни один пункт не сменил владельца (перемирие);
  * предел: ALT_DAYS суток после исторической фазы, MAX_DAYS - у гипотетической.
Итог для игрока - по доле выполненных целей операции своей и противника, развалу фронта и пунктам (verdict).
Игрока сценарий не ограничивает: его приказы и свои вылеты - и в запретные районы (последствия - на нём).
"""
from __future__ import annotations

from pathlib import Path

from . import model

LIFT_RATIO = 1.5        # снять политические ограничения - сторона сильнее противника в столько раз (наземные войска)
COLLAPSE_OWN = 0.4      # развал фронта: осталось меньше этой доли своей начальной силы наземных войск
COLLAPSE_RATIO = 0.5    # и сила меньше этой доли от противника
COLLAPSE_DAYS = 2
STALEMATE_DAYS = 4      # позиционный тупик - суток без смены владельцев пунктов
STALEMATE_FROM = 4      # гипотетическая кампания: тупик - не раньше этих суток
ALT_DAYS = 14           # альтернативное продолжение исторической кампании - не дольше
MAX_DAYS = 30           # гипотетическая кампания - не дольше

# Историческая фаза: день 1 - дата начала состава сил. Даты - по открытым источникам (в тексте события).
HISTORY = {
    "oob_caucasus": {"end_day": 9, "end_why": "16.08.2008 - план Медведева-Саркози подписан обеими сторонами",
                     "events": {5: "12.08: президент России объявил о завершении операции по принуждению к миру",
                                6: "13.08: российские части выходят к Гори и Поти (буферная зона)"},
                     "hold": {"blue": ["Tbilisi", "Mtskheta", "Rustavi", "Kutaisi", "Batumi"]},
                     "alt": {"objectives": {"red": ["Mtskheta", "Tbilisi"]},
                             "why": "смена власти в Тбилиси - вариант, от которого Россия отказалась 12.08"}},
    "oob_abkhazia": {"end_day": 15, "end_why": "30.09.1993 - абхазские силы вышли на Ингури, война окончена",
                     "events": {12: "27.09: пал Сухуми", 14: "29.09: оставлена Очамчира"},
                     "hold": {"blue": ["Zugdidi", "Senaki", "Poti"]}},
    "oob_golan73": {"end_day": 18, "end_why": "23.10.1973 - Сирия приняла резолюцию СБ ООН 338, прекращение огня",
                    "events": {2: "07.10: сирийцы у Нафаха, бои в 'Долине слёз'", 5: "10.10: Израиль на 'фиолетовой линии'",
                               6: "11.10: наступление Израиля к Сасе", 8: "13.10: разгром иракской дивизии у Тель-Шамса",
                               17: "22.10: взят Хермон"},
                    "hold": {"blue": ["BnotYaakov", "ArikBridge", "Tiberias", "Safed"], "red": ["Damascus", "Kanaker", "Katana"]},
                    "alt": {"objectives": {"blue": ["Kanaker", "Katana"]},
                            "why": "выход на ближние подступы к Дамаску - Израиль остановился в 40 км, у Сасы"}},
    "oob_sinai73": {"end_day": 19, "end_why": "24.10.1973 - окончательное прекращение огня, 3-я армия Египта окружена",
                    "events": {4: "09.10: оперативная пауза Египта на плацдармах", 9: "14.10: египетское наступление вне "
                               "зонтика ЗРК - разгром", 11: "16.10: Израиль на западном берегу у Девесуара",
                               17: "22.10: первое прекращение огня (резолюция 338)"},
                    "hold": {"blue": ["Tasa", "Refidim", "Mitla", "Giddi"], "red": ["Ismailia", "Suez", "Cairo"]},
                    "alt": {"objectives": {"blue": ["Ismailia", "Suez"]},
                            "why": "штурм Суэца 24.10 отбит, у Исмаилии остановились - что, если бы взяли"}},
    "oob_syria": {"end_day": 6, "end_why": "11.06.1982 12:00 - прекращение огня между Израилем и Сирией",
                  "events": {4: "09.06: 'Медведка 19' - разгром ЗРК в Бекаа", 5: "10.06: бои у Султан-Якуба"},
                  "hold": {"red": ["Beirut", "Chtaura", "Zahle"]},
                  "alt": {"objectives": {"blue": ["Chtaura"]},
                          "why": "перерезать шоссе Бейрут - Дамаск у Шторы: Израиль остановился в нескольких км"}},
    "oob_vietnam72": {"end_day": 26, "end_why": "01.05.1972 - пал Куангчи; фронт стабилизируется на р. Митян",
                      "events": {3: "08.04: ВНА у Донгха", 23: "28.04: оставлен Донгха"},
                      "hold": {"blue": ["Hue", "PhuBai", "DaNang"]},
                      "alt": {"objectives": {"red": ["Hue"]}, "why": "Хюэ - цель ВНА в мае 1972, удержан на р. Митян"}},
    "oob_vietnam72_lb2": {"end_day": 12, "end_why": "29.12.1972 - конец 'Лайнбэкера-2', Ханой возвращается к переговорам",
                          "events": {1: "18.12: первый налёт B-52 на Ханой", 9: "26.12: крупнейший налёт (120 B-52)"}},
    "oob_tankerwar88": {"end_day": 1, "end_why": "18.04.1988 - операция 'Богомол' проведена за один день",
                        "events": {}},
}


def history(state: dict) -> dict:
    """Историческая фаза кампании: сценарий (forces 'campaign') сильнее таблицы HISTORY; нет - {}."""
    if not model.historical(state):
        return {}
    own = (state.get("scenario") or {}).get("campaign")
    if own:
        return own
    return HISTORY.get(Path(str(state.get("oob") or "")).stem, {})


def hist_end(state: dict) -> int | None:
    return history(state).get("end_day")


def phase(state: dict) -> str:
    """'historical' - историческая фаза; 'alternative' - продолжение после неё (альтернативный ход) или гипотетическая
    кампания; 'over' - кампания завершена."""
    if state.get("ended"):
        return "over"
    end = hist_end(state)
    if end is not None and state["day"] <= end:
        return "historical"
    return "alternative"


def _objectives(state: dict, side: str) -> list[str]:
    objs = (state.get("objectives") or {}).get(side) or []
    if isinstance(objs, str):
        return [objs]
    if isinstance(objs, dict):
        return [o for l in objs.values() for o in l]
    return list(objs)


def objectives_done(state: dict, side: str) -> tuple[int, int]:
    """(взято, всего) пунктов целей операции стороны."""
    objs = [o for o in dict.fromkeys(_objectives(state, side)) if o in state["places"]]
    return sum(1 for o in objs if state["places"][o].get("side") == side), len(objs)


def hold_list(state: dict, side: str) -> list[str]:
    """Что сторона должна удержать: сценарий (hold), иначе - у стороны без целей операции - цели противника
    (оборона - не дать ему их взять). Без пунктов, куда противник по сценарию не идёт (off_limits)."""
    from . import ops
    off = ops.banned(state, model.enemy(side))  # куда противник по сценарию не идёт - удерживать не заслуга
    h = (history(state).get("hold") or {}).get(side) or ((state.get("scenario") or {}).get("hold") or {}).get(side)
    if h:
        return [p for p in h if p in state["places"] and p not in off]
    if not _objectives(state, side):
        return [o for o in dict.fromkeys(_objectives(state, model.enemy(side))) if o in state["places"] and o not in off]
    return []


def hold_done(state: dict, side: str) -> tuple[int, int]:
    """(удержано, всего) пунктов, которые сторона должна удержать."""
    h = hold_list(state, side)
    return sum(1 for p in h if state["places"][p].get("side") == side), len(h)


def side_value(state: dict, side: str) -> float:
    """Выполнение замысла стороны, 0..1: среднее долей взятых целей операции и удержанных пунктов (что есть)."""
    parts = [d / t for d, t in (objectives_done(state, side), hold_done(state, side)) if t]
    return sum(parts) / len(parts) if parts else 0.0


def _power(state: dict, side: str) -> float:
    from . import ops
    return ops._ground_power(state, side)


def limits_lifted(state: dict, side: str) -> bool:
    """Политические ограничения сценария сняты для стороны: альтернативный ход, историческая фаза позади (у
    исторической кампании) и сторона сильнее противника в LIFT_RATIO раз - "перестаёт оглядываться на политику"
    (транзит, ОМГ, авиация - и в запретные районы; цели операции прежние)."""
    if model.influence(state) != "alternative":
        return False
    end = hist_end(state)
    if end is None or state["day"] <= end:      # гипотетическая кампания: ограничения - сама её постановка (нейтральные
        return False                             # страны, чужая территория) - не снимаются
    if state.get("_lift_day") == state["day"] and side in (state.get("_lift") or {}):   # одно решение на сутки
        return state["_lift"][side]
    foe = _power(state, model.enemy(side))
    ok = foe <= 0 or _power(state, side) / foe >= LIFT_RATIO
    if state.get("_lift_day") != state["day"]:
        state["_lift_day"], state["_lift"] = state["day"], {}
    state["_lift"][side] = ok
    return ok


def verdict(state: dict, reason: str, loser: str | None = None, day: int | None = None) -> dict:
    """Итог кампании для игрока: доли выполненных целей своих и противника, развал фронта."""
    me = state["player_side"]
    foe = model.enemy(me)
    d_me, t_me = objectives_done(state, me)
    d_foe, t_foe = objectives_done(state, foe)
    score = side_value(state, me) - side_value(state, foe)   # цели операции и удержание - обеих сторон
    if loser == foe:
        score += 1.0
    elif loser == me:
        score -= 1.0
    word = ("победа" if score >= 0.5 else "частичный успех" if score >= 0.15 else "ничья" if score > -0.15
            else "частичная неудача" if score > -0.5 else "поражение")
    day = state["day"] - 1 if day is None else day   # итог - по концу прошедших суток
    return {"day": state["day"], "last_day": day, "reason": reason, "verdict": word, "score": round(score, 2),
            "objectives": {me: [d_me, t_me], foe: [d_foe, t_foe]}, "loser": loser,
            "hold": {me: list(hold_done(state, me)), foe: list(hold_done(state, foe))},
            "phase": "historical" if hist_end(state) and day <= hist_end(state) else "alternative"}


def daily(state: dict) -> list[str]:
    """Новые сутки (после state['day'] += 1): ключевое событие даты; проверка конца кампании (state['ended'])."""
    lines = []
    h = history(state)
    day = state["day"]
    ev = (h.get("events") or {}).get(day) or (h.get("events") or {}).get(str(day))
    if ev and phase(state) == "historical":
        lines.append(f"Событие: {ev}.")
    if state.get("ended"):
        return lines
    prev = day - 1                               # прошедшие сутки - итог по их концу
    end = h.get("end_day")
    # счётчики: развал фронта и тупик
    owners = {p: q.get("side") for p, q in state["places"].items()}
    last = state.get("_end_owners")
    state["_end_owners"] = owners
    st_days = (state.get("_stalemate", 0) + 1) if last is not None and last == owners else 0
    if end is not None and prev <= end:          # тупик альтернативного хода - считается после исторической фазы
        st_days = 0
    state["_stalemate"] = st_days
    loser = None
    p0 = state.setdefault("_power0", {s: _power(state, s) for s in model.SIDES})   # сила на начало кампании
    for side in model.SIDES:
        foe_p, own_p = _power(state, model.enemy(side)), _power(state, side)
        weak = (p0.get(side, 0) > 0 and own_p / p0[side] < COLLAPSE_OWN    # потеряла большую часть своих сил
                and foe_p > 0 and own_p / foe_p < COLLAPSE_RATIO)           # и противник намного сильнее
        k = f"_collapse_{side}"
        state[k] = (state.get(k, 0) + 1) if weak else 0
        if state[k] >= COLLAPSE_DAYS:
            loser = side
    winner = next((s for s in model.SIDES if objectives_done(state, s)[1] and
                   objectives_done(state, s)[0] >= objectives_done(state, s)[1]), None)
    side_ru = lambda s: "красных" if s == "red" else "синих"
    reason = None
    if loser:
        reason = (f"фронт {side_ru(loser)} развалился (осталось меньше {COLLAPSE_OWN:.0%} сил, вдвое слабее противника)")
    elif winner and not (end is not None and prev == end and model.influence(state) == "alternative"
                         and (history(state).get("alt") or {}).get("objectives", {}).get(winner)):
        reason = f"цели операции {side_ru(winner)} достигнуты"
    elif end is not None and prev >= end and model.influence(state) == "historical":
        reason = f"историческая фаза окончена: {h.get('end_why', 'дата сценария')}"
    elif end is not None and prev >= end + ALT_DAYS:
        reason = f"альтернативный ход: {ALT_DAYS} суток после исторической даты - перемирие"
    elif end is None and prev >= int((state.get("scenario") or {}).get("max_days") or MAX_DAYS):
        reason = "предел кампании - перемирие"
    elif st_days >= STALEMATE_DAYS and (end is None and prev >= STALEMATE_FROM or end is not None and prev > end):
        reason = f"позиционный тупик - {st_days} суток без изменений на фронте, перемирие"
    if end is not None and prev == end and model.influence(state) == "alternative" and not reason:
        lines.append(f"Историческая фаза окончена ({h.get('end_why', '')}). Дальше - альтернативный ход: "
                     "война продолжается, пока стороны не добьются целей, фронт не развалится или не наступит тупик.")
        lines += start_alternative(state)
    if reason:
        state["ended"] = verdict(state, reason, loser, prev)
        e = state["ended"]
        lines.append(f"КАМПАНИЯ ЗАВЕРШЕНА (сутки {prev}): {reason}. Итог для игрока - {e['verdict']}; цели: "
                     + ", ".join(f"{side_ru(s)} {d}/{t}" for s, (d, t) in e["objectives"].items() if t)
                     + ("; удержано: " + ", ".join(f"{side_ru(s)} {d}/{t}" for s, (d, t) in e["hold"].items() if t)
                        if any(t for _d, t in e["hold"].values()) else "") + ".")
    return lines


def start_alternative(state: dict) -> list[str]:
    """Начало альтернативного хода: новые цели операции сторон (alt.objectives сценария) вместо выполненных или
    невыполненных исторических, сторона с новыми целями - в наступление; эти пункты для неё - не запретные."""
    if state.get("alt_started"):
        return []
    state["alt_started"] = state["day"]
    alt = history(state).get("alt") or {}
    lines = []
    for side, objs in (alt.get("objectives") or {}).items():
        objs = [o for o in objs if o in state["places"]]
        if not objs:
            continue
        state.setdefault("objectives", {})[side] = objs
        state.setdefault("posture_days", []).append({"from_day": state["day"], side: "offense"})
        lines.append(f"Альтернативный ход - новые цели {'красных' if side == 'red' else 'синих'}: {', '.join(objs)}"
                     + (f" ({alt['why']})" if alt.get("why") else "") + ".")
    return lines


def alt_targets(state: dict, side: str) -> set[str]:
    """Пункты - цели альтернативного хода стороны (для неё не запретные)."""
    if not state.get("alt_started"):
        return set()
    return set(((history(state).get("alt") or {}).get("objectives") or {}).get(side) or [])


def resume(state: dict) -> str:
    """Продолжить завершённую кампанию: историческая фаза окончена - в альтернативном ходе (настройка influence);
    иначе - отказ."""
    e = state.get("ended")
    if not e:
        return "Кампания не завершена."
    if not e["reason"].startswith("историческая фаза окончена"):
        raise ValueError(f"кампания завершена ({e['reason']}) - продолжить нельзя, только новая")
    state.setdefault("settings", {})["influence"] = "alternative"
    state.pop("ended")
    extra = start_alternative(state)
    return "Кампания продолжается в альтернативном ходе: что было бы дальше." + (" " + " ".join(extra) if extra else "")

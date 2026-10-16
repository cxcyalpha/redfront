"""Туман войны для игрока: что он знает о противнике - журнал разведки state['intel'] (все числа - ОЦЕНКИ).

Запись по части противника: {'pos', 'day', 't' (с от начала кампании), 'src', 'state', 'strength'} - где, когда и
какой её видели последний раз.
Отслеживаются наземные части противника (кроме приданной ПВО - она с частью) и самостоятельные позиции ЗРК и КРУ
(объектовая ПВО стоит - её положение известно).

Источники:
  * начало кампании - разведка мирного времени: известны все части и позиции на местах (выдвигающиеся из глубины -
    нет, пока их не увидят);
  * соприкосновение - части противника в бою с нашими или ближе CONTACT_KM к нашим частям в поле и к нашим пунктам
    у фронта - видны всегда (обновляются при планировании, в конце суток, после дебрифа);
  * вылет игрока - ЗРК не дальше SEEN_KM, наземные части не дальше SEEN_GROUND_KM от маршрутов его пакета;
  * разведывательные вылеты (recon.py).

Давность - уровень знания: до EXACT_H часов - точно (знак, номер, боеспособность), до APPROX_H - примерно (знак
пунктиром, "?", место с ошибкой: часть могла уйти на UNC_KMH км/ч), старше - только присутствие. На карте, в целях
задач игрока (удар - туда, где видели), в итогах ударов своих ИИ по устаревшим данным (freshness). Миссия ставит
противника туда, где он на самом деле. Противник планирует по настоящему положению наших (туман - только для игрока).
"""
from __future__ import annotations

from . import model

STALE_DAYS = 2      # ОЦЕНКА: ЗРК - данные старше - "уточнить" (на карте бледно)
SEEN_KM = 60        # ОЦЕНКА: ЗРК не дальше этого от маршрутов пакета игрока - видели в вылете (СПО, визуально)
SEEN_GROUND_KM = 15  # ОЦЕНКА: наземные части не дальше этого от маршрутов пакета игрока - видели в вылете
CONTACT_KM = 10     # ОЦЕНКА: войсковая разведка и наблюдение у линии соприкосновения
EXACT_H = 12        # ОЦЕНКА: данные моложе - точно
APPROX_H = 48       # ОЦЕНКА: моложе - примерно, старше - только присутствие
DR_H = 18           # ОЦЕНКА: счисление пути колонны (маршрут и скорость известны) держится столько часов после наблюдения
UNC_KMH = 1.2       # ОЦЕНКА: на сколько км в час часть могла уйти от места, где её видели (~30 км в сутки)
DAY_S = 86400


def now(state: dict) -> float:
    return (state["day"] - 1) * DAY_S + max(state.get("clock_s") or 0, state.get("ground_s") or 0)


def tracked_sam(state: dict, u: dict) -> bool:
    return (u["side"] != state["player_side"] and model.category(u) in ("sam", "gci") and not u.get("attached_to")
            and not u.get("fixed") and "pos" in u)


def tracked_ground(state: dict, u: dict) -> bool:
    return u["side"] != state["player_side"] and model.category(u) == "ground" and not u.get("attached_to")


def tracked(state: dict, u: dict) -> bool:
    return tracked_sam(state, u) or tracked_ground(state, u)


def _rec(state: dict, uid: str) -> dict | None:
    return (state.get("intel") or {}).get(uid)


def seen(state: dict, uid: str, src: str = "") -> None:
    u = state["units"].get(uid)
    if u and tracked(state, u) and u["state"] not in ("destroyed", "pending"):
        state.setdefault("intel", {})[uid] = {"pos": dict(model.unit_pos(state, u)), "day": state["day"], "t": now(state),
                                               "src": src, "state": u["state"], "strength": round(model.strength(u), 2)}


def ensure(state: dict) -> None:
    """Разведка мирного времени: в начале кампании известны все части и позиции на местах."""
    intel = state.setdefault("intel", {})
    for u in state["units"].values():
        if tracked_sam(state, u) and u["id"] not in intel and u["state"] != "pending":
            seen(state, u["id"], "разведка мирного времени")
        elif tracked_ground(state, u) and u["id"] not in intel and u["state"] != "pending" \
                and not state.get("_intel_ground"):    # один раз: новая кампания (и старое сохранение - при загрузке)
            seen(state, u["id"], "разведка мирного времени")
    state["_intel_ground"] = True


def age_h(state: dict, uid: str) -> float | None:
    r = _rec(state, uid)
    if not r:
        return None
    return max(0.0, (now(state) - r.get("t", (r["day"] - 1) * DAY_S)) / 3600.0)


def level(state: dict, uid: str) -> str | None:
    """exact - точно, approx - примерно, presence - только присутствие, None - неизвестно."""
    a = age_h(state, uid)
    if a is None:
        return None
    return "exact" if a <= EXACT_H else "approx" if a <= APPROX_H else "presence"


def unc_km(state: dict, uid: str) -> float:
    """Куда часть могла уйти с места, где её видели: стоящие (оборона) - медленнее."""
    a = age_h(state, uid) or 0.0
    u = state["units"].get(uid) or {}
    k = UNC_KMH if u.get("state") == "march" else UNC_KMH * 0.4
    return min(80.0, a * k)


def known_pos(state: dict, u: dict) -> dict | None:
    """Где игрок думает, что часть стоит (свои и неотслеживаемые - где стоит); неизвестна - None."""
    if tracked(state, u):
        r = _rec(state, u["id"])
        if r:
            return r["pos"]
        return None if tracked_ground(state, u) else model.unit_pos(state, u)
    return model.unit_pos(state, u)


def aim_pos(state: dict, u: dict) -> dict | None:
    """Куда лететь к цели стороне игрока: колонна, замеченная на марше не раньше DR_H часов назад, - счисление по её
    движению (где она должна быть сейчас: дорога и скорость известны); иначе - где её видели."""
    if tracked_ground(state, u):
        r = _rec(state, u["id"])
        if r and r.get("state") == "march" and u["state"] == "march" and (age_h(state, u["id"]) or 0) <= DR_H:
            return model.unit_pos(state, u)
    return known_pos(state, u)


def can_target(state: dict, u: dict) -> bool:
    """Цель для задачи стороны игрока: известна; колонна на марше - только по свежим данным (через сутки её там
    нет), стоящая - и по примерным."""
    if not tracked_ground(state, u):
        return True
    lv = level(state, u["id"])
    return lv == "exact" or (lv == "approx" and u.get("state") != "march")


def freshness(state: dict, u: dict) -> float:
    """Множитель успеха удара по данным разведки: свежие - 1, примерные - 0.6, только присутствие - 0.3."""
    if not tracked_ground(state, u):
        return 1.0
    return {"exact": 1.0, "approx": 0.6, "presence": 0.3}.get(level(state, u["id"]) or "", 0.2)


def update(state: dict) -> list[str]:
    """Соприкосновение: части противника в бою с нашими или ближе CONTACT_KM к нашим частям в поле и к нашим пунктам
    у линии фронта - видны."""
    from . import ops
    own = [model.unit_pos(state, x) for x in ops._maneuver(state, state["player_side"])]
    g = ops.graph(state) if state.get("links") else {}
    own += [state["places"][p] for p in g if state["places"][p].get("side") == state["player_side"]
            and any(state["places"][q].get("side") != state["player_side"] for q in g[p])]
    n = 0
    for u in state["units"].values():
        if not tracked_ground(state, u) or u["state"] in ("destroyed", "pending"):
            continue
        pos = model.unit_pos(state, u)
        engaged = u["state"] == "battle" and any(state["units"].get(f, {}).get("side") == state["player_side"]
                                                 for f in u.get("engaged", []))
        if engaged or any(model.dist_km(pos, q) <= CONTACT_KM for q in own):
            if level(state, u["id"]) != "exact":
                n += 1
            seen(state, u["id"], "соприкосновение")
    return [f"Разведка: в соприкосновении уточнены части противника: {n}."] if n else []


def after_debrief(state: dict, man: dict) -> list[str]:
    """Вылет игрока: ЗРК противника не дальше SEEN_KM, наземные части не дальше SEEN_GROUND_KM от маршрутов его
    пакета (бывшие в миссии) - видели."""
    from . import planner
    lines = []
    legs = []
    for pg in (state.get("task") or {}).get("package") or []:
        pts = [state["airbases"][pg["base"]]] + list(pg["route"])
        legs += list(zip(pts, pts[1:]))
    n_ground = 0
    for g in man.get("ground") or []:
        u = state["units"].get(g["unit"])
        if not u or not tracked(state, u) or u["state"] in ("destroyed", "pending"):
            continue
        pos = model.unit_pos(state, u)
        lim = SEEN_KM if tracked_sam(state, u) else SEEN_GROUND_KM
        if legs and min(planner._seg_dist_km(pos, a, b) for a, b in legs) > lim:
            continue
        old = _rec(state, u["id"])
        if tracked_sam(state, u) and old and model.dist_km(old["pos"], pos) > 0.5:
            lines.append(f"Разведка: {u['name']} - новая позиция ({model.dist_km(old['pos'], pos):.0f} км от известной).")
        if tracked_ground(state, u):
            n_ground += 1
        seen(state, u["id"], "вылет")
    if n_ground:
        lines.append(f"Разведка: в вылете замечены части противника: {n_ground}.")
    return lines + update(state)

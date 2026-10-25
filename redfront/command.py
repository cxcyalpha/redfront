"""Режим командующего: правка плана полётов своей стороны (ATO) до вылета.

Что можно: снять вылет (любой, в том числе дежурство и перевозку); у вылета задачи - перенести время на объекте,
сменить у группы часть-исполнителя, число бортов и подвеску (подвеска DCS Retribution или по задаче автоматически);
поставить вылет из задач, которые планировщик нашёл, но в план не взял (лимиты плана ato.ATO_MAX_TASKS / ATO_PER_KIND).
Править можно только вылеты своей стороны, ещё не взлетевшие (взлёт не раньше часов кампании) и не слетанные.

Самолёты проверяются по всему плану стороны, как при его построении (ato._Pool): у части должно хватать самолётов на
всё время вылета плюс подготовку к повторному (turnaround_min); ночью летят только типы с night (aircraft.json);
часть должна доставать до объектов группы (радиус роли). План противника не правится. Итоги вылетов, которые игрок
не летал, модель считает как обычно (airwar.py и др.) - по новому составу и времени.
"""
from __future__ import annotations

from . import ato, logistics, model, planner

GROUP_MAX = planner.GROUP_MAX


def _turn_s(state: dict, side: str) -> float:
    return model.doctrine(state, side)["sim"].get("turnaround_min", ato.TURNAROUND_MIN) * 60


def _method(state: dict, e: dict) -> str | None:
    return model.doctrine(state, e["side"])["tasks"].get(e["kind"], {}).get("method")


def _busy(state: dict, e: dict) -> dict[str, tuple[float, float, int]]:
    """Самолёты частей, занятые вылетом: (с, по, сколько) - от взлёта до посадки плюс подготовка."""
    turn = _turn_s(state, e["side"])
    lift = _method(state, e) == "airlift"
    out: dict[str, list] = {}
    for g in e["task"]["package"]:
        t = e["times"].get(g["group"])
        if not t:
            continue
        t1 = t["land_s"] + (t["land_s"] - t["takeoff_s"] if lift else 0) + turn   # перевозка: ещё обратный перелёт
        if g["performer"] in out:
            a, b, n = out[g["performer"]]
            out[g["performer"]] = [min(a, t["takeoff_s"]), max(b, t1), n + g["size"]]
        else:
            out[g["performer"]] = [t["takeoff_s"], t1, g["size"]]
    return {k: tuple(v) for k, v in out.items()}


def _pool(state: dict, skip: str | None = None) -> ato._Pool:
    pool = ato._Pool(state)
    for e in state["ato"]["entries"]:
        if e["id"] != skip:
            pool.book(_busy(state, e))
    return pool


def clock(state: dict) -> float:
    return max(state.get("clock_s") or 0, state.get("ground_s") or 0)


def entry(state: dict, eid: str) -> dict:
    a = ato.ensure(state)
    e = next((x for x in a["entries"] if x["id"] == eid), None)
    if e is None:
        raise ValueError(f"нет вылета {eid} в плане полётов")
    return e


def why_locked(state: dict, e: dict) -> str | None:
    """Почему вылет нельзя править (None - можно)."""
    a = state["ato"]
    if e["side"] != state["player_side"]:
        return "план противника не правится"
    if e["id"] in a.get("done", []) or e.get("resolved"):
        return "вылет уже слетан"
    first = min(t["takeoff_s"] for t in e["times"].values())
    if first < clock(state):
        return f"вылет уже начался (взлёт {ato.hhmm(first)}, часы кампании {ato.hhmm(clock(state))})"
    return None


def _check(state: dict, e: dict) -> None:
    why = why_locked(state, e)
    if why:
        raise ValueError(f"{e['title']}: {why}")


def remove(state: dict, eid: str) -> str:
    e = entry(state, eid)
    _check(state, e)
    state["ato"]["entries"] = [x for x in state["ato"]["entries"] if x["id"] != eid]
    return f"Снят вылет: {ato.hhmm(e['tot_s'])} {e['title']}."


def _place(state: dict, e: dict, tot: float, pool: ato._Pool) -> str | None:
    """Время вылета задачи на объекте tot: times по пакету; None - встал, иначе причина."""
    tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
    rel = ato.rel_times(state, tdef, e["task"])
    first = min(x["takeoff_s"] for x in rel.values())
    if tot + first < clock(state):
        return f"взлёт {ato.hhmm(tot + first)} - раньше часов кампании {ato.hhmm(clock(state))}"
    if tot + max(x["land_s"] for x in rel.values()) > ato.DAY_S:
        return "посадка - после конца суток"
    night = ato.is_night(state, tot + first) or ato.is_night(state, tot)
    if night and not ato.night_capable(state, e["task"]):
        return "ночью этот состав не летает (типы без night в aircraft.json)"
    need = ato._need(e["task"], rel, tot, _turn_s(state, e["side"]))
    if not pool.fits(need):
        short = [state["units"][u]["name"] for u, (t0, t1, n) in need.items() if pool.free(u, t0, t1) < n]
        return "не хватает самолётов в это время: " + ", ".join(short)
    e["tot_s"] = tot
    e["times"] = {k: {kk: tot + vv for kk, vv in v.items()} for k, v in rel.items()}
    e["night"] = night
    return None


def parse_hhmm(s: str) -> float:
    try:
        h, m = str(s).strip().split(":")
        h, m = int(h), int(m)
    except ValueError:
        raise ValueError(f"время - ЧЧ:ММ, а не '{s}'") from None
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"время - ЧЧ:ММ, а не '{s}'")
    return h * 3600 + m * 60


def _is_duty(state: dict, e: dict) -> bool:
    return bool(e["ai_only"]) or _method(state, e) in ("orbit", "alert", "airlift")


def _roles(tdef: dict, g: dict) -> list[str]:
    if g["group"] == "strike":
        return list(tdef["performers"])
    sup = next((s for s in tdef.get("support", []) if s["id"] == g.get("support_id", g["group"])), None)
    return list(sup["performers"]) if sup else []


def _reroute(state: dict, tdef: dict, task: dict, g: dict) -> None:
    """Маршрут группы - от новой базы (ИПМ, рубеж ожидания), как при планировании."""
    base = state["airbases"][g["base"]]
    o = g["objective"]
    if o["kind"] in ("column", "site", "point", "search_zone", "flyover") and len(g["route"]) == 2:
        g["route"] = [planner.ip_point(base, g["route"][-1], tdef["ip_offset_km"]), g["route"][-1]]
        if g["group"] == "strike":
            task["ip"] = g["route"][0]
    elif o["kind"] == "sam" and o.get("units") and o["units"][0] in state["units"]:
        g["route"] = [planner.hold_point(state, state["units"][o["units"][0]], base, g)]
    if g["group"] == "strike":
        task["base"], task["performer"] = g["base"], g["performer"]
        task["distance_km"] = round(model.dist_km(base, task["target_pos"]), 1)


def _reaches(state: dict, unit: dict, route: list[dict]) -> bool:
    r = planner.strike_radius_km(unit)
    base = state["airbases"][unit["base"]]
    return r is None or all(model.dist_km(base, p) <= r for p in route)


def loadouts(type_name: str, state: dict | None = None) -> list[str]:
    """Подвески типа на выбор: свои подвески кампании ('my:имя', custom_loadouts) и подвески по задачам ('rt:имя')."""
    from . import dcstypes
    try:
        dcs_id = dcstypes.flying(type_name).id
    except KeyError:
        return []
    own = [f"my:{k}" for k in ((state or {}).get("custom_loadouts") or {}).get(dcs_id, {})]
    rt = [f"rt:{k}" for k, v in (model.load_json("payloads.json").get("types", {}).get(dcs_id) or {}).items() if v["pylons"]]
    return own + rt


def loadout_label(cat: str) -> str:
    """Имя подвески для показа: задача без источника ('Retribution Strike' -> 'Strike'), своя - её имя."""
    name = cat.split(":", 1)[1] if cat[:3] in ("rt:", "my:") else cat
    return name.replace("Retribution ", "")


def pylons(type_name: str) -> list[dict]:
    """Пилоны типа и варианты подвески на каждом (pydcs): [{num, options: [{clsid, name}]}]."""
    from . import dcstypes
    ac = dcstypes.flying(type_name)
    out = []
    for n in sorted(ac.pylons):
        p = getattr(ac, f"Pylon{n}", None)
        opts = sorted({v[1]["clsid"]: v[1]["name"] for k, v in vars(p).items() if not k.startswith("_") and isinstance(v, tuple)}.items(),
                      key=lambda x: x[1]) if p else []
        out.append({"num": n, "options": [{"clsid": c, "name": nm} for c, nm in opts]})
    return out


def save_loadout(state: dict, type_name: str, name: str, pyl: dict) -> str:
    """Своя подвеска кампании: тип -> имя -> пилоны (номер -> CLSID). Пустое имя - ошибка; пустые пилоны - пустые."""
    from . import dcstypes
    name = str(name or "").strip()
    if not name:
        raise ValueError("у подвески должно быть имя")
    ac = dcstypes.flying(type_name)
    valid = {n: {v[1]["clsid"] for k, v in vars(getattr(ac, f"Pylon{n}")).items() if not k.startswith("_") and isinstance(v, tuple)}
             for n in ac.pylons if getattr(ac, f"Pylon{n}", None)}
    pl = {}
    for k, c in (pyl or {}).items():
        if c and int(k) in valid and c in valid[int(k)]:
            pl[str(int(k))] = {"CLSID": c}
    state.setdefault("custom_loadouts", {}).setdefault(ac.id, {})[name] = {"pylons": pl}
    return f"Своя подвеска {type_name} «{name}»: пилонов {len(pl)}."


def effective_loadout(g: dict, type_name: str) -> str:
    """Подвеска, выбранная для группы командующим (loadout_user), иначе первая своя категория списка; '' - по задаче."""
    have = loadouts(type_name)   # своих (my:) тут нет - они только по выбору (loadout_user)
    if g.get("loadout_user"):
        return g["loadout"][0] if g.get("loadout") else ""
    return next((c for c in g.get("loadout") or [] if c in have and not c.startswith("rt:")), "")


def options(state: dict, eid: str) -> dict:
    """Что можно выбрать для вылета: части по группам (роль группы, достают до объектов), подвески их типов."""
    e = entry(state, eid)
    tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
    groups = []
    for g in e["task"]["package"]:
        roles = _roles(tdef, g)
        perfs = []
        for u in state["units"].values():
            if u["side"] != e["side"] or u["role"] not in roles or model.category(u) not in ("air", "heli"):
                continue
            if u["id"] != g["performer"] and not _reaches(state, u, g["route"]):
                continue
            perfs.append({"id": u["id"], "name": u["name"], "type": u["type"], "available": logistics.available(state, u),
                          "base": state["airbases"].get(u["base"], {}).get("name", u["base"]),
                          "loadouts": loadouts(u["type"], state)})
        perfs.sort(key=lambda p: (p["id"] != g["performer"], p["type"], p["name"]))
        groups.append({"group": g["group"], "title": g["title"], "performer": g["performer"], "size": g["size"],
                       "loadout": effective_loadout(g, state["units"][g["performer"]]["type"]), "performers": perfs})
    return {"id": e["id"], "title": e["title"], "tot": ato.hhmm(e["tot_s"]), "duty": _is_duty(state, e),
            "locked": why_locked(state, e), "groups": groups}


def edit(state: dict, eid: str, tot: str | None = None, groups: dict | None = None) -> list[str]:
    """Правка вылета задачи: время на объекте tot ('ЧЧ:ММ') и группы {группа: {performer, size, loadout}}.
    Всё или ничего: не встаёт - вылет остаётся прежним, ValueError с причиной."""
    import copy
    e = entry(state, eid)
    _check(state, e)
    if _is_duty(state, e):
        raise ValueError(f"{e['title']}: дежурство или перевозка - их можно только снять")
    tdef = model.doctrine(state, e["side"])["tasks"][e["kind"]]
    new = copy.deepcopy(e)
    lines = []
    for gname, ch in (groups or {}).items():
        g = next((x for x in new["task"]["package"] if x["group"] == gname), None)
        if g is None:
            raise ValueError(f"нет группы {gname} в вылете")
        if ch.get("performer") and ch["performer"] != g["performer"]:
            u = state["units"].get(ch["performer"])
            if not u or u["side"] != e["side"] or u["role"] not in _roles(tdef, g):
                raise ValueError(f"{g['title']}: эта часть не может выполнять задачу группы")
            g["performer"], g["base"] = u["id"], u["base"]
            _reroute(state, tdef, new["task"], g)
            if not _reaches(state, u, g["route"]):
                raise ValueError(f"{g['title']}: {u['name']} не достаёт до объекта (радиус роли)")
            lines.append(f"{g['title']}: исполнитель {u['name']} ({u['type']}, {state['airbases'][u['base']]['name']}).")
        if ch.get("size") is not None:
            n = int(ch["size"])
            if not 1 <= n <= GROUP_MAX:
                raise ValueError(f"{g['title']}: бортов в группе - от 1 до {GROUP_MAX}")
            if n != g["size"]:
                lines.append(f"{g['title']}: бортов {g['size']} -> {n}.")
                g["size"] = n
        if "loadout" in ch:
            cat = ch["loadout"] or ""
            typ = state["units"][g["performer"]]["type"]
            if cat and cat not in loadouts(typ, state):
                raise ValueError(f"{g['title']}: у {typ} нет подвески '{cat}' (payloads.json)")
            was = effective_loadout(g, typ)
            if cat != was:
                g["loadout"] = [cat] + [c for c in g.get("loadout") or [] if c != cat] if cat else []
                g["loadout_user"] = bool(cat)    # выбор командующего - первым, раньше подвески по виду задачи
                lines.append(f"{g['title']}: подвеска {loadout_label(cat) if cat else 'по задаче'}.")
        if g["group"] == "strike":
            new["task"]["group_size"] = g["size"]
    tot_s = parse_hhmm(tot) if tot else new["tot_s"]
    why = _place(state, new, tot_s, _pool(state, skip=eid))
    if why:
        raise ValueError(f"{e['title']}: {why} - вылет не изменён")
    if tot_s != e["tot_s"]:
        lines.append(f"Время на объекте {ato.hhmm(e['tot_s'])} -> {ato.hhmm(tot_s)}.")
    e.clear()
    e.update(new)
    state["ato"]["entries"].sort(key=lambda x: x["tot_s"])
    return [f"Вылет изменён: {e['title']}."] + lines


def _key(t: dict) -> str:
    return f"{t['kind']}|{t.get('target') or ''}"


def candidates(state: dict) -> list[dict]:
    """Задачи своей стороны, которых нет в плане: всё, что планировщик находит без лимитов плана."""
    a = ato.ensure(state)
    side = state["player_side"]
    have = {_key(e["task"]) for e in a["entries"] if e["side"] == side}
    tasks, _why = planner.plan_side(state, side, max_tasks=99, per_kind=99)
    out = []
    for t in tasks:
        if t.get("ai_only") or _key(t) in have:
            continue
        out.append({"key": _key(t), "title": t["title"], "kind": t["kind"], "km": round(t["distance_km"]),
                    "base": state["airbases"].get(t["base"], {}).get("name", t["base"]),
                    "groups": [f"{g['title']}: {g['size']} x {state['units'][g['performer']]['type']} "
                               f"({state['units'][g['performer']]['name']})" for g in t["package"]]})
    return out


def add(state: dict, key: str, tot: str | None = None) -> list[str]:
    """Поставить вылет задачи key (из candidates) на время tot ('ЧЧ:ММ'); без времени - первое, когда хватает
    самолётов, начиная с часов кампании (шаг ato.SLOT_MIN)."""
    a = ato.ensure(state)
    side = state["player_side"]
    tasks, _why = planner.plan_side(state, side, max_tasks=99, per_kind=99)
    t = next((x for x in tasks if _key(x) == key and not x.get("ai_only")), None)
    if t is None:
        raise ValueError("этой задачи больше нет (обстановка изменилась) - обновите список")
    n = sum(1 for x in a["entries"] if x["id"].startswith(f"{side}-cmd"))
    e = {"id": f"{side}-cmd{n + 1}-{t['kind']}", "side": side, "kind": t["kind"], "title": t["title"], "task": t,
         "tot_s": 0, "times": {}, "ai_only": False}
    pool = _pool(state)
    if tot:
        why = _place(state, e, parse_hhmm(tot), pool)
        if why:
            raise ValueError(f"{t['title']}: {why}")
    else:
        tdef = model.doctrine(state, side)["tasks"][t["kind"]]
        rel = ato.rel_times(state, tdef, t)
        first = min(x["takeoff_s"] for x in rel.values())
        w0, w1 = ato.flying_window(state)
        s = max(clock(state) + 15 * 60, w0) - first
        why = "нет времени до конца суток"
        while s + first < ato.DAY_S:
            why = _place(state, e, s, pool)
            if why is None:
                break
            s += ato.SLOT_MIN * 60
        if why:
            raise ValueError(f"{t['title']}: {why}")
    a["entries"].append(e)
    a["entries"].sort(key=lambda x: x["tot_s"])
    return [f"Поставлен вылет: {ato.hhmm(e['tot_s'])} {e['title']}."]


# ---- перебазирование авиачастей (приказ командующего; выполняется в конце суток) ----
SLOTS_PER_UNIT = {"air": 16, "heli": 12}     # ОЦЕНКА: мест стоянки на часть (как при генерации состава сил)


def _capacity(state: dict, bid: str, cat: str) -> int:
    """Сколько частей класса cat (air, heli) примет аэродром: стоянки / SLOTS_PER_UNIT; площадка - одну вертолётную."""
    from dcs.terrain.germany import Germany
    b = state["airbases"][bid]
    if b.get("kind") == "farp":
        return 1 if cat == "heli" else 0
    ap = Germany().airports.get(b.get("airport") or "")
    if ap is None:
        return 1
    n = sum(1 for s in ap.parking_slots if (s.helicopter if cat == "heli" else s.airplanes))
    return max(1, n // SLOTS_PER_UNIT[cat])


def _at(state: dict, bid: str, cat: str, skip: str = "") -> int:
    return sum(1 for u in state["units"].values() if u["id"] != skip and model.category(u) == cat and u.get("count", 0) > 0
               and (u.get("rebase_to") or u.get("base")) == bid)


def base_options(state: dict, uid: str) -> dict:
    """Куда можно перебазировать свою авиачасть: свои открытые аэродромы (вертолётам - и площадки) с местом."""
    from . import farp
    u = state["units"].get(uid)
    if not u or u["side"] != state["player_side"] or model.category(u) not in ("air", "heli"):
        raise ValueError("перебазировать можно только свою авиачасть")
    cat = model.category(u)
    cur = state["airbases"][u["base"]]
    out = []
    for bid, b in state["airbases"].items():
        if b.get("side") != u["side"] or b.get("state", "open") not in ("open", "active") or bid == u["base"]:
            continue
        if b.get("kind") == "farp" and cat != "heli":
            continue
        cap = _capacity(state, bid, cat)
        here = _at(state, bid, cat, skip=uid)
        if here >= cap:
            continue
        out.append({"id": bid, "name": b["name"], "farp": b.get("kind") == "farp",
                    "front_km": round(farp.front_km(state, u["side"], b)), "km": round(model.dist_km(cur, b)),
                    "free": cap - here,
                    **({"helos": min(u.get("count", 0), farp.capacity(b))} if b.get("kind") == "farp" else {})})
    out.sort(key=lambda x: x["front_km"])
    return {"id": uid, "name": u["name"], "base": cur["name"], "pending": state["airbases"].get(u.get("rebase_to") or "", {}).get("name"),
            "front_km": round(farp.front_km(state, u["side"], cur)), "options": out}


def rebase(state: dict, uid: str, bid: str) -> str:
    """Приказ: перебазировать часть на bid в конце суток (сегодняшние вылеты - с прежнего аэродрома). bid == текущий -
    приказ отменён. Перебазированная командующим часть сама на площадки не выдвигается (farp.py), пока её аэродром цел."""
    opts = base_options(state, uid)
    u = state["units"][uid]
    if bid in (u["base"], "__cancel__"):
        u.pop("rebase_to", None)
        return f"{u['name']}: приказ на перебазирование отменён."
    b = next((o for o in opts["options"] if o["id"] == bid), None)
    if b is None:
        raise ValueError("на этот аэродром нельзя: не свой, закрыт, нет мест или он не для этого типа")
    u["rebase_to"] = bid
    part = (f"; на площадку - передовая группа {b['helos']} из {u['count']} вертолётов, остальные - на {opts['base']}"
            if b.get("helos") is not None and b["helos"] < u.get("count", 0) else "")
    return f"{u['name']}: перебазирование {opts['base']} -> {b['name']} в конце суток ({b['km']} км; до противника {b['front_km']} км{part})."


def apply_rebases(state: dict) -> list[str]:
    """Конец суток: приказы на перебазирование выполнены (аэродром ещё свой и открыт)."""
    lines = []
    for u in list(state["units"].values()):      # передовые группы появляются и уходят в полк по ходу
        if u["id"] not in state["units"]:
            continue
        bid = u.pop("rebase_to", None)
        if not bid:
            continue
        b = state["airbases"].get(bid)
        if not b or b.get("side") != u["side"] or b.get("state", "open") not in ("open", "active"):
            lines.append(f"{u['name']}: перебазирование отменено - аэродром недоступен.")
            continue
        from . import farp
        p = state["units"].get(u.get("parent") or "")
        if p and p["base"] == bid:               # передовая группа - обратно в свой полк
            farp.merge(state, u)
            lines.append(f"{u['name']}: вернулась в полк ({b['name']}).")
            continue
        if farp.is_farp(b) and model.category(u) == "heli":   # на площадку - сколько поместится
            x = farp.detach(state, u, bid)
            x["base_fixed"] = True
            lines.append(f"{x['name']}: перебазирована на {b['name']} ({x['count']} вертолётов"
                         + (f"; полк - {u['count']} на {state['airbases'][u['base']]['name']}" if x is not u else "") + ").")
            continue
        u["base"], u["base_fixed"] = bid, True
        u.pop("home", None)
        lines.append(f"{u['name']}: перебазирована на {b['name']}.")
    return lines

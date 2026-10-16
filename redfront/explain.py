"""Пояснения для игрока: что значит цифра и что даст удар (склады, заводы, мосты, аэродромы, пути подвоза).

Модель считает тыл в тоннах (logistics.py), но голое "562 т/сутки" или крестик на складе ничего не говорит. Здесь -
строки "что это / на что влияет / что даст удар" по тем же формулам, что и модель. О своём - точно, о противнике -
по оценке (ёмкость складов - разведка мирного времени; запас - грубо, по ёмкости и повреждению).
"""
from __future__ import annotations

from . import convoys, logistics, model


def _side_ru(side: str | None) -> str:
    return {"red": "красных", "blue": "синих"}.get(side or "", "")


def _parts(n: int) -> str:
    return f"{n} " + ("часть" if n % 10 == 1 and n % 100 != 11 else "части" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "частей")


def _days(x: float) -> str:
    return "меньше чем на сутки" if x < 1 else f"на ~{x:.0f} сут."


def _t(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def daily_need_t(state: dict, side: str) -> tuple[float, float]:
    """(расход войск стороны в сутки сейчас, то же в обороне), т."""
    from . import ops
    us = ops._maneuver(state, side)
    return (sum(logistics.demand_t(state, u) for u in us), sum(logistics.demand_t(state, u, "defend") for u in us))


def inflow_t(state: dict, side: str) -> float:
    return logistics._rate(state, side, "supply_inflow", logistics.SUPPLY_INFLOW) * logistics._side_base_t(state, side)


def _depot_users(state: dict, d: dict) -> list[dict]:
    """Части стороны, которые берут снабжение с этого склада (в supply_km по своей территории)."""
    from . import ops
    g = ops.graph(state)
    if d.get("place") not in state["places"]:
        return []
    reach = logistics._reach(state, d["side"], [d["place"]], g)
    lim = logistics._sim(state, d["side"])["supply_km"]
    return [u for u in ops._maneuver(state, d["side"]) if reach.get(ops.node_of(state, u), 1e9) <= lim]


def _level_ru(frac: float) -> str:
    return ("почти пуст" if frac < 0.15 else "около четверти" if frac < 0.4 else "около половины" if frac < 0.65
            else "около трёх четвертей" if frac < 0.9 else "полный")


def depot(state: dict, d: dict, viewer: str) -> list[str]:
    own = d["side"] == viewer
    if not logistics.supplies(d):
        return ["Склад, найденный на карте: на снабжение войск в модели не влияет (цель без последствий)."]
    if d.get("state") == "lost":
        return ["Потерян: пункт занят противником."]
    out = []
    logistics.init_depots(state)                 # ёмкость в тоннах - при первом расчёте (как logistics.supply)
    cap = d.get("cap_t") or 0
    if cap <= 0:
        return [f"Запас {logistics.depot_stock(d):.0%}."]
    stock = d.get("stock_t", 0.0)
    dmg = d.get("damage", 0.0)
    users = _depot_users(state, d)
    need = sum(logistics.demand_t(state, u) for u in users)
    lim = logistics._sim(state, d["side"])["supply_km"]
    if own:
        out.append(f"Запас {_t(stock)} т из {_t(cap)} т ({stock / cap:.0%})" + (f"; повреждение {dmg:.0%} - вмещает не больше "
                   f"{_t(cap * (1 - dmg))} т" if dmg > 0 else "") + ".")
    else:
        out.append(f"Ёмкость ~{_t(cap)} т (разведка); запас по оценке - {_level_ru(min(stock / cap if cap else 0, 1 - dmg))}.")
    if users:
        days = stock / need if need > 0 else 99
        out.append(f"Снабжает {_parts(len(users))} в {lim:.0f} км по своей территории: расход ~{_t(need)} т/сутки"
                   + (f", запаса - {_days(days)} без подвоза" if own and need > 0 else "") + ".")
    else:
        out.append(f"Частей в {lim:.0f} км нет - склад сейчас в резерве (снабжает при подходе войск и авиацию).")
    if d.get("_cut"):
        out.append("Отрезан от подвоза из тыла: пополняется только воздухом.")
    rep = logistics._sim(state, d["side"])["repair_depot"] * logistics.industry(state, d["side"])
    out.append(f"{'Удар противника' if own else 'Удар'}: повреждение X% сжигает запас сверх ёмкость x (1 - X) - при 50% останется не больше {_t(cap / 2)} т; "
               f"ремонт ~{rep:.0%} в сутки. Без снабжения части слабее в бою и медленнее на марше.")
    return out


def industry_after(state: dict, side: str, f: dict, dmg: float) -> float:
    """Множитель промышленности стороны, если у завода f будет повреждение dmg."""
    old = f.get("damage", 0.0)
    f["damage"] = dmg
    try:
        return logistics.industry(state, side)
    finally:
        f["damage"] = old


def factory(state: dict, f: dict, viewer: str) -> list[str]:
    side = f["side"]
    fs = [x for x in logistics.objects(state, "factory") if x["side"] == side]
    k = logistics.industry(state, side)
    eff = logistics._sim(state, side).get("industry_effect", 0.0)
    out = [f"Завод {_side_ru(side)} ({len(fs)} в секторе): промышленность стороны сейчас x{k:.2f} - так быстро "
           "ремонтируются склады, мосты, аэродромы и приходят пополнения авиации и экипажей."]
    if f.get("state") == "lost":
        out.append("Потерян: пункт занят противником.")
        return out
    k1 = industry_after(state, side, f, 1.0)
    out.append(f"Удар: этот завод разрушен полностью - x{k:.2f} -> x{k1:.2f} (вклад завода 1/{len(fs)}, влияние "
               f"{eff:.0%}); сам ремонтируется ~{logistics._sim(state, side)['repair_factory']:.0%} в сутки. Эффект - "
               "медленный, на дни вперёд.")
    return out


def bridge(state: dict, b: dict, viewer: str) -> list[str]:
    links = [tuple(l) for l in b.get("links", [])]
    names = ", ".join(f"{a} - {c}" for a, c in links) or "связь не найдена"
    rep = logistics._sim(state, b.get("side") or state["player_side"])["repair_bridge"]
    days = max(1, round(1 / rep)) if rep > 0 else 99
    flows = {}
    for side in model.SIDES:
        for link, t in convoys.link_flows(state, side).items():
            a, c = link.split(">")
            if (a, c) in links or (c, a) in links:
                flows[side] = flows.get(side, 0.0) + t
    out = [f"Мост на связи {names}."]
    if flows:
        out.append("По нему подвоз: " + ", ".join(f"{_side_ru(s)} ~{_t(t)} т/сутки" for s, t in flows.items()) + ".")
    if logistics.is_minor(b):
        out.append(f"Малый мост: разрушенный связь не закрывает - объезд, марш и подвоз медленнее; ремонт ~{days} сут.")
    else:
        out.append(f"Удар: разрушенный мост закрывает связь - войска и подвоз идут в обход (или не идут); ремонт ~{days} сут.")
    return out


def airfield(state: dict, o: dict, viewer: str) -> list[str]:
    bid = o["id"][3:] if o["id"].startswith("af_") else o.get("airbase")
    us = [u for u in state["units"].values() if u.get("base") == bid and model.category(u) in ("air", "heli")]
    n = sum(u.get("count", 0) for u in us)
    dmg = o.get("damage", 0.0)
    rep = logistics._sim(state, o["side"])["repair_airfield"] * logistics.industry(state, o["side"])
    out = [f"Базируется: {_parts(len(us))}, ~{n} ЛА" + (f" ({', '.join(u['name'] for u in us[:3])}"
                                                           + (" ..." if len(us) > 3 else "") + ")" if us else "") + "."]
    if dmg > 0:
        out.append(f"Повреждение {dmg:.0%}: к вылету меньше на столько же (~{int(n * dmg)} ЛА не взлетят).")
    out.append(f"Удар: повреждение X% - доля самолётов, не готовых к вылету; ремонт ~{rep:.0%} в сутки.")
    return out


def obj(state: dict, o: dict, viewer: str) -> list[str]:
    role = o.get("role")
    return {"depot": depot, "factory": factory, "bridge": bridge, "airfield": airfield}.get(role, lambda *a: [])(state, o, viewer)


def route(state: dict, side: str, link: str, t: float) -> list[str]:
    """Участок пути подвоза: что значит поток."""
    total = inflow_t(state, side)
    need_now, need_def = daily_need_t(state, side)
    to = [state["units"][r["depot"]]["name"] for r in convoys.routes(state, side)
          if any(convoys.key(a, b) == link for a, b in zip(r["path"], r["path"][1:])) and r["depot"] in state["units"]]
    out = [f"~{_t(t)} т/сутки - около {t / convoys.TRUCK_T:.0f} грузовиков ({convoys.TRUCK_T:.0f} т) в сутки, "
           f"{t / total:.0%} подвоза {_side_ru(side)} из тыла (~{_t(total)} т/сутки)." if total else f"~{_t(t)} т/сутки."]
    if to:
        out.append("Везёт на: " + ", ".join(to) + ".")
    out.append(f"Для сравнения: войска {_side_ru(side)} расходуют ~{_t(need_now)} т/сутки (в обороне - ~{_t(need_def)}).")
    out.append(f"Удар: удачный удар ИИ - недовоз ~{convoys.INTERDICT_LOSS:.0%} потока (~{_t(t * convoys.INTERDICT_LOSS)} т); "
               f"в миссии на участке ~{convoys.WINDOW_SHARE:.0%} суточного потока, сожжённые машины - недовезённые тонны.")
    return out


def task(state: dict, t: dict) -> list[str]:
    """Цель задачи игрока и что даст удар."""
    units = state["units"]
    tgt = units.get(t.get("target") or "")
    if t["kind"] == "strike_supply_route":
        link = t.get("link") or ""
        foe = model.enemy(t["side"])
        fl = convoys.link_flows(state, foe).get(link, 0.0)
        return route(state, foe, link, fl) if link else []
    if t["kind"] != "airlift" and tgt and tgt.get("role") in ("depot", "factory", "bridge", "airfield"):
        return obj(state, tgt, t["side"])
    if tgt and model.category(tgt) == "sam":
        return [f"Позиция ЗРК: радиус поражения ~{_planner().threat_radius_km(tgt):.0f} км. Удар - потери пусковых и РЛС; "
                "подавленный ЗРК открывает коридор для следующих вылетов."]
    if tgt and model.category(tgt) == "ground":
        from . import intel
        lv = intel.level(state, tgt["id"]) if intel.tracked_ground(state, tgt) else "exact"
        rec = (state.get("intel") or {}).get(tgt["id"]) or {}
        s = model.strength(tgt) if lv == "exact" else rec.get("strength")
        what = {"battle": "в бою с нашими войсками", "march": "на марше", "defend": "в обороне"}.get(tgt.get("state"), "")
        return [f"{tgt['name']}{': ' + what if what else ''}" + (f", боеспособность {'~' if lv != 'exact' else ''}{s:.0%}" if s is not None else "")
                + ("" if lv == "exact" else f" (разведка {intel.age_h(state, tgt['id']):.0f} ч назад)") + ".",
                f"Удар: потери в технике - слабее в бою; при боеспособности ниже "
                f"{model.doctrine(state, tgt['side'])['sim'].get('combat_ineffective_below', 0.5):.0%} часть выходит из боя "
                "и больше не держит фронт (на восстановление)."]
    if t["kind"] == "airlift" and tgt:
        perf = units.get(t["performer"]) or {}
        cargo = logistics.airlift_cargo_t(state, perf) if perf else 0
        n = t["package"][0]["size"]
        need = sum(logistics.demand_t(state, u) for u in _depot_users(state, tgt))
        return ([f"Груз: {n} x {perf.get('type', '')} по ~{cargo:.1f} т = ~{n * cargo:.0f} т на склад за рейс"
                 + (f" - ~{n * cargo / need:.0%} суточного расхода частей у склада (воздухом - только самое срочное)" if need else "") + "."]
                + depot(state, tgt, t["side"])[:-1])
    return []


def _planner():
    from . import planner
    return planner


def damage_effect(state: dict, o: dict, before: float) -> str:
    """Что изменил удар по объекту (повреждение before -> o['damage']) - строка к итогу удара."""
    role = o.get("role")
    own = o.get("side") == state.get("player_side")
    if role == "depot" and o.get("cap_t") and logistics.supplies(o):
        was = o.get("stock_t", 0.0)
        logistics._clip(o)
        burned = was - o.get("stock_t", 0.0)
        if own:
            return f" Сгорело {_t(burned)} т запаса, осталось {_t(o['stock_t'])} т."
        return f" По оценке сгорело ~{_t(burned)} т запаса." if burned >= 1 else " Запас, по оценке, не пострадал (склад был неполон)."
    if role == "factory":
        k1 = logistics.industry(state, o["side"])
        k0 = industry_after(state, o["side"], o, before)
        return f" Промышленность {_side_ru(o['side'])}: x{k0:.2f} -> x{k1:.2f} (ремонт тыла и пополнения)."
    if role == "airfield":
        bid = o["id"][3:] if o["id"].startswith("af_") else ""
        n = sum(u.get("count", 0) for u in state["units"].values() if u.get("base") == bid and model.category(u) in ("air", "heli"))
        if n:
            return f" С аэродрома к вылету ~{int(n * (1 - before))} -> ~{int(n * (1 - o['damage']))} ЛА."
    return ""


def rear(state: dict) -> list[str]:
    """Сводка тыла своей стороны для вкладки "Тыл": что значат тонны."""
    side = state["player_side"]
    ds = [d for d in logistics.objects(state, "depot") if d["side"] == side and logistics.supplies(d)]
    if not ds:
        return []
    logistics.init_depots(state)
    stock = sum(d.get("stock_t", 0.0) for d in ds if d.get("state") != "lost")
    cap = sum(d.get("cap_t", 0) for d in ds) or 1
    need_now, need_def = daily_need_t(state, side)
    inflow = inflow_t(state, side)
    k = logistics.industry(state, side)
    out = [f"Расход войск сейчас ~{_t(need_now)} т/сутки (в обороне ~{_t(need_def)}; бой - 1 т на машину в сутки, марш - "
           "0.5, оборона - 0.2) плюс авиация: ~4 т на самолёто-вылет, 1.5 - на вертолёто-вылет.",
           f"Подвоз из тыла - до ~{_t(inflow)} т/сутки ({inflow / need_def:.1f} x расход в обороне): в обороне склады "
           "наполняются, в наступлении и бою - тают." if need_def else f"Подвоз из тыла - до ~{_t(inflow)} т/сутки.",
           f"Склады: {_t(stock)} т из {_t(cap)} ({stock / cap:.0%}) - это ~{stock / need_now:.0f} сут. нынешнего расхода без подвоза."
           if need_now else f"Склады: {_t(stock)} т из {_t(cap)} ({stock / cap:.0%}).",
           f"Промышленность: x{k:.2f} (ремонт складов, мостов, аэродромов, пополнения авиации; заводы противника - "
           f"x{logistics.industry(state, model.enemy(side)):.2f}).",
           "Часть, получившая меньше нормы, слабее в бою и медленнее на марше (⚠ на карте)."]
    return out

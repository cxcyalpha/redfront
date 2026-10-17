"""Добавить авиаполк в идущую кампанию: из списка исторических допущений или свой (режим командующего).

Исторические допущения - авиачасти других пресетов того же театра (составы сил на другие даты), которых нет в этой
кампании: например, 116-й гв. и 497-й бап (Су-24М) ушли из Германии в июле 1989 - в пресете 1989 их нет, в 1985 и
1987 - есть. Добавленная часть помечена (added: historical / custom) и в описании видно, что это допущение.

Свой полк: название, сторона, роль (по ней планировщик даёт задачи), тип ЛА (любой летательный аппарат pydcs),
число, аэродром своей стороны (вертолётам - и площадка), радиус действия. Экипажи и лётчики - как у всех.
В план полётов часть попадает со следующих суток (план текущих уже составлен).
"""
from __future__ import annotations

import json

from . import dcstypes, model

MAX_COUNT = 72


def _cat(role: str) -> str:
    return model.role_info(role)["category"]


def roles() -> list[dict]:
    return [{"id": k, "title": v["title"], "cat": v["category"]} for k, v in model.roles()["units"].items()
            if v.get("category") in ("air", "heli")]


def types() -> list[dict]:
    """Летательные аппараты pydcs: имя класса (как в составе сил), DCS id, вертолёт ли."""
    from dcs import helicopters, planes
    out = []
    for mod, heli in ((planes, False), (helicopters, True)):
        for k, v in vars(mod).items():
            if isinstance(v, type) and getattr(v, "__module__", "") == mod.__name__ and hasattr(v, "id") and hasattr(v, "pylons"):
                out.append({"id": k, "name": v.id, "heli": heli})
    return sorted(out, key=lambda x: x["name"].lower())


def catalog(state: dict) -> list[dict]:
    """Авиачасти других пресетов театра, которых нет в кампании (исторические допущения)."""
    have = set(state["units"])
    out, seen = [], set()
    for f in sorted(model.DATA.glob("oob_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("theatre") != state.get("theatre"):
            continue
        year = (d.get("preset") or {}).get("year") or d.get("date", "")[:4]
        for u in d.get("units", []):
            if u["id"] in have or u["id"] in seen or u.get("role") not in model.roles()["units"] \
                    or _cat(u["role"]) not in ("air", "heli"):
                continue
            seen.add(u["id"])
            out.append({"id": u["id"], "name": u["name"], "side": u["side"], "type": u["type"], "role": u["role"],
                        "count": u.get("count", 0), "base": u.get("base"), "year": year, "source": u.get("source", ""),
                        "_unit": u})
    return sorted(out, key=lambda x: (x["side"], x["name"]))


def bases(state: dict, side: str, heli: bool) -> list[dict]:
    return sorted(({"id": k, "name": b["name"], "farp": b.get("kind") == "farp"} for k, b in state["airbases"].items()
                   if b.get("side") == side and b.get("state", "open") in ("open", "active")
                   and (heli or b.get("kind") != "farp")), key=lambda x: (x["farp"], x["name"]))


def options(state: dict) -> dict:
    return {"catalog": [{k: v for k, v in c.items() if k != "_unit"} for c in catalog(state)], "types": types(),
            "roles": roles(), "bases": {s: bases(state, s, True) for s in model.SIDES}}


def _finish(state: dict, u: dict) -> dict:
    from . import pilots
    state["units"][u["id"]] = u
    model.init_crews(state)
    pilots.ensure(state, u)
    return u


def add_historical(state: dict, uid: str, base: str | None = None) -> str:
    c = next((x for x in catalog(state) if x["id"] == uid), None)
    if c is None:
        raise ValueError("такой части в списке нет (уже в кампании или не этого театра)")
    u = json.loads(json.dumps(c["_unit"]))
    bs = bases(state, u["side"], _cat(u["role"]) == "heli")
    if not bs:
        raise ValueError("у стороны нет открытого аэродрома")
    ids = {b["id"] for b in bs}
    if base and base not in ids:
        raise ValueError("аэродром не свой или закрыт")
    if not base:                                 # свой аэродром пресета, иначе ближний к нему свой
        if u.get("base") in ids:
            base = u["base"]
        else:
            ref = state["airbases"].get(u.get("base") or "")
            base = min(ids, key=lambda k: model.dist_km(ref, state["airbases"][k])) if ref and "lat" in ref else bs[0]["id"]
    u.update({"base": base, "count0": u.get("count", 0), "added": "historical",
              "source": f"историческое допущение: из пресета {c['year']}; " + u.get("source", "")})
    _finish(state, u)
    return f"{u['name']}: добавлен (историческое допущение, из пресета {c['year']}) на {state['airbases'][base]['name']}, {u['count']} ЛА; в плане - со следующих суток."


def add_custom(state: dict, spec: dict) -> str:
    name = str(spec.get("name") or "").strip()
    side, role, typ, base = spec.get("side"), spec.get("role"), spec.get("type"), spec.get("base")
    if not name:
        raise ValueError("нужно название полка")
    if side not in model.SIDES:
        raise ValueError("сторона - red или blue")
    if role not in model.roles()["units"] or _cat(role) not in ("air", "heli"):
        raise ValueError("роль - одна из авиационных")
    try:
        ac = dcstypes.flying(typ)
    except KeyError as e:
        raise ValueError(str(e)) from None
    from dcs import helicopters
    heli = ac in vars(helicopters).values()
    if heli != (_cat(role) == "heli"):
        raise ValueError("вертолёт - только с вертолётной ролью, самолёт - с самолётной")
    if base not in {b["id"] for b in bases(state, side, heli)}:
        raise ValueError("аэродром не свой, закрыт или площадка для самолёта")
    try:
        count = int(spec.get("count") or 0)
    except ValueError:
        count = 0
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"число ЛА - от 1 до {MAX_COUNT}")
    n = 1
    while f"add_{side}_{n}" in state["units"]:
        n += 1
    tname = next((k for k, v in vars(__import__("dcs").planes).items() if v is ac), None) or \
        next((k for k, v in vars(helicopters).items() if v is ac), typ)
    u = {"id": f"add_{side}_{n}", "name": name, "side": side, "role": role, "base": base, "type": tname,
         "count": count, "count0": count, "added": "custom", "estimate": True,
         "source": "свой полк (добавлен командующим)"}
    try:
        r = float(spec.get("radius") or 0)
    except ValueError:
        r = 0
    if r > 0:
        u["strike_radius_km"] = r
    elif model.role_info(role).get("strike_radius_km") is None and role not in ("awacs", "tanker", "transport", "recon"):
        u["strike_radius_km"] = 150 if heli else 300   # ОЦЕНКА: радиус по умолчанию, если у роли нет
    if spec.get("nation"):
        u["nation"] = spec["nation"]
    _finish(state, u)
    return f"{name}: свой полк добавлен на {state['airbases'][base]['name']} ({count} x {tname}, роль {role}); в плане - со следующих суток."

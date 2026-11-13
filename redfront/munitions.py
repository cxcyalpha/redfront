"""Запас управляемого оружия сторон (глобальная механика, ОЦЕНКИ).

Управляемое оружие расходуется и пополняется; неуправляемые бомбы и НАР не учитываются (их всегда хватает).
Классы (classify): arm_long - дальние ПРР (Х-58, Х-31П, HARM, ALARM), arm_short - ближние ПРР (Х-25МП, Х-28,
Shrike), agm - управляемые ракеты воздух-поверхность, gbu - управляемые бомбы, asm - противокорабельные,
aam_r - ракеты воздух-воздух с радиолокационным наведением, aam_ir - с тепловым.

Запас стороны: state['munitions'][сторона][класс] = {'n': запас, 'per_day': пополнение в сутки}. Начальный - по
числу самолётов стороны и профилю страны (PROFILE: запас на самолёт в 'днях', пополнение - доля), или явно в составе
сил сценария (munitions: {сторона: {класс: [запас, в сутки]}}). Расход:
  * миссия (build.apply): на пилонах группы - управляемое оружие класса, которого нет в запасе, заменяется
    неуправляемым того же пилона (ракеты воздух-воздух - радиолокационные на тепловые, затем снимаются); остальное
    списывается: по земле - всё подвешенное (EXPEND_AG), воздух-воздух - доля (EXPEND_AA);
  * модель (airwar): удар ИИ вне миссии списывает по классу задачи (MODEL_USE).
Пополнение - в конце суток (daily).
"""
from __future__ import annotations

import re

from . import model

CLASSES = {
    "arm_long": r"Kh-58|Kh-31P|AGM-88|HARM|ALARM",
    "arm_short": r"Kh-25MP|Kh-28|AGM-45|Shrike",
    "asm": r"Kh-35|Kh-31A|AGM-84|Harpoon|Exocet|Kormoran|Kh-22|Sea Eagle|C-802|YJ-",
    "gbu": r"KAB|GBU|UPAB|JDAM|Paveway|AGM-154|AGM-62|Walleye|GB-6|LS-6|FT-",
    "agm": r"Kh-2[359]|Kh-59|Kh-38|Kh-66|AGM-65|Maverick|AGM-114|Hellfire|AS-?30|Vikhr|9M1|Ataka|S-25L|AGM-12|Bullpup|HOT|TOW",
    "aam_r": r"R-27(R|ER|EA)|R-77|R-37|R-33|R-40R|R-23R|R-24R|AIM-7|AIM-120|AIM-54|Phoenix|Sparrow|Super 530|MICA.?R|Sky ?Flash|SD-10|PL-12",
    "aam_ir": r"R-73|R-74|R-60|R-13|R-3S|R-27(T|ET)|R-24T|R-40T|AIM-9|Sidewinder|Magic|MICA.?I|Python|Shafrir|PL-[58]",
}
SKIP_RX = r"Fuel|Tank|PTB|Pod|pod|TGP|ECM|Smoke|L-081|Fantasmagoria|Sorbtsiya|LITENING|Pave Penny|LANTIRN|Kopyo|ALQ|Sky-Shadow|BOZ"
BASE = {"arm_long": 1.0, "arm_short": 1.0, "agm": 2.0, "gbu": 2.0, "asm": 1.0, "aam_r": 4.0, "aam_ir": 4.0}   # на самолёт стороны
# профиль страны: (запас - во сколько раз BASE на самолёт, пополнение в сутки - доля начального запаса). ОЦЕНКИ.
PROFILE = {
    "USA": (3.0, 0.08), "Russia": (3.0, 0.06), "USSR": (3.0, 0.06), "Germany": (2.0, 0.05), "UK": (2.0, 0.05),
    "France": (2.0, 0.05), "Israel": (2.0, 0.06), "Syria": (1.5, 0.03), "Egypt": (1.5, 0.03), "Iraq": (1.5, 0.03),
    "Ukraine": (0.6, 0.01), "Iran": (0.5, 0.005), "Georgia": (0.5, 0.01), "Armenia": (0.8, 0.02),
    "Azerbaijan": (1.0, 0.03), "Vietnam": (1.0, 0.03), "default": (1.5, 0.03),
}
EXPEND_AG = 1.0      # ОЦЕНКА: оружие по земле - расходуется всё подвешенное
EXPEND_AA = 0.25     # ОЦЕНКА: ракеты воздух-воздух - пускается часть
MODEL_USE = {        # ОЦЕНКА: расход на самолёт в ударе ИИ вне миссии: группа -> класс
    "sead": ("arm", 2), "kill": ("agm", 2), "strike_sam_site": ("agm", 2), "strike_ew": ("agm", 2),
    "strike_art": ("agm", 1), "strike_ssm": ("agm", 2), "strike_bridge": ("gbu", 1), "strike_ship": ("asm", 1),
}


def classify(name: str) -> str | None:
    if not name or re.search(SKIP_RX, name):
        return None
    for cls, rx in CLASSES.items():
        if re.search(rx, name, re.I):
            return cls
    return None


def init(state: dict, forces: dict | None = None) -> None:
    """Начальный запас и пополнение сторон (по составу сил и профилю страны); явный в сценарии - сильнее."""
    if state.get("munitions"):
        return
    out = {}
    for side in model.SIDES:
        n_air = sum(u.get("count", 0) for u in state["units"].values() if u.get("side") == side and model.category(u) == "air")
        stock_k, day_k = PROFILE.get((state.get("countries") or {}).get(side, ""), PROFILE["default"])
        out[side] = {c: {"n": round(n_air * b * stock_k), "per_day": round(n_air * b * stock_k * day_k, 1),
                         "cap": round(n_air * b * stock_k)} for c, b in BASE.items()}
        for c, v in ((forces or {}).get("munitions") or {}).get(side, {}).items():
            out[side][c] = {"n": v[0], "per_day": v[1], "cap": max(v[0], v[2] if len(v) > 2 else v[0])}
    state["munitions"] = out


def stock(state: dict, side: str, cls: str) -> float:
    return ((state.get("munitions") or {}).get(side) or {}).get(cls, {}).get("n", 1e9) if state.get("munitions") else 1e9


def take(state: dict, side: str, cls: str, n: float) -> float:
    """Списать до n единиц класса; возвращает списанное."""
    st = ((state.get("munitions") or {}).get(side) or {}).get(cls)
    if st is None:
        return n
    got = min(st["n"], n)
    st["n"] = round(st["n"] - got, 2)
    return got


def daily(state: dict) -> list[str]:
    for side, d in (state.get("munitions") or {}).items():
        for st in d.values():
            st["n"] = round(min(st.get("cap", 1e9), st["n"] + st.get("per_day", 0)), 2)   # склады не бездонны
    return []


def _arm_cls(state: dict, side: str, prefer: str) -> str:
    other = "arm_short" if prefer == "arm_long" else "arm_long"
    return prefer if stock(state, side, prefer) >= 1 else other


def model_use(state: dict, side: str, group: str, kind: str, size: int) -> float:
    """Расход в ударе ИИ вне миссии; возвращает долю группы с управляемым оружием (0..1)."""
    use = MODEL_USE.get(group) or MODEL_USE.get(kind)
    if not use or size <= 0:
        return 1.0
    cls, per = use
    if cls in ("agm", "gbu") and ((state.get("loadout_policy") or {}).get(side) or {}).get("ag_unguided"):
        return 1.0                               # сторона по земле бьёт неуправляемым (ВКС 2022) - не списываем
    if cls == "arm":
        cls = _arm_cls(state, side, "arm_long")
    need = size * per
    return take(state, side, cls, need) / need if need else 1.0


def apply(fg, state: dict, side: str, swap, spend: dict | None = None) -> list[str]:
    """Миссия: управляемое оружие на пилонах группы - из запаса стороны; нет - замена (swap(ac, num, name) -> {clsid,
    name} | None: неуправляемое того же пилона или другая ракета). Возвращает строки 'было -> стало'."""
    if not state.get("munitions"):
        return []
    notes, need = [], {}
    for u in fg.units:
        for d in u.pylons.values():
            from . import weapons
            c = classify(weapons.name_of(d.get("CLSID", "")))
            if c:
                need[c] = need.get(c, 0) + 1
    held = (spend or {}).get(side, {})          # уже отдано другим группам этой миссии
    short = {c for c, n in need.items()
             if stock(state, side, c) - held.get(c, 0) < n * (EXPEND_AA if c.startswith("aam") else EXPEND_AG)}
    from . import weapons
    for u in fg.units:
        for num, d in list(u.pylons.items()):
            name = weapons.name_of(d.get("CLSID", ""))
            c = classify(name)
            if c not in short:
                continue
            w = swap(u.unit_type, int(num), name, c)
            if w:
                u.pylons[num] = {"CLSID": w["clsid"]}
            else:
                del u.pylons[num]
            note = f"{name.split(' - ')[0]} -> {(w['name'].split(' - ')[0]) if w else 'снято'} (нет в запасе)"
            if note not in notes:
                notes.append(note)
    for c, n in need.items():                    # к списанию - то, что осталось на пилонах (списывается после миссии)
        if c in short:
            continue
        k = n * (EXPEND_AA if c.startswith("aam") else EXPEND_AG)
        if spend is not None:
            spend.setdefault(side, {})[c] = spend.setdefault(side, {}).get(c, 0) + k
        else:
            take(state, side, c, k)
    return notes

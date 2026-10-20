"""Связь в миссии: частоты групп и каналы радиостанций ЛА игрока.

Сети (ОЦЕНКА, по смыслу документов того времени, частоты условные): тактическая группа (все группы пакета игрока на
одной частоте - слышно ИИ своего пакета), ДРЛО (А-50 / E-3A - его группа на этой частоте), аэродром вылета и посадки
(частоты УВД аэродрома DCS), аварийная. Красные - МВ (Р-862 МиГ-29, Р-863 Ми-8/Ми-24, Р-832 МиГ-21: 100-150 МГц),
синие - ДМВ (ARC-164 F-4E/F-16, ARC-51 UH-1H: 225-400 МГц); у каждой сети - пара частот МВ/ДМВ, станция берёт свою.

Каналы пишутся прямо в радиостанции ЛА игрока в .miz (у кого в DCS каналы: МиГ-29, Ми-8, Ми-24, МиГ-21, F-4E, F-16,
UH-1H...): К1 - тактическая группа, К2 - ДРЛО, К3 - аэродром вылета, К4 - аэродром посадки, К5 - аварийная.
У типов без каналов (FC3: Су-25, А-10А...) частоты - в брифинге.
"""
from __future__ import annotations

GUARD = {"vhf": 121.5, "uhf": 243.0}
BASE = {"vhf": 124.0, "uhf": 250.0}
STEP = 0.5
NETS = 28                                        # частот на сторону в полосе (124-138 / 250-264 МГц)
PRIMARY = {"red": "vhf", "blue": "uhf"}


def band_of(radio: dict) -> str | None:
    """Полоса радиостанции ЛА по её каналам по умолчанию в DCS: МВ, ДМВ или УКВ ЧМ (ниже 100 МГц - не трогаем)."""
    vals = [v for v in radio.get("channels", {}).values() if v]
    if not vals:
        return None
    lo = min(vals)
    return "vhf" if 100 <= lo < 200 else "uhf" if lo >= 200 else None


def net(i: int) -> dict:
    k = i % NETS
    return {"vhf": round(BASE["vhf"] + k * STEP, 3), "uhf": round(BASE["uhf"] + k * STEP, 3)}


def atc(airport) -> dict:
    r = getattr(airport, "atc_radio", None)
    if not r:
        return {}
    return {"vhf": round(r.vhf_high_hz / 1e6, 3), "uhf": round(r.uhf_hz / 1e6, 3)}


def plan(sortie: int, dep_airport, arr_airport) -> dict:
    """Сети миссии: тактическая группа (своя на каждый вылет), ДРЛО (постоянная), аэродромы, аварийная."""
    return {"pkg": net(3 + sortie * 3), "awacs": net(0), "dep": atc(dep_airport), "arr": atc(arr_airport),
            "guard": dict(GUARD)}


CHANNELS = (("pkg", "тактическая группа"), ("awacs", "ДРЛО"), ("dep", "аэродром вылета"), ("arr", "аэродром посадки"),
            ("guard", "аварийная"))
CHANNELS_EN = {"pkg": "package", "awacs": "AWACS", "dep": "departure airfield", "arr": "landing airfield", "guard": "guard"}


def set_presets(unit, nets: dict) -> bool:
    """Каналы К1-К5 радиостанций ЛА игрока (в своей полосе). False - у типа в DCS каналов нет."""
    radio = getattr(unit, "radio", None)
    if not radio:
        return False
    done = False
    for rid, r in radio.items():
        band = band_of(r)
        if not band:
            continue
        for ch, (key, _t) in enumerate(CHANNELS, 1):
            f = (nets.get(key) or {}).get(band)
            if f and ch in r["channels"]:
                unit.set_radio_channel_preset(rid, ch, f)
                done = True
    return done


def card(nets: dict, side: str, channels: bool, lg: str = "ru") -> list[str]:
    """Карточка связи для брифинга."""
    b = PRIMARY[side]
    out = []
    for ch, (key, title) in enumerate(CHANNELS, 1):
        f = nets.get(key) or {}
        if not f:
            continue
        en = lg == "en"
        both = (f"{f['vhf']:.3f} {'VHF' if en else 'МВ'} / {f['uhf']:.3f} {'UHF' if en else 'ДМВ'}"
                if f.get("vhf") and f.get("uhf") else f"{f.get(b, 0):.3f}")
        out.append(((f"Ch{ch} - " if en else f"К{ch} - ") if channels else "") + f"{CHANNELS_EN[key] if en else title}: {both}")
    return out

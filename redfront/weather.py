"""Погода кампании: по суткам, с памятью (сегодняшний тип погоды зависит от вчерашнего), по климату Северо-Германской
низменности для месяца кампании; в миссии - облачность (пресеты DCS), ветер у земли / 2000 / 8000 м, температура,
давление, видимость, туман, осадки. Для брифинга и наколенного планшета - сводка.

Типы погоды (синоптические положения, упрощённо):
  high  - антициклон: ясно или малооблачно, слабый ветер, в холодное время по утрам туман и дымка;
  low   - циклон: сплошная облачность, дождь, сильный ветер с юго-запада;
  front - прохождение фронта: значительная облачность, дождь, ветер западный;
  post  - тыл циклона: кучевая облачность, северо-западный ветер, видимость хорошая.

Климат (CLIMATE) - ОЦЕНКА по многолетним нормам Ганновера (DWD, 1961-1990: средний максимум температуры, дни с
туманом, преобладающий ветер W-SW); вероятности смены типов (TRANS) и все пороги - ОЦЕНКИ, не наблюдения.
"""
from __future__ import annotations

# месяц -> (средний максимум, °C; суточный размах, °C; вероятность утреннего тумана при антициклоне; доля циклонов)
CLIMATE = {
    1: (3, 5, 0.45, 0.55), 2: (4, 6, 0.40, 0.50), 3: (8, 8, 0.30, 0.45), 4: (13, 10, 0.15, 0.40),
    5: (18, 11, 0.10, 0.35), 6: (21, 11, 0.05, 0.35), 7: (23, 10, 0.05, 0.35), 8: (23, 10, 0.10, 0.35),
    9: (19, 9, 0.25, 0.40), 10: (14, 7, 0.40, 0.45), 11: (8, 5, 0.45, 0.55), 12: (4, 4, 0.45, 0.55),
}
TRANS = {          # ОЦЕНКА: вероятность завтрашнего типа погоды при сегодняшнем (циклоны - с поправкой на сезон)
    "high": {"high": 0.65, "front": 0.25, "post": 0.05, "low": 0.05},
    "front": {"low": 0.35, "post": 0.45, "front": 0.10, "high": 0.10},
    "low": {"low": 0.40, "front": 0.30, "post": 0.25, "high": 0.05},
    "post": {"high": 0.45, "front": 0.30, "post": 0.20, "low": 0.05},
}
PRESETS = {        # пресеты облачности DCS по типу погоды
    "high": ["LightScattered1", "LightScattered2", "HighScattered1", "HighScattered2", "HighScattered3", None],
    "post": ["Scattered1", "Scattered2", "Scattered3", "Scattered4", "Scattered5", "Broken1", "Broken3"],
    "front": ["Broken4", "Broken5", "Broken6", "Broken7", "Overcast1", "Overcast3", "OvercastAndRain2"],
    "low": ["Overcast2", "Overcast4", "Overcast5", "Overcast6", "Overcast7", "OvercastAndRain1", "OvercastAndRain3",
            "Broken5", "Broken7", "Broken8"],    # Broken5-8 - облака от земли: низкая облачность 150-500 м
}
WIND = {           # (направление у земли, откуда, °; разброс, °; скорость у земли, м/с: от, до; давление QNH, гПа)
    "high": (90, 120, 1, 4, 1026), "post": (300, 40, 4, 8, 1014),
    "front": (250, 30, 5, 10, 1005), "low": (220, 40, 6, 13, 997),
}
NAMES = {"high": ("антициклон", "high pressure"), "post": ("тыл циклона", "post-frontal"),
         "front": ("прохождение фронта", "frontal passage"), "low": ("циклон", "low pressure")}


def _month(state: dict) -> int:
    import datetime
    y, mo, d = map(int, state["date"].split("-"))
    return (datetime.date(y, mo, d) + datetime.timedelta(days=state["day"] - 1)).month


def day(state: dict, d: int | None = None) -> dict:
    """Погода суток d (по умолчанию - текущих); считается один раз и хранится в кампании (state["weather"])."""
    d = d or state["day"]
    wx = state.setdefault("weather", {})
    if str(d) in wx:
        return wx[str(d)]
    import random
    prev = day(state, d - 1)["type"] if d > 1 else None
    seed = (state.get("scenario") or {}).get("seed", 0)
    r = random.Random(f"wx-{seed}-{state.get('date')}-{d}")   # один seed - одна погода
    mo = _month(state)
    tmax, swing, fog_p, cyc = CLIMATE[mo]
    if prev is None:
        w = {"high": 1 - cyc, "front": cyc * 0.35, "low": cyc * 0.35, "post": cyc * 0.3}
    else:
        w = dict(TRANS[prev])
        k = cyc / 0.45                           # сезон: зимой циклоны чаще
        w["low"] *= k
        w["front"] *= k
    t = r.choices(list(w), weights=list(w.values()))[0]
    preset = r.choice(PRESETS[t])
    wdir0, spread, v0, v1, qnh = WIND[t]
    wdir = (wdir0 + r.uniform(-spread, spread)) % 360
    wspd = r.uniform(v0, v1) * (1.2 if mo in (11, 12, 1, 2, 3) else 1.0)
    tmax = tmax + {"high": 2 if mo in range(4, 10) else -2, "post": -2, "front": 0, "low": 1 if mo in (11, 12, 1, 2) else -2}[t] \
        + r.uniform(-3, 3)
    rain = bool(preset and preset.startswith("OvercastAndRain"))
    base = None
    if preset:                                   # нижняя граница: в пределах пресета, при циклоне - ниже (ОЦЕНКА)
        from dcs.cloud_presets import Clouds
        p = Clouds[preset].value
        lo, hi = max(p.min_base, 150), p.max_base
        k = {"low": 0.12, "front": 0.25, "post": 0.4, "high": 0.5}[t] * r.uniform(0.3, 1.6)
        base = int(round(lo + (hi - lo) * min(k, 0.9), -1))
    out = {"type": t, "preset": preset, "base_m": base, "wind_dir": round(wdir), "wind_mps": round(wspd, 1),
           "qnh_hpa": round(qnh + r.uniform(-6, 6)), "tmax_c": round(tmax), "swing_c": swing,
           "fog": t == "high" and r.random() < fog_p, "rain": rain,
           "vis_km": round(r.uniform(5, 10) if rain else r.uniform(15, 30) if t in ("low", "front") else r.uniform(30, 80))}
    if out["fog"]:
        out["fog_vis_m"] = round(r.uniform(400, 1500), -1)
        out["fog_top_m"] = round(r.uniform(80, 300), -1)
    wx[str(d)] = out
    return out


def at_hour(w: dict, hour: float) -> dict:
    """Температура и туман к часу суток: максимум к 15 ч, минимум к 5 ч; туман рассеивается к 10-11 ч (ОЦЕНКА)."""
    import math
    t = w["tmax_c"] - w["swing_c"] * (1 - math.cos((hour - 15) / 24 * 2 * math.pi)) / 2
    return {"temp_c": round(t), "fog": bool(w.get("fog")) and (hour < 10.5 or hour >= 20)}


def apply(m, state: dict, hour: float) -> dict:
    """Погода суток в миссию pydcs."""
    from dcs import weather as W
    from dcs.cloud_presets import Clouds
    w = day(state)
    h = at_hour(w, hour)
    wx = m.weather
    to = lambda d: (d + 180) % 360               # в файле миссии DCS - куда дует (редактор показывает - откуда)
    wx.wind_at_ground = W.Wind(to(w["wind_dir"]), w["wind_mps"])
    wx.wind_at_2000 = W.Wind(to(w["wind_dir"] + 20), round(w["wind_mps"] * 1.8, 1))   # ОЦЕНКА: с высотой сильнее и правее
    wx.wind_at_8000 = W.Wind(to(w["wind_dir"] + 35), round(w["wind_mps"] * 3.2, 1))
    wx.season_temperature = h["temp_c"]
    wx.qnh = round(w["qnh_hpa"] * 0.750062, 1)   # мм рт. ст.
    wx.visibility_distance = int(w["vis_km"] * 1000)
    wx.turbulence_at_ground = int(min(w["wind_mps"] * 2, 60))   # 0.1 м/с: порывы ~20% ветра (ОЦЕНКА)
    if w.get("preset"):
        p = Clouds[w["preset"]].value
        wx.clouds_preset = p
        wx.clouds_base = cloud_base(w)
    else:
        wx.clouds_preset = None
        wx.clouds_density = 0
    wx.enable_fog = h["fog"]
    if h["fog"]:
        wx.fog_visibility = int(w["fog_vis_m"])
        wx.fog_thickness = int(w["fog_top_m"])
    return {**w, **h}


def cloud_base(w: dict) -> int | None:
    """Нижняя граница облаков, м: в пределах пресета DCS, ближе к нижнему краю при циклоне (ОЦЕНКА)."""
    if not w.get("preset"):
        return None
    if w.get("base_m"):
        return w["base_m"]
    from dcs.cloud_presets import Clouds                 # погода, сохранённая до base_m
    p = Clouds[w["preset"]].value
    lo, hi = max(p.min_base, 300), p.max_base
    k = {"low": 0.1, "front": 0.25, "post": 0.4, "high": 0.5}[w["type"]]
    return int(lo + (hi - lo) * k)


def cover(w: dict) -> str:
    p = w.get("preset") or ""
    return ("SKC" if not p else "OVC" if p.startswith("Overcast") else "BKN" if p.startswith("Broken")
            else "FEW" if p.startswith(("Light", "High")) else "SCT")


def summary(state: dict, hour: float, lg: str = "ru") -> str:
    """Сводка для брифинга и планшета (в духе METAR, с пояснением)."""
    from . import i18n
    w = day(state)
    h = at_hour(w, hour)
    base = cloud_base(w)
    ft = f"{cover(w)}{round(base * 3.281 / 100):03d}" if base else "SKC"
    metar = (f"{w['wind_dir']:03d}{round(w['wind_mps'] * 1.944):02d}KT {('%04d' % w['fog_vis_m']) if h['fog'] else '9999' if w['vis_km'] >= 10 else '%04d' % (w['vis_km'] * 1000)}"
             f"{' FG' if h['fog'] else ' RA' if w['rain'] else ''} {ft} {h['temp_c']:02d} Q{w['qnh_hpa']}")
    L = lambda ru, en: i18n.L(lg, ru, en)
    txt = (L(f"{NAMES[w['type']][0]}; ветер {w['wind_dir']:03d}° {w['wind_mps']:.0f} м/с (на 2000 м - {w['wind_mps'] * 1.8:.0f}); ",
             f"{NAMES[w['type']][1]}; wind {w['wind_dir']:03d}° {w['wind_mps'] * 1.944:.0f} kt (at 2000 m - {w['wind_mps'] * 1.8 * 1.944:.0f}); ")
           + (L(f"облачность {cover(w)}, нижняя граница {base} м", f"clouds {cover(w)}, base {round(base * 3.281, -2):.0f} ft") if base
              else L("ясно", "clear sky"))
           + (L(", дождь", ", rain") if w["rain"] else "")
           + (L(f"; туман, видимость {w['fog_vis_m']} м, верхняя граница {w['fog_top_m']} м",
                f"; fog, visibility {w['fog_vis_m']} m, top {w['fog_top_m']} m") if h["fog"]
              else L(f"; видимость {w['vis_km']} км", f"; visibility {w['vis_km']} km"))
           + L(f"; {h['temp_c']}°C, QNH {w['qnh_hpa']} гПа", f"; {h['temp_c']}°C, QNH {w['qnh_hpa']} hPa ({w['qnh_hpa'] * 0.02953:.2f} inHg)"))
    return f"{metar}\n{txt}"


# Минимумы погоды для вылета (нижняя граница облаков BKN/OVC, м; видимость, м) - ОЦЕНКИ по смыслу наставлений:
# вертолёты - полёт ниже облаков на малой высоте; удар с визуальным поиском цели (бомбы, НАР, пушка, ТВ/лазерные ракеты)
# и фоторазведка - нужна цель под облаками и время на поиск; всепогодные типы (aircraft.json night: РЛС, прицельные
# системы для слепого бомбометания) и задачи в воздухе (истребители, ДРЛО, заправщики, перевозки) - по минимуму аэродрома.
MINIMA = {"heli": (150, 1500), "visual": (600, 5000), "photo": (1000, 5000), "field": (60, 800)}
VISUAL_KINDS = ("column", "site", "point", "escort_lz", "csar", "air_assault", "air_evac")


def conditions(state: dict, t_s: float) -> dict:
    """Погода в момент t_s (с от полуночи текущих суток): нижняя граница облаков (BKN/OVC, иначе None), видимость, м."""
    w = day(state)
    h = at_hour(w, (t_s % 86400) / 3600)
    ceil = cloud_base(w) if cover(w) in ("BKN", "OVC") else None
    vis = w["fog_vis_m"] if h["fog"] else w["vis_km"] * 1000
    return {"ceiling_m": ceil, "vis_m": vis, "fog": h["fog"]}


def rule(state: dict, g: dict) -> str:
    """Какой минимум у группы: heli, photo, visual или field (всепогодный тип / задача в воздухе)."""
    from . import model
    perf = state["units"].get(g["performer"]) or {}
    kind = (g.get("objective") or {}).get("kind")
    if model.category(perf) == "heli":
        return "heli"
    if model.aircraft_info(perf.get("type")).get("night"):
        return "field"
    if kind == "recon":
        return "photo"
    return "visual" if kind in VISUAL_KINDS else "field"


def blocks(state: dict, task: dict, times: dict) -> str | None:
    """Причина отмены вылета по погоде (None - можно): каждая группа - на своём выходе на объект; минимум аэродрома -
    на взлёте. times - время групп (с от полуночи)."""
    if not (state.get("settings") or {}).get("weather_effects", True):
        return None
    for g in task["package"]:
        t = times.get(g["group"])
        if not t:
            continue
        r = rule(state, g)
        for when, mins in ((t.get("takeoff_s", t["objective_s"]), MINIMA["field"]), (t["objective_s"], MINIMA[r])):
            c = conditions(state, when)
            if c["vis_m"] < mins[1]:
                return f"видимость {c['vis_m']:.0f} м" + (" (туман)" if c["fog"] else "")
            if c["ceiling_m"] is not None and c["ceiling_m"] < mins[0]:
                return f"нижняя граница облаков {c['ceiling_m']} м"
    return None

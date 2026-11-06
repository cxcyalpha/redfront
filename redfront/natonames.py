"""Обозначения НАТО для техники противника: пилот стороны с доктриной НАТО (units: imperial - НАТО, США, Израиль)
видит советские ЗРК и самолёты так, как их называли у него - 'Куб' - SA-6, С-75 - SA-2, МиГ-21 - Fishbed.

Только для показа (карта, брифинг, планшет): в модели имена частей не меняются.
"""
from __future__ import annotations

import re

# (образец в русском имени или типе DCS, обозначение НАТО) - первое совпадение заменяется; порядок важен (Стрела-10 до
# Стрела-1, С-125 до С-12...)
SAM = [
    (r"С-300ПС|S-300PS|SA-10", "SA-10 Grumble"), (r"С-200|S-200|SA-5", "SA-5 Gammon"), (r"С-125|S-125|SA-3", "SA-3 Goa"),
    (r"С-75|S-75|SA-2", "SA-2 Guideline"), (r"Бук|Buk|SA-11", "SA-11 Gadfly"), (r"Куб|Kub|SA-6", "SA-6 Gainful"),
    (r"Оса|Osa|SA-8", "SA-8 Gecko"), (r"Стрела-10|Strela-10|SA-13", "SA-13 Gopher"), (r"Стрела-1|Strela-1|SA-9", "SA-9 Gaskin"),
    (r"Стрела-2|SA-7", "SA-7 Grail"), (r"Игла|Igla|SA-18", "SA-18 Grouse"), (r"Тор|Tor\b|SA-15", "SA-15 Gauntlet"),
    (r"Тунгуска|Tunguska|SA-19", "SA-19 Grison"), (r"Шилка|ЗСУ-23-4|ZSU-23-4|ZSU_23_4", "ZSU-23-4 Shilka"),
]
AIR = [
    (r"МиГ-15|MiG-15", "MiG-15 Fagot"), (r"МиГ-17|MiG-17", "MiG-17 Fresco"), (r"МиГ-19|MiG-19", "MiG-19 Farmer"),
    (r"МиГ-21|MiG-21", "MiG-21 Fishbed"), (r"МиГ-23|MiG-23", "MiG-23 Flogger"), (r"МиГ-25|MiG-25", "MiG-25 Foxbat"),
    (r"МиГ-27|MiG-27", "MiG-27 Flogger-D"), (r"МиГ-29|MiG-29", "MiG-29 Fulcrum"), (r"Су-7|Su-7\b", "Su-7 Fitter-A"),
    (r"Су-17|Су-20|Су-22|Su-17|Su-22", "Su-17 Fitter"), (r"Су-24|Su-24", "Su-24 Fencer"), (r"Су-25|Su-25", "Su-25 Frogfoot"),
    (r"Су-27|Su-27", "Su-27 Flanker"), (r"Ми-8|Mi-8", "Mi-8 Hip"), (r"Ми-24|Mi-24", "Mi-24 Hind"), (r"А-50|A-50", "A-50 Mainstay"),
    (r"Ту-16|Tu-16", "Tu-16 Badger"), (r"Ту-22М|Tu-22M", "Tu-22M Backfire"),
]


def western(state: dict, viewer: str) -> bool:
    from . import model
    return model.doctrine(state, viewer).get("units", "metric") == "imperial"


SUFFIX = r"[А-ЯA-Z]{0,3}(?:/[А-ЯA-Z]{1,3})*"   # МиГ-21ПФ/МФ, Су-20М - модификация уходит в обозначение НАТО


def _apply(s: str) -> str:
    """ЗРК - короткое обозначение (SA-6), ЛА - с именем (MiG-21 Fishbed); уже западное - не трогать."""
    for pat, nato in SAM:
        s = re.sub(rf"(?<![\w-])(?:{pat})(?![\w])", nato.split(" ")[0], s)
    for pat, nato in AIR:
        if nato not in s:
            s = re.sub(rf"(?:{pat}){SUFFIX}", nato, s)
    return s


def name(state: dict, unit: dict, viewer: str | None = None) -> str:
    """Имя части для зрителя viewer (по умолчанию - сторона игрока): техника противника западного зрителя - в
    обозначениях НАТО."""
    viewer = viewer or state.get("player_side")
    nm = unit.get("name", "")
    if not viewer or unit.get("side") == viewer or not western(state, viewer):
        return nm
    if _lang(state) == "en":
        return _apply(_en(state, nm))
    out = _apply(nm)
    _register(nm, out)
    return out


def text(state: dict, side_of_text: str, s: str, viewer: str | None = None) -> str:
    """Произвольная строка о технике стороны side_of_text (состав, угрозы) - в обозначениях НАТО для западного зрителя."""
    viewer = viewer or state.get("player_side")
    if not viewer or side_of_text == viewer or not western(state, viewer):
        return s
    if _lang(state) == "en":
        return _apply(_en(state, s))
    out = _apply(s)
    _register(s, out)
    return out


def _lang(state: dict) -> str:
    from . import i18n
    return i18n.lang(state)


def _register(ru: str, out: str) -> None:
    """Русский интерфейс с английским окном (X-Lang): заменённое имя - в переводы на ходу (английское имя + НАТО)."""
    if out != ru:
        from . import i18n_en
        i18n_en.register(out, _apply(i18n_en.en(ru)))


def _en(state: dict, s: str) -> str:
    """Английский интерфейс: сначала перевод русского имени (каталог имён), затем обозначения НАТО - иначе
    заменённое имя ('Батарея SA-6 №2') уже не найдётся в каталоге перевода."""
    from . import i18n
    if i18n.lang(state) != "en":
        return s
    from . import i18n_en
    return i18n_en.en(s)

"""Английский текст окна и миссии из русского текста модели.

Модель пишет журнал, причины планировщика, пояснения целей и имена частей по-русски и хранит их в кампании;
язык выбирается в окне в любой момент. Поэтому перевод - на выходе: ответ окна (gui.App) и тексты миссии
проходят через en() / deep():

1. каталог точных строк (data/i18n/en_names.json - имена частей, пунктов, объектов, названия сценариев;
   en_text.json - готовые фразы);
2. шаблоны фраз с подстановками (data/i18n/en_templates.json: регулярное выражение по-русски -> английский текст;
   подстановки переводятся рекурсивно - имена внутри фраз тоже);
3. составные строки - по разделителям (' · ', '; ', '\\n'), каждая часть отдельно.

Непереведённое остаётся как есть; tools/i18n_check.py прогоняет все сценарии на английском и показывает остаток.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent / "data" / "i18n"
CYR = re.compile("[А-Яа-яЁё]")
SEPS = ("\n", " · ", "; ", " | ", ": ", ", ", " - ", " -> ")
SKIP_KEYS = {"id", "file", "pos", "key", "unit", "uid", "type", "base_id", "livery", "url", "path", "miz", "ato_id"}


@lru_cache(maxsize=1)
def _catalog() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in ("en_names.json", "en_text.json"):
        p = DIR / f
        if p.is_file():
            out.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")})
    from .i18n import TITLES, WAYPOINTS             # названия задач, групп, ролей и точек маршрута (i18n.py)
    for k, v in {**TITLES, **WAYPOINTS}.items():
        out.setdefault(k, v)
    return out


@lru_cache(maxsize=2)
def _templates(late: bool = False) -> list[tuple[re.Pattern, str]]:
    """Шаблоны фраз; late - общие (короткий текст вокруг подстановок): только после разбора по разделителям."""
    p = DIR / "en_templates.json"
    if not p.is_file():
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    return [(re.compile(r[0], re.S), r[1]) for r in rows if isinstance(r, list) and bool(r[2:3] and r[2]) == late]


@lru_cache(maxsize=1)
def _names_rx() -> re.Pattern:
    keys = sorted((k for k in _catalog() if len(k) >= 10 and CYR.search(k) and re.search(r"[\d (]", k)), key=len, reverse=True)
    return re.compile("(?<![А-Яа-яЁё])(?:" + "|".join(map(re.escape, keys)) + ")(?![А-Яа-яЁё])")


def reload() -> None:
    _catalog.cache_clear(); _templates.cache_clear(); _names_rx.cache_clear(); _words.cache_clear(); en.cache_clear()


@lru_cache(maxsize=200_000)
def en(text: str) -> str:
    """Русский текст -> английский (каталог, шаблоны, части). Нет перевода - текст как есть."""
    if not isinstance(text, str) or not CYR.search(text):
        return text
    cat = _catalog()
    if text in cat:
        return cat[text]
    s = text.strip()
    if s != text:
        lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
        return lead + en(s) + trail
    sub = _names_rx().sub(lambda m: cat[m.group(0)], text)   # известные имена внутри фразы (длинные - первыми)
    if sub != text:
        return en(sub)
    r = _apply(text, _templates())
    if r is not None:
        return r
    for sep in SEPS:
        parts = split(text, sep)
        if len(parts) > 1:
            return sep.join(en(p) for p in parts)
    r = _apply(text, _templates(True))
    if r is not None:
        return r
    return people(words(designators(text)))


def _apply(text: str, rows: list) -> str | None:
    for rx, repl in rows:
        m = rx.fullmatch(text)
        if m:
            g = {k: en(v) if v is not None else "" for k, v in m.groupdict().items()}
            def put(mm):
                v = g.get(mm.group(1), mm.group(0))
                if mm.group(2) == "|ord":
                    return ordinal(v)
                if mm.group(2) == "|tr":                  # имя собственное без перевода - транслитерацией
                    return translit(v) if CYR.search(v) else v
                return v
            return re.sub(r"\{(\w+)(\|ord|\|tr)?\}", put, repl).replace("  ", " ").strip()
    return None


@lru_cache(maxsize=1)
def _words() -> tuple[re.Pattern | None, dict]:
    p = DIR / "en_words.json"
    w = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    w = {k: v for k, v in w.items() if not k.startswith("_")}
    if not w:
        return None, {}
    keys = sorted(w, key=len, reverse=True)
    return re.compile("(?<![А-Яа-яЁё])(?:" + "|".join(map(re.escape, keys)) + ")(?![А-Яа-яЁё])"), w


def words(text: str) -> str:
    """Сокращения и отдельные слова (подписи знаков '94 гв. мсд', звания лётчиков)."""
    rx, w = _words()
    return rx.sub(lambda m: w[m.group(0)], text) if rx else text


NAME = re.compile(r"(?<![А-Яа-яЁё])[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)? [А-ЯЁ]\.(?: ?[А-ЯЁ]\.)?")


def people(text: str) -> str:
    """Фамилии и инициалы лётчиков ('Лебедев Г.Г.') - транслитерацией."""
    return NAME.sub(lambda m: translit(m.group(0)), text)


def translit(s: str) -> str:
    return "".join(TRANSLIT.get(c, c) for c in s)


def split(text: str, sep: str) -> list[str]:
    """Разбить по разделителю вне скобок (имена со скобками и запятыми внутри не рвутся)."""
    out, depth, cur, i = [], 0, [], 0
    while i < len(text):
        c = text[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and text.startswith(sep, i):
            out.append("".join(cur)); cur = []; i += len(sep)
            continue
        cur.append(c); i += 1
    out.append("".join(cur))
    return out


def ordinal(n: str) -> str:
    """'94' -> '94th', '1' -> '1st', '22' -> '22nd'."""
    if not n.isdigit():
        return n
    k = int(n)
    suf = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{n}{suf}"


TRANSLIT = dict(zip("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["A", "B", "V", "G", "D", "E", "E", "Zh", "Z", "I", "Y", "K", "L", "M", "N", "O", "P", "R", "S", "T", "U",
                     "F", "Kh", "Ts", "Ch", "Sh", "Shch", "", "Y", "", "E", "Yu", "Ya",
                     "a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                     "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))
DESIG = re.compile(r"(?<![А-Яа-яЁё])(?:[А-ЯЁ][А-Яа-яЁё]{0,4}-\d+[А-Яа-яЁё0-9]*|(?:Оса|Тор|Бук|Куб|Круг|Стрела|Шилка|Тунгуска|Игла)"
                   r"(?:-[А-Яа-я0-9]+)?|бис)(?![А-Яа-яЁё])")


def designators(text: str) -> str:
    """Обозначения техники (МиГ-29, Су-17М4, С-75, ЗСУ-23-4, Оса-АКМ) - латиницей, остальное как есть."""
    tl = lambda m: "".join(TRANSLIT.get(c, c) for c in m.group(0))
    return SLASH.sub(tl, DESIG.sub(tl, text))


SLASH = re.compile(r"(?<=/)[А-ЯЁ]{1,4}(?![А-Яа-яЁё])")   # МиГ-23М/МЛД: вариант после косой черты


def deep(obj, key: str | None = None):
    """Перевод всех строк структуры ответа окна (ключи-идентификаторы не трогаются)."""
    if isinstance(obj, str):
        return obj if key in SKIP_KEYS else en(obj)
    if isinstance(obj, list):
        return [deep(x, key) for x in obj]
    if isinstance(obj, dict):
        return {k: deep(v, k) for k, v in obj.items()}
    return obj


def missing(obj, key: str | None = None, out: set | None = None) -> set[str]:
    """Строки структуры, оставшиеся с кириллицей после перевода (для проверки полноты)."""
    out = set() if out is None else out
    if isinstance(obj, str):
        if key not in SKIP_KEYS and CYR.search(obj):
            out.add(obj)
    elif isinstance(obj, list):
        for x in obj:
            missing(x, key, out)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            missing(v, k, out)
    return out

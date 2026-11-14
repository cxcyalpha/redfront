"""Наколенный планшет (kneeboard) ЛА игрока: страницы-картинки в .miz по типу ЛА (DCS не умеет планшет на группу -
страницы подписаны группой).

Вид - тактическая карточка вылета (как карточки задания lineup card / mission data card): главное крупно и в рамках,
второстепенное - на последних листах.
  1. Карточка вылета: задание и звено; полоса времени (запуск, взлёт, сбор, цель); цель и угрозы; звено (позывной,
     тип, подвеска, старт); связь (таблица каналов); погода (METAR, ветер, облачность, давление); навигация
     (аэродромы вылета и посадки: TACAN, ILS, приводы).
  2. Маршрут: таблица точек (номер, время, высота, скорость, точка) и порядок действий пакета.
  3. Пакет и обстановка (вторично): остальные группы, позывные, полная погода.
Не помещается - продолжение на следующем листе с тем же заголовком; ничего не обрезается.

Картинки рисует Pillow; нет Pillow - миссия без планшета (брифинг остаётся). Шрифт - системный с кириллицей
(Windows: Consolas / Arial, Linux: DejaVu), иначе встроенный.
"""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

W, H = 768, 1024
M = 22                    # поле листа
GAP = 10                  # между рамками
FONTS = ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "LiberationMono-Regular.ttf"]
BOLD = ["consolab.ttf", "courbd.ttf", "DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]
PAPER, INK, DIM, RULE = (246, 243, 232), (18, 18, 18), (95, 95, 95), (120, 112, 95)
BAND, BAND_INK, HEAD, ALERT, ZEBRA = (34, 44, 58), (255, 255, 255), (222, 214, 192), (165, 25, 25), (236, 231, 214)


def _font(names, size):
    from PIL import ImageFont
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


class _Fonts:
    def __init__(self):
        self.title, self.sub = _font(BOLD, 26), _font(FONTS, 16)
        self.big, self.lbl = _font(BOLD, 34), _font(BOLD, 14)
        self.head, self.txt, self.txtb = _font(BOLD, 17), _font(FONTS, 17), _font(BOLD, 17)

    @staticmethod
    def cw(f) -> float:
        return max(7.0, f.getlength("Ж")) if hasattr(f, "getlength") else 9.0


def _wrap(text: str, f, width: float) -> list[str]:
    cols = max(8, int(width / _Fonts.cw(f)))
    return textwrap.wrap(text, cols, subsequent_indent="  ") or [""]


class _Sheet:
    """Лист: шапка; затем блоки сверху вниз; не помещается - новый лист (продолжение)."""

    def __init__(self, kb: "_Book", title: str):
        from PIL import Image, ImageDraw
        self.kb, self.title = kb, title
        self.img = Image.new("RGB", (W, H), PAPER)
        self.d = ImageDraw.Draw(self.img)
        F = kb.F
        self.d.rectangle([0, 0, W, 64], fill=BAND)
        self.d.text((M, 8), title, font=F.title, fill=BAND_INK)
        self.d.text((M, 40), kb.sub, font=F.sub, fill=(205, 210, 220))
        self.y = 64 + GAP

    def room(self, h: int) -> bool:
        return self.y + h <= H - M


class _Book:
    def __init__(self, sub: str, lg: str = "ru"):
        self.F, self.sub, self.sheets, self.lg = _Fonts(), sub, [], lg

    def sheet(self, title: str, cont: bool = False) -> _Sheet:
        s = _Sheet(self, title + ((" (cont.)" if self.lg == "en" else " (продолж.)") if cont else ""))
        s.base = title
        self.sheets.append(s)
        return s

    def cur(self, title: str, need: int) -> _Sheet:
        s = self.sheets[-1] if self.sheets else None
        if s is None or not s.room(need):
            s = self.sheet(title, cont=s is not None and getattr(s, "base", "") == title)
        return s

    # ---- элементы ----
    def times(self, title: str, cells: list[tuple[str, str]]) -> None:
        """Полоса времени: подпись мелко, время крупно; последняя ячейка (цель) - выделена."""
        if not cells:
            return
        F, h = self.F, 66
        s = self.cur(title, h)
        w = (W - 2 * M - GAP * (len(cells) - 1)) / len(cells)
        for i, (lbl, val) in enumerate(cells):
            x = M + i * (w + GAP)
            hot = i == len(cells) - 1
            s.d.rectangle([x, s.y, x + w, s.y + h], fill=(250, 236, 226) if hot else (255, 252, 244),
                          outline=ALERT if hot else RULE, width=3 if hot else 2)
            s.d.text((x + 8, s.y + 5), lbl, font=F.lbl, fill=ALERT if hot else DIM)
            s.d.text((x + 8, s.y + 22), val, font=F.big, fill=ALERT if hot else INK)
        s.y += h + GAP

    def boxes(self, title: str, row: list[tuple[str, list[str]]], widths: list[float] | None = None) -> None:
        """Ряд рамок: заголовок рамки и строки (строка с '!' в начале - красная, с '*' - жирная). Высота ряда - по
        самой длинной рамке; не помещается на лист - на следующий (длинная рамка - режется по строкам)."""
        F = self.F
        widths = widths or [1.0 / len(row)] * len(row)
        inner = W - 2 * M - GAP * (len(row) - 1)
        cols = []
        for (head, lines), fr in zip(row, widths):
            w = inner * fr
            out = []
            for ln in lines or ["-"]:
                style = "alert" if ln.startswith("!") else "bold" if ln.startswith("*") else "txt"
                body = ln[1:] if style != "txt" else ln
                out += [(style, part) for part in _wrap(body, F.txtb if style != "txt" else F.txt, w - 16)]
            cols.append((head, out, w))
        lh, hh = 21, 24
        while any(c[1] for c in cols):
            s = self.cur(title, hh + 2 * lh + 12)
            fit = int((H - M - s.y - hh - 12) / lh)
            n = max(len(c[1]) for c in cols)
            take = min(n, fit)
            h = hh + take * lh + 10
            x = M
            new = []
            for head, out, w in cols:
                s.d.rectangle([x, s.y, x + w, s.y + h], fill=(255, 252, 244), outline=RULE, width=2)
                s.d.rectangle([x, s.y, x + w, s.y + hh], fill=HEAD)
                s.d.text((x + 8, s.y + 3), head, font=F.head, fill=INK)
                yy = s.y + hh + 4
                for style, part in out[:take]:
                    s.d.text((x + 8, yy), part, font=F.txtb if style != "txt" else F.txt,
                             fill=ALERT if style == "alert" else INK)
                    yy += lh
                new.append((head, out[take:], w))
                x += w + GAP
            s.y += h + GAP
            cols = new

    def table(self, title: str, head: str, cols: list[tuple[str, float]], rows: list[list[str]]) -> None:
        """Таблица: колонки (заголовок, доля ширины), строки зеброй; продолжение - с заголовком колонок."""
        F = self.F
        inner = W - 2 * M
        lh, hh = 24, 24
        i = 0
        while i < len(rows) or i == 0:
            s = self.cur(title, hh * 2 + lh * 2)
            y0 = s.y
            s.d.rectangle([M, s.y, W - M, s.y + hh], fill=HEAD)
            s.d.text((M + 8, s.y + 3), head, font=F.head, fill=INK)
            s.y += hh
            x = M
            for name, fr in cols:
                s.d.text((x + 6, s.y + 3), name, font=F.lbl, fill=DIM)
                x += inner * fr
            s.y += 20
            fit = int((H - M - s.y) / lh)
            for r in rows[i:i + fit]:
                if (i % 2) == 0:
                    s.d.rectangle([M, s.y, W - M, s.y + lh], fill=ZEBRA)
                x = M
                for (name, fr), val in zip(cols, r):
                    cw = int(inner * fr / _Fonts.cw(F.txt))
                    alert, bold = val.startswith("!"), val.startswith("*")
                    s.d.text((x + 6, s.y + 3), (val[1:] if alert or bold else val)[:max(3, cw - 1)],
                             font=F.txtb if alert or bold else F.txt, fill=ALERT if alert else INK)
                    x += inner * fr
                s.y += lh
                i += 1
            s.d.rectangle([M, y0, W - M, s.y], outline=RULE, width=2)
            s.y += GAP
            if not rows:
                break

    def save(self, folder: Path, stem: str) -> list[Path]:
        out = []
        n = len(self.sheets)
        for k, s in enumerate(self.sheets):
            s.d.text((W - M - 60, H - 18), f"{k + 1}/{n}", font=self.F.lbl, fill=DIM)
            p = folder / f"{stem}_{k:02d}.png"
            s.img.save(p)
            out.append(p)
        return out


def render(card: dict, folder: Path, stem: str) -> list[Path]:
    """card: {sub, pages: [{title, items: [("times", cells) | ("boxes", row, widths) | ("table", head, cols, rows)]}]}."""
    kb = _Book(card["sub"], card.get("lg", "ru"))
    for page in card["pages"]:
        kb.sheet(page["title"])
        for it in page["items"]:
            if it[0] == "times":
                kb.times(page["title"], it[1])
            elif it[0] == "boxes":
                kb.boxes(page["title"], it[1], it[2] if len(it) > 2 else None)
            elif it[0] == "table":
                kb.table(page["title"], it[1], it[2], it[3])
    return kb.save(folder, stem)


def build(m, lg: str, groups: list[dict]) -> int:
    """groups: {"type": тип pydcs, "card": card (render)} - на группу игрока. Возвращает число страниц (0 - нет Pillow)."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="redfront_kb_"))
    n = 0
    for gi, g in enumerate(groups):
        for p in render(g["card"], tmp, f"{gi:02d}"):
            m.add_aircraft_kneeboard(g["type"], p)
            n += 1
    return n

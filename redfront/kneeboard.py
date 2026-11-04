"""Наколенный планшет (kneeboard) ЛА игрока: страницы-картинки в .miz по типу ЛА (DCS не умеет планшет на группу -
страницы подписаны группой). Страницы: задание и маршрут со временем, связь, погода и аэродромы.

Картинки рисует Pillow; нет Pillow - миссия без планшета (брифинг остаётся). Шрифт - системный с кириллицей
(Windows: Consolas / Arial, Linux: DejaVu), иначе встроенный.
"""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

W, H = 768, 1024
MARGIN = 28
FONTS = ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "LiberationMono-Regular.ttf"]
BOLD = ["consolab.ttf", "courbd.ttf", "DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]


def _font(names, size):
    from PIL import ImageFont
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _page(title: str, sub: str, blocks: list[tuple[str, list[str]]], path: Path) -> list[Path]:
    """Страница: заголовок, подзаголовок (группа), разделы (заголовок, строки); длинные строки переносятся. Не помещается -
    продолжение на следующих страницах (заголовок с номером листа), ничего не обрезается."""
    from PIL import Image, ImageDraw
    ft, fs, fh, fb = _font(BOLD, 30), _font(FONTS, 18), _font(BOLD, 20), _font(FONTS, 18)
    cw = max(8.0, fb.getlength("Ж")) if hasattr(fb, "getlength") else 10.0
    cols = int((W - 2 * MARGIN) / cw) - 1
    rows: list[tuple[str, str]] = []             # (вид строки, текст): head, line, gap
    for head, lines in blocks:
        for part in textwrap.wrap(head, int(cols * 0.85)) or [""]:
            rows.append(("head", part))
        rows.append(("rule", ""))
        for ln in lines:
            for part in textwrap.wrap(ln, cols, subsequent_indent="  ") or [""]:
                rows.append(("line", part))
        rows.append(("gap", ""))
    step = {"head": 28, "line": 23, "gap": 12, "rule": 0}
    sheets: list[list[tuple[str, str]]] = [[]]
    y = 116
    for kind, txt in rows:
        if y + step[kind] > H - 24 and kind != "gap":
            sheets.append([])
            y = 116
        sheets[-1].append((kind, txt))
        y += step[kind]
    out = []
    for k, sheet in enumerate(sheets):
        img = Image.new("RGB", (W, H), (246, 242, 230))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 70], fill=(40, 48, 60))
        d.text((MARGIN, 16), title + (f" ({k + 1}/{len(sheets)})" if len(sheets) > 1 else ""), font=ft, fill=(255, 255, 255))
        d.text((MARGIN, 82), sub, font=fs, fill=(90, 90, 90))
        y = 116
        for kind, txt in sheet:
            if kind == "head":
                d.text((MARGIN, y), txt, font=fh, fill=(150, 30, 30))
            elif kind == "rule":
                d.line([MARGIN, y - 4, W - MARGIN, y - 4], fill=(180, 170, 150), width=1)
            elif kind == "line":
                d.text((MARGIN, y), txt, font=fb, fill=(20, 20, 20))
            y += step[kind]
        pth = path.with_name(f"{path.stem}_{k}{path.suffix}")
        img.save(pth)
        out.append(pth)
    return out


def build(m, lg: str, groups: list[dict]) -> int:
    """groups: {"type": тип pydcs, "title", "sub", "pages": [(заголовок страницы, [(раздел, строки)])]} - на тип ЛА игрока.
    Возвращает число страниц (0 - нет Pillow)."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="redfront_kb_"))
    n = 0
    for gi, g in enumerate(groups):
        for pi, (title, blocks) in enumerate(g["pages"]):
            for p in _page(title, g["sub"], blocks, tmp / f"{gi:02d}_{pi:02d}.png"):
                m.add_aircraft_kneeboard(g["type"], p)
                n += 1
    return n

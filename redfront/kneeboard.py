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


def _page(title: str, sub: str, blocks: list[tuple[str, list[str]]], path: Path) -> Path:
    """Страница: заголовок, подзаголовок (группа), разделы (заголовок, строки); длинные строки переносятся."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (246, 242, 230))
    d = ImageDraw.Draw(img)
    ft, fs, fh, fb = _font(BOLD, 30), _font(FONTS, 18), _font(BOLD, 20), _font(FONTS, 18)
    d.rectangle([0, 0, W, 70], fill=(40, 48, 60))
    d.text((MARGIN, 16), title, font=ft, fill=(255, 255, 255))
    y = 82
    d.text((MARGIN, y), sub, font=fs, fill=(90, 90, 90))
    y += 34
    cw = max(8.0, fb.getlength("Ж")) if hasattr(fb, "getlength") else 10.0
    cols = int((W - 2 * MARGIN) / cw) - 1
    for head, lines in blocks:
        if y > H - 60:
            break
        for part in textwrap.wrap(head, int(cols * 0.85)) or [""]:
            d.text((MARGIN, y), part, font=fh, fill=(150, 30, 30))
            y += 28
        d.line([MARGIN, y - 4, W - MARGIN, y - 4], fill=(180, 170, 150), width=1)
        for ln in lines:
            for part in textwrap.wrap(ln, cols, subsequent_indent="  ") or [""]:
                if y > H - 30:
                    break
                d.text((MARGIN, y), part, font=fb, fill=(20, 20, 20))
                y += 23
        y += 12
    img.save(path)
    return path


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
            p = _page(title, g["sub"], blocks, tmp / f"{gi:02d}_{pi:02d}.png")
            m.add_aircraft_kneeboard(g["type"], p)
            n += 1
    return n

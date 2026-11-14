"""Растр типа поверхности для театра (data/landcover/<театр>.png + .json): лес, вода, застройка - по ESA WorldCover 2021
(10 м, CC BY 4.0, (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by
ESA WorldCover consortium). Карта DCS Cold War Germany повторяет реальную местность, поэтому реальный покров - лучшая
доступная оценка леса и водоёмов карты (скриптам DCS лес не виден: land.getSurfaceType - только суша/дорога/вода).

Читается уровень обзора (overview) облачных GeoTIFF (COG) с S3 ESA по HTTP Range - без GDAL: заголовок TIFF, плитки
1024x1024, DEFLATE. Классы растра: 0 - открытая местность, 1 - лес, 2 - вода и болото, 3 - застройка.
Запуск: python tools/gen_landcover.py germany [уровень обзора, по умолчанию 4 - ~150x90 м]
"""
from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
OUT = Path(__file__).resolve().parent.parent / "redfront" / "data" / "landcover"
BOX = {"germany": (49.2, 6.4, 54.8, 13.9)}   # юг, запад, север, восток: все сектора театра с запасом
CLS = {10: 1, 80: 2, 90: 2, 50: 3}           # WorldCover: деревья, вода, болото, застройка; прочее - 0


def _get(url: str, a: int, b: int) -> bytes:
    """Байты a..b файла (curl - через прокси окружения)."""
    return subprocess.run(["curl", "-sSf", "-r", f"{a}-{b}", url], check=True, capture_output=True).stdout


def _ifds(url: str) -> list[dict]:
    head = _get(url, 0, 65535)
    bo = "<" if head[:2] == b"II" else ">"
    off, out = struct.unpack(bo + "I", head[4:8])[0], []
    while off:
        n = struct.unpack(bo + "H", head[off:off + 2])[0]
        d = {}
        for i in range(n):
            tag, typ, cnt, val = struct.unpack(bo + "HHI4s", head[off + 2 + 12 * i:off + 14 + 12 * i])
            fmt = {3: "H", 4: "I", 16: "Q"}.get(typ)
            if fmt is None:
                continue
            size = struct.calcsize(fmt)
            if cnt * size <= 4:
                v = list(struct.unpack(bo + fmt * cnt, val[:cnt * size]))
            else:
                p = struct.unpack(bo + "I", val)[0]
                raw = head[p:p + cnt * size] if p + cnt * size <= len(head) else _get(url, p, p + cnt * size - 1)
                v = list(struct.unpack(bo + fmt * cnt, raw))
            d[tag] = v
        out.append({"w": d[256][0], "h": d[257][0], "tw": d[322][0], "th": d[323][0], "offs": d[324], "bcs": d[325]})
        off = struct.unpack(bo + "I", head[off + 2 + 12 * n:off + 6 + 12 * n])[0]
    return out


def tile_raster(lat0: int, lon0: int, level: int) -> tuple[int, bytearray]:
    """Плитка WorldCover 3x3 градуса (юго-западный угол lat0, lon0) на уровне обзора level: (сторона, классы по строкам
    с севера). Нет плитки (море) - вода."""
    tile = f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"
    url = URL.format(tile=tile)
    try:
        ifd = _ifds(url)[level]
    except subprocess.CalledProcessError:
        n = 36000 >> level
        return n, bytearray([2]) * (n * n)
    w, h, tw, th = ifd["w"], ifd["h"], ifd["tw"], ifd["th"]
    nx = math.ceil(w / tw)
    lut = bytes(CLS.get(i, 0) for i in range(256))
    out = bytearray(w * h)
    for k, (o, c) in enumerate(zip(ifd["offs"], ifd["bcs"])):
        ty, tx = divmod(k, nx)
        data = zlib.decompress(_get(url, o, o + c - 1)).translate(lut)
        for r in range(th):
            y = ty * th + r
            if y >= h:
                break
            x0 = tx * tw
            n = min(tw, w - x0)
            out[y * w + x0:y * w + x0 + n] = data[r * tw:r * tw + n]
        print(f"  {tile}: плитка {k + 1}/{len(ifd['offs'])}", end="\r")
    print()
    return w, out


def main() -> None:
    from PIL import Image
    theatre = sys.argv[1] if len(sys.argv) > 1 else "germany"
    level = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    s, w, n, e = BOX[theatre]
    la0, lo0 = 3 * math.floor(s / 3), 3 * math.floor(w / 3)
    la1, lo1 = 3 * math.ceil(n / 3), 3 * math.ceil(e / 3)
    side = 36000 >> level
    step = 3.0 / side
    W, H = round((lo1 - lo0) / step), round((la1 - la0) / step)
    big = Image.new("L", (W, H), 0)
    for lat in range(la0, la1, 3):
        for lon in range(lo0, lo1, 3):
            n_, raw = tile_raster(lat, lon, level)
            im = Image.frombytes("L", (n_, n_), bytes(raw))
            big.paste(im, (round((lon - lo0) / step), round((la1 - lat - 3) / step)))
    x0, y0 = round((w - lo0) / step), round((la1 - n) / step)
    x1, y1 = round((e - lo0) / step), round((la1 - s) / step)
    big = big.crop((x0, y0, x1, y1))
    pal = big.convert("P")
    pal.putpalette([235, 235, 215, 0, 100, 0, 0, 100, 200, 250, 0, 0] + [0] * (256 * 3 - 12))
    png = OUT / f"{theatre}.png"
    pal.save(png, optimize=True, bits=2)
    meta = {"_about": __doc__.split("\n\n")[0], "north": lo0 * 0 + la1 - y0 * step, "west": lo0 + x0 * step,
            "step_lat": step, "step_lon": step, "w": big.width, "h": big.height,
            "classes": {"0": "open", "1": "forest", "2": "water", "3": "built"}}
    (OUT / f"{theatre}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{png}: {big.width}x{big.height}, шаг {step * 111_320:.0f} м по широте, {png.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()

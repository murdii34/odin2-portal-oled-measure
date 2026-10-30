"""Colour and light across the whole screen, not just the measuring region:
each archived shot, black frame (same exposure) subtracted, in a grid of
cells; printed as left-to-right profiles relative to the screen's mean."""
import calendar
import glob
import json
import os
import re
import struct
import sys
import time

import numpy as np

import rawstats

HOME = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HOME, "raw", "archive")
PINNED = os.path.join(HOME, "raw", "pinned")


def shots(pattern):
    """Archived and kept shots matching pattern, oldest first."""
    files = glob.glob(os.path.join(ARCHIVE, pattern)) + glob.glob(os.path.join(PINNED, "*", pattern))
    return sorted(files, key=lambda f: os.path.basename(f))


def exposure(path):
    """(seconds, iso) from the ARW's EXIF (it's a TIFF)."""
    with open(path, "rb") as f:
        data = f.read(1 << 16)
    end = "<" if data[:2] == b"II" else ">"

    def ifd(off):
        n = struct.unpack_from(end + "H", data, off)[0]
        for i in range(n):
            tag, typ, cnt, val = struct.unpack_from(end + "HHII", data, off + 2 + 12 * i)
            yield tag, typ, cnt, val, off + 2 + 12 * i + 8

    exif = next(v for t, _, _, v, _ in ifd(struct.unpack_from(end + "I", data, 4)[0]) if t == 0x8769)
    seconds = iso = None
    for tag, typ, cnt, val, at in ifd(exif):
        if tag == 0x829A:
            num, den = struct.unpack_from(end + "II", data, val)
            seconds = num / den
        elif tag == 0x8827:
            iso = struct.unpack_from(end + "H", data, at)[0]
    return seconds, iso


def black_for(path, blacks):
    """The black frame with the same exposure, nearest in time."""
    want = exposure(path)
    same = [b for b in blacks if exposure(b) == want]
    if not same:
        return None
    t = stamp(path)
    if t is None:
        return same[-1]
    return min(same, key=lambda b: abs((stamp(b) or 0) - t))


def stamp(path):
    """Unix time from a shot's name: 20261025T065915Z-... (UTC) or the older
    20261024-152500-... (local); None if neither. (Comparing the HHMMSS digits
    alone matched yesterday's frames across noon and midnight.)"""
    name = os.path.basename(path)
    m = re.match(r"(\d{8})T(\d{6})Z", name)
    if m:
        return calendar.timegm(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    m = re.match(r"(\d{8})-(\d{6})", name)
    if m:
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    return None


def grid(path, black, box, cols=12, rows=5, inset=0.04):
    img, colors, lvl, white, _ = rawstats.load(path)
    if black:
        bimg = rawstats.load(black)[0]
        img = img - bimg
    else:
        img = img - lvl
    y0, y1, x0, x1 = box
    dy, dx = (y1 - y0) * inset, (x1 - x0) * inset
    y0, y1, x0, x1 = int(y0 + dy), int(y1 - dy), int(x0 + dx), int(x1 - dx)
    out = np.zeros((rows, cols, 3))
    for r in range(rows):
        for c in range(cols):
            ya, yb = y0 + (y1 - y0) * r // rows, y0 + (y1 - y0) * (r + 1) // rows
            xa, xb = x0 + (x1 - x0) * c // cols, x0 + (x1 - x0) * (c + 1) // cols
            v, k = img[ya:yb, xa:xb], colors[ya:yb, xa:xb]
            out[r, c] = (v[k == 0].mean(), np.concatenate([v[k == 1], v[k == 3]]).mean(), v[k == 2].mean())
    return out


def profile(g):
    """Left-to-right: R/G, B/G and light (sum), each relative to the mean."""
    col = g.mean(axis=0)
    rg, bg, y = col[:, 0] / col[:, 1], col[:, 2] / col[:, 1], col.sum(axis=1)
    return rg / rg.mean(), bg / bg.mean(), y / y.mean()


def main():
    box = json.load(open(os.path.join(HOME, "state", "roi.json")))["screen"]
    blacks = shots("*-black-*.ARW")
    pats = sys.argv[1:]
    for pat in pats:
        files = shots(f"*-{pat}.ARW")
        if not files:
            print(pat, "no files")
            continue
        path = files[-1]
        b = black_for(path, blacks)
        g = grid(path, b, box)
        rg, bg, y = profile(g)
        s, iso = exposure(path)
        print(f"{os.path.basename(path)}  ({s:.3g}s ISO {iso}, black {'matched' if b else 'LEVEL ONLY'})")
        print("  column   " + " ".join(f"{i + 1:>5}" for i in range(len(rg))))
        print("  R/G      " + " ".join(f"{x:5.2f}" for x in rg))
        print("  B/G      " + " ".join(f"{x:5.2f}" for x in bg))
        print("  light    " + " ".join(f"{x:5.2f}" for x in y))


if __name__ == "__main__":
    main()

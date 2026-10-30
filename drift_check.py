"""Has the Odin moved against the camera over the days? From kept shots of
bright full-screen patches, the screen's four edges at sub-pixel precision
(where the light crosses half way between background and plateau, on 2x2
green blocks), plus each edge's softness (10-90% width: a change there means
the focus moved). Reads files only; the camera is left alone.
    drift_check.py [N [MATCH]]   (N shots spread over time, default 60; MATCH
    e.g. b177-code128 keeps to one backlight and grey, so exposure and
    flare don't masquerade as movement)"""
import glob
import json
import os
import re
import sys
import time

import numpy as np

import rawstats
from measure import RAW, RUNS, log

BOX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "roi.json")))["screen"]


def edge(profile, rising):
    """Sub-pixel position of the 50% crossing and the 10-90% width of one
    edge in a 1-D profile (low to high if rising)."""
    p = profile if rising else profile[::-1]
    lo, hi = np.percentile(p, 5), np.percentile(p, 95)
    if hi - lo <= 0:
        return None, None
    q = (p - lo) / (hi - lo)

    def cross(level):
        i = int(np.argmax(q >= level))
        if i == 0:
            return None
        return i - 1 + (level - q[i - 1]) / max(q[i] - q[i - 1], 1e-9)

    c50, c10, c90 = cross(0.5), cross(0.1), cross(0.9)
    if c50 is None or c10 is None or c90 is None:
        return None, None
    pos = c50 if rising else len(p) - 1 - c50
    return pos, c90 - c10


def measure(path):
    img, cols, black, _, _ = rawstats.load(path)
    g = np.where((cols == 1) | (cols == 3), img - black, 0.0)
    h, w = g.shape[0] // 2 * 2, g.shape[1] // 2 * 2
    g = g[:h, :w].reshape(h // 2, 2, w // 2, 2).sum(axis=(1, 3)) / 2     # two greens per 2x2 block
    y0, y1, x0, x1 = (v // 2 for v in BOX)
    m = 60                                                              # margin around the screen, blocks
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    # Profiles through the middle third, across each pair of edges.
    rows = g[cy - (y1 - y0) // 6: cy + (y1 - y0) // 6, max(0, x0 - m): x1 + m].mean(axis=0)
    colp = g[max(0, y0 - m): y1 + m, cx - (x1 - x0) // 6: cx + (x1 - x0) // 6].mean(axis=1)
    half_x, half_y = len(rows) // 2, len(colp) // 2
    left, wl = edge(rows[:half_x], True)
    right, wr = edge(rows[half_x:], False)
    top, wt = edge(colp[:half_y], True)
    bottom, wb = edge(colp[half_y:], False)
    if None in (left, right, top, bottom):
        return None
    ox, oy = max(0, x0 - m), max(0, y0 - m)
    # Back to raw pixels.
    return {"left": 2 * (ox + left), "right": 2 * (ox + half_x + right), "top": 2 * (oy + top),
            "bottom": 2 * (oy + half_y + bottom), "soft": 2 * float(np.mean([wl, wr, wt, wb]))}


def when(path):
    m = re.search(r"(\d{8})T?-?(\d{6})", os.path.basename(path))
    return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")) if m else os.path.getmtime(path)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    match = sys.argv[2] if len(sys.argv) > 2 else None
    files = []
    for f in glob.glob(os.path.join(RAW, "**", "*.ARW"), recursive=True):
        m = re.search(r"code(\d+)\.ARW$", f)
        if m and int(m.group(1)) >= 64 and (not match or match + ".ARW" in f):   # bright, full-screen patch
            files.append(f)
    files.sort(key=when)
    pick = [files[round(i * (len(files) - 1) / max(1, n - 1))] for i in range(min(n, len(files)))]
    out = []
    for f in dict.fromkeys(pick):
        try:
            r = measure(f)
        except Exception as e:
            log(f"{os.path.basename(f)}: {e}")
            continue
        if not r:
            continue
        r.update(file=os.path.basename(f), t=when(f))
        out.append(r)
        log(f"{time.strftime('%d %H:%M', time.localtime(r['t']))} {r['file'][:44]:44s} L {r['left']:8.1f} R {r['right']:8.1f} "
            f"T {r['top']:8.1f} B {r['bottom']:8.1f} soft {r['soft']:5.1f}")
    path = os.path.join(RUNS, f"drift-check-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    if len(out) > 1:
        for r in out:
            r["cx"], r["cy"] = (r["left"] + r["right"]) / 2, (r["top"] + r["bottom"]) / 2
            r["width"], r["height"] = r["right"] - r["left"], r["bottom"] - r["top"]
        for k in ("cx", "cy", "width", "height", "soft"):
            v = np.array([r[k] for r in out])
            log(f"{k:6s}: first {out[0][k]:8.1f}, range {v.min():8.1f}..{v.max():8.1f} ({v.max() - v.min():.1f} px), "
                f"last minus first {v[-1] - v[0]:+.1f} px")
    log(f"saved {path}")


if __name__ == "__main__":
    main()

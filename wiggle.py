"""How much play has the hood? One shot per position (murdii nudges the
Odin by its cable in between): the screen's centre, size and tilt in the
frame, in millimetres via the panel's width (7", 16:9: 154.9 mm active).
    wiggle.py LABEL     -> appends to runs/wiggle.json and prints against the first"""
import json
import math
import os
import sys

import numpy as np

import rawstats
from drift_check import BOX, edge
from measure import RAW, RUNS, Rig, codes

PANEL_MM = 154.9
PATH = os.path.join(RUNS, "wiggle.json")


def geometry(path):
    img, cols, black, _, _ = rawstats.load(path)
    g = np.where((cols == 1) | (cols == 3), img - black, 0.0)
    h, w = g.shape[0] // 2 * 2, g.shape[1] // 2 * 2
    g = g[:h, :w].reshape(h // 2, 2, w // 2, 2).sum(axis=(1, 3)) / 2
    y0, y1, x0, x1 = (v // 2 for v in BOX)
    m = 120
    lines = {}
    for name, rising, horiz in (("top", True, True), ("bottom", False, True), ("left", True, False), ("right", False, False)):
        pts = []
        across = np.linspace(0.15, 0.85, 13)
        for f in across:
            if horiz:
                x = int(x0 + f * (x1 - x0))
                lo, hi = (max(0, y0 - m), (y0 + y1) // 2) if rising else ((y0 + y1) // 2, min(g.shape[0], y1 + m))
                p, _ = edge(g[lo:hi, x - 8:x + 8].mean(axis=1), rising)
                if p is not None:
                    pts.append((x, lo + p))
            else:
                y = int(y0 + f * (y1 - y0))
                lo, hi = (max(0, x0 - m), (x0 + x1) // 2) if rising else ((x0 + x1) // 2, min(g.shape[1], x1 + m))
                p, _ = edge(g[y - 8:y + 8, lo:hi].mean(axis=0), rising)
                if p is not None:
                    pts.append((y, lo + p))
        lines[name] = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)
    cx = (np.polyval(lines["left"], (y0 + y1) / 2) + np.polyval(lines["right"], (y0 + y1) / 2)) / 2
    cy = (np.polyval(lines["top"], (x0 + x1) / 2) + np.polyval(lines["bottom"], (x0 + x1) / 2)) / 2
    width = np.polyval(lines["right"], cy) - np.polyval(lines["left"], cy)
    tilt = math.degrees(math.atan((lines["top"][0] + lines["bottom"][0]) / 2))
    return {"cx": 2 * float(cx), "cy": 2 * float(cy), "width_px": 2 * float(width), "tilt": tilt}


def main():
    label = sys.argv[1]
    rig = Rig(keep=False)
    try:
        rig.screen.brightness(177)
        rig.read(codes([128])[0], 177)               # finds the exposure
        rig.screen.patch(codes([128])[0])
        path = rig.cam.capture(os.path.join(RAW, f"wiggle-{label}.ARW"))
    finally:
        rig.close()
    g = geometry(path)
    data = json.load(open(PATH)) if os.path.exists(PATH) else []
    data.append({"label": label, **g})
    json.dump(data, open(PATH, "w"), indent=1)
    first = data[0]
    mm = PANEL_MM / first["width_px"]
    print(f"{label}: centre {g['cx']:.1f}, {g['cy']:.1f} px, width {g['width_px']:.1f} px, tilt {g['tilt']:+.2f}°")
    if len(data) > 1:
        print(f"  against '{first['label']}': x {(g['cx'] - first['cx']) * mm:+.2f} mm, y {(g['cy'] - first['cy']) * mm:+.2f} mm, "
              f"size {g['width_px'] / first['width_px'] - 1:+.2%} (distance), tilt {g['tilt'] - first['tilt']:+.2f}°")
        xs = [(d["cx"] - first["cx"]) * mm for d in data]
        ys = [(d["cy"] - first["cy"]) * mm for d in data]
        ts = [d["tilt"] for d in data]
        print(f"  so far ({len(data)}): x {max(xs) - min(xs):.2f} mm, y {max(ys) - min(ys):.2f} mm, tilt {max(ts) - min(ts):.2f}° of play")


if __name__ == "__main__":
    main()

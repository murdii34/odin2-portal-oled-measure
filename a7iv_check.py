"""A7 IV acceptance: linearity (shutter, ISO) and dark noise on a grey patch / black."""
import json, os, sys, time
import numpy as np
import camera, rawstats
from measure import RAW, ROI_FILE, log
from screen import Screen

roi = json.load(open(ROI_FILE))["roi"]
screen = Screen(); cam = camera.Camera()
out = {}
def shot(tag):
    p = cam.capture(os.path.join(RAW, f"a7iv-{tag}.ARW"))
    img, cols, black, white, _ = rawstats.load(p)
    y0, y1, x0, x1 = roi
    g = img[y0:y1, x0:x1]; c = cols[y0:y1, x0:x1]
    gm = g[(c == 1) | (c == 3)]
    return dict(mean=float(gm.mean() - black), std=float(gm.std()), p99=float(np.percentile(gm, 99.9)) / (white - black), black=black)
try:
    screen.brightness(1000); screen.patch(96); time.sleep(1)
    rows = []
    for sec in ("1/60", "1/30", "1/15", "1/8", "1/4"):
        cam.set(iso=800, seconds=camera._seconds(sec)); s = shot(f"shut-{sec.replace('/','_')}"); s["shutter"] = sec
        s["per_s"] = s["mean"] / camera._seconds(cam.shutter); rows.append(s); log(f"shutter {cam.shutter}: {s['mean']:.1f} ({s['per_s']:.0f}/s) p99 {s['p99']:.2f}")
    out["shutter"] = rows; rows = []
    for iso in (100, 200, 400, 800, 1600, 3200):
        cam.set(iso=iso, seconds=1 / 15); s = shot(f"iso-{iso}"); s["iso"] = iso
        s["per_iso"] = s["mean"] / iso; rows.append(s); log(f"ISO {iso}: {s['mean']:.1f} ({s['per_iso']:.3f}/ISO) p99 {s['p99']:.2f}")
    out["iso"] = rows; rows = []
    screen.patch(0); time.sleep(1)
    for iso, sec in ((800, 1 / 30), (3200, 1 / 15), (3200, 4), (3200, 15)):
        cam.set(iso=iso, seconds=sec); s = shot(f"dark-{iso}-{cam.shutter.replace('/','_')}"); s.update(iso=iso, shutter=cam.shutter)
        rows.append(s); log(f"dark ISO {iso} {cam.shutter}s: mean {s['mean']:.2f} std {s['std']:.2f} black {s['black']}")
    out["dark"] = rows
finally:
    screen.hide()
json.dump(out, open("runs/a7iv-check.json", "w"), indent=1)

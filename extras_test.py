"""Extra panel tests with the rig (correction off, raw panel):

  sweep  - grey 255 and 32 across the backlight range: where the panel's
           behaviour changes (jumps, the bad band's edges)
  pwm    - very short exposures: the electronic shutter reads out row by row,
           so pulsed dimming shows as bands along the readout; band period
           and depth per backlight step
  split  - bright left half next to a dark grey right half vs the dark grey
           alone (stray light measured separately and subtracted): does
           bright content shift dark greys?
  stray  - a bright window in the middle, black elsewhere: light the camera
           sees in the black area (lens flare + hood reflections)
"""
import json
import os
import sys
import time

import numpy as np

import camera
import plugin
import rawstats
import uniformity
from measure import RAW, RUNS, Rig, archive, codes, log


def screen_js(rig, css_body):
    """Draw arbitrary content into the measuring overlay."""
    rig.screen.ui.eval("""(() => {
      let d = document.getElementById("oled-measure");
      if (!d) { d = document.createElement("div"); d.id = "oled-measure";
        d.style.cssText = "position:fixed;inset:0;z-index:2147483647;cursor:none"; document.body.appendChild(d); }
      d.style.background = "#000"; d.innerHTML = %s; return true; })()""" % json.dumps(css_body))


def with_pattern(rig, body):
    """Make rig.read() show `body` (HTML) instead of a grey; its black frames stay black."""
    orig = rig.screen.patch

    def patch(code):
        if code == 0 or code == (0, 0, 0):
            orig(0)
            rig.screen.ui.eval('(() => { const d = document.getElementById("oled-measure"); if (d) d.innerHTML = ""; return true; })()')
        else:
            screen_js(rig, body)
    rig.screen.patch = patch
    return orig


def save(out, path):
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


def sweep(rig):
    out = {"test": "sweep", "records": []}
    path = os.path.join(RUNS, f"sweep-{time.strftime('%Y%m%d-%H%M%S')}.json")
    steps = sorted({int(round(40 * (4096 / 40) ** (i / 34))) for i in range(35)})
    for b in steps:
        rig.screen.brightness(b)
        # Short exposures only where the panel can't be pulsing (full range).
        camera.MIN_SECONDS = 0.002 if b >= 2000 else 1 / 30
        for level in (255, 32):
            r = rig.read(codes([level])[0], b)
            out["records"].append({"backlight": b, "level": level, **r})
            log(f"sweep b {b:4d} grey {level:3d}: Y {r['Y']:.5g}  R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}")
            save(out, path)
    camera.MIN_SECONDS = 1 / 30
    log(f"saved {path}")


def pwm(rig):
    out = {"test": "pwm", "records": []}
    path = os.path.join(RUNS, f"pwm-{time.strftime('%Y%m%d-%H%M%S')}.json")
    box = rig.screen_box
    camera.MIN_SECONDS = 1 / 8000
    for b in (52, 96, 177, 310, 543, 1217, 4096):
        rig.screen.brightness(b)
        rig.screen.patch(255)
        time.sleep(0.5)
        for secs, iso in ((1 / 4000, 6400), (1 / 1000, 1600)):
            rig.cam.set(iso=iso, seconds=secs)
            p = rig.cam.capture(os.path.join(RAW, "pwm.ARW"))
            img, cols, black, white, _ = rawstats.load(p)
            y0, y1, x0, x1 = box
            g = np.where((cols == 1) | (cols == 3), img - black, np.nan)[y0:y1, x0:x1]
            prof = np.nanmean(g, axis=1)          # along the readout (sensor rows)
            prof = prof[np.isfinite(prof)]
            mean = float(prof.mean())
            # Detrend (vignetting, panel gradient) with a wide moving average.
            k = max(9, len(prof) // 8) | 1
            trend = np.convolve(prof, np.ones(k) / k, mode="same")
            ripple = (prof - trend)[k:-k]
            depth = float(np.std(ripple) / max(mean, 1e-9))
            spec = np.abs(np.fft.rfft(ripple - ripple.mean()))
            spec[:3] = 0
            period = float(len(ripple) / max(int(np.argmax(spec)), 1))
            arch = archive(p, f"pwm-b{b}-{secs:.6f}s", keep=True)
            out["records"].append({"backlight": b, "seconds": secs, "iso": iso, "mean": mean,
                                   "ripple_rel": depth, "period_rows": period, "raw": arch})
            log(f"pwm b {b:4d} {secs * 1e6:6.0f} us: ripple {depth:.1%} of mean, dominant period {period:.1f} sensor rows")
            save(out, path)
    camera.MIN_SECONDS = 1 / 30
    log(f"saved {path}")


def split(rig, step=177):
    """Left half white, right half grey g; right-half cells vs the grey alone,
    after subtracting what the white half alone puts into the right half."""
    out = {"test": "split", "step": step, "records": []}
    path = os.path.join(RUNS, f"split-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    rig.screen.brightness(step)
    half = '<div style="position:absolute;left:0;top:0;width:50%%;height:100%%;background:rgb(255,255,255)"></div>'
    for g in (8, 16, 32):
        right = f'<div style="position:absolute;right:0;top:0;width:50%;height:100%;background:rgb({g},{g},{g})"></div>'
        for name, body in (("grey alone", right), ("white alone", half % ()), ("white + grey", (half % ()) + right)):
            orig = with_pattern(rig, body)
            # Meter on the dark half: move the ROI there for this read.
            roi = rig.roi
            y0, y1, x0, x1 = rig.screen_box
            rig.roi = [y0 + (y1 - y0) // 4, y1 - (y1 - y0) // 4, x0 + (x1 - x0) * 5 // 8, x1 - (x1 - x0) // 8]
            try:
                r = rig.read(255, step)
            finally:
                rig.roi = roi
                rig.screen.patch = orig
            out["records"].append({"grey": g, "pattern": name, **r})
            log(f"split grey {g:2d} {name:13s}: dark-half region R {r['R']:.4g} G {r['G']:.4g} B {r['B']:.4g}")
            save(out, path)
        rec = {x["pattern"]: x for x in out["records"] if x["grey"] == g}
        for c in "RGB":
            alone, white, both = rec["grey alone"][c], rec["white alone"][c], rec["white + grey"][c]
            log(f"  grey {g} {c}: with white next to it {(both - white) / alone - 1:+.1%} (stray light subtracted)")
    log(f"saved {path}")


def stray(rig, step=543):
    """A 20%-wide white window in the middle: the black area's light as a
    share of the window's, per channel, near and far from the window."""
    out = {"test": "stray", "step": step}
    path = os.path.join(RUNS, f"stray-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    rig.screen.brightness(step)
    body = '<div style="position:absolute;left:40%;top:40%;width:20%;height:20%;background:#fff"></div>'
    orig = with_pattern(rig, body)
    try:
        win = rig.read(255, step)          # meters on the centre ROI = the window
        s0, iso0 = rig.cam.seconds, int(rig.cam.iso)
        # The black area needs ~200x the exposure.
        rig.cam.set(iso=min(6400, iso0 * 16), seconds=min(rig.cam.longest, s0 * 12))
        rig.screen.patch(255)
        time.sleep(0.3)
        p = rig.cam.capture(os.path.join(RAW, "stray.ARW"))
        k = rig._black()
        gl = uniformity.grid(p, k["path"] if os.path.exists(k["path"]) else None, rig.screen_box)

        unit_l = rig.cam.seconds * int(rig.cam.iso) / 100
        archive(p, f"stray-b{step}-long", keep=True)
    finally:
        rig.screen.patch = orig
    gw = np.array(win["grid"]) * 1.0                    # per unit already
    gl = gl / unit_l
    rows, cols = gl.shape[:2]
    window = gw[2, 5:7].mean(axis=0)                   # middle cells
    ring = []
    for r in range(rows):
        for c in range(cols):
            if r == 2 and 4 <= c <= 7:
                continue
            ring.append((abs(r - 2) + abs(c - 5.5), gl[r, c] / window))
    near = np.mean([v for d, v in ring if d <= 2.5], axis=0)
    far = np.mean([v for d, v in ring if d >= 5], axis=0)
    out.update(window=window.tolist(), near=near.tolist(), far=far.tolist(), grid_long=gl.tolist())
    log(f"stray light, share of the window's light: near R {near[0]:.2%} G {near[1]:.2%} B {near[2]:.2%}; "
        f"far R {far[0]:.2%} G {far[1]:.2%} B {far[2]:.2%}")
    save(out, path)
    log(f"saved {path}")


def main():
    tests = sys.argv[1].split(",") if len(sys.argv) > 1 else ["sweep", "pwm", "split", "stray"]
    plugin.set_enabled(False)
    rig = Rig()
    try:
        for t in tests:
            log(f"--- {t}")
            {"sweep": sweep, "pwm": pwm, "split": split, "stray": stray}[t](rig)
    finally:
        camera.MIN_SECONDS = 1 / 30
        rig.close()
        plugin.set_enabled(True)


if __name__ == "__main__":
    main()

"""Does the dither that moves per frame give the same light as the still
one? First a redraw check (a shader that flashes the whole screen every
other frame must read as half light, with the animated patch keeping
gamescope drawing), then grey levels at one step with the dither still,
paired and golden."""
import json
import os
import sys
import time

import plugin
from measure import RUNS, Rig, codes, log
from pattern_test import ATOM, FX, host, show

LEVELS = [4, 8, 12, 16, 20, 24, 32, 48, 64]


def redraw_check(rig, step):
    """Light of a frame-flashing green 64 against solid green 64: ~0.5 when
    gamescope draws every frame; 0 or 1 when the picture stands still."""
    plugin.set_enabled(False)
    made, out = [], {}
    try:
        for name, expr in (("solid", "1.0"), ("flash", "float(FrameCount % 2)")):
            fx = FX.replace("uniform float Strength = 1.0;",
                            'uniform float Strength = 1.0;\nuniform int FrameCount < source = "framecount"; >;')
            made.append(show(f"oledtest_redraw_{name}_{int(time.time() * 1000)}.fx",
                             fx % {"on": expr, "hi": 64, "lo": 0, "ch": "0.0, 1.0, 0.0"}))
            for animate in (False, True):
                rig.screen.animate = animate
                r = rig.read(255, step)
                out[(name, animate)] = r["G"]
                log(f"redraw check {name:5s} animated={animate}: G {r['G']:9.2f}  ({r['seconds']:.3g}s ISO {r['iso']})")
    finally:
        host("xprop", "-root", "-remove", ATOM)
        for p in made:
            os.remove(p)
    share = {a: out[("flash", a)] / out[("solid", a)] for a in (False, True)}
    log(f"flashing / solid: still patch {share[False]:.3f}, animated patch {share[True]:.3f} (drawn every frame: ~0.5)")
    return share


def main():
    # temporal_check.py STEP [MODES [--no-redraw]]: MODES like still,pair
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 177
    modes = [False if m == "still" else m for m in sys.argv[2].split(",")] if len(sys.argv) > 2 else [False, "pair", "golden"]
    redraw = "--no-redraw" not in sys.argv
    data = plugin.read()
    keep = {k: data.get(k) for k in ("dither", "crush", "dither_temporal", "dither_temporal_ui", "enabled", "dither_ui")}
    rig = Rig()
    out = {"step": step, "redraw": None, "records": []}
    path = os.path.join(RUNS, f"temporal-check-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    try:
        rig.screen.brightness(step)
        share = redraw_check(rig, step) if redraw else {False: None, True: 0.3}
        out["redraw"] = {"still": share[False], "animated": share[True]}
        # 0.5 would be honest; at low backlight a pixel switched every frame
        # gives less (it doesn't fully light within a frame). Only 0 or 1
        # would mean gamescope isn't drawing every frame.
        if share[True] < 0.05 or share[True] > 0.95:
            raise SystemExit("gamescope doesn't draw every frame even with the animated patch")
        rig.screen.animate = True
        for mode in modes:
            def m(d, mode=mode):
                d.update(enabled=True, engine="reshade", dither=True, crush=0,
                         dither_temporal=mode, dither_temporal_ui=True, dither_ui=True)
            plugin.change(m)
            for level, code in zip(LEVELS, codes(LEVELS)):
                r = rig.read(code, step)
                out["records"].append({"mode": mode or "still", "level": level, **r})
                log(f"{str(mode or 'still'):6s} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  "
                    f"Y {r['Y']:.4g}  ({r['seconds']:.3g}s ISO {r['iso']})")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
    finally:
        rig.screen.animate = False
        rig.close()
        keep["dither_temporal_ui"] = bool(keep["dither_temporal_ui"])
        plugin.change(lambda d: d.update({k: v for k, v in keep.items() if v is not None}), compiled=False)
        log(f"settings back; saved {path}")


if __name__ == "__main__":
    main()

"""Accuracy across the brightness range, stock vs corrected: grey levels at
backlight steps through and around the bad band, with the plugin off and on
(dither moving per frame, as in games). Colour: R/G and B/G against the same
grey at full brightness (hood-ref). Light: against gamma 2.2 anchored at grey
128 of the same backlight. Writes runs/accuracy-sweep-*.json with a summary
(share within tolerance, mean and worst errors, a grade)."""
import json
import math
import os
import sys
import time

import plugin
from measure import RUNS, Rig, codes, log

STEPS = [52, 62, 70, 85, 100, 120, 150, 177, 230, 310, 450, 1200, 4096]
LEVELS = [4, 8, 16, 32, 128]
TOL_COLOUR = 0.03          # barely visible
TOL_LIGHT = 0.10


def grade(share):
    return "A" if share >= 0.9 else "B" if share >= 0.75 else "C" if share >= 0.6 else "D" if share >= 0.4 else "F"


def summarise(records, ref):
    """Per mode: errors per (step, level) and the overall verdict."""
    by = {}
    for r in records:
        by.setdefault((r["mode"], r["step"]), {})[r["level"]] = r
    out = {}
    # The steps actually measured (a re-check may cover others than STEPS).
    steps = sorted({r["step"] for r in records})
    for mode in ("stock", "corrected"):
        cells = []
        for step in steps:
            x = by.get((mode, step))
            if not x or 128 not in x:
                continue
            for L in LEVELS:
                if L == 128 or L not in x:
                    continue
                rg = x[L]["R"] / x[L]["G"] / (ref[L]["R"] / ref[L]["G"]) - 1
                bg = x[L]["B"] / x[L]["G"] / (ref[L]["B"] / ref[L]["G"]) - 1
                light = x[L]["Y"] / (x[128]["Y"] * (L / 128) ** 2.2)
                colour = max(abs(rg), abs(bg))
                ok = bool(colour <= TOL_COLOUR and abs(math.log(light)) <= math.log(1 + TOL_LIGHT))
                cells.append({"step": step, "level": L, "rg": float(rg), "bg": float(bg), "light": float(light),
                              "colour_err": float(colour), "ok": ok})
        if not cells:
            continue
        share = sum(c["ok"] for c in cells) / len(cells)
        band = [c for c in cells if 62 <= c["step"] <= 540]
        out[mode] = {
            "cells": cells,
            "share_ok": share,
            "share_ok_band": sum(c["ok"] for c in band) / len(band) if band else None,
            "mean_colour_err": sum(c["colour_err"] for c in cells) / len(cells),
            "worst_colour_err": max(c["colour_err"] for c in cells),
            "mean_light_err": math.exp(sum(abs(math.log(c["light"])) for c in cells) / len(cells)) - 1,
            "worst_light": max(cells, key=lambda c: abs(math.log(c["light"])))["light"],
            "grade": grade(share),
        }
    return out


def main():
    # accuracy_sweep.py [MODES [STEPS]]: e.g. corrected 70,100,177 (a re-check
    # after a calibration; stock doesn't change).
    modes = sys.argv[1].split(",") if len(sys.argv) > 1 else ["stock", "corrected"]
    steps = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else STEPS
    with open(os.path.join(RUNS, "hood-ref.json")) as f:
        ref = {r["level"]: r for r in json.load(f)["records"]}
    data = plugin.read()
    keep = {k: data.get(k) for k in ("dither", "crush", "dither_temporal", "dither_temporal_ui", "dither_ui", "enabled", "shadow_curve")}
    rig = Rig()
    out = {"steps": steps, "levels": LEVELS, "records": []}
    path = os.path.join(RUNS, f"accuracy-sweep-{time.strftime('%Y%m%d-%H%M%S')}.json")
    try:
        for mode in modes:
            if mode == "stock":
                plugin.set_enabled(False)
                rig.screen.animate = False
            else:
                plugin.change(lambda d: d.update(enabled=True, engine="reshade", dither=True, crush=0, dither_ui=True,
                                                 dither_temporal="pair", dither_temporal_ui=True, shadow_curve="g22"))
                rig.screen.animate = True
            for step in steps:
                t0 = time.time() - 0.5
                rig.screen.brightness(step)
                time.sleep(1.0)
                # The plugin follows the backlight with a new effect, which can
                # take gamescope a while: measure only once it's on screen.
                if mode != "stock":
                    plugin.settle(step, t0)
                for level, code in zip(LEVELS, codes(LEVELS)):
                    r = rig.read(code, step)
                    out["records"].append({"mode": mode, "step": step, "level": level, **r})
                    log(f"{mode:9s} b {step:4d} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  Y {r['Y']:.4g}")
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
    finally:
        rig.screen.animate = False
        rig.close()
        keep["dither_temporal_ui"] = bool(keep["dither_temporal_ui"])
        plugin.change(lambda d: d.update({k: v for k, v in keep.items() if v is not None}), compiled=False)
    out["summary"] = {m: {k: v for k, v in s.items() if k != "cells"} for m, s in summarise(out["records"], ref).items()}
    out["cells"] = {m: s["cells"] for m, s in summarise(out["records"], ref).items()}
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    for m, s in out["summary"].items():
        log(f"{m:9s}: grade {s['grade']}, {s['share_ok']:.0%} within ±{TOL_COLOUR:.0%} colour and ±{TOL_LIGHT:.0%} light "
            f"(in the bad band {s['share_ok_band']:.0%}); colour error mean {s['mean_colour_err']:.1%}, worst "
            f"{s['worst_colour_err']:.0%}; light error mean {s['mean_light_err']:.0%}, worst {s['worst_light']:.2f}x")
    log(f"saved {path}")


if __name__ == "__main__":
    main()

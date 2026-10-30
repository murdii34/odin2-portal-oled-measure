"""gamescope's SDR colour conversion at a given vibrance (gamut wideness),
measured: pure primaries at full code through the page, at the given
wideness and at 1.0 (where channels reach the panel unmixed), at full
backlight (no pedestal). In linear panel light, M = C1^-1 · C_w, with C the
camera's response to each pure channel. Mixed colours check how well a
matrix on linearised input predicts the rest, and which transfer function
(sRGB or gamma 2.2) gamescope linearises with."""
import json
import os
import struct
import sys
import time

import numpy as np

import plugin
from measure import RUNS, Rig, log
from pattern_test import host

WIDE = "GAMESCOPE_COLOR_SDR_GAMUT_WIDENESS"
PRIMARIES = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
CHECKS = [(128, 0, 0), (0, 128, 0), (255, 128, 0), (64, 128, 192), (200, 60, 120), (160, 160, 160)]


def wideness(w):
    bits = struct.unpack("<I", struct.pack("<f", w))[0]
    host("xprop", "-root", "-f", WIDE, "32c", "-set", WIDE, str(bits))
    time.sleep(1.5)


def srgb(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def main():
    w = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 4096
    plugin.set_enabled(False)
    rig = Rig()
    out = {"wideness": w, "step": step, "records": []}
    path = os.path.join(RUNS, f"gamut-matrix-{w}.json")
    cam = {}
    try:
        rig.screen.brightness(step)
        for ww in (1.0, w):
            wideness(ww)
            for rgb in PRIMARIES + CHECKS:
                r = rig.read(rgb, step)
                cam[(ww, rgb)] = np.array([r["R"], r["G"], r["B"]])
                out["records"].append({"wideness": ww, "rgb": rgb, **{k: r[k] for k in ("R", "G", "B", "Y", "seconds", "iso")}})
                log(f"w {ww} {rgb}: camera {cam[(ww, rgb)].round(1)}")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
    finally:
        wideness(0.5)
        rig.close()
        plugin.set_enabled(True)
    C1 = np.stack([cam[(1.0, p)] for p in PRIMARIES], axis=1)
    Cw = np.stack([cam[(w, p)] for p in PRIMARIES], axis=1)
    M = np.linalg.solve(C1, Cw)
    out["M"] = M.round(5).tolist()
    log("M (panel-linear, columns = input R, G, B):\n" + str(M.round(4)))
    # How well does "linearise, multiply, re-encode" predict the mixed colours?
    for name, lin in (("srgb", srgb), ("g22", lambda x: x ** 2.2)):
        errs = []
        for rgb in CHECKS:
            want = cam[(w, rgb)]
            got = C1 @ (M @ lin(np.array(rgb) / 255.0))
            errs.append(float(np.max(np.abs(got / want - 1))))
        out[f"err_{name}"] = errs
        log(f"{name}: worst channel error per check colour {[f'{e:.1%}' for e in errs]}")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    log(f"saved {path}")


if __name__ == "__main__":
    main()

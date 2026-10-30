"""Where exactly does the panel switch into its bad mode at the bottom of the
band, and does it depend on the direction? Sweep 1 found 62 clean, sweep 2
found it 23x too bright at grey 4. Correction off; grey 16 against grey 128
(gamma 2.2) at backlight 56..72, stepping up from below and down from
above, twice each. Clean mode reads ~1.9x, the bad one 3x and more. The
plugin's band-edge snap keeps the backlight out of what's unstable.
Writes runs/band-edge-*.json."""
import json
import os
import time

import plugin
from measure import RUNS, Rig, codes, log

POINTS = [56, 58, 60, 62, 64, 66, 68, 70, 72]
CLEAN_BELOW = 2.5            # grey 16 ratio: clean mode ~1.9, bad 3+


def main():
    data = plugin.read()
    enabled = data.get("enabled")
    rig = Rig()
    out = {"points": POINTS, "records": []}
    path = os.path.join(RUNS, f"band-edge-{time.strftime('%Y%m%d-%H%M%S')}.json")
    g16, g128 = codes([16, 128])
    try:
        plugin.set_enabled(False)
        for rep in range(2):
            for direction, pts, start in (("up", POINTS, 45), ("down", POINTS[::-1], 120)):
                rig.screen.brightness(start)        # come from well outside
                time.sleep(2)
                for b in pts:
                    rig.screen.brightness(b)
                    time.sleep(1.5)
                    y16 = rig.read(g16, b)["Y"]
                    y128 = rig.read(g128, b)["Y"]
                    r = y16 / (y128 * (16 / 128) ** 2.2)
                    mode = "clean" if r < CLEAN_BELOW else "bad"
                    out["records"].append({"rep": rep, "dir": direction, "b": b, "ratio": r, "mode": mode})
                    log(f"rep {rep} {direction:4s} b {b}: grey 16 {r:.2f}x ({mode})")
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
    finally:
        rig.close()
        plugin.change(lambda d: d.update(enabled=enabled if enabled is not None else True), compiled=False)
    seen = {}
    for r in out["records"]:
        seen.setdefault(r["b"], set()).add(r["mode"])
    clean = [b for b in POINTS if seen.get(b) == {"clean"}]
    bad = [b for b in POINTS if seen.get(b) == {"bad"}]
    unstable = [b for b in POINTS if len(seen.get(b, ())) > 1]
    out["summary"] = {"always_clean": clean, "always_bad": bad, "unstable": unstable}
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    log(f"always clean {clean}, always bad {bad}, depends on the way there {unstable}; saved {path}")


if __name__ == "__main__":
    main()

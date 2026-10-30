"""How much room light gets into the hood? Black frames (screen at code 0,
backlight 52) at the longest exposure the runs use, N per room condition;
the condition's mean against the dark room's is the leak, compared with the
signal of grey 4 at 52/96/177 from the last accuracy sweep. Black frames are
shot once per run and reused, so light that changes during a run lands in
the readings; this says how much that can matter.
    ambient_test.py LABEL [N]     (LABEL: dark, normal, bright, ...)
    ambient_test.py --compare"""
import glob
import json
import os
import sys
import time

from measure import RUNS, Rig, log

SECONDS, ISO, STEP = 15, 6400, 52
PATH = os.path.join(RUNS, "ambient-test.json")


def shoot(label, n):
    data = json.load(open(PATH)) if os.path.exists(PATH) else {"seconds": SECONDS, "iso": ISO, "frames": {}}
    rig = Rig()
    try:
        rig.screen.brightness(STEP)
        rig.cam.set(iso=ISO, seconds=SECONDS)
        unit = rig.cam.seconds * ISO / 100
        frames = []
        for i in range(n):
            _, s = rig._shot(0, f"ambient-{label}-{i}")
            frames.append({c: s[c] / unit for c in "RGB"})
            log(f"{label} {i}: R {frames[-1]['R']:.4f}  G {frames[-1]['G']:.4f}  B {frames[-1]['B']:.4f}  (per s at ISO 100)")
    finally:
        rig.close()
    data["frames"][label] = frames
    with open(PATH, "w") as f:
        json.dump(data, f, indent=1)


def compare():
    data = json.load(open(PATH))
    mean = {k: {c: sum(f[c] for f in v) / len(v) for c in "RGB"} for k, v in data["frames"].items()}
    spread = {k: max(f["G"] for f in v) - min(f["G"] for f in v) for k, v in data["frames"].items()}
    # The newest full sweep (re-checks skip stock and backlight 52).
    sweeps = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(RUNS, "accuracy-sweep-*.json")))]
    sweep = next(s for s in reversed(sweeps) if STEP in s["steps"] and any(r["mode"] == "stock" for r in s["records"]))
    grey4 = {(r["mode"], r["step"]): r["G"] for r in sweep["records"] if r["level"] == 4}
    base = mean.get("dark")
    for k, m in mean.items():
        line = f"{k:8s} G {m['G']:.4f} (frame-to-frame {spread[k]:.4f})"
        if base and k != "dark":
            leak = m["G"] - base["G"]
            line += f"  leak {leak:+.4f}: " + ", ".join(
                f"{leak / g:+.1%} of grey 4 {mode} at {b}" for (mode, b), g in sorted(grey4.items())
                if b in (52, 96, 177) and g > 0)
        log(line)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--compare"]:
        compare()
    else:
        shoot(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)

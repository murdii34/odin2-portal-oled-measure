"""Closed loop on the profile's brightness (lift) at grey 64, 80 and 96 per
step, so the greys follow gamma 2.2 against grey 128 of the same backlight.
The accuracy sweeps found the dithered darks uniformly 1.2-1.3x too bright
at 100-310: the dither aims at the light of grey 64, which sits that much
high. Below the hand-over the plugin uses grey 64's correction for every
dark grey, so one lift there moves all of them alike; 80 and 96 get their
own so the curve has no kink. Grey 128 stays as it is (the anchor).
Settings as the sweeps: dither on, pair, gamma 2.2. Writes the active
profile (Camera) and runs/lift-cal-*.json."""
import json
import math
import os
import sys
import time

import plugin
from measure import RUNS, STATE, Rig, codes, log

STEPS = [96, 177, 310]
LEVELS = [16, 32, 64, 80, 96, 128]
# Profile level index of each grey set here (the plugin's LEVELS, in 8-bit:
# 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, ...).
SET = {64: 9, 80: 10, 96: 11}
DARK = (16, 32, 64)          # grey 64's lift answers for these together
ROUNDS = 4
TOL = 0.03                   # light within ±3%
MAX_LIFT = 50.0


def lifts(step):
    return {L: step["l"][i] or 0.0 for L, i in SET.items()}


def main():
    steps = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else STEPS
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log(f"settings backed up to {plugin.backup(os.path.join(STATE, f'settings-before-lift-{stamp}.json'))}")
    data = plugin.read()
    profile = data["profile"]
    if profile == "Factory":
        raise SystemExit("Factory is active; pick the profile to calibrate")
    keep = {k: data.get(k) for k in ("dither", "crush", "dither_temporal", "dither_temporal_ui", "dither_ui",
                                     "shadow_curve", "enabled", "engine")}
    out = {"profile": profile, "steps": steps, "levels": LEVELS, "history": []}
    path = os.path.join(RUNS, f"lift-cal-{stamp}.json")

    def push(b, new):
        def m(d):
            d.update(enabled=True, engine="reshade", dither=True, crush=0, dither_ui=True,
                     dither_temporal="pair", dither_temporal_ui=True, shadow_curve="g22")
            for st in d["steps"]:
                if st["b"] == b and new:
                    for L, v in new.items():
                        st["l"][SET[L]] = round(v, 1)
            d["profiles"][profile] = d["steps"]
        plugin.change(m)

    rig = Rig()
    rig.screen.animate = True
    try:
        for b in steps:
            step = next((st for st in plugin.read()["steps"] if st["b"] == b), None)
            if step is None:
                log(f"profile has no step {b}, skipped")
                continue
            lam = {L: 1 + v / 100 for L, v in lifts(step).items()}
            t0 = time.time() - 0.5
            rig.screen.brightness(b)
            push(b, None)
            plugin.settle(b, t0)                 # this step's correction on screen
            best = None
            for rnd in range(ROUNDS + 1):
                y = {L: rig.read(c, b)["Y"] for L, c in zip(LEVELS, codes(LEVELS))}
                r = {L: y[L] / (y[128] * (L / 128) ** 2.2) for L in LEVELS if L != 128}
                out["history"].append({"step": b, "round": rnd, "lift": {L: round((v - 1) * 100, 1) for L, v in lam.items()},
                                       "Y": y, "ratio": r})
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
                log(f"b {b} round {rnd}: lift {[round((lam[L] - 1) * 100, 1) for L in SET]}  "
                    + "  ".join(f"g{L} {r[L]:.3f}" for L in r))
                worst = max(abs(math.log(v)) for v in r.values())
                if best is None or worst < best[0]:
                    best = (worst, dict(lam), rnd)
                if worst < math.log(1 + TOL) or rnd == ROUNDS:
                    break
                # Light goes with the code value to the power 2.2; step 0.8 of
                # the way, a reading near black can be a few percent off.
                want = {64: math.exp(sum(math.log(r[L]) for L in DARK) / len(DARK)), 80: r[80], 96: r[96]}
                for L in SET:
                    lam[L] *= want[L] ** (-0.8 / 2.2)
                    lam[L] = max(1 - MAX_LIFT / 100, min(1 + MAX_LIFT / 100, lam[L]))
                push(b, {L: (v - 1) * 100 for L, v in lam.items()})
            if best[2] != rnd:
                log(f"b {b}: keeping round {best[2]}")
                push(b, {L: (v - 1) * 100 for L, v in best[1].items()})
            out.setdefault("result", {})[b] = {L: round((v - 1) * 100, 1) for L, v in best[1].items()}
            with open(path, "w") as f:
                json.dump(out, f, indent=1)
    finally:
        rig.screen.animate = False
        rig.close()
        keep["dither_temporal_ui"] = bool(keep["dither_temporal_ui"])
        plugin.change(lambda d: d.update({k: v for k, v in keep.items() if v is not None}), compiled=False)
    log(f"lifts kept in profile {profile}: {out.get('result')}; history {path}")


if __name__ == "__main__":
    main()

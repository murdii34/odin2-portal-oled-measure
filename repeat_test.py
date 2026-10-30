"""How much does a reading scatter from shot to shot near black? Grey 4 and 8
at one backlight step, dither on (still and pair), N shots each: mean and
spread of light and colour. The closed loop's single-shot rounds near grey 4
kept swinging; this says how many shots a round would need."""
import json
import os
import statistics as st
import sys
import time

import plugin
from measure import RUNS, Rig, codes, log


def main():
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 177
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    data = plugin.read()
    keep = {k: data.get(k) for k in ("dither", "crush", "dither_temporal", "dither_temporal_ui", "dither_ui", "enabled")}
    rig = Rig()
    out = {"step": step, "n": n, "records": []}
    path = os.path.join(RUNS, f"repeat-test-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    try:
        rig.screen.brightness(step)
        for mode in ("still", "pair"):
            def m(d, mode=mode):
                d.update(enabled=True, engine="reshade", dither=True, crush=0, dither_ui=True,
                         dither_temporal=False if mode == "still" else mode, dither_temporal_ui=mode != "still")
            plugin.change(m)
            rig.screen.animate = mode != "still"
            for level in (4, 8):
                ys, rgs, bgs = [], [], []
                for i in range(n):
                    r = rig.read(codes([level])[0], step)
                    out["records"].append({"mode": mode, "level": level, "shot": i, **r})
                    ys.append(r["Y"]); rgs.append(r["R"] / r["G"]); bgs.append(r["B"] / r["G"])
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
                cv = lambda v: st.pstdev(v) / st.mean(v)
                log(f"{mode:5s} grey {level}: light {st.mean(ys):.4g} ±{cv(ys):.1%}  R/G {st.mean(rgs):.3f} ±{cv(rgs):.1%}  "
                    f"B/G {st.mean(bgs):.3f} ±{cv(bgs):.1%}  ({n} shots)")
    finally:
        rig.screen.animate = False
        rig.close()
        keep["dither_temporal_ui"] = bool(keep["dither_temporal_ui"])
        plugin.change(lambda d: d.update({k: v for k, v in keep.items() if v is not None}), compiled=False)
    log(f"saved {path}")


if __name__ == "__main__":
    main()

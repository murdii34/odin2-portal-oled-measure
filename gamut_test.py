"""Does gamescope's SDR gamut wideness (Steam's colour vibrance) mix the
channels of what the shader outputs? Single-channel code 16 through the
shader and through the page, at wideness 0.5 (as set), 1.0 and 0.0."""
import json
import os
import struct
import time

import plugin
from measure import RUNS, Rig, log
from pattern_test import ATOM, CHANNELS, FX, host, show

WIDE = "GAMESCOPE_COLOR_SDR_GAMUT_WIDENESS"


def wideness(w):
    bits = struct.unpack("<I", struct.pack("<f", w))[0]
    host("xprop", "-root", "-f", WIDE, "32c", "-set", WIDE, str(bits))
    time.sleep(1.5)


def main(step=177, code=16):
    plugin.set_enabled(False)
    rig = Rig()
    out = {"step": step, "code": code, "records": []}
    path = os.path.join(RUNS, f"gamut-test-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    made = []
    try:
        rig.screen.brightness(step)
        for w in (0.5, 1.0, 0.0):
            wideness(w)
            for ch, chv in CHANNELS.items():
                made.append(show(f"oledtest_{ch}_gamut_{int(time.time() * 1000)}.fx",
                                 FX % {"on": "1.0", "hi": code, "lo": 0, "ch": chv}))
                r = rig.read(255, step)
                out["records"].append({"wideness": w, "path": "shader", "channel": ch, **r})
                log(f"w {w} shader {ch}={code}: camera R {r['R']:8.2f} G {r['G']:8.2f} B {r['B']:8.2f}")
            host("xprop", "-root", "-remove", ATOM)
            time.sleep(2)
            for ch in "RG":
                rgb = tuple(code if c == ch else 0 for c in "RGB")
                r = rig.read(rgb, step)
                out["records"].append({"wideness": w, "path": "page", "channel": ch, **r})
                log(f"w {w} page   {ch}={code}: camera R {r['R']:8.2f} G {r['G']:8.2f} B {r['B']:8.2f}")
            with open(path, "w") as f:
                json.dump(out, f, indent=1)
    finally:
        wideness(0.5)
        host("xprop", "-root", "-remove", ATOM)
        rig.close()
        for p in made:
            os.remove(p)
    log(f"wideness back at 0.5; saved {path}")


if __name__ == "__main__":
    main()

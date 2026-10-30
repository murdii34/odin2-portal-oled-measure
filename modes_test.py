"""Does the panel's low end change with the output mode? Raw greys
(correction off) at one backlight step under: the current mode (HDR on,
120 Hz), HDR off, and 60 Hz. Each switch is checked against gamescope's
feedback atoms and skipped if it didn't take."""
import json
import os
import sys
import time

import plugin
from measure import RUNS, Rig, codes, log
from pattern_test import host

LEVELS = [4, 8, 12, 16, 24, 32, 48, 64, 128]


def atom(name):
    r = host("xprop", "-root", name)
    v = r.stdout.strip().rsplit("=", 1)[-1].strip()
    return v if v.isdigit() else None


def set_atom(name, value):
    host("xprop", "-root", "-f", name, "32c", "-set", name, str(value))


def ctl(*args):
    return host("gamescopectl", *args)


def main():
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 177
    plugin.set_enabled(False)
    rig = Rig()
    out = {"step": step, "records": [], "modes": {}}
    path = os.path.join(RUNS, f"modes-test-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    refresh0 = atom("GAMESCOPE_DYNAMIC_REFRESH")
    in_steam0 = atom("GAMESCOPE_DYNAMIC_REFRESH_IN_STEAM")

    def run(mode):
        rig.screen.brightness(step)
        time.sleep(2)
        for level, code in zip(LEVELS, codes(LEVELS)):
            r = rig.read(code, step)
            out["records"].append({"mode": mode, "level": level, **r})
            log(f"{mode:8s} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  Y {r['Y']:.4g}")
            with open(path, "w") as f:
                json.dump(out, f, indent=1)

    try:
        out["modes"]["base"] = {"hdr": atom("GAMESCOPE_DISPLAY_HDR_ENABLED"),
                                "refresh": atom("GAMESCOPE_DISPLAY_REFRESH_RATE_FEEDBACK")}
        log(f"base mode: {out['modes']['base']}")
        run("base")
        # HDR off
        ctl("hdr_enabled", "0")
        time.sleep(4)
        hdr = atom("GAMESCOPE_DISPLAY_HDR_ENABLED")
        out["modes"]["sdr"] = {"hdr": hdr}
        if hdr == "0":
            run("sdr")
        else:
            log(f"HDR didn't switch off (feedback {hdr}); skipped")
        ctl("hdr_enabled", "1")
        time.sleep(4)
        # 60 Hz
        set_atom("GAMESCOPE_DYNAMIC_REFRESH_IN_STEAM", 1)
        set_atom("GAMESCOPE_DYNAMIC_REFRESH", 60)
        time.sleep(4)
        hz = atom("GAMESCOPE_DISPLAY_REFRESH_RATE_FEEDBACK")
        out["modes"]["60hz"] = {"refresh": hz}
        if hz == "60":
            run("60hz")
        else:
            log(f"refresh didn't switch to 60 (feedback {hz}); skipped")
    finally:
        ctl("hdr_enabled", "1")
        if in_steam0 is not None:
            set_atom("GAMESCOPE_DYNAMIC_REFRESH_IN_STEAM", in_steam0)
        if refresh0 is not None:
            set_atom("GAMESCOPE_DYNAMIC_REFRESH", refresh0)
        time.sleep(3)
        log(f"restored: HDR {atom('GAMESCOPE_DISPLAY_HDR_ENABLED')}, refresh {atom('GAMESCOPE_DISPLAY_REFRESH_RATE_FEEDBACK')}")
        rig.close()
        plugin.set_enabled(True)
    log(f"saved {path}")


if __name__ == "__main__":
    main()

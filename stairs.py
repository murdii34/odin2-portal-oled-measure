"""The bottom of Steam's slider step by step, up and down (AGENDA "Bottom-end
step-by-step photos", murdii 2026-10-30): slider 0% -> TOP% in the D-pad's 1%
steps and back down, CYCLES times, through the hand-over from the native
backlight (0-4%: raw 40-53) to floor dimming (5% = target 57 on). Unlike Rig's
other runs the plugin is left exactly as murdii uses it (snap, floor dimming):
the brightness goes through Steam's SetBrightness, which the plugin's frontend
intercepts like a slider move. Per position: the plugin's state and slider log,
the raw backlight, white + greys 64/16 (and 4/8 around the hand-over).
usage: stairs.py NAME [CYCLES [TOP]]   -> runs/NAME.json
       stairs.py --summary NAME"""
import json, os, sys, time
sys.path.insert(0, os.path.expanduser("~/projects/decky-oled-tint"))
import camera, cdp, measure, plugin
from measure import RAW, RUNS, ROI_FILE, Rig, codes, log
from screen import Screen, read_backlight

LEVELS = (255, 64, 16)
DARK_AT = (4, 5, 6)                 # slider % around the hand-over: greys 4 and 8 too
DARKS = (8, 4)
SLIDER_LOG = "/tmp/oled-slider.log"
SETTINGS = ("enabled", "dimming", "band_snap", "soft_target", "floor_backlight", "engine", "dither", "profile")


class LiveRig(Rig):
    """Rig without its plugin changes (snap and floor dimming stay on)."""
    def __init__(self):
        if not os.path.isdir(RAW):
            raise SystemExit(f"{RAW} isn't there: is the microSD mounted?")
        self.keep = True
        self.snap_was = self.dimming_was = None
        self.screen = Screen()
        self.cam = camera.Camera()
        self.black, self.exposure = {}, {}
        with open(ROI_FILE) as f:
            box = json.load(f)
        self.roi, self.screen_box = box["roi"], box["screen"]

    def read(self, code):
        """Rig.read at whatever backlight the plugin chose: its "the screen
        dimmed itself" check would otherwise set the backlight past the
        plugin's intercept."""
        b = read_backlight()
        measure.plugin_safe_backlight = lambda: b
        return super().read(code, b)


def set_slider(f):
    cdp.shared().eval(f"SteamClient.System.Display.SetBrightness({f:.4f}); true")


def settled(timeout=15.0):
    """Wait until backlight and the plugin's state hold still for 1 s
    (frontend floor check every 2 s, effect throttle ~1 s)."""
    time.sleep(2.5)
    end, last, since = time.time() + timeout, None, time.time()
    while time.time() < end:
        s = plugin._state() or {}
        now = (read_backlight(), s.get("revision"), s.get("effect"), s.get("pending"), s.get("applied"))
        if now != last:
            last, since = now, time.time()
        elif time.time() - since >= 1.0 and not now[3]:
            return True
        time.sleep(0.25)
    return False


def slider_lines(pos):
    try:
        with open(SLIDER_LOG) as f:
            f.seek(pos)
            return f.read().splitlines()[-20:], f.tell()
    except OSError:
        return [], pos


def run(name, cycles, top):
    path = os.path.join(RUNS, name + ".json")
    settings = plugin.read()
    out = {"name": name, "cycles": cycles, "top": top, "levels": list(LEVELS),
           "settings": {k: settings.get(k) for k in SETTINGS}, "conditions": [plugin.conditions()], "records": []}
    log(f"settings {out['settings']}")
    up = list(range(0, top + 1))
    path_pct = []
    for c in range(1, cycles + 1):
        path_pct += [(c, "up", p) for p in up] + [(c, "down", p) for p in reversed(up[:-1])]
    rig = LiveRig()
    try:
        set_slider(0)
        settled()
        try:
            logpos = os.path.getsize(SLIDER_LOG)
        except OSError:
            logpos = 0
        for i, (c, way, p) in enumerate(path_pct):
            set_slider(p / 100)
            ok = settled()
            lines, logpos = slider_lines(logpos)
            st = plugin._state() or {}
            s = plugin.read()
            b = read_backlight()
            pos = {"i": i, "cycle": c, "way": way, "pct": p, "settled": ok, "backlight": b,
                   "soft_target": s.get("soft_target"), "state": st, "slider_log": lines, "shots": {}}
            levels = LEVELS + (DARKS if p in DARK_AT else ())
            for level, code in zip(levels, codes(levels)):
                r = rig.read(code)
                if level != 255:
                    r.pop("grid", None)      # one grid per position (white) keeps the file small
                pos["shots"][level] = r
            pos["backlight_after"] = read_backlight()
            out["records"].append(pos)
            log(f"c{c} {way:<4} {p:>2}%  bl {b:>4}->{pos['backlight_after']:<4} target {pos['soft_target']}  "
                + "  ".join(f"g{l} Y {r['Y']:.4g} R/G {r['R'] / r['G']:.3f}" for l, r in pos["shots"].items()))
            with open(path, "w") as f:
                json.dump(out, f, indent=1)
    finally:
        rig.close()
        out["conditions"].append(plugin.conditions())
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    log(f"saved {path}")


def summary(name):
    d = json.load(open(os.path.join(RUNS, name + ".json")))
    by = {}
    for r in d["records"]:
        by.setdefault((r["pct"], r["way"]), []).append(r)
    print("pct way   n  backlight      target   white Y (mean, spread)   g64/white  g16/white   g16 R/G")
    for (p, way), rs in sorted(by.items(), key=lambda k: (k[0][0], k[0][1] != "up")):
        w = [r["shots"]["255"]["Y"] if "255" in r["shots"] else r["shots"][255]["Y"] for r in rs]
        sh = lambda r, l: r["shots"].get(str(l)) or r["shots"].get(l)
        m = sum(w) / len(w)
        spread = (max(w) - min(w)) / m if m else 0
        g64 = sum(sh(r, 64)["Y"] / sh(r, 255)["Y"] for r in rs) / len(rs)
        g16 = sum(sh(r, 16)["Y"] / sh(r, 255)["Y"] for r in rs) / len(rs)
        rg16 = sum(sh(r, 16)["R"] / sh(r, 16)["G"] for r in rs) / len(rs)
        bls = sorted({r["backlight"] for r in rs})
        tgs = sorted({r["soft_target"] for r in rs}, key=str)
        print(f"{p:>3} {way:<4} {len(rs):>2}  {str(bls):<14} {str(tgs):<8} {m:>10.4g} {spread:>6.1%}   "
              f"{g64:>9.4f}  {g16:>9.5f}   {rg16:.3f}")


if __name__ == "__main__":
    if sys.argv[1] == "--summary":
        summary(sys.argv[2])
    else:
        run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3, int(sys.argv[3]) if len(sys.argv) > 3 else 25)

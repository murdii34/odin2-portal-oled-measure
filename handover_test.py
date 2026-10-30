"""The handover at the bottom of the band, in numbers: grey 255/128/32 light and
colour at the panel's own low backlights (40..56, below where floor dimming
takes over) against floor-dimmed targets 57..80 at backlight 543. A smooth
slider needs the two sides to meet: Y(255) should follow the panel's white
curve across 57 without a step. usage: handover_test.py [NAME] -> runs/NAME.json"""
import json, os, sys, time
sys.path.insert(0, os.path.expanduser("~/decky-oled-tint"))
import plugin
from measure import RUNS, Rig, codes, log
import main as plug

name = sys.argv[1] if len(sys.argv) > 1 else "handover-" + time.strftime("%Y%m%d-%H%M")
levels = [32, 128, 255]
real = [40, 44, 48, 52, 56]
soft = [57, 60, 64, 70, 80, 100]
with plugin.switches_kept():
    keep_target = plugin.read().get("soft_target")
    rig = Rig()
    out = {"name": name, "profile": None, "records": []}
    path = os.path.join(RUNS, name + ".json")
    try:
        plugin.change(lambda d: d.update(enabled=True, engine="reshade", dither=False, crush=0, dimming="soft",
                                         band_snap=False, soft_target=543))
        out["profile"] = plugin.read().get("profile")
        out["conditions"] = [plugin.conditions()]      # RESULTS 28: what else the screen ran under
        def shoot(kind, T, b):
            for level, code in zip(levels, codes(levels)):
                r = rig.read(code, b)
                out["records"].append({"kind": kind, "target": T, "backlight": b, "level": level, **r})
                log(f"{kind} {T:4d} (backlight {b}) grey {level:3d}: R/G {r['R'] / r['G']:.3f} B/G {r['B'] / r['G']:.3f} Y {r['Y']:.4g}")
                json.dump(out, open(path, "w"), indent=1)
        # real low backlights: the plugin's ordinary curves, no dimming (target = the backlight)
        for b in real:
            t0 = time.time() - 0.5
            plugin.change(lambda d, b=b: d.update(soft_target=b), compiled=False)
            rig.screen.brightness(b)
            time.sleep(1.0)
            plugin.settle(b, t0)
            shoot("real", b, b)
        # floor-dimmed targets at the floor
        rig.screen.brightness(543)
        for T in soft:
            plugin.change(lambda d, T=T: d.update(soft_target=T), compiled=False)
            time.sleep(0.5)
            shoot("floor", T, 543)
    finally:
        try:
            plugin.change(lambda d: d.update(soft_target=keep_target), compiled=False)
        finally:
            rig.close()
    rows = []
    for r in out["records"]:
        T = r["target"]
        rows.append({"kind": r["kind"], "target": T, "level": r["level"], "Y": r["Y"],
                     "white_curve": plug.white_at(T)})
    out["summary"] = rows
    try:
        out.setdefault("conditions", []).append(plugin.conditions())   # and at the end
    except Exception as e:
        log(f"note: end conditions not read: {e}")
    json.dump(out, open(path, "w"), indent=1)
    log(f"saved {path}")

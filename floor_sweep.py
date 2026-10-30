"""Floor dimming accuracy: backlight held at the floor (543), the picture dimmed
to targets 57..542 by the plugin's ReShade ladder. Per target and grey level:
colour (R/G, B/G) against a7iv-ref, shape against the undimmed floor, and the
light against what the panel's own white curve says that target should give.
usage: [OLED_FLOOR=600] floor_sweep.py [NAME [N_TARGETS [LEVELS]]]  -> runs/NAME.json"""
import json, math, os, sys, time
sys.path.insert(0, os.path.expanduser("~/projects/decky-oled-tint"))
import plugin
from measure import RUNS, Rig, codes, log
import main as plug     # the plugin's own white curve (white_at)

FLOOR = int(os.environ.get("OLED_FLOOR", 543))     # the plugin's floor_backlight for this run (RESULTS 28)
name = sys.argv[1] if len(sys.argv) > 1 else "floor-sweep-" + time.strftime("%Y%m%d-%H%M")
n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
levels = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else plugin.LEVELS
targets = [FLOOR] + sorted({round(57 * (542 / 57) ** (i / (n - 1))) for i in range(n)}, reverse=True)

with plugin.switches_kept():
    keep_target = plugin.read().get("soft_target")
    rig = Rig()                                   # also switches snap/dimming off for the run
    out = {"name": name, "floor": FLOOR, "levels": levels, "targets": targets, "records": []}
    path = os.path.join(RUNS, name + ".json")
    try:
        plugin.change(lambda d: d.update(enabled=True, engine="reshade", dither=False, crush=0,
                                         dimming="soft", soft_target=FLOOR, band_snap=False,
                                         floor_backlight=FLOOR))
        rig.screen.brightness(FLOOR)
        out["profile"] = plugin.read().get("profile")
        out["conditions"] = [plugin.conditions()]      # RESULTS 28: what else the screen ran under
        for T in targets:
            plugin.change(lambda d, T=T: d.update(soft_target=T), compiled=(T in targets[:2]))     # the floor, and the first dimmed target (the ladder's compile)
            time.sleep(0.5)
            for level, code in zip(levels, codes(levels)):
                r = rig.read(code, FLOOR)
                out["records"].append({"target": T, "level": level, **r})
                log(f"target {T:4d} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  Y {r['Y']:.4g}")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
    finally:
        try:
            plugin.change(lambda d: d.update(soft_target=keep_target), compiled=False)
        finally:
            rig.close()
    ref = {r["level"]: r for r in json.load(open(os.path.join(RUNS, "a7iv-ref.json")))["records"] if r["step"] == 4096}
    base = {r["level"]: r for r in out["records"] if r["target"] == FLOOR}
    rows = []
    for r in out["records"]:
        if r["target"] == FLOOR or r["level"] not in base or r["level"] not in ref:
            continue
        rg = r["R"] / r["G"] / (ref[r["level"]]["R"] / ref[r["level"]]["G"]) - 1
        bg = r["B"] / r["G"] / (ref[r["level"]]["B"] / ref[r["level"]]["G"]) - 1
        want = base[r["level"]]["Y"] * plug.white_at(r["target"]) / plug.white_at(FLOOR)
        rows.append({"target": r["target"], "level": r["level"], "rg": rg, "bg": bg, "light": r["Y"] / want})
    out["accuracy"] = rows
    try:
        out.setdefault("conditions", []).append(plugin.conditions())   # and at the end
    except Exception as e:
        log(f"note: end conditions not read: {e}")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    log(f"saved {path}")

"""Compare two floor sweeps (before / after a calibration) and keep the better
profile active. usage: decide_profile.py BEFORE AFTER OLDPROFILE NEWPROFILE
Better = lower mean colour error by at least 1 point AND mean light error not worse by >2 points,
over the dim half of the targets and greys 4-96 (what the calibration targets)."""
import json, math, os, sys
import plugin
from measure import RUNS, log

def score(name):
    d = json.load(open(os.path.join(RUNS, name + ".json")))
    rows = [r for r in d["accuracy"] if r["level"] <= 96]
    col = sum(max(abs(r["rg"]), abs(r["bg"])) for r in rows) / len(rows)
    lit = sum(abs(math.log(r["light"])) for r in rows) / len(rows)
    return col, lit, len(rows)

before, after, old, new = sys.argv[1:5]
b, a = score(before), score(after)
log(f"before {before}: colour {b[0]:.1%} light {b[1]:.1%} ({b[2]} cells)")
log(f"after  {after}: colour {a[0]:.1%} light {a[1]:.1%} ({a[2]} cells)")
# Repeating the same state moved the numbers by ~0.5 points (2026-10-27): ask for more than noise.
better = a[0] < b[0] - 0.01 and a[1] <= b[1] + 0.02
keep = new if better else old
plugin.change(lambda d: (d.update(profile=keep), d.update(steps=json.loads(json.dumps(d["profiles"][keep])))), compiled=False)
log(f"{'KEEPING the new' if better else 'REVERTING to the old'} profile: {keep}")
json.dump({"before": b, "after": a, "kept": keep}, open(os.path.join(RUNS, "decide-profile.json"), "w"))

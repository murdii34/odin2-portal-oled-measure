"""The 2026-10-30 camera session's verdict (RESULTS 28), in plain words:
did the rig move, and does a floor of 600 keep the darkest greys out of the
band's look that 543 sometimes shows?
usage: session_verdict.py RIGCHECK SWEEP543 SWEEP600  (names in runs/)"""
import json, os, statistics, sys
RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")     # no measure import: runs without numpy

rig, s543, s600 = (json.load(open(os.path.join(RUNS, n + ".json"))) for n in sys.argv[1:4])
ref = {r["level"]: r for r in json.load(open(os.path.join(RUNS, "a7iv-ref.json")))["records"] if r.get("step") == 4096}
rg = lambda r: r["R"] / r["G"]
out = {"rig": {}, "floor": {}, "accuracy": {}}

now = {r["level"]: r for r in rig["records"]}
for g in sorted(set(now) & set(ref)):
    out["rig"][g] = {"rg": rg(now[g]) / rg(ref[g]) - 1, "light": now[g]["Y"] / ref[g]["Y"]}
hi = [v for g, v in out["rig"].items() if g >= 32]
moved = any(abs(v["light"] - 1) > 0.05 or abs(v["rg"]) > 0.03 for v in hi)

for name, d in (("543", s543), ("600", s600)):
    at = {r["level"]: r for r in d["records"] if r["target"] == d["floor"]}
    out["floor"][name] = {g: rg(at[g]) / rg(ref[g]) - 1 for g in (4, 8, 16, 32) if g in at and g in ref}
    acc = d.get("accuracy") or []
    col = lambda sel: statistics.median(max(abs(r["rg"]), abs(r["bg"])) for r in acc if sel(r)) if any(sel(r) for r in acc) else None
    lit = lambda sel: statistics.median(abs(r["light"] - 1) for r in acc if sel(r)) if any(sel(r) for r in acc) else None
    out["accuracy"][name] = {"colour_all": col(lambda r: True), "light_all": lit(lambda r: True),
                             "colour_grey4_8": col(lambda r: r["level"] <= 8)}

lines = []
lines.append("Rig: " + ("MOVED since the reference (light or colour off at grey 32+): compare within this session only."
                        if moved else "unchanged against the reference (grey 32+ within 5% light, 3% colour)."))
for name in ("543", "600"):
    f = out["floor"][name]
    lines.append(f"Floor {name}, undimmed, red/green against the reference: "
                 + ", ".join(f"grey {g} {v:+.0%}" for g, v in f.items()))
in_band = {n: out["floor"][n].get(4, 0) < -0.25 for n in ("543", "600")}
if in_band["543"] and not in_band["600"]:
    lines.append("Verdict: 543 shows the band's green darks today, 600 doesn't. Raise the default floor (floor_backlight).")
elif in_band["543"] and in_band["600"]:
    lines.append("Verdict: both floors show green darks. Not the band edge alone: look at the rig and the panel's low end.")
elif not in_band["543"]:
    lines.append("Verdict: 543 is clean today (the edge wanders night to night). Compare the accuracy below; "
                 "600 is the safer floor if it costs little.")
for name in ("543", "600"):
    a = out["accuracy"][name]
    fmt = lambda v: f"{v:.1%}" if v is not None else "-"
    lines.append(f"Floor {name} dimming accuracy (median): colour {fmt(a['colour_all'])}, light {fmt(a['light_all'])}, "
                 f"grey 4-8 colour {fmt(a['colour_grey4_8'])}")
out["verdict"] = lines
with open(os.path.join(RUNS, "session-20261030-verdict.json"), "w") as f:
    json.dump(out, f, indent=1)
print("\n".join(lines))

"""The darks drift run (state/drift-run.sh) in one table: per round the phase,
temperatures, uptime, and for each dark grey its colour (R/G) and its light
relative to grey 255 in the same round (cancels camera gain), then how well
grey 4-8's R/G follows each temperature. usage: drift_summary.py TAG"""
import glob, json, os, sys

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
DARKS = (4, 6, 8, 12, 16)


def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sxy / (sx * sy) if sx and sy else float("nan")


def main(tag):
    cond = {}
    with open(os.path.join(RUNS, tag + "-log.jsonl")) as f:
        for line in f:
            c = json.loads(line)
            cond[c["round"]] = c
    rows = []
    for path in sorted(glob.glob(os.path.join(RUNS, tag + "-r[0-9][0-9].json"))):
        r = int(path[-7:-5])
        recs = {x["level"]: x for x in json.load(open(path))["records"]}
        if 255 not in recs or r not in cond:
            continue
        y255 = recs[255]["Y"]
        rows.append((r, cond[r], {l: (recs[l]["R"] / recs[l]["G"], recs[l]["Y"] / y255) for l in DARKS if l in recs}))
    t0 = rows[0][1]["time"] if rows else 0
    head = "rnd phase   min  up_h  cpu  bat  pmic | " + "  ".join(f"g{l:<2} R/G  Y/255  " for l in DARKS)
    print(head)
    for r, c, g in rows:
        print(f"{r:>3} {c['phase']:<6} {(c['time'] - t0) / 60:>4.0f} {c['uptime_h']:>5.1f} {c['cpu_max']:>4.0f} "
              f"{c['battery']:>4.0f} {c['pmic']:>5.0f} | "
              + "  ".join(f"{g[l][0]:>7.3f} {g[l][1]:>8.2e}" if l in g else " " * 16 for l in DARKS))
    print("\ncorrelation of R/G with:   cpu_max  battery  pmic  uptime")
    for l in DARKS:
        rg = [g[l][0] for _, _, g in rows if l in g]
        cs = [c for _, c, g in rows if l in g]
        print(f"  grey {l:<3}                " + "  ".join(
            f"{corr([c[k] for c in cs], rg):>6.2f}" for k in ("cpu_max", "battery", "pmic", "uptime_h")))


if __name__ == "__main__":
    main(sys.argv[1])

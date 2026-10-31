"""The Odin 2 Portal panel spec sheet: a self-contained HTML page with inline
SVG charts, built from the measurement JSONs in ../runs. Rebuild after new
measurements: python3 report/make_report.py  (writes report/index.html)."""
import glob
import html
import json
import math
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(os.path.dirname(HERE), "runs")


def load(pattern):
    files = sorted(glob.glob(os.path.join(RUNS, pattern)))
    return json.load(open(files[-1])) if files else None


def sweeps():
    """Every accuracy sweep, oldest first, with its file's time."""
    out = []
    for f in sorted(glob.glob(os.path.join(RUNS, "accuracy-sweep-*.json"))):
        d = json.load(open(f))
        if d.get("summary"):
            d["when"] = os.path.basename(f)[15:28]
            out.append(d)
    return out


def latest_cells(mode):
    """The newest measurement of each (step, level) for a mode, across sweeps
    (a re-check after a calibration covers only some steps)."""
    cells = {}
    for d in sweeps():
        for c in d["cells"].get(mode, []):
            cells[(c["step"], c["level"])] = c
    return cells


def settings():
    try:
        return json.load(open(os.path.expanduser("~/homebrew/settings/decky-oled-tint/settings.json")))
    except (OSError, ValueError):
        return {}


def esc(s):
    return html.escape(str(s))


# ---- tiny SVG chart kit -------------------------------------------------

W, H = 640, 300
PAD = dict(l=56, r=150, t=16, b=44)
MARKS = ("circle", "square", "diamond")
CH = {"R": ("Red", "var(--s-red)", "circle"), "G": ("Green", "var(--s-green)", "square"),
      "B": ("Blue", "var(--s-blue)", "diamond")}


def scale(v, lo, hi, a, b, log=False):
    if log:
        v, lo, hi = math.log10(v), math.log10(lo), math.log10(hi)
    return a + (v - lo) / (hi - lo) * (b - a)


def ticks(lo, hi, log=False, n=5):
    if log:
        out = []
        for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1):
            for m in (1, 2, 5):
                v = m * 10 ** e
                if lo <= v <= hi:
                    out.append(v)
        return out
    step = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(step))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= step), default=step)
    v = math.ceil(lo / step) * step
    out = []
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def fmt(v):
    if v == 0:
        return "0"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.0f}"
    if abs(v) >= 1:
        return f"{v:.2g}" if v != int(v) else f"{int(v)}"
    return f"{v:.2g}"


def marker(kind, x, y, color, tip):
    t = f'<title>{esc(tip)}</title>'
    if kind == "square":
        return f'<rect x="{x-4:.1f}" y="{y-4:.1f}" width="8" height="8" rx="1.5" fill="{color}" stroke="var(--surface)" stroke-width="2" data-tip="{esc(tip)}">{t}</rect>'
    if kind == "diamond":
        return (f'<path d="M{x:.1f},{y-5:.1f} L{x+5:.1f},{y:.1f} L{x:.1f},{y+5:.1f} L{x-5:.1f},{y:.1f} Z" fill="{color}" '
                f'stroke="var(--surface)" stroke-width="2" data-tip="{esc(tip)}">{t}</path>')
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="var(--surface)" stroke-width="2" data-tip="{esc(tip)}">{t}</circle>'


def line_chart(series, xlabel, ylabel, xlog=False, ylog=False, xr=None, yr=None, ref=None, yfmt=fmt, xfmt=fmt):
    """series: [(name, color, marker, [(x, y), ...])]; ref: (y, label) dashed line."""
    xs = [x for _, _, _, pts in series for x, _ in pts]
    ys = [y for _, _, _, pts in series for _, y in pts] + ([ref[0]] if ref else [])
    x0, x1 = xr or (min(xs), max(xs))
    y0, y1 = yr or (min(ys), max(ys))
    if not ylog and not yr:
        span = (y1 - y0) or 1
        y0, y1 = y0 - span * 0.08, y1 + span * 0.08
    L, R, T, B = PAD["l"], W - PAD["r"], PAD["t"], H - PAD["b"]
    sx = lambda v: scale(v, x0, x1, L, R, xlog)
    sy = lambda v: scale(v, y0, y1, B, T, ylog)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart">']
    for v in ticks(y0, y1, ylog):
        y = sy(v)
        out.append(f'<line x1="{L}" x2="{R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{L-8}" y="{y+4:.1f}" class="tick" text-anchor="end">{yfmt(v)}</text>')
    for v in ticks(x0, x1, xlog):
        x = sx(v)
        out.append(f'<text x="{x:.1f}" y="{B+18}" class="tick" text-anchor="middle">{xfmt(v)}</text>')
    out.append(f'<line x1="{L}" x2="{R}" y1="{B}" y2="{B}" class="axis"/>')
    out.append(f'<text x="{(L+R)/2}" y="{H-6}" class="label" text-anchor="middle">{esc(xlabel)}</text>')
    out.append(f'<text x="14" y="{(T+B)/2}" class="label" text-anchor="middle" transform="rotate(-90 14 {(T+B)/2})">{esc(ylabel)}</text>')
    if ref:
        y = sy(ref[0])
        out.append(f'<line x1="{L}" x2="{R}" y1="{y:.1f}" y2="{y:.1f}" class="ref"/>'
                   f'<text x="{R-4}" y="{y-5:.1f}" class="reflabel" text-anchor="end">{esc(ref[1])}</text>')
    ends = []
    for name, color, mk, pts in series:
        pts = sorted(pts)
        d = " ".join(f'{"M" if i == 0 else "L"}{sx(x):.1f},{sy(y):.1f}' for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for x, y in pts:
            out.append(marker(mk, sx(x), sy(y), color, f"{name}: {xfmt(x)} → {yfmt(y)}"))
        ends.append([sy(pts[-1][1]), name, color])
    # Direct labels at the line ends, nudged apart.
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 13)
    for y, name, color in ends:
        out.append(f'<text x="{R+6}" y="{y+4:.1f}" class="dlabel" fill="var(--ink-2)">'
                   f'<tspan fill="{color}">■</tspan> {esc(name)}</text>')
    out.append("</svg>")
    return "".join(out)


def bar_chart(groups, names, colors, ylabel, ref=None, yr=None, yfmt=fmt):
    """groups: [(group label, [value per name])]."""
    vals = [v for _, vs in groups for v in vs if v is not None] + ([ref[0]] if ref else [])
    y0, y1 = yr or (0, max(vals) * 1.12)
    L, R, T, B = PAD["l"], W - PAD["r"], PAD["t"], H - PAD["b"]
    sy = lambda v: scale(v, y0, y1, B, T)
    gw = (R - L) / len(groups)
    bw = min(22, (gw - 16) / len(names))
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart">']
    for v in ticks(y0, y1):
        y = sy(v)
        out.append(f'<line x1="{L}" x2="{R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{L-8}" y="{y+4:.1f}" class="tick" text-anchor="end">{yfmt(v)}</text>')
    for gi, (g, vs) in enumerate(groups):
        cx = L + gw * (gi + 0.5)
        x = cx - bw * len(names) / 2
        for i, v in enumerate(vs):
            if v is None:
                continue
            y = sy(v)
            h = max(0.0, sy(y0) - y)
            out.append(f'<rect x="{x + i * bw + 1:.1f}" y="{y:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" rx="3" '
                       f'fill="{colors[i]}" data-tip="{esc(g)} · {esc(names[i])}: {yfmt(v)}">'
                       f'<title>{esc(g)} · {esc(names[i])}: {yfmt(v)}</title></rect>')
        out.append(f'<text x="{cx:.1f}" y="{B+18}" class="tick" text-anchor="middle">{esc(g)}</text>')
    out.append(f'<line x1="{L}" x2="{R}" y1="{B}" y2="{B}" class="axis"/>')
    out.append(f'<text x="14" y="{(T+B)/2}" class="label" text-anchor="middle" transform="rotate(-90 14 {(T+B)/2})">{esc(ylabel)}</text>')
    if ref:
        y = sy(ref[0])
        out.append(f'<line x1="{L}" x2="{R}" y1="{y:.1f}" y2="{y:.1f}" class="ref"/>'
                   f'<text x="{R-4}" y="{y-5:.1f}" class="reflabel" text-anchor="end">{esc(ref[1])}</text>')
    ly = T + 4
    for name, color in zip(names, colors):
        out.append(f'<text x="{R+6}" y="{ly+8}" class="dlabel" fill="var(--ink-2)"><tspan fill="{color}">■</tspan> {esc(name)}</text>')
        ly += 16
    out.append("</svg>")
    return "".join(out)


def heatmap(grid, title, lo=0.4, hi=2.5):
    """12x5 ratio grid around 1.0, diverging blue (darker than mean) to red
    (brighter), log scale, grey at 1."""
    rows, cols = len(grid), len(grid[0])
    cw, chh = 44, 34
    w, h = cols * cw + 70, rows * chh + 40
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" class="heat"><text x="0" y="12" class="label">{esc(title)}</text>']
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            t = max(-1.0, min(1.0, math.log(v) / math.log(hi if v > 1 else 1 / lo)))
            out.append(f'<rect x="{c*cw+1}" y="{r*chh+20}" width="{cw-2}" height="{chh-2}" rx="3" '
                       f'style="fill: color-mix(in oklab, var(--mid) {100-abs(t)*100:.0f}%, {"var(--hot)" if t > 0 else "var(--cold)"})" '
                       f'data-tip="column {c+1}, row {r+1}: {v:.2f}× the screen mean"><title>{v:.2f}×</title></rect>')
            if v >= 1.6 or v <= 0.62:
                out.append(f'<text x="{c*cw+cw/2}" y="{r*chh+20+chh/2+4}" class="cell" text-anchor="middle">{v:.1f}</text>')
    out.append(f'<text x="{cols*cw+6}" y="34" class="tick">brighter</text><text x="{cols*cw+6}" y="{rows*chh+16}" class="tick">darker</text>')
    out.append("</svg>")
    return "".join(out)


def table(headers, rows):
    t = ["<table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>"]
    for r in rows:
        t.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>")
    t.append("</tbody></table>")
    return "".join(t)


def figure(fid, title, lede, svg, data_headers=None, data_rows=None, note=None):
    parts = [f'<section class="card" id="{fid}"><h2>{esc(title)}</h2><p class="lede">{lede}</p>{svg}']
    if note:
        parts.append(f'<p class="note">{note}</p>')
    if data_headers:
        parts.append(f'<details><summary>Data table</summary>{table(data_headers, data_rows)}</details>')
    parts.append("</section>")
    return "".join(parts)


# ---- the measurements ----------------------------------------------------

def ratios_vs_ref(rec, ref, L):
    return (rec[L]["R"] / rec[L]["G"] / (ref[L]["R"] / ref[L]["G"]) - 1,
            rec[L]["B"] / rec[L]["G"] / (ref[L]["B"] / ref[L]["G"]) - 1)


def main():
    cards = []
    ref = {r["level"]: r for r in load("hood-ref.json")["records"]}

    # 1. The pedestal: single-subpixel light per code at 177 (vibrance 1.0).
    floor = {}
    for n in ("hood-floor-177.json", "hood-floor-177b.json"):
        d = load(n)
        for r in d["records"]:
            if r["code"] > 0:
                floor.setdefault(r["channel"], {})[r["code"]] = r[r["channel"]]
    series, rows = [], []
    for c in "RGB":
        base = floor[c][32]
        pts = [(k, v / base) for k, v in sorted(floor[c].items()) if k <= 64]
        series.append((CH[c][0] + " subpixel", CH[c][1], CH[c][2], pts))
    for k in sorted(floor["G"]):
        if k <= 64:
            rows.append([k] + [f"{floor[c][k] / floor[c][32]:.3f}" for c in "RGB"] + [f"{(k / 32) ** 2.2:.4f}"])
    g22 = [(k, (k / 32) ** 2.2) for k in sorted(floor["G"]) if k <= 64]
    svg = line_chart(series + [("gamma 2.2", "var(--ink-3)", "circle", g22)], "code (0-255)", "light vs code 32 (log)",
                     xlog=True, ylog=True, yr=(0.0005, 6))
    cards.append(figure("pedestal", "The pedestal: each subpixel jumps at code 2",
                        "Backlight 177, correction off, one subpixel colour at a time. A normal panel follows the grey line; this one jumps "
                        "from almost off at code 1 to a far too bright minimum at code 2, green the most. That is the green cast and the "
                        "glowing black.", svg, ["code", "red", "green", "blue", "gamma 2.2"], rows))

    # 2. Before / after at 177: the sweeps' newest stock and corrected cells,
    # light against gamma 2.2 from grey 128 of the same backlight (as in the
    # accuracy section), colour against the same grey at full brightness.
    stock_c, corr_c = latest_cells("stock"), latest_cells("corrected")
    lv = [L for L in (4, 8, 16, 32) if (177, L) in stock_c and (177, L) in corr_c]
    off = {L: stock_c[(177, L)] for L in lv}
    on = {L: corr_c[(177, L)] for L in lv}
    light = lambda x, L: x[L]["light"]
    svg = line_chart([("uncorrected", "var(--s-orange)", "square", [(L, light(off, L)) for L in lv]),
                      ("corrected", "var(--s-blue)", "circle", [(L, light(on, L)) for L in lv])],
                     "grey level", "light vs gamma 2.2 (log)", ylog=True, yr=(0.5, 60), ref=(1.0, "target"),
                     yfmt=lambda v: f"{v:g}×")
    rows = [[L, f"{light(off, L):.2f}×", f"{light(on, L):.2f}×",
             f"{off[L]['rg']:+.0%} / {off[L]['bg']:+.0%}", f"{on[L]['rg']:+.0%} / {on[L]['bg']:+.0%}"] for L in lv]
    if lv:
        cards.append(figure("fix", "Before and after, at backlight 177",
                            f"The worst brightness step. Uncorrected, grey 4 glows at {light(off, 4):.0f}× its gamma 2.2 light "
                            f"(from grey 128 of the same backlight); with the plugin (dither moving per frame, as in games) it lands "
                            f"at {light(on, 4):.2f}×. Newest accuracy sweep readings.", svg,
                            ["grey", "light, uncorrected", "light, corrected", "R/G, B/G uncorrected", "R/G, B/G corrected"], rows))

    # 3. Colour error before / after.
    svg = line_chart([("uncorrected", "var(--s-orange)", "square", [(L, off[L]["rg"] * 100) for L in lv]),
                      ("corrected", "var(--s-blue)", "circle", [(L, on[L]["rg"] * 100) for L in lv])],
                     "grey level", "red/green vs neutral (%)", yr=(-55, 15), ref=(0, "neutral"), yfmt=lambda v: f"{v:+.0f}%")
    cards.append(figure("colour", "The green cast, as numbers",
                        "Red relative to green, against the same grey at full brightness. Negative means greener.", svg))

    # 4. Tone curve at full brightness and 543.
    t4 = {r["level"]: r for r in load("tone-4096-b.json")["records"]}
    t5 = {r["level"]: r for r in load("tone-543-b.json")["records"]}
    tone = lambda t, L: t[L]["Y"] / t[255]["Y"] / (L / 255) ** 2.2
    lv = [L for L in sorted(t4) if L < 255 and L >= 4]
    svg = line_chart([("backlight 4096", "var(--s-blue)", "circle", [(L, tone(t4, L)) for L in lv]),
                      ("backlight 543", "var(--s-orange)", "square", [(L, tone(t5, L)) for L in lv])],
                     "grey level", "light vs gamma 2.2 (log)", xlog=True, ylog=True, yr=(0.8, 2.6), ref=(1.0, "gamma 2.2"),
                     yfmt=lambda v: f"{v:g}×")
    cards.append(figure("tone", "Tone curve: gamma 2.2 from grey 32 up",
                        "Correction off. Within ±3% of gamma 2.2 from grey 32 to 255 at full brightness; the deepest shadows are lifted "
                        "(grey 8 about 1.5×, grey 4 about 2×), a little more at 543.", svg,
                        ["grey", "4096", "543"], [[L, f"{tone(t4, L):.2f}×", f"{tone(t5, L):.2f}×"] for L in lv]))

    # 5. Pattern blur (rows vs columns).
    pt = load("pattern-test-177-*.json")
    if pt:
        solid = {r["channel"]: r[r["channel"]] for r in pt["records"] if r["pattern"] == "solid"}
        names = {"checker1": "checker 1×1", "checker2": "checker 2×2", "checker4": "checker 4×4",
                 "vstripe1": "columns", "hstripe1": "rows"}
        groups = []
        for p, label in names.items():
            vals = []
            for c in "RGB":
                rec = [r for r in pt["records"] if r["channel"] == c and r["pattern"] == p]
                vals.append(rec[0][c] / solid[c] if rec else None)
            groups.append((label, vals))
        svg = bar_chart(groups, [CH[c][0] for c in "RGB"], [CH[c][1] for c in "RGB"], "share of solid light", ref=(0.5, "honest 0.5"),
                        yr=(0, 0.75), yfmt=lambda v: f"{v:.2f}")
        cards.append(figure("patterns", "The panel blurs from row to row",
                            "Half the pixels lit at code 2 should give half the light. Columns are honest; alternating rows lose up to 40% "
                            "(the panel is natively portrait and shares subpixels along its rows). Hence dither cells 1 pixel wide and 4 "
                            "rows tall. (Measured at vibrance 0.5; the shares are relative, so the conclusion holds.)", svg,
                            ["pattern"] + [CH[c][0] for c in "RGB"], [[g] + [f"{v:.3f}" if v else "-" for v in vs] for g, vs in groups]))

    # 6. Vibrance mixes the channels.
    gm = load("gamut-test-177-*.json")
    if gm:
        groups = []
        for w in (1.0, 0.5, 0.0):
            rec = [r for r in gm["records"] if r["wideness"] == w and r.get("path") == "shader" and r["channel"] == "R"]
            if rec:
                groups.append((f"vibrance {w}", [rec[0]["G"] / rec[0]["R"]]))
        svg = bar_chart(groups, ["green per red"], ["var(--s-green)"], "green seen in a red-only patch",
                        ref=(0.19, "pure red (filter overlap)"), yr=(0, 4), yfmt=lambda v: f"{v:.1f}")
        cards.append(figure("vibrance", "Steam's colour vibrance mixes the channels",
                            "A red-only code 16 at backlight 177. At vibrance 1.0 the camera sees only its filter overlap (0.19); at 0.5 "
                            "(default) gamescope's gamut mapping sends 3× as much green. Greys are untouched, which is why it hid; the dither, "
                            "which drives each subpixel exactly, can't survive it. The plugin holds 1.0 while dithering.", svg))

    # 7. Uniformity at low drive.
    n2 = load("night2-check-177.json")
    if n2:
        recs = {r["level"]: r for r in n2["records"]}
        heat = []
        for L in (4, 48):
            g = recs[L]["grid"]
            cells = [[sum(c) for c in row] for row in g]
            m = sum(sum(r) for r in cells) / (len(cells) * len(cells[0]))
            # The camera is turned 180°: flip both axes to show the screen as you see it.
            heat.append(heatmap([[v / m for v in row][::-1] for row in cells][::-1], f"grey {L}"))
        cards.append(figure("uniformity", "Uneven only near black",
                            "Light per area against the screen's mean, backlight 177, dithered, as seen from the front. At grey 48 within "
                            "about ±5%; at grey 4 from 0.4× to 2.4× (bottom left brightest). Confirmed panel-side by turning the camera 180°. "
                            "Not corrected yet: the next step is a 2D map.", '<div class="heats">' + "".join(heat) + "</div>"))

    # 8. Brightness sweep.
    sw = load("sweep-*.json")
    if sw and sw["records"]:
        by = {}
        for r in sw["records"]:
            by.setdefault(r["level"], {})[r["backlight"]] = r["Y"]
        s255 = sorted(by.get(255, {}).items())
        common = [b for b, _ in s255 if b in by.get(32, {})]
        gam = [(b, by[32][b] / by[255][b] / (32 / 255) ** 2.2) for b in common]
        svg = line_chart([("white", "var(--s-blue)", "circle", [(b, y / s255[-1][1]) for b, y in s255])],
                         "backlight value", "light vs full (log)", xlog=True, ylog=True, yfmt=lambda v: f"{v:g}")
        svg2 = line_chart([("grey 32 vs 2.2", "var(--s-orange)", "square", gam)], "backlight value",
                          "grey 32 light vs gamma 2.2", xlog=True, ref=(1.0, "gamma 2.2"), yfmt=lambda v: f"{v:.2f}×")
        cards.append(figure("sweep", "Across the brightness range",
                            "Correction off. Top: how white follows the backlight value. Bottom: how grey 32 sits against gamma 2.2 at each "
                            "backlight; the bad band shows as its departure from 1.", svg + svg2,
                            ["backlight", "white (rel.)", "grey 32 vs 2.2"],
                            [[b, f"{by[255][b] / s255[-1][1]:.4f}", f"{g:.2f}×"] for b, g in gam]))

    # 9. Flicker.
    pw = load("pwm-*.json")
    if pw:
        pts = {}
        for r in pw["records"]:
            pts.setdefault(r["seconds"], []).append((r["backlight"], r["ripple_rel"] * 100))
        svg = line_chart([(f"{s * 1e6:.0f} µs", col, mk, v) for (s, v), col, mk in
                          zip(sorted(pts.items()), ("var(--s-blue)", "var(--s-orange)"), ("circle", "square"))],
                         "backlight value", "row ripple (% of mean)", xlog=True, yr=(0, 6), yfmt=lambda v: f"{v:.0f}%")
        cards.append(figure("pwm", "No classic PWM",
                            "Very short exposures read the screen row by row, so pulsing shows as bands. A ~3–4% band pattern appears at every "
                            "backlight (a camera artefact; also at full brightness). Only at 96–310 does a faster pattern (≈1.3 kHz, 1.3–2.7%) "
                            "appear in the shortest exposure and vanish in the longer one: a shallow ripple, harmless to the eye, in exactly "
                            "the band with the green cast.", svg,
                            ["backlight", "exposure", "ripple", "band period (rows)"],
                            [[r["backlight"], f"{r['seconds'] * 1e6:.0f} µs", f"{r['ripple_rel']:.1%}", f"{r['period_rows']:.1f}"] for r in pw["records"]]))

    # 10. Stray light and bright-next-to-dark.
    st, sp = load("stray-*.json"), load("split-*.json")
    rows = []
    if st:
        rows.append(["Stray light next to a bright window (hood + lens)", "red {:.2%} · green {:.2%} · blue {:.2%}".format(*st["near"])])
        rows.append(["… far from it", "red {:.2%} · green {:.2%} · blue {:.2%}".format(*st["far"])])
    if sp:
        for g in (8, 16, 32):
            rec = {x["pattern"]: x for x in sp["records"] if x["grey"] == g}
            if len(rec) == 3:
                ch = [(rec["white + grey"][c] - rec["white alone"][c]) / rec["grey alone"][c] - 1 for c in "RGB"]
                rows.append([f"Grey {g} next to a white half (stray light subtracted)", "red {:+.1%} · green {:+.1%} · blue {:+.1%}".format(*ch)])
    if rows:
        cards.append(f'<section class="card" id="extras"><h2>Stray light and loading</h2><p class="lede">The hood lets well under 1% '
                     f'through, reddish (black materials reflect red more). Bright content barely shifts dark greys.</p>{table(["test", "result"], rows)}</section>')

    # 11. Accuracy across the range, stock vs corrected.
    runs_ = sweeps()
    if runs_:
        steps = sorted({b for d in runs_ for b in d["steps"]})
        levels = [L for L in runs_[-1]["levels"] if L != 128]

        def grid(mode):
            by = latest_cells(mode)
            cw, ch = 40, 26
            w, h = len(steps) * cw + 70, len(levels) * ch + 46
            o = [f'<svg viewBox="0 0 {w} {h}" class="heat"><text x="0" y="12" class="label">{esc(mode)}</text>']
            for j, L in enumerate(levels):
                o.append(f'<text x="{len(steps) * cw + 6}" y="{j * ch + 20 + ch / 2 + 4}" class="tick">grey {L}</text>')
                for i, b in enumerate(steps):
                    c = by.get((b, L))
                    if not c:
                        continue
                    # Colour: the worse of colour (vs 3%) and light (vs 10%), 0 = perfect, 1 = at tolerance.
                    bad = max(c["colour_err"] / 0.03, abs(math.log(c["light"])) / math.log(1.1))
                    t = min(1.0, bad / 4)
                    tip = (f"backlight {b}, grey {L}: colour R/G {c['rg']:+.0%}, B/G {c['bg']:+.0%}; light {c['light']:.2f}x"
                           + (" (within tolerance)" if c["ok"] else ""))
                    o.append(f'<rect x="{i * cw + 1}" y="{j * ch + 20}" width="{cw - 2}" height="{ch - 2}" rx="3" '
                             f'style="fill: color-mix(in oklab, var(--mid) {100 - t * 100:.0f}%, var(--hot))" data-tip="{esc(tip)}">'
                             f'<title>{esc(tip)}</title></rect>')
                    if c["ok"]:
                        o.append(f'<text x="{i * cw + cw / 2}" y="{j * ch + 20 + ch / 2 + 4}" class="cell" text-anchor="middle">✓</text>')
            for i, b in enumerate(steps):
                o.append(f'<text x="{i * cw + cw / 2}" y="{len(levels) * ch + 36}" class="tick" text-anchor="middle">{b}</text>')
            o.append("</svg>")
            return "".join(o)

        # Progress: every sweep, inside the band (70-450), corrected.
        def band_median(d, key):
            xs = sorted(key(c) for c in d["cells"].get("corrected", []) if 70 <= c["step"] <= 450)
            return xs[len(xs) // 2] if xs else None
        rows = []
        for d in runs_:
            x = d["summary"].get("corrected")
            if not x:
                continue
            col = band_median(d, lambda c: c["colour_err"])
            lt = band_median(d, lambda c: abs(math.log(c["light"])))
            st = d["summary"].get("stock")
            rows.append([d["when"][:8] + " " + d["when"][9:11] + ":" + d["when"][11:13],
                         ", ".join(str(b) for b in d["steps"]) if len(d["steps"]) < 13 else "all 13",
                         f"{col:.1%}" if col is not None else "–", f"{math.exp(lt) - 1:.0%}" if lt is not None else "–",
                         x["grade"] + (f" (stock {st['grade']})" if st else "")])
        cards.append(f'<section class="card" id="accuracy"><h2>Accuracy across the range</h2>'
                     f'<p class="lede">Grey 4–32 at 13 backlight levels, stock against corrected (dither moving per frame, as in '
                     f'games). A sample passes when its colour is within ±3% of neutral and its light within ±10% of gamma 2.2. '
                     f'Grey cells are fine, red ones far off; ✓ marks a pass; each cell is its newest reading. Camera-relative, '
                     f'not absolute colorimetry. Progress: median errors, corrected, inside the band (70–450).</p>'
                     f'{table(["sweep", "steps", "colour error", "light error", "grade (strict)"], rows)}'
                     f'<div class="heats">{grid("stock")}{grid("corrected")}</div><p class="note">backlight value →</p></section>')

    # 12. The calibration as it stands: camera tables, trims per dither mode,
    # the profile's lift per step, and the lift loop's rounds.
    st = settings()
    tables = st.get("dither_tables") or {}
    if tables:
        prof = {x["b"]: x for x in st.get("steps", [])}
        trows = []
        for k in sorted(tables, key=int):
            t = tables[k]
            modes = ", ".join(sorted((t.get("trims") or {}).keys())) or ("generic" if t.get("trim") else "none")
            trows.append([k, t.get("measured", "–"), t.get("V", "–"), modes])
        lrows = []
        for b in sorted(prof):
            l = prof[b]["l"]
            if any(v for v in l[9:12] if v):
                lrows.append([b] + [f"{(l[i] or 0):+.1f}%" for i in (9, 10, 11)])
        lift = load("lift-cal-*.json")
        hrows = []
        for h in (lift or {}).get("history", []):
            r = h["ratio"]
            hrows.append([h["step"], h["round"], " / ".join(f"{h['lift'][k]:+.1f}" for k in ("64", "80", "96") if k in h["lift"]),
                          *(f"{r[k]:.2f}×" for k in ("16", "32", "64", "80", "96") if k in r)])
        body = (f'<p class="lede">Profile “{esc(st.get("profile", "?"))}”, shadow curve {esc(st.get("shadow_curve", "?"))}, '
                f'dither pattern {esc(st.get("dither_temporal") or "still")}. Camera tables per backlight step (the dither between '
                f'them is blended in log brightness); each dither mode has its own closed-loop trim, golden falling back to '
                f'pair’s where it has none.</p>{table(["step", "measured", "hand-over code", "trims"], trows)}')
        if lrows:
            body += ('<p class="lede">Brightness (lift) at grey 64, 80 and 96 per step: the dithered darks aim at grey 64’s '
                     'light, which sat ~20% high against grey 128; one lift there moves all of them.</p>'
                     + table(["step", "grey 64", "grey 80", "grey 96"], lrows))
        if hrows:
            body += ('<p class="note">Lift loop, light against gamma 2.2 from grey 128 per round:</p>'
                     + table(["step", "round", "lift 64/80/96 (%)", "grey 16", "grey 32", "grey 64", "grey 80", "grey 96"], hrows))
        cards.append(f'<section class="card" id="calibration"><h2>Calibration state</h2>{body}</section>')

    # 13. Ambient light into the hood: black frames per room condition.
    amb = None
    try:
        amb = json.load(open(os.path.join(RUNS, "ambient-test.json")))
    except (OSError, ValueError):
        pass
    amb_spec = None
    if amb and "dark" in amb.get("frames", {}) and len(amb["frames"]) > 1:
        g = {k: [f["G"] for f in v] for k, v in amb["frames"].items()}
        mean = {k: sum(v) / len(v) for k, v in g.items()}
        noise = max(max(v) - min(v) for v in g.values())
        g4 = [c for (b, L), c in latest_cells("corrected").items() if L == 4]
        sweep4 = None
        for d in reversed(sweeps()):
            recs = [r for r in d["records"] if r["mode"] == "corrected" and r["level"] == 4 and r["step"] == 52]
            if recs:
                sweep4 = recs[0]["G"]
                break
        arows = []
        for k in mean:
            if k == "dark":
                continue
            leak = mean[k] - mean["dark"]
            arows.append([k, f"{leak:+.4f}", f"{noise:.4f}", f"{leak / sweep4:+.2%}" if sweep4 else "–"])
        cards.append(f'<section class="card" id="ambient"><h2>Room light into the hood</h2><p class="lede">Black frames '
                     f'(screen at code 0, backlight 52, {amb["seconds"]} s at ISO {amb["iso"]}) with the room lit and dark. The '
                     f'difference is what leaks in, against the weakest signal measured (corrected grey 4 at backlight 52) and the '
                     f'frame-to-frame scatter.</p>{table(["room", "leak (G, per s at ISO 100)", "scatter", "of grey 4 at 52"], arows)}</section>')
        if arows and sweep4:
            amb_spec = f"{arows[0][3]} of the weakest signal (room lit vs dark; scatter {noise / sweep4:.2%})"

    # Specs.
    specs = [
        ("Device", "AYN Odin 2 Portal, Armada OS 20261010"),
        ("Panel", "7\" OLED, 1920×1080 (native portrait 1080×1920, rotated), 120 Hz"),
        ("Display controller", "Chipone ICNA3512 (Linux: panel-chipone-icna35xx)"),
        ("Backlight", "raw 40–4096 (12-bit DBV)"),
        ("Compositor", "gamescope 3.16.31-ogc1+, HDR output, SDR content at 202.6 nits"),
        ("Bad band", "backlight ~62–540 (Steam slider ~6–38%): the panel jumps between 60 and 69 and is clean again from ~530; worst at 177–230"),
        ("At full brightness", "gamma 2.2 ±3% from grey 32, grey tracking ±1%, uniformity ±6–7%"),
        ("Pedestal at 177", "code 2 = 28% (G), 12% (B), 9% (R) of code 32's light; gamma 2.2: 0.2%"),
        ("Pattern blur", "alternating rows lose up to 40%, columns honest"),
        ("Flicker", "no classic PWM; ≈1.3 kHz ripple of 1–3% at 96–310"),
        ("Stray light (rig)", "≤0.43% next to a bright window"),
        ("Second unit", "another Portal (2026-10-31, eye check, no camera): the same green band, gone with the plugin and this unit's calibration"),
        ("Plugin", "OLED Tint 0.2.0 (beta, 2026-10-31) for Decky Loader: github.com/murdii34/decky-oled-tint"),
    ] + ([("Room light (rig)", amb_spec)] if amb_spec else [])
    tiles = ""
    if lv:
        tiles = (f'<div class="tiles"><div class="tile"><div class="big">{light(off, 4):.0f}× → {light(on, 4):.2f}×</div>'
                 f'<div class="cap">grey 4 light vs target at 177</div></div>'
                 f'<div class="tile"><div class="big">{off[4]["rg"]:+.0%} → {on[4]["rg"]:+.0%}</div>'
                 f'<div class="cap">grey 4 red vs green (green cast)</div></div>'
                 f'<div class="tile"><div class="big">±3%</div><div class="cap">gamma 2.2 accuracy at full brightness, grey 32+</div></div></div>')
    # Footnote: the project in numbers (see stats.py).
    try:
        import stats as stats_mod
        n = stats_mod.collect()
    except Exception:
        n = {}
    foot = ""
    if n.get("commits"):
        k = lambda v: f"{v / 1e6:.1f} million" if v >= 1e6 else f"{v / 1e3:.0f}k" if v >= 1e4 else f"{v:,}"
        items = [
            f"≈{n['photos_est']:,} raw photos taken ({n['photos_on_disk']:,} kept, {n['raw_gb']} GB), "
            f"{n['readings']:,} accepted readings in {n['run_files']} measurement files",
            f"camera running at least {n['camera_hours_min']} h",
            f"{n['days']} days from first commit; {n['commits']} commits across the plugin, the measuring tool, the hood "
            f"and the tile art; {n['code_lines']:,} lines of code in {n['code_files']} files, {n['tests']} automated tests",
            f"written with Claude Code (Claude Opus): {n['session_hours']} h of sessions, {n['model_calls']:,} model calls, "
            f"{k(n['tokens_out'])} tokens written and {k(n['tokens_total'])} processed (mostly re-read context)",
            f"the Odin drew {n['energy_wh']} Wh over the {n['energy_hours']} h logged; CPU at most {n['cpu_peak_c']:.0f} °C",
            "one 3D-printed light hood; two external code reviews",
        ]
        foot = ('<footer class="numbers"><h2>The project in numbers</h2><ul>'
                + "".join(f"<li>{esc(x)}</li>" for x in items)
                + "</ul><p class=\"note\">Counted from the project's files when this page was built. Photos: the rolling "
                "archive drops old intermediate shots, so the total is an estimate from the run files and logs; camera time is "
                "a lower bound. Tokens: from this device's session logs only.</p></footer>")
    # 14. Camera change: A7 III against A7 IV on the same grey ramp.
    try:
        ra = {r["level"]: r for r in load("ref.json")["records"] if r["step"] == 4096}
        rb = {r["level"]: r for r in load("a7iv-ref.json")["records"] if r["step"] == 4096}
        chk = load("a7iv-check.json") or {}
        lv = [l for l in sorted(ra) if l in rb]
        crow = []
        for l in lv:
            la = ra[l]["G"] / ra[64]["G"]
            lb = rb[l]["G"] / rb[64]["G"]
            crow.append([l, f"{ra[l]['R'] / ra[l]['G']:.3f}", f"{rb[l]['R'] / rb[l]['G']:.3f}",
                         f"{ra[l]['B'] / ra[l]['G']:.3f}", f"{rb[l]['B'] / rb[l]['G']:.3f}",
                         f"{la:.4f}", f"{lb:.4f}", f"{lb / la:.3f}"])
        if crow:
            cards.append('<section class="card" id="camera"><h2>Measuring camera: A7 III vs A7 IV</h2>'
                         '<p class="lede">The measuring camera was changed on 2026-10-26, from a Sony A7 III to an A7 IV, '
                         'so the same grey ramp was shot with both behind the same hood. These are the numbers from that '
                         'run. Colour (red/green and blue/green) agrees within about 2% and 1%; the light of each grey, '
                         'relative to grey 64, agrees within 1–2% from grey 12 to 192. At grey 255 the A7 IV reads 7% '
                         'lower. Both cameras were also checked for linearity: light scales with shutter time and ISO '
                         'within about 1%, and the read noise is about 2.5 counts out of ~15900 at ISO 800.</p>'
                         + table(["grey", "R/G A7 III", "R/G A7 IV", "B/G A7 III", "B/G A7 IV",
                                  "light vs 64, A7 III", "light vs 64, A7 IV", "ratio IV / III"], crow)
                         + '<p class="note">Light is the green channel at a long exposure, divided by the same camera\'s '
                         'grey 64. A ratio of 1.000 means both cameras see the ramp identically.</p></section>')
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        pass

    # 15. Floor dimming accuracy (newest floor sweep with an accuracy block).
    try:
        def acc_file(cal):
            best = None
            for f in sorted(glob.glob(os.path.join(RUNS, "floor-sweep-a7iv*.json"))):
                if f.endswith("-cal.json") != cal:
                    continue
                d = json.load(open(f))
                if d.get("accuracy"):
                    best = d
            return best
        a0, a1 = acc_file(False), acc_file(True)
        intro = ('Floor dimming keeps the backlight at its floor (543) and does the dimming in the shader instead. '
                 '“Target” is the brightness asked for. “Light” is the measured light divided by what the panel’s own white '
                 'curve predicts for that target, so 1.00 is exactly right; colour error is the larger of the red/green and '
                 'blue/green deviations from neutral.')
        if not (a0 or a1):
            cards.append('<section class="card" id="floordim"><h2>Floor dimming accuracy</h2><p class="lede">' + intro
                         + '</p><p class="note">Measurement pending.</p></section>')
        else:
            runs2 = [(n, d) for n, d in (("before calibration", a0), ("after calibration", a1)) if d]
            def pick(d):
                m = {}
                for r in d["accuracy"]:
                    m.setdefault(r["target"], {})[r["level"]] = r
                return m
            maps = [(n, pick(d)) for n, d in runs2]
            targets = sorted(set(t for _, m in maps for t in m))
            hdr = ["target"]
            for n, _ in maps:
                for g in (16, 64, 128):
                    hdr += [f"{n}: grey {g} colour", f"{n}: grey {g} light"]
            rows = []
            for t in targets:
                row = [t]
                for _, m in maps:
                    for g in (16, 64, 128):
                        r = m.get(t, {}).get(g)
                        row += [f"{max(abs(r['rg']), abs(r['bg'])):.1%}", f"{r['light']:.2f}"] if r else ["–", "–"]
                rows.append(row)
            cols = ["var(--s-red)", "var(--s-green)", "var(--s-blue)"]
            series = []
            for (n, m) in maps:
                for g, c, mk in zip((16, 64, 128), cols, MARKS):
                    pts = [(t, m[t][g]["light"]) for t in targets if t in m and g in m[t]]
                    if pts:
                        series.append((f"grey {g}" + (f" ({n.split()[0]})" if len(maps) > 1 else ""), c, mk, pts))
            svg = line_chart(series, "target brightness", "light vs panel curve", ref=(1.0, "exact")) if series else ""
            cards.append('<section class="card" id="floordim"><h2>Floor dimming accuracy</h2><p class="lede">' + intro
                         + '</p>' + svg + table(hdr, rows) + '</section>')
    except (OSError, ValueError, KeyError, TypeError):
        pass

    # 16. The floor itself, night to night (RESULTS 28): the darkest greys at
    # backlight 543 undimmed, against the full-brightness reference.
    try:
        ref = {r["level"]: r for r in json.load(open(os.path.join(RUNS, "a7iv-ref.json")))["records"] if r.get("step") == 4096}
        nights = []
        for f in sorted(glob.glob(os.path.join(RUNS, "floor-sweep-*.json")), key=os.path.getmtime):
            d = json.load(open(f))
            at = {r["level"]: r for r in d.get("records", []) if r.get("target") == d.get("floor", 543)}
            if 4 in at and 255 in at:
                nights.append((time.strftime("%m-%d", time.localtime(os.path.getmtime(f))), d.get("profile", "?"), at))
        if nights and 255 in ref:
            hdr = ["sweep", "profile"] + [f"grey {g} R/G vs ref" for g in (4, 8, 16)] + ["white light vs first"]
            w0 = nights[0][2][255]["Y"]
            rows = [[day, prof] + [f"{(at[g]['R'] / at[g]['G']) / (ref[g]['R'] / ref[g]['G']) - 1:+.0%}" if g in at and g in ref else "–"
                                   for g in (4, 8, 16)] + [f"{at[255]['Y'] / w0:.2f}"] for day, prof, at in nights]
            cards.append('<section class="card" id="floornight"><h2>The floor, night to night</h2><p class="lede">'
                         'The darkest greys at the floor (backlight 543, nothing dimmed), against the same grey at full brightness. '
                         'On 10-29 grey 4 lost about half its red, like the panel inside its bad band, and white was 17% brighter: '
                         'the band edge (about 530) seems to wander above 543 some nights, and the rig may have moved. '
                         'The floor can now be set higher (floor_backlight) for a test.</p>' + table(hdr, rows) + '</section>')
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        pass

    page = TEMPLATE.replace("%TILES%", tiles).replace("%SPECS%", table(["", ""], specs)).replace("%CARDS%", "".join(cards) + foot) \
        .replace("%STAMP%", time.strftime("%Y-%m-%d %H:%M"))
    with open(os.path.join(HERE, "index.html"), "w") as f:
        f.write(page)
    print("wrote", os.path.join(HERE, "index.html"), len(cards), "sections")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Odin 2 Portal panel</title>
<style>
:root { color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s-blue: #2a78d6; --s-orange: #eb6834; --s-red: #e34948; --s-green: #008300;
  --cold: #2a78d6; --hot: #e34948; --mid: #f0efec; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s-blue: #3987e5; --s-orange: #d95926; --s-red: #e66767; --s-green: #008300;
  --cold: #3987e5; --hot: #e66767; --mid: #383835; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s-blue: #3987e5; --s-orange: #d95926; --s-red: #e66767; --s-green: #008300;
  --cold: #3987e5; --hot: #e66767; --mid: #383835; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 26px; margin: 8px 0 4px; } h2 { font-size: 18px; margin: 0 0 6px; }
.sub { color: var(--ink-2); margin: 0 0 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px 18px 12px; margin: 16px 0; }
.lede { color: var(--ink-2); margin: 0 0 10px; } .note { color: var(--ink-3); font-size: 13px; }
footer.numbers { border-top: 1px solid var(--border); margin: 28px 0 8px; padding-top: 14px; color: var(--ink-2); font-size: 14px; }
footer.numbers h2 { font-size: 15px; margin: 0 0 6px; color: var(--ink-2); }
footer.numbers ul { margin: 0 0 8px; padding-left: 18px; line-height: 1.6; }
.chart, .heat { width: 100%; height: auto; display: block; margin: 6px 0; }
.heats { display: grid; gap: 8px; }
.grid { stroke: var(--grid); stroke-width: 1; } .axis { stroke: var(--axis); stroke-width: 1; }
.ref { stroke: var(--ink-3); stroke-width: 1; stroke-dasharray: 4 4; }
.tick { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.label { fill: var(--ink-2); font-size: 12px; } .reflabel, .dlabel { font-size: 11px; fill: var(--ink-2); }
.cell { fill: var(--ink); font-size: 10px; font-variant-numeric: tabular-nums; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; }
details { margin: 8px 0 4px; } summary { cursor: pointer; color: var(--ink-2); font-size: 13px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
.big { font-size: 24px; font-weight: 650; } .cap { color: var(--ink-2); font-size: 13px; }
#tip { position: fixed; pointer-events: none; background: var(--ink); color: var(--surface); font-size: 12px; padding: 4px 8px;
  border-radius: 6px; opacity: 0; transition: opacity .1s; z-index: 10; max-width: 280px; }
[data-tip]:hover { opacity: .85; cursor: default; }
nav { font-size: 13px; color: var(--ink-3); }
details.card > summary.h2 { font-size: 18px; font-weight: 650; color: var(--ink); cursor: pointer; list-style-position: outside; margin: 0 0 6px; }
h3 { font-size: 14px; color: var(--ink-2); margin: 16px 0 0; font-weight: 600; }
hr.divider { border: 0; border-top: 1px solid var(--axis); margin: 28px 0 8px; }
.vlabel { font-size: 10px; fill: var(--ink); font-variant-numeric: tabular-nums; } nav a { color: var(--ink-2); margin-right: 10px; }
</style></head>
<body><main>
<h1>Odin 2 Portal panel</h1>
<p class="sub">What a camera (Sony A7 III, later A7 IV, raw, in a printed light hood) found about this OLED, and what the OLED Tint plugin does about it.
Built %STAMP% from the measurement files.</p>
<nav><a href="#status">Status</a><a href="#pedestal">Pedestal</a><a href="#fix">Before/after</a><a href="#tone">Tone curve</a><a href="#patterns">Patterns</a>
<a href="#vibrance">Vibrance</a><a href="#uniformity">Uniformity</a><a href="#sweep">Sweep</a><a href="#pwm">Flicker</a><a href="#extras">Stray light</a><a href="#accuracy">Accuracy</a><a href="#calibration">Calibration</a><a href="#ambient">Room light</a></nav>
<details class="card" id="status" open><summary class="h2">Right now</summary>
<p class="lede" id="st-mission">Loading the rig's status…</p>
<div class="tiles" id="st-tiles"></div>
<table><tbody id="st-rows"></tbody></table>
<h3>Last 12 hours (10-minute averages)</h3>
<div id="st-temp"></div><div id="st-power"></div>
<p class="note" id="st-updated"></p></details>
<hr class="divider">
%TILES%
<section class="card"><h2>Spec sheet</h2>%SPECS%</section>
%CARDS%
</main><div id="tip"></div>
<script>
const tip = document.getElementById("tip");
document.addEventListener("pointerover", e => { const t = e.target.closest("[data-tip]"); if (!t) return;
  tip.textContent = t.dataset.tip; tip.style.opacity = 1; });
document.addEventListener("pointermove", e => { tip.style.left = (e.clientX + 12) + "px"; tip.style.top = (e.clientY + 12) + "px"; });
document.addEventListener("pointerout", e => { if (e.target.closest("[data-tip]")) tip.style.opacity = 0; });
document.querySelectorAll("svg title").forEach(t => t.remove());
// The rig's status: one small file, fetched once a minute by this page (the
// device only writes it, once a minute).
const el = id => document.getElementById(id);
const row = (k, v) => `<tr><td>${k}</td><td>${v ?? "–"}</td></tr>`;
const tile = (big, cap) => `<div class="tile"><div class="big">${big}</div><div class="cap">${cap}</div></div>`;
async function status() {
  try {
    const s = await (await fetch("status.json?" + Date.now(), { cache: "no-store" })).json();
    const q = s.queue, d = s.device, p = s.plugin;
    el("st-mission").textContent = s.mission;
    el("st-tiles").innerHTML =
      tile(q.running ? "Measuring" : "Idle", q.running ? (q.stage || "") : "no measurement running") +
      tile(d.cpu_c != null ? d.cpu_c.toFixed(0) + " °C" : "–", "CPU (battery " + (d.battery_c ?? "–") + " °C)") +
      tile(d.battery_pct + "%", "battery, " + (d.battery_status || "").toLowerCase());
    el("st-rows").innerHTML =
      row("Current stage", q.stage) + row("Last event", q.last_event) +
      row("Earlier stages", (q.stages_done || []).join("<br>")) +
      row("Backlight", d.backlight) + row("Power draw", d.watts != null ? d.watts.toFixed(1) + " W" : null) +
      row("Free storage", d.disk_free_gb + " GB") +
      row("Plugin", `${p.enabled ? "on" : "off"} · profile ${p.profile} · dither ${p.dither ? (p.dither_temporal || "still") : "off"} · shadows ${p.shadow_curve} · crush ${p.crush}`);
    const age = (Date.now() - new Date(s.updated.replace(" ", "T"))) / 1000;
    el("st-updated").textContent = `Updated ${s.updated}` + (age > 180 ? " — stale: the status writer may not be running" : "");
  } catch (e) { el("st-updated").textContent = "No status available (status.json missing)."; }
}
// 12-hour history, drawn here from history.json (a few dozen points).
function hchart(pts, series, unit, yfix) {
  const W = 640, H = 220, L = 46, R = 640 - 110, T = 14, B = 220 - 30;
  const vals = series.flatMap(s => pts.map(p => p[s.key]).filter(v => v != null));
  if (!vals.length) return `<p class="note">No data yet: logging started recently.</p>`;
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (yfix) { lo = Math.min(lo, yfix[0]); hi = Math.max(hi, yfix[1]); }
  const pad = (hi - lo) * 0.15 || 1; lo -= pad; hi += pad;
  if (unit === "W") lo = Math.max(0, lo);        // no negative watts on the axis
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t || t0 + 1;
  const sx = t => L + (t - t0) / Math.max(1, t1 - t0) * (R - L), sy = v => B - (v - lo) / (hi - lo) * (B - T);
  let o = `<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  const step = (hi - lo) / 4;
  for (let i = 0; i <= 4; i++) { const v = lo + step * i, y = sy(v);
    o += `<line x1="${L}" x2="${R}" y1="${y}" y2="${y}" class="grid"/><text x="${L - 6}" y="${y + 4}" class="tick" text-anchor="end">${v.toFixed(unit === "W" ? 1 : 0)}</text>`; }
  for (let t = Math.ceil(t0 / 7200) * 7200; t <= t1; t += 7200) {
    const d = new Date(t * 1000), x = sx(t);
    o += `<text x="${x}" y="${B + 16}" class="tick" text-anchor="middle">${String(d.getHours()).padStart(2, "0")}:00</text>`; }
  o += `<line x1="${L}" x2="${R}" y1="${B}" y2="${B}" class="axis"/>`;
  const ends = [];
  for (const s of series) {
    const p = pts.filter(q => q[s.key] != null);
    if (!p.length) continue;
    o += `<path d="${p.map((q, i) => (i ? "L" : "M") + sx(q.t).toFixed(1) + "," + sy(q[s.key]).toFixed(1)).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
    // Numbers on the chart: every 2 hours, plus the latest.
    p.forEach((q, i) => { if (i % 12 === 0 || i === p.length - 1) {
      const x = sx(q.t), y = sy(q[s.key]);
      o += `<circle cx="${x}" cy="${y}" r="3" fill="${s.color}"/><text x="${x}" y="${y - 7}" class="vlabel" text-anchor="middle">${q[s.key].toFixed(unit === "W" ? 1 : 0)}</text>`; } });
    ends.push([sy(p[p.length - 1][s.key]), s]);
  }
  ends.sort((a, b) => a[0] - b[0]); for (let i = 1; i < ends.length; i++) ends[i][0] = Math.max(ends[i][0], ends[i - 1][0] + 13);
  for (const [y, s] of ends) o += `<text x="${R + 8}" y="${y + 4}" class="dlabel"><tspan fill="${s.color}">■</tspan> ${s.name}</text>`;
  return o + `<text x="${L}" y="${T - 2}" class="label">${unit}</text></svg>`;
}
async function hist() {
  try {
    const h = await (await fetch("history.json?" + Date.now(), { cache: "no-store" })).json();
    el("st-temp").innerHTML = hchart(h.points, [{ key: "cpu", name: "CPU max", color: "var(--s-orange)" },
                                                 { key: "bat", name: "battery", color: "var(--s-blue)" }], "°C");
    el("st-power").innerHTML = hchart(h.points, [{ key: "w", name: "system draw", color: "var(--s-green)" }], "W", [0, 1]);
  } catch (e) { el("st-temp").innerHTML = `<p class="note">No history available.</p>`; }
}
status(); hist(); setInterval(() => { status(); hist(); }, 60000);
</script>
</body></html>
"""

if __name__ == "__main__":
    main()

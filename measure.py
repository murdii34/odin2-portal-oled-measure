"""Measure the Odin 2 Portal's panel with a camera and calibrate OLED Tint.

Run inside the camera toolbox:  toolbox run -c oled-cam python3 measure.py ...

  setup                       framing shot: finds the screen, picks the region
  measure  --steps .. [--levels ..] [--correction on|off] --name NAME
  calibrate --steps .. --reference NAME [--levels ..] [--rounds 3] [--apply]
  apply PROPOSAL              write a calibrate proposal into the plugin
  report NAME [--against REF] table of a measurement run

The screen shows full-screen grey patches through Steam's UI; the plugin's
correction (ReShade) applies to them like to anything else. Brightness comes
from the plugin's steps, so a step's values are exactly what's on screen.
"""
import argparse
import json
import math
import os
import sys
import shutil
import time

import camera
import plugin
import rawstats
import uniformity
from screen import Screen

HOME = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HOME, "state")
RUNS = os.path.join(HOME, "runs")
RAW = os.path.join(HOME, "raw")
for d in (STATE, RUNS, RAW):
    os.makedirs(d, exist_ok=True)
ROI_FILE = os.path.join(STATE, "roi.json")
MAX_ISO = 6400
# Accepted patch shots and their black frames are kept here for later
# analysis (uniformity, grain), oldest dropped first beyond ARCHIVE_BYTES.
ARCHIVE = os.path.join(RAW, "archive")
ARCHIVE_BYTES = 5 * 1024**3      # was 15 GB; the pinned tier fills the disk (see backup_to_nas.sh)
# Shots worth keeping (checks and tests, not a closed loop's intermediate
# rounds) go here, by UTC day, and are never pruned; backup_to_nas.sh copies
# them to the NAS.
PINNED = os.path.join(RAW, "pinned")


def archive(path, name, keep=False):
    """Move a shot out of the way. keep: into PINNED for good; otherwise
    into the rolling ARCHIVE, oldest dropped first beyond ARCHIVE_BYTES."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ-", time.gmtime())       # UTC: no DST ambiguity
    if keep:
        folder = os.path.join(PINNED, stamp[:8])
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, stamp + name + ".ARW")
        shutil.move(path, dest)     # PINNED may be on the microSD (another filesystem)
        return dest
    os.makedirs(ARCHIVE, exist_ok=True)
    dest = os.path.join(ARCHIVE, stamp + name + ".ARW")
    os.replace(path, dest)
    files = sorted((os.path.join(ARCHIVE, f) for f in os.listdir(ARCHIVE)), key=os.path.getmtime)
    total = sum(os.path.getsize(f) for f in files)
    while files and total > ARCHIVE_BYTES:
        total -= os.path.getsize(files[0])
        os.remove(files.pop(0))
    return dest


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Rig:
    def __init__(self, keep=True):
        # keep: shots of this run go to the kept tier (a closed loop's many
        # intermediate rounds don't).
        self.keep = keep
        if not os.path.isdir(RAW):
            # raw/ links to the microSD, which is mounted at login (or boot).
            raise SystemExit(f"{RAW} isn't there: is the microSD mounted?")
        # The plugin's band-edge snap would move backlights 63-69 away while
        # we measure them; off for the run, back on in close().
        # AYN-style dimming likewise: it would hold the backlight at its floor.
        self.snap_was = None
        self.dimming_was = None
        with plugin.locked():
            d = plugin.read()
            if d.get("band_snap", True):
                self.snap_was = True
                d["band_snap"] = False
            if d.get("dimming") == "soft":
                self.dimming_was = "soft"
                d["dimming"] = "band"
            if self.snap_was or self.dimming_was:
                plugin._write(d)
        if self.dimming_was:
            # The frontend's slider intercept follows the setting every 2 s; until it lets go
            # it swallows the brightness probes (calibrate failed at 22:28 on 2026-10-26: "could not reach backlight 543 (at 573)").
            time.sleep(5)
        try:
            self.screen = Screen()
            self.cam = camera.Camera()
            self.black = {}            # (shutter, iso) -> black frame channels
            self.exposure = {}         # code -> last good (seconds, iso), a starting guess
            with open(ROI_FILE) as f:
                box = json.load(f)
            self.roi, self.screen_box = box["roi"], box["screen"]
        except BaseException:
            self._snap_back()          # close() won't run for a rig that never came up
            raise

    def _shot(self, code, tag):
        self.screen.patch(code)
        time.sleep(0.3)
        for attempt in range(2):
            path = self.cam.capture(os.path.join(RAW, f"{tag}.ARW"))
            try:
                return path, rawstats.channels(path, self.roi)
            except Exception as e:                   # truncated download
                log(f"unreadable raw ({e}), shooting again")
        raise RuntimeError("raw files keep coming back unreadable")

    def _black(self):
        key = (self.cam.shutter, self.cam.iso)
        if key not in self.black:
            path, stats = self._shot(0, "black")
            stats["path"] = archive(path, f"black-{key[0].replace('/', '_')}s-iso{key[1]}", self.keep)
            self.black[key] = stats
        return self.black[key]

    def read(self, code, backlight):
        """Light from grey `code` at the current backlight: black-subtracted
        camera R, G, B in units of (raw counts per second at ISO 100), plus XYZ."""
        seconds, iso = self.exposure.get(code, (self.cam.seconds, int(self.cam.iso)))
        path = None
        for attempt in range(8):
            if abs(plugin_safe_backlight() - backlight) > max(1, backlight * 0.02):
                self.screen.brightness(backlight)   # the screen dimmed itself
            if path:
                os.remove(path)                     # the previous try, now superseded
            self.cam.set(iso=iso, seconds=seconds)
            path, s = self._shot(code, "patch")
            p = s["g_p99"]
            at = (self.cam.seconds, int(self.cam.iso))
            if p > 0.85 and (self.cam.seconds > camera.MIN_SECONDS * 1.01 or int(self.cam.iso) > 100):
                seconds, iso = self._scale(*at, 0.3)                 # clipping: much shorter
                why = "clipping"
            elif p > 0.85:
                # Clipped at the shortest exposure: no valid reading to be had
                # (it used to pass as one, review 17).
                raise RuntimeError(f"code {code} clips even at {at[0]:.3g}s ISO {at[1]}")
            elif p < 0.15 and not self._at_limit(*at):
                seconds, iso = self._scale(*at, min(8.0, 0.45 / max(p, 0.005)))
                why = "too dark"
            else:
                break
            log(f"  exposure {at[0]:.3g}s ISO {at[1]}: peak {p:.0%} ({why}), next {seconds:.3g}s ISO {int(iso)}")
        else:
            raise RuntimeError(f"code {code}: exposure didn't settle in 8 tries")
        self.exposure[code] = (self.cam.seconds, int(self.cam.iso))
        k = self._black()
        unit = self.cam.seconds * int(self.cam.iso) / 100
        rgb = {c: (s[c] - k[c]) / unit for c in "RGB"}
        xyz = rawstats.to_xyz(rgb, path)
        # The whole screen too, not just the measuring region: a grid of
        # cells, black frame subtracted, in the same units (see uniformity.py).
        black = k["path"] if os.path.exists(k["path"]) else None   # the archive rolls
        cells = uniformity.grid(path, black, self.screen_box) / unit
        archive(path, f"b{backlight}-code{'-'.join(map(str, code)) if isinstance(code, tuple) else code}", self.keep)
        return {**rgb, "X": float(xyz[0]), "Y": float(xyz[1]), "Z": float(xyz[2]),
                "seconds": self.cam.seconds, "iso": int(self.cam.iso), "g_p99": p,
                "grid": [[[round(float(v), 3) for v in cell] for cell in row] for row in cells]}

    def _at_limit(self, seconds, iso):
        return seconds >= self.cam.longest and iso >= MAX_ISO

    def _scale(self, seconds, iso, factor):
        """New (seconds, ISO) for `factor` times the light: exposure time
        first (up to the camera's longest), then ISO for the rest."""
        amount = seconds * iso * factor
        seconds = max(camera.MIN_SECONDS, min(self.cam.longest, amount / 200))
        want = amount / seconds
        isos = sorted(int(i) for i in self.cam.isos if 100 <= int(i) <= MAX_ISO)
        iso = min(isos, key=lambda i: abs(math.log(i / want)))
        return seconds, iso

    def close(self):
        try:
            self.screen.hide()
        finally:
            self._snap_back()

    def _snap_back(self):
        if self.snap_was or self.dimming_was:
            with plugin.locked():
                d = plugin.read()
                if self.snap_was:
                    d["band_snap"] = True
                if self.dimming_was:
                    d["dimming"] = self.dimming_was
                plugin._write(d)
            self.snap_was = self.dimming_was = None


def plugin_safe_backlight():
    from screen import read_backlight
    return read_backlight()


def codes(levels):
    return [min(255, round(l / 256 * 255)) if l != 255 else 255 for l in levels]


# ---- commands --------------------------------------------------------------

def cmd_setup(args):
    screen = Screen()
    cam = camera.Camera()
    screen.brightness(args.backlight)
    screen.patch(255)
    try:
        seconds = 1 / 60
        for _ in range(6):
            cam.set(iso=200, seconds=seconds)
            path = cam.capture(os.path.join(RAW, "setup.ARW"))
            p = rawstats.channels(path, (0, 10**6, 0, 10**6))["g_p99"]
            log(f"exposure {cam.shutter}: brightest 1% at {p:.0%} of range")
            if 0.3 < p < 0.85:
                break
            seconds *= 0.3 if p >= 0.85 else min(8, 0.5 / max(p, 0.01))
        box = rawstats.find_screen(path)
        roi = rawstats.centre(box, args.fraction)
        with open(ROI_FILE, "w") as f:
            json.dump({"screen": [int(v) for v in box], "roi": [int(v) for v in roi]}, f)
        out = os.path.join(STATE, "setup.png")
        rawstats.preview(path, out, box, roi)
        log(f"screen {box}, measuring region {roi}; preview {out}")
    finally:
        screen.hide()


def cmd_measure(args):
    steps = [int(s) for s in args.steps.split(",")]
    levels = [int(l) for l in args.levels.split(",")]
    with plugin.switches_kept():
        plugin.set_enabled(args.correction == "on")
        rig = Rig()
        out = {"name": args.name, "correction": args.correction, "records": []}
        path = os.path.join(RUNS, args.name + ".json")
        try:
            for b in steps:
                t0 = time.time() - 0.5
                rig.screen.brightness(b)
                if args.correction == "on":
                    time.sleep(1.0)
                    plugin.settle(b, t0)   # this step's correction on screen
                for level, code in zip(levels, codes(levels)):
                    r = rig.read(code, b)
                    out["records"].append({"step": b, "level": level, **r})
                    log(f"step {b:>4} level {level:>3}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  "
                        f"Y {r['Y']:.4g}  ({r['seconds']:.3g}s ISO {r['iso']})")
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
        finally:
            rig.close()
        log(f"saved {path}")


def ratios(r):
    return r["R"] / r["G"], r["B"] / r["G"]


def targets(ref, level):
    """Reference camera ratios at `level` and its luminance relative to 128."""
    by = {x["level"]: x for x in ref["records"]}
    r0, b0 = ratios(by[level])
    return r0, b0, by[level]["Y"] / by[128]["Y"]


# The plugin's model (see main.py): tint t -> red/blue gain k relative to
# green, hue h splits red from blue, lift l scales everything.
def to_gains(v, l, h):
    t = v / 100
    k = 1 - t if t < 0 else 1 / (1 + t)
    return k, 1 + h / 200, 1 + l / 100


def from_gains(k, split, lam):
    v = -(k - 1) * 100 if k >= 1 else (1 / k - 1) * 100
    clamp = lambda x, m: max(-m, min(m, x))
    return clamp(v, 400), clamp((lam - 1) * 100, 50), clamp((split - 1) * 200, 100)


def cmd_calibrate(args):
    steps = [int(s) for s in args.steps.split(",")]
    levels = [int(l) for l in args.levels.split(",")]
    with open(os.path.join(RUNS, args.reference + ".json")) as f:
        ref = json.load(f)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    before = plugin.backup(os.path.join(STATE, f"settings-before-{stamp}.json"))
    log(f"settings backed up to {before}")
    # Everything that changes the settings is covered: a failure before the
    # loop (e.g. the camera not answering) gives them back too.
    try:
        if args.profile:
            def use(d):
                # Work in a profile of our own; a new one starts as a copy of
                # what's active, so the eye calibration stays as it is.
                profiles = d.setdefault("profiles", {})
                if not profiles:
                    # A file from before profiles: the plugin calls its one
                    # calibration Eye. Keep it, or it would vanish behind ours.
                    profiles["Eye"] = json.loads(json.dumps(d["steps"]))
                    d["profile"] = "Eye"
                if args.profile not in profiles:
                    profiles[args.profile] = json.loads(json.dumps(d["steps"]))
                d["profile"] = args.profile
                d["steps"] = json.loads(json.dumps(profiles[args.profile]))
            plugin.change(use)
            log(f"working in profile {args.profile!r}")
        # The dither takes over below its hand-over and ignores the curve
        # values there (grey 4 tint -318.5 or +400 gave the same shader):
        # calibrate the curves with it off. The settings come back after.
        plugin.change(lambda d: d.update(dither=False), compiled=False)
        plugin.set_enabled(True)
        rig = Rig(keep=False)   # many intermediate rounds
        history = []
    except BaseException:
        plugin.write(json.load(open(before)))
        log("setup failed, settings restored")
        raise
    try:
        for b in steps:
            rig.screen.brightness(b)
            si = plugin.step_index(plugin.read(), b)
            # Start from what the plugin resolves now, written out explicitly so
            # every level is independent of its neighbours.
            data = plugin.read()
            sys.path.insert(0, os.path.expanduser("~/decky-oled-tint"))
            import main as tint                       # the plugin's own maths
            tints, lifts, hues = tint.resolve_step(data["steps"][si])
            vals = {lv: [tints[i], lifts[i] if args.lift is None else args.lift, hues[i]]
                    for i, lv in enumerate(plugin.LEVELS)}

            def push():
                def m(d):
                    for i, lv in enumerate(plugin.LEVELS):
                        d["steps"][si]["v"][i], d["steps"][si]["l"][i], d["steps"][si]["h"][i] = (
                            round(x, 1) for x in vals[lv])
                plugin.change(m)
            push()
            # Luminance anchor: grey 128 at this step, as it is now.
            y128 = rig.read(codes([128])[0], b)["Y"]
            for level, code in zip(levels, codes(levels)):
                r0, b0, rel = targets(ref, level)
                gam = [2.2, 2.2, 2.2]                 # local response, refined by secant
                last = None
                for rnd in range(args.rounds + 1):
                    m = rig.read(code, b)
                    if min(m["R"], m["G"], m["B"], m["Y"]) <= 0:
                        # Below the panel's switch-on point: nothing to measure,
                        # nothing a colour correction could fix (see floor runs).
                        log(f"step {b} level {level}: no measurable light, skipped")
                        history.append({"step": b, "level": level, "round": rnd, "skipped": "no light"})
                        break
                    rr, bb = ratios(m)
                    yy = m["Y"] / y128
                    err = (math.log(r0 / rr), math.log(b0 / bb), math.log(rel / yy))
                    history.append({"step": b, "level": level, "round": rnd, "values": vals[level][:],
                                    "R/G": rr, "B/G": bb, "relY": yy, "target": [r0, b0, rel]})
                    log(f"step {b} level {level} round {rnd}: R/G {rr:.3f}->{r0:.3f}  B/G {bb:.3f}->{b0:.3f}  "
                        f"Y {yy:.4f}->{rel:.4f}  values {[round(x) for x in vals[level]]}")
                    # Colour first: at low drive levels the panel has a green glow
                    # floor, and darkening a grey makes it greener, so brightness
                    # is held (at --lift, or what's set) and only colour solved.
                    if max(abs(err[0]), abs(err[1])) < 0.01 or rnd == args.rounds:
                        break
                    k, split, lam = to_gains(*vals[level])
                    gains = (k * split, k / split, lam)       # red, blue, overall
                    if last:                                   # secant: how the panel really responded
                        for i in range(3):
                            dg = math.log(gains[i] / last[0][i])
                            if abs(dg) > 1e-3:
                                gam[i] = max(0.5, min(6.0, (last[1][i] - err[i]) / dg))
                    step_ = [0.8 * e / g for e, g in zip(err, gam)]   # damped
                    step_[2] = 0.0                                     # brightness held
                    nr, nb, nl = (gains[i] * math.exp(step_[i]) for i in range(3))
                    last = (gains, err)
                    k2, split2 = math.sqrt(nr * nb), math.sqrt(nr / nb)
                    v, l, h = from_gains(k2, split2, nl)
                    vals[level] = [v, l, h]
                    push()
            proposal = {"step": b, "values": {str(lv): [round(x, 1) for x in vals[lv]] for lv in plugin.LEVELS}}
            path = os.path.join(RUNS, f"proposal-{stamp}-{b}.json")
            with open(path, "w") as f:
                json.dump({"proposal": proposal, "history": history}, f, indent=1)
            log(f"proposal for step {b}: {path}")
    finally:
        try:
            rig.close()
        finally:                    # the settings come back even if the screen cleanup fails
            if not args.apply:
                plugin.write(json.load(open(before)))
                log("settings restored (run `apply` to use the proposal)")
            else:                   # the proposal stays; the dither switch as it was
                was = json.load(open(before)).get("dither", False)
                plugin.change(lambda d: d.update(dither=was), compiled=False)


def cmd_floor(args):
    """Light from one subpixel colour at a time, at the lowest codes: does
    each channel switch off at 0, and how much does each code add?"""
    codes_ = [int(c) for c in args.codes.split(",")]
    with plugin.switches_kept():
        plugin.set_enabled(False)
        rig = Rig()
        out = {"name": args.name, "step": args.step, "records": []}
        path = os.path.join(RUNS, args.name + ".json")
        try:
            rig.screen.brightness(args.step)
            for ch, name in enumerate("RGB"):
                for c in codes_:
                    rgb = tuple(c if i == ch else 0 for i in range(3))
                    if c == 0:   # all subpixels off: that's the black frame, zero by definition
                        out["records"].append({"channel": name, "code": 0, "R": 0.0, "G": 0.0, "B": 0.0,
                                               "X": 0.0, "Y": 0.0, "Z": 0.0, "seconds": 0, "iso": 0})
                        continue
                    r = rig.read(rgb, args.step)
                    out["records"].append({"channel": name, "code": c, **r})
                    log(f"{name}={c:>3}: camera R {r['R']:9.2f}  G {r['G']:9.2f}  B {r['B']:9.2f}  "
                        f"Y {r['Y']:9.3f}  ({r['seconds']:.3g}s ISO {r['iso']})")
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
        finally:
            rig.close()
        log(f"saved {path}")


def cmd_dither_table(args):
    """Turn floor runs (single-channel light per code) and the reference run
    (grey luminance at full brightness) into the plugin's dither table for
    one backlight step."""
    light = {"R": {}, "G": {}, "B": {}}
    for name in args.floor.split(","):
        with open(os.path.join(RUNS, name + ".json")) as f:
            run = json.load(f)
        if run["step"] != args.step:
            raise SystemExit(f"{name} was measured at step {run['step']}, not {args.step}")
        for r in run["records"]:
            light[r["channel"]][r["code"]] = max(0.0, r[r["channel"]])  # its own camera channel
    V = args.V
    L = {}
    for ch, pts in light.items():
        ks = sorted(pts)
        if ks[-1] < V:
            raise SystemExit(f"{ch} measured only up to code {ks[-1]}, need {V}")
        # Unmeasured codes are -1: through the shader the light isn't
        # monotonic in the code, so guessing between neighbours would lie;
        # the plugin dithers between measured, rising codes only.
        L[ch] = [round(pts[c], 3) if c in pts else -1.0 for c in range(V + 1)]
    with open(os.path.join(RUNS, args.reference + ".json")) as f:
        ref = json.load(f)
    yref = [[code, r["Y"]] for r, code in
            ((r, codes([r["level"]])[0]) for r in ref["records"] if r["level"] > 0) if r["Y"] > 0]
    # measured: the floor shots' date, shown in the plugin's sidebar.
    # (--floor may name several parts, comma separated: the newest counts.)
    measured = time.strftime("%Y-%m-%d", time.localtime(max(
        os.path.getmtime(os.path.join(RUNS, part + ".json")) for part in args.floor.split(","))))
    table = {"V": V, "L": L, "yref": yref, "cell": args.cell, "source": [args.floor, args.reference],
             "measured": measured}

    def m(d):
        d.setdefault("dither_tables", {})[str(args.step)] = table
    plugin.change(m, settle=0.5)
    log(f"dither table for step {args.step} (V={V}) written to the plugin")


def cmd_dither_calibrate(args):
    """Closed loop on the dither table's per-channel trim: measure each dark
    grey with dithering on and scale R, G, B until its colour matches the
    reference and its light the reference curve (anchored at V, where the
    dither hands over). Solid-patch tables miss how the panel mixes."""
    levels = [int(l) for l in args.levels.split(",")]
    with open(os.path.join(RUNS, args.reference + ".json")) as f:
        ref = json.load(f)
    by = {x["level"]: x for x in ref["records"]}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log(f"settings backed up to {plugin.backup(os.path.join(STATE, f'settings-before-dcal-{stamp}.json'))}")
    data = plugin.read()
    table = data["dither_tables"][str(args.step)]
    V = table["V"]
    cs = codes(levels)
    mode = args.mode
    # Each dither mode loses light differently on this panel, so each has its
    # own trim (see the plugin's trim_for); start from what's there.
    # Golden starts from pair's (both move every frame).
    trims = table.get("trims") or {}
    start = trims.get(mode) or (trims.get("pair") if mode == "golden" else None) or table.get("trim")
    trim = json.loads(json.dumps(start)) if start else {
        "codes": cs, "R": [1.0] * len(cs), "G": [1.0] * len(cs), "B": [1.0] * len(cs)}
    if trim["codes"] != cs:
        raise SystemExit(f"table has a trim for codes {trim['codes']}, not {cs}")
    crush = data.get("crush", 0)
    keep = {k: data.get(k) for k in ("dither", "dither_temporal", "dither_temporal_ui", "dither_ui")}

    def push(dither=True, c=0):
        def m(d):
            d["enabled"], d["engine"], d["dither"], d["crush"] = True, "reshade", dither, c
            # A moving dither only moves in Steam's UI with the animated patch.
            d["dither_temporal"] = False if mode == "still" else mode
            d["dither_temporal_ui"] = mode != "still"
            d["dither_ui"] = True                       # the patches are Steam's UI
            d["shadow_curve"] = args.curve
            d["dither_tables"][str(args.step)].setdefault("trims", {})[mode] = trim
        plugin.change(m)
    rig = Rig(keep=False)   # many intermediate rounds
    rig.screen.animate = mode != "still"
    # Camera RGB -> Y, the same matrix every read uses.
    ymat = rawstats.load(os.path.join(RAW, "setup.ARW"))[4][1]
    out = {"step": args.step, "mode": mode, "curve": args.curve, "reference": args.reference, "history": []}
    path = os.path.join(RUNS, f"dither-cal-{args.step}-{mode}-{stamp}.json")
    try:
        rig.screen.brightness(args.step)
        push()
        anchor = rig.read(V, args.step)["Y"]
        log(f"anchor: grey {V} Y {anchor:.4g}")
        for i, (level, code) in enumerate(zip(levels, cs)):
            r0, b0 = ratios(by[level])
            if args.curve == "g22":
                yt = anchor * (code / V) ** 2.2
            else:
                yt = anchor * by[level]["Y"] / by[V]["Y"] if V in by else None
            if yt is None:
                raise SystemExit(f"reference has no level {V}")
            prev = {c: None for c in "RGB"}
            slope = {c: 1.0 for c in "RGB"}
            best = None
            for rnd in range(args.rounds + 1):
                mm = rig.read(code, args.step)
                if min(mm["R"], mm["G"], mm["B"], mm["Y"]) <= 0:
                    log(f"level {level}: no measurable light, skipped")
                    break
                rr, bb = ratios(mm)
                err = (math.log(r0 / rr), math.log(b0 / bb), math.log(yt / mm["Y"]))
                g = [trim[c][i] for c in "RGB"]
                out["history"].append({"level": level, "round": rnd, "trim": g, "R/G": rr, "B/G": bb,
                                       "Y": mm["Y"], "target": [r0, b0, yt]})
                log(f"level {level} round {rnd}: R/G {rr:.3f}->{r0:.3f}  B/G {bb:.3f}->{b0:.3f}  "
                    f"Y {mm['Y']:.4g}->{yt:.4g}  trim {[round(float(x), 3) for x in g]}")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
                score = max(abs(err[0]), abs(err[1])) + 0.5 * abs(err[2])
                if best is None or score < best[0]:
                    best = (score, g, rnd)
                if (max(abs(err[0]), abs(err[1])) < 0.012 and abs(err[2]) < 0.04) or rnd == args.rounds:
                    break
                # The channels each want: same light share as the reference,
                # total light on the reference curve.
                gw = yt / (ymat[0] * r0 + ymat[1] + ymat[2] * b0)
                want = (r0 * gw, gw, b0 * gw)
                have = (mm["R"], mm["G"], mm["B"])
                for j, c in enumerate("RGB"):
                    # Near black the panel doesn't respond in proportion (a
                    # code-1 pixel among blacks gives far less than a code-1
                    # patch), so each channel's slope in log-log is learned
                    # from its last two readings.
                    if prev[c] and abs(math.log(trim[c][i] / prev[c][0])) > 1e-3 and have[j] > 0 and prev[c][1] > 0:
                        slope[c] = max(0.5, min(8.0, math.log(have[j] / prev[c][1])
                                                / math.log(trim[c][i] / prev[c][0])))
                    prev[c] = (trim[c][i], have[j])
                    step_ = 0.8 * math.log(want[j] / have[j]) / slope[c] if have[j] > 0 else 0.5
                    # Small steps: one noisy reading near black must not throw it.
                    trim[c][i] = max(0.05, min(4.0, trim[c][i] * math.exp(max(-0.5, min(0.5, step_)))))
                push()
            if best and best[2] != rnd:
                # It didn't settle: keep the round that came closest.
                for c, x in zip("RGB", best[1]):
                    trim[c][i] = x
                log(f"level {level}: keeping round {best[2]} (trim {[round(float(x), 3) for x in best[1]]})")
                push()
    finally:
        try:
            rig.close()
        except Exception as e:                    # the settings come back regardless
            log(f"rig cleanup failed: {e}")
        def m(d):
            d["dither"], d["crush"] = bool(keep["dither"]), crush     # as it was before the run
            d["dither_temporal"] = keep["dither_temporal"] or False
            d["dither_temporal_ui"] = bool(keep["dither_temporal_ui"])
            d["dither_ui"] = keep["dither_ui"] is not False
        plugin.change(m, compiled=False)
        log(f"trim kept in the dither table; dither and crush as before ({bool(keep['dither'])}, {crush}); history {path}")


def cmd_apply(args):
    """Write a proposal's step into a named profile (created empty if new);
    if that profile is the active one, the screen follows at once."""
    with open(args.proposal) as f:
        p = json.load(f)["proposal"]

    def m(d):
        profiles = d.setdefault("profiles", {})
        if args.profile not in profiles:
            profiles[args.profile] = [{"b": s["b"], **{k: [None] * len(s[k]) for k in "vlh"}}
                                      for s in d["steps"]]
        targets = [profiles[args.profile]] + ([d["steps"]] if d.get("profile") == args.profile else [])
        for steps in targets:
            si = [s["b"] for s in steps].index(p["step"])
            for i, lv in enumerate(plugin.LEVELS):
                steps[si]["v"][i], steps[si]["l"][i], steps[si]["h"][i] = p["values"][str(lv)]
    plugin.backup(os.path.join(STATE, f"settings-before-apply-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    plugin.change(m)
    log(f"step {p['step']} written to profile {args.profile!r}")


def cmd_report(args):
    with open(os.path.join(RUNS, args.name + ".json")) as f:
        run = json.load(f)
    ref = None
    if args.against:
        with open(os.path.join(RUNS, args.against + ".json")) as f:
            ref = json.load(f)
    print(f"{run['name']} (correction {run['correction']})")
    print("step  level    R/G     B/G   relY(128)" + ("   dR/G%   dB/G%  dY%" if ref else ""))
    for b in sorted({r["step"] for r in run["records"]}):
        recs = {r["level"]: r for r in run["records"] if r["step"] == b}
        y128 = recs.get(128, {}).get("Y")
        for lv in sorted(recs):
            r = recs[lv]
            rr, bb = ratios(r)
            rel = r["Y"] / y128 if y128 else float("nan")
            line = f"{b:>4}  {lv:>5}  {rr:6.3f}  {bb:6.3f}  {rel:9.4f}"
            if ref:
                r0, b0, rel0 = targets(ref, lv)
                line += f"  {100 * (rr / r0 - 1):+6.1f}  {100 * (bb / b0 - 1):+6.1f}  {100 * (rel / rel0 - 1):+5.0f}"
            print(line)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--backlight", type=int, default=543)
    s.add_argument("--fraction", type=float, default=0.3)
    s = sub.add_parser("measure")
    s.add_argument("--steps", required=True)
    s.add_argument("--levels", default=",".join(map(str, plugin.LEVELS)))
    s.add_argument("--correction", choices=("on", "off"), default="off")
    s.add_argument("--name", required=True)
    s = sub.add_parser("calibrate")
    s.add_argument("--steps", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--levels", default=",".join(map(str, plugin.LEVELS[:-1])))
    s.add_argument("--rounds", type=int, default=4)
    s.add_argument("--lift", type=float, help="hold brightness at this value (default: as set)")
    s.add_argument("--profile", help="calibrate in this profile (created from the active one if new)")
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("floor")
    s.add_argument("--step", type=int, default=177)
    s.add_argument("--codes", default="0,1,2,3,4,5,6,8,10,12,16,20,24,32")
    s.add_argument("--name", required=True)
    s = sub.add_parser("dither-table")
    s.add_argument("--step", type=int, default=177)
    s.add_argument("--floor", required=True, help="floor run names, comma separated")
    s.add_argument("--reference", required=True)
    s.add_argument("--V", type=int, default=64)
    s.add_argument("--cell", type=int, default=1, help="dither cell height in rows (see pattern_test.py cells)")
    s = sub.add_parser("dither-calibrate")
    s.add_argument("--step", type=int, default=177)
    s.add_argument("--reference", required=True)
    s.add_argument("--levels", default="4,8,12,16,20,24,32,40,48")
    s.add_argument("--rounds", type=int, default=6)
    s.add_argument("--curve", choices=("g22", "native"), default="native",
                   help="target below the hand-over: gamma 2.2 or the reference's own curve (the plugin's shadow_curve)")
    s.add_argument("--mode", choices=("still", "pair", "golden"), default="still",
                   help="the dither mode to calibrate (moving ones with an animated patch)")
    s = sub.add_parser("apply")
    s.add_argument("proposal")
    s.add_argument("--profile", default="Camera")
    s = sub.add_parser("report")
    s.add_argument("name")
    s.add_argument("--against")
    args = ap.parse_args()
    globals()["cmd_" + args.cmd.replace("-", "_")](args)


if __name__ == "__main__":
    main()

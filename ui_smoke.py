"""Automated UI smoke test of the OLED Tint plugin on the device, no camera:
drives Steam's brightness through its UI (debug port, like a user's slider),
then checks what really happened - the backlight in sysfs, gamescope's
effect and technique atoms, the plugin's settings, state file and log.
Everything is given back at the end. ~2 min; the screen changes brightness.
usage: python3 ui_smoke.py   (exit 1 if any check fails)"""
import glob, json, os, sys, threading, time
sys.path.insert(0, os.path.expanduser("~/projects/decky-oled-tint"))
import cdp
import plugin
from screen import read_backlight
import main as plug

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


def atom(name):
    import subprocess
    r = subprocess.run(["env", "DISPLAY=:0", "xprop", "-root", name], capture_output=True, text=True, timeout=10)
    line = r.stdout.strip()
    if "=" not in line:
        return None
    v = line.split("=", 1)[1].strip()
    return v.strip('"') if v.startswith('"') else int(v) if v.isdigit() else v


def log_errors():
    logs = sorted(glob.glob(os.path.join(plugin.LOGS, "*.log")), key=os.path.getmtime)
    if not logs:
        return 0
    with open(logs[-1], errors="replace") as f:
        return sum(1 for l in f if "[ERROR]" in l or "Traceback" in l)


def wait(cond, seconds=6.0):
    end = time.time() + seconds
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(0.2)
    return cond()


steam = cdp.shared()
ask = lambda f: steam.eval(f"SteamClient.System.Display.SetBrightness({f:.4f}); true")
floor = plug.floor_of(plugin.read())
errors0 = log_errors()
start_bl = read_backlight()

with plugin.switches_kept():
    keep_target = plugin.read().get("soft_target")
    try:
        plugin.change(lambda d: d.update(enabled=True, engine="reshade", dimming="soft"), compiled=False)
        ask(0.5)                                            # start above the floor, undimmed
        time.sleep(2)
        st = plugin._state() or {}
        check("plugin answers (state file has a revision)", st.get("revision") is not None, f"revision {st.get('revision')}")

        # 1. A slider move into the band: the backlight stays at the floor, the
        #    picture is dimmed instead.
        ask(0.15)
        bl = wait(lambda: (lambda b: b if abs(b - floor) <= floor * 0.03 else None)(read_backlight()))
        check("in-band request: backlight held at the floor", bl, f"backlight {read_backlight()}, floor {floor}")
        t1 = wait(lambda: (lambda t: t if t and t < floor else None)(plugin.read().get("soft_target")))
        check("in-band request: stored as the dimming target", t1, f"soft_target {plugin.read().get('soft_target')}")
        eff1 = wait(lambda: atom(plug.RESHADE_ATOM))
        check("a ReShade effect is on screen", eff1 and str(eff1).startswith("oled"), f"{eff1}")
        if t1:
            want = plug.gain_index(plug.soft_gain(t1, read_backlight()))
            got = wait(lambda: atom(plug.RESHADE_TECHNIQUE_ATOM) if abs((atom(plug.RESHADE_TECHNIQUE_ATOM) or 0) - want) <= 1 else None)
            check("the technique matches the target's gain", got is not None, f"atom {atom(plug.RESHADE_TECHNIQUE_ATOM)}, expected {want}")

        # 2. Lower still: only the technique moves, no new effect (no stutter).
        ask(0.07)
        t2 = wait(lambda: (lambda t: t if t and t1 and t < t1 else None)(plugin.read().get("soft_target")))
        check("lower request: target follows", t2, f"soft_target {plugin.read().get('soft_target')}")
        time.sleep(1.5)
        check("lower request: same effect, no recompile", atom(plug.RESHADE_ATOM) == eff1, f"{atom(plug.RESHADE_ATOM)}")
        check("lower request: backlight still at the floor", abs(read_backlight() - floor) <= floor * 0.03,
              f"backlight {read_backlight()}")

        # 3. Above the floor: the real backlight follows, nothing dimmed.
        ask(0.6)
        bl3 = wait(lambda: (lambda b: b if b > floor * 1.3 else None)(read_backlight()))
        check("above-floor request: backlight follows", bl3, f"backlight {read_backlight()}")

        # 4. Back in the band, then correction off: the effect goes and the
        #    asked-for brightness comes back.
        ask(0.15)
        wait(lambda: abs(read_backlight() - floor) <= floor * 0.03)
        # Meanwhile, in that order: the effect first (it can only go), then the
        # backlight (it can only drop): the floor with no effect is a real flash.
        samples, stop = [], threading.Event()
        def sample():
            while not stop.is_set():
                on = str(atom(plug.RESHADE_ATOM) or "").startswith("oled")
                samples.append((on, read_backlight()))
        sampler = threading.Thread(target=sample)
        sampler.start()
        try:
            plugin.change(lambda d: d.update(enabled=False), compiled=False)
            gone = wait(lambda: not str(atom(plug.RESHADE_ATOM) or "").startswith("oled"), 8)
            back = wait(lambda: read_backlight() < floor * 0.9, 8)
        finally:
            stop.set()
            sampler.join()
        check("correction off: effect removed", gone, f"{atom(plug.RESHADE_ATOM)}")
        check("correction off: the asked-for (lower) backlight given back", back, f"backlight {read_backlight()}")
        flash = [bl for on, bl in samples if not on and bl >= floor * 0.97]
        check("correction off: the backlight dropped before the effect went (no floor undimmed)", not flash,
              f"{len(flash)} of {len(samples)} samples at the floor without the effect")

        # 5. Back on (review 10-31 #1): up to the floor again, dimmed for the
        #    target. It used to stay in the band, uncorrected, until the next
        #    slider move.
        def at_floor_dimmed():
            t, tech = plugin.read().get("soft_target"), atom(plug.RESHADE_TECHNIQUE_ATOM)
            return abs(read_backlight() - floor) <= floor * 0.03 and t and isinstance(tech, int) \
                and abs(tech - plug.gain_index(plug.soft_gain(t, floor))) <= 1
        now = lambda: f"backlight {read_backlight()}, technique {atom(plug.RESHADE_TECHNIQUE_ATOM)}, soft_target {plugin.read().get('soft_target')}"
        plugin.change(lambda d: d.update(enabled=True), compiled=False)
        check("correction back on: at the floor again, dimmed", wait(at_floor_dimmed, 8), now())

        # 6. The same through the frontend's switch (the sidebar toggle, the
        #    Test pattern's Y): off and straight on again, then Compare, which
        #    showed the floor undimmed (review 10-31 #2).
        hook = steam.eval("typeof OLEDTint === 'object'")
        check("frontend test hook (window.OLEDTint)", hook)
        if hook:
            steam.eval("OLEDTint.correction(false); true")
            check("switch off: the target's backlight", wait(lambda: read_backlight() < floor * 0.9, 4), now())
            steam.eval("OLEDTint.correction(true); true")
            check("switch back on: at the floor again, dimmed", wait(at_floor_dimmed, 8), now())
            steam.eval("OLEDTint.compare(4); true")
            check("Compare: the backlight at the target", wait(lambda: read_backlight() < floor * 0.9, 2), now())
            check("Compare: no effect meanwhile", wait(lambda: not str(atom(plug.RESHADE_ATOM) or "").startswith("oled"), 3),
                  f"{atom(plug.RESHADE_ATOM)}")
            time.sleep(4)
            check("after Compare: at the floor again, dimmed", wait(at_floor_dimmed, 8), now())
    finally:
        plugin.change(lambda d: d.update(soft_target=keep_target), compiled=False)

try:
    from screen import Screen
    Screen().brightness(start_bl)                   # the brightness the test found
except Exception as e:
    print(f"note: brightness not restored to {start_bl}: {e}")
time.sleep(1)
check("no new errors in the plugin log", log_errors() == errors0, f"{log_errors() - errors0} new")
failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED: {', '.join(r[0] for r in failed)}" if failed else ""))
sys.exit(1 if failed else 0)

"""The OLED Tint plugin's settings file, which it re-reads within a second."""
import contextlib
import fcntl
import glob
import json
import os
import shutil
import subprocess
import time

SETTINGS = os.path.expanduser("~/homebrew/settings/decky-oled-tint/settings.json")
LOGS = os.path.expanduser("~/homebrew/logs/decky-oled-tint")
# 8-bit labels of the plugin's levels (k/64), in order.
LEVELS = [4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 255]


def read():
    with open(SETTINGS) as f:
        return json.load(f)


# The plugin writes the same file: both take this lock around their writes
# (change() around its whole read-modify-write), each with a temp file of
# its own (a shared "settings.json.tmp" let one writer truncate the other's).
LOCK = SETTINGS + ".lock"


@contextlib.contextmanager
def locked():
    fd = os.open(LOCK, os.O_RDONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _write(data):
    tmp = f"{SETTINGS}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SETTINGS)


def write(data):
    with locked():
        _write(data)


STATE = "/tmp/oled-tint-state.json"         # written by the plugin each round


def _state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_state_since(mtime, revision=None):
    """The plugin has read settings written at `mtime` and has nothing
    pending (a deferred apply counted as read before: review 11).
    Prefer the adoption `revision` (exact, immune to a coarse clock) when
    both sides report one; otherwise fall back to the settings mtime."""
    st = _state()
    if revision is not None and st and st.get("revision") is not None:
        return st["revision"] > revision and not st.get("pending")
    got = st and st.get("settings_mtime")
    return got is not None and got >= mtime - 1e-6 and not st.get("pending")


def settle(backlight, since, timeout=30.0):
    """After moving the backlight: wait until the plugin's correction for it
    is on screen. With the state file: the plugin at this backlight with
    nothing pending, and gamescope's compile if a new effect came; without
    (an older plugin): a compile seen within 10 s, or go on."""
    if os.path.exists(STATE):
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = _state() or {}
            b = st.get("backlight")
            if b and abs(b - backlight) <= max(2, backlight * 0.03) and not st.get("pending"):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError(f"the plugin didn't settle at backlight {backlight}")
        # Its effect changed for this step: that compile, not an earlier one
        # (an intermediate brightness's could satisfy a plain check).
        changed = st.get("effect_since")
        if changed and changed >= since and st.get("effect"):
            if not _wait_compiled(changed - 0.5, 45):
                raise RuntimeError(f"gamescope never confirmed compiling the effect for backlight {backlight}")
    else:
        _wait_compiled(since, 10)              # older plugin: best effort
    time.sleep(1.0)


SLIDER_LOG = "/tmp/oled-slider.log"           # the plugin's per-step log


def _technique_atom():
    """The technique index gamescope is told to use now (root atom), or None."""
    r = subprocess.run(_host() + ["env", "DISPLAY=:0", "xprop", "-root",
                                  "GAMESCOPE_RESHADE_TECHNIQUE_IDX"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        if "=" in line:
            return int(line.rsplit("=", 1)[1])
    return None


def _last_technique(since):
    """The last technique the plugin switched to after `since` (its own log),
    or None when it logged no switch then."""
    try:
        with open(SLIDER_LOG) as f:
            lines = [l for l in f if " B technique " in l]
    except OSError:
        return None
    for line in reversed(lines):
        ts, _, rest = line.partition(" ")
        if float(ts) >= since and rest.startswith("B technique "):
            return int(rest.split()[2])
    return None


def handshake(since, expect_effect=None, timeout=30.0, check_compile=True):
    """Before a capture: the effect on screen is what we expect (a step that
    only moves the technique never recompiles - gamescope caches effects by
    name - so the root atom against the plugin's own log line is the check),
    and an effect changed for this step has its compile. Adoption itself is
    change()/settle()'s job. Returns the active effect name to pin later steps."""
    st = _state() or {}
    if not st.get("effect"):
        raise RuntimeError("the state file reports no active effect")
    if expect_effect and st["effect"] != expect_effect:
        raise RuntimeError(f"the effect changed to {st['effect']} (expected {expect_effect})")
    since_fx = st.get("effect_since")
    if check_compile and since_fx and since_fx >= since:
        if not _wait_compiled(since_fx - 0.5, 45):
            raise RuntimeError("gamescope never confirmed compiling the new effect")
    want = _last_technique(since)
    if want is not None:
        deadline = time.time() + timeout
        while time.time() < deadline and _technique_atom() != want:
            time.sleep(0.2)
        got = _technique_atom()
        if got != want:
            raise RuntimeError(f"the technique atom reads {got}, the plugin switched to {want}")
    return st["effect"]


CONDITION_ATOMS = ("GAMESCOPE_COLOR_SDR_GAMUT_WIDENESS",       # Steam's colour vibrance (finding 3)
                   "GAMESCOPE_SDR_ON_HDR_CONTENT_BRIGHTNESS",   # SDR content nits
                   "GAMESCOPE_DISPLAY_HDR_ENABLED", "GAMESCOPE_SDR_INPUT_GAIN")


def conditions():
    """What the screen runs under besides our settings, for a run's JSON: the
    gamescope atoms that change what a grey looks like, the plugin's switches
    and state, the raw backlight. RESULTS 28: two nights differed with no
    record of why."""
    import struct
    out = {"time": time.time()}
    r = subprocess.run(_host() + ["env", "DISPLAY=:0", "xprop", "-root", *CONDITION_ATOMS],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        name, _, val = line.partition("(CARDINAL) = ")
        if val.strip().isdigit():
            v = int(val)
            out[name.strip()] = v if v < 2 else round(struct.unpack("f", struct.pack("I", v))[0], 4)
    data = read()
    out["switches"] = {k: data.get(k) for k in SWITCHES}
    out["state"] = _state()
    try:
        with open("/sys/class/backlight/" + os.listdir("/sys/class/backlight")[0] + "/actual_brightness") as f:
            out["backlight_sysfs"] = int(f.read())
    except (OSError, IndexError, ValueError):
        pass
    return out


SWITCHES = ("enabled", "engine", "dither", "crush", "dither_temporal", "dither_temporal_ui", "dither_ui",
            "shadow_curve", "menu_correction", "dimming", "profile", "floor_backlight")


@contextlib.contextmanager
def switches_kept():
    """The plugin's switches as they were before a measuring command, given
    back however it ends (a camera that won't start, a cleanup that fails),
    while what it measured (tables, trims, steps) stays (review 17)."""
    before = {k: v for k, v in read().items() if k in SWITCHES}
    try:
        yield
    finally:
        def m(d):
            d.update(before)
            if before.get("profile") in (d.get("profiles") or {}):
                d["steps"] = d["profiles"][before["profile"]]
        change(m, compiled=False)


def backup(dest):
    shutil.copy(SETTINGS, dest)
    return dest


def _last_applied():
    log = max(glob.glob(os.path.join(LOGS, "*.log")), key=os.path.getmtime)
    with open(log) as f:
        stamps = [line[1:24] for line in f if "applied" in line or "Unloaded" in line]
    return stamps[-1] if stamps else ""


def _compiled_since(t0):
    """Has gamescope compiled a ReShade effect since unix time t0?"""
    # Inside the toolbox the journal is the host's, reached via flatpak-spawn.
    r = subprocess.run(_host() + ["journalctl", "--user", "--since", f"@{t0:.3f}",
                        "--no-pager", "-o", "short-unix"], capture_output=True, text=True, timeout=20)
    return any("Compiling pass" in line and float(line.split()[0]) > t0 for line in r.stdout.splitlines())


def change(mutate, settle=1.0, compiled=True):
    """Edit the settings with mutate(data) and wait until the plugin has
    applied them, and (compiled=True) until gamescope has actually compiled
    the new effect: it picks up a new effect anywhere from 0.2 to ~30 s
    later, and measuring before that reads the old one. Then `settle` s."""
    before = _last_applied()
    started = time.time() - 0.5             # a compile from here on is this change's (review 14)
    rev_before = (_state() or {}).get("revision")   # the plugin's adoptions so far
    with locked():                          # read-modify-write in one go
        data = read()
        mutate(data)
        _write(data)
        written = os.path.getmtime(SETTINGS)
    if os.path.exists(STATE):
        # A plugin that says what it has read: wait for it to take this
        # change up (it then applies a new effect, or needs none). No answer:
        # stop rather than measure against whatever is on screen.
        deadline = time.time() + 20
        while time.time() < deadline and not _read_state_since(written, rev_before):
            time.sleep(0.2)
        if not _read_state_since(written, rev_before):
            raise RuntimeError("the plugin never confirmed reading the new settings")
        time.sleep(0.3)                     # its log line follows the state
    else:
        deadline = time.time() + 6          # older plugin: the log alone
        while time.time() < deadline and _last_applied() == before:
            time.sleep(0.2)
    applied = _last_applied() != before
    if compiled and applied and data.get("engine", "reshade") == "reshade":
        if not _wait_compiled(started, 45):
            # No compile seen (29 times in the runs up to 2026-10-25, the
            # rounds measured anyway). Force a fresh one: with its effect atom
            # gone the plugin sets it again, and gamescope compiles. Still
            # nothing: stop rather than measure against an unknown effect.
            print("note: no compile seen; setting the effect again", flush=True)
            t1 = time.time() - 0.5
            _xprop("-root", "-remove", "GAMESCOPE_RESHADE_EFFECT")
            if not _wait_compiled(t1, 45):
                raise RuntimeError("gamescope never confirmed compiling the new effect")
    if applied and os.path.exists(STATE) and data.get("enabled", True) \
            and data.get("engine", "reshade") == "reshade" and (_state() or {}).get("effect"):
        # The effect and technique on screen are the plugin's last (a
        # technique-only step never recompiles; review 2026-10-30: this
        # check was written but never called).
        handshake(started, check_compile=compiled)     # compiled=False: the caller waits for no compile (2026-10-30: a 600 sweep stopped here)
    time.sleep(settle)


def _host():
    return [] if shutil.which("journalctl") and not os.path.exists("/run/.containerenv") else ["flatpak-spawn", "--host"]


def _xprop(*args):
    subprocess.run(_host() + ["env", "DISPLAY=:0", "xprop", *args], capture_output=True, timeout=10)


def _wait_compiled(t0, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _compiled_since(t0):
            return True
        time.sleep(0.5)
    return False


def set_enabled(on):
    def m(d):
        d["enabled"] = on
        d["engine"] = "reshade"
    # Turning off removes the effect (nothing to compile); give it a moment.
    change(m, settle=2.0 if not on else 1.0, compiled=on)


def step_index(data, b):
    return [s["b"] for s in data["steps"]].index(b)

"""The camera, through gphoto2 (Sony "PC Remote" over USB)."""
import os
import subprocess
from fractions import Fraction

SHUTTER = "/main/capturesettings/shutterspeed"
# At least a few frames at 120 Hz, so the panel's refresh and PWM flicker
# average out (silent/electronic shutter reads out line by line on top).
MIN_SECONDS = float(os.environ.get("OLED_MIN_SECONDS", 1 / 30))   # shorter only where the panel does not flicker (full backlight)
# Longer exposures fail over USB on the A7 III (with long-exposure noise
# reduction the camera takes a second, equally long dark frame and gphoto2
# gives up waiting); more light comes from ISO instead.
MAX_SECONDS = 15
ISO = "/main/imgsettings/iso"


def _gp(*args, timeout=120):
    r = subprocess.run(["gphoto2", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip()
        if "No camera found" in msg:
            msg += "\n" + usb_diagnosis()
        raise RuntimeError(f"gphoto2 {' '.join(args)}: {msg}")
    return r.stdout


USB = "/sys/bus/usb/devices"


def usb_diagnosis():
    """What the Odin sees on USB, in plain words, for a "No camera found":
    whether it's the camera, the hub, or nothing at all (2026-10-29: the
    hub's inner chip dropped and the camera was still blamed three times)."""
    devs, empty = [], []
    try:
        for d in sorted(os.listdir(USB)):
            path = os.path.join(USB, d)
            if os.path.exists(os.path.join(path, "idVendor")):
                rd = lambda f: open(os.path.join(path, f)).read().strip() if os.path.exists(os.path.join(path, f)) else ""
                devs.append((d, rd("idVendor"), rd("idProduct"), rd("product")))
            for port in os.listdir(path) if ":" in d else []:
                st = os.path.join(path, port, "state")
                if port.startswith(d.split(":")[0] + "-port") and os.path.exists(st) \
                        and open(st).read().strip() == "not attached":
                    empty.append(f"{d.split(':')[0]}.{port.split('-port')[-1]}")
    except OSError as e:
        return f"USB: couldn't read {USB} ({e})"
    sony = [d for d in devs if d[1] == "054c"]
    hubs = [d for d in devs if "hub" in d[3].lower() and not d[0].startswith("usb")]
    lines = ["USB as the Odin sees it: " + ", ".join(f"{d[0]} {d[1]}:{d[2]} {d[3]}" for d in devs if not d[0].startswith("usb"))]
    if sony:
        lines.append("A Sony device is attached but gphoto2 can't use it: the camera's USB mode "
                     "isn't PC Remote, or another program holds it.")
    elif not hubs:
        lines.append("No hub at all: the hub or its cable to the Odin is not connected.")
    else:
        lines.append(f"The hub is there, nothing on its ports ({', '.join(empty) or 'none listed'} empty): no "
                     "data from the camera's side. Camera off/asleep, cable, or the hub's inner chip "
                     "(unplug the hub's power AND its Odin cable 10 s).")
    return "\n".join(lines)


def _choices(key):
    out = _gp("--get-config", key)
    return [line.split(" ", 2)[2] for line in out.splitlines() if line.startswith("Choice:")]


def _seconds(label):
    """'1/250' -> 0.004, '32/10' -> 3.2, '30' -> 30."""
    return float(Fraction(label))


class Camera:
    def __init__(self, iso=200):
        self.shutters = sorted((s for s in _choices(SHUTTER)
                                if s.replace("/", "").isdigit() and _seconds(s) <= MAX_SECONDS),
                               key=_seconds)
        self.isos = [i for i in _choices(ISO) if i.isdigit()]
        if not self.isos:   # the A7 IV lists no choices but takes any standard value
            self.isos = [str(i) for i in (100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250,
                                           1600, 2000, 2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800)]
        self.iso = None
        self.shutter = None
        self.set(iso=iso, seconds=1 / 60)

    def set(self, iso=None, seconds=None):
        if iso is not None and str(iso) != self.iso:
            _gp("--set-config-value", f"{ISO}={iso}")
            self.iso = str(iso)
        if seconds is not None:
            seconds = max(seconds, MIN_SECONDS)
            label = min((s for s in self.shutters if _seconds(s) >= MIN_SECONDS * 0.99),
                        key=lambda s: abs(_seconds(s) / seconds - 1))
            if label != self.shutter:
                _gp("--set-config-value", f"{SHUTTER}={label}")
                self.shutter = label

    @property
    def seconds(self):
        return _seconds(self.shutter)

    @property
    def longest(self):
        return _seconds(self.shutters[-1])

    def capture(self, path):
        """Shoot and download one raw file to `path`. A broken download is
        retried; a camera that has gone (battery, auto power-off) stops the
        run with a clear message."""
        err = "file too short"
        for attempt in range(3):
            if os.path.exists(path):
                os.remove(path)
            try:
                _gp("--capture-image-and-download", "--filename", path, "--force-overwrite",
                    timeout=max(60, self.seconds * 2 + 60))
                if os.path.getsize(path) > 10_000_000:   # a full ARW is ~49 MB
                    return path
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                err = e
            if "usb:" not in _gp("--auto-detect"):
                raise RuntimeError("camera disconnected (battery? auto power-off?)")
        raise RuntimeError(f"capture failed three times: {err}")

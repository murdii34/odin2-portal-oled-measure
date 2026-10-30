"""One take of the show-off triptych: the A7 IV (USB streaming, UVC) records
while the backlight sweeps 310 -> 4096 -> 40 -> 310, identical for every
take, so the takes line up by their start. The info overlay is on for the
take. Writes runs/showoff-<label>.mkv and the sweep's start in a .json.
Runs on the host (ffmpeg, no camera tool imports).
    showoff_take.py LABEL [SECONDS]"""
import glob
import json
import math
import os
import subprocess
import sys
import time

import plugin
from screen import Screen

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
LO, HI, START = 40, 4096, 310
# Steam slider fraction -> raw backlight on this device (as the plugin's
# frontend has it), interpolated in log(raw).
CURVE = [(0, 40), (0.01, 43), (0.05, 57), (0.1, 80), (0.15, 113), (0.2, 159), (0.25, 223), (0.3, 313),
         (0.35, 440), (0.4, 617), (0.45, 867), (0.5, 1217), (0.75, 2332), (1, 4096)]


def fraction(raw):
    for (f0, r0), (f1, r1) in zip(CURVE, CURVE[1:]):
        if raw <= r1:
            k = (math.log(raw) - math.log(r0)) / (math.log(r1) - math.log(r0))
            return min(1.0, max(0.0, f0 + k * (f1 - f0)))
    return 1.0


def backlight_at(ph):
    """0..1 through the take: up from START to HI, down to LO, up to START,
    eased at the turns, in log brightness."""
    a, b, s = math.log(LO), math.log(HI), math.log(START)
    ease = lambda u: 0.5 - 0.5 * math.cos(math.pi * u)
    if ph < 0.25:
        x = s + (b - s) * ease(ph / 0.25)
    elif ph < 0.75:
        x = b + (a - b) * ease((ph - 0.25) / 0.5)
    else:
        x = a + (s - a) * ease((ph - 0.75) / 0.25)
    return math.exp(x)


def camera():
    for d in sorted(glob.glob("/sys/class/video4linux/video*")):
        name = open(os.path.join(d, "name")).read().strip()
        if any(k in name for k in ("Sony", "ILCE", "7M4", "UVC")):
            return "/dev/" + os.path.basename(d), name
    raise SystemExit("no USB streaming camera (A7 IV set to USB Streaming?)")


def main():
    label = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 180   # the band down in ~40 s: the correction keeps up
    out = os.path.join(RUNS, f"showoff-{label}.mkv")
    dev, name = camera()
    print(f"camera {name} at {dev}", flush=True)
    # (The info overlay renders as a tiny glyph in this MangoHud: the label is
    # burned in when stitching instead.)
    screen = Screen()
    screen.brightness(START)
    time.sleep(3)
    rec = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
                            "-video_size", "1280x720", "-framerate", "30", "-i", dev, "-c", "copy", out])
    t0 = time.time()
    try:
        time.sleep(3)                               # lead-in at START
        sweep0 = time.time()
        while (t := time.time() - sweep0) < seconds:
            screen._set_fraction(fraction(backlight_at(t / seconds)))
            time.sleep(0.1)
        screen.brightness(START)
        time.sleep(3)
    finally:
        rec.terminate()
        rec.wait(timeout=15)
    json.dump({"label": label, "lead_in": sweep0 - t0, "seconds": seconds}, open(out + ".json", "w"))
    print(f"take {label}: {out}, sweep {seconds:.0f} s after {sweep0 - t0:.1f} s lead-in", flush=True)


if __name__ == "__main__":
    main()

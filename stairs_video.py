"""The bottom of Steam's slider stepped quickly, filmed (murdii 2026-10-30):
"coming from 0% going up, at around 10% it does a big jump, then goes back
down quickly". stairs.py waited each step out; this one holds each 1% step
only DWELL seconds, the way a D-pad press does, while the A7 IV (USB
streaming, UVC) records 30 fps. Brightness goes through Steam's
SetBrightness (the plugin's intercept, snap + floor dimming as set below),
each call's time logged, so a frame's light lines up with the step it
followed and the plugin's slider log. Runs on the host (like showoff_take).
    stairs_video.py LABEL [DWELLS [TOP [REPS]]]     e.g. stairs_video.py t1 1,0.5,0.25 25 2
    stairs_video.py --analyse LABEL                 per-frame light -> jumps"""
import json
import os
import subprocess
import sys
import time

import cdp
import plugin
from showoff_take import RUNS, camera
from screen import Screen

GREY = 128           # a mid grey: neither clipped at 25% nor lost at 0%
SLIDER_LOG = "/tmp/oled-slider.log"


def set_slider(f):
    cdp.shared().eval(f"SteamClient.System.Display.SetBrightness({f:.4f}); true")


def take(label, dwells, top, reps):
    out = os.path.join(RUNS, f"stairs-video-{label}.mkv")
    dev, name = camera()
    print(f"camera {name} at {dev}", flush=True)
    # The Odin is a dev/demo device: set what this take needs, log it.
    plugin.change(lambda d: d.update(enabled=True, engine="reshade", dimming="soft", band_snap=True,
                                     dither=False, floor_backlight=None))
    settings = {k: plugin.read().get(k) for k in ("enabled", "engine", "dimming", "band_snap", "dither", "profile")}
    screen = Screen()
    screen.patch(GREY)
    set_slider(0)
    time.sleep(4)
    logpos = os.path.getsize(SLIDER_LOG) if os.path.exists(SLIDER_LOG) else 0
    events = []
    rec = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
                            "-video_size", "1280x720", "-framerate", "30", "-i", dev, "-c", "copy", out])
    t0 = time.time()
    try:
        time.sleep(3)                                   # lead-in at 0%
        for dwell in dwells:
            for rep in range(reps):
                for p in list(range(1, top + 1)) + list(range(top - 1, -1, -1)):
                    events.append({"t": time.time() - t0, "pct": p, "dwell": dwell, "rep": rep})
                    set_slider(p / 100)
                    time.sleep(dwell)
                time.sleep(3)                           # settle at 0% between passes
    finally:
        time.sleep(2)
        rec.terminate()
        rec.wait(timeout=15)
        screen.hide()
        try:
            with open(SLIDER_LOG) as f:
                f.seek(logpos)
                slider = f.read().splitlines()
        except OSError:
            slider = []
        json.dump({"label": label, "t0": t0, "dwells": dwells, "top": top, "reps": reps, "grey": GREY,
                   "settings": settings, "events": events, "slider_log": slider},
                  open(out + ".json", "w"), indent=1)
    print(f"take {label}: {out}, {len(events)} steps", flush=True)


def analyse(label):
    """Mean of the screen's middle per frame (ffmpeg, grey), against the step
    times: per step the light it settles at (last third of its dwell) and the
    highest/lowest frame on the way (overshoot / dip against both neighbours)."""
    out = os.path.join(RUNS, f"stairs-video-{label}.mkv")
    meta = json.load(open(out + ".json"))
    # ffmpeg averages: the middle third of the frame shrunk to 8x8 (no numpy on the host)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vf", "crop=iw/3:ih/3,scale=8:8:flags=area",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    light = [sum(raw[i:i + 64]) / 64 for i in range(0, len(raw) - 63, 64)]
    fps = 30.0
    t = [i / fps for i in range(len(light))]
    json.dump(light, open(out + ".light.json", "w"))
    ev = meta["events"]
    print(f"{len(light)} frames; step: pct dwell  settled  min..max on the way  (vs previous settled)")
    prev = None
    rows = []
    for i, e in enumerate(ev):
        end = ev[i + 1]["t"] if i + 1 < len(ev) and ev[i + 1]["dwell"] == e["dwell"] else e["t"] + e["dwell"]
        seg = [v for v, ti in zip(light, t) if e["t"] <= ti < end]
        if not seg:
            continue
        tail = seg[-max(1, len(seg) // 3):]
        settled = sum(tail) / len(tail)
        lo, hi = min(seg), max(seg)
        flag = ""
        if prev is not None and hi > max(prev, settled) * 1.08:
            flag = f"  OVERSHOOT +{hi / max(prev, settled) - 1:.0%}"
        if prev is not None and lo < min(prev, settled) * 0.92:
            flag += f"  DIP -{1 - lo / min(prev, settled):.0%}"
        rows.append({**e, "settled": settled, "lo": lo, "hi": hi})
        print(f"{e['pct']:>3}% {e['dwell']:>5}s  {settled:7.2f}  {lo:7.2f}..{hi:7.2f}{flag}")
        prev = settled
    json.dump(rows, open(out + ".steps.json", "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "--analyse":
        analyse(sys.argv[2])
    else:
        a = sys.argv[1:]
        take(a[0], [float(x) for x in (a[1] if len(a) > 1 else "1,0.5,0.25").split(",")],
             int(a[2]) if len(a) > 2 else 25, int(a[3]) if len(a) > 3 else 2)

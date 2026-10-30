"""The hand-over lead, filmed (RESULTS 32): slider 4% <-> 5% back and forth
at several values of the frontend's lead (window.OLED_HANDOVER_LEAD: the ms
between the backend's technique switch and the backlight move), A7 IV USB
streaming at 30 fps, grey 128. Per lead and direction: the worst frame
against the settled levels around it (flash > 1, dip < 1). Runs on the host.
    handover_sweep.py LABEL [LEADS [CROSSINGS]]    e.g. handover_sweep.py s1 0,80,160,240,320,400 4"""
import json
import os
import subprocess
import sys
import time

import cdp
import plugin
from screen import Screen
from showoff_take import RUNS, camera

DWELL = 1.5


def light_trace(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "crop=iw/3:ih/3,scale=8:8:flags=area",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return [sum(raw[i:i + 64]) / 64 for i in range(0, len(raw) - 63, 64)]


def main(label, leads, n):
    out = os.path.join(RUNS, f"handover-{label}.mkv")
    dev, _ = camera()
    plugin.change(lambda d: d.update(enabled=True, engine="reshade", dimming="soft", band_snap=True,
                                     dither=False, floor_backlight=None))
    sh = cdp.shared()
    screen = Screen()
    screen.patch(128)
    sh.eval("SteamClient.System.Display.SetBrightness(0.04); true")
    time.sleep(4)
    rec = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
                            "-video_size", "1280x720", "-framerate", "30", "-i", dev, "-c", "copy", out])
    t0, events = time.time(), []
    try:
        time.sleep(2)
        for lead in leads:
            if lead >= 0:                               # a negative "lead": the built-in values
                sh.eval(f"window.OLED_HANDOVER_LEAD = {lead}; window.OLED_HANDOVER_LAG = {lead}; true")
            else:
                sh.eval("delete window.OLED_HANDOVER_LEAD; delete window.OLED_HANDOVER_LAG; true")
            for _ in range(n):
                for pct, way in ((5, "up"), (4, "down")):
                    events.append({"t": time.time() - t0, "lead": lead, "way": way})
                    sh.eval(f"SteamClient.System.Display.SetBrightness({pct / 100}); true")
                    time.sleep(DWELL)
    finally:
        sh.eval("delete window.OLED_HANDOVER_LEAD; delete window.OLED_HANDOVER_LAG; true")
        time.sleep(1)
        rec.terminate()
        rec.wait(timeout=15)
        screen.hide()
    L = light_trace(out)
    fps = 30.0
    rows = []
    for e in events:
        i0 = int((e["t"] - 0.3) * fps)
        before = sorted(L[max(0, i0 - 10):i0])[len(L[max(0, i0 - 10):i0]) // 2] if i0 > 10 else L[0]
        seg = L[i0:i0 + int(DWELL * fps)]
        after = sorted(seg[-10:])[5]
        hi, lo = max(seg), min(seg)
        rows.append({**e, "before": before, "after": after, "flash": hi / max(before, after),
                     "dip": lo / min(before, after),
                     "frames_off": sum(1 for v in seg if v > 1.15 * max(before, after) or v < 0.85 * min(before, after))})
    json.dump({"events": rows, "light": L}, open(out + ".json", "w"))
    print("lead  way   worst flash  worst dip  frames off (mean)")
    for lead in leads:
        for way in ("up", "down"):
            rs = [r for r in rows if r["lead"] == lead and r["way"] == way]
            print(f"{lead:>4}  {way:<4}  {max(r['flash'] for r in rs):>9.2f}x  {min(r['dip'] for r in rs):>8.2f}x  "
                  f"{sum(r['frames_off'] for r in rs) / len(rs):>6.1f}")


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "0,80,160,240,320,400").split(",")],
         int(sys.argv[3]) if len(sys.argv) > 3 else 4)

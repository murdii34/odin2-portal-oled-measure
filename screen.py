"""The Portal's screen: full-screen test patches and exact backlight levels."""
import time

import cdp

BACKLIGHT = "/sys/class/backlight/ae96000.dsi.0/brightness"

PATCH_JS = """(() => {
  let d = document.getElementById("oled-measure");
  if (!d) {
    d = document.createElement("div");
    d.id = "oled-measure";
    // Above everything, Steam's bars and the calibration page included.
    d.style.cssText = "position:fixed;inset:0;z-index:2147483647;cursor:none";
    document.body.appendChild(d);
  }
  d.style.background = "rgb(%(r)d,%(g)d,%(b)d)";
  return true;
})()"""

HIDE_JS = """(() => { document.getElementById("oled-measure")?.remove(); return true; })()"""

# One pixel in the top-left corner that changes every frame, so gamescope
# redraws Steam's UI continuously (it otherwise redraws only on change) and a
# dither that moves per frame really moves. Code 0/1 red on one pixel: no
# measurable light.
ANIMATE_JS = """(() => {
  const d = document.getElementById("oled-measure");
  if (!d || d.querySelector("#oled-measure-tick")) return true;
  const t = document.createElement("div");
  t.id = "oled-measure-tick";
  t.style.cssText = "position:absolute;left:0;top:0;width:1px;height:1px";
  d.appendChild(t);
  let k = 0;
  const step = () => { if (!t.isConnected) return; k ^= 1; t.style.background = `rgb(${k},0,0)`; requestAnimationFrame(step); };
  requestAnimationFrame(step);
  return true;
})()"""


def read_backlight():
    with open(BACKLIGHT) as f:
        return int(f.read())


class Screen:
    def __init__(self):
        self.ui = cdp.ui()
        self.steam = cdp.shared()
        self.animate = False       # see ANIMATE_JS
        # Steam slider fraction -> raw backlight, measured on this device.
        self.curve = [(0, 40), (0.05, 57), (0.1, 80), (0.2, 159), (0.3, 313), (0.4, 617),
                      (0.5, 1217), (0.75, 2332), (1, 4096)]

    def patch(self, code):
        """Fill the screen with grey `code` (0-255), or an (r, g, b) colour."""
        r, g, b = code if isinstance(code, tuple) else (code,) * 3
        self.ui.eval(PATCH_JS % {"r": r, "g": g, "b": b})
        if self.animate:
            self.ui.eval(ANIMATE_JS)
        else:
            self.ui.eval('(() => { document.getElementById("oled-measure-tick")?.remove(); return true; })()')

    def hide(self):
        self.ui.eval(HIDE_JS)

    def _set_fraction(self, f):
        self.steam.eval(f"SteamClient.System.Display.SetBrightness({f:.6f}); true")

    def brightness(self, target, tolerance=0.01):
        """Set the raw backlight to `target` through Steam (the only way that
        sticks), bisecting on what sysfs reports."""
        lo, hi = 0.0, 1.0
        for (f0, r0), (f1, r1) in zip(self.curve, self.curve[1:]):
            if r0 <= target <= r1:
                lo, hi = f0, f1
                break
        f = (lo + hi) / 2
        for _ in range(20):
            self._set_fraction(f)
            time.sleep(0.15)
            raw = read_backlight()
            if abs(raw - target) <= max(1, target * tolerance):
                return raw
            if raw < target:
                lo = f
            else:
                hi = f
            f = (lo + hi) / 2
        raise RuntimeError(f"could not reach backlight {target} (at {read_backlight()})")

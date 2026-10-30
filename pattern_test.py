"""Does the panel turn fine pixel patterns into the light their codes average
to? Solid levels against checkerboards and stripes, drawn by a ReShade effect
(the layer the dither works in), at one backlight step."""
import json
import math
import os
import subprocess
import sys
import time

import plugin
from measure import RUNS, Rig, log

SHADERS = os.path.expanduser("~/.local/share/gamescope/reshade/Shaders")
ATOM = "GAMESCOPE_RESHADE_EFFECT"

FX = """namespace ReShade
{
    texture BackBufferTex : COLOR;
    sampler BackBuffer { Texture = BackBufferTex; };
}
uniform float Strength = 1.0;

void VS(in uint id : SV_VertexID, out float4 pos : SV_Position, out float2 uv : TEXCOORD)
{
    uv.x = (id == 2) ? 2.0 : 0.0;
    uv.y = (id == 1) ? 2.0 : 0.0;
    pos = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
}

float m2(float x) { return x - 2.0 * floor(x * 0.5); }
float ign(float2 p) { return frac(52.9829189 * frac(dot(p, float2(0.06711056, 0.00583715)))); }

float4 PS(float4 pos : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float3 c = tex2D(ReShade::BackBuffer, uv).rgb;
    float2 p = floor(pos.xy);
    float on = %(on)s;
    float v = (on > 0.5 ? %(hi)d.0 : %(lo)d.0) / 255.0;
    float3 o = float3(%(ch)s) * v;
    // The measurement patch is white; its black frame stays black.
    return float4(c.g > 0.5 ? o * Strength : float3(0.0, 0.0, 0.0), 1.0);
}

technique PatternTest { pass { VertexShader = VS; PixelShader = PS; } }
"""

PATTERNS = {
    "solid": "1.0",
    "checker1": "m2(p.x + p.y)",
    "checker2": "m2(floor(p.x / 2.0) + floor(p.y / 2.0))",
    "checker4": "m2(floor(p.x / 4.0) + floor(p.y / 4.0))",
    "vstripe1": "m2(p.x)",
    "hstripe1": "m2(p.y)",
}
CHANNELS = {"R": "1.0, 0.0, 0.0", "G": "0.0, 1.0, 0.0", "B": "0.0, 0.0, 1.0"}


def host(*cmd):
    pre = ["flatpak-spawn", "--host"] if os.path.exists("/run/.containerenv") else []
    return subprocess.run(pre + ["env", "DISPLAY=:0", *cmd], capture_output=True, text=True, timeout=20)


def show(name, src):
    path = os.path.join(SHADERS, name)
    with open(path, "w") as f:
        f.write(src)
    for attempt in range(2):
        t0 = time.time() - 0.5
        if attempt:
            # No compile seen: set it again (from nothing, so gamescope
            # takes it as new).
            host("xprop", "-root", "-remove", ATOM)
            time.sleep(0.5)
        host("xprop", "-root", "-f", ATOM, "8u", "-set", ATOM, name)
        deadline = time.time() + 45
        while time.time() < deadline and not plugin._compiled_since(t0):
            if _failed_since(t0):
                raise RuntimeError(f"gamescope could not compile {name}")
            time.sleep(0.5)
        if _failed_since(t0):
            raise RuntimeError(f"gamescope could not compile {name}")
        if plugin._compiled_since(t0):
            time.sleep(1.0)
            return path
    # Measuring now would record whatever was on screen before (review 11).
    raise RuntimeError(f"gamescope never confirmed compiling {name}")


def _failed_since(t0):
    r = host("journalctl", "--user", "--since", f"@{t0:.3f}", "--no-pager", "-o", "cat")
    return "Failed to parse reshade" in r.stdout


def floor_run(step, codes):
    """The floor, single channels at solid codes, drawn by the shader: the
    path the dither's codes take, which is not the page's (10-bit HDR output
    rounds them differently). Saved like measure.py floor runs."""
    plugin.set_enabled(False)
    rig = Rig()
    name = f"shader-floor-{step}"
    out = {"name": name, "step": step, "records": []}
    path = os.path.join(RUNS, name + ".json")
    made = []
    try:
        rig.screen.brightness(step)
        for ch, chv in CHANNELS.items():
            for c in codes:
                if c == 0:
                    out["records"].append({"channel": ch, "code": 0, "R": 0.0, "G": 0.0, "B": 0.0,
                                           "X": 0.0, "Y": 0.0, "Z": 0.0, "seconds": 0, "iso": 0})
                    continue
                fx = FX % {"on": "1.0", "hi": c, "lo": 0, "ch": chv}
                made.append(show(f"oledtest_{ch}_solid{c}_{int(time.time() * 1000)}.fx", fx))
                r = rig.read(255, step)
                out["records"].append({"channel": ch, "code": c, **r})
                log(f"shader {ch}={c:>3}: own channel {r[ch]:9.2f}  ({r['seconds']:.3g}s ISO {r['iso']})")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
    finally:
        host("xprop", "-root", "-remove", ATOM)
        rig.close()
        for p in made:
            os.remove(p)
    log(f"saved {path}")


CELLS = (1, 2, 4)


def cells_run(step, hi):
    """Half the pixels lit at random, like the dither, in cells one pixel
    wide and h rows tall: which h makes the panel give honest half light?
    Writes the choice to state/dither-cell."""
    plugin.set_enabled(False)
    rig = Rig()
    out = {"step": step, "hi": hi, "records": []}
    path = os.path.join(RUNS, f"cells-test-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    made = []
    share = {}
    try:
        rig.screen.brightness(step)
        for ch, chv in CHANNELS.items():
            pats = [("solid", "1.0")] + [(f"cell{h}", f"ign(float2(p.x + 0.5, floor(p.y / {h}.0))) < 0.5 ? 1.0 : 0.0")
                                         for h in CELLS]
            got = {}
            for pat, expr in pats:
                made.append(show(f"oledtest_{ch}_{pat}_{int(time.time() * 1000)}.fx",
                                 FX % {"on": expr, "hi": hi, "lo": 0, "ch": chv}))
                r = rig.read(255, step)
                got[pat] = r[ch]
                out["records"].append({"channel": ch, "pattern": pat, **r})
                log(f"{ch} {pat:6s}: own channel {r[ch]:9.2f}  ({r['seconds']:.3g}s ISO {r['iso']})")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
            for h in CELLS:
                share.setdefault(h, {})[ch] = got[f"cell{h}"] / got["solid"]
                log(f"  {ch} cell 1x{h}: {share[h][ch]:.3f} of solid (honest: 0.500)")
    finally:
        host("xprop", "-root", "-remove", ATOM)
        rig.close()
        for p in made:
            os.remove(p)
    # The smallest cell whose worst channel is within 4% of honest; else the
    # one closest. (Green also runs high with fewer pixels lit; that part the
    # closed loop takes care of, so only the loss counts here.)
    def worst(h):
        return max(abs(math.log(min(v, 0.5) / 0.5)) for v in share[h].values())
    good = [h for h in CELLS if worst(h) < math.log(1 / 0.96)]
    cell = good[0] if good else min(CELLS, key=worst)
    with open(os.path.join(os.path.dirname(RUNS), "state", "dither-cell"), "w") as f:
        f.write(str(cell))
    log(f"dither cell height: {cell} rows; saved {path}")


def main():
    if sys.argv[1:2] == ["cells"]:
        return cells_run(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 2)
    if sys.argv[1:2] == ["floor"]:
        return floor_run(int(sys.argv[2]), [int(c) for c in sys.argv[3].split(",")])
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 177
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    plugin.set_enabled(False)
    rig = Rig()
    out = {"step": step, "hi": hi, "records": []}
    path = os.path.join(RUNS, f"pattern-test-{step}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    made = []
    try:
        rig.screen.brightness(step)
        for ch, chv in CHANNELS.items():
            for pat, expr in PATTERNS.items():
                name = f"oledtest_{ch}_{pat}_{int(time.time() * 1000)}.fx"
                made.append(show(name, FX % {"on": expr, "hi": hi, "lo": 0, "ch": chv}))
                r = rig.read(255, step)
                out["records"].append({"channel": ch, "pattern": pat, **r})
                log(f"{ch} {pat:9s}: own channel {r[ch]:9.2f}  ({r['seconds']:.3g}s ISO {r['iso']})")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
            solid = next(x for x in out["records"] if x["channel"] == ch and x["pattern"] == "solid")[ch]
            for x in out["records"]:
                if x["channel"] == ch and x["pattern"] != "solid":
                    log(f"  {ch} {x['pattern']:9s}: {x[ch] / solid:.3f} of solid (honest: 0.500)")
    finally:
        host("xprop", "-root", "-remove", ATOM)
        rig.close()
        for p in made:
            os.remove(p)
    log(f"saved {path}")


if __name__ == "__main__":
    main()

"""Software dimming instead of a low backlight: keep the backlight at a clean
step (543) and darken the picture in a shader by exactly the light the
panel loses at a lower step (k = grey 128 at the step / at 543, measured),
then measure grey levels for colour, light and uniformity, with and without
a blue-noise dither for the fractional codes. Compare with the hardware
step plus the plugin's correction (closed-loop checks)."""
import json
import os
import struct
import sys
import time

import plugin
from measure import RUNS, Rig, codes, log
from pattern_test import ATOM, host, show

LEVELS = [4, 8, 12, 16, 24, 32, 48, 64, 128]
HIGH = 543
GAIN = "GAMESCOPE_SDR_INPUT_GAIN"
GAIN_ONE = "1065353216"          # 1.0f

FX = """namespace ReShade
{
    texture BackBufferTex : COLOR;
    sampler BackBuffer { Texture = BackBufferTex; };
}
uniform float Strength = 1.0;
texture NoiseTex < source = "oled_tint_bluenoise_c4.png"; > { Width = 64; Height = 16; Format = R8; };
sampler Noise { Texture = NoiseTex; MagFilter = POINT; MinFilter = POINT; MipFilter = POINT;
                AddressU = REPEAT; AddressV = REPEAT; };

void VS(in uint id : SV_VertexID, out float4 pos : SV_Position, out float2 uv : TEXCOORD)
{
    uv.x = (id == 2) ? 2.0 : 0.0;
    uv.y = (id == 1) ? 2.0 : 0.0;
    pos = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
}

float4 PS(float4 pos : SV_Position, float2 uv : TEXCOORD) : SV_Target
{
    float3 c = tex2D(ReShade::BackBuffer, uv).rgb;
    // Dim in linear light (gamma 2.2): code x -> x * k^(1/2.2).
    float3 v = c * %(scale).6f * 255.0;
    float n = (tex2Dlod(Noise, float4((float2(floor(pos.x), floor(pos.y / 4.0)) + 0.5) / float2(64.0, 16.0), 0, 0)).r * 255.0 + 0.5) / 256.0;
    float3 o = %(dither)s ? floor(v) + (frac(v) > n ? 1.0 : 0.0) : floor(v + 0.5);
    return float4(o / 255.0 * Strength, 1.0);
}

technique SoftDim { pass { VertexShader = VS; PixelShader = PS; } }
"""


def main():
    steps = [int(s) for s in (sys.argv[1] if len(sys.argv) > 1 else "177,96").split(",")]
    plugin.set_enabled(False)
    rig = Rig()
    out = {"high": HIGH, "records": []}
    path = os.path.join(RUNS, f"swdim-test-{time.strftime('%Y%m%d-%H%M%S')}.json")
    made = []
    try:
        rig.screen.brightness(HIGH)
        y_high = rig.read(codes([128])[0], HIGH)["Y"]
        for step in steps:
            rig.screen.brightness(step)
            y_low = rig.read(codes([128])[0], step)["Y"]
            k = y_low / y_high
            log(f"step {step}: grey 128 gives {k:.4f} of the light at {HIGH}")
            rig.screen.brightness(HIGH)
            for dither in (False, True):
                name = f"oledtest_swdim_{step}_{int(dither)}_{int(time.time() * 1000)}.fx"
                made.append(show(name, FX % {"scale": k ** (1 / 2.2), "dither": "true" if dither else "false"}))
                for level, code in zip(LEVELS, codes(LEVELS)):
                    r = rig.read(code, HIGH)
                    out["records"].append({"step": step, "k": k, "dither": dither, "level": level, **r})
                    log(f"soft {step} dither={dither!s:5s} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  "
                        f"B/G {r['B'] / r['G']:.3f}  Y {r['Y']:.4g}  ({r['seconds']:.3g}s ISO {r['iso']})")
                    with open(path, "w") as f:
                        json.dump(out, f, indent=1)
                host("xprop", "-root", "-remove", ATOM)
            # (c) gamescope's own gain for SDR content: dims everything,
            # overlays too, in its HDR pipeline; no shader at all.
            gain = struct.unpack("<I", struct.pack("<f", k))[0]
            host("xprop", "-root", "-f", GAIN, "32c", "-set", GAIN, str(gain))
            time.sleep(3)
            for level, code in zip(LEVELS, codes(LEVELS)):
                r = rig.read(code, HIGH)
                out["records"].append({"step": step, "k": k, "dither": "gain", "level": level, **r})
                log(f"gain {step} grey {level:3d}: R/G {r['R'] / r['G']:.3f}  B/G {r['B'] / r['G']:.3f}  "
                    f"Y {r['Y']:.4g}  ({r['seconds']:.3g}s ISO {r['iso']})")
                with open(path, "w") as f:
                    json.dump(out, f, indent=1)
            host("xprop", "-root", "-f", GAIN, "32c", "-set", GAIN, GAIN_ONE)
            time.sleep(2)
    finally:
        host("xprop", "-root", "-f", GAIN, "32c", "-set", GAIN, GAIN_ONE)
        host("xprop", "-root", "-remove", ATOM)
        rig.close()
        for p in made:
            os.remove(p)
        plugin.set_enabled(True)
    log(f"saved {path}")


if __name__ == "__main__":
    main()

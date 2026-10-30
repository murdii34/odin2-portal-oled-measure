"""One photo of the Odin through the camera, as a jpeg you can look at (and
send with SendUserFile), so nobody has to take the Odin out of the hood.

    toolbox run -c oled-cam python3 look.py OUT_BASENAME [ISO] [SECONDS]

Writes OUT_BASENAME.arw and OUT_BASENAME.jpg (1600 px wide). Defaults ISO 400,
1/60 s: right for a normal game scene; the overlay strip shows well at that."""
import sys

import rawpy
from PIL import Image

import camera

out = sys.argv[1]
c = camera.Camera(iso=int(sys.argv[2]) if len(sys.argv) > 2 else 400)
c.set(seconds=float(sys.argv[3]) if len(sys.argv) > 3 else 1 / 60)
c.capture(out + ".arw")
with rawpy.imread(out + ".arw") as r:
    rgb = r.postprocess(use_camera_wb=True, half_size=True, output_bps=8)
Image.fromarray(rgb).resize((1600, 1066)).save(out + ".jpg", quality=88)
print(out + ".jpg")

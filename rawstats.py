"""Reading the patch out of a raw file: per-channel means in a fixed region.

Raw values are linear in light. The OLED's primaries keep their spectra at
every drive level, only their mix drifts, so camera R:G:B ratios track the
panel's balance whatever the camera's own colour response is.
"""
import numpy as np
import rawpy


def load(path):
    """(image, colour index map, black level, white level, cam->XYZ matrix)."""
    with rawpy.imread(path) as r:
        img = r.raw_image_visible.astype(np.float64)
        cols = r.raw_colors_visible.copy()
        black = float(np.mean(r.black_level_per_channel))
        white = float(r.white_level)
        xyz_cam = np.array(r.rgb_xyz_matrix[:3])  # XYZ -> camera RGB (dcraw cam_xyz)
    return img, cols, black, white, np.linalg.inv(xyz_cam)


def channels(path, roi):
    """Mean camera R, G, B (black-subtracted) and the brightest channel's 99th
    percentile as a fraction of the usable range, inside roi = (y0, y1, x0, x1).
    (Metering on green alone overexposed red and blue patches.)"""
    img, cols, black, white, cam_xyz = load(path)
    y0, y1, x0, x1 = roi
    img, cols = img[y0:y1, x0:x1] - black, cols[y0:y1, x0:x1]
    r = img[cols == 0].mean()
    g = np.concatenate([img[cols == 1], img[cols == 3]])
    b = img[cols == 2].mean()
    p99 = max(np.percentile(img[cols == c], 99) for c in (0, 1, 2, 3))
    return {"R": r, "G": g.mean(), "B": b, "g_p99": float(p99) / (white - black)}


def to_xyz(rgb, path):
    """Camera RGB -> XYZ with the camera's matrix (approximate; used for
    luminance only, relative between patches)."""
    *_, cam_xyz = load(path)
    return cam_xyz @ np.array([rgb["R"], rgb["G"], rgb["B"]])


def find_screen(path):
    """Bounding box (y0, y1, x0, x1) of the bright screen area in a white-patch
    shot, at raw (Bayer) resolution."""
    img, cols, black, white, _ = load(path)
    g = np.where((cols == 1) | (cols == 3), img - black, 0.0)
    # Work on 8x8 blocks: fast and plenty for a bounding box.
    h, w = (g.shape[0] // 8) * 8, (g.shape[1] // 8) * 8
    blocks = g[:h, :w].reshape(h // 8, 8, w // 8, 8).mean(axis=(1, 3))
    mask = blocks > 0.5 * np.percentile(blocks, 99.5)
    # Other bright things in the room are separate blobs: keep the largest.
    label = np.zeros(mask.shape, dtype=np.int32)
    best, best_size, n = 0, 0, 0
    for start in zip(*np.nonzero(mask)):
        if label[start]:
            continue
        n += 1
        label[start] = n
        stack, size = [start], 0
        while stack:
            y, x = stack.pop()
            size += 1
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not label[ny, nx]:
                    label[ny, nx] = n
                    stack.append((ny, nx))
        if size > best_size:
            best, best_size = n, size
    if not best:
        raise RuntimeError("no bright screen found in the frame")
    rows, colsx = np.where((label == best).any(axis=1))[0], np.where((label == best).any(axis=0))[0]
    return int(rows[0] * 8), int((rows[-1] + 1) * 8), int(colsx[0] * 8), int((colsx[-1] + 1) * 8)


def centre(box, fraction=0.3):
    """The middle `fraction` of a box, aligned to the 2x2 Bayer pattern."""
    y0, y1, x0, x1 = box
    cy, cx, hh, hw = (y0 + y1) // 2, (x0 + x1) // 2, int((y1 - y0) * fraction / 2), int((x1 - x0) * fraction / 2)
    even = lambda v: v - v % 2
    return even(cy - hh), even(cy + hh), even(cx - hw), even(cx + hw)


def preview(path, out, box=None, roi=None, scale=8):
    """Small PNG of the shot (camera white balance), with boxes drawn."""
    import struct
    import zlib
    with rawpy.imread(path) as r:
        rgb = r.postprocess(use_camera_wb=True, half_size=True, output_bps=8)
    small = rgb[::scale // 2, ::scale // 2].copy()
    for rect, colour in ((box, (255, 200, 0)), (roi, (0, 255, 0))):
        if rect:
            y0, y1, x0, x1 = (v // scale for v in rect)
            small[y0:y1, [x0, x1 - 1]] = colour
            small[[y0, y1 - 1], x0:x1] = colour
    h, w, _ = small.shape
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"".join(b"\x00" + small[y].tobytes() for y in range(h))
    with open(out, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b""))

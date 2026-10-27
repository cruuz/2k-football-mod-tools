"""b778-ee1/ee2: the alien's gray palette (authoring helper, OpenCV build dependency).

Kept out of the product module so the staged runtime's dependency audit sees
only the Studio's declared runtime packages. The build imports this helper
when it creates the gray arm, hand and neck textures.
"""
from __future__ import annotations


def gray_palette(palette_bgra: bytes, pixels: bytes, base_lab) -> bytes:
    """The Lightest skin palette mapped onto the alien gray: each entry keeps its lightness offset from the texture's
    median skin lightness (x0.9) around ``base_lab``'s L, and takes its colour (plus 20 % of its own)."""
    import numpy as np  # noqa: PLC0415
    import cv2  # noqa: PLC0415
    pal = np.frombuffer(palette_bgra, np.uint8).reshape(256, 4)
    rgb = pal[:, [2, 1, 0]][None].copy()
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)[0]
    used = np.bincount(np.frombuffer(pixels, np.uint8), minlength=256)
    order = np.argsort(lab[:, 0])
    cum = np.cumsum(used[order])
    med = lab[order[np.searchsorted(cum, cum[-1] / 2)], 0]
    out_lab = np.empty_like(lab)
    out_lab[:, 0] = base_lab[0] + (lab[:, 0] - med) * 0.9
    out_lab[:, 1] = base_lab[1] + (lab[:, 1] - np.median(lab[used > 0, 1])) * 0.2
    out_lab[:, 2] = base_lab[2] + (lab[:, 2] - np.median(lab[used > 0, 2])) * 0.2
    out_rgb = cv2.cvtColor(np.clip(out_lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0]
    out = np.empty((256, 4), np.uint8)
    out[:, 0], out[:, 1], out[:, 2], out[:, 3] = out_rgb[:, 2], out_rgb[:, 1], out_rgb[:, 0], pal[:, 3]
    return out.tobytes()

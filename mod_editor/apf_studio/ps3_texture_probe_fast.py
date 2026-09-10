"""Optional NumPy acceleration for the read-only bulk comparison, not writers.

Keeps the Xenos address/endian/channel equations of apf_inner and uses the
same Pillow BCn decoder as the importer. Synthetic randomized parity tests
compare every supported format/endian mode with the existing decoder.
Importing the product bundle importer never imports this research accelerator.
"""
from __future__ import annotations

from .ps3_texture_codec import _bc, _size
from .backend import ensure_tools_importable

ensure_tools_importable()
import apf_inner


def decode_xbox_base(metadata, source):
    try:
        import numpy as np
    except ImportError:
        return apf_inner.decode_txtr_base_rgba(metadata, source)
    m = metadata
    width, height, fmt = int(m["width"]), int(m["height"]), int(m["format"])
    _size(width, height)
    if m["dimension"] != 1 or m["stacked"] or fmt not in (2, 3, 4, 6, 10, 15, 18, 19, 20):
        return apf_inner.decode_txtr_base_rgba(metadata, source)
    block = 4 if fmt in (18, 19, 20) else 1
    unit = {2: 1, 3: 2, 4: 2, 6: 4, 10: 2, 15: 2, 18: 8, 19: 16, 20: 16}[fmt]
    wb, hb = (width + block - 1) // block, (height + block - 1) // block
    pitch = (int(m["pitch_pixels"]) + block - 1) // block
    if pitch < wb:
        raise apf_inner.FormatError("Texture pitch is narrower than width")
    src = np.frombuffer(source, dtype=np.uint8)
    if m["tiled"]:
        pitch = (pitch + 31) & ~31
        if len(source) < pitch * ((hb + 31) & ~31) * unit:
            raise apf_inner.FormatError("Truncated tiled texture")
        y, x = np.indices((hb, wb), dtype=np.int64)
        outer = ((y >> 5) * (pitch >> 5) + (x >> 5)) << 6
        inner = (((y >> 1) & 7) << 3) | (x & 7)
        address = (outer | inner) << (unit.bit_length() - 1)
        bank, pipe = (y >> 4) & 1, ((x >> 3) & 3) ^ (((y >> 3) & 1) << 1)
        offsets = (((y & 1) << 4) | (pipe << 6) | (bank << 11) | (address & 15)
                   | (((address >> 4) & 1) << 5) | (((address >> 5) & 7) << 8) | ((address >> 8) << 12))
        indices = offsets.ravel()[:, None] + np.arange(unit)
        if indices.max() >= len(source):
            raise apf_inner.FormatError("Tiled address exceeds source")
        linear = src[indices].reshape(-1)
    else:
        need = pitch * hb * unit
        if len(src) < need:
            raise apf_inner.FormatError("Truncated linear texture")
        linear = src[:need].reshape(hb, pitch, unit)[:, :wb, :].copy().reshape(-1)
    endian = int(m["endianness"])
    if endian in (1, 2):
        n = 2 if endian == 1 else 4
        if len(linear) % n:
            raise apf_inner.FormatError("Texture endian unit is misaligned")
        linear = linear.reshape(-1, n)[:, ::-1].copy().reshape(-1)
    elif endian == 3:
        if len(linear) % 4:
            raise apf_inner.FormatError("Texture endian unit is misaligned")
        linear = linear.reshape(-1, 4)[:, [2, 3, 0, 1]].copy().reshape(-1)
    elif endian != 0:
        raise apf_inner.FormatError("Unsupported endian mode")
    if block == 4:
        rgba = np.frombuffer(_bc(linear.tobytes(), width, height, {18: "DXT1", 19: "DXT3", 20: "DXT5"}[fmt]).tobytes(), dtype=np.uint8).reshape(-1, 4)
    elif fmt == 6:
        rgba = linear.reshape(-1, 4)
    else:
        rgba = np.zeros((width * height, 4), dtype=np.uint8)
        rgba[:, 3] = 255
        if fmt == 2:
            rgba[:, :3] = linear[:, None]
        elif fmt == 10:
            rgba[:, :2] = linear.reshape(-1, 2)
        else:
            words = np.frombuffer(linear.tobytes(), dtype="<u2")
            if fmt == 15:
                for channel in range(4):
                    rgba[:, channel] = ((words >> (channel * 4)) & 15) * 17
            else:
                r = (words >> (11 if fmt == 4 else 10)) & 31
                g = (words >> 5) & (63 if fmt == 4 else 31)
                b = words & 31
                rgba[:, 0], rgba[:, 2] = (r << 3) | (r >> 2), (b << 3) | (b >> 2)
                rgba[:, 1] = (g << 2) | (g >> 4) if fmt == 4 else (g << 3) | (g >> 2)
                if fmt == 3:
                    rgba[:, 3] = (words >> 15) * 255
    out = np.empty_like(rgba)
    for channel, selector in enumerate(m["swizzle_components"]):
        out[:, channel] = rgba[:, selector] if selector < 4 else 255 if selector == 5 else 0
    return width, height, out.tobytes()

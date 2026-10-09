"""Own-art helmet decals calibrated in native top-left atlas coordinates.

Only numeric placement measurements come from the PS2 orientation oracle.
The author accepts our own atlas and mark. It never loads an oracle image.
Raw shell C V grows upwards on the upper island and downwards on the lower.
For Seattle, both beaks belong at small U, toward the helmet's front.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage
from dataclasses import asdict
import hashlib


SEA_PLACEMENT = {
    "upper": {"centre": [103.0, 73.3], "matrix": [[106.0, 9.9], [-21.8, 43.7]], "flip": [-1, -1]},
    "lower": {"centre": [103.0, 182.7], "matrix": [[106.0, -9.9], [21.8, 43.7]], "flip": [-1, 1]},
}


def sample_mark(logo: Image.Image, shape: tuple, placement: dict) -> np.ndarray:
    """Sample straight-alpha artwork through a measured affine transform."""
    box = logo.getbbox()
    if box is None:
        raise ValueError("empty helmet mark")
    a = np.asarray(logo.crop(box).convert("RGBA"), dtype=np.float32) / 255.0
    # Premultiply before interpolation so transparent RGB cannot produce halos.
    a[..., :3] *= a[..., 3:4]
    h, w = shape
    if h != w or h % 256:
        raise ValueError("helmet canvas must be a multiple of 256 square")
    matrix = np.asarray(placement["matrix"], dtype=float)
    if matrix.shape != (2, 2) or np.linalg.det(matrix) <= 0:
        raise ValueError("invalid helmet decal transform")
    yy, xx = np.indices(shape, dtype=float)
    xy = np.stack([(xx + .5) * 256 / w, (yy + .5) * 256 / h], -1)
    uv = (xy - placement["centre"]) @ np.linalg.inv(matrix).T
    flip = placement["flip"]
    if flip not in ([1, 1], [-1, 1], [1, -1], [-1, -1]):
        raise ValueError("invalid decal orientation")
    u, v = .5 + uv[..., 0] * flip[0], .5 + uv[..., 1] * flip[1]
    result = np.stack([ndimage.map_coordinates(a[..., k], [v * (a.shape[0]-1), u * (a.shape[1]-1)],
                       order=1, mode="constant", cval=0) for k in range(4)], -1)
    result[..., :3] /= np.maximum(result[..., 3:4], 1e-8)
    return result


def apply_decal(canvas: np.ndarray, logo: Image.Image, recipe: dict, shell: np.ndarray,
                family: str = "helmet02") -> tuple:
    """Erase the old mark, preserve protected fittings, paint our mark, retain alpha."""
    import nfl2k5_team_2026_art as art
    out = canvas.copy()
    h, w = canvas.shape[:2]
    factor = h // 256
    base = art.downscale(canvas) if factor == art.MASTER else canvas
    mask, _ = art._old_decals(base, {k: tuple(v) for k, v in recipe["erase_boxes"].items()})
    erase = ndimage.zoom(mask.astype(float), factor, order=0) > .5
    protected = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in recipe.get("protect", []):
        protected[y0*factor:y1*factor, x0*factor:x1*factor] = True
    erase &= ~protected
    luma = out[..., :3] @ art.LUMA
    scale = np.clip(luma / max(float(shell @ art.LUMA), 1e-3), 0, 2.5)
    shellness = np.exp(-(np.linalg.norm(out[..., :3]-shell*scale[..., None], axis=2)/.08)**2)
    out = art._inpaint_weighted(out, erase.astype(float), shellness, 2.0*factor)
    scope = erase.copy()
    crown = recipe.get("clear_crown")
    if crown and family in crown["families"]:
        x0, y0, x1, y1 = crown["box"]
        region = np.zeros((h, w), bool)
        region[y0*factor:y1*factor, x0*factor:x1*factor] = True
        region &= ~protected
        # The shell A primary retained the old solid green centre stripe.
        # Use our navy albedo, while keeping its reflection channel exact.
        out[region, :3] = shell
        scope |= region
    for placement in recipe["placements"].values():
        mark = sample_mark(logo, (h, w), placement)
        alpha = mark[..., 3:4] * (~protected)[..., None]
        out[..., :3] = out[..., :3]*(1-alpha) + mark[..., :3]*alpha
        scope |= alpha[..., 0] > 0
    out[..., 3] = canvas[..., 3]
    out[protected] = canvas[protected]
    return out, scope


def compile_existing_palette(span: bytes, native: np.ndarray, scope: np.ndarray,
                             maximum_colors_per_alpha: int | None = None) -> tuple:
    """Compile a decal into its current P8 allocation with the existing palette.

    Indices outside the scope, palette bytes, descriptors and each stored mip's
    reflection alpha outside the decal stay exact. This avoids asking a nearly
    full protected palette for additional colours. Within the decal, palette
    selection allows at most two alpha steps, so the old 254/255 colour split
    cannot speckle a newly moved white or chrome mark. The fixed-span writer proves
    the in-place decoder guard and independently decodes its output.
    """
    from nfl_txtr import (parse_chunks, decode_chunk, parse_texture, unswizzle_2d, swizzle_2d,
                          encode_rgba_png)
    from nfl_vc_lz_fill import rebuild_fixed_span_filled
    from nfl_live_helmet_txtr_png_import import decode_levels, MIP_DIMENSIONS, INDEX_CHAIN_BYTES
    import nfl_tset_png_import as palettes
    chunks = parse_chunks(span)
    if len(chunks) != 1 or chunks[0].kind != "TXTR":
        raise ValueError("helmet template must contain one TXTR")
    c = chunks[0]
    decoded, _ = decode_chunk(span, c)
    tex = parse_texture(decoded, c)
    if tex.format_name != "P8" or tex.width != 256 or tex.height != 256 or tex.mip_levels != 6:
        raise ValueError("helmet template is outside the six-mip P8 contract")
    levels = decode_levels(decoded)
    base = np.frombuffer(levels[0].rgba, np.uint8).reshape(256, 256, 4)
    if native.shape != base.shape or scope.shape != (256, 256) or not np.array_equal(native[~scope], base[~scope]):
        raise ValueError("authored helmet changed pixels outside its scope")
    palette = np.array(palettes.parse_palette(decoded, 128+INDEX_CHAIN_BYTES), dtype=np.int32)
    cur, changed, offset, chain, rows, result = native.copy(), scope.copy(), 128, [], [], []
    for (w, h), stored_level in zip(MIP_DIMENSIONS, levels):
        stored = np.frombuffer(stored_level.rgba, np.uint8).reshape(h, w, 4)
        original = np.frombuffer(unswizzle_2d(decoded[offset:offset+w*h], w, h, 1), np.uint8).reshape(h, w).copy()
        offset += w*h
        cur[..., 3] = stored[..., 3]
        for alpha in np.unique(cur[..., 3][changed]):
            candidates = np.flatnonzero(np.abs(palette[:, 3]-int(alpha)) <= 2)
            if not len(candidates):
                raise ValueError("stored alpha is absent from its palette")
            if maximum_colors_per_alpha is not None and len(candidates) > maximum_colors_per_alpha:
                if maximum_colors_per_alpha < 4:
                    raise ValueError("palette simplification must retain at least four tones")
                wanted = cur[..., :3][changed & (cur[..., 3] == alpha)]
                unique, counts = np.unique(wanted, axis=0, return_counts=True)
                distance = ((unique.astype(np.int32)[:, None, :]-palette[candidates, :3])**2).sum(axis=2)
                hits = np.bincount(candidates[distance.argmin(axis=1)], weights=counts, minlength=256)
                ranked = sorted(candidates, key=lambda i: (-float(hits[i]), int(i)))
                tones = palette[candidates, :3].sum(axis=1)
                extremes = [candidates[tones.argmin()], candidates[tones.argmax()]]
                candidates = np.array(sorted(set(extremes + ranked[:maximum_colors_per_alpha-2])))
            points = np.argwhere(changed & (cur[..., 3] == alpha))
            colors = cur[points[:, 0], points[:, 1], :3]
            unique, inverse = np.unique(colors, axis=0, return_inverse=True)
            distance = ((unique.astype(np.int32)[:, None, :]-palette[candidates, :3])**2).sum(axis=2)
            chosen = candidates[distance.argmin(axis=1)][inverse]
            original[points[:, 0], points[:, 1]] = chosen
        quantized = palette[original].astype(np.uint8)
        alpha_delta = np.abs(quantized[..., 3].astype(int)-stored[..., 3].astype(int))
        if not np.array_equal(quantized[~changed], stored[~changed]) or alpha_delta.max() > 2:
            raise ValueError("palette compilation changed protected pixels or exceeded its alpha bound")
        chain.append(swizzle_2d(original.tobytes(), w, h, 1))
        result.append(quantized)
        rows.append({"width": w, "scope_texels": int(changed.sum()), "outside_scope_rgba_identical": True,
                     "alpha_identical": bool(alpha_delta.max() == 0), "maximum_alpha_delta": int(alpha_delta.max())})
        if w > 8:
            cur = ((quantized.astype(np.int32).reshape(h//2, 2, w//2, 2, 4).sum(axis=(1, 3))+2)//4).astype(np.uint8)
            changed = changed.reshape(h//2, 2, w//2, 2).any(axis=(1, 3))
    rebuilt_decoded = decoded[:128] + b"".join(chain) + decoded[128+INDEX_CHAIN_BYTES:]
    fixed, receipt = rebuild_fixed_span_filled(span, rebuilt_decoded, encoder="auto")
    actual, _ = decode_chunk(fixed, parse_chunks(fixed)[0])
    if actual != rebuilt_decoded or len(fixed) != len(span):
        raise ValueError("compiled helmet failed native round trip")
    previews = [encode_rgba_png(w, h, a.tobytes()) for (w, h), a in zip(MIP_DIMENSIONS, result)]
    return fixed, previews, {"writer": asdict(receipt), "mips": rows, "palette_identical": True,
                            "system_descriptor_identical": True,
                            "maximum_scope_colors_per_alpha": maximum_colors_per_alpha,
                            "decoded_sha256": hashlib.sha256(actual).hexdigest()}

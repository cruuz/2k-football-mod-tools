#!/usr/bin/env python3
"""Render the exact installed star table with Pillow, without game/GPU execution."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_player_star as ps


def star_passes(star: str = ps.DEFAULT_STAR):
    """(outer tip, outer notch, inner tip, inner notch, diffuse ARGB, height) of each drawn pass of the table."""
    va, _, code = next(row for row in ps.CAVES if row[0] <= ps.SYMBOLS['star_passes'] < row[0]+len(row[2]))
    code = ps._star_code(va, code, star)
    start, end = ps.SYMBOLS['star_passes']-va, ps.SYMBOLS['star_passes_end']-va
    rows = [struct.unpack_from('<4fIf', code, at) for at in range(start, end, 24)]
    return [row for row in rows if row[4] >> 24], code


def render(output: Path) -> None:
    import math
    from PIL import Image, ImageDraw, PngImagePlugin

    # Draw the actual strips the runtime submits: eleven (outer, inner) pairs on the ten rays of each pass,
    # composited with the pass's diffuse alpha. Supersampling smooths only the exported preview.
    supersample = 4
    canvas = Image.new('RGBA', (480*supersample, 360*supersample), '#547b45')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 235*supersample, 480*supersample, 248*supersample), fill='#e6e7d7')
    passes, code = star_passes()
    for ot, on, it, inn, argb, _height in passes:
        layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        color = ((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, argb >> 24)
        vertices = []
        for k in range(11):
            for r in ((ot, it) if k % 2 == 0 else (on, inn)):
                a = k*math.pi/5
                vertices.append(((240+r*math.sin(a)*1.15)*supersample, (179-r*math.cos(a)*1.15)*supersample))
        for i in range(len(vertices)-2):
            d.polygon(vertices[i:i+3], fill=color)
        canvas = Image.alpha_composite(canvas, layer)
    canvas = canvas.convert('RGB').resize((480, 360), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 12), 'White outline star over a thin dark under-edge / exact pass table', fill='white')
    draw.text((14, 339), 'Shape preview only; in-game appearance unwitnessed', fill='white')
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('geometry_sha256', hashlib.sha256(code).hexdigest())
    metadata.add_text('source', 'mod_editor/core/nfl2k5_player_star.py CAVES / tools/player_star/runtime.S')
    metadata.add_text('proof_boundary', 'Orthographic intended shape; no GPU or in-game witness.')
    canvas.save(output, pnginfo=metadata)
    print(f'Wrote {output}; exact table SHA-256 {hashlib.sha256(code).hexdigest()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/mod_editor/nfl2k5_player_star_filled.png')
    render(parser.parse_args().output)

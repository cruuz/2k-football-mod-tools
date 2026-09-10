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


def render(output: Path) -> None:
    from PIL import Image, ImageDraw, PngImagePlugin

    table_va = ps.SYMBOLS['star_inset']
    va, _, code = next(row for row in ps.CAVES if row[0] <= table_va < row[0]+len(row[2]))
    inset = struct.unpack_from('<f', code, table_va-va)[0]
    values = struct.unpack_from('<20f', code, ps.SYMBOLS['star_points']-va)
    points = list(zip(values[::2], values[1::2]))
    # Draw the actual strip triangles, including its repeated centre vertices.
    # Supersampling smooths only the exported preview; no game texture is made.
    supersample = 4
    canvas = Image.new('RGB', (480*supersample, 360*supersample), '#547b45')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 235*supersample, 480*supersample, 248*supersample), fill='#e6e7d7')
    for scale, color in ((1.125, '#101010'), (1.0, '#ffffff')):
        vertices = []
        for x, z in points + points[:1]:
            for factor in (1.0, inset):
                vertices.append(((240+x*scale*factor*1.15)*supersample,
                                 (179+z*scale*factor*1.15)*supersample))
        for i in range(len(vertices)-2):
            draw.polygon(vertices[i:i+3], fill=color)
    canvas = canvas.resize((480, 360), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 12), 'Filled player star / exact vertex table', fill='white')
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

#!/usr/bin/env python3
"""Offline, bounded native scorebug projection; no emulator or GPU rendering.

This research harness shares the standalone Unicorn fixture. It is not imported
by the application. Text glyphs, depth testing and GPU fences remain unmodeled.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from test_nfl2k5_scorebug_runtime import Machine
from mod_editor.core import nfl2k5_scorebug_ingame as r, nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_scorebug_resources as art, nfl2k5_widescreen as wide
from nfl_normshort3_positions import decode_position


def native_geometry(payload, decoded, *, root=r.ROOT, widescreen=False, mode=0, slide=1.0):
    """Run the actual scene relocator, setup, frame driver and camera activation.

    Only startup animation selection, font resource creation, per-frame game
    predicates and the GPU render-list boundary are replaced. Score rotation is
    disabled for a settled-score sample. No replacement writes the root matrix.
    """
    if widescreen:
        payload = wide.apply(payload)[0]
    m = Machine(runtime.apply(payload)[0])
    m.uc.mem_write(r.layout.sbpos.X_SLOT, struct.pack('<2f', *root))
    body = m.alloc(len(decoded)); m.uc.mem_write(body, decoded)
    # No startup animation controller or font renderer in this geometry fixture.
    m.uc.mem_write(0x2f010, bytes.fromhex('c20400'))
    m.run(0x2f140, ecx=body + 256, limit=500000)
    m.run(0x43e30, (0,), ecx=body, edx=0, limit=500000)
    m.uc.mem_write(0xef850, bytes.fromhex('b801000000c3'))
    m.put(0xa6a9d0, 720); m.put(0xa6a9d4, 480)
    m.run(0xfccd0, limit=500000)
    instance = m.get(0xa9552c)
    if instance != body + 352:
        raise ValueError('native scene instance identity changed')
    # The frame driver still executes all native transforms and root operands.
    # The fixture visibility callback in Machine replaces FC9C0 only.
    va, original = runtime.HOOKS['update']; m.uc.mem_write(va, original)
    m.put(0xa95870, mode)
    for i in range(2):
        m.put(0xa9597c + i * 0x38, 0)
    for i in range(6):
        record = r.layout.ELEMENT_RECORDS + i * 0x70
        m.put(record + 0x58, int(i < 2))
        m.put(record + 0x38, 1)
        m.float(record + 0x3c, 30 * slide if i == 0 else 30)
    m.run(0xfce70, (0,), limit=500000)
    frame_instructions = len(m.visits)
    matrices = m.get(instance + 0x14)
    m.run(0x22c00, (body + r.layout.SHAPE, matrices), limit=10000)
    m.uc.mem_write(wide.RENDER_LIST_VA, bytes.fromhex('31c0c3'))
    m.run(0x2ac80, ecx=0xa95530, limit=10000)
    def floats(va, count):
        return struct.unpack('<' + 'f' * count, m.uc.mem_read(va, count * 4))
    camera = floats(wide.ACTIVE_CAMERA_VA + 0xf0, 16)
    def project(p):
        p = (*p, 1)
        result = [sum(p[j] * camera[j * 4 + i] for j in range(4)) for i in range(4)]
        # Explicit active-area crop, not an assumption of a 640-pixel framebuffer.
        return [result[0] / result[3] - r.HUD_INSET[0], result[1] / result[3]]
    scale = floats(body + r.layout.SHAPE + 0x1c, 1)[0]
    bias = floats(body + r.layout.SHAPE + 0x10, 3)
    positions = []
    for v in range(r.layout.VCOUNT):
        q = struct.unpack_from('<3h', decoded, r.layout.S0 + v * 6)
        point = (*decode_position(q, scale, bias), 1)
        index = struct.unpack_from('<h', decoded, r.layout.S1 + v * 10 + 8)[0] // 3
        palette = floats(0xafa710 + index * 48, 12)
        world = [sum(point[j] * palette[i * 4 + j] for j in range(4)) for i in range(3)]
        positions.append(project(world))
    anchors = {}
    for name in r.ANCHORS:
        out = m.alloc(16)
        m.run(0xfb640, ecx=out, edx=0x4f6950, eax=matrices + r.layout.T[name] * 64)
        anchors[name] = project(floats(out, 3))
    def bounds(indices):
        points = [positions[i] for i in indices]
        return [min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points)]
    return dict(schema='nfl2k5_scorebug_native_projection/v1', experimental=True, runtime_witnessed=False,
                coordinate_system='720x480 framebuffer, crop x=40..680 to a 640x480 comparison',
                root=list(root), native_root_matrix=list(floats(matrices, 16)),
                native_camera=list(camera), hud_viewport=list(floats(wide.ACTIVE_CAMERA_VA + 0x250, 8)),
                positions=positions, anchors=anchors,
                frame=bounds(range(96, 166) if mode == 0 else range(166, 230)),
                clock=bounds(range(48, 64)), down=bounds(range(64, 80)),
                frame_instructions=frame_instructions, widescreen=widescreen, mode=mode,
                text_scale_x=27 / 32 if widescreen else 1,
                scene_sha256=r.digest(decoded),
                limitations=['glyphs approximated', 'no depth test or GPU consumption',
                             'settled score rotation', 'not a reproduction of the supplied clipped screenshot'])


def v7_baseline(spans):
    """Reconstruct and pin the shipped v7 inputs, for comparison only."""
    from PIL import ImageDraw
    mesh = r.mesh(r.pinned(spans['score_bug'], art.RESOURCES['score_bug']), baseline_v7=True)
    decoded = bytearray(r.serialize(mesh))
    for v, pos in enumerate(mesh.pos):
        q = [round((c - o) / 420 * 32767) for c, o in zip(pos, (-20, 100, -29.5))]
        struct.pack_into('<3h', decoded, r.layout.S0 + v * 6, *q)
    scene, _ = r.layout.refit(spans['score_bug'], bytes(decoded))
    atlas = r.atlas(spans); draw = ImageDraw.Draw(atlas)
    draw.rectangle((0, 0, 63, 15), fill=(0, 0, 0, 0))
    draw.rounded_rectangle((0, 0, 63, 15), 2, fill=(19,20,25,255), outline=(122,124,132,255))
    draw.line((3,1,60,1), fill=(190,190,196,255))
    for x in range(64):
        value = round(75 * (1-x/63) + 17*x/63)
        draw.line((x,16,x,31), fill=(value,value,value+5,255))
    for x in (48,53,58):
        draw.line((x,30,x+2,30), fill=(230,230,232,255))
    texture, _ = r.encode_atlas(spans['score_buga'], atlas)
    if r.digest(scene) != '475efc3d7aa03535f8f807dbdca0baaa32928faf2ade9116551c7bb57039c732':
        raise ValueError('v7 scene baseline drifted')
    if r.digest(texture) != '72aee2c09b471c6f07e3658c00ef6f204021f3f6065cd96344c7c72d30df9947':
        raise ValueError('v7 atlas baseline drifted')
    return bytes(decoded), texture


def main(argv=None):
    from PIL import Image
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True, type=Path)
    parser.add_argument('--xbe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with args.pack.open('rb') as stream:
        view = art.PackView.from_fd(stream.fileno(), 0, args.pack.stat().st_size)
        spans = {n: view[v['pack_offset']:v['pack_offset']+v['span_size']] for n,v in art.RESOURCES.items()}
    before, old_atlas = v7_baseline(spans)
    after = r.decode(r.apply(spans['score_bug'], 'score_bug')[0])[1]
    new_atlas = r.apply(spans['score_buga'], 'score_buga', inputs=spans)[0]
    receipts = {}
    for name, decoded, atlas, root, widescreen in (
        ('before_v7_640x480', before, old_atlas, (320,424), False),
        ('after_v8_640x480', after, new_atlas, r.ROOT, False),
        ('after_v8_wide_640x480', after, new_atlas, r.ROOT, True)):
        geometry = native_geometry(args.xbe.read_bytes(), decoded, root=root, widescreen=widescreen)
        c, d, _ = r.decode(atlas); texture = r.tx.parse_texture(d, c)
        image = Image.frombytes('RGBA', (64,64), r.tx.texture_to_rgba(d,c,texture))
        mesh = r.layout.Mesh(r.pinned(spans['score_bug'], art.RESOURCES['score_bug']))
        mesh.buf = bytearray(decoded)
        mesh.uv = [tuple(n / (32768 if n < 0 else 32767) for n in struct.unpack_from('<2h',decoded,r.layout.S1+i*10+4))
                   for i in range(r.layout.VCOUNT)]
        r.layout.preview_reference(mesh, image, args.output / (name + '.png'), scale=1,
                                   samples={'away_city':'TB','home_city':'NE'}, projection=geometry)
        receipts[name] = {k:v for k,v in geometry.items() if k not in ('positions','anchors')}
        if name == 'after_v8_640x480':
            r.layout.preview_reference(mesh, image, args.output / 'after_v8_widest_640x480.png', scale=1,
                                       widest=True, projection=geometry)
            receipts['after_v8_widest_640x480'] = {**receipts[name], 'widest_sample': True}
    (args.output / 'projection.json').write_text(json.dumps(receipts,indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:{n:v[n] for n in ('frame','clock','down')} for k,v in receipts.items()},indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

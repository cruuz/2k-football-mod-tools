#!/usr/bin/env python3
"""PROVED OFFLINE: bounded native placement projection and witness measurement.

Runs only CPU code in the existing StaticMachine. No emulator/disc build, GPU,
whole archive read, scene rewrite, or synthetic screenshot is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_playcall_layout as pc
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_widescreen as wide
from nfl2k5_scorebug_projection import StaticMachine
from nfl2k5_playbook_position_recode import OuterImage

DEFAULT_XBE = ROOT / 'extracted/ESPN NFL 2K5 (USA)/default.xbe'
DEFAULT_PACK = DEFAULT_XBE.parent / 'vc_53450030'
PHASES = (0., 1/12, 1/6, 1/3, .5, 1.)
SCENE_PINS = {83:'c5328ee5baa02b8a3170ae20170cf74088c51cd325903c1f3e60f217d9f1db59',
              84:'862ffa7f58030004da761bd2d04cbacb07f889b3d1c098fa6e2f0365ac4262f3',
              86:'1e3b984af5838d11ee67a1a5b28e4294a97d901f84afcea87e00ed66ec298c79'}


def word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scene_sources(pack):
    with OuterImage(pack) as archive:
        data = archive.read_entry(346)
    chunks = scene.tx.parse_chunks(data)
    return [(index, chunks[index], scene.tx.decode_chunk(data, chunks[index])[0])
            for index in (83, 84, 86)]


def project(matrix, p):
    p = (*p, 1)
    q = [sum(p[j] * matrix[j*4+i] for j in range(4)) for i in range(4)]
    return [q[0]/q[3], q[1]/q[3]]


def native_proof(payload, sources):
    assert pc.valid(payload, applied=False), 'placement source pins differ'
    m = StaticMachine(payload)
    m.record = False
    try:
        m.put(0xa6a9d0, 720); m.put(0xa6a9d4, 480)
        # Only GPU submission is stubbed. Menu, card, viewport constructors,
        # scene relocation, node initialization and animation all run natively.
        m.uc.mem_write(wide.RENDER_LIST_VA, bytes.fromhex('31c0c3'))
        m.run(0x69030)
        m.run(0x2ac80, ecx=0xa83f20)
        menu_matrix = m.floats(wide.ACTIVE_CAMERA_VA + 0xf0, 16)
        menu_target = m.floats(0xa83f20+0x250, 8)
        loaded, metadata = [], []
        for (glob, count, root_y), (index, chunk, decoded) in zip(pc.SCENES, sources):
            assert hashlib.sha256(decoded).hexdigest() == SCENE_PINS[index], 'retail SCNE pin differs'
            base = m.alloc(len(decoded)); m.uc.mem_write(base, decoded)
            desc = base + 256
            m.run(0x2f140, ecx=desc, limit=500000)
            assert m.get(desc+0x24) == count
            m.put(glob, desc)
            nodes = []
            for i in range(count):
                node = m.get(desc+0x28) + i*0x60
                name = m.read_string(m.get(node))
                # Same AA440 call used directly for coach nodes and through
                # ABED0 for offense/defense nodes in ABF60, BEFORE our hook.
                m.run(0xaa440, eax=m.get(node), edi=desc)
                assert m.floats(node+0x54, 1) == [root_y]
                shape = m.get(node+8)
                n = struct.unpack('<H', m.uc.mem_read(shape+0x50, 2))[0]
                nodes.append((node, name, n))
            loaded.append((desc, nodes))
            anchors = {}
            for node, name, count in nodes:
                transforms = m.get(m.get(node+8)+0x64)
                anchors[name] = [m.read_string(m.get(transforms+i*0x70+0x60)) for i in range(count)]
            metadata.append(dict(chunk=index, decoded_sha256=hashlib.sha256(decoded).hexdigest(),
                                 decoded_size=len(decoded), nodes=[n for _, n, _ in nodes], anchors=anchors))
        def sample():
            rows = []
            for desc, nodes in loaded:
                for phase in PHASES:
                    m.run(0x2f010, (word(phase),), ecx=desc, limit=500000)
                    for node, name, count in nodes:
                        palette = m.get(node+0x14)
                        for i in range(count):
                            mat = m.floats(palette+i*64, 16)
                            rows.append((name, phase, i, mat, project(menu_matrix, mat[12:15])))
            return rows
        before = sample()
        cave = 0x5100000
        m.uc.mem_map(cave, 4096); m.uc.mem_write(cave, pc.code_for(cave))
        args = (0x4f0e10, 0x4f0e00, 0x4f0df0)
        m.run(0x2bc60, ecx=0xb719d0)
        m.run(cave, args, ecx=0xb719d0, edx=0x4f0e20)
        after = sample()
        max_error = 0.
        for a, b in zip(before, after):
            assert a[:3] == b[:3]
            for i, (x, y) in enumerate(zip(a[3], b[3])):
                error = abs(y-x-(-pc.SHIFT if i == 13 else 0))
                assert error < .0001, (a[:3], i, x, y)
                max_error = max(error, max_error)
            assert abs(b[4][1]-a[4][1]+pc.SHIFT) < .0001
            assert abs(b[4][0]-a[4][0]) < .0001
        m.run(cave, args, ecx=0xb719d0, edx=0x4f0e20)
        assert after == sample(), 'reinitializing must not accumulate the shift'
        # Separate MRKS camera projection, same view setter as both initializers.
        cameras = []
        for cam, pos, args in ((0xb38c50, 0x4e9660, (0x4e9650,0x4e9640,0x4e9630)),
                               (0xb719d0, 0x4f0e20, (0x4f0e10,0x4f0e00,0x4f0df0))):
            matrices = []
            m.run(0x2bc60, ecx=cam)
            for value in (0., -pc.SHIFT):
                m.float(pos+4, value)
                m.run(0x2ba10, args, ecx=cam, edx=pos)
                m.run(0x2ac80, ecx=cam)
                matrices.append(m.floats(wide.ACTIVE_CAMERA_VA+0xf0, 16))
            for i, (a,b) in enumerate(zip(*matrices)):
                assert abs(b-a-(-pc.SHIFT if i == 13 else 0)) < .0001
            cameras.append(dict(camera=hex(cam), before=matrices[0], after=matrices[1]))
        # Execute the native rectangle mapping, including its inset constructor.
        m.uc.mem_write(0x627c0, bytes.fromhex('31c0c3'))  # explicit normal FOV fixture
        viewports = []
        for mode in (0, 1, 2):
            targets = []
            for shifted in (False, True):
                vals = m.floats(0xa84ad0+mode*16, 4)
                if shifted and mode:
                    vals[0] -= pc.SHIFT/448; vals[2] -= pc.SHIFT/448
                y0, x0, y1, x1 = vals
                # 5F140..5F170's output record consumed by 5F460:
                for at, val in zip(range(0xa839e8,0xa839fc,4), (y0,x0,x1-x0,y1-y0,1.)):
                    m.float(at,val)
                m.run(0x5f460, ecx=5, limit=500000)
                targets.append(m.floats(0xa82940+0x250, 8))
            expect = -pc.SHIFT if mode else 0
            for i,(a,b) in enumerate(zip(*targets)):
                assert abs(b-a-(expect if i in (1,5) else 0)) < .0001, (mode,i,a,b)
            viewports.append(dict(mode=mode, before=targets[0], after=targets[1]))
        return dict(classification='PROVED OFFLINE', runtime_witnessed=False,
                    xbe_sha256=hashlib.sha256(payload).hexdigest(), shift=pc.SHIFT,
                    scene_sources=metadata, phases=PHASES, matrix_samples=len(before),
                    max_matrix_error=max_error, menu_camera=menu_matrix, menu_target=menu_target,
                    cameras=cameras, viewports=viewports, initializer_bytes=len(pc.code_for(cave)),
                    limits='CPU projection; GPU raster, live state selection and transitions require candidate G')
    finally:
        m.close()


def measurements(research):
    """Pixel detectors, with explicit masks, thresholds and JPEG uncertainty.

    The black-background detector measures VISIBLE UI only. No algorithm can
    recover pixels hidden by the scorebug in an existing screenshot. The native
    proof independently checks that hidden geometry/anchor palettes move too.
    Kick-return has live field behind it, so use its yellow selector and the
    neutral gray card's unoccluded side strips instead of calling field pixels UI.
    """
    import numpy as np
    from PIL import Image
    specs = [('main/witness/kr_candE/ari.jpg', 'offense formation'),
             ('main/witness/kr_candE/det.jpg', 'three plays'),
             ('hx/lab-F-20260929-091218/s37-hou/attempt-01/screens/09-last-play.png', 'LAST PLAY'),
             ('hx/lab-20260929-072352/ari-kickoff/attempt-02/screens/toss-0131.3s.jpg', 'KICK RETURN / OFFENSE CHOSE')]
    rows = []
    for rel, name in specs:
        path = research / rel
        a = np.asarray(Image.open(path).convert('RGB')).astype(float)
        assert a.shape == (672,1280,3)
        # Expected band from the independently projected sprite body; locate
        # weak coverage and the first strong horizontal edge within +/-6 rows.
        edge = np.abs(a[1:,400:881]-a[:-1,400:881]).mean(axis=(1,2))
        weak = next(y for y in range(564,576) if edge[y-1] > 10)
        strong = next(y for y in range(weak,576) if edge[y-1] > 15)
        if name.startswith('KICK'):
            # A gray card separator precedes the bar here. Require chroma on
            # both team wings so that separator cannot be mistaken for the rim.
            wings = np.concatenate((a[:,400:425],a[:,850:875]),axis=1)
            chroma = (wings.max(2)-wings.min(2)).mean(1)
            weak = next(y for y in range(564,576) if chroma[y]>25)
            strong = next(y for y in range(weak,576) if chroma[y]>50)
            s = a[80:150,277:297]
            yellow = (s[:,:,0]>60)&(s[:,:,1]>60)&(s[:,:,1]-s[:,:,2]>25)&(abs(s[:,:,0]-s[:,:,1])<50)
            top = int(np.where(yellow)[0].min()+80)
            sides = np.concatenate((a[590:630,356:392],a[590:630,888:924]),axis=1)
            gray = (sides.max(2)-sides.min(2)<18)&(sides.mean(2)>25)
            bottom = int(np.where(gray.mean(1)>.5)[0].max()+590)
            sensitivity = None
        else:
            sensitivity = []
            for threshold in (16,24,32):
                mask = a.max(2)>threshold
                mask[:,:192] = False; mask[:,1088:] = False
                mask[24:80,900:1030] = False  # independent watermark
                mask[568:635,394:885] = False  # witnessed bar plus 1-2 px filtering fringe
                ys = np.where(mask)[0]
                sensitivity.append([threshold,int(ys.min()),int(ys.max())])
            _, top, bottom = sensitivity[1]
        rows.append(dict(classification='PROVED OFFLINE', source=str(path),
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest(), screen=name,
                         bar_top_weak=weak, bar_top_strong=strong,
                         visible_ui_top=top, visible_ui_bottom_inclusive=bottom,
                         top_headroom=top, usable_headroom_above_menu_clip=top-16*1.4,
                         black_background=not name.startswith('KICK'),
                         threshold_sensitivity=sensitivity,
                         projected_top=round(top-pc.SHIFT*1.4,4),
                         projected_bottom_exclusive=round(bottom+1-pc.SHIFT*1.4,4),
                         projected_bar_gap=round(weak-(bottom+1-pc.SHIFT*1.4),4)))
    spec,_ = sprite.load_layout()
    body = next(r for r in spec['static'] if r['name']=='body')
    tab = next(r for r in spec['fields'] if r['name']=='timeout_tab')
    bar_y = sprite.hud_box(body['box'])[1]*1.4
    tab_y = sprite.hud_box(tab['box'])[1]*1.4
    bottom = max(r['visible_ui_bottom_inclusive']+1 for r in rows)
    top = min(r['visible_ui_top'] for r in rows)
    return dict(classification='PROVED OFFLINE', frames=rows,
                method='visible pixels; black threshold 16/24/32 with scorebug/watermark masks; kick selector chroma and gray card side strips',
                limitation='occluded pixels are not measurable from these frames; JPEG edge uncertainty about 2 capture pixels',
                design=dict(classification='DESIGN', shift_game_units=pc.SHIFT, capture_pixels=pc.SHIFT*1.4,
                            scale='672/480 = 1.4; world preview uses a 448-high target inside that 480-high frame',
                            body_projected_top=bar_y, timeout_projected_top=tab_y,
                            normal_min_shift_for_4px_gap=(bottom-569+4)/1.4,
                            timeout_min_shift_for_1px_gap=(bottom-tab_y+1)/1.4,
                            max_shift_for_2px_menu_clip_margin=(top-16*1.4-2)/1.4,
                            selected_min_top=top-pc.SHIFT*1.4,
                            selected_menu_clip_margin=top-pc.SHIFT*1.4-16*1.4,
                            selected_timeout_gap=tab_y-(bottom-pc.SHIFT*1.4)))


def envelope_svg(result, path):
    """Standalone measured-envelope figure, explicitly NOT a gameplay render."""
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="790" viewBox="0 0 1200 790">',
             '<rect width="1200" height="790" fill="#111827"/>',
             '<g font-family="sans-serif" font-size="15" fill="white">',
             f'<text x="25" y="28">PROVED OFFLINE measurements + DESIGN projection: {pc.SHIFT:g} game units up ({pc.SHIFT*1.4:g} capture pixels)</text>',
             '<text x="25" y="53">Measured visible envelopes only. Not a gameplay render. Candidate G must confirm raster and state transitions.</text>']
    for col, row in enumerate((result['frames'][1],result['frames'][3])):
        for side in range(2):
            x = 25+col*590+side*280
            top = row['visible_ui_top']-side*pc.SHIFT*1.4
            bottom = row['visible_ui_bottom_inclusive']+1-side*pc.SHIFT*1.4
            parts += [f'<text x="{x}" y="86">{row["screen"].split(" /")[0]} {"shifted" if side else "retail"}</text>',
                      f'<rect x="{x}" y="100" width="250" height="672" fill="black" stroke="#64748b"/>',
                      f'<path d="M{x} 122.4h250" stroke="#60a5fa" stroke-dasharray="4 3"/>',
                      f'<rect x="{x+2}" y="{100+top}" width="246" height="{bottom-top}" fill="#10b981" fill-opacity=".3" stroke="#34d399"/>',
                      f'<rect x="{x+32}" y="{100+result["design"]["timeout_projected_top"]}" width="75" height="25" fill="#f59e0b" fill-opacity=".8"/>',
                      f'<rect x="{x+32}" y="{100+row["bar_top_weak"]}" width="185" height="64" fill="#ef4444" fill-opacity=".8"/>',
                      f'<text x="{x+9}" y="{120+top}">UI y {top:.1f} to {bottom:.1f}</text>',
                      f'<text x="{x+36}" y="697">scorebug</text>']
    parts += ['</g></svg>']
    path.write_text('\n'.join(parts)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe', type=Path, default=DEFAULT_XBE)
    parser.add_argument('--pack', type=Path, default=DEFAULT_PACK)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--witness-root', type=Path)
    args = parser.parse_args()
    result = native_proof(args.xbe.read_bytes(), scene_sources(args.pack))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    if args.witness_root:
        measured = measurements(args.witness_root)
        args.out.with_name('measurements.json').write_text(json.dumps(measured,indent=2)+'\n')
        envelope_svg(measured,args.out.with_name('envelopes.svg'))
    print(json.dumps({k: result[k] for k in ('classification','shift','matrix_samples','max_matrix_error')}))


if __name__ == '__main__':
    main()

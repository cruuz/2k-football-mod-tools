#!/usr/bin/env python3
"""Bounded native projection evidence for the experimental Broadcast adaptation.

Reads only a pinned 12 MB executable. No disc, archive, game boot or display.
The synthetic field projection is not a GPU capture or a coach-mode witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as camera, nfl2k5_widescreen as wide
from tools.nfl2k5_camera_far_proof import Projection, RETAIL_SHA256, SAFE_BAR
from tests.mod_editor import test_nfl2k5_widescreen_polish as fixtures


def map_owned(uc, payload):
    for region in camera.space.layout(payload)['regions']:
        uc.mem_map(region['va'], region['size'])
        uc.mem_write(region['va'], payload[region['raw']:region['raw'] + region['size']])
        flags = fixtures.u.UC_PROT_READ
        if region['kind'].startswith('code'):
            flags |= fixtures.u.UC_PROT_EXEC
        elif region['kind'].startswith('data'):
            flags |= fixtures.u.UC_PROT_WRITE
        uc.mem_protect(region['va'], region['size'], flags)


class BroadcastProjection(Projection):
    def __init__(self, payload):
        super().__init__(payload)
        map_owned(self.uc, payload)


def prove(retail):
    if len(retail) != 11948032 or hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError('the pinned USA executable is required')
    patched, receipt = camera.apply(retail)
    rows = []
    for aspect in ('4:3', *wide.ASPECTS):
        payload = patched if aspect == '4:3' else wide.apply(patched, aspect)[0]
        p = BroadcastProjection(payload)
        table = camera.read_preset_table(payload)
        for direction in (1, -1):
            for state in camera.BROADCAST_STATES:
                for zoom in (0, 1):
                    descriptor = table[camera.BROADCAST_ROW][state][1]
                    decoded = p.setup(descriptor, direction=direction, zoom=zoom)
                    samples = {name: p.point(x, y, z * direction) for name, x, y, z in (
                        ('focus', 0, 0, 0), ('backfield', 0, 0, -700), ('shotgun_qb', 0, 175, -600),
                        ('left_flat', -1600, 175, 500), ('right_flat', 1600, 175, 500),
                        ('near_wideout', 2200, 175, 0), ('far_wideout', -2200, 175, 0),
                        ('middle_15', 0, 175, 1500),
                        ('left_deep', -1600, 175, 2500), ('right_deep', 1600, 175, 2500),
                        ('deep_middle', 0, 175, 4000))}
                    rows.append(dict(aspect=aspect, direction=direction, state=state,
                                     pass_zoom=zoom, descriptor=decoded, metrics=p.metrics,
                                     points_640x480=samples))
    evidence = []
    for va, size, meaning in (
        (0x501D78, 52, 'Coach Mode menu row and independent callbacks'),
        (0x149320, 88, 'Coach toggle changes E6002C only'),
        (0x63810, 37, 'effective Coach Mode excludes mode 0, mode 3 and First Person'),
        (0x156870, 323, 'Coach Mode removes body control bindings; human team assignment retained'),
        (0x18FBE0, 849, 'separate coach command route; entered only with effective Coach Mode'),
        (0xA5490, 83, 'row 7 spectator fallback, row 6 special case, ordinary session row selection'),
        (0xA5B20, 480, 'only entering/leaving row 6 changes coach/audio settings'),
        (0x27AEB0, 149, 'native session restore and explicit row-7 fallback'),
        (0xA881E0, 80, 'fixed world sideline descriptor, native type 0 and lens 120'),
        (0xA89770, 80, 'separate scripted shot descriptor; not the selectable gameplay adaptation'),
        (0xA5FAC, 67, 'native scripted sideline mount +/-5000,1800,focus.z'),
        (0x60090, 652, 'descriptor flag 1 preserves the previous eye'),
        (0x52B700, 52, 'active Camera enum callbacks shared by the camera submenu'),
        (0x2C66A0, 63, 'maximum, current label and inclusive label width'),
        (0x2C6960, 544, 'session setter, preview, snapshot, cancel, next and previous'),
    ):
        raw = camera._read(retail, va, size)
        evidence.append(dict(va=hex(va), size=size, meaning=meaning, bytes=raw.hex(),
                             sha256=hashlib.sha256(raw).hexdigest()))
    return dict(schema='nfl2k5_camera_broadcast_proof/v5', experimental=True,
                runtime_witnessed=False, exact_coach_director_proved=False,
                scope='Native CPU projection of a following adaptation of the retail sideline mount',
                limitation='Does not identify the full coach television script or reproduce its shot selection',
                retail_sha256=RETAIL_SHA256, patch_receipt=receipt, native_evidence=evidence,
                safe_bar_640x480=SAFE_BAR, rows=rows)


def render(retail, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    payload = wide.apply(camera.apply(retail)[0], '16:9')[0]
    p = BroadcastProjection(payload)
    table = camera.read_preset_table(payload)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), layout='constrained')
    for ax, row in zip(axes, (0, 1, 7)):
        p.setup(table[row][15][1], zoom=1)
        for x in range(-2400, 2401, 800):
            points = [p.point(x, 0, z) for z in range(-1000, 5001, 100)]
            ax.plot(*zip(*points), color='#3d6b53', linewidth=.7)
        for z in range(-1000, 5001, 500):
            points = [p.point(x, 0, z) for x in range(-2400, 2401, 100)]
            ax.plot(*zip(*points), color='#91b698', linewidth=.7)
        for x, z in ((0, 0), (0, -600), (-1600, 500), (1600, 500), (2200, 0), (-2200, 0), (0, 1500), (-1600, 2500), (1600, 2500), (0, 4000)):
            feet, head = p.point(x, 0, z), p.point(x, 175, z)
            ax.plot(*zip(feet, head), color='#f3a343', linewidth=3)
            ax.scatter(*head, color='#f3a343', s=12)
        ax.add_patch(Rectangle((84, 381), 476, 48, facecolor='#222c3b', alpha=.85))
        ax.set(xlim=(0, 640), ylim=(480, 0), title=camera.PRESET_NAMES[row], aspect='equal')
        ax.set_facecolor('#162c24')
        ax.tick_params(labelsize=7)
    fig.suptitle('EXPERIMENTAL / UNWITNESSED: native CPU projection, synthetic field\n'
                 'Pass state, zoom on, 16:9. Broadcast is an adaptation; no GPU or coach-mode capture.', fontsize=10)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe', type=Path, default=fixtures.XBE)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--png', type=Path)
    args = parser.parse_args()
    if args.xbe.stat().st_size != 11948032:
        parser.error('expected a bounded USA default.xbe, never a disc or pack')
    payload = args.xbe.read_bytes()
    proof = prove(payload)
    args.json.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    if args.png:
        render(payload, args.png)
    print(f"{len(proof['rows'])} bounded native projection cases; EXPERIMENTAL / UNWITNESSED")


if __name__ == '__main__':
    main()

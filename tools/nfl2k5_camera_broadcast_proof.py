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


# The near-side stands the following mount can enter (world centimetres; the camera side is +x, y up, z along the
# field; sidelines x = +/-2438, goal lines z = +/-4572, end lines +/-5486). Measured on the retail stadium scenes
# through the Stadium Studio's own glTF derivation: the reporter's Superdome (scene outer 3153) and the first model
# (3136) dissected group by group, all 53 models surveyed by facing-aware ray casting (ASTRA_REPORT.md, beta 63.1).
# Only the numbers are recorded here; no retail geometry is copied. The Superdome's lower bowl rises from its front
# row (4241, 164) to its back row (7029, 1175) with about 110 cm of crowd cards on the seats; its second level
# (loge) starts above it with the underside at 1408 cm and the front at 5821 cm (Arizona: 1498 and 5972); beyond
# the goal line its loge corner trim comes in to x = 3779 at 1430..1892 cm. v5.2 put the eye 1650 cm up and 5650 cm
# toward the camera side of the ball, exactly the second level's front-row height, so any ball past the near hash
# (282 cm) had the mount among the second-level seats and crowd, and any ball in the end zone had it inside the
# corner trim: the reported clipping.
STANDS = dict(
    second_level=dict(front_x=5821.0, underside_y=1408.0),
    lower_bowl=dict(front_x=4241.0, front_y=164.0, back_x=7029.0, back_y=1175.0, card=110.0),
    corner=dict(x_from=3779.0, y_from=1430.0, y_to=1892.0, z_from=5080.0),
)
# The ball positions the mount is proved clear for: the whole field along z (both end zones included), and across
# the field from the far sideline to CLEAN_BALL_X toward the camera (the near hash is 282, the near numbers begin at
# 1097 from the centre). Wider plays still move a constant-offset mount into the stands; see the report.
CLEAN_BALL_X = 900.0
BALL_GRID_X = tuple(float(x) for x in range(-2400, int(CLEAN_BALL_X) + 1, 300))
BALL_GRID_Z = tuple(float(z) for z in range(-5486, 5487, 457))
V52_EYE_FOCUS_RELATIVE = (5650.0, 1650.0, 450.0)


def stands_violations(eye_focus_relative, direction, *, grid_x=BALL_GRID_X, grid_z=BALL_GRID_Z):
    """Sampled ball positions whose world eye sits inside the modelled near-side stands.

    ``eye_focus_relative`` is the settled native eye relative to the focus for ``direction`` (the z lead already
    carries the direction sign, as the harness reports it).
    """
    ex, ey, ez = eye_focus_relative
    level, bowl, corner = STANDS['second_level'], STANDS['lower_bowl'], STANDS['corner']
    rise = (bowl['back_y'] - bowl['front_y']) / (bowl['back_x'] - bowl['front_x'])
    out = []
    for bx in grid_x:
        for bz in grid_z:
            x, y, z = bx + ex, ey, bz + ez
            kinds = []
            if x >= level['front_x'] and y >= level['underside_y']:
                kinds.append('second level')
            if bowl['front_x'] <= x <= bowl['back_x'] and y <= bowl['front_y'] + rise * (x - bowl['front_x']) + bowl['card']:
                kinds.append('lower bowl crowd')
            if abs(z) >= corner['z_from'] and x >= corner['x_from'] and corner['y_from'] <= y <= corner['y_to']:
                kinds.append('corner trim')
            for kind in kinds:
                out.append(dict(kind=kind, ball=(bx, bz), eye=(x, y, z), direction=direction))
    return out


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
                    violations = stands_violations(p.eye, direction)
                    rows.append(dict(aspect=aspect, direction=direction, state=state,
                                     pass_zoom=zoom, descriptor=decoded, metrics=p.metrics,
                                     points_640x480=samples,
                                     stands=dict(violations=violations, sampled_ball_positions=len(BALL_GRID_X) * len(BALL_GRID_Z))))
    eye = rows[0]['metrics']['eye_focus_relative_cm']
    stands = dict(model=STANDS, clean_ball_x=CLEAN_BALL_X, ball_grid_x=BALL_GRID_X, ball_grid_z=BALL_GRID_Z,
                  eye_focus_relative_cm=eye,
                  second_level_front_reached_at_ball_x=STANDS['second_level']['front_x'] - eye[0],
                  rows_with_violations=sum(bool(row['stands']['violations']) for row in rows),
                  v52_eye_focus_relative_cm=V52_EYE_FOCUS_RELATIVE,
                  v52_violations={str(direction): len(stands_violations(V52_EYE_FOCUS_RELATIVE[:2] + (V52_EYE_FOCUS_RELATIVE[2] * direction,), direction))
                                  for direction in (1, -1)})
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
    return dict(schema='nfl2k5_camera_broadcast_proof/v5', revision='v5.3 (beta 63.1: the mount clears the near stands)',
                experimental=True, runtime_witnessed=False, exact_coach_director_proved=False,
                scope='Native CPU projection of a following adaptation of the retail sideline mount',
                limitation='Does not identify the full coach television script or reproduce its shot selection; '
                           'the stands model is a measured envelope, not the rendered stadium',
                retail_sha256=RETAIL_SHA256, patch_receipt=receipt, native_evidence=evidence,
                safe_bar_640x480=SAFE_BAR, stands=stands, rows=rows)


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

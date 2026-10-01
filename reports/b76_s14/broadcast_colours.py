"""On-air wing and plate colours for every team with ESPN broadcast evidence, by one method.

Read-only evidence, never copied into the repository (only the measured numbers are):

- NYG at LAR, 2026 Monday Night Football: the s12 highlights reel and Noah's off-air OBS recording, the rows
  reports/b76_s12/harvest.json classified ``normal``.
- DEN at KC, ESPN 2026 Week 1, the full game at one frame per second:
  ``/media/noah/Storage/Broadcast refs/espn-2026-broncos-chiefs-full/frames_1s``, seconds whose per-second label
  (``grammar/labels.jsonl``) is a settled full bar with a down-and-distance plate.
- LV at HOU, ESPN 2026 preseason week 2 highlights at 29.97 frames per second:
  ``/media/noah/Storage/Broadcast refs/espn-2025-raiders-texans/frames``, one frame from the middle of every second
  whose label (``grammar_proto/sec_rt.jsonl``) is a full bar with a down plate.
- Any folder added with ``--extra NAME=FOLDER:AWAY:HOME`` (frames named ``frame_*.png``/``*.jpg``); every frame
  passes the same bar predicates, so no label file is needed.

The same code measures every frame, whatever its source:

- bar present: the s12 predicates (bright clock pill, dark body) plus a dark tray on both sides of the plate.
- wing: the median RGB of the 12 by 80 block at each wing's outer end (``away_wing_peak`` and ``home_wing_peak``
  in reports/b76_s12/harvest.py), per frame, then the median over frames. That is the on-air colour the team tint
  reaches at the bar's outer ends.
- plate: the median RGB of the plate body (rows 953 to 971, x 845 to 1075) without the white label or its
  antialiased edge (the label mask is dilated by two pixels), per frame. The possessing team is read from the light
  chevron on the bar's top edge above that team's score, which is how ESPN marks possession; frames where neither
  or both sides are lit are left out. Then the median over frames per team.

``measure_frame`` is also applied to our own renders, so a display colour can be compared with the broadcast by
exactly the same numbers. No in-game behaviour is measured or claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
REFS = Path('/media/noah/Storage/Broadcast refs')
S12 = ROOT / 'reports/b76_s12/harvest.json'
SCRATCH = Path.home() / '2k-worktrees/.b76-session/scratchpad/b76'
COMPOSITE_CAP = 400

WING = dict(away=(440, 960, 452, 1040), home=(1470, 960, 1482, 1040))
# The per-row wing profile is read just inside the broadcast bar's own edge highlight lines (x 440 and 1480 on
# air; the broadcast bar spans about 436 to 1484, ours 437 to 1478), 12 columns wide, so no edge line, bevel or
# pitch pixel enters it. reports/b76_s14/fit_display.py reads our render 3 to 15 pixels inside our own bar ends.
WING_PROFILE = dict(away=(442, 940, 454, 1056), home=(1466, 940, 1478, 1056))
PLATE = (845, 953, 1075, 972)
# The light possession chevron: rows 948 to 954, centred over each score.
CHEVRON = dict(away=(740, 948, 770, 955), home=(1145, 948, 1175, 955))
LUMA = np.array((0.2126, 0.7152, 0.0722))
# Rows of the per-row wing profile (the bar spans rows 942 to 1052).
PROFILE_ROWS = (940, 1056)
# The bar crop kept (as a per-pixel median, in scratch only) for the tint calibration.
CROP = (420, 930, 1500, 1065)


def hexof(rgb):
    return '#%02X%02X%02X' % tuple(int(round(float(v))) for v in rgb)


def block(frame, box):
    x0, y0, x1, y1 = box
    return frame[y0:y1, x0:x1].reshape(-1, 3)


def bar_present(frame) -> bool:
    """The s12 predicates (reports/b76_s12/harvest.py bar_present) and a dark tray beside the plate."""
    pill = frame[1005:1035, 900:1010].mean()
    body = frame[995:1045, 1230:1250].mean()
    tray = frame[1000:1040, 812:828].mean() < 80 and frame[1000:1040, 1092:1108].mean() < 80
    return bool(pill > 150 and body < 70 and tray)


def possession(frame):
    lit = {side: float((block(frame, box) @ LUMA).mean()) for side, box in CHEVRON.items()}
    if lit['away'] > 140 and lit['home'] < 110:
        return 'away', lit
    if lit['home'] > 140 and lit['away'] < 110:
        return 'home', lit
    return None, lit


def plate_colour(frame):
    x0, y0, x1, y1 = PLATE
    patch = frame[y0:y1, x0:x1].astype(np.float64)
    label = patch.min(-1) > 140
    grown = label.copy()
    for _ in range(2):
        padded = np.pad(grown, 1)
        grown = np.max([padded[dy:dy + label.shape[0], dx:dx + label.shape[1]]
                        for dy in range(3) for dx in range(3)], axis=0)
    rest = patch[~grown]
    if len(rest) < 0.25 * label.size:
        return None
    return np.median(rest, axis=0)


def row_profile(frame, box):
    """Mean RGB of each row of the wing's outer-end columns, rows PROFILE_ROWS."""
    x0, _y0, x1, _y1 = box
    return frame[PROFILE_ROWS[0]:PROFILE_ROWS[1], x0:x1].mean(axis=1)


def measure_frame(frame) -> dict:
    """Wing ends, plate body and possession of one 1920 by 1080 frame (broadcast or ours)."""
    frame = np.asarray(frame, dtype=np.float64)
    side, lit = possession(frame)
    plate = plate_colour(frame)
    return dict(present=bar_present(frame), possession=side, chevron_luma={k: round(v, 1) for k, v in lit.items()},
                away_wing=np.median(block(frame, WING['away']), axis=0).tolist(),
                home_wing=np.median(block(frame, WING['home']), axis=0).tolist(),
                away_profile=row_profile(frame, WING_PROFILE['away']),
                home_profile=row_profile(frame, WING_PROFILE['home']),
                plate=None if plate is None else plate.tolist())


def load(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float64)


def s12_frames():
    harvest = json.loads(S12.read_text())
    folders = dict(highlights=SCRATCH / 'mnf/frames', obs=SCRATCH / 'obs/frames')
    return [(row['source'], folders[row['source']] / row['frame']) for row in harvest['frames']
            if row['state'] == 'normal']


def labelled_seconds(path, *, settled_key):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    keep = []
    for r in rows:
        if r.get('layout') != 'full_bar' or r.get('kind') not in ('down_distance', 'down_only', 'goal'):
            continue
        if settled_key and not (r.get('settled') and (r.get('clean') or 0) >= 0.8):
            continue
        keep.append(r['t'])
    return keep


def den_kc_frames():
    folder = REFS / 'espn-2026-broncos-chiefs-full/frames_1s'
    seconds = labelled_seconds(REFS / 'espn-2026-broncos-chiefs-full/grammar/labels.jsonl', settled_key=True)
    return [('den_kc', folder / ('s_%05d.jpg' % (t + 1))) for t in seconds]


def lv_hou_frames():
    folder = REFS / 'espn-2025-raiders-texans/frames'
    seconds = labelled_seconds(REFS / 'espn-2025-raiders-texans/grammar_proto/sec_rt.jsonl', settled_key=False)
    return [('lv_hou', folder / ('frame_%06d.jpg' % (round((t + 0.5) * 29.97) + 1))) for t in seconds]


def extra_frames(spec, stride):
    name, _, rest = spec.partition('=')
    folder, away, home = rest.rsplit(':', 2)
    files = sorted(list(Path(folder).glob('frame_*.png')) + list(Path(folder).glob('frame_*.jpg')))[::stride]
    return name, away, home, [(name, f) for f in files]


def summarise(values):
    if not values:
        return None
    a = np.array(values)
    med = np.median(a, axis=0)
    return dict(rgb=[round(float(v), 2) for v in med], hex=hexof(med), frames=len(values),
                p25=[round(float(v), 2) for v in np.percentile(a, 25, axis=0)],
                p75=[round(float(v), 2) for v in np.percentile(a, 75, axis=0)])


def run(matchups, stride, composites=None):
    """Measure every matchup; optionally keep per-possession median crops (scratch, never the repository)."""
    teams, sources = {}, {}
    for name, (away, home, frames) in matchups.items():
        wings = dict(away=[], home=[])
        profiles = dict(away=[], home=[])
        plates = dict(away=[], home=[])
        crops = dict(away=[], home=[])
        used = rejected = 0
        # Evenly spread composite frames over the whole game, at most COMPOSITE_CAP per possession side.
        keep_every = max(1, len(frames[::stride]) // (2 * COMPOSITE_CAP))
        for _source, path in frames[::stride]:
            if not path.is_file():
                rejected += 1
                continue
            frame = load(path)
            m = measure_frame(frame)
            if not m['present']:
                rejected += 1
                continue
            used += 1
            wings['away'].append(m['away_wing'])
            wings['home'].append(m['home_wing'])
            profiles['away'].append(m['away_profile'])
            profiles['home'].append(m['home_profile'])
            if m['possession'] and m['plate'] is not None:
                plates[m['possession']].append(m['plate'])
                if composites is not None and used % keep_every == 0 and len(crops[m['possession']]) < COMPOSITE_CAP:
                    crops[m['possession']].append(frame[CROP[1]:CROP[3], CROP[0]:CROP[2]].astype(np.uint8))
        if composites is not None:
            composites.mkdir(parents=True, exist_ok=True)
            for side in ('away', 'home'):
                if crops[side]:
                    np.save(composites / ('%s_%s_ball.npy' % (name, side)), np.median(np.stack(crops[side]), axis=0))
        sources[name] = dict(away=away, home=home, frames_considered=len(frames[::stride]), frames_used=used,
                             frames_rejected=rejected, stride=stride,
                             folders=sorted({str(p.parent) for _s, p in frames}))
        for side, team in (('away', away), ('home', home)):
            profile = np.median(np.array(profiles[side]), axis=0) if profiles[side] else None
            teams.setdefault(team, {})[name] = dict(
                side=side, wing=summarise(wings[side]), plate=summarise(plates[side]),
                wing_rows=None if profile is None else dict(
                    first_row=PROFILE_ROWS[0], columns=list(WING_PROFILE[side][::2]),
                    rgb=[[round(float(v), 1) for v in row] for row in profile]))
    return teams, sources


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output', type=Path, default=OUT / 'broadcast_colours.json')
    p.add_argument('--stride', type=int, default=1, help='Use every Nth selected frame')
    p.add_argument('--extra', action='append', default=[], help='NAME=FOLDER:AWAY:HOME, repeatable')
    p.add_argument('--only-extra', action='store_true', help='Measure only the --extra folders')
    p.add_argument('--composites', type=Path, help='Scratch folder for per-possession median crops (never the repository)')
    a = p.parse_args(argv)
    matchups = {}
    if not a.only_extra:
        matchups['nyg_lar'] = ('NYG', 'LAR', s12_frames())
        matchups['den_kc'] = ('DEN', 'KC', den_kc_frames())
        matchups['lv_hou'] = ('LV', 'HOU', lv_hou_frames())
    for spec in a.extra:
        name, away, home, frames = extra_frames(spec, 1)
        matchups[name] = (away, home, frames)
    teams, sources = run(matchups, a.stride, a.composites)
    previous = json.loads(a.output.read_text()) if a.output.is_file() and a.only_extra else {}
    merged_teams = dict(previous.get('teams', {}))
    for team, entry in teams.items():
        merged_teams.setdefault(team, {}).update(entry)
    merged_sources = dict(previous.get('sources', {}))
    merged_sources.update(sources)
    result = dict(schema='b76-s14-broadcast-colours/v1', teams=merged_teams, sources=merged_sources,
                  regions=dict(wing=WING, wing_profile=WING_PROFILE, profile_rows=PROFILE_ROWS, plate=PLATE,
                               chevron=CHEVRON),
                  method='Per-frame medians of fixed regions, then the median over frames; plate split by the '
                         'possession chevron; see the module docstring.',
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  note='Evidence frames are read-only and outside the repository; only these numbers are kept.')
    a.output.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    for team, entry in sorted(merged_teams.items()):
        for source, m in entry.items():
            print('%-4s %-8s wing %s (%s) plate %s (%s)' % (
                team, source, m['wing'] and m['wing']['hex'], m['wing'] and m['wing']['frames'],
                m['plate'] and m['plate']['hex'], m['plate'] and m['plate']['frames']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

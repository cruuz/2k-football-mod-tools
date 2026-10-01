"""Read-only measurement of the 2026 Giants at Rams Monday Night Football bar.

Every number here is measured from the supplied read-only broadcast frames. No
frame, crop or retail byte is written into the repository: only measurements and
the small derived composites this job's report needs. Geometry is reported both
at 1080 lines and at the 617-pixel player bar scale used by reports/b72_s10 and
reports/b72_s11, so the residuals stay comparable with those passes.

Two read-only sources are measured: ``highlights`` (the 2026 Giants at Rams MNF
highlights reel) and ``obs`` (Noah's own off-air recording of the same broadcast,
which carries states the highlights never show). Each frame keeps its source, and
every element is reported per source as well as combined.

Usage:
    python3 reports/b76_s12/harvest.py \
        --frames highlights=FRAMES_A --frames obs=FRAMES_B --output reports/b76_s12
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

# 617 visible columns across the 1041-pixel ESPN bar: the player-size scale that
# reports/b72_s10/player_scale.py established and that s11 reused unchanged.
SCALE = 617 / 1041
CROP = (420, 930, 1500, 1065)
LUMA = (0.2126, 0.7152, 0.0722)

# Search windows, deliberately wider than any expected element. Every reported
# box is the measured extent inside its window, never the window itself.
WINDOWS = dict(
    plate=(790, 950, 1130, 992),
    capsule=(830, 992, 1090, 1045),
    away_score=(690, 955, 828, 1030),
    home_score=(1092, 955, 1230, 1030),
    away_timeouts=(706, 1026, 812, 1045),
    home_timeouts=(1110, 1026, 1216, 1045),
    quarter=(846, 1004, 898, 1036),
    clock=(904, 1004, 1016, 1036),
    play_clock=(1022, 1004, 1076, 1036),
    away_logo=(436, 943, 700, 1052),
    home_logo=(1230, 943, 1485, 1052),
    watermark=(1600, 20, 1900, 80),
    housing_rail=(820, 1040, 1100, 1048),
)
STATES = ('normal', 'play_clock_red', 'flag', 'banner', 'timeout',
          'halftime_or_final', 'absent', 'other')


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def luma(a: np.ndarray) -> np.ndarray:
    return a @ np.asarray(LUMA)


def box_of(mask: np.ndarray, origin=(0, 0)):
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    return [int(xs.min() + origin[0]), int(ys.min() + origin[1]),
            int(xs.max() + origin[0] + 1), int(ys.max() + origin[1] + 1)]


def player(box):
    """One box expressed at the 617-pixel player bar scale."""
    if not isinstance(box, (list, tuple)):
        return None
    return [round(v * SCALE, 3) for v in box]


def window(frame: np.ndarray, name: str):
    x0, y0, x1, y1 = WINDOWS[name]
    return frame[y0:y1, x0:x1], (x0, y0)


def bar_present(frame: np.ndarray) -> bool:
    """Two independent measured predicates, never a single bright sample."""
    pill = frame[1005:1035, 900:1010].mean()
    body = frame[995:1045, 1230:1250].mean()
    return bool(pill > 150 and body < 70)


def bar_box(frame: np.ndarray):
    """Outer bar extent, from the fraction of pitch-coloured pixels per line.

    The scan is confined to the crop the composites use, so a padded composite
    measures the same extent a live frame does.
    """
    def pitch(a):
        return (a[..., 1] > a[..., 0] + 6) & (a[..., 1] > a[..., 2] + 20)
    band = frame[1000:1040, CROP[0]:CROP[2]]
    columns = np.where(pitch(band).mean(0) < 0.3)[0]
    strip = frame[CROP[1]:CROP[3], 1150:1230]
    rows = np.where(pitch(strip).mean(1) < 0.3)[0]
    if not len(columns) or not len(rows):
        return None
    return [int(columns.min() + CROP[0]), int(rows.min() + CROP[1]),
            int(columns.max() + CROP[0] + 1), int(rows.max() + CROP[1] + 1)]


def ink(a: np.ndarray, kind='light'):
    if kind == 'light':
        return (a.min(-1) > 170) & ((a.max(-1) - a.min(-1)) < 70)
    if kind == 'dark':
        return a.max(-1) < 110
    if kind == 'blue':
        # The bar's own top bevel is a near-white blue-cast highlight. Excluding
        # bright pixels keeps the plate's saturated blue from swallowing it.
        return (a[..., 2] > a[..., 0] + 55) & (a[..., 2] > 110) & (a.min(-1) < 170)
    if kind == 'gold':
        return (a[..., 0] > 140) & (a[..., 1] > 110) & (a[..., 2] < a[..., 0] - 60)
    if kind == 'red':
        return (a[..., 0] > 90) & (a[..., 1] < a[..., 0] - 45) & (a[..., 2] < a[..., 0] - 40)
    raise ValueError('unknown ink kind ' + kind)


def wing_profile(frame: np.ndarray, side: str):
    """Team colour fall-off across the wing, measured column by column.

    The mark's own ink sits on top of the wing, so the wing colour is read as
    the 90th percentile of blue-minus-red over the wing's rows: that survives
    the letterforms without averaging them in.
    """
    rows = frame[946:1050]
    signal = rows[..., 2] - rows[..., 0]
    # The mark's own ink covers most rows of the columns it crosses, so those
    # pixels are excluded outright rather than averaged into the wing colour.
    mark = ink(rows, 'light') | ink(rows, 'red') | ink(rows, 'gold')
    xs = range(434, 800) if side == 'away' else range(1487, 1120, -1)
    raw = []
    for x in xs:
        column = signal[:, x][~mark[:, x]]
        raw.append(float(np.percentile(column, 90)) if len(column) >= 15 else np.nan)
    raw = np.array(raw)
    index = np.arange(len(raw))
    if np.isnan(raw).any():
        good = ~np.isnan(raw)
        raw = np.interp(index, index[good], raw[good])
    # A five-column box smooth removes the bevel and keyline spikes without
    # moving the fall-off: the quantity of interest is the decay, not an edge.
    values = np.convolve(raw, np.ones(5) / 5, mode='same')
    start = int(np.argmax(values))
    peak = float(values[start])
    edge = 434 if side == 'away' else 1487
    out = dict(side=side, peak_signal=round(peak, 2), edge_x=edge,
               peak_offset_px=start, peak_offset_player_px=round(start * SCALE, 2))
    for fraction in (0.5, 0.25, 0.1):
        hit = next((i for i, v in enumerate(values[start:]) if v < peak * fraction), None)
        out['fall_to_%d_percent_px' % round(fraction * 100)] = None if hit is None else int(hit)
        out['fall_to_%d_percent_player_px' % round(fraction * 100)] = None if hit is None else round(hit * SCALE, 2)
    sample = rows[:, (edge + 6) if side == 'away' else (edge - 8)]
    out['peak_rgb'] = [round(float(v), 2) for v in np.median(sample, axis=0)]
    # An exponential decay constant, so the authored ramp can be set directly.
    tail = values[start:start + 260]
    positive = np.where(tail > max(1.0, peak * 0.06))[0]
    if len(positive) > 20:
        fit = np.polyfit(positive, np.log(tail[positive]), 1)
        out['decay_px'] = round(float(-1 / fit[0]), 2) if fit[0] < 0 else None
        out['decay_player_px'] = None if out['decay_px'] is None else round(out['decay_px'] * SCALE, 2)
    out['profile_px'] = [round(float(v), 2) for v in values[:340]]
    return out


def measure(frame: np.ndarray) -> dict:
    out = dict(bar=bar_box(frame))
    plate, origin = window(frame, 'plate')
    out['plate'] = box_of(ink(plate, 'blue'), origin)
    capsule, origin = window(frame, 'capsule')
    out['capsule'] = box_of(capsule.min(-1) > 185, origin)
    rail, origin = window(frame, 'housing_rail')
    out['housing_rail'] = box_of(luma(rail) > 45, origin)
    for name in ('away_score', 'home_score', 'away_timeouts', 'home_timeouts'):
        a, origin = window(frame, name)
        out[name] = box_of(ink(a, 'light'), origin)
    for name in ('quarter', 'clock', 'play_clock'):
        a, origin = window(frame, name)
        out[name] = box_of(ink(a, 'dark'), origin)
    away, origin = window(frame, 'away_logo')
    out['away_logo'] = box_of(ink(away, 'light') | ink(away, 'red'), origin)
    home, origin = window(frame, 'home_logo')
    out['home_logo'] = box_of(ink(home, 'gold'), origin)
    # The bar's top and bottom bevels: measured over plain body columns, away
    # from the plate and the marks, because the rim carries real visible area.
    body = float(np.median(luma(frame[1000:1035, 1215:1245])))
    for name, y0, y1 in (('rim_top', 941, 966), ('rim_bottom', 1040, 1056)):
        bevel = frame[y0:y1, 1215:1245]
        out[name] = box_of(luma(bevel) > body + 25, (1215, y0))
    out['body_luma'] = round(body, 2)
    return out


def classify(frame: np.ndarray, m: dict) -> str:
    if m['bar'] is None or m['capsule'] is None:
        return 'absent'
    pc = frame[1004:1034, 1020:1080]
    if ink(pc, 'red').mean() > 0.25:
        return 'play_clock_red'
    plate = frame[948:982, 840:1080]
    if ((plate[..., 0] > 150) & (plate[..., 1] > 130) & (plate[..., 2] < 110)).mean() > 0.4:
        return 'flag'
    banner = frame[890:936, 700:1240]
    if (luma(banner) < 70).mean() > 0.6 or (banner[..., 2] > banner[..., 0] + 50).mean() > 0.4:
        return 'banner'
    if m['clock'] is None or m['quarter'] is None:
        return 'halftime_or_final'
    if m['away_score'] is None or m['home_score'] is None:
        return 'other'
    return 'normal'


def colours(stack: np.ndarray, regions: dict) -> dict:
    out = {}
    for name, (x0, y0, x1, y1) in regions.items():
        block = stack[:, y0 - CROP[1]:y1 - CROP[1], x0 - CROP[0]:x1 - CROP[0]]
        flat = block.reshape(-1, 3).astype(float)
        out[name] = dict(box=[x0, y0, x1, y1], box_player=player([x0, y0, x1, y1]),
                         p5=[round(float(v), 2) for v in np.percentile(flat, 5, axis=0)],
                         median=[round(float(v), 2) for v in np.median(flat, axis=0)],
                         p95=[round(float(v), 2) for v in np.percentile(flat, 95, axis=0)],
                         samples=int(block.shape[0]))
    return out


def watermark(paths, output: Path, name: str = 'watermark_mnf_measured.png') -> dict:
    """Static corner mark: lower-envelope temporal composite, then its opacity.

    The mark is white over live footage, so the 5th percentile across frames is
    the darkest background each pixel ever shows blended with the constant mark.
    Opacity follows from the measured lift of the mark's rows over the frames'
    own background, not from an assumed alpha.
    """
    x0, y0, x1, y1 = WINDOWS['watermark']
    stack = np.stack([np.asarray(Image.open(p).convert('RGB').crop((x0, y0, x1, y1)), dtype=np.float32)
                      for p in paths])
    low = np.percentile(stack, 5, axis=0)
    grey = low.mean(-1)
    mask = grey > grey.min() + 60
    box = box_of(mask, (x0, y0))
    if box is None:
        raise ValueError('No stable corner mark found')
    inside = mask
    background = float(np.median(grey[~inside])) if (~inside).any() else 0.0
    peak = float(np.percentile(grey[inside], 95))
    opacity = round(max(0.0, min(1.0, (peak - background) / max(1.0, 255.0 - background))), 4)
    alpha = np.clip((grey - background) / max(1.0, peak - background), 0, 1) * inside
    crop = box[0] - x0, box[1] - y0, box[2] - x0, box[3] - y0
    mark = Image.new('RGBA', (crop[2] - crop[0], crop[3] - crop[1]), 'white')
    mark.putalpha(Image.fromarray(np.rint(alpha[crop[1]:crop[3], crop[0]:crop[2]] * 255).astype('uint8')))
    mark.save(output / name)
    return dict(box=box, box_player=player(box), width=box[2] - box[0], height=box[3] - box[1],
                background_luma=round(background, 2), peak_luma=round(peak, 2),
                opacity=opacity, samples=len(paths),
                method='5th percentile luminance over the accepted frames; opacity from the mark lift over the same composite background')


REGIONS_RGB = dict(
    body=(1215, 1000, 1245, 1035), plate_top=(900, 949, 1010, 954),
    plate_bottom=(900, 974, 1010, 980), capsule=(900, 1012, 916, 1030),
    rim_top=(1150, 946, 1230, 956), rim_bottom=(1150, 1046, 1230, 1051),
    away_wing_peak=(440, 960, 452, 1040), home_wing_peak=(1470, 960, 1482, 1040),
    away_wing_mid=(560, 960, 572, 1040), home_wing_mid=(1350, 960, 1362, 1040),
    away_wing_tail=(700, 960, 712, 1040), home_wing_tail=(1210, 960, 1222, 1040),
    score_white=(736, 975, 776, 1010), housing_rail=(860, 1041, 1060, 1044),
)
# The temporal composite is a median over accepted frames. It is capped so a
# long recording cannot exhaust memory; the cap is recorded in the receipt.
COMPOSITE_CAP = 500


def mark_inks(full: np.ndarray) -> dict:
    marks = {}
    for name, kinds in (('away_logo', ('light', 'red')), ('home_logo', ('gold', 'blue'))):
        x0, y0, x1, y1 = WINDOWS[name]
        patch = full[y0:y1, x0:x1]
        entry = dict(window=[x0, y0, x1, y1])
        for kind in kinds:
            mask = ink(patch, kind)
            entry[kind] = dict(pixels=int(mask.sum()),
                               median_rgb=[round(float(v), 2) for v in np.median(patch[mask], axis=0)] if mask.any() else None,
                               box=box_of(mask, (x0, y0)))
        marks[name] = entry
    return marks


def scan(source: str, folder: Path) -> tuple:
    """Classify every frame of one source and keep its accepted composite set."""
    files = sorted(Path(folder).glob('frame_*.png'))
    if not files:
        raise SystemExit('No frame_*.png in ' + str(folder))
    rows, accepted = [], []
    for path in files:
        frame = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)
        if not bar_present(frame):
            rows.append(dict(source=source, frame=path.name, state='absent'))
            continue
        m = measure(frame)
        state = classify(frame, m)
        rows.append(dict(source=source, frame=path.name, state=state, boxes=dict(m),
                         boxes_player={k: player(v) for k, v in m.items()}))
        if state == 'normal':
            accepted.append(path)
    return files, rows, accepted


def composite_of(accepted, output: Path, name: str) -> tuple:
    step = max(1, len(accepted) // COMPOSITE_CAP)
    used = accepted[::step][:COMPOSITE_CAP]
    stack = np.stack([np.asarray(Image.open(p).convert('RGB').crop(CROP), dtype=np.uint8) for p in used])
    median = np.median(stack, axis=0).astype(np.uint8)
    Image.fromarray(median).save(output / name)
    full = np.zeros((1080, 1920, 3), dtype=np.float32)
    full[CROP[1]:CROP[3], CROP[0]:CROP[2]] = median.astype(np.float32)
    return stack, full, used


def summarise(output: Path, tag: str, accepted, stack, full, used) -> dict:
    boxes = measure(full)
    return dict(
        accepted_normal=len(accepted), composite_frames=len(used),
        composite_cap=COMPOSITE_CAP,
        composite=dict(boxes=boxes, boxes_player={k: player(v) for k, v in boxes.items()},
                       file='broadcast_bar_median%s.png' % tag,
                       sha256=hashlib.sha256((output / ('broadcast_bar_median%s.png' % tag)).read_bytes()).hexdigest()),
        wings=dict(away=wing_profile(full, 'away'), home=wing_profile(full, 'home')),
        colours=colours(stack, REGIONS_RGB),
        marks=mark_inks(full))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames', action='append', required=True,
                   help='NAME=PATH, repeatable. Each source is measured separately and then combined.')
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    a = p.parse_args(argv)
    a.output.mkdir(parents=True, exist_ok=True)
    sources = {}
    for entry in a.frames:
        name, _, path = entry.partition('=')
        sources[name or 'source'] = Path(path or name)
    rows, per_source, all_accepted, all_files = [], {}, [], 0
    for name, folder in sources.items():
        files, source_rows, accepted = scan(name, folder)
        all_files += len(files)
        rows.extend(source_rows)
        if len(accepted) < 25:
            raise SystemExit('Too few accepted frames for %s: %d' % (name, len(accepted)))
        stack, full, used = composite_of(accepted, a.output, 'broadcast_bar_median_%s.png' % name)
        entry = summarise(a.output, '_' + name, accepted, stack, full, used)
        entry['folder'] = str(folder)
        entry['frames'] = len(files)
        entry['states'] = {}
        for row in source_rows:
            entry['states'][row['state']] = entry['states'].get(row['state'], 0) + 1
        entry['watermark'] = watermark(accepted[::max(1, len(accepted) // 150)], a.output,
                                       'watermark_mnf_%s.png' % name)
        per_source[name] = entry
        all_accepted.extend(accepted)
    stack, full, used = composite_of(all_accepted, a.output, 'broadcast_bar_median.png')
    combined = summarise(a.output, '', all_accepted, stack, full, used)
    counts = {}
    for row in rows:
        counts[row['state']] = counts.get(row['state'], 0) + 1
    result = dict(
        schema='b76-s12-harvest/v2',
        sources={name: dict(folder=str(folder), frames=per_source[name]['frames'], read_only=True)
                 for name, folder in sources.items()},
        source_note='Broadcast frames are evidence only. No frame is copied into the repository.',
        scale=dict(bar_width_px=617, factor=round(SCALE, 6),
                   note='Geometry is given at 1080 lines and at the 617-pixel player bar of b72-s10/s11.'),
        states=dict(counts=counts, accepted_normal=len(all_accepted), taxonomy=list(STATES),
                    by_source={name: entry['states'] for name, entry in per_source.items()}),
        composite=combined['composite'], wings=combined['wings'],
        colours=combined['colours'], marks=combined['marks'],
        watermark=watermark(all_accepted[::max(1, len(all_accepted) // 200)], a.output,
                            'watermark_mnf_measured.png'),
        by_source=per_source,
        frames=rows,
        limitations=[
            'Element boxes are measured extents of a thresholded feature, not a claim of exact ESPN source geometry.',
            'Wing fall-off is read as the 90th percentile of blue minus red per column so the mark ink does not enter the average.',
            'The temporal composite uses an evenly strided subset capped at %d frames per source.' % COMPOSITE_CAP,
            'No in-game behaviour is measured or claimed here.',
        ])
    write(a.output / 'harvest.json', result)
    print(json.dumps(dict(frames=all_files, states=counts,
                          by_source={k: v['states'] for k, v in per_source.items()},
                          bar=combined['composite']['boxes']['bar'],
                          plate=combined['composite']['boxes']['plate'],
                          marks={k: {kk: vv['pixels'] for kk, vv in v.items() if kk != 'window'}
                                 for k, v in combined['marks'].items()},
                          watermark=result['watermark']['box']), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

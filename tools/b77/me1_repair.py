#!/usr/bin/env python3
"""Super Bowl event walls (N06) and the era ball (N15) on a verified candidate copy.

prepare reads a disc and writes only the changed spans and receipts to a work folder: the stadium scene span of each
of the 16 Super Bowl aliases, the ball scene span of global.iff, and the changed runs of default.xbe (the moment-venue
owner with the ball selector and its 0x950CC hook). It accepts the v0.6.1 candidate or that candidate after mo2; the
spans are disjoint from mo2's field spans, so both are pinned with their own output hash. Output hashes are computed
on a virtual repaired disc without making a disc copy; that receipt is explicitly not a physical write.
apply writes those same fixed spans to --disc-copy, refusing unknown whole-disc hashes. scope compares two actual
discs. studio compares every repaired wall span with the Studio's own compiled alias, without a disc copy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_era_ball as ball
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_super_bowl_walls as walls
from mod_editor.core import platform_compat as io

BASE_SHA = '520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4'
MO2_PINS = Path(__file__).with_name('mo2_pins.json')
PINS = Path(__file__).with_name('me1_pins.json')
BLOCK = 4 * 1024 * 1024


def write_json(path, doc):
    with Path(path).open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(doc, stream, indent=2, sort_keys=True)
        stream.write('\n')


def require(ok, reason):
    if not ok:
        raise ValueError('me1 refused: ' + reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wall_rows():
    return [r['row'] for r in walls.manifest()['rows']]


def _entry_edits(disc, target, name, identity, before, after, start, size, label):
    entry = disc.archive_entries[target.outer(name, identity=identity)]
    out, cursor = [], start
    for span in disc.entry_spans(entry, start, size):
        out.append(dict(offset=span.xiso_offset, length=span.length, data=after[cursor:cursor + span.length],
                        before=before[cursor:cursor + span.length], name=label))
        cursor += span.length
    require(cursor == start + size, label + ' span mapping')
    return out


def xbe_runs(before, after, gap=16):
    """[(start, end)] runs of differing bytes, joining runs closer than `gap`."""
    require(len(before) == len(after), 'the executable changed size')
    runs = []
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b:
            if runs and i - runs[-1][1] < gap:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
    return [tuple(r) for r in runs]


def patches(path, disc):
    target = hs.Target(disc)
    situ = target.get(identity=hs.SITU_OUTER_ID)
    result, details = [], []
    for row in wall_rows():
        name = f"a{row - 1:02d}{fields.variant(situ, row - 1)}.iff"
        before = target.get(name)
        after, proof = walls.apply(before, row)
        require(proof['written'], f'row {row} walls already applied; prepare requires the original candidate')
        again, second = walls.apply(after, row)
        require(again == after and second['already_applied'], f'row {row} replay changed bytes')
        result += _entry_edits(disc, target, name, None, before, after, proof['stadium_offset'],
                               proof['stadium_size'], f'{name} stadium')
        details.append(dict(kind='walls', row=row, name=name, before_sha256=sha(before), after_sha256=sha(after),
                            stadium_offset=proof['stadium_offset'], stadium_size=proof['stadium_size'],
                            textures=len(proof['textures']), replay_written_bytes=0,
                            studio_transform='nfl2k5_super_bowl_walls.apply'))
        print(f'prepared walls row {row:02d} {name}', flush=True)
    outer = target.get(identity=ball.GLOBAL_ID)
    after, proof = ball.apply_global(outer)
    require(proof['written'], 'the ball is already applied; prepare requires the original candidate')
    require(ball.apply_global(after)[0] == after, 'ball replay changed bytes')
    result += _entry_edits(disc, target, None, ball.GLOBAL_ID, outer, after, proof['ball_offset'], proof['ball_size'],
                           'global.iff ball')
    details.append(dict(kind='ball', before_sha256=sha(outer), after_sha256=sha(after), replay_written_bytes=0,
                        studio_transform='nfl2k5_era_ball.apply_global',
                        **{k: proof[k] for k in ('ball_offset', 'ball_size', 'palette_entries', 'modern_mean_abs_error',
                                                 'disc_ball_mean_abs_error', 'old_ball_rows')}))
    with path.open('rb') as stream:
        from mod_editor.core import nfl2k5_espn25_rosters as rosters
        xbe_at, xbe = rosters._image_xbe(stream)
    require(venues.status(xbe) == 'previous', 'the executable is not the v0.6.1 moment-venue owner')
    new_xbe, receipt = venues.apply(xbe)
    require(venues.status(new_xbe) == 'applied' and venues.apply(new_xbe)[1]['status'] == 'already_applied',
            'moment-venue replay changed bytes')
    runs = xbe_runs(xbe, new_xbe)
    for lo, hi in runs:
        result.append(dict(offset=xbe_at + lo, length=hi - lo, data=new_xbe[lo:hi], before=xbe[lo:hi],
                           name=f'default.xbe +{lo:#x}'))
    details.append(dict(kind='executable', before_sha256=sha(xbe), after_sha256=sha(new_xbe), runs=len(runs),
                        changed_bytes=receipt['changed_bytes'], replay_written_bytes=0,
                        studio_transform='nfl2k5_moment_venues.apply'))
    result.sort(key=lambda p: p['offset'])
    require(all(a['offset'] + a['length'] <= b['offset'] for a, b in zip(result, result[1:])), 'overlapping spans')
    return result, details


def overlay(raw, at, edits):
    out = bytearray(raw)
    for p in edits:
        lo, hi = max(at, p['offset']), min(at + len(raw), p['offset'] + p['length'])
        if lo < hi:
            out[lo - at:hi - at] = p['data'][lo - p['offset']:hi - p['offset']]
    return bytes(out)


def virtual_hashes(disc, plans):
    """{label: (sha256, changed bytes)} of the disc with each list of edits overlaid, in one read pass."""
    digests = {label: hashlib.sha256() for label in plans}
    changed = dict.fromkeys(plans, 0)
    for at in range(0, disc.image_size, BLOCK):
        raw = disc.read(min(BLOCK, disc.image_size - at), at)
        for label, edits in plans.items():
            out = overlay(raw, at, edits)
            if out != raw:
                changed[label] += sum(a != b for a, b in zip(raw, out))
            digests[label].update(out)
    return {label: (digests[label].hexdigest(), changed[label]) for label in plans}


def prepare(path, out):
    require(archive.file_hash(path) == BASE_SHA, 'unknown input disc SHA-256')
    mo2 = json.loads(MO2_PINS.read_text())
    require(mo2['input_sha256'] == BASE_SHA, 'mo2 pins are for another base')
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'tools'))
    from b77 import mo2_repair
    with archive.Disc(path, descriptors=()) as disc:
        edits, details = patches(path, disc)
        mo2_edits, _ = mo2_repair.patches(disc)
        for p in edits:
            require(not any(p['offset'] < m['offset'] + m['length'] and m['offset'] < p['offset'] + p['length']
                            for m in mo2_edits), 'me1 and mo2 spans overlap')
        hashes = virtual_hashes(disc, dict(me1=edits, mo2=mo2_edits,
                                           mo2_me1=sorted(mo2_edits + edits, key=lambda p: p['offset'])))
        require(hashes['mo2'][0] == mo2['output_sha256'], 'mo2 spans do not reproduce the pinned mo2 output')
        pins = dict(schema='b773/me1/v1', size=disc.image_size, spans=[],
                    inputs={BASE_SHA: hashes['me1'][0], mo2['output_sha256']: hashes['mo2_me1'][0]})
        for i, p in enumerate(edits):
            filename = f'{i:03d}.span'
            (out / filename).write_bytes(p['data'])
            pins['spans'].append(dict(offset=p['offset'], length=p['length'], file=filename, name=p['name'],
                                      before_sha256=sha(p['before']), after_sha256=sha(p['data'])))
    write_json(out / 'pins.json', pins)
    report = dict(kind='read_only_virtual_disc_and_extracted_spans', physical_disc_written=False,
                  input_sha256=BASE_SHA, virtual_output_sha256=hashes['me1'][0],
                  virtual_changed_bytes=hashes['me1'][1], after_mo2_input_sha256=mo2['output_sha256'],
                  after_mo2_virtual_output_sha256=hashes['mo2_me1'][0], spans=len(edits),
                  span_bytes=sum(p['length'] for p in edits), virtual_changed_outside_spans=0,
                  replay_written_bytes=0, studio_transform_shared=True, resources=details)
    write_json(out / 'receipt.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'resources'}, sort_keys=True))


def load_plan(folder):
    pins = json.loads(PINS.read_text())
    require(json.loads((folder / 'pins.json').read_text()) == pins, 'plan differs from shipped pins')
    require(BASE_SHA in pins['inputs'], 'unknown plan base')
    edits = []
    for p in pins['spans']:
        data = (folder / p['file']).read_bytes()
        require(len(data) == p['length'] and sha(data) == p['after_sha256'], 'payload hash mismatch')
        edits.append(dict(p, data=data))
    return pins, edits


def apply(path, folder, receipt):
    require(not path.is_symlink(), 'disc copy is a symlink')
    pins, edits = load_plan(folder)
    current = archive.file_hash(path)
    outputs = set(pins['inputs'].values())
    require(current in pins['inputs'] or current in outputs, 'unknown input disc SHA-256')
    require(path.stat().st_size == pins['size'], 'disc length mismatch')
    written = 0
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        require(archive.digest(lambda n, at: io.pread(fd, n, at), pins['size']) == current, 'disc changed before write')
        for p in edits:
            expected = p['after_sha256'] if current in outputs else p['before_sha256']
            require(sha(io.pread(fd, p['length'], p['offset'])) == expected, 'span identity mismatch')
        output = current if current in outputs else pins['inputs'][current]
        if current not in outputs:
            for p in edits:
                archive.write_all(fd, p['data'], p['offset'])
                written += p['length']
            os.fsync(fd)
        require(archive.digest(lambda n, at: io.pread(fd, n, at), pins['size']) == output, 'output hash mismatch')
    finally:
        os.close(fd)
    result = dict(kind='physical_disc_write', written_bytes=written, input_sha256=current, output_sha256=output)
    write_json(receipt, result)
    print(json.dumps(result, sort_keys=True))


def scope(before, after, receipt):
    pins = json.loads(PINS.read_text())
    original = archive.file_hash(before)
    require(original in pins['inputs'], 'unknown original disc')
    require(archive.file_hash(after) == pins['inputs'][original], 'unknown repaired disc')
    changed = outside = 0
    with before.open('rb') as a, after.open('rb') as b:
        at = 0
        while raw := a.read(BLOCK):
            actual = b.read(len(raw))
            require(len(actual) == len(raw), 'short repaired disc')
            if actual != raw:
                for i, (x, y) in enumerate(zip(raw, actual)):
                    if x != y:
                        changed += 1
                        outside += not any(p['offset'] <= at + i < p['offset'] + p['length'] for p in pins['spans'])
            at += len(raw)
        require(not b.read(1), 'repaired disc grew')
    require(outside == 0, 'out-of-scope change')
    result = dict(kind='physical_full_disc_compare', changed_bytes=changed, changed_outside_spans=outside)
    write_json(receipt, result)
    print(json.dumps(result, sort_keys=True))


def studio(path, retail, receipt):
    """The Studio's alias compiler output, compared texture by texture with the repaired stadium scenes."""
    from mod_editor.core import nfl2k5_modern_metlife as mm
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv

    def stadium(bundle):
        chunk, _, _ = walls._stadium_chunk(bundle)
        return mm.scene_span(bundle, chunk)

    require(archive.file_hash(path) == BASE_SHA, 'unknown input disc SHA-256')
    with hs.Source(path) as built, hs.Source(retail) as source:
        situ, _ = fields.repair_situ(built.get(identity=hs.SITU_OUTER_ID))
        compiled, _ = fields.compile_assets(built.get, source.get, situ)
        catalog = {r['row']: r for r in fields.catalog()}
        rows = []
        for row in wall_rows():
            code = fields.variant(situ, row - 1)
            name = f"a{row - 1:02d}{code}.iff"
            before = built.get(name)
            after, proof = walls.apply(before, row)
            spec = catalog[row]
            donor = (built.get if spec['source_kind'] == 'built' else source.get)(spec['source_prefix'] + code + '.iff')
            studio_scene, repair_scene = stadium(compiled[name]), stadium(after)
            listed = [t['material'] for t in proof['textures']]

            def by_material(bundle):
                _, rec, decoded = walls._stadium_chunk(bundle)
                index = mv.rows_by_material(rec)
                return {m: walls.texture_bytes(decoded, rec, [index[m]])[str(index[m])] for m in listed}

            studio_t, repair_t = by_material(compiled[name]), by_material(after)
            alias_t, donor_t = by_material(before), by_material(donor)
            differing = sorted(m for m in listed if studio_t[m] != repair_t[m])
            drift = sorted(m for m in listed if alias_t[m] != donor_t[m])
            rows.append(dict(row=row, name=name, stadium_span_equal=studio_scene == repair_scene,
                             wall_textures_equal=not differing, wall_textures=len(listed),
                             differing_wall_textures=differing, donor_drift_wall_textures=drift,
                             explained_by_donor_drift=set(differing) <= set(drift),
                             studio_stadium_sha256=sha(studio_scene), repair_stadium_sha256=sha(repair_scene)))
    result = dict(kind='studio_wall_comparison', physical_disc_written=False, bundles=len(rows),
                  equal_stadium_spans=sum(r['stadium_span_equal'] for r in rows),
                  equal_wall_textures=sum(r['wall_textures_equal'] for r in rows),
                  donor_drift_rows=[r['row'] for r in rows if not r['wall_textures_equal']], resources=rows)
    write_json(receipt, result)
    require(all(r['explained_by_donor_drift'] for r in rows),
            'Studio wall output differs beyond the disc\'s own donor drift; see receipt')
    print(json.dumps({k: v for k, v in result.items() if k != 'resources'}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--disc', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('apply')
    p.add_argument('--disc-copy', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p = sub.add_parser('scope')
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p = sub.add_parser('studio')
    p.add_argument('--disc', type=Path, required=True)
    p.add_argument('--retail', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = parser.parse_args()
    if a.command == 'prepare':
        prepare(a.disc, a.out)
    elif a.command == 'apply':
        apply(a.disc_copy, a.plan, a.receipt)
    elif a.command == 'scope':
        scope(a.before, a.after, a.receipt)
    else:
        studio(a.disc, a.retail, a.receipt)


if __name__ == '__main__':
    main()

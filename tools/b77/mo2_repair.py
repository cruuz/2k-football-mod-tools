#!/usr/bin/env python3
"""Protect Anniversary field bindings on a verified candidate copy.

prepare reads a disc and writes only field spans and receipts to a work folder.
apply writes those same fixed spans to --disc-copy, refusing unknown whole-disc
hashes. scope compares two actual discs. prepare also hashes a virtual repaired
disc without making a disc copy; that receipt is explicitly not a physical write.
studio compares all 51 compiled bundles with the repair, without a disc copy.
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
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import platform_compat as io

BASE_SHA = '520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4'
PINS = Path(__file__).with_name('mo2_pins.json')
BLOCK = 4 * 1024 * 1024


def write_json(path, doc):
    with Path(path).open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(doc, stream, indent=2, sort_keys=True)
        stream.write('\n')


def require(ok, reason):
    if not ok:
        raise ValueError('mo2 refused: ' + reason)


def patches(disc):
    target = hs.Target(disc)
    situ = target.get(identity=hs.SITU_OUTER_ID)
    result, details = [], []
    for row in fields.catalog():
        if row['row'] in fields.PRESERVED_RETAIL_ROWS:
            continue
        name = f"a{row['row']-1:02d}{fields.variant(situ,row['row']-1)}.iff"
        before = target.get(name)
        after, proof = fields.protect_period_field(before)
        require(not proof['already_applied'], 'prepare requires the original candidate')
        start, size = proof['field_offset'], proof['field_size']
        entry = disc.archive_entries[target.outer(name)]
        spans = disc.entry_spans(entry, start, size)
        cursor = start
        for span in spans:
            data = after[cursor:cursor + span.length]
            result.append(dict(offset=span.xiso_offset, length=span.length, data=data,
                               before=before[cursor:cursor + span.length], name=name))
            cursor += span.length
        replay, again = fields.protect_period_field(after)
        require(replay == after and again['decoded_changed_bytes'] == 0, 'replay changed bytes')
        details.append(dict(row=row['row'], name=name, before_sha256=fields.sha(before),
                            after_sha256=fields.sha(after), replay_written_bytes=0,
                            studio_transform='nfl2k5_espn25_fields.protect_period_field', **proof))
        print(f"prepared row {row['row']:02d} {name}", flush=True)
    result.sort(key=lambda p: p['offset'])
    require(all(a['offset'] + a['length'] <= b['offset'] for a,b in zip(result,result[1:])), 'overlapping spans')
    return result, details


def virtual_hash(disc, edits):
    digest = hashlib.sha256()
    changed = 0
    for at in range(0, disc.image_size, BLOCK):
        raw = disc.read(min(BLOCK, disc.image_size - at), at)
        out = bytearray(raw)
        for p in edits:
            lo, hi = max(at,p['offset']), min(at+len(raw),p['offset']+p['length'])
            if lo < hi:
                out[lo-at:hi-at] = p['data'][lo-p['offset']:hi-p['offset']]
        changed += sum(a != b for a,b in zip(raw,out)) if raw != out else 0
        digest.update(out)
    return digest.hexdigest(), changed


def prepare(path, out):
    require(archive.file_hash(path) == BASE_SHA, 'unknown input disc SHA-256')
    out.mkdir(parents=True, exist_ok=True)
    with archive.Disc(path, descriptors=()) as disc:
        edits, details = patches(disc)
        output_sha, changed = virtual_hash(disc, edits)
        pins = dict(schema='b773/mo2/v1', input_sha256=BASE_SHA, output_sha256=output_sha,
                    size=disc.image_size, spans=[])
        for i,p in enumerate(edits):
            filename = f'{i:02d}.span'
            (out / filename).write_bytes(p['data'])
            pins['spans'].append(dict(offset=p['offset'], length=p['length'], file=filename,
                                      name=p['name'], before_sha256=fields.sha(p['before']),
                                      after_sha256=fields.sha(p['data'])))
    write_json(out/'pins.json', pins)
    report = dict(kind='read_only_virtual_disc_and_extracted_field_spans', physical_disc_written=False,
                  fields=len(details), input_sha256=BASE_SHA, virtual_output_sha256=output_sha,
                  virtual_changed_bytes=changed, virtual_changed_outside_spans=0,
                  replay_written_bytes=0, studio_transform_shared=True, resources=details)
    write_json(out/'receipt.json', report)
    print(json.dumps({k:v for k,v in report.items() if k!='resources'},sort_keys=True))


def load_plan(folder):
    pins = json.loads(PINS.read_text())
    require(json.loads((folder/'pins.json').read_text()) == pins, 'plan differs from shipped pins')
    require(pins['input_sha256'] == BASE_SHA, 'unknown plan base')
    edits = []
    for p in pins['spans']:
        data = (folder/p['file']).read_bytes()
        require(len(data)==p['length'] and fields.sha(data)==p['after_sha256'], 'payload hash mismatch')
        edits.append(dict(p,data=data))
    return pins,edits


def apply(path, folder, receipt):
    require(not path.is_symlink(), 'disc copy is a symlink')
    pins,edits=load_plan(folder)
    current=archive.file_hash(path)
    require(current in (pins['input_sha256'],pins['output_sha256']), 'unknown input disc SHA-256')
    require(path.stat().st_size==pins['size'], 'disc length mismatch')
    written=0
    fd=os.open(path,os.O_RDWR|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    try:
        require(archive.digest(lambda n,at:io.pread(fd,n,at),pins['size'])==current, 'disc changed before write')
        for p in edits:
            expected=p['before_sha256'] if current==pins['input_sha256'] else p['after_sha256']
            require(fields.sha(io.pread(fd,p['length'],p['offset']))==expected, 'span identity mismatch')
        if current!=pins['output_sha256']:
            for p in edits:
                archive.write_all(fd,p['data'],p['offset']);written+=p['length']
            os.fsync(fd)
        require(archive.digest(lambda n,at:io.pread(fd,n,at),pins['size'])==pins['output_sha256'], 'output hash mismatch')
    finally:
        os.close(fd)
    result=dict(kind='physical_disc_write',written_bytes=written,output_sha256=pins['output_sha256'])
    write_json(receipt,result);print(json.dumps(result,sort_keys=True))


def scope(before, after, receipt):
    pins=json.loads(PINS.read_text())
    require(archive.file_hash(before)==pins['input_sha256'], 'unknown original disc')
    require(archive.file_hash(after)==pins['output_sha256'], 'unknown repaired disc')
    changed=outside=0
    with before.open('rb') as a,after.open('rb') as b:
        at=0
        while raw:=a.read(BLOCK):
            actual=b.read(len(raw)); require(len(actual)==len(raw),'short repaired disc')
            if actual!=raw:
                for i,(x,y) in enumerate(zip(raw,actual)):
                    if x!=y:
                        changed+=1
                        outside+=not any(p['offset']<=at+i<p['offset']+p['length'] for p in pins['spans'])
            at+=len(raw)
        require(not b.read(1),'repaired disc grew')
    require(outside==0,'out-of-scope change')
    result=dict(kind='physical_full_disc_compare',changed_bytes=changed,changed_outside_spans=outside)
    write_json(receipt,result);print(json.dumps(result,sort_keys=True))


def studio(path, retail, receipt):
    require(archive.file_hash(path) == BASE_SHA, 'unknown input disc SHA-256')
    with hs.Source(path) as built, hs.Source(retail) as source:
        situ, _ = fields.repair_situ(built.get(identity=hs.SITU_OUTER_ID))
        compiled, _ = fields.compile_assets(built.get, source.get, situ)
        rows = []
        for row in fields.catalog():
            name = f"a{row['row']-1:02d}{fields.variant(situ,row['row']-1)}.iff"
            before = built.get(name)
            after = (before if row['row'] in fields.PRESERVED_RETAIL_ROWS else
                     fields.protect_period_field(before)[0])
            rows.append(dict(row=row['row'], name=name, byte_equal=compiled[name] == after,
                             studio_sha256=fields.sha(compiled[name]), repair_sha256=fields.sha(after)))
    result = dict(kind='studio_bundle_comparison', physical_disc_written=False,
                  bundles=len(rows), byte_equal=sum(row['byte_equal'] for row in rows), resources=rows)
    write_json(receipt, result)
    require(result['byte_equal'] == result['bundles'], 'Studio output differs; see receipt')
    print(json.dumps({k:v for k,v in result.items() if k != 'resources'}, sort_keys=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--disc',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('apply');p.add_argument('--disc-copy',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p=sub.add_parser('scope');p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p=sub.add_parser('studio');p.add_argument('--disc',type=Path,required=True);p.add_argument('--retail',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='prepare':prepare(a.disc,a.out)
    elif a.command=='apply':apply(a.disc_copy,a.plan,a.receipt)
    elif a.command=='scope':scope(a.before,a.after,a.receipt)
    else:studio(a.disc,a.retail,a.receipt)


if __name__=='__main__':main()

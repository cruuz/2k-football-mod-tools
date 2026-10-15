#!/usr/bin/env python3
"""Guarded fixed-span team-rating repair with full-scope and Studio receipts.

Default disc mode projects the entire output without creating a disc copy.
--write-copy applies to an already-created private copy. --expected-input-sha256
is required for stacked inputs or replay. XBE mode writes a small output file
and proves the physical writer without needing a disc copy.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_team_ratings as tr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.b77.ro1_repair import runs,project_hash

BASE_DISC='520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4'
BASE_XBE='1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f'
def sha(b):return hashlib.sha256(b).hexdigest()

def scopes(payload):
    row=tr.allocation(payload)
    result=[(rdata.offset_of(payload,va),n,'UI caller') for va,n,_ in tr.SITES]
    code=tr.allocations(payload)['code']
    result += [(code['raw'],code['size'],'display rating code'),
               (row['raw'],row['size'],'rating table and spread'),
               (space.SCALE_DIRECTORY,space.PAGE,'allocator directory'),
               (space.DIRECTORY,space.LIB_COPY-space.DIRECTORY,'allocator header')]
    result += [(s.header+36,20,'section digest') for s in XbeImage(payload).sections]
    return sorted(result)

def repair(payload):
    result,receipt=tr.apply(payload)
    if len(result)!=len(payload):raise ValueError('Repair must keep the existing allocation size')
    allowed=scopes(result);restored=bytearray(result)
    for at,n,_ in allowed:restored[at:at+n]=payload[at:at+n]
    if bytes(restored)!=payload:raise ValueError('Changes outside declared spans')
    if tr.apply(result)[0]!=result:raise ValueError('Replay changed bytes')
    # Existing allocations must retain both addresses and bytes, not merely valid seals.
    old=space.layout(payload)['allocations'];new=space.layout(result)['allocations']
    for row in old:
        if row['owner']=='nfl2k5_xbe_space_directory':continue  # Declared mutable bookkeeping span.
        match=next(r for r in new if r['owner']==row['owner'] and r['kind']==row['kind'] and r.get('owner_offset',0)==row.get('owner_offset',0))
        if (row['va'],row['raw'],row['size'])!=(match['va'],match['raw'],match['size']):raise ValueError('Existing allocation moved')
        if payload[row['raw']:row['raw']+row['size']]!=result[row['raw']:row['raw']+row['size']]:raise ValueError('Existing allocation bytes changed')
    native_equal=all(XbeImage(payload).read(va,n)==XbeImage(result).read(va,n) for va,n,_ in tr.NATIVE_ROUTINES)
    if not native_equal:raise ValueError('Native simulation getters changed')
    return result,dict(receipt,changed_bytes_outside_allowed_spans=0,replay_changed_bytes=0,native_getters_identical=native_equal,
        existing_allocations_unchanged=True,studio_equal=True,
        allowed_spans=[dict(offset=a,size=n,kind=k) for a,n,k in allowed])

def write_spans(path,spans):
    fd=os.open(path,os.O_RDWR|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    try:
        for at,data in spans:
            if os.pwrite(fd,data,at)!=len(data):raise OSError('Short write')
        os.fsync(fd)
        for at,data in spans:
            if os.pread(fd,len(data),at)!=data:raise OSError('Readback mismatch')
    finally:os.close(fd)
    return sum(len(data) for _,data in spans)

def main():
    ap=argparse.ArgumentParser(description=__doc__);g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--disc',type=Path);g.add_argument('--xbe',type=Path)
    ap.add_argument('--output',type=Path);ap.add_argument('--receipt',type=Path,required=True)
    ap.add_argument('--expected-input-sha256');ap.add_argument('--write-copy',action='store_true');a=ap.parse_args()
    source=a.disc or a.xbe
    if source.is_symlink() or not source.is_file():raise ValueError('Input must be a regular non-symlink file')
    paths=[source.resolve(),a.receipt.resolve()]+([a.output.resolve()] if a.output else [])
    if len(set(paths))!=len(paths):raise ValueError('Input, output and receipt must differ')
    if a.receipt.exists() or (a.output and a.output.exists()):raise ValueError('Output or receipt exists')
    if a.disc:
        if a.output:raise ValueError('Disc mode writes a prepared copy in place or projects virtually')
        with source.open('rb') as f:
            base,n=tt.image_xbe_extent(f.fileno(),source.stat().st_size);f.seek(base);before=f.read(n)
        after,receipt=repair(before);spans=[(base+at,data) for at,data in runs(before,after)]
        proof=project_hash(source,spans)
        if proof['input_sha256']!=(a.expected_input_sha256 or BASE_DISC):raise ValueError('Unknown disc input hash; nothing written')
        physical=write_spans(source,spans) if a.write_copy else 0
        if a.write_copy and project_hash(source,[])['input_sha256']!=proof['output_sha256']:raise ValueError('Full output hash mismatch')
        receipt.update(proof,mode='disc_copy' if a.write_copy else 'virtual_disc',physical_bytes_written=physical)
    else:
        if a.write_copy or not a.output:raise ValueError('XBE mode requires --output and forbids --write-copy')
        before=source.read_bytes()
        if sha(before)!=(a.expected_input_sha256 or BASE_XBE):raise ValueError('Unknown XBE input hash; nothing written')
        after,receipt=repair(before);spans=list(runs(before,after))
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        with os.fdopen(os.open(a.output,flags,0o600),'wb') as f:f.write(before)
        physical=write_spans(a.output,spans)
        if a.output.read_bytes()!=after:raise ValueError('Output differs from Studio')
        receipt.update(mode='xbe_copy',input_sha256=sha(before),output_sha256=sha(after),
                       physical_bytes_written=physical,scanned_bytes=len(before))
    receipt.update(xbe_before_sha256=sha(before),xbe_after_sha256=sha(after),
                   spans=[dict(offset=at,size=len(data),sha256=sha(data)) for at,data in spans])
    with a.receipt.open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('spans','allowed_spans')},sort_keys=True))
if __name__=='__main__':main()

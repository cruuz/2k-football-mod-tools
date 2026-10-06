#!/usr/bin/env python3
"""Repair only f1's dated FA membership/records/appearance in v0.4 ROST.

Input: a bare ROST body or extracted vc_53450030/0 (never an ISO).
Unknown hashes refuse. A coordinator may explicitly approve an exact composed
input hash with --approved-input-sha256; this is logged in the scope receipt.
Every other byte/bit is proved identical before output is written. No XBE or
texture write. Apply c1 commentary normalization after this writer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_free_agents as fa

BODY_SIZE=0x90F60
PACK_SIZE=194072576
ROST_OFFSET=0x393000
BODY_OFFSET=ROST_OFFSET+0x20
BODY_BEFORE='a10aadd7f7968ef5334eb029109b199db954c7cfdd305229d24ea36beb711bb0'
BODY_AFTER='7aba399a889d4298959807793e4c04cdda510d07bf418d8d6b9add021e1c61a0'
PACK_BEFORE='01e4e49d47dcc41fb54a3c0404fb988df9fe842bf7efdd46288a50190b233e21'
PACK_AFTER='6caa32dcc80e012820adfca204e437a8d6319736c75898bad1f47c21fb8f2168'  # filled from the deterministic native scope receipt


def sha(raw):return hashlib.sha256(raw).hexdigest()


def _changed_ranges(before,after,base=0):
    ranges=[];start=None
    for i,(a,b) in enumerate(zip(before,after)):
        if a!=b and start is None:start=i
        if a==b and start is not None:ranges.append([base+start,base+i]);start=None
    if start is not None:ranges.append([base+start,base+len(before)])
    return ranges


def prove_scope(before,after,plan):
    if len(before)!=BODY_SIZE or len(after)!=BODY_SIZE:raise ValueError('ROST geometry differs.')
    a=rr.RosterDocument(before,scheme='one_pool',reference_year=2026)
    b=rr.RosterDocument(after,scheme='one_pool',reference_year=2026)
    by={(p.pool,p.index):p for p in a.players};allowed=bytearray(BODY_SIZE)
    # Existing six-field appearance ownership; adjacent biography/equipment bits remain exact.
    masks={0x06:0xff,0x07:0xff,0x0c:0x80,0x18:0x99,0x19:0x0f,0x22:0x1e}
    for row in plan['existing']:
        p=by[(row.get('pool','primary'),row['index'])]
        for off,mask in masks.items():allowed[p.offset+off]|=mask
    newkeys={(r.get('pool','primary'),r['index']) for r in plan['added']}
    for key in newkeys:
        p=by[key];allowed[p.offset:p.offset+rr.PLAYER_SIZE]=b'\xff'*rr.PLAYER_SIZE
    countoff=a.obj_base+rr.FREE_AGENT_COUNT_FIELD
    allowed[countoff:countoff+4]=b'\xff'*4
    span=max(len(a.free_agents),len(b.free_agents))*4
    allowed[a.free_agent_list:a.free_agent_list+span]=b'\xff'*span
    allowed[a.names.start:a.names.end]=b'\xff'*(a.names.end-a.names.start)
    escaped=[i for i,(x,y,m) in enumerate(zip(before,after,allowed)) if (x^y)&~m]
    if escaped:raise ValueError(f'Write escaped f1 bit scope at {escaped[:10]}.')
    # The name allocator may use gaps/release create-player strings, never alter
    # a shared string still selected by an unrelated player.
    afterby={(p.pool,p.index):p for p in b.players}
    for key,p in by.items():
        if key not in newkeys and (p.first,p.last)!=(afterby[key].first,afterby[key].last):
            raise ValueError(f'Unrelated name changed: {key}.')
    if any(t.slots!=u.slots for t,u in zip(a.teams,b.teams)) or a.reserves!=b.reserves:
        raise ValueError('Team/reserve membership changed.')
    for p in a.players:
        if p.pool=='primary' and 1944<=p.index<2324:
            q=afterby[(p.pool,p.index)]
            if before[p.offset:p.offset+84]!=after[q.offset:q.offset+84]:raise ValueError('Draft record changed.')
    outside_before=bytes(x&~m for x,m in zip(before,allowed))
    outside_after=bytes(x&~m for x,m in zip(after,allowed))
    return dict(outside_scope_identical=outside_before==outside_after,
                outside_scope_masked_sha256=sha(outside_before),
                existing_appearance_byte_masks={hex(k):hex(v) for k,v in masks.items()},
                existing_appearance_record_offsets=[by[(r.get('pool','primary'),r['index'])].offset for r in plan['existing']],
                new_record_spans=[[by[k].offset,by[k].offset+84] for k in sorted(newkeys)],
                fa_count_span=[countoff,countoff+4],fa_pointer_span=[a.free_agent_list,a.free_agent_list+span],
                allocated_names_span=[a.names.start,a.names.end],unrelated_names_identical=True,
                draft_380_records_identical=True,team_and_reserve_membership_identical=True,
                changed_body_ranges=_changed_ranges(before,after),changed_bytes=sum(x!=y for x,y in zip(before,after)))


def repair_body(body,*,approved_input_sha256=()):
    digest=sha(body)
    if digest not in {BODY_BEFORE,BODY_AFTER,*approved_input_sha256}:raise ValueError('Unexpected ROST SHA-256; input left untouched.')
    plan=fa.load_data();after,receipt=fa.apply_body(body,plan)
    receipt['scope']=prove_scope(body,after,plan)
    receipt['approved_composed_input']=digest not in (BODY_BEFORE,BODY_AFTER)
    receipt['data_sha256']=sha(fa.DEFAULT_DATA.read_bytes())
    return after,receipt


def repair_file(payload,*,approved_input_sha256=()):
    digest=sha(payload)
    if len(payload)==BODY_SIZE:return repair_body(payload,approved_input_sha256=approved_input_sha256)
    if len(payload)!=PACK_SIZE or payload[ROST_OFFSET:ROST_OFFSET+4]!=b'ROST':raise ValueError('Input must be the audited ROST body or extracted pack0.')
    if digest not in {PACK_BEFORE,PACK_AFTER,*approved_input_sha256}:raise ValueError('Unexpected pack0 SHA-256; input left untouched.')
    body=payload[BODY_OFFSET:BODY_OFFSET+BODY_SIZE]
    after,receipt=repair_body(body,approved_input_sha256=(sha(body),))
    result=payload[:BODY_OFFSET]+after+payload[BODY_OFFSET+BODY_SIZE:]
    assert result[:BODY_OFFSET]==payload[:BODY_OFFSET] and result[BODY_OFFSET+BODY_SIZE:]==payload[BODY_OFFSET+BODY_SIZE:]
    receipt.update(disc_file='vc_53450030/0',before_file_sha256=digest,after_file_sha256=sha(result),
                   size=len(result),rost_body_pack_span=[BODY_OFFSET,BODY_OFFSET+BODY_SIZE],
                   outside_roster_identical=True,changed_pack_ranges=_changed_ranges(body,after,BODY_OFFSET),
                   approved_composed_input=digest not in (PACK_BEFORE,PACK_AFTER))
    return result,receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--approved-input-sha256',action='append',default=[])
    args=p.parse_args()
    if args.input.resolve()==args.output.resolve():p.error('Output must be a separate scratch file.')
    if args.output.exists() or args.receipt.exists():p.error('Output/receipt already exists; choose fresh paths.')
    for digest in args.approved_input_sha256:
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):p.error('Approval must name an exact lowercase SHA-256.')
    raw,receipt=repair_file(args.input.read_bytes(),approved_input_sha256=args.approved_input_sha256)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(raw);args.receipt.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ('free_agents','by_position','before_sha256','after_sha256')}))

if __name__=='__main__':main()

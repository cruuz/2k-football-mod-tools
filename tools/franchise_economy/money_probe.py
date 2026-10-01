"""PROVED OFFLINE: native currency callbacks and their complete direct-call census.

No renderer, xemu, native return substitution, or fabricated screen image.
The text dump is what the native callbacks write before drawing. Displaying
real units does not make a fitted contract equal its source cash/APY schedule.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_roster, retail_bytes
from tools.franchise_economy.probe import start

FORMATTER = 0x31E580
# PROVED OFFLINE: all relative calls found in the pinned retail instruction
# sections, including adjacent callbacks omitted by the old decompiler index.
CALLS = (0x21c01a,0x21c045,0x21c150,0x21c19d,0x21ca8a,0x21cab5,0x21cbe1,0x21cc0c,
         0x2b9aee,0x2b9b75,0x2b9d29,0x2b9d8a,0x2b9de3,0x2badaa,0x2badfa,0x2c0644,0x2c066d,
         0x319c8f,0x347008,0x3470b5,0x3474d5,0x3475a1,0x3475eb,0x347617,0x347783,0x3477cb,
         0x347e63,0x347ee7,0x348636,0x34a042,0x34a09c,0x34a0ec,0x34a158,0x3624dc,0x362508,
         0x362728,0x3627af,0x36298a,0x362a79,0x362b69,0x362c46,0x363301,0x366429,0x36644c,
         0x366483,0x366517,0x369120,0x36918c,0x3691f8,0x369264,0x36fd3f)


def census(payload):
    image = XbeImage(payload)
    calls, jumps, pointers = [], [], []
    for sec in image.sections:
        if not sec.raw_size:
            continue
        blob = image.read(sec.start, sec.raw_size)
        for offset in range(len(blob) - 4):
            address = sec.start + offset
            if blob[offset:offset+4] == struct.pack('<I', FORMATTER):
                pointers.append(hex(address))
            if sec.start >= 0x420000 or blob[offset] not in (0xe8,0xe9):
                continue
            if address + 5 + struct.unpack_from('<i', blob, offset + 1)[0] == FORMATTER:
                (calls if blob[offset] == 0xe8 else jumps).append(address)
    if tuple(calls) != CALLS or jumps or pointers:
        raise ValueError('currency call graph differs from the reviewed retail census')
    return {'evidence': 'PROVED OFFLINE', 'formatter': hex(FORMATTER),
            'direct_calls': [hex(a) for a in calls], 'tail_jumps': jumps, 'absolute_references': pointers,
            'scope': 'USA XBE direct machine-code calls; renderer layout and external UI scripts are not execution proof',
            'other_currency_format': {'address':'0xea7094', 'callers':['0x32e653','0x32e99a'],
                                      'meaning':'Trivia game scores, separate from franchise dollars; left unchanged'}}


def wide(m, address):
    return bytes(m.uc.mem_read(address, 256)).decode('utf-16-le', 'strict').split('\0')[0]


def dump(body, payload):
    doc = rr.RosterDocument(body)
    allen = next(p for p in doc.players if p.display == 'Josh Allen' and 3 in p.teams)
    m = start(body, payload)
    player = m.ARENA + 0x300 + allen.offset
    team = m.team_base + 3 * 500
    out, row, holder, offer = (m.ARENA + n for n in (0x180000,0x181000,0x182000,0x183000))
    m.call(0x13ec90, ecx=team)
    m.put(0xcc2400, m.get(team + 0x124))
    result = []
    def record(screen, field, address, **kwargs):
        pointer = m.call(address, **kwargs)
        text = wide(m, pointer)
        result.append({'evidence':'PROVED OFFLINE', 'screen':screen, 'field':field,
                       'native_callback':hex(address), 'text':text})
    for address, field in ((0x366410,'League cap'),(0x366440,'Bills payroll'),(0x366460,'Bills cap space')):
        record('Cap screen',field,address,ecx=0)
    m.put(holder, player)
    m.call(0x21c000, ecx=holder, edx=out)
    result.append({'evidence':'PROVED OFFLINE','screen':'Contract summary','field':'Josh Allen fitted remaining contract',
                   'native_callback':'0x21c000','text':wide(m,out)})
    # Native UI list metadata setters execute against a bounded row object.
    m.put(0xaced60,0xffffffff)
    record('Trade / roster list','Josh Allen current cap charge',0x2b9cc0,ecx=player,edx=0,args=(row,))
    record('Trade / roster list','Josh Allen fitted total',0x2b9d40,ecx=player,edx=0,args=(row,))
    record('Trade / roster list','Josh Allen modeled release penalty',0x2b9da0,ecx=player,edx=0,args=(row,))
    record('Re-sign / free-agent list','Josh Allen current base charge',0x3624d0,ecx=player)
    record('Re-sign / free-agent list','Josh Allen generated demand',0x3624f0,ecx=player)
    b = bytes(m.uc.mem_read(player,84))
    value = struct.unpack_from('<H',b,10)[0]
    word = (2 << 26) | ((b[0x26] & 15) << 29) | ((b[0x27] & 15) << 16) | (b[0x26] >> 4)
    m.uc.mem_write(offer,struct.pack('<IIIHH',player,team,word,value,0))
    m.put(0xcb8c34,offer)
    for address, field in ((0x347740,'Annual base charge'),(0x347790,'Annual amortized bonus')):
        m.call(address,edx=0,args=(out,0,0))
        result.append({'evidence':'PROVED OFFLINE','screen':'Negotiation annual schedule','field':field,
                       'native_callback':hex(address),'text':wide(m,out)})
    # Execute the player-card salary-text branch through its native formatter
    # and the native "Salary : %s" composition. Stop before the enclosing
    # switch callback's epilogue, whose frame belongs to the actual renderer.
    m.call(0x3474c8,edi=player,esi=out,stop=0x3474f3)
    result.append({'evidence':'PROVED OFFLINE','screen':'Player card','field':'Salary text branch (fitted total)',
                   'native_callback':'0x3474c8..0x3474f3','text':wide(m,out)})
    vectors=[]
    for units in (0,1,249,250,13750,75300,-1,-25,-75300,655350):
        m.call(FORMATTER,ecx=units,edx=out)
        vectors.append({'game_thousands':units,'real_dollars':units*4000,'text':wide(m,out)})
    return {'evidence':'PROVED OFFLINE','callbacks':result,'vectors':vectors,'substituted_leaves':m.leaves,
            'roster_sha256':hashlib.sha256(body).hexdigest(),'xbe_sha256':hashlib.sha256(payload).hexdigest(),
            'boundary':'Native text output, not a rendered screen. 13,750 is a formatter vector for $55M, not Allen APY read from the fitted record.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--ratings',type=Path)
    ap.add_argument('--fragment',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    body=retail_roster()
    for path in (args.base,args.ratings,args.fragment):
        if path:
            body,receipt=rr.apply_body(body,path)
            if receipt['log']:raise ValueError('input replay discrepancies')
    retail=retail_bytes()
    graph=census(retail)
    payload,_=economy.apply(retail)
    result=dump(body,payload)
    result['call_graph']=graph
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    lines=['PROVED OFFLINE: native money text dumps; no renderer or xemu.']
    lines.extend(f"PROVED OFFLINE: {r['screen']} | {r['field']} | {r['text']}" for r in result['callbacks'])
    lines.append('DESIGN: contract figures are fitted cap liabilities. Original cash/APY is in the source ledger.')
    lines.append('PROVED OFFLINE: formatting vector 13,750 game-thousands -> 55.00m, not an APY callback.')
    args.out.with_suffix('.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':
    main()

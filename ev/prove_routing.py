"""Prove the builder's routing and calendar overlay in memory, without a disc build."""
import importlib.util
import json
import resource
import struct
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
spec=importlib.util.spec_from_file_location('event_tests',ROOT/'tests/mod_editor/test_nfl2k5_event_fields.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
season,calendar=t.season,t.calendar
base=json.loads((ROOT.parent/'setup.json').read_text())['base']
old_source=subprocess.check_output(['git','--git-dir='+str(ROOT.parent/'private.git'),'show',
                                   base+':mod_editor/core/nfl2k5_season_length.py'])
old=type(sys)('mod_editor.core._ev_legacy_season');old.__package__='mod_editor.core'
sys.modules[old.__name__]=old
exec(compile(old_source,'baseline season source','exec'),old.__dict__)
retail=t.XBE.read_bytes();legacy,_=old.apply(retail);checks=[]
before=t.XbeImage(retail)
for sofi in (False,True):
    out,receipt=t.build_route(retail,sofi)
    if not sofi:assert out==legacy
    built,cal_receipt=calendar.apply(out)
    image=t.XbeImage(built)
    table=image.read(season.SB_VENUE_TABLE_VA,20)
    targets=struct.unpack('<5I',table)
    slots=[]
    for target in targets:
        instruction=image.read(target,5)
        assert instruction[0]==0xbd  # mov ebp, UTF-16 stadium key
        ptr=struct.unpack_from('<I',instruction,1)[0]
        slots.append(image.read(ptr,8).decode('utf-16le').rstrip('\0'))
    assert slots==(['s40'] if sofi else ['s44'])+['s42','s43','s41','s44']
    default=image.read(0x1332e8,5);ptr=struct.unpack_from('<I',default,1)[0]
    fallback=image.read(ptr,8).decode('utf-16le').rstrip('\0');assert fallback=='s45'
    assert table[4:]==before.read(season.SB_VENUE_TABLE_VA+4,16)
    assert image.read(0x1332b0,0xa1)==before.read(0x1332b0,0xa1)
    assert calendar.status(built)=='applied' and season.simple_status(built)=='applied'
    checks.append(dict(sofi=sofi,season0_bytes=table[:4].hex(),table_bytes=table.hex(),index_0_to_4=slots,
                       index_5_and_later=fallback,selector_sha256=t.mv.sha(image.read(0x1332b0,0xa1)),
                       later_table_unchanged=True,calendar_status=calendar.status(built),
                       season_status=season.status(built),legacy_exactly_equal=None if sofi else out==legacy,
                       xbe_sha256=t.mv.sha(built),build_receipt=receipt,
                       pro_bowl_skip=image.read(0x2a82ae,5).hex(),pro_bowl_week=image.read(0x133a61,1).hex()))
    print('PROVED OFFLINE',sofi,table.hex(),slots,fallback,flush=True)
assert checks[0]['pro_bowl_skip']==checks[1]['pro_bowl_skip']=='eb22909090'
doc=dict(evidence='PROVED OFFLINE',base=base,retail_sha256=t.mv.sha(retail),checks=checks,
         scope='Actual executable statements selected from mod_build.py plus complete calendar overlay; no other E patches or disc build.',
         peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
(ROOT/'ev/evidence/routing_proof.json').write_text(json.dumps(doc,indent=2)+'\n')

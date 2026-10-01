import sys,json,struct,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_rdata_sites as rd
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
raw=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').read_bytes()
cs=Cs(CS_ARCH_X86,CS_MODE_32)
out=[]
for va,length in [(0x133a30,0x40),(0x1332b0,0xa1),(0x133370,0x81),(0xc4e70,0x46),(0x134040,0x120)]:
 off=rd.offset_of(raw,va)
 out+=['\nSTART '+hex(va),'\n'.join(f'{i.address:08x} {i.mnemonic:8} {i.op_str}'.rstrip() for i in cs.disasm(raw[off:off+length],va))]
path=ROOT.parent/'evidence/event_disassembly.txt';path.write_text('\n'.join(out))
print(path)

for va in [0xe79528,0xe79530,0xe79538,0xe79540,0xe79548,0xe79550,0xe79558,0xe79560,0xe79568]:
 try:
  off=rd.offset_of(raw,va);print(hex(va),raw[off:off+8].hex(),repr(raw[off:off+8]))
 except ValueError as exc: print(hex(va),str(exc))

import nfl_franchise_limit_feasibility as feasibility
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core import nfl2k5_roster_storage as storage
from mod_editor.core import mod_build
recipe_path=Path('/home/noah/Desktop/2K5-8 Editors/ultimate/ULTIMATE_BUILD_RECIPE_2026-09-28_candidate_E.json')
recipe=json.loads(recipe_path.read_text())
effective={**mod_build.PRESETS[recipe['preset']],**recipe['overrides']}
checked=[]
for group in ('calendar','season_length','year'):
 for s in season.group_sites(group):
  off=rd.offset_of(raw,s.va)
  assert raw[off:off+len(s.retail)]==s.retail,(group,s.label)
  if s.label in ('super_bowl_venue_season0','is_super_bowl_week','is_pro_bowl_week','pro_bowl_record_skip','stage_table_postseason_weeks'):
   checked.append(dict(group=group,label=s.label,va=hex(s.va),before=s.retail.hex(),after=s.patched.hex(),note=s.note))
proof=dict(evidence='PROVED OFFLINE',xbe_sha256=hashlib.sha256(raw).hexdigest(),
 recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
 effective={k:effective.get(k) for k in ('season_2026','calendar_engine','modern_sofi','all_stadiums')},
 retail=feasibility.validate_super_bowl_venue_selector(raw,{k:{} for k in ('s40','s42','s43','s41','s44','s45')}),
 checked_season_sites=checked,retail_create_team_ids=list(storage.RETAIL_IDS),expanded_create_team_ids=list(storage.STADIUM_IDS),
 default_2026_sb_mapping=['s44','s42','s43','s41','s44','s45'],
 limitation='Static executable/source inspection only. No Quick Game menu or runtime witnessed.')
(ROOT.parent/'evidence/event_proof.json').write_text(json.dumps(proof,indent=2)+'\n')

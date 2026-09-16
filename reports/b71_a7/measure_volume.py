"""Compile the bounded appended resources and record their exact component sizes."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_resources as r,nfl2k5_scorebug_ingame as scene
index=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
rows=[]
with index.open('rb') as stream:
 rec=scene.RESOURCES['score_buga'];stream.seek(rec['pack_offset']);template=stream.read(rec['span_size'])
 def record(name,spans):
  rows.append(dict(component=name,count=len(spans),bytes=sum(map(len,spans)),individual_bytes=list(map(len,spans)),sha256=[hashlib.sha256(s).hexdigest() for s in spans]))
 record('shared 64x64 team TXTR',[r.mnf_panel_span(template,team,'home') for team in sorted(r.TEAM_LOGOS)])
 record('neutral 32x32 TXTR',[r.mnf_panel_span(template,None,'home')])
 record('painted 256x512 P8 atlas',[r.mnf_atlas_span(template)])
 view=r.PackView.from_fd(stream.fileno(),0,index.stat().st_size)
 clock,quarter=r.clock_font_spans(view)
 record('slot-9 FirstPersonComic FONT 256x256',[clock])
 record('core_bug quarter FONT 128x128',[quarter])
assert [row['bytes'] for row in rows]==[168960,2208,132256,80160,27040]
assert sum(row['bytes'] for row in rows)==410624
assert r.probe_sizes('mnf')==(33,410624,411648)
result=dict(components=rows,total_appended_bytes=410624,sector_aligned_growth=411648,native_heap_bytes_from_s4=414080,saved_from_v3=2944,mib=410624/1048576)
(ROOT/'reports/b71_a7/volume.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

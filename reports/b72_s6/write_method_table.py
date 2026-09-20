"""Readable table of observed live values with source-line provenance."""
from pathlib import Path
import json
import struct

OUT=Path(__file__).resolve().parent
capture=json.loads((OUT/'earlier_hud_draws.json').read_text())
rows={r['name']:r for r in capture['rows']}
a,b=rows['yscore_buga1'],rows['yscore_buga']
setup=capture['first_sprite_array_setup_line']
lines=['# Earlier live HUD method comparison','',
 'This is the 13:55:28 window in the original session trace, not the supplied 13:55:49 sample. Label/score names are inferred from the later RAM descriptor sequence; the logger omitted the actual index values. Line numbers refer to the full trace.log. JSON retains every observed register, complete resident program memory, every observed constant component and its last write line. Missing means unknown.','',
 f'Inferred label: draw {a["id"]}, BEGIN line {a["begin_line"]}. Inferred scores: draw {b["id"]}, BEGIN line {b["begin_line"]}. First sprite vertex-array setup: line {setup}.','',
 '| Method | Label | Scores | Last write line, label / scores | Provenance |','|---|---|---|---|---|']
unknown={f'0x{x:04x}' for x in [0x184,0x188,0x190,0x194,0x198,0x19c,0x1a0,0x200,0x204,0x208,0x20c,0x210,0x214,0x30c,0x37c,0x17bc,0x17c0,0x1d7c]}
for key in sorted(set(a['state'])|set(b['state'])|unknown):
 def cell(row):return f"0x{row['state'][key]:08x}" if key in row['state'] else 'UNKNOWN'
 wa,wb=a['state_writes'].get(key),b['state_writes'].get(key)
 origin='unobserved' if wa is None else 'preceding game state' if wa<setup else 'sprite setup or earlier sprite material'
 lines.append(f'| {key} | {cell(a)} | {cell(b)} | {wa} / {wb} | {origin} |')
lines += ['', 'The provenance names identify when a write occurred relative to the first sprite array setup. They do not prove a CPU call stack. Every value persists until overwritten; CPU shadow caches and host shader uniforms were not dumped. No separate NV097 TFACTOR exists in this stream. All observed stage and final combiner constants are included above.','',
 '| Vertex constant | Label | Scores | Last component write lines, label |','|---|---|---|---|']
for slot in list(range(9))+[27,28,29]:
 def value(row):
  values=[row['vertex_constants'].get(str(slot*4+j)) for j in range(4)]
  return 'UNKNOWN' if None in values else str([round(struct.unpack('<f',struct.pack('<I',v))[0],8) for v in values])
 lines.append(f"| c{slot} | {value(a)} | {value(b)} | {[a['constant_writes'].get(str(slot*4+j)) for j in range(4)]} |")
lines += ['', 'Both observed 13-instruction programs hash to d2f8707d23d3e86d3d0f0e8d097292495c6701df9f51e3dc037dbae7d2d63867, matching s5. Their colour instruction reads c6, not the differing earlier-material c5 values. The atlas state differs from s5 in LOD bias (-1 versus 0). It has only one mip level, so this does not select darker mip bytes.','']
(OUT/'gpu_methods.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
print('Compared draws',a['id'],b['id'],'state differences', {k:[a['state'].get(k),b['state'].get(k)] for k in set(a['state'])|set(b['state']) if a['state'].get(k)!=b['state'].get(k)})

"""Summarize captured method values without inventing preceding frame state."""
from pathlib import Path
import hashlib,json,re,struct,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite import xemu_model,gpu
OUT=Path(__file__).resolve().parent
XEMU=Path('/home/noah/Desktop/2K5-8 Editors/research/xemu_src/xemu/hw/xbox/nv2a')
files=['nv2a_regs.h','pgraph/texture.c','pgraph/swizzle.c','pgraph/glsl/psh.c','pgraph/glsl/vsh-prog.c','pgraph/gl/draw.c','pgraph/gl/texture.c']
source=dict(commit='f9b14039e5bb56ae2d8f028e31e7cc19f13f7e12',files={p:hashlib.sha256((XEMU/p).read_bytes()).hexdigest() for p in files})
(OUT/'xemu_source.json').write_text(json.dumps(source,indent=2)+'\n')
names={int(v,16):n for n,v in re.findall(r'^#   define\s+(NV097_\w+)\s+(0[xX][0-9a-fA-F]+)',(XEMU/'nv2a_regs.h').read_text(),re.M)}
arrays=[(0x260,8,'COMBINER_ALPHA_ICW'),(0xa60,8,'COMBINER_FACTOR0'),(0xa80,8,'COMBINER_FACTOR1'),(0xaa0,8,'COMBINER_ALPHA_OCW'),(0xac0,8,'COMBINER_COLOR_ICW'),(0x1e40,8,'COMBINER_COLOR_OCW'),(0xb00,32,'TRANSFORM_PROGRAM_DATA'),(0xb80,32,'TRANSFORM_CONSTANT_DATA'),(0x1720,16,'VERTEX_ARRAY_OFFSET'),(0x1760,16,'VERTEX_ARRAY_FORMAT'),(0x1e20,2,'SPECULAR_FOG_FACTOR')]
for base,count,name in arrays:
 for i in range(count):names[base+4*i]=name+'['+str(i)+']'
rows={r['name']:r for r in json.loads((OUT/'baseline_gpu_True.json').read_text())['rows']}
a,b=rows['yscore_buga1'],rows['yscore_buga']
lines=['# Captured native GPU method comparison','',
 'Baseline, 16:9. Label is `yscore_buga1`; scores are `yscore_buga`. Values are last emitted values at each draw in the bounded fixture. Missing methods are UNKNOWN, never GPU defaults. Upload ports are streams: the separate `vertex_program` and `vertex_constants` fields are authoritative, not the last value at a port. Full ordered packets are retained in the JSON captures.','',
 '| Offset | NV097 method | Label | Scores |','|---|---|---|---|']
for offset in sorted(set(a['state'])|set(b['state']),key=lambda k:int(k,16)):
 def value(row):return f"`0x{row['state'][offset]:08x}`" if offset in row['state'] else 'UNKNOWN'
 lines.append(f"| `{offset}` | {names.get(int(offset,16),'unnamed')} | {value(a)} | {value(b)} |")
lines += ['', 'Additional inherited state absent from this bounded run:', '',
 '| Offsets | State | Label | Scores |', '|---|---|---|---|',
 '| 0x0184 / 0x0188 / 0x0190..0x01a0 | DMA memory contexts | UNKNOWN | UNKNOWN |',
 '| 0x0200..0x0214 | Surface clips, format, pitch, colour/zeta offsets | UNKNOWN | UNKNOWN |',
 '| 0x02a8 | Fog colour | UNKNOWN, inactive with captured final C0.a=0 | Same |',
 '| 0x02b4 / 0x02c0..0x02fc | Window/scissor clipping | UNKNOWN | UNKNOWN |',
 '| 0x030c | Depth-test enable | UNKNOWN | UNKNOWN |',
 '| 0x037c | Flat/smooth shading | UNKNOWN; uniform quad colours | Same |',
 '| 0x17bc / 0x17c0 | Logic operation enable/op | UNKNOWN | UNKNOWN |',
 '| 0x1d78 / 0x1d7c | Z clip and antialiasing control | UNKNOWN | UNKNOWN |',
 '| 0x1b10 / 0x1b1c / 0x1b24 | Pitch/rectangle/border colour | Not emitted; P8 swizzled, repeat and no border fetch in this draw | Same |',
 '| 0x1b40..0x1bff | Texture stages 1..3 | Not emitted; disabled by stage program 0x1 | Same |',
 '', 'CPU cache invalidation forces the binder to expose its writes. It cannot reconstruct methods issued earlier in a real frame. Physical texture/palette addresses are fixture addresses; matching them is not a capture of live xemu VRAM or its host texture cache.', '']
(OUT/'gpu_methods.md').write_text('\n'.join(lines))
trace=json.loads((OUT/'baseline_gpu_True.json').read_text());pipeline=xemu_model.Pipeline(trace);pipeline.select('yscore_buga1')
probe=[]
for plate in (18,19):
 for alpha in (255,128,64):
  probe.append(dict(plate_luma=plate,white_texel_alpha=alpha,output_rgba=pipeline.fragment((255,255,255,alpha),(255,)*4,(plate,plate,plate,255))))
(OUT/'measured_plate_probe.json').write_text(json.dumps(dict(samples=probe,limitation='Analytical fetch/coverage probes over measured plate luminance, not a screenshot-fitted shader; opaque core remains 255.'),indent=2)+'\n')
(OUT/'gpu_code_pins.json').write_text(json.dumps([dict(start=hex(a),end=hex(b),sha256=h) for a,b,h in gpu.GPU_CODE_PINS],indent=2)+'\n')
print('Wrote GPU method table, source hashes and measured-plate fragment probe')

# Decode every field of the pinned 13-instruction vertex program.
source=(XEMU/'pgraph/glsl/vsh-prog.c').read_text()
fields={n:tuple(map(int,(i,s,k))) for n,i,s,k in re.findall(r'\{\s+FLD_(\w+),\s+(\d+),\s+(\d+),\s+(\d+)\s+\}',source)}
program=a['vertex_program'];decoded=[]
for at in range(0,len(program),4):
 words=program[at:at+4]
 decoded.append({n:(words[i]>>shift)&((1<<bits)-1) for n,(i,shift,bits) in fields.items()})
(OUT/'vertex_program_decode.json').write_text(json.dumps(decoded,indent=2)+'\n')

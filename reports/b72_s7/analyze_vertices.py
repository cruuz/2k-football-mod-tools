"""Job-local evidence recipe, reusing the s3/s5/s6 compiler and raster.

No RAM, retail resource, executable, or texture spans are written to the repo.
The optional removal of the event plate is a counterfactual, not a fixed build.
"""
from pathlib import Path
import copy
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import live, xemu_model
import nfl2k5_scorebug_projection as projection
from PIL import Image, ImageDraw
import numpy as np

OUT = Path(__file__).resolve().parent
CAPTURE = Path('/home/noah/.var/app/app.xemu.xemu/data/xemu/capture/20260919-135300')
EVIDENCE = Path('/home/noah/Desktop/2K5-8 Editors/beta72_evidence')
BASE = 0x01e75900
BASELINE = 'ec5d68d4'
LUMA = np.array([.2126, .7152, .0722])


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounds(points):
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


class Ram:
    def __init__(self):
        self.data = (CAPTURE / 'ram_6.bin').read_bytes()
        # Recover, do not assume, the sole present recursive PDE at slot 768.
        candidates = [p for p in range(0, len(self.data)-4095, 4096)
                      if self.u(p+768*4) & 0xfffff001 == p | 1]
        assert candidates == [0xf000], candidates
        self.directory = candidates[0]
        assert self.u(self.physical(0xa95528)) == BASE + 0x80000100

    def u(self, at):
        return struct.unpack('<I', live.read_ram(self.data, at, 4))[0]

    def physical(self, va):
        if 0x80000000 <= va < 0x84000000:
            return va - 0x80000000  # Xbox direct RAM alias used by the scene.
        pde = self.u(self.directory + (va >> 22)*4)
        if not pde & 1:
            raise ValueError('Nonpresent PDE')
        if pde & 128:
            return (pde & 0xffc00000) + (va & 0x3fffff)
        pte = self.u((pde & 0xfffff000) + ((va >> 12) & 1023)*4)
        if not pte & 1:
            raise ValueError('Nonpresent PTE')
        return (pte & 0xfffff000) + (va & 4095)

    def read(self, va, size):
        result = bytearray()
        while size:
            n = min(size, 4096-(va & 4095))
            result.extend(live.read_ram(self.data, self.physical(va), n))
            va += n
            size -= n
        return bytes(result)


def frame_replay(ram):
    """Execute the dumped FCE70 path, retaining requests at one stated boundary."""
    import unicorn as uc
    from unicorn import x86_const as x
    m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
    m.mem_map(0x80000000, (len(ram.data)+4095) & ~4095)
    m.mem_write(0x80000000, ram.data)
    mapped = 0
    for va in range(0x10000, 0x1600000, 4096):
        try:
            page = ram.read(va, 4096)
        except ValueError:
            continue
        m.mem_map(va, 4096)
        m.mem_write(va, page)
        mapped += 1
    m.mem_map(0x7000000, 0x10000)
    m.mem_write(0x700fff0, struct.pack('<II', 0x700ffe0, 0))
    m.reg_write(x.UC_X86_REG_ESP, 0x700fff0)
    m.mem_write(0xfc9c0, bytes.fromhex('c20400'))
    writes = []

    def written(_m, _access, at, size, value, _data):
        if at == BASE + 0x800005c8:
            writes.append(dict(pc=hex(m.reg_read(x.UC_X86_REG_EIP)), value=hex(value), size=size))

    m.hook_add(uc.UC_HOOK_MEM_WRITE, written)
    m.emu_start(0xfce70, 0x700ffe0, count=500000)
    assert m.reg_read(x.UC_X86_REG_EIP) == 0x700ffe0
    return dict(writes=writes, final_flags=hex(struct.unpack('<I', m.mem_read(BASE+0x800005c8, 4))[0]),
                mapped_low_pages=mapped, directory_candidate=hex(ram.directory),
                boundary='FC9C0 replaced by RET 4 to retain captured request words; dt=0; synthetic stack.',
                limitation='A bounded offline replay. No active CR3 register or same-frame GPU witness was captured.')


def main():
    ram = Ram()
    body = live.read_ram(ram.data, BASE, 20416)
    trace_path = ROOT / 'reports/b72_s6/earlier_hud_draws.json'
    hub_trace = EVIDENCE / 's6_reports/earlier_hud_draws.json'
    trace = json.loads(trace_path.read_text())
    assert hub_trace.read_bytes() == trace_path.read_bytes()
    rows = trace['rows']
    pipeline = xemu_model.Pipeline(dict(rows=rows, fixture_assumptions=[
        'Earlier 13:55:28 method state with later streamed RAM dump.',
        'Indices inferred from RAM descriptors; stock trace omitted their values.',
        'Guest P8 bytes; host cached texture and complete framebuffer history unavailable.']))
    batches = json.loads((ROOT/'reports/b72_s6/ram_scene_batches.json').read_text())['rows']
    assert [(b['material'], b['indices']) for b in batches] == list(projection.submission_batches(body, BASE|0x80000000))
    header = sprite.HEADER.unpack_from(body, sprite.TABLE_OFFSET)
    with tempfile.TemporaryDirectory(prefix='b72-s7-layout-') as temp:
        for name in ('layout.json', 'template.png'):
            Path(temp, name).write_bytes(subprocess.check_output([
                'git', 'show', BASELINE+':data/nfl2k5_scorebug_sprite/'+name], cwd=ROOT))
        compiled = sprite.compile_folder(temp, True)
        assert body[sprite.TABLE_OFFSET:sprite.TABLE_OFFSET+header[6]] == compiled.table
        preview = sprite.NativePreview(folder=temp)
        fixture_geometry, fixture = preview.capture(dict(away='SF', home='BUF', away_score=7,
            home_score=3, clock=300, play_clock=17, quarter=1, down=1, distance=10), True)
        try:
            fixture_body = fixture['live_decoded']
            fixture_materials = fixture_geometry['materials']
        finally:
            fixture['machine'].close()
    fields = []
    for i, spec in enumerate(compiled.spec['fields']):
        values = sprite.FIELD.unpack_from(body, header[3]+i*sprite.FIELD.size)
        tokens = []
        for j in range(values[4]):
            glyph = sprite.GLYPH.unpack_from(body, values[3]+j*sprite.GLYPH.size)
            tokens.append(dict(token=''.join(chr(c) for c in glyph[:4] if c),
                               metrics=list(glyph[4:8]), uv=list(glyph[8:])))
        fields.append(dict(index=i, name=spec['name'], table_address=hex(BASE+header[3]+i*sprite.FIELD.size),
            source_index=values[0], first_vertex=values[1], capacity=values[2], colour=hex(values[5]),
            baseline_colour=spec['colour'], current_colour=sprite.load_layout()[0]['fields'][i]['colour'],
            glyphs=tokens, packed=list(values)))

    # The already decoded, pinned 13-instruction program uses c8 for position
    # scale/bias, c[27+v1..29+v1] for the palette, and c0..3 for projection.
    words = rows[0]['vertex_constants']
    constants = {i: [struct.unpack('<f', struct.pack('<I', words[str(i*4+j)]))[0] for j in range(4)]
                 for i in (0, 1, 2, 3, 8, 27, 28, 29)}
    positions, world = [], []
    for v in range(286):
        q = struct.unpack_from('<3h', body, 0x2660+v*6)
        assert struct.unpack_from('<h', body, 0x2d28+v*10)[0] == 0
        point = [n/(32768 if n < 0 else 32767)*constants[8][3]+constants[8][j] for j,n in enumerate(q)]+[1]
        w = [sum(a*b for a,b in zip(point, constants[j])) for j in (27,28,29)]+[1]
        clip = [sum(a*b for a,b in zip(w, constants[j])) for j in range(4)]
        positions.append([clip[0]/clip[3]-40, clip[1]/clip[3]])
        world.append(w[:3])
    geometry = dict(positions=positions, world_positions=world, materials=[None]*11,
                    draws=[], static_version='live RAM / earlier state')
    for batch in batches:
        mat = batch['material']
        geometry['materials'][mat] = dict(name=batch['name'], address=hex((BASE|0x80000000)+0x1c0+mat*128),
            visible=batch['visible'], texture=hex(batch['material_words'][12]))
    textures, spans, texture_receipts = {}, {}, []
    for row in rows:
        s = row['state']
        w, h = (1 << (s['0x1b04'] >> shift & 15) for shift in (20,24))
        indices = live.read_ram(ram.data, s['0x1b00'], w*h)
        palette = live.read_ram(ram.data, s['0x1b20'] & ~63, 1024)
        tex = xemu_model.p8_texture(indices, palette, w, h)
        key = row['name'].encode()
        receipt = dict(name=row['name'], dimensions=[w,h], offset=hex(s['0x1b00']),
            palette=hex(s['0x1b20'] & ~63), indices_sha256=sha(indices), palette_sha256=sha(palette))
        textures[key] = tex, receipt
        texture_receipts.append(receipt)
    spans = {m['texture']:m['name'].encode() for m in geometry['materials'] if m['visible']}
    pipeline.select('yscore_buga1')
    quads = []
    for cq in compiled.quads:
        first = cq['vertex']
        field = next((f for f in fields if f['first_vertex'] <= first < f['first_vertex']+4*f['capacity']), None)
        vertices = []
        for v in range(first, first+4):
            uv = struct.unpack_from('<2h', body, 0x2d24+v*10)
            vertices.append(dict(index=v, position_s16=list(struct.unpack_from('<3h', body, 0x2660+v*6)),
                position_address=hex(BASE+0x2660+v*6), attribute_address=hex(BASE+0x2d20+v*10),
                diffuse=hex(struct.unpack_from('<I', body, 0x2d20+v*10)[0]), specular=None,
                specular_reason='No stored specular attribute; NV097 v4/v5 arrays disabled (format 0x2), unused by this program.',
                uv_s16=list(uv), uv_normalized=list(pipeline.vertex_uv(uv)), transform_index=0, projected=positions[v]))
        uv_flat = [n for v in vertices for n in v['uv_s16']]
        glyphs = [g['token'] for g in field['glyphs'] if g['uv'] == uv_flat] if field else []
        uv_bounds = bounds([v['uv_normalized'] for v in vertices])
        batch = next(b for b in batches if first in b['indices'])
        dimensions = next((r['dimensions'] for r in texture_receipts if r['name']==batch['name']), [256,512])
        uv_box = [round(uv_bounds[i]*dimensions[i%2]) for i in range(4)]
        same = all(body[0x2660+v*6:0x2660+(v+1)*6] == fixture_body[0x2660+v*6:0x2660+(v+1)*6]
                   and body[0x2d20+v*10:0x2d20+(v+1)*10] == fixture_body[0x2d20+v*10:0x2d20+(v+1)*10]
                   for v in range(first, first+4))
        quads.append(dict(name=cq['name'], first_vertex=first, field_index=field['index'] if field else None,
            field=field['name'] if field else None, glyph_candidates=glyphs, atlas_box=uv_box,
            intended_cells=({'logo':[0,0,64,64]} if cq.get('cell')=='logo' else
                            {k:list(v) for k,v in compiled.cells.items() if list(v)==uv_box}),
            material=batch['name'], visible=batch['visible'],
            alpha_nonzero=any(int(v['diffuse'],16)>>24 for v in vertices),
            projected_box=bounds(positions[first:first+4]), native_fixture_bytes_equal=same, vertices=vertices))
    write('vertices.json', dict(ram_bytes=len(ram.data), ram_sha256=sha(ram.data), physical_base=hex(BASE),
        header=list(header), all_compiled_table_bytes_equal=True, baseline_revision=BASELINE,
        fields=fields, quads=quads, unused_vertices=98, projection_constants=constants,
        texture_receipts=texture_receipts))
    label_box = bounds([p for q in quads if q['field']=='down' and q['alpha_nonzero']
                        for p in positions[q['first_vertex']:q['first_vertex']+4]])
    later = []
    for row in rows[5:]:
        qs = [q for q in quads if q['material']==row['name']]
        later.append(dict(draw=row['id'], name=row['name'], begin_line=row['begin_line'],
            roles=[q['name'] for q in qs], texture=next(r for r in texture_receipts if r['name']==row['name']),
            blend={k:hex(row['state'][k]) for k in ('0x0304','0x0344','0x0348','0x0350')},
            quads=[dict(first_vertex=q['first_vertex'], box=q['projected_box'],
                overlap_area=overlap(label_box,q['projected_box']), diffuse=[v['diffuse'] for v in q['vertices']],
                atlas_box=q['atlas_box']) for q in qs]))
    write('overdraw.json', dict(label_box=label_box, draws_after_label=later,
        overlapping_draws=[r['draw'] for r in later if any(q['overlap_area'] for q in r['quads'])],
        provenance='All three later draws in supplied HUD inventory, not a complete same-frame history.'))

    # Geometric scaling from visible 1138x672 picture rectangle. No RGB gain/bias.
    calibration = dict(size=[1277,760], affine=[1138/640,672/448,39,36-16*672/448])
    shot = Image.open(EVIDENCE/'xemu_capture_0919/shot_6_xemu_window.png').convert('RGB')
    region = (555,631,646,645)  # same explicit interior as s6, not a selected brighter ROI
    results = {}
    images = {'screenshot':shot}
    for mode in ('composite', 'without_hang_counterfactual'):
        g = copy.deepcopy(geometry)
        if mode != 'composite':
            g['materials'][8]['visible'] = False
        # Adapt the existing texture decoder at its input boundary. The renderer,
        # bilinear sampler, blend and fragment equations are unchanged.
        with patch.object(xemu_model, 'texture', lambda key:textures[key]):
            receipt = projection.render_native(body, b'yscore_buga1', [], g, OUT/(mode+'.png'),
                texture_spans=spans, gpu_pipeline=pipeline, calibration=calibration,
                background=Image.new('RGB', (1277,760), '#303030'))
        images[mode] = Image.open(OUT/(mode+'.png')).convert('RGB')
        results[mode] = dict(raster=receipt)
    for name, im in images.items():
        data = np.asarray(im.crop(region), dtype=float) @ LUMA
        results.setdefault(name,{})['label_interior'] = dict(box=list(region), min=float(data.min()),
            mean=float(data.mean()), max=float(data.max()))
    a, b = results['screenshot']['label_interior'], results['composite']['label_interior']
    errors = {k:abs(a[k]-b[k]) for k in ('min','mean','max')}
    results['acceptance'] = dict(absolute_error=errors, within_15=all(v<=15 for v in errors.values()),
        fix_applied=False, cause_specific_writer_proved=False, runtime_witnessed=False,
        limitation='RAM glyphs say play clock 17, screenshot says 19; trace is earlier still. No tone fitting.')
    write('model.json', results)
    sheet = Image.new('RGB',(760,340),'#303030')
    draw = ImageDraw.Draw(sheet)
    for i,(name,label) in enumerate((('screenshot','Supplied screenshot, clock 19'),
             ('composite','Live RAM plus earlier state, clock 17'),
             ('without_hang_counterfactual','Counterfactual: remove hang-time plate; no code fix'))):
        draw.text((4,i*112+2), label, fill='white')
        sheet.paste(images[name].crop((450,615,780,690)).resize((660,90)),(0,i*112+20))
    sheet.save(OUT/'comparison.png')

    events = []
    for i in range(6):
        va = 0xa959c8+i*112
        data = ram.read(va,112)
        material = struct.unpack_from('<I',data,0x44)[0]
        events.append(dict(index=i, record_va=hex(va), physical=hex(ram.physical(va)),
            minimum=struct.unpack_from('<f',data,0x2c)[0], slide=struct.unpack_from('<f',data,0x3c)[0],
            request=struct.unpack_from('<I',data,0x38)[0], binding=struct.unpack_from('<I',data,0x58)[0],
            material=hex(material), flags=hex(struct.unpack('<I',ram.read(material+8,4))[0])))
    write('native_comparison.json',dict(fixture_state=dict(away='SF',home='BUF',away_score=7,home_score=3,
        clock=300,play_clock=17,quarter=1,down=1,distance=10),
        field_vertex_mismatches=[q['name'] for q in quads if q['field'] and not q['native_fixture_bytes_equal']],
        all_quad_mismatches=[q['name'] for q in quads if not q['native_fixture_bytes_equal']],
        live_events=events, fixture_materials=fixture_materials, live_frame_replay=frame_replay(ram)))
    write('inputs.json', [dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
        for p in (CAPTURE/'ram_6.bin', trace_path, hub_trace,
                  EVIDENCE/'xemu_capture_0919/shot_6_xemu_window.png')])
    lines = ['# All 47 live scorebug quads', '',
        'Positions below are packed signed shorts, TL and BR. All four vertices, addresses, normalized UVs, and intended cells are in vertices.json. Colour is ARGB and uniform across each quad. Specular is absent from this vertex format and unused by the program. Offscreen or hidden rows remain listed.', '',
        '| First vertex | Field / role | Glyph | Packed TL / BR | Atlas box | Diffuse | Visible material | Fixture equal |',
        '|---|---|---|---|---|---|---|---|']
    for q in quads:
        v = q['vertices']
        lines.append(f"| {q['first_vertex']} | {q['name']} | {q['glyph_candidates']} | {v[0]['position_s16']} / {v[3]['position_s16']} | {q['atlas_box']} | {v[0]['diffuse']} | {q['visible']} | {q['native_fixture_bytes_equal']} |")
    (OUT/'QUADS.md').write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(quad_count=len(quads), errors=errors, acceptance=results['acceptance']),indent=2))


if __name__ == '__main__':
    main()

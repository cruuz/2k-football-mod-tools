"""Offline retained native sequences and captured-frame visibility replay."""
from pathlib import Path
import contextlib
import copy
import io
import json
import struct
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from reports.b72_s7 import analyze_vertices as prior
from test_nfl2k5_scorebug_down_visibility import Sequence
from tools.scorebug_sprite.native import submission_trace
from PIL import Image, ImageDraw
import numpy as np

OUT = Path(__file__).resolve().parent


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def retained_sequences():
    preview = sprite.NativePreview()
    result = {}
    for wide in (False, True):
        seq = Sequence(preview, wide)
        stages = []
        try:
            for state, latch, count in (('pre_snap', False, 120), ('punt', None, 60),
                    ('pre_snap', False, 120), ('after_play', True, 45),
                    ('pre_snap', False, 80), ('flag', None, 45),
                    ('pre_snap', False, 80), ('fumble', None, 45), ('pre_snap', False, 80)):
                seq.configure(state, latch=latch)
                frames = []
                for _ in range(count):
                    row = seq.step()
                    assert all(e['visible'] == bool(e['binding'] and not e['slide'] <= e['minimum'])
                               for e in row['events'])
                    if state == 'pre_snap' and not any(e['visible'] for e in row['events']):
                        assert row['visible_glyphs'] == 5
                    frames.append(row)
                entered, draw = seq.native_draw()
                submission = submission_trace(seq.capture)
                stages.append(dict(state=state, frames=frames, native_draw_elements=entered,
                                   submitted_materials=submission['rows']))
            result['16:9' if wide else '4:3'] = stages
        finally:
            seq.close()
    write('sequences.json', dict(aspects=result, runtime_witnessed=False,
        boundary='Retained Unicorn machines; native FC9C0 requests, FCE70 slide integration, owner and FC360 draw walk. '
                 'Only gameplay/world query inputs are supplied; no event, slide or material writes between stages.',
        frames_per_aspect=sum(len(s['frames']) for s in stages)))
    write('budgets.json', dict(rx_used=len(owner.code_for(0x6000000, 0x6001000)[0].rstrip(b'\xcc')),
        rx_reserved=owner.CODE_SIZE, rw_reserved=owner.DATA_SIZE,
        aspects={str(k):v['volume'] for k,v in preview.modes.items()}))


def live_visibility():
    import unicorn as uc
    from unicorn import x86_const as x
    ram = prior.Ram()
    m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
    m.mem_map(0x80000000, (len(ram.data) + 4095) & ~4095)
    m.mem_write(0x80000000, ram.data)
    for va in range(0x10000, 0x1600000, 4096):
        try:
            page = ram.read(va, 4096)
        except ValueError:
            continue
        m.mem_map(va, 4096)
        m.mem_write(va, page)
    code, state, caller = 0x6000000, 0x6001000, 0x6001100
    m.mem_map(code, 8192)
    content, labels = owner.code_for(code, state)
    m.mem_write(code, content)
    base = prior.BASE | 0x80000000
    mats = base + 0x1c0
    def get(at):
        return struct.unpack('<I', m.mem_read(at, 4))[0]
    m.mem_write(state, struct.pack('<10I', base + 256, 1,
        get(mats + 3*128 + 0x30), get(mats + 10*128 + 0x30), *([0xff303030]*6)))
    m.mem_write(caller, b'\x68' + struct.pack('<I', state) + b'\xe8' +
        struct.pack('<i', labels['sprite_update'] - caller - 10) + b'\x83\xc4\x04\xc3')
    m.mem_map(0x7000000, 0x10000)
    m.mem_write(0x700fff0, struct.pack('<I', 0x700ffe0))
    m.reg_write(x.UC_X86_REG_ESP, 0x700fff0)
    before = [get(mats + i*128 + 8) for i in range(11)]
    m.emu_start(caller, 0x700ffe0, count=500000)
    assert m.reg_read(x.UC_X86_REG_EIP) == 0x700ffe0
    after = [get(mats + i*128 + 8) for i in range(11)]
    assert [i for i in range(11) if (before[i] ^ after[i]) & 1] == [8]
    assert after[8] & 1
    write('live_owner.json', dict(before_flags=[hex(v) for v in before], after_flags=[hex(v) for v in after],
        runtime_witnessed=False, owner_rx_bytes=len(content),
        boundary='Execute rebuilt sprite_update on captured RAM with relocated owner and synthetic State/stack. '
                 'Only output material visibility feeds the raster; all captured vertices, textures and state stay as s7.'))
    render = prior.projection.render_native
    def fixed_render(body, name, draws, geometry, output, **kwargs):
        if output.stem == 'composite':
            fixed = copy.deepcopy(geometry)
            for i, row in enumerate(fixed['materials']):
                row['visible'] = not bool(after[i] & 1)
            receipt = render(body, name, draws, fixed, OUT / 'fixed_live_composite.png', **kwargs)
            write('fixed_raster.json', receipt)
        return render(body, name, draws, geometry, output, **kwargs)
    # Reuse the unchanged s7 texture/projection adapter in a disposable folder.
    with tempfile.TemporaryDirectory(prefix='b72-s8-live-') as temp:
        with patch.object(prior, 'OUT', Path(temp)), patch.object(prior.projection, 'render_native', fixed_render):
            with contextlib.redirect_stdout(io.StringIO()):
                prior.main()
        original = Image.open(Path(temp) / 'composite.png').convert('RGB')
        fixed = Image.open(OUT / 'fixed_live_composite.png').convert('RGB')
        stats = {}
        for name, image in (('captured_visibility', original), ('fixed_owner_visibility', fixed)):
            pixels = np.asarray(image.crop((555,631,646,645)), dtype=float) @ prior.LUMA
            stats[name] = dict(min=float(pixels.min()), mean=float(pixels.mean()), max=float(pixels.max()))
        assert stats['fixed_owner_visibility']['mean'] > 100
        assert np.any(np.all(np.asarray(fixed.crop((555,631,646,645))) == 255, axis=2))
        write('luminance.json', dict(interior=[555,631,646,645], measurements=stats,
            runtime_witnessed=False, tone_fitting=False,
            limitation='Offline live-data composite. RAM, screenshot and traced state were not synchronized. '
                       'No screenshot tolerance gate is used; Noah confirms the test disc in game.'))
        sheet = Image.new('RGB', (760,230), '#303030')
        draw = ImageDraw.Draw(sheet)
        for i, (im, label) in enumerate(((original, 'Captured visibility: inactive hang-time plate visible'),
                (fixed, 'Fixed owner visibility: offline composite, in-game confirmation pending'))):
            draw.text((4,i*115+2), label, fill='white')
            sheet.paste(im.crop((450,615,780,690)).resize((660,90)), (0,i*115+22))
        sheet.save(OUT / 'comparison.png')


def fixture_renders():
    """Both aspects and both possessions with the preserved s5 team palette."""
    from tools.scorebug_sprite.gpu import capture_state
    from tools.scorebug_sprite.xemu_model import Pipeline
    import math
    preview = sprite.NativePreview()
    sheet = Image.new('RGB', (960,280), '#303030')
    labels = ImageDraw.Draw(sheet)
    results = []
    for index, (wide, possession) in enumerate((w,p) for w in (False,True) for p in ('home','away')):
        state = dict(home='LV', away='DET', down=1, distance=10, possession=possession)
        geometry, capture = preview.capture(state, wide)
        mode = preview.modes[wide]
        try:
            events = [capture['machine'].get(0xa959c8+i*112+0x44) for i in range(2,6)]
            assert all(capture['machine'].get(m+8) & 1 for m in events)
            path = OUT / ('fixture_'+('169' if wide else '43')+'_'+possession+'.png')
            prior.projection.render_native(capture['live_decoded'],mode['atlas'],preview.fonts,
                geometry,path,texture_spans=capture['texture_spans'],
                gpu_pipeline=Pipeline(capture_state(capture)),
                background=Image.new('RGB',(640,480),'#303030'))
            im = Image.open(path).convert('RGB')
            points = [geometry['positions'][q['vertex']+j] for q in mode['compiled'].quads
                      if q['name'].startswith('down:') and
                      struct.unpack_from('<I',capture['live_decoded'],0x2d20+q['vertex']*10)[0]
                      for j in range(4)]
            box = [math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points)),
                   math.ceil(max(p[0] for p in points)), math.ceil(max(p[1] for p in points))]
            luma = np.asarray(im.crop(box),dtype=float) @ prior.LUMA
            assert luma.max() >= 240
            results.append(dict(aspect='16:9' if wide else '4:3', possession=possession,
                team='LV' if possession=='home' else 'DET',label_box=box,
                mean=float(luma.mean()),max=float(luma.max()),all_event_plates_hidden=True))
            x,y = (index%2)*480,(index//2)*140
            labels.text((x+4,y+4),results[-1]['aspect']+' '+results[-1]['team']+
                        ' possession / fixed owner offline model',fill='white')
            sheet.paste(im.crop((70,395,570,455)).resize((475,95)),(x,y+26))
        finally:
            capture['machine'].close()
    sheet.save(OUT/'both_aspects.png')
    write('fixture_renders.json',dict(rows=results,runtime_witnessed=False,
        boundary='Fresh native CPU fixtures and existing fragment model; no in-game capture or calibration claim.'))


if __name__ == '__main__':
    retained_sequences()
    live_visibility()
    fixture_renders()
    print('Retained sequences and rebuilt-owner live-data composite passed.')

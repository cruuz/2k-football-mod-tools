#!/usr/bin/env python3
"""Calibrated v2 witness reconstruction and v3 native forecast, offline only."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebar_v3 as v3
from nfl2k5_scorebug_exact import Build, write_json
import nfl2k5_scorebug_projection as projection
import nfl2k5_scorebug_witness as witness

CASES = {
    'bal_jax_pre_snap': dict(file='ksnip_20260907-165742.png', sha256='1341d1d69d431d93a576a57e481dc1af47b1244ad02905ba55266aa0c1bdeb4a', size=[1132,668], offset=[86,-26],
        identity=dict(away='BAL',home='JAX'), possession='home', quarter=2, game_seconds=88,
        play_seconds=15, down=2, distance_yards=10, visibility_state='pre_snap'),
    'min_nyj_pre_snap': dict(file='ksnip_20260907-170211.png', sha256='64d5aaf5ad3ff5c2e5f2b161875c86191142c9005d9965f4cdb3c9eac22acf77', size=[1142,687], offset=[92,-10],
        identity=dict(away='MIN',home='NYJ'), possession='away', quarter=1, game_seconds=258,
        play_seconds=30, down=3, distance_yards=2, visibility_state='pre_snap'),
    'min_nyj_live': dict(file='ksnip_20260907-170222.png', sha256='377d78995899e414d5b888c80613ff2dc1f281eb8d056593a139cedabf13bf19', size=[1137,681], offset=[89,-12],
        identity=dict(away='MIN',home='NYJ'), possession='away', quarter=1, game_seconds=255,
        play_seconds=30, down=3, distance_yards=2, visibility_state='live'),
}

MATERIAL_CODE_PINS = (
    (0x241ec,0x241fb,'462b702fa06bbbb2c1f48f60b7417665f94d00297a7936167be33d49bae6645a'),
    (0x23bf0,0x23c93,'e88770fb550c363af9c1ecfa5af25129a347038e2879b59017008b9ec1504d30'),
)
MENU_COLOR_PIN = (0x31f48f,0x31f4cf,'ad2b8f5424aaff0f49249a893d26f52825cf599beb0a8fef8c098828a729b681')


def material_submission(m, payload, material):
    """Execute the native material +18 read through its command-buffer write.

    Driver storage is a bounded fixture. Stop at the next instruction after
    the retail call; no graphics device or shader execution is represented.
    """
    pins=[]
    for start,end,sha in MATERIAL_CODE_PINS:
        offset=scene.layout.sbpos.va_to_off(payload,start)
        if scene.digest(payload[offset:offset+end-start])!=sha:
            raise ValueError('foreign native material submission code')
        pins.append(dict(start=hex(start),end=hex(end),sha256=sha))
    driver=m.alloc(4096);commands=m.alloc(512);m.put(driver+12,commands)
    sp=m.STACK+0xf000
    def submit():
        m.uc.reg_write(m.x.UC_X86_REG_ESP,sp)
        m.uc.reg_write(m.x.UC_X86_REG_EDI,material)
        m.uc.reg_write(m.x.UC_X86_REG_EBX,driver)
        m.visits.clear();m.writes.clear()
        m.uc.emu_start(0x241ec,0x241fb,count=1000)
        if m.uc.reg_read(m.x.UC_X86_REG_EIP)!=0x241fb or m.uc.reg_read(m.x.UC_X86_REG_ESP)!=sp:
            raise AssertionError('native material submission did not return within its bound')
        for at,n,_ in m.writes:
            if not (m.STACK<=at and at+n<=m.STACK+0x10000 or
                    driver<=at and at+n<=driver+4096 or commands<=at and at+n<=commands+512):
                raise AssertionError('material submission escaped fixture state')
    submit();end=m.get(driver+12);color=m.get(material+24)
    header=struct.unpack('<3I',m.uc.mem_read(commands,12))
    values=m.floats(commands+12,4)
    if header!=(0x41ea4,6,0x100b80) or end-commands!=28:
        raise AssertionError('unexpected native shader constant submission')
    for got,shift in zip(values,(16,8,0,24)):
        if abs(got-((color>>shift)&255)/510)>1e-7:
            raise AssertionError('native material constant differs from ARGB/510')
    submit();repeat=m.get(driver+12)-end
    if repeat:raise AssertionError('unchanged native color was uploaded again')
    return dict(argb=hex(color),material_field='+0x18',code_pins=pins,header=[hex(v) for v in header],
        rgba_half_scale=values,command_bytes=end-commands,unchanged_color_second_submission_bytes=repeat,
        gpu_executed=False)


def color_evidence(build):
    import unicorn
    start,end,sha=MENU_COLOR_PIN
    offset=scene.layout.sbpos.va_to_off(build.payload,start)
    menu=build.payload[offset:offset+end-start]
    if scene.digest(menu)!=sha:raise ValueError('foreign menu color source evidence')
    span=scene.apply(build.spans['score_bug'],'score_bug')[0]
    capture={}
    projection.native_geometry(build.payload,scene.decode(span)[1],fonts=build.fonts,
        texture_span=scene.apply(build.spans['score_buga'],'score_buga')[0],capture=capture,
        visible_elements=(),visibility_state='pre_snap')
    m=capture['machine'];rows=[]
    try:
        dest=m.alloc(128);base=m.get(m.get(0xa95528)+0x20)
        for away,home in (('BAL','JAX'),('MIN','NYJ'),('WAS','NYG')):
            m.identity(away=away,home=home)
            for side,name,callback,context in (('away',away,0xfc030,0xb30a58),('home',home,0xfc010,0xb30864)):
                m.run(0x68d70,ecx=context);primary=m.uc.reg_read(m.x.UC_X86_REG_EAX)
                reads=[]
                hook=m.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                    lambda _u,_a,at,n,_v,_d:reads.append((at,n)),begin=0x4e7fe0,end=0x4e889f)
                try:m.run(callback,ecx=dest)
                finally:m.uc.hook_del(hook)
                material=base+128*v3.MATERIAL_INDICES[side]
                rows.append(dict(pair=away+' at '+home,side=side,team=name,
                    asset_code=m.read_string(m.get(context+0x10c)),primary=hex(primary),
                    panel_argb=hex(m.get(material+24)),abbreviation=m.read_string(dest),
                    primary_reads=[hex(at) for at,n in reads if (at-0x4e7fe0)%28==8],
                    native_primary_accessor_visited=0x68d70 in m.visits,
                    native_submission=material_submission(m,build.payload,material)))
        return dict(schema='nfl2k5_scorebar_v3_colors/v1',pairs=rows,
            menu_evidence=dict(start=hex(start),end=hex(end),sha256=sha,retail_bytes=menu.hex(),
                primary_call='0x31f4b0 -> 0x68d70',primary_store='0x31f4b6: [material+0x18] = EAX',
                secondary_call='0x31f4c4 -> 0x68dc0',
                source='Native Team Select function 0x31f1d0, also identified in the read-only Ghidra corpus.'),
            guards=[dict(va=hex(a),size=n,sha256=sha,label=label) for a,n,sha,label in v3.GUARDS],
            table=dict(start='0x4e7fe0',end='0x4e88a0',stride=28,primary_offset=8,rows=80),
            scope='Native CPU table reads and material constant upload proved; GPU shader result modeled.',
            first_draw='Neutral until existing abbreviation callbacks run; no team-entry hooks.')
    finally:m.close()


def calibration(case):
    return dict(size=case['size'], affine=[1.5,1.5,*case['offset']], gain=1.082, bias=-21.1,
        evidence='One viewport transform from frame rails; independent score/down/cell ink checks.',
        limits='GPU filtering, video range and depth are modeled. Live hidden values are fixture inputs.')


def render(build, path, case, *, compiler=None, calibrated=True, **overrides):
    compiler = compiler or scene.exact
    decoded = scene.serialize(compiler.mesh(build.retail_scene))
    span, receipt = scene.layout.refit(build.spans['score_bug'], decoded)
    decoded = scene.decode(span)[1]
    atlas, atlas_receipt = scene.encode_atlas(build.spans['score_buga'], compiler.atlas())
    kwargs = {k:v for k,v in case.items() if k not in ('file','size','offset','sha256')}
    kwargs.update(overrides)
    capture = {}
    geometry = projection.native_geometry(build.payload, decoded, fonts=build.fonts, texture_span=atlas,
        visible_elements=(), capture=capture, **kwargs)
    try:
        geometry.update(projection.native_text_draw(capture))
        # FC360 submits the mesh before running abbreviation callbacks. This
        # settled forecast therefore models the next draw with those colours.
        # The first draw starts neutral; no setup/binding work is invented.
        geometry.update(projection.render_native(decoded,atlas,build.fonts,geometry,path,
            calibration=calibration(case) if calibrated else None))
    finally:
        capture['machine'].close()
    geometry['resource_pins'] = dict(scene=scene.digest(span),atlas=scene.digest(atlas),decoded=scene.digest(decoded))
    geometry['scene_refit'] = asdict(receipt)
    geometry['atlas_refit'] = atlas_receipt
    geometry['panel_timing'] = 'Settled draw after native abbreviation callbacks; first draw neutral.'
    return geometry


def measure(actual, predicted, case):
    # Score quads are independent of center visibility. These ROIs also stay
    # clear of the rim, timeouts, city labels and neighboring text.
    x,y=case['offset']
    boxes={'away_score': [317,614,361,660], 'home_score': [591,614,636,660]}
    if case['visibility_state']=='pre_snap':
        boxes.update(down=[405,610,550,635],quarter=[397,640,453,674],
                     game_clock=[453,640,520,674],play_clock=[520,640,561,674])
    rows={}
    for label,box in boxes.items():
        roi=[box[0]+x,box[1]+y,box[2]+x,box[3]+y]
        bright=label not in ('quarter','game_clock')
        want=witness.ink_box(actual,roi,bright=bright)
        got=witness.ink_box(predicted,roi,bright=bright)
        rows[label]=dict(roi=roi,witness_ink_box=want,projected_ink_box=got,
            maximum_edge_error_px=None if want is None or got is None else max(abs(a-b) for a,b in zip(want,got)))
    return rows


def build_evidence(extraction, output, source, *, disc=None):
    from PIL import Image,ImageDraw
    output.mkdir(parents=True,exist_ok=True)
    (output/'witness').mkdir(exist_ok=True)
    build=Build(extraction/'vc_53450030/0',extraction/'default.xbe')
    rows={}; pictures=[]
    try:
        for name,case in CASES.items():
            path=source/case['file']
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=case['sha256']:
                raise ValueError('foreign Noah capture: '+path.name)
            if path.resolve() != (output/'witness'/path.name).resolve():
                shutil.copyfile(path,output/'witness'/path.name)
            with Image.open(path) as opened: actual=opened.convert('RGB')
            if list(actual.size)!=case['size']: raise ValueError('capture size changed')
            before_path=output/(name+'_v2.png');after_path=output/(name+'_v3.png')
            with witness.historical('v2') as old:
                before=render(build,before_path,case,compiler=old)
            if before['resource_pins']['scene']!='6c3cad4eee9dc3aab4d4cc2ffba60dfdfc579c40fa6d60b18d013deab0529eea':
                raise ValueError('v2 installed scene reconstruction changed')
            if before['resource_pins']['atlas']!='a4055637d479233c9e929f73fa3ee60da5826e28f47b0f562ed39771a50d90f3':
                raise ValueError('v2 installed atlas reconstruction changed')
            after=render(build,after_path,case)
            with Image.open(before_path) as opened:before_image=opened.convert('RGB')
            with Image.open(after_path) as opened:after_image=opened.convert('RGB')
            measured=measure(actual,before_image,case)
            rows[name]=dict(witness=case,calibration=calibration(case),measurements=measured,before=before,after=after)
            x,y=case['offset'];crop=(x+208,y+601,x+750,y+683)
            pictures.append((name,[im.crop(crop) for im in (actual,before_image,after_image)]))
        # A second live value proves the forecast is not a frozen presnap label.
        case=CASES['min_nyj_live'];x,y=case['offset']
        next_path=output/'min_nyj_live_next_v3.png'
        rows['live_next']=render(build,next_path,case,game_seconds=254)
        with Image.open(next_path) as opened: next_image=opened.convert('RGB')
        crop=(x+208,y+601,x+750,y+683)
        pictures.append(('live: next clock sample (4:14)',[None,None,next_image.crop(crop)]))
        sheet=Image.new('RGB',(3*556,4*110+64),(25,25,28));draw=ImageDraw.Draw(sheet)
        for i,title in enumerate(('Noah gameplay, disc bf','Installed v2: calibrated native raster','v3 forecast: EXPERIMENTAL / UNWITNESSED')):
            draw.text((i*556+7,8),title,fill='white')
        for j,(name,images) in enumerate(pictures):
            for i,im in enumerate(images):
                if im is not None:
                    draw.text((i*556+7,j*110+30),name.replace('_',' '),fill='white')
                    sheet.paste(im,(i*556+7,j*110+47))
        draw.text((8,480),'Live quarter/down inferred from presnap; hidden game clock sampled at 4:15 then 4:14. Play clock: -- when unavailable.',fill='white')
        sheet.save(output/'comparison.png')
        write_json(output/'calibration.json',dict(schema='nfl2k5_scorebar_v3_witness/v1',cases=rows,
            experimental=True,v3_witnessed=False,baseline_fixture_sha256=witness.V2_FIXTURE_SHA))
        receipts=projection.static_receipts(build.payload,build.spans)
        write_json(output/'colors.json',color_evidence(build))
        receipts['new_callback_edits']=[dict(va=hex(a),retail=o.hex(),patched=n.hex(),label=l) for a,o,n,l in v3.xbe_specs()]
        if disc is not None:
            with disc.open('rb') as stream:
                jobs,receipt=scene.image_plan(stream.fileno(),os.fstat(stream.fileno()).st_size)
            receipts['read_only_disc_preflight']=dict(receipt=receipt,writes=[dict(offset=a,length=len(b),
                before_sha256=scene.digest(b),after_sha256=scene.digest(c)) for a,b,c in jobs])
        receipts['root_free_bytes']=shutil.disk_usage('/').free
        write_json(output/'receipts.json',receipts)
        return {name:row['measurements'] for name,row in rows.items() if 'measurements' in row}
    finally:
        build.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extraction',type=Path,default=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)'))
    parser.add_argument('--output',type=Path,default=ROOT/'docs/scorebug_ingame/v3')
    parser.add_argument('--witness',type=Path,default=ROOT/'docs/scorebug_ingame/v3/witness')
    parser.add_argument('--disc',type=Path)
    args=parser.parse_args(argv)
    print(build_evidence(args.extraction,args.output,args.witness,disc=args.disc))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render the compiled v10 bar using the bounded native projection harness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as r
from mod_editor.core import nfl2k5_scorebug_template as template
from nfl2k5_scorebug_projection import (native_geometry, native_text_draw, read_fonts,
    render_native, containment_failures, static_receipts, native_team_binding_audit,
    v8_baseline, reference_rails)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack',type=Path,required=True)
    parser.add_argument('--xbe',type=Path,required=True)
    parser.add_argument('--folder',type=Path,default=template.DEFAULT_FOLDER)
    parser.add_argument('--photo',type=Path,default=ROOT/'docs/scorebug_ingame/real_broadcast_reference.jpeg')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/scorebug_ingame')
    # Historical projection CLI compatibility; this is a provenance input only.
    parser.add_argument('--witness',type=Path)
    args=parser.parse_args(argv)
    from PIL import Image, ImageDraw, ImageChops
    if args.xbe.stat().st_size > 16 * 1024 * 1024:
        parser.error('XBE exceeds the bounded 16 MB input limit')
    xbe=args.xbe.read_bytes()
    with args.pack.open('rb') as stream:
        spans={}
        for name,record in r.RESOURCES.items():
            stream.seek(record['pack_offset']);spans[name]=stream.read(record['span_size'])
    compiled=template.compile_folder(args.folder)
    scene_span,_=r.apply(spans['score_bug'],'score_bug')
    scene=r.decode(scene_span)[1]
    atlas_span,_=r.apply(spans['score_buga'],'score_buga',scorebug_folder=args.folder)
    fonts=read_fonts(args.pack)
    args.output.mkdir(parents=True,exist_ok=True)
    audit={'schema':'nfl2k5_scorebug_v10_audit/v1','status':'PASS_STATIC_V10',
           'experimental':True,'witnessed':False,'template':compiled.receipt,
           'reference_rails':reference_rails(),'xbe_sha256':r.digest(xbe),
           'scene_sha256':r.digest(scene),'atlas_sha256':r.digest(atlas_span),
           'static_receipts':static_receipts(xbe,spans,scorebug_folder=args.folder),
           'projections':{},'team_material_hook':r.TEAM_MATERIAL_HOOK,
           'fonts':[{'name':font.name,'sha256':font.decoded_sha256} for font in fonts],
           'gpu_state_proved':False,'full_disc_created':False}
    for wide in (False,True):
        for mode in (0,1):
            capture={}
            geometry=native_geometry(xbe,scene,widescreen=wide,mode=mode,
                                     texture_span=atlas_span,fonts=fonts,capture=capture)
            try:
                geometry.update(native_text_draw(capture))
                if not wide and mode==0:
                    audit['team_binding_cases']=native_team_binding_audit(capture)
                failures=containment_failures(geometry)
                strict=containment_failures(geometry,geometry['frame'],.02)
                if failures or strict:
                    raise ValueError(f'Native v10 containment failed: {failures or strict}')
                suffix=('_wide' if wide else '')+('_mode1' if mode else '')
                for cull in (False,True):
                    name=f'after_v10{suffix}_640x480'+('_cull' if cull else '')+'.png'
                    policy=render_native(scene,atlas_span,fonts,geometry,args.output/name,cull_positive=cull)
                    key='zz_ESPN_bug1' if mode else 'zz_ESPN_bug'
                    if policy['winding'][key] != {'positive':0,'negative':2}:
                        raise ValueError('V10 mark winding changed')
                    if not cull:geometry['raster']=policy
                geometry['containment_failures']=failures
                geometry['actual_frame_containment_failures']=strict
                audit['projections'][suffix or 'normal']=geometry
            finally:
                capture['machine'].close()
        a=args.output/('after_v10'+('_wide' if wide else '')+'_640x480.png')
        b=args.output/('after_v10'+('_wide' if wide else '')+'_mode1_640x480.png')
        with Image.open(a) as first,Image.open(b) as second:
            if ImageChops.difference(first,second).getbbox():
                raise ValueError('The direction modes render different pixels')
    audit['direction_modes_pixel_identical']=True
    # Preserve the independent v8 negative control: the same predicate must
    # reject visible panels and score glyphs below the frame.
    before,old_atlas=v8_baseline(spans);capture={}
    negative=native_geometry(xbe,before,texture_span=old_atlas,fonts=fonts,
                             capture=capture,baseline_v8=True)
    try:
        negative.update(native_text_draw(capture))
        failures=containment_failures(negative)
        if 'zscore_buga' not in failures or not any(k.startswith('0xfc050:') for k in failures):
            raise ValueError('The pinned v8 negative control stopped detecting the defect')
        audit['v8_negative_control']={'scene_sha256':r.digest(before),'atlas_sha256':r.digest(old_atlas),
                                      'containment_failures':failures}
    finally:capture['machine'].close()
    before_path=ROOT/'docs/scorebug_ingame/after_v9_640x480.png'
    if not before_path.is_file() or not args.photo.is_file():
        raise ValueError('The preserved v9 render and original broadcast photo are required for the comparison')
    photo_bytes=args.photo.read_bytes()
    photo_target=args.output/'real_broadcast_reference.jpeg'
    if args.photo.resolve()!=photo_target.resolve():
        shutil.copyfile(args.photo,photo_target)
    audit['reference']={'path':'real_broadcast_reference.jpeg','sha256':r.digest(photo_bytes),
        'kind':'original broadcast photograph supplied in the read-only research hub',
        'photo_bar_crop':[432,939,1490,1056],
        'adaptations':['Mark moved from upper right into the left cell, as requested',
                       'Neutral team blocks with live abbreviations; runtime colours deferred',
                       'FONT2 scores; FONT1 clock/down; FONT5 abbreviations; new glyph sheet staged only'],
        'misnamed_targets':{name:{'sha256':r.digest((ROOT/'docs/scorebug_ingame'/name).read_bytes()),
                                 'kind':'historical staged mockup, not a broadcast capture'}
                            for name in ('target_NO_MIA.png','target_BAL_PIT.png','target_LV_HOU.png','target_widest.png')}}
    audit['before_v9']={'path':str(before_path.relative_to(ROOT)),'sha256':r.digest(before_path.read_bytes())}
    sheet=Image.new('RGB',(1920,520),(12,16,22));d=ImageDraw.Draw(sheet)
    for i,(path,label) in enumerate(((before_path,'BEFORE: V9 / NATIVE INPUTS / SOFTWARE RASTER'),
            (args.output/'after_v10_640x480.png','AFTER: V10 / EXPERIMENTAL / UNWITNESSED'),
            (photo_target,'REAL BROADCAST PHOTO / ORIGINAL SUPPLIED REFERENCE'))):
        d.text((i*640+8,8),label,fill='white')
        with Image.open(path) as source:
            im=source.convert('RGB')
            if i==2:im=im.resize((640,360),Image.Resampling.LANCZOS)
            sheet.paste(im,(i*640,32))
    d.text((1288,412),'Photo: corner mark, mirrored teams, red down cell, light clock.',fill='white')
    d.text((1288,432),'V10 follows the requested left-mark / neutral-team adaptation.',fill='white')
    sheet.save(args.output/'v10_before_after_real.png')
    strips=Image.new('RGB',(960,408),(12,16,22));d=ImageDraw.Draw(strips)
    for i,(path,box,label) in enumerate(((before_path,(84,381,560,429),'V9 / SAME NATIVE HUD RAILS'),
             (args.output/'after_v10_640x480.png',(84,381,560,429),'V10 / NEW TEMPLATE ART / LIVE RETAIL FONTS'),
             (photo_target,(432,939,1490,1056),'ORIGINAL BROADCAST / CROP NORMALIZED TO BAR WIDTH'))):
        d.text((8,i*136+4),label,fill='white')
        with Image.open(path) as source:
            strip=source.convert('RGB').crop(box)
        strip=strip.resize((952,96 if i<2 else 105),Image.Resampling.LANCZOS)
        strips.paste(strip,(4,i*136+26))
    strips.save(args.output/'v10_bar_comparison.png')
    (args.output/'v10_native_audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':audit['status'],'resources':audit['static_receipts']['resources'],
                      'direction_modes_pixel_identical':True,'output':str(args.output)},indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

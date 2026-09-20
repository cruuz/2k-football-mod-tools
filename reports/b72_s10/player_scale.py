"""Native 448-line rasters, player-size measurements and supplied witness sheets.

Run baseline before authoring, then final after authoring. No emulator is launched.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import gpu, xemu_model
import nfl2k5_scorebug_projection as projection

HUB = Path('/home/noah/Desktop/2K5-8 Editors/beta72_evidence')
BROADCAST = Path('/media/noah/Storage/Broadcast refs')
# 617 visible columns in the first supplied disc r capture, x=260..877.
# All references keep their aspect, normalized by bar width, never by a glyph.
SCALE = 617/1041
PLAYER = {False: (round(1440*SCALE), round(1080*SCALE)),
          True: (round(1920*SCALE), round(1080*SCALE))}
CASES = {
    'DEN_KC': (BROADCAST/'espn-2026-broncos-chiefs-full/frames_1s/s_00724.jpg',
        dict(away='DEN', home='KC', away_score=0, home_score=0, clock=897,
             quarter=1, play_clock=40, down=1, distance=10, possession='away', broadcast='monday_night')),
    'LV_HOU': (BROADCAST/'espn-2025-raiders-texans/frames/frame_005000.jpg',
        dict(away='LV', home='HOU', away_score=0, home_score=7, clock=515,
             quarter=1, play_clock=10, down=1, distance=10, possession='away', broadcast='play_now')),
}
# Visible outer housings, measured from the supplied frame edge profiles.
# A frame-width match alone leaves the ESPN bar about six player pixels
# wider, which would incorrectly inflate the long rim residual.
REFERENCE_BOUNDS = {'s_00724.jpg': (435,942,1486,1055),
                    'frame_005000.jpg': (433,942,1487,1055)}
# These are independent surface ROIs, not a claim of exact segmentation.
# Leave the score, label and central pill separate from the colour surface.
REGIONS = {
    'wing_colour': [(438,948,686,1050),(1230,948,1477,1050)],
    'logo': [(438,944,656,1050),(1260,944,1477,1050)],
    'score': [(696,955,816,1026),(1100,955,1220,1026)],
    'down_capsule': [(819,942,1100,989)],
    'housing_rim': [(438,942,1477,948),(438,1046,1477,1052),(831,989,1089,999)],
    'pill': [(839,999,1082,1043)],
}


def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def draw(preview, state, wide):
    geometry, capture = preview.capture(state, wide)
    try:
        mode = preview.modes[wide]
        with tempfile.TemporaryDirectory(prefix='s10-raster-') as tmp:
            path = Path(tmp)/'hud.png'
            receipt = projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts,
                geometry, path, texture_spans=capture['texture_spans'],
                background=Image.new('RGB',(640,480),'#303030'),
                gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
            hud = Image.open(path).convert('RGB').crop((0,16,640,464))
            display = hud.resize(PLAYER[wide], Image.Resampling.LANCZOS)
        return display, dict(state=sprite.normalize_state(state), raster=receipt,
            hud=[640,448], display=list(PLAYER[wide]), filter='Lanczos display approximation',
            runtime_witnessed=False, calibrated_gpu_capture=False)
    finally:
        capture['machine'].close()


def aligned(im):
    canvas=Image.new('RGB',PLAYER[True],'#303030')
    canvas.paste(im,((canvas.width-im.width)//2,0))
    return canvas


def box(b):
    return tuple(round(v*SCALE) for v in b)


def bar(im):
    return aligned(im).crop(box((425,930,1495,1060)))


def reference(path):
    source=Image.open(path).convert('RGB')
    x,y,right,bottom=REFERENCE_BOUNDS[path.name]
    factor=617/(right-x)
    resized=source.resize((round(source.width*factor),round(source.height*factor)),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',PLAYER[True],'#303030')
    target_x,target_y,_,_=box((437,942,1478,1052))
    canvas.paste(resized,(target_x-round(x*factor),target_y-round(y*factor)))
    return canvas


def visible(mask):
    """Retain only disagreement with a 2 by 2 player-pixel core.

    This intentionally ignores isolated one-pixel contour/stem residuals.
    Dilating the core back one pixel records the connected visible area.
    """
    core=mask[:-1,:-1]&mask[1:,:-1]&mask[:-1,1:]&mask[1:,1:]
    result=np.zeros_like(mask)
    for y in range(2):
        for x in range(2): result[y:y+core.shape[0],x:x+core.shape[1]] |= core
    return result


def metrics(im, ref):
    actual=np.asarray(aligned(im),dtype=float)
    target=np.asarray(ref,dtype=float)
    # RGB difference is sufficient for broad surfaces; shape/ink occupancy
    # handles the same-state score. Logo masks isolate brighter mark ink
    # from the underlying gradient, while the colour surface excludes it.
    bright_a=actual.min(2)>155
    bright_b=target.min(2)>155
    rows=[]
    for name, regions in REGIONS.items():
        roi=np.zeros(actual.shape[:2],bool)
        for r in regions:
            x,y,right,bottom=box(r);roi[y:bottom,x:right]=True
        rgb_diff=np.max(abs(actual-target),axis=2)>=24
        if name=='wing_colour':
            roi &= ~(bright_a|bright_b)
            # Measure the extent of the colour well, not whether two legal
            # shades differ by 24 RGB levels. Neutral teams use a raised
            # grey surface; coloured teams use chroma above the dark body.
            colour_a=(actual.max(2)-actual.min(2)>14)|(actual.min(2)>53)
            colour_b=(target.max(2)-target.min(2)>14)|(target.min(2)>53)
            diff=colour_a^colour_b
        elif name in ('logo','score'):
            diff=bright_a^bright_b
        elif name=='pill':
            diff=(actual.min(2)>185)^(target.min(2)>185)
        elif name=='down_capsule':
            surface_a=(np.max(abs(actual-37),axis=2)>24)&~bright_a
            surface_b=(np.max(abs(target-37),axis=2)>24)&~bright_b
            diff=surface_a^surface_b
        else:
            surface_a=(actual.mean(2)>65)|(actual.max(2)-actual.min(2)>35)
            surface_b=(target.mean(2)>65)|(target.max(2)-target.min(2)>35)
            diff=surface_a^surface_b
        counted=visible(roi & diff)
        rows.append(dict(feature=name,visible_area_px=int(counted.sum()),
            rgb_diagnostic_px=int(visible(roi&rgb_diff).sum()),
            measured_area_px=int(roi.sum()),threshold='Feature occupancy with a 2x2 player-pixel core; exact thresholds in metrics()',
            method='Visible feature occupancy XOR, filtered to 2x2 player-pixel cores. RGB mismatch retained only as a diagnostic.',
            caveat='White logo ink only; coloured silhouette also changes the wing ROI.' if name=='logo' else 'Surface/shape proxy; not a perceptual identity verdict.'))
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['baseline','final'])
    args=parser.parse_args()
    if args.phase=='baseline':
        from mod_editor.core import nfl2k5_scorebug_teams as teams
        teams.DATA=ROOT/'.scratch/s10_before'
    preview=sprite.NativePreview(folder=ROOT/'.scratch/s10_before' if args.phase=='baseline' else None)
    rows=[];receipts={}
    for name,(path,state) in CASES.items():
        ref=reference(path)
        for wide in (False,True):
            aspect='169' if wide else '43'
            im,receipt=draw(preview,state,wide)
            im.save(OUT/f'{args.phase}_{name}_{aspect}.png')
            receipts[name+'_'+aspect]=receipt
            rows.extend(dict(matchup=name,aspect=aspect,**r) for r in metrics(im,ref))
    ranked=[]
    for feature in REGIONS:
        values=[r['visible_area_px'] for r in rows if r['feature']==feature]
        ranked.append(dict(feature=feature,visible_area_px=round(sum(values)/len(values),2),
            maximum_area_px=max(values),metric='mean player pixels across two same-state matchups and both aspects'))
    ranked.sort(key=lambda r:-r['visible_area_px'])
    for i,r in enumerate(ranked):r['rank']=i+1
    write(args.phase+'_measurements.json',dict(player_sizes={str(k):v for k,v in PLAYER.items()},
        bar_width_px=617,rows=rows,ranked=ranked,
        provenance={name:dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),state=state,bar_bounds=REFERENCE_BOUNDS[path.name]) for name,(path,state) in CASES.items()},
        limitation='Proxy counts overlap between logo and wing and must not be summed. No 4:3 broadcast or WAS-LAC broadcast is supplied.'))
    write(args.phase+'_native_receipts.json',receipts)
    print(json.dumps(ranked,indent=2))


if __name__=='__main__': main()

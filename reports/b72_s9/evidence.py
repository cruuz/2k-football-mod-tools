"""Offline native render comparisons. All before captures are supplied witnesses."""
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import argparse
import hashlib
import json
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_teams as teams
from tools.scorebug_sprite import render, gpu, xemu_model
from tools.scorebug_sprite.jev import descriptors,miner
from tools.scorebug_sprite.match_espn import glyph_proof
import nfl2k5_scorebug_projection as projection

WITNESSES=[('TEN','WAS','ksnip_20260919-170803.png',dict(away_score=0,home_score=3,quarter=1,clock=300,play_clock=32,down=1,distance=10,possession='home')),
           ('MIN','CHI','ksnip_20260919-170844.png',dict(away_score=7,home_score=13,quarter=3,clock=15,play_clock=34,down=1,distance=10,possession='home')),
           ('DEN','NE','ksnip_20260919-170601.png',dict(away_score=0,home_score=0,quarter=1,clock=80,play_clock=25,event='ball on',possession='away'))]
STATES=dict(first_and_ten=dict(down=1,distance=10),second_and_ten=dict(down=2,distance=10),
    short_yardage=dict(down=3,distance=1),third_and_long=dict(down=3,distance=12),
    fourth_down=dict(down=4,distance=8),goal_to_go=dict(down=1,distance=5,goal_to_go=True),
    flag=dict(event='FLAG'),fumble=dict(event='FUMBLE'),ball_on=dict(event='ball on'),hang_time=dict(event='hang time'),
    score_slabs=dict(event='score slabs'),hidden_play_clock=dict(event='hidden play clock'),
    play_clock_five=dict(play_clock=5),two_minute=dict(clock=120),quarter_end=dict(clock=0),
    timeouts_two=dict(home_timeouts=2,away_timeouts=2),timeouts_one=dict(home_timeouts=1,away_timeouts=1),
    timeouts_none=dict(home_timeouts=0,away_timeouts=0))


def write(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')


def draw(preview,state,aspect):
    state=sprite.normalize_state(state);wide=aspect=='16:9'
    native=projection.native_geometry
    # Only the supplied field-position input is changed, not native code or
    # event records. This reproduces the photographed Ball on DEN 28 state.
    def geometry(*args,**kwargs):
        if state['event']=='ball on':kwargs['ball_yards']=28
        return native(*args,**kwargs)
    with patch.object(projection,'native_geometry',geometry):g,c=preview.capture(state,wide)
    try:
        mode=preview.modes[wide];pipeline=xemu_model.Pipeline(gpu.capture_state(c))
        with tempfile.TemporaryDirectory(prefix='s9-raster-') as directory:
            p=Path(directory)/'frame.png'
            receipt=projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,p,
                texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#303030'),gpu_pipeline=pipeline)
            im=Image.open(p).convert('RGB').crop((0,16,640,464)).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
        return im,dict(state=state,aspect=aspect,native_text=g.get('draws',[]),raster=receipt,
                       runtime_witnessed=False,calibration_passed=False)
    finally:c['machine'].close()


def bar(im):
    dx=(im.width-1920)//2
    return im.crop((425+dx,930,1495+dx,1060))


def metrics(im):
    a=np.asarray(im,dtype=float)
    # All measurements operate in aligned broadcast coordinates, then report
    # SD positions. Stable samples avoid glyphs and marks.
    def sample(box):
        x,y,r,b=box;return np.median(a[y:b,x:r,:3].reshape(-1,3),axis=0)
    result={}
    for name,box in dict(body=(800,990,815,1020),pill=(895,1012,900,1028),plate=(840,960,853,977),
                         rim=(690,944,711,949),housing=(900,1043,1010,1046),
                         wing_outer=(450,1040,462,1045),wing_middle=(520,1040,532,1045),
                         wing_inner=(625,1040,637,1045)).items():result[name]=sample(box).round(2).tolist()
    for name,box,dark in [('away_score',(698,958,819,1023),False),('clock',(906,1002,1014,1034),True),
                           ('down',(840,950,1080,983),False),('quarter',(855,1005,900,1031),True)]:
        x,y,r,b=box;crop=a[y:b,x:r,:3]
        mask=crop.max(2)<90 if dark else crop.min(2)>185
        ys,xs=np.where(mask)
        result[name]=dict(ink_box=[int(xs.min()+x),int(ys.min()+y),int(xs.max()+x+1),int(ys.max()+y+1)] if len(xs) else None,
                         cap=int(ys.max()-ys.min()+1) if len(xs) else 0,
                         width=int(xs.max()-xs.min()+1) if len(xs) else 0)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('hub',type=Path);p.add_argument('broadcast',type=Path);p.add_argument('raiders',type=Path)
    p.add_argument('--sheets-only',action='store_true',help='Refresh sheets and state receipts after a clock-only change; retain the existing all-team raster audit.')
    args=p.parse_args();preview=sprite.NativePreview();before=sprite.NativePreview(folder=ROOT/'.scratch/s9_before')
    sheets=OUT/'sheets';sheets.mkdir(exist_ok=True)
    receipts={};before_rows=[];calibration=[]
    for away,home,filename,state in WITNESSES:
        source=args.hub/'beta72_evidence/disc_q_witness_0919'/filename
        witness=Image.open(source).convert('RGB').resize((1920,1080),Image.Resampling.LANCZOS)
        state=dict(state,away=away,home=home)
        baseline,b=draw(before,state,'16:9')
        rendered={}
        for aspect in ('16:9','4:3'):
            after,r=draw(preview,state,aspect);rendered[aspect]=bar(after)
            receipts[f'witness_{away}_{home}_{aspect}']=r
        before_rows.append(dict(label=away+' at '+home,witness=bar(witness),after=rendered))
        actual=descriptors.describe(witness);modeled=descriptors.describe(baseline,light_clock=True)
        calibration.append(dict(capture=filename,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            actual=actual,base_model=modeled,calibration_passed=False,
            limitation='Witness crop has unrecorded display scaling and color processing. No artificial brightness multiplier fitted.'))
    # Same three before states on every sheet. These source captures are never
    # relabeled as captures of the proposed build or of another matchup.
    def sheet(ours,reference,title,aspect,reference_note):
        image=Image.new('RGB',(1800,710),'#252525');d=ImageDraw.Draw(image)
        d.text((20,10),title+' / '+aspect+' / OFFLINE PROPOSAL, NOT A GAME CAPTURE',fill='white')
        d.text((20,35),'Supplied disc q before captures',fill='#ffdb88');d.text((920,35),'Proposed artwork at the same captured states',fill='#ffdb88')
        for i,row in enumerate(before_rows):
            y=60+i*120;d.text((20,y),row['label'],fill='white')
            image.paste(row['witness'].resize((856,104)),(20,y+15))
            image.paste(row['after'][aspect].resize((856,104)),(920,y+15))
        d.text((20,450),'ESPN reference: '+reference_note,fill='white')
        d.text((920,450),'Proposed '+title,fill='white')
        image.paste(reference.resize((856,104)),(20,478));image.paste(ours.resize((856,104)),(920,478))
        d.text((20,610),'Live Broncos-Chiefs then Raiders-Texans govern geometry and style. Bills-Chiefs is an older preview.',fill='#cccccc')
        d.text((20,635),'Unavailable broadcast behaviors are listed in FIDELITY.md; native event timing remains disc q behavior.',fill='#cccccc')
        d.text((20,660),'4:3 references retain the broadcast bar proportions. No 4:3 ESPN source or new game witness exists.',fill='#cccccc')
        return image
    bc=[json.loads(l) for l in (args.broadcast/'grammar/seconds.jsonl').read_text().splitlines()]
    rt=[json.loads(l) for l in (args.raiders/'grammar_proto/sec_rt.jsonl').read_text().splitlines()]
    def reference_for(name,rows,kind):
        conditions=dict(first_and_ten=lambda d:d['down']==1 and d['dist']==10,
            second_and_ten=lambda d:d['down']==2 and d['dist']==10,
            short_yardage=lambda d:d['dist'] in (1,2),third_and_long=lambda d:d['down']==3 and isinstance(d['dist'],int) and d['dist']>=10,
            fourth_down=lambda d:d['down']==4,goal_to_go=lambda d:'GOAL' in d['plate'],
            flag=lambda d:d['plate']=='FLAG',play_clock_five=lambda d:d['pc']==5,
            two_minute=lambda d:d['clock']==120,quarter_end=lambda d:d['clock']==0,
            timeouts_two=lambda d:d['tAS']==2,timeouts_one=lambda d:d['tAS']==1,timeouts_none=lambda d:d['tAS']==0)
        chosen=next((d for d in rows if d['layout']=='full_bar' and conditions.get(name,lambda d:False)(d)),None)
        matched=chosen is not None
        if chosen is None:chosen=next(d for d in rows if d['layout']=='full_bar' and d['kind']=='down_distance')
        if kind=='bc':im=Image.open(args.broadcast/'frames_1s'/f"s_{chosen['t']+1:05d}.jpg").convert('RGB')
        else:
            frame=round(chosen['t']*30000/1001)+1
            im=Image.open(args.raiders/'frames'/f'frame_{frame:06d}.jpg').convert('RGB')
        return chosen,im,matched
    residuals=[]
    for matchup in [('LV','HOU'),('BUF','KC')]:
        for name,changes in STATES.items():
            chosen,reference,matched=reference_for(name,rt if matchup[0]=='LV' else bc,'rt' if matchup[0]=='LV' else 'bc')
            state=dict(away=matchup[0],home=matchup[1],away_score=24 if matchup[0]=='BUF' else chosen['sA'] or 0,
                home_score=36 if matchup[0]=='BUF' else chosen['sH'] or 0,clock=chosen['clock'] or 0,
                quarter=chosen['qS'] or 1,play_clock=chosen['pc'] or 0,down=chosen['down'] or 1,
                distance=chosen['dist'] if type(chosen['dist']) is int else 10,possession=chosen['possS'] or 'home')
            state.update(changes)
            for aspect in ('16:9','4:3'):
                im,r=draw(preview,state,aspect);key='_'.join(matchup)+'_'+name+'_'+aspect.replace(':','')
                receipts[key]=r
                note=('Raiders-Texans' if matchup[0]=='LV' else 'live MNF style applied to Bills-Chiefs')+f" t={chosen['t']}s"
                if not matched:note+='; normal reference, no matching event in supplied reel'
                sheet(bar(im),bar(reference),' at '.join(matchup)+' / '+name,aspect,note).save(sheets/(key+'.png'))
                offset=(1920-im.width)//2
                aligned=Image.new('RGB',(1920,1080),'#303030');aligned.paste(im,(offset,0))
                actual,wanted=metrics(aligned),metrics(reference)
                rows=[]
                for element in actual:
                    if isinstance(actual[element],list):
                        error=float(max(abs(np.array(actual[element])-wanted[element])));tol=15;unit='RGB channel'
                    else:
                        error=abs(actual[element]['cap']-wanted[element]['cap'])*448/1080;tol=1.;unit='HUD cap px'
                    comparable=matched and matchup[0]=='LV' and name not in ('ball_on','fumble','hang_time','score_slabs','hidden_play_clock')
                    rows.append(dict(element=element,actual=actual[element],reference=wanted[element],error=round(error,3),
                        tolerance=tol,unit=unit,status=('PASS' if error<=tol else 'FAIL') if comparable else 'NOT_COMPARABLE'))
                residuals.append(dict(sheet=key,reference_second=chosen['t'],matched_state=matched,rows=rows))
            print('state',matchup,name,flush=True)
    # All 52 runtime tint slots and both aspects, including neutral custom slots.
    readability=json.loads((OUT/'readability.json').read_text()) if args.sheets_only else []
    for aspect in (() if args.sheets_only else ('16:9','4:3')):
        grid=Image.new('RGB',(1100,26*85+30),'#252525');d=ImageDraw.Draw(grid)
        d.text((5,4),'OFFLINE ALL-SLOT READABILITY / '+aspect+' / NOT WITNESSED',fill='white')
        for i,(name,t) in enumerate(teams.load().items()):
            im,r=draw(preview,dict(away=name,home=name,down=1,distance=10,play_clock=40),'16:9' if aspect=='16:9' else '4:3')
            desc=descriptors.describe(im,aspect=aspect)
            field=desc['fields']['down'];plate=desc['fields']['plate']
            ratio=descriptors.contrast(plate['rgb'])
            readability.append(dict(team=name,aspect=aspect,core_luma=field['core_luma'],contrast=ratio,
                predicted_pass=field['core_luma']>=200 and ratio>=4.5,
                runtime_witnessed=False))
            x=i%2*550;y=i//2*85+30;d.text((x+5,y),name,fill='white');grid.paste(bar(im).resize((535,65)),(x+5,y+16))
        grid.save(OUT/('all_teams_'+aspect.replace(':','')+'.png'));print('all teams',aspect,flush=True)
    write('native_receipts.json',receipts);write('calibration.json',calibration);write('residuals.json',residuals)
    write('readability.json',readability)
    write('glyph_proof.json',{str(w):glyph_proof(preview,w) for w in (False,True)})
    write('budgets.json',dict(rx_used=len(owner.code_for(0x6000000,0x6001000)[0].rstrip(b'\xcc')),
        rx_reserved=owner.CODE_SIZE,rw_reserved=owner.DATA_SIZE,aspects={str(k):v['volume'] for k,v in preview.modes.items()},
        ceiling=sprite.MAX_APPEND,runtime_source_changed='clock formatter selection only'))
    requests=json.loads((OUT/'miner/requests.json').read_text());descs=json.loads((OUT/'miner/descriptors.json').read_text())
    answers=[r['answers'] for i in range(5) for r in json.loads((OUT/f'miner/call_{i}.json').read_text())['response']['results']]
    write('miner/states.json',miner.cluster(descs,answers))
    print('readability failures',[r for r in readability if not r['predicted_pass']],flush=True)


if __name__=='__main__':main()

"""All-slot native label audit, geometry containment and owner budgets."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw
import player_scale as P
from mod_editor.core import nfl2k5_scorebug_teams as teams
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from tools.scorebug_sprite.jev import descriptors


def main():
    preview=P.sprite.NativePreview();spec=preview.compiled.spec
    rows=[];logos=[]
    # Every static/dynamic layout remains within the original HUD bar.
    for row in spec['static']+spec['fields']+spec['events']:
        x,y,r,b=row['box'];assert 437<=x<r<=1478 and 942<=y<b<=1052,row['name']
    for wide in (False,True):
        sheet=Image.new('RGB',(1320,26*102+130),'#303030');draw=ImageDraw.Draw(sheet)
        draw.text((5,4),'BEFORE: supplied disc r WAS-LAC, original capture pixels',fill='#ffdb88')
        witness=Image.open(P.HUB/'disc_r_witness_0919/ksnip_20260919-210430.png').convert('RGB')
        sheet.paste(witness.crop((253,584,887,667)),(5,22))
        draw.text((5,112),'All 52 slots | native '+('16:9' if wide else '4:3')+' | OFFLINE | player scale',fill='white')
        for i,(name,team) in enumerate(teams.load().items()):
            im,receipt=P.draw(preview,dict(away=name,home=name,down=1,distance=10,play_clock=40),wide)
            arr=np.asarray(P.aligned(im),dtype=float)
            x,y,r,b=P.box((829,950,1089,980));crop=arr[y:b,x:r,:3]
            ink=crop.min(2)>185;luma=descriptors.rgb_luma(crop)
            core=float(np.percentile(luma[ink],75)) if ink.any() else 0.
            # Palette contrast is independent of an ROI median that could
            # be contaminated by the white text itself.
            contrast=teams.contrast_white(team['plate'])
            ok=core>=200 and contrast>=4.5 and int(ink.sum())>=100
            rows.append(dict(team=name,aspect='169' if wide else '43',core_luma=round(core,2),
                white_core_pixels=int(ink.sum()),contrast=round(contrast,4),passed=ok,runtime_witnessed=False))
            x=i%2*660;y=i//2*102+130;draw.text((x+5,y),name,fill='white');sheet.paste(P.bar(im),(x+5,y+16))
        sheet.save(P.OUT/f'all_teams_{"169" if wide else "43"}.png')
        print('Completed all slots',wide,flush=True)
    for name,fit in spec['logo_fit']['by_team'].items():
        from mod_editor.core import nfl2k5_scorebug_exact as exact
        im=exact.mnf_panel(name,'home',fit=fit);alpha=np.asarray(im.getchannel('A'))
        logos.append(dict(team=name,fit=fit,bounds=im.getchannel('A').getbbox(),
            coverage_pixels=int((alpha>128).sum()),edge_pixels={side:int((values>128).sum()) for side,values in
                dict(top=alpha[0],bottom=alpha[-1],left=alpha[:,0],right=alpha[:,-1]).items()},
            provenance='Compared with supplied broadcast' if name in ('DEN','KC','LV','HOU') else 'Silhouette inference; no same-team broadcast supplied'))
    P.write('readability.json',rows);P.write('logo_fits.json',logos)
    budget=dict(rx_used=len(owner.code_for(0x6000000,0x6001000)[0].rstrip(b'\xcc')),
        rx_reserved=owner.CODE_SIZE,rw_reserved=owner.DATA_SIZE,
        aspects={str(k):v['volume'] for k,v in preview.modes.items()},ceiling=P.sprite.MAX_APPEND,
        owner_code_changed=False,footprint=[437,942,1478,1052])
    P.write('budgets.json',budget)
    assert budget['rx_used']<=4096
    assert all(v['volume']['appended_bytes']<400000 for v in preview.modes.values())
    failures=[r for r in rows if not r['passed']]
    print('Label checks',len(rows),'failures',failures,flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()

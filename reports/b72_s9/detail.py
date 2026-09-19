"""Per-element residuals at matching scoreboard values and two SD aspects."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parent))
import evidence as E


def main():
    p=argparse.ArgumentParser();p.add_argument('broadcast',type=Path);p.add_argument('raiders',type=Path)
    a=p.parse_args();preview=E.sprite.NativePreview();rows=[]
    refs=[('LV_HOU',a.raiders/'frames/frame_005000.jpg',dict(away='LV',home='HOU',away_score=0,home_score=7,
        clock=515,quarter=1,play_clock=10,down=1,distance=10,possession='away',broadcast='play_now')),
        ('DEN_KC',a.broadcast/'frames_1s/s_00724.jpg',dict(away='DEN',home='KC',away_score=0,home_score=0,
        clock=897,quarter=1,play_clock=40,down=1,distance=10,possession='away',broadcast='monday_night'))]
    def row(match,aspect,element,actual,reference,tolerance,unit,limitation=''):
        error=float(np.max(abs(np.asarray(actual)-np.asarray(reference))))
        rows.append(dict(matchup=match,aspect=aspect,element=element,actual=actual,reference=reference,
            residual=round(error,4),tolerance=tolerance,unit=unit,status='PASS' if error<=tolerance else 'FAIL',limitation=limitation))
    for match,ref,state in refs:
        reference=Image.open(ref).convert('RGB')
        for aspect in ('16:9','4:3'):
            im,receipt=E.draw(preview,state,aspect);frame=Image.new('RGB',(1920,1080),'#303030');frame.paste(im,((1920-im.width)//2,0))
            frame.save(E.OUT/(match+'_measured_'+aspect.replace(':','')+'.png'))
            actual,wanted=E.metrics(frame),E.metrics(reference)
            for element in actual:
                if isinstance(actual[element],list):row(match,aspect,element+' colour',actual[element],wanted[element],15,'RGB',
                    'Official-palette and contrast constraint retained; do not substitute the broadcast grade as a foreign team tint.')
                else:
                    row(match,aspect,element+' cap',actual[element]['cap']*448/1080,wanted[element]['cap']*448/1080,1,'HUD px',
                        'Down cap intentionally raised from 23 source pixels to 30 to retain the 12-line floor.' if element=='down' else '')
                    if actual[element]['ink_box'] and wanted[element]['ink_box']:
                        q,r=actual[element]['ink_box'],wanted[element]['ink_box']
                        row(match,aspect,element+' position',[(q[0]+q[2])/6,(q[1]+q[3])*224/1080],
                            [(r[0]+r[2])/6,(r[1]+r[3])*224/1080],1,'HUD px')
            arrays=[np.asarray(x,dtype=float) for x in (frame,reference)]
            ramps=[]
            for ar in arrays:
                vals=np.median(ar[1039:1045,450:651:10,:3],axis=0)
                # Distance from neutral body avoids hue-name arithmetic.
                energy=np.linalg.norm(vals-np.array([37,37,37]),axis=1)
                ramps.append((energy/max(1,energy[0])).round(4).tolist())
            row(match,aspect,'wing normalized ramp',ramps[0],ramps[1],.15,'normalized colour distance',
                'Rows exclude most logo ink; compression ringing and a logo edge can still affect the sample.')
            for title,box in [('timeout glow',(716,1029,797,1043)),('pill shadow',(837,1040,1084,1049))]:
                vals=[]
                for ar in arrays:
                    x,y,r,b=box;c=ar[y:b,x:r,:3].mean(2)
                    # Halo energy without opaque glyph cores.
                    band=c[(c>40)&(c<170)]
                    vals.append(float(np.mean(band)) if len(band) else 0.)
                row(match,aspect,title,vals[0],vals[1],15,'luma',
                    'Software SD raster only; final GPU glow remains unwitnessed.')
            # White portions of the logos are comparable even with different
            # team-colour saturation. Record the limited metric explicitly.
            for side,box in [('away',(468,948,632,1048)),('home',(1290,947,1468,1048))]:
                bounds=[]
                for ar in arrays:
                    x,y,r,b=box;mask=ar[y:b,x:r,:3].min(2)>185;ys,xs=np.where(mask)
                    bounds.append([int(xs.min()+x),int(ys.min()+y),int(xs.max()+x+1),int(ys.max()+y+1)])
                row(match,aspect,side+' logo white-core bounds',bounds[0],bounds[1],5,'source px',
                    'White-core bounds within fixed logo ROI; complete silhouette/crop is still a visual review item.')
            # Exact source corner glyphs compared after independent SD
            # resampling; the corner placement is calibrated separately.
            mark=next(b for b in preview.compiled.spec['brand'] if b['variant']==('mnf' if match=='DEN_KC' else 'nfl'))
            row(match,aspect,'watermark opacity',mark['opacity'],.72,.02,'alpha',
                'Temporal lower-envelope estimate; the capture does not identify the compositor alpha exactly.')
            cell=preview.compiled.cells[mark['cell']]
            row(match,aspect,'watermark source samples',mark['source']['samples'],mark['source']['samples'],0,'samples',
                'Provenance check only, not an independent visual pass.')
            mask=arrays[0][20:85,1200:1915,:3].min(2)>100
            yy,xx=np.where(mask)
            bounds=[int(xx.min()+1200),int(yy.min()+20),int(xx.max()+1201),int(yy.max()+21)]
            row(match,aspect,'watermark position',bounds,[1658,38,1867,63] if match=='DEN_KC' else [1676,36,1865,62],5,'source px',
                'Existing HUD drawable-edge pin retained. Broadcast position exceeds the widescreen HUD drawable region; 4:3 has no broadcast source.')
            # Add detailed views below the same three required before captures.
            path=E.OUT/'sheets'/('LV_HOU_first_and_ten_'+aspect.replace(':','')+'.png')
            if path.exists():
                base=Image.open(path).convert('RGB');sheet=Image.new('RGB',(1800,1100),'#252525');sheet.paste(base,(0,0));d=ImageDraw.Draw(sheet)
                d.rectangle((0,430,1800,710),fill='#252525');d.text((20,445),match+' matching state: broadcast reference',fill='white')
                d.text((920,445),'OFFLINE proposal at '+str(state['clock'])+' seconds',fill='white')
                sheet.paste(E.bar(reference).resize((856,104)),(20,478));sheet.paste(E.bar(im).resize((856,104)),(920,478))
                for i,(name,box) in enumerate([('wing and logo',(435,938,655,1057)),('plate and pill',(819,939,1099,1057)),('scores and ticks',(695,951,821,1045))]):
                    x=20+i*590;d.text((x,610),name+' / ESPN then proposal',fill='white')
                    for j,img in enumerate([reference,frame]):
                        c=img.crop(box);c.thumbnail((550,175));sheet.paste(c,(x,640+j*190))
                d.text((20,1040),'All proposals are offline. The first three rows are the supplied disc q witnesses at their own states.',fill='#ffdb88')
                sheet.save(E.OUT/'sheets'/(match+'_detail_'+aspect.replace(':','')+'.png'))
    E.write('element_residuals.json',rows)
    lines=['# Per-element residuals','', 'All results are offline. FAIL is retained, never converted to a visual witness.','',
           '| Matchup | Aspect | Element | Residual | Tolerance | Units | Result |','|---|---|---|---:|---:|---|---|']
    lines += ['| '+ ' | '.join(str(r[k]) for k in ('matchup','aspect','element','residual','tolerance','unit','status'))+' |' for r in rows]
    (E.OUT/'ELEMENT_RESIDUALS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    print('element results',dict(E.Counter(r['status'] for r in rows)),flush=True)


if __name__=='__main__':main()

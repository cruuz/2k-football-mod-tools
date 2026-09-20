"""Six player-scale sheets, always including all four supplied disc r views."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
import player_scale as P

WITNESSES=[
    ('ksnip_20260919-210430.png',(260,591,877,659),dict(clock=177,play_clock=22,down=1)),
    ('ksnip_20260919-210432.png',(267,589,884,657),dict(clock=177,play_clock=15,down=1)),
    ('ksnip_20260919-210434.png',(263,591,880,659),dict(clock=173,play_clock=0,down=1,event='hidden play clock')),
    ('ksnip_20260919-210436.png',(263,589,880,657),dict(clock=173,play_clock=35,down=2)),
]


def main():
    preview=P.sprite.NativePreview();receipts=[];sources=[];rendered={}
    for filename,bounds,state in WITNESSES:
        path=P.HUB/'disc_r_witness_0919'/filename
        image=Image.open(path).convert('RGB');x,y,r,b=bounds
        state=dict(away='WAS',home='LAC',away_score=0,home_score=0,quarter=1,distance=10,possession='away',**state)
        sources.append(dict(filename=filename,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_size=list(image.size),bar_bounds=bounds,state=state,
            before=image.crop((x-7,y-7,r+10,b+8))))
        for wide in (False,True):
            im,receipt=P.draw(preview,state,wide);receipts.append(dict(filename=filename,wide=wide,**receipt))
            rendered[filename,wide]=P.bar(im)
            im.save(P.OUT/f'final_WAS_LAC_{filename[-10:-4]}_{"169" if wide else "43"}.png')
    (P.OUT/'sheets').mkdir(exist_ok=True)
    for matchup in ('WAS_LAC','LV_HOU','DEN_KC'):
        for wide in (False,True):
            aspect='169' if wide else '43'
            sheet=Image.new('RGB',(1320,790),'#252525');d=ImageDraw.Draw(sheet)
            d.text((15,10),f'b72-s10 | {matchup} | {"16:9" if wide else "4:3"} | 617-pixel bar | OFFLINE CANDIDATE',fill='white')
            d.text((15,35),'BEFORE: supplied disc r WAS at LAC, original capture pixels',fill='#ffdb88')
            d.text((675,35),'AFTER: native 448-line HUD, then display upscale',fill='#ffdb88')
            for i,row in enumerate(sources):
                y=63+i*115;state=row['state']
                label=f'{row["filename"]} | {state["down"]}{"st" if state["down"]==1 else "nd"} & 10'
                d.text((15,y),label,fill='white');d.text((675,y),'Same state, offline '+aspect,fill='white')
                sheet.paste(row['before'],(15,y+18));sheet.paste(rendered[row['filename'],wide],(675,y+18))
            ref_name='DEN_KC' if matchup=='WAS_LAC' else matchup
            path,state=P.CASES[ref_name]
            d.text((15,545),'ESPN '+ref_name+' | broadcast bar scaled to 617 pixels',fill='white')
            d.text((675,545),'OFFLINE '+matchup+(' | style comparison, different teams' if matchup=='WAS_LAC' else ' | matching scoreboard values'),fill='white')
            sheet.paste(P.bar(P.reference(path)),(15,568))
            after=rendered[WITNESSES[0][0],wide] if matchup=='WAS_LAC' else P.bar(Image.open(P.OUT/f'final_{matchup}_{aspect}.png'))
            sheet.paste(after,(675,568))
            d.text((15,684),'Every BEFORE is an actual supplied WAS-LAC disc r capture; none is relabelled as another matchup or aspect.',fill='#cccccc')
            d.text((15,707),'No WAS-LAC broadcast or 4:3 game witness supplied. The 4:3 AFTER uses the native 4:3 projection.',fill='#cccccc')
            d.text((15,730),'Display filter is a Lanczos approximation. GPU fixture and screenshot colour calibration remain incomplete.',fill='#cccccc')
            d.text((15,753),'Open at 100 percent for player scale. No magnified residual is counted as a visible gap.',fill='#cccccc')
            sheet.save(P.OUT/'sheets'/f'{matchup}_{aspect}.png')
    P.write('witnesses.json',[{k:v for k,v in r.items() if k!='before'} for r in sources])
    P.write('witness_state_receipts.json',receipts)
    print('Wrote six sheets, four genuine before views per sheet, both native aspect projections.')


if __name__=='__main__':main()

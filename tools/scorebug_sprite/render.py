"""Render any sprite matchup using compiled resources and the native CPU harness.

This command reports its calibration gate. A bright software label is not proof
that the screenshot mismatch has been solved.
"""
from pathlib import Path
import argparse
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core.nfl2k5_scorebug_resources import TEAM_LOGOS

STATES={
    'normal':{}, '1st_and_10':dict(down=1,distance=10),
    'first_and_ten':dict(down=1,distance=10), '2nd_and_10':dict(down=2,distance=10),
    'short_yardage':dict(down=3,distance=1),'third_and_long':dict(down=3,distance=12),
    'fourth_down':dict(down=4,distance=8),'goal_to_go':dict(down=1,distance=5,goal_to_go=True),
    'flag':dict(event='FLAG'),'fumble':dict(event='FUMBLE'),'field_goal_setup':dict(down=4,distance=3,event='ball on'),
    'two_minute':dict(clock=120),'end_of_quarter':dict(clock=0),
    'raiders_ball':dict(away='DET',home='LV',away_score=0,home_score=7,down=1,distance=10,clock=300,quarter=1,play_clock=29,possession='home'),
    'lions_ball':dict(away='DET',home='LV',away_score=0,home_score=7,down=2,distance=10,clock=300,quarter=1,possession='away'),
}


def team(value):
    value=value.upper().replace(' ','_')
    aliases={'OAK':'LV','RAIDERS':'LV','LIONS':'DET','CHIEFS':'KC','BRONCOS':'DEN','SD':'LAC','STL':'LAR','WAS':'WSH'}
    names=json.loads((ROOT/'data/nfl2k5_team_names_2026.json').read_text())
    codes={r['asset_code']:k for k,r in TEAM_LOGOS.items()}
    aliases.update({r['retail']['nickname'].upper():codes[r['retail']['asset_code']] for r in names['teams']})
    value=aliases.get(value,value)
    if value not in TEAM_LOGOS:raise ValueError('Unknown team: '+value)
    return value


def state_for(name,away=None,home=None,possession=None):
    state=json.loads(name) if name.lstrip().startswith('{') else dict(STATES[name])
    for key,value in [('away',away),('home',home),('possession',possession)]:
        if value is not None:state[key]=team(value) if key!='possession' else value
    return sprite.normalize_state(state)


def render(preview,state,aspect,path):
    from PIL import Image
    import nfl2k5_scorebug_projection as projection
    from tools.scorebug_sprite.jev.descriptors import describe
    wide=aspect=='16:9';g,c=preview.capture(state,wide);mode=preview.modes[wide]
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='sprite-preview-') as folder:
            raster_path=Path(folder)/'hud.png'
            receipt=projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,raster_path,
                texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#303030'))
            image=Image.open(raster_path).convert('RGB').crop((0,16,640,464)).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
            image.save(path)
        result=dict(state=state,aspect=aspect,descriptor=describe(image,aspect=aspect),raster=receipt,
            appended_bytes=mode['volume']['appended_bytes'],runtime_witnessed=False,
            calibration=dict(passed=False,reason='Disc-o dark-label reproduction is unresolved; native CPU geometry and software sampling only.'))
        path.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
        return image,result
    finally:c['machine'].close()


def contact_sheet(preview,path,aspect='16:9'):
    from PIL import Image,ImageDraw
    names=sorted(TEAM_LOGOS);sheet=Image.new('RGB',(800,64*len(names)//2),'#202020');draw=ImageDraw.Draw(sheet)
    with tempfile.TemporaryDirectory(prefix='sprite-teams-') as directory:
        for i,name in enumerate(names):
            image,_=render(preview,state_for('1st_and_10',name,name,'home'),aspect,Path(directory)/(name+'.png'))
            offset=(image.width-1920)//2;bar=image.crop((425+offset,938,1490+offset,1057)).resize((395,44))
            x=(i%2)*400;y=(i//2)*64;sheet.paste(bar,(x,y+18));draw.text((x+5,y+2),name,fill='white')
    sheet.save(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--away');p.add_argument('--home');p.add_argument('--state',default='1st_and_10')
    p.add_argument('--aspect',choices=['16:9','4:3'],default='16:9');p.add_argument('--possession',choices=['away','home'])
    p.add_argument('--all-teams',action='store_true');p.add_argument('--folder',type=Path);p.add_argument('--source',type=Path)
    p.add_argument('--output',type=Path,default=Path('scorebug_preview.png'))
    a=p.parse_args();preview=sprite.NativePreview(folder=a.folder,source=a.source)
    if a.all_teams:contact_sheet(preview,a.output,a.aspect)
    else:render(preview,state_for(a.state,a.away,a.home,a.possession),a.aspect,a.output)
    print(a.output);print('Calibration gate: FAIL (disc-o dark-label reproduction unresolved). In-game result unwitnessed.')

if __name__=='__main__':main()

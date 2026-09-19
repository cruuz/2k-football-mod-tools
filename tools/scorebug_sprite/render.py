"""Render sprite matchups through the bounded xemu reference fragment path.

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
    aliases={'OAK':'LV','RAIDERS':'LV','LIONS':'DET','CHIEFS':'KC','BRONCOS':'DEN','SD':'LAC','STL':'LAR','WSH':'WAS','COMMANDERS':'WAS'}
    names=json.loads((ROOT/'data/nfl2k5_team_names_2026.json').read_text())
    codes={r['asset_code']:k for k,r in TEAM_LOGOS.items()}
    aliases.update({r['retail']['nickname'].upper():codes[r['retail']['asset_code']] for r in names['teams']})
    value=aliases.get(value,value)
    from mod_editor.core.nfl2k5_scorebug_teams import load
    if value not in load():raise ValueError('Unknown team: '+value)
    return value


def state_for(name,away=None,home=None,possession=None):
    state=json.loads(name) if name.lstrip().startswith('{') else dict(STATES[name])
    for key,value in [('away',away),('home',home),('possession',possession)]:
        if value is not None:state[key]=team(value) if key!='possession' else value
    return sprite.normalize_state(state)


def render(preview,state,aspect,path,*,naive=False):
    from PIL import Image,ImageDraw
    import nfl2k5_scorebug_projection as projection
    from tools.scorebug_sprite.jev.descriptors import describe
    wide=aspect=='16:9';g,c=preview.capture(state,wide);mode=preview.modes[wide]
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        pipeline=None
        if not naive:
            from tools.scorebug_sprite.gpu import capture_state
            from tools.scorebug_sprite.xemu_model import Pipeline
            pipeline=Pipeline(capture_state(c))
        with tempfile.TemporaryDirectory(prefix='sprite-preview-') as folder:
            raster_path=Path(folder)/'hud.png'
            receipt=projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,raster_path,
                texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#303030'),gpu_pipeline=pipeline)
            image=Image.open(raster_path).convert('RGB').crop((0,16,640,464)).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
            ImageDraw.Draw(image).text((20,20),('NAIVE' if naive else 'XEMU FRAGMENT MODEL')+
                ' / CALIBRATION FAILED / NOT A GAME CAPTURE',fill='#ffcc66')
            image.save(path)
        light_clock=next(r for r in mode['compiled'].spec['fields'] if r['name']=='clock')['colour']=='#FFFFFF'
        result=dict(state=state,aspect=aspect,descriptor=describe(image,aspect=aspect,light_clock=light_clock),raster=receipt,
            appended_bytes=mode['volume']['appended_bytes'],runtime_witnessed=False,
            preview_path='naive' if naive else 'xemu-model',
            calibration=dict(passed=False,reason='Dark-label reproduction unresolved; preceding frame GPU state and surface-scale coverage are not captured.'))
        path.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
        return image,result
    finally:c['machine'].close()


def contact_sheet(preview,path,aspect='16:9',*,naive=False):
    from PIL import Image,ImageDraw
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    from mod_editor.core.nfl2k5_scorebug_teams import load
    teams=load();names=sorted(teams);sheet=Image.new('RGB',(800,20+64*len(names)//2),'#202020');draw=ImageDraw.Draw(sheet)
    draw.text((5,4),('NAIVE' if naive else 'XEMU FRAGMENT MODEL')+
        ' / CALIBRATION FAILED / NOT A GAME CAPTURE',fill='#ffcc66')
    rows=[]
    with tempfile.TemporaryDirectory(prefix='sprite-teams-') as directory:
        for i,name in enumerate(names):
            image,receipt=render(preview,state_for('1st_and_10',name,name,'home'),aspect,Path(directory)/(name+'.png'),naive=naive)
            rows.append(dict(team=name,review_required=teams[name]['review_required'],down=receipt['descriptor']['fields']['down'],plate=receipt['descriptor']['fields']['plate']))
            offset=(image.width-1920)//2;bar=image.crop((425+offset,938,1490+offset,1057)).resize((395,44))
            x=(i%2)*400;y=20+(i//2)*64;sheet.paste(bar,(x,y+18));draw.text((x+5,y+2),name+(' REVIEW' if teams[name]['review_required'] else ''),fill='white')
    sheet.save(path)
    path.with_suffix('.json').write_text(json.dumps(dict(aspect=aspect,teams=rows,calibration_passed=False,
        preview_path='naive' if naive else 'xemu-model',
        limitation='52 roster tint slots; extra slots use neutral logos. GPU calibration is unresolved; these are model predictions.'),indent=2)+'\n',encoding='utf-8',newline='\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--away');p.add_argument('--home');p.add_argument('--state',default='1st_and_10')
    p.add_argument('--aspect',choices=['16:9','4:3'],default='16:9');p.add_argument('--possession',choices=['away','home'])
    p.add_argument('--all-teams',action='store_true');p.add_argument('--folder',type=Path);p.add_argument('--source',type=Path)
    p.add_argument('--naive',action='store_true',help='Use the former texture-times-vertex preview for comparison')
    p.add_argument('--output',type=Path,default=Path('scorebug_preview.png'))
    a=p.parse_args();preview=sprite.NativePreview(folder=a.folder,source=a.source)
    if a.all_teams:contact_sheet(preview,a.output,a.aspect,naive=a.naive)
    else:render(preview,state_for(a.state,a.away,a.home,a.possession),a.aspect,a.output,naive=a.naive)
    print(a.output);print('Calibration gate: FAIL (dark-label reproduction unresolved). In-game result unwitnessed.')

if __name__=='__main__':main()

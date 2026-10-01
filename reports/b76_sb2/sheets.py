"""PROVED OFFLINE: identical state TV/native crop sheets in both aspects, with before/after ink measurements."""
from pathlib import Path
import json,sys,tempfile,subprocess
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parent))
from render import render,sprite,ROOT,OUT,SCRATCH
from measure import ink,measure
from mod_editor.core import nfl2k5_scorebug_teams as teams
BASE='6bd9b3d66d239a267f8d4f66e083b8a6eb320671'
COMMON=dict(away='PHI',home='CHI',away_score=0,home_score=7,quarter=1,clock=0,play_clock=40,down=1,distance=10,possession='home',broadcast='monday_night',away_record=[2,0,0],home_record=[1,1,0])
ROWS=[
 ('chi_interim',28,dict(away_score=0,home_score=0,clock=887,down=2,previous_down=1)),
 ('chi_first10',41,dict(home_score=0,clock=781,play_clock=38)),
 ('phi_first10',113,dict(clock=519,possession='away')),
 ('fourth1_white6',69,dict(home_score=0,clock=654,play_clock=6,down=4,distance=1)),
 ('fourth1_red5',70,dict(home_score=0,clock=653,play_clock=5,down=4,distance=1)),
 ('third16',144,dict(clock=417,play_clock=17,down=3,distance=16,possession='away')),
 ('flag',245,dict(quarter=2,clock=895,play_clock=25,event='FLAG')),
 ('chi_goal',270,dict(quarter=2,clock=880,play_clock=31,down=2,goal_to_go=True)),
 ('phi_goal',510,dict(quarter=2,home_score=10,clock=0,play_clock=30,down=2,goal_to_go=True,possession='away',away_timeouts=0)),
 ('player_tags_ESPN',188,dict(clock=119,event='hang time')),
 ('post_punt_ESPN',194,dict(clock=113,play_clock=25,event='ball on')),
 ('red2',530,dict(away_score=7,home_score=10,quarter=3,clock=818,play_clock=2,down=3,distance=5,possession='away')),
 ('under_minute',230,dict(clock=5,down=2,distance=12))]

def main():
    data=teams.DATA; allmetrics={};images={}
    with tempfile.TemporaryDirectory(prefix='sb2-base-') as td:
      base=Path(td)
      for p in data.iterdir():
       if p.is_file():
        (base/p.name).write_bytes(subprocess.check_output(['git','show',BASE+':'+str(p.relative_to(ROOT))]))
      for version,folder in [('before',base),('after',data)]:
       teams.DATA=folder;preview=sprite.NativePreview(folder=folder)
       for wide in (True,False):
        # Baseline 4:3 repeats no changed aspect logic; after is required in both aspects.
        if not wide and version=='before':continue
        aspect='169' if wide else '43'; dx=0 if wide else -240
        for name,t,st in ROWS:
         image,receipt=render(preview,dict(COMMON,**st),wide)
         crop=image.crop((400+dx,820,1500+dx,1060));a=np.array(crop)
         key=f'{version}_{name}_{aspect}';images[key]=crop
         crop.save(SCRATCH/(key+'.png'))
         label=ink(a,(844,946,1078,984),name=='flag')
         allmetrics[key]=dict(receipt,label_ink=label)
         if version=='after' and wide:
          tv=np.array(Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png'))
          allmetrics[key]['broadcast']=dict(bin=t,label_ink=ink(tv,(844,946,1078,984),name=='flag'),measure=measure(tv))
       print(version,'done',flush=True)
      teams.DATA=data
    for aspect in ('169','43'):
     sheet=Image.new('RGB',(2220,65+280*len(ROWS)),'#202020');d=ImageDraw.Draw(sheet)
     d.text((10,8),'PROVED OFFLINE | ESPN broadcast (left) and native owner projection (right)',fill='white')
     d.text((10,28),f'{aspect} | 640x448 HUD enlarged for comparison | GPU calibration unresolved | NOT A GAME CAPTURE',fill='#ffd080')
     for i,(name,t,st) in enumerate(ROWS):
      y=65+i*280;tv=Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png');sheet.paste(tv,(0,y+25));sheet.paste(images[f'after_{name}_{aspect}'],(1120,y+25))
      d.text((10,y),f'{name} / NFL bin {t}s',fill='white')
      note='PLAYER TAGS UNIMPLEMENTED; bar state only' if 'tags' in name else 'same visible state; official team marks'
      d.text((1130,y),note,fill='white')
     sheet.save(SCRATCH/f'SB2_side_by_side_{aspect}.png')
    (OUT/'render_readback.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',renders=allmetrics),indent=2)+'\n')
    (OUT/'sheet_states.json').write_text(json.dumps(dict(classification='DESIGN',common=COMMON,rows=ROWS,unobserved='Distance underneath interim/FLAG is a preview input, not measured; event/phase inputs emulate the observed plate; no player-tag implementation.'),indent=2)+'\n')
if __name__=='__main__':main()

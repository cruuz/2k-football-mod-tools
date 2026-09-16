"""Capture native sprite streams, measure layout/ink, and publish paired crops."""
from pathlib import Path
import hashlib,json,struct,sys,time
from PIL import Image,ImageDraw
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'reports/b71_s4')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite,nfl2k5_scorebug_exact as exact
import nfl2k5_scorebug_projection as projection
import nfl2k5_scorebug_exact as comparison
from prove_v4 import measure
OUT=ROOT/'reports/b71_s6'
REFERENCE=Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
DAY=Path('/home/noah/Desktop/2K5-8 Editors/beta71_evidence/day/ksnip_20260915-154929.png')
STATES=[('standard',{}),('no_at_den',dict(away='NO',home='DEN',possession='away'))]
STATES += [('score_'+str(n),dict(away_score=n,home_score=n)) for n in (0,28,100)]
STATES += [('clock_007',dict(clock=7)),('play_12',dict(play_clock=12)),('play_3',dict(play_clock=3))]
STATES += [('down_'+str(n),dict(down=n)) for n in range(1,5)]
STATES += [('overtime',dict(quarter=5)),('inches',dict(distance=0)),('goal',dict(goal_to_go=True))]
STATES += [('timeouts_'+str(n),dict(away_timeouts=n,home_timeouts=n)) for n in range(4)]
STATES += [(e.replace(' ','_').lower(),dict(event=e)) for e in ('FLAG','FUMBLE','hang time','ball on','score slabs','hidden play clock')]

def box(points):return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
def bounds(g,rows):return box([p for q in rows for p in g['positions'][q['vertex']:q['vertex']+4]])
def main():
 p=sprite.NativePreview();c=p.compiled;states={};measurements={};contact=[]
 source=Image.open(REFERENCE).convert('RGB');target=Image.new('RGB',(640,480));target.paste(source.resize((640,448),Image.Resampling.LANCZOS),(0,16))
 crop=(420,930,1500,1060);reference_crop=source.crop(crop).resize((2160,260),Image.Resampling.LANCZOS)
 for wide in (False,True):
  aspect='169' if wide else '43'
  for name,state in STATES:
   started=time.monotonic();g,cap=p.capture(state,wide)
   try:
    live=cap['live_decoded'];path=OUT/(name+'_'+aspect+'.png')
    picture=target
    if wide:picture=comparison.wide_reference(target)
    raster=projection.render_native(live,p.atlas,p.fonts,g,path,texture_spans=cap['texture_spans'],background=picture)
    im=Image.open(path).convert('RGB');restored=im.crop((50 if wide else 0,16,590 if wide else 640,464)).resize((1920,1080),Image.Resampling.LANCZOS)
    output_crop=restored.crop(crop);output_crop.save(OUT/(name+'_'+aspect+'_crop.png'))
    panel=Image.new('RGB',(2160,554),'#16191d');panel.paste(reference_crop,(0,18));panel.paste(output_crop.resize((2160,260),Image.Resampling.LANCZOS),(0,294))
    d=ImageDraw.Draw(panel);d.text((8,2),'ESPN reference',fill='white');d.text((8,278),'Sprite native output / '+name+' / '+aspect,fill='white');panel.save(OUT/(name+'_'+aspect+'_compare_2x.png'))
    rows=[q for q in c.quads if not q['dynamic'] or struct.unpack_from('<I',live,0x2d20+q['vertex']*10)[0]]
    fieldboxes={f['name']:bounds(g,[q for q in rows if q['name'].startswith(f['name']+':')]) for f in c.spec['fields'] if any(q['name'].startswith(f['name']+':') for q in rows)}
    state_receipt=dict(state=sprite.normalize_state(state),glyph_boxes=fieldboxes,
       retail_draws=[dict(text=r['text'],font=r['font'],quads=len(r['vertices'])//4) for r in g['draws'] if r['vertices']],
       sprite_quads=len(rows),winding=raster['winding'],runtime_witnessed=False)
    states[name+'_'+aspect]=state_receipt
    if name=='standard':
     geometryboxes={q['name']:bounds(g,[q]) for q in rows if not q['dynamic']}
     geometryboxes['bar']=bounds(g,[q for q in rows if q['name'] in ('body_left','body','body_right')])
     # Every static quad is checked against its authored source rectangle.
     checks={}
     for q in rows:
      if q['dynamic']:continue
      want=list(exact.hud_box(q['box']))
      if wide:
       for k in (0,2):want[k]=320+(want[k]-320)*27/32
      actual=geometryboxes[q['name']]
      checks[q['name']]=dict(source=q['box'],native=actual,max_hud_error=max(abs(x-y) for x,y in zip(actual,want)))
     glyphs={}
     for role,wantsource in c.spec['reference_boxes'].items():
      if role=='bar':continue
      want=list(exact.hud_box(wantsource))
      if wide:
       for k in (0,2):want[k]=320+(want[k]-320)*27/32
      actual=fieldboxes[role]
      roi=[int(wantsource[0]-8),int(wantsource[1]-5),int(wantsource[2]+8),int(wantsource[3]+5)]
      try:ink=measure(restored,roi,'dark' if role in ('clock','quarter') else 'white')
      except ValueError:ink=None
      inkerror=None if ink is None else max(abs(a-b)*(27/32 if wide and i in (0,2) else 1)*(1/3 if i in (0,2) else 448/1080) for i,(a,b) in enumerate(zip(ink,wantsource)))
      glyphs[role]=dict(source=wantsource,native=actual,max_hud_error=max(abs(x-y) for x,y in zip(actual,want)),ink_source=ink,ink_hud_error=inkerror)
     g['frame']=geometryboxes['bar'];g['down']=geometryboxes['plate'];g['clock']=geometryboxes['capsule'];g['comparison_regions']=geometryboxes
     result=comparison.compare(picture,im,g,{},runtime=True,regions={q['name']:q['box'] for q in c.quads if not q['dynamic']})
     measurements[aspect]=dict(static=checks,glyphs=glyphs,comparison=result)
     p.render(OUT/('day_'+aspect+'.png'),screenshot=DAY,state=state,widescreen=wide)
    thumb=output_crop.resize((864,104),Image.Resampling.LANCZOS);contact.append((name+' / '+aspect,thumb))
    print(name,aspect,round(time.monotonic()-started,2),state_receipt['retail_draws'],flush=True)
   finally:cap['machine'].close()
 board=Image.new('RGB',(1728,126*((len(contact)+1)//2)),'#16191d');d=ImageDraw.Draw(board)
 for i,(label,im) in enumerate(contact):x=(i%2)*864;y=(i//2)*126;d.text((x+4,y+2),label,fill='white');board.paste(im,(x,y+20))
 board.save(OUT/'states_contact_sheet.png')
 (OUT/'states.json').write_text(json.dumps(states,indent=2)+'\n')
 (OUT/'measurements.json').write_text(json.dumps(measurements,indent=2)+'\n')
 (OUT/'volume.json').write_text(json.dumps(p.volume,indent=2)+'\n')
 failures=[(a,n,r['max_hud_error']) for a,v in measurements.items() for n,r in (v['static']|v['glyphs']).items() if r['max_hud_error']>1 or ('ink_hud_error' in r and (r['ink_hud_error'] is None or r['ink_hud_error']>1))]
 print('BOUNDARY_FAILURES',failures,flush=True)
 if failures:raise SystemExit(1)
if __name__=='__main__':main()

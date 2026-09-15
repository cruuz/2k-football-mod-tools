"""Native v4 renders, frame-measured text boxes, boundary and pixel comparisons."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import nfl2k5_scorebug_exact as comparison
from mod_editor.core import nfl2k5_scorebug_exact as exact,nfl2k5_scorebug_resources as resources
from mod_editor.core import nfl2k5_scorebug_runtime as owner

REFERENCE=Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
OUT=ROOT/'reports/b71_s4'
ROIS={
 'away_score':((730,960,785,1025),'white'), 'home_score':((1130,960,1188,1025),'white'),
 'down':((850,950,1060,995),'white'), 'quarter':((847,1004,903,1034),'dark'),
 'clock':((910,1000,1010,1039),'dark'), 'play_clock':((1036,1004,1066,1035),'white'),
 'away_ticks':((712,1027,801,1042),'white'), 'home_ticks':((1116,1027,1204,1042),'white')}

def measure(source,box,polarity):
 a,b,c,d=box;pix=np.asarray(source)[b:d,a:c]
 hit=pix.min(axis=2)>180 if polarity=='white' else pix.max(axis=2)<150
 seen=np.zeros_like(hit);ink=[]
 for y,x in np.argwhere(hit):
  if seen[y,x]:continue
  queue=[(int(y),int(x))];component=[];seen[y,x]=True
  while queue:
   yy,xx=queue.pop();component.append((yy,xx))
   for dy in (-1,0,1):
    for dx in (-1,0,1):
     ny,nx=yy+dy,xx+dx
     if 0<=ny<hit.shape[0] and 0<=nx<hit.shape[1] and hit[ny,nx] and not seen[ny,nx]:
      seen[ny,nx]=True;queue.append((ny,nx))
  if len(component)>=3 and not any(yy in (0,hit.shape[0]-1) or xx in (0,hit.shape[1]-1) for yy,xx in component):ink.extend(component)
 if not ink:raise ValueError('empty glyph ROI after excluding edge fragments')
 ys,xs=map(np.asarray,zip(*ink))
 return [a+int(xs.min()),b+int(ys.min()),a+int(xs.max())+1,b+int(ys.max())+1]

def main():
 args=argparse.ArgumentParser();args.add_argument('--reference',type=Path,default=REFERENCE);args=args.parse_args()
 source=Image.open(args.reference).convert('RGB');assert source.size==(1920,1080)
 measured={'away_score':[736,965,776,1018],'home_score':[1138,965,1180,1018],
     'down':[898,955,1021,978],'quarter':[850,1009,892,1028], 'clock':[920,1006,1000,1033],
     'play_clock':[1042,1009,1057,1028],'away_ticks':[717,1032,796,1038],'home_ticks':[1120,1032,1198,1038]}
 target=Image.new('RGB',(640,480));target.paste(source.resize((640,448),Image.Resampling.LANCZOS),(0,16))
 pack=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0';build=comparison.Build(pack,pack.parents[1]/'default.xbe')
 results={}
 try:
  for wide in (False,True):
   label='wide' if wide else '43';path=OUT/('render_'+label+'.png')
   g=build.render(path,runtime=True,widescreen=wide,matchup=('DEN','KC'),score_values=(7,7),previous_scores=(7,7),quarter=2,game_seconds=273,play_seconds=4,down=3)
   callback_roles={}
   for row in g['draws']:
    if not row['vertices']:continue
    text=row['text'];box=comparison.box_of([v['screen'] for v in row['vertices']])
    if text=='\x87':role='away_score' if box[0]<320 else 'home_score'
    elif text=='~ ~ ~':role='away_ticks' if box[0]<320 else 'home_ticks'
    elif text=='3rd & 10':role='down'
    elif text=='2ND':role='quarter'
    elif text=='´:³³':role='clock'
    elif text=='Ä':role='play_clock'
    else:continue
    callback_roles[row['callback']]=role
    comparison.TEXT_ROIS[row['callback']]=ROIS[role][0]
   text_boxes={cb:list(exact.hud_box(measured[role])) for cb,role in callback_roles.items()}
   # compare()'s legacy callback list cannot know relocated private callbacks.
   # Supply the measured v4 role polarity for its independent ink diagnostic.
   def native_ink(pixels,callback,widescreen=False):
    roi,polarity=ROIS[callback_roles[callback]];box=list(exact.hud_box(roi))
    if widescreen:
     for i in (0,2):box[i]=320+(box[i]-320)*27/32
    try:return measure(Image.fromarray(pixels),tuple(map(round,box)),polarity)
    except ValueError:return None
   comparison.rendered_text_ink=native_ink
   result=comparison.compare(comparison.wide_reference(target) if wide else target,Image.open(path),g,text_boxes,runtime=True,regions=exact.MNF_COMPARE_REGIONS)
   # Native vertices are measured separately for the logo quad, cell and pointer.
   vertices={name:layout['logo'] for name,layout in exact.MNF_WING_LAYOUT.items()}
   vertices.update(play_clock_cell=range(262,266),pointer=range(76,80))
   extra={}
   for name,ids in vertices.items():
    actual=comparison.box_of([g['positions'][i] for i in ids])
    source_box=exact.MNF_SOURCE[name+'_logo'] if name in ('away','home') else (1019,999,1082,1040) if name=='play_clock_cell' else (951,942,965,947)
    want=list(exact.hud_box(source_box))
    if wide:
     for i in (0,2):want[i]=320+(want[i]-320)*27/32
    extra[name]=dict(reference_source_box=source_box,native_box=actual,native_boundary_error_px=max(abs(x-y) for x,y in zip(actual,want)))
   result.update(extra_regions=extra,callback_roles=callback_roles,winding=g['winding'])
   results[label]=result
   comparison.write_json(OUT/('render_'+label+'.json'),g)
   rendered=Image.open(path).convert('RGB')
   # Restore source-frame coordinates for directly comparable crops, including
   # the existing 27/32 HUD contraction in widescreen.
   render_source=rendered.crop((50 if wide else 0,16,590 if wide else 640,464)).resize((1920,1080),Image.Resampling.LANCZOS)
   result['rendered_text_source_boxes']={}
   for role,spec in ROIS.items():
    try: ink=measure(render_source,*spec)
    except ValueError: ink=None
    result['rendered_text_source_boxes'][role]=dict(box=ink,reference_box=measured[role],
        max_source_pixel_error=None if ink is None else max(abs(a-b) for a,b in zip(ink,measured[role])))
   crop_box=(425,933,1490,1060)
   ref_crop=source.crop(crop_box);crop=render_source.crop(crop_box)
   crop.save(OUT/('render_'+label+'_crop.png'))
   panel=Image.new('RGB',(ref_crop.width,ref_crop.height*2+10),'#202020')
   panel.paste(ref_crop,(0,0));panel.paste(crop,(0,ref_crop.height+10))
   panel=panel.resize((panel.width*2,panel.height*2),Image.Resampling.NEAREST)
   panel.save(OUT/('compare_'+label+'.png'))
  for wide in (False,True):
   label='no_den_'+('wide' if wide else '43')
   g=build.render(OUT/(label+'.png'),runtime=True,widescreen=wide,matchup=('NO','DEN'),possession='away',score_values=(7,7),previous_scores=(7,7))
   comparison.write_json(OUT/(label+'.json'),g)
  comparison.write_json(OUT/'comparison-diagnostic.json',results)
  # Every retail event uses its native visibility and formatter in both aspects.
  states={'live_clock_hidden':(), 'flag':(3,), 'score':(5,), 'hang_time':(2,), 'ball_on':(4,), 'all_events':(0,1,2,3,4,5)}
  state_results={}
  for name,elements in states.items():
   for wide in (False,True):
    label=name+('_wide' if wide else '_43');path=OUT/(label+'.png')
    g=build.render(path,runtime=True,widescreen=wide,visible_elements=elements if name=='live_clock_hidden' else (1,)+elements,matchup=('DEN','KC'))
    state_results[label]=dict(text=[dict(text=r['text'],font=r['font'],color=r['color'],box=comparison.box_of([v['screen'] for v in r['vertices']])) for r in g['draws'] if r['vertices']],containment=g.get('containment'),visible_materials=[r['name'] for r in g['materials'] if r['visible']])
    Image.open(path).crop((140,397,499,459)).resize((1077,186)).save(OUT/(label+'_crop.png'))
  comparison.write_json(OUT/'states.json',state_results)
  multi={}
  for score in (28,100,999):
   for wide in (False,True):
    label=str(score)+('_wide' if wide else '_43');path=OUT/('scores_'+label+'.png')
    g=build.render(path,runtime=True,widescreen=wide,matchup=('DEN','KC'),score_values=(score,score),previous_scores=(score,score))
    boxes=[comparison.box_of([v['screen'] for v in r['vertices']]) for r in g['draws'] if r['text'] and 0x80<=ord(r['text'][0])<=0x99]
    assert len(boxes)==2 and all(box[2]<=g['down'][0] or box[0]>=g['down'][2] for box in boxes)
    multi[label]=dict(score_boxes=boxes,plate=g['down'],no_plate_overlap=True)
    Image.open(path).crop((140,397,499,459)).resize((1077,186)).save(OUT/('scores_'+label+'_crop.png'))
  comparison.write_json(OUT/'multi_digit_scores.json',multi)
 finally:build.close()
 result=dict(reference=dict(path=str(args.reference),sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),size=source.size,text_source_boxes=measured),volume=dict(appended_bytes=resources.probe_sizes('mnf')[1],font_bytes=resources.CLOCK_FONT_SPAN_SIZE,texture_count=66),comparisons=results,limits='Native CPU execution with software raster; no GPU or played-game witness. Widescreen comparison includes the existing 27/32 HUD transform.')
 comparison.write_json(OUT/'measurements.json',result)
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()

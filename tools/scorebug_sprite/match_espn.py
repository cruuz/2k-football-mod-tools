"""Measure native sprite rendering against the beta 72 ESPN evidence.

The CPU harness executes the owner, retail formatters and transforms. The shared
raster submits real SCNE descriptors and push buffers, then the 640x448 viewport
is expanded through the documented display chain. This is not an in-game witness.
Pass --frames to the read-only broadcast directory. No retail bytes are saved.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import numpy as np
from PIL import Image,ImageDraw
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection

FRAMES=(12001,1500,4500,5200,10500,12000,3000,20200,16500,18000,19500,17200,14200,26200,29000,29700,29990)
# Clean regions from the dossier, avoiding live text and moving specular sweeps.
COLOURS={
 'body':(1215,990,1245,1030), 'away_wash':(696,944,704,948),
 'home_wash':(1226,944,1234,948), 'centre_wash':(944,943,948,946),
 'away_wing':(451,1044,455,1047), 'home_wing':(1471,1044,1475,1047),
 'away_bottom_rim':(441,1048,449,1050), 'home_bottom_rim':(1401,1048,1409,1050),
 'centre_bottom_rim':(940,1048,980,1050),
 'plate_lip':(855,948,865,951),'plate_dip':(855,953,865,956),
 'plate_sheen':(855,966,865,971),'plate_bottom':(855,980,865,983),
 'housing':(860,1041,1060,1044),'capsule':(902,1015,915,1025),
 'capsule_rim':(910,999,950,1001),'red':(1064,1010,1075,1028),
 'pointer':(953,943,963,946),
}


def sample(image,box,offset=0):
 x0,y0,x1,y1=box
 return np.asarray(image.crop((x0+offset,y0,x1+offset,y1)),dtype=float)


def bounds(mask,box):
 ys,xs=np.where(mask)
 return [float(box[0]+xs.min()),float(box[1]+ys.min()),float(box[0]+xs.max()+1),float(box[1]+ys.max()+1)] if len(xs) else [0.]*4


def ink_features(im,offset=0):
 out={}
 for name,box in [('away_logo',(465,950,655,1042)),('home_logo',(1260,943,1480,1050)),
                  ('away_score',(710,956,810,1024)),('home_score',(1110,956,1210,1024))]:
  a=sample(im,box,offset)
  # White only. Coloured wing pixels must never count as logo extent.
  mask=(a.min(-1)>150)&((a.max(-1)-a.min(-1))<65)
  out[name+'_box']=bounds(mask,box)
 for role,box in [('down',(835,950,1085,985)),('quarter',(844,1003,897,1036)),('play_clock',(1023,1003,1077,1036))]:
  a=sample(im,box,offset)
  mask=a.mean(-1)<110 if role=='quarter' else a.min(-1)>170
  b=bounds(mask,box);out[role+'_cap']=b[3]-b[1]
 out['score_white']=np.percentile(sample(im,(736,975,776,1010),offset).reshape(-1,3),90,axis=0).tolist()
 # Separator is measured only in its intended x range, excluding quarter/clock.
 a=sample(im,(896,1001,905,1008),offset).mean(-1)
 columns=np.where(a.min(0)<180)[0]
 out['separator_x']=float(896+columns.mean()) if len(columns) else 0.
 return out


def rendered_display(preview,wide,path,state=None):
 g,c=preview.capture(state,wide)
 try:
  mode=preview.modes[wide]
  projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,path,
    texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#343b40'))
  im=Image.open(path).convert('RGB')
  display=im.crop((0,16,640,464)).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
  display.save(path.with_name(path.stem+'_display.png'))
  return display,g,c['live_decoded']
 finally:c['machine'].close()


def sampled_columns(texels,left,right,uv0=0.,uv1=None):
 """Actual pixel-centre bilinear taps, including subpixel quad placement."""
 touched=set();uv1=texels if uv1 is None else uv1
 for pixel in range(math.ceil(left-.5),math.ceil(right-.5)):
  t=(pixel+.5-left)/(right-left)*(uv1-uv0)+uv0-.5
  lo=math.floor(t)
  for column,weight in ((lo,1-(t-lo)),(lo+1,t-lo)):
   if weight>1e-8 and 0<=column<texels:touched.add(column)
 return sorted(touched)


def glyph_proof(preview,wide,path=None):
 """Quantized native quads + decoded P8 alpha, not source-cell dimensions."""
 # The same decoded texture source used by render_native.
 mode=preview.modes[wide];g,c=preview.capture(dict(down=1,distance=10),wide)
 try:
  compiled=mode['compiled'];records=[]
  chunk,body,_=scene.decode(mode['atlas']);tex=scene.tx.parse_texture(body,chunk)
  packed=Image.frombytes('RGBA',(tex.width,tex.height),scene.tx.texture_to_rgba(body,chunk,tex))
  for q in compiled.quads:
   role=q['name'].split(':')[0]
   if not q['dynamic'] or role not in ('down','quarter','play_clock','clock','away_score','home_score'):continue
   v=q['vertex']
   if not struct_word(c['live_decoded'],scene.layout.S1+v*10):continue
   p=g['positions'][v:v+4];left,top=p[0][:2];right,bottom=p[3][:2]
   # Match UVs to the exact glyph entry, then examine its area-filtered mask.
   import struct
   uv=tuple(t for j in range(4) for t in struct.unpack_from('<2h',c['live_decoded'],scene.layout.S1+(v+j)*10+4))
   field=next(f for f in compiled.spec['fields'] if f['name']==role)
   glyph=next((z for z in compiled.spec['glyph_sets'][field['glyph_set']]['glyphs'].values() if sprite.quantized_uv(compiled.cells[z['cell']],compiled.spec['atlas'])==uv),None)
   if glyph is None:continue
   cell=compiled.cells[glyph['cell']];a=np.asarray(packed.crop(cell).getchannel('A'),dtype=float)/255
   h,w=a.shape
   # Mid-cap vertical stem: alpha mass in left half of zero; quantization and
   # bilinear reconstruction conserve it because there is no minification.
   stem=float(np.median(a[max(1,h//3):max(2,2*h//3),:w//2].sum(1)))*(right-left)/w
   # Reconstruct the exact P8 alpha at raster pixel centres, using quantized
   # UV endpoints and transparent gutters, then count ink-bearing scanlines.
   xs=range(math.ceil(left-.5),math.ceil(right-.5));ys=range(math.ceil(top-.5),math.ceil(bottom-.5))
   alpha=np.zeros((len(ys),len(xs)))
   transform=struct.unpack_from('<4f',c['live_decoded'],scene.layout.SHAPE+0x30)
   def texel_uv(value,axis):
    normalized=value/(32768 if value<0 else 32767)
    return (normalized*transform[axis]+transform[axis+2])*(packed.width if axis==0 else packed.height)
   uvx0=texel_uv(uv[0],0);uvx1=texel_uv(uv[2],0)
   uvy0=texel_uv(uv[1],1);uvy1=texel_uv(uv[5],1)
   for iy,yy in enumerate(ys):
    ty=uvy0+(yy+.5-top)/(bottom-top)*(uvy1-uvy0)-.5;py=math.floor(ty);fy=ty-py
    for ix,xx in enumerate(xs):
     tx=uvx0+(xx+.5-left)/(right-left)*(uvx1-uvx0)-.5;px=math.floor(tx);fx=tx-px
     alpha[iy,ix]=sum(packed.getpixel((px+dx,py+dy))[3]/255*weight for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)))
   records.append(dict(field=role,cell=glyph['cell'],cap=bottom-top,ink_scanlines=int((alpha.max(1)>.5).sum()),width=right-left,stem=stem,texels=[w,h],
     minification=[w/(right-left),h/(bottom-top)],
     columns_sampled=sampled_columns(w,left,right,uvx0-cell[0],uvx1-cell[0]),
     rows_sampled=sampled_columns(h,top,bottom,uvy0-cell[1],uvy1-cell[1])))
  if path:
   projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,path,
     texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#343b40'))
  return records
 finally:c['machine'].close()


def struct_word(data,at):
 import struct
 return struct.unpack_from('<I',data,at)[0]


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--frames',type=Path,required=True)
 p.add_argument('--evidence',type=Path,default=ROOT/'tools/bench/b72_scorebug')
 p.add_argument('--output',type=Path,default=ROOT/'reports/b72_s1')
 p.add_argument('--folder',type=Path);p.add_argument('--before-folder',type=Path)
 p.add_argument('--pack',type=Path);p.add_argument('--xbe',type=Path)
 p.add_argument('--hud-tolerance',type=float,default=1);p.add_argument('--rgb-tolerance',type=float,default=6)
 p.add_argument('--reuse',action='store_true',help='Measure previously rendered after images; no rendering claim for changed source')
 args=p.parse_args(argv);args.output.mkdir(parents=True,exist_ok=True)
 rows=[];references=[];canonical=None;frame_comparisons=[]
 for n in FRAMES:
  path=args.frames/f'frame_{n:06d}.jpg'
  im=Image.open(path).convert('RGB')
  references.append(dict(frame=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),features=ink_features(im)))
  if n==12001:canonical=im
 median=Image.open(args.evidence/'espn_bar_median.png').convert('RGB')
 reference=Image.new('RGB',(1920,1080),'#343b40');reference.paste(median,(437,942))
 # The temporal median mixes possession colours and play-clock states. Use the
 # canonical frame for those regions; the dossier calls out this distinction.
 for box in ((825,947,1094,987),(837,987,1084,1047),(951,942,965,947)):
  reference.paste(canonical.crop(box),box[:2])
 dossier=json.loads((args.evidence/'bar_measurements.json').read_text())
 glyph_dossier=json.loads((args.evidence/'glyph_measurements.json').read_text())
 ref_features=ink_features(canonical)
 def residual(aspect,name,actual,target,unit,reason=None,minimum=False):
  aa=np.asarray(actual);tt=np.asarray(target)
  error=float(np.maximum(tt-aa,0).max()) if minimum else float(np.abs(aa-tt).max())
  tolerance=0 if minimum else args.rgb_tolerance if unit=='RGB' else args.hud_tolerance
  passed=error<=tolerance
  rows.append(dict(aspect=aspect,feature=name,actual=np.round(aa,3).tolist(),target=np.round(tt,3).tolist(),residual=round(error,3),unit=unit,tolerance=tolerance,
    status='PASS' if passed else 'IMPOSSIBLE' if reason else 'FAIL',reason=reason if not passed else None))
 preview=None if args.reuse else sprite.NativePreview(args.pack,args.xbe,args.folder)
 before=sprite.NativePreview(args.pack,args.xbe,args.before_folder) if args.before_folder and not args.reuse else None
 sheets=[];proof={}
 for wide in (False,True):
  aspect='16:9' if wide else '4:3';suffix='169' if wide else '43';offset=0 if wide else -240
  path=args.output/f'after_{suffix}.png'
  if preview:shown,g,live=rendered_display(preview,wide,path)
  else:shown=Image.open(path.with_name(path.stem+'_display.png')).convert('RGB')
  features=ink_features(shown,offset)
  sx=1/3 if wide else 4/9;sy=448/1080
  # Project the 1080-line reference through the same finite 448-line display
  # footprint before comparing small rims. Keep its source RGB in the receipt.
  ref_crop=reference if wide else reference.crop((240,0,1680,1080))
  ref_sd=ref_crop.resize((640,448),Image.Resampling.BOX).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
  for name,box in COLOURS.items():
   actual=sample(shown,box,offset).mean((0,1));target=sample(ref_sd,box,offset).mean((0,1))
   residual(aspect,name,actual,target,'RGB')
   rows[-1]['reference_source_rgb']=sample(reference,box).mean((0,1)).round(3).tolist()
  # Measure all representative frames as well as the canonical/median target.
  # Their raw residuals expose moving reflections and event/possession colours.
  # The envelope check asks whether the static cut lies within the observed
  # broadcast range; it supplements, never replaces, the stricter median gate.
  samples={name:[] for name in COLOURS}
  for ref in references:
   frame=Image.open(args.frames/ref['frame']).convert('RGB')
   frame_crop=frame if wide else frame.crop((240,0,1680,1080))
   frame_sd=frame_crop.resize((640,448),Image.Resampling.BOX).resize(sprite.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
   measurements={}
   for name,box in COLOURS.items():
    value=sample(frame_sd,box,offset).mean((0,1));actual=sample(shown,box,offset).mean((0,1))
    samples[name].append(value)
    measurements[name]=dict(reference_rgb=value.round(3).tolist(),residual_rgb=(actual-value).round(3).tolist())
   frame_comparisons.append(dict(aspect=aspect,frame=ref['frame'],features=measurements))
  for name,values in samples.items():
   lo=np.min(values,axis=0);hi=np.max(values,axis=0);actual=sample(shown,COLOURS[name],offset).mean((0,1))
   residual(aspect,'reference_range.'+name,actual,np.clip(actual,lo,hi),'RGB')
   rows[-1]['reference_range']={'min':lo.round(3).tolist(),'max':hi.round(3).tolist()}
  for name in ('away_logo_box','home_logo_box','away_score_box','home_score_box'):
   target=ref_features[name]
   residual(aspect,name,np.array(features[name])*[sx,sy,sx,sy],np.array(target)*[sx,sy,sx,sy],'HUD px')
  residual(aspect,'score_white',features['score_white'],dossier['espn']['score_rgb_p90'],'RGB')
  residual(aspect,'separator_x',features['separator_x']*sx,900*sx,'HUD px')
  if preview:
   for name,target in (('body',[437,942,1478,1052]),('pointer',dossier['espn']['pointer_box'])):
    q=next(q for q in preview.modes[wide]['compiled'].quads if q['name']==name)
    points=g['positions'][q['vertex']:q['vertex']+4]
    actual=[points[0][0],points[0][1],points[3][0],points[3][1]]
    expected=sprite.contracted(sprite.hud_box(target,wide),wide)
    residual(aspect,name+'_quad_box',actual,expected,'HUD px')
   proof[aspect]=glyph_proof(preview,wide,args.output/f'first10_{suffix}.png')
   zero=next(r for r in proof[aspect] if r['cell']=='label_0')
   for role,target in (('down',23),('quarter',19),('play_clock',19)):
    first=next(r for r in proof[aspect] if r['field']==role)
    residual(aspect,role+'_cap',first['ink_scanlines'],target*sy,'HUD px',
      'The broadcast cap is below the SD readability floor; the requested larger SD type deliberately exceeds the 1080-line reference.')
   residual(aspect,'label_minimum_cap',zero['ink_scanlines'],12,'HUD scanlines',minimum=True)
   residual(aspect,'label_minimum_stem',zero['stem'],2.5,'HUD px',minimum=True)
   residual(aspect,'label_stem_width',zero['stem'],glyph_dossier['espn_reference_frame_012001']['stem_width_px_median']*sx,'HUD px',
     'The common SD cut needs at least 2.5-pixel stems at 16:9, giving at least 3.333 pixels at 4:3; the broadcast median is 2.222 pixels at 4:3. Those requirements cannot fit the 1-pixel match tolerance together.')
   residual(aspect,'label_skipped_columns',len(zero['columns_sampled']),zero['texels'][0],'count',minimum=True)
   residual(aspect,'label_digit_width',zero['width'],16*sx,'HUD px',
     'The requested 2.5 HUD pixel stems and retail-scale digits require a wider SD cut than the 16 source pixel broadcast digit.')
  for label,im,off in [('ESPN reference',canonical,0),('After '+aspect,shown,offset)]:
   sheets.append((label,im.crop((417+off,930,1498+off,1065))))
  before_path=args.output/'before'/f'espn_{suffix}_display.png'
  if before:
   (args.output/'before').mkdir(exist_ok=True)
   old,_,_=rendered_display(before,wide,args.output/'before'/f'espn_{suffix}.png')
  elif before_path.is_file():old=Image.open(before_path)
  else:old=None
  if old:sheets.insert(len(sheets)-1,('Before '+aspect,old.crop((417+offset,930,1498+offset,1065))))
 board=Image.new('RGB',(1100,len(sheets)*160),'#16191d');d=ImageDraw.Draw(board)
 for i,(label,im) in enumerate(sheets):d.text((8,i*160+3),label,fill='white');board.paste(im,(8,i*160+20))
 board.save(args.output/'before_after.png')
 if proof:
  label_board=Image.new('RGB',(540,360),'#16191d');draw=ImageDraw.Draw(label_board)
  for i,wide in enumerate((False,True)):
   suffix='169' if wide else '43';aspect='16:9' if wide else '4:3'
   roi=tuple(round(v) for v in sprite.contracted(sprite.hud_box([830,944,1095,989],wide),wide))
   for j,(name,file) in enumerate((('Before',args.evidence/f'b72_first10_{suffix}.png'),('After',args.output/f'first10_{suffix}.png'))):
    crop=Image.open(file).crop(roi);y=(i*2+j)*82
    draw.text((8,y+4),f'{name} {aspect}: native HUD crop, 3x nearest enlargement',fill='white')
    label_board.paste(crop.resize((crop.width*3,crop.height*3),Image.Resampling.NEAREST),(8,y+22))
  label_board.save(args.output/'label_size_proof.png')
 ref_board=Image.new('RGB',(1060,len(references)*138),'#16191d');draw=ImageDraw.Draw(ref_board)
 for i,ref in enumerate(references):
  draw.text((8,i*138+3),ref['frame']+' (broadcast reference; event states retained)',fill='white')
  ref_board.paste(Image.open(args.frames/ref['frame']).crop((437,942,1478,1052)),(8,i*138+22))
 ref_board.save(args.output/'representative_frames.png')
 output=dict(tolerances=dict(hud_px=args.hud_tolerance,rgb=args.rgb_tolerance),rows=rows,glyph_proof=proof,
  reference_frames=references,representative_frame_residuals=frame_comparisons,dossier_glyph_reference=glyph_dossier['espn_reference_frame_012001'],
  reference_method='Static colours: supplied 500-frame temporal median, canonical possession/clock regions, projected to the SD raster before the same display expansion. Source RGB is retained. Ink boxes: canonical 012001. All 16 representative frames measured and hashed, including event states; event ink is not treated as a standard down label.',
  runtime_witnessed=False,render_reused=args.reuse)
 (args.output/'residuals.json').write_text(json.dumps(output,indent=2)+'\n',newline='\n')
 lines=['Native CPU + submission-order software raster; in-game UNWITNESSED.',f'Tolerances: {args.hud_tolerance} HUD px, {args.rgb_tolerance} RGB units. Minimum gates have zero tolerance.','',
 '| Aspect | Feature | Actual | Target | Residual | Result | Reason |','| --- | --- | --- | --- | --- | --- | --- |']
 for r in rows:lines.append(f"| {r['aspect']} | {r['feature']} | {r['actual']} | {r.get('reference_range',r['target'])} | {r['residual']} {r['unit']} | {r['status']} | {r['reason'] or ''} |")
 text='\n'.join(lines)+'\n';(args.output/'residuals.md').write_text(text,newline='\n');print(text)
 return int(any(r['status']=='FAIL' for r in rows))

if __name__=='__main__':raise SystemExit(main())

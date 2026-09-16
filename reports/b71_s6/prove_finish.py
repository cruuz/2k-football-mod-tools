"""Measure decoded P8 edges, plate, rims, ramps, and native glyph occlusion."""
from pathlib import Path
import json,sys,struct
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite,nfl2k5_scorebug_exact as exact,nfl2k5_scorebug_assets as assets,nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection
OUT=ROOT/'reports/b71_s6'
REF=Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
p=sprite.NativePreview();proof={'runtime_witnessed':False,'before':json.loads((OUT/'before-diagnostics.json').read_text())}

def decode(span):
 ch,b,_=scene.decode(span);t=scene.tx.parse_texture(b,ch)
 return Image.frombytes('RGBA',(t.width,t.height),scene.tx.texture_to_rgba(b,ch,t))

def halo(im):
 # Same coverage/colour sampled by the NV2A straight model vs a premultiplied
 # reference. This isolates hidden-RGB contamination from silhouette changes.
 a=np.asarray(im).astype(float)/255
 yy,xx=np.mgrid[0:im.height*4,0:im.width*4]/4+.125
 ix=np.floor(xx).astype(int);iy=np.floor(yy).astype(int);fx=xx-ix;fy=yy-iy
 straight=np.zeros((*xx.shape,4));premul=straight.copy()
 for dx,dy,w in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
  sample=a[np.minimum(im.height-1,iy+dy),np.minimum(im.width-1,ix+dx)]
  straight+=sample*w[:,:,None]
  sample=sample.copy();sample[:,:,:3]*=sample[:,:,3:];premul+=sample*w[:,:,None]
 edge=(straight[:,:,3]>.08)&(straight[:,:,3]<.92)
 error=(premul[:,:,:3]-straight[:,:,:3]*straight[:,:,3:])*255
 dark=np.maximum(0,error)[edge]
 return dict(edge_samples=int(edge.sum()),mean_dark_rgb_error=float(dark.mean()),p95_dark_rgb_error=float(np.percentile(dark,95)),max_dark_rgb_error=float(dark.max()))

proof['logos']={}
for team in ('DEN','KC'):
 before=Image.open(OUT/f'{team}_before_p8.png').convert('RGBA')
 after=decode(p.chunks[1+sorted(scene.TEAM_LOGOS).index(team)]);after.save(OUT/f'{team}_after_p8.png')
 raw=assets.alpha_bleed(exact.mnf_panel(team,'home'));raw.save(OUT/f'{team}_after_input.png')
 a=np.asarray(raw);d=np.asarray(after)
 solid=a[:,:,3]>=128;pad=np.pad(solid,1,mode='edge')
 adjacent=[pad[y:y+64,x:x+64] for y in range(3) for x in range(3)]
 band=np.logical_or.reduce(adjacent)&~np.logical_and.reduce(adjacent)
 outside=int((((a[:,:,3]>0)&(a[:,:,3]<255))&~band).sum())
 assert outside==0
 stats=dict(before=halo(before),after=halo(after),transparent_pixels_made_visible=int(((a[:,:,3]==0)&(d[:,:,3]>0)).sum()),opaque_pixels_made_translucent=int(((a[:,:,3]==255)&(d[:,:,3]<255)).sum()),partial_coverage_pixels=int(((a[:,:,3]>0)&(a[:,:,3]<255)).sum()))
 assert stats['transparent_pixels_made_visible']==stats['opaque_pixels_made_translucent']==0
 assert stats['after']['mean_dark_rgb_error']<stats['before']['mean_dark_rgb_error'],stats
 stats['feather_pixels_outside_one_texel_boundary']=outside
 stats['hidden_rgb_ablation']=halo(assets.alpha_bleed(before))
 stats['coverage_unchanged_by_bleed']=bool(np.array_equal(np.asarray(before)[:,:,3],np.asarray(assets.alpha_bleed(before))[:,:,3]))
 assert stats['coverage_unchanged_by_bleed']
 proof['logos'][team]=stats
 board=Image.new('RGB',(768,278),'#202b3b');draw=ImageDraw.Draw(board)
 for i,(label,im) in enumerate((('S5 P8',before),('S6 input',raw),('S6 P8',after))):
  bg=Image.new('RGBA',im.size,(50,65,85,255));bg.alpha_composite(im)
  board.paste(bg.convert('RGB').resize((256,256),Image.Resampling.NEAREST),(i*256,22));draw.text((i*256+4,4),label,fill='white')
 board.save(OUT/f'{team}_texture_edges_4x.png')

atlas=decode(p.atlas);atlas.save(OUT/'atlas.png');p.compiled.atlas.save(OUT/'atlas_input.png')
profiles={};c=p.compiled
for team,flip in (('DEN',False),('KC',True)):
 mask=np.asarray(atlas.crop(c.cells['wing']))[:,:,3]
 alpha=mask[mask.shape[0]//2].astype(float)/255
 assert (np.diff(alpha)<=0).all() and alpha[0]==1 and alpha[-1]==0
 tint=exact.ESPN_WING_LIT[team];body=np.asarray(atlas.crop(c.cells['body_middle']))[55,0,:3]
 rgb=np.rint(alpha[:,None]*tint+(1-alpha[:,None])*body).astype(int)
 assert all((np.diff(rgb[:,k])*np.sign(body[k]-tint[k])>=0).all() for k in range(3))
 profiles[team]=dict(direction='outer to inner',alpha=mask[mask.shape[0]//2].tolist(),rgb=rgb.tolist(),max_column_alpha_step=int(abs(np.diff(mask[mask.shape[0]//2].astype(int))).max()),outer=rgb[0].tolist(),inner=rgb[-1].tolist(),monotonic=True)
proof['wing_profiles']=profiles
chart=Image.new('RGB',(1100,400),'#181b20');draw=ImageDraw.Draw(chart)
for i,team in enumerate(('DEN','KC')):
 x0=60+i*550;y0=350;draw.text((x0,10),team+' outer -> inner / decoded P8',fill='white')
 for v in (0,64,128,192,255):
  y=y0-v;draw.line((x0,y,x0+440,y),fill='#3c4249');draw.text((x0-28,y-5),str(v),fill='white')
 for k,color in enumerate(('#fc7070','#70e690','#80a8ff')):
  draw.line([(x0+x*440/212,y0-row[k]) for x,row in enumerate(profiles[team]['rgb'])],fill=color,width=2)
 draw.text((x0,370),'Column 0                                212',fill='white')
chart.save(OUT/'wing_column_profiles.png')

reference=Image.open(REF).convert('RGB')
proof['plate_and_rims']={}
for aspect in ('43','169'):
 s5=Image.open(ROOT/f'reports/b71_s5/standard_{aspect}_crop.png').convert('RGB')
 s6=Image.open(OUT/f'standard_{aspect}_crop.png').convert('RGB')
 ref=reference.crop((420,930,1500,1060))
 board=Image.new('RGB',(2160,834),'#16191d');draw=ImageDraw.Draw(board)
 for i,(label,im) in enumerate((('ESPN frame',ref),('S5 native / '+aspect,s5),('S6 native / '+aspect,s6))):
  draw.text((8,i*278+2),label,fill='white');board.paste(im.resize((2160,260),Image.Resampling.LANCZOS),(0,i*278+18))
 board.save(OUT/f'espn_s5_s6_{aspect}_2x.png')
 for team,box in (('DEN',(453,943,653,1050)),('KC',(1268,943,1468,1050))):
  local=(box[0]-420,box[1]-930,box[2]-420,box[3]-930)
  board=Image.new('RGB',(2400,452),'#16191d');draw=ImageDraw.Draw(board)
  for i,(label,im) in enumerate((('ESPN',ref),('S5 / '+aspect,s5),('S6 / '+aspect,s6))):
   draw.text((i*800+6,4),label,fill='white');board.paste(im.crop(local).resize((800,428),Image.Resampling.NEAREST),(i*800,24))
  board.save(OUT/f'{team}_edge_compare_{aspect}_4x.png')
 def sample(im,box):
  x,y,r,b=box;a=np.asarray(im.crop((x-420,y-930,r-420,b-930)))
  return np.mean(a,axis=(0,1)).round(2).tolist()
 # Clear interior plate strips exclude the white down label; row windows expose
 # the gradient at the native HUD sampling limit, not an ideal PNG-only number.
 regions={'plate_top':(850,949,880,953),'plate_bottom':(850,978,880,981),'body_top_rim':(700,942,710,944),'body_highlight':(700,945,710,950),'body_middle':(700,988,710,998),'body_bottom_rim':(700,1050,710,1052),'red_cell':(1060,1012,1066,1025)}
 proof['plate_and_rims'][aspect]={name:{'reference':sample(ref,box),'s5':sample(s5,box),'s6':sample(s6,box),'box':box} for name,box in regions.items()}

proof['native_foreground']={}
proof['native_wing_profiles']={}
proof['display_proportions']={}
for wide in (False,True):
 g,cap=p.capture(widescreen=wide)
 try:
  sizes={}
  for name in ('away_logo','home_logo','capsule','red','body_left','body_right'):
   row=next(q for q in c.quads if q['name']==name);points=g['positions'][row['vertex']:row['vertex']+4]
   w=max(v[0] for v in points)-min(v[0] for v in points);h=max(v[1] for v in points)-min(v[1] for v in points)
   sizes[name]=[w*3/(27/32 if wide else 1),h*1080/448]
  proof['display_proportions']['169' if wide else '43']=sizes
  q=next(q for q in c.quads if q['name']=='play_clock:0');v=q['vertex']
  # Isolate exactly the same native digit stream. Compare its white coverage
  # against the full bar; another material may not remove any of that coverage.
  live=bytearray(cap['live_decoded'])
  for j in range(scene.layout.VCOUNT):
   if not v<=j<v+4:struct.pack_into('<I',live,scene.layout.S1+j*10,0)
  geometry=dict(g,draws=[])
  path=OUT/('play_clock_isolated_'+('169' if wide else '43')+'.png')
  projection.render_native(bytes(live),p.atlas,p.fonts,geometry,path,texture_spans=cap['texture_spans'],background=Image.new('RGB',(640,480),'black'))
  full=OUT/('foreground_'+('169' if wide else '43')+'.png')
  projection.render_native(cap['live_decoded'],p.atlas,p.fonts,g,full,texture_spans=cap['texture_spans'],background=Image.new('RGB',(640,480),'black'))
  b=exact.hud_box([1040,1007,1060,1030]);b=list(b)
  if wide:
   for k in (0,2):b[k]=320+(b[k]-320)*27/32
  box=(int(b[0]),int(b[1]),int(b[2])+1,int(b[3])+1)
  isolated=np.asarray(Image.open(path).crop(box)).astype(int);actual=np.asarray(Image.open(full).crop(box)).astype(int)
  error=int(np.maximum(0,isolated-actual).max())
  assert error<=1,error
  positions=g['positions'][v:v+4];centre=(min(x[0] for x in positions)+max(x[0] for x in positions))/2
  target=1049.5/3;target=320+(target-320)*27/32 if wide else target
  assert abs(centre-target)<.02
  proof['native_foreground']['169' if wide else '43']=dict(max_lost_digit_coverage=error,centre_hud=centre,target_hud=target,fully_visible=True)
  # Measure actual raster columns with logos/text hidden only for this diagnostic.
  # The body, wing UVs, live vertex tints and draw order remain the native output.
  wings=bytearray(cap['live_decoded']);keep=set()
  for row in c.quads:
   if row['name'] in ('body_left','body','body_right','away_wing','home_wing'):
    keep.update(range(row['vertex'],row['vertex']+4))
  for j in range(scene.layout.VCOUNT):
   if j not in keep:struct.pack_into('<I',wings,scene.layout.S1+j*10,0)
  wingpath=OUT/('native_wings_'+('169' if wide else '43')+'.png')
  projection.render_native(bytes(wings),p.atlas,p.fonts,geometry,wingpath,texture_spans=cap['texture_spans'],background=Image.new('RGB',(640,480),'black'))
  pixels=np.asarray(Image.open(wingpath)).astype(int);profiles={}
  for name,team in (('away_wing','DEN'),('home_wing','KC')):
   row=next(q for q in c.quads if q['name']==name);points=g['positions'][row['vertex']:row['vertex']+4]
   x0=min(v[0] for v in points);x1=max(v[0] for v in points);y=round(sum(v[1] for v in points)/4)
   left=int(np.ceil(x0-.5));right=int(np.ceil(x1-.5));rgb=pixels[y,left:right,:3]
   if team=='KC':rgb=rgb[::-1]
   sign=np.sign(np.array([37,37,37])-exact.ESPN_WING_LIT[team])
   reversals=int((np.diff(rgb,axis=0)*sign<0).sum())
   assert reversals==0,(wide,team,rgb.tolist())
   profiles[team]=dict(y_hud=y,x_hud=[left,right],rgb_outer_to_inner=rgb.tolist(),reversals=reversals,max_rgb_step=int(abs(np.diff(rgb,axis=0)).max()))
  proof['native_wing_profiles']['169' if wide else '43']=profiles
 finally:cap['machine'].close()

# Round-end masks use actual decoded P8 and have a feather, transparent corners,
# opaque centres and mirrored vertical silhouettes. Display contraction is
# reversed by the same 27/32 used to restore every paired preview.
# A separate black-background crop makes native corners/rims visible without
# the ESPN screenshot's old rails showing through transparent corners.
for aspect in ('43','169'):
 im=Image.open(OUT/f'foreground_{aspect}.png').convert('RGB')
 restored=im.crop((50 if aspect=='169' else 0,16,590 if aspect=='169' else 640,464)).resize((1920,1080),Image.Resampling.LANCZOS)
 restored.crop((430,937,1485,1057)).resize((2110,240),Image.Resampling.NEAREST).save(OUT/f'clean_background_{aspect}_2x.png')
proof['round_ends']={}
for name in ('capsule','red'):
 a=np.asarray(atlas.crop(c.cells[name]))[:,:,3]
 edge=a[:,0 if name=='capsule' else -1]
 assert edge[0]<16 and edge[-1]<16 and edge[len(edge)//2]>200
 proof['round_ends'][name]=dict(atlas_size=list(a.shape[::-1]),outer_edge_alpha=edge.tolist(),source_box=next(q['box'] for q in c.quads if q['name']==name),vertical_symmetry_error=int(abs(a.astype(int)-a[::-1].astype(int)).max()))
proof['body_silhouette']={}
for name in ('body_left','body_right'):
 a=np.asarray(atlas.crop(c.cells[name]))[:,:,3]
 edge=a[:,0 if name=='body_left' else -1]
 proof['body_silhouette'][name]=dict(outer_edge_alpha=edge.tolist(),corner_alpha=int(edge[0]),mid_edge_alpha=int(edge[len(edge)//2]),source_radius=8)
 assert edge[0]==0 and edge[len(edge)//2]==255
for name,size in proof['display_proportions']['43'].items():
 other=proof['display_proportions']['169'][name]
 assert max(abs(a-b) for a,b in zip(size,other))<.001
proof['display_proportions']['max_source_pixel_difference']=max(abs(a-b) for name,sz in proof['display_proportions']['43'].items() for a,b in zip(sz,proof['display_proportions']['169'][name]))
proof['volume']=p.volume
assert p.volume['appended_bytes']==323808 and p.volume['font_count']==0 and p.volume['quads']==46
(OUT/'finish-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k not in ('wing_profiles','before')},indent=2))

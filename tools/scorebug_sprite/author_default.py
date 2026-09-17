"""One-time default art author. The product reads only template.png and layout.json."""
from pathlib import Path
import base64,hashlib,io,json
from PIL import Image,ImageDraw,ImageFont
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/nfl2k5_scorebug_sprite'
FONT=Path('/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf')
# Noto Sans Display is SIL OFL 1.1. Fit its bold outlines to condensed broadcast cells.
sheet=Image.new('RGBA',(1536,512),(255,255,255,0));cells={};cursor=[0,0,0]
def put(name,im):
 w,h=im.size;x,y,row=cursor
 if x+w+2>sheet.width:x=0;y+=row+2;row=0
 assert y+h+2<=sheet.height,name
 sheet.paste(im,(x,y));cells[name]={'box':[x,y,x+w,y+h]}
 cursor[:]=[x+w+2,y,max(row,h)]
 return name

def pill(w,h,r,color,ends='both'):
 im=Image.new('RGBA',(w*4,h*4),(255,255,255,0));d=ImageDraw.Draw(im)
 d.rounded_rectangle((0,0,w*4-1,h*4-1),r*4,fill=color)
 if ends=='left':d.rectangle((w*2,0,w*4-1,h*4-1),fill=color)
 if ends=='right':d.rectangle((0,0,w*2,h*4-1),fill=color)
 return im.resize((w,h),Image.Resampling.LANCZOS)
body=pill(1041,110,8,(37,37,37,255));a=np.asarray(body).copy()
# Visible reflection near the top, and the dark lower rim retained in the art.
for y in range(110):
 value=round(39+21*np.exp(-y/11)-4*y/109)
 a[y,:,:3]=[value]*3
for y in (0,1):a[y,:,:3]=(74,80,88)
for y in (108,109):a[y,:,:3]=(13,20,28)
body=Image.fromarray(a);put('body',body)
# Three authored slices preserve the full-resolution silhouette at the ends.
b=cells['body']['box'];cells['body_left']={'box':[b[0],b[1],b[0]+10,b[3]]};cells['body_middle']={'box':[b[0]+10,b[1],b[0]+11,b[3]]};cells['body_right']={'box':[b[2]-10,b[1],b[2],b[3]]}
ramp=pill(213,110,8,(255,255,255,255),'left');a=np.asarray(ramp).copy()
for x in range(213):a[:,x,3]=(a[:,x,3].astype(float)*(1-x/212)**1.5).round().astype('uint8')
# Let the body rim show through the tinted wings. The horizontal mask remains monotonic.
a[:2,:,3]=(a[:2,:,3].astype(float)*.35).round().astype('uint8');a[-2:,:,3]=0
put('wing',Image.fromarray(a))
# A neutral luminance mask is modulated by the possessing team's tint.
plate=pill(246,36,6,(255,255,255,255));a=np.asarray(plate).copy()
for y in range(36):
 for x in range(246):
  # Soft inner edge shading, plus a restrained top lip and darker bottom lip.
  shade=211-18*y/35-14*np.exp(-min(x,245-x)/4)-9*np.exp(-(35-y)/2)
  if y==0:shade=211
  a[y,x,:3]=round(shade)
put('plate',Image.fromarray(a))
notch=Image.new('RGBA',(56,20),(255,255,255,0));d=ImageDraw.Draw(notch)
d.polygon([(0,0),(55,0),(28,19)],fill=(255,248,250,255))
put('pointer',notch.resize((14,5),Image.Resampling.LANCZOS))
put('housing',pill(246,62,18,(24,24,26,255)).resize((82,26),Image.Resampling.LANCZOS))
# Store the round ends at the 4:3 HUD sampling footprint, so bilinear minification
# does not skip their subpixel silhouette coverage. Source-space boxes stay exact.
put('capsule',pill(180,40,20,(248,248,250,255),'left').resize((60,17),Image.Resampling.LANCZOS))
put('red',pill(63,41,20,(215,0,51,255),'right').resize((21,17),Image.Resampling.LANCZOS))
put('tick',Image.new('RGBA',(20,6),(255,255,255,255)))
put('event',Image.new('RGBA',(2,2),(37,37,37,255)))
sets={}
def glyph(token,w,h):
 # Rasterize outlines once at 4x, then retain a full-alpha native-sized cell.
 f=ImageFont.truetype(str(FONT),h*6)
 b=f.getbbox(token);im=Image.new('L',(b[2]-b[0],b[3]-b[1]));ImageDraw.Draw(im).text((-b[0],-b[1]),token,font=f,fill=255)
 im=im.crop(im.getbbox()).resize((w,h),Image.Resampling.LANCZOS)
 rgba=Image.new('RGBA',(w,h),'white');rgba.putalpha(im);return rgba
for name,w,h in [('score',40,53),('clock',23,27),('small',15,19),('label',16,23)]:
 g={}
 for t in '0123456789':
  cell=put(name+'_'+t,glyph(t,w,h));g[t]={'cell':cell,'size':[w,h],'advance':w+2}
 if name=='clock':g[':']={'cell':put('colon',glyph(':',5,18)),'size':[5,18],'advance':7,'raise':-4}
 if name in ('small','label'):
  for t in ('st','nd','rd','th','&','Goal','GOAL','and','OT','ST','ND','RD','TH','Inch','es'):
   gh=13 if name=='small' and t in ('ST','ND','RD','TH','st','nd','rd','th') else h
   width=round(len(t)*gh*.57) if t!='&' else round(gh*.72)
   if name=='small' and t in ('ST','ND','RD','TH','st','nd','rd','th'):width=25
   if name=='label' and t=='&':width=19
   cell=put(name+'_'+t,glyph(t,width,gh));g[t]={'cell':cell,'size':[width,gh],'advance':width+2,'raise':0}
 g[' ']={'cell':'tick','size':[0,0],'advance':11 if name=='label' else 6}
 if name=='label':g['~']={'cell':'tick','size':[20,6],'advance':30}
 sets[name]={'cap_height':h,'glyphs':g}
sets['ticks']={'cap_height':6,'glyphs':{'~':{'cell':'tick','size':[20,6],'advance':30}}}
# FLAG: the plate turns broadcast yellow with a dark bold label baked into the cell.
# The retail white FLAG text is blanked by the owner's literal edit.
flag=pill(246,36,6,(255,204,0,255));a=np.asarray(flag).copy()
for y in range(36):
 for x in range(246):
  shade=(211-18*y/35-14*np.exp(-min(x,245-x)/4)-9*np.exp(-(35-y)/2))/211
  if y==0:shade=1
  a[y,x,:3]=(np.array([255,204,0])*shade).round()
flag=Image.fromarray(a);label=glyph('FLAG',55,23)
flag.paste(Image.new('RGBA',label.size,(26,26,26,255)),((246-55)//2,(36-23)//2),label)
put('flag',flag)
# Brand marks are exact replicas lifted from broadcast stills, the first of a family that
# will replace every ESPN-branded asset. The ESPN MNF watermark: per-pixel temporal minimum
# of luminance over 944 frames that carry the mark lifts the static translucent overlay off
# its darkest background (black level 0.0); alpha=(min-black)/(255-black); the cell stores
# coverage=alpha/p95 at the frame's own resolution and the layout row carries the measured
# opacity, colour and box. Nothing is redrawn: proportions and letterforms are the still's.
ESPN_MNF_COVERAGE_PNG_B64='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'
mark=Image.open(io.BytesIO(base64.b64decode(ESPN_MNF_COVERAGE_PNG_B64))).convert('L')
espn_mnf=Image.new('RGBA',mark.size,(255,251,241,255));espn_mnf.putalpha(mark)
put('espn_mnf',espn_mnf)
BRAND=[dict(name='watermark',cell='espn_mnf',box=[1655, 35, 1869, 64],material=9,tint='none',pin='top-right',opacity=0.714,z=0,
 source=dict(frames='Broncos-vs-Chiefs-Week1-Highlights/frames, every 30th frame from frame_000101 (999 candidates, 944 with the mark present)',method='per-pixel temporal minimum of luminance over frames that carry the mark lifts the static semi-transparent overlay off its darkest background; alpha=(min-black)/(255-black); coverage=alpha/p95(alpha)',black_level=0.0,measured_opacity=0.714,colour=[255, 251, 241]))]
static=[]
def s(name,box,cell,mat=3,tint='none',**kw):static.append(dict(name=name,box=box,cell=cell,material=mat,tint=tint,**kw))
s('body_left',[437,942,447,1052],'body_left');s('body',[447,942,1468,1052],'body_middle');s('body_right',[1468,942,1478,1052],'body_right')
s('housing',[837,983,1083,1045],'housing');s('capsule',[839,999,1019,1039],'capsule')
s('plate',[837,947,1083,983],'plate',4,'possessing team')
s('pointer',[951,942,965,947],'pointer',4)
s('away_wing',[437,942,650,1052],'wing',9,'away team');s('home_wing',[1265,942,1478,1052],'wing',9,'home team',flip_x=True)
s('red',[1019,999,1082,1040],'red',9)
s('away_logo',[453,943,653,1050],'logo',8);s('home_logo',[1268,943,1468,1050],'logo',5)
fields=[]
def f(name,source,box,glyphset,slots,mat,colour,anchor=None,**kw):
 fields.append(dict(name=name,source=source,box=box,glyph_set=glyphset,slots=slots,material=mat,colour=colour,alignment='center',anchor=anchor or [(box[0]+box[2])/2,box[1]],size=box[3]-box[1],**kw))
f('away_score','away score',[696,965,816,1018],'score',3,6,'#E1E1E1')
f('home_score','home score',[1100,965,1220,1018],'score',3,6,'#E1E1E1')
f('clock','clock',[920,1006,1000,1033],'clock',5,6,'#000000')
f('play_clock','play clock',[1028,1009,1073,1028],'small',2,6,'#FFFFFF',anchor=[1049.5,1009],strip_zero=True)
f('quarter','quarter',[850,1009,892,1028],'small',3,6,'#1E1E1E')
f('away_timeouts','away timeouts',[717,1032,797,1038],'ticks',3,7,'#F6F6F6',anchor=[717,1032],timeout=True)
f('home_timeouts','home timeouts',[1120,1032,1200,1038],'ticks',3,7,'#F6F6F6',anchor=[1120,1032],timeout=True)
f('down','down and distance',[850,955,1070,978],'label',8,7,'#FFFFFF')
for x in fields:
 if x.get('timeout'):x['alignment']='left'
for row in static:row['z']=-2 if row['cell']=='logo' else -1 if 'wing' in row['name'] else -3 if row['material'] in (4,9) else 0
for row in fields:row['z']=-5
layout=dict(schema='nfl2k5_scorebug_sprite/v1',frame=[1920,1080],atlas=[256,512],template='template.png',cells=cells,glyph_sets=sets,static=static,fields=fields,brand=BRAND,
 events=[dict(name=n,material=m,box=[837,947,1083,983],cell='flag' if n=='FLAG' else 'event',z=-7) for n,m in [('FUMBLE',0),('ball on',1),('FLAG',2),('hang time',10)]],
 plate_tints={'KC':'#D70E48'},
 reference_boxes={'bar':[437,942,1478,1052],'away_score':[736,965,776,1018],'home_score':[1140,965,1180,1018],'down':[898,955,1021,978],'clock':[920,1006,1000,1033],'quarter':[850,1009,892,1028],'play_clock':[1042,1009,1057,1028]},
 provenance=dict(font='Noto Sans Display Bold, condensed raster fit',license='SIL Open Font License 1.1',font_sha256=hashlib.sha256(FONT.read_bytes()).hexdigest(),author='tools/scorebug_sprite/author_default.py',rendered_once=True,font_distributed=False,brand='brand cells are coverage masks lifted from broadcast stills; each brand row records its source frames, method, opacity and colour'))
# Logical layers are submitted back to front; GPU vertices share one depth.
layout['layer_order']='increasing-z'
for group in ('static','fields','brand','events'):
 for row in layout[group]:row['z']=-20-row.get('z',0)
OUT.mkdir(parents=True,exist_ok=True);sheet.save(OUT/'template.png');(OUT/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
print('authored',cursor,OUT)

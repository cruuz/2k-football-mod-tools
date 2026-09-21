"""One-time default art author. The product reads only template.png and layout.json."""
from pathlib import Path
import base64,hashlib,io,json
from PIL import Image,ImageDraw,ImageFont
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/nfl2k5_scorebug_sprite'
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font',type=Path,default=Path('/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf'))
parser.add_argument('--output',type=Path,default=OUT)
parser.add_argument('--brand-only',action='store_true',
 help='Refilter only the two ESPN watermark cells in an existing --output folder, leaving every other cell and every other layout key untouched.')
args=parser.parse_args()
FONT=args.font;OUT=args.output

# The measured watermark masks the shipped cells were lifted from, with the
# offset that centres each one in the 214x29 quad the layout draws.
BRAND_CANVAS=(214,29)
BRAND_SOURCES={'mnf':('reports/b72_s9/watermark_mnf.png',(3,3)),
               'nfl':('reports/b72_s9/watermark_nfl.png',(21,1))}
# An output row that the measured ink band covers by at least this much is a
# letter row, not a band edge, so it is lifted back to full coverage.
BRAND_KNEE=0.4

def area_rows(lo,hi,count,source):
 """Exact-area resampling weights: `count` output rows spanning source [lo,hi)."""
 step=(hi-lo)/count;out=[]
 for j in range(count):
  a=lo+j*step;b=a+step;w=np.zeros(source)
  for y in range(max(0,int(np.floor(a))),min(source,int(np.ceil(b)))):w[y]=max(0.0,min(b,y+1)-max(a,y))
  out.append(w/w.sum())
 return np.array(out)

def brand_coverage(cell,size,colour=(255,255,255)):
 """Minify a measured watermark mask without thinning its letter tops.

 A box filter is area accurate, so an ink band that does not land on whole
 output rows leaves the band's first and last row at part of the alpha the
 rows between them carry. At the watermark's drawn 0.72 opacity that partial
 top row reads as a cut-off letter rather than as an edge. The filter runs
 premultiplied over exact areas, then a coverage curve divides any output row
 the measured ink band covers by at least BRAND_KNEE by its own coverage, so
 it returns to the level of the rows below it. The letterforms are the still's
 and are never redrawn: only the sampling of the band's edge rows changes.
 """
 width,height=size
 alpha=np.asarray(cell.convert('RGBA')).astype(float)[:,:,3]/255
 # RGB is one flat brand colour, so rebuilding the cell as colour plus
 # coverage is exactly the premultiplied result and carries no dark fringe.
 peak=np.percentile(alpha[alpha>0],99.5) if (alpha>0).any() else 1.0
 profile=np.clip(alpha.max(axis=1)/peak,0,1)
 filtered=area_rows(0,cell.height,height,cell.height)@alpha@area_rows(0,cell.width,width,cell.width).T
 ink=np.nonzero(profile>0)[0]
 if len(ink):
  # Subpixel band edges: the first and last inked row are themselves partly
  # covered, and the mask's own antialiasing measures by how much.
  top=ink[0]+(1-profile[ink[0]]);bottom=ink[-1]+profile[ink[-1]];step=cell.height/height
  for j in range(height):
   covered=max(0.0,min((j+1)*step,bottom)-max(j*step,top))/step
   if covered>=BRAND_KNEE:filtered[j]=filtered[j]/covered
 image=Image.new('RGBA',size,tuple(colour)+(255,))
 image.putalpha(Image.fromarray(np.rint(np.clip(filtered,0,1)*255).astype('uint8'),'L'))
 return image

def brand_mask(variant,size=BRAND_CANVAS):
 """The measured mask for one variant, placed in the quad the layout draws."""
 name,offset=BRAND_SOURCES[variant]
 canvas=Image.new('RGBA',size,(255,255,255,0))
 canvas.paste(Image.open(ROOT/name).convert('RGBA'),offset)
 return canvas

def free_slot(sheet,boxes,size,gutter=1):
 """First position whose cell plus a transparent gutter is clear, never at y=0."""
 width,height=size;alpha=sheet.getchannel('A')
 for y in range(gutter,sheet.height-height-gutter+1):
  for x in range(gutter,sheet.width-width-gutter+1):
   area=(x-gutter,y-gutter,x+width+gutter,y+height+gutter)
   if any(a<area[2] and area[0]<b and c<area[3] and area[1]<d for a,c,b,d in boxes):continue
   if alpha.crop(area).getbbox() is None:return x,y
 raise AssertionError('No free slot for a %dx%d brand cell'%size)

def author_brand_only(folder):
 """Refilter the two watermark cells in place; every other byte of the layout stays."""
 spec=json.loads((folder/'layout.json').read_text(encoding='utf-8'))
 sheet=Image.open(folder/'template.png').convert('RGBA')
 moved={}
 for row in spec.get('brand',[]):
  name=row['cell'];box=spec['cells'][name]['box']
  size=(box[2]-box[0],box[3]-box[1])
  colour=tuple(row.get('source',{}).get('colour',(255,255,255)))
  built=brand_coverage(brand_mask(row['variant']),size,colour)
  # Vacate the old rectangle before repacking, so no stale texels survive.
  sheet.paste(Image.new('RGBA',size,(255,255,255,0)),(box[0],box[1]))
  spec['cells'][name]['box']=[0,0,0,0];moved[name]=built
 for name,built in moved.items():
  boxes=[c['box'] for n,c in spec['cells'].items() if n!=name and c['box'][2]>c['box'][0]]
  x,y=free_slot(sheet,boxes,built.size)
  sheet.paste(built,(x,y));spec['cells'][name]['box']=[x,y,x+built.width,y+built.height]
 spec['sampling']=(spec.get('sampling','')+' Watermark cells are area-filtered premultiplied with a coverage '
  'curve that keeps the measured ink band\'s edge rows at full alpha, and are packed with a one-pixel '
  'transparent gutter away from the sheet edge.').strip()
 spec['provenance']['brand_filter']=('tools/scorebug_sprite/author_default.py --brand-only: exact-area '
  'premultiplied box filter, then rows the measured ink band covers by at least %g are divided by their '
  'own coverage'%BRAND_KNEE)
 sheet.save(folder/'template.png')
 (folder/'layout.json').write_text(json.dumps(spec,indent=1)+'\n',encoding='utf-8',newline='\n')
 print('refiltered brand cells',{n:spec['cells'][n]['box'] for n in moved},folder)

if args.brand_only:
 author_brand_only(OUT);raise SystemExit(0)
if not FONT.is_file():parser.error('Pass --font with NotoSansDisplay-Bold.ttf (SIL OFL 1.1).')
# Noto Sans Display is SIL OFL 1.1. Fit its bold outlines to condensed broadcast cells.
# Packing starts one pixel in so no cell, least of all a brand cell, sits on the sheet edge.
sheet=Image.new('RGBA',(1536,512),(255,255,255,0));cells={};cursor=[1,1,0]
def put(name,im):
 w,h=im.size;x,y,row=cursor
 if x+w+2>sheet.width:x=1;y+=row+2;row=0
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
# A neutral foundation under the team-driven rim and wash masks.
for y in range(110):
 value=np.interp(y,[0,1,3,18,105,107,109],[18,90,72,37,37,70,18])
 a[y,:,:3]=round(value)
body=Image.fromarray(a);put('body',body)
# Reuse the former end slices as two rim masks. The opaque body is now one
# pre-filtered quad. This keeps 47 quads while giving each team a separately
# tinted light rim; multiplying the wing primary alone cannot reach the rim RGB.
median=Image.open(ROOT/'tools/bench/b72_scorebug/espn_bar_median.png').convert('RGB')
for side,tint in [('away',(58,102,178)),('home',(239,33,82))]:
 mask=Image.new('RGBA',(523,110),(255,255,255,0));a=np.asarray(mask).copy()
 lit=(np.array(tint)+255)//2
 for y in list(range(18))+list(range(105,110)):
  for x in range(523):
   source_x=437+x if side=='away' else 955+x
   if y<18:
    # Sample clean columns, not the transient white possession arrow or the
    # horse crest embedded in the median's top strip.
    inner=700 if side=='away' else 1230;outer=453 if side=='away' else 1473
    distance=source_x-437 if side=='away' else 1478-source_x
    edge=np.array(median.getpixel((outer-437,y)),dtype=float)
    wash=np.array(median.getpixel((inner-437,y)),dtype=float)
    mix=max(0,min(1,(distance-16)/217));rgb=edge*(1-mix)+wash*mix
    if distance>383:
     mix=min(1,(distance-383)/110)
     rgb=rgb*(1-mix)+np.interp(y,[0,1,3,18],[18,65,72,37])*mix
    if not 930<source_x<990:rgb*=np.array([1.15 if side=='away' else 1.105,1.10,1.15 if side=='away' else 1.20])
    else:rgb+=np.array([8,2,8])
   else:
    rgb=np.array(median.getpixel((source_x-437,y)),dtype=float)
    rgb*=(np.array([1.22,1.22,1.15]) if side=='away' else np.array([1.13,1.35,1.16])) if source_x<825 or source_x>1094 else np.array([.80,1.05,1.0])
   a[y,x,:3]=np.clip(np.round(rgb/lit*255),0,255)
   a[y,x,3]=255
 put(side+'_rim',Image.fromarray(a))
ramp=pill(233,110,8,(255,255,255,255),'left');a=np.asarray(ramp).copy()
for x in range(233):a[:,x,3]=(a[:,x,3].astype(float)*max(0,min(1,(233-x)/217))**1.05).round().astype('uint8')
# Rims submit over wings; interior tint is full primary at the outer 16 pixels.
# White masks keep the dedicated 64-entry coverage ramp in P8. Encoding
# a differently coloured feather on every row caused visible colour bands.
for side,source_x in [('away',453),('home',1473)]:
 b=a.copy();b[:,:,:3]=255
 for y in range(110):
  # Match the reference's vertical brightness with coverage over the body.
  target=median.getpixel((source_x-437,y))[2 if side=='away' else 0]
  peak=178 if side=='away' else 239
  gain=max(0,min(1,(target-37)/(peak-37)))
  b[y,:,3]=(b[y,:,3].astype(float)*gain).round().astype('uint8')
 put('wing' if side=='away' else 'home_wing',Image.fromarray(b))
# Gloss: wider lip, dip, broad sheen, lower edge, with no label shadow.
plate=Image.new('RGBA',(268,40),(255,255,255,0));d=ImageDraw.Draw(plate)
d.polygon([(0,0),(267,0),(261,4),(256,8),(256,33),(250,39),(17,39),(11,33),(11,8),(6,4)],fill='white')
a=np.asarray(plate).copy()
for y in range(40):
 targets=[(182,24,71),(182,24,71),(169,22,64),(185,7,57),(170,13,58),(150,35,68)]
 rgb=[np.interp(y,[0,2,7,21,30,39],[t[k] for t in targets]) for k in range(3)]
 a[y,:,:3]=np.clip(np.round(np.array(rgb)/[215,45,90]*255),0,255)
put('plate',Image.fromarray(a))
notch=Image.new('RGBA',(56,20),(63,32,40,0));d=ImageDraw.Draw(notch)
d.polygon([(0,0),(55,0),(28,19)],fill=(63,32,40,255))
put('pointer',notch.resize((14,5),Image.Resampling.BOX))
put('housing',pill(246,62,18,(43,43,44,255)))
capsule=pill(180,40,20,(248,248,250,255),'left');a=np.asarray(capsule).copy()
a[0,:,:3]=(200,202,204)
# Separator only at the top and bottom, leaving the clock's breathing room.
a[1:9,60:63,:3]=80;a[31:39,60:63,:3]=80
put('capsule',Image.fromarray(a))
put('red',pill(63,41,20,(215,0,51,255),'right'))
put('tick',Image.new('RGBA',(18,6),(255,255,255,255)))
put('event',Image.new('RGBA',(2,2),(37,37,37,255)))
sets={}
def glyph(token,w,h):
 # Rasterize outlines once at 4x, then retain a full-alpha native-sized cell.
 f=ImageFont.truetype(str(FONT),h*6)
 b=f.getbbox(token);im=Image.new('L',(b[2]-b[0],b[3]-b[1]));ImageDraw.Draw(im).text((-b[0],-b[1]),token,font=f,fill=255)
 im=im.crop(im.getbbox()).resize((w,h),Image.Resampling.LANCZOS)
 rgba=Image.new('RGBA',(w,h),'white');rgba.putalpha(im);return rgba
for name,w,h in [('score',40,53),('clock',23,27),('small',21,26),('label',24,30)]:
 g={}
 for t in '0123456789':
  cell=put(name+'_'+t,glyph(t,w,h));g[t]={'cell':cell,'size':[w,h],'advance':w+2}
 if name=='clock':g[':']={'cell':put('colon',glyph(':',5,18)),'size':[5,18],'advance':7,'raise':-4}
 if name in ('small','label'):
  for t in ('st','nd','rd','th','&','Goal','GOAL','and','OT','ST','ND','RD','TH','Inch','es'):
   gh=18 if name=='small' and t in ('ST','ND','RD','TH','st','nd','rd','th') else h
   width=round(len(t)*gh*.57) if t!='&' else round(gh*.72)
   if name=='small' and t in ('ST','ND','RD','TH','st','nd','rd','th'):width=30
   if name=='label' and t=='&':width=24
   cell=put(name+'_'+t,glyph(t,width,gh));g[t]={'cell':cell,'size':[width,gh],'advance':width+2,'raise':0}
 g[' ']={'cell':'tick','size':[0,0],'advance':11 if name=='label' else 6}
 if name=='label':g['~']={'cell':'tick','size':[18,6],'advance':30}
 sets[name]={'cap_height':h,'glyphs':g}
sets['ticks']={'cap_height':6,'glyphs':{'~':{'cell':'tick','size':[18,6],'advance':30}}}
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
# Reuse the measured face: N, F, then an L from F's stem and flipped top arm.
nfl=Image.new('RGBA',(214,29),(255,251,241,0))
nfl.paste(espn_mnf.crop((0,0,104,29)),(15,0))
nfl.paste(espn_mnf.crop((150,0,182,29)),(124,0))
fmark=espn_mnf.crop((185,0,212,29));nfl.paste(fmark,(159,0))
letter=Image.new('RGBA',(25,29),(255,251,241,0))
letter.paste(fmark.crop((0,0,8,29)),(0,0))
letter.paste(fmark.crop((0,0,25,7)).transpose(Image.Transpose.FLIP_TOP_BOTTOM),(0,22))
nfl.paste(letter,(189,0));put('espn_nfl',nfl)
BRAND=[dict(name='watermark',cell='espn_mnf',box=[1655, 35, 1869, 64],material=9,tint='none',pin='top-right',opacity=0.714,z=0,
 source=dict(frames='Broncos-vs-Chiefs-Week1-Highlights/frames, every 30th frame from frame_000101 (999 candidates, 944 with the mark present)',method='per-pixel temporal minimum of luminance over frames that carry the mark lifts the static semi-transparent overlay off its darkest background; alpha=(min-black)/(255-black); coverage=alpha/p95(alpha)',black_level=0.0,measured_opacity=0.714,colour=[255, 251, 241]))]
BRAND[0]['variant']='mnf'
BRAND.append(dict(BRAND[0],name='watermark_nfl',cell='espn_nfl',variant='nfl',
 source=dict(BRAND[0]['source'],method='Measured ESPN logotype, N and F; L assembled from F stem and vertically flipped top arm. NFL has a 15 source pixel left inset in the same quad. No ESPN NFL still is available.')))
static=[]
def s(name,box,cell,mat=3,tint='none',**kw):static.append(dict(name=name,box=box,cell=cell,material=mat,tint=tint,**kw))
s('body_left',[437,942,960,1052],'away_rim',3,'away rim');s('body',[437,942,1478,1052],'body');s('body_right',[955,942,1478,1052],'home_rim',3,'home rim')
s('housing',[837,987,1083,1049],'housing');s('capsule',[839,999,1019,1039],'capsule')
s('plate',[825,947,1093,987],'plate',4,'possessing team')
s('pointer',[951,942,965,947],'pointer',4)
s('away_wing',[437,942,670,1052],'wing',9,'away team');s('home_wing',[1245,942,1478,1052],'home_wing',9,'home team',flip_x=True)
s('red',[1019,999,1082,1040],'red',9)
s('away_logo',[456,942,639,1054],'logo',8);s('home_logo',[1282,943,1482,1050],'logo',5)
fields=[]
def f(name,source,box,glyphset,slots,mat,colour,anchor=None,**kw):
 fields.append(dict(name=name,source=source,box=box,glyph_set=glyphset,slots=slots,material=mat,colour=colour,alignment='center',anchor=anchor or [(box[0]+box[2])/2,box[1]],size=box[3]-box[1],**kw))
f('away_score','away score',[696,965,816,1018],'score',3,6,'#FDFDFD')
f('home_score','home score',[1100,965,1220,1018],'score',3,6,'#FDFDFD')
f('clock','clock',[920,1006,1000,1033],'clock',5,6,'#000000')
f('play_clock','play clock',[1023,1006,1076,1032],'small',2,6,'#FFFFFF',anchor=[1049.5,1006],strip_zero=True)
f('quarter','quarter',[846,1006,900,1032],'small',3,6,'#1E1E1E')
f('away_timeouts','away timeouts',[717,1032,797,1038],'ticks',3,7,'#F6F6F6',anchor=[717,1032],timeout=True)
f('home_timeouts','home timeouts',[1120,1032,1200,1038],'ticks',3,7,'#F6F6F6',anchor=[1120,1032],timeout=True)
f('down','down and distance',[838,952,1082,982],'label',8,7,'#FFFFFF')
for x in fields:
 if x.get('timeout'):x['alignment']='left'
for row in static:row['z']=-2 if row['cell']=='logo' else -1 if 'wing' in row['name'] else -3 if row['material'] in (4,9) else 0
for row in fields:row['z']=-5
layout=dict(schema='nfl2k5_scorebug_sprite/v1',frame=[1920,1080],atlas=[256,512],template='template.png',cells=cells,glyph_sets=sets,static=static,fields=fields,brand=BRAND,
 events=[dict(name=n,material=m,box=[825,947,1093,987],cell='flag' if n=='FLAG' else 'event',z=-7) for n,m in [('FUMBLE',0),('ball on',1),('FLAG',2),('hang time',10)]],
 plate_tints={'KC':'#D72D5A'},
 wing_tints={'DEN':'#3A66B2','KC':'#EF2152'},
 logo_fit={'default':{'fill_x':1.14,'height':1.0},'by_team':{'KC':{'fill_x':1.30,'height':1.0},'DEN':{'fill_x':1.29,'height':1.0}}},
 reference_boxes={'bar':[437,942,1478,1052],'away_score':[736,965,776,1018],'home_score':[1140,965,1180,1018],'down':[898,955,1021,978],'clock':[920,1006,1000,1033],'quarter':[850,1009,892,1028],'play_clock':[1042,1009,1057,1028]},
 provenance=dict(font='Noto Sans Display Bold, condensed raster fit',license='SIL Open Font License 1.1',font_sha256=hashlib.sha256(FONT.read_bytes()).hexdigest(),author='tools/scorebug_sprite/author_default.py',rendered_once=True,font_distributed=False,brand='brand cells are coverage masks lifted from broadcast stills; each brand row records its source frames, method, opacity and colour'))
# Logical layers are submitted back to front; GPU vertices share one depth.
layout['layer_order']='increasing-z'
for group in ('static','fields','brand','events'):
 for row in layout[group]:row['z']=-20-row.get('z',0)
for row in static:
 if row['name'] in ('body_left','body_right'):row['z']=-18.5
# Pre-filter all used atlas cells to the smallest (16:9) raster footprint.
# Floor, rather than round, ensures neither axis minifies at either aspect.
# Shared glyph cells use the smallest dimensions of every reference.
original=sheet.copy();source_cells=dict(cells);sizes={};cursor[:]=[1,1,0]
def footprint(cell,w,h):
 if w and h:
  size=(max(1,int(w/3)),max(1,int(h*448/1080)))
  sizes[cell]=tuple(min(a,b) for a,b in zip(sizes.get(cell,size),size))
for row in static+BRAND+layout['events']:
 if row['cell']!='logo':footprint(row['cell'],row['box'][2]-row['box'][0],row['box'][3]-row['box'][1])
# The smooth full-width body needs only half its HUD columns, and fits a 256 atlas.
sizes['body']=(173,45)
for name,gs in sets.items():
 # Native fields compress three-digit scores and two-digit-minute clocks.
 factor={'score':120/124,'clock':80/105}.get(name,1)
 for g in gs['glyphs'].values():footprint(g['cell'],g['size'][0]*factor,g['size'][1])
sheet=Image.new('RGBA',(1536,512),(255,255,255,0));cells={};cursor[:]=[1,1,0]
for name,size in sizes.items():
 im=original.crop(source_cells[name]['box'])
 # Pillow's RGBA BOX filter is alpha-aware; each cell is filtered separately.
 fitted=im.resize((min(im.width,size[0]),min(im.height,size[1])),Image.Resampling.BOX)
 if name.startswith('espn_'):
  # A plain box leaves the mark's top row at part of the alpha the rows below
  # it carry, which reads in game as a flat-topped letter. Refilter instead.
  fitted=brand_coverage(im,fitted.size,(255,251,241))
 if name in ('wing','home_wing'):
  a=np.asarray(fitted).copy();a[:,-1,3]=0;fitted=Image.fromarray(a)
 put(name,fitted)
layout['cells']=cells
layout['sampling']=('Cells area-filtered to no larger than the smallest 16:9 HUD footprint; one mip, no minification. '
 'Watermark cells are area-filtered premultiplied with a coverage curve that keeps the measured ink band\'s edge '
 'rows at full alpha, and are packed with a one-pixel transparent gutter away from the sheet edge.')
OUT.mkdir(parents=True,exist_ok=True);sheet.save(OUT/'template.png');(OUT/'layout.json').write_text(json.dumps(layout,indent=1)+'\n',newline='\n')
print('authored',cursor,OUT)

#!/usr/bin/env python3
"""Author bounded period-paint reconstructions. Reference charts are never copied.

This is an authoring tool, not the build compiler: the checked-in RGBA assets
are the deterministic build inputs. Fonts/wordmarks are reconstructions and
must not be described as photographic reproductions.
"""
from pathlib import Path
import hashlib,json
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path(__file__).resolve().parents[2]
FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf')
OUT=ROOT/'data/nfl2k5_espn25_fields'
LOGOS=ROOT/'data/nfl2k5_scorebug_assets/logos'
ALIASES={'GB':'gb','OAK':'lv','KC':'kc','PIT':'pit','DAL':'dal','SF':'sf','MIA':'mia','WAS':'wsh','CLE':'cle','CIN':'cin','STL':'ari','DEN':'den','BUF':'buf','NYG':'nyg','TEN':'ten','NE':'ne','PHI':'phi','MIN':'min','ARI':'ari','ATL':'atl','IND':'ind','NO':'no','BAL':'bal','SEA':'sea','DET':'det','LAR':'lar','CAR':'car'}
def sha(b):return hashlib.sha256(b).hexdigest()
def logo(team,size):
 if team=='DEN_old':
  im=Image.open(OUT/'source/den_1968_1996.png').convert('RGBA');im=ImageOps.contain(im,size,Image.Resampling.LANCZOS);canvas=Image.new('RGBA',size);canvas.alpha_composite(im,((size[0]-im.width)//2,(size[1]-im.height)//2));return canvas
 white=team.endswith('_white');team=team.removesuffix('_white'); p=LOGOS/(ALIASES[team]+'.png')
 if not p.is_file():return Image.new('RGBA',size)
 im=Image.open(p).convert('RGBA');box=im.getbbox()
 if box:im=im.crop(box)
 if white:
  for y in range(im.height):
   for x in range(im.width):
    r,g,b,a=im.getpixel((x,y))
    if r>g+5 and r>b+5:im.putpixel((x,y),(255,255,255,a))
    else:
     gray=max(r,g,b);im.putpixel((x,y),(gray,gray,gray,a))
 im=ImageOps.contain(im,size,Image.Resampling.LANCZOS);out=Image.new('RGBA',size);out.alpha_composite(im,((size[0]-im.width)//2,(size[1]-im.height)//2));return out

def label(text,size,color,outline):
 im=Image.new('RGBA',size);d=ImageDraw.Draw(im);f=ImageFont.truetype(str(FONT),100)
 bb=d.textbbox((0,0),text,font=f,stroke_width=2); canvas=Image.new('RGBA',(bb[2]-bb[0]+8,bb[3]-bb[1]+8));ImageDraw.Draw(canvas).text((4-bb[0],4-bb[1]),text,font=f,fill=color,stroke_width=2,stroke_fill=outline)
 canvas.thumbnail((size[0]-8,size[1]-8),Image.Resampling.LANCZOS);im.alpha_composite(canvas,((size[0]-canvas.width)//2,(size[1]-canvas.height)//2));return im

def endzone(row,side):
 if row.get('endzone_files'):
  return Image.open(OUT/row['endzone_files']['NS'[side]]).convert('RGBA').resize((768,128),Image.Resampling.LANCZOS)
 e=row['endzones'][side];bg=e['background']; im=Image.new('RGBA',(768,128),(0,0,0,0) if bg=='turf' else bg);d=ImageDraw.Draw(im)
 if row.get('pattern')=='diagonal':
  for x in range(-128,850,64):d.polygon([(x,0),(x+25,0),(x+153,128),(x+128,128)],fill=e['foreground'])
 elif row.get('pattern')=='stripes':
  for x in range(-128,850,100):d.polygon([(x,0),(x+45,0),(x+173,128),(x+128,128)],fill='#101820')
  im.alpha_composite(label(e['text'],(600,104),'#ffffff','#101820'),(84,12))
 else:
  if e.get('wordmark_file'):
   source=Image.open(OUT/e['wordmark_file']).convert('RGBA')
   for y in range(source.height):
    for x in range(source.width):
     r,g,b,a=source.getpixel((x,y))
     if min(r,g,b)>245:source.putpixel((x,y),(r,g,b,0))
   source.thumbnail((560,108),Image.Resampling.LANCZOS);im.alpha_composite(source,((768-source.width)//2,(128-source.height)//2))
  else:im.alpha_composite(label(e['text'],(560,108),e['foreground'],e['outline']),(104,10))
  if row['season']>=1990 or row['super_bowl']:
   side_logo='DEN_old' if e['team']=='DEN' and row['season']<1997 else e['team']
   im.alpha_composite(logo(side_logo,(94,94)),(8,17));im.alpha_composite(logo(side_logo,(94,94)),(666,17))
 return im

def shield(size,modern):
 if modern:
  im=Image.open(OUT/'source/nfl_2008.png').convert('RGBA');box=im.getbbox()
  if box:im=im.crop(box)
  im.thumbnail(size,Image.Resampling.LANCZOS);canvas=Image.new('RGBA',size);canvas.alpha_composite(im,((size[0]-im.width)//2,(size[1]-im.height)//2));return canvas
 im=Image.new('RGBA',(256,256));d=ImageDraw.Draw(im)
 p=[(30,35),(74,35),(128,17),(182,35),(226,35),(223,139),(199,191),(128,239),(57,191),(33,139)]
 d.polygon(p,fill='#ffffff',outline='#182a58',width=7);d.polygon([(37,41),(219,41),(216,121),(40,121)],fill='#182a58')
 for x,y in [(61,64),(93,64),(164,64),(194,64),(60,96),(91,96),(166,96),(196,96)]:d.regular_polygon((x,y,8),5,rotation=-90,fill='#ffffff')
 d.ellipse((108,55,149,112),fill='#ffffff');d.line((129,64,129,102),fill='#182a58',width=3)
 im.alpha_composite(label('NFL',(162,85),'#d71920','#ffffff'),(47,133))
 return im.resize(size,Image.Resampling.LANCZOS)

def main():
 doc=json.loads((ROOT/'data/nfl2k5_espn25_fields.json').read_text());OUT.mkdir(exist_ok=True);manifest=[]
 for row in doc['moments']:
  folder=OUT/f"row{row['row']:02d}";folder.mkdir(exist_ok=True)
  images={'endzone_N':endzone(row,0),'endzone_S':endzone(row,1)}
  center=row['center']
  if row.get('center_file'):
   im=Image.open(OUT/row['center_file']).convert('RGBA');im=im.crop(im.getbbox());im=ImageOps.contain(im,(256,256),Image.Resampling.LANCZOS);canvas=Image.new('RGBA',(256,256));canvas.alpha_composite(im,((256-im.width)//2,(256-im.height)//2));images['center_logo']=canvas
  else:images['center_logo']=Image.new('RGBA',(256,256)) if center=='blank' else shield((256,256),row['season']>=2008) if center=='NFL' else logo(center,(256,256))
  if row['super_bowl']:
   images['playoff_logo']=label('SB '+row['super_bowl'],(128,128),'#ffffff','#29303b')
  else: images['playoff_logo']=Image.new('RGBA',(128,128))
  for key,im in images.items():
   path=folder/(key+'.png');im.save(path);manifest.append(dict(row=row['row'],key=key,file=str(path.relative_to(OUT)),size=list(im.size),sha256=sha(path.read_bytes())))
 (OUT/'manifest.json').write_text(json.dumps(dict(schema='nfl2k5_espn25_field_art/v1',authoring_font_sha256=sha(FONT.read_bytes()),art=manifest),indent=2)+'\n')
if __name__=='__main__':main()

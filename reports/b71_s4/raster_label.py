"""Reproduce the authored label masks from installed Roboto Condensed Bold.

This offline authoring tool is not needed on the player's machine. Render at
2x the 23-source-pixel cap height, then downsample into the FONT donor cells.
"""
from pathlib import Path
import hashlib,json
from PIL import Image,ImageFont,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
FONT=Path('/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf')
font=ImageFont.truetype(str(FONT),64)
chars='0123456789stndrh&GoalANDSTHR:Icew'
sheet=Image.new('L',(512,256));rows={}
for i,ch in enumerate(dict.fromkeys(chars)):
 box=font.getbbox(ch);im=Image.new('L',(box[2]-box[0],box[3]-box[1]));ImageDraw.Draw(im).text((-box[0],-box[1]),ch,font=font,fill=255)
 # 64pt has a 46px cap; this is the actual 2x raster, retained losslessly.
 x,y=(i%10)*50,(i//10)*64;sheet.paste(im,(x,y));rows[ch]=[x,y,x+im.width,y+im.height]
out=ROOT/'data/nfl2k5_scorebug_mnf';sheet.save(out/'painted_label_2x.png')
(out/'painted_label_2x.json').write_text(json.dumps(dict(font='Roboto Condensed Bold',font_sha256=hashlib.sha256(FONT.read_bytes()).hexdigest(),raster_pixels=64,cap_pixels=46,boxes=rows),indent=2)+'\n')

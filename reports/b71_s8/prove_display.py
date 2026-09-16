"""Display-model proof: predicted on-screen boxes before (S6 layout) and after (S8) at both aspects,
Noah's widescreen screenshot measurements, and ESPN/render comparisons at 2x."""
import json,sys
from pathlib import Path
sys.path[:0]=['.','tools']
import numpy as np
from PIL import Image
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
OUT=Path('reports/b71_s8')
ESPN=Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
SHOT=Path('/home/noah/Downloads/ksnip_20260916-043627.png')   # disc n, widescreen, xemu window 1129x673
boxes={'bar':[437,942,1478,1052],'capsule':[839,999,1019,1039],'plate':[837,947,1083,983],'away_logo':[453,943,653,1050],'home_logo':[1268,943,1468,1050]}
def before(box,wide):   # S6: x/3 for both displays, then the game's contraction and the same display scaling
    x0,y0,x1,y1=box;hud=(x0/3,16+y0*448/1080,x1/3,16+y1*448/1080)
    return sprite.display_box(sprite.contracted(hud,wide),wide)
def after(box,wide):return sprite.display_box(sprite.contracted(sprite.hud_box(box,wide),wide),wide)
rows=[]
for name,box in boxes.items():
    src=(box[2]-box[0])/(box[3]-box[1])
    for wide in (False,True):
        b=before(box,wide);a=after(box,wide)
        rows.append(dict(region=name,display='16:9' if wide else '4:3',source_aspect=round(src,3),before_aspect=round((b[2]-b[0])/(b[3]-b[1]),3),after_aspect=round((a[2]-a[0])/(a[3]-a[1]),3),
                         before_box=[round(v,1) for v in b],after_box=[round(v,1) for v in a]))
# Noah's screenshot (disc n = the S6 layout at 16:9): measured bar width and logo height, scaled to 1920x1080
a=np.asarray(Image.open(SHOT).convert('RGB')).astype(int);H,W=a.shape[:2]
band=a[560:673];dark=(band.max(-1)<75)
rowsd=np.nonzero(dark.mean(1)>0.25)[0];y0,y1=rowsd.min()+560,rowsd.max()+560
cols=np.nonzero(dark[rowsd.min():rowsd.max()+1].mean(0)>0.5)[0]
kc=(a[590:660,700:830].min(-1)>150);kr=np.nonzero(kc.sum(1)>2)[0];kcw=np.nonzero(kc.sum(0)>2)[0]
measured=dict(window=[W,H],bar_dark_core_px=[int(cols.min()),int(cols.max()+1)],bar_rows_px=[int(y0),int(y1+1)],
              kc_arrowhead_px=dict(width=int(kcw.max()-kcw.min()+1),height=int(kr.max()-kr.min()+1)),
              note='the window is 1.68:1, not 1.78:1; xemu stretches to the window unless display.ui.fit keeps 16:9 (letterbox)')
pred_before_logo=before(boxes['home_logo'],True);pred_after_logo=after(boxes['home_logo'],True)
measured['kc_arrowhead_aspect']=round(measured['kc_arrowhead_px']['width']/measured['kc_arrowhead_px']['height'],3)
measured['predicted_logo_aspect_before_on_this_window']=round((pred_before_logo[2]-pred_before_logo[0])/(pred_before_logo[3]-pred_before_logo[1])*(W/1920)/(H/1080),3)
measured['predicted_logo_aspect_after_on_this_window']=round((pred_after_logo[2]-pred_after_logo[0])/(pred_after_logo[3]-pred_after_logo[1])*(W/1920)/(H/1080),3)
json.dump(dict(display_model=sprite.DISPLAY,x_scale={'4:3':sprite.x_scale(False),'16:9':sprite.x_scale(True)},rows=rows,screenshot=measured),open(OUT/'display_model.json','w'),indent=1,default=str)
# comparisons at 2x: ESPN bar crop vs the 16:9 display render (1:1 pixels), and the FLAG state
def stack(paths,labels,crop,out):
    ims=[Image.open(p).convert('RGB').crop(crop) for p in paths]
    w=max(i.width for i in ims);h=sum(i.height for i in ims)+12*(len(ims)-1)
    sheet=Image.new('RGB',(w*2,h*2),(24,24,24));y=0
    from PIL import ImageDraw
    for im,l in zip(ims,labels):
        big=im.resize((im.width*2,im.height*2),Image.LANCZOS);sheet.paste(big,(0,y));ImageDraw.Draw(sheet).text((6,y+4),l,fill=(255,255,0));y+=big.height+24
    sheet.save(out)
crop=(400,920,1520,1070)
stack([ESPN,OUT/'standard_169_display.png'],['ESPN frame_012001','S8 sprite, 16:9 display model (1 source px = 1 display px)'],crop,OUT/'espn_vs_s8_169_2x.png')
stack([OUT/'flag_169_display.png'],['S8 FLAG state, 16:9 display model'],crop,OUT/'flag_s8_169_2x.png')
stack([OUT/'standard_43_display.png'],['S8 sprite, 4:3 display model'],(160,920,1280,1070),OUT/'s8_43_2x.png')
stack([ESPN,OUT/'standard_169_display.png'],['ESPN top right','S8 watermark, 16:9 display'],(1500,0,1920,120),OUT/'watermark_espn_vs_s8_2x.png')
print(json.dumps(rows,indent=0)[:1200]);print(measured)

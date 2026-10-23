"""Author the Seamen's menu cards from the plain Browns card renders (reference only; no Madden art ships).

Usage: python3 tools/b77/ss1_cards.py --cards <folder with helm_h30_0.png, unif_h30_0.png, ...> [--out DIR]
The source renders are decoded from the retail card aggregate members (nfl2k5_historic_styles / the card targets);
the authored PNGs ship in data/nfl2k5_classic_teams/cards.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/nfl2k5_classic_teams/cards'
SRC = Path('/home/noah/2k-worktrees/.b77-scratch/b778/ss1/work/cards2')
TEAL = (16, 185, 132)
INK = (16, 24, 32)
WHITE = (255, 255, 255)

def font(size):
    for name in ('DejaVuSans-BoldOblique.ttf','DejaVuSans-Bold.ttf'):
        try: return ImageFont.truetype(name,size)
        except OSError: pass
    return ImageFont.load_default()

def mask_brown(a):
    r,g,b=a[...,0].astype(int),a[...,1].astype(int),a[...,2].astype(int)
    return (a[...,3]>40)&(r<160)&(g<80)&(b<80)&(r>g+25)&(g<b+20)

def mask_orange(a):
    r,g,b=a[...,0].astype(int),a[...,1].astype(int),a[...,2].astype(int)
    return (a[...,3]>40)&(r>130)&(g<150)&(b<100)&(r>g+40)&(g>=b-10)

def mask_light(a, lo=170):
    r,g,b=a[...,0].astype(int),a[...,1].astype(int),a[...,2].astype(int)
    return (a[...,3]>40)&(r>lo)&(g>lo)&(b>lo)&(abs(r-g)<28)&(abs(g-b)<28)

def shade_to(rgb, lum, base=0.45, span=0.55):
    f = base + span * (lum / 255.0)
    return tuple(min(255,max(0,int(c*f))) for c in rgb)

def map_grey_keep_lum(a, mask, target):
    out=a.copy()
    idx=np.argwhere(mask)
    lum=a[...,:3].mean(axis=2)
    for y,x in idx:
        out[y,x,:3]=shade_to(target, float(lum[y,x]))
    return out

def map_flat(a, mask, rgb):
    out=a.copy(); out[mask,:3]=rgb; return out

def paste_patch(a,dst,src):
    out=a.copy(); dx0,dy0,dx1,dy1=dst; sx0,sy0,sx1,sy1=src
    out[dy0:dy1,dx0:dx1]=a[sy0:sy0+(dy1-dy0),sx0:sx0+(dx1-dx0)]
    return out

def cover(a, dst, src):
    """A feathered cloth patch: the source box scaled over the destination, edges blended."""
    im=Image.fromarray(a)
    dx0,dy0,dx1,dy1=dst; sx0,sy0,sx1,sy1=src
    patch=im.crop((sx0,sy0,sx1,sy1)).resize((dx1-dx0,dy1-dy0),Image.BILINEAR)
    mask=Image.new('L',(dx1-dx0,dy1-dy0),0)
    ImageDraw.Draw(mask).rectangle([3,3,dx1-dx0-4,dy1-dy0-4],fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(3))
    im.paste(patch,(dx0,dy0),mask)
    return np.array(im)

def anchor(draw,cx,cy,size,colour=TEAL,ink=INK,outline=True):
    s=size/100.0
    ring=(cx,cy-38*s,16*s)
    if outline:
        draw.ellipse([ring[0]-ring[2]-5*s,ring[1]-ring[2]-5*s,ring[0]+ring[2]+5*s,ring[1]+ring[2]+5*s],fill=ink)
        draw.rectangle([cx-9*s-5*s,cy-22*s,cx+9*s+5*s,cy+48*s],fill=ink)
        draw.rectangle([cx-38*s-5*s,cy-8*s-5*s,cx+38*s+5*s,cy-8*s+9*s+5*s],fill=ink)
    draw.ellipse([ring[0]-ring[2],ring[1]-ring[2],ring[0]+ring[2],ring[1]+ring[2]],fill=colour)
    draw.ellipse([ring[0]-6*s,ring[1]-6*s,ring[0]+6*s,ring[1]+6*s],fill=ink if outline else (0,0,0,0))
    draw.rectangle([cx-9*s,cy-22*s,cx+9*s,cy+48*s],fill=colour)
    draw.rectangle([cx-38*s,cy-8*s,cx+38*s,cy+9*s],fill=colour)
    for side in (-1,1):
        pts=[(cx+side*8*s,cy+26*s),(cx+side*32*s,cy+38*s),(cx+side*44*s,cy+24*s),(cx+side*40*s,cy+4*s)]
        if outline: draw.line(pts,fill=ink,width=max(3,int(14*s)),joint='curve')
        draw.line(pts,fill=colour,width=max(2,int(8*s)),joint='curve')
        tip=(cx+side*50*s,cy+2*s)
        arrow=[(tip[0],tip[1]-10*s),(tip[0]+side*14*s,tip[1]+10*s),(tip[0]-side*2*s,tip[1]+12*s)]
        if outline: draw.polygon(arrow,fill=ink)
        draw.polygon([(tip[0]+side*2*s,tip[1]-4*s),(tip[0]+side*8*s,tip[1]+7*s),(tip[0]+side*1*s,tip[1]+7*s)],fill=colour)

def logo_card(size=256):
    im=Image.new('RGBA',(size,size),(32,170,150,255)); d=ImageDraw.Draw(im)
    r=max(5,size//34)
    for y in range(-r,size+r,int(r*1.7)):
        for x in range(-r,size+r,int(r*2.0)):
            off=(r if (y//int(r*1.7))%2 else 0)
            pts=[(x+off+r*np.cos(a),y+r*np.sin(a)) for a in np.linspace(0.5236,6.806,6)]
            d.polygon(pts,outline=(28,158,140,255))
    anchor(d,size*0.5,size*0.44,size*0.78)
    f=font(max(16,int(size*0.17))); text='SEAMEN'; box=d.textbbox((0,0),text,font=f)
    d.text((size-(box[2]-box[0])-size*0.06,size-(box[3]-box[1])-size*0.09),text,font=f,fill=INK)
    return im

def _stripe(im, points, colour=TEAL, clip=None):
    shell=np.array(im)[...,3]>40
    if clip is not None: shell=shell&clip
    mask=Image.new('L',im.size,0); ImageDraw.Draw(mask).polygon(points,fill=255)
    m=np.array(mask,dtype=bool)&shell
    a=np.array(im); a[m,:3]=colour; return Image.fromarray(a)

def helmet_card(base):
    a=np.array(base.convert('RGBA')); orig=a.copy()
    brown=mask_brown(orig); orange=mask_orange(orig)
    a=map_grey_keep_lum(a,orange|brown,WHITE)
    # lift the grey toward white: the card shell is white, the dark edges stay grey
    lift=orange|brown
    rgb=a[...,:3].astype(int); a[...,:3]=np.where(lift[...,None],np.clip(190+rgb*0.25,0,255).astype(np.uint8),a[...,:3])
    im=Image.fromarray(a)
    im=_stripe(im,[(145,15),(172,15),(190,150),(165,150)])
    anchor(ImageDraw.Draw(im),195,120,60)
    return im

def uniform_card(base, home):
    a=np.array(base.convert('RGBA')); orig=a.copy()
    brown=mask_brown(orig); orange=mask_orange(orig)
    yy,xx=np.mgrid[0:a.shape[0],0:a.shape[1]]
    helmet=(xx<135)&(yy>135)&(((xx-85)**2+(yy-205)**2)<95**2)
    # jersey cloth and trim
    a=map_grey_keep_lum(a,brown&~helmet,TEAL)
    a=map_grey_keep_lum(a,orange&~helmet,WHITE if home else TEAL)
    # helmet shell: white with a teal stripe; the facemask bars stay pale
    a=map_grey_keep_lum(a,(orange|brown)&helmet,WHITE)
    rgb=a[...,:3].astype(int); shell=(helmet&(orange|brown))[...,None]
    lifted=np.clip(190+rgb*0.25,0,255).astype(np.uint8)
    a[...,:3]=np.where(shell,lifted,a[...,:3])
    # home pants: pale cloth -> teal
    if home:
        pants=(xx>=205)&(yy>90)
        light=mask_light(orig,150)&pants
        a[light,:3]=TEAL
    # cover the BROWNS wordmark with clean shoulder cloth
    a=cover(a,(24,46,110,82),(110,75,155,111))
    im=Image.fromarray(a)
    im=_stripe(im,[(82,143),(96,143),(104,230),(90,230)],TEAL,clip=helmet)
    anchor(ImageDraw.Draw(im),64,198,40)
    return im

def mini_card(base):
    a=np.array(base.convert('RGBA')); orig=a.copy()
    brown=mask_brown(orig); orange=mask_orange(orig)
    a=map_grey_keep_lum(a,orange|brown,WHITE)
    rgb=a[...,:3].astype(int); a[...,:3]=np.clip(190+rgb*0.25,0,255).astype(np.uint8)
    im=Image.fromarray(a)
    im=_stripe(im,[(30,8),(40,8),(45,56),(35,56)],TEAL)
    anchor(ImageDraw.Draw(im),26,34,24)
    return im

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cards',type=Path,default=SRC,help='folder with the decoded Browns card PNGs')
    ap.add_argument('--out',type=Path,default=OUT)
    args=ap.parse_args()
    out=args.out; out.mkdir(parents=True,exist_ok=True)
    cards={n:Image.open(args.cards/f'{n}.png') for n in ('helm_h30_0','helm_a30_0','unif_h30_0','unif_a30_0','mini_h30_0','mini_a30_0')}
    logo_card(256).save(out/'logo.png')
    logo_card(64).save(out/'logo_s.png')
    helmet_card(cards['helm_h30_0']).save(out/'helm_h.png')
    helmet_card(cards['helm_a30_0']).save(out/'helm_a.png')
    uniform_card(cards['unif_h30_0'],True).save(out/'unif_h.png')
    uniform_card(cards['unif_a30_0'],False).save(out/'unif_a.png')
    mini_card(cards['mini_h30_0']).save(out/'mini_h.png')
    mini_card(cards['mini_a30_0']).save(out/'mini_a.png')
    print('wrote',out)

if __name__=='__main__':
    main()

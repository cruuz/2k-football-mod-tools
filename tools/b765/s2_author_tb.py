"""Author Tampa Bay's current turf end zones from pinned exact vector marks.

The September 27, 2026 home gallery resolves the supplied word contours,
red face, white outline, black offset shadow and Buccaneers flag flanks.
Paint footprint and midfield dimensions are photographic estimates. This
offline author command needs Inkscape/Pillow/NumPy/SciPy; Studio consumes
the resulting hash-pinned native PNGs and four-times-native masters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b765.s2_author_field import install_overrides

SCALE=4
BODY_HEIGHT=96
OUTLINE=3
SHADOW=[4,4]
MIDFIELD_SCALE_XZ=[1.49,1.88]
PANELS=[
    dict(x_cm=[-2443.47998046875,-810.2064819335938],u=[.000152587890625,.9923098087310791]),
    dict(x_cm=[-810.2064819335938,810.2064819335938],u=[.007964849472045898,.9923098087310791]),
    dict(x_cm=[810.2064819335938,2443.47998046875],u=[.007964849472045898,1.0001220703125]),
]
DEPTH=919.52392578125
V=[.000091552734375,1.00006103515625]
PINS={"wordmark":"e20512032da3e8ff73b7a27500740c5d26ab627e9315701a47189a919baecc9e",
      "flag":"c22a1d7344ab0ec5fabd2fbdecd94edef48af9173819aae5856b518e495e5c8c"}
REFERENCE="https://www.buccaneers.com/photos/photos-bucs-cheerleaders-from-vikings-vs-bucs-week-3-2026"
MIDFIELD_REFERENCE="https://www.buccaneers.com/photos/packers-vs-bucs-week-4-2026-top-images-gallery"


def sha(data):return hashlib.sha256(data).hexdigest()


def world_x(px):
    i=min(2,max(0,int(px//256)));p=PANELS[i];u=(px-i*256)/256
    return p["x_cm"][0]+(u-p["u"][0])/(p["u"][1]-p["u"][0])*(p["x_cm"][1]-p["x_cm"][0])


def physical_width(width):return world_x(384+width/2)-world_x(384-width/2)


def raster(path,key,folder):
    data=Path(path).read_bytes()
    if sha(data)!=PINS[key]:raise ValueError("Unexpected reviewed Tampa Bay "+key+" SVG")
    root=ET.fromstring(data)
    if key=="wordmark":
        # Only the exact red BUCCANEERS paths: remove TAMPA BAY and the
        # supplied gray offset-shadow group, both explicitly gray in this SVG.
        for parent in root.iter():
            for child in list(parent):
                if child.get("fill")=="#b1babf":parent.remove(child)
    source=folder/(key+".svg");out=folder/(key+".png")
    ET.ElementTree(root).write(source)
    subprocess.run(["inkscape",str(source),"--export-width=4096",
                    "--export-background-opacity=0","--export-filename="+str(out)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with Image.open(out) as im:
        image=im.convert("RGBA");box=image.getchannel("A").getbbox()
        if box is None:raise ValueError("Empty reviewed vector")
        return image.crop(box),dict(render_alpha_bbox=list(box),render_size=list(image.size),
                                   crop_size=[box[2]-box[0],box[3]-box[1]],render_sha256=sha(out.read_bytes()))


def width_for_height(aspect,height):
    wanted=DEPTH*height/128/(V[1]-V[0])*aspect
    lo,hi=1.,740.
    for _ in range(64):
        mid=(lo+hi)/2
        if physical_width(mid)<wanted:lo=mid
        else:hi=mid
    return (lo+hi)/2


def master(wordmark,flag):
    from scipy.ndimage import grey_dilation
    with tempfile.TemporaryDirectory(prefix="b765-s2-tb-") as temp:
        word,wmeta=raster(wordmark,"wordmark",Path(temp));logo,lmeta=raster(flag,"flag",Path(temp))
    aspect=word.width/word.height
    width=round(width_for_height(aspect,BODY_HEIGHT)*SCALE)
    alpha=word.getchannel("A").resize((width,BODY_HEIGHT*SCALE),Image.Resampling.LANCZOS)
    coverage=Image.new("L",(768*SCALE,128*SCALE))
    coverage.paste(alpha,((coverage.width-alpha.width)//2,(128-BODY_HEIGHT)*SCALE//2))
    radius=OUTLINE*SCALE;y,x=np.ogrid[-radius:radius+1,-radius:radius+1]
    outer=Image.fromarray(grey_dilation(np.asarray(coverage),footprint=x*x+y*y<=radius*radius))
    canvas=Image.new("RGBA",coverage.size)
    shadow=Image.new("RGBA",coverage.size,(0,0,0,0));shadow.putalpha(outer)
    canvas.alpha_composite(shadow,(SHADOW[0]*SCALE,SHADOW[1]*SCALE))
    white=Image.new("RGBA",coverage.size,(255,255,255,0));white.putalpha(outer);canvas.alpha_composite(white)
    red=Image.new("RGBA",coverage.size,(167,25,48,0));red.putalpha(coverage);canvas.alpha_composite(red)
    # Fixed same-end flank centres, with the SVG's aspect preserved in world
    # units rather than square atlas pixels. No old NFL/helmet source marks.
    logo_height=69;logo_aspect=logo.width/logo.height
    target_height=DEPTH*logo_height/128/(V[1]-V[0])
    flank_rows=[]
    for centre in (64.,704.):
        lo,hi=1.,120.
        for _ in range(64):
            w=(lo+hi)/2
            actual=world_x(centre+w/2)-world_x(centre-w/2)
            if actual<target_height*logo_aspect:lo=w
            else:hi=w
        w=round((lo+hi)/2*SCALE);h=logo_height*SCALE
        paint=Image.fromarray(mv.resample(np.asarray(logo),w,h,smooth=True))
        xy=(round(centre*SCALE-w/2),round(64*SCALE-h/2))
        canvas.alpha_composite(paint,xy)
        flank_rows.append(dict(centre_native_px=[centre,64],size_master=[w,h],xy_master=list(xy),
                               physical_aspect=(world_x(centre+w/SCALE/2)-world_x(centre-w/SCALE/2))/target_height))
    arr=np.asarray(canvas).copy();arr[arr[:,:,3]==0]=0
    native_width=width/SCALE
    physical_ratio=physical_width(native_width)/(DEPTH*BODY_HEIGHT/128/(V[1]-V[0]))
    return Image.fromarray(arr),dict(word_render=wmeta,flag_render=lmeta,exact_source_contours=True,
        word_source_aspect=aspect,body_height_native_px=BODY_HEIGHT,body_width_native_px=native_width,
        physical_word_aspect=physical_ratio,physical_aspect_error_percent=(physical_ratio/aspect-1)*100,
        outline_native_px=OUTLINE,shadow_offset_native_px=SHADOW,flanks=flank_rows)


def author(art_root,out,wordmark,flag):
    image,validation=master(wordmark,flag)
    replacements={"endzone_"+end+"_"+part:image.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
                  for end in "NS" for i,part in enumerate("LMR")}
    receipt=install_overrides(art_root,out,"s27",replacements)
    art=mv.load_art(out);path=Path(art["venues"]["s27"]["manifest"]);doc=json.loads(path.read_text())
    for item in doc["items"]:
        if item["scene"]=="field" and item["material"] in replacements:item["layer"]="overlay"
    doc.setdefault("paint",{}).update(endzone="retail_turf",endzone_south="retail_turf")
    doc["midfield_scale_xz"]=MIDFIELD_SCALE_XZ
    doc["endzone_turf_from_field"]=True
    notes=re.sub(r"End zones: .*?(?=Fan banners:)","",doc.get("notes",""))
    doc["notes"]=("S2: red exact-source BUCCANEERS with white outline/black offset shadow and flag flanks "
                  "on cleaned retail turf, from September27,2026 home photo42. Source glyph contours match "
                  "the photo. Field footprints and midfield x/z scale are photographic estimates requiring "
                  "Noah's camera check. "+notes.strip())
    doc.setdefault("sources",[]).extend([REFERENCE+" (2026-09-27, zero-based photo41)",
                                          MIDFIELD_REFERENCE+" (2026-10-04, zero-based photo195)"])
    path.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["provenance"]=dict(source_svg_sha256=PINS,field_reference=REFERENCE,event_date="2026-09-27",
        photo_zero_based=41,validation=validation,native_panel_size=[256,128],master_scale=SCALE,
        colours=dict(fill="#A71930",outline="#FFFFFF",shadow="#000000"),background="transparent overlay onto cleaned retail turf",
        midfield_scale_xz=MIDFIELD_SCALE_XZ,midfield_reference=MIDFIELD_REFERENCE,
        placement="Word/flank footprints and midfield scale are estimates; all existing quad centres/UVs preserved",
        physical_mapping=dict(original_panel_maps=PANELS,depth_cm=DEPTH,v=V),
        native_downscale="Studio premultiplied Lanczos mv.resample(smooth=True)")
    image.save(Path(out)/"TB_endzone_master.png")
    panels=[mv.resample(np.asarray(image.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))),256,128,smooth=True) for i in range(3)]
    Image.fromarray(np.concatenate(panels,axis=1)).save(Path(out)/"TB_endzone_native.png")
    (Path(out)/"tb_field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    mv.load_art(out)
    for name,digest in receipt["preserved"].items():
        if sha((Path(out)/name).read_bytes())!=digest:raise ValueError("Unselected source file changed: "+name)
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--art-root",required=True,type=Path);p.add_argument("--out",required=True,type=Path)
    p.add_argument("--wordmark-svg",required=True,type=Path);p.add_argument("--flag-svg",required=True,type=Path)
    a=p.parse_args();print(json.dumps(author(a.art_root,a.out,a.wordmark_svg,a.flag_svg)["provenance"],indent=2))

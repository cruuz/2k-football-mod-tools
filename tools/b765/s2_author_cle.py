"""Author independent Cleveland end-zone paint from the pinned supplied SVG.

The Browns' October 1, 2026 primary home photos show BROWNS and CLEVELAND
on turf without helmet flanks. This command retains the exact supplied glyph
contours and writes transparent 4x masters/native overlays. Placement, stroke
and the default N/S assignment are photographic estimates requiring camera
review. Inkscape/Pillow/NumPy/SciPy are offline author dependencies; Studio
pack builds consume the installed PNGs and do not invoke this author command.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image
import numpy as np
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b765.s2_author_field import install_overrides

SCALE = 4
SOURCE_SHA256 = "03e50051d73331d9fb4c0d530afa5bec9c9798d5416bbd57620d3d0176542f84"
SOURCE_URL = "https://commons.wikimedia.org/wiki/File:Cleveland_Browns_wordmark.svg"
FIELD_REFERENCE = "https://www.clevelandbrowns.com/photos/thursday-night-football-at-huntington-bank-field-2026-in-focus"
FIELD_DATE = "2026-10-01"
BODY_HEIGHT = 86
OUTLINE = 2
PANELS = [
    dict(x_cm=[-2443.47998046875,-810.2064819335938],u=[3.0517112463712692e-05,.9921875]),
    dict(x_cm=[-810.2064819335938,810.2064819335938],u=[.007827520370483398,.9921875]),
    dict(x_cm=[810.2064819335938,2443.47998046875],u=[.007827520370483398,.9999847412109375]),
]
DEPTH = 919.52392578125
V = [3.0517112463712692e-05,.9999847412109375]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def world_x(px):
    index = min(2,max(0,int(px//256)))
    panel = PANELS[index]
    u = (px-index*256)/256
    x0,x1 = panel["x_cm"]
    u0,u1 = panel["u"]
    return x0+(u-u0)/(u1-u0)*(x1-x0)


def physical_width(width):
    return world_x(384+width/2)-world_x(384-width/2)


def width_for_aspect(aspect):
    wanted = DEPTH*BODY_HEIGHT/128/(V[1]-V[0])*aspect
    lo,hi = 1.,740.
    for _ in range(64):
        mid = (lo+hi)/2
        if physical_width(mid) < wanted:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def masters(wordmark_svg):
    """Return two exact-source transparent paint atlases and shape metadata."""
    from scipy.ndimage import grey_dilation
    data = Path(wordmark_svg).read_bytes()
    if sha(data) != SOURCE_SHA256:
        raise ValueError("Unexpected reviewed Cleveland wordmark SVG")
    with tempfile.TemporaryDirectory(prefix="b765-s2-cle-") as temporary:
        source = Path(temporary)/"wordmark.svg"
        raster = Path(temporary)/"wordmark_8x.png"
        source.write_bytes(data)
        subprocess.run(["inkscape",str(source),"--export-type=png","--export-background-opacity=0",
                        "--export-width=3286","--export-filename="+str(raster)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with Image.open(raster) as image:
            alpha = image.convert("RGBA").getchannel("A")
        render_sha = sha(raster.read_bytes())
    if alpha.size != (3286,1496):
        raise ValueError("Reviewed Cleveland source render dimensions changed")
    a = np.asarray(alpha)
    bands = []
    for y in np.nonzero(a.max(axis=1)>0)[0]:
        if not bands or y>bands[-1][1]+1:
            bands.append([int(y),int(y)])
        else:
            bands[-1][1] = int(y)
    if bands != [[17,631],[692,1481]]:
        raise ValueError("Reviewed Cleveland exact two-row alpha crop changed")
    images,words = {},{}
    for word,(y0,y1) in zip(("cleveland","browns"),bands):
        _,xs = np.nonzero(a[y0:y1+1])
        box = (int(xs.min()),y0,int(xs.max())+1,y1+1)
        glyph = alpha.crop(box)
        aspect = glyph.width/glyph.height
        nominal = width_for_aspect(aspect)
        width_master = round(nominal*SCALE)
        width = width_master/SCALE
        body = glyph.resize((width_master,BODY_HEIGHT*SCALE),Image.Resampling.LANCZOS)
        coverage = Image.new("L",(768*SCALE,128*SCALE))
        xy = ((coverage.width-body.width)//2,(128-BODY_HEIGHT)*SCALE//2)
        coverage.paste(body,xy)
        radius = OUTLINE*SCALE
        y,x = np.ogrid[-radius:radius+1,-radius:radius+1]
        outline = Image.fromarray(grey_dilation(np.asarray(coverage),footprint=x*x+y*y<=radius*radius))
        master = Image.new("RGBA",coverage.size,(255,60,0,0))
        master.putalpha(outline)
        white = Image.new("RGBA",coverage.size,(255,255,255,0))
        white.putalpha(coverage)
        master.alpha_composite(white)
        pixels = np.asarray(master).copy()
        pixels[pixels[:,:,3]==0] = 0
        images[word] = Image.fromarray(pixels)
        ratio = physical_width(width)/(DEPTH*BODY_HEIGHT/128/(V[1]-V[0]))
        words[word] = dict(source_alpha_bbox=list(box),source_glyph_pixels=list(glyph.size),
                           source_glyph_aspect=aspect,nominal_width_native_px=nominal,
                           body_width_native_px=width,chosen_body_xy_master=list(xy),
                           physical_body_width_cm=physical_width(width),physical_glyph_aspect=ratio,
                           physical_aspect_error_percent=(ratio/aspect-1)*100)
    return images,dict(render_size=list(alpha.size),render_sha256=render_sha,alpha_row_bands=bands,
                       words=words,exact_source_contours=True,no_font_or_trace_substitution=True)


def author(art_root,out,wordmark_svg,north_text="browns"):
    """Copy a complete art root, replacing only six Cleveland field panels."""
    source,output = Path(art_root).resolve(),Path(out).resolve()
    if north_text not in ("browns","cleveland"):
        raise ValueError("North text must be browns or cleveland")
    if output.exists() or output==source or output.is_relative_to(source):
        raise ValueError("Output must be a new separate art root outside input")
    art = mv.load_art(source)
    if "s30" not in art["venues"]:
        raise ValueError("Complete input art root lacks Cleveland s30")
    manifest = Path(art["venues"]["s30"]["manifest"])
    original = json.loads(manifest.read_text())
    if any(i["scene"]=="field" and i["material"].startswith("endzone_S_") for i in original["items"]):
        raise ValueError("Expected the reviewed shared-end Cleveland source")
    images,validation = masters(wordmark_svg)
    south_text = "cleveland" if north_text=="browns" else "browns"
    replacements = {"endzone_N_"+part:images[north_text].crop(
        (i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE)) for i,part in enumerate("LMR")}
    receipt = install_overrides(source,output,"s30",replacements)
    target = output/manifest.relative_to(source)
    doc = json.loads(target.read_text())
    for item in doc["items"]:
        if item["scene"]=="field" and item["material"] in replacements:
            item["layer"] = "overlay"
    for i,part in enumerate("LMR"):
        key = "endzone_S_"+part
        panel = images[south_text].crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
        native_rel,master_rel = "refined/field/"+key+".png","refined/field/"+key+"_master.png"
        native_path,master_path = target.parent/native_rel,target.parent/master_rel
        panel.save(master_path)
        Image.fromarray(mv.resample(np.asarray(panel),256,128,smooth=True)).save(native_path)
        doc["items"].append(dict(scene="field",material=key,layer="overlay",size=[256,128],
                                 file=native_rel,master=master_rel,sha256=sha(native_path.read_bytes()),
                                 master_sha256=sha(master_path.read_bytes()),native_from_master=True))
        receipt["changed"].extend(str(p.relative_to(output)) for p in (native_path,master_path))
    doc["split_shared_endzones"] = True
    doc["field_prefix_loan"] = True
    doc.setdefault("paint",{})["endzone"] = "retail_turf"
    notes = re.sub(r"End zones: .*?(?=Midfield:)","",doc.get("notes",""))
    notes = re.sub(r"No 2026 home game yet .*?gallery shows plain brown wall pads\.","",notes)
    doc["notes"] = ("S2: independent white/orange BROWNS and CLEVELAND on cleaned retail turf, no helmet flanks, "
                    "from the Browns' October 1 2026 primary home gallery. Exact supplied SVG glyphs; original "
                    "world/UV aspect compensated. Height, stroke, centering and native N/S assignment are "
                    "estimated and require camera review. "+notes.strip())
    doc.setdefault("sources",[]).append(FIELD_REFERENCE+" (2026-10-01, gallery photos 39 and 47 / zero-based38 and46)")
    target.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["selected"] = sorted("endzone_"+e+"_"+p for e in "NS" for p in "LMR")
    receipt["provenance"] = dict(source_wordmark=SOURCE_URL,source_svg_sha256=SOURCE_SHA256,
                                 source_validation=validation,field_reference=FIELD_REFERENCE,
                                 field_event_date=FIELD_DATE,field_photos_zero_based=[38,46],
                                 native_panel_size=[256,128],master_scale=SCALE,
                                 north_word=north_text,south_word=south_text,
                                 colours=dict(fill="#FFFFFF",outline="#FF3C00"),
                                 body_height_native_px=BODY_HEIGHT,body_center_native_px=[384,64],
                                 outline_outset_native_px=OUTLINE,
                                 background="transparent overlay composed onto same-end clean retail turf; no flat fill",
                                 native_downscale="Studio premultiplied Lanczos mv.resample(smooth=True)",
                                 physical_mapping=dict(original_panel_maps=PANELS,depth_cm=DEPTH,v=V,
                                                       geometry_unchanged=True),
                                 placement="Photographic height/stroke/centering estimates; native N/S cardinal mapping unconfirmed")
    for word,image in images.items():
        master_path,native_path = output/("CLE_"+word+"_master.png"),output/("CLE_"+word+"_native.png")
        image.save(master_path)
        panels = [mv.resample(np.asarray(image.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))),
                              256,128,smooth=True) for i in range(3)]
        Image.fromarray(np.concatenate(panels,axis=1)).save(native_path)
        receipt["changed"].extend(str(p.relative_to(output)) for p in (master_path,native_path))
    (output/"cle_field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    mv.load_art(output)
    for name,digest in receipt["preserved"].items():
        if sha((output/name).read_bytes())!=digest:
            raise ValueError("Unselected source file changed: "+name)
    return receipt


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art-root",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--wordmark-svg",required=True,type=Path)
    parser.add_argument("--north-text",choices=("browns","cleveland"),default="browns")
    args = parser.parse_args()
    print(json.dumps(author(args.art_root,args.out,args.wordmark_svg,args.north_text)["provenance"],indent=2))

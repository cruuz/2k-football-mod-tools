"""Author Washington's ordinary home field paint from pinned source contours.

The official September 27, 2026 home highlight shows burgundy/gold COMMANDERS
on turf, flanked by inward-facing helmets. Exact supplied SVGs provide the word
and W decal. Helmet paint contours come from reviewed native retail s29 panels;
their silhouettes are vectorized at 4x and checked against the native masks.
Height, stroke and positions are photographic estimates, requiring camera review.
Studio consumes the resulting native/master PNGs, not these author dependencies.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_fill_holes, grey_dilation
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b765.s2_author_field import install_overrides

SCALE = 4
WORD_SHA = "31678d30678c35448f33b5470b1f15911f6cd015d6689828535ba6a2a4044de9"
W_SHA = "36787556089a354f3bbc3c5cd70c3977bef317d521398d191e189678ca42bcfa"
RETAIL_SHA = {
    "L": "4984dd630c39a4f6b94de38b5363dc59ca796baa443444438a19b5e99de68797",
    "R": "0027bc9820d9ef073924ad04d50bc67bee533e4daefe60bcea91a6e01233662e",
}
REFERENCE = "https://www.seahawks.com/video/2026-week-3-highlight-sam-darnold-finds-jsn-in-the-endzone"
REFERENCE_DATE = "2026-09-27"
BURGUNDY, GOLD = (90,20,20), (255,182,18)
BODY_HEIGHT, OUTLINE = 68, 2
HELMET_HEIGHT = 79
PANELS = [
    dict(x_cm=[-2443.47998046875,-810.2064819335938],u=[.000152587890625,.9923098087310791]),
    dict(x_cm=[-810.2064819335938,810.2064819335938],u=[.007964849472045898,.9923098087310791]),
    dict(x_cm=[810.2064819335938,2443.47998046875],u=[.007964849472045898,1.0001220703125]),
]
DEPTH = 919.52392578125
V = [.000091552734375,1.00006103515625]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def world_x(px):
    i = min(2,max(0,int(px//256)))
    p = PANELS[i]
    u = (px-i*256)/256
    return p["x_cm"][0]+(u-p["u"][0])/(p["u"][1]-p["u"][0])*(p["x_cm"][1]-p["x_cm"][0])


def physical_width(width):
    return world_x(384+width/2)-world_x(384-width/2)


def width_for_aspect(aspect):
    wanted = DEPTH*BODY_HEIGHT/128/(V[1]-V[0])*aspect
    lo,hi = 1.,740.
    for _ in range(64):
        mid = (lo+hi)/2
        if physical_width(mid)<wanted:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def export_svg(source, filename, width):
    subprocess.run(["inkscape",str(source),"--export-type=png",
                    "--export-background-opacity=0","--export-width="+str(width),
                    "--export-filename="+str(filename)],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with Image.open(filename) as image:
        return image.convert("RGBA")


def rounded_path(mask):
    """Vectorize native contours, rounding subpixel corners and retaining holes."""
    # The 4x nearest mask exposes pixel-cell boundaries; native cv2 contours run
    # through pixel centers and would shrink thin facemask bars by half a pixel.
    cells = cv2.resize(np.uint8(mask)*255,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
    contours,_ = cv2.findContours(cells,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    paths = []
    for contour in contours:
        points = (cv2.approxPolyDP(contour,3.0,True).reshape(-1,2).astype(float)+.5)/4
        if len(points)<3:
            # Preserve one-pixel paint details, rather than dropping small hardware.
            x,y,w,h = [v/4 for v in cv2.boundingRect(contour)]
            paths.append(f"M{x},{y}h{w}v{h}h{-w}Z")
            continue
        before,after = [],[]
        for i,point in enumerate(points):
            a,b = points[i-1]-point,points[(i+1)%len(points)]-point
            before.append(point+a*(min(.45,np.linalg.norm(a)/3)/max(np.linalg.norm(a),1e-9)))
            after.append(point+b*(min(.45,np.linalg.norm(b)/3)/max(np.linalg.norm(b),1e-9)))
        fmt = lambda p: f"{p[0]:.4f},{p[1]:.4f}"
        path = "M"+fmt(after[-1])
        for a,p,b in zip(before,points,after):
            path += "L"+fmt(a)+"Q"+fmt(p)+" "+fmt(b)
        paths.append(path+"Z")
    return " ".join(paths)


def helmet(retail_panel, side, w_logo, temporary):
    data = Path(retail_panel).read_bytes()
    if sha(data)!=RETAIL_SHA[side]:
        raise ValueError("Unexpected reviewed retail Washington helmet panel "+side)
    with Image.open(retail_panel) as image:
        rgb = np.asarray(image.convert("RGB")).copy()
    if rgb.shape!=(128,256,3):
        raise ValueError("Washington retail end-zone panel dimensions changed")
    a = rgb.astype(int)
    mask = ((a[:,:,0]>=a[:,:,1]) | ((a.min(axis=2)>145)&(np.ptp(a,axis=2)<75))
            | ((a.max(axis=2)<65)&(np.ptp(a,axis=2)<25)))
    if side=="L":
        mask[:,155:] = False
        decal_box,feathers = (16,21,70,78),(16,59,42,96)
        w_box = (22,31,89,63)
    else:
        mask[:,:105] = False
        decal_box,feathers = (186,21,242,78),(214,59,242,96)
        w_box = (169,31,236,63)
    original_foreground_pixels = int(mask.sum())
    # Retail palette dithering/old decal counters expose isolated turf pixels
    # within the rear shell. Fill those enclosed holes as shell paint; genuine
    # open facemask spaces remain transparent. This does not expand its outline.
    internal_holes = binary_fill_holes(mask)&~mask
    if side=="L":
        internal_holes[:,75:] = False
    else:
        internal_holes[:,:181] = False
    mask |= internal_holes
    rgb[internal_holes] = BURGUNDY
    # Remove both the old Indian oval and its feather decal inside the shell.
    clear = Image.new("L",(256,128))
    draw = ImageDraw.Draw(clear)
    draw.ellipse(decal_box,fill=255)
    draw.rectangle(feathers,fill=255)
    rgb[(np.asarray(clear)>0)&mask] = BURGUNDY
    colours = np.asarray([BURGUNDY,GOLD,(255,255,255),(30,30,30)],float)
    distance = ((rgb[:,:,None,:].astype(float)-colours[None,None,:,:])**2).sum(axis=3)
    labels = distance.argmin(axis=2)
    # Quantized retail shading includes isolated dots in every palette layer.
    # Keep connected ear/rim/facemask hardware; clear tiny disconnected flecks.
    speckles = np.zeros(mask.shape,bool)
    speckle_counts = {}
    for colour in (1,2,3):
        count,components,stats,_ = cv2.connectedComponentsWithStats(
            np.uint8(mask&(labels==colour)),connectivity=8)
        selected = np.zeros(mask.shape,bool)
        for index in range(1,count):
            if stats[index,cv2.CC_STAT_AREA]<=8:
                selected |= components==index
        speckles |= selected
        speckle_counts[("gold","white","charcoal")[colour-1]] = int(selected.sum())
    labels[speckles] = 0
    # Dither also leaves tiny enclosed counters within otherwise solid paint.
    # Fill only <=8px holes fully inside the helmet silhouette, keeping the
    # large open facemask spaces and the ear opening as their reviewed shapes.
    counter_counts = {}
    for colour in (1,2):
        layer = mask&(labels==colour)
        holes = binary_fill_holes(layer)&~layer&mask
        count,components,stats,_ = cv2.connectedComponentsWithStats(
            np.uint8(holes),connectivity=8)
        selected = np.zeros(mask.shape,bool)
        for index in range(1,count):
            if stats[index,cv2.CC_STAT_AREA]<=8:
                selected |= components==index
        labels[selected] = colour
        counter_counts[("gold","white")[colour-1]] = int(selected.sum())
    alpha_path = rounded_path(mask)
    paths = [f'<path fill="#5A1414" fill-rule="evenodd" d="{alpha_path}"/>']
    for index,colour in enumerate(("#5A1414","#FFB612","#FFFFFF","#1E1E1E")):
        if index:
            paths.append(f'<path fill="{colour}" fill-rule="evenodd" d="{rounded_path(mask&(labels==index))}"/>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="128" viewBox="0 0 256 128">'+"".join(paths)+"</svg>"
    svg_file,render = temporary/("helmet_"+side+".svg"),temporary/("helmet_"+side+".png")
    svg_file.write_text(svg, newline="\n")
    vector = export_svg(svg_file,render,256*SCALE)
    native_mask = np.asarray(vector.getchannel("A").resize((256,128),Image.Resampling.LANCZOS))>=128
    intersection = np.count_nonzero(native_mask&mask)
    union = np.count_nonzero(native_mask|mask)
    iou = intersection/union
    if iou<.97:
        raise ValueError(f"Washington helmet contour reconstruction exceeded silhouette tolerance: {side} IoU={iou:.6f}")
    # Decal scales from the exact current W; the logo contains the intended burgundy counters.
    x0,y0,x1,y1 = w_box
    panel = PANELS[0 if side=="L" else 2]
    x_cm_per_pixel = (panel["x_cm"][1]-panel["x_cm"][0])/(panel["u"][1]-panel["u"][0])/256
    y_cm_per_pixel = DEPTH/(V[1]-V[0])/128
    w_aspect = w_logo.width/w_logo.height
    decal_height = (y1-y0)*SCALE
    decal_width = round(w_aspect*decal_height*y_cm_per_pixel/x_cm_per_pixel)
    decal = w_logo.resize((decal_width,decal_height),Image.Resampling.LANCZOS)
    decal_xy = (round((x0+x1)*SCALE/2-decal_width/2),y0*SCALE)
    vector.alpha_composite(decal,decal_xy)
    box = vector.getchannel("A").getbbox()
    vector = vector.crop(box)
    height = HELMET_HEIGHT*SCALE
    width = round(vector.width*height/vector.height)
    vector = vector.resize((width,height),Image.Resampling.LANCZOS)
    return vector,dict(retail_sha256=RETAIL_SHA[side],source_mask_pixels=int(mask.sum()),
                       original_foreground_pixels=original_foreground_pixels,
                       cleared_internal_retail_mask_holes=int(internal_holes.sum()),
                       silhouette_iou_native_threshold128=iou,source_crop_bbox_master=list(box),
                       source_contour_recipe="Native foreground palette mask; .75px polygon tolerance; .45px rounded corners; even-odd holes; 4x SVG render",
                       old_decal_removal=dict(oval=list(decal_box),feathers=list(feathers)),
                       w_decal_bbox_source_native=list(w_box),master_dimensions=list(vector.size),
                       w_decal_actual_bbox_master=[*decal_xy,decal_xy[0]+decal_width,decal_xy[1]+decal_height],
                       w_source_aspect=w_aspect,
                       w_physical_aspect=decal_width*x_cm_per_pixel/(decal_height*y_cm_per_pixel),
                       w_physical_aspect_error_percent=(decal_width*x_cm_per_pixel/(decal_height*y_cm_per_pixel)/w_aspect-1)*100,
                       reconstruction_svg_sha256=sha(svg.encode()),
                       removed_palette_speckle_pixels=speckle_counts,
                       filled_tiny_palette_counter_pixels=counter_counts,
                       internal_paint="Nearest reviewed burgundy/gold/white/charcoal palette regions, vectorized before scaling")


def master(wordmark_svg, w_svg, retail_left, retail_right):
    for source,digest in ((wordmark_svg,WORD_SHA),(w_svg,W_SHA)):
        if sha(Path(source).read_bytes())!=digest:
            raise ValueError("Unexpected reviewed Washington SVG: "+Path(source).name)
    with tempfile.TemporaryDirectory(prefix="b765-s2-was-") as name:
        temporary = Path(name)
        word = export_svg(wordmark_svg,temporary/"word.png",2048)
        alpha = np.asarray(word.getchannel("A"))
        bands = []
        for y in np.nonzero(alpha.max(axis=1)>0)[0]:
            if not bands or y>bands[-1][1]+1:
                bands.append([int(y),int(y)])
            else:
                bands[-1][1] = int(y)
        if word.size!=(2048,656) or bands!=[[9,107],[155,206],[250,553],[596,647]]:
            raise ValueError("Reviewed Washington exact four-band source crop changed")
        y0,y1 = bands[2]
        _,xs = np.nonzero(alpha[y0:y1+1])
        box = (int(xs.min()),y0,int(xs.max())+1,y1+1)
        glyph = word.getchannel("A").crop(box)
        aspect = glyph.width/glyph.height
        width = round(width_for_aspect(aspect)*SCALE)
        glyph = glyph.resize((width,BODY_HEIGHT*SCALE),Image.Resampling.LANCZOS)
        body = Image.new("L",(768*SCALE,128*SCALE))
        xy = ((body.width-glyph.width)//2,(128-BODY_HEIGHT)*SCALE//2)
        body.paste(glyph,xy)
        radius = OUTLINE*SCALE
        y,x = np.ogrid[-radius:radius+1,-radius:radius+1]
        outline = Image.fromarray(grey_dilation(np.asarray(body),footprint=x*x+y*y<=radius*radius))
        atlas = Image.new("RGBA",body.size,GOLD+(0,))
        atlas.putalpha(outline)
        ink = Image.new("RGBA",body.size,BURGUNDY+(0,))
        ink.putalpha(body)
        atlas.alpha_composite(ink)
        # The actual helmet uses the filled four inner W pieces, while the
        # broadcast/team tile uses the outlined colourway of the same SVG.
        # Select and recolour exact supplied paths, never retrace the emblem.
        tree = ET.fromstring(Path(w_svg).read_bytes())
        paths = list(tree)
        if len(paths)!=2 or paths[0].get("fill")!="#FFB612" or paths[1].get("fill")!="#5A1414":
            raise ValueError("Reviewed Washington exact two-layer W source changed")
        tree.remove(paths[0])
        paths[1].set("fill","#FFB612")
        filled_w = temporary/"filled_w.svg"
        filled_w.write_bytes(ET.tostring(tree))
        logo = export_svg(filled_w,temporary/"w.png",2048)
        logo_box = logo.getchannel("A").getbbox()
        if logo.size!=(2048,2048) or logo_box!=(204,576,1872,1468):
            raise ValueError("Reviewed Washington W source crop changed")
        logo = logo.crop(logo_box)
        helmets = {}
        for side,panel,center in (("L",retail_left,58),("R",retail_right,710)):
            image,info = helmet(panel,side,logo,temporary)
            placement = (round(center*SCALE-image.width/2),round(64*SCALE-image.height/2))
            atlas.alpha_composite(image,placement)
            info["placement_master_xy"] = list(placement)
            helmets[side] = info
        render_sha = sha((temporary/"word.png").read_bytes())
        w_render_sha = sha((temporary/"w.png").read_bytes())
    pixels = np.asarray(atlas).copy()
    pixels[pixels[:,:,3]==0] = 0
    ratio = physical_width(width/SCALE)/(DEPTH*BODY_HEIGHT/128/(V[1]-V[0]))
    info = dict(source_wordmark_sha256=WORD_SHA,source_w_svg_sha256=W_SHA,
                word_render_sha256=render_sha,w_render_sha256=w_render_sha,
                w_colourway="Filled gold four inner pieces selected from exact supplied two-layer SVG; same contour paths, outer border omitted as on photographed helmets",
                w_source_alpha_bbox=list(logo_box),
                word_alpha_bands=bands,word_source_bbox=list(box),word_source_aspect=aspect,
                body_height_native_px=BODY_HEIGHT,body_width_native_px=width/SCALE,
                physical_word_width_cm=physical_width(width/SCALE),physical_glyph_aspect=ratio,
                physical_aspect_error_percent=(ratio/aspect-1)*100,word_body_master_xy=list(xy),
                helmet_contours=helmets,exact_svg_glyphs=True,no_font_substitution=True)
    return Image.fromarray(pixels),info


def author(art_root,out,wordmark_svg,w_svg,retail_left,retail_right):
    """Copy the full art root and replace only three shared s29 end-zone items."""
    source,output = Path(art_root).resolve(),Path(out).resolve()
    if output.exists() or output==source or output.is_relative_to(source):
        raise ValueError("Output must be a new separate art root outside input")
    art = mv.load_art(source)
    if "s29" not in art["venues"]:
        raise ValueError("Complete input art root lacks Washington s29")
    manifest = Path(art["venues"]["s29"]["manifest"])
    image,validation = master(wordmark_svg,w_svg,retail_left,retail_right)
    replacements = {"endzone_N_"+part:image.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
                    for i,part in enumerate("LMR")}
    receipt = install_overrides(source,output,"s29",replacements)
    target = output/manifest.relative_to(source)
    doc = json.loads(target.read_text())
    for item in doc["items"]:
        if item["scene"]=="field" and item["material"] in replacements:
            item["layer"] = "overlay"
    doc.setdefault("paint",{})["endzone"] = "retail_turf"
    doc["endzone_turf_from_field"] = True
    notes = re.sub(r"End zone: .*?(?=Midfield:)","",doc.get("notes",""))
    doc["notes"] = ("S2: ordinary home COMMANDERS in burgundy with gold outline on cleaned same-variant main-field turf, "
                    "inward-facing helmet flanks with current W decals. Exact supplied word/W SVGs and "
                    "reviewed vectorized native retail helmet contours; no Indian decal retained. "
                    "Word height/stroke/centering and helmet positions are photographic estimates. "+notes.strip())
    doc.setdefault("sources",[]).append(REFERENCE+" (ordinary home September 27, 2026; frames0.50s/24.00s)")
    target.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["provenance"] = dict(field_reference=REFERENCE,field_date=REFERENCE_DATE,
                                 source_wordmark="https://commons.wikimedia.org/wiki/File:Washington_Commanders_wordmark.svg",
                                 source_w_logo="https://static.www.nfl.com/league/api/clubs/logos/WAS.svg",
                                 source_validation=validation,native_panel_size=[256,128],master_scale=SCALE,
                                 colours=dict(fill="#5A1414",outline="#FFB612",white="#FFFFFF"),
                                 outline_outset_native_px=OUTLINE,
                                 background="Transparent paint overlay composed onto cleaned same-variant color_premipped; donor bytes unchanged",
                                 endzone_turf_from_field=True,
                                 donor_reason="Same-end retail cleanup retained brown/gold helmet-paint islands outside the new overlay silhouette",
                                 native_downscale="Studio premultiplied Lanczos mv.resample(smooth=True)",
                                 physical_mapping=dict(original_panel_maps=PANELS,depth_cm=DEPTH,v=V,geometry_unchanged=True),
                                 placement="Photographic estimates; shared three-panel route retained for both ends; opposite real end not separately established")
    master_path,native_path = output/"WAS_endzone_master.png",output/"WAS_endzone_native.png"
    image.save(master_path)
    native = [mv.resample(np.asarray(replacements["endzone_N_"+p]),256,128,smooth=True) for p in "LMR"]
    Image.fromarray(np.concatenate(native,axis=1)).save(native_path)
    receipt["changed"].extend(str(p.relative_to(output)) for p in (master_path,native_path))
    # A reviewed input may already contain this author's prior receipt. Its
    # replacement describes the new donor route; all copied art stays pinned.
    receipt["preserved"].pop("was_field_source_scope.json",None)
    receipt["changed"].append("was_field_source_scope.json")
    (output/"was_field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    mv.load_art(output)
    for name,digest in receipt["preserved"].items():
        if sha((output/name).read_bytes())!=digest:
            raise ValueError("Unselected source file changed: "+name)
    return receipt


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("art-root","out","wordmark-svg","w-svg","retail-left","retail-right"):
        parser.add_argument("--"+name,required=True,type=Path)
    args = parser.parse_args()
    receipt = author(args.art_root,args.out,args.wordmark_svg,args.w_svg,args.retail_left,args.retail_right)
    print(json.dumps(receipt["provenance"],indent=2))

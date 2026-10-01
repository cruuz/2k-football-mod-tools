"""Author approved residual sponsor type panels from the user's retail textures.

No fan artwork or roster data. Only reviewed rectangles are exported; transparent
pixels outside them avoid distributing retail art. Single process, no game writes.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
import nfl2k5_modern_venues_2026_art as cloth
DATA=ROOT/'data/nfl2k5_stadium_shared_art'
FONTS={'black':cloth.FONT_BLACK,'cond':cloth.FONT_COND}


def sha(data):
    return hashlib.sha256(data).hexdigest()

def dump(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", newline="\n")

def text_panel(size, lines, font_key, fg, bg=(0, 0, 0, 0), rotate=0):
    w, h = size
    area = (h, w) if rotate else (w, h)
    panel = Image.new("RGBA", area, bg)
    draw = ImageDraw.Draw(panel)
    text = "\n".join(lines)
    stroke = 0
    size = int(area[1] * 1.4)
    while size > 5:
        font = ImageFont.truetype(FONTS[font_key], size)
        box = draw.multiline_textbbox((0, 0), text, font=font, spacing=2, align="center", stroke_width=stroke)
        if box[2]-box[0] <= area[0]*0.87 and box[3]-box[1] <= area[1]*0.79:
            break
        size -= max(1, size//24)
    draw.multiline_text(((area[0]-box[2]+box[0])/2-box[0], (area[1]-box[3]+box[1])/2-box[1]),
                        text, font=font, fill=fg, spacing=2, align="center", stroke_width=stroke)
    return panel.rotate(rotate, expand=True) if rotate else panel

def sponsor_texture(retail, row):
    h, w = retail.shape[:2]
    if row['material'] == 'banner_corp':
        # Exactly u4's approved sheet, including its line breaks and fold rules.
        master = Image.new('RGBA', (w*4, h*4), (0, 0, 0, 0))
        alpha = np.asarray(Image.fromarray(retail[..., 3]).resize(master.size, Image.Resampling.NEAREST))
        for cell, box in cloth.CELLS.items():
            x0, y0, x1, y1 = box
            tile = np.asarray(cloth.draw_cloth(cell, x1-x0, y1-y0), dtype=np.float64)
            tile[..., :3] *= cloth.folds(retail, box)[..., None]
            tile[..., 3] = alpha[y0*4:y1*4, x0*4:x1*4]
            master.paste(Image.fromarray(np.uint8(np.clip(tile, 0, 255))), (x0*4, y0*4))
        native = cloth.reduce(master, w, h)
        with Image.open(cloth.OUT) as approved:
            if not np.array_equal(np.asarray(native), np.asarray(approved.convert('RGBA'))):
                raise ValueError('corporate cloth differs from the approved u4 sheet')
        return native, master, []
    master = Image.fromarray(retail).resize((w*4, h*4), Image.Resampling.NEAREST)
    mattes = []
    for op in row["ops"]:
        x0, y0, x1, y1 = op["rect"]
        sub = retail[y0:y1, x0:x1, :3]
        clear = op.get("bg") == "clear"
        if op.get("bg", "light") in ("light", "dark", "auto"):
            pixels = sub.reshape(-1, 3)
            lum = pixels.mean(axis=1)
            bg = tuple(int(x) for x in np.median(pixels[lum >= np.percentile(lum, 60)] if op.get("bg", "light") != "dark"
                                                 else pixels[lum <= np.percentile(lum, 40)], axis=0))
        elif clear:
            # A decal on a see-through wall texture: the rectangle goes transparent and any type is cut out on
            # it. The colour retail keeps under alpha 0 stays under it, so filtered edges fringe to the wall.
            if row.get("cloth"):
                raise ValueError(f"{row['venue']}/{row['material']}: a clear panel cannot take cloth alpha")
            under = sub[retail[y0:y1, x0:x1, 3] == 0]
            bg = tuple(int(x) for x in np.median(under if len(under) else sub.reshape(-1, 3), axis=0))
            mattes.append((op["rect"], bg))
        else:
            bg = tuple(bytes.fromhex(op["bg"].lstrip("#")))
        text = op.get("text", "")
        fg = (204, 0, 0) if text == "ESPN" else (1, 51, 105)
        if sum(bg)/3 < 100:
            fg = (255, 255, 255)
        tile = text_panel(((x1-x0)*4, (y1-y0)*4), text.split("\n"), "black", fg, bg+((0,) if clear else (255,)),
                          op.get("rotate", 0))
        if row.get("cloth"):
            a = np.array(tile, dtype=np.float64)
            a[..., :3] *= cloth.folds(retail, op["rect"])[..., None]
            a[..., 3] = np.asarray(Image.fromarray(retail[y0:y1,x0:x1,3]).resize(tile.size, Image.Resampling.NEAREST))
            tile = Image.fromarray(np.uint8(np.clip(a,0,255)))
        master.paste(tile, (x0*4,y0*4))
    native = np.array(cloth.reduce(master,w,h))
    for (x0, y0, x1, y1), bg in mattes:
        sub = native[y0:y1, x0:x1]
        sub[sub[..., 3] == 0, :3] = bg
    # Preserve every pixel outside the approved panel rectangles, including alpha.
    mask = np.zeros((h,w),bool)
    for x0,y0,x1,y1 in row["rects"]:
        mask[y0:y1,x0:x1]=True
    # Catalog PNGs carry only authored rectangles, never the untouched retail ads.
    native[~mask]=0
    authored_master=np.array(master)
    authored_master[~np.repeat(np.repeat(mask,4,axis=0),4,axis=1)]=0
    master=Image.fromarray(authored_master)
    return Image.fromarray(native),master,[]

def p8_preview(retail, native, row):
    """The actual writer's mip-chain quantization, decoded at native game size."""
    from mod_editor.core import nfl2k5_stadium_texture_writer as stw
    w,h=row['size'];levels=1
    while min(w>>levels,h>>levels)>=8:
        levels+=1
    dims=stw._mip_dimensions(w,h,levels)
    item=dict(key=row['material'],scene='stadium',size=[w,h],rects=row['rects'],layer='full')
    canvas=mv.compose(item,retail,retail,np.array(native),'d')
    mip=stw._generate_dynamic_mips(canvas.tobytes(),dims)
    palette,linear,_=stw.quantize_levels(mip,256)
    return Image.fromarray(np.asarray(palette,dtype=np.uint8)[np.frombuffer(linear[0],dtype=np.uint8).reshape(h,w)])

def read_textures(source, rows):
    ids = {mv.name_id(v+"dd.iff"): v for v in {r["venue"] for r in rows}}
    with mv._outer_image()(source, writable=False) as archive:
        entries = {ids[e.name_id]: e for e in archive.entries if e.name_id in ids}
        for prefix in sorted(entries):
            e = entries[prefix]
            scenes = mv.decode_scenes(archive.read(e.virtual_offset,e.size))
            rec,decoded = scenes["stadium"]
            for row in (r for r in rows if r["venue"] == prefix):
                index = mv.find_stadium_texture(rec,row["material"])
                if index is None:
                    raise ValueError(f"{prefix}: missing {row['material']}")
                rgba=mv.read_texture(decoded,rec,mv.p8_rows(rec)[index])
                if sha(rgba.tobytes()) != row["source_rgba_sha256"]:
                    raise ValueError(f"{prefix}/{row['material']}: retail source has changed")
                yield row,rgba

def contact_pages(entries, review):
    review.mkdir(parents=True,exist_ok=True)
    pages=[]
    # One texture per row: native before/after, 4x before/after. Split pages
    # to retain exact pixel scale in a viewer, including large 256-square atlases.
    for start in range(0,len(entries),4):
        group=entries[start:start+4]
        widths=[r["size"][0] for r in group];heights=[max(r["size"][1]*4,150)+58 for r in group]
        width=max(10*w+70 for w in widths);page=Image.new("RGB",(width,sum(heights)),"#bbb")
        d=ImageDraw.Draw(page);y=0
        for r,height in zip(group,heights):
            d.text((8,y+4),f"PROVED OFFLINE {r['venue']} / {r['material']} / {r['size']} P8 - raw retail vs this supplement alone",fill="black")
            x=8
            for title,im in [("Before 1x",Image.open(r["before"])),("After 1x",Image.open(r["after"])),
                             ("Before 4x",Image.open(r["before"]).resize((r['size'][0]*4,r['size'][1]*4),Image.Resampling.NEAREST)),
                             ("After 4x",Image.open(r["after"]).resize((r['size'][0]*4,r['size'][1]*4),Image.Resampling.NEAREST))]:
                d.text((x,y+20),title,fill="black");page.paste(im,(x,y+38),im.getchannel("A"));x+=im.width+14
            y+=height
        path=review/f"before_after_{start//4:02}.png";page.save(path,optimize=True);pages.append(path.name)
    (review/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>FB before / after</title><p>PROVED OFFLINE. Native P8-decoded output and exact 4x nearest-neighbour enlargement. Scroll horizontally for full scale.</p>'+''.join(f'<p><a href="{p}">{p}</a></p><img src="{p}" alt="Before and after at game size and 4x">' for p in pages), newline="\n")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retail',required=True,type=Path)
    ap.add_argument('--design',type=Path,default=DATA/'design.json')
    ap.add_argument('--output',type=Path,default=DATA/'venues')
    ap.add_argument('--review',required=True,type=Path)
    args=ap.parse_args();design=json.loads(args.design.read_text())
    for key,pin in design['font_sha256'].items():
        if sha(Path(FONTS[key]).read_bytes())!=pin:raise ValueError('font pin differs: '+key)
    manifests={};evidence=[];args.review.mkdir(parents=True,exist_ok=True)
    for row,retail in read_textures(args.retail,design['textures']):
        prefix,key=row['venue'],row['material']
        native,master,_=sponsor_texture(retail,row)
        folder=args.output/prefix;folder.mkdir(parents=True,exist_ok=True)
        file=folder/(key+'.png');mfile=folder/(key+'_4x.png')
        native.save(file,optimize=True);master.save(mfile,optimize=True)
        item=dict(scene='stadium',material=key,size=row['size'],format='P8',layer='full',file=file.name,
                  master=mfile.name,sha256=sha(file.read_bytes()),master_sha256=sha(mfile.read_bytes()),rects=row['rects'],
                  kind='sponsor',source_rgba_sha256=row['source_rgba_sha256'])
        manifests.setdefault(prefix,dict(schema=mv.ART_SCHEMA,venue_prefix=prefix,team=prefix,items=[]))['items'].append(item)
        before=args.review/(prefix+'_'+key+'_before.png');Image.fromarray(retail).save(before)
        preview=args.review/(prefix+'_'+key+'_after_p8.png');p8_preview(retail,native,row).save(preview)
        evidence.append(dict(row,before=str(before),after=str(preview),authored=str(file)))
        print(prefix,key,flush=True)
    for prefix,doc in manifests.items():
        path=args.output/prefix/'manifest.json'
        if path.is_file():
            doc['items'] += [i for i in json.loads(path.read_text())['items'] if i.get('kind') == 'field-logo']
        dump(path,doc)
    dump(args.review/'inventory.json',evidence);contact_pages(evidence,args.review)
    print('SPONSOR ITEMS',len(evidence),flush=True)

if __name__=='__main__':main()

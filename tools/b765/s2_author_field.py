"""Author the reviewed ATL field overlay, or install field overrides in a copied art root.

Coordinates are traced in the team's September 19, 2026 paint gallery, photo 29.
This is a clean vector reconstruction, not sampled grass or a photograph texture.
The side lettering comes from the supplied official high-resolution wordmark.
No original art root is modified. Native PNGs are reduced once from an 8x master.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
import numpy as np
from mod_editor.core import nfl2k5_modern_venues_2026 as mv

REFERENCE = "https://www.atlantafalcons.com/photos/photos-of-the-fresh-paint-job-in-mercedes-benz-stadium"
SCALE = 8
SIZE = (768, 128)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _point(x, y):
    # Photo 29: field sidelines x=100..1180; end line y=163, goal line y=375.
    return ((x - 100) * 768 / 1080 * SCALE, (y - 163) * 128 / 212 * SCALE)


def atl_master(wordmark):
    """Return the eight-times-native transparent end-zone paint and provenance."""
    image = Image.new("RGBA", (SIZE[0] * SCALE, SIZE[1] * SCALE))
    draw = ImageDraw.Draw(image)
    # Straight letter contours, matched to the overhead stencil, including the
    # falcon wing forming the left stroke of A. Coordinates retain the source frame.
    contours = [
        [(419,186),(554,186),(602,315),(552,315),(537,281),(482,281),
         (467,317),(463,354),(448,340),(434,319),(427,295),(424,265),(437,210)],
        [(572,186),(737,186),(737,221),(687,221),(687,315),(626,315),(626,221),(585,221)],
        [(754,186),(821,186),(821,277),(876,277),(876,315),(754,315)],
    ]
    for contour in contours:
        pts = [_point(*p) for p in contour]
        draw.polygon(pts, fill=(0,0,0,255))
        draw.line(pts + pts[:1], fill=(165,172,175,255), width=6*SCALE, joint="curve")
        draw.line(pts + pts[:1], fill=(255,255,255,255), width=3*SCALE, joint="curve")
    # A counter, transparent turf within the white border.
    counter = [_point(*p) for p in [(502,222),(512,222),(524,250),(491,250)]]
    draw.polygon(counter, fill=(0,0,0,0))
    draw.line(counter + counter[:1], fill=(165,172,175,255), width=6*SCALE, joint="curve")
    draw.line(counter + counter[:1], fill=(255,255,255,255), width=3*SCALE, joint="curve")
    # Feather cut-ins are white, with red accents in the black wing.
    for points in [
        [(443,207),(495,206),(446,218)],
        [(434,239),(478,222),(432,254)],
        [(430,282),(474,239),(433,295)],
        [(439,318),(473,267),(449,333)],
    ]:
        draw.polygon([_point(*p) for p in points], fill=(255,255,255,255))
    for points in [
        [(443,217),(482,212),(445,225)],
        [(434,258),(466,235),(433,271)],
        [(439,296),(463,264),(441,311)],
        [(449,325),(466,293),(453,338)],
    ]:
        draw.polygon([_point(*p) for p in points], fill=(167,25,48,255))
    source = Image.open(wordmark).convert("RGBA")
    if source.size != (2048,429):
        raise ValueError("Supply the reviewed 2048x429 official ATLANTA / FALCONS wordmark export")
    # Both crops are exact disjoint source lines, not a substitute typeface.
    for box, rect in [((467,0,1585,120),(119,246,360,281)),
                      ((0,198,2048,429),(937,246,1168,281))]:
        mask = source.crop(box).getchannel("A")
        # Some wordmark exports are opaque white; select their actual dark/red ink.
        if mask.getextrema() == (255,255):
            rgb = np.asarray(source.crop(box))[...,:3]
            mask = Image.fromarray(np.uint8(255 - rgb.min(axis=-1)))
        ink = Image.new("RGBA", mask.size, (255,255,255,0))
        ink.putalpha(mask)
        x0,y0 = _point(rect[0],rect[1]);x1,y1 = _point(rect[2],rect[3])
        ink = ink.resize((round(x1-x0),round(y1-y0)), Image.Resampling.LANCZOS)
        image.alpha_composite(ink,(round(x0),round(y0)))
    return image, dict(reference=REFERENCE, photo=29, trace="measured polygon reconstruction",
                       source_wordmark_sha256=sha(Path(wordmark).read_bytes()), native_size=list(SIZE),
                       master_scale=SCALE, colours=dict(black="#000000",red="#A71930",
                                                     silver="#A5ACAF",white="#FFFFFF"),
                       placement="overhead photograph normalized to end-zone bounds; visual witness pending")


def install_overrides(input_root, output_root, prefix, replacements):
    """Copy a standard Studio venue art root and update only the named field items.

    replacements maps material names to high-resolution RGBA Image objects.
    Other teams and non-field PNGs are copied byte for byte. This helper is reusable
    by a1; no venue geometry or stadium item can be selected here.
    """
    src,dst = Path(input_root).resolve(),Path(output_root)
    if dst.exists() or dst.resolve() == src.resolve():
        raise ValueError("The output must be a new, separate art root")
    original = mv.load_art(src)
    if prefix not in original["venues"]:
        raise ValueError(f"No authored venue {prefix} in the supplied root")
    manifest = Path(original["venues"][prefix]["manifest"])
    doc = json.loads(manifest.read_text())
    available = {i["material"] for i in doc["items"] if i["scene"] == "field"}
    if not replacements or not set(replacements) <= available:
        raise ValueError("Overrides must select existing field material items")
    shutil.copytree(src,dst)
    target = dst / manifest.relative_to(src)
    target.chmod(target.stat().st_mode | 0o200)  # frozen inputs can be read-only; only our copy changes
    modified = []
    for item in doc["items"]:
        if item["scene"] != "field" or item["material"] not in replacements:
            continue
        image = replacements[item["material"]].convert("RGBA")
        width,height = item["size"]
        if image.width < width or image.height < height:
            raise ValueError("A master must be at least the texture's native size")
        master_rel = f"refined/field/{item['material']}_master.png"
        native_rel = f"refined/field/{item['material']}.png"
        master_path,native_path = target.parent/master_rel,target.parent/native_rel
        master_path.parent.mkdir(parents=True,exist_ok=True)
        image.save(master_path)
        Image.fromarray(mv.resample(np.asarray(image),width,height,smooth=True)).save(native_path)
        item.update(file=native_rel,master=master_rel,sha256=sha(native_path.read_bytes()),
                    master_sha256=sha(master_path.read_bytes()),native_from_master=True)
        modified.extend([str(native_path.relative_to(dst)),str(master_path.relative_to(dst))])
    target.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    modified.append(str(target.relative_to(dst)))
    mv.load_art(dst)
    preserved = {str(p.relative_to(src)):sha(p.read_bytes()) for p in src.rglob("*")
                 if p.is_file() and str(p.relative_to(src)) != str(target.relative_to(dst))}
    for name,digest in preserved.items():
        if sha((dst/name).read_bytes()) != digest:
            raise ValueError(f"Unselected source file changed: {name}")
    return dict(schema="field_source_scope/v1",venue=prefix,selected=sorted(replacements),
                changed=modified,preserved=preserved)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art-root",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--wordmark",required=True,type=Path)
    args=parser.parse_args()
    master,provenance=atl_master(args.wordmark)
    panels={f"endzone_N_{part}":master.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
            for i,part in enumerate("LMR")}
    receipt=install_overrides(args.art_root.resolve(),args.out,"s01",panels)
    manifest=args.out/"ATL/venue/manifest.json"
    doc=json.loads(manifest.read_text())
    doc["mercedes_midfield_scale"]=1.6
    doc["notes"] += " S2: end-zone fused ATL stencil traced from official 2026 paint photo 29. Midfield quad scaled 1.6 about centre, estimated from photo 44 yard-line spacing; requires gameplay review."
    manifest.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["provenance"]=provenance
    receipt["provenance"]["midfield_scale"]=dict(scale=1.6,reference=REFERENCE,photo=44,
                                                    evidence="yard-line spacing; estimated, witness pending")
    (args.out/"field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    master.resize((1536,256),Image.Resampling.LANCZOS).save(args.out/"ATL_endzone_master_preview.png")
    print(args.out/"field_source_scope.json")


if __name__=="__main__":
    main()

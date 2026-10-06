"""Build Houston's separate 2026 field-paint masters from reviewed source marks.

The designer's clean primary H supplies the letterform. Its red border and blue
bevel become white, its face stays black, and the separate star is omitted as in
the team's September 11 field-painting photo 3. Placement is reference-estimated;
the north/south cardinal assignment needs Noah's camera review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
import numpy as np
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b765.s2_author_field import install_overrides

SCALE = 4
PINS = {
    "word_houston.png": "3ee7461b59b9e3e1fa13c31736492ecbfee83f0c6f17bc995b2b0c176a06dc8b",
    "word_texans.png": "8a3059b3d67ae35d84b574bf8a725b6c5db1a2a983d11b3b2aba34ab379326f8",
    "bull_full.png": "b849fa45c06fe9f902e58274df6dc5494521576b829b731033aeb6bccc76ef11",
    "designer_primary.jpg": "55ba4a673bd108b5d6c39bf191f0f5b03985cd68d9e02ec43acd0c135de3274e",
}
FIELD_REFERENCE = "https://www.houstontexans.com/photos/behind-the-scenes-kickoff-field-painting"
H_REFERENCE = "https://www.overturfdesign.studio/hlogo"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reviewed(path, key):
    data = Path(path).read_bytes()
    if sha(data) != PINS[key]:
        raise ValueError("Unexpected reviewed source: " + key)
    return Image.open(path).convert("RGBA")


def field_h(image):
    """Clean flat brand colours, with JPEG grain excluded from the paint mask."""
    a = np.asarray(image.convert("RGB"))[250:830, 670:1160]
    centres = np.asarray([[245,245,245], [235,0,40], [0,128,198],
                          [10,65,104], [2,16,24]], dtype=float)
    labels = ((a.astype(float)[:,:,None,:] - centres) ** 2).sum(axis=-1).argmin(axis=-1)
    component = Image.fromarray(np.uint8(labels != 0) * 255).copy()
    # Seed in the H face; the disjoint star is deliberately excluded.
    if component.getpixel((76,70)) != 255:
        raise ValueError("Reviewed H source no longer matches its crop")
    ImageDraw.floodfill(component, (76,70), 128)
    return Image.fromarray(np.uint8(np.isin(labels, [1,3]) & (np.asarray(component) == 128)) * 255)


def master(word, wordmark, bull, h):
    image = Image.new("RGBA", (768*SCALE,128*SCALE), (0,0,0,255))
    def place(mask, rect):
        box = mask.getbbox()
        if box is None:
            raise ValueError("A reviewed field mask is empty")
        x0,y0,x1,y1 = rect
        mask = mask.crop(box).resize(((x1-x0)*SCALE,(y1-y0)*SCALE), Image.Resampling.LANCZOS)
        paint = Image.new("RGBA", mask.size, (255,255,255))
        paint.putalpha(mask)
        image.alpha_composite(paint,(x0*SCALE,y0*SCALE))
    mask = wordmark.getchannel("A")
    if word == "houston":
        # The supplied extraction has negligible alpha remnants of the second
        # line. Crop the complete actual HOUSTON line, including antialiasing.
        mask = mask.crop((356,0,2084,149))
    place(mask,(111,28,654,101))
    a = np.asarray(bull)
    bull_mask = a[:,:,3].copy()
    bull_mask[a[:,:,:3].min(axis=-1) > 220] = 0  # star, dividing cut and outer white logo outline
    place(Image.fromarray(bull_mask),(26,34,93,95))
    place(h,(684,32,750,97))
    return image


def author(source, output, marks, designer, north_text="texans"):
    marks = Path(marks)
    h = field_h(reviewed(designer, "designer_primary.jpg"))
    bull = reviewed(marks / "bull_full.png", "bull_full.png")
    masters = {word: master(word, reviewed(marks / ("word_"+word+".png"),
                                             "word_"+word+".png"), bull, h)
               for word in ("texans","houston")}
    north = masters[north_text]
    south = masters["houston" if north_text == "texans" else "texans"]
    replacements = {"endzone_N_"+part: north.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
                    for i,part in enumerate("LMR")}
    receipt = install_overrides(source, output, "s37", replacements)
    path = Path(output) / "HOU/venue/manifest.json"
    doc = json.loads(path.read_text())
    for item in doc["items"]:
        if item["scene"] == "field" and item["material"] in replacements:
            item["layer"] = "full"
    for i,part in enumerate("LMR"):
        key = "endzone_S_"+part
        if any(item["scene"] == "field" and item["material"] == key for item in doc["items"]):
            raise ValueError("Expected the reviewed shared-end HOU source")
        panel = south.crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
        native_rel, master_rel = "refined/field/"+key+".png", "refined/field/"+key+"_master.png"
        native_path, master_path = path.parent/native_rel,path.parent/master_rel
        panel.save(master_path)
        Image.fromarray(mv.resample(np.asarray(panel),256,128,smooth=True)).save(native_path)
        doc["items"].append(dict(scene="field",material=key,layer="full",size=[256,128],
                                 file=native_rel,master=master_rel,sha256=sha(native_path.read_bytes()),
                                 master_sha256=sha(master_path.read_bytes()),native_from_master=True))
        receipt["changed"].extend(str(p.relative_to(output)) for p in (native_path,master_path))
    doc["split_shared_endzones"] = True
    doc["notes"] += " S2: independent TEXANS/HOUSTON ends, bull and black/white H from dated paint references. Footprints and cardinal assignment are estimated and need camera review."
    path.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["provenance"] = dict(field_reference=FIELD_REFERENCE,field_photos=[1,3],
                                 h_designer=H_REFERENCE,source_pins=PINS,north_word=north_text,
                                 south_word="houston" if north_text=="texans" else "texans",
                                 native_panel_size=[256,128],master_scale=SCALE,
                                 placement="reference-estimated; cardinal assignment and gameplay witness pending")
    (Path(output)/"hou_field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    for word, image in masters.items():
        image.resize((1536,256),Image.Resampling.LANCZOS).save(Path(output)/("HOU_"+word+"_master_preview.png"))
    mv.load_art(output)
    return receipt


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--art-root",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--marks",required=True,type=Path)
    p.add_argument("--designer-primary",required=True,type=Path)
    p.add_argument("--north-text",choices=("texans","houston"),default="texans")
    a=p.parse_args()
    print(json.dumps(author(a.art_root,a.out,a.marks,a.designer_primary,a.north_text)["provenance"],indent=2))

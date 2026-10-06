"""Author separate Detroit 2026 field-paint masters from reviewed exact marks.

The official footer supplies DETROIT's custom glyphs. A clean contour trace
removes JPEG stair noise; it retains seven glyphs and three counters. This is a
vector reconstruction from a 445x81 raster, not a larger raster source or a
substitute font. LIONS retains the supplied exact SVG paths. Body height and
centering preserve the v0.4 native placement. White outline width and the default
N=LIONS/S=DETROIT assignment are estimated and require camera review.
DETROIT's width compensates the native world/UV aspect; its original custom
letterform proportions are retained on the field rather than in atlas pixels.

This offline author command needs Pillow, NumPy, OpenCV, SciPy and Inkscape.
Studio pack builds consume the installed PNGs and do not invoke these tools.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image
import numpy as np
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b765.s2_author_field import install_overrides

SCALE = 4
FOOTER_SHA256 = "659c3222b9293a5b18f612d32e1f86a6b47757139f44c0057d82c9b5048bf40c"
LIONS_SHA256 = "f48a8f2e24a1de2422875bf057add99799155d0933c46342b1e7608b0435235b"
FOOTER_URL = "https://media.ceros.com/detroit-lions/images/2024/04/09/a4c4dd41fefee93503573ba2b6c166b2/detroit-lions-logo-footer.jpg"
FIELD_REFERENCE = "https://www.detroitlions.com/photos/lions-vs-saints-week-1-photos"
CITY_FIELD_REFERENCE = "https://www.detroitlions.com/photos/lions-vs-jets-week-3-photos"
NS = "{http://www.w3.org/2000/svg}"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reviewed(path, digest, label):
    data = Path(path).read_bytes()
    if sha(data) != digest:
        raise ValueError("Unexpected reviewed Detroit source: " + label)
    return data


def trace_city(footer):
    """Return exact-source polygon SVG and an independent sampling-grid check."""
    import cv2
    a = np.asarray(Image.open(footer).convert("RGB"))[69:150, 131:576]
    mask = np.uint8((a[:, :, 0] < 128) & (a[:, :, 2] > 120) & (a[:, :, 1] < 185)) * 255
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if len(contours) != 10 or sum(int(v[3]) == -1 for v in hierarchy[0]) != 7:
        raise ValueError("Reviewed city crop no longer contains seven glyphs and three counters")
    paths = []
    for contour in contours:
        if cv2.contourArea(contour) < 3:
            raise ValueError("Unexpected JPEG speck in reviewed city crop")
        q = cv2.approxPolyDP(contour, 1.10, True).reshape(-1, 2).astype(float) + 0.5
        paths.append("M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in q) + " Z")
    svg = ET.Element(NS + "svg", dict(width="445", height="81", viewBox="0 0 445 81"))
    # OpenCV's contour follows boundary pixel centres. A half-pixel outset
    # restores the original boundary cells; it is not an artistic glyph weight.
    ET.SubElement(svg, NS + "path", {"d": " ".join(paths), "fill": "#ffffff",
                                    "fill-rule": "evenodd", "stroke": "#ffffff",
                                    "stroke-width": "1", "stroke-linejoin": "round"})
    return svg, mask, dict(contours=10, outer_glyphs=7, holes=3,
                          tolerance_source_px=1.10, source_pixel_cell_recovery_outset_px=0.5)


def render(svg, output, width, height):
    subprocess.run(["inkscape", str(svg), "--export-type=png", "--export-background-opacity=0",
                    "--export-filename=" + str(output), "--export-width=" + str(width),
                    "--export-height=" + str(height)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with Image.open(output) as image:
        return image.convert("RGBA").getchannel("A")


def masters(footer, lions_svg):
    """Render both reviewed marks at four times the native atlas resolution."""
    from scipy.ndimage import binary_erosion, distance_transform_edt, grey_dilation
    reviewed(footer, FOOTER_SHA256, "official footer JPG")
    reviewed(lions_svg, LIONS_SHA256, "exact LIONS SVG")
    city, source_mask, validation = trace_city(footer)
    lions = ET.fromstring(Path(lions_svg).read_bytes())
    for node in lions.iter():
        if node.tag == NS + "path":
            node.set("fill", "#ffffff")
            node.attrib.pop("style", None)
    vectors = {"detroit": ET.tostring(city, encoding="utf-8", xml_declaration=True),
               "lions": ET.tostring(lions, encoding="utf-8", xml_declaration=True)}
    images = {}
    with tempfile.TemporaryDirectory(prefix="b765-s2-detroit-") as temporary:
        temp = Path(temporary)
        for word, vector in vectors.items():
            (temp / (word + ".svg")).write_bytes(vector)
        trace = render(temp / "detroit.svg", temp / "check.png", 445, 81)
        got, want = np.asarray(trace) >= 128, source_mask >= 128
        intersection, union = int((got & want).sum()), int((got | want).sum())
        iou = intersection / union
        if iou < 0.98:
            raise ValueError("City reconstruction exceeds reviewed source-shape tolerance")
        we, ge = want ^ binary_erosion(want), got ^ binary_erosion(got)
        distances = np.r_[distance_transform_edt(~we)[ge], distance_transform_edt(~ge)[we]]
        validation.update(source_mask_iou=iou, changed_source_mask_pixels=int((got ^ want).sum()),
                          source_mask_area=int(want.sum()), reconstruction_mask_area=int(got.sum()),
                          bidirectional_boundary_max_source_px=float(distances.max()),
                          bidirectional_boundary_p99_source_px=float(np.quantile(distances, .99)),
                          bidirectional_boundary_mean_source_px=float(distances.mean()),
                          native_footprint_city_source_scale=[487/445, 78/81])
        for word, width in (("lions", 330), ("detroit", 487)):
            body = render(temp / (word + ".svg"), temp / (word + ".png"), width*SCALE, 78*SCALE)
            coverage = Image.new("L", (768*SCALE, 128*SCALE))
            coverage.paste(body, (int((768-width)*SCALE/2), 25*SCALE))
            radius = 5*SCALE
            y, x = np.ogrid[-radius:radius+1, -radius:radius+1]
            outline = Image.fromarray(grey_dilation(np.asarray(coverage), footprint=x*x+y*y <= radius*radius))
            master = Image.new("RGBA", coverage.size, (0,118,182,255))
            white = Image.new("RGBA", coverage.size, (255,255,255,0)); white.putalpha(outline)
            master.alpha_composite(white)
            blue = Image.new("RGBA", coverage.size, (0,118,182,0)); blue.putalpha(coverage)
            master.alpha_composite(blue)
            images[word] = master
    return images, vectors, validation


def physical_aspect():
    """Document the measured s09 mapping; all nine original variants match."""
    panels = [
        dict(x_cm=[-2443.47998046875,-810.2064819335938], u=[3.0517112463712692e-05,.9921875]),
        dict(x_cm=[-810.2064819335938,810.2064819335938], u=[.007827520370483398,.9921875]),
        dict(x_cm=[810.2064819335938,2443.47998046875], u=[.007827520370483398,.9999847412109375]),
    ]
    depth = 919.52392578125
    v = [3.0517112463712692e-05,.9999847412109375]
    def world_x(px):
        index = min(2,max(0,int(px//256)))
        panel = panels[index]
        u = (px-index*256)/256
        lo,hi = panel["x_cm"]
        u0,u1 = panel["u"]
        return lo+(u-u0)/(u1-u0)*(hi-lo)
    height = depth*(78/128)/(v[1]-v[0])
    width = world_x(384+487/2)-world_x(384-487/2)
    aspect = width/height
    return dict(source_glyph_aspect=445/81,
                native_world_atlas_cm=[4886.9599609375,depth], original_panel_maps=panels,
                original_panel_v=v, body_height_world_cm=height, city_body_width_world_cm=width,
                nominal_city_width_px=483.77686770634807,
                uv_gutter_compensated_city_width_px=486.7563453803958,
                chosen_city_width_px=487, physical_glyph_aspect=aspect,
                physical_aspect_error_percent=(aspect/(445/81)-1)*100,
                formula="Panel i=floor(x/256), u=(x-256*i)/256; world_x=x_min+(u-u_min)/(u_max-u_min)*(x_max-x_min). Bodyheight=depth*(78/128)/(v_max-v_min). Solve [world_x(384+w/2)-world_x(384-w/2)]/bodyheight=445/81.",
                method="actual original endzone panel positions and UV gutters, equal in all9 variants; no geometry change")


def author(art_root, output_root, footer_jpg, lions_svg, north_text="lions"):
    """Copy a complete Studio art root; change only six Detroit field panels."""
    source, output = Path(art_root).resolve(), Path(output_root).resolve()
    if north_text not in ("lions", "detroit"):
        raise ValueError("North text must be lions or detroit")
    if output.exists() or output == source or output.is_relative_to(source):
        raise ValueError("The output must be a new, separate art root outside the input")
    source_art = mv.load_art(source)
    venue = source_art["venues"].get("s09")
    if venue is None:
        raise ValueError("The complete input art root lacks Detroit s09")
    original_manifest = json.loads(Path(venue["manifest"]).read_text())
    if any(i["scene"] == "field" and i["material"].startswith("endzone_S_")
           for i in original_manifest["items"]):
        raise ValueError("Expected the reviewed shared-end Detroit source")
    images, vectors, validation = masters(footer_jpg, lions_svg)
    south_text = "detroit" if north_text == "lions" else "lions"
    replacements = {"endzone_N_"+part: images[north_text].crop(
        (i*256*SCALE, 0, (i+1)*256*SCALE, 128*SCALE)) for i, part in enumerate("LMR")}
    receipt = install_overrides(source, output, "s09", replacements)
    manifest = output / "DET/venue/manifest.json"
    doc = json.loads(manifest.read_text())
    for item in doc["items"]:
        if item["scene"] == "field" and item["material"] in replacements:
            item["layer"] = "full"
    for i, part in enumerate("LMR"):
        key = "endzone_S_" + part
        panel = images[south_text].crop((i*256*SCALE,0,(i+1)*256*SCALE,128*SCALE))
        native_rel, master_rel = "refined/field/"+key+".png", "refined/field/"+key+"_master.png"
        native_path, master_path = manifest.parent/native_rel, manifest.parent/master_rel
        panel.save(master_path)
        Image.fromarray(mv.resample(np.asarray(panel),256,128,smooth=True)).save(native_path)
        doc["items"].append(dict(scene="field",material=key,layer="full",size=[256,128],
                                 file=native_rel,master=master_rel,sha256=sha(native_path.read_bytes()),
                                 master_sha256=sha(master_path.read_bytes()),native_from_master=True))
        receipt["changed"].extend(str(p.relative_to(output)) for p in (native_path,master_path))
    doc["split_shared_endzones"] = True
    doc["field_prefix_loan"] = True
    doc["notes"] += (" S2: independent blue-fill/white-outline LIONS and DETROIT ends; exact LIONS vector and "
                     "clean contour reconstruction of official DETROIT glyphs. Body height/centering preserve native "
                     "placement; city width compensates native world/UV aspect. Stroke width and N/S assignment "
                     "are estimated and need camera review.")
    manifest.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")
    receipt["provenance"] = dict(
        official_city_page="https://rivalries.detroitlions.com/", official_city_asset=FOOTER_URL,
        official_city_sha256=FOOTER_SHA256, exact_lions_svg_sha256=LIONS_SHA256,
        city_source_crop=[131,69,576,150], city_source_pixels=[445,81],
        trace="OpenCV closed contours, Douglas-Peucker1.10sourcepx + halfpixel cell recovery; no substitute font",
        trace_validation=validation, field_reference=FIELD_REFERENCE, field_date="2026-09-13",
        city_field_reference=CITY_FIELD_REFERENCE, city_field_date="2026-09-27",
        city_field_photo="https://static.clubs.nfl.com/image/upload/lions/rpjby6cv3zhvjmkh6gue.jpg",
        north_word=north_text, south_word=south_text, native_panel_size=[256,128], master_scale=SCALE,
        body_height_native_px=78, outline_outset_native_px=5,
        city_body_width_native_px=487,
        physical_aspect=physical_aspect(),
        placement="native body height/centering retained; physical city aspect compensated; stroke width and N/S assignment estimated")
    for word in ("lions", "detroit"):
        (output / ("DET_"+word+"_source_mask.svg")).write_bytes(vectors[word])
        receipt["changed"].extend("DET_"+word+suffix for suffix in ("_source_mask.svg","_master.png","_native.png"))
        images[word].save(output / ("DET_"+word+"_master.png"))
        Image.fromarray(mv.resample(np.asarray(images[word]),768,128,smooth=True)).save(
            output / ("DET_"+word+"_native.png"))
    (output / "det_field_source_scope.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    mv.load_art(output)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art-root",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--footer",required=True,type=Path)
    parser.add_argument("--lions-svg",required=True,type=Path)
    parser.add_argument("--north-text",choices=("lions","detroit"),default="lions")
    args = parser.parse_args()
    print(json.dumps(author(args.art_root,args.out,args.footer,args.lions_svg,args.north_text)["provenance"],indent=2))

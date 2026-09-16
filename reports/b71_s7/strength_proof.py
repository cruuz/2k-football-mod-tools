"""Decode one day, one afternoon and one night Arrowhead bundle at retail, strength 0.5 and 1.0;
report the colour-map means, the rig values and the calibrated on-screen turf prediction."""
import json, sys, colorsys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_color as mc
from PIL import Image, ImageDraw
GAME = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
OUT = ROOT / "reports" / "b71_s7"
def settings(k):
    d = mc.default_settings(); d["values"]["master.strength"] = k; return d
def map_mean(payload, outer):
    tx, inv, ResourceRecord, HEADER = mc._tools()
    chunk = tx.parse_chunks(payload, allow_trailing=True)[0]
    rec, out, record = mc._scene(payload, chunk, outer)
    texture = next(t for t in rec["embedded_textures"] if t.get("mapped_material_names") == ["color_premipped"])
    info = inv.texture_info(out, texture["descriptor_offset"], rec["name"], texture["index"])
    rgba = tx.texture_to_rgba(out, record.as_chunk(), info)
    px = [rgba[i:i + 3] for i in range(0, len(rgba), 4)]
    return tuple(round(sum(p[c] for p in px) / len(px), 1) for c in range(3))
rows = []
pins = {r["name"]: r for r in mc._pins()["bundles"]}
with mc._outer_image()(GAME / "vc_53450030") as archive:
    for name, rig in (("s13dd.iff", "day"), ("s13ad.iff", "afternoon"), ("s13nd.iff", "night_indoor")):
        row = pins[name]; entry = archive.entries[row["outer"]]
        data = archive.read(entry.virtual_offset, entry.size)
        result = dict(bundle=name, rig=rig)
        for label, k in (("retail", 0.0), ("half", 0.5), ("full", 1.0)):
            after, edits = mc.modern_bundle(data, outer_index=row["outer"], settings=settings(k))
            mean = map_mean(after, row["outer"])
            table = mc.configured_rig(rig, settings(k))
            pred = mc.predicted_on_screen(mean, rig, settings=settings(k))
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in pred))
            result[label] = dict(map_mean=mean, ambient_intensity=round(table["ambient_intensity"], 4), key=round(table["lights"][0][1], 4),
                                 fill=round(table["lights"][1][1], 4), shadow=round(table["shadow"], 4), key_colour=[round(c, 3) for c in table["lights"][0][0]],
                                 predicted=pred, saturation=round(s, 3), value=round(v, 3), bundle_sha256=mc.sha(after))
            if k == 0.0: result["retail_identical"] = after == data
        rows.append(result); print(json.dumps(result, indent=1), flush=True)
json.dump(rows, open(OUT / "strength_proof.json", "w"), indent=1)
sheet = Image.new("RGB", (3 * 130 + 40, len(rows) * 150 + 30), (30, 30, 30)); d = ImageDraw.Draw(sheet)
for i, r in enumerate(rows):
    for j, label in enumerate(("retail", "half", "full")):
        x, y = 20 + j * 130, 20 + i * 150
        d.rectangle((x, y, x + 110, y + 90), fill=tuple(r[label]["predicted"]))
        d.text((x, y + 95), f"{r['rig']} {label}", fill=(230, 230, 230)); d.text((x, y + 110), str(r[label]["predicted"]), fill=(230, 230, 230))
sheet.save(OUT / "strength_swatches.png"); print("swatches written")

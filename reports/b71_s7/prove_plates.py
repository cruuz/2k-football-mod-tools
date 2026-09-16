"""Render the lit possession plate for all 32 teams with the sprite preview, measure the
label contrast on the rendered plate, and build the contact sheet plus DAL-at-KC previews."""
import json, sys, colorsys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_scorebug_sprite as sprite, nfl2k5_scorebug_exact as exact
from mod_editor.core.nfl2k5_scorebug_resources import TEAM_LOGOS
OUT = ROOT / "reports" / "b71_s7"; OUT.mkdir(exist_ok=True)
SHOT = Path("/home/noah/Desktop/2K5-8 Editors/beta71_evidence/disc_n_3.png")
t0 = time.time()
pv = sprite.NativePreview()
print("compiled", round(time.time() - t0, 1), "s", flush=True)

def crop(raster_path, box, pad=2, scale=3):
    im = Image.open(raster_path).convert("RGB")
    k = im.width / 640
    x0, y0, x1, y1 = (int(round(v * k)) for v in box)
    c = im.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    return c.resize((c.width * scale, c.height * scale), Image.Resampling.LANCZOS)

def plate_colour(raster_path, box):
    im = Image.open(raster_path).convert("RGB"); k = im.width / 640
    x0, y0, x1, y1 = (int(round(v * k)) for v in box)
    px = [im.getpixel((x, y)) for y in range(y0 + 2, y1 - 2) for x in range(x0 + 4, x1 - 4)]
    px = [p for p in px if max(p) - min(p) > 12 or max(p) < 120]  # drop white label ink and grey antialiasing
    px.sort(key=lambda p: sum(p)); return px[len(px) // 2]

rows = []; crops = {}
for team in sorted(TEAM_LOGOS):
    away = "KC" if team != "KC" else "DEN"
    state = dict(home=team, away=away, possession="home", down=1, distance=10, quarter=1, clock=900, play_clock=25, home_score=0, away_score=0)
    path = OUT / f"plate_{team}_43.png"
    result = pv.render(path, screenshot=SHOT, state=state, widescreen=False)
    box = result["quads"]["plate"]
    rendered = plate_colour(path, box)
    expected = exact.lit_plate_rgb(exact.plate_rgb(team))
    contrast = exact.contrast_ratio((255, 255, 255), rendered)
    rows.append(dict(team=team, tint=list(exact.plate_rgb(team)), expected_under_label=list(expected), rendered=list(rendered),
                     contrast=round(contrast, 2), wing=list(exact.wing_rgb(team))))
    crops[team] = crop(path, box)
    print(team, rendered, expected, round(contrast, 2), round(time.time() - t0), "s", flush=True)
json.dump(rows, open(OUT / "plate_contrast.json", "w"), indent=1)
w, h = max(c.width for c in crops.values()), max(c.height for c in crops.values())
sheet = Image.new("RGB", (4 * (w + 8) + 8, 8 * (h + 22) + 8), (24, 24, 24)); d = ImageDraw.Draw(sheet)
for n, (team, c) in enumerate(sorted(crops.items())):
    x, y = 8 + (n % 4) * (w + 8), 8 + (n // 4) * (h + 22)
    sheet.paste(c, (x, y)); r = rows[n]
    d.text((x, y + h + 3), f"{team}  contrast {r['contrast']:.1f}:1", fill=(230, 230, 230))
sheet.save(OUT / "plate_contact_sheet.png")
# DAL at KC standard state (possession DAL), both aspects, bar crop at 2x
for wide, tag in ((False, "43"), (True, "169")):
    path = OUT / f"dal_kc_{tag}.png"
    result = pv.render(path, screenshot=SHOT, state=dict(away="DAL", home="KC", possession="away"), widescreen=wide)
    q = result["quads"]; boxes = [q[n] for n in ("body_left", "body", "body_right") if n in q]
    bar = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    crop(path, bar, pad=6, scale=2).save(OUT / f"dal_kc_{tag}_2x.png")
# wings of the darkest primaries, 3x
for team in ("DAL", "GB", "PHI", "PIT", "NYG"):
    path = OUT / f"plate_{team}_43.png"; q = json.load(open(path.with_suffix(".json")))["quads"]
    boxes = [q[n] for n in ("body_left", "body", "body_right") if n in q]
    bar = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    crop(path, bar, pad=6, scale=3).save(OUT / f"bar_{team}_43_3x.png")
print("done", round(time.time() - t0), "s", "min contrast", min(r["contrast"] for r in rows))

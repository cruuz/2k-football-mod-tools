"""Author the Modern Arrowhead texture set (data/nfl2k5_modern_arrowhead/*.png).

Inputs: the private retail texture exports of the Arrowhead night package (seat, tarp, end zone
and grass tones are read from them so the replacements keep the retail shading) and the current
Kansas City mark. Every output is an exact-dimension RGBA8 PNG for one embedded P8 texture of
the s13 stadium packages. Run once by the author; the PNGs ship in the reviewed catalog.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nfl2k5_modern_arrowhead"
RETAIL = Path("/home/noah/2k-football-mod-tools/assets/intermediate/nfl2k5/scne_textures")
RED = (227, 24, 55)        # Chiefs red
DARK_RED = (150, 12, 34)
GOLD = (255, 184, 28)
WHITE = (255, 255, 255)
FONT_BOLD = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
FONT_WIDE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def retail(name):
    """The retail export PNG of the night package texture (by mapped material name)."""
    import csv
    rows = csv.DictReader(open(ROOT / "reports/assets/nfl2k5_scne_texture_png_occurrences.tsv"), delimiter="\t")
    for row in rows:
        if row["outer_index"] == "3255" and name in row["mapped_material_names"].split("|"):
            return Image.open(Path("/home/noah/2k-football-mod-tools") / row["png_path"]).convert("RGBA")
    raise SystemExit(f"retail export for {name} not found")


def logo(size):
    im = Image.open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1000/arrowhead/kc500.png").convert("RGBA")
    im = im.crop(im.getbbox())
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    return im


def text_centered(draw, box, text, fnt, fill, outline=None, width=0):
    x0, y0, x1, y1 = box
    bb = draw.textbbox((0, 0), text, font=fnt)
    # Shrink until the text fits its box with a small margin.
    while bb[2] - bb[0] > (x1 - x0) - 6 and fnt.size > 8:
        fnt = ImageFont.truetype(fnt.path, fnt.size - 1)
        bb = draw.textbbox((0, 0), text, font=fnt)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    x = x0 + (x1 - x0 - w) / 2 - bb[0]
    y = y0 + (y1 - y0 - h) / 2 - bb[1]
    if outline:
        draw.text((x, y), text, font=fnt, fill=outline, stroke_width=width, stroke_fill=outline)
    draw.text((x, y), text, font=fnt, fill=fill)


def recolour(im, ramp_dark, ramp_light):
    """Keep the retail shading (luminance) and re-map it onto a two-colour ramp."""
    lum = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    out = ImageOps.colorize(lum, ramp_dark, ramp_light).convert("RGBA")
    out.putalpha(im.getchannel("A"))
    return out


def grass_base(size, seed=7):
    """A calm green base with faint mowing stripes, matching the retail end zone tone."""
    ref = retail("endzone_N_M")
    greens = sorted(p[:3] for p in ref.getdata() if p[1] > p[0] + 10 and p[1] > p[2] + 10)
    base = greens[len(greens) // 2] if greens else (70, 96, 44)
    im = Image.new("RGBA", size, base + (255,))
    d = ImageDraw.Draw(im)
    for x in range(0, size[0], 64):
        d.rectangle((x, 0, x + 31, size[1]), fill=tuple(min(255, c + 8) for c in base) + (255,))
    noise = Image.effect_noise(size, 12).convert("L")
    im = Image.composite(im, Image.new("RGBA", size, tuple(max(0, c - 10) for c in base) + (255,)), noise.point(lambda v: 255 if v > 118 else 200))
    return im


def endzones():
    """One 768x128 strip split into the L, M, R textures: red CHIEFS with white trim on grass, the mark at both ends."""
    strip = grass_base((768, 128))
    d = ImageDraw.Draw(strip)
    fnt = font(FONT_BOLD, 124)
    text_centered(d, (150, 0, 618, 128), "CHIEFS", fnt, RED, outline=WHITE, width=5)
    mark = logo(96)
    strip.alpha_composite(mark, (28, 16))
    strip.alpha_composite(ImageOps.mirror(mark), (768 - 28 - mark.width, 16))
    for i, name in enumerate(("endzone_L", "endzone_M", "endzone_R")):
        strip.crop((i * 256, 0, (i + 1) * 256, 128)).save(OUT / f"{name}.png")


def center_logo():
    im = grass_base((256, 256))
    mark = logo(216)
    im.alpha_composite(mark, ((256 - mark.width) // 2, (256 - mark.height) // 2))
    im.save(OUT / "center_logo.png")


def seats():
    for name, out in (("seat03", "seat03"), ("seat01", "seat_rows")):
        im = retail(name)
        recolour(im, (92, 6, 20), (235, 52, 78)).save(OUT / f"{out}.png")


def tarp():
    recolour(retail("tarpGreen"), (110, 10, 26), (214, 30, 58)).save(OUT / "tarp_red.png")


def wall_pads():
    # yardside 64x64: red pad, gold top rail, the mark centred.
    im = Image.new("RGBA", (64, 64), RED + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 63, 5), fill=GOLD + (255,))
    d.rectangle((0, 6, 63, 7), fill=DARK_RED + (255,))
    mark = logo(40)
    im.alpha_composite(mark, ((64 - mark.width) // 2, 14))
    im.save(OUT / "yardside.png")
    # yardfront 128x128: red pad, gold rail, CHIEFS KINGDOM in white.
    im = Image.new("RGBA", (128, 128), RED + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 127, 9), fill=GOLD + (255,))
    d.rectangle((0, 10, 127, 12), fill=DARK_RED + (255,))
    text_centered(d, (0, 14, 128, 70), "CHIEFS", font(FONT_BOLD, 46), WHITE)
    text_centered(d, (0, 66, 128, 122), "KINGDOM", font(FONT_BOLD, 36), WHITE)
    im.save(OUT / "yardfront.png")


def boards():
    # banner_corp 256x256: four fascia board rows (tiled around the stadium).
    im = Image.new("RGBA", (256, 256), (20, 20, 20, 255))
    d = ImageDraw.Draw(im)
    rows = ((( 20, 110,  50), "DRAFTKINGS SPORTSBOOK", WHITE),
            ((245, 245, 245), "BET LIVE NOW", (20, 110, 50)),
            ((226,  0, 116), "T MOBILE", WHITE),
            (RED, "CHIEFS KINGDOM", WHITE))
    for i, (bg, label, fg) in enumerate(rows):
        y0 = i * 64
        d.rectangle((0, y0, 255, y0 + 63), fill=bg + (255,))
        d.rectangle((0, y0 + 60, 255, y0 + 63), fill=(10, 10, 10, 255))
        text_centered(d, (0, y0, 256, y0 + 60), label, font(FONT_BOLD, 34), fg)
    im.save(OUT / "banner_corp.png")
    # ad01 256x256: a 2x4 grid of sponsor panels.
    im = Image.new("RGBA", (256, 256), (16, 16, 16, 255))
    d = ImageDraw.Draw(im)
    panels = (((20, 60, 130), "GEHA", WHITE), ((0, 55, 120), "FORD", WHITE), ((200, 16, 46), "STATE FARM", WHITE), ((0, 92, 170), "BUD LIGHT", WHITE),
              ((20, 110, 50), "DRAFTKINGS", WHITE), ((240, 240, 240), "PEPSI", (0, 60, 150)), (RED, "CHIEFS", GOLD), ((30, 30, 30), "GEHA FIELD AT ARROWHEAD", WHITE))
    for i, (bg, label, fg) in enumerate(panels):
        x0, y0 = (i % 2) * 128, (i // 2) * 64
        d.rectangle((x0 + 2, y0 + 2, x0 + 125, y0 + 61), fill=bg + (255,))
        size = 26 if len(label) <= 10 else 16
        text_centered(d, (x0 + 2, y0 + 2, x0 + 126, y0 + 62), label, font(FONT_BOLD, size), fg)
    im.save(OUT / "ad01.png")


def fan_banners():
    im = Image.new("RGBA", (128, 128), RED + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 127, 127), outline=GOLD + (255,), width=6)
    text_centered(d, (0, 14, 128, 64), "CHIEFS", font(FONT_BOLD, 44), WHITE)
    text_centered(d, (0, 62, 128, 114), "KINGDOM", font(FONT_BOLD, 34), GOLD)
    im.save(OUT / "banner_home_team.png")
    im = Image.new("RGBA", (256, 128), WHITE + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 255, 127), outline=RED + (255,), width=6)
    text_centered(d, (8, 8, 248, 66), "MAHOMES 15", font(FONT_BOLD, 50), RED)
    text_centered(d, (8, 64, 248, 120), "KELCE 87", font(FONT_BOLD, 44), (30, 30, 30))
    im.save(OUT / "banner_home_player.png")
    im = Image.new("RGBA", (128, 128), GOLD + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 127, 127), outline=RED + (255,), width=6)
    text_centered(d, (0, 10, 128, 62), "GO", font(FONT_BOLD, 50), RED)
    text_centered(d, (0, 60, 128, 118), "CHIEFS", font(FONT_BOLD, 40), RED)
    im.save(OUT / "banner_away_team.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    endzones(); center_logo(); seats(); tarp(); wall_pads(); boards(); fan_banners()
    for p in sorted(OUT.glob("*.png")):
        im = Image.open(p); print(p.name, im.size, im.mode, p.stat().st_size)

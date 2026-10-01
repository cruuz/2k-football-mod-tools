"""The 2026 venue art's name and sponsor fixes in st3's board-kit venues (st3, job st7, 2026-09-28; the SN stale-name
audit and main's calls of 2026-09-28 22:12 and 23:05). Denver's adBoard02 and every venue's banner_corp need nothing
here: u4's own Broncos art (its 10a rows) and its league sponsor sheet already turn their MOTOROLA, Reebok and ESPN
VIDEOGAMES cells into NFL NETWORK, NFL+ and ESPN (PROVED OFFLINE on the planner with u4's root_final art).

On st2's rect-extras mechanism (nfl2k5_modern_venues_2026.TABLE_EXTRAS; st2's b2f8334f and 77244b17) and its art
tool's shared helpers (author_cells, the type panels, reduce), which this file imports and never changes:

* s30 lambert39: the header "at Cleveland Browns Stadium" that the scene still draws on the south upper fascia (group268,
  V 0 to 0.0917) becomes HUNTINGTON BANK FIELD in plain type, in the header's own colours (its peach lettering on its
  dark ground); the header's border rows stay. Its MOTOROLA panel (drawn by the 2004 boards when the board kit is off)
  takes u4's NFL NETWORK panel.
* s17 swall3: the field-wall posters' 2004 players photo and the STALLWORTH/BENTLEY strip become plain-type posters:
  SAINTS in the team's gold on black where the photo was, WHO DAT in the strip's own white on dark grey. The helmet and
  the fleur-de-lis below (current marks) stay retail. Every swall3 use draws the same texture, so every poster changes.
* s17 corp_temp_adbanner01 and corp_temp_adbanner02 (candidate E's Superdome lab, 2026-09-29): the two sponsor atlases
  the fascia ribbons and the panels round the "Welcome to the Home of the Saints" board draw. Their defunct 2004 cells
  take u4's type panels under the same policy: MOTOROLA (the blue lower-bowl ribbon) -> NFL NETWORK, Reebok x2 -> PLAY
  60, ESPN THE MAGAZINE x2 -> ESPN, PLAYERS INC x2 -> NFLPA. ESPN, ESPN Radio, Gatorade, Riddell, Wilson and the NFC
  shield stay retail.
* s37 texscore01 and texscore02: the defunct 2004 cells under u4's approved sponsor policy (U4_MODERN_VENUES 10d):
  MOTOROLA -> NFL NETWORK, Reebok -> PLAY 60, ESPN VIDEOGAMES -> ESPN, ESPN THE MAGAZINE -> ESPN, the Visual Concepts
  credit -> NFL+, in u4's type panels. ESPN, ESPN.com, ESPN Radio, SportsCenter, Riddell, Wilson and Gatorade stay
  retail; u4's own Texans slots (the bull, the HOUSTON TEXANS panels) compose over these, as the table lays them.

The league-wide sweep for defunct 2004 brand logos (main, 2026-09-29; candidate E's textures with every table extra,
fb2's residual items and fb2's model fan art composed): the logo-only cells the OCR lists missed, in u4's table venues,
under the same policy (MOTOROLA -> NFL NETWORK, Reebok -> PLAY 60, ESPN VIDEOGAMES and ESPN THE MAGAZINE -> ESPN,
the Visual Concepts logo -> NFL+, PLAYERS INC -> NFLPA, and u4's league cloths' TEAM NFL -> PLAY 60, PLAY FOOTBALL ->
NFL FLAG, COACHES ASSOCIATION -> SUPER BOWL LXI). ESPN Radio (black ESPN over a dark bar), ESPN.com, SportsCenter,
the ESPN oval, Riddell, Wilson and Gatorade stay. SWEEP_CELLS lists them by venue and texture (the table's
SWEEP_RECTS); a turned cell is a vertical strip (-90, a quarter clockwise, as the scene lays it).

Only the cells are drawn; every other pixel is clear, so no retail pixel ships. Input: a retail dry-day export of s17,
s30 and s37 in u4's naming (<prefix>dd_stadium_t*_<key>.png, the user's own disc).

    python3 tools/nfl2k5_modern_venues_2026_st3_art.py RETAIL_EXPORT_DIR [--masters DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl2k5_modern_venues_2026_art as u4art  # noqa: E402  (st2's shared helpers, used as they are)

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras"
S = u4art.S

#: the table's rects (nfl2k5_modern_venues_2026.CLE_LAMBERT39_RECTS and the rest): what each PNG draws
CLE_HEADER = (0, 1, 128, 11)                 # lambert39's header interior (the rows the fascia strip draws)
CLE_CELLS = {"lambert39": {(1, 19, 127, 39): ("NFL NETWORK", "net")}}   # MOTOROLA, on the 2004 boards the kit replaces
NO_PHOTO, NO_STRIP = (0, 0, 128, 64), (0, 65, 128, 77)
HOU_CELLS = {
    "texscore01": {(183, 52, 256, 90): ("PLAY 60", "play60"),          # Reebok
                   (183, 90, 256, 131): ("ESPN", "espn"),              # ESPN VIDEOGAMES
                   (0, 155, 124, 194): ("NFL NETWORK", "net")},        # MOTOROLA
    "texscore02": {(168, 26, 254, 48): ("ESPN", "espn"),               # ESPN VIDEOGAMES
                   (163, 114, 254, 140): ("NFL+", "net"),              # the Visual Concepts credit
                   (163, 142, 254, 168): ("ESPN", "espn_dark"),        # ESPN THE MAGAZINE (the TEXANS slot below is u4's)
                   (4, 152, 162, 172): ("NFL NETWORK", "net")},        # MOTOROLA
}
#: the Superdome's sponsor atlases, by the table's rects (NO_ADBANNER01_RECTS, NO_ADBANNER02_RECTS)
NO_CELLS = {
    "corp_temp_adbanner01": {(0, 0, 64, 32): ("PLAY 60", "play60"),          # Reebok
                             (0, 32, 64, 64): ("ESPN", "espn_dark")},         # ESPN THE MAGAZINE
    "corp_temp_adbanner02": {(0, 0, 128, 31): ("NFL NETWORK", "net"),        # MOTOROLA (the blue lower-bowl ribbon)
                             (35, 32, 67, 64): ("NFLPA", "nflpa"),            # PLAYERS INC
                             (67, 32, 128, 64): ("PLAY 60", "play60"),        # Reebok
                             (65, 64, 128, 96): ("ESPN", "espn_dark"),        # ESPN THE MAGAZINE
                             (0, 96, 35, 128): ("NFLPA", "nflpa")},           # PLAYERS INC
}
#: the sweep's cells: {prefix: {key: {rect: (text, style[, turn])}}} (the table's SWEEP_RECTS)
SWEEP_CELLS = {
    "s02": {"ad03": {(4, 59, 125, 75): ("NFL NETWORK", "net")}},                                   # MOTOROLA
    "s04": {"panthers_score01": {(0, 17, 68, 31): ("ESPN", "espn"),                                # ESPN VIDEOGAMES
                                 (1, 70, 97, 87): ("NFL+", "plus"),                                # the Visual Concepts logo
                                 (99, 50, 127, 78): ("PLAY 60", "play60")},                        # Reebok
            "panthers_score02": {(110, 15, 128, 54): ("ESPN", "espn", -90),                        # ESPN VIDEOGAMES, upright
                                 (99, 96, 107, 126): ("ESPN", "espn_dark", -90)}},                 # ESPN THE MAGAZINE, upright
    "s09": {"sign02_sign04": {(2, 88, 110, 169): ("ESPN", "espn")}},                               # ESPN VIDEOGAMES
    "s27": {"lambert63": {(6, 64, 56, 95): ("NFL FLAG", "play60"),                                 # PLAY FOOTBALL
                          (82, 63, 114, 94): ("PLAY 60", "play60"),                                # TEAM NFL
                          (6, 95, 56, 128): ("NFLPA", "play60")},                                  # PLAYERS INC (navy on the grey)
            "lambert64": {(0, 32, 64, 64): ("PLAY 60", "play60")},                                 # Reebok
            "lambert65": {(0, 0, 64, 32): ("PLAY 60", "play60"),                                   # Reebok
                          (0, 32, 64, 64): ("ESPN", "espn_dark")}},                                # ESPN THE MAGAZINE
    "s28": {"ad_bb02": {(129, 0, 254, 25): ("NFL NETWORK", "net"),                                 # MOTOROLA
                        (194, 97, 230, 179): ("ESPN", "espn_dark", -90)}},                         # ESPN VIDEOGAMES, upright
    "s29": {"ad_bb01_LIGHT_ad_bb01": {(2, 132, 127, 193): ("ESPN", "espn_dark"),                   # ESPN THE MAGAZINE
                                      (4, 193, 126, 256): ("PLAY 60", "play60")},                  # Reebok
            "ad_bb02": {(4, 5, 124, 63): ("ESPN", "espn")},                                        # ESPN VIDEOGAMES
            "banner_home_team": {(1, 1, 65, 40): ("SUPER BOWL", "nflpa"),                          # COACHES ASSOCIATION
                                 (1, 40, 65, 62): ("LXI", "nflpa"),                                # (its second line)
                                 (66, 1, 127, 61): ("PLAY 60", "nflpa")}},                         # TEAM NFL
    "s30": {"LIGHT_jumbotronB1": {(0, 0, 92, 67): ("ESPN", "espn_dark"),                           # ESPN THE MAGAZINE
                                  (0, 70, 93, 128): ("PLAY 60", "play60")},                        # Reebok
            "jumbotronE1": {(0, 17, 64, 45): ("ESPN", "espn_dark")},                               # ESPN VIDEOGAMES
            "lambert40": {(1, 1, 31, 14): ("ESPN", "espn_dark"),                                   # ESPN THE MAGAZINE
                          (2, 15, 30, 30): ("ESPN", "espn"),                                       # ESPN VIDEOGAMES (Riddell stays)
                          (35, 33, 63, 63): ("NFLPA", "nflpa")}},                                  # PLAYERS INC
}
#: the sweep's PNG per texture (s27 lambert63 already carries st2's name rows, so its logos take their own file)
SWEEP_OUT = {p: {k: EXTRAS / (f"{p}_{k}_logos.png" if (p, k) == ("s27", "lambert63") else f"{p}_{k}.png") for k in keys}
             for p, keys in SWEEP_CELLS.items()}
OUT = {"s30": {"lambert39": EXTRAS / "s30_lambert39.png"},
       "s17": dict({"swall3": EXTRAS / "s17_swall3.png"}, **{k: EXTRAS / f"s17_{k}.png" for k in NO_CELLS}),
       "s37": {k: EXTRAS / f"s37_{k}.png" for k in HOU_CELLS}}
#: the Saints' colours (black and old gold), for the plain-type poster
SAINTS_BLACK, SAINTS_GOLD = (16, 24, 32), (211, 188, 141)
CLE_TEXT = "HUNTINGTON BANK FIELD"


def _line(draw, text, font_path, box, colour, fill_w=0.9, fill_h=0.8):
    """One line of type fitted to ``box`` (4x pixels) and centred in it."""
    x0, y0, x1, y1 = box
    font, (l, t, r, b) = u4art._fit(draw, text, font_path, (x1 - x0) * fill_w, (y1 - y0) * fill_h)
    draw.text((x0 + ((x1 - x0) - (r - l)) / 2 - l, y0 + ((y1 - y0) - (b - t)) / 2 - t), text, font=font,
              fill=tuple(colour) + (255,))


def author_cle(export_dir, masters=None):
    """s30 lambert39: the header interior, HUNTINGTON BANK FIELD in the header's own peach on its own dark ground."""
    retail = u4art._retail(export_dir, "s30", "lambert39")
    height, width = retail.shape[:2]
    x0, y0, x1, y1 = CLE_HEADER
    cell = retail[y0:y1, x0:x1, :3].reshape(-1, 3).astype(np.float64)
    lum = cell.mean(axis=1)
    ground = tuple(int(v) for v in np.median(cell[lum <= np.percentile(lum, 50)], axis=0))
    ink = tuple(int(v) for v in np.median(cell[lum >= np.percentile(lum, 92)], axis=0))
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    box = (x0 * S, y0 * S, x1 * S, y1 * S)
    draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=ground + (255,))
    _line(draw, CLE_TEXT, u4art.FONT_COND, box, ink, 0.92, 0.72)
    # the MOTOROLA panel below it (drawn by the 2004 boards when the board kit is off) as u4's NFL NETWORK panel
    return u4art.author_cells("s30", CLE_CELLS, OUT["s30"], export_dir, masters, sheets={"lambert39": sheet})


def author_no(export_dir, masters=None):
    """s17 swall3: SAINTS in gold on black where the players photo was, WHO DAT in the strip's own white on dark grey."""
    retail = u4art._retail(export_dir, "s17", "swall3")
    height, width = retail.shape[:2]
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    x0, y0, x1, y1 = (v * S for v in NO_PHOTO)
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=SAINTS_BLACK + (255,))
    inset = 3 * S
    draw.rectangle((x0 + inset, y0 + inset, x1 - 1 - inset, y1 - 1 - inset), outline=SAINTS_GOLD + (255,), width=S)
    _line(draw, "SAINTS", u4art.FONT_BLACK, (x0 + inset, y0 + inset, x1 - inset, y1 - inset), SAINTS_GOLD, 0.84, 0.62)
    sx0, sy0, sx1, sy1 = NO_STRIP
    strip = retail[sy0:sy1, sx0:sx1, :3].reshape(-1, 3).astype(np.float64)
    lum = strip.mean(axis=1)
    ground = tuple(int(v) for v in np.median(strip[lum <= np.percentile(lum, 40)], axis=0))
    ink = tuple(int(v) for v in np.median(strip[lum >= np.percentile(lum, 90)], axis=0))
    box = (sx0 * S, sy0 * S, sx1 * S, sy1 * S)
    draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=ground + (255,))
    _line(draw, "WHO DAT", u4art.FONT_BLACK, box, ink, 0.8, 0.78)
    return {"swall3": u4art._save(sheet, width, height, OUT["s17"]["swall3"], masters, "s17_swall3_4x.png")}


def author_no_sponsors(export_dir, masters=None):
    """s17 corp_temp_adbanner01 and 02: the defunct cells as u4's type panels (st2's author_cells)."""
    return u4art.author_cells("s17", NO_CELLS, OUT["s17"], export_dir, masters)


def author_sweep(export_dir, masters=None):
    """The sweep's cells as u4's type panels (st2's author_cells), one PNG per texture."""
    digests = {}
    for prefix, cells in SWEEP_CELLS.items():
        for key, digest in u4art.author_cells(prefix, cells, SWEEP_OUT[prefix], export_dir, masters).items():
            digests[f"{prefix} {key}"] = digest
    return digests


def author_hou(export_dir, masters=None):
    """s37 texscore01 and texscore02: the defunct cells as u4's type panels (st2's author_cells)."""
    return u4art.author_cells("s37", HOU_CELLS, OUT["s37"], export_dir, masters)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", help="a retail export folder of u4's table venues in u4 naming (<prefix>dd_stadium_t*_<key>.png)")
    ap.add_argument("--masters", help="where to keep the 4x masters (outside the repository)")
    a = ap.parse_args(argv)
    digests = {}
    digests.update({f"s30 {k}": v for k, v in author_cle(a.export, a.masters).items()})
    digests.update({f"s17 {k}": v for k, v in author_no(a.export, a.masters).items()})
    digests.update({f"s17 {k}": v for k, v in author_no_sponsors(a.export, a.masters).items()})
    digests.update({f"s37 {k}": v for k, v in author_hou(a.export, a.masters).items()})
    digests.update(author_sweep(a.export, a.masters))
    for key, digest in digests.items():
        print(key, digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

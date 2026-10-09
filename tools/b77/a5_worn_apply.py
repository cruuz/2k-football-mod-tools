#!/usr/bin/env python3
"""b77 / a5: write what each side wore in its game (and the sourced kit overrides) into data/nfl2k5_moment_uniform_eras.json.

Noah (10/8 evening): in the 25th Anniversary mode the Brady Super Bowl Patriots need their old jerseys, the Giants grey pants,
"uniforms selected for 2005-2020 with variations for teams so these scenarios make more sense". a1x had colours from text
searches only ("no photo checked"). a5 read the dated per-game uniform graphics of the Gridiron Uniform Database (GUD:
gridiron-uniforms.com, team-season pages, one graphic per team and game: jersey, pants, socks, helmet, front and back) for all
26 authored moments, and the SB / playoff / club texts that four Haiku 5.5 shards and the lead found. The result:

  * `a5_worn`: per moment side, the colours as worn (from the GUD graphic, viewed by the lead on 2026-10-08), the designated home
    team of the game, and the sources;
  * `overrides` (rule R0): the sides where the closest kit in this build is neither what R1-R4 give nor modern by default;
  * `a5_fit`: per side, how close the selected kit is to the worn uniform ("exact", "close", or "gap" with the id of the era kit
    plan item in data/nfl2k5_moment_era_kit_plan.json that would close it).

Run once (idempotent): python3 tools/b77/a5_worn_apply.py [--root DIR]. Then `python3 tools/b77/a1_uniforms.py compile`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ERAS = "data/nfl2k5_moment_uniform_eras.json"
GUD = "http://www.gridiron-uniforms.com/GUD/controller/controller.php?action=teams-season&team_id={t}&year={y}"
WIKI = "https://en.wikipedia.org/wiki/"

# (moment, side): team id of the GUD page, graphic file, then the worn facts.
# jersey / pants / socks / helmet are read from the GUD graphic; "text" lists the SB texts (read by the shards, not re-read).
W = {}


def w(moment, side, gud_team, graphic, designated_home, jersey, pants, socks, helmet, note="", text=(), confidence="high"):
    W[(moment, side)] = dict(gud_team=gud_team, graphic=graphic, designated_home=designated_home, jersey=jersey, pants=pants,
                             socks=socks, helmet=helmet, note=note, text=list(text), confidence=confidence)


w("the_miss", "away", "ATL", "th/1998_ATL_1.png", False, "white, red numerals", "silver with a red stripe", "red", "black",
  "road set, Metrodome", ["Game: " + WIKI + "1998_NFC_Championship_Game (Atlanta the visitor)"])
w("the_miss", "home", "MIN", "th/1998_MIN_2.png", True, "purple, white numerals trimmed gold", "white, purple-gold stripe", "purple",
  "purple, white horns", "home set")
w("helmet_catch", "away", "NYG", "2007_NYG_3.png", False, "white, red numerals", "gray", "red", "blue",
  "road white with gray pants, Super Bowl patch", ["Wikipedia Super Bowl XLII: 'the Giants wore their road white uniforms with grey pants'"])
w("helmet_catch", "home", "NE", "2007_NE_3.png", True, "navy blue", "silver", "navy", "silver",
  "home set, Super Bowl patch", ["Wikipedia Super Bowl XLII: 'the Patriots elected to wear their home navy uniforms with silver pants'; designated home team"])
w("toe_tap", "away", "PIT", "2008_PIT_2.png", False, "white, black numerals", "gold", "black", "black",
  "road white (the black home set was not available)", ["AP 2009-01-21: 'The Pittsburgh Steelers will wear their white road uniforms against Arizona in the Super Bowl'"])
w("toe_tap", "home", "ARZ", "2008_ARZ_4.png", True, "red, white numerals", "white", "red", "white",
  "home red; text sources say red pants but the GUD graphic shows white pants (graphic kept)",
  ["AP 2009-01-21: 'The Cardinals, as the home team, chose to wear their red home jerseys'"], "high")
w("manningham", "away", "NYG", "2011_NYG_1b.png", False, "white, red numerals", "gray", "red", "blue",
  "road white with gray pants (the same combination as Super Bowl XLII)",
  ["Boston.com 2012-01-23: the Giants 'tweeted that they would wear their road white jerseys with gray pants'"])
w("manningham", "home", "NE", "2011_NE_2a.png", True, "navy blue", "silver (text calls it gray)", "navy", "silver",
  "home set", ["NFL.com: 'The Patriots chose their home blue uniforms'; Wikipedia: designated home team"], "high")
w("comeback_28_3", "away", "NE", "2016_NE_1a.png", False, "white, navy numerals", "navy", "navy and white striped", "silver",
  "road whites with navy pants, Super Bowl LI patch",
  ["NFL.com 2017-01-27: 'The Patriots will wear their white jerseys'; Wikipedia: Patriots the designated away team"])
w("comeback_28_3", "home", "ATL", "2016_ATL_2a.png", True, "red, white numerals", "white", "red", "black",
  "home red as the designated home team", ["USA Today Falcons Wire 2017-01-24: Falcons 'will wear home red unis'"])
w("fourth_and_18", "away", "MIN", "th/2022_MIN_B.png", False, "white, purple numerals", "purple", "purple", "purple",
  "road white over purple pants", ["Bets Dressed 2022-11-13: 'Purple pants confirmed for the Vikings'"], "high")
w("fourth_and_18", "home", "BUF", "th/2022_BUF_D3.png", True, "royal blue, white numerals", "white", "blue", "white",
  "home blue over white pants, white helmet")
w("music_city_miracle", "away", "BUF", "th/1999_BUF_1.png", False, "white, blue numerals", "white, red-blue stripe", "red", "red",
  "road set")
w("music_city_miracle", "home", "TEN", "th/1999_TEN_2.png", True, "navy, light blue shoulders", "white", "navy", "white",
  "home navy set, Adelphia Coliseum")
w("tuck_rule", "away", "OAK", "th/2001_OAK_1.png", False, "white, silver numerals", "silver", "white", "silver",
  "the Raiders wore their road whites with silver pants (not black)")
w("tuck_rule", "home", "NE", "th/2001_NE_2.png", True, "navy blue", "silver", "navy", "silver", "home set, Foxboro snow game")
w("super_bowl_shootout", "away", "CAR", "2003_CAR_2.png", False, "white, blue numerals", "white", "blue", "silver",
  "road whites with white pants", ["Wikipedia Super Bowl XXXVIII: 'road white uniforms with white pants'"])
w("super_bowl_shootout", "home", "NE", "2003_NE_3.png", True, "navy blue", "silver", "navy", "silver", "home set",
  ["Wikipedia Super Bowl XXXVIII: 'home navy uniforms with silver pants'; 'the Patriots, as the designated home team'"])
w("ambush", "away", "NO", "2009_NO_2.png", False, "white, black numerals", "old gold", "black", "gold",
  "road white over old gold pants", ["Wikipedia Super Bowl XLIV: 'the Saints wore their road white uniforms with old gold pants'"])
w("ambush", "home", "IND", "2009_IND_3.png", True, "royal blue, white numerals", "white", "blue", "white",
  "home blue over white pants", ["Wikipedia Super Bowl XLIV: 'the Colts elected to wear their home blue uniforms with white pants'"])
w("new_meadowlands_miracle", "away", "PHI", "th/2010_PHI_2.png", False, "white, midnight green numerals", "midnight green",
  "black", "midnight green", "white jersey over midnight green pants (the Giants were in blue)")
w("new_meadowlands_miracle", "home", "NYG", "th/2010_NYG_2.png", True, "royal blue, white numerals", "gray", "blue", "blue",
  "home blue over gray pants")
w("beast_quake", "away", "NO", "th/2010_NO_3.png", False, "white, black numerals trimmed gold", "black", "black", "gold",
  "road white over black pants")
w("beast_quake", "home", "SEA", "th/2010_SEA_2.png", True, "Seahawks blue (steel blue), white numerals", "Seahawks blue", "navy",
  "Seahawks blue", "the 2002-2011 home set")
w("catch_three", "away", "NO", "th/2011_NO_1.png", False, "white, black numerals trimmed gold", "old gold", "black", "gold",
  "road white over old gold pants")
w("catch_three", "home", "SF", "th/2011_SF_2.png", True, "red, white numerals", "gold", "red", "gold", "home red over gold pants")
w("mile_high_miracle", "away", "BAL", "th/2012_BAL_A.png", False, "white, purple numerals", "black", "black", "black",
  "road white over black pants")
w("mile_high_miracle", "home", "DEN", "th/2012_DEN_2.png", True, "orange, white numerals", "white", "navy", "navy",
  "home orange over white pants (the 2012 Nike set)")
w("goal_line_stand", "away", "BAL", "2012_BAL_S.png", False, "white, purple numerals", "black", "black", "black",
  "road white over black pants, Super Bowl XLVII patch on the right chest",
  ["Wikipedia Super Bowl XLVII: 'The Ravens wore white jerseys as they did in Super Bowl XXXV, but with black-colored pants'"])
w("goal_line_stand", "home", "SF", "2012_SF_S.png", True, "red, white numerals", "gold", "red", "gold",
  "red home jerseys over gold pants", ["Wikipedia Super Bowl XLVII: 'San Francisco elected to wear their red jerseys'; designated home team"])
w("dez_caught_it", "away", "DAL", "th/2014_DAL_1.png", False, "white, navy numerals", "silver-blue (metallic)", "navy", "silver",
  "road white over silver-blue pants")
w("dez_caught_it", "home", "GB", "th/2014_GB_2.png", True, "green, white numerals", "gold", "green", "gold", "home green over gold pants")
w("butler_goal_line", "away", "NE", "2014_NE_3.png", False, "white, navy numerals", "navy", "navy and white striped", "silver",
  "road whites over navy pants",
  ["Patriots.com: 'As technically the visiting team for Super Bowl XLIX the Patriots will be wearing their white road jerseys'"])
w("butler_goal_line", "home", "SEA", "2014_SEA_7.png", True, "college navy, neon green numerals", "navy", "navy", "navy",
  "all navy home set", ["Wikipedia Super Bowl XLIX: the Seahawks 'elected to wear their college navy home jerseys with navy pants'"])
w("miracle_in_motown", "away", "GB", "th/2015_GB_1.png", False, "white, green numerals", "gold", "green", "gold", "road white over gold pants")
w("miracle_in_motown", "home", "DET", "th/2015_DET_2.png", True, "Honolulu blue", "silver", "white", "silver",
  "home Honolulu blue over silver pants (the 2009-2016 set)")
w("minneapolis_miracle", "away", "NO", "th/2017_NO_B.png", False, "white, black numerals", "black", "black", "gold",
  "road white over black pants")
w("minneapolis_miracle", "home", "MIN", "th/2017_MIN_C.png", True, "purple, white numerals", "white, purple stripe", "purple",
  "purple", "home purple over white pants")
w("philly_special", "away", "PHI", "2017_PHI_D2.png", False, "midnight green, white numerals", "white", "black and white",
  "midnight green", "the Eagles wore GREEN as the visitor (the Patriots took white)",
  ["Wikipedia Super Bowl LII: 'The Eagles therefore wore their standard home uniform of midnight green jerseys with white pants'"])
w("philly_special", "home", "NE", "2017_NE_A2.png", True, "white, navy numerals", "navy", "navy and white striped", "silver",
  "the designated HOME team chose its road whites over navy pants",
  ["NFL.com: 'As the home team in Super Bowl LII, New England earned its pick of jersey colors'",
   "Wikipedia Super Bowl LII: 'the Patriots chose to wear their road white jerseys with navy blue pants'"])
w("jet_chip_wasp", "away", "SF", "2019_SF_A2.png", False, "white, red numerals", "gold", "red", "gold",
  "standard road set", ["NFL.com 2020-01-20: 'The Niners will don white jerseys with gold pants'"])
w("jet_chip_wasp", "home", "KC", "2019_KC_D3.png", True, "red, white numerals", "white", "red and yellow striped", "red",
  "home red", ["NFL.com: 'The Chiefs, the designated home team, will wear their dark jerseys'"])
w("thirteen_seconds", "away", "BUF", "th/2021_BUF_C.png", False, "white, blue numerals", "white, red-blue stripe", "white", "white",
  "all white with the white helmet", ["Buffalo Rumblings preview: 'white jerseys with white pants and white helmet' (search excerpt)"], "medium")
w("thirteen_seconds", "home", "KC", "hr/2021_KC_DDDD.gif", True, "red, white numerals", "white", "red", "red", "home red over white pants")
w("donald_fourth_down", "away", "LAR", "2021_LAR_D2.png", False, "white, royal numerals (modern throwback)", "yellow", "royal",
  "royal, gold horns", "the white 'modern throwback' with yellow pants (the 1999 road look)",
  ["Fox LA: 'the NFC champs will wear the white \"modern throwback\" jerseys to go with their yellow \"sol\" pants'"])
w("donald_fourth_down", "home", "CIN", "2021_CIN_I2.png", True, "black, orange stripes on the shoulders", "white with orange tiger stripes",
  "orange", "orange, black tiger stripes", "home black as the designated home team, Super Bowl patch on the left chest",
  ["NFL.com: 'As the designated home team in Super Bowl LVI, the Bengals had the first choice of uniform'"])
w("comeback_33", "away", "IND", "th/2022_IND_A2.png", False, "white, royal numerals", "white", "white", "white", "road whites",
  ["Bets Dressed 2022-12-17: 'The icy white Colts are the runaway choice'"], "medium")
w("comeback_33", "home", "MIN", "hr/2022_MIN_CC.gif", True, "purple, white numerals", "white", "purple", "purple", "home purple over white pants")
w("overtime_in_vegas", "away", "SF", "hr/2023_SF_AA2.gif", False, "white, red numerals", "gold", "red", "gold", "road set",
  ["Wikipedia Super Bowl LVIII: 'The 49ers wore their white away jerseys with gold pants'"])
w("overtime_in_vegas", "home", "KC", "2023_KC_H3.png", True, "red, white numerals", "white", "red and yellow striped", "red", "home red",
  ["Wikipedia Super Bowl LVIII: 'the Chiefs chose to wear their red home jerseys with white pants'"])
w("unc_bowl", "away", "PIT", "th/2025_PIT_D.png", False, "black, gold numerals", "gold", "black", "black",
  "standard home set worn as the road team",
  ["SportsLogos 2025-10-14: 'Pittsburgh will wear its standard home uniform of black helmets, black jerseys and gold pants'"])
w("unc_bowl", "home", "CIN", "th/2025_CIN_B.png", True, "white (White Bengal), black numerals outlined orange",
  "white, black stripes", "white", "white, black tiger stripes", "all-white White Bengal set",
  ["bengals.com 2025-10-13: 'Jersey: White', 'Pants: White w/ Black Stripes'"])


# URLs of the text sources, aligned with each entry's `text` list (the quotes were read by the Haiku shards or the lead's searches;
# the GUD graphic, not the text, is the basis of the colours).
SB = lambda n: WIKI + "Super_Bowl_" + n
TEXT_URLS = {
    ("the_miss", "away"): [WIKI + "1998_NFC_Championship_Game"],
    ("helmet_catch", "away"): [SB("XLII")],
    ("helmet_catch", "home"): [SB("XLII")],
    ("toe_tap", "away"): ["https://archives-new.honoluluadvertiser.com/article/2009/Jan/21/br/hawaii90121042.html"],
    ("toe_tap", "home"): ["https://archives-new.honoluluadvertiser.com/article/2009/Jan/21/br/hawaii90121042.html"],
    ("manningham", "away"): ["https://www.boston.com/sports/new-england-patriots/2012/01/23/patriots_opt_fo/?amp=1"],
    ("manningham", "home"): ["https://www.nfl.com/news/patriots-giants-super-bowl-rematch-will-feature-same-uniforms-09000d5d826426b1"],
    ("comeback_28_3", "away"): ["https://www.nfl.com/news/pats-wearing-white-in-super-bowl-will-definitely-win-0ap3000000778558"],
    ("comeback_28_3", "home"): ["https://web.archive.org/web/20170126094124/http://thefalconswire.usatoday.com/2017/01/24/falcons-choose-to-wear-red-jerseys-for-super-bowl-li-vs-patriots/"],
    ("fourth_and_18", "away"): ["https://betsdressed.beehiiv.com/p/bets-dressed-week-10-uniform-matchups-picks"],
    ("super_bowl_shootout", "away"): [SB("XXXVIII")],
    ("super_bowl_shootout", "home"): [SB("XXXVIII")],
    ("ambush", "away"): [SB("XLIV")],
    ("ambush", "home"): [SB("XLIV")],
    ("goal_line_stand", "away"): [SB("XLVII")],
    ("goal_line_stand", "home"): [SB("XLVII")],
    ("butler_goal_line", "away"): ["https://www.patriots.com/news/ask-pfw-on-to-the-super-bowl-221886-x2229"],
    ("butler_goal_line", "home"): [SB("XLIX")],
    ("philly_special", "away"): [SB("LII")],
    ("philly_special", "home"): ["https://www.nfl.com/news/new-england-patriots-to-wear-white-in-super-bowl-lii-0ap3000000909752", SB("LII")],
    ("jet_chip_wasp", "away"): ["https://www.nfl.com/news/49ers-to-wear-white-jerseys-gold-pants-at-super-bowl-0ap3000001098078"],
    ("jet_chip_wasp", "home"): ["https://www.nfl.com/news/49ers-to-wear-white-jerseys-gold-pants-at-super-bowl-0ap3000001098078"],
    ("thirteen_seconds", "away"): ["https://www.buffalorumblings.com/2022/1/23/22896375/buffalo-bills-vs-kansas-city-chiefs-broadcast-info-announcers-streaming-radio-television-josh-allen"],
    ("donald_fourth_down", "away"): ["https://foxla.com/sports/super-bowl-lvi-la-rams-to-wear-popular-throwback-unis-for-big-game"],
    ("donald_fourth_down", "home"): ["https://www.nfl.com/news/bengals-to-wear-black-home-uniforms-in-super-bowl-lvi-vs-rams"],
    ("comeback_33", "away"): ["https://betsdressed.beehiiv.com/p/bets-dressed-week-15-saturday-special-edition"],
    ("overtime_in_vegas", "away"): [SB("LVIII")],
    ("overtime_in_vegas", "home"): [SB("LVIII")],
    ("unc_bowl", "away"): ["https://news.sportslogos.net/2025/10/14/cincinnati-bengals-to-wear-white-bengal-alternate-uniforms-on-thursday-night-football/football/"],
    ("unc_bowl", "home"): ["https://www.bengals.com/news/bengals-uniform-combination-week-7-2025-steelers-white-bengal"],
}

# R0: the closest kit in this build, where R1-R4 do not give it. kit: "retail_current" = the retail 2004 look on the spare style.
O = [
    dict(moment="helmet_catch", side="away", kit="retail_current",
         reason="worn: white jersey over GRAY pants; the retail 2004 Giants road kit is white over gray (style 0 has white pants)"),
    dict(moment="manningham", side="away", kit="retail_current",
         reason="worn: white jersey over GRAY pants; the retail 2004 Giants road kit is white over gray (style 0 has white pants)"),
    dict(moment="toe_tap", side="home", kit="retail_current",
         reason="worn: red jersey, white pants, white helmet; the retail 2004 Cardinals home kit is red over white with a white helmet (style 0 has maroon pants)"),
    dict(moment="miracle_in_motown", side="home", kit="retail_current",
         reason="worn: Honolulu blue over SILVER pants (the 2009-2016 set, the 2003 design); the retail 2004 Lions kit is that look (style 0 has blue pants)"),
    dict(moment="new_meadowlands_miracle", side="away", kit=10,
         reason="worn: white jersey over midnight green pants; Eagles style 10 is the u3d alternate 'white jersey with midnight green pants' (both kits)"),
    dict(moment="donald_fourth_down", side="away", kit=2,
         reason="worn: the white modern throwback over yellow pants with royal helmet and gold horns, the 1999 road look; Rams style 2 (1998-1999) is that road kit (style 0 road has royal pants)"),
]

# fit of the selected kit (decision in a1_uniforms) against the worn uniform. "gap" ids are items of the era kit plan.
FIT = {
    ("the_miss", "away"): ("close", "retail 1998-2003 road set (white, silver pants, red socks)"),
    ("the_miss", "home"): ("exact", "retail 2004 look is the 1996-2005 design: purple, white pants"),
    ("helmet_catch", "away"): ("close", "white over gray yes; 2005 numerals and trim differ slightly from the 2000-04 retail road"),
    ("helmet_catch", "home"): ("exact", "navy over silver, silver helmet"),
    ("toe_tap", "away"): ("exact", "style 0 road: white over gold, black helmet"),
    ("toe_tap", "home"): ("close", "red, white pants, white helmet yes; numerals and trim are the 1996-2004 design"),
    ("manningham", "away"): ("close", "white over gray yes; 2005 numerals and trim differ slightly"),
    ("manningham", "home"): ("exact", "navy over silver, silver helmet"),
    ("comeback_28_3", "away"): ("close", "white over navy pants yes (retail road); Nike cut and 2012+ details differ"),
    ("comeback_28_3", "home"): ("close", "red over white pants, black helmet; retail 2003-2019 design"),
    ("fourth_and_18", "away"): ("exact", "style 0 road: white over purple"),
    ("fourth_and_18", "home"): ("exact", "style 0 home: blue over white"),
    ("music_city_miracle", "away"): ("exact", "retail 1987-2002 set"),
    ("music_city_miracle", "home"): ("exact", "retail 2004 look is the 1999 design: navy, white pants"),
    ("tuck_rule", "away"): ("exact", "style 0 road: white over silver, silver helmet"),
    ("tuck_rule", "home"): ("exact", "navy over silver"),
    ("super_bowl_shootout", "away"): ("close", "white over white, silver helmet (style 0 road)"),
    ("super_bowl_shootout", "home"): ("exact", "navy over silver"),
    ("ambush", "away"): ("gap", "G2: white over OLD GOLD pants; style 0 road has black pants"),
    ("ambush", "home"): ("exact", "style 0 home: royal over white"),
    ("new_meadowlands_miracle", "away"): ("exact", "Eagles style 10: white over midnight green"),
    ("new_meadowlands_miracle", "home"): ("exact", "retail 2004 look: blue over gray"),
    ("beast_quake", "away"): ("exact", "style 0 road: white over black"),
    ("beast_quake", "home"): ("exact", "retail 2004 look is the 2002-2011 Seahawks blue set"),
    ("catch_three", "away"): ("gap", "G2: white over OLD GOLD pants; style 0 road has black pants"),
    ("catch_three", "home"): ("exact", "style 0 home: red over gold"),
    ("mile_high_miracle", "away"): ("gap", "G3: white over BLACK pants; the retail road kit has white pants, style 0 purple"),
    ("mile_high_miracle", "home"): ("close", "style 0: orange over white (2012 Nike set vs the 2024 redesign details)"),
    ("goal_line_stand", "away"): ("gap", "G3: white over BLACK pants; the retail road kit has white pants, style 0 purple"),
    ("goal_line_stand", "home"): ("exact", "style 0 home: red over gold"),
    ("dez_caught_it", "away"): ("close", "style 0 road: white over silver (worn pants are silver-blue)"),
    ("dez_caught_it", "home"): ("exact", "style 0 home: green over gold"),
    ("butler_goal_line", "away"): ("close", "white over navy pants yes (retail road); Nike cut and 2012+ details differ"),
    ("butler_goal_line", "home"): ("close", "style 0: navy over navy (the 2026 set is the 2012 family)"),
    ("miracle_in_motown", "away"): ("exact", "style 0 road: white over gold"),
    ("miracle_in_motown", "home"): ("close", "retail 2004 look: Honolulu blue over silver"),
    ("minneapolis_miracle", "away"): ("exact", "style 0 road: white over black"),
    ("minneapolis_miracle", "home"): ("exact", "style 0 home: purple over white"),
    ("philly_special", "away"): ("gap", "G1b: worn midnight GREEN; the engine gives the away side its white kit"),
    ("philly_special", "home"): ("gap", "G1: worn WHITE over navy pants; the engine gives the home side its navy kit"),
    ("jet_chip_wasp", "away"): ("exact", "style 0 road: white over gold"),
    ("jet_chip_wasp", "home"): ("exact", "style 0 home: red over white"),
    ("thirteen_seconds", "away"): ("close", "style 0 road: white over white (worn white helmet)"),
    ("thirteen_seconds", "home"): ("exact", "style 0 home: red over white"),
    ("donald_fourth_down", "away"): ("close", "Rams style 2 (1999 road): white, gold pants, royal helmet; 2021 marks differ"),
    ("donald_fourth_down", "home"): ("exact", "style 0 home: black over white with tiger stripes"),
    ("comeback_33", "away"): ("exact", "style 0 road: white"),
    ("comeback_33", "home"): ("exact", "style 0 home: purple over white"),
    ("overtime_in_vegas", "away"): ("exact", "style 0 road: white over gold"),
    ("overtime_in_vegas", "home"): ("exact", "style 0 home: red over white"),
    ("unc_bowl", "away"): ("gap", "G4: worn BLACK over gold (the Bengals took white); the engine gives the away side its white kit"),
    ("unc_bowl", "home"): ("gap", "G4: worn all-white White Bengal; style 0 home is black. Bengals style 5 (White Bengal, built) is NOT selected: the visiting Steelers would be white too until G4 gives them a black away kit"),
}


def build(eras):
    sides = {(s["moment"], s["side"]): s for s in eras["sides"]}
    assert set(W) == set(sides) == set(FIT), "worn / fit / sides differ"
    worn = []
    for (moment, side), d in sorted(W.items(), key=lambda kv: [s["moment"] for s in eras["sides"]].index(kv[0][0]) * 2 + (kv[0][1] == "home")):
        s = sides[(moment, side)]
        selector, season = s["team_key"].rsplit("_", 1)
        worn.append(dict(
            moment=moment, side=side, team_key=s["team_key"], designated_home=d["designated_home"],
            jersey=d["jersey"], pants=d["pants"], socks=d["socks"], helmet=d["helmet"], note=d["note"],
            basis="Gridiron Uniform Database per-game graphic (jersey, pants, socks, helmet, front and back) viewed by the lead on 2026-10-08",
            gud_page=GUD.format(t=d["gud_team"], y=season), gud_graphic="https://www.gridiron-uniforms.com/GUD/images/singles/" + d["graphic"],
            text_sources=[dict(url=u, quote=q) for u, q in zip(TEXT_URLS.get((moment, side), []), d["text"])],
            confidence=d["confidence"]))
        assert len(TEXT_URLS.get((moment, side), [])) == len(d["text"]), (moment, side)
    fit = []
    for (moment, side) in [(s["moment"], s["side"]) for s in eras["sides"]]:
        kind, why = FIT[(moment, side)]
        entry = dict(moment=moment, side=side, fit=kind, why=why)
        if kind == "gap":
            entry["gap"] = why.split(":")[0]
        fit.append(entry)
    overrides = []
    for o in O:
        sources = [x for x in worn if x["moment"] == o["moment"] and x["side"] == o["side"]][0]
        overrides.append(dict(o, sources=[sources["gud_page"]] + [t["url"] for t in sources["text_sources"]]))
    return worn, overrides, fit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    path = args.root / ERAS
    eras = json.loads(path.read_text(encoding="utf-8"))
    worn, overrides, fit = build(eras)
    eras["a5_worn"], eras["overrides"], eras["a5_fit"] = worn, overrides, fit
    eras["rule"]["text"] = (
        "Per team-season: R0 a sourced per-side override (the `overrides` block, from what the team wore in the game); R1 style 0 "
        "(the 2026 kit) when the season is on or after design_2026_since; R2 a retail period set when a retail era row contains the "
        "season; R3 the retail 2004 kit ('retail_current') when the season is inside the 2004 look's years for that kit (home or "
        "road), whatever the Reebok or Nike template (a5, Noah 10/8); R4 otherwise style 0 (modern by default).")
    eras["a5"] = dict(
        compiled="2026-10-08", by="a5 (Sonnet 5.5): GUD per-game graphics viewed by the lead, SB texts from four Haiku 5.5 shards",
        note="a1x's worn_in_game texts are kept untouched; a5_worn supersedes them (graphics, not text searches). Designated home equals "
             "the moment's home side in all 26 games.")
    path.write_text(json.dumps(eras, indent=2) + "\n", encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

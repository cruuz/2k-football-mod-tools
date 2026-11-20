#!/usr/bin/env python3
"""b772-i3: write (or check) the reviewed modern-art PNG catalog the 2K5 release gate pins.

  python3 tools/b77/modern_art_png_catalog.py [--repo .] [--check]

The release gate (packaging/check_2k5_mod_studio_release.py) forbids every .png except exact reviewed files. The 2026
coaches (co1/co2), the 2026 fans (fr1) and the 2025-26 officials (rf1) ship authored PNG art under three data folders.
This tool lists every .png the release allowlist declares under those folders, records path, byte size, SHA-256 and
PNG dimensions, and writes packaging/nfl2k5_modern_art_pngs.json. It then prints the catalog's own SHA-256, which the
checker pins as MODERN_ART_PNG_CATALOG_SHA256 (change both together).

A file goes into the catalog only after it was reviewed as authored art: no photograph or crop of one, and no
retail-extracted pixels. Files that failed that review are listed in NOT_AUTHORED below with the reason; they stay out
of the catalog, so the release gate keeps refusing them until they are replaced or the decision changes. Each entry's
SHA-256 is pinned here, so a replaced file is reviewed again instead of inheriting the old verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

CATALOG = "packaging/nfl2k5_modern_art_pngs.json"
SCHEMA = "nfl2k5_modern_art_pngs/v1"
FOLDERS = ("data/nfl2k5_modern_coaches/", "data/nfl2k5_modern_fans/", "data/nfl2k5_modern_officials/",
           "data/nfl2k5_super_bowl_walls/", "data/nfl2k5_era_ball/", "data/nfl2k5_modern_venues_2026/numbers/",
           "data/nfl2k5_super_bowl_fields/",
           "data/nfl2k5_hair_styles/art/",  # b775-hs1
           "data/nfl2k5_rookie_faces/",  # b778-rh1: the authored rookie face bank atlases
           "data/nfl2k5_real_portraits/",  # b779-pt1: official-headshot Player Card portraits (game format)
           "data/nfl2k5_classic_teams/",  # b778-ss1: the Seamen card, field and face art
           "data/nfl2k5_alien_prospect/",  # b778-ee1: the gray alien portrait and face textures
           "data/trophy_room_logo/",  # b778-pg2: the authored TROPHY ROOM emblem
           "data/nfl2k5_glyph_fixes_2026/",  # b776-fn2 (int2)
           "data/nfl2k5_relief_2026_b81u/",  # b81-retail-free-art: the 2026 relief as differences (no retail base)
           "data/nfl2k5_glyph_fixes_2026_b81u/",  # b81-retail-free-art: the b81u digits and name strips drawn new or
                                                  # edited from the project's own glyph art
           "data/nfl2k5_scorebug_digit_glyphs.png")  # b780: the scorebug digit sheet's glyph layer (one file)
CLASSIFICATION = ("b779 pt1's real portrait atlases are the official NFL.com / ESPN headshot photographs of the created real free agents, cropped and reduced to the game's 128 x 128 P8 portrait format (Noah 2026-10-28: the card shows the real picture, like the NFL roster does); the original photo files never ship, only these game-format portraits. "
                  "b778 rh1/rh2's rookie face bank atlases are generated fictional draft headshots (Codex image_gen), "
                  "reviewed face by face; no photograph or retail-extracted pixels. "
                  "b778 ss1's Seamen card, field and face art is drawn from the video references and the authored kit. "
                  "b778 ee1/ee2's gray alien portrait and face textures are authored from a generated headshot. "
                  "b778 pg2's TROPHY ROOM emblem is authored (gold cup, navy banner, white type). "
                  "Reviewed authored 2026/2025-26 art for the modern coaches (co1/co2), the modern fans (fr1) and the "
                  "modern officials (rf1), plus fa1 authored block yard numerals (fn1): painted textures, team marks and lettering at the native slot size. Coach "
                  "faces are painted from the official headshots onto the 2004 head layout (Noah 2026-10-12: authored "
                  "likeness textures ship, the reference photos never do). Coach Matchup pictures are supplied by the "
                  "external SOFTDRINK league project; no portrait PNG ships in these folders. The accessories atlas "
                  "ships only its authored headset half (headset.png); the shoe and clipboard come from the user's disc. "
                  "The Super Bowl event walls (me1, redesigned "
                  "by sb2) are drawn by tools/nfl2k5_super_bowl_walls_art.py from type, shapes and team colours with "
                  "an original event plate (no Super Bowl or broadcaster logo is copied); each surface's .marks.png "
                  "layer holds its authored slot marks, including the mod's own 2026 team logos "
                  "(data/nfl2k5_scorebug_assets/logos, as the modern fans use them) at slot size. The NFL shield is "
                  "added at build time (the mod's 2008 field shield, or the period shield from the user's disc), and "
                  "areas a surface keeps from the venue are transparent in the PNG and filled from the user's disc. "
                  "The modern game ball (me1) is drawn by tools/nfl2k5_era_ball_art.py: leather, laces, lettering "
                  "and a generic shield; its plain leather is taken from the user's disc ball at build time. "
                  "b77 cm1 repainted eighteen coach heads (WAS, DAL, CIN, CAR, GB, TEN, LAR, SF, MIN, NYJ, TB, MIA, DET, CLE, "
                  "NE, ATL, JAX, NYG) in 3D on the head mesh: one painted skin tone, painted hair and facial hair, and only "
                  "the fine feature detail of co2's authored faces. "
                  "b775 hs1's nine 64 x 64 hair textures (locs, twists, braids, strands, curls, bun) are drawn "
                  "procedurally by tools/nfl2k5_hair_styles_generate.py. "
                  "b778 cf1 and its follow-up jobs scanned the head.png of every club with a recipe in "
                  "tools/b77/cf1_recipes (tools/b77/cf1_face_scan.py): "
                  "each is the coach's reference photo projected onto the 2004 head mesh, relit, symmetrised and blended into a "
                  "painted base, so these head.png files are photo-derived likeness textures shipped under Noah's "
                  "2026-10-12 rule (as co2's photo-warped faces were); the reference photos and their cleaned copies "
                  "never ship. Apart from those coach likeness textures, no photograph or photo crop and no "
                  "retail-extracted pixels are listed; retail details are taken from the user's own disc at build time."
                  " sb1's Super Bowl field flank marks (data/nfl2k5_super_bowl_fields/marks) are drawn by "
                  "tools/nfl2k5_super_bowl_marks_art.py from geometry, gradients and system type in each game's design "
                  "system (no logo is copied, traced or read); LXII to LXV are generic current-system marks for franchise "
                  "seasons whose logo is not revealed; the club marks of the three team-flank games are the mod's own 2026 "
                  "team logos at mark size or a plain club roundel."
                  " b776 fn2's four Titans 7 digit textures (data/nfl2k5_glyph_fixes_2026) are flat two-colour shapes drawn from "
                  "measurements of 2026 club photos (constant-width stem, block foot), not traced from a font file or photo pixels. "
                  "b780's scorebug digit sheet glyph layer (data/nfl2k5_scorebug_digit_glyphs.png) is rendered text: the digits 0-9, "
                  "the colon and FINAL drawn by tools/nfl2k5_scorebug_espn_art.py (digits_from_font) with DejaVu Sans Bold through "
                  "Pillow 10.2.0 / FreeType 2.13.2, white glyph coverage on transparent, and the retail bolt cell cleared; it holds no "
                  "font file data, no photograph and no retail pixel. DejaVu is under the Bitstream Vera license (DejaVu's changes are "
                  "public domain), which allows reproducing and distributing the fonts; the release ships only this rendering of "
                  "those characters, not the font."
                  " b81-retail-free-art: the 2026 jersey relief (data/nfl2k5_relief_2026_b81u) ships only the project's own layer: "
                  "per texel the authored level B relief minus the base the Studio derives at build time from the user's own disc "
                  "(the 2004 folds softened, the 2004 construction lifted out: mod_editor/core/nfl2k5_relief_2026.py), modulo 256, "
                  "so its difference files hold this season's seams, collar band, vents, pin holes and embosses and are zero "
                  "elsewhere; the jersey's UV islands and each kit's collar opening are derived on the user's machine too (from the "
                  "game's player mesh and the kit's torso texture), so no layout mask ships. The earlier absolute relief masters and patches (85 and 93 "
                  "percent byte-equal to a transform of the retail maps) were withdrawn, and this tool refuses any relief file "
                  "that decodes as an absolute normal map."
                  " b81-retail-free-art: the b81u digit and nameplate pictures (data/nfl2k5_glyph_fixes_2026_b81u) that ship are "
                  "measured (retail-free/glyphs/SUMMARY.md: remap, mask and structure tests against the v0.9 glyph and every "
                  "retail glyph) as drawn new by code from 2026 photographs (ARI, ATL, CIN, LAC, TEN digits; 11 name strips) or as "
                  "edits of the project's own glyph art (glyph_shapes traced from photographs, or renders of fan-made fonts: CLE, "
                  "DEN, DET, HOU, LAR, MIA, NE, SEA digits; CLE names). The pictures that edited a glyph the Studio builds from a "
                  "retail donor are listed in NOT_AUTHORED and do not ship: their edits are shipped as operations and applied at "
                  "build time to the glyph the user's disc gives (digit_derived), or, where no operation list rebuilds "
                  "them, only the texels that differ from that glyph (or from the strip the nameplate pass "
                  "leaves) ship (paint); none was withdrawn.")

# Reviewed by i3 on 2026-10-14 (contact sheets in the i3 scratch png_review/). Not authored art, so not catalogued.
# path or (folder, name) -> (SHA-256 of the reviewed bytes, reason). A different SHA-256 at the path needs a new review.
# pr2 removed both rejected rendered portraits. Real headshots live in the external league data.
# co3 replaced the 32 accessories atlases with authored headset halves; retail details come from the user's disc.
# b81-retail-free-art (2026-11-20): the b81u digit pictures measured as edits of retail-derived glyphs
# (retail-free/glyphs/SUMMARY.md); none ships, and a file put back at one of these paths is refused.
NOT_AUTHORED: dict[str, tuple[str, str]] = {
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02A0_digit_arm_0.png": ("68812b84079d06eac339e4907da96e91f232d3dec8baccf8a99e9837035af8d1", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02A0_digit_arm_4.png": ("2b5d29dd4c399fe25a27342c2248b3f07ce1c10aa338683646660bf0f9ca1489", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02A3_digit_arm_0.png": ("5fd5f6d4442793a37fe13390a76c2e36ac86cc471dab1f31450cb62bcd79ac9d", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02A3_digit_arm_4.png": ("993f0016ad9dc14fc3e49eb6ca603c14a9c34b72887d04f63761b358ced0be41", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H0_digit_arm_0.png": ("4273e976a1cfea4e20a14784056a9c72be3cd0b4ef0f0c509ad66754ee0f71ae", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H0_digit_arm_4.png": ("fef24d9ad4a93f017e4f198810f94a1fede25d0f174381e5a5008ccec9cdcc58", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H2_digit_arm_0.png": ("0d2ef7af04f57c10c78ad77e7f864e0909e4b350afc484e86ac80755067399da", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H2_digit_arm_4.png": ("61effb9ecc4676aba3f0076886b3ba87df1c3b2d5c777cfa5947acc124b634dc", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H2_digit_jersey_0.png": ("126241816a5dad969e860de0e7a4a967c8e7d96d0cc2373d7f55d9953e6ba925", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H2_digit_jersey_4.png": ("85f761b9ddb264beebc5fb377ef6ee224f85e07bfd4f52b9c923ceca050e8baf", "b81-retail-free-art unsure (b81u-BAL-digit-0-4-wide): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_0.png": ("9962a0f9f62d821e2110065e0c672c3c1d23f80cee329e66b532c5dd02549c31", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_1.png": ("510847c5ed44ba6758fa3b38a936cf96beebb66f3631685d0b54f3c1fb3d026d", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_2.png": ("24c4d272a2c2ed6661c93103752a02d9b5b141baaf82a005767352457837119c", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_3.png": ("83c4165dad5fb865dac9bfbe956a62dd8f83261e04b60e678cbd1b321d165e19", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_4.png": ("09a699554a18dc33ab63969f4a23a73c577b5dc977af2f9e2afd044adb176972", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_5.png": ("6ca2ab3e8f0554327caef98c8e7cf5564b77ee710c84502f5ebf8dfdecf042b4", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_6.png": ("905c1ea29525ef2d254f5b4eff7e60dd91ff9b5d5c68f83dc0b2cedd1c6b2d19", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_7.png": ("2d8e07734d2ea3cf3e8649e7b232b1fc407c41ac0f20bb50a1b083891d06c79d", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_8.png": ("f691bc4e2697237c142836da187c6025295bdd16e5c15ad3c572873d413242c3", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_9.png": ("f22b191850cd901944b4d71275e68353c7528aa4192d4b6b77870ba74704d724", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_0.png": ("c2a7d5aab04a7c46b62ffcbfa2d12467281c46cd93de02c2f3ce6f1e86ec6f39", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_1.png": ("0d9af191249d99e6f94a4a420c3e7e74c6a6679cf9f9654d56b46e64b22b1389", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_2.png": ("2fc4d7fb9d4dd621905b2f75d0ca677e9f75bc4ed65cc72c6079c75c4e148152", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_3.png": ("f08c3e02c4de0d596206e3a0b0687e72982cff6fb40813a9fb36550f13ffd417", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_4.png": ("7593fc2b8b6007f6fe2ea99616d48e1e0e5582cb213b6ae694ba7893e727289f", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_5.png": ("688a48a7eff49413cbb130dbd6774385c968bd0dcd5fa6f2444bbe57d1cab038", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_6.png": ("a4bcb30988ac7dc7efd0c07fba2edfa4a34e7d7741ee3b88e6944d7267242574", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_7.png": ("e49861b61600285aaf802bc4090cd3a4398a9fbf1d4bb450f9ed45583623889c", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_8.png": ("08760fa83ee21e9057589148295054f5d6023ab40df866ca1f9686822c34a3c7", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_9.png": ("4071d93780aa2655979494cbb1d36f4b1988450efd022344c34b734846583ce3", "b81-retail-free-art C (b81u-CHI-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_0.png": ("1125288e9973f4c5eb281425ba65133392b87822b092913284c0eebff6feed22", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_1.png": ("169701b339a975f3cbc4c9855d52f3c07aee3f47a358462bed2a3e740d0b07ed", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_2.png": ("af91e0dc5ab1bbcb5d66c5b1aebf4b03a467940a806df9b269c27e9f3c97a6a9", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_3.png": ("fbd37a949f108d42793a7a6723dc04e857b5fb150826b5c4c9f5629808dd4837", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_4.png": ("773138ab4d5bcd194e5098204ab5c2880378316544249aa981a8b4c83fd27f1b", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_5.png": ("180ce771f46f7b2a077b8a73834cbfa279f298977a6a8eb2e26c2bc7e617073a", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_6.png": ("08b9333cf99a4b123bda877e9c25a1418ece2abd6580ed55d342828f3784d6ad", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_7.png": ("90f1cfc20ba430612560949e9abecaf58bfc3247dc49fe0b1c7a1fc163b6e749", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_8.png": ("b5ca0c360470c227413664abae6130062800b74ff463ceb1104951bcd9d42b47", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_9.png": ("449ca01cf797f32ca77412c3c6a339b1ba7f100c60a085aa71ba6e7923a8dbfa", "b81-retail-free-art unsure (b81u-DAL-navy-digits-heavy): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_0.png": ("46fc95629ce5955ebafd64fa894cd5886a36c8d63e7564fe4e5cc31ba46d8baf", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_1.png": ("f7b05da8a186a93ae07262e74f96a9caf4e482c48b38897b4248d93e303fca15", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_2.png": ("1f4d9167700af7073ded0b083fc373cb555c34d245b849d0eedf40353a762318", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_3.png": ("f7f18fe2b7c08e8438d44dc0d16be782a01d551128c035a251d3266b8ca79347", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_4.png": ("2a83d372987e4a72f7d076dabd3052fb90b8521885ed49a5f98d9e07aded369d", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_5.png": ("cefec46bd322f9ac0ccb3fe329c87cbbbdf61e9a360fe58c580ab602a77068e7", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_6.png": ("f5147bd2524fab8beff58efc822330c47be15f9a709a6709848548ab3a00bf78", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_7.png": ("d5e881786992337594f0f7e225b03d522df16379257e5676e1a6c8818210c39b", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_8.png": ("d914b3f96fa06ac09ea11d372d7d8f3fa687615d6bfebe0da0c5c0a10cec47e9", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_arm_9.png": ("d557b7fcb1fb3c144de011dffa10520d0a35148461628ef221d2fd4ab6b840d4", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_0.png": ("28ae1db2e05d503e9e8cafcd7ce2743e3ef32902cea41b358166adf21cf6b32d", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_1.png": ("978f4d8fd74c82dcab3485e09ce76c593b31f83fd324ff73d8afeb850b555a0e", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_2.png": ("c1be8a9a3439da1e2da9c092a05f9e50610d95f064f33957fec3f4273c06cf2e", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_3.png": ("4761f5dd91ba5c2fc711ab7f1fbd04c8fe81f3c88eaf542c9df0ef297fd06d7d", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_4.png": ("2f5701d2f9797d3fc3ca7893d5a012ac9f06e61a0ef38237d3c8b822aceb1eaf", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_5.png": ("0c013e20958d184597cfeb5684acc4f9c4326ffbd077efae71caf29069126e16", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_6.png": ("ff4d84d537fbfdb8d7af9c6975ceeabdf3d6c80e1e00b534b20d76cbad8cf9aa", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_7.png": ("8ac5aa8011652b161511d25402a5f7c96f880c63f1333e7383af07b5cfc96e9c", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_8.png": ("a760a84459772a30551889373195dce81db0b766809279fb7da3c39b466bf050", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/GB_10A5_digit_jersey_9.png": ("1743ec966525f11da3b688e6ea53ac70888af4d612c8e4ae8350f3cd1d27f320", "b81-retail-free-art C (b81u-GB-rivalries-heavy-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_0.png": ("00f692c74f4a03a3938af6840f6716ff866f21943769431a797ee258a8e445e9", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_1.png": ("936cbf4eae76b955505ecfd9dad2aeac372fc7bd1b31bb45036c29ca0d966a39", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_2.png": ("bb5fe595333823d9e3469ea9c05220597e29aea79dfc2858ed9c350b54f6425e", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_3.png": ("fff8e94498d5fd848c8a37540347a19486f647f84ee4ca506c69184c7c4f4a26", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_4.png": ("2a38840c69763e1d836dc3f7c780be14ce59cf03a23fdec0cdd35e93c816d30f", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_5.png": ("82b779d793f33f93fd1fd2a49e2a1a0118822f9976f50343944f9ce76a468c14", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_6.png": ("733afd9ded172a625de6118f662704a7bd4b6bffbd93342437472e8bff098090", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_7.png": ("79d7d0724a003ed70e6c9984cce6bee92c138e230c5295b76d4567c4fe15cfac", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_8.png": ("ccef34e903397a87cb29e6377845860a66882c5e452de2341ff78d402262b38d", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_9.png": ("81ea03c171c53fca20283ef607b15d0fc30420fb3622a810a1431916d23ff084", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_0.png": ("0dcde67ab6ac486b29d83f0db385ca36e23dbaa312dafc77396f037da717a8dc", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_1.png": ("4907c76ee94f16abd68f61f6465a90208aaabd4a7c14807f4218d15c2a16c9e7", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_2.png": ("52017d49172b8bf3715c4282268abe1f88ef512b1a3e715f93103d543a293ebf", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_3.png": ("3767635fc7ca44c905ca8e3724cad5664b14c747d078c0c950d0affcfe8816dd", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_4.png": ("1277519b6d41eeb6665aa452ebb9bd215871efdbee6eaa8af7ab6fd8028b081d", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_5.png": ("383be7dfce478245c0436783eda541a050f7dd2e22274d3cf5d5c99ce5297c5b", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_6.png": ("7b43de0b3236ce734bacc8d4689f24382ba35d632e7ed85a044c2ebd7f660772", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_7.png": ("8f5ab3f8a509f0c93ebc4d43beeb11e51710cd09634c71a2aab2fdc0adbeff7a", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_8.png": ("1a6f9b3e73993b0ea08d5e9156f625f5b49e82983bd44366d9e27b8d5dca9c7e", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_9.png": ("ded5ed0f319fe175a02164c7c190788d274676cdfb8c4dddc3cfd09d7967c31c", "b81-retail-free-art C (b81u-IND-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/JAX_12A0_names.png": ("3098fcc01a455e61336834d739847fcac67f87197df3f5b619d13cb182445d80", "b81-retail-free-art C (b81u-JAX-road-nameplate-thin-his-design): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_0.png": ("a49cfb74c0dc8d2c84013ef0fcc81e2e75dfd8ce12ea9de469060bf4d418cfef", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_1.png": ("f6afccb8a1cf91e61acd3a827a67fba2c35ad60811acd023e7ffe486bae7810c", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_2.png": ("b83c55ffa7612651a1ef6a89c0995630b4ef2f9e30d411e4aa165fa31d85833c", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_3.png": ("db364a0cc795a4eca56b34e408a7eb71bb1a2b62f67ca567e5e130e976fc2ba8", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_4.png": ("180a8c9f5fadc5c00835e53ff083b38f581b28896164c3b5dd2927ca7fa41864", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_5.png": ("b004a305afbd3003a658f6e80a37d3f80da54ff0c98deb0a0a8d19e31734094d", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_6.png": ("3af9926e9abb6c9ea26af7331738f16a8f623849473965cfec52ae1cf86bc69f", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_7.png": ("c4249f242337564b88c276211b816f9accf0524d79b09f79fb8c7ae2389c3ab5", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_8.png": ("fecbaa289052aa17a99280bb0308527981f21c0deda7577beb9678e0f5c4acd6", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/LV_20A0_digit_arm_9.png": ("20f785efed1a48b1a2cff0eb4276098a03a57923f66ec9a3eae8b2b964acdb4a", "b81-retail-free-art C (b81u-LV-road-digit-edge-heavy): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_0.png": ("90ce22f338ec526e3fa62d44a97614fa0634c0d702cbe88b3394970e29b36444", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_1.png": ("250e48680643e5c739ba1280a53be61b331bb20b5991306a843edb29790f6273", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_2.png": ("bb7e6dbbe4b71fe5d80b523ceca3a121c4eb03b15f0e0afc4e81e9c7ade9112c", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_3.png": ("c263bcf65e7dcef66a55d0289475fbf9c8101626a2bb97c106cf0ef0ea17063c", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_4.png": ("0e5e456b7d3f34762f5f24319f9b55aff1a0e5590002df749b7e75ddadf8ff41", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_5.png": ("ead90c3dafe6598d002d5741bbe97ddee835c2ee22e51ca615510b56cd603b8a", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_6.png": ("375fe1a474f6740c0846ce9ff8a07585b82ee1f3ad37b1c0051f15be26d838de", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_7.png": ("94a4a718a4837a6c679f06b2c9da433ed13810391736862782639872d9f3e66e", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_8.png": ("a2c32690ca1b60a4ffd7562316f3f280fa70f44449f2303d8a630ec3b3c6fe1b", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_digit_arm_9.png": ("ccbffa9ad37e7dbc2d08bcbff41e46635312dea2210d3ea21db6ff45900ccb2a", "b81-retail-free-art C (b81u-NO-colorrush-light-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_0.png": ("546a433a34f78c175f50baf4b835b0d8918ce556e705b22d48b03f85e4b329d4", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_1.png": ("4bb2c66f0d4b3c01e7c06abb9112f388f1d111abed60fe646e954b5457ba4f91", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_2.png": ("20735c1214a0d04b0badd0e313f82712bb188ef3c71ea3258f8ded62318bc54d", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_3.png": ("82a03d13a3ceedf17cffe6f6129548840c14439dbc257276b756e3d458c70fa2", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_4.png": ("753adc235364c104a670c9dd85aa5ac150db774820fb37085173985d2e0bd3e4", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_5.png": ("6a2e0e8107169999e3fa32faa3594c47c7cbed7c8c311a74b28b82dab284e1f5", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_6.png": ("ca710b697f5d57fa32b72baeccaa6e7391e38006b6cd52f721351c347301ebb1", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_7.png": ("0a09d349ebce80b62dd28a2f635113c79d6852a37b014adfa58a9d71c07c8999", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_8.png": ("21867fdf11888b63a33ce0f145f6efc114920d5ed7cb39c4bf251ce84e04c0df", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_9.png": ("47681ebf5756863fed88443196fdf0ade4bbac7d262639c7dca223b0265847b8", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_0.png": ("60055df548d6e3805465164af9457ba883943b2f27c01625225ba34881cc1b3e", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_1.png": ("3fe5a82d46596ec5066e9620211994c7a93c3693be59f46096d331963e896f53", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_2.png": ("241112df04f92d5dfc5cd679e8d8f89d1cd7561bfaf46ecb35aab669f90f7aef", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_3.png": ("f015c2b115ee922841ca214605f7e9a94065bc2a3d9f1757a7d81d609fd66862", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_4.png": ("8d1a2f422662e429e5564e2bbb43effb6255d76d57efe887e579e2eb4308c695", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_5.png": ("1e7248d6c79b13815d05c82613d36e87fe77a036d147a77cd41743fe2806e7b6", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_6.png": ("18fe5e42d95c9e9608c806d4eee4ff79384a3eb40bfdad1549c15795af95c84b", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_7.png": ("5e0eaa977a41ed783c8cbecd8896128150526a678105e573dbed211122e382db", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_8.png": ("3a9a03f247c0a2fa00ddba2bf9fc2c1da19c9c21bbb47c6c170d253e53531d40", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_9.png": ("f15ce082a741ce82dc3ca703c977e2c0a518a5bfc7cddfc1277b16fa25aeff36", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_0.png": ("a8672fde56cae624c9a5abb4a3e5a8b96179c21492f1f43d974a8d66c860747f", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_1.png": ("f12e1d92436b3176269c4caee48e75440cd2faf27d5a381db2c87dbe8415ecee", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_2.png": ("ccd6a29f297dc4ab39459b0712de84c6c9438ca6c4bfe78a16b988c49cd74f68", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_3.png": ("90535802893dbc6cab551d3c89890d48c507bf9a20c964f1f447bde3c9629509", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_4.png": ("f153e3ecc0047b9ed98c36f6f3dfdaabac9d6cab27c7a8a20582efe32fc8dca1", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_5.png": ("8983a3c7ecb7554c4078587810ea0f2e26b2f937fa295a75d69ee9a365c97b36", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_6.png": ("01457322a6124fa81489d7040fa796b065039692d8aa210f897a8bf0ddd26fb9", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_7.png": ("3a5f5fa82127899cf015df7b6900f117ce16bf0248e32bacdd9b694a995f4087", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_8.png": ("dd9bc04983684662a4c3775220593c8ec9ca00b464c623888478638e1ef2378f", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_9.png": ("b2dbf7971f0ec5715a0d8fa83dcc9b5d8a591e6a69dd03f7098b34e76e1e79b1", "b81-retail-free-art unsure (b81u-NYG-narrow-2004-digits): edit of a glyph the Studio builds from a retail donor; operations on the build's glyph plus the few texels they leave (paint, at most a quarter of the base's edges)"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_0.png": ("d8c71476316d4c2962cca23b97697d6df1174f0334081afd2ce15cc1ea5a5ade", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_1.png": ("185aac0f5bb0bfe8f9e268289776e84e4c899b1ca6b654a05da8164b333a3169", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_2.png": ("9c74362d2669472415232f8aa89ec94204f0003a936157c2b53df44a962a4773", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_3.png": ("1cf755a0471513cb91a9188cfdd3355577b35e883cd91930582c9fabbebaa2ea", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_4.png": ("f87f6931ef812b2595ebbbc1016d34b5d3fb52eecd7c30ed31b6de0bd4d1bb02", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_5.png": ("d4c418f2ce363cb30ae4eb4fb3f285e96457ee9c0588f41e1ccc90319828bb91", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_6.png": ("74fa19896c718353631c1828be0a1735d8d47a4326748fde76cfb719317433fe", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_7.png": ("a20f4920eef5e1b02d4bb2dfb9c8852200c6b4d29e8d43bf1aa010cbf80c236f", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_8.png": ("2200371e3e2639e0536b4110271413e287dfde6f16a602f931a6cd84d1394d95", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_9.png": ("1d6e012cb70806ffdb548e00c5e94b30767f2857ea17145d0ebd56a25110fbbf", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_0.png": ("976668f370c0075514ec8b13d79eba669c52593d8f77658370685c278d09a261", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_1.png": ("95a32b2529ee3228e3c5edf899640d82c38711c55bd03c5a67c7e6831267df0d", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_2.png": ("34248988b4d7d2a059281b1ba1b32f25666f6911d05682ff0387bd0d7f79878d", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_3.png": ("32f4dd515a5154eec565159632c643d4457ed8f04eeacae177b87faa5289cdb9", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_4.png": ("b7298ec077051b0f76abb1a5317e7699fb842aaf421713a55d421619a639f98b", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_5.png": ("4afa8f5b09895635c4b1095ee99c4e4e21a4d5bdb5f4a324fe16b5c7f6f0950a", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_6.png": ("9d3e2c9b9d19cb10bfb73b31832586eac5fe83bc8d25b1daaf792633a1e614c4", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_7.png": ("6fbd9ebe200b105139b8b5a836d0395d59f96082ca638da1d2e759c95d68f228", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_8.png": ("9a5ec63e8ffdf684e06ed3b370ee7571b54670c8149a15a6c71c82ab1f8c0ed6", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_9.png": ("7c7807d85767e5fe74f1c5010f4ec9ef0e59deedeaf8ec40a89a8002fb1b7596", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_0.png": ("7eb0c719756335fa0ff211f7f3c1d5bf828a87e69c4b352b4cf9e7bc2e837c88", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_1.png": ("fe7899a53f105af7337cb997725bfcadbb1b5f08cd431a735d13303dab91e933", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_2.png": ("fc34970735f9e34172973e8e0697cdf22b1ab5ed95c0fd16a9c406d779e7e29d", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_3.png": ("74df0fb3a45876b375fd9bf0dc8537c19abd673f1ea84c5b0d3bf58bbd0062d8", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_4.png": ("bdb7912e6a568705edfcb44937500c462ec95b6adbbb5fd092e65fa40d477dd5", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_5.png": ("f65985cfaf41f01b69c9c417a10f42eff7e472a906ab0c27eaed6b89f28e8484", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_6.png": ("c0bda07853a73f4a32bb43c2ed8a82966b207c3cb2103b2080c5a6056cfed695", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_7.png": ("d8d0aff26ee87690eb055af66f84c2c2814ad99f0cfe06a53b631538ac12de50", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_8.png": ("71aaa509513b7b7e93c5994ec1a690154bc4b6d67489dfe5c4b40b6799a34064", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_9.png": ("095cdf5451fb1858a4be054e387ffc0a1d7bfd1da1e891a4b780b6ac20992ab9", "b81-retail-free-art C (b81u-NYJ-black-light-narrow-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_0.png": ("1e1a665780b5350d6093f815c25d9b2b927e4859ca1cbc705232ea4767a63eae", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_1.png": ("91e66510704c007724c1dd952c59e35184d6cc84aa40b60581be4df6ad634309", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_2.png": ("da672d8d5366ab6fc302f6210b475e6fb0ce83a0866f81edf0567fcd5493fbe2", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_3.png": ("f5c44d1438f1af62a239a85e89d0eddfd3c69392c069cdba1ca1f4473052e80a", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_4.png": ("2159cde9bf6eb06292ec2c1b1a4fbaeebbc775e1f7627b9158bfa34d4a85e64d", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_5.png": ("a029ded1591a652c267fe5ffe945e1ba1e9f1fc88a919f5182f5c7ac85245ac3", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_6.png": ("f5195fa0ffd3c0412009ec1072822f8e15a8d1ccd582c8a8cce85e7be6a5c76a", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_7.png": ("7b72afa92764369e7e6e5a466b4b2f4df62427ff1592a720db8dcd512a33be54", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_8.png": ("86d0089a45d60acdcb3b707981835e1420ac200a2c10f3cd1c40e8003f49821e", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_9.png": ("5e7be7cd17f49a1c353f5873fc8ebe8015ede99b46cf3571abfb58105a97f091", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_0.png": ("defc5a4913ec3c5d3669a4a5c303fe300ada7e315383df2c799690802f025892", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_1.png": ("c2bb4b22afbb86ecf38af8b91dd982ab1dacfe19c84efdd04fefbcecd4313d08", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_2.png": ("f44453e04c035395a883b9f5a1cff0d29a38f240d3f1a7398b9d6e6e272214ec", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_3.png": ("8ff3b9211228d4d3696c1ce644146783eb4138f2118459878a92f11101cad47a", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_4.png": ("be0409e9b4c6912c01d818d264965678d8270a2b9ed9bedbf5cabb7df2217fdd", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_5.png": ("4f3d4e0f0d7d0bdf5b566f4640ab0c3d604cfce76eef1c63e8897a0efe5fad99", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_6.png": ("21a8c50e3208e05f9bfbef1db6b4ab4be26140d61f822c04732b7c82dfdcda52", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_7.png": ("8b6241eedc4278e7c0a00c3424f1421df137cc271d0b892d8f9141b837301f7e", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_8.png": ("eaf03cc9bf43a544b74f4f075f7a38a9bdbb24bdd8c7df02c6276399f3ebb665", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_9.png": ("8c7c11ad05ec95b28efc81815904a8957d1bc526197d9832716d37498efe19c1", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_0.png": ("d2efc95238eb0c4ebfa08f00fb4e22515205991542d8006c0040778f5bca1070", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_1.png": ("55b8fe8fa5892fc16540e7874b70e1d1b153476b938151d1cef899b566655a93", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_2.png": ("e5295329d5174fb4236d5b672bfdac0812950f51225bfc614e1bfae2f9b551b8", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_3.png": ("05197e1124c1364bf22e71cb72363b5ef9e6baf8a03092af1be66f98336c1a1b", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_4.png": ("b4b9d42bf01e8a27ca32864407e511f0d12bf349204bd593e7413a1c96afe30d", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_5.png": ("7518cea0798df82f54f84047e7bde5972163fa0193737a619f8b6c03f42fb028", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_6.png": ("6b7385d4cd059aa88c895d3ab6dbac6494a13615647f895f16336e6709093c32", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_7.png": ("06e7a73524cd3a4c3b022fdee34a44922a16954f8d8dcd168cf1125276d4545e", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_8.png": ("3a73b3f81956ac4f4ebf7d231bf44473464611f16f7d498d2bbd4ab18f7d2249", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_9.png": ("9de7ea8bf0816ca3dcf76413a818f6a6445dcdd98d3348d0269177be2d693e53", "b81-retail-free-art C (b81u-NYJ-2004-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_0.png": ("7811450ec36ae6965e6af17958b645459be4b06586b68fe2cb2cd9f49b307485", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_1.png": ("6c9379a0aba2c4680fcc28ca4d33b5786850072f833d159cc08063e7204d2172", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_2.png": ("12641ddacd5b58ff78b2e844d8c14c879a41bbdaed1fad3f68ef11a31a1327d3", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_3.png": ("1f8cd0a78755cc36b8ad74f5246c802d7a9260e13cac15284a0d8554466e741a", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_4.png": ("31e5ff858cf9611ad467d478c345980a9fc5d6ba99b007aa7bcbb0b0dbb13ff1", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_5.png": ("3e845d839c2f905da1754287e29fdb2c737598ac05cf5bcbea9d4355f26a0aec", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_6.png": ("06108ec107d19b9e1ac8f1a93d9b592354bcf4c3bfe254a4ef637c6912ae4ab3", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_7.png": ("ee8b787cc0e944ab766a66b09e17512a41ee6fa687246083761cd659a8787fe8", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_8.png": ("7cfe3c037a717f4a445e608faea54905dafc29dfd804c1a1ebe1f6ce5cc04a3f", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_digit_arm_9.png": ("a63337673fec372bfaec805a29f21a2ad66aaa0a2974beff6a72e34d29ea4cbe", "b81-retail-free-art C (b81u-TB-road-digits-no-orange-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_0.png": ("4769e904762188f61b8e6e33a8360590f3c6e7dd784009491ce90910bcd0e556", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_1.png": ("dc2439855b4e06d759bde7e3f183fd90d1dec5b89bc0fe59d8fa6efd1bb363a2", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_2.png": ("78df14a865e6afe46b96847e3e662541c27c67da3f655a1a2c2f80f4d8b3d0f4", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_3.png": ("9ae25db24f484f871791c86124f9ac814c409da1b15de1d83fad58297ee8878e", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_4.png": ("099a5ba156ab595f557952d6070fc641a27d0ee1ce4dc2e8dedd138cb35f5eec", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_5.png": ("d581098a412b141506ac48ce1250ffc9b76ddbd7ffb8a3c6944c7a8ca9de0bd8", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_6.png": ("a5d4b9c3cd25a348db07b44300030f6a313ee3c231dd71f070c16d2a908e9939", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_7.png": ("77d470b217255496a2690dce715fc80057e8bd29dd35ffd53bb1704cc2f9085b", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_8.png": ("81541b236f3a0ff1983dd471fe31515c6be0c2aec1586dc73994c8fad8719f04", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/TB_27H0_digit_arm_9.png": ("003c3ee041835bbc504d22dc0f401fcd007cb1b5265e4abd114c0acbc6c3a222", "b81-retail-free-art C (b81u-TB-home-digits-muddy-inline): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_0.png": ("517d0c0798829bcaa7a31e13e7f77d663356718d006da8138f4ed9fd7a97cc4d", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_1.png": ("b96e8237b8769518cc78a1c166a229a8675b6e294e14610cb6b114934063039e", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_2.png": ("131d8c696d96f669e0ef5448b9df71bd87f5071aefb9b592b4182244e3010729", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_3.png": ("3b3f233abd7130cb15c15f92d8f2e9ea1997b8332505cf602933870a854b0d40", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_4.png": ("fef01e5275a31c680e70f25468559b4b303d9d5b8454f8350cfd0b2bc828ec89", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_5.png": ("1a6d70afb744292345e396b08b81c087247dd4b7187469c7382d8e45744e95ca", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_6.png": ("4816cb256d9cb06a8ef47ca860071e88194acd5f99277ee816bbe3125e99928d", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_7.png": ("b9ddc66aef7858dfd59910baee71e4d638f4775e24ccd68d7f528d5f04cd89f0", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_8.png": ("916a9e94505ba4d7b0b13484d53baa8f92d5d5c7ddc8847cb5f658b41afd38cd", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_9.png": ("68e4b466d4680c22943b19c3b795958436601ba2e93ffbb3406a318af18fbded", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_0.png": ("30ff99c88e1261d6773e5850a89962a85adae2ee91724e79ec7a051f7bd49d12", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_1.png": ("527c5cf11242390bbbed0f86656180f525b8d68ecf12e67e127f5c04a9433854", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_2.png": ("d166139cee837e91f88822db447b4e188edaeb6979e0e827f2916b8fba2dee69", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_3.png": ("2569241469ba4c5d4f9135990da88bf67d1349657168d089eff8458744798f95", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_4.png": ("752a787b1b1cdb4c94112e50cafbac5de1cfb69377875a5f14e9747737076ce5", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_5.png": ("71bed9e6ea039ee25200435649ce4835ef37d531f2bad8f8e6a2da7fd288333e", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_6.png": ("53fd7fb9a8127caed544040603bb2e5b6ebbc34a240534aa847c58379a5cad04", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_7.png": ("6a2dea672b3cd2db50b19dd856702e00c5cd61d656cdc6efa450c12a5cb98f6d", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_8.png": ("05c727681b33b8666b2416b75e5b5774a31c44c880e676a8e14f0d590b6ab266", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
    "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_9.png": ("51cd74bd3634716544a044af9dee863f8bed2352b99eab29322f8207e329ce17", "b81-retail-free-art C (b81u-WSH-light-narrow-jersey-digits): edit of a glyph the Studio builds from a retail donor; the edit ships as operations on the build's glyph"),
}
NOT_AUTHORED_BY_NAME: dict[tuple[str, str], tuple[str, str]] = {}


RELIEF_FOLDER = "data/nfl2k5_relief_2026_b81u/"
#: an absolute tangent-space normal map decodes to unit vectors facing out; a difference layer does not. More than this
#: share of a relief file's opaque texels reading as such a normal means a retail-derived map was put back.
RELIEF_NORMAL_SHARE = 0.02


def relief_problem(relative: str, data: bytes) -> str | None:
    """Why a relief file may not ship (it decodes as an absolute normal map, or it is a layout mask), or None."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from nfl_tset_png_import import decode_rgba_png
    width, height, rgba = decode_rgba_png(data, None)
    a = np.frombuffer(rgba, np.uint8).reshape(height, width, 4)
    if relative.rsplit("/", 1)[-1].startswith(("islands_", "openings_")) or (
            np.isin(a[..., :3], (0, 255)).all() and (a[..., 0] == a[..., 1]).all() and (a[..., 0] == a[..., 2]).all()
            and (a[..., 0] == 255).any() and (a[..., 3] == 255).all()):
        return ("a layout mask (UV islands, collar openings) is the game's layout: derive it at build time from the "
                "user's disc (review F1, F2)")
    opaque = a[..., 3] == 255
    if not opaque.any():
        return "an empty relief layer"
    n = a[..., :3][opaque].astype(np.float64) / 127.5 - 1.0
    normal = (np.abs(np.sqrt((n * n).sum(-1)) - 1.0) < 0.05) & (a[..., 2][opaque] >= 180)
    if normal.mean() > RELIEF_NORMAL_SHARE:
        return ("%.0f percent of its texels decode as an absolute normal map: a relief map with a retail-derived base; "
                "ship the difference against the base the Studio derives from the user's disc" % (100 * normal.mean()))
    return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_size(data: bytes, relative: str) -> tuple[int, int]:
    if len(data) < 24 or data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    return struct.unpack_from(">II", data, 16)


def declared_pngs(repo: Path) -> list[str]:
    out = []
    for line in (repo / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#") and entry.lower().endswith(".png") and entry.startswith(FOLDERS):
            out.append(entry)
    return sorted(set(out))


def excluded(relative: str, digest: str) -> str | None:
    """The review verdict for a file that is not authored art, or None. Refuses a changed file at a reviewed path."""
    row = NOT_AUTHORED.get(relative)
    if row is None:
        row = next((v for (folder, name), v in NOT_AUTHORED_BY_NAME.items()
                    if relative.startswith(folder) and relative.rsplit("/", 1)[-1] == name), None)
    if row is None:
        return None
    if row[0] != digest:
        raise SystemExit(f"{relative} changed since its review (was {row[0][:12]}, now {digest[:12]}): review it again")
    return row[1]


#: b81-retail-free-art (review F5): data documents that may carry texel data (``paint`` operations: the texels a
#: redraw adds over the glyph the build holds). Every paint operation is listed in the catalog by row with its SHA-256
#: and texel count, so the release gate refuses any texel data in a data file that was not reviewed here.
PAINT_DOCUMENTS = ("data/nfl2k5_glyph_fixes_2026_b81u.json",)


def paint_digest(op: dict) -> str:
    return sha256(json.dumps(op["runs"], separators=(",", ":")).encode("ascii"))


def paint_rows(document: dict) -> dict:
    """{"<selector>:<chunk>": {"sha256", "texels"}} of every paint operation in a glyph document."""
    out = {}
    for row in document.get("textures", []):
        for i, op in enumerate(row.get("derive") or []):
            if op.get("op") != "paint":
                continue
            texels = 0
            for y, x0, values in op["runs"]:
                if not (isinstance(y, int) and isinstance(x0, int) and isinstance(values, str) and values
                        and len(values) % 8 == 0 and all(c in "0123456789ABCDEF" for c in values)):
                    raise SystemExit(f"malformed paint run in {row.get('selector')}:{row.get('chunk')}")
                texels += len(values) // 8
            out[f"{row['selector']}:{row['chunk']}:{i}"] = dict(sha256=paint_digest(op), texels=texels)
    return out


def build(repo: Path) -> tuple[dict, dict]:
    files, refused = {}, {}
    for relative in declared_pngs(repo):
        data = (repo / relative).read_bytes()
        width, height = png_size(data, relative)
        if relative.startswith(RELIEF_FOLDER):
            problem = relief_problem(relative, data)
            if problem is not None:
                raise SystemExit(f"{relative}: {problem}")
        reason = excluded(relative, sha256(data))
        if reason is not None:
            refused[relative] = dict(sha256=sha256(data), size=len(data), reason=reason)
            continue
        files[relative] = dict(height=height, sha256=sha256(data), size=len(data), width=width)
    on_disk = sorted(p.relative_to(repo).as_posix() for folder in FOLDERS for p in (repo / folder).rglob("*.png"))
    undeclared = sorted(set(on_disk) - set(files) - set(refused))
    if undeclared:
        raise SystemExit("PNG files under the reviewed folders are not in the release allowlist: " + ", ".join(undeclared))
    paint = {}
    for relative in PAINT_DOCUMENTS:
        rows = paint_rows(json.loads((repo / relative).read_text(encoding="utf-8")))
        if rows:
            paint[relative] = dict(rows=rows, texels=sum(r["texels"] for r in rows.values()))
    return dict(classification=CLASSIFICATION, files=files, paint=paint, schema=SCHEMA), refused


def render(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--check", action="store_true", help="refuse when the committed catalog differs")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    document, refused = build(repo)
    data = render(document)
    target = repo / CATALOG
    stale = (target.read_bytes() if target.is_file() else b"") != data
    if not args.check:
        with open(target, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data.decode("utf-8"))
    by_folder = {}
    for relative in document["files"]:
        key = relative.split("/")[1]
        by_folder[key] = by_folder.get(key, 0) + 1
    print(json.dumps(dict(catalog=CATALOG, sha256=sha256(data), files=len(document["files"]), by_folder=by_folder,
                          not_catalogued=len(refused)), sort_keys=True))
    for relative, row in sorted(refused.items()):
        print(f"NOT_AUTHORED {relative} {row['sha256'][:12]} {row['reason']}")
    if args.check and stale:
        print("MODERN_ART_PNG_CATALOG_STALE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

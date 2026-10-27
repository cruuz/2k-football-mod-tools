# 2026 head coaches (beta 77 co1, co2, co3, cm1; b778 cm2, cf1)

Authored textures for `mod_editor/core/nfl2k5_modern_coaches.py`, one folder per club (2026 abbreviations), each at
the native size of the coach model's texture slot (the 4x masters stay with the art job; they go into the 2K5 Edition
texture packs, not this repository):

| File | Slot (coach scene `cNN.iff`, chunk 0) | What it is |
| --- | --- | --- |
| `shirt.png` 128x128 | `shirtShader1` (+ `hatShader1` patch u 0.83-0.99, v 0-0.17) | polo / quarter-zip in the 2026 top colour, thin trims in the accent, cap patch in the cap colour; fabric folds keep the retail shading |
| `jacket.png` 128x128 | `jacketShader1` | full-zip sideline jacket in the same colours |
| `logo.png` 64x64 | `shirtLogoShader1`, `jacketLogoShader1` | the club's 2026 logo where the chest mark quad samples (v 0.41-1.11); the 2004 maker mark is gone |
| `headset.png` 64x64 | `accessoriesShader1`, `clipboardShader1` (the left half, x < 64, of the 128x64 atlas) | unbranded matte black headset (the 2004 earcup and band marks are gone). The shoe and clipboard half of the atlas is not shipped: the build derives it from the user's own disc texture (`derive_accessories`, the 4x bicubic round trip the art was authored through, in integers), so the disc bytes equal those of the earlier full-atlas file (b77 co3) |
| `head.png` 256x128 | `headShader1` | the 2026 head coach's face moved onto the retail head of the body he wears (co2: 468-point landmark warp, the photo's lighting removed, the 2004 shading kept, Poisson-blended, closed mouth, his hair colour on the model's hair layout) |
| `head.png` (cm1: WAS, DAL, CIN, CAR, GB, TEN, LAR, SF, MIN, NYJ, TB, MIA, DET, CLE, NE, ATL, JAX, NYG) 256x128 | `headShader1` | painted per texel at its 3D point on the head mesh (`tools/b77/cm1_coach_models.py head`): one skin tone over the whole head (no face oval, no seam where the UV islands meet), his hair painted above his hairline or a bald scalp, facial hair painted as shapes around the face rig (a grey beard reads grey, never a dark smudge on a light face), and only the fine feature detail (eyes, nose, mouth creases, ears) of co2's face; Tampa Bay's 2004 blue eye atlas recoloured brown |
| `geometry.json` (cm1: WAS, CIN, CAR, GB, TEN, LAR, SF, MIN, JAX, BAL, CLE) | the coach scene's `coachHeadGrp1`, `coachBodyGrp1`, `coachLodGrp1` vertex lanes | authored vertex edits as integers: new NORMSHORT3 positions and NORMPACKED3 normals for the vertices that move, each shape pinned by the SHA-256 of its retail lanes. WAS: Dan Quinn's bald head (the 2004 hair volume off the scalp, up to 1 cm on the crown), with the headset band and the low-detail head following. The ten others: a leaner body (torso, hips and legs of a leaner retail coach of the same mesh family; neck, headset, glasses and hands stay; JAX's c30 has its own vertex order, so its change comes over by position from c28, the same build, to the lean c12), with the low-detail body following. Same vertex count, triangles, skin weights, skeleton and animations |
| `KC/head_mask.png` 256x128 | `headShader1` (c21) | Kansas City only, in place of head.png: R = weight, G = class x 80 (1 hair, 2 brows, 3 moustache) of the recolour the build applies to the disc's own 2004 Reid face |
| `KC/head_overlay.png` 256x128 RGBA | `headShader1` (c21) | Kansas City only: Reid's glasses, painted (the 2004 Reid model has no glasses geometry) |
| `sideline_dry.png` 256x256 | `coachshirt` in the club's four `?d?` team packages | the sideline staff's polo in the same colours |
| `sideline_rain.png` 256x256 | `coachshirt` in the club's four `?r?` team packages | the sideline staff's jacket in the same colours |

Dallas (Brian Schottenheimer, 7031) and Washington (Dan Quinn, 7034) pictures come from the external SOFTDRINK
league project, through `player_portrait` edits like the other 30 coaches. No portrait PNG ships in the Studio.
The module reserves these ids in the coach records. A plain build fills the reserved slots with the user's own
disc's `nophoto` pixels. Retail slots and the rejected co3 renders become that fallback; external league pictures
are kept. Applying the league project replaces either old photo crops or rejected renders with its real headshots.
The painted 3D coach faces and their pins are unchanged.

Skin (b778 cm2): every coach stands on a retail model of his own skin (the module's `DARK_SKIN_MODELS`: the 2004
Black head coaches' models c00, c05, c06, c11, c19 and the created-team coaches c50, c51; `pins.json` `bodies[club].skin`
for the coach, checked when the pins load). Tampa Bay's Todd Bowles wears Dennis Green's c00 (Noah 10/21: "we should use
an actual black model"); Todd Monken (CLE, c26), Zac Taylor (CIN, c36) and Shane Steichen (IND, c33) moved off c00, c06
and c11. Pittsburgh's Mike McCarthy wears the capped c27, with his heavy build carried over in `PIT/geometry.json`.
`superseded_body_codes` names a model an earlier version wrote into a club's record (rewritten on such a disc); `retired`
lists the models no club wears any more (c06, c11), put back to retail on such a disc. Recipes and the 3D move of the
face detail between head meshes: `tools/b77/cm2_coach_models.py`; pins: `tools/b77/cm2_record_pins.py --retail RETAIL.iso --write`.

Scanned faces (b778 cf1: JAX Liam Coen, PIT Mike McCarthy, TB Todd Bowles, CLE Todd Monken; Noah 10/22 "Build every
single coach a proper face"): `head.png` is his official headshot projected onto the head mesh of the model he wears, in
3D (`tools/b77/cf1_face_scan.py`): 478 face-mesh points found on a front render of that model's head and on the photo,
the photo's head pose solved from them, the face of the mesh reshaped toward his proportions (`geometry.json` gains a
`coachHeadGrp1` entry: face vertices only, up to 0.8 cm, left-right symmetric; the low-detail head and the headset
microphone follow; the scalp, ears, neck and any earlier body edit stay), the photo's side light evened out over the
surface, an open or smiling mouth closed, the head around the face painted in his measured skin and hair (cm1's
painter) and blended without a seam. The recipe per coach is `tools/b77/cf1_recipes/<club>.json`; the headshots stay
private. Re-pin only the scanned clubs with `python3 tools/b77/cf1_record_pins.py --retail RETAIL.iso --teams JAX,...
--write` (earlier digests carried forward as `superseded_sha256`).

Bodies (co2): the coach record's `+0x18` names the model the game loads (`c%02d.iff`). Fourteen clubs' coaches wear
another retail body that fits their build better (`pins.json` `bodies`: the model and why; `body_code` per club), and
the module writes those fourteen 16-bit body ids. Kansas City's Andy Reid wears the 2004 Reid model (`c21`) with its own
face, derived at build time from the disc (no retail pixels ship): hair and moustache white and grey, glasses painted.
Each model's shirt, jacket, headset and head are authored for the club that now wears it.

Colours: `data/nfl2k5_scorebug_sprite/team_colors_official_2026.json` (2026 Record and Fact Book, NFL.com logo files);
logos: `data/nfl2k5_scorebug_mnf/logos/`. Each club's choice of top, trim and cap colour, and why, is in
`pins.json` (`apparel`). Faces: painted by `tools/b77/co2_coach_faces.py` (co1: `tools/b77/co1_coach_art.py faces`) from the 2026 official headshots (the
full reference photos stay outside the Studio; portrait crops belong to the separate league project; for Buffalo, Miami and
Minnesota the club's 2026 Coach Matchup portrait in the league art was the reference). Hair colour and density are
set by eye from the photos (`HAIR`, `DENSITY` in that tool).

The sideline staff (gamedata.iff `coach_asst`, material `SIDELINE`, no embedded texture) draw the club's
`coachshirt` texture from the team packages `{code}{h,a}{d,r}{n,s}.iff`; the module refits that one TXTR chunk in all
eight, found through each package's own chunk table.

`pins.json` holds, per club, the retail and compiled SHA-256 of the coach scene span, its offset and size, the palette
size the art compiles at (192 for five clubs whose new art needs a smaller palette to fit the retail span), the refit
receipt and the SHA-256 of every PNG and of a club's geometry.json; per portrait, the slot, the retail and fallback span SHA-256 and rejected render digests.
Regenerate with `python3 tools/b77/cm1_record_pins.py --retail RETAIL.iso --write` after changing any PNG or geometry
file (it carries the digests of earlier versions forward as `superseded_sha256`). A club's
`geometry` pin is the SHA-256 of its `geometry.json`; `python3 tools/b77/cm1_coach_models.py geometry|head --retail
RETAIL.iso` rewrites the geometry and the painted heads from the recipes in that tool.

EXPERIMENTAL / UNWITNESSED: proved offline; the look in the game is for Noah's eyes.

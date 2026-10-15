# 2026 head coaches (beta 77 co1, co2, co3, cm1)

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
| `head.png` (cm1: WAS, DAL, CIN, CAR, GB, TEN, LAR, SF, MIN, NYJ, TB) 256x128 | `headShader1` | painted per texel at its 3D point on the head mesh (`tools/b77/cm1_coach_models.py head`): one skin tone over the whole head (no face oval, no seam where the UV islands meet), his hair painted above his hairline or a bald scalp, facial hair painted as shapes around the face rig (a grey beard reads grey, never a dark smudge on a light face), and only the fine feature detail (eyes, nose, mouth creases, ears) of co2's face; Tampa Bay's 2004 blue eye atlas recoloured brown |
| `geometry.json` (cm1: WAS, CIN, CAR, GB, TEN, LAR, SF, MIN) | the coach scene's `coachHeadGrp1`, `coachBodyGrp1`, `coachLodGrp1` vertex lanes | authored vertex edits as integers: new NORMSHORT3 positions and NORMPACKED3 normals for the vertices that move, each shape pinned by the SHA-256 of its retail lanes. WAS: Dan Quinn's bald head (the 2004 hair volume off the scalp, up to 1 cm on the crown), with the headset band and the low-detail head following. The seven others: a lean body (torso, hips and legs of a leaner retail coach of the same mesh family; neck, headset, glasses and hands stay), with the low-detail body following. Same vertex count, triangles, skin weights, skeleton and animations |
| `KC/head_mask.png` 256x128 | `headShader1` (c21) | Kansas City only, in place of head.png: R = weight, G = class x 80 (1 hair, 2 brows, 3 moustache) of the recolour the build applies to the disc's own 2004 Reid face |
| `KC/head_overlay.png` 256x128 RGBA | `headShader1` (c21) | Kansas City only: Reid's glasses, painted (the 2004 Reid model has no glasses geometry) |
| `sideline_dry.png` 256x256 | `coachshirt` in the club's four `?d?` team packages | the sideline staff's polo in the same colours |
| `sideline_rain.png` 256x256 | `coachshirt` in the club's four `?r?` team packages | the sideline staff's jacket in the same colours |

`portraits/7031.png` (Dallas, Brian Schottenheimer) and `portraits/7034.png` (Washington, Dan Quinn) are the Coach
Matchup / VIP pictures for the two clubs whose 2004 coach had none (7007 and 7029 resolve to `nophoto`). The module
writes them into two retail portrait slots no roster record uses and points those coach records' `+0x40` at them.
They are authored renders (b77 co3), not photographs: the game's own coach model for that club (its 2004 head mesh,
co2's authored face texture and co1/co2's polo), the head reshaped to the coach's proportions (landmark positions
measured on his official headshot), the face texture painted over by hand (seams levelled, the 2004 hair layout painted
out, his eye colour), his hair and beard grown as strands, lit and rendered in Blender Cycles in the framing of the
game's coach pictures and cut out on a transparent background. No pixel of any photograph is in them. co1's earlier
pictures (photo crops) are pinned only as `superseded_sha256` disc states, so a disc that carries them is updated in
place.

Bodies (co2): the coach record's `+0x18` names the model the game loads (`c%02d.iff`). Fourteen clubs' coaches wear
another retail body that fits their build better (`pins.json` `bodies`: the model and why; `body_code` per club), and
the module writes those fourteen 16-bit body ids. Kansas City's Andy Reid wears the 2004 Reid model (`c21`) with its own
face, derived at build time from the disc (no retail pixels ship): hair and moustache white and grey, glasses painted.
Each model's shirt, jacket, headset and head are authored for the club that now wears it.

Colours: `data/nfl2k5_scorebug_sprite/team_colors_official_2026.json` (2026 Record and Fact Book, NFL.com logo files);
logos: `data/nfl2k5_scorebug_mnf/logos/`. Each club's choice of top, trim and cap colour, and why, is in
`pins.json` (`apparel`). Faces: painted by `tools/b77/co2_coach_faces.py` (co1: `tools/b77/co1_coach_art.py faces`) from the 2026 official headshots (the
photos themselves are reference only and are never copied into the repository or a pack; for Buffalo, Miami and
Minnesota the club's 2026 Coach Matchup portrait in the league art was the reference). Hair colour and density are
set by eye from the photos (`HAIR`, `DENSITY` in that tool).

The sideline staff (gamedata.iff `coach_asst`, material `SIDELINE`, no embedded texture) draw the club's
`coachshirt` texture from the team packages `{code}{h,a}{d,r}{n,s}.iff`; the module refits that one TXTR chunk in all
eight, found through each package's own chunk table.

`pins.json` holds, per club, the retail and compiled SHA-256 of the coach scene span, its offset and size, the palette
size the art compiles at (192 for five clubs whose new art needs a smaller palette to fit the retail span), the refit
receipt and the SHA-256 of every PNG; per portrait, the slot, the retail and written span SHA-256 and the PNG digest.
Regenerate with `python3 tools/b77/cm1_record_pins.py --retail RETAIL.iso --write` after changing any PNG or geometry
file (it carries the digests of earlier versions forward as `superseded_sha256`, the two portraits' included). A club's
`geometry` pin is the SHA-256 of its `geometry.json`; `python3 tools/b77/cm1_coach_models.py geometry|head --retail
RETAIL.iso` rewrites the geometry and the painted heads from the recipes in that tool.

EXPERIMENTAL / UNWITNESSED: proved offline; the look in the game is for Noah's eyes.

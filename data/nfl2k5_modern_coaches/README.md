# 2026 head coaches (beta 77 co1, co2)

Authored textures for `mod_editor/core/nfl2k5_modern_coaches.py`, one folder per club (2026 abbreviations), each at
the native size of the coach model's texture slot (the 4x masters stay with the art job; they go into the 2K5 Edition
texture packs, not this repository):

| File | Slot (coach scene `cNN.iff`, chunk 0) | What it is |
| --- | --- | --- |
| `shirt.png` 128x128 | `shirtShader1` (+ `hatShader1` patch u 0.83-0.99, v 0-0.17) | polo / quarter-zip in the 2026 top colour, thin trims in the accent, cap patch in the cap colour; fabric folds keep the retail shading |
| `jacket.png` 128x128 | `jacketShader1` | full-zip sideline jacket in the same colours |
| `logo.png` 64x64 | `shirtLogoShader1`, `jacketLogoShader1` | the club's 2026 logo where the chest mark quad samples (v 0.41-1.11); the 2004 maker mark is gone |
| `accessories.png` 128x64 | `accessoriesShader1`, `clipboardShader1` | unbranded matte black headset (the 2004 earcup and band marks are gone); shoe and clipboard pixels are the retail layout |
| `head.png` 256x128 | `headShader1` | the 2026 head coach's face moved onto the retail head of the body he wears (co2: 468-point landmark warp, the photo's lighting removed, the 2004 shading kept, Poisson-blended, closed mouth, his hair colour on the model's hair layout) |
| `KC/head_mask.png` 256x128 | `headShader1` (c21) | Kansas City only, in place of head.png: R = weight, G = class x 80 (1 hair, 2 brows, 3 moustache) of the recolour the build applies to the disc's own 2004 Reid face |
| `KC/head_overlay.png` 256x128 RGBA | `headShader1` (c21) | Kansas City only: Reid's glasses, painted (the 2004 Reid model has no glasses geometry) |
| `sideline_dry.png` 256x256 | `coachshirt` in the club's four `?d?` team packages | the sideline staff's polo in the same colours |
| `sideline_rain.png` 256x256 | `coachshirt` in the club's four `?r?` team packages | the sideline staff's jacket in the same colours |

`portraits/7031.png` (Dallas, Brian Schottenheimer) and `portraits/7034.png` (Washington, Dan Quinn) are the Coach
Matchup / VIP pictures for the two clubs whose 2004 coach had none (7007 and 7029 resolve to `nophoto`). The module
writes them into two retail portrait slots no roster record uses and points those coach records' `+0x40` at them.

Bodies (co2): the coach record's `+0x18` names the model the game loads (`c%02d.iff`). Twelve clubs' coaches wear
another retail body that fits their build better (`pins.json` `bodies`: the model and why; `body_code` per club), and
the module writes those twelve 16-bit body ids. Kansas City's Andy Reid wears the 2004 Reid model (`c21`) with its own
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
Regenerate with `python3 tools/b77/co2_record_pins.py --retail RETAIL.iso --write` after changing any PNG (it carries
the digests of earlier versions forward as `superseded_sha256`).

EXPERIMENTAL / UNWITNESSED: proved offline; the look in the game is for Noah's eyes.

# 2025-26 NFL officials (Build option `modern_officials`)

Authored textures for `mod_editor/core/nfl2k5_modern_officials.py`. EXPERIMENTAL / UNWITNESSED.

| File | Slot (gamedata.iff) | Size | What it is |
|---|---|---|---|
| `shirt.png` | scene `referee`, material `shirt` | 256x256 | the shirt used since 2006: wide white and thin black stripes flaring into a black shoulder yoke, black collar and centre placket, white number panel across the upper back, NFL shield on the wearer's left chest, long black sleeves with one white stripe down the outside of the arm, black cuff; black shoes with a white midsole line |
| `pants.png` | scene `referee`, material `pants` | 256x256 | black long pants, a thin white stripe down the outside of each leg, black belt and silver buckle, small NFL shield on the wearer's right hip |
| `hat_white.png` | TSET `rhat_white` | 64x64 | the referee's white cap |
| `hat_black.png` | TSET `rhat_black` | 64x64 | the other officials' black cap, white piping on the panel seams |
| `numbers/ref_*.png` | TXTR `ref_R`, `ref_U`, `ref_HL`, `ref_LJ`, `ref_FJ`, `ref_SJ`, `ref_BJ` | 128x128 | black role letter(s) above the number on the white back panel; `ref_HL` reads `DJ` (head linesman renamed down judge in 2017); the numbers are the game's own |

The two caps share one index image in the game (two palettes), so the PNGs have identical structure. Rows 0-50 of
the number textures are clear: the 2004 front-chest number patch samples there after the module's UV plan.

Every texel was painted from the 3D point of the retail referee model it lands on (bind pose; the model only supplies
geometry and UV layout); no retail pixel is in these files. Sources for the look (photos stay private, never in the
repo): Wikimedia Commons photos of NFL officials from the 2025 and 2026 seasons (CC BY-SA 4.0), ESPN (2006 redesign:
wide white and thin black stripes flaring at the shoulders), Football Zebras (black pants since 2012, referee white
cap and black caps for the others, the 2017 head linesman to down judge rename) and NFL Football Operations (the seven
positions R, U, DJ, LJ, FJ, SJ, BJ). Stripe widths are estimated from the photos (no published measurement).

Authoring tool: `tools/b77/rf1_officials_art.py` (4x masters, area-downscaled). Pins: `tools/b77/rf1_record_pins.py`
from a retail USA image. Native application on a disc copy: `tools/b77/rf1_repair.py`.

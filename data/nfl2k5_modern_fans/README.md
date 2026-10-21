# 2026 fans in the crowd cutaways (b77 fr1)

Authored textures for the Build option `modern_fans` (`mod_editor/core/nfl2k5_modern_fans.py`), EXPERIMENTAL /
UNWITNESSED, on only in the `softdrink_experimental` preset.

The close-up fans of the crowd-reaction cutaways (scenes `crowda` .. `crowdn`, `crowdv3`, `propscrowdsign`) bind
their clothing and props by material name to the textures of the club's crowd texture sets: four archive families
of 85 outers each, in asset-code order (`A` 1822+i, `B` 1907+i, `ns` = `nsNN.iff` 2162+i, `tg` = `tgNN.iff`
2247+i). One PNG per club and texture name, at the native slot size; the Build writes it into every set copy.

| File | Size | What it is |
|---|---|---|
| `tshirt.png` | 256x128 | club-colour tee, 2026 logo on the chest and the cap panel (u 0.75-1, v 0-0.37) |
| `sweatshirt.png` | 256x128 | heather-grey hoodie front: logo, nickname, drawstrings, pouch pocket |
| `jersey.png` | 256x128 | replica of the 2026 home jersey colours, collar trim, two sleeve stripes |
| `varsity.png` | 256x128 | club-colour body, cream sleeves, second-colour trims, plain white tee, small chest logo |
| `puffyjacket.png` | 256x128 | club colour, hood lining in the second colour, small chest logo |
| `hardhat.png` | 128x64 | club colour with the 2026 logo |
| `boxlogo.png` | 64x64 | 2026 logo on a clear ground |
| `crowdsign.png` | 128x128 | white poster board: `#`, logo, a harmless club chant |
| `foamfinger.png` | 128x64 | foam finger in the club colour and the second colour |
| `fanplate.png` | 128x128 | vanity plate, nickname, cloth patch, logo (tailgate) |
| `noshirtns0N.png` | 64x64 | painted-chest letters, only WAS (HAIL!!!!), LAR, SEA, LAC |
| `head01.png`, `head03.png` | 128x128 | face-paint layer, only where the 2004 paint carried a retired or outdated mark (WAS 01 and 03, DET 03, MIA 03, NYJ 03, SEA 01): 2026 colours split down the face (or two stripes), small 2026 logo |
| `scenes/*.png` | 64x64 | KC and WAS superfans: headdress feathers clear, band a club-colour headband with the logo; the drinking fan's cup without the 2004 drink brand |

Only authored textures ship here: the 2004 retail art was the layout and fold template (read from the user's own
disc by `tools/b77/fr1_fan_art.py`), and no reference photo is in this folder or any pack. No retail pixel ships
either: the few retail details the 2026 art keeps (the t-shirt's sneaker and swatches, the hard hat's corner
swatches, the plate's grey bar; `KEEP_RECTS` in the module) are flat grey here and the Build takes them from the
disc's own texture, and the face paints are paint layers (alpha = paint) laid over the disc's own head. The 4x masters are
kept outside the repository. `pins.json` holds, per set copy, the retail and compiled SHA-256 of the texture chunk
span and the palette size it compiles at (`tools/b77/fr1_record_pins.py`).

Not changed: the other heads and face paints, the jersey digits, cement and chair, the other team superfans
(`crowdsNN` embedded textures), the 53 classic and special asset codes.

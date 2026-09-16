# Modern Arrowhead (experimental)

Beta 71. Option `modern_arrowhead` (Build tab, "Modern Arrowhead (experimental)"), off in every preset, needs a disc image. Owner `mod_editor/core/nfl2k5_modern_arrowhead.py`; art `data/nfl2k5_modern_arrowhead/`; pins `data/nfl2k5_modern_arrowhead_pins.json`. EXPERIMENTAL and UNWITNESSED in game.

## What it changes

The nine Arrowhead Stadium bundles (`s13` day, afternoon, night x dry, rain, snow) carry a field scene and a stadium scene. Fourteen embedded P8 textures are replaced in each bundle and the two scenes are refit inside their fixed VC-LZ spans with the retail wrapper bytes unchanged (only the scratch word may move):

| Scene | Material(s) | Texture | Retail | Modern |
| --- | --- | --- | --- | --- |
| field | endzone_N_L / endzone_S_L, _M, _R | three 256x128 | red CHIEFS and the 2004 mark on grass, with an AFL A | red CHIEFS with white trim on grass, the current mark at both ends |
| field | center_logo | 256x256 | the 2004 mark | the current mark |
| stadium | seat03; seat01 / seat02 | 128x128 x2 | grey-blue seats and grey rows | Chiefs red, retail shading kept |
| stadium | yardside; yardfront | 64x64, 128x128 | green pad with the mark; brown pad | red pads with the gold rail, the mark, CHIEFS KINGDOM |
| stadium | banner_corp | 256x256 | 2004 sponsor boards | fascia boards: sportsbook green, BET LIVE NOW, magenta carrier, CHIEFS KINGDOM |
| stadium | ad01 | 256x256 | 2004 wall ads | 2026 sponsor panels |
| stadium | banner_home_team, banner_home_player, banner_away_team | 128x128, 256x128, 128x128 | 2004 fan banners | CHIEFS KINGDOM, MAHOMES 15 / KELCE 87, GO CHIEFS |
| stadium | tarpGreen | 128x128 | green tarp | red tarp |

Untouched (and why): the crowd figures live in the separate `crowds13` scenes (heads and hats; their shirt colours are not a texture), the grass colour map and bump map belong to the modern colour option, the yard numbers and the AFC/NFC shields, the stadium lights, walls, rails, suites, benches, cameras and props are retail, the jumbotron digits are a shared 32x32 atlas, and the goal posts, seating bowl and boards are geometry.

## Proof

`python3 -m mod_editor.core.nfl2k5_modern_arrowhead record-pins <packs>` compiles every bundle from the retail packs; every scene fits its retail consumed size with scratch under the observed SCNE maximum:

- `s13dd.iff`: field 200486 of 200488 bytes (scratch 16), stadium 913131 of 913146 bytes (scratch 96)
- `s13dr.iff`: field 215150 of 215166 bytes (scratch 32), stadium 924181 of 924195 bytes (scratch 80)
- `s13ds.iff`: field 170673 of 170674 bytes (scratch 16), stadium 973065 of 973073 bytes (scratch 112)
- `s13ad.iff`: field 200562 of 200565 bytes (scratch 16), stadium 915489 of 915503 bytes (scratch 80)
- `s13ar.iff`: field 215228 of 215242 bytes (scratch 32), stadium 926322 of 926331 bytes (scratch 80)
- `s13as.iff`: field 170724 of 170725 bytes (scratch 16), stadium 975418 of 975427 bytes (scratch 128)
- `s13nd.iff`: field 200488 of 200490 bytes (scratch 16), stadium 915753 of 915765 bytes (scratch 80)
- `s13nr.iff`: field 215151 of 215166 bytes (scratch 32), stadium 934929 of 934944 bytes (scratch 80)
- `s13ns.iff`: field 170661 of 170663 bytes (scratch 16), stadium 969046 of 969057 bytes (scratch 112)

`tests/mod_editor/test_nfl2k5_modern_arrowhead.py` re-derives the night bundle from the retail packs and checks it against the pins, checks that bytes outside the two spans are untouched, and that the packs read as retail. `image_status` returns retail / applied / mixed / foreign; the build refuses anything but retail or already-modern bundles. Off does not restore an already-modern source.

## Witness list

Play Now at Arrowhead (Chiefs home) at night and by day: red seats and tarps, red wall pads with the gold rail and CHIEFS KINGDOM, the fascia boards, the wall ads, the end zones, the midfield mark, the fan banners. Compare with `before_after_night.png`. None of it has been seen in a running game.

## Combined colour builds

When Modern colour and lighting is enabled alongside Arrowhead, the field scene is authored with the modern marks before its colour transforms and compressed once into its retail allocation. The decoded turf, linked outside grass and vertex tints retain the selected colour recipe. Stadium art retains its separate applied pins. A per-bundle sidecar records both options, and read-back checks complete bundle hashes and every owned scene span. A changed or missing receipt requires the original retail source.

The integration report records the nine-variant offline proof. The combined disc builder is prepared; a played appearance remains UNWITNESSED.

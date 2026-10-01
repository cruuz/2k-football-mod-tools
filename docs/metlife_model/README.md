# Modern MetLife model (experimental)

Build tab option `modern_metlife_model` (beta 76, job u5). It is off in every preset. EXPERIMENTAL / UNWITNESSED:
nothing here has been seen by the owner in game.

## What it does

It replaces Giants Stadium with a MetLife Stadium model built from scratch. This covers the Giants home venue (s18)
and the Jets home venue (s19), across all eighteen stadium bundles: day, afternoon and night, each dry, rain and snow.
Modern MetLife Stadium (`modern_metlife`, the skin) repaints the retail building. This option writes a new stadium
scene over the skin and reuses the skin's signage, boards and crowd hooks. Turning it on in the Build tab also turns
on the skin.

The model is built to the real plan and section:

* **Plan.** The field wall and the facade follow the OpenStreetMap outline of the stadium and pitch (ways 24221553
  and 180559973). The sideline wall is about 39 m from the centre line and the end wall about 66.5 m, cross-checked
  against Esri World Imagery from 2014, 2018, 2022 and 2025.
* **Section.** The tiers stack in the order the Commons photos show: the 100 level, Suite Level 3, the club fascia,
  the 360 degree ribbon, the 200 level, Suite Levels 5 and 6 on the sidelines, the Ring of Honor fascia and the 300
  level with its vomitories.
* **Video boards.** Four corner boards, 35 x 9.1 m (b76-u5b). The game draws its live feed into the `jumbo_tron`
  material as a 640x448 image inside a 1024x512 texture, so each board's video window maps a crop of that rectangle
  (u 0 to 0.625, v 0 to 0.875) at the window's own aspect: the feed fills the window and is never stretched. On the
  inner side of each board an 11.5 m game-information panel (team, VISITORS, TIME, PLAY CLOCK) carries the game's own
  score, clock and play-clock digits; a sponsor header sits on top (pepsi and BUD LIGHT at the north end, HCLTech and
  verizon at the south, the 2022-2024 photos).
* **Signage (b76-u5b).** Every sign is its own strip of geometry at its atlas cell's aspect, on the fascia's own
  facets: the 360 ribbon runs the home team's content end to end (Giants in royal blue, Jets in white on black, as
  the 2025 and 2026 photos show), the club fascia MetLife's, and the gate signs and pylon strips keep 8:1.
* **Ring of Honor (b76-u5b).** Every member of the home team's ring (the Wikipedia lists: Giants 50, Jets 21) on a
  white plate with the number and name, 0.9 m tall at the plate's 10.67:1 aspect, a third of a plate apart along the
  300-level fascia as the 2026 Jets photo shows them. The Jets' run is centred on the far sideline; the Giants' fifty
  go all the way round.
* **Field wall (b76-u5b).** Panels of a wall atlas (`data/nfl2k5_metlife_model/wall.json`) at their own aspect: for
  the Giants the royal-blue pads with 'ny GIANTS', the twelve retired numbers in white boxes along the sidelines, GO
  BIG BLUE over a sunburst and the SINCE 1925 roundel at the ends (the 2025 photos); for the Jets the White Out wraps
  (two green stripes, JETS, NEW YORK JETS, J-E-T-S and the plane roundel; the 2026-09-20 photos). The retail
  field-level fan and corporate banners are gone.
* **Solar Ring.** 47 frames on the rim with an LED strip that shows the team colour at night. The light glows and
  flares are moved onto the ring.
* **Facade.** Aluminium louvres over a limestone base. At night the glass glows in the team colour. METLIFE STADIUM
  letters and the MetLife mark sit on top.
* **Plaza and gates.** The plaza, and the five gate buildings on their OpenStreetMap footprints (ways 230056157,
  230056159, 230056162, 230056176 and 230056181), with sponsor signs taken from the skin's atlas.
* **Flyover.** A new pregame flyover (the intro_cameras scene): five shots, opening outside the stadium.
* **Crowd.** 2026 superfans: the Giants helmet and the Jets hard hat in the crowd scenes carry the current marks.

The engine and gameplay still use some retail parts, so those stay: the field scene, the sideline props, the pylons and
yard markers, the 190 markers and every material the executable looks up by name (`crowd`, `jumbo_tron`, `digit_*`).

## How it fits

`nfl2k5_scne_builder` writes the stadium scene from scratch: records, relocations, strips, render spheres and P8
textures. The scene is then fitted into the retail stored span of each bundle's stadium chunk. The fit uses a literal
fill up to the stored size, with the scratch word at the exact in-place minimum. Every bundle and every archive entry
keeps its size, and nothing else on the disc moves. The decoded model scene is smaller than retail in every variant:
the Giants' at least 83 KB under (s18dd 1.573 MB against 1.657 MB), the Jets' at least 179 KB under. PROVED OFFLINE.
With Modern colour on the disc, the Build step re-pins the colour receipt's rows for the eighteen bundles it writes,
so the colour read-back and a rebuild from the output disc still recognise them.

## Files

* `mod_editor/core/nfl2k5_metlife_model.py`: the model, its assembly, the cameras, the Build step and the CLI.
* `mod_editor/core/nfl2k5_scne_builder.py`: the static SCNE parser, serializer and fixed-span refit.
* `mod_editor/core/nfl2k5_metlife_crowd.py`: the superfan atlases.
* `data/nfl2k5_metlife_model/footprint.json`: the OpenStreetMap outline, pitch and gates, converted to metres
  (ODbL 1.0, (c) OpenStreetMap contributors).
* `data/nfl2k5_metlife_model/art/*.png`: the authored textures, drawn by `tools/nfl2k5_metlife_model_art.py`. These
  are the louvres, limestone, ring panels, letters and logo (from the MetLife logo file on Wikimedia Commons, public
  domain), the portals, the two superfan overlays (the 2026 team marks), and per venue the board panel, the signage
  atlas (Ring of Honor plates, ribbon, club and gate signs) and the field-wall atlas.
* `data/nfl2k5_metlife_model/ring_of_honor.json`: the Giants' and Jets' Ring of Honor lists (Wikipedia, CC BY-SA 4.0,
  fetched 2026-09-24).
* `data/nfl2k5_metlife_model/wall.json`: the wall atlas cells and the per-region panel layouts.
* `data/nfl2k5_metlife_model/pins.json`: the eighteen stretches and the four crowd outers. Each has a retail/skin
  hash and a model hash.

## CLI

```
python3 -m mod_editor.core.nfl2k5_metlife_model status <source>            # retail / skin / applied / mixed / foreign
python3 -m mod_editor.core.nfl2k5_metlife_model build-bundles <source> <out>
python3 -m mod_editor.core.nfl2k5_metlife_model record-pins <retail source>   # maintainer
python3 -m mod_editor.core.nfl2k5_metlife_model apply-lab <disc> --source <retail source>   # lab only
```

## Status

EXPERIMENTAL / UNWITNESSED. Offline: every bundle keeps its size and decodes back byte for byte; the eighteen stretches and four crowd outers are pinned. Lab results are recorded in the u5 report.

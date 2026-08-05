# NFL 2K5 Crib backend and spike findings

This note describes the product boundary implemented by
`mod_editor/core/nfl2k5_crib.py`. It is not a retail-data manifest. The catalog
is reconstructed from checked-in ownership reports, while every original PNG
is decoded lazily from the user's private NFL 2K5 source cache.

## Shipped backend surface

- `load_nfl2k5_crib_catalog()` creates a searchable catalog with 498 physical
  Crib textures. Every row has a stable logical selector, browser label,
  dimensions, format, status, and an authoring note.
- `Nfl2k5CribIO.ensure_original()` and `export_original()` decode any of those
  textures to PNG. Original PNGs and their integrity receipts remain in the
  user's private cache and are never project payloads.
- All 128 Team Photos are `Editable`. `compile_photo()` consumes an exact
  128x128 non-interlaced RGBA PNG, regenerates the 128, 64, 32, 16, and 8 pixel
  P8 mip levels, swizzles each mip independently, retains the existing wrapper
  and system bytes, and produces one 23,008-byte fixed-span build-time patch.
- The other 114 Team Item textures are `Editable` through the same raw,
  fixed-allocation P8 path generalized to their own dimensions and mip counts.
- All 68 standalone CRIB textures are `Editable`. The writer handles 66 normal
  swizzled P8 resources, preserves the reflection texture's exact 109,440-byte
  source-owned pre-palette gap, and writes `ticker_src` as its native 1024x32
  row-major `VC_P8_LINEAR` surface. VC-LZ resources are deterministically
  refitted into the original stored bound.
- All 188 P8 textures embedded in 36 SCNE resources are `Editable`. Same-scene
  edits are composed before one fixed-span recompression; geometry, descriptors,
  unrelated texture allocations, and the source-derived opaque tail are kept.
- The catalog therefore has **498 editable / 0 export-only** texture rows.
- A shareable Crib edit contains only `kind`, the logical `selector`, and the
  user's PNG path. Absolute offsets, original hashes, wrapper bytes, opaque
  tails, and compiled replacement spans stay private build-time values.

## Complete inventory and ownership

The 498 textures divide into three physical storage families:

| Storage family | Count | Contents | Product status |
| --- | ---: | --- | --- |
| Crib item aggregate (outer resource 4274) | 242 | 128 Team Photos, 32 helmets, 32 foam fingers, 32 street signs, 18 collection-art images | All editable, raw fixed-allocation P8 |
| Standalone CRIB textures | 68 | 32 bobbleheads, 32 team logos, logo, reflection, and two ticker surfaces | All editable, fixed-allocation VC-LZ P8 / linear P8 |
| Embedded textures in 36 SCNE resources | 188 | Room and collectible/object surfaces | All editable, grouped fixed-allocation SCNE P8 |

The Team Photo writer has stronger ownership evidence than a name-only match.
The executable-owned catalog row names the `team_photo` scene and `photo`
texture family, and its lookup table resolves exactly 128 resources named
`00_photo_00` through the four variants for all 32 team codes. Every resource
uses the same raw P8 contract: 128x128, five mips totaling 21,824 index bytes,
a 1,024-byte BGRA palette, 128 system bytes, 22,848 video bytes, 22,976 stored
bytes, a 23,008-byte complete resource span, and 32 bytes of following slot
padding.

The 188 scene-embedded rows cover these 36 scenes: `100_complete_lo`,
`ESPN_25_lo`, `air_hockey`, `bar_sign`, `cap`, `chopper`, `dart_machine`,
`fish_tank`, `framed_jersey`, `franchise_lo`, `fullsize_helmet`, `game_ball`,
`glass_00`, `glass_01`, `gui`, `guitar`, `gumball_machine`, `helmet_lamp`,
`mini_helmet`, `paper_football`, `phone`, `player_lo`, `popcorn_maker`,
`primetime_lo`, `punching_bag`, `room`, `skybox_day`, `skybox_night`,
`soda_machine`, `team_lo`, `team_photo`, `team_plaque`, `ticker`,
`trivia_machine`, `user_lo`, and `water_feature`.

## Read-only production-cache result

The production catalog loads exactly 498 unique selectors: 498 editable and
zero export-only. A one-time private-cache export pass decoded and strictly
reparsed **all 498 assets** successfully: all 242 aggregate resources, all 68
standalone textures, and all 188 scene-embedded textures. Every PNG remained
under the user's private source-cache originals directory. Representative
selectors from the three ownership routes were:

- `crib_team_photo:00_photo_00` (aggregate P8 Team Photo, 128x128)
- `crib_external_texture:9:bobblehead_00` (standalone compressed TXTR, 64x128)
- `crib_scene_texture:room:22` (P8 texture inside a compressed SCNE, 128x128)

The real Team Photo template passed the five-mip compiler's independent decode,
allocation, swizzle, and PNG checks and remained exactly 23,008 bytes. Private
read-only compiler proofs also passed for a raw helmet item, an ordinary
standalone VC-LZ logo, the reflection-gap layout, the row-major linear ticker,
and a non-electronics embedded scene surface. No proof run modified a pack or
XISO, and these are not claims of in-game runtime visibility.

## Object reskin and "PS5 in the Crib" spike

No texture, scene, or material name contains `console`, `xbox`, `playstation`,
or `ps5`. Plausible electronics surfaces do exist: the room includes
`bar_monitor`, `screen_espn`, and `screen_crib`; separate object scenes include
`phone`, `trivia_machine`, `soda_machine`, and their mapped materials. These
are credible targets for a custom screen or PS5-themed texture illusion. The
evidence does **not** support promising a PS5-shaped console: a texture can
change colors, labels, and screen art, but it cannot change the silhouette or
add missing geometry.

## Bounded model editing

The 36 Crib SCNE resources contain interdependent node, shape, submesh,
material, pointer, bounds, marker, and command structures inside fixed
compressed allocations. The bounded geometry lane exports and reimports
position-only edits for ten exactly catalogued meshes across seven scenes, with
vertex counts and topology held fixed. UVs, materials, collision/index data,
normals and all unrelated registers remain source-owned. Arbitrary model
swapping, changed topology, new vertices, and replacement helmet/object formats
remain outside this proved boundary.

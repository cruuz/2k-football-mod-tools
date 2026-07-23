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
- The exact `crib_scene_texture:room:22` / `bar_monitor` screen is also
  `Editable`. It accepts a 128x128 RGBA8 PNG, regenerates five P8 mips, changes
  only that decoded texture allocation, recompresses its fixed room SCNE span,
  and preserves geometry, other decoded allocations, and the source-derived
  opaque tail. Images outside the proved compression/scratch envelope are
  refused with a modder-facing suggestion.
- The 369 remaining textures are deliberately `Preview/Export-only`. The
  electronics ownership spike mapped 25 exact material/submesh consumers; only
  `bar_monitor` has the reviewed writer, leaving the other 24 export-only.
- A shareable Crib edit contains only `kind`, the logical `selector`, the user's
  PNG, and its hashes. Absolute offsets, original hashes, wrapper bytes, opaque
  tails, and compiled replacement spans stay private build-time values.

## Complete inventory and ownership

The 498 textures divide into three physical storage families:

| Storage family | Count | Contents | Product status |
| --- | ---: | --- | --- |
| Crib item aggregate (outer resource 4274) | 242 | 128 Team Photos, 32 helmets, 32 foam fingers, 32 street signs, 18 collection-art images | Team Photos editable; 114 others export-only |
| Standalone CRIB textures | 68 | 32 bobbleheads, 32 team logos, logo, reflection, and two ticker surfaces | Export-only |
| Embedded textures in 36 SCNE resources | 188 | Room and collectible/object surfaces | `room:22 / bar_monitor` editable; 187 others export-only |

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

The production catalog loaded with exactly 498 unique selectors: 129 editable
and 369 export-only. A one-time private-cache export pass decoded and strictly
reparsed **all 498 assets** successfully: all 242 aggregate resources, all 68
standalone textures, and all 188 scene-embedded textures. Every PNG remained
under the user's private source-cache originals directory. Representative
selectors from the three ownership routes were:

- `crib_team_photo:00_photo_00` (aggregate P8 Team Photo, 128x128)
- `crib_external_texture:9:bobblehead_00` (standalone compressed TXTR, 64x128)
- `crib_scene_texture:room:22` (P8 texture inside a compressed SCNE, 128x128)

The real Team Photo template also passed the five-mip compiler's independent
decode, allocation, swizzle, and PNG checks. The result remained exactly
23,008 bytes. This pass did not modify a pack or XISO and is not a claim of
in-game runtime visibility; build-pipeline integration and a single xemu spot
check remain the acceptance step for the product owner.

## Object reskin and "PS5 in the Crib" spike

No texture, scene, or material name contains `console`, `xbox`, `playstation`,
or `ps5`. Plausible electronics surfaces do exist: the room includes
`bar_monitor`, `screen_espn`, and `screen_crib`; separate object scenes include
`phone`, `trivia_machine`, `soda_machine`, and their mapped materials. These
are credible targets for a custom screen or PS5-themed texture illusion. The
evidence does **not** support promising a PS5-shaped console: a texture can
change colors, labels, and screen art, but it cannot change the silhouette or
add missing geometry.

Best next step: implement one fixed-span P8 writer for
`crib_scene_texture:room:22` (`bar_monitor`) or the mapped `screen_crib`
surface, rebuild a copied XISO, and spot-check the result in xemu. If it renders
on the expected surface, generalize the same bounded SCNE serializer to the
other compatible Crib scene textures.

## Model-swap spike: Coming Soon

The 36 Crib SCNE resources contain interdependent node, shape, submesh,
material, pointer, bounds, marker, and command structures inside fixed
compressed allocations. Existing evidence supports bounded edits to selected
geometry fields elsewhere in the game; it does not establish a safe general
mesh importer or a same-footprint Crib object replacement contract. Therefore
general model swapping remains **Coming Soon**, rather than being exposed as a
writer that could silently corrupt a scene. The single best follow-up is a
same-footprint experiment on one isolated object: map every pointer and draw
record, replace only its vertex/index payload without changing counts, rebuild
inside the original allocation, and verify both scene traversal and runtime
rendering. Arbitrary glTF/OBJ import would still require relocation, bounds,
material binding, and command-stream semantics after that succeeds.

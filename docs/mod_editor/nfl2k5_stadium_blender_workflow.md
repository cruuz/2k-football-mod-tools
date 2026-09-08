# Stadium texture editing in Blender

**EXPERIMENTAL / UNWITNESSED.** Offline byte checks pass independently of
Blender. Actual Blender interaction and in-game appearance require the witness
lists in `ASTRA_STADIUM_EDITOR_REPORT.md`.

1. Load your NFL 2K5 source in Mod Studio, prepare Stadiums, and select the
   desired scene. Export the textured model into a new folder. Keep the `.gltf`
   and its `.bin` together: the buffer includes geometry, PNG images and UVs.
2. Save `tools/blender/nfl2k5_stadium.py` from the Stadiums workflow card, or
   copy that shipped script. Open it in Blender's Text Editor and Run Script.
   This adds File > Import > NFL 2K5 Stadium and File > Export > NFL 2K5 Stadium
   textures. It can also be imported as a Python module and its `register()`
   called; `unregister()` removes its menu entries.
3. Import the original export through that Import entry. It uses Blender's
   stock glTF importer, packs the images, and retains each source texture's ID
   and dimensions on the material and image. Use Material Preview. Tiling comes
   from each native shape's UV scale and offset, without a V flip. A single
   0.01 root converts centimetres to metres. The source position/index bytes
   are unchanged. The matte material, repeat sampler and 0.5 alpha cutout are
   preview choices, not a reproduction of the game's shader or lighting.
4. Paint an image at its original dimensions. Save the `.blend` file to keep
   your work and custom properties. Keep the image directly connected to the
   Principled shader's Base Color input. The helper does not bake procedural
   materials or scene lighting. To use a replacement image, connect it to that
   material and keep the original dimensions. Shared users of one game texture
   must agree on the same pixels. Renaming the object, material or image does
   not change its source ID.
5. Select the objects whose textures you want to export and use the helper's
   File > Export entry. Choose a new `stadium-textures.gltf` filename. It saves
   the live painted pixels through Blender's image save path, without applying
   the scene view transform. It emits only textures and IDs, no meshes. It does
   not alter the original images' paths or clear their painted pixel buffers.
   One scene per bundle; selecting objects from two scene exports refuses.
6. Back in Mod Studio, select the **same scene** and choose Import Blender
   textures (the older button is named Apply textures from glTF). Open the
   helper's file. Unchanged current pixels produce unchanged receipts and no
   history entry, even if the PNG container differs. Explicit foreign or
   conflicting IDs, wrong dimensions, malformed PNGs and ambiguous names
   refuse before edits. Legacy glTF exports without IDs can still map by an
   unambiguous material name; the helper never needs that fallback.
7. Changed textures compile together with earlier texture edits and the
   existing bounded position recipe for that scene. Every changed P8 texture
   gets one shared 256-entry palette and its complete mip chain. The complete
   scene must fit its fixed compressed span and loader-scratch bound before
   the session publishes any change. A failed fit leaves the previous edit set
   intact. Simplifying a larger area can help; some combinations still cannot
   fit. Review the quantized preview. Undo reverses the whole bundle import.
8. Save the project and use the normal Mod Studio build to create a new game
   copy. The source disc is never edited. Record the build receipt and perform
   Noah's visibility, load, replay and restore checks before sharing a mod.

The new workflow card and updated receipt wording require the protected
`studio_qt.py` wiring in `WIRING.md`. The existing export and texture-import
buttons already invoke the updated facade and backend. Packaging/closure pins
must be refreshed before the integrated build is released.

## What remains outside this workflow

A shape is exported as a named mesh/node so it can be selected in Blender.
That does **not** prove independent runtime ownership. Native node matrices,
selectors, visibility, bounds and linked surfaces are not separable part
transforms. This release does not write transforms, UV coordinates, topology,
materials, normals, collision or newly modelled stadiums.

The existing position-only importer remains restricted to its 75 catalogued
FLOAT3 targets in scene o3280/c5/2648. It requires the full matching scene,
identical vertex counts and equivalent faces. Use Edit Mode vertex movement
and its existing instructions. The locked `s42` family is not a Quick Game
runtime witness. General per-part import requires the research gates in the
report, not a different Blender file format.

## Developer verification without Blender

The source-free tests run with plain Python:

```sh
python3 tests/mod_editor/test_nfl2k5_stadium_blender.py
python3 tests/mod_editor/test_nfl2k5_stadium_gltf_export.py
python3 tests/mod_editor/test_nfl2k5_stadium_editor_roundtrip.py
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_stadium_blender_panel.py
```

The retail acceptance tool reads bounded scene spans and deletes each scene's
export before moving on. `--start` and `--limit` split the set into bounded
batches; omit them for all 477 scenes. It writes only metadata/hashes:

```sh
python3 -m tools.nfl_stadium_editor_proof \
  --cache /path/to/private/derived/stadium-studio-v1 \
  --index /path/to/extracted/vc_53450030/0 \
  --inventory /path/to/indexes/nfl2k5_resource_chunks_v2.json \
  --output /path/to/proof.json
```

For a private developer SCNE span and receipt, without copying a disc:

```sh
python3 -m tools.nfl_stadium_texture_bundle \
  --gltf /path/to/stadium-textures.gltf \
  --index /path/to/extracted/vc_53450030/0 \
  --inventory /path/to/indexes/nfl2k5_resource_chunks_v2.json \
  --output /path/to/new-private-span-directory
```

That directory contains game-derived bytes and is not a distributable modpack.
Use Mod Studio's normal project/build/modpack flow for distribution. The proof
JSON contains no game bytes; glTFs, stock PNGs, `.blend` files and compiled SCNE
spans remain private user assets.

## Community stadium add-ons: withheld from beta 62

The community **Stadium Importer v0.11.1** and **Round-Trip Exporter v0.3.0**
were tested in Blender 4.0.2 with a real Models export. They are **not approved
or bundled**. An untouched Fast Template Export changed 148,712 BIN bytes,
including positions in the wrong coordinate axes. Moving a handle also used
the wrong axes. The exporter can overwrite the original template and does
not write its two output files transactionally. See the
[review and byte evidence](../../ASTRA_STADIUM_BLENDER_ADDONS_REPORT.md).

These add-ons target **Models > Export, then Models > Import**. The Stadiums
export has textures and UVs but does not supply their required vertex-ID
attribute. A shared unit root does not make the two return paths compatible.
Do not feed these versions' Fast Template outputs back into Models. Retain
your original export and saved Blender scene while awaiting a corrected,
validated community release. Continue using the texture workflow above for
Stadiums image edits; for the existing Models workflow, follow the README
generated beside each Models export and review its import receipt.

Any future bundled version must credit the community contributor. The
submitted `author: OpenAI` metadata does not establish OpenAI authorship or
endorsement. Game appearance, visibility, collision and loading remain
**EXPERIMENTAL / UNWITNESSED** until Noah performs the report's witness checks.

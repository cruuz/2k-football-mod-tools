# r62 Stadium editor

**EXPERIMENTAL / UNWITNESSED.** Implemented F2 and F3, with a source-driven UV
export, Blender texture helper, atomic session imports and unchanged-byte
preservation. F1 stays gated on independent runtime ownership; its exact next
steps are below. F4 is a working helper/import workflow and a documented
Stadiums UI handoff. No emulator, display, audio or network was used. Qt tests
run offscreen and bpy is mocked. Nothing is claimed as played by Noah.

Base: branch `astra/r62-stadium-editor`, commit
`cea907a09c69f0be2bb1688f334d9961cc355103`. Read the task brief, RC85 product
changelog, previous Astra report inventory, the hub's
`STADIUM_EDITOR_RESEARCH.md`, and the later
`MODELS_UV_STADIUM_FINDING_2026-09-04.md`. Those hub notes remain unmodified and
are not copied into this commit. The later memo and shipped code supersede the
original memo's statement that no textures or glTF import existed.

## Built

### F2: textured Stadiums exports

The existing exporter already appended decoded PNGs and canonical texture
IDs. Its geometry cache lacked `TEXCOORD_0`, so attaching an image alone could
not place the artwork correctly. `Nfl2k5StudioFacade._studio_for_session` now
supplies the existing writer's bounded scene reader. The exporter rereads one
SCNE and appends source-derived UVs after the unchanged geometry/PNG bytes.

`tools/nfl_scne_gltf.append_stadium_texcoords` matches each cached shape ID,
position count and every position byte against the fresh source before
binding the lane. It reuses the Models decoder's proved equation:

```
u = normshort(register6.x) * shape[+0x30] + shape[+0x38]
v = normshort(register6.y) * shape[+0x34] + shape[+0x3C]
```

Signed normalization divides negative shorts by 32768 and nonnegative shorts
by 32767. No V flip, no clamp to one texture repeat and no vertex-colour
multiplier is added. Existing position/index accessors and bytes are retained.
One 0.01 root retains the centimetre-to-metre contract. The cached source files
are never rewritten or regenerated, and no broad Models/UV import code changed.

Textures use white base colour to avoid darkening the image or introducing a
Blender colour-mix node. Transparent images get a preview alpha cutout at 0.5.
Repeat sampling, matte material, double-sided preview and that cutout remain
preview approximations; exact game shader/sampler/blend behavior is unproved.
Image metadata distinguishes current exported RGBA from the stock RGBA hash.
A backend constructed without a native source reader retains the explicitly
labelled legacy geometry-only UV limitation; the live session facade supplies
the reader.

### F3: Blender images back to the P8 writer

`tools/blender/nfl2k5_stadium.py` is standard-library Python until its injected
or lazily imported bpy entry point runs. It registers File menu Import/Export
operators, uses stock glTF import, packs images and stores source texture IDs
and original dimensions on both materials and images. It exports selected
objects' texture materials to a self-contained, texture-only `.gltf`. It never
passes re-exported meshes, transforms or UVs to a game writer.

The helper explicitly copies live painted pixels into a temporary image;
`Image.copy()` alone can lose unsaved image edits. It preserves image colour
space and alpha mode and uses `Image.save`, without the scene view transform.
Original image paths and pixel buffers are retained, and temporary images and
files are removed on failure. Materials must have one Principled shader with
an image connected directly to Base Color. Different game texture IDs cannot
silently share a Blender image. Linked users of one ID must export matching
pixels. Selected objects from multiple scenes, missing IDs, resized images,
procedural material connections and existing output filenames refuse.

The Studio reader bounds each document/buffer and aggregate image data to
64 MiB, confines external paths and checks the material/texture/image ID
carriers for agreement. An explicit foreign ID never falls back to a matching
material name. Legacy missing IDs can use an unambiguous material name. All
PNGs are validated before any delegate mutation; different PNG containers with
identical pixels count as the same image. Identical current pixels return
`changed=False`, without a writer call or undo entry.

The session delegate adds a multi-texture route. `compile_many` fits all
incoming and earlier staged textures for the scene, plus its existing bounded
position recipe, together. All new authored/preview files are prepared before
publishing the session manifest. A fit, file-write or manifest failure restores
the earlier edit set. Successful imports produce one grouped undo action.
A legacy delegate without batch support refuses more than one changed texture.

The developer CLI `python3 -m tools.nfl_stadium_texture_bundle` invokes the
existing unified writer and writes a new private SCNE-span directory and
receipt. It never copies a pack or disc. These outputs contain game-derived
bytes and are not shareable modpacks.

### No-op preservation and fixed-span compression

The P8 compiler previously regenerated lower mips and reordered palettes even
when the supplied base pixels were unchanged. It now preserves the complete
original index chain, every palette byte including unused entries, and every
original mip. If the entire decoded scene is unchanged, it returns the original
compressed span, wrapper, padding and opaque tail byte for byte. Mixed imports
retain unchanged texture allocations while rebuilding only the edited ones.
Receipts distinguish regenerated mips from preserved allocations.

The retail run exposed a second boundary: simplifying a large texture could
produce a compressed stream so short that its zero gap exceeded the existing
3,120-byte observed loader-scratch cap. The writer now uses the existing
VC-LZ token parser/serializer to replace early match tokens with equivalent
literals, accounting exactly for token and flag-byte costs in linear time.
It never exceeds the original consumed cap; the standard decoder and minimum
in-place-scratch computation run afterward. The fixed tail is preserved and
only the wrapper scratch field may change on an edited scene. Unchanged scenes
bypass recompression and token filling entirely.

Ordinary small edits can still fail because the recompressed stream is too
large. Initial two-small-texture experiments recorded that clean refusal on
several scenes. This is a fixed-allocation limit, not an authorization to grow
archives or alter topology. The complete positive retail witnesses simplify
two larger surfaces in each scene to exact solid colours; they demonstrate the
writer and preservation boundary, not arbitrary photographic-image fidelity.

## PROVED offline

The final acceptance passed **477/477 scenes**, covering **23,838 P8 texture
occurrences**, **43,639 meshes** and **8,392,217 UV vertices**. Every embedded
PNG matches the cached source PNG, and every decoded image matches the source
RGBA hash. An independent source-short/shape-float calculation matches every
exported UV byte. The original geometry buffer is an unchanged prefix.

All 477 helper-format bundles pass the actual Studio no-op importer without
staging an edit. The compiler then preserves each full original SCNE span
byte for byte, including native mip chains, unused palette bytes, compression,
wrapper and opaque tail. **477/477 changed-scene witnesses** also pass: two
large textures per scene, **954 changed texture occurrences**, independently
decoded exact base colours and complete mip chains. Every unselected decoded
byte and opaque tail is retained, and each edited scene fits its retail span
and scratch bounds. No failures remain in the final batches.

The metadata-only receipt is
`docs/mod_editor/nfl2k5_stadium_editor_retail_proof.json` (550,023 bytes), SHA-256
`9d3ba72efbbfe11de88fc4be96541e028a853b5857d09ad05426070db12c0bd5`.
It contains all scene hashes and eight disjoint batch receipts. Batch elapsed
times range from 1,055.85 to 1,113.31 seconds; maximum process RSS is
636,168 KiB (621.3 MiB), below the 2 GiB process limit.

The actual private developer CLI was also exercised through the unified
compiler on `nfl2k5.stadium.o3280.c0005.scene2648.texture0002`: its untouched
908,912-byte SCNE span retained SHA-256
`0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a`.
The temporary span/preview directory was deleted afterward. A separate scan
of every cached scene found no embedded texture without a material user.

Retail input pins were independently streamed, not read as whole packs:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Pack 0 | 193,710,080 | `34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d` |
| Pack 8 | 929,370,112 | `265560a55bebc13e5c8bfbe7770dac2032624946b4767fad72191bb3266aca14` |
| Pack 9 | 634,941,440 | `779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a` |
| Retail XBE | 11,948,032 | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |

Packs 8 and 9 match the existing writer's retail size/hash pins. The resource
inventory is the existing private
`indexes/nfl2k5_resource_chunks_v2.json`; the Stadium cache reports 477 scenes
and 23,838 P8 occurrences. No source pack, stock image, exported model or SCNE
payload is committed. Only algorithms, synthetic fixtures and metadata/hash
receipts are delivered.

## F1 decision and exact research plan

**PROVED:** the existing native evidence tool replays eight pinned retail
function ranges. `docs/mod_editor/nfl2k5_stadium_part_ownership.json` records
the hashes and checks. Node `+0x14` supplies a current matrix for transforming
shape centres; node flags `+0x0C` affect radius scaling, culling bypass and
render suppression. The shape radius is at `+0x48`. Consumers include centre
transform `0x21520`, visibility dispatch `0x215A0`, node relocation `0x21630`,
render-node `0x21860`, shape relocation `0x22F90`, getters `0x23750/0x23760` and
frustum test `0x2ADC0`.

**NOT PROVED:** that one named SCNE shape, one transform record or a zero
selector lane identifies a part with an independently editable runtime matrix.
A name-based node/shape match does not establish pointer ownership. Emitting
those matrices as independent editable part transforms would overstate the
available evidence. No new per-part transform export/import is enabled.

The next F1 work is precisely bounded:

1. Choose an actually selectable stadium family, beginning with the
   o3136/c6 scene rather than locked `s42`. Record its venue selection and all
   day/night/weather variants from the resource inventory. Have Noah confirm
   the scene is loaded for that venue before calling it a visibility witness.
2. Extend the read-only ledger through the existing node/shape relocators.
   Resolve each serialized node's actual shape pointer, transform-table
   references, parent links and selector uses, not just equal names. Hash each
   record and classify zero/one/multiple owners, aliases and native consumers
   across every scene. No writer is admitted at this step.
3. Trace who creates and updates node `+0x14`, when visibility/LOD changes
   select another matrix and how radius scaling reaches `0x215A0`. Establish
   row/column order, local versus world space, parent multiplication order,
   handedness and the unit root from pinned code plus numeric fixtures.
4. For one uniquely owned static part, prove its unchanged matrix export/import
   is byte-identical and that another part's transform, bounds and selectors
   cannot be touched. Refuse shared/animated/selector-driven ownership. Native
   trace and Noah's paired scene observation must agree on that exact part.
5. Only after those ownership gates should a separately authorized transform
   serializer be proposed. Its gate list must include bounds/visibility,
   animation/LOD transitions, exact fixed-span packing, refusal of hierarchy
   changes and an undoable one-part identity contract. Topology and UV writers
   remain separate research tasks. This brief expressly excludes implementing
   those serializers, even if preliminary metadata looks promising.

The old 75-target same-count FLOAT3 position importer is retained unchanged in
scope. Added UV preview attributes do not grant UV/transform write permission.
The original hub memo's linked `docs/research/nfl2k5_stadium_import_xemu_witness.md`
is absent from this lean checkout; no witness claim is inferred from that link.

## F4 workflow and integration boundary

`docs/mod_editor/nfl2k5_stadium_blender_workflow.md` contains the complete
select/export/import/paint/export-textures/import/review/undo/build workflow,
CLI commands, limits and recovery instructions. The owned
`StadiumBlenderPanel` implements that guidance, a helper-save button and action
signals. Offscreen tests exercise its signals and unchanged-import summary.

The live existing facade is wired. The shared `studio_qt.py` is protected, so
inserting the new card, correcting its old “wrote every receipt” wording and
shipping allowlist/runtime/capability/closure updates are concrete instructions
in the new first section of `WIRING.md`. Protected files and the canonical
capability registry remain unchanged. Until Claude refreshes the sealed
provider fingerprints, that provider correctly refuses the modified closure.
This task does not claim a fully integrated packaged release or a new XBE patch.

## Tests and resource discipline

All commands below ran independently as
`QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<filename>.py`, with exit
status zero. **163 tests executed successfully across 15 files**. One NFL
window-test class was skipped precisely because this lean checkout lacks
`reports/assets/nfl2k5_team_select_card_inventory.json`; its two independent
APF checks executed. No actual Blender process was run.

| Filename | Tests run | Result |
| --- | ---: | --- |
| `test_nfl2k5_stadium_studio` | 6 | PASS |
| `test_nfl2k5_stadium_texture_writer` | 9 | PASS |
| `test_nfl2k5_stadium_gltf_export` | 36 | PASS |
| `test_nfl2k5_stadium_editor_roundtrip` | 12 | PASS |
| `test_nfl2k5_stadium_blender` | 11 | PASS, bpy mocked |
| `test_nfl2k5_stadium_blender_panel` | 2 | PASS, Qt offscreen |
| `test_stadium_gltf_roundtrip` | 17 | PASS |
| `test_nfl2k5_stadium_geometry` | 2 | PASS |
| `test_unified_stadium_texture_composition` | 5 | PASS |
| `test_nfl2k5_stadium_cache` | 14 | PASS |
| `test_nfl2k5_stadium_people_categories` | 15 | PASS |
| `test_stadium_viewer` | 3 | PASS |
| `test_stadium_editable_discovery` | 2 | PASS; one evidence-dependent class skipped |
| `test_studio_session` | 18 | PASS |
| `test_studio_facade` | 11 | PASS |

The new tests cover live painted pixels, Blender registration/import/export
with mocked bpy, PNG/ID/path refusal, no-op and ancillary-PNG equivalence,
grouped undo, earlier texture/geometry composition, file/manifest failure
rollback, byte-preserved native mips, compression token filling, source UV
validation and the eight native ownership ranges. Existing standalone test
files received repository path bootstraps where needed for plain Python.

`git diff --check` and Python compilation passed. The capability fragment
passes its JSON Schema, new file references, module-command resolution and
merged registry semantic validation. Full legacy registry file checks still
require developer evidence absent here; protected packaging/runtime closure
checks follow the exact handoff in `WIRING.md`. The developer CLI's `--help`
also exits zero. No XBE owner was added, so this change does not alter either
XBE gate's owner union.

The retail acceptance command was split into eight ordinary Python processes
with `--start 0,60,120,180,240,300,360,420 --limit 60`. These are bounded test
batches, not delegated agents. All used the same final SCNE compiler and UV
algorithm. Each process was measured with `/usr/bin/time -v`. Its command,
scene receipts, source pins and test logs are retained privately in `.scratch/`.
The committed proof combines the complete, disjoint batches in scene order.

Every temporary export/PNG/span lives under `TemporaryDirectory` and is deleted
on normal or exceptional exit. No real disc build or pack copy was needed.
Root free space initially reported 102 GiB. The final byte-count check reports
101,914,587,136 available bytes, above the brief's 100 GB floor (95 GiB in
binary units). No task-owned temporary stadium exports remain. Scratch is
under 1 MiB of small logs and metadata; no disc, archive or
stock artwork. The acceptance did not create a disc or pack copy.
The original image/extraction, private cache, other worktrees and hub are
unchanged. No network, push, GUI display, audio or emulator was used.

## MisterAlex's witness list

1. Record Blender version, Mod Studio revision and canonical scene ID. Import
   o3136/c6 plus a domed/roofed venue with the helper. Check normal metre scale,
   separate named selection objects, upright ads and goal-line text, tiled
   seats/concrete and alpha cutouts. Compare with the supplied source artwork.
2. Paint an unmistakable small patch, keep dimensions, save/reopen the `.blend`
   and export selected objects through the helper. Confirm the saved file
   contains the live unsaved image paint, correct orientation, colour and alpha.
   Use the Studio preview to judge quantization before building.
3. Rename material/object/image names while retaining properties. Confirm the
   same texture ID is targeted. Verify all surfaces sharing that ID change
   together. Make conflicting copies and confirm refusal, without prior edits
   changing. Resize an image and confirm the dimension message.
4. Re-export an untouched scene and reimport into a fresh session. Expect zero
   changed receipts and no undo entry. Reimport a current edited preview and
   expect the same. Import two edits, undo once, and confirm both previous
   states return. Save/reopen the project and confirm the authored images persist.
5. Test helper registration, removal and a second import of the same scene in
   the supported Blender version. Record any reused material/image datablocks.
   This edge is not established by the mocked bpy tests.

## Noah's witness list

1. After protected wiring and closure refresh, make an explicit experimental
   build from a copy of the pinned retail source. Record source/build hashes,
   SCNE IDs, texture IDs, receipt, platform and selected venue. Confirm the
   clean reference game and edited build both load that actually selectable
   venue. Do not treat the locked `s42` family as a Quick Game witness.
2. View the edited field/sign/stand/roof surfaces in play, pause, replay and
   stadium flyover. Check colours, alpha edges and mip transitions near/far;
   every shared user of the changed texture must agree. Record which scene
   variant actually supplied each surface.
3. Leave/re-enter the venue, load another venue and return. Exercise day/night,
   dry/wet and the matching venue variants explicitly. Watch for loading stalls,
   corrupted textures, incorrect bounds, missing surfaces or new memory trouble.
   The token-fill and scratch checks are offline evidence, not a loader witness.
4. Build a project containing a prior texture edit plus a two-texture Blender
   import. Also test the existing bounded geometry-plus-texture combination
   separately. Verify the expected final surfaces and safe refusal if the whole
   scene cannot fit. The source image must remain unchanged.
5. Restore original images/undo, save/reopen, build again and compare the affected
   SCNE span hashes against retail. Untouched imports must remain byte-identical.
   Test the composed project with the desired other patches only after the
   isolated texture build passes. Record observations rather than marking
   unvisited stadiums “witnessed.”

## Delivery

Delivered on `astra/r62-stadium-editor` as a normal Git commit, using explicit
paths for staging and committing. Git metadata was writable, so the bundle
fallback was unnecessary. `ASTRA_BRIEF.md` and `.scratch/` are excluded.
No push. The commit contains code, standalone tests, workflow, native ownership
metadata, complete retail proof and the protected-file handoff. The remaining
release wiring and human witness gates are listed above without claiming them
complete.

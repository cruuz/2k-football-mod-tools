# r62 community stadium Blender add-ons review

2026-09-06. Base `7d46618e477f7feb2b4375d1691f39027eeea519`, branch
`astra/r62-stadium-blender-addons`. **Recommendation: DO NOT SHIP** the submitted Stadium Importer
v0.11.1 and Round-Trip Exporter v0.3.0. **EXPERIMENTAL / UNWITNESSED.**
The default untouched round trip changes geometry, and Models import accepts
that incorrect geometry. No community add-ons or upstream README were copied
into `tools/blender/community/`. No silently patched version is presented as
safe. This completes the review with a release hold, not a release approval.

The delivery contains a reproducible headless proof tool, standalone audit
tests, a metadata-only byte receipt, a short user-guide section and protected
packaging instructions in `WIRING.md`. Existing game writers and protected
files are unchanged. No disc was built or written; no push occurred.

## Inputs and evidence scope

Read `ASTRA_BRIEF.md`, the project index, prior Astra report inventory, RC85
product changelog, `ASTRA_STADIUM_EDITOR_REPORT.md`, the existing Blender
workflow and all three supplied community files. The relevant implementation
is `mod_editor/core/nfl2k5_models.py`, `nfl2k5_stadium_studio.py`,
`tools/nfl_scne_gltf.py` and the locally installed Blender glTF importer.
No online documentation or other worktree was needed.

The exact supplied files remain private inputs under `.scratch/community/`:

| File | SHA-256 |
| --- | --- |
| `NFL_2K5_Stadium_Importer_v0_11_1.py` | `0353398b0962137b101835f8c47874a1f41ba13b1222539a07471d27915f48fe` |
| `NFL_2K5_Stadium_RoundTrip_Exporter_v0_3_0.py` | `d87fdff9bf1fb1135d8d65323d91261bfa5e33e9b9355d3dc4d866efe46a488a` |
| `NFL_2K5_Stadium_Blender_Tools_README.md` | `c52f3e03f274fbf3e018fb3c21fea4a9c7dba2df63c8009383bda4869e8209df` |

**PROVED** below means an executed Blender, Python or static AST check, with
its scope stated. **SOURCE REVIEW / HYPOTHESIS** identifies behavior read from
code that still needs an execution fixture. Nothing was witnessed in game.

## Contract audit

| Assumption | Result and evidence |
| --- | --- |
| Which exporter supplies the return contract? | **PROVED:** Models `export_model` supplies `_NFL_VERTEX_INDEX` FLOAT SCALAR, `_NFL_COLOR` FLOAT VEC4, POSITION FLOAT VEC3 and TEXCOORD_0 FLOAT VEC2. The retail run has these on all 105 meshes. The README's Models > Import return path is the intended target. |
| Stadiums page compatibility | **SOURCE REVIEW:** its cached geometry plus `append_stadium_texcoords` supplies POSITION and UVs, embedded PNGs and texture IDs, but no `_NFL_VERTEX_INDEX` or `_NFL_COLOR`. The common root and textured preview do not make this a Fast Template return contract. Its texture helper and 75-target position importer remain separate. |
| Attribute preservation in Blender | **PROVED in Blender 4.0.2:** all 3,901 separated pieces retained `_NFL_VERTEX_INDEX:POINT:FLOAT` and `_NFL_COLOR:POINT:FLOAT_COLOR`, plus UVMap and the importer UV backup on CORNER. No missing vertex-ID attributes. Installed stock importer `gltf2_blender_mesh.py` explicitly recognizes underscore attributes. Other Blender releases are **HYPOTHESIS**. |
| Units and root detection | **PROVED:** `nfl2k5_units_centimetre_to_metre` is recognized and passes strict scale validation at 0.01. Importer also accepts its root tag; exporter recognizes names, not that tag. Renamed roots, custom scene units and transformed roots require separate tests. Its scale tolerance is 0.0005, not exact identity. |
| Coordinate axes | **PROVED FAIL:** stock Blender converts glTF `(x,y,z)` to `(x,-z,y)`. `_collect_fast_edits` writes Blender-local components directly to glTF. Baseline inversion removes the object frame, not Blender's mesh-coordinate conversion. Normals use the same unconverted frame. |
| UV convention | **PROVED:** Models uses `normshort * scale + offset`, no game-side V flip, REPEAT 10497 on both sampler axes. Blender independently stores V as `float32(1-v)`; the add-on reverses this with `1-v`. That reversal is conceptually required, but cannot restore lost original float bits. The retail no-op changes 5,515 UV rows. Disabling the V conversion would introduce an actual orientation error. |
| Layout arithmetic | **PROVED by retail and synthetic probes:** accessor plus bufferView offsets, dense float SCALAR/VEC2/VEC3/VEC4, and interleaved FLOAT3 stride work; padding is preserved for valid layouts. Retail has dense views with zero accessor offsets and no stride. Sparse and non-FLOAT edits refuse. |
| Layout validation | **PROVED FAIL:** a declared view shorter than the accessor is not rejected; a write can reach neighboring bytes in the BIN. NaN values are accepted; invalid row indices and wrong tuple widths silently skip. **SOURCE REVIEW:** negative indices/offsets, alignment, overlapping views, stride bounds, normalized values, count consistency and aggregate input size are not comprehensively validated. Matrix layout/padding is not a supported editable contract despite entries in the type table. |
| Multiple primitives/accessors | **PROVED:** all primitives within each retail mesh share one attribute map, so the supplied sample fits that assumption. **PROVED FAIL on synthetic input:** with two distinct ID accessors, the nested loops apply every ID map to every semantic accessor and overwrite unrelated rows. Duplicate mesh names and conflicting copied IDs also need rejection instead of dictionary overwrite. |
| Bounds refresh | **PROVED:** both outputs' POSITION and UV min/max match independently decoded rows. Synthetic stride/minmax tests include unchanged rows. Refresh only runs when existing bounds are present, and fast export invokes it only for POSITION/UV. Current color/ID accessors have no bounds. |
| Normals absent from template | **PROVED:** the real stadium has no NORMAL accessors and none are introduced. A synthetic NORMAL edit with no template lane leaves the BIN unchanged. **HYPOTHESIS:** templates with authored normals need a separate fixture; the collector reads geometric `vertex.normal`, not explicitly the imported custom corner normals. Cleanup/splitting and re-normalization can lose their baseline. |
| External BIN | **PROVED:** current Models uses one external BIN, with all 53 PNGs in it; all image/index/ID/color bytes remain identical in the two fast exports. **SOURCE REVIEW:** data-URI/GLB templates are unsupported, external URIs are joined as filesystem paths without confinement or URI decoding, and extra buffers/external images are not safely copied or globally rejected. Only buffer 0 accessors are handled. |
| Missing or conflicting edits | **PROVED FAIL:** strict mode reports success for an unknown source ID and leaves it unchanged. Conflicting UV corners silently choose the first. **SOURCE REVIEW:** conflicting duplicate vertex IDs choose the last collected record, source-group baselines are not compared in the fast path, missing groups are not diagnosed, and the source template has no fingerprint binding to the imported scene. |

The static exporter and Blender implementation evidence comes from local code,
not an inferred compatibility claim about all glTF documents. Models' normal
import is a vertex-fitting writer, not a validator that can infer whether a
user intended to rotate an entire stadium.

## Actual headless round trip

**PROVED:** Blender **4.0.2**, stock glTF importer, both community modules
registered in a fresh disposable process. No user add-on installation or
preferences were modified. This is an actual Blender run, not the stub fallback.
The importer ran its recommended defaults, including individual parts, batch
splitting, connector cleanup, handles, descriptive names and category
collections. Fast Template Export used every default patch checkbox and
strict validation. No crowd override PNG was supplied.

Source: retail extracted `vc_53450030/0` index and its bounded resource spans,
using the existing private resource inventory. Model key **o3136c6**, scene
name `stadium`: **105 meshes, 479 primitives, 17,669 vertices, 53 embedded
images, zero skins**. Imported result: **3,901 parts and 3,901 handles**,
zero split errors and zero handle failures. Cleanup reported zero connector
faces/edges in this sample, so removal of nonzero connectors is not claimed
as a real-stadium witness. Category labels and visible texture orientation
still require visual review.

Original SCNE span SHA-256:
`77ee3d9b2821b39508dbfef75218058de58ed6900d658cc4d7cf5bc9bb1e59ea`.
Original BIN is **1,172,734 bytes**, SHA-256
`1c94101a7b07231382fbd27fc3325b0a2cb62f90eb02de9f689eb3ade7e4aa27`.

| BIN comparison | Changed bytes | Changed POSITION rows / bytes | Changed UV rows / bytes | All other bytes |
| --- | ---: | ---: | ---: | --- |
| Untouched Fast Template vs original | 148,712 | 17,669 / 141,510 | 5,515 / 7,202 | Identical |
| One moved handle vs original | 148,718 | 17,669 / 141,516 | 5,515 / 7,202 | Identical |
| Moved vs untouched Fast Template | 21 | 3 / 21 | 0 / 0 | Identical |

Untouched output BIN SHA-256:
`22ce8b044c0f6e69622b4680030f799ac2d65004fac5478b7e3c245ff82a0ec2`.
Moved output BIN SHA-256:
`8759278d0f539471d259a4552d0a810860d20ec767e94c1ac47a8b1867ecead7`.
Both JSON documents retain all topology, materials, images, nodes and extras;
only buffer URI/length and correct POSITION/UV bounds may differ.

For example, the untouched first `digits2` position goes from
`(-753.9592895507812, 1624, 8650)` to
`(-753.9592895507812, -8650, 1624)`. Fixing the axis permutation alone in the
observed output still leaves **8,885 POSITION rows** different, with maximum
component error **0.0009765625 cm**. Handle reparenting/matrix arithmetic and
unconditional row serialization cannot promise exact no-op bytes. An epsilon
that simply suppresses small changes would also suppress intentional edits.

Moved handle: `H_Field_yardside_G408_P007`, child
`Field_yardside_G408_P007`, original group `group408`, IDs **30, 31, 32**.
Requested Blender world offset: **(1, 2, 3) metres**; measured Z is
2.999999761581421 due to Blender float storage. The glTF offset should be
**(100, 300, -200) cm**. Observed exported offset is
**(100, 200, about 300) cm**, with maximum expected-offset error about
**500 cm**. The three rows and all 21 changed byte offsets are recorded
exactly in the receipt. Isolation passes; axes and template preservation fail.

## Models import acceptance

These are actual `nfl2k5_models.compile_import` calls, with their real fixed
span compressor and scratch validator. No game image writer was invoked.
`changed_bytes` in this API counts differing **decoded SCNE bytes**, not
compressed-span differences or a full disc diff.

| Input | Import settings | Acceptance | `changed_bytes` |
| --- | --- | --- | ---: |
| Original Models export | Defaults; separately UV writes enabled | Unchanged control, no edit | 0 |
| Untouched community output | Defaults, `write_uvs=False` | Accepted incorrect geometry | 141,510 |
| Moved community output | Defaults, `write_uvs=False` | Accepted incorrect geometry | 141,516 |
| Untouched community output | `write_uvs=True` | Refused: needs scratch 114, retail 112; padding 13 | No compiled receipt |
| Moved community output | `write_uvs=True` | Same refusal | No compiled receipt |

Both accepted outputs report **17,669 moved vertices**. No normals, UVs or
colors are written with the default calls. Their compressed streams occupy
879,496 and 879,499 bytes respectively of the 879,504-byte stored body, with
the wrapper unchanged. The rejected calls return no `CompiledModelImport`,
so their `changed_bytes` is explicitly null in the JSON, not invented as zero.

The complete metadata receipt is
[`docs/mod_editor/nfl2k5_stadium_community_addons_proof.json`](docs/mod_editor/nfl2k5_stadium_community_addons_proof.json).
It includes hashes, every changed row and absolute byte range (inclusive),
unattributed-byte checks, Blender diagnostics, motion measurements, exact
commands and both accepted Models receipts. No game BIN, PNG, glTF or SCNE
span is committed.

## Safety review and fix decision

**PROVED, static AST/import/call scan:** neither supplied script has explicit
network clients, shell/process launch, `eval`, `exec`, or arbitrary downloaded
code. Importer direct file opens are reads; its PNG override is a local image
load. This is a bounded review of these scripts, not a security guarantee for
all Blender dependencies or malicious glTF content.

**PROVED, disposable synthetic file tests:** Fast Template Export can
overwrite the original template BIN/glTF even with strict validation. It
opens final destinations directly with `wb`/`w`; a JSON failure leaves the
new BIN behind. An output BIN symlink writes an unrelated file outside the
chosen directory. These tests use tiny temporary sentinels, not user files.
There is no pair-wide rollback, source alias check or preflight of the sibling
BIN. The input BIN is read wholesale through an unscoped `open().read()`;
there is no size cap. Only the small actual stadium was loaded here.

**PROVED, real Blender synthetic scene:** Clear Previous Stadium deletes
untagged user descendants under a recognized root (three objects in the
fixture); it retains an unrelated object and its shared mesh datablock.
**SOURCE REVIEW:** cleanup scans all `bpy.data.objects`, including other
scenes, and happens before stock import succeeds. A failed new import can
therefore leave the old scene cleared. Cleanup also removes loose edges and
isolated vertices, beyond degenerate faces. The legacy exporter can bake
mesh transforms and remove handles in place, changes selection/visibility,
and has weaker restoration after exceptions. Legacy export was not used or
approved as a workaround.

Both `bl_info` dictionaries say `author: OpenAI`. The package was supplied by
a community member using ChatGPT. That metadata is not authorship evidence
or endorsement; any future distributed revision must credit the community
contributor, whose preferred name was not supplied. The originals remain
unchanged so the source hashes identify the reviewed versions.

An axis/name correction is small, but this package also needs a reliable
original-attribute/baseline scheme for lossless untouched rows, correct normal
handling, ID/UV ambiguity checks, bounded accessor validation, template
identity and safe two-file publication. Changing two axis expressions does
not address the measured residual drift or the file hazards. The brief says
not to rewrite the add-ons; therefore **no ms1 copy or version bump was made**.
Do not bundle the importer alone as an implicitly safe round-trip workflow.

## Reproduction and tests

Final command (all source/archive access is read-only):

```sh
blender --version
/usr/bin/time -v python3 tools/nfl_stadium_community_proof.py \
  --addons .scratch/community \
  --index '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --inventory /home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json \
  --output .scratch/community-proof-final.json \
  > .scratch/community-proof-final.log 2>&1
python3 tests/mod_editor/test_nfl2k5_stadium_community_audit.py
python3 tests/mod_editor/test_nfl2k5_models.py
python3 tests/mod_editor/test_nfl2k5_stadium_gltf_export.py
python3 tests/mod_editor/test_nfl2k5_stadium_blender.py
git diff --check
```

The proof tool invokes
`blender -b -noaudio --factory-startup -t 2 --python-exit-code 1 --python tools/nfl_stadium_community_proof.py -- --worker --addons <absolute-input-folder> --folder <TemporaryDirectory>`.
Choose a fresh receipt filename to rerun. Exit zero means the **audit ran**,
not that the add-ons passed their release gates. Modules are registered only
in that disposable process. The first diagnostic run used the same retail
export/defaults and got identical BIN results; Blender initialization logged
a refused PulseAudio wake-up. No playback was requested. The final run forces
the sound system to None with `-noaudio`.

| Standalone test | Result |
| --- | --- |
| `test_nfl2k5_stadium_community_audit.py` | 22 passed, including a real headless scene-cleanup probe |
| `test_nfl2k5_models.py` | 37 run: 26 passed, 11 precise missing-inventory skips |
| `test_nfl2k5_stadium_gltf_export.py` | 36 passed |
| `test_nfl2k5_stadium_blender.py` | 11 passed, existing helper tests use mocked bpy |

**95 passed, 11 skipped.** The new audit tests deliberately reproduce pinned
upstream defects; their passing result does not approve those defects. They
also test the independent byte-accounting oracle, valid strided accessors,
bounds and absent normals. Without the private scripts, their source-bound
classes skip with an exact reason; without Blender, only the scene probe
skips. `NFL2K5_COMMUNITY_ADDONS` supports another private input folder.
The lean command
`NFL2K5_COMMUNITY_ADDONS=/tmp/nfl2k5-community-inputs-not-installed python3 tests/mod_editor/test_nfl2k5_stadium_community_audit.py`
also passed: eight oracle tests, one skipped scene test and one skipped
source-dependent class. Python compilation, module `--help` and
`git diff --check` passed.

## Resource discipline, integration and remaining witnesses

Final run: **7:30.30**, maximum RSS **1,019,028 KiB**, below 2 GiB.
Its metadata receipt is **1,022,074 bytes**, SHA-256
`157bf9a7f27e6e4270d4ef3645b94da36318e4ee330dcbcabd44a3c79871113c`.
The final run reproduces both first-run BIN hashes exactly; the pristine
Models control returns zero changed bytes with UV writes both off and on.
Available root disk space was **104,740,122,624 bytes before** and
**111,098,847,232 bytes after**, above the 100 GB floor.
Both runs use `TemporaryDirectory` for every exported stadium and
automatically delete it on normal or exceptional exit. No disc/pack copies,
whole-disc reads, game writes, GUI display, network calls or emulator were
used. The process limit is respected; the initial run peaked at 1,019,832 KiB
RSS, below 2 GiB, and took 7:34.36. Inputs and other worktrees remain unchanged.

Final cleanup found no remaining `/tmp/nfl2k5-community-*` export directories.
Scratch held 5,052,282 bytes of inputs, logs and metadata before the small Git
fallback was created, well below 200 MB. There are no task-owned exports,
discs or packs over 100 MB.

`WIRING.md` supplies the exact allowlist lines and guide anchor. There are no
dispatcher kwargs, BuildPlan fields, preset options, PATCHES entries, runtime
imports, capability counts, XBE owners or cave allocations to add. Protected
files and release-tag tests are untouched.

**Commit transport:** explicit-path `git add` failed because the worktree's
`index.lock` is on read-only Git metadata. The authorized fallback is
`.scratch/r62-stadium-blender-addons.bundle`, containing a commit on the same
branch name with base `7d46618e477f7feb2b4375d1691f39027eeea519` as its
prerequisite. Git objects/index/refs for that commit live only in a private
scratch repository. The worktree branch itself remains at its original HEAD.
The six deliverable paths are explicitly staged and committed; neither the
brief, supplied add-ons nor scratch is included. No push is performed.

**HYPOTHESIS / future acceptance:** a corrected version must pass exact no-op
BIN preservation, isolated translations in all three axes, handle rotations
and scales, custom normals, UV/color changes, conflicting duplicate IDs and
UV seams, alternate templates, source/output aliases and failed pair writes.
Repeat on multiple stadium families and supported Blender versions, after
saving/reopening the scene and reimporting a second stadium. Do not infer a
general stadium writer from a single scene or from reconstructed topology.

**Noah's witness list, only after a corrected version passes offline gates:**

1. Record Blender/build versions, venue, exact Models key and source/output
   hashes. Compare untouched scale, upright ads, repeat tiling, crowd cutouts,
   named parts and selection handles against the original export.
2. Move one recognizable piece in a selectable venue. Record its three-axis
   offset, exported changed-row receipt and Models receipt; unrelated parts
   and attributes must remain identical before building a private game copy.
3. In game, verify venue loading, flyover, play, pause and replay, near/far
   LOD transitions, day/night/weather variants, exits and reloads. Check
   culling/bounds, linked geometry and collisions separately from appearance.
4. Verify save/reopen, scene undo, refusal recovery and restoration of the
   original model. Keep the original disc and original template unchanged.
   No visibility, collision or loader claim is made by this rejected package.

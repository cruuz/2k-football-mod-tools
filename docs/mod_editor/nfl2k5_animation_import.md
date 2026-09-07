# Animation and limb imports

EXPERIMENTAL / UNWITNESSED. These are offline data edits. Gameplay, contact,
body profiles and transitions still need Noah's witness checks.

## Studio workflow

1. Open Animations and choose a clip. The named skeleton bindings are referee
   `archive:3107/27` and player `archive:3092/163`. Other archive families and
   multi-root/paired clips remain inspection-only in the import workflow.
2. Export glTF and native files into a new folder. Keep the entire folder.
   `animation.gltf` is a baked skeleton preview. Edit rotations in
   `primary.gltf` / `primary.bin`, whose tracks contain the original primary
   channels at native frame times. Keep `animation.native.json` unchanged.
3. Choose the source disc and the edited `primary.gltf`. Select **What would
   change**. The importer checks the sidecar against the source, fixed layout,
   times, counts and unit quaternions; it checks packing and decoded poses at
   frames and intermediate samples with mirror, loop and endpoint cases.
4. Inspect the replacement preview and receipt. **Import to a new copy** only
   becomes available after every check, including the selected disc's archive
   directory and resource bytes, has passed. Choose a new output filename.
   The source is read-only. The output and its `.animation-receipt.json` record
   hashes and every differing byte range. Changed input files require another
   check; existing output files are refused.

The initial glTF contract intentionally freezes node, accessor, buffer, channel
and sampler structure. JSON whitespace/key order may change, quaternion signs
may flip, and the binary rotation values may change. Keep the filename
`primary.gltf`, external buffer `primary.bin`, and the exact native times.
General Blender re-export, node reordering, extra tracks, resampling, changed
counts, GLB, external/data-URI buffers and CUBICSPLINE are not accepted. The
primary file contains channel nodes, not a skinned Blender control rig. The
separate skeleton bake and in-Studio preview show the reconstructed local pose.
Unchanged/sign-equivalent keys retain their original packed words, including
non-largest omitted components. Events, movement, auxiliary data and slack stay.

The two known embedded roots (`xbe:0086dfe0`, `xbe:008528e8`) use the optional
retail executable as their source. Their Import action creates a new `.xbe`,
not a disc. Both roots have pinned complete native spans; writes are confined
to main rotation words and the affected section digest. Their skeleton/football
meaning remains unresolved, so their comparisons show raw channels and sign
mirroring without a proved joint permutation. Install the reviewed XBE copy
through the existing disc workflow before any game witness. The retail `.rdata`
flags are 7 (writable/executable/preload); the editor preserves those flags.

## Coordinated limb and first authored gesture

**Check left forearm +1%** fits the original low and high player body resources
and checks the SKEL member together. It updates local/absolute bind positions,
including all four high forearm twist pivots, deforms the left arm's weighted
geometry, and transforms affected normals. Updated mesh bounds appear in the
receipt. The original conservative position encoding bounds still contain all
edited vertices and are retained to preserve precision elsewhere. No unproved
culling field is rewritten. The low/high bind arrays remain 2,800/6,944 bytes;
the 400-byte SKEL axis array remains byte-identical because this is a length
adjustment with the existing directions. SKEL vectors are separately authored
axes; they must not be replaced by normalized bone endpoints.

The CLI also permits scales 0.98 through 1.02. Each requested scale is compiled
and must fit independently; success of +1% does not guarantee every value fits.
The compressed wrappers, spans and original scratch allowances stay fixed.
The head, accessories, weights, morph records, names and parents are retained.
High derived rotations continue to use the game's existing routines with the
translated pivots. Live proportions, morph appearance and accessory/contact
alignment remain unwitnessed.

**Check new referee gesture** authors an eight-degree left-arm variation in the
existing delay-of-game clip, easing to the original first/last frames. It changes
42 keys in the retail seed without growth. This is a new motion under an existing
identity and selector; it does not add a new animation name, gameplay state,
throw style or paired-action selection path. The existing payload budget is
sufficient, so it uses zero archive growth, hooks or cave bytes.

## Command line

Export remains in `mod_editor.core.nfl2k5_animation`:

```sh
python3 -m mod_editor.core.nfl2k5_animation --index /path/vc_53450030/0 --inventory /path/resources.json export archive:3107/27 --output /path/new-export
```

Check or import the primary-channel glTF into a new disc copy:

```sh
python3 -m mod_editor.core.nfl2k5_animation_import --index /path/vc_53450030/0 --inventory /path/resources.json check archive:3107/27 --gltf /path/new-export/primary.gltf --source /path/source.iso --output /path/new-check.json
python3 -m mod_editor.core.nfl2k5_animation_import --index /path/vc_53450030/0 --inventory /path/resources.json import archive:3107/27 --gltf /path/new-export/primary.gltf --source /path/source.iso --output /path/new-copy.iso
```

For embedded roots add `--xbe /path/retail.xbe`, use the `xbe:` identity, and
pass the executable as `--source`. The result is a new `.xbe`.

```sh
python3 -m mod_editor.core.nfl2k5_animation_import --index /path/vc_53450030/0 --inventory /path/resources.json limb-check --scale 1.01 --source /path/source.iso --output /path/limb-check.json
python3 -m mod_editor.core.nfl2k5_animation_import --index /path/vc_53450030/0 --inventory /path/resources.json limb-import --scale 1.01 --source /path/source.iso --output /path/limb-copy.iso
python3 -m mod_editor.core.nfl2k5_animation_import --index /path/vc_53450030/0 --inventory /path/resources.json variant archive:3107/27 --source /path/source.iso --output /path/gesture-copy.iso
```

Every writer stages a copy, preflights all members before writing, verifies the
result, closes handles, and publishes a new output plus a receipt. It streams
through bounded buffers. The output drive needs room for the copy plus a small margin. No growth writer or
allocator is used here.

Before promising import, use the exact witness list in
`ASTRA_BONE_IMPORT_REPORT.md`. Passing offline comparisons does not establish
continuous interpolation equality or game acceptance.

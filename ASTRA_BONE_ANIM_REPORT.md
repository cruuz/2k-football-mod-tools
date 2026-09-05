# Animations workspace: r61b-bone-anim

2026-09-05. Branch `astra/r61b-bone-anim`, base `e6784e7`.
**EXPERIMENTAL / UNWITNESSED.** No game or console emulator was launched. All
retail reads were read-only; edit experiments were in memory. Qt ran offscreen.
No network, audio, source-disc writes, executable writes, or push was used.

## Delivered

- `mod_editor/core/nfl2k5_animation.py`: separate archive and embedded-root
  catalogues; bounded SMCD/MMCD parsing; exact root timing and metadata;
  native key decoding; local pose sampling; projected skeletons; glTF bundle
  export; strict primary-key preflight; fixed-span SMCD replacement bytes,
  whole-span status/apply checks and exact receipts. A standalone CLI exposes
  `catalog`, `export`, and `check`; it never exposes a game-file write command.
- `mod_editor/core/nfl2k5_animation_math.py`: portable float32-store decoder,
  encoder retaining original omission/sign choices for unchanged keys, the
  recovered fixed-table interpolation model, documented channel maps and
  referee/player derived-joint calculations. This reuses the existing
  recovered math and table, with no runtime C library or research-data import.
- `mod_editor/gui/animations_panel_qt.py`: Animations panel, permanent
  experimental/unwitnessed badge, separate source scopes, name/identity/family
  filter, multi-root part selector, native frame scrubber, front/side 2D
  skeleton projection, native details, export and **What would change**.
  Unknown families show independent rotation-channel axes with an explicit
  explanation. Import is permanently disabled and has no connected writer.
  Background tasks use the established lifetime-safe delivery helper.
- Three standalone unittest files and one synthetic fixture helper. Private
  evidence tests skip precisely when their inputs are absent. Qt tests use
  `QT_QPA_PLATFORM=offscreen`.
- `WIRING.md`: appended Animations handoff while preserving the prior depth-lock
  handoff. It specifies exact Studio registration, allowlist additions, lazy
  runtime import closure, a schema-valid capability row, future import gates,
  and the explicit non-applicability of all executable build/patch fields.

No existing glTF research tool needed modification; those witnesses remain
available with their stricter historical report dependencies. No protected
file, Models panel, other GUI panel, or other feature implementation was edited.

## Scope and decisions

**PROVED:** A fresh `tools/nfl_resource_scan.py` run on the retail extracted
archive found 86,882 resources total. The Animations catalogue reads all 5,198
inventoried animation resources: 4,559 SMCD and 639 MMCD resources, containing
6,068 roots. It records family/namespace or unresolved ownership, native
frames/rate/multiplier/duration, known bone count, packed channels, root flags,
event/trajectory/auxiliary counts, whole-span/body hashes, per-region hashes,
and exact archive location segments. Multi-root children retain their original
16-byte directory records and opaque words.

**PROVED:** The mapped seed resources are:

| Identity | Binding | Native data | Decoded body SHA-256 |
| --- | --- | --- | --- |
| `archive:3107/27` | Referee, map `0x0051d010`, `346/109` ref_low skeleton | 46 frames, 21 packed channels, 25 joints, 15 Hz, 2.9666669368743896 s | `75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f` |
| `archive:3092/163` | Conditional player celebration, map `0x0051cd70`, `3/113` LO_res skeleton | 93 frames, 23 packed channels, 25 joints, 15 Hz, 6.083333492279053 s | `a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52` |

Skeleton names and parents are checked against the documented map order;
translations are decoded from the matching source SCNE. No family is assigned
merely because a clip has 21 or 23 channels. The remaining 5,196 resource
families are unresolved and remain cataloguable/decodable/exportable as raw
primary channels. A named clip search does not establish ordinary locomotion,
quarterback release, or a gameplay selection trigger.

**PROVED:** Embedded scope is deliberately the two header addresses explicitly
identified in the brief's memo: `xbe:0086dfe0` (29 x 23 keys) and
`xbe:008528e8` (27 x 23). Both use absolute XBE pointers. Their bounded original
spans, including intervening bytes, are retained with file/VA coordinates.
Only the complete retail XBE SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` is accepted.
This is not a new embedded-motion census. The memo mentioned four scratch
samples without identifying every header; no extra roots were guessed.
Their football style names and full binding remain unresolved.

**Decision:** The existing-clip authoring interchange for tier 2 groundwork is
`animation.keys.json`, a full frame/channel array of scalar-first native WXYZ
rotations. Only the rotations may change. It is deliberately distinct from the
120 Hz glTF bake, which contains derived local joints and is not a native
master. Arbitrary Blender/glTF ingestion is not implemented or advertised.
The requested constrained native writer is implemented; UI import and all
archive/XISO transport remain unavailable until Claude completes the gates.

## Export and replacement contract

Each new export directory is prepared privately and published with `os.replace`
after all file handles close. Existing destinations refuse. The bundle contains:

- `animation.gltf` and `animation.bin`: normalized XYZW local pose tracks,
  baked at 120 Hz by default, with shortest-path sign continuity. Known
  skeletons have real parent/local-bind offsets converted from cm to m.
  The loop flag and explicit unwrapped endpoint convention are recorded.
- `animation.native.json` (mandatory): original complete bytes in base64;
  wrapper/body hashes and offsets; native words and omission lanes; the
  positive-root sign convention; export sign flips and normalization choices;
  identities, namespace, family/map and map pairs; native header bytes,
  duration/rate/multiplier/sample times and root flags; raw events including
  post-duration events; trajectory shorts/yaw layout; auxiliary records and
  unresolved fourth shorts; opaque fields, directories, nonzero slack and
  per-region hashes; source skeleton metadata and hashes of exported files.
- `animation.keys.json` for SMCD only: strict native primary-key document for
  offline edit checking. MMCD and embedded exports have no key-edit file.
- `README.txt`: plain explanation of the local-pose assumptions and disabled
  import, including the requirement to keep the native sidecar.

`verify_sidecar(document, clip)` compares native bytes and metadata against a
freshly read source clip. Export bundles contain source game data and are local
inspection artifacts, not release content.

`compile_replacement(clip, rotations)` preserves the complete original wrapper
and every byte outside changed main rotation words. It fixes channels, frames,
name/identity, native timing, flags, events, trajectory, auxiliary fields and
slack. Unchanged and sign-equivalent keys reuse their original words, including
the non-largest-omission counterexample `0x0319172a`. Changed words prefer the
original omission when it meets the packing bound; another omission is allowed
when necessary. Edited rotations must be finite and nonzero and fit within
0.35 degrees of packing error. Near-identical normalized components within
2e-7 are treated as unchanged to absorb interchange float noise.

The returned `Replacement` performs no file I/O:

```python
replacement = compile_replacement(clip, rotations)
replacement.status(current_span)       # original / applied / unchanged; foreign raises
new_span, receipt = replacement.apply(current_span)
```

`status` compares the entire wrapper-plus-body against the original or the exact
compiled result. Mixed/foreign input refuses before mutation; reapplying the
compiled result is idempotent. Receipts distinguish changed four-byte key words
from exact differing byte runs and map those runs through potentially split
archive pack segments. No receipt claims that game files were written.
MMCD/paired-action replacement and embedded XBE replacement refuse entirely.
No XBE digest, reservation, or cave allocation is needed for this implementation.

## Validation results

All **28 new tests passed** locally, without skips in the full evidence run:

| Exact command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_animation.py` | 16 passed; final run 0.314 s. Includes synthetic whole-span identity, invalid inputs/structure, omission/sign cases, exact and split-pack receipts, foreign/idempotent behavior, fixed fields/counts, MMCD refusal/preservation, mirror/loop/end and frame/between-frame pose comparisons, export accessors/hashes/sidecars and projection. |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_animations_panel_qt.py` | 7 passed; final run 0.060 s. Includes software painting/scrubbing, source scopes, disabled import, export and no-edit change preview, failure gating, stale-source result rejection and deletion before queued delivery. |
| `NFL2K5_ANIMATION_FULL_CORPUS=1 NFL2K5_ANIMATION_CORPUS_REPORT=.scratch/corpus_results.json python3 tests/mod_editor/test_nfl2k5_animation_retail.py` | 5 passed; final run 173.481 s. Full catalogue/corpus, pinned embedded roots, seed exports and exact edit, and recovered-C comparisons. |

The C comparison compiles only the repository's portable recovered C sources in
a temporary directory. It does not run an emulator or retail executable code.
There were **84 broad synthetic pose comparisons** and **1,144 retail pose
comparisons** across both known families, native frames, half frames, mirror
and loop flag combinations, duration boundaries, multiple loops, and clamped
end time. Maximum observed component difference was **0** in both runs.
This is a bounded host-model result, not an Xbox x87 bit-identity claim.

Full-corpus results:

| Measurement | Result |
| --- | ---: |
| Archive resources / roots | 5,198 / 6,068 |
| Whole wrapper-plus-body bytes preserved | 61,096,560 |
| Decoded body bytes preserved | 60,930,224 |
| SMCD no-edit writer identities | 4,559 / 4,559 |
| MMCD main-word rebuild whole-span identities (writer remains disabled) | 639 / 639 |
| Main / auxiliary words checked | 14,073,985 / 17,311 |
| Total packed words retaining original omission/bytes | 14,091,296 |
| Quaternion slack / nonzero bytes retained | 31,404 / 6,549 |
| Trajectory slack / nonzero bytes retained | 3,428 / 2,190 |
| Roots at 15 Hz / 12 Hz | 6,022 / 46 |
| Events strictly after duration | 143 |
| Events beyond duration plus 20 microseconds | 69 |

The original research count of 69 uses the explicit `duration + 0.00002`
comparison in `tools/nfl_motion_sampler_inventory.py:328`. The first new corpus
assertion counted strictly and found 143. The final test records and verifies
both definitions. No event is discarded or retimed.

**PROVED:** The documented referee one-word edit was reproduced through the
shipping groundwork API: decoded body `+0x214`, `0x1ff80201 -> 0x1ff80202`.
Exactly one byte changes at whole-span `+0x234`, pack `4` offset
`25875456 + 0x234`. All non-key bytes retain identity.

Additional checks:

- Fresh resource index:
  `python3 tools/nfl_resource_scan.py '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --json .scratch/resource_inventory.json`.
  Passed; 86,882 records, including the full animation set.
- `python3 .scratch/runtime_smoke.py`: copied the existing release allowlist
  plus the proposed animation additions into a temporary isolated stage;
  imported the core/panel and all lazy helpers and constructed the offscreen
  panel with `python3 -I`. Passed. An initial intentionally minimal stage
  omitted existing package-level controller dependencies; copying the existing
  release closure resolved that staging omission without product changes.
- The proposed capability JSON in `WIRING.md` was validated against the current
  `registry.schema.json` capability definition using `jsonschema`. Passed.
- `python3 -m compileall -q` over the three implementation files and four new
  test/helper files: passed. `git diff --check`: passed.
- The real referee panel at native frame 21 was rendered and inspected entirely
  offscreen (`.scratch/animation-panel.png`); skeleton, frame label, metadata
  and disabled import are visible. This is not an interactive GUI or gameplay
  witness.

### Pre-existing global guard failures

These guards were also run; they are **not green**:

- `python3 tests/mod_editor/test_xbe_patch_memory_writes.py`: four independent
  section tests passed, but `PatchWriteTests.setUpClass` errored.
- `python3 tests/mod_editor/test_xbe_patch_cave_references.py`:
  `CaveReferenceTests.setUpClass` errored before its tests ran.

Both failures occur at `nfl2k5_depth_locks.apply` with
`DepthLockError: depth locks are foreign; refusing: {'status': 'foreign',
'reason': 'unknown bench promotion call sites'}`.

A clean `git archive HEAD mod_editor tools data tests` snapshot was extracted
inside `.scratch/baseline`, and both standalone commands were run there. The
same setup errors reproduced (memory: 4 tests, 1 setup error; cave: 0 tests,
1 setup error). This establishes that the failure predates these changes.
Neither setup imports Animations. The new feature has no XBE owner to add.
The unrelated patch and protected orchestrators were left untouched; the
separate repair is documented in `WIRING.md`.

## Noah's witness plan before Claude enables import

These are required future observations, **none completed here**. Record source
and output hashes, chosen clip, changed keys, trigger used, result, and video
or screenshots for each check. Use a disposable future output copy only after
Claude has reviewed and wired a transactional archive transport and restored
the existing global XBE guards.

1. In the wired Studio, open the retail source and verify Animations appears
   with its badge. Confirm the two source scopes stay separate; search and
   select referee `3107/27` and diagnostic player `3092/163`. Scrub first,
   middle and last native frames, switch front/side, inspect events and native
   duration, and export each bundle. Confirm the game source hashes do not
   change. Select an unknown family and an MMCD child; confirm their limits
   remain explicit and import stays disabled.
2. Open the glTF bundles in the intended Blender/glTF viewer. Verify local
   skeleton scale, joint order, arm/hand behavior and animation playback across
   the clip. Keep the native sidecar. The actor's world path is intentionally
   absent; do not interpret the static root as the game's live movement.
3. Feed untouched `animation.keys.json` back into What would change. Require
   zero changed keys and bytes. Make one small primary-channel edit and require
   exactly the expected joints/keys and byte ranges, with events, movement and
   timing retained. Attempt a changed identity/frame count/duration and a
   mismatched source; each must refuse and leave import disabled.
4. After a separately reviewed future transport exists, build two disposable
   comparisons: unchanged native round trip and a clear, modest referee key
   edit. Compare actual selection and playback against retail from start
   through transitions, mirrored left/right use, looping or final stop, and
   replay. Inspect both referee LODs and hands. The static one-byte proof is
   not acceptance of a visibly useful edit.
5. Establish the real gameplay trigger for `ANM_CELEBRATE_USER_34` before
   claiming a player witness. Compare the same cases at both player LODs,
   different body profiles, replay and camera distance. Check shoulder pads,
   head, hands, equipment, planted feet and blending with preceding/following
   clips. The low-body diagnostic does not validate the high-body/proportion
   stages or event selection.
6. For any later throw, tackle or paired-action experiment, first prove its
   selector and both actors' ownership. Then check release/contact timing,
   hand-to-ball and player contact, trajectory integration and replay. Neither
   named search results nor the MMCD inspector authorize paired-action edits.
7. Keep import disabled until the byte/source gates, same-skeleton comparisons,
   exact output-copy transport, restored global guard tests, and the relevant
   game observations are recorded and reviewed by Claude. Enabling a button
   or changing the constant is not completion of those gates.

## Known gaps and evidence limits

**HYPOTHESIS / unproved:** gameplay acceptance, actual selected player state,
external actor root, player proportions and high-body postprocessing, collision
and contact behavior, arbitrary family bindings, complete ordinary locomotion
or release-style catalogue, and continuous glTF-vs-native interpolation error.
The glTF bake uses standard spherical interpolation between samples and is not
an exact native timing/interpolator representation; no continuous error bound
is asserted. Skeleton export here is an animated joint hierarchy, not a new
mesh/skin/body-set exporter. Existing Models/glTF tools remain separate.

No arbitrary glTF import, new clip identity, new frame/channel count, new bone,
bone-length editing, MMCD authoring, embedded-root writer, archive relocation,
XBE hook, or cave allocation is claimed. These are outside the requested
constrained writer and the documented first-tier inspection contract.
Protected Studio/release registration is intentionally handed to Claude as
requested, so this branch does not itself add a visible Studio navigation item.

All disposable native exports, retail catalogues, numerical logs, rendered
images and the clean baseline snapshot remain under `.scratch/` and are not
staged. `ASTRA_BRIEF.md` is not staged. Commit paths are explicit; no push.

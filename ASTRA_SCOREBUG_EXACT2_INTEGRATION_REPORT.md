# Exact scorebug integration on b167472

**EXPERIMENTAL / UNWITNESSED.** Job A of `ASTRA_BRIEF.md` merges the reviewed
exact-v1 change onto camera v2, MyCareer v2, kickoff v3 and the v10 template
stack. The default `scorebug` path is `espn-broadcast-exact-v1`. Supplying
`scorebug_folder` selects `espn-reference-v10`, including its native fonts,
scene, palette compiler, source snapshot and transaction receipts. No runtime
allocation, hook instruction, camera, MyCareer or kickoff implementation is
changed by this integration. The runtime resource version follows exact-v1.

PROVED: the explicit shipped template produces the exact pre-integration
XBE SHA-256 `0d0eee5163c1d5edbc41a8a0a522f3c55d74e9c5699f078aab37bd9e01b8d23f`,
scene span `8bf58e95bdc4ddbfe627ee705165f7a639d5ba033dc3d6c9732f622ef3e364f2`,
and atlas span `a208b56329eec1dc285dfc8f04dcf66883b62d502c549ed70583d2fb7b0b1609`.
The default independently reproduces exact-v1's resource pins. Both scenes
keep their entire fixed-size wrappers, including `+0x14 = 16`. Native
in-place decompression, receipts, replay and transaction rollback are tested.

`atlas`, `mesh`, `stage_binding_scene` and `preview_data` accept the folder
keyword. A folder binding scene is the v10 static mesh; the incompatible
128x32 exact runtime panels are never bound to a folder's 64x64 packing.
The existing historical staging helpers remain explicitly named `_v8`.
`template_uv`, `compile_folder`, the template assets and release catalog keep
their landed contracts. Projection accepts both scenes; the public CLI uses
`--folder` for the v10 proof and the exact comparator otherwise.

Read-only XBE and static resource/image readers recognize both complete
shipped identities. An explicit folder is required to recognize custom art.
Writers select one version and refuse a different already-installed version.
Version checking considers the union of owned fields, so exact-only font,
label and play-clock fields must be retail in a v10 image. All eight binary
scene/atlas/XBE combinations are tested: only the two coherent combinations
pass. Historical v8/v9 bytes remain foreign. Preview parsing also checks
both specific scene pins; it never accepts arbitrary SCNE bytes.

The brief asks both for a changed default and unchanged v10 tests. Two
existing template tests implicitly selected the old default; their calls
now explicitly supply their existing folder, with all assertions retained.
The complete landed v10 ingestion and projection assertions are retained in
`test_nfl2k5_scorebug_v10_ingame.py` and `_v10_projection.py`, with explicit
folder calls. Historical staging checks still select their historical helper.
The original suite filenames cover exact-v1, and the new versions suite
checks independent landed hashes and cross-version refusal. No failure was
turned into a skip. Historical negative controls keep their original v10
rails and unchanged containment predicate; using the narrower exact rails
had hidden their old score-height failure and was corrected.

The new version test first found a float32 expectation error in its own
anchor assertion, then exposed the missing v10 scene pin in preview parsing.
Both are corrected. Validation details below retain those development
failures separately from their successful final checks.

The prior exact report and iterations 00..25 are preserved as the starting
point for Job B. Their palette plateau is not global visual convergence.
The font, rim, radius, separator, lettering, logo, possession and crowding
residuals, and the six-profile freeze matrix, remain open at this checkpoint.
Native CPU fixtures and software rasters are not gameplay witnesses. Noah's
witness list remains in `ASTRA_SCOREBUG_EXACT_REPORT.md`; no freeze fix,
1:1 match or preset promotion is claimed here.

All protected changes are specified at the top of `WIRING.md`: the exact
module allowlist line, runtime import, two shared help strings, explicit
Build folder override help, and manifest/source-identity regeneration.
Existing dispatcher tuples, kwargs, four status dictionaries, presets,
BuildPlan fields, PATCHES/NEEDS_IMAGE and capability behavior are recorded.
No protected file was edited. No push, network, emulator, GUI display or
audio was used. Bounded native CPU execution is the only execution of game
instructions. No disc or pack copy was made; temporary fixtures live under
`.scratch/tmp` and are removed on exit. A source review ledger covers the
prior ASTRA reports and the RC85 baseline in scratch.

## Validation and delivery

Results and hashes are in `docs/scorebug_ingame/exact/integration_validation.json`
and `integration_pins.json`. Both XBE gates compose the complete current
owner union in forward/reverse orders and both allocator configurations.
The integration commit uses explicit paths and excludes the brief and
scratch. `.scratch/integration.bundle` contains every commit since b167472;
`.scratch/INTEGRATION_DONE` identifies the commit and handoff. Job B continues
from this committed checkpoint without changing the v10 template contract.

Final Job A validation: **307 passed, 7 skipped, zero failures across 16 standalone suites**. Peak measured RSS: 516,692 KiB. Root free space: 102,138,925,056 bytes. `git diff --check` passes. Shared Git staging refused index.lock with a read-only filesystem error; the authorized isolated-metadata commit and bundle fallback is used. Nothing is pushed.

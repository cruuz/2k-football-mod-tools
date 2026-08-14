# Handoff: the update after Beta 42

**Date:** 2026-08-14
**Branch:** `cursor/ship-beta-38` (name is stale; it carries beta-43)
**Shipped:** `beta-43` = 2K5 `v1.0-RC66` / APF `0.1.0-alpha.75`
**Previous:** `beta-42` = 2K5 `v1.0-RC65` / APF `0.1.0-alpha.74`, at `0d0f0d3`

All four investigations are finished, every blocker they raised is closed, and
the local suite is **233 pass / 0 fail / 0 skip**. What remains open is listed
under "Still open" at the end, and none of it blocked this release.

---

## What this session did

### 1. The import preflight is finished and wired

`24d4ad0` left `mod_editor/core/nfl2k5_import_preflight.py` with no caller. It
now has one.

- **"Check My Images"** sits directly above Build in the 2K5 footer, runs through
  `_start_task` with progress off the UI thread, and names its own blocker when
  disabled (never silent-gray). The slow ladder runs **outside** the facade lock;
  only the snapshot is taken under it.
- **A 7x wrong contract was found while wiring it.** `sleeve` was modelled as
  512x256 / 6 mips like the torso. The real sleeve slot is **128x128, 5 mips,
  with a 64-byte gap between the clean and mud palettes**. Every sleeve
  prediction would have been confidently wrong -- the exact failure the module's
  own docstring promises never to make. `CONTRACTS` is now **derived** from the
  four importers with an import-time cross-check against the decoded size each
  importer refuses to deviate from.
- **Tests: 4 minutes -> 17 seconds**, by shrinking the *contract*, not the source
  PNG (the mip chain is the cost, so a smaller input would have done nothing).
  The real contracts are pinned separately against the importers.
- The macOS reporter's open issue is now in the torso/sleeve/pants copy: do not
  paint numbers into the jersey, 2K5 draws them from separate digit textures
  (Jersey/Arm 64x64, Helmet 32x32, Nameplate 1024x32) and they double up.
- The nameplate authoring copy said **32x1024 vertical**. It is 1024x32
  horizontal -- the pre-fix transposed value from a TXTR descriptor bug the
  decoder fixed long ago, still live in three user-facing places. Fixed and
  pinned.

New file `tests/mod_editor/test_2k5_check_my_images.py` (21 tests) pins the whole
path: button -> handler -> facade -> session -> predictor, plus the dialog copy
and the disabled-state reasons.

### 2. Franchise CPU draft bug -- ROOT CAUSE PROVED, and it is 2K5-only

Landed as row **G15** in `docs/product/APF_GAMEPLAY_BUG_MAP.md`.

Two `jne` gates on the same 0-based round counter `DAT_00E3C0A8`:

- `FUN_0031DEA0 @ 0x0031E012` (bytes `75 17`) computes the roster-need and
  team-quality terms and then **overwrites them** at `0x0031E05E` with a raw
  table constant. Every one of the 32 teams therefore gets an identical board.
- `FUN_0031E0F0 @ 0x0031E170` (bytes `75 60`) reads only `array[0]/[1]/[2]` in
  round 1; the `inc ebx` at `0x0031E1DE` exists only on the round>=2 path.

Net: **picks 1-5 can only take QB/HB/DE, picks 6-32 only DE/HB/T -- 4 of 17
positions, 13 unreachable.** It also leaks into the human's *Suggested Picks*,
the round-1 mock board, and any team whose 30-second clock expires. **APF has no
rookie draft at all** (clean negative, proved by string absence).

The fix surface is the signed XBE. No roster, save, draft-class or slider edit
can change it, because in round 1 the builder never reads roster counts.

Also promoted out of that row into the map's **Honesty** section, because it
invalidates a class of earlier conclusions: **"zero references" from the function
ledger is not evidence.** Ghidra truncated functions opening
`mflr r12; bl __savegprlr`, so 6,827 of 21,347 APF ledger rows (32%) are recorded
as size 8. Two conclusions already overturned: the fantasy priority table
`0x820F4B70` is *not* an orphan, and 2K5's `FUN_0036F830` is not virtual-dispatched.

### 3. Camera -- mapped from zero on both products

Landed as `docs/product/CAMERA_MAP.md`, plus a machine-readable companion that
ships in beta-43: `tools/camera_options_audit.py` re-derives the whole surface
from both executables into
`reports/gameplay_tuning/camera_options_audit.json`,
`mod_editor/core/camera_inspection.py` projects it read-only, and it is reachable
as `python3 -m mod_editor --inspect-camera-options nfl2k5|apf2k8`.
`tools/validate_camera_options_audit.sh` regenerates the audit, requires byte
identity, and asserts that no raw address and no writer ever reach a user.
Verdict: **partially proved with a named boundary** -- the map is proved, the
writer is blocked.

Highlights: 2K5 row table `0x0052B700` (7 rows, stride 0x34, same shape as the 21
sliders); APF `0x84E40940` (9 rows, stride 0x60, including a **Camera Pitch** axis
2K5 lacks); the Custom gate; the proved polar solver; and the save layout
(`SAVEGAME.DAT` +0x70..0x88, derived as `global_VA - 0x00E5FF80`).

Two things to carry forward carefully:

- **2K5 has exactly six presets.** An early reading of mine claimed
  `1st Person`/`Broadcast` were hidden presets. That is **wrong** and the doc
  records why: `.rdata` there is a run of adjacent enum label tables and
  `0x004F25D4` starts a *different* enum, almost certainly the replay camera.
- **The genuine hidden-preset win is APF-only:** index 5 `Blimp`, block
  `0x84E13340`, eye (0, 3750, -20), 17/17 slots authored -- geometry that matches
  its own name. Unreachable behind three immediates that never read `maximum()`:
  `0x84A15D00`, `0x84A15D5C`, `0x84A15540`. Safe ceiling is index 5.
- **Flat negative worth keeping:** the gameplay camera has no asset-side
  representation on either product. All 3,744 2K5 and 730 APF SCNE camera records
  are intro/cutscene/UI; zero stadium scenes contain one. No archive-only camera
  mod is possible.

### 4. Catching slider above 100 -- REFUSE, with the reasoning

On 2K5 the slider is genuinely **MEANINGFUL** above 1.0: in `FUN_00232200` the
S terms cancel in the denominator (`WA+WD = 2.5 + cA + cB`), so catch probability
is exactly linear in S and 120 is worth roughly +2 to +4 points. It still refuses:

1. **It cannot be written.** The 736-byte settings record is covered by a 20-byte
   HMAC-SHA1 in the sibling `EXTRA`; the check at `0x0004D520` is exact and a
   mismatch aborts the load with status `0x1A`.
2. **One button press destroys it.** The increment callback at `0x0014AB50`
   *snaps* anything above 0.975 to exactly `0x3F800000`. The decrement has no
   upper bound, so 120 survives "left" and dies on "right".
3. **It does not generalise.** Fumble **saturates** exactly, Interception
   **inverts** (used as `1.0 - x`), Fatigue is a **boolean** already off at 100.

APF is **UNPROVED**: the live bridge was found this session (`0x847C69A0` ->
cache `0x84D754B0` -> indexed getter `0x847C6A18`, 31 gameplay sites), which
**refutes** the earlier "APF sliders are inert" finding -- do not build on that.
None of the 31 sites selects the Catching slot with a constant.

For G9: the slider-to-code binding now exists end to end on both products, and
the APF candidate set is an enumerable 31 sites. G9's row text stands; add that
note.

### 5. A shipped, user-facing bug found and fixed end to end

`tools/nfl2k5_xbox_save_inventory.py::SLIDER_LAYOUT` built both slider vectors in
**menu display order**. The save is a flat memcpy of the RAM struct, so the
vectors are in **address order**, where Catching is *last*, not fourth. The file's
own `EXPECTED_GLOBALS` proves it. Twelve of the eighteen vector slots were
therefore published under their neighbour's name, and that flowed through
`gameplay_inspection.py` into the public inspector.

Fixed by **deriving** the order from `EXPECTED_GLOBALS`, and the report was
regenerated from the real fixture. The regenerated file is the same 31,477 bytes;
only the 36 label/order/index fields changed, with every container hash and every
slider *value* byte-identical. Four checks that asserted the bug were corrected:
`semantic_index == 8`, `"Human Fatigue"` as the last row, and `franchise1 == 0.35`
in both a test and a validator's inline script. **The real value is 1.0** -- that
fixture's Human Catching is maxed, and the inspector reported it as 0.35 under
the wrong name.

A full suite run then caught one more downstream artifact:
`mod_editor/data/nfl2k5_gameplay_inspection.v1.json`, the shipped product
snapshot that `facade._verified_gameplay_snapshot()` compares against the live
core inspection. Regenerated deterministically from the four `inspect_*` calls --
14 values moved to their correct labels plus two source-report hashes, size
unchanged at 22,874 -- and `_GAMEPLAY_SNAPSHOT_SHA256` repinned. Worth knowing
that this snapshot exists and self-verifies: any future change to the core
inspection output must regenerate it or the panel raises
"Gameplay product snapshot no longer matches the proved core inspection."

The APF audit carries the matching bug and is **not** yet fixed: Human Catching is
blob element 9 (byte 0x24) and CPU Catching element 18 (byte 0x48), not 4 and 13.
`element = (global - 0x84F3F99C)/4`. A writer built on the audit's indices writes
Coverage while claiming Catching.

### 6. The test harness was hiding red

`tests/conftest.py` reclassifies a FAILED test as SKIPPED when the failure message
names an absent gitignored tree. Six of those trees are bare English words:
`build`, `assets`, `research`, `extracted`, `artifacts`, `docs/updates`. A genuine
`AssertionError` of mine reading "... decided at build time" was reported as
`Skipped: game data not present: build`.

Fixed: matching is now path-shaped (`_names_a_path`) -- a single-segment name only
counts when a separator follows it, a multi-segment one at a word boundary, and a
*preceding* separator stays allowed because the gitignore pattern `research/` also
matches `docs/research/`. Measured across 300 files before changing anything: 245
masked failures, of which 240 still mask under the new rule. Five new regression
tests added.

---

## The fixture question is settled

`~/.var/app/app.xemu.xemu/data/xemu/xemu/xbox_hdd.qcow2` (1.77 GB) exists and holds
a **pre-draft** Franchise1 save -- 32 teams at 54-61 players, a 377-player pool
with nothing taken -- whose hash matches the one already recorded in
`reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json`. It is the Flatpak path,
which is why earlier checks under `~/.local/share/xemu` came up empty.

The pinned `xemu-hdd-readonly.raw` is gone, but it can be reproduced:
`qemu-img convert -f qcow2 -O raw` yields a sparse 8 GB image (946 MB actual). One
is kept at `artifacts/xemu-hdd-from-qcow2.raw` (gitignored). Note the tool refuses
multi-link inputs, so the XBE and ledger must be copied with
`cp --no-preserve=links` first.

That single file serves the draft repro, the camera save layout, and the slider
delivery test. `scope.save_or_profile_fixture_supplied: false` in
`gameplay_tuning_ai_draft_audit.json` is out of date.

---

## The blockers are closed

### B1/B2 -- the SCNE transform stride, and why the catalog would not regenerate

Both are fixed and shipped in beta-43.

`apf_scene.MATRIX_SIZE` is now **0x90 (144)**, not 0x40. Provable two ways:
structurally (`node_start + 0xB0*count == matrix_start` and
`next_table - matrix_start == 144*count`, exact for all seven scorebug SCNEs and
the stadium) and from code (two unrelated functions walk it with
`addi r10,r10,144` at `0x84ABE524` and `0x8472A358`, reaching the transform via a
pointer at record+0x74). Measured after the fix: `matrix_nonfinite` is 0 and the
PORTME is gone on all eight files, with `m[15] == 1.0` on all 96 records. The old
"2 non-finite components" note was bytes +0x44/+0x64 of a record -- a node-name
CRC-32 that reads as a signalling NaN at the wrong stride. The stadium catalog's
`matrix_table` moved from 5,696 bytes (89x64, 44.4% coverage) to **12,816**
(89x144).

The regeneration blocker was **not** a regression, which is worth recording
because the first diagnosis said it was. `compress_h7a` is byte-identical to the
commit that generated the catalog, `decompress_h7a`/`decode_block`/`parse_iff`
are unchanged, and the disc hashes still match the catalog's own pins exactly.
The real cause: **greedy is 2,599 bytes worse than retail on that block before
any edit**, so it could never have produced the recorded 659-byte growth -- the
generator had simply always called the wrong encoder for a slot with 2,026 bytes
of headroom. It now uses `apf_inner.encode_h7a_preserving_tokens`, which is pure
Python (the optimal ELF is smaller still at 3,279,318 but is gated to Linux
x86_64, which would make the catalog reproducible on one platform only).

Because the encoder changed, the fit witness moved -- and it moved the safe way:
growth 659 -> **59**, slack 1,367 -> **1,967**. `validate_document`'s pinned
constant moved with it. Nine pins of the catalog identity across seven files, the
recipe schema identity, and the conformance spec pin were all updated; every
stadium and scene test is back to its exact pre-change baseline and
`validate_apf_stadium_static_target_catalog.sh` now **passes**, which it did not
before.

### B3 -- the checkout was incomplete, and is now complete

The 12 "lean checkout" skips and the capability-registry failure were both just
absent local data. All of it was still on the old repo tree at
`/media/noah/Storage/for codex 1.0`: 235 `docs/research/` files (the registry
references 72 of them), 422 `reports/assets/` files, plus `reports/asset_samples`,
`manifests`, `headers`, `cut_content`, `static_recomp`, `cross_title`, the
`tools/vendor` build, and the 2.4 GB `assets/` tree. All are gitignored, so
restoring them changes nothing that gets committed.

**The suite went from 220 pass / 1 fail / 12 skip to 233 pass / 0 fail /
0 skip.** If a future checkout looks broken in this shape, look for missing
gitignored derived data before looking for a bug.

Two things to know when regenerating anything from the disc:

* Several tools refuse **multi-link** inputs, so stage the XBE and the function
  ledger with `cp --no-preserve=links` first.
* Do **not** leave a symlink at `extracted/`. It is not covered by the
  `extracted/` gitignore rule (that pattern matches directories), and the stadium
  writers deliberately refuse a game path containing a symlink, so it turns
  passing tests red. Point tools at the real path with `--game-dir` instead.

## Still open

None of this blocked beta-43. Each is recorded with enough detail to start from.

1. **Camera T1 -- is the 2K5 `EXTRA` signature roamable?** This is the single
   question that decides whether *any* 2K5 save writer is ever possible, for the
   camera and for the sliders both. `XCalculateSignature(flags=0)` skips
   `XboxHDKey` (`0x0001FBD2`), so the key is `XboxSignatureKey` and is in
   principle console-independent -- but that is an inference, not a measurement.
   **The measurement:** produce the same 736-byte `SAVEGAME.DAT` on two different
   consoles or xemu instances and compare the two 20-byte `EXTRA` blobs. Identical
   means content-only and roamable, and a writer becomes possible. Different means
   console-bound, and no offline 2K5 save writer will ever ship.
2. **Camera T2 -- does the load path re-clamp?** The save provably *contains*
   non-default camera values. If the loader is a flat copy, an out-of-range value
   written into a save survives into the game with no executable patch at all,
   which would change the whole product. Trace the deserializer from
   `container_filename_dispatch 0x0004B1F0` back to its buffer producer; an xref
   on `0x00E5FF80` fails because 400+ generic settings sites hit it.
3. **The APF Catching consumer.** The live slider bridge is now mapped end to end
   (`0x847C69A0` -> cache `0x84D754B0` -> indexed getter `0x847C6A18`, 31 gameplay
   call sites), which refuted the earlier "APF sliders are inert" reading. None of
   those 31 sites selects the Catching slot with a constant. One computed site,
   `0x84830BA4`, resolves to slot 4 when `r5 == 3` and feeds
   `fmadds f29, f1, [0x82006904], [0x820036EC]` -- linear and unclamped at that
   instruction. Tracing `f29` to its branch closes this.
4. **Scorebug geometry.** Three of the seven APF components already satisfy the
   shipped stadium catalog predicate unmodified -- inner 106 `scorebug_bottombar`
   (46/46 nodes), 156 `scorebug_team_logos` (4/4), 250 `scorebug_messages` (2/2),
   for 393 vertices and 4,716 authorized POSITION0 lane bytes. The other four are
   disqualified for a real reason: every node carries `BLENDINDICES0` at offset 32
   of a 36-byte stride. The container work is enumerable rather than novel, and
   the pure-Python token-preserving encoder now proved on the stadium removes the
   platform restriction that would otherwise have applied. What is *not* proved is
   the transform chain -- whether the runtime applies hierarchy record 0, the
   per-node matrix, or neither -- and nothing should move a scorebug pixel until
   it is.
5. **G9 (offensive false starts).** Its wall was "no slider-to-code binding". That
   binding now exists on both products, and the APF candidate set is an enumerable
   31 sites. If the false-start code reads a slider at all it is in that list; if
   it is not, G9 must be attacked from the penalty code inward -- which is now a
   decision that can be *made* rather than deferred.
6. **The draft fix itself.** G15's root cause is proved to the byte, but every fix
   surface is inside the signed XBE, and this project treats emulator-only
   executable patches as unsafe/deferred. The reproduction fixture exists locally
   (see "The fixture question is settled"), so an emulator witness is now cheap to
   obtain; that is the next honest step, not a patch.

## Non-negotiables (unchanged)

- **Three OS.** CI covers all three but only runs on `main` and PRs -- a branch
  push runs nothing. Verify locally and say so.
- **`python3 packaging/repin.py`** after touching `studio/session.py`,
  `studio/facade.py`, `core/providers.py`, or any `tools/` writer. Done for
  everything in this session's tree.
- **Both release gates** on a staged tree, both products, before any release.
- **Never claim runtime behaviour without a witness.**

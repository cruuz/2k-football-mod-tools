# Job b75-x1: the in-game Edit Player only offers the elbow pads a player already has

Branch `job/b75-x1` off the beta 74 commit `56b537342`. Research first, then a bounded patch.
Nothing in this report is a witnessed in-game result; X_Ray witnesses.

## The report

X_Ray, #2k5-ideas 2026-09-20 7:51 AM, ESPN NFL 2K5, the GAME's Edit Player screen:

> "If a player doesn't automatically have these equipment options assigned to them in game
> you can't add them because they are just not available. Or if they do have them on a
> player in-game and you toggle to another piece of equipment the missing equipment options
> (High elbow and Turf) disappear and are not able to be selected."

Beta 74 fixed the STUDIO's list (`ELBOWS`, sixteen entries, in
`mod_editor/core/nfl2k5_roster_records.py`, pinned by
`tests/mod_editor/test_b74_equipment_enums_match_xbe.py`). This job is the game's own screen.

## What kind of gate it is

**A cap constant, not per-player data.** Two immediates forward and two more backward, in two
handler functions that every Edit Player and Create Player screen shares. No allowed set is
read from the player record, no table of per-slot counts is indexed, and nothing else in the
executable clamps the field.

## The site

The Edit Player equipment page is a list of row descriptors. Create Player (row list
`.rdata 0x5672A0`), Edit Player for created-face players (`0x5674F0`) and Edit Player for
real-face players (`0x567740`) all point at the same two descriptors:

| row | descriptor | label getter (+0x08) | next (+0x20) | prev (+0x38) | field |
| --- | --- | --- | --- | --- | --- |
| Left Elbow Pad | `0x563520` | `0x3451F0` | `0x345210` | `0x345250` | bits 22..25 of `[rec+0x1C]` |
| Right Elbow Pad | `0x5635D0` | `0x3452A0` | `0x3452C0` | `0x345300` | bits 26..29 of `[rec+0x1C]` |

Both getters index the sixteen-entry option list at `.rdata 0x555C78` with the raw stored
value, which is why a player who already carries White Turf or High Team reads back correctly
(the list at `0x555C78` is `None, White, Black, White/Black Stripe, Black/White Stripe,
Black/Team Stripe, Team, White/Team Stripe, Elastic, Neoprene, White Turf, Black Turf, Taped,
High White, High Black, High Team` - exactly the beta 74 `ELBOWS` order, verified against the
executable in `RetailTests.test_the_option_list_has_sixteen_labels_in_the_studio_order`).

Left elbow label getter, `0x3451F0`:

```
003451f0  a1 14 8b cb 00        mov  eax, [0xcb8b14]       ; the live edit-player record
003451f5  8b 48 1c              mov  ecx, [eax+0x1c]
003451f8  c1 e9 16              shr  ecx, 0x16
003451fb  83 e1 0f              and  ecx, 0xf              ; the whole 0..15 range is read
003451fe  8b 04 8d 78 5c 55 00  mov  eax, [ecx*4 + 0x555c78]
00345205  c3                    ret
```

The forward handler is the gate. Left elbow, `0x345210`:

```
00345210  a1 14 8b cb 00        mov  eax, [0xcb8b14]
00345215  c7 05 20 88 cb 00 ..  mov  dword [0xcb8820], 1   ; the screen's dirty flag
0034521f  8b 48 1c              mov  ecx, [eax+0x1c]
00345222  c1 e9 16              shr  ecx, 0x16
00345225  8b d1                 mov  edx, ecx
00345227  83 e2 0f              and  edx, 0xf
0034522a  80 fa 09              cmp  dl, 9                 ; <== THE CAP
0034522d  7c 08                 jl   0x345237
0034522f  81 60 1c ff ff 3f fc  and  dword [eax+0x1c], 0xfc3fffff   ; wrap: field = 0
00345236  c3                    ret
00345237  8b 50 1c              mov  edx, [eax+0x1c]
0034523a  41                    inc  ecx
0034523b  c1 e1 16              shl  ecx, 0x16
0034523e  33 ca                 xor  ecx, edx
00345240  81 e1 00 00 c0 03     and  ecx, 0x3c00000
00345246  33 d1                 xor  edx, ecx
00345248  89 50 1c              mov  [eax+0x1c], edx
0034524b  c3                    ret
```

and the backward handler, `0x345250`:

```
0034525f  8b 48 1c              mov  ecx, [eax+0x1c]
00345262  c1 e9 16              shr  ecx, 0x16
00345265  f6 c1 0f              test cl, 0xf
00345268  7f 13                 jg   0x34527d              ; non-zero: decrement
0034526a  8b 48 1c              mov  ecx, [eax+0x1c]
0034526d  81 e1 ff ff 7f fe     and  ecx, 0xfe7fffff       ; clears bits 23,24
00345273  81 c9 00 00 40 02     or   ecx, 0x2400000        ; sets bits 22,25  => field = 9
00345279  89 48 1c              mov  [eax+0x1c], ecx
0034527c  c3                    ret
```

The right elbow pair at `0x3452C0` / `0x345300` is the same code with `shr 0x1a`, mask
`0x3C000000`, `and 0xe7ffffff`, `or 0x24000000`: also 9.

So the reachable range on the game's screen is **0..9**: None through Neoprene. White Turf,
Black Turf, Taped, High White, High Black and High Team (10..15) can never be selected, and
pressing next on a player who already wears one takes `dl >= 9` and clears the field to None.
That is X_Ray's report, exactly.

Elbow pads are the only short slot. Every other row on the same page already caps at
`len(list) - 1`, checked against the executable in
`RetailTests.test_elbow_pads_are_the_only_slot_the_game_cannot_cycle_fully`:

| row | next handler | cap | list length |
| --- | --- | --- | --- |
| Helmet | `0x345A30` | 1 | 2 |
| Face Mask | `0x345AD0` | 26 | 27 |
| Face Shield | `0x345B80` | 2 | 3 |
| Eyeblack | `0x345CE0` | 1 | 2 |
| Mouthpiece | `0x345D80` | 1 | 2 |
| Left / Right Glove | `0x345E20` / `0x345ED0` | 9 | 10 |
| Left / Right Wristband | `0x3450B0` / `0x345160` | 13 | 14 |
| **Left / Right Elbow Pad** | `0x345210` / `0x3452C0` | **9** | **16** |
| Sleeves | `0x345F80` | 3 | 4 |
| Left / Right Shoe | `0x345370` / `0x345460` | 6 | 7 |
| Neck Roll | `0x346010` | 4 | 5 |
| Turtleneck | `0x3460B0` | 3 | 4 |

Nothing else clamps the field. Every other reference to the two masks in `.text`
(`0x60B20`, `0xBE0F0`, `0xE4300`, `0x3428D0`, `0x345XXX`) is a plain four-bit get/set accessor
pair. One site, `0x106433`, forces a zero left-elbow field to 9 in one unrelated routine; it
never lowers a value and is not on the cycle path.

## What was built

`mod_editor/core/nfl2k5_elbow_options.py`, in the shape of the smallest existing 2K5 XBE
options (`nfl2k5_position_row.py` / `nfl2k5_probowl_order.py` over the shared
`nfl2k5_rdata_sites` helper: pinned retail spans, `retail | applied | foreign`, section SHA-1
recomputed). Off by default, EXPERIMENTAL / UNWITNESSED, no cave, no new data.

Four spans, **eight changed instruction bytes** (plus the one `.text` section digest):

| label | span VA | span file offset | span | changed bytes (VA: before -> after) |
| --- | --- | --- | --- | --- |
| `left_elbow_next` | `0x34521F` | `0x33521F` | 24 B | `0x34522C`: `09` -> `0f` |
| `left_elbow_prev` | `0x34525F` | `0x33525F` | 30 B | `0x345271`: `7f` -> `3f`; `0x345272`: `fe` -> `fc`; `0x345277`: `40` -> `c0`; `0x345278`: `02` -> `03` |
| `right_elbow_next` | `0x3452CF` | `0x3352CF` | 24 B | `0x3452DC`: `09` -> `0f` |
| `right_elbow_prev` | `0x34530F` | `0x33530F` | 30 B | `0x345322`: `e7` -> `c3`; `0x345328`: `24` -> `3c` |

(File offsets are `VA - 0x10000`: `.text` is VA `0x11000` at raw `0x1000`.)

After the patch: `cmp dl, 0xf` forward (0..15 reachable, 15 wraps to None) and
`and ecx, 0xfc3fffff` + `or ecx, 0x3c00000` backward (None wraps to High Team); the right row
is `and ecx, 0xc3ffffff` + `or ecx, 0x3c000000`. Instruction lengths are unchanged, the field
stays four bits, and the stored value stays in 0..15, so a patched image and a retail image
read each other's rosters identically.

Retail bytes pinned in the module (the four spans start at the field read and end at the ret
of the wrap path, so the shift that names the field, the mask and the wrap constants are all
covered); a foreign span refuses the patch.

**Exact revert**: `revert()` writes the same four spans back, and the tests prove the result is
byte-identical to the input for both the synthetic image and the retail executable.

Wiring, matching `probowl_order` end to end:

* `mod_editor/core/nfl2k5_throw_tuning.py`: import, `elbow_options` flag in `_apply_all` and
  both public builders, the apply chain entry, and `"elbow_options"` in all four inspector
  status dictionaries.
* `mod_editor/core/mod_build.py`: `BuildPlan.elbow_options = False`, `wants_xbe_patch()`,
  `availability()`, the report map and the receipt step keys. No preset turns it on.
* `mod_editor/gui/build_panel_qt.py`: the Build-tab option with the EXPERIMENTAL / UNWITNESSED
  badge and the retail-only gate, plus the inspector rows ("elbow pad options") in both the
  read-back tooltip and the "Already on this disc" summary.
* `mod_editor/core/providers.py`, `packaging/release-allowlist.txt`,
  `packaging/check_2k5_mod_studio_runtime.py`: the new module added to the pinned closure.
* `tests/nfl2k5_throw_tuning_test.py`: the shared synthetic XBE gains a `.text` window at
  `0x345000` (section index 7, previously empty) seeded with the four retail spans, so the
  Build tab sees the option as `retail` in tests.

## Tests and results

New: `tests/mod_editor/test_b75_elbow_options.py` (22 tests: shape, synthetic apply / revert /
idempotence / digest / tamper, build-dispatcher order independence, wiring, and a retail class
that re-derives the gate from the executable).

```
python3 -m pytest -q -p no:cacheprovider tests/mod_editor/test_b75_elbow_options.py
    22 passed

python3 -m pytest -q -p no:cacheprovider \
    tests/mod_editor/test_b74_equipment_enums_match_xbe.py \
    tests/mod_editor/test_nfl2k5_position_row_probowl.py \
    tests/nfl2k5_throw_tuning_test.py \
    tests/mod_editor/test_ux_build_plan_coverage_qt.py \
    tests/mod_editor/test_gameplay_patches_panel_qt.py
    61 passed, 1 skipped

python3 -m pytest -q -p no:cacheprovider \
    tests/mod_editor/test_provider_integrity.py tests/mod_editor/test_providers.py
    41 passed, 9 subtests passed

python3 -m pytest -q -p no:cacheprovider \
    tests/mod_editor/test_nfl2k5_olb_row.py tests/mod_editor/test_nfl2k5_season_cap.py
    20 passed, 414 subtests passed

python3 -m pytest -q -p no:cacheprovider tests/mod_editor/test_build_panel_qt.py
    16 passed

python3 -m pytest -q -p no:cacheprovider tests/mod_editor/test_mod_build.py::PresetTests
    7 passed
```

One long run (`test_build_panel_qt.py`, `test_mod_build.py`,
`test_xbe_patch_memory_writes.py`, `test_nfl2k5_season_cap.py`, 26:50) came back
`2 failed, 153 passed, 350 subtests passed`. Both failures were
`ThrowTuningError: Unsupported Build settings` from `project_build_settings()`, because that
run was started before `elbow_options` was added to `nfl2k5_build_settings.FEATURE_KEYS`: a
Build toggle that the saved-settings key list does not know is refused on capture. With the key
in place both pass:

```
python3 -m pytest -q -p no:cacheprovider \
    "tests/mod_editor/test_build_panel_qt.py::BuildPanelTests::test_intro_trim_is_build_only_off_and_roundtrips_project_settings" \
    "tests/mod_editor/test_build_panel_qt.py::BuildPanelTests::test_watermark_choice_survives_project_restore"
    2 passed
```

Offscreen Qt check of the Build tab against the synthetic executable: `mod_build.inspect` reports
`elbow_options = retail`, the row is enabled and unchecked, its label is "Edit Player offers every
elbow pad", and the read-back tooltip carries the "elbow pad options:" inspector row.

`python3 packaging/repin.py --apply` moved seven pins in two passes (mod_build, throw_tuning,
build_settings, build_panel_qt, and their provider copies); a final pass reports zero.

`packaging/check_2k5_mod_studio_runtime.py` refuses on this worktree, but it refuses identically
on the unmodified beta 74 tree (`validate_registry` missing at
`mod_editor/capabilities/test_registry.py:12`): pre-existing, not from this job.

## Reservation manifest

**Yes, it needs regenerating, for the fingerprints only. No new reservation, no span change.**

The patch writes four fixed `.text` spans in place. It allocates no cave, adds no span and
changes no allocator layout, so `data/nfl2k5_cave_reservations.json`'s 13,037 spans are correct
as they stand.

What is stale is its `source_sha256` map. `tests/mod_editor/test_nfl2k5_cave_oracle.py` loads the
manifest with `source_root=ROOT` (lines 382 and 395), and that check refuses on any pinned source
whose bytes moved. `mod_editor/core/mod_build.py` and `mod_editor/core/nfl2k5_throw_tuning.py`
are both pinned and both changed here, which is why the gate reports:

```
python3 -m pytest -q -p no:cacheprovider tests/mod_editor/test_nfl2k5_cave_oracle.py
    2 failed, 27 passed, 3 subtests passed in 372.31s (0:06:12)
    FAILED CaveOracleTests::test_release_manifest_includes_resource_build_steps
    FAILED CaveOracleTests::test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag
    OracleError: stale reservation source: mod_editor/core/mod_build.py; regenerate manifest
```

Both failures are that one check, and nothing else. Proof: refreshing only those two hashes in a
scratch copy of the manifest (same 176 keys, same 13,037 spans, nothing else touched) and
re-running the two tests through `NFL2K5_CAVE_MANIFEST`:

```
NFL2K5_CAVE_MANIFEST=<scratch>/refreshed_manifest.json python3 -m pytest -q -p no:cacheprovider \
    tests/mod_editor/test_nfl2k5_cave_oracle.py \
    -k "release_manifest_includes_resource_build_steps or retail_current_stack_owns_every_supplied_cave"
    2 passed, 27 deselected
```

A real regeneration also adds `mod_editor/core/nfl2k5_elbow_options.py` to the map, since
`nfl2k5_cave_manifest.source_fingerprints()` globs `mod_editor/core/nfl2k5_*.py` and
`nfl2k5_throw_tuning` now imports it. That regeneration needs the pinned USA retail XBE and a
retail xiso and belongs to whoever assembles the beta 75 stack; the scratch manifest above was
written outside the worktree and is not committed.

## Commit

One commit on `job/b75-x1`, twelve files, on top of the beta 74 commit `56b537342`, not
pushed: "Beta 75: the game's own Edit Player cycles all sixteen elbow pads, not the first
ten". A commit cannot carry its own hash, so read it from `git rev-parse job/b75-x1`; the
job's closing message quotes it.

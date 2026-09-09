# ASTRA_REPORT: beta-63.1 hotfix, "outer 5: ROST preamble ... Build & Share works" (2026-09-09)

Branch `astra/hf63-repacked-source` (from tag `beta-63`, 9c17c538). One bug, one root cause, one
unprotected file changed, one new test file. No push, no emulator, no GUI display.

## TL;DR

The disc layout was never the problem. The build died in its LAST step, the Outside Linebackers
scan, because that scan's ROST parser accepted only the retail preamble version 17 while the
16-reserves / extra-created-teams arena growth (which the tester had ticked, together with the
merged position pools) rewrites the main roster as version 18 with a 0x92000 arena. The build then
decorated that refusal with the disc identity, and for the tester's image the identity line said
"repacked disc ... Build & Share works", which sent him to repack a disc that was never at fault.
The same plan fails identically on a retail dump.

Fix: `tools/nfl2k5_roster_reclassify.py` reads version 18 when the arena is exactly the writer's
grown shape. Regression tests red before / green after, synthetic and retail-gated. The build that
reproduced the tester's dialog verbatim now completes (BUILD OK in 424 s on the repack).

## 1. Reproduction

Inputs: the retail xiso `/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso` (read-only,
never copied into the repo). All images below lived in `mktemp -d` folders on the Storage / 12TB
drives (never on `/`, which stayed at 104 GB free) and are deleted; `df -h /` at the end of this
report.

### 1a. A repack from the vendored extract-xiso

`tools/vendor/extract-xiso/build/extract-xiso -r -d <tmp> <retail>` (28 s). Output 6,300,958,720
bytes (retail 6,300,499,968). The studio's classifier on it:

```
repack
repacked disc (retail files, different layout: rebuild your image with extract-xiso -r or use the
original dump). Read as an xiso. The game files are byte-for-byte retail, but 19 of 19 sit at other
sectors than a real dump (for example update.xbe at 0x43A0800 instead of 0x11000). Build & Share
works (it finds every file through the disc directory), but a .2k5patch addresses bytes by their
position and this image moved them, so Apply cannot use it. ...
update.xbe       off=0x43A0800 retail=0x11000     default.xbe  off=0x84800 retail=0x249000
vc_53450030/0    off=0x3C140800 retail=0x6139F800  (all 19 relocated, all retail sizes)
```

That is the tester's image to the sector (his update.xbe was at 0x43A2800, one extra 0x2000 of
directory in front; same tool, same kind). Note `-r` leaves `default.xbe` byte-identical: its media
patch looks for `E8 CA FD FF FF 85 C0 7D`, which none of the three retail XBEs contain.

**Gotcha found on the way:** rewrite mode renames its INPUT path to `<name>.old` before writing,
even with `-d` pointing elsewhere (`extract-xiso.c:806-813`). It renamed the retail dump; I renamed
it back at once (same inode 17301530, size and mtime unchanged, bytes untouched). The retail-gated
test therefore hands extract-xiso a symlink inside the scratch folder, so only the link is renamed.

### 1b. Builds on the repack, beta-63 code, before any change

| plan | result |
|---|---|
| `softdrink_basic` preset | BUILD OK in 51 s, output 6,300,958,720 B, sha256 1724232174fe... |
| `softdrink_advanced` preset (pools, schedule, history, names, tags, depth roles) | BUILD OK in 177 s, output 6,313,259,008 B |
| the tester's Gameplay set: guardian_overlay + everyone-in-practice, my_career, franchise_autosave, crib_reclaim, modern_naming, reserves_16, created_teams_extra=2 | BUILD OK in 310 s, output 5,896,230,912 B |
| the same set **plus position_pools** | **BUILD FAILED in 386 s** |

The failure is the dialog text verbatim (upscaled screenshot `2k5-bugs_004.png`; the page shows the
Gameplay page scrolled to the beta-62 rows, all ticked; "Merged positions with one Linebackers
group" sits higher on the same page):

```
[13:58:22] Adding experimental extra patch space 0/0
[13:59:18] Writing modern 2K mode names 0/0
[14:03:08] Scanning every disc roster for outside linebackers 0/0
BUILD FAILED in 386s: ValueError: outer 5: ROST preamble. This image is: repacked disc (retail
files, different layout: rebuild your image with extract-xiso -r or use the original dump). Read as
an xiso. The game files are byte-for-byte retail, but 19 of 19 sit at other sectors than a real dump
(for example update.xbe at 0x43A0800 instead of 0x11000). Build & Share works (it finds every file
through the disc directory), but a .2k5patch addresses bytes by their position and this image
moved them, so Apply cannot use it. Build the mod yourself on the Build tab instead of applying a
patch file.
  File ".../mod_editor/core/mod_build.py", line 1736, in _build
    scan = roster_scan.olb_filter_policy(target)
  File ".../tools/nfl2k5_roster_reclassify.py", line 166, in parse_resource
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
  File ".../mod_editor/core/mod_build.py", line 915, in build
    raise _with_identity(exc, source, tt.is_disc_image(source)) from exc
```

(The screenshot's source pill reads "Disc: ESPN NFL 2K5 (USA).iso"; "(gameplay patched)" is the
NAME HE TYPED for the output copy, not a pre-modded source. His "repackaging" changed nothing: the
layout is irrelevant, and extract-xiso even skips an already-optimized image, `extract-xiso.c:802-804`.)

### 1c. The same failure without any disc, in memory

Read outer entry 5 of the retail image through the directory, grow it with the shipped arena
migration, parse it with the scan's parser:

```
retail entry 5: 0x392800 593792 version 17 -> parses: roster 2547 players 52 teams
{'reserves_16': True,  'created_teams_extra': 0} grown: 598112 version 18 -> outer 5: ROST preamble
{'reserves_16': False, 'created_teams_extra': 2} grown: 598112 version 18 -> outer 5: ROST preamble
{'reserves_16': True,  'created_teams_extra': 2} grown: 598112 version 18 -> outer 5: ROST preamble
```

## 2. Root cause (file:line, beta-63 numbering)

1. `mod_editor/core/nfl2k5_roster_arena.py:24` `DISC_VERSION = 18`; `:232-233` (`struct.pack_into(... layout.preamble + 16, ... DISC_VERSION)`) the migration stamps
   the main roster's preamble `+0x10` with 18 and pads the arena after the root to `ARENA_SIZE =
   0x92000` (`:18`). Records, root and pointers keep their shape.
2. `mod_editor/core/mod_build.py:1713-1714` runs that growth (`tt._finish_roster_arena_image`) for
   `reserves_16` / `created_teams_extra`, and `:1721-1744` runs the Outside Linebackers scan (`:1736`)
   `roster_scan.olb_filter_policy(target)` AFTER it, on purpose ("decided after the LAST roster
   mutation (... arena growth)"). The scan runs when `position_pools` is on (or the source already
   carries the pools).
3. `tools/nfl2k5_roster_reclassify.py:166` `parse_resource` required
   `nr.u32(body, 0x10) == 17` -> `ReclassifyError("outer 5: ROST preamble")` on the grown roster.
   The wrapper check on `:164` passes (the growth keeps stored == sys bytes), so the version is the
   only thing that refuses.
4. `mod_editor/core/mod_build.py:913-915` and `:820-836` (`_with_identity`) append
   `This image is: <identity line>` to every build `ValueError` on an image. For a repack the line
   ends in "Build & Share works ... Build the mod yourself on the Build tab", which is what the
   dialog quoted; for a retail xiso it would have said "Build and Apply both work."

So: any image, `position_pools` + (`reserves_16` or `created_teams_extra`) -> refused after the
full five-minute build. Nothing in the build path addresses bytes by absolute image offset: every
reader/writer I traced (`OuterImage`, `DiscBanks`, `image_xbe_extent`, `write_image_xbe`,
`nfl2k5_music_archive.Disc/layout/write_named`, `nfl2k5_resource_growth`, crib `_geometry`) resolves
through the XDVDFS directory, and the three successful repack builds above prove it.

## 3. The fix (`tools/nfl2k5_roster_reclassify.py`)

- `ROST_VERSION_RETAIL = 17`, `ROST_VERSION_GROWN = 18`, `GROWN_ARENA_SIZE = 0x92000` (documented
  against `nfl2k5_roster_arena.DISC_VERSION` / `ARENA_SIZE`).
- `parse_resource` accepts version 18 only when `len(body) - root == 0x92000`, i.e. exactly the
  arena writer's shape; any other version-18 file is still "outer N: ROST preamble". Versions other
  than 17/18 stay refused.
- `status()` / `apply()` are untouched: a grown roster never hashes retail, so the pass is still
  never applied on top of a grown arena (the build applies it before the growth).
- Docstring paragraph explaining why the reader accepts the grown shape.

Diff: 14 insertions, 1 deletion, plus the docstring. `python3 packaging/repin.py --apply` ->
"applied 0 pin update(s)" (no `.py` pin covers this tool). The only pin is the protected manifest,
see WIRING.md section 1.

Not changed on purpose: `mod_build._build` order (the scan must see the grown roster), the disc
identity classifier (its text is right in the panel header; the contradiction is created by the
concatenation in protected `_with_identity`, patch in WIRING.md section 2), other version-17-only
readers (`nfl2k5_team_history.py:245`, `nfl2k5_player_tags.py:128`, `tools/nfl_roster.py:295`): they
are status readers used as gates BEFORE the growth in the build order and wrapped in try/except in
`inspect()`; on a grown disc they report "foreign" in the receipt, which is cosmetic and out of
scope for this one bug.

## 4. Tests

New file `tests/mod_editor/test_nfl2k5_roster_reclassify_grown_arena.py` (11 tests):

- `SyntheticResourceTests`: a minimal ROST resource the parser accepts (preamble, root, players,
  teams, labels, strings), in the retail shape and the grown shape (version 18, arena 0x92000).
  Same players/positions/teams from both; the OLB evidence counts the same; a retail-length version
  18 and versions 0/16/19 stay refused.
- `SyntheticImageTests`: a synthetic XDVDFS image with 189 outer entries (entry 5 grown, 113..187
  historic) whose only pack sits at sector 64 and, separately, at sector 64 + 0x900:
  `olb_filter_policy` gives one identical complete answer at both layouts; a grown roster without
  OLBs certifies absence (`filter_rows: removed`).
- `RetailGrownRosterTests` (skips without the retail xiso): entry 5 of the retail image grown in
  memory for all three option sets parses and scans like retail.
- `RetailRepackTests` (skips without the retail xiso, the vendored binary, or
  `NFL2K5_REPACK_SCRATCH` pointing at a folder with 20 GiB free): extract-xiso `-r` through a
  symlink, identity "repack", every ROST outer identical to retail through the directory, the scan
  equal to the retail scan; then `nfl2k5_roster_arena_image.build_image` on the repack and the scan
  on the grown copy.

### Red before the fix (beta-63 parser), `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_roster_reclassify_grown_arena.py`

```
ERROR: test_the_grown_retail_roster_parses_for_every_arena_option (__main__.RetailGrownRosterTests.test_the_grown_retail_roster_parses_for_every_arena_option) (reserves_16=True, created_teams_extra=0)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_grown_retail_roster_parses_for_every_arena_option (__main__.RetailGrownRosterTests.test_the_grown_retail_roster_parses_for_every_arena_option) (reserves_16=False, created_teams_extra=2)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_grown_retail_roster_parses_for_every_arena_option (__main__.RetailGrownRosterTests.test_the_grown_retail_roster_parses_for_every_arena_option) (reserves_16=True, created_teams_extra=2)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_a_grown_roster_without_outside_linebackers_certifies_absence (__main__.SyntheticImageTests.test_a_grown_roster_without_outside_linebackers_certifies_absence)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_scan_reads_a_grown_roster_wherever_the_pack_sits (__main__.SyntheticImageTests.test_the_scan_reads_a_grown_roster_wherever_the_pack_sits) (layout='retail-layout')
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_scan_reads_a_grown_roster_wherever_the_pack_sits (__main__.SyntheticImageTests.test_the_scan_reads_a_grown_roster_wherever_the_pack_sits) (layout='moved-layout')
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_scan_reads_a_grown_roster_wherever_the_pack_sits (__main__.SyntheticImageTests.test_the_scan_reads_a_grown_roster_wherever_the_pack_sits)
ERROR: test_the_grown_shape_parses_like_the_retail_one (__main__.SyntheticResourceTests.test_the_grown_shape_parses_like_the_retail_one)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
ERROR: test_the_scan_counts_the_same_outside_linebackers_on_both_shapes (__main__.SyntheticResourceTests.test_the_scan_counts_the_same_outside_linebackers_on_both_shapes)
nfl2k5_roster_reclassify.ReclassifyError: outer 5: ROST preamble
Ran 11 tests in 3.352s
FAILED (errors=9, skipped=2)
```

(2 skipped = `RetailRepackTests`, opt-in scratch not set. The retail-shape, negative and
moved-sector-retail tests pass before and after; every grown-shape test fails with the tester's
exact message, on the synthetic retail-layout image as on the moved one.)

### Green after the fix, same command plus `NFL2K5_REPACK_SCRATCH=<folder on the Storage drive>` (runs all 11, including the extract-xiso -r rebuild and the shipped arena writer on it)

```
----------------------------------------------------------------------
Ran 11 tests in 117.603s

OK
exit=0
```

Without the scratch variable: `Ran 11 tests in 1.935s  OK (skipped=2)`.


### Existing suites, `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 <file>` (tails)

The brief's globs (`test_mod_build*`, `test_*source*`, `test_*xiso*`, `test_*classif*` -> the disc
identity file; there is no other `classif` test), the reclassify / position-pool suites, the
Outside Linebackers row test, the guardian / scorebug resource writers (they share the archive
growth primitives) and the two XBE gates:

| file | tail | exit |
|---|---|---|
| `tests/nfl2k5_roster_reclassify_test.py` | Ran 10 tests in 0.205s OK | exit=0 |
| `tests/nfl2k5_position_pools_test.py` | Ran 26 tests in 11.252s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_olb_row.py` | Ran 13 tests in 73.303s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_disc_identity.py` | Ran 24 tests in 0.688s OK | exit=0 |
| `tests/mod_editor/test_source_accepts_any_dump.py` | Ran 15 tests in 0.009s OK (skipped=2) | exit=0 |
| `tests/mod_editor/test_xiso_layout_tolerance.py` | Ran 9 tests in 0.814s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_source_cache_privacy.py` | Ran 7 tests in 0.005s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_audio_source_containment.py` | Ran 17 tests in 0.551s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_audio_source_fingerprints.py` | Ran 17 tests in 0.079s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_audio_source_scan.py` | Ran 12 tests in 3.020s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_scorebug_source_art.py` | Ran 13 tests in 0.554s OK (skipped=3) | exit=0 |
| `tests/mod_editor/test_nfl2k5_scorebug_resources.py` | Ran 6 tests in 141.203s OK | exit=0 |
| `tests/mod_editor/test_nfl2k5_guardian_resources.py` | Ran 9 tests in 87.115s OK | exit=0 |
SUITES_TABLE_2


## 5. End-to-end after the fix

The failing plan (tester's Gameplay set + position_pools) on the repack:

```
[14:04:25] outer 5 (roster): 483 players rewritten 0/0
[14:05:37] Adding experimental extra patch space 0/0
[14:06:23] Writing modern 2K mode names 0/0
[14:09:36] Scanning every disc roster for outside linebackers 0/0
[14:10:43] The output differs from the source. Review the build receipt for the selected changes.
BUILD OK in 424s   output 5,896,230,912 B  sha256 408ceb76c7fb23d76d10807c639a6a4284bab4e8316b40041d0c1bf8d3f97d9a
```

The output disc read back: `olb_filter_policy` complete, olb_players 0, roster_has_olb False,
filter_rows removed; `nfl2k5_roster_arena_image.image_status` applied; position pools applied and
filter rows applied; crib movie cut applied.

The same plan on the RETAIL dump (`/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso`,
whole-file sha256 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9, the hash the
studio's own cache folder is named after), after the fix:

```
[14:22:19] Scanning every disc roster for outside linebackers 0/0
BUILD OK in 384s   output 5,895,757,824 B  sha256 71ebef1df5138c2014373dac6981ab909b41d6b086145a2a72dc34bcbb9dd304
read back: OLB scan complete, olb_players 0, roster_has_olb False, filter_rows removed;
           arena image_status applied; position_pools applied, filter rows applied
```

(Before the fix this plan fails on the retail dump the same way; the in-memory retail proof in 1c
and the red run of `RetailGrownRosterTests` are that failure without the six-minute build.)

## 6. The brief's items 2 and 3

- Item 2 (build through the directory on a repack): already true, now also true for this plan. Basic,
  Advanced, the tester's set and the tester's set + pools all build on the extract-xiso repack. No
  open-time refusal is needed for repacks; the classifier's "Build & Share works" is correct.
- Item 3 (a previously modded source must read as MODDED): the classifier already does this. The
  Basic-preset output opened as a source: `modified | can_build: False`, "default.xbe does not
  match retail, while vc_53450030/0 still does. Build starts from retail bytes, so it refuses
  this." A grown/crib-cut output: `unknown | can_build: False` ("default.xbe, vc_53450030/0,
  vc_53450030/F is missing or not its retail size"). The header pill shows "· modified" at open
  time (`studio_qt.py:8008-8022`, `_describe_source_pill`), and every stage refusal on such a source keeps the identity
  note (WIRING section 2 only drops the note when the identity says the files are retail).
  The tester's source was not a modded image (see 1b), so no open-time behaviour changed.

## 7. What Noah must witness

Nothing here is proved in-game by me. To witness:

1. Beta-63.1 on his own dump (and, if he likes, on an extract-xiso `-r` copy of it): Gameplay page,
   tick "Merged positions with one Linebackers group" together with "16 reserves" and "Two extra
   created teams" (and the rest of the beta-62 rows if wanted), Make disc. Expected: the build
   finishes (about 7 minutes; the roster scan is the last step) instead of the "outer 5: ROST
   preamble" dialog.
2. In xemu on that disc: the depth chart / position filters must not list Outside Linebackers
   (the scan found none after the reclassify, so the rows are removed), and the 16-reserve /
   created-team features must behave as they did on a beta-63 disc built WITHOUT the pools. Both
   underlying features are still EXPERIMENTAL / UNWITNESSED as shipped in beta 63.
3. After WIRING section 2 lands: a build refusal on a retail or repacked image no longer ends with
   the "This image is: ... Build & Share works" sentence.

## 8. Housekeeping

- Retail inputs: untouched (the `.old` rename reverted immediately, same inode/size/mtime).
- Temp images: extract-xiso rebuild, three studio outputs, scratch folders: all deleted.
- Disk: DF_PLACEHOLDER

## 9. Commits

COMMITS_PLACEHOLDER

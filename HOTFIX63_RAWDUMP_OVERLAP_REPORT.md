# ASTRA_REPORT: beta-63.1 hotfix, "overlapping disc file or metadata: root directory" on a raw dump, then "please insert disk" (2026-09-09)

STATUS: FIXED. Root cause `mod_editor/core/nfl2k5_music_archive.py:165` (the extent-overlap sweep in
`Disc.__init__` started at `partition + 0x10800`, i.e. it assumed every named extent sits past the volume
descriptor; the tester's raw dump keeps its root directory at sector 30 and its `vc_53450030` directory at
sector 31, below the descriptor at sector 32, so the first span was reported as an overlap although nothing
overlaps). Fix: 3 lines in that unprotected file (commit `d067a795`), regression tests red before / green
after, all-options build from the raw dump reproduced the tester's dialog verbatim before the fix and
completes after it (section 1c). Second symptom: xemu 0.8.x does not boot redump-layout images at all; the
studio keeps the source's layout, so the identity line for a raw dump now says so (commit `00083367`,
separate so Claude can drop it). No protected file touched; `data/nfl2k5_cave_reservations.json` needs a
regen (WIRING.md). No push, no emulator, no GUI display.

Branch `local/hf63-rawdump-overlap` (from `hotfix/beta-63.1`, 8eccd7c7). Everywhere the brief says Astra,
this was Claude Fable 5.1 in Claude Code.

## TL;DR

* The tester's image is a **genuine pressed-disc dump** (redump size 7,825,162,240 B, real DVD-Video
  partition in front, game partition at 0x18300000) whose XDVDFS puts the **root directory at sector 30 and
  the `vc_53450030` directory at sector 31**, i.e. below the volume descriptor at sector 32. The xiso the
  studio pins puts its root at sector 33. Every writer that opens the disc through
  `nfl2k5_music_archive.Disc` (Crib reclaim, Guardian overlay, 16 reserves / extra created teams, hi-res
  pack, music shuffle / library, scorebug runtime) ran an overlap guard that started its sweep *past* the
  descriptor, so the root directory itself was refused as "overlapping metadata". The presets never open the
  disc that way, which is why "selecting one of your presets" built.
* Fix: sweep from the partition start and give the descriptor sector its own span. Real overlaps (a root
  that runs into the next directory, a file or a directory over the descriptor) are still refused, and the
  refusal now names the second span.
* "Please insert disk": the copy the studio writes keeps the dump's layout (verified byte-for-byte outside
  `default.xbe`), and **xemu 0.8.x cannot boot a redump-layout image** (its docs say so; its PR #2915 "Add
  Redump ISO support" is closed, not merged; the installed 0.8.136 binary does not even contain the XDVDFS
  magic string). The tester's untouched dump would show the same screen. The raw-dump identity line now says
  so and names the two cuts xemu's documentation gives.

## 1. Reproduction

Inputs (read-only, never copied into the repo): the raw dump `/home/noah/Downloads/ESPN NFL 2K5 (USA) 2.iso`
(7,825,162,240 B), the extract-xiso-style repack `/home/noah/Downloads/ESPN NFL 2K5 (USA) 1.xiso.iso`
(6,300,958,720 B) and the pinned retail xiso under `/media/noah/Storage/for codex 1.0/`. Every output lived
under `/media/noah/Storage/.hf63-rawdump/` (SSD, never `/`) and is deleted at the end (section 8).

### 1a. The classifier says exactly what the tester's screenshot says

```
$ identify(raw dump)      kind: repack
repacked disc (retail files, different layout: rebuild your image with extract-xiso -r or use the original
dump). Read as a raw dump (game partition at 0x18300000). The game files are byte-for-byte retail, but 19 of
19 sit at other sectors than a real dump (for example update.xbe at 0xD59F5000 instead of 0x11000). Build &
Share works (it finds every file through the disc directory), but a .2k5patch addresses bytes by their
position and this image moved them, so Apply cannot use it. ...
$ identify(1.xiso.iso)    kind: repack   (Read as an xiso ... update.xbe at 0x43A0800 instead of 0x11000)
$ identify(retail xiso)   kind: retail-xiso
```

The tester's line is this line to the byte, so his image is this layout.

### 1b. The failure in one call, no build needed

```
archive.Disc("/home/noah/Downloads/ESPN NFL 2K5 (USA) 2.iso")
  -> ValueError('overlapping disc file or metadata: root directory')      (0.0 s)
archive.Disc(1.xiso.iso)   -> OK, partition 0x0, 20 entries
archive.Disc(retail xiso)  -> OK, partition 0x0, 20 entries
```

The span list the guard builds on the raw dump (absolute offsets; `rel` = partition-relative):

```
name                 abs lo       abs hi       rel lo       attr
root directory       0x001830F000 0x001830F800 0x000000F000  -1  <-- refused (sweep started at 0x18310800)
vc_53450030          0x001830F800 0x0018310000 0x000000F800  16
vc_53450030/0        0x0018311000 0x0023BCD800 0x0000011000 128
... packs 1-8, default.xbe (rel 0xD16D8000), dashupdate.xbe, update.xbe (rel 0xD59F5000), packs 9-f ...
vc_53450030/f        0x01802E5000 0x019B1B3800 0x0167FE5000 128
last extent end rel 0x182EB3800; image end rel 0x1BA3A8000 (927,942,656 B of non-zero filler after it)
```

Root directory: sector 0x1E (30), 2048 B; `vc_53450030`: sector 0x1F (31); descriptor: sector 32; sector 33
unused; first file at sector 34 (0x11000). Nothing overlaps anything.

### The layouts that exist (what "real dump" means)

| image | container | root dir | first file | file order | note |
|---|---|---|---|---|---|
| pinned retail xiso (`for codex 1.0`, 6,300,499,968 B) | xiso, base 0 | sector 33 (0x10800), 108 B | update.xbe @0x11000 | 9,5,3,1,0,2,4,7,6,8,D,B,A,C,E,F | that pack order is the pre-order of a balanced AVL tree over 0-F: a *created* xiso (extract-xiso/xdvdfs style), which is what `RETAIL_LAYOUT` in the classifier encodes |
| `1.xiso.iso` (6,300,958,720 B) | xiso, base 0 | sector 264 (0x84000) | default.xbe @0x84800 | 7,3,... | `extract-xiso -r` rewrite (same kind as the 63.1 "repacked source" report) |
| `2.iso`, the tester's kind (7,825,162,240 B = redump XGD1 size) | raw, base 0x18300000 | sector 30 (0xF000), 2048 B; `vc_53450030` at 31 | vc_53450030/0 @0x11000 | 0-8, default.xbe, dashupdate.xbe, update.xbe, 9-f | real DVD-Video partition in front (ISO 9660 PVD at 0x8000, label `SEP13011042`), non-zero filler in the game partition's spare sectors: a pressed-disc dump, not a rebuild |

So the classifier's "sit at other sectors than a real dump" is backwards for this image: the dump *is* the
pressed disc and the pinned xiso is the rebuilt one. That wording is not this bug and is left alone (the
"repack" verdict is still the useful one: Build works, a byte-run `.2k5patch` cannot apply). Worth a later
copy pass: "rebuild your image with extract-xiso -r or use the original dump" tells a redump owner to do
what he already did.

### 1c. Builds from the raw dump

Headless driver (`BuildPlan` + `mod_build.build`, scratchpad script; a plan validation loop dropped the
options that refuse on their own, independent of the disc: `franchise_2026_rules` and `senior_bowl`
("unavailable ... not proved"), `flatter_deep_ball` ("must be selected on its own"), `hires_pack` ("Select one
or more known Hi-res assets") and `read_option_runtime` ("need at least one paired authored read recipe")).

| plan | code | result |
|---|---|---|
| `softdrink_basic` (the tester's working case) | beta-63.1 before the fix | **BUILD OK in 45 s**, output 7,825,162,240 B, steps `['xbe']` |
| experimental preset + every remaining opt-in (87 options on, incl. `crib_reclaim`, `guardian_overlay`, `reserves_16`, `created_teams_extra=2`, `music_shuffle`, `music_policy=jukebox_menus`, `scorebug_runtime`, `xbe_space`, `kickoff_relocated`, `my_career`, `abilities`, `qb_spy`, `momentum`, ...) | pristine `git archive` of 8eccd7c7 (before the fix) | **BUILD FAILED in 0 s: ValueError: overlapping disc file or metadata: root directory** (the tester's dialog; `_with_identity` appends the identity line quoted in 1a) |
| the same plan | after the fix (commit d067a795) | see section 1d |

The pre-fix traceback, which also says which option pulled the trigger for him:

```
  File ".../mod_editor/core/mod_build.py", line 919, in build
    raise _with_identity(exc, source, tt.is_disc_image(source)) from exc
  File ".../mod_editor/core/mod_build.py", line 898, in build
    receipt = _build(replace(plan, target=str(directory / target.name), overwrite=False), progress,
  File ".../mod_editor/core/mod_build.py", line 1111, in _build
    tt.crib_reclaim_patch.plan(source)
  File ".../mod_editor/core/nfl2k5_crib_reclaim.py", line 163, in plan
    with archive.Disc(source, descriptors=()) as disc:
  File ".../mod_editor/core/nfl2k5_music_archive.py", line 167, in __init__
    require(lo >= end, f"overlapping disc file or metadata: {name}")
ValueError: overlapping disc file or metadata: root directory
```

Crib reclaim plans on the *source* before the copy, which is why his build died at once rather than after
minutes; had he left it unticked, Guardian overlay (`mod_build.py:1647`), the roster arena growth (`:1718`,
reserves / created teams), hi-res, music shuffle / library (`nfl2k5_music_banks`) or the runtime scorebug
(`nfl2k5_scorebug_ingame.py:898`) would have raised the same error later in the run. None of the three
presets opens the disc through this reader.

### 1d. The all-options build after the fix

Driver dropped, before the copy, the options that refuse on their own regardless of the disc
(read_option_runtime); the plan then ran with
85 options on (the experimental preset plus every remaining opt-in that
takes no authored input, including crib_reclaim, guardian_overlay, reserves_16, created_teams_extra=2, music_shuffle,
music_policy=jukebox_menus + unlock + UserList, scorebug_runtime, xbe_space, kickoff_relocated, my_career, abilities,
qb_spy, momentum + contact + collisions, weekly prep, deep-zone, defensive try, zone drop cap, all stadiums, 7-on-7,
team names 2026, chop block toggle, coverage slider, scramble tuning, practice squad screen, screen hooks, CPU money downs).

```
BUILD OK in 491s
STEPS ['xbe', 'position_pools', 'depth_chart_rows', 'kickoff_alignment', 'kickoff_returns', 'seven_on_seven_book', 'depth_roles', 'screen_timing', 'season_2026', 'team_history', 'prospect_names', 'team_names_2026', 'scorebug_runtime', 'guardian_overlay', 'xbe_space', 'modern_naming', 'roster_arena_growth', 'crib_reclaim', 'position_pool_filters']
OUTCOME {"status": "changed", "source": {"sha256": "645fa9dff40e2c6b9d2c141c9868111ddb0677025396a959c0517ea95eeabb6a", "size": 7825162240}, "output": {"sha256": "e4915be77b2f6e01058add84308098434cfafdea875613bdadaa03e5c4b75523", "size": 6291335168}, "message": "The output differs from the source. Review the build receipt for the selected changes."}
```

Step log tail (progress lines; copies, archive/verify counters and per-team rows elided):

```
[    48s] SD: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] SEA: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] SF: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] STL: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] TB: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] TEN: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] WAS: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] WCO: kickoff coverage to the receiving 40, return setup zone 35-30 0/0
[    48s] Giving the kickoff return blockers close assignments 0/0
[    51s] Editor: local kickoff return blocking 0/0
[    51s] Writing the 7-on-7 sets into the practice playbook 0/0
[    51s] Building the 7-on-7 practice book 0/0
[    51s] Writing PRACTICE-pb.iff 0/0
[    51s] Assigning X / Z / SLOT receivers and nickel / dime corners in the playbooks 0/0
[    61s] Screen pass timing (experimental) 0/0
[    70s] Setting the franchise to 2026 (year, calendar, 18-week season) 0/0
[    70s] Showing the seven-seed playoff picture and previews 0/0
[    71s] Writing the real 2026 schedule into the franchise template 0/0
[    80s] Writing the real team history into the roster template 0/0
[    80s] Matching the team history to the roster 0/0
[    81s] Writing the roster's history pool 0/0
[    81s] Writing the modern prospect names into the roster's name pool 0/0
[    81s] Rewriting the generated-player name pool 0/0
[    81s] Writing the roster resource 0/0
[    81s] Writing 2026 team names with fixed-length short forms 0/0
[    81s] Installing team logos and scorebug effects (unwitnessed) 0/0
[   164s] Adding experimental extra patch space 0/0
[   263s] Writing modern 2K mode names 0/0
[   435s] Scanning every disc roster for outside linebackers 0/0
[   491s] The output differs from the source. Review the build receipt for the selected changes. 0/0
```

## 2. Root cause (file:line, beta-63.1 numbering before the fix)

`mod_editor/core/nfl2k5_music_archive.py:157-168`, `Disc.__init__`:

```python
spans = sorted((e.byte_offset, e.byte_offset + e.size, name) for name, e in self.entries.items() if e.size)
root_sector, root_size = struct.unpack('<II', self.read(8, self.partition + 0x10014))
root_at = self.partition + root_sector * 2048
spans.append((root_at, root_at + root_size, 'root directory'))
spans.sort()
end = self.partition + 0x10800                       # <-- line 165: "everything lives past the descriptor"
for lo, hi, name in spans:
    require(lo >= end, f"overlapping disc file or metadata: {name}")
    end = hi
```

`end` starts at the end of the volume descriptor sector, so any extent whose start is below
`partition + 0x10800` is refused as overlapping "metadata", and the sorted list's first span is the root
directory (0xF000) on this dump. The guard was written (beta 61, cf349b76) against the pinned xiso, where the
root sits at sector 33 and nothing precedes it. XDVDFS reserves only the descriptor sector; the kernel reads
the root from whatever sector the descriptor names, and this pressed disc names sector 30. The partition
base plays no part: the same directory placement at base 0 fails identically (test
`test_the_testers_layout_opens`), and the same option set builds on the pinned xiso because its layout
happens to satisfy the assumption.

Nothing else in the writers shares the assumption in a harmful way: `nfl2k5_crib_reclaim._geometry` uses
`partition + 0x10800` only as a *floor* for compaction (`max(0x10800, root end, directory ends)`), which
stays valid; `archive.layout` / `write_named` append growth at the image end (`align_up(image_size)`) and
`image_file_node` resolves every file through the directory. The identity module and `parse_xdvdfs` read the
root from the descriptor and never assumed its sector.

## 3. Fix (commit d067a795, unprotected file, 3 lines + comment)

```diff
             spans.append((root_at,root_at+root_size,'root directory'))
+            # The volume descriptor is the only reserved sector. A pressed disc can keep its
+            # directories below it (a redump of this game has the root at sector 30), so sweep
+            # from the partition start and let the descriptor claim its own sector.
+            spans.append((self.partition + 0x10000, self.partition + 0x10800, 'volume descriptor'))
             spans.sort()
-            end = self.partition + 0x10800
+            end = self.partition
             for lo, hi, name in spans:
                 require(lo >= end, f"overlapping disc file or metadata: {name}")
                 end = hi
```

The descriptor keeps its protection (a file or directory over sector 32 is refused, now by name), directory
and file extents may sit anywhere else in the partition, and a real overlap is still refused naming the
second span in disc order. `status()` / `apply()` semantics of every caller are unchanged; the reader is
read-only. `packaging/repin.py --apply` repinned the module in `mod_editor/core/providers.py` (47479bf3... ->
a86456b8...). `data/nfl2k5_cave_reservations.json` (protected) lists the old hash under `source_sha256`:
regen needed (WIRING.md); the build path never checks that map, only `tools/nfl2k5_cave_oracle.py:98` does.

### 3b. The second symptom (commit 00083367, unprotected `nfl2k5_disc_identity.py`)

`_xemu_note(base)` appends one sentence to the identity detail of any image read as a raw dump (retail-raw
and relocated alike; xiso lines unchanged):

> xemu boots only the game partition, so a copy built from this dump keeps the video partition in front and
> xemu answers "please insert disc": build from an xiso, or cut the first 0x18300000 bytes off the copy
> (xdvdfs pack, or dd bs=1M skip=387).

(`dd bs=2048 skip=N` when the base is not a whole MiB, e.g. XGD2's 0x0FD90000.) The Build page already shows
this line in its source header (`build_panel_qt.py:1031`), so it is read before the build. Kept as a
separate commit: drop it if it counts as more copy than the bug needs; the overlap fix does not depend on it.

## 4. Tests

New file `tests/mod_editor/test_nfl2k5_music_archive_raw_layout.py` (synthetic sixteen-pack images built on
`tests/nfl2k5_xiso_fixture.SyntheticXiso`, the directories moved by a helper; one retail-gated read-only
open of the raw dump with `SkipTest` when it is absent):

* `test_the_pinned_fixture_layout_still_opens` (root at 33, as before)
* `test_the_testers_layout_opens` (root 30, `vc_53450030` 31)
* `test_a_file_below_the_descriptor_opens_too` (`default.xbe` at sector 29)
* `test_the_testers_layout_opens_behind_a_video_partition` (same, partition base 0x30000)
* `test_a_root_directory_that_runs_into_the_next_directory_is_still_refused` (root declared two sectors long
  over `vc_53450030`: "overlapping disc file or metadata: vc_53450030")
* `test_a_file_over_the_volume_descriptor_is_still_refused`
* `test_a_directory_over_the_volume_descriptor_is_still_refused`
* `RawDumpTests.test_the_raw_dump_opens_with_its_directories_below_the_descriptor` (partition 0x18300000,
  root below 32, packs 0..F, 16 banks)

Red before the fix (8eccd7c7 code):

```
ERROR: test_a_file_below_the_descriptor_opens_too ... ValueError: overlapping disc file or metadata: root directory
ERROR: test_the_testers_layout_opens ... ValueError: overlapping disc file or metadata: root directory
ERROR: test_the_testers_layout_opens_behind_a_video_partition ... ValueError: overlapping disc file or metadata: root directory
ERROR: test_the_raw_dump_opens_with_its_directories_below_the_descriptor ... ValueError: overlapping disc file or metadata: root directory
FAIL: test_a_root_directory_that_runs_into_the_next_directory_is_still_refused
  "overlapping disc file or metadata: vc_53450030" does not match "overlapping disc file or metadata: root directory"
Ran 8 tests in 0.042s   FAILED (failures=1, errors=4)
```

Green after: `Ran 8 tests in 0.061s  OK` (and `archive.Disc(raw dump)` -> `partition=0x18300000 entries=20
banks=16`).

`tests/mod_editor/test_nfl2k5_disc_identity.py` gained `RawDumpXemuNoteTests` (4 tests: raw-dump line names
the cut, relocated raw dump too, xiso lines stay silent, the XGD1 cut is the documented 387 MiB):
`Ran 29 tests in 0.455s  OK`.

Related suites, each standalone with `PYTHONPATH=<repo> QT_QPA_PLATFORM=offscreen python3 <file>` (28 files, all rc=0; both XBE gates included although no game-code writer changed):

```
test_nfl2k5_music_archive_raw_layout rc=0 1s | Ran 8 tests in 0.062s OK 
test_nfl2k5_music_banks rc=0 12s | Ran 15 tests in 11.768s OK 
test_nfl2k5_music_build rc=0 4s | Ran 8 tests in 3.633s OK 
test_nfl2k5_music_acceptance rc=0 0s | Ran 1 test in 0.000s OK (skipped=1) 
test_music_simple rc=0 16s | Ran 12 tests in 15.729s OK 
test_nfl2k5_music_playlist_library rc=0 17s | Ran 7 tests in 16.838s OK 
test_nfl2k5_crib_reclaim rc=0 5s | Ran 6 tests in 4.846s OK 
test_nfl2k5_roster_arena_image rc=0 15s | Ran 4 tests in 14.922s OK 
test_nfl2k5_hires_pack rc=0 2s | Ran 15 tests in 1.723s OK 
test_nfl2k5_hires_pack_retail rc=0 17s | Ran 4 tests in 16.180s OK 
test_nfl2k5_hires_families rc=0 1s | Ran 7 tests in 1.175s OK 
test_nfl2k5_hires_families_retail rc=0 455s | Ran 5 tests in 454.682s OK 
test_nfl2k5_guardian_resources rc=0 58s | Ran 9 tests in 57.804s OK 
test_nfl2k5_guardian_manifest rc=0 223s | Ran 1 test in 222.633s OK 
test_nfl2k5_animation_import_retail rc=0 13s | Ran 3 tests in 12.982s OK (skipped=2) 
test_nfl2k5_scorebug_resources rc=0 100s | Ran 6 tests in 99.322s OK 
test_provider_integrity rc=0 7s | Ran 7 tests in 7.546s OK 
test_nfl2k5_disc_identity rc=0 1s | Ran 29 tests in 0.434s OK 
test_xiso_layout_tolerance rc=0 1s | Ran 9 tests in 0.668s OK 
test_source_accepts_any_dump rc=0 0s | Ran 15 tests in 0.007s OK (skipped=2) 
test_apf_iso_extraction_is_layout_tolerant rc=0 0s | Ran 10 tests in 0.077s OK 
test_pack_extent_resolver rc=0 1s | Ran 6 tests in 0.974s OK 
test_modpack rc=0 8s | Ran 36 tests in 7.906s OK 
test_mod_build_beta62_integration3 rc=0 123s | Ran 11 tests in 121.939s OK 
test_mod_build_beta62_integration rc=0 176s | Ran 8 tests in 175.708s OK 
test_mod_build rc=0 1s | Ran 11 tests in 1.346s OK 
test_xbe_patch_memory_writes rc=0 1075s | Ran 111 tests in 1075.022s OK 
test_xbe_patch_cave_references rc=0 1245s | Ran 123 tests in 1244.437s OK 
DONE
```

## 5. Output verification (structural, no xemu) and the xemu verdict

Verifier (scratchpad script): locate the game partition, check `MICROSOFT*XBOX*MEDIA` at partition + 0x10000
head and tail, the root directory sector/size inside the image, walk the directory, check `default.xbe` at
its sector with the `XBEH` magic, every extent inside the image, the video partition's ISO 9660 PVD when the
base is not 0, then hash every file extent of output and source and the whole video partition.

**Basic preset output** (`basic-from-rawdump.iso`, 7,825,162,240 B, the tester's working case):

```
size 7825162240 base 0x18300000 magic head/tail ok: True True
root dir sector 0x1E size 0x800 root inside image: True
video partition PVD at 0x8000: b'\x01CD001' label b'SEP13011042'
directory: {'root_sector': 30, 'root_size': 2048, 'directory_extents': 2, 'directory_nodes': 20}
default.xbe sector 0x1A2DB0 (rel 0xD16D8000) size 11948032 magic b'XBEH'
every extent inside image: True
per-file: default.xbe bytes equal: False (the patched XBE); every other file and both directories
          same place and bytes equal: True; video partition [0, 0x18300000) equal: True
```

So the studio writes a structurally valid disc in the **source's own layout**: a raw dump in, a raw dump
out. Nothing the studio wrote breaks the image; what breaks the tester is the container.

**All-options output**: `all-options-fixed.iso`, 6,291,335,168 B (smaller than the 7,825,162,240 B source: the Crib reclaim step compacts the game files from sector 33 upward, drops the 417 MB of Crib movies from pack F and trims the dump's 927 MB of trailing filler). The game partition base is still 0x18300000, the descriptor magic is intact head and tail, the root directory is still sector 30 (directories are fixed by the compaction), all 20 directory nodes walk, `default.xbe` grew to 12,300,288 B (extra patch space) and sits at its new sector with the `XBEH` magic, every extent is inside the image and the last one ends exactly at the image end, `update.xbe` / `dashupdate.xbe` moved but are byte-equal, pack 0 grew (roster arena + Guardian resources), pack F shrank to 34,617,344 B, every other pack differs (playbooks, rosters, music, names live in them), and the video partition is byte-equal to the dump. Structurally a valid XDVDFS disc in the dump's container, i.e. still not an xiso: xemu would show the same "please insert disc" until the first 0x18300000 bytes are cut off.

```
== /media/noah/Storage/.hf63-rawdump/all-options-fixed.iso
   size 6291335168 base 0x18300000 magic head/tail ok: True True
   root dir sector 0x1E size 0x800 root inside image: True
   video partition PVD at 0x8000: b'\x01CD001' label b'SEP13011042'
   directory: {'root_sector': 30, 'root_size': 2048, 'directory_extents': 2, 'directory_nodes': 20}
   default.xbe sector 0x2A0B57 (rel 0x1505AB800) size 12300288 magic b'XBEH'
   last extent end abs 0x176FE2800; image end abs 0x176FE2800; every extent inside image: True
== /home/noah/Downloads/ESPN NFL 2K5 (USA) 2.iso
   size 7825162240 base 0x18300000 magic head/tail ok: True True
   root dir sector 0x1E size 0x800 root inside image: True
   video partition PVD at 0x8000: b'\x01CD001' label b'SEP13011042'
   directory: {'root_sector': 30, 'root_size': 2048, 'directory_extents': 2, 'directory_nodes': 20}
   default.xbe sector 0x1A2DB0 (rel 0xD16D8000) size 11948032 magic b'XBEH'
   last extent end abs 0x19B1B3800; image end abs 0x1D26A8000; every extent inside image: True
== per-file comparison (output vs source)
   vc_53450030      dir  same place:True
   vc_53450030/1    rel 0x000010800 size  299999232 same place:False bytes equal:False
   vc_53450030/2    rel 0x011E2A800 size  309252096 same place:False bytes equal:False
   vc_53450030/3    rel 0x024517800 size  315508736 same place:False bytes equal:False
   vc_53450030/4    rel 0x0371FC000 size  313178112 same place:False bytes equal:False
   vc_53450030/5    rel 0x049CA7800 size  307972096 same place:False bytes equal:False
   vc_53450030/6    rel 0x05C25C000 size  458231808 same place:False bytes equal:False
   vc_53450030/7    rel 0x07775D000 size  319197184 same place:False bytes equal:False
   vc_53450030/8    rel 0x08A7C6000 size  929370112 same place:False bytes equal:False
   dashupdate.xbe   rel 0x0C1E17000 size   58421248 same place:False bytes equal:True
   update.xbe       rel 0x0C55CE000 size    2326528 same place:False bytes equal:True
   vc_53450030/9    rel 0x0C5806000 size  634941440 same place:False bytes equal:False
   vc_53450030/a    rel 0x0EB58D000 size  310294528 same place:False bytes equal:False
   vc_53450030/b    rel 0x0FDD78800 size  458248192 same place:False bytes equal:False
   vc_53450030/c    rel 0x11927D800 size  315131904 same place:False bytes equal:False
   vc_53450030/d    rel 0x12BF06000 size  309135360 same place:False bytes equal:False
   vc_53450030/e    rel 0x13E5D6800 size  301813760 same place:False bytes equal:False
   default.xbe      rel 0x1505AB800 size   12300288 same place:False bytes equal:False
   vc_53450030/0    rel 0x151166800 size  195528704 same place:False bytes equal:False
   vc_53450030/f    rel 0x15CBDF000 size   34617344 same place:False bytes equal:False
   video partition [0,0x18300000) equal: True
   compared in 9s
```


**Does xemu 0.8.x accept redump images? No.**

* xemu's own documentation (xemu.app/docs/disc-images, fetched 2026-09-09): *"A 'redump' ISO contains both of
  these partitions ... xemu is not currently compatible with this format, but you can extract the second
  partition of the disc image for use with xemu"*, with `xdvdfs pack game-redump.iso`, `dd if=game-redump.iso
  of=game.iso skip=387 bs=1M` or `fallocate -c -o 0 -l 387MiB game.iso`.
* GitHub: xemu-project/xemu PR #2915 "Add Redump ISO support" (JBW89, 2026): `state closed, merged False,
  merged_at None`. It would have added `system/xemu-redump.c` detecting the game partition at sector 0x30600
  (0x18300000) and opening the drive with a raw `offset`; nothing of it is in master.
* The installed flatpak xemu 0.8.136 (release 2026-06-08; the newest non-prerelease) contains zero
  occurrences of `MICROSOFT*XBOX*MEDIA` and offers only "Disc Image Files (*.iso, *.xiso)", so it cannot be
  locating a game partition by its magic.

xemu hands the whole file to the emulated drive; the Xbox kernel reads sector 32 of the *file*, finds the
video partition's bytes (`01 00 02 00 5B 00 ...` on this dump) instead of the XDVDFS descriptor, and the
dashboard says "please insert disc". Reset / eject / re-insert changes nothing. The tester's untouched dump
behaves the same way, so the message cannot come from anything the studio wrote. The video partition in his
copy is byte-equal to his dump (verified above); truncating it or changing the size would not make xemu load
it either.

xemu-side checklist for the relay: (1) build from the xiso (the 6.3 GB image, or slice the game partition
out of the dump with `xdvdfs pack`, or `dd if=dump.iso of=game.xiso.iso bs=1M skip=387`, or
`fallocate -c -o 0 -l 387MiB copy.iso` on Linux); (2) point `dvd_path` in `xemu.toml` (`[sys.files]`) at the
new file, or Machine > Load Disc; (3) on the Flatpak build the file picker's FUSE portal path can fail to
open large images: set `dvd_path` in `~/.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml` directly; (4) eject
and insert again after changing the path.

## 6. What is proved offline, and what Noah must witness

Proved offline: the refusal is gone for this layout (unit tests, the raw dump itself, the all-options build),
real overlaps are still refused, every retail-gated suite listed above passes, the Basic output is the source
plus the patched XBE and nothing else, the all-options output is structurally a valid disc in the dump's
layout (section 1d / 5).

Not proved and not claimed: anything in-game. Nothing here changes what any patch writes; a copy built from
a raw dump will still not boot in xemu until its game partition is cut out (or the tester builds from an
xiso), and that cut-out image is what Noah would play if he wants to witness a raw-dump build.

## 7. Tester relay text (short, plain, from Claude)

> From Claude: two things were going on. (1) "overlapping disc file or metadata: root directory" was a bug
> in the studio, not in your disc: your dump keeps its folder tables just before the disc header (sector 30
> and 31), which is fine, but the check that opens the disc for Crib reclaim, Guardian overlay, 16 reserves,
> created teams, hi-res, music shuffle and the runtime scorebug assumed nothing lives there. Fixed in
> beta-63.1; every option now builds from your dump. (2) "please insert disk" is xemu, not the build: your
> image is a full disc dump (7.8 GB, video partition first) and xemu 0.8.x only boots the game partition
> (their docs say redump images are not supported). The studio keeps your dump's layout, so the built copy
> has the same problem, and so does your untouched dump. Either build from the 6.3 GB xiso, or cut the video
> partition off the built copy: `xdvdfs pack built.iso`, or on Linux/macOS `dd if=built.iso
> of=built.xiso.iso bs=1M skip=387`, then load that file in xemu. The studio now says this on the source line
> whenever it reads a raw dump.

## 8. Housekeeping

All scratch outputs under `/media/noah/Storage/.hf63-rawdump/` were deleted at the end; `/` never held an
image (`df -h /`: 100G free throughout). Retail inputs were opened read-only and not copied. No push. No
emulator launched. No GUI display used (tests offscreen). Commits, each with explicit paths:

```
00083367 Hotfix 63.1: a raw dump's identity line says xemu boots only the game partition
d067a795 Hotfix 63.1: the archive reader accepts a raw dump whose directories sit below the volume descriptor
```

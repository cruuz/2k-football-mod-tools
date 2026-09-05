# r61b music banks

2026-09-05. **EXPERIMENTAL / UNWITNESSED.** No Xbox emulator, GUI, audio playback,
network, real profile/save mutation or push was used. Bounded Unicorn execution below
is an offline integer-code experiment explicitly requested by the brief.

## Delivered

`mod_editor/core/nfl2k5_music_banks.py` exposes read-only `plan`, transactional
`rebuild`, independent `verify`, and realistic `estimate`. Its CLI is
`tools/nfl2k5_music_banks.py`; `inventory`, `plan`, `rebuild`, `verify`, and
`estimate` all write reviewable JSON. `WIRING.md` contains the complete protected
BuildPlan, dispatcher, status, Music panel, packaging and capability hand-off.

The archive helper resolves the 16 named XDVDFS packs and walks all 17 AUSB
wrappers at their stable resource ordinals. It validates names, aliases, codecs,
boundary counts, complete outer coverage, root/nested directory extents and u32
fields. Changed resource bodies stay aligned to 16 bytes. A 200-track descriptor
has 201 byte boundaries and a 960-byte body; the retail menu body is 192 bytes.
Every other resource wrapper/body/gap in a changed container remains exact.

The planner reports every moved outer, each pack's size delta, projected physical
ISO and scratch space. The writer streams canonical 22,050 Hz PCM16 WAV through
bounded Xbox IMA chunks, pads at most 63 final PCM frames, and concatenates songs
without inter-song sector padding. Stereo/mono twins derive from the same frame
timeline, with floor-rounded `(left + right) / 2` downmix. Retained source slots
travel byte for byte. Same-count descriptors keep their exact size and suffix;
unchanged-position outer payloads are skipped when possible.

Rebuild writes a private sibling image from the selected source, including prior
edits. F growth appends the complete named F file and repoints its actual nested
directory node; shrink retains physical ISO slack and changes the named length.
All source/input identities, staged twins, read-back hashes and destination
identity must pass before `os.replace`. All handles close first. Failures and
cancellation preserve an existing destination. Reapplying the same recipe to a
built image produces identical bytes without another append.

Format 2 adds **ID 5 `file_shrink`, version 1**; ID 4 stays reserved for `file_add`.
Existing replacement/growth semantics and registry/reader versions are unchanged.
Shortened files must keep their sector, physical image size and unused allocation
bytes. Named pack replacement/growth/shrink operations are sufficient; no new
music-specific binary operation or modpack.py change was needed.

## XBE ownership and decisions

The existing allocator's 4 KiB writable page cannot hold this read-only library.
`nfl2k5_music_storage.py` adds an owned 64 KiB RO/preload section at
`0x14BC000..0x14CC000`, raw offset `0xB79000`. Its name is `.ASTRAr`, flags `0x3A`;
it is neither writable nor executable. The third descriptor uses another 56 bytes
of the allocator's already relocated header metadata. Names/counters fit in the
remaining retired header area; every unowned suffix byte is pinned. Existing
code/RW pages and other allocations keep their addresses. The final XBE is
12,095,488 bytes, with 25 sections.

Necessary additive helper changes: `nfl2k5_xbe_space.py` recognizes and reports the
RO owner; `nfl2k5_bump_strength.py` accepts only the validated additional section
when enumerating digests; `nfl2k5_depth_chart_storage.py` recognizes/writes/replays
this exact grown extent; `nfl2k5_cave_manifest.py` observes and reserves this owner
in its disposable default-off ownership probe. No protected file was edited.

`nfl2k5_music_metadata.py` stores sealed title/artist/duration strings and native
four-word song records in that allocation, then repoints the count/record-pointer
pair of each of the 18 collections at `0xAC9C80`. Original 59 records, collection
labels, stereo/mono pointers, enabled words and purchase keys remain pinned or
unchanged. The first 59 collection/song identities remain stable; added songs
fill the free collections beginning with collection 17. No collection exceeds
256 songs. Shared retail duration strings are never overwritten. Section digests
are repinned through the existing helper. Mixed counts, foreign pointers, corrupt
seals/padding or a different applied recipe refuse before mutation.

**Allocation proof boundary:** the region is newly declared loader storage beyond
all retail mappings and existing manifest owners. It is not a retail cave and is
never classified as `free`. A byte-granular absolute/relative encoding scan finds
469 candidate patterns in retail bytes; those are retained in
`.scratch/music-allocation.json`. They include unaligned bitmap/data/instruction
substrings. This report does **not** claim an empty reference scan or prove that
no computed runtime alias can ever occur. Loader acceptance, memory pressure and
dynamic aliases remain unwitnessed. Both existing executable cave/write gates
pass with the actual metadata owner composed into the complete patch stack.

## PROVED: disposable retail image acceptance

Source: the supplied 6,300,499,968-byte retail XISO, SHA-256
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
Its virtual outer archive is 6,227,718,144 bytes. The extracted retail XBE is pinned
to `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

200 generated mono/stereo tones use varied non-block input lengths. The encoder
rounds them to 3..7 blocks each. Every build reopened and checked all 4,323 outer
payloads: 4,321 unaffected outers for menu builds, 4,320 for twins, plus complete
expected changed-container bytes, every output track hash, first/middle/last
decoded tracks, and every unrelated named file. All source hashes stayed exact.

| Build | Encoded bytes | Virtual archive bytes | Physical ISO bytes | Pack F bytes | Moved outers | Plan / total seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 200 menu tracks | 72,000 | 6,210,230,272 | 6,300,499,968 | 434,245,632 | 4,319 | 3.941 / 36.485 |
| Retail 7-track menu fast path | 2,304 | 6,210,158,592 | 6,300,499,968 | 434,173,952 | 1,194 | 3.923 / 32.473 |
| 200 jukebox tracks plus twins | 108,000 | 5,900,091,392 | 6,312,595,456 | 124,106,752 | 4,319 | 6.956 / 44.157 |
| Retail 59-track paired fast path | 31,644 | 5,900,013,568 | 6,312,595,456 | 124,028,928 | 1,200 | 6.766 / 40.377 |

Scratch projections were respectively 6,336,514,592; 6,336,444,128;
6,348,646,432; and 6,348,568,956 bytes, excluding the already existing source.
Metadata-bearing builds append the complete grown XBE even though the music
archive shrinks. The descriptor-size change moves most outers in 200-count builds;
same-count cases only move the later bank suffix. Pack 0's index is always updated.

Output hashes, in table order:

```text
3e4f6470fbee2064163173628bc4ff4d7999c9920353464d0b176fe45e0f5a34
e0570375ecd6c10aa72ab730385806dec2dbec6a1552a2caeff179f6e749b2cc
c9817484923149d44efa67694d4f3f72ebd551d0a5fbd5007d9aceb4fa9e1d18
633d3950306a7fdcf58c8f0a756bf78130aca0bf82a7589b548e1d950562c204
```

All disposable ISO copies, including the oracle's full stack image, were deleted
under `.scratch/`. Detailed local receipts remain in
`.scratch/music-acceptance-{femusic,cribmusic}-{200,7,59}.json` for the combinations
above; `.scratch/music-acceptance-summary.json` records sizes/times/estimates.
No proprietary image, recipe input, generated tone, scratch file or brief is part
of the commit.

## PROVED: 200-entry native list and scroll experiment

The actual XBE code ran with allocated read-only metadata, a synthetic profile,
and the 400-node retail pool of 20-byte records. The sole external stub was
`0x191D20`, selecting synthetic profile zero. Native checksum calculation,
profile record reads/writes, node allocation/recycling, title lookup, bank-index
lookup and scroll clamping all executed. No XAPI, rendering, sound or filesystem
routine ran.

| Native path | Result |
| --- | --- |
| `0x280530` list builder | 200 nodes built in 15,671 instructions |
| Same builder, repeated | Old nodes recycled and 200 rebuilt in 19,075 instructions; no pool leak |
| `0x27F3A0` save path | 200 original items round-tripped and the following stop item cleared in 12,033 instructions |
| `0x27F900`, `0x27F9A0`, `0x27FA40` | Every list position 0..199 returned its correct native node, exact title and bank index; position 200 returned null |
| `0x329F20` viewport clamp | Every selected offset 0..199 retained a valid five-row playlist window |

1,004 native calls completed, each bounded by 100,000 instructions and one second,
with a required return sentinel. Largest call: 19,075 instructions. Evidence is
`.scratch/bounded.json`; the executable experiment is a standalone unittest.

**Exact limits:** the playlist displays five rows at once; the disc collection
render path inspected in the corpus uses four rows at once. These are viewports,
not a 200-item ceiling. The pool holds 400 nodes. Saved collection/song indices
and the saved playlist cursor are one byte each. The metadata writer splits
collections at 256 songs, but persisting a cursor beyond 255 would truncate in
retail; this is an explicit limit for libraries larger than the 200-item target.
No 400-item gameplay or cursor-persistence claim is made. Two-track `femusic`
refuses because the retail random branch divides by `N-2`; one track works by
the unsigned modulo contract, and 3..400 are accepted within other budgets.

## Realistic 200 x 3-minute estimate

Each input has 3,969,000 frames; block rounding produces 3,969,024 frames, or
4,465,152 stereo bytes. These are layout estimates, not 600-minute encoder
benchmarks or burnable-media compatibility claims.

| Variant | Encoded library | Virtual archive | Projected physical ISO | Pack F | Scratch budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Menu bank, stereo only | 893,030,400 B | 7,103,186,944 B | 7,627,702,272 B | 1,327,202,304 B | 8,587,841,536 B |
| Jukebox stereo plus mono twins | 1,339,545,600 B | 7,239,526,400 B | 7,776,137,216 B | 1,463,541,760 B | 9,182,791,680 B |

Mono adds 446,515,200 bytes. Both F extents remain below 2 GiB; both encoded
libraries satisfy the 2 GiB minus one total budget. Growth appends the whole F
file, explaining why physical ISO growth exceeds just the net music delta.

## Validation commands and results

All tests use standalone unittest execution. The optional acceptance switch is
intentional: normal CI does not allocate multi-GB retail image copies. Missing
retail evidence or Unicorn produces precise skips in the new evidence tests.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_music_banks.py` | 15 passed; synthetic growth/shrink, 200 count, same-count, replay, cross-pack/partition-relative layout, retained audio, prior named growth and outer edits, malformed WAV/descriptor/IMA, stale source/recipe/destination, budgets, failed twin, interrupted archive, failed verification/publication, nested shrink modpack round-trip and wrong node |
| `NFL2K5_MUSIC_EVIDENCE_DIR=.scratch python3 tests/mod_editor/test_nfl2k5_music_metadata.py` | 6 passed; ownership, immutable seals/retired suffix, corrupt bank pointers, SPECIAL/relocated-code composition, bounds and actual 200-node execution |
| `NFL2K5_MUSIC_ACCEPTANCE=1 python3 tests/mod_editor/test_nfl2k5_music_acceptance.py` | 1 acceptance test passed, four complete retail builds, 160.822 s on final full run |
| `python3 tests/mod_editor/test_modpack.py` | All 36 existing tests passed, 8.060 s |
| `python3 tests/test_xbox_ima_encoder.py` | All 11 existing codec/reference/quality tests passed, 9.951 s |
| `python3 tests/mod_editor/test_nfl2k5_ausb_fixed_slots.py` | All 6 passed, 0.092 s; fixed an existing missing repository-path setup so this file runs plain/standalone |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | All 12 existing allocator tests passed, 31.867 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | All 10 passed with music metadata in setUpClass |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | All 11 passed with music metadata in setUpClass |
| Oracle manifest generation command below | 3,363 reservations from 39 observed XBE writer calls; includes full 64 KiB music owner |
| `NFL2K5_CAVE_MANIFEST=.scratch/music-cave-manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | All 28 passed; the current-stack manifest gate was also rerun against the final generated manifest and passed |
| CLI retail `inventory` | Parsed all 17 descriptor records successfully |
| Runtime import check | New core/CLI/operation modules imported with NumPy, Capstone and Unicorn deliberately unavailable |
| `python3 -m py_compile` on four new core modules and CLI; `git diff --check` | Passed |

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/music-cave-manifest.json
```

The protected release manifest is unchanged. Claude must regenerate it after
integration; source-drift refusal remains intact. Tests and tooling do not bypass
that guard. Local generated-manifest source fingerprints were checked against
the final source files.

## HYPOTHESIS, known gaps, and Noah's witness list

The 200-song bank, immutable metadata, list pool and scroll lookup are proved
offline to the boundaries above. Actual Xbox loader acceptance, memory usage,
streaming, audible transitions and every screen's scheduling are unwitnessed.
This service rebuilds `femusic` or paired `cribmusic`; it does not replace timed
loading/show cues or provide a new all-screen shuffle controller. The existing
random formula and profile playlist policy belong to the parallel tier-1 work.

Canonical WAV is the backend import contract; compressed input conform, Music
panel UX and project asset embedding are protected/parallel integration work in
`WIRING.md`. The service preserves earlier edits and composes XBE owners, but
there was no played full build with SPECIAL and a 200-song bank together. Old
playlist identity checksums may become stale after title changes. Old saved PA
trim endpoints are not clamped by this job. Use a recreated playlist and fresh
clips for the first witness, then exercise stale state deliberately. Do not
advertise safe migration of arbitrary existing playlists/PA clips.

No row is witnessed. For each pass record platform, source/output hashes, recipe,
profile state, track index, transition and observed result:

1. Cold boot the 200-track menu image on the intended platform. Check logo and
   ordinary menus; identify first, middle and last tracks, let boundaries finish,
   and check the volume slider/mute, channel order, clipping and absence of gaps.
2. Enter/leave Quick Game setup, options, Franchise desk/calendar/rosters/draft,
   Crib, jukebox and back. Record unsupported transitions separately. Check no
   duplicate stream, hang, memory failure or unwanted restart.
3. On a fresh profile, browse the added free-collection entries and select track
   199. Fill a 200-song playlist, scroll from first to last and back, save/reload
   with item 100 and item 199 selected. Verify title, artist and duration text.
4. Repeat on an existing profile with purchased/locked collections. Check that
   credits, purchase flags and collection availability remain correct. Recreate
   stale title-checksum playlist entries and verify the resulting saved list.
5. For jukebox twins, compare stereo jukebox playback and mono Stadium Music
   Manager previews of first/middle/last. Replace longer and shorter songs; test
   fresh trims, then old saved clips whose ends exceed the new duration. Record
   the exact failure or clamp behavior; no clamp is claimed here.
6. Boot/play a combined build with SPECIAL, practice-squad, relocated kickoff,
   roster and texture edits plus music. Verify both the earlier edits and music,
   then rebuild the same recipe and confirm no extra append or size increase.
7. Try a realistic 200 x 3-minute library with/without twins on the actual target
   medium. Check sustained streaming, boundary crossings, available memory and
   load times. Larger-image arithmetic does not certify physical-media support.
8. After Claude wires the panel, on Linux/macOS/Windows import/conform a batch,
   cancel during encoding and archive copy, close previews, save/reopen the
   project, export/apply a recipe/patch, and reopen output. Check old destination
   survives failed builds and every reader closes before replacement.

## Commit scope

Only the explicit source/helper/test/CLI/documentation paths listed in the final
commit are included. `ASTRA_BRIEF.md`, `.scratch/`, protected files and parallel
Music panel/policy/catalog files are excluded. No push.

The requested normal branch commit was attempted with explicit paths, but Git
could not create its worktree `index.lock`: **Read-only file system**. Per the
brief's authorized fallback, the commit is created in an isolated local Git
repository under `.scratch/` and exported to `.scratch/music-banks.bundle`.
The working files remain in place. The bundle contains the single commit above
this worktree's original HEAD, with only the 19 explicit deliverable paths;
neither the brief nor scratch artifacts are included in its tree changes.

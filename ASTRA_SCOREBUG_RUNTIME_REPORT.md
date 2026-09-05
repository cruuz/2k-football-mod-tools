# Runtime scorebug, r61b

**EXPERIMENTAL / UNWITNESSED.** Implemented native team-panel binding, remaining
timeout dashes, score flash, down-and-distance refresh through the native slide,
and play-clock colour below five seconds. The runtime owns allocator RX code and
RW state; the companion compiler installs actual native textures in the HUD
collection. No emulator, GUI, audio, network, kernel boot or played-game witness
was used. Bounded Unicorn execution is an offline proof, not a gameplay witness.

All requested implementation and offline proof work is complete. Protected
product integration is handed off in [WIRING.md](WIRING.md), as the brief
requires. The allocator itself is unchanged. The full reservation manifest was
generated privately and tested; the protected checked-in manifest is unchanged.

## Resource decision and native evidence

**PROVED within static analysis and bounded native execution:** the scene's
material `+0x30` stores a native texture descriptor returned by the game's lookup.
It cannot simply point at P8 bytes in the new read-only code page. Native
registration/relocation rewrites the serialized object and descriptor pointers.
The selected implementation appends ordinary native TXTR resources to the same
HUD outer that contains the scorebug scene. The game's existing resource loader
owns their allocation, relocation and cleanup.

Relevant pinned USA executable paths, also identified in the read-only Ghidra
corpus under `research/functions/nfl2k5`:

| Native address/path | Contract used and evidence |
| --- | --- |
| `0x43A20`, `0x438D0` | Collection reader checks the supplied end offset and advances by each wrapper's stored length. Bounded execution continues past the old end, advances through all 264 appended wrappers, and stops at the new end. There is no fixed 139-chunk loop bound on this path. |
| `0x43E30 -> 0x43D20 -> 0x44DA0 -> 0x34DF0 -> 0x34C10` | Actual native registration and relocation execute against compiler-produced system/video buffers. Tests verify name, descriptor, pixel and palette relocation and native lookup-list registration. |
| `0x449E0 -> 0x443D0 -> 0x30C40` | Native UTF-16 name lookup returns the loaded descriptor. The hook uses these instructions, not a test replacement lookup. |
| `0xFC1A0`, `0xFBC70` | Native scorebug initialization and material-name lookup execute against an explicit scene fixture. Home uses `hscore_buga`; away uses `zscore_buga`. |
| `0x61C50`, `0x61C60` | Home/away contexts are `0xB30864` / `0xB30A58`; the asset-code string pointer is at `+0x10C`. The adjacent native city/score callbacks establish side orientation. |
| `0xB81C0` | Native timeout reset writes the count at `+4` in the score objects referenced by `0xE5FC28` and `0xE5FC68`. The runtime reads those same counts. |
| `0xFC7D0`, `0xFCE70`, `0xFC9C0` | Native down formatter and slide/visibility driver. Tests execute the actual driver and patched call site through the visibility update. |
| `0xFBB10` | Native play-clock formatting rounds upward. Runtime urgency uses the underlying seconds, so 4.9 seconds is red while native text can still read `:05`. |

The native loader also has the ordinary allocation/cleanup paths (`0x44E60`,
`0x44DC0`). Their existence is static evidence; actual asynchronous I/O,
allocation lifetime and GPU consumption were not executed end to end. The
collection-reader test supplies I/O completion and isolates its handler work;
the registration test separately supplies an allocated heap and video base.

The compiler generates 264 textures: 32 team identities, two orientations and
four timeout counts, plus eight neutral variants. Each is a swizzled 128x32 P8
texture with one mip, a 128-byte system buffer, 4,096 pixel bytes and a 1,024-byte
palette. It reuses the pinned retail descriptor template and existing quantizer,
swizzler and validator. Uncompressed 5,280-byte wrappers require no VC-LZ scratch
buffer. Home mirrors the gradient orientation while preserving logo orientation.
All team pixels are derived from the user's pinned retail source artwork.

HUD outer 346 grows from 2,977,184 to 4,371,104 bytes. The append is 1,393,920
bytes; sector-aligned pack growth is 1,394,688 bytes. Pack 0 grows from
193,710,080 to 195,104,768 bytes. System/video bytes total 1,385,472 before native
allocation overhead. Actual memory pressure remains unwitnessed.

All 139 existing chunk wrappers retain their offsets and sizes. Only the
fixed-span scorebug scene and atlas contents change within that prefix. The
existing outer-index entry grows; later virtual archive offsets and pack-0 block
count shift by the same sector count. Tests check all 4,323 entries, retained
pack-0 tail bytes and the physical mapping of assets in other packs. No PLAY or
ROST records are edited. Full HUD/index fingerprints deliberately refuse an
unknown or partially converted collection, including an already-installed
neutral v7 HUD. Rebuild from the supported base to switch modes.

## Runtime hooks and event behaviour

The hook module is
[`nfl2k5_scorebug_runtime.py`](mod_editor/core/nfl2k5_scorebug_runtime.py).
Public `status(payload)` returns retail/applied/foreign; `apply(payload)` returns
immutable bytes and a receipt. Mixed code, hooks, data, allocator layouts or
native ABI guards refuse before output mutation. Applied replay returns the same
bytes. Every section digest is repinned through the existing helper.

| Hook | Pinned displaced bytes | Native continuation |
| --- | --- | --- |
| Setup call at `0xFCE56` | `e845f3ffff` | Calls `0xFC1A0` exactly once, then performs binding and clears the per-scene state. |
| Update call at `0xFCFA2` | `e819faffff` | Forwards the original float argument to `0xFC9C0` exactly once; native `RET 4` consumes the copy and hook `RET 4` consumes the original. |

After the native call, both hooks preserve general registers, EFLAGS and the
complete x87/MMX/SSE/MXCSR state using an aligned FXSAVE/FXRSTOR area. FNINIT
provides a private empty x87 stack even if the incoming stack is full. CLD is
local to the preserved flags. Frame-time scratch lives beyond the saved FX area
on the private stack, not in the return/GPR frame. Tests set a full x87 stack,
nontrivial SIMD registers and DF, then check register and stack preservation.

Setup reads the two native asset-code strings and accepts `00` through `30` and
`37`. Created-team context kinds 2/4, null strings, invalid lengths/characters and
unknown codes use `--`. Names are `sb37h3`, for example, or `sb--h3` for neutral.
All four timeout states per side are resolved once at setup. An individually
missing team texture retries its neutral equivalent. A missing descriptor is
stored as null and hides that material; no old pointer is retained. Setup binds
the current timeout count immediately and disables native hangtime element 2's
visibility writes to the repurposed home panel.

Each setup clears all 128 state bytes and remembers the scene. Updates require
the same nonnull scene and an enabled scorebug. This covers the explicit tested
setup lifecycle; it does not prove asynchronous destruction or pointer reuse in
every game mode. There is no private texture allocator or per-frame loading.

| Event | Runtime behaviour |
| --- | --- |
| Timeout count | Reads each real score-object count independently. Selects the cached 3/2/1/0 panel; invalid counts dim all three marks. Native resets to 3 or 2 are reflected on the next update. |
| Score change | Seeds without flashing on initial population. A later change to either score makes that score `0xFFFFD166` for approximately 0.18 seconds, then restores white. The other side remains independent. |
| Down/distance refresh | Compares down, ball/line Z positions, possession and phase with the previous sample. While the native down element is requested visible, a change restarts its native opening ramp at 1/30 open. An unchanged frame does not restart it. |
| Native slide | Bounded execution of `0xFCE70` through the patched update call advances position 1 to 3.5 on the first 1/60-second frame and reaches 30 within 12 frames, monotonically, with the material visible. |
| Play clock | Reads raw seconds at `[0xE60294]+0x10`. Enabled, visible, finite nonnegative values below 5 use `0xFFD0021B`; 5 or above, disabled/hidden, negative and NaN/infinite values use `0xFF111118`. |

The runtime changes existing writable HUD fields and material objects, and its
own state allocation. It never writes `.text` or the grown RX page at runtime.
The slide uses the existing visibility/ramp mechanism; field predicates and
unrelated callbacks are explicit stubs in the bounded driver test. Render order,
replay behaviour and animation feel still require Noah's witness.

## Allocator composition and ownership

Owner: `nfl2k5_scorebug_runtime`. Requests are 1,408 code bytes and 128 data bytes,
both aligned to 16. Actual code is 1,228 bytes, followed by reserved INT3 padding.
The existing allocator supplies one preloaded RX page and one preloaded RW page.
No new allocator API, retail cave or unreserved address was introduced.

Reserve the complete request union with `nfl2k5_xbe_space.apply(payload, requests)`
before applying either runtime owner. Adding an unreserved owner to an already
grown executable refuses and requires rebuilding from base. With both owners:

| Owner | Code VA / bytes | Data VA / bytes |
| --- | --- | --- |
| Existing boot-logo transfer | `0x14BA000` / 690 | none |
| Relocated dynamic kickoff | `0x14BA2C0` / 1,939 | `0x14BB000` / 10 |
| Runtime scorebug | `0x14BAA60` / 1,408 | `0x14BB010` / 128 |

Both installation orders produce byte-identical results and stable allocations.
The composed code allocation ends at `0x14BAFE0`, leaving 32 bytes at the page
end. The RX/RW pages remain entirely reserved by their allocator owner. Without
kickoff, scorebug code/data are at `0x14BA2C0` / `0x14BB000`.

Both shared XBE gate setups compose the complete ordinary stack, v7, the union,
relocated kickoff and runtime scorebug. The memory gate enumerates both code
owners and their permitted RW stores. The cave gate checks runtime hook ownership
and allocator evidence. Neither gate was weakened. The manifest recorder adds
full five-byte hook reservations, named code and unchanged zero-data spans.

The observed experimental ownership build produced **3,348 reservations from
42 writer calls**. It runs the real v7 atlas writer, then final XBE owners. That
temporary disc is an ownership fixture with no runtime-panel installation; its
receipt says so and the file was removed. The separate resource tests and private
witness disc prove the paired installation. The fresh manifest passes all 28
oracle tests with source-drift refusal intact.

`tools/nfl2k5_cave_oracle.py space-proof --allocated` now forwards the existing
allocator evidence API so the actual composed owner set can be checked. Its
result reports no encoded retail references and no foreign manifest overlaps
in the grown pages. This is an owned loader allocation, not a verdict that a
retail cave is free.

## Disc transport, previews and private artifacts

The working CLI is:

```sh
python3 tools/nfl2k5_scorebug_reference.py apply '<retail.xiso.iso>' '<output.xiso.iso>' --runtime
python3 tools/nfl2k5_scorebug_reference.py status '<output.xiso.iso>' --runtime
python3 tools/nfl2k5_scorebug_reference.py preview '<preview.png>' --source '<output.xiso.iso>' --runtime --matchup LV HOU --timeouts 3 3
```

Optional `--relocated-kickoff` reserves and installs both XBE owners. It is an
offline composition option; its gameplay alignment prerequisites remain the
existing build's responsibility. The final private witness disc uses runtime
scorebug alone, so Noah can first check this feature independently.

The installer preflights the resource/XBE pair before writing, appends and
verifies the full pack, switches its directory node, and uses the existing
generalized XBE writer. Ordinary write failures restore both directory nodes,
any same-size XBE bytes and the original image length. Injected failures at
pack data, pack node, XBE data, XBE node and same-size grown XBE writes all pass
whole-image hash/length rollback checks. Power-loss atomicity is not claimed.
The copy CLI publishes a closed, verified temporary with `os.replace`; source
aliases/symlinks are refused. Status reads do not regenerate artwork.

Private local artifacts, intentionally untracked:

| Artifact | Meaning |
| --- | --- |
| `.scratch/scorebug-runtime.xiso.iso` | Final runtime-only witness disc; runtime status applied, relocated kickoff retail. |
| `.scratch/scorebug-runtime.xbe` | Final executable installed in that disc, 12,029,952 bytes. |
| `.scratch/scorebug-kickoff-composed.xbe` | Separate final executable with both runtime owners for composition/evidence. |
| `.scratch/scorebug-runtime-manifest.json` | Fresh manifest used by the oracle suite; not the protected product manifest. |
| `.scratch/runtime_space_proof.json` | Actual composed-allocation proof. |
| `.scratch/disc_proof.json` | Complete source-prefix comparison and full source/target hashes. |

The final source disc is 6,300,499,968 bytes; output is 6,507,634,688 bytes. A
complete comparison proves that all source-extent bytes are identical except
10 changed bytes contained in the two eight-byte XDVDFS file-location/length
fields. Full SHA-256 values:

- Source: `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`
- Witness output: `87662b96a15a966cc65c196edebda6cead496a915a89d26d289ab92e248008c0`
- Runtime-only XBE: `3f4e763692dd6b5cef19bd81d4b74069c526bbfb96c42c8641e35915936e3730`
- Composed XBE: `f9f54ba67181627b43a264c41c4f13e8390398837bc465b55f9839f665349c5e`

All twelve committed PNGs render the compiled native SCNE triangles, material UVs
and decoded P8 resources. Text font rasterization is an approximation, labelled
on every image. These are static previews, not screenshots from a running game.

| States | Preview |
| --- | --- |
| LV/HOU, three timeouts | [LV_HOU.png](docs/scorebug_runtime/LV_HOU.png) |
| Two other palettes | [NO_MIA.png](docs/scorebug_runtime/NO_MIA.png), [BAL_PIT.png](docs/scorebug_runtime/BAL_PIT.png) |
| Timeout counts 2, 1, 0 | [2](docs/scorebug_runtime/timeouts_2.png), [1](docs/scorebug_runtime/timeouts_1.png), [0](docs/scorebug_runtime/timeouts_0.png) |
| Under-five clock | [4 seconds](docs/scorebug_runtime/clock_under_5.png), [4.9 seconds with native ceiling](docs/scorebug_runtime/clock_4p9.png) |
| Independent score flashes | [Home](docs/scorebug_runtime/home_score_flash.png), [away](docs/scorebug_runtime/away_score_flash.png) |
| Down opening ramp | [Refresh](docs/scorebug_runtime/down_refresh.png), [halfway](docs/scorebug_runtime/down_halfway.png) |

Each preview has a JSON receipt. The committed
[evidence.json](docs/scorebug_runtime/evidence.json) includes all 264 resource
names/hashes, pack/index pins, executable allocations/hooks, test results,
manifest source fingerprints and the complete disc comparison. It contains no
executable or native texture payloads.

## Exact verification

All commands below ran standalone with plain Python. Paths in the first column
are invoked as `python3 <path>`, except the oracle suite also uses
`NFL2K5_CAVE_MANIFEST=.scratch/scorebug-runtime-manifest.json`.

| Test file | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | 12 passed, 88.675 s |
| `tests/mod_editor/test_nfl2k5_scorebug_resources.py` | 5 passed, 75.228 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 11 passed, 12.684 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 12 passed, 25.864 s |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 53.279 s |
| `tests/mod_editor/test_nfl2k5_xbe_space.py` | 12 passed, 33.236 s |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame.py` | 11 passed, 8.699 s |
| `tests/nfl2k5_scorebug_layout_test.py` | 15 run, 4 skipped, 2.702 s |
| `tests/mod_editor/test_nfl2k5_scorebug_source_art.py` | 13 run, 3 skipped, 0.279 s |
| `tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` | 5 passed, 0.059 s |

Total: 124 tests, 117 passed and seven explicit legacy skips. Skips cover absent
developer exports/audit fixtures and the older opt-in emulation suite. The new
runtime suite ran all bounded proofs without skips. Missing retail evidence or
Unicorn results in explicit skips in portable runs; Capstone is not required by
the new runtime assembler or execution tests. The shared gates retain their
existing dependency skips.

Manifest command, successful:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/scorebug-runtime-manifest.json
python3 tools/nfl2k5_cave_oracle.py space-proof \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --manifest .scratch/scorebug-runtime-manifest.json \
  --allocated .scratch/scorebug-kickoff-composed.xbe \
  --json .scratch/runtime_space_proof.json
```

The new capability handoff JSON validates against the existing registry's
`$defs/capability` schema. Final whitespace and protected-path checks accompany
the explicit-path commit. The capability is `offline-writer-proved` with runtime
`not-tested`, never `runtime-proved`.

## HYPOTHESIS and Noah's witness list

**HYPOTHESIS requiring play:** the real kernel preloads the grown pages as
declared; the full asynchronous HUD collection is resident before setup; its
descriptors remain live for the scene; GPU palette/orientation matches the
decoded preview; extra resource allocation fits all intended game modes; the
sampled state fields produce the intended cadence in actual gameplay.

Noah should record mode, matchup, home/away orientation and observed result for
each item. Use the runtime-only private disc first, then an integrated build
with relocated kickoff and its existing gameplay prerequisites.

1. Cold boot and enter a game. Confirm boot art, HUD, field and menus load without
   a hang, missing asset or new memory failure. Repeat with a long game and
   after returning to menus.
2. Check LV away/HOU home, reverse them, then NO/MIA and BAL/PIT. Confirm team
   identity, colour, logo orientation, readable native abbreviations/scores,
   ESPN NFL corner and no mirrored or stale logo. Check the other native teams.
3. Select created/unknown teams and confirm neutral panels. Start another
   matchup without restarting the application, including after aborting a game;
   confirm both panels update and no pointer from the prior scene survives.
4. Spend timeouts independently on both sides through 3/2/1/0. Check halftime,
   overtime and any mode that initializes two timeouts. Marks must follow actual
   remaining counts without changing the opponent's marks.
5. Score by touchdown, extra point, two-point conversion, field goal and safety.
   Confirm the correct score flashes briefly once, settles to white and still
   shows native number updates. Initial scene population and menu resume should
   not invent a scoring flash.
6. Run ordinary downs, first downs, penalties, goal-to-go, turnovers and changes
   of possession. Confirm correct native text and one short opening slide when
   state changes, no repeated flicker during a stable play and proper hiding on
   transitions/replays. Confirm returning from replay resumes normally.
7. Let the play clock cross 5.0, 4.9, 4 and 0 seconds. Expect red below five raw
   seconds even when rounded native text still reads `:05`. Check huddle reset,
   timeout, pause/resume, disabled clock and quarter transitions for restored
   normal colour and visibility.
8. Check 4:3 and the supported widescreen path, low/high scores and long native
   text. Compare visual placement and slide with the labelled static previews.
9. On the fully integrated experimental build, repeat a game with both owners.
   Check both-direction kickoff lineup, hold, contact release and return, plus
   boot, SPECIAL/depth features and ordinary gameplay. Offline composition is
   proved; played coexistence is not.

## Delivery and scope decisions

The prerequisite `9a3b41d` was cherry-picked first, with additive WIRING and gate
resolutions, as isolated commit `787023f`. Shared Git metadata is read-only, and
the requested local fetch failed at `FETCH_HEAD`. Per the brief's explicit
fallback, commits use isolated Git metadata inside `.scratch`, reading the
existing object store without modifying it. The branch name in that repository
is `astra/r61b-scorebug-runtime`; the original shared branch metadata is intact.

The delivery bundle is `.scratch/scorebug-runtime.bundle`, containing the
prerequisite and implementation commits above base `d0bf583`. The current files
remain in this worktree. Inspect with `git bundle verify` and import the bundle
in a writable integration checkout. If v7 is already present, integrate only the
final implementation commit and resolve the handoff additions additively. No
push was performed. `ASTRA_BRIEF.md` and `.scratch` are not committed.

The small changes to the cave manifest recorder/CLI are necessary to record this
new owner and prove the actual union; they add no allocator behaviour. All
protected build, dispatcher, GUI, release, registry and checked-in manifest files
are left for Claude's integration. WIRING is the expressly required documentation
handoff. No executable resources or game-disc payloads are included in the commit.

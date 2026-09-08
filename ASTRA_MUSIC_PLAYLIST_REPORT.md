# r62 music playlist

**EXPERIMENTAL / UNWITNESSED.** Implemented the tier-4a playlist controller,
Music tab Playlist page, pinned native integration, and offline context policies.
Tier 4b is **partial**: individual submenu/replay routes and the actual draft
player remain unproved. There is no "all modes" claim. Protected Build/release
integration is delivered in `WIRING.md`, as instructed; it is not silently
implemented in protected files.

Work stayed in this worktree. No network, game emulator, graphical display,
audio playback, real disc/pack/save mutation or push occurred. Unicorn ran only
bounded instruction fixtures. Retail XBE input was read-only, 11,948,032 bytes,
SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
No test loads a disc or archive pack into RAM. The instruction fixture maps
about 23 MiB plus the XBE buffers; the large XBE gates retain their bounded
executable-only inputs. No test process approaches the 2 GiB limit.

## What was built and decisions

- `mod_editor/core/nfl2k5_music_playlist.py`: exact `status`, `apply`,
  `read_settings`, `Selection`, `selection`, `from_options`, `validate_source`,
  `reservations`, and allocator request APIs. Fifteen live hooks own 86 bytes.
  All complete dependency spans are pinned, normalizing only this owner's
  hook bytes. Independent older music policies and the 200-song RO metadata
  compose in either order.
- `tools/nfl2k5_music_playlist.S`, its assembler, and generated
  `nfl2k5_music_playlist_code.py`: reproducible relocated x86. No assembler,
  Ghidra corpus, Capstone or Unicorn is required by the runtime writer.
- `music_panel_qt.py`: Recordings and Playlist pages; off-by-default enable,
  individual song checks, outtakes switch, beds switch, visible select/clear,
  selected-count and zero/one-song explanations, validated JSON choices,
  atomic Save/Open choices, shell signals and source/operation lock handling.
  Existing audio editing, playback and policy signals keep their contracts.
- The shared gate union, manifest builder, and allocator's default
  allocation-evidence union include the playlist. A dedicated manifest test
  observes its real writer and every full hook/RX/RW/RO reservation. The
  protected cave JSON is unchanged.
- `reports/music_playlist_contexts.v1.json`: 22 named policy rows, each with
  its mapping evidence and an explicit unwitnessed flag. A ready capability
  object is in `docs/mod_editor/nfl2k5_music_playlist_capability.json` for the
  mandated protected-integration handoff.

Default selection is **7 femusic + 59 cribmusic recordings**, including all
12 spoken outtakes. Disabling outtakes leaves 54. The optional beds switch
adds **10 established background beds**: loadm:2, wrapupm:0..7,
halftimeaudio:3. It does not add the ten remaining short/unresolved presentation
slots, replace narration, or change how shows schedule their own music.

Records are `(bank pointer, u32 stream index)` in RO, with bank names in the
same RO allocation. Build preflight accepts validated source descriptor counts;
the runtime resolves the bank again and refuses null/-1 descriptors,
count >65536, invalid indices, zero geometry, and equal/reversed boundaries
before binding or enqueueing. Existing source descriptor validation remains
responsible for archive extent/codec consistency. This is not a new archive
writer or a runtime arbitrary-pointer validator.

The shuffle bag stores u16 record ordinals. Fisher-Yates consumes exactly
N-1 calls to the memo's **0x48BC0 -> 0x48B50 retail RNG** on a refill.
The bounded choice is unsigned `sample % remaining`; this retains the small
modulo bias when N does not divide 2^32. It is a permutation shuffle, not an
unbiased-randomness certification. The most recent RNG sample is retained in
our RW seed/sample word. The full generator and startup seed remain in the
retail writable RNG state, seeded by retail startup; this patch does not reseed
or copy its 55-pair generator into the 512-byte private allocation. A repeatable
private seed or profile-persistent playlist order is not provided.

At refill, if N>1 and the first item equals the preceding last item, swap the
first two bag entries. Zero enabled items stops cleanly; one repeats explicitly;
two alternates without modulo zero. A changed enabled mask invalidates the bag
and cursor. The list/mask starts from sealed RO choices, copied to RW at runtime.
An invalid/corrupt ordinal is refused before indexing the records. A different
on-disc selection requires a rebuild from a supported base; applying the same
selection is byte-idempotent and never appends another allocation.

## Position, stream and context policies

Ordinary menus, Crib and game background share one bag, current song, cursor,
pending completion and decoder. Ordinary context requests retain an active
song without enqueueing a duplicate. Native modal pause/resume helpers retain
the decoder position; a completion delivered while paused remains pending until
resume. Stops for loading, shows, explicit preview or player recreation preserve
the interrupted song and shuffle cursor, then **restart that song** on return.
There is no seek-position persistence across a destroyed stream or cold boot.

The native 0x2801A0 direct enqueue is adapted using the real range/packet
builders, existing volume controller and loop flag zero. The shared start
routine 0x280450 routes through it. Own completion packets carry generation
cookies: cancellation and stale/duplicate callbacks cannot consume the next
record. 0x27FF10's native completion call and the explicit HDD callback feed the
preview handoff; 0x280620 retains its complete retail volume update and dispatches
pending work through the shared enqueue. Missing-player cancellation stops with
an error state instead of recursively queueing more records.

The five 0xF6510 modes are explicitly handled: stop/show, menu, loading, Crib,
game. Unknown values are refused. A pinned profile-setting stop at 0xF64CD is
adapted so changing Crib Music settings cannot silently disable an explicitly
selected game-background override. No profile purchase, credits or playlist
record is written. The front-end player initializer invalidates the old stream
generation while preserving the bag/song on recreation.

Explicit disc/HDD jukebox preview suspends the background, plays the selected
preview using its native path, then resumes the interrupted background song at
its beginning. A late native preview completion is ignored after return. The
separate stadium manager/PA player is not hijacked. Native HDD I/O and a real
nonempty profile have not been executed in these fixtures.

Loading keeps F5430's loadm scheduler and its F5410 start path. Halftime entry
D90F0 suspends only the shared background; D9350 releases that exclusion after
the native halftime player closes. Its show body, cue order and narration are
unchanged. Wrap-up retains 28F7F0's mode-0 stop and existing mode restoration.

**Corrected research assumption:** neither recovered 165C20 caller requests
`drafta`. F6124 passes the UTF-16 `coachambience` at E6C008, and 12D503 passes
`coachambience` at E761A4. These are read-only retail-byte observations. We do
not hook that initializer as a supposed draft bed controller. Actual drafta
routing remains unresolved and is not certified by the context suite.

## Allocation and coexistence

The existing beta-62 budget fixture already contains this exact owner's three
rows. Before implementation, ran:

```text
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json
```

It passed; the local plan is `.scratch/playlist-budget.json` (human-readable
planner output despite that scratch suffix). No budget fixture or allocator
page count changed.

| Kind | Reserved | Content / maximum touched |
| --- | ---: | ---: |
| RX | 2,048 B | 1,545 B code, remaining bytes INT3 padding |
| RW | 512 B | up to 296 B for 100 records; all 512 B zero on disc |
| RO | 1,024 B | default content through byte 719; 100 records through byte 991 |

The 8-byte record representation caps the playlist at **100 records** under
this RO budget. It can address added bank indices after `validate_source`, but
does not automatically turn a grown 200-song bank into a 200-entry shuffle.
The existing 200-song metadata section remains compatible and untouched.
Extending playlist capacity needs a new compact record/state version or a new
approved budget; no extra memory was taken here.

All new runtime writes are in owned RW or the existing writable controller
fields. Code and strings/records are read-only and outside `.text`; no retail
cave or unreserved address was used. Section digests are repinned through the
existing helpers. Foreign/mixed hooks, code, RO, nonzero on-disc RW, allocator
seals and dependent retail bytes refuse before mutation.

Both complete XBE gates compose this owner with every current owner, normal
and reverse order, including music policy and the 200-title metadata owner.
The cave gate had the documented base-stack assumption that a test class named
"normal" implied legacy allocation. It now checks `space.is_scaleout(patched)`
because the real new-owner union selects v3 automatically. Legacy zero-reference
assertions remain; v3 still retains its raw pointer-shaped candidates and tests
for no retail mapping overlap. No candidate was reclassified as a free cave.
The unrelated allocator-scaleout/ordering suites were not changed.

## Exact final validation

Commands ran from this worktree as standalone unittest files with plain Python.
Qt was offscreen and playback was mocked. Logs are `.scratch/playlist-*.log`.

| Command | Tests | Result |
| --- | ---: | --- |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist.py` | 13 | PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist_contexts.py` | 4 | PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | 2 | PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_music_panel_qt.py` | 7 | PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_policy.py` | 8 | PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_metadata.py` | 6 | PASS |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 51 | PASS |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 63 | PASS |

**154 passed, no skips or failures in the final runs.** Initial test failures
caught incomplete synthetic descriptor geometry and the inherited legacy-layout
assumption; they were repaired and the final relevant suites rerun.
Additional passing checks: assembler `--check`, Python compilation, allocator
budget planner, and `git diff --check`.

**PROVED / bounded:** complete 0/1/2/66 cycles, 100-record cycles through the
actual retail RNG with synthetic state, no refill repeat, source-bank enqueue
for every one of the 66 records, actual native packet and range builders,
callback cookie transport, callee-saved registers and stack ABI, pending modal
completion, stale callbacks, mask changes, invalid indices/descriptors/ranges,
profile-stop adaptation, recreation and preview-return contracts. Each invocation
has a 30,000-instruction / 200,000-microsecond limit and must reach its return
sentinel. RX/RO pages are protected; a memory-write hook checks indexed writes.

Stubs replace resource lookup, binding/volume/queue I/O, DirectSound pause/resume,
loading start, game-channel switching and HDD stop. The 100-record RNG test
executes the actual generator; other tests supply deterministic RNG samples.
The halftime test runs actual entry/exit with an absent show descriptor while
separately proving the full show body byte-identical. Preview guards and
completion contracts are bounded; real nonempty native profile/HDD streaming is
not. Native packet/range arithmetic is executed, not stubbed.

**HYPOTHESIS / unproved:** the exact mapping of each franchise, season,
tournament/practice, Crib and replay screen to its nominated shared/modal
contract; actual drafta routing; loader/DirectSound/stream timing and volume;
real profile/HDD preview; audible stereo/mono/surround and PA coexistence.
The 22-row suite tests the declared transitions, and explicitly leaves draft/PA
rows unintegrated. It does not turn a family-level contract into proof of every
screen route. No row is witnessed by Noah.

## Noah's witness matrix

For every row record output image hash, project/playlist choices, platform,
source/profile state, exact slot/transition, and pass/failure. **All unwitnessed.**

| Memo witness row | Required observation for this delivery |
| --- | --- |
| Baseline and four-byte redirect | Compare shuffle off, old jukebox redirect, and new shuffle. Cold boot without a profile, fresh profile, existing profile. Identify both menu and jukebox songs; check volume/mute and end-of-track advance. |
| Availability | With independent unlock off/on, check all collections, credits and purchase state. Shuffle bypasses background collection purchase selection without writing the profile. |
| Contexts | Main menu, Quick Game setup, options, Franchise desk/calendar/rosters/free agency/draft menus, season/tournament/practice entry, Crib entry/exit and jukebox preview, each recorded separately. Check duplicate streams, silence, unwanted starts and controls. |
| Existing retail playlist/HDD | All three Crib Music settings, empty/nonempty disc and HDD playlists, missing HDD library. Verify intentional background substitution, temporary preview, one completion return, and absence of stale callbacks. |
| Fixed replacements | Distinct replacement in femusic:0 and first/middle/last crib pairs. Verify the shuffle reaches their actual encoded replacements and their neighbors remain intact. Existing fixed-slot editor tests remain applicable. |
| Free-length pairs | Longer/shorter first/middle/last songs must complete once, with no early/late advance. Separately test old PA trims; this patch does not add trim clamping. |
| Growth/composition | Combined build with SPECIAL, practice squad, scorebug, roster/texture edits and music banks. Boot, exercise every other patch, reapply and confirm no size increase. |
| Final shuffle | Full 66-song cycle and refill, outtakes off at 54, beds on at 76, plus 0/1/2 songs. Verify same song/cursor across menus/Crib/game, exact modal resume, and documented restart after destroyed streams. Repeat across cold boots without expecting persistent order. |
| Presentation/PA | Loading, halftime, wrap-up and draft transitions; narration timing and bed duck/stop, stereo/surround, PA/crowd intelligibility, no doubled background. Draft routing must be recovered before promotion. |
| Editor portability | Linux/macOS/Windows: checkbox synchronization after Claude wiring, individual song choices, save/open JSON, project reopen, combined Build/export/apply and reopening the output. Missing/corrupt choices refuse without partial updates; closing/canceling releases handles. |

Known gaps are deliberately visible: protected integration and coordinated
manifest regeneration; individual screen-route proofs; actual draft bed mapping;
100-record playlist cap; private seeded/profile-persistent order; real Xbox/HDD
streaming, audio, macOS/Windows and boot witnesses. The implementation does not
claim complete tier 4b or a packaged release.

## Commit delivery

Only the explicit feature/helper/test/documentation paths are staged.
`ASTRA_BRIEF.md`, `.scratch/`, protected files and other GUI panels are excluded.
No push. The final delivery records whether Git could write its worktree
metadata or required the brief's authorized local bundle fallback.

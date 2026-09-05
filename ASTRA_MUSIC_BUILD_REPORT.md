# ASTRA music build report

2026-09-05. Branch `astra/r61b-music-build`. Observed starting HEAD:
`d0bf583d0bc5027c92dd7150aa6c4eed9a74ee70`. Scope: ASTRA_BRIEF tiers 1 and 2.
All music runtime behavior is **EXPERIMENTAL / UNWITNESSED**.

## Delivered

- `mod_editor/core/nfl2k5_music_policy.py`: independent, exact-pinned menu,
  availability and optional UserList policies. Four menu-pointer bytes,
  fourteen four-byte availability fields, twelve UserList bytes, plus the
  existing .data digest. The full option set owns 72 field bytes. No code,
  cave, allocated memory, purchase bits, profile or save is changed.
- `mod_editor/core/nfl2k5_music_catalog.py`: 66 core logical rows and 20
  presentation rows, representing 145 stored streams. Seven menu recordings
  use Menu 01..07; presentation cues use Loading, Wrap-up, Halftime and Draft
  slot numbers. The 59 jukebox titles/artists/collections are transcribed from
  the XBE; twelve are explicitly spoken outtakes. Every jukebox row links its
  stereo stream to the corresponding mono stadium stream.
- `mod_editor/studio/music_service.py` and `gui/music_panel_qt.py`: a Music tab
  backed by the existing StudioSession audio transactions. Default 66-row view,
  optional presentation rows, source/current playback, mono preview, WAV export,
  local current-set ZIP with manifest/M3U, ordered file drops, assignment review,
  fit review, batch cancellation, Restore, shared Undo and local Music Redo.
  Encoded-preview playback always requires an explicit Play action.
- `audio_conform.conform_music`: 22050 Hz, target channels and exact slot frames;
  useful-content RMS matching; maximum +12 dB gain; -1 dBFS peak ceiling;
  silence/near-silence guards; silence padding; a 50 ms end fade on trim (or
  the whole slot when shorter). Reports source/slot/trim/pad/fade durations,
  input/baseline/output RMS, applied gain, capped gain and peak limitation.
  Mono twins are arithmetic (L+R)/2 after stereo gain, with a near-silence
  cancellation notice. Exact-shape WAVs still receive the selected RMS policy.
- Native 22050 Hz PCM16 mono/stereo WAV fit works without FFmpeg, including
  length fitting and channel matching. Other rates and formats reuse the
  bounded existing FFmpeg/FFprobe decoder. Added optional cancellable process
  execution, with child kill/reap before temporary-file cleanup. Existing
  conform callers retain their prior behavior.
- `mod_editor/core/nfl2k5_music_build.py`: fresh copy construction using the
  commentary tool's AUSB parser and pack-span mapper, plus the existing
  fixed-slot encoder/validator. All twins and expected source bytes preflight
  before writes; whole-source copy and hash recheck; exact write read-back;
  one final publication after all handles close. Unrelated staged edits remain.
  Source aliases, existing destinations, malformed/foreign/mixed slots,
  interrupted work and incomplete twin requests refuse without publishing.
- Format-2 authored export uses existing type-0 byte_runs/v1, minimum reader 2,
  and recipe `music_fixed_slots` schema 1. Each music payload is a complete
  authored encoded replacement divided only at physical pack seams, plus any
  generated policy fields/digest. No original bank, neighbor, coalesced source
  suffix or cached original is included. Full projected-result verification
  refuses undeclared edits. Modpack descriptions now show plain music text.
- Fixed-stream validation accepts optional cancellation. The commentary bank
  constructor now closes its descriptor on failures at every parsing stage,
  including a bad later bank descriptor. Tests cover that leaked-reader case.
- Both composed XBE safety gates include the fully selected music owner.
  `WIRING.md` retains earlier handoffs and adds the exact protected dispatcher,
  four status maps, BuildPlan/presets, panel lifecycle, allowlist/runtime closure,
  captions, NEEDS_IMAGE and capability-record instructions.

## Decisions and boundaries

The immutable original is the selected source's encoded slot and decoded WAV,
including a deliberately modified source. It is captured privately and checked
against source-cache file identity. Repeated replacements never replace it.
The shared session is the only edit/Undo owner; Music caches are derived state.
A failed/cancelled later file, second twin or session manifest publication
leaves the edit and Undo ledgers intact. A single twin changed through another
audio surface displays Needs attention and blocks paired build/export until
Replace or Restore repairs the row.

`status` reports retail/applied/foreign. Independent legal options can differ;
partial unlock sets, partial UserList words, foreign context/name pins, and a
UserList override without the menu redirect are foreign. `Selection` provides
requested-option status so dispatch does not incorrectly skip a menu redirect
when only unlock was already applied. Applying is byte-idempotent and adds
selected options. Retail/off preserves the source; removing a policy requires
starting from the original XBE/image. All presets are to leave music retail/off.

The normal `.2k5mod` and canonical Studio build project already retain both
conformed authored WAVs. The dedicated `.2k5music` subset also carries fit/input
metadata, policies, source hash, original-slot hashes, encoder identity and
expected encoded hashes. Reopening verifies source and all assets, reproduces
the exact encoding, validates display metadata and commits once. It replaces
the music subset while preserving unrelated session edits. Originals are
reconstructed from the verified recipient source. Ordinary `.2k5mod` does not
carry Music-specific fit/policy metadata; use `.2k5music` to retain it. No shared
project-schema change was made implicitly.

The standalone panel build/patch buttons operate on the music subset. Music
WAVs also feed the normal shared-session build through its existing ausb_audio
provider. The protected combined-build integration is specified in WIRING,
including how to avoid writing the same slots twice or discarding earlier
roster/texture/XBE edits. No protected shell, build, capability registry,
allowlist, CI, release-tag or reservation file was edited. Consequently the
new tab is implemented and tested but still awaits the mandated Claude mount
and release integration; no packaged application was built here.

Tier 3 free-length banks and tier 4 allocator playlists remain deferred by the
brief. This tier keeps source allocation, boundaries, archive layout and slot
lengths. It does not combine the seven menu recordings into the jukebox bank,
implement a shuffle bag, change the first selected track, override show timing,
edit display-duration strings or claim every game context. There is no allocator
or cave requirement for these tiers.

## Evidence: PROVED versus HYPOTHESIS

**PROVED / bytes and offline tests:** retail XBE identity
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`;
the exact policy pins and unchanged surrounding collection/context words;
all 59 title/artist/collection transcriptions; digest repinning and bounded
write union; composition with the existing grown XBE owners. The source XBE
was only read; modifications existed in process memory for tests.

**PROVED / read-only real inventory:** the real XISO was present. All seven
music banks matched descriptor/count/channel/outer ownership. Their 145 streams
have whole-block boundaries, totaling 376,582,716 encoded bytes. Every stereo
cribmusic boundary is twice its crib22 mono boundary. No real song was played,
exported, rewritten or claimed audibly correct; no real ISO build was produced.

**PROVED / synthetic tests:** both twin writes, a mono stream crossing a pack
seam inside a codec block, full unaffected-byte preservation, raw and extracted
game-partition forms, failed second twin and malformed IMA refusal, source
mutation detection, output rollback, idempotence without growth, encoded-preview
hashes, authored-only projects/recipes, generic format-2 apply and already-applied
recognition, normal Studio project integration and offscreen Qt lifecycle.
RMS, peak, trim, silence, downmix and cancellation checks use generated PCM.
WAV/MP3/FLAC/OGG decoding/resampling was tested with generated local input.

**HYPOTHESIS / runtime gates:** DirectSound reconfiguration after the pointer
redirect, audible completion/advance, exact submenu coverage, new-profile/shop
consistency with zero keys, HDD/UserList interaction, stadium PA consumption,
and presentation timing. Research predicts the retail random order and fixed
initial index; this implementation does not turn the prior bounded integer
research into a game witness. Nothing is marked witnessed by Noah.

## Exact validation run

Each file below was executed separately with plain `python3 <file>` from this
worktree, without PYTHONPATH. Qt used `QT_QPA_PLATFORM=offscreen`. The final
Music service test was rerun after its final immutable-export snapshot change.
Local logs are in `.scratch/validation-*.log` and `.scratch/music_validation.json`
and are intentionally not committed.

| Command suffix after python3 | Tests | Final result |
| --- | ---: | --- |
| `tests/mod_editor/test_nfl2k5_music_policy.py` | 8 | PASS |
| `tests/mod_editor/test_nfl2k5_music_catalog.py` | 4 | PASS |
| `tests/mod_editor/test_music_conform.py` | 7 | PASS |
| `tests/mod_editor/test_music_service.py` | 10 | PASS |
| `tests/mod_editor/test_nfl2k5_music_build.py` | 8 | PASS |
| `tests/mod_editor/test_music_panel_qt.py` | 6 | PASS |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 10 | PASS |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 11 | PASS |
| `tests/mod_editor/test_audio_conform.py` | 17 | PASS (1 precise evidence skip) |
| `tests/test_game_audio_convert.py` | 15 | PASS |
| `tests/nfl2k5_commentary_swap_test.py` | 22 | PASS |
| `tests/mod_editor/test_nfl2k5_ausb_fixed_slots.py` | 6 | PASS |
| `tests/mod_editor/test_nfl2k5_ausb_build_adapter.py` | 10 | PASS |
| `tests/mod_editor/test_modpack.py` | 36 | PASS |

**170 tests run: 169 passed, 1 skipped, 0 failures.** The one skip is the older
AUDO real-capacity cross-check because
`reports/assets/nfl2k5_audo_import_capacity.json` is absent from this checkout.
It now gives that precise standalone skip; synthetic strict-WAV and Music gates
still run. Two older AUSB test files now add the repository root before imports
so they satisfy the brief's plain-python standalone requirement.

Additional successful checks: Python compilation of all new product modules
and changed conversion helpers; `git diff --check`; a lean runtime smoke with
NumPy imports deliberately unavailable and FFmpeg discovery disabled, importing
all five Music modules, loading the lazy commentary writer closure and creating
an empty offscreen MusicPanel. That smoke did not play audio. No network,
emulator, visible GUI, original-disc mutation or push was used.

## Noah's witness matrix for tiers 1 and 2

Every row is **NOT WITNESSED**. For each observation, record output image hash,
project/patch hash, platform, source/profile state, exact slot and pass/failure.
Do not promote a context from another context's result.

| Tier / pass | Required observation |
| --- | --- |
| 1: Baseline and four-byte redirect | Cold boot without a profile, then fresh and existing profiles. Hear an identifiable jukebox recording in the main menu; let several tracks finish, including index 58 followed by another valid track. Check menu volume and mute. Compare to baseline. |
| 1: Availability | Fresh profile with no purchases: browse and select all 18 collections and all 59 entries. Confirm credits and purchase bits were not spent/awarded. Reboot/reload and check shop/jukebox consistency. |
| 1: Contexts | Main menu; Quick Game setup; options; Franchise desk/calendar/rosters/free agency/draft menus; season/tournament/practice entry; Crib entry/exit and preview. Check duplicate streams, restarts, silence and controls. Record unsupported screens separately. |
| 1: Optional UserList | Compare override off/on with empty and nonempty disc playlists, HDD selections and missing HDD library. Exercise all three Crib Music settings. Verify the intentional playlist substitution, actual order, menu/in-game distinction and recovery on return. |
| 2: Fixed replacements | Distinct supplied content in femusic:0, jukebox first/middle/last pairs (0/28/58), loadm:0 and at least one wrapupm, halftimeaudio and drafta slot. Check each audible identity and neighboring originals. |
| 2: Stereo/mono and fit | Compare encoded editor preview to game output, L/R order, mono manager preview, stadium situation playback, pitch/rate, default RMS match, disabled RMS match, peak/gain notices, end fade and silence padding. Use an anti-phase source to verify the mono cancellation notice. |
| 2: Restore and history | Replace a song twice; Restore both versions; Undo/Redo through replace and restore. Build again from the selected source and confirm exact original music returns. Reopen original/current views and compare first/middle/last neighbors. |
| 2: Presentation/PA | Commentary/show narration retain timing, beds duck/stop properly, and PA/crowd stay intelligible. Check stereo/surround configurations and show transitions. No all-screen scheduling change is intended. |
| 1+2: Composition | With Claude's protected wiring, build music alongside SPECIAL/practice-squad and ordinary roster/texture edits. Boot and verify all edits remain. Reapply the same music patch and verify size does not grow. |
| 2: Editor portability | Linux/macOS/Windows: drop WAV/MP3/FLAC/OGG; reorder and cancel a batch; test overflow refusal; compare file/slot/trim durations; play current/original; Restore/Undo/Redo; save/reopen .2k5music and normal .2k5mod; export current set; build/apply .2k5patch; reopen output. Confirm missing-FFmpeg explanation/native WAV fallback and that closing preview releases handles before build/publication. |

## Remaining limits

Protected registration/build/release integration is intentionally handed off,
not edited around the brief. Main-project fit/policy metadata uses the dedicated
Music project format as documented. Outputs use fresh names rather than an
overwrite UI. Only Linux offscreen/software validation ran; macOS, Windows,
console/HDD behavior, listening and the complete real-image build remain Noah's
witnesses. Friendly identities for seven menu tracks and twenty presentation
slots remain unresolved. Fixed-length content does not certify later growth,
free-length saved PA trims, allocator playlists or all-context shuffle.

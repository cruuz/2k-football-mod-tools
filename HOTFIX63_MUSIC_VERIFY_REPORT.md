# Beta-63 Music fresh-rip verification — 2026-09-09

**Decision:** no production fix is justified by the fresh-rip Music exception
reproduction on this branch. The existing beta-63 fixes accept the opened
disc's cache folder and keep readiness checks from raising. This change adds
reproducible verification and this report; it does not change product behavior.

Verified base: `9c17c538` (`beta-63`, `1.0.0rc87`), branch
`astra/hf63-music-verify`. Both `ef495b4e` (folder acceptance) and `ad845272`
(readiness guard) are ancestors of this base.

## Report and scope

The supplied Discord dump's `2k5-bugs.jsonl:42` records Mud's 01:31 report,
edited at 02:06: “Music error, comes up in stadium music but not crib jukebox.”
The following entry references a video; the text supplies no traceback.
The separate `BETA621_FIELD_REPORT_2026-09-08.md` supplies Coach Edwards's
five matching cache-key exception stacks. The tests below establish that
**that editor exception is fixed in 63**, including the stadium slots. They
cannot establish that Mud's in-game symptom has the same cause.

No emulator, visible GUI, audio playback, retail disc build, or retail audio
replacement was run. The audio-origin preparation pipeline was exercised end
to end with a small synthetic source; the actual retail replay exercised
opening, selecting, refreshing and reopening with **unprepared** audio-origin
inventories, which is the reported crash state. The full retail origin scan
and Windows execution were not performed on this Linux host.

## Stadium versus jukebox paths

| Operation | Jukebox | Stadium-specific work |
| --- | --- | --- |
| Catalog | `cribmusic`: 59 stereo ranges, descriptor outer 3/chunk 222, external outer 3123 | `crib22`: 59 mono ranges, descriptor outer 3/chunk 223, external outer 3122; one twin per jukebox row |
| Music selection/preview | `MusicPanel.selection_changed`; primary target | The mono checkbox selects `row.twin` in `MusicService.playback_path`; same service and original/changed-content lookup |
| Replace existing recording | Conform to stereo primary shape | `MusicService.prepare_batch` reads the mono original, downmixes PCM, checks phase cancellation, encodes the mono shape, and submits both targets in one authorized session transaction |
| Audio Cues selection | Stereo range from the soundtrack collection | Separately selectable mono range; same `AudioPanel` refresh/readiness and facade replacement pipeline |
| Add songs/library build | A `cribmusic` library recipe | `nfl2k5_music_banks` builds and validates both `cribmusic` and `crib22`, including the stereo/mono boundary relationship |

Source references on the verified base:

- `mod_editor/core/nfl2k5_music_catalog.py:12,133,145`: exact banks,
  doubled stereo boundaries, paired logical rows.
- `mod_editor/gui/music_panel_qt.py:789,904` and
  `mod_editor/studio/music_service.py:370,458,483,517,588`: selection,
  original reads, mono conversion, paired transaction and playback target.
- `mod_editor/core/nfl2k5_music_build.py:62` and
  `mod_editor/core/nfl2k5_music_banks.py:87,245`: recipe and twin validation.
- `mod_editor/gui/studio_qt.py:2034`: `_music_changed` invalidates **both**
  Music and Audio Cues; `audio_panel_qt.py:4051,4646` reads
  `facade.audio_editing_ready` (`mod_editor/studio/facade.py:1446`).
- The readiness property reaches `Nfl2k5AudioOriginPreparation.is_ready`
  (`mod_editor/core/nfl2k5_audio_origin_preparation.py:65`). Explicit
  `facade.prepare_audio_editing` (`facade.py:1461`) prepares/loads the same
  exact and containment inventories for either bank. The scanners have no
  separate stadium cache identity rule.

Thus the cache exception is shared; a stadium-only audible failure cannot be
inferred from this stack. Mono conversion and the stadium's game-time playback
remain distinct from stereo jukebox playback.

## Root cause already fixed in beta 63

`Nfl2k5SourceCache.index` stores the cache at `cache_root / source.sha256`
(`mod_editor/core/nfl2k5_source_cache.py:218`). Before `ef495b4e`, the exact
store required `root.name == self.expected_source_sha256`
(`nfl2k5_audio_source_fingerprints.py:700` at `ef495b4e^`), and the containment
store repeated that requirement (`nfl2k5_audio_source_containment.py:353`
at the same revision). Those comparisons reject an opened rip with a
different container digest, even when its game content is accepted upstream.

Current checks accept the opened digest or the project digest
(`nfl2k5_audio_source_fingerprints.py:701` and
`nfl2k5_audio_source_containment.py:355`). `ad845272` also catches
`ValidationError` in the readiness probe (`nfl2k5_audio_origin_preparation.py:76`),
returning `False`. Explicit preparation still rejects an unrelated folder.
The exact scanner's result is correctly read as `result.inventory.path`
in preparation (`nfl2k5_audio_origin_preparation.py:129`).

## Synthetic reproduction and historical controls

Added `tests/mod_editor/test_nfl2k5_music_fresh_rip.py`. It uses the existing
`SyntheticSourceFixture` with the actual opened image digest as cache name,
while **both stores and scanner pins retain `SOURCE_SHA256`**. Only the tiny
fixture geometry and parser replace retail inputs; scanners, PCM decoding,
private publication, strict document reload and preparation are real. The
facade receives an unloaded-service flag so its real readiness property must
consult the coordinator; strict reloads use the real scanners.

The fresh cache starts not ready, prepares both missing inventories, becomes
ready through the real facade property, strictly reloads both inventories,
and reuses them. The source hash remains unchanged. A third, unrelated digest
folder answers not-ready and both stores and explicit preparation refuse it.

As negative controls, each historical method was extracted with Python `ast`
from `git show`, compiled against the current module's globals, and temporarily
substituted with `unittest.mock.patch.object` in a separate Python process.
No production file was edited. Running the same new test with each old method
produced the following expected failures:

```text
ef495b4e^:nfl2k5_audio_source_fingerprints.py:678 _validate_cache
AudioSourceFingerprintError: NFL 2K5 source-cache directory is not the canonical cache key
ef495b4e^:nfl2k5_audio_source_containment.py:341 _validate_cache
AudioSourceContainmentError: NFL 2K5 source-cache path is not canonical and source-bound
ad845272^:nfl2k5_audio_origin_preparation.py:65 is_ready
AudioSourceFingerprintError: NFL 2K5 source-cache directory does not belong to the opened game disc
All three historical controls reproduced; worktree production code unchanged.
```

## Real offscreen replay

Added `tests/mod_editor/test_nfl2k5_music_fresh_rip_gui.py`, adapting the supplied
`FRESH_RIP_GUI_REPLAY_2026-09-09.py` pattern to the Music workspace. It constructs
the real `StudioMainWindow`, facade, source cache, session and catalogs. All
generated files go under `TemporaryDirectory`, including the session/recovery
roots. The test verifies the pinned source hash while copying it read-only,
then changes only 16 zero padding bytes at `0x100` in the temporary image.

```text
Retail SHA-256: 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
Opened SHA-256: 411c23adea86b08c778ed4c0fa1bb2d50acf2bff84db942be2303a45f7356014
Cache basename: 411c23adea86b08c778ed4c0fa1bb2d50acf2bff84db942be2303a45f7356014
```

The replay selects all 59 linked Music rows with mono off and on, emits 118
real `MusicPanel.changed` signals, pages through every stereo jukebox and
mono stadium Audio Cues range (59 each), invalidates content, and reopens the
same source with the Music panels instantiated. Readiness remains `False`
throughout. `QMessageBox` static methods and `exec_`, `sys.excepthook`, the
window error handler and Audio Cues errors are captured and asserted empty.
No audio player is started. Source size/mtime/ctime must match after cleanup.

Environment decision: the instructed retail path initially existed only with
an `.old` suffix. Its hash matched the retail pin, so the first replay used
that read-only file. During the run it was externally restored to the original
name. All Music checks passed with zero captured errors, but the final source
`stat()` correctly failed because the `.old` name disappeared. The final run
uses the restored canonical path and retains the integrity assertion; this
was an input-path race, not a reproduced Music defect.

Final replay output (2026-09-09, EDT; waiting messages omitted):

```text
13:57:31 Copying and hashing read-only retail input into a temporary fresh rip
13:59:36 Open fresh rip: settled in 83.8s
13:59:37 Enter Music workspace: settled in 0.1s
13:59:46 59 jukebox/stadium pairs and 118 Music changes: settled in 0.1s
13:59:55 Selected all 59 mono stadium and 59 stereo jukebox Audio Cues ranges; readiness=False without raising
13:59:55 Music refreshes: settled in 0.1s
14:01:02 Reopen fresh rip with Music instantiated: settled in 67.3s
14:01:02 Music change after reopen: settled in 0.1s
14:01:02 Close replay: settled in 0.1s
14:01:04 GUI_FRESH_RIP_MUSIC_OK {"crashes": [], "dialogs": [], "errors": []}
Ran 1 test in 213.515s
OK
```

Reproduce from this worktree:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen \
  python3 tests/mod_editor/test_nfl2k5_music_fresh_rip.py -v
PYTHONPATH=. QT_QPA_PLATFORM=offscreen \
  NFL2K5_MUSIC_REPLAY_XISO='/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  python3 tests/mod_editor/test_nfl2k5_music_fresh_rip_gui.py -v
```

The GUI test gives a precise `SkipTest` when the retail path is not configured,
does not exist, or PyQt5 is absent. Its default standalone invocation was also
checked: `Ran 1 test ... OK (skipped=1)` with the configuration instruction.

## Verification results

Each module below was run standalone with `PYTHONPATH=.` and
`QT_QPA_PLATFORM=offscreen`, using plain `python3`, not pytest. Existing paired
edit/build tests use synthetic audio and cover atomic twin replacement,
restore/undo/redo, mono dispatch without playback, pack seams and failed-twin
rollback. The retail catalog case validates all seven banks and 145 ranges
read-only.

| Test module under `tests/mod_editor/` | Tests | Result |
| --- | ---: | --- |
| `test_nfl2k5_music_fresh_rip.py` | 2 | OK |
| `test_nfl2k5_audio_origin_preparation.py` | 7 | OK |
| `test_nfl2k5_audio_source_fingerprints.py` | 17 | OK |
| `test_nfl2k5_audio_source_scan.py` | 12 | OK |
| `test_nfl2k5_audio_source_containment.py` | 17 | OK |
| `test_music_service.py` | 10 | OK |
| `test_music_panel_qt.py` | 9 | OK |
| `test_audio_panel_qt.py` | 50 | OK |
| `test_nfl2k5_music_catalog.py` | 4 | OK, retail case included |
| `test_nfl2k5_music_build.py` | 8 | OK |
| `test_nfl2k5_music_fresh_rip_gui.py` | 1 | OK, real retail fresh-rip replay |

Final runs: **137 tests passed, zero skipped** across these 11 modules.
The separate no-retail configuration check intentionally skipped its one GUI
test; the three historical negative controls intentionally failed as described
above. `git diff --check` passed.

## Handoff and witness

No protected file, runtime writer, provider pin, release manifest or preset
changed. No repin or manifest regeneration is required; `WIRING.md` is
unchanged. No push or external message was sent. Handoff inputs
`ASTRA_BRIEF.md` and `HOTFIX_CONTEXT.md` remain untracked and are not part of
the verification commit.

Suggested precise response for Noah: “The beta-62.1 Music-tab cache error is
fixed in 63. We verified a fresh-rip cache, all 59 stadium slots, all 59 jukebox
slots and reopening with no editor errors.” Do not expand that into a claim
that stadium playback has been witnessed.

Noah's in-game witness: with his own authored song, check the same selection
in the Crib jukebox and an actual stadium music slot, including the saved
stadium assignment and audible mono result. If only the stadium fails, retain
the exact build/version, assignment and error or recording: those details
would distinguish a runtime/mono/assignment problem from the fixed editor
cache exception. Nothing in-game is proved by this verification.

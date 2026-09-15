# Beta 70 T3: jersey choice and music imports

Branch: `astra/b70-t3-game-audio`, based on `df9b9dcf`. Implementation commit:
`e64d61aa`. No emulator, GUI display, audio playback, network, disc copy or
retail-byte fixture was used. Qt ran offscreen. Retail input was read-only.

## Outcome and integration boundary

- **PROVED:** both retail Controller Assign and exhibition Team Select callback
  sets reach the patched choice handlers; crossing the available-era boundary
  toggles only the selected side, and the kit selector consumes those words.
  An explicit era reset **clears** the words. They do not survive it. No new
  uniform-code defect or failing game transition was reproduced.
- **Implemented:** the Music page warns before import about 22,050 Hz playback
  and downsampling. A Music-only conversion owner tightens the existing SoXR
  filter and adds deterministic TPDF dither at the final PCM16 conversion.
- **PROVED:** the native NOW PLAYING list permits explicit repeated adds in both
  retail and My songs. Five adds produce five nodes; profile rebuild does not
  multiply them. The separate automatic playlist rejects duplicate records and
  suppresses repeated active enqueue/completion requests.
- **Required integrator work:** [WIRING.md](WIRING.md) supplies the two shared
  `audio_conform.py` forwarders, release allowlist entry, selected-form inspection
  field, Build/Gameplay captions and badges, preset default correction, and
  registry edits. Until the shared forwarders land, the studio still calls the
  old audio conversion path. This is not claimed as already wired.
- **Every beta-70 in-game outcome is UNWITNESSED.** X_Ray's failure and Mud's audio
  quality complaint remain unresolved. Keep the option EXPERIMENTAL. Existing
  ADVANCED/EXPERIMENTAL presets currently enable jersey choice; WIRING requests
  turning those two fields off to meet the shared beta-70 instructions. BASIC
  already keeps it off. Practice/Xbox Live are not extended.

## 1. Uniform choice: executable facts versus hypothesis

X_Ray, September 14, 6:50 AM: “Also I don't even think the mod is even working
properly. I can't pick away jerseys at home and vice versa.” The screenshot
labels the option “Not yet tested in game”; it does not establish which form
was actually built or which screen he used.

### PROVED with retail bytes and bounded Unicorn execution

`test_nfl2k5_uniform_choice_screens.py` installs `choice` with the real writer.
It executes all eight retail screen wrappers, including their real team getter,
era-validity lookup and preview-update callee. Synthetic team data contains
sparse eras 0, 1, 5 and 14. No flip word is reseeded before the kit selector.

| Screen | Home next / away next | Home previous / away previous |
| --- | --- | --- |
| Controller Assign | `0x27AF50` / `0x27AF70` | `0x27AF90` / `0x27AFB0` |
| Exhibition Team Select | `0x2C0BA0` / `0x2C0BC0` | `0x2C0BE0` / `0x2C0C00` |

Next walks 0 → 1 → 5 → 14 → 0, toggling that side's colour word on the wrap.
Previous from 0 goes to 14 and toggles. The other side's word stays unchanged.
The wrappers return with the correct stack cleanup. The existing 18-test suite
also covers all 30 states when all 15 eras exist, no-throwback/no-team cases,
retail clamping, both forms, foreign rejection, idempotence and composition.

**The requested reset-survival premise is false.** The choice patch's reset
at `0xE2D80` zeroes the eras at `0xE60210/0xE60214` and, at its patched tail
`0xE2D91`, stores zero into `0xA69974/0xA69978`. The native setup prefix
`0x77D20..0x77D40` executes this reset at `0x77D3B`; the test runs its two real
bulk clears and the real reset. A direct-relative-call scan found the setup
caller at `0x74AA6` and the reset caller at `0x77D3B`. That does not exclude
indirect calls or establish a complete in-game event order.

The harness executes **setup reset → screen callbacks → kit selector**, then
explicitly tries **screen callbacks → reset → kit selector** as a control. In
the first case the choices reach the selector; in the control they are cleared.
This distinguishes lifetime behavior from a claim to have reproduced X_Ray's
failing transition. Clearing old game state during setup is not by itself a
proved bug, so the reset bytes were retained.

At game asset selection, `0x6160F` computes the retail Cowboys swap and combines
it independently with the two words. The away read at `0x6168B` uses scratch
`0xA6997C`; the home site uses `ESI`. The test observes the characters passed to
the real name-formatting call sites `0x616B4/0x616FA`:

| Ordinary matchup, e.g. NYG home / PHI away | Home word | Away word | Home / away kit letters |
| --- | --- | --- | --- |
| Default | 0 | 0 | `h` dark / `a` white |
| Home flipped | 7 | 0 | `a` white / `a` white |
| Away flipped | 0 | 7 | `h` dark / `h` dark |
| Both flipped | 7 | 7 | `a` white / `h` dark |

Dallas at home starts with the opposite retail default; flipping both yields
`h/a`. The final loader seam stubs only era-number lookup (`0xE2F20` returns 0)
and formatting (`0x4A410`, `ret 8`), matching the existing harness. This proves
colour characters supplied to the kit-name formatter, not archive resolution,
rendered uniforms, preview art or a full playable game.

The `rule` form remains one fixed home-dark/away-white rule, without a colour
choice. WIRING names that distinction and reads the installed form from bytes.
The core file changed only its explanatory docstring. Comparison against the
pre-T3 source confirms identical generated sites in both forms:

```text
rule:   1 site, SHA256 58766d43aff1a2c6cf49fd82d235250f4fc041fde2336ec3020b98dc09df0a48
choice: 7 sites, SHA256 928f125f974ed0d28b9886da11fa8a11f6f48af404246a3107f728d230f0d45a
```

### HYPOTHESIS / still needed

Wrong form, unsupported screen, misunderstanding an era-only preview, or a
reset on an unexecuted transition could explain X_Ray's report. None is proved
as his cause. Do not present the bounded tests as overturning his report.

### X_Ray witness recipe (integrator supplies the build)

1. Rebuild from the original supported disc. Enable the jersey option and choose
   **choice**, not **rule**. Keep the build receipt showing `uniform_choice:
   choice`. Confirm the revised caption names that form.
2. Use **Play Now / exhibition Team Select**, with NYG at home and PHI away (or
   another ordinary non-Cowboys matchup). Use the normal jersey-era **D-pad
   Up/Down** controls on the side being tested. Tap **Up** through the available
   eras; one more Up past the last era returns to the current era. That wrap
   should flip that side's colour. With no throwbacks, one tap should suffice.
3. Flip **both** sides once, leave the teams/eras alone, and start the game.
   Expected on the field: the home side wears white and the visitor dark.
   Team Select's artwork still shows era only; a colour change in that preview
   is not promised. Record the receipt and a field screenshot or short video.
4. Repeat on **Controller Assign**, after team selection. Exercise **Down**
   below the current/first era: it should jump to the last available era and
   flip that side. Start without changing teams again and compare on the field.
   Also try a one-side flip to check independence; both teams may then wear white.
5. Report which screen, side, direction, era before/after, and whether the
   failure happens before or only after advancing to game load. If it still
   fails, keep the exact receipt/XBE identity and the complete transition video.
   Practice and Xbox Live are outside this witness and outside this job.

## 2. Music quality

Mud, September 14, 3:46 AM: “Audio imports to its own playlist and doesn't crash
the game when loading from The Crib but audio sound bad”.

### PROVED: warning before import and conversion behavior

The visible Songs page now explains: “The game plays music at 22,050 Hz
(16-bit). Higher-rate files will be downsampled before import, which removes
the highest frequencies.” It asks for the original file and a prepared-preview
check. The fixed-slot Assignment Review repeats that warning before its worker
starts. Offscreen tests assert that the warning exists before selecting files,
and in the assignment dialog. No extra confirmation dialog was introduced.

The input contract is PCM16 at 22,050 Hz; the existing bank writer still encodes
Xbox IMA audio. The original Music importer already used SoXR precision 28;
it was **not** an unfiltered decimator. The new Music owner uses the existing
FFmpeg/SoXR implementation with `precision=33:cutoff=0.90:cheby=1`. This tightens
rejection with slightly earlier top-end rolloff. Decode and resample stay float;
gain, peak protection and any fixed-slot fade precede one PCM16 conversion.
Native PCM16 fixed-slot input at unity gain without a fade stays exact.

TPDF is triangular noise formed by subtracting two independent uniforms,
spanning ±1 least-significant 16-bit step before rounding. One locally seeded
generator persists across chunks, so repeat imports are reproducible and
channels receive different noise. Exact digital zeros and padding stay zero.
The ten-minute song bound, decode ceiling, cancellation, volume cap, source
validation, twin transaction and archive writers keep their existing contracts.

### Synthetic measurement (no listening)

Two-second 48,000-Hz **float64** WAV sweeps, amplitude 0.75, converted to
22,050-Hz float output. Discard 100 ms at each edge. The stopband sweep runs
11,026–20,000 Hz, wholly above the output Nyquist limit of 11,025 Hz. Its
residual output energy measures folding/error **before dither**. There cannot
be output frequencies above Nyquist; the test measures energy folded down
from input above that limit. Float64 avoids mistaking PCM16 source noise for
filter leakage.

| Measurement | Current shared path | New Music path |
| --- | ---: | ---: |
| Stopband residual, dBFS | -205.127294 | -228.323402 |
| Passband 100–8,000 Hz, dBFS | -5.5090754 | -5.5090742 |
| Stopband improvement | | **23.196108 dB** |

The regression requires >6 dB improvement, <0.01 dB passband level difference,
matching frame counts and a new residual below -150 dBFS. Both measured filter
floors were already far below 16-bit noise; these numbers do not show an audible
improvement or explain Mud's complaint. Dither adds low-level noise and reduces
quantization bias; it is deliberately excluded from the alias measurement.

For 100,000 samples at 0.25 LSB, the old quantizer outputs mean 0; the new mean
is **0.24922 LSB**, with error variance **0.24871 LSB²** (target 0.25). Chunk
splitting produces identical bytes; tests cover silence, clipping, independent
channel noise, invalid floats, both import routes, frame counts and repeatability.

The integration harness runs the existing 29 Music conform/simple/service tests
against the new functions. This catches gain/peak behavior, padding, trim fades,
mono cancellation, missing FFmpeg, codec import, cancellation, authored projects,
encoded preview and source preservation. Shared callers still need WIRING.

### Mud quality witness recipe

Use the same short passage from a high-quality original, retaining its source
rate and codec. Reimport with the integrated beta-70 build; compare the prepared
encoded preview with the same passage in My songs/The Crib at similar volume.
Report whether “bad” means hiss, distortion, dull treble, wrong speed, stuttering
or a channel problem, and whether it already occurs in the studio preview.
Retain the import notes and the source file privately for diagnosis. Also check
that imports still appear under My songs and that entering The Crib still works.
22,050 Hz cannot retain content above 11,025 Hz; restored high-frequency detail
and audible quality are not claimed.

## 3. NOW PLAYING: two different lists

I inspected the saved frames `2k5-bugs_9ac2dfdc_1_11.png` and `_12.png` in the
read-only Discord evidence folder. Both show five visible entries with the
same truncated title, “27 Sam Spence, Da R…”, duration 1:32, collection My songs
and artist Custom. NOR is selected; the selected row changes. This establishes
repeated **display labels**, not how many add-button presses occurred, whether
IDs differ, or whether automatic playback independently duplicated a track.

### PROVED native queue and manifest trace

- `nfl2k5_music_metadata` / `nfl2k5_music_collections` write the immutable
  collection table, track IDs, titles and stream indices. They do not populate
  NOW PLAYING by duplicating automatic shuffle records.
- Native `0x27F1B0..0x27F33E` initializes the 400-node pool at `0xC3AC94`.
  The harness executes this loop, stopping before sound-device setup.
- `0x27F5F0` takes one free node and appends `{collection, song, identity}` to
  the active list rooted at `0xC3CBE8`, incrementing count `0xC3CC04`.
  It has no duplicate-ID guard. Five calls with the same tuple
  yield five distinct nodes in **both retail collection 0 and My songs 18**.
- Real scroll lookup `0x27F900` and title consumer `0x27F9A0` return the five
  repeated entries. Profile writer `0x27F3A0` persists all five; two calls to
  profile rebuilder `0x280530` each leave exactly five nodes. The only stub in
  these operations is `0x191D20`, which selects synthetic profile zero.
- `nfl2k5_music_playlist.Selection` rejects duplicate `(bank,index)` pairs.
  Its installed read-only manifest describes a separate automatic background
  shuffle bag, not the native display pool. `tools/nfl2k5_music_playlist.S`
  guards active enqueue, advances through unique records, and suppresses a
  boundary repeat when more than one item is enabled. Zero items stop; a single
  enabled item naturally repeats after completion. Different IDs with the same
  content/title are permitted.
- The new test calls automatic enqueue five times while active and observes
  **one** packet. Repeated completion/frame notifications over a five-song cycle
  yield **five unique** packets. Existing playlist tests cover the broader
  shuffled cycles, runtime descriptor bounds and replay/modal guards.

No new duplicate-enqueue defect was proved, so neither native repeat semantics
nor the playlist XBE writer was changed. The video alone does not justify
removing the ability to deliberately add the same track twice.

### Mud queue witness recipe

In a fresh/cleared NOW PLAYING list, add three visibly different songs once
each, recording the queue after each press. Let them advance without pressing
Add again. Then intentionally add one of them twice and compare. Report whether
the original five repeats followed repeated Add presses, loading an existing
saved queue, identical imported files/titles, or passive playback. Include the
playlist choice manifest and whether background shuffle was enabled. Do not
clear his only saved playlist; retain a copy or use a fresh test profile.

## 4. Historical positive witness and release wording

Mud's beta-69 report/video positively witnesses imports in their own playlist
and no crash while entering The Crib in that run. The beta-70 changelog quotes
that success together with “audio sound bad”; it does not reopen the old Crib
crash or claim new listening validation. It also quotes X_Ray's negative report,
explains form/screen scope and leaves his cause unresolved.

## 5. Verification commands and results

All commands ran from this worktree. Complete output is in `reports/b70_t3/`.
No skips occurred in these runs. Each test file ran as a standalone Python
entry point; the integration file loads the three existing suites under scoped
Music delegation.

| Command | Output | Log |
| --- | --- | --- |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_uniform_choice.py` | 18 tests, OK | `uniform-existing.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_uniform_choice_screens.py` | 2 tests, OK | `uniform-screens.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_resample.py` | 4 tests, OK + sweep/dither numbers | `resample.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_queue.py` | 3 tests, OK + retail/custom queue counts | `music-queue.log` |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_conform_integration.py` | 29 tests, OK | `conform-integration.log` |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_music_panel_qt.py` | 9 tests, OK | `music-qt.log` |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_music_simple_qt.py` | 9 tests, OK | `music-simple-qt.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_playlist.py` | 15 tests, OK; template verified | `music-playlist.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_metadata.py` | 7 tests, OK | `music-metadata.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_playlist_library.py` | 7 tests, OK | `music-playlist-library.log` |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | 2 tests, OK | `music-playlist-manifest.log` |

**105 passing test cases**, including the nested integration suites. The first
Songs UI run failed because its old contract explicitly forbade showing
“22,050”; it now requires the warning before import. A first queue harness
attempt reached unrelated audio-device setup; it was bounded at `0x27F33E`
after the complete pool loop. Both complete suites then passed as reported.

`git diff --check` passed. `python3 packaging/repin.py --apply` ran after each
pinned owner/help edit and before commits. Automatic changes only repinned the
uniform provider hash and the shared-help hash in the packaging check; no
packaging logic was edited. No uniform/playlist XBE bytes changed, as verified
against the pre-T3 generator, so the conditional XBE memory-write/cave-reference
and pairwise/oracle gates were not rerun. The existing uniform composition and
playlist manifest tests passed. Integrator must regenerate the cave manifest
as requested by the shared pinned-writer handoff and repin again after wiring.

Registry handoff adds one missing uniform-choice capability (172 → 173 rows)
and updates existing audio evidence; it does not upgrade runtime status.

The proposed registry handoff validates structurally at 173 rows, and every
new row's backend/evidence path exists. Full registry file checks already fail
on the unchanged base row 0 at `docs/research/apf_audio.md` (missing locally).
That unrelated baseline gap is recorded in `registry-handoff.log`; it was not
repaired or suppressed. Tool versions are in `environment.json`: Python 3.12.3,
Unicorn 2.1.4, Capstone 5.0.7, FFmpeg 6.1.1-3ubuntu5.

## Commit transport limitation

The implementation commit `e64d61aa` is on the requested branch. The final
report/changelog commit could not update that branch because Git could not
create `/home/noah/2k-football-mod-tools/.git/worktrees/astra-b70-t3/index.lock`:
**Read-only file system**. No permission escalation was requested.

The final documentation commit is instead supplied in `ASTRA_T3_HANDOFF.bundle`,
created with temporary Git metadata inside an allowed scratch directory and the
implementation commit as its prerequisite. The original repository metadata
was not changed by this fallback. The bundle contains only the documentation,
capability handoff and small test logs added by this job; no retail media.
Import it in a writable integration checkout as described in WIRING.md.

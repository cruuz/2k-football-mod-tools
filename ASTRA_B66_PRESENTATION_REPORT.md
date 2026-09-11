# Beta 66 job F: 2K5 in-game presentation

Branch `astra/b66-presentation`. Native/offline proof only. No emulator, game
boot, display, audio, network, disc build or push. Source: pinned USA retail
`default.xbe`, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Read `ASTRA_CONTEXT.md`, triage rows 7/15/22, all three requested camera histories,
the 53-model clip survey, camera source, scorebug/scorebar font work and M3 code.

## Delivered

- Camera owner v6: 512 RX / 320 RO bytes, four following descriptors, no RW
  reservation or retail cave. Constrain the final smoothed eye before projection;
  pull inward near corners; retain the midfield v5.3 pre-snap framing. Run lens
  magnification increases 15%, airborne/caught-pass lens decreases 15%.
- Own Broadcast state 7 and route it to the wide following descriptor. Native
  selection and the subsequent kickoff state-8 lookup are executed in tests.
- MyPlayer HUD in enabled M3 careers, On by default, with a real native Settings
  row and persistent On/Off choice. Name, current position label and live game
  counters use retail font4, native formatting and glyph submission. No added
  persistent text buffer, RW owner or executable seed. Both M3 menus now share
  the bounded compressed-template decoder to fit the existing code allocation.
- Strict composed-owner recognition for the defensive-try extension of CB240;
  unrecognized or damaged hooks/bodies still refuse before writing.
- Changelog credits maumau78, CER and Mud. Protected integration is specified
  precisely in `WIRING.md`, including job A's shared byte and M3 budget handoff.

## PROVED: final eye, lenses and stadium survey

v5.4's setup box constrains the desired position **before** native smoothing.
`0x5F760` writes the final eye at `0xA82BF0 + camera_index*0x460`; its reset and
smoothed branches merge at **0x5FC74**. The new six-byte call site executes the
owned clamp there, before the eye-to-target vector, lens and projection. It
recognizes only this owner's setup callback at camera+0x430, so other descriptors
retain their native behavior. Both scratch XMM registers, EAX and flags are
preserved, and the displaced `fld [ebx+0xA82C00]` executes exactly once.

Centimeter bounds: `2500 <= x <= 5000`, `1400 <= y <= 1500`, `abs(z) <= 5000`,
plus `x <= 5000 - max(0, abs(z)-2800)`. The corner boundary is continuous. The
native filter position at `0xA82C70` is anchored to the constrained eye; velocity
is cleared only on constrained axes. The setup callback supplies the matching
box and caps target height at 100 cm. First-frame inherited eyes at
`(7300,365,+/-5936)` and hostile velocities are inside the boundary immediately,
including reset, ordinary smoothing and elevated-ball paths.

The survey reuses the historical 96x72 static-triangle ray method, ground
rectangle `abs(x)<2810, abs(z)<5900`, front-face determinant convention and
**dirty = more than 2% of ground pixels occluded by stadium geometry**. It now
feeds actual native **post-smoothing** eye/target output, not a host approximation
of the desired mount. Ball grid: 17 x 13 locations, x -2400..2400 in 300 cm steps,
z -5400..5400 in 900 cm steps, both directions. All 53 retail model variants
3136..3188 are included. Four unique v6 lens families are sampled at each point.

| Version / samples | Dirty / total | Dirty % |
|---|---:|---:|
| v5.3, whole settled grid | 4,348 / 23,426 | 18.5606% |
| v5.4, whole settled grid | 788 / 23,426 | 3.3638% |
| v6, four settled lens families | **0 / 93,704** | **0%** |
| v6, 120 moving frames x 13 states x both directions x 53 models | **0 / 165,360** | **0%** |

All 53 models individually have zero v6 dirty samples. Chicago 3141 and Lambeau
3146 are included. No v6 frame has an empty ground mask. Maximum settled ground
occlusion is 1.63935%, below the declared historical threshold. The first v6
candidate left 49 dirty corner frames in Cincinnati/RCA Dome variants; the final
2800 cm corner onset removed them in the complete rerun. Zero *dirty samples*
is not a claim of zero occluded pixels or an exhaustive collision proof.

Receipts: `docs/presentation/camera_native_v6.json` contains only numeric native
measurements and source hashes; `camera_survey_v6.json` contains every model's
before/after counts and source hashes. It binds the native capture by SHA-256.
No retail XBE, FONT, geometry or texture payload is included.

Native solver samples at midfield, direction +1, 16:9, same eye
`(4900,1400,450)` and target `(400,0,250)`:

| Row-7 state | Lens word | Native scale | Vertical / horizontal FOV | Ball pixel | Near wideout pixel |
|---|---:|---:|---|---|---|
| 9 pre-snap, v5.3 and v6 | 68.0 | 3.777778 | 25.6313 / 38.8801 deg | 361.169, 214.829 | 421.034, 369.559 |
| 16..19 run, sample 17 | 78.199997 | 4.344444 | 22.3785 / 34.1231 deg | 367.344, 211.053 | 436.189, 388.993 |
| 13 catch / 15 airborne pass | 57.799999 | 3.211111 | 29.9654 / 45.0989 deg | 354.994, 218.604 | 405.879, 350.126 |
| 7/8 kickoff and other owned previews | 48.0 | 2.666667 | 35.7247 / 53.1301 deg | 349.061, 222.232 | 391.318, 331.454 |

Ratios are natively 1.15 and 0.85. State 9's midfield projection is bit-identical
to v5.3; the safety boundary necessarily changes its edge/corner eye. Deep-pass
framing is wider while continuing to follow the ball, not a promise to show the
entire field simultaneously. State 1 and 7..19 are owned; other Broadcast
presentation/replay states and other camera rows retain native descriptors.

Exact v5.4 recognition was independently checked against `camera.apply()` from
historical git object `ef33b55ab4f9cd87de3c005adc56e45bd37e39a8`.
The complete standalone installed XBE matches SHA-256
`a4aafb585649b4a3a05f76bf6e542db982f2dcf5a90b5ad2306e676484d91b85`.
`status()` returns `v5.4`, and applying v6 refuses before installation with the
retail-rebuild instruction. A resealed but altered historical callback is foreign.
Current apply/status/replay remain exact and idempotent.

## PROVED / HYPOTHESIS: CER's PAT-to-kickoff shot

PROVED: the native decision tail `0x896EA..0x89776` chooses camera **state 7**
when no active-controller/presentation condition diverts it. This branch is
executed with kickoff phase `E602B4=2`. The ordinary alternative sets state 11
and lets `0x894A0` select the play-type camera. Its real descriptor getter
`0x189640` and type-8 kickoff decode set **state 8** after the kickoff play is
selected. With Broadcast selected, the lookup at `0xA572D` indexes
`[0x4F03F8 + (7*29+state)*8]`; this is engine row 7, not a new coach-mode switch.

The old row-7/state-7 descriptor is `0xA88460`, with callback `0xA4650`.
Executing that callback with kickoff phase 2 produces the low kick offset
`(-3000,365,5000)` and its goal-post/sideline setup. v6 replaces the state-7
pointer with the owned 48-lens descriptor. States 8 and 11 share the same safe
wide descriptor; states 10/12/14 also have independent wide following eyes.
The test executes both the actual table lookup/setup and the native kickoff
state-8 selection. The survey includes inherited low corner eyes through every
owned kickoff/PAT state and both directions.

HYPOTHESIS / UNWITNESSED: this conditional native route explains the camera shown
in CER's seven-second video. A recording cannot identify live RAM values, and
we did not replay the entire physical PAT-to-play-call sequence. The intermittent
play-call stall is **not** claimed fixed by this camera change; job D2 owns that
separate audit. Noah must witness the complete transition.

## PROVED: MyPlayer live stat line

`0x74790..0x7489E` is the native outer presented-frame routine. Its single
`0x74879` no-op call to `0x89F50` now calls `mode_hud_frame`, after normal scene/HUD
work and before the final submission calls. There is no inner-simulation-tick
HUD hook. A bounded execution of the entire outer routine, with unrelated frame
services as explicit leaves, proves three presented frames invoke the owner
three times and native text draw `0x6BC30` three times. FXSAVE/FXRSTOR and
pushad/pushfd preserve the original call site's machine state.

Visibility requires an enabled, valid M3 career in phase 3, game state 3,
unpaused, an initialized match, camera states 8..19 and neither native replay
channel active (`0x83940`, flag 4 at B607F0/B608F0). Menus, camera replay states,
manual replay flags, disabled/lost careers and Off suppress the line.

The M3 binder's base-state+2564 is a **match roster row**, not the entity pointer.
It is checked against both 65 x 84-byte match pools (B30C4C/B321A0), alignment,
primary identity/name pointers/birth bits/position and initialized live-stat
pointers. The primary lookup validates the saved MyPlayer fingerprint. The
position text uses the exact retail enum abbreviation table and known EDGE/LB
labels, so the HUD follows those installed label choices.

The brief's proposed `player+0x2C` packed dwords hold **season history**, not live
game totals. Native `CB240(ECX=MyPlayer match row, EDX=selector, bank=0)` reads
`[match+0x30]` through C96B0 and the pinned native live providers. All five QB
getter entries and their actual player/bank arguments are captured; native
completed-pass events change the line from 0/0 to 1/1 for 17 yards, then 2/2 for
40 yards. Negative native yardage is retained. No season-history reads feed the
live line. The exact defensive-try companion branch forwards these ordinary
selectors to the same native implementation; both install orders and actual
HUD reads are covered, and a resealed damaged companion is rejected.

| Position | Line | Native selectors |
|---|---|---|
| QB | CMP/ATT, YDS, TD, INT | 4, 35, 76, 64, 22 |
| HB/RB, FB | CAR, YDS, TD | 3, 80, 63 |
| WR, TE | REC, YDS, TD | 46, 79, 62 |
| Defense | TKL, SACK, INT | 50, 47 (half-sack units), 23 |
| K | FG made/attempted, XP made/attempted | sum 173..176 / 169..172; 88 / 89 |
| P | PUNTS, AVG | 43; 78 / 43 to one decimal |
| C, G, T | Name and position | No invented counting stat |

All 17 positions execute their native getter paths. Supplied live-row fixtures
also prove `9 TKL / 1.5 SACK / 2 INT`, `FG 7/10 / XP 3/4`, and `3 PUNTS / 46.3 AVG`.
These fixtures supply counters, not fake getter results. Full player name is
compacted to first initial and at most 12 last-name characters for a small line.
The UTF-16 buffer is stack-local and bounded to 128 units.

Drawing uses the already proved native path
`6BC30 -> F1C70 -> retail formatter -> 47420 -> 46DF0 -> glyph submissions`.
Font4 is global slot 3 at A90ED8 (native 17-pixel line advance, 12-pixel digit
height). Context alignment words are 3/2, opaque white, z=20; native width
measurement right-aligns the line at x=620, y=38 in the 640-column HUD space.
This is an immediate HUD text pass at the outer presentation tail, not a new
scene/resource label. Tests relocate the real FONT resource and execute native
metrics and glyph walks; only leaf GPU submission is captured. The formatter
also walks a terminal newline with zero glyphs; that is not a second visible
line or a second HUD invocation. An early `|` separator was removed because it
is a native formatting control character.

Apartment > Settings > **MyPlayer stat line: On / Off** is implemented as row 3.
Save byte **82 bit 4 (0x10) means Off**, state+2712; old zero-filled saves default
On. Bits 0/1/2 are preserved and bit 3/+2708 is reserved for job A. Native and
Python codecs agree on all 16 combinations, native save/cold relocation preserves
the choice, and reserved encodings refuse. Combined job A must merge its mask
without dropping this bit, as detailed in WIRING.

M3 remains **16,384 RX + 4,096 base RW + 4,096 M3 RW**. Final measured standalone
and full-union code content is 16,301 bytes, leaving 66 bytes before the tag.
No allocator capacity was borrowed. Job A must rerun the budget check after
merging its own runtime additions.

## Verification

The final receipt is [`docs/presentation/validation.json`](docs/presentation/validation.json).
It records each standalone file, test count, result, log hash and the exact
pairwise batch arguments. **Across 41 standalone files: 833 tests passed,
1 skipped, zero failures or errors.** The one skip is the oracle's release-resource receipt
check: the private manifest explicitly covers XBE composition only. No disc or
resource build is claimed.

| Check | Result |
|---|---|
| Memory-write XBE gate | 115 passed |
| Cave-reference XBE gate | 127 passed |
| Cave oracle | 28 passed; 1 explicit XBE-only manifest skip |
| Owner pairwise file | 335 passed; 8 complete standalone batches |
| Camera v6 native proof; Broadcast/Far regressions | 30 passed |
| MyPlayer native HUD | 5 passed |
| All MyCareer standalone files, including settings and cold loads | 145 passed |
| Supersim live | 17 passed |
| Allocator integration and scale-out | 30 passed |
| Observed complete-stack manifest | 1 passed |

All `test_nfl2k5_my_career*.py` files were run standalone, together with the new
HUD/final-eye tests, both camera suites, Supersim live, allocator integration and
scale-out. The pairwise file's 335 discovered methods were covered exactly once
by eight independent standalone invocations. Each invocation constructs its own
fixtures; the receipt lists every method argument. The Far proof now maps the
installed callback owner even for a native Far descriptor. Receipt and capacity
expectations account for v6's 47 edits and additional 352 RX / 240 RO bytes.

Both complete XBE gates cover forward/reverse owner installation and scale-out.
The fresh observed manifest attributes every changed byte in 125 real writer
steps, with 12,364 reserved spans and matching fingerprints for 304 source files.
Its fully composed XBE SHA-256 is
`2c03d6decca1ab8eb1a7433489770c312d4b629e324fc6a9331e731081755391`;
section digests pass. The protected release manifest remains untouched.

Reproduce the private manifest and gate environment:

```bash
PYTHONPATH=. NFL2K5_GUARDIAN_MANIFEST_OUTPUT=.scratch/b66-presentation/observed-xbe-manifest.json \
  python3 tests/mod_editor/test_nfl2k5_guardian_manifest.py
export PYTHONPATH=.
export QT_QPA_PLATFORM=offscreen
export NFL2K5_CAVE_MANIFEST="$PWD/.scratch/b66-presentation/observed-xbe-manifest.json"
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py
python3 tools/mycareer_mode/build_runtime.py --check
```

Reproduce the full native capture and 53-model survey from the local stadium
cache (only numeric measurements are written):

```bash
OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1 python3 tools/nfl2k5_presentation_proof.py \
  --xbe "extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  --capture docs/presentation/camera_native_v6.json \
  --cache /home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/derived/stadium-studio-v1 \
  --survey docs/presentation/camera_survey_v6.json
```

Generated C/S runtime matches its checked-in module. The proposed WIRING camera
row validates against the capability schema. Source and generated-code integrity
pins were renewed with `python3 packaging/repin.py --apply` after every pinned
source edit and immediately before commits. Protected GUI/registry/release
integration remains the concrete handoff in WIRING; gameplay appearance remains
Noah's witness below.

## HYPOTHESIS / UNWITNESSED and Noah's witness script

Bounded native execution and static geometry are not a console/GPU witness.
The survey samples finite positions and omits alpha, near-plane behavior,
dynamic crowd/LOD/collision and transient stadium assets. Smoothness, readability,
all possible physical plays and actual pause/replay transitions remain
UNWITNESSED. The 53-model zero count uses the declared historical >2% threshold.

1. Rebuild from retail with the existing ADVANCED camera option. In-game Options
   select Broadcast. Confirm Standard remains the initial/default choice and
   cycling through the seven choices does not enter First Person accidentally.
2. Chicago: run a wide sweep toward the **near sideline**, then continue toward
   each end-zone corner. Watch the camera pull inward smoothly without passing
   through crowd, loge trim or corner fascia. Repeat in Lambeau, including the
   opposite direction after a quarter change.
3. Score a touchdown, kick the PAT, and watch every frame until the **KICK RETURN**
   play call and the kickoff. Expect a sane wide following shot. Record any
   goal-post/stands view or stall, including which camera option was selected.
4. Throw a deep pass. Compare pre-snap, run, ball-in-air and catch framing. Runs
   should tighten and passes widen; the ball/receiver should remain usable as
   the camera follows. Check near-sideline catches and end-zone targets.
5. Create/load a QB career with MyCareer enabled. Check name and QB, 0/0 to a
   completion, incompletion, yards, TD and INT against the native box score.
   Open Settings, turn the line Off, save, reload, verify Off, then turn On.
   Pause, open play call, enter manual replay and allow automatic replay: the
   line should disappear and return only during eligible gameplay. Watch for
   doubled text during any off-field Supersim presentation.
6. Spot-check RB/WR/TE, defense (including a half sack), K and P careers against
   their box scores; check long names, EDGE/LB labels and both 4:3 and 16:9.
   Confirm text contrast and the top-right position do not obscure useful HUD.

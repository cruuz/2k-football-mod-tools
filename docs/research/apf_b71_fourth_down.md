# Beta 71 APF-5: fourth-down decision and pre-snap frontiers

Status: **bounded offline proof; gameplay UNWITNESSED**. No SPLB/MASTER situation
data or CPU Play Calling situation table is changed. The separate Tools dialog
exports a global, hash-keyed Xenia patch, disabled by default.

## Pinned inputs and addresses

Owned BASE XEX SHA-256:
`981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f`.
Decoded BASE image: `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`;
reconstructed TU 1.1: `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457`.
Xenia module hashes (beta-67 import-thunk normalization): BASE
`5447E5428AA2D52A`, TU `CEA825F7C2012F5A`. Decoding, reconstruction and MASTER
relocation occur in memory; no retail images or books are emitted.

| Function/frontier | BASE | TU 1.1 |
| --- | --- | --- |
| Complete offensive call | `8486CE88` | `8486DB88` |
| Scrimmage go/punt/kick chooser | `8486BD90` | `8486CA90` |
| Field-goal predicate | `8486B8E0` | `8486C5E0` |
| Punt predicate | `84866D28` | `848679F8` |
| Ordinary situation-row selector | `84867600` | `848682D0` |
| Late-game helper | `84866318` | `84866FE8` |
| Draw-offside predicate | `8485ED68` | `8485FA08` |
| Call producer, flag store and substitution | `84816FF0` | `84817C90` |
| Scrimmage substitution routine | `8486BF90` | `8486CC90` |
| Pre-snap controller | `84836698` | `84837338` |
| Native timeout eligibility | `84934D48` | `84935C10` |
| Timeout dispatch (stop before entry) | `8488E4C0` | `8488F308` |

Chooser return **17 is punt, 19 is field goal**; other witnessed returns are
scrimmage rows. These row numbers are not MASTER category indices. For example,
the isolated global-o punt call selects MASTER category index 15.

## Decision data and patch sites

Coordinates use approximately 91.44 units per yard. In the ordinary neutral
branch, goal distance beyond 50 yards forces punt. A later gate compares distance
to one yard, with a cached-random test below that cutoff. The field-goal predicate
uses kicker range minus a five-yard margin. Urgency can shrink that margin.
After the main predicates, cached random above 0.95 can still select a kick.
Late-game, score, clock and field-position branches also exist; this work does
not claim a complete football strategy model or a direct per-book strategy table.

| Parameter | Retail constant | BASE load pair / comparison | TU load pair / comparison |
| --- | --- | --- | --- |
| One-yard cutoff | `820B75C0` float 91.44 | `84867078/7C` | `84867D48/4C` |
| Own-half limit | shared 4572-coordinate value | `84867054` | `84867D24` |
| Punt slope | `82003740` float .05 | `8486708C/90` | `84867D5C/60` |
| Fallback threshold | `82003850` float .95 | `8486BF00/04` | `8486CC00/04` |
| Negative FG margin | `820B837C` float −457.2 | `8486B99C/A4` | `8486C69C/A4` |
| Negative FG margin, double arm | `820B92D0` double | `8486B978/80` | `8486C678/80` |
| Draw max yards | `82003708` float 182.88 | `8485EDF0/F4` | `8485FA90/94` |
| Draw max goal distance | `820B7A5C` float 5029.2 | `8485EE6C/70` | `8485FB0C/10` |
| Timeout threshold | `82000AC8` float 2 | `84836B20/2C` | `848377C0/CC` |

TU constants in the `820Bxxxx` region are BASE+`0x20`; the `8200xxxx` constants
remain at the same addresses. The shared own-half coordinate cannot simply be
overwritten: it also constructs distance to the goal. A separate 40-byte leaf
loads an independent threshold and performs the intended CR6 comparison.

Persistent authored data: **`844DBD80..844DBDC0`** reservation (40 used of 64
bytes), zero raw padding after `.rdata`'s virtual end (`844DBD54` BASE,
`844DBD74` TU). Code: **`84D0D000..84D0D040`** (40 used of 64 bytes), within
the code page that also contains beta-67's separate `84D0E000` reservation.
BASE XEX security descriptors classify these 64-KiB pages `0x13` (read-only)
and `0x11` (code). The image is resident; no stack or temporary resource owns
the parameter block. Native tests verify both reservations are zero and every
original instruction matches the pinned profile before applying authored words.

The 37-word patch comprises ten data words, ten leaf instructions, one branch
hook and sixteen literal-load instructions. It preserves the shared constants.
The leaf saves full r11 and f0, restores SP and changes CR6 intentionally;
it does not write LR or CTR. Exact authored TOML SHA-256 regressions plus a
full-width instruction oracle supplement PPC32 native execution. Canonical
readback refuses changed metadata, addresses, words, extra patches and invalid
parameters. Xenia application is module-hash keyed; interaction with arbitrary
third-party patches is not proved.

## Draw-offside and timeout

The draw predicate requires: unused latch `84DBAFB0`, CPU manager control,
fourth down, selected family 2 or 4, native timeout eligibility, at most two
yards to go, goal distance beyond the first-down distance, at most 55 yards to
goal, three available timeouts and score margin below ten. Inside five yards
there is an additional half-distance gate. Running-clock and late field-goal
branches add further conditions. These are numeric branch interpretations;
their football meaning is not a gameplay observation.

The producer executes the real selector and predicate, then stores `0x200000`
in team flags at team+`0x2C` and enters the scrimmage substitution routine.
The minimal isolated global-o fixture selects a real punt tuple but lacks an
ordinary replacement formation/play; its replacement pointers are zero. This
is a disclosed fixture limit, not a claim that retail match assembly fails.

The pre-snap controller reads that flag, executes native timeout eligibility,
and reaches timeout dispatch below 2.0 seconds; 2.0 and 2.01 hold. An edited
4.0-second threshold holds at 4.0 and dispatches at 3.99. Clearing the flag
prevents that timeout path. Defense snap/readiness and animation/timer helpers
have explicit synthetic boundary returns. Timeout dispatch itself is not run:
timeout decrement, animation, play clock reset and next real-match call are
**UNWITNESSED**.

## Reproducible proof scope

Run standalone with `PYTHONPATH=.`:

```sh
python3 tests/mod_editor/test_apf_fourth_down.py
python3 tests/mod_editor/test_apf_fourth_down_native.py
python3 tests/mod_editor/test_apf_fourth_down_qt.py
python3 tests/mod_editor/test_apf_xenia_edge.py
```

Native tests use optional Unicorn/Capstone and pinned owned inputs; absence
skips explicitly, mismatched present inputs fail. The prior play-call suite
relocates/validates MASTER in 7,189,487 instructions, bound 16 million. Decision
calls are bounded to 100,000; complete offensive/producer calls to two million;
pre-snap to 100,000. The native runner records adapted PPC64/vector instruction
sites; it is PPC32 execution with documented ABI/value adapters, not a Xenon
hardware witness. RNG and 50-yard kicker range are boundary inputs. Animation,
timer, player readiness and defense snap predicates are additional stated
boundaries for the pre-snap trace, never for the decision itself.

The preview matrix covers 2,016 native comparisons across both images, three
parameter sets, eight field positions, six distances and seven random values.
The enabled retail-value patch also compares 360 late-game/score/clock/urgency
decisions against untouched images. Separate tests cover an edited complete
scrimmage call, draw production, changed draw distance gates and timeout edges.
Receipts and actual outcomes are in `reports/b71_apf5/commands.jsonl` and the
final `ASTRA_REPORT.md`; failed development runs remain in that ledger.

**PROVED** is limited to pinned bytes, bounded paths, authored-byte regressions
and mocked configuration/launch tests that pass. **HYPOTHESIS** includes unseen
computed references to padding, other patch interactions, match-state assembly,
all late-game combinations and stability improvements from changing runtime.
**UNWITNESSED** includes running-match choices, player animation, timeout
consumption, actual Edge/Canary loading and SDL controller input. The Edge
source inspection was read-only web research, not a local binary test.

## Match retest

1. Record actual executable profile, loaded book, saved USER override, score,
   quarter, clocks, timeouts, ball position, distance and kicker.
2. With the patch absent, reproduce fourth-and-one near own 48; record the
   selected kick, draw attempt, timeout instant and next call.
3. Export the matching profile with short cutoff 2, own-half limit 75 and
   fallback threshold 1; explicitly enable/install and restart Xenia. Confirm
   its log applies the named patch, then repeat the same state.
4. Separately change draw gates and timeout threshold; test either side and
   exactly on each boundary, three versus two timeouts, both halves and a
   late-game deficit. Record full replacement call and timeout consumption.
5. Remove the patch, restart and retest the retail state. Do not infer a fix
   from the preview or a successful patch-load message alone.

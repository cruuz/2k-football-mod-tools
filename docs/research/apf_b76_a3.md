# A3: APF 2K8 live situations and formation multipliers

PROVED OFFLINE means pinned bytes or bounded execution, never a Xenia witness.
DESIGN identifies the authored policy and lab procedure. INFERRED identifies a
football interpretation. This work follows Urianus's items 1 and 3 only.

## Situation inventory

PROVED OFFLINE: the candidate view's complete list comes from
`apf2k8_offensive_schemes.BUCKETS`. The live patch keys are authored buckets over
actual state, not twelve stored native situation records. Ordinary requested
rows 0 through 10 are another namespace; category IDs are a third namespace.
The new thirteenth key is ordinary offense in native try phase 3.

| Candidate view label | Classification and live edit target for its sample |
|---|---|
| Openers | Studio label; 1st down, over 7 yards |
| 1st and 10 | Studio sample of native down/distance; 1st down, over 7 yards |
| 2nd and 2-3 | Studio interval; sample 2.5 maps to 2nd down, over 2 through 7 |
| 2nd and 4-6 | Studio interval; 2nd down, over 2 through 7 |
| 2nd and 7-10 | Studio interval; sample 8.5 maps to 2nd down, over 7 |
| 2nd and 11+ | Studio interval; 2nd down, over 7 |
| 3rd and 2-3 | Studio interval; sample 2.5 maps to 3rd down, over 2 through 7 |
| 3rd and 4-6 | Studio interval; 3rd down, over 2 through 7 |
| 3rd and 7-10 | Studio interval; sample 8.5 maps to 3rd down, over 7 |
| 3rd and 11+ | Studio interval; 3rd down, over 7 |
| 4th down | Studio sample 4th-and-2; 4th down, up to 2 |
| Short yardage | Studio sample 3rd-and-1; 3rd down, up to 2 |
| Red zone 25-21 | Studio label; sample 1st-and-10 maps to 1st down, over 7 |
| Red zone 20-16 | Studio label; sample 1st-and-10 maps to 1st down, over 7 |
| Red zone 15-11 | Studio label; sample 1st-and-10 maps to 1st down, over 7 |
| Red zone 10 and in | Studio label; sample is 1st-and-10 at the seven, not goal-to-go; 1st down, over 7 |
| Goal line | Studio sample 1st-and-1 at the one; 1st down, up to 2 |
| 2pt | Real native try phase; NEW independent ordinary two-point offense key 12 |
| Backed-up | Studio label; sample 1st-and-10 at own three; 1st down, over 7 |
| After negative play | Studio label; sample 2nd-and-15; 2nd down, over 7 |
| Sudden change | Studio label; sample 1st-and-10; 1st down, over 7 |
| 4-minute | Studio clock/score sample; 1st down, over 7 |
| 2-minute | Studio clock/score sample; 1st down, over 7 |

PROVED OFFLINE: an alias edits its displayed live bucket. It does not isolate
every state described by the coaching label. For example, second-and-two and
second-and-three straddle the live two-yard cut. A red-zone third-and-eight uses
third down, over seven. The same live key also applies outside the red zone.
There is no stored native red-zone-25-to-21, opener, turnover, or four-minute
formation list to expose. Both UI views now print this mapping. All 23 labels
are selectable on Live situations beside the thirteen independent keys.

PROVED OFFLINE: native decisions relevant to this view, with explicit BASE/TU
addresses, are inventoried below. These are predicates over continuous and
discrete state, not additional named spreadsheet rows. The original byte and
native evidence is in [the offense model](apf_playcall_model.md) and
[the defense model](apf_defense_playcall_model.md).

| Native distinction | BASE | TU 1.1 | Result / editor scope |
|---|---|---|---|
| Actual down and longitudinal distance | `84866258`, `8493D800` | `84866F28`, `8493E6C8` | Four downs; continuous yards. All twelve scrimmage live keys editable |
| Requested ordinary offense row | `84867600` | `848682D0` | Rows 0..10 from distance curve, jitter, urgency, overtime field position; local category comparison rows remain editable |
| Second down at 9..11 yards | Within `84867600..84867938` | `848682D0..84868608` | Uses first-down row arithmetic, without changing the actual-down patch key |
| Row curve | `820C8884` | `820C88A4` | Four interpolation points, rounded and clamped to 0..10 |
| Scrimmage / try / kick phases | Switch `8486CA0C`, phase read `8486C9E4` | `8486D70C`, `8486D6E4` | Phase 4 ordinary scrimmage; phase 3 try; phases 1/2 kicks |
| Try: kick versus two-point offense | `84866C78`, call `8486CA64` | `84867948`, `8486D764` | Row 19 for kick, or ordinary row with effective down 4; ordinary try gets new live key 12 |
| Field goal | `8486B8E0`, selected at `8486BDDC` | `8486C5E0`, `8486CADC` | Row 19; native special path |
| Punt | `84866D28`, selected at `8486BDF8` | `848679F8`, `8486CAF8` | Row 17; native special path |
| Hail Mary | `84866B28`, staging `8486BE08..BE3C` | `848677F8`, `8486CB08..CB3C` | Cached formation/play and its primary row; not a four-minute list |
| Clock-management call | `84867150`, staging `8486BE54..BE9C` | `84867E20`, `8486CB54..CB9C` | Cached clock formation/play; not every ordinary call with four minutes left |
| Onside versus regular kickoff | `848670C0`, dispatch `8486CA24` | `84867D90`, `8486D724` | Row 22 versus 21; special phase |
| Additional fourth-down punt/FG arbitration | `8486BEF8..BF80` | `8486CBF8..CC80` | Time estimate, field position, kicker range and cached random |
| Effective clock, score, timeouts, urgency | `8486A250..A704`, `84868970` | `8486AF50..B404`, `84869670` | Adjust native requests and weights; no single 120/240-second formation row |
| Backed-up formation factor and yardage interpolation | `84869058..848693F8` | `84869D58..8486A0F8` | Real field-position/rating arithmetic; no independent backed-up key |
| Explicit formation-family dispatch | `8486C980` | `8486D680` | Families 0..3 wildcard row 25; punt 17; FG 19; Kickoff name 21, other kick family 22; remaining families null |
| Mode-specific requested-row override | `84A3CEC8` | `84A3DDA0` | Separate U mode 9 input; retained native |
| Explicit saved/subtype call | `8486CEB0..CF58` | `8486DBB0..DC58` | Saved play or subtype fetch before ordinary draw; retained native |
| Defense response to offense personnel | `84869B60`, `848696E8` | `8486A860`, `8486A3E8` | Separate defense mapper; no new offensive coaching buckets |

PROVED OFFLINE: special rows 17/19/21/22 and cached Hail Mary/Clock calls remain
outside these ordinary-formation hooks. They were not additional editable
ordinary candidates in the 23-label view. Their real native identities are
listed here rather than relabeled as ordinary aliases. This release does not
provide arbitrary special-play formation exclusions or personnel replacements.
A broader interpretation of "every live situation" that includes those
special selectors is not completed by A3. Their caches can bypass the draw
hooks; changing them requires separate guarded cache/tuple work, not removal
of the existing safety gates. Defense policy is likewise outside this change.

## Patch design and ownership

DESIGN: v3 extends the existing consent-installed situation patch, with no new
installer or automatic enablement. Older v1 and v2 canonical payloads remain
recognizable. Projects without weights or a try edit still export v2. Enabling
the project switch alone does not install a patch. Build export includes both
profiles and receipts. Removing the installed patch requires a Xenia restart.

DESIGN: formation factors are positive powers of two: 0.25, 0.5, 1, 2, 4.
One means no stored override. Zero is the separate exclusion control with its
empty-draw fallback. At the formation hook, multiply the already enumerated
native weight by the selected book/key/formation factor and execute the original
power-one lottery. Category enumeration and its cubed lottery remain native.
The decomposition is category curve x mean rating, followed by formation native
weight x local multiplier. These are weights, not absolute call percentages.
They cannot create missing candidates or choose different personnel by themselves.

| Allocation / hook | BASE | TU 1.1 |
|---|---|---|
| Category exclusion draw | `8486B198` | `8486BE98` |
| Formation draw | `848696C0` | `8486A3C0` |
| Local personnel comparison row | `8486B090` | `8486BD90` |
| Code, same pre-existing reservation | `84D0E300..84D0EFFF` | Same |
| Immutable table | `8462CA00..8462FFFF` | Same |
| Last-draw receipts | `852D6500..852D653F` | Same |

PROVED OFFLINE: generated v3 code is 3,260 bytes in the 3,328-byte reservation.
No new code space is claimed. The v3 generator omits spills only for registers
it never changes; it still preserves full-width live GPRs, CR, f0/f13, FPSCR and
SP, and does not touch LR or CTR. The v1/v2 generators retain their old bytes.
Independent disassembly checks every instruction and direct branch target.
The existing cave/section/reference audit runs against both pinned images.

DESIGN: table magic APF4, version 3, count, stride 288; each book has a 28-byte
ASCII key matched exactly against runtime UTF-16 name, then thirteen 20-byte
formation masks. A bounded sparse personnel appendix uses four-byte records
`book,key,category,row`. The following bounded weight appendix uses eight-byte
records `book,key,formation,zero,f32 factor`. All words are big-endian. The
13,824-byte allocation admits at most 47 named books, fewer with many overrides.
Capacity is checked before staging/export. Canonical decoding rejects duplicate,
foreign, malformed, nonfinite and out-of-range entries or nonzero padding.
Runtime header/count/appendix bounds and factor bounds fail back to native.

DESIGN: masks and multipliers apply only to structurally valid ordinary draws.
No book, MASTER, runtime pointer cache, RNG helper or persistent game file is
modified. Empty exclusion results restore the whole original draw, including
original weights. Exclusions and local personnel rows share the same project
writers, receipts and Undo path as prior versions. New weights have their own
request kind and are included in transition and prediction cache keys.

PROVED OFFLINE: `SituationPatch.revert_image` verifies every patched word,
restores displaced instructions and original zero padding, then verifies the
entire original image SHA-256. This is an offline exact-revert check, not a live
hot-unpatch mechanism. For users, remove the canonical installed file and restart.

## Offline results

PROVED OFFLINE: `test_apf_b76_situation_weights_native` passes five tests on both
pinned images. Twenty-four scrimmage-key vectors match the cold model, including
0.25x, 0.5x and 4x factors after native book normalization. Phase-3 vectors verify
exclusions, personnel comparison rows and weights independently of phase-4
fourth down. The complete try witness (fourth period, -5, 110 seconds, two yards)
selects category 1 and formation 27, and records live key 12 on both images.

PROVED OFFLINE: O-ManBlock Queens native weights 2/2/2 become 2/8/2 at
third-and-eight. In 96 deterministic formation draws per arm and image,
formation counts 2/14/24 change 32/32/32 to 16/64/16. Twenty-four complete CPU
calls per arm change 8/8/8 to 4/16/4. First-and-ten and third-and-five retain
identical complete output tuples. These deterministic quantiles are explicit
RNG boundary inputs, not estimates of full-game probabilities. Malformed
headers/counts, foreign or absent policies and an emptied draw retain native
output/book/MASTER/team bytes and GPR/CR/FPR state in the tested cases.

PROVED OFFLINE: native elapsed time is 316.334 seconds, measured peak resident
memory 665,940 KiB, CPU affinity 24..31. Receipts record profile pins, generated
code hashes, branch audits, distributions and complete-image revert hashes in
`reports/b76_a3/native-receipt.json`. No Xenia or disc build was run.

## Main's Xenia witness

DESIGN: do this separately for BASE and TU 1.1. A3 does not launch either.

1. Start from a separate built test folder and a named offensive book assigned
   to the CPU. Record the source folder, module profile, saved-roster selection,
   actual runtime book name and patch receipt SHA-256. Avoid a saved USER book
   silently replacing the edited disc book. Use O-ManBlock with Queens formations
   2, 14 and 24 present and equivalent raw ratings for the clearest conditional
   comparison. Retain enough valid pass plays in each formation.
2. In Live situations, leave 1st down over seven at 1x for all formations. For
   3rd down over seven, set formation 14 to 4x; leave 2 and 24 at 1x. For a test
   with frequent Queens calls, stage Queens comparison row 10 in this third-down
   bucket in BOTH baseline and treatment projects. Save both project recipes.
   Do not change global yardage sliders between arms.
3. Baseline: install an otherwise identical patch with formation 14 at 1x,
   restart, and record 200 CPU calls at 3rd-and-8, midfield, first quarter,
   neutral score/timeouts, plus 200 at 1st-and-10 in the same field/clock state.
   Use CPU play calling in a repeatable Practice state if available; otherwise
   reset an exhibition state. User-chosen calls do not test this hook.
4. Treatment: install the 4x patch, restart, repeat both 200-call sets. Record
   selected personnel, formation, play, live down/distance/phase and fallback
   receipt. Within Queens draws with three equal native weights, the expected
   formation-14 share changes from 1/3 to 2/3. Overall formation frequency also
   depends on which personnel category wins; do not demand that unconditional
   calls equal 2/3. First-and-10 should show no systematic treatment effect.
   Report counts with sample sizes; a finite game sample is not byte identity.
5. Try coverage: set only the independent two-point bucket to exclude formation
   2 and request Queens comparison row 10. Use an exhibition try with fourth
   period, trailing by five, about 110 seconds remaining, and CPU control.
   Confirm ordinary offense is selected, key 12 is used, formation 2 is absent
   unless the fallback flag is set, and the observed formation/player lineup is
   valid. Test a fourth-and-two scrimmage separately; its key must be 9 and its
   controls unchanged. PAT kicks must retain the native path.
6. Revert: remove the installed situation patch, restart, and repeat the baseline
   states. Also test 1x reset plus reinstall, and project Undo/save/reload without
   reinstall to confirm the UI explicitly reports the installed patch mismatch.
7. Capture screenshots/video of edit, install status, actual CPU call, requested
   personnel and selected formation. An empty TE depth chart may substitute an
   FB, so separate requested TE roles from actual players.

INFERRED: live learned history, fatigue, roster substitution, saved-book loading
and native special decisions may change observed frequencies relative to cold
offline samples. A3's receipt does not prove those lifecycle or rendered outcomes.

### Result (main's lab, 2026-10-01)

PROVED IN GAME in Xenia on BASE, with patches built by the Studio's own path from this release's code and checked byte
for byte against `compile_patch` on the real BASE image. Practice, Full Scrimmage, no controller assigned, so the CPU
called every play; midfield. Third and eight was held by writing the down word after each re-spot; first and ten used
the natural state. The formation of each call was read from guest memory (the committed pointer and the game's own name
string, checked once against the screen), and the patch's receipt counted every draw with its live key.

| arm | third and eight: formations 2 / 14 / 24 in Queens | first and ten: formation 14 / Queens / calls |
| --- | --- | --- |
| baseline (patch installed, all 1x) | 13 / 19 / 14 (14 on 19 of 46) | 0 / 2 / 21 |
| treatment (14 at 4x, 2 and 24 at 0.25x) | 3 / 42 / 1 (14 on 42 of 46; expected 8 of 9) | 1 / 4 / 21 |
| patch removed | 20 / 19 / 6 (14 on 19 of 45) | 1 / 4 / 21 |

All 92 receipted third-and-eight draws used key 8 with all three candidates kept and no fallback; all 42 receipted
first-and-ten draws used key 2. Fisher's exact test: treatment against baseline p = 4.9e-07, removed against baseline
p = 1.0. The live book was O-TwoBack (the CPU offense in Practice was always the profile's created team), which has
the same Queens formations 2, 14 and 24 with equal native weights. INFERRED: a held down is equivalent to a natural
third and eight for the selector (the receipts show key 8). Not covered: TU 1.1, the two-point key, exclusions,
personnel rows, Undo and reinstall.

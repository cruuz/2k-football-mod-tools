# r62 momentum-contact, 2026-09-06

**EXPERIMENTAL / UNWITNESSED. All presets remain off.**

Built the requested bounded tier C extension in the existing Momentum owner,
with independent `momentum_collisions` and `momentum_collision_level` settings.
It adds a mass-times-approach-velocity term to the carrier's two native Break
Tackle reads. The original ratings, sliders, charge comparison, velocity blend,
random threshold and reaction dispatcher continue to select outcomes. Nothing
is labelled witnessed: Noah has not played this implementation.

The protected dispatcher, BuildPlan, GUI, release closure and reservation JSON
are unchanged. Their complete integration instructions are appended to
`WIRING.md`. The existing capability object is updated as a concrete registry
handoff. No network, console emulator, GUI display, audio or push was used.
Unicorn executed only bounded native routines against synthetic objects.

## Authority and decisions

Read the hub memo `MOMENTUM_RESEARCH_2026-09-05.md`, including sections 3/4,
the RC85 product changelog, and the Momentum, abilities, allocator scale-out,
integration and gameplay-lever reports before extending their implementation.
The other ASTRA report inventory was checked for existing ownership/features.
The read-only Ghidra corpus's `functions.tsv` and
`pseudo_c/shard_008704_009215.c` corroborate the native contact paths. Assembly
and the pinned USA executable are the authority for the wrapper ABI.

Retail input SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Only the supplied extracted executable is read into memory, about 12 MB; no
whole disc or archive pack is loaded. Disc transport uses existing streaming
writers and disposable directories.

The memo explicitly defers a general collision solver. This task implements the
brief's narrower outcome-input extension. It does not add impulses, conserve
energy, change animation assets or force the Truck ability. Ordinary live
carrier eligibility remains the scope; active shoulder charges, jukes, dives,
locked tackles and other special carrier states fall back to retail. Their
existing native weight/velocity/charge effects remain active.

## Exact model 2 rule

Let `n` point from the carrier to the opponent, using their horizontal position
separation. Read both actual horizontal velocities at the first Break Tackle
call, before the resolver's later velocity mixture. Decode both roster weight
bytes as `byte + 150` pounds, matching native contact. Then:

```text
carrier_approach = dot(carrier_velocity, n)
defender_approach = max(0, -dot(defender_velocity, n))
p = carrier_mass * carrier_approach - defender_mass * defender_approach
v_ref = 640.0800170898438 + 274.32000732421875 * .99
collision_bonus = .06 * collision_level/100 * clamp(p/(220*v_ref), 0, 1)
sampled_bonus = min(.08, existing_runup_bonus + collision_bonus)
effective_break_tackle_for_this_read = min(1, native_attribute + sampled_bonus)
```

Require positive finite carrier approach before either bonus. A stationary,
retreating or perpendicular carrier gets zero new benefit. Zero separation or
nonfinite geometry gives zero; nonfinite defender approach disables the new
collision term. A defender moving away contributes zero opposing momentum.
A stronger opposing approach reduces or eliminates the benefit; there is no
new negative rating penalty. Pounds are an explicit calibration unit: a common
conversion to kilograms cancels in numerator and reference denominator.

The collision contribution is at most **six effective rating points** at
level 100. Both experiments together stay within **eight points**, even with
both levels at 100. This bounds the new rating input; it does not guarantee a
monotonic probability, animation, displacement or dominance relationship in
every native branch. Existing low ratings still select their native early
exits in the bounded extreme-mass/speed checks.

**PROVED, direct installed-wrapper samples**, native effective Break Tackle .5,
stationary 220-pound defender, collision level 100, run-up off:

| Carrier mass | Carrier approach | Adjusted attribute |
| --- | ---: | ---: |
| 180/220/320 lb | 0 | 0.500000, exactly unchanged |
| 180 lb | 300 | 0.516154 |
| 220 lb | 300 | 0.519744 |
| 320 lb | 300 | 0.528719 |
| 180 lb | 900 | 0.548463 |
| 220 lb | 900 | 0.559233 |
| 320 lb | 900 | 0.560000, capped |

The public settings contract accepts integer levels 0..100 and strict Boolean
flags. A positive collision level requires its flag. True/0 has no effect.
Both levels zero return exact retail bytes without allocation. Collision-only
mode (`momentum=0`, `momentum_contact=False`) leaves the dispatcher, turn curve
and both floor copies byte-identical to retail. It needs no run-up or prior
movement callback. The old run-up option still requires positive movement
momentum and retains its original formula when collisions are off.

CLI, new output only (existing destinations refuse):

```sh
python3 -m mod_editor.core.nfl2k5_momentum <source.xbe>
python3 -m mod_editor.core.nfl2k5_momentum <source.xbe> \
  --output <new-copy.xbe> --level 0 --collisions --collision-level 50
```

Omitted replay settings retain the installed values and return the same bytes
object with zero changed bytes. Changing any setting refuses. Model 1 uses a
different allocation/code shape and intentionally refuses in-place upgrade;
rebuild from the supported source with the complete owner union.

## Native sites, identity, ownership and parity

The only contact hooks remain the complete five-byte calls at `0x1D9D62` and
`0x1DA39F`, originally `e8a912faff` and `e86c0cfaff`. Both invoke the original
`0x17B010` accessor first, forwarding modifier `0x104` and preserving its
`ret 4` convention. No global accessor hook or permanent rating change exists.

The first hook caches one scalar for the two reads, keyed by entity, opponent,
resolver EBP, simulation tick, carrier state pointer and roster pointer. The
last three keys reuse the three previously reserved dwords in each 64-byte
slot. A later read does not resample native blended velocity; changing velocity
after the first sample retains its bonus. Changed tick, pair, frame, holder,
state or roster suppresses it. New first reads replace the sample, including
zero-effect contacts; repeated same-pair resolutions do not add to the old
bonus. Slots are protected by both movement and contact timestamps, preventing
collision-only entities from stealing another current sample. Exhaustion
returns retail and increments the existing diagnostic counter.

The shared eligibility check now also guards null/sentinel velocity and roster
pointers. The attached-ball check guards null and -1; opponent entity, kind,
velocity and collision-weight record are checked before added reads. These
are native-graph checks, not arbitrary-address memory validation. No added
instruction reads controller index, side, position, Truck permission or a
cosmetic star to choose collision strength.

**PROVED:** the complete native `0x1D9C50` resolver, effective accessor, threshold
curve, `0x1DADD0` pair scalar, `0x1DB370` pair cache and `0x1DBDB0` reaction
dispatcher are hash-pinned. Only the two exactly validated owned call operands
are normalized when comparing resolver bytes. Foreign dependent code, mixed
hooks, altered configuration, owner code, nonzero on-disk state or stale
section/seal bytes refuse before an installed result. Section digests use the
existing helpers; named code is installed through `space.install_code`.

**PROVED, bounded:** complete resolver fixtures retain the native rating/weight
mixture, slider lookup, charge comparison, RNG call and both returns. Pose,
effective-attribute values and RNG values are declared external boundaries.
With Break Tackle .20 and matched scalar/RNG, the 180-lb/900 and 220-lb/300
cases retain native return 1; 320-lb/900 and 220-lb/900 return 0 with collisions,
while retail returns 1 for all four. At .01/.15 the capped change cannot move
the tested early exit, even at 405 lb and speed 1300.

A further fixture executes complete `0x1DBDB0`, its actual `0x1D9C50` call,
and the downstream branch. In a declared pose/move context it selects
`0x1D8F50` on retail versus `0x1D8F90` with collision momentum. Animation entry
is the boundary, using ABI-correct return fixtures. Those addresses are
observed destinations, not invented universal labels for truck, stumble,
broken tackle or completed tackle. Full reaction animations remain witnesses.

Human marker 0 and CPU marker -1 produce identical results and output vectors
in the matched resolver matrix and identical downstream destinations. That
fixture deliberately sets carrier +0x2D=1 for both, bypassing retail's separate
human move early-out before the attribute reads. **This proves added-rule parity
in a common native context, not removal of retail controller/side branches.**
The matrix compares full standstill results and vectors against retail, not
just a Python formula or an isolated bonus number.

Both application orders with actual abilities produce identical bytes. The
bounded composition executes the Speedster call/store (raw 127 -> cache 1.27),
Momentum braking/restoration and both contact reads. Existing abilities native
permission/meter suites also pass. The new bonus does not unlock a disallowed
Truck action. Legacy acceleration's native AI bypass remains a separate known
limit; the protected wiring extends the existing profile normalization to
collision-only builds so a newly requested legacy ramp is disabled.

The assembled template occupies **1,400 bytes**, padded to **1,408 RX bytes**;
state remains **2,064 RW bytes**, zero on disk. The code increase is 464 bytes.
The pre-build scratch plan reserved an upper bound of 1,792 RX with unchanged
RW, fitting alongside every committed beta-62 budget. The actual fixture
replaces only Momentum's 944-byte code row with 1,408. No separate new Momentum
row was specified in the scale-out report, so this extension deliberately
uses the existing owner's capacity and adds no RW demand. No allocator policy,
page count, unrelated budget or unreserved cave was changed.

Standalone collision apply selects v3, and a legacy preallocation refuses
with a scale-out rebuild message. In the complete union, the allocator may
place this existing owner's child in a legacy RX page within the v3 layout;
that is its explicit named allocation, not a hardcoded address claim. All
manifest owner lists already contained Momentum. Both manifest probes and
both XBE gates now install collisions at 100 alongside all other owners,
including abilities, in forward/reverse order. The manifest additionally
records the installed Momentum settings.

## Tier A/B audit against beta 61

The memo describes alternatives and larger proposals, not a promise that
beta 61 implemented every lever. This bounded task keeps movement calibration
stable and documents each omission instead of silently adding another model.

| Memo item | Shipped implementation and decision |
| --- | --- |
| A: Running/Tackling/Pursuit sliders | Existing native inputs/writers remain. No new slider remap. Hold sides equal during comparisons; retail side/charge branches remain. |
| A: high-command turn curve and floor | Implemented in beta 61: five-point record, last three ordinates reduced; data and inline floor both changed. Low-command points and count retained. This is command-based global data, not scope-specific or physical-speed turning. |
| A: slower positive acceleration curve | General 10-20% preset was not implemented by Momentum. Retain native launch/weight/Agility math. Beta 62's separate slow-QB owner supplies its own scoped 65% curve; no duplicate curve is added here. |
| A: strafe curve and heading bypass | Unchanged. A separate direction/rate path exists; ordinary turn changes do not limit all strafe facing. Deferred pending a specific witness. |
| A: contact threshold curve | Unchanged and now pinned. New mass/velocity bonus changes per-resolution rating inputs; it is not a global threshold-table rebalance. |
| A: locomotion bounds / animation or special-move tables | Unchanged. Arbitrary playback changes can affect reach/foot sliding and are outside this extension. |
| B: speed-estimate/Speedster-aware ordinary turn formula | Not implemented: beta 61 chose the simpler global q curve. Cached Speed does not enter that table. The memo's `omega * max(.25, 1-.5*m*u*u*(1-.3*a))` remains deferred, with scoped role/caller exclusions still needed. |
| B: braking envelope | Implemented: `t_stop=m*(.4-.12*agility)`, current native q, dt, throttle/neutral heading substitution through dispatcher AND tail return. Raw fields restored conditionally; native acceleration retained. Actual displacement and root-motion animation remain unwitnessed. |
| B: lifecycle / controller parity | Implemented: entity/state/roster identity, real simulation tick, state age, ordinary-state eligibility, 32 nonaliasing slots, stale reset, same-tick reuse, catch/control-switch continuity. New collision sample keys use existing spare words. Universal save/load and every state population remain unproved. |
| B: run-up optional contact | Implemented in beta 61 and retained. 21 simulation frames, not a dt-accumulated .35 seconds at all frame rates. Fixed v_ref omits the memo's conditional .975 factor. The new collision option is independent of this history and has its own level. |
| B / section 5: carrier and other-player sliders | Not shipped. Movement has one global level; no separate carrier/noncarrier scope or immediate scope-level swap. Do not claim the memo's 50/0 versus 0/50 scope experiment is available. |
| B: legacy ramp / abilities composition | Beta-61 profile disables newly selected legacy ramp. Actual beta-62 abilities now exists and composes in both orders, replacing beta-61's deferred proof. No second launch envelope or Speedster cache owner is introduced. |
| C: conserved impulse / full collision physics | Still deferred: authoritative velocity/displacement handoff, friction/restitution, root-motion replacement, paired ordering, piles, airborne/braced/wrapped states and all reaction assets need further proof. This task supplies the explicitly bounded mass-times-velocity outcome term only. |

## Verification and disposable evidence

All tests are standalone plain `python3 file.py` unittest commands. Missing
retail/Unicorn/Capstone/assembler gets a precise skip; this host supplies them.
The existing Momentum fixture now maps all actual v3 sections and uses distinct
caller addresses for the first and later contact reads. Rewriting one caller
address had let Unicorn's translated-block cache retain the first target;
the corrected test proves later-read coherence even after velocity changes.
No product logic was changed to hide that fixture issue.

Final results are appended below. The protected reservation file was never
regenerated here; generated manifests, logs and receipts stay under
`.scratch/momentum-contact`.

## Noah's witness list, all pending

Start with the same roster, ratings, home/away sliders and input sequence;
legacy ramp off and movement/run-up off. Compare collision off/0, on/50,
on/100 before combining with movement or run-up. Record model/version, all
four settings, actual XBE hash, carrier/defender identities, mass, intended
approach and repeated results. RNG requires repeated paired situations.

1. **Mass at equal speed:** light/heavy backs with matched ratings against
   the same defender, straight approaches and both field orientations. Record
   trucks, stumbles, wraps, breaks and yards after contact; check ratings still
   distinguish strong/weak tacklers and carriers.
2. **Speed at equal mass:** stationary, jog, short run-up and full-speed contact
   against stationary/incoming/chasing defenders. Standing carriers must gain
   no added benefit; incoming heavy defenders should reduce it. Check side,
   perpendicular, retreat and near-zero separation contacts.
3. **Human/CPU:** reproduce the same pairs with either side/controller and CPU
   carrier, then switch control immediately before contact. Include native
   charged contact and movement early-outs; the bounded matched fixture does
   not certify every controller-specific retail branch.
4. **Moves and reactions:** shoulder charge/Truck, spin, both juke styles,
   stiff-arm, hurdle, dive/charged tackles, wrap-up struggle and falls. Check
   special-state exclusions and transitions; no ordinary bonus should unlock
   an ability-denied move or replace its animation.
5. **Possession/lifecycle:** catches in stride versus standing catches,
   scrambling QBs, interceptions, punt/kick returns, loose balls, new play,
   substitutions, fatigue/injury, save/load and reused player identities.
   Look for stale bonuses, held motion or transfer to another player.
6. **Tier A/B regression:** with collisions off, compare Retail/50/100 movement
   for 45/90/180-degree cuts, jog/full-speed turns, neutral release, reversal,
   stop/go, pursuit and strafe. Measure stop distance and foot sliding; the
   existing global q curve is not a Speedster-aware or two-scope turn rule.
7. **Abilities/combined options:** raw Speed 99/100/127 with Speedster off/on;
   permitted/denied Truck; run-up off/on; then both experiments at 100. Check
   native meter and animation behavior, especially the abilities owner's
   existing carrier-only meter restrictions on noncarriers.
8. **Loader and full stack:** after Claude wires the protected fields and
   regenerates the release manifest, build a paired full-feature disc, boot,
   enter practice/exhibition/franchise, play kickoff in both directions and
   repeat after save/load. Report boot failures and unrelated feature changes
   with exact settings/hash; offline section permissions do not prove Xbox
   kernel acceptance or console memory pressure.

Known gaps are protected product integration, the explicitly listed tier A/B
alternatives, full reaction/animation execution, pile/impulse physics,
universal native-context parity and Noah's gameplay/loader witnesses. These
are not labelled completed by the bounded implementation.

## Final validation and delivery evidence

On branch `astra/r62-momentum-contact`, base
`f371972f4a17cecf654c019d5c6ff3a3c32c7caa`. Standalone command prefix is
`python3` unless shown otherwise. Final shared suites use
`NFL2K5_CAVE_MANIFEST=.scratch/momentum-contact/manifest.json`; this points at
actual freshly observed writer evidence and keeps source checks enabled.

| Command / check | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_momentum.py` | 23 passed, 23.801 s |
| `python3 tests/mod_editor/test_nfl2k5_momentum_collisions.py -v` | 16 passed, 33.209 s |
| `python3 tests/mod_editor/test_nfl2k5_abilities_runtime.py` | 12 passed, 23.157 s |
| `python3 tests/mod_editor/test_nfl2k5_abilities_unicorn.py` | 12 passed, 7.506 s |
| `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 passed, 93.150 s |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 13 passed, 33.474 s, fresh manifest |
| `QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3 tests/mod_editor/test_beta61_allocator_integration.py` | 7 passed, 66.703 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, 158.248 s, both owner orders |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, 241.124 s, both owner orders |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 68.816 s, fresh manifest |
| `python3 tools/nfl2k5_momentum_assemble.py --check` | Exact reproduction of checked-in template |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | 34 requests fit; new-owner RW availability stays 4,096 bytes |
| Changed Python files and five WIRING Python snippets | Parse successfully |
| Updated registry object in combined registry | Schema passes; every new evidence and backend/validation module path exists |
| Fresh manifest source SHA-256 check | All 103 match final writer sources |
| Brief-protected files compared byte-for-byte to HEAD | All unchanged |
| `git diff --check` | Pass |

**264 final tests passed, with no skips.**

An initial allocator proof against the stale checked-in manifest correctly
refused an overlap with the old smaller Momentum allocation. It passes with
the newly generated manifest; no reference/source guard was disabled. The
broader integration test initially expected the old exact code total 16,535;
it now expects **16,999**, the measured 464-byte increase, and passes. Its
permission, stable-address, metadata and reverse-order checks remain intact.
The full existing-registry file check still reports the pre-existing missing
`docs/research/apf_audio.md`; this does not affect the new object's verified
schema or closure. No absent evidence was fabricated.

The actual disposable manifest command was:

```sh
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 /usr/bin/time -v \
  python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json .scratch/momentum-contact/manifest.json
```

It performed the actual Experimental preset build plus the separate dormant
owner probe, wrote/read back the grown XBE and verified section digests. The
probe records movement 100, run-up true, collisions true/100, model 2. Its
`runtime_panel_resources: false` remains visible: this probe establishes XBE
ownership/transport, not a played or fully paired runtime-scorebug witness.
No protected product wiring was substituted in memory.

| Manifest evidence | Result |
| --- | --- |
| Reservations / observed writer calls / source fingerprints | 8,991 / 102 / 103 |
| Final owner-probe XBE SHA-256 | `b8cf1a1e2dc4eed356d280c50683aa5b73429c8fbf95c84c8b17b9d8e123f25b` |
| XBE size | 12,300,288 bytes |
| Momentum named code / state VAs in this union | `0x14D95A0` / `0x14BB4A0` |
| Build wall time / peak RSS | 4:52.46 / 1,167,548 KiB |
| Memory gate / cave gate / oracle peak RSS | 293,400 / 482,248 / 905,900 KiB |
| Final allocator proof peak RSS | 235,280 KiB |

Disk preflight ran `df -h /` and measured 109,449,842,688 bytes free. It reserved
the 6,300,499,968-byte source-disc size plus a 1,000,000,000-byte work allowance
while requiring 100,000,000,000 bytes remain free, also satisfying the 40 GB
start threshold. During the build the observed free space was 103,131,435,008
bytes. After completion it was 109,436,694,528 bytes, and no temporary oracle
disc remained. TemporaryDirectory cleanup completed before this report was
finished. Scratch contains small JSON/log/text evidence only, well below
200 MB. The largest measured process stayed below 2 GB.

Explicit-path staging succeeded on this branch. The final commit includes only
the feature source/template/assembly, standalone and composed tests, budget
fixture, capability object, report and WIRING handoff. `ASTRA_BRIEF.md`,
`.scratch/`, retail/generated executables and discs are excluded. No push.

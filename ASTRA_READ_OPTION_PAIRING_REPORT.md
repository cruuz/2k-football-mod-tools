# Read option final-book pairing, 2026-09-08

Branch `astra/r64-read-option-pairing`, base `45c0544a`.
**EXPERIMENTAL / UNWITNESSED.** The resolver, compiler integration, standalone
tests and protected-file handoff are implemented. The two requested complete
Experimental image builds remain **BLOCKED by the 100 GB disk floor**. They
were explicitly attempted through the acceptance runner, which refused before
copying a disc. Passing bounded resource/XBE tests below do not replace that
missing full-build acceptance or a gameplay witness.

No protected source, canonical reservation manifest, other worktree or retail
input was edited. No network, emulator, GUI display, audio or push was used.

## Delivered behavior and decisions

- `mod_editor/core/nfl2k5_play_intents.py` adds
  `resolve_final_pairs(image, retained_pairs, progress=None)`. It checks the
  retained SHA-256/schema/indices, revalidates the authored intent through the
  real compiler, reads each final team book once, and resolves the original
  slot plus custom name. A moved play must have a unique matching name. A
  renamed, missing or ambiguous play refuses. Multiple independent retained
  compilations for one team become one final pair; duplicate retained plays
  and conflicting personnel evidence refuse.
- All eleven assignment descriptors and complete node chains, plus the play
  flags, must equal the retained authored play. This is deliberately more
  conservative than checking only the QB/back runtime hashes: it also protects
  the RPO receiver route. Relocated relative pointers are allowed when their
  decoded descriptors and nodes are identical. A refusal names team, original
  play/name, final slot, assignment slot and whether the descriptor or nodes
  changed. Inputs and images remain unchanged on refusal.
- `nfl2k5_playbook_pack.recompile_final_intents` is a new compiler entry point
  for reports from final bytes. It makes unchanged self-donor requests, runs
  synchronization and retail play validation, and uses the existing
  formation/play and personnel compilers to reproduce the final resource
  byte-for-byte. Its final report includes the final SHA-256, option/Spy
  records, resolved names/indices, native validation provenance and zero
  changed bytes. It does not retag a retained compiler report with a new hash.
- Both runtime `compile_intent_table` APIs accept this final report schema,
  repeat its compiler proof and check the full resulting report. The runtime
  record formats, hashes, capacities, executable instructions, hooks,
  allocations and status/apply logic are unchanged. Table receipts identify
  the actual final resource. Existing legacy compiler pairs still work.
- `WIRING.md` and `tests/fixtures/read_option_pairing_wiring.patch` specify the
  exact protected Build changes. Retain at pack time; after the existing book
  passes resolve final pairs; compile both selected tables; verify the final
  pairs; install through the existing final `_apply_all`. Nothing else moves.
  Initial `read_option_preflight` stays intact. Final resolved counts and
  identities go in `play_intents_final`, and `play_intents_summary` supplies
  plain completion text. The new resolver needs one release-allowlist line and
  one runtime-closure import, both documented. No new UI option or capability
  surface is introduced. Both flags remain off in every preset.

### Additional PROVED obstruction: pooled defensive personnel

Depth roles alone changes 12 bytes in the shipped MIN book, but the actual
Advanced/Experimental pipeline also changes 22 defensive personnel bytes in
the position-pool pass. A direct self-donor compiler call on that final book
refuses with:

> Unrecognized or recoded defense personnel/package fingerprint; native donors are required

That is independent of the stale complete-resource hash. Fixing only the
original equality check would therefore still fail the required presets.

The final compiler creates an explicit native-personnel **validation view**
using the retained native codes. It accepts this view only if the existing
pool and/or depth-role writers reproduce the entire final resource exactly.
No names, flags, descriptor words, pointers or nodes differ between the views.
Native donor/MLB/menu/opponent-fixture checks run on that certified view; actual
final scripts also pass the existing synchronization/retail validators. The
personnel compiler then reconstructs the exact final resource. Its new report
keeps the native compiler's report separately as provenance. Table compilers
repeat this proof before using the view for the original fixture checks.

Unknown personnel edits and changed defensive fixture geometry refuse. The
native authoring validator still rejects pooled sources outside this explicit
translation path; its fingerprint set and behavior were not weakened. The
matched runtime scripts have the same bytes in both views, so their runtime
hashes are unchanged. Both the final-resource hash and the separate native
compiler hashes remain reviewable.

## PROVED retail-byte evidence

Commands:

```sh
python3 .scratch/read-option-pairing/prove_nodes.py
NFL2K5_PAIRING_REAL_BUILD=1 /usr/bin/time -v python3 tests/mod_editor/test_nfl2k5_play_intents_build.py -v
```

The evidence reads the original XISO through `OuterImage`, one 78,768-byte PLAY
resource at a time. It installs the shipped option pack through the real pack
writer, applies the real pool transformation to all 37 books, then runs
`depth_roles.apply_to_archive(..., allow_custom=True)` on those bounded real
resources. The old `_verify_play_intents` fails on its retained pair. The new
resolver returns final compiler pairs accepted by the unchanged verifier.
This is a real-resource writer pipeline, **not a complete Experimental disc
build**. No synthetic bytes substitute for the book contents.

`.scratch/read-option-pairing/node-proof.json` contains the exact before/after
descriptor words, every node's hex, decoded opcodes/flags/operands, affected
formation names, resource hashes and final table receipt.

| Stage | MIN resource SHA-256 |
| --- | --- |
| Retail | `50673fd09d38f4a17057a4e79a87119ee861456dd4416b94191b1563aa60887e` |
| Shipped pack installed | `b54805a0f8d2013ff49907a81d41b9ca1ab517a610854ba06a73902d14fd1ccf` |
| After pools, immediately before roles | `471d919dedba1980b3114d47998642acceef9dc553de3cc5be7a41556ce0fb0b` |
| After depth roles | `c180ed3ad11b901eef35d0c275a29cf85cf192938cc242d252fd0a51d1f83962` |

Every descriptor and node in **all eleven assignments** is equal before and
after roles for both plays. The runtime hashes two complete five-node chains,
the QB and back, rather than just two individual nodes. Their exact values:

| Play / assignment | Descriptor before = after | Node-chain SHA-256 before = after |
| --- | --- | --- |
| 155 Zone Read / QB 0 | `00b12915` | `445edb36f91f4d6d8d03d1ba090d771d43e256c6fc1846f9ba0f2c9f549bcf1c` |
| 155 Zone Read / back 10 | `00b10115` | `3934c21da8c53ff29e87086975d9e99d48bd799f4d5701eb59fc9f3ad4aef78e` |
| 157 RPO / QB 0 | `00b12d15` | `3289bc4c2af6664f3c5a812ad5a0160fcd03eefddd23e29302e839f7ae83aa9b` |
| 157 RPO / back 10 | `00b10115` | `3934c21da8c53ff29e87086975d9e99d48bd799f4d5701eb59fc9f3ad4aef78e` |
| 157 RPO / receiver 7 | `01b11013` | `1d1c814ec7b25b591ac1ce408b90876655873791e0d30df0f46de16c30bf4dc5` |

The final table contains exactly two reads, indices **155** and **157**, and
is byte-identical to the table compiled before the book passes. Its SHA-256 is
`7832f07955ff1eec66cfbe6a58e77f780da0f261619ae0df038b1396edcd427c`.
All six speed-option records are excluded from runtime read count as before.

The bounded XBE proof installs this active two-read table and the QB-spy
owner on the pinned retail executable in both orders. Both statuses are
`applied`, the installed read-only bytes equal the compiled table, and both
complete output hashes match. The separate authored ATL MLB Spy test produces
one nonempty Spy record after both personnel passes, with its descriptor and
two-node script pinned and its table byte-identical to the original.

The shipped option pack has no Spy intent, so `qb_spy=True` alongside that
pack correctly gives **two reads and zero authored Spy assignments**. This
does not disable the owner's existing native zone/man/rush behavior.

## Full Experimental acceptance: refused before copy

Exact command:

```sh
NFL2K5_PAIRING_REAL_BUILD=1 /usr/bin/time -v python3 tests/mod_editor/test_nfl2k5_play_intents_build.py -v
```

The runner writes the exact proposed protected module to
`.scratch/read-option-pairing/mod_build.py`, uses its real `BuildPlan` and
Experimental preset, then separately selects:

1. `read_option_runtime=True` plus `data/playbooks/softdrink_option.2k5book`.
2. Those same options plus `qb_spy=True`.

Both cases were skipped with **103,428,001,792 bytes free** and
**113,112,999,936 bytes required**. The threshold is 100,000,000,000 bytes
remaining plus two 6,300,499,968-byte output copies and 512,000,000 bytes for
growth. Even a single ordinary source copy would cross the floor at the
observed free space. The two-copy allowance covers resource rebuilds without
loosening the user's floor.

The exact measurements are in `read-only-disk.json`, `read-and-spy-disk.json`
and `build-tests.log` under `.scratch/read-option-pairing/`. No acceptance disc
was created, so there is no 6 GB image to delete and no successful full-build
receipt to claim. The runner creates each eventual image under a resolved
`TemporaryDirectory`, outside `.scratch`, and deletes it on success or failure.
It verifies final play names, final resource hashes, installed counts and both
selected owners' statuses before cleanup. The source remains read-only.

## Standalone validation

The commands below ran from the worktree root. Regression suites used
`PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen`; these tests do not display
a GUI. `/usr/bin/time -v` measured each process independently. Logs are under
`.scratch/read-option-pairing/`.

| Command after `python3` | Result | Seconds | Peak RSS KiB |
| --- | --- | ---: | ---: |
| `tests/mod_editor/test_nfl2k5_play_intents.py` | 18 passed | 29.402 | 59,516 |
| `tests/mod_editor/test_nfl2k5_play_intents_build.py -v` with real-build flag | 3 passed, 2 disk-floor skips | 18.980 | 149,388 |
| `tests/mod_editor/test_nfl2k5_read_option_runtime.py` | 10 passed | 7.124 | 130,136 |
| `tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 13 passed | 136.707 | 162,540 |
| `tests/mod_editor/test_nfl2k5_formation_play_writer.py` | 8 passed | 1.105 | 40,856 |
| `tests/mod_editor/test_nfl2k5_playbook_pack.py` | 36 passed, 1 private uniform-catalog skip | 1.747 | 175,420 |
| `tests/mod_editor/test_nfl2k5_read_option.py` | 15 passed | 9.509 | 96,640 |
| `tests/mod_editor/test_nfl2k5_defense_play.py` | 12 passed | 125.228 | 100,332 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 passed | 357.445 | 315,428 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 103 passed | 450.265 | 505,884 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 27 passed, 1 expected stale ESPN pin error | 107.662 | 910,440 |

The existing Build suites also ran against the **exact scratch copy** of the
protected proposal, with only the test process's module binding redirected to
that copy. The harness restores the checkout's resource root for the copied
module. It does not replace its build functions or the compiler/resolver.

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -v python3 .scratch/read-option-pairing/run_wired_suite.py tests/mod_editor/test_mod_build.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -v python3 .scratch/read-option-pairing/run_wired_suite.py tests/mod_editor/test_mod_build_beta62_integration.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -v python3 .scratch/read-option-pairing/run_wired_suite.py tests/mod_editor/test_mod_build_beta62_integration3.py
```

| Existing suite against proposed Build | Result | Seconds | Peak RSS KiB |
| --- | --- | ---: | ---: |
| `test_mod_build.py` | 11 passed | 1.685 | 167,636 |
| `test_mod_build_beta62_integration.py` | 8 passed | 151.915 | 192,132 |
| `test_mod_build_beta62_integration3.py` | 11 passed | 96.686 | 245,948 |

These use their existing bounded synthetic transports and pinned executable
fixtures; they do not claim full retail-disc acceptance. The proposed Build
copy passes its context-based patch check and preserves preset definitions.
`git diff --check` and `git diff --cached --check` pass. Protected-file diffs
are empty. `python3 -m py_compile` passed for the four changed core modules
and both new tests. The existing complete budget also passed:

```sh
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json
```

The oracle's sole error is exactly the brief's expected base defect:

```text
stale reservation source: mod_editor/core/nfl2k5_espn25_scenarios.py; regenerate manifest
```

No private manifest or pin replacement was used to conceal it. Claude must
regenerate the protected manifest after landing, including the changed host
compiler/runtime fingerprints. Both XBE gates already enumerate these owners
and compose them in both orders; there is no new owner to add to their union.
The maximum observed test RSS is 910,440 KiB, below the 2 GB limit. Neither a
whole archive pack nor a disc image was loaded into memory.

## HYPOTHESIS, pending integration and Noah's witness list

**PROVED:** byte equality, fresh compiler reports, known personnel translation,
strict refusal, two runtime records, active XBE installation, both XBE gates,
and supported Shotgun authoring through both personnel passes.

**HYPOTHESIS / pending:** the complete Experimental preset produces the desired
on-field behavior. Full-disc acceptance remains blocked by disk headroom;
protected Build/GUI/packaging integration and canonical manifest regeneration
remain Claude's handoff. No gameplay or visible mesh result is witnessed.
This change adds no read-table capacity and makes no animation, collision,
balance or receiver-readiness claim beyond the existing runtime.

The brief's Shotgun description differs from the shipped pack. The actual
calling locations, all zero-based indices, are:

| Recipe | Team / formation | Play indices / names |
| --- | --- | --- |
| Shipped option pack | MIN / **I Jokers** | 155 `SD Zone Read EXPERIMENTAL`; 157 `SD RPO EXPERIMENTAL` |
| Additional shared menus | MIN / I Jokers Pair; Split Jokers | 155 also in I Jokers Pair; 157 also in Split Jokers |
| Separate existing Shotgun recipes | MIN / **Gun: Doubles Right** | 134 `SD Gun Zone Read`; 31 `SD Gun RPO Slant` |

The new `test_min_shotgun_reads_survive_pool_and_depth_roles` authors those
Shotgun recipes with the real compiler and proves final pairing. They are not
silently installed by, or substituted into, the shipped option pack. Do not
look for the shipped two names in Shotgun or advertise them as Shotgun calls.

After protected wiring and a successful disposable acceptance build, Noah's
witness list is:

1. In MIN's indicated formation, call Zone Read and **hold the snap button
   through the mesh window to keep**. Confirm one ball, QB carry and back
   release; repeat both directions and supported controller layouts.
2. **Release the snap button during the window to give**. Confirm a clean
   handoff; check early/late release, re-press and repeated inputs. A committed
   decision must not reverse or create a second exchange.
3. Call the RPO, hold snap and **press the receiver during the mesh**. The
   current slot-7 recipe uses B in the supported default layout. Confirm a
   native pass attempt to the intended receiver, with no late handoff or stuck
   QB. Check release without a receiver press, late press and an unready target.
4. For the separately authored Shotgun recipes, repeat keep, give and RPO in
   **MIN / Gun: Doubles Right**. Record snap/exchange/throw timing and animation;
   the I-form resource proof does not witness Shotgun ball handling.
5. Have the defense crash, stay wide, block the expected edge and substitute
   defenders. Check CPU selection, stable decisions and the no-candidate case.
   Record the actual selected actor and outcome rather than inferring a read
   from a tackle.
6. Repeat with QB spy enabled, plus an explicitly authored Spy assignment for
   a nonempty Spy-table witness. Check normal runs/passes and both selected
   runtimes through audibles, no-huddle, substitutions, controller changes,
   replay, pause/resume, possession changes and consecutive snaps.
7. Check the cue only during the human mesh, in normal/widescreen and supported
   multiplayer views. Preserve the build receipt, table hash, exact formation,
   play name and video for each observation. All witnesses remain pending.

## Delivery

Changes are committed on the assigned branch using explicit paths, including
this report, the resolver/compiler/runtime changes, the two standalone test
files, the wiring fixture and WIRING.md. `ASTRA_BRIEF.md` and `.scratch/` are
excluded. No push is performed. The scratch module, decoded node proof and
logs remain available for the protected integration and acceptance retry.
The final scope audit found all 11 protected files byte-identical to HEAD,
282,615 bytes of scratch evidence before the final audit/allocator JSON, and
102,746,890,240 bytes free on the main drive. No acceptance images or archive
pack copies remain.

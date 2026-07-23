# APF 2K8 Membership-Consumer Census

## Result

The external census runner is implemented at
`tools/apf_membership_consumer_census.py`. It is observation-only and contains
no retail game bytes. Its purpose is to find code paths that read or write the
APF team-member array/count boundary before anyone claims that a 43rd through
53rd roster slot is safe across the whole game.

This tool does **not** prove 53-man rosters, modify a roster, or modify the
game executable. A positive single run proves only that the reviewed hook
captured a valid headless boot trace. Global convergence has separate gates
described below.

## Current lock

The Linux x86-64 live runner is pinned to exactly:

- Xenia SHA-256
  `712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d`;
- source commit `d09cae8d8374324048ef603d48a9c1696b39d552`.

That build received independent source review, a clean Release build, and a
dedicated hostile-thunk sentinel. The sentinel calls the census transition
itself, deliberately clobbers its protected volatile GPRs, XMM1 through XMM15,
and MXCSR, checks the System V callback stack alignment, and proves execution
continues with every promised value restored. It passed 22 assertions; all 18
backend tests passed 88 assertions and the full CPU suite passed 247 test cases
with 845 assertions. This proves hook/thunk safety, not APF runtime causality.
The Windows thunk received static review only.

The stable local checkpoint is
`artifacts/apf_membership_census_xenia_d09cae8d/`. It includes the exact
binary, both source patches, Xenia's license, and an independently checked
`SHA256SUMS`. The binary retains the reviewed absolute RUNPATH
`/home/noah/.codex-tmp/xenia-build-env-19/lib`; that environment must remain
present on this host. Rewriting the RUNPATH would create a different binary
and requires a new review and pin.

`REVIEWED_STATIC_LEDGER_SHA256` remains `None`. Therefore one pinned live boot
trace can now run, but global `census_converged` status remains locked until the
static candidate inventory and every disposition receive independent review.
Supplying arbitrary values on the command line cannot bypass either boundary.

Dry-run preparation remains available before the pins land. It admits the
provided binary/XEX hashes, builds isolated roots and the exact command, hashes
the entire source tree before and after, writes a private manifest, and launches
no emulator process.

## One headless pass

```bash
python3 tools/apf_membership_consumer_census.py run \
  --xenia /absolute/path/to/reviewed/xenia_canary \
  --xenia-sha256 712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d \
  --hook-commit d09cae8d8374324048ef603d48a9c1696b39d552 \
  --game-dir /absolute/path/to/extracted/APF2K8 \
  --run-root /absolute/path/to/new-private-run-directory \
  --scenario boot_headless_smoke \
  --pass-index 1 \
  --timeout-seconds 180
```

Add `--dry-run` to prepare and verify the manifest without launching Xenia.
The current runner deliberately refuses other scenario labels because it uses
null GPU, audio, and controller backends. Roster-management, depth-chart,
team-select, and gameplay coverage need a later isolated operator/script
profile with an explicit scenario-completion receipt. A label alone is not
scenario evidence.

## Isolation and source safety

Every run creates fresh private storage, content, cache, HOME, XDG, temporary,
and log roots. It disables title updates, patches, plugins, Discord, scratch,
and memory-unit mounts. The source game is never copied or opened for writing
by the runner. The whole source tree and `default.xex` are hashed before and
after the bounded Xenia process group.

`xvfb-run` itself receives no `TMPDIR`, so its owner-only Xauthority directory
uses the secure system `/tmp` default. The fixed `env` executable restores the
run's private temporary root only for the Xenia child. This split avoids the
Debian wrapper's unquoted Xauthority expansion when a run-root path contains
spaces, while preserving Xenia's private temp isolation and avoiding a shell.

The Xenia command forces `--store_all_context_values=true`. This is required so
the hook can reject stale link-register context rather than reporting a false
caller. The hook must emit exactly one protocol receipt before any other census
receipt:

```text
APF_MEMBERSHIP_CENSUS receipt=protocol version=1 observation_only=true
```

A missing, duplicate, reordered, or changed protocol receipt is
`validation_rejected`.

## Receipt contract

The parser accepts this bounded v1 vocabulary:

- `receipt=epoch_invalidated epoch=N`
- `receipt=validation_accepted epoch=N teams=40 memberships=1344`
- `receipt=validation_rejected epoch=N reason=TOKEN`
- `receipt=access epoch=N pc=XXXXXXXX lr=XXXXXXXX op=read|write width=1..16|32|128 region=member|count team=N slot=N byte=N`
- `receipt=census_failed epoch=N reason=unsupported_overlap|overflow|event_limit|malformed_access|root_reload|dropped_event|context_state_not_forced`

Normal loads/stores and partial-vector operations may report any exact integer
width from 1 through 16 bytes; this includes non-power-of-two widths such as 3,
5, or 15. MEMSET intersections may retain their original 32- or 128-byte
interval width.
For `region=member`, `byte` is the first intersected byte within that
four-byte membership slot (`0..3`), and one receipt is emitted per intersected
slot rather than per byte. For `region=count`, `slot` is zero and `byte` is the
count byte's lane within the original access interval (`0..width-1`). This
preserves whether a wider load/store reached `+0xC5` through its first or a
later byte. Widths 32 and 128 are write-only MEMSET intervals.
Reserved/atomic, partial-vector, or other interval forms must either be
normalized to the exact access interval above or fail closed as
`unsupported_overlap`. Hook arithmetic `overflow` is a validation failure,
because it means the address interval could not be classified safely.
`event_limit`, `dropped_event`, and parser-capacity loss are `trace_overflow`,
never a successful partial result. Epoch zero and an all-zero source PC are
invalid. A second root invalidation in one process is a fatal v1 `root_reload`;
a cold reload is a new isolated process.

Raw PCs, LRs, epochs, teams, member slots, byte offsets, and log lines stay in
the private Xenia log. `result.json` stores only fixed reason codes, counters,
booleans, and domain-separated SHA-256 fingerprints. A consumer fingerprint
covers the full `(pc, lr, op, width, region, team, slot, byte)` key. A separate
PC-only site fingerprint can be joined to the reviewed static ledger without
publishing the guest PC.

## Classifications

- `validation_rejected`: toolchain, source integrity, protocol, epoch, or hook
  validation failed.
- `path_not_reached`: the exact v1 protocol ran but no validated epoch appeared.
- `trace_overflow`: the hook or parser reported a dropped/capacity-limited trace.
- `partial_coverage`: some evidence exists, but a required completion,
  scenario, matrix cycle, reviewed pin, or static candidate is missing.
- `scenario_census_complete`: one validated headless boot trace contains at
  least one exact access and no rejection/overflow.
- `census_converged`: offline aggregate only; never emitted from one hook run.

## Offline aggregation

```bash
python3 tools/apf_membership_consumer_census.py aggregate \
  --input /private/cycle-1-boot-run \
  --input /private/cycle-2-boot-run \
  --required-scenario boot_headless_smoke \
  --convergence-passes 2 \
  --static-ledger /private/reviewed-static-ledger.json \
  --output /private/census-aggregate.json
```

Pass indexes are matrix-cycle indexes. Convergence compares the union of all
required scenarios in each complete cycle; independently stable scenario runs
with non-overlapping pass indexes do not count as complete cycles. Two or more
final complete cycles must have identical consumer-fingerprint sets.

Stable runtime traces are still only `partial_coverage` until all three trust
requirements pass, and until the caller requests the exact fixed global matrix:

`boot_headless_smoke`, `frontend_navigation`, `team_select`,
`roster_management`, `depth_chart`, `play_now_offense`, `play_now_defense`,
`play_now_special_teams`, `substitutions`, `injury`, `stats`, `postgame`, and
`cold_reload_fresh_process`.

The current null-GPU/null-HID runner can generate only the first scenario.
Therefore global convergence is structurally unreachable in this v1 operator
profile, even if a caller supplies a smaller stable matrix.

Each `--input` is a complete private run root, not a copied `result.json`.
Aggregation verifies the recorded manifest/log hashes, reparses
`logs/xenia.log`, recomputes the sanitized receipt set and classification, and
requires exact equality with `result.json`. It also requires the result's
source-tree and `default.xex` before/after digests to match each other, and the
result's source-tree-before digest to match the manifest's admitted tree
digest. The `*_unchanged` booleans are never accepted as the sole integrity
evidence. This catches protocol drift and accidental/local partial tampering.
It is not a cryptographic defense against a malicious machine owner who
deliberately fabricates every file in a bundle.

The remaining trust requirements are:

1. the result toolchain matches the installed reviewed Xenia/hook pins;
2. the static ledger matches its installed reviewed SHA-256 pin;
3. every static candidate site was observed at runtime or has a reviewed
   explicit disposition (`statically_resolved`, `false_positive`, or
   `unsupported`).

The aggregate carries the ledger digest and counts, never its path, raw guest
locations, or retail bytes.

## Verification receipt

Synthetic coverage lives in
`tests/test_apf_membership_consumer_census.py`. It covers pin admission,
protocol/version enforcement, every partial-vector width from 1 through 16
(including confirmed width 3), rejection of width 17, write-only 32/128 MEMSET
intervals, epoch lifecycle, overflow/rejection paths, retail-free result
sanitization, source mutation detection, complete matrix-cycle comparison, and
reviewed static ledger gates.

A fresh real-source dry-run then admitted the final pinned artifact/commit
pair without launching Xenia. It preserved all six files and 3,919,218,688
bytes, kept the source-tree digest identical before and after, and left
`default.xex` unchanged. The generated command uses null GPU/audio/controller,
fresh private roots, forced full context state, and the observation-only cvar.
Its private manifest is at
`.codex-tmp/apf-membership-census-dryrun-d09cae8d-20260719-1/manifest.json`.

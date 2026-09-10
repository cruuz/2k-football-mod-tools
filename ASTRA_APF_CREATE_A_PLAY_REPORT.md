# APF Create a Play / Design Formation — Astra delivery

2026-09-09. **Offline implementation and proof complete within the authorized
files. Every new gameplay result is UNWITNESSED.** The main-window, Build
dispatcher, capability registry and release integration remain with Claude under
the protected-file rule; exact changes are at the top of [WIRING.md](WIRING.md).
This is not an integrated installer or an in-game validation claim.

## Delivered

| Brief item | Result |
| --- | --- |
| Alignment dependency first | Cherry-picked `24274c91` as local commit `5c8a8bdd` before implementation. Its two files are unchanged by this work. |
| Native PLAY proof | All 586 plays, 163 formations, 4,948 nodes and the complete 182,096-byte MASTER body round-trip exactly. |
| The 38 failed conversions | All are opcode `1C`; native APF bit layout and callback ownership recovered. All 38 now re-encode exactly; offsets, hashes and operands listed in the derived JSON. |
| Existing-play edits | Same index, same-slot stock assignment copies via the existing route writer; unique node chains edited in place, shared chains detached into checked free capacity. Numeric movement, route, read, zone, man-cushion and lane fields supported. |
| New plays | Six bounded append slots, indices 586..591; explicit same-side clone-and-replace also implemented. Custom UTF-16BE names with all relative pointers rebuilt. |
| New formations | Thirteen bounded append slots, indices 163..175; donor category/personnel and slot ordering retained, all three coordinate variants editable. Donor opaque 84-byte row cloned for a new formation. Replacement preserves destination personnel compatibility. |
| CPU callability | Existing named SPLB rows accept new play indices. An explicitly empty row can inherit a compatible donor trailer for a new formation. CPU books only; no user-save writes. |
| Defense | Real defensive clone with a changed zone landmark at play 591 compiles and enters X-34Base. All stock man/zone/rush/defense-start/dual-lane nodes round-trip. |
| Concepts | Real Smash, Levels / Drive, Dagger, Curl-Flat and Mesh recipes compile together, with explicit stem/turn distances and backside routes. The physical QB landmark is -21 feet; five-step timing is not claimed. |
| Persistence / controls | Canonical logical JSON, one atomic stage/undo, idempotent staging, source/payload pin checks, project save/import, facade adapter and an offscreen-tested standalone panel. No retail payload is stored in a project. |

Code and proof commit: **`85c8af9a`**, “APF: prove native PLAY encoding and add
bounded play and formation design”. The final report is a separate commit.
Both manual commits use explicit path lists; no `git add -A`, push, release,
emulator, display, audio or game-data network operation was performed.

## Proof and concrete build

Read [the format proof](docs/research/apf_play_format.md) for table/field offsets,
relative-pointer encoding, callback addresses, units, replacement constraints,
SPLB ownership and relocation design. The complete semantic dump is
[apf_play_format_derived.json](docs/research/apf_play_format_derived.json).

MASTER decoded SHA-256:
`2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891`.
The BASE flat executable was pinned to
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`;
all cited code addresses use `file_offset = VA - 0x82000000`.

The previously missing native table is at `0x820FBFC8`, 29 rows of **16**, not
20, bytes. Flags are at `0x820FBE68`. Native `1C` uses mask `0xC00F3F3F` and
differs from NFL's layout/flags. The stock legacy conversion is 4,910 exact /
38 changed; native encoding is 4,948 exact / zero opaque operand nodes.
Descriptor high nibbles describe 6,446 assignments and 1,737 distinct starts;
every assignment ends with native terminal flag `0x20`.

| Resource / case | Allocation | Active compressed bytes | Free bytes |
| --- | ---: | ---: | ---: |
| MASTER stock on disc | 57,344 | 56,356 | 988 |
| MASTER stock with reviewed optimal encoder | 57,344 | 54,822 | **2,522** |
| Combined authored MASTER, optimal | 57,344 | 55,290 | **2,054** |
| Combined authored MASTER, portable fallback | 57,344 | 57,026 | **318** |
| Combined O-TwoBack, optimal | 2,048 | 1,652 | 396 |
| Combined X-34Base, optimal | 2,048 | 1,030 | 1,018 |

The combined test appends the five concepts, defensive play 591 and formation
163, then adds CPU calls in outer 259 records 0/25 and outer 618 record 0. It
finishes with **164 formations, 592 plays, 5,010 nodes**, 863 changed MASTER body
bytes, exact H7A round-trips, zero overlapping matches, unchanged file ownership,
and successful independent reparsing of all three resources. No pack was written.
The portable compressor produced the same decoded result with the smaller free
budgets shown above; this is an offline fallback proof, not a Windows runtime run.

The [logical example](docs/research/apf_play_design_example.json) reproduces the
[derived build receipt](docs/research/apf_play_design_build_derived.json) exactly.
Its resulting MASTER body SHA is
`e13f57801d90579450996354485bad919ea0122634d20b7597f8530e046287a4`.
The CLI compiles into memory and writes only a derived JSON receipt outside the
source tree. The protected Build integration consumes its in-memory entries.

## Decisions where context and evidence diverged

1. **The asserted MASTER membership writer is absent, and the relation is not
   established as formation membership.** `tools/playbook_inventory.py:248`
   explicitly retracts that name. The fresh audit of 11 named CPU books finds
   only 1,650 of 6,727 entries covered (24.53%) and zero of 171 populated records
   fully covered. Existing bytes are preserved; a new formation copies its donor
   row without invented membership bits. SPLB provides the proved call association.
2. **Pass operand 1 is a receiver selector, not drop steps.** Decoder
   `0x84A91420` plus consumer `0x84A87E30..54` establish selector-plus-five player
   slot lookup. Movement `04` Y and route `12` distance have biased integer-feet
   encodings and native feet-to-centimetres consumers. The recipes use those
   proved landmarks. Five-step animation/cadence remains unproved.
3. **Physical capacity is not supported capacity.** The play table physically
   holds 640, but the current strict inspector limits the opaque relation's
   74-byte interpretation to 592. The writer permits six new plays, 13 new
   formations and 452 spare nodes subject to actual compression/name fit.
4. **Growth beyond those bounds is design work only.** The checked NFL formation
   writer uses fixed-capacity slots/names/nodes. APF's block directory can express
   a resource appended to the final pack and repointed by offset/size; the format
   document gives exact fields and why earlier-pack growth shifts later starts.
   No relocation writer or loader-acceptance proof is claimed.
5. **Spy and full freehand creation are deferred.** Native defense encoding is
   established, but no APF QB-tracking owner proves a dedicated spy. The complete
   native gameplay validator is not ported. Existing chain shapes/descriptors
   are retained; arbitrary opcode graphs, flags and timing are not exposed.

Smash's 10-yard corner stem / 5-yard hitch-curl stem, Levels / Drive depths,
Dagger vertical/dig, Curl-Flat and Mesh crossings are real authored recipes.
Their football execution, legal alignment, route-side behaviour and timing are
UNWITNESSED. Dagger pre-snap shifts, Pirate and a true five-step drop are not
implemented. The previous alignment witness does not witness newly appended
records or these designs. BASE and TU 1.1 need separate in-game checks.

## Tests run and output

All new test files run standalone with plain `python3`. The nine older
regression files were invoked with `PYTHONPATH=.` to supply the repository root,
as required by their existing imports. Qt was offscreen. Latest results:

| Command (from repository root) | Output |
| --- | --- |
| `python3 tests/mod_editor/test_apf_play_designer.py` | `Ran 27 tests in 13.929s` / `OK` (includes all four retail proofs) |
| `python3 tests/mod_editor/test_apf_play_designer_project.py` | `Ran 5 tests in 0.153s` / `OK` |
| `python3 tests/mod_editor/test_apf_play_designer_qt.py` | `Ran 5 tests in 0.127s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_splb_writer.py` | `Ran 22 tests in 0.125s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py` | `Ran 14 tests in 0.255s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_splb_tag_reassignment.py` | `Ran 86 tests in 1.428s` / `OK (skipped=5)` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_package_map_writer.py` | `Ran 27 tests in 0.382s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf2k8_playbook_route_writer.py` | `Ran 12 tests in 0.177s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_formation_alignment_writer.py` | `Ran 44 tests in 0.202s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_project_document_workflow.py` | `Ran 13 tests in 4.469s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_project_streaming.py` | `Ran 6 tests in 0.008s` / `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_capability_action_parity.py` | `Ran 11 tests in 0.071s` / `OK` |

**272 tests executed: 267 passed, five older fixture-dependent tests skipped.**
The unavailable old tag-reassignment fixture is independent of the four new
retail proofs, all of which ran successfully against the supplied APF extraction.

The new suite's missing-retail gate was also tested deliberately:

```sh
APF_RETAIL_INDEX=/does-not-exist/apf-test/0A python3 tests/mod_editor/test_apf_play_designer.py -v
```

Output: `Ran 27 tests in 2.229s`, `OK (skipped=4)`. Each skip says
`Retail APF 0A absent: /does-not-exist/apf-test/0A; set APF_RETAIL_INDEX to extracted read-only retail`.
The 23 synthetic tests still run, including synthetic IFF/H7A resources, numeric
field bounds, ownership isolation, idempotence, CPU tags/empty records, exhaustion,
tamper rejection and oversized-plan rejection.

Reproduction commands (set the input variables to the paths in the supplied context):

```sh
python3 tools/apf_play_format_proof.py --index "$APF_RETAIL_INDEX" --pe "$APF_FLAT_PE" --output docs/research/apf_play_format_derived.json
python3 -m mod_editor.core.apf2k8_play_design_build --index "$APF_RETAIL_INDEX" --plan docs/research/apf_play_design_example.json --receipt "$APF_RECEIPT_OUT"
```

Observed output:

```text
PASS: {'plays': 586, 'formations': 163, 'categories': 28, 'nodes': 4948}; legacy 4910/38; native exact; 2522 free bytes
APF_DESIGN_VERIFIED entries=[180, 259, 618]; receipt=.astra-work/example-cli-receipt.json; UNWITNESSED in-game
EXAMPLE_RECEIPT_EXACT: CLI result matches combined retail proof
CAPABILITY_PROPOSAL_VALID: 8 rows; merged registry 132 rows; protected registry unchanged
PROTECTED_FILES_UNCHANGED: 9
NEW_PYTHON_SOURCE_PORTABILITY_AUDIT: 7 files; no raw os.open, os.rename, or /tmp literals
STAGED_AUDIT_PASS: text/source/derived JSON only; prior WIRING.md preserved exactly
```

The capability proposal was merged and checked **in memory**, with full existing
registry validation and evidence file checks. It did not modify the protected
registry. Compilation/AST checks and staged `git diff --check` also passed.
The final retail receipt equals the committed derived receipt. No installer,
protected Build dispatcher or clean staged release check is claimed.

## Git delivery and sandbox limitation

The first requested `git cherry-pick 24274c91` encountered a real filesystem wall:
the worktree's original `.git` points to
`/home/noah/2k-football-mod-tools/.git/worktrees/astra-apf-create-a-play`, and
creation of `index.lock` there is denied by this sandbox. The permission profile
only permits writes in this worktree and temporary storage; escalation is disabled.
No permission was requested and that original checkout/metadata was not changed.

To finish the commits locally, `.astra-local-git` was created **inside this
worktree**, starting from the same base `4498b643ec089440cd4a66a992f16999c8716fef`
and branch name `astra/apf-create-a-play`. It reads existing objects through an
alternate and stores all new objects/refs locally. Commands use
`git --git-dir=.astra-local-git --work-tree=.`. The sequence is:

1. `5c8a8bdd` — required alignment cherry-pick, first.
2. `85c8af9a` — native proof, writers, panel, persistence, tests, example and wiring.
3. `APF: record Astra proof results and integration boundaries` — this report.

`ASTRA_COMMITS.bundle` carries the commits since the shared base and the local
branch ref. The bundle is a handoff artifact, not committed into its own history.
It is verified with `git bundle verify`. For a writable integration checkout:

```sh
git fetch /path/to/ASTRA_COMMITS.bundle refs/heads/astra/apf-create-a-play
git log --oneline 4498b643ec089440cd4a66a992f16999c8716fef..FETCH_HEAD
```

Then cherry-pick the listed commits in order, omitting the alignment cherry-pick
if the integrator already landed the same change. **The original worktree branch
ref remains at the base; the new commits live in the local Git database/bundle.**
The user's brief/context files are uncommitted and untouched. Earlier WIRING.md
content (863,663 bytes) is preserved exactly after the new integration section.

## Remaining integration and witness

Claude must apply the exact protected page/build/registry/allowlist/runtime
closure changes in WIRING.md together, including capability action bindings and
the Playbooks category mapping, then exercise the actual Build dispatcher and
clean release checks. The logical design refuses composition with the legacy
MASTER/SPLB editors until an explicitly verified common compiler is added.

Noah's witness should cover CPU selection of the new IDs, new formation
personnel/alignment, offensive and defensive assignments, route geometry on both
field sides and QB timing, on BASE and TU 1.1. Unknown relation semantics, the
complete game validator, larger growth, spy and five-step cadence remain named
research boundaries, not silently implemented promises.

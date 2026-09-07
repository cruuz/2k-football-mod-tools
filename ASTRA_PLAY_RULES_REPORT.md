# Astra play rules editor report

Public path notation: `<home>` and `<media>` identify the original local home and mounted input directories. Recorded hashes, measurements and outcomes are unchanged.

| Rule vocabulary | PLAY data | Evidence and authoring boundary | Runtime consumers |
| --- | --- | --- | --- |
| Defensive combo exchange | 0x1B -> 0x0D -> 0x0E paired with 0x1B -> 0x0E -> 0x0D | PROVED. Partner is man operand 5 (c), transition operand 6; zone has transition operand 6. Keep slots 4/9 and 6/10 together in ATL p28. | 0x0019FA10, 0x001A2E70, 0x001A5090 |
| Zone run / zone step | 0x11 type 8 in the sampled Inside/Outside Zone line; offsets, turn, end and group | PROVED bytes; HYPOTHESIS football policy. Both sampled zone runs use type 8, group 2; their lateral offsets differ. Other runs use type 0 drive legs. No separate zone-step toggle or guaranteed double-team command was proved. | 0x0023ABB0, 0x002400B0, 0x0023F450 |
| Double team / combo block | No dedicated opcode established | PROVED runtime candidate selection; HYPOTHESIS double-team interpretation. The resolver ranks primary/secondary live candidates, sees other blockers and can swap their targets. Copying a leg cannot prescribe a new coordination algorithm. Not authorable as new AI. | 0x002FAFF0 (especially 0x002FBF26..0x002FC179) |
| Pull / trap | 0x11 type 2 with lateral/depth offsets and time | PROVED data and distinct runtime path. The type-2 path selects its own movement/update helpers. Engagement and timing against a live front remain unwitnessed. | 0x002400B0, 0x0023F450 case 2 |
| Lead / release then block | 0x11 types 4 / 3, optionally preceded by 0x18 | PROVED grammar; HYPOTHESIS result. Copy every leg; a selected path is not a guaranteed live defender. | 0x0023ABB0, 0x0023F450 |
| Pass set / slide protection | 0x11 type 1; 0x1A in conditional protection | PROVED data; PROVED runtime slide offset. 0x0023B6E0 counts predicted threats by side and writes the bounded offset at 0x00C16BAC. Pass-set consumers add it. No new authorable slide algorithm. | 0x0023B6E0, 0x0023ABB0, 0x0023F450 |
| Zone landmarks | 0x1B -> 0x0D; X, depth, selectors and boundary mode | PROVED. Runtime initializes a zone record and adds actor adjustments; later callbacks pick receivers and steer. Landmark coordinates alone do not implement Palms or match quarters. | 0x001A6220, 0x001A5090, 0x001A5790 |
| Man target and cushion | 0x0E with receiver selectors, side and depth | PROVED. Friendly exchange partner and geometric opponent selector are different fields. | 0x001A5BC0, 0x001A2E70 |
| Rush / fire zone | 0x1B -> 0x0B; replacement 0x0D coverage over front | PROVED grammar; HYPOTHESIS football result. A coverage can drop a front lineman; active coverage wins overlap. Preserve a legal eleven-slot front/coverage union. | 0x001CEA80, 0x001A8C80, 0x001A8CB0 |
| Screen hold and release | 0x11 finite hold -> 0x18 -> 0x11 type 3; receiver 0x12 type 9 | PROVED. Not every screen-named play uses that grammar. Nominal delays do not promise a throw or catch frame. | 0x00229AE0, 0x0019C740; ASTRA_SCREEN_PASS_REPORT.md |
| Read / motion / synchronization | 0x1A with explicit path flags; 0x13/0x16 transfer pair | PROVED predicate; HYPOTHESIS modern read. Kinds 0/1 test assignment/header, 4 position/velocity, 5 geometry, 6 another decision, 7 personnel. No new EDGE/apex recognition policy is authored. | 0x001ACE40, 0x001AC7B0; ASTRA_READ_OPTION_BUILD_REPORT.md |

EXPERIMENTAL / UNWITNESSED. PROVED means byte-level or static code evidence.
No gameplay result was witnessed in this session.

## Completed work

The Create a Play assignments page now has Assignments, Rules library and Info tabs.
The library extracts complete per-position bundles from the loaded resource, supports
named selectors and searching every play, remaps friendly references, retains explicit
branch flags, validates the combined eleven assignments and stages through the existing
writer/project/pack pipeline. Unchanged donor chains reuse their pointers. The Info panel
is read-only, searchable and generated from structured JSON plus the codec parameter schemas.
Top-level Studio registration, release closure and capability integration are specified
in WIRING.md because the brief protects those shared files.

## Representative complete-chain audit

All indices are zero-based. Counts below list every slot, 0 through 10; shared and
inactive chains are included. Each sample was decoded completely and re-encoded node
by node, then applied to its original formation/play through the compiler. Every
result reproduced the entire 78,768-byte resource with zero changed bytes.

| Rule | Book / formation / play | Retail name | Nodes by slot |
| --- | --- | --- | --- |
| combo_inside | ATL / 23 (Nickel) / 28 | Combo Inside Zone | 2, 2, 2, 2, 3, 2, 3, 2, 2, 3, 3 |
| outside_zone | ATL / 6 (Quads) / 77 | Strong Outside Zone | 3, 2, 2, 3, 2, 2, 2, 2, 2, 5, 3 |
| power | ATL / 2 (Split Flip Pro) / 98 | Strong Power | 3, 2, 2, 3, 2, 2, 2, 2, 2, 5, 3 |
| counter | ATL / 10 (Ace) / 127 | Weak Counter | 3, 2, 2, 3, 2, 2, 2, 2, 2, 5, 3 |
| draw | ATL / 6 (Quads) / 159 | Strong Draw | 4, 3, 3, 4, 3, 3, 2, 2, 2, 2, 3 |
| screen | ATL / 5 (Flip Tight Triple) / 178 | 50 H Screen Strong | 4, 2, 4, 5, 2, 4, 3, 3, 2, 3, 2 |
| cover3 | ATL / 23 (Nickel) / 8 | 3 Weak | 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2 |
| cover2man | ATL / 23 (Nickel) / 25 | 2 Man | 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2 |
| pass_sets | ATL / 12 (I Pro) / 60 | 50 Z Comeback | 4, 2, 2, 3, 2, 2, 4, 3, 3, 2, 2 |
| fire | CIN / 27 (4-3) / 12 | Strong Fire Zone Blitz | 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2 |
| speed_option | MIN / 12 (I Jokers) / 24 | Strong Speed Option | 5, 2, 2, 3, 2, 2, 2, 2, 2, 3, 5 |
| inside_zone | TB / 15 (Weak I Pro) / 70 | Strong Inside Zone | 3, 2, 2, 3, 2, 2, 2, 2, 2, 2, 3 |

The full local export is `.scratch/play_rules_audit.json`: eleven descriptors and
all node bytes, flags, decoded operands, plain English and per-resource receipts for
each sample. It is intentionally excluded from the commit and release. Reproduce it
with the command in [the guide](docs/mod_editor/play_rules.md). The committed
[evidence manifest](docs/mod_editor/play_rules.evidence.json) records every source
hash, sample count, callback location and corpus gap without shipping retail scripts.

## Runtime evidence

Pinned retail XBE SHA-256: `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The 29-entry, 20-byte-per-row table at `0x00521078` contains flags and decode,
encode, draw and validation callback addresses. Its SHA-256 is
`cf59c9ec6e250849eb3c23a9abb7675ae782487bb355e4596626dd5afa1f06cf`.
The offline auditor verified every table field against the structured reference.

Corpus paths below are relative to the read-only Ghidra root
`<home>/2k-football-mod-tools/research/functions/nfl2k5`.
The evidence manifest pins each complete decompiler block by SHA-256.

| Consumer | Corpus location |
| --- | --- |
| `0x0019FA10` | `pseudo_c/shard_007680_008191.c:6441` |
| `0x001A2E70` | `pseudo_c/shard_007680_008191.c:8822` |
| `0x001A5090` | `pseudo_c/shard_007680_008191.c:10349` |
| `0x001A5790` | `pseudo_c/shard_007680_008191.c:10600` |
| `0x001A6220` | `pseudo_c/shard_007680_008191.c:11065` |
| `0x001B85A0` | `pseudo_c/shard_007680_008191.c:24753` |
| `0x001B8BC0` | `pseudo_c/shard_007680_008191.c:25247` |
| `0x001B8C40` | `pseudo_c/shard_007680_008191.c:25308` |
| `0x001B8CA0` | `pseudo_c/shard_007680_008191.c:25339` |
| `0x0023ADA0` | `pseudo_c/shard_009728_010239.c:10232` |
| `0x0023ABB0` | `pseudo_c/shard_009728_010239.c:10141` |
| `0x0023B6E0` | `pseudo_c/shard_009728_010239.c:10840` |
| `0x0023DBE0` | `pseudo_c/shard_009728_010239.c:12489` |
| `0x0023F450` | `pseudo_c/shard_009728_010239.c:13582` |
| `0x002400B0` | `pseudo_c/shard_009728_010239.c:14094` |
| `0x002FAFF0` | `pseudo_c/shard_012800_013311.c:1036` |
| `0x001ACE40` | `pseudo_c/shard_007680_008191.c:15895` |
| `0x001A9840` | `pseudo_c/shard_007680_008191.c:13734` |
| `0x001CEA80` | `pseudo_c/shard_008192_008703.c:14437` |

`FUN_001B85A0` constructs the runtime initializer dispatch at `0x00BE5110`:
0x11 selects `0x002400B0`, 0x12 selects `0x00229AE0`, 0x0D selects
`0x001A6220`, 0x0E selects `0x001A5BC0`, and 0x1A selects `0x001ACE40`.
The reference records all 29 dispatch/table entries, including null callbacks
and unnamed initializer addresses. `FUN_001B8C40`/`001B8CA0` read decoded operands;
`001B8BC0` addresses the current decision cache. `001A9840` supplies the existing
ported play validator. This follows data through dispatch to live consumers,
rather than inferring all semantics from play names or draw functions.

**Blocking data versus code.** `002400B0` reads the eight block-leg operands and
calls `0023F450`. Leg type, time, movement endpoint, turn/end modes and group are
data. Type 3's depth treatment differs from ordinary coordinates; type 9 uses
named-spot indices. `0023ABB0` converts the stored leg into a resolver mode, and
`0023DBE0` updates block phases 12/13/14. `002FAFF0` indexes a mode table at
`0x00AD6660` with a 0x38-byte stride, ranks live opponents using positions,
velocities and actor/blocker state, and stores primary and secondary targets.
The region around `002FBF26..002FC179` can exchange target/score fields with
another blocker. PROVED: selection and coordination happen in code. HYPOTHESIS:
describing any one such swap as a specific football double-team-to-linebacker
handoff. No new dedicated combo-block policy was established in PLAY.

The sampled Inside Zone and Outside Zone lines both use **type 8, group 2**.
Outside Zone's one-yard lateral step differs from Inside Zone's straight
one-yard step. Calling all zone legs type 0 would be incorrect. Power and
Counter use type-0 drive legs and a type-2 pulling guard with different lateral
endpoints. Their other eligible-player condition/lead chains are retained in
the complete audit; copying only the line deliberately leaves those skill
assignments with the target play. Draw uses finite type-1 holds followed by
type-0 legs, alongside the quarterback's drop/handoff and the back's take/run.
Screen uses finite holds, 0x18 releases, type-3 blocking and a type-9 receiver
route; its quarterback read values include zeros. These are observed script
differences, not promises about animation timing or engagement success.

**Pass protection.** `0023B6E0` builds a predicted threat list, counts lateral
imbalance and, when its close-threat gate is met, writes `DAT_00C16BAC`. It clamps
the adjustment to +/-274.32 cm (three yards). Type-1 paths in both `0023ABB0` and
`0023F450` consume that offset. The author can copy exact pass sets and existing
conditions; the threat-count rule and shift calculation are runtime-only.
No call named Slide protection exists in the census. Plays with Slide in route
names are not proof of a protection identity.

**Combo Inside Zone and landmarks.** ATL p28 is a coverage component, linked to
Nickel and Dime. Active slots are 2 and 4 through 10; DT2 drops and MLB rushes.
Slots 4/9 and 6/10 pair zone-to-man with man-to-zone scripts. `001A2E70` reads the
man boundary, friendly partner and transition fields, calls `0019FA10`, signals
`0x00BE4D00[partner]`, and stores the transition in actor state. `0019FA10` tests
predicted receiver position (position plus 0.2 times velocity) against the
boundary bit table at `0x0050A4C8`, including lateral and depth tests.
`001A5090` consumes the partner signal, updates zone steering and transitions.
`001A6220` initializes a zone record at `0x00BE4B60` with actor adjustments from
`+0x428/+0x42C`. The defender's landmark and selectors are PLAY data; receiver
pickup, boundary evaluation and steering are code. PROVED reactive exchange
does not prove a complete modern Palms or quarters-match policy.

Cover 3 preserves its three deep landmarks plus four underneath assignments.
Cover 2 Man preserves five man assignments and the two deep zones. CIN's fire
zone drops DE2 while MLB/OLB rush, retaining the other coverage assignments.
Inactive front slots in these coverage records are intentional; the effective
front/coverage union must cover all eleven players, with active coverage winning
an overlap. The existing menu/native-personnel guards remain authoritative.

**Read findings.** There is no literal Inside Zone Read among 9,251 plays in
37 books. TB Inside Zone and MIN Strong Speed Option were audited separately
and labelled accordingly. The five native speed-option donors remain MIN 24,
NO 57/66, PHI 175 and TEN 144. `001ACE40` implements the existing predicates;
MIN's quarterback position/velocity condition and the back's kind-6 cache
reference retain both terminal paths. The separate Zone read/RPO recipes are
authored experiments with opponent fixtures. Copying an exact native option
does not confer modern EDGE recognition, mesh policy or experimental intent.

**Corpus limits.** Of 138 distinct referenced callback/consumer addresses,
55 have independently emitted Ghidra blocks and 83 do not. Many missing entries
are the small encode/decode or draw callbacks in the retail table, not missing
evidence that a new football policy exists. Their table identities and all
91,833 byte-exact codec round trips are verified; an independent decompilation
of every one of those callbacks is not claimed. The manifest lists every gap.
Unresolved football meanings retain raw parameter labels. No decompiler output
or retail script payload is bundled into the product.

## Implementation decisions and limits

`nfl2k5_play_rules.py` binds bundles to the current body SHA-256 and exact native
position codes. It preserves all bytes the codec can represent and refuses
reserved-bit loss. Friendly references follow the existing pack retarget
contract; receiver selectors and condition node numbers are distinct namespaces.
Source and target dependencies cannot be split. Special teams remain viewable
but are refused by the new wizard apply action. Cross-book automatic application
is deliberately refused; re-extract from the selected book.

The inspector walks descriptor-declared spans, including second terminal paths.
The library's exact-chain helper and defense/pack helpers preserve explicit node
flags. `rule_play_request` validates and reuses identical donor assignments;
`compile_application` requests a checked no-op only for round-trip verification.
Ordinary compiler no-op behavior stays intact. The writer still owns allocation,
descriptor reconstruction, fixed-span writes, menu checks, reparse and receipts.
Copied defense exports use schema v3 and track the union of replaced slots across
multiple applications, retaining Spy intent only on untouched target slots; copying retail rules creates no new Spy or option intent.

Budgets remain 50 formations, 270 plays, 26 categories, 36 menu links, 3,500
nodes, 15 nodes per chain, and the existing bounded name pool. Eight team books
are already at 270 plays: ARZ, BUF, CIN, HOU, JAX, NYJ, OAK and SD. Reusing an
unchanged chain costs zero new nodes; replacing a different chain still needs
pool space. Full source/resource identity requires no name/header/menu/geometry
change; copying onto a different record can only promise exact selected chains
and valid compiler receipts, not an identical entire resource.

The Info topics incorporate the beta-61 defense, option and screen reports,
deep-zone runtime findings, the beta-62 dedicated spy backend and its 31-record
lookup limit, utility-book drill preservation, and the normal project/pack/build
path. Older report statements that the codec is unknown or the true-spy backend
is not yet built are identified as historical. The separate runtime options
must still be paired by their existing Build integration.

No XBE patch owner, memory allocation, dispatcher change, archive growth or disc
build was needed. Protected files and unrelated GUI panels were not edited.
The user-approved bundle fallback is used if branch metadata is read-only.

## Validation

Commands ran from this worktree with plain standalone unittest entry points;
no `PYTHONPATH` override, pytest, emulator or display was required. All commands
in the table exited 0. Qt ran offscreen.

| Exact command | Result |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_play_author.py` | 13 tests, 1.204 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_formation_play_writer.py` | 8 tests, 0.614 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_defense_play.py` | 12 tests, 124.514 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_read_option.py` | 15 tests, 9.973 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_playbook_pack.py` | 37 tests, 1.259 s; OK, one class skipped |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_playbook_inspector.py` | 6 tests, 0.002 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_defense_play_qt.py` | 4 tests, 3.263 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_read_option_qt.py` | 7 tests, 1.115 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_create_play_wizard_qt.py` | 0 tests, 0.050 s; OK, one class skipped |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_play_designer_qt.py` | 4 tests, 0.327 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_playbook_pack_ui.py` | 13 tests, 0.600 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_play_rules.py` | 12 tests, 3.061 s; OK |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_play_rules_qt.py` | 6 tests, 3.002 s; OK |

The pack facade class and the existing Create a Play real-facade class skip
because the private uniform catalog report is absent. The retail XISO and cache
directory exist. The new Rules Qt tests use extracted resources and do run the
actual project archive save/reopen and pack compiler paths without that facade
catalog. A fully integrated real-facade/packaged Studio run remains for wiring.

The 18 new tests cover all 29 reference schemas and links, all twelve exact
whole-resource applications, independent node encoding, paired-exchange refusal,
remapping without changing opponent selectors, changed-play compilation, node
overflow, stale sources (including delayed compilation), reserved-byte loss,
every resolved preset across 37 books, complete alternate terminals, read-only
Info search and local link traversal, GUI application/reset, preserved zero
reads, repeated partial copies without reviving overwritten Spy intent, v3 pack
serialization and project save/reopen/recompile equality.

Full refreshed offline research command:

```sh
python3 tools/nfl2k5_play_rules_research.py --image '<media>/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)' --xbe '<media>/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' --corpus <home>/2k-football-mod-tools/research/functions/nfl2k5 > .scratch/play_rules_audit.json
```

Result: exit 0; 37 books; 9,251 validated plays and synchronization checks;
91,833 exact node round trips; 12 identical complete resources; all 29 XBE table
entries pinned; 55 corpus blocks found and 83 explicitly listed gaps. Refreshed
audit counts, hashes and corpus pins match the committed evidence manifest.

CLI smoke: `python3 -m mod_editor.core.nfl2k5_play_rules inspect --image
'<media>/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)' --book ATL
--play 28 --formation 23` exited 0; its parsed JSON contains all 11 assignments
and 26 nodes. Output remains local in `.scratch/combo_rules.json`.

Capability handoff: merged registry passes `validate_data(..., check_files=False)`;
all new evidence paths and both dotted-module commands pass the repository path
checks. Full inherited `check_files=True` stops on the pre-existing missing
`docs/research/apf_audio.md`. No registry/protected packaging file was changed.
`git diff --cached --check` passed. Scratch evidence was under 1 MiB before the
final CLI smoke outputs; no disposable disc or archive copy was created.

Changes are staged and committed on `astra/r62-play-rules-editor` with the 18
explicit paths listed by the commit. The normal Git operation is available;
no bundle fallback is needed. `ASTRA_BRIEF.md` and `.scratch/` are excluded.

## Noah's witness list

1. In the integrated Studio, open Info before loading a game and search for
   opcodes, 31 records and capacity; follow local report links.
2. Copy ATL Combo Inside Zone into a compatible Nickel coverage, save/reopen,
   build a disc copy and confirm the call/art. Against inside/outside releases,
   crossing routes and motion, capture both paired defenders before and after
   an exchange. Compare with the untouched retail call using the same front.
3. Compare copied Inside/Outside Zone, Power and Counter line rules against even
   and odd fronts. Record each guard pull, initial step, primary/secondary target
   and any observed double-team release; test both orientations.
4. Compare copied pass sets against left/right overloads and blitzes, recording
   protection movement and QB pressure. Copied data does not prove slide success.
5. Run Draw and Screen; capture hold/release, receiver readiness, target choice,
   throw/catch timing and pressure. Compare zero-valued retail reads unchanged.
6. Exercise Cover 3, Cover 2 Man and the fire-zone drop with multiple formations
   and motions; check all eleven defenders and CPU call selection, including
   practice utility books without losing drill records.
7. Run both native speed-option branches, CPU and human control, with the pitch
   partner present. Keep modern Zone read/RPO and dedicated Spy witnesses with
   their own documented runtime option/fixture requirements.

Until those captures exist, all gameplay outcomes remain UNWITNESSED. No
emulator, display, audio or network was used, and nothing was pushed.

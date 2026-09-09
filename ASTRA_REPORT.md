# PS3 APFe import delivery — 2026-09-09

The importer, paired staging adapter, offscreen mapping dialog, read-only
roster probe and full-package texture census are implemented. Code, tests,
user documentation and the protected-file handoff are committed in
`3de8ee01` on `astra/apf-ps3-texture-import`. Nothing has been pushed.

**PROVED offline:** source parsing, semantic layer mapping, destination hash
identity, reversible session staging, one supplied crest's allocation-fit
rebuild/reparse, and the existing crest/cache/Field Art writer regressions.
**UNWITNESSED:** Windows packaged execution, a complete 46-pair build, Xenia
appearance, palette/cache consumption, and PS3-roster acceptance on Xbox.
The protected GUI, build, registry and packaging files remain unchanged.
[WIRING.md](WIRING.md) contains the concrete integration edits; its earlier
handoffs are preserved beneath the new PS3 section.

## Importer and the hash-match answer

[User guide](docs/mod_editor/ps3_bundle_import.md) documents export layout,
CLI/API usage, batch choices and decoder boundaries. The importer accepts a
ZIP, enclosing directory or individual team folder without extracting ZIPs.
DDS takes precedence; GTF is used only when DDS is absent. Numeric subfile
order never supplies the l0/l1 meaning. Aliases preserve the historical NFL
identity and original spelling. Missing/identical pairs are listed as rejected;
unsafe paths, malformed metadata, duplicate aliases, wrong dimensions and
ambiguous mappings fail closed. Individual inputs and aggregate decoded RGBA
have explicit bounds.

**Yes: every one of the 120 supplied manifest rows matches an Xbox outer
entry hash and exactly one semantic TXTR name.** There are 59 unique hashes.
For example, PS3 export entry 753 / hash `0x7ba6e2b0` resolves to Xbox entry
756, whose inner 0 is `logo_l1` and inner 1 is `logo_l0`. PS3 entry numbers and
offsets are not portable. A matching hash identifies a library slot; the NFL
folder name does not prove which Xbox team owns that slot.

The supplied ZIP has 378 files, with 28 team folders and two stripe-update
folders, rather than 30 NFL teams. Its usable paired inventory is:

| Result | Count |
| --- | ---: |
| Valid logo pairs | 27 |
| Valid endzone pairs | 28 |
| Total valid pairs / textures | 55 / 110 |
| Rejected groups / affected layers | 5 / 6 |
| Live Xbox crest slots | 118 |
| Live complete endzone pairs | 117 |
| Writer-supported endzone pairs | 78 |
| Prepared hash-matched pairs / textures | 46 / 92 |

The 27 logo pairs cover 26 teams because Detroit has two variants. Cincinnati's
endzone layers are identical. Denver's and San Francisco's logo siblings have
different source hashes and therefore form four incomplete groups. Dallas
has both `EndZone` and `EndZone/Orginal`; the prepared plan explicitly chooses
`EndZone`. It contains 27 crests and 19 endzones. Eight otherwise valid imported
endzone pairs map to unsupported format-59 destinations: Chicago, Cleveland,
Green Bay, Houston, Indianapolis, Los Angeles Raiders, New York Giants and
New York Jets. They remain reviewable candidates for explicit reassignment to
a supported slot. No unsupported writer is added.

Receipts: [inventory](reports/ps3_import/bundle_inventory.json),
[all manifest identities](reports/ps3_import/manifest_hash_proof.json),
[live mappings](reports/ps3_import/hash_mapping.json), and
[46-pair plan](reports/ps3_import/available_staging_plan.json).
The plan is a review artifact; it does not claim that all pairs were built.

`stage_plan` binds the reviewed plan to fresh live destinations, verifies
pixel hashes, reparses temporary PNGs, preserves both crest layers, and uses
the existing session replacement methods. A failed batch undoes successful
prior operations. Repeated application replaces the same logical edits.
Existing shared full-shell projects are refused. The ready-to-wire button
pins the source session across review and staging and refreshes the existing
facade staging mirrors.

The supplied Atlanta crest was rebuilt through `apf_logo_patch.build_patch_rgba`
at Xbox entry 756. It fit the **67,584-byte** allocation, reparsed both layers,
regenerated both mip chains and preserved the retail input. l0's existing
ARGB4444 encoder had maximum channel error 8; l1 decoded exactly. The separate
retail-gated importer test stages a synthetic distinct pair through the real
session and writer, repeats staging to prove idempotence, and reparses the
rebuilt resource. [Actual Atlanta receipt](reports/ps3_import/atlanta_crest_writer.json).

The existing crest and linked-cache writers retain the no-overlap H7A rule.
Field Art retains its existing stale-mip limitation and fixed-allocation
checks. No raw PS3 TXTR writer or new helmet/uniform/number/banner writer was
created.

## Full 1993-package texture census

All **1,541 PS3 entries** were visited (Xbox: 1,543), with **3,626 TXTRs**
indexed and **zero entry errors**. Final base-level results are **2,303
different, 1,186 equal and 137 uncompared**. The 69 non-IFF entries are
classified separately. The remaining gaps are explicit unsupported PS3
shapes, Xbox linear DXN/DXT5A layouts, or a missing counterpart; they are not
counted as equal. Errors can overlap on the same texture.

| Heuristic kind | Different | Equal | Uncompared |
| --- | ---: | ---: | ---: |
| banners | 79 | 13 | 0 |
| endzones | 162 | 25 | 48 |
| field | 11 | 1 | 0 |
| helmets | 38 | 12 | 3 |
| logos | 189 | 207 | 62 |
| numbers | 296 | 185 | 0 |
| other | 1303 | 602 | 24 |
| presentation | 38 | 2 | 0 |
| uniforms | 187 | 139 | 0 |

[Complete per-texture receipt](reports/ps3_import/texture_comparison.json).
Filter `textures` by `status == "different_pixels"` for the complete observed
difference list; `uncompared` rows retain their specific refusal reasons.

The source nested ZIP is STORED in the outer ZIP; its four volume members are
DEFLATED. Actual volume sizes are 1,073,741,824 bytes for each of 0A/0B/0C and
794,974,208 bytes for 0D: **4,016,199,680 bytes total**. No volume extraction was
performed. TXTR-containing packages include **1,899 compressed blocks and
128 uncompressed blocks**, so PS3 TXTR storage is not universally uncompressed.
The supplied APFe GTFs begin pixels at their declared offset, normally `0x30`,
rather than a fixed `0x80` header.

The initial full census was completed before the inline pixel-pointer support
landed. A forward-only completion pass revisited all 348 affected texture
rows using the final decoder, comparing dimensions and the previously recorded
Xbox decoded-RGBA SHA-256. The receipt marks rows whose differing-pixel count
was not recomputed. The 715,296,768-byte outer entry 577 was classified by its
non-IFF signature without allocating it. A fresh invocation of the delivered
CLI handles both cases directly. The initial interrupted journal and completed
intermediate journal are not delivered.

These are **cross-platform base-pixel differences**, not a proved set of edits
by the modder. There is no base PS3 disc; platform artwork, format conventions
and codec rounding can also differ. Mips and runtime consumption are not part
of the comparison. Names supply heuristic kinds; each receipt row retains its
outer hash, inner hash/name, destination identity, decoded hashes/dimensions,
and an existing writer owner where established. Other rows are candidates for
the corresponding existing workspace owner to inspect.

## Roster evidence and converter decision

The PS3 roster USERDATA and both Xbox fixtures are **2,715,908 bytes**. All 40
root counts match. Player records begin at `0x150` with stride 332; team records
have stride 384. Appearance graphs and player-membership graphs parse on both
platforms, with 1,680 PS3 memberships versus 1,386 in the Xbox fixture.
The 69 × 12-byte playbook-label table at `0x1D31DC` and its referenced label
names are byte-identical. The user-book region from `0x26D030` has matching
extent and five USER marker offsets but a different content hash.

The payload differs from `Roster.ROS` in **430,995 bytes**, and from
`Roster2.ROS` in **430,996 bytes**. Existing player-text parsing refuses the
PS3 data at `mod_editor/apf_studio/save_roster_players.py:586`: player 0's
nickname pointer field `0x268` resolves to odd address `0x207A9B`.
**1,344 nickname pointers** have this alignment issue. Root fields 15–18 also
contain differing serialized runtime addresses rather than file pointers.
The shared size/layout is not sufficient proof for a container rename.

Decision: ship a bounded, read-only probe and converter design, **no converter
writer**. The guide identifies the remaining work: establish PS3 string
grammar/ownership, relocate complete reference sets into valid allocations,
preserve all player/team and user-book state, independently verify the result,
then hand off Xbox container handling and an actual game-load witness.
The franchise USERDATA and editor-only season/stat exports are not substituted
for roster data. No existing parser was loosened.

Receipts: [Roster.ROS comparison](reports/ps3_import/roster_comparison.json)
and [Roster2.ROS comparison](reports/ps3_import/roster2_comparison.json).

Reproduce the read-only comparisons with new output paths:

```bash
python3 -m mod_editor.apf_studio.ps3_roster_probe \
  "/home/noah/Downloads/1993 NFL Season (Update Logos).zip" \
  "/home/noah/Downloads/apfe/Roster.ROS" \
  --ps3-member "1993 NFL Season (Update Logos)/BLUS30049-ROS/USERDATA" \
  --receipt roster-repeat.json
python3 -u -m mod_editor.apf_studio.ps3_texture_probe \
  "/home/noah/Downloads/1993 NFL Season (Update Logos).zip" \
  "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A" \
  --receipt textures-repeat.json
```

## Validation and remaining integration

Across the 12 selected standalone suites, final results cover **152 tests:
150 passed, 2 intentional opt-in skips**. This is the relevant importer and
writer regression selection, not a claim that the entire repository suite ran.

| Standalone file under `tests/mod_editor/` unless noted | Final result |
| --- | --- |
| `test_apf_ps3_texture_bundle.py` | 28 passed, including retail stage/rebuild |
| `test_apf_ps3_probes.py` | 9 passed, including 72 randomized Xenos parity cases |
| `test_apf_ps3_texture_bundle_qt.py` | 3 passed offscreen |
| `test_apf_helmet_crest_design_product.py` | 13 passed |
| `test_apf_team_crest_selection.py` | 9 passed |
| `test_apf_all_crest_slots.py` | 15 passed against retail |
| `test_apf_logo_patch.py` | 18 passed against retail |
| `test_apf_logocache_patch.py` | 14 passed against retail |
| `test_apf_field_art.py` | 6 passed |
| `test_apf_field_art_patch.py` | 24 passed, 2 slow practice-overlay opt-in skips |
| `tests/apf_h7a_no_overlap_test.py` | 3 synthetic tests plus retail discipline test passed |
| `test_apf_save_roster_players.py` | 7 passed |

Every command and its unittest output is retained in
[initial regressions](reports/ps3_import/test_results.txt),
[final importer](reports/ps3_import/test_results_importer_final.txt),
[final probes](reports/ps3_import/test_results_probes_final.txt),
[final Qt](reports/ps3_import/test_results_qt_final.txt) and
[retail regressions](reports/ps3_import/test_results_retail_regression.txt).
The standard invocation is:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_ps3_texture_bundle.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_ps3_probes.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py -v
```

Existing tests with checkout-relative retail paths initially skipped. They
were then run unchanged from a `tempfile.TemporaryDirectory` mirror containing
only copied test scripts and symlinks to this worktree's tools and the supplied
read-only retail directory; the mirror was removed. The final H7A rerun selects
`RetailDisciplineTests` only. The two remaining skips require
`APF_FIELD_ART_SLOW=1` and concern unchanged practice-overlay writers.

The first importer run exposed a synthetic-fixture issue: installed Pillow
10.2.0 silently ignored the requested DDS save `pixel_format`. The fixtures
now assert actual DXT headers and supply known synthetic BC blocks when
necessary. The failing output is preserved, and all 28 final tests pass.

The temporary clean product stage imported all six new modules, parsed a
synthetic DDS ZIP, verified its paired plan, and constructed the mapping dialog
offscreen: **PS3_IMPORT_CLEAN_CLOSURE_PASS**. The unchanged full runtime gate
refused the new files at `packaging/check_apf2k8_mod_studio_release.py:870` because
the protected internal allowlist lacks `ps3_roster_probe.py` (the first missing
path). This is an integration gate, not a missing dependency. The new capability
row independently validates against the registry's capability schema.
[Closure output](reports/ps3_import/runtime_closure.txt).

The integration owner must apply the exact Team Logo/Field Art buttons,
dirty/revert/project-refresh connections, action binding, registry row and
allowlist/runtime lines in WIRING.md, then run the normal packaged gates.
The complete-project Build already carries paired crest/cache inputs and
grouped field layers. Windows and game results remain UNWITNESSED.

Only source, synthetic tests, documentation and metadata receipts are committed.
No source archive, roster, retail payload, decoded texture or generated game
patch is included. Retail inputs were read-only; temporary assets were deleted.
Observed free space stayed above 100 GB (about 114 GB near completion).
No emulator, displayed GUI, audio, game-data fetch or push was used.
[Final validation and artifact hashes](reports/ps3_import/validation_summary.json)
record the implementation commit, source hashes, receipt hashes and coverage.

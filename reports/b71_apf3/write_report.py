"""Render the APF-3 report from the recorded commands and suite results."""
import json
from pathlib import Path
import shlex
import subprocess

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).parent
records = sorted((json.loads(line) for line in (folder / 'commands.jsonl').read_text().splitlines()), key=lambda r: r['started_utc'])
summary = json.loads((folder / 'suite_results.json').read_text())
head = subprocess.check_output(['git', '--git-dir=.scratch/git', '--work-tree=.', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
report = '''# Beta 71 APF-3 report

## Delivery status

**Partial implementation. Independent per-situation exclusions remain unimplemented.** Native evidence rules out the proposed existing SPLB fields as independent situation lists. The export reproduction fits with APF-2's compressor, and a later zero-TE producer is now proved through the final eleven-player builder under explicit synthetic roster conditions.

| Requested item | Result | Evidence boundary |
| --- | --- | --- |
| 1. Independent situation exclusion and page control | **UNFINISHED** | 4,832 native weight comparisons, 138 category/formation component queries and 46 shared-exclusion buffers on BASE/TU prove why the existing data-only edits do not provide this contract. No independent control or runtime patch is shipped. |
| 2. Straight for three Queens in O-ManBlock | **PROVED for the named edit and an overflowing 84-play variant** | Exact decoded bytes, unchanged allocation/descriptors/footer, no overlapping H7A matches. The screenshot's precise 2,417-byte payload remains unreconstructed because its selected play IDs are unknown. |
| 3. Third-and-8 after the APF-2 trace boundary | **PROVED, conditional on roster inputs** | Native current-call stores, depth/provider fallback and eleven assignments execute on both images. An empty TE depth list selects an FB-depth player despite a one-TE tuple. Actual match attribution remains UNWITNESSED. |
| 4. Hydration, suites, registry, alpha.92 | **PASS** | Strict validator; 183/183 standalone suite files; 1,763 reported tests with 12 optional skips; repin; provider/catalog/phase1; staged APF release/runtime. |
| 5. Private delivery | **COMMITTED AND BUNDLED** | Explicit paths only, private git directory, verified bundle, no push. Final commit IDs and bundle hash are in the private delivery receipt. |

Base: `astra/b71-apf2-situations` at `7d95493750156f77e0533a16378330f4d80e7caa`.
Branch: `astra/b71-apf3-situation-exclusions`.
Implementation commit: `IMPLEMENTATION_HEAD`.
Private git directory: `.scratch/git`; shared worktree Git metadata was not changed.
Bundle: `.scratch/astra-b71-apf3.bundle`.
Final delivery command receipt: `.scratch/astra-b71-apf3-delivery.json`.

The supplied `ASTRA_CONTEXT.md`, APF sections of `BETA71_TRIAGE.md`, APF-2 `ASTRA_REPORT.md` and `WIRING.md` were read. The screenshot `u5.png` was inspected in the read-only hub. APF-2 history remains in the base commit. No emulator, disc build, desktop/audio access or push was performed. This report and new public text use no tester names.

## 1. Per-situation exclusions: exact wall and remaining design

SPLB record `0x70 + n*0xB0` has word A at `+0xA8` and membership word B at `+0xAC`. Native `84869058` evaluates rating curves, `8486AEB0` weights MASTER categories and `848693F8` selects category members. Their proved equivalents are `mod_editor/core/apf2k8_playcall_model.py:197`, `:234` and `:258`.

- **PROVED:** All eight encoded ratings across all 23 query proxies, plus all 512 triples in both interpolation arms, produce positive rating weights in the ordinary neutral-urgency test. The 4,832 native/model comparisons have minimum `0.10000000149011612`. There is no zero rating code. Separate family/run-share gates are not independent per-formation situation storage.
- **PROVED:** Moving singleton formation 14 among categories 3/6/7 leaves it eligible in every ordinary query on BASE/TU. The full call tuples are recorded, including the real fourth-down/two-point kick branches. Those special branches are not forced into scrimmage by a stub.
- **PROVED:** Clearing only formation 14's membership word removes it from all 23 category-6 candidate buffers on both images while formations 2/24 remain. This is a shared book exclusion.
- **PROVED:** Some query labels supply identical native inputs, including Openers / 1st and 10 / Sudden change. Existing fields cannot distinguish those labels under identical state.

Code/evidence: `tests/mod_editor/test_apf_playcall_research_native.py:534` and `:567`; `reports/b71_apf3/native_receipt.json`; `docs/research/apf_b71_apf3.md:15`.

**HYPOTHESIS / required further implementation:** an independent control needs a new persistent per-book mask, a defined live situation key, hooks that filter both category and formation selection, and explicit handling when exclusions empty a draw. The 23 overlapping proxies need real event/clock matching and precedence. The existing native format does not provide that storage or key. No hook/cave/storage ABI for this extension is proved here, so there is no claimed native tuple showing an independent local exclusion. The CPU page continues to describe removal as book-wide.

## 2. O-ManBlock export

The named reproduction adds Gun: Straight, formation 133/category 7, with the 25 existing O-Shotgun play IDs, then removes Queens formations 2, 14 and 24. It uses the production membership/trailer compiler, removals and repacker. APF-2 commit `290e51c2` already supplies the necessary refit; this job adds the missing exact regression, not another packer implementation.

| Stage | Old token-preserving IFF bytes | Final IFF bytes | Allocation |
| --- | ---: | ---: | ---: |
| Add 133 | 1,639 | 1,639 | 2,048 |
| Remove 2 | 2,027 | 2,027 | 2,048 |
| Remove 14 | 2,054 | 1,526 | 2,048 |
| Remove 24 | 2,019 | 2,019 | 2,048 |

Final decoded body SHA-256: `8feb01162777475a7c537ef12375b942615ea0e56e8eb1802d9a3e8fca407742`.
Final complete 2,048-byte allocation SHA-256: `5b8d650fbb16d5448d4bad0062977373932ff7aa6027ffc7bdd50dffe7c19efc`.

An authored 84-play variant (IDs 0–83) makes the final old stream 2,275 bytes. The existing portable refit produces 1,634 bytes, with complete allocation SHA-256 `4724fbec1c6c5b11489ec0519b7d712e2ccf2294294e25ecae4518273cfbf004`. The optional native compressor is disabled in the regression. Every decoded byte, retained record's entries/trailer, file descriptor, footer and zero tail is checked; retail archives remain unchanged. No records are dropped to save space, and no container allocation is grown.

Code/evidence: `tools/apf_b71_situation_probe.py:14`; `tests/mod_editor/test_apf_b71_situations.py:130`; `reports/b71_apf3/export.json`; `reports/b71_apf3/exact-export-regression.log`.

**UNWITNESSED / unresolved exact historical input:** the screenshot reports 2,417 bytes but omits its selected play list/project recipe. That exact payload is not reconstructed. The named operation and a forced-overflow variant are proved; a claim of identical historical compressed bytes would be false. These are offline transport/readback proofs, not gameplay or a native container-resize proof.

## 3. Zero-TE producer beyond 8486D0CC

`tools/apf_b71_situation_probe.py:49` executes the final lineup; `tests/mod_editor/test_apf_playcall_research_native.py:622` and `:657` drive it from the native selected call. Native CE88 writes directly to current-call `TEAM+4`, continues through its return and performs the stores after D0CC at `TEAM+0x70`, `+0x68`, `+0x6C`. The next native phase consumes those unchanged bytes.

| Native step | BASE | TU 1.1 |
| --- | --- | --- |
| Current-call lineup phase | 84859820 | 8485A4C0 |
| Category/formation wrapper | 848608B8 | 84861558 |
| Eleven-player builder | 84860020 | 84860CC0 |
| Substitution/depth request | 847B2DA0 | 847B3878 |
| Player provider/alternative positions | 847B29E8 | 847B34C0 |
| Final slot assignment | 8485E768 | 8485F408 |

Sixteen cases cover both images and TE depth present/absent: twelve Straight-133 cases at RNG fractions .25/.5/.75 and four original APF-2 reassignment cases. At .5 the tuples are `(7,133,122)` and `(7,14,114)`. Each has one requested TE. With a TE present, slot 6 receives depth `(3,0)`. With an empty TE list, native provider attempts `(slot=6, role=8, attempt=0, position=3)` and then `(6,8,1,2)` and selects FB depth `(2,0)`. The final eleven unique player pointers contain zero TE-depth players. Native role/depth tables `820B3D30` / `820B3D40` independently identify positions 3/2 as TE/FB.

Both requested role bytes `+0x34` and primary-package bytes `+0x35` still count one TE. The selected player pointer is `+0x44`. This is a concrete later producer of a zero-TE-depth lineup following a one-TE call tuple. Each phase executes approximately 74,000–76,000 native instructions. The receipt records every slot, role, provider attempt, selected depth, tuple and executed entry point.

**Boundaries:** The depth charts and healthy player objects are synthetic (32 players with TE, 31 without). Only equipment refresh leaves `847C1728`/`847C16D0` and TU equivalents `847C2348`/`847C22F0` are bounded out. Category, formation, substitutions, eligibility, player provider and assignment loops all run natively. RNG and kicker range are explicit existing harness inputs. Two native phase calls are bridged; the whole match scheduler is not run. The explicit-output arm omits play notification `8488DAB0`. Execution stops at `84859958`/`8485A5F8` after the offensive builder and before the other team. Real USER/save overlays, real roster availability, fatigue/injury state, later match phases and displayed players remain **UNWITNESSED**. Attributing the observed match to this fallback is **HYPOTHESIS**.

UI correction: `mod_editor/apf_studio/playcalling_editor_qt.py:179` labels the column “Requested TEs”; `:583` explains the depth-list fallback. The existing Qt suite passes all 13 tests.

## 4. Hydration, integration and gates

The initial strict validator failed: 75 registered private evidence paths were absent despite the supplied hydration expectation. They were copied as ordinary independent files from narrowly scoped read-only access to the original evidence copies. `reports/b71_apf3/hydration.json` records source paths, sizes and hashes. Source checkout files were not changed. The private copies are excluded from commits and release. Reviewed extractor tooling was restored with the APF-2 hydration helper and its exact pins. The H7A helper remains mode 0755. Dependencies came from already-installed local copies; no network install occurred.

`mod_editor/capabilities/registry.v1.json:2640`, `:2814`, `:3017`, `:3556` and `:3624` integrate APF-2's five pending rows and the APF-3 evidence. Full replacements are in `docs/research/apf_b71_apf3_registry.json`. There are zero new rows: counts remain 174 total / 72 APF. Runtime status remains not-tested for actual gameplay. Alpha.92 notes are in `docs/mod_editor/apf2k8_mod_studio_changelog.md:8`; the walkthrough links the new research.

Applying the rows exposed an APF-2 wiring omission: the APF runtime checker still required hidden legacy scheme cards to be Editable. The protected checker change at `packaging/check_apf2k8_mod_studio_runtime.py:1419` removes exactly those two cards from the exact editable set and explicitly requires both to be Evidence. All other exact boundary and complete-editor checks remain. The user's registry/runtime integration request authorized this necessary matching update; `WIRING.md` explains it. No installer test or 2K5 checker was changed. `packaging/apf2k8-release-allowlist.txt:294` includes the new research doc.

Final results:

- **183/183 suite files pass**, comprising all 178 `test_apf*.py` files plus B69 A1 play-calling, provider integrity, product catalog, phase1 packaging and registry module commands.
- **1,763 reported tests, 12 optional skips**, matching APF-2's optional-skip count. `suite_results.json` lists every latest file result and skip. The native APF-3 suite passes **30/30, no skips**. Export suite 10/10; Qt 13/13; installer 16/16.
- Strict validator: `MOD_CAPABILITY_REGISTRY_VALIDATION_PASS`, 174 capabilities.
- Repin: exit 0, zero pin updates. It is run again immediately before each commit.
- Staged release: **281 files, 10,321,100 bytes**, no private/retail/symlink/undeclared files.
- Staged runtime: **156 modules, 72 APF capabilities**, exit 0. Retail-source-dependent probes report their explicit unavailable state in this packaged-source-free check.

Failures are retained, not erased: the first strict validator lacked hydration; two initial native runs incorrectly expected ordinary tuples for the actual fourth-down/two-point kick branches and were corrected to preserve those native branches; the first installer run inherited a source PYTHONPATH that shadowed staged namespace imports; rerunning without it exposed the real registry/checker mismatch described above. The corrected installer and final native runs pass. The batch coordinator's exit 1 records those first failures; the final aggregation uses each suite's latest complete run. No required gate remains failing.

## 5. Retest steps and remaining acceptance

1. Run the strict validator and repin. Recreate the private test interpreter if necessary with `python3 reports/b71_apf3/prepare_test_python.py`; then put `.scratch/test-python/bin` first on PATH and set `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen`. The local setup requires the already-installed pinned Capstone dependency; it does not download anything.
2. Run `python3 tests/mod_editor/test_apf_playcall_research_native.py`, `python3 tests/mod_editor/test_apf_b71_situations.py` and `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py`. Supply the owned inputs using `APF_RETAIL_INDEX`, `APF_RETAIL_XEX`, `APF_RETAIL_TU` when defaults differ. Missing native inputs are optional skips, not proof; the delivery ran both pinned images.
3. For O-ManBlock, add Gun: Straight/category 7 with the 25 donor play IDs from O-Shotgun, then remove I Spread/Strong I Spread/Weak I Spread (2/14/24). Export a copied book, re-open it and check the retained plays and formations. The regression's exact body/allocation hashes above identify the tested recipe. A different selected play list needs its own measured export.
4. For the lineup witness, compare third-and-8 at midfield with a TE-depth entry and with that depth list empty; record the source/book identity, BASE/TU image, save/USER state, available depth chart and actual eleven players. A requested TE count is not evidence of a TE player. The native result is conditional, and actual gameplay remains to be witnessed.
5. Do not retest book-wide removal as an independent situation feature. Item 1 requires the new native filter/storage/matching implementation described above before a meaningful local-exclusion witness exists.
6. To rerun the full set, use `python3 reports/b71_apf3/suites.py --workers 4` in a clean evidence directory (the runner reuses same-label completed records). Run the installer with `env -u PYTHONPATH` so its staged imports resolve correctly. `APF_BOOK_RETAIL_INDEX` enables the owned-book optional probe. Exact stage/release/runtime commands and every suite command are in the ledger below.

## Command ledger

Every acceptance/test command below records UTC start, elapsed seconds, exit code and its complete output log. Commands are shell-rendered from their exact argv; `commands.jsonl` is the authoritative machine-readable form. Read-only inspection and exploratory interactive disassembly were not acceptance commands and are not represented as tests. No exploratory retail memory dump is stored in the delivery. Final report commit/bundle/audit commands are separately recorded in `.scratch/astra-b71-apf3-delivery.json` to avoid a self-referential commit ID.

'''.replace('IMPLEMENTATION_HEAD', head)
report += '| UTC start | Seconds | Exit | Command | Complete output |\n| --- | ---: | ---: | --- | --- |\n'
for r in records:
    command = shlex.join(r['command']).replace('|', '&#124;')
    report += f"| {r['started_utc']} | {r['elapsed_seconds']:.3f} | {r['exit_code']} | `{command}` | [{Path(r['log']).name}]({r['log']}) |\n"
report += '\n## Optional skips by file\n\n| File | Skips | Evidence |\n| --- | ---: | --- |\n'
for r in summary['suites']:
    if r['skipped']:
        report += f"| `{r['suite']}` | {r['skipped']} | [{Path(r['log']).name}]({r['log']}) |\n"
report += '\nASTRA_DONE\n'
(root / 'ASTRA_REPORT.md').write_bytes(report.encode())
(root / 'ASTRA_LAST_MESSAGE.md').write_bytes('''APF-3 is a partial delivery. Independent per-situation exclusions remain unimplemented; bounded BASE/TU evidence shows the proposed existing fields cannot provide them.

The Straight-for-Queens export fits with APF-2's refit and has exact byte regressions. Native traces now reach all eleven player assignments and prove TE-to-FB depth fallback when the TE list is empty. Actual gameplay remains UNWITNESSED.

All 183 requested suite files pass: 1,763 reported tests, 12 optional skips. Native play-calling: 30/30 with no skips. Strict registry, repin, provider/catalog/phase1, installer and staged release/runtime pass.

See ASTRA_REPORT.md, WIRING.md and .scratch/astra-b71-apf3-delivery.json. Commits use private .scratch/git; bundle: .scratch/astra-b71-apf3.bundle. No push.

ASTRA_DONE
'''.encode())
print('Wrote ASTRA_REPORT.md and ASTRA_LAST_MESSAGE.md')

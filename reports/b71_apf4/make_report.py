"""Write the delivery report only after every complete acceptance suite passes."""
from pathlib import Path
import json,shlex
root=Path(__file__).resolve().parents[2];folder=Path(__file__).parent
results=json.loads((folder/'suite_results.json').read_text())
assert not results['failures'], results['failures']
assert next(r for r in results['results'] if r['suite'].endswith('test_apf_b71_situation_mask_native.py'))['tests'] == 36
records=[json.loads(s) for s in (folder/'commands.jsonl').read_text().splitlines()]
native=json.loads((folder/'native-byte-receipt.json').read_text())
text=f'''# Beta 71 APF-4 report

## Delivery

Implemented the independent mask and the requested-row editing surface. **{results['passed']}/{results['suite_files']} complete standalone suite files pass**, with **{results['tests']} reported tests and {results['optional_skips']} optional skips**. The final expanded native file passes all 36 tests, including the inherited **30/30** through the real mask detours. Gameplay remains **UNWITNESSED**.

Base: `astra/b71-apf3-situation-exclusions`, `dc87cd0f`. Branch: `astra/b71-apf4-situation-mask`. First implementation commit: `13eab964`. Commits use explicit paths in `.scratch/git`; the shared git directory is unchanged. Final commit IDs and bundle integrity are recorded separately in `.scratch/astra-b71-apf4-delivery.json`. Bundle: `.scratch/astra-b71-apf4.bundle`. No push, emulator, desktop display, audio or disc build was performed. Qt ran offscreen; launcher tests used fake folders and never executed Xenia.

The supplied context, both APF triage sections and later witness, APF-2 report at `7d954937`, APF-3 report and research were read. The in-game witness already established that reassigned personnel hold rather than reverting. The recorded observation that Situations and Requested Rows “are the hidden goldmine” supports exposing the actual data boundaries, including computed requests and editable shared personnel rows. No tester is named in new public material.

## Design and addresses

The patch defines twelve live keys: actual down 1 through 4 crossed with absolute single-precision longitudinal target-minus-ball distance <= `f32(182.88)`, <= `f32(640.08)`, or greater. These are the native two- and seven-yard thresholds. The older 23 labels remain representative preview queries; identical inputs such as Openers / first-and-10 / sudden change are not falsely separated. There is no new claim about event-label semantics.

| Item | BASE | TU 1.1 |
| --- | --- | --- |
| Live game state G | `851A2780` | `851A27B0` |
| Down; ball/target coordinates | `[G+6C]+4`; `+18`, `+28` | same offsets |
| Member selector entry traced | `848693F8` | `8486A0F8` |
| Category draw hook, displaced `li r5,3` | `8486B198` | `8486BE98` |
| Formation draw hook, displaced `li r5,1` | `848696C0` | `8486A3C0` |
| Immutable policy allocation | `8462CA00..8462FFFF` | same |
| Executable reservation | `84D0E300..84D0EFFF` | same |
| Last-draw writable receipts | `852D6500..852D653F` | same |

The 13,824-byte policy allocation holds a versioned directory of up to 48 named books. Each entry contains a 28-byte ASCII name and twelve 20-byte bit masks, one bit per ordinary formation ID 0..150. Runtime lookup compares the actual SPLB name at `book+30`; it does not bind by archive ordinal or transient book pointer. No policy, a missing name or an empty mask means retail behavior. The policy survives book normalization because it is stored separately from SPLB's rebuilt caches.

The two generated leaves total **2,480 bytes / 620 instructions**, with **100 checked direct branches**. They filter the already enumerated candidate arrays, preserving retained order and weight bytes. Category filtering respects primary preference, memberships, the hidden flag and special caches. It conservatively retains categories with an unexcluded structural member; the subsequent native member enumeration remains authoritative for play gates and its forty-slot bound. It does not recompute rating means.

If filtering empties a draw, its original count, pointer array and weight array remain. Native receipts record key, sorted book ordinal, original count, filtered count, fallback flag and cumulative fallback count. Category fields begin at `852D6500`; formation fields at `852D6518`. A valid original draw remains valid when emptied by exclusions. This does not repair a book that was already invalid before applying the mask.

Only automatic ordinary CPU offense in scrimmage phase 4 uses the extension. Defense, explicit play/formation paths, special requested rows, cached special shortcuts and kick/try phases bypass it. Patches target the pinned BASE/TU module hashes through the existing Xenia TOML framework. No encrypted retail XEX is rewritten, signed or distributed.

## Editor and persistence

The CPU page adds **Live situations: exclusions and requested personnel**: twelve buckets, every ordinary formation, sample candidacy and personnel/TE information, and an exclusion checkbox. The switch starts off, and no preset stages or enables it. Choices are per named book and bucket. **Preview this live situation** fills the existing custom preview; mask-aware preview notes report empty-draw fallbacks.

The game-computed requested row is read-only and shown with the representative sample and RNG endpoint range. It can change with urgency and overtime field position. The stored MASTER comparison row is editable beside it, explicitly labeled as affecting **all books**. Eleven requested roles are displayed. **An empty TE depth list substitutes an FB**, so a requested TE is not a guarantee of a TE player on the field. This continues APF-3's proved boundary without inventing per-bucket storage for the computed request.

Masks, the switch and stored-row edits use the existing review/replay receipts, undo and project save/reload. A mask-only build preserves the source archive bytes and emits both profile-specific patches, `situation-masks.bin` and `situation-mask-receipt.json`. Explicit installation is required. The page provides export, review/install, status and removal, with canonical validation and rollback through the existing launcher. Its owned patch is synchronized into the launch storage folder. Undo or disabling a project option does not remove an already installed patch; the UI explains removal or installation of an empty policy followed by restart.

## Proofs and limits

**PROVED**:

- BASE/TU native execution of 90 local-exclusion cases: formation 14 excluded only in third down over seven yards; excluding all three Queens removes their category draw when other categories remain; excluding every ordinary formation records both fallbacks and still returns valid tuples.
- Formation 14 remains selectable in three other buckets and in a renamed USER book after native normalization, on both images. Entry and hook traces include registers 3..7, state pointer, down, coordinate words and book name.
- 48 live key boundary traces, plus eight unchanged kick/try/fourth-down cases. The separate 24 unaffected-call comparisons check output, team and book bytes, GPRs/CR and exact RNG call consumption. All inherited 30 native cases pass through the empty-policy detours.
- Twelve native category/formation candidate-and-weight buffer comparisons match the mask-aware preview. An independent edge regression preserves an already-empty category under an unrelated mask.
- Full-width independent synthetic execution checks GPR upper halves, CR, FPRs, FPSCR, LR/CTR, guarded writes and stack restoration. Each leaf uses its own bounded stack frame; no native callback or extra random draw is introduced.
- Exact code/data/image regressions, zero storage, section padding/flags, direct branch and executable literal checks, nearby address-construction checks, strict canonical transport and disjoint writes with the existing pass-fetch patch.
- Offscreen checkbox/preview/shared-row actions; independent named books; real project save/reload and undo; unchanged archives for mask-only builds; both patch/data readbacks; explicit installation, configuration preservation, launch-folder synchronization, removal and failed-write rollback.

| Exact one-exclusion fixture | SHA-256 |
| --- | --- |
| BASE patched flat image | `{native[0]['patched_flat_sha256']}` |
| TU 1.1 patched flat image | `{native[1]['patched_flat_sha256']}` |
| Complete policy allocation | `ba2f34bcd2a76502f51a2e0e5103675a7b00e7601208c6c8b3e23270ffce0cca` |
| BASE emitted code | `bb39ee9f752ced58504e8fddb0c2dfed8a7577e1ee799daadb847467a77aec4d` |
| TU emitted code | `edcc2796d01c5f27b82ffe469267e864c1d088d74f2636c255efbb653d6c7cce` |

The fixture is O-ManBlock with only formation 14 excluded at key 8. Every byte outside the two detours, generated code, immutable policy allocation and owned receipt allocation is compared to its pinned original. Generated TOML is reparsed and every word is canonical. No retail image or book payload is committed.

**HYPOTHESIS / static audit limit:** Each image has 19 address-like untyped words in `.rdata`; the receipt lists their source/value pairs. The retained `.reloc` section is opaque, not a decoded PE relocation table (its first BASE words do not form an IMAGE_BASE_RELOCATION header). They are not claimed as typed pointers or as proved non-pointers. No executable literal, direct branch or nearby `lis`/displacement construction reaches the owned allocations. The ranges are beyond declared content in their mapped final pages, but arbitrary computed/data-derived pointers are not globally certified. This is bounded ownership evidence, not a complete proof about every possible memory access.

**UNWITNESSED**: actual Xenia patch consumption, every mode's live USER/save merge/name lifecycle, match scheduling, real roster availability and rendered on-field outcomes. Native proofs use explicit match/RNG/history inputs and the existing bounded native adapters; they do not run a complete game. APF-3's conditional TE-to-FB proof remains conditional on the supplied depth chart.

## Registry, packaging and failures retained

The existing `apf2k8.playbooks.cpu_playcalling` row is updated; **zero new rows**, retaining **174 total / 72 APF**. Status stays not-tested for gameplay. The alpha.92 changelog and research guide describe the control and limits without names. `WIRING.md` records the protected registry/runtime integration made under the user's explicit request. The APF allowlist adds three modules and the guide. The runtime gate now validates all three mask ranges, pinned code/data bytes, canonical documents, default-off state and disjoint pass-fetch writes. The original pass-fetch preflight and emitted code remain unchanged.

Strict validator and repin pass. Provider integrity, product catalog, phase1 packaging, all APF/play-calling acceptance suites and staged release/runtime pass. The staged product contains **285 files** and imports **159 modules**, with 72 APF capabilities. Optional skips are listed in the suite results and are not counted as native proof. The new native file has no skips.

Failures are retained in the ledger: initially missing private evidence; missing accessibility descriptions on new controls; registry canonical-JSON formatting; the original whole-page reservation expectation in the installer; the first overly broad numeric-pointer census; attempts to parse the opaque `.reloc` payload as conventional relocation blocks; Git's expected ignore refusal for the new research doc; and an attribution audit that initially counted unchanged historical changelog text as newly authored material. Each was resolved or explicitly bounded as described above. No required final gate is left failing. The original batch coordinator's exit 1 records the first installer failure; the final aggregation uses each file's latest **complete** standalone run, never a selected passing test.

The 75 missing evidence paths were restored as independent copies with the APF-3 recorded size/hash checks; source files were read only. The reviewed extractor was restored from the archived public build using its existing pins. No network download occurred. `tools/apf_h7a_optimal` remains mode 0755. `.scratch` remains below 200 MB and contains no retail image or disc copy.

## Retest

1. Use the owned BASE XEX, TU 1.1 package and APF index via the existing `APF_RETAIL_XEX`, `APF_RETAIL_TU`, `APF_RETAIL_INDEX` overrides. Missing native inputs are precise optional skips and do not constitute proof.
2. Run `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_b71_situation_mask_native.py` and the mask data, ABI, Qt and install files. The existing native file remains independently runnable. Local Capstone 5.0.7/Unicorn are needed; `reports/b71_apf3/prepare_test_python.py` can recreate the private interpreter from installed dependencies.
3. Select O-ManBlock, enable masks explicitly, choose third down over seven yards, and exclude formation 14 or all Queens 2/14/24. Preview third-and-8 and other buckets; save/reopen, undo, switch named books, and check that the chosen mask alone persists.
4. Build a copied game and review the patch/data receipts. Install the matching BASE or TU patch through the explicit page action. Restart. The tester records actual loaded book, executable profile, USER/save overlay, depth chart and players for third-and-8 versus other buckets. Real personnel reassignment already has a witness; the new exclusion needs its own witness.
5. Exclude all ordinary formations in one bucket to witness the documented fallback, and compare kick/two-point behavior. Restore the mask, or remove the installed patch and restart to return to retail.
6. Re-run the full file list in `suite_results.json`, strict validator, repin, provider/catalog/phase1 and the staged release/runtime commands below. Installer runs clear source PYTHONPATH so staged imports are authoritative.

## Command ledger

UTC starts, elapsed seconds, exit codes and full logs are below; `commands.jsonl` is authoritative. Read-only file inspection and exploratory disassembly are not acceptance commands and are not represented as tests. Final report commit and bundle commands are recorded separately in `.scratch/astra-b71-apf4-delivery.json` to avoid a self-referential commit ID.

| UTC start | Seconds | Exit | Command | Log |
| --- | ---: | ---: | --- | --- |
'''
for record in records:
 command=shlex.join(record['command']).replace('|','\\|')
 text+=f"| {record['started_utc']} | {record['elapsed_seconds']:.3f} | {record['exit_code']} | `{command}` | [{Path(record['log']).name}]({record['log']}) |\n"
(root/'ASTRA_REPORT.md').write_bytes(text.encode())
(root/'ASTRA_LAST_MESSAGE.md').write_bytes(f'''Implemented APF-4 and delivered the private bundle at `.scratch/astra-b71-apf4.bundle`.

{results['passed']}/{results['suite_files']} standalone suites pass; 36/36 expanded native tests include the original 30/30. Strict validator, repin, provider/catalog/phase1, APF release and runtime checks pass. Gameplay remains UNWITNESSED. Requested-row and static-reference limits are explicit in ASTRA_REPORT.md.

No push or emulator launch.

ASTRA_DONE
'''.encode())
print('Wrote ASTRA_REPORT.md and ASTRA_LAST_MESSAGE.md')

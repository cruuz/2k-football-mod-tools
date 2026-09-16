"""Assemble the final integration report from measured command receipts."""
from pathlib import Path
import json
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
audit = json.loads((OUT / 'final-audit.json').read_text())
manifest = audit['manifest']
rows = sorted((json.loads(p.read_text()) for p in OUT.glob('*.result.json')), key=lambda r: r['started'])
by_name = {r['name']: r for r in rows}
volume = json.loads((OUT / 'volume.json').read_text())
locations = json.loads((OUT / 'wiring-locations.json').read_text())
ledger = OUT / 'command-ledger.json'
ledger.write_text(json.dumps(rows, indent=2) + '\n')

text = f'''# Beta 71 A7: combined painted-bar integration

Private branch `astra/b71-a7-integrate` starts from A6 `07c544a2c9a5c20c27a8e6557874b15a552d9d82` and merges S4 `7b54e354ab8187c59b12cf66671982c822bf9d03`. Private Git directory: `.scratch/git-a7`. The shared Git directory is untouched. No push, emulator or GUI launch.

All requested final suites and both studios' release/runtime closures pass: **{audit['required_completed']} required command receipts**, **{audit['unittest_cases']} reported unittest cases**. Full logs and exact arguments are linked below. Skips retain their stated boundaries and are not runtime evidence.

Registry: **176 unique capabilities = 102 2K5 + 73 APF + 1 third game**. Provider closure: **287**. Product catalog tuple: **`(102, 80, 8, 1, 0, 10, 3)`**, with its exact ID set. Validation-plan pins: **176 total / 171 covered / 5 deferred / 129 distinct validators**. The id-indexed union retains every exact A6 row except the exact updated S4 scorebug runtime row. Colour v2.1, day/afternoon tuning, linked sidelines, modern Arrowhead and APF4/APF5 remain integrated.

## Merge and conflict receipt

Before any workspace mutation other than those copies, S4's root report and wiring were archived as `ASTRA_B71_S4_REPORT.md` and `WIRING_B71_S4.md`, with human attributions anonymized. The A6 report is retained anonymously at `reports/b71_a7/INHERITED_A6_REPORT.md`.

The explicit-commit merge had six conflicts:

1. `ASTRA_REPORT.md`: A6 was retained as the working checkpoint, with both input reports archived; this A7 report replaces it.
2. `ASTRA_LAST_MESSAGE.md`: A6 was retained until the A7 handoff was written.
3. `data/nfl2k5_cave_reservations.json`: A6 supplied the seed; the complete merged forward stack was observed and the manifest regenerated last.
4. `docs/mod_editor/2k5_mod_studio_changelog.md`: both sides' distinct bullets were retained, including the older scorebug iteration history and S4 painted-bar entry.
5. `packaging/release-allowlist.txt`: both colour-control paths and all three S4 module/label paths were retained.
6. `tests/mod_editor/test_provider_integrity.py`: A6's exact 287-module closure pin was retained; the final exact-set/hash test passes.

The registry, provider pin map and remaining implementation merged cleanly. S4 supersedes the inherited S3 atlas/wing/plate/capsule/label/score-cell implementation through normal ancestry. Generated pin files were passed through `packaging/repin.py --apply`, which needed zero updates. All commits enumerate explicit paths; `git commit --include -- <paths>` preserves the real merge parents while concluding the conflicted merge.

## Wiring and release integration

S4's `WIRING.md` is byte-identical to its S3 parent's file; it contains inherited beta-70 T1 follow-ups, not new S4 instructions. Its completion-dialog hooks are already present in A6. Historical Windows-helper and digit-fit proposals are not new painted-bar work. The root `WIRING.md` records this disposition.

One S4 packaging omission was corrected: the new authored `painted_label_2x.png` was allowlisted but absent from the exact reviewed PNG catalog. Its catalog entry now pins 11,138 bytes, 512×256 dimensions and SHA-256 `b8632704a110087b939a2e1de98c54eebc2354f40bb89d3eb2f0b16bdfa45b2d`; the catalog hash is refreshed. No binary-validation rule was relaxed. See `label-release-pin.json`.

The 75 inherited ignored evidence files were initially absent. `reports/b71_apf4/hydrate.py` restored independent copies from the recorded read-only sources, checking the prior inventory; `audit_pins.py` also checked S4's SHA-256 inventory: **2,063,157 bytes**, all single-link files. These private inputs are not staged or bundled. The strict registry validator keeps its default file checks. Reviewed APF release tooling and the pinned local Capstone test environment were restored using the existing A6 recipes without network or system changes.

| Wiring/count anchor | File:line |
| --- | --- |
'''
for r in locations:
    text += f"| `{r['anchor']}` | `{r['path']}:{r['line']}` |\n"
text += f'''
## Appended payload and accepted visual limits

Fresh bounded compilation measured each component; `volume.json` contains individual resource sizes and hashes. No retail resources were saved in reports.

| Component | Count | Appended bytes |
| --- | ---: | ---: |
'''
for r in volume['components']:
    text += f"| {r['component']} | {r['count']} | {r['bytes']:,} |\n"
text += f'''| **Total** | **34 TXTR + 2 FONT** | **410,624** |

The append is **0.391602 MiB**, **2,944 bytes below v3's 413,568**, within the required ~0.4 MB class. Sector-aligned pack growth is **411,648 bytes**. S4's loader allocation accounting is 414,080 native heap bytes; this is not a measured game peak-memory guarantee.

The owner emits **1,380 bytes** inside `CODE_SIZE=1408`, with `DATA_SIZE=128`. Cave requests remain `(nfl2k5_scorebug_runtime, code, 1408, 16)` and `(nfl2k5_scorebug_runtime, data, 128, 16)`. Current allocations are recorded in `manifest-receipt.json`.

The supplied v4 verdict accepts all six v3 residuals. The remaining KC transparent-cell fringe, top rim measured at (42,40,44) against the (37,37,37) body rather than about (60,64,70), and 256-pixel frame tile stretched across 1,041 source pixels were deliberately left unchanged. S4's exact-pixel comparison remains false (RGB MAE 36.479 / 35.514). Its software-render verdict does not witness gameplay or GPU filtering.

## Manifest receipt

The final manifest is the **bounded complete forward XBE projection**, using the A6 parent manifest SHA-256 `bbc7b1afd93bd4e0c7cabb02452d54e7ac05e6fe6e0d26d4ffdaf381a5368315`. The A6 recipe retains historical retail reservations, observes every forward owner, applies the colour owner and excludes delegated shared helpers from duplicate ownership. S4's changed ingame writer is explicitly observed; its two offline compiler/render tools are recorded as non-XBE source snapshots.

- Manifest SHA-256: `{manifest['sha256']}`; {manifest['bytes']:,} bytes.
- Reservations: {manifest['reservations']:,}; source seals: {manifest['source_count']}; observed writer steps: {manifest['observed_steps']}.
- Composed XBE SHA-256: `{manifest['stack_xbe_sha256']}`.
- `release_manifest=false`, `disc_built=false`, `runtime_witnessed=false`, `production_regeneration_required=true`; inherited disc fields are historical.
- Final projection: exit {by_name['manifest-projection-delivery']['exit_code']}, {by_name['manifest-projection-delivery']['seconds']} seconds. It ran after the final repin and was the last product code/data change. All {audit['product_paths_frozen']} other product/test/docs paths retain their frozen hashes.
- Production launcher: exit {by_name['manifest-production']['exit_code']}, {by_name['manifest-production']['seconds']} seconds. Directory creation failed with `Errno 30` / read-only Storage. External command: `bash reports/b71_a7/manifest_regen.sh`.

The projection is the requested sandbox deliverable. No production build receipt has been invented. `manifest-receipt.json` and both logs record the actual results.

## Prepared disc, not executed

`reports/b71_a7/build_testdisc71.py` is prepared and statically parsed/compiled, never imported or run, including `--plan-only`. Exact name:

`NFL 2K5 MOD TEST 2026-09-15k (everything + painted bar)`

Preset: Advanced (`softdrink_advanced`). Exactly the disc-i overrides: `scorebug=True`, `scorebug_runtime=True`, `modern_color=True`, `modern_arrowhead=True`, `widescreen=True`. It refuses an existing named disc or patch, checks output-directory access before pruning, removes the oldest MOD TEST images until fewer than three remain, and retains patch archives. It reparses scorebug resources/runtime, colour XBE/all 477 bundles, Arrowhead and 16:9 widescreen from the built disc before exporting the patch. An incomplete disc is removed on failure; a verified disc survives a later patch-export failure. Import the bundle before running externally so the build source is the delivered head.

No disc, patch export or disc read-back was produced here. Output storage is read-only. The prepared name retains the requested 2026-09-15 date even though UTC gate timestamps may fall on the next day.

## Every recorded command result

Order: strict registry/count audit; repin; final manifest projection; fast manifest suites; four detached XBE gates; then pairwise, presentation/colour/APF/provider/catalog/packaging checks and both studios' closures. Each of the four XBE gates used `setsid nohup`, its own log and stdin `/dev/null`; the launching shell waited on child PIDs and logs were polled. No `pkill -f` was used. Every suite ran standalone with Qt offscreen. Independent suites ran concurrently within their phase.

The exact argv arrays and UTC start/end timestamps are in [command-ledger.json](reports/b71_a7/command-ledger.json). Large explicit commit path lists are linked through their receipt instead of duplicated in this table. Read-only discovery and file assembly are also retained in the session tool transcript. Preliminary failures are preserved, never substituted for final receipts.

| Command/log | Exit | Seconds | Exact invocation or argv receipt |
| --- | ---: | ---: | --- |
'''
for r in rows:
    name = r['name']; command = shlex.join(r['argv']).replace('|', '\\|')
    rendered = '`' + command + '`' if len(command) < 800 else f'[exact argv](reports/b71_a7/{name}.result.json)'
    text += f"| [{name}](reports/b71_a7/{name}.log) | {r['exit_code']} | {r['seconds']} | {rendered} |\n"
text += '''
The initial archive commit needed explicit staging and was retried successfully. The merge's exit 1 reports the six resolved conflicts. The first pin-audit script matched an unrelated string `.replace` call; restricting that audit to `dataclasses.replace` fixed the audit without changing the builder. The first projection refused three unaccounted S4 source changes; explicit writer observation and documented non-XBE tool classifications corrected the recipe. A successful preliminary projection was repeated after the PNG-catalog correction and final repin to preserve the required delivery order. The production-launcher failure remains an external read-only-storage limitation.

## Skip boundaries

'''
for key, lines in sorted(audit['skips'].items()):
    text += f'- `{key}`:\n'
    for line in lines:
        text += '  - ' + line + '\n'
text += '''
## PROVED / UNWITNESSED and delivery

**PROVED:** exact registry union and count pins; actual appended component bytes; unchanged owner allocation; current manifest source seals and complete forward observation; passing requested offline/native/ABI/composition tests; both product packaging closures; the builder's static name/options/order contract; explicit-path private commits and verified bundle fetch/tree read-back.

**UNWITNESSED:** disc construction/read-back, boot and intro peak memory, coin toss/kickoff, real score/timeout/possession/event transitions, GPU filtering, final combined stadium/lighting appearance, APF played behavior and installations on unexecuted platforms. Historical witnesses do not convert this combined build into a played-game result.

Bundle: `.scratch/astra-b71-a7.bundle`, based on prerequisite `07c544a2`. `.scratch/astra-b71-a7-delivery.json` records the final head/tree, bundle size/hash and independent fetch/connectivity verification, including final delivery command exit codes and times. No retail bytes, hydrated private evidence, disc images or patch archives are bundled. Scratch remains below 200 MB. No push. No xemu.
'''
(ROOT / 'ASTRA_REPORT.md').write_text(text)
(ROOT / 'ASTRA_LAST_MESSAGE.md').write_text('''A7 integrates A6 and S4 on private branch astra/b71-a7-integrate. All requested final gates and both studios' release/runtime closures pass. Registry 176, provider closure 287, product tuple (102, 80, 8, 1, 0, 10, 3).

Appended payload: 410,624 bytes (logos 168,960; neutral 2,208; atlas 132,256; slot-9 font 80,160; quarter font 27,040), 2,944 bytes below v3.

The bounded manifest projection is delivered with production regeneration required. Storage is read-only; the external launcher is reports/b71_a7/manifest_regen.sh. The requested Advanced disc-k builder is prepared at reports/b71_a7/build_testdisc71.py and was not run. Gameplay remains UNWITNESSED; the accepted S4 visual residuals are unchanged.

Bundle: .scratch/astra-b71-a7.bundle (prerequisite 07c544a2). Full merge, wiring, command/timing and manifest receipts: ASTRA_REPORT.md and reports/b71_a7/. Final private head and verified bundle hash: .scratch/astra-b71-a7-delivery.json. No push or emulator launch.

ASTRA_DONE
''')
print('Wrote final report, last message and exact command ledger.')

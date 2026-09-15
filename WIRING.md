# APF-3 integration

All wiring is implemented in this branch. No remaining integration code is delegated to another checkout.

## Registry

The job explicitly requests registry rows/evidence. Five existing objects in `mod_editor/capabilities/registry.v1.json` are replaced by the complete objects in `docs/research/apf_b71_apf3_registry.json`:

- `apf2k8.playbooks.cpu_playcalling`
- `apf2k8.playbooks.identity`
- `apf2k8.playbooks.offensive_schemes`
- `apf2k8.playbooks.scheme_presets`
- `apf2k8.playbooks.scheme_spreadsheet`

This integrates APF-2's pending handoff and adds APF-3's native weight, export and final-lineup evidence. Independent situation exclusion stays explicitly unimplemented. Gameplay status remains not-tested / UNWITNESSED.

There are **zero new rows**. Shared and APF counts remain **174 / 72**. No row count pins change.

## Required APF runtime contract update

Applying the registry replacements exposed an omitted APF-2 integration step: `packaging/check_apf2k8_mod_studio_runtime.py` still required the two hidden scheme cards to be Editable. The unchanged checker rejected the integrated registry with `public editable capability/action boundary changed`.

As part of the requested registry integration and runtime gate, the exact `expected_editable` set drops `apf2k8.playbooks.offensive_schemes` and `apf2k8.playbooks.scheme_presets`. An additional assertion requires both cards to have `ApfStatus.EVIDENCE`. Exact equality and complete-editor/writer checks for every remaining editable card are preserved. This changes the protected APF checker only to match the approved consolidated workflow; no installer test, 2K5 checker, build owner or 2K5 GUI is edited.

## Packaged research

`packaging/apf2k8-release-allowlist.txt` includes `docs/research/apf_b71_apf3.md`, linked by the book walkthrough. The native instrument and private command logs are not packaged with the product.

## Private hydration

Despite the supplied hydration expectation, the first strict validator found 75 missing evidence paths. They were restored as ordinary, independent files from narrowly scoped read-only access to the original evidence copies. `reports/b71_apf3/hydration.json` records sizes, hashes and source paths. These private research/assets copies are excluded from the commit path list and release. The source checkout was not modified.

Run the normal repin, strict validator, provider integrity, product catalog, phase1 packaging, APF installer, staged release and staged runtime checks. The final commands and results are recorded in `ASTRA_REPORT.md`.

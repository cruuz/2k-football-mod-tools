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

# APF-5 integration

The APF-5 brief explicitly requests registry/evidence and release/runtime checks.
The following wiring is implemented here; no APF-4 situation code/table is edited.

- New registry object `apf2k8.playbooks.fourth_down`, inserted in id order before
  `apf2k8.playbooks.identity`, names `mod_editor/core/apf2k8_fourth_down.py`,
  bounded native and authored-byte evidence, the Tools dialog, and default off.
  Runtime status stays `not-tested`. No existing registry object changes.
- `mod_editor/apf_studio/models.py:CAPABILITY_ACTION_BINDINGS` adds the reviewed
  authored-patch writer. `gui.py:_install_menus` adds Tools → CPU fourth-down
  triggers, with `_fourth_down_triggers` opening its independent dialog.
- `packaging/apf2k8-release-allowlist.txt` adds only these four shipped paths:

```
mod_editor/core/apf2k8_fourth_down.py
mod_editor/apf_studio/fourth_down_qt.py
docs/mod_editor/apf2k8_fourth_down_and_xenia.md
docs/research/apf_b71_fourth_down.md
```

- `packaging/check_apf2k8_mod_studio_runtime.py:PRODUCT_MODULES` adds the two
  modules above; the exact registry contract is now:

```python
len(registry.capabilities) == 175
len(registry.for_game(core_model.GameId.APF2K8)) == 73
len(cards) == 73 and len({item.capability_id for item in cards}) == 73
```

  The existing `expected_editable` set adds only
  `'apf2k8.playbooks.fourth_down'`; all prior equality checks remain.
- `packaging/check_2k5_mod_studio_runtime.py` changes only the shared-registry
  count assertion and summary from 174 to 175. The 101 2K5 capabilities and
  all 2K5 behavior remain untouched. The two corresponding source-contract
  expectations in `test_phase1_packaging.py` and `test_apf_studio_installer.py`
  change only that count. `test_apf_capability_action_parity.py` verifies the new
  authored-patch writer just as it verifies the two older patch writers.
- Launcher configuration recognizes Edge/Canary, persists the runtime choice,
  writes only HID.hid to SDL with parsed readback, and retains explicit config
  paths. Managed launch-patch synchronization adds the canonical fourth-down
  file. No executable runs during configuration or tests.

Private evidence hydration repeats APF-3's 75 missing inherited files with
exact prior SHA-256 checks; no copy enters the implementation commit. See
`reports/b71_apf5/hydration.json`. Test/release results and proof limits are in
`ASTRA_REPORT.md`. No manual integration patch is outstanding.

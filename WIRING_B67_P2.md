# Beta 67 P2 integration handoff

PROVED authored changes: USER/global book lists, same-side clones, Fine-tune name resolution and patch installation are implemented in their owned modules. Their tests run offscreen. `ASTRA_BRIEF.md` reserves `mod_editor/apf_studio/gui.py`, and `ASTRA_CONTEXT.md` reserves `mod_editor/capabilities/registry.v1.json`; these two files were not edited. Apply only this new section for P2. Older handoffs remain below as history.

## Launch result message

In `mod_editor/apf_studio/gui.py`, replace `ApfStudioMainWindow._launch_complete` (currently near line 21948) with this complete method. PROVED: `LaunchReceipt.patch_status` is now supplied by the launcher and tested with a fake process. HYPOTHESIS/UNWITNESSED: rendering this main-window message after a real Xenia launch still needs a witness.

```python
    def _launch_complete(self, receipt: object) -> None:
        pid = int(receipt.pid)  # type: ignore[attr-defined]
        log = Path(receipt.log_path)  # type: ignore[attr-defined]
        patch_status = str(getattr(receipt, "patch_status", "Patch status unavailable."))
        self._last_detail = f"Xenia started as process {pid}. Log: {log}\n{patch_status}"
        QMessageBox.information(
            self,
            "Xenia started",
            f"Xenia Canary started the verified modded default.xex.\n\n"
            f"Process: {pid}\nLog: {log}\n\n{patch_status}",
        )
```

PROVED: no new main-window config picker is required. The CPU Play Calling panel already exposes Choose Xenia config, install, remove and status. `configure_xenia(..., xenia_config=...)` is also available through the facade. The existing two-argument main-window configuration call remains valid.

## Existing capability row updates

In `mod_editor/capabilities/registry.v1.json`, locate the following existing IDs. Replace exactly the values described here, retain other fields, and append the listed evidence paths if absent. PROVED: these extend existing capabilities and their verifiers; no new capability ID, selector writer, preset or build route is needed. HYPOTHESIS: runtime remains `not-tested`, unchanged until played.

For `apf2k8.playbooks.clone`, replace `selectors.fields` with:

```json
[
  {"allowed": "unused label 0..68 on the same side as the donor", "name": "label_id", "required": true},
  {"allowed": "team slot 0..39", "name": "team_index", "required": true},
  {"allowed": "one of the 15 named stock, USER or global offensive/defensive books", "name": "donor_type", "required": true}
]
```

Append to that row's `evidence`:

```json
[
  "tests/mod_editor/test_apf_b67_books_qt.py",
  "docs/research/apf_defense_playcall_model.md"
]
```

For `apf2k8.playbooks.pass_fetch_te_bias`, replace `gui.reason` with:

```json
"CPU Play Calling: install a chosen Studio BASE or TU 1.1 pass-fetch patch in Xenia's patches folder after consent. Enable apply_patches in the selected launch config, reparse and report installed/enabled state, and offer removal. Last-resort fetch only; not a CPU play-calling fix. Gameplay UNWITNESSED."
```

Append to that row's `input_constraints`:

```json
[
  "Studio installation accepts only the canonical BASE or TU 1.1 pass-fetch payload. Explicit consent enables Memory.apply_patches; other enabled Xenia patches can also become active. Restart Xenia after changing installation.",
  "Removal deletes only the Studio-managed pass-fetch file and leaves unrelated patches and the shared apply_patches setting alone."
]
```

Append to that row's `evidence`:

```json
[
  "tests/mod_editor/test_apf_b67_xenia_patch.py",
  "docs/research/apf_defense_playcall_model.md"
]
```

PROVED: the CLI export's separate output selector remains valid; it is the Studio deployment path that changes. EXPERIMENTAL, no preset enables the patch automatically. The compiler retains full BASE/TU image, hook and cave pins; the installer checks the generated TOML's semantic payload and reparses the selected config.

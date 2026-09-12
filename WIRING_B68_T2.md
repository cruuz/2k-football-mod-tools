# Beta 68 T2 integration wiring

GUI panels and the capability registry are protected. These edits are for Claude to apply before release; none of those GUI files was modified in this branch. The scope refusal and compiler changes are already implemented in core. No mod_build change and no XBE cave manifest regeneration are needed. No preset enables a new patch: independent artwork and shoe relief remain EXPERIMENTAL / UNWITNESSED, chosen by an explicit import.

## 1. Equipment import dialog

Replace `mod_editor/gui/equipment_texture_import_dialog.py` with this complete file. A global row has exactly one scope option, “All teams”; the sentence comes from the same core constant used to refuse a per-team request. The full-size choice stays first. Socks and their mud row enable own artwork through the already wired capability predicate.

```python
"""Owned equipment import choice; the shared Studio panel wires this dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)
from mod_editor.core.nfl2k5_equipment_import_intent import (
    CHOICE_CAPTION, CHOICE_HELP, PALETTE_HELP, supports_own_texture,
)


from mod_editor.core.nfl2k5_equipment_import import (
    equipment_import_scope, PACKAGE_LOCAL_SHOE_HELP,
)


class EquipmentTextureImportDialog(QDialog):
    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import equipment artwork")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        target = QLabel(f"{asset.label}\nPNG size: {asset.width} x {asset.height}")
        target.setWordWrap(True)
        layout.addWidget(target)
        choices, rule = equipment_import_scope(asset.asset_id)
        layout.addWidget(QLabel("Import applies to:"))
        self.import_scope = QComboBox()
        self.import_scope.setObjectName("equipmentImportScope")
        for value, caption in choices:
            self.import_scope.addItem(caption, value)
        layout.addWidget(self.import_scope)
        scope_note = QLabel(rule)
        scope_note.setObjectName("equipmentScopeExplanation")
        scope_note.setWordWrap(True)
        layout.addWidget(scope_note)
        if ":shoes" in asset.asset_id:
            local_note = QLabel(PACKAGE_LOCAL_SHOE_HELP)
            local_note.setWordWrap(True)
            layout.addWidget(local_note)
        default = QLabel(
            "Socks, gloves and shoes default to their own artwork, including when you copy an exported style. "
            "Untick below only for a recolour of the existing shared design. " + PALETTE_HELP)
        default.setWordWrap(True)
        layout.addWidget(default)
        self.own_texture = QCheckBox(CHOICE_CAPTION)
        self.own_texture.setObjectName("equipmentOwnTexture")
        self.own_texture.setChecked(supports_own_texture(asset.asset_id))
        self.own_texture.setEnabled(supports_own_texture(asset.asset_id))
        self.own_texture.setToolTip(CHOICE_HELP)
        layout.addWidget(self.own_texture)
        help_text = QLabel(CHOICE_HELP)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addWidget(QLabel("Image size in the game:"))
        self.game_size = QComboBox()
        self.game_size.setObjectName("equipmentGameImageSize")
        for scale in (1, 2, 4):
            self.game_size.addItem(f"{asset.width // scale} x {asset.height // scale}"
                                  + (" (original size)" if scale == 1 else ""), scale)
        self.game_size.setEnabled(self.independent)
        self.own_texture.toggled.connect(
            lambda checked: self.game_size.setEnabled(checked and self.own_texture.isEnabled()))
        layout.addWidget(self.game_size)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Check and import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def independent(self) -> bool:
        return self.own_texture.isEnabled() and self.own_texture.isChecked()

    @property
    def scale(self) -> int:
        return int(self.game_size.currentData()) if self.independent else 1

    @property
    def scope(self) -> str:
        return str(self.import_scope.currentData())
```

## 2. Pass the selected scope through Studio

In `mod_editor/gui/studio_qt.py`, the facade protocol's `replace_equipment_texture` signature becomes:

```python
    def replace_equipment_texture(
        self, asset: object, supplied_png: Path, progress: ProgressSink, *,
        independent: bool | None = None, scale: int = 1, scope: str | None = None,
    ) -> object: ...
```

In `_replace_visual_asset`, replace the `equipment_choice` declaration and its assignment after `dialog.exec_()`:

```python
        equipment_choice: tuple[bool, int, str] | None = None
```

```python
            equipment_choice = (dialog.independent, dialog.scale, dialog.scope)
```

In its nested `replace_texture`, replace the equipment branch:

```python
            if equipment_choice is not None:
                independent, scale, scope = equipment_choice
                return self.facade.replace_equipment_texture(
                    asset, path, progress, independent=independent, scale=scale, scope=scope,
                )
```

`StudioFacade.replace_equipment_texture` already accepts and forwards `scope`. Update the `_FacadeStub.replace_equipment_texture` in `tests/mod_editor/test_2k5_uniform_equipment_export.py` to accept `scope=None`, and the stub returned by `_auto_accept_equipment_dialog` to set `scope="all-teams"`. After wiring, run that complete suite with its existing generated visual catalog reports available.

## 3. Existing Bump Maps tab

`mod_editor/core/nfl2k5_bump_texture_writer.py` now discovers GLOBAL.IFF from the index and returns its seven shoe maps through the same `list_packages` / `package_bump_slots` APIs. The existing table needs no parallel data source or hardcoded outer selector. In `mod_editor/gui/bump_panel_qt.py`, add this import:

```python
from mod_editor.core.nfl2k5_bump_texture_writer import SHOE_BUMP_NAMES, SHOE_BUMP_SCOPE
```

In `BumpPanel._build_ui`, replace the title and subtitle construction:

```python
        title = QLabel("Uniform and shoe bump maps (advanced)")
        title.setObjectName("bumpTitle")
        subtitle = QLabel(
            "Edit jersey, pants, sleeve and sock fabric maps in a selected uniform package. "
            "Select GLOBAL.IFF for shoe relief maps. " + SHOE_BUMP_SCOPE + " "
            "Import checks every distance image and available space before Write is enabled. "
            "Writes update the working disc copy you choose. Experimental / unwitnessed."
        )
```

Change the package table headings to `("Outer", "Package", "Size")`. In `_slot_selected.done`, replace the `_set_status` call with:

```python
            scope = SHOE_BUMP_SCOPE if name in SHOE_BUMP_NAMES else "Selected uniform package."
            self._set_status(
                f"{name}: {metadata['width']}x{metadata['height']}, "
                f"{metadata['mip_levels']} distance images. {scope} Experimental / unwitnessed."
            )
```

In `_import_clicked.done`, replace its `_set_status` call with:

```python
            self._set_status(
                f"{name}: every distance image and the fixed span checked. "
                f"{result['scope']} Experimental / unwitnessed."
            )
```

In `_write_clicked`, before `confirmation = QMessageBox.question`, insert:

```python
        scope = SHOE_BUMP_SCOPE if name in SHOE_BUMP_NAMES else "Selected uniform package."
```

Replace that question's body argument with:

```python
            f"Replace {name} in {label} inside:\n{target}\n\n"
            f"{scope} This updates that copy in place. The source disc is not touched.",
```

Styles 3 and 6 provide per-team **colour** through shoes09/shoes10, but both use global relief map 7. Maps 5 and 6 are present and editable, but no selection in the reviewed six-style/taped table uses them. Do not promise that they appear on a player. The existing tab label in `studio_qt.py`, “Bump Maps (advanced)”, can stay.

## 4. Capability metadata

In `mod_editor/capabilities/registry.v1.json`, append the following complete capability row (or merge into an equivalent bump row if integration has added one). The source writer, fixed-span verifier and tests are present. The new feature is not a preset patch.

```json
{
  "backend": {
    "command": "python3 -m mod_editor.core.nfl2k5_bump_texture_writer import <source> <working-copy> <outer> --chunk <name> --png <authored.png>",
    "module": "mod_editor/core/nfl2k5_bump_texture_writer.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "ASTRA_REPORT.md",
    "tests/mod_editor/test_nfl2k5_shoe_relief.py",
    "tests/mod_editor/test_nfl2k5_equipment_texture_native.py",
    "tests/mod_editor/test_nfl2k5_bump_texture_writer.py"
  ],
  "game": "nfl2k5_xbox",
  "gui": {
    "default_enabled": false,
    "expose": true,
    "mode": "edit",
    "reason": "Advanced Bump Maps tab; source read-only, explicit working-copy write. Shoe relief is shared across teams. EXPERIMENTAL / UNWITNESSED."
  },
  "id": "nfl2k5.uniforms.bump_textures",
  "input_constraints": [
    "Uniform jersey, pants, sleeve and sock maps retain their A8R8G8B8 layout; GLOBAL.IFF contains seven separate 128x128 P8 shoe relief maps.",
    "Exact dimensions and every mip must decode to the authored pixels; P8 imports needing more than 256 colours or exceeding the fixed compressed span are refused.",
    "Wrapper, including the retail in-place loader scratch word, and all unselected spans stay exact. Sources cannot be write targets.",
    "Styles 1, 2, 3, 4, 5 and 6 use bump_shoes1, 4, 7, 2, 3 and 7 respectively. Maps 5 and 6 are present but not selected by those styles."
  ],
  "portme": [
    "Witness shoes close up and at distance, both teams and swapped home/away, with changed colour and relief maps. Do not claim new per-team relief."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Only source selectors, code, authored inputs and hash evidence are distributable.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [],
    "scope": "Pinned resource and bounded CPU binding proofs only; no game or GPU witness.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [
      {
        "allowed": "entry-table-discovered uniform package or GLOBAL.IFF",
        "name": "outer_index",
        "required": true
      },
      {
        "allowed": "bump_jersey, bump_pants, bump_sleeve, bump_sock, bump_shoes1..7",
        "name": "chunk",
        "required": true
      }
    ],
    "notes": "GLOBAL.IFF is discovered by its name hash 0x8EE9EEED; its shoe relief maps are league-wide."
  },
  "source_container": {
    "format": "VC-LZ TXTR in Xbox VC archive packs",
    "hash_pins": [
      "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    ],
    "resource": "Four maps per uniform package plus seven global P8 shoe relief maps.",
    "retail_file": "User-owned ESPN NFL 2K5 USA XISO"
  },
  "summary": "Edit uniform fabric maps and shared shoe relief maps inside fixed spans of a working disc copy; reparse every authored mip before writing.",
  "surface": "uniforms",
  "title": "Uniform and shoe bump maps (experimental, unwitnessed)",
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_shoe_relief.py"
}
```

For `nfl2k5.textures.all_p8` and `nfl2k5.uniforms.all_visual`, replace the old equipment-only paragraph in `input_constraints` with:

```text
Socks, gloves and shoes can own a selected independent mip chain; new imports default to that choice. Global equipment rows offer All teams only, and explicit per-team requests are refused. shoes09/Style 3 and shoes10/Style 6 read each team's selected uniform package; players must select the corresponding shoe style. Unchanged retail exports at original size preserve the pinned palette and all distance images, reusing an identical shared chain when possible; otherwise exact allocation must fit or the import is refused. Half/quarter images explicitly discard detail; new art can also merge colours to fit P8 or the fixed span, with measured errors in the receipt. Siblings and retail wrapper scratch stay exact. All new in-game appearance remains unwitnessed.
```

Append `tests/mod_editor/test_nfl2k5_equipment_retail_roundtrip.py`, `tests/mod_editor/test_nfl2k5_equipment_consumers.py` and `ASTRA_REPORT.md` to those rows' evidence. No new module needs release allowlisting; new tests/docs follow normal integration policy.

## 5. Integration gates

Run `python3 packaging/repin.py --apply` last before the integration commit, then the equipment, shoe relief and offscreen wiring suites listed in ASTRA_REPORT. These changed writers edit archive data, not the XBE: **no cave manifest regeneration is needed for T2**. T1 owns `nfl2k5_equipment_lz.py`; this branch does not edit it. The generated provider/runtime hash changes are part of T2's repin, not hand changes to protected release checks.

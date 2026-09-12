## H3 beta 66.1: CPU book content control (2026-09-11)

This section supersedes the September 9 Book Identity instructions below where they conflict. Owned implementation is complete; `gui.py` and the protected registry/release gates were not edited. Existing Book Identity page construction and the `_update_product_state` call to `book_identity.set_busy(bool(self._workers))` already connect the new editor and disable its dialogs during disk work. No new tab, navigation index or signal connection is needed.

### `mod_editor/apf_studio/gui.py`: complete replacement block

In `CATEGORY_BLURBS`, replace the entire `ApfCategory.PLAYBOOKS` item with:

```python
    ApfCategory.PLAYBOOKS: (
        "Edit CPU book formations, plays and same-formation audibles. Book Identity "
        "gives one team an independent offensive copy and opens it in Fine-tune. "
        "Build the original Studio project before cloning, then use the named "
        "book-edit recipe to continue. Content recipes remain editable. "
        "Expanded-book gameplay is UNWITNESSED."
    ),
```

Keep these existing blocks unchanged (included in full to make the required wiring reviewable):

```python
from .book_identity_qt import BookIdentityPanel
```

In `InspectorCategoryPage.__init__`:

```python
self.book_identity = BookIdentityPanel(run_task, facade=facade) if category is ApfCategory.PLAYBOOKS else None
```

In the Playbooks tab construction:

```python
tabs.addTab(self.book_identity, "Book Identity")
```

In `ApfStudioMainWindow._update_product_state`:

```python
playbooks_page = getattr(self, "_pages", {}).get(ApfCategory.PLAYBOOKS)
for name in ("playbook_playcall", "coverage_geometry", "book_identity"):
    panel = getattr(playbooks_page, name, None)
    if panel is not None:
        panel.set_busy(bool(self._workers))
```

Do not load the cloned folder into the old Studio session to implement the shortcut. `BookIdentityPanel.open_fine_tune` creates `BookContentSession` and the existing membership widget in `BookContentDialog`; book and MASTER lookups use names. The original project retains numeric asset indices, which cloning shifts. The cloned-folder editor therefore saves its own name/hash-bound recipe and builds the correct volume segments. Other Studio workspaces are not advertised as expanded-archive compatible.

### Required packaging and capability merge

Add this exact line beside the existing Book Identity module in `packaging/apf2k8-release-allowlist.txt` (and the combined distribution manifest if it packages this APF surface):

```text
mod_editor/apf_studio/book_content.py
```

Add this exact import to `PRODUCT_MODULES` in `packaging/check_apf2k8_mod_studio_runtime.py`:

```python
"mod_editor.apf_studio.book_content",
```

Add this documentation line to the APF allowlist:

```text
docs/mod_editor/apf_b661_cpu_book_control.md
```

Replace, by ID, the three existing capability objects for `apf2k8.playbooks.clone`, `.identity` and `.scheme_presets` with the complete objects in `docs/mod_editor/apf_b661_book_capabilities.json`. This is a merge fragment, not a new runtime dependency. The full temporary merge passes schema validation and every replacement row backend/evidence path exists. Full-registry file validation encounters a baseline missing `reports/assets/apf_ausb_inventory.json`; that existing evidence file must be restored during integration. Existing capability IDs and backend CLI commands remain valid; their scope now explains the GUI content continuation. `models.py` product notes were updated in owned code. Runtime status remains `not-tested`.

Do not package the native probe's private input or the commit bundle. `tools/apf_personnel_native_probe.py` and `reports/apf_b661/personnel_native.json` are development evidence only. Product dependencies are unchanged: Qt, existing archive/playbook tools and Python standard library. Unicorn is only needed to rerun the native proof.

### Integration acceptance

Run the standalone suites listed in `ASTRA_REPORT.md`, then the normal APF staged release/runtime gates after the allowlist/module/capability merge. In an offscreen main window, open Book Identity, inspect a source, choose a preset and verify that team/label/donor remain editable. Open **Edit books in Fine-tune** and verify the named session/dialog; building a clone redirects that button to the output folder and selects its new book name. Other project source state must not change.

The standalone tests exercise that actual dialog and widget with a synthetic two-volume cloned archive, including recipe save/reload and edited output verification. Full staged distribution checks and BASE/TU in-game observations remain for integration/witnessing.


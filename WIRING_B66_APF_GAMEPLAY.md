# Beta 66 job E integration handoff

Branch `astra/b66-apf-gameplay`. No `gui.py`, capability registry, packaging
allowlist or packaging check was edited. Apply these small hooks to job C's final
GUI. The writer, scalar project persistence, Undo, facade, build composition,
independent panel and tests are already implemented. This section supersedes
only conflicting historical instructions below.

## Field Art row

In `mod_editor/apf_studio/gui.py`, `FieldArtStudioPage.__init__`, immediately
after constructing/connecting/adding `self.editor`, insert:

```python
from .field_material_qt import FieldMaterialOpacityPanel
self.field_opacity = FieldMaterialOpacityPanel(facade, run_task)
self.field_opacity.modifiedChanged.connect(self.modifiedChanged)
layout.addWidget(self.field_opacity)
```

C can place the widget in its new Field Art expandable row/tab. Its own heading
is **Field overlay opacity**. In BOTH `FieldArtStudioPage.set_context` and
`FieldArtStudioPage.refresh`, immediately after `self.editor.set_context()`, add:

```python
self.field_opacity.set_context()
```

Remove the assertion in this page's prose that all SCNE records have no writer.
Only the eleven named alpha constants in entries 53/252/578/1333 are supported;
other scene data remains browse/export only. Keep materials unticked initially.
ADVANCED, off by default; runtime UNWITNESSED. Revert and modifiedChanged are
implemented in the panel. Recipe IDs are `field-material:<outer>`.

The build service applies this scalar writer AFTER other field texture writers,
composing into their rebuilt entry. Do not add a second whole-entry write to the
build output. `test_apf_field_material_project.py` exercises the real normal build
path, preserving an earlier writer's change inside that same IFF.

In `mod_editor/apf_studio/models.py`, `CAPABILITY_ACTION_BINDINGS`, add:

```python
"apf2k8.field_art.material_opacity": CapabilityActionBinding(
    "apf2k8.field_art.material_opacity",
    "field_art.material_opacity_editor",
    _actions(ApfProductAction.PREVIEW, ApfProductAction.REPLACE,
             ApfProductAction.REVERT),
    replace_method="apply_field_material",
    revert_method="revert",
    product_note=("Select named field alpha constants; preview source/staged values, "
                  "stage, revert, save/reopen, and build a copied game. "
                  "Token-preserving fixed-allocation H7A refit; rendering UNWITNESSED."),
),
```

`revert` takes the full recipe asset ID, as the new panel already supplies.
If job C routes capability cards by handler ID, map this handler to Field Art.
Do not route it to the PNG chooser.

## Wordmark region order

In `ApfTextLogoPanel.__init__`, immediately after `content.addLayout(selector)`
(the row with `self.slot` and `self.fit_mode`), insert:

```python
from .textlogo_authoring import WORDMARK_REGION_ORDERS, WORDMARK_REGION_NOTE
region_row = QHBoxLayout()
region_row.addWidget(QLabel("Region channels (3):"))
self.region_order = QComboBox()
for label, order in WORDMARK_REGION_ORDERS:
    self.region_order.addItem(label, order)
self.region_order.setToolTip(WORDMARK_REGION_NOTE)
region_row.addWidget(self.region_order, 1)
content.addLayout(region_row)
region_note = QLabel(WORDMARK_REGION_NOTE)
region_note.setWordWrap(True)
content.addWidget(region_note)
```

In `ApfTextLogoPanel._stage_path`, capture the order next to `fit_mode`, before
starting the worker:

```python
region_order = tuple(self.region_order.currentData() or (0, 1, 2))
```

Pass it to the existing preparation call:

```python
return prepare_wordmark_png(
    source_path, prepared_path, fit_mode=fit_mode, region_order=region_order
)
```

In `_preview_prepared_wordmark`, add this item to `summary_lines`:

```python
"Region channel order: " + "/".join(
    "RGB"[i] for i in getattr(prepared, "region_order", (0, 1, 2))
) + ". These are mask channels; six team palette-slot assignments are not proved.",
```

The existing confirmation, saved PNG payload, mip writer and build path remain
in use. Identity is the default. This permutes THREE channels. Do not offer six
regions or a dropdown promising arbitrary team palette colours. No second
textlogo mask exists in any of the 206 pinned packages; mapping selector tail
bytes to palette slots remains unproved. Paired crest layers are the available
six-region artwork surface, with a different in-game use.

## PS3 import

`ps3_roster_import_qt.py` already contains the working review control:
**Also apply team appearance (N teams)**, unchecked until reviewed. A user who
leaves it off must choose a raw Xbox roster to retain appearance from; players
still come from PS3. `gui.py` already instantiates `Ps3RosterImportPanel` on Saves.
No new page hook is needed. The chooser accepts `.ROS` containing PS3 layout;
already-Xbox roster input remains a typed refusal in this conversion action.
Custom logo/uniform texture files still need the existing texture import.

## Protected registry and package closure

Add the registry object in the next section to
`mod_editor/capabilities/registry.v1.json`. Update the existing
`apf2k8.logos_cards.textlogo_wordmarks` input constraints with the three-channel
permutation boundary above and its evidence with
`tests/mod_editor/test_apf_wordmark_regions.py`. Update
`apf2k8.players_rosters.ps3_roster_import` with the optional appearance review,
raw Xbox retention baseline and per-team/bank/selector receipt. Default receipt
conversion already transported PS3 selectors before this branch; do not call
this a newly discovered missing-selector byte copy.

Append these exact paths to `packaging/apf2k8-release-allowlist.txt` (and the
combined allowlist if it owns the APF runtime):

```text
mod_editor/core/apf_field_material_writer.py
mod_editor/apf_studio/field_material_service.py
mod_editor/apf_studio/field_material_qt.py
```

The witness tool/report are development evidence, not runtime dependencies.
If adding the registry row to the packaged registry requires its evidence
closure, also include `docs/research/apf_b66_gameplay_data.md` and the named
retail-free metadata report, or project that evidence into the shipped findings
as the packager normally does. Never include a retail roster, PE, PNG or volume.

In `packaging/check_apf2k8_mod_studio_runtime.py`, add to the existing module
import smoke list:

```python
"mod_editor.core.apf_field_material_writer",
"mod_editor.apf_studio.field_material_service",
"mod_editor.apf_studio.field_material_qt",
```

After merging C, offscreen smoke the two hooks with the exact source folder,
then run standalone `test_apf_studio_installer.py`, `test_apf_gui.py`,
`test_apf_field_art_gui.py`, `test_apf_field_material_project.py`,
`test_apf_textlogo_gui.py`, `test_apf_wordmark_regions.py`, and
`test_apf_ps3_roster_import_qt.py`; run the protected APF runtime checker. The
unmodified release allowlist cannot package these new imported modules.

Validation performed: a temporary release stage containing exactly the existing
allowlist plus the three modules above passes
`APF2K8_MOD_STUDIO_RUNTIME_PASS modules=133 capabilities=53`. The system Python
has Capstone only in the local user site; the successful isolated run explicitly
added that dependency directory to PYTHONPATH while leaving PYTHONNOUSERSITE=1.
The first isolated run without it correctly refused `No module named capstone`.
The checkout's unchanged installer suite therefore still needs both the listed
allowlist merge and its declared Capstone 5.0.7 dependency in the isolated runtime.
This temporary-stage check did not install the new registry row or render C's
future GUI hooks, and does not claim those steps are complete.

No Deep Threat patch registration or Export patch button is warranted. The
proved sites are evaluation branches, not an isolated animation repair.

## Registry object

```json
{
  "backend": {
    "command": "python3 -m mod_editor.apf_studio",
    "module": "mod_editor/core/apf_field_material_writer.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "docs/research/apf_b66_gameplay_data.md",
    "reports/apf_b66_gameplay_witness.json",
    "tests/mod_editor/test_apf_field_material_writer.py",
    "tests/mod_editor/test_apf_field_material_project.py"
  ],
  "game": "apf2k8_xbox360",
  "gui": {
    "default_enabled": false,
    "expose": true,
    "mode": "edit",
    "reason": "ADVANCED, off by default. Source/staged scalar preview, Stage, Revert, Undo, save/reopen and copied-game Build. All four retail entries refit and reparse; rendering UNWITNESSED."
  },
  "id": "apf2k8.field_art.material_opacity",
  "input_constraints": [
    "Entry 53, 252, 578 or 1333, pinned name and material/shader identities; one field SCNE in one warning-free H7A block.",
    "Select only field_grass, endzone_grass, ticks, chalk_lines, graphic_overlay_4/5/7/8/9, outside_grass_10/11. Alpha is finite 0..1; RGB stays (1,1,1).",
    "Self-relative bounded tables, 0x28 material stride; constants payload tint at +0x70 except material 1 at +0x100. Only selected alpha words may change.",
    "Token-preserving H7A must fit the fixed allocation and contain no length-greater-than-distance match. Nonzero tail bytes and changed sibling data are refused."
  ],
  "portme": [
    "Witness each scene, weather variant and composited texture on user-owned hardware. Material-to-visible-surface descriptions are not gameplay proof."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Distribute tooling, selectors, and user-authored PNGs only; each user rebuilds a copied 0A from their own retail game.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "status": "not-tested",
    "evidence": [],
    "scope": "UNWITNESSED rendering. Four retail entry refits and synthetic build composition reparse exactly."
  },
  "selectors": {
    "fields": [
      {
        "name": "outer_index",
        "allowed": "53, 252, 578, 1333",
        "required": true
      },
      {
        "name": "alphas",
        "allowed": "nonempty mapping of named material to alpha 0..1",
        "required": true
      }
    ],
    "notes": "Portable scalar JSON; no retail payload in project recipes. Optional material checkboxes start unticked."
  },
  "source_container": {
    "format": "IFF/H7A field SCNE in fixed 0A entry",
    "hash_pins": [
      "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
    ],
    "resource": "field scenes 53, 252, 578, 1333",
    "retail_file": "All-Pro Football 2K8 (USA)/0A"
  },
  "summary": "Stage alpha values for eleven named field materials in four scenes; reparse and refit H7A within the original allocation, composing with staged field textures.",
  "surface": "stadiums_fields",
  "title": "Field overlay opacity",
  "validation_command": "PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_field_material_project.py"
}
```

---

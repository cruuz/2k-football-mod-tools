# Beta 67 P4 wiring, as applied to the stack (2026-09-12)

Integration record for `astra/b67-p4-studio` (bundle commits `8ff0e514`, `ff8c3937`).
P4's own request text follows verbatim below; this header records what landed and what did not.

APPLIED
- `mod_editor/apf_studio/gui.py`: the `ApfPlaycallPanel` import now resolves to
  `playcalling_editor_qt.ApfPlayCallingEditor`; the workspace route accepts `cpu-playcalling`,
  `own-team-books`, `master-personnel` and `personnel-curves` alongside the existing names; and
  `ApfStudioMainWindow._build_complete` prefixes "Teams now owning a book: ..." and names
  `book-content-receipt.json` with the UNWITNESSED sentence. The panel construction, tab title and
  busy forwarding were already compatible and are unchanged.
- `mod_editor/apf_studio/models.py`: the four `CAPABILITY_ACTION_BINDINGS` entries, with
  `product_note` trimmed of the "P3 integration required" clause because P3 is now merged.
- `mod_editor/capabilities/registry.v1.json`: `apf2k8.playbooks.cpu_playcalling`,
  `own_team_books` and `personnel_curve_patch` inserted as supplied. `master_personnel` collided
  with the row P3 requested for the same id, so ONE row survives: P4's product-facing row (the tab
  renders those controls) with the evidence lists of both jobs merged.
- `packaging/apf2k8-release-allowlist.txt`: the four `mod_editor/apf_studio/playcalling_*.py`
  modules and `docs/mod_editor/apf_b67_play_calling_editor.md`. P3's four core modules were added by
  its own integration commit. `packaging/release-allowlist.txt` (2K5) is unchanged: it ships no APF
  workspace module.
- `packaging/check_apf2k8_mod_studio_runtime.py`: all eight import names added to `PRODUCT_MODULES`.

NOT APPLIED, with the reason
- `docs/mod_editor/apf_b67_playcalling_capabilities.json` stays in the tree as the merge input P4
  describes; only the canonical registry is a runtime dependency, so it is not allowlisted.

RECONCILED AFTERWARDS (see the follow-up commit "Beta 67: reconcile the Play Calling editor with the
delivered writers and model")
- `CloneRequest` is constructed with P3's fourth field, `clone_name`.
- `LINEUP_CALLERS` stays `"unclassified"`: P3's static audit leaves the resolver's callers
  unclassified and says to keep the beta 66.1 refusal, so the warning-only path stays off.
- `CURVE_PRESETS` replaced with the tuple shapes P3 accepts (offense five weights, defense three).
- `RATING_EXPLANATION`, `RATING_MAPPING` and the per-slider sentences rewritten to P3's corrected
  semantics: lower raw numbers weigh more.
- The tab degrades with a message instead of crashing when a contract call raises.

----- P4's WIRING.md text, verbatim -----

# Beta 67 P4: CPU Play Calling editor integration

This section supersedes the earlier CPU Play Calling page instructions below.
Branch: `astra/b67-p4-studio`, based on `653cb708`. Do not enable these proposed
capabilities until P3's core contract is merged and accepted. P4's fake model
and new writer functions exist only in `tests/mod_editor/test_apf_playcalling_editor_*.py`
and enter the product through `ApfStudioFacade(playcalling_backend=...)`.
The production code has no stand-in model. P4 proves the UI, replay, session,
synthetic archive transport and installer plumbing, not P3's selector math.

## gui.py: complete replacement blocks

In `mod_editor/apf_studio/gui.py`, replace the existing import of
`ApfPlaycallPanel` (line 198 at the base) with this complete line:

```python
from .playcalling_editor_qt import ApfPlayCallingEditor as ApfPlaycallPanel
```

The existing construction, signal forwarding, tab title, refresh calls and
busy-state forwarding already fit the new panel. Keep these existing blocks:

```python
self.playbook_playcall = ApfPlaycallPanel(facade, run_task) if category is ApfCategory.PLAYBOOKS else None
```

```python
tabs.addTab(self.playbook_playcall, "CPU Play Calling")
```

In `InspectorCategoryPage.open_workspace`, replace the current CPU route
branch with this complete block:

```python
elif normalized in {"cpu-audibles", "cpu-playcall", "cpu-playcalling", "te-bias",
                    "own-team-books", "master-personnel", "personnel-curves"} \
        and self.category is ApfCategory.PLAYBOOKS:
    target = self.workspace_tabs.indexOf(self.playbook_playcall)
```

In `ApfStudioMainWindow`, replace `_build_complete` in full with:

```python
def _build_complete(self, receipt: object) -> None:
    output = Path(receipt.output_game)
    detail = self._build_edit_detail(receipt)
    owners = tuple(getattr(receipt, "teams_now_own_books", ()))
    ownership = (
        "Teams now owning a book: " + ", ".join(owners) + ". "
        if owners else ""
    )
    self._last_detail = f"Build complete: {output.name}. {ownership}{detail}"
    self._update_product_state()
    QMessageBox.information(
        self,
        "Modded game folder built",
        f"Wrote:\n{output}\n\n"
        f"{ownership}{detail} The complete output was verified and your source stayed untouched.\n\n"
        "CPU Play Calling changes are recorded in book-content-receipt.json. Gameplay remains UNWITNESSED.\n\n"
        "Point Xenia at this folder. Rebuild into the same folder to keep that path.\n\n"
        "This folder contains your retail game data. Do not redistribute it; share the .apf2k8mod project instead.",
    )
```

No replacement Build dispatcher is needed: P4 edited the owned
`apf_studio/build.py`. It verifies existing edits first, invokes the book
finalizer inside the private staging directory, inserts clones in one core
batch, resolves content by filename hash, and publishes only after readback.
Its historical span verification is explicitly scoped to the phase before
play-calling finalization; `playcalling.verification` and the separate book
receipt describe the final phase. Existing edit receipt indices and the
returned `changed_outer_entries` are remapped after insertion.

## P3 acceptance boundary

The exact imported contract names are in `playcalling_service.Backend` and
`playcalling_patches`. Existing P2 helpers `CloneRequest`, `bind_roster`,
`clone_body`, `compile_unlock`, `build_new_folder`, `read_resource` and
`rebuild_resource` are reused. P4's finalizer calls `compile_unlock` and
`build_new_folder` once for the combined clone batch. It then writes the
reviewed final book contents by name. The intermediate clone copy lives in a
temporary sibling directory; all other output siblings are preserved.

P3 must support the full batch, including independently planned sides in one
session; P2's old `_requests` rejects repeated team indices even when one
request is offense and the other is defense. This is not papered over in P4.
Test combined offense/defense plans against P3 before release.

`PatchDocument.as_toml()` is used, matching P2's existing patch serializer.
Confirm that P3 keeps that serializer and accepts the following distance
presets before merging the curve capability. They are authored experiment
values, not a claimed native witness:

```python
CURVE_PRESETS = {
    "offense": (1.0, 0.35, 0.10, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "defense": (1.0, 0.35, 0.10, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
}
```

The existing installer now validates only canonical curve documents generated
by those profiles/presets, reparses installation/config bytes, retains P2's
rollback, and uses a distinct managed curve filename. Installing another
curve preset replaces the previous curve preset. Pass-fetch uses its existing
separate file. Both installs require explicit consent; no preset installs one.

The caller classification is intentionally fail-closed while P3 is absent.
In `mod_editor/apf_studio/playcalling_service.py`, replace the single constant
only after reading P3's caller proof. If all relevant callers are non-CPU:

```python
LINEUP_CALLERS = "non_cpu"
```

If P3 proves CPU reachability, use:

```python
LINEUP_CALLERS = "cpu"
```

Leaving `"unclassified"` keeps the refusal. All three paths are tested, with
coverage and retired names visible. This is an integration fact, never a
user-toggle that can bypass the guard. Reconcile `RATING_EXPLANATION` and
`RATING_MAPPING` with P3's exact report words at the same time. The current
mapping uses the merged P1 report (0–20 / 2–7 / 2–5 yard blending and urgency).
The requested higher-rating sentence is already visible. Per-team row weights
remain hidden; no unproved control was added.

## Capability/action bindings

After accepting the corresponding P3 writers, merge the four complete registry
objects below (also in `docs/mod_editor/apf_b67_playcalling_capabilities.json`)
into `mod_editor/capabilities/registry.v1.json`, sorted by ID. Their proposed
`offline-writer-proved` classification is conditional on P3 acceptance;
P4's synthetic contract tests alone are not proof of the new core writers.
Keep runtime `not-tested` and the visible UNWITNESSED wording.

In `mod_editor/apf_studio/models.py::CAPABILITY_ACTION_BINDINGS`, add:

```python
**{
    "apf2k8.playbooks." + feature: CapabilityActionBinding(
        "apf2k8.playbooks." + feature,
        "playbooks.cpu_playcalling",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.REPLACE,
                 ApfProductAction.REVERT, ApfProductAction.BUILD_COPY),
        replace_method="stage_playcalling",
        revert_method="revert",
        product_note=(
            "CPU Play Calling reviews named team books and stages an authored "
            "recipe with Undo, Save Project and copied-game Build. The tab "
            "predicts calls in a worker. P3 integration required; gameplay UNWITNESSED."
        ),
    )
    for feature in ("cpu_playcalling", "own_team_books", "master_personnel")
},
"apf2k8.playbooks.personnel_curve_patch": CapabilityActionBinding(
    "apf2k8.playbooks.personnel_curve_patch",
    "playbooks.personnel_curves",
    _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT,
             ApfProductAction.BUILD_COPY),
    one_shot_target="mod_editor.apf_studio.playcalling_patches:prepare",
    output_kind="authored-xenia-patch-toml",
    product_note=(
        "Experimental personnel curves prepare a canonical patch for the "
        "selected game version. The tab obtains consent before installation "
        "and enabling Xenia patches, and offers status and removal. "
        "Changes every book; gameplay UNWITNESSED."
    ),
),
```

These are workspace capabilities, not universal raw-asset Replace bindings.
The existing CPU-audibles and pass-fetch capability IDs remain valid; their
underlying controls/writers are retained.

<!-- B67_P4_REGISTRY_ROWS -->

```json
[
  {
    "backend": {
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --output <new-folder>",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "tests/mod_editor/test_apf_playcalling_editor_facade.py",
      "docs/mod_editor/apf_b67_play_calling_editor.md"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "CPU Play Calling tab with worker previews, reviewed edits and explicit staging. No option or patch is enabled by a preset. Merge only with the accepted P3 core writers."
    },
    "id": "apf2k8.playbooks.cpu_playcalling",
    "input_constraints": [
      "A loaded APF source and the integrated beta-67 P3 model/writers are required. No production substitutes are supplied.",
      "Book choices resolve by name; project replay checks reviewed before/after facts and refuses conflicts.",
      "MASTER and curve changes affect every book; personnel retirement with uncovered rows is refused until P3 classifies the lineup callers as non-CPU."
    ],
    "portme": [
      "Integrate and run P3 writer/model proofs before merging this proposed offline-writer-proved row; P4 synthetic contract tests alone do not prove those writers.",
      "Keep gameplay UNWITNESSED until Noah observes edited calls in the game."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "status": "not-tested",
      "scope": "UNWITNESSED. P4 proves UI, project/undo, synthetic archive composition and installer plumbing using injected test contract modules. Real P3 integration and gameplay require separate acceptance.",
      "evidence": []
    },
    "selectors": {
      "fields": [
        {
          "name": "team_and_book",
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Per-team call preview and staged formation ratings, play ratings, personnel, removals, tendency and audibles. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "CPU Play Calling editor",
    "validation_command": "python3 -m tests.mod_editor.test_apf_playcalling_editor_facade"
  },
  {
    "backend": {
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --output <new-folder>",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "tests/mod_editor/test_apf_playcalling_editor_build.py",
      "docs/mod_editor/apf_b67_play_calling_editor.md"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "CPU Play Calling tab with worker previews, reviewed edits and explicit staging. No option or patch is enabled by a preset. Merge only with the accepted P3 core writers."
    },
    "id": "apf2k8.playbooks.own_team_books",
    "input_constraints": [
      "A loaded APF source and the integrated beta-67 P3 model/writers are required. No production substitutes are supplied.",
      "Book choices resolve by name; project replay checks reviewed before/after facts and refuses conflicts.",
      "MASTER and curve changes affect every book; personnel retirement with uncovered rows is refused until P3 classifies the lineup callers as non-CPU."
    ],
    "portme": [
      "Integrate and run P3 writer/model proofs before merging this proposed offline-writer-proved row; P4 synthetic contract tests alone do not prove those writers.",
      "Keep gameplay UNWITNESSED until Noah observes edited calls in the game."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "status": "not-tested",
      "scope": "UNWITNESSED. P4 proves UI, project/undo, synthetic archive composition and installer plumbing using injected test contract modules. Real P3 integration and gameplay require separate acceptance.",
      "evidence": []
    },
    "selectors": {
      "fields": [
        {
          "name": "team_and_book",
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Review per-team clone assignments and insert the batch before resolving final book content by name. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "Give teams their own books",
    "validation_command": "python3 -m tests.mod_editor.test_apf_playcalling_editor_build"
  },
  {
    "backend": {
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --output <new-folder>",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "tests/mod_editor/test_apf_playcalling_editor_qt.py",
      "docs/mod_editor/apf_b67_play_calling_editor.md"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "CPU Play Calling tab with worker previews, reviewed edits and explicit staging. No option or patch is enabled by a preset. Merge only with the accepted P3 core writers."
    },
    "id": "apf2k8.playbooks.master_personnel",
    "input_constraints": [
      "A loaded APF source and the integrated beta-67 P3 model/writers are required. No production substitutes are supplied.",
      "Book choices resolve by name; project replay checks reviewed before/after facts and refuses conflicts.",
      "MASTER and curve changes affect every book; personnel retirement with uncovered rows is refused until P3 classifies the lineup callers as non-CPU."
    ],
    "portme": [
      "Integrate and run P3 writer/model proofs before merging this proposed offline-writer-proved row; P4 synthetic contract tests alone do not prove those writers.",
      "Keep gameplay UNWITNESSED until Noah observes edited calls in the game."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "status": "not-tested",
      "scope": "UNWITNESSED. P4 proves UI, project/undo, synthetic archive composition and installer plumbing using injected test contract modules. Real P3 integration and gameplay require separate acceptance.",
      "evidence": []
    },
    "selectors": {
      "fields": [
        {
          "name": "team_and_book",
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Edit category rows and eleven personnel roles across every book, including the defensive 5-2 row-13 fix. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "MASTER personnel (EXPERIMENTAL)",
    "validation_command": "python3 -m tests.mod_editor.test_apf_playcalling_editor_qt"
  },
  {
    "backend": {
      "module": "mod_editor/apf_studio/playcalling_patches.py",
      "command": "python3 -m mod_editor.apf_studio.playcalling_patches --profile <base|tu1> --side <offense|defense> --output <new.patch.toml>",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "tests/mod_editor/test_apf_playcalling_editor_patches.py",
      "docs/mod_editor/apf_b67_play_calling_editor.md"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "CPU Play Calling tab with worker previews, reviewed edits and explicit staging. No option or patch is enabled by a preset. Merge only with the accepted P3 core writers."
    },
    "id": "apf2k8.playbooks.personnel_curve_patch",
    "input_constraints": [
      "A loaded APF source and the integrated beta-67 P3 model/writers are required. No production substitutes are supplied.",
      "Book choices resolve by name; project replay checks reviewed before/after facts and refuses conflicts.",
      "MASTER and curve changes affect every book; personnel retirement with uncovered rows is refused until P3 classifies the lineup callers as non-CPU."
    ],
    "portme": [
      "Integrate and run P3 writer/model proofs before merging this proposed offline-writer-proved row; P4 synthetic contract tests alone do not prove those writers.",
      "Keep gameplay UNWITNESSED until Noah observes edited calls in the game."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "status": "not-tested",
      "scope": "UNWITNESSED. P4 proves UI, project/undo, synthetic archive composition and installer plumbing using injected test contract modules. Real P3 integration and gameplay require separate acceptance.",
      "evidence": []
    },
    "selectors": {
      "fields": [
        {
          "name": "team_and_book",
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Prepare, consent to, install, check and remove offense or defense personnel curve presets through the Xenia installer. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "Personnel curve presets (EXPERIMENTAL)",
    "validation_command": "python3 -m tests.mod_editor.test_apf_playcalling_editor_patches"
  }
]
```

## Release allowlists and runtime imports

Add these lines to `packaging/apf2k8-release-allowlist.txt` and to the combined
`packaging/release-allowlist.txt` if that product ships APF workspaces:

```text
mod_editor/apf_studio/playcalling_service.py
mod_editor/apf_studio/playcalling_editor_qt.py
mod_editor/apf_studio/playcalling_build.py
mod_editor/apf_studio/playcalling_patches.py
docs/mod_editor/apf_b67_play_calling_editor.md
```

P3's runtime dependencies must also be allowlisted by its integration:

```text
mod_editor/core/apf2k8_playcall_model.py
mod_editor/core/apf2k8_master_writer.py
mod_editor/core/apf2k8_team_tendency.py
mod_editor/core/apf2k8_playcall_curves_patch.py
```

Retain the already shipped SPLB writer, book clone/identity, audibles,
pass-fetch writer, legacy `playbook_playcall_qt.py`, launcher, session,
project, facade and build modules. The capability JSON is a merge input;
only the canonical merged registry is a runtime dependency. Test modules,
synthetic replay fixtures, work reports and game data are not runtime assets.

Add these import names to the protected APF runtime check's `PRODUCT_MODULES`:

```python
"mod_editor.apf_studio.playcalling_service",
"mod_editor.apf_studio.playcalling_editor_qt",
"mod_editor.apf_studio.playcalling_build",
"mod_editor.apf_studio.playcalling_patches",
"mod_editor.core.apf2k8_playcall_model",
"mod_editor.core.apf2k8_master_writer",
"mod_editor.core.apf2k8_team_tendency",
"mod_editor.core.apf2k8_playcall_curves_patch",
```

Run after integration (Qt is offscreen in the test modules):

```sh
python3 -m tests.mod_editor.test_apf_playcalling_editor_facade
python3 -m tests.mod_editor.test_apf_playcalling_editor_qt
python3 -m tests.mod_editor.test_apf_playcalling_editor_build
python3 -m tests.mod_editor.test_apf_playcalling_editor_patches
python3 tools/apf_gui_replay_offscreen.py --playcalling-contract-only --receipt /tmp/b67-p4-replay.json
```

Then run P3's standalone core tests and a real-source preview/build through
the wired tab, including both ownership sides together, USER/global donors,
MASTER plus other project edits, and P2 installer acceptance of real curve
TOML. Inspect the two build receipts and the ownership completion message.
Run the registry/release/runtime gates against the integrated staged product.
The baseline canonical registry references missing `docs/research/apf_audio.md`
in this checkout, so its full file-check gate needs that existing closure
repaired by integration; P4 does not edit that protected registry.

---


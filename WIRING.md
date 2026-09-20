# b72-a3 integration wiring

The Studio action is implemented directly in
`mod_editor/apf_studio/save_playbooks_qt.py`, in
`SavePlaybookAssignmentsPanel.__init__`, `_write_label_type`, and
`_update_enabled`. No main-window or protected GUI change is needed to use
the button. The capability card registration below is an integration follow-up.

The context file protects capability registry/release-gate files. They were
not edited. Apply these concrete integration changes:

1. Append the complete row in `reports/b72_a3/capability.json` to
   `mod_editor/capabilities/registry.v1.json`'s `capabilities` array, then keep
   the registry's usual ordering. This adds **one** capability, no removals.
   The exact insertion can be applied with:

   ```python
   import json
   from pathlib import Path

   path = Path("mod_editor/capabilities/registry.v1.json")
   registry = json.loads(path.read_text(encoding="utf-8"))
   row = json.loads(Path("reports/b72_a3/capability.json").read_text(encoding="utf-8"))
   assert all(existing["id"] != row["id"] for existing in registry["capabilities"])
   registry["capabilities"].append(row)
   registry["capabilities"].sort(key=lambda item: item["id"])
   path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
   ```

2. Add this documentation path to `packaging/apf2k8-release-allowlist.txt`:

   ```text
   docs/mod_editor/apf_saved_book_types.md
   ```

   All changed production modules and their existing strict-reader imports are
   already allowlisted. The two probe/benchmark scripts are developer tools,
   not Studio runtime dependencies, and need not ship. Do not ship the fixtures.

3. In `mod_editor/apf_studio/models.py`, add this dictionary entry beside
   `apf2k8.playbooks.identity` in `CAPABILITY_ACTION_BINDINGS` (the existing
   binding table, private name if renamed by another integration):

   ```python
   "apf2k8.playbooks.saved_label_type": CapabilityActionBinding(
       "apf2k8.playbooks.saved_label_type",
       "playbooks.saved_label_type",
       _actions(ApfProductAction.PREVIEW, ApfProductAction.BUILD_COPY),
       one_shot_target="mod_editor.apf_studio.save_playbooks:write_label_type",
       output_kind="copied_xbox_roster_payload_with_receipt",
       product_note=(
           "Save Assignments > Write a label's book type requires a raw roster, "
           "an installed same-side book and explicit confirmation. Only one "
           "type pointer changes. In-game behavior remains UNWITNESSED."
       ),
   ),
   ```

   This card binding and the protected registry row should land together. The
   button itself is already usable through the Save Assignments tab.

4. Increase the shared registry-count expectations by one in the protected
   runtime/packaging gates where pinned:
   `packaging/check_2k5_mod_studio_runtime.py` (two sites),
   `tests/mod_editor/test_phase1_packaging.py`,
   `packaging/check_apf2k8_mod_studio_runtime.py`, and
   `tests/mod_editor/test_apf_studio_installer.py`.
   Also increase the APF-only row/card totals by one (73 to 74 in the supplied
   checkout) and add `apf2k8.playbooks.saved_label_type` to `expected_editable`
   in the APF runtime check. The shared count there is 176 before this row.
   Recalculate after other integrated additions instead of pinning a stale
   total from this branch.

5. Run `python3 packaging/repin.py --apply` and the registry/release checks
   after those integration edits. This job's production changes needed zero
   pin updates. `tools/apf_h7a_optimal` remains 0755.

6. Apply only this job's two changelog bullets if integrating over the newer
   supplied checkout. The deliverable branch is based on the requested
   `088e3f41`; the worktree itself was supplied at `6944f5626`.

The experimental action is off in every preset. In-game state remains
UNWITNESSED. No converter, season/franchise feature, VIP or auto-sub work is
part of this integration.

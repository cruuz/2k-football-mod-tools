# Beta 69 J2: checked Models edits in projects

Branch: `astra/b69-j2-models`. Baseline: `922c009d`. Read `ASTRA_CONTEXT.md`,
triage rows 3/7/8 and the reinforcing row 9 DM, and
`ASTRA_B661_MODELS_REPORT.md`. **All in-game outcomes are UNWITNESSED.**

## Delivered

Models has **Add model edit to project** after a passing geometry or paired
geometry/skeleton check. It records one replaceable edit per model set and keeps
the quick **Make disc with this model** path, labelled as using the same model
writer. The displayed disc byte count now measures the packed resource changes;
the old `CompiledModelImport.changed_bytes` counts decoded geometry bytes and
was incorrectly labelled as on-disc bytes. The original check remains in the
record alongside the actual packed count.

The default facade creates `ModelProjectSession`, a small extension of the
existing session in the granted Models module namespace. Existing explicitly
supplied session factories keep their previous behavior. This avoids editing
the ungranted session/archive owners while reusing their archive validation,
atomic publication, texture staging and Undo transactions.

A `.2k5mod` stores one hashed `model-edits.json` member. Each record contains the
glTF/GLB paths and SHA-256s, every external buffer and export-manifest hash,
import options, check metadata, actual changed-byte count, and sparse compiled
changes for each resource. Only changed byte runs are stored; original packed
resources and exported glTF/buffer payloads are not archived. Skeleton check
metadata strips the old receipt's `before_hex`/`after_hex` dumps. The base
archive still uses its established reader/writer and all legacy projects take
the original loading path.

Opening rechecks source-file hashes and reconstructs/reparses the saved compiled
changes against the user's source resources. A missing or changed file explicitly
**refuses re-checking with its full path**, while the project opens with an inline
warning and keeps the last checked compiled bytes buildable. Adding a stale check
refuses. This resolves the requested distinction between authoring-input validity
and a portable already-compiled project: reopening does not discard a usable
compiled edit just because its Blender folder moved. No file is silently relinked
and changed files are never silently adopted. An unchanged SHA-256 identifies the
same previously checked glTF and buffers, so reopening does not rerun Blender or
recompress an unchanged authoring snapshot.

Reconstruction validates source and replacement hashes, wrapper identity,
decoded changes, vertex/attribute bounds, finite positions and the permitted
geometry lanes. Skeleton binds are reparsed against the checked axial target;
parent/name/rotation/weight/morph/topology bytes remain outside writable lanes.
SKEL must remain identical. Consistently rehashed edits outside the permitted
lanes are also refused. Both ordinary Undo and Undo of Revert All include model
edits in the same ordered history as texture edits.

The visual backend accepts `model_edit` recipes, pins the compiled recipe rather
than the glTF files, prepares the saved model spans, and includes model check and
source provenance in its build artifacts/receipts. `nfl2k5_build_service.py`
requires **no changes**: it already handles the canonical `recipe` field and
its existing publication/receipt-verification path accepts these prepared edits.

The exact protected shell/build patch is in `WIRING.md` and
`docs/mod_editor/nfl2k5_model_project_wiring.patch`. It updates the actual bottom
bar/recovery dirty state, lists model summaries in Build & Share, puts model rows
in the combined gameplay receipt and adds early resource-conflict feedback.
The patch was replayed in memory; Claude must apply it and the two-file release
allowlist update. Registry: extend the existing Models row, **0 added rows**.

## Pair rule and next steps

The refusal now names the missing, unedited or mismatched file and gives:
**Blender: File > Export > glTF 2.0 > Include > Data > Custom Properties**.
It explains that both LODs must come from one export and that **Geometry only >
Check model** accepts a single LOD mesh edit while preserving the other LOD and
both skeletons. An unedited head is expected and explicitly retained; it is not
mistaken for the missing body LOD. Models user text drops the exception-class
prefix.

No new safe single-LOD *bone-length* case was found. The low and high models have
separate 112-byte bind records and high derived pivots. Their shared SKEL stores
directions, not lengths; changing one bind set cannot update the other at an LOD
transition. The native paired gate remains intact, including the 95%-105% axial
bound, admitted limbs, source pins and native pose comparisons. Single-LOD
geometry with unchanged skeletons is accepted and exercised by the project replay.

## Writer order and shared spans

PROVED by the current writer code and read-only resource inventory:

| Resource | Pack-relative span, wrapper included | Project ownership |
| --- | --- | --- |
| lo_body SCNE 3/113 | `0:0x1a0850`, 135,840 bytes | geometry; paired bind change |
| hi_body SCNE 3/114 | `0:0x1c1af0`, 202,272 bytes | geometry; paired bind/derived-pivot change |
| hi_head SCNE 3/115 | `0:0x1f3110`, 270,368 bytes | geometry; retained head bind guard |
| SKEL 3/116 | `0:0x235130`, 512 bytes | retained canonical-direction guard |

- Uniform torso/sleeve/pants and equipment artwork own TSET resources; live
  helmet/number/face artwork owns TXTR resources. These are separate from the
  four player resources above. Uniform equipment uses its existing grouped
  TSET compiler, preserving neighboring edits. Body SCNE 3/113 has no embedded
  textures; the player body check does not pretend to import separate artwork.
- Bump maps own uniform/global TXTR spans, including the seven shared shoe maps.
  Bump strength owns executable material values. They do not overwrite the
  player SCNE/SKEL spans.
- Both Guardian C cap and Guardian B overlay require their pinned original
  **3/113 and 3/115** spans. C additionally writes TXTR 4002/12. B rebuilds outer
  3 and appends its texture while preserving other chunks. A staged model owning
  either shared scene is refused **before the project disc is built**, with the
  names and the instruction to deselect Guardian or remove the model edit.
  Neither order would safely compose their fixed-retail geometry writers.
- The current hi-res catalog has **zero outer-3 targets**. Its TXTR/TSET and
  midfield SCNE resources therefore do not collide with the player set. For
  arbitrary Models scenes, selected hi-res `(outer, chunk)` identities are
  checked before building; a shared retail-only hi-res target is refused.
- Other project writers sharing an exact SCNE span (for example scene geometry
  or embedded artwork) are prepared first. The model change is merged in decoded
  space: disjoint changes and identical overlapping values survive; different
  values at the same decoded byte refuse with both selectors. The resulting
  scene is refit once with `nfl_vc_lz_fill`, wrapper/scratch retained, and decoded
  again. Partial-resource overlaps refuse rather than guessing layout ownership.
- The project service writes and verifies those resources, then the central
  `build_with_project` runs gameplay/archive-growth passes against its private
  project copy. Later writers use that copy's directory/entry mappings. Final
  publication remains owned by the existing central build path. Ordinary XBE
  gameplay edits are disjoint; Guardian is the explicit exception above.

## PROVED and limits

- Materialized **854,016-byte compact XISO** round trips use the real low/high
  body, head and SKEL resources read from the user's retail archive at test time.
  Tests pin the compact pack/inventory and synthetic XBE identities; no model
  compiler, XDVDFS parser, span writer, whole-disc union verifier, receipt verifier
  or service publisher is mocked. Project-only geometry and +1% paired forearm
  skeleton builds are each byte-identical to their quick paths. The geometry
  build works after deleting the external glTF buffer. The full historical
  skeleton receipt reconstruction also passes. Exact hashes are in
  `docs/mod_editor/nfl2k5_model_project_proof.json`.
- Facade tests save/reopen the actual archive, name stale paths, reject stale
  staging and tampered compiled bytes, count the set, and exercise mixed
  texture/model Undo including Undo of Revert All.
- Offscreen tests execute the real Models page and the exact shell handoff,
  observe the actual **1 project edit** bottom bar, Undo, re-add and build through
  `Nfl2k5BuildService`. The Build & Share confirmation names the model.
- The combined-plan handoff test runs the real project service before a
  **synthetic gameplay XBE-byte writer**, preserving all model spans and recording
  model rows in the combined receipt. This proves the orchestration order; it
  is not an actual retail gameplay-patch witness. Existing visual union and
  build-service suites also pass.
- The existing native skeleton suite passes all seven tests, including direct
  paired imports and actual Blender GLB forearm/thigh witnesses. No native
  tolerance or pair requirement was relaxed.

HYPOTHESIS / not measured here: full-size retail disc performance, every possible
mixed artwork/equipment/gameplay selection, compression fit for arbitrary user
models, and final packaged Windows behavior. Root free space was **79 GiB**, below
the mandated 80 GiB large-write floor; no full-size retail disc was copied and no
large scratch disc was created. Compact fixtures and temporary exports were
removed by their test cleanups. The 854,016-byte materialized proof must not be
reported as a full-size retail image build.

Every in-game outcome remains **UNWITNESSED**: idle/running/passing/catching/
tackling, both camera LODs, varied body profiles, ball/helmet attachment placement,
texture appearance, collision and original hardware. Noah/maumau78 should reopen
and build a real combined gameplay + texture + model project, then witness these
behaviors and retain the build receipts.

## Witness and changelog

The RC94/beta-69 bullets quote maumau78's row 8 project complaint and row 9 private
question, row 7 skeleton refusal, and row 3: "gameplay mods and 3D model edit" in
"just few minutes compared to 50 minutes of the previuos build". Row 3 is the
second beta-68 build-speed witness alongside Coach Edwards, and is recorded as a
build-time witness only. Noah's public/private commitment is addressed by the
project path, not by telling the reporter to keep using the isolated quick disc.

## Functions touched

- `mod_editor/gui/models_panel_qt.py`: `_Task.run`, `ModelsPanel.__init__`, `ModelsPanel._build`, `ModelsPanel._invalidate_import`, `ModelsPanel._refresh`, `ModelsPanel._selected`, `ModelsPanel.compile_edited`, `ModelsPanel.compile_edited.operation`, `ModelsPanel.compile_edited.done`, `ModelsPanel.compile_body_set`, `ModelsPanel.compile_body_set.operation`, `ModelsPanel.compile_body_set.done`, `ModelsPanel._add_to_project`, `ModelsPanel._add_to_project.operation`, `ModelsPanel._add_to_project.done`, `import_report_text`, `set_report_text`
- `mod_editor/core/nfl2k5_model_skeleton.py`: `pair_error`, `compile_set`
- `tools/nfl2k5_visual_mod_project.py`: `validate_edit_shape`, `read_project`, `project_asset_paths`, `prepare_project`
- `mod_editor/core/nfl2k5_build_service.py`: `NONE`
- `mod_editor/studio/facade.py`: `Nfl2k5StudioFacade.__init__`, `Nfl2k5StudioFacade.stage_model_edit`, `Nfl2k5StudioFacade.model_project_plan`, `Nfl2k5StudioFacade._load_project_candidate`
- `mod_editor/core/nfl2k5_model_project.py`: `sha`, `canonical`, `require`, `changed_runs`, `apply_runs`, `source_files`, `recheck_files`, `_resource`, `checked_disc_summary`, `make_record`, `make_record.check_metadata`, `validate_record`, `_validate_model_lanes`, `_validate_model_lanes.allow`, `restore_member`, `merge_decoded`, `prepare_project_models`, `plan_rows`, `validate_build_plan`
- `mod_editor/core/nfl2k5_model_project_session.py`: `_copy_archive`, `_read_models`, `ModelProjectSession.__init__`, `ModelProjectSession.model_records`, `ModelProjectSession.modified_count`, `ModelProjectSession._manifest_document`, `ModelProjectSession.stage_model`, `ModelProjectSession.undo`, `ModelProjectSession.revert_all`, `ModelProjectSession.canonical_document`, `ModelProjectSession.save_shareable_project`, `ModelProjectSession.load_shareable_project`

The shared J1 file `tools/nfl2k5_visual_mod_project.py` changes only
`validate_edit_shape`, `read_project`, `project_asset_paths`, `prepare_project`,
plus the model import and report-free-kind constant. No phase/error-surfacing,
`build`, receipt reader, `verify_written` or J1 migration code was changed.
`mod_editor/core/nfl2k5_build_service.py`: **no functions touched**.
Provider/runtime changes are source pins, including the one new backend module;
the exact backend closure grows from 271 to 272. No XBE writer/cave was changed.
Production source/cave manifest regeneration is still required after integration.

## Standalone verification

All commands below ran from the worktree root with plain `python3`. The complete
logs are retained under `reports/b69_j2/tests/`. The generated private inventory
is local metadata, not a committed retail fixture:

```sh
PYTHONPATH=. python3 tools/nfl_resource_scan.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --json reports/assets/nfl2k5_resource_chunks_v2.json
```

Inventory result: 4,323 outer entries; 86,882 resource chunks; 4,616 SCNE and one
SKEL. Native tests receive that path through `NFL2K5_ANIMATION_INVENTORY`.

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_model_project.py
```

```text
Ran 10 tests in 45.652s
OK
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_models_project_wiring.py
```

```text
Ran 2 tests in 11.770s
OK
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_models_panel_qt.py
```

```text
Ran 8 tests in 4.311s
OK
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_models_skeleton_wiring.py
```

```text
Ran 2 tests in 0.053s
OK
```

```sh
NFL2K5_ANIMATION_INVENTORY=reports/assets/nfl2k5_resource_chunks_v2.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_model_skeleton.py
```

```text
Ran 7 tests in 169.514s
OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_models.py
```

```text
Ran 37 tests in 54.194s
OK
```

```sh
PYTHONPATH=. python3 tools/test_nfl2k5_visual_mod_project.py
```

```text
Ran 46 tests in 2.360s
OK (skipped=10)
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_studio_qt_models.py
```

```text
Ran 0 tests in 0.000s
OK (skipped=1)
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_studio_facade.py
```

```text
Ran 11 tests in 0.022s
OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_build_service.py
```

```text
Ran 28 tests in 0.169s
OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_provider_integrity.py
```

```text
Ran 7 tests in 13.180s
OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_providers.py
```

```text
Ran 33 tests in 4.448s
OK
```

The ten visual-project skips name absent private team-identity, roster,
portrait and scorebug audits. The Studio view-model class skips because its
private uniform catalog report is absent; the actual shell/Models/footer replay
runs and passes in the new wiring suite. Initial failures exposed those missing
fixtures, an outdated synthetic skeleton GUI file lookup, and the backend closure
count. The tests now use precise private-input skips, a bounded mocked lookup for
the old synthetic GUI case, and the actual 272-file closure count. No writer
failure or native tolerance was waived.

`git apply --check docs/mod_editor/nfl2k5_model_project_wiring.patch` and
`git diff --check` pass. `python3 packaging/repin.py --apply` updates actual source
hashes, then is run once more immediately before the explicit-path commit. No
push, emulator, GUI display, audio or network operation was performed.

## Integration and reporter follow-up

Apply WIRING's protected shell/build patch, existing registry-row extension and
two release-allowlist paths. Regenerate source/cave metadata and run final release
and installer gates. These protected changes are pending integration, not silently
claimed as installed. The facade/project writer and Models button are directly
implemented. Ask maumau78 to stage his player set, see the project count, save and
reopen it, combine it with his real texture/gameplay edits, and build via Make disc
from project. Also check the named pair error using his reported one-LOD folder,
then test a properly paired skeleton export. Every played result still needs a
separate witness.

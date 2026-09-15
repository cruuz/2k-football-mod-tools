# Beta 70 T2 integration

Apply before release. The protected-file rule in `ASTRA_CONTEXT.md` leaves the
following integration changes to Claude. No new capability rows or presets:
**registry count delta 0**. No larger-allocation switch is shipped.

## Shared-owner coordination with T1

Keep T1's search bounds, offset-tier caching and Windows helper work. T2 changes
`nfl2k5_uniform_equipment_writer.py` only for `_striped_art`, `_quantize_art`,
the stripe palette floor, actual fit/colour reporting and returning already
compiled fit rows from `preflight_project_equipment`. `_compile_group` changes
are the quantizer call, stripe floor, measured retry colour count and receipt
fields. They do not replace the compressor or introduce another search pass.

`equipment_staging._checked_rows` compiles each complete physical group once,
including normal and mud. Preserve T1's cache in that call path. If T1 replaces
project-load preflight with a cache read, return these same measured rows from
the validated cache. Do not run another fit ladder for GUI captions.

## Project rows use the import/load measurements

In `mod_editor/studio/session.py`, `StudioSession.load_shareable_project`, change
the existing preflight call immediately after `try:` to assign its result:

```python
            equipment_fit_rows = preflight_project_equipment(self.cache.pack0, [
                (None, row.asset.asset_id, row.staged_path)
                for row in loaded.edits
                if getattr(row.asset, "kind", None) == "uniform_equipment_texture"
            ])
```

After the successful transaction and immediately before `return len(loaded.edits)`,
insert (retain its `loaded.cleanup()` finally):

```python
            from mod_editor.core.equipment_staging import _remember_fit
            _remember_fit(self, equipment_fit_rows)
```

This consumes the existing preflight result, with no second compilation. A failed
load never adopts the candidate session. Imported rows already populate the same
cache in the granted facade path. The key includes every staged equipment ID and
PNG hash; Undo, revert or another sibling edit cannot display a stale fit.

Replace `StudioMainWindow._refresh_build_includes` in
`mod_editor/gui/studio_qt.py` with:

```python
    def _refresh_build_includes(self, *, baseline=False):
        from tools.nfl2k5_visual_mod_project import ProjectEditTimeline
        from mod_editor.core.equipment_reporting import project_fit_labels
        session = getattr(self.facade, "_session", None)
        if getattr(self, "_build_includes_session", None) is not session:
            self._build_includes_session = session
            self._build_includes_timeline = ProjectEditTimeline()
            baseline = bool(session and getattr(session, "modified_count", 0))
        if not hasattr(self, "_build_includes_timeline"):
            self._build_includes_timeline = ProjectEditTimeline()
        try:
            document = session.canonical_document() if session and session.modified_count else {"edits": []}
            rows = self._build_includes_timeline.observe(document, baseline=baseline)
            fits = project_fit_labels(session) if session and any(
                e.get("kind") == "uniform_equipment_texture" for e in document["edits"]
            ) else {}
            labels = []
            for row in rows:
                edit = document["edits"][row["project_edit_index"]]
                label = row["label"]
                if edit.get("kind") == "uniform_equipment_texture":
                    label += "; " + fits.get(edit["asset_id"], "fit measurement unavailable; reimport to check")
                labels.append(label)
            text = "\n".join(labels)
        except Exception as exc:
            text = f"The project edit list could not be read: {exc}. Resolve this before building."
        self._build_includes_text = text
        if self._build_panel is not None:
            self._build_panel.project_includes_list.setPlainText(text)
```

## Verified build summary

In `mod_editor/core/nfl2k5_build_service.py`, add this default field to
`BuildResult`, after `stage_seconds`:

```python
    texture_summary: tuple[str, ...] = ()
```

Replace its `message` property with the following, merging T1's digit-warning
grouping into the `kept_retail` paragraph if that change lands first:

```python
    @property
    def message(self) -> str:
        if not self.kept_retail and not self.texture_summary:
            return ""
        lines = [f"Build complete: {self.output_xiso.name} is ready."]
        if self.kept_retail:
            rows = "; ".join(str(row.get("message", row.get("selector", ""))) for row in self.kept_retail)
            lines.append(f"Kept retail for {len(self.kept_retail)} uniform slots: {rows}")
        lines.extend(self.texture_summary)
        return "\n".join(lines)
```

In `_read_verified_result`, immediately before its final `return BuildResult`,
insert:

```python
        from mod_editor.core.equipment_reporting import verified_build_texture_lines
        texture_summary = verified_build_texture_lines(manifest)
```

Pass `texture_summary=texture_summary` to that returned `BuildResult`. In `build`,
pass `texture_summary=result.texture_summary` to the final `BuildResult` constructed
immediately before `BuildStage.COMPLETE`. This reads the verified per-span reports
before their staging directory is cleaned. It rechecks their hashes and never
recompiles. Equivalent equipment fits are grouped across packages; project rows
and per-span receipts keep the individual package identities. Stadium lines name
every selected occurrence from `compiled_textures`, after successful verification.

## Arm-family import action

The granted dialog module contains `ArmDigitImportDialog`. Arm digits are
`live_number_nameplate` assets, so the existing equipment-only branch would not
open that help. In `StudioMainWindow._replace_visual_asset`, immediately before
`fitted = self._fit_for_slot(...)`, insert:

```python
        if getattr(asset, "family", None) == "arm":
            from mod_editor.gui.equipment_texture_import_dialog import ArmDigitImportDialog
            dialog = ArmDigitImportDialog(asset, self)
            if dialog.exec_() != dialog.Accepted:
                return
```

This is an explicit user import action, not a load-path message box. The granted
dialog and FAQ explain that texture imports do not move model surfaces. The
normal equipment import result already displays its `EquipmentImportResult.message`
through the existing success handler, including fitted dimensions/colours and
normal/mud staging. No additional result dialog is needed.

## Compatibility entry points

The live facade already calls the new atomic staging owner. In the non-granted
`mod_editor/core/nfl2k5_equipment_import.py`, replace the bodies of the two public
staging/revert functions with these lazy forwards, retaining `EquipmentImportResult`,
scope helpers and `_consumer_receipt` in that module:

```python
def stage_equipment_import(session, asset, path, *, independent=None, scale=1, scope=None):
    from .equipment_staging import stage_equipment_import as stage
    return stage(session, asset, path, independent=independent, scale=scale, scope=scope)


def revert_equipment_import(session, asset):
    from .equipment_staging import revert_equipment_import as revert
    return revert(session, asset)
```

The structural assertion in `AppliedWiringTests.test_applied_shell_keeps_model_signal_and_inline_load_errors`
already accepts the lazy forward and follows it to the combined check before
`replace_batch`. Both legacy import and consumer suites have also been run in
separate Python processes with the exact staging/revert forwards installed in
memory: 13 and 19 tests pass, respectively. Their existing message contracts are
preserved. Logs have the `-forwarded.log` suffix. No further message-test edits
are needed.

## Registry and distribution

Add these exact paths to `packaging/release-allowlist.txt` near `equipment_palette.py`:

```text
mod_editor/core/equipment_staging.py
mod_editor/core/equipment_reporting.py
```

No new sealed compiler dependency is introduced: median cut stays inside the
already-pinned equipment writer; the stadium identity helper stays inside its
already-pinned writer. `providers.py` and the facade digest in
`packaging/check_2k5_mod_studio_runtime.py` contain only automatic repin updates.

In `mod_editor/capabilities/registry.v1.json`, update existing rows
`nfl2k5.textures.all_p8` and `nfl2k5.uniforms.all_visual`:

- In the existing equipment entry of the `input_constraints` array, replace only
  this stale sentence (preserve the rest of that entry, including the retail
  no-op, mip, wrapper and restored-project constraints):

```text
maumau78 reported a Style 6 Edit Player success and Bears in-game failure on beta 68; that report remains unresolved.
```

  with:

```text
maumau78 subsequently reported visibility after assigning both the normal and mud slots, while the artwork still looked buggy; this corrects the earlier single-slot guidance without establishing this change's in-game appearance.
```

- Append the following exact string as a new `input_constraints` array entry:

```text
Normal shoe, glove and pad imports stage the mud sibling where the catalog contains one, with combined fit checking and grouped revert. Explicit mud-only imports stay separate. maumau78 reported visibility only after assigning both slots and still reported buggy artwork. Bounded native cache fill and field binding distinguish normal/mud rows; the caller transports runtime player record +0x18 bit 28 even under dry weather inputs. The flag's gameplay lifecycle and this change's appearance remain UNWITNESSED. Equipment reports actual fitted dimensions and referenced colours across all mips. High-contrast bands retain a palette limit of at least 16; a smaller checked image can still lose detail. Larger archive allocation remains UNPROVED and is unavailable.
```

- Append that witness update to `runtime.scope`; retain the existing runtime
  status for unrelated features. Add the following evidence file paths to the
  existing evidence/test lists in each row:

```text
tests/mod_editor/test_b70_t2_equipment.py
tests/mod_editor/test_b70_t2_native.py
tests/mod_editor/test_b70_t2_reporting.py
reports/b70_t2/sock-quality.json
reports/b70_t2/grown-loader.json
reports/b70_t2/growth-audit.json
```

In `nfl2k5.uniforms.all_visual`, replace the entire stale `input_constraints`
entry beginning `The Stadium texture route accepts an exact 64x64 RGBA8 PNG only`
with:

```text
The Stadium texture route accepts an exact-dimension RGBA8 PNG for a reviewed P8 embedded texture exposed as editable by the Stadiums delegate. Every material linked to that occurrence changes together. Fixed-allocation compression overflow is refused; geometry, UVs, shaders and collision are unchanged.
```

For `nfl2k5.uniforms.all_visual` and
`nfl2k5.stadiums_fields.blender_textures`, append this constraint and add
`tests/mod_editor/test_b70_t2_stadium.py` plus `reports/b70_t2/stadium-banners.json`
to the evidence lists:

```text
Stadium imports edit the selected SCNE occurrence only. Venue/time/weather labels resolve the archive filename CRC; all other variants retain their own textures. The 18 Chicago/Cincinnati package traces and bounded native material relocations bind their own banner_corp occurrence. Retail banner writes reparse and close/reopen exactly. The reporter's played venue is unknown; in-game banner appearance remains UNWITNESSED. Build receipts identify the package, SCNE, embedded texture and linked material names.
```

Do not claim the original reporter selected Cincinnati merely because his screen
said Texture 29; many packages have that index. Do not mark every banner variant
modified when only one was staged. No automatic cross-venue/condition overwrite
is requested by this fix.

After wiring, run `python3 packaging/repin.py --apply` and the standalone reporting,
equipment, stadium, facade, build-service and provider suites. No XBE bytes,
caves or runtime allocations were patched. T2 adds zero cave reservations. Claude
should regenerate the shared cave manifest after integration as required by
ASTRA_CONTEXT.md; preserve every other job's reservations.

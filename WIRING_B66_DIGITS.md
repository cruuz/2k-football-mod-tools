## Beta 66 job G: Coach Edwards number sheets (RC90)

Status: core implemented and tested. Apply this section after all earlier wiring. No protected file was changed by this job. The existing `nfl2k5.uniforms.all_visual` capability owns this import repair; it is not a gameplay preset or a new capability.

Apply the exact patch below from the repository root (`git apply --check tests/fixtures/coach_digit_wiring.patch`, then `git apply tests/fixtures/coach_digit_wiring.patch`). The standalone offscreen test applies it in memory and executes its methods. Do not omit the facade change: it obtains the current edited torso's dominant opaque colour under the same source-session lock. The 24px 57 comparison is an estimate because actual screen size depends on camera, mesh and projection; no fixed game screen size was established.

Insertion points:

* `studio_qt.py`, `_build_uniform_page`: immediately after `team_kit_layout.addLayout(team_kit_actions)`, add the complete four-line `number_help` block in the patch.
* `_review_digit_sheet_preview`: replace the note and OK caption exactly as shown. The core PNG already includes per-row KEPT RETAIL badges, build and retail at each level, and build/retail 57 composites. Do not draw a second overlay or resize the PNG.
* `_choose_digit_sheet_import`: immediately after the orientation assignment, insert the complete registration chooser block; pass its result to the splitter in `prepare`. PNG metadata preserves the choice through the Team Kit and project input snapshot. All ten slots are staged together after review; the count describes how many authored digits will actually be written.
* `mod_editor/studio/facade.py`: replace `preview_digit_sheet` with the complete function printed below. This is a coordinated integration change, not a protected edit made here.
* `packaging/release-allowlist.txt`: insert the new digit-art core module after digit-preview. This is required for a release that imports the module.
* `packaging/check_2k5_mod_studio_runtime.py`: insert its import smoke check after digit-preview.

```diff
--- a/mod_editor/gui/studio_qt.py
+++ b/mod_editor/gui/studio_qt.py
@@ -3536,6 +3536,10 @@
         team_kit_actions.addWidget(self.import_digit_sheet_button)
         team_kit_actions.addStretch(1)
         team_kit_layout.addLayout(team_kit_actions)
+        number_help = QLabel(SHEET_HELP, team_kit)
+        number_help.setWordWrap(True)
+        number_help.setObjectName("metadataText")
+        team_kit_layout.addWidget(number_help)
         detail_layout.addWidget(team_kit)

         split = QHBoxLayout()
@@ -7278,9 +7282,10 @@
         dialog.setWindowTitle("Number sheet: encoded game preview")
         layout = QVBoxLayout(dialog)
         note = QLabel(
-            "EXPERIMENTAL / UNWITNESSED. These are the saved number textures at "
-            "small sizes. The game adds jersey lighting and chooses detail by camera distance. "
-            "Check every digit and the size notes before importing.", dialog,
+            "Each row shows the build result above the retail digit at the same size. "
+            "A KEPT RETAIL badge means that slot will use its original number. "
+            "The 57 comparison uses the jersey base colour at an estimated screen size. "
+            "The game adds lighting and camera-dependent detail. In-game appearance is unwitnessed.", dialog,
         )
         note.setWordWrap(True)
         layout.addWidget(note)
@@ -7299,7 +7304,7 @@
         details.setMaximumHeight(160)
         layout.addWidget(details)
         buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
-        buttons.button(QDialogButtonBox.Ok).setText("Import all ten digits")
+        buttons.button(QDialogButtonBox.Ok).setText(preview.import_button_text)
         buttons.accepted.connect(dialog.accept)
         buttons.rejected.connect(dialog.reject)
         layout.addWidget(buttons)
@@ -7347,6 +7352,15 @@
         if not accepted:
             return
         orientation = dict(SHEET_LAYOUTS).get(str(layout_label), SHEET_LAYOUTS[0][1])
+        from mod_editor.core.nfl2k5_digit_art import REGISTRATION_CHOICES
+        registration_label, accepted = QInputDialog.getItem(
+            self, "Number size", "Match retail size keeps the glyph inside the original number box. "
+            "As authored keeps your placement and can extend beyond the number mesh.",
+            [row[0] for row in REGISTRATION_CHOICES], 0, False,
+        )
+        if not accepted:
+            return
+        registration = dict(REGISTRATION_CHOICES)[str(registration_label)]
         filename, _ = QFileDialog.getOpenFileName(
             self,
             f"Choose the {label.lower()} 0-9 sheet (ten equal cells)",
@@ -7368,7 +7382,7 @@
         prepared_outputs = ()

         def prepare(progress: ProgressSink) -> object:
-            outputs = split_digit_sheet(source, targets, orientation=orientation)
+            outputs = split_digit_sheet(source, targets, orientation=orientation, registration=registration)
             preview = self.facade.preview_digit_sheet(outputs, progress)
             return outputs, preview

--- a/mod_editor/studio/facade.py
+++ b/mod_editor/studio/facade.py
@@ -3306,13 +3306,21 @@
             return service.import_edited(source, progress=progress)

     def preview_digit_sheet(self, outputs: Sequence[object], progress: ProgressSink) -> object:
-        """Encode a frozen sheet against the active source, without staging it."""
-        from mod_editor.core.nfl2k5_digit_preview import preview_digit_sheet
+        """Encode the frozen sheet and current jersey colour under the source lock."""
+        from mod_editor.core.nfl2k5_digit_preview import preview_digit_sheet, jersey_preview_colour

         with self._lock:
             session = self._require_session()
             targets = tuple(self.uniform_catalog.get_asset(output.asset_id) for output in outputs)
-            return preview_digit_sheet(session.cache.pack0, targets, outputs, progress)
+            if not targets:
+                raise ValidationError("Choose ten digit slots before previewing a sheet.")
+            torso = next((asset for asset in self.uniform_catalog.assets_for_set(targets[0].set_selector)
+                          if asset.kind == "torso"), None)
+            if torso is None:
+                raise ValidationError("The selected uniform has no jersey base for the preview.")
+            background = jersey_preview_colour(session.current_path(torso))
+            return preview_digit_sheet(session.cache.pack0, targets, outputs, progress,
+                                       background=background)

     def replace_asset(
         self, asset: UniformAsset, supplied_png: Path, progress: ProgressSink
--- a/packaging/release-allowlist.txt
+++ b/packaging/release-allowlist.txt
@@ -84,6 +84,7 @@
 mod_editor/core/nfl2k5_crib_scene_texture_writer.py
 mod_editor/core/nfl2k5_crib_standalone_texture_writer.py
 mod_editor/core/nfl2k5_digit_preview.py
+mod_editor/core/nfl2k5_digit_art.py
 mod_editor/core/nfl2k5_digit_sheet.py
 mod_editor/core/nfl2k5_digit_texture.py
 mod_editor/core/nfl2k5_extended_visual_catalog.py
--- a/packaging/check_2k5_mod_studio_runtime.py
+++ b/packaging/check_2k5_mod_studio_runtime.py
@@ -1820,6 +1820,7 @@
         "mod_editor.core.build_feedback",
         "mod_editor.core.image_use",
         "mod_editor.core.nfl2k5_digit_preview",
+        "mod_editor.core.nfl2k5_digit_art",
         "mod_editor.core.nfl2k5_digit_sheet",
         "mod_editor.core.nfl2k5_digit_texture",
         "mod_editor.core.nfl2k5_equipment_import",
```

Complete replacement facade method:

```python
    def preview_digit_sheet(self, outputs: Sequence[object], progress: ProgressSink) -> object:
        """Encode the frozen sheet and current jersey colour under the source lock."""
        from mod_editor.core.nfl2k5_digit_preview import preview_digit_sheet, jersey_preview_colour

        with self._lock:
            session = self._require_session()
            targets = tuple(self.uniform_catalog.get_asset(output.asset_id) for output in outputs)
            if not targets:
                raise ValidationError("Choose ten digit slots before previewing a sheet.")
            torso = next((asset for asset in self.uniform_catalog.assets_for_set(targets[0].set_selector)
                          if asset.kind == "torso"), None)
            if torso is None:
                raise ValidationError("The selected uniform has no jersey base for the preview.")
            background = jersey_preview_colour(session.current_path(torso))
            return preview_digit_sheet(session.cache.pack0, targets, outputs, progress,
                                       background=background)

```

After applying, run `python3 packaging/repin.py --apply` so the existing runtime pins for the protected GUI and facade reflect the integrated bytes. The core provider already includes a pin for the new module. The existing number-sheet and Team Kit wiring tests already accept the new count and third chooser. Run those suites, plus `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_b66_coach_wiring.py`; that suite accepts both the proposed and applied patch. Run the normal release gates. Regenerate `data/nfl2k5_cave_reservations.json` using the normal integration workflow because pinned writers changed; this job adds no XBE write sites or caves.

No build-panel change is required. `build_feedback.completion` already lists every kept-retail receipt message; the digit writer now supplies the shared reason used by preview and Check my images. The Getting Started and number-sheet guide have been edited directly. There is no permission request or deferred core work.

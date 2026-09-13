# Beta 69 J3 integration

This job leaves protected files untouched. `studio_qt.py:2751` already constructs
`MyCareerPanel`; the page text and controls belong in that existing widget.
Apply the exact GUI and Build patch below. Its source is reproducible with
`PYTHONPATH=. python3 tools/mycareer_mode/b69_wiring.py`. The offscreen test
executes that proposed panel in memory, including a real signed-save export.
This is reviewable wiring, not a claim that the protected studio has changed.

## MyCareer page and mod_build

The patch adds the three saved caller choices, reads both preferences together,
and exports both in one signed copy. The creation controls add prospect tiers
and prototype aliases. Original creation and Pocket QB retain their defaults.
The starter checkbox is disabled for an explicit tier because the tier owns its
initial place. `mod_build._build`, immediately after the existing generic
MyCareer/draft-AI dependency, enables the existing depth-lock companion for generic creation and a
tiered prepared setup. Depth locks reserve no additional allocation. No global preset or read-option setting changes.

```diff
--- a/mod_editor/gui/my_career_panel_qt.py
+++ b/mod_editor/gui/my_career_panel_qt.py
@@ -8,6 +8,7 @@
                             QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

 from mod_editor.core import nfl2k5_my_career as career
+from mod_editor.core import nfl2k5_my_career_prospects as prospects
 from mod_editor.core import nfl2k5_my_career_save as career_save
 from mod_editor.core import nfl2k5_crib_reclaim as crib
 from mod_editor.core import nfl2k5_roster_records as roster
@@ -51,7 +52,10 @@
         title = QLabel("MyCareer")
         title.setStyleSheet("font-size: 22px; font-weight: bold;")
         layout.addWidget(title)
-        description = QLabel(career.HELP_TEXT)
+        description = QLabel(
+            "Create MyPlayer in the game, or prepare a signed draft save here. "
+            "Choose who calls the plays in Apartment Settings. Fast forward handles "
+            "MyPlayer's time off the field. Experimental: this build still needs a played check.")
         description.setWordWrap(True)
         layout.addWidget(description)

@@ -85,13 +89,26 @@
         self.position.currentIndexChanged.connect(self._position_changed)
         form.addRow("Position", self.position)
         self.template = QComboBox()
-        form.addRow("Ratings", self.template)
+        form.addRow("Prototype", self.template)
+        self.prospect = QComboBox()
+        for tier, (label, overall, goal) in enumerate(prospects.TIERS):
+            self.prospect.addItem(label if overall is None else f"{label} ({overall} OVR)", tier)
+        form.addRow("Prospect tier", self.prospect)
+        prospect_help = QLabel(
+            "1st Day: backup, Slot WR or Nickel CB. 2nd Day: third string or fourth WR/CB. "
+            "3rd Day: third string or fifth WR/CB. Undrafted: bottom of the depth chart. "
+            "The career keeps the tier's goal label. Senior Bowl play, Combine drills and Pro Day are planned. "
+            "Gunslinger QB uses the existing Pocket QB ratings.")
+        prospect_help.setWordWrap(True)
+        form.addRow(prospect_help)
         self.contract = QLabel()
         self.contract.setWordWrap(True)
         form.addRow("On the field", self.contract)
         self.starter = QCheckBox("Lock MyPlayer as a starter at his first club (depth row 1 with a rank lock)")
         self.starter.setChecked(True)
         form.addRow(self.starter)
+        self.prospect.currentIndexChanged.connect(
+            lambda: self.starter.setEnabled(self.prospect.currentData() == 0))
         self.port = QSpinBox()
         self.port.setRange(1, 8)
         form.addRow("Controller", self.port)
@@ -130,6 +147,17 @@
         self.career_supersim.setCurrentText("Fast forward")
         self.career_supersim.setEnabled(False)
         settings_form.addRow("Supersim", self.career_supersim)
+        self.career_playcall = QComboBox()
+        self.career_playcall.addItems(career_save.PLAYCALL_CHOICES)
+        self.career_playcall.setEnabled(False)
+        settings_form.addRow("Who calls the plays", self.career_playcall)
+        caller_help = QLabel(
+            "You call every play is the default. By position lets a QB call offense and an ILB "
+            "(LB in the one-pool roster) call defense. Coach calls the plays lets you execute "
+            "the coach's choice. You keep control before the snap and during the play. "
+            "Change the same saved choice in Apartment > Settings.")
+        caller_help.setWordWrap(True)
+        settings_form.addRow(caller_help)
         note = QLabel("New in-game careers default to Fast forward. Choose a save to "
                       "read its setting, then export a copy to change it. "
                       "During a game, B cancels fast forward. The same three choices "
@@ -206,8 +234,10 @@
         """Templates follow the position: the native styles of the active scheme."""
         code = self.position.currentData()
         self.template.clear()
-        for template in career.templates_for(code, scheme=self._position_scheme):
-            self.template.addItem(template.label, template.variant)
+        for label, variant in prospects.prototypes(code, scheme=self._position_scheme):
+            self.template.addItem(label, variant)
+        if code == 0:
+            self.template.setCurrentIndex(3)  # historical Pocket default
         if self.template.count() == 0:
             self.template.addItem("Keep the generated prospect ratings (no retail template)", None)
         group = career.position_group(code)
@@ -229,15 +259,19 @@

         def read_choice():
             container = roster.SaveContainer.load(source)
-            return career_save.supersim_choice(container.savegame)
-
-        def loaded(choice):
+            return (career_save.supersim_choice(container.savegame),
+                    career_save.playcall_choice(container.savegame))
+
+        def loaded(choices):
+            choice, caller = choices
             self._career_settings_source = source
             self.career_settings_path.setText(source)
             self.career_supersim.setCurrentText(choice)
+            self.career_playcall.setCurrentText(caller)
+            self.career_playcall.setEnabled(True)
             self.career_supersim.setEnabled(True)
             self.career_settings_export.setEnabled(True)
-            self.result.setText(f"Saved Supersim setting: {choice}.")
+            self.result.setText(f"Saved settings: {choice}. {caller}.")

         self._run(read_choice, loaded)

@@ -246,6 +280,7 @@
             return
         source = self._career_settings_source
         choice = self.career_supersim.currentText()
+        caller = self.career_playcall.currentText()
         target, _ = QFileDialog.getSaveFileName(
             self, "Export MyCareer save copy", "MyCareer-settings.zip",
             "Xbox save (*.zip)")
@@ -255,9 +290,10 @@
         def exported(receipt):
             self.result.setText(
                 f"Exported {receipt['target']}. Supersim: {receipt['supersim']}. "
-                "The save signature and read-back passed.")
-
-        self._run(lambda: career_save.write_supersim(source, target, choice), exported)
+                f"{receipt['playcall']}. The save signature and read-back passed.")
+
+        self._run(lambda: career_save.write_settings(
+            source, target, supersim=choice, playcall=caller), exported)

     def _choose_save(self):
         path, _ = QFileDialog.getOpenFileName(self, "Choose a Franchise draft save", "",
@@ -281,6 +317,7 @@
         self.career_settings_load.setEnabled(False)
         self.career_settings_export.setEnabled(False)
         self.career_supersim.setEnabled(False)
+        self.career_playcall.setEnabled(False)
         self.create_button.setEnabled(False)
         self.review_button.setEnabled(False)
         self.rebuild_button.setEnabled(False)
@@ -293,6 +330,7 @@
             self.career_settings_load.setEnabled(True)
             self.career_settings_export.setEnabled(bool(self._career_settings_source))
             self.career_supersim.setEnabled(bool(self._career_settings_source))
+            self.career_playcall.setEnabled(bool(self._career_settings_source))
             self.create_button.setEnabled(True)
             self.review_button.setEnabled(True)
             self.rebuild_button.setEnabled(self._plan is not None)
@@ -312,7 +350,8 @@
         options = dict(first=self.first.text().strip(), last=self.last.text().strip(),
                        position=self.position.currentData(), template=self.template.currentData(),
                        port=self.port.value() - 1, camera=self.camera.currentIndex(),
-                       starter_lock=self.starter.isChecked(), scheme=self._position_scheme)
+                       starter_lock=self.starter.isChecked(), scheme=self._position_scheme,
+                       prospect_tier=self.prospect.currentData())

         def done(receipt):
             self.setup_path = str(Path(receipt["output"]) / "MyCareer.json")
--- a/mod_editor/core/mod_build.py
+++ b/mod_editor/core/mod_build.py
@@ -1161,7 +1161,13 @@
     if plan.weekly_prep_cpu or plan.weekly_prep_remember:
         plan = replace(plan, weekly_prep=True, xbe_space=True)
     if plan.my_career and plan.my_career_setup is None:
-        plan = replace(plan, draft_ai=True)  # generic MyCareer (M3 draft) reuses the draft-AI implementation
+        plan = replace(plan, draft_ai=True, depth_locks=True)  # generic MyCareer (M3 draft) reuses the draft-AI implementation
+    if plan.my_career and plan.my_career_setup:
+        # Tiered prepared careers carry initial rank/side locks. Keep those
+        # locks through native depth sorting; ordinary creation is unchanged.
+        import struct
+        if struct.unpack_from("<I", r62["my_career_setup"], 212)[0]:
+            plan = replace(plan, depth_locks=True)
     if type(plan.deep_zone_bail_calls) not in (tuple, list) or plan.deep_zone_bail_calls:
         raise ValueError("Press corner bail authoring calls are not staged by this build; leave deep_zone_bail_calls empty "
                          "(the runtime bail option serves an already authored press call)")
```

## Registry and packaging

Add **two** EXPERIMENTAL capabilities, both off in every preset. Use the full
rows in `tools/mycareer_mode/b69_registry_rows.json`, inserted in sorted ID order alongside
`nfl2k5.mode.my_career_inline`. Their runtime status stays `not-tested`:
bounded instruction execution is not a played witness. Add their evidence to
the existing inline MyCareer row and update its settings description:

> Apartment Settings adds Who calls the plays: You call every play (default),
> By position (QB offense, ILB defense, including one-pool LB), or Coach calls
> the plays. The choice lives in footer byte 82 bits 5..6. Footer byte 83 stores
> the creation tier. A zero-filled old footer keeps the original caller and
> creation behavior. Fast-forward hand-back invalidates the absent unit's CPU
> choice for a human caller, then opens the native play-call screen. Coach
> policy keeps that native choice and restores MyPlayer's execution controller.
> In-game outcomes remain UNWITNESSED. andrethealchemist separately confirms
> the beta-68 fixes: “Wow! Everything I asked for was fixed in beta 68!”

The caller row uses the existing native mode installer as its registry CLI
backend. Studio save export uses `nfl2k5_my_career_save.write_settings` through
the page patch above; that API is not presented as an unimplemented CLI.

The shared registry count rises by two. Update both count checks in
`packaging/check_2k5_mod_studio_runtime.py`, plus
`tests/mod_editor/test_phase1_packaging.py`, the APF runtime check and
`tests/mod_editor/test_apf_studio_installer.py`. Recheck the registry schema.

Add `mod_editor/core/nfl2k5_my_career_prospects.py` to the core-provider pin
dictionary alongside the other MyCareer modules, using its actual SHA-256,
with this exact entry in `Nfl2k5UnifiedVisualProvider.module_pins`:

```python
"mod_editor/core/nfl2k5_my_career_prospects.py": "6edcb1b6bc07bfb68c1317df5c8949596ae6d4ebcfb2fd13cace66b7539ae00a",
```

Then run `python3 packaging/repin.py --apply`. Repin updates existing entries;
it does not create an entry for a new module. Add this module to
`packaging/release-allowlist.txt`. Include the new source tests, test fixture,
development wiring helper, registry rows and derived beta-69 receipts if those
development files ship in the release. Never package `.scratch`, the private
retail symlink, executables, roster data or native RAM.

In `tests/mod_editor/test_provider_integrity.py`, increase the unified provider's
expected import-closure count from 271 to 272 (the first value in the six-provider
count list). The current full provider suite reports `271 != 272` because this
new pin awaits integration. Keep its exact closure and digest checks intact.
`PYTHONPATH=. python3 tools/mycareer_mode/verify_b69_provider_wiring.py` runs all
seven provider tests with only those two proposed changes in memory.

The zero/default caller preserves beta-68 eligibility. C/G/T and K/P keep
their existing coach calls; do not broaden that mask in integration.

No new build preference is needed for play calling. It is per career, never a
global executable seed. No allocation changes: MyCareer still owns 20,480 RX
bytes and two 4,096-byte RW blocks. **Regenerate the release/settings cave
manifest after integration.** The scratch gate manifest is a conservative
projection that retains every parent allocation/reservation; it is not a
release-disc manifest. New guards pin the native menu path and overall routine.

## Integration checks

Run the proposed-panel test before applying the patch, then the actual
`test_nfl2k5_my_career_panel.py` and a direct page replay after applying it.
Update its historical QB template-count expectation for four labels sharing
three native templates. Verify both saved settings can be changed in either
direction, the tier is passed to `career.prepare_save`, and a tiered setup
requests the depth-lock companion. Run registry/provider/allowlist checks,
regenerate the release manifest, rerun the four XBE gates on the integrated
stack, and complete the reporter witness scripts in `ASTRA_B69_J3_REPORT.md`.

The proposed combined registry passes its schema validator after sorting IDs,
and every new J3 evidence/module path exists. The full inherited evidence-file
check stops at absent `docs/research/apf_audio.md`; supply the historical
release evidence before running that check during integration.

For the new helper, update `tests/mod_editor/test_provider_integrity.py`,
`test_all_external_writer_and_verifier_import_closures_are_exactly_pinned`,
replace the unique count-list literal as follows, keeping its inline comment:

```diff
-            [271, 10, 8, 9, 8, 9]
+            [272, 10, 8, 9, 8, 9]
```

The unintegrated standalone provider check fails `271 != 272` at its import
closure assertion because the helper is deliberately awaiting this pin wiring.
The proposed pin plus this count update are checked together in memory; neither
the import-closure assertion nor the source digest check is bypassed.

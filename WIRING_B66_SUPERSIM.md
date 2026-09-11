
# Beta 66 job A: MyCareer Supersim

This section belongs to `astra/b66-supersim`. Use the final
`ASTRA_REPORT.md` acceptance table and witness script for the installed runtime.
Earlier sections of this file belong to other jobs and remain historical.

The native owner now requests **20,480 RX bytes**, up from 16,384. Its base
4,096 RW bytes and separate M3 4,096 RW bytes do not grow. The allocator
chooses the owner's extension; no other owner may move. Regenerate
`data/nfl2k5_cave_reservations.json` from the integrated build. The scratch
projection is evidence for the source stack only, never the release manifest.

## Protected studio Settings choice

File: `mod_editor/gui/my_career_panel_qt.py`. Add this import beside `career`:

```python
from mod_editor.core import nfl2k5_my_career_save as career_save
```

In `MyCareerPanel.__init__`, after adding the Create MyPlayer group and before
creating the Crib movie group, insert:

```python
        settings = QGroupBox("MyCareer Settings")
        settings_form = QFormLayout(settings)
        self._career_settings_source = ""
        self.career_settings_path = QLineEdit()
        self.career_settings_path.setReadOnly(True)
        self.career_settings_path.setPlaceholderText("Choose a saved in-game MyCareer")
        self.career_settings_load = QPushButton("Choose career save")
        self.career_settings_load.clicked.connect(self._choose_career_settings)
        source_row = QHBoxLayout()
        source_row.addWidget(self.career_settings_path, 1)
        source_row.addWidget(self.career_settings_load)
        settings_form.addRow("Career", source_row)
        self.career_supersim = QComboBox()
        self.career_supersim.addItems(career_save.SUPERSIM_CHOICES)
        self.career_supersim.setCurrentText("Fast forward")
        self.career_supersim.setEnabled(False)
        settings_form.addRow("Supersim", self.career_supersim)
        note = QLabel("New in-game careers default to Fast forward. Choose a save to "
                      "read its setting, then export a copy to change it. "
                      "During a game, B cancels fast forward.")
        note.setWordWrap(True)
        settings_form.addRow(note)
        self.career_settings_export = QPushButton("Export career save copy")
        self.career_settings_export.setEnabled(False)
        self.career_settings_export.clicked.connect(self._export_career_settings)
        settings_form.addRow(self.career_settings_export)
        layout.addWidget(settings)
```

Add these methods to `MyCareerPanel` before `_choose_save`:

```python
    def _choose_career_settings(self):
        if self._task is not None:
            return
        source, _ = QFileDialog.getOpenFileName(
            self, "Choose a saved MyCareer", "",
            "Xbox saves (*.zip SAVEGAME.DAT);;All files (*)")
        if not source:
            return

        def read_choice():
            container = roster.SaveContainer.load(source)
            return career_save.supersim_choice(container.savegame)

        def loaded(choice):
            self._career_settings_source = source
            self.career_settings_path.setText(source)
            self.career_supersim.setCurrentText(choice)
            self.career_supersim.setEnabled(True)
            self.career_settings_export.setEnabled(True)
            self.result.setText(f"Saved Supersim setting: {choice}.")

        self._run(read_choice, loaded)

    def _export_career_settings(self):
        if self._task is not None or not self._career_settings_source:
            return
        source = self._career_settings_source
        choice = self.career_supersim.currentText()
        target, _ = QFileDialog.getSaveFileName(
            self, "Export MyCareer save copy", "MyCareer-settings.zip",
            "Xbox save (*.zip)")
        if not target:
            return

        def exported(receipt):
            self.result.setText(
                f"Exported {receipt['target']}. Supersim: {receipt['supersim']}. "
                "The save signature and read-back passed.")

        self._run(lambda: career_save.write_supersim(source, target, choice), exported)
```

In `_run`, immediately after its `_task is not None` early-return guard, add:

```python
        self.career_settings_load.setEnabled(False)
        self.career_settings_export.setEnabled(False)
        self.career_supersim.setEnabled(False)
```

In its nested `finished`, immediately after `self._task = None`, add:

```python
            self.career_settings_load.setEnabled(True)
            self.career_settings_export.setEnabled(bool(self._career_settings_source))
            self.career_supersim.setEnabled(bool(self._career_settings_source))
```

This updates the inline **128-byte MyCareer footer's byte 82**. It does not
change the legacy prepared-save JSON. Supersim uses mask `0x0A`: Off=`0x02`,
Skip presentation=`0x00`, Fast forward=`0x08`. Both bits set is invalid.
FPF bit 0 and star-off bit 2 survive. The core helper validates identity,
recomputes the footer checksum, verifies the source EXTRA signature, writes a
separate container, signs it and verifies its read-back. Historical zero-filled
footers keep Skip presentation; their choices are not silently migrated.

Acceptance after wiring: offscreen instantiate the real panel, open a signed
inline career with each choice, export and reopen, confirm the source remains
identical, verify unknown/non-career saves display the core error, and verify
all Settings controls disable during a worker. Run
`tests/mod_editor/test_nfl2k5_my_career_settings.py` and the existing panel suite.


## Protected capability row

File: `mod_editor/capabilities/registry.v1.json`, the object with id
`nfl2k5.mode.my_career_inline`. Keep its explicit MyCareer opt-in, current
classification, distribution rules and `runtime.status = "not-tested"`.
Fast forward defaults on **inside an enabled newly created career**; this does
not enable MyCareer in any preset. Apply these exact field replacements:

```python
row["summary"] = (
    "Native draft or undrafted entry, played-XP upgrades and the Apartment loop, "
    "with live CPU Supersim at up to eight complete updates per presented frame. "
    "Off, Skip presentation and Fast forward persist in MyCareer Settings. "
    "Sim to next appearance waits for settled native personnel and a full play clock. "
    "A score/clock/last-play ticker runs while fast forwarding; B cancels. "
    "EXPERIMENTAL / UNWITNESSED."
)
row["input_constraints"][3] = (
    "M3 requires 20480 RX and two named 4096-byte RW blocks. Rebuild old "
    "reservations from base; every other owner keeps its address."
)
row["input_constraints"][5] = (
    "Senior Bowl preparation only: the default seed-1 squads include MyPlayer. "
    "Native event transport and stat isolation are unresolved. Requests and trades stay out."
)
row["input_constraints"][7] = (
    "Apartment > Settings offers First Person Football Off/On (default Off), "
    "Supersim Off/Skip presentation/Fast forward (new-career default Fast forward), "
    "and MyPlayer star On/Off (default On). All choices persist in the signed "
    "128-byte career footer. Old zero-filled footers keep Skip presentation. "
    "The Apartment action Sim to next appearance launches the scheduled game "
    "and arms the settled-appearance wait. Fast forward runs up to eight native "
    "updates per presented frame with one input poll. Initial/OT toss, challenge, "
    "tips, pause and disconnected controllers use native prompts at normal speed. "
    "B cancels to Off. Hardware speed, audio and visual behavior remain unwitnessed."
)
row["runtime"]["scope"] = (
    "Existing bounded native creation, draft, signing, played-XP, settings and "
    "signed-save proofs remain. The installed Supersim scheduler additionally "
    "executes uninterrupted native CPU plays, checks every outer football phase, "
    "counts hardware polls/presents, keeps the match RNG cadence, drains muted "
    "native audio sources, guards modal prompts, holds CPU snap requests, restores "
    "the full play clock, and submits native ticker glyphs. Native chosen personnel "
    "cover all 17 positions, actual K/P membership and an injury replacement. "
    "Declared clip/model inputs and empty optional overlays bound the renderer "
    "proof; no console, rasterizer, display or audio device is run."
)
row["source_container"]["resource"] = (
    "Game Modes and Apartment rows, pinned native hooks, owned 20480 RX/8192 RW "
    "and an appended 128-byte career save footer."
)
row["portme"][1] = "Complete the full Supersim witness script in ASTRA_REPORT.md."
for key in (row["evidence"], row["runtime"]["evidence"]):
    for path in ("ASTRA_REPORT.md", "tests/nfl2k5_supersim_series.py",
                 "tests/nfl2k5_supersim_audio.py", "tests/nfl2k5_supersim_scheduler.py",
                 "tools/mycareer_mode/supersim_budget.json",
                 "tools/mycareer_mode/supersim_b66_receipt.json"):
        if path not in key:
            key.append(path)
```

The replacement indices above refer to the beta-65 row. If another integration
has inserted constraints, match the original paragraph text instead of applying
an index to a different paragraph.

## Protected changelog

File: `docs/mod_editor/2k5_mod_studio_changelog.md`. Under
`## v1.0 RC90, beta 66` (create the heading above RC89 if absent), insert:

```markdown
- **Live MyCareer fast forward (Noah: "i want full supersim"; andrethealchemist:
  "My career Super Sim hasn't worked for me.", 2026-09-10).** Supersim now offers
  Off, Skip presentation and Fast forward. Fast forward lets the native CPU
  engine run up to eight updates per presented frame while MyPlayer is absent,
  skips eligible presentation, keeps audio sources draining while muted, and
  shows score, quarter, clock and the last play. It holds the CPU snap until
  MyPlayer's next formation settles, then restores control with the native full
  play clock. B cancels to normal speed; toss, challenge, tips and pause prompts
  remain at normal speed. New enabled careers default to Fast forward; existing
  careers keep their saved choice. The Apartment also offers Sim to next
  appearance, and Studio Settings can export a signed save copy with the same
  three choices. Bounded native proofs cover CPU plays, actual personnel,
  substitutions, K/P, audio pool retirement and the ticker. Console speed,
  visuals and audio still need Noah's witness. EXPERIMENTAL / UNWITNESSED.
```

## Integration gates and packaging

No `mod_build.py` change is required: the existing `my_career_mode` writer owns
all installed hooks. Regenerate the protected cave manifest from the integrated
writer stack after applying this branch, including its 4 KiB RX growth. Do not
copy the scratch manifest directly into a release. The scratch-only command is:

```bash
python3 tools/mycareer_mode/refresh_settings_manifest.py --output .scratch/b66-manifest.json
```

Run both XBE gates, cave oracle and owner pairwise matrix against the regenerated
manifest, then `python3 packaging/repin.py --apply`. The report distinguishes
this branch's scratch projection from the required integrated release manifest.
The product has no new Python runtime dependency: the existing allowlist
already includes `nfl2k5_my_career.py`, `nfl2k5_my_career_mode.py`,
`nfl2k5_my_career_mode_code.py`, `nfl2k5_my_career_save.py` and the protected
`my_career_panel_qt.py`. No release-allowlist edit is required for this job.
The new test fixtures, native probe, receipt and budget are committed source
and validation evidence; the GUI archive continues to use its explicit runtime
closure. No retail asset bytes or generated XBE belong in packaging.
The Studio panel code above was projected into a scratch module
and exercised offscreen with real workers and signed save export/read-back;
the protected source itself has not been edited.

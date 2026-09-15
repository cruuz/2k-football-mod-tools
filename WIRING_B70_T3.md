# Beta 70 T3 integration handoff

Branch: `astra/b70-t3-game-audio`. No game-code bytes changed. Uniform owner edits
are documentation only. Every beta-70 in-game outcome is **UNWITNESSED**.

## Required: connect the new Music conversion owner

`audio_conform.py` is outside T3's granted owner list, so this caller change is
provided here. The new implementation is complete in
`mod_editor/core/nfl2k5_music_conform.py`. In
`mod_editor/core/audio_conform.py`, replace the **entire bodies** of the two
Music-only entry points with these forwarders (keep all other helpers):

```python
def conform_song(supplied, destination, *, reference_rms, cancelled=None):
    """Prepare a free-length 22,050-Hz song with the Music conversion owner."""
    from .nfl2k5_music_conform import conform_song as prepare
    return prepare(supplied, destination, reference_rms=reference_rms,
                   cancelled=cancelled)


def conform_music(supplied, shape, original_pcm: bytes, *, match_volume=True,
                  cancelled=None):
    """Fit a fixed music slot with the Music conversion owner."""
    from .nfl2k5_music_conform import conform_music as prepare
    return prepare(supplied, shape, original_pcm, match_volume=match_volume,
                   cancelled=cancelled)
```

The imports are lazy to keep the existing helpers available to the new module.
`conform()` for other audio panels and `tools/game_audio_convert.py` stay as they
are. This is a real release dependency: until these two forwarders land, the UI
still calls the old resampler/quantizer. The committed
`test_nfl2k5_music_conform_integration.py` runs all 29 existing Music conform,
simple-import and service tests with these exact targets installed in a scoped
patch, without editing the shared file.

In `packaging/release-allowlist.txt`, immediately after
`mod_editor/core/nfl2k5_music_banks.py`, add:

```text
mod_editor/core/nfl2k5_music_conform.py
```

## Required: show the selected jersey form and its scope

Shared help and caption function are already committed in
`mod_editor/gui/beta62_options.py`: `UNIFORM_CHOICE_HELP` and
`uniform_choice_caption(mode)`.

### Installed form evidence

In BOTH dictionaries containing
`"uniform_choice": uniform_choice_patch.status(payload)` in
`mod_editor/core/nfl2k5_throw_tuning.py` (`read_xbe` and `read_image`),
add the adjacent field:

```python
"uniform_choice_mode": uniform_choice_patch.applied_mode(payload),
```

In `mod_editor/core/mod_build.py::inspect`, beside the existing
`"uniform_choice": report.get("uniform_choice", "unknown")` entry, add:

```python
"uniform_choice_mode": report.get("uniform_choice_mode"),
```

The value must come from executable bytes;
`"applied"` by itself cannot distinguish `rule` from `choice`.

### Build panel

In `mod_editor/gui/build_panel_qt.py`, replace the existing
`self.uniform_choice_check = self._option(...)` call with:

```python
self.uniform_choice_check = self._option(
    g, "uniform_choice", r62_ui.uniform_choice_caption(""),
    r62_ui.UNIFORM_CHOICE_HELP, badge=NOT_TESTED)
```

Replace the two `uniform_choice_mode.addItem` calls and tooltip:

```python
self.uniform_choice_mode.addItem(
    "choice: choose either colour on Controller Assign / exhibition Team Select", "choice")
self.uniform_choice_mode.addItem(
    "rule: fixed home dark / away white (no colour choice)", "rule")
self.uniform_choice_mode.setToolTip(r62_ui.UNIFORM_CHOICE_HELP)
self.uniform_choice_mode.currentIndexChanged.connect(lambda _i: self._refresh())
```

In `BuildPanel._refresh`, after the initial widget construction guards, set the
caption from the actual installed or selected value:

```python
uniform_state = (self._state or {}).get("uniform_choice")
if uniform_state == "applied":
    uniform_mode = (self._state or {}).get("uniform_choice_mode")
else:
    uniform_mode = (self.uniform_choice_mode.currentData()
                    if self.uniform_choice_check.isChecked() else "")
self.uniform_choice_check.setText(r62_ui.uniform_choice_caption(uniform_mode))
```

In `BuildPanel.apply_state`, after uniform widget enablement, restore an
installed form explicitly so a disabled combo never displays `choice` over an
installed `rule`:

```python
if state.get("uniform_choice") == "applied":
    installed_form = state.get("uniform_choice_mode")
    self.uniform_choice_mode.setCurrentIndex(
        self.uniform_choice_mode.findData(installed_form))
```

Keep existing saved-project restoration and `BuildPlan.uniform_choice` handling.
The unchecked option stays off. This remains **EXPERIMENTAL**. The base branch
currently enables it in `PRESETS["softdrink_advanced"]` and
`PRESETS["softdrink_experimental"]` (the two nonempty `uniform_choice` values).
To meet the beta-70 context's off-in-every-preset instruction, replace each of
those two field values with `""` in `mod_build.py`; keep BASIC's existing `""`.

### Gameplay Patches panel

In `mod_editor/gui/gameplay_patches_panel_qt.py`, replace the `uniform_choice`
entry in `PATCHES` (the tuple list around line 152) with:

```python
("uniform_choice", "Jersey choice: choice form (Controller Assign / exhibition Team Select)",
 r62_ui.UNIFORM_CHOICE_HELP),
```

Replace its `LABELS` dictionary entry (around line 323) with:

```python
"uniform_choice": (
    "Jersey choice: choice form (Controller Assign / exhibition Team Select)",
    "Choice form only here. Build also offers a fixed rule. Preview art shows era only.",
    "Reported not working; bounded checks pass / UNWITNESSED"),
```

In `GameplayPatchesPanel._refresh`, add:

```python
uniform = self.checks.get("uniform_choice")
if uniform is not None:
    source_state = (self._state or {}).get("uniform_choice")
    mode = ((self._state or {}).get("uniform_choice_mode")
            if source_state == "applied" else "choice" if uniform.isChecked() else "")
    uniform.setText(r62_ui.uniform_choice_caption(mode))
    if source_state != "foreign":
        uniform.setToolTip(r62_ui.UNIFORM_CHOICE_HELP)
    if source_state == "applied":
        self.badges["uniform_choice"].setText(
            "Installed " + str(mode or "unknown form") + "; in-game UNWITNESSED")
```

Leave `STRING_TOGGLES["uniform_choice"] = "choice"`. Gameplay Patches installs
choice; Build provides the two-form selector. Do not label a rule-only source as
colour choice. Retain foreign-source refusal and disabled-state handling.

## Required: registry evidence and count

The base registry has **no uniform-choice row**. Add the complete JSON object in
`docs/mod_editor/nfl2k5_uniform_choice_capability.json` to the `capabilities`
array in `mod_editor/capabilities/registry.v1.json`, in canonical ID order.
**One row added (172 → 173)**; no new row for audio. Retain `offline-writer-proved` and
runtime `not-tested`. The row's evidence string explicitly records the false
reset-survival premise and the limits of bounded execution.

For existing `nfl2k5.music.bank_rebuild`, append these evidence paths:

```json
[
  "ASTRA_REPORT.md",
  "tests/mod_editor/test_nfl2k5_music_resample.py",
  "tests/mod_editor/test_nfl2k5_music_conform_integration.py",
  "tests/mod_editor/test_nfl2k5_music_queue.py"
]
```

Replace its `gui.reason` and `runtime.scope` with:

```text
Mud's beta-69 video confirms that imports appear in My songs and The Crib loads without a crash. He also reports poor audio; its cause is unresolved. Beta 70 warns before import about 22,050 Hz playback, uses stricter SoXR low-pass filtering and final TPDF PCM16 dither. Synthetic sweep and bounded queue checks are PROVED; listening quality and every beta-70 in-game outcome remain UNWITNESSED. Five identical visible queue titles alone do not prove duplicate automatic enqueueing.
```

Append that same text to its `summary`; retain runtime `status: not-tested`
for the new revision. Add `ASTRA_REPORT.md` to `runtime.evidence` as the source
of the narrowly scoped reporter witness, without converting it into blanket
runtime certification.

For `nfl2k5.music.fixed_slot`, append the resample/integration test paths above
to `evidence`, and replace `gui.reason` with:

```text
86 logical music slots; linked stereo/mono replacements remain one transaction. Before import, explain the game's 22,050 Hz playback. Converted inputs stay float through resampling, gain and fade, then receive one TPDF PCM16 conversion. Native PCM16 at unity gain without a fade stays exact. EXPERIMENTAL / UNWITNESSED in game.
```

For `nfl2k5.music.playlist`, append the queue test and report to `evidence`, and
append to `runtime.scope`:

```text
Beta 70: the manifest rejects duplicate (bank,index) records; bounded repeated active-enqueue and completion requests do not multiply automatic playback. The separate native NOW PLAYING pool permits explicit repeated adds in retail and My songs, and profile rebuild preserves their count. Mud must confirm whether his five visible repeats followed repeated adds; automatic duplication is unproved.
```

Update the shared registry count by **+1** in both count pins in
`packaging/check_2k5_mod_studio_runtime.py`, and in
`tests/mod_editor/test_phase1_packaging.py`, the APF runtime check and
`tests/mod_editor/test_apf_studio_installer.py` wherever they pin the shared
count. Package the new capability JSON if release policy packages individual
capability documents. T3 does not edit these protected registry/count owners.

## Final integration checks

- Apply the two shared Music forwarders and allowlist entry before claiming the
  new resampler is available in the studio.
- Run `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3
  tests/mod_editor/test_nfl2k5_music_conform_integration.py`, then the existing
  Music service/simple/conform tests standalone without scoped delegation.
- Run the resample, queue and uniform screen tests listed in `ASTRA_REPORT.md`.
- Offscreen, check unchecked/choice/rule, an installed rule XBE, source switch
  back to retail, saved project restoration, and all three presets. An installed
  rule must never say choice. Keep foreign source errors visible.
- Run `python3 packaging/repin.py --apply` after the protected pinned writers
  and help/captions change. Regenerate the cave reservation manifest as required
  by the shared handoff. T3 changed documentation in the uniform owner, with no
  generated byte changes or new reservations; the T3 audio module writes WAVs,
  not XBE bytes. If integration changes executable bytes, run both XBE memory
  write/cave-reference gates and pairwise/oracle tests before release.

Registry structural validation of the combined proposed document passed, and
every new row's backend/evidence path exists. Full file checks are already
blocked by baseline `docs/research/apf_audio.md` missing from this checkout;
see `reports/b70_t3/registry-handoff.log`. Do not call the full registry gate
passed until the integration checkout resolves that baseline evidence path.

## Final commit transport

The implementation is already commit `e64d61aa` on
`astra/b70-t3-game-audio`. A read-only Git metadata directory prevented the
last documentation commit from updating this worktree's branch. Its child
commit is supplied in `ASTRA_T3_HANDOFF.bundle` (prerequisite `e64d61aa`).
In a clean, writable integration checkout containing that prerequisite:

```bash
git bundle verify /path/to/ASTRA_T3_HANDOFF.bundle
git fetch /path/to/ASTRA_T3_HANDOFF.bundle astra/b70-t3-game-audio
git merge --ff-only FETCH_HEAD
```

If the integration branch already has other commits, fetch the bundle and
cherry-pick its documentation commit instead. Do not overwrite a dirty
checkout. Files in the current worktree already contain the complete handoff.

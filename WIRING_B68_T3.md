# Beta 68 T3 integration

Claude owns the protected GUI, registry and release manifest. Apply the following
changes when integrating this job. No approval or feature enablement is requested.
These options remain EXPERIMENTAL and off in every preset. Every in-game outcome
for this revision is UNWITNESSED.

## Build and Gameplay text

In `mod_editor/gui/beta62_options.py`, replace `SCOREBUG_RUNTIME_HELP` with:

```python
SCOREBUG_RUNTIME_HELP = (
    "Reported game freeze: andrethealchemist says the game freezes after Berman "
    "when this option is selected: 'Unselecting that option fixed the issue for me.' "
    "Leave this off for normal play. Diagnostic only; off in every preset. "
    "Adds team gradients, logos, live timeout marks, resized text, a white "
    "possession marker and three-digit scores to the experimental scorebar. "
    "Bounded native checks do not reproduce the player's freeze. "
    "EXPERIMENTAL / UNWITNESSED. Rebuild from the original source for comparisons.")
```

In `mod_editor/gui/build_panel_qt.py`, at the existing
`self.scorebug_runtime_check = self._option(...)` in the Build panel constructor,
replace the complete call with:

```python
self.scorebug_runtime_check = self._option(
    pl, "scorebug_runtime", "Scorebug effects (reported Berman freeze)",
    r62_ui.SCOREBUG_RUNTIME_HELP, needs_image=True, badge=NOT_TESTED,
    details=r62_ui.SCOREBUG_RUNTIME_HELP)
```

In `mod_editor/gui/gameplay_patches_panel_qt.py`, replace the `PATCHES` tuple for
`scorebug_runtime` with:

```python
("scorebug_runtime", "Scorebug effects (reported Berman freeze)",
 r62_ui.SCOREBUG_RUNTIME_HELP),
```

Both surfaces use the same help. The visible label names the freeze even when the
tooltip/details are closed. Do not change `scorebug`, Dynamic kickoff, defaults
or preset classifications as part of this text change.

## Registry rows

In `mod_editor/capabilities/registry.v1.json`, find the existing row by
`id == "nfl2k5.scorebug_presentation.runtime"`. Set these fields, retaining all
other fields and existing evidence:

```json
{
  "title": "Scorebug effects (reported Berman freeze)",
  "summary": "Diagnostic team-panel and scorebug effects. andrethealchemist reports a freeze after Berman when selected and says: 'Unselecting that option fixed the issue for me.' Leave off for normal play; off in every preset. The player's failing state remains unreproduced in bounded native execution.",
  "gui.reason": "EXPERIMENTAL / UNWITNESSED. andrethealchemist reports the Berman freeze with this option selected and recovery when unselected. Leave off for normal play. Native entry, resource and draw checks are bounded proofs, not a played fix confirmation.",
  "runtime.status": "not-tested",
  "runtime.scope": "The previous GPU-fence repair passes its historical control. Beta 68 exercises scorebug-enabled composed BuildPlans, native collection loading, setup at FCE56, update at FCFA2, font glyph draws, re-entry and the separate presentation/kickoff fixtures. andrethealchemist's selected/unselected comparison identifies this option as a reported trigger, but the stopped instruction, real asynchronous loader/GPU state and full scene lifetime are unavailable. No Berman fix is claimed. In-game behavior remains UNWITNESSED.",
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_b68_game_composition.py"
}
```

Dot keys above mean nested fields, not new literal JSON keys. Append
`ASTRA_REPORT.md`, `tests/mod_editor/test_nfl2k5_b68_game_composition.py` and
`docs/nfl2k5_b68_t3_composition.json` to both evidence lists. Keep
`gui.default_enabled: false` and the existing classification. Replace the first
`portme` entry with "Apply the beta 68 T3 section of WIRING.md; keep the reported
Berman-freeze option off in every preset." The reporter comparison supersedes
the old request to obtain such a comparison; it does not prove a stopped PC.

For `id == "nfl2k5.mode.my_career_inline"`, replace `summary` with:

```json
"Native draft or undrafted entry, played-XP upgrades and the Apartment loop. Fast forward runs up to eight native CPU updates per presented frame and returns at a settled MyPlayer appearance. B cancels the current CPU sequence until the next native snap without changing the saved Supersim choice; human receiver B and controller disconnect do not set it to Off. The career's scoring side retains native PAT play choice even when MyPlayer leaves the field. Native boundary/series tests cover these paths; played games remain EXPERIMENTAL / UNWITNESSED."
```

Append `ASTRA_REPORT.md`, `tests/nfl2k5_b68_series.py` and
`docs/nfl2k5_b68_t3_validation.json` to its evidence lists. Preserve the row's
existing default, exposure and `runtime.status`. Do not mark the played loop
tested based on a native fixture.

## Cave manifest and pins

**Regenerate `data/nfl2k5_cave_reservations.json` after integration.** The generated
MyCareer writer changed. The shipped reservation file is intentionally untouched
here. The runtime remains **20,480 RX bytes and two 4,096-byte RW blocks**; no
allocation size, peer address, XBE section geometry or file size changes. The
four-byte cancellation word is unused space at base RW `+2732`, before the
controller scratch table at `+2800`. It is not serialized.

After integration, with the release work directory available, regenerate with:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir '/media/noah/Storage/.b66-t3' \
  --json data/nfl2k5_cave_reservations.json
```

For the bounded incremental gate projection used in this worktree:

```sh
python3 tools/mycareer_mode/refresh_gate_manifest.py \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --base-revision c8783a64406ce6b062a7b287173ecbe778f43df2 \
  --output .scratch/t3/gate-manifest.json
```

That projection retains the parent reservations and observes the changed writer;
it is not a regenerated disc manifest. The release build must regenerate and run
the four gates against its release manifest. Run `python3 packaging/repin.py
--apply` after integration edits and immediately before each commit.

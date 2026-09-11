# Beta 66 job F: presentation integration (2026-09-10)

This section is the current handoff; older sections below are historical.
`ASTRA_CONTEXT.md` protects GUI panels, the registry, build dispatcher, release
allowlist, release checks and `data/nfl2k5_cave_reservations.json`. None was edited.
The camera and MyCareer writers, native in-game Settings row and persistence are
implemented, not pending GUI code. No preset defaults change.

## Coordinate with job A before merging the shared M3 files

Save footer byte **82 bit 4 (`0x10`) means MyPlayer stat line Off**. Zero means On.
Runtime base-state **+2712** stores that boolean. Existing bits 0/1/2 retain their
beta-65 meanings. **Bit 3 (`0x08`) and base-state +2708 remain free for job A's
third Supersim choice.** This branch's accepted settings mask is `0x17`; when job
A uses bit 3, merge to `0x1F`, retain all bits in both native and Python codecs,
and reject an invalid three-way Supersim encoding. Do not reinterpret bit 4.

Shared functions: `inline_valid`, `inline_encode`, `inline_decode`, `settings_labels`,
`mode_settings_toggle` in `tools/mycareer_mode/runtime.c`; `validate`,
`from_runtime`, `to_runtime` in `nfl2k5_my_career_save.py`; settings-row construction
in `nfl2k5_my_career_mode.code_for`. The stat-line row is index 3, after MyPlayer star.
Rebuild `nfl2k5_my_career_mode_code.py` after merging C/S, then repin. Both immutable
menu templates now use the same bounded LZ decoder to keep the 16 KiB RX budget.
Do not restore the uncompressed M3 template while retaining this HUD. Check
`labels['content_end'] - code_va <= TAG_OFFSET` in every reservation layout.
No new RW owner or persistent text buffer is used; line and font context live on
stack. Job A must include this presentation hook once per **presented** frame,
not once per simulated inner update. Hook `0x74879` replaces a native no-op call.

## Protected MyCareer panel: explain the in-game setting

File `mod_editor/gui/my_career_panel_qt.py`, `MyCareerPanel.__init__`, immediately
after the existing description label's `layout.addWidget(description)`, insert:

```python
stat_line_help = QLabel(
    "In-game MyCareer: Apartment > Settings > MyPlayer stat line. "
    "On by default; shows MyPlayer's current game stats in the top right. "
    "The choice is saved with the career."
)
stat_line_help.setWordWrap(True)
layout.addWidget(stat_line_help)
```

The working On/Off choice is already in the native Apartment Settings menu.
This label points users to it; no ineffective build-time preference is needed.
MyCareer stays an explicit opt-in. Camera stays enabled in ADVANCED and
EXPERIMENTAL, disabled in BASIC; Standard stays the default and Broadcast is the
existing seventh in-game menu choice (engine row 7). Do not change `mod_build.py`
for this job.

## Protected registry: extend the existing MyCareer capability

File `mod_editor/capabilities/registry.v1.json`, row
`id == "nfl2k5.mode.my_career_inline"`: append the following text to its `summary`
and `runtime.scope`, and append these paths to both evidence lists. Retain job A's
Supersim changes to that row when merging.

```text
MyPlayer stat line defaults On in an enabled career; Apartment Settings offers On/Off.
Bounded native proof executes one HUD call per presented gameplay frame, excludes
menus and both replay channels, checks MyPlayer identity, reads live bank-0 game
stats and submits real font4 glyphs. Actual game appearance remains UNWITNESSED.
```

```json
[
  "tests/mod_editor/test_nfl2k5_myplayer_hud.py",
  "tests/mod_editor/test_nfl2k5_my_career_settings.py",
  "ASTRA_REPORT.md"
]
```

Camera has no individual registry row on this base. Add this complete row to the
capabilities array; retain the registry's normal sorting and formatting:

```json
{
  "id": "nfl2k5.camera.broadcast_v6",
  "game": "nfl2k5_xbox",
  "title": "Broadcast camera v6",
  "surface": "mode_state_routing",
  "classification": "offline-writer-proved",
  "summary": "Broadcast follows gameplay with a final-eye boundary, corner pull-in, run/pass lenses and a wide kickoff transition. ADVANCED choice; gameplay appearance unwitnessed.",
  "backend": {
    "module": "mod_editor/core/nfl2k5_camera.py",
    "operation": "write",
    "command": "Studio Build: Camera enabled; in-game Options > Camera > Broadcast"
  },
  "gui": {
    "default_enabled": false,
    "expose": true,
    "mode": "edit",
    "reason": "Uses the existing Build Camera option and in-game Broadcast row; Standard remains the default."
  },
  "selectors": {
    "fields": [{"name": "camera", "required": true, "allowed": "existing boolean; enabled in ADVANCED/EXPERIMENTAL"}],
    "notes": "Broadcast is a session selection, engine row 7. No new preset default."
  },
  "source_container": {
    "format": "XBE in XDVDFS",
    "retail_file": "user-owned NFL 2K5 USA default.xbe",
    "resource": "Camera table, pinned native hooks, owned 512 RX and 320 RO bytes",
    "hash_pins": ["73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"]
  },
  "input_constraints": [
    "Reserve the complete allocator union before applying.",
    "Exact v5.4 installations are recognized and must rebuild from retail; foreign or mixed code refuses."
  ],
  "evidence": ["tests/mod_editor/test_nfl2k5_presentation_v6.py", "docs/presentation/camera_survey_v6.json", "ASTRA_REPORT.md"],
  "runtime": {
    "status": "not-tested",
    "scope": "Bounded native final-eye solver, lens projection, kickoff selection and 53-model static occlusion survey. No console, emulator or GPU witness.",
    "evidence": ["docs/presentation/camera_native_v6.json", "docs/presentation/camera_survey_v6.json"]
  },
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "tooling": "source-and-schemas-only",
    "rule": "Distribute source and measurements; never a generated XBE or retail stadium geometry."
  },
  "portme": ["Witness Chicago near-sideline run, Lambeau corners, PAT to kickoff and a deep pass as specified in ASTRA_REPORT.md."],
  "validation_command": "PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_presentation_v6.py"
}
```

## Manifest and release integration

Regenerate the protected release manifest **after all beta-66 jobs merge**; source
pins and reservations changed. Camera requests are now 512 RX/320 RO; M3 stays
16384 RX plus two 4096 RW reservations. New retail hook sites are camera
`0x5FC74..0x5FC79`, Broadcast state-7 pointer, and MyCareer `0x74879..0x7487D`.
The standalone checks here use an observed private pure-XBE manifest. That proves
the tested XBE composition; it is not a release-disc build receipt.

Claude's normal release regeneration, using disposable storage and the current
combined tree:

```bash
python3 packaging/repin.py --apply
python3 tools/nfl2k5_cave_oracle.py manifest "extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  --xiso "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso" \
  --work-dir "/media/noah/Storage/.b66-presentation" \
  --json data/nfl2k5_cave_reservations.json
```

All runtime Python paths already appear in `packaging/release-allowlist.txt`.
The two new survey/proof tools and `docs/presentation` are development evidence;
no new application import or runtime dependency on NumPy/Numba/Unicorn is added.
Run both XBE gates, oracle, pairwise and standalone subject tests on the integrated
manifest; keep existing release drift checks intact. No release checker edits.

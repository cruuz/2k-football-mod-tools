# J6 integration handoff

The granted `mod_editor/gui/roster_editor_panel_qt.py` is already edited directly. No `studio_qt.py` or `mod_build.py` change is needed for player CSV: the existing ★ Rosters page constructs this widget. The existing career-stats/team-history import paths are unchanged.

## Page text already implemented

Existing `CSV ▾` menu: `Export this list…`, `Export every player…`, `Import players from CSV…`, `CSV format and Excel help…`. The file import opens `Preview player CSV import`, listing CSV row, pool/index, field, before, after and refusal. `Apply valid rows` adds one Undo entry; an unchanged import adds none. Full instructions are `nfl2k5_roster_records.CSV_HELP`, including units and reversible Excel text protection. No shell insertion required.

## Registry: add one row

In `mod_editor/capabilities/registry.v1.json`, append this object to `capabilities` (new row count: **+1**). Update both count pins in `packaging/check_2k5_mod_studio_runtime.py`, `tests/mod_editor/test_phase1_packaging.py`, the APF runtime check and `tests/mod_editor/test_apf_studio_installer.py` as appropriate for the merged registry. These protected files were not edited here.

```json
{
  "backend": {
    "command": "Python API: export_csv(document), preview_csv(document, text), apply_csv_preview(document, preview)",
    "module": "mod_editor/core/nfl2k5_roster_records.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "ASTRA_REPORT.md",
    "tests/mod_editor/test_nfl2k5_roster_csv.py",
    "tests/mod_editor/test_nfl2k5_roster_records.py",
    "tests/mod_editor/test_roster_editor_panel_qt.py"
  ],
  "game": "nfl2k5_xbox",
  "gui": {
    "default_enabled": false,
    "expose": true,
    "mode": "edit",
    "reason": "Explicit CSV action on the loaded Rosters document. Preview before apply; source unchanged; one Undo. In-game outcomes UNWITNESSED."
  },
  "id": "nfl2k5.rosters.player_csv",
  "input_constraints": [
    "Loaded disc ROST, verified Xbox save or franchise document; UTF-8 CSV, at most 16 MiB and 100,000 rows.",
    "Every row needs pool + index. Duplicate or unknown identities refuse; never match by name. Fields use the loaded scheme and editor bounds. Unknown/duplicate headers refuse the sheet.",
    "An invalid row is refused whole. Unchanged out-of-range stored fields are preserved. Name pool and team membership constraints still apply."
  ],
  "portme": [
    "Witness Excel open/edit/save with leading-zero and long numeric text.",
    "Witness copied disc/save/franchise edits, including contracts and one Undo/Redo."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Ship source and recipes; never distribute the generated game executable or disc.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [
      "ASTRA_REPORT.md"
    ],
    "scope": "Synthetic document and offscreen page checks; no played disc/save/franchise result.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [
      {
        "name": "pool + index",
        "required": true,
        "allowed": "Exact player identity in the loaded document"
      },
      {
        "name": "player columns",
        "required": true,
        "allowed": "CSV_COLUMNS in nfl2k5_roster_records; loaded scheme position labels; card bounds"
      }
    ],
    "notes": "CSV menu on \u2605 Rosters; export every player or this list, import with preview. Numeric contract_value is in $10,000 units."
  },
  "source_container": {
    "format": "ROST/save body",
    "hash_pins": [],
    "resource": "Loaded RosterDocument, all pools; 0x54 player records, name pools and team lists",
    "retail_file": "User-owned disc roster or verified signed save"
  },
  "summary": "Export player fields and preview exact pool/index imports with per-row refusals and one complete Undo/Redo action.",
  "surface": "players_rosters",
  "title": "Player CSV export and import",
  "validation_command": "QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_roster_csv.py"
}
```

## Existing historic-rosters registry row: update, no new row

The current `nfl2k5.rosters.espn25_real_rosters` row claims opt-in availability and “no XBE edit”. Replace the following values (retain all other fields):

```python
from mod_editor.core import nfl2k5_espn25_rosters as historic
row = next(r for r in registry["capabilities"] if r["id"] == "nfl2k5.rosters.espn25_real_rosters")
row["gui"]["default_enabled"] = False
row["gui"]["reason"] = historic.BUILD_BLOCK_REASON + " EXPERIMENTAL / UNWITNESSED."
row["runtime"] = {
    "status": "not-tested",
    "scope": "Native team import, archive wait with supplied completion, scenario setup and export. Complete scene/graphics/audio load and the reported music freeze remain unproved.",
    "evidence": ["ASTRA_ESPN25_IN_GAME_REPORT.md", "ASTRA_REPORT.md", "tests/mod_editor/test_nfl2k5_espn25_loading_wait.py"],
}
row["source_container"]["resource"] = "35 pinned historic roster resources plus the existing guarded 12-byte native team-release repair at C2319; no cave or allocation."
row["selectors"]["fields"][0]["allowed"] = "false in every preset; build is blocked even when explicitly selected"
row["selectors"]["notes"] = historic.BUILD_BLOCK_REASON
row["portme"] = ["Retain the build block until the failing game's archive completion and scene state are captured and diagnosed; do not infer scene readiness from native roster import/export."]
row["evidence"] += ["ASTRA_REPORT.md", "tests/mod_editor/test_nfl2k5_espn25_loading_wait.py"]
```

The existing build-facing hold in `require_build_ready()` still guards `apply`, `apply_resources`, `preflight_image`, `apply_to_image` and `build_image`. Its updated reason is already implemented. Keep `espn25_rosters=False` in every preset. The saved ESPN Anniversary authoring plan remains a separate feature and must not be described as bypassing this all-moments hold. No new toggle, preset or game-code writer is proposed.

## Protected Build preflight refinement

`mod_editor/gui/build_panel_qt.py:717` already uses `tt.espn25_rosters_patch.HELP_TEXT`, so the edited backend help appears automatically. No Build-panel or `studio_qt.py` edit is needed for that text.

In `mod_editor/core/mod_build.py`, `build()`, the `if plan.espn25_rosters:` preflight currently evaluates `module.read_resources(source)` before `module.apply()` can issue the hold. After the existing module availability check (around line 1228), replace the apply line with this block so a held option refuses before that unnecessary resource read:

```python
        module.require_build_ready()
        _, roster_preview = module.apply(module.read_resources(source))
```

Keep the existing image/retail-position checks and every preset value. This is a preflight clarity refinement; the backend already refuses before any copy or write. At the final `if plan.espn25_rosters:` publication block (around line 1908), correct the obsolete comment to:

```python
        # Historic resource pass plus the guarded native reload repair, on the copy after relocations.
```

## Packaging and manifest

No new runtime module; CSV lives in the existing roster-records module and page. New standalone tests are `tests/mod_editor/test_nfl2k5_roster_csv.py` and `tests/mod_editor/test_nfl2k5_espn25_loading_wait.py`. If the release allowlist includes test files individually, add those paths in the protected allowlist. Native helpers remain in the existing `tests/nfl2k5_espn25_in_game.py` and `tests/nfl2k5_espn25_rosters_native.py`; the latter now retains its code-hook handle for bounded observation.

`packaging/repin.py --apply` updates the existing `mod_editor/core/providers.py` SHA pins. No manual pin bypass. The protected `data/nfl2k5_cave_reservations.json` needs Claude's regeneration because its roster-records and ESPN-rosters source fingerprints changed. The game patch bytes, XBE sites, allocation requests and dataset pins did not change. Local gates use `/tmp/b69-j6-manifest.json`: the release manifest with only those two source fingerprints refreshed, not a new real-disc manifest. Do not publish that scratch manifest as a disc proof.

## Commit bundle because shared Git metadata is read-only

The assigned worktree still points at the original base; the sandbox cannot create its shared `index.lock`. Explicit-path commits were created on `astra/b69-j6-rosters` in isolated Git metadata. `ASTRA_J6.bundle` contains only the J6 commits and requires base `922c009d65e35f8195762c31106789bb353fb43c`, already on the beta-69 stack.

In a writable integration checkout, verify/fetch the bundle, inspect the commit list, then cherry-pick that list in order:

```bash
git bundle verify /home/noah/2k-worktrees/astra-b69-j6/ASTRA_J6.bundle
git fetch /home/noah/2k-worktrees/astra-b69-j6/ASTRA_J6.bundle astra/b69-j6-rosters:refs/remotes/astra-j6/rosters
git log --reverse --oneline 922c009d65e35f8195762c31106789bb353fb43c..refs/remotes/astra-j6/rosters
```

The registry row above passes its capability definition. An attempted whole-registry schema validation also exposed the pre-existing `games.maxItems=2` versus three checked-in game records; resolve that separately during protected registry integration.

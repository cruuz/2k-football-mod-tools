# WIRING — ★ Rosters Franchise tab (local/franchise-tab)

Additions the lead needs to make in files this branch deliberately did not touch.

## packaging/release-allowlist.txt

Add the new page so it ships (beside `mod_editor/gui/roster_editor_panel_qt.py`):

    mod_editor/gui/franchise_panel_qt.py

## packaging/check_2k5_mod_studio_runtime.py

Add `"mod_editor.gui.franchise_panel_qt"` to the importable-module list next to
`"mod_editor.gui.roster_editor_panel_qt"` (around line 1752), so the runtime check imports it.

## Nothing else

* `mod_editor/gui/roster_editor_panel_qt.py` gained ten lines: the import, a `QTabWidget` (`pages`) that
  wraps the roster splitter as **Roster** and hosts the **Franchise** page (tab bar hidden until a franchise
  save is loaded), `franchise_panel.clear()` in `load_document`, `franchise_panel.load(container, document)`
  in `load_save`, and a two-line route in `write_copy_to` so a franchise save's copy goes through
  `FranchisePanel.write_copy_to` (roster edits first via `document.to_body()`, then the franchise journal).
  The concurrent label simplification should merge around those without conflict.
* `mod_editor/core/nfl2k5_franchise_save.py` gained one public read helper, `team_player_indices(team)`
  (the IR picker's list); no writer changed.
* `packaging/repin.py --apply` reported 0 pin updates after every commit (none of these modules is pinned).
* The `test_shipped_tools_posix_only.py` gate passes; the new module has no `os.open`.
* No Build tab change: saves are not disc patches.

## Noah's in-game checklist (per FRANCHISE_SAVE_REPORT_2026-09-04.md)

1. Salary cap first: raise the cap on a copy of Franchise1, load it, open the Front Office — the cap line
   should print the new figure and the cap-space arithmetic follow it.
2. User control: hand DET to the CPU and take GB; the Coach's Desk should offer GB.
3. Schedule: move one un-played game a day (or swap home/away) in a season save (f0 is week 0) and read
   the schedule screen.
4. Coach: +1 wins on Mariucci and read the coach card.
5. Injured reserve: the f1 reproduction is Finn's own witnessed save; *Activate* is ours and unwitnessed —
   activate a player and see whether the game accepts the roster count and clears the IR marker.
6. The year: witnessed already (display = 2004 + field).

# WIRING — ★ Rosters phase 2 (local/roster-phase2)

Additions the lead needs to make in files this branch deliberately did not touch.

## packaging/release-allowlist.txt

Add the new shared document so it ships:

    docs/nfl2k5_ratings_and_styles.md

Nothing else is new on disk: every code change lives in the two already-allowlisted modules
(`mod_editor/core/nfl2k5_roster_records.py`, `mod_editor/gui/roster_editor_panel_qt.py`) and their
two test files. `packaging/repin.py --apply` reported 0 pin updates after every commit (neither
module is pinned).

## mod_build.py / build_panel_qt.py

No change needed. The roster-edits step already calls `nfl2k5_roster_records.apply(...)`, which
now replays the document's `moves` (team membership) before the fields, as one checked
transaction. The `.2k5patch` Share recovery (`modpack.recognise_recipe` -> `edits_between`) picks
the moves up from the two rosters automatically.

## Optional follow-ups (not wired, listed for the record)

* The portrait picker reads `reports/assets/nfl2k5_player_portrait_compatibility.json`, already on
  the release allowlist (line 162). Absent, the picker says so and the spin box stays.
* `docs/nfl2k5_ratings_and_styles.md` mentions the optional `0x002D92B1` test patch
  (`and ecx,ebx` -> `xor ecx,ecx`) that would confirm the Scramble parity bit's animation. It is
  not implemented.

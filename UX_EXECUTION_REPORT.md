# UX simplification — execution report (2026-09-04, branch `local/ux-exec`)

Spec: `~/Desktop/2K5-8 Editors/UX_SIMPLIFICATION_PROPOSAL_2026-09-04.md` (the audit) adjudicated by
`~/2k-worktrees/ux-audit/ASTRA_UX_REVIEW.md` (the review is the final word). Stages E1–E7 are one commit
each on `local/ux-exec`, off the beta-60 stack at `7a8f521`; the moved stack (`local/stack-beta-60` at
`9f23210`: Franchise tab + practice squads) was merged additively before validation. Nothing pushed.
Screenshots (before = the audit's own captures, after = this branch with the retail disc open, 1366×768
and 1600×1000, all offscreen): `~/Desktop/2K5-8 Editors/ux_exec_2026-09-04/`, with `E8_hook_report.txt`
beside them (what every page said once the disc was open).

Brief kept: nothing removed, only collapsed; the Flying Finn layout on ★ Rosters, all four ★ pages and
the ★ row order; every BuildPlan field on the Build tab (now 47 with the merged `practice_squad` and the
beta-60 kickoff / depth-role fields); `ATTRIBUTE_CARDS`, `ProductStatus` values, BuildPlan fields, preset
ids, schema keys, asset ids and CLI arguments untouched; `SEVEN_ON_SEVEN_RELEASED` untouched; no new
save format, no writer change, no combined project→patch build (BS-14 dropped as the review said).

## Commits

| Stage | Commit | What changed |
|---|---|---|
| E1 | `f433237` | Names and output contracts: tab titles no longer clip (bold on `QTabBar`, not `::tab`), lone `&` escaped everywhere Qt reads a mnemonic, header / File menu / footer / every copy-writing page use one vocabulary (Open game disc…, Open project… / Save project, Game disc (.iso) / Save disc copy as — or Game executable / Save executable copy as for a bare default.xbe — Make my disc, Make disc from project, Make disc with these changes, Save patched executable…, Update working copy, Save disc copy… / Save Xbox save copy…, Export roster edits (.json)…, Set up xemu…, Play latest disc in xemu). One xemu sentence. Blockers and launch tooltips name the next step. `mod_editor/gui/ux_text.py` holds the shared pieces (`tab_title`, `Details`, `show_operation_error`, `suggest_copy_name`). |
| E2 | `d76e062` | The one authorised hook: opening a disc feeds every page with its own source field through that page's existing reader, off the UI thread, generation-guarded; Share follows the open disc only where nothing owns the field; ★ Rosters loads lazily on first entry and never resets an edited roster; copy names suggested only where a copy is made (Bump's working copy stays unfilled); a finished Build adopts the output as source and suggests a fresh target (never a build onto itself); Start SOFTDRINK Basic waits for the inspection and only ticks a fresh selection; roster / model / Share discs register with the launcher. Tests: `test_ux_open_disc_hook_qt.py`. |
| E3 | `3e4ffa7` | Getting Started names the tasks, one primary button, Discord line; Build tab leads with presets + captions, output name, selection summary, Make my disc with a visible blocker; plain confirmation and finish; Share leads with Export mod file, the any-two-discs form under an expander, Install a friend's mod with plain states. |
| E4 | `12ac725` | The option list rebuilt from the review's label table: short check boxes, helper lines, visible badges (Full disc required / Already installed / Not yet tested in-game / New franchises only / Not available in this release / Unrecognized source data), Details for the technical story, groups Gameplay / Franchise / Rosters & positions / Presentation; new bindings for manual arc, commentary rows, playbook packs, mod name / author / notes, jersey modes; required-file rows appear with their tick and block by name; Game Fixes / Position names share the labels. Tests: `test_ux_build_plan_coverage_qt.py` walks the dataclass. |
| E5 | `6485102` | ★ Rosters in Finn's layout with honest words: Position names visible + override under an expander, Est. OVR, units on height / weight / contract value (money beside it), readable contract line, key ratings, checks without bracketed tags, name-space sentences, export = snapshot (stale after the next edit, on the page and on the Build tab), replacing an edited roster asks first, Global Attribute Editor invalidates a preview when a setting changes and recalculates before Apply. Disc-text page renamed Names, Numbers & Faces (display only) with position names, Player list 1/2, View only, name-space units. Tests: `test_ux_rosters_words_qt.py`. |
| E6 | `c81eccf` | Every remaining page opens with a sentence; Gameplay lands on Game Fixes (research tables under Reference (read-only), Saves & Sliders moved from Uniforms); Throw expanders; Presentation / Audio / Models / Playbooks / Create a Play wording; browser panes may shrink. |
| E7 | `0ffb06c` | The P3 details (eyebrow, help menu order + Getting started guide, capability pills, Field Art / Stadiums / Crib / Audio / Xbox save / Bump / PS2 / pack dialog / designers / playbook meta / Menus & UI). |
| merge | `9f18480` | `local/stack-beta-60` merged additively (Franchise tab hook kept; `practice_squad` gets a row in the same shape). |
| Franchise | `bf26961` | The Franchise tab gets the same label discipline (badges on cap / schedule / coach / IR Activate); nothing restructured. |

Count of changed on-screen strings, per stage (added quoted lines in `mod_editor/gui`): E1 322, E2 101,
E3 208, E4 330, E5 136, E6 187, E7 89, Franchise 20 — about 1,390 lines of visible text touched.

## What the hook does with the real disc (E8, offscreen, retail dump)

From `E8_hook_report.txt`: the disc opens in ~25 s; the pill reads `Disc: ESPN NFL 2K5 (USA).xiso.iso ·
original`; Getting Started says `Disc open: … / Next: choose SOFTDRINK patches or edit rosters.`; Build,
Game Fixes and Position names carry the disc with `Game disc (.iso)` captions and a suggested
`ESPN NFL 2K5 (USA) (modded / gameplay patched / position names).xiso.iso`; Throw read the original
tables; the ESPN bar page says the original scorebug can be written and suggests its own copy name;
Commentary found 16 banks; Replace a Sound read the three banks; Bump Maps browsed 634 packages and left
the working copy unfilled; ★ Models listed 4,616 models; Share's starting disc and install disc follow the
open disc with its identity line; ★ Rosters stayed empty until the page was entered, then loaded 2,547
players. Start SOFTDRINK Basic ticked 9 changes after the inspection and the confirmation lists the
source, the new disc and every change by its short name. No chooser opened and nothing was written.

## Layout at 1366×768 and 1600×1000

No horizontal page scroll on Getting Started, Build & Share (both tabs), Gameplay or ★ Rosters at
1600×1000; at 1366×768 Getting Started, Build & Share and Gameplay fit; ★ Rosters with a loaded roster is
within a few pixels (see the residual list below). Across all 17 rows and every tab with no disc, the
only page still wider than a 1366-px window is Stadiums (three fixed panes; ~100 px).

## Deliberately not done, and why

- **BS-14 combined project→patch build** — dropped by the review (new orchestration outside the scope).
- **Backend / writer changes** — none. Every change is presentation or the E2 wiring of existing readers.
- **`SEVEN_ON_SEVEN_RELEASED`** — untouched; the row is reachable, disabled, "Not available in this release".
- **Catalog data notes** (`authoring_note` strings in the visual catalog) — not edited; the page shows
  "Common image files are resized to W×H for you" and keeps the slot's own note one hover away.
- **`ESPN_25TH_COMING_SOON_NOTE`** — the constant stays (a test pins its words); the on-screen label is the
  short sentence with the constant as its tooltip.
- **Getting-started document** — only the changelog bullet and the STATUS line were written; the
  markdown guide still uses some of the old button names (it is not pinned by tests beyond its heading).
  Left for a docs pass.
- **Residual width**: Stadiums at 1366 px (fixed 300 / 360-min / 320 panes), ★ Rosters with a loaded
  roster at 1366 px (a few pixels from the card grid); both scroll horizontally within the page host.
- **Franchise tab** — labels only, as asked; the schedule score cells and coach names stay read-only as
  the tab's own changelog says.

## Validation (E8)

**Named files** (the proposal's and the review's list, one consolidated run after the merge): shell layout,
accessibility, capability visibility, explainable build, build panel, share, roster panel + franchise card +
Franchise tab, throw, models, gameplay patches, sounds, commentary, uniform export, player assets, playbooks
panel + pack UI, create-play wizard, inspection panels, refusal wording, product catalog, and the three new
UX test files — **249 passed, 16 skipped, 0 failed** (3 min 06 s).

**Whole `tests/mod_editor`**: run once as a single pytest process it stalled at ~15 % for more than 35 min
(the untouched base commit stalled at the same place in an earlier run, so it is not this branch); it was
then run **file by file with a 15-minute cap** (298 files): **3,325 passed, 135 skipped, 15 failed in 5 files,
4 files collected no tests** (`test_nfl2k5_bump_strength`, `_bump_texture_writer`, `_save_writer`,
`_throw_tuning` need retail fixtures). The five failing files, each with its cause:

| File | Cause | Action |
|---|---|---|
| `test_2k5_audio_operation_integration` (1) | the source-release fence counted two post-release tasks; the open-disc hook queues a third (the read-only inspection), after release like the other two | test updated to 3; behaviour unchanged |
| `test_nfl2k5_player_star` (1) | pinned "none ticked" in the star label; the label now reads "none selected" + the Names, Numbers & Faces route (M06) | test updated |
| `test_nfl2k5_prospect_names` (1) | pinned the tooltip "Needs a disc image."; it now says "Full disc required (not a bare default.xbe)." | test updated |
| `test_provider_integrity` (1), `test_providers` (11) | `ProviderError: … evidence child must not be a symlink` — this worktree's `reports/assets` is the read-only symlink the render setup uses; the untouched base commit fails the same way here | not caused by the pass; passes in a checkout with a real `reports/assets` |

`python3 packaging/repin.py --apply`: 2 pin updates on the first run (the studio module's runtime pin and
the allowlist entry), 0 on the re-runs after the last edits.

**Renders**: all 17 rows and every tab rendered offscreen with no disc at 1366×768 (only Stadiums keeps a
horizontal scroll, ~100 px), and the four named pages with the retail disc open at 1366×768 and 1600×1000
(`after_*.png` beside the audit's `before_*.png`). Build & Share shows no horizontal page scroll at either
size, with or without the disc.

## Left for Claude

- `mod_editor/gui/studio_qt.py` — the Stadiums page width (`scenes_panel.setFixedWidth(300)`,
  `viewport.setMinimumSize(360, 300)`, `texture_panel.setFixedWidth(320)` around the `_build_stadium_page`
  block) if a 1366-px window matters there.
- `docs/mod_editor/2k5_mod_studio_getting_started.md` — bring the button names in line with the app.

# DESIGN: final-disc playbook integration

DESIGN: Replace the final draft's entire `playbook_packs` array with [final_playbooks.json](final_playbooks.json)'s 64 paths and apply its two flags. Preserve every other production key, including `qb_spy`, `screen_timing` and `xemu_display_list_fix`. [compose.py](compose.py) copies a real recipe and changes only these three keys. [The defense lab recipe](../lab/defense.recipe.json) now derives from the final draft; [the older offense lab recipe](../lab/v7.pb.json) derives from v7 with the same overrides. Neither isolates the books by switching other owners off.

PROVED OFFLINE: Import the phase 3 core validator change with the packs. The updated custom-defense validator permits only CPU score bits 9-11 to differ from the verified donor header; older builds reject these weighted v2 recipes. Preset headers and all other bits remain exact.

DESIGN: The first 32 packs are complete offenses with level D screens, followed by 32 exact-source defensive packs. Build's existing `playbook_packs` path orders complete offense compilation ahead of v2 defense. Each defense fingerprint targets its team's current offense result. An incompatible source or a changed offense fails validation rather than silently retargeting. Keep source v2 packs in this explicit list; do not add the old generic packs afterward.

| DESIGN removed pack / flag | DESIGN reason |
| --- | --- |
| `softdrink_option` | Noah excludes read option and RPO; complete offenses already own the ordinary offense menus. |
| `modern_gun_core` | Its generic gun package is superseded by the complete per-team offenses; adding it would overwrite their authored menus and consume capacity. |
| `softdrink_modern_defense` | Its donor grammar is reused inside team defenses; reinstalling the generic pack would overwrite selected team-specific calls and break exact source composition. |
| `softdrink_match_coverage` | Its bounded native exchanges and robber recipe are reused inside team defenses; the generic pack is not appended again. Full match policies remain unproved. |
| `read_option_runtime: false` | There are no option-intent records or RPO calls in these packs. |
| `playbook_pair: false` | Each retail team resource now contains its own offense and defense; a second-book substitution hook is unnecessary. |
| No `qb_spy` override | Inherit production's enabled owner. KC has one cited situational Spy via the existing authoring/runtime contract; all other packs report empty intent. |
| No `screen_timing` override | Inherit production's D level. All authored RB screens declare D values, certified by exact owner signature pins. A/B/C on these pre-timed books refuse. |

DESIGN: [full_build.sh](full_build.sh) copies the real final draft, merges the fragment and invokes the Ultimate builder under `nice -n 15` using this stack. It retains final owner inspection and the log, then deletes the disc. A check-only result is not composition proof. Current evidence is in [PB_REPORT.md](../PB_REPORT.md).

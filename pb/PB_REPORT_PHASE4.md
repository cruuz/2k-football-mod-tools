# PROVED OFFLINE: phase 4, team books in the full final-draft build

PROVED OFFLINE: The full Ultimate build completed in 2703 seconds after preflight, using this worktree and the real final-draft recipe with only `playbook_packs`, `playbook_pair` and `read_option_runtime` changed. QB Spy and screen timing retain production values (`true` and `D`). The display-list fix remains enabled. No pending option was dropped. [Build log](receipts/phase4/full-build.log), [merged recipe](receipts/phase4/full-recipe.json), [full owner inspection](receipts/phase4/full-build.json), [builder summary](receipts/phase4/full-summary.json).

PROVED OFFLINE: All 64 compiler receipts carry versioned Spy records. The complete-offense compiler emits empty Spy and option records plus its resolved play indices. The final-intent resolver accepts that explicit empty contract and rejects any nonempty intent claimed by a complete-offense report. The normal defense compiler retains responsibility for real Spy validation. [Contract receipt](receipts/phase4/contracts.json).

DESIGN: KC gets one situational call, `PB Two Spy 21`, through the existing Spy authoring API, native MLB slot 5 and a four-yard centered fallback. The enabled runtime supplies QB tracking. [Cited tendency and limitations](research/SPY.md). The other 31 defenses and all 32 offenses have empty Spy records. One menu call is a design choice, not an invented season rate or a quarterback-aware CPU policy. The final runtime table uses one of 31 available records, recompiled against the installed PLAY after personnel-pool and depth-role changes.

PROVED OFFLINE: All 407 authored RB screens declare D's 0.8-second finite hold, seven-yard QB drop and 0.6-second explicit pass delay. Their menu names include `RB Screen`, making them visible to the screen owner. The owner recognizes their exact whole-screen signatures alongside its retail pins; it does not accept arbitrary custom screens, missing screens or different-level assignments. The screens are already at D when compiled, so this consumes no extra timing-pass nodes. Retail utility books still receive their normal D pass. A/B/C requests on these pre-timed authored books refuse.

PROVED OFFLINE: The new tests exercise all 64 receipts, stale/missing/forged intent, final Spy re-resolution after both personnel writers, every screen timing value, different-level and changed-byte refusal, and the transactional 37-book archive including retail utilities. [Composition tests](receipts/phase4/composition-tests.txt), [owner regression](receipts/phase4/owner-regression.txt), [native Spy regression](receipts/phase4/spy-native-regression.txt). The native regression skips two generic opt-in disc tests; this job separately runs the requested full production build.

PROVED OFFLINE: Current native menu, assignment, selector and preservation evidence is in [the defense appendix](DEFENSE_APPENDIX.md), [composition](receipts/defense/composition.json), [offense menu replay](receipts/league-offline.json) and [preservation](receipts/defense/preservation.json). The phase 3 source fingerprints were regenerated for the changed offenses. [Phase 3 historical report](PB_REPORT_PHASE3.md) retains its earlier scope; its disabled-owner guidance is superseded by this report.

PROVED OFFLINE: The initial book regression retained obsolete assertions for zero screen delay and the isolated 32-pack recipe. Updated tests require D delay, the 64-pack fragment and enabled production owners. [Updated expectations](receipts/phase4/updated-league-expectations.txt), [book regression log](receipts/phase4/book-regression-initial.txt), [final league regression](receipts/phase4/league-tests-final.txt), [defense tests](receipts/phase4/defense-tests.txt).

DESIGN: Reproduce with `python3 pb/build_giants.py --image <retail>`, `python3 pb/build_league.py --image <retail>`, `python3 pb/defense/build.py`, `python3 pb/phase4.py --write-pins`, then `bash pb/recipes/full_build.sh`. The last command starts from a fresh copy of the real final draft, uses `nice -n 15 taskset -c 0-23`, writes only under the designated Storage directory, records statuses and deletes the disposable ISO on exit. The older lab recipes were also rebuilt from real production files. Check-only is not composition proof.

PROVED OFFLINE: Build evidence directory: `/media/noah/Storage/.b76-research/pb/astra-build/phase4.KuDOys`. Output size before deletion: 7,475,951,616 bytes. NVMe free at status checks: 104.51 GiB. The disc was deleted after status checks; the log and build JSON remain. [Exact source and pack hashes](receipts/phase4/build-inputs.json) identify the changed files used on top of phase 3 commit `6f7815db5`. The source recipe and other worktrees were not modified. No xemu was run.

PROVED OFFLINE: Build composition, owner byte status and offline menu execution are proved for these inputs. DESIGN: Live Spy pursuit, screen timing benefit, CPU opponent-aware selection and game stability still require main's lab. This build uses the final draft's roster input exactly; it does not substitute the separate 2026-team project builder.

PROVED OFFLINE: Per-team compiler results follow. Node/name use is after both packs, before unrelated production writers. Every screen is certified at D; empty Spy records are explicit.

| Team | PROVED OFFLINE D screens | PROVED OFFLINE Spy records | PROVED OFFLINE nodes / name bytes |
| --- | ---: | ---: | ---: |
| ARZ | 2 | 0 | 2832 / 9890 |
| ATL | 22 | 0 | 2801 / 9626 |
| BAL | 11 | 0 | 2773 / 9606 |
| BUF | 27 | 0 | 2768 / 9722 |
| CAR | 13 | 0 | 2795 / 9808 |
| CHI | 13 | 0 | 2843 / 9624 |
| CIN | 14 | 0 | 2775 / 9616 |
| CLE | 3 | 0 | 2689 / 9622 |
| DAL | 3 | 0 | 3171 / 10224 |
| DEN | 13 | 0 | 2669 / 9168 |
| DET | 24 | 0 | 2802 / 9600 |
| GB | 11 | 0 | 2863 / 10198 |
| HOU | 3 | 0 | 2832 / 9768 |
| IND | 2 | 0 | 2758 / 9718 |
| JAX | 3 | 0 | 2823 / 9824 |
| KC | 20 | 1 | 2673 / 9096 |
| MIA | 26 | 0 | 3121 / 10248 |
| MIN | 12 | 0 | 2962 / 10318 |
| NE | 10 | 0 | 2773 / 9188 |
| NO | 14 | 0 | 2778 / 9650 |
| NYG | 6 | 0 | 2870 / 9584 |
| NYJ | 21 | 0 | 3150 / 10078 |
| OAK | 11 | 0 | 2774 / 9822 |
| PHI | 15 | 0 | 2878 / 10000 |
| PIT | 11 | 0 | 3124 / 9846 |
| SD | 23 | 0 | 3185 / 10538 |
| SEA | 14 | 0 | 2833 / 9974 |
| SF | 22 | 0 | 2828 / 9554 |
| STL | 3 | 0 | 2820 / 10062 |
| TB | 11 | 0 | 2763 / 9728 |
| TEN | 12 | 0 | 2705 / 9050 |
| WAS | 12 | 0 | 2859 / 9368 |

PROVED OFFLINE: Current test results:

| Suite | PROVED OFFLINE result |
| --- | --- |
| [composition-tests.txt](receipts/phase4/composition-tests.txt) | 6 passed, 32 subtests passed in 109.81s (0:01:49) |
| [owner-regression.txt](receipts/phase4/owner-regression.txt) | 53 passed, 184 subtests passed in 679.89s (0:11:19) |
| [spy-native-regression.txt](receipts/phase4/spy-native-regression.txt) | 33 passed, 2 skipped, 57 subtests passed in 442.41s (0:07:22) |
| [league-tests-final.txt](receipts/phase4/league-tests-final.txt) | 11 passed, 5522 subtests passed in 92.20s (0:01:32) |
| [defense-tests.txt](receipts/phase4/defense-tests.txt) | 13 passed, 159 subtests passed in 43.97s |

PROVED OFFLINE: Every top-level final inspection row follows, including disabled owners and metadata. Nested details remain in the linked full inspection JSON. Builder classification: 93 applied, 2 expected foreign, 0 not applied and 8 without a separate inspection row.

| Owner / inspection key | PROVED OFFLINE final value |
| --- | --- |
| `abilities` | applied |
| `abilities_settings` | applied |
| `accel_ramp` | retail |
| `accelerated_clock` | applied |
| `accelerated_clock_settings` | applied |
| `all_stadiums` | applied |
| `calendar_engine` | applied |
| `camera` | applied |
| `catch_slider` | applied |
| `chop_block_evidence` | applied |
| `chop_block_toggle` | applied |
| `coin_defer` | applied |
| `coin_defer_settings` | applied |
| `commentary` | unknown |
| `container` | xiso |
| `coverage_slider` | applied |
| `coverage_trail` | applied |
| `cpu_money_downs` | applied |
| `cpu_money_downs_settings` | details in full-build.json; no standalone status |
| `cpu_scrambles` | applied |
| `cpu_scrambles_settings` | applied |
| `created_teams_extra` | applied |
| `crib_reclaim` | applied |
| `custom_intro` | applied |
| `decided_clock` | applied |
| `decided_clock_settings` | applied |
| `deep_zone_bail` | applied |
| `deep_zone_facing` | applied |
| `deep_zone_settings` | applied |
| `defensive_try` | applied |
| `depth_chart_rows` | applied |
| `depth_locks` | applied |
| `depth_roles` | foreign |
| `depth_roles_books` | details in full-build.json; no standalone status |
| `disc_identity` | details in full-build.json; no standalone status |
| `disc_identity_headline` | unknown image |
| `disc_identity_line` | unknown image. This is an xiso holding ESPN NFL 2K5, but default.xbe, vc_53450030/0, vc_53450030/F is missing or not its retail size. Neither Build nor Apply can trust it; use a dump of your own retail disc. |
| `draft_ai` | applied |
| `dynamic_kickoff` | applied |
| `dynamic_kickoff_settings` | applied |
| `edge_rename` | applied |
| `edge_rename_disc` | foreign |
| `elbow_options` | applied |
| `espn25_more_moments` | applied |
| `espn25_plan` | foreign |
| `espn25_rosters` | applied |
| `espn_marks_2026` | applied |
| `espn_wipes_boards_2026` | applied |
| `flatter_deep_ball` | foreign |
| `franchise_2026_kernel` | retail |
| `franchise_2026_rules` | unavailable |
| `franchise_2026_runtime_enforced` | False |
| `franchise_autosave` | applied |
| `franchise_edit_player` | applied |
| `franchise_practice` | applied |
| `guardian_cap` | foreign |
| `guardian_overlay` | applied |
| `guardian_overlay_resources` | applied |
| `guardian_overlay_settings` | applied |
| `helmet_finish` | retail |
| `hires_pack` | foreign |
| `hires_pack_details` | foreign |
| `historic_styles` | applied |
| `historic_teams_quick_game` | applied |
| `image_sha256` | 735a95bb6eab910c51573266b6fb5755333b62435a8a5288a5c30319d7b882ed |
| `image_size` | 7475951616 |
| `k128_early` | retail |
| `k128_memory` | applied |
| `k128_roster_heap` | applied |
| `k128_settings` | applied |
| `kick_laces` | applied |
| `kick_power` | applied |
| `kick_rules` | applied |
| `kickoff_alignment` | applied |
| `kickoff_relocated` | retail |
| `kickoff_relocated_settings` | retail |
| `kickoff_return_blocking` | retail |
| `kickoff_returns` | applied |
| `modern_arrowhead` | retail |
| `modern_color` | applied |
| `modern_color_settings` | details in full-build.json; no standalone status |
| `modern_metlife` | applied |
| `modern_metlife_model` | applied |
| `modern_naming` | applied |
| `modern_naming_details` | 24 detail rows in full-build.json |
| `modern_sofi` | applied |
| `modern_venues_2026` | applied |
| `momentum` | applied |
| `momentum_collisions` | applied |
| `momentum_contact` | applied |
| `momentum_settings` | applied |
| `music_library` | available |
| `music_library_counts` | details in full-build.json; no standalone status |
| `music_metadata_patch` | retail |
| `music_policy` | applied |
| `music_project` | available |
| `music_shuffle` | applied |
| `music_shuffle_state` | applied |
| `music_state` | applied |
| `music_unlock` | applied |
| `music_userlist` | applied |
| `my_career` | applied |
| `overtime` | applied |
| `path` | /media/noah/Storage/.b76-research/pb/astra-build/phase4.KuDOys/final.xiso.iso |
| `penalties` | applied |
| `playbook_packs` | n/a |
| `playbook_pair` | retail |
| `player_star` | applied |
| `player_tags` | applied |
| `playoff_picture` | applied |
| `position_pool_filters` | applied |
| `position_pools` | applied |
| `position_row` | applied |
| `practice_reserves` | applied |
| `practice_squad` | applied |
| `practice_squad_screen` | applied |
| `probowl_order` | applied |
| `progression` | applied |
| `prospect_names` | applied |
| `qb_spy` | applied |
| `read_option_runtime` | retail |
| `read_option_runtime_settings` | None |
| `reserves_16` | applied |
| `returner_fix` | applied |
| `roster_arena_growth` | applied |
| `roster_arena_resource` | applied |
| `roster_arena_settings` | applied |
| `roster_edits` | edited |
| `scheme_labels` | applied |
| `scorebug` | foreign |
| `scorebug_runtime` | applied |
| `scorebug_runtime_resources` | applied |
| `scorebug_xbe` | applied |
| `scramble_tuning` | applied |
| `screen_hooks` | applied |
| `screen_hooks_settings` | details in full-build.json; no standalone status |
| `screen_timing` | applied |
| `screen_timing_details` | applied |
| `season_2026` | applied |
| `season_cap` | applied |
| `senior_bowl` | retail |
| `senior_bowl_native_available` | False |
| `seven_on_seven` | applied |
| `seven_on_seven_book` | applied |
| `team_column` | applied |
| `team_history` | applied |
| `team_names_2026` | applied |
| `team_names_2026_details` | details in full-build.json; no standalone status |
| `team_names_2026_xbe` | applied |
| `the1wam_lineman_rating` | applied |
| `throw` | TuningSettings(max_deep_yards=80.0, arc=0.0, realistic_flight=True, arc_by_distance=True) |
| `trim_intro_videos` | retail |
| `uniform_choice` | foreign |
| `uniform_choice_mode` | None |
| `weather_haze` | applied |
| `weather_plan` | foreign |
| `weekly_prep` | applied |
| `weekly_prep_cpu` | applied |
| `weekly_prep_remember` | applied |
| `weekly_prep_settings` | applied |
| `widescreen` | applied |
| `xbe_space` | applied |
| `xemu_display_list_fix` | applied |
| `zone_drop_cap` | applied |
| `zone_drop_settings` | applied |

PROVED OFFLINE: The builder's explicit non-applied, expected-foreign and uninspected classifications:

```json
{
  "not_applied": {},
  "expected_foreign": {
    "depth_roles": "custom books (packs, 7-on-7) read foreign without allow_custom; the step reports applied",
    "scorebug": "static scorebar inspector vs the sprite-grown HUD (same on the Berman disc A)"
  },
  "not_inspected": {
    "momentum_collision_level": "no inspection row (a setting of another option, or an input)",
    "scorebug_watermark": "no inspection row (a setting of another option, or an input)",
    "accelerated_clock_minimum_seconds": "no inspection row (a setting of another option, or an input)",
    "decided_clock_margin": "no inspection row (a setting of another option, or an input)",
    "decided_clock_seconds": "no inspection row (a setting of another option, or an input)",
    "abilities_lock_right_stick": "no inspection row (a setting of another option, or an input)",
    "abilities_lock_special_moves": "no inspection row (a setting of another option, or an input)",
    "abilities_lock_speedster": "no inspection row (a setting of another option, or an input)"
  },
  "skipped_pending": {}
}
```

PROVED OFFLINE: Last 25 build-log lines, preserved verbatim:

```text
[08:07:29]   SoFi Stadium: done 1/1
[08:07:29]   ESPN presentation marks (2026)
[08:07:31]   ESPN presentation marks: nfl_chiclet (1 of 4) 0/4
[08:07:31]   ESPN presentation marks: shield_espn (2 of 4) 1/4
[08:07:31]   ESPN presentation marks: espnLogo1 (3 of 4) 2/4
[08:07:31]   ESPN presentation marks: z_ESPN_bug (4 of 4) 3/4
[08:07:31]   ESPN presentation marks: done 4/4
[08:07:33]   ESPN 2026 wipes and boards
[08:07:33]   ESPN 2026 wipes and boards: replay_wipe (1 of 6) 0/6
[08:07:33]   ESPN 2026 wipes and boards: fullscreen_WipeElectricity (2 of 6) 1/6
[08:07:33]   ESPN 2026 wipes and boards: fullscreen_WipeRedFlashy (3 of 6) 2/6
[08:07:33]   ESPN 2026 wipes and boards: scoreboard (4 of 6) 3/6
[08:07:34]   ESPN 2026 wipes and boards: helmetbumper (5 of 6) 4/6
[08:07:35]   ESPN 2026 wipes and boards: playercard (6 of 6) 5/6
[08:07:35]   ESPN 2026 wipes and boards: done 6/6
[08:07:35]   Writing the custom intro video
[08:07:55]   copy 0/7517149184
[08:08:08]   archive 0/4418
[08:08:18]   verify 1/4418
[08:08:39]   Hashing the verified disc
[08:08:44]   The copy differs from your source. Review the Build summary for its selected contents and any edits kept original.
[08:08:44]   Publishing the verified disc
[08:08:45] applied 93, expected foreign 2, not applied 0, not inspected 8, skipped pending 0
[08:08:45] sprite HUD appended bytes 327520
[08:08:45] ULTIMATE_BUILD_OK target=/media/noah/Storage/.b76-research/pb/astra-build/phase4.KuDOys/final.xiso.iso bytes=7475951616 seconds=2703
```

PROVED OFFLINE: Shared Git metadata is read-only. Delivery uses a pathspec commit in private `.scratch/pb.git` and `.scratch/pb-phase4.bundle`, based on `6f7815db5`, with the required Astra co-author. No push or tags. Exact commit and bundle hash are in `.scratch/pb-phase4-delivery.json`.

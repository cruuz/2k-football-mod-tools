# Independent A2b hunk ledger

Diff base `b5949335` is the completed J4/J3/J5 merge union. Final A2b head is `c2489fca`.
Every hunk below links to its full before/after diff. Merge-only resolutions are separately recorded in
`j3/j4/j5-merge-resolution.patch`; job-owned final deltas are in `j3/j4/j5-job-to-stack.patch`.
“Applied exactly” means the WIRING behavior is preserved, including mechanically forwarded parameters.
“Documented deviation” identifies A2b adapters/evidence needed by the actual integrated tree.
“Wrong” rows have findings in ASTRA_REPORT.md. Missing hunks (old pins/fixtures) appear there too.

| ID | Job | File / hunk | Verdict | Review |
| --- | --- | --- | --- | --- |
| H001 | J3/J4/J5 | [ASTRA_B69_A2B_REPORT.md #1](integration-full.patch#L6) | wrong | A2b integration handoff; Clear-control claim and 12-entry runtime-block count are inaccurate (D5); other results independently checked |
| H002 | J3/J4/J5 | [ASTRA_B69_J3_REPORT.md #1](integration-full.patch#L375) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H003 | J3/J4/J5 | [ASTRA_B69_J3_REPORT.md #2](integration-full.patch#L384) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H004 | J3/J4/J5 | [ASTRA_B69_J4_REPORT.md #1](integration-full.patch#L397) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H005 | J3/J4/J5 | [ASTRA_B69_J4_REPORT.md #2](integration-full.patch#L406) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H006 | J3/J4/J5 | [ASTRA_B69_J5_REPORT.md #1](integration-full.patch#L419) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H007 | J3/J4/J5 | [WIRING_B69_J3.md #1](integration-full.patch#L432) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H008 | J3/J4/J5 | [WIRING_B69_J4.md #1](integration-full.patch#L445) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H009 | J3/J4/J5 | [WIRING_B69_J4.md #2](integration-full.patch#L454) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H010 | J3/J4/J5 | [WIRING_B69_J4.md #3](integration-full.patch#L463) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H011 | J3/J4/J5 | [WIRING_B69_J5.md #1](integration-full.patch#L476) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H012 | J3/J4/J5 | [WIRING_B69_J5.md #2](integration-full.patch#L485) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H013 | J3/J4/J5 | [WIRING_B69_J5.md #3](integration-full.patch#L494) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H014 | J3/J4/J5 | [WIRING_B69_J5.md #4](integration-full.patch#L503) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H015 | J3/J4/J5 | [WIRING_B69_J5.md #5](integration-full.patch#L512) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H016 | J3/J4/J5 | [WIRING_B69_J5.md #6](integration-full.patch#L521) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H017 | J3/J4/J5 | [WIRING_B69_J5.md #7](integration-full.patch#L530) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H018 | J3/J4/J5 | [WIRING_B69_J5.md #8](integration-full.patch#L539) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H019 | J3/J4/J5 | [WIRING_B69_J5.md #9](integration-full.patch#L548) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H020 | J3/J4/J5 | [WIRING_B69_J5.md #10](integration-full.patch#L557) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H021 | J3/J4/J5 | [WIRING_B69_J5.md #11](integration-full.patch#L566) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H022 | J3/J4/J5 | [WIRING_B69_J5.md #12](integration-full.patch#L575) | documented deviation | Job handoff report/wiring links retargeted after rename; original handoff status retained |
| H023 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #1](integration-full.patch#L588) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H024 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #2](integration-full.patch#L663) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H025 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #3](integration-full.patch#L820) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H026 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #4](integration-full.patch#L833) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H027 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #5](integration-full.patch#L843) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H028 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #6](integration-full.patch#L855) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H029 | J3/J4/J5 | [mod_editor/capabilities/registry.v1.json #7](integration-full.patch#L996) | documented deviation | J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json |
| H030 | J5 | [mod_editor/core/mod_build.py #1](integration-full.patch#L1159) | applied exactly | J5 five BuildPlan fields, False/17/60/Retail defaults |
| H031 | J4 | [mod_editor/core/mod_build.py #2](integration-full.patch#L1171) | applied exactly | J4 climate path and haze boolean |
| H032 | J4/J5 | [mod_editor/core/mod_build.py #3](integration-full.patch#L1180) | applied exactly | J4/J5 wants_xbe_patch: haze/rules, climate data only |
| H033 | J4/J5 | [mod_editor/core/mod_build.py #4](integration-full.patch#L1189) | applied exactly | J4/J5 BASIC explicitly Off/Retail |
| H034 | J4/J5 | [mod_editor/core/mod_build.py #5](integration-full.patch#L1200) | applied exactly | J4/J5 ADVANCED explicitly Off/Retail |
| H035 | J4/J5 | [mod_editor/core/mod_build.py #6](integration-full.patch#L1211) | applied exactly | J4/J5 EXPERIMENTAL explicitly Off/Retail |
| H036 | J4 | [mod_editor/core/mod_build.py #7](integration-full.patch#L1222) | applied exactly | J4 module availability |
| H037 | J5 | [mod_editor/core/mod_build.py #8](integration-full.patch#L1231) | applied exactly | J5 module/allocator availability |
| H038 | J5 | [mod_editor/core/mod_build.py #9](integration-full.patch#L1241) | applied exactly | J5 inspect states and installed settings |
| H039 | J4 | [mod_editor/core/mod_build.py #10](integration-full.patch#L1250) | applied exactly | J4 climate requires image default |
| H040 | J4 | [mod_editor/core/mod_build.py #11](integration-full.patch#L1258) | applied exactly | J4 bounded ROST inspect |
| H041 | J4 | [mod_editor/core/mod_build.py #12](integration-full.patch#L1274) | applied exactly | J4 haze status inspect |
| H042 | J4 | [mod_editor/core/mod_build.py #13](integration-full.patch#L1289) | applied exactly | J4 strict weather types and stripped path |
| H043 | J5 | [mod_editor/core/mod_build.py #14](integration-full.patch#L1301) | applied exactly | J5 preflight allocator predicate |
| H044 | J3 | [mod_editor/core/mod_build.py #15](integration-full.patch#L1310) | applied exactly | J3 generic/prepared tier enables depth locks |
| H045 | J5 | [mod_editor/core/mod_build.py #16](integration-full.patch#L1325) | documented deviation | J5 full source settings check before deferred copy/project work |
| H046 | J4 | [mod_editor/core/mod_build.py #17](integration-full.patch#L1339) | applied exactly | J4 climate validation/frozen final-pass document and haze source checks |
| H047 | J4/J5 | [mod_editor/core/mod_build.py #18](integration-full.patch#L1367) | applied exactly | J4/J5 defer haze and allocation-dependent rules in initial pass |
| H048 | J5 | [mod_editor/core/mod_build.py #19](integration-full.patch#L1381) | applied exactly | J5 final allocator predicate |
| H049 | J4 | [mod_editor/core/mod_build.py #20](integration-full.patch#L1390) | applied exactly | J4 haze after helmet, before composed inspect, Off restores |
| H050 | J4 | [mod_editor/core/mod_build.py #21](integration-full.patch#L1411) | applied exactly | J4 climate after final ESPN/resource pass; reparse before publication |
| H051 | J4/J5 | [mod_editor/core/nfl2k5_build_settings.py #1](integration-full.patch#L1429) | documented deviation | J4/J5 explicit FEATURE_KEYS; actual serializer requires this beyond the J4 dataclass assumption |
| H052 | J4 | [mod_editor/core/nfl2k5_cave_manifest.py #1](integration-full.patch#L1442) | applied exactly | J4 reserve all four coefficient bytes including unchanged bytes |
| H053 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #2](integration-full.patch#L1454) | applied exactly | J4/J5 recorder imports |
| H054 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #3](integration-full.patch#L1465) | applied exactly | J4/J5 recorder module closure |
| H055 | J5 | [mod_editor/core/nfl2k5_cave_manifest.py #4](integration-full.patch#L1474) | applied exactly | J5 dormant complete allocation union |
| H056 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #5](integration-full.patch#L1483) | applied exactly | J4/J5 dormant writer applications |
| H057 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #6](integration-full.patch#L1494) | applied exactly | J4/J5 synthetic replay list |
| H058 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #7](integration-full.patch#L1503) | applied exactly | J4/J5 status verification list |
| H059 | J4/J5 | [mod_editor/core/nfl2k5_cave_manifest.py #8](integration-full.patch#L1512) | applied exactly | J4/J5 extra owner list |
| H060 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #1](integration-full.patch#L1525) | applied exactly | J5 imports |
| H061 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #2](integration-full.patch#L1535) | applied exactly | J5 three space and five runtime keys |
| H062 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #3](integration-full.patch#L1546) | applied exactly | J5 explicit Retail enum deferral and validator signature |
| H063 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #4](integration-full.patch#L1560) | applied exactly | J5 option domains |
| H064 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #5](integration-full.patch#L1572) | applied exactly | J5 selection signature and validator forwarding |
| H065 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #6](integration-full.patch#L1583) | applied exactly | J5 complete REQUESTS union |
| H066 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #7](integration-full.patch#L1593) | applied exactly | J5 allocator adapter signature/forwarding/scaleout |
| H067 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #8](integration-full.patch#L1609) | applied exactly | J5 clock adapter and status/settings helper |
| H068 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #9](integration-full.patch#L1638) | applied exactly | J5 grown status projection |
| H069 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #10](integration-full.patch#L1646) | documented deviation | J5 extracted complete-plan installed-settings check |
| H070 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #11](integration-full.patch#L1694) | applied exactly | J5 _apply_all settings signature |
| H071 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #12](integration-full.patch#L1703) | documented deviation | J5 private deferred-settings flag |
| H072 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #13](integration-full.patch#L1711) | documented deviation | J5 defer only intermediate installed-setting validation |
| H073 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #14](integration-full.patch#L1734) | applied exactly | J5 final allocation predicate |
| H074 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #15](integration-full.patch#L1743) | applied exactly | J5 install coin, clock, scrambles immediately after accelerated clock |
| H075 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #16](integration-full.patch#L1755) | applied exactly | J5 bare-XBE entrypoint signature |
| H076 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #17](integration-full.patch#L1764) | applied exactly | J5 bare-XBE work predicate |
| H077 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #18](integration-full.patch#L1773) | applied exactly | J5 image entrypoint signature |
| H078 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #19](integration-full.patch#L1782) | documented deviation | J5 explain complete-plan preflight before partial pass |
| H079 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #20](integration-full.patch#L1791) | applied exactly | J5 image work predicate |
| H080 | J5 | [mod_editor/core/nfl2k5_throw_tuning.py #21](integration-full.patch#L1800) | documented deviation | J5 complete-plan preflight and unchanged intermediate replay |
| H081 | J3/J5 | [mod_editor/core/providers.py #1](integration-full.patch#L1824) | applied exactly | J3/J5 eight added dependency pins |
| H082 | J5 | [mod_editor/core/providers.py #2](integration-full.patch#L1839) | applied exactly | J5 dispatcher pin |
| H083 | J4/J5 | [mod_editor/core/providers.py #3](integration-full.patch#L1848) | applied exactly | J4/J5 saved settings pin |
| H084 | J3/J4/J5 | [mod_editor/core/providers.py #4](integration-full.patch#L1857) | applied exactly | J3/J4/J5 mod_build pin |
| H085 | J5 | [mod_editor/gui/beta62_options.py #1](integration-full.patch#L1870) | applied exactly | J5 exact two boolean captions/help; CPU scrambles remains an enum |
| H086 | J5 | [mod_editor/gui/build_panel_qt.py #1](integration-full.patch#L1885) | applied exactly | J5 cutoff and Retail/Modern selectors, defaults, accessible labels |
| H087 | J4 | [mod_editor/gui/build_panel_qt.py #2](integration-full.patch#L1916) | applied exactly | J4 climate choose/editor/status and reversible haze controls |
| H088 | J4 | [mod_editor/gui/build_panel_qt.py #3](integration-full.patch#L1946) | applied exactly | J4 source gates, climate reset and installed haze projection |
| H089 | J5 | [mod_editor/gui/build_panel_qt.py #4](integration-full.patch#L1968) | applied exactly | J5 preset reset of cutoff and scramble selectors |
| H090 | J4 | [mod_editor/gui/build_panel_qt.py #5](integration-full.patch#L1983) | applied exactly | J4 boolean/path control map |
| H091 | J4 | [mod_editor/gui/build_panel_qt.py #6](integration-full.patch#L1991) | applied exactly | J4 plan path/haze fields |
| H092 | J5 | [mod_editor/gui/build_panel_qt.py #7](integration-full.patch#L2000) | applied exactly | J5 plan cutoff/enum values |
| H093 | J4/J5 | [mod_editor/gui/build_panel_qt.py #8](integration-full.patch#L2010) | applied exactly | J4/J5 has_work predicates |
| H094 | J4/J5 | [mod_editor/gui/build_panel_qt.py #9](integration-full.patch#L2020) | applied exactly | J4/J5 selected labels, cutoff values and explicit haze restoration |
| H095 | J4 | [mod_editor/gui/build_panel_qt.py #10](integration-full.patch#L2038) | applied exactly | J4 climate blocker |
| H096 | J5 | [mod_editor/gui/build_panel_qt.py #11](integration-full.patch#L2049) | wrong | J5 installed settings lock and enum source gating; source-reset omission D1 |
| H097 | J4 | [mod_editor/gui/build_panel_qt.py #12](integration-full.patch#L2087) | applied exactly | J4 editor launch/save signal and bounded climate preflight helper |
| H098 | J4 | [mod_editor/gui/build_panel_qt.py #13](integration-full.patch#L2135) | applied exactly | J4 confirmation plan basename |
| H099 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #1](integration-full.patch#L2148) | documented deviation | J4/J5 rows; climate path and scramble enum are informational, never booleans |
| H100 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #2](integration-full.patch#L2162) | documented deviation | J4/J5 exact captions/help |
| H101 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #3](integration-full.patch#L2172) | documented deviation | J4/J5 full-disc gates |
| H102 | J4 | [mod_editor/gui/gameplay_patches_panel_qt.py #4](integration-full.patch#L2181) | documented deviation | J4 weather navigation signal |
| H103 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #5](integration-full.patch#L2189) | documented deviation | J4/J5 weather editor action and Retail/Modern enum |
| H104 | J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #6](integration-full.patch#L2218) | documented deviation | J5 cutoff selectors |
| H105 | J4 | [mod_editor/gui/gameplay_patches_panel_qt.py #7](integration-full.patch#L2242) | documented deviation | J4 reversible haze source state |
| H106 | J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #8](integration-full.patch#L2256) | documented deviation | J5 plan cutoff/enum projection |
| H107 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #9](integration-full.patch#L2268) | wrong | J4/J5 installed locks, source gating and has_work; source-reset omission D1 |
| H108 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #10](integration-full.patch#L2315) | documented deviation | J4/J5 selection helpers and standalone weather-editor fallback |
| H109 | J4/J5 | [mod_editor/gui/gameplay_patches_panel_qt.py #11](integration-full.patch#L2341) | documented deviation | J4/J5 actionable selection/confirmation including restoration and cutoff |
| H110 | J5 | [mod_editor/gui/gameplay_project_ui.py #1](integration-full.patch#L2365) | documented deviation | J5 restore cutoff/enum |
| H111 | J4 | [mod_editor/gui/gameplay_project_ui.py #2](integration-full.patch#L2375) | documented deviation | J4 restore climate path |
| H112 | J5 | [mod_editor/gui/gameplay_project_ui.py #3](integration-full.patch#L2384) | documented deviation | J5 bidirectional combo signals |
| H113 | J5 | [mod_editor/gui/gameplay_project_ui.py #4](integration-full.patch#L2393) | documented deviation | J5 bidirectional combo values |
| H114 | J3 | [mod_editor/gui/my_career_panel_qt.py #1](integration-full.patch#L2406) | applied exactly | J3 prospects import |
| H115 | J3 | [mod_editor/gui/my_career_panel_qt.py #2](integration-full.patch#L2414) | applied exactly | J3 honest MyCareer page description |
| H116 | J3 | [mod_editor/gui/my_career_panel_qt.py #3](integration-full.patch#L2426) | applied exactly | J3 tier/prototype controls and tier-owned starting depth place |
| H117 | J3 | [mod_editor/gui/my_career_panel_qt.py #4](integration-full.patch#L2454) | applied exactly | J3 saved caller choices, retail default and help |
| H118 | J3 | [mod_editor/gui/my_career_panel_qt.py #5](integration-full.patch#L2472) | applied exactly | J3 prototype aliases/Pocket default |
| H119 | J3 | [mod_editor/gui/my_career_panel_qt.py #6](integration-full.patch#L2485) | applied exactly | J3 load caller and Supersim together |
| H120 | J3 | [mod_editor/gui/my_career_panel_qt.py #7](integration-full.patch#L2508) | applied exactly | J3 capture caller on export |
| H121 | J3 | [mod_editor/gui/my_career_panel_qt.py #8](integration-full.patch#L2516) | applied exactly | J3 one signed write_settings export |
| H122 | J3 | [mod_editor/gui/my_career_panel_qt.py #9](integration-full.patch#L2529) | applied exactly | J3 disable caller while working |
| H123 | J3 | [mod_editor/gui/my_career_panel_qt.py #10](integration-full.patch#L2537) | applied exactly | J3 restore caller availability after work |
| H124 | J3 | [mod_editor/gui/my_career_panel_qt.py #11](integration-full.patch#L2545) | applied exactly | J3 pass prospect tier to creation |
| H125 | J4 | [mod_editor/gui/studio_qt.py #1](integration-full.patch#L2559) | documented deviation | J4 existing Gameplay weather signal opens Build weather editor |
| H126 | J4 | [mod_editor/gui/studio_qt.py #2](integration-full.patch#L2567) | documented deviation | J4 existing Gameplay weather signal opens Build weather editor |
| H127 | J4 | [packaging/check_2k5_mod_studio_runtime.py #1](integration-full.patch#L2582) | documented deviation | J4 studio source pin |
| H128 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #2](integration-full.patch#L2591) | documented deviation | J3/J4/J5 separate weather/UI/tool runtime pins |
| H129 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #3](integration-full.patch#L2612) | documented deviation | J3/J4/J5 executable runtime contract: pins/defaults/controls |
| H130 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #4](integration-full.patch#L2657) | documented deviation | J3/J4/J5 fourteen additional imports |
| H131 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #5](integration-full.patch#L2679) | documented deviation | J3/J4/J5 execute runtime contract |
| H132 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #6](integration-full.patch#L2687) | documented deviation | J3/J4/J5 shared registry 172 and 2K5 catalog 99 assertions |
| H133 | J3/J4/J5 | [packaging/check_2k5_mod_studio_runtime.py #7](integration-full.patch#L2701) | documented deviation | J3/J4/J5 printed shared registry/catalog pins |
| H134 | J3/J4/J5 | [packaging/check_apf2k8_mod_studio_runtime.py #1](integration-full.patch#L2714) | applied exactly | J3/J4/J5 shared registry 172; APF product unchanged |
| H135 | J3/J4/J5 | [packaging/release-allowlist.txt #1](integration-full.patch#L2727) | applied exactly | J3/J4/J5 ten core sources, four tools, two research docs; no compiler/emulator dependency |
| H136 | J3/J4/J5 | [reports/b69_a2b/allocation-delta.json #1](integration-full.patch#L2754) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H137 | J3/J4/J5 | [reports/b69_a2b/assembly-mycareer-hooks.log #1](integration-full.patch#L7544) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H138 | J3/J4/J5 | [reports/b69_a2b/assembly-mycareer-runtime.log #1](integration-full.patch#L7551) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H139 | J3/J4/J5 | [reports/b69_a2b/assembly-rules.log #1](integration-full.patch#L7558) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H140 | J3/J4/J5 | [reports/b69_a2b/core-repin.log #1](integration-full.patch#L7567) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H141 | J3/J4/J5 | [reports/b69_a2b/deferred-repin.log #1](integration-full.patch#L7581) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H142 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_build_panel_qt.log #1](integration-full.patch#L7595) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H143 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_mod_build.log #1](integration-full.patch#L7606) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H144 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_mod_build_beta62_integration.log #1](integration-full.patch#L7617) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H145 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_mod_build_beta62_integration2.log #1](integration-full.patch#L7628) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H146 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_mod_build_beta62_integration3.log #1](integration-full.patch#L7635) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H147 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_nfl2k5_accelerated_clock.log #1](integration-full.patch#L7646) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H148 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_nfl2k5_b69_rules.log #1](integration-full.patch#L7657) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H149 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/test_nfl2k5_my_career_b69_wiring.log #1](integration-full.patch#L7668) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H150 | J3/J4/J5 | [reports/b69_a2b/dispatcher-regressions/tests.json #1](integration-full.patch#L7679) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H151 | J3/J4/J5 | [reports/b69_a2b/evidence-generation.log #1](integration-full.patch#L7783) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H152 | J3/J4/J5 | [reports/b69_a2b/final-audit.json #1](integration-full.patch#L7792) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H153 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_gameplay_patches_panel_qt.log #1](integration-full.patch#L7837) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H154 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_nfl2k5_accelerated_clock.log #1](integration-full.patch#L7866) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H155 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_nfl2k5_b69_rules.log #1](integration-full.patch#L7877) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H156 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_nfl2k5_build_service.log #1](integration-full.patch#L7888) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H157 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_nfl2k5_throw_tuning.log #1](integration-full.patch#L7963) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H158 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/test_throw_tuning_panel_qt.log #1](integration-full.patch#L7974) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H159 | J3/J4/J5 | [reports/b69_a2b/final-dispatcher/tests.json #1](integration-full.patch#L7985) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H160 | J3/J4/J5 | [reports/b69_a2b/final-gameplay-panel/test_gameplay_patches_panel_qt.log #1](integration-full.patch#L8065) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H161 | J3/J4/J5 | [reports/b69_a2b/final-gameplay-panel/tests.json #1](integration-full.patch#L8076) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H162 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_nfl2k5_accelerated_clock_manifest.log #1](integration-full.patch#L8096) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H163 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_nfl2k5_cave_oracle.log #1](integration-full.patch#L8107) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H164 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_nfl2k5_music_playlist_manifest.log #1](integration-full.patch#L8118) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H165 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_nfl2k5_my_career_manifest.log #1](integration-full.patch#L8129) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H166 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_nfl2k5_owner_pairwise_composition.log #1](integration-full.patch#L8140) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H167 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_xbe_patch_cave_references.log #1](integration-full.patch#L8151) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H168 | J3/J4/J5 | [reports/b69_a2b/final-gates/test_xbe_patch_memory_writes.log #1](integration-full.patch#L8162) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H169 | J3/J4/J5 | [reports/b69_a2b/final-gates/tests.json #1](integration-full.patch#L8173) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H170 | J3/J4/J5 | [reports/b69_a2b/final-simwin/test_nfl2k5_simulated_windows_build.log #1](integration-full.patch#L8265) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H171 | J3/J4/J5 | [reports/b69_a2b/final-simwin/tests.json #1](integration-full.patch#L8277) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H172 | J3/J4/J5 | [reports/b69_a2b/final-source-fingerprints.json #1](integration-full.patch#L8297) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H173 | J3/J4/J5 | [reports/b69_a2b/final-tests.json #1](integration-full.patch#L8636) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H174 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_2k5_build_is_explainable.log #1](integration-full.patch#L9618) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H175 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_apf_studio_installer.log #1](integration-full.patch#L9629) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H176 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_b69_a2b_game_wiring.log #1](integration-full.patch#L9666) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H177 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_beta66_d1_panels.log #1](integration-full.patch#L9677) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H178 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_build_panel_qt.log #1](integration-full.patch#L9688) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H179 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_capability_registry_module_commands.log #1](integration-full.patch#L9699) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H180 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_discord_bugs_1_wiring.log #1](integration-full.patch#L9710) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H181 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_discord_bugs_2_wiring.log #1](integration-full.patch#L9721) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H182 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_mod_build.log #1](integration-full.patch#L9732) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H183 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_mod_build_beta62_integration.log #1](integration-full.patch#L9743) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H184 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_mod_build_beta62_integration3.log #1](integration-full.patch#L9754) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H185 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_nfl2k5_my_career_b69_wiring.log #1](integration-full.patch#L9765) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H186 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_nfl2k5_my_career_panel.log #1](integration-full.patch#L9776) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H187 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_phase1_packaging.log #1](integration-full.patch#L9787) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H188 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_product_catalog.log #1](integration-full.patch#L9798) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H189 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_provider_integrity.log #1](integration-full.patch#L9809) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H190 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_providers.log #1](integration-full.patch#L9820) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H191 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_shipped_tools_posix_only.log #1](integration-full.patch#L9831) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H192 | J3/J4/J5 | [reports/b69_a2b/final-wiring/test_validate_all_capabilities.log #1](integration-full.patch#L9842) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H193 | J3/J4/J5 | [reports/b69_a2b/final-wiring/tests.json #1](integration-full.patch#L9867) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H194 | J3/J4/J5 | [reports/b69_a2b/gate-case-counts.json #1](integration-full.patch#L10103) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H195 | J3/J4/J5 | [reports/b69_a2b/gate-manifest-summary.json #1](integration-full.patch#L10116) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H196 | J3/J4/J5 | [reports/b69_a2b/gates/test_nfl2k5_accelerated_clock_manifest.log #1](integration-full.patch#L12129) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H197 | J3/J4/J5 | [reports/b69_a2b/gates/test_nfl2k5_cave_oracle.log #1](integration-full.patch#L12154) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H198 | J3/J4/J5 | [reports/b69_a2b/gates/test_nfl2k5_music_playlist_manifest.log #1](integration-full.patch#L12193) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H199 | J3/J4/J5 | [reports/b69_a2b/gates/test_nfl2k5_my_career_manifest.log #1](integration-full.patch#L12204) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H200 | J3/J4/J5 | [reports/b69_a2b/gates/test_nfl2k5_owner_pairwise_composition.log #1](integration-full.patch#L12215) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H201 | J3/J4/J5 | [reports/b69_a2b/gates/test_xbe_patch_cave_references.log #1](integration-full.patch#L12226) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H202 | J3/J4/J5 | [reports/b69_a2b/gates/test_xbe_patch_memory_writes.log #1](integration-full.patch#L12237) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H203 | J3/J4/J5 | [reports/b69_a2b/gates/tests.json #1](integration-full.patch#L12248) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H204 | J3/J4/J5 | [reports/b69_a2b/hydration.json #1](integration-full.patch#L12340) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H205 | J3/J4/J5 | [reports/b69_a2b/input-bundle-verification.json #1](integration-full.patch#L12468) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H206 | J3/J4/J5 | [reports/b69_a2b/integration-audit.json #1](integration-full.patch#L12490) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H207 | J3/J4/J5 | [reports/b69_a2b/integration-complete/test_b69_a2b_game_wiring.log #1](integration-full.patch#L12534) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H208 | J3/J4/J5 | [reports/b69_a2b/integration-complete/tests.json #1](integration-full.patch#L12545) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H209 | J3/J4/J5 | [reports/b69_a2b/integration-final/test_b69_a2b_game_wiring.log #1](integration-full.patch#L12565) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H210 | J3/J4/J5 | [reports/b69_a2b/integration-final/tests.json #1](integration-full.patch#L12608) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H211 | J3/J4/J5 | [reports/b69_a2b/integration-rerun/test_b69_a2b_game_wiring.log #1](integration-full.patch#L12628) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H212 | J3/J4/J5 | [reports/b69_a2b/integration-rerun/test_nfl2k5_my_career_panel.log #1](integration-full.patch#L12683) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H213 | J3/J4/J5 | [reports/b69_a2b/integration-rerun/tests.json #1](integration-full.patch#L12694) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H214 | J3/J4/J5 | [reports/b69_a2b/integration/test_b69_a2b_game_wiring.log #1](integration-full.patch#L12726) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H215 | J3/J4/J5 | [reports/b69_a2b/integration/tests.json #1](integration-full.patch#L12852) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H216 | J3/J4/J5 | [reports/b69_a2b/job-test-inventory.json #1](integration-full.patch#L12872) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H217 | J3/J4/J5 | [reports/b69_a2b/manifest-final.log #1](integration-full.patch#L12895) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H218 | J3/J4/J5 | [reports/b69_a2b/manifest-generation-final.log #1](integration-full.patch#L12907) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H219 | J3/J4/J5 | [reports/b69_a2b/manifest-generation.log #1](integration-full.patch#L12919) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H220 | J3/J4/J5 | [reports/b69_a2b/measure-allocation.py #1](integration-full.patch#L12939) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H221 | J3/J4/J5 | [reports/b69_a2b/native-code-identity.json #1](integration-full.patch#L12957) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H222 | J3/J4/J5 | [reports/b69_a2b/native/test_beta66_supersim_wiring.log #1](integration-full.patch#L13049) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H223 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_accelerated_clock.log #1](integration-full.patch#L13060) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H224 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_b661_transition.log #1](integration-full.patch#L13071) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H225 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_b68_game_composition.log #1](integration-full.patch#L13082) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H226 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_b69_rules.log #1](integration-full.patch#L13093) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H227 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_b69_rules_series.log #1](integration-full.patch#L13104) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H228 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career.log #1](integration-full.patch#L13115) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H229 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_b69_wiring.log #1](integration-full.patch#L13126) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H230 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_completion.log #1](integration-full.patch#L13137) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H231 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_control.log #1](integration-full.patch#L13148) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H232 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_choice.log #1](integration-full.patch#L13159) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H233 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_frame.log #1](integration-full.patch#L13170) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H234 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_injury.log #1](integration-full.patch#L13181) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H235 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_period.log #1](integration-full.patch#L13192) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H236 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_timeout.log #1](integration-full.patch#L13203) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H237 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_cpu_turnover.log #1](integration-full.patch#L13214) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H238 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_creation_boundary.log #1](integration-full.patch#L13225) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H239 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_draft.log #1](integration-full.patch#L13236) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H240 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_frontend.log #1](integration-full.patch#L13247) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H241 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_generic_build.log #1](integration-full.patch#L13258) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H242 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_inline.log #1](integration-full.patch#L13269) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H243 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_m3_budget.log #1](integration-full.patch#L13280) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H244 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_m3_menus.log #1](integration-full.patch#L13291) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H245 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_mode4.log #1](integration-full.patch#L13302) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H246 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_mode5.log #1](integration-full.patch#L13313) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H247 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_mode_audit.log #1](integration-full.patch#L13324) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H248 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_mode_routes.log #1](integration-full.patch#L13335) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H249 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_panel.log #1](integration-full.patch#L13346) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H250 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_playcalling.log #1](integration-full.patch#L13374) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H251 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_played.log #1](integration-full.patch#L13399) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H252 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_position_inputs.log #1](integration-full.patch#L13410) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H253 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_prospects.log #1](integration-full.patch#L13421) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H254 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_season.log #1](integration-full.patch#L13432) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H255 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_settings.log #1](integration-full.patch#L13443) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H256 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_signing.log #1](integration-full.patch#L13454) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H257 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_unicorn.log #1](integration-full.patch#L13465) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H258 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_upgrades.log #1](integration-full.patch#L13476) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H259 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_my_career_week.log #1](integration-full.patch#L13487) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H260 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_practice_reserves.log #1](integration-full.patch#L13498) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H261 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_roster_arena_growth.log #1](integration-full.patch#L13509) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H262 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_supersim.log #1](integration-full.patch#L13520) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H263 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_supersim_live.log #1](integration-full.patch#L13531) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H264 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_weather.log #1](integration-full.patch#L13550) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H265 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_weather_editor.log #1](integration-full.patch#L13561) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H266 | J3/J4/J5 | [reports/b69_a2b/native/test_nfl2k5_weather_native.log #1](integration-full.patch#L13572) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H267 | J3/J4/J5 | [reports/b69_a2b/native/tests.json #1](integration-full.patch#L13583) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H268 | J3/J4/J5 | [reports/b69_a2b/packaging-repin.log #1](integration-full.patch#L14131) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H269 | J3/J4/J5 | [reports/b69_a2b/packaging-rerun/test_apf_studio_installer.log #1](integration-full.patch#L14142) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H270 | J3/J4/J5 | [reports/b69_a2b/packaging-rerun/test_phase1_packaging.log #1](integration-full.patch#L14179) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H271 | J3/J4/J5 | [reports/b69_a2b/packaging-rerun/test_product_catalog.log #1](integration-full.patch#L14190) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H272 | J3/J4/J5 | [reports/b69_a2b/packaging-rerun/tests.json #1](integration-full.patch#L14201) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H273 | J3/J4/J5 | [reports/b69_a2b/pin-delta.json #1](integration-full.patch#L14245) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H274 | J3/J4/J5 | [reports/b69_a2b/protected-wiring.patch #1](integration-full.patch#L14427) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H275 | J3/J4/J5 | [reports/b69_a2b/release-audit-final.log #1](integration-full.patch#L18927) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H276 | J3/J4/J5 | [reports/b69_a2b/release-audit.log #1](integration-full.patch#L18934) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H277 | J3/J4/J5 | [reports/b69_a2b/run-tests.py #1](integration-full.patch#L18941) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H278 | J3/J4/J5 | [reports/b69_a2b/runtime-early.log #1](integration-full.patch#L18975) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H279 | J3/J4/J5 | [reports/b69_a2b/runtime-final.log #1](integration-full.patch#L18982) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H280 | J3/J4/J5 | [reports/b69_a2b/runtime-stage.log #1](integration-full.patch#L18989) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H281 | J3/J4/J5 | [reports/b69_a2b/simulated-windows-build.json #1](integration-full.patch#L18996) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H282 | J3/J4/J5 | [reports/b69_a2b/simwin/test_nfl2k5_simulated_windows_build.log #1](integration-full.patch#L20803) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H283 | J3/J4/J5 | [reports/b69_a2b/simwin/tests.json #1](integration-full.patch#L20815) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H284 | J3/J4/J5 | [reports/b69_a2b/stage-final.log #1](integration-full.patch#L20835) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H285 | J3/J4/J5 | [reports/b69_a2b/stage.log #1](integration-full.patch#L20842) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H286 | J3/J4/J5 | [reports/b69_a2b/test-build-panel-early.log #1](integration-full.patch#L20849) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H287 | J3/J4/J5 | [reports/b69_a2b/test-discord-wiring-early.log #1](integration-full.patch#L20860) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H288 | J3/J4/J5 | [reports/b69_a2b/test-mycareer-integrated-early.log #1](integration-full.patch#L20867) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H289 | J3/J4/J5 | [reports/b69_a2b/test-mycareer-proposed.log #1](integration-full.patch#L20878) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H290 | J3/J4/J5 | [reports/b69_a2b/test-product-catalog-early.log #1](integration-full.patch#L20889) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H291 | J3/J4/J5 | [reports/b69_a2b/test-provider-integrity-early.log #1](integration-full.patch#L20989) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H292 | J3/J4/J5 | [reports/b69_a2b/ui-repin.log #1](integration-full.patch#L21008) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H293 | J3/J4/J5 | [reports/b69_a2b/wiring/test_2k5_build_is_explainable.log #1](integration-full.patch#L21022) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H294 | J3/J4/J5 | [reports/b69_a2b/wiring/test_apf_studio_installer.log #1](integration-full.patch#L21033) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H295 | J3/J4/J5 | [reports/b69_a2b/wiring/test_beta66_d1_panels.log #1](integration-full.patch#L21083) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H296 | J3/J4/J5 | [reports/b69_a2b/wiring/test_build_panel_qt.log #1](integration-full.patch#L21094) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H297 | J3/J4/J5 | [reports/b69_a2b/wiring/test_capability_registry_module_commands.log #1](integration-full.patch#L21105) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H298 | J3/J4/J5 | [reports/b69_a2b/wiring/test_discord_bugs_1_wiring.log #1](integration-full.patch#L21116) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H299 | J3/J4/J5 | [reports/b69_a2b/wiring/test_discord_bugs_2_wiring.log #1](integration-full.patch#L21127) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H300 | J3/J4/J5 | [reports/b69_a2b/wiring/test_mod_build.log #1](integration-full.patch#L21138) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H301 | J3/J4/J5 | [reports/b69_a2b/wiring/test_mod_build_beta62_integration3.log #1](integration-full.patch#L21149) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H302 | J3/J4/J5 | [reports/b69_a2b/wiring/test_phase1_packaging.log #1](integration-full.patch#L21160) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H303 | J3/J4/J5 | [reports/b69_a2b/wiring/test_product_catalog.log #1](integration-full.patch#L21186) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H304 | J3/J4/J5 | [reports/b69_a2b/wiring/test_provider_integrity.log #1](integration-full.patch#L21212) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H305 | J3/J4/J5 | [reports/b69_a2b/wiring/test_providers.log #1](integration-full.patch#L21223) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H306 | J3/J4/J5 | [reports/b69_a2b/wiring/test_shipped_tools_posix_only.log #1](integration-full.patch#L21234) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H307 | J3/J4/J5 | [reports/b69_a2b/wiring/test_validate_all_capabilities.log #1](integration-full.patch#L21245) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H308 | J3/J4/J5 | [reports/b69_a2b/wiring/tests.json #1](integration-full.patch#L21270) | documented deviation | J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b |
| H309 | J3/J4/J5 | [tests/mod_editor/test_apf_studio_installer.py #1](integration-full.patch#L21457) | applied exactly | J3/J4/J5 shared registry 172 |
| H310 | J3/J4/J5 | [tests/mod_editor/test_b69_a2b_game_wiring.py #1](integration-full.patch#L21471) | documented deviation | J3/J4/J5 additional compact image, option, replay, refusal and UI evidence |
| H311 | J4/J5 | [tests/mod_editor/test_gameplay_patches_panel_qt.py #1](integration-full.patch#L21709) | documented deviation | J4/J5 align row/caption/foreign-source expectations |
| H312 | J4/J5 | [tests/mod_editor/test_gameplay_patches_panel_qt.py #2](integration-full.patch#L21735) | documented deviation | J4/J5 align row/caption/foreign-source expectations |
| H313 | J3 | [tests/mod_editor/test_nfl2k5_my_career_b69_wiring.py #1](integration-full.patch#L21760) | documented deviation | J3 run integrated panel/build source, preserve original proposed-panel generator |
| H314 | J3 | [tests/mod_editor/test_nfl2k5_my_career_b69_wiring.py #2](integration-full.patch#L21766) | documented deviation | J3 run integrated panel/build source, preserve original proposed-panel generator |
| H315 | J3 | [tests/mod_editor/test_nfl2k5_my_career_panel.py #1](integration-full.patch#L21786) | documented deviation | J3 four QB labels sharing three native styles, Pocket default |
| H316 | J3 | [tests/mod_editor/test_nfl2k5_my_career_panel.py #2](integration-full.patch#L21795) | documented deviation | J3 four QB labels sharing three native styles, Pocket default |
| H317 | J4 | [tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py #1](integration-full.patch#L21808) | applied exactly | J4 haze added to pair matrix |
| H318 | J5 | [tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py #1](integration-full.patch#L21820) | documented deviation | J5 common helper excluded from double attribution; calling owner still recorded |
| H319 | J3/J4/J5 | [tests/mod_editor/test_nfl2k5_simulated_windows_build.py #1](integration-full.patch#L21834) | documented deviation | J3/J4/J5 additional existing non-POSIX shim/Experimental composition proof |
| H320 | J3/J4/J5 | [tests/mod_editor/test_phase1_packaging.py #1](integration-full.patch#L21908) | applied exactly | J3/J4/J5 shared registry 172 and 2K5 catalog 99 |
| H321 | J3/J4/J5 | [tests/mod_editor/test_product_catalog.py #1](integration-full.patch#L21921) | applied exactly | J3/J4/J5 exact seven new IDs |
| H322 | J3/J4/J5 | [tests/mod_editor/test_product_catalog.py #2](integration-full.patch#L21935) | applied exactly | J3/J4/J5 99 unique rows |
| H323 | J3/J4/J5 | [tests/mod_editor/test_product_catalog.py #3](integration-full.patch#L21944) | applied exactly | J3/J4/J5 stadium/menu/gameplay section totals |
| H324 | J3/J4/J5 | [tests/mod_editor/test_product_catalog.py #4](integration-full.patch#L21960) | applied exactly | J3/J4/J5 total tuple (99,77,8,1,0,10,3) |
| H325 | J3/J4/J5 | [tests/mod_editor/test_product_catalog.py #5](integration-full.patch#L21969) | applied exactly | J3/J4/J5 provider binding count |
| H326 | J3/J5 | [tests/mod_editor/test_provider_integrity.py #1](integration-full.patch#L21982) | applied exactly | J3/J5 combined exact unified closure 280 |
| H327 | J4 | [tests/nfl2k5_allocator_stack.py #1](integration-full.patch#L21995) | applied exactly | J4 haze import |
| H328 | J4 | [tests/nfl2k5_allocator_stack.py #2](integration-full.patch#L22003) | applied exactly | J4 haze composed owner |
| H329 | J4 | [tests/nfl2k5_allocator_stack.py #3](integration-full.patch#L22012) | applied exactly | J4 full four-byte reservation only after other-owner overlap refusal |
| H330 | J3 | [tools/mycareer_mode/b69_registry_rows.json #1](integration-full.patch#L22030) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H331 | J3 | [tools/mycareer_mode/b69_registry_rows.json #2](integration-full.patch#L22039) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H332 | J3 | [tools/mycareer_mode/b69_registry_rows.json #3](integration-full.patch#L22048) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H333 | J3 | [tools/mycareer_mode/b69_registry_rows.json #4](integration-full.patch#L22057) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H334 | J3 | [tools/mycareer_mode/b69_registry_rows.json #5](integration-full.patch#L22066) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H335 | J3 | [tools/mycareer_mode/b69_registry_rows.json #6](integration-full.patch#L22075) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H336 | J3 | [tools/mycareer_mode/b69_registry_rows.json #7](integration-full.patch#L22084) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H337 | J3 | [tools/mycareer_mode/b69_registry_rows.json #8](integration-full.patch#L22093) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H338 | J3 | [tools/mycareer_mode/b69_registry_rows.json #9](integration-full.patch#L22102) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |
| H339 | J3 | [tools/mycareer_mode/b69_registry_rows.json #10](integration-full.patch#L22111) | documented deviation | J3 handoff paths/integration wording match renamed report and applied UI |

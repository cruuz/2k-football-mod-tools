# b72-s11: complete primary marks inside the enlarged logo wells

Beta 73 candidate on base `refs/astra/b72-s10/b72-s10` at `c3b3b53a2`. Washington's left arm is restored. All 32 primary marks retain exactly 100 percent of complete source ink in both native aspects and at both ends. Zero crop is allowed for every class, including circles and shields. Each fit comes from its own source alpha bounds, aspect, complete transformed ink and safe placement. The 32 marks produce 21 distinct texture sizes.

Only the per-team logo-fit metadata and its existing replication digest change in the shipped artwork. The s10 template PNG, wings, scores, raised plate, thinner housing, palettes, native owners, inventories and provider sources are unchanged. The existing wide-mark test now expects the complete Chiefs silhouette's aspect with the same tolerance; a new independent paste regression catches the original cropped fits.

| Required residual | S10 player pixels | S11 player pixels | S10 gain vs S9 | S11 gain vs S9 |
|---|---:|---:|---:|---:|
| Logo | 1,931.75 | 1,931.75 | 30.9% | 30.9% |
| Wing | 1,524.00 | 1,502.50 | 19.3% | 20.4% |
| Score | 16.75 | 16.75 | 92.4% | 92.4% |

Fresh s10 renders reproduce every recorded residual row exactly. [GAPS.md](reports/b72_s11/GAPS.md) retains all features and the unchanged metric definition. These are overlapping occupancy proxies, not perceptual identity scores. All remaining broadcast residuals stay open.

| Player-scale comparison | 16:9 | 4:3 |
|---|---|---|
| Washington at Chargers | [sheet](reports/b72_s11/sheets/WAS_LAC_169.png) | [sheet](reports/b72_s11/sheets/WAS_LAC_43.png) |
| Raiders at Texans | [sheet](reports/b72_s11/sheets/LV_HOU_169.png) | [sheet](reports/b72_s11/sheets/LV_HOU_43.png) |
| Steelers at Titans | [sheet](reports/b72_s11/sheets/PIT_TEN_169.png) | [sheet](reports/b72_s11/sheets/PIT_TEN_43.png) |
| All 52 roster slots | [contact sheet](reports/b72_s11/all_teams_169.png) | [contact sheet](reports/b72_s11/all_teams_43.png) |

Open at 100 percent. Before and after candidates use the same native 448-line HUD and 617-pixel player bar. The Washington sheets retain all four supplied disc r captures, labelled with their original provenance. The 20 historical/all-star/user slots retain their existing neutral fallback and are included in the 104 label checks; no new primary artwork is claimed for those slots.

[INK_RETENTION.md](reports/b72_s11/INK_RETENTION.md) gives every primary team's before/after survival fractions in both aspects. [FIDELITY.md](reports/b72_s11/FIDELITY.md) describes complete-source and filtered-ink denominators, rounded wing containment, sampling guard, actual native projection and limitations. Washington rises from 81.3428 percent source-alpha containment to 100 percent. The PNG sources are unchanged.

All 36 default standalone files pass, with 316 test cases and 8 existing skips. All 104 label measurements and all 1,350 retained event-frame records exactly equal s10. Both product closures, provider integrity, replication pins, existing allowlist membership and the 31 focused owner-composition pairs pass. Isolated re-authoring is byte-identical, and native runtime regeneration passes. Appended size is 325,216 bytes in both aspects; RX is 4,086/4,096 and RW is 128 bytes. No component grows.

[VALIDATION.md](reports/b72_s11/VALIDATION.md) lists commands, logs and limits. The broader memory-write and cave-reference suites each time out at 420 seconds. The cave-oracle suite has two errors for the inherited stale `nfl2k5_scorebug_exact.py` manifest fingerprint; its other 27 cases pass. The standalone phase-one packaging suite passes. The protected manifest and native sources remain unchanged; [WIRING.md](WIRING.md) retains the integrator's manifest-regeneration requirement. No blanket repository-wide pass is claimed.

[JEV_REVIEW.md](reports/b72_s11/JEV_REVIEW.md) records the proof-method review and the reviewed expected-aspect flag from the installed diff-gate recipe. [JEV_USAGE.json](reports/b72_s11/JEV_USAGE.json) contains every charged call below the $1 cap. Jev reads evidence text and does not certify pixels. The final handoff fact-check is retained with its raw request and response.

PROVED here means source-ink containment, bounded native CPU/software-raster execution and the listed integrity checks. GPU/display calibration, the readability of every fine source detail after SD sampling and all played behaviour remain UNWITNESSED. No emulator, disc image build, push, publication or release action ran. Temporary product staging was used only for closure validation. The existing EXPERIMENTAL option stays off in every preset. A later played retest must check Washington's W, Raiders lettering, circular borders and event transitions; no in-game result is claimed.

Implementation commit: `eafd053db`. Shared Git metadata is read-only, so branch `b72-s11` lives in `.scratch/b72-s11.git` with this checkout as its work tree. Delivery is `.scratch/astra-b72-s11.bundle`, using `c3b3b53a2` as prerequisite. `bundle.py` verifies import, tree identity and the committed 20-line summary plus `ASTRA_DONE`. Unrelated hub inputs, retail symlinks and scratch data are excluded.

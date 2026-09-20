# b72-s10: ESPN proportions at player scale

Candidate for beta 73 if integration timing permits, otherwise beta 74. Branch `b72-s10`, base `refs/astra/b72-s9/b72-s9` at `97d2bf9b2`. This changes wing geometry and ramps, team logo crop/bleed, score size/alignment, plate placement and housing thickness. It preserves the native event owner, clock formatter, readable labels and team-owned accent validation. The white pill stays at its measured size after a larger trial overshot the reference.

This is an offline proportion improvement with visible residuals, not a 1:1 certification or a new in-game result. No emulator, disc image build, publish, push or release step was performed. The broad down-capsule and pill mismatch is not materially closed. The exact GPU/display colour and filtering chain remains incompletely calibrated.

Six final player-scale sheets include all four original disc r WAS-LAC captures. Every after is labelled offline. Both native projections go through the 448-line HUD before display upscale; each ESPN reference is normalized to the same 617-pixel apparent bar width. Open at 100 percent for the intended viewing size.

| Matchup | 16:9 | 4:3 |
|---|---|---|
| Washington at Chargers | [sheet](reports/b72_s10/sheets/WAS_LAC_169.png) | [sheet](reports/b72_s10/sheets/WAS_LAC_43.png) |
| Raiders at Texans | [sheet](reports/b72_s10/sheets/LV_HOU_169.png) | [sheet](reports/b72_s10/sheets/LV_HOU_43.png) |
| Broncos at Chiefs | [sheet](reports/b72_s10/sheets/DEN_KC_169.png) | [sheet](reports/b72_s10/sheets/DEN_KC_43.png) |

There is no supplied WAS-LAC broadcast or 4:3 game witness. Those sheets say so. [FIDELITY.md](reports/b72_s10/FIDELITY.md) explains source provenance, rendering, per-team fits, rejected trials and limitations. [GAPS.md](reports/b72_s10/GAPS.md) ranks the measured visible area: logo 2795.50 to 1931.75 pixels, wing colour 1887.50 to 1524.00, housing/rim 975.75 to 926.00, down capsule 669.75 to 669.50, pill 431.50 to 431.00 and score 221.25 to 16.75. These are overlapping per-feature means and must not be added. A residual needs a 2x2 player-pixel core to count.

[VALIDATION.md](reports/b72_s10/VALIDATION.md) records 35 passing default files, 313 cases with 8 existing skips, 104 readable team/aspect labels, 1,350 retained native event frames, both product closures, provider integrity and 31 owner-composition pairs. Broader auxiliary results include two owner-suite timeouts and two cave-oracle errors caused by the inherited stale manifest fingerprint; they are separately listed there. The standalone phase-one packaging suite passes. No blanket full-repository test pass is claimed.

The append remains 325,216 bytes, below the 400,000-byte ceiling. RX remains 4,086/4,096 bytes with 10 spare; RW remains 128 bytes. Native owners and the official palette are unchanged. Denver's brighter navy is a verified unclipped three-times transform of its own palette, with the same 4.5:1 white-label contrast requirement. All other team accent RGB values are unchanged.

[JEV_REVIEW.md](reports/b72_s10/JEV_REVIEW.md) and [JEV_USAGE.json](reports/b72_s10/JEV_USAGE.json) retain both phrasings, every charged call, cautious and unfavourable recognition scores, ranking revisions and reviewed diff flags. Final recognition scores are 1.79 and 1.86 out of 4. Both final next-gap decisions choose logo, matching the measurements. Jev cannot certify appearance or override a measurement.

The exact disc q/r combination is in [TEST_DISC.md](reports/b72_s10/TEST_DISC.md) and its complete recorded option dictionary. Both source build receipts have identical plans. Rebuild from supported retail input using the final integrated owner and bundled assets; do not patch an existing test disc. [WIRING.md](WIRING.md) documents the inherited cave-manifest regeneration required on the final integration stack. No new wiring, dependency, inventory entry, capability row or provider-count change is needed. Existing asset identities and provider/replication pins are refreshed; release-check logic is unchanged apart from its reviewed catalogue hash constant.

Because shared Git metadata is read-only, the local branch lives in `.scratch/b72-s10.git` with this checkout as its work tree. Implementation commits are `af9ed35a1` and `73273e596`. Delivery uses `.scratch/astra-b72-s10.bundle`, branch `b72-s10`, with base `97d2bf9b2` as prerequisite. The final evidence commit includes `ASTRA_LAST_MESSAGE.md`, its 20-line summary and `ASTRA_DONE`. Unrelated hub inputs and retail symlinks are excluded.

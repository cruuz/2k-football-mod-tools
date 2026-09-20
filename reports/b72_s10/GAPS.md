# Ranked visible-area gaps

Mean display pixels at the 617-pixel player bar, two matched broadcasts and both native aspects. Nonzero gaps remain open. This is an offline measurement, not a game result.

| Rank | Feature | s9 before area | s10 after area | Reduction | Status |
|---:|---|---:|---:|---:|---|
| 1 | logo | 2795.50 | 1931.75 | 30.9% | Reduced, residual open |
| 2 | wing_colour | 1887.50 | 1524.00 | 19.3% | Reduced, residual open |
| 3 | housing_rim | 975.75 | 926.00 | 5.1% | Reduced, residual open |
| 4 | down_capsule | 669.75 | 669.50 | 0.0% | No material closure |
| 5 | pill | 431.50 | 431.00 | 0.1% | No material closure |
| 6 | score | 221.25 | 16.75 | 92.4% | Reduced, residual open |

A visible difference must contain a 2x2 player-pixel core. White-ink, colour-coverage and surface masks are defined in `player_scale.py`; each detailed row records its area and the secondary RGB diagnostic. Areas overlap and must not be summed. The Raiders white logo proxy includes some bright wing area.

The first exploratory RGB ranking was wing, housing/rim, plate, logo, pill, score. The feature-occupancy ranking above supersedes it and drove the refinement pass. Jev saw both revisions. No one-pixel stem residual is counted. The plate and pill differences are below one 2x2-pixel core on average and are not claimed as visible improvements.

Rejected: the first broad flat wing wash, centre decay 85 instead of 65, the 288x46 down plate, 43-row pill and 57-row scores. Retained: wider wing boxes with a two-dimensional ramp, team-specific logo crops, 274x42 raised plate, original pill size, 56-row scores with corrected home alignment.

The final down cell is prefiltered to 91x17 texels. The first 96x19 cell failed the SD footprint test and was corrected without weakening the test. All final sheets and measurements use the corrected cell.

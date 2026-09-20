# b72-s11 residual comparison

Fresh s10 renders reproduce every recorded s10 row and ranked residual exactly. S11 uses the same reference frames, same scoreboard values, same two aspects, same 617-pixel bar, same ROIs and same 2-by-2 player-pixel core threshold.

| Feature | S9 residual px | S10 residual px | S11 residual px | S10 reduction vs S9 | S11 reduction vs S9 |
|---|---:|---:|---:|---:|---:|
| logo | 2795.50 | 1931.75 | 1931.75 | 30.9% | 30.9% |
| wing_colour | 1887.50 | 1524.00 | 1502.50 | 19.3% | 20.4% |
| score | 221.25 | 16.75 | 16.75 | 92.4% | 92.4% |
| housing_rim | 975.75 | 926.00 | 899.50 | 5.1% | 7.8% |
| down_capsule | 669.75 | 669.50 | 669.50 | 0.0% | 0.0% |
| pill | 431.50 | 431.00 | 431.00 | 0.1% | 0.1% |

The required logo and score gains are retained exactly. The wing residual improves further. Housing pixels in this proxy also change when logo ink moves across the overlapping rim ROI; the housing artwork itself is unchanged. Every residual remains nonzero. The logo metric measures white-ink occupancy, whereas the separate crop proof counts the complete source alpha of every colour. These are overlapping feature proxies, not perceptual identity scores, and must not be added. No in-game outcome or exact broadcast match is claimed.

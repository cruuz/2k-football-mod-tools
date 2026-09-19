# b72-s7: live vertices verified, hang-time overdraw not fully calibrated

Base: `b6bdf106` (`refs/astra/b72-s6/b72-s6`). Delivery branch: `b72-s7`.

The live label has white diffuse, correct glyph UVs and correct positions. All 47 quads match the matching baseline native fixture byte-for-byte. The later draw previously called the brand is actually the hang-time event plate. It overlaps the entire active label rectangle and obscures the letters in the live-data composite.

The requested numeric reproduction still fails: label-interior mean is 37.64 in the composite and 19.66 in the screenshot, an error of 17.98. Min and max errors also exceed 15. The RAM vertices encode play clock 17 while the screenshot shows 19; GPU state comes from an earlier window whose indices were not logged. The hang-time material is visible in the dump despite an inactive event record, but the dumped native frame update hides it correctly in bounded replay. No erroneous write path or complete cause proof is established.

Following the stopping rule, no speculative runtime change is made. Shipping code, art, compiler tables, s5 team accents and allocator reservations remain unchanged. No new release, test disc, emulator run or in-game result is claimed. No fixed-output >=200 / >=4.5:1 claim is made from the counterfactual render.

Evidence:

- [Full findings and file/VA references](reports/b72_s7/FINDINGS.md)
- [All 47 quad rows](reports/b72_s7/QUADS.md) and [all 188 owned vertices](reports/b72_s7/vertices.json)
- [Every later HUD draw and overlap](reports/b72_s7/overdraw.json)
- [Screenshot/composite comparison](reports/b72_s7/comparison.png) and [numeric gate](reports/b72_s7/model.json)
- [Native fixture and live-RAM replay](reports/b72_s7/native_comparison.json)
- [Validation commands and results](reports/b72_s7/VALIDATION.md)

The existing s6 capture protocol should target the hang-time plate's before/after draw and material-flag writes as detailed in FINDINGS.md. The counterfactual image is an investigative result, not a patch ready for a test disc.

The sandbox rejected writes to the shared worktree Git metadata. Commits and the `b72-s7` branch therefore live in the writable `.scratch/b72-s7.git` store. The incremental `.scratch/astra-b72-s7.bundle` uses `b6bdf106` as its prerequisite and is the integration artifact. No protected shipping file needs wiring.

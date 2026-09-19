# b72-s9: ESPN live-package artwork candidate

This is an offline fidelity candidate on disc q, not a certified 1:1 match. The new source art replaces the generic score digits, dark clock area, broad wing wash and fabricated NFL lettering with broadcast-derived contours, a white pill, restrained ramps and directly harvested NFL/MNF marks. Strict residual failures remain. Nothing in this job is a new in-game witness. Noah's three supplied disc q captures are the only game witnesses used here.

The 17:15 addendum governs scope: preserve readable labels, team palettes and native event records; change fidelity. Records, attached stat panels and new broadcast event timing are not added. The sole native code change fixes a clock formatter defect revealed by the live reference's 14:57 clock. The retail short formatter intentionally returns empty above 599.0 seconds. The complementary long formatter now handles 599.01 through 3600, including the fractional rollover into 10:00. The exact disc q owner fails the new boundary regression, and the candidate passes. See clock_base_regression.json and the sprite test log.

## Ground truth and source provenance

The full 2026 Broncos-Chiefs MNF broadcast governs the design, then Raiders-Texans preseason, then the older Broncos-Chiefs reel. The year-old Bills-Chiefs preview is not authoritative where live evidence differs. All broadcast inputs were read without modification. Full source roots, timestamps, bounding boxes, sample counts and source hashes are in harvest.json. The full-broadcast grammar has 8,657 labelled seconds. Its supplied spot check is 1/30 state errors under the author's non-game grouping; the index also discloses 8/30 under a stricter pregame classification. These are classification estimates, not pixel-match accuracy.

| Element | Bills-Chiefs preview | Full MNF / Raiders-Texans live evidence | Decision |
|---|---|---|---|
| Score digits | Heavy condensed 24/36; compressed still limits contour inference | Many settled score and clock observations, distinct narrow 1 and curved 0 | Trace live glyphs; never infer all numerals from the preview |
| Pill digits and quarter | White pill, dark figures, raised ordinal | Same broad family; actual spacing and cap sizes come from live frames | Separate live clock and quarter masks; whole quarter token at SD |
| Down capsule | Chiefs red, 2nd & 8 | Possession family follows team; Raiders gray, Chiefs red, Broncos blue/navy | Own-palette tint; preserve white-label contrast |
| Pill and separators | White pill with quarter/clock/play-clock divisions | White normal pill, dark digits; red play-clock state exists at five and below | Match normal artwork; red threshold behavior remains unimplemented |
| Records | 10-10 in both wing corners | No confirmed wing records in the supplied live game; records_seen is empty | Do not build records |
| CURRENT DRIVE | Attached banner in one preview still | Supplied live grammar labels drive banners and player/team strips; these do not prove the preview's exact wording, field layout or timing | Do not import the preview banner |
| Colors | Bills blue and Chiefs red in a static preview | Actual frame grades vary; MNF Chiefs red, Broncos blue; Raiders gray and Texans red | Live family first, official per-team transforms and contrast gate retained |
| Wing gradients | Visible inward fade | Subtle inward fade; clean MNF lower strip used for normalized ramp | Lower opacity and faster taper, measured residuals retained |
| Logo treatment | Large edge marks; records consume lower corner space | Large cropped logos with no record reservation | Explicit fits for all 32 modern teams; only four have live fitting evidence |
| Rims, gloss, shadow | Still suggests thin edges and shallow relief | Temporal samples distinguish persistent edges from transient sheen | Reduce broad rim/gloss; no assertion of animated sheen equivalence |
| Corner mark | Preview crop has no usable full corner reference | MNF and NFL have separately observed letterforms | Harvest each mark independently; preserve tested HUD edge pin |

## Traced glyphs and SD constraints

harvest.py segments settled live frames, aligns repeated observations, takes temporal medians, traces the binary contours including holes, and stores 4x outline masks. author.py rasterizes them into the existing bounded sprite atlas, then prefilters each cell to its worst complete field width at the 448-line HUD. No installed, retail or third-party font file is used to author these replacement cells. Report captions use Pillow's default caption renderer; they are not game assets.

There are 57 harvested entries and 5,329 accepted glyph observations from 1,087 contributing frames. Sample counts vary; score 6 has only 14 observations. Score 5, 8 and 9 are not independently observed as settled score numerals in this source selection and are reconstructed from the broadcast clock contours. Rare OT, Inches and word fragments use observed or previously broadcast-traced strokes. They are explicitly RECONSTRUCTED in art_provenance.json, not verified exact glyphs. Native event text such as Ball on DEN 28 still uses the game's existing event renderer, preserving s8 behavior; it has not been replaced by a complete ESPN alphabet.

| Readability exception | Broadcast source cap | Authored source cap | Reason |
|---|---:|---:|---|
| Down label | 23 | 30 | Retain s3's 12 HUD-line floor; 30 maps to 12.44 HUD pixels |
| Quarter numeral | about 19 | 22 | Whole token hinted to nine SD rows; narrow 1 and ordinal must survive together |
| Quarter ordinal | about 13 | 14 | Six SD rows within the quarter token |

The score cap stays 53 source pixels. Proportional advances preserve the narrow 1 instead of forcing every digit into the old 40-column shape. The clock cap is 27 and the label cap is 30. The all-team raster audit and glyph_proof.json check actual native P8 sampling, not only the high-resolution source image. The 4:3 references preserve broadcast bar proportions; no 4:3 ESPN source was supplied.

## Color, surface and logo measurements

The selected wing has peak coverage 0.624736 and exponent 2.755999. The target profile comes from the temporal MNF median at x=450..650 and y=1039..1045, below most of the horse. The search's other numeric targets include engineering constraints and manual estimates, not independent metrology for every parameter. The selected rim parameter is 1.525921 source pixels and gloss parameter 0.084226. author.py contains the explicit vertical sheen stops, housing outlines, pill geometry and separator placement. Surface reconstruction is static; it does not recreate moving broadcast reflections.

The normal pill is neutral 246 with dark 23 ink. The possession plate retains each team's legal palette family. Both accent phrasings were sent to Jev. Low-confidence or competing answers did not auto-edit the palette. art_provenance.json records manual live-reference decisions for DEN, KC, LV, HOU and BUF; other teams retain their earlier validated accents. Historical aliases follow their native modern identity. The second phrasing is a stability audit, not an unlogged second mutation.

Raiders live gray is materially brighter than the contrast-safe official transform allowed by s3. White text on the observed roughly 153 gray would fail the retained 4.5:1 plate test. This candidate keeps the darker official gray and records the color mismatch. Denver's observed broadcast blue also differs from the discrete allowed official transforms. No foreign colors or looser palette validator are introduced to hide those residuals.

Logo fitting now supports bounded zoom and x/y shift before clipping into the same 64x64 native texture. All 32 modern teams have explicit fits. DEN, KC, LV and HOU were fitted against live crops; their remaining white-core residuals are reported. The other 28 are silhouette-based inferences, including BUF, and are not certified per-team live matches. The neutral/custom slots remain supported. Default fit arguments reproduce the previous behavior exactly.

The NFL and MNF masks use 602 and 626 observed frames respectively. The 0.72 alpha is a temporal lower-envelope estimate; alpha is not independently recoverable from the supplied encoded frames. Their provenance checks are not independent fidelity passes. The tested HUD drawable-edge pin places the mark inward of the broadcast's true x position. In widescreen the right drawable boundary is source x=1770, while the broadcast mark reaches about 1867. Extending it requires a separate projection/clip change. The residual table reports that failure rather than pretending the layout box is the rendered position.

## Comparison sheets and limits

sheets/ contains 72 matchup/state/aspect sheets: Raiders-Texans and Bills-Chiefs, 18 available native states, both aspects. Every comparison includes the three supplied disc q witness captures on the left and the proposal at those same witness states on the right. The lower row compares the requested matchup with a live style reference. Bills-Chiefs uses the live package applied to those teams, not an invented live Bills game. A missing broadcast counterpart is labelled explicitly; it is not counted as a matched-state pass.

Four additional detail sheets compare exact matching LV-HOU and DEN-KC score/clock values. ELEMENT_RESIDUALS.md and element_residuals.json retain every result, tolerance, coordinate and limitation. The wider residuals.json links each state sheet to its reference second. Fixed-ROI wing samples can include logo ink, and white-core logo bounds are not a complete silhouette metric. Those numbers must not be interpreted as isolated gradient or full-logo fidelity proofs. The target median profile is a cleaner gradient measurement than the single-frame logo-contaminated residual.

Strict 1:1 acceptance is not met. Remaining issues include absolute palette color, SD cap differences, housing/rim samples, logo bounds, the corner position, reconstructed rare glyphs and uncalibrated final GPU appearance. A passing individual row is only a passing offline metric under its stated limitation. The witnesses have unrecorded display scaling/color processing, so calibration.json remains false; no artificial brightness multiplier was fitted to manufacture a pass.

## Jev population experiment

Three generations contain 128 candidates each. Code measures normalized ramp/shape residuals and retains readability/contrast constraints; Jev judges ESPN hierarchy, team identity and state legibility from text descriptors. Selection retains a Pareto front and mutates it. This is an artwork search, not a 384-layout native execution sweep. Deterministic candidates and all raw requests/answers are retained in population_* files.

| Generation | Best code objective, lower is better | Jev cost USD |
|---|---:|---:|
| 0 | 0.631863 | 0.00391662 |
| 1 | 0.413771 | 0.00390446 |
| 2 | 0.256051 | 0.00390260 |

An equally sized 384-candidate random baseline reaches 0.473811. search_curves.json and search_curves.png show the curves. s3's calibrated single-path search still refuses calibration_verified=False, so a valid end-to-end comparison is unavailable. This is a disclosed acceptance gap; the artwork-only improvement does not establish superiority on live screenshots. Jev never sees pixels. Final screenshot judgments receive measured descriptors and limitations, not a claim that the model viewed the images.

## Integration

Import branch b72-s9 from the supplied local bundle onto 42579f4a5. Use the bundled sprite assets. The runtime RX reservation remains 4096 bytes, RW remains 128, and the generated code uses 4086 bytes. No new module or shipping dependency is introduced. Existing provider and template hashes were refreshed; no closure count or gate logic was relaxed. The cave manifest is byte-identical to the base and intentionally has stale source fingerprints after these owner/compiler edits. The integrator owns its regeneration for the final stack.

No disc, installer, release upload, emulator session or new game witness was produced. The integrator builds one test disc; Noah judges the proposed appearance and authorizes any release. Preserve the disc q option combination and test both the readable down label and recovery after native event plates, along with the clock above and below ten minutes.

# b72-s10: player-scale proportion pass

The s9 game verdict was "still not 1:1 looks about the same". This candidate changes layout geometry and artwork, not only glyph contours. It is not a certified 1:1 match and has no new in-game witness. All six comparison sheets include all four supplied disc r WAS-LAC captures as genuine before views. The after views are offline native renders, labelled as such.

The immutable base is `97d2bf9b2`. Runtime event handling, material records, submission order, label visibility and the clock formatter above 9:59 remain the s9 implementation. There is no native owner code change. The artwork continues to compile through the existing sprite interface and 64x64 team textures.

## Output chain and measurement

The native harness executes the existing owner and captures the submitted scene and P8 textures. The existing fragment model consumes that state at 640x480. Only the 640x448 HUD viewport, rows 16 through 463, is presented. Native widescreen contraction is included before rasterization. The display images are 1138x640 for 16:9 and 853x640 for 4:3, equivalent to the existing 1920x1080/1440x1080 display model at the first disc r capture's 617-pixel bar width. Each raster is enlarged once, using a Lanczos display-filter approximation. No high-resolution render is shrunk to manufacture fine detail.

Each ESPN bar is independently normalized to that same 617-pixel width using the measured housing bounds recorded in `final_measurements.json`. The first exploratory run scaled whole frames; those receipts are retained and superseded by the independently aligned bar measurements. The supplied screenshots are manually cropped captures with slightly different framing. Their original pixels are retained in every sheet. No screenshot brightness or colour correction is fitted.

`GAPS.md` ranks visible feature area. White logo/score ink, colour-well coverage, plate surface, rim and white pill are measured separately. A disagreement counts only when it contains a 2x2 display-pixel core; isolated one-pixel stems and contours do not count. Pixel counts are averaged across the two broadcast matchups and both native aspects. The logo and colour ROIs overlap, so their areas must not be summed. Logo coverage is a white-ink proxy; it also sees part of the bright Raiders wing. It does not establish the exact coloured silhouette.

An initial raw-RGB table over-counted differences between legal palette shades. That table remains as an explicitly secondary diagnostic. Feature occupancy is the final proportion metric. Both revisions and every Jev request remain logged. Measurements are reproducible in `player_scale.py`; no tolerance was changed to turn a failed visual comparison into a pass.

## Changes and rejected trials

Wing boxes grow from 233 to 340 source pixels on each side. The final neutral coverage mask uses a broad top and bottom colour continuation plus a soft horizontal centre ramp. An opaque broad wash and a slower centre decay both increased measured mismatch and were rejected. No generic blue or foreign accent is baked into the art.

Logo wells grow from 200x108 inset boxes to 230x110 boxes touching the bar's ends. Individual fits compensate for the new quad aspect and control crop, zoom and offset within the unchanged texture contract. Tall shields and wide marks use different fits. WAS and LAC intentionally bleed at the edges. DEN, KC, LV and HOU are compared against the supplied broadcasts; the other 28 team fits remain silhouette-based inferences. `logo_fits.json` records every fit, coverage and clipped edge.

The score cap grows from 53 to 56 source pixels, with the traced masks filtered again at the native cap. The home score shifts five source pixels to match its measured placement. A larger 57-pixel trial overshot the reference. This is a modest size and ink-area correction, not arbitrary large digits.

The down plate grows from 268x40 at y=947 to 274x42 at y=945. Its label retains the 30-source-pixel readability floor. The 288x46 trial was rejected because it increased the visible shape mismatch. Event plate boxes move with the normal plate, retaining their own material indices and native visibility records. The clock housing is 252x56 instead of 246x62, with a thinner surround. A taller white pill overshot the reference, so the original 243x40 combined pill size and clock anchors are retained.

Denver's old white-lift navy looked grey. The new `#1E69C9` derives exactly from its own official `#0A2343` by multiplying each RGB channel by three without clipping. The validator recomputes that transform from the trusted palette, never candidate metadata. It still enforces white contrast of at least 4.5:1 for every accent role. Historical aliases sharing the same native identity receive the same values. All other team accent colours remain unchanged. Neutral source cells cannot inject another team's hue.

## Limits that remain visible

The bar still differs from ESPN in logo silhouette, cropped outlines, rim relief and palette shade. Raiders grey remains darker because of the preserved white-label contrast rule. The down label is intentionally larger than the broadcast to survive the HUD. Static ramps cannot reproduce broadcast animation and specular motion. Rare unobserved s9 glyphs remain reconstructed, not exact traces.

There is no supplied WAS-LAC ESPN frame and no 4:3 game witness. The WAS-LAC sheet uses DEN-KC only as a labelled style reference. The reference fragment model does not capture all NV2A state, screenshot colour processing or the emulator's complete display configuration. These limits prevent an exact GPU/display calibration claim.

Jev only receives text measurements. Its recognition scores do not certify appearance, and a higher or lower score cannot override the measured feature table. The final handoff preserves its unfavourable answers as well as its rankings. The next decision belongs to the player-scale sheets and a future played test.

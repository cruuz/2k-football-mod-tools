PROVED OFFLINE: EV implements the approved event routing and plain-type field identities against `c340704642e5a4b4115b2e97766a318e5a41b054`. The private working copy is `/media/noah/Storage/.b76-research/ev/work`; git state and the delivery bundle stay in the same research area. The supplied checkout, other worktrees and disc folder are unchanged.

PROVED OFFLINE: the redirect originated with the Beta 54 season patch on 2026-09-03, commit `9a44516ce6f506231d52d688a0a980a6764b7437`, shipped in `3423cf7f`. Its own module documentation explains the choice: it points season zero to the retail Los Angeles entry because LXI belongs at SoFi. That was a geographic stand-in. u6 subsequently installed the neutral SoFi model into s40 while retaining the executable's venue codes. The fb2 memo exposed the mismatch. [History evidence](evidence/history.json), [fb2 memo](../fb/EVENT_SLOTS.md), and [u6 documentation](../docs/sofi_model/README.md) establish this sequence.

DESIGN: with `modern_sofi` enabled, the builder now asks the season patch for s40 and restores s40 when reusing an older s44 calendar. Without SoFi, a fresh 2026 build keeps the existing s44 default. Off does not undo a route already present in an input image. Indices 1 through 4 keep s42, s43, s41, s44; all indices at least 5 keep s45. No retrospective Levi's LX option is added.

PROVED OFFLINE: [the routing proof](evidence/routing_proof.json) executes the actual executable-only season and SoFi statements extracted from `mod_build.py`, then installs the complete calendar overlay in memory. It uses the pinned retail XBE, not synthetic table bytes. It is E-like season/calendar/SoFi configuration, not a complete E build. The SoFi-off executable before the calendar overlay equals the old implementation's result byte for byte, using the season module loaded from the base commit.

| Evidence | Configuration | VA 0x133354, little-endian | Selected case | Index 0 | Indices 1-4 | Index 5 onward |
| --- | --- | --- | --- | --- | --- | --- |
| PROVED OFFLINE | SoFi on | `c5321300` | `0x1332C5` | s40 | s42, s43, s41, s44 | s45 |
| PROVED OFFLINE | SoFi off, fresh 2026 build | `e1321300` | `0x1332E1` | s44 | s42, s43, s41, s44 | s45 |

PROVED OFFLINE: the proof follows each case's actual UTF-16 stadium pointer. The remaining 16 jump-table bytes and the selector body at `0x1332B0..0x133350` remain retail. The unchanged selector body SHA-256 is `1b17980494fd9dc22ac2117d48a8773ee54542a5bc5bef0ee9ab2a5ad246e762`. No related selector table or instruction changes. Season and calendar status both read `applied` with either supported route, and the season status includes the selected slot. Tests also cover idempotence, migration with an existing calendar overlay, section digest updates, unknown-pointer rejection and the unchanged s40 site's byte validation.

DESIGN: the new field identities use u4's centered type style and the installed Roboto Condensed Bold / Roboto Black fonts, white on transparent. [The policy and font pins](../data/nfl2k5_stadium_shared_art/event_fields.json) and [deterministic authoring tool](../tools/nfl2k5_event_field_art.py) contain no official mark, shield, trophy silhouette or numeral lockup. Every authored PNG has a four-times master. They are `field-logo`, `scene=field`, full-layer P8 items in fb2's existing per-slot venue-art manifests.

| Evidence | Slots | Material | Native format and size | Replacement |
| --- | --- | --- | --- | --- |
| PROVED OFFLINE | s31, s39 | `center_logo` | P8, 256 x 256 | PRO BOWL / ALL-STARS |
| PROVED OFFLINE | s42, s43, s41, s44, s45 | `logo` | P8, 256 x 256 | SUPER BOWL / CHAMPIONSHIP |
| PROVED OFFLINE | s40 | u6's existing field materials | Existing model art retained | SUPER BOWL LXI |

PROVED OFFLINE: s40 already paints LXI. Per the explicit s40 exception, its existing u6 image, model, venue module, art manifest and model pins are unchanged, including the existing LXI mark and shield art. [Retention hashes](evidence/sofi_retained.json) record this. No new s40 fallback image is necessary for E's installed model. With SoFi disabled, EV does not paint a new s40 field.

PROVED OFFLINE: the pinned retail s39 field image actually reads PRO BOWL HAWAII, unlike the earlier memo's Miami transcription. Both Pro Bowl field images are now replaced completely by the same approved yearless wording. [The reviewed comparison sheet](review/event_fields.png) shows all seven retail images against the new native P8 output and a 2x enlargement of the new type.

PROVED OFFLINE: [the field proof](evidence/field_proof.json) serially reads and hashes all 63 source bundles, covering day, afternoon and night in dry, rain and snow. Every exact material selector, native dimension and P8 format is checked. Each event delta is painted by the production venue writer, compressed into the existing span and decoded back. All 63 fit at 256 colors. Every byte outside that one texture's mip/palette allocation is identical: 20,626,368 other decoded field bytes in total, including geometry and descriptors. The scene wrapper and every byte outside the changed compressed field span are identical as well. This measures the incremental EV field delta over fb2, whose special-slot work only changes stadium sponsor scenes; it does not claim compressed bytes inside an edited span stay identical.

PROVED OFFLINE: the production bundle status reader recognizes every resulting bundle through its receipt and rejects both a missing receipt and tampered bytes. The special-slot table now records the event selectors, the receipt includes the event-policy hash, and the registry, release allowlist and PNG catalog include the new art. The original 60 sponsor images stay unchanged. Event slots are selected even when the chosen venue-art folder has no optional league marks. The sponsor authoring tool preserves event items when regenerating sponsor manifests.

PROVED OFFLINE: [sn OCR output](evidence/ocr.json) uses sn's installed Tesseract C API wrapper serially at 2x and 4x, segmentation modes 11 and 6. All 63 outputs map by exact RGBA hash to 13 distinct images, each checked directly. Every image yields the new heading and subtitle. None yields HAWAII, MIAMI, '05, 2005-2009, XL, XLI, XLII or XLIII. The review sheet also received visual inspection. INFERRED: OCR is not a guarantee of perfect text recall; the complete texture replacement and byte proof establish that the old raster is removed.

PROVED OFFLINE: E's 18-week schedule still has no scheduled Pro Bowl game. The in-memory outputs retain `eb22909090` at the Pro Bowl record skip `0x2A82AE` and week `0x16` at `0x133A61`, outside the 22-row grid. No schedule data or Pro Bowl scheduling logic changes.

PROVED OFFLINE: fb2's executable evidence shows that the Create a Team list already includes s31, while `all_stadiums` adds s39 and s40-s45. INFERRED: choosing one of those stadiums for a created team gives a plausible route to its field in Quick Game via the team's stadium pointer. EV does not witness the picker, unlock behavior, preview or game load, and establishes no independent Quick Game event selector or automatic Quick Game year rotation. E's automatic championship route is the franchise/postseason selector proved above.

DESIGN: main must regenerate the observed-build cave manifest after integration. [The handoff](evidence/cave_handoff.json) lists changed source fingerprints and the existing reservation: owner `nfl2k5_season_length`, `[0x133354, 0x133358)`, four bytes, `super_bowl_venue_season0`. The actual route change is one byte, `E1` to `C5`; the touched section SHA-1 is repinned. Fresh SoFi-on builds preserve the retail pointer, while SoFi-off still uses the old redirect. There is no new cave allocation. The manifest is byte-identical to the base and was not regenerated or manually repinned here.

PROVED OFFLINE: all long jobs use one process with no pools, numerical-library thread limits of one and a 1,843,200 KiB virtual-memory ceiling. The field proof peaks at 210,212 KiB RSS and the routing proof at 154,576 KiB. All writes stay under the EV area, below 500 MB; the observed nvme free space stays above 100 GB. No full build, xemu, push or tag is performed.

PROVED OFFLINE: 95 distinct focused tests ran: 94 passed and one private-portrait hydration test skipped because those optional local images are absent. This includes 11 event/shared-art tests, 10 season tests, 15 calendar tests and 59 venue/fan/SoFi tests. The actual s40 field, model pins, PNG catalog and capability registry checks pass. Two initial calendar test failures were isolated-runner setup omissions: the existing report file and test-helper import path. Both pass after fixing the runner environment. Logs: [initial run](evidence/tests_initial.log), [completed checks and registry validation](evidence/tests_followup.log). No source-pin gate is repinned; main's cave regeneration remains the integration step.

PROVED OFFLINE: delivery uses a pathspec commit with the requested `Co-Authored-By: GPT-6 Astra (Codex) <noreply@openai.com>` trailer in `ev/private.git`. The bundle `ev/ev.bundle` requires base `c340704642e5a4b4115b2e97766a318e5a41b054`; it is verified and fetched into a second private git, whose commit and tree match the delivery. The exact commit, bundle SHA-256 and verification receipt are in `/media/noah/Storage/.b76-research/ev/delivery.json`.

PROVED OFFLINE: 15-line delivery summary follows.
1. PROVED OFFLINE: the older s44 redirect was a Los Angeles stand-in for SoFi.
2. PROVED OFFLINE: SoFi-on season zero now reads s40 at VA 0x133354.
3. PROVED OFFLINE: SoFi-off fresh 2026 output remains exactly the old s44 behavior.
4. PROVED OFFLINE: indices 1-4 and the s45 fallback stay retail.
5. PROVED OFFLINE: existing s44 calendars can migrate safely and repeat idempotently.
6. PROVED OFFLINE: season and calendar status readers recognize both supported routes.
7. PROVED OFFLINE: u6's existing s40 LXI art and model pins are retained.
8. PROVED OFFLINE: five Super Bowl slots receive yearless championship type.
9. PROVED OFFLINE: two Pro Bowl slots receive yearless all-stars type.
10. PROVED OFFLINE: all 63 native P8 variants refit and decode correctly.
11. PROVED OFFLINE: every other decoded field byte and outside-span byte is unchanged.
12. PROVED OFFLINE: sn OCR finds the new text and none of the retired event text.
13. PROVED OFFLINE: the 18-week franchise still schedules no Pro Bowl game.
14. INFERRED: Create a Team assignments can expose these fields through Quick Game.
15. DESIGN: main integrates the verified private bundle and regenerates the cave manifest.
ASTRA_DONE

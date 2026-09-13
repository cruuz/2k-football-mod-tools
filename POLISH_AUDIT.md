# Beta 69 polish audit: both studios

Audit recorded before GUI edits on `astra/b69-j7-polish`, 2026-09-13.
The baseline static inventory is [source_strings_before.json](reports/b69_j7/source_strings_before.json):
71 GUI modules, 22,667 non-docstring Python string literals (including identifiers and filters).
The offscreen inventory records every constructed page, nested tab, caption, tooltip,
option and menu action at 1480×920 (default) and 1366×768. Hidden controls are retained.
No disc, emulator, audio or network action is performed. Signal connections and mocked
choosers are checked separately; opening a page does not prove its writer or gameplay.

The supplied 2K5 replay script is absent. A small walker is used instead. This lean
worktree initially lacked the ignored uniform/visual catalogs; 16 allowlisted metadata
reports were restored from `/tmp/astra-b68-a1-release`, with no tracked file overwritten.
The beta-68 public FAQ was read at the hub. `UX_EXECUTION_REPORT.md` is absent at both
root and hub; the existing `ux_text.py`, current page structure and UX regression tests
preserve the simpler-words pass.

| ID | Before / evidence | Intended after | Status |
| --- | --- | --- | --- |
| P01 | GUI workers prepend exception classes in Models, Build, Game Fixes, Animations, Commentary, Presentation, Share, Sounds, Rosters and APF Play Calling. Shared error dialogs display the first backend line verbatim. | Remove class prefixes at the GUI boundary, keep the actual cause, give a next step. J2 retains the skeleton pair explanation. | Fixed |
| P02 | A first-line internal build progress marker can displace the real failure (triage row 1, Coach Edwards). | GUI displays the cause and next step. Writer/service wording belongs to J1; exact coordination notes in WIRING. | GUI fixed; J1 source selection in WIRING |
| P03 | Disc ready says only that bytes differ and lists `xbe, position_pools, ...`. | Describe selected contents in words, preserve measured unchanged/unknown results and kept-original warnings, offer the next play action. | Fixed |
| P04 | APF's build completion always mentions CPU Play Calling even for unrelated builds. | Name the actual authored contents; mention book ownership only when present. | Fixed |
| P05 | Updater passes backend failures straight into its banner; opening a download URL ignores failure. | Say what failed and how to retry or install from the release page; report a browser-open failure. | Fixed |
| P06 | Game Fixes help has obsolete beta references; Field Art inventory cites beta 66. | Retain evidence and feature meaning without release-history captions. | Fixed |
| P07 | Build option captions with `&` are constructed without mnemonic escaping; many options lack hover help despite having adjacent helper text. | Literal ampersands display correctly; visible help is also available on the option itself. | Fixed |
| P08 | Long checkbox/button labels, option badges and tab bars need measurement at default and 1366 px. | Keep full captions reachable, readable labels wrapped, and tooltips on elided navigation/tabs. Exact measured findings follow. | Measured and fixed; see exceptions below |
| P09 | Hand-authored honesty labels and registry findings may diverge; witnessed scope must not become a blanket gameplay claim. | Compare rendered findings to registry runtime scope; exact registry changes go in WIRING. | Compared; registry updates in WIRING |
| P10 | First-run guide names old actions: Load XISO, Build Modded ISO, Launch in xemu. | Use Open game disc, the current preset and build controls, then Play latest disc in xemu. Check actionable navigation in both empty shells. | Fixed and checked offscreen |
| P11 | Getting-started docs retain obsolete release captions, internal WIRING/ASTRA instructions and no complete current sidebar map. | Beta 69 overview and every page in current navigation order, followed by existing tutorials. Remove internal handoff instructions. | Fixed |
| P12 | No dedicated current product FAQ. | Two linked FAQs fold the beta-68 answers and MacDog850, CER, Mud, lt9608 and 7ET answers from beta 69, with current evidence limits. | Fixed |
| P13 | No single fast regression gate covers all pages, their strings and current guide links. | Standalone string-hygiene, offscreen page/tab smoke and doc-link tests. | Added and passing |

Writer ownership: no core/tool writer, build service, model integration, equipment-fit
refusal or registry mutation is included in J7. Changes required there are recorded as
exact replacements in `WIRING.md`. Existing changelogs and historical reports keep their
historical version numbers. Counts and the before/after result are appended after fixes.

## After: measured result

| Measure | Before | After |
| --- | ---: | ---: |
| GUI modules inventoried | 71 | 72 |
| Non-docstring source string literals, including identifiers and filters | 22,667 | 22,756 |
| Constructed sidebar pages, both studios | 34 | 34 |
| Distinct control/string/tooltip combinations | 2,204 | 2,478 |
| Distinct option/action captions lacking hover help | 394 | 0 |
| Raw geometry clipping candidates | 43 | 8 |
| Stale beta captions/help fields identified | 2 | 0 |
| New capabilities | 0 | 0 |

The remaining eight geometry candidates are **not truncated action captions**. Seven
are zero-width descendants of hidden/deferred APF presentation panels. The other is
Field Art's existing two-line `CompactLabel` prose: its paint handler exposes the full
text on hover. The walker records that label's original text before paint and therefore
flags its width. The compact prose treatment is retained from the existing UX pass.
Music's action strips and recording options now fit; Franchise help and image-drop
instructions wrap; Stadium's scene/package columns and flow layouts keep actions readable.
The two 1366-pixel screenshots were inspected offscreen.

The first scan covered workers. A later direct-dialog AST sweep found **66 additional
message boundaries across 23 files** that could display an unformatted cause. Those now
use the same cause, next step and original-disc assurance. The actual backend cause is
preserved; class prefixes, tracebacks and internal progress records are removed from
public output. J1 must still fix the service that can discard the real stderr cause.
Neither a formatter nor a successful interface test establishes a writer fix.

Build option ampersands render literally. Existing specific help is preserved; defaults
supply labels/ranges for controls without it. Preset values and experimental defaults
are unchanged. MyCareer, Play Now, MyNFL, EDGE, Rosters and Build & Share keep current
product spelling. “My NFL 2K5 patch” remains a suggested user project name, not a MyNFL
mode label. Historical comments/docstrings and changelogs keep their dates.

Updater failures are actionable, including a failed browser handoff. 2K5 Copy Build
summary retains selections, result and first failure. Disc ready names selected contents
in words while retaining changed/unchanged/unmeasured outcomes and kept-original warnings.
APF completion describes authored asset categories and only describes CPU book edits when
present, including a book-only manifest with zero ordinary asset edits.

## Navigation, actions and evidence

The fast standalone gate opens **20 2K5 pages and 14 APF pages**, visits **216 tabs** across
the two sizes, and checks **3,908 controls**. It tests the empty first-run chooser/cancel,
the 2K5 Basic-to-Build navigation and the APF build refusal without a source. Signals and
menu actions are inspected; chooser/browser/clipboard outcomes use mocks. No empty-shell
page caused a modal dialog or uncaught slot exception. Opening a source, building real
game bytes and emulator launch are outside this offscreen evidence.

The 161-row registry is unchanged. Registry-backed findings remain authoritative in the
GUI. MyCareer partial reporter scope and the negative shoes10/Style 6 played result need
the exact registry updates in [WIRING.md](WIRING.md); no blanket badge upgrade is made.
APF formation/play authoring and CPU Play Calling retain their stated unwitnessed scope.

## Reproduction and complete inventories

- [Baseline source strings](reports/b69_j7/source_strings_before.json)
- [Final source strings, gzip JSON](reports/b69_j7/source_strings_after.json.gz)
- [Before runtime controls, gzip JSON](reports/b69_j7/before.json.gz)
- [After runtime controls, gzip JSON](reports/b69_j7/after.json.gz)
- [Metrics and count definitions](reports/b69_j7/metrics.json)
- [Direct-dialog sweep by file](reports/b69_j7/dialog_boundary_changes.json)
- [Music at 1366 px](reports/b69_j7/2k5_music_1366.png)
- [APF Stadium at 1366 px](reports/b69_j7/apf_stadium_1366.png)
- [Standalone test results and log paths](reports/b69_j7/test_results.json)

```sh
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/beta69_polish_audit.py /tmp/j7-audit.json.gz
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_beta69_studios_offscreen.py
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_beta69_string_hygiene.py
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_beta69_feedback_qt.py
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_beta69_doc_links.py
```

The final full-catalog walk took **16.854 seconds**. The smaller standalone all-pages gate
took **11.488 seconds**, with a 55-second subprocess timeout. Across **50 standalone test
files**, **49 pass** (548 test cases, including one skipped case). The existing registry-wide
`test_no_capability_is_invisible.py` runs two tests but has two setup errors because
`docs/research/apf_audio.md` is absent in this lean worktree. Its checks were not weakened;
restore the reviewed metadata and rerun during integration. See WIRING for the exact scope.

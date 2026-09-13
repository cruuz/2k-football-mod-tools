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
| P01 | GUI workers prepend exception classes in Models, Build, Game Fixes, Animations, Commentary, Presentation, Share, Sounds, Rosters and APF Play Calling. Shared error dialogs display the first backend line verbatim. | Remove class prefixes at the GUI boundary, keep the actual cause, give a next step. J2 retains the skeleton pair explanation. | To fix |
| P02 | A first-line internal build progress marker can displace the real failure (triage row 1, Coach Edwards). | GUI displays the cause and next step. Writer/service wording belongs to J1; exact coordination notes in WIRING. | To fix / J1 |
| P03 | Disc ready says only that bytes differ and lists `xbe, position_pools, ...`. | Describe selected contents in words, preserve measured unchanged/unknown results and kept-original warnings, offer the next play action. | To fix |
| P04 | APF's build completion always mentions CPU Play Calling even for unrelated builds. | Name the actual authored contents; mention book ownership only when present. | To fix |
| P05 | Updater passes backend failures straight into its banner; opening a download URL ignores failure. | Say what failed and how to retry or install from the release page; report a browser-open failure. | To fix |
| P06 | Game Fixes help has obsolete beta references; Field Art inventory cites beta 66. | Retain evidence and feature meaning without release-history captions. | To fix |
| P07 | Build option captions with `&` are constructed without mnemonic escaping; many options lack hover help despite having adjacent helper text. | Literal ampersands display correctly; visible help is also available on the option itself. | To fix |
| P08 | Long checkbox/button labels, option badges and tab bars need measurement at default and 1366 px. | Keep full captions reachable, readable labels wrapped, and tooltips on elided navigation/tabs. Exact measured findings follow. | Audit running |
| P09 | Hand-authored honesty labels and registry findings may diverge; witnessed scope must not become a blanket gameplay claim. | Compare rendered findings to registry runtime scope; exact registry changes go in WIRING. | Audit running |
| P10 | First-run guide names old actions: Load XISO, Build Modded ISO, Launch in xemu. | Use Open game disc, the current preset and build controls, then Play latest disc in xemu. Check actionable navigation in both empty shells. | To fix |
| P11 | Getting-started docs retain obsolete release captions, internal WIRING/ASTRA instructions and no complete current sidebar map. | Beta 69 overview and every page in current navigation order, followed by existing tutorials. Remove internal handoff instructions. | To fix |
| P12 | No dedicated current product FAQ. | Two linked FAQs fold the beta-68 answers and MacDog850, CER, Mud, lt9608 and 7ET answers from beta 69, with current evidence limits. | To fix |
| P13 | No single fast regression gate covers all pages, their strings and current guide links. | Standalone string-hygiene, offscreen page/tab smoke and doc-link tests. | To fix |

Writer ownership: no core/tool writer, build service, model integration, equipment-fit
refusal or registry mutation is included in J7. Changes required there are recorded as
exact replacements in `WIRING.md`. Existing changelogs and historical reports keep their
historical version numbers. Counts and the before/after result are appended after fixes.

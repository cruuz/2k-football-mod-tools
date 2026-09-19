# b72-s9: beta 73 ESPN fidelity candidate

Base: `42579f4a5` (`local/b73-disc-q`). Bundle branch: `b72-s9`. Implementation commits: `2cb6190cbd` and `16536dca08`. Bundle: `.scratch/astra-b72-s9.bundle`. This candidate changes the scorebug artwork and fixes the native clock above 9:59 while retaining disc q's event ownership. Strict 1:1 fidelity is not achieved: 40 detailed residual checks still fail. No new in-game result is claimed.

- [Fidelity report and preview/live differences](reports/b72_s9/FIDELITY.md)
- [Raiders-Texans comparison, 16:9](reports/b72_s9/sheets/LV_HOU_detail_169.png) and [4:3](reports/b72_s9/sheets/LV_HOU_detail_43.png)
- [Live Broncos-Chiefs comparison, 16:9](reports/b72_s9/sheets/DEN_KC_detail_169.png) and [4:3](reports/b72_s9/sheets/DEN_KC_detail_43.png)
- [Bills-Chiefs with live package styling, 16:9](reports/b72_s9/sheets/BUF_KC_first_and_ten_169.png) and [4:3](reports/b72_s9/sheets/BUF_KC_first_and_ten_43.png)
- [Per-element pass/fail table](reports/b72_s9/ELEMENT_RESIDUALS.md), [glyph traces](reports/b72_s9/glyph_contact.png), [search curves](reports/b72_s9/search_curves.png)
- [Runtime/state/records/stat research](reports/b72_s9/STATE_COVERAGE.md)
- [Final tests and closures](reports/b72_s9/VALIDATION.md), [Jev flag dispositions](reports/b72_s9/JEV_REVIEW.md), [Jev cost](reports/b72_s9/JEV_USAGE.json)

There are 72 state comparison sheets plus four detailed sheets. Every comparison shows Noah's three supplied disc q captures as the before views, with the proposal at the same states. All proposal renders are offline. All 104 team/aspect label checks pass. Both product closures and all 35 default test files pass; the slowest file is 76.72 seconds. The auxiliary owner sweep passes all 31 scorebug pairs, and retained native sequences cover 1,350 frames.

The shipped changes are broadcast-traced proportional digits and label shapes, a hinted ordinal quarter token, white normal clock pill and dark ink, restrained wing fades/rims/gloss, independent NFL/MNF masks, and explicit bounded logo fits for every modern team. Only four teams have live logo-fit evidence; the others are inferred. Rare unobserved glyphs remain identified as reconstructed. The corner mark stays inside the existing HUD's drawable boundary and cannot yet reach ESPN's broadcast position.

The latest fidelity-only addendum takes precedence over new behavior work. No records, CURRENT DRIVE panel, TONIGHT strip, new touchdown collapse, timeout delay, down-only timer or play-clock red threshold is added. STATE_COVERAGE.md lists every supplied full-game state and each rule's available inputs or missing proof. Team records never appear in Play Now or any other mode.

GAMEDATA appendices are 325,216 bytes, 384 above disc q, below the 400,000-byte ceiling. RX is 4,086 of 4,096 bytes, RW remains 128. The cave manifest is unchanged, as requested; its source fingerprints need integrator regeneration after merging the final stack. Existing provider/template pins were refreshed without changing closure counts, requirements, release inventories or gate logic.

The shared Git metadata is read-only in this workspace. Commits and branch b72-s9 are in the private Git directory `.scratch/b72-s9.git`; the importable bundle carries the complete job. The visible shared-worktree branch therefore continues to show the edits relative to its original base. Existing unrelated untracked hub/reference files are not included.

No release steps or emulator session were performed. The integrator builds one test disc with the disc q option combination and this bundled sprite folder. Noah checks appearance, every-team label readability, event recovery and the 10:00 clock boundary, and approves any release. This handoff is a tested candidate with documented fidelity blockers, not a completed 1:1 or witnessed-release claim.

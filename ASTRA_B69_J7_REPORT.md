# J7: beta 69 polish over both studios

Completed GUI/doc work on `astra/b69-j7-polish`, based on
`922c009d65e35f8195762c31106789bb353fb43c`. Small commits use explicit paths.
The original worktree Git metadata is read-only; the commit branch lives in
`/tmp/b69-j7-git` and is delivered in `BETA69_J7.bundle`. The edited files are also present
in this worktree. No remote, shared index or other job's branch was changed.

## Before and after

[POLISH_AUDIT.md](POLISH_AUDIT.md) was committed before implementation and retains the
13-item before/after list. It links the complete static strings and constructed control
inventories, recorded at 1480×920 and 1366×768.

| Before | After |
| --- | --- |
| Worker class prefixes, traceback text and progress records could appear as errors. | Shared GUI formatter retains the cause and gives a next step; 66 additional direct-dialog boundaries use it. J1's service-level cause selection remains a required handoff. |
| Disc ready listed receipt step keys; no retained copyable first-error summary. | Named build selections, measured result, retained-art warnings, original-disc assurance and next play action; Copy Build summary retains the first error. |
| APF completion mentioned CPU calling for unrelated builds. | Authored categories described in words; CPU book edits detected from the manifest, including book-only builds. |
| Updater exposed raw failures and ignored a browser-open failure. | Cause and recovery wording, including manual release-page recovery. |
| 394 distinct option/action captions lacked hover help. | Zero in the constructed page/tab inventory; existing specific help is retained. |
| 43 raw geometry clipping candidates. | Eight explained audit artifacts/intentional compact prose; zero clipped action captions. Music, Franchise and Stadium layouts corrected. |
| Two current GUI fields named stale betas; guides named old controls. | No prohibited release captions in GUI literals; both beta 69 guides match current sidebar and first-run controls. |
| No current per-studio FAQ. | Two linked FAQs fold the public beta-68 answers and beta-69 reports. |
| No single fast all-pages/string/doc gate. | Four standalone polish test files plus a reproducible full-catalog walker. |

Counts: **71 → 72 GUI modules**, **22,667 → 22,756 source string literals**,
**2,204 → 2,478 distinct control/string/tooltip combinations**, **34 sidebar pages**.
Source counts include identifiers and filters; runtime counts distinguish text/help variants
and are not a claim of 2,478 separate visible buttons. Registry rows remain **161**, with
**zero new capabilities** and no count-pin change.

Product spelling remains MyCareer, Play Now, MyNFL, EDGE, Rosters and Build & Share.
Preset defaults and the earlier simpler-words treatment are preserved. Specific help
wins over fallback labels/ranges; no experimental option was enabled by this pass.

## Community answers and public docs

Getting Started uses the actual first-run actions and lists every current page in order.
2K5 opens a disc, selects SOFTDRINK Basic, opens Build & Share, makes a disc and offers
Play latest disc in xemu. APF loads the game, stages supported edits, builds a game folder
and offers Launch in Xenia; it has no global BASIC preset.

The new FAQs answer MacDog850's “i also had to have chat gpt fix it”: reinstall from the
official Setup.exe, rebuild, post the Build summary and first error; an assistant-modified
installation is unsupported. They cover CER's Interceptions slider and BASIC repair,
Mud's menu-time radio roadmap request, lt9608's emulator settings, and 7ET's existing
Create formation/Create play tools with CPU-book, off-by-default and UNWITNESSED limits.
Play Calling is explained as which plays get called. Public pages contain no private
“What Noah must witness” checklist.

Both beta 69 changelog sections have house-voice bullets and reporter quotations.
maumau78's “shoe slot 10 / style 6 is not show in-game” is explicitly recorded as a negative
Bears played report despite the visible Edit Player preview. No J7 equipment repair is
claimed. MyCareer reporter evidence is kept bounded to the reported sequences.

## Validation and practical limits

**49 of 50 standalone test files pass**: the passing files contain **548 cases**, including
**one skipped case**. The remaining existing registry-wide file has two setup errors due
to absent `docs/research/apf_audio.md`; its two runnable tests pass. The complete file list,
timings and logs are in [test_results.json](reports/b69_j7/test_results.json).
No failing assertion is being suppressed. The missing evidence gate needs an integration rerun.

The new all-pages test opens **34 pages**, visits **216 tabs** at two sizes and checks
**3,908 controls** in **11.488 seconds**; its child timeout is 55 seconds. The final walker
using hydrated release metadata takes **16.854 seconds**, with no modal dialogs or uncaught
slot exceptions. String hygiene rejects stale beta/RC captions, protocol/class text and
raw exception-object dialog bodies. Feedback tests cover failed builds, copied summaries,
unchanged and retained-art outcomes, APF book-only receipts and a failed browser handoff.
The local doc-link gate checks the two guides and two FAQs. Existing GUI subject files and
the two adjusted legacy test files were run independently as required.

Two 1366-pixel screenshots were inspected. The eight residual geometry candidates are
seven zero-width descendants of hidden/deferred APF panels and one intentional compact
Field Art prose label with full-text hover handling in its existing paint implementation.
No action caption remains clipped in the measured empty-shell states.

PROVED here means the named offline interface, text, receipt and mocked-action checks.
The source chooser/cancel and Basic navigation are exercised without a game. Connected
signals are checked, but this does not prove every disc-dependent action or external
application can complete. No game disc was built or modified. No emulator, audio, live
display or network was used. Every new gameplay outcome remains UNWITNESSED.

The 2K5 replay script is absent; the committed small walker is the fallback. The root and
hub have no `UX_EXECUTION_REPORT.md`, so existing UX code and regression tests guided the
preservation pass. Sixteen missing allowlisted, ignored metadata reports were hydrated
without overwriting tracked files; [hydration.json](reports/b69_j7/hydration.json) lists them.
No retail bytes are included in the changes, reports or bundle.

## Required integration

[WIRING.md](WIRING.md) contains exact paths, insertion points and replacement text for:

- Both protected package allowlists: new shared GUI helper and product FAQ entries; APF
  also needs the shared `ux_text.py` dependency. These entries are required before shipping.
- J1's build-service first-error selection, plus protected writer completion wording.
- Registry runtime scope for the partial MyCareer reporter result and negative Style 6
  witness; APF authoring remains unwitnessed. No row/count addition.
- Restoring the missing registry evidence metadata and rerunning its existing standalone gate.

No core/tool writer, mod_build, build service, registry, J2 model-edit integration or
skeleton-pair explanation, or J1 equipment-fit refusal was edited. Generic Models worker
and failure-dialog formatting are the only Models changes. No writer repin or cave-manifest
regeneration is required. The bundle and audit assets are development deliverables and
must not enter either product package.

The final artifact is `BETA69_J7.bundle`; its companion checksum identifies its exact bytes.
Use `git bundle list-heads BETA69_J7.bundle` to inspect the delivered branch, then fetch it
into the integration repository and cherry-pick the theme commits. The bundle requires the
base commit named above. The initial untracked handoff files and `extracted` symlink remain
outside the commits.

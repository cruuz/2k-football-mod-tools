# Beta 72 a1: situation personnel sets and visible weights

The implementation adds per-book, per-live-bucket personnel comparison rows
through the v2 situation patch. The candidate view shows curve term, member
ratings mean, their f32 product, category rank, retail weight and effective
row. The existing formation weight stays visible for the next draw. Local
rows are the only new authoring lever. The option is EXPERIMENTAL and off in
every preset. In-game effect remains **UNWITNESSED** until Urianus or Noah
observes the scenario below.

Source facts were read from `ASTRA_CONTEXT.md`, the hub's
`ASTRA_CONTEXT_B72_2026-09-18.md`, the `apf-playbook-structure` memory, and
`BETA72_APF_DOSSIER.md`, APF72-A. Book policies follow resolved SPLB names,
not roster labels. No other job's implementation was changed.

The supplied diagnosis needed one correction: the pinned fixture's Queens
category 6 has row 7, so request row 10 gives a 0.5 curve term. The 0.05
floor begins at a gap of four. Native execution establishes this difference.
The override to row 10 gives Queens a 1.0 term. With Pro: Strong's three
ratings set to 7 and the other member ratings unchanged, the observed
category product rises from 0.6833333373069763 to 1.3666666746139526, rank 1.
The category mean includes structural members before exclusions, as retail
does. The surviving formation's own weight is 0.10000000149011612.

The reports "Still unable to add personnel sets to situations" and
"Can't edit base weight or per-situation weight" are addressed by the local
row control and explicit calculation. Existing formations must already be
members of the book. The override does not invent a formation or bypass
native play-validity checks.

## Offline proof

- The v2 writer and strict reader round-trip both BASE and TU 1.1 exports.
  Legacy v1 data/code/TOML remain canonical. A v2 sparse appendix shares the
  original 13,824-byte data region and refuses overflow before staging.
- A new pre-curve hook supplies only the local row register, then resumes
  retail arithmetic. It does not rescale an already-rounded weight or
  consume RNG. The two draw hooks retain masks and empty-draw fallback.
- 48 native combinations cover all 12 buckets, both run/pass arms and both
  executable profiles. Native category weights match the model exactly; factor products, ranks
  and category-weight sums are checked against those weights.
- Eight v2 bypass cases compare output, book, MASTER and team bytes, GPRs,
  CR and RNG consumption against untouched retail execution. Absent policy,
  another book, another bucket and unknown version retain retail behavior.
- The other 14 fixture books keep exact category-weight bytes. Row edits
  leave all SPLB and MASTER bytes unchanged. The full build regression also
  preserves every input archive hash and reparses both patch receipts.
- Queens / Pro: Strong at ratings (7,7,7), with every other ordinary formation
  excluded at O-ManBlock 3rd-and-8, is selected in 12 bounded BASE/TU draws
  and every one of 256 model seeds. No empty-draw fallback is taken. The
  portable authored fixture independently checks the minimum-rating guard.
- Full-width synthetic instruction execution checks GPR, CR, FPR, FPSCR,
  stack and guarded-write behavior of the new row leaf, including bypasses.
  Emitted code occupies 3,156 of 3,328 reserved executable bytes.
- Staging, project reload, undo, reset to Retail row, Confirm workflows and
  build receipts preserve the policy. Offscreen tests check the displayed
  factors and missing/matching/stale installed-patch status beside the switch.

The code preserves the existing positive minimum-rating behavior; no new
rating-based exclusion or minimum-weight special case was introduced.

## Delivery and integration

Code commits are `a07c6569` and `1a6eb013`, followed by the evidence handoff
commit on bundle branch `b72-a1`. The bundle is
`.scratch/astra-b72-a1.bundle`, based on `088e3f41`. Fetch its `b72-a1` branch.
The shared Git metadata was read-only, so commits use isolated metadata in
`.scratch/b72-a1.git` with existing objects read-only. The launcher worktree's
original shared branch and all other worktrees remain unchanged.

`WIRING.md` provides the exact metadata update for the existing protected
`apf2k8.playbooks.cpu_playcalling` capability. New registry rows: zero.
No protected registry or packaging source was edited, and no version marker
was bumped. Repin reports zero updates. `tools/apf_h7a_optimal` remains 0755.
No retail inputs or decoded game binaries are included in the delivery.

The first native development invocation had a harness-installation error:
its instruction adapter read the original in-memory image after installing
the patch into CPU memory. Updating both representations fixed that test
harness. A focused run used accelerated AES only to shorten development;
the final acceptance suite ran standalone with the repository decoder.
The first Qt run found missing accessibility descriptions on two controls;
the complete Qt suite passed after they were added. The installer also required a private test environment with the already
installed Capstone 5.0.7 copied into its site-packages, because that test
intentionally disables user-site imports. No dependency download or gate
relaxation was used. Final per-file receipts supersede earlier progress entries.

## Required in-game witness

Use the resolved **O-ManBlock** book, ordinary CPU offense, tied score,
first quarter 15:00, midfield, **3rd-and-8**, three timeouts. Enable the
experimental situation option. In the third-down over-7-yards bucket, set
**Queens (category 6) to local comparison row 10**. Leave only **Pro: Strong
(formation 14)** unexcluded among ordinary formations and set its three
ratings to **7**. Confirm, build, install the matching BASE or TU 1.1 v2
patch, verify the inline matching status, then fully restart Xenia.

Expected ordinary personnel/formation: **Queens / Pro: Strong**. Verify the
called set and lineup in game, then test another bucket and another book
for isolation. Remove the override/exclusions and install that revised
patch to return to retail choices. A project toggle or undo alone cannot
change an already installed/running patch.

No emulator was launched, no live match was observed, and no in-game result
is claimed. The preview remains a cold neutral-history model; installed
global curve patches and live learned history can change actual weights.

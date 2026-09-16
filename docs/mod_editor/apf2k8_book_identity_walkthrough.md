# CPU Play Calling: books, situations and formations

Start in **Playbooks → CPU Play Calling**. The integrated Book Identity tab
points here. Every in-game outcome remains **UNWITNESSED**.

1. Choose **Offense** or **Defense**, then **Book to edit and preview**. USER books
   are selectable directly. Global books supply special calls and may have no
   ordinary candidates. The selected team is used for team tendency edits and
   independent copies; it does not select the book being previewed.
2. To give a team its own copy, choose the team and starting book, click
   **Give this team its own book**. The assignments are checked automatically. The new
   named book becomes the edit target. **Give every team its own book** covers the
   24 disc teams on the selected side, or 48 independent books across offense and
   defense. The retail 36 offensive / 33 defensive labels share resources; they
   are not 36 independent teams. The 16 saved-team slots retain their USER-o /
   USER-d assignments. Use **Save Assignments** for supported roster saves.
3. Choose a **Situation**. Its candidate table lists formations, personnel and
   the number of tight-end roles. Select a candidate and use **Fine-tune formation
   weights** beside the table. Its three raw ratings control short, medium and
   long yardage; the game interpolates them for each situation. **Preview formation
   weights** compares personnel and formation weights across all situations,
   including Pending edits, without staging. These weights are calculated together,
   not independently stored percentages for each situation. **Confirm formation
   ratings** runs the existing checks and stages the edit. With **Add edits to
   Pending edits** enabled, it queues the captured book, formation and ratings;
   **Confirm all** checks the batch and stages it in one Undo step. To add a
   formation, choose its donor book and formation, then **Confirm formation addition**.
4. **Confirm removal from this book** removes that formation completely. Review
   the surviving personnel first. Membership and removal are shared across all
   situations in the book; these are not independent per-situation lists.
   A low weight does not exclude a formation. Raw rating 7 remains selectable,
   and a lone candidate still wins its draw.
5. Set **Preview run share (%)** and refresh the call preview. This percentage
   is independent of the team picker and does not stage a team tendency edit.
   The spreadsheet exports the selected book with this preview value. Its
   23 buckets include shared-input and special-phase proxies, labeled in the
   export and situation view.
6. Save the project, then **Build** a separate game copy. Edits are not applied
   to the source. Load that built copy for the gameplay retest. A saved roster's
   USER book can override disc content; verify which book the game actually uses.

## Individual plays and team settings

**Fine-tune Plays** edits individual play membership and audible slots. Compatible
Fine-tune changes replay existing CPU edit receipts in the same Undo transaction.
If a change removes a formation still targeted by a CPU edit, the editor names
that conflict and retains the previous project. Undo the conflicting CPU edit
before removing its target. To fine-tune a newly cloned resource in the legacy
record editor, build it and open that copy as a new source first; the main CPU
editor can edit its staged formations by name before building.

**Confirm team run/pass tendency** edits the selected team's stored value. It is
separate from the preview percentage. MASTER personnel controls remain explicit
experimental edits shared by all books. No preset stages any new control.

## What the evidence establishes

Bounded BASE and TU 1.1 tests prove the shared membership fields, selected
category/formation/play tuples, minimum-rating behavior and complete removal
from the tested book. A category's eleven role bytes supply its TE count.
The later native depth selector and eleven-player builder now have bounded
BASE/TU tests with supplied player pools. An empty TE depth list can supply a
fullback for a requested TE role, so the table shows **Requested TEs**. Actual
saved rosters, the saved-book lifecycle and in-game lineups remain UNWITNESSED.
See [the extended situation and lineup research](../research/apf_b71_apf3.md).

For a local exclusion, **Live situations** offers the separate opt-in mask in
twelve down/distance buckets. It needs the matching BASE/TU patch installed;
an emptied draw falls back to its original candidates. The 23 representative
preview queries remain distinct from these twelve live buckets. See the
[situation-mask guide](../research/apf_b71_apf4.md).

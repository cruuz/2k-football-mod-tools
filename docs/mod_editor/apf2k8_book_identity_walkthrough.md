# CPU Play Calling: books, situations and formations

Start in **Playbooks → CPU Play Calling**. The integrated Book Identity tab
points here. Every in-game outcome remains **UNWITNESSED**.

1. Choose **Offense** or **Defense**, then **Book to edit and preview**. USER books
   are selectable directly. Global books supply special calls and may have no
   ordinary candidates. The selected team is used for team tendency edits and
   independent copies; it does not select the book being previewed.
2. To give a team its own copy, choose the team and starting book, click
   **Give this team its own book**, review the assignments, and confirm. The new
   named book becomes the edit target. This stages an explicit project edit.
3. Choose a **Situation**. Its candidate table lists formations, personnel and
   the number of tight-end roles. Select a candidate to edit its ratings or
   personnel below. To add a formation, choose its donor book and formation,
   then **Review formation addition** and confirm.
4. **Review removal from this book** removes that formation completely. Review
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

**Stage team run/pass tendency** edits the selected team's stored value. It is
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

Independent per-situation formation whitelists still need a new runtime selector
and exclusion gate. The ordinary editor does not write a guessed mask or present
the unrelated lineup ladder as that control.

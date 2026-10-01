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
   defense. This action's scope is not an archive capacity limit: the retail pool
   has 36 offensive / 33 defensive labels, initially sharing resources. The
   automatic action preserves the 16 saved-team slots and their USER-o / USER-d
   assignments. **Manual book allocation…** restores the broader Book Identity
   utility: build your current project, choose that built folder, select any of
   its 40 roster slots and an unused label, review, then build a new folder.
   This can exceed 24 allocations and can change saved-team slots. Loaded roster
   saves can override disc assignments; use **Save Assignments** for those saves.
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

PROVED OFFLINE: **Live situations** offers separate formation multipliers,
exclusions and personnel comparison rows for twelve actual down/distance
buckets plus ordinary two-point offense in the native try phase. All 23 named
coaching samples appear as explicit mappings to those controls. A sample such
as **Red zone 25-21** edits the displayed down/distance bucket everywhere that
bucket occurs. **4-minute** is a clock/score sample, not an independent stored
native formation list. Other live downs and distances use their own buckets.

Choose a formation multiplier of **0.25x, 0.5x, 1x, 2x or 4x**. This changes
only the selected book and live bucket; **1x** removes the override. Higher
multipliers increase relative weight. The candidate view shows native weight
x multiplier = resulting formation weight, separately from the personnel
curve x mean rating. These are not call percentages. The shared yardage
sliders still affect every situation that interpolates them.

DESIGN: enable the EXPERIMENTAL project option explicitly, confirm edits, then
use **Review and install situation patch** for the BASE or TU 1.1 profile you
launch. Export and Build produce patches and receipts but do not install them.
Weight or try edits require v3. Restart Xenia after installation. Pending edits,
Undo and saved projects include these controls; they do not silently replace an
installed patch. Check the dependency message after changes. To revert one
weight, stage **1x** and reinstall. To restore all native policy, remove the
installed situation patch and restart Xenia.

PROVED OFFLINE: an emptied exclusion draw retains its original candidates and
weights. The two-point controls apply after the CPU chooses ordinary offense
in phase 3; the displayed candidates are a scrimmage proxy and do not predict
the kick-versus-two-point decision. Native kicks and cached Hail Mary/Clock
calls use separate paths. Gameplay remains UNWITNESSED. See the
[complete inventory and witness procedure](../research/apf_b76_a3.md).

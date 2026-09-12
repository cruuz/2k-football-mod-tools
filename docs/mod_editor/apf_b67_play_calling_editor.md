# CPU Play Calling

Open **Playbooks → CPU Play Calling**. Choose a team, then offense or defense.
The page shows the book it uses now and every other team sharing that book.
For example: “O-ManBlock, shared with Beasts, Rollers, Top Guns and Wasps.”
Changing that book changes the calls available to all those teams.

**Give this team its own book** prepares a separate copy for the selected team.
Choose its starting book first. Stock, USER and global books are donors on the
selected side. USER books bring their contents; they use the same call selector.
Global books supply special teams and may have no ordinary calls to preview.

**Give every team its own book** prepares an independent copy of each team's
current book on this side. It keeps their different starting contents. Review
the team, label, donor and clone name in the table, then choose **Confirm and
stage reviewed edit**. The build inserts the clones together. You can edit a
staged clone immediately; its shared donor keeps its own contents.

## Live call preview

Each row shows the personnel row the game requests, the leading personnel,
formations and plays with percentages, and an explanation from the model.
“Flush carries no tight end” describes that personnel's roles; adding a play
alone does not give its lineup a tight end.

The offense grid includes 1st and 10 midfield, 2nd and short, 2nd and long,
3rd and 2/5/8/15, goal line, red zone, two-minute trailing, two-minute leading,
4th and 1, and a custom situation. The defense grid shows responses to the
offense's personnel rows 0 through 10. Yards to goal also affects defense.

The custom controls say what the game uses:

| Control | What the game does with it |
|---|---|
| Down | Chooses a situation row and adjusts the run share. |
| Yards to first down | Weighs short, medium and long situations. |
| Yards to goal | Changes the personnel request near either goal line. |
| Quarter | Uses it with clock and score to assess urgency. |
| Seconds left in quarter | Changes run/pass choice as time runs out. |
| Team's points ahead | Treats a trailing team differently from a leading team late in the game; use a negative value when behind. |
| Timeouts left | Decides whether there is time to run. |

Custom values change the preview, not the book. **Refresh call preview** reads
the current staged choices. Staging a book, MASTER or tendency edit refreshes
automatically in a worker. Identical book contents, MASTER contents, tendency
and situations reuse a cached prediction. The table shows the top three
candidates at each stage, so displayed percentages need not total 100%.

These are offline predictions, not guaranteed calls. The game also considers
match state, recent calls and suitability. Gameplay remains **UNWITNESSED**.

## Change how this book calls plays

Choose a formation to see its three current ratings, personnel and plays.
Each button and field has a one-sentence explanation in its tooltip and
accessible description, with the main rules printed beside the controls.

| Control | What the game does with it |
|---|---|
| Short, medium and long ratings, 0–7 | A **lower** raw number makes the game weigh this formation more: the first field for short yardage, the second for medium, the third for long. 0 is the strongest setting and 4 through 7 all share the weakest. |
| Stage formation ratings | Uses those three ratings for this formation in the built book. |
| Play X rating, 0–7 | Weighs lower X ratings more heavily; **0 = called most**. |
| Stage play rating | Uses that X rating for this play in this formation. |
| Primary personnel | Advertises the formation under this main personnel category. |
| Checked secondary personnel | Also makes the formation reachable under those personnel categories. |
| Review personnel change | Shows the lineup resolver's remaining row coverage before staging the new categories. |
| Remove formation | Removes this formation's records and plays from this book after coverage review. |
| Retire personnel | Strikes the category from surviving primary and secondary memberships when the writer can preserve a valid book. |
| Team run share | Starts from this team's run percentage, then adjusts it for the situation; it affects this team even when its book is shared. |
| Stage team run/pass tendency | Saves that starting run share for this team in the built roster. |
| Stage balanced CPU audibles | Uses existing run and pass plays for the formation's audible slots; formations lacking either kind cannot be balanced. |

The raw formation numbers are **not** a conventional “higher is better” scale.
For equal ratings the game weighs 0/0/0 as category 3 and formation 0.5, 1/1/1 as
2 and 2, 2/2/2 as 1 and 1, 3/3/3 as 0.5 and 0.5, and 4/4/4 through 7/7/7 as 0.1 and
0.1, before distance and cubing. The situation interpolates between the three
ratings and urgency changes that calculation. A zero raw rating does not disable a
formation; remove it to exclude it from this book. A category averages its
applicable formations' weights before the category lottery, so edit all relevant
records of one personnel when trying to change that category's weight. The
brief's heavy 7/7/7 goal-line recipe therefore favours the *other* formations: use
raw 0/0/0 on the heavy set and 7/7/7 on the sets you want called less.
These are P3's measured values from `docs/mod_editor/apf_b67_play_calling.md`.

For removals and personnel changes, **Review before staging** names retired
categories and lists every requested row with its remaining candidates.
When the research classifies the lineup resolver's callers as non-CPU, an
uncovered row is a warning that you can confirm. If a CPU caller reaches it,
or classification is still unknown, the page refuses the unsafe change and
keeps the coverage visible so you can retain a nearby category. Beta 67's
static audit found exactly two direct callers, both inside a routine that
supplies both team managers, and no direct caller of that routine, so the
classification stays unknown and the page still refuses. A writer that
refuses before producing replacement bytes shows coverage explicitly labeled
as the current book, before the refused edit.

Use **Fine-tune Plays** for individual audible slots. Book edits already staged
there and Scheme Presets are included before the CPU Play Calling recipe.
If another editor changes something the recipe relied on, the recipe must be
reviewed again. The builder refuses a changed before-value instead of silently
overwriting a different result.

## MASTER personnel: EXPERIMENTAL

The separate group starts disabled and says **changes every book on the
disc**. Open it only when you intend that scope. Its table lists all 28
categories, their rows, and the eleven lineup roles.

Select a category. **Stage personnel row** changes the row the game compares
with its personnel request. Each **Player** role chooses the role the game
fills in that lineup slot. **Stage eleven personnel roles** saves those roles
for this category across every book.

“5-2 sits one row below the ordinary request, so the game never weighs it;
move it to row 13 to make it an ordinary candidate.” **Make 5-2 an ordinary
candidate (row 13)** stages that row change. This explanation concerns ordinary
matchups; near-goal requests can differ.

## Staging, Undo and Build

The receipt table lists each staged control, its book or team, before and
after values, and retired categories. **Undo last session change** restores
the previous session state. Save Project stores the authored recipe with the
rest of the session; opening the project replays it before predicting calls.
No decoded game resources are included in that recipe.

Build writes a separate game copy. Its `book-content-receipt.json` records
before/after ratings, play ratings, personnel memberships, removed formations,
retired categories, team tendencies, MASTER rows/roles, clones and verification.
After archive insertion, resource lookups use names and receipt indices are
resolved again. The completed-build message names the teams now owning books.

## Experimental patches

Both personnel curve presets start off. Choose **Retail BASE** or **Title
Update 1.1**, matching the game you run, then either:

- **Offense: stick closer to the situation's personnel** reduces the weight of more distant personnel in offensive calls. Retail weighs the five offensive distance steps 1, 1, 0.85, 0.5 and 0.05; the preset uses 1, 0.35, 0.10, 0.02 and 0.
- **Defense: stick closer to the situation's personnel** reduces the weight of more distant personnel in defensive responses. Retail weighs the three defensive steps 1, 0.01 and 0; the preset uses 1, 0.002 and 0.

Both preset tuples are authored experiment values, not measured in the game. The
core accepts exactly five offensive and three defensive weights, each starting at
one and never increasing with distance.

**Review and install personnel curve patch…** prepares the patch before asking
for consent. The dialog names the destination in Xenia's patches folder and
the launch config where it will set `apply_patches = true`. That setting also
activates other patches marked enabled. Installing a curve preset replaces
the previous personnel curve preset; the pass-fetch experiment has its own
file. **Check personnel curve patch status** reads installation and config
state. **Remove personnel curve patch** removes only that Studio file. Restart
Xenia after changing patches.

The retained P2 actions are **Install TE bias for last-resort fetch…**,
**Install an exported pass-fetch patch…**, **Remove Studio pass-fetch patch**,
**Choose Xenia config…**, and **Check patch status**. Choose the game folder
and, when needed, **Choose Title Update 1.1…**; **Detect installed update**
returns to automatic detection. **Choose flat image (expert)** accepts a
private decoded executable instead. These inputs let the studio match the
patch to the game Xenia will run.

The pass-fetch patch affects last-resort fetches at every down, including
user calls. **This is not a CPU play-calling fix.** The ordinary successful
weighted picker uses another path. Its installation uses the same explicit
P2 consent flow. Neither experiment has an in-game witness.

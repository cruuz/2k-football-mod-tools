# Authoring CPU play calling in beta 67

Each team chooses a book by name. Teams assigned the same book share its
formations, plays and ratings. Give a team its own copy before changing only
that team's calls. USER-o and USER-d are content donors; they use the same
selector as the stock books. The global books supply special calls and are
not blank ordinary playbooks. A saved USER bank can override a disc template.

The ordinary CPU call is three weighted choices: personnel category, formation,
then play. The game computes a requested personnel row from the situation.
Nearby categories tend to receive more weight, but a distant offensive
category can still win. Category and play weights are cubed, so a modest
weight difference can produce a large difference in call frequency. Adding a
formation makes it available after its cached indexes are rebuilt; it does
not guarantee its selection. The preview warns when an inserted membership
is absent from the stored play cache. Category edits and removal rebuild
these indexes; older membership-only insertion can leave them stale.

## What each edit changes

| Edit | What it controls | Scope |
| --- | --- | --- |
| Own book | Copies contents and assigns a distinct resource name | One team and side |
| Three formation ratings | Formation weight and its category's mean weight at short, medium and long distances | The edited book |
| X play rating | Initial play weight; independent of audible tags | One formation's membership in the edited book |
| Primary and secondary categories | Personnel packages in which the formation can participate; primary matches get preference during formation selection | The edited book |
| Remove formation | Deletes every duplicate record for that formation and compacts the remaining records | The edited ordinary book |
| Retire category | Removes its primary and secondary references; requires another primary for surviving formations | The edited book |
| Category row | The situation row to which a personnel category belongs | **Every book on the disc** |
| Category roles | The eleven requested positions, preserving each slot's stored depth bits | **Every book on the disc** |
| Team run percentage | Team tendency before situation adjustment and the run/pass draw | The team's ROST tendency record |
| Optional team row arrays | An optional tendency category/formation cache | Not the ordinary CPU category lottery |
| Experimental distance curves | Makes the CPU stick closer to the situation's personnel | **Every team using that executable** |

The raw formation numbers are **not** a conventional “higher is better” scale.
For a neutral situation, category weights for equal ratings are:

| Raw triple | Category rating weight | Formation rating weight |
| --- | ---: | ---: |
| 0/0/0 | 3 | 0.5 |
| 1/1/1 | 2 | 2 |
| 2/2/2 | 1 | 1 |
| 3/3/3 | 0.5 | 0.5 |
| 4/4/4 through 7/7/7 | 0.1 | 0.1 |

The situation interpolates between the three ratings. Urgency changes that
calculation. A zero raw rating does not disable a formation. Remove it to
exclude it from the edited ordinary book. A category averages its applicable
formations' weights before the category lottery, so edit all relevant Ace
records when trying to reduce Ace's category weight.

X runs in the same direction: 0 is the strongest initial play preference,
then 1, 2, 3 and 4. Values 4 through 7 share the low endpoint. X does not
change the four Y audible assignments. The run/pass tendency, play suitability,
history and player skills can alter the final result.

## Goal-line witness for Urianus and Noah

1. Start from an owned retail folder and a fresh project. Assign one team its
   own offensive book, using O-Singleback3WR as the donor. Add Jacks or Jokers
   with ordinary plays from O-Shotgun if absent.
2. Run the requested **negative control**: give the heavy formation raw
   **7/7/7** and every Ace formation raw **0/0/0**. Build, assign the CPU team,
   and use first-and-goal at the one. Record the actual loaded book and calls.
   Those raw values favor Ace. A guaranteed heavy call is not the expected
   outcome; the native heavy category weight is 0.1 versus 3 with raw 0/0/0,
   before distance and cubing.
3. Reverse the raw values: heavy **0/0/0**, every Ace **7/7/7**. Build a new
   folder and reload the match without a saved USER-book override. Repeat
   first-and-goal at the one over several fresh calls. A heavy goal-line call
   is the intended positive witness. Selection remains a lottery.
4. Record the book name, team, build identity, BASE or TU 1.1, situation,
   formation and visible TE count. Remove the test formation, rebuild and
   reload; confirm that it stays absent. Check both sides if authoring defense.

If the Studio displays a conventional strength scale where 7 means strongest,
it must explicitly convert that value to the raw field. The core API writes
the raw 0..7 value and does not silently reverse it.

## A tight end on third down

Straight carries a tight end in retail MASTER. Give its formations a strong
preference by using low raw category ratings, and reduce competing Flush,
Queens and 5 Wide records. Preview third-and-3, third-and-8 and third-and-15,
then build and witness the selected category and its visible lineup.

Optionally enable the experimental offensive distance curve to make the CPU
stick closer to the situation's personnel. Alternatively, edit one of Flush's
WR role bytes to TE in MASTER. That role edit affects **all books**, not just
the team's copy. Preserve the slot's depth bits and review all eleven roles.
The native builder requests and writes the edited role with supplied eligible
players, but roster depth selection, equipment,
animation, route behavior and the rendered lineup still require a game witness.

For defense, 5-2's retail row is 12. An ordinary request for row 13 gives it
zero weight. Moving its MASTER category to row 13 gives it ordinary category
weight 1, alongside other matching packages. This edit is shared across books.

## Preview and removal limits

The preview uses empty learned history, neutral player skill and a cold
scrimmage context. It does not reconstruct clock-management urgency, previous
plays, saved USER banks or global merges. Defensive paired-play estimates
assume a lineup feature of four; that value is a **HYPOTHESIS**, not a proved
retail default. Defensive play rows count both components of a call, so their
probabilities can total more than one. Preview seeds are repeatable samples,
not the game's RNG seed. Kicker-range branches assume 50 yards, which is
not a proved retail default. Read the notes with the distribution.

Ordinary formation removal is stable under two native normalizer passes.
Special-play removal is refused pending special-tail and cache repair. A
different merged book or saved bank can independently supply a removed
formation. Rebuild and reload to test the actual loaded book.

Row coverage describes the separate lineup resolver's bounded search. Empty
coverage is not evidence that the ordinary CPU lottery has no candidates.
The static audit found two direct resolver calls, both in a routine supplying
both team managers. Its entry lifecycle remains unclassified. This work does
**not** prove that only human teams can reach it, so it does not authorize a
blanket downgrade of the older retirement refusal.

Experimental curves ship off. Export the curve patch for the correct pinned
BASE or TU 1.1 profile, then use the explicit install action for the selected
Xenia patches folder and configuration. The curve patch has its own filename
and can coexist with the older pass-fetch patch. Building alone does not
install either patch. All on-field behavior remains **UNWITNESSED**.

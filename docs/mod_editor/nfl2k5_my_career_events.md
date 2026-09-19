# MyCareer host-side pre-draft events

This implements the offline half of the proposal. No playable event, native menu,
draft decision, preseason cut or XBE allocation is added. Existing Build defaults
remain off. The studio prepares an existing NFL Draft stage save; it does not
synthesize a draft class.

`nfl2k5_my_career_events` contains validated scoring tables. Senior Bowl passing
and rushing each earn up to three points, with six total. The dash earns up to
five; Pass Skeleton yardage and completion percentage each earn three, with
eleven total for pre-draft events. Undrafted projects cannot record either event.

Dash times are positive finite seconds, rounded to hundredths using decimal
half-up rounding. This resolves gaps between the printed intervals. Exactly two
attempts are required; rounded ties select the first. Faster-than-chart times
receive a speed ceiling of 95, slower-than-chart times receive 75, and times above
4.82 earn no dash points. Completion percentages are continuous: 64.999 remains
one point and 65 becomes two. Negative yardage earns zero. The module docstring
specifies the complete rules, including the inverse speed interval.

Each point buys one attribute increment. This is separate from played-game XP
and uses the existing progression caps. Buckets preserve the proposal's attribute
permissions. SEC is `hold_onto_ball`. SCR is excluded from purchases because the
existing progression system treats its byte as a style channel containing throw
parity. Dash purchases are additionally limited by the recorded speed ceiling.
A rating already above a ceiling is kept and cannot be raised by that purchase.

```python
from mod_editor.core import nfl2k5_my_career_events as events

# record is MyPlayer's existing roster.PlayerRecord.
ledger = events.new_ledger(record, prospect_tier=1)
events.earn(ledger, event="senior_bowl", pass_yards=300, rush_yards=50)
events.earn(ledger, event="pre_draft", attempts=["4.69", "4.65"],
            pass_yards=150, completion_percent="67.5")
events.apply_earned(record, ledger, {"senior_pass": {"pass_accuracy": 2}},
                    transaction_id="accuracy-purchase-1")
events.save_project("MyCareer-events.json", record, ledger)
record, ledger = events.load_project("MyCareer-events.json")
```

The journal stores the baseline and ordered results/purchases; it does not trust
serialized earned or spent totals. Both event slots and purchase IDs are unique.
Replay checks permissions, available credit, caps and the resulting record.
Purchases commit ratings and debits together, or change neither. Sidecar saves
use an exclusive lock, atomic replacement and an existing-journal prefix check;
a stale copy cannot overwrite a newer spend. These guarantees cover supported
local operations, not manually falsified statistics or deliberate file rollback.

`prepare_save` creates `MyCareer-events.json` beside the signed save and setup.
Studio creation also stores the journal as `my_career_events` metadata when a
project is open. Named and recovery `.2k5mod` saves preserve it and validate it
by replay on load. The facade's `project_my_career_events` and
`set_project_my_career_events` provide detached state for future host event UI.
There is no playable event or event-results UI in this change, and this journal
does not update in-game career XP.

The identity controls accept jersey number, inches, pounds and a college already
in the chosen save. Keeping a value preserves the prospect's existing field.
All body writes happen before tier calibration, and the serialized player is
read back to check the requested 74/70/64/59 overall. The native API still accepts
all 17 position codes for compatibility; Studio offers the eleven design rows,
or ten with LB and no OLB on a one-pool roster.

QB's fourth studio prototype is an authored Gunslinger rating vector: Pocket's
other fields, arm strength 95, accuracy 78 and reads 72. It is distinct before
and after tier calibration. The native 51-row table remains unchanged. Other
positions keep their three existing templates.

Draft Advisory reads each active club roster against the executable's existing
position targets and maxima. Its report orders target shortfalls first, then
maximum headroom, then club index. Each review reopens the signed prepared save;
a changed prospect class or roster mode is rejected. Incumbent changes refresh
the counts rather than reusing old estimates. One-pool estimates refuse saves
that still contain retired OLB players.

Cut risk assumes MyPlayer joins each displayed club. Equal native overall favors
the incumbent. Risk is High if estimated position rank exceeds the maximum, or
if it exceeds target while the projected roster exceeds 53. Either condition
alone gives Moderate; otherwise Low. The page displays the underlying counts
and ranks. These labels are capacity estimates, not probabilities or predictions
of the native cut routine. They never change the draft or end a career.

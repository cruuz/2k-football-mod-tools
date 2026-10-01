# DESIGN: main-only kickoff witness, three returns

DESIGN: use a fresh roster with the integrated dc code and merged roster file. Build the next candidate from C's complete recipe. Existing roster/franchise saves keep their own old assignments; start fresh for this check. Keep the inherited depth_locks and returner_fix options enabled. Astra has not launched xemu.

1. DESIGN: start Play Now with Arizona receiving against Detroit. Use a normal Kick Return formation and a normal, returnable kickoff. Return the ball, then capture the LAST PLAY card. Expected text: `Kickoff returned by Devin Duvernay` or `Kickoff returned by Max Melton`, depending on which returner fields the kick. C previously selected long snapper Casey Kreiter at KR1.
2. DESIGN: repeat with Detroit receiving against Arizona. Expected LAST PLAY returner: Tom Kennedy or Jacob Saylors. C previously selected defensive tackle Skyler Gill-Howard at KR1 and long snapper Hogan Hatten at KR2.
3. DESIGN: create a fresh franchise with Minnesota, leave CPU depth management on, advance one week and save/reload. Arrange one returnable Minnesota kickoff. Expected LAST PLAY returner: Myles Price or Demond Claiborne. C previously selected long snapper Andrew DePaola at KR1.

DESIGN: capture the complete LAST PLAY sentence and screenshot for each return. A touchback, fair catch, onside kick, injury substitution or absent sentence is not evidence of a normal kickoff return. Record any manual lineup changes or eligibility issues; do not count a different named player as a pass. A single returned kick proves only the player who caught that kick, not both depth entries.

DESIGN: save the three card transcriptions in `ari.txt`, `det.txt`, `min.txt`, then check them with:

```sh
python3 dc/lab/check_cards.py --ari ari.txt --det det.txt --min min.txt --out kickoff_result.json
```

DESIGN: this checker validates transcribed text only. Main must inspect the matching screenshots and record the disc/roster hashes. The full-build proof disc is deliberately deleted after offline verification, so main must build its next candidate before this lab.

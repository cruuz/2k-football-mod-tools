# b72-s8: beta 73 scorebug test-disc handoff

Use branch `b72-s8` from `.scratch/astra-b72-s8.bundle`, based on `c5134e232` (`refs/astra/b72-s7/b72-s7`). This carries s5 team colours, s6/s7 diagnostics and the inactive event-plate fix. The decision is FIX NOW, then Noah confirms on this test disc. In-game verification is pending.

Build from the retail USA source with this branch's application and bundled sprite folder. Use disc p's requested option combination:

| Setting | Exact value |
|---|---|
| Preset | Experimental, internal name `softdrink_experimental` |
| Scorebug | `scorebug=True` |
| Scorebug runtime | `scorebug_runtime=True` |
| Sprite layout | Bundled `data/nfl2k5_scorebug_sprite`, `scorebug_folder=""` |
| ESPN watermark | `scorebug_watermark="auto"` |
| Modern colour and lighting | `modern_color=True`, default `modern_color_settings={}` (overall strength 0.5) |
| Modern Arrowhead | `modern_arrowhead=True` |
| Widescreen | `widescreen=True` |
| Dynamic kickoff and other preset settings | Retain the Experimental preset values |

The equivalent plan construction is below. `test_disc_options.json` records the complete preset plus explicit override map. These are integrator build instructions, not a disc produced by this job.

```python
from dataclasses import replace
from mod_editor.core.mod_build import BuildPlan, apply_preset

plan = apply_preset(BuildPlan(source=retail_iso, target=new_test_iso),
                    "softdrink_experimental")
plan = replace(plan, scorebug=True, scorebug_runtime=True, scorebug_folder="",
               scorebug_watermark="auto", modern_color=True,
               modern_color_settings={}, modern_arrowhead=True, widescreen=True)
```

For the integrator: regenerate the protected cave reservation manifest from the final integrated owner set. The base already has stale source fingerprints, and the generated scorebug owner changes here. The reservation sizes, hook ownership and appended resource size remain unchanged. Both product closures and the scoped owner checks are recorded in `VALIDATION.md`. No provider or allowlist wiring remains.

Noah should check these three things:

1. **Label readability:** check `1st & 10` with a dark team and a light team, for example Raiders and Lions, with each team in possession.
2. **Punt recovery:** let the hang-time event show during a punt, then confirm the down label returns for the receiving team's next snap and remains readable over subsequent plays.
3. **Presentation:** confirm accents change with the selected teams and the ESPN NFL watermark appears in Play Now. Auto switches to ESPN MNF only for a franchise Monday-night game.

Record the matchup, build identity and which check passed or failed. The final gate is Noah's in-game test. The offline composite is evidence of the repaired visibility behavior, with no new in-game result claimed.

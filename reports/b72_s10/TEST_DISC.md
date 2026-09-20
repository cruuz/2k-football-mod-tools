# b72-s10 test-disc handoff

Import branch `b72-s10` from `.scratch/astra-b72-s10.bundle`, based on `refs/astra/b72-s9/b72-s9` at `97d2bf9b2`. Use the final integrated application and its bundled sprite folder. Schedule this candidate for beta 73 if integration timing permits, otherwise beta 74. No version or release marker is changed here.

The supplied disc q and disc r build receipts have identical `plan` dictionaries. `test_disc_options.json` contains that complete dictionary, both source receipt hashes, and the comparison result. This is the disc q event-owner fix plus disc r's s9 long-clock/white-pill/traced-glyph base, with s10 artwork and geometry replacing the bundled sprite assets.

| Setting | Exact value |
|---|---|
| Preset baseline | `softdrink_experimental` |
| Scorebug | `scorebug=True` |
| Runtime sprite | `scorebug_runtime=True` |
| Bundled layout | `scorebug_folder=""` |
| Watermark | `scorebug_watermark="auto"` |
| Modern colour | `modern_color=True` |
| Colour settings | `modern_color_settings={}`, overall strength defaults to 0.5 |
| Modern Arrowhead | `modern_arrowhead=True` |
| Widescreen | `widescreen=True` |
| Other settings | Exact disc q/r values in `test_disc_options.json`, including `dynamic_kickoff=True` |

To reconstruct every recorded option without depending on future preset drift:

```python
import json
from pathlib import Path
from mod_editor.core.mod_build import BuildPlan

options = json.loads(Path("reports/b72_s10/test_disc_options.json").read_text())["options"]
plan = BuildPlan(source=retail_iso, target=new_test_iso, **options)
```

Build from the supported retail USA disc. Do not stack resources onto disc q or disc r. The sprite resources and XBE owner must come from the same integrated checkout. For a separate 4:3 test, change only `widescreen=False`; the checked 4:3 sheets use that projection. These are integrator build instructions. This job produces no disc image and launches no emulator.

The source reservation manifest inherited from s9 needs integrator regeneration against the final owner stack. This job adds no RX or RW allocation and changes no native owner bytes. Existing provider and replication pins are refreshed. No allowlist entry, dependency, capability row or preset default is added.

Compare WAS at LAC at `1st & 10` and `2nd & 10` against the four supplied disc r before views. Also check LV at HOU and DEN at KC, both possessions and a light/dark team pair. Watch logo crop and bleed, colour coverage, score size, plate shape and label readability at the actual display size. Confirm the down label returns after a punt, hang-time, FLAG and FUMBLE, and confirm 9:59, 10:00 and a clock above ten minutes. Record the build identity, aspect, matchup and result. Every s10 in-game outcome remains unwitnessed.

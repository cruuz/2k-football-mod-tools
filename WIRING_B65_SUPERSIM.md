# WIRING: Beta 65 job B (MyCareer Supersim stage 1)

## Beta 65 job B — live MyCareer Supersim (Astra, 2026-09-10)

This section supersedes earlier Supersim capacity/unavailable statements only
for **Stage 1: native off-field presentation-skip requests at 1x**. Accelerated
sim-to-next-appearance remains unavailable. This is part of the existing
in-game MyCareer writer, not a new `nfl2k5_supersim.apply()` or allocation.
See `ASTRA_REPORT.md` for bounded proof limits and Noah's exact witness list.

### Native option and protected Build/GUI integration

The native Apartment row is already implemented in
`mod_editor/core/nfl2k5_my_career_mode.py::code_for`, `hub_rows[7]`, and
`tools/mycareer_mode/runtime.c::mode_supersim_toggle`. It says
`Supersim: Skip presentation` / `Supersim: Off`, with Skip presentation the
session default inside an enabled career, as the brief explicitly requests.
Native construction refreshes the cached label and retains selection; the
seven-row viewport scrolls to the eighth row. No editor-side toggle or extra
pause action is required for Stage 1. Do not expose a Fast forward option,
headless-speed claim, ticker or Sim to next appearance action.

Keep the existing `my_career` Build option/preset classification EXPERIMENTAL,
off in every preset. The internal Stage 1 default does not turn MyCareer on.
The generic path calls `nfl2k5_my_career_mode.apply()` as before. There is no
`mod_build.py` insertion or new allocator request to wire. Legacy prepared-save
MyCareer is not changed by this job's live mode hooks.

### Protected capability registry: amend the existing inline-mode row

File: `mod_editor/capabilities/registry.v1.json`.
Insertion point: existing capability `id == "nfl2k5.mode.my_career_inline"`.
Apply the following complete amendment (retain its backend, classification,
selectors, opt-in defaults and runtime `status: not-tested`). No new capability
row should claim accelerated Supersim. This is the exact field transformation:

```python
from pathlib import Path
import json
p = Path("mod_editor/capabilities/registry.v1.json")
doc = json.loads(p.read_bytes())
row = next(r for r in doc["capabilities"] if r["id"] == "nfl2k5.mode.my_career_inline")
for evidence in (
    "ASTRA_REPORT.md",
    "tests/mod_editor/test_nfl2k5_supersim_live.py",
    "tools/mycareer_mode/supersim_live_receipt.json",
    "tools/mycareer_mode/supersim_budget.json",
    "tools/mycareer_mode/supersim_validation.json",
):
    if evidence not in row["evidence"]:
        row["evidence"].append(evidence)
row["input_constraints"] = [s.replace(
    "Requests, trades and Supersim stay out.",
    "Requests, trades and accelerated Supersim stay out.")
    for s in row["input_constraints"]]
constraint = (
    "Supersim Stage 1 requests native off-field presentation skips at 1x. "
    "The Apartment choice is Skip presentation or Off; B cancels eligible "
    "off-field skip requests for the session. Cold load resets the choice. "
    "Complete unattended drives and full-play-clock return are unproved."
)
if constraint not in row["input_constraints"]:
    row["input_constraints"].append(constraint)
row["summary"] = (
    "Native draft or undrafted entry, Senior Bowl preparation, played-XP upgrades, "
    "next-fixture calendar and optional native off-field presentation skips at 1x "
    "in the Apartment loop. Accelerated sim to next appearance is unavailable. "
    "EXPERIMENTAL / UNWITNESSED."
)
for evidence in ("ASTRA_REPORT.md", "tests/mod_editor/test_nfl2k5_supersim_live.py"):
    if evidence not in row["runtime"]["evidence"]:
        row["runtime"]["evidence"].append(evidence)
addition = (
    " Bounded native skip readiness/cleanup, replay input consumers, presence "
    "guards and Apartment row dispatch are also proved. No headless scheduler, "
    "audio gating, uninterrupted drive or pre-snap return is proved."
)
if addition not in row["runtime"]["scope"]:
    row["runtime"]["scope"] += addition
witness = "Complete the Stage 1 QB, CB, kick, halftime, two-minute and save/load witnesses in ASTRA_REPORT.md."
if witness not in row["portme"]:
    row["portme"].append(witness)
p.write_bytes((json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
```

### RC89 / beta 65 changelog bullet

File: `docs/mod_editor/2k5_mod_studio_changelog.md`, insert under
`## v1.0 RC89, beta 65` (create that section above RC88 if integration has not
already created it). This is the complete bullet, not a claim of Stage 2:

```markdown
- **MyCareer Supersim, first stage (existing `my_career` option, experimental and opt-in).** While MyPlayer is off the field, the live game can request the retail post-play, replay, injury/timeout and period-presentation skips. Both sides keep their native AI and gameplay stays at normal speed. Scroll below Upgrades in the Apartment for **Supersim: Skip presentation / Off**; Skip presentation is the session default, and B during an eligible off-field presentation turns it off. The choice resets on a cold career load. Native skip readiness and cleanup, replay-button consumers and the scrolling option are proved in bounded execution. Fast forward, headless CPU drives and a guaranteed pre-snap return with a full play clock are not proved or shipped. The existing 16 KiB code and 8 KiB writable reservations still fit, with 1,051 code bytes spare; no other owner moves. Built by Astra; unwitnessed.
```

### Protected release cave manifest and packaging

`packaging/repin.py --apply` was run; the two changed existing provider pins are
committed in `mod_editor/core/providers.py`. The protected release manifest is
stale after this writer change and **must be regenerated by Claude** after all
beta 65 jobs are integrated. Three new hook reservations must appear:

| Hook | Native site | Native target |
| --- | --- | --- |
| `mode_skip_tick` | `0x64D27`, 5 bytes | `0x89F40` (ret) |
| `mode_skip_buttons` | `0x13856`, 5 bytes | `0x70A10` |
| `mode_skip_buttons` | `0x112DD9`, 5 bytes | `0x70A10` |

No reservation sizes or peer addresses change. `status()` verifies the complete
owner/template and guards; `apply()` replay is byte-identical. The guard-only
skip ranges do not authorize a cave allocation.

Development gates use `.scratch/supersim-final-manifest.json`, created by:

```bash
python3 tools/mycareer_mode/refresh_gate_manifest.py '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' --output .scratch/supersim-final-manifest.json --base-revision c9d01941
```

It verifies every unchanged source pin and the changed sources at the pinned
parent revision, observes the actual writer, and conservatively retains all
parent reservations. It is explicitly **not a regenerated release/disc
manifest**; old disc fields remain historical. Do not publish it in place of
`data/nfl2k5_cave_reservations.json`. After integration and a final repin, use:

```bash
python3 packaging/repin.py --apply
python3 tools/nfl2k5_cave_oracle.py manifest '<retail default.xbe>' --xiso '<retail xiso>' --work-dir '<existing scratch directory with space for a disposable 6+ GB disc>' --json data/nfl2k5_cave_reservations.json
```

Keep developer probes, retail-gated tests and research receipts out of runtime
payload requirements. Existing core-module packaging already covers the two
changed MyCareer modules and the Supersim contract. If the release allowlist
uses exact paths for development-source bundles, add these source/derived-only
paths there; no retail resource or `.scratch` output is distributable:

```text
tests/mod_editor/test_nfl2k5_supersim_live.py
tools/nfl2k5_supersim_live_probe.py
tools/mycareer_mode/supersim_live_receipt.json
tools/mycareer_mode/supersim_budget.json
tools/mycareer_mode/supersim_capacity.json
tools/mycareer_mode/supersim_validation.json
```

Run both XBE gates, cave oracle and pairwise matrix again on the integrated
release manifest. Final branch-local results and command receipts are in
`ASTRA_REPORT.md`; a passing bounded gate is not an in-game witness.

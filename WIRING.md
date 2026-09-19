# b72-m1 integration wiring

The brief authorizes the MyCareer form and its Studio connection. Those edits are already implemented in `mod_editor/gui/my_career_panel_qt.py` and `mod_editor/gui/studio_qt.py`. Project persistence is wired through the facade, session and project archive. No additional GUI insertion is needed.

Protected release-list and registry updates below are left for integration, as required by `ASTRA_CONTEXT.md`. There are zero new capability rows, so registry-count pins do not change. `packaging/repin.py --apply` updated existing source digests only.

## Package the two new host modules

In `packaging/release-allowlist.txt`, beside `mod_editor/core/nfl2k5_my_career_prospects.py`, insert:

```text
mod_editor/core/nfl2k5_my_career_events.py
mod_editor/core/nfl2k5_my_career_advisory.py
```

In `mod_editor/core/providers.py`, in the source-digest map that already includes `nfl2k5_my_career_prospects.py`, add these final source pins:

```python
        "mod_editor/core/nfl2k5_my_career_events.py": "228a0b59d43b9b9c52e10ac93cc72072e772e694cc864c8e2e037c5d7c772460",
        "mod_editor/core/nfl2k5_my_career_advisory.py": "14aa17b6d3dc4aba6303de17eaa999c7599856110ee89ae14ccd522f0eaf00ba",
```

In the import-smoke module list in `packaging/check_2k5_mod_studio_runtime.py`, beside `mod_editor.core.nfl2k5_my_career_prospects`, add:

```python
        "mod_editor.core.nfl2k5_my_career_events",
        "mod_editor.core.nfl2k5_my_career_advisory",
```

## Update the existing MyCareer capability

In `mod_editor/capabilities/registry.v1.json`, locate `id == "nfl2k5.mode.my_career"`. Append these evidence entries:

```json
[
  "tests/mod_editor/test_nfl2k5_my_career_events.py",
  "tests/mod_editor/test_nfl2k5_my_career_host.py",
  "docs/mod_editor/nfl2k5_my_career_events.md",
  "reports/b72_m1/host_only.json"
]
```

Replace `summary` with:

```json
"MyCareer retains native Franchise drafting and player control. Studio adds body and college creation, eleven design positions or ten with one-pool LB, four distinct QB prototypes and three elsewhere, replay-checked host earned-rating projects, and read-only Draft Advisory and 53-man cut-risk estimates. Playable pre-draft events and career-ending cuts are not implemented."
```

Append to `input_constraints`:

```json
[
  "Body edits precede prospect-tier calibration; save read-back must equal 74/70/64/59. The fourth QB rating row is host-authored and does not change the native 51-row table.",
  "Event results are supplied host-side. Replayed event buckets, unique transaction IDs, progression caps and dash ceilings constrain purchases; no played-stat authentication is claimed.",
  "Draft Advisory and cut risk require the prepared save and matching class fingerprint and roster mode. Estimates use native target and maximum tables; neither changes the draft or cuts MyPlayer."
]
```

Replace the `input_constraints` entry beginning `All 17 retail positions` with:

```json
"Studio offers eleven design positions with retail pools, or ten with LB and no OLB under one-pool mode. The preparation API retains all seventeen retail position codes. The native table retains three templates per position; Studio adds a distinct fourth QB prototype. Position-specific input decode and switch guards are bounded-native proofs; movement, routes, catches and block animations require a played witness."
```

Replace `source_container.resource` with:

```json
"Game Modes First Person Football row rewritten to the MyCareer action, pinned hooks; allocator-owned 20480 RX and 4096 RW bytes; fixed signed Franchise save and bounded checkpoint journal. Host preparation, earned-rating projects and advisory estimates add no XBE bytes."
```

Keep runtime status `not-tested` and preset defaults off.

## Manifest and gates

The protected `data/nfl2k5_cave_reservations.json` is untouched. Regenerate it during integration after all jobs land. For this job, `python3 reports/b72_m1/verify_host_only.py` verifies byte-identical MyCareer and MyCareer-mode XBE outputs against `088e3f41`, verifies the unchanged b69 budget, then creates `.scratch/b72-m1-gate-manifest.json`. It retains every parent span/allocation and updates only the changed source pin whose byte identity was proved. Run the four gates with `NFL2K5_CAVE_MANIFEST` pointing to that temporary file. No new reservation or allocator change is needed.

Run `python3 packaging/repin.py --apply` after these integration edits.

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
        "mod_editor/core/nfl2k5_my_career_events.py": "48d9377853040fbc3335088257eab9405fb1b2ad894bb959ee7eb983e8ac785e",
        "mod_editor/core/nfl2k5_my_career_advisory.py": "d9d20c00cc24db73ebbefb172004bb16d8f7194e52c7681961d60955fc0cab86",
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

Replace the old picker description in `input_constraints` with the studio eleven/ten-row rule above, retaining the native seventeen-code API compatibility note. Set `source_container.resource` to describe the existing 20,480-byte RX and 4,096-byte RW allocation, not the stale 8,192-byte size. Keep runtime status `not-tested` and preset defaults off.

## Manifest and gates

The protected `data/nfl2k5_cave_reservations.json` is untouched. Regenerate it during integration after all jobs land. For this job, `python3 reports/b72_m1/verify_host_only.py` verifies byte-identical MyCareer and MyCareer-mode XBE outputs against `088e3f41`, verifies the unchanged b69 budget, then creates `.scratch/b72-m1-gate-manifest.json`. It retains every parent span/allocation and updates only the changed source pin whose byte identity was proved. Run the four gates with `NFL2K5_CAVE_MANIFEST` pointing to that temporary file. No new reservation or allocator change is needed.

Run `python3 packaging/repin.py --apply` after these integration edits.

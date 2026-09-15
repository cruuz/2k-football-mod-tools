# C5 integration metadata

The outside writer and Colour & lighting page changes are implemented directly under the C5 brief. No functional GUI/build wiring remains. No capability rows or runtime reservations are added.

`ASTRA_CONTEXT.md` protects `mod_editor/capabilities/registry*`; C5 does not grant that file. The existing registry validates strictly, but its four C4 prose fields still claim the old bundle pins. Replace the following fields on row `nfl2k5.presentation.modern_color_lighting` using the exact values in `reports/b71_c5/registry-metadata.json`:

```python
replacement = json.loads(Path("reports/b71_c5/registry-metadata.json").read_text())
row["input_constraints"][3:5] = replacement["input_constraints"][3:5]
row["runtime"]["scope"] = replacement["runtime"]["scope"]
row["selectors"]["notes"] = replacement["selectors"]["notes"]
```

`reports/b71_c5/registry_metadata.py` prepares and validates this same row in `.scratch/b71_c5_registry.json` without editing the protected registry. Run strict validation and repin after integration.

The release cave manifest retains inherited stale source fingerprints. Regenerate it during normal integration as required by C4; C5 changes no rig bytes, executable code, caves or reservations. The complete applied XBE is checked against C4. Both XBE gates were therefore not rerun for this outside-resource-only change.

The inherited unrelated wiring handoff is archived at `reports/b71_c5/INHERITED_WIRING.md`.

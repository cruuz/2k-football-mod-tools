# b72-s11 integration

No GUI, build-service, registry, preset, dependency, provider-count or release-inventory changes are needed. Existing allowlists already contain both edited logo-fit metadata files and the replication pin table. The template PNG, palette values, native owners, PNG catalogue and release checkers remain byte-identical to base c3b3b53a2.

The inherited cave manifest still requires regeneration by the integrator on the final stack. Its existing failure names `mod_editor/core/nfl2k5_scorebug_exact.py`; this job does not modify that source or the protected manifest. Run the repository manifest builder against supported retail inputs and disposable integration storage, using the command retained in `reports/b72_s10/VALIDATION.md` and the prior integration handoff.

```bash
python3 tools/nfl2k5_cave_oracle.py manifest \
  "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  --xiso "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso" \
  --work-dir "$INTEGRATION_SCRATCH" \
  --json data/nfl2k5_cave_reservations.json
```

No protected-file edit is requested beyond that inherited manifest regeneration. No release action or emulator launch belongs to this job. Reuse the existing option dictionary in `reports/b72_s10/TEST_DISC.md` for a later integrated build; this job creates no disc.

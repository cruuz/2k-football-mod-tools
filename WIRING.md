# Beta 71 A7 integration wiring

All protected files are granted for this job. S4 has no newly authored deferred wiring: `git diff 464423f0 7b54e354 -- WIRING.md` is empty. Its inherited beta-70 T1 instructions are archived anonymously in `WIRING_B71_S4.md`.

- The inherited completion-dialog hooks are already active at `mod_editor/gui/studio_qt.py:8023` and `mod_editor/core/build_feedback.py:53`.
- The inherited Windows-helper and digit-fit proposals are historical follow-ups, not S4 changes. This merge does not add an unreviewed executable or a digit writer.
- S4's runtime registry metadata is merged by capability ID; all 176 unique rows remain.
- The release allowlist retains the colour controls and documentation and adds the scorebug assets module and both label assets.
- The authored label PNG has an exact path/size/dimensions/SHA-256 catalog entry and a refreshed catalog hash in the release checker. The binary-asset validator is unchanged.
- Provider/runtime seals are regenerated with `packaging/repin.py --apply`; counts remain 287 providers and 176 registry capabilities.
- The cave reservation manifest is regenerated last as the complete forward bounded XBE projection. Production regeneration remains required. External command: `bash reports/b71_a7/manifest_regen.sh`.

Exact file:line locations, measurements and final command receipts are in `ASTRA_REPORT.md` and `reports/b71_a7/`.

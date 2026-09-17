# Beta 71 A7 integration wiring

All protected files are granted for this job. S4 has no newly authored deferred wiring: `git diff 464423f0 7b54e354 -- WIRING.md` is empty. Its inherited beta-70 T1 instructions are archived anonymously in `WIRING_B71_S4.md`.

- The inherited completion-dialog hooks are already active at `mod_editor/gui/studio_qt.py:8023` and `mod_editor/core/build_feedback.py:53`.
- The inherited Windows-helper and digit-fit proposals are historical follow-ups, not S4 changes. This merge does not add an unreviewed executable or a digit writer.
- S4's runtime registry metadata is merged by capability ID; all 176 unique rows remain.
- The release allowlist retains the colour controls and documentation and adds the scorebug assets module and both label assets.
- The authored label PNG has an exact path/size/dimensions/SHA-256 catalog entry and a refreshed catalog hash in the release checker. The binary-asset validator is unchanged.
- Provider/runtime seals are regenerated with `packaging/repin.py --apply`; the combined closure is 288 modules (A6 287 plus S4's painted-atlas assets dependency), with 176 registry capabilities.
- The cave reservation manifest is regenerated last as the complete forward bounded XBE projection. Production regeneration remains required. External command: `bash reports/b71_a7/manifest_regen.sh`.

Exact file:line locations, measurements and final command receipts are in `ASTRA_REPORT.md` and `reports/b71_a7/`.

# U1 direct integration

The U1 brief authorizes the updater, Linux packaging and launch checks. The
following integration edits are already applied; no deferred wiring is needed.

- `mod_editor/gui/studio_qt.py`, `launch_studio`, immediately before `app.exec_()`:
  `from mod_editor.core.self_update import notify_update_ready` followed by
  `notify_update_ready()`. This schedules the first-event-loop acknowledgement
  only when an updater supplied its private readiness path.
- `mod_editor/apf_studio/gui.py`, `launch_studio`, immediately before
  `application.exec_()`: the identical two lines, for the shared tarball updater.
- `mod_editor/gui/update_ui.py`, `_confirm_dialog` and `_on_done`: describe the
  preflight/automatic restore and show the actual retained backup path.
- `packaging/check_apf2k8_mod_studio_{release,runtime}.py`: require the selected
  interpreter invocation, `.studio-python`, `--update-check`, and runtime-specific
  dependency advice in the launcher contract. No audit is removed.
- `packaging/check_2k5_mod_studio_runtime.py`: `repin.py --apply` updates the
  existing `studio_qt.py` source digest for its two-line acknowledgement hook.

The existing beta-tag parser already supports `beta-71.1`; its grammar is
unchanged. `update_check.BUILD_RELEASE_TAG` and its test are stamped `beta-71.1`
so the hotfix will not advertise itself again. Product RC versions are unchanged.
All NSIS code and the Windows installer
handoff functions are unchanged. No registry rows or cave reservations change.

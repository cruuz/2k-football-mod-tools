# Scorebug v3 evidence

The v3 source is built from the A5 integration at `a7440f05`.

- `measurements.json`: reference-frame provenance, measured text boxes, native boundaries, pixel errors, volume and containment for both aspects.
- `compare_43.png` and `compare_wide.png`: the ESPN crop beside the native execution/software raster result. These are not game captures.
- `states.json` and the event crops: native flag, hang-time, ball-on, FUMBLE event and hidden-play-clock states. The synthetic all-events image is a stress diagnostic, not a valid simultaneous retail state.
- `multi_digit_scores.json` and `scores_*_crop.png`: 28, 100 and 999 stay clear of the plate in both aspects.
- `compiler_pins.json`: regenerated resource identities.
- `*.result.json` and `*.log`: command, UTC start/end, elapsed seconds, exit code and output. Preliminary failures remain visible; the report identifies the final runs.

Reproduce the renders with `PYTHONPATH=.:tools python3 reports/b71_s3/prove_v3.py`. The default frame path is local evidence; `--reference` accepts another copy of frame 012001. The retail pack and XBE are read through the existing `extracted` link. Generated native binary payloads are never saved here.

Import the bundle into the integration checkout before building; the private Git ref does not update this worktree’s ordinary read-only HEAD. The external build entry point is `bash reports/b71_s3/launch_testdisc71.sh`. It builds the Advanced preset with scorebug, scorebug runtime, modern colour and widescreen, reparses the result and exports its patch. The output name is `NFL 2K5 MOD TEST 2026-09-15h (scorebug v3 + colour + widescreen)`. Only `--plan-only` is executed in this session.

The builder checks destination access, preserves existing patch archives and follows A5's at-most-three MOD TEST image policy. It refuses an existing named output. The actual image, patch and played-game behavior remain UNWITNESSED.

Final validation uses `bash reports/b71_s3/launch_final_checks.sh`. It runs every scorebug test program with two independent processes, regenerates the complete XBE projection from the A5 parent, then detaches both XBE gates. Final result names end in `-release`; preliminary results remain in the ledger. The final resource appendix is 413,568 bytes (0.394 MiB), including narrower metrics for multi-digit scores with no extra atlas pixels.

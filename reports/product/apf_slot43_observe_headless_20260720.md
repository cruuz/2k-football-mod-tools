# APF 2K8 slot-43 observation control — headless result

Date: 2026-07-20  
Result: **completed negative (`path_not_reached`)**

## Question

Does an ordinary no-input APF boot traverse the exact defensive-roster
count/getter pair used by the bounded slot-43 prototype? A positive observation
would be required before the separately gated one-player override could run.

## Valid control

- The reviewed, hash-pinned Linux Xenia build ran for the complete 180-second
  bound under Xvfb with null graphics, audio, and controller backends.
- The override remained disabled for the entire process.
- Xenia booted the supported APF executable and was stopped by the runner's
  normal timeout/SIGTERM boundary.
- The complete source-tree digest and `default.xex` digest were identical
  before and after the run. The runner made no direct source write.
- No target-match or accepted-validation receipt appeared for the exact
  slot-43 consumer path.

The classification is therefore `path_not_reached`, with reason
`complete_target_receipts_not_seen`. This is not a validator failure and not a
crash. It means a passive boot does not exercise the needed roster-builder
path.

## Setup defect found first

An earlier launch attempt used a private run root whose pathname contained
spaces. `xvfb-run` mishandled the resulting Xauthority pathname and Xenia exited
before logging with `Failed to initialize GTK+`. The source remained unchanged.
The valid control above used the same reviewed binary and game through a
no-space private run root.

The runner fix is now implemented in both the slot-43 and membership-census
runners. `xvfb-run` receives no private `TMPDIR`, so it creates its owner-only
Xauthority directory under `/tmp`; the fixed `env` executable restores the
run-private temporary root only for the Xenia child, without a shell. All 44
focused synthetic tests pass. A direct test of the installed `xvfb-run` with a
synthetic child also completed from a spaced run root with return code zero,
Xauthority under `/tmp`, and the exact private child `TMPDIR`. This does not
claim a post-fix spaced-root Xenia run; the valid 180-second Xenia control
remains the no-space run described above.

## Claim boundary

This experiment does **not** prove a 43rd player, 53-player teams, 32-team
offline selection, depth-chart behavior, substitutions, injuries, statistics,
or saves. Modified mode remains locked because its required positive observe
control did not occur.

The next causally useful experiment must deliberately navigate an isolated APF
session into the defensive roster-builder path—either through a reviewed
scripted virtual-controller profile or a designated hands-on operator on a
private display—then rerun observation before any override is enabled.

# APF 2K8 slot-43 Xenia experiment

## Outcome

The version-pinned, emulator-only slot-43 prototype and retail-free runner are
implemented. The first valid **observe** control ran headlessly for the full
180-second bound and completed as `path_not_reached`: ordinary no-input boot
did not traverse the exact count/getter pair. The complete source tree and
`default.xex` remained unchanged. Modified mode therefore stays off until a
later, deliberately navigated observe control records one complete traversal.

An earlier spaced-path attempt exited in 164 ms with `Failed to initialize
GTK+` because `xvfb-run` mishandled its Xauthority path. The runner now keeps
`TMPDIR` away from `xvfb-run` and restores the private temp root only for the
Xenia child. Twelve slot-43 tests pass, including a no-shell spaced-path
regression, and the installed `xvfb-run` completed the same synthetic boundary
with its Xauthority under `/tmp`. That last test used a synthetic client, not
Xenia; no post-fix spaced-path Xenia run is claimed.

## Exact pins

| Item | Pinned value |
| --- | --- |
| Xenia base | `6e5b8324f4101464de0f8c2334edb03cac8826c4` |
| Reviewed hook commit | `d145430737f787f522e08e7d86d3e94bdde6d6a1` |
| Native Linux binary SHA-256 | `e8d7fda95239d12c11a1d2b336bbed33b39d1da738a65dc2e757c16b8d215641` |
| Supported APF USA `default.xex` SHA-256 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| APF title ID | `0x54540807` |
| Loaded-module hash | `0x5447E5428AA2D52A` |

The reviewed source is retained on the private research host. The compiled
binary is an experiment artifact, not part of the public Mod Studio package.

## What the hook does

The hook changes no XEX, ROST, team record, source game file, or persistent
save. It adds five opt-in host callbacks at exact guest instruction addresses:

| Guest PC | Role |
| --- | --- |
| `0x84AB9840` | Count-helper entry |
| `0x84AB9880` | Normal count-helper return |
| `0x84AB9930` | Position/getter entry |
| `0x84AB997C` | Getter miss return |
| `0x84AB9988` | Getter found return |

Only caller returns `0x84A16D34` and `0x84A16D50`, position byte `4` (CB),
Team 0, and one exact downstream defensive-roster consumer are eligible. All
other helper traffic returns unchanged before a full ROST scan.

The full acceptance gate requires:

- the pinned title ID and module hash;
- 2,254 player records and 40 team records;
- the exact Team-0 root pointer and 42-player counted roster;
- exact Team-0 membership indices `84..125`;
- exactly four stock Team-0 cornerbacks;
- candidate player index `1032`, position CB;
- candidate 1032 absent from every counted membership across all 40 teams;
- readable, overflow-bounded guest ranges for every dereference.

Validation is cached only for one exact defensive-builder traversal. Every
matching count entry invalidates the prior cache, fully revalidates, and binds
the result to the same guest thread and Team-0 pointer for its following exits
and getter calls. A title relaunch or concurrent traversal therefore cannot
reuse a stale player pointer; interference fails closed.

In **observe** mode the callbacks only emit bounded receipts. In **modified**
mode, after the same gates, the count return changes from four CBs to five and
only ordinal four's miss return changes from null to candidate 1032. No other
register result or guest memory is changed. This is intentionally much smaller
than a roster-capacity patch.

## Headless runner

The private `apf_slot43_xenia_experiment.py` research runner accepts the user's
own extracted APF directory and the reviewed Xenia binary. The runner and Xenia
binary are not distributed with Mod Studio.
It pins both hashes, creates new owner-only storage/content/cache/home/XDG
roots, and forces:

```text
gpu=null
apu=nop
hid=nop
apply_title_update=false
apply_patches=false
allow_plugins=false
discord=false
apf_roster_slot43_log=true
```

It runs through `xvfb-run`, never the user's active display. The process group
has a bounded timeout and SIGTERM/SIGKILL fallback. The complete source game
tree and `default.xex` are hashed before and after. Raw Xenia output stays in
the private run directory; `result.json` retains only counters, booleans,
reason codes, hashes, and relative artifact names—never guest pointers or raw
log lines.

The wrapper deliberately leaves `TMPDIR` unset while `xvfb-run` creates its
owner-only Xauthority directory under the system `/tmp`. It then invokes Xenia
through the fixed `env` executable, with the run's private `tmp` directory set
only for the Xenia child. This keeps Xenia isolated and also supports run-root
paths containing spaces; no shell command or user environment is involved.

The parser recognizes four conservative results:

- `path_not_reached` — the exact complete traversal was not observed;
- `validation_rejected` — execution, source integrity, hook gates, ordering,
  mode, or receipt syntax failed;
- `observe_path_proved` — count entry/exit plus ordinary getter traffic formed
  one ordered traversal with no modifying action;
- `modified_path_proved` — the count increment and ordinal-four candidate
  return formed one ordered traversal.

Modified mode additionally requires the exact confirmation token printed by
the command-line help. It is not authorized by an ordinary `--mode modified`
argument alone.

## Completed checks

1. Clang 19.1.7 compiled the hook into `xenia-cpu` Release.
2. The complete native `xenia_canary` Release executable linked with no missing
   dynamic-library dependency.
3. Independent review confirmed the PPC addresses, LR/register ABI, HIR
   ordering, bounds, stock membership assumptions, per-traversal cache, and
   fail-closed behavior.
4. The runner's 12 synthetic tests passed, including cross-traversal rejection,
   modified-mode confirmation, source mutation rejection, obsolete-pin
   rejection, sanitized output, and the spaced-path temp split.
5. The real-source dry-run admitted the pinned executable and game, generated
   the exact isolated observe command, hashed six game files totaling
   `3,919,218,688` bytes before and after, and reported both the whole tree and
   `default.xex` unchanged. Xenia was not launched.
6. The valid no-space observe control booted Xenia for 180 seconds, preserved
   both source digests, and completed `path_not_reached` with
   `complete_target_receipts_not_seen`.
7. The installed `xvfb-run` plus a synthetic child proved that a spaced run
   root now leaves Xauthority in `/tmp` while the child receives the exact
   private `TMPDIR`. A post-fix spaced-root Xenia rerun has not been performed.

## Remaining runtime order

1. Deliberately navigate a fresh isolated **observe** run into the defensive
   roster-builder path; passive boot is already a completed negative.
2. Accept a positive result only if it is exactly `observe_path_proved` and the
   source-integrity booleans are true.
3. If the result is `path_not_reached`, complete the experiment as a negative
   for the no-input boot route; do not turn on the override merely to make a
   receipt appear.
4. Only after a positive control, run one separately isolated **modified**
   process.
5. Promote no product capability until modified mode records both
   `count_incremented` and `candidate_returned` and the game remains stable.

The completed passive control used private Xvfb plus null graphics/audio/input
and never addressed the user's active display or pointer. Any future hands-on
navigation must remain on the isolated test desktop. A reviewed scripted
virtual-controller route is also acceptable if it remains bound to the private
run and exact observe-only mode.

## Claim boundary and next work

Even `modified_path_proved` would establish only one 43rd player through one
consumer. It would **not** prove 53-player teams, depth charts, substitutions,
Play Now selection, statistics, saves, all 32 teams, or season/franchise
compatibility.

A true 53-player implementation still needs separately owned reserve storage
plus an inventory and redirect of every membership consumer. The already
populated 32 on-disc team records are a distinct opportunity, but teams 24–31
still need offline selector/runtime ownership proof. The best next action is a
deliberately navigated isolated observe run—not another passive boot or offline
schema change.

# CPU fourth-down triggers and Xenia

## Fourth-down settings

Open **Tools → CPU fourth-down triggers**. Choose **Retail BASE** or **Title
Update 1.1**, review the eight global thresholds and compare the retail and edited
decisions. The settings affect every CPU book. They are independent of the CPU
Play Calling situation table.

The patch is **experimental and disabled by default**. Export writes a separate
authored `.patch.toml`; it does not edit a game folder or project. Check **Enable
this experimental patch**, then **Review and install** to use it in Studio
launches. Installation enables Xenia's patch switch, which also allows other
installed patches marked enabled. Restart Xenia after changing patches. **Remove
patch** removes the managed file; the next Studio launch also removes its stale
storage-root copy. It leaves Xenia's shared patch switch enabled.

| Control | Retail value | Meaning |
| --- | ---: | --- |
| Punt short-yardage cutoff | 1 yard | Above this distance, the ordinary punt gate can choose a punt. |
| Automatic punt beyond goal distance | 50 yards | In the ordinary early-game branch, punts beyond this distance to the attacking goal. |
| Short-yardage punt probability per spare yard | 0.05 | Below the cutoff, compares cached random value with `(cutoff − distance) × slope`. |
| Fallback kick random threshold | 0.95 | A random value above this can still select a kick after the main predicates. |
| Field-goal safety margin | 5 yards | Subtracted from kicker range at neutral urgency; urgency can reduce it. |
| Draw-offside maximum distance | 2 yards | Additional retail score, clock, timeout and field-position gates still apply. |
| Draw-offside maximum goal distance | 55 yards | Maximum distance to the attacking goal for this attempt. |
| Draw-offside timeout below play clock | 2 seconds | Timeout dispatch uses **strictly less than** this value, with the draw flag active. |

For a retest starting point, raise the short-yardage cutoff to **2**, the
automatic-punt goal distance to **75**, and the fallback threshold to **1**.
The bounded neutral fourth-and-one test changes from punt to a scrimmage call at
52 yards from the goal. This is an illustrative test setup, not a validated
coaching preset or an all-situations guarantee.

The preview fixes first period, tied score, neutral urgency, a 50-yard kicker
range and cached random value 0.5. Late-game strategy and real kicker skills can
change the choice. Bounded native proofs do not establish on-field behavior:
the complete animation, timeout consumption and following call are
**UNWITNESSED**. See the [address and proof ledger](../research/apf_b71_fourth_down.md).

CLI export, disabled unless `--enable` is supplied:

```sh
python3 -m mod_editor.core.apf2k8_fourth_down --profile tu_1_1 --output fourth-down.patch.toml
```

Optional `--thresholds authored.json` accepts the eight named fields from
`Thresholds` in the backend. Omitted fields use retail defaults. Use the profile
that matches the executable actually loaded by Xenia. BASE and TU patches have
different module hashes; this does not install the title update itself.

## Xenia Edge and SDL controllers

**Xenia Configured → Choose Xenia Edge (recommended) or Canary** accepts either
runtime. Common Edge/Canary filenames are detected without running them. For a
renamed executable, select the corresponding **renamed executable** file filter.
Windows `.exe` files launch directly on Windows and through Wine on Linux.
Native executable and AppImage paths launch directly on Linux.

Studio writes `[HID] hid = "sdl"` into the selected runtime's config and also
passes `--hid=sdl` when launching. Default filenames are
`xenia-edge.config.toml`, `xenia-canary.config.toml`, and `xenia.config.toml` for
an unclassified runtime. Existing settings and an explicitly selected config
remain supported. Malformed configs refuse with an error before launching.

Edge is recommended here for its SDL input path. Upstream Edge declares SDL as
the default HID driver and uses the Edge config filename. This recommendation
does not claim a gameplay or stability comparison. Sources:
[Edge input registration](https://github.com/has207/xenia-edge/blob/edge/src/xenia/app/xenia_main.cc)
and [Edge config reader](https://github.com/has207/xenia-edge/blob/edge/src/xenia/config.cc).

An **XMA-decoder crash was reported on Canary**. That is a Canary observation;
its cause and any relationship to edited game data remain unproved. Edge
support and SDL input are not an XMA-decoder fix. This job launched neither
runtime and collected no controller, audio or gameplay witness.

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

## Community play-calling patches (Basileus Maximus)

Open **Tools > Community play-calling patches (Basileus Maximus)**. Three Xenia
patches by community modder **Basileus Maximus**, shipped with his permission,
for **Title Update 1.1 only**:

- **Play calling by package fixed**: every package can be picked in the play
  call screen and applies to every formation; Punt, Field Goal and the other
  kicking packages open their own formations.
- **All packages in substitution menu**: the Substitutions screen lists every
  package, in the main menu and in game, in a fixed order, and keeps new
  formations next to their family.
- **Hidden formations revealed**: offensive formations the game leaves out of
  their family are grouped with it in the Playbook Manager and the in-game
  picker.

All three start **off**. **Review and install** writes the Studio's copy into
the Xenia patches folder and enables Xenia's patch switch, like the other
Studio patches; **Remove** takes it out again. Each patch file keeps
`author = "Basileus Maximus"`.

The author's original files put the first two patches' code into
`0x84D0D400..0x84D0D7E7`, which the Studio's charged-abilities patch also uses,
so the two could not be enabled together. The Studio's copies move that code to
its own reserved space (`data/apf2k8/patch_reservations.json`):
`0x84D0D980..0x84D0DAEF` (play calling) and `0x84D0DC00..0x84D0DE6F` (all
packages); hidden formations (`0x84D0D800..0x84D0D94F`) and the all-packages
family table (`0x84D0DB00..0x84D0DBAF`) stay where he put them. Only branch
offsets and one table address change; every other instruction is his. A
Capstone check compares both versions instruction by instruction. Do not keep
his original files for the first two patches in the same patches folder: the
Studio refuses to launch when they sit next to the charged-abilities patch.

These patches change menus and play calling. Their in-game behavior with
Studio builds has not been witnessed by the Studio maintainers.

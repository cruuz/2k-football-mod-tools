# Visual xemu QA driver

This Linux helper starts one private Xvfb display, xemu Flatpak, and a virtual
Xbox 360 controller. It uses the existing `tools/xemu_virtual_gamepad.py`.
Requires system Python with evdev, qemu-img, Xvfb, xdotool and ImageMagick.
The original config, HDD, EEPROM and disc are read only. The writable HDD is a
standalone compressed QCOW2 copy, with all virtual sectors compared before boot.
Launch under `nice -n 19 ionice -c3`. No network configuration is changed.

```bash
nice -n 19 ionice -c3 python3 tools/b77/visual_xemu_driver.py serve \
  --scratch /absolute/private/scratch \
  --name run01 \
  --config /path/to/original/xemu.toml \
  --disc /path/to/shipped.xiso.iso
```

Keep this process running. In another terminal send exactly one command:

```bash
python3 tools/b77/visual_xemu_driver.py cmd --scratch /absolute/private/scratch \
  '{"op":"wait","seconds":30,"note":"boot legal screen"}'
python3 tools/b77/visual_xemu_driver.py cmd --scratch /absolute/private/scratch \
  '{"op":"tap","button":"START","hold":0.3,"seconds":1,"note":"title prompt"}'
```

**Open the returned PNG in an image viewer after every input.** Decide the next
input from that picture and write the screen and controls in `menu_map.md`.
The driver does no OCR, menu classification or blind route playback. Each step
resumes the machine, releases the button, pauses through QMP, and captures only
the private xemu window. Input hold is 0.03 to 2 seconds and wait is 0 to 55
seconds. Use at least 0.5 seconds after ordinary menu taps, and wait again if the frame still shows a transition. Too-short captures can show the previous screen even after input was accepted. A held direction may repeat in some menus; play-call D-pad navigation advanced once per press in this session. `wait` sends no pad input.
The VM stays paused while its frame is reviewed, avoiding menu/play-clock drift.
`active_seconds` counts only resumed step intervals, excluding review time.
Controls include A/B/X/Y, START/BACK, LB/RB, LT/RT, D-pad directions,
and `LS_` / `RS_` LEFT/RIGHT/UP/DOWN. Vertical right-stick inputs are exposed; this game used three A-button meter steps for the tested kickoff.
Restart the helper after changing its supported controls.
The helper's X/Y codes now follow the Linux Xbox labels (`BTN_X`/`BTN_Y`).
Its previous NORTH/WEST choices were reversed under SDL's Xbox 360 mapping.

Commands are JSON objects with `op` and optional `note`:

| Operation | Additional fields | Result |
| --- | --- | --- |
| `tap` | `button`, `hold`, `seconds` | ACK, release, pause, frame |
| `wait` | `seconds` | Run without input, pause, frame |
| `capture` | | Frame of current paused state |
| `note` | `note` | Append reviewer observation to events |
| `save` | `name` | Internal QCOW2 snapshot and frame |
| `load` | `name` | Restore snapshot, remain paused, frame |
| `status` | | QMP status, snapshot list, free space |
| `stop` | | Shut down only owned processes and verify originals |

Save `main_menu`, `franchise_hub`, and play-call checkpoints as they are reached.
Snapshots are **inside `scratch/snapshots.qcow2`**, not separate state files.
The human monitor `savevm` / `loadvm` commands are sent through a private Unix
QMP socket. There is no TCP monitor. See the [official snapshot documentation](https://xemu.app/docs/snapshots/)
and [CLI documentation](https://xemu.app/docs/cli/). The disc must be mounted and
the controller configuration must match on restore. The next `serve` reuses the
private HDD and connects the same virtual-controller GUID. It refuses reuse if
the original HDD hash changed, so use a new scratch folder in that case.

Review snapshot restoration visually and test that an input changes the screen.
In this QA session, two cold restores were followed by guest halts: one during
the following game load, and one after RIGHT at offensive play selection.
The same franchise matchup loaded from a fresh boot. Same-process main-menu
and kickoff restores responded normally. A defensive DOWN input halted after
a same-process restore, then reproduced on two fresh boots, including a new
copy of the original HDD. The final run captured HLT=0 before DOWN and HLT=1
afterward at native address 0x0017fedb. Do not attribute that defensive fault
to snapshot restoration. Keep snapshot-associated and fresh-boot evidence
separate; retained snapshots are diagnostic artifacts, not a guarantee of
reliable restoration in this build. Frame labels describe input intent; the
actual screenshot establishes which screen was reached.
Do not count time spent paused for review as gameplay. A static play-call or
pause screen alone does not establish a hang. For a suspected hang, save an
additional frame after at least 45 active seconds and try a reviewed navigation
or START input, recording whether the picture or clock responds. Store before
and after frames, exact buttons and monitor/log errors. CPU games require
visible save, schedule, matchup and centered-controller evidence. A frame
showing moving football alone cannot establish franchise provenance.

Outputs: numbered PNGs, `events.jsonl`, pad ACK log, xemu log, launch manifest,
`cleanup.json` with original-file hashes, `hdd_copy.json` with comparison receipt,
and `snapshots.txt`. `run01` through `run12` are accepted; existing run folders
are refused. The process refuses an existing exact-name xemu and checks again
immediately before launch. Cleanup signals only processes carrying this run's
environment marker. A 55 billion byte root reserve is checked every two seconds
while idle and each half second during a step. The local advisory lock prevents
another driver from using the same scratch folder. Other tools must also obey
the one-xemu rule. Keep the original files immutable; do not use a copied
snapshot to claim the original HDD remains logically identical after gameplay.

These are automated emulator observations. Noah's gameplay acceptance remains
separate. The driver changes no game source or native disc bytes.

For a visually confirmed CPU game, collect a timed passive watch:

```bash
nice -n 19 ionice -c3 python3 tools/b77/visual_xemu_driver.py observe \
  --scratch /absolute/private/scratch --label franchise_cpu --seconds 1210
```

This sends only `wait` requests, writes one PNG each 55 active seconds, and
retains `franchise_cpu_watch.json`. Inspect the frames as they arrive. There is
no automated PASS or HANG classification. The active time is conservative:
requested run intervals exclude screenshot, review, setup and loading time.
The observer accepts up to two hours and intervals up to 55 seconds, and refuses
to overwrite an existing observation label. To stop observing, interrupt the
observer; the driver completes the pending bounded step and stays paused.

For a suspected hang, `{"op":"diagnose","note":"what stopped"}` retains
CPU registers and VM status. Add `"dump_memory":true` to retain a 128 MiB
physical-memory image in the run folder for native-code diagnosis. No arbitrary
monitor command or writable destination is accepted. This is a diagnostic
capture, not a game-code patch. Keep it private with the copied HDD and saves.

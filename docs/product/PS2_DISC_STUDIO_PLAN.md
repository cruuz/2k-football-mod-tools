# PS2 NFL 2K5 Studio — implementation plan

> **Status 2026-09-05 — delivered on branch `ps2-disc-studio`.** Service, worker, six lane
> adapters, window shell and six tabs, the two entry points, 60 tests, allowlist lines,
> docs and the real-disc trial are in. Every deviation from the plan as first committed
> is recorded in §15.

The six PlayStation 2 on-disc writers of Phase 2 exist today only as command-line
tools: text banks, playbooks, uniform colours, the disc roster, stadium position
lanes and exact-slot AUDO sounds (`docs/product/PS2_PHASE2_*.md`; registry rows
`nfl2k5ps2.menus.text_banks`, `nfl2k5ps2.scripts.director_playbook`,
`nfl2k5ps2.colors.unif_words`, `nfl2k5ps2.players.disc_roster`,
`nfl2k5ps2.stadiums.position_lanes`, `nfl2k5ps2.audio.audo_exact_slot_replace`).
Each row's `gui.reason` says the same thing: *nothing in `mod_editor/` is wired to
it — there is no Qt-free service and no dialog — and when it surfaces it will be a
separate PS2 window off the File menu, following the PS2 save editor and PS2 Disc
Inventory windows.* The **PS2 NFL 2K5 Studio** is that window: one dialog, a tab per
lane, a Build page that writes a **new** ISO from the user's own disc and shows
the independent verifier's verdict.

It inherits every constraint in [`PS2_PORT_HANDOFF.md`](PS2_PORT_HANDOFF.md)
(passivity review, retail-free outputs, no facade gating) and the M1 shape in
[`PS2_M1_PLAN.md`](PS2_M1_PLAN.md) (Qt-free service + thin dialog + File-menu
entry + `--flag`). Nothing here repeats those except where a decision is new.

## 1. Definition of done

1. `File ▸ PS2 NFL 2K5 Studio…` and `python -m mod_editor --ps2-disc-studio [ISO]`
   open one window that: opens the user's ISO read-only and identity-checks it;
   builds or loads each lane's target catalogue **from that disc** through the
   lane's own catalogue tool; lets the user stage bounded edits per lane with the
   budget on screen; plans every staged lane (dry run) so every refusal is shown
   before any image exists; builds a NEW image (destination must not exist; the
   source is never written); runs each lane's independent verifier on what was
   written; and shows the receipt.
2. Two lanes staged together build as a chained queue (source → intermediate →
   destination), each step verified against its own input before the previous
   intermediate is deleted.
3. Service tests on the lanes' own synthetic discs and offscreen dialog tests
   pass; the three repository gates (`test_generated_artifacts_are_lf`,
   `test_shipped_tools_are_self_sufficient`, `test_ps2_lane`) stay green; zero
   new failures elsewhere.
4. One real-disc trial: text + colours catalogues built from the stock ISO, a
   two-lane recipe (one shorter-or-equal string, one facemask colour) built to
   gitignored scratch, both verifiers PASS, timings/sizes/digests recorded in
   `reports/gameplay_tuning/nfl2k5_ps2_disc_studio_trial.v1.json` (names,
   offsets, hashes only).
5. Getting-started section, RC85 changelog bullet, allowlist entries, and this
   plan kept current. The registry is **not** edited here; the exact per-row
   changes go to the coordinator (§13).

Not done here, deliberately: nothing is put on a screen in an emulator. Every
lane stays `offline-writer-proved`; the window says so in plain words.

## 2. What the user experiences

```
File ▸ PS2 NFL 2K5 Studio…   (or  --ps2-disc-studio  [my.iso])
  → Open Disc Image…  → identity line: "SLUS-20919 · retail boot ELF · 4,665,081,856 bytes"
  → each tab shows "Catalogue: not built yet — Build catalogue (about N s)"; building runs in
    the background with progress and a Cancel button; a built catalogue is cached on this
    machine, keyed by the disc, so the next open is instant
  → Text tab: search 6,658 editable strings (the original text is read from YOUR disc and
    shown; it never enters a recipe or receipt) → type a replacement no longer than the
    original → "3 of 9 characters left" / red "one character too long — the budget is the
    original's own length" → Add to recipe
  → Colours / Roster / Playbooks / Stadium / Audio tabs: same shape, each with its own
    picker, editor, budget and caveats
  → Build tab: the queue (lanes with staged edits, in a fixed order), the destination
    (a name that does not exist yet), free-space and time expectations, "Check everything"
    (dry run — refusals surface here, nothing is written), then "Build new ISO"
  → progress per step: plan → write → verify; Cancel deletes a part-written image
  → receipt: what changed (counts, offsets, digests), each verifier's verdict, timings,
    "Open folder"; a JSON receipt is written beside the new image
```

## 3. Passivity: what changes where

Everything new lives in PS2-only files nothing upstream imports:

| component | path | kind |
|---|---|---|
| Service core: identity, cache, catalogue builds, queue, receipts | `mod_editor/core/ps2_disc_studio_service.py` | Qt-free, tested |
| Six lane adapters (recipe schema, budgets, plan/apply/verify glue) | `mod_editor/core/ps2_disc_studio_lanes.py` | Qt-free, tested |
| Build-step worker (`python -m mod_editor.core.ps2_disc_studio_worker`) | `mod_editor/core/ps2_disc_studio_worker.py` | Qt-free, stdlib, tested |
| Window shell, header, Build page, task runner | `mod_editor/gui/ps2_disc_studio_qt.py` | thin Qt |
| The six lane tabs | `mod_editor/gui/ps2_disc_studio_tabs_qt.py` | thin Qt |
| Tests | `tests/mod_editor/test_ps2_disc_studio_service.py`, `tests/mod_editor/test_ps2_disc_studio_qt.py` | synthetic discs only |
| Trial receipt | `reports/gameplay_tuning/nfl2k5_ps2_disc_studio_trial.v1.json` | evidence, not payload |

Upstream-owned files are touched only at the established hook points, and every
touched line is listed in the report:

- `mod_editor/gui/studio_qt.py`: one `_ps2_disc_studio_action` attribute, one
  File-menu `addAction` block mirroring `_ps2_export_action`, one
  `_open_ps2_disc_studio` handler mirroring `_open_ps2_export` (including the
  `_refuse_while_audio_busy` guard), one `setEnabled(not global_busy)` line
  mirroring `_ps2_disc_action`.
- `mod_editor/__main__.py`: one `--ps2-disc-studio [ISO]` argument mirroring
  `--ps2-export`, one dispatch block mirroring `--ps2-disc`.
- `packaging/release-allowlist.txt`: append-only lines for the five new modules.
- `docs/mod_editor/2k5_mod_studio_getting_started.md`: one new section;
  `docs/mod_editor/2k5_mod_studio_changelog.md`: one RC85 bullet.

Not touched: the registry, `validate_registry.py`, `packaging/check_*`, pins,
version numbers, `product_catalog.py`, `studio/facade.py`, any lane tool, any
Xbox module. Where the studio needs a helper (VC-LZ decode of a scene, the
playbook body parser, the formation designer) it **imports** the existing module
and never modifies it.

## 4. Service layer

### 4.1 Opening a disc

`Ps2DiscStudioService.open(path, progress)`:

1. `ps2_iso9660.open_image` (read-only) → `nfl2k5_ps2_disc_inventory.image_identity(image, hash_image=False)`:
   serial, boot ELF digest vs the pinned retail digest, `serial_matches`,
   `retail_boot_elf` — the same identity the Disc Inventory window shows, without
   its 550,000-row walk. `DiscIdentity.headline` has the same wording.
2. `discover_packs` + `read_outer_table` (52 KB): the pack layout. A disc without
   `/VC_20919` is refused with the inventory tool's own sentence.
3. **Disc key** = SHA-256 over `serial | boot_sha256 | size | volume_id | sha256(outer table bytes)`.
   Cheap (no whole-image hash), and sufficient to key a cache: a stale cache can
   only cause a *refusal* later, never a wrong write, because every patcher
   re-derives its targets from the live image at plan time (text and colours and
   roster rebuild their catalogue and pin against ours; stadium pins the scene's
   `system_sha256`; audio re-reads the slot; playbooks re-read the book).
4. A serial that is not `SLUS-20919` opens for reading but every lane says
   "this is not the disc the six writers were proved on" and Build is refused.
   A non-retail boot ELF is reported, not refused (a modded disc still edits;
   the pinned catalogues will refuse anything that actually moved).

### 4.2 Sidecar cache

`user_private_root() / "2k5-mod-studio" / "ps2-disc-studio" / <disc key>/`
(the same root `nfl2k5_source_cache` uses; created with
`platform_compat.create_private_directory`; overridable for tests). Contents:
one catalogue JSON per lane exactly as the lane's tool wrote it
(`text.json`, `colors.json`, `roster.json`, `playbooks.json`, `stadium.json`,
`audio.json`), plus `disc.json` (identity + key inputs) and `timings.json`
(seconds each catalogue/build step last took on this machine, so the UI can
say "about 40 s" instead of guessing). Catalogues are written to a temporary
name and renamed into place only when the tool exited 0, so a cancelled or
failed build leaves nothing behind. Every catalogue tool is retail-free by
construction (digests, offsets, counts; public roster names), so the cache
holds nothing a shared report could not; the decoded **text** the Text tab
shows is *not* cached — it is decoded from the user's disc on demand and kept
only in memory.

### 4.3 Catalogue builds

Each lane's catalogue is produced by **its own catalogue tool, run as a
subprocess** (`sys.executable <tool> --iso … --output|--json|--report <tmp>`):

| lane | tool | output flag | expected size |
|---|---|---|---|
| text | `nfl2k5_ps2_text_target_catalog.py` | `--output` | 6,873 string rows |
| playbooks | `nfl2k5_ps2_playbook_target_catalog.py` | `--output` | 37 books |
| colours | `nfl2k5_ps2_unif_color_target_catalog.py` | `--output` | 634 targets |
| roster | `nfl2k5_ps2_disc_roster_target_catalog.py` | `--output` | 76 rosters, 2,547 boot players |
| stadium | `nfl2k5_ps2_stadium_target_catalog.py` | `--json` (`--scan` or `--entry`) | 1,041 targets on one scene; more with `--scan` |
| audio | `nfl2k5_ps2_audo_target_catalog.py` | `--report` | 844 slots |

Why a subprocess rather than an in-process call: the tools have no progress or
cancel hook (only the colours tool takes a `progress` callback), the stadium
catalogue decodes VC-LZ scenes for minutes, and the coordinator's rule is not
to reshape the lane tools for the studio. A child process gives every lane the
same honest progress (elapsed time plus the tool's own stdout tail) and a real
**Cancel** (terminate; the temporary output is removed). The verifier lane of
the audio tool already runs `ps2_iso9660_verify` this way. Tests substitute a
sleeping command to prove cancel returns promptly and leaves no cache file.

The stadium catalogue offers two scopes in the tab: **one scene** (the proved
entry, ~1,041 targets, a minute or two) and **every stadium scene** (`--scan`,
477 scenes, potentially long; the tab says so). The scope is part of the cache
file name so both can coexist.

### 4.4 Lane adapters

`ps2_disc_studio_lanes.py` defines one `Lane` object per writer with a common
Qt-free surface the tabs and the worker share:

- identity: `id`, `title`, `registry_id`, `caveats` (plain words distilled
  from the registry row's `gui.reason`, `runtime.scope` and `input_constraints`
  — e.g. "Bytes proven, nothing on a screen yet"), `time_note`.
- `catalogue_command(tool_dir, iso, out, scope)`, `load_catalogue(path)`,
  `targets(catalogue) -> list[Target]` (uniform row objects with `key`,
  `label`, `detail`, `budget`, `searchable`).
- `describe_budget(target)`; `check_edit(target, values) -> refusal | None`
  (the inline, before-Add refusals: over-budget text, over-length name,
  out-of-range jersey, wrong-shaped WAV or too long, non-binary32 offset,
  duplicate target, no-op).
- `compose_recipe(edits) -> dict` in the **exact** schema the patcher's
  `parse_recipe`/`load_recipe` accepts (text: `{"edits":[{selector,new_text,
  expect_sha256}]}`; colours: `nfl2k5_ps2_unif_color_recipe/v1`; roster:
  `nfl2k5_ps2_disc_roster_recipe/v1` with `roster`; playbooks:
  `nfl2k5_ps2_playbook_patch/v1`; stadium: `nfl2k5_ps2_stadium_position_recipe/v1`
  pinned to the cached catalogue's file digest; audio: `nfl2k5_ps2_audo_recipe/v1`).
- `plan(source, recipe, catalogue_path, work_dir)`: the lane's own dry run —
  text `patch(dry_run=True)`; colours/roster `plan(source, recipe, pinned)`;
  playbooks `compile_edits`; audio `plan(iso, requests, catalog)`; stadium
  `load_catalog` + `load_recipe` + an in-process decode of the scene with
  `apply_positions` (alias/overlap and count checks) — the recompression fit is
  only decidable by the real run and the plan says so. Every refusal is the
  patcher's own sentence, surfaced verbatim (the export dialog's rule: one
  sentence per condition, never re-worded).
- `apply(source, destination, recipe, catalogue_path, work_dir) -> receipt`
  calling the lane's `patch`/`apply` exactly as its CLI does.
- `verify(source, destination, receipt, recipe, catalogue_path) -> verdict`
  calling the lane's independent verifier; `verdict.passed`, `verdict.summary`.

Reading the user's disc for display (never for output): the Text tab shows each
string's current text (the bank bodies are re-read and decoded with the
catalogue tool's own parsers); the Colours tab shows the current facemask and
turtleneck words as swatches (8 bytes per target); the Roster tab shows names
and jersey numbers (public data already in the catalogue) and decodes a
historic roster's players on demand; the Playbooks tab parses the chosen book
with `nfl2k5_playbook_inspector._parse_body` for formation/play names; the
Stadium tab decodes the chosen scene once to turn per-lane offsets into the
absolute positions the recipe schema requires. None of this reaches the cache,
a recipe preview, a receipt or the trial report.

### 4.5 Build queue and worker

`BuildRequest(source, destination, steps=[(lane, recipe)], work_dir)`. Steps run
in the fixed lane order text → playbooks → colours → roster → stadium → audio.
Before the first byte: destination must not exist (and must not be the source),
its parent must be a real directory, `available_bytes(parent)` must cover
`image_size × (2 if steps > 1 else 1) + 1.25 GiB` (two images can coexist while
the previous intermediate is still needed for verification, plus the staged
pack), and every step must have planned clean.

Each step runs in a **worker subprocess** (`python -m
mod_editor.core.ps2_disc_studio_worker <job.json>`): plan again against the
step's actual input (the intermediate, not the original), apply, verify
input-vs-output with the lane's verifier, write `result.json`, and stream
`{"event": …}` lines for progress. A subprocess because: the ISO writer has no
cancel hook, one step holds ~1 GiB of staged pack in memory (freed when the
child exits instead of lingering in the GUI process), and Cancel can kill the
child and delete the part-written image (the writer creates it `O_EXCL`; the
service removes it only if it did not exist before the step). The last step
writes straight to the destination; intermediates live beside it as
`.<destination>.step<N>.iso` and are deleted once the next step has verified
against them. `BuildReceipt` carries per-step recipe (user values + selectors),
the patcher's report/receipt, the verifier's verdict, timings, sizes and the
SHA-256 of the input and output of every step; it is written as
`<destination>.ps2-disc-studio-receipt.v1.json` with `newline="\n"`.

Honest time expectations shown on the Build page, from `timings.json` when
present and from the trial's numbers otherwise: each lane copies the whole 4.3 GB
image and rewrites a 1 GiB pack (minutes), verification re-reads both images
(a minute or two), a stadium edit recompresses a ~1.3 MB scene into 0–16 spare
bytes (tens of minutes; the STADIUMS doc measured 17 minutes).

### 4.6 Refusal surfaces

Three layers, each using the same sentence the layer below would:

1. **Inline, before Add** — budget checks in the editor (`check_edit`): the
   Add button is disabled and a red line says why, quoting the budget.
2. **Plan (dry run)** — per tab "Check this lane" and on the Build page "Check
   everything": the patcher's own refusal text, verbatim, with the lane named.
   Build stays disabled until every queued lane has a clean plan.
3. **Build** — anything the plan could not decide (stadium fit, disk full,
   destination appeared meanwhile): the worker's error, verbatim, plus the
   fixed footer "Your original disc image was not changed."

Wording rules follow `test_gui_refusal_wording.py`: never a dead end — every
inline refusal names the fix ("shorten it to N characters", "supply mono
audio", "choose a slot with more room"), and the window never promises
anything is visible in game.

## 5. Per-lane tab design

Every tab: a **picker** (search box + table over the catalogue; a
`QAbstractTableModel` over the in-memory rows — 6.9k/2.5k/1.0k/844/634/37 rows
need no paging, Qt only asks for what is visible), an **editor** for the
selected target with the budget on screen and inline refusals, **Add to
recipe**, the lane's **recipe list** (remove/clear), a read-only **recipe
preview** (the exact JSON that will be handed to the patcher), **Check this
lane** (dry run in the background), and a **caveats** card (plain words) with a
collapsible **Rules** list taken from the registry row's `input_constraints`.
Every control has an accessible name and description; every list is
keyboard-reachable; layouts wrap rather than clip (getting-started "Keyboard
access and readable layout").

| tab | picker rows | editor | budget shown | inline refusals | out of scope here |
|---|---|---|---|---|---|
| Text | 6,658 editable strings (label, bank kind, current text from the disc, used/limit, "used by N records") | one replacement line (multi-line allowed) | "N of M code units" from `allocation_bytes // 2 - 1` | longer than the original; empty; NUL; inline token dropped/added/reordered (`tokens_in`); duplicate; unchanged | the 215 read-only strings (listed greyed with the reason code) |
| Playbooks | 37 books (name, formations/plays/nodes, headroom, at-cap flag) | per book: add formation (donor + custom name + 11 slot positions — the Xbox `FormationDesignerDialog` when importable, else a bounded 11-row table), add play (donor + custom name; the Xbox `PlayDesignerDialog` when importable), add link | headroom counts; name ≤40 printable ASCII | book at the 270-play cap when adding a play; 50-formation cap; two edits on one book | route/node authoring beyond what the Xbox designer offers |
| Colours | 634 packages (selector decoded as "package 18 · home · variant 0", current facemask/turtleneck swatches from the disc; team names when the Xbox uniform catalogue is on this machine) | two colour pickers (either or both) | "4-byte packed ARGB" | no change; both blank; duplicate selector; compressed/unsafe target | visor; runtime semantics |
| Roster | boot + 75 historic rosters; 2,547 boot players (pool, index, names, jersey, capacities) | first/last name, jersey 0–99, face shield None/Clear/Dark | "N of M characters" per name from `capacity // 2 - 1` | over-capacity; zero-capacity placeholder; shared string; jersey out of range; no change | team, ratings, depth charts |
| Stadium | 1,041 targets (shape name, batch, vertex count, alias count) | three offsets dx/dy/dz applied to every vertex of the lane | vertex count; "N other targets share this span" | non-binary32 result; two aliases of one span; targets from two scenes; zero offset | choosing by stadium piece (ownership unproved); topology |
| Audio | 844 slots (name, unique?, channels, rate, capacity in seconds) | WAV picker | "your WAV: 2.31 s of 3.10 s (25,486 of 34,160 frames at 11,025 Hz)"; resample note | not strict PCM16 RIFF; metadata chunks; channel mismatch; too long; same slot twice | AUSB streams; which cue plays a shared name |

## 6. Threading

Same model as the disc inventory and export dialogs: a `QThreadPool(1)` and a
`_Task(QRunnable)` per operation with `stage`/`result`/`error`/`finished`
signals constructed on the Qt thread. Long operations — open, catalogue build,
per-lane plan, "Check everything", build — run there; the service's cancel
token is a plain threading `Event` the worker/catalogue subprocess loop polls.
The dialog never queries the service while an operation is running, refuses to
close while busy (status line, as the other windows do), and reports errors
after the busy state is cleared (never a modal over a spinner).

## 7. Build page

Queue list (lane, edits, plan state), destination chooser (`getSaveFileName`
with `DontConfirmOverwrite`; the service refuses an existing path with its own
sentence), free-space line, time-expectation line, **Check everything**,
**Build new ISO**, **Cancel**, indeterminate progress bar with the stage text,
a receipt card (per-step: changed bytes/ranges, verifier verdict, seconds) and
**Open folder** (`QDesktopServices.openUrl` on the destination's folder). The
boundary note at the top of the window: *"NEW IMAGE • Your disc image is opened
read-only and never changed. Only the edits you stage are written, into a new
file that is created only after every check passes. Nothing built here has been
seen or heard in an emulator yet."*

## 8. Entry points

`studio_qt.py`: `File ▸ PS2 NFL 2K5 Studio…` after the export entry, tooltip
"Edit text, playbooks, uniform colours, rosters, stadium positions and sounds on
a copy of an ESPN NFL 2K5 PlayStation 2 disc image. A new image is written; your
original and your Xbox project are not changed."; the handler mirrors
`_open_ps2_export` including `_refuse_while_audio_busy("open the PS2 Disc
Studio")`, the import guard and the closing status line.
`__main__.py`: `--ps2-disc-studio [ISO]` (`nargs="?"`, `const=""`) opening the
window alone, on the given image when one is passed.

## 9. Test plan

`tests/mod_editor/test_ps2_disc_studio_service.py` (synthetic discs from the
lanes' own builders: `test_nfl2k5_ps2_text.build_synthetic_iso`,
`nfl2k5_ps2_unif_color_target_catalog.build_synthetic_iso`,
`nfl2k5_ps2_disc_roster_target_catalog.build_synthetic_iso`,
`test_nfl2k5_ps2_playbook.synthetic_iso/synthetic_pack/default_books`,
`nfl2k5_ps2_stadium_position_patch.build_synthetic_disc`,
`nfl2k5_ps2_audo_target_catalog.build_disc/build_audo_chunk`):

- open → identity (serial, boot ELF not retail, packs) and disc key stability;
  a non-PS2 image is refused with the tool's sentence.
- catalogue build per lane via the real subprocess → cached under the disc key;
  second load reads the cache; the cache holds no decoded text / colour words.
- cancel mid-catalogue (sleeper command) → `Cancelled` within ~1 s, no cache file.
- per lane: targets and budgets; `check_edit` inline refusals (over-budget text,
  token drop, over-length name, jersey 100, WAV too long / wrong channels,
  non-binary32 offset, duplicates, no-ops); `compose_recipe` produces exactly
  what the patcher's own parser accepts; `plan` surfaces the patcher's refusal
  verbatim; `apply` then `verify` PASS and the source is byte-identical.
- destination-exists refusal, source-as-destination refusal, before any write.
- queue chaining on two lanes (text + colours on a disc that carries both
  bank and Unif fixtures): intermediate created and deleted, both verifiers
  PASS against their own input, receipt written LF, digests present.
- the worker module's `run_step` end to end, plus one real `python -m` run.

`tests/mod_editor/test_ps2_disc_studio_qt.py` (offscreen, skipped without
PyQt5): construction with a stub host; tab population from a synthetic
catalogue; over-budget inline refusal disables Add and names the fix; Build
disabled until a valid plan exists; accessible names on every named control;
close refused while busy; a refused open is reported not raised.

Wording: a test asserting every inline refusal sentence names a fix and none
claims runtime visibility (the `test_gui_refusal_wording.py` pattern, kept in
the studio's own test module so the upstream test file is untouched).

## 10. Real-disc trial

**Done, on the rig** (see §15 for why not the dev box). With the stock ISO opened
read-only: text and colours catalogues built by the lanes' tools (1.03 s / 0.51 s);
one shorter-by-one STRG replacement pinned by its original's digest (`String message
897`, 10 → 9 code units) and one facemask colour (`09H0`, `#12FF34`); both planned
clean (0.35 s / 0.09 s); the two-lane queue built a NEW image in 49 s with the text
verifier (`pass`, 10 bytes differ, exactly the edited allocation) and the colour
verifier (`PASS`, 634 Unif records decoded, 1,073,741,816 unchanged bytes compared);
the source re-hashed to the registry's retail pin. Report:
`reports/gameplay_tuning/nfl2k5_ps2_disc_studio_trial.v1.json` — names, selectors,
offsets, counts and digests, no decoded text or colour words; the images were
deleted after the verifiers ran. `reports/` is evidence only and is not allowlisted.

## 11. Docs, allowlist, coordinator handoff

- Getting-started: "PS2 NFL 2K5 Studio" section (how to open, what each tab does,
  the budgets, a new ISO is written and the original never touched, nothing
  seen in game yet, cache location, time expectations).
- Changelog RC85: one bullet.
- `packaging/release-allowlist.txt`: append the five modules; duplicates are
  fatal so each is checked first.
- Registry (coordinator applies, see the report): each of the six rows'
  `gui.expose: true`, `default_enabled` recommendation, a new `gui.reason`
  naming the window, and a sentence in `input_constraints` about the window;
  `product_modules` additions in `check_2k5_mod_studio_runtime.py`.

## 12. Out of scope

Emulator witnesses (each lane stays not-tested); AUSB streams; visor/other
colour words; roster fields beyond names/jersey/face shield; choosing stadium
pieces by name; topology changes; recompression speed-ups (the shared VC-LZ fill
helper belongs to the Xbox lane); a PS2 sidebar; any change to the six tools.

## 13. Effort

| step | estimate |
|---|---|
| plan | ½ d |
| service core + worker + six adapters | 2 d |
| window shell + Build page + six tabs | 2 d |
| entry points, tests, gates | 1 d |
| real-disc trial + docs + allowlist | ½ d |

## 14. Risks

- **Catalogue time on a real disc.** The text walk touches every chunk header
  of 4,322 entries; measured in the trial. Cache makes it a one-time cost.
- **Stadium fit is only decidable at build time** (tens of minutes). The tab
  and the Build page say so before the user commits; Cancel works.
- **RAM.** One step stages a 1 GiB pack in memory; two lanes on both Unif
  packs would be 2 GiB in one patcher run — the colours adapter splits a recipe
  that touches both packs into two steps.
- **Subprocess availability.** `sys.executable` must run the tools and the
  worker (`-m mod_editor.…`); the release layout puts `tools/` and the package
  root on the path (`test_shipped_tools_are_self_sufficient`), and the audio
  verifier already spawns `ps2_iso9660_verify` this way.

## 15. Deviations from this plan

- **Free-space rule tightened (owner request).** The plan allowed a single-step build to
  need only one image's worth of room. The owner's drive filled to 32 MB during this
  work and crashed the dev box, so the service now always requires room for the new
  image **plus one intermediate** plus the staged pack, whatever the step count, and
  the refusal states the sizes (`BuildEstimate.sentence`).
- **Trial ran on the rig, not the dev box (same reason).** No 4 GB image was written on
  the dev box. The stock ISO on the rig was opened read-only over SSH; the catalogue
  builds, the plan → build → verify cycle and the source re-hash ran there through the
  same service the window uses, detached with `setsid nohup`, and the images were
  deleted after the verifiers ran. The dev box ran the plan → refuse → build → verify
  cycle on the lanes' synthetic discs only.
- **Trial numbers.** The catalogue builds the plan called long-running took 1.03 s (text)
  and 0.51 s (colours) on the rig's storage; the text patcher's dry run 0.35 s; two
  chained steps 49 s in all (text: write 9.6 s, verify 11.4 s; colours: write 8.3 s,
  verify 8.9 s; hashing 3 s each). The "long-running" concern stands for the stadium
  catalogue's every-scene scope and for a stadium build step, which were not part of
  this trial.
- **Tabs split into a second module.** `ps2_disc_studio_qt.py` holds the shell, the task
  runner and the Build page; `ps2_disc_studio_tabs_qt.py` holds the six tabs. One window,
  as planned, two files.
- **Stadium recipe preview.** Composing a stadium recipe decodes the whole scene, so the
  tab previews the staged offsets and vertex counts; the exact recipe is composed at
  Check and Build (and never carries coordinates into a receipt).
- **Playbook links.** A play designed with the Play Designer's *Link* option is linked to
  the formation under the index the writer will give it (the book's play count plus
  its place among the pending additions); explicit links take indices.
- **Team names on the Colours tab** come from the Xbox uniform catalogue when the
  machine has one (it is derived from the user's XISO and not shipped); otherwise
  packages are named by decoded selector plus the current colour swatches read from
  the disc.
- **Catalogue and step subprocesses** are exactly as planned; the cancel test uses a
  sleeping command in place of the tool, since a synthetic catalogue builds in well
  under a second.


## 16. Export to PCSX2 from this window (added after the trial)

The owner's request: *"you need to be able to export to PCSX2 the same way from the
Disc Studio."* Somebody building a PS2 disc from their Xbox edits wants the uniform
art on the same emulator, and having to close this window to find **File ▸ Export PS2
replacement pack…** in the main window was the complaint.

A **PCSX2 Pack** page sits beside Build. **Export to PCSX2…** opens the existing
`Ps2ExportDialog` — not a fork of it — on the project-chooser path: this window has no
Xbox session, so it starts on whatever `.2k5mod` was chosen here last (`None` the first
time, which is that window's chooser). Every rule there is unchanged and unrestated
here: only targets the project marks edited are written, the emulator question still has
no default, and the independent verifier is still offered. **No disc image is read and
no ISO is built by this path**, so the export is offered whether or not an image is open
and is withheld only while this window is busy with the disc.

Once a pack has been written, **Write PCSX2 kit** calls
`tools/nfl2k5_ps2_replacement_pack_kit.build_kit` in this process — its Python API, not
its CLI — for the one emulator the pack's receipt names, writing
`<pack>-kit/<target>/` beside the pack: `HOW-TO.txt`, `settings.ini` and a
byte-identical copy of the pack. The card and the status line name where it went and
the setting that has to be on; with texture replacement off the game draws the retail
art and the pack looks like it did nothing. The offer stands down once a kit exists,
because the tool refuses a second one at the same place, and every refusal it makes
(a missing receipt, a pack whose bytes no longer match it, settings that are not that
target's) is surfaced verbatim.

Two files change, both PS2-only: the page and its handlers in
`mod_editor/gui/ps2_disc_studio_qt.py`, and one hook in
`mod_editor/gui/ps2_export_dialog_qt.py` — an optional `on_exported` callback and a
public `project_path`, both notifications that no plan, file or wording there depends
on. `studio_qt.py`, `__main__.py`, the registry, the allowlist and the packaging checks
are untouched; no module is added, so nothing needs allowlisting.

## Windows end-to-end (2026-09-05)

The shipped portable Windows build drove the service over the retail disc on the owner's PC: open and identity check, text and colour catalogues from the disc, one string and one facemask colour staged, a two-step chained build to a new image (text 34 bytes, colours 8 bytes; 368 s on a hard disk), every step verified by the lane's independent verifier, source opened read-only. Receipt with paths scrubbed: `reports/gameplay_tuning/nfl2k5_ps2_disc_studio_windows_e2e.v1.json`. Nothing was seen in game.

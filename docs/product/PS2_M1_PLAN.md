# PS2 M1 — implementation plan

> **Status 2026-09-05 — M1 reached.** WP1–WP6 landed on `ps2-lane` (manifest 5,379 rows; export
> service + independent verifier; export window + `--ps2-export`; registry row
> `nfl2k5ps2.uniforms.replacement_pack_export`, classified `extract-only` because the validator
> binds `offline-writer-proved` to writers with an edit surface and the registry's own definition of
> an exporter fits). WP7 witnessed: a 13-file pack exported by the shipped service rendered in
> PenguinScreen2 `8226182a` by GS-dump replay (ESPN shield, scorebug, kick-meter dial replaced against a reference frame from the same dump rendered with the community pack under modern names, not a pure stock frame;
> uniform parts — torso, sleeves, pants, gloves, head/hair — then witnessed on two player-filling dumps against an
> empty-pack control; the M1 user story, a uniform edited on Xbox seen on PS2, is met). Report:
> `reports/gameplay_tuning/nfl2k5_ps2_replacement_pack_runtime.v1.json`. Open: a witness of a
> uniform part on a near-camera player; `runtime-proved` needs a rule extension for exporters.
> **Stock PCSX2 (measured 2026-09-05):** three stock upstream builds (merge-base v2.7.469, v2.6.0, v2.9.30) loaded the
> classic-named pack unchanged: bit 14 has been ignored on parse since v1.7.5606. The break older packs hit is
> v1.7.4034 (region-only hashing): region-clamped textures get different names that no offline rename recovers;
> unclamped textures load everywhere; PenguinScreen2's Classic Texture Names restores whole-texture hashing. The
> share of region-clamped identities in the manifest is being measured; the report carries the version table.


**M1 is the first thing a modder can actually use.** A user edits a uniform in
2K5 Mod Studio exactly as they do today for Xbox, chooses *Export PS2
replacement pack…*, drops the resulting folder into PenguinScreen2, boots the
stock `SLUS-20919` disc, and sees their uniform on the field.

This document is the build plan for that. It assumes Slice 1 (the read-only
disc inventory, PR #27) is landed or landing, and it inherits every constraint
in [`PS2_PORT_HANDOFF.md`](PS2_PORT_HANDOFF.md) — read that first; nothing here
repeats it except where a decision changes.

## 1. Definition of done

M1 is reached when **all** of the following are true, in this order:

1. `mod_editor/data/nfl2k5-xbox-map.v1.json` exists, is committed, passes
   `tools/nfl2k5_ps2_replacement_pack_audit.py`'s schema check, and carries
   provenance (disc identity, emulator build, hash convention, method version).
2. A user with an edited uniform in an open Xbox project can run *File → Export
   PS2 replacement pack…* (or `--ps2-export`) and get a folder containing
   **only** their edited textures, named as canonical PCSX2 replacement files.
3. `tools/nfl2k5_ps2_replacement_pack_verify.py` — an independent verifier that
   does **not** import the exporter — passes on that folder.
4. Registry row `nfl2k5ps2.uniforms.replacement_pack_export` exists at
   `offline-writer-proved`, with `SURFACE_GAMES["uniforms"]` widened, every pin
   moved, and CI green on all eight checks.
5. **The render is witnessed**: the pack is loaded in a pinned PenguinScreen2
   build on the stock disc and the edited uniform is visible in-game. A runtime
   report is committed and the row moves to `runtime-proved`.

Anything short of 5 is not M1. Anything that emits an unedited texture is not
M1 either — see §6.

## 2. What the user experiences

```
open Xbox XISO  →  edit Lions away jersey (existing flow)
                →  File → Export PS2 replacement pack…
                →  dialog lists edited uniform targets: mapped ✓ / not yet mappable ✗
                →  choose output folder → Export
                →  receipt: N files written, M targets skipped (with reasons)
                →  "Copy textures/ into PenguinScreen2's config dir, enable
                    Load Textures, boot SLUS-20919"
```

The PS2 ISO is **not** required at user time for the texture lane. The manifest
is computed once from the stock disc and shipped as data (it is hashes, names
and asset ids — the same class of thing as `KNOWN_FINGERPRINTS`). The user
needs only their Xbox disc and PenguinScreen2.

## 3. Components

| component | path | kind |
|---|---|---|
| Manifest builder | `tools/nfl2k5_ps2_texture_map.py` | dev-time tool, stdlib |
| Pure-Python XXH3-64 | `tools/xxh3.py` | stdlib module, tested against 120,779 known hashes |
| The manifest | `mod_editor/data/nfl2k5-xbox-map.v1.json` | shipped data |
| Export service | `mod_editor/core/ps2_export_service.py` | Qt-free, tested |
| Export dialog | `mod_editor/gui/ps2_export_dialog_qt.py` | thin Qt, separate window |
| Independent verifier | `tools/nfl2k5_ps2_replacement_pack_verify.py` | does not import the service |
| Validators | `tools/validate_nfl2k5_ps2_replacement_pack.sh` + `.bat` | registry `validation_command` |
| Runtime report | `reports/runtime/nfl2k5_ps2_uniform_runtime.v1.json` | evidence for `runtime-proved` |

Follow the pattern Slice 1 proved: Qt-free service + thin dialog + File-menu
entry + CLI flag. **Do not** widen `product_catalog.py`'s `game != NFL2K5`
filter; **do not** touch `studio/facade.py` gating.

## 4. Work packages

### WP1 — Manifest builder  ·  2–3 days  ·  critical path

Productize the hop1 research (`docs/research/hop1/gscommon.py`, `hop1_v5.py`,
`final_tally.py`) into `tools/nfl2k5_ps2_texture_map.py`.

**Inputs:** stock `SLUS-20919` ISO; the Xbox inventory (the committed name-join
`.csv` from Slice 1, or a live walk of the Xbox disc via the existing
`nfl_outer.py`); optionally the community replacement pack for validation.

**Algorithm, per PS2 TXTR** (from `ps2_iso9660.py` + the disc-inventory walk):

1. Decode TEX0 → PSM, TW, TH, TBW, CBP, CSM; `bits = PSM | TW<<6 | TH<<10 |
   TCC<<14`. Disc TEX0 has TCC=1 on every texture; **emit bit 14 set** — that is
   the convention the shipped pack uses and pcsx2-VR's classic-TCC alias path
   accepts. Measured since: v1.7.5606 dropped TCC from the names PCSX2 dumps
   **and, in the same commit, made every parse path ignore bit 14**, so a
   bit-14 name has loaded on every build there has ever been — three stock
   builds (v2.7.469, v2.6.0, v2.9.30) loaded the classic-named pack with
   identical pixel counts. There is nothing to alias and nothing to rename.
   The **hash** is the thing that moved: see WP4.
2. Level-0 pixel hash: XXH3-64, seed 0, over the GS block image.
   - `mips == 1`: linear rows → `columnTable8` 16×16 block swizzle (PSMT4 uses
     `columnTable4`, low nibble first).
   - `mips > 1`: **try both** — linear first, then the c32 route (one-shot
     PSMCT32 upload 64 px wide = one 8 KB page; rebuild VRAM via
     `blockTable32`/`columnTable32`; read PSMT8 blocks via `blockTable8` + TBW).
     482 PNGs at mips 5–7 are linear-only; the "always c32" rule was wrong.
3. CLUT hash: XXH3-64 over 256 (PSMT8) or 16 (PSMT4) u32 entries. Source:
   1024 bytes at descriptor `+0x28` if present (TSET siblings), else `CBP·256`.
   Linear layout swaps CSM1 bits 3↔4; c32 layout uses the PSMCT32 VRAM read
   permutation; PSMT4 raw. **The CLUT base differs per layout** — linear uses
   `img_off + CBP·256`, c32 uses `CBP·256` into the rebuilt VRAM image.
4. Candidate filename: `f"{tex0:x}-{clut:x}-{bits:08x}.png"` — `%llx` is
   **unpadded**; do not zero-fill the 64-bit fields.
5. Join to Xbox: PS2 `name_key` → Xbox rows. Namespaces:
   `p8:{entry}:{name}` · `tset:{entry}:{chunk}:{child}:{name}` ·
   `nfl2k5.crib.scene.c{chunk:04d}.t{idx:03d}`.
6. **Disambiguation.** Emit a row only when the join is unique, or resolvable:
   - `p8:` and scene rows: unique by name → emit; otherwise defer.
   - `tset:` children: **TSET containers are unnamed on both discs**, so join at
     the set level with the shared `(id, chunk)` key (resolves 9,917 of 12,814
     PS2 TSETs; 512 of 1,826 ids disagree). Uniforms are identity-clean —
     0 of 7,274 cross team or era — so once the set is matched, the child is
     matched by index/name.
   - Everything unresolved goes to a sidecar `nfl2k5-xbox-map.unresolved.json`
     with the reason, never into the shipped manifest.
7. Provenance in the manifest header: `disc: {serial, boot_sha256,
   content_sha256}`, `emulator: {name: "PenguinScreen2", commit, hash_convention:
   "classic-tcc-bit14"}`, `method: "hop1/v5"`, `generated`, counts.

**Only rows where both hashes reproduce are shipped.** TEX0-only rows (473) are
excluded; they are not proven.

**XXH3-64 in pure Python.** The repo's tools are stdlib-only, so `tools/xxh3.py`
implements XXH3-64 (seed 0, secret default). It is a dev-time tool run once, so
speed is secondary; correctness is not. **Test oracle:** hop1's
`hop1_v5_results.jsonl.gz` carries 120,779 known-good hashes produced by
pcsx2-VR's own `xxhash.h` — every one must reproduce. Keep an optional
fast path: `import xxhash` if present, else pure Python, with a test asserting
both agree.

**Acceptance:**
- Reproduces hop1 exactly: 12,958 full-identity hits against the 15,104-identity
  pack, `bits` consistent on 100% of hits.
- `tools/nfl2k5_ps2_replacement_pack_audit.py --pack <community pack>` reports
  `xbox_mapping_ready: true` once the manifest is dropped beside it.
- Unresolved sidecar counts: fan-out by namespace, the 1,673 unexplained, the
  473 TEX0-only — each with a reason string.
- `--selftest` builds a synthetic PS2 image with two PSMT8 textures (one
  linear, one c32-mipped) and a PSMT4 texture, and round-trips hash → name.

**Sub-task, do first:** characterise the 1,673 unexplained — **1,635 sit in
`replacements/Team`**, i.e. uniforms. Determine which teams' kits are fully
mappable today. **Pick the M1 demo team from that set.** If Detroit away is
affected, choose another; the Xbox runtime proof for Detroit is convenience,
not necessity.

### WP2 — Ship the manifest  ·  ½ day  ·  after WP1

- Commit `mod_editor/data/nfl2k5-xbox-map.v1.json` (v1 schema, strict
  `{pcsx2_png, xbox_asset_id}` entries; provenance at top level so the audit
  tool's per-entry key check still passes).
- Commit the unresolved sidecar under `reports/gameplay_tuning/` as evidence.
- Run `packaging/check_2k5_mod_studio_release.py` on a staged release to confirm
  a hashes-and-names JSON passes the retail-free gate (it should — the registry
  already ships retail sha256s — but prove it, don't assume it).
- Add both files to the row's `evidence`.

### WP3 — Capability triage  ·  ½–1 day  ·  parallel with WP1

Desk work over the 32 `nfl2k5_xbox` rows: for each, classify PS2 reachability
as (a) PCSX2 texture replacement, (b) save editing, (c) needs on-disc writing
(Phase 2), (d) not applicable. Output: a table in `PS2_PORT_HANDOFF.md` and the
proposed `SURFACE_GAMES` staging order. **This decides what 5a's successor
rows are allowed to claim**; do it before WP6.

### WP4 — Export service + independent verifier  ·  2–3 days  ·  parallel with WP1

**`mod_editor/core/ps2_export_service.py`** (Qt-free):

```python
def plan_export(project, manifest) -> ExportPlan
    # for each EDITED uniform target in the open project:
    #   xbox_asset_id -> [pcsx2_png, ...] via manifest
    #   status: mapped | unmapped | ambiguous
def run_export(plan, out_dir) -> ExportReceipt
    # writes <out_dir>/textures/SLUS-20919/replacements/<name>.png
    # writes <out_dir>/nfl2k5-ps2-export-receipt.v1.json
```

Rules, each enforced and each tested:
- **Only edited targets are eligible.** The project model already knows which
  targets carry user PNGs. An unedited target is never written — emitting one
  would be emitting retail pixels (§6).
- One Xbox asset may map to several PCSX2 names (mip variants, set fan-out
  resolved to multiple identities). Write all of them; the receipt lists the
  fan-out.
- **The break is the hash, not the name.** **v1.7.4034** (PR #8015,
  2023-02-09) changed `HashTexture` to hash only the texels of the *clamped
  draw region* instead of the whole power-of-two texture. From that build on,
  including every 2.x release, a texture the game draws clamped has a different
  identity from the one computed offline here, and **no offline fix exists** —
  the clamp region is a runtime fact, not something a filename can be renamed
  into. PenguinScreen2's `ClassicTextureNames=true` restores whole-texture
  hashing (plus the flag and a crop at injection). Measured across the 60 rig
  dumps: 1,017 classic-only names covering **584 distinct identities**, all
  palettized 1024×1024 PSMT8H/PSMT8, and **none of them in this manifest** —
  every manifest identity observed is unclamped, so a stock 1.7.4034+ build
  looks up every name this exporter writes.
- **The export records who it is for.** `run_export(..., emulator_target=)`
  takes `penguinscreen2_classic`, `pcsx2_modern` or `pcsx2_legacy`. It changes
  no file — the pack is the same bytes under the same names for all three —
  and writes `emulator_target` plus an `instructions` block (`settings` and
  `lines`) into the receipt, so the verifier can hold a pack to the emulator it
  claims to be for.
- **Geometry.** PCSX2 accepts any replacement size and scales, but aspect
  matters. 2,521 shared names differ in geometry between platforms. Read the
  PS2 native `(TW, TH)` from the manifest's `bits` and, where the aspect
  differs from the Xbox edit, resample to the PS2 aspect (Pillow is a GUI
  dependency already). Record the resample in the receipt.
- Output directory must not already exist; refuse symlinks; write to a temp
  dir and rename in — same publish discipline the Team Kit export learned in
  beta-11 (Windows cannot rename a directory onto an existing one).
- Receipt: for every file — `path`, `sha256`, `xbox_asset_id`, `pcsx2_png`,
  `source_target`, `resampled_from`; plus skipped targets with reasons; plus the
  manifest's provenance block copied verbatim.

**`tools/nfl2k5_ps2_replacement_pack_verify.py`** — independent. It re-derives
from the folder, the receipt and the shipped manifest, importing none of the
service:
1. Every file in the folder is in the receipt; every receipt entry exists; no
   extras, no symlinks, no subdirectories beyond `textures/SLUS-20919/replacements/`.
2. Every filename matches the canonical PCSX2 shape (the widened regex) **and**
   appears in the manifest for the receipt's claimed `xbox_asset_id`.
3. Every PNG has a valid IHDR; recorded sha256 matches.
4. The receipt's provenance equals the manifest's.
5. The receipt names one of the three emulator targets, its `instructions`
   name every setting that target needs and none it does not have (a stock
   PCSX2 has no Classic Texture Names), and the steps still state the fact that
   makes them right.
6. **No receipt entry names a target the project marks unedited** — this needs
   the project file as a third input; when absent, the verifier says so and
   downgrades its verdict rather than passing silently.

It exits non-zero on any violation and names the offending path. Then
`nfl2k5_ps2_replacement_pack_audit.py` runs on the same folder and must report
`xbox_mapping_ready: true`.

**Tests** (`tests/mod_editor/test_ps2_export_service.py`,
`tests/mod_editor/test_nfl2k5_ps2_replacement_pack_verify.py`), all synthetic:
a fake project with two edited and one unedited uniform target, a synthetic
manifest with a 1:1 row, a 1:2 fan-out row and an unmapped id; assert the
unedited target is never written, the fan-out writes two files, the unmapped
target is skipped with a reason; mutate one output byte and assert the verifier
fails; add an extra file and assert it fails; forge a receipt entry for an
unedited target and assert it fails.

### WP5 — Export dialog + entry points  ·  1½–2 days  ·  after WP4

`mod_editor/gui/ps2_export_dialog_qt.py`, opened from *File → Export PS2
replacement pack…* in `studio_qt.py` and from `--ps2-export`. Shows the plan
(target, status, PCSX2 name count), the *Where will you use this pack?*
question below it, output chooser, Export, receipt view with that emulator's
instructions. Pool-thread the write. Mirror `ps2_disc_dialog_qt.py`.

#### Emulator target and its explanation

This is a contract, not a preference, and it is checked:

- The window offers **exactly three** targets — PenguinScreen2 with Classic
  Texture Names (recommended), PCSX2 1.7.4034+ including 2.x, PCSX2 before
  1.7.4034 — and **no default is selected**. Export stays disabled until one is
  chosen (`ps2_export_action_state(..., target_chosen=...)` takes it as a
  required argument, so no caller inherits a default by omission).
- **The files are identical for every answer.** The group's tooltip says so;
  the answer is recorded in the receipt and tailors the instructions.
- Each answer carries a **hover tooltip** and an **accessible description**
  with the same words, and the group carries the reason the question exists.
- The text is built from one constant, `EMULATOR_TARGET_CHOICES` in
  `mod_editor/gui/ps2_export_dialog_qt.py` (with `TARGET_GROUP_TOOLTIP`).
  Nothing else states it.
- **The required facts are the list in that module's
  `TARGET_EXPLANATION_REQUIRED_FACTS`,** not sentences repeated here. Each
  entry is a literal that must still appear in the hover text taken together,
  and it covers: the build that changed how a texture is identified and what it
  changed to; the build that dropped the TCC flag and why that never broke
  loading; the setting that restores the original hashing and the fork that has
  it; the builds each answer targets; the setting they all need; and **the
  measurement** — 584 clamped identities across the 60 dumps, none of them in
  this manifest, three stock builds loading the pack — so a tooltip cannot
  drift away from what was observed.
- `check_target_explanation()` builds the window offscreen and proves all of
  the above; `tools/validate_nfl2k5_ps2_replacement_pack.sh` (and the `.bat`)
  run it and print `NFL2K5_PS2_EXPORT_TARGET_EXPLANATION_PASS`, and the dialog
  tests run the same entry point. Where PyQt5 is absent the validator step
  prints `..._SKIPPED pyqt5=absent`: it inspects widgets, and a build with no
  GUI has no tooltips to check.

⚠ Touching `studio_qt.py` changes its sha256 and **refuses
`RC29_AUDIO_ANNOTATION_RUNTIME_PINS`**. Re-pin in the same commit, and audit
every `*_PINS` dict in both runtime checkers before pushing.

Tests: `tests/mod_editor/test_ps2_export_dialog_qt.py` under
`QT_QPA_PLATFORM=offscreen`, following the disc-dialog tests.

### WP6 — Registry row  ·  1 day  ·  after WP2, WP3, WP4, WP5

Row `nfl2k5ps2.uniforms.replacement_pack_export`:
- `surface: "uniforms"`, `classification: "offline-writer-proved"`,
  `backend.operation: "export"`, `gui.mode: "export"`,
  `backend.module: "mod_editor/core/ps2_export_service.py"`,
  `backend.command` containing that module token,
  `validation_command: "bash tools/validate_nfl2k5_ps2_replacement_pack.sh"`
  (+ `.bat`), `runtime.status: "not-tested"` until WP7.
- `SURFACE_GAMES["uniforms"] = GAMES` — **all three games, not a 2-tuple**: APF already has `uniforms` rows, so `("nfl2k5_ps2", "nfl2k5_xbox")` would drop it and fail the coverage-equality check (the triage's rule: every widening becomes `GAMES` except `crib_assets`).
- Pins, located by **content**: `71→72` at all 13 sites,
  `EXPECTED_COVERED_CAPABILITIES 66→67`, `EXPECTED_UNIQUE_VALIDATORS 53→54`, the
  two prose strings ("2 NFL 2K5 PS2 rows" becomes three), plus the
  `studio_qt.py` dict pin from WP5. Template: `93e1f6a`.
- Allowlist: the service, the dialog, the verifier, both validators, the
  manifest, `tools/xxh3.py`, `tools/nfl2k5_ps2_texture_map.py`. Each new
  `tools/*.py` must pass `test_shipped_tools_are_self_sufficient.py`.
- Changelog RC85 (RC84 is Slice 1) and the version-truth bump it forces
  (`__version__`, STATUS, getting-started, the test literals).
- No schema edit: `uniforms` is an existing surface.

**Gate before push:** `validate.sh` (with `--skip-file-checks`, as CI does),
`validate_all_mod_editor_capabilities.py` under the 3.11 venv, the pin audit,
and the full `tests/mod_editor` per-file comparison against baseline. Two audits
named the covered-capabilities pin as the likeliest CI breaker; treat WP6 as
the watched commit.

### WP7 — Runtime verification  ·  ½–1 day + rig time  ·  after WP6

This is the step that makes it M1.

**Resolved by read-only rig inspection (2026-09-04) — the witness is fully
automatable, no gameplay required.**

**✅ Route PROVEN by dry-run (2026-09-04, H-2 read clear twice beforehand).**
`~/classicdump-validate-fixed.sh ~/penguinscreen2-dev <2026-09-04 dump>` on
build `8226182a` ran in 12.7 s with the *community* pack and returned all four
harness verdicts PASS: V1 classic ⊇ modern (214 tcc-bit additions) · V2 no
region-suffixed names · **V3 classic-mode dump names match 49 community-pack
names against 1 in modern mode — `ClassicTextureNames=true` is mandatory,
measured** · **V4 pack engages under classic: frame sets differ.** The harness
neutralises both per-game inis (`SLUS-20919_42F9D5AF.ini`, `_C0272027.ini`)
and restores them on exit. Evidence: rig `~/classicdump-validate-20260904-220239/`.
The only input WP7 still lacks is our own pack. ⚠ Frame filenames contain
spaces — compare via the harness's verdicts or `find -print0`, never
`for f in $(ls …)`.

1. **The emulator pin is `penguinscreen2-dev @ 8226182aabe19640c6e676331678612f257356dd`**
   (branch `pcsx2-vr-classic-dump`, clean; `~/pcsx2-VR` on the rig symlinks to
   it). It is **not** the dev-box `f5f473479d` (248 commits apart). A second,
   dirty build `~/penguinscreen2-mb @ 91f53a51` also exists and was used by
   runs since 08-15 — do not pin to it; the commit is absent from the dev-box
   repo. The six filename format strings (`GSTextureReplacements.cpp:35-40`)
   are byte-identical across all three, so hashing and naming are unaffected.
   **Bit-14 names load** — `ReloadReplacementMap` (`:449-456`) always inserts the
   canonical stripped key and additionally the verbatim alias when
   `ClassicTextureNames=true`. ⚠ With classic **off**, a bit-14 name aliases onto
   the TCC=0 variant's key (ISS-042, `GSTextureCache.cpp:7110-7117`) → wrong
   art. **`ClassicTextureNames=true` is required**, and `SLUS-20919` is *not* in
   `s_classic_default_serials` (`VMManager.cpp:743-749`, only M09/NCAA09/M12) —
   set it explicitly.
2. **Rig safety.** Run the shared-headset live-session check as its own command
   and read the result before launching anything (hard rule H-2). Never chain a
   launch behind it. Dump replay uses the GPU; the rule applies.
3. **Stage the pack privately.**
   `~/.config/PenguinScreen2/textures/SLUS-20919/replacements` is a **symlink**
   to the 18,476-file community pack. Never write into it. Create a private dir,
   point the link at it for the run, restore the link afterwards.
4. **Witness by GS-dump replay, not gameplay.** Dump replay applies texture
   replacements: `GSDumpReplayer.cpp:155-171` → `VMManager.cpp:1128-1131` sets
   `s_disc_serial` from the dump → `GSTextureReplacements.cpp:274-276, 404-408`
   → `GSTextureCache.cpp:6984`; empirically confirmed on the rig (`frames-on`
   ≠ `frames-off`). **The dump embeds the serial** — no flag needed. Reuse the
   existing harness, passing the dump explicitly (its default glob picks the
   wrong snaps dir):
   ```
   ~/classicdump-validate-fixed.sh ~/penguinscreen2-dev \
     "$HOME/.config/PenguinScreen2/snaps/ESPN - NFL 2K5_SLUS-20919_<stamp>.gs.zst"
   ```
   Core command inside it: `"$GSRUNNER" -renderer Vulkan -surfaceless -loop 1
   -noshadercache -ini <ini> -dumpdir <frames> -logfile <log> -- <dump>`.
   ⚠ The per-game `SLUS-20919_42F9D5AF.ini` sets `LoadTextureReplacements=false`
   and **overrides `-ini`** — reuse the harness's sed + EXIT-trap neutralisation.
   Set **both** `LoadTextureReplacements=true` and `ClassicTextureNames=true`.
   Render the same dump with the pack linked (on) and unlinked (off); the
   edited kit must differ between the two frames and match the user's art.
   Choose a dump that shows the demo team WP1 selected (60 dumps inventoried in
   `wp7_prep.json`: the 2026-09-04 session is DET@DAL and DEN@SF).
5. Write `reports/runtime/nfl2k5_ps2_uniform_runtime.v1.json`: emulator
   commit, disc identity, pack receipt sha256, the PCSX2 names observed,
   screenshot sha256 + dimensions, observer, timestamp, verdict. **The
   screenshot itself stays out of git** (retail-derived pixels); the report is
   the evidence, as the existing xemu runtime-report rows do it.
6. Move the row to `runtime-proved` with the report in `runtime.evidence`.
   Re-pin and re-push (a second pin cycle — budget it).

If the texture does **not** appear: check the name against a live dump (enable
*Dump Textures*, replay the moment, compare the emitted filename to the dumped
one). The most likely culprits, in order: TCC bit convention on that build,
a c32-vs-linear layout miss for a mipped texture, or the asset being one of
the 1,673. Fix in WP1, not by hand-renaming files.

### WP8 — Land  ·  ½ day

Rebase onto current `upstream/main` (it ships daily), cherry-pick — never
merge — run the pin audit, push to `ps2-lane` or a `ps2-m1` branch, and let CI
run the two gates the dev box cannot. Then mark the PR ready.

## 5. Sequencing

```
day  1–3   WP1 manifest builder ──────────┐         WP3 triage (parallel, desk)
day  1–3   WP4 service + verifier ────────┤  (against a synthetic manifest)
day  3–4   WP2 ship manifest  ◄───────────┘
day  4–6   WP5 dialog  ◄── WP4
day  6–7   WP6 registry row  ◄── WP2, WP3, WP4, WP5     ← watched commit
day  7–8   WP7 runtime witness  ◄── WP6, rig
day  8     WP8 land
```

Critical path: **WP1 → WP2 → WP6 → WP7 → WP8.** WP4 and WP5 run alongside WP1
because the service needs only the manifest *schema*, not its contents.

**Total: 8½–12 implementation days.** The variance is almost entirely WP1's
disambiguation and WP7's first-try success.

## 6. Hard rules carried into M1

- **Never guess which emulator the pack is for.** The files are the same for
  all three, but the instructions are not, and a user told to turn on a setting
  their build does not have will hunt for it until they give up. The window
  asks, the receipt records the answer, and the verifier holds the pack to it.
- **Never claim a rename can undo the 1.7.4034 hash change.** The clamped draw
  region is a runtime fact. The only fix is PenguinScreen2's Classic Texture
  Names; the honest thing to say about stock PCSX2 is what was measured.
- **Never emit an unedited texture.** That is retail pixels leaving the disc.
  The service refuses, the verifier checks, and the tests prove both — and
  the guarantee starts *upstream* of the exporter: the canonical input is the
  `.2k5mod` archive, whose writer **refuses any edit whose RGBA equals the
  retail original** (`mod_editor/core/project_archive.py:381-386`), so every
  row the exporter ever sees is provably user-authored (WP4, measured).
- **Never commit a screenshot or a replacement PNG.** Reports and receipts only.
- **Only both-hash-proved rows ship.** TEX0-only and unresolved rows are
  evidence, not data.
- **Audit every `*_PINS` dict before every push.** `require()` stops at the
  first mismatch.
- **Stock disc only.** Hashes from the `NFL 2K27` mod match nothing on stock.
- **Pin the emulator build** and record it where the hashes live.

## 7. Risks

| risk | likelihood | mitigation |
|---|---|---|
| The 1,673 unexplained include the demo kit | real — 1,635 are in `Team` | WP1 sub-task picks a fully-mappable team first |
| `tset:` fan-out leaves uniform pieces unresolved | medium — 23% of TSETs | export only unique/resolved rows; report the rest honestly; the `(id, chunk)` join is design work, budgeted |
| TCC / hash convention differs on the pinned build | low | WP7 step 1 reads the loader source; dump-and-compare fallback |
| Aspect mismatch Xbox→PS2 distorts art | medium | resample to PS2 native aspect from `bits`; record it |
| A mipped texture hashes via the other layout | known | try both layouts; the 482 linear-only cases prove it |
| Upstream moves under WP6 | certain | rebase + pin audit immediately before push |
| Pure-Python XXH3 subtly wrong | low | 120,779-hash oracle from hop1 |
| PR not merged | external | the don't-fork call rests on #3/#5/#6 precedent; fallback is preview builds from the fork |

## 8. Out of scope for M1

Any surface other than uniforms · on-disc writing (Phase 2) · the ISO9660
writer (stays on `ps2-iso9660` until Phase 2) · audio · stadium geometry ·
text · playbooks · resolving the 1,673 · real-hardware PS2 · any change to
PenguinScreen2 itself.

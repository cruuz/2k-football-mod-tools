# Handoff: Beta 39

**Date:** 2026-08-13
**For:** the next session on APF playbook / uniform / field-art work
**Repo:** `https://github.com/cruuz/2k-football-mod-tools`
**Branch:** `cursor/ship-beta-38` (the branch name is stale; it now carries Beta 39)
**Main:** still Beta 36 (`981f596`). Do not treat main as current.

Beta 39 is a community-report release. Three reports were answered, one shipped
claim was withdrawn, and one alpha.70 test regression was fixed. The Layer B
static G12 pins that were uncommitted at Beta 38 ship here too.

---

## What changed and why

### 1. Save Project now saves Fine-tune Plays (Urianus)

**The bug.** The panel held `self._staged` / `_staged_heirs` / `_staged_moves`
and nothing else did. `apf2k8_splb_writer.PAYLOAD_SCHEMA` had been declared
since the panel shipped in Beta 32 and was referenced by nothing. Save Project
wrote a file that silently did not contain the playbook edits.

**The fix.** `splb_book_membership` is now a real modification kind with the
same shape as `play_assignment_route`:

| Layer | What it does |
|---|---|
| `apf2k8_splb_writer` | `change_metadata` / `change_from_mapping` / `encode_membership_payload` / `decode_membership_payload`. Canonical JSON, selectors only. |
| `session` | `apply_splb_membership_batch` (whole set at once), `_active_splb_changes`, `staged_splb_book`, `clear_splb_membership`. Compiles against the user's book before accepting. |
| `project` | payload name, validate, metadata, and load branches |
| `build` | `_compile_splb_membership` → one `build_book_patch` for the whole set |
| `facade` | `stage_splb_membership`, `staged_splb_changes`, `staged_splb_book` |
| panel | `_commit_to_project` on every stage; `_restore_from_project` on load |

The panel's local dicts are now a cache of the session set, not the only copy.
`staged_changes()` is a lossless projection of them, which is what makes the
round trip work.

Behaviour worth knowing: the writer compiles **one book at a time**, so the
session holds edits for one outer index. Switching books with work staged asks
the user (it used to discard silently). Reverting one modification re-compiles
the remainder rather than deferring the failure to build time.

### 2. Emptying a formation (Urianus) — the first G12 runtime witness

He emptied the formations without a TE in `O-ManBlock` on alpha.70 and the CPU
lined up personnel packages that book does not contain (00, 10, 01, 12, 11) and
one the game does not ship at all (02), running plays that are not in the book.
It happened whenever the director selected an emptied formation; untouched books
behaved normally. He separately confirmed plays are not bound to formations — an
offensive play added to a defensive book ran, defence readjusting.

**So an emptied record does not make the director skip that formation. It makes
the director call something the book never listed.**

Static count `0x84a8ac30` returning 0 and get-nth `0x84a8bd20` returning null
are unchanged and still true. They were never a proof of graceful handling, and
the Beta 38 copy read as though they were. That is the claim that was wrong, not
the addresses.

What ships:

- `EMPTY_FORMATION_WARNING` leads the confirmation dialog with the report.
- `compile_book` reports `records_emptied` and `populated_records_remaining`,
  and claims `empty_record_runtime_safe: False` plus
  `empty_record_reported_out_of_book_calls`.
- Emptying **every** populated record in a book raises in `compile_book`; the
  panel refuses the book's last populated formation with its own message.
- The G12 row in `docs/product/APF_GAMEPLAY_BUG_MAP.md` records the witness.

Nothing became proved. `wr3_te_package_sub_proved`,
`APF_3RD_AND_LONG_PLAY_CHOICE_PROVED`, `cpu_behaviour_runtime_proved`, and
`APF_PACKAGE_MAP_ROLE_LEGEND_PROVED` are all still False, and there is still no
WR3↔TE writer.

### 3. Fixed-allocation refusals (davidhbui)

`rebuilt shoulder IFF exceeds fixed allocation by 9231 bytes` named nothing, so
fixing one file and rebuilding produced `9292 → 9231` — a different slot
failing, indistinguishable from progress.

- `apf_texture_patch.AllocationOverflowError` + `allocation_overflow()` carry
  target, overflow, allocation, budget, retail usage. Shoulder, helmet, and
  pants transports raise it; each has a `target_label(row)`.
- `build.py` collects them across the whole edit set and reports every
  over-budget target at once.
- `apf_shoulder_color_transport.slot_capacity` / `inspect_capacity` and
  `uniform_targets.capacity_table` / `slot_capacity` / `capacity_summary`
  rank the 24 shoulder slots. The uniform detail panel shows the line.

**The model, because it is counter-intuitive:** budget = `entry.size − (IFF
header + DRAM block stored + footer)` = retail's own compressed payload + sector
slack, and the payload dominates. Sorting by slack ranks slots *backwards*.
Verified against the disc: outer 182 has the most slack of any shoulder slot and
ranks 18/24 for capacity; outer 184 (9th) and 198 (1st) accept the same PNG it
refuses. That is exactly what davidhbui measured, so the model is right.

Bands are terciles of the family (8/8/8), computed at call time — no hard-coded
byte thresholds, which would not survive a different texture size.

### 4. Field Art: outer 6 is not shared (davidhbui)

The category blurb and `APF_FIELD_ART_STOCK_NFL_WALL.md` both called outer 6 a
**shared** endzone layer. Decoded here: bespoke per-team artwork (wide-brimmed
hats, bandoliers, revolvers, a masked figure, a hitching rail), 2048×512 DXT1,
same l0/l1 split as the other 117. It is the pair whose writer was proved first,
nothing more. Withdrawn everywhere.

Endzone layers are **region masks**: pure R/G/B over black, alpha uniformly 255.
`ENDZONE_MASK_CONTRACT` states the authoring rules; the zero-alpha display rule
correctly does not fire here.

Discovery: `export_endzone_contact_sheets` renders all 118 packages into
labelled sheets (**Export endzone contact sheet…** in the Field Art header).
A name search cannot work — the nicknames appear zero times in `0A`, `0B`, `1A`,
`1B`, `default.xex` across ASCII/UTF-16BE/UTF-16LE; they live only in
`Roster.ROS`.

`mod_editor/data/apf2k8_endzone_labels.v1.json` carries 31 identifications —
davidhbui's list, every one re-confirmed here by decoding the retail volume
(12 nicknames + 19 alphabet letterforms). Unidentified packages stay indices.

Pass `outer_indices` when the inventory is loaded: it is the difference between
~30 s and ~190 s, because otherwise the function parses all 1,543 entries to
rediscover the 118.

### 5. Panel readability

`BOUNDARY` was 11,360 characters and `TAG_BOUNDARY` 11,252, word-wrapped between
the play list and the buttons. Split into `BOUNDARY` (1,488) + `RESEARCH_PINS`
(10,551) and `TAG_BOUNDARY` (1,873) + `TAG_RESEARCH_PINS` (10,532), with the
pins behind a **Research pins** button. Every literal still ships; the copy test
now concatenates all five constants, so the honesty rule is unchanged.
`PanelReadabilityTests` pins the inline strings at 3,000 characters.

### 6. alpha.70 test regression

`gui.py` read `self.facade.launcher.settings.title_update_path` unconditionally.
The launcher-settings `SimpleNamespace` doubles in three test files predated the
field, so **28 window tests were red in the shipped Beta 38**. The doubles now
carry `title_update_path=None`.

---

## Identity

| | Beta 38 | Beta 39 |
|---|---|---|
| Tag / updater identity | `beta-38` | `beta-39` |
| APF studio | `0.1.0-alpha.70` | `0.1.0-alpha.71` |
| 2K5 studio | RC62 | **unchanged RC62** |

Bumped in `mod_editor/apf_studio/__init__.py`, `mod_editor/core/update_check.py`,
`packaging/check_apf2k8_mod_studio_{release,runtime}.py`, `APF2K8-README.md`,
and the two version tests.

`.github/workflows/ci.yml` still hydrates from `beta-38` assets. **Update it
after the beta-39 release assets exist and their hashes are recorded**, exactly
as `07fbc09` did for Beta 38.

---

## Fail-closed (unchanged)

Do not set these True without an independent proof:

- `APF_PACKAGE_MAP_ROLE_LEGEND_PROVED` (full 0..10)
- `cpu_behaviour_runtime_proved`
- `wr3_te_package_sub_proved`
- `APF_3RD_AND_LONG_PLAY_CHOICE_PROVED`

Do not ship a WR3↔TE package-map writer. Do not treat situation word0, playcall
`+0x3C`, script `+0x10`/`+0x14`, or `+0x1F8` as down/ytg.

---

## What is proved (static XEX + disc) — unchanged from the Beta 38 handoff

**Package map → on-field role → roster TE/WR**

- APF package map is 11 bytes at MASTER formation **`+0x11`** (163/163 are a
  permutation of 0..10). 2K5's map is still `+0x0D`.
- Builder `0x84860020` / slot loop `0x848605b4`: slot index = map index.
- Assigner `0x8485e768`: `stb` map byte to on-field **`+0x34` and `+0x35`**.
- Role→roster byte table `0x84a9ae68` → **`0x820FC320`**, first 11 bytes
  `(0, 2, 1, 0, 3, 14, 12, 13, 9, 3, 7)`.
- **Index 8 → roster TE (9), index 9 → roster WR (3).**
- Ace stock map **`[0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7]`** — slot 2 = role 8 (TE),
  slot 3 = role 9 (WR3).
- Roles 1–7 still disagree with the OL / WR-X / WR-Z census.
- MASTER categories at `+0x44` are personnel packages; `0x8485bd38` extracts the
  SPLB trailer index.

**Eligibility AND does not distinguish WR3 vs TE, and the in-game builder does
not call it.** Fn `0x8485e7f8`: 0 `bl` callers, only absolute pointer is
`.pdata`. Live clone: 11-slot loop `0x848623e8`, `and` at `0x84862580`, caller
`0x84a0d110`. Role 8 mask `0xCD00`, role 9 `0xDD20`; both AND 5 Wide cell
`0x200` are 0.

**Down / ytg / picker.** Situation object `0x84F3F8F8`: down `+0x254`, LOS
`+0x258`, ytg `+0x25C`, play-type filter `+0x1F8`, playcall tab `+0x2BC`. Word0
is not down. Name table `0x820E57C8`: 3 = Third Down, 4 = Fourth Down. Picker
`0x8486ce88` gates on word0 and `+0x2BC`. `+0x1F8` is the "Offensive Play
calling" UI filter (`0x845FE7D4`).

**DRCT / leftover.** `dir_ingame.iff` MASTER outer 153: 1015 records, 1014 begin
`0B 00 01 00`; NFL outer 4: 1310/1310 start `0B`. Leftover size rule: `0x00`→1,
`0x0B`→5, `0x04`→5 (tag + IEEE754 LE f32), `0x03`→2, `0x05`–`0x09`→1. Consumes
APF 1015/1015 and NFL 1310/1310. Relocator `0x8466a818` / `0x8466a994` rewrites
only inline directory words. The XEX opcode switch that handles leftover type 4
from a DRCT record pointer is still not found.

False positives are pinned as `APF_FALSE_*` / `APF_DRCT_FALSE_*` in
`playbook_package_rule_spike.py`. Do not re-open them.

---

## Next hunts (still open)

1. Leftover walker from a **DRCT record pointer** (not cursor `0x84F1779C`, not
   expr VM `0x8466c890`, not `+32`/`lwz 0`/`lbz 0`, not serialize `0x84b094d0`).
2. Who packed-calls get_down `0x84ad92e0` / indexes `0x84EB0DE4`.
3. Who **writes** a D&D category index from packed get_down and a ytg source.
4. Packed call of setter `0x849d36d8` from that classifier.
5. `bctrl` of picker `0x8486ce88` not via `.pdata` and not the 8 `bl` UI callers.
6. **New, and now worth more than the above:** the consumer that turns a null
   get-nth into the out-of-book play Urianus saw. That is a runtime-observed
   path, so it is the first G12 thread with a witness at both ends.
7. Identify the remaining 87 endzone packages from the contact sheets and grow
   `apf2k8_endzone_labels.v1.json`.

---

## Evidence machines (do not rediscover)

- Decompressed PE: `/tmp/apf.pe` (52 MB), SHA-256
  `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`, image base
  `0x82000000`, file_offset = VA − base. Also `.codex-tmp/apf-sixth/apf-decoded.pe`.
- Helpers: `/tmp/apfrev/d.py` (`llvm-mc-18`), `/tmp/apfrev/scan.py`.
  **Gotcha:** llvm-mc desyncs on `0x00000000` nops — trust raw `w32` and
  `bl_targets_to`. `fn_start` walking back to `mflr` (`0x7D8802A6`) often groups
  tiny getters into the previous function.
- TEXT: `0x84630000` .. `+0x6d904c`. `bl_targets_to` over all TEXT is ~5–8 s per
  target. PPC `addi` sign-extends; ha16 of `0x844E8568` is `0x844F`.
  **`li rD, 5` encodes as `addi rD, 0, 5`** — leftover hunts must require
  RA ≠ 0.
- **Do not** brute-force the 52 MB PE byte-by-byte; use `.find()`.
- Disc: `/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)`.
  Symlink it in as `extracted/All-Pro Football 2K8 (USA)` to run the disc-gated
  tests (`extracted/` is gitignored). Doing so takes the `tests/mod_editor` run
  from ~7 min to ~30 min, so link it when you need real-disc verification and
  unlink it for the normal loop.
- Parse DRCT via `PYTHONPATH=tools` + `apf_outer` / `apf_inner` /
  `director_inventory.parse_apf_body`. Outer 153 body SHA-256
  `cd5bea8f217ce8fc2ca2ba5f8fc0666f325f12980646df10dc68b27c90aa5a49`.
- NFL xbe: `.../ESPN NFL 2K5 (USA)/default.xbe` (image base `0x10000`), map with
  `tools/xbe_info.py` `Xbe`. `.text` va `0x11000` raw `0x1000`.
- MASTER PLAY outer **180**. SPLB via `read_book(GAME, outer)`.
- Roster enum (17 codes): QB=0, K=1, P=2, **WR=3**, CB=4, FS=5, SS=6, **HB=7**,
  FB=8, **TE=9**, OLB=10, ILB=11, C=12, G=13, T=14, DT=15, DE=16.
- `tests/conftest.py` converts some `FileNotFoundError`s into skips when the
  haystack names a missing gitignored tree.

---

## Community reporters

- **Urianus Magnus Ursulinus** — G12 (TEs rarely on the field), the Save Project
  gap, and the empty-formation runtime witness. He is testing on both Xbox and
  PS3 and knows the 1.1-title-update difference between them.
- **davidhbui** — mask previews (Beta 36/37), the shoulder allocation budget
  study, and the endzone identification work. His reports arrive as reproducible
  measurements; when he says he measured something, he did.

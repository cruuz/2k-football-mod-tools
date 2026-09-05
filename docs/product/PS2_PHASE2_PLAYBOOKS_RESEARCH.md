# Phase 2 — playbooks / formations on PS2: feasibility research

**Question asked.** Can the Xbox studio's Create-a-Formation / Create-a-Play /
Play Designer / package-map feature (Betas 49–53) be ported to the PS2 release
of ESPN NFL 2K5 (`SLUS-20919`), and what does it cost?
[`PS2_PORT_HANDOFF.md`](PS2_PORT_HANDOFF.md):399 estimated **3–5 days**, and
:251 immediately disowned it — *"playbooks and audio unfounded — both are
unstarted reverse-engineering."*

**Verdict: PORT.** The premise behind the disclaimer is wrong. There is no PS2
playbook format to reverse-engineer: the PS2 and Xbox `PLAY` resources are the
**same format, the same size, the same content, and the same 37 content ids**,
and the executable-side constants the codec was derived from are present
verbatim in the PS2 MIPS ELF. The unmodified Xbox parser, validator, encoder
and writer all run on real PS2 bytes with **zero** code changes.

**Revised estimate: 4–6 days**, plus the ~2 d shared ISO9660-writer landing
that Phase 2 already budgets once for every on-disc surface. The driver is
**tool plumbing** — resource-locator retarget, capability/registry wiring, GUI
workspace — **not format research**. That is a different 4–6 days from the
original 3–5: same order of magnitude, entirely different content, and now
founded on measurement.

This is the best-prepared Phase-2 surface measured so far — better prepared
than stadiums, which :397 currently ranks first.

---

## Method and provenance

All numbers below were produced offline, read-only, from:

- the stock PS2 ISO (`SLUS-20919`, boot `SLUS_209.19`, boot sha256
  `e8c3ba9a…47d8aa`), read via `tools/ps2_iso9660.py` on this branch;
- `docs/research/inventories/inventory_{ps2,xbox}.tsv.gz`;
- the shipped Xbox code, executed unmodified: `mod_editor/core/`
  `nfl2k5_play_codec.py`, `nfl2k5_playbook_inspector.py`,
  `nfl2k5_formation_play_writer.py`.

No emulator, no rig, no hardware. Probe scripts live under the gitignored
`docs/research/` (`probe_extract_play.py`, `probe_parse_ps2_play.py`,
`probe_roundtrip.py`, `probe_capacity.py`, `probe_pool.py`,
`probe_writer.py`) and are throwaway. Nothing was written to the ISO.

⚠ **`docs/research/playbook_format.md` does not exist.** The registry row
`nfl2k5.scripts.director_playbook` cites it (and `director_format.md`) as
evidence; `.gitignore:27` is `research/`, so both citations are dangling. Cite
`docs/product/PLAY_*.md` and the code instead. This document does not depend on
either file.

---

## 1. Parity — do the 37 PS2 `PLAY` chunks match Xbox?

**Yes, exactly.** Result: **parses unchanged, zero field differences.**

### Container-level identity

| property | PS2 | Xbox | match |
|---|---|---|---|
| `PLAY` chunk count | 37 | 37 | ✅ |
| chunk name / name_key | `plb` / `PLB` (all 37) | `plb` / `PLB` (all 37) | ✅ |
| stored size (every chunk) | 78,736 = `0x13390` | 78,736 = `0x13390` | ✅ |
| on-disc resource span | 78,768 = `0x20 + 0x13390` | 78,768 | ✅ |
| compression | `lz=0` (all 37) | `cmp=0` (all 37) | ✅ |
| archive pack | pack 0 | pack 0 | ✅ |
| **32-bit content ids** | 37 ids | 37 ids | ✅ **identical lists, same order** |

The id lists are byte-identical as ordered sequences *and* as sets
(`diff` of both is empty). The first six on each platform are `0xf20774de`,
`0x49cd9f21`, `0x2c3def14`, `0xfd85de26`, `0x8fff1c67`, `0xcb0011a9`. The two
discs carry the same 37 playbooks, in the same order, at the same size.

`BODY_SIZE = 0x13390` in `nfl2k5_playbook_inspector.py:35` — written for
Xbox — is exactly the PS2 chunk size. The sub-table bases chain to fill it
with no slack:

```
0x0134 + 50×0xB4  = 0x245C   formations  → formation-aux base
0x245C + 50×0x50  = 0x33FC   aux         → play base
0x33FC + 270×0x60 = 0x993C   plays       → category base
0x993C + 26×0x10  = 0x9ADC   categories  → node base
0x9ADC … 0x10840             nodes (3,500 × 8)
0x10840 … 0x13390            UTF-16LE name pool
```

### Structural header (PS2 body, first 0x44 — structure only)

```
+0x00  00 00 00 00 00 00 00 00 00 00 00 00   (zero)
+0x0C  50 4C 41 59                            "PLAY"
+0x10  11 00 00 00   ED FF FF FF              version 0x11, -19
+0x20  70 00 6C 00 62 00 00 00                "plb" UTF-16LE
+0x30  <name ptr>  <formation count>  <play count>  <category count>
+0x40  <node count>
```

The inspector's two magic gates — `body[0x0C:0x10] == b"PLAY"` and
`body[0x20:0x28] == b"p\0l\0b\0\0\0"` (`nfl2k5_playbook_inspector.py:232`) —
hold on **37 / 37** PS2 books.

Both platforms are little-endian (Xbox x86, PS2 MIPS EE in LE mode), and the
codec uses `<` struct formats throughout, so no endian work arises.

### Running the Xbox parser and validator on PS2 bytes

`insp._parse_body()` is a strict validator: it checks magic, every count
against capacity, and requires the five self-relative pointers at `+0x44`,
`+0x48`, `+0x60`, `+0x64`, `+0x68` to resolve **exactly** to the five table
bases; then it partitions the node pool into chains and requires every chain to
start with clean flags and end on a terminal marker.

| measurement (all 37 PS2 books) | result |
|---|---|
| books parsed by the unmodified Xbox parser | **37 / 37**, 0 failures |
| formations | 1,533 |
| plays | **9,251** |
| categories | 835 |
| 8-byte nodes | 91,833 |
| node chains | 32,502 |
| plays accepted by the XBE-ported validator | **9,251 / 9,251**, 0 refusals |
| distinct node opcodes | 25, max `0x1b` — **all inside the 29-entry table**, 0 outside |
| formation slot stance codes | `{1, 2, 3}` — matches the retail comment |

**9,251 is the same total the Xbox corpus census reports** — `PLAY_EDITOR_-
FINDINGS.md`:40-70 and the codec docstring ("accepts all 9,251 stock plays"),
alongside 1,533 formations / 91,833 nodes / 101,761 slot refs. Every one of
those five figures reproduces on PS2. The two discs carry an identical
playbook corpus.

### Re-encoding PS2 bytes with the Xbox encoders

Parsing could in principle be lenient. Encoding cannot.

| round-trip | result |
|---|---|
| `FormationRecord.from_bytes → to_bytes` vs original | **1,533 / 1,533 byte-exact (100%)** |
| `build_descriptor()` vs the stored 32-bit descriptor | **101,761 / 101,761 byte-exact (100%)** |

The Xbox encoders reproduce PS2 formation records and every assignment
descriptor bit-for-bit.

### The executable-derived constants are in the PS2 ELF too

`nfl2k5_play_codec.py` is explicitly *"a port of the retail `default.xbe`
consumers … addresses are Xbox virtual addresses"*. The obvious objection to a
port is that those tables are Xbox-specific. They are not — every one of them
is present verbatim in `SLUS_209.19` (ELF, `e_machine = 0x0008` = MIPS):

| codec table | Xbox VA | PS2 ELF file offset | verified |
|---|---|---|---|
| `LANE_TABLE_CM` (16 × float32) | `0x520fe8` | `0x4e6bb0` | **16 / 16 floats match** |
| `OPCODE_FLAGS` (29 entries, `0x14` stride) | `0x521078` | `0x4e6c40` | **29 / 29 entries match** |
| `NAMED_SPOT_X_FT` (12 × int8) | `0xaabb30` | `0xa4eec0` | found |
| `NAMED_SPOT_Y_FT` (12 × int8) | `0xaabb3c` | `0xa4eed0` | found |

The lane→opcode spacing is **`0x90` on both platforms** (Xbox
`0x521078−0x520fe8`; PS2 `0x4e6c40−0x4e6bb0`). Same tables, same order, same
relative layout, different link base — i.e. the same source built for two
targets. The codec's XBE provenance is therefore *verified on PS2*, not merely
assumed to carry over.

**Answer to Q1: parses unchanged.** Not "parses with N differences" — zero.

---

## 2. What the Xbox feature actually writes

**Disc data only. One chunk kind — `PLAY`. Zero executable patches, zero
memory-card/save writes.** Nothing in this feature is `(d) not applicable`
on PS2.

### Evidence

- `nfl2k5_formation_play_writer.py` docstring: creations reuse *"empty slots
  inside the **fixed 0x13390 PLAY body**"*, which *"requires no string-pool
  growth and no node allocation, **keeps the body size exact**"*; the writer
  *"preserves every byte outside the newly inhabited formation/play records and
  the two count fields at 0x34/0x38."*
- Changelog Beta 49 (RC73), `docs/mod_editor/2k5_mod_studio_changelog.md`:761 —
  **"the XBE is never touched."** :736-738 — *"all inside the proved empty
  capacity of the fixed 0x13390 PLAY bodies… nothing relocates or grows."*
- Registry row `nfl2k5.scripts.director_playbook` (`surface: scripts_config`,
  `classification: offline-writer-proved`, `runtime.status: not-tested`):
  *"no allocation grows or relocates."* Backend is
  `nfl2k5_visual_mod_project.py build --source-xiso … --output-xiso …`.
- The build path **structurally forbids** executable writes —
  `tools/nfl2k5_visual_mod_project.py`:4630-4647 is a hard `require()` that any
  edit's span lie outside `default.xbe` and outside XDVDFS metadata.
- Grep for `xbe` / `memcard` / `SAVEGAME` / `.ros` across the entire play chain
  (`nfl2k5_formation_play_writer`, `_playbook_inspector`, `_playbook_pack`,
  `_play_library`, `_playbook_route_writer`, `create_play_wizard_qt`,
  `play_designer_qt`, `playbooks_panel_qt`) returns **only comments** — the
  codec's RE provenance note and the package-map spike's notes.

The XBE addresses in the codec (`FUN_0017fe60`, `0x521078`, `FUN_001a9840`)
are **read/RE-derived only**, ported *out of* the executable into Python and
never written back — and §1 shows their PS2 counterparts exist anyway.

### The exact write mask

Only these body ranges may change (`nfl2k5_formation_play_writer.py`:531-534,
586-587, 637, 670, 784-785, 792-793, 834); :848-851 hard-fails otherwise with
*"Formation/play compilation changed an unowned byte"*, followed by an
independent full reparse at :853:

- `+0x34` formation count, `+0x38` play count
- one destination formation record (`0xB4`) + its aux record (`0x50`)
- one destination play record (`0x60`)
- category record `+5..+16` (personnel swap)
- `+0x40` node count + the appended node region
- name-pool zero tail + pool count word at `0x1083C`
- 2 bytes of one `0x1FF` aux menu slot (the link)

### "Authorize and persist" (Beta 49) — both host-tool concepts

Neither is game-side. **Authorize** = the two provider kinds
(`play_formation_create`, `play_create`) were added to the provider allowlist
(`mod_editor/core/providers.py`:641) and to the capability-registry row;
before, Build refused projects staging them at the provider gate. **Persist** =
Save Project serialises them into the `.2k5mod` **JSON manifest** as
`playbook_creates` / `playbook_links` (`mod_editor/studio/project_archive.py`:
587, 589, 716, 888, 923) — a file on the modder's PC. Neither touches a game
save, a memory card, or an executable. Both port unchanged.

### Sub-feature breakdown

| sub-feature | shipped | writes | ports to PS2? |
|---|---|---|---|
| Create-a-Formation (clone + 11 slot records + mirror nibbles) | Beta 49 / 53 | `PLAY` body, in place | ✅ |
| Create-a-Play (clone + node chains + descriptors) | Beta 49 / 53 | `PLAY` body, in place | ✅ |
| Formation→play menu link (`0x1FF` slot) | Beta 49 | `PLAY` body, 2 bytes | ✅ |
| Custom names (name-pool zero tail) | Beta 49 | `PLAY` body, in place | ✅ (invariants verified, §4) |
| Package map (`+0x0D`, 11 bytes) | RC54 groundwork | `PLAY` body, in place | ✅ |
| Play Designer / Create-a-Play wizard GUI | Beta 53 | nothing (authoring UI) | ✅ |
| **Throw Distance & Arc** | Beta 53 | **patches `default.xbe`** | ❌ **not applicable** — see below |

⚠ **One trap.** The *Throw Distance & Arc* workspace shipped in the **same
release** as the Play Designer (changelog:635-650) and **does** patch
`default.xbe` (`tools/nfl2k5_throw_distance.py`:1-18). It is a separate
workspace under Sliders & Gameplay, **not** part of Create-a-Formation /
Create-a-Play. Do not let the shared Beta-53 tag conflate them into "the
playbook feature patches the executable" — it does not. Porting *that* surface
would need independent MIPS analysis of `SLUS_209.19` and is out of scope here.

Neighbouring rows in the surfaces named in the brief are all read-only XBE
research and are **not** this feature: `nfl2k5.cpu_ai_draft.logic`
(`read-only-mapped`, 17-float table at XBE VA `0x00589588`, *"executable
write-back remains disabled"*) and `nfl2k5.mode_state_routing.state_graph`
(`read-only-mapped`, *"route editing remains executable-patch work"*). Those
two **would** be blocked on PS2. The playbook row is not.

---

## 3. The unknown families — `SMCD`, `MMCD`, `CWDS`

All three are **animation and crowd assets, not play data**, and all three are
**identical across platforms**.

| family | PS2 | Xbox | unique names | what it is |
|---|---|---|---|---|
| `SMCD` | 4,559 | 4,559 | 2,333 (both) | **Animation clips** — `ANM_CELEBRATE_*` plus crowd/spectator motion (`ec…crowd…`, `es…player…`, `crowdhat…`) |
| `MMCD` | 639 | 639 | 639 (both) | **Formation-keyed animation clips** — `ANM_2K5_GUNLEFT_HB_HANDOFF_DR`, `ANM_POSTPLAY_*`, `ANM_SINGLEBACK*`, `ANM_SPLITLEFT/RIGHT_*`, `ANM_IRIGHT_*` |
| `CWDS` | 4,420 | 4,420 | **13** (both) | **Crowd models** — `p001`…`p012` + `seat`, replicated 340× (340 stadium instances × 13) |

Counts, unique-name counts and name sets match exactly on both discs. All are
uncompressed (`lz=0`). Header shape is the same 32-byte chunk header + a
UTF-16LE name at `+0x20` that `PLAY` uses; `CWDS` has only 6 distinct sizes in
a repeating 13-chunk group.

**Are they part of the play system?** No — with one caveat worth recording:

- `CWDS` is crowd geometry. Unrelated.
- `SMCD` is celebration and crowd animation. Unrelated.
- `MMCD` is **formation-adjacent but not formation data**: its names encode a
  formation family (GUNLEFT/GUNRIGHT/SINGLEBACK/SPLITLEFT/SPLITRIGHT/IRIGHT), a
  position (HB/FB), and a ball action (HANDOFF/PITCH). These are the *animation
  clips* played for handoffs and pitches out of a given formation family. The
  playbook `PLAY` chunk does not reference them by name — it references lanes,
  slots and opcodes — so **editing a play or formation never requires touching
  `MMCD`**. The caveat: an authored formation in a family the animation set
  never anticipated may fall back to a generic clip. That is a cosmetic
  fidelity question at runtime, identical on both platforms, and it does not
  gate the port.

Neither `SMCD`, `MMCD` nor `CWDS` needs to be understood to ship this feature.

---

## 4. Fixed allocation — can an edit be same-size in place?

**Yes.** This is the strongest result in the study, because it was tested by
running the real writer rather than by reading its docstring.

The unmodified Xbox `compile_formation_play_creations()` was invoked on all 37
PS2 books, each asked to create **one new formation** (with an authored
11-slot lineup and a custom name) **and one new play** (with a custom name):

| result | value |
|---|---|
| books the writer accepted | **29 / 37** |
| books refused **on capacity** | **8** — all with *"That would need 271 plays but the PLAY capacity is 270"* |
| books failed for any other reason | **0** |
| output size produced | **78,768 bytes on every book — identical to input** |
| changed bytes per book | **262 / 264 / 273** (min / mean / max) |
| outputs re-parsed clean by the inspector | 29 / 29 |

The 8 refusals are the capacity guard working correctly — they are exactly the
8 PS2 books already at the 270-play cap. **This matches the Xbox figure
precisely**: `docs/mod_editor/playbook_packs.md`:41-52 records *"Eight books are
already at the 270-play cap."*

So a formation or play edit is a **same-size, in-place change of ~264 bytes**
inside a fixed 78,768-byte span — comfortably inside the ISO writer's
fixed-allocation rule. Nothing grows, nothing relocates.

### PS2 spare-capacity budget

| resource | cap/book | PS2 spare (all 37 books) | books at cap |
|---|---|---|---|
| plays | 270 | 739 | **8** |
| formations | 50 | 317 | 0 |
| nodes | 3,500 | 37,667 | 0 |
| free `0x1FF` menu links | 36/formation | 39,123 | — |
| name-pool free tail | — | 105,846 bytes (~1,290 40-char names) | — |

(The Xbox doc's "180 spare play slots" counts only the 32 **team** books; PS2's
739 across **37** includes the 5 non-team books, which are far from full.)

### Custom-name invariants hold on PS2

The Stage-2 custom-name path requires two retail invariants
(`nfl2k5_formation_play_writer.py`:496-504). Both hold on **37 / 37** PS2 books:

- name-pool **zero tail** past the last live string — 37/37 (free tail min
  2,064 / mean 2,860 / max 9,528 bytes)
- **pool count word** at `0x1083C` equals `(pool_end − 0x10840) / 2` — 37/37

### The span-patch target resolves

Pack 0 of the PS2 disc is `/VC_20919/0.` at LBA 14,639 = byte offset
29,980,672. The first `PLAY` chunk (virtual `0x6ec2000`) therefore sits at
absolute ISO offset **146,118,656 (`0x8b59800`)**; reading there returns
fourcc `PLAY`, `stored = 78,736`, and the body's `PLAY`/`plb` magic. The last
sits at 148,994,048. The writer's `pack.name != "0"` guard (:1010-1011) is
satisfied — all 37 PS2 `PLAY` chunks are in pack 0.

The outer archive container is also shared: `tools/nfl_outer.py` (the Xbox
reader, already present on this branch) and the PS2 inventory tool
independently use the **same** constants — `ALIGNMENT 0x800`,
`PACK_SLOT_COUNT 36`, `HEADER_SIZE 0x0C + 36×4`, `ENTRY_SIZE 12`,
`CHUNK_HEADER_SIZE 0x20`, compression sentinel `0xFEEDBEEF`.

---

## 5. Verdict and revised estimate

### Verdict: **PORT**

Not "new research". The specific unknown the 3–5 d estimate was disowned for —
*"the PS2 data-table format"* (:399), *"unstarted reverse-engineering"* (:251)
— **does not exist**. It was measured, and the format is the Xbox format:
identical size, identical content ids, identical corpus, identical
executable-side tables, and the Xbox codec/validator/encoder/writer all run on
PS2 bytes unmodified and produce valid same-size output.

Not "blocked". Nothing in Create-a-Formation / Create-a-Play is executable-side.
The build path forbids executable writes by construction.

### What transfers with zero changes

`nfl2k5_play_codec.py`, `nfl2k5_playbook_inspector.py`,
`nfl2k5_formation_play_writer.py`, `nfl2k5_play_library.py`,
`nfl2k5_playbook_pack.py`, `nfl2k5_playbook_route_writer.py`,
`playbook_package_rule_spike.py`, and the Qt authoring surfaces
(`create_play_wizard_qt.py`, `play_designer_qt.py`, `playbooks_panel_qt.py`).
Also the project-persistence schema. That is the overwhelming majority of the
feature — and, notably, *no strides or offsets change*, contrary to what a
port would normally require.

### What actually has to be built

| work | driver | est. |
|---|---|---|
| Retarget the resource locator: `xiso_pack_path "vc_53450030/0"` → `/VC_20919/0`; `PACK0_RETAIL_SECTOR/SIZE/SHA256` → PS2 constants; adapt `Nfl2k5UniversalAssetIndex` → the PS2 disc inventory (exists, Slice 1) | plumbing | **1–1.5 d** |
| Capability + registry row (`nfl2k5ps2.scripts.director_playbook`), provider allowlist, project-archive round-trip for the PS2 game id | plumbing + the known **8-file atomic registry change** (handoff correction #1 — it also breaks the APF 2K8 release gate and forces a re-seal) | **1.5–2 d** |
| PS2 workspace GUI wiring, following the `ps2_save_dialog_qt.py` separate-workspace pattern (do **not** retrofit `GameId` into `studio/facade.py`) | plumbing | **1–1.5 d** |
| Tests + committed evidence (mirror the Xbox `PLAY_XISO_SLICE_PROOF` shape) | — | **0.5–1 d** |
| **Playbook lane total** | | **4–6 d** |
| *(shared, already budgeted once for all of Phase 2)* land `ps2_iso9660_writer.py` + `_verify.py` from branch `ps2-iso9660` (built, 56 tests) | :384-391 | *~2 d* |

**Estimate: 4–6 days**, driver **tool plumbing**, not format research. The
handoff's *"3–5 d"* was numerically close but rested on a false premise; this
figure rests on measurement. Note the ISO9660 writer is **not** chargeable to
playbooks — it is the shared prerequisite for stadiums, text and audio too.

### Consequence for Phase-2 ordering

:404 orders **stadiums → text → playbooks → audio**, putting stadiums first as
*"a port rather than research"*. On this evidence **playbooks are more
completely prepared than stadiums**: stadiums still need a bounded writer
ported to PS2 strides (:397), whereas playbooks need no format work at all —
the writer already runs on PS2 bytes and emits correct same-size output. Once
the shared ISO9660 writer lands, playbooks are a candidate to go **first**, as
the cheapest possible end-to-end proof that the PS2 disc-write path is real.

### Risks, honestly stated

1. **No runtime witness on either platform.** The Xbox registry row is
   `runtime.status: not-tested` with `runtime.evidence: []`; the xemu capture
   named in its `portme` has never been taken. A PS2 port inherits an
   offline-proved, never-witnessed feature. It can reach
   `offline-writer-proved` — the same bar the Xbox row holds — but not
   `runtime-proved`, and neither can Xbox today.
2. **Memory-card overlay is unverified.** `PLAY_SAVE_OWNERSHIP.md`:3,11 claims
   plays created by the *in-game* editor live in save containers that *overlay*
   the disc book at load. That claim is itself unproven (the harness never ran;
   the save file's name is unknown). If true on PS2, a user with an existing
   memory-card save could mask disc edits. Worth a note in the UI; not a
   blocker.
3. **The `PLAY_F{X,Y,W,T}_SIM_OVERLAY_PROOF.md` files are simulations**, not
   emulator proofs — `struct.pack` fixtures used to test the diff-overlay tool.
   Do not cite them as runtime evidence for either platform.
4. **Registry row count is an 8-file atomic change** that breaks the APF 2K8
   release gate. Already documented; budgeted above.

### The one experiment that would most change this answer

**Boot a PS2 ISO carrying one patched `PLAY` book in PCSX2 / PenguinScreen2 and
confirm the authored formation lines up in-game.**

Everything offline now points one way, and the remaining risk is entirely
runtime: whether `SLUS_209.19` *consumes* the edited book the way the XBE does.
§1 makes that very likely — the PS2 executable contains the same opcode table,
the same lane table and the same named-spot tables at the same relative
spacing — but "the data is identical and the tables are identical" is still one
inference short of "the game renders my formation."

It is also the cheapest decisive test available: one book, ~264 changed bytes,
one same-size span patch, one screenshot. And because the Xbox row has *never*
had this witness either, taking it on PS2 would make the **PS2** row the
better-evidenced of the two — and would retire the M1-class doubt for every
remaining on-disc Phase-2 surface at the same time.

---

# Implementation

The PORT verdict above was accepted and built. This section records what
shipped, the real-disc trial that exercised it, and what is still missing
before the registry row can claim a classification.

## What ported, and what is new

**Ported unchanged — zero edits.** `nfl2k5_play_codec.py`,
`nfl2k5_playbook_inspector.py` and `nfl2k5_formation_play_writer.py` are used
exactly as the Xbox lane ships them. No stride, offset, capacity or validator
constant was changed for PS2, because §1 showed none differs. The PS2 lane is
therefore a *caller* of the Xbox writer, not a fork of it — the single most
important property to preserve, since it means Xbox-side playbook fixes reach
PS2 for free.

**New, and only about *where the bytes live*:**

| file | role |
|---|---|
| `tools/nfl2k5_ps2_playbook_patch.py` | Locates the 37 `PLAY` resources, drives the Xbox writer, rebuilds pack 0 at identical length, and installs it with `ps2_iso9660_writer.replace_files` into a **new** image. Source ISO opened read-only. |
| `tools/nfl2k5_ps2_playbook_verify.py` | The independent half. Imports neither the patcher nor `ps2_iso9660` (the writer's own reader). Re-derives everything from the two images plus the report. |
| `tools/nfl2k5_ps2_playbook_target_catalog.py` | Emits `reports/gameplay_tuning/nfl2k5_ps2_playbook_catalog.v1.json` — per book: id, name, location, counts, capacity headroom. |
| `tools/validate_nfl2k5_ps2_playbook.{sh,bat}` | Offline validators; compile the tools and run the synthetic suite. No disc needed. |
| `tests/mod_editor/test_nfl2k5_ps2_playbook.py` | 10 tests on a synthetic ISO + synthetic pack + a synthetic `PLAY` body the shipped codec accepts. |

Two design points worth keeping:

- **Locating a book costs one 32-byte read per outer entry.** On both discs
  every playbook is *chunk 0 of its own outer entry* at offset 0, so the
  4,322-entry table resolves without a chunk walk — `list` over the retail ISO
  takes ~14 s, nearly all of it the codec parsing all 37 books.
- **The `PLAY` chunks are uncompressed** (`lz=0` on all 37; the outer header's
  `0xFEEDBEEF` sentinel is absent), so there is no decode on read and **no
  recompression on write**. The body is patched inside the pack and the
  surrounding bytes are untouched. A compressed family would have needed a
  re-encoder that fits the old size — this one does not.

Allocation is pinned twice: the compiled resource is asserted to be exactly
78,768 bytes, and the rebuilt pack is asserted to be exactly its original
1,073,741,824 bytes before `replace_files` — which independently refuses any
replacement that does not fit the extent it already owns — is even called.

## Real-disc trial

Run against the owner's own stock `SLUS-20919` ISO, read-only, output written
to gitignored scratch and **not committed**. Recorded in
`reports/gameplay_tuning/nfl2k5_ps2_playbook_trial.v1.json`.

Target: **ATL** (`0x49cd9f21`), outer entry 336, pack `/VC_20919/0.` at pack
offset 116,217,856 = **absolute ISO offset 146,198,528**. Chosen for headroom,
and because it is the same book the Xbox `PLAY_XISO_SLICE_PROOF.md` used.
Requested: one authored formation ("GUN TRIPS RT", 11 authored slot positions)
and one created play ("PS2 SMASH").

| measurement | value |
|---|---|
| book before → after | **39f / 254p / 2,438n → 40f / 255p / 2,438n** |
| new formation index / new play index | 39 / 254 |
| bytes changed inside the body | **258**, in 74 ranges |
| resource size in and out | 78,768 → **78,768** |
| source image size / output image size | 4,665,081,856 → **4,665,081,856** |
| writer declared ranges | 2 (the pack extent + its directory-record length) |

That the counts land on **39→40 formations and 254→255 plays** is the same
result the Xbox lane recorded for its ATL book — the strongest single
confirmation that the ported writer behaves identically on PS2 data.

**Both verifiers pass.** `nfl2k5_ps2_playbook_verify.py`:

```
ok  iso_writer_replacement_verified          declared_ranges=2
ok  diff_confined_to_declared_play_spans     74 differing ranges, 258 bytes, 1 declared span
ok  books_parse_and_validate                 1 book, 255 plays accepted by the retail validator
ok  undeclared_books_byte_identical          36 of 37 books untouched
PASS
```

The second line is the one that matters most: a **streaming diff of the entire
4.35 GB image** finds 258 differing bytes and every one of them lies inside the
single declared 78,768-byte playbook span. Nothing else on the disc moved. The
third line re-parses the patched book with the codec and puts all 255 plays —
the 254 stock ones and the new one — through the ported retail validator, which
accepts every one.

## Tests

10 tests, all passing, no game data:

- the synthetic body parses with the shipped inspector and **every play passes
  the retail validator** (the fixture has to be a real book or nothing else
  proves anything);
- targets are found with correct offsets;
- a formation and a play are added and the independent verifier returns PASS;
- the untouched book keeps every byte;
- **a byte flipped outside the declared span fails verification**;
- a book at the **270-play capacity is refused** ("would need 271 plays"), and
  no output image is created;
- **a compile returning the wrong body length is refused** before the output
  exists — a fixed-allocation violation cannot reach disk;
- an unknown book id and a bad recipe schema are refused;
- the catalog reports counts and headroom and carries no payload.

`tools/validate_nfl2k5_ps2_playbook.sh` prints
`NFL2K5_PS2_PLAYBOOK_VALIDATION_PASS`. Both `py_compile` under Python 3.9 and
`test_shipped_tools_are_self_sufficient` pass for all three new tools.

## Catalog

`reports/gameplay_tuning/nfl2k5_ps2_playbook_catalog.v1.json` — 37 books,
1,533 formations, 9,251 plays, 91,833 nodes; headroom **317 formations / 739
plays / 37,667 nodes**; **8 books at the 270-play cap**. Those eight are
`ARZ, BUF, CIN, HOU, JAX, NYJ, OAK, SD` — **exactly the eight
`docs/mod_editor/playbook_packs.md` names for Xbox**, independently re-derived
here from the PS2 disc. A recipe that *adds* a play cannot target them; one
that replaces can.

## What remains

**Before the row can claim `offline-writer-proved`** — none of it is format
work, and none of it is in this branch by instruction:

1. **The registry row itself** (`nfl2k5ps2.scripts.director_playbook`), which
   is the 8-file atomic change documented as handoff correction #1 — it also
   re-pins the APF 2K8 release gate. Added in a serialized integration commit.
2. **Capability + provider wiring** so Build accepts the two PS2 kinds, and
   project-archive round-tripping for the PS2 game id.
3. **GUI surfacing** in a separate PS2 workspace, following the
   `ps2_save_dialog_qt.py` pattern.

The *evidence* those steps need already exists: this branch's trial JSON is
what the row would cite.

**Before `runtime-proved`:** the witness named at the end of the research
section — boot the patched ISO in PCSX2 / PenguinScreen2 and see the authored
formation line up. That is a rig step, deliberately not done here. Note again
that the **Xbox** row has never had this witness either
(`runtime.status: not-tested`, `runtime.evidence: []`), so taking it on PS2
would make the PS2 row the better-evidenced of the two.

**Known limits of the current tool**, all deliberate and enforced rather than
silently worked around:

- one pack per run (every `PLAY` resource is in pack 0, so this has never
  bound);
- creations are clones of a donor plus authored slot positions / node chains —
  the Xbox writer's Stage-3 surface, no more;
- the group bits on a formation→play menu link stay unproved, so the writer
  only ever reuses a value the book already uses;
- the memory-card overlay risk from `PLAY_SAVE_OWNERSHIP.md` is untested on
  PS2 and would be a runtime finding, not a writer bug.

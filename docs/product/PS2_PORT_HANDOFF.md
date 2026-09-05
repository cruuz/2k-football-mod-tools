# PS2 disc-modding port: handoff

This document is for whoever picks up the work of extending **2K5 Mod
Studio** — currently a disc-level modding tool for ESPN NFL 2K5 on
**original Xbox** only — so it also edits the **PlayStation 2** release of
the same game (`SLUS-20919`, NTSC-U v1.01). It complements, and does not
duplicate, [`NFL2K5_PS2_SAVE_PIPELINE.md`](NFL2K5_PS2_SAVE_PIPELINE.md),
which covers the memory-card **save** editor already shipped. This doc is
about the **disc** (textures, audio, rosters-on-disc, everything the Xbox
side already edits).

Researched against commit `cc7bb92` on `origin/ps2-save-editor-gui`
(`origin/main` at `0e6ee66` / upstream `cruuz/2k-football-mod-tools` at
`3499a44`, five commits ahead of our origin/main: betas 54–58, none of
which touch PS2 disc work — see "Upstream status" below).

# IMPLEMENTATION PLAN — start here

Everything below this section is supporting evidence and history. This section
is the plan. It supersedes any earlier statement it contradicts.

## How the PS2 lane works

**It does not patch the ISO.** The Xbox lane edits a disc image and builds a
new modded XISO. The PS2 lane emits a **PCSX2 texture-replacement pack** — a
folder of PNGs named by GS hash — which PenguinScreen2 loads at draw time. The
user's ISO is never modified and stays hash-verifiable.

Consequences, stated plainly so nobody is surprised later:

| surface | Xbox lane | PS2 lane |
|---|---|---|
| textures | on disc | **emulator-only**, via replacement pack |
| rosters / names | on disc | via the shipped memory-card save editor |
| audio, geometry, text, menus, playbooks | on disc | **not covered** |
| real PS2 hardware | yes | **no** |

This is the right trade *because* the PS2 audience runs emulators — the Deluxe
community is on PCSX2 and Madden 12 Revamped is already a replacement-pack mod.
If real-hardware or non-texture PS2 modding is ever wanted, the shelved
ISO9660 writer (below) is the route back, with a GS codec behind it.

## Confirmed decisions

1. **Target: stock `SLUS-20919`.** GS hashes are content-derived, so a capture
   from the `NFL 2K27` mod matches nothing on stock.
2. **Emulator: PenguinScreen2** (`/mnt/c/GitHub/pcsx2-VR`). It owns the
   replacement subsystem, so hash stability is in-house. **Pin the build.**
3. **Do not hard-fork.** Upstream merges this fork's PS2 PRs same-day and the
   real gap from the base ref is **8 commits** (`cc7bb92..upstream/main`,
   measured 2026-09-04 after Beta 59), not the 573 measured from the fork's
   stale `main`. Re-measure before branching; upstream ships ~daily. Rebase onto `upstream/main` and keep PR-ing. Use the
   owner's fork approval for **release cadence only** — cut PS2 preview builds
   from the fork while staying rebased.
4. **ISO9660 splits.** Reader lands (it has a consumer). Writer + verifier
   (~2,560 lines) stay on branch `ps2-iso9660`, reserved for the EA suite.
   GS texture codec stays dropped. See TODO 5.
5. **The correspondence is a name join,** not pixel matching: 24,187 shared
   disc resource keys, 99.60% of 24,285 Xbox keys (verified exactly). The
   quantization hazard is dismissed — **but for the right reason**: PCSX2
   replacements are RGBA PNGs with no re-encode, so the source format is
   irrelevant. *Not* because "both platforms are palettized": 9,174 Xbox
   textures (6.5%) are not, and 9,293 shared rows pair Xbox P8 (256 colours)
   with PS2 PSMT4 (16 colours).

## First slice

**`nfl2k5ps2.textures.disc_inventory`** — surface `textures`, classification
**`read-only-mapped`**, GUI mode `view`.

> Open your `SLUS-20919` ISO: identity-check it against the registry's pinned
> hashes, browse ~550K named resources (140K textures with GS format and
> dimensions), and see each one's Xbox counterpart by name.

Chosen because it is the first time the product admits a PS2 disc at all, it
hands PCSX2 pack authors the **names** their hash dumps lack, it carries zero
risk to user data, it needs no writer and no GS decoder, and it is the
prerequisite for the mapping manifest. (PS2 *ratings* editing is not a
candidate — ROST ratings are `PORTME` even on Xbox.)

### The row is not complete until it carries all of this

`validate_registry.py:173-269` rejects a row missing any of these. The
classification is right — `read-only-mapped` matches
`classification_definitions`, and `:257-265` then **forces**
`backend.operation: "inspect"` and `gui.mode: "view"`.

- **`validation_command`** — mandatory for every non-deferred row (`:211`),
  must invoke `bash` or `python3` (`validate_all_mod_editor_capabilities.py:60`)
  and must resolve to a real file (`:213-216`).
  ⚠ **`tools/validate_nfl2k5_ps2_disc_inventory.sh` does not exist. Write it
  and allowlist it as part of commit 5a** — this was missing from the plan.
- **`backend.command`** must contain the exact `backend.module` token (`:206`).
- `portme` ≥ 1 entry · `input_constraints` ≥ 1 · `selectors.notes` ·
  `gui.reason` · `runtime.scope` + `runtime.status`
  (`"not-applicable"` is the idiomatic status for a read-only row).
- `evidence` paths must **exist as files**. Use the committed disc-inventory
  evidence JSON and the name-join TSV from commit 4 — do not cite anything
  under gitignored `docs/research/`.
- `registry.v1.json` must stay **canonically sorted JSON** (`:291`).

### Discovery — decided: a File-menu window, not a sidebar card

`mod_editor/core/product_catalog.py` filters on `game != NFL2K5`, so a
`nfl2k5_ps2` row never reaches the Xbox sidebar. An earlier version of this
plan said 5b must widen that filter. **It was not widened, on purpose:** the
catalog is built per game (`registry.for_game(GameId.NFL2K5)`), so the only
ways to admit the disc row are to admit every PS2 row — which drops the PS2
save *writer* into the Xbox "Sliders & Gameplay" section as an Editable card
and moves the "32 Xbox NFL 2K5 rows" pins — or to add a per-row opt-in field
the schema does not have. The shipped precedent is the PS2 save editor: a
separate window off the File menu plus its own `--ps2-save` entry point, and
the disc inventory follows it exactly (**File → PS2 Disc Inventory…**,
`--ps2-disc`). That menu entry is the discoverable surface, and it is the same
surface the save editor has had since Beta 53. Revisit only if PS2 grows enough
rows to deserve its own sidebar, which is a product decision, not a 5b task.

## Capability triage (WP3, 2026-09-04)

**This section decides what the PS2 lane is allowed to claim, row by row.** It
is the prerequisite of 5a's successor rows — it fixes the `SURFACE_GAMES`
staging that every future PS2 registry commit hard-codes — and it is the
evidence base for Phase 2. Nothing here changes the Xbox lane.

### Method and evidence base

Every disc fact below is **measured**, not assumed, from the two committed
inventories:

- `docs/research/inventories/inventory_ps2.tsv.gz` — 550,746 rows
- `docs/research/inventories/inventory_xbox.tsv.gz` — 569,990 rows

(columns `pack entry_index name name_key fourcc size width height format
extra`). ⚠ **Both live under gitignored `docs/research/` (`.gitignore:27`), so
no registry row may cite them as `evidence`.** The committed stand-in is the
name-join `.csv` and the evidence JSON that landed with commit 4
(`reports/gameplay_tuning/nfl2k5_ps2_disc_inventory.v1.json`); a Phase-2 row
that needs a count from the table below must re-derive it there. Code facts are
from reading the named files on this branch. Where a conclusion is an inference
rather than a reading, it says so inline.

**Recount of the name join, for confidence:** 25,846 distinct PS2 `name_key`s,
24,285 Xbox, **24,187 shared, 98 Xbox-only, 1,659 PS2-only** — reproduces the
"Confirmed decisions" figures exactly (a raw `sort -u` yields 24,188/25,847/
24,286 because both files carry one empty key). Of the 98 Xbox-only keys, **19
are filesystem entries, not resources** (`/DEFAULT.XBE`, `/UPDATE.XBE`,
`/VC_53450030/0..F`), leaving 79 real Xbox-only resources: 52 TXTR (all
`BUMP_*`, `DETAIL_NORMAL`, `SPECULARMAP`, `DIFFUSEMAP`, `CROWDBASE`,
`AN48..57`, `HN48..57` — Xbox pixel-shader maps with no GS analogue), 15 `MANU`
(`XB-1..XB-15`, the Xbox manual), 6 `AUDO` (crowd front/rear surround
variants), 2 `MRKS`, and one each of `XDSP`, `LAYT`/`MRKS` `ONLINE_SIGN_IN`,
`SCNE` `DETAIL_LAYER`, `SCNE_MATERIAL` `FOOTBALL_SHADER`, `SCNE_NODE`/
`SCNE_SHAPE` `LOD6`. **Nothing a registry row edits is Xbox-only.**

#### New measurement: cross-disc resource parity by fourcc

This is the load-bearing new evidence and it was not previously in this
document. For each fourcc, comparing container rows (`role=chunk`/`object`) by
`(name_key, size)` and `(name_key, decoded size)`:

| fourcc | PS2 | Xbox | same name multiset | same raw size | same decoded size |
|---|---|---|---|---|---|
| `PLAY` (playbooks) | 37 | 37 | yes | **37** | **37** |
| `DRCT` (director graphs) | 5 | 5 | yes | **5** | **5** |
| `ROST` (rosters) | 76 | 76 | yes | **76** | **76** |
| `Unif` (uniform colour words) | 634 | 634 | yes | **634** | **634** |
| `STRG` / `SITU` / `CRED` / `TRIV` (the proved text domain) | 2/1/1/1 | 2/1/1/1 | yes | **all** | **all** |
| `NAME` | 635 | 635 | yes | 635 | 635 |
| `LAYT` (menu layouts) | 85 | 86 | no (Xbox-only `ONLINE_SIGN_IN`) | 85 | 85 |
| `SMCD` / `CWDS` / `MMCD` / `SHAP` / `Fldd` / `Cuts` / `Hilt` | 4559/4420/639/1251/477/198/97 | identical | yes | all | all |
| `AUSB` (streaming-bank descriptors) | 17 | 17 | yes | **17** | **17** |
| `AUDO` (standalone sounds) | 844 | 850 | no | **136** | **24** |
| `SCNE` (`role=chunk`) | **4,139** | **4,616** | no | 312 | 2,402 |
| `TSET` | 12,814 | 10,774 | no | 332 | 3,402 |
| `TXTR` | 120,779 (120,772 `TXTR` + 7 `HITX`) | 140,766 | no | — | — |

Read that table as the triage's spine. **Every non-pixel, non-audio gameplay
container on the PS2 disc is byte-size-identical to its Xbox twin** — all 37
playbooks, all 5 director graphs, all 76 rosters, all 634 uniform colour
resources, the entire text domain. Only three families diverge, and they
diverge for the obvious reason: textures and scenes are GS-format, and audio is
a different ADPCM.

⚠ **Identical size is not identical content.** It is very strong evidence of a
shared record layout (same counts, same allocations, same little-endian
wrapper), and it is what makes "port" a defensible verdict below — but it is an
**inference**, and every Phase-2 row must confirm the layout against the real
PS2 bytes before it claims anything past `read-only-mapped`.

Two further measurements used below:

- **Audio is codec-divergent, wrapper-identical.** AUDO wrapper header sizes
  distribute identically (708/98/24/14 at `sys=`128/160/192/224 on PS2 vs
  708/98/30/14 on Xbox), and `menu-back_01` occupies the same 3,344 bytes on
  both discs — but carries 3,216 payload bytes on PS2 against 3,204 on Xbox.
  Same slot, different codec.
- **VC-LZ is shared.** 38,739 PS2 rows are `lz=1`, and the shipped
  `tools/nfl2k5_ps2_disc_inventory.py:220-279` already implements a VC-LZ
  prefix decoder plus a small encoder for its self-test. The compression layer
  is not a Phase-2 unknown.

### Route definitions

- **(a) PCSX2 texture replacement** — the asset resolves to a TXTR / TSET / P8
  target that PenguinScreen2 overlays at draw time.
- **(b) memory-card save** — served by the shipped PS2 save editor
  (`nfl2k5ps2.saves.roster_name_writer`, `tools/nfl2k5_ps2_save.py`).
- **(c) on-disc write — Phase 2** — anything PCSX2 cannot overlay: SCNE
  geometry, text/menu strings, playbook/formation data, `AUDO`/`AUSB` audio,
  on-disc roster and uniform data.
- **(d) not applicable** — no PS2 analogue. For executable rows the ground is
  `docs/README_full.md:1979-1980`: mapping needs "the exact PS2 ELF and
  controlled same-revision saves; **Xbox addresses are not PS2 offsets**." The
  PS2 boot ELF is `SLUS_209.19` (MIPS R5900); the Xbox target is
  `default.xbe` (x86). No address in any XBE-derived row transfers.

`status` vocabulary: `shipped` · `M1` · `stage N` (the post-M1 texture-lane
order in the next section) · `P2-port` · `P2-port (gated)` · `P2-research` ·
`P2-blocked` · `n/a`.

### The matrix — 32 `nfl2k5_xbox` rows + the 2 existing `nfl2k5_ps2` rows

| id | surface | Xbox class | what it edits | route | status | reason |
|---|---|---|---|---|---|---|
| `nfl2k5.audio.audo_wav` | audio | extract-only | browse/export 850 AUDO as WAV, 17 AUSB descriptors, 53,571 IMA ranges | (c) | P2-blocked | PS2 has 844 AUDO + the same 17 AUSB descriptors at identical sizes, but only 136/844 AUDO share a raw size and 24 a decoded size. Even *export* needs a PS2 decoder, and there is none: `grep -rilE "spu.?adpcm|\bVAGp?\b|sony adpcm"` over `tools/ mod_editor/ src/ include/` returns **0 files**. |
| `nfl2k5.audio.ausb_fixed_range_wav` | audio | offline-writer-proved | 53,570 fixed ranges in 16 external banks | (c) | P2-blocked | descriptors port for free (17/17 byte-size-identical; PS2 carries 17 non-video unstructured pack blobs to match). The codec does not: `mod_editor/core/nfl2k5_ausb_fixed_slots.py` hard-codes `IMA_INDEX_TABLE`, `IMA_STEP_TABLE`, `SAMPLE_RATE = 22_050`, `BLOCK_FRAMES = 64`, `CHANNEL_BLOCK_BYTES = 36` — Xbox IMA block geometry. |
| `nfl2k5.audio.fixed_audo_wav` | audio | offline-writer-proved | 849 non-Menu-Back standalone AUDO slots | (c) | P2-blocked | same; `mod_editor/core/nfl2k5_audo_fixed_slots.py` encodes strict PCM16 to Xbox IMA. |
| `nfl2k5.audio.menu_back_wav` | audio | offline-writer-proved | one 3,204-byte `menu-back_01` payload | (c) | P2-blocked | the PS2 twin exists (pack 0 / entry 3 / chunk 99, 3,344 bytes, 3,216 payload) — the single cleanest proof that the slot ports and the codec does not. |
| `nfl2k5.catching_drops.behavior` | catching_drops | unsafe/deferred | ROST attributes + untraced XBE catch/drop code | (d) | n/a | deferred even on Xbox; the unsolved half is `default.xbe` code. |
| `nfl2k5.colors.unif_words` | colors | offline-writer-proved | 2 packed colour words (facemask, HI_turtleneck) in each of 634 `Unif` | (c) | **P2-port** | all 634 `Unif` resources byte-size-identical on both discs. Not a texture, so PCSX2 cannot overlay it. Once the on-disc writer lands this is a same-allocation word poke — **the cheapest Phase-2 win in the registry, and the plan's Phase-2 table does not list it.** |
| `nfl2k5.cpu_ai_draft.logic` | cpu_ai_draft | read-only-mapped | 17-float table at XBE VA `0x00589588`, owner `0x0036EE70..0x0036F095` | (d) | n/a | pure XBE address space. |
| `nfl2k5.crib.assets` | crib_assets | offline-writer-proved | 498 Crib P8 TXTRs **+** 10 bounded meshes across 7 SCNEs | **(a) + (c)** | stage 6 / P2-research | `cribdata` is byte-identical in size (108,816) and id (`0xc61a9833`); 72 CRIB-named rows on each disc. The textures overlay; the 10 mesh edits are SCNE geometry and follow the models verdict. **The PS2 row must be scoped to textures and say so.** |
| `nfl2k5.cross_title_model_conversion.to_apf` | cross_title_model_conversion | read-only-mapped | NFL LE SCNE/SHAP → APF BE SCNE/IFF/H7A | (d) | n/a | both endpoints are non-PS2 (Xbox NFL, Xbox 360 APF). |
| `nfl2k5.franchise_restoration_cross_title.port` | franchise_restoration_cross_title | unsafe/deferred | cross-title executable/UI/ROST/schedule/playbook/save translation | (d) | n/a | deferred on Xbox; executable integration. |
| `nfl2k5.gameplay_tuning_sliders.rating_view` | gameplay_tuning_sliders | read-only-mapped | 21 XBE slider globals, FATX `Settings1`/`Franchise1`, 2,547 ROST players, 204 UI bindings | **(d) + (b)** | n/a / shipped | the slider globals are XBE VAs and the observed values come from a FATX Xbox-HDD image; neither exists on PS2. The PS2 counterpart of the save half is the memory-card lane the shipped row already owns. |
| `nfl2k5.logos.team_select_cards` | logos_cards | offline-writer-proved | 1,902 `unif_*`/`helm_*` raw fixed-slot P8 TXTR cards | **(a)** | stage 2 | `UNIF_*` = 637 distinct names on **both** discs, `HELM_*` = 634 on both. Standalone P8 TXTR, no TSET fan-out. |
| `nfl2k5.menus.layouts` | menus | read-only-mapped | LAYO/LAYT corpus, XBE main-menu ownership, 7 fixed UTF-16LE label slots | **(c) + (d)** | P2-port (inspect only) | 85 of 86 LAYT resources exist on PS2 and every shared one is byte-size-identical → the layout *inventory* ports. The label slots and menu ownership are XBE-resident → no PS2 analogue. Menu *art* is textures and reaches PS2 through route (a) instead. |
| `nfl2k5.mode_state_routing.state_graph` | mode_state_routing | read-only-mapped | XBE compiled state tables, transitions, constructors | (d) | n/a | pure XBE address space. |
| `nfl2k5.models.scne_gltf` | models_shap_scne | offline-writer-proved | glTF export of 4,616 SCNE + same-topology vertex import | (c) | **P2-research** | PS2 has **4,139** SCNE chunks, not 4,616, and only 312 share a raw size. Table strides are decoded (`tools/nfl2k5_ps2_disc_inventory.py:127-131`: texture `0x38`, material `0x60` name `+0x58`, node `0x60`, shape `0x70`, marker `0x40` — reconfirmed here from consecutive `rec=` deltas in the inventory), but **no code anywhere reads a PS2 shape's vertex payload**: `walk_scne` (`:515-560`) reads counts, relative pointers and names only, and `grep -niE "\bVIF\b|\bGIF\b|vertex|FLOAT3"` over that tool returns nothing. |
| `nfl2k5.models.scne_same_count_position` | models_shap_scne | offline-writer-proved | 75 catalog-pinned FLOAT3 targets, scene 2648, `vc_53450030/0` vol 9 | (c) | **P2-research** | `tools/nfl_stadium_catalog_position_patch.py` imports `nfl_outer`, `nfl_scne_inventory`, `nfl_txtr` and is bound to `reports/specs/nfl2k5_stadium_static_target_catalog.v1.json` — Xbox outer/chunk/scene ids in an Xbox volume-9 layout. PS2's archive is `/VC_20919/0..4` as one 4,635,080,704-byte virtual range. The catalog must be re-derived and the FLOAT3 lane re-proved. |
| `nfl2k5.models.scne_same_footprint_geometry` | models_shap_scne | runtime-proved | 4 FLOAT3 + 4 native QUADS ids, `s42nd.iff`, witnessed in xemu | (c) | **P2-research** | as above, plus the runtime witness is an xemu proof; a PS2 row would have to earn its own PenguinScreen2 witness. |
| `nfl2k5.models.scne_upper_deck_source_subset` | models_shap_scne | offline-writer-proved | shrink `upper_deck` to 8 or 4 synchronized records | (c) | **P2-research** | as above; a changed-count edit needs strictly more format knowledge than the same-count one. |
| `nfl2k5.players.disc_roster` | players_rosters | offline-writer-proved | outer-5 main ROST, 2,547 records: masked jersey, faceshield type, names | **(c)**, partly served by (b) | P2-port | **all 76 ROST resources byte-size-identical on both discs.** The shipped PS2 save writer already edits names in the save-side ROST arena (2,479 primary + 68 secondary), and the Xbox row's own caveat — "loaded saves may override the disc seed" — is precisely why the save route was the right first PS2 roster lane. The disc-side seed is the Phase-2 half. |
| `nfl2k5.portraits_faces.live_textures` | portraits_faces | offline-writer-proved | 1,872 `f####`/`h####`/`n####` DXT1 TXTR | **(a)** | stage 3 | `^F[0-9]{4}$` = 624 distinct names on **both** discs (h/n likewise). PS2 stores them PSMT8 rather than DXT1, which is irrelevant: the replacement is an RGBA PNG. |
| `nfl2k5.portraits_faces.roster_portraits` | portraits_faces | offline-writer-proved | 4,303 numeric PORTRAIT TXTR slots | **(a)** | stage 3 | `^[0-9]+$` = 4,313 distinct names on **both** discs. |
| `nfl2k5.saves.dashboard` | saves | read-only-mapped | FATX `E:/UDATA/53450030` containers, 21-field `Settings1`/`Franchise1` | (d) | n/a | FATX Xbox-HDD containers with a platform signature. PS2 saves are `BASLUS-20919*` memory-card directories with a recomputable CRC-32 — different substrate, already covered by the shipped PS2 row. |
| `nfl2k5ps2.saves.roster_name_writer` | saves | offline-writer-proved | `BASLUS-20919` memory-card ROST names, CRC-32 reseal | **(b)** | **shipped** | the reference (b) row. |
| `nfl2k5.schedules_franchise.database` | schedules_franchise | read-only-mapped | XBE fantasy-draft owner, cap validator, Super Bowl selector, 720,044-byte `Franchise1` | (d) | n/a | its own summary states "all mutation and PCSX2/PS2 patching remain disabled". The XBE halves have no PS2 addresses; a PS2 franchise-save lane would be new research, not a port of this row. |
| `nfl2k5.scorebug_presentation.inventory` | scorebug_presentation | offline-writer-proved | `score_buga` / `shield_espn` / `digital_font` P8 TXTR spans | **(a)** | stage 4 | all three names occur exactly once on the PS2 disc. |
| `nfl2k5.scorebug_presentation.score_buga_runtime` | scorebug_presentation | runtime-proved | one 64×64 P8 TXTR, xemu-witnessed | **(a)** | stage 4 | route is clean; a PS2 row starts at `offline-writer-proved` and needs its own PenguinScreen2 witness before it may claim `runtime-proved`. |
| `nfl2k5.scorebug_presentation.shield_espn_runtime` | scorebug_presentation | runtime-proved | one P8 TXTR, xemu-witnessed | **(a)** | stage 4 | same. |
| `nfl2k5.scripts.director_playbook` | scripts_config | offline-writer-proved | 5 DRCT graphs + 37 fixed-capacity PLAY books: route copy, bounded formation/play creation, play design | (c) | **P2-port (gated)** | **all 37 PLAY and all 5 DRCT resources are byte-size-identical across the discs, raw and decoded.** But `mod_editor/core/nfl2k5_play_codec.py` says in its own docstring that it is "a port of the retail `default.xbe` consumers … addresses are Xbox virtual addresses" — opcode table `0x521078`, formation reader `FUN_0017fe60`, validators `FUN_001a9840`/`001a91a0`/`001a96b0`/`001a8fb0`. The *format* almost certainly ports; the *semantics* were recovered from the XBE. **Gate: re-run `validate_play` over the PS2 PLAY bodies and require the same 9,251-play acceptance.** That is an offline check, not new reverse engineering. |
| `nfl2k5.stadiums.create_team_field_art` | stadiums_fields | offline-writer-proved | 126 `ct{logo}{weather}.iff` packages × 9 P8 textures | **(a)** | stage 5 | field art is drawn from textures PenguinScreen2 overlays. |
| `nfl2k5.stadiums.geometry` | stadiums_fields | offline-writer-proved | pinned Stadium SCNE glTF round-trip, same-count position import | (c) | **P2-research** | identical to the models rows: strides known, vertex payload undecoded. |
| `nfl2k5.textures.all_p8` | textures | offline-writer-proved | 11,395 standalone TXTR + 28,530 package-local P8 palettes + 4,080 A1R5G5B5 strips | **(a)** | M1 substrate | this is the lane the M1 manifest builds. PS2 side: 120,779 TXTR (118,531 PSMT8 + 2,248 PSMT4) and 12,814 TSETs. Caveat measured here: **2,702 of 11,504 shared TXTR names have no dimension in common** across platforms (consistent with the plan's 2,521 per-identity figure), so the exporter must resample to PS2 aspect. |
| `nfl2k5ps2.textures.disc_inventory` | textures | read-only-mapped | read-only walk of `/VC_20919`, 550,746 rows, Xbox name join | **(a)** substrate | **shipped** | the reference (a) row and the source of every disc measurement above. |
| `nfl2k5.uniforms.all_visual` | uniforms | offline-writer-proved | one composed XISO build: visual + text + roster + portrait + Crib + Stadium + equipment palettes + Menu Back + 849 AUDO slots | **(a) + (c)** | not portable as one row | this row is a *composition* over the others. Its PS2 successor **must not be a single row**: the texture classes belong to the M1 export lane; text, roster, Stadium and audio each wait for their own Phase-2 gate. Copying this row's scope onto PS2 would claim four unproved surfaces at once. |
| `nfl2k5.uniforms.detroit_away_runtime` | uniforms | runtime-proved | `09A0.IFF` chunk 1 `jersey00` + `jersey00_mud`, VC-LZ TSET span | **(a)** | **M1** | `JERSEY*` = 35 distinct names on PS2 vs 34 on Xbox; uniform TSET children are identity-clean (0 of 7,274 cross team or era). This is the row M1's successor mirrors. |

### Route counts

Of the **32 `nfl2k5_xbox` rows**: **9 pure (a)** · **0 pure (b)** · **11 pure
(c)** · **7 pure (d)** · **5 split** —

| row | split | why |
|---|---|---|
| `nfl2k5.crib.assets` | a + c | 498 textures overlay; 10 bounded meshes do not |
| `nfl2k5.uniforms.all_visual` | a + c | a composition over four other surfaces |
| `nfl2k5.players.disc_roster` | c, partly served by b | the disc ROST is (c); the save-side ROST is already shipped as (b) |
| `nfl2k5.menus.layouts` | c + d | 85 LAYT resources are (c); the XBE label slots and menu ownership are (d) |
| `nfl2k5.gameplay_tuning_sliders.rating_view` | b + d | XBE globals and FATX saves are (d); the PS2 equivalent is the shipped memory-card lane |

Plus the 2 existing `nfl2k5_ps2` rows: one route-(a) substrate
(`textures.disc_inventory`) and one route-(b) writer
(`saves.roster_name_writer`).

Counting split rows on every route they touch, the 34 rows touch route (a) 12
times, (b) 3, (c) 15, (d) 9 — 39 touches over 34 rows.

### `SURFACE_GAMES` staging order

`validate_registry.py:47-54` makes `SURFACE_GAMES` a **coverage requirement**,
not a permission list: `validate_data` (`:296-301`) demands that every
`(game, surface)` pair it names has at least one row. Widening a surface
without landing the row in the same commit fails CI. Today: `saves` = `GAMES`,
`textures` = `("nfl2k5_ps2", "nfl2k5_xbox")`, `crib_assets` =
`("nfl2k5_xbox",)`, everything else `_LEGACY_GAMES`.

**Texture-lane order (route (a)), after M1:**

| # | surface | tuple after | evidence needed first | honest starting class |
|---|---|---|---|---|
| 1 | `uniforms` (M1) | `GAMES` | the manifest rows for uniform TSET children; export service + independent verifier | `offline-writer-proved`, → `runtime-proved` at WP7 |
| 2 | `logos_cards` | `GAMES` | `UNIF_*`/`HELM_*` present in the shipped manifest with **both** hashes reproduced | `offline-writer-proved` |
| 3 | `portraits_faces` | `GAMES` | the numeric-slot and `f/h/n####` families in the manifest, **plus a policy for the `p8:` fan-out** (2,099 of the 7,739 fanned-out PNGs are all-`p8`); ship only unique rows | `offline-writer-proved` |
| 4 | `scorebug_presentation` | `GAMES` | three named targets in the manifest | `offline-writer-proved`; **best candidate for the second PenguinScreen2 witness** — smallest surface, and the Xbox side already has two `runtime-proved` rows to mirror |
| 5 | `stadiums_fields` | `GAMES` | the 126 `ct*` packages in the manifest. **Scope the PS2 row to field art only** — the geometry row on this surface is (c) | `offline-writer-proved` |
| 6 | `crib_assets` | `("nfl2k5_ps2", "nfl2k5_xbox")` | the `nfl2k5.crib.scene.c{chunk}.t{idx}` namespace join; 1,768 of the fan-out is all-scene, so this one needs the disambiguation work done | `offline-writer-proved` |

`crib_assets` is the only widening that does **not** become `GAMES` — it has no
APF row (verified: of the 21 surfaces, only `textures` and `crib_assets` lack
one).

**Phase-2 order (route (c)), which is *not* the plan's order:**

| # | surface | tuple after | evidence needed first | honest starting class |
|---|---|---|---|---|
| 7 | `colors` | `GAMES` | ISO9660 writer landed; confirm the two `Unif` colour-word offsets against PS2 bytes | `read-only-mapped` on day one (inspect all 634 sets), `offline-writer-proved` after the poke is proved |
| 8 | `players_rosters` | `GAMES` | confirm the disc ROST record layout against the PS2 disc copy (the save arena is a different container from the disc resource) | `read-only-mapped` first |
| 9 | `scripts_config` | `GAMES` | **re-run `validate_play` over the PS2 PLAY bodies**; require full acceptance before any claim | `read-only-mapped` (the inspector) immediately after that check; `offline-writer-proved` once the route writer is bound to the PS2 pack |
| 10 | `menus` | `GAMES` | nothing beyond the landed inventory — 85 LAYT already enumerated | `read-only-mapped` **only**; the writable half of the Xbox row is XBE-resident |
| 11 | `models_shap_scne` (+ the geometry half of `stadiums_fields`) | `GAMES` | a PS2 shape vertex-payload decoder — does not exist | `read-only-mapped` is available today (4,139 scenes and their tables are already enumerated); `offline-writer-proved` needs the new decoder |
| 12 | `audio` | `GAMES` | an SPU-ADPCM decoder, then an encoder | **do not stage until a decoder exists** — even `extract-only` is unreachable without one |

**Never staged (7 surfaces stay `_LEGACY_GAMES`):** `catching_drops`,
`cpu_ai_draft`, `cross_title_model_conversion`,
`franchise_restoration_cross_title`, `gameplay_tuning_sliders`,
`mode_state_routing`, `schedules_franchise`.

That accounts for all 21 surfaces: 2 already carry PS2, 12 are stageable, 7
never are.

### Phase 2 reachability, checked against the tooling that exists today

**Stadiums / geometry — verdict: NEW RESEARCH, not a port.**
Ports cleanly: the SCNE *table* layer (strides in
`tools/nfl2k5_ps2_disc_inventory.py:127-131`, reconfirmed from the inventory's
`rec=` deltas), VC-LZ (`:220-279`), and the bounded-edit discipline itself.
Xbox-specific: `tools/nfl_stadium_catalog_position_patch.py` assumes the
`vc_53450030` volume-9 layout, `nfl_outer`'s XISO archive model, and a pinned
75-target catalog of Xbox outer/chunk/scene ids; `nfl_stadium_group36_geometry_patch.py`
additionally assumes an XDVDFS transport span and an xemu witness.
**Specific unknown: the byte layout of a PS2 shape's vertex/position payload.**
`walk_scne` reads counts, relative pointers and names and stops; nothing in the
repo touches PS2 vertex data. The inventory also shows PS2 has 4,139 SCNE to
Xbox's 4,616 with only 312 same-size, so the scene graph itself is
re-authored per platform. **The plan's "port rather than research" framing for
stadiums is the one claim my evidence contradicts** — see below.

**Text / menus — verdict: PORT (the strongest Phase-2 candidate).**
Ports: `mod_editor/core/nfl2k5_safe_text_banks.py` (STRG pool allocations, the
four display-text pointers in each of 25 SITU records, CRED's two pointers per
event, TRIV's seven) and `tools/string_table_inventory.py`, whose docstring
already notes that "NFL 2K5 stores a little-endian body behind the common
resource wrapper" — and PS2 is little-endian too, so the endian split that
separates NFL from APF does not reappear here. All four container types exist
on PS2 at identical sizes; `NAME` (635) and `LAYT` (85 of 86) likewise.
Xbox-specific: the seven direct UTF-16LE label slots in `nfl2k5.menus.layouts`
live in the XBE, and the archive plumbing (`nfl_outer`, `nfl_scene_probe`)
assumes the XISO. **Specific unknown: that PS2 strings are also UTF-16LE with
the same pointer encoding.** Identical allocation sizes make this very likely
but it is an inference, not a reading — confirm before claiming
`offline-writer-proved`. The plan's "716 disc banks ≠ one ROST arena" caution
stands; the shipped surface is 20,074 editable of 23,346 (grep `20,074` in
`docs/mod_editor/2k5_mod_studio_getting_started.md` — line numbers drift daily).

**Playbooks / formations — verdict: PORT, gated on one offline check.**
Ports: `nfl2k5_playbook_inspector.py`, `nfl2k5_playbook_route_writer.py`,
`nfl2k5_formation_play_writer.py`, `nfl2k5_playbook_pack.py`,
`nfl2k5_seven_on_seven_book.py`, `tools/nfl2k5_playbook_position_recode.py`,
and the GUI (`play_designer_qt.py`, `create_play_wizard_qt.py`) — all of which
address a **fixed `0x13390` PLAY body** that is byte-size-identical on the PS2
disc across all 37 books, with all 5 DRCT graphs likewise.
Xbox-specific: `mod_editor/core/nfl2k5_play_codec.py` in full. Its docstring is
explicit — "a port of the retail `default.xbe` consumers … addresses are Xbox
virtual addresses" — covering the 29-entry opcode table at `0x521078`, the
formation reader `FUN_0017fe60`, and four validator functions.
**Specific unknown: whether the PS2 build's opcode table and validator agree
with the XBE-derived port.** The check is cheap and offline: run
`validate_play` over the PS2 disc's own PLAY bodies and require the same
acceptance the Xbox corpus gets. If it passes, this surface is a port. If it
does not, it becomes MIPS reverse engineering of `SLUS_209.19` and should be
re-ranked below text. **Do this check before promising the surface.**

**Audio — verdict: BLOCKED.**
Ports: the descriptor/ownership layer only — `nfl2k5_audio_catalog.py` and the
slot-geometry half of `nfl2k5_ausb_fixed_slots.py` land for free, since all 17
AUSB descriptors are byte-size-identical and the PS2 disc carries 17 non-video
unstructured pack blobs to hold them.
Xbox-specific: every codec constant, and the whole of `nfl2k5_audo_fixed_slots.py`'s
PCM16 → Xbox IMA encoder.
**Specific unknown: the PS2 payload codec itself.** The repo has no SPU-ADPCM
or VAG code of any kind (0 files match), and the AUDO evidence says the payload
differs even where the slot does not (`menu-back_01`: same 3,344-byte
allocation, 3,216 vs 3,204 payload bytes; only 24 of 844 AUDO share a decoded
size). pcsx2-VR's `SPU2` tree is a *reference decoder in another repo*, not an
in-repo dependency. **Audio stays last, and stays unbudgeted.**

### What the next registry commits need

Every widening below is a `SURFACE_GAMES` edit in
`mod_editor/capabilities/validate_registry.py` **landed in the same commit as
the row it admits**, plus the standing 13-count-pin cycle (`71→72` for M1's
row, and one further increment per PS2 row after it) and the
`EXPECTED_COVERED_CAPABILITIES` / `EXPECTED_UNIQUE_VALIDATORS` pins.

| surface | from | to | schema edit? |
|---|---|---|---|
| `uniforms` | `_LEGACY_GAMES` | `GAMES` | no |
| `logos_cards` | `_LEGACY_GAMES` | `GAMES` | no |
| `portraits_faces` | `_LEGACY_GAMES` | `GAMES` | no |
| `scorebug_presentation` | `_LEGACY_GAMES` | `GAMES` | no |
| `stadiums_fields` | `_LEGACY_GAMES` | `GAMES` | no |
| `crib_assets` | `("nfl2k5_xbox",)` | `("nfl2k5_ps2", "nfl2k5_xbox")` | no |
| `colors` · `players_rosters` · `scripts_config` · `menus` · `models_shap_scne` · `audio` | `_LEGACY_GAMES` | `GAMES` | no |

**No schema edit is required for any of these.** All 21 surfaces and the
`nfl2k5_ps2` game id are already in `mod_editor/capabilities/registry.schema.json`'s
enums (verified). Only a genuinely *new* surface would need the schema, and
that carries the 6-edit version-truth cost 5a paid.

Prefer `SURFACE_GAMES["<surface>"] = GAMES` for all but `crib_assets`, matching
the existing `saves` line, and keep the tuple alphabetically sorted as `GAMES`
already is.

### Where this contradicts the plan

1. **Stadiums are not "a port".** `Phase 2 → Reachability` calls stadiums the
   best-prepared surface at 4–6 d because "the PS2 SCNE layout fell out of the
   inventory work for free". The *table* layout did; the **vertex payload did
   not**, and that is the thing the writer edits. Re-rank stadiums below text
   and playbooks, and re-budget it as research.
2. **Text and playbooks are better-prepared than stadiums.** Both have their
   entire container corpus byte-size-identical on PS2 (STRG/SITU/CRED/TRIV; 37
   PLAY + 5 DRCT). Suggested revised order: **text → playbooks → colors →
   rosters → stadiums → audio.**
3. **`colors` and `players_rosters` are missing from the Phase-2 table
   entirely**, and both are cheaper than everything currently listed:
   634 identical `Unif` resources and 76 identical `ROST` resources.
4. **Audio's "844 AUDO + 17 AUSB on the PS2 disc" is right, and its estimate is
   the honest one** — but note the descriptors port for free, so the 8–12 d is
   codec work alone, not container work.
5. **The "not covered" row in "How the PS2 lane works"** ("audio, geometry,
   text, menus, playbooks") should gain a footnote: the *containers* for text,
   playbooks, rosters and uniform colours are all present and identically
   allocated on the PS2 disc. What is missing is the write path, not the data.

## Landing order — 5 commits

Branch from **`upstream/main`**, not `cc7bb92`. Commit the two `/tmp` worktrees
to their branches first — **nothing is currently committed.**

| # | commit | re-seal? |
|---|---|---|
| 1 | `docs/product/PS2_PORT_HANDOFF.md` (this file) | no — unshipped |
| 2 | Audit-tool fixes + 23 tests (`nfl2k5_ps2_replacement_pack_audit.py`) | no — unallowlisted |
| 3 | `tools/ps2_iso9660.py` reader + the synthetic suite. **Fix `SLUS-209.19` → `SLUS-20919`** in `boot_identity()` or it will not join against `SERIAL`. **Move the test file to `tests/mod_editor/`** or CI never runs it. Swap the Madden disc tests for a skip-guarded SLUS-20919 identity test. ✅ **Landed** (`a1ab225` on `ps2-lane`): `_serial_of` normalises the 8.3 name; the suite is 54 tests (50 synthetic + 4 gated on `NFL2K5_PS2_ISO`), verified against the retail image | no — unshipped until #5 |
| 4 | `tools/nfl2k5_ps2_disc_inventory.py` (productized `ps2_vc_inventory.py`) + synthetic selftest + evidence JSON at `reports/gameplay_tuning/nfl2k5_ps2_disc_inventory.v1.json` + a **~1.5 MB name-join as `.csv`** (not `.tsv` — see landing mechanics), not the 70 MB dumps. ✅ **Landed** (`38f0376`): reproduces the research run row for row (550,746 rows); `ps2_iso9660.build_synthetic_iso` made public for the selftest; the validator `.sh`/`.bat` pair landed here rather than in 5a | no |
| 5a | Registry row (complete per the field list above) + `SURFACE_GAMES["textures"] = ("nfl2k5_ps2", "nfl2k5_xbox")` + the **13 count pins** 70→71 + allowlist entries + closure list (the `product_modules` tuple in `check_2k5_mod_studio_runtime.py`, next to the two PS2 save tools — locate by content) + changelog **RC84** (RC83 is taken — Beta 59 shipped 2026-09-04) + the **6-edit** schema fix. ⚠ **"Changelog RC84" is a version-truth bump, not one heading:** `test_no_capability_is_invisible.py` requires `__version__` == the newest changelog heading == the `STATUS.md` and getting-started headers, and `test_beta45_honesty_freeze.py` / `test_phase1_packaging.py` pin the literal, so it is 6 more edits (`mod_editor/__init__.py` → `1.0.0rc84`, `STATUS.md` ×2, getting-started ×1, three test literals) | **2K5 re-seal**; APF literal only |
| 5b | `ps2_disc_service.py` (Qt-free) + `ps2_disc_dialog_qt.py` + `studio_qt.py` menu entry + `--ps2-disc`, `repin.py --apply`. ✅ **Landed** (see the `ps2-lane` log): the service keeps the rows in a private SQLite sidecar and answers filtered counts/windows; the dialog's model fetches 256-row pages on demand (the virtualized model the effort section asked for); the walk runs on a pool thread with progress; `repin.py` had nothing to re-pin. **The `product_catalog.py` game filter was deliberately not widened** — see "Discovery" below | same release |

**The 13 count-pin sites (9 files).** ⚠ **Do not trust any line number in
this document for these sites.** Two audits hours apart on 2026-09-04 reported
*different* drifted positions on `upstream/main` (e.g. `STATUS.md` 2737 vs
2755; `check_2k5` 1793 vs 1798) because upstream ships daily. **Re-locate every
site by content** — grep for the literal `70`, `EXPECTED_COVERED_CAPABILITIES`,
`EXPECTED_UNIQUE_VALIDATORS`, and the prose strings named below.

**Two are prose, not numbers, and are asserted by tests:** `STATUS.md` says
"1 NFL 2K5 PS2 save-import row" and `getting_started.md` says "separate PS2
save-import bridge" — `test_phase1_packaging.py:69` asserts that text. A second
PS2 row invalidates both sentences.

- `packaging/check_2k5_mod_studio_runtime.py` — two sites (the assertion and
  the summary string)
- `packaging/check_apf2k8_mod_studio_runtime.py:1185`
- `docs/mod_editor/2k5_mod_studio_getting_started.md`
- `STATUS.md`
- `tests/mod_editor/test_apf_studio_installer.py:360`
- `tests/mod_editor/test_phase1_packaging.py:69` and `:454`
- `tools/validate_all_mod_editor_capabilities.py:61`, **plus `:62`
  `EXPECTED_COVERED_CAPABILITIES` 65→66 and `:64` `EXPECTED_UNIQUE_VALIDATORS`
  52→53** (enforced at `:1503`/`:1511` and by
  `test_validate_all_capabilities.py:157,159`) — the new row brings a new
  validator, so both counters move
- `APF2K8-README.md:594` and `docs/mod_editor/APF2K8_STATUS.md:750`

Must move in the same commit because the APF gate runs in CI. Re-pinning is
routine — 5 precedents (`aa4b92e`, `ed575f0`, `af8ae63`, `66f26b5`, `93e1f6a`).
**Use `93e1f6a` (67→70, 13 sites) as the template.** ⚠ Do **not** copy
`af8ae63`: it bumped `EXPECTED_CAPABILITIES` but **left
`EXPECTED_COVERED_CAPABILITIES` at 60** — following it verbatim reproduces the
exact CI failure two independent audits flagged as the most likely breaker of
the first PS2 commit.

**⚠ 5a re-seals APF too — not "literal only".** `registry.v1.json`,
`registry.schema.json`, `validate_registry.py` and `check_apf2k8_…runtime.py`
are all in `packaging/apf2k8-release-allowlist.txt`. Any edit to them changes
the APF archive bytes. Plan for **both** products to re-seal on 5a.

**The schema fix is 6 edits, not one** (an earlier count said 5 — it is two
per pair). `registry.schema.json`: `games.minItems` **and** `maxItems` 2→3;
`surfaces.minItems` **and** `maxItems` 20→21; and `textures` added to **both**
surface enums — the row's own `surface: "textures"` is **illegal under the
published schema today**. (Currently inert: no JSON Schema
is ever applied, only the `$id` is checked at `validate_registry.py:326`. Fix
it anyway; a stock validator would reject the file.)

### Landing mechanics that will bite

- **Rebase or cherry-pick onto `upstream/main` — never `git merge`.** A
  full-branch merge conflicts in `check_2k5_mod_studio_runtime.py` because of
  pre-squash history. All three existing commits **cherry-pick cleanly** onto
  `7f1f3b3` (Beta 59). Verified: zero test regressions after applying all three
  (Python 3.9.25 baseline 21 pass / 264 fail — 201 `datetime.UTC`, 56 missing
  PyQt5, 7 other — identical set with our changes).
- **⚠ CI never runs `tests/test_ps2_iso9660.py`.** `ci.yml:217` globs only
  `tests/mod_editor/test_*.py`. **Move it to `tests/mod_editor/` in commit 3**
  or the 56 tests (27 reader + 23 writer/verifier + 6 disc-gated) silently
  never execute.
- **Ship evidence as `.csv` or `.txt`, not `.tsv`.** `.tsv` is not in the
  release checker's `ALLOWED_SUFFIXES` (`.csv` is); a shipped `.tsv` raises in
  `check_2k5_mod_studio_release.py`. Size is fine (8 MiB cap).
- **Every new `tools/*.py` must pass `test_shipped_tools_are_self_sufficient.py`**
  — importable with only its own directory on `sys.path`.
- **Allowlist entries needed** (`packaging/release-allowlist.txt` only — none
  for APF): `tools/nfl2k5_ps2_disc_inventory.py`, `tools/ps2_iso9660.py` (in
  **5a**, not 5b — the inventory tool imports it, so it ships with it),
  `tools/validate_nfl2k5_ps2_disc_inventory.sh` **and `.bat`**,
  `mod_editor/core/ps2_disc_service.py`, `mod_editor/gui/ps2_disc_dialog_qt.py`.
  The evidence JSON and the name-join `.csv` need none: they are committed
  evidence the registry row cites, not shipped files. (`.csv` was still chosen
  over `.tsv` so the join can ship later without a suffix fight.)
- **The Python 3.9 baseline on the dev box is 21 passing files / 264 failing
  files, but the cause is `PyQt5` missing, not `datetime.UTC`** — the same 264
  fail under a bare 3.11. With PyQt5 + Pillow installed (3.11 venv,
  `QT_QPA_PLATFORM=offscreen`) 3,233 tests run and 44 files still fail, all on
  the gitignored release inputs (`reports/assets/`, retail catalogs). Compare
  per-file against that venv baseline; it is the only one that exercises the
  count-pin tests.
- `630c4cc` (upstream PR #5) is **byte-identical** to the base tree —
  `git diff cc7bb92 630c4cc` is empty — so the fork's PS2 history is fully
  upstream already.
- **⚠ Dict-shaped runtime pins — found the hard way on the first CI run.**
  `check_2k5_mod_studio_runtime.py` holds `RC29_AUDIO_ANNOTATION_RUNTIME_PINS`,
  a dict of `"path": "<sha256>"` for seven files including
  `mod_editor/gui/studio_qt.py`. **Any edit to a pinned file refuses CI's
  runtime closure** — 5b's File-menu entry did exactly that, after the
  retail-free release gate itself had already passed (300 files, `retail=false`,
  `undeclared=false`). `repin.py` does **not** see these: it handles only the
  `<name>_sha256` attribute shape, so "repin.py has nothing to re-pin" was true
  and useless. And `require()` stops at the **first** mismatch, so one green
  re-pin proves nothing about the next pin. **Before every push, audit every
  `*_PINS` dict in both runtime checkers against current sha256s** (a ten-line
  loop; the 2026-09-04 audit found exactly one mismatch, fixed in `8688b63`).

**Follow the separate-workspace pattern** (`ps2_save_dialog_qt.py` +
Qt-free service). Do **not** retrofit `GameId` gating into
`studio/facade.py` — 3,404 lines with zero `GameId` references today;
4–7 days the additive way versus 2–4 weeks the invasive way.

**Slice 1 status (2026-09-04): built, CI 8/8, and witnessed** — the owner
opened their own `SLUS-20919` ISO in the studio and saw the inventory. That is
the row's runtime evidence; writing it up moves the row off `not-tested`. **The
next milestone is M1, planned in detail in
[`PS2_M1_PLAN.md`](PS2_M1_PLAN.md)** — eight work packages, 8½–12 days,
critical path manifest → ship → registry row → witnessed render.

## Effort

Commits 1–4 ≈ **1–1.5 days** (plausible — the code is committed). Slice 1
complete through 5b ≈ **7–10 days** — an earlier "3–5" was unfounded because
**5b *is* the GUI workspace** (floor 5.5 d). The GUI figure itself was priced
off a 966-line name editor; a 550K-row browser needs a **virtualized model**,
never previously mentioned. Manifest: 2 d + 1 d set-level join + ½ d layout
fix, full coverage 5–6 d — the best-founded numbers here, backed by the
13,431/15,104 measurement. Comparable precedent: the PS2 save lane was
3,782 lines / ~16 commits / **4 calendar days**.

Phase 2 estimates are weaker: stadiums (port) plausible; text optimistic
(716 disc banks ≠ one ROST arena); **playbooks and audio unfounded** — both are
unstarted reverse-engineering.

## ✅ RESOLVED — the hash IS computable offline (proven 2026-09-04)

**The manifest is a pure offline computation. No rig, no dumping, no
emulation.** This was the project's last unbounded risk and it is retired.

Method: read `HashCacheKey::Create` (`GSTextureCache.cpp:9459`) and
`HashTextureLevel` (`:9328`); compiled pcsx2-VR's own
`3rdparty/include/xxhash.h` behind a ctypes shim; hashed **all 120,779 PS2
TXTRs** straight off the ISO (read-only, **7 seconds**) and matched against the
pack's 15,104 canonical identities.

| result | count | share |
|---|---|---|
| **full filename identity** — TEX0Hash **and** CLUTHash both reproduce | **12,958 / 15,104** | **85.8%** ← *the honest headline* |
| TEX0Hash reproduces (473 of these are TEX0-only, palette unproven) | 13,431 | 88.9% |
| `bits` field consistent on every hit | 0 mismatches / 192,276 | **100%** |
| unexplained | 1,673 | 11.1% |

Independent recomputation from `hop1_v5_results.jsonl.gz` confirms every
count exactly. The method is faithful: `xxhash.h` is md5-identical to
pcsx2-VR's, `GSXXH3_64bits` is dispatch-only over `XXH3_64bits(seed 0)`,
`bits = PSM | TW<<6 | TH<<10 | TCC<<14`, TEXA zeroed for `psm.pal>0`, and
`fmsk == 0xFFFFFFFF` for PSMT8/4 so the block path is correct.
**Unverifiable from preserved artifacts:** the 7 s runtime (no timing log), and
the pack denominator (scripts hardcode "of 19052") — though the 15,104 corpus
was verified live on the rig, see below.

**Corpus completeness — verified, the plan's riskiest assumption holds.** A
stress-test asked whether 15,104 was the whole pack or only the narrow-regex
subset (which would have meant ~65% real coverage, not 88.9%). Measured on the
rig: 17,101 unique PNG basenames; **13,245** unique canonical under the old
narrow regex; **15,104** under the widened one — an exact match. The corpus
was built with the widened regex, so 88.9% stands and the manifest does **not**
need re-deriving after commit 2.

The unexplained are concentrated (1,635) in `replacements/Team` at 256×128 /
128×128 — see the final-tally correction below for what they actually are.

**Inputs the hash needs**, all present on disc: PSM/TW/TH from TEX0, L0 pixels,
CLUT. Absent but irrelevant: TEXA (zeroed for palettized), CLAMP region (the
pack has zero `-r` names), mip/base-level config (the pack is **L0-only** —
zero chain or base-shift hits).

**Three verified disc layouts** — implementers need all three:
- `mips=1` → linear rows → `columnTable8` 16×16 block swizzle, row-major
  blocks, XXH3 (PSMT4 uses `columnTable4`, low nibble first)
- `mips>1` → ⚠ **the earlier rule "always pre-swizzled PSMCT32" is WRONG.**
  482 PNGs at mips 5/6/7 are proved *only* by the linear path, and the c32
  path never hits at mips=1 or 7. **Correct rule: try both layouts** — linear
  (`columnTable8`) first, then the c32 route (a one-shot PSMCT32 upload 64 px
  wide = one 8 KB page; rebuild VRAM via `blockTable32`/`columnTable32`, read
  PSMT8 blocks via `blockTable8` + TBW). Note the CLUT base differs per path:
  linear uses `img_off + CBP·256`, c32 uses `CBP·256` into the rebuilt VRAM
  image.
- CLUT → 1024 bytes at descriptor `+0x28` override (TSET siblings), else
  CBP·256; linear layout swaps CSM1 bits 3↔4, c32 layout uses the PSMCT32 VRAM
  read permutation; PSMT4 CLUT raw

**Legacy TCC:** disc TEX0 has TCC=1 on all 120,779 textures, which is the pack's
bit 14. Stock PCSX2 strips it via `RemoveUnusedBits` and never emits it;
pcsx2-VR's classic mode aliases it. Keep manifest keys as **verbatim pack
filenames**, and emit new names with `0x4000` set.

**Provability:** `offline-writer-proved` = both hashes reproduce from the named
TXTR's bytes, `bits` matches disc TEX0, and the name resolves to exactly one
Xbox asset — with the emulator build and mipmap setting pinned.
`runtime-proved` additionally requires it witnessed in a GS-dump replay or
screenshot.

**Row counts (final, v5 over all 120,779 textures).** 12,706 of 15,104 PNGs
have at least one fully-proved (TEX0 + CLUT + Xbox id) row — but only
**4,297 resolve to exactly one Xbox id**. **7,739 fan out to 8+ same-name
Xbox rows** (6.25M pairs — not shippable as-is).

⚠ **The fan-out is NOT confined to `tset:` — that claim was wrong and would
have broken the first manifest slice.** Of the 7,739 fanned-out PNGs:
**3,866 all-`tset`, 2,099 all-`p8`, 1,768 all-scene**, 6 mixed. Half carry no
`tset:` id at all. The earlier statement that "`p8:` and scene rows join
cleanly" is **false** — their own row totals (1,155,613 `p8` + 1,044,488 scene
rows over ≤12,706 PNGs) prove it. **There is no clean 2-day `p8:`/scene-only
slice.** Every namespace needs disambiguation.

⚠ **The proposed set-level join via `Unif`/`NAME` cannot be built as written.**
All 12,814 PS2 and 10,774 Xbox TSET containers are **unnamed**, so no
TSET-name join exists; 634 `Unif` objects cannot address ~12K TSETs; and PS2
has 19% more TSETs than Xbox, so there is no bijection to find. **The viable
route is a shared `(id, chunk)` key**, which resolves **9,917 of 12,814 PS2
TSETs (77%)** — 512 of 1,826 ids disagree and need adjudication. The PS2 side
remains unambiguous (median 2 records per PNG, mean 6.32, max 2,040); the
ambiguity is entirely on the Xbox side. **This is design work, not a 1-day
add-on; budget 2–3 days and expect a policy decision on the 23%.**

⚠ **The 1,673 misses are UNEXPLAINED — both prior explanations were guesses.**
The first ("runtime-composited jersey numbers") was retracted. The second
("cheerleaders 652 + nameplates 634 + Crib posters ~250, a ½-day TBW=4 fix") is
**also unevidenced**: those counts come from a hardcoded shape whitelist over
PS2 *records* with no hit — 1,541 picked out of **55,671 no-hit PS2 records
(46% of the corpus)** — and **nothing joins them to the 1,673 unexplained PNG
names**. No artifact shows the proposed TBW=4/region variant reproducing even
one missing hash. Treat the 1,673 as **open**, budget it as unknown, and do not
promise them in any slice until a fix reproduces real hashes.

**Revised effort (after the technical fact-check):** the manifest is still an
offline computation, but the previous slice plan was built on two false
premises (clean `p8:`/scene joins; a buildable `Unif` set-join). Re-scoped:
**first shippable slice = the 4,297 PNGs that already resolve to exactly one
Xbox id**, all namespaces, all `offline-writer-proved` — **~2 days** including
validator hookup. **Disambiguation of the 7,739 fan-out** via the `(id, chunk)`
key + a duplicate policy: **2–3 days**, yielding roughly 77% of the remainder.
**The 1,673 unexplained: unbudgeted** until a fix reproduces real hashes.
Realistic full-coverage figure: **6–8 days offline, with ~23% of TSETs plus the
1,673 needing adjudication or left out.** Nothing here needs the rig.

**Artifacts** (hashes only, no pixels): `scratchpad/hop1/{gscommon,hop1_v5,
final_tally}.py`, `hop1_v5_results.jsonl`, `hits_v5.tsv`,
`final_summary_hop1.json`.

## Phase 2 — audio, stadiums, text, playbooks (on-disc)

**Confirmed 2026-09-04: emulator-only delivery is acceptable.** That is a
narrower statement than "texture replacement only". PCSX2 overlays *textures*
and nothing else — it has no audio or geometry replacement system — so every
other surface must be written **on disc**. Patching the ISO is entirely
legitimate here precisely because nobody needs real hardware: the Deluxe mods
are themselves patched ISOs.

Distribution model is unchanged and stays retail-free: the tool patches **the
user's own ISO**, exactly as "Build Modded XISO" does on the Xbox side. No
game data ever ships.

### ⚠ This un-shelves the ISO9660 writer

TODO 5 shelved `ps2_iso9660_writer.py` + `_verify.py` because the texture lane
does not need them. **That condition no longer holds for Phase 2.** They are
built, tested (56 tests) and verified against real discs, preserved on branch
`ps2-iso9660`. Phase 2 begins by landing them with a real
`offline-writer-proved` row behind them (~2 days) — this is not a reversal, it
is the documented trigger firing.

### Reachability, best-prepared first

| surface | already in hand | missing | est. |
|---|---|---|---|
| **Stadiums / geometry** | ⭐ PS2 SCNE strides **already decoded** by the disc inventory — texture `0x38`, material `0x60` (name at `+0x58`), node `0x60`, shape `0x70`, marker `0x40`. Xbox side already does bounded glTF round-trip + a same-count position writer that refuses topology changes | port the bounded writer to PS2 strides | **4–6 d** |
| **Text / menus** | Xbox edits 20,074 strings across 716 banks; fixed-allocation editing already proven by the PS2 save writer | PS2 string writer | **2–3 d** |
| **Playbooks / formations** | upstream shipped this for Xbox in Betas 49–53 | PS2 data-table format | **3–5 d** |
| **Audio** | 844 `AUDO` + 17 `AUSB` on the PS2 disc; pcsx2-VR's own `SPU2` tree is a reference decoder | **SPU-ADPCM codec — nothing exists in-repo** (Xbox side is IMA ADPCM, not portable) | **8–12 d** |

### Order and gate

**Stadiums → text → playbooks → audio.** Stadiums first because it is the
best-prepared surface: the PS2 SCNE layout fell out of the inventory work for
free and the hard part (bounded, topology-refusing geometry editing) already
exists on the Xbox side, so it is a port rather than research. Audio last — it
is the only surface needing genuine new codec work.

**Hard gate: do not start Phase 2 until M1 is reached — a texture *witnessed*
rendering in PenguinScreen2.** An earlier version gated on "Slice 1", which is
logically impossible: slice 1 is `read-only-mapped`/`view` with no writer and no
exporter, so it can never produce a render. The gate names **M1**. Every
Phase-2 surface depends on the disc-writing path being real, and that path has
never been exercised end-to-end on PS2. Proving the cheap lane first keeps the
expensive ones honest.

**Parallelism corrections:** the manifest is proven pure-offline and depends
only on ISO + pack — **run it in parallel with commits 1–4**, not after slice 1.
Capability triage is a *prerequisite* of 5a (it decides the `SURFACE_GAMES`
staging 5a hard-codes), not parallel to it.

## Out of scope, deliberately

On-disc PS2 writing · GS texture codec · SPU-ADPCM / EA audio · PS2 audio,
geometry, text, menus and playbooks · real-hardware PS2 mods · NCAA 12 PS2
(**no PS2 release exists** — NCAA 11 is the last).

---

# APPENDIX — session history (SUPERSEDED where it conflicts with the plan above)

**Read this section as an audit trail, not as instructions.** It is the
accreted record of one long working session, kept because it shows what was
measured and how conclusions changed. Where anything below disagrees with the
IMPLEMENTATION PLAN, **the plan wins, without exception.** Known conflicts an
implementer will hit reading top-to-bottom, with the live statement:

| appears below | live statement (plan) |
|---|---|
| ISO9660 writer "shelved for the EA suite" (TODO 5) | **sequenced**, un-shelved in Phase 2 |
| the hash↔asset bridge "must be established empirically from GS dumps" (TODO 2, "the actual core problem") | **proven offline**, 88.9% |
| 148 of 299 evidence paths missing | **144 of 293** |
| the evidence gate blocks CI | **CI passes `--skip-file-checks`**; local nuisance only |
| upstream 5 / 6 / 7 / 572 commits ahead | **8** from base (2026-09-04) |
| "nothing is committed" | **all three branches carry one commit each** |
| `af8ae63` as the re-pin precedent | **`93e1f6a`** (13 sites) |
| 8 count-pin sites / 7 files | **13 / 9** |
| `ps2_save_dialog_qt.py` ~800 lines | **966** |
| a second "Phase 2" = texture dump + manifest | the plan's **Phase 2 = on-disc surfaces** |
| Phase 2 gated on "Slice 1" | gated on **M1** |
| "88.9% reproduce exactly" as the headline | **85.8%** full filename identity (12,958); 88.9% is TEX0-only |
| fan-out "entirely `tset:` children"; "`p8:`/scene join cleanly" | **half the fan-out is `p8:`/scene**; no clean 2-day slice exists |
| set-level join via `Unif`/`NAME` objects | **TSETs are unnamed on both discs**; use the `(id, chunk)` key — 77% |
| 1,673 misses = cheerleaders + nameplates + posters, "½-day fix" | **unexplained and unbudgeted** — both explanations were guesses |
| `mips>1` → pre-swizzled PSMCT32 | **try both layouts**; 482 PNGs at mips 5–7 are linear-only |
| quantization risk dismissed because "both are palettized" | dismissed because **replacements are RGBA PNGs, no re-encode** |
| "APF literal only" on 5a | **5a re-seals APF too** (4 files in its allowlist) |
| `.tsv` evidence | **`.csv`** — `.tsv` is not an allowed release suffix |

Item numbering is not unique across the lists below; refer to items by name.

## ⚠ CORRECTIONS — independent audit, 2026-09-04

An independent audit checked this document against the code. Where they
disagree, **the audit wins**. Corrections, most consequential first:

1. **The registry gate is an 8-file atomic change, not 2 — and it breaks the
   other product.** The row count `70` is hard-pinned in `registry.v1.json`,
   `validate_registry.py`, `packaging/check_2k5_mod_studio_runtime.py:1775`,
   **`packaging/check_apf2k8_mod_studio_runtime.py:1185`**,
   `docs/mod_editor/2k5_mod_studio_getting_started.md:330`, `STATUS.md:2624`,
   and asserted as string literals in `test_apf_studio_installer.py:360` and
   `test_phase1_packaging.py:69`. **Adding one PS2 row breaks the APF 2K8
   release gate**, and four of the eight are shipped files, forcing a release
   re-seal. This omission was the single biggest error here.
2. **`--check-files` does not exist**, and the evidence gate is *not* a CI
   blocker. The flag is `--skip-file-checks`; checking is the default — and
   **CI deliberately passes `--skip-file-checks`** (`.github/workflows/ci.yml:193`,
   with an explanatory comment). It is a local nuisance only. Counts are
   **144 missing of 293** unique evidence paths (72 `docs/research/`, 69
   `reports/assets/`, 3 `reports/asset_samples/`), affecting 66 of 70 rows —
   not the 148/299 stated below.
3. **Nothing is committed.** Branches `ps2-replacement-name-contract` and
   `ps2-iso9660` both point at the base commit `cc7bb92`; `git log base..branch`
   is empty for each. All ~5,700 lines exist only as uncommitted state in two
   `/tmp` worktrees. Anywhere below that describes them as "branches carrying
   work" is wrong.
4. **Upstream distance:** `origin/main..upstream/main` is **572 commits**
   (568 first-parent), not five. From the true base it is 7. The substantive
   claim — no independent PS2 disc work upstream — still holds.
5. **The regex census corpus was `SLUS-21946` — Madden 12, not 2K5.** Valid
   for a filename-shape census, but it should have been flagged. Measured
   against the *actual* 2K5 pack the old regex is worse than stated: it
   rejects **27.36%**, not 14.2%.
6. **New defect found:** `ps2_iso9660.boot_identity()` emits dotted serials
   (`SLUS-209.19`) while `nfl2k5_ps2_replacement_pack_audit.py` uses
   `SERIAL = "SLUS-20919"`. These need normalising before they can be joined.
7. Minor: `ps2_save_dialog_qt.py` is **966** lines, not ~800; two TODO items
   were both numbered 7.

**Verified correct** (do not re-derive): the `datetime.UTC` failures are
genuinely pre-existing (baseline at the base ref: 43 pass / 277 fail; with our
changes the pass/fail set is identical, or baseline **+1** for the ISO9660
suite — zero regressions); the regex measurement reproduces exactly
(4,502 → 5,183 accepted, 0 old-accept-now-rejected); `studio/facade.py` has
**0** `GameId` hits across 3,404 lines; `registry.schema.json` really does pin
`games` to `minItems/maxItems: 2` against a 3-id enum; the fixture-report pin
is exact; and `nfl2k5-xbox-map.v1.json` is absent on every ref.

## Goal

Reuse this repo's existing NFL 2K5 disc-modding machinery — the VC-pack
container reader, the capability-registry/GUI framework, the retail-free
build discipline — to add a second, PS2-targeted "lane" alongside the
existing Xbox lane, the same way `NCAA-Draft-Class-Editor` added a second
platform variant (PS3, big-endian) to its Madden TDB compiler without
forking the codebase: by reading structure from file-embedded metadata and
gating platform differences behind one flag/enum rather than duplicating
tools per platform. The end state is a `nfl2k5_ps2` game lane in
`mod_editor/capabilities/registry.v1.json` with real `offline-writer-proved`
disc-editing capabilities (textures, audio, rosters), not just the one save
capability that exists today.

## What already works for PS2

- **Memory-card save editing** (full lane, shipped): `tools/nfl2k5_ps2_save.py`,
  `tools/nfl2k5_ps2_save_verify.py`, GUI at `mod_editor/gui/ps2_save_dialog_qt.py`
  (~800 lines), service layer `mod_editor/core/ps2_save_service.py` (326
  lines, Qt-free, unit-testable). Reuses the disc-side `ROST` roster parser
  (`tools/nfl_roster.py`) unchanged because PS2 save payloads are the same
  Visual Concepts object as the disc roster. **Verified**: 5/5 real PS2
  saves (roster/franchise/playbook/VIP) checksum-matched; the checksum
  algorithm was independently confirmed by locating the checksum routine
  inside the PS2 executable itself. **Not yet verified**: an edited save has
  not been loaded and observed in a running game (console or emulator) — see
  `NFL2K5_PS2_SAVE_PIPELINE.md` "What's next" §1.
- **Container/pack format**: `tools/nfl_outer.py` (the `vc_53450030` pack
  reader) is platform-agnostic — no Xbox/DXT/PS2-specific code in it at all
  (confirmed by grep). Prior investigation (logged in the sibling
  `NCAA-Draft-Class-Editor` repo's cross-project memory,
  `project_2k5_ps2_fixtures.md`) proved this empirically: running the
  existing Xbox-side parsers directly against PS2 disc data recovered
  259/259 pack entries and passed 254/254 LZ-chunk decompressions.
- **Capability-registry seam already exists for PS2**:
  `mod_editor/capabilities/registry.schema.json` already enumerates
  `nfl2k5_ps2` as a first-class `game` id alongside `nfl2k5_xbox` and
  `apf2k8_xbox360` (schema.json:157-161), and `mod_editor/core/capabilities.py`
  already has a `GameId.NFL2K5_PS2` enum member wired into its game-title
  table (`capabilities.py:117,243,342`). **Only one row uses it today**:
  `nfl2k5ps2.saves.roster_name_writer` — of 70 total registry rows, 1 is
  `nfl2k5_ps2` (per `STATUS.md:2624`), 0 are disc capabilities.
- **PS2 game identity is fully plumbed and unit-tested.**
  `tests/mod_editor/test_ps2_lane.py` asserts `GameId.NFL2K5_PS2` resolves
  with a "PlayStation 2" display name, and that `mod_editor/core/sources.py`'s
  `KNOWN_FINGERPRINTS` pins both `ps2-iso`
  (`f1300699…`) and `ps2-elf` (`e8c3ba9a…`) by sha256 — the same hashes as
  the rig fixtures. **The editor already recognizes a PS2 ISO as a source.**
- **A PS2 disc-format classifier already exists**:
  `tools/nfl2k5_ps2_fixture_audit.py:213-218` distinguishes `xdvdfs_xbox`
  (magic at `0x10000`) from `iso9660` (`CD001` at `0x8001`). Identification
  only — not a filesystem reader/writer — but the PS2-vs-Xbox disc
  discrimination the audit needs is done.
- **The PS2 texture strategy is already designed and scaffolded — and it
  does not require a GS texture codec.**
  `tools/nfl2k5_ps2_replacement_pack_audit.py` establishes that PS2 texture
  modding goes through **PCSX2's own texture-replacement system**: PCSX2
  identifies a texture by a GS texture/CLUT hash and loads a replacement PNG
  named `<16hex>-<16hex>-<8hex>.png` (`PCSX2_HASH_NAME`, tool line 31-33).
  The tool defines and validates a **PS2→Xbox mapping manifest**,
  `nfl2k5-xbox-map.v1.json`, schema `nfl2k5_ps2_to_xbox_texture_map/v1`
  (lines 34-35), whose entries are exactly
  `{"pcsx2_png": <name>, "xbox_asset_id": <id>}` with the asset id namespaced
  `p8:` / `tset:` / `nfl2k5.` — i.e. the Xbox editor's existing resource
  identity space (tool lines 118-135). So the intended flow is: **author in
  the existing Xbox editor → emit PNGs into a PCSX2 replacement tree → PS2
  renders them.** No GS encoder, and no PS2 disc rewriting, for textures.
- **Fixtures are actually available now**, contrary to what this repo's own
  docs currently claim (see staleness note below): the sibling
  `NCAA-Draft-Class-Editor` repo's memory
  (`project_2k5_ps2_fixtures.md`, 2026-07-25) records a verified PS2 ISO
  (MD5 `46ef5e7a2e155994e7c3e5627293e068`, matches this repo's own pinned
  Redump target), a hash-pinned boot ELF `SLUS_209.19`
  (sha256 `e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa`),
  live PS2 memory-card saves, savestates, and GS texture dumps, all on the
  emulator test rig (`~/.config/PCSX2/` on `pacarey@192.168.68.85`). None of
  this is wired into *this* repo's fixture/test infrastructure yet.

### Independently verified specifics (2026-09-04)

The registry claims above were re-checked directly against
`origin/ps2-save-editor-gui`; exact numbers, so the next agent doesn't have
to re-derive them:

- `mod_editor/capabilities/registry.v1.json` carries **70 capability rows**:
  `apf2k8_xbox360` 37, `nfl2k5_xbox` 32, `nfl2k5_ps2` **1**
  (`nfl2k5ps2.saves.roster_name_writer`, surface `saves`, classification
  `offline-writer-proved`). Zero PS2 disc rows, as stated.
- **The PS2 game entry is already fully specified in the registry**, not just
  the id: `registry.v1.json` `games[]` has an `nfl2k5_ps2` entry with
  `platform: "PlayStation 2"`, retail-free `public_input` text, and pinned
  `retail_identity.content_sha256`
  `f1300699ab445ad04b1e27f6e2df87f7a4d1d080d06c7d73499e1be9618a4ebe` +
  `executable_sha256`
  `e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa`.
  **Both hashes match the verified rig fixtures exactly** (per
  `NCAA-Draft-Class-Editor`'s `project_2k5_ps2_fixtures.md`: same ISO sha256,
  same `SLUS_209.19` boot-ELF sha256). So the authoritative expected-hash
  source for TODO 1 is already in-repo — the fixture audit has something
  real to check against.
- **Schema/validator drift, PS2-specific.** `registry.schema.json`
  `properties.games` still requires exactly two games
  (`"minItems": 2, "maxItems": 2`) even though its `$defs.game.properties.id`
  enum was updated to all three ids including `nfl2k5_ps2`. The *enforced*
  rule disagrees: `mod_editor/capabilities/validate_registry.py:179` is a
  hand-rolled validator that hardcodes `len(games) == 3` and canonical id
  order (`:180`), and its line-21 comment reads "The two long-established
  games; `nfl2k5_ps2` joins a surface's coverage rule." So validation
  currently **passes** with three games and the published JSON Schema is the
  stale artifact — a one-line fix (`maxItems: 3`), but worth doing before
  anyone validates the registry with a generic JSON-Schema tool and gets a
  spurious failure.

## Confirmed Xbox/PS2 divergence points

- **Outer container/pack format: identical.** No porting work needed here —
  `tools/nfl_outer.py` already works unmodified against PS2 disc data (see
  above).
- **Textures diverge at the TXTR descriptor — but the chosen route sidesteps
  it.** Xbox stores DXT-family compressed textures; PS2 uses GS (Graphics
  Synthesizer) native formats, and every existing texture tool is
  Xbox/DXT-specific (`tools/nfl_dxt1.py`, the `tools/nfl_all_texture_*` /
  `tools/nfl_*_png_import.py` family; `tools/apf_xenos_*.py` is Xbox-360
  Xenos tiling, not applicable to 2K5 at all). No PS2 GS texture *codec*
  exists in this repo — **and per the replacement-pack design above, one is
  not needed for the PCSX2 route**, because PCSX2 accepts plain PNGs keyed by
  GS hash. A GS codec becomes necessary only if the goal expands to
  rewriting textures *on the PS2 disc itself* rather than replacing them at
  emulation time.
- **The two identity spaces genuinely do not bridge automatically.** Quoting
  the repo's own audit rationale (`nfl2k5_ps2_replacement_pack_audit.py`
  docstring, and `reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json:31-33`):
  "PCSX2 replacement identity is a GS texture/CLUT hash, while the Xbox
  editor addresses an authenticated archive package, TXTR/TSET resource,
  format and fixed span. Image dimensions or a friendly folder name cannot
  bridge those two identities." **This is the actual core problem of the
  port** — not codecs. It must be established empirically from PS2 disc
  selectors + controlled GS dumps.
- **Audio diverges at the codec, and this one is real.** Note the Xbox 2K5
  side is **IMA ADPCM**, not XMA1 (XMA1 is the APF/Xbox-360 product) — see
  `docs/product/NFL2K5_AUSB_XBOX_IMA_DECODE_RESULT.md` and
  `tests/test_xbox_ima_encoder.py`. PS2 uses SPU-ADPCM, and a grep across the
  whole tree for `VAG` / `SPU-ADPCM` / `spu2` returns **zero hits** — no PS2
  audio codec, no reference, nothing. PCSX2 has no audio-replacement
  equivalent to its texture system, so PS2 audio has no shortcut route.
- **Disc filesystem layer diverges** (only matters for true on-disc modding).
  Xbox-side writers (`tools/nfl_audo_wav_xiso_workflow.py` etc.) assume
  XDVDFS for locating/rewriting slots in the disc image. PS2 uses
  ISO9660-family; the repo can *detect* the difference
  (`nfl2k5_ps2_fixture_audit.py:213-218`) but cannot read or write an
  ISO9660 filesystem. The outer VC-pack format sits *inside* whichever
  filesystem wraps it, so the pack reader itself is unaffected.

## Architecture verdict

**A plug-in point exists at the registry/capability layer; it does not yet
exist at the codec/tool layer.**

- The registry (`mod_editor/capabilities/registry.v1.json` +
  `registry.schema.json`) and the game-id enum in
  `mod_editor/core/capabilities.py` are already platform-generic — adding a
  new `nfl2k5_ps2` capability row for a disc-texture or disc-audio writer
  requires no schema change, just a new entry plus a working backend tool.
  `mod_editor/studio/facade.py` and `mod_editor/core/model.py` also already
  reference the multi-game surface (see grep hits at facade.py, model.py).
- The **container parser is already shared** (`nfl_outer.py`), so a PS2
  disc-texture/audio writer plugs in *after* extraction/before
  re-compression at the same seam the Xbox writers use — no new pack-level
  code needed.
- For **textures**, the intended route is emulation-time replacement, not
  disc rewriting, so **no codec abstraction is required**: the Xbox editor's
  existing PNG export is already the right output format. What's missing is
  the *correspondence data* (which GS hash is which Xbox asset), not code.
- The **codec layer would still need building** if the goal expands to
  writing textures onto the PS2 disc: `nfl_dxt1.py` is a hard DXT
  implementation with no format-negotiation point, so a PS2 GS
  encoder/decoder would be a new sibling module plus a format switch by
  game-id in the writer tools (mirroring the `Endian` pattern below).
  **Treat this as out of scope until the PCSX2 route is proven insufficient.**
- The **disc-image layer** (XISO read/write) is Xbox-specific throughout the
  `*_xiso_*` family; a PS2 ISO9660 reader/writer does not exist. Same
  scoping note: only needed for on-disc PS2 modding, which the PCSX2 texture
  route avoids. **Audio is the one lane with no shortcut** — it needs both an
  SPU-ADPCM codec and a way to get bytes onto the disc.

**Net:** the port's critical path is a *data-mapping* problem
(PS2 GS hash ↔ Xbox asset id), not an engineering-primitives problem. My
earlier framing of "three missing primitives" was wrong on the texture lane;
this section supersedes it.

## Relevant precedent from NCAA-Draft-Class-Editor

`NCAA-Draft-Class-Editor` (`/mnt/c/GitHub/NCAA-Draft-Class-Editor`) solved
the closely analogous problem of one binary TDB format needing to support
both a little-endian platform (PS2) and a big-endian platform (PS3) without
forking its compiler. `NcaaDraftEditor.Compiler/MaddenTdb.cs` gained:

1. A `TdbEndian Endian { LittleEndian, BigEndian }` property, auto-detected
   from a sanity check on the file's own `tableCount` field at load time
   (not hardcoded per target).
2. Endian-dispatching read/write helpers (`ReadU16/U32/F32`,
   `WriteU16/U32/F32`) plus a 4-char-name byte-reversal helper
   (`ReadName4`/`WriteName4`) for the one place raw byte order actually
   leaks through as visible ASCII.
3. Range-based table lookups (`nflTeamTgids` / `UpperBound` in
   `MaddenRosterCompiler.Compile`) to handle a platform-specific sparse ID
   scheme (PS3's multiple-TGIDs-per-team) without a separate code path.

The transferable lesson for this repo is the *shape* of the fix, not the
code itself (different game, different format): add one platform
discriminator flag threaded through the shared reader/writer, keep the
metadata-driven parts (offsets, field directories) shared, and isolate the
platform-specific bytes (here: texture codec, audio codec, disc filesystem)
behind that flag rather than cloning tools per platform.

## Existing planning docs found

- **`docs/product/NFL2K5_PS2_SAVE_PIPELINE.md`** — the save-editor
  announcement/status doc (117 lines). Confirms saves work, flags "watch it
  load" (in-game verification) as the next concrete step, and states plainly
  that "the only piece that doesn't carry straight over to 2K5 is the file
  format itself" when comparing to the Madden PS2 pipeline in
  `NCAA-Draft-Class-Editor` — i.e. this doc already anticipates exactly the
  kind of cross-repo reuse this handoff is scoping, but only for *saves*,
  not disc content.
- **`mod_editor/capabilities/ROADMAP.md`** — the authoritative scope
  document for the whole editor. Explicitly states (lines 72–77) that "The
  NFL executable and archive proofs in this workspace target the original
  Xbox release, not the PS2 disc used by PCSX2," and that no ISO/ELF/save/
  texture dump was locally present at the time it was written — **this is
  stale**, per the fixtures note above; update it once PS2 fixtures are
  wired into this repo. The `## Current modding ceiling` table (line 50)
  and its "NFL franchise limits" row explicitly separate Xbox-mapped
  capability from PS2, which remains fully unmapped for disc content.
- **`reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json`** —
  **stale, single-commit file** (only touched by the initial public-beta
  commit `aa4b92e`). It was generated on a different machine
  (paths under `/home/noah/...`) and reports `expected_iso_present: false`,
  `extracted_boot_elf_present: false`, `save_directory_marker_present: false`,
  `safe_ps2_patch_ready: false` — all of which are now **false negatives**
  given the fixtures confirmed present on the current machine/rig (see
  above). It also carries a `local_evidence.rejected_named_disc_suspects`
  list correctly identifying two candidate files as Xbox XDVDFS (not PS2)
  images — that classifier logic is still valid, just needs to be re-run
  against real PS2 fixtures. **Action for next agent: re-run
  `tools/nfl2k5_ps2_fixture_audit.py` (555 lines, already exists and already
  knows how to classify/hash candidates) against the actual PS2 ISO/ELF/
  memcard fixtures and commit a fresh JSON before relying on this file's
  claims.**
- **`ps2-lane-docs` branch** — despite the name, this is **not** a planning
  doc branch. It is an old snapshot of the PS2-save-editor line (5 commits:
  "PS2: write ESPN NFL 2K5 memory-card saves" → "Add the PS2 Save Editor to
  2K5 Mod Studio" → Windows/packaging fixes → "Let the PS2 save editor open
  without the rest of the studio") that has since been superseded and folded
  into `ps2-save-editor-gui`/`main`. A diff against current `origin/main`
  shows ~13,300 deletions (it predates a large amount of unrelated main-line
  work), confirming it's stale history, not a live plan. No action needed
  beyond leaving it alone or deleting it if the maintainer wants to tidy
  branches.
- **`docs/phases/phase0.md`–`phase4.md`** — a *separate*, broader research
  track: reverse-engineering both Xbox titles toward a possible **native
  Linux port** (CMake/SDL2/OpenGL scaffold, Ghidra decompilation ledgers),
  explicitly **not** the same effort as the data-mod editor
  (`ROADMAP.md`'s "Product boundary" section states the near-term product is
  the data-mod editor, not a native port). Phase 0/1 are marked complete for
  *both Xbox titles*; phases 2–4 are explicitly "recovered title logic is
  not connected yet." Nothing here is PS2-specific or currently blocks the
  disc-modding port — it's a parallel, longer-horizon effort worth being
  aware of but not a dependency.

## Hard constraints that gate the TODO below

These are enforced by code in this repo. A PS2 lane that ignores any of them
will be rejected by the repo's own validators, not by review.

1. **The registry has an enforced per-surface game-coverage gate.**
   `mod_editor/capabilities/validate_registry.py:47-53` defines
   `SURFACE_GAMES`: every one of the 21 surfaces maps to `_LEGACY_GAMES`
   (Xbox only) **except** `saves`, which is set to all three games. The
   comment at `:20-21` states `nfl2k5_ps2` "joins a surface's coverage rule
   only when that surface actually ships a PS2 capability row." **So adding a
   PS2 row to any new surface requires deliberately editing `SURFACE_GAMES`
   in the same change.** This is the intended incremental-staging mechanism —
   use it, one surface at a time.
2. **Every `evidence` path in a capability row must exist as a real file.**
   `validate_registry.py:129` asserts `path.is_file()` on each entry, and
   `check_files` defaults to `True` (so `tools/../validate.sh` enforces it).
   **148 of the 299 cited evidence paths are not tracked in git at all** — 72
   under `docs/research/`, 73 under `reports/assets/`, 3 under
   `reports/asset_samples/`, all of which are gitignored roots
   (`.gitignore:27,34,40`). Consequence: **a fresh clone cannot pass registry
   validation**; it only passes on a machine holding the maintainer's private
   research/asset tree. Plan for this — a new PS2 row needs its evidence docs
   authored (locally, untracked) before validation will pass.
3. **`docs/research/nfl2k5_ps2_fixture_protocol.md` is missing — DECIDED: we
   construct it ourselves.** It is cited as evidence by three registry rows
   (`registry.v1.json` :3148, :4337, :4926) but exists on **no ref** (checked
   across all local, origin and upstream refs) and not in this working tree.
   By its name and citations it is the PS2 fixture-capture protocol.
   **Writing it is a strictly passive, strictly improving action**: `research/`
   is gitignored (`.gitignore:27`), so the file is local-only, can never enter
   a release archive, and cannot affect CI or another clone. It also *repairs*
   three currently-dangling evidence references on this machine, moving
   `validate_registry.py --check-files` closer to passing rather than further.
   Write it to describe the capture procedure actually used, so the registry
   rows that cite it become truthful.
4. **The retail-free release gate forbids shipping the very artifacts this
   work produces.** `packaging/check_2k5_mod_studio_release.py` lists `.png`
   in its forbidden suffixes (:207), blocks known retail sha256s (:254) and
   container magic (:264,:431), and rejects metadata carrying `raw_bytes` /
   `rgba_bytes` / `retail_bytes` (:467,:499). **A PCSX2 texture dump is
   decoded retail pixels and can never be committed or shipped.** The mapping
   manifest is compatible *by design* — it stores only a PNG *filename* and
   an `xbox_asset_id`, no pixels — but that property must be preserved
   deliberately. New PS2 files also need adding to
   `packaging/release-allowlist.txt`.
5. **DECIDED: the emulator target is PenguinScreen2, and the GS hashes come
   from there.** PenguinScreen2 is the operator's PS2 emulator, living at
   `/mnt/c/GitHub/pcsx2-VR` (a PCSX2 fork; it self-identifies as PenguinScreen2
   in its `AGENTS.md`, `HANDOFF.md` and `docs/research/branding-assets.md`;
   `penguinscreen2-fixtures` is its fixtures store). It carries the **full
   texture-replacement subsystem in-house** —
   `pcsx2/GS/Renderers/HW/GSTextureReplacements.cpp`,
   `GSTextureReplacementLoaders.cpp`, `GSTextureReplacements.h`.
   **This converts the version-drift risk from an external dependency into a
   controlled, in-house one**: we own the hashing function, so we can pin or
   deliberately stabilize it, and the replacement pack is authored for a
   platform we ship. Record the exact PenguinScreen2 build used for the dump.
   Its texture root (`…/Documents/PenguinScreen2/textures`) is currently
   **empty** — no `SLUS-20919` dump exists yet, confirming TODO 2 is
   genuinely unstarted.

   **⚠ The filename contract is wider than the mod-tools audit assumes.**
   `GSTextureReplacements.cpp:35-40` defines **six** name shapes, any of which
   may additionally carry a `-mip%u` suffix (`:323-344`):

   | shape | format |
   |---|---|
   | plain | `%llx-%08x` |
   | CLUT | `%llx-%llx-%08x` |
   | region | `%llx-r%ux%u-%08x` |
   | region+CLUT | `%llx-%llx-r%ux%u-%08x` |
   | old region | `%llx-r%llx-%08x` |
   | old region+CLUT | `%llx-%llx-r%llx-%08x` |

   Critically the 64-bit fields use `%llx` — **unpadded**, so a hash with a
   leading zero nibble prints *fewer than 16 hex digits*. But
   `tools/nfl2k5_ps2_replacement_pack_audit.py:31-33` requires exactly
   `^[0-9a-f]{16}-[0-9a-f]{16}-[0-9a-f]{8}\.png$` — one shape, fixed width.

   **Measured against a real, working PCSX2 replacement pack on this machine**
   (`/mnt/c/PCSX2/textures/SLUS-21946`, 5,250 PNGs): **748 files — 14.2% —
   fail that regex.** First-field hex-length distribution is
   `{16: 4876, 15: 306, 14: 19, 13: 1, 12: 1, 11: 3, 10: 1, 9: 1, 8: 6, …}`,
   and 42 names have one field, 56 have four, 5 have two. The ~14% failure
   rate matches the theoretical ~12% for a leading zero in either of two
   64-bit fields. **A legitimate dump would be ~1/7 rejected as "not canonical
   PCSX2 hash names"** — plausibly a contributor to the `NFL2K27` audit
   verdict. Fixing this is strictly additive (accept more, reject nothing that
   currently passes) — see TODO 10.
6. **Capturing fixtures means running an emulator on the rig, which has a
   safety rule.** The rig shares one VR headset across three emulators; the
   mandatory live-session check must be run and read *before* any
   GPU/emulator action, and a launch must never be chained behind it. See the
   rig rules in the operator's global instructions (hard rule H-2).

7. **✅ RESOLVED (2026-09-04): both discs are now on the rig.** The designed
   flow authors in the Xbox editor and maps its asset ids
   (`p8:`/`tset:`/`nfl2k5.`) onto PS2 GS hashes, so it needs the Xbox disc
   both to run the editor and to produce the reference pixels each
   correspondence is judged against. That disc was initially absent and has
   since been supplied:

   | role | path (rig) | verified |
   |---|---|---|
   | PS2 capture target | `~/Games/ps2/ESPN NFL 2K5 (USA).iso` | stock `SLUS-20919` |
   | Xbox authoring surface | `~/roms/xbox/ESPN NFL 2K5 (USA)/ESPN NFL 2K5 (USA).xiso.iso` | **`default.xbe` sha256 matches the pin exactly** |

   **Do not be alarmed by a whole-file hash mismatch on the Xbox image.** The
   supplied image is an extract-xiso **rebuild** (game partition at base
   `0x0`, 6,300,958,720 bytes, whole-file sha256
   `ad8aa94cff9338aa43bf9d20117f7ded3880387413bf800873f1479bc6512dee`),
   whereas `KNOWN_FINGERPRINTS`' `7b4b493b…` is a whole-file hash of the
   maintainer's own **ISO** rip — its note even says "Known project *research
   copy*". The contents are identical: parsing XDVDFS and hashing the
   extracted `default.xbe` (11,948,032 bytes) yields
   `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`, an
   **exact match** for the pinned `executable_sha256`. This is precisely the
   case `tests/mod_editor/test_xiso_layout_tolerance.py` exists to accept —
   its docstring: *"any of the above changes the whole-file hash without
   changing one game byte… the container may vary, not the contents."*

   *Remaining check:* confirm the studio actually admits this image when it is
   next opened. If it balks on a whole-file pin, that is a resurfacing of the
   bug the tolerance work fixed, not a bad dump.

## Product-level scope the format plan does not cover

The items above and the TODO below are about *data and formats*. Turning this
into "Mod Studio supports PS2" is a separate body of work that is currently
unplanned:

7. **There is no multi-game shell in the 2K5 studio.**
   `mod_editor/studio/facade.py` contains **no `GameId` gating whatsoever**
   (grep for `GameId`/`game_id`/`for_game` returns only unrelated audio and
   stadium *filters*). The existing 2K5 studio is Xbox-only by construction.
   Telling: the PS2 save editor was added as a **separate dialog**
   (`mod_editor/gui/ps2_save_dialog_qt.py`) with its own Qt-free service
   layer, rather than as a mode inside the studio — that is the established
   pattern, and it is also a warning that no per-game panel gating exists to
   reuse. Decide deliberately: separate PS2 workspace, or retrofit game
   gating into the studio shell.
8. **A new export lane is needed.** The studio's build path terminates in
   "Build Modded XISO". The PCSX2 route's output is a *replacement-pack
   folder* of hash-named PNGs — a different artifact with different rules
   (see constraint 4). Neither the facade nor the GUI has such a lane.
9. **No capability triage has been done.** The registry holds **32
   `nfl2k5_xbox` rows across 21 surfaces** versus **1 PS2 row** (`saves`).
   Each Xbox capability needs classifying into: (a) transfers via PCSX2
   texture replacement, (b) transfers via save editing (already proven),
   (c) requires on-disc PS2 writing (blocked on the deferred ISO9660 +
   GS-codec work), or (d) does not apply. **Without this matrix there is no
   basis for claiming "PS2 support" or scoping it.** Surfaces such as
   `menus`, `scripts_config`, `schedules_franchise` and `models_shap_scne`
   are on-disc content with no PCSX2 shortcut and will land in (c).
10. **CI must stay green without game data.** `tests/mod_editor/test_ps2_lane.py`
    advertises "No game data is required," and the release gate forbids
    retail bytes — but a hash-mapping pipeline is inherently game-data-derived.
    A synthetic-fixture strategy is required so the mapping code is testable
    in CI while the real mapping data stays local.
11. **Target — DECIDED: stock `SLUS-20919`.** GS hashes are content-derived,
    so a mapping captured on the modded `NFL2K27` build would not match stock
    and vice versa; the rig holds both, and the choice is now stock. This is
    also the zero-friction option: the registry already pins the stock ISO and
    boot-ELF sha256s (`registry.v1.json` `games[].nfl2k5_ps2.retail_identity`)
    and `KNOWN_FINGERPRINTS` already recognizes them, so no identity plumbing
    changes are required. **Capture all GS/texture dumps from the stock disc**
    — a dump taken against `NFL2K27` is not reusable and would silently
    produce a manifest that matches nothing on a stock target.
12. **No definition of done.** There is no milestone ladder for what "supports
    PS2" means at v1 (e.g. M1 load+browse a PS2 ISO; M2 export a uniform
    replacement pack proven in PCSX2; M3 multi-surface parity). Without it
    this work has no completion criterion and no releasable increment.

## Open gaps / ranked TODO for whoever starts the PS2 disc port

1. **Re-run the fixture audit for real** — `tools/nfl2k5_ps2_fixture_audit.py`
   against the verified ISO/ELF/memcard fixtures (pull them from the rig per
   `NCAA-Draft-Class-Editor`'s `project_2k5_ps2_fixtures.md`), commit the
   refreshed `nfl2k5_ps2_fixture_availability.json`, and update
   `ROADMAP.md`'s stale "no matching ISO/ELF present" claim.
2. **Produce a real PCSX2 texture dump for `SLUS-20919`** — this is the
   critical path and everything below depends on it. Boot the verified ISO
   in PCSX2 with texture dumping enabled and capture canonical
   `<16hex>-<16hex>-<8hex>.png` names across the screens that matter
   (uniforms, portraits/faces, scorebug, field art, stadium). The repo's own
   audit already recorded that the user's existing `NFL2K27` tree is **not**
   a usable pack for this — 5,688 directories but only four distinct
   cyberface PNGs, "with no PCSX2 hash filenames or mapping manifest…
   cross-console hash mapping waits for the actual pack"
   (`docs/mod_editor/2k5_mod_studio_changelog.md:587-592`). Note the rig
   already holds 2K5 GS dumps (`.gs.zst`) which can seed/verify this.
3. **Build `nfl2k5-xbox-map.v1.json`** — the PS2→Xbox correspondence, schema
   `nfl2k5_ps2_to_xbox_texture_map/v1`, entries
   `{"pcsx2_png", "xbox_asset_id"}` with ids namespaced `p8:`/`tset:`/`nfl2k5.`.
   **This file does not exist on any ref** (checked across all local, origin
   and upstream refs) and is the single highest-value missing artifact —
   `tools/nfl2k5_ps2_replacement_pack_audit.py` already validates it the
   moment it exists. Correspondence has to be established empirically (both
   platforms ship the same source art in different encodings, so
   pixel/perceptual comparison between a PS2-dumped PNG and the Xbox
   editor's exported PNG for a known asset is the natural oracle) — the repo
   is explicit that dimensions or folder names are *not* sufficient evidence.
4. **Confirm the outer-pack proof at full scale** — re-run `nfl_outer.py`
   against the full verified PS2 ISO (not just the earlier ad-hoc counts
   logged in the sibling repo's memory) and land it as a repeatable fixture
   here (`tests/test_nfl2k5_ps2_fixture_audit.py` is the natural home).
5. **✅ DECIDED 2026-09-04 — the ISO9660 work splits.** Two independent
   strategy reviews reached the same conclusion and the owner confirmed it:

   - **The reader lands** (`tools/ps2_iso9660.py`). It now has a real
     consumer — the PS2 disc-inventory capability — so it stops being
     speculative infrastructure. Fix the `SLUS-209.19` → `SLUS-20919` serial
     defect before landing (`boot_identity()` emits a dotted serial that will
     not join against `SERIAL = "SLUS-20919"`).
   - **The writer + verifier do NOT land in the 2K5 lane** (~2,560 lines).
     They have no consumer here: lane A goes through PCSX2 replacement rather
     than rewriting the disc, this repo requires an `offline-writer-proved`
     row behind any writer, and Deluxe modders already rebuild ISOs with
     commodity tools. **Preserved on branch `ps2-iso9660` and reserved for
     the EA Madden/NCAA suite**, whose proof corpus is the Madden 09/12
     discs the writer was already verified against.
   - **The PS2 GS texture codec stays dropped.** Only needed for true on-disc
     texture rewriting, which the PCSX2 route avoids entirely.

   This is a deliberate reversal: the writer was built before the PCSX2
   replacement route was understood. It is good, tested work aimed at a
   problem this lane turned out not to have.
6. **PS2 SPU-ADPCM audio** — the one lane with no shortcut (PCSX2 has no
   audio-replacement system). Zero `VAG`/`SPU` references exist in the repo.
   Reference implementations are available in the user's own
   `/mnt/c/GitHub/pcsx2-VR/pcsx2/SPU2` tree. Scope this only if PS2 audio
   modding is actually wanted.
7. **Add `nfl2k5_ps2` disc capability rows** to
   `mod_editor/capabilities/registry.v1.json` once step 2–5 primitives
   exist, following the same evidence/classification discipline as existing
   rows (`offline-writer-proved` only after an independent verifier exists,
   per `ROADMAP.md`'s status-label table).
8. **Fix the `registry.schema.json` games-cardinality drift**
   (`minItems`/`maxItems` 2 → 3) so the published schema matches what
   `validate_registry.py` actually enforces — trivial, but it's the kind of
   thing that silently blocks a PS2 registry change made by someone
   validating with a stock JSON-Schema tool. See the verified-specifics
   section above.
9. **In-game verification of the existing save writer** is still the
   nearest-term, lowest-risk win and doesn't block the disc-port work above
   — it's a good first task to hand to whoever/whatever picks this up, per
   `NFL2K5_PS2_SAVE_PIPELINE.md`'s own "What's next" §1 (load the VIP save's
   custom ticker text edit and watch it render in-game/PCSX2).
10. **Broaden `PCSX2_HASH_NAME` in `tools/nfl2k5_ps2_replacement_pack_audit.py:31-33`**
    to the real PenguinScreen2 filename contract: unpadded 1-16 hex in each
    64-bit field, the six shapes, and the optional `-mip%u` suffix (constraint
    5). **This is a strictly passive fix** — it only widens acceptance, so
    nothing that passes today can start failing. **Do it *before* the dump in
    TODO 2**, or ~14% of the capture will be misreported as non-canonical.
    Add test cases from the measured shape census.

## Passivity review: keep the Xbox product untouched

**Governing rule for this port: the existing Xbox/APF products must not
change behaviour, must not lose tests, and must not need re-sealing because
of PS2 work.** Classified by blast radius:

### Strictly additive — safe, prefer these

- **New tools/modules as new files** (a mapping builder, a PS2 workspace).
  Nothing existing imports them.
- **Creating `nfl2k5-xbox-map.v1.json`.** It does not exist yet, and
  `nfl2k5_ps2_replacement_pack_audit.py` only validates it *when present* —
  so adding it activates a dormant path rather than altering a live one.
- **Writing `docs/research/nfl2k5_ps2_fixture_protocol.md`** — gitignored,
  local-only, cannot reach a release or CI (see constraint 3).
- **A separate PS2 workspace/dialog**, following the established
  `mod_editor/gui/ps2_save_dialog_qt.py` + `mod_editor/core/ps2_save_service.py`
  pattern (Qt-free service + thin dialog). This is how PS2 was added last
  time, and it is the reason PS2 support so far has cost the Xbox studio
  nothing.
- **New tests.**

### Two-sided atomic — safe for Xbox, but must land in one commit

- **A PS2 capability row + its `SURFACE_GAMES` entry.**
  `validate_registry.py:296-300` builds `expected_coverage` and asserts
  `coverage == expected_coverage` — **equality, not subset**. So a PS2 row
  without the `SURFACE_GAMES` entry fails (unexpected pair), and the entry
  without a row fails (missing pair). They must change together. Note this
  cuts *for* us: the check is per-`(surface, game)` pair, so **no PS2
  addition can disturb an existing Xbox pair.**
- **`packaging/release-allowlist.txt`** must gain any newly shipped file, or
  the release gate rejects it as undeclared.

### Actively breaking — avoid, or do deliberately and atomically

- **⚠ Regenerating `reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json`
  (TODO 1) is a breaking change.** `mod_editor/core/gameplay_inspection.py:53-56`
  hard-pins it: `PS2_FIXTURE_REPORT_SIZE = 6_581` and
  `PS2_FIXTURE_REPORT_SHA256 = f5fd78fe…`, consumed by `_report_provenance()`
  at `:589-591`; `tests/mod_editor/test_gameplay_inspection.py:238-250`
  deliberately mutates a copy to prove tampering is *detected*. Overwriting
  the file changes its size and digest and breaks that pin and those tests.
  **Passive alternative, recommended for Phases 0-2:** leave the file
  untouched as a historical record, and let this handoff doc carry the
  correction (it already does). Regenerate only when a shipping PS2
  capability actually depends on honest fixture reporting, and then do it as
  one atomic change: JSON + both pin constants + affected tests.
- **Retrofitting `GameId` gating into `mod_editor/studio/facade.py`.** That
  facade has no game gating today and is the spine of a mature, heavily
  tested Xbox product. **Prefer the additive separate-workspace pattern
  above.** Do not refactor the Xbox shell to accommodate PS2.
- **Editing `mod_editor/capabilities/registry.schema.json`** (TODO 8, the
  `maxItems` drift). Low functional risk — `validate_registry.py` is
  hand-rolled and never reads the schema — but the file *is* shipped
  (`packaging/release-allowlist.txt:28`), so any edit changes release archive
  bytes. Treat as a release-process cost, not a code risk, and fold it into a
  release that is being cut anyway rather than cutting one for it.
- **Editing `mod_editor/capabilities/ROADMAP.md`'s stale PS2 paragraph.**
  Same class: shipped file, so correcting it re-seals a release. The passive
  choice — already taken — is to let this doc carry the correction and leave
  ROADMAP alone until its next natural edit.

### Note on release determinism

Every archive is byte-reproducible with a published SHA-256 sidecar, and
`STATUS.md` records per-release receipts. **Any change to a shipped file —
including documentation — invalidates the current receipts and requires
re-sealing.** That is the real cost of "small doc fixes" here, and the reason
to batch them rather than land them individually.

## Recommended sequencing and definition of done

The ranked list above is a backlog, not an order. Suggested order, folding in
the constraints and product-scope items:

**Phase 0 — unblock (no game data needed, nothing breaking).**
Write `docs/research/nfl2k5_ps2_fixture_protocol.md` (constraint 3 — gitignored,
so free); **widen the replacement-name regex (TODO 10) — this must precede any
dump**; pin the PenguinScreen2 build (5). Target and emulator are already
decided (stock `SLUS-20919`; PenguinScreen2). Defer the schema drift (TODO 8)
to the next release that is being cut anyway. Every later phase depends on
Phase 0, and none of it touches a shipped file except TODO 10's tool.

**Phase 1 — establish ground truth (read-only).**
Run the fixture audit against real fixtures (TODO 1) **but do not overwrite
the pinned `nfl2k5_ps2_fixture_availability.json`** — see the passivity review;
report to a scratch path instead and let this doc carry the correction. Land
the full-scale outer-pack proof as a repeatable fixture (TODO 4). Leave the
stale `ROADMAP.md:72-77` claim alone for now. Observe the rig safety rule (6).

**Phase 2 — the critical path.**
Capture a real PCSX2 texture dump (TODO 2) and build
`nfl2k5-xbox-map.v1.json` (TODO 3), keeping it pixel-free per constraint 4.
Do the capability triage matrix (9) in parallel — it is pure desk work and
determines everything downstream.

**Phase 3 — make it a product.**
Decide separate-workspace vs studio game-gating (7), build the
replacement-pack export lane (8), author the PS2 capability rows with their
`gui` blocks and evidence (TODO 7), and extend `SURFACE_GAMES` one surface at
a time (constraint 1). Establish the synthetic-fixture CI strategy (10).

**Deferred unless explicitly scoped:** GS texture codec + ISO9660 writer
(TODO 5) and SPU-ADPCM audio (TODO 6). Note that surfaces landing in triage
bucket (c) — `menus`, `scripts_config`, `schedules_franchise`,
`models_shap_scne` and similar on-disc content — stay unreachable until that
deferred work happens. **"PS2 support" should therefore be scoped and
advertised per surface, never as a blanket claim.**

**Proposed definition of done for a first releasable increment (M1):** a user
loads their own PS2 ISO into the tool, edits one proven surface (uniforms is
the natural first, being the most-used texture lane), exports a PCSX2
replacement pack, and sees the change render in PCSX2 — with the capability
row classified honestly (`runtime.status` moved off `not-tested` only once
that render is actually witnessed, per the repo's own classification rules).

## Upstream status note

Upstream (`cruuz/2k-football-mod-tools`) has continued past our fork's
`origin/main` (five commits: Beta 54–58, covering Build & Share/.2k5patch
sharing, franchise history UI, and a "Models — export to Blender" feature —
none PS2-related). Upstream *does* include the same PS2 save-editor
integration we have (`630c4cc "Wire the PS2 save editor into 2K5 Mod Studio
(#5)"` — same PR number/description as our fork's history, confirming
that work has already round-tripped between the fork and upstream) and the
same online-revival planning doc (`992bcc4`, matching our `992bcc4`).
Searching `origin/main..upstream/main` commit subjects for "ps2"
case-insensitively returns only that one already-shared save-editor commit
— **no independent PS2 disc-modding work exists upstream** that would need
merging or would be duplicated by starting this port here.

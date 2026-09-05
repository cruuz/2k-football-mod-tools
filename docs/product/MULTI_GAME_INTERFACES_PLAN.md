# Multi-game interfaces — hosting MVP Baseball, NCAA Football, Madden NFL and ESPN NBA 2K5 on the 2K Football Mod Tools core

> **Status 2026-09-05 — design proven in code, nothing upstream changed.** The contract,
> discovery, registry merge, conformance harness and chooser live under `mod_editor/games/`
> (commits `c74a481`, `a5c2c91`); ESPN NFL 2K5 (PS2) is expressed on the contract as an
> adapter that wraps its shipped lane tools unchanged, and 40 tests prove discovery, identity,
> catalogue, plan → refuse → build → verify on a synthetic disc. No registry row, pin, allowlist
> line or upstream file was edited; §5 lists exactly which edits would be, once, and which files
> never change again.

## 0. The ask, and the answer in one paragraph

The owner wants game support for **Madden NFL** (04/08/09/12 PS2; 12/25 PS3), **NCAA Football**
(04/09/11 PS2 — NCAA 12 has no PS2 release), **MVP Baseball** (2003–2005, PS2/Xbox/GC/PC) and
**ESPN NBA 2K5** (PS2) built *against* SOFTDRINKTV's 2K Football Mod Tools, with SOFTDRINKTV
continuing to maintain the core and never having to learn a game. Today a new game costs the
upstream author edits in a closed `GameId` enum, an exact-set registry validator, a hand-kept
`SURFACE_GAMES` table, thirteen count pins in nine files, an allowlist, a runtime-closure module
list, hash pins that include his own `studio_qt.py`, a version bump and four prose files — the
PS2 lane paid that eight times. The answer is a **versioned game-module contract**
(`vc_game_module/v1`, `mod_editor/games/contract.py`): a game is a directory
`mod_editor/games/<game>/` carrying a manifest, a registry fragment, an allowlist fragment, its
own count pins and a `GAME` object (identity, source identifier, lanes, windows). The core only
*discovers* it. One File-menu action, **"Select other games…"**, opens a core-owned chooser that
lists every module with name, platform, module version, contract version and load status; a
refused module is an explanatory row, never a crash. One `--game` flag mirrors it. A generic
**conformance harness** runs in his CI against every module on the module's own synthetic
source, so he proves a game he has never seen without owning a disc. A frozen-surface test pins
the contract's public names so neither he nor his AI assistant can break it by accident, and a
two-way **plugin boundary** test keeps games out of his internals and his internals out of
games. If he declines the hooks, the **freeze fallback** costs nothing: a game module runs from
`python -m mod_editor.games` against a pinned upstream tag with zero upstream edits.

## 1. The tool as it is — what the interfaces must fit

Read from `83ec5f7` (the PS2 integration head). Line numbers are from that tree.

### 1.1 The closed world of game ids

| site | what it hard-codes | effect on a new game |
|---|---|---|
| `mod_editor/core/model.py:20-30` | `class GameId(str, Enum)` with three members and a display-name table | new member + display name |
| `mod_editor/core/capabilities.py:243` | `_validate_games`: `required = {"nfl2k5_xbox", "apf2k8_xbox360", "nfl2k5_ps2"}` — **exact set equality** | a fourth id fails closed |
| `mod_editor/core/capabilities.py:338-342` | `_game_id`: registry id → enum dict | new entry |
| `mod_editor/core/capabilities.py:117` | `_SAMPLE_REGISTRY["games"]` fallback | new entry |
| `mod_editor/core/sources.py:76-91` | `KNOWN_FINGERPRINTS` (`ps2-iso`, `ps2-elf` for PS2) | two more pins |
| `mod_editor/capabilities/validate_registry.py:20` | `GAMES = ("apf2k8_xbox360", "nfl2k5_ps2", "nfl2k5_xbox")` | append |
| `…/validate_registry.py:23,47-63` | `_LEGACY_GAMES` and `SURFACE_GAMES` (the 21-surface coverage table, widened one surface at a time for PS2) | one line per covered surface |
| `…/validate_registry.py:189-190` | `len(games) == 3`, canonical order | bump |
| `…/validate_registry.py:305-310` | `coverage == expected_coverage` — **set equality**, so a row without its `SURFACE_GAMES` entry and an entry without its row both fail | two-sided atomic commit |
| `…/registry.schema.json:52-53,85,160,261` | `games` min/max 3, 21 surfaces, two `game` id enums | hand edits to a shipped file |
| `mod_editor/project.schema.json:10` | project `game` enum spelled with `GameId` values (`nfl2k5`, not `nfl2k5_xbox`) | another spelling to keep in step |
| `mod_editor/core/product_catalog.py:301,331` | the Xbox sidebar admits `GameId.NFL2K5` only | none — by construction a foreign row never reaches it |
| `mod_editor/core/providers.py` | bound to `GameId.NFL2K5` / `GameId.APF2K8` only (0 PS2 references) | none — PS2 never entered the provider system |

### 1.2 The separate-window precedent (the PS2 lane)

The PS2 lane is the third product in the repository and the only one that was *added* rather
than founded, so it is the measured precedent:

- **Qt-free service + thin dialog + File-menu action + `--flag`.** `mod_editor/core/ps2_*_service.py`
  import their `tools/` modules by putting `tools/` on `sys.path`
  (`ps2_disc_service.py:38-45`); `mod_editor/gui/ps2_*_dialog_qt.py` draw them behind a `Host`
  protocol; `studio_qt.py:1519-1521,1579-1601` adds three actions, `:2047-2130` three handlers
  (each: `_refuse_while_audio_busy`, guarded import, `dialog.exec_()`, `deleteLater`, status
  line), `:7653-7660` two busy toggles; `__main__.py:51-73,509-545` three flags and dispatches.
- **Lane tools come in a trio** — `*_target_catalog.py` (builds a retail-free catalogue from the
  user's disc and ships a `build_synthetic_iso()`), `*_patch.py` (`parse_recipe`, `plan`,
  `apply` → receipt with `declared_ranges`, refuses before anything is created) and
  `*_verify.py` (an *independent* decoder that re-derives the claims and can fail) — plus
  `validate_<lane>.sh/.bat`. All six on-disc writers write a NEW image through the
  fixed-allocation ISO9660 writer (`tools/ps2_iso9660_writer.py`: no extent moves, no size
  change, `O_EXCL` destination).
- **Registry**: 9 `nfl2k5_ps2` rows (`nfl2k5ps2.*`), 6 of them hidden `offline-writer-proved`
  disc writers with `gui.reason` promising "a separate PS2 window off the File menu".
- **Size**: 25 `tools/nfl2k5_ps2_*.py` + 19 validators, 16 test files / 502 tests, 42 commits.

### 1.3 Packaging and gates

- `packaging/release-allowlist.txt` lists shipped files one at a time (54 PS2 lines today);
  `stage_release.py` copies exactly those; `check_2k5_mod_studio_release.py` is bidirectionally
  exact (undeclared file → refuse; declared-but-missing → refuse) and retail-free
  (suffixes, magic, known hashes, payload keys in JSON).
- `check_2k5_mod_studio_runtime.py:1671-1779` imports a literal 109-entry `product_modules`
  tuple (PS2 block `:1697-1732`, 35 entries) and `:1795` `tool_modules`; `:1829` pins
  `len(registry.capabilities) == 78`; `:98-116` `RC29_AUDIO_ANNOTATION_RUNTIME_PINS` hashes
  seven files **including `mod_editor/gui/studio_qt.py`**, so every File-menu edit re-pins
  (`PS2_PORT_HANDOFF.md:535-546` records being bitten by this).
- `tools/validate_all_mod_editor_capabilities.py:61-64` pins `EXPECTED_CAPABILITIES = 78`,
  `…COVERED = 73`, `…UNIQUE_VALIDATORS = 60`; `check_apf2k8_mod_studio_runtime.py:1185` reads
  the *shared* registry and pins 78 too.
- CI (`.github/workflows/ci.yml`) runs every `tests/mod_editor/test_*.py` as a script on
  Linux/macOS/Windows × 3.11/3.12, validates the registry, stages and gates both releases.
  Repository-wide rules scan every `mod_editor/**/*.py`: text writes must pin `newline`
  (`test_generated_artifacts_are_lf`), no hand-rolled directory publish
  (`test_directory_publishes_are_portable`); allowlisted tools must import with their own
  directory off `sys.path` (`test_shipped_tools_are_self_sufficient`) and use no POSIX-only
  `os.O_*` flags (`test_shipped_tools_posix_only`).

## 2. What adding a game costs today — measured

Method: every `nfl2k5_ps2` literal in the tree (624 occurrences, 93 files), every hard-coded
count a row or a game moves, and the git history of the PS2 lane (`git log` over its paths,
`git show --stat` per commit).

**Per new game** (the `af8ae63` shape, 11 files, +241/−10): `GameId` member and display name;
`_game_id` map, `_validate_games` set and the sample registry (3 sites in `capabilities.py`);
two `KNOWN_FINGERPRINTS`; `registry.schema.json` (two enums + `games` bounds) and
`project.schema.json`; `validate_registry.py` (`GAMES`, `len(games) == N`, `_LEGACY_GAMES`
invented on this occasion, `SURFACE_GAMES` restructured); a `games[]` entry with two mandatory
SHA-256 pins; both runtime gates' count pins; `EXPECTED_CAPABILITIES`; a cloned
`test_<game>_lane.py` (which itself pins counts: `test_ps2_lane.py:81` pins 6 disc writers).

**Per new row** (every registry commit since): **13 count pins in 9 files** — verified, and
matching the maintainer's own note (`PS2_M1_PLAN.md:263`, "71→72 at all 13 sites"):
`validate_all_mod_editor_capabilities.py:61,62,64`; `check_2k5_mod_studio_runtime.py:1829,2236`;
`check_apf2k8_mod_studio_runtime.py:1185`; `test_apf_studio_installer.py:360`;
`test_phase1_packaging.py:69,454`; `APF2K8-README.md:594`; `STATUS.md:2786`;
`2k5_mod_studio_getting_started.md:361`; `APF2K8_STATUS.md:750`. Plus the `SURFACE_GAMES`
line for a newly covered surface, the allowlist lines, the `product_modules` entries, an RC
bump (`mod_editor/__init__.py`, asserted by `test_beta45_honesty_freeze.py:24-26`), and a
changelog/STATUS/getting-started sentence each.

**How often the PS2 lane paid**: 4 commits paid the full set (registry + validator +
`EXPECTED_*` + gates + pinned tests: `af8ae63`, `9b11514`, `a63471d`, `1d458de`), 4 more paid a
registry/`EXPECTED_*`/runtime-gate subset (`93e1f6a`, `e6877b0`, `dce38ed`, `630c4cc`) —
**eight** — and a further 11 were allowlist-only appends and 2 toolkit-only; 21 of the lane's
42 commits touched a shared upstream file. Of the 15 commits in the repository's history that
ever edited `validate_all_mod_editor_capabilities.py`, 5 are PS2.

**What is *not* pinned** (good news the design leans on): the allowlist has no line count;
`stage_release.py` and `check_2k5_mod_studio_release.py` are fully generic and take the
allowlist as an argument; CI globs test files; the classification ↔ `(operation, gui.mode)`
rules (`validate_registry.py:289-297`) are game-agnostic.

## 3. What "support" means per target

Support is claimed **per surface, never as a blanket** (the PS2 handoff's rule), and each
surface is classified by where the bytes live: **on-save** (memory card / PS3 save), **on-disc**
(ISO image) or **emulator-side** (PCSX2/RPCS3 texture replacement, memory patches). The
classification decides which shared format package (§4.6) a game composes and which container
discipline applies. Sources are public; every "KNOWN" has an open reader.

### 3.1 The formats, and what is known about them

| format | where | status | sources |
|---|---|---|---|
| **EA TDB** (`DB` magic, v8, table directory, bit-packed records, 4-char field names, CRC-32/MPEG-2 ×4) | Madden/NCAA saves (PS2 LE; PS3 BE with byte-reversed names), on-disc `DB` files, PS3 `USR-DATA` for M12; **not** M25 PS3 franchise (`FrTk` container) | **KNOWN**: parsed and written byte-exact in Python (`tools/parse_madden_tdb.py`, `write_madden_tdb.py`) and C# (`MaddenTdb`) in the sibling repo; bep713 `madden-file-tools`/`madden-db-editor` as reference | sibling `NCAA-Draft-Class-Editor/CLAUDE.md`, `docs/madden08-tdb-schema.md`; github.com/bep713/madden-file-tools |
| **NCAA draft-class binary** (`46 00 40 06` + 1600 × 86-byte records = 138,240 bytes) | NCAA → Madden memory-card exchange (BASLUS-21620LClass07 etc.) | **KNOWN** (sibling repo compiles and Madden 08 imports it; 2018 verified in PCSX2) | sibling repo `DraftClassFile.cs`, `FieldMap.cs` |
| **PS2 memory-card containers**: `.psu` (EMS, no magic), `.max` (`Ps2PowerSave`, CRC32 + LZARI), `.cbs` (`CFU`, RC4+zlib, load-only in mymc), `.sps/.xps` (SharkPort, load-only), `.psv` (PS3 export, SHA1-HMAC), the 8 MB `.ps2` card (superblock, IFC/FAT, 528-byte pages, 12 ECC bytes) | every PS2 save lane | **KNOWN**; `mymcplus` reads all and writes `.max/.psu`; **this repository already has MIT PSU and card read/write with ECC** in `tools/nfl2k5_ps2_save.py` (mymcplus is GPL — do not vendor; the in-repo code is the route) | ps2savetools.com PSU/MAX/card docs; git.sr.ht/~thestr4ng3r/mymcplus; psdevwiki PSU/PS2_Savedata |
| **PS3 saves**: `PARAM.PFD` protection; RPCS3 writes `dev_hdd0` saves unprotected | M12/M25 PS3 rosters | **PARTIAL**: bypass real (RPCS3 issue #9580 "PFD not implemented"); M12 PS3 `USR-DATA` = bare BE TDB (sibling repo, fresh-save bypass validated); M25 roster = BE TDB with 200 PLAY fields incl. contracts; M25 franchise = zlib `FrTk` — **out of scope** | psdevwiki PARAM.PFD; RPCS3 #9580; sibling `docs/madden25-ps3-plan.md` |
| **EA BIG/VIV** (`BIGF`/`BIG4`, BE sizes; `C0FB` 24-bit variant; RefPack `10FB` members) | MVP Baseball PC (`*.big`, `database/*.dat`), MVP Xbox (`Database/database.big`), MVP PS2 (`.BIG` with `.SSH`, one unverified report); **not** Madden/NCAA PS2 game data | **KNOWN** spec + open readers/writers (big4f, libbig, EASportsToolBox, vivtool, refpack-rs) | OpenSAGE BIG spec; rewiki EA_BIG; XeNTaX variant list; niotso RefPack |
| **EA FSH/SHPI textures** (`SHPS` on PS2; PAL4/PAL8 swizzled, RGBA5551/8888, GST-compressed 0x08–0x0F) | MVP 2005 PS2 listed for 0x01/0x02/0x05/0x0E | **KNOWN** read (EA Graphics Manager, fshtool), **PARTIAL** write (GST preview/export only) | rewiki EA_SSH_FSH Type 1/2; bartlomiejduda/EA-Graphics-Manager |
| **EA audio** (SCHl/SCCl/SCDl "SCxl"; PS2 default codec VAG 0x05, EA-XA 0x0A; banks `.abk/.hdr+.dat/.ast/.mus`) | MVP/Madden/NCAA audio | **PARTIAL**: decode KNOWN (vgmstream, ffmpeg demux); encoders exist for EA-XA R1–R3/XAS (lgdel/eaxas) and VAG (psxavenc); **no** public SCHl-VAG writer or bank rebuilder | wiki.multimedia.cx SCxl; vgmstream `ea_schl.c`; lgdel/eaxas |
| **Madden/NCAA PS2 on-disc**: `DATA/*.DAT` "TERF" containers, `STRMDATA.DB`, `BGM.dat`, `FE.QKL/GAME.QKL` | on-disc rosters/textures/audio | **PARTIAL → UNKNOWN**: a tool exists (DFR by JDHalfrack: read/extract/replace/append) but **no public spec**; Deluxe mods ship xdelta ISO patches + `.psu/.max` roster saves + PCSX2 texture packs | footballidiot.com t=16566, t=18096; github.com/maddendeluxe/madden09deluxe, madden12deluxe; ncaanext.com |
| **MVP `database/*.dat` identity** (is it TDB?) | MVP PC rosters (MVPedit, closed source, 19 files) | **UNKNOWN** — no public source says; MVPMods is offline; verify by running the TDB parser on a user's own copy | mvpmods (archived), go2tom42/Total-Installer-Thingy |
| **MVP console saves** (PS2/Xbox/GC) | MVP rosters | **UNKNOWN** — no public work; PS2 community typed rosters in by AutoHotkey rather than editing saves | github.com/CollinErickson/MVP2005 |
| **Xbox saves** (UDATA/TDATA, per-title HMAC-SHA1 signing, signature location per game) / **GC `.gci`** (additive checksums; per-game checksums undocumented) | MVP Xbox/GC saves; Madden/NCAA GC `.gci` (MXDBE opens them ⇒ bare TDB payload) | **PARTIAL** containers, **UNKNOWN** MVP payload | xboxdevwiki Savegame System; gothi.co.uk resigning; YAGCD ch.12 |
| **Visual Concepts PS2 stack** (outer pack archive `/VC_<serial>`, 0x20 chunk headers, `TXTR/TSET/AUDO/AUSB`, text banks, VC-LZ) | ESPN NFL 2K5 PS2 — fully parsed here; **ESPN NBA 2K5 PS2 — sharing plausible, UNCONFIRMED** | KNOWN for NFL 2K5; for NBA 2K5 the first step is measurement (§8) | this repository; NLSC research note `research/ps2_basketball_modding.md` |
| **PCSX2 texture replacement** (names by TEX0/CLUT XXH3-64 + property word) | any PS2 title, emulator-side | **KNOWN**, witnessed here (M1) and used by Deluxe/Revamped | this repository (`nfl2k5_ps2_texture_map.py`) |

### 3.2 The support matrix

Legend: **S** on-save (memory card / PS3 save), **D** on-disc, **E** emulator-side, **–** not a
target, **?** format unknown. "First lane" is what a game module would ship first.

| game | rosters | draft classes | saves / franchise | textures | audio | text | uniforms | stadiums | first lane |
|---|---|---|---|---|---|---|---|---|---|
| Madden 08 PS2 (BASLUS-21638) | **S** TDB `DRost5` (built, 18 seasons) | **S** NCAA class import (built, 19 seasons) | **S** TDB `BFran1` incl. contracts, cap, stats (built) | E (pack) / D ? (TERF) | D ? | D ? | S (TEAM colours in TDB) | – | roster save + draft class (all offline-proved in the sibling repo) |
| Madden 09 PS2 (BASLUS-21770) | **S** (built; Deluxe template) | **S** (BASLUS-21769LClass08) | **S** (built) | E / D ? | D ? | D ? | S | – | same, by parameterisation |
| Madden 12 PS2 (BASLUS-21946) | **S** (built; PLAY bit layout shifted, metadata-driven) | **S** (BASLUS-21932LClass10) | **S** (built) | E / D ? | D ? | D ? | S | – | same |
| Madden 04 PS2 | S ? (TDB era unconfirmed — measure) | S ? | S ? | E | D ? | D ? | ? | – | identity + TDB probe |
| NCAA 09 / 11 PS2 | **S** TDB roster saves (ncaanext documents DB editing) | **S** "Send to Madden" export is the draft class | S | E / D ? | D ? | D ? | S | – | roster save |
| NCAA 04 PS2 | S ? | – (no import target) | S ? | E | D ? | D ? | ? | – | identity + probe |
| Madden 12 PS3 (BLUS30770) | **S** BE TDB roster (built) | – | **S** BE TDB franchise (built) | E (RPCS3) | – | – | S | – | roster |
| Madden 25 PS3 (BLUS31178) | **S** BE TDB roster with contracts (built) | – | – (`FrTk`) | E | – | – | S | – | roster |
| MVP Baseball 2005 PC | D ? BIG + `database/*.dat` (TDB? measure) | – | ? | **D** BIG/FSH (KNOWN) | D SCxl (decode only) | D `datafile.big` | D FSH | D | measure `.dat`; textures |
| MVP 2003–2005 PS2/Xbox/GC | ? | – | ? | D `.BIG`/`.SSH` (PS2, unverified) | ? | ? | ? | ? | identity + inventory only |
| **ESPN NBA 2K5 PS2** | **S** (community ships a 2025 roster as a PS2 memcard save) | – | S | E (pack) / D if VC stack shared | D if shared | D if shared | D if shared | – | **measure VC-stack reuse**, then rosters via the save pipeline |
| College Hoops 2K5 PS2 | S (`.psv` community rosters) | – | S | as above | | | | | after NBA 2K5 |

Two honest limits: on-disc Madden/NCAA PS2 (TERF) and every MVP console save are reverse
engineering, not integration — the plan sequences them after everything that is already known;
and "support" for a surface is claimed only at the classification its evidence earns
(`offline-writer-proved` until a witness on a screen).

## 4. The game-module contract (`vc_game_module/v1`)

Implemented in `mod_editor/games/contract.py`; the frozen public surface is pinned in
`tests/mod_editor/test_games_contract.py::EXPECTED_SURFACE`. The four rules every part follows
are the PS2 lane's own: **passive** (a game never edits an upstream file; the core never imports
a game by name), **fail closed** (a wrong contract version, a malformed identity or a lane that
does not answer the protocol is refused *with a sentence*), **retail-free** (catalogues carry
names, offsets, lengths and digests; the harness checks a catalogue for payload keys, byte
arrays and data URIs with the release gate's own rules) and **fixed allocation with independent
verification** (a build reads the source read-only, writes a destination that must not exist,
declares every byte range it changes, and ships a verifier that can fail).

### 4.1 Identity

- `GameIdentity(game_id, title, platform, serials, executable_sha256, content_sha256)` — the
  registry id, the disc serials (`SLUS-20919`; an Xbox title passes none) and the retail digests
  the game recognises (validated as hex SHA-256; no payload).
- `SourceIdentifier` (Protocol): `accepted_suffixes`, `identify(path) -> SourceIdentity`,
  read-only. `SourceIdentity(kind, path, size_bytes, serial, executable_sha256, serial_matches,
  retail_executable, headline, details)` is what a window shows before any row — the
  `DiscIdentity.headline` wording of the PS2 inventory window, generalised.
- Shared identifiers live in `mod_editor/games/_formats/` (§4.6): `ps2_disc.Ps2DiscIdentifier(
  identity)` wraps `tools/ps2_iso9660.boot_identity` and is parameterised by the game's
  `GameIdentity`, so NFL 2K5 and a future NBA 2K5 module instantiate the same class.

### 4.2 Lanes — one registry row each

`Lane` (Protocol) carries the row's `capability_id`, `surface`, `classification`,
`recipe_schema`, `validators` (repo-relative `tools/validate_<lane>.sh/.bat`) and
`fixed_allocation`, and answers:

| method | contract | PS2 precedent it generalises |
|---|---|---|
| `build_catalogue(source, progress) -> Catalogue` | targets with `key`, `label`, `detail`, `budget` (the fixed allocation in the user's words), `searchable`, `raw`; `document` is the lane tool's catalogue verbatim | `*_target_catalog.build_catalog` |
| `check_edit(target, values) -> str \| None` | the inline, before-Add refusal naming the fix | disc-studio plan §4.6 layer 1 |
| `compose_recipe(edits) -> Mapping` | **exactly** the document the lane's own patcher accepts | `parse_recipe` schemas |
| `plan(source, recipe, catalogue) -> Plan` | dry run against the live source; raises `Refusal` with the patcher's own sentence | `plan()` / `patch(dry_run=True)` |
| `build(source, destination, recipe, catalogue, work_dir) -> Receipt` | NEW destination, `O_EXCL` discipline, `declared_ranges` | `apply()` → receipt |
| `verify(source, destination, receipt) -> Verdict` | the independent verifier; `passed` is the only bit that matters | `*_verify.verify` |
| `synthetic_source(work_dir) -> Path` | a retail-free source the lane can be proved on | `build_synthetic_iso()` |
| `conformance_edits(catalogue) -> tuple[Edit, ...]` | at least one edit the synthetic source accepts | the tools' own `selftest()` fixtures |

The last two are the contract's one addition to what every PS2 tool already does: they turn the
hand-written per-tool self-tests into one **generic harness** (§4.8). `Refusal` is a
`ValidationError`, so a dialog, a worker and the harness have exactly one thing to catch, and
the rule from the export dialog holds — one sentence per condition, the tool's own wording,
never re-worded on the way up.

### 4.3 Windows

`WindowSpec(window_id, menu_label, tooltip, flag, factory, needs_studio_session)`: a separate
window in the shape the PS2 windows set. `factory(parent=None, **context)` builds and returns
the dialog and **must import Qt lazily** (the boundary check refuses module-level `PyQt5`); a
window that works on the Xbox studio's live project says `needs_studio_session=True` and
receives it as `context["facade"]`; every other window opens with no studio state, which is what
lets a user who owns only this game's release use it. `flag` is the command-line spelling
(`ps2-disc` for `--ps2-disc`).

### 4.4 The manifest — the declarative half gates read without importing code

`game.json` beside the package (`GameManifest`): `schema`, `game_id`, `package`, `title`,
`platform`, **`version`** (the module's own version, `1.2.3[-suffix]`), `contract`,
`registry_fragment`, `allowlist_fragment`, `pins`, `product_modules`, `tool_modules`. Paths are
relative and may not escape the package. The three fragments:

- `registry.fragment.json` (`vc_mod_capability_registry_fragment/v1`): the game's `games[]`
  entry, the **surfaces it declares**, and its rows sorted by id. The merge (§5.1) refuses a
  fragment whose rows disagree with its declared surfaces — the per-game form of the validator's
  coverage-equality rule.
- `allowlist.fragment.txt`: the files this game ships, one per line, in the allowlist's own
  grammar.
- `pins.json` (`vc_game_module_pins/v1`): the counts the game's own tests assert
  (`capability_rows`, `surfaces`, `hidden_disc_writers`, `save_writer_ids`, `shipped_files`,
  `product_modules`, `windows`, `lanes_on_contract`, `retail_identity`). This is where
  `test_ps2_lane.py:81`'s `assertEqual(len(disc_writers), 6)` belongs.

### 4.5 `GameModule` and discovery

`GameModule(contract, identity, identifier, lanes, windows, manifest, package)` is what
`mod_editor/games/<game>/__init__.py` exposes as `GAME`. Construction validates the contract
version, unique lane ids and capability ids, unique window ids and flags, that every lane
answers the protocol and that the manifest agrees with the identity and the directory.

`mod_editor.games.discover()` scans `mod_editor/games/*/` for a package with a `game.json`
(underscore-prefixed directories are not games), imports it, takes its `GAME` and validates it.
It **fails closed per package**: a wrong contract version, an import error (a missing
dependency) or a bad `GAME` becomes a `RefusedGame(directory, reason, title, platform, version,
contract)` — the display fields read leniently from `game.json` — and the other games still
load. `manifests()` reads the declarative half without importing any code (what gates use) and
*raises* on an invalid manifest, because a gate must not proceed on a half-read declaration.
`load(game_id)` names the reason when a refused game is asked for. Discovery is
filesystem-based, not entry-point based, because the products ship as a copied tree
(`stage_release.py`), not an installed distribution.

### 4.6 The plugin boundary and shared formats

A game package may import, at module level, only `mod_editor.games.contract`,
`mod_editor.core.errors`, `mod_editor.core.platform_compat`, its own package, and packages under
**`mod_editor.games._formats`**. Everything else — Qt, the studio facade, `providers.py`, and
**a sibling game** — is refused by `conformance.check_boundary` (an AST scan of module-level
imports, including those under top-level `if`/`try`). Function-level imports are lazy and
allowed, which is how a window factory reaches `mod_editor.gui.ps2_*`.

`_formats/` is the sanctioned reuse path: a format package wraps one container or on-disc format
behind the contract's vocabulary, and games **compose** it. Today: `ps2_disc` (ISO9660 volume +
boot identity over `tools/ps2_iso9660.py`). Planned: `ps2_memcard` (PSU/card read/write over
the MIT code in `tools/nfl2k5_ps2_save.py`), `ea_tdb` (the sibling repository's byte-exact TDB
parser/writer, LE and BE), `vc_ps2` (the Visual Concepts outer-pack stack the six NFL 2K5 PS2
lanes each restate — extracted only after the NBA 2K5 measurement says it is shared, §8). The
"different engine" axis (EA) and the "same engine, different sport" axis (NBA 2K5) therefore
meet the contract the same way: through a format package, never by copying a lane.

The boundary is proved in both directions: `test_upstream_imports_nothing_from_the_games_package_today`
scans every upstream `mod_editor/**/*.py` for an import of `mod_editor.games` (there are none;
the two files that gain the one-time hooks in §5 are the only exemptions this test will ever
carry), and `check_boundary` runs on every game in the conformance suite.

### 4.7 Versioning — interfaces the author and his assistant cannot break by accident

- `CONTRACT_SCHEMA = "vc_game_module/v1"`; `accepts_contract()` admits the same major and any
  minor ≤ the core's. A game declaring `v1.7` against a `v1.0` core is refused *with the
  sentence*, as is `v2` — the chooser shows it as a row, the CLI as `error:`.
- Adding an optional field or method is a minor bump; renaming or removing anything is a major
  bump and a documented event.
- `contract_surface()` introspects every public name, dataclass field and protocol member;
  `test_public_surface_is_pinned` compares it to a literal table. An accidental rename by the
  maintainer — or by an AI assistant editing "just a dataclass" — fails his CI before any game
  team sees it. The registry-merge round-trip test does the same for the fragment convention:
  it reproduces `registry.v1.json` byte for byte from `split` → `merge`, and runs his own
  `validate_data` on the result.

### 4.8 The conformance harness — what CI proves for a game he has never seen

`mod_editor/games/conformance.py` knows the contract and nothing about any game. For each
hosted module it runs, and names, these checks (55 for the PS2 adapter today):

1. **manifest** — fragments exist and parse; the registry fragment is self-consistent (declared
   surfaces = rows' surfaces, rows sorted, all rows this game's); every allowlisted file exists;
   pins are plain values; every `product_modules`/`tool_modules` name resolves to a file.
2. **boundary** — §4.6.
3. **module** — every lane's row exists in the fragment with the same surface and
   classification; the row's `validation_command` names one of the lane's `validators`, which
   exist; every window factory is callable.
4. **behaviour, per lane, on the lane's synthetic source** — `identify` (serial matches, and a
   synthetic source is *never* retail); `build_catalogue` (non-empty, retail-free);
   `conformance_edits` pass `check_edit`; `compose_recipe` carries the recipe schema; `plan`
   names the edits, declares ranges (fixed-allocation lanes) and writes nothing; an unknown
   target is refused; `build` creates the destination, leaves the source byte-identical, keeps
   the size (fixed allocation), returns a receipt whose ranges lie inside the destination, and
   **every byte that differs between source and destination lies inside a declared range**;
   `verify` passes; building onto the existing destination and onto the source are refused and
   leave both intact; **a byte flipped outside the declared ranges makes `verify` fail**.

`tests/mod_editor/test_games_conformance.py` runs it on every discovered game — CI's per-file
glob picks the file up with no `ci.yml` edit — and includes a **negative control**: a lane that
changes an undeclared byte and whose verifier always passes is caught by name
(`every_changed_byte_is_declared`, `verify_fails_on_undeclared_change`). A harness that cannot
fail proves nothing. `python -m mod_editor.games --conformance [--static-only]` is the same
harness for a developer's machine.

### 4.9 The chooser — the single GUI seam

Menu placement: `File ▸ Select other games…`, directly under the three existing PS2 entries and
above the Quit separator. The handler mirrors `_open_ps2_export` (busy guard, guarded import,
`GameChooserDialog(parent=self, context={"facade": self.facade})`, `exec_`, `deleteLater`,
status line). The dialog (`mod_editor/games/chooser_qt.py`, model in `chooser.py`) is
core-owned and game-blind:

- **Rows**: one per discovered module, loadable first — *Game* (title), *Platform*, *Module*
  (module version), *Contract*, *Status* ("Ready" / "Cannot load"); a headline
  ("1 game module ready · 2 cannot be loaded (select one to see why)").
- **Detail pane**: for a loadable row, platform · module version · contract · lane count · the
  windows it offers; for a refused row, the refusal sentence (contract mismatch, missing
  dependency, no `GAME`, duplicate id) in the problem colour, with Open disabled.
- **Windows list**: the module's windows; a window that `needs_studio_session` is listed but
  disabled ("needs the studio's open project") when the chooser was opened without a facade
  (the `--game` route), enabled from inside the studio.
- **Open**: `chooser.open_window` asks the module's factory; a factory that raises becomes a
  `Refusal` sentence in the detail pane — the dialog never raises out of a click and never
  imports a module's internals beyond the contract.
- **Failure behaviour** is tested with a fake loadable module, a deliberately incompatible one
  (`vc_game_module/v9`) and one whose import crashes; and the real PS2 adapter's read-only disc
  window opens through it.

Command line: `python -m mod_editor.games` lists modules; `<game-id>` describes one;
`<game-id> --window <id>` opens a window alone; `--chooser` opens the dialog; `--conformance`
runs the harness. The upstream `--game <module-id> [args]` flag is one line of delegation to
this module's `main()`.

**The three PS2 File entries stay.** The adapter already exposes the same three windows to the
chooser, so the PS2 lane is *already* an ordinary module behind it. Removing the hand-written
entries later is optional: it would be one deletion in `studio_qt.py` (and, because that file is
hash-pinned, one RC29 re-pin) — the only reason ever to touch his file again, and one he can
decline forever at no cost.

## 5. Registry, gates and pins with N games — and the one-time hooks

Design rule: every per-game fact lives in the game's directory; upstream files gain **one hook
each, once**, that reads whatever games are present.

### 5.1 Registry fragments merged at validation

`registry_merge.merge(core, fragments)` appends each fragment's `games[]` entry and rows,
sorts both by id (the validator's canonical order — `GAMES` is alphabetical today), refuses a
game declared twice, a row id appearing twice and a fragment whose rows disagree with its
declared surfaces. `coverage(document)` derives `surface → games` from the rows; the tests show
it **equals the hand-maintained `SURFACE_GAMES` table exactly**, and that splitting every game
out and merging them back reproduces `registry.v1.json` byte for byte while `validate_data`
accepts the merged document unchanged. So the validator's `GAMES`, `len(games) == 3` and
`SURFACE_GAMES` become derived quantities: `GAMES` = the merged ids; expected coverage = the
legacy table for the games still in the core file ∪ each fragment's declared surfaces. Two
sources of truth exist only during migration and are guarded by
`test_the_committed_ps2_fragment_is_the_split_of_the_canonical_registry`.

### 5.2 Allowlist and runtime-closure fragments

`mod_editor.games.allowlist_lines()` concatenates every manifest's `allowlist.fragment.txt`
(refusing a file shipped by two games); `runtime_modules()` concatenates `product_modules` /
`tool_modules`. The PS2 fragment is proved equal to today's 54 PS2 allowlist lines in order, and
its 35 product modules to the runtime gate's PS2 block.

### 5.3 Count pins

Row and game counts stop being literals: `EXPECTED_CAPABILITIES` = core rows + Σ fragment rows;
the runtime gates assert the same sum; per-game counts live in `pins.json` and are asserted by
the game's own tests (`GameOwnedPinsTests`). The 13 sites become 0 per row.

### 5.4 Exactly which upstream files need a one-time hook

| file | one-time hook (approximate size) | then |
|---|---|---|
| `mod_editor/gui/studio_qt.py` | one `_game_chooser_action` attribute; one `addAction("Select other games…")` + tooltip + `connect` after `_ps2_export_action` in `_build_file_menu`; one `_open_game_chooser` handler mirroring `_open_ps2_export`; one `setEnabled(not global_busy)` line (~25 lines) | never again for any game |
| `mod_editor/__main__.py` | one `--game` argument (`nargs="+"`, mutually exclusive with `--studio`) dispatching to `mod_editor.games.__main__.main(args.game)` (~8 lines) | never again |
| `mod_editor/capabilities/validate_registry.py` | `load_and_validate`: merge `mod_editor.games.registry_fragments()` into the core document before `validate_data`; derive `GAMES`/coverage as §5.1; keep the canonical-bytes check on the core file (~20 lines) | never again |
| `mod_editor/core/capabilities.py` | `_game_id` returns the `GameId` for the three native products and the plain string id for a discovered game (`Capability.game: GameId \| str`); `_validate_games` requires the natives and accepts discovered ids (~10 lines). `GameId` itself stays the closed enum of *natively hosted products*; a module game never becomes a `ModProject` — the smallest honest change | never again |
| `mod_editor/capabilities/registry.schema.json` | drop the two `game` id enums and the `games` bounds, or leave them describing the core file only (shipped file: fold into a release being cut anyway) | never again |
| `packaging/stage_release.py`, `packaging/check_2k5_mod_studio_release.py` | read the allowlist **plus** `mod_editor.games.allowlist_lines()` (~6 lines each; both are stdlib and `mod_editor.games` is stdlib) | never again |
| `packaging/check_2k5_mod_studio_runtime.py` | `product_modules += runtime_modules()[0]`; registry count pin derived (~5 lines); one RC29 re-pin for the `studio_qt.py` edit | never again (its own pin policy aside) |
| `packaging/check_apf2k8_mod_studio_runtime.py`, `tools/validate_all_mod_editor_capabilities.py` | count pins derived from core + fragments (~10 lines) | never again |
| `mod_editor/project.schema.json`, `mod_editor/core/model.py`, `product_catalog.py`, `providers.py`, `studio/facade.py`, `apf_studio/*`, `.github/workflows/ci.yml`, `test_ps2_lane.py`, `test_phase1_packaging.py` | **no change** | — |
| docs | one getting-started section ("Select other games…"), one changelog bullet, one STATUS line | per release as today, never per game |

Everything else a game needs is under `mod_editor/games/<game>/` and `tests/mod_editor/test_<game>_*.py`.

### 5.5 Per-game cost after the change

A new game is **one new directory and its tests**: `__init__.py` (identity, lanes, windows),
`__main__.py` (two lines), `game.json`, `registry.fragment.json`, `allowlist.fragment.txt`,
`pins.json`, tools and validators under its own names, synthetic fixtures, and test files CI
globs. **Zero upstream edits, zero pins moved, no version bump of the host** — against today's
11–17 upstream files per full-cost commit, eight times for one game.

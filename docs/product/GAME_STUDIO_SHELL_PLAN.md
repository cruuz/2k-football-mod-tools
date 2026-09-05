# Game Studio shell — RC86 plan (one studio per game, every page an interface)

> Status, 2026-09-05: owner decisions recorded; implementation starting. Supersedes the
> window-list chooser of `MULTI_GAME_INTERFACES_PLAN.md` §4.9 and its "each game writes its own
> window" delivery unit (§8). Everything else in that plan stands. RC87 is Madden NFL 09 (PS2)
> as a second title on this shell, working off its disc — not the memory-card save tooling.

## 0. The owner's decisions, verbatim in effect

1. **One studio per game.** The chooser ("Select other games…") lists *studios*, not windows.
   Pick one and it opens. Today: **PS2 NFL 2K5 Studio**. Next: **PS2 Madden 09 Studio**.
2. **Label rule:** `<Console> <Game> <Year> Studio`, e.g. `PS2 NFL 2K5 Studio`, `PS2 Madden 09
   Studio`, `PS2 NCAA 06 Studio`, `PS2 NBA 2K5 Studio`. Three manifest fields; the core composes
   the label; nobody types it anywhere else.
3. **Page parity.** Every game's studio has the Xbox 2K5 studio's page set, in its order. A page
   whose lane does not exist yet, or is classified `unknown`, is present and says exactly why it
   is unavailable. Never a dead button, never a hidden page.
4. **Interfaces, as much as possible.** The shell, the chooser, the build page, the editors and
   the honesty rules are core-owned. A game module writes **lanes** against typed interfaces and
   never UI. That is the part a maintainer's assistant cannot break.
5. **The uniform editor works off each game's own disc.** For PS2 NFL 2K5 that is PS2 art in,
   PCSX2 replacement pack out, first; writing art back into the disc is a later lane.

## 1. Contract changes (1.0 is still `(unreleased)`, so these land in 1.0)

### 1.1 Manifest (`game.json`) — three display fields
| key | example | rule |
|---|---|---|
| `console` | `"PS2"` | 1–8 chars, no whitespace |
| `game` | `"NFL"`, `"Madden"`, `"NCAA"` | 1–24 chars |
| `year` | `"2K5"`, `"09"`, `"06"` | 1–8 chars, no whitespace |

`GameManifest.studio_label` = `f"{console} {game} {year} Studio"`. `title` and `platform` stay
(long forms for detail panes and receipts). `load_manifest` requires the three keys; the
scaffold writes them; conformance checks the label is composed, never hand-typed.

Optional `page_notes`: `{ "<page-id>": "<one sentence>" }` — the game's own reason a page is not
available yet ("Uniform textures are EA FSH inside BIG; decode is known, console write is not").
Shown on the unavailable page under the core's default sentence.

### 1.2 `GameModule.studio_window`
The window id of the module's studio (`"studio"` by convention). It must name one of `windows`.
The chooser, `--game <id>` and `python -m mod_editor.games open <id>` open **that** window; other
windows stay reachable with `--window <id>` and from the studio's own *Windows* menu.

A module may still provide its own studio factory (that is what PS2 NFL 2K5 does today), but the
core provides `mod_editor.games.studio_qt.GameStudioDialog(module, initial_source=None)`, and
the scaffold's default studio window **is** that class. Writing a window becomes optional.

### 1.3 Lane vocabulary made explicit (all additive)
- `Target.fields: tuple[Field, ...]` — what the editor shows for a target. `Field(key, kind,
  label, help, choices=(), minimum=None, maximum=None, read_only=False)`; kinds: `text`,
  `int`, `float`, `bool`, `choice`, `colour_argb`, `png`, `wav`, `name_pick`, `note`.
  `check_edit(target, values)` stays the authority; fields are the shape, not the rule.
- `ReadOnlyLane(Lane)` — catalogue only; `plan/build/verify` refuse by contract. The shell
  renders its page as *inspect*. (v1.1 candidate from the interfaces plan, pulled forward.)
- `ArtLane(Lane)` — texture art. Adds `decode_png(source, target) -> bytes`,
  `encode(source, target, png: bytes) -> EncodedArt | Refusal`, and
  `replacement_identity(target) -> Optional[str]` (the PCSX2 filename, if the game runs in
  PCSX2). The shell's art pages (Uniforms & Equipment, Field Art, Stadiums textures, All
  Textures) get preview, export PNG, import PNG, and *Write PCSX2 pack* from these three.
- `AudioLane(Lane)` — adds `decode_wav(source, target) -> bytes`; the page gets Play/Export.
- `CodePatchLane` — unchanged.
- `Receipt.artifacts` — already present; export lanes declare their files here.
- `Lane.page: str` — which shell page hosts the lane (one of §2's page ids). Defaults from
  `surface` through the table in §2; a lane may name a page explicitly.

### 1.4 CLI verb `lane`
`python -m mod_editor.games lane <game> <lane> catalogue|plan|build|verify …` runs one lane step
in a child process with progress lines on stdout. The studio service uses it for long
catalogues and for builds, so a crash in a lane never takes the window down, and a CLI-only
writer is usable before any window exists.

### 1.5 Versioning
`CONTRACT_CHANGELOG.md` 1.0 entry gains the items above; pins re-cut once at the end of RC86
(`python -m mod_editor.games pins --write`); frozen tests updated with the contract, never around
it. The frozen surface test lists the new names.

## 2. The shell — `mod_editor/games/studio_qt.py` (core-owned)

`GameStudioDialog(module, *, parent=None, initial_source=None)`:

- **Header:** the studio label; the module's title and platform; the boundary note ("your image is
  opened read-only; every edit lands in a new file").
- **Source row:** Open… (suffixes from `module.identifier.accepted_suffixes`), identity headline
  from `SourceIdentifier.identify`, refusals shown inline.
- **Pages**, left navigation, Xbox order. Page ids and the surfaces that feed them:

| page id | title (Xbox studio) | registry surfaces |
|---|---|---|
| `uniforms` | Uniforms & Equipment | `uniforms` |
| `rosters` | Names, Numbers & Faces | `players_rosters`, `portraits_faces` |
| `identity` | Text & Team Identity | `menus` (text), `colors`, `logos_cards` |
| `field_art` | Field Art & Create-Team Art | `logos_cards` (field), `textures` (field) |
| `stadiums` | Stadiums | `stadiums_fields` |
| `presentation` | Presentation | `scorebug_presentation` |
| `menus` | Menus & UI | `menus` |
| `crib` | The Crib | `crib_assets` |
| `audio` | Audio | `audio` |
| `gameplay` | Gameplay | `gameplay_tuning_sliders`, `catching_drops`, `cpu_ai_draft` |
| `playbooks` | Playbooks & Plays | `scripts_config` |
| `textures` | All Textures | `textures` |
| `saves` | Saves | `saves`, `schedules_franchise` |
| `build` | Build & Share | — (every staged edit, chained, receipts, verify) |

  A lane names its page (`Lane.page`), defaulting from its surface through this table. A page
  with several lanes shows them as sub-tabs (the Xbox studio does the same).
- **Unavailable page:** the page exists with its title and one honest panel: "No <page> lane in
  <studio label> yet." plus the module's `page_notes` sentence if any, plus, for a lane that
  exists but is classified `unknown`/`unsafe/deferred`, that row's `gui.reason` from the
  registry. No controls.
- **Lane page (generic):** the PS2 Disc Studio's `LaneTab` generalised: catalogue button and
  scope picker, target table with search, editor form built from `Target.fields`, Check (calls
  `check_edit`), Add to build, staged list, recipe preview. Optional protocols add: image preview
  + Export PNG + Import PNG + Write PCSX2 pack (`ArtLane`); Play + Export WAV (`AudioLane`);
  inspect-only (`ReadOnlyLane`); the pnach preview (`CodePatchLane`).
- **Build & Share:** the Disc Studio's BuildPage and its chained service, generalised over
  contract lanes through the `lane` CLI verb: destination must not exist; volume check; per-step
  verify; receipts; the kit/HOW-TO for export lanes.
- **Windows menu:** every module window except the studio (PS2: Save Editor, Disc Inventory,
  Export replacement pack).
- **Honesty:** every writer page shows its registry classification badge and, when not
  `runtime-proved`, upstream's "Not yet tested in-game" wording.

## 3. Chooser and File menu

- `GameChooserDialog` rows = studios: label, status (Ready / Cannot load), detail (title,
  platform, module version, lane count). Open opens the studio. Sorted by console, game, year.
  Refused modules keep their refusal sentence, Open disabled.
- Xbox studio File menu: **PS2 NFL 2K5 Studio…** and **Select other games…** only. The three
  PS2 side entries move into the PS2 studio's Windows menu. `--ps2-save/--ps2-disc/--ps2-export`
  flags stay (they open the windows alone). `studio_qt.py` is hash-pinned: one re-pin.
- `python -m mod_editor.games`: listing shows studio labels; `open <game>` opens the studio.

## 4. PS2 NFL 2K5 on the shell

- Manifest: `console="PS2"`, `game="NFL"`, `year="2K5"`, `studio_window="studio"`.
- The six disc lanes, the code-patch lane, the read-only inventory and the export lane are
  exposed as contract lanes with `Target.fields` (they already are lanes; fields are added).
- **Uniform art lane** (`nfl2k5_ps2.uniform_art`, `ArtLane`, classification `extract-only`):
  catalogue = the disc's uniform TSET/TXTR children joined to team/kit through the existing
  texture map (1,394 logical uniform ids); `decode_png` = TEX0 → PSMT8/PSMT4 unswizzle (the
  code in `tools/nfl2k5_ps2_texture_map.py` that already feeds the XXH3 identities) + CLUT
  expand → RGBA PNG; `replacement_identity` = the existing name rule; `encode` accepts a PNG of
  the same size (or an integer multiple, which PCSX2 scales) and refuses anything else with the
  size it wanted; build = the existing pack writer + receipt; verify = the existing independent
  verifier. Registry: the `uniforms.replacement_pack_export` row's scope widens to "from the
  disc's own textures, or from an Xbox project", still `extract-only` by rule.
- The hand-written `Ps2DiscStudioDialog` is retired once the shell renders every PS2 page with
  the same tests green; the PS2 tab classes' custom editors become `Target.fields` kinds
  (`colour_argb`, `name_pick`, `wav`, `png`).
- PS2 registry rows move to the module fragment (interfaces plan §5): `registry.v1.json` loses
  them, `validate_registry.py` validates the merged document, the 13 count pins fall to zero
  PS2-specific edits.

## 5. Madden NFL 09 (PS2) — RC87 on this shell, disc-based

Module `madden09_ps2`: `console="PS2"`, `game="Madden"`, `year="09"`; serial `SLUS-21770`,
vanilla and Deluxe images recognised by their boot-ELF digests (vanilla ELF CRC `38014255`,
Deluxe `084562FF`; whole-image sha256 `b34e8a6a…` / `d331c5e4…`). Day one: every page present.

**Prior art — measured, not assumed.** The owner's `nfl-online-revival` repository (read-only
reference; no licence file, so the fork re-expresses rather than copies) already holds the disc
research this module needs: `tools/lzh1.py` (the `TERF` `COMP` member codecs `LZH1` id 5 and
`RLE1` id 1, reversed from the Madden 2004 executable), `tools/madden_tdb.py` (the `TERF → DIR1 →
[COMP] → DATA` walk and the EA TDB reader), `docs/madden09-container-census.md` (every member of
every container, with decompressed formats), `docs/madden09-iso-contents.md`, `-tdb-schema.md`,
`-data-layer.md`, `-deluxe-diff.md`, `-player-struct.md`, `-playbook-map.md`, `-funcmap.md`. Its
census settles what the pages edit:

| page | on the disc | format | first rung |
|---|---|---|---|
| Uniforms & Equipment | `UNIFORMS.DAT`: 455 `MMAP` textures (+270 empty slots); faces in `PLYRFACE`/`COACFACE`, tattoos | `MMAP` v2: 40-byte header, width/height at +0x28, palettised pixels + palette | inventory → PCSX2 pack (`ArtLane`, extract-only) → write-back once the `COMP` writer round-trips |
| Stadiums | `STADIUMS.DAT`: 651 `SMF\0` geometry + 434 `MMAP`; `STADATA.DAT` | `SMF` geometry, `MMAP` textures | inventory; textures as art; geometry read-only |
| Field Art | `FIELDART.DAT`: 642 `SMF\0` + 73 `MMAP` | same | same |
| Text & Team Identity / Menus | `TEXT` members: 14,049 strings, mostly the story generator (`STRYTEXT` 6,973 …); team data in `DB_TEAMS.DAT` (234 EA TDB v8 members) and `STRMDATA.DB` (bare TDB) | `TEXT`, EA TDB | TDB rows as writers (`offline-writer-proved` with an independent verifier) once the container writer is proved; `GAME.QKL`/`FE.QKL` are copies a data patch must keep consistent |
| Audio | `SOUNDDAT.DAT`, `BGM.DAT` (TERF audio variant), speech `SPCH*.DAT` (`SCHl`) | EA `SCHl` | decode-to-WAV export only; no public writer, the page says so |
| Rosters | on-disc roster/team TDBs; memory-card saves are out of scope for RC87 | EA TDB | inventory, then writers |
| Playbooks, Gameplay | executable + data; the owner's funcmap and pnach→ISO pipeline exist | R5900 | `CodePatchLane` scaffold, translations refused until mapped |

Lanes earn rungs in this order, each with an independent verifier and a synthetic source:
inventory (`ReadOnlyLane`) for every container → uniform art via PCSX2 packs (identities need a
GS-dump capture of Madden 09 on the rig: one human session, or the headless dump seam once a save
state exists; the NCAA 06 + Madden 08 community pack proves the route) → TDB writers through the
`TERF` rewrite path (`DATA` containers first, `COMP` when the encoder round-trips; the owner's
`docs/lzh1-encoder-design.md` is the design) → audio export → code patches.

## 6. Work packages

| WP | what | owner | depends on |
|---|---|---|---|
| A1 | contract: manifest fields, `studio_window`, `Field`/`Target.fields`, `ReadOnlyLane`, `ArtLane`, `AudioLane`, `Lane.page`, `lane` CLI verb, scaffold, conformance checks, frozen tests, `CONTRACT_CHANGELOG` | agent | — |
| A2 | the shell (`GameStudioDialog`, generic lane page, build page over the `lane` verb, unavailable pages, Windows menu), chooser as studio list, File menu, CLI `open`, tests | agent | A1 |
| C | PS2 uniform art `ArtLane`: decode to PNG, encode checks, identities, pack, verifier, tests, Uniforms page data | agent (own worktree; no contract or registry edits) | spec §1.3 |
| D | PS2 module on the shell: `Target.fields` for the six lanes, manifest fields, `studio_window`, retire the hand-written dialog when parity is green; PS2 rows to the fragment | me + agent | A2, C |
| E | docs (contract, adding a game, getting started, handoff), changelog, STATUS, pins, release RC86, Windows smoke, runbook | me | D |
| F1 | `_formats/ea_terf` (TERF/DIR1, `DATA` + `COMP`, LZH1/RLE1 decode re-expressed from the owner's tools, member-format ids, `MMAP` header, `DATA` rewrite, inspect CLI, synthetic tests) | agent (own worktree) | prior art |
| F | Madden 09 module: identity, inventory lane, uniform-art lane (needs the dump session), TDB lanes, page notes; RC87 | agents | E, F1, disc dumps |

Acceptance for RC86: every game module renders all 14 pages offscreen in conformance; the PS2
studio shows the six writers, the code-patch lane, the inventory and the uniform art on the
shell with the existing tests green; `Select other games…` lists `PS2 NFL 2K5 Studio` alone and
opens it; the label is composed from the manifest; `pins --check`, `fragments --check`, both
release gates and the nine CI jobs pass; the portable build's smoke passes on Windows.

# 2K5 Mod Studio — Product Changelog

## v1.0 RC83 — (unreleased)

- **Fixed: a refusal now says which disc image you handed it.** One report carried two failures
  on one file: Build & Share -> Advanced died with `pack-0 schedule template is foreign: ROST
  stored size is not retail`, and Apply refused with `2802 run(s) hold bytes that are neither
  the expected base nor the patched bytes`. Both sentences were true and neither was actionable,
  because both are the same sentence for four different images. A new identifier
  (`mod_editor/core/nfl2k5_disc_identity.py`) finds `default.xbe` and `vc_53450030/0` through the
  disc directory, hashes them, compares their positions with the retail layout, and names the
  image: **retail dump (xiso)**, **retail dump (raw/redump with video partition)**, **repacked
  disc**, **modified disc**, or **unknown image**, each with a sentence saying what to do. The
  Build tab's source line and the Apply panel show it the moment you choose a file, and every
  Build refusal, the schedule step's refusal and the Apply MISMATCH text quote it.
- **A repacked disc builds.** Retail file bytes rebuilt at other sectors are a legal image for
  Build & Share, which resolves every file through the disc directory, and the schedule step now
  finds the ROST roster resource by **searching the pack for it** rather than trusting pack
  offset 0x392800, so a rearranged pack is read where the resource really is instead of being
  called foreign because one u32 was somewhere else. What a repack cannot do is take a
  `.2k5patch`, since a patch addresses bytes by their position in the game partition; Apply now
  says exactly that and points at the Build tab.
- **Published patches stop calling themselves a "custom base".** A patch exported from a working
  copy still applies to a retail dump when every run's expected bytes are the retail bytes.
  `modpack.export` takes a retail image (`--retail-image`, or the new optional field on the
  Share page), proves every run against it, and records `is_retail_equivalent` in the manifest;
  Apply then reads "Base: retail-equivalent" instead of warning about a base that never affected
  the person reading it. Without that proof nothing is claimed.

- **Fixed: "made the patch and didn't get the new scorebug at the bottom."** The ESPN scorebug
  was the one Build step that could only run on the machine it was written on. Its inputs are
  the retail score_bug scene and three retail P8 atlases, plus our repaints of those atlases —
  and a repaint that keeps the retail alpha silhouette, the retail letter mask and one retail
  glyph cell is retail-derived, so none of it could ship under the retail-free release rule.
  The Build tab therefore showed "Not available in this build" and **Advanced silently skipped
  the scorebug**; only the published `.2k5patch` files carried those bytes. Nothing has to ship:
  every input is now read out of **your own disc image** at build time. The scene span and the
  three atlas spans are read at pinned pack-relative offsets — the pack resolved through your
  image's own file table — and checked against the audited retail SHA-256 first; the
  retail atlases are decoded to PNGs and the modern art is regenerated from them by the
  generator that has always shipped (`tools/nfl2k5_scorebug_espn_art.py`), then cached beside
  the model index in the private, disc-derived cache so a second build does no work. The result
  is byte-for-byte what this workstation builds: on the retail image, the re-laid mesh span, the
  `score_buga`, `shield_espn` and `digital_font` spans and the whole patched `default.xbe` are
  identical to a build made with the developer files present
  (`tests/mod_editor/test_nfl2k5_scorebug_source_art.py`, including a full write over a real
  disc copy).
  `availability()["scorebug"]` is now about what this build can DO, not about files on one
  person's disk, and the Presentation tab draws its planned-look mockup from your disc instead
  of saying "mockup not shipped in this build".
  - The shared **digit sheet** (`digital_font`) is drawn with DejaVu Sans Bold. Where that face
    is not installed the sheet is skipped and named in the receipt rather than silently redrawn
    in a fallback font; the bar itself never depends on it.
  - The **ticker-band atlas** (`NAVTEXTURE`, the Bottom Line strip under the bar) was hand
    painted and has no generator, so it stays out of a release build and your ticker keeps its
    retail art. The receipt says so. The published `SOFTDRINK patch advanced` `.2k5patch` still
    carries it — Share → Apply.
  - Every receipt now records where each PNG came from (`art_origin`), whether it matched the
    reference art the published patches were built with (`art_reference_match`), and anything
    that was skipped and why (`art_skipped`).
- The scorebug's texture writer and the field-pack texture writer no longer need an extracted
  copy of `vc_53450030/0` (a developer artefact that was never in a release, and whose absence
  made the step fail even here unless `NFL2K5_RETAIL_INDEX` happened to be set). Both read the
  retail template out of the image they are writing, at a pinned offset with a pinned digest, and
  fall back to the extracted archive only to tell "already imported" from "foreign bytes".
- The scorebug mockup's triangle strips are decoded from the retail scene's own command blocks
  instead of an intermediate glTF research export; the export is no longer needed anywhere.
- **★ Models: a whole player body in one operation.** A player is three scenes -- `hi_body`
  (drawn close up), `lo_body` (swapped in at distance) and `hi_head` -- so a body edit made on one
  of them alone changes shape when the camera pulls back; a modder who exported all three had no
  way to apply more than one of them. Selecting any of the three now arms a **Player body set**
  box: **Export the body set** writes all three (plus a set README) into the export folder, and
  **Check the folder** fits every edited file in one go and writes them into **ONE** copy of the
  disc. It is all-or-nothing twice over: a member that no longer fits its space on the disc
  refuses the whole set *before* the disc is copied, and every member's place on the disc is
  located and checked before the first byte moves. A set is "the three SCNE of one pack entry
  named hi_body / lo_body / hi_head" -- on the retail disc, outer 3 chunks 114 / 113 / 115, and
  no other pack entry carries any of those names. A file you did not touch is skipped and named in
  the report (exporting the set writes all three, so editing only the head is normal); a folder
  where nothing changed is refused. Measured on the real cache: a 120-vertex nudge on both bodies
  repacks to 202,224 of `hi_body`'s 202,240 stored bytes and 135,792 of `lo_body`'s 135,808 with
  the wrapper byte-identical, while a scattered edit (every tenth vertex) needs 623 bytes more than
  `hi_body` has and refuses the whole set - so body edits want to be smooth and local. Single-model
  export and import are unchanged. (`nfl2k5_models.body_sets` / `export_body_set` /
  `compile_body_set_import` / `write_import_set_copy`, new `UnchangedModelError`, `models_panel_qt`.)
- **Fixed: the roster screens listed "Linebackers" twice in a row** with the one-pool positions
  patch on (a user, 2026-09-04). The home screen's Team Rosters, the draft, free agency, the trade
  block and scouting each own a fixed position-filter list with one row per roster code -- fifteen
  arrays of 17-19 records (`0xB0`/`0xC8`/`0x110`/`0x118`/`0x120`/`0x128` bytes, name pointer at
  `+0x00`, roster enum at `+0x18`; the count handler is `FUN_0031AB20` -> `FUN_000C3CB0(team,
  position)`), and the `Outside Linebackers` record is always the one immediately before
  `Inside Linebackers` (0x539520/0x5395E8, 0x53A1F8/0x53A2A8, 0x53AF90/0x53B058, 0x53DEF0/0x53E008,
  0x53FBF0/0x53FD18, 0x5498E8/0x549998, 0x550F68/0x551078, 0x552798/0x5528B0, 0x5545E8/0x554700,
  0x559450/0x559578, 0x55EFB0/0x55F078, 0x570D30/0x570E50, 0x57FD70/0x57FE90, 0x582658/0x582778,
  0x588060/0x588178). Beta 58 renamed **both** rows and pointed the OLB row's enum at 11. The
  retired enum 10 now keeps its retail name everywhere the game prints a roster position -- the
  abbreviation table entry `0x4F26F8` stays `OLB` (0xE69C54), `0xE69D40`/`0xE69EE8` stay
  `Outside Linebacker(s)`, and all fifteen filter records keep enum 10 and their own strings -- so
  every screen shows exactly one `Linebackers` row. The behaviour half of the merge is untouched:
  enum 10 still maps to the ILB kind, reads the LB lists, has a roster target of 0 and is emptied
  by the roster pass, so the `Outside Linebackers` row simply lists nobody, the way `Fullbacks`
  does for a team without one. Removing the row instead would mean restructuring fifteen abutting
  record arrays that have no count word, which cannot be proved without running the game. The
  patch is 46 sites / 655 bytes (was 75 / 935). Also found: the fifteenth OLB record (0x55EFB0,
  the draft board) carries the retail typo `outside Linebackers` at 0xEAE8CC, which is why beta
  58's exact-text sweep renamed only fourteen and left one screen mismatched.
  (`nfl2k5_position_pools.py`, new `filter_rows` / `retail_olb_identity` readbacks.)
- **The Player Card's TEAM column is consistent now.** The shipped nflverse history covers 5,042
  of the 5,838 rows the card can show, and the rest read `--`, about one row in seven, scattered
  down a career (Noah: "make it more consistent"). Every season the data does not cover is now
  filled with that player's **own 2004 club**, read from the roster's 32 team records (each starts
  with a NULL-terminated array of player pointers before its abbreviation at `+0x108`), and
  counted separately in the receipt and the shipped match log as `seasons_inferred` so the data's
  own coverage stays honest. Result on the retail roster: **5,746 of 5,838 rows name a team**
  (was 5,042), 704 seasons over 185 players inferred, pool 36,866 -> 42,612 of 50,000. Only three
  things still read `--`: the folded "pre" row and Total, a season the roster carries no stats for,
  and the 2004 free agents (41 players, 92 rows) who are on no club at all. A CSV row always wins
  over the fill, so one line corrects any inferred season; `infer_current_team=False` restores the
  data-only behaviour. The current-season row keeps reading the player's live team in every mode
  (the getter tests `ecx == 11` before it ever looks at field 87 -- now asserted under unicorn even
  with a field-87 entry present for that slot). (`nfl2k5_team_history.py`, repinned
  `SHIPPED_POOL_SHA256`.)
## v1.0 RC83 — ★ Rosters: the whole roster editable, on the disc and in a save (unreleased)

- **★ Rosters, a new top-level page — the studio's replacement for Flying Finn's NFL 2K5 GameSave
  Editor.** Team list → player grid → attribute cards, the layout everybody already knows, over the
  **disc** as well as over an Xbox save, with the things his 2008 Delphi build could not do: undo and
  redo, dirty markers per player and per field, a diff of the whole edit before anything is written,
  a validation pass, and a source file that is never touched. Every field of the 0x54 record is
  editable: names and college through the shared string pool, position, jersey, years pro, hand,
  height, weight, date of birth, play-by-play and portrait ids, every appearance and equipment slot,
  all 28 rating bytes, the depth rank and side, and the **contract block** (value, type, signing-bonus
  tier, length, remaining, with the derived penalty shown) — which no open tool has ever edited.
  Format credit: **Flying Finn (Glen Leskinen)** and **Bad_AL** (NFL2K5Tool); the map was re-verified
  byte for byte against the retail disc before a line of it was written.
- `mod_editor/core/nfl2k5_roster_records.py`: a typed codec whose field table claims **all 84 bytes
  with no gaps** — every named field plus one explicitly named `unknown_*` field for every bit nobody
  has named yet, which is why decode → encode is **byte-identical on all 2,547 retail records** and
  on the whole 0x90F60 body. Also the team record (65 pointers = the depth order, count byte, coach
  pointer, abbreviation), the 266-entry college table, the free-agent list, and both string pools.
- **The three style channels get first-class controls** (2026-09-04 executable study). **Power Run
  Style** (`+0x4D`) as a Finesse / Balanced / Power segmented control writing the game's own 1 / 50 /
  99 over its 33 / 66 thresholds; **Throw style**, the low bit of **Scramble** (`+0x4F`) — the only
  bit test on any rating byte anywhere in `.text` (`and ecx,ebx` at 0x002D92B1), which picks the
  animation-set family and is believed, not proved, to be the throw motion — as a toggle that moves
  only that bit, beside a Scramble slider that preserves it; and **Kicking Style** (`+0x4B`),
  EXPERIMENTAL, with the three values retail uses. **Best Hand** (`+0x18` bit 1) is a checkbox on the
  Appearance tab. There is no other parity scheme hidden in the ratings: the scan is exhaustive.
- **The name pool is modelled honestly.** 65,120 bytes hold 5,094 strings with **zero** free bytes, so
  it cannot grow: the editor reuses an existing string (Finn's shared-name trick, and how you beat the
  rename limit), rewrites in place when the current string has no other user, reclaims what shortening
  a name frees, and otherwise **refuses** with the number of bytes it needed. Nothing is ever written
  outside the span the pool was discovered from.
- **Xbox saves, read and re-signed.** `EXTRA` = HMAC-SHA1(SigKey16, the whole `SAVEGAME.DAT`); the key
  is the literal Finn carries, and it is byte-identical to what the studio's own
  `nfl2k5_save_writer.derive_sig_key` computes from the retail XBE certificate (asserted by the
  tests). A save whose stored `EXTRA` does not verify is refused rather than quietly re-signed; a
  written copy rebuilds only `SAVEGAME.DAT` and `EXTRA` and copies `SaveMeta.xbx`, `TYPE` and the
  images byte for byte. Franchise arenas are found at their own `+0x2E0` offset.
- **Finn's tools, ported and improved.** Global Attribute Editor with his "show affected players"
  preview plus a condition he never had ("every QB with Speed ≥ 80 → throw style B"); Copy /
  Paste / Paste-attributes-only / Paste-photo under his rules; Advance Years Pro; Restore
  Height/Weight/DOB; a CSV twin that reads his semicolon export as well as ours; position chips;
  search by name, years pro or college; ↑ ↓ depth reorder on the team's own pointer list.
- **Build & Share**: `BuildPlan.roster_edits` applies a roster-edits document
  (`2k5_mod_studio_roster_edits/v1`) to the ROST resource of the copy, **last** of the roster passes —
  it writes named record fields and shared name strings and leaves `+0x2C`, the season-stat pool, the
  generated-name pool and the `+0x53` star bit alone, so the star-tag, team-history, prospect-name and
  position-pool gates all stay intact (asserted by a test on the retail roster). Share detects the
  edit between two discs, rebuilds the document from the rosters themselves and packs it as an asset.
- Unwitnessed in game.

## v1.0 RC82 — the community list: Free Practice in Franchise, Position on Edit Player, jerseys anywhere, penalties, prospect names, Pro Bowl order, laces, the star; overtime and Models UV fixes (2026-09-04)

- **Fixed: modern overtime ended after a first-possession field goal** because the kickoff after
  a score is built (and its receiving team marked as "has possessed") in the same dead-ball pass
  that applies the score, before the post-play evaluator judges the scoring play; the evaluator
  then saw the opponent as already having had its possession and ended the game (Noah, 2026-09-04,
  Situation OT1 0-0, field goal, "game ended"). The receiving team of a kickoff is now only
  *pending* until the kickoff has been played, the Situation screen's game seed clears the
  possession flags (it never runs the overtime kickoff builder), and unicorn tests replay the
  exact scenario through the real score/kickoff/evaluator code: first-possession FG -> play on
  and the other team receives, tying FG -> sudden death, second FG -> game over; first-possession
  TD + PAT -> play on; safety -> game over. Same two caves (`nfl2k5_overtime.py`, 287/300 and
  216/233 bytes), one new 5-byte hook in `FUN_0010bd80`. Unwitnessed in game.
- **Position on the first page of Edit Player, in roster mode and in Franchise.** Create Player's own
  Position picker (17 positions, ratings kept, overall recomputed from the new position's weights)
  now sits after Last Name on both Edit Player screens; Franchise opens the same screens, so a
  position change no longer means a new player. Two 28-byte `.rdata` row-list edits
  (`nfl2k5_position_row.py`). Run Depth Chart -> Auto afterwards. In every preset. Unwitnessed.
- **Pro Bowl Votes tabs in football order.** Offence, defence, then K and P (retail put the kickers
  between the linemen and the defence). One 17-pointer list (`nfl2k5_probowl_order.py`); the vote
  scanner reads each tab's own position and no other screen shares the list. In every preset.
- `nfl2k5_rdata_sites.py`: the shared retail-pin / status / apply / digest-repin helper those two
  and future fixed-span `.rdata` patches use.
- **Penalties at NFL rates + a working Chop Block toggle** (`nfl2k5_penalties.py`, advanced and
  experimental presets; `BuildPlan.penalties = "nfl"`). Every penalty slider drives a hidden
  `.rdata` curve table read through the game's interpolator (`FUN_001b0ae0`); seven of the nine are
  re-knotted in place (offensive/defensive holding, clipping, roughing window, late-hit window, face
  mask, ineligible downfield; DPI hazard/radius and the NZI zone kept) so the default 50 lands near
  NFL 2024 per-team-game rates while 0 still means none and 100 keeps the retail extreme. The
  incidental face mask (idx 25) becomes 15 yards. The Chop Block On/Off toggle, dead in retail
  because idx 9 and 10 share the Clipping-slider case of the enable pass (`FUN_000b1440`), is wired
  through a 10-byte stub (`mov eax,[0xE60064]; jmp 0xB1558`) hosted in the dead `FUN_000b4a60`
  (zero references in the retail image; both cave gates pass) -- note retail profiles carry Chop
  Block **Off**, so switch it On in Penalty Settings. **The rates are ESTIMATED** pending a
  calibration playtest (the engine has no calls-per-game number; see the getting-started recipe).
  Illegal formation, illegal contact and 12 men on the field do not exist in the engine, so no
  patch can add them. 141 bytes over `.text`/`.rdata`/`.data`; unicorn-proven interpolator and
  enable-pass runs; unwitnessed in game.
- **Home/away jerseys at any stadium** (`nfl2k5_uniform_choice.py`, `BuildPlan.uniform_choice`).
  Retail decides the colour once per game load with one rule (home dark, visitor white; the
  Cowboys white at home and navy in Washington/Tennessee) and only lets you pick the era. The
  `choice` form (ADVANCED and EXPERIMENTAL; off in BASIC) rewrites the 97-byte rule block, the four
  era handlers and the slot reset in place: up/down past the last available era on Controller
  Assign or Team Select flips that side's colour and restarts at the first era, so each side
  cycles 15 eras x 2 colours with no new button; the retail default stays the default and both
  teams may choose white. Two flip words live in the writable `.rdata`/`.data` gap beside the
  7-on-7 flag and clear with the era slots; no cave. The `rule` form (opt-in) is the same block as
  `mov esi,0` + NOPs: home always dark everywhere, Cowboys included. Practice, Xbox Live and the
  Team Select preview art are not covered. Unicorn-proven on the real routines; unwitnessed in game.
- **Laces to the posts on field goals and PATs** (`nfl2k5_kick_laces.py`, `BuildPlan.kick_laces`;
  EXPERIMENTAL preset only, opt-in elsewhere until witnessed). The held ball's orientation is not a
  constant: `FUN_001ccfa0` samples the holder's animation ball track every frame, so the hold clip
  decides where the laces point (the kickoff tee is a code constant, `.rdata` 0x50D9A0, and already
  faces the target). The patch hooks the six-byte join point of the three held-ball orientation
  paths at 0x1CD3FB (`mov edx,[esp+0x14]; mov ecx,[edx]` -> `call cave; nop`) into a 143-byte cave
  in the dead `FUN_002979f0` (0x2979F0; zero references in the retail image, both cave gates pass):
  `pushad/pushfd`, live play (`[0xE602B8] == 0xE`) and the offence's chosen formation being the
  Field Goal formation (the `[[[0xE60280]+0xC]+8]` chain with the -4 sentinel guard, flags bits 8-13
  == 12, as the kick-rules PAT fixer reads it), then the ball quaternion at transform +0x20 is
  multiplied in place by a 16-byte roll constant kept in the cave through the game's own
  `FUN_003ca150` (`q <- q x r`, Hamilton order), default `(0, 0, 0, 1)` = 180 degrees about the
  ball's long axis (`(w,x,y,z) <- (-z, y, -x, w)`), so the laces swing from the kicker to the posts;
  `apply(..., roll=ROLL_90)` writes the 90-degree variant into those 16 bytes without touching the
  code. 78 bytes of code, writes only through `esi`; `popfd/popad`, the two instructions replayed,
  `ret`. Punts, kickoffs and scrimmage carries are not the Field Goal formation and stay retail; a
  fake field goal carries the rolled ball for that play only. Unicorn-proven on the real bytes
  (rolled on live FG, untouched on other formations / dead ball / the -4 sentinel, registers, flags
  and stack transparent); unwitnessed in game.
- **Modern draft-prospect names** (`nfl2k5_prospect_names.py`, advanced and experimental presets;
  `BuildPlan.prospect_names = "modern"` or a CSV path; disc images only). Retail names every
  generated rookie and free agent from the 1990 US Census lists (James, Harold, Walter... Smith,
  Garcia, Martinez): two independent uniform draws over a 485 + 485 pool in the roster template
  (ROST body: entry array 0x72FB4, UTF-16 strings 0x8B7D0..0x8EB86), so a fifth of every class
  carries a Hispanic-origin name and none reads like a 2020s roster. The pool is rewritten inside
  its own 13,238 bytes from `data/nfl2k5_modern_names.csv` (nflverse-data 2015-2025 rosters,
  CC-BY-4.0; `tools/nfl2k5_modern_names_generate.py` reproduces it): the 433 surnames the announcer
  has recorded stay at their index (the audio id is 9300 + index) and keep their call-out, the 52
  Hispanic-origin and developer slots take modern surnames (Diggs, Chubb, Kamara...) and every
  first name goes modern. A 27-byte cave on the generator's audio-id store (hook 0x2BE7B8; host =
  the tail of the dead `FUN_000b4a60` at 0xB4A70, beside the penalties stub) keeps 9300 + index for
  surname pointers below the layout's boundary and writes 9100 (no recorded cue: the announcer
  falls back to the jersey number) for replacements. The boundary is baked from the CSV, so
  `inspect` reports `applied` only with both halves present and agreeing (`partial` otherwise) and
  the build refuses a mismatch. Correction to the study: the 272 zero bytes before the pool are the
  empty names of the 68 spare player records (136 relative pointers land there), not free space, so
  the budget is the retail span. Custom lists: `first,last`, 485 rows, `index` optional, ASCII up to
  12 characters, within the byte budget; the receipt logs every slot as kept or replaced. New
  franchises only (a save carries its own roster copy). Unicorn-proven hook (retained pointer ->
  9300 + index, replacement -> 9100), both cave gates pass, order-independent with the other
  executable patches; unwitnessed in game.
- **Free Practice inside Franchise** (`nfl2k5_franchise_practice.py`, `BuildPlan.franchise_practice`;
  ADVANCED and EXPERIMENTAL presets, opt-in in BASIC until witnessed). Retail Practice exists only
  under Game Modes on the main menu, picks two random teams and has no way in from a franchise, and
  the Coach's Desk (descriptor `.rdata` 0x522190) has no spare row: its eleven rows run Schedule ..
  Quit and the type-3 terminator at 0x52215C ends exactly where the descriptor begins. The patch
  relocates the desk's 52-byte event-hook list into a cave (the same six `(event, record)` pairs
  with event 5 last, since the dispatcher `FUN_0006E4E0` scans for the first matching event), which
  frees precisely one 0x34 row slot at 0x521EEC, writes a **Practice** row there (type 9, label =
  the retail UTF-16 `L"Practice"` at 0xE9C3BC, always visible) and moves the descriptor's row
  pointer back one row, so Practice is the first row and the eleven retail rows follow unchanged.
  The row's activate stub is the tail of the retail Front Office callback `FUN_00142910` (start the
  fade, set the deferred next screen `[0xAA2408]`) pointed at a **clone of the Scrimmage Settings
  descriptor** in the cave -- byte-identical to 0x501834 except its own hook list (Team Select still
  on event 0xB) and its own START handler. The clone's event-1 stub runs retail `cb_00148AD0`
  (Practice Type 0, the `s32` practice field) and then `FUN_000C4D70`, the game's own "the team the
  user coaches" (`[0xE5775C]` -> `FUN_000C4C50`), and puts that team on **both** sides through
  `FUN_00077AE0` / `FUN_00077B20` at Practice Type = Full Scrimmage via `FUN_000E33F0`, so mode 1
  fields your first-team offence against your first-team defence in your away kit against your home
  kit, with the live franchise roster (there is one roster object, `[0xB72918]`, and the franchise
  load already overwrote it). The START stub is `FUN_00148B50` with **one** pop instead of two,
  because the franchise entry is one push deep, so a rep ends back on the Coach's Desk. 352-byte
  cave at 0x1D82D0 (eleven dead type-tag predicates; no branch target and no aligned pointer in any
  of the 23 sections lands inside), 100 bytes of code, four tables, **no mutable state and not one
  retail instruction byte changed**; no resource or pack change. Practice is mode 1 and the stat,
  clock and injury paths are gated on mode >= 4, so a session writes no season stats and no
  injuries, and the season state is only touched by franchise setters this path never calls.
  Unicorn-proven on the real bytes (both team globals and both playbook names = the coached team,
  Practice Type and the mode word set, retail practice untouched with no coached team; the START
  stub pops once where retail's pops twice); both cave gates pass, order-independent with the other
  executable patches. **Unwitnessed in game** -- the Coach's Desk has never been seen drawing a
  twelfth row, and a mode-1 game ending inside a franchise context has never been witnessed.

- **★ Models: texture coordinates now follow the game's own per-mesh rule.** Beta 56
  decoded every model's UVs with one fixed formula (`u = (n + 1) / 2`, `v = (1 - n) / 2`,
  "verified on the referee"). The game does not. Every NFL 2K5 vertex shader that routes
  register 6 to a texture coordinate computes `oT0.xy = v6.xy * c[-89].xy + c[-89].zw`, and
  `c[-89]` is four floats the draw path loads from each SHAPE record at `+0x30..+0x3C`
  (Su, Sv, Ou, Ov), right beside the proved position scale/offset at `+0x10`/`+0x20`
  (`movaps xmm0,[esi+0x30]` at VA 0x245B9 beside `[esi+0x10]` at 0x245FD). The exporter
  now writes `TEXCOORD_0 = n * S + O` per mesh with **no V flip** (Sv is positive on every
  shape sampled). 242 of 282 stadium shapes tile (S up to 12), so seat rows, crowd,
  concrete and ad boards had collapsed onto one repeat and were mirrored: that was the
  "scrambled stadium textures" report from the community Blender add-on. The referee's own
  constant is (0.81, 1.24, 0.55, 0.18), so the model the old rule was "verified" on was wrong
  too; the fixed rule was the S = O = 0.5 special case plus a flip that merely looked
  plausible on a striped shirt. Import inverts through the same constant (`(uv - O) / S`); a UV
  edit outside `O ± S` widens that mesh's constant one axis at a time, exactly as positions
  widen theirs, and the report says so; UVs stay off by default on import. Each mesh's extras
  carry `nfl2k5_uv_scale` / `nfl2k5_uv_offset` and a `texcoord_decode` block, the file
  carries `nfl2k5_texcoord_contract`, and the README lists each mesh's tiling.
- **Models exports speak the Stadium Studio contract.** Every material, texture and image
  carries `nfl2k5_texture_id` (`nfl2k5.stadium.o3610.c0004.scene4175.texture0002`; the scene
  number is the resource's position among the disc's SCNE resources, the Stadiums page's own
  enumeration; other models use their name in place of `stadium`), images are named after the
  first material that maps them, materials carry `nfl2k5_mapping_status`, and meshes,
  primitives and nodes carry the `source_*` extras the Stadium Studio and the add-on read
  (`source_shape_index`, `source_material_index`, `source_material_name`,
  `source_submesh_index`, `vertex_attribute_descriptors`, `position_decode`). The root node is
  `nfl2k5_units_centimetre_to_metre` and the file-level `nfl2k5_unit_contract` and
  `nfl2k5_texture_contract` blocks are written. A stadium exported from ★ Models and edited
  in Blender is accepted by the Stadiums page's texture write-back. The id format and keys
  now live in `nfl2k5_models.py`; the Stadium Studio imports them. The Stadiums page's own
  export is unchanged (positions only, copied byte for byte from the private cache, so no
  cache re-derive); its contract note now records the proved UV rule and points at the Models
  export for a UV-bearing file.
- **Vertex colours no longer darken the export.** The D3DCOLOR lane is the game's baked
  lighting (mean 155/255; the shaders multiply it into the texture). Written as `COLOR_0`,
  Blender multiplied it into every material's base colour and textures looked dark and
  blotchy. The lane is now the custom attribute `_NFL_COLOR` (VEC4 float, r g b a in 0..1),
  which Blender imports as a FLOAT_COLOR attribute without touching the material, and it
  comes back through import for exactly matched vertices (an unedited file writes nothing;
  new checkbox "Write vertex colours from the file", on by default). The export box gains
  "Bake vertex colours into COLOR_0" for the darker in-game look. A `COLOR_0` coming back
  from Blender is never read.
- Export schema `nfl2k5_model_export/v2`. Tests in `tests/mod_editor/test_nfl2k5_models.py`:
  the shader-rule transform, its exact inverse under real constants, per-axis widening, the
  D3DCOLOR codec and the contract ids without a disc; with the private extraction, the
  referee and a stadium scene export `TEXCOORD_0 == n * S + O` against the raw lanes with the
  full contract, an unchanged export re-imports to the original quantised lanes exactly, a UV
  pushed out of range widens only U, and a painted vertex colour lands in the lane. Proof
  renders (Blender 4.0 headless): referee stripes, number patch and hat crest, stadium banner,
  goal-line numeral, SPORTSCENTER board, crowd and seat rows are right under the per-shape
  rule and wrong under the fixed one. Unwitnessed in game: no UV or vertex-colour edit has
  been played back on a console or emulator yet.
- **Star decal under the players you tag** (`nfl2k5_player_star.py` + `nfl2k5_player_tags.py`,
  `BuildPlan.player_star` / `BuildPlan.player_tags`; off in BASIC, on in ADVANCED and EXPERIMENTAL
  because with no player tagged it draws nothing). Retail already draws this star and the art is
  literally called `icon_controller_star` (`.string_` 0xE6C16C): `FUN_000f8e60` loads it as the
  models `controller` / `controller100` (`[0xBA28A4]` / `[0xBA28A8]`), `FUN_000f8880` puts an
  instance at a player's feet as a **world-space decal** (it adds x/z into the instance transform
  at +0x30 / +0x38 and colours it from the per-user `.rdata` table 0x4ED9A0), `FUN_000f9030` walks
  the on-field entity list `[0xE60268]` once a frame and appends the players who get one to a list
  at 0xBA2824, and `FUN_000f9320` draws them. The **only** gate on that append is `FUN_00075d40`,
  an 80-byte leaf. So nothing is authored: the patch is an **in-place rewrite of that one routine**
  -- 80 retail bytes out, 80 new bytes in, entry unmoved, **no cave and no hook** -- that keeps every
  retail answer and adds "or this player's roster record carries the studio's star bit", refusing
  once the star list is full. The tag is byte **+0x53 bit 0** of the 0x54 roster record: `entity+0x3C`
  **is** that record (`FUN_000fa270` stores it into the marker queue at 0xFA2CB and the consumers
  read its +0x14 as the name pointer, its +0x20 bits 3..9 as the jersey number and its +0x35 as the
  position code -- the studio's own record fields), and +0x53 is the second of the two bytes Bad_AL's
  NFL2K5Tool calls "padded by 2 zero bytes", zero in all 2,547 retail records. Four earlier
  candidates were checked and every one is live: +0x27 bit 0 is **contract length** (981 primary
  records set it; +0x0A/+0x24/+0x26/+0x27 are the contract block and +0x08 the Player Type flags,
  per the Flying Finn V4 RE), +0x26 bit 0 and +0x08 bit 0 the same way, **+0x23** is bits 24..31 of
  the live dword at +0x20 (an 8-bit field at bits 22..29 with a getter at `FUN_000be290` and a
  setter at `FUN_000be2a0`, plus flag bits 30 and 31), and **+0x24 bit 7** is its own copied one-bit
  field that retail data actually sets. The decisive evidence for +0x53 is the game's own
  field-by-field player clone at 0xC16CD..0xC1DDB: it names every field of the record from +0x00 to
  +0x51 and never names +0x52 or +0x53 (a test pins this). The **9-entry clamp is not optional**: the list is 0xC bytes an entry with a byte count at
  0xBA2821 and `FUN_000f9030` flushes `[0xBA2820, 0xBA2820 + 4 + count*0xC)` at 0xF92E3, which with
  9 entries ends exactly at the next global (0xBA2890), so the tag path refuses at 9 while retail's
  own answers are never clamped. The rewrite is a leaf with no push, no pop, no call and no memory
  write at all (its last act is a tail `jmp` to the pure `FUN_0017ebd0`, whose 0/1 return is the
  retail answer); both cave gates and the memory-write gate pass, and unicorn runs the real bytes to
  prove retail-identical answers for untagged records over eleven entity states, 1 for a tagged one,
  a null record pointer never dereferenced, and the clamp at 9. Tagging is a **★ Star** checkbox
  column in Text & Rosters -> Current Roster Players (primary pool only: those are the records the
  on-field entity points at) which the Build tab reads as `player_tags`; the writer rewrites only
  those pad bytes in the ROST resource of the copy, runs last of the roster passes and leaves the
  team-history, reclassify, schedule and prospect-name digests intact. Side effect by design: the
  same predicate gates the on-field name/number indicator in `FUN_00075d90`, so a tagged player gets
  that too when Player Indicator Text is on. Tags need a disc image and reach franchises **created**
  from the copy. Unwitnessed in game.

## v1.0 RC81 — Update now: the studio updates itself on every platform (2026-09-03)

- **Update now.** When a newer release exists the banner and the Help menu's
  Check for Updates dialog offer **Update now** next to the old **Get the update**
  link. The studio downloads the release file that matches this copy, checks it
  against the SHA-256 the release published (a mismatch is discarded, never
  installed), and then:
  - **Windows installer** (the Setup.exe layout): starts the new installer
    silently with `/S /WAITPID=<pid> /RELAUNCH /D=<install folder>` and closes.
    The installer waits for the studio to exit before it touches a file,
    installs over the same folder, and reopens the studio.
  - **Unpacked release folder** (the tarball on Linux, macOS, or Windows): unpacks
    the new version beside the folder, swaps the two so shortcuts keep working,
    keeps the old one as `<folder>.previous`, starts the new version and closes.
    If the folder is held open (Windows, started from the .bat) the new version is
    placed beside it under the release's own name and the banner says where.
  - **A git checkout** is never updated in place; it only gets the link.
- The update runs off the GUI thread with progress in the banner; a failure is
  one sentence in the banner and the old copy is untouched.
- The first-run disclosure now says what the check does and that nothing is
  downloaded on its own. Nothing starts without the user pressing the button
  and confirming.
- Installer template: `.onInit` implements `/WAITPID=` (SYNCHRONIZE wait, ten
  minute cap) and `.onInstSuccess` implements `/RELAUNCH`; both are inert when a
  person runs the installer by hand. Proven under Wine 9: the install held until
  the waited process exited, then `runtime\pythonw.exe` started; the control run
  without `/RELAUNCH` started nothing; a dead pid does not hang.
- New module `mod_editor/core/self_update.py`, shipped in both studios; tests in
  `tests/mod_editor/test_self_update.py` (install-kind detection, asset choice per
  product and layout, sidecar verification, tarball swap + fallback, hostile
  archive refusal, the banner flow off the GUI thread).
- **TEAM column on the franchise Player Card.** A new executable patch (Build tab, Gameplay
  Patches page, both SOFTDRINK presets; `.2k5patch` carries it) adds a frozen TEAM column next to
  Yr on the Player Card's season-by-season stats. The current season shows the live team; every
  season rollover records the team the player finished the season with (field 87 of the game's own
  per-player history stream, written through its own writer), so past seasons show that club from
  then on. Seasons that ended before the patch was in the save, the folded "pre" row and the Total
  row read "--"; a mid-season trade shows the season-end team. Six column lists get the new
  pointer in place; the caves live in the unused tail of the dead `FUN_00046ee0` (0x47220..0x47420).
  Unwitnessed in game; the caves run under unicorn in `tests/mod_editor/test_nfl2k5_team_column.py`.
- **Real team history for the roster's past seasons.** The Build tab's "Real team history" toggle (ADVANCED and
  EXPERIMENTAL presets; disc images only) writes the real club of every past season the retail roster carries stats
  for into the roster template's own history pool (field 87, `data/nfl2k5_retail_team_history.csv`, generated from
  nflverse-data, CC-BY-4.0: 1,148 of the 1,325 retail players with history matched, 5,068 of 5,867 season rows, 86 %;
  5,042 rows land in the pool, 36,866 -> 41,908 of 50,000 dwords). Only franchises created from the copy show it; a
  user CSV (last_name, first_name, birth_date, season, team) replaces the built-in data and rides in the `.2k5patch`
  as `assets/text/`. Relocated franchises show the 2004 abbreviation (Oilers -> TEN, LA Raiders -> OAK). The pool
  writer runs after the position-pool and 2026-schedule passes. Unwitnessed in game.
- **Boot logo kept decodable.** Several executable patches keep code and constants in the XBE
  header's boot-logo bitmap (0x10A10..0x10CC2). The game never reads it, but the kernel draws it during
  the boot animation, and a bitmap full of code decodes to nonsense (a user's investigation of a
  freeze at the Xbox logo flagged exactly this). Whenever a cave has taken the bitmap the builder now
  copies the retail logo into the header's zero padding (0x10CD0) and points LogoBitmapAddr at the
  copy, so the kernel decodes the genuine 100 x 17 logo; the caves are untouched.
  `mod_editor/core/nfl2k5_boot_logo.py`, reported as `boot_logo` in every XBE status.
- **Disc names always end in .iso.** A save name typed without a suffix in Build or Apply produced a
  file xemu's picker could not see; a bare name now gets `.xiso.iso`.
- **In development, not in this release: 7-on-7 practice.** A fifth Practice Type that plays 7-on-7
  sets from the practice playbook is built and tested (executable patch, book writer, three runtime
  bugs found and fixed through xemu's debugger: a flag in read-only `.text`, menu links without
  bit 15, a cave over a live function). It reaches the play-call but has not been witnessed through
  a snap, so it is hidden in this build (`mod_build.SEVEN_ON_SEVEN_RELEASED`).
## v1.0 RC80 — ★ Models: export any model to Blender and back (2026-09-03)

- **New: ★ Models.** Every 3D model on the loaded disc (players, helmets and face
  masks, balls, referees, coaches, cheerleaders, crowds, props, the Crib, menus,
  trophies, stadiums; 4,616 scenes, listed by name in about a second) exports as a
  glTF 2.0 file that opens in Blender: triangles, normals, UVs, vertex colours,
  the embedded textures the game draws it with, a skin with the game's joints for
  every animated model, morph channel names, and a vertex-index lane. A README
  beside each export says what can change.
- **Import an edited glTF/GLB.** Move vertices freely and bring the file back:
  the game's vertex count, triangles, bones, weights and every other byte are
  kept; positions (and normals / UVs for exactly matched vertices) are re-encoded
  into the game's fixed-point lanes, the encodable range is widened when an edit
  needs it, Blender's re-ordered or split vertices are mapped back through the
  index lane (or by order / nearest vertex with a warning), the resource is
  rebuilt into its retail span with the wrapper untouched, and a COPY of the disc
  is written with the pack located through the disc's own directory. The report
  says exactly what changed before anything is written.
- The disc reserves a fixed compressed size per model; the importer packs with an
  optimal-parse VC-LZ encoder that beats the game's own packer by 0.4 to 1.3
  percent, which is the headroom an edit needs. Very heavy edits can still exceed
  it and are refused with the arithmetic.
- Not yet: adding or removing vertices or triangles, new bones or animations, and
  body-type / face morph deltas (channels are listed, not editable).

## v1.0 RC79 — every archive pack found through the disc directory (2026-09-03)

- **Fix: Build → Advanced on any dump of the disc.** A legal USA retail `.iso`
  laid out differently from the rip this studio was developed on (a raw dump
  with the video partition in front, or an image rebuilt by another ripper)
  failed the 2026 season step with `pack-0 schedule template is foreign: ROST
  stored size is not retail` while Basic built fine. The schedule step and
  every other pack writer read `vc_53450030/<pack>` at a byte offset measured
  on one image; they now resolve the pack through the image's own file table,
  exactly as `default.xbe` always was. Disc detection locates the game
  partition instead of assuming it starts at byte 0.
- The ESPN scorebug status no longer aborts the Build panel on machines
  without the developer-only retail scene file; it reports "not available".
- Verified with identical Advanced builds from the retail rip, a redump-style
  image and an extract-xiso reordered image, also with the POSIX-only `os`
  members removed (the simulated-Windows check).

## v1.0 RC78 — Build & Share with the SOFTDRINK patch presets (2026-09-03)

- **New: ★ Build & Share → Build.** One checklist builds a patched COPY of a
  disc image (or `default.xbe`) with every executable, text and presentation
  patch, and three buttons tick a preset first: **Basic** (the 2004 game plus
  the 2K5 fixes: throw ceiling 80 with realistic flight, real Catching and
  Interception sliders, draft and free-agency AI with the Rookie Report rule,
  real returners, kicking power to ~70 yards), **Advanced** (everything modern:
  EDGE, modern kicking 35 / 35 / PAT 15, modern overtime, acceleration ramp,
  progression, arc by distance, the ESPN scorebug, scheme labels, one-pool
  positions with corrected team ratings, the Far-look camera, the 2026 franchise
  with a three-game preseason and rookie birth years) and **Experimental**
  (widescreen hor+ and the dynamic-kickoff line-up). A preset ticks only what
  the source can still take and reports what it skipped.
- **New: Share tab.** `.2k5patch` export, inspect, check and apply: byte runs
  plus your source assets and a recipe, every run SHA-verified against the
  bytes it replaces before anything is written.
- **New: Audio → Sounds and Commentary.** Replace any game sound across every
  sub-bank from a WAV (export, fit line, verify); swap a commentary line.
- Throw Distance & Arc: the arc-by-distance lob-speed table now keeps the
  retail short-game points exactly (relocated 8-point table).
- Every patch is pattern-checked against retail, written to a copy, read back
  and receipted; xemu-only, like every executable edit.

## v1.0 RC77 — Create a Formation / Create a Play, Play Designer, Throw Distance & Arc (2026-09-02)

- **New: ★ Create a Play (last navigation entry).** A five-step wizard: pick
  a playbook, lay out a formation on a field canvas (modern templates; drag a
  player to move him, click to swap or change his position — RB2 instead of
  the FB, a WR instead of the TE), choose run or pass, draw routes by dragging
  from a player or pick a job from his menu, then replace outdated stock plays
  and build. Under it, the Play Designer and Design Formation panels edit
  assignments from the game's own route/block/coverage opcodes. The PLAY
  resource is decoded end to end — eleven 14-byte formation slot records in
  signed centimetres, 29 node opcodes with bit-exact operand encoders (round
  trip on all 91,833 stock nodes), and the retail validator (chain grammar,
  side nibble, feature byte, ball-possession simulation, handoff pairing)
  ported so nothing the game would reject is ever staged.
- **Fixed: authored passes no longer play as QB draws.** The game plays a play
  as the class in its header word (bits 12–15: pass / quick game / run, plus
  play-action, trick and specials bits — 139/139 stock ATL offensive plays
  obey it). The wizard now picks its donor and header from a stock play with
  the same QB-chain shape and writes `play_flags` end to end (writer, facade,
  build validator, Playbooks panel, designer, wizard); bits 0–8 must stay the
  donor's or the build is refused.
- **New: Throw Distance & Arc workspace (Sliders & Gameplay → Throw Distance
  && Arc).** NFL 2K5 caps every throw at a distance that is a curve of the
  passer's effective arm strength, read from five `count + (x, y)` float
  tables in default.xbe through one interpolator; deep balls are forced lobs
  and the accuracy pass re-clamps the target to the bullet curve (55 yd at 99
  arm in retail), then the launch is an exact ballistic solve with no velocity
  cap. Two sliders re-shape those tables on a COPY: the deep-ball ceiling
  (55–100 yd, scaled so a 70 arm gains ~2 yd at 80 while a 99 arm gets the
  full 80) and the pass arc (slows the last 25 yards of the ceiling so long
  balls hang and climb; 40 % at 80 yd is a 5.0 s, 33-yard-high bomb). The
  panel reads a default.xbe or a disc image, previews ceiling / hang / apex
  per arm live, refuses to write when the sliders already match, and verifies
  by read-back and byte diff. Witnessed in xemu with gdb breakpoints on the
  clamp and launch: retail launches pinned at 55.0 yd; the tuned copy launched
  80.0-yard, 5.00-second balls. `tools/nfl2k5_throw_distance.py` is the CLI
  (`read`, `sliders`, `curves`, `preview`).
- The browse-only facade shown before a disc is loaded now implements the
  extended Playbooks contract; the formation/play writer test file gained the
  `unittest` entry point CI's per-file runner needs.

## v1.0 RC76 — Windows binary-open hotfix for the bump workspace (2026-08-24)

Beta 51's new file paths opened disc images, extracted packs, XBE copies and
raw HDD images with `os.open` but without `O_BINARY`. POSIX ignores the flag;
Windows opens such descriptors in TEXT mode, where reads stop at the first
`0x1A` byte — silently truncating payloads (the synthetic uniform fixtures hit
this at byte 58 of the pack). Every `os.open` in the bump-map writer, the
bump-strength writer, the save writer, and the coach-name tool now carries
`getattr(os, "O_BINARY", 0)`, matching the long-shipped uniform-color patch
route. A new AST guard fails any future `os.open` in these modules that drops
the flag. No behavior change on Linux/macOS; the Bump Maps, Bump strength, and
Saves & Sliders workspaces now work on Windows exactly as they do elsewhere.

## v1.0 RC75 — bump maps, bump strength, saves & sliders, stadium glTF loop, speed (2026-08-23)

RC75 is the biggest 2K5-side release to date: four new native workspaces or
routes, all retail-free and fail-closed, plus an editor-wide speed pass for
projects with hundreds of edits.

- **New: Jersey Bump Maps workspace (Uniforms & Equipment → Bump Maps).**
  Every one of the 634 uniform packages carries four tangent-space bump maps
  (bump_jersey, bump_pants, bump_sleeve, bump_sock). The new panel browses
  them from the entry tables (no hardcoded offsets), exports any slot to PNG,
  previews a replacement before/after, and writes it into a COPY of the disc
  image at the exact retail footprint: box-filter mip chain, NV2A swizzle,
  VC-LZ recompressed into the fixed span, wrapper preserved except the
  loader scratch word, then independently re-decoded and verified. The
  retail image itself is browse/export-only and is recognized by full SHA.
- **New: cross-extent uniform packages are editable too.** Three retail
  packages (outers 3625, 3832, 4136) cross a pack boundary and were
  previously refused. Reads and writes are now segmented at pack boundaries
  while still touching only the exact span, so all 634/634 packages are
  first-class.
- **New: bump authoring templates.** One click writes a flat-normal starter
  PNG at the slot's exact size with the retail collar/shield UV zones
  outlined and labeled on bump_jersey (front V-neck band, NFL shield tab,
  back round collar) — the positions the retail art actually uses, graded
  honestly in the metadata.
- **New: bump strength editing.** The per-material detail-scale floats that
  control how strong each bump renders live in default.xbe (jersey 0.1,
  pants 0.3, sleeve shares jersey's float, sock fixed 0). The Bump Maps
  panel now finds those sites by byte pattern, reads them, and patches a
  COPY of the XBE with the touched section digest recomputed and byte-diff
  confinement verified. Honesty: the RSA signature cannot be regenerated,
  so patched XBEs are xemu-only, and sock stays read-only (its retail
  encoding has no room for a float).
- **New: Saves & Sliders workspace.** The settings block proven at RAM
  0xE5FF80 (the first 0x2E0 bytes of Settings1 and Franchise1 saves) is now
  editable: all 21 gameplay sliders (Human/CPU Blocking..Catching plus
  Injury, Fumble, Interception) with editable/mirror/consistent write modes,
  and the Franchise1 year field for franchise saves. Output is always a
  COPY: a mutated SAVEGAME.DAT plus a fresh 20-byte EXTRA signature
  (HMAC-SHA1 with the title-static key derived from your own default.xbe),
  verified at load by the game. A CLI (read/edit/writeback) covers the same
  lane, including write-back of a save container's extents inside a copied
  raw Xbox HDD image, which refuses saves whose stored EXTRA does not verify.
- **New: stadium glTF texture loop closed.** Stadium scenes already exported
  to glTF with every game texture embedded (tagged by canonical texture id)
  and re-imported same-topology vertex moves. Now the edited glTF's images
  come BACK too: Apply textures from glTF maps each Blender-edited image to
  its stadium texture slot (by id, falling back to material name) and writes
  it through the same fixed-allocation P8 route the Stadiums page uses.
  Export → edit in Blender → apply back, entirely in the GUI.
- **Speed: hundreds of edits no longer re-parse the world.** Identity-keyed
  memoization (path + device + inode + size + mtime) now caches the bump
  index volume parse, the retail-image probe verdict, the outer-archive
  parse used by every texture adapter, the 55MB uniform-inventory load plus
  an O(1) (outer, chunk) row index, the compatibility-report digest, and the
  large-file digests the helmet/nameplate/face/field-art/portrait importers
  recomputed PER EDIT. Per-edit structural cost drops to O(1) after the
  first edit; measured ~0.9-2s per edit → sub-second across 30 edit-shaped
  cycles, with deterministic cache tests instead of wall-clock asserts.
- **Flexibility without losing fail-closed guards.** Patched-XBE and
  edited-save outputs can now be re-generated in place with an explicit
  overwrite confirmation; same-file-as-source writes, retail-image writes,
  and unverified saves are still refused outright.

## v1.0 RC73 — Create Formation / Create Play, authorized end to end (2026-08-21)

The clone-based creation writer that shipped quietly in RC54-RC56 is now a
first-class, capability-authorized, project-persisted feature, and it gained
two bounded Stage-2 steps — all inside the proved empty capacity of the fixed
0x13390 PLAY bodies (317 empty formation slots and 739 empty play slots
corpus-wide; nothing relocates or grows):

- **Create Formation / Create Play** are authorized kinds
  (`play_formation_create`, `play_create`) in the unified backend and the
  capability registry, so projects that stage creates now Build instead of
  being refused at the provider gate.
- **Custom names (optional):** a created formation or play may carry a
  1-40-character printable-ASCII name appended to the name pool's verified
  zero tail; the pool count word at 0x1083C is checked against the retail
  invariant (37/37 books) and kept consistent. Donor-name reuse remains the
  default.
- **List Play in Formation** (`play_formation_link`): writes one play index
  into the formation's first empty 0x1FF menu slot so a created play is
  actually callable; the selection group inherits the formation's existing
  slots (or an explicit 0-3). Group-bit gameplay semantics remain unproved
  and are labeled as such.
- **One-pass composition:** creates, links, and stock route copies for one
  book compile against a single intermediate body into one pack-0 slice.
- **Projects persist creates and links:** Save Project writes
  `playbook_creates`/`playbook_links`; load re-validates per book through the
  writer before staging. No silent drops.
- Honesty: registry and panel copy state that runtime visibility of created
  formations/plays is not captured (no emulator gate in this release),
  freehand node synthesis stays refused, and the XBE is never touched.

## v1.0 RC72 — jersey digits that fit (2026-08-21)

Community report: "can't edit numbers in 2k5." The number *values* were
always editable; the digit *art* imports were refusing typical authored
sheets on the tightest retail VC-LZ spans. Root cause, same family as the
2K8 digit finding shipped in APF alpha.79: the mip chain was built with a
channel-box average, and averaging two flat region colours mints a blend
colour that is not in the artwork. The blends spend palette entries and
index entropy, so the compressed stream stops fitting fixed spans that the
same art fits with region-clean mips.

The digit/nameplate mip filter is now a region-majority downsample (majority
colour wins each 2x2 footprint; ties go to the rarer region, so thin
outlines survive). The palette ladder, fixed-span rebuild, and every gate
are unchanged; the importer manifest now names the filter. Measured on the
retail proof chain: the four Detroit fixtures compress from 12,084 changed
bytes to 11,684, and a thin-outline digit that overflowed its span under
box mips now fits (pinned by
`test_box_mips_spend_the_span_on_blends_the_majority_filter_saves`).

Also closed a stale-fixture hazard: the retained 32x1024 nameplate PNG stays
as the pinned historical proof input, and the pipeline now consumes the
generator's corrected 1024x32 atlas from
`reports/assets/nfl2k5_live_numbers_nameplate_fixtures/current/`, so the
live-art XISO proof chain runs green end to end again.

## v1.0 RC71 — Beta 47 identity (2026-08-21)

Identity-only bump: Beta 47 ships the shared desktop-shell fixes and the APF
alpha.80 surfaces; the 2K5 editing surface is unchanged from RC69. The
updater reports beta-47 and the packaged runtime closure re-pins.

This is the modder-facing record of functionality that is actually present in
runnable builds. A mapped resource is not listed as editable unless its product
writer is connected to Replace, Revert, project save/load, and the composed
build path.

## v1.0 RC69 — updater identity beta-46 — 2026-08-15

- Shared updater identity is `beta-46`. No 2K5 writer or importer changed.
  The Playbooks repair, raw-export withdrawal, and APF packaged-import closure
  check in this tag are APF-only.

## v1.0 RC68 — updater identity beta-45 — 2026-08-15

- Shared updater identity is `beta-45`. No 2K5 writer or importer changed.
  Field Art extras, jersey numbers, jersey capacity, and the G12 pack in this
  tag are APF-only.

## v1.0 RC67 — updater identity beta-44 — 2026-08-14

- Shared updater identity is `beta-44`. No 2K5 writer or importer changed.
  The Fine-tune Plays, empty-formation, and build-folder work in this tag is
  APF-only.

## v1.0 RC66 — Check My Images, and a camera map — 2026-08-14

- **New: Check My Images.** Sits directly above Build. Runs the real quantizer
  and the real encoder against the real slot contract for every staged image and
  reports, per slot: fits as authored, will be reduced to N colours, or will not
  fit. The palette ladder added in Beta 41/42 is lossy and used to happen
  silently; this is how you find out first. It changes nothing and starts no
  build.
- **The `sleeve` slot contract was wrong and is fixed.** It had been modelled as
  512x256 with six mips like the torso; the real slot is 128x128, five mips,
  with a 64-byte gap between the clean and mud palettes. Contracts are now
  derived from the importers themselves and cross-checked at import time, so a
  typed table cannot drift from the code that writes the bytes again.
- **Jersey numbers: do not paint them into the art.** The torso, sleeve and
  pants slot copy now says so. 2K5 draws numbers from separate digit textures in
  the same uniform set — Jersey and Arm digits at 64x64, Helmet digits at 32x32,
  and a 1024x32 nameplate atlas — so numbers baked into the jersey appear twice.
- **The nameplate atlas is 1024x32 horizontal**, not 32x1024 vertical. The
  transposed value came from a TXTR descriptor bug fixed long ago in the decoder,
  and three user-facing places still carried it.
- **New: `--inspect-camera-options nfl2k5`.** Seven named settings with their
  shipped ranges and six named presets. Camera Distance is a dimensionless
  multiplier and Camera Height is world units; only Camera Angle is 0..1. The
  three sliders only move the camera while the preset is set to Custom — that is
  how the shipped game works. Read-only: the values live in a signed save.
- **The published slider snapshot was mislabelling 12 of 18 entries.** The save
  stores each slider vector in its globals' address order, where Catching is
  last, not the menu's display order, where it is fourth. If you read a slider
  value out of this tool before, re-read it.

## v1.0 RC65 — pants too, and a test that finds the next one — 2026-08-13

- **The pants importer was missed in Beta 41 and is fixed here.** Building a
  pants replacement still refused with `pants: VC-LZ stream needs more than the
  75472-byte bound`. Beta 41 wired the palette ladder into live helmet, jersey,
  scorebug and create-team field art but not pants, because the sweep that
  found the offenders was truncated and the resulting list was then hard-coded
  into the test that was supposed to guard it — so the test agreed with the
  omission. Pants now uses the ladder like its siblings.
- **That test now derives the set from the tree instead of trusting a list.**
  Anything that compresses into a bounded VC-LZ span and still quantizes at a
  flat 256 fails the suite, so a missed or newly added importer cannot inherit
  this bug by being forgotten.
- **A failing edit is named by the coordinates it was picked by.** Beta 41's
  message said only `pants:` — a uniform edit carries no selector, so the label
  fell back to the bare kind. It now reads
  `pants (asset_code=NE, side=home, variant=0)`.

## v1.0 RC64 — a fixed VC-LZ span fits the art down instead of refusing — 2026-08-13

- **A texture that will not fit its retail compressed span is now quantized
  down instead of failing the build.** Building could refuse with
  `VC-LZ stream needs more than the 34416-byte bound` — 34,416 is a live
  helmet TXTR — and the message named no team, no slot, and no image.

  `quantize_levels_to_vc_lz_bound` has shipped for a while: it tries palettes
  from 256 down to 2 and returns the first that fits, which is what the sleeve,
  digit, all-texture and Crib importers already do. Four importers that
  compress into a bounded span still called the plain 256-entry quantizer and
  hard-failed: live helmet, jersey, scorebug, and the compressed create-team
  field art. They now use the ladder. **The ladder starts at 256, so art that
  already fit is byte-for-byte unchanged**; only art that used to fail steps
  down. When even a two-colour version will not fit, the message says so and
  says what to simplify.

  The three P8 importers that write *uncompressed* fixed spans — team select
  card, player portrait, Crib team photo — have no bound to overflow and are
  deliberately left alone.

- **Every build failure now names the edit that caused it.** The dispatcher
  knew each edit's kind and selector and attached neither, so any importer's
  message stood alone in a build carrying dozens of edits.

  Reported against Beta 40.

## v1.0 RC63 — Team Kit equipment edits can be built — 2026-08-13

- **Swapping a sock, glove, shoe, wristband, elbow pad, or long-sleeve texture
  no longer breaks the build.** Build Modded XISO refused with
  `Unknown uniform asset ID: tset:3660:4:0:socks00`, and Save Project, Load
  Project, Import Team Kit, Undo's restore and Revert All refused the same way.

  Only the uniform *sets* live in the uniform catalog. The Team Kit's 45
  package-local equipment parts are `tset:` assets minted by the extended
  visual catalog, along with `p8:` textures, portraits, live faces,
  create-field art and the scorebug — 47,237 assets the build could not name.
  Staging worked because the panel hands `replace()` an already-resolved asset
  object; every later step re-resolved the ID string through the wrong catalog.

  Every one of those steps now resolves through `Nfl2k5ProductVisualCatalog`,
  the aggregate that was written for exactly this and never handed to a
  session. A uniform edit resolves to the identical object it always did, so
  jersey, helmet and digit edits are unchanged.

  Reported against Beta 39. The routing dates to the first public beta; it
  became reachable in RC49, when Team Kit gained the equipment parts.

## v1.0 RC62 — no 2K5 changes — 2026-08-11

- This release fixes APF 2K8 team-crest mip regeneration and adds a two-layer
  crest import to APF's Team Logo panel. Nothing in 2K5 changed; the version
  moves so both products keep shipping from one release.

## v1.0 RC60 — validation harness PATH isolation — 2026-08-10

- The capability validation harness put the discovered ripgrep's whole
  directory on its fixed PATH while asserting that directory holds exactly one
  command. That held when ripgrep came from `/usr/bin` and failed on any machine
  whose ripgrep ships in a shared vendor bin. It now exposes ripgrep through a
  private single-entry directory, so the invariant holds everywhere instead of
  only where it happened to already. Maintainer tooling; nothing user-facing
  changed in 2K5 this release.

## v1.0 RC59 — stadium caches recover instead of dead-ending — 2026-08-10

### Fixed

- **"Private Stadium Studio result marker is incompatible or incomplete".**
  Beta 30 rebound derived stadium assets to the canonical game-content identity
  instead of a container hash — the right fix — but every private cache written
  before that change then failed its own marker check with no way back. Anyone
  who had already opened Stadium Studio met this error on every launch, on a
  game that had worked, with the only remedy being to delete a private directory
  nobody had told them about.
  A cache this build cannot read is now treated as stale and re-derived
  automatically. Safety refusals are unchanged and still refuse: a symlink, a
  junction, or anything outside the private root is never removed automatically.

## v1.0 RC58 — findable stadium geometry + real xemu setup — 2026-08-10

### Stadium models

- **The editable stadium scene is marked and opened first** — Stadium Studio
  indexes 477 scenes, and exactly one of them carries the catalog-pinned
  geometry targets that Import can write. That scene now shows a ✎ marker and
  its editable-mesh count, the list opens on it instead of on row 1, and a new
  **Only scenes with editable geometry** filter hides the rest. Every other
  scene's tooltip says plainly that it is view and glTF-export only, so Import
  staging nothing is never a mystery.

### Emulator

- **Configure xemu** — the footer can now point the editor at your own xemu
  program, and the choice is remembered between sessions. The old tooltip told
  people to "configure xemu" when nothing in the app could do it.
- **xemu is re-detected while it is still missing** — detection used to run once
  at startup, so installing xemu because the editor asked you to did nothing
  until you restarted the editor.
- **Flatpak xemu can open builds outside home** — a Flatpak launch now grants
  read-only sandbox access to the built XISO's own directory. Without it, a
  build on an external drive failed with an I/O error that looked like a bad
  build rather than a sandbox refusal.
- **Launch Latest Build never silently grays** — it stays clickable and names
  the one thing that is missing (no build yet, no xemu, or a build that has
  since moved) rather than one message covering all of them; when xemu is the
  missing piece, clicking offers to choose it.

### Reliability

- A window opened against an already-loaded game no longer fails during
  construction: the shared status/progress footer is built before the pages that
  report into it.
- The update check refuses to advertise a release older than the running build,
  and reads the highest published beta rather than trusting list order.

## v1.0 RC57 — valid-container shared-cache repair — 2026-08-09

- **Valid ISO layouts share one verified cache** — once the USA retail game is
  recognized and its extracted packs and inventory match their independent
  pins, container padding and partition placement no longer create competing
  cache identities.
- **Stadium Studio loads across layouts** — its private result marker and worker
  now bind the canonical validated game content, fixing the incompatible or
  incomplete result-marker error raised after an otherwise successful load.
- **Original previews stay source-correct** — ordinary and extended visuals,
  Crib art, standalone audio, and streaming-range sidecars use the canonical
  cache binding. Intact legacy visual and Crib entries refresh safely; altered
  bytes and unsafe paths still fail closed.
- **Audio safety data is reusable** — exact PCM fingerprints and containment
  inventories use the canonical cache identity, and containment parses the
  actual opened container size instead of assuming one disc-image layout.
- **Build sizes are honest** — build validation, free-space budgeting, and the
  returned result use the selected container's actual size. Direct source-file,
  recovery, and session race guards remain tied to the exact selected file.


## v1.0 RC56 — crib drop-parity + never-gray G1/G2 — 2026-08-09

### Beta 29 refresh

- **Updater identity corrected** — RC56 now identifies its release channel as
  `beta-29`, not the stale `beta-22` packaging label, so manual and automatic
  checks no longer offer Beta 29 to an already-current Beta 29 build.

### Community / product

- **G2 multi-Ace link-table pack** — Export G2 multi-Ace pack… copies the Quads
  play-link (menu) table onto every Ace-named formation in a private PLAY + honesty
  JSON sidecar. Offline-writer-proved for menu bytes only; runtime TE→WR unproved;
  package maps/assignments untouched.
- **Release allowlist ships G1 + formation clone** — `playbook_package_rule_spike.py` and
  `nfl2k5_formation_play_writer.py` were imported by the product but absent from
  `packaging/release-allowlist.txt` (Windows stage would crash on Playbooks G1 export
  / formation clone). Staged file count 195→197; runtime closure + release gate green.
- **Crib drag/drop fit** — off-size JPEG/PNG drops open the same Contain/Cover/
  Stretch chooser as the Replace dialog (shared `_fit_crib_image` path). Drop-
  parity tests mock the chooser under offscreen Qt so the modal never hangs CI.
- **pytest offscreen default** — `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`
  so monorepo GUI tests do not hang waiting on a display/modal.
- **G1/G2 experimental exports never silent-gray** — Export Package-Map Copy /
  Link-Table Copy stay clickable with disableReason + click-to-explain when the
  XISO/book/formations are not ready (runtime still unproved).
- **Playbooks community legend**
- **Extended visual browsers**
- **Stadium surface textures** — Export/Replace/Revert never silent-gray.
- **Universal inventory raw Export** never silent-gray. — Export/Edit/Replace/Master/Revert never silent-gray (export-only assets explain).
- **Unif colour filter-empty** — facemask/turtleneck/Apply/Revert stay clickable. — G1/G2/G13 one-liners under the ⚠ filter;
  empty-state text when Community-flagged matches zero books.
- **Text & Rosters** — All-Text Apply/Revert/Export, Current Player Apply/Revert,
  Historical Team/Player Apply/Revert stay clickable with disableReason +
  click-to-explain (no-change, unit limit, read-only, nothing staged).
- **Audio Export matching** never silent-gray — shortlist/raw/count/pending
  walls teach on click (1–256 row bound still enforced).
- **Audio Load waveform** never silent-gray for Load/select/raw/bank walls
  (cancel-in-flight may briefly lock while finishing).
- **Audio shortlist bulk** — Add all matching / Add this page / Review / Export
  selected WAVs never silent-gray; blocked clicks teach via progress_label.
- **Audio shortlist Add/Remove selected** never silent-gray.
- **Audio replacement template Export/Import** never silent-gray (busy/Load/
  shortlist walls).
- **Audio row Play/Export/Replace/Revert** never silent-gray (Load/select/raw walls).
- **Audio shortlist Move up/down** never silent-gray.
- **Audio soundtrack quick-view** never silent-gray.
- **Audio copy pack path** never silent-gray.
- **Gameplay Inspector Export JSON/CSV** never silent-gray on inspection failure.
- **Menus & UI Export JSON/CSV** never silent-gray when the named Main Menu map
  fails to load — click teaches the wall (read-only inspector; no menu rewrite).
- **Text & Rosters Export Number** (current + historical) never silent-gray —
  empty selection teaches “select a player first.”
- **Stadium Studio surface Export/Replace/Revert** never silent-gray at
  construction (boot disableReason before first texture selection).
- **All Resources Previous/Next** never silent-gray (first/last/busy/Load walls).
- **Playbooks “G1: Use Nickel donor”** — one-click set package-map donor to
  a Nickel formation when present (offline G1 helper; runtime unproved).
- **Playbooks “Export G1 multi-Dime pack…”** — offline experimental: copy the
  Nickel package map onto **every** Dime-named formation in the selected PLAY
  book; private PLAY + honesty JSON sidecar; multi-region byte-diff verifier;
  runtime G1 still unproved; source ISO never mutated.
- **Audio Previous/Next** never silent-gray — first/last page, pending search,
  busy, and unloaded walls teach via disableReason + progress_label (clicks no
  longer look dead).

### Honesty

- Freehand routes still not Editable; G1/G2 still offline-bytes only.

## v1.0 RC55 — package-map writer, playbooks inspector map, crib UX — 2026-08-08

### Community / product

- **G1 package map (Dime ILB surface)** — o0308 census: assignment-only gate
  failed; primary offline delta is formation `+0x0D` 11-byte role permutation
  (Nickel vs Dime). `build_formation_package_map_patch` + independent verifier
  offline-proved for map bytes. Runtime G1 fix **unproved** — no one-click pack.
- **G2 Ace menu** — formation play-link table copy offline-proved (Ace←Quads
  class); experimental Export Link-Table Copy in Playbooks (private PLAY only).
- **Playbooks inspector** — read-only package-map line under Formation; Dime/Nickel/Ace honesty tags.
- **Crib import fit** — Contain/Cover/Stretch chooser on dialog + drop.
- **Crib model import/export** — click-to-explain when XISO or scene missing (no silent gray).
- **Stadium model Import/Export** — never silent-gray; `disableReason` + click explain.
- **Unif facemask/turtleneck/Apply** — never silent-gray; status teaches Load XISO /
  clear filter / wait for set load (per physical set).
- **Keyboard** — Esc clears search; Ctrl+/ keyboard hints (parity with APF shell).
- **Broken-play ⚠ Ace/Dime/Bear** — still annotations only; G1 map text updated.

### Honesty

- Package-map / link-table exports never mutate the loaded ISO and are not
  project staged as Editable gameplay fixes.
- Freehand routes still not Editable.

## v1.0 RC54 — playbook host clone stubs, stadium import reasons, stretch fit, broken-play flags — 2026-08-07

### Community / product fixes

- **Import fit chooser** — off-size dialog/drop imports pick Contain, Cover, or Stretch (not silent auto-cover).
- **G1/G2 package-rule** — layout pins + o0308 census in `playbook_package_rule_spike`;
  offline writers for formation package-map (`+0x0D`) and link-table copy **proved
  for bytes only** (runtime fix packs unproved).

- **Studio launch / Playbooks host** — `BrowseOnlyFacade` and `StudioFacade`
  expose formation/play clone methods so `PlaybooksPanelHost` isinstance checks
  pass (unblocks every headless Studio GUI test that constructs the main window).
- **Import edited stadium model never silent-gray** — export/import scene buttons
  stay **enabled**; tooltips + `disableReason` + click QMessageBox explain
  load-required / no-scene-selected / same-topology contract (no dead gray).
- **Import resize** — shared `image_fit` gains **stretch** (Contain/Cover already
  shipped); dialog + drop still share `_fit_for_slot`.
- **Playbooks Ace / Dime / Bear annotations** — formation/play names matching
  community package bugs show ⚠ tags and tooltips pointing at
  `docs/product/APF_GAMEPLAY_BUG_MAP.md` (annotations only; no fake auto-fix).
- **Facemask / turtleneck** — still per physical uniform set (Unif words 0/1),
  not global.

### Ledger

- Fix-or-wall tracker: `docs/product/S61_EDITOR_BUG_WALLS.md`.

## v1.0 RC50 — complete uniform fixes, menu/presentation logos, model tools, and release hardening — 2026-08-04

### Uniform-equipment discoverability

- **Socks and other package-local equipment are now directly findable from
  Team Kit.** Select a physical uniform set and choose **Browse 45 Equipment
  Textures** to open the existing All Textures browser filtered to its exact 45
  socks, elbow-pad, glove, long-sleeve, shoe, and wristband records. Searching
  within that list narrows the selected set. The route reuses the canonical
  asset IDs and existing Export, Edit, Replace, Revert, project, and Build
  handlers; it does not create a second writer or duplicate edit IDs.

### Crib textures and bounded model editing

- **All 498 catalogued Crib textures are Editable.** Coverage is 242 raw Team
  Item P8 textures (including all 128 Team Photos), 68 standalone P8 textures,
  and 188 material/submesh-owned P8 surfaces across 36 SCNE scenes. The writer
  preserves the reflection texture's 109,440-byte source gap, the ticker's
  1024x32 linear layout, every unselected allocation, and the fixed compressed
  span.
- **The Crib now has a Models tab.** It exports seven proved scenes and imports
  same-count, same-topology position changes for ten exact electronics meshes.
  UVs, materials, collision, indices, normals, other registers, commands, and
  opaque tails stay source bytes. Changed topology and arbitrary model swaps
  remain explicitly unsupported.

### Jersey numbers and stock play routes

- **All 2,547 current-player jersey numbers are Editable, including the 68
  secondary-pool players that previously errored or stayed disabled.** The
  writer patches only the masked number bits. Secondary names remain read-only
  because their text allocation is zero; the UI now enables each field from its
  own proved contract instead of locking the whole row.
- **Every current and historical player now has a Face shield control.** It
  authors only player word `+0x20` bits 15..16 with exact choices **None**,
  **Clear**, and **Dark**; reserved value `3` is refused. Jersey and face shield
  changes compose into one four-byte replacement, preserving every unrelated
  bit. This is a per-player equipment type, not a HOME/AWAY visor tint, and a
  loaded roster or franchise save may override the disc seed.
- **Playbooks & Plays can copy exact stock assignment routes within one PLAY
  book.** Choose a target assignment and a donor assignment, then stage or
  Revert the copy. The writer changes only the target descriptor word and
  relative pointer to the donor's existing node chain, reparses the full PLAY
  resource, and refuses orphaning or count changes. Freehand waypoint/opcode
  authoring remains unsupported.

### A1 player strips in All Textures

- **The twelve explicit-size `p001`…`p006` / `p011`…`p016` A1R5G5B5
  families are no longer blanket-refused.** The authenticated source contains
  340 copies of each name: 4,080 strips total. All remain searchable,
  previewable, exportable, and editable through the composed-XISO build.
- The writer regenerates all five linear mip levels, keeps the measured
  source-owned video tail byte-exact, preserves every descriptor and the
  complete resource span, and independently decodes the fixed-span VC-LZ
  rebuild. If native five-bit colour is too complex for the retail allocation,
  it tries deterministic four-, three-, two-, then one-bit-per-channel tiers
  before refusing with a simplify-art message.
- **The boundary target is complete too:** outer 581 `p005` straddles physical
  packs 0 and 1 as exact 53,888-byte and 21,008-byte slices. The editor builds
  one logical TXTR, stages both pieces before reserving a new output, verifies
  both source packs, writes only the fresh copy, reads each piece back, and
  reassembles the complete 74,896-byte chain for an independent final check.

### Audited boundaries: stock midfield and PCSX2 packs

- The exact standalone `center_logo` corpus is 126 create-team weather/logo
  packages at outers 384–509. The stock disc has no additional TXTR named
  `center_logo`. Its 85 `NN_teamlogo_00_h0` P8 rasters are not a safe midpoint
  substitute: the executable formats that name at `0x00142AF0`, loads it as a
  TXTR, and attaches it to the `FRANCHISE2` / `coach_desk` scene element named
  `teamlogo`. Stock midfield texture ownership remains unproved and the editor
  does not relabel franchise-office art as field art.
- The supplied `NFL2K27` tree is not a complete PCSX2
  replacement pack: it contains 5,688 directories but only four distinct
  Roman Reigns cyberface PNGs, copied into three locations, with no PCSX2 hash
  filenames or mapping manifest. There is therefore no source-owned mapping to
  automate into Xbox slots. High-resolution authoring and native Xbox fitting
  remain available, but cross-console hash mapping waits for the actual pack.
- NFL 2K3/2K4 discs or extracted packs are also absent. The shared container
  parser is not treated as proof that a 2K5 resource selector or byte extent is
  valid in either earlier game; source admission/build stays closed until each
  title has a pinned executable identity and independently inventoried writer
  targets.

### Bounded Stadium model import

- **Stadium Studio now imports edited glTF vertex positions.** Export the proved
  full scene, move vertices in Blender, keep the sidecar `.bin` beside the
  `.gltf`, then choose **Import edited model…**. The importer requires every
  bounded mesh to keep its exact vertex count and equivalent triangle set.
  Adding/removing faces, welding, subdivision, decimation, sparse accessors, or
  another mesh is refused before the session changes.
- Only the 75 catalogued fixed `FLOAT3` position lanes can change. Game UVs,
  materials, collision data, selectors, LOD/other streams, and the fixed opaque
  SCNE tail are kept from the user's source bytes. Stadium texture edits in the
  same scene are composed with the geometry edit before one VC-LZ rebuild, so
  their spans cannot overwrite one another.
- The position recipe stays in the private working session because it is
  derived from the user's game. It can build a local XISO and supports Undo and
  Revert All, but it is deliberately excluded from shareable `.2k5mod` files.
  Offline topology and byte preservation are proved; visible in-game runtime
  ownership is still labeled unproved until a matched capture exists.

### High-resolution authoring masters

- The Portraits & Faces, Create-a-Team Field Art, Scorebug Presentation, and
  All Textures browsers now expose **Save high-resolution authoring master…**
  after a dialog or drag/drop import. The non-overwriting `.2ktexmaster`
  preserves the exact original bytes, exact native staged PNG, source hash,
  final scale/cover geometry and Lanczos compile metadata, plus a direct 2x or
  4x original-source render. It is an authoring sidecar, not a larger Xbox
  texture or an emulator pack.
- Exact-size JPEG and non-RGBA PNG inputs now receive the same confirmed
  conversion path as off-size images. The source file stays byte-exact; the
  private staged copy is an exact-size RGBA PNG.
- Built-in pixel painting after an external import retains the original master.
  The archive stores the exact native pre-edit canvas and verifies a native
  raster-edit layer over the direct high-resolution render. A retail-only edit
  cannot enable this export because a shareable bundle must not contain
  source-derived retail pixels.
- Existing `.2k5mod` v1 projects retain native replacement PNGs only. Masters
  are explicit sidecars and are not reconstructed from downsampled project
  content. See `high_resolution_texture_authoring.md` for the exact coverage
  boundary and RPCS3 explanation.

### Complete menu, mini-card, franchise, and draft logo coverage

- **All 1,755 team-linked presentation surfaces outside the uniform packages
  are now first-class All Textures assets.** Coverage is all 317 full 256×256
  menu logos, 317 compact logos, 317 shared flip chips, 634 home/away mini
  cards, 85 franchise-office logos, and 85 draft/PDA logos. Together with the
  existing catalog this raises the standalone editable inventory from 9,640
  to **11,395** targets.
- The browser exposes **Team Logos — Menus / Presentation**, **Team Mini Cards
  — Menus / Presentation**, and **Franchise & Draft Presentation** as separate
  groups. Every row carries the exact team asset code, style and home/away set
  owners where applicable, archive name, and statically established consumer
  scope. Searches such as `Eagles`, `21H0`, `menu logo`, `mini helmet`, `coach
  desk`, and `pda logo` reach the intended family. Franchise team logos remain
  explicitly separate from midfield art.
- `logos.cdf`, `mini.cdf`, and `flipchip.cdf` are raw P8 fixed-slot arrays, not
  VC-LZ streams. Their importer preserves the wrapper, descriptor/system
  region, exact 66,720/5,280-byte resource span, and 96-byte zero slot padding;
  only the swizzled indices and 1,024-byte palette are regenerated. This removes
  false “VC-LZ stream needs more” failures for these menu assets. Franchise and
  draft logos keep the existing bounded compressed-P8 path. All 1,755 targets
  support Preview, Export, Edit, resized dialog/drag-drop Replace, Revert,
  project persistence, and composed-XISO Build.

- **The report was correct: NFL 2K5 keeps presentation art separate from live
  uniform art.** Every one of the 634 physical uniform packages contains four
  additional standalone textures: `logo` (128×128), `chiclet` (64×64),
  `splayer` (256×128 with five mips), and `flipchip` (64×64). Those 2,536
  records are not either live helmet diffuse, and they are not the three
  pre-rendered Team Select uniform/helmet cards.
- **All 2,536 are now explicit in All Textures.** Open the new **Team
  Presentation — Menu / UI** group, or search a team name, abbreviation,
  physical selector such as `21H0`, `menu logo`, or the exact resource name.
  Preview, Export PNG, Edit, dialog/drag-drop Replace, Revert, project save/load,
  and Build Modded XISO all use the existing fixed-span P8 route. The editor
  labels this as presentation/menu/UI art because `logo` and team-chiclet
  lookups are statically present but a complete screen-by-screen consumer map
  is not proved.
- **Small presentation spans now get the same bounded palette recovery as
  numbers and sleeves.** A complex Eagles `logo` fixture overflowed its
  6,656-byte VC-LZ budget at 256, 128, 64, and 32 colours, then rebuilt and
  independently decoded at 16 colours inside the exact retail span. Build now
  tries deterministic quality tiers before showing a useful simplify-image
  error; it no longer stops at the first raw “VC-LZ stream needs more” message.
- **Pack-boundary uniforms are covered.** An outer package may cross two
  internal pack files while the selected texture remains wholly inside one of
  them. The resolver now maps the texture's exact physical extent and refuses
  only an individual TXTR that actually straddles a boundary.

## v1.0 RC48 Audio Converter, Stadium Model Export, Update Check - 2026-07-30

- **Facemask/faceshield and turtleneck colours are truly per uniform now.**
  The previous control patched two fixed records and called them global; those
  offsets are actually Detroit current HOME (`09H0`) and AWAY (`09A0`). The
  Colours tab now has a searchable 634-set team/uniform selector. Each project
  row carries only that logical selector and the two authored ARGB values, and
  Build resolves it against the user's pinned source before replacing exactly
  one eight-byte record. HOME, AWAY, throwbacks, and alternate sets can all keep
  independent values in one project. Word 0 jointly controls facemask and
  faceshield; there is no independently proved visor field. Word 1 controls
  `HI_turtleneck`.
- **Socks and the rest of each uniform's equipment are editable now.** All
  28,530 package-local socks, elbow-pad, glove, long-sleeve, shoe, and wristband
  P8 references across 634 physical sets are searchable in **All Textures**,
  with preview, PNG export, built-in Edit, dialog/drag-drop Replace, Revert,
  project persistence, and composed-XISO build. Each TSET shares one retail
  shape/mip index chain, so an import changes only the selected palette and
  proves every sibling byte and decoded image stayed exact. Deterministic colour
  tiers keep the complete compressed TSET inside its original fixed span; a
  target that cannot fit a usable two-colour result is refused. Facemask and
  faceshield colour are not TXTR entries and remain in the per-uniform Colours
  control above.
- **Team Kit export no longer mistakes an old cache for tampering.** The exact
  report was “A private original-backup file changed outside Mod Studio.” Team
  Kit uses the uniform cache lane, while the first repair covered only the
  extended-visual lane. Both now distinguish internally valid stale metadata
  from bytes actually changed behind the app's back, regenerate old-schema or
  old-dimension entries only after a fresh decode succeeds, and preserve the
  old pair if that decode fails. Real changed bytes still fail closed.
- **Titans arm/shoulder numbers are present at their authored size.** Retail did
  not use one dimension per digit family: 380 arm-digit targets are 32×32, and
  200 helmet-digit targets are 64×64. The catalog now resolves every digit from
  the same compatibility row its decoder uses; `28H0`, `28H7`, and `28H8` no
  longer inherit a false 64×64 arm-number size. A real-source regression exports
  and revalidates all 33 reported surfaces: one sleeve and all ten arm digits in
  each of those three Titans packages.
- **All Textures export is exercised through the public router.** The Windows
  filename `p8:386:endzone_north_left.png` is still sanitized to
  `p8-386-endzone_north_left.png`, and a functional regression test now proves
  a `p8_texture` export reaches the extended decoder instead of the uniform IO
  that reports “Export is not implemented.” The exact DM transcription
  `p8:386:endzone_north_;eft.png` is also pinned; its illegal colons are removed
  without guessing that the legal semicolon was meant to be another character.
- **The reported 1,568-byte number/sleeve build error is fixed.** Small P8
  targets now retry deterministic palette tiers until the complete VC-LZ stream
  fits their original allocation, keeping the richest tier that passes. A real
  1,568-byte number target is compiled through the public project route, bound
  to the source XISO, and independently reopened and decoded after composition.
- **Any audio file can now replace a sound.** Drop an MP3, WAV, FLAC, OGG, M4A
  or similar onto an editable sound and it is converted to that slot's exact
  channel count, sample rate and frame count before it is written. Building a
  file to match by hand in an audio editor is no longer necessary. The drop zone
  states what the selected sound needs, and after a replacement the status line
  names what changed: resampled, trimmed to fit, padded with silence, or level
  lowered. Hover it for the full explanation.
- **Nothing external is needed for the codec itself.** All 850 of this game's
  sounds are Xbox IMA ADPCM, which is fully documented, so the encoder is part
  of the app. FFmpeg is used only to read your own file. A file that already
  matches the slot exactly is passed through untouched, byte for byte.
- **This was measured, not assumed.** All 849 authorable slots were converted
  from one ordinary source file, validated by the app's own strict parser,
  encoded and decoded back: 849 of 849 succeeded, signal-to-noise 32.34 dB
  minimum and 32.53 dB median. Typical IMA implementations land nearer 20-25 dB;
  the difference comes from searching every candidate start index per block
  rather than carrying the previous one forward.
- **Long sounds no longer stall the window.** That exhaustive search cost about
  110 seconds for a 30-second sound. It is now vectorised across blocks and
  candidates together, roughly 24 times faster, producing byte-identical output.
  The tests assert byte equality against the original encoder, not similarity.
- **Export model (glTF) on the Stadiums page.** The viewport could draw a
  stadium but offered no way to save it. It now writes the model and its buffer,
  and says where both landed, because the buffer keeps its own name and has to
  travel with the model. The export is scaled to metres: the game stores stadium
  geometry in centimetres, so an unscaled file opens about a hundred times too
  large and disappears past Blender's default view distance. No vertex is
  rewritten; the buffer is copied unchanged.
- **Update check.** Help now offers Check for Updates, an automatic-check
  toggle, and a link to the downloads page. When a newer release exists a strip
  appears at the top of the window. It never downloads or installs anything, it
  cannot delay startup, a failed check is silent, and dismissing one version
  does not hide the next. The first automatic check explains itself once.
- **Wider disc support.** Reading a disc image no longer aborts over an empty
  folder, a single accented filename, or deep directory nesting. Extent bounds,
  cycle detection and filename-separator rejection are unchanged.
- **Nameplate Atlas is exportable again** for all 634 uniform sets. Its
  compatibility report still carried a transposed 32x1024 dimension after the
  texture descriptor fix moved to 1024x32, so every set was refused. The atlas
  is a wide strip and its mip chain halves from 1024x32, so written the other
  way round the check could never pass. All 19,654 art resources now report
  compatible, where 634 were refused before.
- **An unexpected error now tells you what happened.** Previously the window
  simply closed: Qt ends the process when an error reaches it and no handler is
  installed, and the editor runs from an icon with no console, so nothing was
  shown anywhere. There is now a message naming the problem, stating that your
  original game files were untouched, and giving the path of a log file to
  attach to a bug report. The editor keeps running. A fault that repeats is
  logged every time but only interrupts once, so a problem in a redraw cannot
  bury the screen in identical boxes.
- **Odd and broken disc images are answered in words.** An empty file, a partial
  download, an archive renamed to .iso, a folder, or a file that has since been
  moved or deleted each get a sentence saying what was wrong. A file picked from
  a recent list and since deleted used to raise a raw system error.
- **A disc image reached through a symlink is recognised.** Keeping the image on
  another drive and linking it into a working folder is ordinary, but the
  identifier refused to follow the link and called it "not an Xbox game" while
  the recogniser accepted the same file. The two now agree.
- **A corrupt disc image cannot exhaust the reader.** A directory whose entries
  form one long chain rather than a balanced tree recursed once per entry and
  ran the interpreter out of stack, which surfaced as a crash instead of a
  refusal. The reader now counts every recursive step and refuses well before
  that. A balanced directory of the same size still reads normally.

## v1.0 RC47 Player Assets, Save Roster Import, Stadium Round-Trip — 2026-07-28

- **Player Assets** joins Rosters & Players. Search a player and see the face
  textures and portrait that belong to them. The face link is real — it comes
  from the `face_id` in the player's own roster record — and is labelled as
  such; a portrait is matched by name because nothing in the bytes ties a
  portrait number to a player, and that is labelled too. Equipment is listed
  once with a plain statement that NFL 2K5 stores it as five shared textures,
  so editing one changes it for everybody.
- **Roster names can come off a PS2 memory card.**
  `tools/nfl2k5_save_roster_import.py` reads a save's ROST arena and emits a
  project the normal build applies. A name too long for its fixed slot is
  skipped and reported rather than truncated, and capacity is measured in
  UTF-16LE because that is what the disc stores.
- **Stadium geometry round-trips through Blender.**
  `tools/nfl_stadium_gltf_roundtrip.py` turns an edited glTF into the recipe
  the proved position writer already validates. Proved end to end on the real
  disc: the retail 574-vertex roof raised five units, composed into a patched
  volume 9, 670 decoded bytes changed, topology and every unrelated stream
  preserved. It moves vertices; it cannot add or remove them, and it says so.

## v1.0 RC46 A Built-In Pixel Editor — 2026-07-28

- **Edit…** next to Export/Replace in every texture browser opens the slot at
  its exact retail size. Pencil, eraser, fill, eyedropper, a full colour picker
  with alpha, brush sizes to 64, zoom to 16x with a pixel grid, and 24 steps of
  undo.
- **The canvas has no resize control** — it *is* the slot's size — so what you
  save can never be the wrong shape. That round trip through another program is
  where a resaved 512×256 came back 513×256, or a crest lost its alpha.
- Transparency is drawn over a chequerboard rather than white, because an
  accidentally transparent crest is a black box on a helmet and you should see
  that before you build, not after.
- Nothing is written until you press Save; Cancel leaves the slot untouched.
- `tools/nfl_fit_image.py` does the same conversion from a terminal, one file or
  a whole folder at a time, for batches a dialog cannot reach — a directory of
  textures lifted out of another mod, for instance.

## v1.0 RC45 Images Get Resized For You — 2026-07-28

- New shared image-fitting layer, used by both editors. A texture slot occupies
  a fixed byte span so its replacement must be the exact retail pixel size, and
  that will always be true — but refusing the file instead of offering to fit
  it was our choice, and it stopped people at step one.
- Three fits, picked to suit the content: an image that is already exact is
  passed through **untouched**; a same-aspect image is resampled with Lanczos;
  and a different aspect either **pads** (crests and logos, keeping the whole
  shape on transparency) or **crops** (jerseys and field panels, where
  transparent bars would show in game as holes).
- JPEG, BMP, GIF, WebP and TGA are read as well as PNG, so a texture lifted
  from another mod or a photo does not need converting first.

## v1.0 RC44 The Facemask Colour Is A Colour Picker — 2026-07-28

- **You can pick the facemask colour in the editor now.** Uniforms & Equipment
  → **Colours & Other Tools** has two swatches, Apply and Revert. Word 0 of the
  `Unif` pair tints the facemask and faceshield; word 1 tints `HI_turtleneck`,
  which the game reads only when a player's two-bit selector is 3.
- It is a project edit like any other: it counts toward pending edits, Revert
  All clears it, it saves with the project, and it reaches the disc through the
  same composed **Build Modded XISO** as every texture and audio change.
- This release's control was later found to be global only in the UI: the two
  fixed records were Detroit current HOME and AWAY. RC48 replaces that route
  with one independently selectable record for every physical uniform set.
- **Repainting the coloured square on a helmet texture still will not move the
  facemask.** It is a separate material fed by this value — the difference from
  CFB 2K3 that started this whole thread.
- Ownership is proved by executable trace. A controlled in-game capture is
  still outstanding and the capability continues to say so.

## v1.0 RC43 All Textures Previews And Exports Actually Work — 2026-07-28

- **Export PNG failed with "The file name is not valid."** The suggested
  filename was the asset id, `p8:386:endzone_north_left.png`, and `:` is
  reserved on Windows. The old code only replaced `.`, which happened to be
  enough for every id that existed before. Suggested names are now sanitised
  for every character Windows rejects, plus trailing dots and spaces and the
  reserved device names, for **all** asset kinds rather than just this one.
- **The preview sat on "Preparing…" forever.** Every preview and export goes
  through a per-kind decoder dispatch that had no `p8_texture` branch, so it
  raised, the error was swallowed, and the loading text was never replaced.
  The decoder is implemented: it parses the retail descriptor and decodes the
  texture exactly as the writer does.
- **A preview that cannot be produced now says so** instead of spinning. That
  silent failure is the only reason this shipped looking like it worked.

## v1.0 RC42 All Textures Is A Workspace Now, And Its Edits Reach The Disc — 2026-07-28

- **All Textures shipped as a sidebar entry with nothing behind it.** It is a
  real workspace now: **3,024 targets** you can search, preview, Export PNG,
  Replace PNG and Revert, exactly like every other visual family. That is 1,770
  end-zone panels, 1,024 goalpost pads, 225 grass `divots` overlays and the
  five shared equipment textures.
- **The half that mattered: those edits now survive Build Modded XISO.** A new
  `p8_texture` edit kind runs through the composed build, is validated, refuses
  duplicate targets, and binds per-extent — the build locates each pack in your
  own image, re-derives the offset from where it actually lands, and verifies
  the pack hash and retail span before writing. A browser whose edits vanished
  at build time would have been worse than the bare card it replaced.
- Proved end-to-end on **three differently packed dumps of the same game** --
  the project's canonical `.xiso`, a reporter's repack and a reporter's
  pressed-disc read. All three composed two texture edits and changed an
  identical **31,652 bytes**.
- This corpus is separate from Stadium Studio's 23,838. That lane edits
  textures embedded *inside* SCNE scenes; these are standalone `TXTR` chunks
  sitting beside them. Outer 3136 carries five SCNE chunks and eight separate
  TXTRs; outer 853 carries ten TXTRs and no SCNE at all.
- **The Nameplate Atlas exported as gibberish and now doesn't.** `names` is a
  1024x32 horizontal character strip; the descriptor reader was transposing it
  to 32x1024 and shredding every letterform. Only `VC_P8_LINEAR` orders its two
  size halfwords that way, so the 4,081 `A1R5G5B5` player strips are untouched.
- **Stadium geometry export is command-line only and now says so.** The
  Stadiums viewport renders private glTF exports but has no save-to-file
  control, so pointing its card at that page would have been another
  overpromise. Whole-model *import* still does not exist: only same-count
  position writers across 75 pinned targets, and no topology importer.

## v1.0 RC41 The Uniform Browser Comes Back, And Cards Stop Overpromising — 2026-07-28

- **Fixes a regression RC40 introduced.** Splitting Uniforms & Equipment into
  two tabs put the uniform browser behind a tab bar that had no styling at all,
  so it rendered in the platform's light style with near-unreadable labels. The
  tab strip is now styled for the dark theme and **Uniform Sets is always the
  landing tab**. Rosters & Players had carried the same unstyled tabs since it
  shipped and is fixed by the same rule.
- **Capability cards no longer imply you can edit from them.** A card is a
  description with no controls; only seven of the nineteen writers have a real
  workspace in the app. Clicking through to the facemask colours and finding a
  paragraph with an "Editable" pill on it reads as a broken button, and it was
  reported as one. Each writer card now either names the workspace that edits
  it, or says plainly that it is command-line only **and prints the command**.
- Twelve writers are command-line only today, including the facemask colours
  and the new All Textures lane. That is the honest state, and the next builds
  are the workspaces that change it.

## v1.0 RC40 The Facemask Option Is Actually On Screen — 2026-07-28

- **The facemask colours were switched on and still invisible.** Uniforms &
  Equipment builds its uniform-set browser around one capability
  (`nfl2k5.uniforms.all_visual`) and silently dropped the other three filed
  under that category -- the facemask/turtleneck packed colours, the Team Select
  cards, and the Detroit away runtime proof. Enabling one changed nothing a
  modder could see. The category is now two tabs: **Uniform Sets** and
  **Colours & Other Tools**, the same shape Rosters & Players already used.
- **The window said RC36 while running RC38.** `mod_editor.__version__` is what
  the title bar renders, and three releases bumped the changelog, STATUS.md and
  the docs without touching it -- so nobody, including us, could tell from a
  screenshot which build they were on. It is now checked against STATUS.md and
  the newest changelog heading, so it cannot drift again.

## v1.0 RC39 Your PNG Editor's Normal Export Now Works — 2026-07-28

- **"needs an exact 512×256 8-bit RGBA PNG with interlacing off" was half our
  fault.** The importer accepted only colour type 6 at bit depth 8,
  non-interlaced. An image editor saving a jersey normally writes colour type 2
  (RGB, no alpha) or 3 (indexed), because those are smaller -- so good art came
  back rejected with a message that read like the user had done something wrong.
- Every colour type and bit depth the PNG specification defines now imports:
  RGB, RGBA, greyscale, greyscale+alpha and indexed, at 1, 2, 4, 8 and 16 bits,
  interlaced or not, with `tRNS` transparency honoured. Each is widened to RGBA
  internally, so nothing about the retail side changed.
- Decoding is verified pixel-for-pixel against Pillow across every variant.
- **The size rule stays**, because it is the disc's rule and not ours: a texture
  occupies a byte span its index chain has to fill exactly, so an image of a
  different size genuinely cannot go there. The message now says that instead of
  telling you to convert a file that was already fine.

## v1.0 RC38 All Textures, And The Writers Stop Demanding One Exact Disc — 2026-07-28

- **New workspace: All Textures.** 36,761 of the disc's 57,208 textures can now
  be replaced from a PNG. That covers the things modders kept asking for and
  finding absent: the real teams' end-zone art, goalpost pads, `divots`, the
  `mark1`..`mark3` overlays, and the shared equipment textures `shoes_taped`,
  `wristband_qb` and the three `elbowpad_*` variants.
- Replacements are recompressed into the **exact byte span** the original
  occupied, so nothing on the disc moves and an image that cannot be made to
  fit is refused rather than shifting resources around.
- Only compressed, swizzled P8 textures whose index chain starts at the video
  buffer and whose palette follows it are editable. A1R5G5B5, A8R8G8B8, DXT1
  and VC_P8_LINEAR are refused, and the capability says so.
- **Four writers stopped demanding one exact disc image.** The audio lane, the
  generic texture import, the Crib bar-monitor patcher and the uniform colour
  patcher each gated on the whole container's size and SHA-256 -- so a legally
  dumped disc that differed from the developer's copy could not be used at all.
  Identity is now per-extent (`default.xbe` plus each touched pack), the same
  correction the load path already had. Pinned sector numbers and absolute
  offsets went with them; both are artifacts of how a disc was packed.
- **The facemask colour is on by default.** It was exposed but disabled.
- Proved on three legitimately different images of the same game: the project's
  canonical `.xiso`, a reporter's repack, and a reporter's pressed-disc read.
  The same two edits produced identical change counts at three different
  absolute offsets.
- Still not runtime-proved: no emulator was started, so on-screen visibility of
  a replaced texture is untested. Transport and byte-exactness are proved.

## v1.0 RC37 The Facemask Colour Is Named — 2026-07-28

- **The two `Unif` packed colour words now say what they own.** They were
  presented as "packed colours" whose "visual semantics remain incomplete",
  which is why a modder reported that nothing in the editor reads a facemask
  colour. The executable trace had in fact already resolved them:
  **word 0 is the facemask/faceshield tint** -- it reaches the selected
  `FACEMASK%02d` player records and the `LO_FACEMASK` / `HI_faceshield`
  materials, and a dedicated `facemask` scene colours `bar_01..bar_03` after a
  fixed darkening transform -- and **word 1 is the `HI_turtleneck` tint**, read
  only when a per-player two-bit selector is 3.
- This confirms the reported behaviour: **repainting the coloured square on a
  helmet texture cannot move the facemask**, because the facemask is a separate
  material fed by this value. That differs from CFB 2K3, where the square does
  drive it.
- Ownership is proved by static executable trace. A controlled runtime capture
  is still outstanding and the capability says so; the rung did not change.
- No writer, pin or file format changed.

## v1.0 RC36 Exporting A Team Kit Folder Works On Windows — 2026-07-28

- **Export Team Kit as a folder failed on Windows for everyone**, with
  `[WinError 5] Access is denied` naming a temporary path, which reads like a
  drive or permissions problem rather than a bug in the app.
- The export built the folder under a temporary name and published it by
  reserving the destination with `mkdir` and then renaming the finished tree
  onto that reservation. That is a POSIX idiom: `rename(2)` there replaces an
  existing *empty* directory. **Windows `MoveFileEx` cannot replace a directory
  at all** -- documented, not a quirk -- so the second step always failed.
- It now publishes through `platform_compat.publish_no_replace`, which already
  existed and already knew the correct primitive per platform:
  `renameat2(RENAME_NOREPLACE)` on Linux, `renamex_np(RENAME_EXCL)` on macOS, and
  a plain `os.rename` on Windows, where refusing to overwrite is precisely what
  that call does for a directory. The no-clobber guarantee is unchanged: an
  existing destination is still refused rather than overwritten.
- **Also fixed, found in the same place:** the ZIP export published with a hard
  link. That is the right no-clobber publish on POSIX, but on Windows it needs
  NTFS, and an external drive holding disc images is frequently exFAT, where
  `os.link` fails outright. The same helper uses `os.rename` there.
- Guarded by a test that asserts the rule rather than the symptom: no shipped
  module may reserve a directory with `mkdir` and then rename onto it. It runs on
  any platform, which is the point -- the failure cannot be reproduced on Linux,
  where replacing a directory simply works.

## v1.0 RC35 Saving Works On Any Legal Dump — 2026-07-27

- **RC34 let you load and edit your disc; it could not save.** Building refused
  every image but the project's own, and the reason was layout rather than
  content.
  - **Sector numbers were pinned.** extract-xiso relocates files when it
    rebuilds an image: all nineteen files sit at different sectors in a pressed
    disc, in an extract-xiso rebuild and in a repack, while every file is
    byte-identical. Pinning the sector meant no other image could ever match.
  - **Absolute byte offsets were pinned.** `1,631,188,992 + pack_offset` is
    where pack 0 happens to sit in this project's rebuild; on a pressed disc it
    is somewhere else entirely, so every downstream read would have landed in
    the wrong place.
  - The Crib scene texture was read at a pinned absolute offset. It now locates
    pack `c` by name -- names do not move -- and derives the span from wherever
    that pack actually starts.
- Sizes and content hashes are still verified exactly, because those are
  properties of the game rather than of the image someone built. What is gone is
  only the requirement that a file sit where ours does.
- Verified by building real mods from a reporter's own two images: a
  7,825,162,240-byte pressed-disc read and a 6,300,958,720-byte repack, each
  producing an output the size of its own source. Same span bytes read from
  5,399,363,856 in one image and 5,661,790,480 in the other.

## v1.0 RC34 Every Legal Dump, All The Way Through A Build — 2026-07-27

- **A genuine disc read is finally accepted.** Three separate causes, each
  hidden behind the last, all found against a real user's ISO:
  - A raw disc read contains **two** filesystems -- the video partition at byte 0
    holding only a placeholder, and the game further in. The reader stopped at
    the first one it found, saw no `default.xbe`, and called the disc wrong.
    Partitions are now enumerated and the one containing the game is chosen.
  - A **pressed disc marks its files `0x80`** (NORMAL). The reader demanded the
    ARCHIVE bit `0x20`, which extract-xiso happens to set on everything it
    rebuilds. On a real disc that rejected every file, `default.xbe` included.
    A node is now simply a directory or a file.
  - The generated game index embedded its pack path with `str()`, which is
    backslashes on Windows and three more bytes once JSON escapes them, so the
    index could not match its own pinned hash.
- **Build works too, not just loading.** The build lane still required the user's
  container to equal the project's own rip in three places, so an image that had
  loaded, indexed and been edited was refused at the last step. Container
  equality is gone; every copy length now follows the user's actual file, and
  identity comes from the located game partition, its file count and
  `default.xbe`.
- Audio preparation, the stadium writer and the stadium build lane carried the
  same container pins and are fixed the same way.
- **Stadium Studio no longer depends on which zlib you have.** It pinned the
  bytes of a PNG it generates, and zlib-ng -- shipped as the system zlib on
  Fedora 40+ and openSUSE -- emits different but perfectly valid output. It now
  verifies the decoded pixels, which are identical everywhere.
- Verified against the reporter's own two images: a 7,825,162,240-byte raw disc
  read and a 6,300,958,720-byte repack. Both are recognised, both index fully
  (16 packs, index byte-identical to its pin), and both pass the build lane's
  source validation.

## v1.0 RC33 The Game Index Is Byte-Identical On Windows — 2026-07-27

- **Fixed the error every Windows user hit, whatever disc image they had:**
  "The generated game index did not match NFL 2K5". The index was written in
  text mode, and text mode on Windows turns every `\n` into `\r\n`. With
  2,289,506 newlines in it, Windows produced a 58,035,920-byte file where the
  pinned size is 55,746,414 — same game, same packs, different bytes. It was
  never possible for a Windows user to get past this step, and the message
  blamed their game when nothing about their game was wrong.
- Fixed as a class rather than a line: **38 text writes across 29 shipped files**
  now pin the line ending, so nothing generated by this product can differ
  between platforms again. The shipped surface is at zero unguarded text writes,
  enforced by a test.
- The index content is unchanged — regenerated from the same packs it still
  hashes to the pinned value, with zero CRLF bytes.

## v1.0 RC32 Find The Filesystem, And Import On Windows — 2026-07-27

- **A raw disc read is accepted now, whatever tool made it.** RC31 checked a
  *list* of four known game-partition offsets, which is the same mistake as
  checking one, only with four guesses — and a real user's rip was not among
  them, so it was still refused. The reader now **searches** for the XDVDFS
  header rather than guessing where it should be, confirming a candidate by
  requiring the magic at both ends of its sector and a root directory that fits
  inside the image. Offsets nobody here has ever seen now work.
- **Fixed the error that reached people who install rather than unzip:**
  `Could not catalog the game files: ModuleNotFoundError: No module named
  'nfl_outer'`. The product runs `tools/*.py` as subprocesses and those scripts
  import each other. Any ordinary Python adds a script's own directory to
  `sys.path`; the embeddable runtime inside the installer does not, because a
  `._pth` file defines the path outright. So this failed **only** on installed
  Windows copies — not from the tarball, not in CI, not from source. Every
  shipped tool now restores its own directory, and the `._pth` lists
  `app\tools` as an independent second guard.
- Both are covered by tests that need no game data and no Windows: one resolves
  partition offsets deliberately absent from the known list, the other launches
  every shipped tool with its directory removed from `sys.path`. The second one
  immediately found six tools a hand-written check had missed, including
  `apf_texture_patch` and `apf_roster`.

## v1.0 RC31 Any Legal Dump Of The Disc — 2026-07-27

- **Your own dump of ESPN NFL 2K5 is now accepted, however you made it.** The
  editor used to require a file whose size and SHA-256 exactly matched the
  project's own rip, and it looked for the disc filesystem at the one offset an
  extracted `.xiso` puts it at. Both are properties of a *container*, not of a
  game, so people holding perfectly legal copies were told their file "is not
  the supported NFL 2K5 Xbox XISO" or was not the USA version. Two real reports
  drove this: a full raw disc read of 7,825,162,240 bytes, and a repack of the
  same game 224 sectors longer than ours.
- The filesystem is now *located* rather than assumed. A game partition at byte
  0 (extracted `.xiso`) and at the XGD1/XGD2/XGD3 raw-read offsets are all read
  identically, and trailing padding no longer matters.
- Identity now comes from `default.xbe` inside the image. That is the game; the
  wrapper around it is not.
- **Nothing was relaxed about the bytes you edit.** The archive packs pulled out
  of your image are still verified against their pinned SHA-256s, the derived
  game index against its own, and every writer still checks the exact extents it
  touches before and after. Those cover the bytes that matter, which a
  whole-file hash never did. Eleven separate checks moved from "equals our copy"
  to "is the right game"; the guarantees they were standing in for are all still
  enforced.
- Loading is also much faster: recognition hashes an 11.9 MB executable instead
  of 6.3 GB.

## v1.0 RC30 Off-Linux Direct Uniform-Colour Copy — 2026-07-27

- Fixed `tools/nfl_uniform_color_xiso_direct_patch.py`, whose whole-XISO copy
  called the Linux-only `os.copy_file_range` inside `except OSError`. On Windows
  and macOS the syscall does not exist, and its absence raises `AttributeError`,
  which that clause never caught — so the portable `pread`/`pwrite` fallback the
  function documents could not run and the copy aborted instead. The syscall is
  now resolved before the loop, and the fallback is chosen rather than crashed
  into. On Linux the accelerated path is unchanged.
- No capability, pin, writer contract or editable count changed. This is the 2K5
  half of the same portability sweep that produced APF `0.1.0-alpha.35`; the
  shared guard is `tests/mod_editor/test_shipped_tools_posix_only.py`, which
  drives every shipped writer with the POSIX-only names deleted from `os` and
  needs no retail data to do it.

## v1.0 RC29 Project-backed Audio Cue Labels — 2026-07-20

- Added custom titles and multiline notes for every playable standalone cue
  and indexed streaming range. Labels are keyed by stable logical cue ID, so
  shared physical aliases may carry separate human meanings.
- Added immediate title/note search, a **Labeled only** filter, pencil-marked
  table names, original game-label/ID preservation, character counters, and
  per-cue Save/Clear controls in the Audio inspector.
- Added deterministic `audio-annotations.json` project persistence with exact
  manifest filename, size, count, and SHA-256 binding. Annotation-only projects
  are valid; legacy projects remain compatible.
- Added one-action Undo and Revert All coverage plus autosave recovery. Cue
  labels are counted separately from game edits and never enable Build or
  enter the canonical XISO provider document.
- Retained unsaved title/note drafts while browsing, paging, or changing Audio
  filters. Labeled-only controls now appear only for project-backed hosts.
- Carried custom titles, notes, and the preserved game/catalog name into local
  matching and shortlist ZIP manifests; playlists use the custom title while
  stable IDs and canonical payload paths remain unchanged.
- Made project import, mixed Revert All, and its Undo atomic across PNG, WAV,
  text, Stadium, Crib, and cue-label state. Disk-full or final handoff failure
  restores the prior manifest/ledgers and removes the disposable candidate.
- Bounded user metadata to 54,421 logical cues, 120 title characters, 2,000
  note characters, and 16 MiB of UTF-8 text. NUL/unsupported controls,
  Unicode format controls, duplicate JSON keys/IDs, rich-text interpretation,
  malformed metadata, undeclared members, and checksum/size mismatches are
  refused.
- No retail audio, decoded PCM, source path, physical offset, rollback byte, or
  game asset is stored in an annotation or annotation-only project.

## v1.0 RC28 Audio Pack Preview and Apply — 2026-07-20

- Replaced one-click Audio replacement-pack import with an explicit two-step
  **Preview → Apply** workflow. Preview fully validates the folder or ZIP,
  manifest/source binding, baselines, supplied file set, WAV shapes, origin
  authorization, current staged bytes, and shared physical aliases without
  changing the project, manifest, Undo history, replacement tree, or source
  XISO.
- Added a frozen, sanitized preview summary for modders: supplied, would-change,
  already-current, restore-original, unique physical change/restore, linked
  alias, and resulting Modified counts, plus a bounded list of readable change
  labels. An unchanged-only pack succeeds as a preview but offers no Apply.
- Bound confirmation to an opaque session-local token covering the exact pack
  member digest, schema, loaded source, session identity, and monotonic
  project/audio mutation revision. The token is hidden from result
  representation and neither the public preview nor the session retains ZIP
  paths, WAV bytes, private source hashes, or private member hashes.
- Apply reopens the chosen pack, snapshots caller-controlled WAVs privately,
  reruns every validation, verifies the preview token, and only then performs
  the existing single atomic Undoable transaction. A changed valid WAV, source,
  session, or project state is refused and requires a new Preview.
- Added the confirmation dialog's logical-versus-physical counts, explicit
  restore and linked-alias disclosures, first-change labels, Cancel/no-change
  paths, and worker-drain handoff so Preview fully finishes before Apply starts.
  The release candidate remains headless; no audible-runtime claim is added.

## v1.0 RC27 All Playable Audio — 2026-07-20

- Made **All Playable Audio (54,421)** the default Audio scope. Its canonical
  order is domain-prefixed and stable: all 850 standalone `AUDO` rows first,
  followed by all 53,571 indexed streaming ranges. Complete streaming banks
  and opaque raw containers remain in their dedicated scopes because they are
  not individual playable sounds.
- Added combined search, stable paging, family filtering, and one global
  **Modified** filter without wrapping or changing either row type. Search
  reuses the existing standalone/range metadata haystacks instead of retaining
  another 54,421 copies of searchable strings.
- Kept meaning-confidence honest: the 1/152/697 confidence groups remain
  standalone-only and are not partially applied to the mixed scope. Select
  **Standalone sounds** to use them.
- Added bounded matching export for 1–256 mixed results as current playable
  WAVs. Each record keeps its truthful retail-derived or user-replacement label;
  raw `.bin` export remains available only from the dedicated streaming-bank or
  indexed-range scopes.
- Preserved the frozen v4 **all-850 standalone** replacement-pack contract. RC27
  does not claim an all-54,421 template: streaming ranges continue to use
  per-row Replace or the existing 1–256 selected-shortlist replacement pack.
- Closed the release candidate headlessly: the complete cross-title suite
  passes **1090/1090**, the 2K5 slice passes **603/603**, the release-focused
  selection passes **122/122**, and the Audio/Crib/project lifecycle selection
  passes **40/40**. Independent adversarial review reports GO with no P0/P1
  finding. No visible desktop, pointer, audio device, emulator, or external
  player was used.

## v1.0 RC26 Read-only Audio Waveforms — 2026-07-20

- Added an explicit **Load waveform** view for all 850 standalone cues and all
  53,571 playable streaming ranges. It reads the selected sound's private
  current PCM16 WAV, including a staged replacement, without autoplay or any
  project mutation. Whole streaming banks and opaque raw containers remain
  honestly unavailable as single waveforms.
- Kept long sounds bounded: the reader retains at most 640 normalized envelope
  columns and samples no more than 1,024 frames per column. It opens only a
  regular non-link file, detects a WAV that changes during reading, and leaves
  the private WAV byte-for-byte untouched.
- Bound the waveform to the exact source, selection, and current audio content.
  Replace, Revert, batch import, project load, Undo, Revert All, selection
  changes, and source transitions invalidate both stale waveforms and playback,
  even when the logical asset ID remains the same.
- Added **Cancel waveform** with truthful limits: bounded sampling is
  cooperative, while an in-process source decode finishes before its now-stale
  result is discarded. Audio and Crib now share one mutually exclusive worker
  lane; global actions and sibling editors remain fenced until its owner drains,
  while the owning Audio page keeps waveform Cancel reachable.
- Added seven bounded-reader tests and seventeen shell-integration tests for signal
  edges, direct and visible action fences, close refusal, autosave deferral, and
  same-ID invalidation, then expanded the lifecycle matrix for Audio/Crib mutual
  exclusion and source/project/save/recovery/Undo/Revert-All completion order.
  The complete combined headless suite passes **1088/1088**, the current 2K5
  slice passes **601/601**, the release-focused selection passes **107/107**,
  and the final independent review is GO with no P0/P1 finding. No visible
  desktop, audio device, emulator, or external player was used.

## v1.0 RC25 Recoverable Audio Curation — 2026-07-20

- Made Audio shortlist **Clear** reversible. After clearing 1–256 selected
  sounds, the same control becomes **Undo** and restores every standalone cue
  and streaming range in its exact prior order.
- Keeps one deliberately bounded restore snapshot. A successful add/remove
  consumes it, and a successful source load clears it; searches, filters,
  exports, project navigation, and a refused source load do not. Clear/Undo is
  session-only and emits no replacement/project mutations.
- Preserved the 930-pixel Audio-toolbar contract. The compact visible label is
  **Undo**; its accessible name, tooltip, and progress copy carry the restored
  count and behavior. Longer count-bearing labels were measured and rejected
  because they widened the panel.
- Closed a failed-source-load lifecycle bug found during independent review.
  Because source loading commits transactionally, a refused replacement source
  now restores the still-valid old Audio page/actions (or the honest empty Load
  XISO state on a first-load failure) while the invalidated preview stays stopped.
- Six new headless tests cover browser/review Clear, mixed 256-sound exact-order
  restoration, no project mutation, undo expiration, current/pending old-query
  recovery, and first-load refusal. The complete headless/offscreen product
  regression passes **1034/1034**, and the focused Audio/UI/source-bound/
  packaging selection passes **118/118**. No visible GUI, audio device,
  emulator, or external desktop player was launched.

## v1.0 RC24 Applied Audio Search Results — 2026-07-20

- Bound every Audio catalog page to the exact source epoch, search text, scope,
  family, edit status, and meaning-confidence controls that produced it. The
  220 ms typing debounce can no longer leave page-wide actions attached to the
  previous result set.
- Immediately disables and independently guards **Add this page**, **Add all
  matching**, **Export matching audio**, Previous, and Next while a new search
  is pending. The counter says **Updating audio results…** until the refreshed
  page is actually installed.
- Keeps safe selected-row work responsive during that brief update: Play,
  Export, Replace, Revert, and **Add selected sound** still target the exact row
  that remains visibly selected.
- Stops a pending search timer when a filter, scope, Soundtrack quick view, or
  source transition performs an immediate refresh. Shortlist-review pagination
  remains independent and usable.
- Five new offscreen race regressions cover stale page-add, matching export,
  all-matching requery/warnings, pagination/selection stability, and automatic
  timer application; a sixth covers the fast type/erase round trip. The complete
  headless/offscreen product regression passes **1028/1028**, and the focused
  Audio/UI/source-bound/packaging selection passes **112/112**. No visible GUI,
  audio device, emulator, or external desktop player was launched.

## v1.0 RC23 Selection-Bound Audio Preview — 2026-07-20

- Bound every preview request to a monotonically increasing source/selection
  epoch and exact asset ID. A delayed preparation success or error from A can
  no longer act after A → B → A, and a source switch invalidates old callbacks
  even when the new game exposes the same asset ID.
- Centralized all effective Audio selection changes. Refreshing the same row
  preserves current playback; selecting a different row, leaving a result set,
  or resetting the source stops the controlled player and restores **Play**.
- Queued one-click playback for a newly selected row while the old controlled
  process finishes stopping, instead of requiring a second click or racing two
  processes. The queue also drains when the old process reports FailedToStart,
  whose Qt signal path has no later `finished` event.
- Removed the unowned desktop-handler fallback. Playback now uses only
  `ffplay`, `paplay`, or `aplay`, which Mod Studio can stop; if none exists, the
  UI gives an actionable install message. Preparation/start failures clear all
  pending preview state instead of leaving **Preparing…** stuck.
- Source loading invalidates Audio before its worker begins and disables the
  embedded Audio panel for the entire global blocking operation. Five new
  Audio lifecycle tests plus one shell-order test prove these transitions.
- The complete headless/offscreen product regression passes **1022/1022**, and
  the focused Audio/UI/source-bound/packaging selection passes **106/106**. No
  visible GUI, audio device, emulator, or external desktop player was launched.

## v1.0 RC22 Responsive Audio Toolbars — 2026-07-20

- Reflowed the five Audio search/filter controls and seven shortlist controls
  into two deliberate rows instead of two oversized single-row toolbars. Every
  control remains visible; no action moved into an overflow menu.
- Reduced the Audio panel's normal minimum-width hint from 1,442 to 833 pixels.
  A conservative worst-case state—256-result add/review/export labels and a
  full shortlist counter—fits at 930 pixels, within the main window's 932-pixel
  workspace at its supported 1,180-pixel minimum width.
- Added an offscreen geometry regression that pins every grid position, applies
  the longest labels together, and proves all 12 controls are inside the panel,
  non-overlapping, and at least their own minimum usable width.
- Kept Audio behavior unchanged: search debounce, filters, selection, shortlist
  order, exports, replacement state, and Build routes use the same controls and
  signal connections as before.
- The complete headless/offscreen product regression passes **1016/1016**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **100/100**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC21 Scrollable Audio Inspector — 2026-07-20

- Made the dense selected-sound inspector vertically scrollable while keeping
  the WAV drop target and Play/Export/Replace/Revert actions pinned below it.
  Long ownership lists can no longer push the actions out of reach.
- Preserved the complete technical truth. Names, exact IDs, format/WAV
  contracts, ownership and alias warnings, shared-slot owner IDs, and the
  all-850 replacement path remain unabridged and wrap without changing their
  copied text.
- Made the title, technical metadata, ownership details, action requirements,
  and pack path selectable by mouse and keyboard, with explicit accessible
  names for assistive technology.
- Reset the inspector to its top whenever the selected row changes, and reduced
  its bounded minimum width from 360 to 320 pixels. This checkpoint fixes the
  detail pane's constrained-height behavior; the separate single-row toolbar
  width is not claimed as solved here.
- The complete headless/offscreen product regression passes **1015/1015**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **99/99**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC20 Add All Matching Audio — 2026-07-20

- Added a separate **Add all matching** Audio action beside **Add this page**.
  It collects one complete 1–256-row filtered result across Standalone Audio or
  Playable streaming ranges while preserving canonical order and keeping
  already-selected IDs once.
- Made the critical reviewed-label workflow one action: **Meaning confidence →
  Reviewed labels (152) → Add all matching (152) → Selected shortlist (1–256)**.
  The exported v2 replacement template receives those exact 152 IDs in the
  visible shortlist order.
- Kept the operation atomic and session-only. The current search, scope,
  family, edit status, meaning confidence, stable count/order, row types, and
  unique IDs are rechecked before mutation; an overflow or changed/hostile
  result adds nothing and never touches project replacements.
- Complete streaming banks and raw BANK/ABNK/WBNK containers remain ineligible,
  and results above 256 ask the modder to narrow the filters.
- The complete headless/offscreen product regression passes **1014/1014**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **98/98**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC19 Audio Meaning-Confidence Filter — 2026-07-20

- Added a dedicated **Meaning confidence** filter to Standalone Audio with the
  exact v4 cue-map groups: **Menu Back route (1)**, **Reviewed labels (152)**,
  and **Provisional labels (697)**. This signal no longer has to be inferred
  from warnings or confused with the separate Editable/Modified status filter.
- Used the same public `standalone_runtime_meaning_status` contract for CSV
  generation, catalog-host browsing, and the product facade. Filtered counts,
  pagination, search, family/edit-status combinations, and matching collection
  export therefore resolve the same canonical rows.
- Disabled and reset the filter for streaming banks, indexed AUSB ranges, and
  raw universal containers, where the standalone meaning domain does not apply.
  Shortlist review temporarily disables it without losing the underlying
  standalone selection.
- Preserved the honest boundary: all 850 physical standalone slots remain
  Editable. “Provisional” means the human label/runtime caller is unproved; it
  does not mean the fixed writer target is approximate or unsafe.
- The complete headless/offscreen product regression passes **1009/1009**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **93/93**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC18 In-App Audio Pack Paths — 2026-07-20

- Added an **All-850 replacement pack path** card to every standalone Audio
  detail view. It shows the exact generic v4 destination used by
  `AUDIO-CUE-MAP.csv`, so modders can move from search/playback to authoring
  without manually finding the same row in a spreadsheet.
- Added a selectable path and keyboard-accessible **Copy pack path** action with
  **Ctrl+Shift+C**. Clipboard access occurs only after explicit activation;
  browsing, selecting, filtering, and paging never replace clipboard contents.
- Derived the path from the same canonical catalog order used by v3/v4 export.
  The UI receives only `replacements/NNN__selected-audio.wav`; it does not gain
  physical selectors, offsets, source fingerprints, or other private metadata.
- Kept the boundary obvious: complete streaming banks, indexed AUSB ranges, and
  raw universal containers hide and disable the standalone-only action. Their
  existing selected-shortlist/export workflows are unchanged.
- The complete headless/offscreen product regression passes **1006/1006**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **90/90**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC17 Human-Friendly 850-Sound Cue Map — 2026-07-20

- Added `AUDIO-CUE-MAP.csv` to the default **All standalone sounds (850)**
  authoring hand-off. Each canonical row now connects its generic replacement
  filename to the public Audio-browser ID, display name, family, duration,
  channels, sample rate, exact frame count, edit route, legacy membership, alias
  status, and honest runtime-meaning status. Modders no longer have to manually
  cross-reference 850 raw IDs before authoring WAVs.
- Introduced a dedicated v4 format instead of changing the shipped v3 contract.
  Direct complete exports without the new map still produce byte-identical v3
  packs; v1 legacy, v2 selected, v3 complete, and v4 mapped packs all import.
  The GUI chooses v4 for the one-click all-850 workflow.
- Made the CSV deterministic, UTF-8/LF, single-line, formula-safe, and read-only
  reference metadata. Import verifies its exact manifest path, schema, row
  count, SHA-256, canonical row order, columns, values, and 1/152/697 meaning
  status distribution before any WAV can change the project. Modders can copy
  the CSV outside the pack for personal notes; a changed or reordered in-pack
  map is refused rather than silently trusted.
- Kept the hand-off retail-free: the new map contains no WAVs, decoded PCM,
  physical offsets, source/private audio fingerprints, rollback bytes, or
  originals. The template still binds to the user's whole source XISO, missing
  replacement WAVs still mean “skip,” and all accepted changes remain one
  atomic Undo action.
- The complete headless/offscreen product regression passes **1005/1005**, and
  the focused audio/facade/GUI/packaging selection passes **83/83**. No GUI or
  emulator was launched for this checkpoint.

## v1.0 RC16 Complete 850-Sound Authoring Pack — 2026-07-20

- Made **All standalone sounds (850)** the default batch-authoring choice in
  Audio. One click now exports a complete metadata-only folder or deterministic
  ZIP for Menu Back plus all 849 fixed-AUDO slots; modders can fill only the WAV
  paths they want to change and import all true changes as one Undo action.
- Added a dedicated v3 pack contract instead of changing either existing
  format. The v3 route validates the exact canonical 850-row source order,
  unique logical IDs and underlying physical selectors, one Menu Back row,
  exact PCM16 contracts, the whole-XISO SHA-256 binding, and current-edit
  baselines. Public rows do not expose those physical selectors. Missing
  replacement WAVs mean “skip”; changed guide/manifest/order, unknown or
  duplicate rows, invalid WAVs, stale baselines, and extra archive members fail
  before the project changes.
- Preserved both older workflows. Legacy v1 remains the same frozen ordered
  153-cue format, while selected v2 remains an ordered 1–256-sound pack that can
  mix standalone cues with exact soundtrack, commentary, crowd, stadium, and
  presentation ranges. Whole streaming banks remain excluded from all three.
- Kept hand-off files retail-free by construction. An empty v3 template contains
  only `EDIT-AUDIO.md`, `audio-replacement-pack.json`, and the empty
  `replacements/` directory marker—never original WAVs, decoded audio, game
  offsets, private per-audio PCM fingerprint inventories, originals, or
  rollback bytes. It does include the whole-XISO SHA-256 needed to bind the
  hand-off to the user's own source. The clean 144-file release stage
  independently reproduces the all-850 manifest and reports
  `private_inventory=false` and `retail=false`.
- The complete headless/offscreen product regression passes **1001/1001**, and
  the focused audio/facade/GUI/packaging selection passes **79/79**. RC16 does
  not claim that provisional cue names are semantically correct or that every
  edited slot has been heard in-game; those 697 uncertain rows retain their
  prominent physical-slot/runtime-meaning warning.

## v1.0 RC15 Complete Standalone Audio Editing — 2026-07-20

- Promoted all **850 standalone AUDO sounds** to Editable. Menu Back keeps its
  separate fixed-target route; all 849 other rows use stable outer/chunk IDs,
  exact non-overlapping physical allocations, strict per-row PCM16 shape
  validation, deterministic Xbox IMA encoding, and the unified copied-XISO
  build path.
- Replaced the old hidden lock on 697 alias-related rows with an honest warning:
  the physical slot being changed is exact, but its provisional name, semantic
  cue identity, and runtime selector owner may be unknown. Matching names or
  decoded content do not collapse distinct spans or imply that another slot
  changes.
- Preserved old v1 replacement packs exactly. **Legacy 153-cue pack** still
  resolves only Menu Back plus the original 152 classified rows in the same
  order; **Selected shortlist (1–256)** can now author any of the newly unlocked
  physical slots alongside exact AUSB soundtrack, commentary, stadium, crowd,
  and presentation ranges.
- Updated the capability registry, Audio panel copy/accessibility, product docs,
  runtime closure receipt, and pinned provider closure to report 850 Editable /
  0 Export-only standalone rows. Complete raw streaming banks remain
  Export-only; RC15 does not claim recovered cue names, loops, gain/pan,
  priority, mixer ownership, or audible runtime consumption.
- The complete headless/offscreen product regression passes **993/993**. A
  compatibility regression pins the RC14 ordered 153-ID set to SHA-256
  `156c3a02e4ef27ee1a245a0946a3033575dc3d30872f1664b2adf1dfbd488ecc`;
  the public stage separately proves all 850 modern edit routes while preserving
  the legacy manifest/guide contract.

## v1.0 RC14 Roster Workspace Navigation — 2026-07-20

- Moved the complete current and historical name/number workflow to the place
  modders expect it: **Rosters & Players → Players & Numbers**. The same page
  keeps **Portraits & Faces** one tab away, so a player can be renamed,
  renumbered, and visually updated without jumping to an unrelated category.
- Kept **Text & Team Identity** focused on the universal fixed-allocation text
  browser. No writer, project schema, source allocation, or build behavior
  changed; this checkpoint fixes product navigation and discoverability.
- Split the shared text/roster panel into scoped views. Each sidebar workspace
  now constructs and reloads only its own models instead of processing 23,346
  text rows and 6,522 roster rows twice. The legacy combined view remains
  available to internal callers and tests.
- Preserved source/project reload, Undo, Revert All, autosave, status reporting,
  and Ctrl+F routing across current players, historical players, portraits,
  faces, and universal text. All work and verification remained headless; no
  emulator or visible desktop session was launched.
- The final focused navigation/edit selection passes **44/44**, including real
  Apply operations in both scoped views. The complete headless desktop-tool
  regression passes **992/992**, and independent review returned **GO** after
  the scoped change-refresh path was exercised directly.

## v1.0 RC13 Modified-Range Collection Parity — 2026-07-20

- Fixed the last collection-export mismatch after fixed-range AUSB editing
  shipped. **Export matching audio** and **Export selected WAVs** now include a
  Modified streaming range's staged user-replacement WAV, in order, exactly as
  individual Play and Export WAV already do.
- Kept the retail boundary explicit: an unmodified range is still labeled
  `retail_derived`; complete streaming banks and exact raw-range `.bin` exports
  can never be labeled as user replacements. Collection ZIPs remain private
  listening exports and never enter project, Undo, recovery, or Build state.
- Improved keyboard search routing so the global **Ctrl+F** action discovers the
  visible search field in Text & Team Identity, The Crib, Playbooks, and other
  product workspaces instead of incorrectly reporting that the page has no
  search box.

## v1.0 RC12 Selected Audio-Shortlist Authoring Packs — 2026-07-20

- Added **Selected shortlist (1–256)** beside the existing **All standalone
  cues (153)** replacement-pack mode. A modder can now curate any ordered mix
  of Editable standalone cues and fixed-slot soundtrack, commentary, stadium,
  crowd, or presentation ranges, export one metadata-only folder/ZIP, fill only
  the desired WAV paths, and import all true changes as one Undo action.
- Kept old v1 153-cue packs compatible. New v2 packs preserve the shortlist's
  logical order and exact PCM16 channel/rate/frame contracts. They carry only
  logical IDs, user-replacement baselines, source binding, and disclosed logical
  alias owners—never physical slot IDs, offsets, bank filenames, private source
  fingerprints, original audio, or rollback bytes.
- Reused the shipped fixed-range writer and authorized batch transaction instead
  of adding another encoder. Every supplied WAV crosses exact shape and private
  source-origin checks before commit. Identical files for two logical owners of
  the one shared AUSB slot collapse to one physical edit; divergent files fail
  before the project changes.
- Corrected stale product copy that called individually Editable streaming
  ranges browse/export-only. Complete raw banks remain Export-only: RC12 does
  not claim whole-bank repacking, recovered cue names, loop/gain/pan/priority
  editing, mixer ownership, or in-game audible consumption.
- Kept the listening shortlist broader than the authoring pack without making
  the mismatch mysterious. Playable-but-Export-only standalone sounds can still
  stay in a listening/WAV collection, but Selected-shortlist template export is
  disabled with an exact count and removal instructions until every chosen row
  is Editable.
- Kept the rights boundary honest. The private gates reject exact source PCM and
  unchanged excerpts covered by their deterministic window/anchor rules. They
  cannot prove authorship or classify transformed/re-encoded copyrighted audio;
  mod authors remain responsible for what they use and distribute.
- The final headless/offscreen desktop-tool regression passes **973/973** and
  the focused RC12 catalog/audio/GUI/packaging selection passes **75/75**. A
  clean 144-file public stage passes release → runtime closure → desktop/Bash →
  release, including a source-free ordered standalone+AUSB v2 export/import
  probe and `audio_replacement_pack_v2=selected_mixed` receipt. No source XISO,
  WAV, private audio inventory, GUI, or emulator entered this checkpoint.

## v1.0 RC11 Complete Fixed-Range AUSB Editing — 2026-07-20

- Promoted all **53,571 logical AUSB streaming ranges** to Editable through
  **53,570 exact physical fixed slots**. Replace accepts a canonical authored
  PCM16 WAV with the selected row's exact channel/rate/frame shape, encodes
  Xbox IMA into the unchanged allocation, and composes the resulting one-span
  or pack-seam edit with every other Mod Studio category. The 17 complete raw
  banks remain Export-only; this is not a general bank repacker.
- Added one physical edit state behind logical aliases. The one shared slot
  displays both affected owners; Replace, Modified filtering, Play, WAV export,
  Revert, Undo, Revert All, project save/load, and Build change them together.
  Identical duplicate alias requests collapse to one record, while divergent
  WAVs fail atomically before the project changes.
- Added automatic first-use source-audio preparation. The first Replace,
  standalone batch import, or shared audio-project load can build the complete
  private exact and containment indexes with in-app progress. It normally takes
  about 20–35 minutes once, keeps the source XISO read-only, releases the main
  facade lock while working, and refuses a source/project switch before staging.
- All authored WAV paths now cross the same immutable-byte origin gate when
  staging, saving, loading, building, and independently verifying. Exact source
  PCM and unchanged source excerpts are refused. A shareable `.2k5mod` contains
  only a logical asset ID plus the user's WAV; canonical slots, offsets, source
  fingerprints, private inventories, original audio, and rollback bytes never
  enter it.
- Added the real registry capability
  `nfl2k5.audio.ausb_fixed_range_wav`, bringing the shared registry to **62**
  rows and the NFL 2K5 product catalog to **31**. The init-free unified provider
  pins its exact 60-file execution closure and receives private origin inputs
  only for audio builds; visual-only validation/builds remain unchanged.
- The clean release-stage review contains 144 allowlisted files and passes its
  runtime closure with 46 product modules plus 22 tool modules. It includes no
  XISO, WAV, private inventory, decoded source audio, or other retail payload.
  Headless/offscreen tests cover the complete UI/session/project/provider path;
  no audible runtime cue-identity claim is made until a game spot-check exists.
- Completed one real-source, authored-WAV product-flow proof through Replace,
  Modified playback/export, retail-free project save, fresh-session project
  load, Build, and independent Verify. The one logical edit compiled to one
  physical span; Build and Verify both passed, the 6.30 GB source remained
  byte-for-byte unchanged, and the generated test output was removed afterward.
  This proves the offline product path, not in-game audibility or semantic cue
  ownership.

## Post-RC10 Audio Scale and Project-Bounds Checkpoint — 2026-07-20

- Precomputed the metadata-only Audio search index once per loaded source.
  Real-source searches across 53,571 indexed streaming rows now take roughly
  23–35 ms median instead of rebuilding every row's search text for about
  367–424 ms on each query. Reloading a source replaces the catalog and search
  index together; a focused lifecycle test proves terms from the old catalog
  do not survive.
- Added one shared limit of 25,000 simultaneous visual-plus-audio edits per
  `.2k5mod`, a 1 GiB aggregate replacement-payload limit, and an expanded ZIP
  preflight. Loading rejects excessive declared expansion and insufficient
  staging space before extracting a replacement. Saving uses a descriptor-
  pinned, single-link read for each authored WAV and refuses a project that
  would exceed either its expanded or 2 GiB archive boundary.
- Replaced the unified backend's quadratic span-overlap loop with a sorted,
  adjacent check. A worst-budget 25,004-span synthetic set validates in about
  3.24 ms while retaining the same out-of-order overlap refusal. The release
  gate now also rejects private `derived/` audio-origin cache trees, the exact
  fingerprint schema, and both containment v1/v2 schemas even if a future
  allowlist names or renames them.
- Added the isolated fixed-allocation AUSB codec/span backend and private exact-
  PCM inventory store as internal source slices. They cover 53,570 physical
  streaming slots behind 53,571 visible catalog rows, including one two-owner
  alias and four pack-seam slots. The independently reviewed read-only source
  scanner has now directly decoded all 850 standalone cues and all 53,570
  physical streaming slots, passed a final complete-XISO recheck, and published
  one 13.84 MiB private, metadata-only exact-PCM inventory. A clean second pass
  loaded it without rebuilding. The source XISO and archive cache were not
  modified.
- Added an independently reviewed exact-containment primitive as another
  internal source slice. Quarter-second source windows on a quarter-second grid
  guarantee detection of unchanged, same-shape excerpts at the roughly 500 ms
  bound; short and sparse cues use deterministic nonzero anchors, and only
  all-zero windows are exempt.
- Persisted the approved real-source containment census after a hostile review
  closed directory-swap redirection, concurrent-publication source rechecking,
  and arbitrary owner-label leakage. The read-only scan covered 54,420 cues /
  54,421 logical owners and published 615,244 digest records in a 152,956,258-
  byte private mode-0600 document. It stores no WAV, PCM, encoded sound, source
  path, or game span. A clean reuse load completed without re-decoding streaming
  payloads and repeated the complete source authentication.
- Added the sealed final-Build authorization boundary for all three fixed audio
  routes: Menu Back, standalone AUDO, and indexed AUSB. Both private origin
  checks receive the exact immutable WAV bytes later consumed by the encoder;
  a forged lookalike cannot cross the hand-off. The AUSB compiler emits exactly
  one physical span or one two-pack seam, binds aliases to one slot, deduplicates
  identical alias edits, and rejects divergent ones. Audio projects pass the
  canonical private inventories to both Build and independent Verify, while
  visual-only builds require neither file. Streaming Replace remains hidden
  until the shared session/project/Audio-panel wiring completes; no new runtime
  consumption claim is made here.

## v1.0 RC10 Accessibility and Layout Checkpoint — 2026-07-20

- Advanced the current product version to **v1.0 RC10**. The sidebar release
  label continues to derive from the package version, so the visible product
  name and the version checked by the release tests cannot drift apart.
- Added **Ctrl+F** as a window-wide shortcut for the active workspace's search
  box. It focuses the relevant search field, selects any existing query, and
  reports a short instruction in the operation-status area. Pages without a
  search box point the modder to category navigation instead.
- Added **Ctrl+1** as a window-wide shortcut for the complete modding-category
  sidebar. The category list advertises the shortcut in its tooltip and
  assistive description, so mouse-free navigation is discoverable inside the
  product.
- Added clear keyboard-focus outlines to the category list, asset lists, and
  component trees. Search fields, the current-operation label and progress
  bar, **Build Modded XISO**, and **Launch Latest Build** now expose concise
  accessible names and instructions for assistive software.
- Made the shell more tolerant of larger desktop fonts: the header and footer
  can grow instead of being trapped at one fixed height, while roomier category
  rows, primary controls, spacing, and padding keep the main workflow easier to
  scan and target.
- Added focused headless coverage for shortcut routing, active-page search,
  assistive copy, visible-focus styling, and expandable shell chrome. This
  checkpoint changes product navigation and presentation only; it does not
  claim a new asset writer or runtime game proof. No GUI or emulator was
  launched for the source-and-documentation checkpoint.
- Removed workstation-specific home, mount, workspace, and game-dump paths
  from the public changelog and nine reviewed visual catalogs. Those catalog
  fields now use stable relative provenance labels; selectors, allocations,
  resource hashes, and writer meaning are unchanged. The release gate now
  refuses either known private workstation prefix anywhere in staged UTF-8
  text while continuing to allow unrelated portable absolute-path examples.

## v1.0 RC9 Batch Audio Authoring Checkpoint — 2026-07-19

- Added **Export replacement template** and **Import replacement pack** to the
  Audio workspace for all **153 currently Editable standalone cues**: 152
  fixed-AUDO slots plus Menu Back. The folder/ZIP template contains only a
  canonical JSON manifest, editing guide, and empty `replacements/` directory;
  it exports **zero retail WAVs**.
- Each manifest row gives the stable asset ID, declared filename, writer route,
  and exact PCM16 channel count, sample rate, frame count, and no-metadata
  requirement. Modders add only their authored WAVs at the declared paths;
  missing paths are skipped.
- Import validates the complete manifest/source/current-project baseline,
  duplicate and unknown paths, every supplied WAV, and every exact cue contract
  before staging. All true changes commit as **one Undo action**. An invalid,
  stale, duplicate, unknown, or unchanged-only pack leaves the project exactly
  as it was, and a commit failure restores every touched cue. Batch Undo uses
  the same all-cues transaction: a failure restores every current WAV and the
  session manifest, keeps the Undo action available, and can be retried.
- The project boundary compares decoded PCM against every one of the 850
  standalone source cues, not merely the selected target. Moving cue A's
  source WAV into a same-shaped cue B path is refused at Replace, batch import,
  project save, and project load. Decoded streaming ranges already present in
  the user's private cache are source-verified and covered by the same rule.
- The batch route deliberately rejects streaming soundtrack, commentary,
  stadium, and presentation banks/ranges. Those remain browse/play/export-only
  until cue ownership, loop/mixer semantics, and reversible bank repacking are
  decoded. Per-cue Replace/Revert and replacement-only `.2k5mod` save/build
  remain unchanged.
- Added an output-drive free-space preflight before private build staging.
  A 2K5 build now refuses before creating any temporary file unless the
  selected filesystem can hold one complete XISO plus a 512 MiB safety margin.
  The error reports available space, required space, and the exact shortfall in
  GiB, then tells the modder to free space or choose another drive. The source
  and output stay untouched on refusal. Focused cross-title build-safety tests
  pass **32/32**.
- Closed the batch transaction and retail-sharing boundary under adversarial
  review. Same-contract cross-cue source PCM is refused during Replace, batch
  import, project save, and project load; verified source streaming PCM already
  in the private cache is covered too. Injected second-item failures during
  validation, commit, and Undo preserve the complete session tree, leave no
  hidden `.audio-pack-*` or `.audio-undo-*` files, retain the Undo ledger, and
  can be retried. Template publication and contract reads are descriptor-pinned,
  no-replace, hardlink-refusing, and maximum-plus-one bounded. Import captures
  the exact pre-edit snapshot first, validates that same snapshot against the
  exported baseline, and retains it as Undo state; an injected same-shape
  mutation during snapshot capture is refused before commit. The final
  eight-module dependent gate passes **99/99**; an independent rerun passes
  **93/93** relevant tests plus **16/16** standalone-audio tests.
- RC9 was the headless-tested package for this audio checkpoint; sealed RC8
  remained its previous immutable checkpoint. The exact 136-file stage and
  independent extraction pass release → runtime → release with no retail data,
  private inventory, links, or undeclared files. Packaged docs remain self-hash-free;
  the adjacent `.sha256` sidecar authenticates the portable archive. No GUI or
  emulator was launched while assembling or checking RC9.

## v1.0 RC8 Complete Team Kit Checkpoint — 2026-07-18

- Added **Complete Team Kit** directly to **Uniforms & Equipment**. A modder can
  export any highlighted physical uniform set, or resolve the selected team's
  HOME, AWAY, or paired HOME + AWAY style/variant, as either an editable folder
  or deterministic ZIP.
- Every exported physical set contains all **39 supported components**:
  torso/jersey, sleeve, pants, both live helmet families, jersey/helmet/arm
  digits 0–9, the vertical nameplate atlas, and all three independent Team
  Select cards. Each folder includes exact dimensions, stable labels,
  ownership notes, practical UV limitations, and `EDITING-GUIDE.md`.
- Team Kit import validates the source identity, unchanged manifest/guide,
  complete set inventory, current working baseline, every declared path, every
  PNG, exact dimensions, and decoded RGBA pixels before staging anything. It
  stages only real pixel changes as **one Undo action**; unchanged imports add
  no replacement and no Undo entry. A commit failure restores the prior
  project state.
- The bundle is intentionally source-bound. If the active source or any
  exported working pixels change after export, the modder must export a fresh
  kit. This refuses stale hand-offs instead of overwriting newer edits.
- Team Kit folders/ZIPs are private working exports and may reproduce retail
  artwork from the user's own disc. They must not be distributed. The existing
  `.2k5mod` route remains the shareable format and stores only authored,
  pixel-changed replacements plus logical metadata.
- Per-component Export/Replace/Revert remains intact for small changes. A
  successful Team Kit import enters the same modified badges, autosave,
  project, Revert, Build, and independent output-publication flow as individual
  edits.
- RC8's public allowlist and source-free runtime closure now include the Team
  Kit service explicitly. No retail template, private bundle, source XISO,
  original PNG, or generated preview is packaged.
- The focused Team Kit/session/facade/packaging selection passes **47/47
  tests**, and the complete current cross-title headless suite passes
  **489/489**. This checkpoint was assembled headlessly; no visible GUI or
  emulator was launched and the user's desktop was not touched. Exact release
  counts, archive hash, and extraction-parity receipt are recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar after sealing.
- Post-seal visual QA passed on isolated `DISPLAY=:99`. A fresh
  `v1.0 RC8 • Xbox Edition` window loaded the recognized XISO and visibly
  presented the 39-component **Complete Team Kit**, paired `HOME + AWAY`
  scope, editable-folder selector, Import/Export actions, private-retail-art
  warning, and unobstructed footer. No clipping, overlap, spacing, padding, or
  alignment defect was found, and the user's active desktop/pointer was never
  used.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC8-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz.sha256`
- Archive size: **9,667,067 bytes**
- SHA-256:
  `17254d4030806e8636c67a9b90cfcee88a7711484d9ab6ef079aba875e569466`
- The stage and independent clean extraction each contain **135 files**, **14
  directories including the root**, **101,871,957 file bytes**, **36
  executables**, and zero links or special files. The tar has **149 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **37 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `df710e64f5e7f441dfa51908a161425478c0b1c9b210a3b06cc50f0ae924df10`.
- RC7 and RC6 were reverified after sealing RC8 and remain immutable at
  SHA-256 `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
  and `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`,
  respectively.

## v1.0 RC7 Audio Review Checkpoint — 2026-07-18

- Added a dedicated **Review selected** workspace for the session Audio
  Shortlist. It shows only the curated playable sounds, supports Play/Stop,
  remove, and **Move up / Move down**, and returns to the exact browser scope,
  family, status, search, page, and selected row through **Back to browser**.
  Reordering changes the exported sequence but remains session-only: it does
  not dirty a project, enter Undo/recovery, or affect Build.
- Every multi-WAV Audio collection now includes an ordered `playlist.m3u8`.
  Its relative entries match the exact ZIP member order, so shortlist order is
  immediately playable in ordinary media software. `manifest.json` records
  the playlist path and WAV-record count. Raw-only collections deliberately
  omit a playlist and declare `playlist: null` / `playlist_record_count: 0`.
- Added **Raw Bank Containers** as a fourth Audio scope. It exposes the exact
  nine universal-index containers—three `BANK`, three `ABNK`, and three
  `WBNK`—with search, paging, metadata, and byte-exact local `.bin` export.
  These rows are truthfully Export-only: they cannot Play, Replace, Revert, or
  join the playable shortlist, and they never enter projects, recovery, Undo,
  modified state, or Build. The scope fails closed if the exact nine-row
  inventory is incomplete.
- RC7 changes only local review/export ergonomics. It does not claim decoded
  cue ownership or safe writeback for streamed or raw bank audio.
- The focused RC7 Audio/packaging selection passes **42/42 tests**; the complete
  current cross-title headless suite passes **475/475**. The clean stage passed
  release, runtime closure, source-free registry, desktop-entry, launcher
  syntax, and post-runtime release gates before publication.
- The required new-layout visual inspection remains a separate isolated-display
  gate; no GUI or emulator was launched while assembling this
  source and package checkpoint. The exact archive receipt is recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC7-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz.sha256`
- Archive size: **9,658,588 bytes**
- SHA-256:
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
- The stage and independent clean extraction each contain **134 files**, **14
  directories including the root**, **101,801,912 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates;
  runtime closure remains **36 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `e80313e49d9acade03e4dc8668eb4dda0059f6fd3e47320d0f8104e832917031`.
- RC6 was reverified after sealing RC7 and remains immutable at SHA-256
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.

## v1.0 RC6 Audio Shortlist Checkpoint — 2026-07-18

- Added a session-only **Audio Shortlist** for hand-picking standalone AUDO
  sounds and playable streaming ranges across unrelated searches, pages,
  families, and scopes. Selected rows carry a visible `★ Selected` status and
  an ordered **Selected _n_ / 256** count.
- Added **Add/Remove selected sound**, atomic **Add this page**, **Clear**, and
  **Export selected WAVs** actions. Complete streaming banks are deliberately
  excluded because a bank is not one playable cue; its indexed ranges remain
  selectable.
- The exact selected-ID exporter is independent of current browser filters and
  mixes original standalone WAVs, staged replacement WAVs, and decoded
  streaming-range WAVs in selection order. The existing transactional bundle
  manifest records `retail_derived` versus `user_replacement` origin.
- The shortlist survives normal refresh, search/filter/page/scope changes, and
  project loads for the same source. Only a successful new-XISO load clears it.
  It never enters `.2k5mod`, recovery, Undo, modified state, or Build.
- Invalid empty, duplicate, unknown, complete-bank, or over-256 selections fail
  before output. Existing destinations remain untouched, and a failed decode
  still leaves no partial ZIP.
- The focused Audio backend/offscreen-Qt selection passes **18/18 tests**. The
  complete current cross-title desktop-tool suite passes **443/443** with
  `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`.
- Isolated-display visual QA inspected the RC6 Audio workspace on `DISPLAY=:99`. The
  Soundtrack, matching-export, shortlist Add/Remove, Add-page, count, Clear,
  and Export-selected controls are readable and unclipped; the browser/detail
  layout remains usable without touching the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC6-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz.sha256`
- Archive size: **9,643,071 bytes**
- SHA-256:
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`
- The stage and independent extraction each contain **134 files**, **14
  directories including the root**, **101,773,880 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **36 product + 22 tool modules**, **60 registry
  capabilities**, **11 sections**, and **30 NFL 2K5 capabilities**; extraction
  is byte- and mode-identical.
- RC5 remains immutable. Its sealed SHA-256 is
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`,
  and its complete receipt is preserved immediately below.

## v1.0 RC5 Active Project Checkpoint — 2026-07-18

- Added normal document-style project identity: an opened or first-saved
  `.2k5mod` becomes the active project, its name appears in the window title,
  and an asterisk marks changes since the last successful named save/load.
- **Save** / **Ctrl+S** now updates the active project directly. **File → Save
  Project As…** / **Ctrl+Shift+S** owns first-time naming and separately named
  copies. Recovered edit sets remain visibly **Untitled** until named.
- Protected fast-save with an in-memory target fingerprint. A missing target,
  symbolic/hard link, path substitution, or external file change fails closed
  with a Save As instruction; the remembered project, live session, and private
  recovery state stay intact.
- Corrected dirty-state semantics so every authored mutation remains unsaved
  even when it reduces the current replacement count to zero. In particular,
  **saved project → Revert All** shows **No edits • unsaved**, keeps Save and
  the close/source/project data-loss gates active, and leaves Build disabled.
- Added an explicit empty-project route for GUI Save/Save As and private
  recovery. The archive contains only `project.json`, an empty edit list, and
  the existing `user-replacements-only` policy; accidental backend empty saves
  remain rejected by default.
- Added six headless project-document/target-safety tests and extended recovery
  and facade checks. The focused project, recovery, facade, and session
  selection passes 35/35 tests without a visible desktop; the complete current
  desktop-tool suite passes 428/428.
- Isolated-display visual QA inspected the clean RC5 candidate on `DISPLAY=:99`.
  **File** visibly exposes **Save Project** (`Ctrl+S`) and **Save Project As…**
  (`Ctrl+Shift+S`); both are correctly disabled in the clean, no-edit state,
  and the complete menu renders without clipped or overlapping text. The check
  did not touch the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC5-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz.sha256`
- Archive size: **9,639,953 bytes**
- SHA-256:
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`
- The tar contains **148 members**. Both the original stage and independent
  clean extraction contain **134 files**, **14 directories including the
  release root** (**13 internal**), **101,750,965 file bytes**, **36 executable
  files**, and **zero links**.
- The original tree and independent clean extraction both passed the
  release/runtime/registry/desktop/bash/post-runtime gates. Runtime closure is
  **36 product + 22 tool modules**; the registry exposes **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**.
- The full desktop-tool suite passes **428/428**. The immutable RC4 checksum
  sidecar was reverified unchanged after the RC5 seal.

## v1.0 RC4 Audio Collections Checkpoint — 2026-07-18

- Added a one-click **Soundtrack & music (136)** view and transactional
  **Export matching audio** for any 1–256 filtered standalone cues, raw banks,
  or indexed streaming ranges. The complete known music view fits the bounded
  route at 136 rows and about 1.22 GiB of decoded PCM before ZIP compression.
- Added a deterministic local-audio manifest with stable catalog IDs, physical
  bank/range coordinates, PCM metadata, payload SHA-256, and explicit
  `user_replacement` versus `retail_derived` origin. The artifact identifies
  itself as local-only and never enters a shareable `.2k5mod` project.
- Bundle creation is all-or-nothing, capped at 256 rows and 2 GiB of payload,
  refuses overwrite/symlink targets, and publishes only after every decode,
  size check, checksum, and manifest entry succeeds. A failed row leaves no
  partial ZIP and does not change edits, Undo, recovery, or Build state.
- Added the **Modified** filter for instant review of staged standalone WAVs.
  Streaming banks/ranges correctly return no Modified rows because their
  replacement route remains disabled.
- Isolated-display visual QA checked the final Audio layout on `DISPLAY=:99`. It
  caught Qt consuming the first ampersand as a mnemonic marker; the button now
  visibly reads **Soundtrack & music (136)**, and both filter/action rows,
  browser table, and detail pane remain unclipped.
- The complete cross-title product gate passes 419/419 tests. RC4 is a new
  immutable checkpoint; RC2, RC3, and their checksums remain unchanged.

### Release receipt

- Portable archive: `2K5-Mod-Studio-v1.0-RC4-20260718.tar.gz`
- Size: `9,645,491` bytes
- SHA-256: `acde381520b8b0efb26266977f5e4d657fb478ce91299ce9cd152f03d36b2e22`
- The exact 134-file stage contains `101,736,199` file bytes. Its 36-product /
  22-tool-module runtime closure, 60-row registry, 11 product sections, and
  source-free desktop construction checks passed before archiving and again
  after clean extraction.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## v1.0 RC3 Product Checkpoint — 2026-07-18

- Packaged the working-tree advances that followed RC2: complete indexed AUSB
  range browsing/playback/export, dedicated Gameplay and Menus inspectors,
  source-bound autosave/recovery, recent files, and shared Save/Discard/Cancel
  data-loss gates.
- Polished the Audio workspace so all three scopes remain readable at normal
  desktop size. Standalone sounds retain their truthful edit controls; complete
  banks and indexed ranges now use visibly disabled Replace/Revert controls,
  concise ownership summaries, and full technical tooltips.
- Corrected alternating-row colors in the Gameplay and Menus tables, preserved
  literal ampersands in tab labels, and tightened local status copy so no table
  presents a white or misleadingly writable row.
- Added the APF digital-font provider to the exact clean-release closure. This
  fixes a real clean-stage import failure while keeping the 2K5 application
  package source-free and retail-free.
- Ran four current-code visual checks on isolated `DISPLAY=:99`:
  recovery/recent files, every Audio scope, the complete
  Gameplay inspector, and both Menus inspector modes. All controls, disabled
  states, tables, tooltips, and status labels rendered without clipping or
  overlap; the isolated QA window and synthetic recovery fixture were removed.
- Passed 404/404 desktop-tool tests headlessly, including both title backends,
  before assembling the non-overwriting RC3 release tree and archive. The
  archive is `2K5-Mod-Studio-v1.0-RC3-20260718.tar.gz` (**9,635,511
  bytes**) with SHA-256
  `69b79986903152102093632c60c3f6ba177dd3c9dd5d615e8f18d9c4e025c548`;
  its adjacent `.sha256` sidecar carries the same checksum.

## Post-RC3 Audio Review — 2026-07-18

- Added a **Modified** Audio status filter so a modder can isolate every staged
  standalone WAV among the 850 indexed cues, then inspect or Revert it without
  paging through untouched sounds. Streaming banks/ranges truthfully return no
  Modified rows because their replacement controls remain disabled.

## Post-RC3 Audio Collections — 2026-07-18

- Added a one-click **Soundtrack & music** view for all 136 exact music ranges
  and a bounded **Export matching audio** action for any 1–256 filtered rows.
  The action packages current standalone WAVs, complete raw banks, or verified
  WAV/raw ranges in one manifest-backed ZIP instead of requiring one export per
  table row.
- Collection export is all-or-nothing, refuses an existing or linked target,
  caps both row count and predicted payload bytes, and publishes the ZIP only
  after every payload and checksum succeeds. A failed decode leaves no partial
  result.
- The manifest distinguishes staged `user_replacement` WAVs from
  `retail_derived` audio. Collection exports remain local-only and structurally
  separate from shareable `.2k5mod` projects, project mutations, Undo, recovery,
  and Build.

## Workspace Recovery and Recent Files — 2026-07-18

- Added immediate background autosave after every connected visual, text,
  roster, Crib, audio, Stadium, Undo, and Revert workflow. Autosave delegates
  to the normal validated `.2k5mod` writer, so it contains user-authored
  replacements and logical metadata only—never source or original game bytes.
- Bound every recovery snapshot to the active source SHA-256 while holding the
  facade session lock. A source switch cannot relabel one game's edit set as
  another game's recovery, and recovery refuses a source-identity mismatch.
- Added a startup recovery choice plus **File → Recover Unsaved Edits**. A
  missing/moved source produces an exact path instruction and keeps the
  replacement-only recovery archive rather than guessing at another dump.
- Added **Save Project / Discard Edits / Cancel** gates before source switches,
  project replacement, and app close. Cancelling or a failed load retains both
  the current session and its recovery snapshot.
- Added private, atomic recent-file state for the last eight XISOs and eight
  named projects, surfaced through File-menu submenus. Recent paths never enter
  shareable projects.
- Added seven focused headless recovery/state/connectivity tests and expanded
  the release allowlist so the recovery module cannot be omitted from the next
  package. The selected 50-test recovery/facade/session/UI-model/packaging
  regression passed without launching a GUI or touching a display.

## Current-Tree Source-Free Preflight — 2026-07-18

- Replaced the stale streaming-audio research boundary with the complete
  registry instruction: “Recover external music/commentary cue identities and
  directories, loop points, gain, pan, priority, runtime routing, and
  reversible rebuild rules before any bank writer.” A focused test requires
  this exact instruction once and refuses the former wording.
- Added the recovery-state module to the clean-stage runtime closure and
  exercised recent-source metadata, source-SHA binding, recovery discovery,
  retail-payload exclusion, and cleanup using synthetic files only.
- Extended the same closure receipt across current all-range Audio coverage and
  the dedicated Gameplay and Menus inspectors. The passing receipt covers 35
  product modules, 22 tool modules, 850 standalone sounds, 17 streaming-bank
  descriptors, and all 53,571 indexed streaming ranges without a display.
- Fixed a preflight defect found by the post-runtime retail scan: module imports
  could leave undeclared `__pycache__` files in an otherwise clean stage. The
  checker now disables bytecode publication before any product/tool import.
- Rebuilt a fresh disposable allowlist-only stage and passed the release gate,
  runtime closure, 60-row source-free registry validation, desktop-entry
  validation, launcher syntax, and the post-runtime release gate. The stage had
  132 files, 13 directories, 101,659,703 bytes, no private inventory, and zero
  retail payloads; its totals stayed identical after runtime probing.
- Passed 317/317 nonvisual 2K5 tests (295 product plus 22 NFL/shared-provider
  integrity cases) and preserved the exact 43-validator plan. GUI/visual QA and
  RC3 packaging remain root-owned follow-up work; neither was performed here.

## Gameplay and Menus Inspector Pass — 2026-07-18

- Replaced the static **Sliders & Gameplay** findings page with a dedicated
  read-only product inspector: all 21 named slider rows, the stock range, all
  17 CPU **Fantasy Draft** position weights, eight observed save containers,
  the save/signature boundary, and five bounded franchise findings are now
  directly browsable.
- Kept the proof boundary in the controls themselves. Fixture slider values are
  labeled as research observations rather than the user's profile; Fantasy
  Draft is not called Franchise Draft; and no preset, executable patch, save
  writer, or out-of-range control is offered.
- Added a specialized **Menus & UI** inspector for the named NFL Main Menu:
  seven initialized rows/transitions, two owned layout relationships, rendering
  boundaries, initial selection, and all three remaining blockers are visible.
- Preserved the existing complete archive-resource browser as **All Raw
  Resources** inside the Menus workspace, and kept the registry capability
  cards/limitations available in both specialized inspectors.
- Added non-overwriting, sanitized JSON and spreadsheet-ready CSV export routes
  in the flagship facade for both inspectors. These reports contain named
  evidence and status metadata, never retail executables, saves, or archive
  bodies.
- Added two small, hash-pinned product snapshots so the inspectors remain
  runnable when private research reports are correctly absent from a release.
  The snapshots contain named metadata only, are covered by the exact
  reviewed-metadata allowlist, and are checked against the proved core outputs
  when the development evidence set is present.
- Added fail-closed model validation for the exact 21/17/seven-row contracts
  plus focused facade and offscreen flagship connectivity tests. All **51**
  selected inspector, facade, existing gameplay/menu core, Qt model, and
  release-manifest tests passed without launching or visually inspecting a GUI
  and without building a package.
- Corrected product documentation to match the current layout: Rosters &
  Players presently owns portrait/live-face textures, while the Current and
  Historical roster forms still share the **Text & Team Identity** workspace.

## Continuous Audio Coverage Pass — 2026-07-18

- Split the Audio tab into **Standalone sounds (850)**, **Streaming banks
  (17)**, and **Indexed streaming ranges (53,571)** so soundtrack, commentary,
  stadium/PA/coach, broadcast, and ambient audio are visible in the dedicated
  editor rather than only as opaque rows in the archive-resource fallback.
- Added exact private-source parsing for all 17 NFL 2K5 `AUSB` descriptors,
  their 16 external `.bin` owners, and all 53,571 indexed ranges.
  The duplicate `cwdloop` descriptors visibly report their shared owner.
- Added searchable family and status filters plus explicit container, ownership,
  export-format, and replacement-status labels. Standalone audio exports as a
  playable WAV; streaming banks retain exact raw `.bin` export, and every
  individual range now supports both its raw `.bin` and decoded PCM16 WAV.
- Completed the main-facade paging contract used by the Audio panel, including
  stable first/last result numbers for cue, bank, and range pages.
- Proved the bank payload codec as Xbox IMA ADPCM: all 53,571 ranges are whole
  descriptor-channel block groups, and a complete 2,183,326,092-byte scan found
  60,647,947 valid physical channel-block headers with zero invalid step indices.
- Added private Play/Stop and PCM16 WAV export for all indexed ranges. Complete
  banks remain raw-only because they contain many cues. Replacement remains
  disabled because cue names, loops/durations, mixer rules, and reversible
  repacking are still unresolved. Raw and decoded retail audio remain local and
  are structurally excluded from shareable `.2k5mod` projects.
- Made the original bounded **Menu Back** replacement route explicit in the
  selected-cue instructions while preserving all 152 additional exact-shape
  standalone writers and 697 alias-safe Export-only rows.
- Live private-cache indexing returned 850 standalone cues, 153 Editable rows,
  17 streaming descriptors, 16 external owners, and 53,571 ranges with the
  source opened read-only. Focused retail-free catalog and panel backend tests
  cover raw-bank and exact-range discovery/export, decoded range playback paths,
  cache-tamper/failed-decode cleanup, search/filter behavior, WAV replacement,
  revert, and overwrite refusal.
- Exercised the largest real range end to end: 8,954,064 encoded bytes became a
  31,836,716-byte stereo WAV in 1.018681 seconds. Python 3.12 uses an optional
  standard-library accelerated path; an explicit test proves the exact fallback
  used when that module is absent.

## v1.0 RC2 UX Refresh — 2026-07-18

- Tightened the desktop shell so more useful content fits without crowding:
  the sidebar, header, footer, browser columns, panels, cards, and preview
  minimums now use one compact spacing rhythm.
- Normalized typography and control sizing around Noto Sans, 34-pixel form
  controls, and 40-pixel primary build/launch actions, with stronger contrast
  and explicit disabled states.
- Made **Build Modded XISO** the clear primary action and renamed the quieter
  emulator action **Launch Latest Build** so the normal workflow reads in the
  order a modder actually uses it.
- Added clear buttons, accessible names, and practical tooltips to search and
  filter controls across the asset browsers. Stadium labels and other internal
  status copy now use modder-facing language.
- Re-ran the complete non-visual 2K5 product suite after the UX refresh: 312
  headless tests passed with no failures, errors, or skips. The release/runtime
  gates are recorded in the release status alongside the final archive hash.
- Published the non-overwriting RC2 runnable tree as
  `2K5-Mod-Studio-v1.0-RC2-20260718/` and portable archive as
  `2K5-Mod-Studio-v1.0-RC2-20260718.tar.gz`. The archive is
  **9,575,103 bytes** with SHA-256
  `6df15767ff766d7eb2b7b87634d79dee495102c74db323067eedc01f796193d7`.
- Independently extracted that archive and reran its retail-free gate,
  runtime-closure probe, desktop-entry validator, launcher syntax check, and
  post-runtime retail-free gate. All passed; the archive contains 126 regular
  allowlisted files, 14 directories, no symlinks or hardlinks, no private
  inventory, and zero retail payloads.

## v1.0 Release Candidate — 2026-07-18

### Product shell and universal coverage

- Completed all 11 sidebar tabs: Uniforms & Equipment, Rosters & Players, Team
  Identity, Field Art & Create-Team Art, Stadiums, Scorebug & Presentation,
  Menus & UI, The Crib, Audio, Sliders & Gameplay, and Playbooks & Plays.
- Connected all 30 NFL 2K5 capability cards to the 60-row cross-title registry.
  Card status renders as **Editable**, **Preview/Export-only**, or **Coming
  Soon** from shared registry state; concrete editor actions remain explicitly
  wired per specialized workflow.
- Kept the archive-resource browser as the fallback home for every resource in
  that index that does not yet have a specialized editor. Raw fallback rows are
  honestly Export-only rather than inheriting a capability status they cannot
  perform.
- Indexed 32,038 specialized visual assets with searchable category browsers,
  previews/thumbnails where supported, stable asset IDs, Export, Modified
  badges, Replace for writable classes, and per-asset Revert.
- Extended the shared session across visual, text, roster, audio, Crib, and
  Stadium edits, including Undo, Revert All, modified counts, and retail-free
  `.2k5mod` project save/load.

### Uniforms, rosters, text, and presentation

- Shipped the complete proved Uniforms & Equipment workflow for jerseys/torsos,
  sleeves, pants, live helmets, digits/nameplates, and separate Team Select
  cards.
- Shipped bounded portrait, live-face, create-team field-art,
  scorebug/presentation, team-identity, player-name, and jersey-number editing.
- Added a dedicated **Current Roster Players** browser/editor inside the shared
  **Text & Team Identity** workspace. Every current player number has a
  searchable row with current/original name and number, status filtering,
  Apply, Revert, and number Export. Primary proved rows are Editable;
  secondary-pool rows remain visibly Preview/Export-only. Rosters & Players
  currently remains the portrait/live-face texture workspace.
- Added Historical Teams coverage for all 75 historical ROST resources and
  3,975 historical players.
- Proved that the current and historical player views cover all 6,522
  jersey-number assets exactly once; no current number is left accessible only
  through an internal catalog.
- Added universal text search across 716 banks and 23,346 strings. Exactly
  20,074 fixed-allocation strings are Editable; the other 3,272 remain
  read-only with a reason.
- Made all four display fields for each ESPN 25th Anniversary moment editable:
  title, historical description, challenge objective, and date. Team selectors,
  scenario state, and unlock conditions remain outside the text writer.

### Stadium Studio and The Crib

- Added Stadium Studio for all 477 indexed scenes, with private lazy glTF/PNG
  derivation, resumable generation, orbit/pan/zoom, surface highlighting, and
  material/texture ownership selection.
- Connected Export/Replace/Revert/project/build for all 23,838 indexed
  fixed-allocation P8 texture occurrences. Multiple edits to one SCNE compose in
  one rebuild instead of overwriting one another.
- Preserved existing Stadium geometry, UVs, materials, collision, archive
  extents, and fixed SCNE allocation. Images that cannot fit the original
  compressed slot fail closed with a modder-facing message.
- Added The Crib browser for all 498 inventoried assets. All 128 Team Photos and
  the exact `room:22 / bar_monitor` screen are Editable, for 129 Editable rows;
  the other 369 are Preview/Export-only.

### Audio, gameplay status, and playbooks

- Added browse/preview/export for all 850 standalone AUDO resources.
- Enabled fixed-contract WAV replacement for 153 resources: the existing
  menu-back cue plus 152 uniquely owned standalone slots. The other 697 remain
  Export-only because duplicate-name/content aliases make runtime cue ownership
  ambiguous.
- Added exact per-row PCM16 validation for channel count, sample rate, frame
  count, and WAV chunk layout. An invalid WAV leaves the project unchanged.
- Corrected the known 17-position Draft table's product label to **Fantasy
  Draft**, not Franchise rookie draft. Private Catching and Fantasy Draft patch
  transports remain experiments and do not appear as finished presets without
  a causal runtime A/B.
- Added the dedicated read-only Gameplay inspector and named Main Menu
  transition inspector described above, including sanitized JSON/CSV export and
  retained capability/limitation views. Neither inspector claims writeback.
- Added the mandated Playbooks & Plays fallback as a structured viewer for 37
  books, 1,533 formations, 9,251 plays, 32,502 assignment chains, 91,833 nodes,
  and 101,761 player-slot references. Selected raw PLAY resources can be
  exported; route drawing/import stays Coming Soon with its findings note.

### Build, rollback, and release safety

- The source XISO is always opened read-only and cannot be selected as a build
  destination.
- Every staged replacement retains a private original for per-asset Revert;
  Undo and Revert All operate across the full project.
- Builds use a temporary output and exclusive final creation. A failed build
  cannot leave a partial/corrupted requested output.
- Shareable `.2k5mod` projects carry only user-authored replacements and logical
  metadata. They do not contain source resource payloads, private originals, or
  compiled XISO spans.
- The clean release-candidate package stage passed with **126 allowlisted
  files**, **101,447,213 bytes**, and **zero retail game bytes/private source
  inventory**.

### v1.0 composed smoke

- One product-flow project staged 19 Tier 1 edits and built them into a new
  XISO. The output changed 1,027,710 bytes and has SHA-256
  `70cd2bc0acc57d358d800cd6c0952c1c89c1c09ee9039d9513e435c58dffa0a6`.
- The source remained read-only and retained SHA-256
  `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`
  before and after the build.
- Headless visual QA inspected xemu only on private Xvfb display `:99`. It saw the
  ESPN splash, stable attract sequence, and a clean NFL 2K5 title /
  **Press START** screen with no visible corruption.
- This was a boot-level spot check. The release does not claim that every edited
  asset was individually visited or judged in gameplay. A later isolated
  software-rendered harness retry logged a PFIFO assertion during or after the
  close attempt, so no clean long-duration gameplay claim is attached to it.

### Known limits in v1.0

- The 3,272 non-writable text entries stay visible and read-only because they
  have zero text capacity, selector semantics, or an unproved write contract.
- Secondary roster pools are browsable/exportable. Position codes/labels and
  selected ownership metadata are already decoded in research but are not yet
  surfaced in the product form; ratings, membership, depth charts, and unsafe
  secondary-pool writeback remain Coming Soon.
- Stadium texture editing does not imply arbitrary model import. General
  Stadium/Crib geometry serialization, transforms, collision, and relocation
  remain outside v1.0.
- Only the proved Crib `bar_monitor` electronics surface is writable; the other
  24 electronics-like rows remain export-only pending one-at-a-time ownership
  and fixed-span proof.
- The 697 alias-ambiguous AUDO rows are not routed through the unique-slot
  writer. Complete non-AUDO banks remain raw-only multi-cue containers; their
  53,571 individual ranges are playable/WAV-exportable, but are not writable.
- Catch-strength presets require matched drop-rate sampling. The known Draft
  weights require a Fantasy Draft runtime A/B and do not address the separate
  Franchise rookie-draft scorer.
- Route authoring remains blocked by undecoded coordinates, opcodes, player
  roles, custom-save ownership, and inverse compilation. The read-only PLAY
  inspector ships instead.
- ESPN 25th moment text is editable, while scenario fields and unlock logic
  remain findings-backed Coming Soon.
- xemu is the supported target. Original Xbox hardware is untested.

## Phase 1 Alpha — 2026-07-17

- Shipped the polished Linux desktop shell, source-XISO load/index flow,
  in-app Getting Started page, and searchable Uniforms & Equipment browser.
- Added PNG previews, drag-and-drop replacement, per-asset Revert, Undo, Revert
  All, and modified badges.
- Added end-to-end build of a separate modded XISO and xemu launch detection.
- Added shareable retail-free project files and private original storage.
- Added universal raw inventory browsing so every indexed resource had a
  visible home before specialized v1.0 editors were completed.
- Confirmed the Detroit torso smoke build reached the normal NFL 2K5 title
  screen in xemu.

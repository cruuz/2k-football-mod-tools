# beta-58 — RC82 / alpha.84

**Date:** 2026-09-04

**2K5 Mod Studio:** `v1.0-RC82`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (unchanged)

## New: the community list

- **Free Practice inside Franchise.** The Coach's Desk gains a Practice row: a Scrimmage of your
  team against itself with the exact roster, ratings and depth chart your franchise has right now
  (away kit against home kit), and it returns to the desk. Stats and injuries are not recorded.
- **Position on the first page of Edit Player**, in roster mode and inside Franchise. Ratings stay,
  the overall follows the new position; run Depth Chart, Auto afterwards.
- **Home or away jersey at any stadium.** On Controller Assign or Team Select, keep pressing up or
  down past a side's last era to flip its colour (the Cowboys rule is the retail default; both teams
  may choose white).
- **Penalties near NFL rates**, and the Chop Block toggle now works (retail profiles carry it Off).
  The rates are an estimate until a calibration playtest; the recipe is in Getting Started. Illegal
  formation, illegal contact and 12 men do not exist in the engine.
- **Modern draft-prospect names** from nflverse 2015-2025 rosters (CC-BY-4.0). Surnames the
  announcer has recorded keep their call-out; replacements are announced by number. New
  franchises only. Your own list: a CSV on the Build tab.
- **Pro Bowl Votes tabs in football order** (kicker and punter last).
- **Laces to the posts on field goals and PATs** (EXPERIMENTAL only until witnessed).
- **A star under players you tag** in Text & Rosters (the game's own controller star, up to nine).

## Fixed

- Modern overtime ended the game after a first-possession field goal. The kick path credited the
  receiving team with a possession before the field-goal play was judged; the other team now gets
  its possession, and a Situation started in overtime seeds the rule correctly.
- Models export: the UV rule was wrong for every model (the game applies a per-shape scale and
  offset stored in the shape record). Exports now map textures correctly, carry the Stadium
  Studio's metadata so the community Blender add-on accepts them, and keep baked vertex lighting
  out of the base colour. Same-topology re-import inverts the rule.
- Build & Share left the texture-project buttons greyed after a build and Launch Latest Build did
  not know about the copy; both fixed. Help gains Join the Discord.

## Not in this release

7-on-7 practice is built but hidden until it is witnessed through a snap. The SOFTDRINK patch
files are rebuilt: basic v0.7, advanced v1.0, experimental v0.3. APF 2K8 Mod Studio assets are the
beta-53 alpha.84 files, re-attached. Everything new is unwitnessed in game unless Noah's own test
says otherwise; please report what you see on the Discord.

# beta-57 — RC81 / alpha.84

**Date:** 2026-09-03

**2K5 Mod Studio:** `v1.0-RC81`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (unchanged)

## New: Update now

When a newer release exists, the banner (and Help > Check for Updates) offers **Update now**. The
studio downloads the right file for your install, checks it against the SHA-256 the release
publishes, and installs it: on the Windows installer layout it starts the new installer silently
after the studio closes and reopens the studio; from an unpacked release folder it swaps the
folder in place and keeps the old one beside it as `.previous`. Nothing downloads until you
press the button and confirm. This is the first build with the button, so this one update is by
hand; from here on it is one click.

## New: TEAM on the franchise Player Card, with real history

The season-by-season stats on a player's franchise card now show which team each season was
played for. From the first season rollover after the patch is in your save, every completed
season records the club the player finished it with. For 2004 and earlier the roster template
carries the real clubs from nflverse data (CC-BY-4.0): 1,148 of the 1,325 retail players with
past-season stats, 5,068 of their 5,867 season rows. Rows the data does not cover show "--", and
you can supply your own CSV (`last_name, first_name, birth_date, season, team`) on the Build tab
for an updated roster. Relocated franchises show the 2004 abbreviation in this cut. A new
franchise is required; existing saves keep "--". Both are in the BASIC (column only), ADVANCED
and EXPERIMENTAL presets. Unwitnessed in game so far; please report what you see.

## Fixed

- Several executable patches store code in the XBE boot-logo bitmap. The game never reads it, but
  the kernel draws it during the boot animation, and a user's investigation of a hang at the Xbox
  logo flagged it. The builder now keeps a decodable logo in the header and points the kernel at
  it. On xemu with the Complex BIOS the old discs boot regardless; this closes the risk elsewhere.
- A disc save name typed without an extension produced a file xemu's picker could not see. A bare
  name now gets `.xiso.iso`.

## Not in this release

The 7-on-7 practice mode is built and tested but stays hidden until it is witnessed through a
snap. The SOFTDRINK patch files are rebuilt for the new presets: basic v0.6, advanced v0.9,
experimental v0.2. APF 2K8 Mod Studio assets are the beta-53 alpha.84 files, re-attached.

# beta-56 — RC80 / alpha.84

**Date:** 2026-09-03

**2K5 Mod Studio:** `v1.0-RC80`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (unchanged)

## New: ★ Models — every model out to Blender and back

The ★ Models page lists every 3D model on your disc (players, helmets, face masks, balls,
referees, coaches, cheerleaders, crowds, props, the Crib, menus, trophies, stadiums) and
exports any of them as glTF 2.0 for Blender: triangles, normals, UVs, vertex colours, the
textures the game draws it with, a skin with the game's joints on every animated model, and a
vertex-index lane so an edited file finds its way back. Import fits your edited glTF/GLB onto the
game's own vertices, re-encodes positions (widening the range when your edit needs it), keeps
everything else exactly as shipped, rebuilds the resource into its retail span, and writes a copy
of your disc. The report tells you what changed before anything is written; the README beside each
export tells you what can change. Not yet: new vertices or triangles, bones, animations, morphs.

# beta-55 — RC79 / alpha.84

**Date:** 2026-09-03

**2K5 Mod Studio:** `v1.0-RC79`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (unchanged)

## Fix: Build & Share → Advanced on any dump of the disc

The second public beta-54 report: a legal USA retail `.iso` laid out differently from the rip
this studio was developed on failed the 2026 season step with `pack-0 schedule template is
foreign: ROST stored size is not retail`, while Basic (executable-only) built. The schedule
step and a dozen other pack writers read packs at a byte offset measured on one image; they
now resolve every `vc_53450030/<pack>` through the image's own file table, disc detection
locates the game partition, and the scorebug status can no longer abort the Build panel on a
user machine. Verified with identical Advanced builds from the retail rip, a redump-style
image and an extract-xiso reordered image, with and without the POSIX-only `os` members.

# beta-54 — RC78 / alpha.84

**Date:** 2026-09-03

**2K5 Mod Studio:** `v1.0-RC78`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (identity ride-along; no APF surface change)

**Hotfix (same release, same file names, 2026-09-03 evening):** the Build tab died on
Windows with `module 'os' has no attribute 'pread'` after writing the copy, in the
read-back that verifies it. Every shipped module now resolves positional IO through
a seek-based fallback where `os.pread` / `os.pwrite` do not exist (the throw-tuning
verify, the playbook position recode, the commentary swap, the team-identity and
scorebug tools, five APF tools), `copy_file_range` is optional, and every raw
descriptor opens in binary mode. Proven by building the Basic and Advanced presets
and applying the Advanced `.2k5patch` to a retail copy with those `os` members
deleted; the outputs are byte-identical to a Linux build. CI now fails on any bare
POSIX-only `os` function in shipped Python. Re-download the same beta-54 assets.

## New: ★ Build & Share — "Start with the SOFTDRINK patch"

One page builds a patched copy of your disc image (or default.xbe) from a
checklist, and three buttons tick a known-good set before you build:

- **Basic: the 2004 game, just the 2K5 fixes.** Throw ceiling 80 with realistic
  flight, Catching / Interception sliders that actually decide drops and picks
  (Catching to 200), franchise draft and free-agency AI that drafts by value and
  need (the Rookie Report never ranks a FB, K or P in the top 25), real kick and
  punt returners on CPU depth charts, and kicking power re-spaced so elite legs
  reach ~70 yards. Retail kick spots, names, rules and presentation.
- **Advanced: everything modern.** Basic plus Defensive End → EDGE game-wide,
  modern kicking (kickoff 35, touchback 35, PAT from the 15), modern overtime
  (both teams possess, 10-minute regular season with ties, playoffs play on),
  acceleration ramp, NFL-shaped progression, arc by distance (short game retail,
  45–60 yd lobs hang, 63+ flat), the ESPN scorebug bar (bottom centre, stays up
  during plays, repainted textures, kick meter lifted, lineup strip off),
  depth-chart positions by scheme (SAM / MIKE / WILL, 3-4 NT / EDGE), one EDGE /
  LB / interior pool across schemes (rosters, playbooks, free agency, draft, team
  ratings), the Far-look default camera, and the 2026 franchise: real 2026
  schedule, three-game preseason, 17 games over 18 weeks, 14-team playoffs, 2026
  dates and rookie birth years.
- **Experimental: advanced + widescreen + rough edges.** Widescreen hor+ 16:9
  (wider 3D view; HUD, menus and play art keep their 4:3 sizing; set xemu's
  Display aspect to 16x9) and the dynamic-kickoff line-up (alignment only).

Every toggle is pattern-checked against retail bytes, refuses a source whose
sites are neither retail nor this patch, writes a COPY, reads it back and
leaves a receipt beside it. xemu-only, like every executable edit here.

## New: Share tab (`.2k5patch`)

Export the difference between your patched copy and the base it came from as a
small patch file (byte runs, your source PNGs / WAVs, a recipe), inspect or
dry-run it against any disc, and apply it to a copy of your own image; every run
is verified against the SHA-256 of the bytes it replaces before anything is
written. The two SOFTDRINK presets ship as `.2k5patch` files with this release.

## New: Sounds and Commentary

Audio → Sounds replaces any game sound (crowd, QB cadence, chants, PA, SFX) across
every sub-bank from a WAV, with export, fit line and verify. Commentary swaps a
stored line for your own recording. Both verified statically; witness in game.

## Also

- Throw Distance & Arc gained the arc-by-distance, catch, acceleration, draft,
  returner, progression and EDGE toggles; the lob-speed table now keeps the retail
  short-game points exactly.
- Gameplay Patches and Presentation pages expose the same toggles individually.

## Also in this beta

- **Getting Started** has a "Start with the SOFTDRINK patch" button that opens Build & Share.
- **Share, the easy way:** after a Build, the Share tab's top button exports a `.2k5patch`
  next to your copy in one click (base, copy, name and file pre-filled).
- The Build tab's checklist is drawn large and high-contrast so every ticked patch reads at a glance.
- Disc-image patching no longer depends on POSIX-only positional reads: the same code path runs on
  Windows and macOS (seek-based fallback), and every image handle opens in binary mode.
- "Field Art & Create-Team Art" now explains itself: it is the game's own Create-a-Team teams
  (fictional by design); real NFL end zones and midfield art live under All Textures / Stadiums.

## Known limits (beta)

- **The ESPN scorebug toggle reads "Not available in this build" in the installed studio.** Its
  repainted art and the retail scorebug mesh are not shipped (retail-free release rule); the
  Advanced preset skips it and says so. The full Advanced experience, scorebug included, is the
  `SOFTDRINK patch advanced` `.2k5patch` published with this release: Share → Apply it to your own copy.
  *(Fixed after beta-58: the scorebug now builds on any install, from your own disc image. Only
  the ticker-band atlas still needs the published patch.)*

- Dynamic kickoff phase 2 (players hold until the ball lands, CPU kicker range)
  is not built; the alignment toggle may draw a kickoff flag — report it.
- Team names, cities and "Super Bowl 2005" text are still 2004; no Pro Bowl in
  the 18-week season; the 2027 preseason reuses the 2026 opponents.
- Widescreen: the injury banner and a few full-screen fades are unproven.

# beta-53 — RC77 / alpha.84

**Date:** 2026-09-02

**2K5 Mod Studio:** `v1.0-RC77`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.84` (identity ride-along; no APF surface change)

## New: ★ Create a Play

The last navigation entry opens a five-step wizard: pick a team's playbook, lay
out a formation (modern templates, drag to move, click to swap or change a
position), choose run or pass, draw routes by dragging from a player or pick a
job from his menu, then replace outdated stock plays and build the disc. The
Play Designer and Design Formation panels sit underneath for fine control. The
PLAY format is decoded end to end and the game's own validator is ported, so
nothing the game would reject is ever staged.

Authored passes now play as passes: the header class bits are written from a
stock play of the same QB-chain shape (the earlier build cloned a run header,
which the game played as a QB draw).

## New: Throw Distance & Arc

Sliders & Gameplay → **Throw Distance && Arc**. Two sliders over the game's own
arm-strength curve tables in `default.xbe`:

- **Deep-ball ceiling** (55 = retail … 100 yards at 99 arm). The curve is
  re-spaced as a scale: at 80, a 70 arm throws 41, an 85 arm 52, a 95 arm 66
  and a 99 arm 80 (retail 40 / 45 / 50 / 55).
- **Pass arc** (0 = retail … 100 %). Slows the last 25 yards of the ceiling so
  long balls hang longer and climb higher; 40 % at an 80-yard ceiling is a
  5.0 s, 33-yard-high bomb.

Read a `default.xbe` or a disc image, watch the per-arm preview (ceiling, hang
time, apex), write a patched **copy** (never the source) with the section
digest recomputed and every byte verified. xemu-only, like Bump strength.
Witnessed in xemu with gdb: retail Vick pinned at 55.0 yd; the tuned copy
launched 80.0-yard, 5.00-second balls. CLI: `tools/nfl2k5_throw_distance.py`.

## Housekeeping

- Pre-source browse-only facade implements the extended Playbooks contract.
- The formation/play writer tests now run under CI's per-file runner.
- Versions: 2K5 `1.0.0rc77`, APF `0.1.0-alpha.84`, updater tag `beta-53`.

# beta-51 — RC75 / alpha.82

**Date:** 2026-08-23

**2K5 Mod Studio:** `v1.0-RC75`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.82`

## New: the jersey bump-map workspace

NFL 2K5 ships a tangent-space bump map for every uniform — jersey, pants,
sleeve, sock — and until now nothing in the editor could touch them. Uniforms
& Equipment → **Bump Maps** changes that:

- Browse all **634 uniform packages** and their four bump slots, discovered
  from the disc's own entry tables (no hardcoded offsets).
- **Export** any slot to PNG; **import** an authored PNG with a before/after
  preview; **write** it into a COPY of your disc image at the exact retail
  footprint — mip chain rebuilt with box filtering, NV2A swizzle, VC-LZ
  recompressed to fit the fixed span, wrapper preserved except the loader
  scratch word, then independently re-decoded and verified pixel-for-pixel.
- The three packages whose entries **cross a pack boundary** (outers 3625,
  3832, 4136) are segmented at the boundary and fully editable — the whole
  uniform corpus, 634/634.
- The retail image is recognized by full SHA and stays browse/export-only.

## New: bump authoring templates

"Save authoring template" writes a flat-normal starter PNG at the slot's exact
size. For bump_jersey it marks the retail collar/shield UV positions — front
V-neck collar band, NFL shield tab, back round collar — so FUSE-collar detail
can be authored where the retail art puts it. Zone labels carry their honest
grade (observed pixels proven; semantic labels inferred) in the metadata.

## New: bump strength editing

How strongly a bump renders is a per-material detail-scale float in
default.xbe (jersey 0.1, pants 0.3, sleeve shares jersey's float, sock fixed
at 0). The Bump Maps panel reads those values by byte pattern (never blind
offsets) and can patch a COPY of the XBE: float immediates rewritten, the
touched section digest recomputed, byte-diff confinement verified. Honesty
labels are built in: the RSA signature cannot be regenerated, so a patched
XBE is xemu-only, and sock stays read-only because its retail encoding has no
room for a float. Jersey/sleeve share one float and are kept in sync in the
UI for the same reason.

## New: Saves & Sliders

Uniforms & Equipment → **Saves & Sliders** edits the settings block that both
Settings1 and Franchise1 saves carry:

- All **21 gameplay sliders** — Human/CPU Blocking, Passing, Running,
  Coverage, Pursuit, Tackling, Kicking, Fatigue, Catching plus Injury,
  Fumble, Interception — with editable / mirror / consistent write modes.
- The **franchise year field** on Franchise1 saves.
- Output is always a copy: a mutated SAVEGAME.DAT plus a fresh 20-byte EXTRA
  signature, computed with the title-static key derived from your own
  default.xbe — the game verifies this signature at load, so both files must
  go back into the container together.
- The same lane ships as a CLI (`read` / `edit` / `writeback`), including
  write-back into a copied raw Xbox HDD image that touches only the
  container's own extents and refuses saves whose stored EXTRA does not
  verify.

## New: the stadium glTF loop closes

Stadium scenes already export to glTF with every game texture embedded and
tagged by its canonical id, and same-topology vertex edits already import
back. Now the textures come back too: **Apply textures from glTF** maps each
Blender-edited image to its stadium texture slot (by id, falling back to the
material name when extras were stripped) and writes it through the same
fixed-allocation P8 route the Stadiums page uses. Export → edit in Blender →
apply back, entirely in the GUI — no terminal.

## Speed: hundreds of edits no longer re-parse the world

Every structural parse that used to repeat per edit is now memoized behind an
identity key (path + device + inode + size + mtime): the bump index volume,
the retail-image probe verdict, the outer-archive parse shared by every
texture adapter, the 55MB uniform inventory (now with an O(1) row index), the
compatibility-report digest, and the large-file hashes the helmet/nameplate/
face/field-art/portrait importers recomputed per edit. Per-edit structural
cost is O(1) after the first edit; the caches are pinned by deterministic
reuse/invalidation tests, not wall-clock timing.

## APF 2K8: add many formations, shared-play honesty

- **Add Formation no longer stops at one.** Each add takes the next free
  slot; the writer is proven to ship N additions in one build (verified on
  the retail disc with two formations added to O-SinglebackAce).
- **Build receipts flag shared-play records and book supply rows** — the
  mechanism behind "my package edit works in Practice but only rarely in
  Quick Game": Quick Game resolves plays by row lookup over shared play
  instances, so an edited record only shows when the CPU calls a record
  owning its own instance.
- Honest boundaries: the user-playbook crash with cut/CPU-only content and
  the O-Shotgun WR depth flip are not provable offline; both ship with their
  decisive in-game experiments documented.

# beta-50 — RC74 / alpha.81

**Date:** 2026-08-22

**2K5 Mod Studio:** `v1.0-RC74` (updater identity only; no 2K5 functional
change)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.81`

## Fixed: the Add / Change formation dialog was unreadable

The dialog kept the studio's light-on-dark text on top of Windows' light
dialog background, so its explanation, play list, and OK / Cancel buttons
were nearly invisible. It now carries the studio dark theme end to end, the
play list selection is visible, and the accept button is highlighted and
labeled with what it does: Add formation, or Apply change. No more blind
clicking for the confirm button.

## Fixed: Add a formation crashed after picking plays

Choosing plays and confirming raised `AttributeError: 'QListWidgetItem'
object has no attribute 'row'`. The dialog now resolves selected rows
through the list widget, so adding a formation to a stock CPU book works
again.

## Fixed: dim Close button in the roster alias owners dialog

A duplicated color in that dialog's button style let a low-contrast gray
win. The button is now readable and gains a hover state like the rest of
the studio.

## Clarity: Who lines up finally explains itself

The tab now says what its words mean. Every formation stores 11 on-field
slots; every play stores one route per slot, even when the play uses no TE.
A role is the roster position the engine plugs into a slot; only role 8 =
TE and role 9 = WR are proved, the rest stay numbered. Routes belong to the
play's slots and are shared by every formation that stores the play, which
is why the stock Weak Dive out of Gun: Pair Slot Left (the same oversight
ships in 2K5) sends the TE on the FB's fake-handoff route, and why
Assignment Routes cannot fix one formation alone. Runtime visibility of the
role map remains unproved and is labeled so; Build, then check in Xenia.

Your original game remains untouched by every change above.

---

# beta-46 — RC69 / alpha.78

**Date:** 2026-08-15

**2K5 Mod Studio:** `v1.0-RC69` (updater identity only)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.78`

## Fixed: both broken Beta 45 Playbooks actions

Beta 45 added two buttons that imported a research module only when clicked.
That module was present in the source checkout but absent from the packaged APF
application. The 3rd-and-long button therefore opened the crash reporter; the
WR3↔TE export failed in its background task. Repeating the 3rd-and-long click
raised the same exception again, but duplicate crash dialogs are suppressed,
so the button appeared dead until restart.

The 3rd-and-long button now opens a normal status dialog directly and works on
every click. The dialog says what Mod Studio knows in ordinary language: no
editable setting for the reported user-team/CPU difference was found in the
playbooks or director data; the behavior appears to live in `default.xex`,
which Mod Studio does not patch.

## Withdrawn: the raw WR3↔TE `.bin` export

The exported file was a 182,096-byte standalone copy of an internal formation
table. It was not a playable mod. Mod Studio had no importer for it, Build Game
Folder did not consume it, and copying it into the game folder could not work.
The byte-level experiment remains in the developer research code, but the
product no longer presents it as a usable workflow.

## Release-packaging regression guard

The clean APF runtime gate now parses every staged Python file and verifies that
each literal `mod_editor.*` import resolves inside the staged package, including
imports inside callbacks. A source-tree test can no longer hide this exact
class of missing packaged dependency.

No game writer changed. Your original game remains untouched, and copied or
studio-built `0A` folders still cannot be used as source.

---

# beta-42 — RC65 / alpha.74

**Date:** 2026-08-13

**2K5 Mod Studio:** `v1.0-RC65`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.74` (no functional change — it carries the
new shared updater identity)

## Fixed: pants, which Beta 41 missed

Building a pants replacement still refused:

```
The modded XISO could not be built. pants: VC-LZ stream needs more than the
75472-byte bound
```

Beta 41 wired the palette ladder into live helmet, jersey, scorebug and
create-team field art — **and not pants.** The sweep that found the offenders
was truncated, the resulting list was hard-coded into the test meant to guard
it, and the test therefore agreed with the omission. Pants now uses the ladder
like its siblings.

**The guard test now derives its list from the tree.** Anything that compresses
into a bounded VC-LZ span and still quantizes at a flat 256 fails the suite, so
a missed or newly added importer cannot inherit this bug by being forgotten.

## Fixed: the failing edit is named by what you picked

Beta 41's message said only `pants:`. A uniform edit carries no selector, so
the label fell back to the bare kind — useless in a project with several. It
now reads:

```
pants (asset_code=NE, side=home, variant=0): VC-LZ stream needs more than the
75472-byte bound
```

## What the pants slot can actually hold

Pants are the tightest uniform slot: 177,024 decoded bytes have to fit a
75,472-byte compressed span, a 2.35:1 ratio. Measured against that bound:

| Source art | Fits at |
|---|---|
| Flat team colours, hard edges | 2–16 colours, with room to spare |
| Shaded cloth with soft gradients | 64 colours |
| Photographic fabric with fine noise | 8 colours |
| Pure random noise (worst case possible) | 4 colours |

So a pants replacement now always builds. Detailed or noisy source art will
come through with a reduced palette — if colour fidelity matters, remove film
grain, fabric noise and long smooth gradients from the PNG before importing and
more of the palette survives.

## Verification boundary

The ladder starts at 256, so a build that succeeded before produces the same
bytes. No new asset became editable.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC65-20260813.tar.gz` | 11,052,675 bytes | `dec0d23c0bef46ad1904987399bdf406ecd295695816d999049cddee90219ab0` |
| `2K5-Mod-Studio-1.0.0rc65-Setup.exe` | 56,695,191 bytes | `aef730ae3e0c180cd45c50784135a906208e03b5d53a24a2891edcd8d674a36d` |
| `apf2k8-mod-studio-0.1.0-alpha.74-20260813.tar.gz` | 1,805,994 bytes | `3aae4468350ff4962797d3adc0e43aa8af2b2a0a6d8b17766645af8452c1cc7c` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.74-Setup.exe` | 52,678,234 bytes | `c0c3619ab048a00c4ab1d4ef3c3c4c2b893d44b2d1873282737a2189e2392dcc` |

---

# beta-41 — RC64 / alpha.73

**Date:** 2026-08-13

**2K5 Mod Studio:** `v1.0-RC64`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.73` (no functional change — it carries the
new shared updater identity, so its bytes differ and its version moves with them)

## Fixed: a texture that will not fit is quantized down, not refused

Building could stop with:

```
The modded XISO could not be built. VC-LZ stream needs more than the
34416-byte bound
Nothing was changed in your source XISO.
```

34,416 is the stored size of a **live helmet TXTR**. Two things were wrong.

**The importer gave up.** A perfectly valid P8 image can be impossible to
encode with a 256-entry palette even though a visually equivalent lower-colour
version fits the retail span. `quantize_levels_to_vc_lz_bound` already handles
that — it tries palettes from 256 down to 2 and takes the first that fits — and
it is what the sleeve, digit, all-texture and Crib importers already use. Four
importers that compress into a bounded span still called the plain 256-entry
quantizer and hard-failed: **live helmet, jersey, scorebug, and the compressed
create-team field art.** They now use the ladder.

**The ladder starts at 256, so anything that already built is byte-for-byte
identical.** Only art that used to fail outright now steps down to a smaller
palette. If even a two-colour version cannot fit, the message says so and says
what to simplify.

The three P8 importers that write *uncompressed* fixed spans — team select
card, player portrait, Crib team photo — have no VC-LZ bound to overflow and
were deliberately left alone.

## Fixed: every build failure names the edit that caused it

The message above named no team, no slot, and no image, in a build that can
carry dozens of edits. The dispatcher knew each edit's kind and selector and
attached neither. Now any importer failure reads as, for example:

```
live_helmet live-helmet:NE:home:0:helmet00: VC-LZ stream needs more than the
34416-byte bound
```

## Verification boundary

No new asset became editable, and no writer's guarantees changed. A build that
succeeded before produces the same bytes.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC64-20260813.tar.gz` | 11,051,750 bytes | `7c26461169f5ecc241e63b9a9abcc9e50ade67b58a0de90da288c9d49a56b967` |
| `2K5-Mod-Studio-1.0.0rc64-Setup.exe` | 56,690,933 bytes | `6a43aace816d456d8bc5133e7fc8eca6d1dd7ad201580a2e0872cc984587ac54` |
| `apf2k8-mod-studio-0.1.0-alpha.73-20260813.tar.gz` | 1,805,902 bytes | `dbcae611e385d3f110ad350b7bff962c09af2138c3fe206ba7ae33dadd46e819` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.73-Setup.exe` | 52,682,862 bytes | `6fe9aa947af243ee9f1e836abcbffed77351e1020b0624c85bc22cd86accddcc` |

---

# beta-40 — RC63 / alpha.72

**Date:** 2026-08-13

**2K5 Mod Studio:** `v1.0-RC63`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.72` (no functional change — it carries the
new shared updater identity, so its bytes differ and its version moves with them)

## Fixed: Team Kit equipment edits can be built

Swapping textures in the Team Kit panel and then building produced:

```
Unknown uniform asset ID: tset:3660:4:0:socks00
Nothing was changed in your source XISO.
```

`tset:3660:4:0:socks00` is **Socks 00 — Cincinnati Bengals Home**, a 64×64
uniform-equipment texture. Only the uniform *sets* live in the uniform catalog;
the Team Kit's 45 package-local socks, elbow pads, gloves, long sleeves, shoes
and wristbands come from the extended visual catalog, together with `p8:`
textures, portraits, live faces, create-field art and the scorebug — **47,237
assets the build could not name.**

Staging worked, which is why this was only discovered at build time: the panel
hands `replace()` an already-resolved asset object. Every later step
re-resolved the ID *string* through the uniform catalog. So **Build Modded
XISO, Save Project, Load Project, Import Team Kit, Undo's restore and Revert
All** all refused equipment edits, and a session could accumulate a large
amount of work with nowhere to put it.

All of those steps now resolve through `Nfl2k5ProductVisualCatalog`. A uniform
edit resolves to the identical object it always did, so jersey, helmet and
digit edits are byte-for-byte unchanged.

If you have a session full of refused equipment edits: they are still staged.
Install this build, reopen, and build — you do not need to redo them.

**Where it came from.** The routing dates to the first public beta. It became
reachable in RC49, when Team Kit gained the equipment parts, so it only bit
someone who edited socks rather than jerseys. Reported against Beta 39.

## Verification boundary

No writer changed. No new asset became editable. The fix is which catalog
answers "what is this asset ID", and the aggregate is built from the session's
own uniform catalog so a uniform ID cannot resolve to a different object than
before.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC63-20260813.tar.gz` | 11,048,530 bytes | `f1a83f4ec2157ca44e9e609d5ee8257fd2127f554d2acc4f710544300a841d35` |
| `2K5-Mod-Studio-1.0.0rc63-Setup.exe` | 56,691,503 bytes | `4917d9743c8e2752603edfd8707273a497221f92799ec971498847d64aeb0f95` |
| `apf2k8-mod-studio-0.1.0-alpha.72-20260813.tar.gz` | 1,805,774 bytes | `8b1301d906ccaab13c283f987ec44db94ceb0afe105f9f91258eb84b4fb72233` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.72-Setup.exe` | 52,684,454 bytes | `60e306c526ebc0d100eb0b54de68e5c055778206bf9d8346f581c4d1c9224b56` |

---

# beta-39 — RC62 / alpha.71

**Date:** 2026-08-13

**2K5 Mod Studio:** `v1.0-RC62` (unchanged)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.71`

## Fixed: Save Project now saves Fine-tune Plays

Reported by **Urianus** against alpha.69 and again against alpha.70. Since the
panel shipped in Beta 32 its staged edits lived only in the panel's own memory.
Nothing wrote them into the session, so Save Project produced a file that
silently did not contain them and reopening it showed an untouched playbook.

Every staged change — a play ticked in or out, a tagged slot carried onto
another play, a tagged slot moved — is now a project modification carrying only
selectors (an outer entry, a record, and play indices; never a byte of your SPLB
resource). It round-trips through the project archive and the main build, so
playbook edits and uniform edits can land in the same volume. Opening a project
selects the book its edits belong to. Switching books with work staged now asks
instead of discarding silently.

## Changed: emptying a formation now leads with what it does in game

Also **Urianus**, on alpha.70: after emptying the formations without a TE in
`O-ManBlock`, the CPU lined up personnel packages that book does not contain
(00, 10, 01, 12, 11) and one the game does not ship at all (02), running plays
that are not in the book. It happened whenever the director selected an emptied
formation; untouched books behaved normally. Plays are not bound to formations
— he moved an offensive play into a defensive book and it ran — so a formation
that stores nothing does not make the director skip it. It makes the director
call something the book never listed.

The static facts are unchanged: count `0x84a8ac30` returns 0 and get-nth
`0x84a8bd20` returns null for an empty record. **That was never a proof that the
director handles the null well, and the previous copy read as though it were.**
The confirmation now opens with the report, the compile report carries
`empty_record_runtime_safe: False`, and emptying **every** populated formation
in a book is refused outright.

To keep a formation and put TEs on its tagged slots, add those plays and use
**Move tagged slot…**. Nothing has been reported against that path.

## Fixed: a refused uniform replacement names its target

Reported by **davidhbui**. Staging several shoulder replacements produced, about
forty seconds per target:

```
rebuilt shoulder IFF exceeds fixed allocation by 9231 bytes
```

Nothing in that names a team, slot, outer entry, or source PNG, so fixing one
file and rebuilding produced `9292 → 9231` — an apparent 61-byte improvement
that was actually a *different* slot failing. The message now reads as the slot,
the outer entry, the allocation, and the slot's real compressed budget, and a
build with several over-budget targets reports all of them at once instead of
stopping at the first.

The uniform panel also shows each shoulder slot's budget and its rank among the
24 before anything is staged. His measurement is why: a slot's budget is
retail's own compressed payload plus a small sector slack, and the payload
dominates — so outer 182, which has the *most* visible free space of any
shoulder slot, is 18th of 24 for capacity and refuses a detailed mask that
outer 184 and 198 accept. Picking by "which has the most room" picks the worst
slot.

## Fixed: Field Art — outer 6 is not a shared layer

Also **davidhbui**. The category blurb and
`docs/product/APF_FIELD_ART_STOCK_NFL_WALL.md` both called outer 6 a **shared**
endzone layer. Decoding it shows bespoke per-team artwork — two figures in
wide-brimmed hats with bandoliers and revolvers, a masked figure, a hitching
rail — structurally identical to the other 117 packages. It is simply the pair
whose writer was proved first. The old wording told users that editing it
changed a common layer when it repaints one specific team's endzone. Withdrawn.

Endzone layers are also **region masks, not artwork**: pure red/green/blue
region selectors over black, with shader-driven colours in game. The panel now
carries the same authoring contract the uniform masks do.

## Added: export endzone contact sheet

A team's endzone cannot be found by searching. The nicknames are not on the
disc at all — `Redcoats` appears zero times in `0A`, `0B`, `1A`, `1B` and
`default.xex` across ASCII, UTF-16BE and UTF-16LE; it exists only in
`Roster.ROS`. **Export endzone contact sheet…** renders all 118 packages into
labelled sheets so a package can be identified by eye in one action.
Thirty-one packages are already identified — davidhbui's list, each one
confirmed here by decoding the retail volume — and those rows carry the team
name. Unidentified packages show their index rather than a guess.

## Improved: the playbook panel is readable again

Fine-tune Plays keeps its complete static record, including every withdrawn
candidate, but 11,360 characters of executable addresses no longer word-wrap
between the play list and the buttons. They are behind **Research pins**.

## Fixed: alpha.70 test regression

The Title Update 1.1 button read `settings.title_update_path` unconditionally,
which crashed every window test whose launcher-settings double predated the
field — 28 tests red in the shipped Beta 38.

## Verification boundary

Nothing about CPU play-calling became proved. `wr3_te_package_sub_proved`,
`APF_3RD_AND_LONG_PLAY_CHOICE_PROVED`, `cpu_behaviour_runtime_proved`, and the
full package-map role legend all remain False. No per-team endzone writer ships;
Field Art stays browse/export-only apart from the six offline-proved slots.

## Downloads

Both 2K5 archives are rebuilt because the shared provider self-integrity pins
changed with the three uniform transports. RC62's behaviour is unchanged.

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC62-20260813.tar.gz` | 11,045,717 bytes | `f7171575a3ac1823f0fc47cbba2871d9272420e57667661c8265dad1275ad63f` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,684,489 bytes | `b77d6059ff76f66dc95dfa83928795c45f70f22075b1e210c128f94259875e13` |
| `apf2k8-mod-studio-0.1.0-alpha.71-20260813.tar.gz` | 1,805,592 bytes | `9470156401bf07c61fb33bd1f2a2d5f6972d9f929240ad0e7efab5d5937a0c18` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.71-Setup.exe` | 52,680,145 bytes | `5b121966210e616223c3586428c95c0cad02a4f6124c33b5f5966ad3d7ecc244` |

---

# beta-38 — RC62 / alpha.70

**Date:** 2026-08-12

**2K5 Mod Studio:** `v1.0-RC62` (unchanged)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.70`

## Fixed: tagged-slot move onto an added play

Moving a tagged slot onto a play added in the same request now verifies. The
old check treated a move as a Y-swap against the original book, so a new play
(no original Y) failed even when the compiler was correct. That was the
X-43Blitz Bear case: add play 560, then hand it tagged slot 1 from play 542.

## Added: empty a formation

**Empty this formation…** removes every stored play in one request. Tagged
slots are shed because `min(4, 0)` is 0. The record trailer is not touched, so
the formation is still named in the book. The executable's count (`0x84a8ac30`)
and get-nth (`0x84a8bd20`) then return 0/null, so the four tagged plays cannot
come from that record. Which formation the director selects next is still
runtime-unproved. This is not a WR3→TE package substitution.

## Added: title update 1.1 for Xenia launch

**Title Update 1.1…** pins the Xbox 360 LIVE installer (title `54540807`,
content type `000B0000`) by size and SHA-256 and copies it into this session's
isolated Xenia content folder on Launch. The 1.1 update is required on
Xbox/Xenia and never shipped for PS3. A TU installed only in a standalone
Xenia folder will not apply here.

Davidhbui's Beta 36 mask-preview follow-up (cache-hit notes, visible exports,
empty retail slots) was already complete in Beta 37 / alpha.69.

## Verification boundary

Focused playbook, launcher, updater, and UI tests pass (135 passed, 11 skipped).
The retail-free APF release gate passed on the staged tree (196 files). The
Linux archive and Windows installer below were built from that stage. No retail
data is added to the repository or release archives.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC62-20260812.tar.gz` | 11,032,707 bytes | `1f681899452f4cb70a86d60769316cdd02091728b614cc39bab8e63e7762a235` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,683,037 bytes | `a0b54bc5cc760576c35f2f1d3cd399c9d540523871f93b9f25d34f63ab64102c` |
| `apf2k8-mod-studio-0.1.0-alpha.70-20260812.tar.gz` | 1,751,122 bytes | `fa224fc3d3640b7d30c1c3a0991c4d92574e639d5c7cc420172fd304cd3e979c` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.70-Setup.exe` | 52,652,594 bytes | `b30e97fe6ac032aa15c609ec809f3017391926f7d184253fe562961b691efdab` |

## beta-37 — RC62 / alpha.69

**Date:** 2026-08-12

**2K5 Mod Studio:** `v1.0-RC62` (unchanged)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.69`

## Fixed: preview notes, visible exports, and empty retail slots

Beta 37 completes the mask-preview follow-up against Beta 36:

- The explanation for display-only opaque alpha survives private preview cache
  hits, so it remains visible every time a mask is opened.
- Uniform, generic TXTR, and embedded scene-texture PNG exports are visible in
  ordinary image editors. The export changes only display alpha; the existing
  writer-side guard restores retail all-zero alpha before encoding.
- A source whose decoded RGBA channels are all zero is labeled as an empty
  retail slot instead of looking like a failed preview. This is why a genuinely
  empty jersey slot can remain blank without being reported as a decoder bug.

## Improved: playbook contract

Fine-tune Plays now says exactly what the offline-proved writer edits: stored
SPLB membership for a formation. The UI no longer claims that the game will
call those plays at runtime; that consumer remains unproved. The shared updater
identity is also corrected from the stale Beta 33 tag to `beta-37`.

## Verification boundary

Focused preview, playbook, updater, and UI tests pass. Full suite, release
gates, deterministic archives, and local launcher smoke tests are recorded
below after packaging. No retail data is added to the repository or release
archives.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC62-20260812.tar.gz` | 11,032,707 bytes | `1f681899452f4cb70a86d60769316cdd02091728b614cc39bab8e63e7762a235` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,683,037 bytes | `a0b54bc5cc760576c35f2f1d3cd399c9d540523871f93b9f25d34f63ab64102c` |
| `apf2k8-mod-studio-0.1.0-alpha.69-20260812.tar.gz` | 1,746,351 bytes | `ec90a59ec81fedab3c6c7aa55479e0f9fdcaa3f4e654ac41ee12a9e9afc08d0a` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.69-Setup.exe` | 52,640,035 bytes | `77e2d5f91d86f1f362c83d5280122d697fb08a2352a4b6ecd63a7b88a70e6f45` |

## beta-36 — RC62 / alpha.68

**Date:** 2026-08-11

**2K5 Mod Studio:** `v1.0-RC62` (unchanged)

**APF 2K8 Mod Studio:** `v0.1.0-alpha.68`

## Fixed: jersey and shoulder previews are visible

Retail `jersey_color` and `shoulder_color` textures store their mask data in
RGB while leaving alpha at zero for every pixel. The old preview treated that
storage alpha as transparency and showed a blank checkerboard.

Beta 36 force-opaques only that all-zero alpha during preview, records a clear
“shown opaque” note in the panel, and invalidates the old preview cache. Raw
PNG exports remain source-faithful. When a displayed PNG returns through the
writer, the original all-zero alpha is restored before BC3 encoding, so the
display convenience cannot alter the game payload.

The low-level `helmet_color` message was also corrected: DXN (format 49) is
supported by the asset layer's dedicated layout decoder, not by the generic
base-format decoder that reports the PORTME.

## Fixed: normal-user Windows builds

The Windows installer remains per-user and uses `RequestExecutionLevel user`.
Runtime staging no longer depends on an administrator-only symbolic link:
staged sibling packs try symlink, then hardlink, then a verified copy when the
game and output are on different filesystems. Playbook output uses the same
fallback. Export commits go through the platform no-replace publisher, which
works on filesystems such as exFAT.

Windows users should choose a new empty output folder under Documents or
Desktop, not Program Files, the original game folder, or a disc. No
administrator mode is needed.

## Field Art discoverability

All 235 stock endzone layers (118 `endzone_l0` and 117 `endzone_l1`) are
surfaced by the Field Art inventory for browsing and export. The focused editor
continues to offer only the two shared outer-6 layers whose copied-volume
writer is pinned and proved; per-team replacement remains explicitly
unproved rather than being presented as a safe edit.

## Verification boundary

Targeted local regression tests cover the display/encode alpha split, cache
routing, DXN messaging, Field Art UI, portable publishing, provider pins, and
Windows fallback code. The only local ISO available for this run was a
PlayStation 3 APF image (`All-Pro Football 2K8-001.iso`); the source loader
correctly refused it as non-Xbox data, so no Xbox 360 texture decode/build claim
is made here.

## Downloads

| Asset | Size | SHA-256 |
|---|---:|---|
| `2K5-Mod-Studio-v1.0-RC62-20260811.tar.gz` | 11,032,048 bytes | `96f62e24871f314cdeaed07ccfdb1c8565b3d5c6e78bb6cc9b0e869fba5f94c5` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,674,441 bytes | `ca3f1041f3cd7158b08e0470ce4d7beb1a80235ecd281c511f45a3e0e5a3cf19` |
| `apf2k8-mod-studio-0.1.0-alpha.68-20260811.tar.gz` | 1,745,759 bytes | `449291a4a1aa18490bb11332b51c0ce1f690e3a72200a853815e0138b9183b20` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.68-Setup.exe` | 52,634,090 bytes | `6b805d4b91ba76901aef9500be9a9f2d3e4d0c62668823e6d73a0931ef981252` |

## beta-35 — RC62 / alpha.67

**Date:** 2026-08-11

**2K5 Mod Studio:** `v1.0-RC62`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.67`

Two APF team-logo fixes, both from bug reports against Beta 34. Nothing in 2K5
changed this release.

## Fixed: the second, smaller logo in the corner of your crest

If you built a team crest and looked at a helmet from certain distances, you saw
your logo with a smaller copy of itself tucked into a corner. Look from further
away and you got the retail logo back, as though the mod had not applied at all.

Both were the same mistake, in how the writer addressed the crest's chain of
smaller copies (its mip levels).

The chain moved from one level to the next by multiplying the level's aligned
width and height. That is not how the Xbox 360's GPU lays them out. Every stored
level starts on a 4096-byte boundary, and — only at two bytes per texel, which
is exactly what a crest is — a 32x32 tile is scattered across 0xC00 bytes of
address space instead of packed into 0x800.

Both errors point the same way, so the shared tile holding the 16x16 and smaller
levels was addressed 0x800 bytes *inside* the 32x32 level. Regenerating the chain
wrote those small levels through the 32x32 one — that is the smaller logo in the
corner — and left the real tail untouched, so the smallest draws kept serving the
retail crest. How much of the 32x32 level is overwritten depends on the artwork:
427 of its 2048 bytes for the image the fix was first derived from, 325 for the
real team crest rebuilt to check it.

The corrected chain accounts for the retail-declared mip length of 0x2C000
exactly, with nothing left over. The old one reached 0x2B000 and explained the
missing page away as padding, which is the clue that was there the whole time.

**If you built a crest with Beta 32, 33 or 34, rebuild it from the same PNG.**
No re-authoring — just Build again.

**Only crests were affected.** The uniform, wordmark, pants, shoulder and helmet
writers all use block-compressed formats at 8 or 16 bytes per block, where both
corrections are no-ops. Their output is unchanged byte for byte, and there is now
a test that says so.

**Xbox 360 only.** This fix is Xenos texture addressing — the 360 GPU's tiling,
its packed-mip layout, its 4096-byte subresource alignment. APF 2K8 on PS3 does
not store its textures that way, and these tools do not read or write the PS3
build at all. If you mod a PS3 copy, nothing here changes it, and a crest that
still looks wrong there is not this bug coming back.

The layout also refuses outright to hand back a chain whose levels share bytes,
so this class of bug fails closed instead of reaching a crest.

## Team Logo can author both crest layers

A crest is not one picture. It is six region masks split across two textures:
`logo_l0` carries regions 0-2 and `logo_l1` carries regions 3-5, and 79 of the
game's 118 crest packages use both.

**Export both layers** could already take a crest apart. Putting one back needed
`tools/apf_logo_patch.py --png --png-l1` at a command line, which meant those 79
packages were effectively read-only inside the app.

**Logos & Team Art → Team Logo → Replace both layers…** now imports the two PNGs
together. Each is sized the way a single import is sized, and both are written
into the `uniform_logo_NN` package and the matching `uniform_logocache` slot by
the same proved writers, in one copied `0A`.

### A single image no longer gets copied into both layers

Dropping one image used to write that same mask to `logo_l0` *and* `logo_l1`,
which selects all six regions and draws your mark once per region in six
different flat colours. One image now goes to `logo_l0` and clears the detail
layer, so the mark is drawn exactly once.

That is what the panel's own export dialog already told you happened, and what a
full project Build already did. The copied-volume Build was the odd one out — so
the same staged image could give you two different crests depending on which
button you pressed.

`tools/apf_logocache_patch.py` gains the `--clear-l1` flag its Python API already
had, so the cache can be told the same thing as the package.

## What is proved, and what is not

The defect was reproduced here before this release shipped. A real team crest
was built twice from a retail disc, once with Beta 34's code and once with this
one, and every level of both was read back out and compared:

| level | size | built with Beta 34 | built with this release |
| --- | --- | --- | --- |
| 0-3 | 512² to 64² | exact | exact |
| 4 | 32² | 325 of 2048 bytes wrong | exact |
| 5-9 | 16² to 1² | byte-identical to retail | exact |

Decoded back to pictures, Beta 34's 32x32 level draws the mark with a second
offset copy of itself, and its 16x16 and smaller levels are the retail logo
pixel for pixel. That is both halves of the report, and they are gone here.

Those levels are not merely present — they are sampled. Xenia's texture fetch
constant for that crest reports `mip_min_level=0`, `mip_max_level=9` and a
`linear` mip filter, so the GPU blends through the whole chain and the levels
Beta 34 left retail were being drawn.

Also checked offline: every level's byte range against every other level's, the
derived chain against the retail-declared allocation exactly, the single-image
treatment clearing the detail layer at all ten levels and rebuilding its chain,
and the two-layer import end to end through to the arguments both writers get.

**Not done: a side-by-side photograph of a helmet in the emulator.** The game
was booted on both builds and reached live play, but the capture is driven by
timed button presses and the two runs did not land on the same screen, so there
is no honest frame-to-frame comparison to show. If you have a crest built with
an earlier beta, rebuilding it and looking at a helmet is still worth doing.

## Credits

Both bugs were reported by **davidhbui**, including the observation that the
artifact tracks zoom level — which is what pointed at the mip chain rather than
the base texture.

## Downloads

| file | bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC62-20260811.tar.gz` | 11,032,048 | `96f62e24871f314cdeaed07ccfdb1c8565b3d5c6e78bb6cc9b0e869fba5f94c5` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,674,441 | `ca3f1041f3cd7158b08e0470ce4d7beb1a80235ecd281c511f45a3e0e5a3cf19` |
| `apf2k8-mod-studio-0.1.0-alpha.67-20260811.tar.gz` | 1,742,447 | `52e8b35b946f854f80cbd68449b0c97d4d236204c8a4eb8cc596440e7c7f876f` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.67-Setup.exe` | 52,638,991 | `0f25f1a8f354938dc4ebe59f3a642d25feb8582f3e716ef8b68f71c1b100bb78` |

Windows installers are self-contained and reproducibly built, but not
code-signed; the installer explains the Windows warning before installation.

These archives are retail-free. They contain no game data of any kind.

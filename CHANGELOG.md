# Changelog

Release-level history. Per-product detail lives in
[`STATUS.md`](STATUS.md) (2K5, plus the published-asset receipts) and
[`docs/mod_editor/apf2k8_mod_studio_changelog.md`](docs/mod_editor/apf2k8_mod_studio_changelog.md)
(APF).

Product versions and release tags are deliberately separate. A tag like
`beta-3` names a *published set of archives*; the editors inside carry their own
versions (`v1.0-RC36`, `0.1.0-alpha.39`) and only change when their code does.

---

## beta-44 — 2026-08-14

**Urianus can edit every stock book, the TE-workaround copy is gone, and
Build writes into the folder Xenia already loads.**

2K5 is `v1.0-RC67` (updater identity only). APF is `0.1.0-alpha.76`.

- Fine-tune Plays does not choose personnel. Play names are not positions.
  `50 TE Corner` in I Spread still fields 0 TEs. The old “add TE plays and
  Move tagged slot” sentence is withdrawn.
- A project can hold every stock book. Switching books no longer discards
  staged work. Build compiles each book separately into one copied `0A`.
- Emptying an exact ` Flip` twin (Ace / Ace Flip) empties both. Weak I
  Jokers Flip Pair is not that twin. Emptying only one hung on load.
- Empty-formation copy now includes the 2026-08-14 defensive / O-Ace Ace
  Empty reports. Still not a director writer.
- Build writes into the folder you pick and can replace a previous build
  so Xenia keeps the same path. No more `APF2K8-Mod-TIMESTAMP` child.
  Close Xenia first if that folder is open. The retail source is never
  written.
- davidhbui's PS3 texture-parity spec is checked in as
  `docs/product/APF_PS3_TEXTURE_PARITY.md`. Weave / numbers / endzones are
  not in this cut — those are the next writer family, not tonight's
  playbook-safety release.

## beta-43 — 2026-08-14

**Four investigations, one shipped user-facing bug fixed, and the first camera
map either game has ever had.**

Nothing in this release claims runtime behaviour. Every address below was read
from a binary; no game was launched and no patch applied.

### New: Check My Images (2K5)

Beta 41/42 replaced a hard build failure with a palette ladder that quantizes
art down until it fits its fixed VC-LZ span. That is lossy and it shipped
silent. **Check My Images** now sits above Build and tells you, per staged slot,
whether your art fits as authored, will be reduced to N colours, or will not fit
at all — before the build decides it for you.

Finishing it turned up a defect worth more than the feature: the `sleeve` slot
was modelled as 512x256 with six mips like the torso. The real sleeve slot is
**128x128, five mips, with a 64-byte gap between the clean and mud palettes** —
a sevenfold error that would have produced a confident wrong answer for every
sleeve. Slot contracts are now *derived* from the four importers with an
import-time cross-check, not typed into a table.

Also corrected: the torso/sleeve/pants copy now says **do not paint jersey
numbers into the art** — 2K5 draws them from separate digit textures in the same
set (Jersey/Arm 64x64, Helmet 32x32, Nameplate 1024x32), so baked-in numbers
appear twice. And the nameplate atlas is **1024x32 horizontal**, not the 32x1024
the copy claimed; that was a pre-fix transposed value the decoder corrected long
ago and three user-facing places kept.

### New: camera options inspector, both products

`--inspect-camera-options nfl2k5|apf2k8`, backed by a report regenerated from
the executables and validated for byte identity. Before this work the project
had not located a single camera byte.

- 2K5: seven settings, row table mapped, **six presets** (Standard, Far, Side,
  Iso, Blimp, Custom). Camera Distance is a multiplier, Camera Height is world
  units — only Angle is 0..1, and a UI that draws all three the same is wrong.
- APF: nine settings including a **Camera Pitch** axis 2K5 does not have, and
  separate Home/Away toggles.
- **APF ships a sixth preset, `Blimp`, that the menu cannot reach.** Its block
  is fully authored — a camera 3,750 units up, which is what its name says. It
  is unreachable because three immediates hard-code the bound and none of them
  reads `maximum()`.
- Stated as a refusal, not an omission: the gameplay camera has **no asset-side
  representation** in either game. Every camera node in both archives belongs to
  an intro, cutscene, menu or model-preview scene, and no stadium scene contains
  one. **No archive-only mod can change a camera setting or preset.**

### Fixed: the public inspector was mislabelling 12 of 18 sliders

The save is a flat memcpy of the RAM struct, so each slider vector is stored in
its globals' **address** order, where Catching is last — not the menu's display
order, where it is fourth. Twelve of the eighteen vector slots were therefore
published under their neighbour's name. A reader who saw "Human Catching 0.35"
was looking at Human Coverage; the real Human Catching in that save is 1.0.

Order is now derived from the address table rather than assumed, and four checks
that had been asserting the wrong values were corrected with it. The matching
APF defect is fixed too: blob element order is memory order, so Human Catching
is element 9 and CPU Catching element 18 — a writer built on the old indices
would have written Coverage while claiming Catching.

### Fixed: the test harness was hiding red

`conftest` reclassified a failed test as skipped whenever the failure message
merely contained the name of an absent gitignored tree — and six of those names
are ordinary words: `build`, `assets`, `research`, `extracted`, `artifacts`,
`docs/updates`. A real assertion failure reading "... decided at build time" was
reported as `Skipped: game data not present: build`. Matching is now path-shaped.
Measured across 300 files: 245 masked failures before, 245 after, zero outcomes
changed.

### Fixed: the stadium target catalog could no longer be regenerated

Regenerating it failed with "second-target representative edit exceeds outer
allocation". The cause was not drift: the greedy H7A encoder is **2,599 bytes
worse than retail** on that block *before* any edit, so a greedy rebuild
overflows a slot retail itself fits. The generator now re-encodes by preserving
retail's own tokens — pure Python, so the regenerated catalog is byte-identical
on all three platforms rather than depending on a Linux-only binary. The
representative edit's growth dropped from 659 bytes to **59**, and its slack rose
from 1,367 to 1,967: the safety property strengthened.

That unblocked a second correction. The SCNE per-node transform record is
**144 bytes, not 64** — provable two ways, and the shipped catalog had been
pinning a span covering 44% of the real table. At the correct stride every one
of the 96 records checked has `m[15] == 1.0` and zero non-finite components, and
a long-standing "non-finite components" note disappears: those bytes are a
node-name CRC-32 that reads as a signalling NaN at the wrong stride.

### Research landed

- `docs/product/APF_GAMEPLAY_BUG_MAP.md` gains **G15**: the NFL 2K5 franchise
  rookie draft restricts CPU round-1 picks to **4 of 17 positions** — QB/HB/DE on
  picks 1-5, DE/HB/T on 6-32, the same board for all 32 teams. Two gates on the
  round counter replace the scoring formula with a table constant and then read
  only the top three entries. It leaks into the human's Suggested Picks as well.
  APF has no rookie draft at all.
- A method warning was promoted into that file's Honesty section: **"zero
  references" from the function ledger is not evidence.** 32% of the APF ledger's
  rows are truncated to size 8, which had already produced two wrong conclusions.
- `docs/product/CAMERA_MAP.md` is new and complete for both products.
- The catching slider was investigated and **refused**. On 2K5 the value is
  genuinely meaningful above 100 — the arithmetic stays linear — but it cannot be
  written (the save is signed), one press of the "+" control snaps it back to
  100, and it does not generalise: Fumble saturates, Interception inverts, and
  Fatigue is a boolean that is already off at 100.

## beta-42 — 2026-08-13

**2K5 RC65: pants too, and a test that finds the next one.**

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
- APF 2K8 has no functional change; it moves to alpha.74 because the shared
  updater identity is now `beta-42`.

## beta-41 — 2026-08-13

**2K5 RC64: a fixed VC-LZ span fits the art down instead of refusing it.**

- **A texture that will not fit its retail compressed span is now quantized
  down instead of failing the build.** Building could refuse with `VC-LZ stream
  needs more than the 34416-byte bound` — 34,416 is a live helmet TXTR — and
  the message named no team, no slot, and no image.
- `quantize_levels_to_vc_lz_bound` has shipped for a while and is what the
  sleeve, digit, all-texture and Crib importers already use: palettes from 256
  down to 2, first fit wins. Four importers that compress into a bounded span
  still called the plain 256-entry quantizer and hard-failed — live helmet,
  jersey, scorebug, and the compressed create-team field art. **The ladder
  starts at 256, so art that already fit is byte-for-byte unchanged**; only art
  that used to fail steps down. When even two colours will not fit, the message
  says what to simplify.
- The three P8 importers that write uncompressed fixed spans — team select
  card, player portrait, Crib team photo — have no bound to overflow and are
  deliberately left alone.
- **Every build failure now names the edit that caused it.** The dispatcher
  knew each edit's kind and selector and attached neither.
- APF 2K8 has no functional change; it moves to alpha.73 because the shared
  updater identity is now `beta-41`. Reported against Beta 40.

## beta-40 — 2026-08-13

**2K5 RC63: Team Kit equipment edits can actually be built.**

- **Swapping a sock, glove, shoe, wristband, elbow pad, or long-sleeve texture
  no longer breaks the build.** Build Modded XISO refused with `Unknown uniform
  asset ID: tset:3660:4:0:socks00` and left the source XISO untouched — and
  Save Project, Load Project, Import Team Kit, Undo's restore and Revert All
  all refused the same way, so a session could fill up with equipment edits
  that had nowhere to go.
- Only the uniform *sets* live in the uniform catalog. The Team Kit's 45
  package-local equipment parts are `tset:` assets from the extended visual
  catalog, along with `p8:` textures, portraits, live faces, create-field art
  and the scorebug — 47,237 assets the build could not name. Staging worked
  because the panel hands `replace()` an already-resolved asset object; every
  later step re-resolved the ID string through the wrong catalog.
- All of those steps now resolve through `Nfl2k5ProductVisualCatalog`, the
  aggregate written for exactly this and never handed to a session. A uniform
  edit resolves to the identical object it always did, so jersey, helmet and
  digit edits are unchanged. Reported against Beta 39; the routing dates to the
  first public beta and became reachable in RC49.
- APF 2K8 has no functional change; it moves to alpha.72 because the shared
  updater identity is now `beta-40` and its archive bytes therefore differ.

## beta-39 — 2026-08-13

**APF 2K8 alpha.71: Save Project keeps Fine-tune Plays, and three community
reports answered.**

- **Save Project now saves Fine-tune Plays.** The panel was the only place the
  staged playbook edits lived, so a saved project reopened with the playbook
  apparently untouched. Every staged tick, carry, and tagged-slot move is now a
  project modification that round-trips through the archive and the build, and
  reopening a project selects the book it belongs to. Reported by Urianus
  against alpha.69 and again against alpha.70.
- **Emptying a formation now leads with what it does in game.** Urianus emptied
  the formations without a TE in `O-ManBlock` on alpha.70 and the CPU lined up
  personnel packages that book does not contain — and one the game does not
  ship at all — for plays that are not in the book. Static count `0x84a8ac30` /
  get-nth `0x84a8bd20` returning 0/null was never a proof that the director
  handles an empty record gracefully, and the copy said so as if it were. The
  confirmation now opens with the report, and emptying *every* populated
  formation in a book is refused outright.
- **A refused uniform replacement names its target.** "rebuilt shoulder IFF
  exceeds fixed allocation by 9231 bytes" now reads as the slot, the outer
  entry, the allocation, and the slot's real compressed budget. A build with
  several over-budget targets reports all of them at once instead of stopping
  at the first. The uniform panel shows each shoulder slot's budget and its
  rank among the 24 before anything is staged — the budget is set by how
  detailed retail's own artwork in that slot is, so the slot with the most free
  space can be the least able to take a busy mask. Reported by davidhbui.
- **Field Art: outer 6 is not a shared layer.** It is one team's own endzone —
  the package whose writer was proved first — and the old wording told users
  that editing it changed a common layer. Withdrawn in the panel and the doc.
  Endzone layers are also region masks rather than artwork, which the copy now
  states. **Export endzone contact sheet…** renders all 118 packages into
  labelled sheets so a team's endzone can be found by eye; 31 packages are
  identified so far. A name search cannot work — the nicknames are not on the
  disc at all. Reported by davidhbui.
- Fine-tune Plays keeps its full static record but no longer word-wraps 11,360
  characters of executable addresses between the user and the controls; it is
  behind **Research pins**.
- Fixed the alpha.70 test regression where the title-update button crashed every
  window test whose launcher settings double predated it.
- 2K5 stays RC62. The shared updater identity is `beta-39`.

## beta-38 — 2026-08-12

**APF 2K8 alpha.70: tagged-slot compose, empty formations, title update 1.1.**

- Moving a tagged slot onto a play added in the same request now verifies.
- A formation can be emptied; tagged slots are shed because `min(4, 0)` is 0.
  Count `0x84a8ac30` / get-nth `0x84a8bd20` then return 0/null for that record.
- Launch installs the hash-pinned Xbox 360 title update 1.1 into the isolated
  Xenia content folder. The update never shipped for PS3.
- Automatic WR3→TE package substitution is not offered (APF `+0x11` map found;
  role legend unproved). 3rd-and-long play choice remains runtime-unproved.
  2K5 stays RC62. The shared updater identity is `beta-38`.

## beta-37 — 2026-08-12

**APF 2K8 alpha.69 completes the mask-preview follow-up.**

- Preview notes persist across cache hits instead of being inferred from
  already-opaqued pixels.
- Uniform, TXTR, and embedded scene-texture PNG exports are visible in normal
  image editors while proved writers still restore retail alpha storage.
- Genuinely empty decoded retail slots are labeled as empty rather than as
  preview failures.
- Fine-tune Plays now uses honest stored-membership wording; runtime CPU
  consumption remains unproved. The shared updater identity is `beta-37`.

## beta-36 — 2026-08-11

**APF 2K8 previews and Windows builds no longer require elevation.**
`0.1.0-alpha.68`.

- `jersey_color` and `shoulder_color` previews now show their RGB mask data
  when retail alpha is uniformly zero. The substitution is display-only;
  raw exports and the encode path preserve retail alpha exactly.
- DXN (`helmet_color`) failures from the low-level decoder now explain that
  the asset layer owns the separate DXN layout.
- Windows staging falls back from symlink to hardlink to a verified copy, so
  output on another drive does not require administrator mode. Exports use the
  platform no-replace publisher for exFAT-safe commits.
- Field Art explicitly surfaces all 235 stock endzone layers for browsing and
  export while keeping the two shared writer slots separate from unproved
  per-team authoring.

## beta-11 — 2026-07-28

**Exporting a Team Kit as a folder now works on Windows.** `v1.0-RC36`.

It failed for everyone there, and the error blamed the drive:

```
[WinError 5] Access is denied: 'G:\.ARZ-style-0-...-Team-Kit.team-kit-...'
  -> 'G:\ARZ-style-0-...-Team-Kit'
```

The export built the folder under a temporary name, then published it by
reserving the destination with `mkdir` and renaming the finished tree onto that
reservation. On Linux that works, because renaming a directory replaces an
existing empty one. **Windows cannot rename a directory onto an existing
directory at all**, so the publish always failed.

It now goes through the platform layer that already handled this correctly
everywhere else in the codebase -- one call site had hand-rolled its own. The
no-clobber guarantee is unchanged: an existing destination is refused, never
overwritten.

**Also fixed alongside it:** the ZIP export published with a hard link, which
needs NTFS on Windows. An external drive holding disc images is often exFAT,
where that fails outright. It uses a rename there now.

Nothing about discs, indexing or building changed in this release.

## beta-10 — 2026-07-27

**beta-9 let you load your disc. This one lets you save.** `v1.0-RC35`.

Building refused every image except the project's own, so you could load, browse
and edit and then be stopped at the last step. The cause was layout, not content:

- **Sector numbers were pinned.** extract-xiso relocates files when it rebuilds
  an image. All nineteen files sit at different sectors in a pressed disc, an
  extract-xiso rebuild and a repack -- while every file is byte-identical. No
  image but ours could match.
- **Absolute byte offsets were pinned**, so reads would have landed in the wrong
  place on any other image.
- The Crib scene texture was read at a fixed offset; it now finds its pack by
  name and derives the offset from the image in front of it.

Sizes and content hashes are still checked exactly. Those describe the game. The
sector a file happens to occupy describes only whoever built the image.

Verified by building real mods from the reporter's own two images -- a
7,825,162,240-byte pressed-disc read and a 6,300,958,720-byte repack -- across
scorebug, Crib photo and roster-text edits. Four builds, four outputs, each the
size of its own source.

## beta-9 — 2026-07-27

**The one that actually works with your disc, all the way through a build.**
`v1.0-RC34` and `0.1.0-alpha.39`.

Every release before this fixed one wall and revealed the next. This was
developed against a reporter's own two disc images rather than the project's
copy, which is what finally exposed the causes the project's own image could
never contain.

### Fixed — a genuine disc read is accepted
- **A raw disc read has two filesystems.** The video partition sits at byte 0
  with only a placeholder in it; the game is further in. The reader stopped at
  the first filesystem, found no `default.xbe`, and rejected the disc. It now
  enumerates partitions and picks the one holding the game.
- **A pressed disc marks its files `0x80` (NORMAL).** The reader demanded the
  ARCHIVE bit, which extract-xiso sets on everything it rebuilds but a real disc
  does not. That rejected every file on a genuine read, `default.xbe` included.
- **The game index embedded a Windows path.** `str()` on a path is backslashes
  there, and JSON escaping added three bytes, so the index could never match its
  own pinned hash.

### Fixed — building, not just loading
The build lane still demanded the user's container equal the project's rip, in
three places. An image could load, index, be browsed and edited, then be refused
at the final step. Container equality is gone across the build, audio and
stadium lanes; copy lengths follow the user's real file, and identity comes from
the located game partition, its file count and `default.xbe`.

### Fixed — Stadium Studio on Fedora and openSUSE
It pinned the bytes of a PNG it generates itself. zlib-ng, the system zlib on
those distributions, emits different but perfectly valid compressed output, so
Stadium Studio refused to open even with a flawless dump. It now verifies the
decoded pixels, which are identical on every platform.

### APF
The same container-hash gate existed on APF disc images and is gone; the
per-file ledger that already ran afterwards is the stronger check.

### Verified against the reporter's images
A 7,825,162,240-byte raw disc read and a 6,300,958,720-byte repack. Both
recognised, both fully indexed (16 packs, index byte-identical to its pin), both
accepted by the build lane's source validation.

## beta-8 — 2026-07-27

**No Windows user could ever finish loading a game. This fixes that.**
`v1.0-RC33` and `0.1.0-alpha.38`.

### Fixed
- **"The generated game index did not match NFL 2K5".** The index was written in
  text mode, and on Windows text mode rewrites every `\n` as `\r\n`. With
  2,289,506 newlines, Windows produced 58,035,920 bytes against a pinned
  55,746,414 — same disc, same packs, different file. This was unconditional:
  every Windows user, every disc image, every time, and the wording blamed their
  game when their game was fine. Linux and macOS never see it, because text mode
  is a no-op there.
- Fixed as a class: **38 text writes across 29 shipped files** now pin the line
  ending. A test holds the shipped surface at zero unguarded text writes, so no
  future generated file can differ between platforms.

## beta-7 — 2026-07-27

**beta-6 fixed half of this. If it still refused your game, or failed straight
after loading it, this is the one.** `v1.0-RC32` and `0.1.0-alpha.37`.

### Fixed
- **A raw disc read is accepted whatever tool made it.** beta-6 checked a *list*
  of four known game-partition offsets — the same mistake as checking one, with
  four guesses — and a real user's rip was not in it. The reader now **searches**
  for the disc filesystem instead of guessing, so layouts nobody here has seen
  still work.
- **`ModuleNotFoundError: No module named 'nfl_outer'` right after loading.**
  This one reached only people who *install* rather than unzip. The product runs
  `tools/*.py` as subprocesses and they import each other; an ordinary Python
  adds a script's own directory to `sys.path`, but the embeddable runtime inside
  the installer does not, because its `._pth` defines the path outright. The
  tarball, CI and a source checkout all launch Python the ordinary way, which is
  exactly why nothing we ran caught it — and the installer is what most people
  use. Every shipped tool now restores its own directory, and the `._pth` lists
  `app\tools` too. Affected both editors.

## beta-6 — 2026-07-27

**If the editor refused your copy of NFL 2K5, this is the release that fixes
it.** Both products move: `v1.0-RC31` and `0.1.0-alpha.36`.

### Fixed
- **2K5 accepts any legal dump of the disc.** The editor required a file whose
  size and SHA-256 matched the project's own rip, and read the disc filesystem
  at the one offset an extracted `.xiso` puts it at. Those are properties of a
  container, not of a game, so people with perfectly legal copies were told
  their file "is not the supported NFL 2K5 Xbox XISO". Two real reports drove
  this: a full raw disc read of 7,825,162,240 bytes, and a repack of the same
  game 224 sectors longer. The filesystem is now located rather than assumed —
  byte 0 or any XGD1/XGD2/XGD3 raw-read offset — and identity comes from
  `default.xbe` inside the image. Eleven checks moved from "equals our copy" to
  "is the right game". Loading is much faster too, since recognition hashes an
  11.9 MB executable instead of 6.3 GB.
- **A failed build cleans up after itself on Windows.** Writers unlinked the
  partial output while its descriptor was still open — fine on Linux, refused by
  Windows — and swallowed the error, so the next build hit "refusing to
  overwrite existing output" with nothing visibly wrong. Affected four writers
  across both editors.

### Added
- **ESPN NFL 2K5 PlayStation 2 memory-card save editing** (#3, by
  @patrickfcarey), as a command-line lane with an independent verifier. Filed
  `offline-writer-proved` with in-game reload explicitly not claimed. Adds
  `nfl2k5_ps2` as a third game; the registry goes to 66 capabilities.

### Unchanged on purpose
- **Nothing was relaxed about the bytes you edit.** Archive packs pulled from
  your image are still verified against their pinned SHA-256s, the derived game
  index against its own, and every writer still checks the exact extents it
  touches. Those cover the bytes that matter, which a whole-file hash never did.

## beta-5 — 2026-07-27

**Windows bug fix.** Editor code changed, so both products move: `v1.0-RC30` and
`0.1.0-alpha.35`. If you are on Windows and beta-4 could not export a texture,
this is the release that fixes it.

### Fixed
- **Every APF texture writer now runs on Windows.** Field art / endzones, team
  logos, the logo cache, the generic texture writer and uniform mips all failed
  immediately with `AttributeError: module 'os' has no attribute 'O_CLOEXEC'`.
  That flag does not exist in CPython on Windows, and four writers passed it to
  `os.open` as a bare attribute rather than `getattr(os, "O_CLOEXEC", 0)` — the
  form 284 other sites in the tree already used. A user reported it against the
  ordinary "export and replace field endzone" flow; thank you.
- **The 2K5 direct uniform-colour writer falls back correctly off Linux.**
  `copy_fd_exact` called `os.copy_file_range` inside `except OSError`, but on
  Windows and macOS the syscall's absence raises `AttributeError`, so the
  documented fallback never ran. The syscall is resolved before the loop now.

### Unchanged on purpose
- **No capability was added, removed or re-graded.** Both registries and every
  ladder position are exactly what beta-4 shipped, and no guarantee is weaker:
  PEP 446 makes every descriptor CPython creates non-inheritable on all
  platforms, so close-on-exec never depended on the flag that was missing.
- Nothing was at risk on the affected machines. The failure landed in the output
  reservation — after the read-only preflight, before any output existed — so no
  file was written at all.

### Added
- `tests/mod_editor/test_shipped_tools_posix_only.py`, a guard that needs **no
  retail data**. Every test over these writers is gated on extracted retail data
  no CI runner has, which is how six green-parity CI jobs never executed one
  `os.open` inside a writer. The new file scans both release allowlists for bare
  POSIX-only `os.open` flags, and deletes those names from `os` to drive every
  shipped writer's real reservation path. Targets come from the allowlists, so a
  writer added later is covered without editing the test.

## beta-4 — 2026-07-25

**Windows installers.** No editor code changed, so both products still identify
as `v1.0-RC29` and `0.1.0-alpha.34`, and the tarballs are byte-identical to
beta 3. This release adds a way to install without a command prompt.

### Added
- **`2K5-Mod-Studio-…-Setup.exe` and `APF-2K8-Mod-Studio-…-Setup.exe`** — wizard
  installers that need nothing preinstalled. No Python, no pip, no 7-Zip, no
  PATH changes, no command prompt. They install per-user under `%LOCALAPPDATA%`,
  so they never ask for administrator rights or touch Program Files, and they
  add Start Menu and desktop shortcuts plus a normal entry in Apps & features.
- **A warning page as the second step of the wizard**, before anything is
  written to disk, with Next disabled until it is acknowledged. It explains the
  SmartScreen prompt an unsigned program triggers, that the visible button is the
  wrong one, that the path is *More info → Run anyway*, and how to verify the
  download by SHA-256 rather than trusting the project. Someone who meets that
  prompt with no warning reasonably concludes the download is malware.
- `packaging/windows/build_windows_installer.py` builds them, and
  `packaging/windows/UNSIGNED-NOTICE.txt` is the text shown in that page.

### How they are built, and why not PyInstaller
The application verifies its own integrity at runtime: `_read_pinned_payload`
reads each pinned module from `workspace/<path>` and hashes the bytes, and the
workspace comes from `Path(__file__).resolve().parents[2]`. A frozen build has
neither real `.py` files nor a meaningful `__file__`, so freezing would silently
delete the guarantee that makes the tool safe to point at a game.

Instead each installer carries a **private CPython** (python.org's embeddable
build) beside the application, with `..\app` on `sys.path` via its `._pth`. The
application ships byte-identical to the tarball — same files, same pins — and
runs with no `PYTHONPATH` and no dependence on the working directory.

### Reproducible, and fail-closed about it
Every byte entering the installer from outside this repository is pinned to an
exact SHA-256 and verified before use: the interpreter and all four wheels
(PyQt5, PyQt5-Qt5, PyQt5-sip, Pillow). A hash mismatch, an unpinned wheel the
resolver pulled in, or a pinned wheel that fails to appear all stop the build
rather than shipping. Version pins alone would not be enough — a version can be
re-uploaded and a resolver can choose a transitive dependency nobody reviewed.

Both installers rebuild **byte-identical**, verified by building each twice and
comparing, so the published SHA-256 means something.

### Verified
Built and exercised end to end under wine, not merely compiled: silent install
lands the expected tree, the private interpreter imports `mod_editor`, PyQt5 and
Pillow, `pythonw.exe` with the shortcut's exact arguments runs without exiting,
and the uninstaller removes everything it created. The warning page was captured
rendering with Next correctly disabled. The refusal path was tested by feeding
the build a wrong hash and confirming it stops.

### Known limit
The installers are **not code-signed**, so Windows shows a SmartScreen prompt the
first time. A certificate costs a few hundred dollars a year, which this project
does not have. The wizard, the release notes and the download instructions all
say so up front rather than letting it come as a surprise.

---

## beta-3 — 2026-07-25

**Documentation, licensing and packaging. No editor code changed**, so both
products still identify as `v1.0-RC29` and `0.1.0-alpha.34`.

Beta 2 shipped correct software with incorrect paperwork, and its APF asset was
replaced twice on release day. Beta 3 exists so there is one unambiguous set of
archives to point people at.

### Fixed
- **The shipped `APF2K8-README.md` contradicted the archive it shipped in.** It
  told Windows users the ISO path would not work and reported the test suite as
  not yet passing on Windows or macOS. Both had stopped being true: the bundled
  `extract-xiso.exe` was in the same tarball, and all six CI jobs had been
  reporting identical results. Corrected, and the title no longer says
  "for Linux" — one archive serves all three platforms.
- **`README.md`'s opening line** still described "two retail-free Linux mod
  editors" a few paragraphs above the section stating that all three platforms
  pass the same suite.
- **Neither archive contained a licence.** The MIT licence requires its own text
  to accompany every copy of the software, so the archives were out of
  compliance with their own licence. `LICENSE` and `NOTICE.md` now ship inside
  both.

### Added
- **`NOTICE.md`** — the game-IP scope (previously an appendix inside `LICENSE`),
  the retail-free statement, third-party attribution for the bundled extractor,
  and the trademark notice.
- **`tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md` now ships in
  the APF archive.** The release notes told users to read it; it was not in what
  they downloaded.
- **The release pipeline is in the repository**: `packaging/stage_release.py`,
  `packaging/build_archive.py` and `packaging/repin.py`. These had lived only in
  scratch directories and were reconstructed from transcripts three times, most
  recently after a power cut. Staging from an allowlist and rebuilding at epoch
  `2026-07-25T00:00:00Z` reproduces the published bytes exactly.
- **`STATUS.md` gained a "Published releases" section** recording the identity
  of every asset actually published, including superseded uploads, so an early
  download can be identified rather than left ambiguous.
- Contributor scaffolding: `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, issue forms and a pull-request template.

### Changed
- `LICENSE` now contains the MIT text and nothing else, so licence scanners
  identify the project as MIT. **No terms changed** — the game-IP paragraph moved
  verbatim into `NOTICE.md` and still applies.
- The APF asset is named `apf2k8-mod-studio-0.1.0-alpha.34-20260725.tar.gz`,
  matching the 2K5 convention of a dated asset name. Beta 2 reused one filename
  across three different sets of bytes; the date makes that impossible to repeat.

### Verified
All six CI jobs identical at **107/126 files, 1304 tests** (Windows, macOS and
Linux × Python 3.11 and 3.12); both retail-free release gates green. Local suite
on a host with retail data: **126/126 files, 1364 tests**. Both archives rebuild
byte-identically, pass their gates when run against the *extracted* archive, and
cold-start with no `PYTHONPATH`.

---

## beta-2 — 2026-07-25

**Superseded by beta 3** — its APF archive was replaced twice and its shipped
documentation was wrong. Kept for the record.

### Added
- **Windows and macOS support.** Every OS difference is concentrated in one shim
  (`mod_editor/core/platform_compat.py`). Real implementations rather than
  `if windows: skip` — positional I/O, directory transactions, atomic
  no-clobber publication, private-cache privacy, ownership and durable flushes
  each have genuine Windows and macOS paths, and where a platform cannot provide
  a guarantee the tools say so instead of pretending.
- **APF team logos** on helmets and the score bug, and **APF field art /
  endzones** — both proven bit-exact by an independent verifier, taking the
  capability registry to 65.
- CI matrix across Windows, macOS and Linux on Python 3.11 and 3.12, plus a
  capability-registry job and both retail-free release gates.
- `extract-xiso` bundled for Linux **and** Windows, each pinned by exact size and
  SHA-256, cross-compiled reproducibly from the same vendored 2.7.1 source.

### Fixed
- A `QScrollArea` regression that painted light grey over the dark theme on
  every APF page.
- Windows file locking, CRLF translation, binary-mode reads and 8.3 short names
  corrupting byte-exact artifacts.
- Twelve security weakenings in the Windows/macOS fallback branches, found by an
  independent audit and closed over ten remediation passes. The recurring fault
  was fallbacks *claiming* guarantees they did not enforce.

---

## beta-1 — 2026-07-22

First public beta of both editors. Linux-first. See
[`BETA_RELEASE_NOTES.md`](BETA_RELEASE_NOTES.md).

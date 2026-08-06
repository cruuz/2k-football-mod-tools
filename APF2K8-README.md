# APF 2K8 Mod Studio

This folder is a retail-free application. It contains no *All-Pro Football
2K8* ISO, extracted game files, textures, audio, screenshots, or rollback
bytes. You select your own legally dumped USA copy after the app opens.

## Install

APF 2K8 Mod Studio needs **Python 3, PyQt5, and Pillow**.

- **Linux** (Mint/Ubuntu) — install the operating-system packages:
  ```bash
  sudo apt install python3 python3-pyqt5 python3-pil
  ```
- **Windows / macOS** (the `apt` line above is Linux-only) — install Python 3
  from https://www.python.org/downloads/, then:
  ```bash
  pip install PyQt5 Pillow
  ```

That command installs libraries only; the Mod Studio installer itself never
requests administrator access.

### Linux (per-user install)

Open a terminal in this extracted folder and run:

```bash
./install.sh
```

Do **not** use `sudo`. The installer puts the program and shortcut only in your
user account. After it finishes, open **APF 2K8 Mod Studio** from the
application menu. You can also run `~/.local/bin/apf2k8-mod-studio`.

### Windows

Extract the archive and double-click **`APF-2K8-Mod-Studio.bat`**. It runs from
its own folder (paths containing spaces are fine), checks that Python 3, PyQt5,
and Pillow are importable, and shows a message and pauses if anything is
missing.

### macOS

Extract the archive and double-click **`APF-2K8-Mod-Studio.command`** (the first
time, right-click it and choose **Open** to clear Gatekeeper). It resolves its
own folder and runs the same dependency check.

**Platform support.** CI is configured to run the suite on Linux, Windows, and
macOS with Python 3.11 and 3.12. Linux is the locally exercised release path;
the Windows and macOS jobs are automated compatibility targets. Retail-dependent
tests and release gates skip with an explicit reason when their private game
data or generated build inputs are unavailable.

**Linux remains the most exercised platform**: the desktop app has been
smoke-tested end to end there, and the GUI has not been manually driven on
Windows or macOS, so treat those as well-tested code with a less-tested window
on top.

The bundled `extract-xiso` extractor ships as **both** a Linux binary and a
Windows `.exe`, built from the same vendored 2.7.1 source, so handing the app an
**ISO** works on either. **macOS has no bundled build** — point it at an
**already-extracted game folder** there, or build extract-xiso yourself
(`brew install extract-xiso`, or `cmake` on the vendored source) and pass it as
`SourceManager(extract_xiso=...)`. `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`
records the exact build commands, toolchain and hashes for both bundled
binaries, so you can reproduce the bytes rather than trust them.

Tight H7A rebuilds have one additional platform distinction: Linux x86-64
ships the reviewed minimum-cost helper. Windows and macOS retain the verified
greedy encoder and fail closed if a particular edited stream cannot meet its
fixed retail allocation; they never publish an oversized or overlapping
stream.

Audio export works without a desktop player. For the Audio tab's **Play/Stop**
button, install any one of `ffplay` (from `ffmpeg`), `paplay`, or `aplay`. On
Linux Mint/Ubuntu, the most broadly useful choice is:

```bash
sudo apt install ffmpeg
```

The Audio tab inventories all 2,261 standalone sounds, all 45,514 addressable
substreams, both 15-track soundtrack encodings, and all 19 named physical XMA1
banks. Original XMA1/WAV export and exact raw-bank export are available. The
current release candidate, **`0.1.0-alpha.56`**, gives the 2,261 standalone
rows and all 45,514 individually addressed AUSB rows an advanced exact-slot
replacement route, selected-sound PCM16 authoring through a separately
installed encoder, and v1 XMA1 plus v2 exact-PCM16 folder/ZIP batch hand-off.
Alpha.38 and earlier remain preserved as previous sealed retail-free packages. AUSB index rows and
whole physical-bank rows remain descriptive/private raw exports rather than
single-sound editors.

Alpha.34 adds **Your cue label & notes** to all **47,775 playable cues**: the
2,261 standalone AUDO sounds and 45,514 individual AUSB substreams. Enter a
custom title of up to 120 characters and/or a multiline note of up to 2,000
characters, then choose **Save label**. The title and note become searchable
immediately, and **Labeled only** isolates discoveries across banks without
changing the stable game cue ID. Raw AUSB index rows and physical-bank rows
cannot own a per-cue annotation because neither represents one playable sound.

Cue annotations are retail-free project metadata under the contract
`project_metadata_only_stable_logical_cue_id`. They save in a bounded,
checksum-bound `audio-annotations.json` member inside `.apf2k8mod`; a project
containing only annotations is valid and shareable. Labels participate in
Save, recovery, Undo, Clear, Revert All, and project load, but do not receive a
Modified badge, do not count as build edits, and are never written into APF or
a modded game build. Audio collection export metadata carries the custom title,
note, and preserved game/catalog name; playlists prefer the custom title while
the stable cue ID and payload path remain unchanged. No retail audio, decoded
PCM, source path, preimage, or replacement packet is stored by this workflow.

Alpha.33 adds a selected-sound drop target labeled **Drop .xma or audio file here**.
Drop one local regular file: `.xma` takes the same advanced exact-
slot route as **Replace with XMA1…**, while ordinary audio (WAV, MP3, FLAC,
OGG, M4A and similar) takes the same cancellable user-encoder route as
**Replace from PCM WAV…**. The target is enabled only for
an individually editable AUDO/AUSB sound. Every Audio mutation/template control
disables at PCM, direct-XMA1, or pack submission and stays disabled until the
owned worker is unregistered. Folders, links, remote URLs, multiple files,
and other formats are refused before mutation; the normal validators remain the
authority after admission.

Audio that is not already the slot's exact shape is converted to it first:
resampled, mixed to the slot's channel count, and fitted to its exact frame
count. A file no longer has to be hand-built in an audio editor. A file that
already matches exactly is passed through untouched, byte for byte. Conversion
needs FFmpeg on `PATH`; without it, exact files still work and anything else is
refused with an explanation rather than converted badly. This adds a route and
removes none: whatever conversion produces still faces the full exact-slot
allocation, packet, complete-decode, source-reuse, target, and alias checks.
Because the Xbox 360 stores this game's audio as XMA1, and no redistributable
XMA1 encoder exists, the final encode still uses the encoder you configure.
Dropping an already-encoded `.xma` remains the only route that re-encodes
nothing at all.

Alpha.32 makes batch replacement a fully validated review followed by explicit
confirmation. **Review replacement folder…** and **Review replacement ZIP…**
show supplied, would-change, already-current, missing, current-modified, and
resulting-modified counts while nothing is staged. **Cancel** and
unchanged-only reviews are no-ops. **Apply** reopens and revalidates the pack,
then verifies a private token bound to its exact authored member hashes,
validated results, source, session, and current project-audio revision. A pack
or project change after review is refused instead of silently applying a
different result.

Alpha.31 adds **Add all matching (N)** for collecting the complete applied
Audio search/filter result into the ordered shortlist, with stable
deduplication and an all-or-nothing 256-sound cap. It caches that exact applied
result so ordinary row selection does not repeatedly scan all 47,814 records.
Closing the app or changing games while preview/waveform decoding is active now
cancels the owned request, drains its worker, and only then releases or replaces
the private loaded-game session; rapid source choices coalesce to the latest
one.

Alpha.28 carries forward the shared desktop-shell polish for keyboard and larger-text
use. Press **Ctrl+1** from any workspace to focus the category sidebar, or
**Ctrl+F** to focus the visible enabled search in the current workspace. Strong
focus outlines make the sidebar and asset lists easier to track, the header and
footer can grow with the system font instead of clipping, and navigation,
operation status/progress, Build, and Launch expose descriptive accessibility
text. These contracts are covered by headless Qt checks; isolated visual QA is
still pending.

Alpha.22 adds an experimental exact-slot editor for the 2,261
standalone `AUDO` sounds. It accepts only pre-encoded, one-stream RIFF XMA1
whose channels, sample rate, encoded byte length, packet framing, and decoded
sample count exactly fit the selected sound. Replace, Revert, Undo, project
save/load, staged preview, and typed Build are wired. Shareable projects store
only the user's canonical replacement packets and bounded target metadata; a
payload matching any source `AUDO` hash is refused. The stronger cross-family
gate described below also rejects any replacement containing a complete source
packet. These checks prevent byte-identical source packets from entering a
project; they cannot determine the copyright or license of independently
re-encoded PCM selected by the user.

The standalone editor is offline-writer-proved. Its completed Xenia A/B booted cleanly,
logged no XMA error, and survived five intended Schedule-enter triggers, but
the captured waveform and spectral comparisons did not beat their controls.
Audible consumption of that tested cue therefore remains inconclusive rather
than being advertised as runtime-proved. Mod Studio ships no XMA1 encoder.
Alpha 28 can hand one selected, exact-shape PCM16 WAV to a user-configured
native encoder or Windows `.exe` through Wine; its result must still pass the
same complete exact-slot gate. It can also process a v2 pack containing up to
256 supplied exact-shape WAVs as one atomic import. FLAC/MP3 and mixed-format
packs remain unsupported. See the
[exact-slot authoring contract](docs/product/APF_AUDO_EXACT_SLOT_XMA1_EDITOR.md).

Alpha.23 extends the same narrow pre-encoded workflow to all 45,514 semantic
`AUSB` commentary, speech, PA, music, presentation, and soundtrack substreams,
backed by 45,513 canonical physical ranges. Replace, Revert, Undo, project
save/load, staged preview, and pack-aware Build are wired without repacking a
descriptor or whole external bank. Both audio domains use a complete
cross-domain authorization inventory: import, project load, preview, and Build
reject any replacement containing even one complete `0x800`-byte packet found
anywhere in the source AUDO or AUSB inventories. Projects and public receipts
store neither those source fingerprints nor retail packets.

Alpha.28 carries the batch authoring layer forward and adds an **Exact PCM16
WAV** v2 contract beside the default **Pre-encoded XMA1** v1 contract. Choose
**Editable folder** for normal local work or **ZIP hand-off** for one
deterministic archive. **Create replacement template…** writes a new
metadata-only folder or ZIP for every playable row matching the current
filters, or for the exact shortlist while it is in Review. The manifest covers
up to all 47,775 editable sounds and stores generated coordinates, exact slot
shape, alias ownership, the loaded-source binding, and a replacement-only
snapshot of the selected target's current project state. It exports no
original sound, decoded source-owned name, private replacement path, or
rollback byte. V1 lists `xma1/*.xma` paths for independently encoded,
one-stream RIFF XMA1. V2 lists `pcm16/*.wav` paths whose authored signed
little-endian PCM16 WAV must exactly preserve channels, sample rate, and frame
count. A template may list all targets, but one v2 import accepts at most 256
supplied WAVs; folder import refuses entry 257 before opening or hashing any
WAV byte. Use **Review replacement folder…** or **Review replacement
ZIP…**; review auto-detects v1/v2, and v1 never needs an encoder. Missing files are
skipped; unknown, repeated, unsafe, wrong-source, wrong-shape, invalid,
conflicting-alias input is rejected before the active project changes;
unchanged-only input produces a valid preview with Apply disabled. If a
supplied target or any physical alias owner changed after template creation,
review asks for a fresh template; unrelated project edits remain usable. A
confirmed folder or ZIP becomes one Undo action.
Failed validation never removes packet data still referenced by the active
project or Undo history. Validation reports progress after each complete file.
**Cancel pack check** interrupts an owned encoder or stops at a safe file
boundary, changes no project edit, and adds no Undo action. The confirmation
opens only after the preview worker drains; nothing is staged until explicit
Apply. Existing
Alpha.25/26/27 v1 templates remain compatible and deterministic. V2 does not
accept FLAC, MP3, floating-point WAV, XMA1/XMA2, mixed payload types, or more
than 256 supplied WAVs per transaction.

For one selected sound, Alpha 27 added **Export PCM authoring template…**,
**Configure XMA1 encoder…**, **Replace from PCM WAV…**, and cooperative
**Cancel PCM encoding**. The template is exact-length PCM16 silence and
contains no source audio. Encoder/Wine paths, literal no-shell argv, and the
bounded timeout stay in local application settings and never enter a mod
project. External output is untrusted until the existing XMA1 RIFF, allocation,
packet, complete-decode, duration, alias, and cross-family exact-source-packet
checks all pass. The build environment had no real XMA1 encoder, so synthetic
tests prove the bridge and cleanup only—not third-party-tool compatibility or
in-game audibility. Read the
[PCM encoder guide](docs/mod_editor/apf2k8_external_xma1_encoder.md).

The private Track 12 runtime candidate booted, selected the requested track,
and remained stable, but the completed objective capture was honestly
negative/inconclusive for modified-stream causality. The final sustained
segment matched neither the mutated candidate nor decoded stock Track 12, so
the experiment proves boot/selection/stability—not authored-audio consumption
or stock fallback. Read the
[AUSB exact-slot contract](docs/product/APF_AUSB_EXACT_SLOT_FEASIBILITY.md).

Alpha.14 adds **Export complete audio catalog…**, a single
47,814-row batch. It can write original XMA1 or decoder-verified WAV payloads
to a new ZIP and publishes the archive atomically. Its manifest accounts for
every semantic row: the 2,261 standalone sounds and 45,514 addressed AUSB
substreams use the verified single-sound route, while the 20 AUSB index rows
and 19 physical-bank rows are recorded as unsupported rather than treated as
audio cues. Per-row decode failures are also reported without turning an
incomplete result into an unexplained success. Batch export never edits a
project and does not unlock replacement.

Alpha.19 adds **Export all original banks (19)…** for the complementary
physical layer. It copies all source-owned external `.bin` containers,
including both soundtrack banks, into one atomic private ZIP with per-bank
hashes/sizes/name IDs and every AUSB descriptor owner in its manifest. The
Audio page's **Cancel audio export** control now cooperatively stops either
bulk route between complete sounds or banks and leaves an accounted partial
manifest. Raw-bank export still does not provide XMA1 replacement.

Alpha.20 makes the complete 47,814-row cue export practical after it leaves
the app. Alongside `manifest.json`, every archive now includes a searchable
`catalog.csv` that accounts for every requested row and, when any cues
succeed, an ordered `playlist.m3u8`. The v2 manifest preserves role,
source/bank, format, rate, channels, duration, soundtrack-pair metadata, and
exact payload sizes/SHA-256 hashes. Failures, unsupported bank/index rows, and
cancelled items remain visible in the catalog but never enter the playlist.
This organization does not unlock replacement or make raw multi-cue banks
playable.

Playable rows now also have an explicit **Load waveform** action. It creates or
reuses only the selected sound's verified, session-private WAV, samples PCM16
within a fixed memory bound, and can be cancelled by changing selection or
closing the source. Selection alone never starts a decoder or player. AUSB
index rows and physical multi-cue banks never advertise a waveform.

In alpha.13, selecting a physical multi-cue bank hides controls that apply only
to one sound, and the wider detail pane keeps
the complete bank identity readable. Disabled actions use an explicit locked
appearance, so a gray **Replace (locked)** control cannot be mistaken for an
available editor.

Stadium Studio inventories all 93 exact `stadium` SCNE records and builds a
private interactive 3D preview from the selected game. Orbit, pan, zoom, click
surface identity, glTF ZIP export, and same-package PNG/raw exports are
available. For the pinned outer-14/inner-8 stadium, the exact ownership join
maps **89 scene nodes through 84 serialized materials to 78 embedded TXTRs**.
Clicking one of 77 catalog-authorized surfaces lists only the textures owned by
its resolved material. All 78 embedded textures can be previewed, exported,
auto-fitted from an ordinary image, replaced, reverted, and built into a new
copied `1A`; every mip is regenerated and the writer fails closed if the rebuilt
H7A cannot fit its fixed retail allocation.

The same 77 surfaces also support **Export selected mesh** and **Import edited
mesh**. This is an exact-count POSITION-only glTF hand-off: expanded triangles
must remain identical, and import publishes a new independently verified copied
`1A` while preserving the game's UVs, normals, material records, attachments,
collision, and every non-position stream byte. The ownership join and writers
are deliberately limited to this proved scene. Other stadium scenes,
material/shader authoring, new texture identities, transforms, extra vertex
attributes, skins, changed topology, and runtime visibility remain unproved or
locked. The source game is never modified.

The current Alpha.54 source carries forward Alpha.21's exact team **Display
name**, player **First name** / **Last name**, and true native 0–99 base-rating
editing through the bounded ROST route. **Rosters & Players** exposes all 3,273 mapped UTF-16BE identity
allocations and all 2,254 on-disc player records, while authoring admits exactly
3,191 player-name allocations serving 4,482 writable first/last references plus
40 team display-name allocations. That is 3,231 product-editable name
allocations; the empty zero-capacity allocation, both abbreviation fields,
mixed team/player scopes, and unknown scopes remain locked.

Shared names are explicit. Alpha.21 lists every owner before replacement: 429
editable player-name allocations are shared, the largest has 23 owners, and 61
serve both first- and last-name fields. One **Replace Player Name** action
changes every disclosed owner together. Those local owner lists and all retail
source names stay out of `.apf2k8mod`; a shareable project contains only the
user's authored replacement and small target metadata.

Packaged Alpha.21 passes `648/648` product tests in `90.763s`. Its
real-source public workflow also passes end to end: load, replace Dan's last
name with `CODEX`, Undo, replace, Revert, replace, save/reopen a 989-byte
replacement-JSON-only project, Build a separate 3.7 GB game, and reparse the
output. The project SHA-256 is
`45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`;
the output `0A` SHA-256 is
`0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
exactly matching the runtime-proved candidate. Only outer 1126 changed and the
source remained unchanged.

Fresh isolated-display QA passed after the layout fix: **Identity & Names**
defaults visible beside **Base Ratings (28)**, and **Replace Player Name**,
**Revert Player Name**, and **View 23 affected fields…** remain visible with the
exact `4/4` limit and no clipping or scroll trap. A separate retail-free
product-code dialog check displayed all 23 owner rows at once in high contrast.

Alpha.54 is the current headless-tested source candidate. Earlier published
archives remain authenticated by their adjacent `.sha256` sidecars; copies
inside an archive deliberately do not contain their own archive hash. Alpha.24
remains preserved at `710,512` bytes
with SHA-256
`cfcf0990a93df6d2e1f519cac0dd477117be34ed8ca55a44cbb9308467a596c6`.
The current candidate carries Alpha.28's v2 PCM16 folder/ZIP batch authoring
and the later ordinary-audio selected-sound conform route forward through the
separately installed encoder.
Alpha.26 added ZIP hand-off to
Alpha.25's all-editable-audio batch folder, exact target baselines, atomic
cancellation, and one-action Undo. The same Position (17), free-space refusal,
audio, and 53-row planner boundaries remain. Alpha.25's final focused audio/
build/project closure passed 128/128; isolated visual QA and a changed-position
Xenia spot check remain pending. Alpha.22
remains available as an older checkpoint at SHA-256
`f2adf77b9abdeddd1b2c2bf93fd2523a93eb721a192543c7660ba3e49b4578fb`.

An independent audit rejected and deleted the first regenerable Alpha.21
candidate because its bundled docs still described Alpha.20 as current and
Alpha.21 as pre-seal. Only the corrected current-Alpha.21 rebuild was sealed.
The stage and clean extraction each contain 90 exact allowlisted files and no
retail/private material; their full post-seal inventory and gate receipt is in
[STATUS](docs/mod_editor/APF2K8_STATUS.md).

Builds now use a token-preserving H7A route instead of relocating every decoded
token. A bounded `Americans` → `CODEXTEAM` build booted through first-run team
construction and rendered the authored name in Logo Selection, Team Summary,
and Team Select. A separate bounded `Marino` → `CODEX` build visibly rendered
**Dan CODEX #13 QB** in player selection and **QB #13 DAN CODEX — GOLD STAR**
on the Star Card without the old startup crash. These results support only
exact player first/last names and team display names; they do not grant
permission to neighboring packed fields. Read the positive
[runtime report](docs/product/APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md),
the superseded negative
[diagnostic](docs/product/APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md), and the
separate [32-team/53-player feasibility note](docs/product/APF_32_TEAM_53_ROSTER_FEASIBILITY.md).
Jersey numbers remain read-only in the on-disc `0A` project lane because no
consumer-backed on-disc field has yet been identified; the app does not guess
one. The separate **Save Players** raw-save lane authors the exact packed APFe
jersey-number field, abilities, tier, depth, and proved appearance/equipment
fields into a new verified `Roster.ROS` handoff.

Alpha.26 carries forward Alpha.23's 32-team × 53-row roster surface as an
honest planner, not a
53-active-player game writer. Stock APF currently consumes the first 42
membership rows per populated team; rows 43–53 are eleven project-only reserve
choices, and Build does not apply them. True runtime slots 43–53 still require
a version-pinned emulator-target XEX accessor/consumer patch plus owned
side-table storage. Teams 25–32 use populated online-placeholder records whose
offline selector ownership remains unproved. The completed
[true-53 runtime consumer inventory](docs/product/APF_TRUE_53_RUNTIME_CONSUMER_INVENTORY.md)
maps the current lower bound: 93 central-helper calls, at least 25 direct roster
consumers, explicit append limits, and a separate fixed 17-by-42 layout
workspace. It rules out a one-byte/count-only patch but keeps an emulator-owned
eleven-slot side table plus coordinated consumer hooks as the viable route.

Player selection opens a searchable **Base Ratings** editor containing the
game's 31 independent stored values: 27 semantic attributes plus four distinct
untranslated fields labeled by their stored offsets—**Unknown Rating (0xD4)**,
**Unknown Rating (0xBD)**, **Unknown Rating (0xC5)**, and **Unknown Rating
(0xD2)**. Every attribute is authored as a true native
integer from 0 through 99—there is no Madden-style scale conversion, hidden
compression, or shared overall value. Apply and Revert operate on one player
and one semantic attribute at a time, modified badges make the project delta
obvious, and team-name plus rating changes compose into one token-preserving
ROST build. If a source happens to contain the engine's native value 100, the
app shows 100 exactly and permits Revert, but deliberately does not create new
100 values. Overall is position-derived; abilities and Gold/Silver/Bronze tier
are separate systems and are not silently rewritten.

Alpha.24 introduced a separate **Position (17)** tab
for all 2,254 players. Its fixed semantic dropdown covers exact native codes
`0..16` (QB through DE), with per-player Apply/Revert and modified state. The
writer changes executable-consumed byte `+0x34` and its required opaque source
mirror at `+0x35` together, composes with name and rating edits, and stores only
the user-selected code plus retail-free target metadata in a project. It does
not imply team membership, depth-chart, Overall, tier, ability, or rating
changes. Offline writeback and packaged-source closure pass; the first changed-
position Xenia spot check remains pending. This workflow is part of the
headless-tested Alpha.26 source; it is not retroactively claimed as part of
the sealed Alpha.23 archive above.

The runtime spot check changed Dan Marino's stored Speed byte from 40 to 99,
booted in Xenia, and loaded/rendered that player record without the former
startup crash. APF has no numeric ratings screen, so this proves transport and
record consumption rather than a measured on-field Speed effect. See the
[ratings contract](docs/product/APF_TRUE_099_PLAYER_RATINGS.md) and
[runtime result](docs/product/APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md).

**Export ratings sheet…** and **Import ratings sheet…** provide a private bulk
workflow for all 2,254 players × 31 rating columns. Import validates the entire
source-bound CSV first, previews replacements/reverts/conflicts/errors, blocks
wrong-source metadata, and applies a confirmed plan as one Undo action. It
contains names and values derived from your game copy, uses owner-only
permissions, and must not be shared; `.apf2k8mod` remains the retail-free
sharing format containing only authored semantic edits and metadata.

The paired stock-roster audit is deliberately separate from editing. It compares
all **1,344** RPCS3 and Xenia APFe rows positionally, preserves the duplicated
`RunCoverage` header and eight trailing unlabeled fields as schema warnings, and
normalizes only the exact bounded `TeamJerseyBytes` RGBA-to-ARGB platform
serialization. The result is **1,312 equivalent rows, one stock identity
variant (RPCS3 Mike Haynes versus Xenia Mark Smith), 31 randomized Atoms filler
rows, and zero unexplained rows**. Haynes/Smith differs only in First, Last,
College, DOB, Number, Photo, PBP, and Age; equipment, ratings, and skills match
positionally. PBP is the play-by-play announcer ID, not a playbook field.

**Playbooks & Plays → Save Assignments** edits the separate roster-save pointer
table, not `playbook_master.iff`. A raw save lists all **40 team slots** and all
**69 named books**—36 offense and 33 defense—and stages both assignments before
writing a new save plus manifest. The inspected source SHA-256 is rechecked,
the source is never opened for writing, output paths cannot alias or overwrite,
and an independent pass verifies the exact changed bytes while confirming the
book table and every unrelated byte stayed fixed. Signed Xbox CON containers
are inspect-only: writing one without extraction, reinjection, STFS rehashing,
and resigning would produce an invalid container, so the editor refuses it.
Synthetic fixtures remain green. A private raw-save witness also parsed all 40
teams and 69 books, changed team slot 32 offense 25→13 and defense 56→32,
accounted for exactly two assignment fields / three changed bytes, independently
reopened to IDs 13/32 with the book table unchanged, then reverse-patched to the
byte-exact original. This proves bounded raw-save transport only. Gameplay
consumption and signed-STFS reinjection/rehash/resign remain unproved.

The neighboring **Assignment Routes** tab edits the on-disc MASTER PLAY through
a narrower exact contract: copy one stock player's four-byte assignment
descriptor and re-encode the target-relative pointer to the donor's existing
game-authored chain, or atomically swap two assignments. Shareable projects
store only play/slot selectors. Build reparses the complete fixed body,
preserves route nodes, names, formations, the MSB-first formation/play
membership table, and every distinct chain start, then rebuilds fixed outer 180
with token-preserving H7A. A one-way copy that would orphan a stock chain is
refused. Waypoint/opcode drawing, new play/formation creation, DRCT authoring,
and gameplay/runtime behavior remain unavailable or unproved.

**Uniforms & Equipment → Equipment Colors** gives all 40 teams independent
HOME/AWAY facemask-bar and Team-turtleneck palette selectors. The dropdowns
show exact palette names, hex values, and swatches. Staging changes only the
proved selector bytes, preserves both palettes and every neighboring byte, and
uses the normal project/Undo/Revert/Build path. Visors remain the separate
per-player None/Clear/Dark choice; the editor does not invent a per-uniform
visor tint that APF does not carry.

**Uniforms & Equipment → Custom Team Appearance → Raw Roster Save** edits the
appearance graph carried by an accepted custom team's raw `Roster.ROS`.
User-facing team IDs 24–31 map to ROST slots 32–39. HOME/AWAY palettes and exact
helmet/crest selectors are bounded to a 112-byte union per selected team; the
source is SHA-bound and read-only, output and receipt are new/no-overwrite, and
an independent pass reopens both files and verifies pointer ownership and the
changed-byte set. For `CON `, `LIVE`, and `PIRS`, the editor verifies the STFS
metadata/hash tree, extracts the one `Roster.ROS`, and can create either an
exact raw extraction or a patched raw handoff plus independently verified
manifest. It does not verify the RSA signature or write a signed container;
external reinjection, rehashing, and resigning are required. This raw-save path
does not establish emulator consumption, gameplay visibility, or Xbox 360
hardware behavior.

**Uniforms & Equipment → Model Export** makes the two requested stock models
easy to find: helmet `outer 1310 / inner 128 / helmet_00` exports 33 meshes, and
player `outer 1310 / inner 273 / player` exports one mesh. Each export writes a
new `.gltf`, `.bin`, and source-bound v2 `.apf-model.json` while reading `0A`
only. The paired import button accepts same-count **POSITION-only** edits,
requires every expanded triangle index to match the loaded source, and writes a
new verified `0A` plus receipt. It preserves POSITION W, normals, packed
tangent/UV data, blend indices/weights, existing skin/attachment bytes,
materials, animation, collision, and every sibling part exactly. New topology
such as a SpeedFlex/F7 mold, material/UV/normal editing, rig/skin editing, and
runtime model visibility remain unproved and unavailable.

**Logos & Team Art → Team Logo** now resolves all **118**
`uniform_logo_00.iff` through `uniform_logo_117.iff` packages from the loaded
archive. One staged 512×512 RGBA crest is mirrored into `logo_l0` and `logo_l1`
in the chosen package and matching logo-cache index; both packed mip tails are
regenerated. The package write, cache write, and separately implemented cache
verifier form one new-output-only evidence chain.

**Logos & Team Art → Wordmarks** separately owns all **206**
`uniform_textlogo_00.iff` through `uniform_textlogo_205.iff` packages selected
by uniform-selector slot 6. Choose Contain to preserve all imported art or
Cover to fill the 512×128 canvas; transparency is flattened to opaque black,
the preview shows the exact staged result, and Replace/Revert/Undo/project
save-load/Build use the normal Mod Studio workflow. The writer regenerates all
six tiled BC1 mip levels inside the original H7A/IFF allocation and an
independent verifier proves that no byte outside the selected package changed.
A square Team Logo crest is never silently squeezed into this rectangular
wordmark family. Runtime consumption remains unproved.

Select **Full-shell crest wrap — entire helmet shell** to build the fixed
`front_crown_to_rear_v1` shell-atlas route into the copied `0A` itself. The
project keeps the semantic 512×512 design. Full-shell import has two explicit modes:
**Normal logo — convert to APF regions (recommended)** contains ordinary art at
512×512, requires confirmation of the rendered shell plus two detail colours,
and shows the palette-mapped material preview; **APF region mask (advanced)**
accepts only exact four-bit red/green weights with blue fixed to zero, no hidden
transparent colour, and a one-unit red/green sum. Arbitrary source RGB is never passed through or claimed
to render literally. The
**Place on helmet…** canvas auto-fits the resulting mask across the labeled
**FRONT / CROWN → REAR** target before staging. Drag to set X/Y directly, or use
independent Width, Height, and Rotation controls; **Reset** and **Auto-fit
front → rear** remain one click away. Placement uses nearest-neighbour sampling
so exact region-mask values stay exact, and empty or off-canvas art cannot be
staged. Reopening **Place on helmet…** during the same editing
session reuses the normalized original import plus the last transform, so
repeated adjustments do not resample an already flattened result. At build
time, the headless writer maps the fixed weighted 4-bit semantic canvas to physical shell Y/Z,
bakes it bilaterally into the exact noncollapsed stock high/low UV atlas, routes
the shell draw to the crest material, and neutralizes the old overlay with
in-range zero-triangle indices. Shell vertices, UVs, indices, and accessory
draws remain exact. The selected package gets that shell atlas while its menu
cache keeps the undistorted semantic design. Before publication, all 117 other
package pairs are RGBA-preserving migrated to the same stock atlas so the
shared route cannot corrupt their retail side-logo placement and creates no Xenia patch.
It does not edit `default.xex`.

The v24 all-package headless gate compiled and reparsed **121 outer entries** in
memory before any output was created: all 118 source-resolved crest packages,
cache directory 171, cache payload 213, and shared helmet outer 1310. If a
custom-team appearance is staged, outer 1126 is composed as one additional
entry. The pristine source remained unchanged, all 117 non-selected retail
crests were migrated, and the selected Eagles shell-atlas hash matched its
pinned value. The exact atomically published v24 candidate then passed an
independent 118-package/236-layer reopen and a **10-view static asset-space
visual gate** across the stock high and low helmet LODs. Spark review of the
hash-pinned contact sheets found an authentic shell-spanning Eagles wing with
coherent side, front, rear, and crown coverage; the low LOD retained the
silhouette without smears, gaps, holes, seam breaks, or visible UV artifacts.
This proves the static Eagles visual match, not game consumption. No Xenia, Wine, emulator, controller, or FIFO
participated; runtime consumption,
gameplay visibility, scorebug/menu ownership, and Xbox 360 hardware parity
remain unproved.

**Field Art** gives 258 live records a seven-family semantic map across 125
archive packages: endzone textures, field scenes, radiance textures,
divot/weather textures, practice overlays, practice scenes, and penalty
animation curves. Six exact base textures—`endzone_l0`, `endzone_l1`,
`pc_field_goal`, `Field_Pass_text`, `Stride_number_field`, and `divots`—have
Preview/Export, Replace/Revert, and copied-`0A` build routes through the bounded
field-art writer and independent whole-volume verifier. Only the selected base
mip is regenerated; its packed mip tail, siblings, and every unrelated archive
entry remain exact. The other 252 semantic records stay browse/export-only and
are locked for Replace/Revert/Build because their codec or resource ownership
is not proved; no runtime visibility is claimed.

The application enforces capability-to-action parity. Its registry contains 37
APF capabilities (70 across all three registered game/platform targets),
including dedicated editable `draft_logo` and 206-slot wordmark capabilities. A capability is shown
as Editable or Export-only only when the matching desktop handler actually
implements those actions. Semantic findings without a product handler are
labeled **Proof boundary** or **Research boundary** rather than lending their
status to an unrelated generic asset row. No current APF capability is labeled
Coming Soon. The current source classification is
19 Editable, 8 Preview, 3 Export-only, 4 Proof boundary, and 3 Research
boundary. **Menus & Text** remains one of
the real Editable surfaces: its bounded in-place editor owns 2,410 of 2,413
decoded TXT/STRG allocations. The hidden `jersey_06_runtime` capability remains
a proof alias, not a duplicate user-facing editor. **Rosters & Players** earns
Editable status through real player-name, team-display-name, and per-attribute
rating and position handlers in the Alpha.54 source. Abbreviations,
zero-capacity or mixed-owner names, on-disc jersey numbers, and on-disc roster
structure remain locked. The separate raw **Save Players** workspace edits its
proved packed player fields and count-preserving memberships without claiming
on-disc ownership or signed-container reinjection.

Every published archive is built from the exact retail-free allowlist,
then checked through the full regression, source-free/private-source runtime
gates, independent extraction, deterministic rebuild, and isolated-display
visual QA. The adjacent `.sha256` sidecar is authoritative for the archive you
received. See [STATUS](docs/mod_editor/APF2K8_STATUS.md) for versioned receipts.

## Run without installing

Keep this entire folder together and run the launcher for your platform:

- **Linux** — `./APF-2K8-Mod-Studio.sh`
- **Windows** — double-click `APF-2K8-Mod-Studio.bat`
- **macOS** — double-click `APF-2K8-Mod-Studio.command`

Each portable launcher resolves everything relative to this folder. Moving or
renaming the folder is fine; moving only the launcher is not.

Advanced users can validate the packaged capability metadata with:

```bash
python3 mod_editor/capabilities/validate_registry.py --skip-file-checks
```

The flag skips repository-only provenance links that are intentionally absent
from the retail-free public package; it does not weaken registry schema,
classification, hash-pin, action, or distribution-rule validation. Maintainers
working from the complete development tree omit the flag so every private
evidence path is checked too.

## Uninstall

From this folder, or from the installed application folder, run:

```bash
./uninstall.sh
```

The uninstaller removes only files authenticated by its per-user ownership
record. It preserves projects, exports, game extractions, caches, settings,
and Xenia data. If a managed shortcut was changed after installation, that
file is preserved and its exact path is printed instead of being deleted.

For the editing workflow and current capability limits, read
`docs/mod_editor/apf2k8_mod_studio_getting_started.md`.

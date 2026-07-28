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

**Platform support.** **Linux, Windows and macOS all pass the same suite.** CI
runs it on all three, on Python 3.11 and 3.12, and every job reports an
identical result — the six jobs agree file for file and test for test. Part of
that suite is expected to fail on any CI runner regardless of OS, because this
repository deliberately ships no game data and no generated reports.

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

Audio export works without a desktop player. For the Audio tab's **Play/Stop**
button, install any one of `ffplay` (from `ffmpeg`), `paplay`, or `aplay`. On
Linux Mint/Ubuntu, the most broadly useful choice is:

```bash
sudo apt install ffmpeg
```

The Audio tab inventories all 2,261 standalone sounds, all 45,514 addressable
substreams, both 15-track soundtrack encodings, and all 19 named physical XMA1
banks. Original XMA1/WAV export and exact raw-bank export are available. The
current sealed release, **`0.1.0-alpha.48`**, gives the 2,261 standalone
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

Alpha.33 adds a selected-sound drop target labeled **Drop .xma or exact PCM16 .wav here**.
Drop one local regular file: `.xma` takes the same advanced exact-
slot route as **Replace with XMA1…**, while `.wav` takes the same cancellable
user-encoder route as **Replace from PCM WAV…**. The target is enabled only for
an individually editable AUDO/AUSB sound. Every Audio mutation/template control
disables at PCM, direct-XMA1, or pack submission and stays disabled until the
owned worker is unregistered. Folders, links, remote URLs, multiple files,
and other formats are refused before mutation; the normal validators remain the
authority after admission.

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
available. Material-to-texture ownership is not decoded yet, so Replace/Revert
remain disabled instead of guessing that a nearby texture owns a surface.
The completed static material experiment followed 116 mesh nodes through 328
draw records, all 113 serialized materials, and 13 shader families, then
checked 737 unique named texture identities. None is statically referenced by
the scene-system material data. The bounded Wine/Xenia runtime follow-up also
ended honestly: Wine intercepted Xenia's host instruction breakpoint before a
game frame or guest-register capture, and the private debugger configuration
was rolled back exactly. Ownership was not tested by that attempt. The useful
next route is a small instrumented logging build or the native-Windows guest
debugger, not another Wine-hosted breakpoint loop.

The current Alpha.28 source carries forward Alpha.21's exact team **Display
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

Alpha.28 is the current headless-tested sealed checkpoint; Alpha.27 is the
previous sealed retail-free package. Each published archive is authenticated by
its adjacent `.sha256` sidecar; copies inside an archive deliberately do not
contain their own archive hash. Alpha.24 remains preserved at `710,512` bytes
with SHA-256
`cfcf0990a93df6d2e1f519cac0dd477117be34ed8ca55a44cbb9308467a596c6`.
Alpha.28 carries Alpha.27's selected-sound PCM16 bridge forward and adds v2
PCM16 folder/ZIP batch authoring through the separately installed encoder.
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
Jersey numbers remain read-only because no consumer-backed field has yet been
identified; the app does not guess one.

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
game's 28 independent stored values: 27 executable-named attributes plus one
neutral **Unknown Rating 24**. Every attribute is authored as a true native
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
workflow for all 2,254 players × 28 rating columns. Import validates the entire
source-bound CSV first, previews replacements/reverts/conflicts/errors, blocks
wrong-source metadata, and applies a confirmed plan as one Undo action. It
contains names and values derived from your game copy, uses owner-only
permissions, and must not be shared; `.apf2k8mod` remains the retail-free
sharing format containing only authored semantic edits and metadata.

**Field Art** gives 258 live records a seven-family semantic map across 125
archive packages: endzone textures, field scenes, radiance textures,
divot/weather textures, practice overlays, practice scenes, and penalty
animation curves. Search, family filtering, package identity, normal
preview/export, and raw export are available. Archive co-location does not
prove team, stadium, shader, material, selector, or runtime ownership, so
Replace/Revert remain explicitly locked.

The application enforces capability-to-action parity. Its registry contains 31
APF capabilities (62 across both supported games),
including a dedicated editable `draft_logo` capability. A capability is shown
as Editable or Export-only only when the matching desktop handler actually
implements those actions. Semantic research entries without a product handler
remain visible as **Coming Soon** rather than lending their status to an
unrelated generic asset row. The Alpha.28 classification is
10 Editable, 6 Preview, 1 Export-only, and 14 Coming Soon. **Menus & Text** remains one of
the real Editable surfaces: its bounded in-place editor owns 2,410 of 2,413
decoded TXT/STRG allocations. The hidden `jersey_06_runtime` capability remains
a proof alias, not a duplicate user-facing editor. **Rosters & Players** earns
Editable status through real player-name, team-display-name, and per-attribute
rating and position handlers in the Alpha.28 source. Abbreviations, zero-capacity or
mixed-owner names, jersey numbers, and roster structure remain locked.

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

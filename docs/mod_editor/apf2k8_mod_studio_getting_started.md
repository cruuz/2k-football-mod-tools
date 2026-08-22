# APF 2K8 Mod Studio — Getting Started

APF 2K8 Mod Studio works from your own legally dumped USA copy of *All-Pro
Football 2K8* for Xbox 360. The app ships no game images, textures, audio,
screenshots, extracted archives, or other retail game data.

The source code and UI identify as **`0.1.0-alpha.81`**, the current retail-free
release candidate; its mode-`0444` archive is authenticated by the adjacent
`.sha256` sidecar. Alpha.38 and earlier remain preserved unchanged. Verify
whichever sealed archive you install with its authoritative adjacent `.sha256`
sidecar. Packaged guides remain deliberately self-hash-free.

Alpha.62 revalidates the normal ISO recognition, extraction, load, and read-only
source path against a real USA APF 2K8 image. The image stayed read-only, and no
private path, image hash, extracted game data, or retail payload is included in
the app or this guide. Its Linux install and uninstall helpers also suppress
Python bytecode before importing the installer, so they cannot create an
undeclared `__pycache__` before the fail-closed release audit.

Alpha 32 changes batch audio replacement into a no-surprises two-step flow.
Choose **Review replacement folder…** or **Review replacement ZIP…** first.
Mod Studio fully validates every supplied file without changing the project,
then shows **Supplied**, **Would change**, **Already current**, **Missing and
intentionally skipped**, **Modified audio now**, and **Modified audio after
Apply**. Nothing is staged unless you explicitly choose **Apply**; closing or
cancelling the dialog changes nothing. An unchanged-only pack is a successful
read-only review with Apply unavailable, not an error.

Apply reopens the folder or ZIP and repeats the complete validation. A private
opaque confirmation token binds the exact authored member hashes and validated
packet results to the loaded source, loaded session, and current project-audio
revision. If a payload or project audio changes while the confirmation is
open, Apply refuses and asks for a fresh review. No extracted ZIP path or audio
bytes are retained by the dialog, preview-only packet cache is discarded, and
the confirmation is queued only after its background worker has drained.

Alpha 31 adds **Add all matching (N)** beneath the Audio shortlist controls.
It collects every new playable sound owned by the currently applied search and
filters, not only the visible page, while preserving stable catalog order and
skipping duplicates. One shortlist holds at most 256 sounds. If the full set
would not fit, Mod Studio shows exact counts and adds nothing; narrow the
filters or remove selected sounds and try again. Selection-only button updates
reuse the applied result instead of rescanning all 47,814 rows.

Closing Mod Studio or choosing another game while a preview/waveform is still
decoding now cancels that private request and waits for its worker to finish
before releasing the loaded session. If several source choices arrive while a
reader drains, only the latest choice opens. This is automatic—never force-kill
the app just because a button briefly says **Cancelling…**.

Alpha 30 makes private audio decoding genuinely interruptible. While **Play**
is preparing a sound it becomes **Cancel preview**; while **Load waveform** is
decoding it becomes **Cancel waveform**. Pressing either button, selecting a
different row, or changing the loaded source signals the exact request and
stops its FFmpeg/ffprobe process group. The control briefly reports
**Cancelling…**, then becomes available for the current row. Cancelled/stale
results never play, warn, write a project edit, publish a partial WAV, or erase
an already verified cached preview.

Alpha 29 makes the large Audio workspace safer during ordinary browsing. A
search or filter change immediately fences page-wide actions until the new
table is visible, so an old page cannot be shortlisted, paged, exported, or
turned into a replacement template under new controls. Selected-row actions
remain usable because they own an exact row identity. **Clear** on the ordered
shortlist becomes a one-level **Undo** that restores as many as 256 sounds in
their exact order until the next real shortlist change or game load. Preview
preparation is also bound to the exact game/model and selected row: a late
success or failure cannot start audio or show an error for a newer selection,
and a current failure returns the button to a retryable **Play** state.

Alpha 28 adds metadata-only folder/ZIP templates for exact PCM16 WAV batch
authoring across all 47,775 individually editable AUDO/AUSB sounds. A template
may list the complete surface, while one import accepts at most 256 supplied
WAVs. Mod Studio privately sends each exact-shape WAV through a separately
configured external XMA1 encoder, then stages the whole valid set as one Undo
action. The legacy pre-encoded-XMA1 pack remains the default and byte-compatible;
import detects either generation automatically. Mod Studio ships no encoder,
and external output receives no special trust: every final XMA1 still crosses
the exact-slot, decode, duration, alias, target, and cross-family source-packet
gates. Selected-sound import accepts WAV, FLAC, MP3, OGG, M4A, and other
FFmpeg-readable ordinary audio and conforms it before encoding. Folder/ZIP
packs remain intentionally narrower: pre-encoded XMA1 or exact PCM16 WAV only;
mixed-format ordinary-audio packs are unsupported. Alpha 28 carries
forward Alpha 27's selected-sound PCM route, passive slot-43 result
`path_not_reached`, Position (17), exact 0–99 ratings, pre-build free-space
refusal, and the honest 42-active-plus-11-project-reserve planner.

Alpha.22 adds the experimental, offline-proved exact-slot XMA1 editor for all
2,261 standalone `AUDO` sounds. Its completed Xenia spot check proved that the
one-span build boots and survives repeated triggers without XMA faults; the
captured audio did not prove that the tested menu cue was actually consumed.
The UI therefore labels the writer as an advanced exact-slot workflow rather
than runtime-proved audio replacement. Alpha 27's PCM bridge makes one selected
PCM16 WAV easier to hand to an encoder the user supplies; the current selected-
sound route also conforms supported ordinary-audio input before that hand-off.
Neither route proves that every encoder or cue works.

Alpha.23 extends that advanced route to all 45,514 individually
addressed AUSB soundtrack, commentary, speech, PA, music, and presentation
substreams. It also adds a 53-row roster planner for 32 populated teams. That
planner is intentionally honest: APF still sees the first 42 players at
runtime, while rows 43–53 are project-only reserve choices that Build does not
apply.

## Install or run portable on Linux

After extracting the release, open a terminal in its top-level folder and run:

```bash
./install.sh
```

Do not use `sudo`. The installer first runs the retail-free release audit, then
copies only the exact declared program files into your user data directory. It
creates an absolute-path app-menu shortcut and a command at
`~/.local/bin/apf2k8-mod-studio`. Installation and updates are staged before
publication, so an interrupted update cannot publish half an application.

To keep the release portable instead, leave its folder together and run:

```bash
./APF-2K8-Mod-Studio.sh
```

The portable launcher resolves the application from its own location; it does
not depend on the terminal's working directory. Linux Mint/Ubuntu users can
install the system dependencies with:

```bash
sudo apt install python3 python3-pyqt5 python3-pil
```

The Mod Studio installer itself remains per-user and never invokes that
administrator command. If a dependency is absent, the launcher names the
missing package and keeps a private diagnostic log under
`${XDG_STATE_HOME:-$HOME/.local/state}/apf2k8-mod-studio`.

Run `./uninstall.sh` from either the extracted release or installed application
folder to remove it. Uninstall authenticates every owned path and preserves
projects, exports, game extractions, caches, settings, and emulator data. A
shortcut changed outside the installer is reported and preserved, not erased.

## What you need

- A clean USA APF 2K8 ISO, or its complete extracted game folder.
- Enough free space for a private extraction and a separate modded game folder.
  A complete extracted build is roughly 4 GB; keep additional working space for
  previews and exports. **Build writes into the folder you pick** — choose the
  directory Xenia already loads and confirm replace. The studio no longer
  creates an `APF2K8-Mod-TIMESTAMP` child inside an empty folder.
- Python 3, PyQt5, and Pillow. The launcher reports each missing dependency in
  plain language before trying to open the application.
- Xenia Canary for playing the result. Xemu is an original-Xbox emulator and is
  not the correct emulator for APF 2K8. On Xbox and Xenia, **title update 1.1**
  is required; it never shipped for PS3. Use **Title Update 1.1…** so Launch
  copies that LIVE package into this session's isolated Xenia content folder
  (a TU installed only in a standalone Xenia folder will not apply here).

The supported source revision is recognized by all seven hashes in the app's
read-only source ledger: the original ISO plus `0A`, `0B`, `1A`, `1B`,
`default.xex`, and `$SystemUpdate/su20076000_00000000`. A mismatch produces an
error and no source file is changed.

## The basic workflow

1. Open **APF 2K8 Mod Studio** from the application menu.
2. Choose **Load Game** and select one of these:
   - your clean USA ISO;
   - the complete extracted game folder; or
   - `0A` inside that complete folder.
3. Wait for the private index to finish. ISO extraction, catalog generation,
   thumbnails, originals, and temporary exports live in your own cache, not in
   the installed application.
4. Browse or search the asset list. Status badges mean:
   - **Editable** — Replace/Revert and the transactional build path are wired;
   - **Export-only** — local export works, but safe replacement does not yet;
   - **Preview** — a decoded structure can be inspected without an authoring
     writer;
   - **Proof boundary** — a reviewed technical witness is available but is not
     itself an editor; and
   - **Research boundary** — the finding stays visible without fabricating a
     write contract.
   Universal-browser rows add the exact export level: editable PNG, PNG when a
   codec is decoded, raw-parts ZIP only, or raw outer record only.
   These badges come from an explicit capability/action binding: a
   actionable card must have the matching
   desktop handler, and an Editable card must have real Replace and Revert
   methods (or a verified copied-volume writer). Unbound semantic findings use
   explicit Proof/Research boundaries instead of borrowing actions from a
   similarly named raw asset. Across the 37 APF
   capability records, the current source split is 19 Editable, 8 Preview,
   3 Export-only, 4 Evidence, and 3 Research. The hidden `jersey_06_runtime` proof alias
   does not create a duplicate editor in the product.
5. Select an editable item, export its PNG, edit a copy in GIMP or Photoshop,
   and use **Replace**. The app checks dimensions, color mode, and the special
   channel rules before accepting it.
6. Use **Revert** for one asset, **Revert All** for the project, or **Undo** for
   the most recent edit.
7. Save a `.apf2k8mod` project if you want to continue later or share the mod.
   The first Save asks for a name. After that, use `Ctrl+S` to update the active
   project or `Ctrl+Shift+S` to save a separate copy.
8. Choose **Build** and pick the folder Xenia already loads. Confirm
   replace; the studio writes into that folder and does not create an
   `APF2K8-Mod-TIMESTAMP` child. A copied or studio-built `0A` cannot be
   opened as source — load the retail extract and rebuild into the last
   folder.
9. Choose **Title Update 1.1…** if you have not already, then **Launch in
   Xenia**. The 1.1 LIVE package is required on Xbox/Xenia and never shipped
   for PS3.

The product currently builds a complete extracted game directory. It does not
claim to rebuild a bootable retail ISO. Never redistribute the built directory:
it contains the user's own game data. Share the `.apf2k8mod` project instead.

## Keyboard and larger-text access

- Press **Ctrl+1** anywhere in the app to focus the category sidebar. Use the
  arrow keys to choose a workspace, then press Tab to enter it.
- Press **Ctrl+F** to focus and select the visible, enabled search field in the
  current workspace. If that page has no available search, the status bar says
  so and points back to **Ctrl+1**.
- The focused category and asset lists use a strong outline instead of relying
  on color alone.
- Navigation, operation status/progress, source safety, Build, and Xenia Launch
  expose descriptive accessibility text and tooltips.
- The header and footer can grow with a larger Linux system font instead of
  clipping fixed-height controls. These are headless Qt contract checks, not a
  completed visual or screen-reader certification.

## Author one selected sound from PCM WAV

Every individually editable Audio sound now has five complementary actions:

- **Drop .xma or audio file here** routes one local file without opening
  a chooser, while keeping the same validators as the matching button;
- **Export PCM authoring template…** creates a new exact-length, source-free
  PCM16 silence WAV for that selected slot;
- **Replace from PCM WAV…** accepts ordinary audio, conforms it to PCM, runs a
  separately installed encoder, and admits its output only after the signal
  comparison and every exact-slot gate pass;
- **Replace with XMA1…** keeps the direct pre-encoded advanced route; and
- **Revert sound** removes that selected staged replacement.

To use the PCM route:

1. Select one standalone AUDO row or one AUSB substream.
2. Either export its template and replace the silence, or choose/drop an
   ordinary WAV, FLAC, MP3, OGG, M4A, or other supported audio file. FFmpeg
   conforms non-exact input to the slot's exact PCM16 shape.
3. Choose **Configure XMA1 encoder…**. Select a trusted encoder you legally
   obtained. A Windows `.exe` can use a separately installed Wine executable.
4. If the tool needs switches, open Advanced and enter one literal argument per
   line. This is not a shell command. `{input}` and `{output}` are required;
   channel/rate/sample-count/encoded-size placeholders are available.
5. Choose **Replace from PCM WAV…**. The encoded result is decoded back and
   compared with the authored PCM for silence, channel routing, rate/pitch,
   clipping, DC, and tail failures before exact-slot validation. Cancellation,
   timeout, tool failure, signal failure, or validator failure adds no edit.

You may instead drag that `.wav` onto **Drop .xma or audio file here**.
An `.xma` drop takes the direct pre-encoded route. The drop target accepts
exactly one local regular file and rejects folders, links, remote URLs, multiple
files, and other extensions. It is disabled on bank/index rows. All Audio
mutation/template controls disable immediately for PCM, direct-XMA1, and pack
work, then return only after the owned worker is unregistered. A drop never bypasses shape,
packet, decode, source-reuse, alias, project, or Undo checks.

Encoder/Wine paths, arguments, and timeout are PC-local settings, not project
data. Mod Studio does not bundle an encoder. A fake encoder proves only the
headless bridge mechanics. The alignment-aware artifact comparator and its
fail-closed handoff have synthetic proof, but no real XMA1 encoder compatibility,
perceptual transparency, or in-game audibility is claimed. Alpha 28 can use the
same configuration for exact PCM16 folder/ZIP batches; those batch v2 payloads
remain exact WAVs even though the selected-sound chooser accepts ordinary audio.

Read the complete [external encoder guide](apf2k8_external_xma1_encoder.md) for
placeholders, error messages, safety gates, and the exact proof boundary.

## Uniform editing

The first editable uniform surface contains 96 physical assets:

| Family | Count | Required PNG | Important channel rule |
| --- | ---: | --- | --- |
| Jersey | 24 | 1024×1024 RGBA | The channels feed material masks; the PNG is not a literal final-color decal. |
| Pants | 24 | 512×512 RGBA | Alpha must be 255 everywhere. |
| Helmet | 24 | 256×1024 RGBA | R/G carry the two stored mask planes; B must be 0 and A must be 255. |
| Shoulder | 24 | 1024×1024 RGBA | Edits `shoulder_color`; the paired normal package is preserved. |

### Why a same-size replacement can still be refused

Every uniform slot is a **fixed allocation**: the game reads that entry from a
fixed span, so the rebuilt entry cannot grow. Matching the required PNG
dimensions is not enough — what has to fit is the *compressed* result, and a
slot's budget is retail's own compressed payload plus a small sector slack, with
the payload as the dominant term. A slot whose retail artwork is nearly flat has
a small payload and therefore a small budget, however much free space it appears
to have. Measured across the 24 shoulder slots (davidhbui, Beta 38): the slot
with the **most** sector slack is 18th of 24 for capacity, and refuses a
detailed mask that two roomier slots accept.

The detail line under a selected jersey or shoulder slot names its budget and
its rank in that family, so a slot can be chosen before a build is spent on it.
Jersey uses the same compressed-budget model as shoulder. If a build
does refuse, the message names the slot, its outer entry, its allocation, and
its budget — and if several targets are over, it reports all of them at once.

These are region masks, so the fix is almost always the same: snap colours to
the retail palette and remove anti-aliasing. An anti-aliased edge emits invalid
region IDs rather than a soft edge, and it inflates the payload — one measured
cleanup (800 colours → 3) cut a file's overflow by 56%.

The Uniforms page starts with two texture workspaces. **Editable Materials (96)** is the
bounded writer above. **Additional Assets (312)** inventories every other
uniform/equipment record: 275 more textures, 24 NumberFont resources, 11
NameFont resources, and two scenes. Together they cover all 408 indexed
uniform/equipment records without duplicating the 96 writer targets. Additional
items are searchable, previewable when decoded, and exportable, but they remain
read-only until an exact writer owns their format and archive boundary.

**Equipment Colors** is the all-team HOME/AWAY equipment selector editor.
Choose any of the 40 teams, then independently pick the facemask-bar color and
the color used by players whose turtleneck setting is **Team**. Each dropdown
shows the bank's exact palette index, name, hex value, and swatch. The writer
changes only helmet selector slot 3 byte 6 and turtleneck selector slot 0 byte
2; both full palettes, their metadata, and every other selector byte remain
exact. Visors stay in **Save Players** as the proved per-player None/Clear/Dark
choice because APF has no verified per-uniform visor-tint field.

**Custom Team Appearance** is a separate bounded workspace for user-team slots
32–39. Pick a slot, edit the ten HOME and ten AWAY ARGB swatches, and inspect or
author the exact eight-byte helmet and crest selectors. Only helmet asset byte
0, helmet shell-palette byte 1, and crest catalog byte 0 have proved names; the
remaining selector fields are intentionally labeled opaque. **Apply 2017
Eagles preset** preserves the chosen helmet model, selects crest catalog 30,
preserves the complete helmet-selector tail, applies the exact Xenia-proved
Eagles crest-routing tail, and sets both banks to the midnight-green/silver/
white palette. The individual routing bytes remain unnamed. Choose
**Stage appearance** to add its replacement-only JSON to the project; the
normal Build path composes it with roster names, ratings, and positions and
independently reparses the result.

The same panel now has a separate **Raw Roster Save · runtime user team**
source. Use this only after a custom team has been accepted and saved: the
game's user-facing team IDs 24–31 are the save's ROST slots 32–39. Choose a raw
`Roster.ROS`, select the occupied team, apply the Eagles preset or exact values,
then choose **Write verified raw save…**. The source is opened read-only; the
editor exclusively creates a separate raw payload and JSON receipt, SHA-binds
the inspected source to the write, accounts for the exact 112-byte authorized
union per edited team, reopens both files, and independently verifies the
pointer graph and changed-byte set. Save bytes and paths never enter the
`.apf2k8mod` project.

`CON `, `LIVE`, and `PIRS` STFS packages can be opened directly in this panel.
The editor verifies the STFS metadata/hash tree and the complete `Roster.ROS`
block chain before showing the eight user-team slots. Use **Extract verified
Roster.ROS…** for an exact raw copy, or stage an appearance and use **Write
patched raw handoff…**. Both operations create a new raw payload and a
source-bound manifest; neither writes a signed container or claims to verify
its RSA signature. Reinject, rehash, and resign with an external save manager.
LIVE/PIRS retail signatures require Microsoft's unavailable private keys; CON
signing requires the owning console's private keyvault.

The raw-save handoff and its receipt prove only the bounded file edit. They do
not establish emulator consumption, gameplay visibility, or Xbox 360 hardware
behavior, and the editor does not need to launch an emulator to build or verify
the output.

These are shared physical assets, not 40 independent team slots. Before
replacing one, read **Affected teams** in the asset details. Every listed use
will receive the edit. Selector-bank de-aliasing is still experimental and is
not silently performed by the app.

Jersey asset 6 has positive visual runtime evidence and is corroborated in the
Home/Away editor. Pants has a separate positive witness: an unmistakable
red/white/blue checker appeared on the Americans Away Uniform Type PANTS leg
preview. Helmet and shoulder have passed bounded offline reconstruction but do
not yet have positive visible proofs. Those distinctions remain in the UI.

### Team crest workflow

Open **Logos & Team Art → Team Logo**. After a game is loaded, the selector
contains all **118** `uniform_logo_00.iff` through `uniform_logo_117.iff`
packages. Built-in team names come from the source selector graph; the other
game-library slots stay index-labeled because their in-game picker ownership is
not proved.

The ownership line beneath the editor shows exactly what the selected index
means. Selector slot 5 links crest package `uniform_logo_NN.iff` to the same
index `N` in the statically mapped frontend/Team Select `uniform_logocache`,
and Team Logo co-writes both. Selector slot 6 is a different 206-entry
rectangular wordmark bank owned by **Wordmarks**; Team Logo never resizes the
square crest into it. This is a static storage/path statement, not proof that a
changed cache image was consumed during a running Team Select screen.

1. Select a slot. Retail coverage keeps its existing exact/contain resize flow.
   For Full-shell, choose **Normal logo — convert to APF regions (recommended)**
   for ordinary painted art, or **APF region mask — exact channels (advanced)**
   only for an authored mask already on the Xenos four-bit lattice.
2. Choose **Retail side decal** to preserve stock geometry, or choose
   **Full-shell crest wrap — entire helmet shell (affects every team)** for the
   fixed `front_crown_to_rear_v1` stock-shell atlas route.
3. Normal-logo import contains the whole source at 512×512, suggests three
   colours only when the artwork itself has a stable colour triangle, and
   requires you to confirm/edit the rendered helmet shell and two detail
   colours. Inspect the palette-mapped preview and error metric: APF stores
   colour weights, so the editor does not pass through or promise literal
   source RGB. Advanced import instead rejects non-four-bit components,
   nonzero blue, overweight red/green sums, hidden RGB under alpha zero, and empty masks.
4. In **Place on helmet…**, drag the converted/validated mask on the labeled **FRONT / CROWN →
   REAR** guide, or edit X center, Y center, independent Width/Height, and
   Rotation. **Auto-fit front → rear** spans the proved shell envelope;
   **Reset** restores the imported placement. The accepted result is always an
   exact 512×512 semantic RGBA design. Nearest-neighbour transforms
   preserve the region-mask palette; empty or clipped/off-canvas art is refused.
   Reopen the canvas to adjust again: during this editing session it reuses the
   normalized original import and last transform instead of resampling the
   flattened staged PNG. The old one-shot fit checkbox is hidden so it cannot
   silently erase an authored X/Y placement.
5. After an external import, choose **Save high-resolution authoring master…**
   if you want a portable `.2ktexmaster` sidecar. It retains the exact original,
   palette/semantic pipeline, final placement controls, exact staged 512×512
   mask, and a direct 2×/4× authoring render. A later built-in pixel edit is
   recorded as a native edit layer without discarding the original. The action
   never overwrites an existing file and creates no RPCS3 texture pack.
6. Choose **Build copied 0A (team logo)…** and select a new output path. This is
   a headless file build; it creates no Xenia patch and never edits
   `default.xex`.

If a Custom Team Appearance slot is staged, the confirmation lists it and the
same action composes the crest package, custom-team ROST records, and logo cache
into one copied `0A`. A separate appearance receipt proves the final ROST was
reopened and decoded. Other staged Mod Studio edits are not silently included
in this specialized Team Logo action.

The same staged crest is mirrored into `logo_l0` and `logo_l1` in both the
selected package and matching uniform-logocache index. Both packed mip tails
are regenerated, not preserved. The source stays read-only; the package writer,
cache writer, and independent cache verifier account for the new copied volume.
The raw cache directory/payload pair is dispatched to its dedicated verifier,
not parsed as two ordinary IFF entries.

For every full-shell build, the editor maps the fixed semantic canvas directly
to physical shell Z (front to rear) and Y (top to the audited opening bound),
then bakes it bilaterally into the noncollapsed, consistently oriented,
nonoverlapping retail high/low shell UV atlas. It changes no shell vertex,
index, or UV. The old bounded overlay is replaced by in-range repeated indices
that produce zero triangles. Before that shared route can be published, both
layers of all 118 crest packages are rebuilt in memory: the selected package
gets the new shell atlas; every other package's retail RGBA mask is sampled from
its original draw-2 physical Y/Z placement into the shell atlas. The selected
menu cache receives the semantic design rather than the distorted atlas. Any
compression overflow fails before the one copied output volume is created.

The v24 all-package headless gate compiled and reparsed **121 outer entries** in
memory before any output was created: all 118 source-resolved crest packages,
cache directory 171, cache payload 213, and shared helmet outer 1310. If a
custom-team appearance is staged, outer 1126 is composed as one additional
entry. The pristine source remained unchanged, all 117 non-selected retail
crests were migrated, and the selected Eagles shell-atlas hash matched its
pinned value. The exact atomically published candidate then passed an
independent 118-package/236-layer reopen plus a **10-view static asset-space
visual gate** at the stock high and low helmet LODs. Visual review of both
hash-pinned contact sheets found a coherent shell-spanning Eagles wing from
side/front/crown through the rear, with its low-LOD silhouette retained and no
smears, gaps, holes, seam breaks, or visible UV artifacts. This proves the
static Eagles visual match, not game consumption; the proof used no Xenia, Wine, emulator,
controller, or FIFO. The frontend menu-cache path is statically mapped;
gameplay consumption and the scorebug dynamic sampler's package-versus-cache
resolver, plus Xbox 360 hardware parity, remain unproved.

Since that static gate, one bounded runtime witness exists. On 2026-08-03 the
accepted user team's raw save — the Manage Team flow, not the Create Team
scratch editor — combined with the catalog-30 crest package/cache and the
retired global crest-box emulator patch, rendered midnight-green Eagles
helmet previews on **Main Menu → Teams → Manage Team → Edit Team → Logo
Selection**, and strict visual review passed both HOME and AWAY. The witness
proves the coupled accepted-team save + catalog-30 package/cache + emulator
crest-box patch path in a menu preview. It does not isolate package from cache
ownership, prove the scorebug or other menu consumers, or establish Xbox 360
hardware parity. Full receipts are in the
[custom-team appearance findings note](../research/apf_custom_team_appearance.md).

**Known defect, fix in flight:** in live gameplay the v24 shell currently
renders semi-transparent/flat (background alpha `0x88`). Until the fix lands
and is re-witnessed, live-gameplay shell rendering is explicitly not claimed
as proved; the static 10-view gate and the menu witness above stand on their
own.

### Uniform wordmark workflow

Open **Logos & Team Art → Wordmarks** for the separate rectangular team-text
family. The typed selector exposes all **206**
`uniform_textlogo_00.iff` through `uniform_textlogo_205.iff` targets and lists
the teams currently selecting each asset through ROST slot 6. These indices do
not generally match the 118 square crest indices.

1. Select a wordmark index from 0 through 205.
2. Choose **Contain** to keep the entire image or **Cover** to fill and crop the
   exact 512×128 canvas, then import or drag a PNG. Transparent pixels are
   composited onto opaque black because the retail texture is BC1 without
   alpha. The preview is the exact staged image.
3. Choose **Replace** to stage it. Revert, Revert All, Undo, project save/load,
   and normal Build work like every other typed uniform asset.

Build regenerates all six tiled BC1 mip levels, token-preserves the package's
H7A streams inside the original fixed allocation, reparses the IFF, and runs an
independent whole-volume verifier on the copied output. The source `0A` is
never modified. Wordmarks do not edit square crests or crest-cache layers, and
Team Logo does not silently reshape a crest into a wordmark. File transport is
offline-proved; the exact in-game/menu consumer and Xbox 360 behavior remain
unproved.

### Helmet and player POSITION round trip

Open **Uniforms & Equipment → Model Export**. The dedicated cards remove the
need to discover the stock targets manually:

- **Helmet:** outer 1310, inner 128, `helmet_00`, 33 meshes.
- **Player:** outer 1310, inner 273, `player`, one mesh.

Each export button reads `0A` without modifying it and writes new `.gltf`,
`.bin`, and source-bound v2 `.apf-model.json` files. Edit vertex positions only,
keep the companion manifest, do not apply mesh-node transforms, and do not add
or remove vertices, faces, attributes, materials, or primitives. **Import edited
glTF** independently reopens the loaded source, verifies every expanded triangle
and vertex count, quantizes XYZ into the existing signed-normalized lanes, and
writes a new `0A` plus receipt without overwriting the source.

This is a structural round trip, not a general DCC re-export path. A program
that removes the exported node identity, bakes transforms, emits normals or
materials, or reorders the expanded indices will produce a glTF that the
importer deliberately refuses. Keep the emitted glTF structure and edit only
the float32 POSITION values in its companion binary.

The importer preserves POSITION W, normals, packed tangent/UV data, blend
indices/weights, existing skin/attachment data, materials, animation, collision,
and every byte outside POSITION XYZ. It therefore cannot replace the stock mold
with a SpeedFlex/F7 model or author rigs, materials, UVs, normals, topology, or
attachments. The offline round trip is verified; in-game/Xenia/hardware model
visibility is not claimed.

## Give every team its own uniform textures (Team Independence)

APF's forty teams draw helmets from only six textures, jerseys from nine,
numbers from seven, and socks from six — painting art on a shared helmet puts
it on every team that wears it. The **Team Independence** tab on Uniforms &
Equipment writes a new `0A` in which each built-in team points at its own
packages: helmets 6→24, jerseys 9→24, numbers 7→24, socks 6→24, pants 11→24,
shoulders 14→24, fonts 7→11 (95 selector assignments). The game already ships
24 complete helmet packages with only six referenced, so nothing is added —
teams are simply pointed at slots that were already there. The tab lists every
helmet with the teams currently sharing it and marks unused packages free to
take over. Only selector bytes change, uniforms look identical until you edit
them, and the loaded volume stays read-only while the new one is written.
In-game visibility of the repointed selectors is not yet proved; treat the
output volume as the authoring precondition for per-team art.

## Roster and true 0–99 ratings editing

Open **Rosters & Players** to search the live roster by player, team, stadium,
or membership. Player rows identify **First name** and **Last name** fields;
team rows identify **Display name**, **Abbreviation**, and **Secondary
abbreviation**. In the Alpha.21 package, every nonempty pure player
first/last-name allocation and every team **Display name** allocation is
editable under the exact character limit shown beside it. Select the field,
type replacement text, choose **Replace Player Name** or **Replace Team Name**,
and use the matching **Revert** action to remove only that shared allocation's
edit. Both abbreviation fields remain visible and locked because their
individual runtime-consumption routes are not yet proved.

The complete map contains 3,273 fixed UTF-16BE string-pool allocations and
4,628 mapped references. The product admits exactly 3,191 nonempty player-name
allocations serving 4,482 writable first/last-name references plus 40 team
display-name allocations: 3,231 product-editable name allocations in total.
One empty allocation has zero writable characters and remains locked. Team
abbreviations, mixed team/player ownership, unknown ownership, and every other
identity scope also fail closed.

Names are often aliases rather than independent fields. There are 429 shared
editable player-name allocations; the largest has 23 owners, and 61 are used
by a mixture of first- and last-name fields. The details panel lists every
owner as a retail-free semantic coordinate such as **Player 788 · last name**.
Read that list before replacing: one edit changes every disclosed owner
together. Alias-owner lists stay local to the loaded game and are not saved in
a shareable project.

The complete public workflow has been exercised against the recognized source:
load, replace Dan's last name with `CODEX`, Undo, replace, Revert, replace again,
save a project, reopen that project, Build a separate 3.7 GB game, and reparse
the result. The project is 989 bytes with SHA-256
`45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`
and contains replacement JSON only. The built `0A` SHA-256 is
`0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
matching the runtime-proved candidate exactly. Only outer entry 1126 changed;
the loaded source stayed unchanged.

Isolated visual QA also passed after the layout fix. **Identity & Names** is
visible by default, **Base Ratings (28)** sits beside it, and a 23-owner shared
name shows **Replace Player Name**, **Revert Player Name**, and **View 23
affected fields…** together with the exact `4/4` limit—without clipping or a scroll trap.
The owner dialog uses high-contrast text and displays all 23 semantic owner rows
at once. These checks ran on an isolated desktop and did not touch the user's
mouse.

The original generic H7A rebuild failed in Xenia because its decoded pointer
graph was relocated twice. The replacement path preserves every still-valid
token and splits only the tokens touched by an authored allocation. Its bounded
runtime result is positive:

| Edit | Runtime result |
| --- | --- |
| Team display name `Americans` → `CODEXTEAM` | Booted through first-run team construction; authored text appeared in Logo Selection, Team Summary, and Team Select. |
| Player last name `Marino` → `CODEX` | Booted without the old roster crash; **Dan CODEX #13 QB** appeared in player selection and **QB #13 DAN CODEX — GOLD STAR** appeared on the Star Card. |
| Dan Marino `Speed` 40 → 99 | Booted; the edited player record loaded and rendered on the live player card without the former startup crash. |

Full evidence is in the positive
[roster identity runtime report](../product/APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md)
and [rating runtime report](../product/APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md).
The earlier [negative report](../product/APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md)
is retained as diagnostic history; it describes the superseded generic rebuild,
not the current product route.
The ambitious capacity question is tracked separately in the
[32-team/53-player feasibility note](../product/APF_32_TEAM_53_ROSTER_FEASIBILITY.md);
that note does not unlock abbreviations, membership, depth charts, or true
53-player active rosters. Player-name editing changes existing bounded strings;
it does not expand the active roster structure.

Alpha.23 adds a separate **53-player roster planner** inside
**Rosters & Players**. Choose one of the 32 populated source team records to see
53 rows:

- slots 1–42 show the source memberships APF currently recognizes in-game;
- slots 43–53 accept eleven authored **project-only reserve** choices; and
- **Save reserve plan…** writes a retail-free `.apf2k8roster` containing only
  those reserve player indices. It never copies the 42 source memberships,
  player records, names, ROST bytes, preimages, or executable bytes.

**Build Modded Game does not apply these reserves.** The planner is useful for
building complete league concepts and validating that no reserve duplicates an
active or another reserve assignment. True runtime slots 43–53 require a
version-pinned XEX accessor/direct-consumer patch plus owned side-table storage.
Teams 25–32 are populated online-placeholder records with real 42-player source
rosters, but their offline Team Select ownership is still unproved.

Selecting a player opens **Base Ratings**. The 31 rows are independent stored
attributes, not percentages derived from one Overall. Choose an attribute,
enter an integer from 0 through 99, and press **Apply Rating**. A changed row
shows a modified badge; **Revert Rating** removes only that player/attribute
edit.

The same player also enables the **Position (17)** tab. Choose one of the exact
named positions from QB through DE, then press **Apply Position**. The row and
panel show that the position is modified; **Revert Position** removes only that
player-position edit. Mod Studio writes the game's semantic `+0x34` byte and
required `+0x35` mirror together. It does not move the player to another team or
depth-chart slot and does not recalculate ratings, Overall, tier, or abilities.
The writer is offline-proved, but its first changed-position Xenia spot check is
still pending. Player-name, team-name, rating, and position edits can coexist in
one project and one token-preserving Build.

For a whole-league edit, choose **Export ratings sheet…**. The private v2 CSV
contains exactly 2,254 player rows and one stable column for each of the 31
attributes. Edit only the `rating.*` columns, save as UTF-8 CSV, then choose
**Import ratings sheet…** (or press **Ctrl+Shift+I**). Mod Studio checks the
complete 69,874-cell sheet
without changing the project and shows replacements, reverts, matches,
conflicts, and errors before Apply. A wrong-game sheet or changed source-owned
identity column cannot be overridden. If a sheet disagrees with an existing
in-app rating edit, you must explicitly acknowledge that conflict. A successful
import is one Undo action; an invalid or already-matching sheet adds no action.

The sheet contains names and source-derived values from your own game, so keep
it private. Share the `.apf2k8mod` project instead. Projects contain only your
authored rating numbers, selected player-position codes, or replacement name
text plus stable semantic target metadata; they never embed the CSV, original
names/values, source position codes, alias-owner lists, player records,
preimages, or retail game bytes.

The engine can read a native value of 100. If the source contains one, the app
displays 100 exactly instead of clipping it, but new edits are intentionally
limited to the familiar 0–99 scale. Overall is calculated separately by
position. A position edit is explicit and separate; rating edits never infer or
change it. The on-disc rating and position editors do not infer or change
abilities, Gold/Silver/Bronze tier, equipment, membership, depth charts, or
jersey numbers. Jersey numbers remain **read-only / unmapped in the on-disc
`0A` project lane** because no consumer-backed on-disc field has been
identified. Use the separate **Save Players** raw-save workspace for the exact
packed APFe jersey-number, ability, tier, depth, appearance/equipment, text,
and count-preserving membership fields it explicitly exposes.

### Paired RPCS3/Xenia roster-label audit

The supplied stock APFe text exports contain **1,344 rows** each. The comparison
is positional because the header has 169 labels for 177 fields, repeats
`RunCoverage`, and leaves eight trailing fields unlabeled. The audit preserves
those hazards instead of inventing names and normalizes only the exact bounded
`TeamJerseyBytes` RGBA-to-ARGB platform serialization.

After that normalization, 1,312 rows are equivalent, one is the known stock
identity variant, 31 are randomized Atoms filler rows, and **zero are
unexplained**. The stock identity is RPCS3 **Mike Haynes** versus Xenia **Mark
Smith**, not Mike Smith. Only First, Last, College, DOB, Number, Photo, PBP, and
Age differ; their equipment, ratings, and skills match positionally. Here PBP
means the play-by-play announcer identifier, not playbook.

## Presentation editing

`digital_font` is an additional editable 128×128 RGBA texture. Its RGB pixels
must all be white; draw the glyph mask in alpha. The app preserves the fixed
allocation and validates the rebuilt entry.

Other scorebug and presentation resources remain visible at their registry
status. They do not become writable merely because a raw texture can be
exported.

The **Presentation Map** names all seven field-scorebug scene components and
shows their mesh/triangle counts beside the `digital_font` writer boundary.
It also reports the closed draw/material texture ownership trace. Four scenes
own 11 embedded textures total; the team-logo scene deliberately owns no
embedded TXTR. Its two logo quads use two runtime-injected samplers. Team Logo
updates both candidate reservoirs (`uniform_logo` gameplay packages and the
separate `uniform_logocache` menu cache), so the editor does not need to invent
a third scorebug texture. Which cache the runtime sampler resolves remains
unproved. Season GameCast, clocks, timing, replay/halftime presentation, and
scorebug audio remain separate systems.

## Draft logo editing

The Logos & Team Art tab exposes one additional bounded target:
`draft_logo`, a 128×128 RGBA PNG stored as a single-level BC3 texture in
`franchise.iff`. It has the same Export, Replace, Revert, modified badge,
Undo, project-save, and Build workflow as other editable PNGs.

This draft resource is separate from both the Team Logo crest and Wordmarks
workflows above. It also does not claim that a
Logo Selection thumbnail consumes `draft_logo`. The writer and archive rebuild
are offline-proved; an actual franchise/draft screen still needs a positive
runtime witness.

The registry gives this writer its own
`apf2k8.logos_cards.draft_logo` capability instead of letting it inherit the
broader read-only logo catalog's status. The current registry contains 37 APF
records and 70 records across all registered game/platform targets. Those numbers describe
product capabilities, not the number of logos or editable team slots.

## Edit every proved player field in a roster save

Open **Rosters & Players → Save Players**, then choose a raw `Roster.ROS` or a
`CON ` / `LIVE` / `PIRS` package. A signed package is hash-tree verified and its
`Roster.ROS` is extracted read-only; the editor never labels its output as a
signed container.

1. Choose player index 0–2253. The panel shows the source identity and exposes
   all 149 exact packed/numeric fields in one searchable category-labeled list.
2. Stage any base rating, ability, style, tier, number, mirrored position,
   depth, appearance/equipment, or exact ID/metadata change. Choice-backed
   fields offer only proved values.
3. For any of the 15 known player text fields, enter replacement text that fits
   the displayed existing UTF-16 allocation. Shared aliases show how many known
   fields will change together.
4. To move existing players between depth-chart memberships, choose two
   populated team/slot entries and stage a swap. This cannot add a 43rd player,
   create duplicates, or change any roster count.
5. Write a new raw save. Keep the adjacent `.players.json` receipt with it.

The independent verifier reconstructs the selected bit masks, preserves all
unselected bits and every text pointer, reparses all 2,254 players and 40 teams,
and checks the complete membership multiset. Whole-pound weight editing leaves
the low packed nibble used by abilities untouched. Overall is intentionally not
offered because the complete engine formula is not proved.

For a signed source, reinject the new raw `Roster.ROS`, rebuild the STFS hashes,
and resign it with the owner's save manager/keyvault before emulator or hardware
testing. Mod Studio does not have Microsoft signing keys or the owner's keyvault.

## Assign existing playbooks in a raw save

Open **Playbooks & Plays → Save Assignments**. This workflow changes the
team-to-playbook pointers in a roster save; it is separate from the neighboring
on-disc inspector and stock assignment-route editor.

1. Choose a save. All 40 team slots and their current offense/defense choices
   are listed.
2. Select one of the **36 offensive** books and one of the **33 defensive**
   books, then choose **Stage both assignments**.
3. Stage any other teams, then write a new raw save and manifest.

The writer rechecks the inspected source SHA-256, never opens the source for
writing, refuses output aliases and overwrites, changes only the selected
assignment pointer bytes, reparses the result, confirms the 69-name book table
is unchanged, and runs an independent verification pass.

Synthetic fixtures remain green. A private raw-save witness also parsed all 40
teams and 69 books, changed team slot 32 offense 25→13 and defense 56→32,
accounted for exactly two assignment fields / three bytes, reopened to IDs
13/32 with the book table unchanged, then reverse-patched to the byte-exact
original. This proves bounded raw-save transport only; gameplay consumption in
Xenia or on Xbox 360 remains unproved.

## Fine-tune stock CPU playbooks

Open **Playbooks & Plays → Fine-tune Plays**. This edits the on-disc `SPLB`
membership lists, not the save-assignment labels.

Fine-tune Plays changes which MASTER plays a formation **stores**. It does
not change who lines up. Personnel comes from the formation package map
(MASTER `+0x11`). A play named `50 TE Corner` can live in I Spread (20 / 0 TE)
because the play is routes and assignments on whatever slots that formation
plugs. Play names are not personnel. **Move tagged slot…** only reassigns Y
tags inside one record.

Open **Playbooks & Plays → Who lines up** to edit that package map. Role 8 is
TE and role 9 is WR. The other nine roles stay numbered. The project stores
the 11 role bytes per formation; Build writes them into the copied MASTER
PLAY. Runtime look is unproved — check the formation in Xenia after Build.
This is not a 3rd-and-long director patch. The old raw WR3↔TE `.bin` export
is still gone: it was not a playable mod.

The reported user-team/CPU difference on 3rd-and-long also has no editable
setting in MASTER PLAY, the stock playbooks, or the director files. The
behavior appears to be implemented in `default.xex`, which Mod Studio does not
patch. **3rd-and-long editing status…** explains that boundary without changing
anything. Technical addresses remain under **Research pins**.

- Tick plays in or out of a formation. Tagged slots follow `min(4, plays)`.
- **3rd-and-long editing status…** explains why this behavior cannot currently
  be changed. It is a status dialog, not a writer, and can be opened repeatedly.
- **Move tagged slot…** can hand a slot to a play you just added in the same
  request (the X-43Blitz Bear case). That only reassigns Y tags inside one
  record. It does not change who lines up.
- **Save Project keeps these edits.** Before alpha.71 the panel was the only
  place they lived, so a saved project reopened with the playbook apparently
  untouched. The project now stores each staged change as a selector — outer
  entry, record, play indices — and never a byte of your `SPLB` resource.
  Reopening a project keeps every staged book. Switching books no longer
  discards the others — a project can hold all fifteen stock books and Build
  writes them all into one copied 0A. The writer still compiles one book per
  call; the session groups by outer.
- **Empty this formation… changes what the CPU does, in a way this project
  cannot yet predict.** Urianus emptied the formations without a TE in
  `O-ManBlock` on alpha.70 and the CPU lined up personnel packages that book
  does not contain (00, 10, 01, 12, 11) and one the game does not ship at all
  (02), running plays that are not in the book. It happened whenever the
  director selected an emptied formation; the books he had not touched behaved
  normally. Plays are not bound to formations — he moved an offensive play into
  a defensive book and it ran — so a formation that stores nothing does not
  make the director skip it, it makes the director call something the book
  never listed. The static side is unchanged and was never a safety proof:
  `min(4, 0)` is 0, the record trailer still names the formation, and the
  executable's count (`0x84a8ac30`) and get-nth (`0x84a8bd20`) return 0/null,
  so the four tagged plays cannot come from that record. Emptying **every**
  populated formation in a book is refused: that leaves the director nothing at
  all to select. Adding a play whose name mentions TE, or moving a tagged slot
  onto it, does not change who lines up. Emptying one of an exact “ Flip”
  twin (Ace / Ace Flip) without the other hangs on load, so the panel
  empties both together. Weak I Jokers Flip Pair is not that kind of twin.
  Emptying a defensive formation still lets the director select it and call
  something the book never listed, except X-43Blitz 4-3 / Bear, which falls
  back to the other formation.
- **Research pins** shows every executable address behind these statements,
  including the candidates that were checked and withdrawn.
- **Who lines up** stages the 11-byte `+0x11` map as a project edit. Role 8
  is TE and role 9 is WR. Runtime look is unproved. Retail Ace Empty is not
  an 8↔9 swap of Ace (slots 9/10 are 6↔7). The former raw WR3↔TE export had
  no import, Build, or installation path and is no longer in the product.
  **3rd-and-long editing status…** explains that the reported CPU/user-team
  fork appears to live in `default.xex`, which Mod Studio does not patch.
  MASTER categories at
  `+0x44` are personnel packages (Ace, 5 Wide, Flush); `0x8485bd38` extracts
  the trailer index. `0x84a472d0` is play-type UI, not down; `0x8486ce88`
  picks a play from situation word0 / `+0x2BC` (a tab). Eligibility ANDs
  map-role masks at `0x820FC380` with a personnel cell (also
  `0x84862580`). `0x844dbe00` is `.pdata`, not a script table.
  `0x84b694a8` is not a play picker. `0x84a89ea8` maps a play onto an
  SPLB record; situation `+0x1F8` is a play-type filter, not down.
  `0x848699d8` filters by type nibble. `0x8485e7f8` has 0 `bl` callers;
  playcall `+0x20` (`0x851A2780`) is the current book the fetch reads;
  `0x8493d968` registers that object. `0x8466af70` loads `dir_ingame.iff`.
  `0x8466a818` relocates DRCT pointers (NFL `0x000dc700` analog);
  `0x8466aae0` walks the relocated fixed table, not the instruction consumer.
  `0x8466abc0` indexes fixed-record children via `+0x18`; `0x8466af28`
  indexes strings via `+0x14`. Picker `0x8486ce88` takes the playcall
  object as `r3` (`0x8470c2c4`). Jump-table `0x8470bf18` takes a small
  integer mode 0..19 (`0x84712498`); case 2 (`li r3, 2` at `0x847163d4`)
  is frontend, not CPU down/ytg. Find-by-slot's book singleton is
  `0x8520CDE0` (init `0x84a139d0`). Shadow `0x84887e18` writes bitmasks
  to `0x8516C908+0x20`, not a book. Slot `+0` can be type singleton
  `0x850F1218` (install `0x84ad0048`); init `0x847c6da8` copies live
  MASTER from `0x84F3F7D8+0x2C` (`0x849fd6a8`) onto type `+0x20`.
  Helper `0x8486cd80` is UI-only. Setter `0x849fd6c8` is bind/SPLB-select
  (table `0x851D9660` via `0x849fcf60`), not per-play. `0x849d81d0` is
  init-stored at `0x84E28670+0x2C94` (0 `bl`). `get_down` lives only
  in packed property blob `0x84EB0DE4`. Property-get-by-id `0x849c9c90`
  uses ids 997..999, not down. Relocator `0x8466a994` inlines the
  instruction directory at `+0x20`. NFL `0x000dca40` is a bitset/float
  lookup, not an instruction indexer. `dir_ingame.iff` (outer 153) has
  1015 instruction records; 1014 begin `0B 00 01 00` then a token at +4
  — bytecode, not a C++ vtable. The relocator rewrites only the inline
  directory words; it does not follow those pointers into record bodies.
  Packed `lhz +6` getter `0x84ab2010` has 0 `bl` and 0 inbound pointers.
  DRCT vtable[2] `0x8466ba30` unlinks a list. Byte-stream `0x8466bd38`
  compares 94/96/97 and 275–330, not instruction tokens. `0x84bcd760`
  is a string classifier (0 `bl`). 0 `addi 32`/`lwzx`/`lbz 0(record)`
  consumer. `dir_wrapup.iff` (outer 265) has 96 records, all `0B 00`.
  Groups are tagged fields (`0B 00` + u16 field + u8), not a VM opcode
  at +4. vtable[0] `0x8466b8b0` only relocates then walks the fixed
  table (`bl 0x8466aae0` at `0x8466b8fc`). Packed +0x14/+0x18 indexers
  have 0 `bl` and 0 inbound pointers. `0x8466af48` is a bounds check
  (r4 < +0x10), not a type mapper. `0x84b162a8` is an embedded C++
  object at +0x20. `lbz`+`cmpwi 11` then 12 is a class-id, not tag
  `0x0B`. Field ids inside `0B 00` groups are BE u16 `0x0100`/`0x0200`,
  not 1/2. Nested lead bytes `0x03`..`0x09` appear after those groups.
  0 `lhz`+`cmpwi 0x0100` parser (`0x84c381e8` is stack/float). 0
  skip-`0B 00` then `lhz`. 0 `lhbrx` in TEXT. `0x84a87b38` is play-type
  nibble `srwi 28`. `0x84bdfb00` is ASCII Y/I. 0 `cmpwi 0x0B00` in
  TEXT. `0x848bb1a8` is RTTI class 2 vs 11. `0x8466b660` is a map
  count vs 256, not field `0x0100`. `0x8466c7f0` is a packed LE f32
  (4×lbz, not lwbrx).
  0 lis/addi of `0x84EE65C0`. `0x84671838` is C++ vt[2] on r4+0x20,
  not a property registrar. 0B groups are tag + u8 variant + BE u16
  field + u8 (variant 0 is 3589/3621; variants 1–5 use field `0x0200`),
  not a 2-byte `0B00` tag. `0x84842f48` is RTTI class 3/4/5/6/7/11/12
  via +0x14/+4. `0x8476ca80` counts 10×5-byte slots at object +0x13D9.
  `0x8492bb24` sums 5-byte windows then uses floats.
  `0x84b0a4c0` compact-int-indexes stride-12 table `0x84EE65A8`
  (max id `0x35`) then `bctrl` get/set; 0 `cmpwi 11` in those cases.
  `0x849e7790` copies a 12-byte record (`0xffff` sentinel), not a 0B
  group. `0x847e2818` is class-id 3/5/6/7/4 via +4, not leftover leads.
  `0x84abb590` copies 5 bytes with no tag check. `0x84a9d7a0` copies
  stride-32 floats at +0x1C, not NFL table `0xB73BD0`.
  NFL `dir_ingame` (outer 4) has 1310 instruction records, all starting
  `0B`; prefixes `0B 00 01 00` / `01 01` / `01 02` — same
  tag+variant+u16 encoding as APF. `0x84be2b48` is an ASCII/scanf
  0..11 jump, not leftover leads. `0x848777cc` loads one float from
  `0x84F1A150+0x1C`, not a stride-32 bitset table. `0x84b93b10` reads
  a 5-byte header with no `0x0B` check; caller `0x84b94258` switches
  on first byte 0..4.
  Non-`0B` leftovers are concatenated typed groups: type `0x04` is
  tag + 4-byte LE float (size 5) on APF and NFL; types `0x05`/`0x06`/
  `0x07`/`0x08`/`0x09` are 1-byte tags (a following `00` is the
  terminator type, not a payload); type `0x03` is tag + u8 (size 2).
  That walk consumes APF ingame 1015/1015 and NFL ingame 1310/1310.
  `0x849277a8` switches on a presentation byte (cases 4/11 store
  floats), not those tags. `0x84c4c480` copies 1/2/4/8 bytes with
  endian swap (`cmplwi` 1/2/4/8 then `lwbrx` for width 4), not a
  type-4 float reader. `0x84ba2520` walks a stride-12 table in r4
  from a packed descriptor (`mulli` 12 + `lbz` +8), not a property
  `bctrl` registrar. `0x846c2068` compares object +0x62 to 4 then
  stores 5, not float-group size. `0x8466c890` is a float-expression
  VM (opcodes 0..12, table `0x8466c91c`, cursor `0x84F1779C`);
  case 4 is the LE f32 immediate (helper `0x8466c7f0`); case 11
  consumes 1 extra byte, not a leftover 0B group. Descriptor slot
  `0x844dd260`. `0x8477f950` switches on a UI byte 0..12 (cases
  5-10 just return). `0x84a37850` loads situation down and ytg
  together and wraps ytg at 100, not a play picker. `0x848864b0`
  compares situation word0 to 4 (not down) and playcall+0x38 to 11.
  `0x84a5eb08` indexes 24-byte tables by type 3/4/8/9/11/12, not leftover.
  `0x8475b7b0` tweens `0x84D58C70` (`lfs` +0x258, counter +0x25C), not
  situation ytg. NFL xbe has 0 `add r32,5` within 80 bytes of `cmp al, 0x0B`;
  the only `.text` sites with both `cmp al,4` and `cmp al,0x0B` within 48
  bytes are `0x1138e0` (object +0x35 enum) and killed play-type classifiers
  `0x133fd1` / `0x27e830`. `0x84a23bd0` cycles situation +0x1F8 through
  0..7 (UI play-type filter), not CPU 3rd-and-long. The only PE pointer to
  picker `0x8486ce88` is its `.pdata` row `0x844e8568` (section
  `0x844DBE00`), not a `bctrl` dispatch slot. Situation +0x1F8 setter
  `0x849d36d8` has 0 `bl` and 0 PE pointers. NFL relocator `0x000dc700`
  returns after fixing +0x14/+0x0c/+0x08 and does not walk instruction bodies.
  `0x848631d0` is the +0x1F8 getter used by the "Offensive Play calling"
  widget (`0x845FE7D4`); `0x849d36d8` remains the packed setter (0 `bl`).
  NFL `0x168ad0` walks a SHAP list at +0x14 (stride 0xC, dword==3), not leftover
  TLV. The only `lhz` +6 then `addi` 32 is relocator `0x8466a994`.
  `0x84a2ccd8` reads situation +0x1F8 and +0x2BC (word0==2, filter==0,
  tab==3), not down/ytg. The only TEXT sites with cmp 4, addi 5, and cmp 11
  together are occupancy `0x84961548` and bit-pack `0x849e3a24`, not leftover
  sizes. Picker-caller neighborhood `0x84814dcc` / `0x84816118` compares
  situation word0 to 4, not Fourth Down; the addi 5 is `srawi`-3 index math.
  `0x8485a04c` switches word0 0/1/2/3/4/9 into mode immediates. Real
  `addi r,r,5` (not `li 5`) plus cmp 4/11 is still not a leftover stream:
  `0x84869e60` is a 4-wide fill remainder and `0x84a9adcc` is an 11-slot
  `lbzx` at object+5 beside the role table. `0x84a21298` is a packed UI
  formatter (0 `bl`) that indexes the seven labels at `0x84E446C8`
  ("First Down" … "Third and Long" `0x845FD8B4` … "Fourth and Long"); every
  `lis`/`addi` of its object `0x85212B88` sits in the same `0x84a20xxx`
  widget cluster, not a CPU picker. `lbz`+`cmplwi` 9 then `bctr` at
  `0x84911750` / `0x849ecd48` switch object fields, not leftover tags.
  `0x847d7590` / `0x8480189c` compare playcall `0x851A2780+0x3C` to 3/6,
  not down. Every TEXT `lis`/`addi` of leftover cursor `0x84F1779C` /
  `0x84F177AC` sits in expr-VM `0x8466c778`–`0x8466d888`; the VM entry
  stores r5 to cursor+8 (`0x8466c8dc`). No TEXT site loads situation +0x254
  and +0x25C together and yields D&D index 4; lookalikes `0x8499e420` /
  `0x849a3b58` compare script node +0x10/+0x14. Packed get_ytg `0x84b68cd8`
  (`lwz r3, +0x25C(r3)`) has 0 `bl` and 0 PE pointers; the situation
  property blob that holds get_down `0x84ad92e0` has no +0x25C getter.
  Expr VM `0x8466c890` has only desc slot `0x844dd260` (0 inbound PE ptrs,
  0 TEXT `lis`/`addi`). 0 `lwz` +0x20 then `lbz` and cmp 4/11 leftover
  walk. `0x84879bc0` extracts ytg bit 1, not a D&D index. Packed object
  get_down `0x84b68cc8` sits next to get_ytg (0 PE ptrs). `0x84ad0348`
  copies situation +0x254/+0x258/+0x25C onto a stack blob (only PE is
  `.pdata` `0x844f72b0`); not a D&D index. 0 aligned inbound PE pointers
  into get_down blob `0x84EB0800`..`0x84EB0F00`. Other TEXT `lwz`
  +0x254/+0x25C pairs are stack slots, tween `0x8475b7b0`, status query
  `0x84b694a8`, or a non-situation object where +0x254 is a pointer
  (`0x84b39458`). TEXT `lis`/`addi` of the blob only hit row base
  `0x84EB02D0` (packed `0x84ad9f40`: `mulli` r4, 0x1C then `lwz` +4).
  get_down's row `0x84EB0DD0` is not 0x1C-aligned from that base. 0
  `addi` 32 then `lwz` 0 then `lbz` 0(record) leftover walk. 8 `lwz`
  +0x20 then `lbz` 0 sites are string/ASCII. Only TEXT `lis 0x0B00` is
  bitmask `0x848ee750` (`li r4, 11`). `0x84b64c88` walks a 4-byte window with UTF-8 extra-byte
  table `0x844C69C8` (0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0), not leftover sizes.

Which play the CPU calls on 3rd-and-long from a still-populated list remains
runtime-unproved.

A signed Xbox package now uses the same verified raw-handoff lane as Save
Players: Mod Studio verifies and extracts `Roster.ROS`, writes an independently
verified raw result, and requires external reinjection, STFS rehashing, and
resigning. It never emits or labels an unsigned result as a signed container.
This feature selects existing books; it does not change on-disc PLAY/DRCT.
Signed-STFS reinjection/rehash/resign and changed assignment gameplay
consumption remain unproved.

## Copy or swap stock player-assignment routes on disc

Open **Playbooks & Plays → Assignment Routes** after loading the game.

1. Choose a target play and one of its 11 player slots.
2. Choose a donor play and slot.
3. Use **Copy donor route to target** when the target's current chain is also
   used elsewhere. If the editor reports that the copy would orphan a chain,
   use **Swap both assignment routes** instead.
4. Save the `.apf2k8mod` project or Build a new game folder normally. Every
   staged target has a Revert row; when chain safety requires it, reverting one
   half also reverts its reciprocal swap partner. A two-way swap is one Undo
   action.

The project stores only MASTER/play/slot selectors. During Build, Mod Studio
reads the donor descriptor and chain from your recognized source, re-encodes
the target-relative pointer, and changes only the selected eight-byte
assignment fields. It reparses the fixed 0x2C750 MASTER body, preserves every
route-node byte, name, formation, exact MSB-first formation/play membership
bit, opaque membership tail, and the complete set of chain starts, then
token-preserves H7A inside fixed outer 180.

This reuses exact stock assignments. It does not decode or draw route-node
waypoint coordinates/opcodes, create new plays or formations, edit DRCT, or
claim gameplay/runtime behavior.

## Browsing and exporting everything

For the supported source, the live catalog contains 10,464 universal items:
10,394 named inner assets plus 70 non-IFF outer resources. The browser exposes
all of them, including 3,637 textures, 2,261 audio resources, 1,303 scenes,
playbook data, layouts, rosters, animation resources, and opaque records.

Exports are local copies of data from your game. A raw ZIP, XMA, WAV, texture,
scene, screenshot, or generated glTF may contain retail-derived material. Keep
those in your private workspace; they are deliberately rejected by the public
release checker and must not be placed in a shared project.

The specialized semantic views are also generated directly from the selected
game. They cover 2,254 players, 40 teams, 31 stadium identities, 1,344 roster
memberships, 3,273 mapped roster-name allocations serving 4,628 mapped
identity references, 1,572 TXT-localization references plus 2,413 underlying pool
allocations across four banks (1,294 TXT and 1,119 STRG), one playbook with 163
formations and 586 plays, five director resources with 1,623 instructions, and all 1,120
uniform selector records across 80 HOME/AWAY banks. These views do not turn
unnamed fields into editable fields; their notes preserve that boundary.

Sliders & Gameplay adds 38 searchable mapped rows: the exact 21 stock slider
names/range/order and 17 retained draft-lineage weights. They are definitions,
not the current values from a user's profile. APF's retained draft tables have
no proved live CPU selector, and no settings, executable, catch-strength, or
draft-AI writer is enabled.

## Stadium Studio

Open **Stadiums** to browse all 93 exact `stadium` SCNE records. Archive outer
and inner coordinates are shown because the 31 roster stadium names are not
yet safely joined to those 93 scene records; Mod Studio does not invent venue
names.

Selecting a scene prepares a source-hash-fenced private glTF cache from your
own game and opens the dependency-free 3D viewer:

- drag to orbit;
- Shift-drag or middle-drag to pan;
- use the wheel to zoom; and
- click a visible surface to read its glTF mesh/primitive plus retained APF
  scene-node and source-mesh identity.

**Export 3D Scene ZIP** writes `scene.gltf`, `scene.bin`, and a source-bound
manifest as one private local export. The right panel lists every record in the
same outer archive package. In the proved outer-14/inner-8 stadium, the editor
closes an exact 89-node → 84-material → 78-embedded-TXTR ownership join.
Clicking a surface lists only its owned textures. All 78 embedded textures can
be previewed/exported, replaced from PNG with target-size auto-resizing and a
complete regenerated mip chain, reverted, and built into a source-fenced copied
`1A`. The independent verifier reopens the result and checks every unrelated
byte. Other stadium scenes retain browse/export until their own ownership map
is proved; package proximity alone never grants write permission.

The exact outer-14/inner-8 stadium has a separate, bounded geometry lane. Click
one of its 77 catalog-authorized surfaces, choose **Export selected mesh**, edit
only vertex POSITION values, apply object transforms, and export the same
vertex count and triangles. **Import edited mesh** authenticates the private
source reference, rejects changed topology, transforms, materials, skins and
extra attributes, then creates a new folder containing a copied `1A` and
hash-only manifest only after independent full-volume verification. Original
UVs, normals, materials, attachments and every unrelated game byte are
preserved. This is not a changed-topology or runtime-visibility claim.

The earlier same-package and Wine-breakpoint experiments remain useful history,
but the current serialized-node/material/TXTR join supersedes their unresolved
inventory boundary for this one stadium. Runtime visibility, other stadium
scenes, arbitrary material reassignment, changed topology, UV editing, collision,
and allocation growth are still explicit boundaries.

## Field Art map

Open **Field Art** for a semantic view over all 258 records already routed to
that category. The header shows seven families across 125 archive packages:

| Family | Records | What the name/package evidence supports |
| --- | ---: | --- |
| Endzone textures | 235 | 117 package-local `l0`/`l1` pairs plus one `l0`-only record; the level meaning and selector are not proved. |
| Field scenes | 4 | Four `field` SCNE resources; no team, stadium, or rendered-instance owner is assigned. |
| Field radiance textures | 4 | One `field_radiance` TXTR beside each field scene; co-location is not shader/material ownership. |
| Divot & weather textures | 6 | Three `divots` plus named GrassRain, GrassSnow, and GrassDry resources. |
| Practice & field overlays | 3 | Field-goal, passing, and stride-named overlays grouped for discovery. |
| Practice-related scenes | 4 | Divot, field-pass, and football-field-named SCNE rows with no invented mode owner. |
| Penalty animation curves | 2 | Name-matched CurveAnim rows, explicitly identified as animation rather than field textures. |

Search by name, choose a family, inspect the source package, and use the
existing PNG/scene/raw export offered for that asset. An export comes from the
user's game and stays private. The Field Art editor writes the original six
bases (`endzone_l0`, `endzone_l1`, `pc_field_goal`, `Field_Pass_text`,
`Stride_number_field`, `divots`), the 21 package-659 weave/dirtmaps (ten
64×64 8_8_8_8 weaves, two 256×256 BC3 `weave_skin_weights_*`, nine BC3
dirtmaps), and 196 format-18 DXT1 endzone layers (118 `l0` + 78 `l1`).
Import auto-resizes to the target dimensions, regenerates the required
encoded payload, stages a source-fenced copied `0A`, and fails closed if
the fixed allocation cannot be preserved. Thirty-nine format-59 DXT5A
`endzone_l1` layers, `field_radiance`, the `divot_Grass*` weather textures,
and the SCNE/CurveAnim rows stay inspect/export-only. In-game look is not
proved.

### Finding one team's endzone

Every endzone package is **one team's own artwork**. Package 6 is not a
shared layer; it is structurally identical to the other format-18 packages
and was simply the pair whose writer was proved first. Editing any writable
endzone slot repaints that one team's layer. (Earlier builds described
outer 6 as shared. That was wrong.) Format-59 `endzone_l1` packages are
not offered.

You cannot find a team's endzone by searching. The nicknames are not on the
disc: a name like `Redcoats` appears zero times in `0A`, `0B`, `1A`, `1B` and
`default.xex` across ASCII, UTF-16BE and UTF-16LE — it lives only in
`Roster.ROS`. Use **Export endzone contact sheet…** in the Field Art header. It
renders all 118 packages into labelled sheets so you can identify a package by
its artwork; 31 are already named and show their team on the tile. Note the
package number and open it under **All Textures**.

Endzone layers are **region masks, not artwork**: pure red / green / blue region
selectors over black, 2048×512 DXT1, with alpha uniformly opaque. The colours
you see in game are shader-driven. Author them like the uniform masks — flat
colours, hard edges, no anti-aliasing — because an intermediate value is an
invalid region ID rather than a blend.

Use **Export decoded rows** in any specialized inspector to save all rows
matching the current search and kind filter. JSON preserves nested decoded
fields; CSV includes identity columns plus a `fields_json` column so no nested
information is silently discarded. These local exports may contain
retail-derived names or metadata from your game and therefore do not belong in
the public application or a shareable `.apf2k8mod` project.

## Editing menu and mode text

Open **Menus & Text**. The upper browser begins with **Localization Pool
String** and **String Bank Pool String** rows—the underlying shared TXT/STRG
allocations the game actually stores. TXT reference rows remain available for
text-ID ownership/context, but they are not edited independently. STRG rows
show the exact aggregate consumer count without inventing a menu label for an
unowned numeric ID.

This is a real **Editable** capability, not a Coming Soon research card. The
alpha.13 action binding points directly to the in-place text editor; it does
not require or advertise a made-up file-extension import route. Of the 2,413
decoded allocations, 2,410 retain Apply/Revert under their displayed limit and
the three structural exceptions remain read-only as described below.

The end-to-end runtime spot check changed one ordinary TXT allocation from
`Artist Biography` to `MOD BIOGRAPHY`; Xenia displayed that exact new header
on the 2K Beats biography page while the body and portrait stayed intact. That
proves the writer/build/runtime path for the recorded allocation, not that all
other strings have known screen ownership. Use each row's bank, coordinates,
reference count, and displayed limit instead of assuming a label's destination.

For an editable pool row:

1. Search or use the record-kind filter to select the allocation.
2. Read its UTF-16 limit and shared-reference count. If six references use one
   allocation, one edit intentionally changes all six.
3. Enter replacement text and choose **Apply Text**. Most ordinary characters
   use one UTF-16 unit; a non-BMP symbol may use two. Embedded NUL characters
   are refused.
4. Use **Revert Text** to restore only that allocation, or the footer's
   **Revert All** to clear the project.

For a large translation, historical-name cleanup, or menu rewrite, use the
two **Text Sheet** buttons instead of editing one row at a time:

1. Choose **Export Text Sheet**. Mod Studio creates a new UTF-8 CSV containing
   all 2,413 owned TXT/STRG allocations, their exact limits and coordinates,
   the source fingerprint, original text, and any currently staged replacement.
2. Keep that CSV private. It necessarily contains strings exported from your
   own game and is not a shareable `.apf2k8mod` project.
3. In LibreOffice or another spreadsheet editor, change only `action` and
   `replacement_text`. Keep the leading apostrophe in every text cell; it is a
   deliberate formula-safety marker. Actions are `auto`, `replace`, `revert`,
   or `skip`.
4. Choose **Import Text Sheet**. Mod Studio verifies every row, source hash,
   target coordinate, original string, editable flag, and UTF-16 allocation
   limit before staging anything. A late invalid row rejects the whole sheet.
5. A valid sheet applies all replacements and reverts as one Undo action. Only
   authored replacement text enters the normal retail-free project/recovery
   path; unchanged source strings from the private CSV do not.

There are 2,413 underlying allocations across all four decoded English text
banks. The two `INVALID TEXT` fallbacks and one zero-capacity empty STRG
allocation are structurally required and stay read-only; the other 2,410 accept
replacement under their displayed limit. Layout geometry and seven labels
stored directly in the executable are separate read-only structures.

## Audio browsing, waveforms, and export

Audio browsing includes both storage systems:

- all 2,261 ordinary `AUDO` resources; and
- all 45,514 addressable substreams inside 20 `AUSB` banks, backed by 19
  external packet resources.

Those 45,514 semantic AUSB rows resolve to 45,513 canonical physical ranges.
The difference is one shared `cwdloop` range with two semantic owners; it is not
an inventory error.

Those 19 physical resources now appear by their source-owned `.bin` names,
including `jukeboxmusic.bin`, `jukebox22.bin`, `lines.bin`, `players.bin`, and
`teams.bin`. Select one **External Bank** row and choose **Export original bank
.bin** for an exact local copy. A physical bank is a multi-cue packet container,
not one sound: Play, shortlist, and Replace stay disabled on that row; use its
linked AUSB substream rows for per-sound playback/export.

In alpha.13, choosing an External Bank row hides the single-sound Play control
and changes the shortlist prompt to **Choose a sound
to shortlist**. The technical detail pane also keeps a larger minimum width and
height so long bank ownership and archive coordinates remain readable. These
are presentation changes only: exact bank export still works, and the bank does
not become a playable or replaceable cue.

The Audio table exposes ordinary columns for role, format/sample rate/channels,
length, archive location, and current action. Its separate filter row combines
record kind, broad role, and an exact **Audio source / bank** selector. Choose
**Standalone AUDO** or one named AUSB bank to explore it without knowing a
search term first. Every bank label includes its outer/inner archive coordinates,
so two banks with the same name remain separate. The number beside each source
counts playable sounds; selecting a bank also keeps its one descriptive bank row
visible. Exact source-owned AUSB bank names support broad labels such as
**Soundtrack & Music**, **Commentary & Speech**, and **Stadium PA & Chants**.
Standalone AUDO labels are deliberately broad name heuristics; the detail pane
says that exact cue routing is not proved, and unknown sounds remain in
**General / Unknown SFX**. A role label never makes an asset editable.

The two jukebox banks contain 15 entries each. Mod Studio pairs their matching
indices/durations as **Soundtrack Track 01** through **Soundtrack Track 15**:
`jukeboxmusic` is the 48 kHz stereo form, and `jukebox22` is its 22.05 kHz mono
companion. The game does not provide safely owned artist/title metadata here,
so the app does not guess song names.

Choose **Soundtrack album (15)** to open those bank-indexed pairs as a focused
album. It always starts on the 15 `jukeboxmusic` stereo masters; the adjacent
selector exposes the 15 `jukebox22` mono companions while keeping the same
track number selected. **Back to all audio** restores the prior search, kind,
role, source/bank, page, and selection. The album appears only when the exact
15-by-15 source pair, indices, channel/rate layouts, export identities, and
matching durations are present. “Track 01” is an owned index label—not a song
title—and artist/title remain **Unknown** rather than guessed.

Every playable audio row carries an exact export identity:

- **Load waveform** explicitly decodes or reuses this one sound's verified
  session-private PCM16 WAV and draws a bounded waveform without playing it.
  Selecting a row does not start decoding. Changing the selected row or source
  cancels an in-flight request; while it is decoding, **Cancel waveform** does
  the same directly. Cancellation stops the owned decoder process group,
  discards partial private output, and returns this row to a retryable state.
  A failed decode leaves a retryable explanation. AUSB index rows and physical
  banks never offer this action.
- **Play** creates a decoder-verified PCM WAV inside the current private
  loaded-game session and starts `ffplay`, `paplay`, or `aplay` without a shell.
  During preparation the button becomes **Cancel preview**; afterward **Stop**
  ends playback. The WAV is not added to a project, and the whole preview
  directory is removed when the source is closed or replaced. Preview
  preparation belongs to the selected row; selecting another sound stops the
  owned decoder and makes a late success or failure inert. A current
  preparation failure restores **Play** so the sound can be retried.
- **Export this sound** writes the selected original XMA1 payload or a WAV. WAV
  publishes only after the local decoder verifies the complete result. If a
  sound does not decode, export its exact `.xma` instead.
- **Export complete bank** is available for a complete AUSB bank containing
  1–256 sounds, including both 15-track soundtrack banks. Original XMA1 is the
  safe default. Verified-WAV mode is all-or-nothing: one failed decode leaves no
  partial ZIP at the chosen destination.
- **Export matching sounds** packages the 1–256 playable rows matching the
  current search, kind, role, and source/bank filters. Selecting
  `jukeboxmusic` immediately produces an exact 15-track full-stereo selection;
  `jukebox22` produces its 15 mono companions. This is also the practical route for a
  bounded slice of the much larger `lines`, `players`, or `teams` commentary
  banks. The ZIP may mix ordinary AUDO and AUSB substreams, includes a metadata
  manifest, defaults to original XMA1, and keeps verified-WAV export
  all-or-nothing. If more than 256 sounds match, narrow the filters first.
- **Audio shortlist** is for sounds that do not share one convenient filter.
  Choose **Add selected sound** while browsing, or **Add this page** for the
  playable rows currently visible. The ordered shortlist follows you across
  searches, pages, roles, and banks; selected rows receive a visible badge.
  Choose **Review selected** to see only that exact insertion order, page
  through as many as 256 choices, play or export a row, remove mistakes, and
  use **Move up**/**Move down** to set the final bundle/playlist order. **Back
  to audio browser** restores the prior filters, page, and selection. Removing
  the last row, clearing the list, or loading a different model exits Review
  cleanly. **Clear** keeps one session-only snapshot and becomes **Undo**;
  choose it again to restore the exact prior order without reopening Review.
  The snapshot expires after the next real shortlist change or loaded-game
  change.
  **Export selected sounds** packages up to 256 hand-picked rows through the
  same transactional original-XMA1 or verified-WAV route. The shortlist is
  session-only, contains no audio bytes, never enters a shareable project, and
  clears when the loaded game changes.
- Search, kind, role, and source/bank controls apply after a short typing delay.
  While **Updating audio results…** is shown, Add-this-page, pagination,
  filtered export, decoded-row export, and replacement-template actions wait
  for the displayed table to catch up. Play, individual Export/Replace/Revert,
  and Add/Remove-selected still target the exact visible row and remain safe.
- **Export complete audio catalog…** accounts for all 47,814 semantic rows in
  one new atomically published ZIP. Choose original `.xma` or decoder-verified
  `.wav` in the save dialog.
  The 2,261 standalone sounds and 45,514 addressed substreams go through the
  existing single-sound exporter. The manifest records the 20 AUSB index rows
  and 19 physical-bank rows as unsupported because neither is one playable
  cue. Its `catalog.csv` gives every requested row an ordered, searchable line
  with status, role, source/bank, format, rate, channels, duration, coordinates,
  output path, and exact size/hash where a payload succeeded. An ordered
  `playlist.m3u8` contains successful sounds only. Per-sound failures continue
  to later rows; cancellation produces a fully accounted partial export rather
  than an unexplained archive. This may be a very large, long-running private
  export; it never changes the loaded project or unlocks replacement.
- **Export all original banks (19)…** separately copies every physical XMA1
  `.bin`, including both soundtrack containers, into one new private ZIP. Its
  manifest records each exact payload SHA-256/size/name ID and every owning
  AUSB descriptor/role. These are raw multi-cue containers, so this action does
  not make them playable or replaceable. Use **Cancel audio export** to stop
  either bulk route after the current complete sound or bank; the partial
  manifest accounts for everything skipped and no member is cut in half.

Every complete-bank, matching-sounds, shortlist, and successful complete-
catalog ZIP includes an ordered `playlist.m3u8` beside `manifest.json`. Open
that playlist in a compatible media
player to hear the exported sounds in the same order shown or arranged in Mod
Studio. The manifest records the playlist name and exact entry count; durations
are included when the bank metadata owns them. A playlist points only to files
inside that local ZIP—it is not stored in an `.apf2k8mod` project. Original
XMA1 playback still depends on player support; choose verified WAV for the
broadest compatibility. Raw physical banks and AUSB index rows never enter a
playlist because neither is one addressed sound.

These are private exports from the user's own copy, not files that belong in a
release or shareable project. Preview safety also fails closed if a session WAV
is replaced, tampered with, or redirected through a symlink.

### Name and document cues without changing the game

Alpha.34 gives each of the **47,775 playable cues** a project-backed discovery
record. This includes all 2,261 standalone AUDO rows and all 45,514 individual
AUSB substreams. It excludes the 20 AUSB index rows and 19 physical-bank rows,
because those are containers rather than single sounds.

1. Select one playable sound in **Audio** and listen to it with **Play**, inspect
   its waveform, or export it for private review.
2. In **Your cue label & notes**, enter a custom title of up to 120 characters,
   a multiline note of up to 2,000 characters, or both. Good notes record what
   you heard, where it triggered, and what you may want to replace later.
3. Choose **Save label**. The custom title appears without replacing the
   preserved game/catalog name or stable logical cue ID.
4. Search for words in either the original catalog metadata, custom title, or
   note. Turn on **Labeled only** to show only cues documented in this project.
5. Choose **Clear** to remove the selected annotation. Ordinary Undo and Revert
   All include annotation changes alongside the rest of the project.

Annotations are metadata, not audio edits. They never receive a Modified badge,
never enable Build by themselves, and never enter the composed game output. An
annotation-only project is still useful: **Save Project** creates a shareable
`.apf2k8mod` containing the checksum/size/count-bound `audio-annotations.json`
document and project metadata, but no game audio, decoded PCM, source path,
preimage, rollback byte, or replacement packet. Opening that project restores
the labels and notes against the same recognized APF source revision.

Matching-sound and shortlist collection exports carry the custom title, note,
and preserved game/catalog name in their local metadata. Their playlist uses
the custom title when present, while the stable cue ID and payload path stay
unchanged. This makes a listening/research project portable without pretending
that a guessed title came from the game.

In Alpha.22, selecting a **Standalone AUDO** row exposes **Replace with XMA1…**
and **Revert sound**. Alpha.23 exposes the same controls for every
individual **AUSB substream** row. Physical External Bank and AUSB index rows
remain containers, not individual sounds, so author through their linked
substream rows. Alpha.33 also exposes **Drop .xma or audio file here** for
those same editable rows; it is a shortcut into the existing routes, not a new
format or a weaker validator. The exact-slot editor is deliberately narrow:

1. For **Replace with XMA1…**, supply an already encoded, one-stream RIFF XMA1
   `.xma` file. That direct-XMA action rejects WAV, FLAC, MP3, WMA, xWMA, and
   XMA2. For one exact-shape PCM16 WAV instead, use Alpha.27's separate
   **Replace from PCM WAV…** action and a user-configured external encoder.
2. Match the exact channel count, sample rate, and encoded-byte requirement
   shown in the selected row's detail panel. Encoded length cannot grow or
   shrink.
3. Mod Studio validates the RIFF structure, every `0x800`-byte packet, and a
   complete FFmpeg decode. The decoded duration must match the target within
   the bounded XMA packet-tail tolerance. PCM/external-encoder submissions must
   first decode back and pass the alignment-aware authored-signal artifact gate;
   direct pre-encoded XMA has no PCM reference and remains byte-preserved.
4. A successful import receives a modified badge and participates in Undo,
   individual Revert, project save/load, private preview, and Build like other
   typed edits.

### Batch exact-slot replacement folders and ZIPs

Alpha.28 supports two retail-free batch contracts: legacy pre-encoded XMA1
(`v1`) and exact PCM16 WAV plus a user-configured encoder (`v2`). Both can stage
many independently authored sounds without repeating the file picker for every
row:

1. In **Audio**, narrow the search, kind, role, and source filters to the sounds
   you want. For a hand-picked set, add sounds to the shortlist and enter
   **Review selected**.
2. Choose **Pre-encoded XMA1** or **Exact PCM16 WAV**, then choose **Editable
   folder** for normal local editing or **ZIP hand-off** for one archive. Choose
   **Create replacement template…**. In the ordinary browser, the template
   covers every playable row matching the current filters; shortlist Review
   preserves the exact reviewed order. Either template may list up to all
   47,775 editable AUDO and AUSB rows. Existing paths are never overwritten.
3. Open `replacement-pack.json` and add only listed payloads:
   - v1: put pre-encoded, one-stream RIFF XMA1 files under `xma1/`;
   - v2: put signed little-endian PCM16 RIFF WAVs under `pcm16/`, preserving
     each target's exact channels, sample rate, and frame count.
   Leave every target you do not want to change absent. A v2 template may list
   more, but one import accepts at most 256 supplied WAVs. For a ZIP, keep
   `replacement-pack.json`, `README.md`, and the generated payload folder at
   its root—do not add a wrapper folder. Do not rename listed files, mix the two
   payload types, or add an unlisted payload. Folder import refuses entry 257
   before opening or hashing any WAV byte; ZIP import applies the same ceiling
   before extracting payload members.
4. Choose **Review replacement folder…** or **Review replacement ZIP…** and
   select the pack. Review detects v1 or v2 from the exact schema and input
   contract; the export selector does not need to match. A v1 pack needs no
   encoder. A v2 pack requires **Configure XMA1 encoder…** first. Mod Studio
   checks the complete manifest against the exact loaded source,
   including every coordinate, slot shape, AUSB alias owner, and the selected
   targets' replacement-only project state when the template was created. For
   v2, it privately copies and encodes each WAV. Every resulting file then runs
   through the normal allocation, packet, full-decode, duration, target, and
   cross-family source-packet rejection checks. **Cancel pack check** can
   interrupt the owned encoder or stop at a safe file boundary.
5. Read the fully validated count preview, including **Would change** and
   **Modified audio after Apply**. If **Would change** is zero, Apply is
   unavailable and no state changes. Otherwise choose **Cancel** to leave the
   project untouched, or explicitly choose **Apply**. Apply reopens and
   revalidates the pack, verifies its opaque source/session/project/member
   binding, and only then stages the real changes as one Undo action. Missing
   files are reported as skipped. If any row or file
   is unknown, repeated, unsafe, invalid, wrong-source, wrong-shape, or conflicts
   with another alias owner, no active project edit changes. A folder or ZIP
   containing only replacements that are already staged remains a read-only
   no-op with Apply disabled.

If a supplied sound or any linked AUSB alias owner changed after you created
the pack, import stops before validation and asks you to export a fresh
template. Edits elsewhere in the project do not make the pack stale. Keep the
generated `README.md` and `replacement-pack.json` unchanged; Mod Studio accepts
only the exact, bounded contract files it generated. Alpha.25 template folders
remain compatible, and Alpha.26/27 v1 ZIP bytes and README stay unchanged.

Cancelling changes no project edit and adds no Undo action. Any new private
packet cache prepared for this cancelled attempt is discarded only when no
active edit or Undo snapshot references it.

The generated template is retail-free: it contains no original audio,
source-owned sound names, descriptors, physical pack offsets, or rollback
bytes. It does contain the loaded-source SHA-256 and bounded semantic metadata
needed to prevent applying it to the wrong revision or overwriting a newer edit
to the same sound. The baseline records only original/modified state, typed
writer kind, and the hash of a user-authored replacement—never private paths or
replacement bytes. Once you add authored files, those XMA1 or PCM16 WAV files
are the only audio payloads in the folder or ZIP. Folder mode is easiest to
fill; ZIP mode is easiest to move or hand off. ZIP import accepts normal stored
or deflated, unencrypted archives and rejects unsafe paths, duplicate/case-
colliding names, symlinks, special entries, wrapper folders, unknown files,
and oversized expansion. Mod Studio copies each v2 WAV to a private pinned
input before the external process sees it and removes temporary inputs/outputs
after success or failure. FLAC/MP3, floating-point WAV, XMA2, mixed v1/v2
payloads, and more than 256 supplied WAVs per import are unsupported. Renaming
audio to `.wav` or `.xma` never converts it.

An `.apf2k8mod` stores only the canonical raw packets supplied by the modder and
small target-shape metadata. It stores no original audio, retail rollback
payload, RIFF wrapper, physical source coordinate, source-payload fingerprint,
or retail loop metadata. Alpha.23 builds a complete fingerprint inventory of
every `0x800`-byte source packet in both the 2,261 standalone AUDO slots and all
45,513 canonical AUSB ranges. Session import, project load, modified preview,
and Build each reject a replacement containing even one complete source packet
from either family. This blocks same-family reuse, cross-family AUDO/AUSB
transplants, and retail packets hidden inside otherwise changed payloads. The
40,316 unique whole-AUSB-payload hashes are an inventory fact, not the sole
protection mechanism.

The bounded real-source Build check matters: it rejected an 8-bit-mutated Track
12 near-retail candidate at replacement packet 0 even though that candidate had
passed the older whole-payload-only gate. The scan covered both source audio
families and completed in 14.13 seconds with 208,896 KiB peak RSS. No private
candidate data is stored in the project or these docs.

The standalone AUDO result is **offline-writer-proved; runtime partial and
boot-compatible, with audible cue consumption inconclusive**. The matched
candidate/control recordings did not justify claiming that the authored cue
was heard. Read the full
[exact-slot XMA1 contract](../product/APF_AUDO_EXACT_SLOT_XMA1_EDITOR.md) before
authoring or sharing a project.

For AUSB, the writer preserves every descriptor byte and replaces only the
selected existing packet allocation. Exactly one physical range has two owners:
both `cwdloop` rows disclose the shared effect. Editing either changes both;
byte-identical edits through both aliases deduplicate, while different edits to
the same bytes are rejected. Exactly one allocation—stereo Soundtrack Track
03—crosses from the end of `0A` into `0B`; Build splits it into two independently
source-guarded spans and publishes the complete game folder atomically. The
other 45,512 physical ranges occupy one pack span each.

The source soundtrack decoder sweep is a compatibility warning, not a smaller
editor count: FFmpeg 6.1.1 decoded 18 of the 30 original stereo/mono soundtrack
sides and rejected 12 otherwise packet-valid retail inputs. All 45,514 rows are
addressable, but every new replacement must decode cleanly and match its target
within the packet-tail tolerance. Alpha.28 can hand one selected WAV or up to
256 supplied exact-shape PCM16 pack WAVs to a separately installed encoder.
Mod Studio ships no encoder and real-tool compatibility remains unproved.
Selected-sound FLAC/MP3/OGG/M4A input is conformed through FFmpeg; those formats
remain unsupported in the bounded folder/ZIP batch route.

The private Alpha.23 candidate booted, selected **Track 12 — Bury Me Standing
Remix**, and visibly remained in playback for 25 seconds without crashing.
The completed objective capture experiment was negative/inconclusive: its final
sustained segment matched neither the mutated candidate nor stock Track 12, with
a best 17-second absolute normalized cross-correlation of about `0.031` and no
meaningful winner in candidate-versus-stock distinguishing frames. A
self-control confirmed the classifier could distinguish the known inputs. Treat
this as positive boot/selection/stability evidence only; it proves neither
authored replacement consumption nor stock fallback. The runtime status remains
partial. Before another replay, use a wholly independently encoded,
unmistakable replacement when a usable XMA1 encoder exists, or trace the
mixer/routing path.
Read the full
[AUSB exact-slot feasibility and authoring contract](../product/APF_AUSB_EXACT_SLOT_FEASIBILITY.md)
for the physical-range, alias, decoder, and runtime evidence details.

Across the alpha.13 interface, disabled primary, secondary, utility, Build,
and Launch controls use explicit disabled styling. A disabled orange button in
the sealed alpha.12 visual receipt was a styling defect, not an unlocked
writer; alpha.13 renders locked actions unambiguously gray.

## Projects, originals, and safe builds

Projects behave like ordinary named documents:

- `Untitled* — APF 2K8 Mod Studio` means the current edits have never been
  given a project filename.
- An asterisk after a named `.apf2k8mod` file means the document differs from
  its last successful save or load. A clean named title has no asterisk.
- **Save Project** in the header or File menu and `Ctrl+S` all use the same
  command. First Save opens Save As; later saves update the exact remembered
  project without another filename dialog.
- **Save Project As** (`Ctrl+Shift+S`) gives the edit set a new filename. It is
  also available for a clean named project when you want to make a copy.
- Dirty state is separate from edit count. Reverting the final replacement can
  show `0 edits • unsaved`; saving then writes a valid replacement-only project
  with an empty edit list rather than silently forgetting that change.
- Loading another source or project, and closing the app, offers
  **Save Project**, **Discard Changes**, or **Cancel** whenever the active
  document is dirty. A failed switch keeps the current document and its state.

Fast-save refuses a remembered target if it disappeared, became a symlink or
other non-regular file, gained another hardlink, was substituted at the same
pathname, or changed outside Mod Studio. The foreign file is preserved; use
Save Project As or reopen the intended project. Project opening likewise
checks that the same file remains in place throughout validation before it
replaces the active session.

The File menu now has **Open Recent Game**, **Open Recent Project**, and
**Recover Unsaved Edits**. Recent games may be either your original ISO/XISO or
an extracted game folder. Mod Studio remembers the path you selected, not its
private extraction cache. Missing recent paths stay visible but disabled so the
tooltip can tell you exactly what moved; recent projects remain disabled until
an APF source is loaded.

Every authored change also creates a private crash-recovery snapshot. This is a
normal replacement-only `.apf2k8mod` bound to both the exact selected source
path and its recognized `0A` SHA-256. It can contain an empty replacement list
when Revert All itself is the unsaved change. It never contains an ISO, XEX,
original pixels, original audio, preimages, or extracted retail resources.

After an interrupted session, startup offers:

- **Recover Edits** — load the matching source, validate the recovery, and open
  it as an unnamed dirty document. Use Save Project to choose a shareable name.
- **Not Now** — leave the recovery untouched for a later launch.
- **Discard Recovery** — remove only that private recovery snapshot.

If the original source moved, choose **Recover Unsaved Edits** after putting the
same legally dumped ISO or extracted folder back at the path shown by the app.
A failed load or canceled save leaves both the current dirty document and the
recovery intact. Saving or explicitly discarding a document clears only the
recovery bound to that same source; a postponed recovery from another source is
not overwritten.

A `.apf2k8mod` project contains only:

- a small JSON manifest;
- the user's replacement PNGs, canonical text/rating JSON, and—only for a
  current-source standalone AUDO or addressed AUSB exact-slot edit—canonical
  user-supplied XMA1 packet payload; and
- stable target IDs, dimensions, and hashes needed to apply those replacements.

It contains no original source pixels or source audio bytes, preimages, archive
entries, XEX data, or game volumes. The app resolves originals from the
selected source so every edit can be reverted without embedding those originals
in the shareable project. Exact source-payload and packet gates cannot determine
the copyright or license of independently re-encoded PCM; mod authors remain
responsible for every replacement they use or share.
Project metadata is limited to the small typed coordinates needed to identify
each supported target. Opaque arrays, duplicate targets, duplicate archive
members, symlinks, and conflicting cache payloads are refused.

Builds follow four safety rules:

1. The selected source is opened read-only and rechecked before the build.
2. A new complete game folder is assembled in a temporary sibling directory.
3. Changed fixed allocations are compiled and verified before publication.
   Cross-volume AUSB edits source-guard and verify every physical pack span.
4. The finished directory is published atomically. A failure removes staging
   and can never leave a half-built destination pretending to be complete.

If the operating system or destination filesystem cannot provide an atomic
"publish without replacing" directory operation, the app refuses the build.
Move the destination to a normal local Linux filesystem and try again; the app
will not substitute an overwrite-prone fallback.

Choose a destination that does not already exist. The app refuses to overwrite
an older build or the source folder.

## Headless and non-interfering work

Source validation, indexing, exports, project operations, and builds do not
need an emulator or control of the desktop pointer. Automated Xenia checks can
also be isolated on a separate virtual display, but that is a test-operator
setup rather than a requirement for ordinary editing. The app must never bind
automation to the user's active display merely to index or build a project.

## If something is rejected

- **Wrong revision or incomplete game** — reload the untouched USA dump with
  all six extracted boot files present. Do not select a previously modded `0A`.
- **Wrong PNG dimensions or mode** — export the original template again, keep
  it RGBA, and do not resize the canvas.
- **Pants alpha error** — flatten to fully opaque alpha.
- **Helmet channel error** — clear blue to 0 and set alpha to 255 everywhere.
- **digital_font RGB error** — make RGB solid white and author only alpha.
- **Direct XMA1 replacement rejected** — confirm the selected row is a
  standalone `AUDO` or individual `AUSB substream`, use a one-stream RIFF XMA1
  file rather than WAV/FLAC/WMA/XMA2, and match the exact channels, sample rate,
  encoded-byte count, and decoded duration shown by the app. A source-derived
  exact payload or packet is intentionally refused even when its format fits.
  For exact-shape PCM16 WAV, use **Replace from PCM WAV…** and the separately
  configured encoder route.
- **PCM16 replacement pack rejected** — configure the external encoder, keep
  each WAV at its listed `pcm16/` path and exact channel/rate/frame shape, and
  split an authored set larger than 256 supplied WAVs into multiple fresh
  imports. Do not put XMA1, FLAC, MP3, or unlisted files in a v2 pack.
- **Destination exists** — choose a new folder. Existing builds are never
  overwritten automatically.
- **Atomic publication unavailable** — build to a normal local Linux filesystem
  that supports atomic no-replace directory publication.
- **An export has no PNG preview** — use its raw local export. The texture codec
  is inventoried but not yet decoded for preview.

## Privacy and distribution rule

The installed tool includes exact reviewed Linux and Windows `extract-xiso`
executables with their license, plus the exact reviewed Linux x86-64
minimum-cost H7A helper used for tight fixed-allocation rebuilds. These files
contain no game data and are independently size/hash-pinned by both release
gates. Users supply their own dump, and all derived game content remains
outside the public application tree. Xenia is the supported emulator target;
original Xbox 360 hardware is untested.

The minimum-cost H7A helper is currently a Linux x86-64 release component. On
Windows and macOS the same writers keep the verified greedy encoder and refuse
an edit when that stream cannot fit its fixed retail allocation; they do not
publish an oversized fallback.

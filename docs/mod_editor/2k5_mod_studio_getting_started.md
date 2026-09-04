# 2K5 Mod Studio v1.0 RC81 — Getting Started

2K5 Mod Studio lets you modify your own legally dumped USA Xbox copy of
**ESPN NFL 2K5** without using a hex editor. Think of the source XISO as the
master copy: the app reads it, remembers your edits in a separate project, and
creates a new modded copy when you click Build. It never writes changes into
the master.

RC60 accepts validated USA retail ISO layouts without treating harmless wrapper
padding or partition placement as different game content. Stadium Studio,
visual and Crib originals, and private audio safety data share the same
independently verified cache. The app still guards the exact file you selected
for read-only scans, recovery, and Build, and a built copy keeps that source
container's actual size.

Community: questions, bug reports and shared patches live on the Discord,
https://discord.gg/dpMJCnJZD (also under Help > Join the Discord… in both studios).

## Before you begin

You need:

- an unmodified USA NFL 2K5 Xbox XISO dumped from your own disc;
- PNG editing software such as GIMP, Krita, or Photoshop;
- free disk space for a second full XISO; and
- xemu if you want to launch a build directly from the app.

No terminal knowledge is required. Every release-candidate package is assembled
from an exact file-by-file allowlist and must pass the retail-free gate before it
is published; the gate reports the package's final file and byte counts and
refuses retail game bytes. The app creates private indexes, previews, and
originals from your XISO on your computer; do not share that private cache.

## Make your first edit

1. Open **2K5 Mod Studio** from the desktop application menu.
2. Click **Load XISO** and choose your untouched USA NFL 2K5 XISO.
3. Wait while the app creates its private local index. This reads the game but
   does not change it.
4. Choose a category from the left sidebar. **Uniforms & Equipment** is the
   easiest place to start.
5. Search for an asset and select it to see its preview, dimensions, product
   status, and ownership notes.
6. Click **Export PNG** (or the matching Export button for text/audio). Start
   from that exported template whenever possible.
7. Edit the exported file. For an image, keep its exact canvas size and expected
   color/alpha layout. For audio, keep the exact channel count, sample rate, and
   frame count shown by the app. For text, stay under the displayed allocation
   limit.
8. Click **Replace** and choose your edited file. Dragging a PNG onto a supported
   image preview also works. A **Modified** badge means the replacement is
   staged in your project but has not touched the source XISO.
9. Repeat for any other assets. Use **Undo**, **Revert**, or **Revert All** if
   you change your mind.
10. Click **Save** to name your first shareable `.2k5mod` project. It contains
    your replacement files and logical edit metadata, never original game
    assets. After that, **Save** / **Ctrl+S** updates that named project directly;
    use **File → Save Project As…** to make a separately named copy.
11. Click **Build Modded ISO**, choose a new filename, and wait for the success
    message. The output is published only after the internal build check passes.
12. Click **Launch in xemu** if xemu is configured, or select the newly built
    XISO from xemu yourself.

### Keep a high-resolution texture master

In **Portraits & Faces**, **Create-a-Team Field Art**, **Scorebug
Presentation**, and **All Textures**, an external image import enables **Save
high-resolution authoring master…**. Choose 4x (recommended) or 2x and a new
`.2ktexmaster` filename. The editor never overwrites an existing master.

The sidecar keeps your exact original file, the exact staged native PNG, and
the resize/crop transform. Its high-resolution PNG is rendered from your
original, not enlarged from the Xbox texture. If you then use **Edit…**, the
original stays in the bundle and changed native pixels are recorded as an
explicit edit layer. The game build still uses the catalog's native size.

Current `.2k5mod` projects do not embed full-resolution sources. Save the
sidecar before switching sources or projects. Uniform Sets, Team Kit, Stadium,
and other specialist panels do not offer this action until their controllers
retain the same exact source/transform evidence. This sidecar is not an RPCS3
or xemu texture pack.

## Keyboard access and readable layout

You can move between the two parts of the interface used most often without
reaching for the mouse:

- Press **Ctrl+F** from any workspace to focus that page's search box. Existing
  search text is selected, so typing immediately starts a new query. If the
  current page has no search box, the status area tells you to use **Ctrl+1**.
- Press **Ctrl+1** to focus the left **Modding categories** list. Use the Up and
  Down arrow keys to move through Getting Started and all 11 workspaces.
- A bright focus outline marks the focused category list, asset list, or
  component tree. This is the keyboard equivalent of seeing where the mouse
  pointer is before clicking.

The category sidebar, current-operation status, progress bar, build control,
and xemu launch control include concise labels and instructions for assistive
software. The header and footer can expand for larger desktop fonts instead of
forcing every label into one fixed-height strip. Category rows and primary
controls also use roomier spacing and padding for easier scanning and targeting.
At unusually large system scaling, maximize the window to give asset details
and previews the most usable room.

## Edit a Supported Team Kit

The **Supported Team Kit** panel in **Uniforms & Equipment** moves all 39 parts
with proved writers between Mod Studio and GIMP without making you export and
import them one at a time. The existing per-component **Export PNG**,
**Replace**, and **Revert** buttons remain available when you only need one
small change.

1. Select a physical uniform set in the left list. Use Ctrl-click or
   Shift-click if you want several unrelated physical sets.
2. Choose the scope:

   - **Selected physical set(s)** exports exactly the highlighted set rows;
   - **HOME kit** or **AWAY kit** resolves that side for the selected team's
     style/variant; or
   - **HOME + AWAY kit** exports the paired sides together.

3. Choose **Editable folder** for ordinary GIMP work, or **ZIP hand-off** when
   you need one deterministic file to move between computers.
4. Click **Export Team Kit**, read the private-export warning, and choose a new
   destination. Mod Studio never overwrites an existing folder or ZIP.
5. Open `EDITING-GUIDE.md` inside the export, then edit only PNGs below
   `SETS/`. Do not rename files or change `team-kit-manifest.json`. Remove any
   editor backup/sidecar files before import because undeclared files are
   refused.
6. In GIMP, preserve each PNG's exact canvas size, RGBA mode, transparency,
   existing UV islands, seams, blank margins, and orientation. The exact body
   region represented by every pixel is not fully decoded, so use the exported
   source art as the registration template.
7. Back in Mod Studio, set the format selector to match the folder or ZIP you
   are returning, then click **Import Edited Kit** and choose it.
8. Review the completion message. All files are checked before anything is
   staged. Only decoded RGBA pixel changes become replacements, and the entire
   import is one **Undo** action. If every PNG is unchanged, no edit and no Undo
   entry are added.
9. Save the resulting `.2k5mod` project, then Build normally.

Every physical set has **39 writable components**: torso/jersey, sleeve,
pants, both live helmet families, jersey/helmet/arm digits 0–9, the horizontal
nameplate atlas, and three separate Team Select cards. The live textures and
Team Select pictures are different storage: changing one never regenerates the
other. Edit both `helmet00` and `helmet02` for complete player-model coverage.
Mud palettes are derived during the normal visual build from the edited clean
uniform art.

The package also contains **45 equipment references that are not part of that
writable bundle**: socks (clean/mud), elbow pads, gloves, long sleeves, shoes,
and wristbands. Select a physical set in **Uniform Sets**, then click **Browse
45 Equipment Textures**. Mod Studio opens the existing **All Textures** browser
already filtered to that exact selector; add `socks`, `gloves`, `shoes`,
`sleeves`, `pads`, or `wristbands` in the same search box to narrow it. This is
one canonical list, not a second import path. All **28,530** references across
the 634 physical sets keep the existing preview, Export, Edit, dialog/drag-drop
Replace, Revert, project save/load, and modded-XISO Build behavior. They are
labelled **Editable** only when the reviewed descriptor is compressed,
swizzled P8; any future unsupported format remains **Preview / Export only**.

Equipment variants inside one TSET share the retail shape/mip indices and own
separate colour palettes. Import therefore projects your image onto that proved
shape and changes only the selected palette. Every unselected sock/glove/shoe
variant remains byte- and pixel-identical. Highly detailed or noisy art may use
fewer colours so the complete VC-LZ TSET stays inside its original fixed span;
if even a usable two-colour result cannot fit, Build refuses it with a clear
message. The five global `shoes_taped`/`wristband_qb`/`elbowpad_*` targets in All
Textures are different standalone assets and keep their full P8 writer.

Each physical set also owns four **separate presentation textures** that are
not part of Team Kit's 39 live/card components:

| Resource | Size | Editor label |
| --- | ---: | --- |
| `logo` | 128×128 | Team Logo — Presentation |
| `chiclet` | 64×64 | Team Chiclet |
| `splayer` | 256×128 | Team Player Banner |
| `flipchip` | 64×64 | Team Flip Chip |

Open **All Textures → Team Presentation — Menu / UI**, or search a team name,
abbreviation, selector such as `21H0`, `menu logo`, or one of the four resource
names. All 2,536 records across 634 sets support preview, Export PNG, Edit,
dialog/drag-drop Replace, Revert, project save/load, and the composed XISO
build. A differently sized image goes through the same resize offer as other
visual imports before the fixed-size replacement is staged.

These resources are different bytes from `helmet00`/`helmet02`, jersey art,
and the three pre-rendered Team Select cards. Static `logo` and team-chiclet
lookups establish presentation/UI use, but not every exact screen consumer is
mapped, so the editor uses the honest umbrella label instead of claiming that
one texture controls every menu. Edit the live/card targets separately when
you want those views changed too.

The game also carries **1,755 team-linked menu, mini-card, franchise, and
draft logo surfaces outside the uniform packages**. These are now separate,
typed All Textures entries instead of being hidden behind the three aggregate
archives:

| Family | Count | Size | Find it with |
| --- | ---: | ---: | --- |
| Full menu team logo | 317 | 256×256 | `menu logo`, team name, or `logo_21_0` |
| Compact menu team logo | 317 | 64×64 | `compact team logo` or `logo_s21_0` |
| Shared menu flip chip | 317 | 64×64 | `flipchip` or `playoff picture` |
| Home/away mini card | 634 | 64×64 | `mini helmet`, `mini card`, or `21H0` |
| Franchise-office team logo | 85 | 256×256 | `franchise logo` or `coach desk` |
| Draft/PDA team logo | 85 | 64×64 | `draft logo` or `pda logo` |

Open **Team Logos — Menus / Presentation**, **Team Mini Cards — Menus /
Presentation**, or **Franchise & Draft Presentation**. Each entry shows its
team asset code, known team/style owners, exact archive, and statically
established consumer scope. A complete screen-by-screen consumer map is not
proved, so these rows keep the honest presentation/menu umbrella label;
franchise-office logos are deliberately not labelled midfield art, because
stock midfield graphics are a different resource family.

All 1,585 entries from `logos.cdf`, `mini.cdf`, and `flipchip.cdf` use raw P8
fixed slots. Replace preserves the wrapper, descriptor/system bytes, complete
resource span, and the 96-byte slot padding while regenerating only swizzled
indices and the palette, so a raw menu logo cannot fail with a VC-LZ size
error. The 85 draft/PDA entries use their existing compressed P8 spans and
the normal bounded compression recovery. Preview, Export, Edit,
dialog/drag-drop Replace with resize, Revert, project save/load, and composed
XISO Build are available for every one of these menu and draft/PDA entries.

The 85 `NN_teamlogo_00_h0` franchise-office rasters are editable presentation
textures in the **Franchise & Draft Presentation** group, each replaced inside
its exact compressed P8 span. Their consumer scope is statically established
— the executable binds them to the `FRANCHISE2` / `coach_desk` scene's
`teamlogo` element — and their ownership as stock midfield team logos remains
unproved, so the editor does not relabel franchise-office art as field art.

## Set facemask, faceshield, and turtleneck colours

1. Open **Uniforms & Equipment → Colours & Other Tools**.
2. Search by team name, abbreviation, or selector, then choose the exact
   physical uniform set. HOME, AWAY, alternate, and throwback records are
   independent.
3. Pick **Facemask / faceshield colour** and **HI_turtleneck colour**, then
   click **Apply to project**. The status line repeats the selector and values
   that were staged.
4. Repeat for any other sets, save the `.2k5mod`, and Build normally. Revert on
   this panel restores only the selected set; Revert All restores every edit.

The game stores two proved words in each set's `Unif` record. Word 0 jointly
controls the facemask and faceshield; Mod Studio does not invent a separate
visor control because no independent visor field has been proved. Word 1 is
`HI_turtleneck`. Shareable projects contain only the logical set selector and
your two ARGB choices. Raw retail bytes and physical offsets remain private and
are resolved and verified from the source XISO during Build.

A Team Kit folder or ZIP is a **private working export**. Its templates may
reproduce retail artwork from your own disc, so do not upload, publish, or send
that bundle to other people. The shareable artifact is the `.2k5mod` project,
which contains only your authored pixel-changed replacements and logical
metadata—never the exported source templates.

The manifest is bound to the exact source XISO SHA-256 and to the working pixel
baseline that existed at export time. Import it while that same source and
baseline are active. If you load a different dump, change/revert one of those
components after export, or load a project that changes the baseline, export a
fresh Team Kit before importing. This prevents an old bundle from silently
overwriting newer work.

## Autosave, recent files, and crash recovery

You do not have to remember a terminal command or recovery folder. After every
successful authored change, Mod Studio quietly writes a private
`unsaved-recovery.2k5mod` using the same validated, replacement-only format as
**Save Project**. It is bound to the SHA-256 identity and local path of the XISO
that owns the edit set. The autosave contains your PNG/WAV/text replacements
and logical selectors; it does not contain original game assets, an XISO, or
private previews.

If the app or computer stops unexpectedly, the next launch offers **Recover
Edits**, **Not Now**, or **Discard Recovery**. Recovery first reopens your own
XISO and refuses to apply the project if its source identity differs. If the
XISO was moved, **File → Recover Unsaved Edits** tells you the exact path that
must be restored; the recovery project is kept until you explicitly discard it
or save/replace the working set.

The **File** menu remembers up to eight recent XISOs and eight recent named
projects. Paths are private local settings and are not written into shareable
`.2k5mod` files. Before opening another XISO, opening another project, or
closing the app with changes that have not been saved under a project name,
Mod Studio asks you to **Save Project**, **Discard Edits**, or **Cancel**. A
cancelled or failed source/project load leaves the current session and recovery
snapshot intact.

## Named projects, Save, and Save As

Opening or naming a project turns it into the active document. Its filename is
shown in the window title; an asterisk means the working document differs from
the last successful named save. **Save** / **Ctrl+S** updates that exact active
project without asking for its filename again. **Save Project As…** /
**Ctrl+Shift+S** always asks for a new destination. A recovered edit set is
intentionally **Untitled** until you name it.

Fast Save remembers the filesystem identity of the project you opened or last
saved. If that file is deleted, replaced with a link, or changed by another
program, Mod Studio refuses to overwrite it and tells you to use Save Project
As or reopen it. A failed save leaves both the existing file and the working
edit set intact.

One project may contain at most **25,000 combined visual and audio edits** and
**1 GiB of authored replacement payloads**. These are simultaneous-project
limits, not catalog limits: every indexed asset still remains browsable and a
large conversion can be split into smaller shareable projects. Mod Studio also
checks the ZIP's total declared expansion and available staging space before it
extracts anything.

The asterisk tracks document history, not only the current replacement count.
For example, if a named project contains one edit and you choose **Revert All**,
the footer reads **No edits • unsaved** and Save remains available. Saving then
publishes a valid empty, replacement-only project so the old edit is actually
removed from that project. Private recovery supports the same empty state;
Build remains disabled until at least one replacement is staged.

## What the status labels mean

- **Editable** means Export, Replace, Revert, project save/load, and Build are
  supported for that row.
- **Preview/Export-only** means the app can safely show and export the asset,
  but does not yet own a safe replacement contract.
- **Proof boundary** identifies a reviewed witness that is useful for auditing
  but is not itself an authoring action.
- **Research boundary** keeps unresolved ownership visible without pretending
  that a safe writer exists.
- **Modified** means your current project has staged a replacement for that
  asset.

These labels come from the same capability registry used by the build system.
The current registry has 70 cross-title rows, including 32 Xbox NFL 2K5
capabilities and the separate PS2 save-import bridge. No current 2K5 capability
is labeled Coming Soon, and an asset never becomes writable merely because it
has a preview.

## What v1.0 covers

The complete 12-tab sidebar is present even where a feature remains read-only.
The whole-game resource browser is the fallback home for anything that does not
yet have a specialized editor, so indexed assets are not hidden.

### Uniforms, players, identity, fields, and presentation

- The visual catalog includes all **28,530 package-local uniform-equipment P8
  palettes** as editable assets alongside uniforms, portraits, live faces,
  create-team field art, scorebug/presentation art, and Team Select cards.
- **Supported Team Kit** exports/imports all 39 writable components for any catalogued
  physical set, including paired HOME/AWAY kits. Imports validate the complete
  source-bound bundle first and stage pixel changes as one Undo action.
- Uniform gameplay textures and Team Select cards are separate. Replacing a
  jersey or helmet does not automatically repaint the card shown before a game.
- Team/player identity uses same-allocation text. The app shows the maximum
  space available and rejects a longer value without changing the project.
- `digital_font` is shared presentation art. Editing it can affect screens
  beyond the field scorebug.

### Text and rosters

- Open **Rosters & Players → Players & Numbers** for current and historical
  roster editing. Portrait and live-face textures remain beside it under
  **Portraits & Faces**. **Text & Team Identity** now stays focused on the
  universal fixed-allocation text browser, so the same roster tools are no
  longer filed under two unrelated concepts.
- **All Text** searches 716 recognized banks and 23,346 decoded strings. Exactly
  20,074 strings are Editable; 3,272 remain read-only with a reason.
- **Current Roster Players** gives every current player an explicit searchable
  row with current name, number, face-shield type, status, Export, Apply, and
  Revert controls. All 2,547 current jersey numbers and face-shield selectors
  are Editable, including all 68 secondary-pool rows. Primary same-allocation
  names are Editable; secondary-pool names remain read-only because their text
  allocation is zero.
- **Face shield is per player:** choose **None**, **Clear**, or **Dark**. It is
  not a HOME/AWAY visor tint or color picker. The editor refuses reserved raw
  value `3`, preserves every unrelated bit in the shared player word, and
  composes simultaneous jersey/face-shield edits into one write. A loaded
  roster or franchise save may override this disc-default value.
- **Historical Teams & Players** exposes all 75 historical ROST resources and
  3,975 historical players.
- Across the current and historical views, all **6,522 jersey-number assets**
  are covered exactly once and Editable through masked number-bit writeback.
- ESPN 25th Anniversary moment titles, historical descriptions, objectives,
  and dates are Editable. Team selectors, scenario values, and unlock logic
  remain inspect-only because their selector/unlock ownership is not proved and
  they are not ordinary text.

### Stadium Studio

Stadium Studio lists **477 scenes**. You can orbit, pan, and zoom a derived 3D
view, click a surface to identify its owning texture, then Export, Replace, or
Revert that texture in the same panel. All **23,838 indexed P8 texture
occurrences** support the bounded project/build route.

The proved full scene also supports a deliberately narrow model round trip:

1. Select it and choose **Export model (glTF)…**.
2. Keep the exported `.gltf` and `.bin` together, then move existing vertices
   in Blender. Do not add/remove faces or vertices, weld, subdivide, decimate,
   rename/remove meshes, or apply a topology-changing modifier.
3. Choose **Import edited model…** and select the edited `.gltf`.

Mod Studio compares the complete triangle topology and vertex counts before it
stages anything, then writes only the catalogued position lanes. The game's UV,
material, collision, selector, LOD, and other stream bytes stay untouched.
Texture and geometry changes in that same scene are composed before one fixed
SCNE rebuild. This is not arbitrary model swapping and cannot install a new
topology. The source-derived position recipe remains private: build it locally;
it cannot be saved inside a shareable `.2k5mod`.

Each SCNE resource must retain its original compressed allocation. If an
unusually noisy texture or edited position stream cannot fit, the app refuses
it with an actionable message instead of creating a risky build.

The first Stadium visit derives private glTF/PNG data from your own source
cache. This can take 10–30 minutes and use roughly 750 MiB. Completed scenes are
checkpointed so generation can resume after an interruption. These derived
models/textures stay private and are not part of a shareable project.

### The Crib

The Crib lists **498 assets**:

- 242 raw Team Item P8 textures, including all 128 Team Photos;
- 68 standalone P8 textures, including the reflection and linear ticker; and
- 188 material/submesh-owned P8 surfaces across 36 SCNE scenes.

All **498 are Editable** through their original fixed allocations. Extremely
flat or heavily noisy/dithered art can exceed a compressed slot; simplify the
image if the app reports that boundary.

The **Models** tab also exports and imports position-only edits for ten exact
electronics meshes across seven scenes. Move existing vertices in Blender, but
keep every vertex count and face unchanged. UVs, materials, collision, indices,
normals, other registers, and topology remain original game data. This can
reshape the proved meshes within their existing structure; it is not arbitrary
object or helmet replacement.

Crib preview/export/replace work and Audio preparation share one safe background
operation lane. While either owns it, the category list and global
source/project/save/build/undo/revert/close actions wait for that operation to
finish; this prevents one panel from changing the game session underneath the
other. Audio's waveform Cancel remains reachable when Audio owns the lane.

### Audio

The Audio tab opens on **All Playable Audio** and has five scopes, so soundtrack
and commentary are no longer hidden behind the archive-resource browser:

- **All Playable Audio (54,421; default):** one searchable, pageable view lists
  all **850 standalone sounds first**, in their existing standalone order, then
  all **53,571 playable streaming ranges**, in their existing range order. The
  **Modified** filter covers both domains. Complete streaming banks and opaque
  raw containers are excluded because they are not individual playable sounds.
  Rows keep their normal type and actions, so selecting a standalone cue or a
  streaming range still shows its exact Play, Export, Replace, Revert, and WAV
  contract. **Export matching audio** publishes 1–256 matching rows as current
  playable WAVs with truthful per-row source/replacement labels. Raw `.bin`
  export stays in the dedicated bank/range scopes. **Meaning confidence** is
  disabled here because its 1/152/697 labels apply only to standalone sounds;
  choose **Standalone sounds** before using that filter.

- **Standalone sounds (850):** every `AUDO` cue is searchable, playable, and
  exportable as PCM16 WAV, and all **850 are Editable**. Menu Back keeps its
  separately reviewed route; the other 849 use exact, non-overlapping physical
  fixed slots. For 697 alias-related rows, the exact slot is known but the
  human/in-game cue meaning is not. Read the warning, identify the sound by
  playing it, and expect that a duplicate-looking row may be consumed somewhere
  other than its provisional label suggests. Use the **Modified** status filter
  to review only the WAV replacements currently staged for the next build.
- **Meaning confidence:** this is separate from edit status. Use the standalone
  filter to isolate **Menu Back route (1)**, **Reviewed labels (152)**, or
  **Provisional labels (697)**. Every row still owns an exact Editable physical
  slot; this filter says how much is known about its human label/runtime caller,
  not whether Replace is safe.
- **Streaming banks (17):** every known `AUSB` descriptor is searchable by
  family, including soundtrack/music, commentary/speech, stadium/PA/coach,
  broadcast/presentation, and ambient banks. Together they index **53,571
  ranges** across 16 external files. **Export Raw Bank** copies the exact `.bin`
  from your own game; it is not a playable WAV. That export contains retail
  audio bytes, never enters a `.2k5mod` project, and must not be distributed.
- **Playable streaming ranges (53,571):** every exact boundary pair inside
  those descriptors is independently searchable, playable, and **Editable**.
  **Replace** accepts a canonical PCM16 WAV with the exact channel count,
  sample rate, and frame count shown for that row, then encodes it into the
  existing fixed slot in a new copied XISO. **Export WAV** returns your staged
  WAV when Modified and otherwise privately decodes the source Xbox IMA blocks;
  **Export Raw Range** always preserves the original encoded retail span. The
  range number is an exact logical owner, not a recovered human cue name.
  Source-derived WAV/raw exports must not be distributed or put in a project.
  A `.2k5mod` stores only a user-supplied replacement WAV and the logical range ID.
- **Raw Bank Containers (9):** the universal index owns exactly three `BANK`,
  three `ABNK`, and three `WBNK` containers. Search, filter, page, inspect, and
  use **Export Raw Container** to copy one byte-exact `.bin` from your own
  source. These are whole opaque containers, not playable cues, so Play,
  Replace, Revert, and shortlist actions stay disabled. If the exact nine-row
  inventory cannot be established, the scope refuses to show a partial or
  misleading catalog. Raw exports contain retail bytes and must not be shared.

The selected-sound inspector keeps Play, Export, Replace, Revert, and the WAV
drop target pinned at the bottom. Long format contracts, exact IDs, ownership
warnings, shared-slot owner lists, and the all-850 replacement path scroll above
those actions instead of pushing them out of reach. Technical text remains
complete and selectable, so copying an ID or path never inserts hidden breaks.
Changing rows returns the inspector to the top.

Audio filters and shortlist controls use two compact rows. Nothing is hidden:
search/scope stay together, the family/status/meaning filters sit directly
below them, and shortlist add actions are separated from review/count/clear/
export actions. This keeps even the longest 256-sound labels inside the app's
normal minimum-width workspace without overlapping or shrinking a control below
its usable size.

#### Name and annotate sounds as you identify them

Every standalone sound and exact playable streaming range has a **Your cue
label & notes** card. Enter a custom title (up to 120 characters), a research
note (up to 2,000 characters), or both, then choose **Save label**. This is the
safe place to record a soundtrack title, commentary line, crowd reaction,
menu action, or replacement idea after listening. The custom title appears in
the Audio table with a pencil marker; the original game/catalog label and
stable cue ID remain visible in the details and tooltip.

Custom titles and notes are searchable immediately. Turn on **Labeled only**
to show just the cues you have identified; it works in All Playable Audio,
Standalone sounds, and Playable streaming ranges. Complete banks and opaque
raw containers cannot own a cue label because each contains multiple or
undecoded sounds. Shared physical WAV aliases still receive separate labels by
logical cue ID, even though replacing either alias changes their shared sound.

Labels are user-authored project metadata, not game edits. They save inside
the `.2k5mod`, survive Open Project and private recovery, and support individual
Clear, Undo, and Revert All. An annotation-only project can be saved and shared
without any retail audio. Labels never enable **Build Modded XISO**, never
change the source or output XISO, and never count as a Modified WAV. The header
reports cue-label and build-edit counts separately so this boundary stays
visible.

An unfinished title or note stays as a local draft while you change rows,
pages, or filters; return to that cue to continue, then choose **Save label** to
put it in the project. When you export a matching collection or Audio
Shortlist, its local ZIP manifest includes the custom title, note, and preserved
game/catalog name, and its playlist uses the custom title. The stable cue ID
and payload path remain canonical. The ZIP may contain retail-derived audio
from your own XISO and is still a private listening export—not a shareable mod
project—even though its label metadata is user-authored.

Typing in Audio search deliberately waits 220 milliseconds after the last
keystroke before rebuilding the result page. During that brief update, the old
visible row remains available for Play, Export, Replace, Revert, or adding that
one selected sound. Actions that mean “this page,” “all matching,” or another
page show an updating message and stay disabled until the displayed results
match the new search and filters. This prevents a fast click from acting on the
previous result count or previous page.

Play is bound to the sound and game source currently selected. Changing to a
different row stops Mod Studio's player; refreshing the same row leaves it
alone. A delayed WAV preparation result or error from an older row/XISO is
discarded, even if you later return to an asset with the same ID. Linux playback
requires one controllable helper—`ffplay`, `paplay`, or `aplay`. If none is installed, the
app explains what to install and does not open a separate player it cannot stop.

Select a standalone sound or one playable streaming range, then click **Load
waveform** for a visual overview of its current PCM16 WAV. Nothing loads
automatically, playback never starts, and drawing the waveform does not stage an
edit. If that row is Modified, the view comes from your staged WAV; otherwise it
comes from the private source-derived WAV. Use **Reload waveform** after an
outside file change. Complete banks and opaque raw containers cannot be shown as
one waveform because each contains multiple or still-undecoded sounds.

Waveform sampling is deliberately bounded, so a long soundtrack does not get
read into memory in full. **Cancel waveform** discards the result at the next
safe boundary. If the app first has to decode a source range, that in-process
decode itself cannot be interrupted; wait for it to finish safely. While Audio
owns that background operation, source/project changes, Save, Undo, Revert All,
Build, Launch, and closing are paused so none can race the current sound. The
Audio page stays usable so its Cancel control remains reachable.

Use **Soundtrack & music (136)** for a one-click view of every currently known
music range. These are exact bank/range identities, not recovered song titles.
**Export soundtrack & music (136)** saves that filtered collection as one WAV
ZIP. For any other view, **Export matching audio** becomes available when the
current filters contain 1–256 rows. The default mixed All Playable view exports
WAV only. Complete banks export as raw `.bin` from **Streaming banks**, ranges
can export as decoded WAV or exact raw `.bin` from **Playable streaming
ranges**, and standalone sounds export as their current WAV (your staged
replacement when Modified, otherwise the local source-derived WAV). Broader
results ask you to narrow the search or family so the app cannot accidentally
begin an enormous export.

Use the **audio shortlist** when the sounds you want do not share one filter.
Choose a playable standalone sound or indexed streaming range, then click **Add
selected sound**. **Add this page** adds every playable row currently visible;
the operation adds all of them or none of them if the 256-sound limit would be
exceeded. **Add all matching** collects an entire filtered result in one action
when it contains 1–256 standalone sounds or playable streaming ranges. It
rechecks the search, family, edit status, meaning confidence, count, and order
before changing the shortlist; existing selections stay selected once, and a
result that would exceed 256 adds nothing. A `★ Selected` status and the
**Selected _n_ / 256** counter make the curated set visible. Re-select a sound
to remove it, or use **Clear**. After Clear, the same button becomes **Undo**
and restores every cleared sound in its exact prior order. That one-level undo
remains available until you add/remove another shortlist sound or load another
XISO; browsing, searching, and a refused source load do not discard it.

Click **Review selected** to work only with the curated list. The review table
keeps the same order that will be exported. Use **Move up** and **Move down**
to arrange it, Play/Stop to audition an entry, or remove an entry without
returning to its original search. **Back to browser** restores the scope,
family, status filter, search text, page, and selected browser row you left.

The shortlist keeps its insertion order while you change searches, pages,
families, scopes, or load another project for the same game source. It is a
session convenience, not authored project data, and clears when another XISO is
successfully loaded. **Export selected WAVs** writes those exact IDs in that
order as one transactional WAV ZIP. Standalone rows use the current WAV, so a
staged replacement is included; streaming ranges likewise use the staged WAV
when Modified and the verified local decoder otherwise. Complete streaming
banks are excluded because one bank contains many
sounds—open **Playable streaming ranges** and select the ranges you want.

The full 136-range decoded music collection is about **1.22 GiB of WAV payload**
before ZIP compression. Allow roughly 3 GiB of temporary free space and expect
this export to take longer than a single cue. Exact raw-range export is much
smaller but is not directly playable in normal audio software.

Every collection ZIP is completed in private temporary storage before it
appears at the filename you chose; an error leaves no partial ZIP and an
existing file is never overwritten. Its `manifest.json` labels each entry as
`user_replacement` or `retail_derived`. When a bundle contains WAV entries it
also contains `playlist.m3u8`, whose relative entries follow the exact bundle
order; the manifest records its path and WAV count. A raw-only bundle omits the
playlist instead of pretending opaque `.bin` files are playable. A collection
ZIP is a local convenience
export, **not** a shareable `.2k5mod` project. It never enters project save,
Undo, recovery, or Build, and retail-derived entries must not be redistributed.

#### Replace a soundtrack, commentary, crowd, or presentation range

1. Choose **Playable streaming ranges**, then narrow the family/search or use
   the **Soundtrack & music** quick view. Play candidate rows to identify the
   sound you want; human cue names, loop rules, and mixer purpose are not yet
   decoded, so confirm by listening.
2. Export WAV as a shape/template reference, but do not redistribute that
   source-derived file. Create your own audio and make it canonical PCM16 with
   exactly the row's listed channels, sample rate, and frame count. Replace
   refuses even a one-frame mismatch or extra WAV metadata.
3. Click **Replace** or drop the authored WAV on the replacement area. The first
   audio edit on a newly indexed game may take roughly **20–35 minutes** while
   Mod Studio reads the XISO and creates two private, metadata-only source-audio
   safety indexes. This happens once, shows progress in the app, needs no
   terminal command, and never writes to the source XISO. Later edits reuse the
   private indexes.
4. If the detail panel says **Shared physical slot**, all listed logical owner
   rows change together. Replace, Modified status, Revert, Undo, Revert All,
   project save/load, and Build all treat that shared slot as one edit. Two
   aliases cannot supply different WAVs in one project/import.
5. Play or Export WAV again to hear/check the staged authored bytes, save the
   `.2k5mod`, then choose **Build Modded XISO**. The raw bank remains fixed-size;
   no bank repack, loop/mixer edit, or runtime cue-name claim is implied.

The private safety indexes cover every standalone cue and all **53,570 physical
streaming slots** behind the 53,571 logical rows. They reject exact source PCM
and unchanged source excerpts before a supplied WAV can be staged, saved,
loaded, or built. These large private digest files remain under the local
source cache and are never copied into the application, a `.2k5mod`, or a
release archive.

#### Batch-replace all standalone sounds or a selected Audio Shortlist

The replacement-pack card has three content modes:

- **All standalone sounds (850)** is the replacement-pack default. It creates
  the frozen v4
  metadata-only template for every standalone physical sound slot: Menu Back
  plus all 849 fixed-AUDO slots. The template includes exact WAV contracts,
  logical targets, current-edit baselines, the whole source XISO's SHA-256
  binding, and a human-readable `AUDIO-CUE-MAP.csv`. That map connects each
  generic replacement filename to its Audio-browser ID, display name, family,
  duration, exact WAV settings, edit route, and current runtime-meaning status.
  It contains no original WAVs, decoded game audio, physical offsets, private
  per-audio PCM fingerprint inventory, or rollback bytes. For 697 provisionally
  named rows, the physical slot is exact while the human meaning and runtime
  cue owner may still be unknown. Old v3 all-850 packs remain accepted.
- **Selected shortlist (1–256)** creates a v2 pack from the shortlist's exact
  visible order. Use it to mix standalone sounds with fixed-slot soundtrack,
  commentary, stadium, crowd, and presentation ranges.
- **Legacy 153-cue pack** keeps the original v1 pack byte-compatible: all 152
  previously exposed fixed-AUDO cues plus Menu Back, in their frozen order.

Complete raw banks are never eligible because a bank is a container, not one
replaceable sound. Use All standalone for bulk cue discovery or a complete
authoring hand-off; use Selected shortlist for a soundtrack collection or a
small hand-picked set. **All Playable Audio is a browser/export scope, not a
54,421-row replacement-pack template.** The v4 contract and canonical order
remain exactly the 850 standalone sounds; streaming ranges enter a replacement
pack only through the existing 1–256 selected-shortlist route:

1. For a selected pack, add 1–256 Editable standalone sounds or **Playable
   streaming ranges** to the Audio Shortlist. Use **Add all matching** when one
   filtered result contains the set you want. For example: choose **Standalone
   sounds**, set **Meaning confidence → Reviewed labels (152)**, then click
   **Add all matching (152)** to create the complete reviewed-label shortlist in
   one action. Use **Review selected** and Move up/down if order matters.
   All-850 and legacy exports ignore the shortlist.
2. In the replacement-pack card, choose **All standalone sounds (850)**,
   **Selected shortlist (1–256)**, or **Legacy 153-cue pack**. Choose
   **Editable folder** for local work or **ZIP hand-off** to move one template,
   then click **Export replacement template**. Existing destinations are never
   overwritten.
3. For the default v4 pack, open `AUDIO-CUE-MAP.csv` first. Filter its safe,
   single-line columns by `display_name`, `family_label`, or
   `runtime_meaning_status`, then use `replacement_path` as the exact destination
   for your authored WAV. Copy the CSV outside the pack before adding personal
   notes: the copy inside the pack is read-only, hash-pinned reference metadata
   and import refuses a changed or reordered map. You can paste `asset_id` into
   the Audio search box to play or privately export the matching original from
   your own XISO. Every standalone sound's detail card also shows its exact
   all-850 `replacements/NNN__selected-audio.wav` destination; choose **Copy
   pack path** or press **Ctrl+Shift+C** instead of retyping it. Streaming ranges
   and raw banks do not show that action because they are not members of the
   all-850 standalone pack. The on-screen **Meaning confidence** filter uses the
   same three status values as the CSV, so you can reduce the browser to the
   Menu Back route, 152 reviewed labels, or 697 provisional labels before
   searching, shortlisting, or exporting matching rows. Those groups do not
   claim that every label has been heard and confirmed in-game.
4. Open `EDIT-AUDIO.md` and `audio-replacement-pack.json` for the machine
   contract. Each row owns one logical sound ID, declared path, exact
   channels/rate/frame count, and strict PCM16/no-metadata contract. A v2 row
   may also disclose the other logical alias that shares its fixed slot. A v3
   or v4 complete pack must retain the exact canonical 850-row order. Every pack
   binds to the whole source XISO by SHA-256; no pack exposes physical offsets,
   bank paths, private per-audio PCM fingerprints, original audio, or rollback
   bytes.
5. Put only the user-supplied WAVs you want to apply at their declared paths
   below `replacements/`. Missing WAVs mean “skip.” Do not rename files, edit
   the manifest/guide/cue map, or leave backup files in the pack. Keep every WAV
   exact: RIFF PCM16 little-endian, listed channel count, sample rate, and frame
   count, with no extra metadata. Even a one-frame mismatch is refused.
6. Choose **Import replacement pack**. The first pass is a read-only Preview:
   Mod Studio auto-detects legacy v1, selected v2, old complete v3, and mapped
   complete v4 packs, then validates the source binding, exact logical targets,
   canonical order where required, disclosed aliases, current replacement
   baselines, v4 cue-map bytes, every supplied WAV shape, and source-safety
   rules. It shows supplied/already-current/change counts, unique physical
   slots, restorations, linked aliases, the resulting Modified count, and a
   bounded list of named changes. Preview does not stage files, add an Undo
   action, change the project manifest, or modify the source XISO. If every WAV
   is already current, **Apply** is unavailable and the workflow ends safely.
7. Review the Preview dialog, then choose **Apply** or **Cancel**. Apply uses an
   opaque session-only confirmation token and reopens and fully revalidates the
   exact folder or ZIP before the atomic write. If any pack member, the loaded
   source, the session, or project/audio mutation revision changed after
   Preview, Apply refuses it and asks you to Preview again. The token does not
   expose or retain a ZIP path, WAV bytes, source hash, or private member hash.
   Conflicting alias files fail; identical alias files collapse to one physical
   edit.
8. All real changes enter as one **Undo** action. Canceling or supplying an
   invalid, stale, duplicate, unknown, conflicting, or unchanged-only pack
   stages nothing. Transactional Undo restores the whole prior set or leaves
   the retryable action intact if a disk/validation failure interrupts
   restoration.
9. Review **Modified**, then save a `.2k5mod` or Build. The source XISO remains
   unchanged; the project contains only user-supplied WAVs and logical metadata.

The unedited template is safe to share because it contains **zero audio files**,
only generated metadata, the authoring map, and instructions. The map contains
no decoded PCM, original audio, private fingerprints, physical game offsets, or
rollback bytes. After WAVs are added, share them only when you have the rights
to do so. Mod Studio's private gates reject exact source
PCM and the unchanged source excerpts covered by their window/anchor rules, but
they cannot prove who authored transformed or re-encoded audio and cannot decide
copyright or license. Those decisions remain the mod author's responsibility.
Whole streaming-bank replacement remains unavailable because cue naming,
loop/mixer rules, and a general bank-repack format are not decoded.

Each Editable row shows the exact PCM16 channel count, sample rate, and frame
count its WAV must preserve. Complete-bank Play stays disabled because a bank
contains many ranges, while each range has Play/Stop and WAV export. Streaming
range replacement is fixed-allocation: it preserves the existing duration and
layout and does not edit cue identity, loops, gain, pan, priority, or mixer
routing. Never rename a raw bank to `.wav`; use a range's **Export WAV** action.

### Playbooks and gameplay experiments

- **Playbooks & Plays** is a structured inspector for 37 books, 1,533
  formations, 9,251 plays, 32,502 assignment chains, 91,833 nodes, and 101,761
  player-slot references. Raw PLAY export is supported. You can copy an exact
  stock assignment route from another play/slot in the same book, Revert it,
  save it in a project, and Build. Freehand route drawing/import remains
  unsupported because coordinates, opcodes, player roles, save ownership, and
  inverse compilation are not safely decoded.
- **Sliders & Gameplay** shows the real state of the Draft and Catching work.
  The known 17-position table belongs to Fantasy Draft, not Franchise rookie
  drafting. Catch 125/150/200 and the Fantasy Draft control remain experiments
  until matched xemu tests prove a causal runtime effect; they are not presented
  as finished presets.

## Rules that prevent most bad imports

- Start from the app's exported template.
- Keep the exact image width/height and required alpha behavior.
- Do not rename or hand-edit stable asset IDs inside a project.
- Keep audio channels, rate, sample count, and required PCM format exact.
- Keep text inside the shown UTF-16 allocation limit.
- Do not choose your source XISO as the build output.
- Keep related assets together, especially gameplay uniforms and their separate
  Team Select cards.

If an import is incompatible, the app explains the expected dimensions, format,
or allocation and leaves the staged project unchanged.

## Revert, failed builds, and sharing

Use **Revert** on one asset or **Revert All** for the whole project. The app
keeps each changed asset's original privately so rollback does not depend on
shipping original bytes inside the project.

A build is assembled under a temporary name and the requested output is created
exclusively only after success. A failed build cannot publish a partial output,
and the source XISO is never a build destination.

When sharing a mod, send the `.2k5mod` project—not your XISO, private cache,
exported originals, or built output. The recipient applies the project to their
own recognized dump.

## Tested boundary

The composed v1 smoke staged 19 Tier 1 edits, built one separate XISO, changed
1,027,710 bytes, and left the source SHA-256 unchanged. Headless xemu on the
private display `:99` visibly reached the ESPN splash, stable attract sequence,
and clean NFL 2K5 title / **Press START** screen without visible corruption.

That is a boot-level spot check, not proof that every edited asset was visited
and judged during gameplay. A later isolated software-rendered harness retry
logged a PFIFO assertion during or after shutdown, so the release does not claim
a clean long-duration gameplay session from that retry. xemu is the supported
target; original Xbox hardware is untested.

RC11 also completed a separate real-source, headless streaming-audio product
flow. One authored AUSB WAV passed Replace, Modified playback/export,
replacement-only project save, fresh-session project load, Build, and
independent Verify. The source XISO remained unchanged, and the temporary
6.30 GB output was removed after the result was recorded. This proves the
offline authoring/build path; it does not prove that the selected range was
heard in-game or establish its semantic cue name.

## ★ Create a Play (RC77)

The last entry in the left navigation. Load your NFL 2K5 disc first (File →
Open), then walk the five steps: pick a team's playbook, lay out a formation
(modern templates; drag a player to move him, click him to swap or change his
position), choose run or pass, draw routes by dragging from a player or pick a
job from his menu, replace outdated stock plays, build. Every authored play is
checked against the game's own validator before it is staged; the build refuses
anything the game would reject.

## Throw Distance & Arc (RC77)

Sliders & Gameplay → **Throw Distance && Arc**. Choose a `default.xbe` or a
disc image, move the two sliders (deep-ball ceiling in yards at 99 arm, pass
arc), watch the per-arm preview (ceiling, hang time, apex), choose where to
save the patched **copy**, and write. The source is never touched. The copy is
xemu-only: its RSA signature cannot be regenerated, so real hardware rejects it
(the same rule as Bump strength). `tools/nfl2k5_throw_distance.py` does the
same from a terminal (`read`, `sliders`, `curves`, `preview`).

**Position on Edit Player, Pro Bowl order** (Gameplay group, every preset): Edit Player's first
page gains the game's own Position picker after Last Name, in roster mode and inside Franchise
(the ratings stay, the overall follows the new position; run Depth Chart -> Auto afterwards), and
the Pro Bowl Votes tabs run offence, defence, then kicker and punter. Both are unwitnessed in game.

**Penalties at NFL rates, Chop Block toggle** (Gameplay group, advanced and experimental presets):
retail's default 50 on every slider flags far more holding, face masks and clipping than an NFL
Sunday, the incidental face mask is still the 2004 five-yard call, and the Chop Block On/Off toggle
does nothing (chop blocks ride the Clipping slider). The patch re-knots seven of the hidden
slider-to-rate curve tables in place so 50 lands near the NFL 2024 per-team-game rates (0 still
means none, 100 keeps the retail extreme; every Penalty Settings slider still moves in 40 steps and
"All Penalties Off" still kills every flag), makes the incidental face mask 15 yards, and wires the
Chop Block toggle for real. Retail profiles carry Chop Block **Off**: switch it On in Penalty
Settings if you want chop blocks called. Illegal formation, illegal contact and 12 men do not exist
in the engine. **The rates are an estimate** (the engine has no calls-per-game number; each slider
drives a probability per event, a hazard per second or a grace window, and how often those events
happen is unmeasured). Calibration recipe: on a **retail** copy at default sliders, play or watch
six CPU-vs-CPU games (coach or demo mode; Practice -> Scrimmage does not count, penalties are off in
practice) and tally the flags by type from the play log and the referee announcements (holding,
false start, DPI, roughing, face mask, defensive holding, clipping, late hit, offside/NZI, delay).
Divide the NFL rate (per team-game: offensive holding 1.30, false start 1.30, DPI 0.58, defensive
holding 0.34, unnecessary roughness 0.34, delay 0.32, roughing the passer 0.18, face mask 0.17,
NZI 0.17, ineligible downfield 0.14) by what you counted, scale each table's 50 knot by that
factor (never above its 100 knot), and send the numbers in: they become the shipped profile.
Unwitnessed in game.

**Home/away jerseys at any stadium** (Gameplay group, ADVANCED and EXPERIMENTAL): the retail game
decides the jersey colour once per game load (home dark, visitor white, except the Cowboys wear
white at home and navy in Washington and Tennessee) and only lets you choose the era. With the
patch, on Controller Assign or the exhibition Team Select screen, keep pressing up (or down) on a
side's uniform past its last era: that side's colour flips and the era restarts at the first (or
last) one, so each side cycles 15 eras x 2 colours on the same input. The retail default is still
the default, and both teams may choose white. Practice and Xbox Live are not covered, and the
Team Select preview shows the era art only, not the colour. Unwitnessed in game.

## If xemu says "insert a disc" or stops at the Xbox logo

Every disc the studio writes is a plain XISO; the changed bytes are inside `default.xbe` and the
packs. If xemu will not boot it: quit xemu completely and load the image fresh (the "insert a
disc" message means no disc was mounted at boot); keep the images outside `C:\Program Files`;
make sure the save name ends in `.iso` (the studio adds `.xiso.iso` to a bare name); check that
your retail image boots with the same settings; and if you run a ReShade or other graphics
wrapper, try once without it. The boot logo the kernel draws is kept decodable by the builder
from RC81 on.

## Updating the studio

The studio checks GitHub for a newer release when it starts (Help menu: **Check
for updates automatically** turns that off; **Check for Updates…** asks now).
When there is one, a banner appears with three choices:

- **Update now** downloads the release, verifies it against its published
  SHA-256, installs it over this copy and reopens the studio. Save your work
  first: the studio closes to finish. On Windows the installer runs on its own
  after the studio closes and reopens it when it is done. From an unpacked
  release folder the new version is placed beside the old one, the folders are
  swapped so your shortcut keeps working, and the previous version stays next
  to it as `<folder>.previous` until you delete it.
- **Get the update** opens the downloads page instead, for a manual install.
- **Later** hides the notice until the next release.

**Update now** is only offered when this copy knows how to replace itself: the
Windows installer layout, or an unpacked release folder you can write to. A
folder you cannot write to, or a git checkout, gets the link only. Nothing is
downloaded until you press the button and confirm.

## ★ Models — every model out to Blender and back

1. Load your XISO, open **★ Models** (below the categories) and press **List the models**.
   Every 3D model on the disc appears; filter by group (Players, Helmets & face masks,
   Balls & field props, Officials, Cheerleaders & crowd, Sideline props, Stadiums, Trophy
   room, Cutscenes, The Crib, Menus) or search by name.
2. Pick a model and press **Export selected**. You get `<model>.gltf`, `<model>.bin` and a
   README in the export folder. Open the `.gltf` in Blender (File → Import → glTF 2.0).
   Units are metres; keep the scaled root node.
3. Edit: move vertices, sculpt, proportional-edit. Keep the vertex count and the triangles;
   do not decimate, merge or add geometry (the game's allocation is fixed).
4. Export from Blender (File → Export → glTF 2.0) and tick **Include → Data → Mesh →
   Attributes** so the `_NFL_VERTEX_INDEX` and `_NFL_COLOR` lanes come along; `.glb` or
   `.gltf` both work.
5. Back in ★ Models, select the same model, choose the edited file and press **Check the
   edited file**. The report says how the file was matched, how many vertices moved, how many
   normals / UVs / vertex colours changed, whether an encodable range (positions or UVs) was
   widened, and whether the model still fits its space on the disc.
6. Choose the source image and where to write the copy, then **Write the copy**. The source
   is never touched; a receipt is written beside the copy. Share → Apply can turn that copy
   into a `.2k5patch`.

**UVs (RC82).** Texture coordinates follow the game's own rule: every mesh stores a scale and
offset in its shape record (`+0x30`), the vertex shaders compute `uv = lane × scale + offset`,
and there is no V flip. Tiled surfaces (seat rows, crowd, concrete, ad boards; 242 of 282
stadium meshes, up to 12 repeats) legitimately run past 0..1 in Blender and repeat, and each
mesh's tiling is listed in the README and in the mesh extras (`nfl2k5_uv_scale`,
`nfl2k5_uv_offset`). Beta 56 used one fixed formula for every model, which squeezed tiled
surfaces onto one repeat and mirrored V — the "scrambled stadium textures" people saw in
Blender. **Write UVs from the file** on import inverts through the same per-mesh constant;
a UV moved outside a mesh's range widens that mesh's constant for you (one axis at a time)
when **Widen the range** is ticked. UVs stay off by default on import.

**Vertex colours.** The game's per-vertex colour is baked lighting that multiplies the texture
in game. The export carries it as the `_NFL_COLOR` attribute (r g b a, 0..1; see it in the
Spreadsheet or paint it with an Attribute node), so textures show at full brightness in
Blender. Tick **Bake vertex colours into COLOR_0** in the export box for the darker in-game
look. Paint `_NFL_COLOR` and it comes back with **Write vertex colours from the file** (on by
default; an unedited file writes nothing).

**Textures and the Stadiums page.** Every embedded image is named after the material that maps
it and carries its `nfl2k5_texture_id` (materials and textures carry it too), so a stadium
exported here, edited in Blender and re-exported can be handed to the Stadiums page's texture
write-back, and the community Blender add-on's part handles find the same `source_*` extras the
Stadiums export has. The Stadiums page's own export is still positions only.

What you cannot change (yet): the number of vertices or triangles, bones, weights, animations,
and the body-type / face morph deltas (their channels are listed in the export). The player
body and head are shared base meshes; editing them changes every player.

## ★ Build & Share — the SOFTDRINK patch (RC78)

Open your disc image (File → Open), go to **★ Build & Share → Build**, and press
one of the three preset buttons: **Basic** keeps the game in 2004 and ticks only
the 2K5 fixes (throw ceiling 80 with realistic flight, real Catching and
Interception sliders, draft and free-agency AI, real returners, kicking power);
**Advanced** adds everything that modernises the game (EDGE, modern kicking and
overtime, acceleration, progression, arc by distance, the ESPN scorebug, scheme
labels, one-pool positions, the Far-look camera, the 2026 franchise);
**Experimental** adds widescreen hor+ (set xemu's Display aspect to 16x9) and the
dynamic-kickoff line-up. Untick anything you do not want, choose where the
patched **copy** goes, and Build. The original is never touched; a receipt is
written beside the copy. The **Share** tab turns that copy into a `.2k5patch`
file anyone can check and apply to their own image.

Modern overtime (in Advanced and Experimental) is the current NFL rule: a 10-minute
period (scaled from your quarter length), both teams get a possession unless the first
possession ends in a safety, a first-possession field goal or touchdown is answered by a
kickoff to the other team, and after both have possessed the next score wins; regular
season games can still end tied after one period, playoff games play on.

**TEAM column on the Player Card** (Gameplay group, in both Basic and Advanced): the
franchise Player Card's season-by-season stats gain a TEAM column next to Yr, showing
which team each season was played for. The current season shows the player's live
team; from the first season rollover after the patch is in the save, every completed
season shows the team the player finished it with. Past seasons of an OLD franchise
save show "--" until their next rollover (the game never stored a team per season;
the patch records one from then on), the folded "pre" row and the Total row also
read "--", and a player traded mid-season shows the season-end team. Saves stay
loadable with or without the patch. Unwitnessed in game so far: it is executed under
an emulator in the test suite, so please report what you see.

**Real team history** (Build tab, ADVANCED and EXPERIMENTAL; disc images only): the retail
roster already carries season-by-season stats for 1,325 players back to 1982, and the TEAM
column above can only learn teams from the seasons a patched disc plays. This toggle writes
the real club of those past seasons into the roster template from nflverse-data (CC-BY-4.0):
1,148 of the 1,325 players match by name and birth date and 5,068 of their 5,867 season rows
get a team (86 %; 1999-2003 about 85 %, the 1990s 80-90 %, sparse before 1990). Only a
franchise CREATED from the copy shows it - an existing save keeps its own roster - and each
row costs one dword of the game's 50,000-dword history pool (36,866 -> 41,908), so the game's
automatic folding of the oldest seasons into the "pre" row starts a little earlier. To use
your own data, point the "Team history CSV" field at a UTF-8 CSV with the columns
`last_name,first_name,birth_date,season,team` (birth date `YYYY-MM-DD`; `position` and
`roster_index` optional; team = a 2004 abbreviation such as `ARZ`, `STL`, `TEN` or an nflverse
code such as `RAI`, `RAM`, `PHX`, `HOU` for the Oilers up to 1996). Players are matched by
name and birth date, then last name and birth date, then name and position; a season is only
written when the roster has stats for it (the receipt lists every row that could not be used).
In this cut relocated franchises show the 2004 abbreviation (a 1990 Oilers season reads TEN).

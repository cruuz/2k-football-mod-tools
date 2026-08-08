# 2K5 Mod Studio — Product Changelog

This is the modder-facing record of functionality that is actually present in
runnable builds. A mapped resource is not listed as editable unless its product
writer is connected to Replace, Revert, project save/load, and the composed
build path.

## v1.0 RC54 — playbook host clone stubs, stadium import reasons, stretch fit, broken-play flags — 2026-08-07

### Community / product fixes

- **Import fit chooser** — off-size dialog/drop imports pick Contain, Cover, or Stretch (not silent auto-cover).
- **G1/G2 package-rule RE spike** — layout pins + o0308 fixture offsets in `playbook_package_rule_spike` (offline writer still not shipped).

- **Studio launch / Playbooks host** — `BrowseOnlyFacade` and `StudioFacade`
  expose formation/play clone methods so `PlaybooksPanelHost` isinstance checks
  pass (unblocks every headless Studio GUI test that constructs the main window).
- **Import edited stadium model never silent-gray** — export/import scene buttons
  always set tooltips for load-required, no-scene-selected, and same-topology
  contract when enabled.
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
- Post-seal Spark Hands QA passed on isolated `DISPLAY=:99`. A fresh
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
- The required new-layout visual inspection remains a separate root-session
  Spark Hands gate; no GUI or emulator was launched while assembling this
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
- Spark Hands inspected the RC6 Audio workspace on isolated `DISPLAY=:99`. The
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
- Spark Hands inspected the clean RC5 candidate on isolated `DISPLAY=:99`.
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
- Spark Hands checked the final Audio layout on isolated `DISPLAY=:99`. It
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
- Ran four current-code visual checks through Spark Hands on the isolated
  `DISPLAY=:99`: recovery/recent files, every Audio scope, the complete
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
- Headless Spark inspected xemu only on private Xvfb display `:99`. It saw the
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

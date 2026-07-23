# Phase 4 — integration and verification

Status: pending original-title integration. The native research shell is
verified, but neither recovered title state machine drives it yet.

## What works today

- The strict Linux build completes with SDL2, OpenGL 3.3, OpenAL, POSIX, PNG,
  and Assimp; all 45 CTest cases pass. `ctest -L gpu` selects 21 cases: 20
  GPU-labeled checks plus the swapped-logo fixture setup they require.
- A Clang 18 ASan+UBSan build passes all 25 non-GL-selected tests with leak
  detection. A clean install contains eight files total and excludes font7/TM,
  APF `player_shadow`, and every `assets/intermediate` file.
- The host launches a bounded menu, accepts keyboard/SDL game-controller
  navigation, initializes the audio and rendering seams, and can run hidden
  deterministic smoke frames.
- `assets/mod/common/ui/team_logo.png`, `models/player.gltf`, and
  `audio/menu_select.wav` are loaded as loose standard files. NFL font7 and TM
  overrides are optional loose files too; F5 transactionally reloads all five
  seams.
- NFL row labels have a bounded native bitmap-font path. Explicit
  `--nfl-font-atlas` / `--nfl-font-metrics` paths, matching environment
  variables, or a complete loose override pair can provide font7. Its parser
  validates 94 glyphs, 256×256 atlas dimensions, line advance 25, and space
  advance 9 before OpenGL receives any glyph quad.
- `--nfl-tm-icon`, `VC_NFL2K5_TM_ICON`, or `ui/nfl2k5_tm.png` supplies the
  exact index-40/slot-9 inline object. Its GPU comparison changes 638 pixels in
  row 2 and zero outside it; no retail icon is installed.
- `--model` / `VC_FOOTBALL_MODEL` directly selects any glTF/GLB while keeping
  relative external buffers intact. An automated recovered APF collection test
  loads two meshes, uploads six vertices/six indices, and captures a screenshot.
- Replacing the logo fixture changes the rendered screenshot hash. This is an
  automated loose-PNG swap proof, not merely a successful file conversion.
- A separate original-archive integration gate rebuilds APF outer 810
  `draft_logo` from PNG through touched-block BC3, Xenos tiling/endian routing,
  H7A, IFF metadata, and a copied `0A` volume. It preserves the source hash,
  exact bytes outside the entry, and all 158 unrelated decoded parts. This is
  an offline/copied-volume acceptance proof; the hidden draft screen is not
  yet shown in Xenia or hardware.
- Separate 60-frame native runs loaded and rendered an extracted NFL Cardinals
  logo, recovered NFL PCM audio, APF `glowball`, APF `hi_head`, and an NFL
  stadium `FLOAT3` glTF proof. A newer three-frame run loads the 143-shape,
  562-primitive recovered stadium collection, uploads 16,269 vertices and
  77,526 triangle indices, and captures a screenshot.
- The NFL exporter now covers every static shape: 46,192 `FLOAT3` plus 8,774
  instruction-proved `NORMSHORT3`. An automated native run loads the all-
  compressed `geometry_font` glTF and uploads 973 vertices/7,521 triangle
  indices, leaving only 609 genuinely zero-shape scenes withheld.
- Five mapped player/referee/coach meshes now carry standard raw-coordinate
  glTF skins with 125 named joints and 11,730 dense vertex influence records.
  An automated Assimp/OpenGL run accepts the player file's 111 primitives;
  the host evaluates its standard rest skin. These base files contain no
  animation; one separate referee derivative now carries a recovered clip.
- A redistributable one-joint glTF proves the host's standard CPU skinning and
  first-animation path numerically and through a 31-frame OpenGL smoke run.
  This independently verifies the generic destination format/runtime seam.
- The NFL player skin also has a separately validated meter-space derivative:
  right-handed XYZ/Y-up is retained and every position, joint translation,
  and inverse-bind translation is scaled from centimeters by exactly 0.01. A
  GPU smoke test loads it through the standard host skinning path.
- The first title-derived skeletal animation is canonical. Shipped
  `ANM_REF_PENALTY_DELAY_OF_GAME_R` expands 21 packed channels into 25 local
  referee rotations and bakes 357 keys at 120 Hz onto both high/low LODs (50
  target channels). The host imports 12 Assimp meshes, 300 bone records, 2,006
  weights, and one animation; all 1,375 vertices deform between 0 and 1.5
  seconds, with maximum `0.658806324 m` displacement. Strict GCC/Clang
  regeneration verifies the glTF, binary, and manifest, and a 91-frame GPU
  smoke writes `build/host-nfl-referee-animation.png`.
- APF's first exact shipped animation binding is now exported as a quantified
  derivative of a canonical static `SCNE/player_shadow` skin. The static file
  has 351 vertices, 306 triangles, 21 direct-order joints, exact one-hot
  influences, and proved inverse binds. Selector `(slot=1,index=2)` supplies
  `mnu_stn_01_070130_01_lg` to the separate animated file at 120 Hz. Assimp
  imports 175 deduplicated vertices, 918 indices, 21 bones, 181 weight records,
  and 18 animation channels; all 175 move at the two-second probe, with maximum
  `0.0449219383 m` displacement. Three-frame static and two-frame animated GPU
  tests plus a PNG crop test prove visible, differing host output.
  Normalized base position/heading/scale and finite glTF interpolation remain
  explicit representation boundaries rather than captured live frontend state.
- All 37,389 NFL SCNE embedded-texture occurrences are available through an
  exact-provenance catalog of 5,351 standard RGBA8 PNGs. The catalog retains
  all 55,905 material rows, but does not invent base-color, normal-map, UV, or
  sampler assignments that the recovered shader path has not proved.
- The host build remains redistributable: extracted proprietary assets stay in
  research/intermediate paths and are not installed as defaults. In particular,
  font7 PNG/metrics and both APF `player_shadow` files remain under
  `assets/intermediate`; `assets/mod/common` contains only the font override
  schema, not copied retail pixels or metrics.
- Original frontend state selection is now statically bounded. NFL descriptor
  `0x00515660` loads `main_menu_sub`, constructs seven navigation rows, and
  reaches activation/update/draw paths. APF descriptor `0x820F4350` loads
  `quicknav`/`template_quicknav`, constructs seven typed rows, and has a proved
  return-to-main callback. The closure trace recovers 12 fragmented boundaries
  and resolves 8 of 23 inherited blockers, including the type-3 apply/config
  route and eight main-descriptor routes. Fifteen address-specific `PORTME`s
  remain; the trace explicitly does not count as executing either state
  machine.
- The APF v5/v6 boot trace continues from XEX entry `0x84BE9D08` through the
  main loop and frontend bootstrap into registration of state ID `0x1F1A625A`
  with descriptor `0x82015330` (`TitlePage_Menu`). Its key-11 record statically
  binds callback `0x846E0528`, which constructs `StartupMenu` descriptor
  `0x820F4940`. This does not prove key 11's runtime meaning or invocation, a
  cold-boot construction of `Main Menu` descriptor `0x820F4350`, or ownership
  of the unowned Main tail wrapper at `0x84A56950`. Team Select dispatches Main
  as an exit-policy argument, but the callback only tests it for non-null.
- APF's backdrop asset identity and archive request are exact:
  `0x8467CA70 -> 0x8468DA70` requests `frontend_sync.iff`; outer 1493 has
  157 entries / 30 LAYTs, and inner 53 is seven-child `layout_mainmenu`, CRC
  `0x48C6D154`. Main's direct descriptor path selects `global.iff` 1310/57
  `quicknav`, disproving inner 53 for that path. All 161 decoded APF LAYTs
  contain no serialized owner reference; no separate runtime owner is claimed.
- The follow-on APF label trace proves all eight `template_quicknav` type-0
  option bindings reach content provider `0x846F5198` and orphan getter
  `0x846F3888`. Selected labels format as `{0}|M_PRIMARY|`; ordinary labels use
  bounded UTF-16 copy, bypassing localization on this exact US chain. APF's
  final font/glyph/atlas/GPU rendering is still open. Candidate `0x84A58698` is
  exactly End Of Game row 5 “Quit” preflight, not a cold-boot predecessor.
- `--menu nfl2k5` and `--menu apf2k8` render and navigate those exact seven-row
  models through the SDL seam. All guest VAs remain inert provenance, and row
  activation only logs guarded non-execution evidence. CPU tests cover every
  row/action field and wrap behavior; decoded PNG tests cover both seven-row
  layouts without treating them as original-title screenshots.
- NFL's portable row helper retains the exact three modes, wrap arithmetic,
  Z/W, and `(+8,-4)` text-origin offset. The live `+0xA7C` mode and projection
  are not proved, so these remain title-space values rather than Linux pixels.
  Separately, the current NVIDIA font7 GPU witness changes 11,170 pixels inside
  the seven host row-label bands and zero outside them when compared with the
  5×7 fallback.

## What does not work yet

- The selectable recovered-row views are native host representations, not the
  original NFL 2K5/APF 2K8 renderer or running state machine. Therefore “main
  menu displayed” is still not counted as original-game verification.
- Navigation is connected to the recovered row models at the SDL seam, but
  their guest actions, focus graphs, localization bindings, and title
  transitions are intentionally not executed.
- NFL font7 uses recovered metrics and pixels in a native host renderer. The
  57-record formatted-token table is exact, and `The Crib|TM|` now draws its
  proved slot-9 loose PNG; the current comparison changes only row 2. The
  other inline texture slots, original style/default-state path, and
  title-space projection remain address-specific `PORTME` work.
- No exhibition game, franchise flow, AI, rules engine, physics, animation
  graph, commentary system, or save path executes natively.
- Standard glTF node animation and CPU skinning execute, and one recovered NFL
  referee local-rotation clip and one recovered APF frontend clip drive
  separate derivative skins. NFL's 368 trajectory/controller path and final
  hierarchy/queue/palette/draw ownership are exact, but root translation is
  withheld because one concrete actor's initialization/live state remains
  unresolved; events are also omitted. APF's derivative uses normalized live
  instance inputs. Title animation graphs, morphs, shaders, samplers, and full
  material behavior remain disconnected.
- Referee gameplay ownership is instruction-exact for the namespace,
  controller, and skeletal family, but the concrete one-of-seven actor record
  and cutscene type-4 instance are unproved. Standard glTF slerp differs from
  the title's fixed-table/x87 path by at most `0.0507245908` degrees on 26,700
  observed probes; this is not a continuous or bit-exact bound. Player
  postprocessors `0x00092140` and `0x00093850` are now portable and tested at
  measured value-level tolerances. Shipped `ANM_CELEBRATE_USER_34` is now
  joined conditionally from selector row 2 and playback mode 1 through the
  player controller/gameplay frame into both `LO_res` and `HI_res` matrix
  paths, and the exact 62-joint HI_res static attachment passes Assimp/GPU
  validation. A player animation remains withheld because the concrete
  scoring-record type/classifier and resulting playback mode, live mutable
  profile selection, and concrete actor/root state remain unresolved; no
  defaults are invented for those live values.
- The scene PNGs are editable standard files. A narrow APF PNG-to-Xenos-BC3 /
  H7A/IFF/copy-volume writer now round-trips hidden `draft_logo` exactly and
  preserves 158 unrelated parts, but its dormant screen has no proved retail
  route. A copied game carrying that replacement boots in Xenia Canary through
  the real title screen and 3D attract loop, proving archive acceptance but not
  target visibility. A second writer now regenerates all nine Xenos mip levels
  for the Americans' live-selected `jersey_color`, including packed levels
  6–8, and passes exact copied-volume validation. A matched Xenia capture at
  the actual Americans Home Jersey editor proves that the untouched navy/red
  target becomes visibly pink/magenta through this rebuilt archive path.
  A subsequent asymmetric red/cyan source produces a large white/red spatial
  response, proving channel-weight/material-mask semantics rather than a
  conventional diffuse RGBA interpretation. Rebuilding the identical RGB with
  all 1,048,576 alpha bytes zero leaves the jersey visibly opaque and closely
  matched, so conventional straight-alpha opacity does not control the target;
  this does not prove that the shader never reads alpha. Exact full-pattern UV
  orientation, fine detail, distant-mip behavior, Xbox 360 hardware parity,
  and a production-quality BC3 compressor remain open. All 24 jersey
  packages now independently share that exact layout and pass a controlled
  in-memory fixed-allocation rebuild. The copy-only CLI now exposes all 24 with
  per-entry hashes and refuses arbitrary detailed art that exceeds a package
  allocation. All three writer front ends additionally pass a 25-case
  descriptor/inode ownership gate covering path aliases and live pathname
  replacement; see `docs/research/apf_writer_path_safety.md`. NFL now also has
  a copy-only fixed-size `Unif` color writer and a validated create/list/extract
  XISO round trip for the Lions' current home/away packages, plus a second
  sector-identical XISO writer whose full-image gate changes exactly ten bytes.
  The earlier title-return frames are no longer classified as resets because
  untouched retail reproduces them. A layout-identical three-byte donor image
  now reaches rendered Demo Mode gameplay in isolated xemu, proving acceptance
  of that exact modified disc. A focus-verified Demo-to-Main route is frozen.
  The exact Xbox controller GUID and START/A/START timing now also reach Team
  Select deterministically. Static ownership proves the
  edited word reaches conditional `HI_turtleneck`, not the jersey torso. No NFL
  xemu-visible swap is yet claimed. A complete shipped
  Falcons-AWAY `jersey00` / `jersey00_mud` TSET donor now also boots from the
  Lions-current-HOME slot. The deterministic route reaches Jaguars at Lions
  Current Uniform; ten preview samples retain the retail Lions torso and never
  show the donor pattern, falsifying the assumed Team Select binding. A
  deterministic VC-LZ encoder now reproduces eight
  representative retail streams exactly and supports fail-closed fixed-span
  rebuilding. The first bounded P8 writer now imports a strict 512×256 RGBA
  PNG into all six swizzled mips and separate clean/mud palettes, independently
  verifies the fixed 74,720-byte TSET, and losslessly encodes the 32-color
  `CODEX MOD` fixture. A full-image-verified, layout-identical XISO now carries
  that exact span with 70,333 changed bytes confined to it; all filesystem
  extents, `default.xbe`, pack 0, and unrelated bytes remain exact, and all 12
  decoded mip previews reverify after extraction. The same bounded target has
  a user-facing arbitrary-PNG workflow with a distinct noncanonical full-XISO
  proof and adversarial provenance/path/overflow tests. A complete 634-package
  audit now proves all 317 HOME/AWAY pairs use the supported chunk-1 P8 layout;
  a generalized code/side/variant workflow preserves every target's exact
  allocation and has independent `00H0`, `27A0`, and smallest-allocation
  `30H2` fixtures plus a full-XISO `27A0` proof. The legacy HOME and AWAY
  `CODEX MOD` captures remain negative controls, but the recovered TSET loader
  proves both recompressed streams overwrite unread input under its in-place
  decode because their retail `+0x14` scratch values are too small. The v3
  writer computes the exact alias requirement and raises that wrapper word
  while preserving the fixed on-disc span. A corrected `09A0` XISO passes the
  independent workflow/alias checks and visibly renders the injected
  magenta/cyan/green texture on Detroit's live coin-toss players. All 13 Team
  Select controls remain retail-looking; the follow-up compiled-owner/image
  audit resolves that menu to standalone 256×256 `unif_*`/`helm_*` cards
  dynamically bound to flat SCNE planes. This resolves live `jersey00` ->
  `UNIF_jersey` ownership for current AWAY and the distinct menu-preview owner.
  The separate card pipeline now audits all 1,902 formatter resources, imports
  both raw P8 allocation classes, and independently verifies a 131,816-byte
  two-card copy-only XISO delta. See
  `docs/research/nfl_team_select_card_pipeline.md` and validate with
  `bash tools/validate_nfl_team_select_card_pipeline.sh`; no edited-card
  runtime visibility is claimed.
  The separate created-team field-art lane now closes 126 concrete
  `ct{logo}{D|R|S}.iff` packages and 1,134 live-field P8 TXTRs. A synthetic
  `ct67D` north-middle end-zone replacement passes deterministic all-mip
  import, fixed-span VC-LZ alias checks, a copy-only XISO build, and an
  independent full-image verifier: exactly 38,156 target bytes change while
  the XDVDFS tree and `default.xbe` remain exact. See
  `docs/research/nfl_create_team_field_art_pipeline.md` and validate with
  `bash tools/validate_nfl_create_team_field_art_pipeline.sh`; xemu was not
  started, runtime visibility is false, and stock-stadium signs are not yet a
  supported selector family.
  A companion team-identity audit now separates the two art domains and joins
  them to the main ROST table: 85 team `+0x10c` uniform/card codes, 80 XBE
  color records, 42 stadium-selected field-art codes, and 52 main team rows.
  A same-size `Detroit Lions` -> `Codexia Codex` copied-disc proof changes only
  17 bytes within four UTF-16LE strings; the two-digit code `09`, complete team
  record/roster, `default.xbe`, and XDVDFS tree remain exact. See
  `docs/research/nfl_team_identity_modding.md` and validate with
  `bash tools/validate_nfl_team_identity_audit.sh`; save ownership and runtime
  visibility remain open.
  The companion player audit now proves a second data edit directly in the
  main disc ROST. The 2,547 fixed `0x54` records expose executable-backed
  name pointers, membership, face/head ID, jersey number, and position; 204
  exact rating UI bindings conditionally name only three stable raw fields for
  positions whose dispatch proves each label. The copied
  `Joey Harrington #3 QB` -> `Noah CodexProof #42 QB` XISO differs at exactly
  14 bytes, with Detroit slot 35/count 53, face 3593, position 0, all pointers,
  unrelated fields, `default.xbe`, and XDVDFS extents identical. See
  `docs/research/nfl_player_roster_modding.md` and validate with
  `bash tools/validate_nfl_player_roster_audit.sh`; it is a disc-seed proof,
  not a save-container or runtime claim.
  The actual live 3D helmet resources are now independently closed rather than
  conflated with those cards. Player modes 0/1 bind uniform-package
  `helmet00`/`helmet02` to the A/C player helmet materials. All 1,268 resources
  pass one-layout, fixed-span VC-LZ, in-place alias, and retail-XISO checks. A
  two-edit Detroit-away proof XISO changes exactly 71,407 bytes inside the two
  target spans while preserving the complete XDVDFS tree and `default.xbe`.
  See `docs/research/nfl_live_helmet_txtr_compatibility.md` and validate with
  `bash tools/validate_nfl_live_helmet_txtr_compatibility.sh`; no live helmet
  replacement visibility is claimed.
  All-634 sleeve and pants copy-only pipelines also pass offline verification,
  and the separately traced live-number/nameplate lane now covers 19,654 pixel
  TXTRs across every selector. A four-edit Detroit copied XISO changes exactly
  12,084 bytes inside jersey, helmet, arm-digit, and name-atlas spans while
  preserving the complete XDVDFS tree and XBE. The name metrics remain
  read-only and none of these new fixtures has a runtime capture. No
  post-coin-toss gameplay frame or live sleeve/pants/number/nameplate capture
  exists; equipment, models, hardware parity, and general APF texture variants
  remain open. See `docs/research/nfl_live_numbers_nameplate_pipeline.md` and
  validate with `bash tools/validate_nfl_live_numbers_nameplate_pipeline.sh`.
  Live player face/head textures are also offline-writable for all 624 matched
  IDs: 1,872 `f/h/n` DXT1 textures are proved and SHAP `s` geometry remains
  read-only. The three-edit `0124:f/h/n` proof changes 97,048 bytes with every
  non-target byte exact. Fixed-size team identity is now part of the same v1
  project alongside fixed-size primary-player names/jersey number and numeric
  roster portraits, without exposing raw offsets, membership/stadium pointers,
  guessed ratings, colors, relocation, or executable patch bytes. The eleven
  completed NFL visual/data lanes pass one combined copy-only build: 13 project
  edits expand to 19 non-overlapping physical spans, 428,469 changed bytes, one
  final XISO, no intermediate discs, identical XDVDFS/default.xbe, and an
  independent verifier that reruns the pinned proof logic instead of trusting
  the build report. Portrait `4070` proves the pack-3/pack-4 split. The nine-
  and six-family v1 proofs still verify unchanged. See
  `docs/research/nfl2k5_unified_visual_mod_project.md` and
  `bash tools/validate_nfl2k5_visual_mod_project.sh`; no combined runtime
  visibility is claimed.
- The solid-magenta Americans copied archive boots under a clean Xenia run,
  and matched untouched/patched runs reach the actual Americans Home Jersey
  editor. In a fixed 25,800-pixel torso crop, pink-threshold pixels rise from
  98 to 8,969 while navy-threshold pixels fall from 15,400 to 341. This proves
  outer 875 / `uniform_jersey_06` / `jersey_color` runtime binding and visible
  solid-color replacement. The asymmetric and alpha-zero followups prove the
  material-mask response and rule out conventional alpha opacity, respectively.
  They do not yet prove exact detailed-art UVs, lower-mip fidelity, that alpha
  is wholly ignored, or Xbox 360 hardware parity.
- Roster and localization parsers are read-only research interfaces. The host
  does not yet offer a safe editor or size-changing archive import.
- A logo swap is visible in the host fixture. It is not yet routed through an
  original recovered team/uniform/material selection path.
- APF cold boot is proved through initial title registration, a static
  TitlePage action-to-StartupMenu edge, and the executable
  `frontend_sync.iff` request. A genuine TitlePage/StartupMenu-to-Main
  construction, live key-11 dispatch, and any separate runtime owner of
  `layout_mainmenu` remain unproved; Main itself directly selects `quicknav`.
- The isolated APF static-recomp harness now maps the exact guest image,
  installs all 60,731 generated mappings and 30 typed import bridges, and
  proves the first boundary at `RtlImageXexHeaderField` with no opcode,
  switch-tail, or unresolved-indirect residue before it. The composed corpus
  and exhaustive instruction-budget derivative now pass independently, and a
  contained child executes `_xstart` for exactly 38 guest instructions before
  the typed bridge stops at that boundary. No continuation, signal, timeout,
  import abort, boot, or menu is claimed.
- The next contained startup checkpoint executes the statically matched
  226-instruction continuation (264 cumulative), reaches the expected 1 MiB
  virtual-memory request, and verifies the Linux adapter's result before
  stopping at the following translated instruction. This is still startup
  compatibility only, not a native launch.
- A reversible Xenia PatchDB write at `0x84E55F10` redirecting Season's old
  Gameplan descriptor to retained Coach's Desk is confirmed loaded and
  boot-safe through the real title screen. Mandatory first-run team creation
  blocked both control and patched runs before Season, so the pointer effect is
  not classified as a menu, no-op, or crash.

## Required evidence before Phase 4 can pass

1. Complete the now-bounded boot/frontend traces: prove NFL cold boot, connect
   APF TitlePage/StartupMenu to a genuine Main construction, identify a
   separate runtime owner for `layout_mainmenu` or prove it unused, recover
   APF's final font/glyph/atlas/render-queue route after the now-proved label
   provider, and extend the guarded static runtime one exact boundary at a time
   without bypassing its fail-closed instruction/import gates.
2. Connect the recovered `LAYT` ownership/event graph to native rendering and
   SDL input without inventing field semantics.
3. Recover material/texture assignment far enough that a roster-selected team
   reaches a loose logo and uniform override through original title state.
4. Connect title audio events to the verified PCM/OpenAL seam, preserving
   variants, loops, mixer priority, and bank ownership where applicable.
5. Add deterministic integration tests for original menu launch, keyboard and
   gamepad navigation, F5 asset reload, and a visible team-logo replacement.
6. Retain an address-specific `PORTME` for every guest operation skipped by the
   native path.

## Current verification command

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DVC_PORT_STRICT=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Current result: `100% tests passed, 0 tests failed out of 47`. This verifies the
Linux scaffold and mod boundary only. Phase 4 remains open until the original
title-state conditions above are met.

```c
// PORTME: recovered original boot/frontend state is not linked.
// PORTME: NFL cold boot and APF TitlePage/StartupMenu-to-Main remain unproved.
// PORTME(0x48C6D154/0x846EFD38): Main directly selects quicknav; recover a
// separate layout_mainmenu runtime owner or prove inner 53 unused.
// PORTME: LAYT event/focus/localization semantics are not complete.
// PORTME(0x000EEDB0): bind the remaining NFL inline texture slots and original
// NV2A state; |TM| index 40 / slot 9 is now exact in the host view.
// PORTME(0x0014FB7A/0x0014FF21): prove NFL live row mode and title-space
// projection before using recovered coordinates as pixels.
// PORTME: original team -> uniform/material -> loose asset binding is not wired.
// PORTME: original audio event/bank/mixer behavior is not connected.
// PORTME: host-row representation tests exist; original-menu execution tests do not.
```

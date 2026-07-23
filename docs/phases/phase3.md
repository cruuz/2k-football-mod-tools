# Phase 3 — Linux port scaffold

Status: scaffold complete and verified; recovered title logic is not connected.

## What worked

- CMake builds a native Linux x86_64 executable from `src/` and `include/`.
- SDL2 supplies the OpenGL 3.3 core window, keyboard input, Xbox-style gamepad
  mapping, controller hotplug, timing, and the host thread seam.
- OpenGL renders a deterministic research menu and loose PNG texture.
- OpenAL initializes as the 3D-audio seam, loads mono/stereo PCM8/PCM16 loose
  WAV clips, and degrades to muted operation when no device exists.
- POSIX-backed file, memory, and timing wrappers are present in
  `src/platform/xdk_linux.c` and `include/xdk/xdk_linux.h`.
- Assimp validates glTF 2.0, and the OpenGL path uploads all bounded triangle
  meshes into a static fitted preview. The default fixture is deliberately
  redistributable rather than extracted game content.
- `--model PATH` and `VC_FOOTBALL_MODEL` select any glTF/GLB directly while F5
  keeps reloading that exact path. This lets Blender output and derived scene
  collections retain their relative external buffers without copying them
  into the default asset tree.
- `--model-only` renders an explicitly selected model full-frame for bounded
  evidence/inspection captures; the CLI rejects it when no `--model` or
  `VC_FOOTBALL_MODEL` is supplied.
- `assets/mod/common/ui/team_logo.png` is loaded from the loose asset tree and
  hot-reloads after an atomic replacement. The executable also accepts a
  different tree through `--assets` or `VC_FOOTBALL_ASSETS`.
- Installed builds resolve their packaged asset directory relative to
  `/proc/self/exe`, while development builds retain explicit overrides.
- CLI parsing, PNG allocation bounds, PNG transparency/interlace handling,
  OpenGL error propagation, screenshot failures, controller deduplication, and
  cleanup paths were hardened under strict GCC 13 and Clang 18 builds.
- Xbox/XDK or recovered-engine behavior that is not implemented is marked
  `PORTME`; the host shell does not present itself as either original game.
- The first manually confirmed cross-title semantic function is compiled from
  `src/recovered/shared/side_label.c` and tested across its complete decision
  table.
- `--menu host|nfl2k5|apf2k8` selects either the unchanged native shell or a
  typed host representation of the seven statically recovered title rows.
  Source/label addresses, action types, targets, handler chains, callbacks,
  and layout identity remain inert `uint32_t` evidence. Recovered activation
  logs `HOST VIEW ONLY ... NOT EXECUTED`; no guest address is cast or called.
- NFL's original row drawer is now proved to select FONT slot 6, `font7`. The
  native host can load its 256×256 RGBA atlas and all 94 recovered glyph
  metrics from explicit loose paths and uses them only for NFL row labels.
  Missing or rejected files retain the bounded 5×7 host fallback.
- The title-derived font7 PNG/metrics remain under `assets/intermediate` and
  are not copied into the installed mod tree. `assets/mod/common/ui` contains
  only user-owned font/TM override schemas; a modder supplies the loose files.
- NFL's exact 57-record formatted-token table is compiled and tested. The
  visible `|TM|` maps case-insensitively to index 40, texture slot 9, and a
  full-UV square; its optional loose PNG hot-reloads and changes only row 2 in
  the GPU comparison. The other 12 inline texture resources remain unbound.
- The NFL row-coordinate arithmetic is compiled separately as an exact
  three-mode, value-level helper. It returns title-space coordinates and takes
  the still-unproved live mode explicitly; the host does not mislabel those
  values as framebuffer pixels.
- Read-only APF v5/v6 traces reach `TitlePage_Menu`, prove its static route to
  `StartupMenu`, and prove bootstrap requests `frontend_sync.iff`. Team Select
  dispatches Main as an exit-policy argument, but that callback does not
  construct Main. Main's direct LAYT is exactly `global.iff` `quicknav`, not
  `layout_mainmenu`; no separate inner-53 runtime owner is proved.
- APF `SCNE/player_shadow` now has a canonical 21-joint static glTF skin and a
  separately bounded animated derivative. Both reach the existing
  Assimp/CPU-skin/OpenGL preview through explicit `--model` paths; neither is
  presented as a live original frontend instance.
- NFL now has a bounded copy-only archive/repackage seam. The writer changes
  only the two proved raw `Unif` color words in Detroit's current home and away
  packages, uses independent inode-bound copies of packs `A`/`B`, and builds a
  new XISO with extract-xiso's automatic XBE media patch disabled. Listing and
  full re-extraction preserve all 17 unrelated files and `default.xbe`
  byte-exact while all four magenta words reparse. This proves fixed-size data
  modification and XISO repacking, not PNG/TSET/TXTR or model replacement.
  The first Quick Game probes were initially misclassified as resets. A fresh
  untouched-retail audit reproduced the same title/attract flow; those frames
  do not establish archive rejection or a filesystem-layout defect. A second
  copy-only writer preserves the retail root sector and every original XDVDFS
  LBA/extent; a full-image comparison proves exactly ten changed bytes. A
  separate three-byte retail-donor copy now reaches rendered Demo Mode gameplay
  in isolated xemu, proving runtime acceptance for that exact modified image.
  Its focus-audited route reaches Main Menu deterministically but not yet Team
  Select, and static ownership identifies the edited field as conditional
  `HI_turtleneck`, not jersey diffuse; visible binding remains open. See
  `docs/research/nfl_uniform_color_xiso.md` and
  `docs/research/nfl_uniform_color_xiso_direct.md`, plus
  `docs/research/nfl_uniform_xemu_runtime.md`; validate with
  `bash tools/validate_nfl_uniform_color_xiso.sh` and
  `bash tools/validate_nfl_uniform_color_xiso_direct.sh`, then
  `bash tools/validate_nfl_uniform_xemu_runtime.sh`. A third layout-identical
  writer copies the complete equal-sized Falcons-AWAY `jersey00` /
  `jersey00_mud` TSET into Lions current HOME without recompression. Its
  73,304-byte-difference XISO now reaches a deterministic Jaguars-at-Lions
  Current Uniform screen. Ten animated preview samples keep the retail Lions
  torso and never show the Falcons-away donor pattern, falsifying the assumed
  Team Select binding. See `docs/research/nfl_jersey_tset_xemu_runtime.md`;
  validate with `bash tools/validate_nfl_jersey_tset_xemu_runtime.sh`. The
  formerly missing write-side compression step is now bounded and tested:
  `tools/nfl_txtr.py` reproduces eight representative retail VC-LZ streams
  byte-for-byte and fails closed when a recompressed body cannot fit its fixed
  span. A first real importer accepts strict 512×256 RGBA PNG, generates six
  mips, deterministically quantizes one shared Xbox P8 index chain, inverse
  swizzles every mip, derives separate clean/mud palettes, and emits a fully
  reparsed fixed-size `09H0` TSET. The 32-color `CODEX MOD` fixture is lossless
  and compresses to 22,285/74,688 bytes. A copy-only direct writer now inserts
  that span into a layout-identical XISO: the full-image gate finds 70,333
  changed bytes in 3,265 runs entirely inside the target span, while the root
  sector, all XDVDFS paths/LBAs/extents/sizes, `default.xbe`, pack 0, and every
  unrelated byte remain exact. Re-extraction reproduces all six clean and six
  mud previews. A user-facing copy-only orchestrator accepts any strict
  512×256 RGBA8 PNG for the original Detroit target, dynamically validates the
  resulting manifest/span instead of pinning the diagnostic art, and commits
  the XISO only after independent reconstruction and path-ownership checks. A
  complete follow-up audit covers all 634 HOME/AWAY jersey chunk-1 packages /
  317 pairs: every span matches its retail-XISO location and all share one
  supported P8 six-mip layout. The generalized selector workflow derives code,
  side, variant, pack, and exact XISO offset from pinned evidence while
  enforcing each target's one of 346 fixed VC-LZ allocations (31,872–126,704
  bytes). Fixtures cover `00H0`, `27A0`, and smallest-allocation `30H2`; an
  independent full `27A0` XISO proof confines all 73,127 changed bytes to that
  span. Forged manifests, incompressible overflow, symlinks, path swaps,
  incompatible mud art, and existing outputs are rejected. The exact
  The two legacy `CODEX MOD` XISOs boot through deterministic Team Select and
  game routes but retain retail-looking art. The recovered
  `0x451D0 -> 0x45280 -> 0x45100` TSET loader explains those negatives: it
  reads the fixed compressed body into the tail of a shared allocation and
  decompresses forward in place, while the PNG rebuilds retained only 32-byte
  HOME / 16-byte AWAY overlap scratch. Exact alias simulation requires 52,392
  / 56,792 bytes, respectively. The v3 writer now raises only wrapper `+0x14`
  to aligned 52,416 / 56,816 values and independently proves collision-free
  decode while preserving each fixed on-disc span. A corrected `09A0` AWAY
  XISO (`5e8cf7c...`) reaches Lions at Giants on Current Uniform. Thirteen Team
  Select samples remain retail-looking, but the injected magenta/cyan/green
  texture is plainly visible on Detroit's live coin-toss player models. This
  proves `09A0` chunk 1 controls the current-AWAY live jersey and resolves the
  static/runtime contradiction for live players. Team Select is now resolved
  separately to standalone 256×256 `unif_*`/`helm_*` pre-rendered cards bound
  to flat SCNE materials, with no dependency on the live `09A0` TSET. A
  follow-on audit now covers all 1,902 concrete cards and both raw P8 fixed
  layouts. The strict importer and copy-only verifier carry non-retail
  Detroit-away `unif_a09_0` / `helm_a09_0` fixtures into a frozen XISO with
  exactly 131,816 changed bytes and every XDVDFS extent preserved; replacement
  visibility remains untested. The actual live 3D helmet path is now closed
  separately: XBE modes 0/1 bind uniform-package `helmet00`/`helmet02` to the
  A/C helmet geometry materials. All 1,268 resources share one 256×256 P8
  six-mip layout across 367 fixed allocation classes. A two-edit Detroit-away
  copied-XISO proof changes exactly 71,407 bytes inside the selected spans and
  preserves every filesystem extent and `default.xbe`; no runtime visibility
  is claimed. The
  nested session ended after coin toss, so no post-coin-toss gameplay
  visibility is claimed. Independent all-634 sleeve and pants PNG/XISO
  pipelines now pass offline fixed-span and loader-alias validation; their
  runtime visibility, equipment/models, and original-hardware parity remain
  unresolved. Live player-number and generated-nameplate art is also closed
  offline: all 19,020 jersey/helmet/arm glyphs and all 634 `names` atlases have
  exact selector/XISO mappings, all-mip PNG import, fixed-span VC-LZ guards,
  and an independently verified four-edit Detroit copied-XISO proof. The
  separate 634 `NAME` metric objects remain byte-exact/read-only because one
  glyph index and metric word 0's physical unit are still unproved; runtime
  visibility of the new art is not claimed.
  A unified v1 project/orchestrator now composes torso, sleeve, pants, live
  helmet, digit/nameplate, Team Select, live face/head `f/h/n`, and create-team
  field art plus fixed-size team identity, fixed-size primary-player
  name/jersey, and numeric roster portraits into one retail-derived XISO copy.
  Its retained eleven-family proof expands 13 project edits to 19
  non-overlapping physical spans and changes 428,469 bytes, preserves the full
  XDVDFS tree and `default.xbe`, and independently rebuilds every expected
  span. Portrait `4070` deliberately crosses packs 3 and 4. SHAP is explicitly
  rejected/read-only; the public schema cannot supply raw offsets, pointers,
  guessed ratings, XBE colors, allocation/relocation, or executable/gameplay
  patch bytes. The nine- and six-family v1 proofs still verify unchanged, so
  no migration is required.
  It creates no per-family intermediate discs and makes no runtime claim. See
  `docs/research/nfl2k5_unified_visual_mod_project.md` and validate with
  `bash tools/validate_nfl2k5_visual_mod_project.sh`.
  See `docs/research/nfl_vc_lz_compressor.md` and
  `docs/research/nfl_tset_png_import.md` plus
  `docs/research/nfl_tset_png_import_xiso_direct.md` and
  `docs/research/nfl2k5_jersey_png_workflow.md` and
  `docs/research/nfl_jersey_tset_compatibility.md`, plus
  `docs/research/nfl_lions_png_import_xemu_runtime.md` and
  `docs/research/nfl_actual_jersey_binding.md`,
  `docs/research/nfl_actual_jersey_binding_away_xemu_runtime.md`,
  `docs/research/nfl_tset_loader_alias_audit.md`, and
  `docs/research/nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.md`,
  plus `docs/research/nfl_team_select_preview_owner.md` and
  `docs/research/nfl_team_select_card_pipeline.md`,
  `docs/research/nfl_sleeve_tset_compatibility.md`, and
  `docs/research/nfl_pants_tset_compatibility.md`,
  `docs/research/nfl_live_helmet_txtr_compatibility.md`,
  `docs/research/nfl_live_numbers_nameplate_pipeline.md`,
  `docs/research/nfl_live_face_texture_compatibility.md`, and
  `docs/research/nfl_create_team_field_art_pipeline.md`;
  validate with
  `bash tools/validate_nfl_vc_lz_compressor.sh` and
  `bash tools/validate_nfl_tset_png_import.sh` plus
  `bash tools/validate_nfl_tset_png_import_xiso_direct.sh`,
  `bash tools/validate_nfl2k5_jersey_png_workflow.sh`, and
  `bash tools/validate_nfl_jersey_tset_compatibility.sh`, plus
  `bash tools/validate_nfl_jersey_tset_xemu_runtime.sh` and
  `bash tools/validate_nfl_actual_jersey_binding.sh`,
  `bash tools/validate_nfl_actual_jersey_binding_away_xemu_runtime.sh`,
  `bash tools/validate_nfl_tset_loader_alias_audit.sh`, and
  `bash tools/validate_nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.sh`,
  plus `bash tools/validate_nfl_team_select_preview_owner.sh` and
  `bash tools/validate_nfl_team_select_card_pipeline.sh`,
  `bash tools/validate_nfl_sleeve_tset_compatibility.sh`, and
  `bash tools/validate_nfl_pants_tset_compatibility.sh`,
  `bash tools/validate_nfl_live_helmet_txtr_compatibility.sh`, and
  `bash tools/validate_nfl_live_numbers_nameplate_pipeline.sh`.
- The first original-archive write seam is now proved for APF outer 810,
  `franchise.iff` / `draft_logo`: PNG-to-touched-block BC3, inverse Xenos
  tile/endian routing, H7A compression, IFF rebuild/footer relocation, and a
  copy-only 1.1 GB `0A` replacement all validate. The source volume remains
  hash-identical and all 158 unrelated inner parts remain exact. This narrow
  writer does not imply that the dormant draft screen is reachable. The
  Americans' live-selected outer-875 `jersey_color` now has its own copy-only
  writer with an exact nine-level layout, including the shared packed tail;
  all levels reinsert bit-exactly and a controlled edit decodes back exactly.
  The fixed-allocation copied-volume proof passes, while Xbox 360 hardware
  validation and production-quality BC3 compression remain open. A read-only
  family audit further proves the same descriptor and exact nine-level
  transport across all 24 jersey packages; controlled solid-color in-memory
  rebuilds fit every allocation. A separate all-24 copy-only CLI now adds
  per-entry hashes and preserves the fixed-allocation refusal for arbitrary
  art; representative targets 6, 14, and 23 reparse, and target 23 passes a
  full copied-volume round trip. See
  `docs/research/apf_texture_roundtrip.md` and
  `docs/research/apf_uniform_mip_roundtrip.md` plus
  `docs/research/apf_jersey_family_layout.md` and
  `docs/research/apf_jersey_family_patch.md`, with exclusive-output ownership
  in `docs/research/apf_writer_path_safety.md`; run
  `bash tools/validate_apf_writer_path_safety.sh` plus
  `bash tools/validate_apf_texture_patch.sh` and
  `bash tools/validate_apf_uniform_mip_patch.sh` plus
  `bash tools/validate_apf_jersey_family_layout.sh` and
  `bash tools/validate_apf_jersey_family_patch.sh`.
  The solid-magenta Americans copied archive also has a matched Xenia proof at
  the actual Americans Home Jersey editor. The untouched retail jersey is
  navy/red while the patched copy is visibly pink/magenta in the same bounded
  torso crop, proving that outer 875 / `jersey_color` controls the live 3D
  target. The earlier white onboarding preview remains a useful non-target
  negative control. A red/cyan asymmetric source then produces a spatially
  varying white/red response, identifying this resource as a
  channel-weight/material mask rather than conventional diffuse RGBA. An
  RGB-identical source with all 1,048,576 alpha bytes zero remains visibly
  opaque and closely matches that response, ruling out conventional
  straight-alpha opacity for this target without claiming the shader never
  reads alpha. Exact full-pattern UV orientation, fine detail, distant mips,
  and Xbox 360 hardware parity remain open. Validate with
  `bash tools/validate_apf_uniform_xenia_runtime.sh`,
  `bash tools/validate_apf_uniform_pattern_xenia_runtime.sh`, and
  `bash tools/validate_apf_uniform_pattern_alpha0_xenia_runtime.sh`.

## Verification

The audited scaffold passes all 46 CTest cases:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DVC_PORT_STRICT=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

`ctest -L gpu` selects 21 cases: 20 GPU-labeled checks plus the required
swapped-logo fixture setup. They use an NVIDIA RTX 2080 Ti and an OpenGL 3.3
context and cover the default/swapped loose-logo views, both recovered-row host
representations, font7 row labels, semantic PNG geometry, recovered APF/NFL
collections, and APF `player_shadow` static/animated witnesses.
The separate Clang 18 AddressSanitizer/UndefinedBehaviorSanitizer build disables
GL tests and passes all 25 selected cases with leak detection and halt-on-error
enabled. A clean-prefix install audit enumerates only the executable and seven
redistributable/user-created mod files; no font7/TM pixels, APF
`player_shadow`, or `assets/intermediate` file is installed.
Representative 1280×720 outputs include:

- `build/host-menu-default.png`
- `build/host-menu-swapped.png`
- `build/host-menu-nfl2k5.png`
- `build/host-menu-nfl-font7.png`
- `build/host-menu-apf2k8.png`
- `build/host-nfl-stadium-collection.png`
- `build/host-nfl-geometry-font.png`
- `build/host-nfl-raw-skin.png`
- `build/host-nfl-meter-skin.png`
- `build/host-animated-skin.png`
- `build/host-nfl-referee-animation.png`
- `build/host-apf-player-shadow-static.png`
- `build/host-apf-player-shadow-animated.png`

A separate non-GPU native-code test covers APF's recovered mode-0 packed-pose
decoder, including all 16 selector-nibble behaviors, signed 20-bit extraction,
unit reconstruction, invalid-radicand rejection, and exact mirror sign-bit
changes on numbered lanes 2/3. The research validator additionally compares
the C implementation against all 155,642 supplied records.

A companion APF native-code test covers the recovered mode-1 translation
unit: big-endian signed-20 extraction, exact `1/1024` stored-point scale,
positive-zero lane 3, numbered-lane-0 mirror, interpolation, invalid arguments,
and the explicit non-Xenon-bit-exact capability flag. Its research gate audits
all 40,434 shipped mode-1 records and the exact 21-row `player_shadow` binding.

A second non-GPU native-code test covers NFL 2K5's little-endian signed-10
smallest-three decoder: all four omitted-component placements, exact f32 scale,
negative-radicand rejection, and mirror sign bits on numbered lanes 2/3. Its
research validator batch-compares the native module with all 14,073,985 main
and 17,311 optional shipped records while withholding an unproved original-x87
bit-identity claim.

A third recovered-code test covers NFL's six/eight-byte trajectory records,
exact one-eighth scaling, optional fourth shifted integer, invalid-stride
handling, and instruction-proved mirror changes. Its archive gate compares all
567,075 records; the follow-on trace now names them X/Y/Z centimeters and the
fourth value as a +Y turn without changing the decoder's stored-lane API.

A fourth recovered-code test covers NFL's packed motion-event tick/ID split,
terminator, invalid time-scale handling, and portable seconds conversion. Its
archive gate validates all 9,024 events and 6,068 stream terminators while
withholding unproved event names and callback meanings.

A fifth recovered-code test covers NFL's exact fixed-table quaternion
interpolation topology, including shortest-path sign handling, both sides of
the strict threshold, negative/high extrapolation, input/output aliasing, and
the explicit non-bit-exact capability flag. The research gate additionally
checks 65,546 deterministic vectors and all 65,536 table angles.

A sixth recovered-code test composes NFL frame addressing, signed channel-map
selection, packed-pose decode, the exact interpolator, mirror sign changes,
and final-frame clamp. Its full archive gate checks three samples from every
one of 6,068 roots (18,204 total), then checks the actual title flags on all
roots. Eight looping clips reproduce
the controller's repeated-duration subtraction and 696 roots select mirror;
pose-to-local-matrix application remains explicit `PORTME` work; the concrete
player root-motion path is now separately proved.

A seventh recovered-code test compiles the bounded portable implementation of
NFL player current-matrix postprocessor `0x00093850` under the selected strict
GCC/Clang toolchain and checks masks, low/high axial scaling, pivot retention,
the conditional matrix-12 scale, and fail-before-mutation validation. The
separate research gate compiles it with both GCC and Clang and runs an
independent 116-case oracle using the four original-XBE profiles, the exact
62-byte high-to-low schedule, and recovered SKEL axes. It establishes bounded
value-level portability; Xbox rsqrt/x87 bit identity and human-facing names for
context fields `+0x18`/`+0x2a` remain `PORTME`.

An additional recovered-code test compiles the complete player local-matrix
postprocessor `0x00092140`. Its research gate preserves all 127 ordered call
sites and the exact 25-to-62 matrix mapping, compares eight poses against an
independent graph (`0.000234525141` maximum error), and optionally executes the
original XBE function in Unicorn against GCC/Clang
(`0.000234564883` maximum error). This is value-equivalent, not an Xbox
rsqrt/x87 bit-identity claim.

An eighth recovered-code test covers the active NFL coach/referee local-pose
path: 21 packed channels pass through the exact signed map, both arm twists are
synthesized, humeri are adjusted, wrists become identity, and all 25 scalar-
first rotations convert to glTF XYZW order. The independent archive gate uses
real referee frames and compares 1,000 local channel results under strict GCC
and Clang while retaining the fixed-table/x87 and half-twist bit-identity
caveat.

A ninth recovered-code test covers the corresponding NFL player local-pose
path. It expands the exact 23-channel map into 25 named slots, extracts full
signed twists from `lhand`/`rhand` into disabled `lwrist`/`rwrist`, and applies
the instruction-proved left product `conjugate(twist) * hand`. Its independent
gate rereads all 93 frames of shipped `ANM_CELEBRATE_USER_34` and compares 22
poses / 550 channels under GCC and Clang with zero lane error. The portable
helper explicitly does not claim original-Xbox x87/SSE bit identity.

A further NFL native-code test covers the exact three-record row-layout table
at `0x00509A30`, both 38-unit modes, the 30-unit mode, wrap behavior, Z/W, and
the `(+8,-4)` text offset. Ten strict test cases include normal, wrapped,
negative-row, and invalid input. The live manager mode at `+0xA7C` and the
downstream title-space projection remain explicit `PORTME` work.

The native bitmap-font test independently loads font7's 94 strictly ordered
glyphs, 256×256 atlas contract, line advance 25, space advance 9, and recovered
`Quick Game` advance 177. A three-frame OpenGL test supplies the title-derived
PNG/metrics explicitly and writes `build/host-menu-nfl-font7.png`; comparison
with the bounded fallback changes 11,170 pixels inside the seven row-label
bands and zero outside them on the current NVIDIA witness. This proves the
isolated host render seam, not original boot, LAYT placement, all formatted-
string styles, or state execution. A separate exact 57-record native token
table resolves case-insensitive `|TM|` to index 40/texture slot 9. Its loose
32×32 source PNG replaces the literal markup in the host; a GPU comparison
changes 638 row-2 pixels and zero elsewhere.

The gold replacement test proved that changing a loose PNG changes the
rendered output. A deliberately unwritable screenshot path returns exit status
1 and `SMOKE FAIL`, avoiding a false-positive smoke result. The model fixture
reports one mesh and one material. The default smoke uploads the
redistributable `audio/menu_select.wav` as mono PCM16 through OpenAL.

An additional 60-frame native run loaded an actually extracted NFL 2K5
Cardinals logo and a recovered NFL `AUDO` conversion from one loose asset root:

- texture: 256×256 PNG;
- audio: mono PCM16, 15,000 Hz, 44,608 frames;
- screenshot: `reports/host_menu_extracted_cardinals_audio.png`; and
- result: `SMOKE PASS: rendered 60 frames`.

A second 60-frame native run loaded the evidence-checked APF `glowball` SCNE
glTF proof through the same loose model override. Assimp accepted one mesh;
OpenGL uploaded four vertices and six triangle indices; and
`reports/host_menu_extracted_apf_glowball.png` visibly captures the recovered
plane in the preview. The run ended with `SMOKE PASS`.

The larger APF `hi_head` proof also passed a 60-frame native render. Its glTF
contains 2,506 positions and 12,687 triangle-list indices derived from 7,345
source strip indices; `reports/apf_hi_head_position_preview.png` visibly
resolves as a human head rather than an arbitrary vertex cloud.

One automated GPU case uses `--model` on the recovered two-node APF
`online_titlebar` collection. Assimp reports two meshes; OpenGL uploads all six
vertices and six triangle indices; a 1280×720 screenshot is written to
`build/host-apf-online-titlebar.png`; and the run ends with `SMOKE PASS`.

A separate native smoke run now loads the complete recovered NFL stadium
collection at outer 3161 / chunk 6. Assimp splits its 143 source shapes and 562
submesh primitives into 562 meshes; OpenGL uploads 16,269 vertices and 77,526
triangle indices and writes `build/host-nfl-stadium-collection.png`. Raw
coordinates make the fitted preview diagnostic rather than scene-equivalent,
but the standard glTF/Assimp/OpenGL seam accepts the full collection.

An additional automated GPU case loads the all-`NORMSHORT3` recovered NFL
`geometry_font` collection. The executable-proved scale/offset decoder emits
41 source meshes; Assimp exposes 47 primitive meshes, and OpenGL uploads 973
vertices with 7,521 triangle indices before writing
`build/host-nfl-geometry-font.png`. This closes the compressed-position path
through extraction, standard glTF, Assimp, and the native renderer.

A ninth GPU case loads the raw-coordinate player skin proof. Assimp accepts
its 111 retained primitives, and OpenGL uploads 3,690 deduplicated vertices and
36,267 triangle indices before writing `build/host-nfl-raw-skin.png`. The file
contains the proved 25-joint hierarchy, inverse binds, and all 5,065 source
vertex influences. The host now evaluates those standard glTF skin objects at
rest; the proof file deliberately contains zero animation channels, so it does
not establish title-derived motion playback.

A tenth GPU case loads a redistributable one-joint animated glTF and performs
31 CPU deformation/upload frames. A non-GPU semantic test independently checks
all three vertices at 0, 0.5, and 1 second, proving exact 0/0.5/1-unit joint
translation while preserving their normals. This closes the generic standard-
glTF node/skin/animation seam; it does not assign Xbox channel axes or connect
either title's animation graph. See `docs/research/host_gltf_animation.md`.

An additional recovered-asset GPU case loads the separately validated NFL
player meter-skin derivative. It follows the proved retain-XYZ, right-handed
Y-up, centimeter-to-meter contract and reaches the same Assimp/CPU-skin/OpenGL
path without relabeling the still animation-free file as a title clip.

The next recovered-asset case is the first actual title-derived animation. The
shipped `ANM_REF_PENALTY_DELAY_OF_GAME_R` clip expands 21 packed channels into
25 local referee rotations, baked at 120 Hz as 357 keys and applied to both
high/low LODs (50 target channels). Independent host evaluation imports 12
meshes, 300 Assimp bone records, 2,006 weights, and one animation; all 1,375
vertices move between 0 and 1.5 seconds, with maximum `0.658806324 m`
displacement. A 91-frame GPU run exercises CPU skinning and dynamic upload.
The exporter gate byte-verifies three canonical outputs after strict GCC and
Clang regeneration. See `docs/research/nfl_referee_animated_gltf.md`.

APF `player_shadow` is now covered by the same native destination seam. The
canonical source has 351 vertices, 306 triangles, 21 direct-order joints, and
exact one-hot influences; Assimp's attribute-preserving deduplication imports
175 vertices, 918 indices, 21 bones, and 181 weight records. The selected
frontend derivative imports 18 animation channels. A native probe moves all
175 imported vertices by up to `0.0449219383 m` between 0 and 2 seconds, while
three-frame static and two-frame animated GPU tests produce visibly different
model crops (3,546 pixels on the local NVIDIA witness). Live scale, heading,
and base position remain normalized host-export inputs, not captured
menu-instance state.

The APF frontend v5/v6 evidence improves the boot boundary without claiming
completion. XEX entry `0x84BE9D08` reaches the frontend bootstrap, which
registers state ID `0x1F1A625A` with descriptor `0x82015330`
(`TitlePage_Menu`). Its key-11 record statically binds callback `0x846E0528`,
which constructs `StartupMenu` descriptor `0x820F4940`. Runtime key meaning,
live dispatch, any boot-to-`0x820F4350` Main route, and the owner of the orphan
Main tail wrapper at `0x84A56950` remain unproved. Bootstrap now exactly
requests `frontend_sync.iff`; its outer 1493 / inner 53 is
`layout_mainmenu`, CRC `0x48C6D154`. Team Select owns Main as an exit-policy
argument, but its callback closure does not construct Main. Main's direct
descriptor path instead selects `global.iff` 1310/57 `quicknav`. A scan of all
161 APF LAYTs finds no serialized inner-53 owner, so any separate runtime
manager remains unproved.

## What failed or remains intentionally absent

- The selectable NFL/APF rows are recovered-data host representations, not
  either title's original renderer or executing state machine.
- Navigation reaches the exact row models, but guest activation chains remain
  inert `PORTME` evidence. No recovered gameplay, franchise, roster, AI,
  rules, animation-graph, or original title UI logic executes yet.
- NFL font7 and the visible `TM` inline object are recovered host
  representations. All 57 token records and 13 texture resources are exact,
  but only TM is bound to a loose native icon today; the remaining texture
  slots, original style/state path, and title-space projection remain
  `PORTME` boundaries.
- The glTF seam evaluates standard node transforms, CPU skinning, and standard
  imported node animations. The raw/meter NFL base skins and static APF skin
  remain animation-free canonical files; separate derivatives bind one NFL
  referee clip and one APF frontend clip. NFL root translation remains omitted
  because one concrete actor's initialization/live state is unresolved. APF's
  derivative uses explicit zero base position/heading and scale one. Complete
  live scene ownership, textures, morphs, materials, and animation-graph
  semantics remain absent.
- The title-derived referee witness is deliberately bounded: gameplay
  ownership is exact for its `Referee` namespace/controller/skeletal family,
  while the concrete one-of-seven actor record and cutscene type-4 instance are
  unproved. Its 120 Hz standard glTF slerp has `0.0507245908` degrees maximum
  observed error over 26,700 sampled between-key probes, not a continuous or
  Xbox-bit-exact bound. The formerly blocking `0x00092140` stage now has
  structured value-equivalent C, and `0x00093850` is compiled/tested. One
  exact shipped player clip is conditionally joined through both LO_res and
  HI_res matrix paths, and the exact 62-joint HI_res static attachment now
  passes Assimp/GPU validation. Animated export remains withheld pending the
  concrete scoring-record type/classifier and resulting playback mode, the
  live mutable profile selection, and concrete actor/root state.
- APF boot is proved through initial title-state registration, a static
  title-action-to-StartupMenu edge, and the `frontend_sync.iff` request. Cold
  boot to a genuine Main construction and live key-11 dispatch remain
  unproved. Main directly owns `quicknav`; a separate runtime consumer for
  `layout_mainmenu` inner 53 is unproved and it may be unused retail content.
- NFL's complete SCNE embedded-texture catalog is available as standard PNG,
  with exact material-occurrence provenance, but the host deliberately does
  not attach those images to glTF materials until shader-stage, UV, and
  sampler semantics are proved.
- Loose PCM playback is working, but APF XMA, NFL `ABNK`/`WBNK`, streaming,
  loops, title mixers, and voice priority are not connected to OpenAL.
- Physical keyboard and gamepad navigation were not automated with hardware;
  input mapping and hotplug behavior are covered at the software seam.
- The disc roster parsers now expose proved read-only player/team/stadium
  subsets, but the host deliberately has no writable roster override yet. A
  separate offline NFL proof can replace four unique team-identity strings
  without changing their allocations or any serialized pointer; its copied
  XISO differs at exactly 17 bytes. A second fixed-size copied-XISO proof changes
  one player's unique first/last names and masked jersey bits in exactly 14
  bytes while preserving membership, count, position, face, and every unrelated
  field. Face/jersey/position plus three stable rating bytes are mapped, but
  remaining packed appearance fields, general string allocation, save-wrapper
  integrity, roster membership writes, and team-count expansion must still be
  proved before an editor can promise lossless general import.

## Blocking Phase 4

Phase 4 requires recovered title state machines and validated asset schemas,
not more host scaffolding. Both exhaustive function ledgers, NFL standalone
audio/texture conversion, APF XMA1/AUSB inventories, both scene-geometry paths,
read-only roster subsets, native NFL font/row helpers, and bounded NFL/APF
animated witnesses now exist. The immediate blockers are complete
material/root/animation-graph and bank semantics, writable roster/appearance
fields, NFL cold boot, APF Title/Startup-to-Main ownership, the remaining
`LAYT` lookup/event/instantiation edges, and the call chains that connect
recovered title state to the renderer and input layer.

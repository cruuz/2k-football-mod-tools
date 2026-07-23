# Phase 2 — decompilation and semantic recovery

Status: in progress. Exhaustive function ledgers exist for both executables,
but they are analysis artifacts rather than a source-equivalent recompilation.
The native host does not yet call either title's recovered state machine.

## What worked

### Complete address-accounted function corpora

- APF 2K8 has one ledger row and one delimited pseudo-C block for every one of
  21,347 final Ghidra functions. Ghidra emitted C for 21,346. The sole
  no-C result, the anomalously merged 686,968-byte function at `0x84C559C0`,
  has an address-specific `PORTME` and retained listing evidence.
- APF records every hard warning rather than treating emitted text as correct
  source: 880 functions have hard pseudo-C control-flow warnings, 12 own a
  seeded warning, 1,389 displaced `.pdata` starts and 198 displaced import
  thunks remain explicit work items. The consolidated queue has 2,513 rows.
- NFL 2K5 has 20,131 complete ledger rows: 19,971 internal functions and 160
  resolved external declarations. All internal functions have a pseudo-C
  body: 19,970 automated bodies and one instruction-complete manual body.
  The only remaining NFL function-level `PORTME`, `0x00115850`, is scoped to
  validating an implicit-register helper ABI rather than missing code.
- Both corpora retain function ranges, callers/callees, referenced strings,
  SDK/import evidence, warnings, decompiler diagnostics, and reproducible
  shard manifests. The validators reject missing addresses or silent errors.

### Cross-title shared-engine evidence

- Exact shared strings and normalized control-flow features were compared
  across x86 NFL 2K5 and PowerPC APF 2K8.
- Twenty-three one-to-one semantic/common-source homologs are confirmed, plus
  one duplicate-wrapper family. A 19-function roster/value cluster preserves
  constants and access patterns despite changed record strides.
- Two pure value-bucketing helpers and the left/middle/right side-label helper
  were rewritten as architecture-neutral C in `src/recovered/shared/` and are
  covered by boundary/decision-table tests.
- These are semantic matches, not unsupported byte-identity claims. The
  evidence and candidate rankings are in
  `docs/research/cross_title_cfg.md` and
  `docs/research/cross_title_lineage.md`.

### Renderer and asset semantics recovered from call sites

- NFL's proprietary `SCNE` loader/relocators prove an eight-table scene
  descriptor, named materials/nodes/shapes, embedded Xbox textures, vertex
  streams, and bounded NV2A push-buffer draw commands. The strict full-corpus
  inventory accepts all 4,616 scenes and accounts for 54,966 shapes, 276,642
  submeshes, 55,905 materials, 70,555 nodes, and 37,389 embedded P8 textures;
  every texture conversion, active vertex stream, command stream, and vertex
  reference validates.
- Every one of those 37,389 embedded P8 occurrences now re-decodes from the
  archive into a deterministic catalog of 5,351 standard RGBA8 PNGs. All
  55,905 material occurrences remain represented, including 45,413 exact
  material `+0x30` descriptor links and 10,492 null links. An independent
  validator parses every PNG/CRC, recomputes every RGBA and file hash, and
  rejects missing or extra catalog files. The link is provenance only:
  shader stage, UV selection, sampler state, mip use, and reverse PNG-to-P8
  archive writing remain explicit `PORTME` boundaries.
- NFL shape records expose 16 Xbox vertex-register descriptors. Each descriptor
  is exactly `(byte_offset << 16) | (stream_index << 8) | X_D3DVSDT`; eight
  following strides and eight self-relative pointers identify the streams.
  `ARRAY_ELEMENT16`, `ARRAY_ELEMENT32`, and `DRAW_ARRAYS` commands now recover
  bounded topology with all observed indices checked against vertex counts.
- The proved NFL position path now emits 4,007 static glTF scene collections
  containing all 54,966 shapes: 46,192 `FLOAT3` and 8,774 `NORMSHORT3`, with
  276,642 submesh primitives, 13,731,388 positions, and 24,139,104 glTF
  indices. The compressed path is proved by the serialized scale/offset
  relocator, render constant upload, common MAD in all 13 static shaders, and
  Xbox signed-short normalization. Every one of 8,014 model files is hashed
  and structurally revalidated; only 609 zero-shape scenes remain withheld,
  and a full archive-to-glTF byte comparison passes.
- NFL standalone texture and audio recovery is already complete at the asset
  level: 57,208 base-level textures convert to PNG, and all 850 `AUDO` objects
  convert from Xbox IMA ADPCM to PCM16 WAV.
- NFL's field-scorebug owner is now exact: the XBE binds nine named score
  materials to `score_buga` and two ESPN materials to `shield_espn`. Both P8
  textures, plus the explicitly global `digital_font`, have strict fixed-span
  PNG writers. A copied XISO changes exactly 2,169 `score_buga` bytes while
  preserving every XDVDFS extent and `default.xbe`. APF's seven registered
  `global.iff` scorebug SCNEs and separate season/GameCast SCNE export to glTF,
  but APF write-back remains `PORTME` because Xenon SCNE serialization, H7A
  IFF rebuilding, and DXT5A font import are not closed. See
  `docs/research/scorebug_presentation_modding.md`; no runtime visibility is
  claimed.
- NFL's created-team gameplay field-art family is now closed statically from
  selector to material owner. The XBE builds `ct%s%c.iff` from active-team
  logo code plus dry/rain/snow state, registers it as `CTGRAPHIC`, and binds
  `center_logo` plus six `endzone_*` names into the live `field` table. A
  separate pinned `goalpost`/`pad` material path binds `pad_north` and
  `pad_south`, closing all nine package textures. The
  exact outer-384..509 corpus contains 126 packages and 1,134 P8 textures with
  complete swizzled mip/palette and fixed-span compression layouts. See
  `docs/research/nfl_create_team_field_art_pipeline.md`; patched on-screen
  visibility and stock-stadium signage remain `PORTME`.
- NFL's 634 uniform packages are now exact 317-pair HOME/AWAY assets. Their
  invariant 53-object layout accounts for 6,340 `TSET` containers, 32,334
  embedded texture references, 25,994 standalone textures, and 18,386 glyph
  metrics. Executable evidence proves filename CRC construction, `Unif`
  relocation, HOME/AWAY loading, roster asset-code/style-label joins, and the
  runtime link into shared player `SCNE` materials. All 317 paired logo RGBA
  hashes match; a 51-PNG decode smoke test passes.
- NFL's complete motion-resource corpus is structurally bounded. All 4,559
  `SMCD` and 639 `MMCD` bodies re-read and reconstruct, accounting for
  60,930,224 bytes, 6,068 standalone/embedded 52-byte roots, and 18,375 unique
  pointer-bounded packed regions. XBE registration/load/release callbacks
  prove the shared name/root header, four root pointer fields, and `MMCD`'s
  counted `0x10` child directory over contiguous child roots. Eight absent
  saved Ghidra function boundaries remain explicit instruction-backed
  `PORTME` entries rather than silent pseudo-C omissions.
- The downstream NFL runtime sampler is also recovered. Exact code proves
  frame addressing, frame-major smallest-three quaternion decoding, signed
  short trajectory strides and 0.125 scale, fixed-point terminated events,
  logical-channel iteration, mirror/clamp flags, and an optional 12-byte
  per-frame stream. All 6,068 roots validate 14,073,985 main rotations,
  567,075 trajectories, 9,024 events, and 17,311 auxiliary records. The
  original named callers are correctly classified as prefetch paths rather
  than mislabeled samplers.
- The NFL smallest-three decoder now has a strict portable C implementation
  in `src/recovered/nfl2k5/packed_pose.c`. Unit tests cover all four omitted
  lanes, signed-10 extraction, reconstruction failure, and the instruction-
  proved mirror sign changes on lanes 2/3. A batched validator compares every
  one of the 14,073,985 main and 17,311 auxiliary packed words with the
  executable-derived reference; maximum lane and radicand errors are
  `1.16e-07` and `1.23e-07`. The module explicitly returns false for original-
  Xbox x87 bit identity and retains `PORTME at 0x000DEB00` for that helper.
- NFL's shared four-lane interpolator at `0x003CA270` is now instruction-
  proved and portable-native: shortest-path sign selection, the strict
  `0x3F7FF2E5` linear threshold, 16-bit turn-angle quantization, the exact
  256-entry piecewise-linear sine table, extrapolation, and non-normalized
  output. Nine edge vectors and a 65,546-vector grid pass with zero stored-lane
  error and `5.97e-08` maximum weight error. Exact original-x87 control-word
  behavior remains an addressed `PORTME`, not a hidden equivalence claim.
- The native composed pose-channel sampler now joins frame addressing, signed
  two-byte map selection, packed decode, fixed-table interpolation, numbered-
  lane mirroring, and final clamp. The later axis trace assigns the numbered
  vector lanes to right-handed game X/Y/Z without changing this sampler.
  Three deterministic cases across every one of the 6,068 roots produce
  18,204 checked samples over 14,959 distinct packed words. Both interpolation
  branches and shortest-path negation occur; maximum lane error is zero and
  maximum reference/native weight error is `2.98e-08`. The title-policy
  wrapper also validates all 6,068 flag sets: eight bit-0 roots perform the
  controller's repeated-duration loop and 696 bit-2 roots mirror. The follow-
  on coach/referee work now closes one exact 21-to-25 local-rotation path;
  family-wide root/controller ownership and player pose application remain
  explicit boundaries.
- The native NFL trajectory module preserves both proved six/eight-byte record
  layouts, exact one-eighth scaling of X/Y/Z, the optional fourth
  `signed_short << 3` turn integer, and mirror changes. The focused follow-on
  proves X=lateral, Y=up, Z=longitudinal, one game unit=one centimeter, and
  the optional short's `1/8192`-turn quantum. Its batch verifier matches all 567,075 records
  (451,676 stride-6 and 115,399 stride-8), including every signed source value
  and scaled float.
- The native NFL motion-event module preserves the exact 24-bit tick/8-bit ID
  split, `0xffffffff` termination, and fixed-point/time-scale conversion. Its
  corpus gate covers all 6,068 streams, 9,024 events, and 59 observed IDs with
  at most `2.07e-07` portable/reference seconds error; event names remain
  explicit `PORTME` work.
- The sampler's executable-installed non-identity channel maps are now exact.
  Three object-list initializers partition logical mask bits 0 through 24 and
  install two 25-pair signed-byte maps with 23 and 21 enabled channels. Both
  normal and mirrored packed-index domains are dense; converting mirrored
  indices through the normal map proves exact self/bilateral involutions. The
  maps, adjacent 25-float profile pointers, initializer bodies, and XBE
  section mapping are independently checked by deterministic Python and
  read-only Ghidra regeneration.
- Both 25-channel families are now bound to exact named SCNE transforms. Map
  `0x0051cd70` matches the player `lo_body`/`LO_res` order; map `0x0051d010`
  matches the shared referee/coach body order. Adjacent XBE parent arrays match
  every non-root serialized transform parent, while runtime sampling and
  name-to-record-index paths prove the index join. All 50 names, mirror pairs,
  and disabled bilateral pairs validate across one player, two referee, and 72
  coach body/LOD transform-table copies without relabeling unrelated SCNE
  nodes as bones.
- NFL's transform/skin path now resolves every vertex. Loader and palette code
  prove 110,318 absolute/parent-local bind translations and parents, 73,803
  two/three-source CPU matrix blends, register-1 `SHORT1` selectors, all 13
  active shader palette rows, and full/remapped palette uploads. All
  13,731,388 selectors map without conflicts to exact influence sets:
  13,372,190 one-transform, 328,001 two-transform, and 31,197 three-transform
  vertices. The follow-on trace proves identity rest rotations, `+0x50.xyz`
  local translations, external-root-parent hierarchy multiplication, and
  translation-only `T(-+0x40.xyz)` inverse binds. All 330,954 hierarchy
  components and all 110,318 rest palette cancellations are exact.
- Five fully mapped player/referee/coach meshes now have bounded raw-coordinate
  glTF skins: 125 named joint nodes and 11,730 dense vertex influence records
  across 157 primitives. The validator byte-compares clean regeneration,
  re-decodes every `JOINTS_0`/`WEIGHTS_0` and inverse-bind value, reconstructs
  125 rest hierarchies, and preserves each source static binary as an unchanged
  prefix. The later trace proves the right-handed Y-up, centimeter-to-meter
  conversion and concrete player root composition. The raw proofs remain
  unchanged, while a separately validated derivative set scales all 12,790
  positions, 125 joint translations, and 125 inverse binds by 0.01 meters and
  rejects any other binary change. Both base sets remain unanimated; a separate
  referee-only derivative now attaches one provenance-pinned shipped clip.
  Other external-root owners, loop accumulation, materials, and reverse
  writing stay explicit.
- The unique shipped `hi_body` / `HI_res` player shape now has a separate exact
  static attachment. All 62 serialized joints, 139 two/three-source CPU blend
  records, 86 per-submesh remap tables, and 7,396 vertex selectors resolve with
  no missing vertex or cross-submesh conflict: 5,356 vertices have one
  influence, 1,921 have two, and 119 have three. Deterministic raw-centimeter
  and right-handed Y-up meter derivatives preserve the 126,252-byte canonical
  static binary as an unchanged prefix and contain 62 inverse binds and zero
  animations. This closes the old static `HI_res` skin/palette-attachment
  blocker, but does not supply a live player controller, external root,
  profile values, or animation.
- NFL coordinate and concrete player-root semantics are now instruction-
  proved. X is field-lateral, Y is up, Z is field-longitudinal; one unit is one
  centimeter, and the trajectory quantum is 0.125 cm. The interval helper's
  result is `[dX, absolute Y1, dZ, dt, dTurn]`, mirror negates X/turn, and the
  player path adds X/`Y-100`/Z before hierarchy expansion. Game space is
  right-handed and Y-up, so glTF retains XYZ, scales positions by 0.01, and
  reorders scalar-first quaternions to `[x,y,z,w]`. Caller-specific external
  parents, scene ownership, and loop-cycle displacement remain bounded
  blockers rather than generic axis uncertainty.
- The selected referee trajectory now has a concrete gameplay callback trace.
  All 46 eight-byte records (368 bytes) are tabulated; title duration samples
  frame position `44.5000041`, between serialized records 44 and 45. Seventeen
  complete XBE function hashes prove the path from pool `0x00E60274` through
  controller `0x0031BEB0`, interval/heading rotation, actor scale, mutable
  transform state `+0x84`, and writes through `actor+0x18`. A follow-on trace
  proves two external-root builders, hierarchy expansion, low/high queue
  selection, palette generation, and draw. A glTF root track remains withheld
  because the concrete one-of-seven actor's initial/live state is not proved.
- The packed-pose-to-current-matrix path is now instruction-bounded. Hidden
  switch arms prove generic/player/coach/referee descriptor types; every one
  of 75 named family slots has either a mapped sample or an exact disabled-slot
  callback result. Scalar-first quaternion slot `N` becomes local matrix `N`,
  SCNE `+0x50` supplies its translation, hierarchy expansion is
  `local * parent/external_root`, and the palette is `T(-+0x40) * current`.
  Four cutscene/direct root policies remain distinct. Coach/referee paths are
  eligible for a bounded local-rotation witness. The player `0x00092140`
  local-matrix stage is now structured and value-equivalent within its measured
  portable/Xbox floating-point boundary. A shipped player celebration clip and
  its conditional selector/controller/render path are now joined, but an
  end-to-end animated player export still requires the concrete live record
  type/playback mode, external-root state, and profile values described below.
- The first such witness is now canonical. Executable selector row 4 right
  resolves `ANM_REF_PENALTY_DELAY_OF_GAME_R` under the literal `Referee` SMCD
  namespace and into the gameplay acquire/play/controller path. Its 46 frames
  at 15 Hz contain 21 packed channels; the native callback completes 25 local
  rotations and bakes them at 120 Hz into 357 keys, 8,925 native samples, and
  50 high/low-LOD glTF target channels. The title-derived glTF preserves the
  meter-skin binary as an unchanged prefix. All 1,375 vertices move between 0
  and 1.5 seconds, with maximum displacement `0.658806324 m` in the independent
  native deformation test.
- The representation boundary is measured rather than hidden. glTF unit XYZW
  keys require normalization and standard `LINEAR` rotation slerp, while the
  title uses slightly non-unit output from its fixed-table/x87 path. Across
  26,700 quarter/half/three-quarter between-key probes, the maximum observed
  difference is `0.0507245908` degrees; this is not a continuous bound or a
  bit-exact claim. The clip's 368 trajectory bytes and controller/callback
  behavior and final renderer ownership are now exact evidence, but root
  translation is omitted because one concrete actor's initial/live state
  remains unresolved; events are also omitted. Ownership is exact for the `Referee`
  namespace/controller/skeletal family, but the concrete one-of-seven actor
  record and a cutscene type-4 descriptor instance remain unproved.
- NFL's celebration selector and live-record ownership are now instruction-
  bounded. A new or otherwise unmodified profile initializes selector slot 2
  to row 2; actor state word `0x34` dispatches slot 2, whose null left pointer
  forces `ANM_CELEBRATE_USER_34` on the right. The direct profile setter at
  `0x00369AFA` and its 37-label table prove that row 2 (`Chest Pound`) is
  mutable, so it is not claimed for every saved profile. For every successful
  state-`0x34` selector dispatch, the newest tag-2 scoring record in the
  four-entry ring is proved to be owned by the same actor. Its concrete type is
  still not fixed: actor-owned types 1 through 5 select playback modes
  `[1,14,2,2,1]`. Neither the live gate/type nor the indirect producer of
  `state+0x1C = 0x34` is proved, so mode 1 and original-title end-to-end
  celebration playback remain explicit blockers.
- The player-only matrix postprocessors are now portable at value level.
  `0x00092140` preserves all 127 ordered calls/inline operations, the exact
  25-to-62 matrix map, both wrist-to-hand right multiplies, and all final
  writers. Eight-pose comparison against an independent graph peaks at
  `0.000234525141`; direct original-XBE execution in Unicorn against GCC and
  Clang peaks at `0.000234564883`. `0x00093800` has an exact four-call wrapper,
  while portable `0x00093850` retains its four profiles, mask/schedule loops,
  matrix order, and conditional scale with `3.81469727e-06` maximum error over
  116 cases. Xbox rsqrt/x87 bit identity and exceptional conversion flags
  remain explicit boundaries. The exact static 62-joint `HI_res` skin is now
  emitted, but no animated player glTF is emitted because the partial live
  type/playback-mode result and concrete external-root/profile inputs do not
  justify one.
- The three map-owning pools are now connected to the executable's five exact
  allocation rows. The 23-channel pool is allocated as two sides of 11+11 in
  ordinary configurations; the shared 21-channel map covers a seven-entry
  fixed-position pool and a two-entry pool whose indices 0/1 bind to the two
  exact team globals. Linked/backing strides and allocator type values are
  proved. Player, seven-official, and coach-like role labels remain explicitly
  graded inferences until stripped loader/model names are recovered.
- APF's `SCNE` work parses all 1,303 scene records: 13,006 mesh nodes,
  16,217,141 source vertices, 24,519,417 indices, 43,098 vertex declarations,
  and 40,991 hierarchy records. XEX-proved big-endian position formats and D3D
  triangle-strip draws produce evidence-checked `glowball` and 2,506-vertex
  `hi_head` glTF proofs; both load in the Linux host and the face is visibly
  recognizable in the captured render.
- The same proved APF position/topology path now emits 1,208 static glTF scene
  collections containing all 13,006 meshes, 16,217,141 positions, and
  11,588,322 non-degenerate triangles. Every one of the 2,416 glTF/binary
  files is manifest-hashed and structurally validated; 95 zero-mesh scenes are
  retained as withheld entries rather than fabricated models.
- APF's twelve executable-named uniform families resolve exactly to 517 normal
  IFF packages containing 1,332 TXTRs. All 40 roster teams have two proved
  14-pointer selector banks (1,120 unique aligned records), with slots 2–12
  linked to bounded package catalogs. The separate custom
  `uniform_logocache.iff` directory adds 236 exact `l0`/`l1` entries, yielding
  518 uniform-related resources; six representative team assets decode to
  loose PNG without implying an encoder or safe writer.
- APF's two facial `CurveAnim` banks contain 2,325 named bodies and tile all
  2,657,064 decoded bytes exactly. Registered XEX load/inverse callbacks prove
  four one-based field-local pointers in every one of 2,324 non-null bodies;
  all 9,296 resulting regions are ordered and bounded. The sole all-null root
  is an explicit 32-byte `null` sentinel, not misparsed as a normal curve.
- APF's 68 `SingleMoCap` resources preserve all 1,301,080 bytes as 67 normal
  clips plus one XEX-verified mirror alias. Runtime consumers prove 6,782
  counted six-byte root-vector samples and 34 terminated timed events. Both
  `BoneScaleMap` objects join all 144 bone CRCs to exact `SCNE` names, while
  seven exact NFL `SMCD` names establish structural lineage without a codec
  compatibility claim.
- The seven exact motion-name anchors now prove the boundary between shared
  motion semantics and changed serialization. Every pair preserves count,
  15 Hz rate, time scale 1, constant 100, six-byte trajectory order, and event
  sentinel, but values are revised. All 1,245,136 APF main pose bytes tile
  into 155,642 eight-byte units (23 per sample for 66 clips and 15 for
  `hand_pose`); interpreting them as NFL signed-10-bit dwords fails 50,704
  big-endian and 35,785 byte-swapped radicands. Frame/trajectory/event logic
  can be shared only above separate title-specific pose decoders.
- APF's title-specific main pose decoder is now instruction-proved. A mode-0
  big-endian 64-bit unit contains a four-bit selector and three signed 20-bit
  components with exact scale `23 / 2^24`; the missing unit-length component
  is reconstructed and the selector rotates the four numbered output lanes.
  The aggregate sampler proves 23-unit standard frames, the 15-unit
  `hand_pose` frame, three-byte normal/mirror index maps, frame interpolation,
  and mirror sign changes on numbered lanes 2/3. All 155,642 shipped units
  have positive radicands. The shortest-path interpolation polynomial and
  exact executable constants are recovered. Exact Xenon reciprocal-root
  estimation/rounding, map mode 2, optional-stream ownership, and writing
  remain scoped blockers. A strict C11 portable mode-0
  decoder is now linked into the native host and agrees with the reference on
  all 155,642 units to less than `7.27e-08` absolute lane error.
- Mode 1 is now independently instruction-decoded and portable: all 40,434
  shipped big-endian records contain three signed 20-bit values scaled by
  exactly `1/1024`, with mirror changing numbered lane 0. The active frontend
  path is also exact. Selector `(slot=1,index=2)` chooses shipped
  `mnu_stn_01_070130_01_lg` for object classes 2/3, reloads that exact clip,
  samples main map3 `0x820FC510`, expands 21 matrices through map2
  `0x820FC55C`, and applies them to exact `SCNE/player_shadow`. All 21 row
  names/parents are active bindings rather than candidates. Follow-on proofs
  assign quaternion lanes as `[lane1,lane2,lane3,lane0]` in glTF XYZW, prove
  right-handed Y-up retained XYZ with centimeters scaled by 0.01, keep the
  sampled trajectory on a distinct `player_shadow_external_root`, and prove
  direct 21-row palette order plus `T(-bind_global_cm * 0.01)` inverse binds.
- `player_shadow` therefore has a canonical Blender-readable static skin with
  351 meter-scale vertices, 918 indices, all 21 named joints/inverse binds, and
  all 351 exact one-hot influences. A separate selected
  `mnu_stn_01_070130_01_lg` derivative retains every 15 Hz source key inside
  the `7.716666698`-second runtime duration and bakes 927 keys at 120 Hz: 17
  rotation channels, six named-bone translation channels, and one external-
  root trajectory channel. On a 960 Hz finite probe grid, its maximum observed
  errors against the recovered portable sampler are `9.80911239e-06` degrees,
  `2.61196136e-08 m` for bone translation, and `8.94118177e-08 m` for external-
  root translation. These are finite-grid measurements, not continuous or
  Xenon-bit-exact equivalence.
- The joined export gate clean-regenerates and structurally re-decodes both APF
  artifacts, byte-checks the unchanged 918-index source topology, and passes
  strict GCC and Clang 18 Assimp/OpenGL tests. Assimp's intentional identical-
  vertex join imports 175 vertices, 918 indices, 21 bones, 181 weight records,
  and 18 animated node channels. At two seconds all 175 imported vertices move,
  with `0.0449219383 m` maximum displacement; OpenGL 3.3 renders three static
  and two animated smoke frames. The 1280x720 local screenshot witnesses contain
  1,928 and 1,778 model pixels and differ at 3,546 pixels. Their driver-specific
  hashes are evidence for this host run, not portable golden images, and none
  of these tests executes APF's original state machine.
- APF audio metadata accounts for all 2,261 `AUDO` records, 62,513,152 encoded
  bytes, and 30,524 2-KiB XMA1 packets. Of 1,268 unique payloads, FFmpeg
  independently verifies 1,261; the remaining seven are retained as named
  decoder/header-semantics blockers. All 20 `AUSB` descriptors also parse and
  map by `CRC32(uppercase filename)` to 19 external banks containing 45,514
  bounded substreams and 1,144,270,848 encoded bytes.
- The menu configuration layer is demonstrably data-driven. All 161 APF and 86
  NFL `LAYT` objects parse into 1,837 and 280 bounded linked records. Exact
  consumers prove additive translation X/Y/Z, type-2 child recursion, runtime
  draw/selection gates, APF type-3 60 Hz timelines, and NFL type-1 callback and
  dispatch-table ABIs. There are 102 exact cross-title keys, 98 unique bridges,
  and 27 identical whole-layout sequences covering 120 records. Exact APF and
  NFL visual main-menu data entries are located; native state ownership is
  resolved separately below.
- The native frontend trace now separates visual backdrop from state-selected
  navigation. NFL descriptor `0x00515660` loads `main_menu_sub`, constructs
  seven exact rows, and reaches their typed activation paths. APF descriptor
  `0x820F4350` loads CRC32-selected `quicknav`/`template_quicknav`, constructs
  seven type-10/11/12 rows, and has one proved return-to-main callback. V6
  proves bootstrap requests `frontend_sync.iff`, but Main's direct LAYT is
  exactly `global.iff` `quicknav`, not `layout_mainmenu`. Team Select dispatches
  Main only as an exit-policy argument whose callback does not construct it;
  no genuine cold-boot predecessor or separate `layout_mainmenu` owner is
  proved. A follow-on
  recovers 12 fragmented function boundaries and resolves 8 of the original 23
  blockers, including the exact type-3 apply/config path and seven queued plus
  one direct main-descriptor routes. It also proves negative absence of a
  fullword/string `layout_mainmenu` CRC edge. Fifteen exact `PORTME`s remain,
  preventing an original-launch claim.
- All ten cross-title `DRCT` director resources now preserve every decoded
  byte as a relocated graph: 273 fixed record packages, 3,664 exactly bounded
  opaque instruction records, and 703 primary strings. NFL executable code
  proves a 193-slot fixed table, child accessor, indexed instruction consumer,
  string accessor, and full reset walk; APF evolves this to 217 slots plus an
  opaque auxiliary tail. The generations share 114 exact primary strings.
- Both on-disc roster generations now have strict read-only parsers. APF's
  single `ROST` object accounts for all 40 root arrays, 2,254 `0x14C` player
  records, 40 teams, 31 stadiums, 1,344 counted memberships, and 6,469 exact
  UTF-16BE strings. NFL's complete 76-resource corpus accounts for 6,522
  `0x54` player records, 127 `0x1F4` teams, 157 stadium records, 110 coaches,
  and all proved relationships. In both formats, executable relocators
  independently prove the signed field-local pointer rule. The evolved player
  strides and tagged two-pool accessors provide concrete schema-lineage
  evidence without claiming field-level binary compatibility.
- NFL's main 52-row team identity table is now joined to its separate selector
  domains: 85 uniform/Team Select codes, 80 fixed XBE color records, and 42
  created-team field-art codes. The two empty user seeds and compiled
  create/edit text routines prove shared runtime team-field ownership, while
  the exact save container remains unproved. A same-length four-string rename
  passes a copy-only 17-byte full-XISO proof with the team record, roster,
  selector `09`, XBE, and XDVDFS tree unchanged. This does not expose ratings,
  arbitrary string growth, roster membership writes, or team addition.
- A separate bounded main-disc player audit now closes the most useful fixed
  fields without claiming a general roster editor. XBE consumers prove
  face/head ID `+0x06`, jersey bits 3–9 of `u32 +0x20`, and position byte
  `+0x35` with all 17 labels. Parallel executable dispatch tables yield 204
  exact position/rating UI bindings; Speed `+0x36`, Consistency `+0x50`, and
  Aggression `+0x51` are named only for positions whose UI binding proves the
  label. A copied-XISO
  `Joey Harrington #3` -> `Noah CodexProof #42` proof changes exactly 14 bytes
  and preserves Detroit slot/count, position, face, every pointer/unrelated
  field, XBE, and XDVDFS. Save precedence and runtime remain unproved.
- All four `STRG` localization objects parse and rebuild byte-for-byte. The
  primary banks contain the same 1,492 texts and the same ordered 1,106-entry
  deduplicated pool in both games. Record alignment proves bijective
  translations across 219 first-field IDs, 254 second-field IDs, and 740 ID
  pairs even though the two builds share no numeric IDs. NFL lookup code at
  `0x001692D0` independently proves the two-key, variant-selecting record
  traversal and UTF-16 pool-offset calculation.
- APF's two separate `TXT loc system` resources are also bounded and
  byte-exact: 1,572 sorted IDs reference 1,294 UTF-16BE pool entries. All 1,571
  ordinary references land on exact string boundaries; the sole
  `0xffffffff` control row and its opaque word are retained as an explicit
  blocker. XEX language selection independently maps the CRC32 IDs for
  English, French, German, Italian, and Spanish.
- The complete cross-title `PLAY` corpus is now structurally recovered: APF's
  one master book contains 163 formations, 586 plays, 28 categories, and 4,948
  aligned assignment/route nodes; NFL's 37 books contain 1,533 formations,
  9,251 plays, 835 categories, and 91,833 nodes. Every play has exactly eleven
  bounded assignment references. The titles share 114 formation, 428 play,
  and 23 category names, while executable evidence fixes NFL's table strides
  and eleven-pointer relocation loop.
- The complete observed assignment-descriptor domain now has an exact,
  reversible APF-to-NFL packing transform. It covers all 6,446 APF and 101,761
  NFL descriptor occurrences, maps 78 of 88 APF unique values into NFL's
  observed set, and yields 161 same-named APF play occurrences with all eleven
  converted slots equal. In 101 cases, all eleven first referenced route nodes
  also match after preserving packed bytes and normalizing the platform-endian
  word.
- APF's sole `FSMR` resource is proved to be the finite `crowdren1`
  configuration rather than a bytecode VM: two relative root pointers address
  30 `0x20` records and 47 populated `0x10` records followed by a 72-byte zero
  tail. XEX consumers prove the strides, weighted four-way selector, and
  packed-transition access pattern.

### Linux replacement seams

- XInput-style controller state maps to SDL2, host file/time/memory operations
  map to POSIX, PCM audio maps to OpenAL, and the host renderer uses OpenGL
  3.3. Xbox-only operations that lack proven semantics retain `PORTME` comments.
- Loose PNG, PCM WAV, and static glTF triangle assets are now loaded and used,
  not merely enumerated. This proves the standard-tool mod boundary while the
  original title logic remains disconnected.

## What failed or remains provisional

- Pseudo-C is not automatically compilable recovered source. Ghidra types,
  calling conventions, indirect calls, switch recovery, structure ownership,
  and many names remain provisional, particularly for APF's stripped PPC code.
- APF still has 1,389 displaced runtime-function starts, 198 displaced import
  thunks, and one giant merged function that must be split before it can be
  called safely from native code.
- The NFL `0x00115850` implicit `EBX`/`ESI`/`EDI` helper contract is not yet
  independently ABI-validated.
- Seven unique APF XMA payloads (32 `AUDO` occurrences) do not cleanly decode
  with the current reconstructed XMA1 stream. Extraction and packet boundaries
  validate; remaining header/decoder semantics are unresolved.
- The 45,514 AUSB substreams are structurally inventoried, but only a bounded
  halftime proof set has been decoder-verified rather than the full corpus.
- Fifty-seven APF scenes retain exact variant blockers: 49 matrix-like table
  variants and eight hierarchy-chain variants. They are bounded and named in
  the report rather than rejected as generic parse failures.
- APF's full static glTF corpus is usable for geometry inspection, but raw
  coordinates, omitted draw/material ownership, unapplied transforms, omitted
  non-position attributes, corpus-wide skinning/animation, and the absent
  reverse writer mean it is not yet a scene-equivalent round trip. The selected
  `player_shadow` static skin and bounded animation derivative above are an
  exact, validator-gated exception, not a corpus-wide closure.
- NFL's complete static `FLOAT3`/`NORMSHORT3` position corpus and
  triangle-strip/quad topology are safely exportable. Non-position
  vertex-register meanings outside the proved selector, full node ownership,
  corpus-wide skin export, morph
  channels, full sampler/shader/material parameters, and the secondary
  submesh count remain unproved; none are fabricated in the glTF collections.
- A paired NFL-to-APF stadium/player audit proves only a common glTF/Blender
  authoring seam. The selected players share right-handed Y-up meter space and
  a standard inverse-bind representation, but the NFL 62-joint skin differs
  from the proved APF 21-joint shadow skin and separate 92-joint hierarchy.
  Direct joint indices, serialized meshes, materials/shaders, complete
  normals/UVs, LOD, collision, model archive writeback, and runtime routing are
  not compatible or remain blocked. The deterministic 15-surface matrix and
  124 authoring-only bone candidates validate with
  `bash tools/validate_cross_title_model_compatibility.sh`; see
  `docs/research/cross_title_model_compatibility.md`.
- Full material, texture-assignment, skeleton, skinning, morph, animation,
  collision, franchise, AI, and rules schemas are not yet reconstructed end
  to end. Roster record boundaries and a substantial proved field subset are
  recovered, but packed attributes, appearance fields, opaque root arenas,
  allocation rules, and safe round-trip serialization remain unresolved.
- Uniform package/texture/name relationships are exact, but unknown `Unif`
  selectors, full SCNE material binding, capacity, and a validated archive
  serializer still block a general loose-uniform import path.
- APF uniform filename/package/team-selector/cache relationships are exact,
  but selector slots 0/1/13, selector bytes 1–7, the two banks' user-facing
  orientation, the config tail, Xenos mip/tiling encoding, H7A/IFF/archive
  writing, and logo-cache invalidation remain unproved.
- NFL `SMCD`/`MMCD` pointer graphs, packed-region boundaries, quaternion codec,
  trajectory/event timing, channel iteration, and both executable-installed
  signed-byte maps are exact. Their 22/7/2 actor-pool cardinalities and the
  two-entry pool's team affiliation are also exact, while human-facing class
  names remain partly inferential. Both channel maps now have exact named
  player and referee/coach transform binding plus hierarchy parents. The two
  adjacent `+0x24` targets are exact 25-float profiles rather than handler
  tables, but their stack argument is ignored by the focused pose-difference
  callee, so their semantic role remains unproved. Bind translations,
  hierarchy parents, vertex selectors, exact influence indices/weights, and
  shader palette addressing are now proved. Rest rotations, local/cumulative
  bind translations, inverse binds, and external-root-parent matrix space are
  now exact, with five raw-coordinate skin proofs emitted. Event names/
  callbacks, opaque header fields, title-wide pose application, complete
  animation graphs, non-player external-parent ownership, and loop-cycle root
  accumulation remain unresolved. The native portable decoder is corpus-
  complete but not claimed bit-identical to the original x87 sqrt/rounding
  path. Only the bounded referee animated witness is emitted. Its
  trajectory/controller/callback semantics and final renderer path are exact,
  and the static 62-joint `HI_res` attachment is exact, but no animated player
  glTF is emitted. Celebration selector row 2 and successful-dispatch actor
  ownership are proved only within the scopes above; the concrete scoring type,
  resulting playback mode, live external root/profile values, and event/state
  producer are not guessed.
- `CurveAnim` root pointers and region boundaries are exact, but its packed
  element widths, time/value quantization, interpolation, termination, and
  SCNE morph-target channel mapping remain unresolved; no speculative glTF
  animation is emitted.
- `SingleMoCap` root samples/events, BoneScaleMap names, eight-byte mode-0
  grammar, exact `23 / 2^24` quantization, selector rotation, frame addressing,
  normal/mirror maps, numbered mirror lanes, shortest-path interpolation, and
  all 40,434 mode-1 translations are exact. One active selector-to-clip-to-
  `player_shadow` path supplies exact names/parents for all 21 applied rows.
  For that selected asset, quaternion lane order, APF axes/units, external-root
  placement, palette order, inverse binds, a canonical 21-joint static skin,
  and a bounded 120 Hz animated derivative are now proved and emitted. Xenon-
  bit-exact `vrsqrtefp`/VMX interpolation, map mode 2, optional-stream meaning,
  continuous recovered-polynomial host playback, concrete live menu scale/
  heading/base position, material bindings, and the archive writer remain
  unresolved. The artifacts do not establish original-title state-machine
  execution.
- `LAYT` translations, child recursion, runtime draw gates, timelines, and
  callback shapes are exact, but APF lookup-ID generation, the inherited
  default-one scalar, author-facing event vocabulary, callback ownership,
  pool capacity, state constructors, and round-trip serialization are not.
- `DRCT` graph/string boundaries and consumers are exact, but instruction
  opcodes, operands, branching/termination, fixed-record pointer roles, APF's
  auxiliary tail, and safe serialization remain unresolved.
- `STRG` serialization is byte-exact, but the producer/source-key meanings and
  generation algorithms for its two numeric IDs are not proved. APF's separate
  `TXT loc system` IDs likewise lack producer/source-key semantics; its
  `0xffffffff` control row and lookup/fallback consumer still need a focused
  trace. Neither proprietary archive has a safe size-changing importer.
- Playbook record boundaries, names, and the cross-platform descriptor packing
  transform are exact, but descriptor bit meanings, eight-byte node
  opcodes/chains/coordinates, blocking/routes/coverage,
  packed lineup fields, APF's post-string tables, NFL's post-node region, and
  capacity/save/UI consumers remain unresolved. Same-named plays are lineage
  anchors, not yet safely interchangeable behavior records.
- `FSMR` record boundaries and selector/weight/transition behavior are exact,
  but domain field names, table-B cardinality ownership, and safe serialization
  are not yet proved.
- NFL banked/streamed `ABNK`/`WBNK` audio, loop points, title mixers, and voice
  priority are not connected. The 850 standalone sounds are a proven subset.
- No evidence supports the original RenderWare assumption. Both titles use a
  proprietary Visual Concepts resource/render layer over platform graphics;
  `rw_linux.h` intentionally remains a guarded compatibility stub.

## APF franchise and 2K6-lineage checkpoint

The APF archaeology pass closes two high-value questions without overstating
runtime reachability:

- The retail XEX contains a contiguous 5,884-record animation-definition
  registry. Exact `+0x04/+0x08` name fields reference 519 distinct
  `ANM_*2K6*` identifiers 597 times and associate them with 225 `.ani`
  filenames. All 597 fields map to unique concrete in-XEX motion roots; 149
  identifiers join 49 payload groups in code-enumerated selector arrays. The
  same executable's `ANM_` strings retain annual tags from 2K3 through 2K8.
  This proves a 2K6-era gameplay/animation generation inside the NFL branch,
  not a formal complete product titled NFL 2K6. The name table itself has no
  recovered code owner, and known direct calls do not reach one examined 2K6
  movement configuration. Validate with
  `bash tools/validate_apf_2k6_animation_lineage.sh` and
  `bash tools/validate_apf_2k6_animation_runtime.sh`.
- APF has substantial compiled, APF-adapted franchise code: nine old
  `FranchiseMenu_*` descriptors, a real Coach's Desk initializer, exact
  `franchise.iff`/Season/SportsCenter request paths, and APF-specific
  franchise completion text. Retail Season directly targets the old
  `FranchiseMenu_CoachGameplan` descriptor. The standalone initializer has no
  static owner and the Wrapup graph has no proved retail root, so a hidden
  playable franchise remains unproved. Validate with
  `tools/validate_apf_franchise_runtime_ownership.sh`.
- The archive audit independently preserves all 1,492 ordered NFL franchise
  texts, all 1,106 pooled texts, 21 complete layout sequences, evolved
  SportsCenter/Berman/draft scenes, and recognizable NFL Draft/postseason
  textures. Across 105 directly paired name/type resources, zero decoded
  bodies are byte-identical; this is converted/evolved Xenon content rather
  than a raw Xbox file copy. Validate with
  `bash tools/validate_apf_nfl_cut_content_lineage.sh`.
- A focused `reference.iff` follow-up proves another converted licensed-content
  cluster: APF retains the bound `nfl_shield1` quad/material/128×128 shield
  texture, four valid `REFR` tables totaling 438 records and 1,092 closed
  string pointers, and 987 exact ordered NFL 2K5 text occurrences. The XEX
  retains and boot-registers the matching generic loader/relocator. A focused
  code plus 3,873,511,424-byte all-pack scan finds no APF owner edge, while NFL
  has an exact Extras → Reference Guide lifecycle; classify the APF package as
  statically orphaned retail content, with a runtime-address-synthesis/external-
  injection caveat. Validate with
  `bash tools/validate_apf_reference_nfl_remnants.sh` and
  `bash tools/validate_apf_reference_runtime_owner.sh`.
- A second dual-hash follow-up resolves APF outer 499 and NFL outer 109 as the
  exact `manual.iff` pair. All 15 NFL `xb-*` manual pages survive as APF
  `xenon-*` MANU resources with identical per-page cardinalities: 1,553 string
  slots total, 1,544 exact after only two mechanical markup normalizations,
  and nine bounded authored edits. The XEX retains a registered initializer
  for `manual.iff`, `open_book`, and all 15 pages. No retail frontend/state
  owner or formal NFL 2K6 product identity is proved. Validate with
  `bash tools/validate_apf_manual_nfl_remnants.sh`.
- APF outer 239 and NFL outer 1193 are the exact `pregameanims.iff` pair. APF
  retains `bigfigureafc`, `bigfigurenfc`, `bighelmet`, and
  `big_team_matchup`; all four AFC/NFC textures remain directly bound and
  visibly preserve the conference logos after P8→DXT1 conversion, with
  minimum channel correlation `0.972666`. All three meshes are near-identical,
  and the matchup graph retains ESPN plus dynamic team helmet/logo/color
  names. The graph retains 78/79 compact NFL identifiers. APF has generic MRKS
  support but no exact-name/hash package-specific static owner; NFL explicitly
  loads, resolves, and releases `PREGAME`. APF is a static-orphan candidate,
  not proven runtime-dead because dynamic/index enumeration remains possible.
  Validate with `bash tools/validate_apf_pregame_conference_remnants.sh` and
  `bash tools/validate_apf_pregameanims_static_ownership.sh`.
- NFL's ninth Options row directly targets a complete `Sound Test` state and
  `AUDIOTESTMENU.IFF`. APF removes that row but retains a `Sound Test` state at
  `0x82006870`, `AudioTestMenu`/`gamesound` bindings, three callbacks, and ten
  directly converted glowball/speaker/cursor/audio resources. Whole-image
  pointer and conventional PPC materialization scans find no APF route, with
  positive controls, so it is a bounded static orphan rather than a claimed
  playable hidden menu. All eight retained SCNEs export deterministically to
  Blender-openable glTF (8 meshes, 2,042 vertices, 1,899 triangles). Validate
  with `bash tools/validate_apf_audio_test_remnant.sh` and
  `bash tools/validate_apf_audio_test_gltf.sh`.
- APF also retains all three converted descendants of NFL 2K5's live Basic
  Training states: the six-event tutorial descriptor at `0x820E5AE0`, normal
  and crippled pause loops, a directly called 796-byte update routine, a
  function-table-owned `dir_tutorial.iff` loader, and a 101/101 exact tutorial
  string-set match. The proved descriptor routes remain internal, both code
  paths require mode value 4, and no conventional fixed producer of 4 was
  found. Classify this as code-connected, internally closed cut-mode lineage,
  not a playable hidden mode. Validate with
  `bash tools/validate_apf_basic_training_remnant.sh`.
- The retail NFL and APF executables also preserve the exact challenge
  presentation developer note that the screen is a placeholder pending
  prettier camera cuts. NFL's copy is used by the bounded formatter at
  `0x001B1420`; APF's converted copy is used by the two-way formatter at
  `0x8486FC70`, and both have direct caller chains. Tiny `Hello World` pointer
  getters survive in both titles but have no direct static callers under the
  bounded scans. This is shared unfinished-presentation lineage, not runtime
  proof of cut cameras or a formal NFL 2K6 title. Validate with
  `bash tools/validate_challenge_placeholder_lineage.sh`.

The associated docs are `docs/research/apf_2k6_animation_lineage.md`,
`docs/research/apf_2k6_animation_runtime.md`,
`docs/research/apf_franchise_runtime_ownership.md`, and
`docs/research/apf_nfl_cut_content_lineage.md`,
`docs/research/apf_reference_nfl_remnants.md`,
`docs/research/apf_manual_nfl_remnants.md`, and
`docs/research/apf_pregame_conference_remnants.md`, plus
`docs/research/apf_audio_test_remnant.md` and
`docs/research/apf_basic_training_remnant.md`, plus
`docs/research/challenge_placeholder_lineage.md`.

## APF whole-XEX static-recompilation checkpoint

The retail XEX now reaches 100% in XenonAnalyse/XenonRecomp after removing 22
deterministic 32,767-label false-positive switch tables. The run produced 236
translated-code C++ units plus one mapping unit / 130,462,146 bytes, and representative units pass
Clang 18 syntax checking. A complete independent audit now passes all 237/237
generated C++ files with zero Clang 18 diagnostics. That is a useful
CPU-translation bootstrap, not a
native port. The exact remaining defects include 3,337 cross-function switch
violations across 196 switch bases, a missing switch at `0x84BC849C`, 172 sites
across 11 omitted PPC/VMX instruction semantics, 347 imports, and no
APF-specific Xenos/XMA/title runtime. Generated implementations also outnumber
Ghidra's recovered text functions 60,397 to 21,347, reinforcing the boundary
reconciliation requirement. The generated external boundary contains 334
callable XAM/xboxkrnl thunks and 13 imported data slots; 333 callables occur at
1,708 static sites. That exact count still omits statically linked XDK and
hardware behavior and does not make no-op stubs safe.

The next mechanical gate compiles all 237 generated files to objects and links
them with two support objects. All 334 callable imports are defined as explicit
fail-fast abort traps, LLD reports zero unresolved guest symbols, and a bounded
harness counts all 60,731 mappings with return code 0. The harness never loads
the guest image or calls title entry; this proves link closure only, not APF
runtime behavior.

A second bounded checkpoint performs the pre-execution loader work. It decodes
and verifies the exact 54,001,664-byte retail image, reserves a sparse 4 GiB
guest address space, checks all nine PE sections, and initializes and reads
back all 60,731 host-function mappings. It deliberately leaves all 13 imported
data slots at their original unresolved ordinal words and never calls
`_xstart`. A focused reconciliation proves the 824 XEX security descriptors
sum to exactly `0x03380000`; both pinned XenonRecomp and Xenia allocate and
decompress that authoritative span. The dispatch table begins at its exclusive
end, `0x85380000`, with zero loaded-title-byte overlap. The larger PE
`SizeOfImage` is non-authoritative metadata here. Before execution, the runtime
must reserve the table's page-rounded `[0x85380000,0x86133000)` range from
guest allocators/MMIO or move the table into host-only storage.

A separate nonexecuting direct-call analysis narrows the initial runtime
adapter surface. The 60,397 generated implementations contain 85,643 unique
direct edges. Unrestricted traversal from `_xstart` reaches 6,917 nodes and
151 callable imports; treating title main `sub_84B8B1D0` and post-main
`sub_84BDAC80` as reached-but-opaque boundaries reduces that to 103 nodes and
27 imports. This remains a path-insensitive planning frontier, not a boot
trace: it includes failure/destructor branches and initially omitted 15
indirect dispatches. Ten of those now have exact entry-context proofs totaling
254 edges / 253 unique targets. Following only those edges expands the static
frontier to 458 nodes and 30 imports. Five original and two newly exposed
second-wave indirect calls remain address-specific `PORTME`s.

The first isolated Linux guest-ABI slice accounts for all 87 direct import
sites in the augmented 30-import frontier. Twenty-four bounded adapters cover
76 sites, four terminal adapters cover eight, `RtlRaiseException` preserves
all 32 integer GPRs plus LR and requires guest exception dispatch at two, and
the final `ExCreateThread` site produces a typed non-resumable scheduler
handoff. Four separately
proved indirect TLS dispatches are also supported. The resumable layer provides
required XConfig/process/language/AV/system-flag inputs, per-guest-thread TLS,
overflow-safe big-endian memory access, bounded `RtlInitAnsiString`, documented
`RtlCompareMemoryUlong` byte semantics, and a scheduler-aware
uncontended/recursive critical-section candidate with durable retry state. It
also records the exact post-main `DbgPrint` as a bounded typed event and
validates APF's exact 144-byte retail XEX2 prefix before returning null for the
absent `DEFAULT_HEAP_SIZE` query; generic variants stay fail-fast. Its
complete 19-site VM subset uses exact LR/flag gates, a loader-configured
collision-free 64 KiB ledger/backing arena, mapped-range exclusions,
transactional BE outputs, zero/`NOZERO`, decommit/release/query, and exact
sign-extended NTSTATUS failures. The four-site
event/handle/wait group now uses the Xenon handle namespace, helper-built
case-insensitive named events, reference-counted close, manual/auto-reset
signals, zero-timeout polling, and a nonblocking scheduler stop for pending
waits. It does not sleep a Linux host thread or invent elapsed guest time.
Its optional CMake test is separate from the
normal SDL/OpenGL executable and does not call `_xstart`. Scheduler park/wake
deadlines/signals/APCs, host VM page protection, general kernel objects, SEH,
the eleven out-of-frontier imported-data objects, and the seven unresolved
indirect dispatches remain open.

A frontier-specific imported-data audit narrows 13 imported slots / 46 direct
reads to the only two slots reached in the 458-node frontier. An isolated
transactional bootstrap installs `XexExecutableModuleHandle` and
`KeDebugMonitorData`, preserves the other eleven ordinal words, and points the
module chain at a separate copy of the exact raw-XEX header prefix rather than
the decoded `MZ` image. The debugger-disabled export cell is null, preventing
its callback dispatch.

The guarded first-entry readiness harness composes that bootstrap with the
exact 54,001,664-byte decoded image in a sparse 4 GiB guest mapping, a
loader-owned stack/thread/config state, all 60,731 generated mappings, and all
30 typed import bridges. Exact static order is
`_xstart -> sub_84BF1950 -> sub_84BF1850 -> RtlImageXexHeaderField`; the call
at `0x84BF1888` / LR
`0x84BF188C` is the first typed boundary. No opcode-gap site, unresolved
switch-tail occurrence, or unresolved indirect call precedes it. A throwaway
full link and direct bridge stop pass. The former two blockers are now closed
by a single 237-TU corpus containing both candidate families and a derivative
with one immediate budget hook at every one of 1,808,124 translated guest
instruction occurrences. A v2 driver revalidates those complete trees plus the
loader/import state, then calls `_xstart` only in a forked bounded child. The
first run executes exactly 38 guest instructions and one typed dispatch before
stopping immediately after `RtlImageXexHeaderField` at `0x84BF1888` / LR
`0x84BF188C`, with `r3=0`. It neither continues, signals, times out, aborts an
import, boots the title, nor reaches a menu. This is the first contained
translated-title execution slice, not a native launch.

The next exact startup segment is now proved both statically and dynamically.
The null heap-size result selects a 226-instruction continuation with no
unresolved indirect, opcode, or switch residue before the next platform call.
The contained test executes 264 cumulative guest instructions and reaches
`NtAllocateVirtualMemory` at `0x84BED7B8`; the typed Linux adapter reserves the
requested 1 MiB at guest address `0x40000000`, writes the expected result
cells, and the test stops before `0x84BED7BC`. Static and dynamic ordered-PC
hashes match. This is still early game startup compatibility, not a boot or
menu.

The immediately following 19-instruction path is now also matched statically
and dynamically. Before authorizing `0x84BED7BC`, the isolated bridge
revalidates the complete 16-page reserve ledger and the one-MiB backing
pattern. It then reaches the proved `NtAllocateVirtualMemory` commit call at
`0x84BED808` with base `0x40000000`, size `0x00010000`, and allocation type
`0x60001000`. The existing typed adapter commits and zeroes page 0 while pages
1 through 15 remain reserved with their pattern intact. The cumulative run is
283 guest instructions / three typed dispatches and throws before generated
instruction `0x84BED80C`. It still proves neither native boot nor a menu.

The next exact 82-instruction slice initializes the committed page's absolute
link nodes and descriptor fields, then reaches `KeGetCurrentProcessType` at
`0x84BED908`. A fourth guarded run dynamically matches the static trace,
revalidates the one-committed/15-reserved-page ledger and initialized page,
receives configured process type 1, and stops before `0x84BED90C`. The
cumulative result is 365 guest instructions and four typed dispatches; it is
still not a native boot or menu.

The following 654-instruction slice is now matched statically and dynamically.
It stores process type 1 in the committed page, builds exactly 128 self-linked
allocator heads, and takes the known `r21 == -1` branch to
`RtlInitializeCriticalSection` at `0x84BED954`. The fifth guarded run supplies
`r3=0x40000610`, verifies the exact pre-adapter page and allocation hashes,
executes the existing typed adapter, verifies its exact 28-byte output, and
stops before `0x84BED958`. The cumulative result is 1,019 guest instructions
and five typed dispatches; it still proves neither native boot nor a menu.

The cross-function dispatch defect now has a conservative isolated candidate.
It repairs 2,261 of 3,337 baseline occurrences: 1,998 exact generated-function
tails and 263 Ghidra-body-gated recovered entries. All 237 candidate C++ units
pass syntax checking. The remaining 1,076 occurrences cover 190 unique
address-specific `PORTME`s, including same-body non-template entries,
unowned code/data targets, and the false-positive table at `0x84B29BCC`.
This proves partial local control transfer only; the patch is unapplied and
does not establish whole-function semantics or boot.

All 172 omitted instruction sites are also decoded and context-bound. A
standalone candidate translator patch restores 143 sites covering alias gaps,
saturating lane data, and straightforward integer/VMX state. A fresh isolated
full recompile leaves exactly 29 unsupported sites: 28 `frsqrte` operations
plus one `dcbst` whose treatment depends on final GPU/DMA coherency. A second
unapplied candidate now accounts for all 28 reciprocal-square-root sites. Its
IEEE value helper matches the pinned Xenia x64/A64 models across 2,065,536
inputs and all 12 checked-in native-runner-provenance vectors; an isolated
recompile removes all 28 omissions. This is not architecture-complete: dense
Xenon estimate bits, FPSCR state, enabled exceptions, and `NI` remain unproved,
and pinned Xenia backends disagree for NI-mode subnormals. A third isolated,
unapplied candidate closes the sole `dcbst` omission with exact RA0 effective
addressing, a 128-byte runtime-overridable cache-line hook, and an aborting
default. Its isolated regeneration passes all 237 generated C++ units. The
three candidates were then composed only in a temporary pinned translator
copy. Retail regeneration reduced the 172 baseline omission messages to zero,
and all 237 combined candidate units passed Clang 18 syntax checks. This is
emission coverage, not architecture-complete semantics or bootability: the
same opcode-only run retains 3,337 independent switch-boundary diagnostics.
The composed patch remains unapplied and outside the pinned vendor tree;
GPU/DMA/MMIO visibility, the separate `dcbf` policy, dense `frsqrte`/FPSCR/NI
behavior, and sticky `VSCR.SAT` remain unmodeled.

Validate with `bash tools/validate_apf_static_recomp_probe.sh` and
`bash tools/validate_apf_static_import_surface.sh` plus
`bash tools/validate_apf_static_recomp_all_tus.sh` and
`bash tools/validate_apf_static_recomp_link_probe.sh` plus
`bash tools/validate_apf_static_recomp_guest_image_bootstrap.sh` and
`bash tools/validate_apf_xex_dispatch_boundary.sh` plus
`bash tools/validate_apf_static_boot_import_frontier.sh` plus
`bash tools/validate_apf_boot_indirect_frontier.sh` plus
`bash tools/validate_apf_boot_leaf_adapters.sh` plus
`bash tools/validate_apf_imported_data_frontier.sh` plus
`bash tools/validate_apf_first_entry_readiness.sh` plus
`bash tools/validate_apf_static_recomp_opcode_switch_composed.sh` plus
`bash tools/validate_apf_guest_instruction_budget.sh` plus
`bash tools/validate_apf_guarded_first_entry_execution.sh` plus
`bash tools/validate_apf_second_boundary_static.sh` plus
`bash tools/validate_apf_guarded_second_boundary_execution.sh` plus
`bash tools/validate_apf_post_reserve_static.sh` plus
`bash tools/validate_apf_guarded_third_boundary_execution.sh` plus
`bash tools/validate_apf_post_commit_static.sh` plus
`bash tools/validate_apf_guarded_fourth_boundary_execution.sh` plus
`bash tools/validate_apf_post_process_type_static.sh` plus
`bash tools/validate_apf_guarded_fifth_boundary_execution.sh` plus
`bash tools/validate_apf_static_recomp_switch_tail_dispatch.sh` plus
`bash tools/validate_apf_static_recomp_opcode_audit.sh` plus
`bash tools/validate_apf_frsqrte_semantics.sh` plus
`bash tools/validate_apf_dcbst_semantics.sh` plus
`bash tools/validate_apf_static_recomp_opcode_composition.sh`; see
`docs/research/apf_static_recomp_probe.md` and
`docs/research/apf_static_import_surface.md` plus
`docs/research/apf_static_recomp_all_tus.md` and
`docs/research/apf_static_recomp_link_probe.md` plus
`docs/research/apf_static_recomp_guest_image_bootstrap.md` and
`docs/research/apf_xex_dispatch_boundary.md` plus
`docs/research/apf_static_boot_import_frontier.md` plus
`docs/research/apf_boot_indirect_frontier.md` plus
`docs/research/apf_boot_leaf_adapters.md` plus
`docs/research/apf_imported_data_frontier.md` plus
`docs/research/apf_first_entry_readiness.md` plus
`docs/research/apf_static_recomp_opcode_switch_composed.md` plus
`docs/research/apf_guest_instruction_budget.md` plus
`docs/research/apf_guarded_first_entry_execution.md` plus
`docs/research/apf_second_boundary_static.md` plus
`docs/research/apf_guarded_second_boundary_execution.md` plus
`docs/research/apf_post_reserve_static.md` plus
`docs/research/apf_guarded_third_boundary_execution.md` plus
`docs/research/apf_post_commit_static.md` plus
`docs/research/apf_guarded_fourth_boundary_execution.md` plus
`docs/research/apf_post_process_type_static.md` plus
`docs/research/apf_guarded_fifth_boundary_execution.md` plus
`docs/research/apf_static_recomp_switch_tail_dispatch.md` plus
`docs/research/apf_static_recomp_opcode_audit.md` plus
`docs/research/apf_frsqrte_semantics.md` plus
`docs/research/apf_dcbst_semantics.md` plus
`docs/research/apf_static_recomp_opcode_composition.md`.

## Current blockers to source-equivalent recompilation

1. Restore/split APF function boundaries and validate recovered PPC ABIs.
2. Turn the confirmed function clusters into typed shared modules, then expand
   outward through their callers instead of compiling raw decompiler output.
3. Finish scene materials, node transforms, skeletons, skinning, morphs, and
   animation for both titles; validate each result against original data.
4. Recover title state machines, finish the opaque roster/team fields, identify
   further scripts/configs, and recover the calls that bridge menu/game state
   into rendering, input, and audio.
5. Reimplement or replace remaining XDK/D3D behavior with Linux APIs and keep
   an address-specific `PORTME` for every unresolved guest operation.

Phase 2 is therefore address-complete at the ledger level and increasingly
semantic at the asset/renderer level, but it is not honestly complete as a
full native decompilation.

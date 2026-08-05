# 2K football Linux reverse-engineering workspace

This repository currently contains a native Linux **host/research shell** plus
binary-analysis work. The shell opens an SDL2 window, renders a small OpenGL
3.3 menu, accepts keyboard/gamepad navigation, hot-reloads a loose PNG, loads
and renders a loose glTF mesh with Assimp/OpenGL, and plays a loose PCM WAV
through OpenAL. `--menu nfl2k5` and `--menu apf2k8` also render typed,
host-only representations of the seven recovered frontend rows; their guest
addresses are retained as inert evidence and are never called. When the
user-owned derived NFL font assets are present, the NFL row labels use the
exact recovered `font7` atlas and metrics rather than the 5x7 host fallback.

It does **not** yet execute NFL 2K5 title code or reproduce either original
menu. A separate contained APF static-recomp test now executes 1,019 early
startup instructions through five typed platform calls, then stops; it is not
linked into the host shell and is not a title boot. Bounded NFL referee and APF
`player_shadow` clips now reach coordinate-converted animated skins in the
host, but complete materials, general animation graphs/root ownership,
gameplay state, and original frontend execution remain explicit `PORTME`
boundaries.

## Public mod-project editor preview

A first release-safe GUI scaffold now lives in [`mod_editor/`](mod_editor/).
Users create an NFL 2K5 or APF 2K8 project, select and hash their own source,
browse the research-owned capability registry, and queue named replacement
assets. The editor ships no game data, has no raw-offset field, and refuses
output overwrite. It can always make a verified **unmodified** staging copy.
Fixed providers can import, validate, build, and independently verify the
canonical NFL 2K5 unified-visual project, the one-to-three-target NFL 2K5
scorebug project, **all 850 fixed-contract standalone WAV targets** (849 generic
fixed-AUDO slots plus the separate `menu-back_01` route), and
APF 2K8 jersey-color, opaque 512x512 pants-color, raw two-channel helmet, and
1024x1024 RGBA shoulder-color recipes plus the shared 128x128 alpha-only
`digital_font` recipe. Every other patch backend remains disabled. Selecting
the APF jersey capability also enables a separate
read-only export to a new directory containing an editable base PNG, all nine
mip previews, and provenance; it exposes no raw archive selector and writes no
game data. Advanced gameplay,
AI, presentation, franchise, routing, and cross-title conversion ideas appear
with registry-derived `PROVED`, `READ ONLY`, or `PORTME` status and do not gain
edit actions unless the registry marks a reviewed writer. The GUI now exposes
**Inspect Mapped Data…** on supported read-only rows, backed by the same named,
hash-pinned commands available headlessly:

```sh
python3 -m mod_editor --inspect-gameplay-sliders nfl2k5
python3 -m mod_editor --inspect-draft-priority apf2k8
python3 -m mod_editor --inspect-nfl-franchise-limit all
python3 -m mod_editor --inspect-nfl-save-inventory
python3 -m mod_editor --inspect-main-menu nfl2k5
python3 -m mod_editor --create-apf-pants-recipe my-pants.json \
  --asset-index 13 --pants-png pants-opaque.png
python3 -m mod_editor --create-apf-helmet-recipe my-helmet.json \
  --asset-index 16 --helmet-png helmet-rg-data.png
python3 -m mod_editor --create-apf-shoulder-recipe my-shoulder.json \
  --asset-index 8 --shoulder-png shoulder-color.png
python3 -m mod_editor --create-apf-digital-font-recipe my-apf-font.json \
  --apf-digital-font-png white-rgb-alpha-font.png
python3 -m mod_editor --create-nfl-menu-back-audio-recipe my-menu-back.json \
  --purpose "Replace the fixed menu-back cue" --audio-wav menu-back.wav
```

These views omit executable addresses and distinguish exact ownership from a
safe writer. See
[`public_editor_scaffold.md`](docs/mod_editor/public_editor_scaffold.md) for
the boundary, launch command, and headless tests.

Main Menu label storage is now exact too. Neither game's seven Main labels is
owned by STRG/TXT localization; both routes copy direct executable literals.
NFL has a strict copied-XBE experiment for the seven fixed UTF-16LE slots and
an independent verifier, but recomputing the required `.string_` section digest
changes the RSA-signed header, leaving the retail signature invalid and runtime
acceptance unproved. APF's direct UTF-16BE slots remain read-only because no
verified extracted-PE-to-retail-XEX transport exists. See
[`main_menu_label_patch.md`](docs/research/main_menu_label_patch.md) and run
`bash tools/validate_nfl_main_menu_label_patch.sh`.

The NFL field-scorebug boundary is now independently closed at the disc-file
level. Nine `b/c/d/h/y/zscore_buga*` SCNE materials resolve through an exact
XBE table to the single 64x64 P8 `score_buga` atlas, while both ESPN materials
resolve to `shield_espn`. Strict PNG import and a layout-identical copied-XISO
proof pass with 2,169 target-only changed bytes; the typed editor provider also
composes `score_buga`, `shield_espn`, and `digital_font` into one copied-XISO
project. Separate isolated xemu demo-game runs visibly proved the magenta
`score_buga` frame atlas and cyan `shield_espn` strip on the live field HUD.
A magenta `digital_font` candidate also booted, but the shared atlas was not
visibly exercised in the captured no-input field-HUD/lower-third route, so its
visibility and global side effects remain unproved. APF's seven `global.iff` scorebug SCNE
components and separate
season/GameCast scorebug all export to glTF, but remain read-only until a
Xenon SCNE serializer/H7A repacker exists. Exact packages, replay/halftime
dependencies, audio boundaries, and PORTMEs are in
[`scorebug_presentation_modding.md`](docs/research/scorebug_presentation_modding.md).
The exact runtime boundary is in
[`nfl_scorebug_xemu_runtime.md`](docs/research/nfl_scorebug_xemu_runtime.md).
The separate shield boundary is in
[`nfl_scorebug_shield_xemu_runtime.md`](docs/research/nfl_scorebug_shield_xemu_runtime.md).

APF's separate shared `digital_font` path is now closed offline. A strict
128x128 white-RGB RGBA input supplies only the alpha channel encoded as tiled
Xenos DXT5A; the copy-only writer rebuilds `global.iff` inside a new `0A`, and
the independent verifier proves all 750 unrelated parts and all volume bytes
outside the target remain exact. The public
`apf2k8-digital-font-v1` provider accepts only a canonical content-pinned
`apf2k8_digital_font_recipe/v1`, fixes every writer/verifier argument, pins all
owning modules and the sole retail source, and emits a hash/metrics-only
verification artifact. Its scope is explicitly `shared-global-ui`: runtime
visibility, field-scorebug-only use, hardware behavior, the full set of global
consumers, and production encoder quality remain unproved. The machine-readable
format contract is
[`apf_digital_font_asset_format.v1.json`](reports/specs/apf_digital_font_asset_format.v1.json);
run `bash tools/validate_apf_digital_font_typed_provider.sh`.

The audio ceiling is now explicit as well. NFL exports and edits all 850
standalone `AUDO` records through exact fixed allocations: `menu-back_01` keeps
its separate route and 849 generic slots use the unified writer. For 697
alias-related rows, physical ownership is exact but the human/runtime cue
meaning remains unproved, so the UI warns instead of guessing. The default v4
batch template covers the complete canonical 850-sound inventory and adds a
spreadsheet-safe, read-only `AUDIO-CUE-MAP.csv` that joins generic replacement
paths to public names, families, exact WAV contracts, and honest meaning-status
codes. It still contains metadata only. Old complete v3 packs remain accepted,
the legacy 153-cue v1 pack stays byte-compatible, and v2 selected packs can
contain any 1–256 standalone cues or exact AUSB ranges. Each standalone detail
card now shows and copies its exact v4 all-850 destination, while streaming
ranges and raw banks intentionally omit that standalone-only action. A separate
Meaning confidence filter isolates the 1 Menu Back route, 152 reviewed labels,
or 697 provisional labels without presenting any exact Editable slot as unsafe
merely because its runtime meaning remains unproved. **Add all matching** can
atomically move any complete 1–256-row filtered standalone/range result into the
ordered shortlist, including the full 152 reviewed-label set for a v2 selected
authoring pack. The selected-sound inspector now scrolls complete technical and
ownership details while keeping WAV drop/play/export/replace/revert actions
pinned and reachable; exact IDs and paths remain selectable without alteration.
Its filter and shortlist toolbars now reflow into two rows so all 12 controls
fit the main window's supported minimum workspace without hiding or overlap.
Preview playback is source/selection-bound, discards stale asynchronous WAVs,
stops on a different row, and uses only a controllable Linux helper rather than
opening an external desktop player the app cannot stop.
Templates contain no game audio, and
shareable-project validation rejects decoded PCM matching standalone or indexed
streaming source audio. All 53,571 AUSB ranges are also fixed-slot Editable;
only complete streaming-bank repacking and recovered cue/loop/mixer semantics
remain unavailable. APF can export
standalone XMA1 `AUDO` and inventory-indexed `AUSB` substreams, but has no XMA1
encoder or audio writer. See
[`audio_modding_compatibility.md`](docs/research/audio_modding_compatibility.md),
the full [`NFL 2K5 capability matrix`](docs/research/nfl2k5_modding_capability_matrix.md),
the full [`APF 2K8 capability matrix`](docs/research/apf2k8_modding_capability_matrix.md),
and run `bash tools/validate_nfl_menu_back_audio_modding.sh` plus
`bash tools/validate_nfl_audo_import_capacity_audit.sh`.

## APF NFL/ESPN archaeology and first safe archive writer

The retail APF executable and archives now provide direct evidence for the
game's development lineage:

- the XEX identifies its original PE as
  `nfl_clean_opt_submission_ready.xex`, retains an
  `XENON/NFL/CLEAN_OPT/default.xex.pdb` path, and carries 24
  `vcsports/nfl/code/...` source paths;
- an exact 5,884-record animation-definition registry contains 519 distinct
  identifiers literally tagged `2K6`, referenced 597 times through fixed
  primary/paired-name fields and linked to 225 `.ani` filenames; all 597 map
  to unique concrete in-XEX motion roots, and 149 identifiers join 49 payload
  groups in selector arrays enumerated by compiled code;
- APF's converted `franchise.iff` preserves all 1,492 ordered NFL 2K5
  franchise text records, 1,106 pooled texts, and 21 complete layout
  sequences, while adding calendar, trade, weekly-preparation, and postseason
  resources;
- retail data includes recognizable NFL Draft/postseason art plus evolved
  SportsCenter, Chris Berman, and draft-room scenes;
- APF's converted `reference.iff` retains a directly bound NFL shield texture,
  438 valid reference/manual records, 987 exact ordered NFL 2K5 strings, and a
  matching compiled `REFR` relocation/load handler; that generic handler is
  registered at normal boot, but exhaustive static code and all-pack ownership
  scans classify the package itself as statically orphaned, unlike NFL 2K5's
  normal Extras → Reference Guide lifecycle;
- APF's converted `manual.iff` retains all 15 NFL 2K5 in-game manual pages and
  all 1,553 page string slots under renamed `xenon-*` resources; 1,544 strings
  match after two mechanical markup substitutions, while nine control,
  Weekly Prep, Crib, and Xbox Live edits plus a compiled 15-page initializer
  prove an authored next-generation conversion;
- APF's exact `pregameanims.iff` descendant retains giant AFC/NFC figures,
  their four directly bound 256×256 conference-logo textures converted from
  P8 to DXT1, near-identical geometry, and an ESPN/team-logo matchup graph;
  no package-specific static APF owner was found, while NFL 2K5 retains an
  explicit `PREGAME` load/resolve/release lifecycle;
- APF retains a compiled `Sound Test` state, `AudioTestMenu` transition,
  `gamesound` layout binding, three substantial callbacks, and ten converted
  glowball/speaker/cursor/audio resources from NFL 2K5's wired Audio Test.
  APF's seven-row Options table removes the corresponding row, while direct
  whole-image pointer/materialization scans classify the retained state as a
  bounded static orphan;
- APF also retains a converted three-state NFL 2K5 `Basic Training` subsystem:
  six tutorial callbacks, normal and crippled pause loops, a called 796-byte
  update routine, a function-table-owned `dir_tutorial.iff` loader, and all
  101 NFL tutorial strings. The proved descriptor routes remain internal and
  no conventional fixed producer of the required APF mode value 4 was found,
  so this is code-connected cut-mode lineage rather than a playable hidden
  tutorial claim;
- both retail executables retain the exact developer note that the challenge
  presentation is a placeholder pending prettier camera cuts. NFL uses it in
  the formatter at `0x001B1420`; APF preserves the corresponding two-way
  formatter at `0x8486FC70` with a direct caller chain. Both also retain tiny
  `Hello World` pointer getters with no direct static callers found by the
  bounded scans. This is shared unfinished-presentation evidence, not a
  hidden mode or formal NFL 2K6 product identity; and
- compiled APF-adapted franchise code, nine old `FranchiseMenu_*` descriptors,
  exact archive requests, and a live Season-to-old-Gameplan edge prove this is
  not an assets-only residue.

The boundary is equally important: no exact formal product/build identity
proves a complete game titled `NFL 2K6`; the animation name table itself has
no recovered direct code owner; known direct callers do not reach one examined
2K6 movement configuration; the standalone Coach's Desk initializer has no
static owner; and the Wrapup request graph has no proved retail root. A
complete hidden playable franchise is therefore not claimed.
The retained reference book is more narrowly classified: ordinary static APF
code and all four serialized packs contain no owner edge for it. “Statically
orphaned” does not exclude deliberately synthesized addresses or external
runtime injection.
`pregameanims.iff` is a slightly weaker static-orphan candidate: its exact
names/hashes also have no external APF owner, but dynamic construction,
enumeration, or indirect index access remains possible through generic MRKS
support.
The Sound Test finding and its exact NFL ancestor are documented in
[`apf_audio_test_remnant.md`](docs/research/apf_audio_test_remnant.md); no
runtime APF screen is claimed.
The more substantial three-state Basic Training remnant and its complete
NFL 2K5 tutorial corpus are documented in
[`apf_basic_training_remnant.md`](docs/research/apf_basic_training_remnant.md);
no external APF frontend route or runtime tutorial screen is claimed.
The shared challenge-camera placeholder and paired `Hello World` getter
residue are documented in
[`challenge_placeholder_lineage.md`](docs/research/challenge_placeholder_lineage.md);
no cut camera sequence or runtime visibility is claimed.
An external Xenia pointer experiment is now known to load and remain boot-safe,
but mandatory first-run team creation blocked access to Season, so the patched
Coach's Desk destination itself is still unobserved.

The first copy-only APF writer is also validated. It replaces the hidden
128×128 `draft_logo` PNG in outer 810, rebuilds Xenos tiled BC3, H7A and IFF
metadata, preserves all 158 unrelated inner parts, and can patch only a newly
created copy of the user's 1.1 GB `0A` volume. It refuses source overwrite and
emits a hash manifest without bundling retail pixels. Live uniforms are the
next proved target: the Americans' live-selected 1024×1024 jersey now has a
separate copy-only writer that regenerates all nine levels, including the
three-level Xenos packed tail, and passes zero-error per-level decode-back plus
a fixed-allocation 1.1 GB copied-volume round trip. A solid-magenta copied
archive now has a matched runtime proof in Xenia at the actual Americans Home
Jersey editor. The untouched retail model is navy/red; the patched model is
visibly pink/magenta in the same bounded torso region. This proves that outer
875 / `uniform_jersey_06.iff` / `jersey_color` is loaded through the rebuilt
archive and controls the live 3D jersey. The solid-color probe does not yet
stand alone: a red/cyan asymmetric source produces a large spatially varying
white/red response on the same jersey, proving that `jersey_color` behaves as
a channel-weight/material mask rather than a conventional diffuse RGBA image.
An otherwise RGB-identical rebuild with all 1,048,576 source alpha bytes set
to zero remains visibly opaque and closely matches that mask response. Thus
conventional straight-alpha opacity does not control this target; the broader
claim that the shader never reads alpha is not made. Exact full-pattern UV
orientation, fine detail, distant-mip behavior, Xbox 360 hardware parity, and
a production-quality perceptual BC3 backend remain unproved.
The same descriptor/layout proof now spans all 24 retail jersey packages:
every nine-level transport is bit-exact, and a controlled solid-color
H7A/IFF rebuild fits every fixed allocation in memory. The public CLI is now
available for all 24 asset indices with independent retail hash pins and
copy-only target selection. Arbitrary detailed PNG fit is fail-closed rather
than guaranteed, and runtime visibility is proved only for the Americans'
solid-color target above. A separate 25-case
path-safety gate now proves that manifests, rebuilt entries, and copied
volumes remain bound to their exclusively created descriptors/inodes even if
their pathnames are replaced mid-write.

A first whole-XEX static-recompilation probe also completed. After removing 22
deterministic impossible switch-table results, XenonRecomp produced 237 C++
files (236 translated-code units plus one function-map unit), and representative
units pass Clang 18 syntax checks. A subsequent complete audit now proves all
237/237 generated C++ files pass Clang 18 with zero diagnostics. This is not a
native boot: 3,337 cross-function switch violations, 172 sites across
11 missing instruction semantics, 347 XEX imports, and the complete
Xenos/XMA/title runtime remain unresolved. Static recompilation is therefore a
promising CPU-translation accelerator, not a finished Linux port.
The generated external boundary is now exact as well: 334 callable
XAM/xboxkrnl thunks, 13 imported data slots, and 1,708 static call sites. The
current host adapters are deliberately not guest-ABI implementations.
A full object/link probe also closes mechanically: 237 generated objects plus
two support objects link with zero unresolved guest symbols. Its 334 imports
are fail-fast abort traps, its harness only counts mappings, and title entry is
never called, so it is explicitly not a native game boot.
A bounded loader checkpoint now goes one step farther without executing title
code: it verifies and maps the exact 54,001,664-byte decoded image in a sparse
4 GiB guest space, checks all nine PE sections, and initializes all 60,731
host-function mappings. It leaves all 13 imported-data slots unresolved and
does not call `_xstart`. The apparent PE/dispatch overlap is now reconciled:
all 824 XEX security descriptors sum to exactly `0x03380000`, both pinned
XenonRecomp and Xenia load only that authoritative span, and the dispatch table
starts at its exclusive end with zero loaded-title-byte overlap. The remaining
runtime rule is to reserve `[0x85380000,0x86133000)` from guest allocation/MMIO
or move the table to host-only storage.
A subsequent frontier-specific audit closes the minimum imported-data subset
without pretending all 13 objects exist. Ghidra finds 46 direct reads, but only
`XexExecutableModuleHandle` and `KeDebugMonitorData` have consumers in the
current 458-node frontier. An isolated transactional bootstrap now seeds those
two while preserving the other 11 ordinal words byte-exact. The executable
module chain points to a separate arena copy of the exact raw `XEX2` header
prefix—never the decoded `MZ` image at `0x82000000`—and the debugger-disabled
cell is null, so its `+0x18` callback cannot dispatch. This composes with the
bounded header-field adapter and returns null for APF's absent
`DEFAULT_HEAP_SIZE`; it still does not call `_xstart` or resolve the other 11
out-of-frontier data imports.
A separate nonexecuting call-graph gate narrows the first runtime-adapter lane.
The 60,397-implementation corpus has 85,643 unique direct edges; unrestricted
direct traversal from `_xstart` reaches 6,917 nodes and 151 callable imports.
Stopping at title main `sub_84B8B1D0` and post-main `sub_84BDAC80` reduces this
to 103 nodes and 27 imports. This is a path-insensitive planning frontier: it
retains failure/destructor branches and initially omitted 15 indirect sites.
Ten of those sites now have exact entry-context proofs spanning 254 edges and
253 unique targets. Following only those proved edges expands the planning
frontier to 458 nodes and 30 imports; five original and two newly exposed
second-wave indirect calls remain address-specific `PORTME`s. This is still
not a dynamic boot trace.
The first isolated Linux guest-ABI slice now accounts for all 87 direct import
sites in that augmented 30-import frontier: 24 bounded adapters cover 76
sites, four typed terminal adapters cover eight, `RtlRaiseException` requires
future guest exception dispatch at two, and `ExCreateThread` produces one
typed, non-resumable scheduler handoff. Zero direct sites remain generically
unsupported. Four separately proved indirect TLS dispatches are also supported.
The bounded adapters include explicit guest-thread TLS, required
XConfig/process/language/AV values, overflow-safe big-endian memory,
`RtlInitAnsiString`, documented `RtlCompareMemoryUlong` byte semantics, and a
scheduler-aware uncontended/recursive critical-section candidate. They also
handle the one exact post-main `DbgPrint` as a typed one-`s32` event and
bounds-check APF's exact retail XEX2 header before returning null for its
absent `DEFAULT_HEAP_SIZE` field; generic variants remain fail-fast. This layer
now also implements all 19 direct 64 KiB VM sites behind exact LR/flag gates,
with a loader-configured collision-free page ledger/backing arena, mapped-range
exclusions, transactional BE outputs, zero/`NOZERO`, decommit/release/query,
and sign-extended NTSTATUS failures. The exact four-site event/handle/wait
group now uses Xenon-namespace handles, reference-counted named events,
manual/auto-reset semantics, transactional BE handle writes, and an explicit
nonblocking scheduler boundary for pending waits; no Linux host thread sleeps.
The sole reached `RtlNtStatusToDosError` site now maps exactly the two negative
statuses its current event/wait predecessors can produce—invalid handle to 6
and no memory to 8—and fails closed for every other status/site instead of
guessing error 317.
The sole reached `XamShowMessageBoxUIEx` call is now an explicit host-UI
boundary: it validates and copies the exact one-button UTF-16 request, latches
the requesting context, and resumes only after a host explicitly selects
button zero. Completion writes the bounded 28-byte overlapped result and
signals the original event; no default choice is fabricated. The generic UIEx
ABI, its opaque `r10`, and its eight-byte result object remain deliberately
unclaimed. The final direct import, `ExCreateThread`, now validates and latches
its exact reached handle/stack/TID/start/context/flag request as
`thread_create_requested`. It deliberately provides no completion API and
creates no guest handle, stack, object, CPU state, host thread, or guest
execution until a real scheduler owns lifecycle. A second non-frontier thread
site that immediately references, reprioritizes, resumes, and dereferences six
suspended CPU-affined threads remains explicitly rejected.
An isolated first-entry readiness harness now composes the exact decoded guest
image, the two-slot imported-data bootstrap, the 30-import typed adapter, the
generated Xenon mapping table, loader stack/thread/config state, bounded budget
ledger, and child-process crash/timeout containment. Static execution-order
proof reaches `_xstart -> sub_84BF1950 -> sub_84BF1850 -> RtlImageXexHeaderField`;
the first typed call is at `0x84BF1888` with LR
`0x84BF188C`. No opcode gap, unresolved switch-tail occurrence, or unresolved
indirect call precedes that boundary. A throwaway link installs all 60,731
mappings and verifies all 30 typed bridge pointers, but the gate deliberately
does not call `_xstart`: its two historical ordered blockers were a single
corpus containing both candidate families and per-executed-guest-instruction
budget instrumentation. Both now exist as separately hash-pinned derived
trees. A v2 driver revalidates the old gate and both complete trees, then calls
generated `_xstart` only in a forked, crash/timeout-contained child. That run
executed exactly 38 guest instructions and one typed dispatch, ending at
`RtlImageXexHeaderField` call `0x84BF1888` / LR `0x84BF188C` with `r3=0`.
The bridge threw immediately after the adapter, so no generated continuation
ran. This is the first bounded translated-title execution, not a boot or menu.
It is tested independently and is not linked into the normal shell; scheduler
deadline/signal/APC wakeups, host VM page protection, general kernel objects, SEH, imported
data beyond the two reached slots, and the seven unresolved indirect
dispatches remain `PORTME`.
A second game-startup checkpoint now follows the exact null-result branch from
that first call through 226 additional translated instructions. The contained
test reaches `NtAllocateVirtualMemory` at `0x84BED7B8` after 264 cumulative
guest instructions and two typed platform calls. Its existing Linux adapter
reserves the requested 1 MiB at guest address `0x40000000`, updates the two
big-endian result cells, and leaves the reserved backing unchanged; the test
then stops before the next translated instruction. Static and dynamic ordered
PC traces agree exactly. This remains early startup compatibility—not a title
boot, renderer, menu, or playable game.
A third checkpoint revalidates that exact reserve ledger and backing pattern,
executes the next proved 19 instructions, and reaches the 64 KiB commit call at
`0x84BED808`. The typed adapter commits and zeroes the first page while the
remaining 15 pages stay reserved and byte-pattern intact, then the bridge
stops before `0x84BED80C`. The cumulative trace is 283 guest instructions and
three typed calls; it still does not establish a title boot or menu.
A fourth checkpoint matches the next 82-instruction static proof, initializes
the committed page's eight absolute-link nodes and descriptor fields, and
reaches `KeGetCurrentProcessType` at `0x84BED908`. The typed adapter returns
configured process type 1, and the bridge stops before `0x84BED90C`. The
cumulative trace is 365 guest instructions and four typed calls, with one page
committed and 15 still reserved; this is not a boot or menu.
A fifth checkpoint follows the exact 654-instruction allocator-list path from
that return. It stores process type 1, initializes 128 self-linked allocator
heads, and reaches `RtlInitializeCriticalSection` at `0x84BED954` with
`r3=0x40000610`. The existing typed adapter writes the exact 28-byte Xbox
critical-section state and the bridge stops before `0x84BED958`. The cumulative
trace is 1,019 guest instructions and five typed calls; this still proves
neither native boot nor a menu.
An isolated switch-tail candidate now repairs 2,261 of the 3,337 baseline
cross-function dispatch occurrences: 1,998 are exact generated-function tails
and 263 are conservatively recovered, Ghidra-body-gated entries. All 237
candidate translation units pass syntax checking. The remaining 1,076
occurrences span 190 unique address-specific `PORTME`s, so this is partial
local control-transfer closure—not a title boot or whole-function semantic
proof.
The 172 omitted instruction sites are now fully classified. One validated,
unapplied translator patch restores 143 sites. A second isolated candidate
accounts for all 28 `frsqrte` sites with the pinned Xenia estimate table and
matches 2,065,536 differential inputs plus 12 native-runner-provenance vectors.
A third isolated candidate closes the sole `dcbst` omission with exact RA0
addressing, a 128-byte runtime hook, and fail-closed default behavior; all
237 regenerated C++ units pass syntax checking. The three candidates now also
compose cleanly in a throwaway pinned translator tree: regeneration reports
zero omitted instructions and all 237 units remain syntax-clean. The composed
patch is unapplied and not architecture-complete. Xenon estimate
identity/FPSCR/`NI`, GPU/DMA/MMIO cache visibility, the distinct `dcbf` path,
and sticky `VSCR.SAT` remain architecture-level work.

```sh
bash tools/validate_apf_2k6_animation_lineage.sh
bash tools/validate_apf_2k6_animation_runtime.sh
bash tools/validate_apf_nfl_cut_content_lineage.sh
bash tools/validate_apf_nfl_wrapup_followup.sh
bash tools/validate_apf_reference_nfl_remnants.sh
bash tools/validate_apf_reference_runtime_owner.sh
bash tools/validate_apf_manual_nfl_remnants.sh
bash tools/validate_apf_pregame_conference_remnants.sh
bash tools/validate_apf_pregameanims_static_ownership.sh
bash tools/validate_apf_softdrinktv_video_brief.sh
tools/validate_apf_franchise_runtime_ownership.sh
bash tools/validate_apf_xenia_season_coachdesk_experiment.sh
bash tools/validate_apf_texture_patch.sh
bash tools/validate_apf_uniform_mip_patch.sh
bash tools/validate_apf_jersey_family_layout.sh
bash tools/validate_apf_jersey_family_patch.sh
bash tools/validate_apf_writer_path_safety.sh
bash tools/validate_apf_uniform_xenia_runtime.sh
bash tools/validate_apf_uniform_pattern_xenia_runtime.sh
bash tools/validate_apf_uniform_pattern_alpha0_xenia_runtime.sh
bash tools/validate_apf_static_recomp_probe.sh
bash tools/validate_apf_static_import_surface.sh
bash tools/validate_apf_static_recomp_all_tus.sh
bash tools/validate_apf_static_recomp_link_probe.sh
bash tools/validate_apf_static_recomp_guest_image_bootstrap.sh
bash tools/validate_apf_xex_dispatch_boundary.sh
bash tools/validate_apf_static_boot_import_frontier.sh
bash tools/validate_apf_boot_indirect_frontier.sh
bash tools/validate_apf_boot_leaf_adapters.sh
bash tools/validate_apf_imported_data_frontier.sh
bash tools/validate_apf_first_entry_readiness.sh
bash tools/validate_apf_static_recomp_opcode_switch_composed.sh
bash tools/validate_apf_guest_instruction_budget.sh
bash tools/validate_apf_guarded_first_entry_execution.sh
bash tools/validate_apf_second_boundary_static.sh
bash tools/validate_apf_guarded_second_boundary_execution.sh
bash tools/validate_apf_post_reserve_static.sh
bash tools/validate_apf_guarded_third_boundary_execution.sh
bash tools/validate_apf_post_commit_static.sh
bash tools/validate_apf_guarded_fourth_boundary_execution.sh
bash tools/validate_apf_post_process_type_static.sh
bash tools/validate_apf_guarded_fifth_boundary_execution.sh
bash tools/validate_apf_static_recomp_switch_tail_dispatch.sh
bash tools/validate_apf_static_recomp_opcode_audit.sh
bash tools/validate_apf_frsqrte_semantics.sh
bash tools/validate_apf_dcbst_semantics.sh
bash tools/validate_apf_static_recomp_opcode_composition.sh
```

The archaeology reports are
[`apf_2k6_animation_lineage.md`](docs/research/apf_2k6_animation_lineage.md),
[`apf_2k6_animation_runtime.md`](docs/research/apf_2k6_animation_runtime.md),
[`apf_nfl_cut_content_lineage.md`](docs/research/apf_nfl_cut_content_lineage.md),
[`apf_nfl_wrapup_followup.md`](docs/research/apf_nfl_wrapup_followup.md),
[`apf_reference_nfl_remnants.md`](docs/research/apf_reference_nfl_remnants.md),
[`apf_manual_nfl_remnants.md`](docs/research/apf_manual_nfl_remnants.md),
[`apf_pregame_conference_remnants.md`](docs/research/apf_pregame_conference_remnants.md),
and [`apf_franchise_runtime_ownership.md`](docs/research/apf_franchise_runtime_ownership.md).
The bounded runtime experiment is documented in
[`apf_xenia_season_coachdesk_experiment.md`](docs/research/apf_xenia_season_coachdesk_experiment.md).
Modding proofs are in
[`apf_texture_roundtrip.md`](docs/research/apf_texture_roundtrip.md),
[`apf_uniform_mip_roundtrip.md`](docs/research/apf_uniform_mip_roundtrip.md), and
[`apf_jersey_family_layout.md`](docs/research/apf_jersey_family_layout.md) plus
[`apf_jersey_family_patch.md`](docs/research/apf_jersey_family_patch.md) and
[`apf_uniform_xenia_runtime.md`](docs/research/apf_uniform_xenia_runtime.md),
with the non-solid channel-mask and alpha-zero runtime isolations in
[`apf_uniform_pattern_xenia_runtime.md`](docs/research/apf_uniform_pattern_xenia_runtime.md)
and
[`apf_uniform_pattern_alpha0_xenia_runtime.md`](docs/research/apf_uniform_pattern_alpha0_xenia_runtime.md).
Their byte-exact historical controller binding is frozen in
[`apf_xenia_controller_capture_provenance.md`](docs/research/apf_xenia_controller_capture_provenance.md).
The destructive-path contract is documented separately in
[`apf_writer_path_safety.md`](docs/research/apf_writer_path_safety.md).
Static-recompilation checkpoints are
[`apf_static_recomp_probe.md`](docs/research/apf_static_recomp_probe.md),
[`apf_static_import_surface.md`](docs/research/apf_static_import_surface.md),
[`apf_static_recomp_all_tus.md`](docs/research/apf_static_recomp_all_tus.md),
[`apf_static_recomp_link_probe.md`](docs/research/apf_static_recomp_link_probe.md),
[`apf_static_recomp_guest_image_bootstrap.md`](docs/research/apf_static_recomp_guest_image_bootstrap.md),
[`apf_xex_dispatch_boundary.md`](docs/research/apf_xex_dispatch_boundary.md),
[`apf_static_boot_import_frontier.md`](docs/research/apf_static_boot_import_frontier.md),
[`apf_boot_indirect_frontier.md`](docs/research/apf_boot_indirect_frontier.md),
[`apf_boot_leaf_adapters.md`](docs/research/apf_boot_leaf_adapters.md),
[`apf_imported_data_frontier.md`](docs/research/apf_imported_data_frontier.md),
[`apf_first_entry_readiness.md`](docs/research/apf_first_entry_readiness.md),
[`apf_static_recomp_opcode_switch_composed.md`](docs/research/apf_static_recomp_opcode_switch_composed.md),
[`apf_guest_instruction_budget.md`](docs/research/apf_guest_instruction_budget.md),
[`apf_guarded_first_entry_execution.md`](docs/research/apf_guarded_first_entry_execution.md),
[`apf_second_boundary_static.md`](docs/research/apf_second_boundary_static.md),
[`apf_guarded_second_boundary_execution.md`](docs/research/apf_guarded_second_boundary_execution.md),
[`apf_post_reserve_static.md`](docs/research/apf_post_reserve_static.md),
[`apf_guarded_third_boundary_execution.md`](docs/research/apf_guarded_third_boundary_execution.md),
[`apf_post_commit_static.md`](docs/research/apf_post_commit_static.md),
[`apf_guarded_fourth_boundary_execution.md`](docs/research/apf_guarded_fourth_boundary_execution.md),
[`apf_post_process_type_static.md`](docs/research/apf_post_process_type_static.md),
[`apf_guarded_fifth_boundary_execution.md`](docs/research/apf_guarded_fifth_boundary_execution.md),
[`apf_static_recomp_switch_tail_dispatch.md`](docs/research/apf_static_recomp_switch_tail_dispatch.md),
[`apf_static_recomp_opcode_audit.md`](docs/research/apf_static_recomp_opcode_audit.md),
[`apf_frsqrte_semantics.md`](docs/research/apf_frsqrte_semantics.md), and
[`apf_dcbst_semantics.md`](docs/research/apf_dcbst_semantics.md), plus the
combined gate in
[`apf_static_recomp_opcode_composition.md`](docs/research/apf_static_recomp_opcode_composition.md).
The video evidence manifest and 1920×1080 cards are under
`reports/cut_content/apf_nfl_lineage/`. The concise, claims-graded SoftDrinkTV
publication brief—with title, 10-minute outline, exact narration, pinned
visuals, and statements to avoid—is
[`apf_softdrinktv_video_brief.md`](docs/research/apf_softdrinktv_video_brief.md).

## Linux dependencies

Ubuntu/Debian:

```sh
sudo apt-get install build-essential cmake pkg-config python3 \
  libsdl2-dev libgl1-mesa-dev libglew-dev libopenal-dev libpng-dev \
  libassimp-dev
```

Fedora:

```sh
sudo dnf install gcc cmake pkgconf-pkg-config python3 SDL2-devel \
  mesa-libGL-devel glew-devel openal-soft-devel libpng-devel assimp-devel
```

## Build and run

From the repository root:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DVC_PORT_STRICT=ON
cmake --build build --parallel
./build/vc_football_port
```

The default loose-asset root is `assets/mod/common`. From another working
directory, pass it explicitly or set the environment variable:

```sh
./build/vc_football_port --assets "$PWD/assets/mod/common"
VC_FOOTBALL_ASSETS="$PWD/assets/mod/common" ./build/vc_football_port
```

Preview any Blender-exported glTF/GLB—or one of the recovered static scene
collections—without copying it over the default fixture:

```sh
./build/vc_football_port \
  --model assets/intermediate/apf2k8/models/0899_0021_online_titlebar.gltf
VC_FOOTBALL_MODEL="$PWD/models/my_player.gltf" ./build/vc_football_port
```

For a full-frame inspection render without the host menu, add `--model-only`;
it requires an explicit `--model` or `VC_FOOTBALL_MODEL`:

```sh
./build/vc_football_port --model models/my_scene.gltf --model-only
```

Inspect the recovered-row host models (these do not execute guest state):

```sh
./build/vc_football_port --menu nfl2k5
./build/vc_football_port --menu apf2k8
```

Arrow keys/W/S or a gamepad D-pad navigate. Enter/Space or gamepad A selects;
Escape, gamepad B/Back, or the Quit item exits. A screenshot implies a one-frame
smoke run unless `--smoke` supplies another positive frame count:

```sh
./build/vc_football_port --smoke 3 --screenshot /tmp/host-menu.png
```

OpenAL is optional at runtime; if no device is available, the shell continues
muted. `assets/mod/common/audio/menu_select.wav` is played for menu movement
and selection when available. Replace it with any mono/stereo PCM8 or PCM16
RIFF/WAV. A working OpenGL 3.3 display is required.

## Loose asset overrides

Replace `assets/mod/common/ui/team_logo.png` with an RGB/RGBA PNG. It is checked
for changes every 500 ms; F5 explicitly reloads the PNG, glTF, and WAV overrides.
This generates two redistributable examples:

```sh
python3 tools/create_placeholder_assets.py --variant navy
python3 tools/create_placeholder_assets.py \
  --variant gold --output /tmp/gold-assets/ui/team_logo.png
./build/vc_football_port --assets /tmp/gold-assets
```

Export a Blender model as glTF 2.0 to
`assets/mod/common/models/player.gltf`. The shell validates it, uploads its
triangle meshes, evaluates standard node transforms, inverse binds, joint
weights, and the first glTF node animation on the CPU, then renders a fitted
rotating preview. A deterministic one-joint fixture proves exact translation
at 0, 0.5, and 1 second and exercises the animated OpenGL upload. This standard
glTF host seam also accepts the first bounded title-derived NFL referee local-
rotation witness described below. It still does not connect either title's
complete root motion, animation graph, materials, uniforms, face scans, or
morphs; those broader recovered-title semantics remain `PORTME`.
The `--model`/`VC_FOOTBALL_MODEL` override accepts an arbitrary path and F5
reloads that same file, including its relative external buffers.

Generate or replace the loose menu sound with standard audio tools:

```sh
python3 tools/create_placeholder_audio.py
```

`ui/team_logo.png`, optional `models/player.gltf`, and optional
`audio/menu_select.wav` are connected today. NFL's recovered row font is a
separate, user-owned loose pair:

```sh
./build/vc_football_port --menu nfl2k5 \
  --nfl-font-atlas assets/intermediate/nfl2k5/fonts/font7.png \
  --nfl-font-metrics assets/intermediate/nfl2k5/fonts/font7.metrics.tsv \
  --nfl-tm-icon assets/intermediate/nfl2k5/textures/outer_0003_8ee9eeed/0047_tm.png
```

The same files may be placed at `ui/nfl2k5_font7.png` and
`ui/nfl2k5_font7.metrics.tsv` under any `--assets` root, or selected through
`VC_NFL2K5_FONT7_ATLAS` / `VC_NFL2K5_FONT7_METRICS`. Both are hot-reloaded.
The exact `|TM|` object may likewise be placed at `ui/nfl2k5_tm.png`, selected
with `--nfl-tm-icon`, or set through `VC_NFL2K5_TM_ICON`; it hot-reloads too.
The installable `assets/mod/common` tree contains only override schemas, not
extracted retail pixels. The native path is explicitly a recovered host
representation: original LAYT placement, the other inline texture slots,
renderer state, live/default state ownership, and boot execution remain
addressed `PORTME`s.

There is no validated loose schema yet for uniforms, rosters, teams, players,
leagues, stadiums, or face assignments. Adding those now would invent formats;
they will be documented and exposed after the corresponding game data and call
sites are recovered. Keep original bytes in `assets/raw`, lossless derived data
in `assets/intermediate`, and redistributable/user-created overrides in
`assets/mod`.

## Recovered binary and asset artifacts

The research outputs are deliberately separate from the redistributable host
shell. APF 2K8's current Ghidra corpus covers all 21,347 final functions under
`research/functions/apf2k8/`; validate it with:

```sh
bash tools/validate_apf_function_recovery.sh
```

NFL 2K5's outer packs now have a bounded resource scan and a fully validated
base-level texture conversion. It locates 57,208 `TXTR` objects—even when they
follow `Unif`, `TSET`, `AUDO`, or `SCNE` resources or occupy zero-padded fixed
slots—and converts all five observed layouts to PNG without a decode error.
The 1.2 GiB derived tree is `assets/intermediate/nfl2k5/textures/`; it includes
logos, face scans, uniform art/normal maps, UI textures, stadium strips, and
name atlases. Rebuild and verify it with:

```sh
python3 tools/nfl_resource_scan.py \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json reports/assets/nfl2k5_resource_chunks_v2.json
python3 tools/nfl_all_texture_inventory.py \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --resource-scan reports/assets/nfl2k5_resource_chunks_v2.json \
  --json reports/assets/nfl2k5_all_txtr_inventory_v2.json \
  --tsv reports/assets/nfl2k5_all_txtr_inventory_v2.tsv \
  --validate-conversion \
  --png-dir assets/intermediate/nfl2k5/textures \
  --jobs 12
bash tools/validate_nfl_texture_pipeline.sh
```

See `docs/research/nfl_texture_pipeline.md` for the executable addresses,
resource/LZ/descriptor layouts, format evidence, and remaining `PORTME`
regions. These converted proprietary assets are not installed or presented as
redistributable defaults. Texture assignment and loose override schemas beyond
the host logo remain blocked on the surrounding recovered game data.

NFL's complete uniform layer is now structurally joined to that texture
corpus. All 634 packages form 317 exact `H`/`A` pairs across 85 asset codes;
each package has one `Unif`, ten `TSET`, 41 standalone `TXTR`, and one `NAME`
object. The strict reports cover 32,334 embedded textures, 25,994 standalone
textures, 18,386 glyph metrics, executable filename/CRC construction, roster
asset-code links, and runtime HOME/AWAY material binding. All 317 paired logo
RGBA hashes agree, and a 51-PNG embedded-texture smoke export passes:

```sh
bash tools/validate_nfl_uniform_inventory.sh
```

See `docs/research/nfl_uniforms.md`. This establishes exact lookup and asset
relationships; unknown selectors and material/mesh binding details remain
`PORTME`. A first copy-only writer now changes only the two proved raw `Unif`
color words in the Lions' current home/away packages. It rebuilt a new XISO
with automatic XBE media patching disabled, then listed, re-extracted, and
reparsed it: all four magenta words survived, `default.xbe` and all 17
unrelated files stayed byte-exact, and all retail inputs remained unchanged.
The rebuilt filesystem boots, but a first Quick Game experiment was initially
misclassified as a reset: an untouched-retail audit reproduced the same
title/attract flow. No archive rejection or layout incompatibility is inferred
from those frames. A second writer independently makes
a sector-identical copy of the retail XISO and patches the original `A`/`B`
extents in place. Its complete 6.3 GB comparison proves the original root
sector, all 20 entries/LBAs/extents, XBE, and every byte except the ten intended
changed positions remain exact. A separate three-byte, layout-identical
retail-donor copy now reaches rendered Demo Mode gameplay in an isolated xemu
0.8.135 run, proving modified-disc/archive acceptance for that exact artifact.
Every input in that bounded audit was focus verified; Demo Mode to Main Menu is
reproducible. A later exact controller mapping established that START, not A,
on highlighted Quick Game reaches Team Select deterministically. Static
ownership proves the edited word colors conditional `HI_turtleneck`, not the
large jersey torso, so no visible uniform change is claimed. A third
layout-identical path now copies the complete equal-sized `jersey00` /
`jersey00_mud` TSET from Falcons AWAY into Lions current HOME without
recompression. Its exact 73,304-byte-difference XISO reaches a deterministic
Jaguars-at-Lions Current Uniform screen. Ten animated preview samples retain
the retail Lions torso and never show the Falcons-away donor pattern,
proving that the observed Team Select path did not visibly sample the patched
span; that screen result alone does not identify a different retail owner.
Separately, a
deterministic bounded
VC-LZ encoder reproduces eight representative shipped streams byte-for-byte
and rebuilds the exact fixed 74,688-byte body with independent decode checks.
The first real PNG importer now converts a strict 512×256 RGBA image into all
six 512×256-through-16×8 mip levels, a deterministic Xbox P8 palette/index
chain, inverse NV2A swizzle, separate clean/mud palettes, and a recompressed
74,720-byte `09H0` TSET span. Its 32-color `CODEX MOD` fixture is lossless and
uses 22,285 compressed bytes, leaving 52,403 verified zero bytes. A copy-only
direct writer now places that exact span into a new layout-identical XISO. A
full 6.3 GB comparison finds exactly 70,333 changed bytes in 3,265 runs, all
inside the one target span; the root sector, all paths/LBAs/extents/sizes,
`default.xbe`, pack 0, and every unrelated byte remain exact. Independent
re-extraction matches all six clean and six mud mips to the importer previews.
The exact PNG-derived disc now boots through the same deterministic route,
cycles from Current to 2000–2003 and back, and reaches coin toss plus a live
formation. Detroit still renders its retail uniform and never the large
`CODEX MOD` diagnostic. This proves disc/import runtime acceptance while
retaining a negative visibility result for that legacy artifact; no visible
Lions mod or model writer is claimed from it. A later loader-faithful audit
shows why its separately valid 22,285-byte stream was not runtime-safe: the
game reads the fixed body into the tail of a shared output allocation and
decompresses forward in place, but the rebuilt wrapper retained only 32 bytes
of overlap scratch where that stream needs 52,392. The original capture remains
a preserved negative control rather than evidence against the static binding.
The Detroit checks are exposed as a
copy-only command for strict 512×256 RGBA8 non-interlaced PNG art, including an
optional compatible mud PNG or deterministic mud mode. A second noncanonical
fixture produces a distinct layout-identical disc with 70,303 changed bytes
confined to its target span.

That writer is no longer structurally Detroit-only. A complete audit re-read,
decoded, descriptor-parsed, and retail-XISO-matched chunk 1 from every one of
the 634 HOME/AWAY jersey packages (317 pairs). All 634 share one supported P8
six-mip layout, while retaining 346 distinct fixed VC-LZ allocation classes
from 31,872 through 126,704 bytes across packs `9`, `A`, `B`, and `C`. The
generalized workflow takes an exact two-digit asset code, HOME/AWAY side, and
variant; derives every archive/XISO offset from the hash-pinned inventory; and
fails without output if the selected target's compressed allocation cannot
hold the artwork. Span fixtures cover `00H0`, `27A0`, and the smallest
allocation `30H2`; an independently verified full `27A0` XISO changes 73,127
bytes, all inside its selected span. This proves safe offline jersey-TSET
replacement for the audited layout, not runtime material binding, pants,
sleeves, equipment, models, or arbitrary incompressible art.

Uniform sleeve chunk 3 is now a separate proved family rather than an
assumption inherited from the torso importer. All 634 HOME/AWAY packages were
independently decoded and XISO-matched. They share one `sleeve00` /
`sleeve00_mud` 128×128 P8 layout with five independently swizzled mips, a
21,824-byte shared index chain, two palettes, and a universal zero 64-byte
inter-palette gap. Target transport remains exact: 466 chunk offsets, 193
stored sizes from 5,648 through 20,496 bytes, and 275 scratch/allocation
classes. A deterministic diagnostic rebuild passes both loader-alias guards
for all 634 selectors. The smallest target, `06H2`, also completed independent
PNG-to-span-to-copy-only-XISO verification: 1,837 encoded bytes, 3,811 zero
padding, and exactly 5,229 changed image bytes confined to its selected span.
This is an offline mod path; xemu sleeve visibility has not yet been tested or
claimed.

Uniform pants chunk 2 is now independently proved across the same complete
634-package selector corpus. All entries share one `pants00` /
`pants00_mud` 512×256 P8 layout with six independently swizzled mips, a
174,720-byte shared index chain, and two contiguous palettes. The audit pins
341 exact chunk offsets, 298 stored sizes from 61,328 through 118,880 bytes,
324 scratch/allocation classes, and the exact retail in-place alias
requirement for every stream. A synthetic non-retail fixture fits all 634
targets. The smallest target, `84H0`, completed independent
PNG-to-span-to-copy-only-XISO verification with 22,284 encoded bytes, 39,044
bytes of zero padding, and 58,509 changed bytes confined to its selected span.
No emulator was started and pants runtime visibility is not claimed.

Live 3D player helmets now have a separate proved path from the pre-rendered
Team Select `helm_*` cards. Every one of the 634 HOME/AWAY uniform keys carries
chunk-11 `helmet00` and chunk-12 `helmet02`; the XBE routes player helmet modes
0 and 1 to `HI_HELMET_A`/`HELMET_A_accessories` and
`HI_HELMET_C`/`HELMET_C_accessories`, respectively, then writes the selected
texture pointer to material record `+0x30`. All 1,268 compressed TXTRs share
one 256×256 P8 six-mip layout while retaining 367 exact fixed allocation
classes from 26,496 through 46,768 stored bytes. A strict PNG importer and
plan-driven copy-only XISO writer/verifier carry non-retail Detroit-away
fixtures into both geometry families. The retained proof has SHA-256
`682c689de24efdcff6c33deeef665dc81d4aba2186c098779aea737355a5030b`;
exactly 71,407 bytes change inside the two target spans, all XDVDFS extents and
`default.xbe` remain exact, and the retail source remains unchanged. No
emulator was started and live helmet replacement visibility is not claimed.

Live 3D player numbers and generated nameplates now have their own complete
offline art pipeline. Across all 634 uniform selectors, chunks 13–42 contain
19,020 context-local digit glyphs: `48..57` for front/back jersey numbers,
`hn48..hn57` for helmets, and `an48..an57` for arm/shoulder numbers. Chunk 43
is the 32×1024 six-mip linear `names` atlas; chunk 44 is its separate 29-record
metric object. The XBE trace closes digit composition and the
`PLAYERNAME`/`PLAYERNAME_long` generated-texture route. All 19,654 pixel
resources match the retail XISO, use one of four exact descriptor layouts, and
pass fixed-span VC-LZ/alias validation. A strict all-mip PNG importer plus
plan-driven copied-XISO writer/verifier carries four non-retail Detroit-away
fixtures—jersey, helmet, arm digit 5, and nameplate atlas—into a retained copy
with SHA-256
`905a395131a86d6a8c7ef36fb6b9b463e80b37e0816d88eb17527fb9229cc6a2`.
Exactly 12,084 bytes change inside the selected spans; all XDVDFS extents and
`default.xbe` remain exact. The `NAME` metrics stay read-only because the
physical unit of word 0 and index 28 are not yet proved. Runtime visibility of
the new fixtures is not claimed.

The standalone Team Select card surface is now independently writable too.
All 1,902 concrete `unif_%s%s_%1d` / `helm_%s%s_%1d` resources join exactly
to the 634 side/team/style selectors: 634 uniform cards at 256×256 and two
same-name helmet classes at 256×256 and 128×128. Every card is a raw,
single-mip P8 `TXTR` with a fixed index/palette allocation and zero VC-LZ
scratch/alias requirements. A strict PNG importer and separate plan-driven
copy-only XISO writer/verifier carry deterministic non-retail Detroit-away
style-0 `unif_a09_0` and `helm_a09_0` fixtures into a retained 6.3 GB proof.
Its SHA-256 is
`0c368e253421dc97d35dd49324f89e4caf8994f8c10f67d9c5685907c46bdba6`;
exactly 131,816 bytes change inside the two video allocations, while all 19
XDVDFS files/extents and `default.xbe` remain exact. This is an offline
transport proof; Team Select runtime visibility for the replacements is not
claimed.

Created-team gameplay field branding is now another independently closed
visual-art lane. The retail XBE constructs `ct%s%c.iff` from the active-team
logo-code field and dry/rain/snow state, registers it as `CTGRAPHIC`, and maps
its `center_logo` plus six exact `endzone_*` TXTR names into the live `field`
material table. A separate pinned `goalpost`/`pad` path binds `pad_north` and
`pad_south`, so all nine package textures now have explicit material-owner
evidence. All 126 packages (42 logo codes × three weather variants) and
all 1,134 P8 textures are enumerated: 1,125 fixed-span VC-LZ resources and nine
raw exceptions, each with complete swizzled mip/palette layouts. A strict PNG
importer and separate copy-only XISO writer/verifier carry a synthetic
`ct67D` north-middle end-zone panel into a retained disc whose SHA-256 is
`a698055f9da7809f039e8569b963f6803c30ed2e6657b6c9ad1f20193296d441`.
Exactly 38,156 bytes differ inside the one target span; XDVDFS,
`default.xbe`, and every non-target byte remain retail-exact. This closes the
created-team field path, not stock stadium signage, and no runtime visibility
is claimed. See
[`nfl_create_team_field_art_pipeline.md`](docs/research/nfl_create_team_field_art_pipeline.md).

Live-player face/head textures are now separated from portraits, cards, crowd
heads, and replay-highlight `h####.iff` files. All 624 matched IDs have exact
`f####`, `h####`, `n####`, and `s####` ownership: `f` is a raw six-mip DXT1
face texture in the aggregate, `h` and `n` are compressed one-mip DXT1
face/neck textures in `pf####.iff`, and `s` is SHAP head geometry. All 1,872
texture spans and all 624 shape spans match retail. A deterministic opaque
DXT1 importer and three-edit `0124:f/h/n` copied-XISO proof change exactly
97,048 bytes with every other byte and `default.xbe` unchanged. SHAP remains
read-only and no runtime visibility is claimed. See
[`nfl_live_face_texture_compatibility.md`](docs/research/nfl_live_face_texture_compatibility.md).

Those eleven proved visual/data surfaces now compose through one public-safe v1
project file instead of separate full-disc workflows.
`tools/nfl2k5_visual_mod_project.py` accepts torso, sleeve, pants, live-helmet,
live digit/nameplate, Team Select, live `f/h/n` face texture, and create-team
field-art edits, plus same-allocation main-table team identity, fixed-size
primary-player name/jersey edits, and numeric roster portraits. It explicitly
rejects SHAP and exposes no raw offsets, team/roster pointers, guessed ratings,
XBE colors, allocation, relocation, or executable/gameplay patch bytes.
Existing importers remain unchanged; retail is copied once and the complete
union is verified without a giant changed-offset set. The retained
eleven-family proof exercises 13 project edits expanded to 19 non-overlapping
physical spans and changes exactly 428,469 bytes; portrait `4070` deliberately
crosses packs 3 and 4. Its 6,300,499,968-byte output SHA-256 is
`67b7d52d8fc7fa84eb3cdd86f53a0e6009175d5c34cfbd5782354de478342376`.
Independent `verify` reconstructs the replacements from the project/PNGs and
pinned compatibility inventories rather than trusting the build manifest. It
confirms all bytes outside the union are retail-exact, the XDVDFS tree/extents
and `default.xbe` are unchanged, and all 75 normalized reports/previews match.
The nine-family and original six-family v1 projects still verify unchanged, so
no migration is required. New kinds remain provider-owned and hash-pinned;
future gameplay/AI/mode/XBE work cannot enter the public schema as a raw-offset
escape hatch. No emulator was started and combined runtime visibility is not
claimed. See
[`nfl2k5_unified_visual_mod_project.md`](docs/research/nfl2k5_unified_visual_mod_project.md).

A later address-led XBE trace proves the intended player-material binding.
Detroit current HOME formats `09h0.iff`
into the `HOME` context; cache slots 7/8 are context-first `jersey00`; and body
binder `0x0008EBB0` writes those slots to `UNIF_jersey`. The same routine maps
slot 9 `sleeve00` to `UNIF_sleeve`. All 53 `09H0` resource chunks, all 92
logical textures, the shared `lo_body`/`hi_body`/`hi_head` materials, and the
three standalone number families were independently re-read. The recovered
`0x451D0 -> 0x45280 -> 0x45100` loader chain now proves that both legacy PNG
spans overwrite unread compressed input under the game's in-place layout. An
offline change only to wrapper `+0x14`—52,416 for HOME or 56,816 for AWAY—
eliminates the collision and preserves the intended decoded hash. The exact
retail `01A0` donor is already alias-safe, so its negative result remains a
separate registry/context/cache contradiction rather than proof of another
torso texture or persistent cache. The single-span legacy `09A0` AWAY
discriminator now reaches Lions at Giants on Current Uniform, coin toss, and
live DET-at-NYG play. Detroit again retains retail-looking art and never shows
the cyan/magenta/yellow `CODEX MOD` fixture. That exact capture is preserved,
but its insufficient 16-byte scratch means it cannot discriminate
HOME-versus-AWAY selection; no visible torso mod is claimed from it. Its
corrected successor raises wrapper `+0x14` to 56,816 while preserving the fixed
79,120-byte on-disc TSET span. The v3 artifact has XISO SHA-256
`5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d`
and passes the independent loader-alias and copy-only workflow checks. In a
fresh cache-cleared xemu overlay, all 13 Team Select samples remain
retail-looking, but the injected magenta/cyan/green diagnostic appears on
Detroit's live coin-toss players. This proves `09A0` chunk 1 controls the live
Detroit current-AWAY torso. The Team Select owner is now closed separately:
the screen formats and loads standalone 256×256 pre-rendered P8 cards
`unif_a09_0` (outer 3102/chunk 195) and `helm_a09_0` (outer 3102/chunk 790),
then binds them to flat SCNE material planes. Image registration and the exact
compiled material-write path agree, so the live `09A0` TSET is not expected to
change that preview. The session ended after the coin-toss capture: gameplay
after coin toss was not captured or claimed.

```sh
mkdir -p /media/noah/Storage/nfl2k5-mods
PYTHONPATH=tools python3 tools/nfl2k5_uniform_jersey_png_workflow.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --target-code 09 --target-side H --target-variant 0 \
  --clean-png /path/to/detroit-home-512x256-rgba.png \
  --mud-mode darken_60 \
  --output-xiso /media/noah/Storage/nfl2k5-mods/game.xiso.iso \
  --manifest /media/noah/Storage/nfl2k5-mods/manifest.json \
  --preview-dir /media/noah/Storage/nfl2k5-mods/previews
```

The parallel sleeve command accepts exact 128×128 RGBA8 PNG input:

```sh
PYTHONPATH=tools python3 tools/nfl2k5_uniform_sleeve_png_workflow.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --target-code 09 --target-side A --target-variant 0 \
  --clean-png /path/to/sleeve-128x128-rgba.png \
  --mud-mode darken_60 \
  --output-xiso /media/noah/Storage/nfl2k5-mods/sleeve-game.xiso.iso \
  --manifest /media/noah/Storage/nfl2k5-mods/sleeve-manifest.json \
  --preview-dir /media/noah/Storage/nfl2k5-mods/sleeve-previews
```

The pants command accepts exact 512×256 RGBA8 PNG input:

```sh
PYTHONPATH=tools python3 tools/nfl2k5_uniform_pants_png_workflow.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --target-code 84 --target-side H --target-variant 0 \
  --clean-png /path/to/pants-512x256-rgba.png \
  --mud-mode darken_60 \
  --output-xiso /media/noah/Storage/nfl2k5-mods/pants-game.xiso.iso \
  --manifest /media/noah/Storage/nfl2k5-mods/pants-manifest.json \
  --preview-dir /media/noah/Storage/nfl2k5-mods/pants-previews
```

The live-helmet workflow accepts exact 256×256 RGBA8 PNGs. Edit both
`helmet00` and `helmet02` plan rows for complete A/C geometry-family coverage:

```sh
PYTHONPATH=tools python3 tools/nfl_live_helmet_txtr_xiso_workflow.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --plan assets/fixtures/nfl2k5/live_helmet/detroit_away_both_families_plan.json \
  --output-xiso /media/noah/Storage/nfl2k5-mods/live-helmet-game.xiso.iso \
  --manifest /media/noah/Storage/nfl2k5-mods/live-helmet-manifest.json \
  --preview-dir /media/noah/Storage/nfl2k5-mods/live-helmet-previews
```

```sh
bash tools/validate_nfl_uniform_color_xiso.sh
bash tools/validate_nfl_uniform_color_xiso_direct.sh
bash tools/validate_nfl_unif_color_ownership.sh
bash tools/validate_nfl_uniform_xemu_runtime.sh
bash tools/validate_nfl_jersey_tset_donor_xiso_direct.sh
bash tools/validate_nfl_jersey_tset_xemu_runtime.sh
bash tools/validate_nfl_vc_lz_compressor.sh
bash tools/validate_nfl_tset_png_import.sh
bash tools/validate_nfl_tset_png_import_xiso_direct.sh
bash tools/validate_nfl2k5_jersey_png_workflow.sh
bash tools/validate_nfl_jersey_tset_compatibility.sh
bash tools/validate_nfl_sleeve_tset_compatibility.sh
bash tools/validate_nfl_pants_tset_compatibility.sh
bash tools/validate_nfl_live_helmet_txtr_compatibility.sh
bash tools/validate_nfl_create_team_field_art_pipeline.sh
bash tools/validate_nfl_team_identity_audit.sh
bash tools/validate_nfl_live_face_texture.sh
bash tools/validate_nfl_live_numbers_nameplate_pipeline.sh
bash tools/validate_nfl_team_select_card_pipeline.sh
bash tools/validate_nfl2k5_visual_mod_project.sh
bash tools/validate_nfl_actual_jersey_binding.sh
bash tools/validate_nfl_actual_jersey_binding_away_xemu_runtime.sh
bash tools/validate_nfl_tset_loader_alias_audit.sh
bash tools/validate_nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.sh
```

See
[`nfl_uniform_color_xiso.md`](docs/research/nfl_uniform_color_xiso.md) and
[`nfl_uniform_color_xiso_direct.md`](docs/research/nfl_uniform_color_xiso_direct.md),
plus the ownership and runtime checkpoints in
[`nfl_unif_color_ownership.md`](docs/research/nfl_unif_color_ownership.md) and
[`nfl_uniform_xemu_runtime.md`](docs/research/nfl_uniform_xemu_runtime.md).
The complete jersey donor path and corrected deterministic runtime result are
documented in
[`nfl_jersey_tset_donor_xiso_direct.md`](docs/research/nfl_jersey_tset_donor_xiso_direct.md)
and
[`nfl_jersey_tset_xemu_runtime.md`](docs/research/nfl_jersey_tset_xemu_runtime.md).
The preserved legacy HOME PNG diagnostic route through live play is in
[`nfl_lions_png_import_xemu_runtime.md`](docs/research/nfl_lions_png_import_xemu_runtime.md).
The fixed-span compressor and bounded PNG import contract are documented in
[`nfl_vc_lz_compressor.md`](docs/research/nfl_vc_lz_compressor.md) and
[`nfl_tset_png_import.md`](docs/research/nfl_tset_png_import.md); the exact
copy-only disc insertion is in
[`nfl_tset_png_import_xiso_direct.md`](docs/research/nfl_tset_png_import_xiso_direct.md).
The end-user GIMP export contract and original Detroit workflow are in
[`nfl2k5_jersey_png_workflow.md`](docs/research/nfl2k5_jersey_png_workflow.md).
The all-634 compatibility audit, selector contract, generalized command, and
per-target allocation boundary are in
[`nfl_jersey_tset_compatibility.md`](docs/research/nfl_jersey_tset_compatibility.md).
The independently constrained all-634 sleeve layout, 128×128 PNG contract,
fixed-span writer, and unresolved xemu diagnostic are in
[`nfl_sleeve_tset_compatibility.md`](docs/research/nfl_sleeve_tset_compatibility.md).
The corresponding all-634 pants layout, exact loader-alias audit, 512×256 PNG
contract, and frozen copy-only XISO proof are in
[`nfl_pants_tset_compatibility.md`](docs/research/nfl_pants_tset_compatibility.md).
The create-team live midfield/end-zone/pad selector, all 126 weather/logo
packages, strict PNG importer, and independently verified copied-XISO proof are
in
[`nfl_create_team_field_art_pipeline.md`](docs/research/nfl_create_team_field_art_pipeline.md).
The 624 live face/head ID sets, 1,872 writable `f/h/n` DXT1 textures, read-only
SHAP ownership, deterministic PNG importer, and three-edit copied-XISO proof
are in
[`nfl_live_face_texture_compatibility.md`](docs/research/nfl_live_face_texture_compatibility.md).
The actual live-player `helmet00`/`helmet02` binding, all-1,268 compatibility
audit, strict six-mip PNG importer, and two-family copied-XISO proof are in
[`nfl_live_helmet_txtr_compatibility.md`](docs/research/nfl_live_helmet_txtr_compatibility.md).
The all-selector live digit/nameplate owner trace, 19,654-resource layout
audit, strict PNG importer, and four-edit copied-XISO proof are in
[`nfl_live_numbers_nameplate_pipeline.md`](docs/research/nfl_live_numbers_nameplate_pipeline.md).
The exact torso/sleeve/digit dataflow, full Detroit resource revalidation,
legacy-negative reconciliation, and corrected positive AWAY result are in
[`nfl_actual_jersey_binding.md`](docs/research/nfl_actual_jersey_binding.md).
The separate pre-rendered Team Select cards, formatted TXTR lookup path,
dynamic material binding, and runtime-to-resource image joins are in
[`nfl_team_select_preview_owner.md`](docs/research/nfl_team_select_preview_owner.md).
The complete 1,902-card layout/duplicate audit, strict PNG importer, and frozen
copy-only Detroit card proof are in
[`nfl_team_select_card_pipeline.md`](docs/research/nfl_team_select_card_pipeline.md).
The additive v1 nine-family project schema, one-copy union writer,
independent reconstruction verifier, and fourteen-span retained proof are in
[`nfl2k5_unified_visual_mod_project.md`](docs/research/nfl2k5_unified_visual_mod_project.md).
The insufficient-scratch discriminator's isolated Team Select, coin-toss, and
live-gameplay negative remains preserved as a historical control in
[`nfl_actual_jersey_binding_away_xemu_runtime.md`](docs/research/nfl_actual_jersey_binding_away_xemu_runtime.md).
The recovered loader equations, exact HOME/AWAY unread-source collisions,
retail/donor controls, and scratch-only correction proof are in
[`nfl_tset_loader_alias_audit.md`](docs/research/nfl_tset_loader_alias_audit.md).
The corrected XISO's positive live-player coin-toss evidence, 13-frame retail
Team Select control, fresh-overlay cache isolation, and explicit no-gameplay
boundary are in
[`nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.md`](docs/research/nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.md),
with the complete hash/crop/workflow regression in
[`validate_nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.sh`](tools/validate_nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.sh).

APF's complete uniform catalog is now joined to its roster selectors as well.
Twelve XEX filename families resolve exactly to 517 normal IFF packages with
1,332 textures. All 40 team records point to two 14-selector banks, giving
1,120 unique aligned selector records and exact package mappings for slots
2–12. A separate custom `uniform_logocache.iff` directory accounts for all 236
logo cache entries (118 `l0`/`l1` pairs), for 518 uniform-related resources in
total. Six representative Americans assets, including the flying-eagle logo,
decode to PNG:

```sh
bash tools/validate_apf_uniform_inventory.sh
bash tools/validate_apf_uniform_selector_allocation.sh
```

See `docs/research/apf_uniforms.md` and
`docs/research/apf_uniform_selector_allocation.md`. The hash-pinned selector
planner now covers all eleven filename-owned slots / twelve physical families,
computes maximum-distinct minimum-change plans for the 24 built-ins and all 40
slots, and proves the combined 190-byte built-in plan fits the fixed ROST H7A
allocation with 496 bytes left. That exact 11-family/24-built-in plan now has a
family-aware fail-closed copied-`0A` writer and separately implemented
whole-volume verifier: 95 team/family assignments become 190 both-bank
byte-zero changes, every online/user selector remains exact, and the rebuilt
payload reproduces the 435,528-byte capacity witness. The CLI admits no
arbitrary family recipe and remains hidden from the production editor pending
a matched non-jersey Xenia witness. Selector slots 0/1/13, selector bytes 1–7,
bank orientation, online/user authoring, runtime consumption, and logo-cache
lifecycle remain explicit `PORTME` work. See
`docs/research/apf_uniform_selector_writeback.md` and run
`bash tools/validate_apf_uniform_selector_patch.sh`.

NFL 2K5 standalone audio is also recovered: all 850 `AUDO` chunks validate as
Xbox IMA ADPCM and have been converted to PCM16 WAV under
`assets/intermediate/nfl2k5/audio/` (806 mono, 44 stereo). Rebuild and verify
the full loose corpus with:

```sh
python3 tools/nfl_scene_probe.py \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --kind AUDO --all \
  --wav-dir assets/intermediate/nfl2k5/audio \
  --output reports/assets/nfl2k5_audo_wav_all.json
bash tools/validate_nfl_full_audio.sh
bash tools/validate_nfl_audo_import_capacity_audit.sh
```

See `docs/research/nfl_scene_audio_assets.md` for SCNE/TSET/SHAP/SKEL/audio
evidence, the exact whole-corpus allocation/alias matrix, and unresolved bank,
loop, mixer, runtime-owner, and geometry fields. The capacity audit is
metadata-only and does not enable a generic AUDO writer.

The deeper NFL `SCNE` pass now validates all 4,616 scenes: 54,966 shapes,
276,642 submeshes, 55,905 materials, 70,555 nodes, and 37,389 embedded P8
textures. Every observed NV2A draw stream and vertex reference is bounded.
All 37,389 embedded-texture occurrences now decode to a deterministic,
deduplicated catalog of 5,351 standard RGBA8 PNGs under
`assets/intermediate/nfl2k5/scne_textures/`. Exact scene/material occurrence
links are retained for all 55,905 material records: 45,413 have a proved
`+0x30` texture-descriptor link and 10,492 retain a null link. This proves
provenance and makes the images directly editable in GIMP/Blender; it does not
yet prove shader stage, UV set, sampler state, or that any linked image is a
base-color texture. Rebuild or validate the catalog with:

```sh
bash tools/validate_nfl_scne_embedded_texture_png.sh
```

The position path now exports 4,007 Blender-readable static scene collections
containing every one of the 54,966 shapes: 46,192 `FLOAT3` plus 8,774
instruction-proved `NORMSHORT3`. The corpus contains 276,642 retained submesh
primitives, 13,731,388 positions, and 24,139,104 glTF indices under
`assets/intermediate/nfl2k5/models/`; only 609 genuinely zero-shape scenes are
withheld. The compressed decode combines Xbox signed-short normalization with
the serialized scale/offset proved through the relocator, render constant
upload, and common MAD in all 13 static shaders. All 8,014 model files and the
manifest pass a full archive re-decode/byte comparison. A 143-shape stadium
collection independently loads in the Linux host as 562 Assimp primitives,
and an all-`NORMSHORT3` font collection uploads 973 vertices and 7,521 triangle
indices through the same Assimp/OpenGL path.
Run:

```sh
bash tools/validate_nfl_scne_inventory.sh
bash tools/validate_nfl_normshort3_positions.sh
bash tools/validate_nfl_static_gltf.sh
bash tools/validate_nfl_scne_static_format_spec.sh
```

See
`docs/research/nfl_scne_layout.md`,
`docs/research/nfl_scne_embedded_texture_png.md`,
`docs/research/nfl_normshort3_positions.md`, and
`docs/research/nfl_static_gltf.md`. The editable scene PNG catalog is not yet
bound to glTF materials because shader/UV/sampler semantics remain unproved;
non-position attributes, complete hierarchy ownership, animation, morphs, and
general reverse writing also remain explicitly withheld.

The serializer boundary is now frozen independently of the exporter in
[`nfl2k5_xbox_static_scne.v1.json`](reports/specs/nfl2k5_xbox_static_scne.v1.json).
It specifies the outer archive, VC-LZ wrapper, SCNE descriptor/tables, shape
and submesh records, vertex declarations/streams, FLOAT3/NORMSHORT3 inverse
rules, NV2A push grammar, fixed-allocation policy, no-op identity, and
same-count position-only contract without embedding retail geometry. A writer
is not claimed by the spec alone. Separately, the first narrowly pinned NFL
write-back witness is now closed for `stadium` shape `group36`: exactly four
little-endian `FLOAT3` positions can be replaced in a copied volume 9 while
the count, 12-byte stride, secondary stream, selectors, `cement01` material,
`QUADS [0,1,2,3]` topology, opaque tail, archive extents, and every unrelated
byte remain fixed. A no-op preserves the complete volume byte-for-byte, and an
independent verifier re-derives the authored 48 decoded bytes and all preserved
regions. Run
`bash tools/validate_nfl_stadium_group36_position_patch.sh`; see
`docs/research/nfl_static_position_writeback.md` and
`reports/assets/nfl_stadium_group36_position_patch_roundtrip.json`.

That one-target proof has now been generalized within the same stadium SCNE.
A hashes-only catalog authorizes 75 additional mechanically rigid `FLOAT3`
targets, and the v2 dispatcher derives each exact count/span from the pinned
catalog. Shape 1 `upper_deck` is the second full copied-volume witness: 12
positions, a byte-identical no-op, and a public all-zero edit changing exactly
144 authorized decoded bytes. Its VC-LZ rebuild consumes 908,799 / 908,864
bytes and independently derives `0x60` scratch while preserving the fixed
tail and every byte outside the resource. Run
`bash tools/validate_nfl_stadium_static_target_catalog.sh` and
`bash tools/validate_nfl_stadium_catalog_position_patch.sh`; see
`docs/research/nfl_stadium_static_target_catalog.md`,
`docs/research/nfl_stadium_catalog_position_writeback.md`, and
`reports/assets/nfl_stadium_catalog_position_patch_roundtrip.v2.json`.

`upper_deck` is also the first changed-count writer boundary. The original
machine-readable control contract remains frozen at its pre-writer state, while
a separate closure proves copied-volume count-8 and count-4 output with
synchronized whole-record source subsets across both active streams, exact
physical tails, fixed allocation, and an independently implemented verifier.
A metadata-only authoring conformer now accepts two or four oriented triangles
expressed solely as pinned source-record IDs, proves they partition uniquely
into native quads, preserves winding, and emits the existing writer recipe; it
does not accept new vertex or attribute values. Bounds/culling, collision/LOD
ownership, arbitrary geometry, and runtime acceptance were left open by that
adapter. A follow-on executable and 54,966-shape corpus audit now proves the
render bound: shape `+0x00..+0x0c` is a local homogeneous sphere center and
`+0x48` is its radius, consumed by the node camera/frustum test. The unchanged
`upper_deck` sphere contains all 12 source vertices and therefore every
admitted four/eight-record subset. No general sphere serializer, collision/LOD
owner, arbitrary-position import, or runtime witness follows. Run
`bash tools/validate_nfl_upper_deck_changed_count_spec.sh`,
`bash tools/validate_nfl_stadium_upper_deck_subset_patch.sh`, and
`bash tools/validate_nfl_upper_deck_source_triangle_conformance.sh`, and
`bash tools/validate_nfl_scne_bounds_ownership.sh`; see
`docs/research/nfl_upper_deck_changed_count_boundary.md`,
`docs/research/nfl_upper_deck_source_subset_writeback.md`, and
`docs/research/nfl_upper_deck_source_triangle_conformance.md`, and
`docs/research/nfl_scne_bounds_ownership.md`.

The first same-footprint native-topology loop is also closed offline for
`group36`. A separate writer preserves the four vertices and the complete
seven-word native `QUADS` command footprint while replacing the four existing
`ARRAY_ELEMENT16` IDs; it may also use the already-authorized four-position
lane. The nonretail proof combines all-zero positions with a nondegenerate
index permutation, changes 50 decoded bytes only in the two authorized spans,
and fits VC-LZ at 908,830 / 908,864 bytes with exact `0x40` scratch. A
topology-only permutation over retail positions is mechanically valid but
does not fit this compressed fixture and is correctly refused before output.
Run `bash tools/validate_nfl_stadium_group36_geometry_patch.sh`; see
`docs/research/nfl_group36_same_footprint_geometry_writeback.md`,
`docs/research/static_topology_conformance_gap.md`, and
`reports/assets/nfl_stadium_group36_same_footprint_geometry_roundtrip.json`.
The exact independently verified changed SCNE span can now also be transported
into a layout-identical copied XISO. The transport reparses XDVDFS, preserves
all extents and `default.xbe`, compares the complete 6,300,499,968-byte disc,
and proves every difference lies in one authorized 908,912-byte span. Run
`bash tools/validate_nfl_stadium_group36_geometry_xiso.sh`; see
`docs/research/nfl_group36_geometry_xiso_transport.md` and
`reports/specs/nfl2k5_group36_geometry_xiso_transport.v1.json`. That exact XISO
separately reached rendered title and attract-mode gameplay in xemu 0.8.135,
which proves archive/boot acceptance only. The edited `s42nd.iff` target was not
proved loaded, so geometry visibility remains false. These catalog, topology,
and transport results remain hidden offline tooling: they do not prove semantic
target ownership, edited-glTF import, changed counts, auto-decimation, general
stadium or helmet replacement, original-Xbox hardware acceptance, or production
readiness.

NFL motion storage is now structurally bounded rather than skipped. All 4,559
`SMCD` and 639 `MMCD` resources re-read from the archive, accounting for
60,930,224 body bytes, 6,068 standalone or embedded 52-byte roots, and 18,375
unique pointer-bounded packed regions. XBE load/release callbacks prove the
common header, four field-local root pointers, and `MMCD`'s counted 16-byte
child directory; every body reconstructs exactly. A downstream sampler trace
now proves frame addressing, frame-major smallest-three quaternions, signed
short trajectory records scaled by 0.125, terminated fixed-point events,
logical-channel iteration, and the optional 12-byte-per-frame stream. The full
corpus validates 14,073,985 main packed rotations, 567,075 trajectories, 9,024
events, and 17,311 optional records. A portable native C implementation of
`default.xbe:0x000DED10` is compiled into the Linux host. Its signed-10
extraction, omitted-lane placement, positive unit reconstruction, invalid
radicand rejection, and exact mirror sign-bit changes are tested independently;
the corpus validator compares all 14,091,296 main-plus-optional packed words
with the executable-derived reference. Maximum observed portable/reference
errors are `1.16e-07` per lane and `1.23e-07` for the radicand. It explicitly
does not claim bit identity with the unresolved original x87 helper at
`0x000DEB00`.

The shared interpolator at `0x003CA270` is now instruction-proved and compiled
as `src/recovered/nfl2k5/quaternion_interpolation.c`. It preserves the exact
shortest-path sign rule, strict `0x3F7FF2E5` linear threshold, fixed 16-bit
turn-angle quantization, all 256 recovered sine-table entries, extrapolation,
and the original lack of output normalization. Nine edge vectors plus a
65,546-vector native/reference grid pass; maximum stored-lane error is zero
and maximum weight error is `5.97e-08`. Original-Xbox x87 control-word/80-bit
bit identity remains explicitly unclaimed. See
`docs/research/nfl_quaternion_interpolation.md`.

`src/recovered/nfl2k5/motion_pose_sample.c` now composes those proved pieces
for one logical channel: binary32 time-to-frame addressing, null or signed
two-byte channel-map selection, packed decode, the recovered interpolator,
numbered-lane mirroring, and final-frame clamp. Its independent archive gate
drives three cases through every one of the 6,068 shipped roots—18,204 native
samples spanning 14,959 distinct packed words. It exercises 7,919 linear and
4,217 fixed-table interpolation cases plus 38 shortest-path negations, with
zero output-lane error and `2.98e-08` maximum weight error against the semantic
model. A title-policy wrapper additionally checks all 6,068 real flag sets:
the eight bit-0 looping clips use the controller's repeated-duration
subtraction, while 696 bit-2 clips select the mirrored map/output path.
Skeleton pose application and root motion remain explicit boundaries rather
than guessed runtime behavior; the later axis/root trace now closes the
coordinate and concrete player-root portions of that boundary.

Executable object-list initialization now
also proves both non-identity 25-pair signed-byte channel maps: one enables 23
logical channels and the shared second map enables 21. Their normal and mirror
packed-index domains are dense involutions, with exact disabled and bilateral
channel sets retained:

```sh
bash tools/validate_nfl_motion_inventory.sh
bash tools/validate_nfl_motion_sampler.sh
bash tools/validate_nfl_quaternion_interpolation.sh
bash tools/validate_nfl_motion_channel_maps.sh
bash tools/validate_nfl_motion_object_pools.sh
bash tools/validate_nfl_bone_binding.sh
bash tools/validate_nfl_rest_orientation.sh
bash tools/validate_nfl_raw_skin_gltf.sh
bash tools/validate_nfl_axis_root_motion.sh
bash tools/validate_nfl_coach_ref_pose_native.sh
bash tools/validate_nfl_player_pose_native.sh
bash tools/validate_nfl_player_clip_ownership.sh
bash tools/validate_nfl_ref_clip_ownership.sh
bash tools/validate_nfl_referee_animated_gltf.sh
bash tools/validate_nfl_referee_root_trajectory.sh
bash tools/validate_nfl_referee_render_root.sh
```

The sampler validator also compiles
`src/recovered/nfl2k5/trajectory.c` and compares it with all 567,075 shipped
root-motion records. All 451,676 compact six-byte records and 115,399
eight-byte records match their signed-short fields and exact one-eighth-scaled
floats. The follow-on executable/field/skeleton trace now proves those lanes as
X=lateral, Y=up, Z=longitudinal in centimeters. The optional fourth short is a
turn about +Y at `1/8192` revolution per raw step and is promoted by
`signed_short << 3` into 65,536 turn units.

Root-motion composition is also exact for the concrete player path. The
interval helper returns `[X1-X0, Y1 absolute, Z1-Z0, t1-t0, turn1-turn0]`—the
Y lane is intentionally not a delta—and mirroring negates X and turn. The
player builder rotates in XZ, adds X, `Y-100`, and Z to the root matrix, then
expands the proved row-vector hierarchy. Game XYZ is already right-handed and
Y-up like glTF; standard output retains the lanes, scales positions by `0.01`
meters, and changes quaternion storage order from `[w,x,y,z]` to
`[x,y,z,w]`. External-parent ownership for other callers and loop-cycle
accumulation remain explicit blockers. See
`docs/research/nfl_axis_root_motion.md`.

The selected gameplay-referee path is now narrower than that general blocker.
All 46 records in the clip's 368-byte trajectory region are tabulated, and 17
complete XBE functions prove the path from the seven-entry referee pool through
controller interval sampling, heading rotation, actor scaling, live transform
state, and writes to `actor+0x18`. At title duration the sampler is at frame
position `44.5000041`, not the final serialized record. A glTF root track is
still withheld because the concrete one-of-seven actor's initial scale,
heading/controller/transform state remains unproved. A follow-on trace closes
the final hierarchy/queue/palette/draw edge; see
`docs/research/nfl_referee_root_trajectory.md` and
`docs/research/nfl_referee_render_root.md`.

The same gate compiles `src/recovered/nfl2k5/motion_event.c` and validates all
6,068 terminated event streams. Every one of the 9,024 events preserves its
24-bit tick and unnamed 8-bit ID across the complete 59-ID domain; portable
seconds differ from the executable-derived reference by at most `2.07e-07`.

See `docs/research/nfl_motion.md`, `docs/research/nfl_motion_sampler.md`, and
`docs/research/nfl_motion_channel_maps.md`. The follow-on allocation trace in
`docs/research/nfl_motion_object_pools.md` proves the ordinary 11+11 actor
pool, a seven-entry fixed-position pool, and a two-entry pool bound one per
team. Player, official-crew, and coach-like interpretations are recorded with
explicit confidence rather than promoted to stripped source symbols.

The logical-channel names are now exact. Executable sampling, parent-table,
and name-to-transform-index paths bind map `0x0051cd70` to the player
`lo_body`/`LO_res` order and map `0x0051d010` to the shared referee/coach body
order. All 50 channel names, hierarchy parents, mirror partners, and disabled
bilateral pairs validate against one player, two referee, and 72 coach
body/LOD transform-table copies; see `docs/research/nfl_bone_binding.md`.
The follow-on transform trace now proves all 110,318 bind translations and
parents, 73,803 two/three-source CPU palette blends, register-1 `SHORT1`
selectors, both full/remapped palette upload paths, and the active shader
rows. Every one of 13,731,388 vertex selectors resolves without conflict:
13,372,190 vertices have one transform influence, 328,001 have two, and
31,197 have three. Run `bash tools/validate_nfl_transform_semantics.sh` and
see `docs/research/nfl_transform_semantics.md`.

The follow-on rest trace proves scalar-first Hamilton quaternions, identity
rest joint rotations, `+0x50.xyz` local translations, `local * parent/root`
hierarchy expansion, and translation-only `T(-+0x40.xyz)` inverse binds. All
330,954 reconstructed bind components and all 110,318 rest palette
cancellations are exact; current matrices inherit the external root-parent
space selected by each caller rather than being universally model/world
space. See `docs/research/nfl_rest_orientation.md`.

That contract now drives three standard raw-coordinate glTF files under
`assets/intermediate/nfl2k5/raw_skin_samples/`. Five mapped player/referee/
coach meshes contain 125 named joint nodes and dense `JOINTS_0`/`WEIGHTS_0`
for 11,730 vertices across 157 primitives. Clean regeneration, every influence,
every inverse bind, and 125 rest cancellations validate; the player proof also
loads through Assimp/OpenGL as 111 primitives and evaluates its standard rest
skin. These proof files intentionally preserve raw centimeter coordinates and
contain no animations. A separate derivative set under
`assets/intermediate/nfl2k5/meter_skin_samples/` applies the proved retain-XYZ,
right-handed Y-up, `0.01` meter scale to all 12,790 positions, 125 joint
translations, and 125 inverse binds; every other binary byte is checked
unchanged. The player derivative also passes the Assimp/CPU-skin/OpenGL host
path. Those raw and meter base sets remain animation-free. The first bounded
title-derived derivative now attaches a recovered referee clip to the meter
referee skin as described below. Run
`bash tools/validate_nfl_meter_skin_gltf.sh` and see
`docs/research/nfl_raw_skin_gltf.md` plus
`docs/research/nfl_meter_skin_gltf.md`.

The sampled-pose-to-matrix ABI is now bounded as well. The full writers sample
25 scalar-first quaternions, synthesize disabled player/coach/referee twist or
wrist slots, convert logical slot `N` to pre-postprocess matrix `N`, add the
proved SCNE local translation, expand `local * parent/external_root`, and form
the skin palette as `T(-bind) * current`. Hidden switch arms identify generic,
player, coach, and referee descriptors and tie the five-way controller to the
`cutscene` SCNE. Four root-placement paths remain intentionally distinct.
Coach/referee local rotation has no player-only morphology stage, but player
writers do pass through additional title code. That boundary is now narrower:
`0x00092140` now has a complete structured portable implementation of all 127
ordered helper calls and intervening operations, preserving the exact 25-to-62
matrix map and both wrist-to-hand right multiplies. An independent graph oracle
compares eight poses with maximum error `0.000234525141`; direct execution of
the original XBE function in Unicorn compares both GCC and Clang builds with
maximum error `0.000234564883`. `0x00093800` has an exact four-call hierarchy
wrapper, and current-matrix stage `0x00093850` is separately implemented by
`vc_nfl_player_current_postprocess` with `3.81469727e-06` maximum observed
error across 116 cases. Both recovered stages are compiled into the host and
have strict CTests. Xbox SSE-rsqrt/x87 bit identity and exceptional conversion
flags remain explicit value-level boundaries, not hidden equivalence claims.
The adjacent player quaternion stage is portable too: the exact 23-channel map
expands to all 25 `LO_res` slots, reconstructs `lwrist`/`rwrist` full twists,
and removes those twists from `lhand`/`rhand`. Both compilers match an
independent oracle across 22 poses / 550 channels sampled from shipped
`ANM_CELEBRATE_USER_34` with zero lane error.
An address-level ownership join follows that same unique archive body through
celebration selector row 2, the literal `CELEBRATE` namespace, deferred
acquisition, the 22-player pool/controller, the gameplay frame, and both
`LO_res` and `HI_res` hierarchy paths. It proves `0x00092140` and two
complementary `0x00093850` calls run. The former HI-res attachment blocker is
closed: the exact `HI_res` body now exports 7,396 vertices, 86 submeshes, 62
joints, all 139 blends, and every influence as a meter-space glTF that passes
Assimp and native GPU smoke validation.

The selector producer is narrower but not universal. State word `0x34`
selects slot 2; a new or otherwise unmodified profile maps that slot to row 2,
`ANM_CELEBRATE_USER_34`. The real profile setter at `0x00369AFA` can change
that value through a 37-row UI (`Chest Pound` is display row 2). A successful
state-`0x34` dispatch is now proved to own the newest tag-2 scoring-result
record for that same actor. Record type is still live: types 1/5 yield playback
mode 1, type 2 yields 14, and types 3/4 yield 2. Because the concrete type or
classifier gate for state `0x34` is not proved, no player animation glTF is
falsely emitted. See `docs/research/nfl_player_clip_ownership.md`,
`docs/research/nfl_celebration_selector_producer.md`,
`docs/research/nfl_celebration_live_record_ownership.md`, and
`docs/research/nfl_hi_body_skin.md`.
Run:

```sh
bash tools/validate_nfl_pose_matrix_apply.sh
bash tools/validate_nfl_player_postprocess.sh
bash tools/validate_nfl_player_92140.sh
bash tools/validate_nfl_player_pose_native.sh
bash tools/validate_nfl_player_clip_ownership.sh
bash tools/validate_nfl_celebration_selector_producer.sh
bash tools/validate_nfl_celebration_live_record_ownership.sh
bash tools/validate_nfl_hi_body_skin.sh
```

See `docs/research/nfl_pose_matrix_apply.md`,
`docs/research/nfl_player_92140_native.md`, and
`docs/research/nfl_player_pose_native.md`. That bounded referee path now
drives the canonical shipped `ANM_REF_PENALTY_DELAY_OF_GAME_R` witness. Its 46
source frames at 15 Hz and 21 packed channels become 25 local rotations baked
at 120 Hz: 357 keys, 8,925 native samples, and 50 high/low-LOD target channels.
All 1,375 imported vertices deform between 0 and 1.5 seconds, with a maximum
`0.658806324 m` displacement; the host reports 12 meshes, 300 Assimp bone
records, 2,006 weights, and one animation. Strict regeneration validates the
glTF, binary, and manifest as three canonical outputs. See
`docs/research/nfl_referee_animated_gltf.md` and run
`bash tools/validate_nfl_referee_animated_gltf.sh`.

This first title clip is intentionally local-rotation-only. Its 368 trajectory
bytes are now exactly decoded and their controller/callback/actor-write path is
instruction-proved. The actor transform also reaches the exact low/high
hierarchy/palette/draw path, but translation is omitted because one concrete
actor's initial/live state is not captured. Its three events are also omitted;
both LODs render simultaneously with synthetic host materials.
Gameplay ownership is instruction-exact for the `Referee`
namespace/controller/skeletal family, but the particular one of seven actor
records and a cutscene type-4 descriptor instance are not proved. The 120 Hz
glTF representation normalizes XYZW keys
and uses standard `LINEAR` rotation slerp; 26,700 sampled between-key probes
observe at most `0.0507245908` degrees difference from the title sampler, not a
continuous bound or x87-bit-exact claim. No player clip is exported yet: the
shipped `ANM_CELEBRATE_USER_34` witness, both player postprocessors, and the
62-joint HI-res skin are now exact, but its live scoring-result type/gate,
mutable profile selection, and concrete actor/root state are not. The
player-postprocess evidence is documented in
`docs/research/nfl_player_postprocess.md` and
`docs/research/nfl_player_92140_native.md`.
The adjacent `+0x24` targets are corrected
from provisional handler tables to two exact
25-float channel profiles; their pointer is passed into a pose-comparison ABI
but ignored by that callee, so weight semantics remain unproved. Event
meanings, opaque header fields, non-player external-root ownership, and loop-
cycle displacement remain unresolved. The portable decoder lives at
`src/recovered/nfl2k5/packed_pose.c`, with the trajectory path beside it; only
the provenance-pinned referee local rotations are emitted, without guessing
the unresolved live actor/render-root/event behavior.

APF 2K8's dominant inner format is also bounded now. `tools/apf_inner.py`
strictly parses all 1,473 `0xFF3BEF94` IFFs, validates all 10,394 recovered
resource-name/type CRC pairs, and handles the H7A wrapper plus selected Xenos
tiled DXT1/DXT5/RGBA8 base images. The complete metadata inventory is kept
compact rather than inflating the whole title:

```sh
env APF_DECODED_PE=/tmp/apf2k8_default.pe \
  bash tools/validate_apf_inner_assets.sh
```

See `docs/research/apf_inner_assets.md`,
`reports/manifests/apf_inner.json`, and
`reports/manifests/apf_inner_candidates.tsv`. Three decoded samples with raw
parts/sidecars are under `reports/asset_samples/apf/`. Complete Xenos
format/mip/cube import remains explicit `PORTME` work.

APF `SCNE` geometry is now exhaustively bounded: all 1,303 scenes parse, with
13,006 mesh nodes, 16,217,141 source vertices, 24,519,417 indices, and 43,098
vertex declarations. The XEX-proved position formats and D3D triangle-strip
topology produce `glowball` and 2,506-vertex `hi_head` glTF proofs; the latter
was visibly rendered by the native host. The same conservative path now emits
1,208 Blender-readable static scene collections containing all 13,006 meshes,
16,217,141 positions, and 11,588,322 non-degenerate triangles under
`assets/intermediate/apf2k8/models/`; the 95 zero-mesh scenes are explicit
withheld manifest entries. Run `bash tools/validate_apf_scene.sh` and
`bash tools/validate_apf_static_gltf.sh`, then validate the separate serializer
contract with `bash tools/validate_apf_scne_static_format_spec.sh`; see
`docs/research/apf_scene.md`, `docs/research/apf_static_gltf.md`, and
[`apf2k8_scne_static_serializer.v1.json`](reports/specs/apf2k8_scne_static_serializer.v1.json).
The first narrowly pinned APF write-back witness is also closed for outer 14,
inner 8 `stadium`, node 17 `polySurface19930`: exactly four big-endian
`FLOAT32x3` position lanes can be replaced in a copied `1A` while the 24-byte
interleave, UVs, normals, declarations, matrix/hierarchy, BE16 strip
`[0,1,2,3]`, fixed outer allocation, sibling parts, footer, and unrelated pack
bytes remain fixed. The no-op copied `1A` is byte-identical, and an independent
verifier re-derives the authored decoded positions and preserved spans. Run
`bash tools/validate_apf_stadium_static_position_patch.sh`; see
`docs/research/apf_stadium_static_position_writeback.md` and
`reports/assets/apf_scne_same_count_position_roundtrip.json`. The same outer
container now has a hashes-only catalog of 77 additional bounded
`FLOAT32x3`/no-blend candidates. Its v2 catalog dispatcher is now implemented
for all 77 targets: canonical recipes select a `target_id`, while vertex count,
stream start/stride/offset, format, and every preservation span come from the
pinned hashes-only catalog. Node 3 `polySurface19821` is the second complete
write-back witness: 24 vertices, three draw records, a byte-identical copied-
`1A` no-op, and a public all-zero changed proof whose 284 changed decoded bytes
all remain inside the 288 authorized POSITION0 bytes. The changed rebuild has
1,513 bytes of allocation slack, and a writer-independent verifier re-parses
the catalog target, IFF/H7A bytes, and complete manifest. Run
`bash tools/validate_apf_stadium_static_target_catalog.sh`; see
`docs/research/apf_stadium_static_target_catalog.md` and
`mod_editor/data/apf2k8_stadium_static_position_target_catalog.v1.json`, then run
`bash tools/validate_apf_stadium_catalog_position_patch.sh`; see
`docs/research/apf_stadium_catalog_position_writeback.md` and
`reports/assets/apf_scne_catalog_position_roundtrip.json`.

The first APF same-footprint topology writer is also closed for the pinned
node17 target. It accepts only a duplicate-free permutation of the four
existing BE16 strip IDs, changes only the existing eight-byte index allocation,
preserves the complete 0x30-byte draw record and every vertex/container byte,
and independently re-derives two nondegenerate native triangles. Run
`bash tools/validate_apf_stadium_node17_topology.sh`; see
`docs/research/apf_scne_draw_topology_writeback.md` and
`reports/specs/apf2k8_scne_draw_topology.v1.json`. Catalog membership and
offline write-back do not claim runtime rigidity. Materials, transforms,
remaining attributes, topology beyond this fixed four-index permutation,
changed counts, general edited-glTF import, skinning, animation, Xenia
visibility, and hardware acceptance remain explicitly unproved.

A paired NFL-to-APF model audit now makes the cross-title boundary exact. One
stadium and one skinned player derivative from each title can be hash-checked
and compared in a safe Blender reference scene. The selected player coordinate
bases and standard glTF inverse-bind representation are authoring-compatible,
but NFL's 62-joint/one-to-three-influence skin does not directly map to APF's
proved 21-joint one-hot shadow skin or separate 92-joint hierarchy. Materials,
complete normals/UVs, LOD, collision, APF model serialization, archive
writeback, and runtime routing remain blocked; direct serialized copy and
installable APF import are explicitly false. Run
`bash tools/validate_cross_title_model_compatibility.sh` and see
`docs/research/cross_title_model_compatibility.md` for the 15-surface matrix,
124 authoring-only bone candidates, and Blender workflow.

APF facial animation is no longer an undifferentiated blob. Both
`CurveAnim`-only banks decode into 2,325 uniquely named bodies that tile all
2,657,064 decoded bytes. XEX load/inverse callbacks prove four field-local
relative pointers in each of 2,324 non-null bodies, yielding 9,296 ordered,
bounded regions; the one 32-byte `null` sentinel is handled separately. Run
`bash tools/validate_apf_curve_anim.sh` and see
`docs/research/apf_curve_anim.md`. Bit widths, time/value quantization,
interpolation, and SCNE morph-channel bindings remain explicit blockers, so
the project does not emit guessed glTF animation.

APF skeletal-motion storage is now bounded separately. All 68 `SingleMoCap`
resources preserve 1,301,080 bytes: 67 normal clips plus the XEX-verified
`hand_pose_mirror` alias. Executable samplers decode 6,782 counted root-vector
records and 34 timed events; all other packed regions and the 28 nonzero sample
tails remain exact. Both `BoneScaleMap` resources join all 144 bone hashes to
exact `SCNE` names, and seven clip names are exact NFL `SMCD` lineage anchors:

```sh
bash tools/validate_apf_mocap.sh
```

See `docs/research/apf_mocap.md`. Per-bone channel IDs/widths, quantization,
timing, interpolation, five driver hashes, skeletal glTF binding, and writing
remain `PORTME`; related root shapes and names do not prove codec compatibility.

The exact-name anchors now support a strict cross-title motion comparison.
All seven pairs preserve frame count, 15 Hz rate, time scale 1, constant 100,
six-byte trajectory layout, event sentinel, and trajectory component order;
their samples were nevertheless revised. APF's full 1,245,136-byte main pose
corpus tiles exactly into 155,642 eight-byte units—23 units per sample for 66
clips and 15 for `hand_pose`. Treating those bytes as NFL four-byte
signed-10-bit quaternions fails tens of thousands of radicand checks in both
byte orders, proving that raw pose streams are not interchangeable:

```sh
bash tools/validate_motion_lineage.sh
```

See `docs/research/motion_lineage.md`. Shared frame, trajectory, event, and
relative-pointer semantics can back a decoded intermediate layer, while each
title needs its own pose decoder and writer.

APF's main pose codec is now instruction-proved rather than merely bounded.
Every big-endian eight-byte mode-0 record contains a four-bit selector and
three signed 20-bit components scaled by exactly `23 / 2^24`; the fourth lane
is reconstructed from the unit-length constraint and the selector rotates the
four output lanes. The aggregate sampler proves the 23/15-unit frame widths,
three-byte normal/mirror maps, numbered mirror sign changes, frame selection,
and shortest-path polynomial quaternion interpolation. All 155,642 shipped
units have positive reconstruction radicands:

```sh
bash tools/validate_apf_packed_pose_decoder.sh
```

See `docs/research/apf_packed_pose_decoder.md`. Bit-exact Xenon
`vrsqrtefp` estimation, map mode 2, the optional stream,
family-wide skin-palette/inverse-bind behavior and a reversible writer remain
explicit addressed `PORTME` work; no generic guessed skeletal animation is
emitted. One exact selected witness is exported below. The
portable mode-0 decoder in `src/recovered/apf2k8/packed_pose.c` is compiled
into the Linux host and matches all 155,642 supplied units within
`7.27e-08` of the rational reference while explicitly declining Xenon
bit-exactness. Mode 1 is now decoded by
`src/recovered/apf2k8/translation_pose.c`: all 40,434 shipped records are
signed `4_20_20_20` triples scaled by exactly `1/1024`, with mirror changing
numbered lane 0. Stored points are exact; portable interpolation does not claim
Xenon VMX multiply-add bit identity.

The APF follow-on pose/bone trace proves the sampler-to-matrix ABI and now one
exact active frontend binding. Controller selector `(slot=1,index=2)` chooses
shipped `mnu_stn_01_070130_01_lg` for object classes 2/3, stores and reloads
that exact `SingleMoCap`, samples it with main map3 `0x820FC510`, expands 21
rows with main map2 `0x820FC55C`, and applies them to the exact
`SCNE/player_shadow` hierarchy. All 21 named rows and parents are therefore
active instruction-exact bindings, not candidates. The alternate class branch
selects `mnu_stn_01_070130_01`. The follow-on XEX trace now proves numbered
lanes `[1,2,3,0]` become glTF XYZW, the quaternion matrix is right-handed,
translation is direct XYZ in centimeters, and the selected clip's trajectory
drives a separate external-root parent using the title's scale/base/heading
formula. Across 114,563 shipped mode-0 records the ideal matrix equations,
determinants, and mirror conjugation validate; the selected clip contributes
1,989 records and 117 root samples.

The former `player_shadow` skin blocker is closed. Its exact static derivative
contains 351 meter-space vertices, unchanged 918-index topology, 21 joints and
inverse binds, and 351 one-hot influences. The selected
`mnu_stn_01_070130_01_lg` derivative bakes 927 keys at 120 Hz with 17 rotation,
six bone-translation, and one external-root channel. A 960 Hz probe grid
observes at most `9.80911239e-06` degrees rotation, `2.61196e-08 m` bone
translation, and `8.94118e-08 m` external-root error; these are finite-grid,
not continuous or Xenon-bit-exact bounds. The native host imports 21 bones and
18 animation channels; all 175 Assimp-deduplicated vertices move by two
seconds, and both static and animated OpenGL screenshot gates pass. Live menu
scale, heading, and base position remain explicit normalization boundaries.
Run:

```sh
bash tools/validate_apf_pose_bone_binding.sh
bash tools/validate_apf_pose_config_builder.sh
bash tools/validate_apf_animation_export_readiness.sh
bash tools/validate_apf_animation_transform_semantics.sh
bash tools/validate_apf_player_shadow_skin_semantics.sh
bash tools/validate_apf_player_shadow_gltf.sh
```

See `docs/research/apf_pose_bone_binding.md` and
`docs/research/apf_pose_config_builder.md`, then
`docs/research/apf_animation_export_readiness.md` and
`docs/research/apf_animation_transform_semantics.md`. The final exports and
host boundary are in `docs/research/apf_player_shadow_gltf_export.md`.

APF audio is likewise addressable rather than opaque. All 2,261 `AUDO`
records and 30,524 2-KiB packets validate as XMA1; reconstructed RIFF streams
let FFmpeg cleanly decode 1,261 of 1,268 unique payloads (2,229 of 2,261
occurrences). The seven rejected payloads remain explicit—no partial WAV is
accepted. All 20 `AUSB` descriptors map by an exact uppercase-filename CRC32
rule to 19 external banks containing 45,514 bounded substreams. Run
`bash tools/validate_apf_audio.sh` and see `docs/research/apf_audio.md`.

The shared data-driven menu layer is now bounded and partially semantic. All
161 APF and 86 NFL `LAYT` objects parse into 1,837 and 280 acyclic linked
records. Executable consumers prove additive translation X/Y/Z, type-2 child
layout recursion, runtime draw gates, APF 60 Hz type-3 timelines, and NFL's
type-1 callback ABI/four dispatch tables. Cross-title comparison yields 102
exact keys, 98 unique bridges, and 27 identical whole-layout sequences covering
120 records. It also identifies APF `layout_mainmenu` and NFL `main_menu` /
`main_navi` exactly. A focused state trace now proves that NFL descriptor
`0x00515660` actually loads sibling `main_menu_sub`, constructs the seven
Quick Game/Game Modes/Crib/Features/Options/Xbox Live/Extras rows, and reaches
their activation callbacks. APF descriptor `0x820F4350` instead loads
`quicknav`/`template_quicknav`, constructs seven typed rows, and has a proved
callback route back to main. The v5 boot trace follows XEX entry through
CRT/game main, the main loop, frontend bootstrap, and `TitlePage_Menu`, then a
static key-11 callback to `StartupMenu`. Startup's proved fallthrough reaches
Team Select, not Main; an additional Main wrapper is exact, but cold
boot-to-Main remains unproved. V6 now proves bootstrap explicitly requests
`frontend_sync.iff` through `0x8467CA70 -> 0x8468DA70`, closing the executable
archive-owner blocker. Team Select really dispatches Main descriptor
`0x820F4350` as an exit-policy argument, but the complete callback only tests
it for non-null and does not construct Main. Main's direct LAYT path exactly
selects `quicknav` from `global.iff` (1310/57), disproving
`layout_mainmenu` for that path. Inner 53 of `frontend_sync.iff` is still the
seven-child `layout_mainmenu`; all 161 decoded APF LAYTs contain no serialized
owner reference, so a separate runtime owner—or unused retail content—remains
the honest boundary. Run
`bash tools/validate_layout_inventory.sh` and
`bash tools/validate_layout_semantics.sh`, then
`bash tools/validate_menu_state_trace.sh` and
`bash tools/validate_menu_state_trace_closure.sh`, then
`bash tools/validate_menu_label_renderer_v3.sh`,
`bash tools/validate_quicknav_text_render_v4.sh`,
`bash tools/validate_apf_frontend_boot_backdrop_v5.sh`, and
`bash tools/validate_apf_frontend_main_ownership_v6.sh`; see
`docs/research/layout_format.md` and `docs/research/layout_semantics.md`.
The follow-on closure recovers 12 exact fragmented function boundaries and
resolves 8 of the original 23 blockers. It proves APF's type-3
`template_quicknav` apply/config path and seven queued plus one direct routes to
the main descriptor. Exact negative evidence finds no ASCII, UTF-16, or
fullword executable edge for `layout_mainmenu` CRC `0x48C6D154`; halfword hits
are zero-store collisions. Fifteen address-specific `PORTME`s remain, including
cold boot, APF `layout_mainmenu` runtime ownership, final label rendering, and the
`SlideOnNav_MainMenu` mapping. See `docs/research/menu_state_trace.md` and
`docs/research/menu_state_trace_closure_v2.md`. This is not presented as an
original-menu launch.

The APF label-content edge is exact. Main's `template_quicknav` contains
eight type-0 option IDs bound to provider `0x846F5198`; that provider reaches
orphan getter `0x846F3888` (`lwz r3,+8(r3); blr`) through the recovered PDATA
extent. Selected labels format as `{0}|M_PRIMARY|`, while ordinary labels use
a bounded UTF-16 copy. The v4 trace then proves every type-0 caller overwrites
the provider-buffer argument before use, so those characters have no proved
visual consumer. A separate real UTF-16 glyph/vertex/command path exists, but
its named APF font, atlas, and final draw ownership remain open. A suspected
cold-boot function
`0x84A58698` is instead conclusively End Of Game row 5 “Quit” preflight. The
v3/v4/v5/v6 reports retain address-specific PORTMEs and pass byte-identical
read-only Ghidra regeneration; see `docs/research/menu_label_renderer_v3.md`,
`docs/research/quicknav_text_render_v4.md`, and
`docs/research/apf_frontend_boot_backdrop_v5.md`, and
`docs/research/apf_frontend_main_ownership_v6.md`.

NFL's corresponding font edge is closed. The XBE loads ten named `FONT`
resources; the main row routine selects slot 6, exactly `font7`. All 943
serialized glyph records, field-local range pointers, advances, quads, UVs,
swizzled P8 indices, 16-entry alpha palettes, and ten atlas dimensions validate
with zero observed quad/UV pixel error. Ten transparent PNGs and retained
opaque palette tails are under `assets/intermediate/nfl2k5/fonts/`. A separate
row-layout trace recovers all three title-space modes, seven row origins,
wrapping, and `+8/-4` text offsets as portable C. The formatted-string trace
recovers all 57 case-insensitive inline tokens and 13 exact `TXTR` resources;
`The Crib|TM|` selects index 40, slot 9, resource `tm`, and a full-UV square.
Its loose PNG now renders and hot-reloads in the host. The downstream
projection and original default-state ownership remain explicit. Run
`bash tools/validate_nfl_main_menu_font.sh`,
`bash tools/validate_nfl_main_menu_row_layout.sh`, and
`bash tools/validate_nfl_bitmap_font_native.sh`, plus
`bash tools/validate_nfl_formatted_token.sh`; see
`docs/research/nfl_main_menu_font.md` and
`docs/research/nfl_main_menu_row_layout.md`, and
`docs/research/nfl_formatted_token.md`.

The exact seven-row models are now compiled into an architecture-neutral,
host-only module. Run `./build/vc_football_port --menu nfl2k5` or
`--menu apf2k8` to navigate them with the existing SDL keyboard/gamepad seam.
Every row preserves its source/label address, type, target, handler chain, and
callback provenance as `uint32_t`; activation only reports `HOST VIEW ONLY ...
NOT EXECUTED`. NFL row labels now use the recovered loose `font7` PNG/metrics
path, with a screenshot test proving 11,170 changed pixels inside the bounded
label region and zero outside it. A second GPU comparison replaces literal
`|TM|` with the proved loose icon and changes 638 pixels in row 2, zero
outside. APF and missing-font paths retain the 5x7 fallback. Unit and
screenshot tests enforce those boundaries. This is useful
integration progress, but it is deliberately not guest execution, an original
menu launch or the title projection/renderer. APF `quicknav` is now proved to
be Main's direct LAYT and specifically is not mislabeled as owning
`layout_mainmenu`.

The director/config layer has also been separated from speculation. All five
`DRCT` resources in each title reconstruct byte-for-byte as a relocated graph:
273 bounded fixed packages, 3,664 exactly partitioned opaque instruction
records, and 703 primary strings. NFL consumers prove its 193-slot table,
child lookup, instruction dispatch input, and string accessor; APF widens the
table to 217 slots and retains an opaque auxiliary tail. The two generations
share 114 exact strings, including all 101 tutorial texts and all 12 halftime
texts. Run `bash tools/validate_director_inventory.sh` and see
`docs/research/director_format.md`. Opcode semantics and a writer remain
`PORTME`, so `DRCT` is not mislabeled as source script or silently skipped.

The disc roster formats are now searchable without relying on a save-editor
schema. APF's one `ROST` resource yields 2,254 players, 40 teams, 31 stadiums,
and 1,344 counted memberships; NFL's 76 `ROST` resources yield 6,522 players
and 127 teams, plus their proved stadium, coach, college, and membership
references. Both validators enforce the field-local signed relative-pointer
rule seen in their executable relocators:

```sh
bash tools/validate_apf_roster.sh
bash tools/validate_nfl_roster.sh
```

See `docs/research/apf_roster.md` and `docs/research/nfl_roster.md`. The TSV
exports are deliberately read-only: packed ratings/appearance fields,
allocator capacity, archive recompression, and safe import are still explicit
`PORTME` work, so the host does not yet advertise roster swapping as complete.

One deliberately narrow NFL exception now also participates in the unified
public-safe XISO project.
The 52-row main team table's city, nickname, short-name, two-digit art code,
stadium, and 65-slot roster ownership are joined to all 85 uniform/Team Select
codes, the XBE's 80 fixed color records, and all 42 created-team field-art
codes. The create/edit-team UI directly consumes the same city/name/short-name
fields. Real dashboard containers are now inventoried separately, but the
team-identity payload fields and load precedence are not yet mapped. A
copy-only Detroit-to-`Codexia Codex` proof changes exactly 17 XISO bytes while
leaving code `09`, the complete team record/roster, `default.xbe`, and every
XDVDFS extent identical. It is an offline structural proof, not a runtime or
general roster-writer claim. See
`docs/research/nfl_team_identity_modding.md` and run
`bash tools/validate_nfl_team_identity_audit.sh`.

A second bounded NFL exception now proves practical fixed-size player edits in
the original-Xbox disc files. The main disc ROST has 2,547 `0x54` player
records; executable consumers prove first/last-name pointers, team membership,
face/head ID `+0x06`, jersey bits at `+0x20`, and the 17-code position byte at
`+0x35`. The recovered rating UI dispatch contributes 204 exact
position/slot bindings and conditionally names Speed, Consistency, and
Aggression only where their UI labels directly bind, without guessing every
clamped byte. A copied-XISO
`Joey Harrington #3` -> `Noah CodexProof #42` proof changes exactly 14 bytes
while preserving Detroit slot/count, face, position, every pointer/unrelated
field, `default.xbe`, and all XDVDFS extents. This is a disc-seed proof; a
loaded roster save can override it and runtime visibility remains untested.
See `docs/research/nfl_player_roster_modding.md` and run
`bash tools/validate_nfl_player_roster_audit.sh`.

Numeric roster portraits now participate in that same unified project without
being confused with live `f/h/n` face textures or Crib action photos. The
4,303 exact four-digit P8 targets accept strict 128x128 RGBA PNGs; deterministic
quantization preserves each fixed wrapper/system allocation. Portrait `4070`
is the retained cross-pack proof, split into 8,448 bytes in pack 3 and 9,120
bytes in pack 4 and independently reconstructed as one logical resource. See
`docs/research/nfl_player_portrait_pipeline.md`.

Uniform “sharing” is now split by actual ownership instead of appearance.
For the Xbox NFL build, all 3,170 audited torso, pants, sleeve, and live-helmet
targets occupy distinct, non-overlapping XISO spans even when their decoded
content hashes match. Direct selector-specific import therefore avoids a
hash-replacement alias without archive growth, subject to each fixed allocation.
APF is genuinely shared: 40 team slots select 24-asset jersey, pants, helmet,
and shoulder catalogs. The public editor exposes read-only owner lookups and
no arbitrary selector writer. A hidden offline CLI now writes and independently
verifies the one exact deterministic all-family built-in allocation plan; its
runtime consumption is unproved. See
`docs/research/uniform_texture_sharing.md` and run
`bash tools/validate_uniform_texture_sharing.sh`.

APF pants are now writable at the physical-asset layer too. All 24
`pants_color` packages share one exact 512×512 tiled DXT1/eight-mip class, and
the copy-only CLI preserves each package's H7A profile, fixed allocation,
footer, DRAM descriptor, packed-tail padding, and three normal maps. The retail
ROST uses only 11 pants assets and every used asset is shared; asset 13 has 34
team/bank owners. The named GUI/CLI lookup lists those owners, while the writer
deliberately does not redirect selectors. A full copied-`0A` independent
verification passes, but runtime visibility and production DXT1 quality remain
unproved. The public editor exposes the fixed-argv
`apf2k8-pants-color-v1` provider with canonical recipe creation and a separate
copied-volume verifier. See `docs/research/apf_pants_family_patch.md` and run
`bash tools/validate_apf_pants_typed_provider.sh`.

APF helmets now have a parallel all-24 copy-only lane. `helmet_color` is a
256×1024 tiled DXN/BC5 texture with seven levels; the writer preserves
`helmet_normal`, both DRAM descriptors, the footer, packed-tail padding, and
all bytes outside the selected allocation. Its PNG contract is deliberately
data-oriented: R/G are the two stored channels, B must be 0, and A must be 255,
because shader color semantics are not yet named. Only six assets are selected
by the retail ROST and all are shared; asset 16 has 34 owners. See
`docs/research/apf_helmet_family_patch.md`, inspect owners with
`python3 -m mod_editor --inspect-apf-helmet-sharing 16`, and validate with
`bash tools/validate_apf_helmet_typed_provider.sh`. The public provider uses a
canonical recipe, fixed argv, an independently executed verifier, and an
exclusive hash/metrics-only artifact directory; runtime visibility remains
unproved.

APF shoulders now have a separate all-24 copy-only lane. `shoulder_color` is
1024×1024 tiled BC3 with nine levels and a packed mip tail; the writer preserves
the complete DRAM block, region map, two sideline textures, inactive mip bytes,
footer, paired shoulder-normal package, and all bytes outside the selected
allocation. Selector slot 11 is genuinely shared across 80 team/bank uses;
asset 8 has 36 owners. Inspect them with
`python3 -m mod_editor --inspect-apf-shoulder-sharing 8` and validate with
`bash tools/validate_apf_shoulder_typed_provider.sh`. The public
`apf2k8-shoulder-color-v1` provider creates a canonical recipe, invokes the
writer with fixed argv and no shell, and runs the independent verifier into an
exclusive hash/metrics-only artifact directory. Offline transport is proved;
runtime visibility plus production BC3 quality remain unproved.

The canonical machine-readable contract for all four closed APF uniform
texture families is
[`apf2k8_uniform_texture_formats.v2.json`](reports/specs/apf2k8_uniform_texture_formats.v2.json).
It freezes 96 slots and 33 mip layouts while retaining immutable v1; the drift
validator rejects changed source pins, descriptors, allocations, and preserved
sibling spans.

The reported NFL draft/trade, salary/contract, and future Super Bowl venue
limits now have a separate feasibility matrix. The Xbox XBE proves the exact
17-position fantasy-draft owner, a season-advance salary-cap validator path,
and the mode-9/week-`0x14` Super Bowl classifier. It does not yet prove CPU
trade scoring, contract/save encoding, cap growth/penalty math, or the
intended future venue policy. The venue owner itself is exact: indices 0–4
select `s40`, `s42`, `s43`, `s41`, and `s44`, while every index at or above 5
falls through to `s45`. No executable or save writer is exposed. PCSX2 needs
the exact PS2 ELF and controlled same-revision saves; Xbox addresses are not
PS2 offsets. The local PCSX2 audit pins the NTSC-U target as `SLUS-20919`
version 1.01 / `SLUS_209.19`, but finds no matching ISO, ELF, save marker, or
texture dump; two 2K5-named 6.3 GB images are positively identified as Xbox
XDVDFS instead. See `docs/research/nfl2k5_ps2_fixture_protocol.md`,
`docs/research/nfl_franchise_limit_feasibility.md`, and run
`bash tools/validate_nfl2k5_ps2_fixture_audit.sh` plus
`bash tools/validate_nfl_franchise_limit_feasibility.sh`.

The original-Xbox save boundary is no longer hypothetical. A strict read-only
FATX audit inventories eight user-owned NFL 2K5 containers under title ID
`53450030`: one profile, `Settings1`, `Franchise1`, and five team-management
saves. The exact 21 stock sliders occur in both the 736-byte `Settings1`
payload and the first 736 bytes of `Franchise1`; the public GUI/CLI can display
the observed values without exposing raw save offsets. The XBE owner streams
`SAVEGAME.DAT` through signature mode 0 and reads or writes a 20-byte `EXTRA`.
That proves the integrity boundary, not an offline signer: no platform keys are
read or published, no save writer is enabled, and a copied-HDD changed-save
reload is still required. See `docs/research/nfl2k5_xbox_save_inventory.md`
and run `bash tools/validate_nfl2k5_xbox_save_inventory.sh`.

The shared `STRG` localization layer is also exact now. Both primary banks
contain the same 1,492 ordered texts and 1,106-entry deduplicated string pool;
the generated TSV maps every record between the games' otherwise disjoint
numeric ID domains. All four source bodies rebuild byte-for-byte:

```sh
bash tools/validate_string_table_inventory.sh
```

See `docs/research/string_tables.md`. The two key-generation algorithms,
collision ownership, and size-changing archive import remain `PORTME`;
existing IDs can be translated, but new IDs must not be invented from this
evidence.

APF's separate `TXT loc system` has since been parsed on its own terms: 1,572
sorted IDs across the English UI and credits banks, with 1,294 exact UTF-16BE
pool entries and byte-identical body rebuilds. Run
`bash tools/validate_apf_txt_loc.sh` and see
`docs/research/apf_txt_localization.md`. The one non-pointer control row, source
ID generation, fallback consumer, and safe archive import remain explicit.

All on-disc playbooks are structurally searchable as well. The one APF master
book and all 37 NFL books account for 9,837 play records, 1,696 formations,
863 categories, 96,781 aligned assignment/route nodes, and every one of the
108,207 eleven-player slot references. Cross-title names provide 428 shared
plays and 114 shared formations:

```sh
bash tools/validate_playbook_inventory.sh
bash tools/validate_playbook_lineage.sh
```

The descriptor lineage is stronger than a name match: all 6,446 APF and
101,761 NFL eleven-player assignment descriptors obey one reversible packing
transform. It maps 78 of APF's 88 unique values into NFL's observed domain;
161 APF play occurrences (155 names) match an NFL record in all eleven
converted slots, and 101 also match all eleven first referenced nodes after
platform-endian normalization. See `docs/research/playbook_format.md` and
`docs/research/playbook_lineage.md`. Descriptor meanings, complete node-chain
opcodes, formation lineup fields, opaque auxiliary tables, capacity consumers,
and a safe writer remain `PORTME`; raw unknown fields are preserved rather
than presented as a speculative play editor.

APF's only `FSMR` object, `crowdren1`, is now bounded too. Its `0x700`-byte
body contains two field-local relative root pointers, 30 fixed `0x20` table-A
records, 47 populated `0x10` table-B records, and a 72-byte zero tail. The XEX
consumer proves bounded weighted choices and packed transitions, so this is a
finite crowd-renderer configuration—not a general script VM. Run
`bash tools/validate_apf_fsmr.sh` and see `docs/research/apf_fsmr.md`; field
semantics and serialization remain explicit `PORTME` work.

Phase-by-phase worked/failed/blocking summaries are in
`docs/phases/phase0.md` through `docs/phases/phase4.md`. Phase 4 is intentionally
still open: its document distinguishes the verified Linux research shell and
loose-asset swap from an original recovered menu.

## Tests

```sh
ctest --test-dir build --output-on-failure
```

The OpenGL-enabled configuration contains 45 tests. Twenty are GPU-labeled;
`ctest -L gpu` selects 21 cases because those checks also require the
swapped-logo fixture setup. Coverage includes the title-derived referee's
structural, deformation, and 91-frame GPU checks, APF `player_shadow` static
and animated imports plus screenshot comparison, and NFL font7/TM rendering.
Non-GPU CTests compile the recovered APF pose decoders, NFL player
postprocessors, exact row-layout helper, and strict bitmap-font parser into the
native toolchain. The player local-pose sampler is independently checked
against all 93 frames of shipped `ANM_CELEBRATE_USER_34`; see
`docs/research/nfl_player_pose_native.md`.

The current non-GL configuration also passes all 25 selected tests under
Clang 18 AddressSanitizer plus UndefinedBehaviorSanitizer (including leak
detection):

```sh
cmake -S . -B build-sanitize -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_COMPILER=clang-18 -DVC_PORT_STRICT=ON \
  -DVC_PORT_ENABLE_GL_TESTS=OFF \
  -DCMAKE_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined'
cmake --build build-sanitize --parallel
ASAN_OPTIONS='detect_leaks=1:halt_on_error=1' \
UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' \
  ctest --test-dir build-sanitize --output-on-failure
```

The `gpu` tests render default and swapped-logo screenshots and therefore need
access to a working display. On a headless machine, run the non-GL checks with
`ctest --test-dir build -LE gpu`, or configure with
`-DVC_PORT_ENABLE_GL_TESTS=OFF`. Generated test images are written inside the
build directory.

## Install

```sh
cmake --install build --prefix "$HOME/.local"
```

The install step places the executable in `bin` and the redistributable mod
assets under `share/vc_football_linux_port`. Extracted proprietary assets are
not installed. The install audit enumerates exactly eight files and confirms
that font7, APF `player_shadow`, and the entire `assets/intermediate` tree are
absent; only the user-owned font and TM override schemas are packaged.

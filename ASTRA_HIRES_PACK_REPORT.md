# r62 Hi-res pack pilot

**EXPERIMENTAL / UNWITNESSED.** Delivered an opt-in, resource-only compiler
and transactional disc builder for the scorebug frame, one created-team
field logo and one live helmet. PNG and Studio master input, 2x output,
native-size fallback, exact replay, receipts and fresh image inspection work
from the command line. Nothing enables this feature in a preset. Protected
Build/UI/release integration is specified in `WIRING.md` for Claude.

Work started at `5f5b5047d42984ee41449c4a03669e0945a22f2a` on
`astra/r62-hires-pack`. The project indices, existing Astra reports, RC85
changelog and hub `HIRES_TEXTURES_RESEARCH_2026-09-05.md` were reviewed.
The beta-61 archive grow/shrink transport supersedes the memo's older
fixed-span limitation. No emulator, GUI, audio, network or push was used.

## Delivered behavior and decisions

`mod_editor/core/nfl2k5_hires_texture.py` owns three pinned ordinary P8 TXTRs.
It validates every selected wrapper/system object before encoding, retains
the native mip count, box-filters RGBA with the existing round-half-up rule,
builds a shared palette, swizzles every mip and uses the existing VC-LZ
encoder. It changes only the palette-offset and packed-format words within
each 128-byte system object. It recalculates wrapper/video/stored/scratch
sizes, checks in-place decompression overlap through the existing token
walk, and independently decodes and hashes every output mip.

`mod_editor/core/nfl2k5_hires_pack.py` supplies `status`, pure resource
`apply`, `inspect_image`, `build_image` and a JSON CLI. A `Hi-res` folder
selects one to three exact basenames. PNGs must already be 2x. Validated
`.2ktexmaster` previews include native painting overlays; a 4x preview is
reduced to 2x once. Limits are 32 MiB per input, 64 MiB expanded master ZIP,
16 megapixels per master source, 2 MiB per TXTR and 32 MiB per pilot outer.
The filename explicitly assigns the target; the receipt retains master
identity, source hashes and transform. There is no new image dependency.

The existing `nfl2k5_music_archive` layout/container rewrite and
`nfl2k5_music_banks._write_archive` perform the rebuild. The music publication
boundary was extracted into `archive.transactional_copy`, and music now
uses that same helper. There is no second pack writer. Publication requires
fresh read-back of all 4,323 outer hashes, new XDVDFS pack nodes, selected
TXTRs/mips and the three unrelated named files, including `default.xbe`.
Source/artwork/destination hashes or identities are rechecked; every handle
closes before atomic replacement. Exceptions and cancellation discard the
private copy. Large files stream in 1 MiB blocks. Two existing music
provider integrity pins were refreshed, without widening the pin set.

Ownership is recipe-relative: exact retail spans or exact output from the
same retained artwork at the current scale. Mixed retail/authored or mixed
scales refuse for the selected set. Foreign art, changed reserved bytes,
wrong dimensions, unsafe scratch and unknown consumers refuse before the
source copy is modified. Reapplying the same art/scale is byte-identical.
Native fallback starts from the retained authoring raster, restores native
dimensions/counts and can be enlarged again. It does not restore retail art
or guarantee the original compressed size. Change art/selection from the
original disc; build with the option off to retain retail bytes.

Build is the correct UI location: this operation changes archive sizes and
publishes a new disc. All Textures and the existing native fixed-span
writers retain their contracts. The guide is
`docs/mod_editor/nfl2k5_hires_pack.md`; the precise getting-started insertion,
BuildPlan fields, all-preset false defaults, conflict checks, final-pass
ordering, release allowance, runtime imports and capability row are in
`WIRING.md`. No XBE owner or allocation is introduced, so `_apply_all` and
the four executable status dictionaries have explicit N/A explanations.

## PROVED: scoped consumer and format evidence

These are **static proofs for the audited paths**, not proof that every
possible runtime consumer has been enumerated. Evidence is reproducible with
`tools/nfl2k5_hires_consumer_audit.py` and retained in
`reports/hires_pack_consumers.v1.json`, containing hashes and decoded metadata
only. All 477 field scenes were scanned; 438 have a `center_logo` draw and
39 do not. Together with the scorebug and two helmet LOD scenes, the receipt
contains 441 scenes and 451 selected draws. A second complete scan reproduced
the scene metadata. Thirteen final code/table ranges are hash-pinned and
validated on every image operation; unrelated XBE owners can compose outside
those ranges. A changed pinned byte refuses.

The inherited Models shader audit identifies normalized short2 input in
register 6 and UV reconstruction from shape `+0x30`: multiply by `.xy`,
then add `.zw`. The common constant-upload sequence at `0x000245B9` is
pinned here. The 18 MAD and two copy-through vertex programs documented by
Models provide the existing shader interpretation; this work rechecks the
actual selected shapes, vertex lanes and topology. UV scale/offset has no
texture-size term. Tiny excursions beyond 0..1 in existing UVs are retained.

| Pilot and actual identity | Audited consumer | Draw and mip evidence |
| --- | --- | --- |
| `scorebug`: outer 346/chunk 53, `score_buga`, outer ID `00B6926C` | Binder `0x000FC1A0`, table `0x00A95C60`: nine frame materials bind the texture handle at material `+0x30`. No width/height lookup or pixel source rectangle is used by this binder. | Scene o346c78, shape record 1856; normalized UV lane `[1,4,10]`, vertices 0..261 across nine draws. 64x64 becomes 128x128, still one mip. Screen placement and atlas proportions are preserved. |
| `field_logo`: outer 384/chunk 0, `CT33D.IFF` / `center_logo`, ID `D4DE004F` | Selected binder block `0x0009C5DE` and table `0x004F0090` select the logo texture and assign its handle; no pixel rectangle is copied in that block. This is created-team logo code 33 in dry weather, not stock NFL midfield artwork. | Every one of the 438 `center_logo` scenes has a normalized UV lane. Representative o3179c0, shape record 3168, material 7, vertices 40..43, lane `[1,4,10]`, approximately 0..1. 256x256 becomes 512x512; six levels end at 16x16 rather than native 8x8. |
| `helmet`: outer 3613/chunk 11, uniform `00H0.IFF` / `helmet00`, ID `341ECD96` | `0x0008E9E0` and `0x0008E3F0`, plus name/selection tables `0x004EEAF8` and `0x004EF390`, bind Standard/A shell and accessories by handle, without texture-size-derived mesh coordinates. | o3c113 `lo_body`: accessories 93 vertices and shell 108. o3c115 `hi_head`: accessories 304 and shell 391. Both use normalized lane `[1,0,6]` with recorded shape scale/offset. Six levels at 512..16; `helmet02` and C materials are unselected. |

The common paths `0x000323D0` and `0x00031FA0` select texture stages and
emit NV2A offset/format/palette methods from the descriptor, including its
new dimension exponents. Relocator `0x00034DF0` and loader `0x00044E60`
use descriptor/wrapper sizes. Their pinned bytes support this resource-only
approach. The draw path's `0x03FFFFFF` GPU-address mask is also why extra
guest RAM cannot be assumed usable by these textures.

No pixel-coordinate dependency was found in the audited per-asset binders
and selected draw geometry. **An exhaustive negative proof across every
runtime path is still open.** Runtime-generated surfaces at `0x00036440` /
`0x000364A0`, reflective paths, caches, rare LODs and transitions were not
proved irrelevant by this bounded static audit. The report and API do not
turn that absence of evidence into a compatibility claim. No atlas position,
mesh, sampler or screen-placement patch is justified or installed.

## PROVED: modeled allocation and real offline builds

| Asset | Native video bytes | 2x video bytes | Native stored body | 2x stored body | Mips at 2x |
| --- | ---: | ---: | ---: | ---: | --- |
| Scorebug | 5,120 | 17,408 | 2,400 | 7,120 | 128 |
| Field logo | 88,384 | 350,464 | 22,608 | 183,088 | 512, 256, 128, 64, 32, 16 |
| Helmet | 88,384 | 350,464 | 36,384 | 182,944 | 512, 256, 128, 64, 32, 16 |
| Total | 181,888 | 718,336 | 61,392 | 373,152 | 13 levels |

Each texture retains one 1,024-byte palette. Video growth is 536,448 bytes.
The 2x outputs each require 128 system bytes and 16 scratch bytes, for a
selected total load allocation of 718,768 bytes. These authored native
outputs total 182,320 load bytes. Retail field/helmet scratch was 128 bytes;
the smaller new scratch comes from the checked new token streams, not a
fixed assumption.

The 2x video sum is 1.0704% of a nominal 64 MiB and 0.5352% of a nominal
128 MiB. Those are arithmetic comparisons only: other resources, duplicate
live allocations, allocator headers/alignment, fragmentation, simultaneous
old/new loads, host-expanded P8 textures and render surfaces are excluded.
The compiler does not certify a safe scene budget. `xemu-64` is the only
selectable experimental target; `xemu-128` hard-refuses until guest heaps,
BIOS/kernel exposure and GPU high-address handling are proved. No executable
memory patch is included. Native size remains the normal default.

The user-owned source image was 6,300,499,968 bytes, SHA-256
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
Its 11,948,032-byte XBE hash is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Fresh four-tone noise PNGs exercised high-frequency sampling/compression;
the scorebug also has alpha. These are diagnostic artwork, not a polished
art pack or upscaled retail art. The 8/108/107 shared colors, including all
mips, encoded with zero channel error. General authored images can lose
colors during P8 quantization; every receipt reports that loss.

| Build | API seconds | Wall seconds | Peak RSS KiB | Logical growth | Physical growth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Final-code 2x from retail | 39.921 | 40.10 | 98,152 | +311,296 | +452,044,800 |
| Identical 2x replay | 46.924 | 47.08 | 98,808 | 0 | 0 |
| Native-size rebuild from 2x | 48.740 | 48.92 | 98,876 | -229,376 | 0 |

All outputs were 6,752,544,768 bytes. The inherited writer retains pack 0..E
lengths and appends/repoints the entire enlarged F extent, which explains
physical growth exceeding logical growth. Shrinking retains unused physical
space. Native authored compressed bodies are 3,264 / 69,696 / 69,520 bytes,
so native fallback has different compression from retail.

The 2x and replay full-image hash is
`3691c15d341ccb12918953298cbab7914d39f3688dc0226b09992e63b79be52f`.
The native hash is
`0ce679710835a7ccd3c1769cb8bccd4d26b8d485110db6c15e35be7d0a195df8`.
The final 2x run repeated the initial build after consumer guard hardening
and produced the same full hash. Native output was re-inspected with all
13 final consumer pins. Replay/native timings are from the earlier runs in
this same session; the added guards do not change encoded bytes.

**All three generated disc copies were deleted after verification.** The
original disc was unchanged. `reports/hires_pack_build.v1.json` retains
descriptors, allocation/compression details, every selected mip hash, old/new
locations and XDVDFS node values, output fingerprints and aggregate verified
outer-hash evidence. No disc, authored PNG or retail resource span is staged
for commit.

## Validation run

All new suites run with plain `python3 file.py`; optional retail evidence
has a precise skip when absent. This machine had the retail evidence.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_hires_pack.py` | 15 passed, 1.771 s |
| `python3 tests/mod_editor/test_nfl2k5_hires_pack_retail.py` | 4 passed, 16.873 s; peak RSS 102,332 KiB |
| `python3 tests/mod_editor/test_nfl2k5_music_banks.py` | 15 passed, 11.950 s |
| `python3 tests/mod_editor/test_modpack.py` | 36 passed, 8.320 s |
| `PYTHONPATH=. python3 tests/mod_editor/test_texture_master.py` | 11 passed, 0.024 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 24 passed, 54.391 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 28 passed, 111.230 s |
| `python3 tools/nfl2k5_hires_consumer_audit.py <retail.iso>` | Complete 477-field scan, retained scene metadata reproduced |
| `python3 -I` imports from an isolated allowlist stage plus the three proposed release additions | Passed; three assets, allocation total and status smoke checked |
| Capability object against `registry.schema.json` `$defs/capability` | Passed |
| `python3 packaging/repin.py --apply` | Exactly two existing music pins updated |
| `python3 -m compileall -q` on changed core modules; `git diff --check` | Passed |

The new synthetic tests use a bounded XDVDFS fixture below 200 KiB and the
actual archive writer. They cover growth/shrink, replay/re-upgrade, selected
and unselected hashes, mips/alpha, all mixed sets, foreign art/header bytes,
master input bounds before decoding, disk budget, source/artwork/destination
races and aliases, cancellation, partial writes, write/verify/publish failure,
Windows positional-I/O fallback and handle locks, and a failed constructor
with its traceback retained. They do not substitute a mocked archive writer.
Only synthetic asset pins and its dummy XBE consumer guard are replaced;
the retail suite checks the real three assets and all final consumer pins.

The existing texture-master suite lacks repository path setup and initially
failed its plain standalone invocation with `ModuleNotFoundError`; it passes
with the explicit `PYTHONPATH=.` shown above. This pre-existing test was not
changed. The isolated stage lacks 16 unrelated private inventory JSONs that
are also absent from this checkout; imports for this feature succeed without
them. This is a dependency smoke check, not a complete release certification.
No new executable owner exists to add to either XBE gate; their unchanged
full owner sets pass both composition orders. No cave manifest regeneration
or new code/state reservation is required.

## HYPOTHESIS and Noah's required xemu witness

The larger assets should cover the same visual regions while supplying more
detail at higher rendering scales. Neither this visual result nor retail
loader acceptance of this pack has been played. Keep the feature labeled
experimental/unwitnessed and off in every preset until Noah records these
checks. Boot alone is insufficient.

1. Record source/output/XBE and artwork hashes, compiler receipt, xemu
   version, backend, BIOS and 64 MiB configuration. Build a native control
   from the same retained art. Start each comparison from a fresh boot;
   compare native and 2x at rendering scales 1x, 2x and especially **4x**.
   Test assets separately first, then together. Keep all other edits equal.
2. Scorebug: both possession directions, clock/score changes, timeout and
   penalty states, period transitions, play call and replay returns. Check
   border thickness, atlas seams, alpha, clipping, positions and text
   alignment. Do not combine this frame with the reference/runtime scorebug
   replacement during the first witness. Screen positions must remain equal.
3. Field: select a created team actually using logo code 33 in dry weather.
   A stock NFL midfield view does not witness this target. Check broadcast
   and close replay, both ends/directions, distant views, motion and lighting.
   Look for seams, orientation, mip transitions and shimmer. Use the
   unmodified wet variant as a control; end zones and goal pads are also
   unselected controls, not coverage claims.
4. Helmet: use uniform `00H0.IFF`, Standard/A. Confirm both low body and high
   head LODs, accessories, pre-snap and close replay, a full drive and tackles.
   Check front/back seams, decal orientation, alpha and reflection/specular
   response, distant mip behavior and opponent sharing. `helmet02`/C and
   other kits should remain native controls. Do not count an unrelated
   team-select image as proof of the live texture.
5. Complete a game with halftime/replays, return to menus, load another
   stadium/opponent and repeat. Compare load times, frame times and stalls.
   Record allocation failures, peak usage, largest free blocks, overlapping
   transition allocations and texture uploads/cache misses where measurable.
   Repeat on supported OpenGL and Vulkan configurations. Lower rendering
   resolution does not reclaim guest texture allocations.
6. Verify identical recipe replay, the native-size fallback and an original
   disc build with the option off. Preserve the source artwork. Reserve any
   128 MiB witness for a later implementation that explicitly proves the
   allocator and high-address GPU path; it is unavailable in this pilot.

Known gaps are exhaustive runtime consumer coverage, scene heap headroom,
retail loader/visual/long-game witness, complete protected Build integration,
and 128 MiB support. Shared TSETs, fonts, portraits, linear strips, embedded
textures, other teams and 4x texture output are outside this three-asset
capability. The static proof and offline builds do not remove these limits.

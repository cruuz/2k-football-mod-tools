# NFL 2K5 Stadium P8 Texture Writer

Date: 2026-07-18

## Product result

Stadium Studio now has a source-derived writer for every embedded Stadium P8
texture occurrence that satisfies the fixed-allocation safety contract below.
The private source corpus admits exactly:

- 23,838 editable texture occurrences;
- 477 Stadium SCNE scenes;
- 3,217 distinct stock PNG previews;
- 21,136 occurrences stored in archive pack `9` and 2,702 in pack `8`.

An occurrence is intentional here. Two materials or scenes may display the
same PNG while owning separate index/palette allocations. Each canonical asset
ID, such as
`nfl2k5.stadium.o3280.c0005.scene2648.texture0002`, addresses one allocation in
one scene. The app routes Export, Replace, Revert, undo, project save/load, and
Build by that full ID. It does not treat matching preview hashes as ownership.

The original `cement01` writer remains compatible, but it is no longer the
product boundary. All 23,838 admitted occurrences report Editable. Other
Stadium assets remain browsable/exportable and fail closed as Preview/Export-
only.

## Exact admission contract

The writer does not trust a selector merely because it has the right spelling.
On each compile it replays the user's private index and resource inventory,
resolves the canonical outer/chunk/scene/texture tuple, reads the owning SCNE
from the extracted archive pack, decompresses it, and parses the scene again.
An occurrence is writable only when every condition below is true:

1. The selector has the canonical four-digit form
   `nfl2k5.stadium.oNNNN.cNNNN.sceneNNNN.textureNNNN` and resolves to the exact
   indexed SCNE ordinal, outer ID, chunk, and texture descriptor.
2. The SCNE is fully contained in one recognized source archive pack (`8` or
   `9`); a cross-pack or out-of-bounds resource is rejected.
3. The descriptor is two-dimensional Xbox `P8`, depth 1, `packed_size == 0`,
   flags `0x80000000`, and has a supported base-level decode.
4. Width, height, packed format, descriptor offset, pixel offset, palette
   offset, mip count, stock RGBA hash, stock PNG hash, and material ownership
   match the private catalog occurrence selected in the UI.
5. The pixel allocation is exactly the complete P8 mip chain and ends at the
   palette allocation. The palette is exactly 1,024 BGRA bytes (256 entries).
6. Pixel and palette allocations do not alias or overlap any other embedded
   texture allocation in the same scene.
7. Every mapped material pointer resolves back to this descriptor. The UI
   reports all linked material names because every surface using one linked
   material changes together.

The admitted dimensions and mip layouts are:

| Base dimensions | Mips | Occurrences |
|---|---:|---:|
| 8x8 | 1 | 12 |
| 16x16 | 2 | 18 |
| 32x32 | 3 | 1,065 |
| 64x32 | 3 | 108 |
| 64x64 | 4 | 11,294 |
| 128x64 | 4 | 442 |
| 128x128 | 5 | 8,800 |
| 256x128 | 5 | 689 |
| 256x256 | 6 | 1,410 |

Rectangular mip chains halve width and height independently. For example,
128x64 becomes 128x64, 64x32, 32x16, and 16x8. No mip may be omitted, resized,
or supplied separately.

## PNG authoring and compilation

Replace accepts a regular, non-symlink PNG whose decoded image is RGBA8 and
whose dimensions exactly match the selected occurrence. The error names the
required dimensions when the file is wrong. The compiler then:

1. generates the complete mip chain with deterministic box filtering;
2. quantizes all mips together to one palette of at most 256 RGBA colors;
3. regenerates every level's P8 indices and Xbox swizzle;
4. writes only the selected index-chain and palette allocations in decoded
   SCNE memory;
5. losslessly recompresses the whole SCNE into its original fixed stored span;
6. preserves the wrapper allocation and any final opaque bytes exactly; and
7. returns one fixed-span replacement plus derived quantized previews to the
   unified build provider.

Several selected textures in one SCNE are decoded and composed together before
one recompression. The project backend therefore emits one non-overlapping
replacement span per edited scene, not one overlapping span per texture.
Textures in different scenes produce separate non-overlapping spans.

P8 is a limited-color format. Highly detailed photographs, noise, and dithering
can increase both palette error and compressed size. The build report records
palette count, quantization error, preview hashes, mip hashes, changed decoded
bytes, encoded size, padding, scratch, and target metadata for each texture.

## Fixed-compression boundary

An edited SCNE must still fit the retail scene's exact stored allocation and the
bounded in-place decompression scratch contract. The source XISO is never
expanded or relaid out. A replacement that does not fit returns this actionable
error before edit state or output is published:

> This image cannot fit the stadium's fixed SCNE allocation after lossless
> resource compression. Simplify large noisy or detail-heavy areas; the source
> XISO and current edit are unchanged.

This limit applies to the combined result. Two PNGs that fit separately are not
guaranteed to fit together in one SCNE. Same-scene composition experiments on
scene 2648 confirmed both sides of that boundary:

- a high-contrast 64x64 authored PNG compiled for non-cement texture 4
  (`ibeam01`) to a 906,695-byte stream, leaving 2,169 zero bytes and using
  2,192 bytes of aligned scratch;
- the same authored PNG compiled separately for texture 2 (`cement01`) to a
  907,056-byte stream, leaving 1,808 zero bytes and using 1,824 bytes of
  aligned scratch;
- combining both edits was rejected cleanly at the fixed-allocation boundary;
- a second combined attempt using the scene's `cement03` and `ibeam02` stock
  images was also rejected cleanly because the recompressed stream exceeded
  the 908,864-byte consumed cap.

These negative results are expected product behavior, not partial writes. The
staged project, active edits, source XISO, and any prior successful output stay
unchanged.

## Cross-pack positive evidence

The generalized route is not special-cased to `cement01`, 64x64, or pack `9`.
A real private-source compile resolved
`nfl2k5.stadium.o3136.c0006.scene1974.texture0011`, a 128x64 P8 occurrence in
archive pack `8`, regenerated its four rectangular mips, and produced an exact
879,536-byte fixed span. Its lossless encoded stream used 878,872 bytes. A
separate pack-9 non-cement compile is recorded above for `ibeam01`.

A two-edit real-source project also proved the multi-scene path. The same
user-authored magenta/cyan 64x64 PNG was compiled for scene 2648 texture 2 and
scene 2894 texture 2 in one call. It produced two non-overlapping pack-9 SCNE
spans in 15.456 seconds:

- scene 2648: 908,912-byte span, encoded size 907,056, 1,808 zero-gap bytes,
  1,824 scratch bytes, 5,223 decoded bytes changed, span SHA-256
  `a6c04b8fb7f1dee7c18cb988238436e1753386663eae357e4af130ea368c699e`;
- scene 2894: 916,608-byte span, encoded size 914,752, 1,808 zero-gap bytes,
  1,824 scratch bytes, 5,223 decoded bytes changed, span SHA-256
  `b0713cc833f93b9d8993a70f2a32ef7360b3bb1ab3c15a8a12c892824152244e`.

Both reports used the same independently derived preview hash
`cf6bab1735381a96d487299c946b0623d8de703e29006e7f13d42e5de1649b08`,
marked `contains_retail_bytes: false`, and resolved distinct absolute spans.
The real same-scene two-edit attempts described in the compression section
proved the complementary fail-closed boundary; the synthetic product contract
test proves those logical rows are staged once and passed to one composed-SCNE
compiler call.

The original copied-XISO `cement01` receipt remains under the user-local
`artifacts/stadium_texture_writer_spike/` directory. Its independent verifier
is intentionally the legacy single-target receipt. The supported product path
for arbitrary admitted textures is the unified provider, which performs the
normal source binding, non-overlap checks, atomic output build, and final union-
span verification.

## Unsupported and deliberately deferred

The writer rejects, rather than guesses at:

- non-P8 or unknown descriptor formats;
- incomplete, packed, aliased, overlapping, cross-pack, or malformed
  allocations;
- selectors not present in the current private source catalog;
- changed or stale cache/index/inventory/source-pack identities;
- wrong-size, non-RGBA, malformed, symlinked, or changing PNG inputs;
- an edit or combined scene that exceeds the compression or scratch cap.

This feature edits textures on existing geometry. It does not modify meshes,
UVs, material/shader semantics, lighting, collision, crowd placement, scene
ownership, or general model import. Those remain separate capabilities.

## Retail-data and runtime status

No private texture catalog, extracted source pack, stock PNG, SCNE span, retail
XISO, or other game byte is embedded in release code or a shareable project.
The app ships algorithms, format rules, selectors, identity metadata, and
human-authored replacements only. A user supplies and indexes their own legally
dumped XISO; stock previews remain in that user's private cache. Unified import
reports explicitly mark `contains_retail_bytes: false`.

Offline writer and build composition are proved. A generalized runtime spot
check in xemu is still separate work; this document does not claim that every
one of the 23,838 occurrences has been viewed in-game.

# Phase 0 — Research and tooling baseline

Date: 2026-07-09

## Outcome

Phase 0 is complete enough to begin forensic extraction. The main course correction is that neither supplied title may be assumed to use RenderWare. The supplied NFL 2K5 image has direct evidence for a proprietary Visual Concepts resource layer, original-Xbox D3D8/NV2A rendering, and CRI ADX/AIX/Sofdec audio/video middleware. APF 2K8 still requires XEX and inner-resource inspection, but its known outer archive is also proprietary.

The credible implementation strategy is a hybrid:

1. Preserve original address/function provenance in a machine-readable ledger.
2. Use Ghidra decompilation and signature databases for readable recovery.
3. Use static recompilation as a completeness layer for APF functions that are not yet readable.
4. Reimplement platform calls behind Linux SDL2/OpenGL/OpenAL/POSIX interfaces.
5. Recover Visual Concepts asset formats empirically and retain raw/intermediate/mod layers with manifests.
6. Promote code to `src/shared` only after semantic cross-architecture validation.

## Research deliverables

- [`formats_toolchain.md`](../research/formats_toolchain.md): XEX2/XBE layouts, entry points, sections, imports, compression/encryption, fixed-base behavior, SDK/library fingerprints, and tool usage.
- [`assets_middleware.md`](../research/assets_middleware.md): XMA/ADX/Sofdec, XPR/DDS/Xenos layouts, glTF requirements, proprietary VC resource evidence, RenderWare acceptance test, and conversion blockers.
- [`prior_art.md`](../research/prior_art.md): 2K modding/decompilation prior art, archive leads, static-recompilation precedents, script/config discovery, and cross-architecture matching methodology.
- [`xbe_tooling_setup.md`](../research/xbe_tooling_setup.md): reproducible original-Xbox XBE analysis setup once its tooling validation completes.

## Verified format facts

### Xbox 360 XEX2

- Big-endian signed container around a decoded PE-derived guest image.
- Absolute entry point and image base are optional-header values.
- Image may be AES-encrypted and uncompressed, basic sparse-packed, or LZX-compressed.
- Imports are module/version/ordinal records; static-library version tuples are the best XDK fingerprint.
- Security page descriptors and the decoded PE section table serve different purposes.
- Normal analysis should preserve the declared fixed guest base; no generic XEX relocation table was verified.
- Xenon code uses the Xbox 360 PowerPC ABI and 32-bit big-endian guest memory; calling it merely “generic PPC32” is insufficient.

### Original Xbox XBE

- Little-endian fixed-base executable derived from PE concepts.
- Retail entry point and kernel-thunk pointer are XOR-obfuscated, not encrypted.
- Kernel calls are ordinal thunks; much of XAPI, D3D8, CRT, and other XDK code is statically linked.
- Sections include virtual/raw mappings and SHA-1 digests.
- Library-version records are the first exact-XDK fingerprint to inspect.
- Runtime rebasing is not the default model; PE relocations are normally consumed while an XBE is built.

## Local image facts established during read-only inventory

- `ESPN NFL 2K5 (USA).xiso.iso` is a direct XDVDFS image. The `MICROSOFT*XBOX*MEDIA` volume descriptor is at byte `0x10000` (sector 32).
- Its main executable is `/default.xbe`, size `11,948,032` bytes. The disc also contains sixteen extensionless `vc_53450030/0`–`F` containers.
- `All-Pro Football 2K8 (USA)/All-Pro Football 2K8 (USA).iso` is an XGD2 image with a small UDF/DVD-video decoy partition.
- Its game partition starts at `0x0FD90000`; the XDVDFS descriptor is at absolute byte `0x0FDA0000`.
- Its main executable is `/default.xex`, size `38,408,192` bytes. The local pack names listed from this exact disc are `0A`, `0B`, `1A`, and `1B`; public APF scripts often describe a four-pack family using other sibling names, so the local table—not a filename assumption—must drive extraction.

## Tooling prepared and verified

- Built XboxDev `extract-xiso` v2.7.1 locally; it lists both source images without rewriting them.
- Installed official Ghidra 12.1.2 and verified its published SHA-256: `b62e81a0390618466c019c60d8c2f796ced2509c4c1aea4a37644a77272cf99d`.
- Installed XEXLoaderWV for Ghidra 12.1 and verified SHA-256: `4f5e4f817abab4810055e4904093c90879dcb44f329b3ba99ac52bb2a8a1f944`.
- Installed and verified Java 21 JDK, SDL2, OpenGL, GLEW, OpenAL, PNG, and Assimp development packages.
- Verified headless Ghidra startup using a workspace-local XDG configuration directory.

## What worked

- Located maintained open-source tools and executable specifications for both containers.
- Documented exact entry-point, image-base, import, section, encryption/compression, and library-version mechanics.
- Found public APF outer-archive research and a reproducible QuickBMS oracle.
- Found exact NFL 2K5 middleware/build strings for CRI ADX/AIX/Sofdec and D3D8/NV2A.
- Found a shared NFL/APF player-position enum, which is useful data-lineage evidence.
- Identified Ghidra BSim plus strings/constants/call-neighborhood validation as the defensible cross-architecture matching method.
- Identified XenonRecomp/UnleashedRecomp as the closest APF completeness/bootstrap precedent.

## What failed or was not found

- No public native Linux port or complete decompilation of either game.
- No public Xbox NFL 2K5 disc-resource extractor.
- No general decoder for APF inner model, texture, material, skeleton, or animation resources.
- No verified embedded scripting VM in either title.
- No verified RenderWare API, stream, or version for either title.
- No public x86-XBE ↔ PowerPC-XEX shared-function map.
- The requested names `xbrebase`, `xbox360tool`, `wxm32`, and `XCube` could not be tied reliably to maintained executable/asset tools with authoritative documentation. Syntax will not be invented.

## Blockers carried into later phases

```c
// PORTME: APF inner resource headers and CRC-to-logical-name mapping are unknown.
// PORTME: NFL vc_53450030/0-F directory/container structure is unknown.
// PORTME: NFL TXTR descriptor and exact NV2A swizzle path are unknown.
// PORTME: APF Xenos texture descriptors, endian modes, and mip-tail placement are unknown.
// PORTME: SCNE/SHAP model, skeleton, material, and animation schemas are unknown.
// PORTME: No RenderWare version is identified; do not fabricate rw_linux.h bindings.
// PORTME: No executable-level shared function has yet been validated across x86 and PowerPC.
```

These gaps do not block Phase 1. They do block claims that all assets can already be converted to PNG/glTF or that either game can already display its original menu natively.

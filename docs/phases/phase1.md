# Phase 1 — Extraction and reconnaissance

Date: 2026-07-09

## Outcome

Phase 1 is complete. Both source images were extracted without rewriting them, every extracted top-level file was hashed, both executables now load at their verified guest addresses in Ghidra, SDK/import boundaries are labeled, and both games' outer resource directories are structurally mapped.

The result is reconnaissance, not a completed native game: executable and archive boundaries are now trustworthy enough to begin bulk decompilation, function classification, and inner-resource recovery without guessing.

## Reproducible identity

| Input | SHA-256 |
|---|---|
| NFL 2K5 XDVDFS image | `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9` |
| APF 2K8 XGD2 image | `c45aab61de93773dfe25adbae5749ad5adb3f3369a6c0106b2159ad603b6fe53` |
| NFL `default.xbe` | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| APF `default.xex` | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |

Full hashes are in [`originals.sha256`](../../reports/manifests/originals.sha256) and [`extracted_files.sha256`](../../reports/manifests/extracted_files.sha256).

## NFL 2K5 executable

Canonical reports: [`xbe_tooling_setup.md`](../research/xbe_tooling_setup.md), [`nfl2k5_xbe_header.json`](../../reports/headers/nfl2k5_xbe_header.json), and the complete reports under `reports/headers/`.

| Field | Verified value |
|---|---:|
| Format | retail XBE, x86 little-endian |
| Image base | `0x00010000` |
| Entry point | `0x00016BD1` |
| Kernel thunk table | `0x004E3AE0` |
| Sections | 22; all stored SHA-1 section digests independently verify |
| Kernel imports | 186 named ordinals |
| Regular/feature library records | 9 + 1 |
| XDK build | 5849, with per-library QFE records preserved |
| Debug build path | `C:\projects\built\vcsports\us\obj\xbox\nfl\clean_opt\nfl_clean_opt.exe` |
| XTLID records | 648 |

The Ghidra XBE loader was built against Ghidra 12.1.2, validated first on the open nxdk triangle fixture, and then validated on this exact executable. The entry point decompiles successfully.

XbSymbolDatabase produced 651 SDK candidates:

| Namespace | Candidates |
|---|---:|
| D3D8 | 236 |
| DSOUND | 305 |
| XAPILIB | 82 |
| XGRAPHC | 4 |
| XONLINES | 24 |

These labels define platform/library boundaries; they are not counted as recovered Visual Concepts game functions without further evidence.

## APF 2K8 executable

Canonical reports: [`apf_xex_recon.md`](../research/apf_xex_recon.md), [`apf2k8_xex_report.json`](../../reports/headers/apf2k8_xex_report.json), and [`apf2k8_imports.tsv`](../../reports/headers/apf2k8_imports.tsv).

| Field | Verified value |
|---|---:|
| Format | retail XEX2, PowerPC A2ALT with 32-bit big-endian guest addresses |
| Image base | `0x82000000` |
| Entry point | `0x84BE9D08` |
| Encryption/compression | retail AES-CBC / normal LZX, 32 KiB window |
| Decompressed PE bytes | 54,001,664; SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| PE sections | 9 |
| `.pdata` functions | 18,472 |
| Ghidra functions after analysis | 21,347 |
| Logical imports / thunks | 347 / 334 |
| Static XDK libraries | build 5426 |
| XAM/kernel import ABI | 2.0.5759.0 |
| Original name | `nfl_clean_opt_submission_ready.xex` |
| Link timestamp | `2007-06-12T22:11:24Z` |
| PDB | `...\XENON\NFL\CLEAN_OPT\default.xex.pdb`, GUID `3d9e930e-cc38-478a-9b3b-87ed5607c5fa`, age 23 |

The published XEXLoaderWV binary required a Java 21 rebuild and an LZX output-size overflow correction. An independent C++ extractor verified every chained compressed block and reproduced the PE byte-for-byte before the patched Ghidra import was trusted. The canonical Ghidra program is `ghidra_projects/apf2k8:/default.xex`; an older diagnostic DOS16 import in that project is invalid and must be ignored.

Thirty-three APF function entries produced decoder/decompiler warnings. They are listed in `reports/headers/apf2k8_decompiler_warning_addresses.txt` and remain explicit Phase 2 `PORTME` work.

## Resource containers

Canonical report: [`container_recon.md`](../research/container_recon.md).

### APF

- `0A` begins with big-endian magic `0xAA00B3BF` and declares `0x800` alignment.
- The table names the exact local volumes `0A`, `0B`, `1A`, and `1B` dynamically.
- It contains 1,543 `{CRC, aligned offset, aligned size}` records.
- Two records cross physical volume cuts and need explicit stitching.
- 1,473 entry heads use proprietary magic `0xFF3BEF94`.
- [`tools/apf_outer.py`](../../tools/apf_outer.py) provides bounded `--list`/manifest behavior; its deterministic manifest is [`apf_outer.json`](../../reports/manifests/apf_outer.json).
- The public QuickBMS script is a useful oracle but does not explicitly handle both cross-volume cases.

### NFL

- Container `0` has a little-endian header, 36 size slots, and 4,323 records in the verified order `{name_id, size_bytes, offset_blocks}`.
- Physical packs `0`–`F` form one virtual stream of `0x173337000` bytes.
- Thirteen logical entries cross physical cuts; one entry spans packs `5` through `8`.
- Entry heads classify 1,127 `SCNE`, 1,020 `TXTR`, 681 `AUDO`, 634 `Unif`, 510 `TSET`, 76 `ROST`, and 30 MPEG program streams, among other proprietary types.
- Recovered UTF-16 names include `logos.cdf`, `igfaces.cdf`, `portrait.cdf`, `sfx_game.bnk`, roster, uniform, animation, crib, and UI identifiers.
- No entry-aligned DDS, PNG, XPR, RIFF, or RenderWare stream was found. `TXTR`/`SCNE` are wrappers that still need parsers.

## Cross-title evidence

- Both executables retain `NFL` / `CLEAN_OPT` Visual Concepts build lineage.
- APF contains explicit `vclibrary` paths and `.vcc`, `.mvcc`, `.game`, and `.items` identifiers; NFL has the related `TXTR`, `SCNE`, roster, uniform, and content names.
- Both games use a proprietary Visual Concepts resource vocabulary, but their outer archives and CPU code generation differ.
- No x86/PPC function pair is yet validated as the same source function. Shared-engine promotion remains evidence-gated.
- Neither executable provides a positive RenderWare marker or validated RenderWare stream. The correct working abstraction is a Visual Concepts resource/renderer layer.

## What worked

- Full extraction of both images and hash verification of every top-level output.
- Bounds-checked XBE parsing, all section digest checks, kernel ordinal mapping, Ghidra import, entry decompilation, and SDK signature labeling.
- Independent XEX AES/LZX reconstruction, native Ghidra import, `.pdata` seeding, import naming, and full analysis.
- Structural recovery and invariant testing of both outer resource directories, including cross-volume cases.
- Reproducible parsers, machine-readable reports, raw header artifacts, and canonical Ghidra projects.

## What failed or remains incomplete

- APF's unmodified XEXLoaderWV release could not load this image; the documented local fixes are required.
- APF's matching PDB is not present.
- The APF `.reloc` bytes are outside the signed/decompressed image and are not recovered; the loader's zero-filled mapping is not source data.
- Thirty-three APF functions still trigger decoder/decompiler warnings.
- Neither title's inner texture, mesh, skeleton, animation, material, or general audio-bank schema is decoded.
- No embedded script VM is proven; `.game` may be data rather than bytecode.
- No executable-level shared-function pair is confirmed.

## Phase 2 blockers and explicit handoff

```c
// PORTME: review APF decoder warnings at every address in
// reports/headers/apf2k8_decompiler_warning_addresses.txt.
// PORTME: classify every function as game, SDK, middleware, generated helper,
// or unresolved before counting decompilation progress.
// PORTME: no x86/PPC function pair is yet safe to move into src/shared.
// PORTME: trace NFL TXTR/SCNE and APF FF3BEF94 loaders before defining schemas.
// PORTME: APF .game/.items content is not proven to be an interpreted script.
// PORTME: APF .reloc is unavailable and must not be treated as recovered data.
```

These items block a faithful original menu/gameplay port, but they no longer block bulk pseudocode export, a complete address ledger, static-recompilation experiments, or native platform-wrapper implementation.

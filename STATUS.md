# 2K5 Mod Studio — v1.0 RC42 Release Status

> **APF 2K8 parallel product status:** read
> [`docs/mod_editor/APF2K8_STATUS.md`](docs/mod_editor/APF2K8_STATUS.md). The
> source code and UI identify as the **`0.1.0-alpha.35`** release, whose
> published asset is `apf2k8-mod-studio-0.1.0-alpha.35-20260727.tar.gz`
> (`1,110,239` bytes, SHA-256
> `dc9e149a107f8111601483382c080eff72ae81e4f0d386c802c7614fc9d2c596`).
> The previous
> sealed package is `0.1.0-alpha.34`; its `815,213`-byte archive checksum is
> `beb8b1409b83e052e6c432a9ddc4a79f9f990820c79e0b67dea894dc869393f4`
> and is authenticated by the adjacent mode-`0444` `.sha256` sidecar.
> `0.1.0-alpha.33` remains preserved; its `808,649`-byte archive checksum is
> `e071a6b42bbc5270c1cee2517c27c3115de03966977b1b178b92649e18982270`.
> Alpha.32 is the previous sealed release; its `804,083`-byte archive checksum is
> `d80e690d3eec13b962ecaa96d6b2f725f0e2beaa71d8ce137a860e4d67735de1`.
> Alpha.31 remains preserved; its `795,740`-byte archive checksum is
> `d0e5bd23a56881574a56760709ca87dd76e47bdbe5a431b1f67be57e56c19e5a`.
> Alpha.30
> is the previous sealed release; its `792,312`-byte archive checksum is
> `6f0ca573707ba28d4fba296642e80a7337295d899605f9f3a93c90663819a999`.
> Alpha.29 remains preserved; its `785,069`-byte archive checksum is
> `76c7e88786ffccb3a65a26acaa0698c3840b2be6fa46a6c663cfd22a9b76ea80`.
> Alpha.28 remains preserved; its `781,027`-byte archive checksum is
> `33fe5e1e1c0c11001b159f8ee909f43a4640b6952e33a941753bd00230bd55df`.
> Alpha.27 remains preserved; its `772,445`-byte archive checksum is
> `89e40ccf6e20e221137c634d170f7c7293a805efec7f820c5dd29c53e2b60c84`.
> Alpha.24 remains preserved; its `710,512`-byte archive checksum is
> `cfcf0990a93df6d2e1f519cac0dd477117be34ed8ca55a44cbb9308467a596c6`
> and is authenticated by the adjacent `.sha256` sidecar.
> It ships explicit
> bounded Audio waveforms, atomic 47,814-row audio export, a 258-record Field
> Art inventory, exact team display-name and player first/last-name editing,
> complete shared-name alias disclosure, true independent 0–99
> Replace/Revert for all 28 base ratings on all 2,254 player records, and a
> source-bound 63,112-cell ratings-sheet importer with conflict preview, a
> separate atomic export for all 19 original physical audio banks, and a
> self-describing 47,814-row cue archive with deterministic CSV, ordered
> playlist, and exact per-file checksums. Team-name, player-name, and rating
> edits compose into one token-preserving ROST build and remain
> retail-free semantic deltas in projects. Alpha.23 ships strict exact-slot
> pre-encoded XMA1 editing for all 2,261 standalone `AUDO` sounds and all 45,514
> individually addressed AUSB substreams. Alpha.24 also adds exact Position
> (17) Apply/Revert/project/Build for all 2,254 players and refuses APF/2K5
> builds before staging when the destination lacks the complete output size
> plus a 512 MiB margin. Its visual and first changed-position Xenia spot checks
> remain pending. Alpha.25 adds metadata-only replacement folders, target/
> alias baseline locks, progress/cancel, and one-action atomic import for all
> 47,775 editable sounds. Alpha.26 adds deterministic metadata-only ZIP hand-off
> and direct edited-ZIP import, plus Ctrl+1 sidebar focus and larger-font/
> accessibility shell polish. Alpha.27 adds selected-sound exact-shape PCM16
> authoring through a separately installed user-configured XMA1 encoder while
> preserving the direct pre-encoded and folder/ZIP routes. Alpha.28 extends
> that bridge to metadata-only PCM16 batch packs. Alpha.29 fences debounced
> Audio page actions with an applied query token, adds exact-order one-level
> shortlist Clear/Undo, and owns preview success/failure by model and selected
> row. Alpha.30 carries a request-owned cancellation event through preview and
> waveform UI, facade/session/private I/O, and all four AUDO/AUSB original and
> staged decoder paths. FFmpeg/ffprobe Cancel now terminates the complete owned
> process group and publishes no partial WAV or receipt. Alpha.31 adds the
> complete applied Audio match set to the shortlist in one stable, deduplicated
> action with an atomic 256-sound cap and cached 47,814-row result. Close and
> source switching now cancel and drain private readers before session teardown,
> while protected builds keep their existing close guard. Its full APF suite
> passes 487/487. Alpha.32 adds fully validated, read-only Audio replacement-pack
> Preview; an explicit Apply reopens and revalidates the exact pack under an
> opaque source/session/project-revision token. Its corrected worker-idle barrier
> drains Preview before confirmation or Apply. The full APF suite passes 496/496,
> and the combined cross-title suite passes 1105/1105. Alpha.33 adds a
> selected-sound `.xma` / exact PCM16 `.wav` drop target across all 47,775
> individually editable AUDO/AUSB rows. Each format enters its existing button-
> owned writer; links, folders, remote/multiple files, unsupported rows, and
> busy PCM/direct/pack states are refused before mutation. All related controls
> fence from submission through worker unregistration. Its APF suite passes
> 504/504 and the combined suite passes 1113/1113. The exact 104-file stage and clean
> extraction pass the retail-free and 66-module runtime gates and reproduce
> byte-for-byte. Alpha.34 adds retail-free custom titles/notes, annotation-aware
> search and **Labeled only**, annotation-only projects, and metadata-aware
> collection export for all 47,775 playable cues. It is now sealed: the
> 105-file/15-directory stage passes the retail-free gate before and after the
> 67-module runtime closure, the 120-member deterministic rebuild is
> byte-identical, and the cross-title suite passes 1156/1156; the mode-`0444`
> 815,213-byte archive checksum is
> `beb8b1409b83e052e6c432a9ddc4a79f9f990820c79e0b67dea894dc869393f4`. A separate
> independent hostile review and real-source Xenia runtime proofs remain
> recommended before wide publication. The seal is terminal-only and has not
> addressed the user's desktop or pointer.
>
> Alpha.23 extends strict pre-encoded RIFF XMA1 Replace/Revert, project
> save/load, replacement preview, and typed Build to **all 45,514 semantic AUSB
> substreams** backed by **45,513 canonical physical ranges**. The one shared
> `cwdloop` range discloses both owners, deduplicates identical alias edits, and
> rejects divergent writes. The one Track 3 range that crosses `0A`/`0B` is
> compiled as two independently source-guarded spans. Complete packet-level
> retail protection fingerprints every `0x800`-byte source packet in both the
> 2,261 AUDO slots and all 45,513 canonical AUSB ranges. Session admission,
> project load, modified preview, and Build reject a replacement containing even
> one complete packet from either family, including cross-family transplants;
> projects contain only user packets and retail-free semantic metadata. The
> 40,316 unique whole-AUSB-payload hashes remain an inventory metric, not the
> authorization boundary.
>
> The private Alpha.23 candidate booted, selected **Track 12 — Bury Me Standing
> Remix**, and visibly remained in playback for 25 seconds without a crash.
> The completed capture experiment was negative/inconclusive: the final sustained
> segment matched neither mutated candidate nor stock Track 12, the best
> 17-second `|NCC|` was about `0.031`, distinguishing frames favored neither,
> and a self-control confirmed classifier power. This is positive
> boot/selection/stability evidence, but it proves neither authored-audio
> consumption nor stock fallback; runtime status remains partial. The
> FFmpeg 6.1.1 source sweep decoded 18/30 jukebox sides; replacement input still
> must pass the stricter complete decoder check. Ordinary WAV/FLAC input still
> needs a distributable XMA1 encoder. Separately, a real-source final Build gate
> rejected an 8-bit-mutated Track 12 near-retail candidate at packet 0 that the
> old whole-payload check admitted; the two-domain scan completed in 14.13
> seconds at 208,896 KiB peak RSS. This is safety evidence, not audio-causality
> evidence.
>
> Alpha.24 carries forward the 32-team × 53-row roster planner: 42 source memberships
> are runtime-visible and eleven reserves are project-only. Reserve plans never
> copy the 42 source rows, and Build does not apply slots 43–53. True 53-active
> teams still require a version-pinned XEX accessor/direct-consumer patch plus
> owned side-table storage. The focused Alpha.24 closure passes 163/163 tests.
> Its sealed release contains exactly 100 allowlisted files, and both the stage
> and independent extraction pass the retail-free and 64-module runtime gates
> without shipping retail game bytes.
>
> The first post-seal static roster result is negative and useful: stock code
> reads and writes `team +0x120..+0x126`, so the old idea of placing packed
> reserves at `+0x120` is retired. The compact representation still fits by
> size, but safe storage is unresolved. The next experiment uses no team-tail
> write. The exact Team-0/CB hook, native Linux Xenia binary, and fail-closed
> headless runner are now implemented and independently GO-reviewed. The runner
> passes 11/11 synthetic tests, and its real-source dry-run preserved all six
> source files / 3,919,218,688 bytes while launching no GUI. A log-only control
> must still prove the exact defensive consumer before the one-player override
> is enabled; the required Spark desktop operator is unavailable in this
> session. A completed post-hook static census now shows why that first test
> cannot be widened casually: the XEX has 93 direct calls to the two primary
> position count/getter helpers, at least 25 direct roster-class consumers,
> two explicit append caps at 42, and a separate 17-position-by-42-player
> layout builder whose 3,088-byte stack frame cannot fit a 17-by-53 array.
> The preferred true-53 path remains an emulator-owned eleven-player side
> segment plus a coordinated consumer shim; a one-byte or one-helper patch is
> now explicitly ruled out. No emulator or GUI was launched for this census.
>
> The broader observation-only **Membership Census v1.1** is now compiled and
> independently GO-reviewed at Xenia commit
> `d09cae8d8374324048ef603d48a9c1696b39d552`. Its hostile-callback sentinel
> preserves the thunk contract across 22 assertions, and the combined offline
> protocol gate passes 43/43 tests. Exact read/write widths `1..16` are accepted
> (including partial-vector width 3), width 17 fails closed, and 32/128 remain
> write-only. The native binary SHA-256 is
> `712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d`.
> It is default-off and has not been launched; the live scenario matrix still
> requires the designated Spark desktop operator.

Last updated: 2026-07-25 (America/New_York)

## Published releases — the assets actually on GitHub

The seal receipts throughout this document describe a **staged package** for a
version. The GitHub release **asset** for that same version is a different
tarball: built from the same allowlist, but additionally carrying the bundled
`extract-xiso` binaries, their build receipt, and the release-time documents —
all of which are gitignored release-build inputs. Both artifacts are pinned, and
they are not interchangeable. This section records the asset identities so the
repository's receipts describe what a user actually downloads, rather than only
what was sealed.

### `beta-17` — 2026-07-28 · CURRENT

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-17>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC42-20260728.tar.gz` | 9,616,358 | `c45ea25e0b763cf932b327cc9d237fa81d2a057ea7b1a5aa96c91e404d1f396c` |
| `apf2k8-mod-studio-0.1.0-alpha.45-20260728.tar.gz` | 1,133,134 | `6cdff11f3e7ec03a5f3dfe2225dae3526d86a5e3a435bc6ee68bea1c12822d62` |
| `2K5-Mod-Studio-1.0-RC42-Setup.exe` | 55,990,350 | `c5a2a0c78f6a4be9279e209a851bd871188d6a15b98234b730416e72a9a182e2` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.45-Setup.exe` | 52,363,680 | `5d9e52caf6db404ca2e30aae0203c2ecbb461be85e9f930929dcc30ba72f0f4b` |

All Textures is a real workspace: 3,024 standalone P8 targets (1,770 end-zone
panels, 1,024 goalpost pads, 225 divots overlays, 5 shared equipment textures)
with search, preview, Export/Replace PNG and Revert.

The route that mattered is the composed build. A `p8_texture` edit kind binds
per-extent -- the build locates each pack in the user's own image, re-derives
the offset, and verifies the pack and span hashes. Proved on three differently
packed dumps: identical 31,652 changed bytes on all three.

The Nameplate Atlas decoded transposed (32x1024 instead of 1024x32) and shredded
every letterform; only VC_P8_LINEAR orders its size halfwords that way, so the
4,081 A1R5G5B5 player strips are untouched.

Stadium geometry export is command-line only and its card says so. Whole-model
stadium import still does not exist.

### `beta-16` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-16>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC41-20260728.tar.gz` | 9,488,302 | `b59a0d0220be7b6cb5e08379bd4c447fa2420565f29ce8202196f3ed354cf497` |
| `apf2k8-mod-studio-0.1.0-alpha.44-20260728.tar.gz` | 1,132,787 | `3b6cc0ea56aa97b9b3ebdaacef234761703e5a93d26dc704628943e7f36cedd7` |
| `2K5-Mod-Studio-1.0-RC41-Setup.exe` | 55,916,430 | `9f472c6d7ef8891f7f26a35d811c6eadc3af2b2822cad92c77a2bd1958b40fce` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.44-Setup.exe` | 52,363,061 | `9f0332669d7fac5107fddeb06e4d0c0a3dc053396a9de919b875c5199f185c11` |

Fixes a regression beta-15 introduced: QTabWidget carried no stylesheet rules,
so the new Uniforms & Equipment tab strip rendered in the platform light style
with unreadable labels and put the uniform browser behind it. The strip is
styled and Uniform Sets is pinned as the landing tab.

Capability cards are labels with no controls, so an "Editable" pill on one
reads as a broken button. Seven of nineteen NFL 2K5 writers have an in-app
workspace; each card now names that workspace or states it is command-line only
and prints the command.

Still ahead: the All Textures workspace and stadium model import. Stadium
geometry export to glTF works today; whole-model import does not exist.

### `beta-15` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-15>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC40-20260728.tar.gz` | 9,486,881 | `287ba54f734bf91acc7fea279dfcf83342414f9d3ae083fc239088f229efb56f` |
| `apf2k8-mod-studio-0.1.0-alpha.43-20260728.tar.gz` | 1,132,681 | `187f66c642ea8708601b248e1625777d8de9a974fc3e90649191dd4b763e77f5` |
| `2K5-Mod-Studio-1.0-RC40-Setup.exe` | 55,917,960 | `3f5d7dbf1d5c261b332927f8a014faaad1ec27ca6b3f6438dab881f0468edca7` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.43-Setup.exe` | 52,361,519 | `0ef084513f5bdc4c49b796c69dd673a405161b4db06c26d1feb12fb52c5c7c08` |

Uniforms & Equipment built its browser around one capability and dropped the
other three filed under that category, so the facemask/turtleneck colours were
enabled and still unreachable. The category is now two tabs, Uniform Sets and
Colours & Other Tools. Verified headless against the shipped build.

`mod_editor.__version__` had not moved since RC36, so the window reported a
version three releases old. It is now asserted against STATUS.md and the newest
changelog heading.

### `beta-14` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-14>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC39-20260728.tar.gz` | 9,486,332 | `4e282225464c93f96e2b7e63f78eb49c94560fa87f8e8ed5b98dfb12bf8c89f1` |
| `apf2k8-mod-studio-0.1.0-alpha.42-20260728.tar.gz` | 1,132,573 | `f727ee9db33de0415fff7b38cd6c651f785d43db3f1d12145ecb8747d4628bad` |
| `2K5-Mod-Studio-1.0-RC39-Setup.exe` | 55,908,087 | `77786e55b69cee53dc580e52c6595f4f8905b79b1a5bd1370dee941159f18d55` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.42-Setup.exe` | 52,359,139 | `a9487afa79c1f31c1ca58c8205c3228be5b9c5ee801e4b29648fddb375cc06f5` |

The shared PNG importer accepted only colour type 6 at bit depth 8,
non-interlaced, so an image editor's ordinary export -- usually colour type 2
(RGB) or 3 (indexed) -- was rejected as if the file were wrong. Every colour
type and bit depth the specification defines now decodes and is widened to
RGBA internally, interlaced or not, with `tRNS` honoured. Verified pixel-exact
against Pillow on every variant.

The exact-dimensions rule stays: a texture fills a fixed byte span, so a
differently sized image cannot occupy it. The message now says so.

### `beta-13` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-13>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC38-20260728.tar.gz` | 9,483,708 | `088dad57b92b147b27ac337a645e57025bb27276bb1bd781a1bcd2463b155d9d` |
| `apf2k8-mod-studio-0.1.0-alpha.41-20260728.tar.gz` | 1,132,386 | `2f8b7f7d072327360e52c8b6343b468f4a34d040e94b5d654256104fd4b4b61c` |
| `2K5-Mod-Studio-1.0-RC38-Setup.exe` | 55,915,151 | `7e424a6ed2ca4f4765757e3cadcf68b682108ea3fc26c1f04122b39d6f1195da` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.41-Setup.exe` | 52,359,113 | `6fa468fbfcd8ec85819885e8133e5fc79c79ec5a86779a156777c73b99ee2825` |

New All Textures workspace: 36,761 of the disc's 57,208 textures are editable
from a PNG, recompressed into the original byte span. Covers the real teams'
end-zone art, goalpost pads, `divots`, the `mark*` overlays and the shared
equipment textures. P8 only; other Xbox formats are refused by name.

Four shipped writers -- audio, generic texture import, Crib bar-monitor and
uniform colours -- stopped gating on the whole container's size and SHA-256,
which had made them unusable on any legally dumped disc that differed from the
project's own copy. Identity is per-extent everywhere now.

Proved on three differently packed images of the same game: identical 31,652
changed bytes at three different absolute offsets.

### `beta-12` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-12>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC37-20260728.tar.gz` | 9,475,714 | `b269206ded978509500544f322ff7fe6383bbbe6d25e927a11a5adf85d060349` |
| `apf2k8-mod-studio-0.1.0-alpha.40-20260728.tar.gz` | 1,131,263 | `8df1f32890f1f5ba0488ad7addb262f62f2bb4ebb67e223015eddafa45ba5d6c` |
| `2K5-Mod-Studio-1.0-RC37-Setup.exe` | 55,900,578 | `a0f10b019ac385ad3eb481c87bf529e0b7c9d807d7d518faa32e4bd09155a5b1` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.40-Setup.exe` | 52,357,508 | `f66e9272cdeece95191ffb2194a5c1b099ed7b6cb9dc21acc4a05f70baca1803` |

A legally dumped APF disc could be refused with "does not appear to be a valid
xbox iso image". The bundled `extract-xiso` probes four fixed partition offsets
and rejects anything else -- the 2K5 layout defect, hidden inside a vendored
binary. The disc is now read with the project's own searching XDVDFS reader
first. The report that prompted it was the PlayStation 3 release of the same
game named `.iso`, so containers are now identified by structure and named:
ISO 9660 volumes, PS3 and PlayStation discs, STFS packages, ZIP/RAR/7z.

On the 2K5 side the two `Unif` colour words now say what they own: word 0 is
the facemask/faceshield tint and word 1 is `HI_turtleneck`. Repainting the
coloured square on a helmet texture cannot move the facemask, because the
facemask is a separate material fed by that value.

### `beta-11` — 2026-07-28 · superseded

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-11>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC36-20260728.tar.gz` | 9,473,398 | `028959b26e991e9ef5ec0a75d48d7ba19afa79f2b712cc96a577c705c9cf3cc4` |
| `apf2k8-mod-studio-0.1.0-alpha.39-20260728.tar.gz` | 1,118,445 | `db613a4e0b1929600335357bf152b3bb3004204d7638550ee803e6bbca6fb03f` |
| `2K5-Mod-Studio-1.0-RC36-Setup.exe` | 55,900,541 | `79a3c5ec3a114febad6914065763b70e9676571c3f0f979f122a693375379f06` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.39-Setup.exe` | 52,351,553 | `5a2b14f212d99e1a3beb280c37b7cec7e874a5f1aedf3386acb30aeb1f6d4bf8` |

Export Team Kit as a folder failed on Windows for everyone: the export reserved
its destination with `mkdir` and renamed the staged tree onto it, which POSIX
allows and Windows cannot do for a directory at all. It now publishes through
`platform_compat.publish_no_replace`, as three other publishers in the tree
already did. The ZIP export's hard-link publish is routed the same way, since
`os.link` needs NTFS and an external drive holding disc images is often exFAT.
No disc, indexing or build behaviour changed; the beta-10 fixes were re-verified
against the reporter's pressed-disc read from this published tarball.

### `beta-10` — 2026-07-27 · superseded by beta-11

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-10>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC35-20260727.tar.gz` | 9,472,304 | `6ee4d6f8922fe1ebd4636af45b7e4aa632c65643d3b0d5dfb26acd08ee241a7a` |
| `apf2k8-mod-studio-0.1.0-alpha.39-20260727.tar.gz` | 1,118,430 | `89416520a43dab0a94b2f3fcad465ac54a4bf5c539b9f0dbd32e6397db792b37` |
| `2K5-Mod-Studio-1.0-RC35-Setup.exe` | 55,901,479 | `1e64ab600d59454f74185cd4f51a25333aac998c8e032d6f4e2d2546943a6b44` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.39-Setup.exe` | 52,351,553 | `5a2b14f212d99e1a3beb280c37b7cec7e874a5f1aedf3386acb30aeb1f6d4bf8` |

beta-9 loaded a user's disc but could not build from it: the build path pinned
sector numbers and absolute byte offsets, both of which are properties of
whoever assembled the image rather than of the game. All nineteen files sit at
different sectors in a pressed disc, an extract-xiso rebuild and a repack while
being byte-identical. Files are located by name now and offsets derived from the
image in hand. Verified by building real mods from both of the reporter's images
and again from this published tarball.

### `beta-9` — 2026-07-27 · superseded by beta-10

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-9>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC34-20260727.tar.gz` | 9,471,005 | `646ebd0d04eb715df6daa37daa6582ee6bd4f1697369d25057607646f6b24aeb` |
| `apf2k8-mod-studio-0.1.0-alpha.39-20260727.tar.gz` | 1,118,430 | `89416520a43dab0a94b2f3fcad465ac54a4bf5c539b9f0dbd32e6397db792b37` |
| `2K5-Mod-Studio-1.0-RC34-Setup.exe` | 55,900,424 | `c59e6306275f6793468fcdd86dde5d91604f1fda7d7b0d635813862d6ae33126` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.39-Setup.exe` | 52,351,553 | `5a2b14f212d99e1a3beb280c37b7cec7e874a5f1aedf3386acb30aeb1f6d4bf8` |

Developed against a reporter's own two disc images rather than this project's
copy, which is what exposed the two causes our extract-xiso-normalised image
could not contain: a raw read carries two filesystems, and a pressed disc marks
files `0x80` where a rebuild marks them `0x20`. Container equality is also gone
from the build, audio and stadium lanes, so an image that loads can now finish a
build. See `CHANGELOG.md`.

Verified from the published tarball against both of his images: recognised,
fully indexed (16 packs, index byte-identical to its pin), build-gate accepted.

### `beta-8` — 2026-07-27 · superseded by beta-9

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-8>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC33-20260727.tar.gz` | 9,467,197 | `67c073f7fdca3cf3be9861bf49dd32f29dd66151b2adfe1aa7a59044295c4143` |
| `apf2k8-mod-studio-0.1.0-alpha.38-20260727.tar.gz` | 1,117,824 | `decba035e9536d201ebf50852aab5d104e41a1fbd3d2898597c747f028156839` |
| `2K5-Mod-Studio-1.0-RC33-Setup.exe` | 55,894,637 | `98f3b6da5b0ba7b7020f0be2c6de18af100612630014f07e58beed241638f81e` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.38-Setup.exe` | 52,347,030 | `a44bae57aa64d7959d31ba8fb29c0ec0e51c3b2c87c74160c8b7a9a924475d30` |

The index the editor builds from a user's disc was written in text mode, so
Windows rewrote every line ending and the result could never match its pinned
size or hash. Unconditional: every Windows user, every image. Fixed repo-wide --
38 text writes across 29 shipped files now pin the line ending, held at zero by
a test. See `CHANGELOG.md`.

### `beta-7` — 2026-07-27 · superseded by beta-8

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-7>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC32-20260727.tar.gz` | 9,466,662 | `ddc23b37676e8f9efc0941d0d298c7de5a048ea681dd2a4c342f11a9d02be5fb` |
| `apf2k8-mod-studio-0.1.0-alpha.37-20260727.tar.gz` | 1,117,404 | `fc1fce34c50ddce003923307172ac6be9d4eed5dc6a055a2c51801717338b46f` |
| `2K5-Mod-Studio-1.0-RC32-Setup.exe` | 55,889,723 | `8927f974689b8d95abb672a805eb0b64b77d3107d6afbd7a7efdec842fd7624f` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.37-Setup.exe` | 52,353,300 | `3400ce01378ae134b7c31becbbc2bdc78569af25f8612746cb9f6c5050a31b6e` |

beta-6 fixed only half of the dump-acceptance problem and shipped anyway. Two
follow-on failures came back from the same users: a raw disc read whose
partition offset was not in the list beta-6 probed, and -- reaching only people
who *install* rather than unzip -- `ModuleNotFoundError: No module named
'nfl_outer'` immediately after loading, because the embeddable runtime's `._pth`
defines `sys.path` without adding a script's own directory. Both are fixed here
and both are pinned by tests that need neither game data nor Windows. See
`CHANGELOG.md`.

**Every digest in this table was generated from the built files, not
transcribed.** The two installer digests in the beta-6 notes were written out by
hand from a truncated printout and the tail was wrong; they were corrected in
place, and this table is now produced mechanically so that cannot recur.

### `beta-6` — 2026-07-27 · superseded by beta-7

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-6>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC31-20260727.tar.gz` | 9,459,810 | `c0809e38418f4e1a54706a30a2ad0a6c73fe5f42c46e4e2540fd3c398db160ce` |
| `apf2k8-mod-studio-0.1.0-alpha.36-20260727.tar.gz` | 1,113,374 | `2872293000b7d7e972393313cfeb6ac2c4f26df9ba3d9e1cf5fc376a732b7ca0` |
| `2K5-Mod-Studio-1.0-RC31-Setup.exe` | 55,896,204 | `85e50378fc1be69224205ced4639819523966cd5e2d2c1701f7a451528502bbc` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.36-Setup.exe` | 52,351,547 | `7714ff418a6f832b185529ffcb4adf77db70f8f533d53d7dc9d473befaa5a247` |

The 2K5 editor now accepts any legal dump of the disc rather than only the
project's own rip; see `CHANGELOG.md`. **This is the first release whose
installers are byte-reproducible**: the mtime normalisation added after beta-5
works, and two from-scratch builds of each installer were compared byte for
byte, as were both tarballs.

### `beta-5` — 2026-07-27 · superseded by beta-6

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-5>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC30-20260727.tar.gz` | 9,434,991 | `01d5d6a991ffc5c9978fbdd0700859cf3c00ad74afea490eda0472e0dcfe4183` |
| `apf2k8-mod-studio-0.1.0-alpha.35-20260727.tar.gz` | 1,110,239 | `dc9e149a107f8111601483382c080eff72ae81e4f0d386c802c7614fc9d2c596` |
| `2K5-Mod-Studio-1.0-RC30-Setup.exe` | 55,879,269 | `a6829e23c03ae7f69d3d6ba437260ef20ef4a6badb6d861f04ffe9afd9f64118` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.35-Setup.exe` | 52,344,282 | `07b257330e961cc7078ae238238692fba5c5af4e918260fd18406193a5dccb77` |

Every asset changed, because editor code changed: four APF writers passed
`os.O_CLOEXEC` to `os.open` as a bare attribute, which CPython on Windows does
not define, so field art, team logos, the logo cache, the generic texture writer
and uniform mips all raised `AttributeError` before doing any work. A user
reported it against the endzone flow. `CHANGELOG.md` has the detail.

Before these bytes were built, both **beta-4** tarballs were rebuilt from the
`beta-4` tag and reproduced byte-for-byte, so the pipeline was proved to match
the published reality before it was used to change anything. Both beta-5
tarballs were then built twice independently and compared byte for byte.

**The installers are content-reproducible, not byte-reproducible, and the
distinction is worth stating exactly.** Each of the five external inputs — the
CPython embeddable interpreter and four wheels — is pinned to an exact SHA-256
and verified before use, and the staged runtime tree is reproducible: two
independent builds produced 2,674 files with an identical content hash. NSIS
itself is deterministic, verified here by compiling one fixed staged tree twice
for a byte-identical result. What does **not** reproduce is a build from
scratch: extraction and `pip` stamp fresh mtimes on all 2,674 runtime files, and
NSIS records mtimes in the archive, so the compressed stream differs. A rebuild
therefore reproduces the same *contents*, and its SHA-256 will not match the
published installer. Verify an installer against the hash in this table, or
against its adjacent published `.sha256` sidecar, rather than against a local
rebuild. (The `beta-4` note below claimed byte-for-byte installer
reproducibility without this qualification; that claim was too strong.)

**Fixed for the next release, after these assets were published.**
`packaging/windows/build_windows_installer.py` now flattens every mtime in the
staged tree to a fixed `SOURCE_DATE_EPOCH` before NSIS runs — the same technique
`build_archive.py` already used for the tarballs. Two from-scratch builds now
produce a byte-identical installer, verified. The beta-5 installers above were
built before that change and are **not** re-cut: replacing a published asset
under its own filename is the mistake beta-2 made and beta-3 fixed by dating
filenames. From the next release, installers can be verified by rebuild like the
tarballs can.

The installers are **not code-signed**. Windows shows a SmartScreen prompt on
first run, and the wizard's second page says so before writing anything.

### `beta-4` — 2026-07-25 · superseded by beta-5

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-4>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC29-20260725.tar.gz` | 9,434,164 | `3966d12eeeb73a8f0acd2bb68fca7fda2a683c1865b1d18a58b1dda80f1a251b` |
| `apf2k8-mod-studio-0.1.0-alpha.34-20260725.tar.gz` | 1,108,507 | `feb49eefa5233d4c0459dc8f1783bb1aa3bbe93608c61c34a0191da1585b544d` |
| `2K5-Mod-Studio-1.0-RC29-Setup.exe` | 55,878,130 | `c52464be5a0dc9660d704a7148fd9aad7d7c7c35bfb8d0e64716f6eed4c2fa80` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.34-Setup.exe` | 52,345,481 | `9b920484f348aab416bd15ccaf583382839ce91c03e7464b7bc5caa67a4efdf3` |

The two tarballs are byte-identical to their beta-3 uploads; no editor code
changed. The new assets are Windows wizard installers built by
`packaging/windows/build_windows_installer.py`, each carrying a private CPython
beside the unmodified application tree.

Their reproducibility rests on a different mechanism from the tarballs and is
worth stating separately. The tarballs are deterministic because every input is
in this repository. The installers additionally pull an interpreter and four
wheels from the network, so each of those five artifacts is pinned to an exact
SHA-256 and verified before use; an unpinned wheel appearing, a pinned wheel
failing to appear, or any hash mismatch stops the build. With those pinned,
NSIS output is itself deterministic — both installers were built twice and
compared byte for byte.

> **Correction, recorded 2026-07-27 rather than quietly edited.** That last
> sentence is true of NSIS given one fixed staged tree, but it reads as a claim
> that a from-scratch rebuild reproduces the published installer bytes, and it
> does not: `pip` and extraction stamp fresh mtimes on every runtime file and
> NSIS stores them. See the beta-5 note above for the exact scope. The pinned
> inputs and the reproducible staged *content* are unaffected.

The installers are **not code-signed**. Windows shows a SmartScreen prompt on
first run, and the wizard's second page says so before writing anything.

### `beta-3` — 2026-07-25 · superseded by beta-4

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-3>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC29-20260725.tar.gz` | 9,434,164 | `3966d12eeeb73a8f0acd2bb68fca7fda2a683c1865b1d18a58b1dda80f1a251b` |
| `apf2k8-mod-studio-0.1.0-alpha.34-20260725.tar.gz` | 1,108,507 | `feb49eefa5233d4c0459dc8f1783bb1aa3bbe93608c61c34a0191da1585b544d` |

No editor code changed between beta 2 and beta 3, which is why both products
still identify as `v1.0-RC29` and `0.1.0-alpha.34`. Both archives nevertheless
changed, because both now ship `LICENSE` and `NOTICE.md` — MIT requires its own
text to accompany every copy, and neither archive had contained one. The APF
archive additionally carries the corrected `APF2K8-README.md`. The APF asset
filename now carries a date, matching the 2K5 convention, so one filename can
never again cover more than one set of bytes.

### `beta-2` — 2026-07-25 · SUPERSEDED by beta-3

<https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-2>

| Asset | Bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC29-20260725.tar.gz` | 9,432,505 | `4c293e609ce15df55a2b7dd870ad13eefe419e9db2a88ae8bb4b82e01c2230e4` |
| `apf2k8-mod-studio-0.1.0-alpha.34.tar.gz` | 1,105,799 | `f047682430f4cc5be868b586b875fbf602c62799130cbd5623b128a6219676f1` |

Its 2K5 asset was published once and never changed. Its APF asset was replaced
twice under a single filename — the reason beta 3 dates that filename. The two
superseded APF uploads, recorded so an early download can still be identified:

| Superseded APF upload | Bytes | SHA-256 | Why it was replaced |
| --- | --- | --- | --- |
| first | 981,711 | `51b5d258d242887deba105b2043702554bae1abf50363abd2eb98badbe2e779a` | shipped only the Linux extractor, so a Windows user could not hand the app an ISO |
| second | 1,103,838 | `67a1d777c5f587e28776a75c2ca6ae59d7290a965a04f8f7bf430c0a635e58af` | added `extract-xiso.exe`, but its bundled `APF2K8-README.md` still told Windows users the ISO path would not work and still reported the suite as failing on Windows and macOS |

Every asset above is deterministic: staging from its allowlist with
`packaging/stage_release.py` and rebuilding with `packaging/build_archive.py` at
epoch `2026-07-25T00:00:00Z` reproduces those exact bytes. Each was rebuilt and
compared byte-for-byte rather than asserted, including a rebuild of the two live
beta-2 assets before any of the beta-3 changes were made, to prove the pipeline
matched reality before it was used to change anything.

## RC29 project-backed Audio cue labels — sealed

Audio now lets a modder attach a custom title and multiline note to every
playable standalone cue and indexed streaming range. Titles/notes are
immediately searchable, **Labeled only** isolates discoveries, unsaved drafts
survive row/page/filter changes, and the original catalog label plus stable cue
ID remain visible. Matching and shortlist collection ZIPs carry the custom
title, note, and preserved catalog name in `manifest.json`; WAV playlists use
the custom title without changing canonical cue IDs or payload paths.

Annotations are bounded user metadata, not XISO edits. They save and recover in
checksum/size/count-bound `audio-annotations.json`, may form an annotation-only
`.2k5mod`, support per-cue Clear plus Undo/Revert All, and remain excluded from
Modified/Build state. Untrusted titles render literally, Unicode format
controls and duplicate JSON keys/IDs are refused, and cue IDs are revalidated
against the exact audio catalog when it attaches. Mixed Revert All/Undo and
project import are manifest-atomic: forced disk-full/final-handoff failures
restore memory, files, histories, and the prior manifest, leave no partial
destination, and remain retryable. Rejected facade candidates are removed only
through an exact UUID-root/self-manifest guard.

The source version is **`1.0.0rc30`**. The authoritative cross-title product
suite passes **1372/1372** across 127 files, on Linux, macOS and Windows. RC30
changes exactly one 2K5 file: `tools/nfl_uniform_color_xiso_direct_patch.py`
now resolves the Linux-only `os.copy_file_range` before its copy loop, so the
fallback its docstring promises actually runs off Linux instead of raising
`AttributeError`. No capability, pin or guarantee changed. Independent hostile
review is GO with no unresolved P0/P1 defect.
The exact allowlisted stage contains **146 files**, **13 directories excluding
root**, and **102,748,400 file bytes**. Both stage and clean extraction pass the
retail-free gate before/after the **48-product-module/22-tool-module** runtime
closure, desktop validation, launcher syntax, and zero-bytecode checks. The
160-member deterministic rebuild is byte-identical. The mode-`0444`,
**9,369,401-byte** archive is
[`2K5-Mod-Studio-v1.0-RC29-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC29-20260720.tar.gz)
with authoritative SHA-256
`c1000937cdc47861ce6e1a23c4696c052a0c7bc3cebb1c0279ed9cc1efcdd99d`;
its adjacent mode-`0444` sidecar passes. RC28 and RC27 remain preserved.

- **Shipped:** a runnable retail-free RC29 with project-backed cue discovery, retained drafts, labeled search, metadata-aware collection/playlist export, and transactional project failure handling.
- **Experiment result:** 1142/1142 product tests and 162/162 release-focused tests pass; stage/extraction, deterministic rebuild, seven runtime pins, and independent audit are all green.
- **Blocked on the user:** nothing blocks continued headless product work; identifying unknown cues or proving authored audio audibly in xemu still requires later listening/controller input.
- **Next step:** bring the same durable cue-label/search/export workflow to APF 2K8, then continue bounded audio-authoring and general UX polish without changing RC29's sealed bytes.
- **Deliberately not done:** RC29 includes no retail/game audio, decoded PCM, encoder, source path, rollback bytes, visible desktop session, pointer control, emulator run, or new audible-runtime claim.

## APF Alpha.34 project-backed Audio cue labels — sealed

The source/UI version and release declarations identify Alpha.34 as the current
sealed retail-free package. Every one
of APF's 47,775 playable standalone-AUDO and individual-AUSB cues can own one
bounded custom title and/or multiline note under
`project_metadata_only_stable_logical_cue_id`. **Your cue label & notes** saves
the record, search includes title/note text, and **Labeled only** isolates the
project's discoveries without changing the original catalog identity or stable
cue coordinate.

Annotations persist in checksum/size/count-bound `audio-annotations.json`, and
an annotation-only `.apf2k8mod` is valid. They take part in recovery, Undo,
Clear, Revert All, and project load, but remain outside Modified and Build
state. Collection export metadata carries the custom title, note, and preserved
game/catalog name; playlist display may use the custom title without changing
payload paths. The workflow stores no retail audio, decoded PCM, source path,
preimage, rollback byte, or replacement packet.

- **Shipped:** APF 2K8 Mod Studio `0.1.0-alpha.34`, a runnable retail-free Linux package with project-backed per-cue titles/notes, searchable annotations, **Labeled only**, annotation-only projects, and metadata-aware collection export for all 47,775 playable cues.
- **Experiment result:** the authoritative cross-title suite passes **1156/1156**; the exact 105-file/15-directory stage (3,519,281 file bytes) passes the retail-free gate before and after the 67-module runtime closure; the 120-member deterministic rebuild is byte-identical. The mode-`0444`, 815,213-byte archive is `apf2k8-mod-studio-0.1.0-alpha.34-linux-x86_64.tar.gz` with SHA-256 `beb8b1409b83e052e6c432a9ddc4a79f9f990820c79e0b67dea894dc869393f4`; its adjacent mode-`0444` sidecar verifies.
- **Blocked on the user:** a separate independent hostile review and the real-source Xenia visual/audio runtime proofs remain recommended before wide publication; accurate real-world cue naming still requires later listening.
- **Next step:** continue bounded audio-authoring and general UX polish, and evaluate Backbreaker tooling scaffolding, without changing Alpha.34's sealed bytes.
- **Deliberately not done:** Alpha.34 bundles no retail/game audio, decoded PCM, encoder, source path, rollback bytes, visible desktop session, pointer control, emulator run, or new audible-runtime claim; no independent-audit claim is made for this headless seal.

## APF Alpha.33 selected-sound Audio drag and drop — sealed

The Audio detail pane now accepts one local regular `.xma` or exact PCM16
`.wav` for any of the 47,775 individually editable AUDO/AUSB rows. XMA1 and WAV
drops reuse the established exact-slot and user-encoder button paths; they do
not introduce a second writer. Direct XMA1/Revert, PCM, and pack work fence all
Audio mutation/template controls from submission through exact worker
unregistration. A rapid second drop is ignored, a task-runner refusal is
explained, and folders, links, nonempty-host `file:` URLs, multiple files, and
unsupported extensions never reach mutation.

The focused lifecycle/drop selection passes **17/17**, independent review's
relevant selection passes **68/68**, the complete APF suite passes **504/504**,
and the combined suite passes **1113/1113**. Independent review is GO with no
P0/P1 finding. The exact 104-file/15-directory stage and clean extraction each
contain 3,458,863 file bytes, pass retail-free/runtime/desktop/shell gates, and
contain zero links or bytecode. The 119-member rebuild is byte-identical. The
mode-`0444`, 808,649-byte archive is
[`apf2k8-mod-studio-0.1.0-alpha.33-linux-x86_64.tar.gz`](</media/noah/Storage/for codex 1.0/build/releases/apf2k8-mod-studio-0.1.0-alpha.33-linux-x86_64.tar.gz>)
with authoritative SHA-256
`e071a6b42bbc5270c1cee2517c27c3115de03966977b1b178b92649e18982270`.
Alpha.32 and Alpha.31 re-verify unchanged; temporary verification output was
moved recoverably to Trash.

- **Shipped:** APF Alpha.33 is a runnable retail-free Linux package with selected-sound `.xma`/exact-PCM16 `.wav` drag and drop and submission-to-worker-idle control fencing.
- **Experiment result:** 17/17 focused, 68/68 independent relevant, 504/504 APF, and 1113/1113 combined checks pass; stage/extraction and deterministic packaging are green.
- **Blocked on the user:** audible authored-audio proof still needs a legally obtained XMA1 encoder, independently authored PCM, and a controller-driven Xenia listen A/B; true-53 observation still needs deliberate controller navigation.
- **Next step:** build project-backed 2K5 Audio cue labels/notes so auditioned unknown cues become durable and searchable, then evaluate the same UX for APF.
- **Deliberately not done:** Alpha.33 bundles no encoder or retail audio, accepts no FLAC/MP3, claims no authored-audio runtime causality, changes no true-53 boundary, and used no active desktop or pointer.

## APF Alpha.31 Add-all-matching and safe teardown — sealed

Audio now has **Add all matching (N)** beneath the shortlist controls. It uses
the exact applied search/kind/role/source token or active Soundtrack album,
skips already selected row IDs, and preserves stable catalog order. If the new
set would take the shortlist above 256, the app explains the required and
remaining counts and adds nothing. Success is a session-only metadata change:
no project edit, audio payload, or worker is created. One query/album cache
also prevents selection-only button updates from rescanning all 47,814 rows.

Close and source switching now cancel the exact preview/waveform request and
wait for its registered worker to drain before closing or replacing the private
loaded-game session. Rapid source requests coalesce to the latest selection. A
real blocking build/export retains the established wait-before-close dialog,
even if an Audio reader is cancelled at the same time.

The complete source suite passes **487/487** and the focused Audio GUI suite
passes **32/32**. Independent review is GO with no P0/P1 blocker. The exact
104-file/15-directory stage contains 3,403,930 file bytes, 22 executables, and
71 Python files. Stage and clean extraction pass the retail-free release gate
(`private=false`, `retail=false`, `symlinks=false`, `undeclared=false`) and the
66-module runtime gate with explicit Add-all-matching and cancel/drain receipts.
The 119-member deterministic rebuild is byte-identical. Archive size is
795,740 bytes; authoritative SHA-256 is
`d0e5bd23a56881574a56760709ca87dd76e47bdbe5a431b1f67be57e56c19e5a`.
Alpha.30 re-verifies unchanged. Temporary extraction/rebuild outputs were moved
recoverably to Trash.

- **Shipped:** APF 2K8 Mod Studio `0.1.0-alpha.31`, a runnable retail-free Linux package with one-action filtered Audio shortlist curation and teardown-safe private decoding.
- **Experiment result:** stable-order deduplication, atomic 256 refusal, cache invalidation/reuse, latest-source coalescing, close-after-drain, and protected blocking-operation close all pass; the complete APF suite is 487/487.
- **Blocked on the user:** authored-audio audibility still needs the user's legally obtained XMA1 encoder plus independently authored PCM and a controller-driven Xenia listen A/B; true-53 observation still needs deliberate controller navigation.
- **Next step:** improve the 2K5 Audio workspace, then return to APF filtered replacement-pack ergonomics while user-supplied runtime inputs remain unavailable.
- **Deliberately not done:** no encoder, retail audio, private game source, active desktop, pointer control, emulator run, FLAC/MP3 import, runtime-position claim, or true-53 claim was added to Alpha.31.

## RC28 Audio replacement-pack Preview and explicit Apply — sealed

Audio replacement-pack import now begins with a fully validated, read-only
Preview. The folder or ZIP, public manifest/source binding, current baselines,
declared files, strict WAV shapes, origin authorization, staged bytes, and
shared physical aliases are all checked without changing the project manifest,
replacement tree, Undo history, or source XISO. The frozen public summary shows
logical supplied/change/already-current/restore counts separately from unique
physical changes/restores, reports linked aliases and the resulting Modified
count, and exposes only a bounded set of human-readable change labels.

An unchanged-only pack previews successfully and never offers Apply. A changing
pack must pass an explicit confirmation dialog. Its opaque session-local token
binds the exact member digest and schema to the loaded source, session identity,
and monotonic project/audio mutation revision. The token is hidden from result
representation and does not retain the ZIP path, WAV bytes, private source
hash, or private member hashes. Apply reopens the caller-controlled pack,
privately snapshots the supplied WAVs, reruns every validation, verifies the
token, and only then enters the existing one-action atomic transaction. A
changed valid WAV, source, session, or project state is refused and requires a
new Preview.

The sealed release identifies as `1.0.0rc28`. The complete 2K5 suite passes
**609/609**, the release-focused selection passes **162/162**, and the combined
Audio-pack/Audio-panel selection passes **90/90**. The exact
145-file/13-directory stage contains 102,671,310 file bytes. Stage and clean
extraction pass the retail-free gate before and after the
47-product-module/22-tool-module runtime closure, which emits
`audio_pack_import=validated_preview_token_apply`; desktop and launcher syntax
also pass. Independent review reports GO with no P0/P1 finding. The 159-member
deterministic rebuild is byte-identical. The mode-`0444` 9,835,954-byte archive
is [`2K5-Mod-Studio-v1.0-RC28-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC28-20260720.tar.gz)
with authoritative SHA-256
`8d316c51ebb696be86e6d15850a3bd00b2a02b76a92cabb6489a649045d30ac1`.
RC27 re-verifies unchanged; temporary extraction/rebuild output was moved
recoverably to Trash.

- **Shipped:** fully validated read-only Audio-pack Preview, explicit Apply/Cancel, sanitized logical-versus-physical/restoration/alias summary, and token-bound revalidation before one Undoable write.
- **Experiment result:** 609/609 2K5, 162/162 release-focused, and 90/90 pack/panel checks pass; clean stage/extraction gates, deterministic rebuild, and independent review are all green.
- **Blocked on the user:** nothing blocks continued headless work; authored-audio audibility and cue meaning still require a later controller-driven xemu listen A/B.
- **Next step:** finish APF Alpha32's corrected worker-idle barrier and seal it, then continue the next bounded Audio/UX improvement.
- **Deliberately not done:** no audible-runtime claim, retail payload, visible desktop, pointer control, emulator, external player, or whole-bank writer was added to RC28.

## RC27 default All Playable Audio — sealed

Audio now opens on one **All Playable Audio (54,421)** scope. Its order is
deliberately domain-prefixed rather than globally re-sorted: all **850
standalone AUDO cues** retain their existing order, followed by all **53,571
indexed AUSB ranges** in their existing range order. The mixed inventory reuses
the existing row objects and search haystacks. Complete streaming banks and
opaque raw containers remain visible in their dedicated scopes but never enter
the playable count.

Search, stable paging, combined family filtering, and **Modified** operate
across both playable domains. Existing rows keep their existing actions and
contracts. A current mixed result of 1–256 rows can export as one ordered WAV
collection with truthful retail-derived/user-replacement metadata; the mixed
route refuses raw BIN so a standalone WAV cannot be mislabeled as encoded bank
data. Raw bank/range export remains available from its dedicated scope.

The 1/152/697 **Meaning confidence** groups remain standalone-only and are not
silently applied to half of the mixed result. The public v4 replacement pack is
also unchanged: it remains the frozen canonical **all-850 standalone** template.
RC27 does not claim an all-54,421 replacement template; streaming ranges use
their exact per-row writer or the existing 1–256 selected-shortlist pack.

The complete combined headless suite passes **1090/1090**, the 2K5 slice passes
**603/603**, the release-focused selection passes **122/122**, and the final
Audio/Crib/project lifecycle selection passes **40/40**. Independent review is
GO with no P0/P1 finding. The exact 145-file/13-directory stage contains
102,631,809 file bytes. Stage and clean extraction pass the retail-free gate
(`private=false`, `retail=false`, `symlinks=false`, `undeclared=false`) and the
47-product-module/22-tool-module runtime closure. The 159-member deterministic
rebuild is byte-identical. The mode-`0444` 9,828,168-byte archive is
[`2K5-Mod-Studio-v1.0-RC27-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC27-20260720.tar.gz)
with authoritative SHA-256
`c8f7ef9645e8f636f8eaa0638656ac6abc76789e70e174d0b593b279ff8c1edc`.
RC26 re-verifies unchanged; temporary extraction/rebuild output was moved
recoverably to Trash.

- **Shipped:** RC27 makes one default 54,421-row playable Audio inventory clickable without hiding the dedicated bank/raw views.
- **Experiment result:** canonical order, cross-domain Modified/family/search/paging, standalone-only meaning confidence, reused search strings, and WAV-only mixed export pass the complete release closure.
- **Blocked on the user:** nothing blocks continued headless product work; cue meaning/audibility still needs a later controller-driven xemu listen A/B.
- **Next step:** add a bounded pre-import comparison/preview for replacement packs, then carry the best Audio ergonomics back to APF.
- **Deliberately not done:** no all-54,421 replacement template, whole-bank writer, recovered song title, runtime-audibility claim, retail payload, visible desktop, pointer control, emulator, or external player was added.

## RC26 bounded Audio waveforms and shared worker safety — sealed

Every playable 2K5 sound now has an explicit **Load waveform** action: all 850
standalone AUDO cues and all 53,571 independently addressed AUSB ranges. The
view reads the selected sound's private current PCM16 WAV, including a staged
replacement, without autoplay or project mutation. It retains at most 640
normalized envelope columns and samples no more than 1,024 frames per column;
whole banks and opaque raw containers remain honestly unavailable as one
waveform. The reader opens a regular non-link file read-only, detects changes
during the read, handles full-scale negative PCM correctly, and leaves the WAV
byte-for-byte unchanged.

Waveform and playback state are bound to exact source, selection, and current
audio content. Replace, Revert, batch import, project load, Undo, Revert All,
selection changes, and source changes invalidate stale same-ID media. Audio and
Crib now share one mutually exclusive embedded-worker lane. Direct specialist
mutation routes, sibling panels, navigation, source/project/save/build/launch/
undo/revert, and close are fenced until the owner drains; Audio keeps only its
truthful waveform Cancel route reachable. Save→source/project and recovery
chains run from a post-worker continuation queue only after `_blocking=False`.
Ordinary source/project, recovery mismatch, Undo, and Revert All refresh Crib
last at that same safe boundary.

The complete combined headless suite passes **1088/1088**, the 2K5 slice passes
**601/601**, the release-focused selection passes **107/107**, and the final
lifecycle matrix passes **24/24**. Independent review is GO with no remaining
P0/P1. The exact 145-file/13-directory stage contains 102,617,828 file bytes.
Stage and clean extraction pass the retail-free gate and the 47-product-module/
22-tool-module runtime closure with explicit waveform, same-ID invalidation,
and Audio/Crib mutual-exclusion receipts. The 159-member deterministic rebuild
is byte-identical. The mode-`0444` 9,825,591-byte archive is
[`2K5-Mod-Studio-v1.0-RC26-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC26-20260720.tar.gz)
with authoritative SHA-256
`8000796c7a4f8758c2336640bf63ffc01a537632b13e4bcf372d6bdfbb54bb82`.
RC25 re-verifies unchanged; temporary extraction/rebuild outputs were moved
recoverably to Trash.

The Desktop proof kit now also contains eight new 1920×1080 source-loaded
editor renders—four 2K5 and four APF—covering dashboards, Giants away uniforms,
jerseys, Stadium Studio, and soundtrack/audio browsers. Their manifest verifies
dimensions, hashes, file sizes, and nonblank headless rendering, and the entire
34-file kit passes its refreshed `SHA256SUMS`. No visible desktop or pointer was
used. Spark Hands was unavailable, so the eight filenames honestly retain
`HEADLESS_UNVERIFIED`; the two earlier dashboard captures remain the
Spark-reviewed fallback.

- **Shipped:** 2K5 Mod Studio `v1.0 RC26`, with explicit bounded waveforms for 54,421 playable sounds, same-ID media invalidation, and one safe Audio/Crib worker lane; eight current editor teaser renders are also in the Desktop proof kit.
- **Experiment result:** 1088/1088 combined, 601/601 2K5, 107/107 release-focused, and 24/24 lifecycle tests pass; stage/extraction gates are retail-free, the rebuild is byte-identical, and independent review is GO with no P0/P1.
- **Blocked on the user:** nothing blocks continued headless product work; audibility/meaning of provisional cues still needs a controller-driven xemu listen A/B, and the new teaser candidates need one quick human visual look because Spark was unavailable.
- **Next step:** ship RC27's one default **All Playable Audio (54,421)** search spanning standalone cues and streaming ranges, then carry the best bounded batch ergonomics back to APF.
- **Deliberately not done:** no visible desktop, pointer control, audio device, emulator, external player, retail bytes, recovered song-title claim, or audible-runtime claim was used or added.

## APF Alpha.30 interruptible Audio decode — sealed

Audio **Play** now becomes **Cancel preview** while its private PCM is being
prepared, and **Load waveform** becomes **Cancel waveform** during the same
decode route. Each operation owns its exact model epoch, row, generation, and
thread-safe cancellation event. Explicit Cancel, row/source changes, and
source teardown signal that event. The control reports **Cancelling…** until
the worker exits; cancelled or stale success/failure is silent, cannot start a
player, and leaves the current row retryable. A rejected blocking-task
admission also releases ownership immediately instead of getting stuck.

The callback reaches facade, session, private asset I/O, standalone AUDO,
AUSB substreams, and both staged exact-slot decoders. In this optional path,
FFmpeg/ffprobe are new session leaders and cancellation/timeout performs TERM,
bounded drain, KILL escalation, and complete process-group checking. A
detached-stdio TERM-resistant helper was killed in the focused test. Original
previews stage in private temporary folders; modified previews use a hidden
sibling WAV and no-replace link. Cancellation publishes no partial WAV or
receipt, while an already verified cached preview remains intact. Legacy
no-callback command-line behavior is unchanged.

The complete source suite passes **480/480**. Focused suites pass **29/29**
Audio GUI, **9/9** waveform, and **7/7** decoder cancellation. The exact
104-file/15-directory stage contains 3,388,006 file bytes, 22 executables, and
71 Python files. Stage and clean extraction pass the retail-free release gate
(`private=false`, `retail=false`, `symlinks=false`, `undeclared=false`) and the
66-module runtime gate with explicit preview/waveform process-cancellation
receipts. The 119-member archive rebuild is byte-identical. Archive size is
792,312 bytes; authoritative SHA-256 is
`6f0ca573707ba28d4fba296642e80a7337295d899605f9f3a93c90663819a999`.
Alpha.29 re-verifies unchanged.

- **Shipped:** APF 2K8 Mod Studio `0.1.0-alpha.30`, a runnable retail-free Linux package with truly cancellable preview and waveform decoding across original/staged AUDO and AUSB.
- **Experiment result:** current/stale cancellation, busy-lane rejection, partial-file cleanup, cached-preview preservation, TERM-resistant timeout, and detached-helper process-group cleanup all pass; the complete APF suite is 480/480.
- **Blocked on the user:** authored-audio audibility still needs the user's legally obtained XMA1 encoder plus independently authored PCM and a controller-driven Xenia listen A/B; true-53 observation still needs deliberate controller navigation.
- **Next step:** ship one-action **Add all matching** shortlist curation, then perform the bounded encoded Track/cue build-and-listen A/B when user-supplied inputs are available.
- **Deliberately not done:** no encoder, retail audio, private game source, active desktop, pointer control, emulator run, FLAC/MP3 import, or cancellation inside one monolithic archive-decompression call was added to Alpha.30.

## APF Alpha.29 owned Audio lifecycle — sealed

Audio page-wide actions can no longer consume the old 100-row table while a
new search/filter is waiting on its 180 ms debounce. The applied token covers
model epoch, search, kind, role, source/bank, and page offset. Add-this-page,
pagination, matching/template export, and filtered decoded-row export are both
disabled and method-guarded until the matching table publishes. Exact
selected-row Play/Export/Replace/Revert/Add remains usable. Fast type/erase on
page 2 restores offset 100 and advances normally to page 3.

Shortlist **Clear** now becomes a one-level **Undo** for up to 256 mixed
AUDO/AUSB rows in exact insertion order. The snapshot is metadata-only,
session-only, project-silent, and discarded on the next real shortlist
mutation or successful model/game change. Preview preparation now owns an
exact `(model epoch, row ID, request generation)` token: stale success and
failure are silent, while a current failure clears **Preparing…**, restores
**Play**, and remains retryable. A separate adversarial experiment confirmed
that failed/cancelled source switches already preserve the old Audio model,
page, selection, shortlist, waveform, and running player, so that path was not
rewritten.

The complete source suite passes **466/466**, the focused Audio GUI suite passes
**26/26**, and two independent reviews return GO with no P0/P1/P2 issue in the
final fences. The 104-file stage and clean extraction each contain 3,358,266
file bytes and pass the retail-free release gate plus isolated 66-module runtime
gate with all three Alpha.29 lifecycle receipts. The 119-member archive rebuild
is byte-identical. Archive size is 785,069 bytes; authoritative SHA-256 is
`76c7e88786ffccb3a65a26acaa0698c3840b2be6fa46a6c663cfd22a9b76ea80`.
Alpha.28 re-verifies unchanged.

- **Shipped:** APF 2K8 Mod Studio `0.1.0-alpha.29`, a runnable retail-free Linux package with safe debounced Audio actions, ordered Clear/Undo, and request-owned previews.
- **Experiment result:** wrong-page shortlist/export, stale preview success/failure, stuck-Preparing, and page-offset failures were reproduced, fixed, and independently closed; failed/cancelled source replacement was already transactional and required no rewrite.
- **Blocked on the user:** authored-audio audibility still needs the user's legally obtained XMA1 encoder plus independently authored PCM and a controller-driven Xenia listen A/B; true-53 observation still needs deliberate controller navigation.
- **Next step:** use the packaged PCM16 workflow for one bounded encoded Track/cue build and listen A/B, then carry the same owned-query/preview audit into any remaining large media browsers.
- **Deliberately not done:** no encoder, retail audio, private game source, active desktop, pointer control, emulator run, FLAC/MP3 import, or in-flight source-index cancellation was added to Alpha.29.

## RC25 recoverable Audio curation — sealed

Clearing an Audio shortlist no longer destroys up to 256 hand-picked sounds.
The same compact toolbar control becomes **Undo** and restores the exact prior
order across standalone cues and streaming ranges. The one-level snapshot is
session-only, emits no edit/project signal, triggers no replacement task, and
is consumed only by a real shortlist mutation or successful source change.
Clearing inside Review returns to the browser; Undo restores the list without
unexpectedly reopening Review. The visible label stays exactly **Undo** because
headless width sweeps proved longer forms widen the 930-pixel toolbar contract;
the count and behavior remain in its accessible name, tooltip, and status copy.

Independent audit also proved and fixed a P1 source-failure lifecycle bug.
Source loading is transactional, so a refused new XISO leaves the old facade
source valid. RC24 invalidated the Audio page token before the worker and only
rebound it on success, leaving page-wide actions disabled forever after a
failure. RC25 advances the source token only after a successful commit and adds
an explicit task-error recovery: the old page, search, selection, shortlist,
Clear-undo snapshot, and actions return while preview remains invalidated. A
pending search is applied against the old source; a first-load refusal returns
to the honest empty **Load your NFL 2K5 XISO** state. Recovery runs while the
whole Audio panel is still disabled, before normal task cleanup re-enables it.

Final independent review returned **GO** with no P0–P2 finding and also proved
that canceling the unsaved-workspace dialog starts no worker and never
invalidates Audio. The complete headless/offscreen product suite passes
**1034/1034** and the focused Audio/UI/source-bound/packaging selection passes
**118/118**. The fresh stage and extraction each pass release → runtime →
desktop/Bash → release, contain 144 files and 102,560,651 file bytes, report
`audio_shortlist_clear=one_level_ordered_restore`,
`audio_source_failure=transactional_old_catalog_restore`,
`private_inventory=false`, and `retail=false`, and reproduce byte-for-byte. The
sealed 9,332,131-byte archive is
[`2K5-Mod-Studio-v1.0-RC25-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC25-20260720.tar.gz)
with SHA-256
`8ad21fb0a92be85a8402fcbe85d44b27b8b9ea13468b54cda2466ce756bd4e4a`;
its adjacent mode-`0444` sidecar is the seal marker. RC24 remains unchanged.

## RC24 applied-query Audio actions — sealed

Every displayed Audio catalog page now carries the exact source epoch, search
text, scope, family, edit status, and meaning-confidence token that produced it.
While the 220 ms search debounce is pending, **Add this page**, **Add all
matching**, **Export matching audio**, Previous, and Next are disabled and also
guarded at their method boundaries. They cannot silently use the old page,
count, ordering, or offset. The existing selected row remains visible and its
Play, Export, Replace, Revert, and Add-selected actions remain usable because
those operations target that exact row rather than the pending query.

The original five-race matrix passes for stale page-add, mismatched export
count/query, all-matching requery/warnings, and pagination/selection drift. A
sixth regression covers typing and erasing back to the already applied query:
the timer is canceled and normal labels/actions return immediately rather than
remaining dimmed for another interval. Filter/scope shortcuts and source
transitions cancel older timers; shortlist-review pagination remains
independent. Independent review reran 55 focused tests plus nine direct edge
cases and returned **GO** with no P0–P2 finding.

The complete headless/offscreen product suite passes **1028/1028** and the
focused Audio/UI/source-bound/packaging selection passes **112/112**. The fresh
stage and extraction each pass release → runtime → desktop/Bash → release,
contain 144 files and 102,554,002 file bytes, report
`audio_query_lifecycle=applied_token_debounce_guarded`,
`private_inventory=false`, and `retail=false`, and reproduce the archive
byte-for-byte. The sealed 9,330,783-byte archive is
[`2K5-Mod-Studio-v1.0-RC24-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC24-20260720.tar.gz)
with SHA-256
`67296073fcd22d93fc18bebb031a5de27247d703dd2cfa0c84b7813f6276da85`;
its adjacent mode-`0444` sidecar is the seal marker. RC23 remains unchanged.

## RC23 selection/source-bound Audio preview — sealed

Audio preview requests now carry a monotonically increasing epoch plus the
exact selected asset ID. An asynchronous preparation result or error can act
only while that request, row, and source remain current. This closes the proved
A → B → A race and the same-ID-after-source-switch race. Refreshing the same row
preserves playback; selecting another effective row or starting a source switch
invalidates pending work, stops Mod Studio's controlled player, and restores
**Play**.

One-click switching queues the newly prepared sound while the old process
stops. Both Qt terminal paths are covered: normal kill/crash error-then-finished,
and FailedToStart returning to NotRunning without a finished signal. Preview
uses only `ffplay`, `paplay`, or `aplay`; the unowned desktop-handler fallback
was removed because Mod Studio could not stop it. Missing-player, preparation,
and process-start failures leave clean state and give an actionable message.
The main window invalidates preview before a source-load worker begins and
disables the embedded Audio panel throughout global blocking work.

Independent review initially found two P1 lifecycle holes: obsolete preparation
errors could still raise a modal, and stale FailedToStart could strand a newer
prepared request. Both were fixed, their regressions were added, the obsolete
pre-fix stage was deleted, and final review returned **GO** with no P0–P2
finding. The complete headless/offscreen product suite passes **1022/1022** and
the focused Audio/UI/source-bound/packaging selection passes **106/106**.

The fresh stage and extraction each pass release → runtime → desktop/Bash →
release, contain 144 files and 102,546,349 file bytes, report
`audio_preview_lifecycle=selection_source_epoch_owned_process`,
`private_inventory=false`, and `retail=false`, and reproduce the archive
byte-for-byte. The sealed 9,329,352-byte archive is
[`2K5-Mod-Studio-v1.0-RC23-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC23-20260720.tar.gz)
with SHA-256
`aa23ad080da99d5c795613cca11e140b8626abddcfa14c3f8db558b913b3f9f3`;
its adjacent mode-`0444` sidecar is the seal marker. RC22 remains unchanged.

## RC22 responsive Audio toolbars — sealed

The five Audio search/filter controls and seven shortlist controls now use two
deliberate grid rows instead of two oversized single-row toolbars. Search/scope
remain grouped; family/status/meaning sit below them; add actions occupy the
first shortlist row; review/count/clear/export occupy the second. Every control
remains directly visible, with no overflow menu and no changed signal route.

The Audio panel's normal minimum-width hint dropped from 1,442 to 833 pixels. A
permanent offscreen geometry regression applies the conservative simultaneous
longest state—Add this page (200), Add all matching (256), Review selected
(256), Selected 256 / 256, and Export selected WAVs (256)—and proves the panel
fits at 930 pixels. Both inner grids are 882 pixels; all 12 controls remain
inside the panel, at or above their own minimum usable widths, and have zero
pairwise overlap. That fits the main window's 932-pixel workspace at its
supported 1,180-pixel minimum width.

The complete headless/offscreen product suite passes **1016/1016** and the
focused Audio UI/backend/streaming/facade/packaging selection passes **100/100**.
Independent review returned **GO** with no P0–P2 finding and independently
reproduced the 930/882-pixel geometry. The stage and a fresh extraction each
pass release → runtime → desktop/Bash → release, contain 144 files and
102,537,046 file bytes, report `audio_toolbar_layout=two_row_930`,
`private_inventory=false`, and `retail=false`, and reproduce the archive
byte-for-byte. The sealed 9,326,590-byte archive is
[`2K5-Mod-Studio-v1.0-RC22-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC22-20260720.tar.gz)
with SHA-256
`e7f3018ccd5fb3b8a446204ceb22e5f491c6813cee72c0d11315e2e2eba97548`;
its adjacent mode-`0444` sidecar is the seal marker. RC21 remains unchanged.

## RC21 scrollable Audio inspector — sealed

The selected-sound inspector now scrolls its complete title, status, technical
metadata, ownership/alias warnings, shared-slot owner list, action/WAV contract,
and all-850 pack path. The WAV drop target and Play, Export, Replace, and Revert
actions remain pinned below that scroll region, so a long owner list cannot push
the controls out of reach. Exact IDs and paths remain unabridged and selectable
by mouse or keyboard; changing rows returns the inspector to the top.

The implementation reduces the detail card's bounded minimum width from 360 to
320 pixels and ignores long-token width hints without inserting soft breaks into
copied identifiers. The dedicated offscreen stress test uses 31 long logical
owners, proves vertical overflow, confirms the action tray is outside the scroll
content, retains the final owner ID exactly, and proves selection changes reset
the scroll position without touching replacement state. This checkpoint does
not claim that the separate 1,394-pixel single-row shortlist toolbar is reflowed;
that is the next responsive-layout task.

The complete headless/offscreen product suite passes **1015/1015** and the
focused Audio UI/backend/streaming/facade/packaging selection passes **99/99**.
Independent review returned **GO** with no P0–P2 finding. The stage and a fresh
extraction each pass release → runtime → desktop/Bash → release, contain 144
files and 102,534,262 file bytes, report
`audio_detail_layout=scrollable_pinned_actions`, `private_inventory=false`, and
`retail=false`, and reproduce the archive byte-for-byte. The sealed
9,325,798-byte archive is
[`2K5-Mod-Studio-v1.0-RC21-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC21-20260720.tar.gz)
with SHA-256
`7c9acd6d99042144514a61ebaa7aad9bcf17f1ac9aed6f58bef7c9a9565ac692`;
its adjacent mode-`0444` sidecar is the seal marker. RC20 remains unchanged.

## RC20 bounded Audio “Add all matching” — sealed

Standalone Audio now has a separate **Add all matching** action beside **Add
this page**. It converts the complete current search/family/edit-status/meaning-
confidence result into the review shortlist in canonical catalog order, up to
the explicit 256-row shortlist ceiling. This closes the practical 152-row
workflow: choose **Reviewed labels (152)**, activate **Add all matching**, then
switch to **Selected shortlist** without collecting multiple browser pages by
hand.

The action is intentionally limited to standalone sounds and indexed streaming
ranges. It revalidates the current result count, ordering, types, unique IDs,
visible slice, and every active filter before changing anything. Existing
shortlist rows are retained once, new rows append canonically, and any combined
result above 256 is refused atomically with a modder-facing explanation. It is
session-only selection state: it changes neither the project nor replacement
files.

The complete headless/offscreen product suite passes **1014/1014** and the
focused Audio UI/backend/streaming/facade/packaging selection passes **98/98**.
Independent review returned **GO** with no P0–P2 finding. The stage and a fresh
extraction each pass release → runtime → desktop/Bash → release, contain 144
files and 102,528,972 file bytes, report
`audio_add_all_matching=bounded_256`, `private_inventory=false`, and
`retail=false`, and reproduce the archive byte-for-byte. The sealed
9,324,562-byte archive is
[`2K5-Mod-Studio-v1.0-RC20-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC20-20260720.tar.gz)
with SHA-256
`98402cb4e638e8beca5f2f5a0cf41cc452de712a6897c030b3b76d88bba7f38e`;
its adjacent mode-`0444` sidecar is the seal marker. RC19 remains unchanged.

## RC19 Audio meaning-confidence filter — sealed

Standalone Audio now has a separate **Meaning confidence** filter with the exact
public v4 cue-map groups: **Menu Back route (1)**, **Reviewed labels (152)**,
and **Provisional labels (697)**. The existing edit-status filter continues to
answer whether a slot is Modified/Editable; the new filter answers how much is
known about the human label and runtime caller. This prevents a provisional
name from being mistaken for an approximate or unsafe physical writer.

CSV generation, catalog-host browsing, product-facade browsing, pagination, and
matching collection export share one public `standalone_runtime_meaning_status`
function. The filter composes with search, family, and edit status, appears in
matching bundle names, resets/disables outside standalone Audio, and temporarily
disables without losing its selection during shortlist review. Invalid,
unhashable, or cross-scope values fail before any export is published. Public
v4 generation is byte-unchanged; frozen v1/v2/v3 goldens and v4 deterministic/
import tests remain green.

The complete headless/offscreen product suite passes **1009/1009** and the
focused Audio UI/backend/streaming/facade/packaging selection passes **93/93**.
Independent review returned **GO** with no P0–P2 finding. The stage and a fresh
extraction each pass release → runtime → desktop/Bash → release, contain 144
files and 102,514,393 file bytes, report
`audio_meaning_confidence=1_152_697`, `private_inventory=false`, and
`retail=false`, and reproduce the archive byte-for-byte. The sealed
9,322,097-byte archive is
[`2K5-Mod-Studio-v1.0-RC19-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC19-20260720.tar.gz)
with SHA-256
`bb1fac8a0c3267045d3d0556c0c92124dfe90990e165ec358d4fdd5d3ac9711b`;
its adjacent mode-`0444` sidecar is the seal marker. RC18 remains unchanged.

## RC18 in-app Audio pack paths — sealed

Every standalone Audio detail view now shows the exact public
`replacements/NNN__selected-audio.wav` destination used by the mapped v4
all-850 authoring pack. **Copy pack path** copies it on explicit activation and
has the keyboard shortcut **Ctrl+Shift+C**. Browsing, selecting, filtering, and
paging never touch the clipboard. Complete streaming banks, indexed AUSB ranges,
and raw universal containers clear, hide, and disable this standalone-only card.

The path is derived from the same canonical catalog order used by v3/v4 export,
through one backend helper shared by the standalone host and product facade. The
UI receives only the generic relative path—not a physical selector, offset,
source fingerprint, retail payload, or private ownership record. V1/v2 ZIP
goldens and the deterministic v3 ZIP remain pinned; v4 remains additive. The
first clean-stage attempt usefully failed because the new runtime assertion was
placed in the v2 synthetic probe; that assertion was moved to the complete
v3/v4 probe, the failed temp stage was removed, and nothing was released from
the failed attempt.

The complete headless/offscreen product suite passes **1006/1006** and the
focused Audio UI/backend/streaming/facade/packaging selection passes **90/90**.
Independent review returned **GO** with no P0–P2 finding. The corrected stage
and a fresh extraction each pass release → runtime → desktop/Bash → release,
contain 144 files and 102,506,230 file bytes, report
`audio_pack_path_lookup=canonical_850`, `private_inventory=false`, and
`retail=false`, and reproduce the archive byte-for-byte. The sealed
9,320,231-byte archive is
[`2K5-Mod-Studio-v1.0-RC18-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC18-20260720.tar.gz)
with SHA-256
`af79c83aeff1f723088edc59af6ad1708dc18fcd65bb4ade7eb5f53234fea05d`;
its adjacent mode-`0444` sidecar is the seal marker. RC17 remains unchanged.

## RC17 human-friendly 850-sound cue map — sealed

The default **All standalone sounds (850)** workflow now exports a retail-free
v4 folder or deterministic ZIP with `AUDIO-CUE-MAP.csv`. The 850 canonical rows
connect each generic `replacements/NNN__selected-audio.wav` destination to its
public Audio-browser ID, display name, family, duration, exact PCM16 channel/
rate/frame contract, product route, legacy membership, alias status, and honest
runtime-meaning status. The map has exactly one Menu Back row, 152 reviewed-label
rows, and 697 provisional-label rows. Modders can filter it for discovery and
copy it outside the pack for personal notes; the in-pack reference is immutable.

The new v4 route is additive. Direct complete exports without the authoring map
still produce the byte-pinned RC16 v3 ZIP, and frozen v1/v2/v3 packs remain
import-compatible. V4 import regenerates and verifies the exact UTF-8/LF,
spreadsheet-formula-safe CSV, manifest binding, schema, SHA-256, canonical order,
and all public values before any WAV can change the project. A missing, changed,
reordered, oversized, or extra map fails before mutation. The template contains
no retail WAV, decoded PCM, private fingerprint, physical game offset, original,
or rollback byte; true WAV changes still enter as one atomic Undo action.

The complete headless/offscreen product suite passes **1005/1005** and the
focused audio/facade/GUI/packaging selection passes **83/83**. Independent
review returned **GO** with no P0–P2 finding. The stage and a fresh extraction
each pass release → runtime → desktop/Bash → release, contain 144 files and
102,498,172 file bytes, report
`audio_replacement_pack_v4=all_standalone_850_mapped`,
`private_inventory=false`, and `retail=false`, and reproduce the archive
byte-for-byte. The sealed 9,318,011-byte archive is
[`2K5-Mod-Studio-v1.0-RC17-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC17-20260720.tar.gz)
with SHA-256
`a616e9174bcfbdf19caa0e868c1bb25d7ad596d47e49f375e08191ecaff33606`;
its adjacent mode-`0444` sidecar is the seal marker. RC16 remains unchanged.

## RC16 complete 850-sound authoring pack — sealed

**All standalone sounds (850)** is now the default Audio batch-authoring
workflow. One click exports a retail-free v3 folder or deterministic ZIP for
Menu Back plus all 849 fixed-AUDO physical slots. Modders add only the authored
WAVs they want at the declared paths, then import every true change as one Undo
action. The v3 route requires the exact canonical 850-row order, unique logical
IDs and underlying physical selectors, one Menu Back row, exact PCM16 contracts,
the whole-XISO SHA-256 binding, and current-edit baselines. The public hand-off
contains no original WAVs, decoded game audio, private PCM fingerprint
inventories, physical offsets, rollback bytes, or other retail payload.

Legacy compatibility is unchanged: v1 remains the exact frozen ordered 153-cue
pack, while v2 remains an ordered 1–256-sound selection that may mix standalone
sounds with exact AUSB ranges. RC16 restores their RC15 downstream call shapes
as well as their file bytes. Complete streaming banks remain excluded. The 697
provisionally named standalone rows still warn that physical ownership is exact
while runtime meaning/audibility may be unknown. No visible GUI or emulator was
launched for RC16.

The complete headless/offscreen product suite passes **1001/1001** and the
focused audio/facade/GUI/packaging selection passes **79/79**. Independent
post-fix review passed 7/7 and returned **GO** with no P0–P2 finding. The stage
and a fresh extraction each pass release → runtime → desktop/Bash → release,
contain 144 files and 102,477,638 file bytes, report
`audio_replacement_pack_v3=all_standalone_850`, `private_inventory=false`, and
`retail=false`, and reproduce the archive byte-for-byte. The sealed
9,313,581-byte archive is
[`2K5-Mod-Studio-v1.0-RC16-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC16-20260720.tar.gz)
with SHA-256
`ee28afd8491d8586763e2883c289ad77d1541551ef1affce34bf16112c8bf092`;
its adjacent mode-`0444` sidecar is the seal marker. RC15 remains unchanged.

## RC15 complete standalone audio editing — sealed

All **850 standalone AUDO sounds** are now Editable: Menu Back keeps its
separate fixed-target route, and the other 849 resolve by stable outer/chunk ID
to exact, distinct, non-overlapping physical allocations. The former 697
alias-related rows now show a prominent warning that their physical target is
exact while semantic cue identity/runtime ownership may be unknown. They no
longer hide Replace merely because two physical rows share a provisional name
or decoded content.

Legacy v1 batch packs remain frozen at the original 153 rows and ordering.
The Audio UI labels that route **Legacy 153-cue pack**; v2 **Selected shortlist
(1–256)** packs can include any newly unlocked standalone slot alongside exact
AUSB soundtrack, commentary, crowd, stadium, and presentation ranges. Complete
raw banks remain Export-only. Work and verification are terminal/offscreen only;
no visible GUI or emulator has been launched for RC15.

The complete product suite passes **993/993** and the final integrated audio,
session, provider, and packaging selection passes **130/130**. The clean stage
and a fresh extraction each pass release → runtime → desktop/Bash → release,
contain 144 files and 102,456,230 file bytes, and report
`audio_editable=850`, `audio_export_only=0`, `private_inventory=false`, and
`retail=false`. Deterministic re-archiving is byte-identical. The sealed
9,310,240-byte archive is
[`2K5-Mod-Studio-v1.0-RC15-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC15-20260720.tar.gz)
with SHA-256
`e50e27bae01cd5800109e225bbea3bf71a6ade054f65f17235e33c09b7d3fe07`;
its adjacent mode-`0444` sidecar is the seal marker. Independent final review
returned **GO**. RC14 remains unchanged.

## RC14 roster workspace navigation — shipped

Current and historical name/number editing now lives under **Rosters &
Players → Players & Numbers**, beside **Portraits & Faces**. **Text & Team
Identity** now exposes only the universal fixed-allocation text browser. The
two scoped panels share the same session/project ledger but construct and
reload only the models they display, avoiding a duplicate 23,346-string and
6,522-roster-row UI pass. Source/project reload, Undo, Revert All, autosave,
status copy, and visible-page Ctrl+F routing remain connected. The focused
headless selection passes 44/44, the complete desktop-tool suite passes
992/992, and independent review returned GO. The 144-file clean stage and an
independent extraction each pass release → runtime → desktop/Bash → release,
contain 102,448,423 file bytes, and reproduce the archive byte-for-byte. The
sealed 9,788,063-byte archive is
[`2K5-Mod-Studio-v1.0-RC14-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC14-20260720.tar.gz)
with SHA-256
`bac81312efd8a2e5e42190c281e97493db5ed8959b0b2848d5e7c7e94604eb2e`;
its adjacent mode-`0444` sidecar is the seal marker. RC13 remains unchanged.

## Emergency storage cleanup — shipped

The Storage filesystem had reached effectively zero free space. A bounded,
headless cleanup removed 96 reproducible test/build payloads totaling
297,265,838,080 bytes (276.85 GiB) from the project's `build` and temporary
work roots. Immediate free space was 274 GiB; after delayed block reclamation
settled, it reached 281 GiB with filesystem use at 84%. Original game
dumps, canonical extracted sources, source code, releases, project/edit data,
manifests, logs, screenshots, and unique evidence were protected. The exact
scope and recovery note are recorded in
[`docs/product/STORAGE_CLEANUP_2026-07-19.md`](docs/product/STORAGE_CLEANUP_2026-07-19.md).
No GUI or emulator was launched and the user's desktop was not touched.
Both editors now check the selected output filesystem before build staging.
They require one complete game output plus a 512 MiB margin and report the
available, required, and upward-rounded shortfall without creating a partial
output. The focused build-safety suite passes 32/32 and the direct unit-boundary
matrix passes 16/16.

## Headless operation — active

The managed Codex remote-control service is running as `noah-desktop`. A
read-only process audit found 42 stale Mod Studio GUI test sessions left from
July 18–19 (12 2K5 and 30 APF), including broken-X11 error dialogs and five
still-running APF Python windows. Their exact process groups were terminated
so they can no longer take focus or the mouse. No project, source, release, or
game file was deleted; the test apps can be relaunched normally if needed.
Current product work is terminal-only. No new GUI or emulator process will be
launched without the designated Spark desktop operator.

## RC13 collection parity and keyboard search — shipped

RC13 fixes a product-path mismatch exposed only after RC11 made fixed AUSB
ranges Editable: collection and shortlist export already ask the session for a
Modified range's staged WAV, but the older bundle row still rejected every
streaming `user_replacement`. The bounded fix admits user-replacement content
only for an Editable streaming range exported as WAV; complete banks and raw
range BIN remain source-derived. Focused tests cover Modified matching and
ordered shortlist ZIPs without changing project, Undo, recovery, or Build.

The same checkpoint fixes global **Ctrl+F** routing for visible search fields in
Text & Team Identity, The Crib, Playbooks, and other workspaces.

The complete 2K5/shared regression passes **533/533** and the focused feature
selection passes **80/80**. Independent review returned **GO** after proving
exact staged-WAV export, source-origin labeling, raw/bank refusal, missing-file
atomic failure, and hidden-search exclusion. The 144-file stage and independent
extraction each pass release → runtime → desktop/Bash → release and reproduce
byte-for-byte. The runtime receipt includes
`audio_bundle_modified_range=user_wav`, `private_inventory=false`, and
`retail=false`. The sealed 9,787,042-byte archive is
[`2K5-Mod-Studio-v1.0-RC13-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC13-20260720.tar.gz)
with SHA-256
`adc08a47aee41a9789369a42b57cd63f560502e447e37663ba50fdaa817331e5`;
its adjacent mode-`0444` sidecar is the seal marker. RC12 remains unchanged.

## RC12 selected Audio Shortlist replacement packs — shipped

RC11 already makes every one of the 53,571 logical fixed AUSB ranges
individually Editable, but its batch pack covered only 153 standalone cues.
RC12 closes that product mismatch without changing writer semantics:
**Selected shortlist (1–256)** exports a metadata-only v2 folder/ZIP for an
ordered mix of Editable standalone and streaming-range rows, while **All
standalone cues (153)** and old v1 imports remain compatible.

The v2 public contract is logical-only: stable sound IDs, exact PCM16 shape,
source binding, replacement baselines, and disclosed logical aliases. Physical
slot IDs, offsets, bank paths, source fingerprints, original audio, and rollback
bytes remain private. Import routes through the existing authorized atomic batch
transaction, so every WAV validates before one Undo action; conflicting shared
aliases or any bad row stage nothing. The broader listening shortlist may still
contain playable Export-only standalone rows; the replacement-pack control now
counts those rows, disables export, and explains exactly how to remove them
without changing ordinary WAV-collection export.

The final headless/offscreen suite passes **973/973**, the focused RC12 selection
passes **75/75**, and an independent adversarial audit returned **GO**. The
144-file stage and a fresh extraction each pass release → runtime → desktop/Bash
→ release from `/`, reproduce the archive byte-for-byte, and report 46 product
plus 22 tool modules, `private_inventory=false`, `retail=false`, and
`audio_replacement_pack_v2=selected_mixed`. The sealed 9,785,999-byte archive is
[`2K5-Mod-Studio-v1.0-RC12-20260720.tar.gz`](/home/noah/2K5-Mod-Studio-v1.0-RC12-20260720.tar.gz)
with SHA-256
`064b54dd437da50cb0829588204b7cbc22f333f81fd2076e05b7227ca7248dba`;
its adjacent mode-`0444` sidecar is the seal marker. RC11 remains unchanged.

## RC11 complete fixed-range streaming audio — shipped

All **53,571 logical AUSB ranges** are now Editable through **53,570 exact
physical fixed slots**. Replace/Revert/Undo/Revert-All, Modified playback and
WAV export, retail-free project save/load, and unified Build/Verify all share
one physical edit state for aliases. The one shared slot discloses both owners;
four seam ranges compile to two spans. Complete raw AUSB banks remain
Export-only because RC11 does not claim a general bank repacker.

Automatic first-use preparation builds the two private source-origin indexes
with progress while keeping the source read-only. The final immutable authored
WAV bytes must pass both source-origin gates before they can be staged, saved,
loaded, built, or independently verified. Those private indexes, source audio,
physical identifiers, offsets, originals, and rollback bytes cannot enter a
shareable `.2k5mod` or release package.

One real-source headless product flow completed Replace, Modified playback and
export, a two-member replacement-only project, fresh source/project reload,
Build, and independent Verify for one authored mono range. The build retained
the 6,300,499,968-byte image size and changed 2,568 bytes inside one authorized
2,664-byte span. The complete source stat and SHA-256 were identical before and
after. The generated XISO and all temporary authoring artifacts were removed,
leaving 269 GiB free. The public-safe receipt is
[`reports/product/nfl2k5_streaming_ausb_product_flow_20260720.json`](reports/product/nfl2k5_streaming_ausb_product_flow_20260720.json).
No GUI or emulator ran, so this proves the offline product flow—not in-game
audibility, semantic cue naming, loop behavior, or mixer ownership.

The later RC11 result supersedes the interim Post-RC9 paragraphs below where
they say public streaming Replace was locked or session/project wiring was
still in progress. Those paragraphs are retained as chronological checkpoints,
not current product limits.

## RC9 Audio batch authoring — shipped

The RC9 Audio workspace has **Export replacement template** and
**Import replacement pack** for all 153 supported standalone cues: 152 unique
fixed-AUDO slots plus Menu Back. A folder or ZIP template contains only cue IDs,
filenames, exact PCM16 contracts, and an empty `replacements/` directory—zero
retail WAVs. Modders add only authored WAVs; import validates the complete pack
before staging all real changes as one Undo action. Mixed imports report both
changed and already-current cues. Streaming soundtrack, commentary, stadium,
and presentation banks/ranges remain truthfully play/export-only pending a
reversible bank-repack contract. The final eight-module dependent gate passes
**99/99**; an independent review also passes **93/93** relevant tests plus
**16/16** standalone-audio tests. The sealed
RC9 136-file stage and independent extraction pass release → runtime closure →
release with **61 registry capabilities**, all **53,571** streaming ranges
still present, and zero retail, private-inventory, symlink, hardlink, or
undeclared payload findings. RC8 remains unchanged.

### RC9 adversarial closure

The three originally identified batch-audio publication/validation races are
closed without partial project mutation. Folder templates now stage and publish under
one pinned destination-parent descriptor using Linux
`renameat2(RENAME_NOREPLACE)`; a destination created at the final syscall is
preserved and publication fails. One shared descriptor reader now performs a
maximum-plus-one bounded read, rejects symbolic and hard links, and compares
regular-file identity, size, timestamps, and link count before/open/after; the
catalog WAV validator, its source-origin reread, pack working baselines,
manifest/guide reads, and batch-session validation rereads all use it. A
post-fix review then reproduced one remaining A→C mutation inside Undo snapshot
capture. Batch import now captures the exact before-snapshot first, validates
that same snapshot plus the live ledger/content against the earlier baseline,
and only then commits while retaining that snapshot as Undo state. The exact
interposition fails before edits or Undo change, and the earlier
post-validation mutation regression still passes. All four focused
race/bounds regressions pass, and the current eight-module dependent gate
passes **99/99** headlessly with
Qt offscreen and bytecode disabled. A fresh **136-file**, **13-directory**
allowlist stage passed release → runtime → desktop/launcher syntax → release;
runtime closure loaded 38 product and 22 tool modules, retained all 53,571
streaming ranges, and reported zero retail, private-inventory, symlink, or
undeclared payload findings. Additional injected second-item failures during
validation, commit, and Undo preserve the complete session tree, leave no
hidden transaction WAVs, and retain a retryable Undo action. This closure is
packaged in RC9; sealed RC8 remains untouched.

## Post-RC9 AUSB fixed-slot backend — shipped source slice

The isolated streaming-audio backend now canonicalizes physical AUSB ranges,
maps every semantic owner to that canonical slot, plans exact one- or two-pack
spans, accepts only canonical PCM16LE WAVs with the target's exact channel and
frame shape, and performs bounded Xbox IMA encode/verify with deterministic
progress, cancellation, and empty-output rollback. A real-source headless
census mapped **53,571 semantic ranges** to **53,570 canonical slots**: one
`cwdloop` slot has two semantic owners and four slots cross a pack seam with
two physical spans. Focused tests pass **6/6**, the new backend plus catalog
gate passes **17/17**, and **384/384** mono/stereo block comparisons are
byte-identical with the established encoder. Independent review found a
reversed-seam acceptance bug; the planner now reconstructs the exact ordered
contiguous projection, all forged reordered/duplicate/overlap/gap cases fail,
and the reviewer returned **GO**. The exact pure-Python encoder measured about
145 blocks/second; an unshipped batched native prototype reached about 29,122
blocks/second. Streaming rows intentionally remain Export-only until the
private source-bound PCM fingerprint inventory and Build transaction gate are
complete. No retail bytes, GUI, XISO, cache archive, or release package was
modified by this source slice.

## Post-RC9 private audio-origin inventory — intermediate source slice

The private exact-PCM fingerprint store is implemented at
`mod_editor/core/nfl2k5_audio_source_fingerprints.py`. It binds a canonical,
mode-0600 inventory to the recognized source XISO SHA, requires **850**
standalone occurrences, **53,570** canonical streaming slots, and **53,571**
streaming owners, validates the complete ID/owner/shape sets on every load,
and provides union-wide exact-PCM rejection without storing WAV, PCM, encoded
audio, pack spans, or host paths. Atomic publication, deterministic bytes,
progress/cancellation, malformed/tampered inventory rejection, concurrent
no-clobber publication, foreign-name preservation, and alias resolution now
pass the combined **30/30** exact-store/AUSB/catalog gate. The corrected
store/scanner pair passes **27/27** focused and **44/44** broader tests under
independent review; the local five-module closure passes **48/48**.

The first real-source scanner attempt was not accepted. Review found that its
850 standalone PCM values came from the pinned shipped capacity report rather
than a fresh decode of the authenticated XISO, and that a source change in the
narrow interval after the final rehash could raise after the inventory pathname
became visible. Both defects are closed. Every standalone AUDO is now read and
decoded from the read-only XISO descriptor, with report hashes used only as
cross-checks. The final complete source rehash runs inside the store's
pre-publication guard, and a post-publication source-identity failure removes
only the inode owned by that failed transaction. Independent review returned
**GO** at store SHA-256 `65e5ec17150976dc3dbd0483ca344f77f26049591c1c7dd0b9a8327ab2bd6218`
and scanner SHA-256 `9c46fb4a4836c40c1e1cfa131c0bf715efa7e9cba3eceb55f2538eeb2a8b3646`.

The corrected real scan then completed headlessly in **217.94 scanner seconds**
(**222.07 seconds** including cache recognition). It authenticated the complete
6,300,499,968-byte XISO before and after the work, directly decoded **850**
standalone sounds, and covered **17** AUSB descriptors, **53,571** logical
ranges, **53,570** canonical physical slots, **53,571** logical streaming
owners, and **2,183,326,092** encoded streaming bytes. A clean second pass
loaded the finished inventory as reusable and reproduced all counts. The
mode-0600, single-link private JSON is **14,515,240 bytes**, declares zero audio
payload bytes and `shareable: false`, and has SHA-256
`a74a9b1b1c4a7800559421e171e8635b0fc5e1953b28f3aaca8fd98a7b91dc4a`.
The earlier quarantined file was byte-identical to this freshly source-derived
result and was deleted as a redundant generated copy; the approved canonical
inventory remains. No XISO, archive cache, PCM, WAV, or encoded-audio file was
written or modified.

The complementary exact-containment primitive now indexes quarter-second
source windows on a rational quarter-second grid and one catalog-pinned short
anchor where needed, then scans candidate PCM at every frame offset with a
rolling Adler checksum and SHA-256 confirmation. Any unchanged same-shape
source excerpt of at least about **500 ms** necessarily contains a protected
window. It is lazy and one-cue bounded; only all-zero PCM is exempt. Direct
SHA-keyed buckets and incremental record/owner-reference caps close both review
findings. Independent review returned **GO** at source SHA-256
`da564ae30a18e9bfc7a3006b2422bceef0d0078d3cb9a919671ade23eda5f146`;
the current containment/store gate passes **37/37**. The source-bound
persistence/scanner layer then passed independent hostile review after closing
three reproduced blockers: parent-directory swap redirection, a missing
post-source check when a concurrent publisher won, and arbitrary persisted
owner labels. Its final source/test hashes are
`c49365e1fc7bba234ffedca7314a0d35a543c52b5057dda274d779b6e3b9dd2d`
and `9df42e3b419e6520f294cff40d3a35318933e8ee5e08fd05d4dc92ccc6dbb955`;
the related bytecode-disabled gate passes **76/76**.

The approved real containment scan completed headlessly in **878.23 seconds**.
It authenticated and rechecked the complete 6,300,499,968-byte XISO, directly
covered **850** standalone cues plus **53,570** canonical AUSB slots behind
**53,571** logical streaming owners, and produced **615,244** canonical digest
records across **54,420** source cues / **54,421** owners. The published private
document is **152,956,258 bytes**, mode `0600`, single-link, declares
`shareable: false`, and has SHA-256
`617bc7da80f8c81940bd8c8c32080cac2461d6d48c7e36a1ee0ff06f9f3369de`.
It contains no WAV, PCM, encoded sound, game span, or source path. A clean
second pass returned `reused: true` in **130.35 seconds**, reproduced all
counts, and completed a fresh full-source recheck without re-decoding the
streaming bank payloads. No temporary containment file remained.

The final same-snapshot Build boundary is now implemented in the post-RC9
source. A process-local sealed authorization object is issued only after both
private inventories accept the exact immutable `InputPin.payload`; Menu Back,
standalone AUDO, and AUSB encoders consume that same snapshot. The reviewed
AUSB adapter accepts exactly one physical pack span or a two-pack seam,
strictly binds logical IDs to numeric ownership, deduplicates identical aliases,
and rejects divergent aliases. BuildService conditionally supplies the two
canonical private inventories to both Build and independent Verify for audio
projects while leaving visual-only builds unchanged. Session/project/UI wiring
is still in progress, so the public streaming Replace control remains locked.

The hostile gate review is recorded in
`docs/product/NFL2K5_STREAMING_AUDIO_ORIGIN_GATE_HOSTILE_REVIEW.md` with final
SHA-256
`be64c29eab15f8893c38fb2566781b3fffb930bb2a499f2857ff7e99505c2d2a`.
It found four P0 conditions before UI/Build unlock: preview history cannot
control protection; raw canonical JSON and legacy Menu Back must reach the
same final gate; full hashes need exact containment-window coverage for
trims/padding/concatenation; and public documentation must distinguish the
existing reviewed AUDO hash metadata from the new private inventory. It also
requires aggregate project-ZIP expansion/edit bounds. The disposition is
**HOLD only on public streaming Replace/Build**, not on continued implementation.

The review's project-archive P1 is now closed in the source tree. `.2k5mod`
save/load share one **25,000 combined visual-plus-audio edit** ceiling, matching
the unified backend's logical-edit budget, and cap
authored replacement payloads at **1 GiB**, preflight total declared ZIP
expansion and free staging space before extraction, and retain the **2 GiB**
archive ceiling. Authored WAVs are read through the existing descriptor-pinned,
single-link bounded reader instead of `lstat()` followed by `read_bytes()`.
Focused project-bound tests cover aggregate expansion, combined counts,
hardlinks, and save overflow; the broader project/session/audio gate passes
**41/41**. This closes P1 only; the four P0 origin/Build conditions above still
control the streaming Editability lock.

The unified backend's target-overlap check is now sorted-adjacent
**O(n log n)** instead of comparing every new edit with every earlier edit.
A worst-budget synthetic set of **25,004** out-of-order, non-overlapping spans
validates in about **3.24 ms** on this host; touching spans remain allowed and
an out-of-order overlap still fails with its logical target name. The focused
audio/stadium composition gate passes **11/11**. This removes a scaling trap
before one logical AUSB edit is allowed to expand into two internal seam spans.

The release gate now has a structural no-leak canary for the new private audio
inventories. It rejects any `derived/` cache tree even under an allowed prefix,
rejects recognizable audio-origin inventory filenames, and rejects a renamed
JSON file carrying the exact-fingerprint schema or either containment v1/v2
schema. Product `.py` code may define the protocol, but generated values cannot
enter a stage even if a future allowlist accidentally names them. The expanded
packaging gate passes **17/17**. The existing reviewed standalone AUDO metadata
exception remains unchanged and must be described honestly until its
public/private split is a separate shipped migration.

## Post-RC9 audio-browser search latency — UX slice shipped

A real-source headless benchmark found that rebuilding search text for all
53,571 streaming rows cost **367–424 ms per query**, which would feel laggy
while typing. The facade now precomputes the metadata-only haystacks once per
loaded catalog in about **395 ms** and invalidates them when the catalog
changes. The same searches now complete in **23–35 ms** median; unfiltered
paging remains about **4 ms**. The focused backend/facade suite passes
**23/23**, including one-build-per-catalog and catalog-A-to-B invalidation.
The index contains catalog metadata only, changes no retail cache or XISO, and
does not alter any Editability status.

## APF membership-census hook — reviewed checkpoint shipped

The observation-only Xenia hook is committed at
`d09cae8d8374324048ef603d48a9c1696b39d552` and the runner is locked to the
reviewed binary SHA-256
`712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d`.
Its dedicated Linux hostile-thunk sentinel passes 22/22 assertions, the
backend selection passes 18/18 tests, the full CPU suite passes 247/247, and
the runner/safety suite passes 43/43. The retail-free binary/source checkpoint
is in `artifacts/apf_membership_census_xenia_d09cae8d/` with verified hashes.
A fresh real-source dry-run admitted that exact pair and preserved all six
source files / 3,919,218,688 bytes. This proves hook/thunk and preparation
safety only. No game or emulator was launched, and true 53-active-player
behavior remains unproved pending the controlled runtime trace.

## Release-candidate outcome

RC13 is the current sealed release-candidate checkpoint. It carries forward the
complete 11-tab product shell, **62-row** cross-title capability registry,
whole-game raw resource fallback, admitted Tier 1 editors, compact desktop
layout, Audio Collections, active-project workflow, atomic build/project safety
boundary, complete fixed-range AUSB authoring, and mixed selected-shortlist
replacement packs. It also restores Modified-range parity across collection
exports and specialist Ctrl+F routing. RC12, RC11, RC9, RC8, RC7, and RC6
remain immutable packaged checkpoints; their exact receipts and checksums are
preserved below.

The RC3 foundation originally gave all 850 standalone cues, all 17 known AUSB
descriptors, and all 53,571 exact streaming ranges dedicated searchable homes.
RC12 retains that browser, promotes every exact range to Editable, and can batch
author an ordered mixed selection while keeping complete raw banks Export-only.
Dedicated Gameplay
and Menus inspectors, source-bound autosave/recovery, recent-file menus, and
Save/Discard/Cancel data-loss gates are also included. RC4 turned that
inventory into a practical collection workflow: a one-click 136-range
soundtrack/music view, Modified-only review, and transactional 1–256-row
WAV/raw ZIP export. Every bundle is checksum-manifested, distinguishes user
replacements from retail-derived local exports, and remains structurally
outside shareable projects.

RC5 makes project handling behave like a normal desktop document. Opening or
first-saving a `.2k5mod` establishes an active project name; the title marks
unsaved changes; **Save** / `Ctrl+S` updates that exact target; and **Save
Project As…** / `Ctrl+Shift+S` owns first naming and copies. Protected fast-save
refuses missing, linked, substituted, or externally changed targets. Dirty
state is independent of replacement count, so saved-project → Revert All stays
saveable/recoverable as an explicit empty replacement-only project while Build
correctly remains disabled.

RC6 adds an ordered, session-only Audio Shortlist. A modder can hand-pick
playable standalone AUDO sounds and indexed streaming ranges across unrelated
searches, pages, families, and scopes, then export those exact IDs as one WAV
ZIP. Add/Remove, atomic Add This Page, Clear, a visible `★ Selected` badge, and
the **Selected _n_ / 256** count make the curation state explicit. Complete
banks stay excluded because a bank is not one cue. The shortlist survives
ordinary refresh and project loads for the same source, clears only after a
successful new-XISO load, and never enters `.2k5mod`, recovery, Undo, modified
state, or Build.

RC7 turns that shortlist into a practical listening-order workspace. **Review
selected** isolates the curated rows; Play/Stop, remove, and Move up/down work
there; **Back to browser** restores the exact prior scope, filters, page, and
selection. Every multi-WAV collection now contains an ordered `playlist.m3u8`
and matching manifest fields, while raw-only bundles truthfully omit it. The
fourth Audio scope inventories and byte-exactly exports the nine raw universal
containers: three `BANK`, three `ABNK`, and three `WBNK`. Raw containers remain
Export-only and outside projects, recovery, Undo, modified state, and Build.

RC8 ships the **Complete Team Kit** workflow. Any catalogued physical set, any
explicit multi-selection, or a team's HOME/AWAY pair can be exported as a
labeled folder or deterministic ZIP with all 39 supported parts per set. The
bundle includes gameplay torso/sleeve/pants, both helmet families, all live
digits, the nameplate atlas, and all three independent Team Select cards. Its
guide states the honest UV/ownership limits instead of inventing body-region
semantics.

Import is source- and baseline-bound. It validates the unchanged manifest and
guide, every row/path/PNG/dimension, and all decoded RGBA pixels before staging
anything. True pixel changes enter the existing project/build path as one Undo
action; unchanged or rejected imports add no edit or Undo entry. Private Team
Kit exports may reproduce retail artwork and must not be shared; `.2k5mod`
remains the retail-free, replacement-only sharing format.

The focused RC8 Team Kit/session/facade/packaging selection passes **47/47
tests**, and the stable current cross-title headless suite passes **489/489**
with `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`. RC8 was
assembled headlessly: no visible GUI or emulator was launched, and the user's
desktop was not touched.

The sealed checkpoint then passed its separate visual gate through Spark Hands
on isolated `DISPLAY=:99`. The fresh `v1.0 RC8 • Xbox Edition` window loaded
the user's XISO and showed the 39-component **Complete Team Kit** panel with
paired `HOME + AWAY`, editable-folder selection, Export/Import actions, the
private-retail-art warning, and the normal build footer. Spark found no
clipping, overlap, inconsistent padding, or footer obstruction. The user's
active desktop and pointer were never used.

RC9 adds the retail-free batch authoring handoff for all 153 currently Editable
standalone cues. Folder and deterministic-ZIP templates contain metadata and an
empty replacement directory, never source WAVs. Import is source- and current-
baseline-bound, validates every supplied cue before mutation, commits all real
changes as one Undo action, and refuses decoded PCM owned by any of the 850
standalone source cues or any source-verified streaming range already in the
private cache. Streaming-bank writeback remains honestly locked.

### RC11 sealed release receipt

- Runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC11-20260720`.
- Portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC11-20260720.tar.gz`
  (**9,779,134 bytes**).
- Checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC11-20260720.tar.gz.sha256`.
- SHA-256:
  `c0dd5c0461194f21ca36649fe10ada92e93c8f73f42ea3ab256316a76190001c`.
- Source version is `1.0.0rc11`; the complete AUSB/product closure passes
  **332/332** tests, with an additional **17/17** focused packaging pass.
- The clean stage and independent extraction each contain **144 files**, **13
  directories excluding the root**, and **102,407,073 file bytes**. The tar has
  **158 members** and the normalized content/mode tree digest is
  `3bcdcde5201fea277fdef558b269a46d1d36e7d3d7263d0c4a535c290d32f837`.
- Both trees pass release/runtime/desktop/Bash/post-runtime gates. Runtime
  closure is **46 product + 22 tool modules**, **62 capabilities**, **11
  sections**, and **31 NFL 2K5 capabilities**; all 53,571 streaming ranges are
  Editable and the public stage contains no retail or private inventory.
- The runtime checker was run from caller directory `/` against the independent
  extraction, the trees are byte- and mode-identical, and a deterministic
  re-archive is byte-identical to the sealed archive. No GUI or emulator ran.

### RC9 sealed release receipt

- Runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC9-20260719`.
- Portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC9-20260719.tar.gz`
  (**9,690,570 bytes**).
- Checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC9-20260719.tar.gz.sha256`.
- SHA-256:
  `758bf0805f0c0f8e219fa6f945ae5df938c03b9854b5c94e2cc1e861cbe25184`.
- Source version is `1.0.0rc9`; the final eight-module dependent gate passes
  **99/99**, and the independent **93/93 + 16/16** adversarial review is GO.
- The stage and independent clean extraction each contain **136 files**, **14
  directories including the root**, **101,985,801 file bytes**, **36
  executables**, and zero links or special files. The tar has **150 members**.
- Both trees pass release/runtime/desktop/Bash/post-runtime gates. Runtime
  closure is **38 product + 22 tool modules**, **61 capabilities**, **11
  sections**, and **30 NFL 2K5 capabilities**; all 53,571 streaming ranges are
  retained and the public stage contains no retail or private inventory.
- The extraction is byte- and mode-identical, and a deterministic re-archive is
  byte-identical to the sealed archive. No GUI or emulator was launched.

### RC8 sealed release receipt

- Runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC8-20260718`.
- Portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz`
  (**9,667,067 bytes**).
- Checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz.sha256`.
- SHA-256:
  `17254d4030806e8636c67a9b90cfcee88a7711484d9ab6ef079aba875e569466`.
- Source version is `1.0.0rc8`; focused RC8 passes **47/47**, and the complete
  current cross-title suite passes **489/489**.
- The stage and independent clean extraction each contain **135 files**, **14
  directories including the root**, **101,871,957 file bytes**, **36
  executables**, and zero links or special files. The tar has **149 members**.
- Both trees passed release/runtime/source-free-registry/desktop/Bash/
  post-runtime gates; full file-backed registry validation passed against the
  source tree. Runtime closure is **37 product + 22 tool modules**, **60
  capabilities**, **11 sections**, and **30 NFL 2K5 capabilities**.
- The extraction is byte- and mode-identical; its normalized content/mode
  inventory SHA-256 is
  `df710e64f5e7f441dfa51908a161425478c0b1c9b210a3b06cc50f0ae924df10`.
- RC7 and RC6 were reverified after the RC8 seal and remain byte-for-byte
  immutable at SHA-256
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
  and `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`,
  respectively.

### RC7 sealed release receipt

- Runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC7-20260718`.
- Portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz`
  (**9,658,588 bytes**).
- Checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz.sha256`.
- SHA-256:
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`.
- Source version is `1.0.0rc7`; focused RC7 passes **42/42**, the complete
  non-APF selection passes **362/362**, and the complete current cross-title
  suite passes **475/475**.
- The stage and independent clean extraction each contain **134 files**, **14
  directories including the root**, **101,801,912 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **36 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical; its normalized content/mode inventory SHA-256 is
  `e80313e49d9acade03e4dc8668eb4dda0059f6fd3e47320d0f8104e832917031`.
- RC6 was reverified after the RC7 seal and remains byte-for-byte immutable at
  SHA-256
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.

### RC6 sealed release receipt

- Runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC6-20260718`.
- Portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz`
  (**9,643,071 bytes**).
- Checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz.sha256`.
- SHA-256:
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.
- Source version is `1.0.0rc6`; focused Audio passes **18/18** and the complete
  cross-title desktop-tool suite passes **443/443**.
- The stage and retained independent extraction each contain **134 files**,
  **14 directories including the root**, **101,773,880 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **36 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical; its mode-inventory SHA-256 is
  `98cd357f6c128b081c8cf034e8df6cecbbc52704a10480980cae593398d9f00b`.
- RC5 remains immutable at SHA-256
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`.

The preserved sealed non-overwriting RC5 release is:

- runnable tree: `/home/noah/2K5-Mod-Studio-v1.0-RC5-20260718`;
- portable archive: `/home/noah/2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz`
  (**9,639,953 bytes**);
- checksum sidecar:
  `/home/noah/2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz.sha256`;
- SHA-256:
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`.

### RC5 sealed release receipt

- Source version is `1.0.0rc5`; the complete desktop-tool suite passes
  **428/428**.
- The tar contains **148 members**. The original stage and independent clean
  extraction each contain **134 files**, **14 directories including the root**
  (**13 internal**), **101,750,965 file bytes**, **36 executable files**, and
  **zero links**.
- The original tree and independent clean extraction both passed the
  release/runtime/registry/desktop/bash/post-runtime gates.
- Runtime closure imports **36 product modules** and **22 tool modules**. The
  canonical product surface remains **60 registry capabilities**, **11
  sections**, and **30 NFL 2K5 capabilities**.
- The clean isolated Spark check passed the File-menu shortcut, disabled-state,
  spacing, and clipping review on `DISPLAY=:99`.
- Empty documents remain replacement-only: the explicit archive contains only
  `project.json`, `edits: []`, and the existing `user-replacements-only` policy.
- The immutable RC4 checksum sidecar was reverified unchanged after RC5 sealed.

### Preserved RC4 source-free preflight

- The Audio registry now carries the complete external-bank blocker: recover
  cue identities/directories, loop points, gain, pan, priority, runtime
  routing, and reversible rebuild rules before exposing any bank writer. The
  older codec/directory-only wording is rejected by a focused regression test.
- The capability plan remains exactly 60 rows: 55 validated capabilities, five
  intentional deferrals, and **43 unique validators**. Source-free canonical
  registry validation passed all 60 rows.
- The complete current desktop-tool selection passed **419/419 tests**,
  including both title backends and shared-provider cases. The new 2K5 and APF
  Audio layouts then passed through Spark Hands on the isolated display.
- The exact release allowlist now includes the new metadata-only Audio bundle
  module. The fresh stage passed with **134 files**, **13 internal directories**
  (**14 including the release root**), and **101,736,199 file bytes**, with no
  source XISO, private inventory, symlink, undeclared file, generated
  local-audio ZIP, or retail payload.
- The clean-stage runtime closure imports **36 product modules** and **22 tool
  modules**, then exercises source-bound recovery, all 850 standalone sounds,
  all 17 streaming descriptors and 53,571 streaming ranges, Gameplay and Menus
  inspectors, Text, PLAY, Crib, Stadium, scorebug, and the display-free desktop
  construction boundary.
- The first post-runtime scan found that imports had published `__pycache__`
  files. The runtime checker now disables bytecode publication before importing
  product code; the final stage passed release, runtime, desktop-entry,
  launcher-syntax, registry, and post-runtime release gates with identical file
  and byte totals.

### Headless Audio expansion proof

- The private source cache indexed 850 standalone cues (153 Editable / 697
  Export-only), 17 AUSB descriptors, 16 external owners, and 53,571 individual
  raw-range rows without opening a GUI or modifying the source.
- Range-family totals are 52,940 commentary, 136 music, 482 presentation, 9
  stadium/PA/coach, and 4 ambient. No zero-length ranges were found; observed
  sizes run from 2,664 to 8,954,064 bytes.
- An exact `overlayaudio` range export streamed bytes `0..86,472` into a new
  temporary `.bin`; the published size was exactly 86,472 bytes and the
  temporary proof was removed afterward.
- Empty, family-filtered, and targeted real-catalog range pages completed in
  1.4 ms, 12.4 ms, and 14.3 ms respectively in the headless timing spot check.
- All 76 applicable headless audio/product integration tests passed. The one
  visual Qt test was deliberately not run because desktop operation is assigned
  to Spark Hands; capability-registry validation separately passed all 60 rows.

### AUSB Xbox IMA decode closure

- All 53,571 range sizes are whole `36 * descriptor_channels` byte groups.
  A complete scan of the 16 physical banks checked 2,183,326,092 encoded bytes
  and 60,647,947 channel-block headers; zero step indices were outside 0..88.
- Independent FFmpeg IMA correlation passed for the smallest music range
  (`loadm` range 0, stereo, 3.181134 s) and smallest commentary range
  (`players` range 7,227, mono, 0.214785 s).
- The product now privately decodes every range to verified PCM16 WAV and wires
  it to Play/Stop and Export WAV while preserving Export Raw Range.
- The largest real `cribmusic` range decoded 8,954,064 encoded bytes to a
  31,836,716-byte stereo WAV in 1.018681 seconds; the optional accelerated path
  and the exact pure-Python fallback are both covered.
- Derived retail audio stays in the user's private source cache/output and is
  structurally excluded from projects. Failed headers leave no cache artifact;
  altered/incomplete cache pairs and existing export destinations are refused.
- Human cue names, loops, mixer rules, runtime selection, and whole-bank
  repacking remain unresolved. Fixed-allocation replacement is now shipped for
  every exact range; it preserves each row's existing duration and routing.

### Gameplay and Menus product-depth slice

- **Sliders & Gameplay** now has a dedicated read-only inspector for all 21
  named controls, all 17 proved CPU **Fantasy Draft** weights, eight observed
  save containers and their signature boundary, and five bounded franchise
  findings. Fixture values are explicitly labeled as research observations,
  not the user's current profile.
- **Menus & UI** now has a named Main Menu inspector for all seven initialized
  rows/transitions, both proved layout relationships, rendering boundaries,
  and all three actionable blockers. The existing complete archive-resource
  raw browser remains available as a separate tab in the same workspace.
- Both inspectors export sanitized JSON or spreadsheet-ready CSV through the
  facade with non-overwriting output creation. They expose no preset or
  writeback control and do not claim Fantasy Draft weights fix Franchise Draft.
- Two small hash-pinned product snapshots keep these views runnable in a public
  stage without shipping the underlying research reports. They contain named
  metadata only, are covered by the reviewed-metadata release gate, and are
  structurally checked against the proved core outputs when those reports are
  available in the development tree.
- Capability cards and limitations remain visible beside both specialized
  workflows. Focused model, facade, legacy-core, offscreen Qt connectivity,
  and release-manifest coverage passed **51 tests**; no GUI was launched or
  visually inspected, and no package was built.

The clean package stage passed its release gate with **126 allowlisted files**
and **101,447,213 bytes**. The gate found **zero retail game bytes** and no
private source inventory. Retail XISOs, compiled modded XISOs, private previews,
private cache data, extracted game resources, and research-generated Stadium
models are not release payloads.

The final runnable tree is
`/home/noah/2K5-Mod-Studio-v1.0-RC2-20260718/`. The new, non-overwriting
portable archive is
`/home/noah/2K5-Mod-Studio-v1.0-RC2-20260718.tar.gz` (**9,575,103 bytes**),
SHA-256 `6df15767ff766d7eb2b7b87634d79dee495102c74db323067eedc01f796193d7`.
The 312-test headless 2K5 product suite passed with no failures, errors, or
skips. The retail-free and runtime-closure gates passed on the clean tree and
again after extracting the archive; desktop-entry validation and launcher
shell-syntax validation also passed. The post-runtime retail gate passed again,
proving the probe left no bytecode or other undeclared files.

## Clickable in v1.0

All 11 product tabs exist from the first launch:

1. **Uniforms & Equipment** — searchable PNG previews and bounded
   Export/Replace/Revert/Build for proved jerseys/torsos, sleeves, pants,
   helmets, digits/nameplates, and separate Team Select cards.
2. **Rosters & Players** — complete current/historical name and jersey-number
   workflows under **Players & Numbers**, plus searchable portrait and
   live-face texture workflows under **Portraits & Faces**. All 6,522 indexed
   jersey-number assets have exactly one current or historical player row;
   proved primary rows are editable and unsafe secondary-pool rows remain
   Preview/Export-only.
3. **Text & Team Identity** — the universal fixed-allocation text browser,
   including team identity and all safely owned strings. Roster editing is no
   longer filed here.
4. **Field Art & Create-Team Art** — proved create-team field-art textures with
   PNG Export/Replace/Revert/Build.
5. **Stadiums** — Stadium Studio for 477 scenes, including orbit/pan/zoom,
   click-through surface ownership, and bounded editing for all 23,838 indexed
   P8 texture occurrences on existing geometry.
6. **Scorebug & Presentation** — proved scorebug/presentation textures,
   including the shared `digital_font` caveat.
7. **Menus & UI** — all seven named Main Menu rows/transitions, layout and
   rendering ownership, actionable limitations, JSON/CSV export, capability
   cards, and the complete archive-resource raw fallback.
8. **The Crib** — all 498 catalogued textures, with 128 Team Photos and the
   exact `room:22 / bar_monitor` surface editable.
9. **Audio** — browse/play/export for all 850 standalone AUDO resources, with
   all 850 exact physical slots editable and honest semantic warnings on 697
   alias-related rows; searchable raw export for all 17 AUSB soundtrack/
   commentary/stadium/presentation bank descriptors;
   and Play/Stop, PCM16 WAV/raw export, Replace/Revert, project save/load, and
   Build for all 53,571 indexed Xbox IMA ranges through 53,570 exact physical
   slots. The ordered 256-sound shortlist collects standalone sounds and ranges
   across filters/scopes and exports the exact selection as one transactional
   WAV ZIP.
10. **Sliders & Gameplay** — dedicated tables for 21 named sliders, 17 Fantasy
    Draft weights, save/signature evidence, and five franchise findings, with
    JSON/CSV export. Unproved Catching and Draft experiments are not exposed as
    presets or writers.
11. **Playbooks & Plays** — a structured viewer for every decoded PLAY book,
    formation, play, assignment chain, node, and player-slot reference, plus
    raw resource export. Route authoring remains Coming Soon.

The archive-resource browser remains the universal fallback: no resource in
that index is hidden merely because a specialized editor has not been built.
Registry-derived **Editable**, **Preview/Export-only**, or **Coming Soon**
states appear on capability cards; raw fallback rows retain their explicit
Export-only boundary instead of pretending that registry status is an action.

## Exact v1.0 inventory

| Product surface | Exact release-candidate coverage |
| --- | ---: |
| Capability registry | 62 rows total; 31 NFL 2K5 rows |
| Sidebar tabs | 11 |
| Specialized visual assets | 32,038 |
| Text banks | 716 |
| Decoded strings | 23,346 |
| Editable strings | 20,074 |
| Read-only strings | 3,272 |
| Jersey-number assets | 6,522 |
| Standalone AUDO resources | 850 total; 850 Editable; 0 Export-only; 697 carry semantic/runtime-selector warnings |
| Streaming AUSB audio | 17 descriptors; 16 external `.bin` owners; 53,571 Editable logical Xbox IMA ranges through 53,570 fixed physical slots; complete banks Export-only |
| Crib assets | 498 total; 129 Editable; 369 Export-only |
| Stadium scenes | 477 |
| Editable Stadium P8 occurrences | 23,838 |
| PLAY books | 37 |
| PLAY formations | 1,533 |
| PLAY plays | 9,251 |
| PLAY assignment chains | 32,502 |
| PLAY nodes | 91,833 |
| PLAY player-slot references | 101,761 |

## Tier 1 shipped ledger

| Tier 1 requirement | v1.0 result | Safety boundary |
| --- | --- | --- |
| Uniforms and equipment | Shipped | Fixed owned allocations only; gameplay textures and Team Select cards remain separate assets. |
| Portraits and live faces | Shipped | Exact proved formats/dimensions; the importer rejects incompatible PNGs. |
| Names, team identity, and jersey numbers | Shipped for every proved allocation | All 6,522 numbers are browsable; unsafe secondary-pool writeback stays read-only. Ratings, membership, position, and depth charts are not implied. |
| Historical rosters | Shipped | All 75 historical ROST resources and 3,975 historical players are present. Proved same-allocation names/numbers are editable. |
| Field art and scorebug | Shipped | Only owned fixed-allocation visual classes are writable; `digital_font` is shared presentation art. |
| Universal text | Shipped | 20,074 fixed-allocation strings are editable. The 3,272 unsafe/zero-capacity entries remain visible and read-only with a reason. |
| Audio | Shipped at the proved boundary | All 850 standalone physical AUDO slots and all 53,571 logical AUSB ranges are writable under each row's exact PCM contract. Alias-related standalone rows remain distinct physical edits; AUSB aliases share one of 53,570 fixed physical slots. Complete raw banks remain Export-only; runtime audibility and semantic cue ownership are not claimed. |
| Stadium Studio texture swaps | Shipped | All 23,838 P8 occurrences are editable on existing geometry. A replacement that cannot fit the original compressed SCNE allocation is refused. |
| Crib photos | Shipped | All 128 Team Photos are editable. The proved `bar_monitor` object reskin also ships as a bonus bounded surface. |
| Project, undo, revert, and build safety | Shipped | Projects contain user replacements and logical metadata only; source XISOs are read-only; output creation is exclusive and published only after success. |

## Composed Tier 1 smoke result

One product-flow project staged **19 Tier 1 edits** and built them into one new
XISO. The verified build changed **1,027,710 bytes** and produced:

`70cd2bc0acc57d358d800cd6c0952c1c89c1c09ee9039d9513e435c58dffa0a6`

The source XISO was opened read-only and retained the same SHA-256 before and
after the build:

`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`

Headless Spark inspected xemu only on the private Xvfb display `:99`; the test
never moved, clicked, or typed on the user's real desktop. It saw the ESPN
splash, a stable attract sequence, and a clean NFL 2K5 title / **Press START**
screen with no visible corruption.

This is a boot-level product spot check, not deep gameplay proof. No claim is
made that every one of the 19 edited assets was individually navigated to and
visually judged in-game. A later retry in the isolated software-rendered xemu
harness logged a PFIFO assertion during or after the close attempt. That later
harness failure does not erase the earlier visible boot sequence, but it means
v1.0 does not claim a clean long-duration gameplay session from this smoke.

## Release and data-safety ledger

- The clean RC11 stage contains 144 allowlisted files totaling 102,407,073
  bytes; its independent extraction and deterministic re-archive match.
- The release gate found no retail game bytes and no private inventory.
- The app requires the user to provide their own recognized USA NFL 2K5 XISO.
- The source is never a valid build destination and is always opened read-only.
- Each replacement has a private original for per-asset Revert; Undo, Revert
  All, and project-wide rollback use the same session model.
- A build uses a temporary output and exclusive final creation. A failed build
  cannot publish a partial/corrupted requested output.
- A `.2k5mod` project stores only user-authored replacement files and logical
  metadata. It does not store original resource payloads or an XISO.
- xemu is the supported emulator target. Original Xbox hardware remains
  untested.

## Complete post-v1 triage ledger

Every item below is either partially delivered, visible as Preview/Export-only,
or represented by an in-app Coming Soon boundary and its findings note. These
items did not block v1.0.

### Tier 2 — best effort

| Item | v1.0 disposition | Why it is not fully shipped | Single best next step |
| --- | --- | --- | --- |
| Catch-strength presets | Coming Soon; private 125/150/200 executable transports exist | Offline transport does not prove polarity or drop-rate effect. | Run matched stock/125/150/200 same-play samples in xemu, count catchable-target drops, and promote only presets with a repeatable effect. |
| Draft-AI presets | Fantasy Draft control remains experimental; Franchise Draft remains Coming Soon | The known 17-float table is consumed by Fantasy Draft, not the Franchise rookie draft. | Runtime A/B the extreme Fantasy control first, then trace the separate Franchise rookie prospect-scoring call chain. |
| Additional AUDO replacement | Shipped: 850 of 850 physical resources Editable | Physical ownership is complete; semantic names/runtime selector owners remain uncertain for 697 alias-related rows. | Runtime-trace one alias family so provisional labels can be replaced with confirmed in-game meanings. |
| Music/commentary and other banked audio | All 53,571 logical ranges are Editable through 53,570 exact physical fixed slots; complete raw banks remain Export-only | Cue names, loops, gain/pan/priority, mixer routing, and whole-bank repacking are still unresolved; audible runtime consumption is not yet claimed. | Runtime spot-check one clearly authored range, then map its cue/loop/mixer owner without weakening the shipped fixed-slot boundary. |
| Crib object reskins | `bar_monitor` shipped; 24 other electronics-like rows Export-only | Catalog ownership is mapped, but their fixed-span writers have not been proved individually. | Choose one uniquely owned electronics surface, prove a same-allocation texture rebuild, and generalize only if the scene reparse stays exact. |
| Bounded Stadium geometry | Coming Soon; texture editing shipped | General mesh serialization, draw commands, transforms/collision, and relocation are not owned as one safe contract. | Productize one already bounded vertex/plane edit as an explicitly narrow tool before attempting broader geometry. |
| ESPN 25th moment text | Shipped | All four display strings for each of 25 moments are editable; no remaining Tier 2 text gap is hidden. | Use the shipped text editor; keep scenario state and unlock behavior in the Tier 3 lane below. |
| Deeper roster editing | Coming Soon beyond proved names/numbers | Position codes/labels and selected read-only metadata are already decoded in research, but are not yet surfaced in the product form; ratings, membership, depth charts, and secondary-pool writeback do not share the proved fixed-text contract. | First wire the already-decoded team/position/face metadata into the roster browser, then isolate and runtime-check one writable field family. |

### Tier 3 — spike-only

| Item | v1.0 disposition | Why it is not fully shipped | Single best next step |
| --- | --- | --- | --- |
| Visual Play Editor | Structured viewer/inspector shipped; authoring Coming Soon | Coordinates, player roles, opcode operands, custom-save ownership, and inverse compilation remain undecoded. | Create four controlled game-authored custom-play fixtures, diff X/Y/waypoint/route-type changes, then correlate them with runtime reads. |
| Stadium/Crib model import or swapping | Coming Soon | UV/normal registers, inverse draw-command serialization, transforms, collision, and relocation are not safely decoded. | Try one same-allocation mesh swap with identical topology and prove render plus collision before considering arbitrary import. |
| ESPN 25th scenario logic and unlocks | Coming Soon; display text shipped | SITU numeric fields and persistent-profile unlock ownership are not semantically mapped. | Trace one moment while loading its score, clock, possession, field position, and completion state; name fields only when the runtime consumer agrees. |
| Franchise/save-backed structural features | Coming Soon | Save ownership, integrity, and mode-state precedence are not bounded enough for product writeback. | Use an isolated xemu profile to produce one clean single-field save differential and identify its integrity owner before writing anything. |

## Deliberate non-claims

- The smoke is not Giants home/away, coin-toss, post-coin-toss, or
  asset-by-asset gameplay persistence proof.
- The app does not call Fantasy Draft weights a Franchise Draft fix.
- Catching values are not presented as finished presets before a measured A/B.
- The Playbooks tab does not pretend raw route bytes are understood well enough
  to draw and save new plays.
- Stadium Studio edits textures on existing geometry; it is not a general model
  importer.
- The release does not ship experimental XISOs, source extracts, originals,
  preview caches, research screenshots, or other retail-derived payloads.

## Five-line 2K5 status

- **Shipped:** RC28 is sealed with fully validated read-only Audio-pack Preview followed by explicit token-bound Apply/revalidation.
- **Experiment result:** 609/609 2K5, 162/162 release-focused, and 90/90 pack/panel checks pass; clean stage/extraction gates, deterministic rebuild, and independent review are all green.
- **Blocked on user:** nothing blocks headless closure; cue audibility/meaning still needs a later controller-driven xemu listen A/B, and teaser candidates still need one human visual look.
- **Next:** seal APF Alpha32, then continue the next bounded Audio/UX improvement without changing RC28's reviewed bytes.
- **Deliberately not done:** no audible-runtime claim, retail payload, visible desktop, pointer control, emulator, external player, recovered song titles, or whole-bank replacement claim is asserted for RC28.

## Definition-of-Done tracking

- [x] All 11 sidebar tabs exist; every indexed resource has at least a browsable/exportable home through a specialized panel or the universal fallback browser.
- [x] Every admitted Tier 1 class is replaceable/revertible/buildable; all 6,522 current and historical jersey-number assets are now covered by explicit player rows, with unsafe rows visibly read-only.
- [x] Every Tier 2/3 surface is editable, Preview/Export-only, or Coming Soon with an in-app reason/findings note.
- [x] One 19-edit Tier 1 project built, preserved the source, booted in xemu, and passed the agreed boot-level visual spot check.
- [x] Getting Started documentation and a v1.0 modder-facing capability changelog are present.
- [x] RC26 is sealed as a 145-file, 9,825,591-byte portable archive. Its stage
  and independent extraction each contain 102,617,828 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `8000796c7a4f8758c2336640bf63ffc01a537632b13e4bcf372d6bdfbb54bb82`.
- [x] RC27 is sealed as a 145-file, 9,828,168-byte portable archive. Its stage
  and independent extraction each contain 102,631,809 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `c8f7ef9645e8f636f8eaa0638656ac6abc76789e70e174d0b593b279ff8c1edc`.
- [x] RC28 is sealed as a 145-file, 9,835,954-byte portable archive. Its stage
  and independent extraction each contain 102,671,310 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. Independent review
  reports GO with no P0/P1 finding. The authoritative sidecar records SHA-256
  `8d316c51ebb696be86e6d15850a3bd00b2a02b76a92cabb6489a649045d30ac1`.
- [x] RC25 is sealed as a 144-file, 9,332,131-byte portable archive. Its stage
  and independent extraction each contain 102,560,651 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `8ad21fb0a92be85a8402fcbe85d44b27b8b9ea13468b54cda2466ce756bd4e4a`.
- [x] RC24 is sealed as a 144-file, 9,330,783-byte portable archive. Its stage
  and independent extraction each contain 102,554,002 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `67296073fcd22d93fc18bebb031a5de27247d703dd2cfa0c84b7813f6276da85`.
- [x] RC23 is sealed as a 144-file, 9,329,352-byte portable archive. Its stage
  and independent extraction each contain 102,546,349 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `aa23ad080da99d5c795613cca11e140b8626abddcfa14c3f8db558b913b3f9f3`.
- [x] RC22 is sealed as a 144-file, 9,326,590-byte portable archive. Its stage
  and independent extraction each contain 102,537,046 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `e7f3018ccd5fb3b8a446204ceb22e5f491c6813cee72c0d11315e2e2eba97548`.
- [x] RC21 is sealed as a 144-file, 9,325,798-byte portable archive. Its stage
  and independent extraction each contain 102,534,262 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `7c9acd6d99042144514a61ebaa7aad9bcf17f1ac9aed6f58bef7c9a9565ac692`.
- [x] RC20 is sealed as a 144-file, 9,324,562-byte portable archive. Its stage
  and independent extraction each contain 102,528,972 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `98402cb4e638e8beca5f2f5a0cf41cc452de712a6897c030b3b76d88bba7f38e`.
- [x] RC19 is sealed as a 144-file, 9,322,097-byte portable archive. Its stage
  and independent extraction each contain 102,514,393 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `bb1fac8a0c3267045d3d0556c0c92124dfe90990e165ec358d4fdd5d3ac9711b`.
- [x] RC18 is sealed as a 144-file, 9,320,231-byte portable archive. Its stage
  and independent extraction each contain 102,506,230 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `af79c83aeff1f723088edc59af6ad1708dc18fcd65bb4ade7eb5f53234fea05d`.
- [x] RC17 is sealed as a 144-file, 9,318,011-byte portable archive. Its stage
  and independent extraction each contain 102,498,172 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `a616e9174bcfbdf19caa0e868c1bb25d7ad596d47e49f375e08191ecaff33606`.
- [x] RC16 is sealed as a 144-file, 9,313,581-byte portable archive. Its stage
  and independent extraction each contain 102,477,638 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `ee28afd8491d8586763e2883c289ad77d1541551ef1affce34bf16112c8bf092`.
- [x] RC15 is sealed as a 144-file, 9,310,240-byte portable archive. Its stage
  and independent extraction each contain 102,456,230 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `e50e27bae01cd5800109e225bbea3bf71a6ade054f65f17235e33c09b7d3fe07`.
- [x] RC14 is sealed as a 144-file, 9,788,063-byte portable archive. Its stage
  and independent extraction each contain 102,448,423 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `bac81312efd8a2e5e42190c281e97493db5ed8959b0b2848d5e7c7e94604eb2e`.
- [x] RC13 is sealed as a 144-file, 9,787,042-byte portable archive. Its stage
  and independent extraction each contain 102,442,355 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `adc08a47aee41a9789369a42b57cd63f560502e447e37663ba50fdaa817331e5`.
- [x] RC12 is sealed as a 144-file, 9,785,999-byte portable archive. Its stage
  and independent extraction each contain 102,439,224 file bytes, pass the full
  public/runtime closure, and reproduce deterministically. The authoritative
  sidecar records SHA-256
  `064b54dd437da50cb0829588204b7cbc22f333f81fd2076e05b7227ca7248dba`.
- [x] RC11 is sealed as a 144-file, 9,779,134-byte portable archive; the stage
  and independent extraction passed the full closure from an unrelated caller
  directory and reproduced byte-for-byte. Its authoritative sidecar records
  SHA-256
  `c0dd5c0461194f21ca36649fe10ada92e93c8f73f42ea3ab256316a76190001c`.
- [x] RC9 is sealed as a 136-file, 9,690,570-byte portable archive; the stage
  and independent extraction passed the full closure and deterministic
  re-archive check. RC8 remains sealed and unchanged; the authoritative
  sidecar records SHA-256
  `758bf0805f0c0f8e219fa6f945ae5df938c03b9854b5c94e2cc1e861cbe25184`.
- [x] RC8 remains sealed as a 135-file, 9,667,067-byte portable archive; its
  authoritative sidecar records SHA-256
  `17254d4030806e8636c67a9b90cfcee88a7711484d9ab6ef079aba875e569466`.
- [x] RC7 is sealed as a 134-file, 9,658,588-byte portable archive; the stage
  and independent extraction passed the full closure twice and the authoritative
  sidecar records SHA-256
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`.
- [x] RC6 is sealed as a 134-file, 9,643,071-byte portable archive; the stage
  and clean extraction passed the full closure twice and the authoritative
  sidecar records SHA-256
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.
- [x] The preserved RC5 checkpoint remains a sealed 134-file,
  9,639,953-byte portable archive assembled from the exact allowlist and passed
  the release/runtime/registry/desktop/bash/post-runtime gates with zero links.
  Its authoritative sidecar records SHA-256
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`.

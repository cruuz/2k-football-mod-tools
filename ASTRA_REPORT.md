# Beta 66.1 H3b: game-folder pass-fetch export

Branch: `astra/b661-apf2`. Base: `88a3b353` (H3 integrated).
Reporter: Urianus, triage row 24: “I don't know what a 'flat BASE' and a
'reconstructed 1.1 patch' are, but it doesn't like the game folder or 1.1 patch.”

The export now accepts the player's Xbox 360 game folder and installed
Title Update 1.1 content. The studio derives the executable in memory using
Python, applies the same complete-image identity gate as the expert PE route,
then exports and reparses the authored Xenia patch. No decoded game data is
written to disk. No calling heuristic, patch instruction or game pack changed.

## Implemented

- `mod_editor/core/xex_codec.py`: standard-library AES-128-CBC and bounded
  LZX decoding. No Java, compiler, subprocess, ctypes, native codec, Crypto or
  cryptography runtime dependency. AES tables are for public executable
  decoding, not a general-purpose secret-key cryptographic service.
- `mod_editor/core/apf2k8_xex.py`: bounded XEX2 header/file-format parsing;
  encrypted and unencrypted payloads; normal LZX, basic and uncompressed
  formats; SHA-1 block verification; the exact pinned 1.1 STFS/XEXP delta
  reconstruction; known-location content discovery; source provenance.
- The existing shipped STFS reader retains its roster rules. Only the exact
  SHA-pinned LIVE TU permits the research-proved parent-table status exception.
  Metadata, table and data SHA-1 checks are retained. RSA signature validation
  is explicitly false in the receipt.
- `apf2k8_playcall_patch.check_image` is the shared BASE/TU size and SHA gate.
  Refusals include the observed SHA/size and both accepted SHAs. Existing
  fetch-function hash, original hook, zero-filled cave reservation and
  Capstone checks remain in `compile_patch`.
- `write_patch` accepts a folder, executable or expert PE, optional
  `title_update` and `content_roots`. It still returns the existing patch
  receipt, now with input paths/hashes, derivation metadata and output path.
  Publication requires a separate `.patch.toml`, rejects aliases of its
  executable/update inputs, reparses every patch word and module hash, and
  atomically replaces only the authored output. Repeated exports are idempotent.
- The panel defaults to **Choose game folder** and retains **Choose flat
  image (expert)**. An optional **Choose Title Update 1.1…** accepts the
  installed `TU_…` file or extracted `default.xexp`; **Detect installed update**
  restores automatic detection. Flat mode does not double-apply a saved TU.
- Automatic discovery uses the studio's configured TU first, then known
  game/Xenia content layouts. Portable Xenia, Documents/Xenia (including Qt's
  Windows folder redirection), per-user data storage, relative/custom content
  roots and the Xbox-style zero-profile directory are covered. Conflicting
  discovered files, missing configured updates and unknown updates fail closed.
  There is no recursive disk scan. For arbitrary command-line/Wine overrides,
  select the installed update explicitly.
- Image preparation and patch publication use background workers. The save
  dialog opens only after successful verification and suggests a BASE/TU-specific
  file next to the last build, or next to the selected game folder. The footer
  reports the detected version, destination, cancellation or full refusal.
- The public pass-fetch document explains **What is a flat image**, normal
  player inputs and experiment limits. The alpha.87 changelog quotes Urianus.
  The capability fragment and model note describe the new input contract.
- The APF release allowlist includes both new modules. Protected runtime gate
  additions and the complete canonical capability replacement are in
  `WIRING.md`. `gui.py` already renders this panel on H3; no change is needed.

## PROVED

The local retail decoder and reconstruction tests ran successfully, without
an emulator, GUI display, audio, network or game-file writes.

| Item | Observed identity / checks |
|---|---|
| Original `default.xex` SHA-256 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Derived BASE SHA-256 | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| Derived image size | 54,001,664 bytes (`0x03380000`) |
| BASE compression | 642 SHA-1-verified blocks; 1,648 chunks; 37,717,546 LZX bytes |
| Compression window | Header `0x8000`, LZX window bits 15 |
| TU package SHA-256 | `5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b` |
| Extracted XEXP SHA-256 | `14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6` |
| Derived TU 1.1 SHA-256 | `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` |
| TU verification | 191 STFS data blocks; 12 SHA-1-verified delta blocks; 3,779 delta records |
| Export BASE / TU module selectors | `5447E5428AA2D52A` / `CEA825F7C2012F5A` |
| Existing authored cave verification | 179 decoded instructions; 34 checked branches; 716-byte cave |

The full BASE AES/LZX decode took **71.22 seconds** on this host in the retail
suite. The two retail tests, including TU reconstruction and both verified
exports, took **73.914 seconds**. Timing is a local measurement, not a platform
performance promise. Synthetic and offscreen suites run in roughly one second
or less each. All decrypted images stayed in memory; only small synthetic
fixtures and authored TOML outputs used temporary files.

The decoder follows the research extractor before import resolution:
`tools/xex_extract_pe.cpp`, the exact-size Java compatibility note in
`tools/xexloaderwv-java21/README.md`, and the BASE SHA/size gate in
`tools/apf_boot_indirect_frontier.py`. The local reference source for retail
key/AES conventions and frame/tree behavior was
`/home/noah/.codex-tmp/xenia-slot43-build/src/xenia/cpu/xex_module.cc` and its
`third_party/mspack/lzxd.c`. Runtime does not read these files.

The retail key is `20b185a59d28fdc340583fbb0896bf91`. AES unwraps the security
header's session key at `security+0x150` with a zero IV, then decrypts the
payload with that session key and a fresh zero IV. Each normal compressed
block begins with the next block's size/SHA-1, followed by big-endian chunk
lengths. Concatenated LZX uses little-endian 16-bit words, MSB-first codes,
32 KiB frames, persistent Huffman lengths and repeated offsets, aligned and
verbatim matches, raw blocks, and the optional E8 output transform. It does
not resolve or patch import ordinals. Synthetic tests include an independently
encrypted authored XEX2 container and an AES standard vector.

TU processing follows `tools/apf_playcall_audit.py::reconstruct_tu`: verify the
source signature digest, apply the bounded header deltas, verify the old/new
key relationship, decrypt and SHA-1-check delta blocks, and apply zero/copy/LZX
records. Each compressed record uses ordinary 15-bit LZX with a zero-padded
32 KiB source reference window; it is not the extended MS-PATCH LZX DELTA
stream variant. The final TU image must match its full pinned SHA. The
historical Xenia module selectors are retained; this job does not rerun the
research XXH3/import-thunk calculation.

## Tests and verification commands

Run from this worktree with `PYTHONPATH=.`. Qt ran offscreen. All test files
ran standalone with plain Python 3; no pytest is required.

| Command | Observed result |
|---|---|
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_xex_image.py` | Ran 17 tests; OK |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_pass_fetch_export_qt.py` | Ran 7 tests; OK |
| `PYTHONPATH=. python3 -u tests/mod_editor/test_apf_xex_image_retail.py` | Ran 2 tests; OK; both retail pins reproduced |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_playcall_patch.py` | Ran 11 tests; OK |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_cpu_audibles.py` | Ran 18 tests; OK |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_capability_action_parity.py` | Ran 11 tests; OK |

**66 tests passed.** A separate absent-retail run also verified the precise
skip path:

```bash
APF_RETAIL_XEX=/tmp/apf-h3b-deliberately-absent.xex PYTHONPATH=. \
  python3 tests/mod_editor/test_apf_xex_image_retail.py
```

Result: `Ran 0 tests; OK (skipped=1)` at class setup. `APF_RETAIL_XEX` and
`APF_RETAIL_TU` override the optional retail paths. A present but incorrect
retail XEX fails rather than being mislabeled as a missing-input skip.

Additional checks: isolated `python3 -I -S -B` imports/decodes from a minimal
temporary product namespace with site packages unavailable; unchanged release
text/structured-payload validators on the changed product/docs files; schema
validation of the complete registry with the replacement row merged in memory;
execution of the exact runtime-check function in `WIRING.md`; `git diff --check`;
and `python3 packaging/repin.py --apply` (0 pins needed updates).

## UNWITNESSED and integration limits

- Gameplay remains **UNWITNESSED**, EXPERIMENTAL and opt-in through export.
  This does not fix CPU third-and-long or guarantee a TE lineup. The patch
  affects offensive pass fetches at every down, including user calls. The
  main CPU weighted picker, later formation resolution and Subs retain their
  existing paths. No preset was enabled or patch installed automatically.
- No Windows/macOS packaged runtime or physical UI witness was performed.
  The offscreen tests cover the owned widget and its queued operations. The
  full main-window/staged release gate is an integration check after the
  protected registry/runtime changes in `WIRING.md`.
- Full registry file checking stops at an existing missing-evidence dependency,
  `docs/research/apf_audio.md` (`capabilities[0].evidence[0]`). Schema validation and all changed
  row evidence/backend paths are checked separately; no registry rule is relaxed.
- No title-update authenticity claim beyond the pinned whole-package SHA and
  extracted hashes; the RSA signature is not independently verified.
- `/` had 88 GiB available, below the handoff's 100 GiB threshold. No large
  output, game-folder copy, decoded-image file or disc build was created.

## Witness steps for Noah / Urianus

1. Open Playbooks → CPU Audibles & Personnel. Confirm **Choose game folder**
   is the default beside **Export TE bias for pass fetches…**, and the note
   explains reading/checking the game and writing a separate Xenia patch.
2. With a BASE installation and no configured/detected TU, export from the
   folder containing the original `default.xex`. Observe decryption/unpacking
   progress while the window remains responsive. The save dialog appears only
   after the check and suggests `54540807-base-pass-fetch-te.patch.toml` next
   to the build. Save, then confirm the footer reports retail BASE and the path.
3. Configure or select the installed 1.1 `TU_…` content, then repeat. Confirm
   the footer reports Title Update 1.1 and the suggested name contains
   `tu_1_1`. Test the Xenia Documents/content or portable/content location used
   on Urianus's machine. If the setup uses another Wine/CLI content root,
   select that installed content file explicitly.
4. Confirm exported TOML has `hash = "5447E5428AA2D52A"` for BASE or
   `hash = "CEA825F7C2012F5A"` for TU. Compare executable and update hashes
   before/after; they must be unchanged. Cancelling either dialog must leave
   no new patch file. Re-exporting identical input should preserve output.
5. Choose **Choose flat image (expert)** with an existing private matching
   `.pe` if available; it should export the same version/patch. Choose a wrong
   image and confirm refusal names its SHA plus both accepted SHAs, without
   opening the save dialog or replacing any earlier patch. Wrong/missing TU
   input must not silently export a BASE patch.
6. Install only the exported version matching the running Xenia module using
   the usual Xenia patch setup. Check that no other enabled patch owns
   `0x84D0E000..0x84D0EFFF`. Test the same book/personnel situation with the
   patch disabled and enabled, including user pass calls on multiple downs.
   Record game version, mode, book, formation/personnel, chosen pass play,
   substitutions, crashes/hangs and whether Xenia reports the patch applied.
   These observations are needed before changing gameplay status.
7. Remove the exported patch or set `is_enabled = false` to disable it.

CLI equivalent (writes only authored TOML; no need to create a `.pe`):

```bash
python3 -m mod_editor.core.apf2k8_playcall_patch \
  --game-folder '/path/to/All-Pro Football 2K8' \
  --title-update '/path/to/installed/TU_1A58207_0000008000000.0000000000082' \
  --output '/path/next-to-build/54540807-tu_1_1-pass-fetch-te.patch.toml'
```

Omit `--title-update` for automatic nearby-content detection or a BASE-only
installation. `--content-root` may name a custom Xenia content directory.

## Commit handoff

The normal explicit-path `git add` failed creating
`/home/noah/2k-football-mod-tools/.git/worktrees/astra-b661-apf2/index.lock`:
**Read-only file system**. The actual worktree branch ref therefore remains
at `88a3b353`. Isolated Git metadata under `/tmp` borrows the read-only object
store and records explicit-path commits on `astra/b661-apf2`. The first commit
is `93cbcc27` (decoder, panel and tests).

`ASTRA_H3B_COMMITS.bundle` carries the complete handoff above the H3 base.
It is a development handoff artifact, not a release asset. Untracked context,
briefing/triage files and the `extracted` retail symlink are excluded.

```bash
git fetch /absolute/path/to/ASTRA_H3B_COMMITS.bundle refs/heads/astra/b661-apf2
git cherry-pick 88a3b353..FETCH_HEAD
```

Then apply the complete protected-file blocks in `WIRING.md`, repin and run
the staged APF release/runtime gates before shipping.

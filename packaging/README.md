# 2K5 Mod Studio Linux packaging

These files provide the v1 zero-terminal launch surface. The desktop
entry invokes `2k5-mod-studio`, which is the installed name of
`tools/launch_2k5_mod_studio.sh`. The launcher finds a portable application
root through its own real path, checks Python/PyQt5/Pillow without opening a
terminal, starts `python3 -m mod_editor --studio`, and shows a desktop error
dialog if startup fails. Its diagnostic log is stored under the user's XDG
state directory.

Installers should place these files as follows:

| Source | Installed destination |
| --- | --- |
| `tools/launch_2k5_mod_studio.sh` | `/usr/bin/2k5-mod-studio` |
| `packaging/2k5-mod-studio.desktop` | `/usr/share/applications/2k5-mod-studio.desktop` |
| `packaging/2k5-mod-studio.svg` | `/usr/share/icons/hicolor/scalable/apps/2k5-mod-studio.svg` |

The application package depends on Python 3, PyQt5, and Pillow. On Debian/Linux
Mint those package names are normally `python3`, `python3-pyqt5`, and
`python3-pil`. A portable development build can instead symlink the launcher
into a directory on `PATH`; the launcher resolves that symlink back to the
application root.

## Local Windows CI

On Linux with Wine, run the Windows test-file matrix using the same SHA-256
pinned CPython 3.12.10, PyQt5 and Pillow as the installer:

```bash
python3 packaging/windows/local_windows_ci.py --os-check
python3 packaging/windows/local_windows_ci.py
python3 packaging/windows/local_windows_ci.py --only test_modpack.py
python3 packaging/windows/local_windows_ci.py --only 'test_apf_*' --only test_modpack.py -j 2
python3 packaging/windows/local_windows_ci.py --changed
python3 packaging/windows/local_windows_ci.py --hydrate-from ~/2k-football-mod-tools -j 2
python3 packaging/windows/local_windows_ci.py --hydrate-release -j 2
```

The first run calls the installer's unchanged `build_runtime`, downloading its
pinned interpreter and four wheels, then creates a dedicated headless Wine
prefix. The default cache is `~/.cache/2k-football-mod-tools/winci/`; use
`--work /tmp/winci` to move it. Building from already downloaded inputs measured
1.557 seconds here; download and first-prefix costs remain unmeasured. Cached
runs reuse the runtime and prefix. Host Python needs pip; curl, wine, wineboot
and winepath must be on PATH. An offline build can use cached files in `WORK/dl`
with `PIP_NO_INDEX=1 PIP_FIND_LINKS=/absolute/path/to/WORK/dl`.

`--repo DIR` tests another checkout. `--changed` uses the local merge-base with
`origin/main`, including committed, staged, unstaged and untracked changes;
it selects changed tests and tests whose source mentions a changed Python
module's filename stem. It never fetches. Combine it with `--only` to intersect
the selections. Unmatched `--only` patterns are errors. This is a text-based
selection heuristic, so run the full matrix before relying on coverage.

Lean checkouts need the gitignored catalog inputs. `--hydrate-from DIR` copies
regular files from `reports/`, `mod_editor/assets/`, `tools/vendor/` and
`docs/research/` in a separate sibling checkout. It fills only absent paths,
preserving existing files, tracked deletions and symlinks; source symlinks are
not followed. Every copied path and each tree's copied count are printed,
along with omission counts for existing/tracked files, links, obstructions
and VCS metadata. Missing source trees are reported. The beta-53 worktree's
evidence directories are symlinks; select the real source checkout instead.

Alternatively, `--hydrate-release` uses `gh release download` for CI's exact
two beta-50 archives from `cruuz/2k-football-mod-tools`, verifies both SHA-256
pins before copying, and fills absent archive paths with the same top-level
directory stripping as CI. It also protects tracked deletions and refuses
unsafe paths/nonregular archive members. Downloads are temporary; `gh` must
already be authenticated. The two hydration options are mutually exclusive.
For a snapshot without `.git`, existing paths are protected but there is no
index of tracked deletions. Neither option changes the source checkout.

The runner evaluates CI's exact `reports/assets/nfl2k5_all_txtr_inventory_v2.json`
file sentinel once, after hydration, on `--repo`. `WORK/logs/checkout.log`
records that decision and whether the inventory was already present. Release
hydration preserves existing inputs: it cannot make a previously hydrated
checkout lean. Use a fresh snapshot for CI-equivalent inputs and selection;
the exact command sequence is in [Follow-up 2](../ASTRA_WIN_LOCAL_CI_REPORT.md#follow-up-2).

Each file has a 420-second timeout (`--timeout SECS` overrides it), a full log
at `WORK/logs/test_name.py.log`, and the same PASS/FAIL and SUMMARY accounting
as CI. All selected files run even after failures; `--keep-going` explicitly
requests this default. File skips follow CI's exact lean-checkout evidence
rule and the observed Wine gaps documented in the report. Wine skips happen
after execution: every failure must match its reviewed filename, test case,
statement and exception signature. Logs with additional failures, missing
catalogs or timeouts remain failed. Skips print `SKIP name (Wine gap: reason)`
and count as skipped files, with their original logs retained. Setup failures
exit 2 without a success summary; test failures exit 1.
Timeouts print `TIMED OUT`, target the recorded Windows PID and descendants
with `taskkill /T /F`, and kill the Unix launcher's process group. The runner
flushes partial output chunks immediately and applies the same deadline when
a descendant retains stdout after the launcher exits. The runner
never kills a shared Wine server. A prefix must be empty or owned by this
runner; `--prefix DIR` chooses a separate one. Cache/prefix locks prevent
overlapping invocations from corrupting state or logs.

The default is `-j 1`. The beta-60 lean matrix completed at `-j 2` in
**20.3 minutes for 301 files**: 216 passed, 73 failed and 12 skipped (3,376
tests), versus GitHub's approximately 20–30 minutes per job. No failure log
shows cross-file prefix contention, so no speculative serialization was added.
The report classifies all 73 failures and records the limits of this comparison.
Qt windows
run offscreen, without DISPLAY or desktop/audio integration. `--os-check`
checks the actual Qt platform, prints Windows interpreter facts and the
pre-normalization CRT environment values, and proves normal versus isolated
child imports. The runner uses a private runtime copy for Python path setup;
the cached installer runtime and installer build output are unchanged.
The runner supplies `TEMP`, `TMP` and `TMPDIR` as `LOCALAPPDATA/Temp/winci`.
Wine resets `TEMP`/`TMP` from its registry; CPython honors the inherited
`TMPDIR`, placing test caches under the expected private profile root.

The later hydrated matrix measured 246 passed, 14 failed and 41 skipped in
28.0 minutes. Replaying its logs with the updated signatures and CI's lean
selection yields 242 passed, 3 failed and 56 skipped. Audio cleanup, an
unreported core failure before CopyFile2, and scorebug byte differences need
the test-side follow-up documented in the report. Conditional on resolving
those and unchanged other outcomes, the clean projection is 243 passed,
0 failed and 58 skipped for 301 files; this branch adds one runner test file.
These are replay/forecast numbers, not a new Wine acceptance run.

Wine can expose Windows CPython branches, binary I/O and Windows handle
sharing behavior. It does not certify native Windows filesystem, GUI, shell,
installer or driver behavior, nor the CI Python 3.11 matrix. The hosted job
also installs current dependencies, whereas this runner intentionally uses the
installer pins, whose embeddable runtime lacks Tkinter. Claude's external
acceptance run confirmed Windows imports and Qt offscreen, reproduced the
beta-60 WinError 5 on RED, and passed GREEN. This follow-up was validated with
pure tests and the supplied logs because Wine cannot run in its sandbox. See
[`ASTRA_WIN_LOCAL_CI_REPORT.md`](../ASTRA_WIN_LOCAL_CI_REPORT.md) for exact
acceptance results, the per-file classification and remaining validation.

## Application icons

`tools/make_app_icons.py` generates every icon both editors use, from geometry
rather than from an art file, and is deterministic: re-running it rewrites the
committed assets with the bytes they already had. Run it after changing any of
its constants, never edit its output by hand, and use `--check` to prove the
committed assets are current.

| Output | Used by |
| --- | --- |
| `packaging/<slug>.svg` | the Linux hicolor theme's scalable slot |
| `packaging/icons/<slug>.ico` | the window/taskbar icon at runtime, the NSIS installer chrome, and the Windows shortcuts |
| `packaging/icons/<slug>-<size>.png` | reference renders; not staged into a release |

16, 24 and 32 px are drawn separately rather than downscaled, and 16 px drops
the `K` because three glyphs cannot resolve in that width. The `.ico` carries
all of them, which is why it is what the app loads first.

The `.ico` is the only image either release ships. Both release gates pin it by
exact size and SHA-256 and re-check its image magic on every run, so regenerate
the pins from `tools/make_app_icons.py --print-pins` whenever the icon changes.


## Retail-free release gate

Never stage a release by copying the workspace. Create a new staging directory
from the explicit paths in `release-allowlist.txt`, then run:

```bash
python3 packaging/check_2k5_mod_studio_release.py /path/to/staged-release
python3 /path/to/staged-release/packaging/check_2k5_mod_studio_runtime.py
desktop-file-validate /path/to/staged-release/packaging/2k5-mod-studio.desktop
bash -n /path/to/staged-release/tools/launch_2k5_mod_studio.sh
python3 packaging/check_2k5_mod_studio_release.py /path/to/staged-release
```

The release gate refuses undeclared files, symlinks, hardlinks, special files,
world-writable files, binary or non-UTF-8 content other than the one pinned
application icon, known NFL 2K5 retail hashes
and container magic, retail/container/media extensions (including glTF/GLB),
either known private workstation home/mount prefix in staged text, and any path
under extracted, reports, assets, build, cache, originals, runtime, or other
local-data roots. Generic documentation examples such as `/opt/...` remain
valid. Ordinary product files have an 8 MiB ceiling.
Reviewed metadata may exceed that ceiling only at its exact pinned size.

RC29 carries forward the Audio replacement-pack confirmation boundary as
`AUDIO_REPLACEMENT_PREFLIGHT_CONTRACT=fully_validated_read_only_preview_then_explicit_apply`.
It also requires project-backed Audio cue annotations to remain
`project_metadata_only_stable_logical_cue_id`: custom titles/notes are
searchable and recoverable but never enter buildable XISO edit state.
The clean-stage checker requires the frozen sanitized preview-result fields,
repr-hidden opaque token, session mutation-revision/token API, facade and
service Preview/Apply signatures, GUI explicit-Apply handoff, and the service
ordering that reopens and revalidates the exact pack before its atomic batch
write. Its positive receipt is
`audio_pack_import=validated_preview_token_apply`. Preview, Cancel, and
unchanged-only paths publish no project edit or Undo action; an Apply token is
session-local and is never a retail-data or rollback container.

`reports/` has one narrow exception: the gate admits exactly fourteen size-,
SHA-256-, and schema-pinned JSON catalogs required by the current product.
They cover uniforms, Team Select cards, portraits, faces, create-team field
art, scorebug textures, and standalone-audio ownership. Four additional
reviewed snapshots live under `mod_editor/data/`: the compact 498-entry Crib
catalog, the sanitized Gameplay inspector data, the sanitized named Main Menu
inspector data, and the compact package-local uniform-equipment catalog.
All eighteen reviewed metadata files are pinned by the
same contract. They contain selectors, dimensions, offsets, hashes, ownership
labels, and constraints, but no compressed spans, decoded pixels, decoded
audio, replacement spans, or other retail payload bytes. An arbitrary report
or any changed byte in a reviewed catalog is refused.

The provider generates the 55,746,414-byte
`nfl2k5_resource_chunks_v2.json`, extracted archive packs, decoded originals,
and previews privately from the user's selected XISO after installation. None
of them belongs in the release stage or a shareable mod project. The runtime
closure check imports the source cache, all product catalogs, atomic build
service, session/project routes, resource scanner, unified backend, universal
fixed-text resolver, fixed-slot AUDO encoder, PLAY inspector, Crib bar-monitor
writer, fixed-range AUSB compiler, private audio-origin preparation boundary,
generalized Stadium P8 writer, complete Team Kit bundle service, and every
shipped Stadium Studio worker dependency from the clean stage. It opens the
reviewed catalogs and positively exercises retail-free Text, all three
fixed-allocation Audio routes, both editable Crib routes, extended visuals,
universal-resource browsing, scorebug replacement, the selected v2 Audio pack,
the canonical all-850 v3 metadata-only Audio pack, the mapped all-850 v4 Audio
pack with its exact retail-free cue-map binding, the fully validated read-only
Audio-pack preview followed by explicit token-bound Apply/revalidation,
synthetic PLAY parsing/filtering, the canonical standalone Audio-browser
pack-path lookup, and the exact 1/152/697 standalone-only meaning-confidence
domain; the default
54,421-row All Playable Audio inventory in its domain-prefixed order (850
standalone rows followed by 53,571 streaming ranges), excluding complete banks
and raw containers; bounded mixed matching export of 1–256 current WAVs with
per-row content-origin labels while raw mixed export is refused; the frozen v4
all-850 standalone replacement-pack boundary; the bounded 256-row Audio
all-matching shortlist contract, the scrollable Audio-detail/pinned-action
layout contract, the two-row 930-pixel Audio-toolbar contract, and Stadium
occurrence/dimension gates; verifies the selection/source-epoch-owned Audio
preview lifecycle excludes an unowned desktop-player fallback; exercises a
synthetic bounded read-only PCM16 waveform and proves its input bytes and
metadata stay unchanged; pins same-ID media invalidation and the shell's shared
rule that Audio and Crib workers are mutually exclusive while global
project/source/build/close actions wait for the owner to drain; pins the
source/search/filter applied-query token that fences debounced page-wide Audio
actions from stale results; pins exact-order one-level shortlist Clear undo and
transactional old-catalog recovery after a refused source load; checks the
twelve-section desktop launch signature; and proves the private inventory and
`extracted/` tree are absent. This clean-stage probe is synthetic and structural;
it neither opens a retail source nor claims that an authored cue was heard
in-game.

Stadium glTF scenes and PNG textures are never shipped. After a user loads a
recognized XISO, the shipped coordinator derives them under that user's
private SourceCache (`derived/stadium-studio-v1`) with resumable staging and an
atomic final publish. Generated `.gltf`, `.bin`, `.png`, manifests, archive
packs, and source XISOs must never be copied into a public stage or a shareable
project.

`release-allowlist.txt` intentionally lists the current v1 application and
writer closure one file at a time. When product code gains a new runtime
dependency, review it and add the exact path. Do not broaden the allowlist to
all of `mod_editor/` or `tools/`.

The runtime checker disables bytecode publication before importing product or
tool modules. The final repeated release check is still mandatory: it proves
the probe did not leave a cache, temporary output, private source artifact, or
any other undeclared file in the stage.

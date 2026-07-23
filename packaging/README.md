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
world-writable files, binary or non-UTF-8 content, known NFL 2K5 retail hashes
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

`reports/` has one narrow exception: the gate admits exactly eleven size-,
SHA-256-, and schema-pinned JSON catalogs required by the current product.
They cover uniforms, Team Select cards, portraits, faces, create-team field
art, scorebug textures, and standalone-audio ownership. Three additional
reviewed snapshots live under `mod_editor/data/`: the compact 498-entry Crib
catalog, the sanitized Gameplay inspector data, and the sanitized named Main
Menu inspector data. All fourteen reviewed metadata files are pinned by the
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
eleven-section desktop launch signature; and proves the private inventory and
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

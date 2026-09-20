# b74-v1 integration notes

The job explicitly asks for a working Build option, so its narrow BuildPlan,
source inspection, final output pass, preset, project-setting and Build panel
wiring is implemented directly in `mod_editor/core/mod_build.py`,
`mod_editor/core/nfl2k5_build_settings.py` and
`mod_editor/gui/build_panel_qt.py`. No Gameplay Patches option was added.

`packaging/repin.py --apply` refreshed only the existing source fingerprints in
`mod_editor/core/providers.py` and
`packaging/check_2k5_mod_studio_runtime.py`. It did not regenerate an XBE
reservation manifest or run a release.

Before packaging this feature, the integration owner must add this one runtime
file to the protected `packaging/release-allowlist.txt`, adjacent to the other
core movie/archive modules:

```text
mod_editor/core/nfl2k5_intro_videos.py
```

The read-only `tools/nfl2k5_movie_inventory.py` is a research utility requiring
FFprobe, not a runtime dependency of the Build option. It need not ship.

The protected `mod_editor/capabilities/registry.v1.json` needs one capability
row, adjacent to `nfl2k5.crib.movie_reclaim`, before packaging. The exact row
follows. Increase the shared registry count by one in its existing assertions
in `packaging/check_2k5_mod_studio_runtime.py` (two locations),
`tests/mod_editor/test_phase1_packaging.py`, the APF runtime check and
`tests/mod_editor/test_apf_studio_installer.py`. No registry or count was changed
in this job because the local context reserves them for integration.

```json
{
  "backend": {
    "command": "python3 -m mod_editor.core.nfl2k5_intro_videos rebuild source.iso output.iso",
    "module": "mod_editor/core/nfl2k5_intro_videos.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": ["ASTRA_B74_V1_REPORT.md", "tests/mod_editor/test_nfl2k5_intro_videos.py"],
  "game": "nfl2k5_xbox",
  "gui": {
    "default_enabled": false,
    "expose": true,
    "mode": "edit",
    "reason": "EXPERIMENTAL / UNWITNESSED. Build-only option; off in every preset."
  },
  "id": "nfl2k5.boot.intro_video_trim",
  "input_constraints": [
    "Pinned USA boot loop, table, shared player and four movie IDs, lengths and hashes; foreign or mixed states refuse.",
    "Separate output only; verifies every retained outer and unrelated named file before publication.",
    "Disc saving only has zero credit to the later GAMEDATA memory ceiling.",
    "Do not combine with Crib movie cut; current final-volume capacity is insufficient."
  ],
  "portme": ["Witness startup completion and later game presentation before claiming console acceptance."],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Ship source and recipes; never distribute generated game executables or discs.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": ["ASTRA_B74_V1_REPORT.md", "reports/b74-v1/native.json"],
    "scope": "Bounded native loader, boot-loop and failure execution only; decoder, GPU and whole game were not run.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [{"allowed": "false in every preset; explicit opt-in", "name": "trim_intro_videos", "required": true}],
    "notes": "Direct Build and saved-project wiring is implemented."
  },
  "source_container": {
    "format": "XBE and CRI Sofdec resources in XDVDFS",
    "hash_pins": ["73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"],
    "resource": "Boot loop and outer entries 4293 through 4296; streaming 16-pack archive shrink.",
    "retail_file": "User-owned ESPN NFL 2K5 USA disc image"
  },
  "summary": "Skip four startup movies and compact the output disc while preserving Crib reels, training and game presentation.",
  "surface": "build",
  "title": "Trim intro videos (experimental, unwitnessed)",
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_intro_videos.py"
}
```

The new owner uses no cave or allocator reservation. Its five-byte intentional
hook is VA `0x74BBB..0x74BC0`, replacing `be30974e00` with `e923000000`.
The unchanged current manifest reports no competing owner at that hook. The
32-owner composition check executes both application orders for the new patch.

As required by the job, `data/nfl2k5_cave_reservations.json` remains byte-identical.
Its pinned fingerprint of `mod_editor/core/mod_build.py` necessarily predates
this new Build option. The integration owner will need a fresh manifest when
integrating runtime source changes. Do not treat any stale-fingerprint gate as
passed, and do not hand-edit the fingerprint to conceal drift.

Git delivery uses independent metadata at `.scratch/b74-v1/git` because the
linked worktree's common Git directory is read-only. The commit's parent is
`origin/main` (`6944f5626b17f2ec6c1b56d854c0d00ecc55cc9e`). The incremental
`.scratch/b74-v1.bundle` can be fetched by its `b74-v1` ref in a checkout that
already has this base. The original worktree branch metadata is unchanged.

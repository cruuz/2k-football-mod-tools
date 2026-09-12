# T1 integration blocks

The one GUI function below is already edited in this delivery, as the brief permits.
The release allowlist/checker and new provider dependency entry below are integration
work for Claude. No other GUI panel or gameplay writer was edited. This is an
existing-feature performance/bug fix; no new capability or preset is introduced.

## Already applied: first-use Equipment navigation

File: `mod_editor/gui/studio_qt.py`, replace the complete
`StudioMainWindow._browse_selected_uniform_equipment` function with:

```python
    def _browse_selected_uniform_equipment(self) -> None:
        """Open the canonical visual browser on one set's equipment records."""

        uniform_set = self._selected_set
        if uniform_set is None:
            self._show_error(
                "Choose a physical uniform set before browsing its equipment."
            )
            return
        row = PRODUCT_CATEGORY_ORDER.index(ProductCategory.TEXTURES) + 1
        self._ensure_workspace(row)
        state = self._visual_browsers.get(ProductCategory.TEXTURES)
        if state is None:
            self._show_error("The All Textures browser is unavailable.")
            return

        state.group_filter.setCurrentIndex(0)
        state.search.setText(f"{uniform_set.selector} equipment")
        self._filter_visual_assets(ProductCategory.TEXTURES)
        if state.asset_list.count() != 45:
            self._show_error(
                f"Expected 45 equipment textures for {uniform_set.selector}, "
                f"but found {state.asset_list.count()}."
            )
            return

        self.navigation.setCurrentRow(row)
        self._set_status(
            f"Showing all 45 package-local equipment textures for "
            f"{uniform_set.selector}. Refine the search with socks, gloves, "
            "shoes, sleeves, pads, or wristbands; the existing Export, Edit, "
            "Replace, Revert, project, and Build paths remain in use."
        )

```

## Required release closure

Append these exact paths to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_compile_cache.py
tools/nfl2k5_equipment_optimal
tools/nfl2k5_equipment_optimal.c
```

Do not ship the benchmark tool, this report, tests, private cache directories,
benchmark projects or generated image outputs. `.nfl2k5-compile-cache` contains
private compiled game spans and previews. The session/shareable-project code
continues to export its explicit authored-file ledger, not that directory.

File: `mod_editor/core/providers.py`, `Nfl2k5UnifiedVisualProvider.module_pins` dependency digest
map (the map containing `mod_editor/core/nfl2k5_equipment_lz.py`): insert:

```python
        "mod_editor/core/nfl2k5_compile_cache.py": "4b9e9fc695b8e096cfc4e93e7dd511d43b9ea2455b004411fa1a66d615daca98",

```

The helper is optional. Its runtime gate pins the delivered Linux x86-64 binary
by size/hash, regular single-link file, safe permissions and executable bit,
then independently decodes every successful stream. Do not make the Linux
binary a required dependency on Windows/macOS. Those platforms retain Python;
there is no reviewed Windows/macOS helper in this delivery. The C source uses
binary standard I/O on Windows, but cross-platform compilation/execution is
UNWITNESSED. Build/review those binaries separately before adding runtime pins.

File: `packaging/check_2k5_mod_studio_release.py`, `audit_release`, immediately
before `suffix = path.suffix.casefold()` after the reviewed-icon branch, insert
this exact, path-specific exception. Keep the general suffix and binary refusals.

```python
        equipment_contracts = {
            "tools/nfl2k5_equipment_optimal": (16504, "949aad6a251de3f039f83bff15d4aa033183c250dbeadd1029e7c79dee4817c4"),
            "tools/nfl2k5_equipment_optimal.c": (4648, "6c9c7470d40ce3b99ac000fe75bd51c7d2fbeb44f783e313eb7b7dee0f0b8390"),
        }
        if relative in equipment_contracts:
            expected_size, expected_sha256 = equipment_contracts[relative]
            if info.st_size != expected_size:
                raise ReleaseCheckError(f"reviewed equipment helper size changed: {relative}")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != expected_sha256:
                raise ReleaseCheckError(f"reviewed equipment helper hash changed: {relative}")
            if relative == "tools/nfl2k5_equipment_optimal":
                if payload[:4] != b"\x7fELF":
                    raise ReleaseCheckError("reviewed equipment helper is not ELF")
                if os.name != "nt" and (info.st_mode & 0o777) != 0o755:
                    raise ReleaseCheckError("reviewed equipment helper must be mode 0755")
            else:
                payload.decode("utf-8")
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
```

The general regular-file, hardlink, symlink, permissions and allowlist checks
already precede this insertion. `packaging/stage_release.py` already preserves
executable files as 0755. Add release tests for wrong hash/size/mode and renamed
binaries when integrating the protected checker. The packaged release gate has
not been run with these proposed blocks installed.

## Pins and manifests

`python3 packaging/repin.py --apply` updates existing build-service, LZ and visual
tool pins in `mod_editor/core/providers.py`, plus the GUI source pin in
`packaging/check_2k5_mod_studio_runtime.py`. Those generated pin-only changes are
included. Re-run repin after wiring the new dependency or any integration edit.
Per the shared handoff, regenerate the cave manifest after integrating pinned
writers; T1 changes no XBE write site or cave reservation.

## Retail benchmark still required

The session sandbox makes `/media/noah/Storage` read-only. Creating
`/media/noah/Storage/.b68-t1` failed with `Read-only file system`; `/` has 82 GB
free, below the 100 GB floor. No retail image was built or copied.

In a writable Storage session, prepare the requested synthetic canonical
402-edit project with uniform, equipment, model and texture edits. Keep its PNGs
and recipes private. The runner takes this prepared project; it does not invent
or validate the representativeness of the edit mix. Supply the real private
pack-0 index and inventory paths explicitly:

```bash
git show c8783a64406ce6b062a7b287173ecbe778f43df2:tools/nfl2k5_visual_mod_project.py > /tmp/t1-baseline-tool.py
python3 tools/nfl2k5_b68_build_benchmark.py \
  --baseline-tool /tmp/t1-baseline-tool.py \
  --project /media/noah/Storage/.b68-t1/project-402.json \
  --index "$T1_PACK0" --inventory "$T1_INVENTORY" \
  --scratch /media/noah/Storage/.b68-t1 \
  --report /media/noah/Storage/.b68-t1/timings.json
```

The runner freezes inputs in scratch, runs baseline build+reconstructing verify,
then cold/warm/one-PNG-change build+receipt checks, hashes each whole output once
for comparison, and removes its temporary directory and discs. It requires 402
edits in real-disc mode and refuses to put real-disc scratch on `/`'s filesystem.
For a valid comparison use this T1 code against its base before integrating
other jobs' encoder changes. Re-test Coach Edwards' kit and maumau78's 402-edit
project in their Windows environment; the timing target is not yet certified.

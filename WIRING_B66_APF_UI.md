# Beta 66 job C: APF UI integration wiring

This section is the current job C handoff. The older material below the historical separator predates this branch and is not a new request from this job. No protected file was edited.

## Registry row and matching action binding

In `mod_editor/capabilities/registry.v1.json`, insert this object in `capabilities` immediately before `apf2k8.logos_cards.team_logo`, preserving the required alphabetical ID order. Validate it with `python3 mod_editor/capabilities/validate_registry.py`. This branch has no separate registry checksum file. Existing family rows stay authoritative for their writer contracts.

```json
{
  "backend": {
    "command": "APF Studio > Logos & Team Art > Team Art > Replace",
    "module": "mod_editor/apf_studio/team_art.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "docs/mod_editor/apf2k8_team_art_browser.md",
    "tests/mod_editor/test_apf_team_art.py",
    "tests/mod_editor/test_apf_team_art_qt.py",
    "tests/mod_editor/test_apf_theme_layout_qt.py"
  ],
  "game": "apf2k8_xbox360",
  "gui": {
    "default_enabled": true,
    "expose": true,
    "mode": "edit",
    "reason": "A rendered Team Art workspace under Logos & Team Art, also linked from Field Art and Uniforms. Progressive worker thumbnails, exact layer inspector, paired PNG replacement and per-package Revert use the normal project transaction."
  },
  "id": "apf2k8.logos_cards.team_art_browser",
  "input_constraints": [
    "Use the selected read-only retail APF source. Resolve package names against archive filename CRCs and inner layers by semantic names.",
    "All 118 crests, 118 endzones, 206 wordmarks and 24 packages each of jerseys, shoulders, pants and digits are reachable. Only the proved 24 retail crest and wordmark selector assignments acquire team labels; tentative endzone labels retain question marks.",
    "Crests require separate 512x512 logo_l0 and logo_l1 PNGs for six region masks; the existing crest builder also updates the corresponding uniform_logocache index. Never mirror one layer into both.",
    "Every selected endzone layer is required. Single-layer packages require one PNG; paired packages require both. Wordmarks, jerseys, shoulders and pants use their exact existing color-layer contract. Digit subsets share a combined allocation preflight.",
    "The existing family writers and build verifiers retain mip regeneration, compression, fixed-allocation and decode-back checks. All package layers stage or revert as one Undo action. Authored PNGs and numeric recipes enter projects; retail payloads do not.",
    "Thumbnails and staged image decoding run in workers. Source-scoped, decoder-versioned PNG caches include both crest image hashes and stay private."
  ],
  "portme": [
    "Witness changed non-retail crest art and its linked Team Select cache, paired endzones, wordmarks and uniform art in game.",
    "Retail endzone selector ownership remains unproved; the retail-use filter excludes unproved assignments."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Distribute tooling, structural pins, and user-authored PNGs only; each user rebuilds a copied game from their own retail source.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [
      "docs/mod_editor/apf2k8_team_art_browser.md"
    ],
    "scope": "Offline package counts, source identity resolution, six-mask pairing, existing writer dispatch, private thumbnail cache behavior, project transaction rollback and Qt interactions are tested. Changed art consumption remains in-game UNWITNESSED.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [
      {
        "allowed": "logo|endzone|textlogo|jersey|shoulder|pants|number",
        "name": "family",
        "required": true
      },
      {
        "allowed": "a source-resolved outer entry with named supported texture layers",
        "name": "outer_entry",
        "required": true
      }
    ],
    "notes": "The browser resolves the family catalog index, outer entry, inner indices and linked crest cache catalog identity together. Built-in team selector assignments seed retail labels; the other library slots remain entry-labeled."
  },
  "source_container": {
    "format": "Source-resolved APF H7A/IFF texture packages and linked uniform_logocache",
    "hash_pins": [
      "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
      "39a1e0c944a846e24d7a11c52d6a0fbba4091959f01856d3a087efde01ba490c"
    ],
    "resource": "All 118 crest and 118 endzone packages, 206 wordmarks and all jersey/shoulder/pants/digit packages in retail 0A; existing family writers own source pins and fixed allocations.",
    "retail_file": "All-Pro Football 2K8 (USA)/0A"
  },
  "summary": "Browse every crest, endzone, wordmark, jersey, shoulder, pants and digit package by decoded thumbnails; resolve named layers and stage or revert paired artwork as one project action.",
  "surface": "logos_cards",
  "title": "APF visual Team Art package browser",
  "validation_command": "PYTHONPATH=. python3 tests/mod_editor/test_apf_team_art.py"
}
```

In `mod_editor/apf_studio/models.py`, insert the following entry into `CAPABILITY_ACTION_BINDINGS` immediately after `apf2k8.logos_cards.textlogo_wordmarks`, in the same integration change as the registry row. This owned file is deliberately deferred with the protected row so standalone registry/action parity remains green before integration. Both facade methods already exist and are rendered by `TeamArtBrowser`.

```python
    "apf2k8.logos_cards.team_art_browser": CapabilityActionBinding(
        "apf2k8.logos_cards.team_art_browser",
        "logos_cards.team_art_browser",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_team_art",
        revert_method="revert_team_art",
        product_note=(
            "Browse every source-resolved Team Art package. Paired crest/endzone "
            "PNGs retain their semantic layers and stage as one Undo action. "
            "Existing build writers regenerate mips, enforce allocations and "
            "verify decode-back; changed art remains in-game UNWITNESSED."
        ),
    ),
```

## Runtime capability counts and the protected installer assertion

In `packaging/check_apf2k8_mod_studio_runtime.py`, `_check_static_product_contract`, replace the existing registry/card count checks with:

```python
    require(
        len(registry.capabilities) == 143
        and len(registry.for_game(core_model.GameId.APF2K8)) == 54,
        "shared/APF capability registry counts changed",
    )
    cards = catalog.build_capability_cards()
    require(len(cards) == 54 and len({item.capability_id for item in cards}) == 54,
            "APF capability surface is not exactly 54 unique rows")
```

In the same function's `expected_editable` set, insert immediately before `"apf2k8.logos_cards.team_logo",`:

```python
        "apf2k8.logos_cards.team_art_browser",
```

In the protected `tests/mod_editor/test_apf_studio_installer.py`, `ReleaseClosureTests`' existing runtime-source assertion, change exactly:

```python
        self.assertIn("len(registry.capabilities) == 143", runtime)
```

This updates the exact expected count for the one added row; no assertion or gate is removed. These counts assume this job's row is the only registry addition. Combine the count deltas if other beta-66 jobs add capabilities.

## Optional private-source runtime gate: stale starting-branch inventory counts

The public runtime/installer gate above is exercised by this job. The separate `--source` path in `_check_private_source` still contains older inventory expectations from the starting branch (408 uniform records and 37 capabilities). Live metadata on this branch is 10,464 total assets, 302 uniform/wordmark targets, **888 Uniforms inventory records** (`TXTR: 851`, `NumberFont: 24`, `NameFont: 11`, `SCNE: 2`), and 53 APF capabilities before this job's new registry row, 54 afterward. `Stride_number_field` now correctly belongs to Field Art, which restores its 258-row ownership map.

For that optional gate, replace the uniform inventory count with 888, its type dictionary with the values above, and the capability count with 54. The subsequent mapping must resolve the 302 typed uniform/wordmark targets against **all** catalog TXTR coordinates, because wordmarks belong to Logos & Team Art. Only 96 of those targets are in the Uniforms inventory; its additional inventory is therefore 792 rows (`TXTR: 755`, `NumberFont: 24`, `NameFont: 11`, `SCNE: 2`). This older optional gate was not used to claim verification here; the new live inventory tests and both screenshot audits cover the source metadata directly. If integrating its repair, preserve its exact identity, type and target checks.

## Reviewed label metadata pins

`packaging/check_apf2k8_mod_studio_release.py`, `REVIEWED_METADATA`: replace the existing `mod_editor/data/apf2k8_endzone_labels.v1.json` tuple with the following three tuples (the other two are new adjacent entries). `packaging/repin.py --apply` reports zero changes because this metadata uses `(size, hash, schema)` tuples, not one of that script's supported pin shapes.

```python
    "mod_editor/data/apf2k8_endzone_labels.v1.json": (
        7_714,
        "b873910626d63bf476d55e12253047f88758124697216e9439689dfe5e7e8618",
        "apf2k8_endzone_labels/v1",
    ),
    "mod_editor/data/apf2k8_logo_labels.v1.json": (
        5_811,
        "a3a033f1528e50ee9fff831e7b20f0ceabb3e235b86c7859930cf89a6b32a5a2",
        "apf2k8_logo_labels/v1",
    ),
    "mod_editor/data/apf2k8_textlogo_labels.v1.json": (
        5_904,
        "79f0b6855e25cef7097bf689dde039970a81b25fd5f97faf3973cffbe95db60e",
        "apf2k8_textlogo_labels/v1",
    ),
```

The unmodified protected gate refuses the changed endzone JSON, so the raw checkout's installer lifecycle suite cannot pass until this wiring is applied. The review copy under `/tmp/b66-apf-ui/integration` exercises these exact pin changes without editing protected working-tree files. No release audit or installer test has been weakened.

## Runtime import closure

In the module-name tuple in `packaging/check_apf2k8_mod_studio_runtime.py`, immediately after `"mod_editor.apf_studio.gui",`, add:

```python
    "mod_editor.apf_studio.apf_theme",
    "mod_editor.apf_studio.page_layout",
    "mod_editor.apf_studio.team_art",
    "mod_editor.apf_studio.team_art_qt",
```

`packaging/apf2k8-release-allowlist.txt` already includes these four runtime modules and the two new label JSON files. The protected general `packaging/release-allowlist.txt` and `packaging/check_*.py` remain unchanged. The new screenshot/audit tools are development-only and need no release entry. No additional GUI route patch is required.

Run the registry validator, `tests/mod_editor/test_apf_capability_action_parity.py`, `tests/mod_editor/test_apf_studio_installer.py`, and the APF runtime/release gates after integration. Bump the shared product version to alpha.86 through the release owner's normal workflow; this job adds the requested alpha.86 changelog section without changing shared release identity files.

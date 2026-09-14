# J9 integration wiring, beta 69

The APF widgets and writers are implemented and tested on this branch. The three
new capability cards below must land with their bindings. The existing CPU Play
Calling entry already reaches the controls; this handoff does not claim that
three new cards are registered before Claude applies these protected edits.

Add **3** rows: shared **161 → 164**, APF **69 → 72** for J9 alone. Other jobs'
additions must be aggregated. The existing `scheme_presets` row describes older
book seeding; retain it. These new schemes are a team Play Calling operation.
No additional sidebar category. No runtime-proved promotion.

1. In `mod_editor/capabilities/registry.v1.json`, append these complete rows to
`capabilities`, sort by `id`, and serialize with the existing canonical sorted,
indented JSON convention. Identical machine-readable rows are in
`docs/research/apf_b69_registry_rows.json` for the merge test.

```json
[
  {
    "backend": {
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --output <new-folder>",
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b69_schemes.md",
      "ASTRA_REPORT.md",
      "tests/mod_editor/test_apf_b69_schemes.py",
      "tests/mod_editor/test_apf_b69_editor_qt.py",
      "tests/mod_editor/test_apf_b69_build.py",
      "tests/mod_editor/test_apf_b69_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "Explicit review in the existing CPU Play Calling tab; options start off. The integrated real writers, reparse, project replay, Undo and copied build are tested. Gameplay UNWITNESSED."
    },
    "id": "apf2k8.playbooks.offensive_schemes",
    "input_constraints": [
      "User-owned loaded APF archive with named SPLB, MASTER and ROST resources; no retail bytes enter project recipes.",
      "Preview has the beta-67 cold, empty-history/null-player boundary; saved USER books and global merges need a game witness.",
      "Eight interpretations authored from general football knowledge without network research; category and formation rating effects are coupled through existing records.",
      "Twenty-two situation bytes feed an optional tendency cache; only the overall run tendency is a direct team slider in the ordinary preview. No tempo, snap-count, weather-ratio or coin-toss policy is authored.",
      "Shared book is cloned for the selected team; aliased team tendency pointers are refused. Reapplying adds deltas again."
    ],
    "portme": [
      "Run the named 7ET/Urianus witness steps in ASTRA_REPORT.md before promoting any runtime claim."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "All in-game outcomes UNWITNESSED. Offline real-writer and bounded native execution prove only the explicitly reported input states.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [
        {
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "name": "team_and_book",
          "required": true
        },
        {
          "allowed": "air_coryell, erhardt_perkins, west_coast, west_coast_spread, spread_to_run, wide_zone, power_gap, pro_spread",
          "name": "scheme",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Apply one of eight authored schemes to a team with a reviewed private-book plan, current-book personnel preferences, ratings and ROST tendencies; preview, Undo and copied Build. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "Offensive schemes (ADVANCED)",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b69_schemes"
  },
  {
    "backend": {
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --spreadsheet-team <0..23> --output <new.csv>",
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "operation": "export"
    },
    "classification": "extract-only",
    "evidence": [
      "docs/mod_editor/apf_b69_schemes.md",
      "ASTRA_REPORT.md",
      "tests/mod_editor/test_apf_b69_schemes.py",
      "tests/mod_editor/test_apf_b69_editor_qt.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "export",
      "reason": "Export play call spreadsheet in CPU Play Calling writes UTF-8 CSV of the current staged offense. It is a planning aid with explicit proxy rows and probability limits."
    },
    "id": "apf2k8.playbooks.scheme_spreadsheet",
    "input_constraints": [
      "User-owned loaded APF archive with named SPLB, MASTER and ROST resources; no retail bytes enter project recipes.",
      "Preview has the beta-67 cold, empty-history/null-player boundary; saved USER books and global merges need a game witness.",
      "Openers and sudden change share the ordinary down/distance row; four red-zone bands have no independent rows. 2pt is only a scrimmage proxy; special calls and history are not predicted.",
      "No scripted sequence is installed; requested pick counts and run-by-row intent remain planning annotations."
    ],
    "portme": [
      "Run the named 7ET/Urianus witness steps in ASTRA_REPORT.md before promoting any runtime claim."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "All in-game outcomes UNWITNESSED. Offline real-writer and bounded native execution prove only the explicitly reported input states.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [
        {
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "name": "team_and_book",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Export the staged offensive book as CSV in all 23 coaching buckets, with actual model probabilities, representative engine rows and separate coaching-intent run percentages.",
    "surface": "scripts_config",
    "title": "Play call spreadsheet",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b69_schemes"
  },
  {
    "backend": {
      "command": "python3 -m mod_editor.apf_studio.playcalling_service --game-folder <folder> --project <project.apf2k8mod> --output <new-folder>",
      "module": "mod_editor/apf_studio/playcalling_service.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b69_schemes.md",
      "ASTRA_REPORT.md",
      "tests/mod_editor/test_apf_b69_formation_calling.py",
      "tests/mod_editor/test_apf_b69_editor_qt.py",
      "tests/mod_editor/test_apf_b69_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "Explicit review in the existing CPU Play Calling tab; options start off. The integrated real writers, reparse, project replay, Undo and copied build are tested. Gameplay UNWITNESSED."
    },
    "id": "apf2k8.playbooks.never_call",
    "input_constraints": [
      "User-owned loaded APF archive with named SPLB, MASTER and ROST resources; no retail bytes enter project recipes.",
      "Preview has the beta-67 cold, empty-history/null-player boundary; saved USER books and global merges need a game witness.",
      "Formation IDs 0..150 only; all duplicate records change together. Every affected category must retain another nonretired member.",
      "Only B membership changes. Original masks are saved in the authored recipe for restore; stale or malformed restore requests are refused.",
      "Special records 151..162 remain protected: native Hail Mary constructor cache and post-predicate selection bypass B=0. No universal CPU retirement claim."
    ],
    "portme": [
      "Run the named 7ET/Urianus witness steps in ASTRA_REPORT.md before promoting any runtime claim."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "All in-game outcomes UNWITNESSED. Offline real-writer and bounded native execution prove only the explicitly reported input states.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [
        {
          "allowed": "24 retail teams; named offense/defense books, including stock, USER and global donors",
          "name": "team_and_book",
          "required": true
        },
        {
          "allowed": "ordinary formation IDs 0..150 with remaining category coverage",
          "name": "formation",
          "required": true
        }
      ],
      "notes": "The facade stages one authored recipe containing ordered, undoable edit receipts; the copied-game builder applies it after existing asset edits."
    },
    "source_container": {
      "format": "APF SPLB, MASTER PLAY and ROST; authored Xenia TOML for patches",
      "hash_pins": [],
      "resource": "Team book assignments, named books and MASTER personnel",
      "retail_file": "User-owned All-Pro Football 2K8 (USA) extracted game folder"
    },
    "summary": "Reversibly clear all B membership masks for an ordinary formation without deleting plays or compacting records; cached special formations remain protected. Gameplay UNWITNESSED.",
    "surface": "scripts_config",
    "title": "Never call (ordinary CPU lottery)",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b69_formation_calling"
  }
]
```

2. In `mod_editor/apf_studio/models.py`, at the opening dictionary comprehension
in `CAPABILITY_ACTION_BINDINGS`, replace its feature tuple with:

```python
for feature in ("cpu_playcalling", "own_team_books", "master_personnel",
                "offensive_schemes", "never_call")
```

Immediately after that comprehension's closing `},`, insert:

```python
"apf2k8.playbooks.scheme_spreadsheet": CapabilityActionBinding(
    "apf2k8.playbooks.scheme_spreadsheet",
    "playbooks.cpu_playcalling",
    _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    product_note=(
        "CPU Play Calling exports the current staged offense through "
        "ApfStudioFacade.playcalling_scheme_csv. Twenty-three coaching buckets "
        "map to representative engine rows; intent and predicted calls remain "
        "separate. Gameplay UNWITNESSED."
    ),
),
```

No new GUI handler is necessary: `playbooks.cpu_playcalling` opens the existing
tab, including the Scheme and Never call controls. New write cards use the
existing reviewed `stage_playcalling` / `revert` facade closure; the export
button calls `playcalling_scheme_csv` in a worker and writes verified CSV.

3. Refresh the existing registry rows without changing their counts. Apply the
following Python to the parsed registry object `data` before canonical save:

```python
by_id = {row["id"]: row for row in data["capabilities"]}
row = by_id["apf2k8.playbooks.master_personnel"]
row["summary"] = (
    "Edit shared category rows and eleven roles, including 5-2:Big on row 13. "
    "Native matching offense row 3 selects added 5-2 after moving it from row 12; "
    "the beta-69 UI recognizes the actual category name. Gameplay UNWITNESSED."
)
row["evidence"] += ["tests/mod_editor/test_apf_b69_native.py",
                    "tests/mod_editor/test_apf_b69_editor_qt.py", "ASTRA_REPORT.md"]
row["runtime"]["scope"] = (
    "UNWITNESSED in game. Pinned BASE native defensive driver, offense category "
    "3 (row 3), requests row 13. Added 5-2 row 12: 0/128; row 13: 63/128. "
    "Synthetic seed states and a bounded caller, not a live game."
)
row = by_id["apf2k8.playbooks.pass_fetch_te_bias"]
row["gui"]["reason"] = (
    "Install a reviewed canonical BASE or TU 1.1 pass-fetch patch. Studio launch "
    "copies only its managed patches into the actual --storage_root/patches "
    "folder with readback and honors the reviewed setting through an explicit "
    "--apply_patches=true/false argument. Restart after changes. "
    "Last-resort subtype fetch only; gameplay UNWITNESSED."
)
row["input_constraints"][3] = (
    "Installation accepts only a canonical BASE/TU pass-fetch payload. Consent "
    "sets the selected config's Memory.apply_patches; Studio launch forwards it "
    "as a CLI flag for Xenia builds which register this cvar under General. "
    "Other enabled patches in that launch storage can also become active."
)
row["input_constraints"][4] = (
    "Removal deletes the canonical managed file; the next Studio launch removes "
    "its stale managed copy from that build's storage. Unrelated patches and the "
    "shared apply_patches setting are preserved. External Xenia launches need "
    "the exact logged storage_root/patches path and enabled cvar."
)
row["evidence"] += ["tests/mod_editor/test_apf_b69_launch_patches.py", "ASTRA_REPORT.md"]
```

4. Append the following to `packaging/apf2k8-release-allowlist.txt` adjacent to
the beta-67 Play Calling module/doc entries. The shared 2K5 payload does not
import these new APF modules, so `packaging/release-allowlist.txt` needs no J9
payload entry.

```text
mod_editor/core/apf2k8_offensive_schemes.py
mod_editor/core/apf2k8_formation_calling.py
docs/mod_editor/apf_b69_schemes.md
```

Add these exact imports in `packaging/check_apf2k8_mod_studio_runtime.py`'s
`PRODUCT_MODULES` tuple adjacent to `mod_editor.core.apf2k8_team_tendency`:

```python
"mod_editor.core.apf2k8_offensive_schemes",
"mod_editor.core.apf2k8_formation_calling",
```

Add these exact IDs to `expected_editable` in that file:

```python
'apf2k8.playbooks.offensive_schemes',
'apf2k8.playbooks.never_call',
```

`scheme_spreadsheet` is Export-only, not Editable. Existing editable IDs remain.
The packaging gate's module total is computed dynamically (+2).

5. For J9 alone, make these literal count updates; aggregate other jobs before
editing final numbers. Do not change unrelated counts that happen to equal 69.

| File | Exact context | Replacement |
|---|---|---|
| `packaging/check_2k5_mod_studio_runtime.py` | `len(registry.capabilities) == 161` | `== 164` |
| same | `registry=161 sections=12 nfl2k5_capabilities=91` | `registry=164 sections=12 nfl2k5_capabilities=91` |
| `tests/mod_editor/test_phase1_packaging.py` | assertion for that full summary string | same 164 substitution |
| `packaging/check_apf2k8_mod_studio_runtime.py` | registry count 161; `for_game(...APF2K8)` count 69 | 164; 72 |
| same | `len(cards) == 69` and unique ID count 69 | both 72 |
| same | `APF capability surface is not exactly 69 unique rows` | 72 |
| `tests/mod_editor/test_apf_studio_installer.py` | asserted `len(registry.capabilities) == 161` source text | 164 |

6. Run the proposed-row/binding test before integration, then the real registry,
capability parity and both packaging runtime gates after the protected merge:

```sh
PYTHONPATH=. python3 tests/mod_editor/test_apf_b69_wiring.py
python3 mod_editor/capabilities/validate_registry.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_apf_capability_action_parity.py
python3 packaging/repin.py --apply
```

Run the runtime gates with the release's usual arguments and inputs. They are
integration checks, not claimed run in this isolated J9 handoff. J9's module,
writer, native, Qt and launch checks are recorded in `ASTRA_REPORT.md`.

Git metadata for this worktree is outside its writable roots. The actual
`.git` add/commit was rejected as permission denied; this is an environment
write restriction, not an approval request. Explicit-path commits were made
using isolated metadata in `/tmp`, with the same base and branch. Import the
root `ASTRA_B69_J9.bundle` into the hub, then cherry-pick its commits. The bundle
contains only authored files and has the original base as a prerequisite.

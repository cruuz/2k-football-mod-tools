# Beta 69 J8 integration

The live APF page, transfer dialog, services, capability/action binding, docs
and tests are implemented. No GUI wiring is deferred. Protected registry and
release files remain unchanged, as requested. No commit here contains a save,
retail payload, private roster, or console signing material.

## Registry rows and counts

**Update two existing rows; add zero rows.** These are extensions of the
existing custom-team appearance and PS3 roster import capabilities, not new
capability IDs. Counts remain **161 total, 69 APF, 91 NFL2K5 Xbox, 1 NFL2K5 PS2**
before other jobs' additions. J8's delta is **+0** for every count. Do not
increment any pinned counts for this job. Integrator must include the other
jobs' deltas in `packaging/check_2k5_mod_studio_runtime.py` (both count sites),
`packaging/check_apf2k8_mod_studio_runtime.py` (registry/APF/card sites),
`tests/mod_editor/test_phase1_packaging.py` and
`tests/mod_editor/test_apf_studio_installer.py`.

Apply this exact by-ID update to `mod_editor/capabilities/registry.v1.json`.
The existing disc writer/backend and all earlier appearance constraints remain.
The new one-shot service is already bound in `mod_editor/apf_studio/models.py`
to `mod_editor.apf_studio.roster_appearance_transfer:write_transfer` alongside
the existing Stage/Revert facade routes. Both capabilities retain their
existing IDs and rendering routes. The transfer and Xenia-package choices are
EXPERIMENTAL, explicit actions, off in every preset; no automatic build/save
patch is introduced. The existing appearance editor remains available.

```python
import json
from pathlib import Path

path = Path("mod_editor/capabilities/registry.v1.json")
registry = json.loads(path.read_text(encoding="utf-8"))
rows = {row["id"]: row for row in registry["capabilities"]}
appearance = rows["apf2k8.colors.uniform_selector_appearance_custom_team"]
appearance["input_constraints"] = [
    value for value in appearance["input_constraints"]
    if not value.startswith("CON, LIVE, and PIRS STFS packages are inspect-only")
]
appearance["input_constraints"].extend([
    "Apply my custom team appearance to this roster save transfers current controls and optional other staged appearances by matching slots 32..39. The destination team names are reviewed; each slot authorizes only 112 bytes. Outputs and receipts are new files, and source hashes must still match at write time.",
    "Raw Roster.ROS output is supported. Decrypted PS3 USERDATA or one bounded roster ZIP member passes through the existing converter with all team uniform codes and palette colours carried first; only selected slots then receive the bounded editor appearance. The receipt includes conversion and override verification.",
    "Supported fixed-size, single-file CON/LIVE/PIRS packages can produce a separate rehashed STFS copy only through the explicit Xenia-only output choice. Caption: Xenia only; a real console will reject this package. Changed data blocks, active hash-table blocks and the metadata hash are rehashed; signature bytes are preserved, never renewed. The pinned local Xenia source does not check RSA signatures, but package discovery and full loading remain HYPOTHESIS and UNWITNESSED.",
    "STFS output refuses invalid hashes, shared file/directory blocks, file chains incompatible with Xenia traversal, multi-file packages, changed payload sizes and unsupported hash-tree bounds. The raw handoff route remains available for otherwise extractable packages.",
    "The editor overlay does not copy jersey/shoulder/pants selectors or artwork from the project; destination values remain exact. PS3 conversion independently carries all 14 selectors in both banks and rotates RGBA to ARGB. Texture artwork needs its separate import.",
])
appearance["gui"]["reason"] += (
    " Beta 69: Custom Team Appearance now exposes Apply my custom team appearance to this roster save. "
    "It reviews destination slots, defaults to a new raw output, and optionally creates a Xenia-only "
    "rehashed package. Current controls remain intact and output is reopened with a changed-slot receipt."
)
appearance["summary"] += (
    " Apply current/staged custom-team appearance to a new raw roster, converted PS3 roster, or "
    "explicit Xenia-only rehashed STFS copy; offline verified, in-game UNWITNESSED."
)
appearance["evidence"].extend([
    "docs/research/apf_stfs_rehash.md",
    "tests/mod_editor/test_apf_stfs_roster_rehash.py",
    "tests/mod_editor/test_apf_roster_appearance_transfer.py",
    "tests/mod_editor/test_apf_roster_appearance_transfer_qt.py",
])
ps3 = rows["apf2k8.players_rosters.ps3_roster_import"]
ps3["gui"]["reason"] = (
    "PS3 import reviews uniform carry or Xbox appearance retention. Exact 14-record HOME/AWAY "
    "selector banks, ten colours per bank and palette metadata are compared after conversion. "
    "Receipts name carried/refused fields. Aszemple witnessed RPCS3 logo and roster imports on "
    "2026-09-13; uniform rendering and in-game loading remain UNWITNESSED."
)
ps3["runtime"]["scope"] = (
    "Aszemple: Was able import both the logos and roster files from my rpcs3 files (2026-09-13). "
    "This witnesses import usability only. In-game roster loading, HOME/AWAY uniform rendering "
    "and the helmet close-up remain UNWITNESSED."
)
ps3["runtime"]["status"] = "not-tested"
ps3["input_constraints"].append(
    "All 40 teams' 1120 referenced eight-byte selectors and 800 referenced colours are compared "
    "after conversion, including jersey, shoulder, pants, helmet and crest. Opaque tails remain "
    "exact; custom texture payloads and new meanings for opaque bytes are refused with reasons. "
    "Choosing a new source clears the previous Xbox appearance baseline."
)
ps3["evidence"].extend([
    "tests/mod_editor/test_apf_ps3_roster_convert.py",
    "tests/mod_editor/test_apf_ps3_roster_import_qt.py",
])
for row in (appearance, ps3):
    row["evidence"] = sorted(set(row["evidence"]))
path.write_bytes((json.dumps(registry, indent=2, sort_keys=True) + "\n").encode("utf-8"))
```

## Packaging

Add these exact paths beside the save-appearance modules/tool in
`packaging/apf2k8-release-allowlist.txt` and in the combined
`packaging/release-allowlist.txt` when it includes the APF studio:

```text
mod_editor/apf_studio/roster_appearance_transfer.py
mod_editor/apf_studio/roster_appearance_transfer_qt.py
tools/apf_stfs_roster_rehash.py
docs/research/apf_stfs_rehash.md
```

In `packaging/check_apf2k8_mod_studio_runtime.py`, `PRODUCT_MODULES`, insert
after `"mod_editor.apf_studio.save_appearance",`:

```python
    "mod_editor.apf_studio.roster_appearance_transfer",
    "mod_editor.apf_studio.roster_appearance_transfer_qt",
```

In its `TOOL_MODULES`, next to the existing save/STFS tools, insert:

```python
    "apf_stfs_roster_rehash",
```

In `_check_static_product_contract` (the function containing the existing save
appearance checks), directly after those checks, add:

```python
    transfer = modules["mod_editor.apf_studio.roster_appearance_transfer"]
    transfer_qt = modules["mod_editor.apf_studio.roster_appearance_transfer_qt"]
    rehash = importlib.import_module("apf_stfs_roster_rehash")
    require(
        transfer.SCHEMA == "apf2k8_roster_appearance_transfer/v1"
        and callable(transfer.inspect_transfer_source)
        and callable(transfer.write_transfer)
        and callable(transfer.verify_transfer)
        and hasattr(transfer_qt, "RosterAppearanceTransferDialog")
        and rehash.SCHEMA == "apf2k8_stfs_roster_rehash/v1"
        and callable(rehash.rehash_roster)
        and callable(rehash.verify_rehash)
        and rehash.XENIA_ONLY == "Xenia only; a real console will reject this package",
        "Roster appearance transfer/Xenia-only rehash contract changed",
    )
```

Run the staged runtime/allowlist gates after merging. `repin.py --apply` is
required after integration if any pins change. It reports zero changed pins
for the J8 changes on this branch; the command was run before commits.

## J7 FAQ coordination

No J7 FAQ exists on this branch. The getting-started guide contains a short
“Can I create a formation or play?” section under APF wave authoring, with 7ET's
question and the complete answer. J7 can reuse that section in its FAQ.

## Commit bundle required for this handoff

The shared worktree metadata became read-only after commit `5a9a2e14`:
`/home/noah/2k-football-mod-tools/.git/worktrees/astra-b69-j8/index.lock`
cannot be created. Both staging attempts failed before changing any source
file. The later commits were created with explicit paths in a writable
temporary Git store using this same worktree. No protected metadata permissions
were changed. The original branch ref still points at `5a9a2e14`.

The complete three-commit series is in this bundle, based on `922c009d`:

```text
reports/b69_j8/astra-b69-j8-apf-save.bundle
```

From the writable integration checkout, import it without any network:

```sh
git fetch /home/noah/2k-worktrees/astra-b69-j8/reports/b69_j8/astra-b69-j8-apf-save.bundle refs/heads/astra/b69-j8-apf-save:refs/remotes/handoff/b69-j8
git cherry-pick 922c009d65e35f8195762c31106789bb353fb43c..refs/remotes/handoff/b69-j8
```

If `5a9a2e14` is already integrated, cherry-pick the range starting at
`5a9a2e14035c9e431ded855ea78e632f5b4fcfa2` instead of `922c009d`. The next
implementation commit is `a9d2879e`; the final commit adds the report and
validation logs. The bundle is exported after that final commit, so it is
delivered beside the logs and is not committed into itself. Its contents are
code/docs/synthetic-test receipts, with the existing base as a prerequisite.

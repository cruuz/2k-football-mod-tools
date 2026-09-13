# Beta 69 J8: APF appearance to roster saves

Branch: `astra/b69-j8-apf-save`. Job context: `ASTRA_CONTEXT.md`, beta-69 triage
row 20, hub beta-68 APF reactions rows 10–12. No emulator, GUI display, audio,
network, push, or real-console signing was used. All newly added fixtures are
synthetic and generated in temporary directories. Private inputs used by
pre-existing gated regression tests were read-only; no save or retail payload
was added to the repository.

## Delivered behavior

Custom Team Appearance has **Apply my custom team appearance to this roster
save…** in both game/project and raw-save modes. It captures the current
HOME/AWAY controls before inspecting the destination, so choosing a roster
does not replace the appearance the user wants to apply. The dialog shows
destination team names, occupied/empty state and slot mapping; optionally
includes other staged user-team appearances; defaults to a new raw Xbox
`Roster.ROS`; and offers an explicitly labeled Xenia-only STFS copy when that
package passes the narrower writer checks.

The service uses the existing disc-writer appearance value/schema and existing
raw-save writer. It resolves the destination's pointer graph and writes only
ten ARGB dwords and two eight-byte helmet/crest selectors in each HOME/AWAY
bank: **112 authorized bytes per selected slot, slots 32–39 only**. Palette
metadata, other uniform selector records, players and other slots remain
unchanged. The source hash is checked before writing and again on readback.
Output and receipt are exclusively created at separate paths; existing files
are refused, and a failed write/verification removes only files this operation
created. The verifier reparses the actual output, checks the full allowed-byte
set and reports **the slots that actually changed**.

PS3 raw `USERDATA`, PS3-layout `.ROS`, and the bounded selected member of a
roster ZIP pass through the existing converter before the overlay. Its full
conversion receipt is nested beside the appearance-patch receipt. For STFS,
the package receipt additionally verifies allocation, hashes and unchanged
signature bytes. These are private output receipts, never project payloads.

The APF capability/action binding now names the actual one-shot service
alongside the existing Stage/Revert methods. **Two existing capability rows
are updated in WIRING; zero rows are added.** The live GUI needs no additional
wiring. Registry metadata and release allowlists remain the integrator's
protected edits, with exact code and paths in `WIRING.md`. Counts remain 161
total / 69 APF for J8 alone. Classification: EXPERIMENTAL explicit transfer
actions, off in every preset; additional staged slots and package output both
start off. Existing PS3 appearance-review checkbox still starts off.

## Format findings and proof boundary

**PROVED offline:** raw-save appearance bytes match the disc writer's bounded
contract, every written raw output reparses, PS3 conversion carries exact
uniform selector banks with RGBA→ARGB colour rotation, and synthetic STFS
replacement repairs the complete affected active SHA-1 chain. See
`docs/research/apf_stfs_rehash.md` for the offset table, equations, source pins
and tests.

STFS metadata/header: magic at 0, signature/certificate storage at
`0x004..0x22B`, licenses at `0x22C..0x32B`, metadata digest at `0x32C..0x33F`,
header size at `0x340`, and metadata beginning at `0x344`. The metadata SHA-1
covers `[0x344, round_up(header_size, 4096))`. The volume descriptor starts at
`0x379`; its top-table digest is at `0x381`. The writer preserves signature,
license, ownership and other metadata bytes. It requires APF title `54540807`,
saved-game content type 1, and single-file STFS metadata.

STFS data and tables: 4096-byte blocks; 170 entries per table, 24 bytes per
entry (20-byte SHA-1 and state/next pointer). Changed data-block digests update
their active leaf table; changed leaf tables update active parent digests;
the top-table digest updates the descriptor; the metadata digest is last.
Inactive copies, data-block tail padding, unselected data, file sizes and
chains are preserved. The independent verifier checks all allocated active
data entries and every active leaf table, and rejects any extra mutation even
outside hashed regions. Two-copy geometry previously doubled accumulated
data offsets after block 170; the single-copy higher-level calculation also
used the wrong intermediate value near its boundary. Both are corrected.

The package writer refuses shared file/directory blocks, corrupt hashes,
sparse or out-of-order directories, incompatible next-pointer chains,
changed roster length, multi-file containers, non-APF save metadata and
unsupported hash-tree bounds. Exactly 170/28900 allocated blocks are refused
for package output because the audited Xenia level-selection boundary differs.
Extractable packages retain the raw route. No scans for embedded roster magic
or packed resources were introduced.

**PROVED from pinned local source:** Xenia revision
`d09cae8d8374324048ef603d48a9c1696b39d552`,
`xcontent_container_device.cc::ReadHeaderAndVerify` at line 182, checks length,
successful header read and magic, with **no RSA or metadata digest check**.
`stfs_container_device.cc::Read/ReadEntry` consumes directory and next-pointer
entries without comparing SHA-1. Its traversal follows next pointers even for
contiguous files. The existing repository `synthetic_stfs` fixture originally
marked every block end-of-chain; it now generates real chains and saved-game
metadata. That known synthetic package round-trips through the writer,
production extractor and a separate Python translation of the pinned Xenia
block/chain algorithm, for single/duplicate tables, both active copies, and
fragmented files. The optional source-pin test ran successfully here.

**HYPOTHESIS:** discovery and full loading of the modified package by a user's
Xenia build. The Python traversal model is not native Xenia execution. There
was no actual emulator or game load, and no console RSA signature was produced.
The caption therefore explicitly says **“Xenia only; a real console will reject
this package”**, and calls full loading HYPOTHESIS/UNWITNESSED. Signature-check
absence is proved only for the pinned source, not every Xenia version.

**Every in-game outcome is UNWITNESSED:** roster load/save/reload, correct team
selection, HOME/AWAY rendering, jersey/shoulder appearance, and helmet close-up.
An offline receipt is not a runtime witness.

## PS3 appearance findings

The prior converter already carried the PS3 selector bytes by preserving the
table and already rotated palette colours. This job does not pretend that
transport was missing. The new check compares **all 40 teams' 1120 referenced
eight-byte selector records, 800 referenced colour values, and palette
metadata** after conversion. All 2660 colours in the palette table continue
to receive the converter's existing rotation. Receipts include exact full
selector before/after bytes, named carried fields, and refusals with reasons.

Carried: both 14-record banks, including helmet/crest/jersey/shoulder/pants
codes and opaque tails; colour values in Xbox byte order; palette metadata.
Refused: custom texture payload import (use PS3 bundle/Team Art), and new
semantic labels for opaque selector bytes (the bytes still survive exactly).
If the user selects an Xbox appearance baseline, the receipt explicitly says
PS3 appearance values were declined because the user chose that baseline.
Choosing another PS3 source clears the previous baseline and requires review
again, preventing accidental retention of an unrelated roster's uniforms.

The editor overlay still copies only the bounded colours and helmet/crest
selectors. It does not copy jersey/shoulder/pants choices from the project.
Those existing destination codes, including PS3 codes just converted, stay
exact. This scope matters for davidhbui's workaround.

## Aszemple's steps and requested witnesses

Aszemple: “Next is how do I get the uniforms codes applied that I've already
done from in the APF editor and on my rosters.” His earlier ask: “could the
editor take a .Ros file or PS3 roster file and update the uniforms and players”.

1. Open the project with your appearance, go to **Uniforms & Equipment → Custom
   Team Appearance**, select the slot and review both banks. Existing staged
   values load normally; current un-staged controls can also be transferred.
2. Click **Apply my custom team appearance to this roster save…** and choose
   your raw roster, STFS package or decrypted PS3 roster/ZIP. Review the listed
   destination names: slot 32 means user team 24, through slot 39/user team 31.
   The match is by slot number, never an inferred name match.
3. Tick **Also apply other staged user-team appearances** only if wanted.
   Leave raw output selected, or explicitly choose the **Xenia only; a real
   console will reject this package** option for a supported STFS source.
4. Write to a new filename and retain its `.appearance.json`. The status and
   receipt list changed slots. For PS3, the receipt also lists converted fields
   and the final editor override. Existing source/project data is preserved.
5. For raw output, back up a game-created roster save and place the new output
   as `Roster.ROS` in that save's folder under the configured Xenia content
   root. Find the existing `54540807/00000001/<save name>/` path; some builds
   include a profile folder above the title ID. For STFS, use the existing
   package-save workflow with the new copy. This workflow's full load is still
   a requested witness, not a claim that discovery is proved.
6. Witness load, accepted team identity, HOME and AWAY, jersey/shoulder
   colours, helmet and crest close-up, then save/reload persistence. Include
   Xenia build/version, raw versus STFS route, slot/team and receipt with any
   failure. For STFS also report whether the package was discovered at all.

For a PS3 import without an editor override: choose the decrypted roster in
**Import PS3 roster**, tick **Also apply team appearance (40 teams)**, then
import to a new raw file. Leaving the option off intentionally uses the chosen
Xbox roster's appearance. Artwork uses its separate import.

davidhbui: “pick an in-game asset that fit my art, switch to that one in game,
save, and then copy that uniform into my roster in the editor”. The destination's
saved jersey/shoulder selectors survive this bounded overlay, and PS3 carry
tests give both banks distinct codes/tails to verify they are not discarded.

Aszemple's September 13 witness: “Was able import both the logos and roster
files from my rpcs3 files”. That confirms import usability only. The helmet
close-up, uniform rendering and in-game roster loading are still owed.

## 7ET's answer

7ET: “Read the release notes, but unclear whether we can create play in the
2k8 editor?” The getting-started guide now explicitly answers yes: **Playbooks
→ Design Plays / Formations → Design Formation… / Design Play…** provides
Create formation and Create play. Off by default, CPU books only, offline
validated, every in-game result UNWITNESSED. Beta-67 CPU Play Calling controls
which existing plays get called; it is not the authoring page. No J7 FAQ exists
on this branch, so the guide has the requested short question/answer section.

## Validation

Every command below ran standalone with
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 <path>`. Complete output is in
`reports/b69_j8/<test filename stem>.log`; `test-results.json` lists counts and
exit codes. Final result: **16 files, 117 tests, all suites OK, one pre-existing
skip** for missing gitignored extract-xiso release binaries in Studio core.
The optional private-input regression and local Xenia-source pin checks ran;
new tests use synthetic inputs only.

| Test path | Tests | Result |
|---|---:|---|
| `tests/test_apf_save_custom_team_appearance.py` | 12 | OK |
| `tests/test_apf_save_playbook_assignments.py` | 10 | OK |
| `tests/mod_editor/test_apf_stfs_roster_rehash.py` | 7 | OK |
| `tests/mod_editor/test_apf_roster_appearance_transfer.py` | 5 | OK |
| `tests/mod_editor/test_apf_roster_appearance_transfer_qt.py` | 3 | OK |
| `tests/mod_editor/test_apf_ps3_roster_convert.py` | 13 | OK |
| `tests/mod_editor/test_apf_ps3_roster_import_qt.py` | 3 | OK |
| `tests/mod_editor/test_apf_b66_appearance.py` | 3 | OK |
| `tests/mod_editor/test_apf_custom_team_appearance_patch.py` | 8 | OK |
| `tests/mod_editor/test_apf_custom_team_appearance_gui.py` | 5 | OK |
| `tests/mod_editor/test_apf_save_roster_players.py` | 7 | OK |
| `tests/mod_editor/test_apf_save_roster_players_gui.py` | 4 | OK |
| `tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | 8 | OK |
| `tests/mod_editor/test_apf_capability_action_parity.py` | 11 | OK |
| `tests/mod_editor/test_apf_studio_core.py` | 9 | OK, skipped=1 |
| `tests/mod_editor/test_apf_ps3_probes.py` | 9 | OK |

The WIRING registry-update code was applied to a temporary registry and passed
`validate_data(check_files=False)`: `WIRING_REGISTRY_SCHEMA_PASS total=161 APF=69
updated_rows=2 added_rows=0`. No protected file was mutated for that check.
`git diff --check` passed. `python3 packaging/repin.py --apply` reported
`applied 0 pin update(s)` before commits. Full staged release gates remain for
the integrator after the protected allowlist/registry edits.

## Commits and integration

- `5a9a2e14`: bounded STFS rehash, extractor geometry repair, source/format audit,
  synthetic fixture and round-trip tests.
- `a9d2879e`: studio transfer, PS3 carry verification, final STFS guards and
  the getting-started/changelog updates.
- The final report commit contains this report, `WIRING.md` and the test logs.

**Git metadata restriction:** the first commit landed normally. At the next
commit, two attempts to stage files failed with `Unable to create
/home/noah/2k-football-mod-tools/.git/worktrees/astra-b69-j8/index.lock:
Read-only file system`. The workspace files stayed writable. No permissions
were escalated and no other checkout was edited. The remaining explicit-path
commits were created under the same branch name in a temporary writable Git
metadata store, reusing the existing objects read-only and this same worktree.
They are delivered in `reports/b69_j8/astra-b69-j8-apf-save.bundle`, including
all three J8 commits above base `922c009d65e35f8195762c31106789bb353fb43c`.
The normal worktree branch ref consequently remains at `5a9a2e14`; it must not
be mistaken for the full delivery. Fetch/cherry-pick the bundle using the
instructions in WIRING. The bundle is a separate local deliverable, not a
self-containing file in its own commit.

Follow `WIRING.md` for the two existing registry-row updates, four new release
paths and runtime imports/checks. There is no gameplay/runtime proof upgrade,
no console resigning, and no preset enabled by this job. No source disc was
built or copied; no cleanup of private inputs is required.

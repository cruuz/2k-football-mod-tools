# Beta 66 job E: APF gameplay/data

Branch: `astra/b66-apf-gameplay`. Implementation commit: `402334d9`, followed by
the final receipts, guidance and evidence commit. No push, emulator, GUI display,
audio or network operation was performed. Retail inputs were read-only. No
retail roster, PE, volume or decoded image is committed.

**Implementation and research are delivered; release integration is pending.**
`gui.py` and protected packaging/registry files are untouched. `WIRING.md` gives
exact insertion points/code for job C and the packager. The full standalone APF
set is **not all green** in this checkout: 169/194 pass; 25 fail for the reasons
below. All ten modified/new test suites pass independently in the final focused
run. The user-requested all-suite-green condition remains unmet.

## Results and proof boundaries

| Item | PROVED | HYPOTHESIS / unfinished integration |
| --- | --- | --- |
| 26, Ulf the White | Fine-tune moves normalize destination primary category and replace old word B. Newly cloned Design CPU rows clear donor secondary bits. Receipts include old/new personnel and donor membership. Retail census: 209 rows, 127 formations; 171 moves reparse, 38 refused by the existing last-supply guard. | Actual CPU personnel is UNWITNESSED. Retail contradicts a universal one-category function: formations 72/78/120 have valid alternatives, and 37 untouched records have multi-bit B. |
| 27, Aszemple | Source selectors were already transported. Explicit graph verification, both-bank/per-team receipts, checkbox review and optional Xbox-appearance retention are now implemented. PS3/Xbox table layouts match in the supplied files; 40 teams and 1,120 selector references reparse. Synthetic test keeps a differing PS3 player identity while retaining Xbox appearance. | Roster load/uniform rendering is UNWITNESSED. Custom texture payloads are separate imports. Already-Xbox .ROS is not a PS3 conversion input. |
| 28, Aszemple | All 206 pinned wordmarks have exactly one `textlogo_color` TXTR, RGB BC1, 512x128, six mips. Deterministic three-channel permutations are implemented/tested. | Six-region encoding and exact team palette-slot binding are unproved. The editor must not promise either. The new channel-order control awaits C's GUI hook. |
| 29 §4, davidhbui | New `apf_field_material_writer.py`, portable scalar recipes, Undo/Revert, independent Qt panel and normal Build composition. Eleven material alphas in all four retail scenes reparse/refit; five overlays at 0.25 grow each block by 32 bytes, leaving 868/992/346/65 bytes. Draw-table names and shared material 2 are reparsed. | Rendering is UNWITNESSED. Field Art page, capability registration and package allowlist await the exact WIRING additions. ADVANCED, off by default. |
| 31, Urianus Magnus Ursulinus / Aszemple | DT/Possession bits, getters, table/dispatcher and two DT scoring consumers are identified. Unique normalized TU matches are recorded. | Snap/release-animation causal site remains unidentified. The proved branches change evaluation scores, not an isolated animation request. No animation-only patch is justified or exported. |

The full evidence, addresses, exception sets, pointer layout, channel limitations,
and exact DT branch behavior are in
[`docs/research/apf_b66_gameplay_data.md`](docs/research/apf_b66_gameplay_data.md).
Machine-readable receipts are in
[`reports/apf_b66_gameplay_witness.json`](reports/apf_b66_gameplay_witness.json).
The tool verified the full retail 0A SHA-256 before and after; unchanged:
`dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`.

Two triage assumptions were disproved, not silently encoded as facts: retail
formation->category is not universally single-valued, and the PS3 converter did
not previously discard team selectors. The fixes address actual stale word-B
membership and explicit appearance verification/review.

## Validation

Each test file ran in its own plain `python3` process with
`PYTHONPATH=<repo> QT_QPA_PLATFORM=offscreen`. No pytest collection or emulator.
Final focused run: **10/10 suites, 158 tests, passing (one existing skip)**:

```text
tests/mod_editor/test_apf_play_designer.py
tests/mod_editor/test_apf_ps3_roster_import_qt.py
tests/mod_editor/test_apf_splb_add_multiple_formations.py
tests/mod_editor/test_apf_splb_formation_personnel.py
tests/mod_editor/test_apf_splb_tag_reassignment.py
tests/mod_editor/test_apf_b66_appearance.py
tests/mod_editor/test_apf_b66_personnel.py
tests/mod_editor/test_apf_field_material_project.py
tests/mod_editor/test_apf_field_material_writer.py
tests/mod_editor/test_apf_wordmark_regions.py
```

The broader run includes every `tests/**/test_apf*.py` and every
`tests/apf*_test.py`: **194 suites; 169 pass, 25 fail**. The Studio subset is
**133/135 passing**. Exact paths, exit codes, timings and failure tails are in
[`reports/apf_b66_standalone_suites.json`](reports/apf_b66_standalone_suites.json).
That file also records the later focused rerun after final changes.

- Studio failures: `test_apf_product_findings.py` lacks the ignored, hash-pinned
  `reports/assets/apf_digital_font_layout.json` authority (the next expected
  authority is the font roundtrip receipt). `test_apf_studio_installer.py`
  exposes the pending protected allowlist addition and missing Capstone in its
  isolated runtime. These checks were not bypassed or edited.
- The 23 legacy root-suite failures involve absent family-layout/sample/selector/
  scene/provenance authorities, canonical-inventory hash expectations, source
  paths rejecting the supplied `extracted` symlink, an existing standalone
  `apf_inner` import-path failure, and existing immutable uniform-spec hash drift.
  The checked-in uniform spec and its checker were not changed. Xenia-named
  tests exercised metadata parsers and mocked launchers only.
- Initial local fixture setup restored the ignored extractor tools and building
  note from the existing beta-65 release stage, restored the pinned scorebug
  audit from the local RC62 build, and generated a read-only uniform inventory
  to let the logo ownership tests run. No such fixture is committed. That
  generated inventory's path/sample metadata is not the canonical legacy
  authority, so its consumers correctly refuse the old pin; it was not repinned.
- A temporary release stage containing the unchanged allowlist plus the three
  new field modules **passes** `APF2K8_MOD_STUDIO_RUNTIME_PASS modules=133
  capabilities=53` when its declared local Capstone dependency is explicitly on
  PYTHONPATH. An initial stage without that dependency correctly refused. This
  tests the package additions, not C's future hooks or the new registry row.
- `python3 packaging/repin.py --apply` was run after APF writer changes and before
  commits; final output `applied 0 pin update(s)`. The H7A optimal binary remains
  mode 0755. `git diff --check` passes.

Restore canonical private/ignored evidence and merge the protected handoff before
claiming the release-wide gate is green. Do not regenerate immutable authorities
with new pins merely to silence these failures.

## Noah's witness script

First reproduce the offline proofs from the current worktree. The report output
must be new; this command creates metadata only, not a disc or game patch:

```bash
PYTHONPATH=. python3 tools/apf_b66_gameplay_witness.py \
  --index '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' \
  --ps3 '/home/noah/Downloads/1993 NFL Season (Update Logos).zip' \
  --xbox-roster '/home/noah/Downloads/apfe/Roster.ROS' \
  --base-pe '/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe' \
  --tu-pe '/tmp/astra-audit-tu-v2.pe' \
  --report /tmp/noah-b66-gameplay-witness.json
```

Expected: `26_personnel reparsed`, `28_wordmarks reparsed`,
`29_field_materials reparsed`, a receipt with 171 accepted moves / 38 supply
refusals, 206 texture reparses, matching PS3/Xbox layout, four field refits,
unchanged 0A hash, and `patch_exported: false` for DT. PE arguments refer to
existing decompressed research inputs; no XEX payload is emitted.

After Claude integrates WIRING into C's GUI and packages it, use a copied game
and user-owned hardware for these runtime checks:

1. **Ulf / CPU personnel:** load retail; Fine-tune Plays, select a named book
   with at least two reachable Jacks records (use the receipt to choose an
   accepted outer/record). Move I Jacks (formation 9) to Singleback Quads (69).
   Confirm Flush category 8, word B 0x1 -> 0x100, not 0x101; save/reopen/build.
   Leave the supply guard active if another choice would strand Jacks. In the
   game force the CPU to call that formation and an audible; identify actual
   players by jersey/position, not only alignment. Expected Quads package:
   1 RB / 0 TE / 4 WR. Compare stock, edited, and edited+Subs cases separately.
   Also witness a new Design CPU row cloned from a multi-membership donor.
2. **Aszemple / roster appearance:** Saves -> Import PS3 roster, load the 1993
   USERDATA/ZIP. Confirm the 40-team checkbox starts off and explains review.
   Select the Xbox roster to retain appearance and export to a new .ROS.
   Repeat to another new .ROS with the checkbox checked. Review every team's
   before/after selector receipt. Load each roster; compare the same teams in
   both uniform banks, including jersey, shoulder, numbers, crest, wordmark,
   pants and helmet. Players should follow PS3 in both outputs. Use separately
   imported texture files where custom indices refer to custom art.
3. **Aszemple / wordmark:** author three separated solid R/G/B regions on black;
   choose identity, then swap R/G. Confirm the prepared preview changes exactly
   those regions, build and compare the same wordmark on hardware. Record which
   visible team colours each channel selects; repeat after changing one palette
   slot at a time before claiming any palette-slot mapping. Do not label this
   six-colour support.
4. **davidhbui / field opacity:** Field Art -> Field overlay opacity. Select one
   of the four scenes; tick only overlays 4/5/7/8/9 and set 25%. Keep grass and
   chalk unchecked. Stage, save/reopen, Undo/Revert/restage; combine with a field
   texture change and Build. Inspect the receipt for both composed edits. On
   hardware compare the same stadium/weather/camera and confirm the centre
   graphics fade while grass remains unchanged. Repeat all four scenes. If
   changing ticks, remember material 2 also affects some chalk draws.
5. **Urianus / DT research:** no optional patch is supplied. Use the same receiver,
   formation, route, alignment, coverage and normal ratings in repeated captures
   with no ability, Possession, and DT. Then repeat the zero-stat experiment as
   a separate condition. Record platform and title update. Capture frame-by-frame
   release and intended deep-receiver benefits before any animation-only fix is
   attempted; the existing PS3 observation is not proved by an Xbox PE branch.

All runtime effects above remain UNWITNESSED until these comparisons are made.

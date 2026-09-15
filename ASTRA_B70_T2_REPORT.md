# Beta 70 T2: equipment fit, normal/mud staging and stadium banners

2026-09-15. Branch: `astra/b70-t2-equipment-socks-banners`.
Base: `df9b9dcfbdc8e192e6edd37c4b8e5385bec92024`.

## Delivery and release boundary

The interrupted session's edits were preserved, read and completed within the
granted owners. Equipment imports now report their measured fit and stage normal
and existing mud siblings atomically. Stadium selectors identify the actual
venue/time/weather package; writer receipts identify the occurrence written.
Arm-placement help, the model research note, FAQ and reporter-quoted beta-70
changelog bullets are included.

**Apply [WIRING.md](WIRING.md) before release.** It contains the exact protected
integration for project-row captions, verified build summaries, restored-project
fit metadata, arm-family import action, compatibility entry points, allowlist and
existing registry claims. The granted facade already uses the new staging owner.
The project/build captions and arm action are tested as supplied snippets, but
their protected call sites have deliberately not been edited. The changelog
describes the integrated result and must not be shipped ahead of that wiring.

**No larger-equipment switch ships. Archive relocation remains UNPROVED. Every
in-game outcome of these changes is UNWITNESSED.** These are corrections to
existing import capabilities, with no new preset or capability row; registry
count delta is zero. No XBE patch or cave reservation was added. Claude should
regenerate the shared cave manifest after integration per ASTRA_CONTEXT.md.

The shared Git directory rejected `index.lock` as read-only. Explicit-path
commits are held in `.scratch/t2.git` and delivered in
[.scratch/ASTRA_T2.bundle](.scratch/ASTRA_T2.bundle), using the authorized fallback:

- `d3dbd401`: preserve authored equipment colours and stage normal/mud atomically.
- `a535e05e`: native traces, exact fit/occurrence reporting, tests and evidence.
- The final documentation commit adds this report and finishes registry wiring.

The bundle contains this branch's commits after the stated base. The shared
worktree index therefore still reports the changes as uncommitted; no original
edits were discarded. Task inputs and the `extracted` symlink are excluded.

## 1. Socks: measured quality and fixed-span proof

Coach Edwards: “these sock textures are still distorted”; carried report:
“designer socks ... still coming through blurry in game.” His photo has smeared
patterned socks beside more legible cleats. His actual source PNG is unavailable.
The second measured design below is an authored reconstruction of that kind of
art, **not his image or a reproduction of the reported failure**.

The old quantizer was already art-derived, not a fixed ramp. Small palettes used
frequency/farthest-colour selection; larger reductions could be influenced by
the combined mip histogram. The replacement uses weighted median cut of the
actual base artwork, chooses authored colours as representatives, and maps pixels
without dithering. An already representable base remains exact; filtered mip
colours use the remaining entries. A conservative detector recognizes repeated
coherent high-contrast bands. Their fit ladder never tries a palette limit below
16; an overflowing import offers the existing explicit, measured smaller-size
retry. No automatic acceptance of a destructive two-colour stripe fit occurs.

`_compile_group` changes are limited to palette selection, the stripe floor,
retry colour count and measured receipt fields. T1 must retain its search-order,
cache and Windows helper changes when integrating. Returning the existing
preflight's measured rows adds no second fit pass.

Both examples were compiled against retail `30H0` / `tset:3869:4:0:socks00`:

| Authored design | Accepted fit | Encoded body / retail capacity | Complete span |
| --- | --- | --- | --- |
| Three-colour hard bands | 64 x 64, 10 referenced colours across mips | 6,512 / 6,528 bytes | 6,560 bytes, unchanged |
| Dense designer-style reconstruction | 16 x 16, 17 referenced colours across mips | 6,514 / 6,528 bytes | 6,560 bytes, unchanged |

The simple design's base RGBA is byte-exact after decoding. Mip filtering explains
why its three authored colours become ten across the whole chain. The dense
design at 64 x 64 required at least 6,886 bytes, a 358-byte shortfall. Its offered
16 x 16 retry was compiled before being offered, then applied and reparsed. It
still loses fine detail. Both final spans preserve wrapper +0x14 and fill the
original allocation using the existing lossless fill path.

At a forced eight-colour limit, the reconstruction's maximum channel error fell
from 9 to 3 and mean Delta E76 from 1.037317 to 0.019381. At four colours it fell
from 9 to 6 and 1.037317 to 0.506234. Both implementations were exact at sixteen.
This is not a universal quality improvement: at two colours the reconstruction
worsened slightly, from maximum error 161 to 170. The stripe policy avoids that
case. These forced comparisons measure quantization at the same resolution;
they do not measure the final 16 x 16 design against its original-sized detail.

[sock-quality.json](reports/b70_t2/sock-quality.json) records all palette
attempts, quality values, decoded hashes, exact sizes and wrapper checks.
`tools/b70_t2_sock_probe.py` recreates the synthetic inputs and the comparison.

The import result contains “fitted at W x H, N colours.” The count is the distinct
RGBA colours actually referenced by the decoded mip chain, not the search limit
or a nominal 256-entry allocation. Per-edit receipts retain both allocated and
used counts. Project captions read only cached measurements keyed by every
staged equipment ID and PNG hash; Undo/revert cannot show a fit from another
state. Build summaries consume verified, hash-bound per-span receipts and group
equivalent fits across packages. Neither display path reruns compression.

## 2. Larger allocation: loader passes, archive/disc path unproved

The repeat growth probe used `15H0` / `tset:3734:9:4:shoes10`. Retail XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

**PROVED in the bounded loader:** a 58,432-byte compressed body can be replaced
in an isolated resource input with a 128,912-byte body. System/video/scratch sizes
are 640 / 180,992 / 32. Native allocation requests 181,664 bytes, native I/O reads
128,912 bytes, all six descriptors register, decoded video is exact and guards
remain intact. Wrapper +0x14 stays 32. This is an eight-million-instruction,
one-second run of native `0x45280 / 0x451D0 / 0x45100 / 0x4DC00 / 0x450B0`.
Allocator, I/O, resource-registration shell and context-state query use doubles;
the archive manager and filesystem do not execute.

The exact allocation instructions explain why changing only compressed length
does not suffice:

| VA | Instruction / meaning |
| --- | --- |
| 0x451D0 | `mov edx,[eax+8]`: declared system bytes |
| 0x451DA | `mov esi,[eax+0xc]`: declared video bytes |
| 0x451EC | `mov ecx,[eax+4]`: compressed input length |
| 0x451F5 | `mov ecx,[eax+0x14]`: declared scratch bytes |
| 0x45228, 0x4522A | add scratch and system to video allocation |
| 0x45235 | call allocator at 0x48700 |

**Archive audit:** the index's 12-byte name/size/sector record addresses an entire
IFF, not an inner TSET. Package 3734 is 1,513,424 bytes; chunk 9 starts at 292,432.
This growth needs 70,480 extra bytes and a 1,583,904-byte relocated IFF, preserving
and shifting the subsequent inner content. Index record offset is 44,964. The
largest existing inter-entry gap is 2,032 bytes and tail free space is zero.
A hypothetical append at virtual byte 6,227,718,144 / sector 3,040,878 grows final
volume `F` by 774 sectors. The new index fields serialize and deserialize exactly.
That arithmetic is not an archive or disc round trip.

The current production path still explicitly refuses growth:

- `tools/nfl2k5_visual_mod_project.py:4828` pins the source pack size;
  `:4864` requires the replacement to end within that pack.
- Its union verifier and output construction use the source-sized image
  (`:5562`, `:6085`); they have no append/repoint receipt or XDVDFS relocation.
- `mod_editor/core/nfl2k5_build_service.py:1598` requires the output image's size
  to equal the source size, and `:1618` checks the same manifest property.

No offline disc round trip or native lookup of a relocated archive entry has
been demonstrated. Proving that requires a reviewed whole-IFF/index/volume and
XDVDFS writer, verification of all moved ranges, then archive-manager execution
through the relocated entry into the loader. Merely bypassing these guards or
altering +0x14 would not establish correctness. This is a proof/implementation
gap, not evidence that relocation is impossible. **“Larger equipment art
(experimental)” remains unavailable**, as the import help now states.

Evidence: [grown-loader.json](reports/b70_t2/grown-loader.json) and
[growth-audit.json](reports/b70_t2/growth-audit.json). No disc or whole-pack copy
was written for this investigation.

## 3. Shoes10 / Style 6: both slots, one transaction

maumau78: “I assigned this shoe to both mud and normal slot and it finally show
up in-game”; “unfortunately the shoe look buggy in both.” This witness corrects
the earlier single-slot guidance. It does not witness the code delivered here.

Normal shoes, gloves and elbow pads now include the catalog's corresponding
`_mud` sibling. Gloves with no such descriptor remain single-slot imports.
Explicit mud-only imports remain separate. Existing consumer rules still apply:
global shoe names fan out to their sampled packages; local shoes10 uses the
selected uniform package. The combined physical groups, including existing
staged edits, must compile before one `replace_batch`. A failure leaves the
project untouched. Revert on the normal asset restores that same group in one
undoable transaction. Retail no-op palette/mip preservation remains tested.

**PROVED natively:** J1's rerun binds both clean and mud shoes10 rows to both feet,
for HOME/AWAY and both tested package-load orders. The new caller trace executes
`0x8F89E..0x8F8AC`: runtime player record +0x18 bit 28 becomes frame -0x18.
`0x8F901..0x8F90F` transports it as the third argument to `0x8EFA0`; the existing
field binder uses that argument to choose its normal/mud cache row. Flag zero
selects normal; flag one selects mud. Both values are transported under dry
(70 F, precipitation 0), wet (70 F, 0.5) and snow-like (20 F, 0.5) inputs.

**UNPROVED:** when gameplay sets or clears that runtime flag. Weather alone is
not the selector at this call site. The bounded harness seeds the flag; it does
not simulate a game's dirt lifecycle, render pixels or explain the buggy artwork.
All relevant granted help/status strings now state that boundary; WIRING updates
the protected registry's older witness statements while preserving its other
constraints. Atomic sibling/revert tests, receipt tests and the native logs are
under [reports/b70_t2/tests](reports/b70_t2/tests).

## 4. Stadium banners: select the package the game uses

andrethealchemist: “the new textures do not appear in the game. The old banners
around the stadium are still in the game.” His `Texture 29 / banner_corp` screenshot
does not identify the played venue or conditions.

**PROVED defect:** all 477 Stadium Studio scene rows were called “stadium.” The
legacy default geometry scene is outer 3280 / chunk 5 / scene 2648, which resolves
to `s42nd.iff`, Super Bowl 2006 / Night / Dry; its banner is texture 21. It is not
the Bears home package. The new label resolves archive name IDs using the engine's
uppercase UTF-16LE filename CRC and retail STRG venue names. Search accepts venue
labels. No assumed archive-index ordering is used.

The retail weather suffix selector `0x62BE0..0x62C71` was run with Chicago's s05
and Cincinnati's s06 records across all nine time/weather variants, with a
20,000-instruction bound. Each resulting archive package was resolved and
reparsed. Across the selected 18 IFFs, all 90 SCNEs were inspected: exactly one
SCNE per package carries the `banner_corp` name and mapped material. No duplicate
banner occurrence in those packages was found. The full existing private census
has 468 banner occurrences across 52 venues x 9 variants (practice has none);
archive identities were rechecked for the whole census. Only the selected 18
packages received the fresh complete-SCNE/native trace.

| Package | Outer | Chunk | SCNE index | Texture |
| --- | --- | --- | --- | --- |
| `s05dd.iff` | 3141 | 6 | 1998 | 42 |
| `s05dr.iff` | 3300 | 6 | 2736 | 42 |
| `s05ds.iff` | 3459 | 6 | 3474 | 42 |
| `s05ad.iff` | 3194 | 6 | 2244 | 42 |
| `s05ar.iff` | 3353 | 6 | 2982 | 42 |
| `s05as.iff` | 3512 | 6 | 3720 | 42 |
| `s05nd.iff` | 3247 | 6 | 2490 | 38 |
| `s05nr.iff` | 3406 | 6 | 3228 | 38 |
| `s05ns.iff` | 3565 | 6 | 3966 | 38 |
| `s06dd.iff` | 3142 | 5 | 2003 | 29 |
| `s06dr.iff` | 3301 | 5 | 2741 | 29 |
| `s06ds.iff` | 3460 | 5 | 3479 | 29 |
| `s06ad.iff` | 3195 | 5 | 2249 | 29 |
| `s06ar.iff` | 3354 | 5 | 2987 | 29 |
| `s06as.iff` | 3513 | 5 | 3725 | 29 |
| `s06nd.iff` | 3248 | 5 | 2495 | 29 |
| `s06nr.iff` | 3407 | 5 | 3233 | 29 |
| `s06ns.iff` | 3566 | 5 | 3971 | 29 |

The columns list every banner-carrying SCNE in these packages. The complete
receipt also lists each non-banner SCNE's name, chunk, scene index and source
hash. Chicago day/afternoon uses texture 42; Chicago night uses texture 38.
Cincinnati uses texture 29. Other venues can also have texture 29.

For each row, native SCNE registration runs `0x45BC0 -> 0x2F140` through all
texture relocators (`0x34DF0`) and material relocators (`0x304B0`), stopping at
`0x2F20A` before mesh registration. The material's +0x30 points exactly to the
selected descriptor; its pixel/palette pointers address the expected decoded
allocations. Each run is bounded to 200,000 instructions / one second with no
external doubles. Decompression is independently performed by the strict source
resolver. The package manager, GPU and full game do not execute.

**Delegate decision:** the surface really is written. The test uses the real
Stadium Studio, StudioSession, SourceCache and `Nfl2k5StadiumTextureWriter` delegate
for Chicago and Cincinnati. It follows Editable -> replacement -> one actual
compile -> staged edit -> close/reopen the emitted span -> exact base-pixel and
native binding checks -> revert. The edit is not merely a changed GUI flag.
Native binding reaches the selected package's own banner occurrence, so there
is no evidence for blindly writing unrelated venues or conditions. The fix
makes the selector identify the correct package and the receipt identify exactly
what was written. Wrong package selection is a **HYPOTHESIS** for this reporter's
game, whose venue remains unknown.

Receipts now include package filename/venue/time/weather, outer/chunk/scene and
texture identity, descriptor/pixel offsets, linked materials, selected-SCNE
write scope, `compiled_occurrences`, and `in_game_outcome: UNWITNESSED`. Unified
SCNE reports list every selected embedded texture in `compiled_textures`.
Equivalent retail banner pixels in two venues do not imply shared allocation.

Evidence: [stadium-banners.json](reports/b70_t2/stadium-banners.json),
`tools/b70_t2_stadium_probe.py` and `test_b70_t2_stadium.py`.

## 5. Arm digits and replacement semantics

Coach Edwards: “why the shoulder/sleeve numbers keep showing up on outside of
the sleeves and not the shoulder pad section?” The FAQ and arm help explain
that the jersey mesh/UV mapping places the digits; importing a PNG changes
artwork, not the body surface or its position. Arm-family assets use the live
digit route, so WIRING adds the explicit action that opens the new arm dialog.

[Move the arm digit to the shoulder pad](docs/research/nfl2k5_arm_digit_placement.md)
records the measured facts from `hi_body` o3c114 and `lo_body` o3c113. Both have
24 drawable shoulder/sleeve digit submeshes, including neck-roll alternatives.
UV register 6 uses `NORMSHORT2`, stream 1, offset 0, stride 6; the separate
`SHORT1` selector is at offset 4. Shape-record +0x30..+0x3c holds the scale/offset
used by the existing decoder. Some decoded UVs are signed/outside 0..1. Both
shoulder and sleeve surfaces exist, so a UV-only edit is not a proved complete
relocation: visibility/material selection must also be traced at both detail
levels. The run parsed draw/UV data; it did not execute a vertex shader.
[arm-uv.json](reports/b70_t2/arm-uv.json) contains metadata only.

X_Ray: “So do these textures replace ones that are already there or add extra?”
The FAQ answers: they replace an existing slot's artwork and do not add a new
selectable shoe, sock or glove style.

## Validation

All suites below ran as separate processes, including every modified test file:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/<suite>.py
```

Logs contain complete output. [validation.json](reports/b70_t2/validation.json)
records results and timings: **28 direct suites report OK, 275 test cases counted,
including one skip**. Two additional compatibility runs pass 32 cases. One
aggregate suite has the environment failures detailed below.

| Standalone suite / log | Tests counted | Result |
| --- | --- | --- |
| [test_2k5_uniform_equipment_export](reports/b70_t2/tests/test_2k5_uniform_equipment_export.log) | 13 | FAILED (errors=6, skipped=2) |
| [test_b69_j1_build](reports/b70_t2/tests/test_b69_j1_build.log) | 5 | OK |
| [test_b69_j1_fit](reports/b70_t2/tests/test_b69_j1_fit.log) | 5 | OK |
| [test_b69_j1_native](reports/b70_t2/tests/test_b69_j1_native.log) | 1 | OK |
| [test_b69_j1_wiring](reports/b70_t2/tests/test_b69_j1_wiring.log) | 7 | OK |
| [test_b70_t2_equipment](reports/b70_t2/tests/test_b70_t2_equipment.log) | 8 | OK |
| [test_b70_t2_native](reports/b70_t2/tests/test_b70_t2_native.log) | 1 | OK |
| [test_b70_t2_reporting](reports/b70_t2/tests/test_b70_t2_reporting.log) | 5 | OK |
| [test_b70_t2_stadium](reports/b70_t2/tests/test_b70_t2_stadium.log) | 3 | OK |
| [test_b70_t2_wiring](reports/b70_t2/tests/test_b70_t2_wiring.log) | 2 | OK |
| [test_nfl2k5_equipment_consumers-forwarded](reports/b70_t2/tests/test_nfl2k5_equipment_consumers-forwarded.log) | 19 | OK |
| [test_nfl2k5_equipment_consumers](reports/b70_t2/tests/test_nfl2k5_equipment_consumers.log) | 19 | OK |
| [test_nfl2k5_equipment_import-forwarded](reports/b70_t2/tests/test_nfl2k5_equipment_import-forwarded.log) | 13 | OK |
| [test_nfl2k5_equipment_import](reports/b70_t2/tests/test_nfl2k5_equipment_import.log) | 13 | OK |
| [test_nfl2k5_equipment_import_wiring](reports/b70_t2/tests/test_nfl2k5_equipment_import_wiring.log) | 6 | OK |
| [test_nfl2k5_equipment_retail_roundtrip](reports/b70_t2/tests/test_nfl2k5_equipment_retail_roundtrip.log) | 2 | OK |
| [test_nfl2k5_equipment_scope_wiring](reports/b70_t2/tests/test_nfl2k5_equipment_scope_wiring.log) | 3 | OK |
| [test_nfl2k5_equipment_texture_chain](reports/b70_t2/tests/test_nfl2k5_equipment_texture_chain.log) | 19 | OK |
| [test_nfl2k5_equipment_texture_native](reports/b70_t2/tests/test_nfl2k5_equipment_texture_native.log) | 7 | OK |
| [test_nfl2k5_stadium_cache](reports/b70_t2/tests/test_nfl2k5_stadium_cache.log) | 15 | OK |
| [test_nfl2k5_stadium_editor_roundtrip](reports/b70_t2/tests/test_nfl2k5_stadium_editor_roundtrip.log) | 12 | OK |
| [test_nfl2k5_stadium_gltf_export](reports/b70_t2/tests/test_nfl2k5_stadium_gltf_export.log) | 36 | OK |
| [test_nfl2k5_stadium_people_categories](reports/b70_t2/tests/test_nfl2k5_stadium_people_categories.log) | 15 | OK |
| [test_nfl2k5_stadium_studio](reports/b70_t2/tests/test_nfl2k5_stadium_studio.log) | 6 | OK |
| [test_nfl2k5_stadium_texture_writer](reports/b70_t2/tests/test_nfl2k5_stadium_texture_writer.log) | 9 | OK |
| [test_provider_integrity](reports/b70_t2/tests/test_provider_integrity.log) | 7 | OK |
| [test_providers](reports/b70_t2/tests/test_providers.log) | 33 | OK |
| [test_stadium_editable_discovery](reports/b70_t2/tests/test_stadium_editable_discovery.log) | 2 | OK (skipped=1) |
| [test_studio_facade](reports/b70_t2/tests/test_studio_facade.log) | 11 | OK |
| [test_studio_session](reports/b70_t2/tests/test_studio_session.log) | 18 | OK |
| [test_unified_stadium_texture_composition](reports/b70_t2/tests/test_unified_stadium_texture_composition.log) | 5 | OK |

The two `-forwarded` runs execute the complete original suites in separate
processes with the WIRING lazy forwards installed in memory:

```python
import runpy
from mod_editor.core import nfl2k5_equipment_import as legacy
from mod_editor.core import equipment_staging as current
legacy.stage_equipment_import = current.stage_equipment_import
legacy.revert_equipment_import = current.revert_equipment_import
runpy.run_path("tests/mod_editor/test_nfl2k5_equipment_import.py", run_name="__main__")
# Separate process: same setup, test_nfl2k5_equipment_consumers.py.
```

`test_b69_j1_fit.py` and its wiring check were updated for the changed measured
encoding: 664 bytes / 200-byte shortfall, previously 666 / 202. No tolerance was
widened. The structural wiring assertion accepts the existing public owner or
the prescribed forward and still checks combined validation before mutation.
`test_b70_t2_wiring.py` executes the supplied project-list and BuildResult code;
the project-list test forbids compiler calls on the GUI path. Reporting tests
cover tampered receipts and builds with no texture receipts.

**Environment limitation:** `test_2k5_uniform_equipment_export.py` reports
`FAILED (errors=6, skipped=2)`, 13 counted tests. Errors occur before equipment
compilation because this worktree has no generated `reports/assets` inventory:
the uniform catalog path and
`reports/assets/nfl2k5_player_portrait_compatibility.json` are absent. Tracebacks
identify `nfl2k5_uniform_catalog.py:570` and
`nfl2k5_extended_visual_catalog.py:1113 -> metadata_cache.py:17`. Those files were
not edited. This missing-metadata limitation was also noted in the B68 report;
no tests were weakened or fixtures fabricated. `test_stadium_editable_discovery`
also skips its unavailable developer-inventory GUI case. Claude must rerun the
aggregate export suite with the generated inventories before release.

Research commands run with `PYTHONPATH=.`:

```bash
python3 tools/b70_t2_sock_probe.py
python3 tools/b70_t2_stadium_probe.py
python3 tools/b70_t2_arm_uv_probe.py
python3 tools/nfl2k5_b69_equipment_probe.py growth --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --art '/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-13/attachments/2k5-bugs_3f58becf_3.png' --output reports/b70_t2/grown-loader.json
python3 tools/b70_t2_growth_audit.py
python3 packaging/repin.py --apply
git diff --check
```

Repin was applied after pinned writer changes and before commits. Its final
check reports `applied 0 pin update(s)`; provider suites pass. The facade and
`providers.py` digest changes in the protected packaging check are automatic
repin output only. No hand edits to packaging checks were made. Tests executed
on this Linux host; Windows/macOS are not witnessed here. This run used no
emulator, displayed GUI, audio, network or push. Retail inputs stayed read-only;
only small temporary test spans were emitted and cleaned. The committed reports
contain metadata/hashes and authored test-colour values, never retail payloads.
The fallback Git directory and bundle stay well below the 200 MB scratch limit.

## Noah's witness and follow-ups

1. Apply WIRING, merge T1's shared-writer changes, repin and rerun the affected
   standalone suites. Generate the missing private inventories and rerun the
   aggregate export suite. Claude builds the test image through the normal
   release workflow.
2. With Coach Edwards' actual PNG, record the imported uniform, fitted size and
   colour count. Compare bands/motifs at close and distant views, in Edit Player
   and on the field. The measured dense reconstruction still loses detail.
3. Bears home Style 6: import normal shoes10 once and verify both normal and mud
   rows are staged. Select Style 6 on both feet. Compare dry and wet games, both
   feet, home/away kits and close/distant views; note whether buggy artwork
   remains. Revert normal and confirm the whole group returns to retail.
4. Bears home, Chicago Field / Day / Dry (`s05dd.iff`): change **Texture 42 /
   banner_corp** and inspect the corporate sponsor boards around the field.
   Repeat Cincinnati home at Paul Brown Stadium / Day / Dry (`s06dd.iff`),
   **Texture 29 / banner_corp**. Record the actual venue, time/weather and receipt
   selector. Other conditions use separate packages; Chicago night is texture
   38. These steps specify the intended view, not a witnessed appearance.
5. For the arm request, record Titans/Oilers uniform, neck-roll choice and
   shoulder/sleeve views at both detail levels. Trace active submesh/material and
   digit-atlas selection before designing a placement writer. Keep archive
   growth unavailable until both archive/disc and native lookup proofs exist.

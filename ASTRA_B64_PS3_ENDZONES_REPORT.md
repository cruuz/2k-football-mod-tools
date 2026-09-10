# Beta 64 PS3 endzone completeness

Implementation commit: `4bb936ff`, branch `astra/b64-ps3-endzones`. No push.

**PROVED offline:** 55 valid supplied pairs now yield **54 prepared pairs / 108
textures**, up from 46 / 92. All eight formerly unsupported endzone pairs stage
idempotently. Chicago and Washington rebuild inside their retail allocations,
regenerate their declared mip chains and pass the independent reparse gate.

**Required integration:** apply [WIRING.md](WIRING.md) before launching/shipping
the integrated Studio. The brief protects `gui.py` and release-tag tests. Their
exact patch is delivered and tested in temporary modules; the protected files
remain unchanged. The current GUI codec-label table would raise
`KeyError: 'dxt5a'` without this handoff. The core importer/writer is usable
headlessly. In-game appearance, Windows packaged execution, and a complete
54-pair combined build are **UNWITNESSED**.

## Coverage and decisions

| Measure | Before | Now |
| --- | ---: | ---: |
| Valid supplied pairs | 55 | 55 |
| Complete live endzone destination pairs | 117 | 117 |
| Writer-supported complete endzone pairs | 78 | 117 |
| Prepared pairs | 46 | 54 |
| Prepared textures | 92 | 108 |
| Prepared crests / endzones | 27 / 19 | 27 / 27 |
| Field Art writer contracts | 221 | 260 |

Dallas `EndZone/Orginal` and `EndZone` share a destination. I retained the prior
explicit choice of `EndZone`; both alternatives are valid, but cannot both be
in one conflict-free plan. Washington was already prepared in the old plan;
its failure was at build time. The eight new prepared pairs are Chicago Bears,
Cleveland Browns, Green Bay Packers, Houston Oilers, Indianapolis Colts,
Los Angeles Raiders, New York Giants and New York Jets.

[Updated live mapping](reports/ps3_import/hash_mapping.json) and
[54-pair plan](reports/ps3_import/available_staging_plan.json) distinguish
preparation from allocation proof. Existing crest fit limits remain; this is
not a claim that all 54 pairs build. All eight new pairs were staged twice
through `ApfSession`, leaving exactly 16 endzone modifications.

The requested `ASTRA_APF_WAVE1_INTEGRATION_REPORT.md` is absent on this stack.
I used the actual wave results in `ASTRA_INTEGRATION_REPORT.md`, including its
35-of-46 original build subset and the Washington overage. The separate PS3
import report, brief, context/addendum and H7A memory were read. Work stayed
inside this worktree; no emulator, displayed GUI, audio, game-data fetch,
retail source write or push was performed.

## Format 59 proof and implementation

The TXTR fetch word at descriptor offset `0x98` is `0x0000007B`:
`word & 0x3F = 59` (DXT5A), with endian mode 1 (8-in-16). DXT5A is the
single-channel alpha/BC4 block: two endpoints and sixteen 3-bit selectors in
8 bytes. Every one of the 39 pinned endzone format-59 rows is `endzone_l1`,
2048×512, pitch 2048, tiled 2D, swizzle `[0,0,0,5]`: `(scalar,scalar,scalar,255)`.
The catalog's old `codec: dxt1` was wrong; its format word and hashes were right.

These rows use a `0x80000` base and `0x30000` mip allocation. The declared chain
has eight levels (2048×512 through 16×4), not a guessed complete chain to 1×1:

| Level | Dimensions | Offset from texture start | Allocation |
| --- | --- | --- | --- |
| 0 | 2048×512 | `0x00000` | `0x80000` |
| 1 | 1024×256 | `0x80000` | `0x20000` |
| 2 | 512×128 | `0xA0000` | `0x08000` |
| 3 | 256×64 | `0xA8000` | `0x04000` |
| 4 | 128×32 | `0xAC000` | `0x02000` |
| 5–7 | 64×16, 32×8, 16×4 | shared `0xAE000` | shared `0x02000` |

The packed levels have block origins `(0,4)`, `(0,2)`, `(0,1)`. Existing Xenos
8-byte BC1 addressing is reused for DXT5A, while the scalar codec and swizzle
remain separate. This follows the existing BC1, stadium generic DXT5A, and
helmet mip transports; no new tiling formula was invented. The digital font's
white/alpha swizzle is different and is not reused as endzone pixel meaning.

All 39 retail entry/base hashes and full mip transports pass. The
[entry 78/l1 round-trip receipt](reports/ps3_import/format59_retail_roundtrip.json)
records a byte-identical returned IFF, byte-identical unchanged block encoding,
and **maximum/mean scalar codec error 0/0**. That retail layer contains one
distinct block (blank detail); nonblank gradients, both endpoint modes,
broadcast alpha, active-mip corruption, padding corruption and unrepresentable
RGB/alpha are covered with synthetic fixtures. No retail bytes are fixtures.

Changed endzones now regenerate all active mip levels with nearest sampling
(the existing digit writer also offers nearest). This keeps region values
instead of inventing weights through averaging. Inactive tile padding,
descriptors, unrelated inner parts, footer and outer allocation remain fixed.
Exact no-ops retain the complete retail entry. Other Field Art families keep
their previous base-only behavior.

The writer uses safe greedy H7A, then the existing reviewed optimal helper
when needed. Every emitted stream is bounded by its declared output length,
checked for `length <= distance` and valid history, and decoded exactly.
The IFF is reparsed; an independent verifier checks each endzone mip's
addressing, actual storage/pixel hashes, requested effective image and measured
codec error, plus inactive padding. The copied-volume verifier accepts these
receipted mip changes while retaining its whole-volume isolation checks.
The existing registered Field Art product gate now recognizes the 39 scalar
contracts and still validates its unchanged historical divots evidence.

## Washington diagnosis and bounded quality fallbacks

[The baseline diagnosis](reports/ps3_import/washington_allocation_diagnosis.json)
reproduces the exact **13,524-byte** overage:

| Encoding | Active IFF bytes | Allocation / overage |
| --- | ---: | ---: |
| Retail Washington | 136,059 | 137,216 / fits |
| Old base-only import, safe greedy | 151,951 | +14,735 |
| Old base-only import, safe optimal | 150,740 | **+13,524** |
| New regenerated mips, original pixels, safe optimal | 154,680 | +17,464 |
| New regenerated mips, RGB endpoint simplification, greedy | **119,981** | **17,235 spare** |

The uncompressed VRAM remains exactly 1,441,792 bytes. Both imported and retail
alpha are uniformly 255; the baseline retains retail mip bytes exactly. The
failure is H7A's compression cost after changing the BC1 patterns and spatial
repetition, not alpha noise or a larger mip chain. l0's distinct stored BC1
blocks rise from 650 to 4,733 (253 to 576 decoded colors); l1's fall from 6,337
to 2,146 (2,994 to 31 colors). Total distinct blocks alone therefore do not
predict fit. Regenerating coherent mips by itself also does not fix this pair.

The bounded policy is:

1. Requested pixels and regenerated mips: greedy, then reviewed optimal H7A.
2. Snap each RGB channel below 128 to 0, otherwise 255; preserve alpha. Retry.
3. With that simplification, try 2× then 4× nearest downsampling/upscaling of
   the top mip, regenerating every declared level. Fixed dimensions stay intact.
4. Refuse with the remaining byte overage if every step fails.

Receipts state the palette operation, effective resolution, every attempted
active byte size, and requested-to-effective / requested-to-decoded errors.
The optional optimal helper is Linux x86_64 only. Both successful final results
below fit with **greedy** compression, so they do not depend on that helper
being present; actual Windows execution is still UNWITNESSED.

| Supplied pair | Retail slot / allocation | Selected reduction | Active bytes / spare |
| --- | --- | --- | --- |
| Chicago | 78 / 51,200 | RGB endpoints + 4× top-level reduction (effective 512×128) | 48,565 / **2,635** |
| Washington | 70 / 137,216 | RGB endpoints only; full 2048×512 resolution | 119,981 / **17,235** |

[Chicago receipt](reports/ps3_import/chicago_endzone_writer.json): l0 RGBA MAE
2.862359, maximum 255; l1 exact. [Washington receipt](reports/ps3_import/washington_endzone_writer.json):
l0 MAE 0.884613, maximum 255; l1 MAE 0.292728, maximum 119. These maximum errors
make the lossy boundary explicit; static fit is not a visual-quality witness.

## Validation

Tests are standalone `unittest`; default retail gates name absent inputs
precisely. Full supplied-pair encoding is now an explicit slow opt-in; it was
actually exercised to produce the receipts. Across the selected unique suites
below: **110 tests, 106 passed, 4 skipped**, including 26 temporary-handoff GUI
and release-identity tests. The default endzone rerun is listed separately and
not double-counted. This is not the repository's complete suite.

| Suite | Final tail | Log under `reports/ps3_import/` |
| --- | --- | --- |
| `test_apf_endzone_dxt5a.py`, full proof | 10 tests, 259.491s, OK | `test_results_endzones.txt` |
| Same, final default gate | 10 tests, 39.549s, OK (1 slow-proof skip) | `test_results_endzones_default.txt` |
| `test_apf_field_art_patch.py` | 26 tests, 296.485s, OK (2 slow practice skips) | `test_results_field_art_beta64.txt` |
| `test_apf_ps3_texture_bundle.py` | 28 tests, 26.280s, OK | `test_results_bundle_beta64.txt` |
| `test_apf_ps3_texture_bundle_qt.py` | 3 tests, 0.113s, OK | `test_results_bundle_qt_beta64.txt` |
| `test_apf_field_art_gui.py`, temporary handoff | 17 tests, 0.314s, OK | `test_results_gui_handoff_beta64.txt` |
| `test_beta45_honesty_freeze.py`, temporary handoff | 9 tests, 0.639s, OK | `test_results_freeze_handoff_beta64.txt` |
| `test_apf_field_art.py` | 6 tests, 0.014s, OK | `test_results_field_inventory_beta64.txt` |
| `test_apf_product_validation_wrappers.py` | 5 tests, 0.083s, OK | `test_results_product_wrappers_beta64.txt` |
| `apf_h7a_no_overlap_test.py NoOverlappingMatchTests` | 3 tests, 17.156s, OK | `test_results_h7a_beta64.txt` |
| `test_apf_dxt5a_general_preview.py` | 3 tests, OK (2 checkout-relative retail skips) | `test_results_dxt5a_preview_beta64.txt` |

The last preview suite's two skips do not replace the actual 39-retail-pin and
new retail round-trip tests, which passed against the supplied absolute path.

Commands run (from this worktree):

```bash
APF_ENDZONE_RECEIPTS=reports/ps3_import QT_QPA_PLATFORM=offscreen python3 -u tests/mod_editor/test_apf_endzone_dxt5a.py -v
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_endzone_dxt5a.py -v
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_field_art_patch.py -v
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_texture_bundle.py -v
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py -v
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_field_art.py -v
PYTHONPATH=. python3 tests/mod_editor/test_apf_product_validation_wrappers.py -v
PYTHONPATH=. python3 tests/apf_h7a_no_overlap_test.py NoOverlappingMatchTests -v
PYTHONPATH=. python3 tests/mod_editor/test_apf_dxt5a_general_preview.py -v
python3 tools/validate_apf_field_art_product.py
git apply --check reports/ps3_import/field_art_gui_wiring.patch
git diff --check
```

The first full-proof run preceded addition of the slow opt-in. To reproduce
that proof with the delivered test file, add `APF_ENDZONE_SLOW=1` to its command.
The ordinary final command reran synthetic/retail/staging checks with that
expensive case skipped. Initial failures were a synthetic fixture's incorrect
mip allocation, obsolete expectations that endzone tails stay unchanged and
that the old noise image must always overflow, and a GUI text assertion.
They were corrected; the final refusal test supplies deterministic synthetic
incompressible codec output and proves all four quality steps still refuse
with an explicit byte overage.

Temporary GUI validation commands were
`QT_QPA_PLATFORM=offscreen python3 /tmp/astra_test_gui_handoff.py` and
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 /tmp/astra_test_freeze_handoff.py`.
Those harnesses execute the patched source strings in temporary module objects
with the original package/file context, then run the standalone test classes.
They never replace a protected file. After applying the handoff, run the two
named original test files normally with `PYTHONPATH=. QT_QPA_PLATFORM=offscreen`.
The patch passes `git apply --check` against the untouched files.

Fast product tail:

```text
APF_FIELD_ART_PRODUCT_VALIDATION_PASS mode=fast core=6 extras=254 evidence=hash-pinned full_volume=explicit
```

Final writer tail:

```text
Ran 26 tests in 296.485s
OK (skipped=2)
APF_FIELD_ART_PATCH_PASS mode=patched entry=6 files=1 sha256=ffd24d220c2a28447ab23222751113be3c622e4df549ec71984ded9ae90d8837
APF_FIELD_ART_PATCH_PASS mode=no_op entry=6 files=0 sha256=d8fb70d2bdb180306f49aa2b268d287b35eb33289c69959a74fd6c7dcac9af26
```

Only source, tests, documentation and metadata receipts are committed. Retail
inputs and temporary decoded PNGs/rebuilt resources are not delivered. The
pre-existing untracked brief/context inputs are left untouched and uncommitted.

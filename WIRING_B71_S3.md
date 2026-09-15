# Beta 70 T1 integration and protected follow-ups

Branch: `astra/b70-t1-build-speed`. No push. Every in-game outcome is **UNWITNESSED**.
The explicitly granted writer, LZ, facade import/open, visual-project and build-summary owners were edited directly.
No CI, registry, release allowlist, session, digit encoder, APF or game-code owner was edited by hand.
`packaging/repin.py --apply` regenerated only existing hash values in the protected provider/runtime files.

## 0. Required completion-dialog wiring before claiming the wall is fixed in the UI

PROVED: the granted `BuildResult.message` controls the status line, but the protected
`mod_editor/gui/studio_qt.py::_choose_build_output.success` independently rebuilds the old wall
from receipt `message` fields. The protected Build panel uses `build_feedback.completion` and
also independently concatenates those fields. **Both hooks below must land before release.**
The report/summary tests do not imply the existing modal has already changed.

In `mod_editor/gui/studio_qt.py::_choose_build_output.success`, replace the block from
`kept = tuple(getattr(result, "kept_retail", ()) or ())` through the line before
`QMessageBox.information(` with this block (same indentation as the old block):

<!-- B70_GUI_COMPLETION -->
```python
            from mod_editor.core.nfl2k5_build_service import summarize_kept_retail
            kept = tuple(getattr(result, "kept_retail", ()) or ())
            extra = "\n\n" + summarize_kept_retail(kept) if kept else ""
```

In protected `mod_editor/core/build_feedback.py`, replace `completion` with:

<!-- B70_BUILD_COMPLETION -->
```python
def completion(receipt):
    """Keep measured outcomes and summarize retained assets without changing receipts."""
    from mod_editor.core.nfl2k5_build_service import summarize_kept_retail
    outcome = receipt.get("outcome", {})
    if outcome.get("status") == "unchanged":
        title, message = "No changes written", outcome["message"]
    elif outcome.get("status") == "changed":
        title, message = "Disc ready", outcome["message"]
    else:
        title, message = "Copy ready; changes not measured", "The copy was written, but this receipt does not say whether it differs from the source. Review the Build summary before using the copy."
    rows = [row for step in receipt.get("steps", []) or () if isinstance(step, dict)
            for row in step.get("kept_retail", ()) or () if isinstance(row, dict)]
    named = [row for row in rows if row.get("selector") or row.get("asset_id")]
    if named:
        message += "\n\n" + summarize_kept_retail(named)
    # Very old/minimal receipts carry only a sentence, with no asset identity.
    legacy = list(dict.fromkeys(str(row["message"]) for row in rows
                               if row not in named and row.get("message")))
    if legacy:
        message += "\n\n" + "\n".join(legacy)
    return title, message
```

`test_b70_t1_diagnostics.py` executes these exact snippets against the real Qt completion
method and measured/unmeasured synthetic receipt rows. Re-run the protected GUI/feedback
suites after applying them, then repin.

## 1. Windows helper build: future CI work, no binary supplied

PROVED on this machine: `command -v x86_64-w64-mingw32-gcc` returns no compiler;
`packaging/setup_reviewed_helpers*` is absent. The existing helper gate permits Linux x86-64 only.
The C source already sets stdin/stdout to `_O_BINARY` under `_WIN32`.
Do not label the existing ELF as a Windows helper or exempt all `.exe` files from release review.

the integrator's CI integration must:

1. Build **on a Windows x64 runner**, with a pinned compiler/toolchain. For a reviewed LLVM installation,
   the candidate command is below. This command has **not** been executed on Windows here.
2. Run the native-vs-Python byte-equivalence corpus on Windows, including all offset bits 10..13,
   short streams, random bytes, flat/repeated input, CR/LF and `0x1a`, comparison-budget failures,
   tiny output limits, malformed/absent helpers and subprocess timeout. Validate every successful native
   stream through `decompress_vc_lz`, with exact consumed length and header equality.
3. Review the PE machine type, byte length, SHA-256 and dependency list. Record those measured values;
   never regenerate a trusted binary pin automatically from an arbitrary release payload.
4. In `mod_editor/core/nfl2k5_equipment_lz.py::_optimal_helper`, add an exact Windows x64 row choosing
   `tools/nfl2k5_equipment_optimal.exe` with its **reviewed** size/hash. Keep the Python fallback for
   Windows ARM64, macOS, rejected files and missing binaries until separately built and reviewed.
   Windows regular files report mode `0666`; do not require Unix execute bits or reject that synthesized
   write mode there. Retain regular-file, non-link, size and content checks.
5. Add exactly that path to protected `packaging/release-allowlist.txt`, installer staging and
   `packaging/check_2k5_mod_studio_release.py::equipment_contracts` (currently around line 608).
   The existing pattern pins Linux `tools/nfl2k5_equipment_optimal` to 16,504 bytes /
   `949aad6a251de3f039f83bff15d4aa033183c250dbeadd1029e7c79dee4817c4`, and C source to
   4,648 bytes / `6c9c7470d40ce3b99ac000fe75bd51c7d2fbeb44f783e313eb7b7dee0f0b8390`.
   The new exception must validate `MZ`, the PE signature and x64 machine type rather than ELF.
6. Run packaged import/open tests on actual Windows, repin Python owners, and publish only the
   reviewed artifact. Keep all Windows performance/installer claims UNWITNESSED until that run.

```powershell
clang -O3 -std=c99 -Wall -Wextra -Werror -o tools/nfl2k5_equipment_optimal.exe tools/nfl2k5_equipment_optimal.c
python tests/mod_editor/test_b68_t1_build.py
python tests/mod_editor/test_b70_t1_build_speed.py
python tests/mod_editor/test_b70_t1_diagnostics.py
```

The old C helper returns exit 2 for both fit and other failures. A native miss still needs the
Python fallback because that return code alone does not prove a size overflow. A future revised
protocol can distinguish a proved bound from an allocation/search failure; review/re-pin both the
binary and its source then. T1 did not alter the currently reviewed C binary or its protocol.

## 2. Digit shortfalls and checked retries need the protected digit owners

**Triage correction:** `EquipmentFitError.suggestion` belongs to the equipment TSET writer.
The nine arm/jersey digit rows in a tester' photo originate in
`tools/nfl2k5_visual_mod_project.py::kept_retail_record`, whose cause is
`nfl_tset_png_import.QualityBudgetError`. Current digit attempts contain `vc_lz_overflow`
but **no encoded byte count and no checked smaller-image suggestion**.
`mod_editor/core/nfl2k5_digit_art.py::fit_digit` discards the original size-overflow cause while
combining the palette/registration attempts. Thus those existing rows cannot honestly print an
exact shortfall or promise a fitting size/colour combination.

T1's granted summary path now supports `shortfall_bytes`, `shortfall_is_lower_bound` and
`suggestion={width,height,colours}`; full original messages and attempts remain in the receipt.
Existing measured equipment data is shown accurately. Current digit overflows establish only
“at least 1 byte over”; historical rows without even that evidence say “byte shortfall unmeasured”.
No checked digit retry is invented. **Measured digit retry production remains an integration follow-up.**

### Exact protected insertion for measured digit overflow data

In `tools/nfl_tset_png_import.py::quantize_levels_to_vc_lz_bound`, replace the
`try: compressed, compression = compress_vc_lz(...)` through its overflow `continue` with:

```python
        measurement_limit = max_encoded_size + 512
        try:
            compressed, compression = compress_vc_lz(
                decoded, stream_tag=stream_tag, offset_bits=offset_bits,
                max_encoded_size=measurement_limit,
            )
        except TxtrError as exc:
            if not _is_vc_lz_size_overflow(exc):
                raise
            last_overflow = exc
            attempts.append({
                "maximum_palette_entries": maximum,
                "palette_entries": actual_entries,
                "result": "vc_lz_overflow",
                "required_bytes": measurement_limit + 1,
                "required_is_lower_bound": True,
            })
            continue
        if len(compressed) > max_encoded_size:
            last_overflow = TxtrError(
                f"VC-LZ stream is {len(compressed)} bytes, exceeds {max_encoded_size}"
            )
            attempts.append({
                "maximum_palette_entries": maximum,
                "palette_entries": actual_entries,
                "result": "vc_lz_overflow",
                "required_bytes": len(compressed),
                "required_is_lower_bound": False,
            })
            continue
```

This preserves the selected successful greedy bytes and bounds additional measurement work to
512 output bytes per miss; it must receive the digit encoder's standalone regression tests before
integration. Then replace T1's provisional digit `shortfall_bytes` / lower-bound expressions in
`kept_retail_record` with the smallest recorded `required_bytes - target.stored_size` and its
lower-bound flag. A minimum is exact if an exact attempt attains it and all other lower bounds are
at least that value. Keep the complete attempts in the receipt.

### Checked digit size/colour suggestions are a separate writer change

A digit's fixed native canvas/descriptor is not the equipment writer's independent mip chain.
Do **not** apply an equipment `scale=2` intent to an arm/jersey digit or change its descriptor.
The authorized owner is `mod_editor/core/nfl2k5_digit_art.py::fit_digit`, at the final
`error = QualityBudgetError(...)` before `raise error`. It has the retail image, original prepared
canvas, `candidate` callback, palette floor, offset bits, stream tag and allocation required to
check a retry. A proposal must run at most one additional bounded ladder with one explicit smaller
**visible mark** on the same native canvas, retain the existing edge/coverage and contrasting-region
gates, and offer it only after its full original-size mip-chain candidate fits. Its record must name
both `canvas_width/height` and `art_width/height`, plus checked colours, so the UI does not misrepresent
mark shrinkage as a new game texture size. The digit preview/import owner needs the same explicit
choice before such a suggestion can be actionable. No untested code block is supplied pretending
that this UI/writer contract has already been proved. This is the remaining portion of request 5.

## 3. Release integration

- No new production module, tool, capability or registry row: **0 registry rows added**.
- Source edits require the combined-stack cave manifest fingerprint regeneration required by
  ASTRA_CONTEXT. T1 adds no XBE writes or allocations. Do not change game-byte claims.
- Preserve the exact beta-69 span goldens in `test_b70_t1_build_speed.py`; do not regenerate them
  from the beta-70 writer. `d208076c` records them before any production changes.
- The local staged cache is private derived data beside the extracted source index. It must stay
  outside shareable projects and release packages, like beta 68's compile cache. It uses existing
  bounded, checksummed JSON/atomic replacement support; unavailable/corrupt cache entries recompile.
- Shared Git metadata is read-only in this session. Delivery uses a private Git directory in `/tmp`
  with the original object store as a read-only alternate, and a portable bundle under
  `reports/b70_t1/`. Integrate that branch/bundle; ordinary worktree `git log` remains at the input head.

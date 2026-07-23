# APF 2K8 Mod Studio — bounded localization-writer result

Date: 2026-07-18

## Result

Positive offline product experiment. `tools/apf_txt_loc_patch.py` now compiles
user-authored replacements for both proved English `TXT loc system` resources
without modifying the selected source volume. The writer operates on underlying
deduplicated pool allocations, rebuilds every relative record pointer, H7A
compresses the changed table, rebuilds its IFF entry, and refuses output that
does not fit the original outer allocation.

This transport is connected to APF Mod Studio's Menus & Text Replace/Revert,
project, and unified build paths. This receipt does not claim runtime text
consumption yet.

## 2026-07-18 product extension

The same provider now also owns both APF `STRG` resources. The complete typed
archive string-bank inventory is therefore four banks, 2,413 underlying pool
allocations, 2,410 editable allocations, and three structural read-only rows.
STRG Replace/Revert, retail-free project save/load, and a complete separate-game
build have passed. See
`reports/product/apf_universal_text_bank_inventory_20260718.md` for the exact
inventory, shared-block rebuild proof, safety boundary, and non-STRG text lanes.

## Live source-derived inventory

- Outer 526 / inner 0, `credits_English`: 742 pool allocations.
- Outer 1127 / inner 0, `English`: 552 pool allocations.
- Total underlying allocations: 1,294.
- Editable allocations: 1,292.
- Required fallback sentinels held read-only: 2 (pool zero in each table).
- Allocations referenced by more than one localization record: 148. The UI must
  state that editing one of these shared strings changes every listed consumer.
- Existing semantic record view remains 1,572 records; records and pool assets
  are intentionally different views of shared data.

The displayed limit is the allocation's maximum UTF-16 code-unit count. Most
ordinary characters consume one unit; non-BMP characters such as emoji consume
two. Embedded NUL values are refused.

## Live compile proof

The experiment ran directly against the user's untouched APF 2K8 `0A`:

- Outer 526: pool 1 shortened to `Q`; output remained exactly 16,384 bytes,
  decoded body became 30,098 bytes, and the rebuilt IFF reparsed with zero
  warnings.
- Outer 1127: pool 10 became `MOD` and pool 7 became `MUSIC` in one grouped
  compile; output remained exactly 12,288 bytes, decoded body became 17,298
  bytes, and the rebuilt IFF reparsed with zero warnings.
- Both edited strings decoded back exactly from their rebuilt entries.
- A semantic no-op (`HOME` back into its existing allocation) returned the
  original entry bit-for-bit with zero changed bytes.
- The complete source `0A` SHA-256 was identical before and after the test.
- Six source-free unit tests cover asset IDs, allocation limits, surrogate-pair
  accounting, pointer rebuilds, fallback/NUL refusal, and hashes-only receipts.

## Safety and distribution boundary

- Source is read-only; this module returns one fixed-size replacement entry in
  memory.
- It does not write a retail volume or publish a partial game build.
- Receipts contain coordinates, sizes, counts, and SHA-256 values only. They do
  not contain original text, replacement text, retail bytes, or replacement
  bytes.
- Shareable project integration must store only the user's replacement strings
  and metadata. It must never serialize untouched source strings.

## Remaining product work

1. Expose the 1,294 pool allocations in Menus & Text with limits, reference
   counts, shared-string warnings, modified badges, Replace, and individual
   Revert.
2. Group all active changes targeting the same table into one compile, resolving
   the current duplicate-outer-entry build limitation.
3. Extend `.apf2k8mod` projects to user-authored text payloads while retaining
   the zero-retail-data structural gate.
4. Spot-check one unmistakable menu label in Xenia. Until that happens this is
   an offline-proved writer, not a runtime-proved consumer.
5. Continue inventorying non-localization text-bearing types. `TXT loc system`
   is now owned; other resistant string structures remain read-only with an
   explicit note instead of being silently omitted.

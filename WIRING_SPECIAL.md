# SPECIAL handoff for Claude

Implement these protected-file changes before rebuilding the disc. The current
builder intentionally rejects the larger XBE. No protected file or reservation
manifest was edited here; no emulator was run. The former stride-13 disc must
be rebuilt from retail, not patched in place.

## Storage decision and the required writer wiring

No existing `.rdata` cave was certified. The implemented alternative preserves
all retail allocations and extends the final read-only `.XTLID` section into
new loader memory. Table: `0xEE3000..0xEE3CF0`, 46 records. SPECIAL starts at
record 33; every unit still uses stride 11. XBE size is **12,021,760 bytes**,
formerly 11,948,032 (**+73,728**). Only SPECIAL scrolls.

This is a deliberate deviation from the requested existing `.rdata` host. The
old oracle still returns unknown for unresolved/unmapped candidates. A separate
fresh-allocation proof uses its validated section mapping and the manifest:
no mapped retail bytes are reused, no other owner overlaps, and no absolute
word or relative transfer encoding anywhere in the retail sections/header
points into the new page. New section bytes are build-time data, read-only
at runtime. Its original 5,184-byte `.XTLID` payload is preserved and pinned.
Preloading/loading this extended section still needs Noah's boot witness.

The ready, tested helper is:

```python
from . import nfl2k5_depth_chart_storage as storage
storage.write_image_xbe(fd, patched_xbe)
```

It accepts a fully applied SPECIAL XBE, validates the old embedded storage,
appends the grown file to a disposable disc, verifies it, then changes only
`default.xbe`'s root-directory sector/size. Original XBE and adjacent files
stay intact. Replays write the existing allocation. Short writes/read-back
failures restore the old directory and truncate the appended data. Caller
opens the **output copy**, with `O_BINARY` as usual.

### `mod_editor/core/nfl2k5_throw_tuning.py`

1. Import `nfl2k5_depth_chart_storage as depth_chart_storage`.
2. In `image_xbe_extent()` (near line 649), keep the retail size accepted.
   Replace the single fixed-size requirement with:

   ```python
   if length != EXPECTED_XBE_SIZE:
       _require(length == depth_chart_storage.FILE_SIZE,
                f"unrecognised default.xbe size: {length}")
       candidate = platform_compat.pread(descriptor, length, offset)
       _require(len(candidate) == length
                and depth_chart_rows_patch.status(candidate) == "applied",
                "larger default.xbe is not the recognised SPECIAL layout")
   return int(offset), int(length)
   ```

   This is required for **all** subsequent build/status readers and replays.
   Do not merely remove the size guard or change EXPECTED_XBE_SIZE globally.
3. `_apply_all` already has the import, kwarg, tuple, status and receipt wiring.
   Keep it; change its label from `depth-chart rows` to `SPECIAL tab`.
   No `_apply_all` size restriction needs removing. The same-size restriction
   in `plan_patch()` near line 819 protects an unrelated curve writer; keep it.
4. In `write_disc_copy()`, after copying the source and before writing the
   old byte-difference ranges, branch on `len(patched) != len(original)`:

   ```python
   xbe_relocation = None
   if len(patched) != len(original):
       xbe_relocation = depth_chart_storage.write_image_xbe(dst, patched)
   else:
       # existing ranges calculation and pwrite loop
       ...
   ```

   Retain the EDGE asset pass. At verification, allow exactly
   `size + (xbe_relocation["image_growth"] if xbe_relocation else 0)` and
   resolve `(after_offset, after_length) = image_xbe_extent(check, actual_size)`
   again, then read that extent. Do not verify using the old offset/length.
   Put the relocation receipt in the output receipt. This prevents a truncated
   XBE when the direct Gameplay Patches writer is used.
   `write_xbe_copy()` already writes the full byte buffer and needs no resize fix.

### `mod_editor/core/mod_build.py`

1. Keep `BuildPlan.depth_chart_rows`, dependencies, source preflight, existing
   capability/status entries and EXPERIMENTAL preset selection. Keep the
   post-pools `tt._apply_all(..., depth_chart_rows=True)` step. Comment it as
   retail stride + relocated table, and name its progress message
   `Adding the SPECIAL tab and formation-role views`.
2. `_write_xbe_bytes()` near line 474 must handle the one recognised growth.
   Inside its existing output descriptor lifetime, after resolving the extent:

   ```python
   if length != len(payload):
       from . import nfl2k5_depth_chart_storage as storage
       storage.write_image_xbe(fd, payload)
   else:
       # existing same-size write, with its fsync
       ...
   ```

   The helper validates the only supported size/layout transition; keep
   unknown layouts refused. The updated `tt.image_xbe_extent()` above makes
   the immediate `_xbe_bytes(target)` read-back work.
3. Keep the Tier 1 pass after position recoding and installed/authored book
   packs. It now includes `nfl2k5_special_roles` automatically. Keep
   `allow_custom` limited to intentional authored packs. Update progress to
   `Assigning receiver, corner and SPECIAL formation roles`.
4. Keep book pins/status preflight: old recognised Tier-1-only books report
   retail for upgrade; obsolete stride-13 executables report foreign. Keep
   the complete pools XBE + playbook + roster recoding dependency.

## Gameplay Patches and Build tab wording

Update both the long PATCHES entries and the short card descriptions in
`mod_editor/gui/gameplay_patches_panel_qt.py` (currently lines 169–181 and
240–242), plus `_option` labels/details in `mod_editor/gui/build_panel_qt.py`
(currently lines 434–445). Keys/checkbox variables do not change.

* `depth_chart_rows` label: **SPECIAL tab: role depth charts (experimental)**.
  Details: “Offense and defense keep eleven rows with X/Z receiver labels.
  SPECIAL contains KR, PR, K, P, SLOT, NICKEL, DIME, GADGET, left/right
  GUNNER, LONG SNAPPER, 3RD DOWN BACK and POWER BACK. SPECIAL scrolls.
  These are shared depth lists: changing a role can change another row;
  right gunner and dime corner share a list. Requires position pools and
  formation roles. This revised layout needs an in-game check.”
* `depth_roles` label: **Receiver, corner and SPECIAL formation roles**.
  Details: “Assigns X/Z/SLOT and nickel/dime players, punt gunners and the
  long snapper, passing-set and power backs, and compatible gadget receivers.
  Conflicting formations are listed in the report and keep their existing
  assignment. Some formations use the gadget receiver on ordinary plays too.”
* Short descriptions must also say SPECIAL tab. Remove claims that offense
  or defense has thirteen rows, that special teams stays at four, and that
  Tier 1 has no corresponding depth-chart views.
* Preserve the experimental/unwitnessed badge for the new layout. Do not
  describe these views as independently saved formation substitutions or
  promise the literal third/fourth overall player in every situation.

**Material data-pass choice:** GADGET accepts 56 WR-carry formations, but
those shared personnel groups contain **265 formations total**. Their gadget
receiver also plays ordinary plays. Other gadget assignments are refused
when they conflict with X/Z/SLOT, disagree on the carrier, or need an HB list.
HB direct-snap formations retain the independently selected HB role. There
are 387 classified passing formations: 356 accept 3DB; 31 remain refused.
All 159 classified PWR formations accept PWR. See the checked-in audit for
individual groups and formation names; do not present these totals as an
unconditional per-play formation-sub system.

## Packaging and reservation generation

Add these explicit new runtime paths to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_depth_chart_storage.py
mod_editor/core/nfl2k5_special_roles.py
```

The existing rows/roles/pools/modern/EDGE modules and CLI are already wired.
If the release includes this documentation, also include
`docs/mod_editor/depth_roles.md` and `docs/mod_editor/special_roles_audit.json`.
Do not change release-tag tests for this task. `packaging/repin.py --apply`
already reports **0 updates**; run it again after your protected edits.

**Regenerate `data/nfl2k5_cave_reservations.json` yourself after wiring.**
It was intentionally not regenerated here. The new tail/preload/header/table
ownership and changed source hashes require it. The generator now accepts
only the verified rows module's append, tracks the appended bytes, and emits
`stack_image_size`; the manifest reader accepts that bounded extra address
space without relaxing any reachability verdict or source-fingerprint guard.
The freshness test currently fails on the old depth-chart-rows fingerprint.
Do not suppress that failure or remove its `source_root` check.

```bash
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json data/nfl2k5_cave_reservations.json
```

That command is provided for Claude; it was **not run**. After regeneration,
rerun the two XBE gates, cave-oracle tests, rows/roles/pools/modern/EDGE tests,
and packaging runtime-closure tests. Build an EXPERIMENTAL disc and check
its resolved default.xbe length/status, digests, 37-book role status/audit,
and unchanged formation/play/node counts before Noah boots it.

No new code cave or writable flag is allocated. Keep the full pools helper
reservation at `0x2BA840..0x2BA860`. Reserve the entire relocated table,
loader header edits, and newly materialized final-section tail under rows.

Noah's full witness checklist and per-book counts are in
`ASTRA_ROWS_SPECIAL_REPORT.md`.

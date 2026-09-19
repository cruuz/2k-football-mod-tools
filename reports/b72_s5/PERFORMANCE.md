# Default scorebug check cost

The required default test files retain their assertions, full probe sets, native visibility/order cases and transaction rollback injections. They do not require a speed environment switch.

- Native test machines coalesce adjacent mapped pages with the same permission union. Unused instruction/write histories remove their Unicorn hooks; tests that inspect those histories keep recording enabled. Event capture hooks cover the exact observed entry points instead of calling Python at every instruction.
- Texture encoders cache exact immutable pixel bytes, template bytes and all encoding options. Logo decoding still checks the source pin on every public call and returns a fresh image. Receipts returned from caches are copied. Invalid or changed inputs cannot reuse a stale path/timestamp identity.
- Quantization retains range/population metrics for boxes that have not changed. Current box position still participates in ties, preserving palette output.
- The four timeout variants reuse one validated panel image and repaint their three opaque dashes. All 264 variants match the base implementation byte for byte.
- The static XBE writer validates the existing runtime owner once per unchanged input payload, before its field loop. Previously it repeated the same full XBE validation for every field. It still applies the same override map, writes and hashes.
- XBE receipt counters skip exactly equal 64 KiB blocks and count every byte in changed blocks. Tests cover block edges, partial final blocks, differing lengths and fully changed inputs. XBE validation, hashing and ownership checks are unchanged.
- Sparse test fixture copying uses the equivalent C-backed all-zero byte check. Logical reads, suffix comparisons and complete rollback hashes remain.

`check_performance_equivalence.py` extracts the original quantizer and panel function from base `ec5d68d4` for differential comparison. `performance_equivalence.log` records 24 palette comparisons (including tie cases and seeded RGBA) and all 264 panel variants. `asset_cache_equivalence.log` records fixed-span cache parity and receipt isolation. The nine GPU/palette regression tests include pixel/option/template cache invalidation and logo pin/image isolation checks.

Earlier slow runs are retained rather than discarded. `VALIDATION.md` identifies the most recent applicable result and log for each required file. The auxiliary allocator audit retains its separate 420-second timeout and longer retry. No time threshold or assertion was weakened to claim a pass.

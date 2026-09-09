# Frozen synthetic beta-60 and beta-61 packs

These four ZIPs contain synthetic bytes only. They were exported with the
unchanged `modpack.py` and `modpack_ops.py` from the locally available release
tags. Exact tag commit IDs, ZIP hashes, image sizes and image hashes are in
`receipts.json`. Tests never regenerate these packs using the current exporter.

Basic uses format 1; Advanced uses format 2 `byte_runs` plus SPECIAL `xbe_grow`
version 1. They are transport equivalents of the shipped preset packs, not
proprietary copies of those presets. No shipped `.2k5patch` fixtures existed in
this worktree's `tools/` directory.

The base uses `test_modpack.build_xdvdfs` with `default.xbe`, `next.bin` containing
`b"neighbour"`, and 19 trailing bytes. Basic's XBE is `b"XBEH" + bytes(100)`.
Advanced uses `nfl2k5_depth_chart_rows_test.fixture()` and appends
`rows.apply(prepare(retail))[0]` through `storage.write_image_xbe`, with the
fixture's all-zero retail final-section hash pin. Both set a marker at image
offset 123: `beta-60 basic`, `beta-60 advanced`, `beta-61 basic`, or
`beta-61 advanced`. Export uses `recipe=False`. The regression reconstructs
these expected images independently, checks every byte in blocks, and pins
both before/result SHA-256s and the unchanged archive SHA-256.

The two Advanced packs were re-exported on 2026-09-08 with the same tag exporters (unchanged `modpack.py` and
`modpack_ops.py` from `beta-60` and `beta-61`, loaded over the current package) because the synthetic retail fixture
gained the Outside Linebackers filter-list sites with the one-pool positions change; the Basic packs are untouched.

The two Advanced packs were re-exported again on 2026-09-08 (beta 63) with the same tag exporters because the base
synthetic executable changed under them: the 7-on-7 v2 landing moved the synthetic section table from 0x200 to the
retail 0x370 (the old offset overlapped the arc certificate bytes at 0x310 and corrupted section 5) and seeds the
retail rush reads. The Basic packs are untouched.

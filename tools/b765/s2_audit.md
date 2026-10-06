The field audit reads home-venue bundles from an XISO or an extracted archive,
dumps the native P8 mip chains and records actual material/submesh placement.
It writes no disc files. Supply art manifests separately so historical source
assumptions remain visible beside the native result.

Run from the repository root:

```bash
python3 tools/b765/s2_audit.py extract --disc /path/to/input.xiso.iso --out /path/to/native_before
python3 tools/b765/s2_audit.py audit --before /path/to/native_before --after /path/to/native_after \
  --art-root /path/to/authored/art --review-json /path/to/manual_review.json \
  --variants --out /path/to/audit --workers 4
```

Extraction defaults to the 288 bundles for all 32 home venues. For an initial
pass use `--dry-day-only`, or select `--teams ATL` / `--teams ATL,DET,HOU`.
Existing identical extractions are reused; different existing data refuses.
The extraction receipt records the source, outer ID, offset, size and SHA-256
for every bundle. No original input is opened for writing.

`native_after` may be sparse. An absent after bundle inherits its before bytes,
and its JSON row says `after_uses_original: true`. Each row records both hashes
and byte equality. The native repair's narrower byte scope receipt remains
the authority for changes within a repaired bundle. After-directory bundles
outside the selected teams refuse, protecting the home-venue ownership boundary.

Each `<team>/field_art_audit.json` includes before/after image paths, all bundle
hashes, native texture dimensions, palette hashes, alpha bounds, actual stored
mip images and hashes, and submesh bounds in game centimetres. `--variants`
decodes all extracted variant fields and every supplied repaired variant;
the dry-day pass also dumps stadium branding textures. A manual review JSON
maps team abbreviations to objects containing a `disposition`, `observations`
and optional `issues`; it is preserved under `manual_offline_review`.

The contact sheet shows all 32 before/after pairs. Separate half sheets make
close inspection easier. The previews project actual native UVs and draw-command
indices from above. They omit lighting, grass detail shaders and runtime badge
activation. The diagnostic renderer uses premultiplied bilinear filtering;
it is not an emulation of every NV2A shader/blend state. Native dumps retain
the exact decoded pixels for closer inspection. Mip RMSE compares a stored
level against premultiplied box filtering of the previous level; a nonzero
value indicates a difference, not a confirmed visual defect.

After changing one repaired team, rerun `audit --teams ATL` with the same output
directory and its replacement directory, then refresh the all32 contact sheet
and scope summary without re-decoding the other 31 teams:

```bash
python3 tools/b765/s2_audit.py sheet --out /path/to/audit
```

No byte comparison establishes current field accuracy or gameplay-camera
quality. Review the images and dated real-field references, record unresolved
findings, and capture the requested camera views separately. `gameplay_witness`
stays false throughout this tool.

Reusable helpers for scenario-field tooling are `read_mips`, `texture_stats`,
`field_draws`, `field_preview` and `analyse_bundle`. They accept decoded/native
bytes and output directories and do not rely on a particular team. The CLI's
default team map deliberately excludes special-event/Anniversary venues;
scenario jobs should call these helpers for their own explicitly scoped bundles.

Keep native dumps, web/reference art and contact sheets in local scratch;
none belong in the repository. Retail-free checks run with:

```bash
python3 tests/mod_editor/test_b765_s2_audit.py
```

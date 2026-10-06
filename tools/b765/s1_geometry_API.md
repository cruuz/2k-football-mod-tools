# s1 geometry export and reimport

`s1_geometry.py` transports coordinator-authored geometry. It never authors a
mesh. The full textured stadium is exported through Studio's existing
`ModelSpanSource` / `export_model` API. Every exported primitive carries
`_NFL_VERTEX_INDEX`; mesh and primitive extras retain native shape, submesh and
material IDs. The full bowl, seats, decks, roofs and scoreboards remain beside
the crowd meshes in both `stadium.gltf` and the metre-scale reference OBJ.

Export the exact native bundle to a **new** folder. A source bundle hash can be
supplied from `stadium_extraction_manifest.json`:

```bash
python3 tools/b765/s1_geometry.py export \
  --input /path/to/authorized-captures/disc_files/s07dd.iff \
  --outer-index 3143 \
  --expected-sha256 18d31045c2e9fc22f56e803ae8e8f16341944d341ec6439ca84d44cc71437e9a \
  --out /path/to/authorized-captures/geometry_exports/new_att_edit
```

Edit `stadium.gltf` and `stadium.bin`, leaving the pinned `baseline.gltf`,
`baseline.bin`, `source.scne` and `manifest.json` untouched. Position accessor
values are **centimetres**. Its existing root node scale is `0.01`, displaying
metres in glTF software. `stadium_reference.obj` is in metres and is a read-only
triangulated reference; reimport takes glTF. UV values are texture repeats,
decoded using the native per-shape constant, without a V flip.

The strict lane accepts local mesh position and UV edits. Keep custom vertex
attributes, mesh extras, primitive extras and native IDs. Every native vertex,
including vertices unused by a drawable primitive, must remain present. IDs
can reorder with their corresponding attributes and indices. Duplicate copies
of an ID must agree in every attribute. Equivalent oriented triangle topology
may replace strips in the glTF, but original native topology is retained in
the game file. Node transforms, hierarchy, materials, textures, embedded image
bytes, colours, normals, selectors and other attributes must remain unchanged.
No nearest mapping or assumed vertex order exists in this route. Software
which drops native IDs/metadata will be refused; preserve the original export
and transfer coordinator edits into its accessors by native ID when needed.

Find the shape IDs and material grouping in `manifest.json`. For example,
authorize position edits to native shape ID `48` by adding `--positions 48`;
use the IDs from the specific variant's manifest, not this illustrative ID:

```bash
python3 tools/b765/s1_geometry.py import \
  --input /path/to/authorized-captures/disc_files/s07dd.iff \
  --manifest /path/to/authorized-captures/geometry_exports/s07dd/manifest.json \
  --edited /path/to/authorized-captures/geometry_exports/s07dd/stadium.gltf \
  --positions 48 \
  --output /path/to/authorized-captures/geometry_fixed/s07dd.iff \
  --receipt /path/to/authorized-captures/geometry_fixed/s07dd.receipt.json
```

All scope flags accept comma-separated native shape IDs:

The `apply` command is an alias for `import` for coordinator handoff scripts.

| Flag | Permitted decoded bytes |
|---|---|
| `--positions IDS` | Edited vertices' original FLOAT3 position lanes |
| `--uvs IDS` | Edited vertices' original NORMSHORT2 UV lanes |
| `--rescale-uvs IDS` | Requires `--uvs`; UV constant at shape `+0x30..+0x3f`, plus UV lanes that need re-encoding |
| `--bounds IDS` | Requires `--positions`; bounding sphere XYZ at shape `+0x00..+0x0b` and radius at `+0x48..+0x4b` |

Without `--bounds`, a changed position may not newly leave the existing culling
sphere. Without `--rescale-uvs`, UVs must encode inside the existing range.
The writer patches the original decoded allocation directly. It never invokes
the scene serializer, reorders native vertices, changes draw words, or moves
any decoded allocation. VC-LZ compression must fit the exact original stored
span; budget failure refuses before any output is written. The existing
builder calculates the loader's required overlap scratch word and independently
decompresses its fitted stream. Import then parses the output stadium SCNE and
checks every decoded byte against the intended result.

Receipts contain exact bundle and SCNE span hashes, stored offset and length,
compression budget, per-vertex edit scopes, merged decoded ranges, equal
outside-scope digests, prefix/suffix hashes, and native readback status. Source
artifacts are hash-pinned. The input stadium span must equal the original or
the exact compiled target; applying the same edit to its own output is
idempotent. An unchanged import preserves the entire input bundle byte for
byte. Other bundle chunks may have changed since export and remain intact,
which permits composition with field job s2. Stadium texture or material
repairs inside the same SCNE require a fresh export of that intermediate
bundle before geometry import, then transfer the coordinator's same edits by
native IDs. The tool refuses an unexpected stadium hash.

The Python build integration API is:

s1b may supply `uv_constants={shape_id: [Su, Sv, Ou, Ov]}` to match an
independently compiled Studio shape exactly. Each such shape requires both
`uvs` and `rescale_uvs` authorization; only its UV constant and packed UV lane
are changed. Constants must be finite with nonzero scales. Repair-plan entries
carry the same optional map, with string shape IDs as JSON object keys.

```python
fixed, receipt = compile_bundle(
    current_bundle_bytes, manifest_path, edited_gltf_path,
    positions={shape_id}, uvs=set(), rescale_uvs=set(), bounds=set(),
)
```

Filesystem writes use binary descriptors with `O_BINARY` where available and
atomic replacement followed by byte-for-byte readback. The CLI requires a new
scratch output path, preserving its input. Output and receipt paths must also
preserve the export manifest, pinned source artifacts and coordinator-edited
glTF/buffers. No game disc or emulator is opened.

Run the retail-free tests in their own process:

```bash
python3 tests/mod_editor/test_b765_s1_geometry.py
```

Exports and native byte checks prove transport, scope and fixed allocation.
They do not prove visual quality, runtime visibility, or player-witnessed
gameplay. The coordinator owns actual geometry edits and the xemu capture
script owns the gameplay camera evidence.

## Transport validation from the s1 session

The retail-free test process completed with this actual output:

```text
$ python3 tests/mod_editor/test_b765_s1_geometry.py
...................
----------------------------------------------------------------------
Ran 19 tests in 0.529s

OK
```

Saved output:
`/path/to/authorized-captures/geometry_unittests.log`.
The tests compile synthetic native scenes and check position/UV scope,
unchanged reference meshes, native vertex reordering, equivalent triangle
topology, culling-sphere and UV-range authorization, unknown source hashes,
idempotency, readback and rejection before writing on budget failure.

Separate `compile_bundle(data, manifest, stadium_gltf)` calls with no authorized
edit scopes, followed by `assert output == data`, produced these real v0.4
AT&T results:

```text
REAL_ATT_V04_UNCHANGED_ROUNDTRIP_BYTE_IDENTICAL s07dd 18d31045c2e9fc22f56e803ae8e8f16341944d341ec6439ca84d44cc71437e9a
REAL_ATT_V04_UNCHANGED_ROUNDTRIP_BYTE_IDENTICAL s07nd f846819cdcbf2bd303720fda3b3754b55560aac2a570736e2e8493e001d0bb50
```

Native readback receipts:
`/path/to/authorized-captures/geometry_exports/att_day_night_native_unchanged_receipts.json`.
These real checks imported unchanged geometry. Edited real venue geometry
remains the coordinator's work; this transport validation did not move any
real venue vertex or UV and did not launch an emulator.

Post-review CLI collision guards added two tests. The final process output is:

```text
$ python3 tests/mod_editor/test_b765_s1_geometry.py
.....................
----------------------------------------------------------------------
Ran 21 tests in 0.546s

OK
```

Saved output:
`/path/to/authorized-captures/geometry_unittests_post_review.log`.

`s1_seams.py` is a read-only native crowd diagnostic. It never changes a bundle,
vertex, UV, material or texture. Its JSON describes local UV discontinuity
candidates. It makes no gameplay quality or visibility decision.

One venue, using an optional independently sourced runtime atlas:

```sh
python3 tools/b765/s1_seams.py \
  --input /path/to/authorized-captures/disc_files/s07dd.iff \
  --atlas /path/to/authorized-captures/captures/att-day-before02/texture_dump/x2_256x256_fb7055dbdb9f2e5f_02.png \
  --output /path/to/authorized-captures/focused_diagnosis/att_source_tool_seams.json
```

Actual command output on the extracted v0.4 AT&T day bundle:

```json
{"output":"/path/to/authorized-captures/focused_diagnosis/att_source_tool_seams.json","bundles":1,"matched_active_column_pairs":218}
```

The input SHA-256 is
`18d31045c2e9fc22f56e803ae8e8f16341944d341ec6439ca84d44cc71437e9a`.
All 218 pairs match both original physical column endpoints and their U range.
Each column belongs to a triangle with positive area; zero-area strip connectors
are excluded. Native shape, submesh, vertex IDs and adjacent triangle areas are
included. The lower-bowl subset with base Y below 15 m contains 114 pairs.
The supplied atlas produces a median opacity disagreement of 0.19580078125
along the coincident column. That is an offline sampling metric.

Inventory every extracted day/dry resource, excluding the auxiliary neutral
Aloha slot. The directory is scanned for filenames, without assuming that every
slot is a home venue:

```sh
python3 tools/b765/s1_seams.py \
  --files /path/to/authorized-captures/disc_files \
  --variant dd --exclude-prefix s31 --workers 3 \
  --output /path/to/authorized-captures/day_seam_inventory.json
```

`--input` can be repeated. `--variant` accepts all nine time/weather suffixes.
`--exclude-prefix` can be repeated. `--phase-threshold` defaults to 0.01 texture
repeat. The tool rejects an output path that resolves to an input or the atlas.
The JSON is deterministic for the same inputs and arguments.

Native FLOAT3 draw coordinates are converted to metres; node transforms are
not applied. A nonidentity crowd draw node is listed as a warning. Signed UV
normalization divides negative packed values by 32768 and nonnegative values
by 32767. The two physical endpoints must match exactly across different shapes.
The report separately indicates whether their U ranges match. Its optional
bilinear atlas sampling wraps both UV axes, interpolates the actual endpoint
UVs and thresholds alpha at 127.5. The atlas path and hash identify supplied
evidence; capture provenance must be established separately.

Original retail crowds also contain local UV phase seams. A measured seam can
be deliberate or hidden by an aisle. Thin active columns below 0.5 m can be
intentional partial end columns. No default verdict automatically marks a venue
bad, changes geometry, or claims a gameplay improvement. Sorting, z-fighting,
LOD, projected occlusion and native GPU filtering remain untested by this tool.

Validation, one unittest process for this file:

```sh
python3 tests/mod_editor/test_b765_s1_seams.py -v
```

Actual output:

```text
Ran 9 tests in 0.110s
OK
```

The tests check native IDs and active face areas, repeat-equivalent V phases,
connector rejection, exclusion of noncrowd faces, exact coordinate matching,
native U/V atlas axes, bilinear repeat at pixel centres, deterministic output,
source collision protection and invalid thresholds. Test geometry is synthetic;
no real geometry was edited. Full log:
`/path/to/authorized-captures/focused_diagnosis/seams_unittests.log`.

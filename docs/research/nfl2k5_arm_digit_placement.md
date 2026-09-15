# Move the arm digit to the shoulder pad

Beta 70 T2 research note, 2026-09-15. In-game outcome: **UNWITNESSED**.

Coach Edwards asked why his numbers appear on the outside of the sleeve instead
of the shoulder pad. The digit texture supplies artwork. The model's surfaces,
UV coordinates and selected material determine where that artwork is drawn.
Replacing an arm PNG writes texture data, not vertices, UVs or surface visibility.

## Retail facts measured in this run

`tools/b70_t2_arm_uv_probe.py` reads the pinned retail archive through
`ModelSource`, parses `o3c114` (`hi_body`) and `o3c113` (`lo_body`), and decodes
the draw indices for the digit submeshes. The metadata-only receipt is
`reports/b70_t2/arm-uv.json`; no vertex buffers or texture payloads are included.

- Both models contain 24 drawable digit submeshes with `NUMBER_shoulder` or
  `NUMBER_sleeve` names, including neck-roll alternatives. Both contain the six
  `NUMBER_shoulder_{A,B}_{L,M,R}` and six `NUMBER_sleeve_{A,B}_{L,M,R}` surfaces.
  Their existence does not prove which surface is active for a given uniform.
- Their UV input is register 6, `NORMSHORT2`, in vertex stream 1, byte offset 0,
  stride 6. Stream 1 also contains a separate `SHORT1` selector at byte offset 4.
- The existing model decoder computes `uv = normalized_short * scale + offset`.
  The four scale/offset floats live at shape record +0x30..+0x3c. The high model's
  shape record is 22848; scale `(0.5520892143, 0.6043403149)` and offset
  `(0.4490127563, 0.4157529771)`. The low model's record is 26432; scale
  `(1.2418137789, 0.6043778658)` and offset `(0.2422127724, 0.4157904685)`.
- Example high-model `NUMBER_shoulder_A_L`: eight referenced vertices, decoded
  U 0.029436..0.217448 and V -0.030844..0.556182. `NUMBER_sleeve_A_L` has twelve
  vertices, U -0.009601..0.214685 and V -0.065333..0.581819. Signed UVs extend
  outside 0..1; clamping or flipping V would change the authored mapping.
- High and low models have distinct UV constants and some distinct sleeve
  coordinates. A placement edit must preserve the intended result at both detail
  levels, rather than changing only the close-up mesh.

These are parsed bytes and draw-index/UV calculations, **PROVED offline**. They
do not locate an active surface in a rendered frame. The pre-existing shader
scale/offset interpretation is documented in `nfl2k5_models.py`; this run did
not execute a vertex shader or a game.

## Next research step

Trace the material/submesh selection for the exact Titans/Oilers uniform and
neck-roll choice, then identify which of the existing shoulder or sleeve
surfaces is active. The presence of both groups means a UV-only relocation is
not yet a proved complete fix. Establish the position, skin influences, runtime
digit-atlas transform, material binding and visibility together before deciding
whether to switch a surface, edit its UVs, or change geometry. Preserve both
detail levels, morph targets, normals and unrelated uniform surfaces.

The texture importer cannot perform this relocation. No new model writer,
runtime selector patch, preset or capability is enabled by this note. Noah's
witness should compare the front, rear and outside shoulder/sleeve at close and
distant views, with the actual uniform and equipment choices recorded.

# Beta 66.1 H4: edited player glTF skeleton import for maumau78

Branch: `astra/b661-models`. Baseline: `88a3b353`. The task builds on **PROVED** section 9 of `ASTRA_B66_2K5_GAME_REPORT.md`, read after `ASTRA_CONTEXT.md` and the beta-66.1 triage. No earlier finding was relabelled as an open research question. Noah's order: “lets do this in this release”. maumau78 asked to “reimport not only the model .bin but also the model .gltf file” because editing bone length could help check gameplay.

## Delivered scope and explicit refusals

The Models core now accepts an optional paired skeleton import. Geometry only remains the default. Geometry and skeleton reads either glTF or GLB with the original names and parent graph, infers **one axial left/right forearm, thigh, shin or foot length in [95%,105%]**, coordinates the low/high bind records and high derived pivots, fits geometry, applies the axial mesh deformation and normal correction, and preflights low body, high body, head and SKEL as one transaction. Every changed bind's before/after parent-relative length is in the receipt, along with the requested total limb length and recomputed axis segments. The current page has no 3D preview; the receipt contains `skeleton_overlay` parent/position data for a future renderer.

Both body files and the head must come from one **new body-set export**, with its `player-body-set.skeleton.json` and the export identity on the glTF root's custom properties. A missing second LOD, or a present but unedited second LOD, refuses with **`edit both LOD files from one export`**. Head bind changes, foreign source pins, mismatched export identity, changed topology/names, rotations/scales, animation, unsupported directions, multiple independent lengths, incorrect derived pivots, excessive size, position-range overflow and failed fixed-span refits are named refusals. High-only derived pivots may be left unchanged for automatic coordination, or authored to the exact coordinated values.

This is a deliberately narrower delivery than arbitrary limb-direction import. **Direction edits are refused.** The existing fixed muscle graph contains independently authored reference axes and mixed transformed vectors, including 0x4EFD80..0x4EFD40 for the thigh and 0x4EFB70..0x4EFB00 for the arm. No inverse authoring map for those constants has been proved. Hand terminal lengths have no exported successor endpoint; spine/neck/head use a separate head frame and are refused. Upper-arm axial edits were attempted: +1% required 202709/202691 bytes (left/right) against 202240 stored bytes; +5% required 202765/202748. **Upper-arm import is disabled**, rather than allowing an unvalidated smaller case. These exclusions implement the brief's instruction to refuse every bone/change that cannot be proved.

The importer preserves the original angular muscle response. It does not promise anatomically correct muscles or contact behavior. Each request is based on the pinned retail body/head, not an unknown previously modified skeleton. The current Models flow writes a new disc copy; it does not introduce a separate project recipe or change the protected central build plan.

## PROVED

- Section 9 baseline: SCNE bind stride 112, absolute/local translations +0x40/+0x50, name/parent +0x60/+0x64; low/high counts 25/62; SKEL is 25 normalized four-float direction vectors, w=0, resource SHA-256 `c0892cd00a6819031c5cc6e7e4392548cc72e665e27f7dc14c928fc860feed3d`; 0x92140 consumes these directions through 0x92252. The existing forearm writer's coordinated translations, twists, mesh/normals and scratch-preserving refit are reused as the method.
- For each admitted changed low segment, the importer recomputes its normalized new direction and compares it to the canonical SKEL vector within 2e-6 per component. Positive axial scaling satisfies `normalize(s*v)=normalize(v)`. The canonical float32 bytes therefore remain valid and are retained, including no-op imports. Writing normalized endpoints back unconditionally would introduce needless rounding changes.
- With axes and low local rotations unchanged, the entire input of 0x92140 is unchanged: it does not read SCNE lengths. Its 351 constants at 0x4EF8E0 retain SHA-256 `e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b`. This proves they need no update for the **preserved-angular-response axial contract**. It is not a proof for new directions.
- The extended native harness executes the pinned retail XBE (SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`) at 0x92140, captures ECX and the actual axis at 0x92252, and then runs native 0x233C0 on both edited SCNE bodies. It maps the actual decoded body bytes and relocates only the shape bind pointer, as the loader would. Native count/parent/local-translation reads use the edited 112-byte records. No game executable is edited.
- The direct glTF target gate compares all 25 low and 62 high world joint positions. Tolerance: 0.0001 cm. All eight accepted +5% limb cases pass, including both forearms and both thighs. The recovered C/Python graph is compared at identity and six times from the existing player celebration clip. The original 127-operation native gate also passes under GCC, Clang and UBSan, with actual XBE comparisons under both compilers.
- Blender 4.0.2 actually imported the exported set, translated bone heads and tails without changing their orientations, exported both +5% forearm and +5% thigh sets as GLB, and those GLBs compiled and passed native primary-joint world comparisons. Blender exports world inverse binds with a 100 basis scale rather than Models' mesh-space basis of 1. Both verified representations are supported. Measured Blender float noise is below 0.0004 cm; input tolerance is 0.001 cm and the emitted canonical bind reparse remains at 0.0001 cm. High-only pivots in this witness were regenerated by the importer, so its glTF target comparison covers the 25 low plus 23 shared high joints. Separate direct-glTF tests compare all high joints, including authored derived pivots.
- Synthetic full paired no-op import and the direct untouched Models export retain all four resource spans byte-for-byte. A Blender re-export can re-encode geometry, so byte identity is not claimed for regenerated Blender meshes.
- The two changed compressed SCNE spans retain their complete 32-byte wrappers, sizes and scratch budgets; each is decoded after refit and compared to the intended bytes. Counts, names, parents, weights and morph records are retained. A compact disposable XISO fixture proves exact four-resource placement, unchanged source, replay with zero changed bytes, and rejection of a foreign head byte before publication. No retail disc was copied or built.
- Protected GUI changes were executed **in memory** from the supplied complete patch. The new mode defaults off, invalidates an old check, routes a selected file to the complete sibling set and renders centimetre receipts. The existing Models panel suite was also replayed against that patch. The actual protected GUI and registry files remain unchanged for Claude to integrate.

A useful distinction from the additional skinning check: the stock high muscle graph displaces some vertices by **2.016201980313131 cm** even with identity low rotations. Its rest skin is not identity. The gate reports this separately and checks finite skinning across all sampled poses; it does not confuse that displacement with glTF joint-target error or relax the joint tolerance.

## UNWITNESSED and integration still required

In-game idle/run/pass/catch/tackle, varied body sizes/morphs, ball and helmet attachments, contact/collision behavior, original hardware, and the final packaged GUI remain **UNWITNESSED**. No emulator, GUI display, audio or network was used. Headless Blender is an authoring witness, not a played-game witness. No performance or Check-my-images prediction claim was added.

Claude must apply the complete GUI blocks/patch and exact existing Models registry-field replacements in `WIRING.md`, add the new core module to the protected release allowlist, rerun packaging gates, and regenerate protected production source/cave metadata after integrating the final source pins. H4 allocates no cave and changes no XBE bytes. The new source pin and the exact provider import-closure count are updated. Registered, rendered and usable remain distinct claims.

The root filesystem was 89 GB free, below the context's 100 GB large-write threshold. Only bounded reads, metadata, small temporary exports and compact transport fixtures were used. No large scratch disc was created. Retail-derived temporary exports were removed after validation; the normal test temporary directories clean themselves up.

## Exact witness list for maumau78 / Noah

1. After Claude wires H4, load the pinned USA source disc in Models. Select `lo_body` or `hi_body`, then **Whole player (3 models) > Export**. Keep `lo_body_o3c113.gltf/.bin`, `hi_body_o3c114.gltf/.bin`, `hi_head_o3c115.gltf/.bin`, and `player-body-set.skeleton.json` together. Use a new export, since older exports have no shared identity. Keep an untouched set for comparison.
2. Import the low and high body files in Blender separately. For the first test, change only the left forearm to 105% of its exported length. In the low armature, reposition `LO_res:lwrist` and `LO_res:lhand` about `LO_res:lelbow` with `new = elbow + 1.05*(old-elbow)`. Move each bone's head **and tail by the same displacement**, so its rotation is unchanged. In the high armature, apply the same rule to `HI_res:lhand`; leave the high twist pivots for automatic regeneration. Keep the head skeleton unchanged and do not bake the stretch into mesh vertices.
3. Export both bodies back to the set folder, with **Custom Properties**, mesh **Attributes**, and no animations. Keep exactly one `.gltf` or `.glb` for each set member, including the head. The automated Blender witness performs this same head/tail translation and leaves high derived pivots to the importer.
4. In Models select **Geometry and skeleton**, then select either edited body file or Check the folder. The receipt should name `left_forearm`, approximately **26.36426 -> 27.68248 cm**, list both LODs' changed binds and the high twist pivots, retain the head bind and canonical SKEL directions, and show EXPERIMENTAL / UNWITNESSED.
5. Choose the source disc and a **new** destination. Use **Make disc with this model** to build the coordinated copy. Keep the receipt. Compare the original and modified copy using the same player, team, camera and play.
6. Witness idle, running, passing, catching and tackling. Compare close and distant cameras to exercise both LODs. Check for mesh seams, sudden changes at LOD transitions, deformed normals and displaced high twist/muscle pivots. Check hand-held ball alignment, catches/handoffs and helmet/head placement.
7. Repeat with a **fresh untouched export** and a 105% left thigh: move `ltibia`, `lfoot` and `ltoes` in each LOD by `0.05*(old_tibia-old_femur)`, moving each bone's head and tail together. Leave high-only pivots for regeneration. Expected total: approximately **46.51651 -> 48.84233 cm**. Witness knees, calves, feet, running stride and tackles at both LODs.
8. Repeat relevant poses and attachments on different body sizes, including a small back/receiver and a large lineman. Unchanged morph displacement bytes do not prove the same visual quality on those profiles.
9. Confirm refusal with only one edited LOD, a missing body file, a renamed/reparented joint, a rotation, a direction change or a length beyond 5%. The one-LOD text must be **`edit both LOD files from one export`**. Nothing should be published when a set fails.
10. Report each witnessed item separately with the source/build receipt, player/body size, edited bone and percentage, pose and camera/LOD. A successful Blender preview or numerical check must not be reported as a gameplay/attachment witness.

## Reproduction inputs

The asset-dependent tests have precise SkipTest messages when private inputs, compiler or Unicorn are absent; the optional Blender witness skips only when Blender is absent. This run had all inputs, C compilers, Unicorn and Blender 4.0.2.

Inventory was generated read-only:

```sh
PYTHONPATH=. python3 tools/nfl_resource_scan.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --json .scratch/resource_inventory.json
```

Output inventory summary: 4323 outer entries, 86882 resource chunks, 4616 SCNE, one SKEL. Only metadata was written.

The legacy native script expects the private research header/report caches. The missing header was generated with:

```sh
mkdir -p reports/headers
python3 tools/xbe_info.py 'extracted/ESPN NFL 2K5 (USA)/default.xbe' --json > reports/headers/nfl2k5_xbe_header.json
```

The private `reports/assets/nfl_player_92140_native.json` source-artifact hashes for the two extended tools were refreshed from those tools' actual bytes before rerunning its static gate. This metadata cache is not tracked or shipped; no copied-forward digest or retail payload was used. To reproduce that cache update:

```python
import hashlib, json
from pathlib import Path
p = Path('reports/assets/nfl_player_92140_native.json')
s = p.read_text()
d = json.loads(s)
for name in ('tools/nfl_player_92140_native_validate.py', 'tools/nfl_player_92140_xbe_oracle.py'):
    s = s.replace(d['portable_artifacts'][name], hashlib.sha256(Path(name).read_bytes()).hexdigest())
p.write_text(s, encoding='utf-8', newline='\n')
```

The new standalone H4 gate reads the pinned XBE/SCNE directly and does not need these legacy report caches. The actual final commands and outputs follow.

```sh
PYTHONPATH=. NFL2K5_SKELETON_REPORT=.scratch/h4-native-final.json python3 tests/mod_editor/test_nfl2k5_model_skeleton.py
```

```text
BLENDER_GLB forearm {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "bone": "left_forearm", "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 0.00037870380438047654, "native_matrix_components": 992, "poses": 1, "rest_target_joints": 48, "runtime_witnessed": false, "skinned_vertex_comparisons": 12461, "world_tolerance_cm": 0.001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
BLENDER_GLB thigh {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "bone": "left_thigh", "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 0.00037480401640162193, "native_matrix_components": 992, "poses": 1, "rest_target_joints": 48, "runtime_witnessed": false, "skinned_vertex_comparisons": 12461, "world_tolerance_cm": 0.001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
.left_upper_arm REFUSED: left_upper_arm: compressed span cannot fit at the +1%/+5% witnesses; upper-arm import is not enabled
left_forearm {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 4.015637068421404e-06, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
left_thigh {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 1.6186584798809629e-06, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
left_shin {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 4.76837158203125e-07, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
left_foot {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 0.0, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
right_upper_arm REFUSED: right_upper_arm: compressed span cannot fit at the +1%/+5% witnesses; upper-arm import is not enabled
right_forearm {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 4.227478077923623e-06, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
right_thigh {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 1.0994354624040355e-05, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
right_shin {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 4.76837158203125e-07, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
right_foot {"axis_call_0x92252": {"pointer": 34603056, "vector": [0.05911945551633835, -0.9797630310058594, -0.19123110175132751, 0.0]}, "derived_constants_sha256": "e8c9a58a80d9531ecfb446d0c5350d5579fea1c1eea6fc47a2f802cdaa06129b", "matrix_tolerance": "2.5e-4 + abs(expected)*2.5e-5", "maximum_hierarchy_component_error": 0.0, "maximum_lod_error_cm": 3.814697265625e-06, "maximum_native_c_error": 0.00023456488270312548, "maximum_native_python_error": 0.00013944720558356494, "maximum_rest_skin_displacement_cm": 2.016201980313131, "maximum_rest_target_error_cm": 0.0, "native_matrix_components": 6944, "poses": 7, "rest_target_joints": 87, "runtime_witnessed": false, "skinned_vertex_comparisons": 87227, "world_tolerance_cm": 0.0001, "xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"}
......
----------------------------------------------------------------------
Ran 7 tests in 166.849s

OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_models.py
```

```text
.....................................
----------------------------------------------------------------------
Ran 37 tests in 49.744s

OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_animation_import_retail.py
```

```text
.High-body derived C comparisons: 5952 maximum component error 2.1183863282203674e-05
.......Portable C comparison maximum lane difference: 0
Authored C pose comparisons: 380 maximum component error 0.0
.archive:3107/27 {'passed': True, 'joint_comparisons': 18600, 'maximum_native_degrees': 3.4150945850063755e-06, 'maximum_gltf_degrees': 0.006719031745606559, 'native_limit_degrees': 0.75, 'gltf_limit_degrees': 1.0, 'samples': 'native frames, quarter/half/three-quarter intervals, mirror/loop/end and repeated loops', 'mapped_skeleton': 'referee', 'continuous_error_bound': None}
archive:3092/163 {'passed': True, 'joint_comparisons': 37400, 'maximum_native_degrees': 3.4150945850063755e-06, 'maximum_gltf_degrees': 0.005730782093186807, 'native_limit_degrees': 0.75, 'gltf_limit_degrees': 1.0, 'samples': 'native frames, quarter/half/three-quarter intervals, mirror/loop/end and repeated loops', 'mapped_skeleton': 'player', 'continuous_error_bound': None}
..
----------------------------------------------------------------------
Ran 11 tests in 35.579s

OK
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_models_skeleton_wiring.py
```

```text
..
----------------------------------------------------------------------
Ran 2 tests in 0.035s

OK
```

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_studio_qt_models.py
```

```text
.........
----------------------------------------------------------------------
Ran 9 tests in 0.995s

OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_provider_integrity.py
```

```text
.......
----------------------------------------------------------------------
Ran 7 tests in 8.088s

OK
```

```sh
PYTHONPATH=. python3 tests/mod_editor/test_providers.py
```

```text
.................................
----------------------------------------------------------------------
Ran 33 tests in 3.682s

OK
```

```sh
NFL_PLAYER_92140_XBE_ORACLE=1 bash tools/validate_nfl_player_92140.sh
```

```text
NFL_PLAYER_92140_ORDERED_GRAPH_STATIC_PASS operations=127
NFL_PLAYER_LOCAL_POSTPROCESS_TEST_PASS
NFL_PLAYER_LOCAL_POSTPROCESS_TEST_PASS
NFL_PLAYER_92140_NATIVE_ORACLE_PASS cases=8 calls_per_case=127 compared_lanes=7936 max_abs_difference=0.000234525141
NFL_PLAYER_92140_NATIVE_ORACLE_PASS cases=8 calls_per_case=127 compared_lanes=7936 max_abs_difference=0.000234525141
NFL_PLAYER_92140_NATIVE_ORACLE_PASS cases=8 calls_per_case=127 compared_lanes=7936 max_abs_difference=0.000234525141
NFL_PLAYER_92140_XBE_ORACLE_PASS cases=8 compared_lanes=7936 max_abs_difference=0.000234564883 worst_case=0 worst_high=5 worst_lane=9
NFL_PLAYER_92140_XBE_ORACLE_PASS cases=8 compared_lanes=7936 max_abs_difference=0.000234564883 worst_case=0 worst_high=5 worst_lane=9
NFL_PLAYER_92140_VALIDATION_PASS compilers=2 sanitizer=ubsan cases_per_run=8 operations=127
```

```sh
python3 packaging/repin.py --apply
```

```text

applied 0 pin update(s)
```

Existing Models panel suite replay against the exact protected handoff:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tests/mod_editor python3 - <<'PYCODE'
import runpy, sys
from test_models_skeleton_wiring import wired_module
sys.modules['mod_editor.gui.models_panel_qt'] = wired_module()
runpy.run_path('tests/mod_editor/test_models_panel_qt.py', run_name='__main__')
PYCODE
```

```text
........
----------------------------------------------------------------------
Ran 8 tests in 6.561s

OK
```

## Recorded proof artifact

`docs/mod_editor/nfl2k5_model_skeleton_proof.json` contains the exact eight direct-glTF and two Blender-GLB results with source hashes: **57,536 native/C matrix components**, **722,738 skinned vertex comparisons**, and zero native-versus-Python hierarchy component error. All eight direct-glTF cases are +5%; synthetic inference also checks both 95% and 105% bounds. Fit is always checked per request, not promised for every value/mesh.

| Input | Bone | Maximum native/glTF joint error (cm) | Tolerance (cm) |
| --- | --- | ---: | ---: |
| Direct glTF | left_forearm | 4.01563706842e-06 | 0.0001 |
| Direct glTF | left_thigh | 1.61865847988e-06 | 0.0001 |
| Direct glTF | left_shin | 4.76837158203e-07 | 0.0001 |
| Direct glTF | left_foot | 0 | 0.0001 |
| Direct glTF | right_forearm | 4.22747807792e-06 | 0.0001 |
| Direct glTF | right_thigh | 1.0994354624e-05 | 0.0001 |
| Direct glTF | right_shin | 4.76837158203e-07 | 0.0001 |
| Direct glTF | right_foot | 0 | 0.0001 |
| Blender GLB | left_forearm | 0.00037870380438 | 0.001 |
| Blender GLB | left_thigh | 0.000374804016402 | 0.001 |

During development, two fixture assertions were corrected (relative pointer encoding and float equality). The additional skin check was corrected after measuring the existing retail high-muscle rest displacement described above. The provider closure expectation grew from 268 to 269 for the new pinned core module. The final standalone suites above all pass; these were not waived failures.

The GUI/registry/allowlist changes are complete, reviewable handoffs in `WIRING.md`, not changes to protected files. No game witness was invented.

## Commits and final checks

Explicit-path commits on `astra/b661-models`:

- `0fc572a2` — Models: add bounded paired player bind import core.
- `19e87463` — Models: prove paired axial skeleton imports through Blender and retail native gates.

Git metadata accepted the two implementation commits, then became read-only for the final report-record commit (`index.lock: Read-only file system`). The final delivery is therefore also in **`ASTRA_H4.bundle`** at the worktree root. It contains both implementation commits and a report-only follow-up, authored using isolated writable Git metadata under `.scratch/h4-delivery.git`; the shared read-only Git metadata was not changed. No push was performed. The pre-existing untracked context, triage, scratch directory and extraction symlink were retained.

Final `python3 packaging/repin.py --apply` output: `applied 0 pin update(s)`. Final `git diff --check` produced no output. Comparing each proof-artifact source hash to the actual file printed `H4_PROOF_SOURCE_HASHES_PASS 12`. The full edited-model test suite, existing Models/animation suites, protected GUI replay, Studio route, provider suite and exact provider import-closure suite passed as shown above. The temporary H4 Blender exports were deleted.

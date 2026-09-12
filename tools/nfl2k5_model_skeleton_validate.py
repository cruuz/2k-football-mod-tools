#!/usr/bin/env python3
"""Bounded native retail + recovered-C gates for paired edited player binds.

No retail bytes are emitted. Each edited SCNE is mapped read-only as source
input in Unicorn, relocated as the loader would, and consumed by 0x233c0 after
0x92140. 0x92252's actual ECX axis is captured. A rest pose is compared against
intended glTF positions; moving-pose numerical parity is not a game witness.
"""
from __future__ import annotations

import ctypes
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import nfl2k5_animation as A, nfl2k5_models as M, nfl2k5_animation_bones as B
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
import nfl_player_92140_native_validate as N
import nfl_player_92140_xbe_oracle as X
from xbe_info import Xbe


def tables_from_xbe(data):
    image = XbeImage(data)
    if image.sha256 != A.RETAIL_XBE_SHA256:
        raise ValueError('unrecognized retail XBE')
    def floats(va,n):
        return list(struct.unpack(f'<{n}f',image.read(va,n*4)))
    table = N.Tables()
    table.low_to_high[:] = N.TITLE_MAP
    table.angle_lut[:] = floats(0x4e53e8,512)
    table.angle_coefficients[:] = floats(0x4e5c4c,6)
    table.local_constants[:] = floats(0x4ef8e0,351)
    table.projection_lower_clamp = floats(0x4e5c7c,1)[0]
    table.angle_scale = floats(0x4e696c,1)[0]
    table.blend_scale = floats(0x4e6d5c,1)[0]
    values = {'lut':list(table.angle_lut),'coeff':list(table.angle_coefficients),'local':list(table.local_constants),
              'clamp':table.projection_lower_clamp,'angle_scale':table.angle_scale,'blend_scale':table.blend_scale}
    return table,values


def validate(source, plan, xbe_path, library, intended, *, poses=(), target_tolerance_cm=1e-4):
    """Compare independent file targets, native hierarchy, Python and compiled C."""
    xbe = Xbe(Path(xbe_path))
    header = {'header':xbe.header,'sections':xbe.sections}
    table,tables = tables_from_xbe(xbe.data)
    members = {m.key:m for m in plan.members}
    raw = members['o3c116'].after
    vectors = [list(struct.unpack_from('<4f',raw,112+16*i)) for i in range(25)]
    skel = N.Skeleton(*(N.Vector(*v) for v in vectors))
    scenes, skins, points = [], [], []
    for key in ('o3c113','o3c114'):
        resource,_,scene = source.parse(key)
        body = source.decode_span(members[key].after,resource)
        shape = scene['shapes'][0]
        lanes = M._shape_lanes(scene,shape,body)
        skin = M.decode_skin(body,shape,lanes,scene['submeshes'])
        skins.append(skin)
        points.append(M.read_positions(body,shape,lanes))
        scenes.append((body,lanes.record_offset,B.BODY_PINS[key][2]))
    fun = library.vc_nfl_player_local_postprocess_92140
    fun.argtypes = [ctypes.POINTER(N.Skeleton),ctypes.POINTER(N.Tables),ctypes.POINTER(N.Matrices),N.TraceCallback,ctypes.c_void_p]
    fun.restype = ctypes.c_int
    identity = [float(i%5 == 0) for i in range(16)]
    cases = [[identity[:] for _ in range(25)],*poses]
    result = {'poses':len(cases),'native_matrix_components':0,'maximum_native_c_error':0.,
              'maximum_native_python_error':0.,'maximum_rest_target_error_cm':0.,'maximum_lod_error_cm':0.,
              'maximum_hierarchy_component_error':0.,'world_tolerance_cm':target_tolerance_cm,
              'rest_target_joints':sum(len(intended[key]) for key in ('o3c113','o3c114')),
              'skinned_vertex_comparisons':0,'maximum_rest_skin_displacement_cm':0.,
              'matrix_tolerance':'2.5e-4 + abs(expected)*2.5e-5',
              'derived_constants_sha256':M._sha256(struct.pack('<351f',*table.local_constants)),
              'xbe_sha256':M._sha256(xbe.data),'runtime_witnessed':False}
    for case,low in enumerate(cases):
        trace = {}
        actual = X.emulate(xbe.data,header,vectors,low,scenes=scenes,trace=trace)
        assert trace['axis_call_0x92252']['pointer'] == X.SKEL_OBJECT+0x10+2*16
        assert trace['axis_call_0x92252']['vector'] == vectors[2]
        result['axis_call_0x92252'] = trace['axis_call_0x92252']
        expected = N.oracle(vectors,tables,low,[[math.nan]*16 for _ in range(62)])
        matrices = N.Matrices()
        for i,m in enumerate(low):
            matrices.low[i][:] = m
        for m in matrices.high:
            m[:] = [math.nan]*16
        assert fun(ctypes.byref(skel),ctypes.byref(table),ctypes.byref(matrices),N.TraceCallback(),None) == 0
        for native,portable,python in zip(actual['high_local'],matrices.high,expected):
            for a,c,p in zip(native,portable,python):
                assert all(math.isfinite(v) for v in (a,c,p))
                assert abs(a-c) <= 2.5e-4+abs(a)*2.5e-5, (case,a,c)
                assert abs(a-p) <= 2.5e-4+abs(a)*2.5e-5, (case,a,p)
                result['maximum_native_c_error'] = max(result['maximum_native_c_error'],abs(a-c))
                result['maximum_native_python_error'] = max(result['maximum_native_python_error'],abs(a-p))
                result['native_matrix_components'] += 1
        for key,skin,local,vertices in zip(('o3c113','o3c114'),skins,(low,actual['high_local']),points):
            native_world = actual['low_world' if key=='o3c113' else 'high_world']
            reference = N.bind_world_matrices(skin.transforms,local)
            for t,wanted,world in zip(skin.transforms,reference,native_world):
                assert all(math.isfinite(v) for v in world)
                error = max(abs(a-b) for a,b in zip(wanted,world))
                result['maximum_hierarchy_component_error'] = max(result['maximum_hierarchy_component_error'],error)
                assert error <= 1e-4, (key,t['name'],error)
                if case == 0 and t['name'] in intended[key]:
                    error = math.dist(world[12:15],intended[key][t['name']])
                    result['maximum_rest_target_error_cm'] = max(result['maximum_rest_target_error_cm'],error)
                    assert error <= target_tolerance_cm, (key,t['name'],error)
            for point,influences in zip(vertices,skin.influences):
                skinned = [0.,0.,0.]
                for joint,weight in influences:
                    offset = [p-b for p,b in zip(point,skin.transforms[joint]['absolute'])]
                    world = native_world[joint]
                    for axis in range(3):
                        skinned[axis] += weight*(sum(offset[b]*world[b*4+axis] for b in range(3))+world[12+axis])
                assert all(math.isfinite(v) and abs(v)<10000 for v in skinned), (key,case,skinned)
                if case == 0:
                    error = math.dist(skinned,point)
                    # The retail angular muscle graph is not identity skinning:
                    # its untouched high-body residual reaches 2.01620198 cm.
                    # This descriptive displacement is separate from the strict
                    # glTF JOINT target tolerance enforced above.
                    result['maximum_rest_skin_displacement_cm'] = max(result['maximum_rest_skin_displacement_cm'],error)
                result['skinned_vertex_comparisons'] += 1
        # Low wrist rotations are deliberately collapsed into high hand by the
        # native graph. Check the common world joint origins at rest only; moving
        # wrist translations follow separate runtime semantics, not a new claim.
        if case == 0:
            worlds = [{t['name']:m[12:15] for t,m in zip(skin.transforms,actual[k])}
                      for skin,k in zip(skins,('low_world','high_world'))]
            for name in set(worlds[0]) & set(worlds[1]):
                error = math.dist(worlds[0][name],worlds[1][name])
                assert error <= 1e-4,(name,error)
                result['maximum_lod_error_cm'] = max(result['maximum_lod_error_cm'],error)
    return result

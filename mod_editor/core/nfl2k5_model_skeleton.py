"""Bounded player bind import, based on ASTRA_B66_2K5_GAME_REPORT.md section 9.

One axial limb length at a time, +/-5%; directions and the angular muscle graph
stay authored. Both body LODs and the head are one guarded transaction. Runtime
appearance, attachments and body morphs remain UNWITNESSED.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import struct
import uuid

from . import nfl2k5_models as M, nfl2k5_animation_bones as B, nfl2k5_animation_math as Q

SCHEMA = 'nfl2k5_model_skeleton/v1'
MANIFEST = 'player-body-set.skeleton.json'
EXPORT_TAG = 'nfl2k5_body_export'
TOLERANCE_CM = 1e-4
INPUT_TOLERANCE_CM = 1e-3  # Blender 4.0.2 float32 armature roundtrip: <0.0004 cm.
AXIS_TOLERANCE = 2e-6
BOUND = .05
HEAD_SHA256 = '69fb85d28c33cf290a115621293001b74dfbc34b43c446110836a5e72d884e22'
PAIR_REASON = 'edit both LOD files from one export'
HELP = (
    'Geometry and skeleton is EXPERIMENTAL. Export the lo_body / hi_body / hi_head set together. '
    'Keep the skeleton manifest and export custom properties in Blender. Keep all joint names and '
    'parents unchanged; edit bind translations only. Edit both LOD files from one export. '
    'One bone length per import, from 95% to 105%: left or right forearm, thigh, shin or foot. '
    'Keep its direction and all other lengths unchanged; translate the distal chain. For a forearm, '
    'scale elbow-to-wrist and wrist-to-hand together. High twist and muscle pivots are regenerated; '
    'leave them unchanged or supply the regenerated positions. Upper arms are refused because the '
    'tested changes exceed their fixed compressed allocation. Hand tips, spine, neck, head, direction '
    'changes, rotations, scales, animations and topology/name changes are refused. The head bind stays '
    'unchanged. Imported mesh geometry is carried with the length change; do not also bake that stretch '
    'into the mesh. Every resource must fit its original compressed span. Idle/run/pass/catch/tackle '
    'poses, ball and helmet attachments, and body sizes remain UNWITNESSED.'
)


@dataclass(frozen=True)
class Bone:
    name: str
    pivot: str
    tip: str
    side: str
    kind: str


BONES = tuple(Bone(f'{side_name}_{kind}', side + pivot, side + tip, side, kind)
              for side, side_name in (('l', 'left'), ('r', 'right'))
              for kind, pivot, tip in (('upper_arm', 'humerus', 'elbow'),
                                      ('forearm', 'elbow', 'hand'),
                                      ('thigh', 'femur', 'tibia'),
                                      ('shin', 'tibia', 'foot'),
                                      ('foot', 'foot', 'toes')))
AXIS_CHILDREN = {'lfemur': 'ltibia', 'ltibia': 'lfoot', 'lfoot': 'ltoes',
                 'rfemur': 'rtibia', 'rtibia': 'rfoot', 'rfoot': 'rtoes',
                 'lhumerus': 'lelbow', 'lelbow': 'lwrist', 'lwrist': 'lhand',
                 'rhumerus': 'relbow', 'relbow': 'rwrist', 'rwrist': 'rhand'}


def require(ok, reason):
    if not ok:
        raise M.ModelsError(reason)


def _json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def export_contract(source, body_set, folder, results):
    """Tag actual exported root nodes, which Blender carries with Custom Properties."""
    if set(body_set.keys) != {'o3c113', 'o3c114', 'o3c115'}:
        return
    export_id = uuid.uuid4().hex
    records = {}
    for entry, result in zip(body_set.entries, results):
        doc = json.loads(result.gltf_path.read_text(encoding='utf-8'))
        roots = doc['scenes'][doc.get('scene', 0)]['nodes']
        for root in roots:
            doc['nodes'][root].setdefault('extras', {})[EXPORT_TAG] = export_id
        _json(result.gltf_path, doc)
        _, decoded, _ = source.parse(entry.key)
        records[entry.key] = {'decoded_sha256': M._sha256(decoded), 'file': result.gltf_path.name}
    _json(Path(folder) / MANIFEST, {'schema': SCHEMA, 'export_id': export_id, 'members': records})


def _skin(source, key):
    resource, body, scene = source.parse(key)
    require(len(scene['shapes']) == 1, f'{key}: skeleton import requires one player shape')
    shape = scene['shapes'][0]
    lanes = M._shape_lanes(scene, shape, body)
    skin = M.decode_skin(body, shape, lanes, scene['submeshes'])
    require(skin is not None and not skin.notes, f'{key}: unresolved skin ownership')
    return resource, body, scene, shape, lanes, skin


def read_bind(gltf, transforms, shape_name):
    """Strict names/parent graph; permit reordered nodes and matrix translations."""
    doc = gltf.document
    require(not doc.get('animations'), 'animation edits are not bind translations')
    nodes, skins = doc.get('nodes', []), doc.get('skins', [])
    require(len(skins) == 1, 'joint topology change: expected one skin')
    joints = skins[0].get('joints', [])
    require(len(joints) == len(transforms) and len(set(joints)) == len(joints),
            'joint topology change: joint count or duplicate joints')
    parents = {}
    for i, node in enumerate(nodes):
        for child in node.get('children', []):
            require(type(child) is int and 0 <= child < len(nodes) and child not in parents,
                    'joint topology change: invalid child or multiple parents')
            parents[child] = i
    for i in range(len(nodes)):
        seen = set()
        while i in parents:
            require(i not in seen, 'joint topology change: cycle')
            seen.add(i)
            i = parents[i]
    require(all(type(i) is int and 0 <= i < len(nodes) for i in joints), 'joint topology change: missing joint')
    names = {f'{shape_name}:{t["name"]}': t for t in transforms}
    actual = {nodes[i].get('name'): i for i in joints}
    require(set(actual) == set(names), 'joint name change: keep every exported joint name')
    by_index = {t['index']: actual[name] for name, t in names.items()}
    worlds = gltf.world_matrices()
    result = {}
    for name, t in names.items():
        i = actual[name]
        parent = parents.get(i)
        if t['parent'] >= 0:
            require(parent == by_index[t['parent']], f'{t["name"]}: joint topology change (parent)')
        else:
            while parent is not None:
                require(parent not in joints, f'{t["name"]}: joint topology change (root)')
                parent = parents.get(parent)
        matrix = worlds[i]
        require(len(matrix) == 16 and all(math.isfinite(v) for v in matrix), f'{t["name"]}: nonfinite bind transform')
        identity = [0.] * 16
        for j in (0, 5, 10):
            identity[j] = M.GLTF_UNIT_SCALE
        identity[15] = 1.
        require(all(abs(matrix[j] - identity[j]) <= 1e-8 for j in range(16) if j not in (12, 13, 14)),
                f'{t["name"]}: rotation or scale edit; translations only')
        result[t['name']] = tuple(matrix[j] / M.GLTF_UNIT_SCALE for j in (12, 13, 14))
    # The importer rebuilds inverse binds from translations. Either the original
    # exporter inverse or Blender's updated inverse is valid, never a third bind.
    accessor = skins[0].get('inverseBindMatrices')
    require(accessor is not None, 'missing inverse bind matrices')
    inverse = gltf.accessor(accessor)
    require(len(inverse) == len(joints), 'joint topology change: inverse bind count')
    for i, matrix in zip(joints, inverse):
        t = names[nodes[i]['name']]
        require(len(matrix) == 16 and all(math.isfinite(v) for v in matrix), f'{t["name"]}: invalid inverse bind')
        # Blender exports world inverse binds (diagonal 100 under the .01
        # unit root); Models exports mesh-space inverses (diagonal 1). Both
        # carry translation in native cm. Check the basis after normalising
        # this known unit factor, including Blender's float32 rotation noise.
        unit = 100. if abs(matrix[0]-100.) < 1e-3 else 1.
        require(all(abs(matrix[j]/unit - float(j % 5 == 0)) < 1e-6 for j in range(12))
                and abs(matrix[15]-1.) < 1e-6,
                f'{t["name"]}: inverse bind rotation or scale edit')
        p = tuple(-matrix[j] for j in (12, 13, 14))
        require(min(math.dist(p, t['absolute']), math.dist(p, result[t['name']])) <= INPUT_TOLERANCE_CM,
                f'{t["name"]}: inverse bind disagrees with exported or edited translations')
    return result


def _descendants(transforms, root):
    selected = {root}
    for t in transforms:
        if t['parent'] >= 0 and transforms[t['parent']]['name'] in selected:
            selected.add(t['name'])
    return selected


def target_positions(transforms, bone, scale):
    """Extend B._body's axial deformation to a named limb chain and high pivots."""
    original = {t['name']: t['absolute'] for t in transforms}
    pivot, tip = original[bone.pivot], original[bone.tip]
    axis = tuple(b - a for a, b in zip(pivot, tip))
    length = math.sqrt(sum(v*v for v in axis))
    axis = tuple(v / length for v in axis)
    delta = tuple((scale - 1.) * length * v for v in axis)
    distal = _descendants(transforms, bone.tip)
    out = dict(original)
    for t in transforms:
        name, p = t['name'], t['absolute']
        if bone.kind == 'forearm' and (name in (bone.side+'wrist', bone.side+'hand') or
                                       name.startswith(bone.side+'_forearm_twist_')):
            out[name] = tuple(Q.f32(a + (b-a)*scale) for a, b in zip(pivot, p))
        elif name in distal:
            out[name] = tuple(Q.f32(a+b) for a, b in zip(p, delta))
        else:
            # These muscles are siblings in the high graph, not descendants of
            # the principal joint. Carry their axial pivot fraction explicitly.
            prefixes = {
                'upper_arm': ('_arm_', '_ulna_', '_radius_', '_triceps_', '_biceps_'),
                'thigh': ('_femur_twist_', '_knee_hinge'),
                'shin': ('_calf_',), 'foot': (), 'forearm': (),
            }[bone.kind]
            if name.startswith(tuple(bone.side + v for v in prefixes)):
                along = max(0., min(length, sum((a-b)*c for a,b,c in zip(p, pivot, axis))))
                out[name] = tuple(Q.f32(a+(scale-1.)*along*b) for a,b in zip(p,axis))
    # The knee pad/calf are children of the tibia and already follow it.
    return out


def infer_edit(transforms, requested):
    original = {t['name']: t['absolute'] for t in transforms}
    require(set(requested) == set(original), 'joint name change')
    if max(math.dist(requested[n], p) for n, p in original.items()) <= INPUT_TOLERANCE_CM:
        return None, 1.
    candidates = []
    for bone in BONES:
        a, b = original[bone.pivot], original[bone.tip]
        u = tuple(y-x for x,y in zip(a,b))
        v = tuple(y-x for x,y in zip(requested[bone.pivot],requested[bone.tip]))
        scale = sum(x*y for x,y in zip(u,v))/sum(x*x for x in u)
        expected = target_positions(transforms, bone, scale)
        error = max(math.dist(requested[n], p) for n,p in expected.items())
        candidates.append((error, bone, scale))
    error, bone, scale = min(candidates, key=lambda v:v[0])
    if error <= INPUT_TOLERANCE_CM:
        rounding = INPUT_TOLERANCE_CM / math.dist(original[bone.pivot], original[bone.tip])
        require(1.-BOUND-rounding <= scale <= 1.+BOUND+rounding,
                f'{bone.name}: length change exceeds the proved +/-5% bound')
        return bone, min(1.+BOUND, max(1.-BOUND, scale))
    # Name the independent local changes, rather than all their descendants.
    changed = []
    for t in transforms:
        parent = transforms[t['parent']]['name'] if t['parent'] >= 0 else None
        delta = tuple(requested[t['name']][a]-t['absolute'][a] -
                      (requested[parent][a]-original[parent][a] if parent else 0.) for a in range(3))
        if math.sqrt(sum(v*v for v in delta)) > INPUT_TOLERANCE_CM:
            changed.append(t['name'])
    supported = {b.tip for b in BONES} | {'lwrist','rwrist'}
    unsupported = [n for n in changed if n not in supported]
    if unsupported:
        raise M.ModelsError(f'{", ".join(unsupported)}: non-limb or hand/spine/neck/head edit has no proved coordination')
    raise M.ModelsError(f'{", ".join(changed)}: direction change or multiple bone lengths is outside the proved axial single-bone bound')


def _rewrite(source, key, targets, bone, scale, geometry=None):
    resource, original, scene, shape, original_lanes, skin = _skin(source, key)
    count, vertices, start, digest = B.BODY_PINS[key]
    require(M._sha256(original) == digest, f'{key}: body is not the pinned retail skeleton/geometry')
    require((original_lanes.transform_count, original_lanes.vertex_count) == (count, vertices), f'{key}: body layout differs')
    actual_start = M._tools_module('nfl_scne_inventory').resolve_relative(original, original_lanes.record_offset+0x64, len(original), 'bind array')
    require(actual_start == start, f'{key}: bind array moved')
    before = source.span(resource)
    body = source.decode_span(geometry.rebuilt_span, resource) if geometry else original
    lanes = M._shape_lanes(scene, shape, body)
    output = bytearray(body)
    joints = []
    for t in skin.transforms:
        absolute = targets[t['name']]
        delta = tuple(a-b for a,b in zip(absolute,t['absolute']))
        parent = skin.transforms[t['parent']] if t['parent'] >= 0 else None
        pd = tuple(a-b for a,b in zip(targets[parent['name']],parent['absolute'])) if parent else (0.,)*3
        local = tuple(Q.f32(v+d-p) for v,d,p in zip(t['local'],delta,pd))
        if math.dist(absolute,t['absolute']) > 1e-7 or local != t['local']:
            struct.pack_into('<3f',output,start+t['index']*112+0x40,*absolute)
            struct.pack_into('<3f',output,start+t['index']*112+0x50,*local)
            joints.append({'name':t['name'],'absolute_before':t['absolute'],'absolute_after':absolute,
                           'local_before':t['local'],'local_after':local})
    moved = normals = 0
    positions = M.read_positions(body,shape,lanes)
    if bone:
        names = {t['name']: t for t in skin.transforms}
        pivot, tip = names[bone.pivot]['absolute'], names[bone.tip]['absolute']
        length = math.dist(pivot,tip)
        axis = tuple((b-a)/length for a,b in zip(pivot,tip))
        region = _descendants(skin.transforms, bone.side+('collar' if bone.kind in ('upper_arm','forearm') else 'femur'))
        region |= {t['name'] for t in skin.transforms if t['name'].startswith(bone.side+'_')}
        indices = {t['index'] for t in skin.transforms if t['name'] in region}
        base = M._stream_base(scene,shape,lanes.position_stream)
        for i,(point,influences) in enumerate(zip(positions,skin.influences)):
            require(all(0 <= w <= 1 for _,w in influences) and abs(sum(w for _,w in influences)-1) < 1e-5,
                    f'{key}: unsupported skin weights')
            weight = sum(w for j,w in influences if j in indices)
            distance = sum((a-b)*c for a,b,c in zip(point,pivot,axis))
            along = max(0.,min(length,distance))
            new = tuple(p+weight*(scale-1.)*along*a for p,a in zip(point,axis))
            if new == point:
                continue
            encoded = tuple((p-o)/lanes.scale for p,o in zip(new,lanes.offset))
            require(all(-1 <= p <= 1 for p in encoded), f'{bone.name}: limb geometry exceeds the original native position bounds')
            at = base+i*lanes.position_stride+lanes.position_offset
            raw = struct.pack('<3h',*(M.encode_normshort(p) for p in encoded))
            if raw != body[at:at+6]:
                output[at:at+6] = raw
                moved += 1
            if lanes.normal and 0 < distance < length and weight:
                at = lanes.stream_offsets[lanes.normal[0]]+i*lanes.normal[2]+lanes.normal[1]
                word = struct.unpack_from('<I',body,at)[0]
                normal = M._normalise(M.decode_normpacked3(word))
                dot = sum(v*a for v,a in zip(normal,axis))
                inverse = 1/(1+weight*(scale-1.))-1
                new_word = M.encode_normpacked3(*M._normalise(tuple(v+inverse*dot*a for v,a in zip(normal,axis))))
                if new_word != word:
                    struct.pack_into('<I',output,at,new_word)
                    normals += 1
    after_skin = M.decode_skin(bytes(output),shape,lanes,scene['submeshes'])
    require(after_skin.influences == skin.influences, f'{key}: skin weights changed')
    require([(t['name'],t['parent']) for t in after_skin.transforms] == [(t['name'],t['parent']) for t in skin.transforms],
            f'{key}: hierarchy changed')
    worlds = []
    for t in after_skin.transforms:
        parent = worlds[t['parent']] if t['parent'] >= 0 else (0.,)*3
        worlds.append(tuple(a+b for a,b in zip(t['local'],parent)))
    error = max(math.dist(p,targets[t['name']]) for p,t in zip(worlds,after_skin.transforms))
    require(error <= TOLERANCE_CM, f'{key}: reparsed bind does not match the intended translations')
    if bytes(output) == original:
        rebuilt, fit = before, {'unchanged':True,'wrapper_identical':True}
    else:
        try:
            rebuilt, info = M._tools_module('nfl_vc_lz_fill').rebuild_fixed_span_filled(before,bytes(output),encoder='auto')
        except Exception as exc:
            raise M.ModelsError(f'{bone.name if bone else key}: compressed span cannot fit ({exc})') from exc
        fit = asdict(info)
    require(len(before) == len(rebuilt) and before[:32] == rebuilt[:32], f'{key}: compressed span/scratch wrapper changed')
    require(source.decode_span(rebuilt,resource) == bytes(output), f'{key}: rebuilt bytes do not reparse exactly')
    receipt = {'key':key,'joints':joints,'vertices_changed':moved,'normals_changed':normals,
               'decoded_before_sha256':M._sha256(original),'decoded_after_sha256':M._sha256(output),
               'write_spans':B.A._diff_spans(before,rebuilt),'decoded_write_spans':B.A._diff_spans(original,output),
               'maximum_bind_error_cm':error,'fit':fit}
    return B.BoneMember(key,before,rebuilt,tuple(source.archive_segments(resource)),receipt,B._source_record(source,resource))


def axis_receipt(raw, transforms, targets):
    require(M._sha256(raw) == B.SKEL_SHA256, 'SKEL is not the pinned 25-vector resource')
    by_name = {t['name']:t for t in transforms}
    rows = []
    for name, child in AXIS_CHILDREN.items():
        before = tuple(b-a for a,b in zip(by_name[name]['absolute'],by_name[child]['absolute']))
        after = tuple(b-a for a,b in zip(targets[name],targets[child]))
        if math.dist(before,after) <= TOLERANCE_CM:
            continue
        axis = struct.unpack_from('<4f',raw,112+16*by_name[name]['index'])
        old_length, new_length = math.sqrt(sum(v*v for v in before)), math.sqrt(sum(v*v for v in after))
        recomputed = tuple(v/new_length for v in after)
        require(axis[3] == 0 and max(abs(v/old_length-a) for v,a in zip(before,axis)) <= AXIS_TOLERANCE,
                f'{name}: retail SKEL direction disagrees with its bind segment')
        require(max(abs(v-a) for v,a in zip(recomputed,axis)) <= AXIS_TOLERANCE,
                f'{name}: direction change needs an unproved muscle constant update')
        rows.append({'bone':name,'before_cm':old_length,'after_cm':new_length,'axis_recomputed':recomputed,
                     'axis_stored':axis,'axis_error':max(abs(v-a) for v,a in zip(recomputed,axis))})
    # Normalising a positive scalar multiple has the same direction. Retain the
    # canonical float32 vector, avoiding spurious last-bit SKEL changes/no-op drift.
    return {'key':'o3c116','axis_array_bytes':400,'write_spans':[], 'segments':rows,
            'reason':'Recomputed axial directions match the canonical SKEL float32 vectors; axis and angular constants retained'}


def compile_set(source, body_set, folder, *, write_normals=True, write_uvs=False, allow_rescale=True, write_colours=True, progress=None):
    require(set(body_set.keys) == {'o3c113','o3c114','o3c115'}, 'non-player skeleton: only outer 3 player body is proved')
    folder = Path(folder)
    files = M.find_body_set_files(body_set,folder)
    require({'o3c113','o3c114'} <= files.keys(), PAIR_REASON)
    require('o3c115' in files, 'keep hi_head with both LOD files from one export')
    try:
        manifest = json.loads((folder/MANIFEST).read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise M.ModelsError(PAIR_REASON + ': missing skeleton export manifest; export the body set again') from exc
    require(manifest.get('schema') == SCHEMA and set(manifest.get('members',{})) == set(body_set.keys), PAIR_REASON)
    parsed, requested, gltfs = {}, {}, {}
    for key in body_set.keys:
        parsed[key] = _skin(source,key)
        _,body,_,_,lanes,skin = parsed[key]
        if key == 'o3c115':
            require(M._sha256(body) == HEAD_SHA256, 'hi_head: source is not the pinned coordinated head')
        require(manifest['members'][key]['decoded_sha256'] == M._sha256(body), f'{key}: export source differs')
        gltf = M.GltfFile(files[key])
        gltfs[key] = gltf
        tags = [n.get('extras',{}).get(EXPORT_TAG) for n in gltf.document.get('nodes',[]) if EXPORT_TAG in n.get('extras',{})]
        require(tags and all(tag == manifest.get('export_id') for tag in tags), PAIR_REASON + ': retain Blender Custom Properties')
        requested[key] = read_bind(gltf,skin.transforms,lanes.name)
    low = parsed['o3c113'][-1].transforms
    high = parsed['o3c114'][-1].transforms
    # A present but untouched second LOD is still a one-LOD edit.
    common = set(requested['o3c113']) & set(requested['o3c114'])
    require(all(math.dist(requested['o3c113'][n],requested['o3c114'][n]) <= INPUT_TOLERANCE_CM for n in common), PAIR_REASON)
    bone, scale = infer_edit(low,requested['o3c113'])
    require(bone is None or bone.kind != 'upper_arm',
            f'{bone.name if bone else "upper_arm"}: compressed span cannot fit at the +1%/+5% witnesses; upper-arm import is not enabled')
    for t in parsed['o3c115'][-1].transforms:
        require(math.dist(requested['o3c115'][t['name']],t['absolute']) <= INPUT_TOLERANCE_CM,
                f'hi_head:{t["name"]}: head/spine/neck coordination is not proved')
    targets = {}
    for key,transforms in (('o3c113',low),('o3c114',high)):
        targets[key] = target_positions(transforms,bone,scale) if bone else {t['name']:t['absolute'] for t in transforms}
        for t in transforms:
            n = t['name']
            if key == 'o3c114' and n not in common:
                require(min(math.dist(requested[key][n],t['absolute']),math.dist(requested[key][n],targets[key][n])) <= INPUT_TOLERANCE_CM,
                        f'{n}: derived pivot edit differs from the proved limb coordination')
            else:
                require(math.dist(requested[key][n],targets[key][n]) <= INPUT_TOLERANCE_CM, f'{n}: uncoordinated bind translation')
    members = []
    for key in ('o3c113','o3c114','o3c115'):
        if progress:
            progress(f'Fitting {key} with coordinated skeleton',len(members),4)
        geometry = None
        try:
            geometry = M.compile_import(source,key,files[key],write_normals=write_normals,write_uvs=write_uvs,
                                        allow_rescale=allow_rescale,write_colours=write_colours)
        except M.UnchangedModelError:
            pass
        if key != 'o3c115':
            members.append(_rewrite(source,key,targets[key],bone,scale,geometry))
        else:
            r,_,_,_,_,_ = parsed[key]
            before = source.span(r)
            after = geometry.rebuilt_span if geometry else before
            members.append(B.BoneMember(key,before,after,tuple(source.archive_segments(r)),
                                       {'key':key,'joints':[],'write_spans':B.A._diff_spans(before,after),
                                        'head_bind_retained':True},B._source_record(source,r)))
    _, resources = M._tools_module('nfl_scene_probe').parse_inventory(source.inventory_path)
    skel = next((r for r in resources if (r.outer_index,r.chunk_index) == (3,116)),None)
    require(skel is not None,'missing SKEL 3/116')
    raw = source.span(skel)
    axes = axis_receipt(raw,low,targets['o3c113'])
    members.append(B.BoneMember('o3c116',raw,raw,tuple(source.archive_segments(skel)),axes,B._source_record(source,skel)))
    changed_bones = []
    if bone:
        old = {t['name']:t['absolute'] for t in low}
        changed_bones.append({'bone':bone.name,'before_cm':math.dist(old[bone.pivot],old[bone.tip]),
                              'after_cm':math.dist(targets['o3c113'][bone.pivot],targets['o3c113'][bone.tip]),'scale':scale})
    receipt = {'schema':SCHEMA,'changed_bones':changed_bones,'axis_segments':axes['segments'],
               'changed_bind_lengths':[
                   {'member':m.key,'bone':j['name'],
                    'before_cm':math.sqrt(sum(v*v for v in j['local_before'])),
                    'after_cm':math.sqrt(sum(v*v for v in j['local_after']))}
                   for m in members for j in m.receipt.get('joints',[])
                   if math.dist(j['local_before'],j['local_after']) > TOLERANCE_CM],
               'members':[m.receipt for m in members],'experimental':True,'witnessed':False,
               'preflight_passed':True,'tolerance_cm':TOLERANCE_CM,'input_tolerance_cm':INPUT_TOLERANCE_CM,'bound_fraction':BOUND,
               'help':HELP,'export_id':manifest['export_id'],
               'skeleton_overlay':{key:[{'name':t['name'],'parent':t['parent'],'position_cm':targets[key][t['name']]}
                                       for t in transforms] for key,transforms in (('o3c113',low),('o3c114',high))}}
    plan = B.BonePlan(tuple(members),receipt)
    compiled = M.CompiledModelSet(body_set.outer_index, files={key:str(path) for key,path in files.items()}, skeleton_plan=plan)
    compiled.notes = [HELP] + [f'{row["bone"]}: {row["before_cm"]:.5f} -> {row["after_cm"]:.5f} cm' for row in changed_bones]
    return compiled

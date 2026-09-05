"""EXPERIMENTAL / UNWITNESSED animation inspection and fixed-span groundwork.

No executable, disc, or archive writes. Archive SMCD replacement returns bytes
and a receipt; MMCD and embedded XBE roots remain inspection-only. The local
pose model has no captured actor root, player proportions, or high-body pass.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Callable, Sequence

from mod_editor.core import nfl2k5_animation_math as qm

SCHEMA = 'nfl2k5_animation_native/v1'
KEY_SCHEMA = 'nfl2k5_animation_keys/v1'
RETAIL_XBE_SHA256 = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
EMBEDDED_ROOTS = (0x86dfe0, 0x8528e8)  # Explicit memo roots, NOT an exhaustive census.
IMPORT_ENABLED = False
SKELETON_NAMES = {
    'referee': ('root lfemur ltibia lfoot ltoes rfemur rtibia rfoot rtoes waist thorax neck head '
                'lcollar lhumerus ltwist lelbow lwrist lhand rcollar rhumerus rtwist relbow rwrist rhand').split(),
    'player': ('root lfemur ltibia lfoot ltoes rfemur rtibia rfoot rtoes waist thorax neck head '
               'lcollar lhumerus lelbow lwrist lhand rcollar rhumerus relbow rwrist rhand lshoulderpad rshoulderpad').split(),
}
SKELETON_PARENTS = {
    'referee': (-1,0,1,2,3,0,5,6,7,0,9,10,11,10,13,14,15,16,17,10,19,20,21,22,23),
    'player': (-1,0,1,2,3,0,5,6,7,0,9,10,11,10,13,14,15,16,10,18,19,20,21,10,10),
}
ASSUMPTIONS = (
    'EXPERIMENTAL / UNWITNESSED. Local poses only; no captured actor position or world path.',
    'Player preview uses the low body without live proportions or the high-body postprocessor.',
    'Unknown families show independent channel axes; their skeleton and mirror map are unresolved.',
    'Portable fixed-table interpolation is a numerical model, not Xbox x87 bit identity.',
    'Events, trajectory, auxiliary data and opaque bytes stay in the native sidecar.',
)


class AnimationError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise AnimationError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool(name):
    path = str(Path(__file__).resolve().parents[2] / 'tools')
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')


@dataclass(frozen=True)
class Root:
    index: int
    offset: int
    channels: int
    frames: int
    rate: int
    multiplier: float
    duration: float
    flags: int
    rotations: int
    trajectory: int
    events_offset: int
    auxiliary: int | None
    regions: tuple[tuple[str, int, int], ...]
    events: tuple[tuple[int, int, float], ...]

    @property
    def stride(self):
        return 6 if self.flags & 8 else 8


@dataclass(frozen=True)
class Clip:
    identity: str
    name: str
    kind: str
    source: dict[str, Any]
    original: bytes
    body: bytes
    roots: tuple[Root, ...]
    family: str = 'unknown'
    namespace: str | None = None
    structure: dict[str, Any] | None = None

    @property
    def map_id(self):
        return {'referee': '0x0051d010', 'player': '0x0051cd70'}.get(self.family)


def _root(body, index, offset, regions, targets):
    require(0 <= offset <= len(body)-52, 'Truncated animation root')
    channels, frames, flags, rate = body[offset], struct.unpack_from('<H',body,offset+2)[0], body[offset+4], body[offset+12]
    multiplier, duration, *floats = struct.unpack_from('<5f',body,offset+16)
    require(1 <= channels <= 32 and frames > 0 and rate > 0, 'Invalid frame or channel count/rate')
    require(all(math.isfinite(v) for v in (multiplier,duration,*floats)) and multiplier > 0 and duration > 0,
            'Invalid animation time or opaque float')
    sizes = {'rotations':4*channels*frames, 'trajectory':(6 if flags & 8 else 8)*frames, 'auxiliary':12*frames}
    events = []
    for name, start, end in regions:
        require(0 <= start < end <= len(body), 'Region outside native bytes')
        if name in sizes:
            require(end-start >= sizes[name], f'Truncated {name} region')
        if name == 'events':
            cursor = start
            while cursor+4 <= end:
                word = struct.unpack_from('<I',body,cursor)[0]
                cursor += 4
                if word == 0xffffffff:
                    break
                events.append((word & 255,word >> 8,(word >> 8)/65536/multiplier))
            else:
                raise AnimationError('Event list has no bounded terminator')
    return Root(index,offset,channels,frames,rate,multiplier,duration,flags,
                targets['rotations'],targets['trajectory'],targets['events'],targets.get('auxiliary'),
                tuple(regions),tuple(events))


def parse_archive_span(span: bytes, identity: str, source: dict | None = None) -> Clip:
    """Parse exactly one uncompressed wrapper + body, retaining every slack byte."""
    span = bytes(span)
    require(len(span) >= 32, 'Truncated animation wrapper')
    kind, stored, system, video, magic, scratch, reserved0, reserved1 = struct.unpack_from('<4s7I',span)
    require(kind in (b'SMCD',b'MMCD'), 'Expected a single or multi-root animation')
    require(len(span) == stored+32 and stored == system and not any((video,magic,scratch,reserved0,reserved1)),
            'Animation wrapper differs from the proved uncompressed format')
    body = span[32:]
    parser = _tool('nfl_motion_inventory')
    try:
        parsed = (parser.parse_smcd if kind == b'SMCD' else parser.parse_mmcd)(body,{})
    except ValueError as exc:
        raise AnimationError(str(exc)) from exc
    roots = []
    names = {0x24:'rotations',0x28:'trajectory',0x2c:'events',0x30:'auxiliary'}
    for index, row in enumerate(parsed['roots']):
        regions = [(names[r['owner_pointer_field_relative']],r['offset'],r['end'])
                   for r in parsed['packed_regions'] if r['owner_root_index'] == index]
        targets = {name:start for name,start,_ in regions}
        roots.append(_root(body,index,row['offset'],regions,targets))
    source = dict(source or {})
    family, namespace = 'unknown', None
    # Bind only identities whose ownership chain was joined in the memo.
    if identity == 'archive:3107/27' and parsed['name'] == 'ANM_REF_PENALTY_DELAY_OF_GAME_R':
        require(len(roots) == 1 and roots[0].channels == 21, 'Referee binding differs')
        family, namespace = 'referee','Referee'
    elif identity == 'archive:3092/163' and parsed['name'] == 'ANM_CELEBRATE_USER_34':
        require(len(roots) == 1 and roots[0].channels == 23, 'Player binding differs')
        family, namespace = 'player','Player (conditional celebration selector)'
    return Clip(identity,parsed['name'],kind.decode(),source,span,body,tuple(roots),family,namespace,parsed)


def catalog_entry(clip: Clip) -> dict:
    return {'identity':clip.identity,'name':clip.name,'kind':clip.kind,'family':clip.family,
            'namespace':clip.namespace,'map_id':clip.map_id,'source':clip.source,
            'sha256':sha256(clip.original),'body_sha256':sha256(clip.body),
            'bones':25 if clip.map_id else None,'experimental':True,'witnessed':False,
            'roots':[{'index':r.index,'frames':r.frames,'rate_hz':r.rate,'time_multiplier':r.multiplier,
                      'duration_seconds':r.duration,'channels':r.channels,'flags':r.flags,
                      'loop':bool(r.flags&1),'mirror':bool(r.flags&4),'events':len(r.events),
                      'trajectory_records':r.frames,'trajectory_stride':r.stride,
                      'auxiliary_records':r.frames if r.auxiliary is not None else 0,
                      'region_sha256':{name:sha256(clip.body[start:end]) for name,start,end in r.regions}}
                     for r in clip.roots]}


class AnimationSource:
    """Read-only, handle-free archive catalogue using the Studio resource index."""
    def __init__(self,index_path: Path,inventory_path: Path,xbe_path: Path | None = None):
        self.index_path = Path(index_path).resolve()
        self.inventory_path = Path(inventory_path).resolve()
        self.xbe_path = Path(xbe_path).resolve() if xbe_path else None
        self.outer = _tool('nfl_outer')
        self.archive = self.outer.parse_archive(self.index_path)
        document = json.loads(self.inventory_path.read_text(encoding='utf-8'))
        require(document.get('schema') == 'nfl2k5_resource_chunk_inventory/v1','Unsupported resource inventory')
        self.records = {}
        self.scenes = {}
        for row in document['chunks']:
            pair = (int(row['outer_index']),int(row['chunk_index']))
            if row['kind'] in ('SMCD','MMCD'):
                require(pair not in self.records,'Duplicate animation identity in inventory')
                self.records[pair] = row
            elif row['kind'] == 'SCNE':
                self.scenes[pair] = row
        self._skeletons = {}

    def load(self,identity: str) -> Clip:
        if identity.startswith('xbe:'):
            require(self.xbe_path is not None,'Choose a retail executable for embedded roots')
            return next((c for c in embedded_clips(self.xbe_path) if c.identity == identity), None) or self._missing(identity)
        try:
            pair = tuple(map(int,identity.removeprefix('archive:').split('/')))
            row = self.records[pair]
        except (KeyError,ValueError):
            return self._missing(identity)
        require(identity == f'archive:{pair[0]}/{pair[1]}','Noncanonical animation identity')
        entry = self.archive.entries[pair[0]]
        require(int(row['outer_id'],0) == entry.name_id and int(row['outer_size']) == entry.size,'Archive identity differs from inventory')
        span = self.outer.read_entry_range(self.archive,entry,int(row['chunk_offset']),32+int(row['stored_size']))
        require(span[:4].decode('ascii') == row['kind'],'Resource type differs from inventory')
        segments = self.outer.range_segments(self.archive.packs,[p.virtual_start for p in self.archive.packs],
                                              entry.virtual_offset+int(row['chunk_offset']),len(span))
        source = {'scope':'archive','outer_index':pair[0],'chunk_index':pair[1],
                  'outer_id':row['outer_id'],'chunk_offset':int(row['chunk_offset']),
                  'segments':[{'pack':s.pack_name,'offset':s.pack_offset,'length':s.size} for s in segments]}
        return parse_archive_span(span,identity,source)

    @staticmethod
    def _missing(identity):
        raise AnimationError(f'No animation at {identity}')

    def catalog(self,progress: Callable | None = None) -> dict:
        archive = []
        pairs = sorted(self.records,key=lambda p:(p not in ((3107,27),(3092,163)),p))
        for n,(outer,chunk) in enumerate(pairs):
            archive.append(catalog_entry(self.load(f'archive:{outer}/{chunk}')))
            if progress and n % 100 == 0:
                progress(n,len(pairs))
        embedded = [catalog_entry(c) for c in embedded_clips(self.xbe_path)] if self.xbe_path else []
        return {'schema':'nfl2k5_animation_catalog/v1','archive':archive,'embedded_xbe':embedded,
                'embedded_scope':'Only the two explicitly identified memo roots; no XBE census',
                'assumptions':list(ASSUMPTIONS)}

    def skeleton(self,clip: Clip):
        if clip.family not in ('referee','player'):
            return None
        if clip.family in self._skeletons:
            return self._skeletons[clip.family]
        pair = (346,109) if clip.family == 'referee' else (3,113)
        require(pair in self.scenes,'Matching skeleton resource is absent from the inventory')
        probe, scne = _tool('nfl_scene_probe'), _tool('nfl_scne_inventory')
        row = self.scenes[pair]
        record = probe.ResourceRecord(*(row[k] if k != 'word_10' else int(row[k],0) if isinstance(row[k],str) else row[k]
                                       for k in ('outer_index','outer_id','outer_size','chunk_index','chunk_offset','kind',
                                                 'stored_size','word_08','word_0c','word_10','word_14')))
        raw = self.outer.read_entry_range(self.archive,self.archive.entries[pair[0]],record.chunk_offset,32+record.stored_size)
        body,_ = probe.decode_resource(raw,record)
        scene,*_ = scne.parse_scene(0,record,body,{})
        shape = next(s for s in scene['shapes'] if s['name'] == ('ref_low' if clip.family == 'referee' else 'LO_res'))
        at = int(shape['record_offset'])
        count = struct.unpack_from('<H',body,at+0x50)[0]
        require(count == 25,'Expected a 25-joint inspection skeleton')
        start = scne.resolve_relative(body,at+0x64,len(body),'transforms')
        require(start is not None and start+count*0x70 <= len(body),'Truncated skeleton')
        bones = []
        for index in range(count):
            off = start+index*0x70
            parent = struct.unpack_from('<i',body,off+0x64)[0]
            local = struct.unpack_from('<3f',body,off+0x50)
            _,name = scne.pointer_name(body,off+0x60,len(body),'joint')
            require(-1 <= parent < index and all(math.isfinite(v) for v in local),'Invalid skeleton parent or translation')
            bones.append({'name':name,'parent':parent,'local_cm':list(local)})
        require([b['name'] for b in bones] == SKELETON_NAMES[clip.family] and
                tuple(b['parent'] for b in bones) == SKELETON_PARENTS[clip.family],
                'Skeleton names or parents differ from the documented channel map')
        skeleton = {'family':clip.family,'resource':f'{pair[0]}/{pair[1]}','shape':shape['name'],
                    'body_sha256':sha256(body),'bones':bones}
        self._skeletons[clip.family] = skeleton
        return skeleton


def embedded_clips(path: Path) -> list[Clip]:
    xbe = _tool('xbe_info').Xbe(Path(path))
    require(sha256(xbe.data) == RETAIL_XBE_SHA256,'Embedded catalogue requires the pinned retail executable')
    result = []
    for va in EMBEDDED_ROOTS:
        header_offset = xbe.va_to_offset(va,52)
        header = xbe.data[header_offset:header_offset+52]
        channels,frames = header[0],struct.unpack_from('<H',header,2)[0]
        targets = dict(zip(('rotations','trajectory','events','auxiliary'),struct.unpack_from('<4I',header,36)))
        bounds = []
        for name,address in targets.items():
            if not address:
                continue
            if name == 'events':
                size = 0
                while size < 65536:
                    off = xbe.va_to_offset(address+size,4)
                    size += 4
                    if xbe.data[off:off+4] == b'\xff'*4:
                        break
                else:
                    raise AnimationError('Unterminated embedded event list')
            else:
                size = frames*({'rotations':4*channels,'trajectory':6 if header[4]&8 else 8,'auxiliary':12}[name])
            xbe.va_to_offset(address,size)
            bounds.append((name,address,address+size))
        lo = min(va,*(a for _,a,_ in bounds))
        hi = max(va+52,*(b for _,_,b in bounds))
        start = xbe.va_to_offset(lo,hi-lo)
        body = xbe.data[start:start+hi-lo]
        regions = [(n,a-lo,b-lo) for n,a,b in bounds]
        root = _root(body,0,va-lo,regions,{n:a for n,a,_ in regions})
        result.append(Clip(f'xbe:{va:08x}',f'Embedded root {va:08x}','XBE_ROOT',
            {'scope':'embedded_xbe','header_va':va,'span_va':lo,'file_offset':start,'xbe_sha256':RETAIL_XBE_SHA256},
            body,body,(root,),'unknown',None,{'header_hex':header.hex(),'pointer_mode':'absolute_va'}))
    return result


def native_rotations(clip: Clip,root_index=0):
    r = clip.roots[root_index]
    return [[qm.decode(struct.unpack_from('<I',clip.body,r.rotations+4*(frame*r.channels+channel))[0])
             for channel in range(r.channels)] for frame in range(r.frames)]


def sample_pose(clip: Clip,seconds: float,root_index=0,*,mapped=True,complete=True,loop=True):
    """Title timing/mirror policy; generic roots use unbound packed channel indices."""
    r = clip.roots[root_index]
    require(math.isfinite(seconds) and 0 <= seconds <= 1e6,'Time must be finite and between 0 and 1,000,000 seconds')
    seconds = qm.f32(seconds)
    if loop and r.flags & 1:
        # Bounded equivalent of the recovered repeated float32 subtraction.
        require(seconds/r.duration <= 10000,'Too many loops for the portable title sampler')
        while seconds >= r.duration:
            seconds = qm.f32(seconds-r.duration)
    coordinate = qm.f32(qm.f32(r.rate*seconds)*r.multiplier)
    left = min(int(coordinate),r.frames-1)
    right = min(left+1,r.frames-1)
    factor = qm.f32(coordinate-left) if left != right else 0.0
    mapping = {'referee':qm.REF_MAP,'player':qm.PLAYER_MAP}.get(clip.family) if mapped else None
    mirrored = bool(r.flags&4) if mapped else False
    result = []
    for logical in range(25 if mapping else r.channels):
        channel = mapping[logical*2+int(mirrored)] if mapping else logical
        if channel < 0:
            result.append((1.,0.,0.,0.))
            continue
        require(channel < r.channels,'Skeleton map exceeds clip channels')
        a = qm.decode(struct.unpack_from('<I',clip.body,r.rotations+4*(left*r.channels+channel))[0])
        b = qm.decode(struct.unpack_from('<I',clip.body,r.rotations+4*(right*r.channels+channel))[0])
        q = a if left == right else qm.interpolate(a,b,factor)
        if mirrored:
            q = (q[0],q[1],-q[2],-q[3])
        result.append(q)
    return qm.complete_pose(result,clip.family) if mapping and complete else tuple(result)


def project_pose(clip: Clip,seconds: float,skeleton=None,root_index=0,plane='front',*,loop=True):
    """Return 2D segments without Qt. Unknown families get labelled channel axes."""
    pose = sample_pose(clip,seconds,root_index,loop=loop)
    axis = 0 if plane == 'front' else 2
    if skeleton is None:
        segments = []
        for i,q in enumerate(pose):
            start = ((i%8)*2.,-(i//8)*2.,0.)
            v = qm.rotate(qm.unit(q),(0.,1.,0.))
            end = tuple(a+b for a,b in zip(start,v))
            segments.append(((start[0],start[1]),(end[0],end[1]),f'channel {i}'))
        return segments
    require(skeleton['family'] == clip.family and len(skeleton['bones']) == len(pose),'Skeleton family differs')
    world,positions,segments = [],[],[]
    for i,bone in enumerate(skeleton['bones']):
        parent = bone['parent']
        parent_q = world[parent] if parent >= 0 else (1.,0.,0.,0.)
        offset = qm.rotate(parent_q,bone['local_cm'])
        start = positions[parent] if parent >= 0 else (0.,0.,0.)
        point = tuple(a+b for a,b in zip(start,offset))
        positions.append(point)
        world.append(qm.unit(qm.multiply(parent_q,qm.unit(pose[i]))))
        if parent >= 0:
            segments.append(((start[axis],start[1]),(point[axis],point[1]),bone['name']))
    return segments


def key_document(clip: Clip) -> dict:
    require(clip.kind == 'SMCD' and len(clip.roots) == 1,'Only existing single-root archive clips accept key replacement')
    r = clip.roots[0]
    return {'schema':KEY_SCHEMA,'identity':clip.identity,'source_sha256':sha256(clip.original),
            'name':clip.name,'family':clip.family,'map_id':clip.map_id,'frames':r.frames,'channels':r.channels,
            'rate_hz':r.rate,'time_multiplier':r.multiplier,'duration_seconds':r.duration,'flags':r.flags,
            'quaternion_order':'wxyz','key_space':'primary packed channels before mirroring and derived joints',
            'rotations':native_rotations(clip)}


def native_sidecar(clip: Clip,skeleton=None) -> dict:
    roots = []
    for r in clip.roots:
        words = struct.unpack_from(f'<{r.frames*r.channels}I',clip.body,r.rotations)
        regions = []
        for name,start,end in r.regions:
            used = {'rotations':r.frames*r.channels*4,'trajectory':r.frames*r.stride,
                    'events':(len(r.events)+1)*4,'auxiliary':r.frames*12}[name]
            raw = clip.body[start:end]
            regions.append({'name':name,'offset':start,'length':end-start,'used_bytes':used,
                            'sha256':sha256(raw),'slack_hex':raw[used:].hex()})
        aux = []
        if r.auxiliary is not None:
            for frame in range(r.frames):
                word,*shorts = struct.unpack_from('<I4h',clip.body,r.auxiliary+12*frame)
                aux.append({'word':word,'omitted_lane':word>>30,'shorts':shorts})
        roots.append({'index':r.index,'offset':r.offset,'header_hex':clip.body[r.offset:r.offset+52].hex(),
                      'frames':r.frames,'channels':r.channels,'rate_hz':r.rate,'time_multiplier':r.multiplier,
                      'duration_seconds':r.duration,'sample_times':[i/(r.rate*r.multiplier) for i in range(r.frames)],
                      'flags':r.flags,'runtime_mask':struct.unpack_from('<I',clip.body,r.offset+8)[0],
                      'regions':regions,'original_words':list(words),'omitted_lanes':[w>>30 for w in words],
                      'native_missing_component_sign':'positive square root; no stored sign bit',
                      'events':[{'id':i,'ticks':ticks,'seconds':seconds} for i,ticks,seconds in r.events],
                      'trajectory':{'stride':r.stride,'position_scale_cm':0.125,'yaw_shift':3 if r.stride==8 else None,
                                    'records':[list(struct.unpack_from('<'+('4h' if r.stride==8 else '3h'),clip.body,
                                                                      r.trajectory+i*r.stride)) for i in range(r.frames)]},
                      'auxiliary':aux})
    return {'schema':SCHEMA,'catalog':catalog_entry(clip),'original_bytes_base64':base64.b64encode(clip.original).decode(),
            'body_offset_in_original':32 if clip.kind != 'XBE_ROOT' else 0,
            'original_sha256':sha256(clip.original),'body_sha256':sha256(clip.body),'structure':clip.structure,
            'roots':roots,'skeleton':skeleton,
            'channel_map_pairs':list({'referee':qm.REF_MAP,'player':qm.PLAYER_MAP}.get(clip.family,())),
            'assumptions':list(ASSUMPTIONS),'import_enabled':False,
            'preservation':'Original whole span is authoritative, including wrapper, padding, directory and opaque bytes.'}


def verify_sidecar(document: dict,clip: Clip):
    """Verify a local sidecar against the freshly read source, not against itself."""
    require(document.get('schema') == SCHEMA,'Unsupported native sidecar')
    try:
        raw = base64.b64decode(document['original_bytes_base64'],validate=True)
    except (ValueError,KeyError) as exc:
        raise AnimationError('Invalid native bytes in sidecar') from exc
    require(raw == clip.original and document.get('original_sha256') == sha256(raw),'Native sidecar source differs')
    expected = native_sidecar(clip,document.get('skeleton'))
    for key in ('catalog','body_offset_in_original','body_sha256','structure','roots','channel_map_pairs'):
        require(document.get(key) == expected[key],f'Native sidecar {key} differs')


def export_clip(clip: Clip,destination: Path,skeleton=None,*,bake_rate=120) -> dict:
    """Publish a new directory containing glTF, binary, mandatory native sidecar and keys.

    All handles close before directory replacement. Existing destinations refuse.
    Root translation stays absent; local skeleton bind offsets are centimeters -> meters.
    """
    require(isinstance(bake_rate,int) and 1 <= bake_rate <= 240,'Bake rate must be 1 through 240')
    destination = Path(destination).resolve()
    require(not destination.exists(),'Export folder already exists; choose a new folder')
    if skeleton:
        require(skeleton['family'] == clip.family and len(skeleton['bones']) == 25,'Skeleton family differs')
    sidecar = native_sidecar(clip,skeleton)
    binary = bytearray()
    gltf = {'asset':{'version':'2.0','generator':'2K5 Animations EXPERIMENTAL / UNWITNESSED'},
            'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'animations':[],'buffers':[],
            'bufferViews':[],'accessors':[],
            'extras':{'native_sidecar':'animation.native.json','identity':clip.identity,'assumptions':list(ASSUMPTIONS)}}

    def accessor(values,kind):
        width = 4 if kind == 'VEC4' else 1
        binary.extend(bytes((-len(binary))%4))
        offset = len(binary)
        flat = [c for v in values for c in v] if width == 4 else values
        binary.extend(struct.pack(f'<{len(flat)}f',*flat))
        view = len(gltf['bufferViews'])
        gltf['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(flat)*4})
        result = {'bufferView':view,'componentType':5126,'count':len(values),'type':kind}
        if width == 1:
            result.update(min=[min(values)],max=[max(values)])
        gltf['accessors'].append(result)
        return len(gltf['accessors'])-1

    sign_choices = []
    for r in clip.roots:
        mapped = skeleton is not None
        count = 25 if mapped else r.channels
        base = len(gltf['nodes'])
        for i in range(count):
            bone = skeleton['bones'][i] if mapped else {'name':f'channel_{i}','parent':-1,'local_cm':[0,0,0]}
            node = {'name':bone['name'],'translation':[v*0.01 for v in bone['local_cm']],
                    'extras':{'root_index':r.index,'logical_joint' if mapped else 'packed_channel':i,
                              'independently_importable':False}}
            gltf['nodes'].append(node)
            if bone['parent'] >= 0:
                gltf['nodes'][base+bone['parent']].setdefault('children',[]).append(base+i)
            else:
                gltf['scenes'][0]['nodes'].append(base+i)
        steps = math.ceil(r.duration*bake_rate)
        require(steps*count <= 2_000_000,'Clip exceeds the bounded export sample budget')
        times = [qm.f32(i/bake_rate) for i in range(steps)]+[r.duration]
        times = sorted(set(times))
        time_accessor = accessor(times,'SCALAR')
        tracks = [[] for _ in range(count)]
        signs = [[] for _ in range(count)]
        for seconds in times:
            pose = sample_pose(clip,seconds,r.index,mapped=mapped,loop=False)
            for i,q in enumerate(pose):
                q = qm.unit(q)
                xyzw = (q[1],q[2],q[3],q[0])
                flip = bool(tracks[i] and sum(a*b for a,b in zip(tracks[i][-1],xyzw)) < 0)
                if flip:
                    xyzw = tuple(-v for v in xyzw)
                signs[i].append(int(flip))
                tracks[i].append(xyzw)
        animation = {'name':f'{clip.name} / root {r.index} / local inspection', 'samplers':[],'channels':[],
                     'extras':{'native_root_index':r.index,'loop_flag':bool(r.flags&1),
                               'endpoint':'unwrapped end pose; looping is player-controlled',
                               'root_translation_emitted':False}}
        for i,track in enumerate(tracks):
            animation['samplers'].append({'input':time_accessor,'output':accessor(track,'VEC4'),'interpolation':'LINEAR'})
            animation['channels'].append({'sampler':i,'target':{'node':base+i,'path':'rotation'}})
        gltf['animations'].append(animation)
        sign_choices.append({'root_index':r.index,'times':times,'flipped_xyzw_keys_by_joint':signs})
    sidecar['gltf'] = {'bake_rate_hz':bake_rate,'quaternion_order':'xyzw','normalize_for_gltf':True,
                       'sign_choices':sign_choices,'interpolation':'LINEAR slerp between baked portable samples',
                       'continuous_error_bound':None,'root_translation_emitted':False,
                       'key_edit_file':'animation.keys.json' if clip.kind == 'SMCD' else None,
                       'derived_tracks_independently_importable':False}
    gltf['buffers'] = [{'uri':'animation.bin','byteLength':len(binary)}]
    files = {'animation.gltf':_json(gltf),'animation.bin':bytes(binary)}
    if clip.kind == 'SMCD':
        files['animation.keys.json'] = _json(key_document(clip))
    sidecar['export_hashes'] = {name:sha256(data) for name,data in files.items()}
    files['animation.native.json'] = _json(sidecar)
    files['README.txt'] = ('EXPERIMENTAL / UNWITNESSED\n\n'+'\n'.join(ASSUMPTIONS)+
        '\n\nKeep animation.native.json with the glTF. It contains original native bytes.\n'
        'The glTF is an inspection bake, with derived joints when the skeleton is known.\n'
        'For a dry-run key edit, edit rotations in animation.keys.json. Keep all other fields.\n'
        'Keys are scalar-first WXYZ in original packed-channel order, before mirroring.\n'
        'The UI can report changes but cannot import them. No game file is written.\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    import shutil
    stage = Path(tempfile.mkdtemp(prefix='.animation-',dir=destination.parent)).resolve()
    try:
        for name,payload in files.items():
            (stage/name).write_bytes(payload)
        require(not destination.exists(),'Export folder appeared while preparing files')
        os.replace(stage,destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {'directory':str(destination),'files':{name:sha256(data) for name,data in files.items()},
            'native_sha256':sha256(clip.original),'experimental':True,'witnessed':False}


@dataclass(frozen=True)
class Replacement:
    identity: str
    before: bytes
    after: bytes
    receipt: dict

    def status(self,payload: bytes) -> str:
        if payload == self.before:
            return 'unchanged' if self.before == self.after else 'original'
        if payload == self.after:
            return 'applied'
        raise AnimationError('Mixed or foreign resource bytes; replacement refused')

    def apply(self,payload: bytes) -> tuple[bytes,dict]:
        state = self.status(payload)  # whole-span refusal before any mutation
        return self.after,{**self.receipt,'already_applied':state == 'applied','input_status':state}


def _diff_spans(before,after):
    require(len(before) == len(after),'Replacement changes the native footprint')
    result = []
    i = 0
    while i < len(before):
        if before[i] == after[i]:
            i += 1
            continue
        start = i
        while i < len(before) and before[i] != after[i]:
            i += 1
        result.append({'offset':start,'length':i-start,'before_hex':before[start:i].hex(),'after_hex':after[start:i].hex()})
    return result


def compile_replacement(clip: Clip,rotations: Sequence) -> Replacement:
    """Constrained existing SMCD primary keys only. Pure bytes, never disk I/O."""
    require(clip.kind == 'SMCD' and len(clip.roots) == 1,'MMCD and embedded XBE replacement are disabled')
    r = clip.roots[0]
    require(len(rotations) == r.frames,'Frame count must stay fixed')
    output = bytearray(clip.original)
    changes = []
    max_error = 0.0
    mapping = {'referee':qm.REF_MAP,'player':qm.PLAYER_MAP}.get(clip.family)
    for frame,values in enumerate(rotations):
        require(len(values) == r.channels,'Channel count must stay fixed')
        for channel,value in enumerate(values):
            offset = 32+r.rotations+4*(frame*r.channels+channel)
            before = struct.unpack_from('<I',clip.original,offset)[0]
            try:
                require(all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in value),'Rotation values must be numbers')
                after = qm.encode(value,before)
            except (ValueError,TypeError,OverflowError) as exc:
                raise AnimationError(f'Frame {frame}, channel {channel}: {exc}') from exc
            if before != after:
                requested,decoded = qm.unit(value),qm.unit(qm.decode(after))
                dot = min(1.,abs(sum(a*b for a,b in zip(requested,decoded))))
                error = math.degrees(2*math.acos(dot))
                require(error <= 0.35,'Edited rotation exceeds 0.35 degrees of packing error')
                max_error = max(max_error,error)
                struct.pack_into('<I',output,offset,after)
                changes.append({'frame':frame,'packed_channel':channel,
                                'logical_joint':next((i for i in range(25) if mapping[2*i] == channel),None) if mapping else None,
                                'offset':offset,'length':4,'before_word':before,'after_word':after,
                                'omitted_lane_before':before>>30,'omitted_lane_after':after>>30,'error_degrees':error})
    after = bytes(output)
    parsed = parse_archive_span(after,clip.identity,clip.source)
    require(parsed.roots == clip.roots and parsed.name == clip.name,'Clip structure changed')
    exact = _diff_spans(clip.original,after)
    physical = []
    span_base = 0
    for segment in clip.source.get('segments',[]):
        for diff in exact:
            lo,hi = max(span_base,diff['offset']),min(span_base+segment['length'],diff['offset']+diff['length'])
            if lo < hi:
                physical.append({'pack':segment['pack'],'offset':segment['offset']+lo-span_base,
                                 'length':hi-lo,'before_hex':clip.original[lo:hi].hex(),'after_hex':after[lo:hi].hex()})
        span_base += segment['length']
    receipt = {'schema':'nfl2k5_animation_replacement/v1','identity':clip.identity,
               'before_sha256':sha256(clip.original),'after_sha256':sha256(after),'span_length':len(after),
               'changed_keys':changes,'write_spans':exact,'archive_write_spans':physical,
               'changed_bytes':sum(s['length'] for s in exact),'maximum_packing_error_degrees':max_error,
               'preserved':['identity','name','channels','frames','rate','multiplier','duration','flags',
                            'events','trajectory','auxiliary','opaque fields','wrapper','slack'],
               'experimental':True,'witnessed':False,'ui_import_enabled':False,'game_files_written':False}
    return Replacement(clip.identity,clip.original,after,receipt)


def check_key_document(clip: Clip,document: dict) -> Replacement:
    require(isinstance(document,dict),'Expected a key document object')
    expected = key_document(clip)
    require(set(document) == set(expected),'Key document fields changed')
    for key,value in expected.items():
        if key != 'rotations':
            require(document[key] == value,f'Fixed key field changed: {key}')
    return compile_replacement(clip,document['rotations'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--xbe',type=Path)
    actions = parser.add_subparsers(dest='action',required=True)
    catalog = actions.add_parser('catalog')
    catalog.add_argument('--output',type=Path,required=True)
    export = actions.add_parser('export')
    export.add_argument('identity')
    export.add_argument('--output',type=Path,required=True)
    check = actions.add_parser('check')
    check.add_argument('identity')
    check.add_argument('--keys',type=Path,required=True)
    check.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    source = AnimationSource(args.index,args.inventory,args.xbe)
    if args.action == 'catalog':
        result = source.catalog()
    else:
        clip = source.load(args.identity)
        if args.action == 'export':
            result = export_clip(clip,args.output,source.skeleton(clip))
        else:
            result = check_key_document(clip,json.loads(args.keys.read_text(encoding='utf-8'))).receipt
    if args.action != 'export':
        # Exclusive creation avoids accidentally overwriting a game/input file.
        with args.output.open('xb') as stream:
            stream.write(_json(result))
    print(json.dumps({'action':args.action,'output':str(args.output),'experimental':True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

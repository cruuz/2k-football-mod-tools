"""Compile one PNG + JSON into the scorebug's atlas and native quad table.

The layout is the presentation source of truth. No font files or FONT chunks
are required. Native CPU execution and the shared software raster provide the
preview; actual NV2A rasterization and played-game behavior remain unwitnessed.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
VERSION = 'scorebug-sprite-v1'
MAGIC, MARKER_OFFSET, TABLE_OFFSET = 0x35525053, 0x60, 16512
MAX_APPEND = 400_000
# Raw SCNE material records stay in place: the owner binds them by name/index.
# The SHAP descriptors, not the material array, determine submission order.
SUBMESH_TABLE = 0x1cb0
ATLAS_MATERIALS = (3, 4, 6, 7, 9)
# Display model, measured on the emulator at both aspects (reports/b71_s8): the game
# presents its 640x448 HUD target scaled to the whole picture. At 4:3 a HUD pixel is
# 640/1440 of the width for 448/1080 of the height; with the widescreen patch HUD x is
# contracted by 27/32 about 320 and the 640 columns fill a 16:9 picture. Layout boxes
# are 1920x1080 broadcast pixels: rows map through the 448-line viewport (16 + y*448/1080)
# and columns use the horizontal scale that makes one source pixel one display pixel for
# the display the disc is built for, so the bar keeps the broadcast proportions.
WIDE_CONTRACTION = 27 / 32
DISPLAY = {False: dict(name='4:3', size=(1440, 1080), contraction=1.0),
           True: dict(name='16:9', size=(1920, 1080), contraction=WIDE_CONTRACTION)}
PIN_MARGIN = 12  # source pixels between a pinned layer and the last drawable column

def x_scale(widescreen=False):
    """HUD pixels per source pixel horizontally for the display the disc targets."""
    d=DISPLAY[bool(widescreen)];return 640/d['size'][0]/d['contraction']

def hud_box(box,widescreen=False):
    x0,y0,x1,y1=box;k=x_scale(widescreen)
    return (320+(x0-960)*k,16+y0*448/1080,320+(x1-960)*k,16+y1*448/1080)

def scene_box(box,widescreen=False):
    a,b,c,d=hud_box(box,widescreen);return (a-320,424-d,c-320,424-b)

def drawable_right(widescreen=False):
    """Largest source x the HUD can draw (HUD column 640) on the display."""
    return 960+320/x_scale(widescreen)

def contracted(hud,widescreen=False):
    """What the game's widescreen patch does to an authored HUD box."""
    if not widescreen:return tuple(hud)
    x0,y0,x1,y1=hud;return (320+(x0-320)*WIDE_CONTRACTION,y0,320+(x1-320)*WIDE_CONTRACTION,y1)

def display_box(hud,widescreen=False):
    """A contracted HUD box in display pixels of the modelled picture."""
    d=DISPLAY[bool(widescreen)];sx=d['size'][0]/640;sy=d['size'][1]/448;x0,y0,x1,y1=hud
    return (x0*sx,(y0-16)*sy,x1*sx,(y1-16)*sy)

def placed_box(row,widescreen=False):
    """A static layer's box for the display; 'top-right' pins slide to the drawable edge."""
    box=list(row['box'])
    if row.get('pin')=='top-right':
        width=box[2]-box[0];right=drawable_right(widescreen)-PIN_MARGIN;box[0],box[2]=right-width,right
    return box
SOURCES = ('home score', 'away score', 'home timeouts', 'away timeouts', 'quarter', 'clock', 'play clock', 'down and distance')
TINTS = ('none', 'home team', 'away team', 'possessing team')
FIELD = struct.Struct('<8I6i')  # source, first vertex, capacity, glyph offset/count, colour, flags, visibility, anchor x/y/z, width, align, advance
GLYPH = struct.Struct('<4H4i8h')  # UTF16 token (up to four units), width/height/advance/raise, four packed UV pairs
STATIC = struct.Struct('<4I')  # first vertex, tint source, material, reserved
HEADER = struct.Struct('<8I')

class SpriteError(ValueError):
    pass

def require(value, message):
    if not value:
        raise SpriteError(message)

def _number(value):
    return type(value) in (int, float) and math.isfinite(value)

def _box(value, limit):
    return (isinstance(value, list) and len(value)==4 and all(_number(v) for v in value)
            and 0<=value[0]<value[2]<=limit[0] and 0<=value[1]<value[3]<=limit[1])

def load_layout(folder=None):
    from PIL import Image
    folder=Path(folder or DEFAULT_FOLDER)
    data=(folder/'layout.json').read_bytes()
    require(len(data)<=256*1024, 'The scorebug layout exceeds 256 KB.')
    spec=json.loads(data)
    require(spec.get('schema')=='nfl2k5_scorebug_sprite/v1' and spec.get('frame')==[1920,1080], 'Use a sprite v1 layout on a 1920×1080 frame.')
    require(spec.get('template')=='template.png', 'The scorebug image must be template.png in the layout folder.')
    require(spec.get('layer_order', 'decreasing-z') in ('increasing-z', 'decreasing-z'), 'Unknown scorebug layer order.')
    path=folder/'template.png'
    require(path.stat().st_size<=4*1024*1024, 'The scorebug PNG exceeds 4 MB.')
    with Image.open(path) as image:
        require(image.format=='PNG' and image.width<=2048 and image.height<=2048, 'Use a PNG no larger than 2048×2048.')
        image=image.convert('RGBA')
    require(spec.get('atlas') in ([256,512],[512,512]), 'The scorebug atlas must be 256×512 or 512×512.')
    require(0<len(spec.get('cells',{}))<=256 and 0<len(spec.get('glyph_sets',{}))<=8, 'The scorebug needs bounded cells and glyph sets.')
    for name,row in spec['cells'].items():
        require(_box(row.get('box'),image.size) and all(type(v)==int for v in row['box']), 'Invalid PNG cell: '+name)
    require(len(spec.get('static',[]))<=24 and len(spec.get('fields',[]))<=16, 'Too many scorebug layers or fields.')
    require(isinstance(spec.get('plate_tints', {}), dict), 'Possession plate tints must be an object.')
    for team, colour in spec.get('plate_tints', {}).items():
        from .nfl2k5_scorebug_resources import TEAM_LOGOS
        require(team in TEAM_LOGOS and isinstance(colour, str) and len(colour)==7 and colour[0]=='#', 'Invalid possession plate tint.')
        int(colour[1:],16)
    fit=spec.get('logo_fit', {})
    require(isinstance(fit, dict) and set(fit)<= {'default','by_team'} and isinstance(fit.get('by_team', {}), dict), 'The logo fit must hold a default and per-team values.')
    for team, row in [('default', fit.get('default', {}))]+list(fit.get('by_team', {}).items()):
        from .nfl2k5_scorebug_resources import TEAM_LOGOS
        require(team=='default' or team in TEAM_LOGOS, 'Unknown logo fit team.')
        require(isinstance(row, dict) and set(row)<= {'fill_x','height'} and all(isinstance(v,(int,float)) for v in row.values())
                and 0.5<=row.get('fill_x',1.0)<=2.0 and 0.25<=row.get('height',1.0)<=1.0, 'Invalid logo fit for '+team)
    require(len(spec.get('brand',[]))<=8, 'Too many brand layers.')
    names=set()
    for row in spec['static']+spec['fields']+spec.get('events',[])+spec.get('brand',[]):
        require(row['name'] not in names, 'Duplicate scorebug layer: '+row['name']);names.add(row['name'])
        require(_box(row.get('box'),spec['frame']), 'Invalid frame box: '+row['name'])
        require(_number(row.get('z',0)) and -20<=row.get('z',0)<=0, 'Use a layer depth from -20 to 0.')
        require(type(row.get('material'))==int and 0<=row['material']<11, 'Invalid scene material.')
    for row in spec['static']:
        require(row.get('tint') in TINTS, 'Unknown team tint.')
        require(row['cell']=='logo' or row['cell'] in spec['cells'], 'Unknown static atlas cell.')
        require(row.get('pin') in (None,'top-right'), 'Unknown layer pin.')
    shared={r['cell'] for r in spec['static']+spec.get('events',[])}
    for row in spec.get('brand',[]):
        # Brand layers are replicas lifted from broadcast stills: a coverage cell of their own,
        # drawn with the measured opacity and colour, with the source recorded in the row.
        require(row['cell'] in spec['cells'] and row['cell'] not in shared and row.get('tint','none')=='none', 'A brand layer needs its own untinted atlas cell.')
        require(row.get('pin') in (None,'top-right') and _number(row.get('opacity',1)) and 0<row.get('opacity',1)<=1, 'Invalid brand layer pin or opacity.')
        require(isinstance(row.get('source',{}),dict), 'Brand provenance must be an object.')
        shared.add(row['cell'])
    for row in spec['fields']:
        require(row['source'] in SOURCES and row['glyph_set'] in spec['glyph_sets'], 'Unknown scorebug data source or glyph set.')
        require(type(row['slots'])==int and 1<=row['slots']<=16, 'Each field needs 1–16 quads.')
        require(row['alignment'] in ('left','center','right'), 'Unknown field alignment.')
        require(len(row['anchor'])==2 and all(_number(v) and 0<=v<=limit for v,limit in zip(row['anchor'],(1920,1080))), 'Invalid field anchor.')
        require(_number(row['size']) and 1<=row['size']<=110, 'Invalid glyph height.')
        require(isinstance(row['colour'],str) and len(row['colour'])==7 and row['colour'][0]=='#', 'Use #RRGGBB for glyph colour.')
        int(row['colour'][1:],16)
    for name,gset in spec['glyph_sets'].items():
        require(0<len(gset['glyphs'])<=128, 'Too many glyphs in '+name)
        require(_number(gset.get('cap_height')) and 1<=gset['cap_height']<=110, 'Invalid glyph set cap height.')
        for token,row in gset['glyphs'].items():
            require(1<=len(token)<=4 and all(0<ord(c)<128 for c in token), 'Glyph tokens must have 1–4 ASCII characters.')
            require(row['cell'] in spec['cells'] and len(row['size'])==2 and all(_number(v) and 0<=v<=256 for v in row['size']), 'Invalid glyph cell or size.')
            require(_number(row['advance']) and 0<row['advance']<=256 and _number(row.get('raise',0)), 'Invalid glyph advance.')
    return spec,image

@dataclass
class Compiled:
    spec: dict
    atlas: object
    cells: dict
    quads: list
    table: bytes
    widescreen: bool = False
    material_order: tuple = tuple(range(11))


def _allocate_layers(layers, spec):
    """Fit atomic fields and static layers without reversing an overlap.

    Material numbers in JSON are preferences for the interchangeable, always
    visible atlas batches. Logos/events retain their native texture/visibility
    bindings. Reserve fields first so a full label batch displaces a plate,
    rather than splitting a field or stealing an event/logo material.
    """
    from . import nfl2k5_scorebug_ingame as scene
    capacities = [(words-4)//3 for _, words in scene.layout.SUBMESH_COMMANDS]
    direction = 1 if spec.get('layer_order') == 'increasing-z' else -1
    ordered = sorted(range(len(layers)), key=lambda i: (direction*layers[i].get('z', 0), i))
    def footprint(row):
        if 'slots' not in row:
            return row['box']
        # Runtime placement uses the anchor, not the declared box's origin.
        # Include raised glyphs and the full compressed field width so custom
        # anchors cannot introduce an overlap absent from the allocation graph.
        x,y = row['anchor']; width = row['box'][2]-row['box'][0]
        left = x-width*(0.5 if row['alignment']=='center' else 1 if row['alignment']=='right' else 0)
        glyphs = spec['glyph_sets'][row['glyph_set']]
        factor = row['size']/glyphs['cap_height']
        top = min(-g.get('raise',0)*factor for g in glyphs['glyphs'].values())
        bottom = max((g['size'][1]-g.get('raise',0))*factor for g in glyphs['glyphs'].values())
        return left,y+top,left+width,y+bottom
    boxes = [footprint(row) for row in layers]
    overlaps = []
    for at, i in enumerate(ordered):
        a = boxes[i]
        for j in ordered[at+1:]:
            b = boxes[j]
            if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
                overlaps.append((i, j))
    costs = [r.get('slots', 1) for r in layers]
    choices = [(r['material'],) if r['material'] not in ATLAS_MATERIALS or r.get('cell') == 'logo'
               else (r['material'],)+tuple(k for k in ATLAS_MATERIALS if k != r['material']) for r in layers]
    pending = sorted(range(len(layers)), key=lambda i: (len(choices[i]) != 1, 'slots' not in layers[i], -costs[i], ordered.index(i)))
    assigned = {}; used = [0]*11; attempts = 0

    def submission_order():
        edges = {k: set() for k in range(11)}
        for i, j in overlaps:
            if i in assigned and j in assigned and assigned[i] != assigned[j]:
                edges[assigned[j]].add(assigned[i])
        result = []
        while edges:
            ready = next((k for k in edges if not edges[k]), None)
            if ready is None:
                return None
            result.append(ready); del edges[ready]
            for parents in edges.values():
                parents.discard(ready)
        return tuple(result)

    def place(at):
        nonlocal attempts
        attempts += 1
        if attempts > 20000:
            return None
        if at == len(pending):
            return submission_order()
        i = pending[at]
        for material in choices[i]:
            if used[material]+costs[i] > capacities[material]:
                continue
            assigned[i] = material; used[material] += costs[i]
            result = place(at+1) if submission_order() is not None else None
            if result is not None:
                return result
            used[material] -= costs[i]; del assigned[i]
        return None

    order = place(0)
    require(order is not None, 'Scorebug layers cannot fit the material capacities in draw order; reduce or rearrange overlapping layers.')
    for rank, i in enumerate(ordered):
        layers[i]['material'] = assigned[i]
        layers[i]['layer_rank'] = rank
    return order


def _pack(images, size):
    """Deterministic nonrotating MaxRects with a transparent sampling gutter."""
    from PIL import Image
    from .nfl2k5_scorebug_assets import alpha_bleed
    atlas=Image.new('RGBA',tuple(size),(255,255,255,0));free=[(0,0,*size)];placed={}
    for name,image in sorted(images.items(),key=lambda kv:(-max(kv[1].size),-kv[1].width*kv[1].height,kv[0])):
        image=alpha_bleed(image)
        w,h=image.width+2,image.height+2
        fits=[(min(fw-w,fh-h),max(fw-w,fh-h),y,x,i) for i,(x,y,fw,fh) in enumerate(free) if w<=fw and h<=fh]
        require(fits, 'The cells do not fit the atlas; reduce unused art or choose 512×512.')
        _,_,y,x,_=min(fits);placed[name]=(x+1,y+1,x+1+image.width,y+1+image.height)
        atlas.paste(image,(x+1,y+1))
        # Repeat edge RGB into transparent gutters to avoid dark logo/glyph fringes.
        p=atlas.load();src=image.load()
        for xx in range(-1,image.width+1):
            for yy in (-1,image.height):p[x+1+xx,y+1+yy]=(*src[min(image.width-1,max(0,xx)),min(image.height-1,max(0,yy))][:3],0)
        for yy in range(image.height):
            for xx in (-1,image.width):p[x+1+xx,y+1+yy]=(*src[min(image.width-1,max(0,xx)),yy][:3],0)
        split=[]
        for fx,fy,fw,fh in free:
            if x>=fx+fw or x+w<=fx or y>=fy+fh or y+h<=fy:split.append((fx,fy,fw,fh));continue
            if fx<x:split.append((fx,fy,x-fx,fh))
            if x+w<fx+fw:split.append((x+w,fy,fx+fw-x-w,fh))
            if fy<y:split.append((fx,fy,fw,y-fy))
            if y+h<fy+fh:split.append((fx,y+h,fw,fy+fh-y-h))
        free=[a for i,a in enumerate(split) if not any(i!=j and b[0]<=a[0] and b[1]<=a[1] and b[0]+b[2]>=a[0]+a[2] and b[1]+b[3]>=a[1]+a[3] and (a!=b or j<i) for j,b in enumerate(split))]
    return atlas,placed


def quantized_position(px,py,z=-4,widescreen=False):
    x,y,_,_=scene_box([px,py,px,py],widescreen)
    return tuple(round((c-o)/420*(32768 if c<o else 32767)) for c,o in zip((x,y,z),(-20,100,-29.5)))

def quantized_uv(box,size,flip=False):
    x0,y0,x1,y1=box
    # A stretched one-texel strip must sample its centre. Sampling its edges
    # blends the transparent packing gutter across the whole body quad.
    if x1-x0==1:x0=x1=x0+.5
    if y1-y0==1:y0=y1=y0+.5
    if flip:x0,x1=x1,x0
    return tuple(round(v*32767) for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1)) for v in (2*x/size[0]-1,2*y/size[1]-1))

def compile_folder(folder=None,widescreen=False):
    spec,image=load_layout(folder);scale_x=x_scale(widescreen)
    brand=[dict(r,tint='none',brand=True) for r in spec.get('brand',[])]
    used={r['cell'] for r in spec['static']+spec.get('events',[]) if r['cell']!='logo'}
    used.update(g['cell'] for s in spec['glyph_sets'].values() for g in s['glyphs'].values())
    images={n:image.crop(spec['cells'][n]['box']) for n in used}
    for row in brand:
        cell=image.crop(spec['cells'][row['cell']]['box']);opacity=row.get('opacity',1)
        cell.putalpha(cell.getchannel('A').point(lambda v:round(v*opacity)));images[row['cell']]=cell
    atlas,cells=_pack(images,spec['atlas'])
    statics=[dict(r,box=placed_box(r,widescreen),layout_box=r['box']) for r in spec['static']+brand]
    fields=[dict(r) for r in spec['fields']]
    events=[dict(r) for r in spec.get('events',[])]
    material_order=_allocate_layers(statics+fields+events,spec)
    quads=[];groups={i:[] for i in range(11)}
    def add(row,dynamic=False):
        row=dict(row,vertex=len(quads)*4,dynamic=dynamic);quads.append(row);groups[row['material']].append(row['vertex']);return row
    statics=[add(r) for r in statics]
    for row in fields:
        first=len(quads)*4
        for i in range(row['slots']):add(dict(row,name=row['name']+':'+str(i)),True)
        row['vertex']=first
    for row in events:add(row)
    from . import nfl2k5_scorebug_ingame as scene
    require(len(quads)*4<=scene.layout.VCOUNT, 'The scene allows at most 71 quads.')
    for k,rows in groups.items():
        require(not rows or 3*len(rows)+4<=scene.layout.SUBMESH_COMMANDS[k][1], 'Too many quads for material '+str(k))
    # All tables are offsets from the scene base, deliberately not relocatable pointers.
    table=bytearray(HEADER.size+len(fields)*FIELD.size+len(statics)*STATIC.size)
    glyph_sets={}
    for name,cap in sorted({(r['glyph_set'],r['size']) for r in fields}):
        gset=spec['glyph_sets'][name]
        factor=cap/gset['cap_height']
        offset=TABLE_OFFSET+len(table)
        for token,glyph in sorted(gset['glyphs'].items(),key=lambda kv:(-len(kv[0]),kv[0])):
            w,h=(v*factor for v in glyph['size']);adv=glyph['advance']*factor;rise=glyph.get('raise',0)*factor
            units=(token+'\0'*4)[:4]
            table+=GLYPH.pack(*map(ord,units),round(w*scale_x/420*32767),round(h*448/1080/420*32767),round(adv*scale_x/420*32767),round(rise*448/1080/420*32767),*quantized_uv(cells[glyph['cell']],spec['atlas']))
        glyph_sets[(name,cap)]=(offset,len(gset['glyphs']))
    for i,row in enumerate(fields):
        # Logical z controls submission only. Equal GPU depth makes the retail
        # LEQUAL state agree with painter order even when a depth buffer is bound.
        source=SOURCES.index(row['source']);x,y,z=quantized_position(*row['anchor'],0,widescreen)
        width=round((row['box'][2]-row['box'][0])*scale_x/420*32767)
        align=('left','center','right').index(row['alignment'])
        flags=int(row.get('strip_zero',False))
        visibility=0xa95a70 if source==6 else 0xa95a00 if source==7 else 0
        FIELD.pack_into(table,HEADER.size+i*FIELD.size,source,row['vertex'],row['slots'],*glyph_sets[(row['glyph_set'],row['size'])],0xff000000|int(row['colour'][1:],16),flags,visibility,x,y,z,width,align,0)
    for i,row in enumerate(statics):STATIC.pack_into(table,HEADER.size+len(fields)*FIELD.size+i*STATIC.size,row['vertex'],TINTS.index(row['tint']),row['material'],0)
    HEADER.pack_into(table,0,MAGIC,1,len(fields),TABLE_OFFSET+HEADER.size,len(statics),TABLE_OFFSET+HEADER.size+len(fields)*FIELD.size,len(table),len(quads))
    return Compiled(spec,atlas,cells,quads,bytes(table),bool(widescreen),material_order)


def scene_bytes(retail, compiled=None):
    from . import nfl2k5_scorebug_ingame as scene
    from . import nfl2k5_scorebug_exact as exact
    c=compiled or compile_folder();m=exact.mesh_mnf(retail)
    for v in range(scene.layout.VCOUNT):
        m.pos[v]=[0,0,-5];m.uv_edit[v]=(0,0)
        struct.pack_into('<I',m.buf,scene.layout.S1+v*10,0)
        struct.pack_into('<h',m.buf,scene.layout.S1+v*10+8,0)
    for row in c.quads:
        if row['dynamic']:continue
        x0,y0,x1,y1=row['box'];v=row['vertex'];mat=row['material']
        z=0
        cell=(0,0,64,64) if row['cell']=='logo' else c.cells[row['cell']]
        uv=quantized_uv(cell,(64,64) if row['cell']=='logo' else c.spec['atlas'],row.get('flip_x',False))
        a,b,cc,d=scene_box(row['box'],c.widescreen)
        for j,(x,y) in enumerate(((a,d),(cc,d),(a,b),(cc,b))):
            # scene_box is y-up: d is the top, b is the bottom.
            m.pos[v+j]=[x,y,z];m.uv_edit[v+j]=tuple(u/32767 for u in uv[j*2:j*2+2])
            struct.pack_into('<I',m.buf,scene.layout.S1+(v+j)*10,0xffffffff)
    groups={i:[] for i in range(11)}
    for row in sorted(c.quads,key=lambda r:r['layer_rank']):groups[row['material']].append(row['vertex'])
    for k,vertices in groups.items():
        indices=[]
        for v in vertices:
            if indices:indices.extend((indices[-1],v+2))
            indices.extend((v+2,v+3,v,v+1))
        words=[0x417fc,6,0x40001800|((len(indices)//2)<<18)] if indices else []
        words += [indices[i]|indices[i+1]<<16 for i in range(0,len(indices),2)]
        words += [0x417fc,0]
        at,capacity=scene.layout.SUBMESH_COMMANDS[k]
        require(len(words)<=capacity,'Sprite push-buffer overflow')
        struct.pack_into('<'+str(capacity)+'I',m.buf,at,*(words+[0]*(capacity-len(words))))
    descriptors=[bytes(m.buf[SUBMESH_TABLE+k*128:SUBMESH_TABLE+(k+1)*128]) for k in range(11)]
    for slot,k in enumerate(c.material_order):
        at=SUBMESH_TABLE+slot*128
        m.buf[at:at+128]=descriptors[k]
        # +78 is a one-based, field-relative pointer. Moving its descriptor
        # requires rebasing it; command storage and all other fields stay put.
        struct.pack_into('<i',m.buf,at+0x78,scene.layout.SUBMESH_COMMANDS[k][0]-(at+0x78)+1)
    for k in range(11):struct.pack_into('<I',m.buf,0x1c0+k*128+0x18,0xffffffff)
    result=bytearray(scene.serialize(m));require(result[MARKER_OFFSET:MARKER_OFFSET+8]==bytes(8),'Scene metadata header is not spare')
    struct.pack_into('<II',result,MARKER_OFFSET,MAGIC,TABLE_OFFSET)
    result+=c.table
    result+=bytes((-len(result))%128)
    return bytes(result)


def scene_span(retail,compiled=None):
    data=scene_bytes(retail,compiled)
    return struct.pack('<4s7I',b'SCNE',len(data),len(data),0,0,0,0,0)+data


def appendix(pack,folder=None,widescreen=False):
    from . import nfl2k5_scorebug_resources as art, nfl2k5_scorebug_ingame as scene
    from .nfl2k5_scorebug_assets import texture_chunk
    c=compile_folder(folder,widescreen)
    sources={n:pack[r['pack_offset']:r['pack_offset']+r['span_size']] for n,r in art.RESOURCES.items()}
    template=sources['score_buga'];scene.pinned(template,art.RESOURCES['score_buga'])
    chunks=[('TXTR','sb--h0',art.mnf_panel_span(template,None,'home'))]
    for team,rec in sorted(art.TEAM_LOGOS.items()):chunks.append(('TXTR','sb'+rec['asset_code']+'h0',art.mnf_panel_span(template,team,'home',plate_tints=c.spec.get('plate_tints'),logo_fit=c.spec.get('logo_fit'))))
    chunks.append(('TXTR','score_buga',texture_chunk('score_buga',c.atlas,template,alpha_aware=True)[0]))
    chunks.append(('SCNE','score_bug',scene_span(scene.pinned(sources['score_bug'],art.RESOURCES['score_bug']),c)))
    receipts=[dict(kind=k,name=n,size=len(b),sha256=hashlib.sha256(b).hexdigest()) for k,n,b in chunks]
    data=b''.join(b for _,_,b in chunks)
    require(len(data)<MAX_APPEND,'The scorebug exceeds the 0.4 MB resource limit; reduce the atlas or scene.')
    return data,dict(version=VERSION,display=DISPLAY[bool(widescreen)]['name'],components=receipts,appended_bytes=len(data),font_count=0,texture_count=34,scene_count=1,quads=len(c.quads),native_heap_bytes=sum((len(b)+127)//128*128 for _,_,b in chunks))


def probe_sizes(folder=None):
    from . import nfl2k5_scorebug_resources as art
    c=compile_folder(folder)
    scene_size=(TABLE_OFFSET+len(c.table)+127)//128*128+32
    appended=32*5280+2208+c.atlas.width*c.atlas.height+1184+scene_size
    require(appended<MAX_APPEND,'The scorebug exceeds the 0.4 MB resource limit.')
    growth=((art.HUD_SIZE+appended+2047)//2048-(art.HUD_SIZE+2047)//2048)*2048
    return 34,appended,growth


def pack_status(pack,folder=None,widescreen=None):
    """'retail', 'applied' or 'foreign'; widescreen=None accepts a collection built for either display."""
    from . import nfl2k5_scorebug_resources as art,nfl2k5_scorebug_ingame as scene
    import nfl_outer as outer
    try:
        _,added,growth=probe_sizes(folder);grown=len(pack)==scene.PACK_SIZE+growth
        if len(pack) not in (scene.PACK_SIZE,scene.PACK_SIZE+growth):return 'foreign'
        # The old HUD, including its fonts, remains byte-for-byte retail.
        if scene.digest(pack[art.HUD_START:art.HUD_START+art.HUD_SIZE])!=art.RUNTIME_PINS['hud_before']:return 'foreign'
        count,reserved,packs=struct.unpack('<3I',pack[:12])
        if count!=4323 or reserved or not 1<=packs<=36:return 'foreign'
        table=bytearray(pack[:outer.HEADER_SIZE+count*12])
        if struct.unpack_from('<I',table,12)[0]*2048!=len(pack):return 'foreign'
        at=outer.HEADER_SIZE+art.HUD_OUTER_INDEX*12
        if struct.unpack_from('<3I',table,at)!=(11965036,art.HUD_SIZE+(added if grown else 0),art.HUD_START//2048):return 'foreign'
        if grown:
            struct.pack_into('<I',table,12,scene.PACK_SIZE//2048);struct.pack_into('<I',table,at+4,art.HUD_SIZE)
            for i in range(art.HUD_OUTER_INDEX+1,count):
                pos=outer.HEADER_SIZE+i*12+8;struct.pack_into('<I',table,pos,struct.unpack_from('<I',table,pos)[0]-growth//2048)
        if scene.digest(table)!=art.RUNTIME_PINS['index']:return 'foreign'
        if grown:
            start=art.HUD_START+art.HUD_SIZE;have=bytes(pack[start:start+added])
            modes=(False,True) if widescreen is None else (bool(widescreen),)
            if not any(have==appendix(pack,folder,w)[0] for w in modes) or any(pack[start+added:outer.align_up(start+added)]):return 'foreign'
        return 'applied' if grown else 'retail'
    except (ValueError,KeyError,IndexError,struct.error,OSError):return 'foreign'


def compile_collection(pack,folder=None,widescreen=False):
    from . import nfl2k5_scorebug_resources as art,nfl2k5_scorebug_assets as assets
    state=pack_status(pack,folder,widescreen)
    require(state!='foreign','Foreign or mixed sprite scorebug resources; rebuild from the supported base.')
    if state=='applied':return pack,dict(status='already_applied',changed_bytes=0,growth=0)
    data,receipt=appendix(pack,folder,widescreen)
    read=lambda count,offset:bytes(pack[offset:offset+count])
    parts,growth=assets.grow_pack(read,len(pack),{art.HUD_OUTER_INDEX:[data]})
    result=art.join_views([(source if isinstance(source,bytes) else pack,offset,size) for source,offset,size in parts])
    require(pack_status(result,folder,widescreen)=='applied','Sprite collection read-back failed.')
    return result,dict(receipt,resources=receipt['components'],probe='sprite',fonts=[],outer_index=art.HUD_OUTER_INDEX,outer_size_before=art.HUD_SIZE,outer_size_after=art.HUD_SIZE+len(data),status='applied',growth=len(result)-len(pack),sha256_before=art.pack_digest(pack),sha256_after=art.pack_digest(result),runtime_witnessed=False,experimental=True)


STANDARD_STATE = dict(away='DEN', home='KC', away_score=7, home_score=7,
                      away_timeouts=3, home_timeouts=3, quarter=2,
                      clock=273, play_clock=4, down=3, distance=10,
                      possession='home', event='standard', goal_to_go=False)


def normalize_state(state=None):
    state=dict(STANDARD_STATE,**(state or {}))
    from .nfl2k5_scorebug_resources import TEAM_LOGOS
    require(state['away'] in TEAM_LOGOS and state['home'] in TEAM_LOGOS,'Choose two known NFL teams.')
    for key,low,high in (('home_score',0,999),('away_score',0,999),('home_timeouts',0,3),('away_timeouts',0,3),('quarter',1,9),('down',1,4),('clock',0,3600),('play_clock',0,99),('distance',0,99)):
        require(type(state[key])==int and low<=state[key]<=high,'Invalid preview state: '+key)
    require(type(state['goal_to_go'])==bool,'Goal to go must be true or false.')
    require(state['possession'] in ('home','away'),'Possession must be home or away.')
    require(state['event'] in ('standard','FLAG','FUMBLE','hang time','ball on','score slabs','hidden play clock'),'Unknown retail event state.')
    return state


class NativePreview:
    """Read-only native execution using the user's pinned game resources."""
    def __init__(self, pack=None, xbe=None, folder=None, source=None):
        from . import nfl2k5_scorebug_resources as art,nfl2k5_scorebug_ingame as scene
        import sys
        tools=str(ROOT/'tools')
        if tools not in sys.path:sys.path.insert(0,tools)
        import nfl2k5_scorebug_projection as projection
        self.compiled=compile_folder(folder)
        if source:
            from . import platform_compat as io
            with Path(source).open('rb') as stream:
                entries,_=scene.layout.xc.parse_xdvdfs(stream.fileno(),Path(source).stat().st_size)
                require('vc_53450030/0' in entries and 'default.xbe' in entries,'The selected game source has no pack 0 or default.xbe.')
                p,x=entries['vc_53450030/0'],entries['default.xbe']
                require(x.size<16*1024*1024,'The selected executable exceeds the supported size.')
                self.payload=io.pread(stream.fileno(),x.size,x.byte_offset)
                view=art.PackView.from_fd(stream.fileno(),p.byte_offset,p.size)
                self._read_resources(view,folder)
        else:
            self.pack_path=Path(pack or ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0')
            self.xbe_path=Path(xbe or self.pack_path.parents[1]/'default.xbe')
            require(self.pack_path.is_file() and self.xbe_path.is_file(),'Preview needs the game source; select an ISO or an extracted pack 0 and default.xbe.')
            self.payload=self.xbe_path.read_bytes()
            with self.pack_path.open('rb') as stream:
                view=art.PackView.from_fd(stream.fileno(),0,self.pack_path.stat().st_size)
                self._read_resources(view,folder)
        self.scene=scene.decode(self.chunks[-1])[1];self.atlas=self.chunks[-2]
        self.textures=self.chunks[:-1]

    def _read_resources(self,view,folder):
        from . import nfl2k5_scorebug_ingame as scene
        from nfl_main_menu_font import FONT_NAMES, EXPECTED_FONTS, parse_font
        from nfl_scene_probe import ResourceRecord
        data,self.volume=appendix(view,folder)
        self.chunks=[data[c.offset:c.end_offset] for c in scene.tx.parse_chunks(data)]
        self.modes={}
        for wide in (False,True):
            mode_data,volume=appendix(view,folder,wide)
            chunks=[mode_data[c.offset:c.end_offset] for c in scene.tx.parse_chunks(mode_data)]
            self.modes[wide]=dict(compiled=compile_folder(folder,wide),scene=scene.decode(chunks[-1])[1],atlas=chunks[-2],textures=chunks[:-1],volume=volume)
        # Read only the native global font outer for retained retail events.
        # The outer header has a fixed volume-table size, exposed by its parser.
        from nfl_outer import HEADER_SIZE
        at=HEADER_SIZE+3*12
        identity,size,sector=struct.unpack('<3I',view[at:at+12])
        require((identity,size)==(0x8ee9eeed,2387424),'The retail font collection identity changed.')
        blob=view[sector*2048:sector*2048+size];chunks=scene.tx.parse_chunks(blob);self.fonts=[]
        for slot,name in enumerate(FONT_NAMES[:9]):
            chunk=chunks[slot];decoded,_=scene.tx.decode_chunk(blob,chunk);sha=scene.digest(decoded)
            require(sha==EXPECTED_FONTS[name][4],'The retail event font changed: '+name)
            record=ResourceRecord(3,f'{identity:08x}',size,slot,chunk.offset,'FONT',chunk.stored_size,chunk.system_bytes,chunk.video_bytes,chunk.compression_magic,chunk.overlap_scratch_bytes)
            self.fonts.append(parse_font(slot,name,record,decoded,sha))

    def capture(self,state=None,widescreen=False):
        import nfl2k5_scorebug_projection as projection
        s=normalize_state(state);capture={};mode=self.modes[bool(widescreen)]
        events={'standard':(0,1),'FLAG':(1,3),'FUMBLE':(1,5),'hang time':(1,2),'ball on':(1,4),'score slabs':(0,1),'hidden play clock':(0,)}
        visibility='flag' if s['event']=='FLAG' else 'fumble' if s['event']=='FUMBLE' else None
        geometry=projection.native_geometry(self.payload,mode['scene'],fonts=self.fonts,texture_span=mode['atlas'],
            runtime_textures=mode['textures'],capture=capture,widescreen=widescreen,
            identity=dict(home=s['home'],away=s['away']),score_values=(s['home_score'],s['away_score']),
            previous_scores=(0,0) if s['event']=='score slabs' else (s['home_score'],s['away_score']),
            score_phase=.2 if s['event']=='score slabs' else 0,
            timeouts=(s['home_timeouts'],s['away_timeouts']),quarter=s['quarter'],
            game_seconds=s['clock'],play_seconds=s['play_clock'],down=s['down'],distance_yards=s['distance'],goal_to_go=s['goal_to_go'],
            possession=s['possession'],visible_elements=events[s['event']],visibility_state=visibility)
        # Retail text remains only for event overlays; the bar callbacks are blank.
        # The down formatter's field query is the same explicit boundary used
        # by the existing text raster audit.
        geometry=projection.native_text_draw(capture)|geometry
        def bounds(names):
            points=[v for q in mode['compiled'].quads if q['name'] in names
                    for v in geometry['positions'][q['vertex']:q['vertex']+4]]
            return [min(v[0] for v in points),min(v[1] for v in points),max(v[0] for v in points),max(v[1] for v in points)]
        geometry.update(frame=bounds(('body_left','body','body_right')),down=bounds(('plate',)),clock=bounds(('capsule',)))
        return geometry,capture

    def render(self,path,*,screenshot,state=None,widescreen=False):
        from PIL import Image
        import nfl2k5_scorebug_projection as projection
        geometry,capture=self.capture(state,widescreen);mode=self.modes[bool(widescreen)]
        try:
            source=Image.open(screenshot).convert('RGB')
            if source.width/source.height>1.65:
                background=Image.new('RGB',(640,480))
                background.paste(source.resize((640,448),Image.Resampling.LANCZOS),(0,16))
            else:background=source.resize((640,480),Image.Resampling.LANCZOS)
            raster=projection.render_native(capture['live_decoded'],mode['atlas'],self.fonts,geometry,Path(path),texture_spans=capture['texture_spans'],background=background)
            display=self._display_image(capture,geometry,mode,source,widescreen,Path(path))
            boxes={}
            for q in mode['compiled'].quads:
                vertices=geometry['positions'][q['vertex']:q['vertex']+4]
                if q['dynamic'] and struct.unpack_from('<I',capture['live_decoded'],0x2d20+q['vertex']*10)[0]==0:continue
                boxes[q['name']]=[min(v[0] for v in vertices),min(v[1] for v in vertices),max(v[0] for v in vertices),max(v[1] for v in vertices)]
            result=dict(state=normalize_state(state),widescreen=widescreen,quads=boxes,volume=mode['volume'],display=display,
                        draws=[dict(text=r['text'],glyph_quads=len(r['vertices'])//4) for r in geometry['draws']],
                        raster=raster,runtime_witnessed=False)
            Path(path).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n', newline="\n")
            return result
        finally:capture['machine'].close()


    def _display_image(self,capture,geometry,mode,source,widescreen,path):
        """The raster in display pixels: the 640x448 viewport scaled to the modelled picture over the screenshot."""
        from PIL import Image
        import numpy as np, tempfile
        import nfl2k5_scorebug_projection as projection
        d=DISPLAY[bool(widescreen)]
        with tempfile.TemporaryDirectory() as directory:
            layers=[]
            for name in ('black','white'):
                projection.render_native(capture['live_decoded'],mode['atlas'],self.fonts,geometry,Path(directory)/(name+'.png'),texture_spans=capture['texture_spans'],background=Image.new('RGB',(640,480),name))
                layers.append(np.asarray(Image.open(Path(directory)/(name+'.png')).convert('RGB')).astype(np.int16))
        black,white=layers
        alpha=1-np.clip((white-black).mean(-1)/255,0,1)
        rgb=np.clip(black/np.maximum(alpha[...,None],1e-6),0,255)
        layer=Image.fromarray(np.dstack([rgb.astype(np.uint8),(alpha*255).round().astype(np.uint8)]),'RGBA').crop((0,16,640,464)).resize(d['size'],Image.Resampling.LANCZOS)
        canvas=source.resize(d['size'],Image.Resampling.LANCZOS).convert('RGBA');canvas.alpha_composite(layer)
        out=path.with_name(path.stem+'_display'+path.suffix);canvas.convert('RGB').save(out)
        return dict(aspect=d['name'],size=list(d['size']),path=str(out),
                    quads={q['name']:list(display_box(contracted(hud_box(q['box'],widescreen),widescreen),widescreen)) for q in mode['compiled'].quads if not q['dynamic']})


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    preview=sub.add_parser('preview');preview.add_argument('--screenshot',type=Path,required=True)
    preview.add_argument('--state',default='{}');preview.add_argument('--aspect',choices=('4:3','16:9','both'),default='both')
    preview.add_argument('--output',type=Path,default=Path('scorebug_sprite_preview.png'))
    preview.add_argument('--source',type=Path);preview.add_argument('--folder',type=Path);preview.add_argument('--pack',type=Path);preview.add_argument('--xbe',type=Path)
    args=parser.parse_args(argv)
    engine=NativePreview(args.pack,args.xbe,args.folder,args.source);state=json.loads(args.state)
    for wide in ((False,True) if args.aspect=='both' else (args.aspect=='16:9',)):
        path=args.output.with_name(args.output.stem+('_169' if wide else '_43')+args.output.suffix) if args.aspect=='both' else args.output
        result=engine.render(path,screenshot=args.screenshot,state=state,widescreen=wide)
        print(path);print(result['display']['path'])
    return 0

if __name__=='__main__':raise SystemExit(main())

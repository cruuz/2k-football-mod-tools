"""Dedicated Anniversary field bundles; modern team resources remain unchanged.

The period paint is explicitly a reconstruction. Venue models are selected
from the user's retail source or completed build. All additions are separate
``a00..a50`` resources; the filename hook lives in nfl2k5_moment_venues.
Only the fixed SITU weather/time variant is required by a moment. Rebuilding
an edited SITU creates the matching variant again.
"""
from __future__ import annotations
import hashlib,json,struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/nfl2k5_espn25_fields.json'
ART=ROOT/'data/nfl2k5_espn25_fields'
SCHEMA='nfl2k5_espn25_fields/v1'
WORDMARKS={'ARI':'s00','STL':'s00','BUF':'s03','CAR':'s04','CIN':'s06','DAL':'s07',
          'DEN':'s08','DET':'s09','GB':'s10','IND':'s11','KC':'s13','MIA':'s14',
          'MIN':'s15','NE':'s16','NO':'s17','NYG':'s18','OAK':'s20','PHI':'s21',
          'PIT':'s22','LAR':'s23','SF':'s25','SEA':'s26','TEN':'s28','WAS':'s29',
          'CLE':'s30','ATL':'s01','BAL':'s02'}


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def catalog():
    raw=DATA.read_bytes();require(len(raw)<512*1024,'Anniversary field catalog is too large')
    doc=json.loads(raw);require(doc.get('schema')==SCHEMA,'foreign Anniversary field catalog')
    rows=doc['moments'];require([r['row'] for r in rows]==list(range(1,52)),'Anniversary field physical order')
    for row in rows:
        require(row['source_kind'] in ('retail','built') and row['source_prefix'].startswith('s')
                and len(row['source_prefix'])==3,'foreign source venue')
        require(0<=row['native_stadium_index']<82,'foreign native venue')
        require(len(row['endzones'])==2 and row['variant'][0] in 'dan'
                and row['variant'][1] in 'drs','foreign field paint/variant')
    return rows


def variant(situ,index):
    require(32+0x44+(index+1)*0x6c<=len(situ),'SITU row missing')
    w,t=struct.unpack_from('<II',situ,32+0x44+index*0x6c+0x60)
    require(w<5 and t<3,'unsupported SITU weather or time')
    return 'dan'[t]+'drrss'[w]


def repair_situ(situ):
    """Change only the 51 physical rows' stadium-index words (+0x10)."""
    require(struct.unpack_from('<I',situ,32+0x40)[0]==51,'expected 51 physical Anniversary rows')
    out=bytearray(situ);edits=[]
    for row in catalog():
        at=32+0x44+(row['row']-1)*0x6c+0x10;before=struct.unpack_from('<I',situ,at)[0]
        after=row['native_stadium_index']
        if before!=after:
            struct.pack_into('<I',out,at,after);edits.append(dict(row=row['row'],offset=at,size=4,before=before,after=after))
    return bytes(out),dict(before=sha(situ),after=sha(out),edits=edits,scope='Only SITU stadium-index dwords')


def art(row,key):
    from PIL import Image
    import numpy as np
    manifest=json.loads((ART/'manifest.json').read_text())
    require(manifest.get('schema')=='nfl2k5_espn25_field_art/v1','foreign Anniversary art manifest')
    match=[r for r in manifest['art'] if r['row']==row and r['key']==key]
    require(len(match)==1,'missing or duplicate Anniversary paint')
    r=match[0];path=(ART/r['file']).resolve();require(path.is_relative_to(ART.resolve()),'art path escapes its folder')
    raw=path.read_bytes();require(len(raw)<1024*1024 and sha(raw)==r['sha256'],'Anniversary art hash differs')
    with Image.open(path) as im:
        require(list(im.size)==r['size'],'Anniversary paint dimensions differ')
        return np.asarray(im.convert('RGBA')).copy()


def _field_chunk(bundle):
    from . import nfl2k5_modern_metlife as mm
    tx=mm._tools()[0]
    for chunk in tx.parse_chunks(bundle,allow_trailing=True):
        if chunk.kind=='SCNE':
            rec,decoded=mm._scene(bundle,chunk)
            if rec.get('name')=='field':return chunk,rec,decoded
    raise ValueError('venue resource lacks its native field scene')


def _wordmark(bundle,team=None):
    """The user's retail wordmark, separated from its turf/background.

    This retains an existing team typeface instead of inventing one. A 2004
    typeface is still only an approximation where an era used another mark.
    """
    from . import nfl2k5_modern_venues_2026 as mv
    from PIL import Image
    import numpy as np
    _,rec,decoded=_field_chunk(bundle);rows=mv.p8_rows(rec);materials=mv.rows_by_material(rec)
    parts=[mv.read_texture(decoded,rec,rows[materials['endzone_N_'+p]]) for p in 'LMR']
    rgba=np.concatenate(parts,axis=1).copy()
    if team=='CIN':
        # Bengals glyphs have a closed white border. Flood the exterior of
        # that border to discard the surrounding tiger stripes; retain each
        # enclosed black letter. Cropping a generic central 560-pixel strip
        # would cut the B and S off this unusually wide wordmark.
        from collections import deque
        rgb=rgba[:,:,:3].astype(int);white=(rgb.min(axis=2)>160)&(rgb.max(axis=2)-rgb.min(axis=2)<75)
        height,width=white.shape;outside=np.zeros_like(white);queue=deque()
        for x in range(width):queue.append((0,x));queue.append((height-1,x))
        for y in range(height):queue.append((y,0));queue.append((y,width-1))
        while queue:
            y,x=queue.popleft()
            if y<0 or y>=height or x<0 or x>=width or outside[y,x] or white[y,x]:continue
            outside[y,x]=True;queue.extend(((y-1,x),(y+1,x),(y,x-1),(y,x+1)))
        rgba[:,:,3]=np.where(~outside,255,0).astype('uint8')
        im=Image.fromarray(rgba);box=im.getbbox();require(box is not None,'retail Bengals wordmark is blank')
        return np.asarray(im.crop(box).resize((560,104),Image.Resampling.LANCZOS))
    rgba=rgba[:,104:664]
    rgb=rgba[:,:,:3].astype(float)
    corners=np.concatenate([rgb[:8,:8].reshape(-1,3),rgb[-8:,-8:].reshape(-1,3)])
    bg=np.median(corners,axis=0)
    grass=(rgb[:,:,1]>rgb[:,:,0]*1.02)&(rgb[:,:,1]>rgb[:,:,2]*1.07)
    mask=(np.linalg.norm(rgb-bg,axis=2)>60)&~grass
    rgba[:,:,3]=np.where(mask,255,0).astype('uint8')
    return np.asarray(Image.fromarray(rgba).resize((560,104),Image.Resampling.LANCZOS))


def _endzone(row,end,wordmarks):
    from PIL import Image
    import numpy as np
    if not wordmarks or row.get('pattern')=='diagonal' or row.get('endzone_files'):return art(row['row'],'endzone_'+end)
    side=0 if end=='N' else 1;e=row['endzones'][side];key=e['team']
    # GREEN BAY is distinct from the PACKERS retail donor. Retain the bounded
    # authored phrase until its specific period stencil is supplied.
    if key not in wordmarks or e['text']=='GREEN BAY' or e.get('wordmark_file'):return art(row['row'],'endzone_'+end)
    rgba=wordmarks[key].copy();rgb=rgba[:,:,:3].astype(float)
    primary=np.asarray(Image.new('RGB',(1,1),e['foreground']).getpixel((0,0)))
    outline=np.asarray(Image.new('RGB',(1,1),e['outline']).getpixel((0,0)))
    white=np.min(rgb,axis=2)>190
    rgba[:,:,:3]=np.where(white[:,:,None],outline,primary).astype('uint8')
    # Preserve the supplied end-zone fill/logo layout; the donor covers the
    # old authored wordmark region with its own shape.
    base=art(row['row'],'endzone_'+end).copy()
    fill=(0,0,0,0) if e['background']=='turf' else Image.new('RGBA',(1,1),e['background']).getpixel((0,0))
    base[10:118,104:664]=fill
    canvas=Image.fromarray(base)
    if row.get('pattern')=='stripes':
        from PIL import ImageDraw
        canvas=Image.new('RGBA',(768,128),e['background']);d=ImageDraw.Draw(canvas)
        for x in range(-128,850,100):
            d.polygon([(x,0),(x+45,0),(x+173,128),(x+128,128)],fill='#101820')
    canvas.alpha_composite(Image.fromarray(rgba),(104,12))
    return np.asarray(canvas)


def _field(template,row,wordmarks=None,old_shield=None):
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    from PIL import Image
    import numpy as np
    tx,_,_,HEADER,_=mm._tools();chunk,rec,decoded=_field_chunk(template)
    rows=mv.p8_rows(rec);materials=mv.rows_by_material(rec);out=bytearray(decoded);textures=[]
    require(all(f'endzone_{end}_{part}' in materials for end in 'NS' for part in 'LMR'),
            'split field template lacks end-zone materials')
    require(len({materials[f'endzone_{end}_{part}'] for end in 'NS' for part in 'LMR'})==6,
            'period fields require six independent end-zone allocations')
    for end in 'NS':
        paint=_endzone(row,end,wordmarks)
        for part,n in zip('LMR',range(3)):
            key=f'endzone_{end}_{part}';r=rows[materials[key]]
            current=mv.read_texture(decoded,rec,r)
            authored=paint[:,n*256:(n+1)*256]
            authored=np.asarray(Image.fromarray(authored).resize((r['width'],r['height']),Image.Resampling.LANCZOS))
            result=mm.composite_over(mv.clean_turf(current),authored)
            mm.write_p8(out,rec['system_bytes'],r,result,256);textures.append(materials[key])
    for key in ('center_logo','playoff_logo','AFC_shield','NFC_shield'):
        require(key in materials,'period field template lacks '+key)
        r=rows[materials[key]]
        paint=(np.zeros((r['height'],r['width'],4),dtype='uint8')
               if key in ('AFC_shield','NFC_shield') else art(row['row'],key))
        if key=='center_logo' and row['center']=='NFL' and row['season']<2008 and old_shield is not None:
            paint=old_shield
        paint=np.asarray(Image.fromarray(paint).resize((r['width'],r['height']),Image.Resampling.LANCZOS))
        mm.write_p8(out,rec['system_bytes'],r,paint,256);textures.append(materials[key])
    return _seal_field(template,chunk,rec,decoded,out,textures)


def _seal_field(template,chunk,rec,decoded,out,textures):
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    tx,_,_,HEADER,_=mm._tools();rows=mv.p8_rows(rec)
    # New separate resources may grow. All SCNE offsets remain native because
    # decoded geometry and descriptors stay exactly the field template's size.
    stream,_=tx.compress_vc_lz(bytes(out));stored=(len(stream)+15)&~15;stream+=bytes(stored-len(stream))
    scratch=tx.minimum_vc_lz_overlap_scratch(stream,stored,len(out));scratch=(scratch+15)&~15
    fields=list(HEADER.unpack_from(template,chunk.offset));fields[1]=stored;fields[5]=scratch
    span=HEADER.pack(*fields)+stream
    back,_=tx.decode_chunk(span,tx.parse_chunks(span,allow_trailing=True)[0]);require(back==bytes(out),'period field round trip differs')
    protected=bytearray(out);original=bytearray(decoded)
    for index in textures:
        r=rows[index]
        for at,size in ((rec['system_bytes']+r['pixel_offset'],r['palette_offset']-r['pixel_offset']),
                        (rec['system_bytes']+r['palette_offset'],1024)):
            protected[at:at+size]=original[at:at+size]
    require(protected==original,'period paint changed protected geometry or texture metadata')
    return span,dict(template_field=sha(mm.scene_span(template,chunk)),field=sha(span),
                     decoded=sha(out),geometry_and_descriptors_preserved=True,stored_size=stored,
                     overlap_scratch=scratch,texture_indices=textures)


def _retail_playoff_field(source):
    """Retain the 2003 retail field except its inappropriate title-game stamps."""
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    import numpy as np
    chunk,rec,decoded=_field_chunk(source);rows=mv.p8_rows(rec);materials=mv.rows_by_material(rec)
    out=bytearray(decoded);indices=[]
    for key in ('AFC_shield','NFC_shield'):
        r=rows[materials[key]]
        mm.write_p8(out,rec['system_bytes'],r,np.zeros((r['height'],r['width'],4),dtype='uint8'),256)
        indices.append(materials[key])
    span,detail=_seal_field(source,chunk,rec,decoded,out,indices)
    detail['retail_field_reused_except_championship_stamps']=True
    return span,detail


def compile_assets(get_built,get_retail,situ,*,progress=None):
    """Return ``({alias filename: bytes}, receipt)`` from name-keyed read callbacks.

    get_built reads the completed target's existing venue resources. get_retail
    reads the unchanged retail source. No input callback is ever written to.
    """
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    require(struct.unpack_from('<I',situ,32+0x40)[0]==51,'expected 51 physical Anniversary rows')
    output={};receipts=[];templates={};wordmarks={};old_shield=None
    for row in catalog():
        index=row['row']-1;code=variant(situ,index);name=row['source_prefix']+code+'.iff'
        source=(get_built if row['source_kind']=='built' else get_retail)(name)
        require(isinstance(source,bytes) and 32<len(source)<16*1024*1024,'venue source exceeds bounds')
        if code not in templates:templates[code]=get_retail('s25'+code+'.iff')
        for end in row['endzones']:
            team=end['team']
            if team not in wordmarks:wordmarks[team]=_wordmark(get_retail(WORDMARKS[team]+'dd.iff'),team)
        if old_shield is None and row['center']=='NFL' and row['season']<2008:
            _,shield_record,shield_decoded=_field_chunk(get_retail('s43dd.iff'))
            shield_rows=mv.p8_rows(shield_record);shield_materials=mv.rows_by_material(shield_record)
            old_shield=mv.read_texture(shield_decoded,shield_record,shield_rows[shield_materials['center_logo']]).copy()
            # Retail 2004's many-star shield has a flat green outer fill.
            rgb=old_shield[:,:,:3].astype(int);grass=(rgb[:,:,1]>rgb[:,:,0])&(rgb[:,:,1]>rgb[:,:,2])
            old_shield[:,:,3]=__import__('numpy').where(grass,0,255).astype('uint8')
        chunk,_,_=_field_chunk(source);before=mm.scene_span(source,chunk)
        if row['row'] in (24,25):
            # Keep the actual 2003 helmet/wordmark/NFL PLAYOFFS paint. The
            # generic retail field also carries conference-title stamps, which
            # do not belong to these wildcard/divisional matchups.
            span,detail=_retail_playoff_field(source)
        else:span,detail=_field(templates[code],row,wordmarks,old_shield)
        after=source[:chunk.offset]+span+source[chunk.offset+len(before):]
        _field_chunk(after)
        alias=f'a{index:02d}{code}.iff';require(mv.name_id(alias) not in {mv.name_id(n) for n in output},'alias ID collision')
        output[alias]=after;receipts.append(dict(row=row['row'],alias=alias,source=name,
            source_kind=row['source_kind'],before=sha(source),after=sha(after),size=len(after),
            field_offset=chunk.offset,before_field_size=len(before),after_field_size=len(span),
            outside_field_chunks_identical=True,art_status=row['art_status'],detail=detail))
        if progress:progress(row['row'],51,alias)
    return output,dict(schema='nfl2k5_espn25_fields_receipt/v1',catalog_sha256=sha(DATA.read_bytes()),
        manifest_sha256=sha((ART/'manifest.json').read_bytes()),runtime_witnessed=False,
        assets=receipts,total_bytes=sum(map(len,output.values())),
        scope='Separate Anniversary resources only; existing modern and retail venue files are read only.')

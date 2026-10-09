#!/usr/bin/env python3
"""Recombine existing native kit parts without quantizing or resizing any texture.

The recipe names existing packages. Compilation copies decoded native chunks into
the target's fixed file allocation, with exact decode read-back, then calls w1 for mud.
Three recombined atlases use the game's existing truecolor format to avoid palette loss.
No artwork or binary resources belong in the repository.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b77')]
import u3s_alternates as alt
import u3s_repair as uniform
import u1_audit as audit
import w1_repair as w1
from nfl_txtr import (parse_chunks, decode_chunk, parse_texture, texture_to_rgba,
                      rebuild_compressed_chunk_fixed_span, encode_rgba_png,
                      unswizzle_2d, swizzle_2d, TxtrError)

RECIPES = ROOT / 'data/nfl2k5_moment_era_kits.json'
SCHEMA = 'b77/a5k/native-parts/v1'
sha, require = uniform.sha, uniform.require
COMPACT_CACHE = {}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def read_binary(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as stream:
        return stream.read()


def write_binary(path, data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0),0o644)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data)


def recipes():
    doc = json.loads(RECIPES.read_text())
    require(doc['schema'] == SCHEMA and len(doc['items']) == 5, 'expected exactly five era kits')
    require([(r['id'],r['code'],r['style']) for r in doc['items']] ==
            [('G1','16',11),('G1b','21',14),('G2','17',6),('G3','02',1),('G4','22',4)],
            'recipes differ from the five approved target slots')
    return doc['items']


def lossless_rebuild(span, decoded):
    try:
        return rebuild_compressed_chunk_fixed_span(span, decoded)
    except TxtrError as exc:
        if 'bound' not in str(exc):
            raise
        from nfl_vc_lz_fill import rebuild_fixed_span_filled
        return rebuild_fixed_span_filled(span, decoded, encoder='optimal')


def wet_template(span):
    """Normalize retail mud palettes to w1's accepted input, then use its derivation.

    Some retail whites have ~0.936 palettes, rather than exactly darken_60.
    Only mud palettes are normalized. Clean pixels and all mip chains stay exact.
    """
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    new = bytearray(decoded)
    textures = {t.name: t for t in (audit.tset_texture(decoded, i)
                for i in range(struct.unpack_from('<I', decoded, 4)[0]))}
    for name, t in textures.items():
        if name.endswith('_mud') or name + '_mud' not in textures:
            continue
        m = textures[name + '_mud']
        c, at = 256 + t.palette_offset, 256 + m.palette_offset
        for k in range(256):
            pixel = decoded[c + 4*k:c + 4*k + 4]
            new[at + 4*k:at + 4*k + 4] = bytes([w1.dark(v) for v in pixel[:3]]) + pixel[3:]
    normalized = lossless_rebuild(span, bytes(new))[0] if bytes(new) != decoded else span
    try:
        return w1.rewrite_chunk(normalized)
    except TxtrError as exc:
        if 'bound' not in str(exc):
            raise
        # Give w1 a temporary larger compressed allocation, then fit its exact
        # decoded output back with the existing optimal encoder.
        from nfl_txtr import HEADER
        fields = list(HEADER.unpack_from(normalized))
        fields[1] += 8192
        fields[5] += 8192
        temporary = HEADER.pack(*fields) + normalized[HEADER.size:] + bytes(8192)
        wet, receipt = w1.rewrite_chunk(temporary)
        decoded_wet, _ = decode_chunk(wet, parse_chunks(wet)[0])
        return lossless_rebuild(span, decoded_wet)[0], receipt


def native_atlas(base, chunk, overlays, format_name):
    """Exact donor rectangles at every mip, with no colour quantization."""
    import nfl2k5_team_2026_art as art
    t=parse_texture(base,chunk)
    donors=[base]+[d for d,_boxes in overlays]
    require(t.format_code==11 and all(parse_texture(d,chunk)==t for d in donors),'atlas layouts differ')
    palettes=[d[chunk.system_bytes+t.palette_offset:chunk.system_bytes+t.palette_offset+1024] for d in donors]
    video=[];cursor=t.pixel_offset
    for level in range(t.mip_levels):
        width,height=max(1,t.width>>level),max(1,t.height>>level)
        planes=[unswizzle_2d(d[chunk.system_bytes+cursor:chunk.system_bytes+cursor+width*height],width,height,1) for d in donors]
        pixels=bytearray(width*height*4)
        for y in range(height):
            for x in range(width):
                donor=0
                for index,(_d,boxes) in enumerate(overlays,1):
                    if any(x0>>level<=x<(x1+(1<<level)-1)>>level and y0>>level<=y<(y1+(1<<level)-1)>>level
                           for x0,y0,x1,y1 in (art.SPLAYER[b] for b in boxes)):
                        donor=index
                index=planes[donor][y*width+x];at=(y*width+x)*4
                pixels[at:at+4]=palettes[donor][index*4:index*4+4]
        video.append((width,height,bytes(pixels)));cursor+=width*height
    system=bytearray(base[:chunk.system_bytes])
    if format_name=='P8':
        colors=sorted({p[at:at+4] for _w,_h,p in video for at in range(0,len(p),4)})
        require(len(colors)<=256,f'exact atlas needs {len(colors)} colours, exceeds P8')
        lookup={color:i for i,color in enumerate(colors)}
        indices=[swizzle_2d(bytes(lookup[p[at:at+4]] for at in range(0,len(p),4)),w,h,1) for w,h,p in video]
        palette=b''.join(colors)+bytes(4*(256-len(colors)))
        return bytes(system)+b''.join(indices)+palette
    require(format_name=='A8R8G8B8','unsupported atlas format')
    struct.pack_into('<I',system,t.descriptor_offset+8,0)
    struct.pack_into('<I',system,t.descriptor_offset+12,(t.packed_format&~0xff00)|(6<<8))
    return bytes(system)+b''.join(swizzle_2d(p,w,h,4) for w,h,p in video)


def truecolor_atlas(base, other, chunk, boxes):
    return native_atlas(base,chunk,[(other,boxes)],'A8R8G8B8')


def atlas_overlays(recipe):
    atlas=recipe['atlas']
    return atlas.get('overlays',[dict(donor=atlas.get('donor'),boxes=atlas.get('boxes'))])


def encoded_span(template, decoded, video_bytes):
    from nfl_txtr import HEADER, compress_vc_lz, minimum_vc_lz_overlap_scratch
    c=parse_chunks(template)[0];_old,info=decode_chunk(template,c)
    stream,_=compress_vc_lz(decoded,stream_tag=info.stream_tag,offset_bits=info.offset_bits,verify_roundtrip=True)
    fields=list(HEADER.unpack_from(template));fields[1]=(len(stream)+15)&~15;fields[3]=video_bytes
    padding=fields[1]-len(stream)
    fields[5]=max(fields[5],(max(padding,minimum_vc_lz_overlap_scratch(stream,fields[1],len(decoded)))+15)&~15)
    span=HEADER.pack(*fields)+stream+bytes(padding)
    require(decode_chunk(span,parse_chunks(span)[0])[0]==decoded,'native atlas round-trip differs')
    return span


def compact_span(span, *, optimal=False):
    """Same native decoded allocation, smaller stored allocation, guarded overlap."""
    from nfl_txtr import HEADER, minimum_vc_lz_overlap_scratch
    from nfl_vc_lz_fill import compress_optimal
    key=(sha(span),optimal)
    if key in COMPACT_CACHE:
        return COMPACT_CACHE[key]
    chunk = parse_chunks(span)[0]
    decoded, info = decode_chunk(span, chunk)
    stream = (compress_optimal(decoded, stream_tag=info.stream_tag, offset_bits=info.offset_bits)
              if optimal else span[HEADER.size:HEADER.size+info.consumed_bytes])
    fields = list(HEADER.unpack_from(span))
    fields[1] = (len(stream)+15) & ~15
    padding = fields[1]-len(stream)
    fields[5] = max(fields[5], (max(padding, minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded)))+15)&~15)
    rebuilt = HEADER.pack(*fields)+stream+bytes(padding)
    require(decode_chunk(rebuilt, parse_chunks(rebuilt)[0])[0] == decoded, 'compact span changed decoded bytes')
    COMPACT_CACHE[key]=rebuilt
    return rebuilt


def repack_prefix(target, donor, part_packages, recipe):
    """Borrow stored space between texture chunks inside the same owned kit.

    NAME, bump maps and all later chunk offsets stay fixed. The native loader
    walks wrapper lengths, so it does not rely on the old texture offsets.
    """
    from nfl_txtr import HEADER, minimum_vc_lz_overlap_scratch
    tc = parse_chunks(target)
    sources = {'base': donor, **part_packages}
    pieces = []
    for index in range(1, 44):
        raw = sources[recipe.get('chunks', {}).get(str(index), 'base')]
        c = parse_chunks(raw)[index]
        span = raw[c.offset:c.end_offset]
        if index in (1, 2, 3):
            span = wet_template(span)[0]
        pieces.append(compact_span(span, optimal=recipe['id'] in ('G1','G3') and index in (1, 2, 3, 11, 12, 43)))
    budget = tc[44].offset-tc[1].offset
    total = sum(map(len, pieces))
    require(total <= budget, f'exact native prefix needs {total}, available {budget}')
    # Last prefix chunk absorbs the unused stored space. Its decoded allocation
    # and every texture/mip stay unchanged; the scratch word covers its padding.
    last = pieces[-1]
    c = parse_chunks(last)[0]
    decoded, info = decode_chunk(last, c)
    stream = last[HEADER.size:HEADER.size+info.consumed_bytes]
    fields = list(HEADER.unpack_from(last))
    fields[1] += budget-total
    fields[5] = max(fields[5], (max(fields[1]-len(stream), minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded)))+15)&~15)
    pieces[-1] = HEADER.pack(*fields)+stream+bytes(fields[1]-len(stream))
    result = bytearray(target)
    result[tc[1].offset:tc[44].offset] = b''.join(pieces)
    return bytes(result)


def repack_suffix(target, donor, part_packages, recipe):
    from nfl_txtr import HEADER, minimum_vc_lz_overlap_scratch
    chunks = parse_chunks(target)
    pieces = []
    for index in range(49, 53):
        c = parse_chunks(donor)[index]
        span = donor[c.offset:c.end_offset]
        if index == 51 and recipe.get('atlas'):
            decoded, _ = decode_chunk(donor, c)
            overlays=[]
            for row in atlas_overlays(recipe):
                other=part_packages[row['donor']]
                overlays.append((decode_chunk(other,parse_chunks(other)[51])[0],row['boxes']))
            mixed = native_atlas(decoded,c,overlays,recipe['atlas']['format'])
            span = encoded_span(span,mixed,len(mixed)-c.system_bytes)
        pieces.append(compact_span(span))
    budget = len(target)-chunks[49].offset
    used = sum(map(len, pieces))
    prefix=target[:chunks[49].offset]
    if used > budget:
        # First reclaim prefix padding, then losslessly recompress existing
        # relief maps if necessary. Their pixels and mip levels stay exact.
        c=chunks[43]
        pieces_before=[target[:c.offset],compact_span(target[c.offset:c.end_offset])]
        tail={i:target[chunks[i].offset:chunks[i].end_offset] for i in range(44,49)}
        def available():
            return len(target)-sum(map(len,pieces_before))-sum(map(len,tail.values()))
        for index in (45,47,46,48):
            if available() >= used:
                break
            tail[index]=compact_span(tail[index],optimal=True)
        require(available() >= used, f'native suffix needs {used}, available {available()} after lossless recompression')
        prefix=b''.join(pieces_before+[tail[i] for i in range(44,49)])
        budget=len(target)-len(prefix)
    last = pieces[-1];c=parse_chunks(last)[0];decoded, info=decode_chunk(last,c)
    stream=last[HEADER.size:HEADER.size+info.consumed_bytes]
    fields=list(HEADER.unpack_from(last));fields[1] += budget-used
    fields[5]=max(fields[5],(max(fields[1]-len(stream),minimum_vc_lz_overlap_scratch(stream,fields[1],len(decoded)))+15)&~15)
    pieces[-1]=HEADER.pack(*fields)+stream+bytes(fields[1]-len(stream))
    result=prefix+b''.join(pieces)
    require(len(result)==len(target),'repacked complete kit size differs')
    return result


def compile_kit(target, donor, part_packages, recipe):
    """Return package, per-chunk provenance; every source texture retains all mips."""
    original = target
    if recipe.get('repack_prefix'):
        target = repack_prefix(target, donor, part_packages, recipe)
    if recipe.get('repack_suffix'):
        target = repack_suffix(target, donor, part_packages, recipe)
    result = bytearray(target)
    unif_source = part_packages[recipe['unif_donor']] if recipe.get('unif_donor') else donor
    result[alt.UNIF_COLOURS:alt.UNIF_COLOURS+8] = unif_source[alt.UNIF_COLOURS:alt.UNIF_COLOURS+8]
    require(len(result) == len(original), 'kit allocation changed')
    return bytes(result), []


def export_package(raw, selector, out):
    """Reuse the u3s export naming without a disc-wide export."""
    folder = out / 'uniforms' / selector
    folder.mkdir(parents=True, exist_ok=True)
    assets = []
    for chunk in parse_chunks(raw):
        if chunk.kind not in ('TSET', 'TXTR'):
            continue
        decoded, _ = decode_chunk(raw, chunk)
        textures = [(i, audit.tset_texture(decoded, i)) for i in range(struct.unpack_from('<I', decoded, 4)[0])] if chunk.kind == 'TSET' else [(0, parse_texture(decoded, chunk))]
        for index, t in textures:
            if chunk.kind == 'TSET' and chunk.index in alt.TSET_KINDS:
                if t.name.endswith('_mud'):
                    continue
                name = alt.TSET_KINDS[chunk.index]
            elif chunk.index in (11, 12):
                name = 'helmet_' + t.name
            elif 13 <= chunk.index <= 42:
                name = audit.digit_filename(chunk.index, t.name)[:-4]
            else:
                name = t.name
            write_binary(folder / (name+'.png'),encode_rgba_png(t.width, t.height, texture_to_rgba(decoded, chunk, t)))
            assets.append(dict(file=name+'.png', name=t.name, chunk=chunk.index, kind=chunk.kind,
                               tset_index=index, size=[t.width, t.height]))
    return dict(sha256=sha(raw), size=len(raw), assets=assets, unif=alt.unif_words(raw))


def compile_resources(source, out, resume=False):
    resources, receipts = {}, {}
    for recipe in recipes():
        print('compile', recipe['id'], flush=True)
        for side in 'HA':
            selector = recipe['code'] + side + str(recipe['style'])
            base_name = recipe['kits'][side]
            read = lambda name: read_binary(source / (name+'.IFF'))
            target, donor = read(selector), read(base_name)
            parts = {key: read(name) for key, name in recipe.get('parts', {}).items()}
            cached=out/'resources'/(selector+'.IFF')
            if resume and cached.exists():
                import a5k_acceptance
                fixed=read_binary(cached)
                all_sources={base_name:donor,**{name:read(name) for name in recipe.get('parts',{}).values()}}
                try:
                    a5k_acceptance.verify_kit(target,fixed,all_sources,recipe,side)
                    rows=[]
                except ValueError:
                    fixed,rows=compile_kit(target,donor,parts,recipe)
            else:
                fixed, rows = compile_kit(target, donor, parts, recipe)
            resources[selector+'.IFF'] = []
            if recipe.get('atlas'):
                rows=[dict(chunk='native_parts',offset=parse_chunks(target)[1].offset,
                           length=len(target)-parse_chunks(target)[1].offset)]
            elif recipe.get('repack_prefix'):
                chunks = parse_chunks(target)
                at, end = chunks[1].offset, chunks[44].offset
                rows.insert(0, dict(chunk='1..43', offset=at, length=end-at))
            if recipe.get('repack_suffix') and not recipe.get('atlas'):
                at = parse_chunks(target)[49].offset
                rows.append(dict(chunk='49..52', offset=at, length=len(target)-at))
            for row in rows:
                at, n = row['offset'], row['length']
                if target[at:at+n] == fixed[at:at+n]:
                    continue
                path = out / (sha(fixed[at:at+n])+'.span')
                path.parent.mkdir(parents=True, exist_ok=True)
                write_binary(path,fixed[at:at+n])
                resources[selector+'.IFF'].append(dict(offset=at, length=n, label=f'chunk_{row["chunk"]}',
                    before_sha256=sha(target[at:at+n]), after_sha256=sha(fixed[at:at+n]), replacement=path.name))
            at = alt.UNIF_COLOURS
            if target[at:at+8] != fixed[at:at+8]:
                span = fixed[at:at+8]; path = out / (sha(span)+'.span'); write_binary(path,span)
                resources[selector+'.IFF'].append(dict(offset=at, length=8, label='unif_color',
                    before_sha256=sha(target[at:at+8]), after_sha256=sha(span), replacement=path.name))
            (out / 'resources').mkdir(exist_ok=True)
            write_binary(out / 'resources' / (selector+'.IFF'),fixed)
            export_package(fixed, selector, out)
            receipts[selector] = dict(source=base_name, chunks=rows, before_sha256=sha(target), after_sha256=sha(fixed))
    manifest = dict(schema=SCHEMA, resources=resources)
    write_json(out / 'native_manifest.json', manifest)
    write_json(out / 'compile_receipts.json', receipts)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='reuse only cached kits whose every donor mip verifies')
    args = parser.parse_args()
    compile_resources(args.resources, args.out, args.resume)

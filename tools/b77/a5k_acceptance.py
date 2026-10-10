#!/usr/bin/env python3
"""Scripted offline acceptance of the five native period kits and six moments."""
from __future__ import annotations
import argparse
import dataclasses
import json
from pathlib import Path
import struct
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tools/b77'), str(ROOT/'tests')]
import a5k_kits as kits
import a5k_repair as repair
import a1_uniforms as uni
import kitx_repair as kitx
import u3s_slots as slots
from mod_editor.core import nfl2k5_uniform_slots as us, nfl2k5_historic_styles as hs
from nfl_txtr import parse_chunks, decode_chunk, parse_texture, texture_to_rgba, minimum_vc_lz_overlap_scratch

require, sha = kits.require, kits.sha


def mip_pixels(decoded, chunk, texture):
    cursor, out = texture.pixel_offset, []
    for level in range(texture.mip_levels):
        width, height = max(1, texture.width >> level), max(1, texture.height >> level)
        current = dataclasses.replace(texture, pixel_offset=cursor, width=width, height=height)
        out.append(texture_to_rgba(decoded, chunk, current))
        require(texture.format_code in (11, 0x7f, 6), 'unhandled native mip format')
        cursor += width*height*(4 if texture.format_code == 6 else 1)
    return out


def compare_texture_chunks(source, source_chunk, result, result_chunk):
    before, _ = decode_chunk(source, source_chunk)
    after, _ = decode_chunk(result, result_chunk)
    textures = ([(kits.audit.tset_texture(before, i), kits.audit.tset_texture(after, i))
                for i in range(struct.unpack_from('<I', before, 4)[0])]
                if source_chunk.kind == 'TSET' else [(parse_texture(before, source_chunk), parse_texture(after, result_chunk))])
    rows = []
    for a, b in textures:
        if a.name.endswith('_mud'):
            continue
        require((a.name, a.width, a.height, a.mip_levels) == (b.name, b.width, b.height, b.mip_levels), 'texture layout differs')
        x, y = mip_pixels(before, source_chunk, a), mip_pixels(after, result_chunk, b)
        require(x == y, f'{a.name}: donor mip pixels differ')
        rows.append(dict(name=a.name, dimensions=[a.width,a.height], mip_levels=len(x),
                         rgba_sha256=[sha(p) for p in y], source_pixels_equal=True))
    return rows


def verify_atlas(donor, after, chunk, sources, recipe):
    """Compare decoded RGBA rectangles directly, independently of atlas encoding."""
    from nfl2k5_team_2026_art import SPLAYER
    source_chunk=parse_chunks(donor)[51]
    native=decode_chunk(donor,source_chunk)[0]
    texture=parse_texture(native,source_chunk)
    expected=mip_pixels(native,source_chunk,texture)
    for row in kits.atlas_overlays(recipe):
        other=sources[recipe['parts'][row['donor']]]
        other_chunk=parse_chunks(other)[51]
        data=decode_chunk(other,other_chunk)[0]
        pixels=mip_pixels(data,other_chunk,parse_texture(data,other_chunk))
        for level,(base,part) in enumerate(zip(expected,pixels)):
            width,height=max(1,texture.width>>level),max(1,texture.height>>level)
            mixed=bytearray(base)
            for box in row['boxes']:
                x0,y0,x1,y1=SPLAYER[box]
                for y in range(y0>>level,min(height,(y1+(1<<level)-1)>>level)):
                    lo=(y*width+(x0>>level))*4
                    hi=(y*width+min(width,(x1+(1<<level)-1)>>level))*4
                    mixed[lo:hi]=part[lo:hi]
            expected[level]=bytes(mixed)
    actual=decode_chunk(after,chunk)[0]
    result=mip_pixels(actual,chunk,parse_texture(actual,chunk))
    require(result==expected,'far-player atlas donor pixels differ')
    return dict(chunk=51,overlays=kits.atlas_overlays(recipe),exact_native_atlas=True,
                rgba_sha256=[sha(p) for p in result])


def colour_anchors(raw, recipe):
    """Reject source-equal kits whose visible colours miss the requested look."""
    def pixels(index):
        c=parse_chunks(raw)[index];d,_=decode_chunk(raw,c)
        t=kits.audit.tset_texture(d,0) if c.kind=='TSET' else parse_texture(d,c)
        return t,mip_pixels(d,c,t)[0]
    values={}
    if recipe['id']=='G2':
        t,p=pixels(2);at=(120*t.width+20)*4;r,g,b,a=p[at:at+4]
        require(r-b>50 and g-b>40,'NO pants colour is not old gold')
        values['old_gold_pants']=[r,g,b,a]
    elif recipe['id']=='G1b':
        t,p=pixels(4);lo=(t.width//2)*4;hi=((t.height-1)*t.width+t.width//2)*4
        require(max(p[lo:lo+3])<32 and min(p[hi:hi+3])>220,'PHI socks are not black-white')
        values['black_white_socks']=[list(p[lo:lo+4]),list(p[hi:hi+4])]
    elif recipe['id']=='G3':
        t,p=pixels(4);at=((t.height//2)*t.width+t.width//2)*4
        require(max(p[at:at+3])<32,'BAL socks are not black')
        values['black_socks']=list(p[at:at+4])
    elif recipe['id']=='G4':
        _t,p=pixels(13)
        visible=Counter(tuple(p[i:i+4]) for i in range(0,len(p),4) if p[i+3]>128 and max(p[i:i+3])>32)
        (r,g,b,a),_n=visible.most_common(1)[0]
        require(r-b>100 and g-b>50,'PIT numeral face is not gold')
        values['gold_numerals']=[r,g,b,a]
    return dict(passed=True,values=values)


def verify_kit(before, after, sources, recipe, side):
    a, b = parse_chunks(before), parse_chunks(after)
    require(len(a) == len(b) == 53 and len(before) == len(after), 'kit file size/chunk count changed')
    require([(c.kind,c.system_bytes,c.video_bytes) for c in a if not recipe.get('atlas') or c.index!=51] ==
            [(c.kind,c.system_bytes,c.video_bytes) for c in b if not recipe.get('atlas') or c.index!=51], 'unexpected decoded allocator size change')
    donor = sources[recipe['kits'][side]]
    unif_source=sources[recipe['parts'][recipe['unif_donor']]] if recipe.get('unif_donor') else donor
    require(after[0x50:0x58] == unif_source[0x50:0x58], 'facemask/turtleneck differ from donor')
    rows, mud, guards = [], [], []
    for old, new in zip(a,b):
        if new.kind not in ('TSET','TXTR'):
            continue
        span = after[new.offset:new.end_offset]
        decoded, info = decode_chunk(after,new)
        if info:
            stream=span[32:32+info.consumed_bytes]
            minimum=minimum_vc_lz_overlap_scratch(stream,new.stored_size,len(decoded))
            require(new.overlap_scratch_bytes >= minimum and new.overlap_scratch_bytes >= new.stored_size-len(stream),
                    'native in-place decompression scratch is too small')
            guards.append(dict(chunk=new.index, minimum=minimum, scratch=new.overlap_scratch_bytes,
                               consumed=len(stream), stored=new.stored_size))
        if 45 <= new.index <= 48:
            compare_texture_chunks(before,old,after,new)
            continue
        if new.index == 51 and recipe.get('atlas'):
            rows.append(verify_atlas(donor,after,new,sources,recipe))
            continue
        source_key=recipe.get('chunks',{}).get(str(new.index))
        source=sources[recipe['parts'][source_key]] if source_key else donor
        sc=parse_chunks(source)[new.index]
        textures=compare_texture_chunks(source,sc,after,new)
        rows.append(dict(chunk=new.index, donor=recipe['parts'][source_key] if source_key else recipe['kits'][side],textures=textures))
        if new.index in (1,2,3):
            count=kitx.check_mud(span,span)
            require(kits.w1.rewrite_chunk(span)[0] == span,'w1 derivation does not replay as a no-op')
            mud.append(dict(chunk=new.index,pairs=count,wet_93=True,w1_replay_noop=True))
    video_growth=sum(c.video_bytes for c in b)-sum(c.video_bytes for c in a)
    expected_growth=129920 if recipe.get('atlas',{}).get('format')=='A8R8G8B8' else 0
    require(video_growth==expected_growth,'unexpected video allocation growth')
    return dict(textures=rows,mud=mud,worn_colour_anchors=colour_anchors(after,recipe),allocator=dict(stored_size_unchanged=True,decoded_sizes_unchanged=not video_growth,
        video_growth_bytes=video_growth,atlas_format='A8R8G8B8' if video_growth else 'P8',
        system_bytes=sum(c.system_bytes for c in b),video_bytes=sum(c.video_bytes for c in b),
        max_scratch_before=max(c.overlap_scratch_bytes for c in a),max_scratch_after=max(c.overlap_scratch_bytes for c in b),
        guards=guards),relief_maps_unchanged=True)


def team_records(roster):
    return {c:roster[32+at:32+at+us.TEAM_SIZE] for at,c in hs.team_records(roster)[:32]}


def phase_a(xbe, records):
    """Bounded capacity probes, not a claim that runtime expansion is impossible."""
    machine=slots.Machine(xbe)
    native_maximum=machine.call(0xe2f60)
    require(native_maximum==14,'unexpected native style limit')
    cycle={}
    for r in kits.recipes():
        record=records[r['code']]
        native=machine.cycle(record)
        cycle[r['team']]=native
    probes=[]
    for style in (15,16):
        cpu=slots.Machine(xbe)
        cpu.m.mem_write(cpu.team,records['21'])
        try:
            result=cpu.call(0xe2a90,eax=cpu.team,ecx=style)
            probes.append(dict(style=style,result=result))
        except Exception as exc:
            probes.append(dict(style=style,native_failure=type(exc).__name__+': '+str(exc)))
    return dict(time_box='bounded native investigation; approved fallback used',result='NO_SOUND_EXPANSION_ESTABLISHED',
        executable_sha256=sha(xbe),
        lookup_probes=probes,team_select=cycle,table_bytes=56,table_offset=us.TABLE,
        next_byte_is_default_style=us.STYLE_BYTE==us.TABLE+56,
        max_style=native_maximum,code_sites=['0xE2A90 fixed jump table','0xE2FB0 max 14','0xE2F60 returns 14',
        '0x20CB30 writes SITU kit words','0x615A0 uses 0xE2F20 clamp'],
        historic_records='same franchise asset code keys the shared kit/cache namespace; no isolated namespace proved',
        capacity_memory='no extra style slots or expanded kit directories were built; capacity allocator/cache proof remains open')


def native_moments(disc, xbe, before_situ, after_situ):
    from mod_editor.core import nfl2k5_espn25_more_moments as mm
    import nfl2k5_b77_menu_native as native
    from nfl2k5_espn25_more_moments_native import FastMomentsCPU
    retail=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
    data=mm.Data.load()
    resources,context,ids,_situ,extra,retail_situ=native.disc_inputs(disc,retail,data)
    order=list(mm.display_order(data))
    result={}
    for name,situ in [('before',before_situ),('after',after_situ)]:
        cpu=FastMomentsCPU(xbe,resources,context,ids,situ_chunk=situ[:32+struct.unpack_from('<I',situ,4)[0]],extra_files=extra)
        rows=[]
        for display in range(51):
            cpu.events.clear();cpu.select(display)
            record=cpu.run(0x20C6F0)
            match=cpu.match()  # calls the game's 617E0/615A0 filename builder
            fields=native.record_fields(cpu,record)
            require(cpu.r(0xBF1858)==order[display],'wrong physical moment')
            rows.append(dict(display_row=display+1,physical_row=order[display]+1,title=fields['title'],
                kits=list(fields['kits']),files={s:match['sides'][s]['kit'] for s in ('away','home')},
                exists={s:match['sides'][s]['kit_exists'] for s in ('away','home')}))
            cpu.run(0x20C3C0)
        result[name]=rows
    expected=uni.read_situ_kits(after_situ)
    for row in result['after']:
        p=row['physical_row']-1
        require(row['kits']==[expected[(p,'away')],expected[(p,'home')]],'native selection differs')
        require(all(row['exists'].values()),'native kit lookup references absent package')
    changed=[r['physical_row'] for a,r in zip(result['before'],result['after']) if a!=r]
    want=sorted({r+1 for r,_s,_b,_a in repair.selection_rows()})
    require(sorted(changed)==want and len(changed)==6,'other moments changed')
    result.update(passed=True,changed_physical_rows=changed,all_other_moments_unchanged=True,
                  path='20CB30 select -> 20C6F0 record -> 617E0/615A0 native match kit lookup',runtime_witnessed=False)
    return result


def attach_validation(result, tests_path, cli_path):
    """Attach completed, separately run unittest and CLI evidence to acceptance."""
    tests=json.loads(repair.read_binary(tests_path))
    required={'test_b77_a5k_kits.py','test_b77_a3_uniforms.py','test_b77_a5_uniforms.py',
              'test_b77_u3s_alternates.py','test_b77_kitx_repair.py'}
    require(tests['complete'] and tests['passed'] and required<={r['file'] for r in tests['files']},'required test files did not complete')
    require(all(r['passed'] and r['exit_code']==0 and r['tests']>0 and r['skipped']==0 for r in tests['files']),
            'failed, empty or skipped test evidence')
    cli=json.loads(repair.read_binary(cli_path))
    require(cli['passed'] and {(r['case'],r['exit_code']) for r in cli['cases']}==
            {('replay',0),('selection_first',0),('foreign',2)} and all(r['passed'] for r in cli['cases']),
            'CLI replay, ordering or refusal evidence did not pass')
    result['5_repair'].update(tests=tests,cli_checks=cli,
        tests_receipt_sha256=sha(repair.read_binary(tests_path)),cli_receipt_sha256=sha(repair.read_binary(cli_path)))
    return result


def run(args):
    manifest=json.loads(repair.read_binary(args.manifest))
    result=dict(schema='b77/a5k/acceptance/v1',phase='B',runtime_witnessed=False)
    sources={p.stem:repair.read_binary(p) for p in args.resources.glob('*.IFF')}
    with kitx.bump._Image.open(args.baseline,writable=False) as before, kitx.bump._Image.open(args.output,writable=False) as after:
        ix=kitx.bump._parsed_index(before)
        groups=repair.patches_for(before,manifest,args.manifest.parent)
        kits_checked={}
        for recipe in kits.recipes():
            for side in 'HA':
                selector=recipe['code']+side+str(recipe['style'])
                print('accept kit',selector,flush=True)
                entry=kitx.w1._entry_for(ix,kitx.bump,selector)
                original=kitx.w1._read_resource(before,ix,entry)
                fixed=kitx.w1._read_resource(after,ix,entry)
                kits_checked[selector]=verify_kit(original,fixed,sources,recipe,side)
        result['1_source_parts']=dict(passed=True,kits=kits_checked,
            changed_parts={'G1':'white road jersey, navy pants, striped socks, silver helmet in both files',
            'G1b':'midnight-green home set in both files, existing black-white socks from PHI 14',
            'G2':'v0.5 retail old-gold pants instead of the stacked Color Rush white pants',
            'G3':'retail black pants and existing BAL Darkness black socks with the style-4 jersey',
            'G4':'black home set in both files, existing gold numerals from PIT 4'},
            colour_repainting=False)
        scope={}
        for name,patches in groups.items():
            ordinal=kitx.PACK_NAMES.index(name)
            a=before.read_pack(ordinal,0,before.pack_size(ordinal));b=after.read_pack(ordinal,0,after.pack_size(ordinal))
            ranges=[(p['offset'],p['offset']+p['length']) for p in patches]
            require(sha(a)==manifest['packs'][name]['before_sha256'] and sha(b)==manifest['packs'][name]['after_sha256'], 'pack hashes differ')
            require(kitx.outside_hash(a,ranges)==kitx.outside_hash(b,ranges)==manifest['packs'][name]['outside_sha256'],'outside bytes differ')
            scope[name]=dict(before_sha256=sha(a),after_sha256=sha(b),size=len(a),ranges=kitx.merge_ranges(ranges),outside_scope_identical=True)
        roster_before=kitx.w1._read_resource(before,ix,ix.entries[5]);roster_after=kitx.w1._read_resource(after,ix,ix.entries[5])
        records_before,records_after=team_records(roster_before),team_records(roster_after)
        machine=slots.Machine(repair.read_binary(args.xbe))
        normal={}
        for code in records_before:
            a,b=machine.cycle(records_before[code]),machine.cycle(records_after[code])
            require([s for s,_ in a['order']]==[s for s,_ in b['order']] and a['reverse']==b['reverse'] and a['clamp']==b['clamp'],'Team Select cycle changed')
            changed=[s for (s,x),(_s,y) in zip(a['order'],b['order']) if x!=y]
            wanted=[r['style'] for r in kits.recipes() if r['code']==code]
            require(changed==wanted,'unowned normal-play labels changed')
            normal[us.FRANCHISES[code]]=dict(before=a,after=b,labels_changed=changed)
        result['2_scope']=dict(passed=True,packs=scope,normal_team_select=normal,executable_unchanged=True,directory_unchanged=True)
        result['3_mud']=dict(passed=True,kits=10,chunks=30,rule='w1 wet_93',replay_noop=True)
        old_situ=kitx.w1._read_resource(before,ix,ix.entries[22]);new_situ=kitx.w1._read_resource(after,ix,ix.entries[22])
        result['phase_a']=phase_a(repair.read_binary(args.xbe),records_before)
    print('accept native moment paths',flush=True)
    result['4_native_moments']=native_moments(args.disc,repair.read_binary(args.xbe),old_situ,new_situ)
    replay={}
    with kitx.bump._Image.open(args.output,writable=False) as image:
        groups=repair.patches_for(image,manifest,args.manifest.parent)
        for name,patches in groups.items():
            ordinal=kitx.PACK_NAMES.index(name);raw=image.read_pack(ordinal,0,image.pack_size(ordinal))
            repair.validate_pack(raw,manifest['packs'][name])
            require(repair.uniform.apply_patches(raw,patches)[0]==raw,'second pass changes output')
            corrupt=bytes([raw[0]^1])+raw[1:]
            try:repair.validate_pack(corrupt,manifest['packs'][name])
            except ValueError:pass
            else:raise ValueError('foreign pack accepted')
            replay[name]=dict(second_pass_noop=True,unexpected_input_refused=True)
    result['5_repair']=dict(passed=True,packs=replay,order=manifest.get('order','kitx/u3r + a5 + sh1 then a5k'))
    contacts=[args.scratch/(r['id']+'_contact.png') for r in kits.recipes()]
    require(all(p.is_file() for p in contacts),'missing contact sheet')
    result['6_contacts']=dict(passed=True,files=[str(p) for p in contacts],runtime_witnessed=False)
    require(bool(args.tests)==bool(args.cli_checks),'supply both test and CLI receipts together')
    if args.tests:
        attach_validation(result,args.tests,args.cli_checks)
    result['passed']=True
    kits.write_json(args.acceptance,result)
    print(json.dumps(dict(passed=True,kits=10,mud_chunks=30,native_moments=51,changed_moments=6)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','output','manifest','resources','xbe','disc','scratch','acceptance'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--tests',type=Path)
    parser.add_argument('--cli-checks',type=Path)
    run(parser.parse_args())

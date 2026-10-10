#!/usr/bin/env python3
"""Decode every repaired package and compare catalog/Build imports to combined native output.
Run after kitx_repair. No image build or emulator is needed.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path[:0] = [str(Path(__file__).resolve().parent)]
import kitx_repair as k
from mod_editor.core.nfl2k5_uniform_catalog import Nfl2k5UniformCatalog
import nfl2k5_visual_mod_project as build


def compare_clean_packages(uniform, repaired):
    a_chunks = k.parse_chunks(uniform, allow_trailing=True)
    b_chunks = k.parse_chunks(repaired, allow_trailing=True)
    k.require(len(a_chunks) == len(b_chunks), 'kit chunk count changed')
    count = 0
    for a, b in zip(a_chunks, b_chunks):
        k.require((a.kind,a.offset,a.stored_size) == (b.kind,b.offset,b.stored_size), 'kit chunk layout changed')
        if a.kind not in ('TSET', 'TXTR'):
            continue
        before = uniform[a.offset:a.end_offset]
        after = repaired[b.offset:b.end_offset]
        old, chunk, textures = k.decoded_textures(before)
        clean = [t for t in textures if not t.name.endswith('_mud')]
        count += len(clean)
        if before == after:
            continue
        new, _, _ = k.decoded_textures(after)
        for texture in clean:
            k.require(k.texture_to_rgba(old, chunk, texture) == k.texture_to_rgba(new, chunk, texture),
                      f'clean texture changed in chunk {a.index}: {texture.name}')
    return count


def verify_packages(baseline, output, plan):
    checked, textures = [], 0
    with k.bump._Image.open(baseline, writable=False) as base, k.bump._Image.open(output, writable=False) as final:
        index, groups, _, _ = k.patches_for(base, plan)
        selectors = {k.bump.logical_name_for(e.name_id)[:-4] for e in index.entries
                     if k.uniforms.KIT.fullmatch(k.bump.logical_name_for(e.name_id) or '')}
        for number, selector in enumerate(sorted(selectors), 1):
            if number % 50 == 0:
                print(f'clean decode {number}/{len(selectors)}', flush=True)
            entry = k.w1._entry_for(index, k.bump, selector)
            original = k.w1._read_resource(base, index, entry)
            uniform = original
            for job, packs in groups:
                patches = [dict(p, offset=p['resource_offset']) for ps in packs.values() for p in ps
                           if p['resource'] == selector + '.IFF']
                if patches:
                    uniform, _ = (k.last.apply_patches if job == 'u3r' else k.uniforms.apply_patches)(uniform, patches)
            repaired = b''.join((final if k.PACK_NAMES[o] in k.PACKS else base).read_pack(o, at, n)
                                for o, at, n in index.sub_extents(entry, 0, entry.size))
            textures += compare_clean_packages(uniform, repaired)
            checked.append(selector)
        # JAX 5 kit and Team Select cards must remain the original slot.
        for selector in ('12H5', '12A5'):
            entry = k.w1._entry_for(index, k.bump, selector)
            k.require(k.w1._read_resource(base, index, entry) == k.w1._read_resource(final, index, entry), 'excluded JAX 5 changed')
        jax5 = next(Path(p) for j in plan['jobs'] if j['job'] == 'u3c' for p in j['manifests']
                    if json.loads(Path(p).read_text()).get('key') == 'JAX:5')
        for name, patches in json.loads(jax5.read_text())['resources'].items():
            if not name.startswith('outer:'):
                continue
            entry = index.entries[int(name.split(':')[1])]
            for patch in patches:
                for o, at, n in index.sub_extents(entry, patch['offset'], patch['length']):
                    k.require(base.read_pack(o, at, n) == final.read_pack(o, at, n), 'excluded JAX 5 card changed')
        entry = next(e for e in index.entries if e.name_id == k.uniforms.ROSTER_ID)
        before = k.w1._read_resource(base, index, entry)
        after = k.w1._read_resource(final, index, entry)
        from mod_editor.core import nfl2k5_historic_styles as hs
        record = next(at for at, code in hs.team_records(before)[:32] if code == '12')
        at = 32 + record + k.uniforms.us.TABLE + 4 * (5-1)
        k.require(before[at:at+4] == after[at:at+4], 'JAX 5 label changed')
        k.require(after[at+4:at+8] == __import__('struct').pack('<HH',2026,1), 'JAX 6 label incorrect')
    return dict(passed=True, packages=len(checked), textures=textures, selectors=checked,
                method='RGBA compare changed packages; exact chunk bytes for unchanged packages; decoded mip chains checked during derivation',
                jax5_kits_unchanged=True, jax5_cards_unchanged=True, jax5_label_unchanged=True, jax6_label='2026 Alternate 1')


def studio_samples(output, scratch, studio_index):
    """Use actual catalog provider edits and the same build_one_import used by Studio Build."""
    catalog = Nfl2k5UniformCatalog.from_report()
    evidence = Path('/home/noah/2k-worktrees/.b77-scratch')
    projects = [evidence/'u1/art_b10/project.json', evidence/'u2a/final/ARI/project.json',
                evidence/'u3c/art/jax6/edits.json']
    desired = {'16H0', '16A0', '00H0', '12H6'}
    edits = []
    for project in projects:
        doc = json.loads(project.read_text())
        for edit in doc['edits']:
            selector = f"{edit.get('asset_code')}{edit.get('side')}{edit.get('variant')}"
            if selector in desired and edit['kind'] in ('torso', 'pants', 'sleeve'):
                edits.append((selector, edit['kind'], Path(edit['clean_png'])))
    # A w1-only kit: feed the decoded clean art through the same Build path.
    with k.bump._Image.open(output, writable=False) as image:
        index = k.bump._parsed_index(image)
        selector = '23H10'
        entry = k.w1._entry_for(index, k.bump, selector)
        package = k.w1._read_resource(image, index, entry)
        for chunk in k.parse_chunks(package, allow_trailing=True):
            if chunk.index not in (1, 2, 3):
                continue
            span = package[chunk.offset:chunk.end_offset]
            decoded, local, textures = k.decoded_textures(span)
            texture = next(t for t in textures if not t.name.endswith('_mud'))
            from nfl_txtr import encode_rgba_png
            png = scratch / f'{selector}_{chunk.index}.png'
            k.uniforms._b765().atomic_write(png, encode_rgba_png(texture.width, texture.height,
                                                              k.texture_to_rgba(decoded, local, texture)))
            edits.append((selector, {1:'torso', 2:'pants', 3:'sleeve'}[chunk.index], png))
        results = []
        for order, (selector, kind, png) in enumerate(edits):
            assets = [a for a in catalog.assets_for_set(selector) if a.kind == kind]
            k.require(len(assets) == 1, f'catalog asset not unique: {selector}/{kind}')
            edit = assets[0].provider_edit(png)
            payload = k.read_binary(png)
            pin = build.InputPin(png.resolve(), payload, len(payload), k.sha(payload), (png.stat().st_dev, png.stat().st_ino))
            project = build.ProjectFile(scratch/'project.json', b'', {'edits':[edit]}, (0, 0))
            folder = Path(tempfile.mkdtemp(prefix=f'import_{order}_', dir=scratch))
            owned = build.ownership.track_existing(folder, True)
            temp_files = []
            try:
                span, _, report, _, target = build.build_one_import(order, edit, project, {png.resolve():pin},
                    {kind:build.REPORTS[kind]}, studio_index, build.DEFAULT_INVENTORY,
                    owned, temp_files, -1)
                entry = k.w1._entry_for(index, k.bump, selector)
                actual = b''.join(image.read_pack(o, at, n) for o, at, n in index.sub_extents(entry, target['chunk_offset'], len(span)))
                artifact = scratch / f'build_{selector}_{kind}_{k.sha(span)}.span'
                k.uniforms._b765().publish_batch([(artifact, span)])
                old, chunk, textures = k.decoded_textures(span)
                native, _, _ = k.decoded_textures(actual)
                pixels = {t.name: k.texture_to_rgba(old, chunk, t) == k.texture_to_rgba(native, chunk, t) for t in textures}
                results.append(dict(selector=selector, kind=kind, mud_mode=edit['mud_mode'],
                                    build_sha256=k.sha(span), native_sha256=k.sha(actual), identical=span == actual,
                                    decoded_pixels_identical=pixels, decoded_bytes_identical=old == native,
                                    encoded_stream_identical=span[k.HEADER.size:] == actual[k.HEADER.size:],
                                    build_wrapper=list(k.HEADER.unpack_from(span)[1:]),
                                    native_wrapper=list(k.HEADER.unpack_from(actual)[1:]), build_span=str(artifact)))
            except Exception as exc:
                results.append(dict(selector=selector, kind=kind, identical=False, error=str(exc)))
            finally:
                build.ownership.cleanup_owned(temp_files, [])
    return dict(passed=all(r['identical'] for r in results), samples=results,
                path='catalog.provider_edit -> Studio Build build_one_import', full_catalog_built=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'output', 'plan', 'acceptance', 'scratch'):
        p.add_argument('--'+name, required=True, type=Path)
    p.add_argument('--studio-index', type=Path, default=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
    p.add_argument('--studio-only', action='store_true', help='reuse the recorded exhaustive decode and rerun Studio samples')
    a = p.parse_args()
    doc = json.loads(a.acceptance.read_text())
    if not a.studio_only:
        doc['b'] = verify_packages(a.baseline, a.output, k.load_plan(a.plan))
    a.scratch.mkdir(parents=True, exist_ok=True)
    doc['e'] = studio_samples(a.output, a.scratch, a.studio_index)
    k.write_json(a.acceptance, doc)
    print(json.dumps({'b':{key:value for key,value in doc['b'].items() if key != 'selectors'}, 'e':doc['e']}, indent=2))


if __name__ == '__main__':
    main()

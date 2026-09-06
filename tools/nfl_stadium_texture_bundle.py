"""Compile Blender texture-only glTF into a private fixed SCNE span.

EXPERIMENTAL / UNWITNESSED. This developer CLI writes a new directory, never
modifies the supplied archive, and never builds/copies a disc. Its SCNE output
contains user-owned game data and must remain private. Mod Studio's Stadiums
page stages the same edits in a reversible project for the normal disc build.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT/'tools'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from mod_editor.core.nfl2k5_stadium_studio import stadium_gltf_texture_slots
from mod_editor.core.nfl2k5_stadium_texture_writer import build_unified_stadium_texture_imports


def _sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compile_bundle(gltf: Path, index: Path, inventory: Path, destination: Path) -> Path:
    source_hash = _sha_file(gltf)
    slots = stadium_gltf_texture_slots(gltf)
    images = {}
    for slot in slots:
        if slot.texture_id is None:
            raise ValueError('Export with the Blender Stadium helper to retain texture IDs.')
        if slot.texture_id in images and images[slot.texture_id] != slot.payload:
            raise ValueError('Linked materials disagree about one texture.')
        images[slot.texture_id] = slot.payload
    if not images or len({key.rsplit('.texture', 1)[0] for key in images}) != 1:
        raise ValueError('Choose a texture bundle from exactly one Stadium scene.')
    destination = destination.expanduser().absolute()
    if os.path.lexists(destination):
        raise ValueError('Choose a new output directory.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nfl2k5-texture-compile-', dir=destination.parent) as temporary:
        root = Path(temporary).resolve()
        edits = []
        for number, (identity, payload) in enumerate(sorted(images.items())):
            png = root/f'{number}.png'
            png.write_bytes(payload)
            edits.append((identity, png))
        results = build_unified_stadium_texture_imports(index, inventory, edits)
        if len(results) != 1:
            raise ValueError('The texture compiler returned more than one scene.')
        span, previews, report, _selector, target = results[0]
        report['private_output_contains_retail_bytes'] = True
        if _sha_file(gltf) != source_hash:
            raise ValueError('The Blender bundle changed during compilation.')
        report['blender_gltf_sha256'] = source_hash
        # Publish only after the complete scene passed decode, fit and ownership
        # checks. The exclusive directory belongs to this call until completion.
        destination.mkdir(mode=0o700)
        try:
            (destination/'scene.scne').write_bytes(span)
            for name, payload in previews:
                (destination/name).write_bytes(payload)
            # Remove paths to disposable staged PNGs from the durable receipt.
            for row in report.get('input_pngs', []):
                row.pop('path', None)
            (destination/'receipt.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination.resolve(strict=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gltf', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new private output directory')
    args = parser.parse_args(argv)
    print(compile_bundle(args.gltf, args.index, args.inventory, args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

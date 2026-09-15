"""Present measured equipment fits and exact stadium occurrences from receipts."""
import hashlib
import json
from pathlib import Path

from .errors import ValidationError


def fit_caption(row):
    dimensions = row.get('encoded_dimensions')
    colours = row.get('used_palette_entries')
    if (not isinstance(dimensions, (tuple, list)) or len(dimensions) != 2
            or any(type(v) is not int or not 0 < v <= 4096 for v in dimensions)
            or type(colours) is not int or not 0 < colours <= 256):
        raise ValidationError('The equipment fit receipt is missing measured dimensions or colours.')
    return f'fitted at {dimensions[0]} x {dimensions[1]}, {colours} colours'


def project_fit_labels(session):
    """Read only import/worker measurements; safe on the GUI thread."""
    from .equipment_staging import cached_equipment_fit_rows
    return {r['asset_id']: fit_caption(r) for r in cached_equipment_fit_rows(session)}


def verified_build_texture_lines(manifest):
    """Read hash-bound per-span reports after the normal build verifier passes.

    Use before publishing/cleaning its artifact folder. No texture compilation
    and no game-pixel reads. Old receipts without fit data remain explicit.
    """
    value = json.loads(Path(manifest).read_text(encoding='utf-8'))
    lines = []
    fits = {}
    for edit in value.get('edits', []):
        if edit.get('kind') not in ('uniform_equipment_texture', 'stadium_texture'):
            continue
        directory = Path(value['output']['artifact_directory'])
        reference = edit['import_report']
        name = reference['file_name']
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ValidationError('The texture receipt path is not a local artifact filename.')
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32*1024*1024:
            raise ValidationError('The texture receipt is missing or exceeds its size bound.')
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != reference['sha256']:
            raise ValidationError('The measured texture receipt changed after build verification.')
        report = json.loads(payload)
        if edit['kind'] == 'uniform_equipment_texture':
            for row in report['edits']:
                caption = (fit_caption(row) if 'used_palette_entries' in row else
                           'fit measurement unavailable in this older receipt')
                fits.setdefault((row['name'], caption), set()).add(row['set_selector'])
        else:
            # Each physical SCNE receipt names all selected embedded occurrences.
            for row in report.get('compiled_textures', []):
                target = row['target']
                package = target.get('stadium_package', {}).get('label', target['scene_id'])
                names = ', '.join(target.get('mapped_material_names', []))
                lines.append(f"Stadium {package}: wrote {target['selector']} ({names}). In-game appearance UNWITNESSED.")
    equipment = []
    for (name, caption), packages in fits.items():
        scope = (', '.join(sorted(packages)) if len(packages) <= 6 else
                 f'{len(packages)} uniform packages; individual rows in the receipt')
        equipment.append(f'Equipment {name} ({scope}): {caption}.')
    return tuple(equipment + lines)

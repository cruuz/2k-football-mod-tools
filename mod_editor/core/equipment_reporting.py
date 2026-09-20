"""Present measured equipment fits and exact stadium occurrences from receipts."""
import hashlib
import json
from pathlib import Path
import time

from .errors import ValidationError

#: Backoff, in seconds, between attempts to read a receipt the child build just
#: wrote. On Windows a real-time scanner or a sync client can hold a freshly
#: written file for a moment after the writing process exits; a file that is
#: genuinely absent stays absent through every attempt and is reported as such.
RECEIPT_READ_BACKOFF = (0.05, 0.1, 0.2, 0.4, 0.8)
RECEIPT_SIZE_BOUND = 32 * 1024 * 1024


def _read_receipt(path):
    """Return the receipt's bytes, retrying briefly, or refuse naming the path.

    Coach Edwards, 2026-09-20: "The texture receipt is missing or exceeds its
    size bound" with nothing to say which receipt or where. The message now
    names the file, and what the artifact folder actually holds, so a report
    is diagnosable from the dialog alone.
    """
    last = None
    for attempt, delay in enumerate((0.0,) + RECEIPT_READ_BACKOFF):
        if delay:
            time.sleep(delay)
        try:
            if path.is_symlink():
                last = 'is a symlink'
                break
            if not path.is_file():
                last = 'does not exist'
                continue
            size = path.stat().st_size
            if not 0 < size <= RECEIPT_SIZE_BOUND:
                last = f'is {size} bytes, outside 1..{RECEIPT_SIZE_BOUND}'
                if size > RECEIPT_SIZE_BOUND:
                    break
                continue
            return path.read_bytes()
        except OSError as exc:
            last = f'could not be read ({exc.__class__.__name__}: {exc})'
            continue
    try:
        siblings = sorted(p.name for p in path.parent.iterdir())[:20]
        present = ', '.join(siblings) if siblings else 'nothing'
    except OSError:
        present = 'the folder itself could not be listed'
    raise ValidationError(
        f'The texture receipt is missing or exceeds its size bound: {path} {last} after '
        f'{len(RECEIPT_READ_BACKOFF) + 1} attempts. The artifact folder holds: {present}.')


def fit_caption(row):
    if row.get('fit_status') == 'fit pending':
        return 'fit pending; checked when you build'
    if row.get('fit_status') == 'needs refit':
        return 'needs refit: ' + row['fit_error']
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
    from .nfl2k5_project_fit import art_fit_labels
    return {**art_fit_labels(session),
            **{r['asset_id']: fit_caption(r) for r in cached_equipment_fit_rows(session)}}


def refit_line(row):
    """One final-dialog line for an item Build refitted (beta 72.1)."""
    proof = ''
    if isinstance(row.get('budget'), int) and isinstance(row.get('required'), int):
        proof = (f" It needs {'at least ' if row.get('required_is_lower_bound') else ''}"
                 f"{row['required']:,} bytes and its span holds {row['budget']:,}.")
    return (f"Build refitted equipment {row['set_selector']} / {row['name']}: {row['fit_summary']}, "
            f"exactly as Refit equipment would.{proof} Your project still has your original art; "
            "use Refit equipment to keep this choice in the project.")


def verified_build_refit_lines(manifest):
    """Every equipment item Build refitted, from the hash-bound span reports."""
    return tuple(refit_line(row) for kind, report in _verified_reports(manifest)
                 if kind == 'uniform_equipment_texture' for row in report.get('auto_refit', []))


def _verified_reports(manifest):
    value = json.loads(Path(manifest).read_text(encoding='utf-8'))
    for edit in value.get('edits', []):
        if edit.get('kind') not in ('uniform_equipment_texture', 'stadium_texture'):
            continue
        directory = Path(value['output']['artifact_directory'])
        reference = edit['import_report']
        name = reference['file_name']
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ValidationError('The texture receipt path is not a local artifact filename.')
        path = directory / name
        payload = _read_receipt(path)
        if hashlib.sha256(payload).hexdigest() != reference['sha256']:
            raise ValidationError('The measured texture receipt changed after build verification.')
        yield edit['kind'], json.loads(payload)


def verified_build_texture_lines(manifest):
    """Read hash-bound per-span reports after the normal build verifier passes.

    Use before publishing/cleaning its artifact folder. No texture compilation
    and no game-pixel reads. Old receipts without fit data remain explicit.
    """
    lines = []
    refits = []
    fits = {}
    for kind, report in _verified_reports(manifest):
        if kind == 'uniform_equipment_texture':
            refitted = {row['asset_id'] for row in report.get('auto_refit', [])}
            refits.extend(refit_line(row) for row in report.get('auto_refit', []))
            for row in report['edits']:
                if row.get('asset_id') in refitted:
                    continue
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
    return tuple(refits + equipment + lines)

"""Re-seal the reviewed scorebug PNG catalog for the b76-s12 art, without relaxing a check.

Extends reports/b71_s6/refresh_art_pin.py (which sealed template.png alone) to every
PNG the scorebug passes author: the sprite template and every team mark (b76-s12
recoloured the Giants and Rams marks, b76-s14 the Jets, Cowboys, Colts, Saints and Jaguars marks;
a mark no pass touched re-seals to its unchanged row). For each
path it records the bytes on disk now (size, sha256, PNG width and height) in
packaging/nfl2k5_scorebug_template_pngs.json, keeps every other row untouched
(another job may add rows to the same catalog), rewrites the catalog in its
existing form (indent 2, sorted keys, LF) and puts the catalog's new sha256 into
SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 in packaging/check_2k5_mod_studio_release.py.

It is idempotent and safe to re-run on a merged tree: run it after the art lands,
then run ``python3 packaging/repin.py --apply``. A path must already be a
reviewed row (a new PNG needs a human review, not this script) and must be a PNG
of the dimensions its row already records.

Usage:  python3 reports/b76_s12/refresh_art_pin.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'packaging/nfl2k5_scorebug_template_pngs.json'
CHECKER = ROOT / 'packaging/check_2k5_mod_studio_release.py'
PATHS = ('data/nfl2k5_scorebug_sprite/template.png',) + tuple(
    'data/nfl2k5_scorebug_mnf/logos/' + p.name for p in sorted((ROOT / 'data/nfl2k5_scorebug_mnf/logos').glob('*.png')))
CONSTANT = re.compile(r'(?m)^SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "([0-9a-f]{64})"$')


def row_for(path: Path) -> dict:
    data = path.read_bytes()
    if data[:16] != b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR':
        raise SystemExit('Not a PNG with a leading IHDR: ' + str(path))
    width, height = struct.unpack_from('>II', data, 16)
    return dict(height=height, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=width)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--check', action='store_true', help='Report whether the seal is current; write nothing')
    p.add_argument('--receipt', type=Path, default=Path(__file__).resolve().parent / 'art-pin.json')
    a = p.parse_args(argv)
    raw = CATALOG.read_text(encoding='utf-8')
    document = json.loads(raw)
    if document.get('schema') != 'nfl2k5_scorebug_template_pngs/v1':
        raise SystemExit('Unexpected catalog schema')
    rows = []
    for key in PATHS:
        if key not in document['files']:
            raise SystemExit('Not a reviewed catalog row (needs human review): ' + key)
        before = document['files'][key]
        after = row_for(ROOT / key)
        if (after['width'], after['height']) != (before['width'], before['height']):
            raise SystemExit('PNG dimensions changed for ' + key + '; the texture contract is fixed')
        document['files'][key] = after
        rows.append(dict(path=key, before=before, after=after, changed=before != after))
    text = json.dumps(document, indent=2, sort_keys=True) + '\n'
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    checker = CHECKER.read_text(encoding='utf-8')
    found = CONSTANT.findall(checker)
    if len(found) != 1:
        raise SystemExit('Expected exactly one SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 line in the release checker')
    current = text == raw and found[0] == sha
    receipt = dict(catalog=str(CATALOG.relative_to(ROOT)), checker=str(CHECKER.relative_to(ROOT)),
                   rows=rows, catalog_sha256_before=found[0], catalog_sha256=sha,
                   other_rows_untouched=len(document['files']) - len(PATHS), sealed=current)
    if a.check:
        print(json.dumps(receipt, indent=2))
        return 0 if current else 1
    if text != raw:
        CATALOG.write_text(text, encoding='utf-8', newline='\n')
    if found[0] != sha:
        CHECKER.write_text(CONSTANT.sub('SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "%s"' % sha, checker),
                           encoding='utf-8', newline='\n')
    receipt['sealed'] = True
    a.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

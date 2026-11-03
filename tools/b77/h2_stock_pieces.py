#!/usr/bin/env python3
"""b791-h2-kits: derive the SOFTDRINK stock-piece hashes the drawing art steps look up.

The Anniversary and classic kits draw flat colour on donor pieces (K1 clears two 2026 maker marks, the Seamen kit paints
panels, stripes and logos, the Titans and Browns kits paint numerals). Those steps were authored on the stock piece, the retail
one or the shipped SOFTDRINK one. ``nfl2k5_moment_kits`` runs them, on donors that are not the shipped set, only on a chunk that
is that stock piece; on a user's own art they are skipped. The retail pieces are read from the retail disc at build time. The
SOFTDRINK pieces are these hashes, kept in ``data/nfl2k5_moment_kits_pins.json`` under ``stock_chunks``:

* the Anniversary kits' donors: the b775 fixture disc's packages passed through the b777-sw1 and b779-vk2 passes exactly as
  ``tests/mod_editor/test_b775_ek1_moment_kits.py`` does, so every donor package equals its pin (checked here);
* the classic Seamen kit's donors (14H0, 14A0): the SOFTDRINK v0.8 disc's packages; the shipped v0.8 kit packages 14h14.iff and
  14a14.iff must recompose from them byte for byte (checked here), which proves they are what the stage read.

    python3 tools/b77/h2_stock_pieces.py --fixture FIXTURE.iso --v08 V08.iso [--write]

Without ``--write`` it only prints whether the table in the pins file is what the discs give. Both discs are read only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

ABOUT = (
    'b791-h2-kits: sha256 of the chunk spans of the shipped SOFTDRINK pieces that the drawing art steps ('
    'poly, multipoly, flood, texels, ring, grow, copy ...) of the Anniversary and classic kits are made f'
    'or. A donor that is not the shipped set runs those steps only on a chunk listed here or equal to the'
    " retail chunk; on any other chunk (the user's own art) they are skipped. Anniversary kit donors: the"
    ' pieces as the stage reads them (the b775 fixture disc after the sw1 and vk2 passes, every donor pac'
    'kage equal to its pin above; the same chunks are in the SOFTDRINK v0.8 disc); classic kit donors (14'
    'H0, 14A0): the v0.8 disc, whose shipped 14h14.iff and 14a14.iff recompose from them byte for byte. D'
    'erived by tools/b77/h2_stock_pieces.py.')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_table(fixture: Path, v08: Path) -> dict:
    """{selector: {chunk index (text): sha256 of the chunk span}} from the two discs, every check passed or ValueError."""
    from nfl_txtr import parse_chunks
    from mod_editor.core import nfl2k5_classic_teams as ct
    from mod_editor.core import nfl2k5_historic_styles as hs
    from mod_editor.core import nfl2k5_moment_kits as mk
    from tests.mod_editor.test_b775_ek1_moment_kits import _after_sw1, _after_vk2
    moment, classic = mk.document(), ct.authored_kits()
    pins = json.loads(mk.PINS.read_text(encoding="utf-8"))
    table: dict = {}
    with hs.Source(fixture) as source:
        packages = {s: source.get(mk.selector_name(s)) for s in mk.donors(moment)}
        packages = _after_vk2(_after_sw1(source, packages))
    wrong = sorted(s for s, data in packages.items() if _sha(data) != pins["donors"][s])
    if wrong:
        raise ValueError(f"the fixture disc's donors after sw1 and vk2 differ from the pins: {wrong}")
    for selector, chunks in mk.stock_needs(moment).items():
        parsed = parse_chunks(packages[selector])
        table[selector] = {str(i): _sha(packages[selector][parsed[i].offset:parsed[i].end_offset]) for i in chunks}
    with hs.Source(v08) as source:
        donors = {s: source.get(mk.selector_name(s)) for s in mk.donors(classic)}
        shipped = {name: source.get(name) for name in ("14h14.iff", "14a14.iff")}
    made = mk.compose(classic, donors)          # strict: every step runs, as in the official build
    if any(made[name] != shipped[name] for name in shipped):
        raise ValueError("the v0.8 disc's donors do not recompose its shipped classic kit packages")
    for selector, chunks in mk.stock_needs(classic).items():
        parsed = parse_chunks(donors[selector])
        table[selector] = {str(i): _sha(donors[selector][parsed[i].offset:parsed[i].end_offset]) for i in chunks}
    return {selector: table[selector] for selector in sorted(table)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fixture", type=Path, required=True, help="the b775 fixture disc (SOFTDRINK v0.6.1 i4 test)")
    parser.add_argument("--v08", type=Path, required=True, help="the SOFTDRINK v0.8 disc")
    parser.add_argument("--write", action="store_true", help="write the table into data/nfl2k5_moment_kits_pins.json")
    args = parser.parse_args(argv)
    from mod_editor.core import nfl2k5_moment_kits as mk
    table = derive_table(args.fixture, args.v08)
    pins = json.loads(mk.PINS.read_text(encoding="utf-8"))
    same = pins.get("stock_chunks") == table
    print(f"{sum(len(v) for v in table.values())} hashes in {len(table)} donors; the pins file "
          f"{'already has exactly this table' if same else 'differs'}")
    if args.write and not same:
        pins["stock_chunks"] = table
        pins["stock_chunks_about"] = ABOUT
        mk.PINS.write_text(json.dumps(pins, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print("wrote", mk.PINS)
    return 0 if same or args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())

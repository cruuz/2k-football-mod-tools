#!/usr/bin/env bash
# Deterministic validator for the PS2 disc inventory.
#
# Runs the ISO9660 reader's and the inventory's self-tests, which between them
# prove: a synthetic ISO9660 volume in both sector layouts reads back exactly;
# SYSTEM.CNF resolves to the catalogue serial form (SLUS_209.19 -> SLUS-20919);
# and a synthetic /VC_20919 pack inventories to the expected names, formats and
# dimensions without ever reading a payload byte. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile tools/ps2_iso9660.py tools/nfl2k5_ps2_disc_inventory.py
python3 tools/ps2_iso9660.py --selftest
python3 tools/nfl2k5_ps2_disc_inventory.py --selftest

echo "NFL2K5_PS2_DISC_INVENTORY_VALIDATION_PASS"

@echo off
setlocal enableextensions
rem Windows validator for the PS2 disc inventory.
rem
rem Mirrors tools/validate_nfl2k5_ps2_disc_inventory.sh: compiles the ISO9660
rem reader and the inventory module and runs both self-tests, which between
rem them prove a synthetic ISO9660 volume in both sector layouts reads back
rem exactly, that SYSTEM.CNF resolves to the catalogue serial form
rem (SLUS_209.19 becomes SLUS-20919), and that a synthetic /VC_20919 pack
rem inventories to the expected names, formats and dimensions without ever
rem reading a payload byte. No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 disc inventory validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\ps2_iso9660.py tools\nfl2k5_ps2_disc_inventory.py || exit /b 1
%PY_CMD% tools\ps2_iso9660.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_disc_inventory.py --selftest || exit /b 1

echo NFL2K5_PS2_DISC_INVENTORY_VALIDATION_PASS
exit /b 0

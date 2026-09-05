@echo off
setlocal enableextensions
rem Windows validator for the Madden 09 (PS2) container inventory lane.
rem
rem Mirrors tools/validate_madden09_ps2_inventory.sh.
rem Runs the shared TERF reader's self-test and the lane's own unit tests, which
rem between them prove: a synthetic TERF container round-trips through the reader
rem and the writer at every alignment; a synthetic SLUS-21770 ISO carrying a DATA
rem container and a COMP-with-stored container walks to the expected member counts,
rem codecs and formats; the lane refuses to plan, build or verify; and no catalogue
rem row carries a payload byte. No game data is required.

rem Run from the repository root, one level up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Madden 09 (PS2) validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile mod_editor\games\madden09_ps2\inventory_lane.py mod_editor\games\madden09_ps2\containers.py || exit /b 1
%PY_CMD% tools\ea_terf_inspect.py --selftest || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_madden09_ps2_inventory || exit /b 1

echo MADDEN09_PS2_INVENTORY_VALIDATION_PASS
exit /b 0

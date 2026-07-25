@echo off
setlocal enableextensions
rem Windows validator for the PS2 save writer.
rem
rem Mirrors tools/validate_nfl2k5_ps2_save.sh: compiles both PS2 save modules
rem and runs the writer's and verifier's self-tests, which between them prove
rem a sealed fixed-allocation edit round-trips through .psu unchanged, that a
rem save whose checksum was not resealed is rejected, and that an edit outside
rem the declared byte range is rejected. No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 save validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_save.py tools\nfl2k5_ps2_save_verify.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_save.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_save_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_SAVE_VALIDATION_PASS
exit /b 0

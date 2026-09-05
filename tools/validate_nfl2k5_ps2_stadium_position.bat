@echo off
setlocal enableextensions
rem Windows validator for bounded PS2 stadium position editing.
rem
rem Mirrors tools/validate_nfl2k5_ps2_stadium_position.sh: compiles the target
rem catalogue, the writer and the independent verifier, runs all three
rem self-tests and the synthetic suite. Between them they prove, with no game
rem data anywhere, that a synthetic SLUS-20919-shaped ISO carrying a VC-LZ
rem compressed SCNE can have one catalogued V4_32 position lane rewritten and
rem recompressed into the chunk's fixed stored body with a byte-identical 0x20
rem wrapper; that the independent verifier passes that image and fails a byte
rem changed outside the declared lanes, a byte changed outside the chunk span
rem and a moved +0x14 scratch word; and that the writer refuses a changed
rem vertex count, an inexact binary32 coordinate, an unauthorised target, a
rem mismatched catalogue pin, edits spanning two scenes and a recompression
rem that does not fit, leaving no output image behind.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 stadium position validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_stadium_target_catalog.py tools\nfl2k5_ps2_stadium_position_patch.py tools\nfl2k5_ps2_stadium_position_verify.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_stadium_target_catalog.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_stadium_position_verify.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_stadium_position_patch.py --selftest || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_nfl2k5_ps2_stadium_position -v || exit /b 1

echo NFL2K5_PS2_STADIUM_POSITION_VALIDATION_PASS
exit /b 0

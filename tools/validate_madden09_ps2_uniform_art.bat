@echo off
setlocal enableextensions
rem Windows validator for the Madden 09 (PS2) uniform-art lane.
rem
rem Mirrors tools/validate_madden09_ps2_uniform_art.sh.
rem Runs the uniform-art lane's unit tests, which prove on synthetic MMAP members
rem that: the header parses to the dimensions it declares; a decode round-trips to
rem a PNG of exactly those dimensions; an import of the wrong size is refused with
rem the size the lane wanted; the export writes the files its receipt declares and
rem an independent verify re-derives every digest and fails on a tampered file; and
rem the PCSX2 replacement identity is refused by name. No game data is required.

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

%PY_CMD% -m py_compile mod_editor\games\madden09_ps2\uniform_art.py mod_editor\games\madden09_ps2\mmap_art.py || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_madden09_ps2_uniform_art || exit /b 1

echo MADDEN09_PS2_UNIFORM_ART_VALIDATION_PASS
exit /b 0

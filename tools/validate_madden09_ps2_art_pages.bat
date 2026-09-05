@echo off
setlocal enableextensions
rem Windows validator for Madden NFL 09 PS2, the four MMAP art-page writer lanes.
rem Mirrors tools/validate_madden09_ps2_art_pages.sh: compiles the lane modules and runs the
rem game-module conformance harness for madden09_ps2 on a synthetic disc. No game data.
rem Note: no parentheses inside echo lines within if blocks; cmd.exe reads them as block ends.

rem Run from the repository root, one level up from this script.
cd /d "%~dp0.."
if not defined QT_QPA_PLATFORM set "QT_QPA_PLATFORM=offscreen"

rem Prefer the Python launcher; fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Madden 09 PS2 art-page validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile mod_editor\games\madden09_ps2\art_pages.py mod_editor\games\madden09_ps2\uniform_art.py tools\ps2_iso9660_writer.py tools\ps2_iso9660_verify.py || exit /b 1
set "PYTHONPATH=%CD%"
%PY_CMD% tools\ps2_iso9660_writer.py --selftest || exit /b 1
%PY_CMD% tools\ps2_iso9660_verify.py --selftest || exit /b 1
%PY_CMD% -m mod_editor.games conformance --game madden09_ps2 || exit /b 1

echo MADDEN09_PS2_ART_PAGES_VALIDATION_PASS
exit /b 0

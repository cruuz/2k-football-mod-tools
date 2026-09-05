@echo off
setlocal enableextensions
rem Windows validator for the Madden 09 (PS2) text lane.
rem
rem Mirrors tools/validate_madden09_ps2_text.sh.
rem Runs the text lane's unit tests, which prove on a synthetic disc that: a TEXT
rem member splits to the strings it holds; the catalogue carries counts, lengths and
rem digests and no string at all; a preview reads the strings from the source it is
rem given and elides an over-long one; and the lane refuses to plan, build or
rem verify. No game data is required.

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

%PY_CMD% -m py_compile mod_editor\games\madden09_ps2\text_lane.py || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_madden09_ps2_text || exit /b 1

echo MADDEN09_PS2_TEXT_VALIDATION_PASS
exit /b 0

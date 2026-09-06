@echo off
setlocal enableextensions
rem Windows validator for NCAA Football 09 PS2, the TEXT string-bank lane.
rem Mirrors tools/validate_ncaa09_ps2_text.sh: both hand the work to
rem tools/validate_game_lane.py, which reads mod_editor/games/ncaa09_ps2/validators.json
rem for the steps this lane needs and derives the pass token from the lane name.
rem No game data, and no test framework: this has to run in a shipped tree.
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
    echo NCAA 09 PS2 validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

set "PYTHONPATH=%CD%"
%PY_CMD% tools\validate_game_lane.py --game ncaa09_ps2 --lane text || exit /b 1

exit /b 0

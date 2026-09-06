@echo off
setlocal enableextensions
rem Windows validator for NCAA Football 09 PS2, the kit and face MMAP texture census lane.
rem Mirrors tools/validate_ncaa09_ps2_textures.sh: compiles the lane module, runs the
rem game-module conformance harness for ncaa09_ps2 on a synthetic disc, and runs the
rem lane's own self-test. No game data.
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

%PY_CMD% -m py_compile mod_editor\games\ncaa09_ps2\texture_lane.py || exit /b 1
set "PYTHONPATH=%CD%"
%PY_CMD% -m mod_editor.games conformance --game ncaa09_ps2 || exit /b 1
%PY_CMD% -m mod_editor.games.ncaa09_ps2.texture_lane --selftest || exit /b 1
echo NCAA09_PS2_TEXTURES_VALIDATION_PASS
exit /b 0

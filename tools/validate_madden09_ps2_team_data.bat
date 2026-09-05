@echo off
setlocal enableextensions
rem Windows validator for the Madden 09 (PS2) team-database lane.
rem
rem Mirrors tools/validate_madden09_ps2_team_data.sh.
rem Runs the EA TDB reader's unit tests and the lane's own, which between them
rem prove: a synthetic TDB round-trips every field type through the bit-packer,
rem including fields that straddle byte boundaries and negative signed values; the
rem 4-byte franchise preamble is detected; a truncated or implausible database is
rem refused with a sentence; the lane catalogues tables, record counts and field
rem names and never a record's contents; and it refuses to plan, build or verify.
rem No game data is required.

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

%PY_CMD% -m py_compile mod_editor\games\_formats\ea_tdb.py mod_editor\games\madden09_ps2\team_data.py || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_ea_tdb tests.mod_editor.test_madden09_ps2_team_data || exit /b 1

echo MADDEN09_PS2_TEAM_DATA_VALIDATION_PASS
exit /b 0

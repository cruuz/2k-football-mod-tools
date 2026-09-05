@echo off
setlocal enableextensions
rem Windows validator for the PS2 playbook patcher and its verifier.
rem
rem Mirrors tools/validate_nfl2k5_ps2_playbook.sh: compiles the three tools and
rem runs the synthetic suite, which proves without any game data that a PLAY
rem body built field by field parses with the shipped codec and every play
rem passes the ported retail validator, that a formation and a play can be
rem added and the independent verifier passes, that a byte flipped outside the
rem declared playbook span fails verification, that a book already at the
rem 270-play capacity is refused, and that a compile returning the wrong body
rem length is refused before the output image is created. No disc, no network.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 playbook validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_playbook_patch.py tools\nfl2k5_ps2_playbook_verify.py tools\nfl2k5_ps2_playbook_target_catalog.py || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_nfl2k5_ps2_playbook -v || exit /b 1

echo NFL2K5_PS2_PLAYBOOK_VALIDATION_PASS
exit /b 0

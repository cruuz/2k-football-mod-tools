@echo off
setlocal enableextensions
rem Windows validator for the Madden 09 (PS2) executable-patch lane.
rem
rem Mirrors tools/validate_madden09_ps2_code_patches.sh.
rem Runs the lane's self-test and its unit tests, which prove on a synthetic ELF
rem that: every proposed patch refuses translation by name; hand-authored words
rem plan against the user's own ELF and refuse when the original does not match;
rem the pnach names the ELF's own PCSX2 CRC; verify passes the file the receipt
rem recorded and fails a tampered one; and a build never overwrites. No game data
rem is required.

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

%PY_CMD% -m py_compile mod_editor\games\madden09_ps2\code_patches.py || exit /b 1
%PY_CMD% -m mod_editor.games.madden09_ps2.code_patches --selftest || exit /b 1
%PY_CMD% -m unittest tests.mod_editor.test_madden09_ps2_code_patches || exit /b 1

echo MADDEN09_PS2_CODE_PATCHES_VALIDATION_PASS
exit /b 0

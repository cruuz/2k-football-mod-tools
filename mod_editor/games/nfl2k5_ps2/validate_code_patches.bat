@echo off
setlocal enableextensions
rem Windows validator for the PS2 executable-patch lane (interface only).
rem Mirrors validate_code_patches.sh: runs the lane self-test. No game data is required.

rem Run from the repository root, three levels up from this script.
cd /d "%~dp0..\..\.."

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo Python 3 was not found on PATH.
    exit /b 1
)

%PY_CMD% -m py_compile mod_editor\games\nfl2k5_ps2\code_patches.py || exit /b 1
%PY_CMD% -c "from mod_editor.games.nfl2k5_ps2 import code_patches; raise SystemExit(code_patches.selftest())" || exit /b 1

echo NFL2K5_PS2_CODE_PATCHES_VALIDATION_PASS
exit /b 0

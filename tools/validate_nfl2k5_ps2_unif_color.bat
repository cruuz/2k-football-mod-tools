@echo off
setlocal enableextensions
rem Windows validator for the PS2 uniform-colour on-disc writer.
rem
rem Mirrors tools/validate_nfl2k5_ps2_unif_color.sh: compiles the three modules
rem and runs the target catalogue's, the writer's and the independent verifier's
rem self-tests, which between them prove that a same-size eight-byte colour poke
rem lands in a new image of the source's exact byte length, that an out-of-range
rem selector, an over-length colour literal, a compressed body, a mismatched
rem catalogue and a no-op edit are each refused without creating a destination,
rem and that a byte changed outside the declared spans fails verification.
rem No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 uniform-colour validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_unif_color_target_catalog.py tools\nfl2k5_ps2_unif_color_patch.py tools\nfl2k5_ps2_unif_color_verify.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_unif_color_target_catalog.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_unif_color_patch.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_unif_color_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_UNIF_COLOR_VALIDATION_PASS
exit /b 0

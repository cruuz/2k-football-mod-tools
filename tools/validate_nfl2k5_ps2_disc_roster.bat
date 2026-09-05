@echo off
setlocal enableextensions
rem Windows validator for the PS2 disc-roster on-disc writer.
rem
rem Mirrors tools/validate_nfl2k5_ps2_disc_roster.sh: compiles the three modules
rem and runs the target catalogue's, the writer's and the independent verifier's
rem self-tests, which between them prove that a masked jersey / face-shield word
rem and a same-allocation name land in a new image of the source's exact byte
rem length, that an out-of-range player index, an over-length name, a
rem zero-capacity placeholder slot, a compressed ROST body, a mismatched
rem catalogue, the reserved face-shield value and a no-op edit are each refused
rem without creating a destination, and that a byte changed outside the declared
rem ranges or a moved table pointer fails verification. No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 disc-roster validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_disc_roster_target_catalog.py tools\nfl2k5_ps2_disc_roster_patch.py tools\nfl2k5_ps2_disc_roster_verify.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_disc_roster_target_catalog.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_disc_roster_patch.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_disc_roster_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_DISC_ROSTER_VALIDATION_PASS
exit /b 0

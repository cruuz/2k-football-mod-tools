@echo off
setlocal enableextensions
rem Windows validator for the PS2 replacement-pack export.
rem
rem Mirrors tools/validate_nfl2k5_ps2_replacement_pack.sh: compiles the export
rem service, the pack verifier and the pack audit tool, then runs the
rem verifier's self-test, which builds a synthetic pack, its mapping manifest
rem and its project from scratch and proves a correct pack verifies, that the
rem audit tool independently reports xbox_mapping_ready on the same folder,
rem and that a single changed output byte, an extra file, a receipt entry
rem naming an unedited target, a filename the manifest does not map, a
rem missing file, a forged provenance block, a stray directory and an
rem uncanonical filename are each rejected. It also proves a run without the
rem project is downgraded rather than passed, because the check that no
rem exported file names an unedited target cannot run without it. No game
rem data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 replacement pack validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile mod_editor\core\ps2_export_service.py tools\nfl2k5_ps2_replacement_pack_verify.py tools\nfl2k5_ps2_replacement_pack_audit.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_replacement_pack_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_REPLACEMENT_PACK_VALIDATION_PASS
exit /b 0

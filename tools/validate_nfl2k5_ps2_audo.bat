@echo off
setlocal enableextensions
rem Windows validator for the PS2 exact-slot AUDO audio lane.
rem
rem Mirrors tools/validate_nfl2k5_ps2_audo.sh: compiles the codec, the target
rem catalogue, the patcher and the verifier, then runs all four self-tests.
rem Between them they prove SPU-ADPCM round-trips byte-exactly and every
rem emitted block obeys the shift / filter / flag rules; that a synthetic
rem /VC_20919 disc catalogues to the expected AUDO slots; that a generated tone
rem patches into a slot without touching container metadata while over-length
rem audio, a channel mismatch and a malformed WAV are refused; and that the
rem independent verifier passes a clean patch and fails a flipped byte inside
rem or outside the slot. No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 AUDO audio validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\spu_adpcm.py tools\nfl2k5_ps2_audo_target_catalog.py tools\nfl2k5_ps2_audo_patch.py tools\nfl2k5_ps2_audo_verify.py || exit /b 1
%PY_CMD% tools\spu_adpcm.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_audo_target_catalog.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_audo_patch.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_audo_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_AUDO_VALIDATION_PASS
exit /b 0

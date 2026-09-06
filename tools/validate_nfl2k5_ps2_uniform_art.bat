@echo off
setlocal enableextensions
rem Windows validator for the PS2 uniform-art lane.
rem
rem Mirrors tools/validate_nfl2k5_ps2_uniform_art.sh: compiles the four modules
rem and runs the texture map's, the lane's and the independent replacement-pack
rem verifier's self-tests. Between them they prove that a synthetic PS2 image's
rem PSMT8 and PSMT4 uniform textures are catalogued and decoded to RGBA PNGs,
rem that a replacement is accepted at the texture's own size and at 2x and
rem refused for a 3:2 stretch or a file that is not a PNG, that a pack is
rem written and verified, that a flipped byte in it fails verification, and
rem that an existing destination is refused. No game data is required.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 uniform-art validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_texture_map.py tools\nfl2k5_ps2_uniform_art.py tools\nfl2k5_ps2_replacement_pack_verify.py mod_editor\games\nfl2k5_ps2\uniform_art.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_texture_map.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_uniform_art.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_replacement_pack_verify.py --selftest || exit /b 1

echo NFL2K5_PS2_UNIFORM_ART_VALIDATION_PASS
exit /b 0

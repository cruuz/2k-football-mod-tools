@echo off
setlocal enableextensions
rem Windows validator for bounded PS2 on-disc text editing.
rem
rem Mirrors tools/validate_nfl2k5_ps2_text.sh: compiles the catalog, the
rem patcher and the verifier, runs all three self-tests and then the full
rem conformance suite. With no game data at all these prove that a synthetic
rem UTF-16LE STRG bank parses and rebuilds byte-identically; that the writer
rem refuses an over-length replacement, an empty one, a dropped or added
rem inline token, a read-only allocation, an unknown bank or index, two edits
rem on one allocation, a stale expected digest, an LZ-compressed bank and an
rem edit that changes nothing, leaving no destination behind; that a
rem same-length and a shorter zero-filled edit both write and verify; and that
rem the verifier FAILS on a stray byte anywhere in the image, on a same-length
rem overwrite of an unnamed string, on a moved pointer, on a resized image and
rem on a disagreeing patch report.

rem Run from the repository root, two levels up from this script.
cd /d "%~dp0.."

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo PS2 text validation could not run.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run this again.
    echo.
    exit /b 1
)

%PY_CMD% -m py_compile tools\nfl2k5_ps2_text_target_catalog.py tools\nfl2k5_ps2_text_patch.py tools\nfl2k5_ps2_text_verify.py || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_text_target_catalog.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_text_patch.py --selftest || exit /b 1
%PY_CMD% tools\nfl2k5_ps2_text_verify.py --selftest || exit /b 1
%PY_CMD% -m unittest -v tests.mod_editor.test_nfl2k5_ps2_text || exit /b 1

echo NFL2K5_PS2_TEXT_VALIDATION_PASS
exit /b 0

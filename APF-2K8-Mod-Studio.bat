@echo off
setlocal enableextensions
rem APF 2K8 Mod Studio - Windows launcher.
rem
rem Mirrors tools/launch_apf2k8_mod_studio.sh: it runs from this script's own
rem folder (the application root, which may contain spaces), checks that
rem Python 3, PyQt5, and Pillow are importable, shows a friendly message and
rem pauses if not, and otherwise starts "python -m mod_editor.apf_studio".

set "STUDIO_NAME=APF 2K8 Mod Studio"

rem Run from the folder this script lives in. %~dp0 keeps its quotes-safe
rem trailing backslash, so paths containing spaces still work.
cd /d "%~dp0"

rem Prefer the Python launcher (py -3); fall back to python on PATH.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo %STUDIO_NAME% could not start.
    echo.
    echo Python 3 was not found. Install Python 3 from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then run:
    echo     pip install PyQt5 Pillow
    echo.
    pause
    exit /b 1
)

set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH=%~dp0"

%PY_CMD% -c "from PyQt5 import QtWidgets; import PIL; import mod_editor.apf_studio.gui" >nul 2>nul
if errorlevel 1 (
    echo %STUDIO_NAME% could not start.
    echo.
    echo A required component ^(PyQt5 or Pillow^) is missing. Install both with:
    echo     pip install PyQt5 Pillow
    echo.
    pause
    exit /b 1
)

%PY_CMD% -m mod_editor.apf_studio %*
if errorlevel 1 (
    echo.
    echo %STUDIO_NAME% exited with an error.
    pause
    exit /b 1
)

exit /b 0

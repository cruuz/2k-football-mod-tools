@echo off
setlocal enableextensions
rem 2K5 Mod Studio - Windows launcher.
rem
rem Runs from this script's own folder. When the archive includes a private
rem runtime beside the application (the installed layout), that runtime is used
rem directly. Otherwise this finds Python 3.11 or 3.12 and lets
rem packaging\windows\studio_bootstrap.py build a private .venv on first run.
rem Nothing here writes outside the Studio folder and nothing needs
rem administrator rights. Pass --setup to install or repair the private
rem runtime and exit without opening the Studio.

set "STUDIO_NAME=2K5 Mod Studio"
set "IMPORT_CHECK=from PyQt5 import QtWidgets; import PIL; import numpy; import capstone; import unicorn; import mod_editor"

rem Run from the folder this script lives in. %~dp0 keeps its quotes-safe
rem trailing backslash, so paths containing spaces still work. A ZIP that was
rem extracted into a second folder of the same name is just a longer path.
cd /d "%~dp0"

rem Installed layout: <install>\app\2K5-Mod-Studio.bat beside <install>\runtime.
set "BUNDLED_PYTHON=%~dp0..\runtime\python.exe"
if exist "%BUNDLED_PYTHON%" (
    "%BUNDLED_PYTHON%" -c "%IMPORT_CHECK%" >nul 2>nul
    if not errorlevel 1 (
        "%BUNDLED_PYTHON%" -m mod_editor --studio %*
        if errorlevel 1 (
            echo.
            echo %STUDIO_NAME% exited with an error.
            pause
            exit /b 1
        )
        exit /b 0
    )
    set "BUNDLED_RUNTIME_BROKEN=1"
)

rem Prefer a Python that matches the pinned packages, then any Python 3. The
rem bootstrap prints a clear next step for another version.
if defined MOD_STUDIO_PYTHON (
    set "PY_EXE=%MOD_STUDIO_PYTHON%"
    set "PY_ARG="
    goto have_python
)

set "PY_EXE="
set "PY_ARG="
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARG=-3.12"
    goto have_python
)
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARG=-3.11"
    goto have_python
)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_EXE=py"
    goto have_python
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_EXE=python"
    goto have_python
)
goto no_python

:have_python
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH=%~dp0"

set "BOOTSTRAP_ARGS="
if defined PY_ARG set "BOOTSTRAP_ARGS=--python-arg %PY_ARG%"

"%PY_EXE%" %PY_ARG% -I -B "%~dp0packaging\windows\studio_bootstrap.py" ^
    --app-root "%~dp0." ^
    --python "%PY_EXE%" %BOOTSTRAP_ARGS% ^
    --requirements "%~dp0packaging\requirements-studio.txt" ^
    --module mod_editor ^
    --imports "%IMPORT_CHECK%" ^
    --name "%STUDIO_NAME%" ^
    -- %*
if errorlevel 1 (
    echo.
    echo %STUDIO_NAME% could not start. Read the message above.
    pause
    exit /b 1
)
exit /b 0

:no_python
echo %STUDIO_NAME% could not start.
echo.
if defined BUNDLED_RUNTIME_BROKEN (
    echo The private runtime included with this install is incomplete.
    echo Download the latest 2K5-Mod-Studio Setup.exe from the release page and
    echo run it. You do not need Python for Setup.exe.
) else (
    echo Python 3 was not found on this computer.
    echo Install 64-bit Python 3.12 from:
    echo     https://www.python.org/downloads/windows/
    echo During setup tick "Add python.exe to PATH", then run this file again.
    echo No administrator rights are needed.
)
echo.
pause
exit /b 1

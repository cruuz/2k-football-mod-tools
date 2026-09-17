"""Feature dependencies stay lazy; opening a project never installs packages."""
from __future__ import annotations

import importlib
import shlex
import subprocess
import sys
from pathlib import Path

# Read by packaging/runtime_dependencies.py, including imports made through the
# helper below. Add dynamically selected third-party imports here explicitly.
LAZY_RUNTIME_IMPORTS = ("numpy",)
NUMPY_REQUIREMENT = "numpy==1.26.4"


class MissingDependency(RuntimeError):
    """A feature cannot run in this interpreter; safe to show in the studio."""


def numpy_install_message(feature: str) -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    args = [str(executable), "-m", "pip", "install", NUMPY_REQUIREMENT]
    command = subprocess.list2cmdline(args) if sys.platform == "win32" else shlex.join(args)
    message = f"{feature} needs the numpy package. Install it with: {command}"
    if sys.platform == "win32" and executable.with_name("python312._pth").is_file():
        message += ". For the bundled Windows runtime, reinstall the latest Studio Setup to restore its packages (pip is not bundled)."
    return message


def require_numpy(feature: str):
    try:
        return importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        if exc.name != "numpy":
            raise
        raise MissingDependency(numpy_install_message(feature)) from exc

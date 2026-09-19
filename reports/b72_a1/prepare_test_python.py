"""Provide the pinned installed Capstone dependency without user-site imports."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import venv

import capstone

assert capstone.__version__ == "5.0.7"
root = Path(__file__).resolve().parents[2]
target = root / ".scratch/test-python"
assert not target.exists(), "Use a fresh private test environment"
venv.EnvBuilder(system_site_packages=True, with_pip=False).create(target)
python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
site = Path(subprocess.check_output([str(python), "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"], text=True).strip())
source = Path(capstone.__file__).parent
destination = site / "capstone"
shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in destination.rglob("*") if p.is_file()}
assert subprocess.check_output([str(python), "-s", "-c", "import capstone;print(capstone.__version__)"], text=True).strip() == "5.0.7"
print(json.dumps({"dependency": "capstone==5.0.7", "source": str(source), "destination": str(destination),
                  "bytes": sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()),
                  "sha256": files}, indent=2))

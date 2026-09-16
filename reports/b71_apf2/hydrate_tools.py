"""Restore missing release tooling from the read-only archived public build."""
import hashlib
from pathlib import Path
import shutil
import importlib.util

root = Path(__file__).resolve().parents[2]
path = root / "packaging/check_apf2k8_mod_studio_release.py"
spec = importlib.util.spec_from_file_location("apf_release_check", path)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
archive = Path("/home/noah/Desktop/2K5-8 Editors/builds/apf2k8-mod-studio-0.1.0-alpha.69")
for relative, size, sha in (
    (check.REVIEWED_BINARY, check.REVIEWED_BINARY_SIZE, check.REVIEWED_BINARY_SHA256),
    (check.REVIEWED_WINDOWS_BINARY, check.REVIEWED_WINDOWS_BINARY_SIZE, check.REVIEWED_WINDOWS_BINARY_SHA256),
    (check.REVIEWED_LICENSE, check.REVIEWED_LICENSE_SIZE, check.REVIEWED_LICENSE_SHA256),
):
    source, target = archive / relative, root / relative
    payload = source.read_bytes()
    assert len(payload) == size and hashlib.sha256(payload).hexdigest() == sha, relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o777)
    assert target.read_bytes() == payload
    print(relative, size, sha)
relative = "tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md"
target = root / relative
if not target.exists():
    shutil.copyfile(archive / relative, target)
print(relative, hashlib.sha256(target.read_bytes()).hexdigest())

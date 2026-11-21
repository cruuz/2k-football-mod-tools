"""Prepare an archive-local Python environment for the portable Studio launchers."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys


def prepare(root, imports):
    private = root / ".venv"
    python = private / "bin" / "python3"
    # Two Finder launches can overlap. The kernel releases the lock if setup is interrupted.
    with (root / ".studio-setup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if private.is_symlink():
            raise ValueError(f"Private setup needs a folder inside this archive. Move the .venv link aside first: {private}")
        if private.exists() and not (private / "pyvenv.cfg").is_file():
            raise ValueError(f"The existing folder is not a Python environment. Move it aside and retry: {private}")
        environment = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
            environment.pop(key, None)
        environment["PIP_REQUIRE_VIRTUALENV"] = "true"
        if not python.is_file():
            print(f"Creating the private Studio runtime in {private} ...", flush=True)
            subprocess.run([sys.executable, "-I", "-m", "venv", str(private)], env=environment, check=True)
        # Verify the active venv before allowing pip to write. A bad bin/python3 must never install globally.
        probe = subprocess.check_output(
            [str(python), "-I", "-c", "import sys; print(sys.prefix); print(sys.version_info.minor)"],
            text=True, env=environment,
        ).splitlines()
        if len(probe) != 2 or Path(probe[0]).resolve() != private.resolve() or probe[1] not in ("11", "12", "13"):
            raise ValueError(f"The existing private runtime needs Python 3.11, 3.12 or 3.13. Move it aside and reopen the launcher: {private}")
        check = [str(python), "-I", "-c", imports]
        if subprocess.run(check, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            print("Installing the Studio packages into the private runtime. The first setup needs internet access.", flush=True)
            subprocess.run([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check",
                            "--no-input", "-r", str(root / "packaging" / "requirements-studio.txt")], env=environment, check=True)
            subprocess.run(check, env=environment, check=True)


if __name__ == "__main__":
    try:
        prepare(Path(sys.argv[1]), sys.argv[2])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Could not prepare the private Studio runtime. {error}", file=sys.stderr)
        sys.exit(1)

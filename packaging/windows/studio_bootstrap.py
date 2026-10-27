"""First-run setup for the Windows 2K5 and APF Studio launchers.

The Windows ``.bat`` launchers run this file with the user's own Python before
any third-party package exists, so it uses the standard library only. It builds
a private ``.venv`` beside the application, installs the pinned packages from
``packaging/requirements-studio.txt`` into it, checks that they import, and then
starts the Studio with that interpreter.

Nothing here writes outside the application folder, and nothing needs
administrator rights. Progress is printed for a person watching the console;
failures raise :class:`BootstrapError` with one plain sentence and a next step.

This module is deliberately not imported by the product package; it is a
launcher helper with no runtime dependencies of its own.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Sequence

PYTHON_URL = "https://www.python.org/downloads/windows/"
SUPPORTED_VERSIONS = ((3, 11), (3, 12))
IMPORT_CHECK = (
    "from PyQt5 import QtWidgets; import PIL; import numpy; import capstone; "
    "import unicorn; import mod_editor"
)
DOWNLOAD_NOTE = "about 110 MB to download, about 400 MB on disk"


class BootstrapError(RuntimeError):
    """A setup problem whose message is meant for the person at the console."""


REQUIRED_DATA_FILES = (
    "reports/assets/nfl2k5_team_select_card_inventory.json",
    "reports/assets/nfl2k5_player_portrait_compatibility.json",
    "reports/assets/nfl2k5_live_face_texture_compatibility.json",
    "reports/assets/nfl2k5_create_team_field_art_inventory.json",
    "reports/assets/scorebug_presentation_audit.json",
    "reports/assets/nfl2k5_p8_texture_inventory.json",
)


def _missing_data_files(app_root: Path) -> list[str]:
    return [name for name in REQUIRED_DATA_FILES if not (app_root / name).is_file()]


def _echo(message: str) -> None:
    """Write one progress line immediately, even when output is redirected."""
    print(message, flush=True)


def _venv_python(app_root: Path) -> Path:
    # The launchers are Windows-only, so keep one layout even when this module
    # is exercised by the cross-platform unit tests.
    return app_root / ".venv" / "Scripts" / "python.exe"


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _probe_interpreter(
    python: str,
    python_args: Sequence[str],
    run: Callable[..., subprocess.CompletedProcess],
) -> tuple[int, int, int]:
    """Return (major, minor, bits) for the selected base interpreter."""
    code = (
        "import struct, sys; "
        "print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], "
        "struct.calcsize('P') * 8))"
    )
    try:
        result = run(
            [python, *python_args, "-I", "-B", "-c", code],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise BootstrapError(
            "Python was not found on this computer.\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL}\n"
            'During setup tick "Add python.exe to PATH", then run this file again.\n'
            "No administrator rights are needed."
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootstrapError(
            "The selected Python could not run.\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL} and run this file again.\n"
            "No administrator rights are needed."
        ) from exc
    if result.returncode != 0 or not (result.stdout or "").strip():
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else "it did not report a version"
        raise BootstrapError(
            "The selected Python could not run.\n"
            f"{reason}\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL} and run this file again.\n"
            "No administrator rights are needed."
        )
    parts = result.stdout.strip().split()
    try:
        major, minor = (int(part) for part in parts[0].split("."))
        bits = int(parts[1])
    except (IndexError, ValueError) as exc:
        raise BootstrapError(
            "The selected Python did not report a usable version.\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL} and run this file again."
        ) from exc
    return major, minor, bits


def _check_base_python(
    python: str,
    python_args: Sequence[str],
    run: Callable[..., subprocess.CompletedProcess],
) -> None:
    major, minor, bits = _probe_interpreter(python, python_args, run)
    if (major, minor) not in SUPPORTED_VERSIONS:
        raise BootstrapError(
            f"Python {major}.{minor} is not supported by the pinned Studio packages.\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL}\n"
            'During setup tick "Add python.exe to PATH", then run this file again.\n'
            "No administrator rights are needed."
        )
    if bits != 64:
        raise BootstrapError(
            f"Python {major}.{minor} is {bits}-bit. The Studio packages need 64-bit Python.\n"
            f"Install 64-bit Python 3.12 from {PYTHON_URL}\n"
            'During setup tick "Add python.exe to PATH", then run this file again.\n'
            "No administrator rights are needed."
        )


def _imports_work(
    python: Path | str,
    app_root: Path,
    imports: str,
    run: Callable[..., subprocess.CompletedProcess],
) -> bool:
    environment = _clean_environment()
    environment["PYTHONPATH"] = str(app_root)
    try:
        result = run(
            [str(python), "-B", "-c", imports],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_step(
    command: list[str],
    run: Callable[..., subprocess.CompletedProcess],
    failure: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    try:
        result = run(command, check=False, env=environment)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootstrapError(f"{failure}\n\nDetails: {exc}") from exc
    if result.returncode != 0:
        raise BootstrapError(failure)
    return result


def _ensure_data_files(
    app_root: Path,
    private_python: Path,
    run: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> None:
    """Restore the reviewed startup catalogs when a source ZIP lacks them."""
    missing = _missing_data_files(app_root)
    if not missing:
        return
    echo(
        "The reviewed Studio data files are missing (this is the source ZIP). "
        "Downloading them once from the same release, about 65 MB ..."
    )
    hydration = app_root / "packaging" / "hydrate_release_inputs.py"
    if not hydration.is_file():
        raise BootstrapError(
            "The reviewed Studio data files are missing and this copy has no "
            "packaging/hydrate_release_inputs.py.\n"
            "Download the latest Setup.exe from the release page and run it. "
            "You do not need Python for Setup.exe."
        )
    _run_step(
        [str(private_python), str(hydration)],
        run,
        "The reviewed Studio data files could not be downloaded.\n"
        "Check the internet connection and run this file again, or download the "
        "latest Setup.exe from the release page and run it.\n"
        "You can also run this once yourself:\n"
        f'    "{private_python}" "{hydration}"',
        _clean_environment(),
    )
    still_missing = _missing_data_files(app_root)
    if still_missing:
        raise BootstrapError(
            "The reviewed Studio data files are still missing:\n"
            + "\n".join(still_missing)
            + "\nDownload the latest Setup.exe from the release page and run it."
        )
    echo("The reviewed Studio data files are ready.")


def ensure_runtime(
    app_root: Path,
    python: str,
    python_args: Sequence[str] = (),
    requirements: Path | None = None,
    imports: str = IMPORT_CHECK,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    echo: Callable[[str], None] = _echo,
) -> Path:
    """Return a ready private interpreter, creating and filling ``.venv`` if needed."""
    app_root = Path(app_root).absolute()
    requirements = Path(
        requirements if requirements is not None else app_root / "packaging" / "requirements-studio.txt"
    )
    if not requirements.is_file():
        raise BootstrapError(
            f"The Studio package list is missing: {requirements}\n"
            "Extract the whole archive again and run the launcher from inside the "
            "extracted folder."
        )

    private_python = _venv_python(app_root)
    if private_python.is_file():
        if _imports_work(private_python, app_root, imports, run):
            echo(f"Using the private Studio runtime already in {private_python.parent.parent}.")
            _ensure_data_files(app_root, private_python, run, echo)
            return private_python
        echo(
            f"The private Studio runtime in {private_python.parent.parent} is incomplete. "
            "Rebuilding it now."
        )
        try:
            shutil.rmtree(private_python.parent.parent)
        except OSError as exc:
            raise BootstrapError(
                "The old private Studio runtime could not be removed.\n"
                "Close every 2K5 Mod Studio window, then run this file again.\n"
                "If it repeats, delete the .venv folder beside the launcher and try once more.\n"
                f"\nDetails: {exc}"
            ) from exc

    _check_base_python(python, python_args, run)

    venv_dir = app_root / ".venv"
    echo(f"Creating a private Python runtime in {venv_dir} ...")
    try:
        created = run(
            [python, *python_args, "-m", "venv", str(venv_dir)],
            check=False,
            env=_clean_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        created = None
        detail = exc
    if created is None or created.returncode != 0:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise BootstrapError(
            "Could not create the private Python runtime.\n"
            "Move the whole Studio folder to your Desktop or Documents and run this "
            "file again. Do not put it in Program Files and do not run as administrator.\n"
            f"If Python is incomplete, reinstall 64-bit Python 3.12 from {PYTHON_URL} "
            "with the default options."
            + (f"\n\nDetails: {detail}" if created is None else "")
        )

    if not private_python.is_file():
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise BootstrapError(
            "Python created the private runtime folder but not its interpreter.\n"
            f"Reinstall 64-bit Python 3.12 from {PYTHON_URL} with the default "
            "options, then run this file again."
        )

    echo(f"Installing the Studio packages ({DOWNLOAD_NOTE}; needs an internet connection) ...")
    _run_step(
        [
            str(private_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--progress-bar",
            "on",
            "--only-binary=:all:",
            "-r",
            str(requirements),
        ],
        run,
        "The Studio packages could not be installed.\n"
        "Check the internet connection and the messages above, then run this file "
        "again. It is safe to repeat.\n"
        "If it keeps failing, delete the .venv folder beside the launcher and try once "
        "more. The packages need 64-bit Windows and an internet connection.",
        _clean_environment(),
    )

    if not _imports_work(private_python, app_root, imports, run):
        raise BootstrapError(
            "The packages installed but the Studio still cannot load them.\n"
            "Run this file again. If the same message appears, delete the .venv "
            "folder beside the launcher and try once more."
        )
    echo("The private Studio runtime is ready.")
    _ensure_data_files(app_root, private_python, run, echo)
    return private_python


def _split_launcher_arguments(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    arguments = list(argv)
    if "--" in arguments:
        split = arguments.index("--")
        return arguments[:split], arguments[split + 1 :]
    return arguments, []


def main(argv: Sequence[str] | None = None, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
         echo: Callable[[str], None] = _echo) -> int:
    bootstrap_args, app_args = _split_launcher_arguments(
        sys.argv[1:] if argv is None else argv
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", required=True, type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--python-arg", action="append", default=[])
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--imports", default=IMPORT_CHECK)
    parser.add_argument("--module", default="mod_editor")
    parser.add_argument("--name", default="2K5 Mod Studio")
    args = parser.parse_args(bootstrap_args)

    setup_only = bool(app_args and app_args[0] == "--setup")
    if setup_only:
        app_args = app_args[1:]

    try:
        private_python = ensure_runtime(
            args.app_root,
            args.python,
            args.python_arg,
            args.requirements,
            args.imports,
            run=run,
            echo=echo,
        )
        if setup_only:
            echo(f"Setup finished. Start {args.name} with this launcher.")
            return 0

        environment = _clean_environment()
        environment["PYTHONPATH"] = str(Path(args.app_root).absolute())
        echo(f"Starting {args.name} ...")
        try:
            result = run(
                [str(private_python), "-m", args.module, *app_args],
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError(
                f"{args.name} could not start.\n\nDetails: {exc}"
            ) from exc
        return result.returncode
    except BootstrapError as exc:
        print(f"\n{args.name} could not start.\n\n{exc}\n", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

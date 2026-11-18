"""Launch the Studio in this distribution. Older portable updaters look for this entry point."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    entry = ".cli" if Path(__file__).with_name("cli.py").is_file() else ".apf_studio.__main__"
    return import_module(entry, __package__).main(argv)


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())

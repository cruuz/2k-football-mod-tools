"""Explicit prerequisites for tests using the complete private NFL pack reader."""
from pathlib import Path
import unittest


def require_nfl_retail_packs(source: Path) -> None:
    """Keep strict size/hash validation active once all sixteen inputs exist."""
    path = Path(source)
    if path.is_file():
        return  # Image files keep the strict reader's own validation.
    folder = path if path.name == "vc_53450030" else path / "vc_53450030"
    missing = [f"{index:X}" for index in range(16)
               if not (folder / f"{index:X}").is_file()]
    if missing:
        raise unittest.SkipTest(
            f"complete private NFL archive required; missing packs {', '.join(missing)} in {folder}"
        )

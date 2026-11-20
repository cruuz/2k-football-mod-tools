"""Assemble the scoring slice sources with GNU binutils and compare them with the bytes the Studio writes.

    python3 tools/scoring/check.py
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_kick_aim as aim, nfl2k5_sim_scoring as scoring  # noqa: E402

SOURCES = (("cpu_kick_aim.S", aim.SITE_VA, aim.site_bytes()),
           ("sim_long_attempts.S", scoring.RAMP_VA, scoring.ramp_bytes()),
           ("sim_fg_chance.S", scoring.ACCURACY_VA, scoring.accuracy_bytes()))


def assemble(source: Path, va: int) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        obj, out = Path(folder) / "x.o", Path(folder) / "x.bin"
        subprocess.run(["as", "--32", "-o", str(obj), str(source)], check=True)
        subprocess.run(["ld", "-m", "elf_i386", "--oformat=binary", f"-Ttext={va:#x}", "-e", "start",
                        "-o", str(out), str(obj)], check=True)
        return out.read_bytes()


def main() -> int:
    bad = 0
    for name, va, expected in SOURCES:
        built = assemble(Path(__file__).with_name(name), va)
        same = expected[:len(built)] == built and set(expected[len(built):]) <= {0xCC}
        print(f"{name}: {len(built)} bytes {'matches' if same else 'DIFFERS'}")
        bad += not same
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Capability probes for the development-only i386 ELF toolchain some tests rebuild generated code with.

The checked-in byte templates (scorebug sprite engine, cpu_clock2, Hall of Fame rules) are rebuilt from source by
GNU gcc/binutils targeting 32-bit x86 ELF. Linux CI has that toolchain. macOS arm64 runners ship Apple clang, which
rejects the repo's i386 freestanding flags and whose ``as`` is not GNU as; Windows runners ship MinGW, whose ``ld``
has no ``elf_i386`` emulation and whose ``as --32`` writes PE/COFF. Each probe runs the same tool with the same flags on
a two-line source and returns ``None`` when the capability is there, else the reason (the tool's own message), so a
test skips naming exactly what is missing and still runs wherever the toolchain can do the job.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

#: tools/nfl2k5_honors_build.py and tools/scorebug_sprite/build_runtime.py (without the optimisation level)
FREESTANDING_I386_FLAGS = ("-m32", "-ffreestanding", "-fno-builtin", "-fno-strict-aliasing", "-fno-pic", "-fno-pie",
                           "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
                           "-fomit-frame-pointer", "-fno-jump-tables", "-mpreferred-stack-boundary=2", "-mno-sse",
                           "-mno-mmx", "-Wall", "-Wextra", "-Werror")
_ELF32_LE = b"\x7fELF\x01\x01"


def _first_line(done: subprocess.CompletedProcess) -> str:
    text = (done.stderr or done.stdout or b"")
    text = text.decode("utf-8", "replace") if isinstance(text, bytes) else text
    return (text.strip().splitlines() or ["exit status %d" % done.returncode])[0]


@functools.lru_cache(maxsize=None)
def gcc_freestanding_i386(optimize: str = "-Os") -> str | None:
    """None when ``gcc`` compiles freestanding 32-bit x86 ELF with the repo's flags, else why not."""
    gcc = shutil.which("gcc")
    if not gcc:
        return "no gcc on PATH"
    with tempfile.TemporaryDirectory(prefix="i386-probe-") as folder:
        base = Path(folder)
        (base / "probe.c").write_text("int probe(int x) { return x + 1; }\n", encoding="utf-8", newline="\n")
        done = subprocess.run([gcc, optimize, *FREESTANDING_I386_FLAGS, "-c", str(base / "probe.c"),
                               "-o", str(base / "probe.o")], capture_output=True)
        if done.returncode != 0:
            return "gcc cannot build freestanding i386 code with the repo's flags: " + _first_line(done)
        if (base / "probe.o").read_bytes()[:6] != _ELF32_LE:
            return "gcc -m32 does not write 32-bit ELF objects here"
    return None


@functools.lru_cache(maxsize=None)
def gnu_ld_elf_i386(optimize: str = "-Os") -> str | None:
    """None when gcc (as above) and ``ld -r -m elf_i386`` both work, else why not."""
    reason = gcc_freestanding_i386(optimize)
    if reason:
        return reason
    ld = shutil.which("ld")
    if not ld:
        return "no ld on PATH"
    with tempfile.TemporaryDirectory(prefix="i386-probe-") as folder:
        base = Path(folder)
        (base / "probe.c").write_text("int probe(int x) { return x + 1; }\n", encoding="utf-8", newline="\n")
        subprocess.run([shutil.which("gcc"), optimize, *FREESTANDING_I386_FLAGS, "-c", str(base / "probe.c"),
                        "-o", str(base / "probe.o")], capture_output=True, check=True)
        done = subprocess.run([ld, "-r", "-m", "elf_i386", "-o", str(base / "out.o"), str(base / "probe.o")],
                              capture_output=True)
        if done.returncode != 0:
            return "ld has no elf_i386 emulation: " + _first_line(done)
    return None


@functools.lru_cache(maxsize=None)
def gnu_as_elf32() -> str | None:
    """None when ``as --32`` assembles to a little-endian 32-bit ELF object, else why not."""
    assembler = shutil.which("as")
    if not assembler:
        return "no as on PATH"
    with tempfile.TemporaryDirectory(prefix="i386-probe-") as folder:
        base = Path(folder)
        (base / "probe.S").write_text(".text\n.globl probe\nprobe:\n    ret\n", encoding="utf-8", newline="\n")
        done = subprocess.run([assembler, "--32", "-o", str(base / "probe.o"), str(base / "probe.S")],
                              capture_output=True)
        if done.returncode != 0:
            return "as is not GNU as for i386: " + _first_line(done)
        if (base / "probe.o").read_bytes()[:6] != _ELF32_LE:
            return "as --32 does not write 32-bit ELF objects here (PE/COFF toolchain)"
    return None

"""E2-local GDB reads and stopped-state witnesses. Importing this never starts xemu."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

BODY_SIZE = 0x13390
DEFAULT_GROUPS_SHA256 = "628c2b834d6d0a4baefc479fcbc02d00d4e0bf50a87fd6aa5a4405b139bd5116"
MATCH_TEAMS = {"home": 0xB30864, "away": 0xB30A58}
BOOK_NAMES = {"home": 0xB307D0, "away": 0xB30810}
BOOK_BINDINGS = {"home": 0xE5FE80, "away": 0xE5FE84}
SELECTION = {"home": 0xACF63C, "away": 0xACF640}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def play_fields(body):
    """Pinned native PLAY relocation cells, also exercised by the native tests."""
    if len(body) != BODY_SIZE or body[12:16] != b"PLAY":
        raise ValueError("expected one fixed PLAY body")
    nf, np, nc = struct.unpack_from("<3I", body, 0x34)
    if not (0 < nf <= 72 and 0 < np <= 270 and 0 < nc <= 320):
        raise ValueError(f"invalid PLAY counts {(nf, np, nc)}")
    fields = [0x30, 0x44, 0x48, 0x60, 0x64, 0x68]
    fields += [0x134 + i * 180 for i in range(nf)]
    fields += [0x993C + i * 16 for i in range(nc)]
    for i in range(np):
        fields += [0x33FC + i * 96] + [0x3408 + i * 96 + j * 8 for j in range(11)]
    return fields


def canonical_play(body, base=None):
    """Normalize runtime pointers, retaining all formations, plays and personnel bytes.

    Exclude the resource framework's first 0x30 bytes and the native decoder's
    formation (bit 30 at 0xE0EDE) and play (bit 31 at 0x1A9A8C) flags. Every other content
    bit, including all personnel codes and assignments, participates in the hash.
    """
    out = bytearray(body)
    fields = play_fields(out)
    if base is not None:
        for at in fields:
            value = struct.unpack_from("<I", out, at)[0]
            if value:
                if not base <= value < base + len(out):
                    raise ValueError(f"PLAY pointer outside bound body at {at:#x}: {value:#x}")
                struct.pack_into("<I", out, at, (value - base - at + 1) & 0xFFFFFFFF)
    out[:0x30] = bytes(0x30)
    nf, np = struct.unpack_from("<2I", out, 0x34)
    for count, start, stride, mask in ((nf, 0x138, 180, 0xBFFFFFFF), (np, 0x3400, 96, 0x7FFFFFFF)):
        for i in range(count):
            at = start + i * stride
            struct.pack_into("<I", out, at, struct.unpack_from("<I", out, at)[0] & mask)
    return bytes(out)


def game_ready_play(body):
    """PROVED OFFLINE: reproduce E's 0x204B40 default selection-group setup.

    Input is an unrelocated disc body. This transforms only the expected body;
    captured link bits are never masked. The native initializer fills missing
    groups 0..2 from group 3, requiring play flag 0x800000 for formation types
    4..7. Empty links terminate its candidate search, but not its presence scan.
    """
    play_fields(body)
    out = bytearray(body)
    nf, np = struct.unpack_from("<2I", out, 0x34)
    if nf > 50:
        raise ValueError("formation links exceed fixed PLAY capacity")
    for formation in reversed(range(nf)):
        flags = struct.unpack_from("<I", out, 0x138 + formation * 180)[0]
        restricted = 4 <= ((flags >> 8) & 63) <= 7
        aux = 0x245C + formation * 80
        for group in range(3):
            words = struct.unpack_from("<36H", out, aux)
            if any(w & 511 != 511 and (w >> 9) & 3 == group for w in words):
                continue
            for slot, word in enumerate(words):
                play = word & 511
                if play == 511:
                    break
                if play >= np:
                    raise ValueError("formation link references missing play")
                if (word >> 9) & 3 != 3:
                    continue
                if restricted and not (struct.unpack_from("<I", out, 0x3400 + play * 96)[0] & 0x800000):
                    continue
                struct.pack_into("<H", out, aux + slot * 2, (word & ~0x600) | (group << 9))
                break
    return bytes(out)


def inspect_gdb(done):
    output = (done.stdout or "") + (done.stderr or "")
    eip = re.search(r"\beip\s+0x([0-9a-fA-F]+)", output)
    errors = re.findall(r"(?im)^.*(?:Cannot access memory|No registers|not being run|Remote communication error|"
                        r"Connection timed out|Connection refused|Traceback|Error while executing Python).*$", output)
    return dict(ok=done.returncode == 0 and eip is not None and not errors,
                returncode=done.returncode, eip=int(eip[1], 16) if eip else None, errors=errors, output=output)


def run_gdb(port, log_path, commands=(), *, script=None, timeout=40, resume=None):
    argv = ["gdb", "-q", "-nx", "-batch", "-ex", "set pagination off", "-ex", "set confirm off",
            "-ex", "set architecture i386", "-ex", "set remotetimeout 10",
            "-ex", f"target remote 127.0.0.1:{int(port)}", "-ex", "info registers eip"]
    if script is not None:
        argv += ["-x", str(script)]
    for command in commands:
        argv += ["-ex", command]
    argv += ["-ex", "detach"]
    try:
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            result = inspect_gdb(done)
        except subprocess.TimeoutExpired as exc:
            def text(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            result = dict(ok=False, eip=None, returncode=None, errors=["GDB timeout"],
                          output=text(exc.stdout) + text(exc.stderr) + "\nGDB timeout\n")
        Path(log_path).write_text(result["output"])
        Path(log_path).with_suffix(".json").write_text(json.dumps({k: val for k, val in result.items()
                                                                 if k != "output"}, indent=2) + "\n")
        if not result["ok"]:
            raise RuntimeError(f"GDB read failed; retained {log_path}: {result['errors']}")
        return result
    finally:
        if resume is not None:
            resume()  # detach normally resumes; this also recovers a timed-out client


class Reader:
    def __init__(self, read, directory):
        self.read = read
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ranges = []

    def bytes(self, at, size, label):
        if not (0x10000 <= at < 0xC0000000 and 0 < size <= 1 << 20 and at + size <= 0xC0000000):
            raise ValueError(f"invalid guest range {at:#x}+{size:#x}")
        raw = bytes(self.read(at, size))
        if len(raw) != size:
            raise ValueError("short guest memory read")
        file = f"{len(self.ranges):03d}-{label}.bin"
        (self.directory / file).write_bytes(raw)
        self.ranges.append(dict(address=at, size=size, file=file, sha256=sha(raw)))
        return raw

    def u32(self, at, label):
        return struct.unpack("<I", self.bytes(at, 4, label))[0]

    def text(self, at, label, chars=64):
        raw = self.bytes(at, 2 * chars, label)
        for end in range(0, len(raw), 2):
            if raw[end:end + 2] == b"\0\0":
                return raw[:end].decode("utf-16le")
        raise ValueError(f"unterminated {label}")

    def team(self, pointer, label):
        raw = self.bytes(pointer, 0x154, label)
        word = lambda at: struct.unpack_from("<I", raw, at)[0]
        abbreviation = self.u32(word(0x110) + 4, label + "-label")
        return dict(pointer=pointer, name=self.text(word(0x104), label + "-name"),
                    franchise=self.text(abbreviation, label + "-franchise", 8),
                    category=word(0x128), players=raw[0x11C])


def capture(read, eip, options):
    """Runs inside GDB while the target is stopped, or against a test memory reader."""
    directory = Path(options["directory"])
    reader = Reader(read, directory)
    result = dict(eip=eip, phase=options["phase"], ok=False, ranges=reader.ranges)
    try:
        if options["phase"] not in ("selection", "preview", "books"):
            raise ValueError("unknown witness phase")
        if options["phase"] == "selection":
            result["selection"] = {side: reader.team(reader.u32(at, side + "-selection-pointer"), side)
                                   for side, at in SELECTION.items()}
        else:
            catalog = json.loads(Path(options["catalog"]).read_text())
            result["mode"] = reader.u32(0xE5FF80, "mode")
            result["ordinal"] = reader.u32(0xBF1858, "ordinal")
            stadium = reader.u32(0xE5FE64, "stadium-pointer")
            result["stadium"] = stadium
            for key, offset in (("shared_name", 0), ("shared_presentation_name", 16)):
                result[key] = reader.text(reader.u32(stadium + offset, key + "-pointer"), key)
            if result["mode"] == 8 and result["ordinal"] < 50:
                ptr = reader.u32(catalog["venue_table"] + result["ordinal"] * 4, "historic-venue-pointer")
                result["historic_venue"] = reader.text(ptr, "historic-venue")
                if result["historic_venue"] != catalog["venues"][result["ordinal"]]:
                    raise ValueError("installed venue text differs from catalog")
            if options["phase"] == "books":
                result["books"] = {}
                for side in ("home", "away"):
                    team = reader.team(MATCH_TEAMS[side], side + "-match-team")
                    name = reader.text(BOOK_NAMES[side], side + "-book-filename", 32)
                    pointer = reader.u32(BOOK_BINDINGS[side], side + "-bound-book")
                    entry = catalog["books"][name]
                    body = reader.bytes(pointer, entry["body_size"], side + "-PLAY")
                    expected_name = ("E2R-" if result["mode"] == 8 or team["category"] == 4 else "") + team["franchise"] + "-pb.iff"
                    canonical = sha(canonical_play(body, pointer))
                    item = dict(team=team, filename=name, expected_filename=expected_name, pointer=pointer,
                                counts=list(struct.unpack_from("<3I", body, 0x34)),
                                canonical_sha256=canonical, expected_sha256=entry["canonical_sha256"],
                                content_matches=canonical == entry["canonical_sha256"])
                    result["books"][side] = item
                    if name != expected_name or not item["content_matches"]:
                        raise ValueError(f"{side}: bound PLAY does not match expected book {expected_name}")
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (directory / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def capture_gdb(port, directory, phase, *, catalog=None, resume=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    options = dict(directory=str(directory), phase=phase, catalog=str(catalog) if catalog else None)
    script = directory / "capture.py"
    script.write_text("import gdb, sys\n" + f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
                      "from lab_memory import capture\n"
                      f"capture(gdb.selected_inferior().read_memory, int(gdb.parse_and_eval('$eip')), {options!r})\n")
    run_gdb(port, directory / "gdb.log", script=script, resume=resume)
    result = json.loads((directory / "capture.json").read_text())
    if not result["ok"]:
        raise RuntimeError(f"capture failed: {result.get('error')}; retained {directory}")
    return result


def make_catalog(disc, output):
    """Main's read-only preflight: pin actual candidate books and installed text table."""
    from mod_editor.core import nfl2k5_historic_styles as hs
    from mod_editor.core import nfl2k5_stock_books as stock
    from mod_editor.core import nfl2k5_moment_venues as venues
    from mod_editor.core import nfl2k5_espn25_rosters as rosters
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    xbe = rosters.read_xbe(Path(disc))
    if venues.status(xbe) != "applied" or stock.status(xbe) != "applied":
        raise ValueError("candidate must contain the venue and stock resolver owners")
    # Refuse to model a different native initializer with these expected hashes.
    if sha(XbeImage(xbe).read(0x204B40, 0x138)) != DEFAULT_GROUPS_SHA256:
        raise ValueError("foreign native PLAY selection-group initializer")
    result = dict(normalization="e2.play.v2/native-default-groups", xbe_sha256=sha(xbe),
                  venue_table=venues.allocation(xbe)["va"] + venues.TABLE,
                  venues=[r["venue"] for r in venues.rows()], books={})
    with hs.Source(disc) as source:
        for row in stock.aliases():
            for name in (row["alias"], row["source"]):
                raw = source.get(name)
                if name == row["alias"] and sha(raw) not in (row["source_sha256"], row["one_pool_sha256"]):
                    raise ValueError(f"{name}: not a pinned stock book")
                result["books"][name] = dict(resource_sha256=sha(raw), body_size=len(raw) - 32,
                                             source_canonical_sha256=sha(canonical_play(raw[32:])),
                                             canonical_sha256=sha(canonical_play(game_ready_play(raw[32:]))))
            if result["books"][row["alias"]]["canonical_sha256"] == result["books"][row["source"]]["canonical_sha256"]:
                raise ValueError(f"{row['source']}: modern and stock books are identical")
    if output is not None:
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
    return result

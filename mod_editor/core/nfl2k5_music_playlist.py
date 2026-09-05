"""EXPERIMENTAL / UNWITNESSED shared music shuffle, owned RX/RW/RO storage.

The default list is the 7 menu and 59 jukebox recordings. This overrides the
background UserList/HDD choice, but preserves explicit jukebox previews and PA.
Timed loading/show players retain their retail scheduling. No all-mode claim.
Apply is monotonic; reconfiguration requires rebuilding from a supported base.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from . import nfl2k5_music_playlist_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_music_playlist"
CODE_SIZE, DATA_SIZE, RO_SIZE, MAX_ITEMS = 2048, 512, 1024, 100
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
MAGIC = b"ASTRAMP1"
BANK_COUNTS = {"femusic": 7, "cribmusic": 59, "loadm": 3, "wrapupm": 8,
               "halftimeaudio": 5, "drafta": 4}
CORE = tuple((bank, i) for bank in ("femusic", "cribmusic") for i in range(BANK_COUNTS[bank]))
# Only established background beds; short cues and the unresolved draft player
# are excluded. This switch never changes presentation scheduling or narration.
BEDS = (("loadm", 2),) + tuple(("wrapupm", i) for i in range(8)) + (("halftimeaudio", 3),)
POSITION_POLICY = ("Keep the song and shuffle position between menus, Crib and game background. "
                   "Modal pauses resume playback. Loading, shows and jukebox previews stop the "
                   "background song; it restarts on return. One selected song repeats; zero stops.")
HELP_TEXT = ("Experimental, not yet tested in game. Shuffle 7 menu recordings and 59 jukebox "
             "recordings, including 12 spoken outtakes. Replaces background disc and HDD playlists. "
             "Loading and shows keep their timed music. " + POSITION_POLICY)
# Full instructions only. All are live routine entries/calls, never caves.
HOOKS = {
    "manual_next": (0x27F040, bytes.fromhex("a108ccc300")),
    "hdd_callback": (0x28016D, bytes.fromhex("6840f02700")),
    "profile_context": (0xF64CD, bytes.fromhex("e8ee9f1800")),
    "player_init": (0xF63CA, bytes.fromhex("e8e18d1800")),
    "halftime_enter": (0xD90F0, bytes.fromhex("558bec83e4f8")),
    "halftime_exit": (0xD9350, bytes.fromhex("a1183bb700")),
    "enqueue": (0x2801A0, bytes.fromhex("558bec83e4f8")),
    "dispatch": (0x280450, bytes.fromhex("5333d2b910ccc300")),
    "advance": (0x27FF15, bytes.fromhex("e826f1ffff")),
    "frame": (0x2806B2, bytes.fromhex("e899fdffff")),
    "suspend": (0x27FEC0, bytes.fromhex("b910ccc300")),
    "pause": (0x27F6B0, bytes.fromhex("a1a4d3c500")),
    "resume": (0x27F6F0, bytes.fromhex("a1a4d3c500")),
    "preview": (0x27FF90, bytes.fromhex("558bec83e4f8")),
    "context": (0x2804C0, bytes.fromhex("538bd985db")),
    "mode": (0xF6510, bytes.fromhex("568bf1ff24b5b4650f00")),
}
SYMBOLS = {
    "retail_player_init": 0x27F1B0, "retail_halftime_tail": 0xD90F6,
    "retail_halftime_exit_tail": 0xD9355,
    "retail_rng": 0x48BC0, "resource_lookup": 0x449E0, "range_copy": 0x3CAD20,
    "bind_bank": 0xCEF80, "stop_stream": 0xCF1B0, "bind_volume": 0xCEFD0,
    "packet_init": 0x245460, "packet_callback": 0x245550, "packet_range": 0x245480,
    "queue_packet": 0xCF150, "retail_stop_direct": 0x27F020,
    "retail_advance": 0x27F040, "stop_hdd": 0x3283A0,
    "retail_pause_tail": 0x27F6B5, "retail_resume_tail": 0x27F6F5,
    "retail_preview_tail": 0x27FF96, "string_equal": 0x30CF0,
    "game_music_switch": 0x1C4210, "loading_start": 0xF5410,
}
# Hashes of complete inspected routines, normalized only at the hooks above.
# Populated from the pinned USA retail executable; no developer input at runtime.
GUARDS = (
    (1008512, 225, '5e0c7eed81ec406715e4f093a5e182c11705295541e4fc7a211e338d52cf958b'),
    (1008672, 231, '1c82ea5c067ab03a5990f0b2cc35497c4cb6ffe5c90811b5fbbb97c3add0e0da'),
    (889072, 605, 'edcc7b5032750355ef562b46ca5620fbd4ddb57e22e92ab4adea563f2c6530c6'),
    (889680, 40, 'd4f08fa3a4b055f66dad6bcb27b620efad1a0fbf94fb03204363d8f9bfea9f03'),
    (3976528, 54, '66a704a3e81cad26db8f4f7b0e2bd1bee289c031945e0310060bc6b7c8817051'),
    (2380832, 87, 'e2c15c410dce5049896ce3168e0b309bcb797edab5408f5e453498057bf15b66'),
    (1008912, 184, 'd48b53b32ceca2b1df0b5945144a093cff0316badf6724e86f9245211636e13c'),
    (2621856, 272, '7d7760176a898c2af4469b3a51394803bffc39d18ebf66b9a3a28df7c429e0fb'),
    (2621200, 16, 'a8c1f40c89bb166de5b6eefeb69d250891a65bf3642ba5cd0663fee5d2305038'),
    (2623008, 174, 'd74ad2286dee2ac6f14312f91b2388883d1db08d45b0fe852a0365914fceee8c'),
    (2622544, 218, '5504b0c42d2d71d69967e6aa563e9b3f6e488055f32197d6702d47bda073d52f'),
    (2621120, 65, '54039ef6653250a020d9555ceece2a0cd952b08a77c6145ddf7735dd917557c8'),
    (2619056, 120, '1f4b4c0dcd85db8cc3e66bbfe0f7d601e6e9d50031cc816424dd4e1e9bd69679'),
    (2621328, 521, 'e1942b75b5f723ed14a42d421dcaa2fd577986e2b1738a51f714b6d8c69a14a4'),
    (3976480, 76, '72b4abcf3961a4614ea75742c8e60678b9e4e5159182257601bee5bb75bd6509'),
    (2381136, 48, '2ffece3289e9cc952dfe550a17d1a3f7299e4ca60023a948e2f81da754d06053'),
    (2380928, 128, 'd59214278de5ebe906f7ba00bdd05eceb15d6363cc5dc8f031e08f76e2f0223d'),
    (297920, 10, '52c42074930f0ed09b1637f4754b8c02fa033021d91b94db67656a55932ca01d'),
    (297808, 56, 'ae1c4cc23c4e420827a6ff5ab07a6aebab8b3258db105893eec4af4d12bc8673'),
    (2617376, 23, '4a3c774bd355cf2c920ce61f6dc1c37a4be67586af130f7d9f9332bb14f3bd35'),
)


class PlaylistError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise PlaylistError(message)


@dataclass(frozen=True)
class Selection:
    records: tuple = CORE
    enabled: tuple | None = None

    def __post_init__(self):
        records = tuple(tuple(r) for r in self.records)
        _require(len(records) <= MAX_ITEMS, "Playlist exceeds the 100-record storage budget")
        _require(all(len(r) == 2 and r[0] in BANK_COUNTS and type(r[1]) is int
                     and 0 <= r[1] < 65536 for r in records), "Invalid bank or stream index")
        _require(len(set(records)) == len(records), "Duplicate playlist recordings")
        enabled = tuple(range(len(records))) if self.enabled is None else tuple(self.enabled)
        _require(all(type(i) is int and 0 <= i < len(records) for i in enabled)
                 and len(set(enabled)) == len(enabled), "Invalid enabled record indices")
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "enabled", tuple(sorted(enabled)))

    def status(self, payload):
        try:
            state, current = _inspect(payload)
        except (ValueError, TypeError, KeyError, IndexError, struct.error):
            return "foreign"
        return "applied" if state == "applied" and current == self else (
            "foreign" if state == "applied" else state)

    def apply(self, payload):
        return apply(payload, selection=self)


def selection(*, include_outtakes=True, include_beds=False, enabled=None):
    _require(type(include_outtakes) is bool and type(include_beds) is bool, "Playlist switches must be Boolean")
    records = CORE + (BEDS if include_beds else ())
    allowed = tuple(i for i, (bank, index) in enumerate(records)
                    if include_outtakes or bank != "cribmusic" or not 20 <= index <= 31)
    if enabled is not None:
        chosen = Selection(records, tuple(enabled)).enabled
        allowed = tuple(i for i in chosen if i in allowed)
    return Selection(records, allowed)


def from_options(value):
    """Validate the Music page's JSON choices without importing Qt."""
    _require(isinstance(value, dict) and type(value.get("schema")) is int and value["schema"] == 1,
             "Unsupported playlist choices")
    _require(all(type(value.get(k)) is bool for k in ("music_shuffle", "include_outtakes", "include_beds")),
             "Playlist choices need Boolean switches")
    checked = Selection(CORE + BEDS, value.get("checked", ())).enabled
    count = len(CORE) + (len(BEDS) if value["include_beds"] else 0)
    selected = selection(include_outtakes=value["include_outtakes"], include_beds=value["include_beds"],
                         enabled=tuple(i for i in checked if i < count))
    _require(value.get("records") == [list(r) for r in selected.records]
             and value.get("enabled") == list(selected.enabled),
             "Playlist choices do not match their song selection")
    return selected


def validate_source(selected, counts):
    """Build preflight: counts come from validated source/rebuilt AUSB descriptors.

    Runtime lookup also rechecks count and boundaries immediately before enqueue.
    This function performs no file or archive reads and never assumes 200 metadata
    rows imply that their source audio descriptors have the same geometry.
    """
    _require(isinstance(selected, Selection), "Expected a playlist selection")
    for bank, index in selected.records:
        count = counts.get(bank)
        _require(type(count) is int and 0 < count <= 65536 and index < count,
                 f"Missing descriptor or invalid index: {bank}:{index}")
    return selected


def _names(ro_va):
    blob = bytearray()
    pointers = {}
    for bank in BANK_COUNTS:
        pointers[bank] = ro_va + 64 + len(blob)
        blob.extend((bank + "\0").encode("utf-16le"))
    _require(len(blob) <= 128, "Bank strings exceed RO header")
    return pointers, bytes(blob)


def ro_for(selected, ro_va):
    pointers, names = _names(ro_va)
    blob = bytearray(RO_SIZE)
    blob[:8] = MAGIC
    struct.pack_into("<I", blob, 8, len(selected.records))
    mask = sum(1 << i for i in selected.enabled)
    blob[16:32] = mask.to_bytes(16, "little")
    blob[64:64 + len(names)] = names
    for i, (bank, index) in enumerate(selected.records):
        struct.pack_into("<2I", blob, 192 + i * 8, pointers[bank], index)
    return bytes(blob)


def _decode_ro(content, ro_va):
    _require(content[:8] == MAGIC, "Foreign playlist RO header")
    count = struct.unpack_from("<I", content, 8)[0]
    _require(count <= MAX_ITEMS, "Foreign playlist record count")
    pointers, _ = _names(ro_va)
    banks = {v: k for k, v in pointers.items()}
    records = []
    for i in range(count):
        ptr, index = struct.unpack_from("<2I", content, 192 + i * 8)
        _require(ptr in banks, "Foreign playlist bank pointer")
        records.append((banks[ptr], index))
    mask = int.from_bytes(content[16:32], "little")
    _require(mask >> count == 0, "Foreign playlist enabled mask")
    selected = Selection(tuple(records), tuple(i for i in range(count) if mask & (1 << i)))
    _require(content == ro_for(selected, ro_va), "Foreign playlist RO bytes or padding")
    return selected


def sites(payload):
    rows = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(rows) == {"code", "data", "read_only"}, "Playlist needs the complete allocation union; rebuild from base")
    for _, kind, size, align in REQUESTS:
        _require((rows[kind]["size"], rows[kind]["align"]) == (size, align), "Foreign playlist allocation")
    return rows["code"], rows["data"], rows["read_only"]


def code_for(code_va, data_va, ro_va):
    blob = bytearray(assembly.CODE)
    symbols = dict(SYMBOLS, code=code_va, state_data=data_va, playlist_ro=ro_va)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        addend = struct.unpack_from("<I", blob, offset)[0]
        target = symbols[symbol] + value + addend
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    _require(len(blob) <= CODE_SIZE, "Playlist exceeds its code budget")
    return bytes(blob).ljust(CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in assembly.LABELS.items()}


def edits(labels):
    for name, (va, retail) in HOOKS.items():
        target = labels["enqueue" if name == "dispatch" else "advance" if name == "hdd_callback" else name]
        if name == "hdd_callback":
            yield name, va, retail, b"\x68" + struct.pack("<I", target)
            continue
        opcode = b"\xe8" if name in ("advance", "frame", "profile_context", "player_init") else b"\xe9"
        yield name, va, retail, opcode + struct.pack("<i", target - va - 5) + b"\x90" * (len(retail) - 5)


def _inspect(payload):
    _require(space.status(payload) != "foreign", "Foreign XBE allocator layout or digest")
    from . import nfl2k5_music_policy as policy
    _require(policy.status(payload) != "foreign", "Foreign music policy or collection metadata")
    image = XbeImage(payload)
    allocations = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    installed, selected = False, None
    labels = {k: 0 for k in HOOKS}
    if allocations:
        code, data, ro = sites(payload)
        code_bytes = image.read(code["va"], code["size"])
        ro_bytes = image.read(ro["va"], ro["size"])
        _require(image.read(data["va"], data["size"]) == bytes(data["size"]), "Nonzero on-disc playlist runtime state")
        if code_bytes != b"\xcc" * code["size"] or ro_bytes != bytes(ro["size"]):
            selected = _decode_ro(ro_bytes, ro["va"])
            expected, labels = code_for(code["va"], data["va"], ro["va"])
            _require(code_bytes == expected, "Foreign or mixed playlist code")
            installed = True
    for name, va, retail, replacement in edits(labels):
        _require(image.read(va, len(retail)) == (replacement if installed else retail),
                 f"Foreign or mixed playlist hook: {name}")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, (hook, retail) in HOOKS.items():
            if va <= hook and hook + len(retail) <= va + size:
                content[hook - va:hook - va + len(retail)] = retail
        _require(hashlib.sha256(content).hexdigest() == digest, f"Foreign playlist dependency {va:#x}")
    return ("applied", selected) if installed else ("retail", None)


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload):
    try:
        state, selected = _inspect(payload)
        return dict(status=state, records=list(selected.records) if selected else [],
                    enabled=list(selected.enabled) if selected else [], experimental=True,
                    runtime_witnessed=False, position_policy=POSITION_POLICY, all_modes_proved=False)
    except (ValueError, TypeError, KeyError, IndexError, struct.error) as exc:
        return dict(status="foreign", reason=str(exc), runtime_witnessed=False)


def reservations(payload):
    _require(status(payload) == "applied", "Playlist reservations require verified installed bytes")
    result = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    result += [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                    basis="pinned live routine/call: " + name)
               for name, (va, before) in HOOKS.items()]
    return result


def apply(payload, *, selection=None):
    state, previous = _inspect(payload)
    selected = previous if selection is None and previous is not None else (Selection() if selection is None else selection)
    _require(isinstance(selected, Selection), "Expected a playlist Selection")
    if state == "applied":
        _require(selected == previous, "Different playlist selection; rebuild from supported base")
        return payload, dict(status="already_applied", already_applied=True, changed_bytes=0,
                             runtime_witnessed=False, position_policy=POSITION_POLICY)
    allocated, allocation = (space.apply(payload, REQUESTS, scaleout=True)
                             if space.status(payload) == "retail" else (payload, {}))
    code, data, ro = sites(allocated)
    content, labels = code_for(code["va"], data["va"], ro["va"])
    installed, _ = space.install_code(allocated, OWNER, content)
    installed, _ = space.install_read_only(installed, OWNER, ro_for(selected, ro["va"]))
    image = XbeImage(installed)
    result = bytearray(installed)
    changes = []
    for name, va, before, after in edits(labels):
        at = image.offset(va, len(before))
        result[at:at + len(after)] = after
        changes.append(dict(label=name, va=hex(va), file_offset=hex(at), size=len(after),
                            before=before.hex(), after=after.hex()))
    sections = _sections(installed)
    touched = _section_for_offset(sections, image.offset(0x2801A0)).index
    for section in sections:
        if section.index == touched:
            result[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(result), section)
    result = bytes(result)
    _require(status(result) == "applied", "Playlist post-apply verification failed")
    return result, dict(status="applied", already_applied=False, edits=changes, allocation=allocation,
                        reservations=reservations(result), records=len(selected.records), enabled=len(selected.enabled),
                        code_bytes=len(assembly.CODE), budgets=dict(code=CODE_SIZE, data=DATA_SIZE, read_only=RO_SIZE),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        source_sha256=hashlib.sha256(payload).hexdigest(), result_sha256=hashlib.sha256(result).hexdigest(),
                        position_policy=POSITION_POLICY, experimental=True, runtime_witnessed=False,
                        all_modes_proved=False)

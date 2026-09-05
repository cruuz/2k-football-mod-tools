"""White star outlines at tagged players' feet (USA Xbox executable, xemu).

Beta 58 changed only FUN_00075d40. That is insufficient: FUN_000f9030
encodes ordinary CPU bodies as controller 8; FUN_000f9320 passes (user == 8)
in eax; FUN_000f8880 skips the controller model when eax is nonzero. Its
normal controller model is a circular ring, regardless of the resource name.

The fixed pass wraps the frame call at 0x64F21, keeps the retail circles and
their predicate unchanged, then draws a separate opaque white five-point
outline for every tagged active entity. It reads entity+0x3C -> record+0x53
bit 0 directly, independently of controller assignment and the nine-entry
replay/controller queue. The 22-entity bound is the physical array capacity.

FUN_00061730 -> FUN_000c3c60 copies all 21 dwords of each roster record into
0xB30C4C/0xB321A0. FUN_001d2620/001d27a0 installs these pointers at entity+0x3C.
The ROST relocator 0xE5E70 changes pointers only; the padding tag survives.

All mutable draw state is stack-local. Five small, pinned, unreferenced code
spans hold original instructions and immutable geometry. The controller
material is copied, made white/untextured and uncullable; the shared material
is never modified. See tools/player_star/runtime.S and ASTRA_STAR_FIX_REPORT.md.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
GATE_VA = 0x75D40
GATE_SIZE = 0x50
RETAIL_GATE = bytes.fromhex(
    "a150fce50085c0568bf17509a190fce50085c074378b460c8338ff75288bcee86c8e100085c0751d833e00741f"
    "a180ffe50085c0740f833db802e6000e7406807e2c067407b8010000005ec333c05ec3")
# Exact beta-58..60 predicate: recognized for explicit upgrade, never called applied.
LEGACY_GATE = bytes.fromhex("a150fce5000b0590fce5007442a180ffe5008b510c833aff7533833900741385c0742a833db802e6000e742180792c06751b8b513c85d2740ff64253017409803d2128ba00097205e9438e1000b001c3")
TAG_RECORD_OFFSET = 0x53
TAG_BIT = 1
PLAYER_RECORD_SIZE = 0x54
ENTITY_RECORD_OFFSET = 0x3C
ENTITY_LIST_VA = 0xE60268
ENTITY_LIMIT = 22
# Compatibility receipt key used by the roster writer; this is now the physical
# on-field bound, not a quota on tags or on the retail controller queue.
STAR_LIST_LIMIT = ENTITY_LIMIT
STAR_COUNT_VA = 0xBA2821
STAR_LIST_VA = 0xBA2824
RETAIL_STAR_LIST_LIMIT = 9
DRAW_CALL_VA = 0x64F21
RETAIL_DRAW_CALL = bytes.fromhex("e8fa430900")
RETAIL_DRAW_VA = 0xF9320
DRAW_READY_VA = 0xBA2818
DRAW_VISIBLE_VA = 0xBA281C
MATERIAL_VA = 0xBA28AC
CALL_SITES = ((0x7604A, bytes.fromhex("e8f1fcffff")),
              (0xF90AA, bytes.fromhex("e891ccf7ff85c0")))

CAVE_PINS = {
    0x372D40: '09f95f5f7227f5cc7ba846861bbd763a001b858ad10411298f5ed517758a4ad8',
    0x3DDD50: 'f6984ec8423041706c60868d6a059d2544c5e318b59af52a36d93080ebc71642',
    0x38B0D0: '00967d119728b8827fe63a07f631bffb62f14881b7b5c7be4beffa1c7962f168',
    0x2C9110: '7931044340b34b9b5424a04e511ced65e483e36a690061be7625c960c73801b8',
    0x31E650: '27ee7af3ecd76e1ceace682009c4fb62fef554159bbb90f52d5fdc1353c641c4',
}

# BEGIN GENERATED RUNTIME
SYMBOLS = {
    'frame_done': 0x372D9E,
    'frame_loop': 0x372D76,
    'frame_next': 0x372D98,
    'frame_return': 0x372DA0,
    'frame_visible': 0x372D69,
    'star_draw': 0x3DDD50,
    'star_frame': 0x372D40,
    'star_inset': 0x31E650,
    'star_points': 0x31E654,
    'star_position': 0x38B0D0,
    'star_vertex': 0x2C9110,
    'vertex_outer': 0x2C912D,
    'vertex_same_point': 0x2C9158,
}

# (VA, capacity, original generated code or immutable geometry)
CAVES = (
    (0x372D40, 118, bytes.fromhex(
        "e8db65d8ff833d1828ba00007452833d1c28ba00007449e864faceff85c07409e8cbabd0ff85c0743756578b356802e6"
        "00bf1600000085f67424837e480075188b463c85c07411f6405301740b837e04007405e8b8af06008b76304f75d85f5e"
        "c3"
    )),
    (0x3DDD50, 83, bytes.fromhex(
        "5589e553565783e4f081eca00000008b5e048b35ac28ba008d7c2420b920000000f3a5c7442438ffffffffc744245000"
        "00000081a42480000000fffffff0c744240400004040c744240c0000803fe92dd3faff"
    )),
    (0x38B0D0, 83, bytes.fromhex(
        "d98330010000d88330020000d80d84414e00d95c2410d98338010000d88338020000d80d84414e00d95c24148d442420"
        "6a00506a0631c9ba01000000e88f21caffbb54e63100bf16000000e9f0dff3ff"
    )),
    (0x2C9110, 106, bytes.fromhex(
        "d903d94304f7c7010000007410d80d50e63100d9c9d80d50e63100d9c9d8442414d95c2408d8442410d91c2489e1e82d"
        "39d6fff7c701000000740d83c30883ff037505bb54e631004f75b5e8a038d6ff8d65f45f5e5b5dc3"
    )),
    (0x31E650, 84, bytes.fromhex(
        "3d0a573f00000000000090c2aae09f41790ddcc1bff3884269feb1c1fc570142f11a28413b48294234ff684200000000"
        "000008423b4829c234ff6842fc5701c2f11a2841bff388c269feb1c1aae09fc1790ddcc1"
    )),
)
# END GENERATED RUNTIME

PATCHED_DRAW_CALL = b"\xe8" + struct.pack("<i", SYMBOLS['star_frame'] - DRAW_CALL_VA - 5)
# Pin both unchanged producer/consumer bodies, not just the former gate.
CONTEXT_HASHES = (
    (0xF9030, 735, 'dd1061ca291cf6defecbcbb80f1453051cbe6bfac056b06bb0aa90fd115db9fb'),
    (0xF9320, 420, '54ebe23ac6eb2065e3a40e36af05673f32e6e40fbd23ee4ba6db751fb50188f5'),
)
PINS = (*CALL_SITES,
        (0x64F18, bytes.fromhex("e823ea010085c07505")),  # replay camera branch before the hook
        (0x2CA70, bytes.fromhex("ff0584b2a6008b11a17cb2a6008910")),
        (0x2D2A0, bytes.fromhex("558bec5356578bf9e8b3eeffff")),
        (0x2CA00, bytes.fromhex("e87bffffff")),
        (0x61769, bytes.fromhex("e8f2240600")),
        (0x617A4, bytes.fromhex("e8b7240600")),
        (0xC3C70, bytes.fromhex("8d7a543bd78b34998bc2")))


class PlayerStarError(ValueError):
    """Foreign code or an incomplete star patch; no bytes are changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlayerStarError(message)


def _offset(payload: bytes, va: int) -> int:
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + va - section.virtual_address
    raise PlayerStarError(f"VA 0x{va:x} is in no file-backed section")


def _read(payload: bytes, va: int, size: int) -> bytes:
    off = _offset(payload, va)
    section = _section_for_offset(_sections(payload), off)
    _require(off + size <= section.raw_offset + section.raw_size, 'site crosses section boundary')
    result = payload[off:off + size]
    _require(len(result) == size, 'truncated site')
    return result


def sites() -> list[tuple[str, int, bytes]]:
    """Complete declared replacement spans, including unchanged cave padding."""
    return [('controller_gate', GATE_VA, RETAIL_GATE),
            ('star_frame_call', DRAW_CALL_VA, PATCHED_DRAW_CALL),
            *((f'star_runtime_{va:x}', va, code + b'\x90' * (size-len(code)))
              for va, size, code in CAVES)]


def status(payload: bytes) -> str:
    """retail / legacy (beta 58..60, upgradeable) / applied / foreign.

    Mixed or modified sites are foreign. 'applied' always means the complete
    new renderer. The protected build dispatcher needs the legacy upgrade arm
    described in WIRING_STAR.md when starting from an already patched disc.
    """
    try:
        if payload[:4] != b'XBEH' or struct.unpack_from('<I', payload, 0x104)[0] != IMAGE_BASE:
            return 'foreign'
        if any(_read(payload, va, len(pin)) != pin for va, pin in PINS):
            return 'foreign'
        if any(hashlib.sha256(_read(payload, va, size)).hexdigest() != pin
               for va, size, pin in CONTEXT_HASHES):
            return 'foreign'
        gate = _read(payload, GATE_VA, GATE_SIZE)
        call = _read(payload, DRAW_CALL_VA, 5)
        if gate == RETAIL_GATE and all(_read(payload, va, len(code)) == code for _, va, code in sites()):
            return 'applied'
        if call != RETAIL_DRAW_CALL or any(
                hashlib.sha256(_read(payload, va, size)).hexdigest() != CAVE_PINS[va]
                for va, size, _ in CAVES):
            return 'foreign'
        if gate == RETAIL_GATE:
            return 'retail'
        if gate == LEGACY_GATE:
            return 'legacy'
    except (PlayerStarError, ValueError, struct.error, IndexError):
        pass
    return 'foreign'


def read_settings(payload: bytes) -> dict[str, object]:
    state = status(payload)
    return {'status': state, 'renderer': 'white_star_outline' if state == 'applied' else 'none',
            'tag': 'roster record +0x53 bit 0' if state in ('applied', 'legacy') else 'none',
            'star_list_limit': ENTITY_LIMIT if state == 'applied' else 0,
            'retail_controller_capacity': RETAIL_STAR_LIST_LIMIT,
            'needs_upgrade': state == 'legacy'}


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    if state == 'applied':
        return payload, {'already_applied': True, 'edits': [], 'changed_bytes': 0, **read_settings(payload)}
    _require(state in ('retail', 'legacy'), f'player-star sites are {state}; refusing')
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, va, after in sites():
        off = _offset(payload, va)
        before = payload[off:off+len(after)]
        if before == after:
            continue
        buf[off:off+len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({'label': label, 'va': hex(va), 'file_offset': hex(off), 'bytes': len(after),
                      'before_sha256': hashlib.sha256(before).hexdigest(),
                      'after_sha256': hashlib.sha256(after).hexdigest()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d:d+20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == 'applied', 'post-apply verification failed')
    return patched, {'edits': edits, 'changed_bytes': sum(a != b for a, b in zip(payload, patched)),
                     'sections_repinned': sorted(touched), 'upgraded_from': state,
                     'controller_gate_restored': state == 'legacy',
                     'caves': [{'va': hex(va), 'bytes': size} for va, size, _ in CAVES],
                     'runtime_storage': 'stack only', **read_settings(patched)}

"""128 MB memory on stock xemu (K128) and the roster block in the extra heap. EXPERIMENTAL.

Why (research tracks R1 and R4, 2026-09-22; job b76-k1, 2026-09-23)
-------------------------------------------------------------------
xemu offers the Xbox 128 MB (``[sys] mem_limit = '128'``), but the retail 4627 kernel that xemu boots
is compiled for 64 MB: it never reads the RAM size, reports 64 MB and maps nothing above it. 2K5 itself
is ready for more: its arena init (``0x326E0``) asks the kernel for the RAM size and, on a machine with
more than 64 MB, takes a second region of up to 64 MB from the XAPI heap into ``0xB018B8/0xB018BC``.
Retail never uses that region.

K128 (R1's "late form", 226 bytes, two hooks) teaches the running kernel to manage 128 MB, in RAM only
(no BIOS or flash byte changes, stock xemu):

* hook 1, the XBE entry: guards, then ``MmNumberOfPhysicalPages = 0x8000`` so ``GlobalMemoryStatus``
  reports 128 MB, and on to the original entry (``0x16BD1``);
* hook 2, ``call k128_arena`` plus five NOPs in place of the 10-byte
  ``cmp dword ptr [0xB018E8], 0x4000000`` at ``0x327D1``, inside the arena init right after the game
  built its GPU-visible arena: 16 new page tables that continue the kernel's PFN database at
  ``0x84000000``, then the kernel's own ``MiAddPhysicalPages(0x4010, 0x8000)``. The hook then runs the
  replaced compare itself, so the ``jbe`` at ``0x327E1`` sees the retail flags.

Because the pages arrive after the arena exists, every retail address stays where it was (the XBE
image, the arena, the frame surfaces); the game's own >64 MB branch then takes a 63.0 MiB region (measured in the lab).

Guards (all must hold, or the stub does nothing and the game runs as a 64 MB title): the kernel build
is 4627 (through the title's own thunk slot of ordinal 324, ``0x4E3BA4``), ``NV_PFB_CSTATUS`` reads
``0x08000000`` (xemu is set to 128 MB), ``PDE[0x210]`` is empty, the ``MiAddPhysicalPages`` prologue
matches, and the page count is 0x4000 (phase 1) or 0x8000 (phase 2, which needs phase 1).

The roster heap (option ``roster_heap``): the first time the roster block is allocated
(``0xC1F00``, boot), a game heap is built over the >64 MB region (the game's own heap code
``0x48640``), and the roster block (0x91000 bytes, 0x92000 with the arena growth) comes from it
instead of the main heap. On a machine without the region (64 MB, or another kernel) the roster stays
in the main heap exactly as retail. The extra heap falls back to the main heap if it ever runs out.
With the roster heap, the in-game block (0x84EB0, game setup) is also capped at the 0x180000 bytes the game
ever carves from it (retail takes the largest free block minus 128 KB and leaves the rest as dead slack), so
the room the roster frees stays free in the main heap during the game. At 64 MB the cap sees no region and
keeps the retail size.

Nothing GPU-visible moves: the region is CPU-side virtual memory above 64 MB, and the roster block is
record data the CPU copies (R4 2.5: its only I/O is a read into a temporary block of the current heap
and a byte copy).

Evidence: PROVED IN GAME (lab) for K128's kernel side by R1 (k128, k128r, k128late, k128late2), and
PROVED OFFLINE under Unicorn on the real 4627 kernel. The roster heap's live fault and its fix are in
``K1_EXTRA_HEAP_2026-09-23.md`` (job b76-k1). Not witnessed on a console, where it cannot run: a
console has 64 MB and a different kernel, and the guards keep the stub asleep there.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_k128"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 0x400
# Code only: the RW pages are full in the complete owner union, and the roster heap needs no state of its
# own (the heap control block's "HEAP" magic at the region start says it is built).
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)

# --- the XBE header entry point -------------------------------------------------------------------
ENTRY_FIELD = 0x128                  # file offset of the XOR-encoded entry point
RETAIL_KEY = 0xA8FC57AB              # the retail XBE entry key (the Complex 4627 kernel is retail)
RETAIL_ENTRY = 0x00016BD1            # XAPI mainCRTStartup


def encode_entry(va: int) -> bytes:
    return struct.pack("<I", (va ^ RETAIL_KEY) & 0xFFFFFFFF)


def decode_entry(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, ENTRY_FIELD)[0] ^ RETAIL_KEY


# --- the 4627 kernel (read or written by the stub; pinned for the tests and the report) ----------
KRNL_VERSION_THUNK = 0x004E3BA4      # the title's thunk slot of XboxKrnlVersion (ordinal 324)
NV_PFB_CSTATUS = 0xFD10020C          # the RAM size xemu reports (0x08000000 at 128 MB)
PDE_210 = 0xC0300840                 # page-directory self-map entry for 0x84000000
NEW_TABLES_VA = 0xC0210000           # the 16 new page tables through the self-map
MI_ADD_PHYSICAL_PAGES = 0x8001F91A   # stdcall (start, end)
MI_ADD_PROLOGUE = 0x24748B56         # push esi; mov esi,[esp+..]
MM_NUMBER_OF_PHYSICAL_PAGES = 0x8003B2D4
CONTIGUOUS_USAGE = 0x8003AB64        # AllocatedPagesByUsage[Contiguous]
FIRST_ADDED_PFN, LAST_PFN = 0x4010, 0x8000

# --- the game ------------------------------------------------------------------------------------
ARENA_INIT_VA = 0x000326E0
DWTOTALPHYS_VA = 0x00B018E8          # MEMORYSTATUS.dwTotalPhys the arena init stored
DEVKIT_BASE_VA = 0x00B018B8          # the >64 MB region (written only by the arena init's devkit branch)
DEVKIT_END_VA = 0x00B018BC
MAIN_HEAP = 0x00B04E24               # the main heap control block (0x38FB0 returns it)
MAIN_HEAP_ACCESSOR = 0x00038FB0      # mov eax, 0xB04E24 ; ret
HEAP_INIT = 0x00048640               # fastcall(ecx = control, edx = start), [esp+4] = size; ret 4
HEAP_FALLBACK = 0x8C                 # control +0x8C: the heap 0x48700 retries on
HEAP_MAGIC_OFFSET, HEAP_MAGIC = 0x98, 0x50414548   # "HEAP", written by 0x48640
HEAP_CONTROL_BYTES = 0x100           # the control block sits at the region start
MIN_REGION = 0x200000
ROSTER_SETUP_VA = 0x000C1F00         # boot: registers 'ROST' and allocates the roster block

HOOK2_VA = 0x000327D1
RETAIL_HOOK2 = bytes.fromhex("813de818b00000000004")    # cmp dword ptr [0xb018e8], 0x4000000
ROSTER_SITE_VA = 0x000C1F37
RETAIL_ROSTER_SITE = bytes.fromhex("e87470f7ff")        # call 0x38fb0 (the main heap)
# The in-game block (0x84EB0, called once from game setup 0x64710 with ecx = 0x180000, edx = 0x20000) takes the
# main heap's largest free block minus 128 KB, but only ever carves min(block, 0x180000) of it (0xB6162C; every
# consumer, 0x84C30, 0x84CC0, 0x125700, is bounded by it). With the roster block moved out, the block would
# swallow the freed room as dead slack; the cap keeps it at 0x180000 while the extra region exists.
INGAME_BLOCK_VA = 0x00084EB0
CAP_SITE_VA = 0x00084EC2
RETAIL_CAP_SITE = bytes.fromhex("2bc785c0a31816b600")   # sub eax,edi; test eax,eax; mov [0xB61618],eax
INGAME_BLOCK_SIZE_VA = 0x00B61618

# R1's K128-late product stubs, verbatim (R1_patches/k128_late_stub.s, 226 bytes):
#   +0x00 k128_entry  pushad/pushfd; guards; count 0x4000 or 0x8000 -> 0x8000; popfd/popad;
#                     push 0x16bd1; ret
#   +0x2E k128_arena  pushad/pushfd; guards and count 0x8000; cli; PDE[0x210..0x21f] =
#                     0x04000000+j*0x1000|0x67; zero the 16 tables; table 0 entries 0..15 map the
#                     tables themselves (|0x463); reload cr3; MiAddPhysicalPages(0x4010, 0x8000);
#                     count = 0x8000; Contiguous += 16; popfd/popad; the replaced cmp; ret
#   +0xB5 guards      ZF=1 when build 4627, CSTATUS 0x08000000, PDE[0x210] == 0 and the prologue hold
K128_STUBS = bytes.fromhex(
    "609ce8ae000000751da1d4b203803d0040000074073d00800000750ac705d4b20380008000009d6168d16b0100c3"
    "609ce8800000007571813dd4b20380008000007565fabf400830c0b867000004b910000000ab0500100000e2f8"
    "bf000021c031c0b900400000f3abbf000021c0b863040004b910000000ab0500100000e2f80f20d80f22d86800"
    "8000006810400000b81af90180ffd0c705d4b2038000800000830564ab0380109d61813de818b00000000004c3"
    "a1a43b4e00668178041312751f813d0c0210fd000000087513833d400830c000750a813d1af90180568b7424c3")
K128_STUBS_SHA256 = "bdee5f7ebb540344cd67c84d25bc5c5335ed88e413d842f643793e03580e5c54"
ENTRY_OFFSET, ARENA_OFFSET, GUARDS_OFFSET = 0x00, 0x2E, 0xB5
ENTRY_PUSH_OFFSET = 0x28             # 68 d1 6b 01 00: push 0x16bd1 (the original entry)
assert len(K128_STUBS) == 226 and hashlib.sha256(K128_STUBS).hexdigest() == K128_STUBS_SHA256
assert K128_STUBS[ENTRY_PUSH_OFFSET:ENTRY_PUSH_OFFSET + 5] == b"\x68" + struct.pack("<I", RETAIL_ENTRY)
assert K128_STUBS[ARENA_OFFSET - 1] == 0xC3 and K128_STUBS[GUARDS_OFFSET - 1] == 0xC3

HEAP_OFFSET = 0x100                  # xheap_pick, when the roster heap is on
CAP_OFFSET = 0x180                   # the in-game block cap, when the roster heap is on
EARLY_OFFSET = 0x1A0                 # the early entry, when the early form is on
REQUIRE_OFFSET = 0x200               # the "needs 128 MB" entry (tools/k128/require_guard.S)
OPTIONS_OFFSET = CODE_SIZE - 4       # the option word the installed code carries
OPT_K128, OPT_ROSTER_HEAP, OPT_EARLY, OPT_REQUIRE = 0x1, 0x2, 0x4, 0x8
# The "needs 128 MB" entry, assembled from tools/k128/require_guard.S (as --32; objcopy -O binary -j .text). It runs
# phase 1 like k128_entry; when the machine will not get 128 MB (the guards fail, or the page count is not 0x4000 or
# 0x8000) and 128 MB is not already managed, it takes an 8 MB contiguous buffer below 32 MB (MmAllocateContiguousMemoryEx
# through the title's import), scans it out (NV_PCRTC_START; a 32-bit pitch for the mode's width, CR01 -> CR13/CR19; CR28 32
# bpp; the attribute display bit; SR01 screen on), draws "THIS BUILD NEEDS 128 MB / SET XEMU SYSTEM MEMORY / TO 128
# MB" and stops in a hlt loop instead of starting the game. Otherwise it continues exactly as k128_entry does (and,
# with the early form, runs k128_arena at once), reading the option word at +0x3FC.
REQUIRE_CODE = bytes.fromhex(
    "609ce8000000005de8a8feffff753fa1d4b203803d0040000074073d00800000752cc705d4b2038000800000f685f501"
    "000004740d9d61e8f2fdffff68d16b0100c39d6168d16b0100c3fbf4ebfd813dd4b2038000800000750c813d400830c0"
    "6700000474c66a046a0068ffffff016a006800008000ff15a43c4e0085c074ca89c625ffffff03a3000860fdbad41360"
    "fdc602010fb65a0143c1e30589d8c1e803c60213884201c1e80324e0c60219884201c60228804a01038a4206c642ec20"
    "bac4030cfdc60201806201df89f7b90000200031c0f3ab8d95a30100000fb70285c00f8462ffffff0fb74a020fafc301"
    "f08d3c880fb64a0483c2050fb602425156578db5440100008d048001c66a0559ac57516a0759d0e8731b57515083c8ff"
    "6a0459890789470489470889470c01dfe2f158595f8d3c9fe2dc595f83c710e2cf5f5e5983c760e2b2eb920000000000"
    "01017f01017f0808087f00417f410046494949317f494949363f4040403f7f404040407f4141221c7f0408107f7f4949"
    "49417f021c027f631408146307087008073e4141413e7f0919294600427f400042615149463649494936b4002c001701"
    "02030400050603070800090a0a080400101112000b05e400380016040a01000c0a0b0600040d04010a0b000b0a0b0e0f"
    "0d1401d40009010e00101112000b050000"
)
REQUIRE_CODE_SHA256 = "df6650849510abd7f8ed719c30212c9a906615baa07ffefb3a8413ad4a91e573"
REQUIRE_HALT_OFFSET = REQUIRE_OFFSET + 0x4B      # the hlt of the stop loop
assert len(REQUIRE_CODE) == 497 and hashlib.sha256(REQUIRE_CODE).hexdigest() == REQUIRE_CODE_SHA256
assert REQUIRE_CODE[REQUIRE_HALT_OFFSET - REQUIRE_OFFSET:REQUIRE_HALT_OFFSET - REQUIRE_OFFSET + 3] == b"\xf4\xeb\xfd"
MM_PAGES = 0x8003B2D4                # MmNumberOfPhysicalPages (the STICKY section)

UI_LABEL = "128 MB memory (K128, xemu set to 128 MB)"
ROSTER_HEAP_LABEL = "Roster block in the extra memory"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the Xbox kernel the game boots with manages 64 MB, even when xemu's "
    "System memory is set to 128 MB. Patch: a small startup patch teaches it the upper 64 MB after the game has "
    "built its graphics memory, so every retail address stays in place, and the game's own >64 MB code then takes "
    "a 63 MB extra region. Needs xemu set to 128 MB (xemu.toml: [sys] mem_limit = '128'); at 64 MB, or on any "
    "other kernel, the patch stays asleep and the game runs as retail. A disc that also has the Guardian overlay, "
    "16 reserves or the extra created teams needs the 128 MB: without it the disc stops at startup with a message "
    "saying so, instead of failing at the pregame intro. xemu only; a console has 64 MB.")
ROSTER_HEAP_HELP = (
    "EXPERIMENTAL / UNWITNESSED. Needs the 128 MB option. Retail: the roster block (580 KB, the arena that 16 "
    "reserves and extra created teams grow) sits in the main heap, and each game's in-game block takes all but "
    "128 KB of what is free when the game starts. Patch: a game heap over the extra region takes the roster block, "
    "which gives the menus and the game load that much more room, and the in-game block stops at the 1.5 MB the "
    "game uses, so the freed room stays free during the game. Without the extra region everything stays retail.")
EARLY_LABEL = "Bigger graphics memory (K128 early form)"
EARLY_HELP = (
    "EXPERIMENTAL / UNWITNESSED. Needs the 128 MB option. Retail: the game's graphics memory is 46.7 MB, all "
    "below 64 MB. Patch: the upper 64 MB is added as the game starts instead of after it has built its graphics "
    "memory; the Xbox kernel then moves the game's program pages above 64 MB to make room, and the graphics "
    "memory grows to 61.6 MB, room for larger textures. With the roster heap on, the in-game block's cap keeps "
    "that room free during the game. The game's addresses stay the same; only where its program pages sit "
    "changes. At 64 MB it stays asleep. xemu only.")
BUILD_CAPTION = UI_LABEL


class K128Error(ValueError):
    """Unsupported, foreign, mixed or differently configured installation."""


def _require(condition, message):
    if not condition:
        raise K128Error(message)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def hook2_bytes(code_va: int) -> bytes:
    return b"\xe8" + _rel32(HOOK2_VA + 5, code_va + ARENA_OFFSET) + b"\x90" * 5


def roster_site_bytes(code_va: int) -> bytes:
    return b"\xe8" + _rel32(ROSTER_SITE_VA + 5, code_va + HEAP_OFFSET)


def heap_pick_code(code_va: int) -> bytes:
    """xheap_pick: replaces ``call 0x38fb0`` at 0xC1F37 (the roster block's heap). eax = the heap.

        mov  eax, [0xB018B8]         ; the game's >64 MB region, if the arena init took one
        test eax, eax
        jz   main                    ; no region (64 MB, another kernel): the main heap, as retail
        cmp  dword [eax+0x98], 'HEAP'
        je   done                    ; built on an earlier call
        mov  ecx, [0xB018BC]
        sub  ecx, eax
        cmp  ecx, 0x200000
        jb   main                    ; too small to be worth a heap
        sub  ecx, 0x100
        push ecx                     ; size (0x48640 pops it)
        lea  edx, [eax+0x100]        ; heap start; the control block sits at the region start
        mov  ecx, eax
        call 0x48640                 ; the game's own heap init (writes 'HEAP' at +0x98)
        mov  eax, [0xB018B8]
        mov  dword [eax+0x8C], 0xB04E24   ; if it ever runs out, 0x48700 retries on the main heap
      done:
        ret
      main:
        mov  eax, 0xB04E24
        ret

    The region is a fresh XAPI heap block the game allocates at boot and retail never touches, so the
    magic cannot be there before the first call. Only eax, ecx and edx change (the call site's next
    instructions overwrite ecx and edx); 0x48640 keeps ebx, esi, edi and ebp.
    """

    va = code_va + HEAP_OFFSET
    code = bytearray()
    code += b"\xa1" + struct.pack("<I", DEVKIT_BASE_VA)   # mov eax, [0xB018B8]
    code += b"\x85\xc0"                                   # test eax, eax
    jz_at = len(code); code += b"\x74\x00"                # jz main
    code += b"\x81\xb8" + struct.pack("<I", HEAP_MAGIC_OFFSET) + struct.pack("<I", HEAP_MAGIC)  # cmp [eax+0x98], 'HEAP'
    je_at = len(code); code += b"\x74\x00"                # je done
    code += b"\x8b\x0d" + struct.pack("<I", DEVKIT_END_VA)  # mov ecx, [0xB018BC]
    code += b"\x2b\xc8"                                   # sub ecx, eax
    code += b"\x81\xf9" + struct.pack("<I", MIN_REGION)   # cmp ecx, 0x200000
    jb_at = len(code); code += b"\x72\x00"                # jb main
    code += b"\x81\xe9" + struct.pack("<I", HEAP_CONTROL_BYTES)  # sub ecx, 0x100
    code += b"\x51"                                       # push ecx
    code += b"\x8d\x90" + struct.pack("<I", HEAP_CONTROL_BYTES)  # lea edx, [eax+0x100]
    code += b"\x8b\xc8"                                   # mov ecx, eax
    code += b"\xe8" + _rel32(va + len(code) + 5, HEAP_INIT)       # call 0x48640
    code += b"\xa1" + struct.pack("<I", DEVKIT_BASE_VA)   # mov eax, [0xB018B8]
    code += b"\xc7\x80" + struct.pack("<I", HEAP_FALLBACK) + struct.pack("<I", MAIN_HEAP)
    done = len(code); code += b"\xc3"                     # ret
    main = len(code)
    code += b"\xb8" + struct.pack("<I", MAIN_HEAP)        # mov eax, 0xB04E24
    code += b"\xc3"                                       # ret
    for at, target in ((jz_at, main), (je_at, done), (jb_at, main)):
        rel = target - (at + 2)
        _require(-128 <= rel <= 127, "short jump out of range")
        code[at + 1] = rel & 0xFF
    return bytes(code)


def cap_code(code_va: int) -> bytes:
    """The in-game block cap: replaces the 9 bytes at 0x84EC2 (a call plus four NOPs).

        sub  eax, edi                ; block = largest free - 0x20000 (retail)
        cmp  dword [0xB018B8], 0     ; no extra region (64 MB, another kernel): retail size
        je   store
        cmp  eax, esi                ; esi = 0x180000, the most the game ever carves from the block
        jle  store
        mov  eax, esi
      store:
        mov  [0xB61618], eax
        test eax, eax                ; the flags the retail jle at 0x84ECB reads
        ret

    Only eax and the flags change, as in the retail bytes it replaces.
    """

    code = bytearray()
    code += b"\x2b\xc7"                                                  # sub eax, edi
    code += b"\x83\x3d" + struct.pack("<I", DEVKIT_BASE_VA) + b"\x00"  # cmp dword [0xB018B8], 0
    je_at = len(code); code += b"\x74\x00"                               # je store
    code += b"\x3b\xc6"                                                  # cmp eax, esi
    jle_at = len(code); code += b"\x7e\x00"                              # jle store
    code += b"\x8b\xc6"                                                  # mov eax, esi
    store = len(code)
    code += b"\xa3" + struct.pack("<I", INGAME_BLOCK_SIZE_VA)            # mov [0xB61618], eax
    code += b"\x85\xc0\xc3"                                              # test eax, eax ; ret
    for at in (je_at, jle_at):
        code[at + 1] = (store - (at + 2)) & 0xFF
    return bytes(code)


def cap_site_bytes(code_va: int) -> bytes:
    return b"\xe8" + _rel32(CAP_SITE_VA + 5, code_va + CAP_OFFSET) + b"\x90" * 4


def options_word(*, roster_heap: bool, early: bool = False, require: bool = False) -> int:
    _require(type(roster_heap) is bool and type(early) is bool and type(require) is bool,
             "roster_heap, early and require must be booleans")
    return (OPT_K128 | (OPT_ROSTER_HEAP if roster_heap else 0) | (OPT_EARLY if early else 0)
            | (OPT_REQUIRE if require else 0))


def early_code(code_va: int) -> bytes:
    """The early entry: phase 1 (the page count, same guards and sticky-count rule as k128_entry), then the
    existing k128_arena phase 2 at once (its own guards; the compare it replays is harmless here), then the
    retail entry. The late form's order, count first and pages second, is the one proved in the lab."""

    at = code_va + EARLY_OFFSET
    body = bytearray(b"\x60\x9c")                                              # pushad; pushfd
    body += b"\xe8" + _rel32(at + len(body) + 5, code_va + GUARDS_OFFSET)       # call guards (ZF: G1-G4 hold)
    done_jumps = [len(body)]
    body += b"\x75\x00"                                                         # jne done
    body += b"\xa1" + struct.pack("<I", MM_PAGES)                               # mov eax, [MmNumberOfPhysicalPages]
    body += b"\x3d" + struct.pack("<I", 0x4000) + b"\x74\x07"                  # cmp eax, 0x4000; je set
    body += b"\x3d" + struct.pack("<I", 0x8000)                                 # cmp eax, 0x8000 (sticky)
    done_jumps.append(len(body))
    body += b"\x75\x00"                                                         # jne done
    body += b"\xc7\x05" + struct.pack("<II", MM_PAGES, 0x8000)                  # set: count = 0x8000
    body += b"\x9d\x61"                                                         # popfd; popad
    body += b"\xe8" + _rel32(at + len(body) + 5, code_va + ARENA_OFFSET)        # call k128_arena (phase 2 now)
    body += b"\x68" + struct.pack("<I", RETAIL_ENTRY) + b"\xc3"                 # push 0x16BD1; ret
    done = len(body)
    body += b"\x9d\x61" + b"\x68" + struct.pack("<I", RETAIL_ENTRY) + b"\xc3"  # done: popfd; popad; retail entry
    for j in done_jumps:
        body[j + 1] = done - (j + 2)
    return bytes(body)


def code_for(code_va: int, flags: int) -> bytes:
    _require(flags & ~(OPT_K128 | OPT_ROSTER_HEAP | OPT_EARLY | OPT_REQUIRE) == 0 and flags & OPT_K128,
             "unknown K128 options")
    out = bytearray(b"\xcc" * CODE_SIZE)
    out[0:len(K128_STUBS)] = K128_STUBS
    if flags & OPT_ROSTER_HEAP:
        pick = heap_pick_code(code_va)
        _require(HEAP_OFFSET + len(pick) <= OPTIONS_OFFSET, "roster heap code exceeds its allocation")
        out[HEAP_OFFSET:HEAP_OFFSET + len(pick)] = pick
        _require(HEAP_OFFSET + len(pick) <= CAP_OFFSET, "roster heap pick overlaps the in-game block cap")
        cap = cap_code(code_va)
        out[CAP_OFFSET:CAP_OFFSET + len(cap)] = cap
        _require(CAP_OFFSET + len(cap) <= EARLY_OFFSET, "in-game block cap overlaps the early entry")
    if flags & OPT_EARLY:
        early = early_code(code_va)
        _require(EARLY_OFFSET + len(early) <= OPTIONS_OFFSET, "early entry exceeds its allocation")
        out[EARLY_OFFSET:EARLY_OFFSET + len(early)] = early
    if flags & OPT_REQUIRE:
        _require(REQUIRE_OFFSET + len(REQUIRE_CODE) <= OPTIONS_OFFSET, "the 128 MB entry exceeds its allocation")
        out[REQUIRE_OFFSET:REQUIRE_OFFSET + len(REQUIRE_CODE)] = REQUIRE_CODE
    struct.pack_into("<I", out, OPTIONS_OFFSET, flags)
    return bytes(out)


def allocations(payload: bytes) -> dict:
    return {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}


def sites(code_va: int, flags: int) -> list[tuple[str, int, bytes, bytes]]:
    """Pinned .text sites (the header entry is handled separately: it is not in a section)."""

    # the early form adds the pages at the entry, so 0x327D1 stays retail
    out = [] if flags & OPT_EARLY else [("k128_arena_hook", HOOK2_VA, RETAIL_HOOK2, hook2_bytes(code_va))]
    if flags & OPT_ROSTER_HEAP:
        out.append(("roster_heap_pick", ROSTER_SITE_VA, RETAIL_ROSTER_SITE, roster_site_bytes(code_va)))
        out.append(("ingame_block_cap", CAP_SITE_VA, RETAIL_CAP_SITE, cap_site_bytes(code_va)))
    return out


def entry_offset(flags: int) -> int:
    if flags & OPT_REQUIRE:
        return REQUIRE_OFFSET          # it runs the early phase itself when the early form is on
    return EARLY_OFFSET if flags & OPT_EARLY else ENTRY_OFFSET


def _entry_state(payload: bytes, code_va: int | None, flags: int = OPT_K128) -> str:
    entry = decode_entry(payload)
    if entry == RETAIL_ENTRY:
        return "retail"
    if code_va is not None and entry == code_va + entry_offset(flags):
        return "applied"
    return "foreign"


def _owned_state(payload: bytes):
    found = allocations(payload) if space.status(payload) == "applied" else {}
    image = XbeImage(payload)
    if not found:
        _require(_entry_state(payload, None) == "retail", "entry moved without a K128 allocation")
        _require(image.read(HOOK2_VA, len(RETAIL_HOOK2)) == RETAIL_HOOK2, "arena hook without a K128 allocation")
        _require(image.read(ROSTER_SITE_VA, 5) == RETAIL_ROSTER_SITE, "roster site without a K128 allocation")
        _require(image.read(CAP_SITE_VA, 9) == RETAIL_CAP_SITE, "in-game block site without a K128 allocation")
        return "retail", None, None
    _require(set(found) == {"code"}, "foreign K128 allocation")
    code = found["code"]
    _require((code["size"], code["align"]) == (CODE_SIZE, 16), "foreign K128 allocation")
    blob = image.read(code["va"], CODE_SIZE)
    if blob == b"\xcc" * CODE_SIZE:
        _require(_entry_state(payload, code["va"]) == "retail", "entry moved with an empty K128 allocation")
        _require(image.read(HOOK2_VA, len(RETAIL_HOOK2)) == RETAIL_HOOK2, "arena hook with an empty allocation")
        _require(image.read(ROSTER_SITE_VA, 5) == RETAIL_ROSTER_SITE, "roster site with an empty allocation")
        _require(image.read(CAP_SITE_VA, 9) == RETAIL_CAP_SITE, "in-game block site with an empty allocation")
        return "retail", found, None
    flags = struct.unpack_from("<I", blob, OPTIONS_OFFSET)[0]
    _require(blob == code_for(code["va"], flags), "foreign K128 code or options")
    _require(_entry_state(payload, code["va"], flags) == "applied", "K128 code without its entry hook")
    edits = sites(code["va"], flags)
    _require(not edits or rdata.status(payload, edits) == "applied", "mixed K128 hooks")
    if flags & OPT_EARLY:
        _require(image.read(HOOK2_VA, len(RETAIL_HOOK2)) == RETAIL_HOOK2, "arena hook with the early form")
    if not flags & OPT_ROSTER_HEAP:
        _require(image.read(ROSTER_SITE_VA, 5) == RETAIL_ROSTER_SITE, "roster site moved without the roster heap")
        _require(image.read(CAP_SITE_VA, 9) == RETAIL_CAP_SITE, "in-game block capped without the roster heap")
    return "applied", found, flags


def status(payload: bytes) -> str:
    try:
        return _owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        return {"status": state, "k128": False, "roster_heap": False, "early": False, "require_128": False}
    flags = _owned_state(payload)[2]
    return {"status": state, "k128": True, "roster_heap": bool(flags & OPT_ROSTER_HEAP),
            "early": bool(flags & OPT_EARLY), "require_128": bool(flags & OPT_REQUIRE)}


def roster_site_state(payload: bytes) -> str:
    """For owners whose guards cover 0xC1F00 (the arena growth): 'retail', 'k128' or 'foreign'."""

    try:
        got = XbeImage(payload).read(ROSTER_SITE_VA, 5)
        if got == RETAIL_ROSTER_SITE:
            return "retail"
        found = allocations(payload) if space.status(payload) == "applied" else {}
        if "code" in found and got == roster_site_bytes(found["code"]["va"]):
            return "k128"
    except (ValueError, IndexError, KeyError, TypeError, struct.error):
        pass
    return "foreign"


def _repin(buf: bytearray) -> None:
    for section in _sections(bytes(buf)):
        at = section.header_offset + 36
        buf[at:at + 20] = section_digest(bytes(buf), section)


def apply(payload: bytes, *, roster_heap: bool = False, early: bool = False,
          require: bool = False) -> tuple[bytes, Mapping[str, object]]:
    flags = options_word(roster_heap=roster_heap, early=early, require=require)
    state = status(payload)
    _require(state != "foreign", "foreign or mixed K128 executable; refusing")
    common = {"owner": OWNER, "experimental": True, "k128": True, "roster_heap": roster_heap, "early": early,
              "require_128": require,
              "needs": "xemu System memory 128 MB ([sys] mem_limit = '128'); asleep at 64 MB",
              "stub_bytes": len(K128_STUBS), "stub_sha256": K128_STUBS_SHA256}
    if state == "applied":
        _require(_owned_state(payload)[2] == flags, "K128 options differ; rebuild from the original")
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if space.status(payload) == "retail":
        payload, _ = space.apply(payload, REQUESTS, scaleout=True)
    found = allocations(payload)
    _require(set(found) == {"code"}, "reserve the K128 allocation union first")
    code_va = found["code"]["va"]
    _require(decode_entry(payload) == RETAIL_ENTRY, "the XBE entry point is not retail; refusing to chain")
    result, code_receipt = space.install_code(payload, OWNER, code_for(code_va, flags))
    edits = sites(code_va, flags)          # none for the early form without the roster heap
    result, receipt = (rdata.apply(result, edits, OWNER) if edits
                       else (result, {"already_applied": False, "edits": [], "changed_bytes": 0}))
    buf = bytearray(result)
    buf[ENTRY_FIELD:ENTRY_FIELD + 4] = encode_entry(code_va + entry_offset(flags))
    _repin(buf)
    result = bytes(buf)
    _require(status(result) == "applied", "K128 postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **receipt, "changed_bytes": changed, "site_bytes": receipt.get("changed_bytes", 0),
                    "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(code_va),
                    "entry": {"before": hex(RETAIL_ENTRY), "after": hex(code_va + entry_offset(flags))},
                    "hooks": [{"name": name, "va": hex(va)} for name, va, _b, _a in sites(code_va, flags)],
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_k128 {status,apply} source.xbe [output.xbe] [--roster-heap] [--early]"""

    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=UI_LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
            p.add_argument("--roster-heap", action="store_true", help=ROSTER_HEAP_LABEL)
            p.add_argument("--early", action="store_true", help=EARLY_LABEL)
    args = parser.parse_args(argv)
    _require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload, roster_heap=args.roster_heap, early=args.early)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = {**read_settings(payload), "owner": OWNER, "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "UI_LABEL", "ROSTER_HEAP_LABEL", "HELP_TEXT", "ROSTER_HEAP_HELP",
           "EARLY_LABEL", "EARLY_HELP", "early_code",
           "K128Error", "apply", "status", "read_settings", "roster_site_state", "code_for", "sites",
           "heap_pick_code", "hook2_bytes", "roster_site_bytes", "encode_entry", "decode_entry"]


if __name__ == "__main__":
    raise SystemExit(main())

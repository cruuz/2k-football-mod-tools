"""On-demand modules (overlays), prototype: Career Home loads when MyCareer opens. EXPERIMENTAL, OFF by default.

Why (b778 xs1, Noah 10/22): "if it's possible to make the game infinite in size and just keep shoving things into it
and it still works, that is really the goal". Every feature so far is resident: its bytes are in a preloaded XBE
section, loaded at boot and kept for the whole session. An on-demand module is loaded only when its screen opens. The
design and its limits are in docs/mod_editor/overlay_modules.md; this module is the first, smallest real use of it.

The mechanism is the Xbox's own overlay loader. The retail executable already imports the kernel's ``XeLoadSection``
(ordinal 327, thunk 0x4E3BFC) and ``XeUnloadSection`` (328, 0x4E3C00): a section without the preload flag is not
read at boot; ``XeLoadSection(section header)`` commits its pages and reads its bytes from default.xbe on the disc,
with the kernel's own reference count. So a module is an XBE section, its integrity is the same section digest the
Studio seals, and no new file format or disc file is needed.

What this owner changes (only with Career Home installed):

* Career Home's section descriptor loses its preload flag (flags 0x07 -> 0x05). Its bytes, address and digest stay.
* Two 5/6-byte hooks in the native screen stack, both entries through which a screen becomes current:
  push (0x6E39A, after MyCareer's own dispatch prologue at 0x6E390) and replace (0x6E2E0). Pop-to (0x6E450) only
  returns to screens already on the stack and is not hooked.
* A gate (this owner's code, in the allocator pool): when the screen about to open is one of MyCareer's own
  descriptors (its RW state block, the M3 page) or Career Home's, and Career Home is not loaded yet, it calls
  ``XeLoadSection`` (up to three tries), records the attempt count, the last NTSTATUS and the load time (RDTSC
  cycles), and lets the screen open. If every try fails it cancels that screen change, exactly as MyCareer's own
  filter does when it returns no screen: the player stays on the menu he was on and can press A again. Nothing then
  points into an unloaded page.
* Every MyCareer route opens a MyCareer descriptor before the Apartment (Career Home) can show, so the section is
  in memory before any of its rows, title or handler is read. The load happens during that menu transition.
* The prototype never unloads (``XeUnloadSection`` is not called): after the first MyCareer visit the cost equals
  today's resident section. Unloading needs proof that no MyCareer screen is on the stack (see the doc).

Save files are untouched (Career Home stores nothing). The kernel call is the same at 64 and 128 MB.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_module_loader"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE, DATA_SIZE = 256, 32
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION = "On-demand Career Home (module loader, experimental)"
HELP_TEXT = ("EXPERIMENTAL prototype. Career Home is read from the disc when you open MyCareer instead of at boot, using "
             "the Xbox's own section loader. Nothing should look different. Off by default.")
XE_LOAD_SECTION = 0x004E3BFC        # kernel thunk slot, ordinal 327 (retail import)
XE_UNLOAD_SECTION = 0x004E3C00      # ordinal 328 (not called by the prototype)
PUSH_HOOK = ("screen_push", 0x0006E39A, bytes.fromhex("578bfa7d51"))        # push edi; mov edi, edx; jge 0x6E3F0
PUSH_FULL, PUSH_RESUME = 0x0006E3F0, 0x0006E39F
REPLACE_HOOK = ("screen_replace", 0x0006E2E0, bytes.fromhex("56578bfa6a05"))  # push esi; push edi; mov edi, edx; push 5
REPLACE_RESUME = 0x0006E2E6
TRIES = 3
PRELOAD = 0x02
# data block offsets
LOADED, FAIL, ATTEMPTS, CYCLES, STATUS, LOADS = 0, 1, 4, 8, 12, 16
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class ModuleLoaderError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ModuleLoaderError(message)


def ranges(payload):
    """The descriptor ranges that need Career Home: MyCareer's RW block, the M3 state page, Career Home itself."""
    from . import nfl2k5_xbe_space as space, nfl2k5_my_career_home as home
    rows = space.layout(payload)["allocations"]
    data = [r for r in rows if r["owner"] == "nfl2k5_my_career" and r["kind"] == "data"]
    require(len(data) == 1, "the module loader needs MyCareer's RW block")
    out = [(data[0]["va"], data[0]["size"]), (home.VA, home.SIZE)]
    m3 = [r for r in rows if r["owner"] == space.MYCAREER_M3_STATE_OWNER]
    if m3:
        out.append((m3[0]["va"], m3[0]["size"]))
    return out


def header_va(payload):
    from . import nfl2k5_xbe_space as space
    return 0x10000 + space.scale_music_slots(payload)[0]


def code_for(code_va, data_va, section_header, spans):
    from .nfl2k5_draft_ai import _Asm
    require(1 <= len(spans) <= 4, "range table")
    a = _Asm(code_va)
    d = lambda off: struct.pack("<I", data_va + off).hex()
    # gate_push: from 0x6E39A; [esp] = saved esi, flags = cmp [esi+0x100], 0x20
    a.b("9c")                                   # pushfd
    a.j32("e8", "check")
    a.b("803d" + d(FAIL) + "00")                # cmp byte [fail], 0
    a.j8("75", "cancel_push")
    a.b("9d")                                   # popfd
    a.b("578bfa")                               # push edi ; mov edi, edx
    a.j8("7c", "push_room")                     # jl: room left on the screen stack
    a.jmp_abs(PUSH_FULL)                        # jge 0x6E3F0 (retail: stack full)
    a.label("push_room")
    a.jmp_abs(PUSH_RESUME)
    a.label("cancel_push")
    a.b("9d5ec3")                               # popfd ; pop esi ; ret  (no screen change)
    a.label("gate_replace")                     # from 0x6E2E0 (function entry)
    a.j32("e8", "check")
    a.b("803d" + d(FAIL) + "00")
    a.j8("75", "cancel_replace")
    a.b("56578bfa6a05")                         # the replaced prologue
    a.jmp_abs(REPLACE_RESUME)
    a.label("cancel_replace")
    a.b("c3")
    a.label("check")                            # edx = descriptor; every register kept (pushad), flags not
    a.b("60")                                   # pushad
    a.b("c605" + d(FAIL) + "00")                # mov byte [fail], 0
    a.b("803d" + d(LOADED) + "00")              # cmp byte [loaded], 0
    a.j32("0f85", "done")
    a.b("be")                                   # mov esi, table
    a.items.append(("tableref",))
    a.b("bb" + struct.pack("<I", len(spans)).hex())   # mov ebx, count
    a.label("scan")
    a.b("8bc2")                                 # mov eax, edx
    a.b("2b06")                                 # sub eax, [esi]
    a.b("3b4604")                               # cmp eax, [esi+4]
    a.j8("72", "hit")                           # jb
    a.b("83c608")                               # add esi, 8
    a.b("4b")                                   # dec ebx
    a.j8("75", "scan")
    a.j32("e9", "done")
    a.label("hit")
    a.b("bb" + struct.pack("<I", TRIES).hex())  # mov ebx, tries
    a.label("try")
    a.b("0f31")                                 # rdtsc
    a.b("8bf8")                                 # mov edi, eax
    a.b("68" + struct.pack("<I", section_header).hex())   # push section header
    a.b("ff15" + struct.pack("<I", XE_LOAD_SECTION).hex())  # call [XeLoadSection] (stdcall)
    a.b("8bf0")                                 # mov esi, eax  (NTSTATUS)
    a.b("0f31")                                 # rdtsc
    a.b("2bc7")                                 # sub eax, edi
    a.b("a3" + d(CYCLES))                       # mov [cycles], eax
    a.b("ff05" + d(ATTEMPTS))                   # inc dword [attempts]
    a.b("8935" + d(STATUS))                     # mov [status], esi
    a.b("85f6")                                 # test esi, esi
    a.j8("7d", "ok")                            # jge: NT_SUCCESS
    a.b("4b")                                   # dec ebx
    a.j8("75", "try")
    a.b("c605" + d(FAIL) + "01")                # mov byte [fail], 1
    a.j8("eb", "done")
    a.label("ok")
    a.b("c605" + d(LOADED) + "01")              # mov byte [loaded], 1
    a.b("ff05" + d(LOADS))                      # inc dword [loads]
    a.label("done")
    a.b("61c3")                                 # popad ; ret
    a.label("table")
    # resolve the table address: assemble once to learn the label, then patch the mov esi immediate
    a.items = [it if it != ("tableref",) else bytes(4) for it in a.items]
    first = a.assemble()
    table_at = a.labels["table"]
    ref = first.index(bytes.fromhex("be00000000bb"))
    body = bytearray(first)
    body[ref + 1:ref + 5] = struct.pack("<I", code_va + table_at)
    for lo, size in spans:
        body += struct.pack("<II", lo, size)
    require(len(body) <= CODE_SIZE, "module loader gate exceeds its allocation")
    return bytes(body.ljust(CODE_SIZE, b"\xcc")), {name: code_va + at for name, at in a.labels.items()}


def sites(code_va=0):
    """The two hook edits. The gate's two entries are at fixed offsets of its code (no field before them depends on
    an address size), so they follow from the allocation VA alone."""
    replace_offset = code_for(0x1000000, 0x2000000, 0x10000, [(0, 1)])[1]["gate_replace"] - 0x1000000
    out = []
    for (name, va, before), target in ((PUSH_HOOK, code_va), (REPLACE_HOOK, code_va + replace_offset)):
        out.append((name, va, before, (b"\xe9" + struct.pack("<i", target - va - 5)).ljust(len(before), b"\x90")))
    return out


def canonical_context(payload, va, raw):
    """Another owner's pinned-context view: this owner's exact push hook reads as the retail bytes it replaced (the
    MyCareer and Contracts editor guards hash 0x6E390..). Anything else at the site is left for them to refuse."""
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER and r["kind"] == "code"]
    if len(rows) != 1:
        return raw
    out = bytearray(raw)
    for index, (_name, at, before) in enumerate((PUSH_HOOK, REPLACE_HOOK)):
        if va <= at and at + len(before) <= va + len(raw) and bytes(raw[at - va:at - va + len(before)]) == sites(rows[0]["va"])[index][3]:
            out[at - va:at - va + len(before)] = before
    return bytes(out)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER}
    require(set(rows) == {"code", "data"} and rows["code"]["size"] == CODE_SIZE and rows["data"]["size"] == DATA_SIZE,
            "missing or foreign module loader allocation")
    return rows["code"], rows["data"]


def _home_flags(payload):
    from . import nfl2k5_xbe_space as space
    return struct.unpack_from("<I", payload, space.scale_music_slots(payload)[0])[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space, nfl2k5_my_career_home as home
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    code = data = None
    if present:
        code, data = allocation(payload)
    edits = sites(code["va"] if code else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if code and raw == after else "foreign")
    if code:
        require(home.status(payload) == "applied", "the module loader needs Career Home")
        expected = code_for(code["va"], data["va"], header_va(payload), ranges(payload))[0]
        raw = image.read(code["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == expected else "foreign")
        flags = _home_flags(payload)
        states.add("applied" if flags == home.FLAGS & ~PRELOAD else "retail" if flags == home.FLAGS else "foreign")
    elif space.is_scaleout(payload) and space.has_home_section(payload):
        states.add("retail" if _home_flags(payload) == home.FLAGS else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign or mixed module loader state")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload):
    """Install after Career Home (and after every other late owner). Exact replay is a no-op."""
    from . import nfl2k5_xbe_space as space, nfl2k5_my_career_home as home
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    require(state != "foreign", "foreign/mixed module loader input; rebuild from the original")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0)
    require(space.is_scaleout(payload) and home.status(payload) == "applied", "install Career Home before the module loader")
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code, data = allocation(payload)
    body, labels = code_for(code["va"], data["va"], header_va(payload), ranges(payload))
    payload, _ = space.install_code(payload, OWNER, body)
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = sites(code["va"])
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"module loader site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    at = space.scale_music_slots(payload)[0]
    struct.pack_into("<I", buf, at, home.FLAGS & ~PRELOAD)   # Career Home: not read at boot
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(space.status(result) == "applied" and home.status(result) == "applied" and _recognize(result) == "applied",
            "module loader postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code["va"]), data_va=hex(data["va"]),
                        section_header=hex(header_va(result)), ranges=[(hex(a), b) for a, b in ranges(result)],
                        labels={k: hex(v) for k, v in labels.items()}, allocation=allocation_receipt,
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        edits=[dict(label=n, va=hex(v), before=o.hex(), after=w.hex()) for n, v, o, w in edits])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "DATA_SIZE", "PUSH_HOOK", "REPLACE_HOOK", "code_for", "sites", "ranges",
           "header_va", "allocation", "status", "apply"]

"""Skip resource payloads that do not fit, using the retail dispatcher's failure path.

DRCT, XDSP and SPCI are re-encoded within their 48-byte function extents.
PLAY uses its 116-byte tail after the load-mode call: test eax,eax replaces sub eax,0 and a memory
push replaces mov/push, leaving room for the same allocation check. Its two
borrowed playbook buffers retain their native paths. CACR, BANK and AUSB
check before their direct stream reads; _bin checks before even writing the
allocated header. CACR drops the now-unused EDI save and uses memory pushes
to fit its existing extent. No cave or new memory.

EAX=0 makes 0x438D0 skip [header+4] bytes and call 0x43A20. At EOF 0x43880
closes the stream and calls the context completion, including 0x1256D0's
intro-ready bit. No payload callback is queued and no resource is registered.
0xDC630 skips absent director registry slots; 0xDC930 returns zero candidates
without creating a running script. These are native paths, not simulated flags.

The zero-capacity heap initializer must also leave its bins empty and avoid
writing a free-block header at the boundary of its caller's allocation. The
90-byte tail is re-encoded in place, moving the existing zero test before the
header stores. Nonempty heap geometry, bin calculation and allocations stay
retail. This matters when pregame heap A consumes the whole managed block.

Native test harness: tests/mod_editor/resource_load_guard_probe.py.
"""
from __future__ import annotations

import hashlib
from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_resource_load_guard"
BUILD_CAPTION = "Skip unavailable presentation resources safely"
HELP_TEXT = ("When the presentation pool is full, skip resources that cannot be allocated "
             "and finish loading the context. Prevents the pregame NULL-read crash at 64 MB. "
             "Clips that fit load normally. Enabled in all SOFTDRINK presets.")

# Exact retail bytes, including each function's own alignment padding.
SITES = (
    ("XDSP", 0x165DC0,
        bytes.fromhex("56578bf28bf9e805daedff8b56048bc8e82b29eeff8b4e046a0068a05d1600518bd08bcfe8a76ff8ff5f5ec390909090"),
        bytes.fromhex("565789d689cfe805daedff8b560489c1e82b29eeff85c074148b4e046a0068a05d16005189c289f9e8a36ff8ff5f5ec3")),
    ("DRCT", 0x166730,
        bytes.fromhex("56578bf28bf9e895d0edff8b56048bc8e8bb1feeff8b4e046a006800671600518bd08bcfe83766f8ff5f5ec390909090"),
        bytes.fromhex("565789d689cfe895d0edff8b560489c1e8bb1feeff85c074148b4e046a0068006716005189c289f9e83366f8ff5f5ec3")),
    ("SPCI", 0x168890,
        bytes.fromhex("56578bf28bf9e835afedff8b56048bc8e85bfeedff8b4e046a006870881600518bd08bcfe8d744f8ff5f5ec390909090"),
        bytes.fromhex("565789d689cfe835afedff8b560489c1e85bfeedff85c074148b4e046a0068708816005189c289f9e8d344f8ff5f5ec3")),
    ("PLAY", 0x16661C,
        bytes.fromhex("83e800744448742548753eb901000000e8dfc8f7ffb9010000008bf0e8d3c8f7ffc7808033010000000000eb2d33c9e8c0c8f7ff33c98bf0e8b7c8f7ffc7808033010000000000eb11e866d1edff8b57048bc8e88c20eeff8bf08b47046a0068f0651600508bd68bcbe80667f8ff5f5e5bc39090"),
        bytes.fromhex("85c0744448742548753eb901000000e8e0c8f7ffb90100000089c6e8d4c8f7ffc7808033010000000000eb3131c9e8c1c8f7ff31c989c6e8b8c8f7ffc7808033010000000000eb15e867d1edff8b570489c1e88d20eeff85c0741589c66a0068f0651600ff770489f289d9e80467f8ff5f5e5bc3")),
    ("CACR", 0x453D0,
        bytes.fromhex("5356578bda8bf1e804dcffff85c074228b401085c0741b8b888800000085c97411e8dae3ffff8b53048bc8e830330000eb0fe8c9e3ffff8b53048bc8e8ef3200008b53048b7e048b0e6a0068a05304005257518bd08bcee8c43b00005f5e5bc3"),
        bytes.fromhex("535689d389cee805dcffff85c074228b401085c0741b8b888800000085c97411e8dbe3ffff8b530489c1e831330000eb0fe8cae3ffff8b530489c1e8f032000085c074186a0068a0530400ff7304ff7604ff3689c289f1e8c43b00005e5bc390")),
    ("BANK", 0x45500,
        bytes.fromhex("5356578bfa8bf1e844dcffff8bd8e8bde2ffff8b57048bc8e8e33100008b7f048b56048b0e5368805404005752518bd08bcee8b93a00005f5e5bc39090909090"),
        bytes.fromhex("53565789d789cee844dcffff89c3e8bde2ffff8b570489c1e8e331000085c0741a8b7f048b56048b0e53688054040057525189c289f1e8b53a00005f5e5bc390")),
    ("AUSB", 0x45940,
        bytes.fromhex("56578bfa8bf1e885deffff8b57048bc8e8ab2d00008b7f048b56048b0e6a0068205904005752518bd08bcee8803600005f5ec390909090909090909090909090"),
        bytes.fromhex("565789d789cee885deffff8b570489c1e8ab2d000085c0741b8b7f048b56048b0e6a00682059040057525189c289f1e87c3600005f5ec3909090909090909090")),
    ("_bin", 0x45D60,
        bytes.fromhex("568bf2578bf98b4e08890d6022b100817e10efbeedfe750d8b4604a36c22b1008b4614eb0cc7056c22b1000000000033c053a37022b1008d5c0810e830daffff8bd38bc8e857290000a35c22b1008b4e048908a16c22b10085c08b155c22b1005b741c8b357022b1008b0d6022b1002bd003d603d189156422b1008bf0eb0989156422b1008b76046a0068105d040089356822b1008b4f048b075651508bcfe8ec3100005f5ec3909090909090909090"),
        bytes.fromhex("5689d65789cf8b4e08890d6022b100817e10efbeedfe750d8b4604a36c22b1008b4614eb0cc7056c22b1000000000031c053a37022b1008d5c0810e830daffff89da89c1e857290000a35c22b10085c074598b4e048908a16c22b10085c08b155c22b1005b741c8b357022b1008b0d6022b10029c201f201ca89156422b10089c6eb0989156422b1008b76046a0068105d040089356822b1008b4f048b0756515089f9e8e83100005f5ec35b5f5ec390")),
    ("empty_heap", 0x48699,
        bytes.fromhex("33c93be9891e894e04896e08894e14894e18894e1c8bc57436f7c50000ffff740ac1fd108bc5b910000000f6c4ff7406c1f80883c108a8f07406c1f80483c104a80c7406c1f80283c102a8027401415f89748b085e5d5bc20400"),
        bytes.fromhex("31c989e839cd744b891e894e04896e08894e14894e18894e1cf7c50000ffff740ac1fd1089e8b910000000f6c4ff7406c1f80883c108a8f07406c1f80483c104a80c7406c1f80283c102a80274014189748b085f5e5d5bc20400")),
)

# Pins for the unchanged allocator, dispatch, completion and missing-clip paths.
GUARDS = (
    (0x166610, 7, "d021315c2d1112d7c6df07278b095e15f53b0107ab5a1e3663cf48ab5eb31a8a"),
    (0x438D0, 0xA6, "d03b5edd31b324f44f71bdc58545cfcdef4abd6807920142c98b2f7c358bb42e"),
    (0x43A20, 0x94, "9de52dd9d800aed4eb2d0721ed7c436f7747ccd660248f21db8d571a82ba534b"),
    (0x43880, 0x44, "a13e07259c5d864589639945432dd6f83d16cbd858a42e2e6e2e8de57632ec08"),
    (0x437D0, 0x6, "272b32f96ba721ba92f4ec6760073eff712f53f8c72642e6c62bce468c7bb5da"),
    (0x48700, 0x27, "2afa1c64c28563d908a6f69d13fc1944f151aa7fc7c9baf50e4ded284cf88d01"),
    (0x48640, 0x59, "e95c30014d731a42503447ffef9393f01c078727b825a5681e515e0f7b89351a"),
    (0x1256D0, 0x8, "d683f8aea31866e8c8d1a3e1cc185ecb31a63caea07edb57cc953df0bb9593a9"),
    (0xDC630, 0x7F, "4b1398ddb2e9563ec6d33c2543930b5a910032355b37c36df2985134313aba76"),
    (0xDC930, 0xD4, "116e923806419940441a637ee719fbf18f378c8b4dc9937a994d3f71342674dd"),
    (0xE2F10, 0x1E, "f29437853f6505385dc46b6a566b668360cc9d699ae1a6f56a3e21826e33b66e"),
)


def status(payload: bytes) -> str:
    try:
        mode_off = rdata.offset_of(payload, 0x166617)
        if payload[mode_off:mode_off+5] != bytes.fromhex("e8a433f8ff"):
            from . import nfl2k5_playbook_pair as pair
            if pair.status(payload) != "applied":
                return "foreign"
        for va, size, digest in GUARDS:
            off = rdata.offset_of(payload, va)
            if hashlib.sha256(payload[off:off + size]).hexdigest() != digest:
                return "foreign"
        return rdata.status(payload, SITES)
    except (ValueError, TypeError):
        return "foreign"


def verify(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        raise rdata.RdataSiteError(f"Resource allocation guards are {state}, not applied")
    return dict(status=state, loaders=[row[0] for row in SITES[:-1]], empty_heap_guard=True,
                runtime_witnessed=False, file_growth=0)


def apply(payload: bytes):
    state = status(payload)
    if state not in ("retail", "applied"):
        raise rdata.RdataSiteError("Resource allocation guard prerequisites are foreign or mixed")
    result, receipt = rdata.apply(payload, SITES, BUILD_CAPTION)
    return result, {**receipt, **verify(result), "owner": OWNER,
        "reservations": [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)),
                              size=len(before), basis="pinned live function extent; not a cave")
                         for _, va, before, _ in SITES]}

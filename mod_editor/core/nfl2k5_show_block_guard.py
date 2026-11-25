"""Keep the halftime and postgame shows and the replay system from using the show block at the same time.

Report (b81 played wild card witness, 2026-11-24): NYG at GB, CPU against CPU, 1-minute quarters, modern overtime.
After Green Bay's overtime touchdown the game stopped (bugcheck 0x1E, access violation at EIP 0x4865C writing
address 4): a NULL write inside the retail heap creator 0x48640.

The trigger (traced with breakpoints, b81 ot-crash w9j): with the 2025 overtime rules (nfl2k5_overtime,
``postseason_no_ties``) a playoff overtime period that ends with the trailing team on its first possession goes on into
another period. The retail period-end presentation does not know that rule: with the scores different in overtime it
runs the presentation command 0x1F7DF0 case 9 and loads the POSTGAME show, which then stays loaded (holding the block)
while the game plays the extra period. When the game really ends the postgame show is loaded a second time, 0xF6070
finds the block taken, and the loader builds its heap at address 0.

The show block (retail code throughout)
---------------------------------------
At boot 0xF5FE0 allocates one 0x148000-byte block ([0xB9E230]) and registers it as a free zone ([0xB9E234] = 1).
Two users take it with 0xF6070 and give it back with 0xF60A0:

* the show loader 0xDA4D0 (``halftime.iff`` from 0x9F8FC; ``postgame.iff`` from the presentation command 0x1F7DF0,
  case 9) builds a heap on the block (0xDA52D calls 0x48640) and loads two contexts into it; the show task
  (0xDB0F0, then 0xDA5D0 every frame) waits for both contexts (0xB73B04 = 2), starts the show and runs it to its end;
  the release 0xDA5A0 unloads them and gives the block back;
* the replay system 0x83F10 splits the block into two zones (0x83330 registers each with 0x12EF00); its release 0x83F70
  gives it back.

0xF6070 returns 0 when the block is taken (or missing). Neither user checks:

* the show loader then builds its heap at address 0: the crash above;
* the replay system registers a zone at address 0xA4000 (half the block's size), inside the game's code.

What this owner changes (in place: each routine within its own extent and alignment padding; no cave, no allocation)
---------------------------------------------------------------------------------------------------------------------
* 0xDA4D0: without a block the loader returns before the heap and the contexts; with one it records it first
  (0xB72ED0, which retail writes only here and never reads). So 0xB72ED0 says whether a show holds the block, also when
  a second load is skipped while the first show is still loaded (it keeps that show's block). The "show under way"
  flag 0xB72E80 is set before the take (retail sets it at the end), so a skipped show still counts as under way: the
  postgame presentation waits for it (script command 35, 0xDAD20; w10d stood on the stadium shot without it), and the
  release clears it.
* 0xDA5D0: the show task is done at once when the show holds no block, and it sets the halftime-done flag 0xB72C30
  (which the halftime show itself sets at its end through 0xCED30, and which game state 9 waits on at 0x158D33; the
  next game's setup clears it, 0xCE820). Without this a skipped show's task ran on whatever the previous show left
  (forced-flag witness w10a: the postgame presentation stood nine minutes before the end-of-game menu), and a skipped
  halftime show left halftime waiting for good (w10b, first guard: the referee shot until a button press did nothing).
  Room: the three identical exits share one (retail repeats ``mov eax, 1 / pop esi / ret``) and three ``mov [x], imm``
  stores go through EAX, which is free there.
* 0xDA5A0: the show is marked over first, then the contexts are unloaded and the block given back only when this show
  holds it, and 0xB72ED0 is cleared; a skipped or repeated release never gives away a block someone else holds.
* 0x1F7DF0 (presentation command 14): case 9 loads the postgame show only when the game state is 10 (over). Retail
  reaches case 9 only there; the 2025 overtime rules can reach it at a continued overtime period end (the trigger
  above), where it now loads nothing and the period-end presentation goes on to the next period. Cases 2, 3 and 4 are
  re-encoded shorter (``and [x], 0`` for ``mov [x], 0``, ``push 1 / pop ecx`` for ``mov ecx, 1``) to make room; the case
  table stays at 0x1F7E80 with the new case addresses.
* 0x83F10: the replay system marks itself active (0xB60A90, read only by its two releases) only once it got the
  block; without it, it registers no zone, and its release (0x83F70) gives nothing back.

With the block free, every path makes the same writes and calls as retail (Unicorn-checked).
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_show_block_guard"
BUILD_CAPTION = "Halftime and postgame show memory guard"
HELP_TEXT = ("Load the postgame show only when the game is over, and the halftime or postgame show only when its "
             "memory is free; keep instant replays out of the show's memory. Prevents the crash at the end of a "
             "playoff game whose overtime went on into another period. A retail crash path: no allocation.")

SHOW_BLOCK, SHOW_BLOCK_FREE = 0x00B9E230, 0x00B9E234
SHOW_HELD = 0x00B72ED0          # the block the show holds (0 = none); retail writes it only in the loader
SHOW_ACTIVE = 0x00B72E80        # 1 while a show is loaded
REPLAY_ACTIVE = 0x00B60A90      # 1 while the replay system holds the block
LOADER_VA, RELEASE_VA, TASK_VA, REPLAY_VA = 0x000DA4D0, 0x000DA5A0, 0x000DA5D0, 0x00083F10
SWITCH_VA = 0x001F7DF0          # presentation command 14 (its case 9 loads the postgame show), with its case table
GAME_STATE = 0x00E602B8         # 10 = the game is over (the post-play evaluator or the period end decided it)
TAKE_VA, GIVE_VA, SIZE_VA = 0x000F6070, 0x000F60A0, 0x000F6060

# Exact retail bytes over each routine's whole extent, its alignment padding included; the new bytes are assembled at
# the same address (GNU as --32, linked there) and padded with the same 0x90.
SITES = (
    ("show loader: no heap and no contexts without the show block", LOADER_VA,
        bytes.fromhex(
            "5733ff3bcf893df03ab700893de82eb700890dec3ab700893df43ab700893db03bb700750fe846be0300e8f18ffaffe81c95fa"
            "ff56e856bb01008bf0e85fbb01008d480383e1fca3d02eb7008d919c0000002bc203c650890dd42eb700e80ee1f6ff393dec3a"
            "b700893d043bb7005eba348de6007505ba508de600a1d42eb7005768409c0d005068882eb700b9208de600e8ea99f6ff8b0dd4"
            "2eb7008b1574bea8005768409c0d005168ac2eb700b96c8de600e8c899f6ffc705802eb700010000005fc39090909090909090"
            "90909090"),
        bytes.fromhex(
            "5731ff39f9893df03ab700893de82eb700890dec3ab700893df43ab700893db03bb700c705802eb70001000000750fe83cbe0300"
            "e8e78ffaffe81295faff56e84cbb010089c6e855bb010085c07479a3d02eb7008d480383e1fc8d919c00000029d001f050890dd4"
            "2eb700e800e1f6ff393dec3ab700893d043bb7005eba348de6007505ba508de600a1d42eb7005768409c0d005068882eb700b920"
            "8de600e8dc99f6ff8b0dd42eb7008b1574bea8005768409c0d005168ac2eb700b96c8de600e8ba99f6ff5fc35e5fc39090909090")),
    ("show release: unload and give back only a block the show holds", RELEASE_VA,
        bytes.fromhex(
            "b96c8de600e8468df6ffb9208de600e83c8df6ffe8e7ba0100e8a29cfaffc705802eb70000000000c390909090909090"),
        bytes.fromhex(
            "31c0a3802eb7008705d02eb70085c07419b96c8de600e8358df6ffb9208de600e82b8df6ffe8d6ba0100e8919cfaffc3")),
    ("show task: done at once when no show was loaded (and the halftime with it)", TASK_VA,
        bytes.fromhex(
            "a1f03ab7005633f683f8028935e42eb7000f8425010000833d043bb700020f850b0100002bc60f84df000000480f85d100000033"
            "c9e84663f9ff85c00f84c200000068888de600ba4d524b5333c9c705f03ab70002000000c705842eb70001000000e8a9a3f6ff3b"
            "c6a3d03ab70074248bc8e8e96e07008bc8e8d245f5ff518b0dd03ab700d91c24e8d36e07008bc8e8ac49f5ff68b48de600ba4d52"
            "4b5333c9e86ba3f6ff3bc6a3083bb70074338bc8e8ab6e0700834808018b0d083bb700e89c6e07008bc8e88545f5ff518b0d083b"
            "b700d91c24e8866e07008bc8e85f49f5ffe8ea17180068fc3ab70068f83ab700b8003bb700e816f5ffffb904000000e8dcb0f8ff"
            "b8010000005ec333c9c705f03ab70001000000e83462f9ff8935d03ab7008935083bb700b8010000005ec38935d03ab700b80100"
            "00005ec3e81f02f8ff518b0dd03ab700d91c24e8106e07008bc8e80949f5ff85c075a95ec3909090"),
        bytes.fromhex(
            "833dd02eb70000750dc705302cb7000100000031c0c3a1f03ab7005631f683f8028935e42eb7000f8411010000833d043bb70002"
            "0f85fc00000029f00f84d9000000480f85cb00000031c9e83063f9ff85c00f84bc00000068888de600ba4d524b5331c96a0258a3"
            "f03ab70048a3842eb700e899a3f6ff39f0a3d03ab700742489c1e8d96e070089c1e8c245f5ff518b0dd03ab700d91c24e8c36e07"
            "0089c1e89c49f5ff68b48de600ba4d524b5331c9e85ba3f6ff39f0a3083bb700743389c1e89b6e0700834808018b0d083bb700e8"
            "8c6e070089c1e87545f5ff518b0d083bb700d91c24e8766e070089c1e84f49f5ffe8da17180068fc3ab70068f83ab700b8003bb7"
            "00e806f5ffffb904000000e8ccb0f8ffb8010000005ec331c940a3f03ab700e82862f9ff8935d03ab7008935083bb700ebde8935"
            "d03ab700ebd6e81d02f8ff518b0dd03ab700d91c24e80e6e070089c1e80749f5ff85c075b75ec390")),
    ("presentation: the postgame show only when the game is over", SWITCH_VA,
        bytes.fromhex(
            "0fb6c183f8097725ff2485807e1f00e9bc7aeaffe9c7def2ffc705c802e60016000000c705cc02e60000000000c3c705c802e600"
            "18000000c705cc02e60000000000c3b901000000e9e384eaffe94ea0eaffe85940f2ff33c9e832d7eaffe80d2de6ff33c9e80676"
            "e6ffb983000000e98cffe6ffe92782eaffe8d2eef3ff8bc8e90bf9f1ffb901000000e95126eeff90ff7d1f00047e1f00097e1f00"
            "1e7e1f00337e1f003d7e1f00427e1f00647e1f00697e1f00757e1f00"),
        bytes.fromhex(
            "0fb6c183f8097722ff2485807e1f00e9bc7aeaffe9c7def2ffc705c802e600160000008325cc02e60000c3c705c802e600180000"
            "008325cc02e60000c36a0159e9eb84eaffe956a0eaffe86140f2ff31c9e83ad7eaffe8152de6ff31c9e80e76e6ffb983000000e9"
            "94ffe6ffe92f82eaffe8daeef3ff89c1e913f9f1ff833db802e6000a75a46a0159e95226eeff9090ff7d1f00047e1f00097e1f00"
            "1b7e1f002d7e1f00357e1f003a7e1f005c7e1f00617e1f006d7e1f00")),
    ("replay system: no zones and no later give-back without the show block", REPLAY_VA,
        bytes.fromhex(
            "f605f008b60001754d56c705900ab60001000000e8372107008bf032c9d1fee86cf5ffff8325f007b600fee830210700568bd0"
            "32c9a3b807b600e8e1f3ffffa1b807b6008d143056b1018915bc07b600e8cbf3ffff5ec3909090909090909090"),
        bytes.fromhex(
            "f605f008b60001755156e84121070089c630c9d1fee876f5ffff8325f007b600fee83a21070085c0742fc705900ab600010000"
            "005689c230c9a3b807b600e8ddf3ffffa1b807b6008d143056b1018915bc07b600e8c7f3ffff5ec39090909090")),
)

# Pins for the unchanged routines the three sites rely on: the block's size, take and give, the zone registry, the
# heap creator, the replay zone setup and release, and the halftime zone release the show release calls.
GUARDS = (
    (SIZE_VA, 0x0F, "the block's size: 0x148000 while it exists"),
    (TAKE_VA, 0x2F, "take: 0 when the block is missing or taken"),
    (GIVE_VA, 0x23, "give back: registers the block again only when it is taken"),
    (0x12EF00, 0x121, "zone registry: register"),
    (0x12F030, 0x33, "zone registry: unregister by id"),
    (0x48640, 0x59, "heap creator (head; nfl2k5_resource_load_guard owns its tail)"),
    (0x83330, 0x2C, "replay zone setup"),
    (0x83F70, 0x3F, "replay release: only while 0xB60A90 is set"),
    (0x84260, 0x0F, "halftime zone release"),
)
GUARD_SHA256 = {
    SIZE_VA: "c7a01fefe37c4a768170b153f6a8deb7f22863cd879f93a72ba98033bd01987d",
    TAKE_VA: "8e9f1cbebbda53091fa676ff4cc4cff9e29589d8699334f2ca198fcbcf58b4a6",
    GIVE_VA: "c91cf77c7211c13aba9126b552d0e0abd4798e937eba8d91b3b7d4dba2a8067f",
    0x12EF00: "71467359aac02f5866d520c9a59f14118f720b1261a1777f2700f42093dd2509",
    0x12F030: "9bd2ea5c15daa9e1b1021a5b6e69a280a807371cbbfb03c22fce41bed77f512f",
    0x48640: "e95c30014d731a42503447ffef9393f01c078727b825a5681e515e0f7b89351a",
    0x83330: "17592f38dff0ce66b14ec0542e60a82cd89a2e692f2afe4b907667d4cfd97cd5",
    0x83F70: "a6e87732dca7080e5bf051aee93290cd87e208e1b101c9474b63337ae5ce5d43",
    0x84260: "1d96c9335eb683bf2c052774afcd3bd163d70dbb4a39547cf2f58b3aeb4f8229",
}


def _guards_hold(payload: bytes) -> bool:
    for va, size, _what in GUARDS:
        off = rdata.offset_of(payload, va)
        if hashlib.sha256(payload[off:off + size]).hexdigest() != GUARD_SHA256[va]:
            return False
    return True


def status(payload: bytes) -> str:
    """'retail', 'applied' or 'foreign' (the sites or the routines they rely on are not the expected bytes)."""
    try:
        if not _guards_hold(payload):
            return "foreign"
        return rdata.status(payload, SITES)
    except (ValueError, TypeError):
        return "foreign"


def verify(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        raise rdata.RdataSiteError(f"The show block guard is {state}, not applied")
    return dict(status=state, sites=[row[0] for row in SITES], file_growth=0, runtime_witnessed=False)


def apply(payload: bytes):
    state = status(payload)
    if state not in ("retail", "applied"):
        raise rdata.RdataSiteError("The show block guard's routines are foreign or mixed")
    result, receipt = rdata.apply(payload, SITES, BUILD_CAPTION)
    return result, {**receipt, **verify(result), "owner": OWNER,
                    "reservations": [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                                          basis="pinned live function extent; not a cave")
                                     for _, va, before, _ in SITES]}

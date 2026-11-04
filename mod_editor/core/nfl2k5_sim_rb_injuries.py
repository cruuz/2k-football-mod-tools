"""Short running-back injuries in simulated franchise games (b779 sim2). EXPERIMENTAL, native owner.

Report (b779, released v0.7): two simulated seasons of the released modern roster at Sim. Quarter Length 5
produced no injury for any club player (two full seasons, 512 games), while the NFL 2021-2025 injury reports
show 1.57 one-to-two-week running-back injuries a team season and 0.22 of three weeks or longer (nflverse
``injuries_2021..2025``, regular season, position RB, runs of consecutive weeks with report status Out or
Doubtful; 1.48 and 0.21 in the 16-game season this game plays).

This owner has two entries in one 640-byte code cave.

The weekly roll (``code_for`` entry, ``WEEKLY_SITE``) runs at the tail of the franchise week's own injury
tick (``FUN_00133c50``, called once per advance; it walks every club's players and clears the injury status
the week countdown gives back). The hook replaces the tick's ``pop edi; pop esi; pop ebx; ret`` with a jump
to the cave; the cave replays the three pops, adds the roll and returns. For each club it finds the first
healthy halfback in the team's depth-ordered pointer list and draws one 16-bit value from the game's own
league RNG (``FUN_00048bc0``, the state the retail draft/league code seeds): 810/65536 (0.21 a season) set a
4-5 week injury, the next 5706/65536 (1.48 a season) a 2-3 week one, and the rest leave the club alone. The
weeks land in ``+0x20`` bits 22..29 with the injured bit 31, and ``+0x24`` gets status 4 (out). Those are the
same fields the game itself uses (``0xE6680`` clears them, ``0x13E3A0`` reads the weeks): nothing new is
invented and no roster record outside the injury fields changes. The roll is in the weekly advance only, so
played games are never touched.

b780 hunt1: the roll skips every club a person controls (the game's own human-club flag, ``0x13EC30``, the same
test the weekly depth sort uses to leave user clubs alone). Before, the weekly advance rolled for all clubs, so the
halfback a player's own Franchise or MyCareer club lists first was put out for 2 to 5 weeks about 1.7 times a season
(about one advance in ten, preseason and playoff weeks included) even when the player played every game and nobody
got hurt on the field: those games already have the game's own injuries. Measured on the SOFTDRINK 2K28 v0.9 RC
executable with the game's own franchise start and weekly tick (400 ticks): 33 injuries on the user club's first
healthy back, 39 on a computer club's (the published 9.9 % a tick); with this revision 0 on the user club. Clubs
the computer runs are unchanged.

b780 hunt1, the carry guard's backup scan: beta-79 kept the club's player count in EBP and loaded each candidate
into EBP, so after the first candidate the wrap test compared the index with a player pointer and the scan never
wrapped: when no healthy halfback followed the selected one in the club's list (the last back, or the next ones hurt)
it ran on past the list into the club record and loaded +0x35 through the words there. The count word at +0x11C
(0x2E4D6441 on a 65-man preseason roster) is no pointer: the SOFTDRINK 2K28 v0.9 RC franchise (seed 2602, year 2,
preseason) stopped there with a read of unmapped memory, which on the console is a freeze. The count now stays in
EDI (same instruction lengths, same 350-byte guard), so the scan wraps to the backs ahead of the selected one and
never reads past the club's list.

A beta-79 / SOFTDRINK 2K28 v0.8 install (same cave, same hooks) reads ``previous`` and is upgraded in place
(``nfl2k5_sim_rb_injuries_b779`` is that frozen revision).

Fullback carries (b780 db2, built on hunt1). Report (beta-80 cycle, v0.8): fullbacks running for 150 yards and 3
touchdowns in simulated games. The retail lottery ``0x103360`` draws the carrier from four lineup slots, ``0x4F6A6C`` =
1, 3, 2, 0 (HB1, HB2, FB1, QB1 in the lineup table ``0xA96828``), each weighted by its rating composite to the fourth
power. That is the retail design and it suited 2004 (fullbacks had 8.0% of NFL carries); the modern NFL gives them 0.3%
(nflverse 2021-2025, 1.4 carries a team-season), and the modern roster's fullbacks rate close enough to the backs that
the lottery gave them 9.3-9.9% of simulated carries (44-47 a team-season, up to 172 for one fullback). The guard keeps a
fullback's carry (position byte 8) 1 time in 16 (``FULLBACK_KEEP_THRESHOLD``); otherwise it runs the game's own lottery
again for the same team (up to ``FULLBACK_REDRAWS`` times), so the other candidates share the carry by their own
weights, and a halfback drawn this way takes the halfback path above (an injured back passes it to the next healthy
one). If the lottery returns the fullback every time (a club whose first two backs are hurt, so weak backs fill the
HB slots), the HB1 lineup slot takes the carry. A halfback the depth chart puts in the FB slot keeps the retail carries;
only the position-8 fullback is thinned. Two v0.8-executable seasons with beta-80's sim owners and this guard (seeds
2502/2501, against the same seeds without it): fullbacks 46.7/44.9 -> 3.3/3.1 carries a team-season (9.9/9.6% -> 0.7%),
top fullback 167/741/5 and 172/682/6 -> 19/72/0 and 12/52/0, no fullback game of 100 yards or 2 TDs; lead backs 234/237
carries and 949/972 yards (NFL 218 and 958), 15/15 backs over 1,000 (NFL 13.4). (A first version gave every such carry to HB1: lead backs 1,075 yards and 20
backs over 1,000 against the NFL's 958 and 13.4. A second kept the fullback after three fullback draws: 4.1-4.2
carries a team-season, but on hunt1's guard one club with its first two backs out gave its fullback 12-14 carries in
three games, 64 for the season.) The guard grew from 350 to 427 bytes, so it moved from offset 256 to 208 (hunt1's
weekly roll is 197 bytes); the carrier call at ``0x106CFA`` points there. A beta-79 install reads "previous" from both
its cave and its carrier call, and the in-place upgrade rewrites both. The Simulated season realism QB hook at
``0x106CFF`` takes the guard's EAX: on every path it is a carrier of the same team (the lottery's pick, a re-drawn pick,
the HB1 slot or a healthy backup's match copy), and EBX, EBP and ESI come back unchanged (``CarrierSiteChainTests`` runs
``0x106CFA`` to the store at ``0x106D0A`` with both owners installed).

The scheduled-sim carry guard (``SUB_OFFSET``, ``CARRIER_SITE``) is the part that makes an injured back miss
the simulated game. Retail's weekly tick clears the out status while the weeks run down, and the scheduled
simulator's lineup picker then seats the player anyway (b779 inj1 patches that picker). The assist here hooks
the simulator's own ball-carrier selection (``0x106CFA``, the call whose EAX is stored in the current-player
global ``0xA971A4``): if the selected match copy is an injured halfback (``+0x35`` position 7 and the injury
mask), the cave finds the same club through the roster pointer list, walks to the next healthy halfback and
returns that player's match copy instead (the match copies are byte-identical to the roster record up to
``+0x2C``). A healthy halfback keeps retail most of the time, but 2% of his selections go to the next healthy
back as well (b779-int1: 6% before the integration rebalance, which with every sim owner installed left too few
1,000-yard backs); with the injury weeks the lead back keeps a little over half of the club's carries. It is a scheduled-sim
path only and writes no roster field; every other selection returns retail's own pointer. The game's own
lineup guard remains the first line; this covers the weeks-only cases that guard and the sim's status clear
leave standing.

0 writable and 0 read-only bytes are requested. The allocator code request is 640 bytes: the weekly roll,
the carry guard and their shared constants. The cave is placed as the last late owner (see
``nfl2k5_xbe_space.LATE_OWNERS``).
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_sim_rb_injuries"
CODE_SIZE = 640
SUB_OFFSET = 208                  # b780 db2: the guard (416 bytes with the fullback rule) starts here; beta-79 used 256
UPGRADES_PREVIOUS = True          # status() may read "previous" (the beta-79 install); apply() upgrades it in place
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Simulated RB short injuries"
HELP_TEXT = ("EXPERIMENTAL. Simulated franchise games give running backs the short injuries the NFL sees: about 1.5 "
             "one-to-two-week injuries a team season and 0.2 of three weeks or longer. The injured back sits out "
             "the simulated game and the next healthy back takes his carries; the injury is stored in the "
             "franchise roster and counted down by the game's own weekly tick. Clubs you control (your Franchise "
             "or MyCareer club) are left alone: their backs get hurt only on the field. A fullback keeps about 1 in "
             "16 of the simulated carries the original game gives him, close to the handful modern fullbacks get; the "
             "others are drawn again among the halfbacks and the quarterback. Played games and every rating are "
             "unchanged.")

# The franchise week injury tick FUN_00133c50 ends with pop edi; pop esi; pop ebx; ret. It runs once per
# advance and walks every club player, so its tail is the once-a-week point after the game's own clear.
WEEKLY_SITE = 0x00133CC9
WEEKLY_BEFORE = bytes.fromhex("5f5e5bc390")
# The scheduled simulator's ball-carrier selection: the call whose return value 0x106D0A stores at 0xA971A4.
CARRIER_SITE = 0x00106CFA
CARRIER_BEFORE = bytes.fromhex("e861c6ffff")

FN_RAND = 0x00048BC0              # mov ecx, 0xB12680; jmp 0x48B50: the league RNG, returns a dword in EAX
FN_HUMAN_CLUB = 0x0013EC30        # ecx = club object -> eax = the club's human flag ([0xE5775C + 4 * index]); b780 hunt1
LEAGUE_ROOT = 0xB72918            # franchise root; +0x1C is the club array
TEAM_COUNT = 32
TEAM_STRIDE = 500
PLAYER_COUNT = 0x11C              # club record: player count byte, pointer list from +0
PLAYER_POSITION = 0x35            # 7 = HB
INJURY_WORD = 0x20
STATUS_WORD = 0x24
INJURED = 0x80000000
WEEKS_MASK = 0x3FC00000
STATUS_MASK = 0x70000000
STATUS_OUT = 0x40000000
INJURY_MASK = INJURED | WEEKS_MASK   # 0xBFC00000

# 1.48 and 0.21 events a team-season over the 17 weekly advances, as 16-bit cumulative thresholds.
LONG_THRESHOLD = 810              # 0.21 / 17 * 65536
SHORT_END = 6516                  # (0.21 + 1.48) / 17 * 65536
HEALTHY_HB_MASK = INJURY_MASK
# b779-sim2 carry concentration: the scheduled sim gives the lead back about 0.60 of the club's carries (the
# retail roster gives 0.57 and still produces the right 2004 count because its backs are less efficient). The
# modern room's depth-2 halfback is about 20 OVR below the starter, so the reviewed depth-gradient target (5.7)
# would need implausible backup boosts. Instead the carrier guard hands 6% of every healthy halfback selection
# to the next healthy back. With the injuries above the measured season share lands near 0.48-0.49.
# b779-int1 rebalance: 2% (1311/65536 = 0.02); with all sim owners together 6% left 8-10 backs over 1,000 yards.
ROTATION_THRESHOLD = 1311
# b780 db2: a fullback (position byte 8) picked by the retail lottery keeps the carry when the 16-bit league draw is
# below this (4096/65536 = 1 in 16); otherwise the lottery draws again (its candidates: sim team offense summary +8 QB1,
# +0xC HB1, +0x10 FB1, +0x14 HB2, from 0x4F6A6C over the lineup table 0xA96828).
FULLBACK_POSITION = 8
FULLBACK_KEEP_THRESHOLD = 4096
FULLBACK_REDRAWS = 3              # fresh lottery draws for a fullback's carry; then the HB1 slot takes it
LEAD_BACK_SLOT = 0x0C             # sim team offense summary: the HB1 slot


class SimRbInjuriesError(ValueError):
    """The weekly tick, the carrier site or the patched cave does not read back."""


def require(ok, message):
    if not ok:
        raise SimRbInjuriesError(message)


def _weekly(a):
    """The once-a-week roll. Entry replays the three pops the hook displaced."""
    a.b("5f")                                          # pop edi
    a.b("5e")                                          # pop esi
    a.b("5b")                                          # pop ebx
    a.b("60")                                          # pushad
    a.b("33db")                                        # xor ebx, ebx
    a.call(0x000C6430)                                 # club count
    a.b("8be8")                                        # mov ebp, eax
    a.label("team_loop")
    a.b("8bcb")                                        # mov ecx, ebx
    a.call(0x000C4C50)                                 # club object
    a.b("8bf8")                                        # mov edi, eax
    a.b("8bcf")                                        # mov ecx, edi
    a.call(FN_HUMAN_CLUB)                              # b780 hunt1: a club a person controls gets no roll
    a.b("85c0")                                        # test eax, eax
    a.j32("0f85", "next_team")
    a.b("8bcf")                                        # mov ecx, edi
    a.call(0x000C3E70)                                 # first player
    a.b("8bf0")                                        # mov esi, eax
    a.label("player_loop")
    a.b("85f6")                                        # test esi, esi
    a.j32("0f84", "next_team")
    a.b("807e3507")                                    # cmp byte [esi+0x35], 7
    a.j32("0f85", "player_next")
    a.b("f74620" + struct.pack("<I", INJURY_MASK).hex())  # test dword [esi+0x20], injured | weeks
    a.j32("0f84", "healthy")
    a.label("player_next")
    a.b("8bd6")                                        # mov edx, esi
    a.b("8bcf")                                        # mov ecx, edi
    a.call(0x000C3E80)                                 # next player
    a.b("8bf0")                                        # mov esi, eax
    a.j32("e9", "player_loop")
    a.label("healthy")
    a.call(FN_RAND)
    a.b("0fb7c0")                                      # movzx eax, ax
    a.b("3d" + struct.pack("<I", LONG_THRESHOLD).hex())  # cmp eax, LONG_THRESHOLD
    a.j32("0f82", "long_injury")
    a.b("3d" + struct.pack("<I", SHORT_END).hex())     # cmp eax, SHORT_END
    a.j32("0f82", "short_injury")
    a.j32("e9", "next_team")
    a.label("long_injury")
    a.b("83e001")                                      # and eax, 1
    a.b("83c004")                                      # add eax, 4        4 or 5 weeks
    a.j32("e9", "set_injury")
    a.label("short_injury")
    a.b("83e001")                                      # and eax, 1
    a.b("83c002")                                      # add eax, 2        2 or 3 weeks
    a.label("set_injury")
    a.b("8b4e20")                                      # mov ecx, [esi+0x20]
    a.b("81e1" + struct.pack("<I", 0x003FFFFF).hex())  # and ecx, 0x003fffff
    a.b("81c9" + struct.pack("<I", INJURED).hex())     # or ecx, 0x80000000
    a.b("c1e016")                                      # shl eax, 0x16
    a.b("09c1")                                        # or ecx, eax
    a.b("894e20")                                      # mov [esi+0x20], ecx
    a.b("8b4e24")                                      # mov ecx, [esi+0x24]
    a.b("81e1" + struct.pack("<I", 0x8FFFFFFF).hex())  # and ecx, 0x8fffffff
    a.b("81c9" + struct.pack("<I", STATUS_OUT).hex())  # or ecx, 0x40000000
    a.b("894e24")                                      # mov [esi+0x24], ecx
    a.label("next_team")
    a.b("43")                                          # inc ebx
    a.b("3bdd")                                        # cmp ebx, ebp
    a.j32("0f8c", "team_loop")
    a.b("61")                                          # popad
    a.b("c3")                                          # ret

def _carrier(a):
    """The scheduled-sim ball-carrier guard: replace an injured HB match copy with the next healthy one.

    b780 db2: a fullback pick keeps the carry 1 time in 16; otherwise the retail lottery draws again (see FULLBACK_*)."""
    a.b("60")                                          # pushad
    a.call(0x00103360)
    a.b("89c6")                                        # mov esi, eax
    a.b("8944241c")                                    # mov [esp+0x1c], eax   default return
    a.b("85f6")                                        # test esi, esi
    a.j32("0f84", "done")
    a.b("807e3507")                                    # cmp byte [esi+0x35], 7
    a.j32("0f85", "fullback")                          # b780 db2: not a halfback (was: done)
    a.label("halfback")
    a.b("f74620" + struct.pack("<I", INJURY_MASK).hex())  # test dword [esi+0x20], injured | weeks
    a.j32("0f84", "maybe_rotate")                      # healthy: 2% of the room's carries go to the next back
    a.j32("e9", "find_team")                           # injured: always the next healthy back
    a.label("maybe_rotate")
    a.call(FN_RAND)
    a.b("0fb7c0")                                      # movzx eax, ax
    a.b("3d" + struct.pack("<I", ROTATION_THRESHOLD).hex())  # cmp eax, 1311
    a.j32("0f82", "find_team")
    a.j32("e9", "done")
    a.label("find_team")
    a.b("8b3d" + struct.pack("<I", LEAGUE_ROOT).hex())  # mov edi, [root]
    a.b("8b7f1c")                                      # mov edi, [edi+0x1c]
    a.b("33db")                                        # xor ebx, ebx
    a.label("team_loop")
    a.b("8bc3")                                        # mov eax, ebx
    a.b("69c0" + struct.pack("<I", TEAM_STRIDE).hex())  # imul eax, eax, 500
    a.b("03c7")                                        # add eax, edi
    a.b("0fb688" + struct.pack("<I", PLAYER_COUNT).hex())  # movzx ecx, byte [eax+0x11c]
    a.b("85c9")                                        # test ecx, ecx
    a.j32("0f84", "next_team")
    a.b("33d2")                                        # xor edx, edx
    a.label("find_loop")
    a.b("8b2c90")                                      # mov ebp, [eax+edx*4]
    a.b("85ed")                                        # test ebp, ebp
    a.j32("0f84", "find_next")
    a.b("8b4e10")                                      # mov ecx, [esi+0x10]
    a.b("3b4d10")                                      # cmp ecx, [ebp+0x10]
    a.j32("0f85", "find_next")
    a.b("8b0e")                                        # mov ecx, [esi]
    a.b("3b4d00")                                      # cmp ecx, [ebp]
    a.j32("0f85", "find_next")
    a.b("807d3507")                                    # cmp byte [ebp+0x35], 7
    a.j32("0f85", "find_next")
    a.b("8bfa")                                        # mov edi, edx          injured index
    a.j32("e9", "found_team")
    a.label("find_next")
    a.b("42")                                          # inc edx
    a.b("0fb688" + struct.pack("<I", PLAYER_COUNT).hex())  # movzx ecx, byte [eax+0x11c]
    a.b("3bd1")                                        # cmp edx, ecx
    a.j32("0f8c", "find_loop")
    a.label("next_team")
    a.b("43")                                          # inc ebx
    a.b("83fb" + struct.pack("<B", TEAM_COUNT).hex())  # cmp ebx, 32
    a.j32("0f8c", "team_loop")
    a.j32("e9", "done")
    a.label("found_team")
    # b780 hunt1: the club's player count stays in EDI for the whole scan. Beta-79 kept it in EBP, which the first
    # candidate load overwrote, so from the second candidate on the wrap test compared the index with a pointer, never
    # wrapped, and read past the club's list into the club record (+0x104 on); a count word there (+0x11C) is no
    # pointer, and loading +0x35 through it stopped the game (the SOFTDRINK 2K28 v0.9 RC franchise, year 2 preseason).
    a.b("8bdf")                                        # mov ebx, edi          injured index
    a.b("0fb6b8" + struct.pack("<I", PLAYER_COUNT).hex())  # movzx edi, byte [eax+0x11c]   club count
    a.b("8bcf")                                        # mov ecx, edi
    a.b("49")                                          # dec ecx
    a.j32("0f8e", "done")
    a.label("cand_loop")
    a.b("43")                                          # inc ebx
    a.b("3bdf")                                        # cmp ebx, edi
    a.j32("0f82", "no_wrap")
    a.b("33db")                                        # xor ebx, ebx
    a.label("no_wrap")
    a.b("8b2c98")                                      # mov ebp, [eax+ebx*4]
    a.b("85ed")                                        # test ebp, ebp
    a.j32("0f84", "cand_next")
    a.b("807d3507")                                    # cmp byte [ebp+0x35], 7
    a.j32("0f85", "cand_next")
    a.b("f74520" + struct.pack("<I", INJURY_MASK).hex())  # test dword [ebp+0x20], injured | weeks
    a.j32("0f85", "cand_next")
    a.j32("e9", "found_backup")
    a.label("cand_next")
    a.b("49")                                          # dec ecx
    a.j32("0f85", "cand_loop")
    a.j32("e9", "done")
    a.label("found_backup")
    a.b("8d8e00e0ffff")                                # lea ecx, [esi-0x2000]
    a.b("8d9600e0ffff")                                # lea edx, [esi-0x2000]
    a.b("81c200400000")                                # add edx, 0x4000
    a.label("scan_loop")
    a.b("3bca")                                        # cmp ecx, edx
    a.j32("0f83", "done")
    a.b("80793507")                                    # cmp byte [ecx+0x35], 7
    a.j32("0f85", "scan_next")
    a.b("8b5d10")                                      # mov ebx, [ebp+0x10]
    a.b("3b5910")                                      # cmp ebx, [ecx+0x10]
    a.j32("0f85", "scan_next")
    a.b("8b5d00")                                      # mov ebx, [ebp]
    a.b("3b19")                                        # cmp ebx, [ecx]
    a.j32("0f85", "scan_next")
    a.b("894c241c")                                    # mov [esp+0x1c], ecx   replacement
    a.j32("e9", "done")
    a.label("scan_next")
    a.b("83c104")                                      # add ecx, 4
    a.j32("e9", "scan_loop")
    # b780 db2: a fullback keeps 1 in 16 of his retail carries; for the rest the game's own lottery draws again (up to
    # FULLBACK_REDRAWS times) among the other candidates, so HB1, HB2 and the QB share them by rating
    a.label("fullback")
    a.b("807e35" + bytes([FULLBACK_POSITION]).hex())  # cmp byte [esi+0x35], 8
    a.j8("75", "done")                                 # neither a halfback nor a fullback: retail
    a.call(FN_RAND)
    a.b("663d" + struct.pack("<H", FULLBACK_KEEP_THRESHOLD).hex())  # cmp ax, 4096   the 16-bit league draw
    a.j8("72", "done")                                 # below: the fullback keeps this carry
    a.b("bb" + struct.pack("<I", FULLBACK_REDRAWS).hex())  # mov ebx, 3   (0x103360 preserves ebx)
    a.label("redraw")
    a.b("8b742404")                                    # mov esi, [esp+4]      saved ESI: the team the lottery drew for
    a.call(0x00103360)                                 # the retail lottery again (reads only; esi = team)
    a.b("85c0")                                        # test eax, eax
    a.j8("74", "done")                                 # nothing drawn: keep the fullback
    a.b("807835" + bytes([FULLBACK_POSITION]).hex())  # cmp byte [eax+0x35], 8
    a.j8("75", "redrawn")
    a.b("4b")                                          # dec ebx
    a.j8("75", "redraw")
    # the lottery drew the fullback every time (a room of hurt or weak backs): the HB1 lineup slot takes the carry
    a.b("8b442404")                                    # mov eax, [esp+4]      the team
    a.b("8b40" + bytes([LEAD_BACK_SLOT]).hex())        # mov eax, [eax+0xc]    its HB1 slot (HB rank 0 at the lineup)
    a.b("85c0")                                        # test eax, eax
    a.j8("74", "done")
    a.b("807835" + bytes([7]).hex())                   # cmp byte [eax+0x35], 7
    a.j8("75", "done")                                 # no halfback there: the fullback keeps it
    a.label("redrawn")
    a.b("8bf0")                                        # mov esi, eax
    a.b("8944241c")                                    # mov [esp+0x1c], eax   the new pick
    a.b("807e3507")                                    # cmp byte [esi+0x35], 7
    a.j32("0f84", "halfback")                          # a halfback: his own injury check and the 2% rotation
    a.label("done")
    a.b("61")                                          # popad
    a.b("c3")                                          # ret


def code_for(code_va):
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    _weekly(a)
    body = a.assemble()
    require(len(body) <= SUB_OFFSET, f"weekly RB injury cave is {len(body)} bytes, guard offset {SUB_OFFSET}")
    b = _Asm(code_va + SUB_OFFSET)
    _carrier(b)
    guard = b.assemble()
    require(len(guard) <= CODE_SIZE - SUB_OFFSET,
            f"carrier guard is {len(guard)} bytes, limit {CODE_SIZE - SUB_OFFSET}")
    return (body.ljust(SUB_OFFSET, b"\xcc") + guard).ljust(CODE_SIZE, b"\xcc")

def sites(code_va):
    return [("weekly_injury_tick", WEEKLY_SITE, WEEKLY_BEFORE,
             b"\xe9" + struct.pack("<i", code_va - WEEKLY_SITE - 5)),
            ("sim_carrier_guard", CARRIER_SITE, CARRIER_BEFORE,
             b"\xe8" + struct.pack("<i", code_va + SUB_OFFSET - CARRIER_SITE - 5))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE
            and rows[0]["align"] == 16, "Missing or foreign RB injury allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    states = set()
    # b780 db2: the guard moved (256 -> 208), so a beta-79 install's carrier call is its own "previous" bytes
    previous_sites = _previous_sites(owned["va"]) if owned else [None] * 2
    for (_name, va, before, after), prior in zip(sites(owned["va"] if owned else 0), previous_sites):
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after
                   else "previous" if prior is not None and raw == prior[3] else "foreign")
    code_state = None
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        code_state = ("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"])
                      else "previous" if raw == _previous_code_for(owned["va"]) else "foreign")
        if code_state == "applied" and "previous" in states:
            code_state = "foreign"  # b780 db2: this release's cave behind a beta-79 carrier call is no install of ours
        states.add(code_state)
    if states == {"applied", "previous"}:
        states = {"previous"}   # b780 hunt1: the same hooks with the beta-79 roll (a v0.8 executable)
    require(states in ({"retail"}, {"applied"}, {"previous"}), "Foreign or mixed RB injury site/code")
    return next(iter(states))


def _previous_code_for(code_va):
    """b780 hunt1: the beta-79 / v0.8 cave (its weekly roll also hit clubs a person controls), from the frozen module."""
    from . import nfl2k5_sim_rb_injuries_b779 as b779
    return b779.code_for(code_va)


def _previous_sites(code_va):
    """b780 db2: the beta-79 / v0.8 hooks (its guard at offset 256), from the frozen module."""
    from . import nfl2k5_sim_rb_injuries_b779 as b779
    return b779.sites(code_va)


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError):
        return "foreign"


def apply(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    if state == "foreign":
        raise SimRbInjuriesError("the source executable is not retail or Simulated RB short injuries")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    if state == "previous":
        # b780 hunt1: a beta-79 / v0.8 install (same cave and hooks) is upgraded in place to the roll that leaves
        # clubs a person controls alone. b780 db2: the guard moved, so the carrier call is re-pointed as well; the
        # weekly hook keeps its bytes. Same allocation and address; the result equals a fresh install.
        code_va = allocation(payload)["va"]
        result, _ = space.install_code(payload, OWNER, code_for(code_va), previous=_previous_code_for(code_va))
        image = XbeImage(result)
        buf = bytearray(result)
        edits = []
        for (name, va, _retail, after), prior in zip(sites(code_va), _previous_sites(code_va)):
            off = image.offset(va, len(after))
            if bytes(buf[off:off + len(after)]) == after:
                continue
            require(bytes(buf[off:off + len(after)]) == prior[3], f"RB injury site {va:#x} is not the beta-79 hook")
            buf[off:off + len(after)] = after
            edits.append(dict(label=name, va=hex(va), before=prior[3].hex(), after=after.hex()))
        for section in _sections(buf):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        result = bytes(buf)
        require(status(result) == "applied" and space.status(result) == "applied", "RB injury upgrade postcondition failed")
        return result, dict(common, status="applied", upgraded_from="previous",
                            changed_bytes=space.count_differing_bytes(payload, result), edits=edits)
    before = payload
    receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Simulated RB short injuries need the scale-out allocator")
            payload, receipt = space.extend_scaleout(payload, REQUESTS)
    owned = allocation(payload)
    code_va = owned["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"RB injury site {va:#x} is not retail")
        buf[off:off + len(new)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "RB injury postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result),
                        file_growth=len(result) - len(before), allocation=receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex())
                               for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "SUB_OFFSET", "WEEKLY_SITE", "WEEKLY_BEFORE",
           "CARRIER_SITE", "CARRIER_BEFORE", "BUILD_CAPTION", "HELP_TEXT", "code_for", "sites", "allocation",
           "status", "apply", "SimRbInjuriesError", "FULLBACK_POSITION", "FULLBACK_KEEP_THRESHOLD", "FULLBACK_REDRAWS",
           "UPGRADES_PREVIOUS"]

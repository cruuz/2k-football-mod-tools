"""CPU-only opening-toss deferral. EXPERIMENTAL / UNWITNESSED.

The CPU winner defers at a nominal 240/272 (15/17, 88.2353%) probability,
the 2023 regular-season count published by jpmSportsStats. This dated measured
rate is not a claimed 2026 league average. The loser chooses for the first
half; the deferring CPU chooses receive for the second half. Humans retain
the two retail choices. See docs/research/nfl2k5_b69_rules.md for the menu limit.

Revision 2 (b780 modes2, Q25): every game starts with no deferral. Revision 1 cleared the state only at a toss, so
a game without an opening toss (a Situation game, a moment, which the era rules forward here for post-2008
seasons) that crossed halftime gave the second-half kickoff by the previous game's CPU deferral. A fifth hook, the
match reset's call 0x55F61 (FUN_00055dd0 runs once per game before any toss; call 0xAF400, the clock record reset),
clears it first. It is not one of HOOKS: the era rules wrap those four, and the reset must run in every mode.
Revision-1 installs read "previous" and upgrade in place (the code, then the new hook).
"""
from __future__ import annotations
import sys
from . import nfl2k5_rules_patch as patch
from . import nfl2k5_coin_defer_code as assembly
from . import nfl2k5_coin_defer_code_b779 as assembly_b779

OWNER = "nfl2k5_coin_defer"
REQUESTS = ((OWNER, "code", 384, 16), (OWNER, "data", 4, 4), (OWNER, "read_only", 128, 4))
DEFAULTS = {}
NOTICE = "CPU deferred. Choose for the first half."
RATE_NUMERATOR, RATE_DENOMINATOR = 15, 17
RATE_SOURCE = "https://www.reddit.com/r/nfl/comments/198fkwh/2023_regular_season_coin_toss_data/"
BUILD_CAPTION = "Coin toss: CPU defer (modern, experimental; CPU winners only)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Off in every preset. CPU winners defer "
             "at the published 2023 rate of 240/272 (88.24%). The loser chooses "
             "kick or receive for the first half and the deferring CPU receives "
             "in the second half. Human winners keep the retail menu; a human "
             "Defer choice is not available. Overtime keeps retail toss choices.")
HOOKS = (("choose", 0x25E7B5, bytes.fromhex("8bd8a18c91c300"), b"\xe9"),
         ("menu", 0x25E81F, bytes.fromhex("e89cf8ffff"), b"\xe8"),
         ("halftime", 0x15864C, bytes.fromhex("e80f0ef9ff"), b"\xe8"),
         ("winner_result", 0x25EAF0, bytes.fromhex("8b0d8c91c300"), b"\xe9"))
# b780 modes2: the match reset's clock-record call (FUN_00055dd0, once per game, before the toss)
INIT_HOOK = ("game_init", 0x55F61, bytes.fromhex("e89a940500"), b"\xe8")
UPGRADES_PREVIOUS = True
GUARDS = (
    (0x25e780, 171, "d26b37746850937511a50a31f8e7862894e615e67fc6e23af5dfe57066a5a21b"),
    (0x25eaf0, 20, "53ec57e42084bf8db18240a66f1c8017b852a5195c44157489cf7b412c1bf88c"),
    (0x25dfc0, 31, "8789924ee6ddb0206a6772c1c118c2047407bec9cf355009cfd352d99dfd7f17"),
    (0x771f0, 10, "e94fedfd4b5865214b4dba8cd6a7c2c893a66c4f4443c731313408e2834410fa"),
    (0x48b50, 56, "ae1c4cc23c4e420827a6ff5ab07a6aebab8b3258db105893eec4af4d12bc8673"),
    (0xb9930, 86, "a975448f43fce059a2f7569124d6f71755224b1a3475672946b87dcc76f54a02"),
    (0xb82b0, 49, "931e08a78a0475dde593b320370db201fb974945948497e64efb0ce33f9d9359"),
    (0xb82f0, 58, "f9eb6781f3a430e970f23578e0a8288bf4241d753d3a021e854c64c3f6b178b9"),
    (0x17ed80, 88, "6a0c145c12b3083efb676c5e6dcc9396fc5525faed23b0b8351514f5adbb2791"),
    (0x158620, 49, "c09346caa661115024a03120cdc4e3d67260a05ab6b192483a50ee7d4c60d5c2"),
    (0xe9460, 62, "5f35cd253f4fe2adaf8e75d8067ffa54daa60889add9aceda4bd1ab40f4358a5"),
    (0x25e0c0, 254, "0bf07d7d16eddb8071aa46c0546750e401322e888cbb6f51d057af105c5f5a17"),
    (0x1be1f0, 65, "4f3106616dab10958821450aaee362f6984cb5a60067a1a813812451185ff125"),
    (0x1bdd20, 39, "e59e82e82cee209b9dae4030b8bf25debec772824019a9213cdbfbd38a110d2f"),
    # b780 modes2: the reset's call, the clock record reset it calls, and the reset's period/phase/possession tail
    (0x55f61, 5, "c658936f38c0a6478b27c0eff54f25f67229a8196bc374dbda670de29414b164"),
    (0xaf400, 31, "32578d950df0d2fe320c6a2c4e1ea8af01bd6c99e18e5e8bc8ce6d202da7f706"),
    (0x56032, 44, "f52f4798820289ec80b83f6ba248d136c83b8ea7e1ad0f6d57dbadbfaebeab38"),
)


def encode_options():
    return (NOTICE + "\0").encode("utf-16le").ljust(128, b"\0")


def decode_options(content):
    if content != encode_options():
        raise ValueError("Foreign CPU-defer notice")
    return {}


def code_for(places, source=assembly):
    return patch.relocate(source, places, dict(state=places["data"]["va"],
        notice=places["read_only"]["va"], choose_tail=0x25E7BC,
        native_menu=0x25E0C0, native_possession=0xE9460, human_query=0x25DFC0,
        random_word=0x48B50, home_name=0x61C50, away_name=0x61C60, native_game_init=0xAF400))


def sites(places):
    return patch.hook_sites(HOOKS + (INIT_HOOK,), assembly, places)


def previous(places):
    """Revision 1 (beta-69 .. the v0.9 RC): its code and its four hooks."""
    return [(code_for(places, assembly_b779), patch.hook_sites(HOOKS, assembly_b779, places))]


def status(payload):
    return patch.status(payload, sys.modules[__name__])


def verify(payload):
    return dict(**patch.verify(payload, sys.modules[__name__]), human_defer=False,
                cpu_defer_rate=[RATE_NUMERATOR, RATE_DENOMINATOR], source=RATE_SOURCE)


def apply(payload):
    return patch.apply(payload, sys.modules[__name__])

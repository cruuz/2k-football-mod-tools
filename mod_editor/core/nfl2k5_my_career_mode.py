"""Generic in-game MyCareer owner. EXPERIMENTAL / UNWITNESSED.

Uses 16384 RX and two separately owned 4096-byte RW blocks. Legacy prepared-save installs
and this format are mutually exclusive; rebuild from the original executable.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_my_career as legacy
from . import nfl2k5_my_career_mode_code as assembly
from . import nfl2k5_xbe_space as space
from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_cave_oracle import XbeImage

OWNER = legacy.OWNER
EXTRA_OWNER = space.MYCAREER_M3_STATE_OWNER
EXTRA_VA = space.MYCAREER_M3_STATE_VA
REQUESTS = legacy.REQUESTS + ((EXTRA_OWNER, "data", 4096, 16),)
CODE_SIZE, DATA_SIZE = legacy.CODE_SIZE, legacy.DATA_SIZE
TAG = b"MC-INLINE-M003\0\0\0"
TAG_OFFSET = CODE_SIZE - len(TAG)
COMMON = frozenset(("attach", "copy", "reset", "assign", "automatic", "team_reset", "manual", "transfer",
                    "slot_generation", "sim", "navigation", "cpu_management", "camera", "camera_focus"))
SAVE_HOOKS = (
    ("inline_size", 0x16AA26, "e8555d1600", 0xE8),
    ("inline_admission", 0x16ABB5, "e856feffffeb13", 0xE9),
    ("inline_save", 0x16E50D, "e87e221600", 0xE8),
    ("inline_load_begin", 0x16E5CE, "e89dc5ffff", 0xE8),
    ("inline_read", 0x16E6D3, "e8a8e1ffff", 0xE8),
    ("inline_roster_size", 0x16E7E5, "e86616f5ff", 0xE8),
    ("inline_load_end", 0x16E815, "e8661f1600", 0xE8),
)
MODE_HOOKS = (
    ("mode_camera_pick", 0x8970B, "a150fce50085c0", 0xE9),
    ("mode_art_input", 0x1212A5, "e876f7ffff", 0xE8),
    ("mode_result", 0xC5D60, "e80beef9ff", 0xE8),
    ("mode_result", 0xC5D69, "e802eef9ff", 0xE8),
    ("mode_result", 0xC74E3, "e888d6f9ff", 0xE8),
    ("mode_result", 0xC74EC, "e87fd6f9ff", 0xE8),
    ("mode_visuals", 0x11A8F5, "e896b4f5ff", 0xE8),
    ("mode_stats_commit", 0xC5D9E, "e89de30600", 0xE8),
    ("human_esi", 0x1891DE, "8b463085c0", 0xE8),
    ("human_ecx", 0xA1412, "8b413085c0", 0xE8),
    ("human_eax", 0xA2ABA, "8b483085c9", 0xE8),
    ("human_ecx", 0xA2E7B, "8b413085c0", 0xE8),
    ("human_ecx", 0xA2EBA, "8b413085c0", 0xE8),
    ("human_esi", 0xA30FE, "8b463085c0", 0xE8),
    ("human_esi", 0x189D9B, "8b463085c0", 0xE8),
    ("mode_row_text", 0x2C8790, "e81b83d6ff", 0xE8),
    ("human_eax", 0x1530B9, "8b483085c9", 0xE8),
    ("human_esi", 0x1531D5, "8b463085c0", 0xE8),
    ("human_defense", 0xA342C, "395e30537511", 0xE9),
    ("mode_cap_template", 0x343460, "8b15148bcb00", 0xE9),
    ("mode_dispatch", 0x6E390, "568bf183be0001000020", 0xE9),
    ("mode_creation_done", 0x346D4F, "e9fc76d2ff", 0xE9),
    ("mode_creation_done", 0x346D80, "e9cb76d2ff", 0xE9),
    ("mode_practice_return", 0x2C0E83, "e8c8d5daff", 0xE8),
    ("mode_loaded_replace", 0x16DDE0, "e9fb04f0ff", 0xE9),
)
GUARDS = (
    (0x2bf9a0, 0xf5, "2f271dc4e9289b21f483b18b1f2f9b25af2d582bce1ea95f060aaa5a1c0ea4d9"),
    (0x2484c9, 0xa8, "f367f540e739efc16676dd44bb80ccbb2d707da3e77f32b8ffee6aecafc31d85"),
    (0x3254d0, 0x20, "77a2842feb19a62d33dbd0cc986949386b11989aec4bc855b9a9b555c62dd8ac"),
    (0x325a30, 0x33, "d3b095e220724aaf931d2e173c2d16a5f40911c8ba68488668f2649dab31aa84"),
    (0x325b50, 0x1ae, "e5c5699cecd4899a0761a654ddfccfc874a032ca718cdf1e4f0a4fdebdae1210"),
    (0x325d00, 0x1b, "65a4ae4d9be2137bba947842bc09419cabb2663c7018b7a3436fb6bf83b440ac"),
    (0x31e430, 0x66, "6029f602cbd3832ba4d93dceb64962f56551161e2f78dab73d8283cd6a1262c7"),
    (0x14e540, 0x21, "fde4d8743dcc8e2f0c5b0a9ca78a9481ae4137a87a4048721788de512edf0585"),
    (0x1211E0, 0xD0, "cdf04ccd4ba54547e9f51089891248244ccbd893c2d15d6e694827f2f1c2137c"),
    (0xa88460, 0x50, "0ce3ab700261bc38b8597990ecfbc72eb8cc9dcfd007138dcebc2ddd0c04ec83"),
    (0x896e9, 0x8d, "33f20f68556e2ebb244f5e45ccb4cb5d7f62cd629a9547327a77dda4c15adf29"),
    (0xa4650, 0x17a, "637ec6cc6060f3e6873bc773a648918cdc66e3007b75d41b8e5e5de7d16726f3"),
    (0x6bc30, 0x23d, "f7ee67e89a1f031057d6ff3d7ee46ac59a76558bf0269862aaf0ecef4a53ee7e"),
    (0x46920, 0x90, "eb1885e56619b0b7e653fa72af949e5ada2e8452bf19b1867dcc8591b267e7d7"),
    (0xef850, 0x9, "abfc77963bcc467afc49221d7f61ae661e915fe5710ebd7b9be44d1c6a88c5f9"),
    (0x75d40, 0x50, "2da6c72df0c1539de0b9f6fd2034f7930f0abaecbb883a691356ae94088eb3a1"),
    (0x75d90, 0x6ed, "348a220b359012d8fd386cc8e1ea8258fa2b02412e7ea1a918a16cd8aebfb65f"),
    (0x120a20, 0x775, "17308ced725f4ca7d221cc803adc4b254d6903bfe90cc3a98a0417c645f25f2c"),
    (0x49f00, 0x4d9, "908d559d09574449caa7b433d83fbd92ea17718ab1d728f5824406c309a4f790"),
    (0xf3e90, 0xed, "ec3b1d1e23628198be072193dcf9959fbbe68c218226c7e17eec07ecea427077"),
    (0xf3cd0, 0x87, "c6a26b2780164a3e75395d59ef13abaa13f1fc42a43b290ac27712748f7a2ec0"),
    (0xf37e0, 0x18f, "82f21e664aa9c26b883bfdb3fd4e56f2ae0db841f6f09b558f737947ec769f7a"),
    (0x143ea0, 0xec, "4c96e5f3bba073c4217d5743a214bcaaa57509717a093de0594387146a36cf5a"),
    (0x143450, 0xb7, "c3f4054fd3db4b8272cba5c054d7414576784c3f08999e47ae8e30f7e07c0cde"),
    (0x2c8730, 0x6b, "f7b29a4dfa6927f593f3d9a2cfd4937bafe1ce4dcee37c097a2db932fe5ec559"),
    (0x2c8810, 0x5c, "f0051c31c6c26ca1728dd52e413bbdb00ac1110d33486579a548933267a05dba"),
    (0x150260, 0x94, "b92b5c935f2c864568e123dc9e925663e413613bfa77882a9fc7e7cfec2586de"),
    (0x14ff80, 0xa0, "b9caaad84cde3c36bcce67af26a1a2e943756591e160f25abb916021a9f36a2e"),
    (0x4f03f8, 0xe8, "414cd90aad9ac27f35fac2eb5b0b45f03e622550d7599f9d07075e30b2ebf6e1"),
    (0x247D40, 0x1C, "bf2327b23418946929186e588ffb7fd28b68712d3e92fe29a7a4f154bbb9013f"),
    (0x2480B0, 0x1C, "f0fa650aa4f5631ef3b4cf8168809000b1ab2c320621fad9d2647b00b9c1104d"),
    (0xC79F0, 0x29, "8ab13e288a240ce89a92c4d2a2408dfaf3d71f22b47aeb332c24d70fc98fb91c"),
    (0xC73B0, 0x12B, "07fef36f39b8423857ac0c5cc693363c00752cd7bf06fe92dfefd490e8b83b86"),
    (0xC74E0, 0x43, "bb1906f9f029ea81788d579b295586805684d2a185ca8402e8d31483e27f6cc2"),
    (0xC5D60, 0x49, "57f2d784b1dd7419bab67951363f82a169fa5cb2d9f06529fdf56ea864f03941"),
    (0x1891B0, 0x53, "ee2e72b5f39d739e4e46aa79a71aba77b446b5544599483c8b1e26674c98e1a3"),
    (0x189D10, 0x1EA, "9a4538e1f60aa36b90bb790d388272d5cd5fd5b42c400d730a0b6adcb8556f94"),
    (0xA11F0, 0x299, "c19563b80a731172b11f2df41e94219a87629b124dd48917808c565770ad4d87"),
    (0xA2A60, 0xF9, "d0b86d2a91f1333bf0408ae8aadf09bf31d1c713d9a885c65e56c76c6ef3f99a"),
    (0xA2D40, 0x41E, "6ea576ebdb694d8215b61be72a60c06d865d8aacb1111cf39d550a4d727ba049"),
    (0x1530B0, 0x22, "3c893f6157ef270cab88ba73dfcd58cb415cfc8f983579bc5537e497398c6a9f"),
    (0x153170, 0x7F, "7e2686593d4632a284655585086fa725f212a0b2c7153378280708aebe8aaf29"),
    (0xA31E0, 0x2E5, "207f813e288939ac8a36bef8d97d46e525665fa855f7554815c0efed17919335"),
    (0x3461F0, 0x86, "8c016c8fb8b61b493ae6bfa40e5454e6499e9d33186600618f428217dbaac2c7"),
    (0x346C50, 0x135, "95b8854916829321b25a322e302fca645954d5e8d3f6d7d2dfc27ad0ae6bd255"),
    (0xBFF50, 0x50, "3f53775040e420a012ed20cdf784ba216db304600110131a06e96be37603a256"),
    (0xC0A80, 0xB9, "65e0538d1596a8077ad72612b6cc459c16ab07b0cdcc9b9f86dca2627ba81179"),
    (0x148C60, 0x47, "863f6aa48532459d037f59375ed91bb233cdc1563b638a82901c0a2589fe9f21"),
    (0x10EA10, 0x4E, "f3f93194d04d2f8c165fe8f4f69819bf55929f5426fc6ba168849bdf3a634e23"),
    (0x13EE10, 0x234, "c2a1f6f63153cb3949fcd06a010e66a74d82faf5718570e9967a63adc972e864"),
    (0x13F1B0, 0x13C, "453d1d9b4f7c0b7c7fcf7073c70bb3853e8ddb9548387cbaa4a62d80729de6d9"),
    (0x320E90, 0x27, "6cb719e02510c75c475c7f8644cb22134d142644a8a43d13db997418b28ff965"),
    (0x2C0E70, 0xC, "f48420415bbe66d8c3a4f80a5124073df01f6f493d4184773e265410a2bd2c68"),
    (0x2C0E81, 0x61, "0d02bc5488213e0b8f2bde2a8364a7d8ce00860d668d05eea8394802a9120531"),
    (0x16DDD0, 0x15, "ebc1dac2de06ef688727f132eac6b2c865d250207fedf457071dc80159cd4c33"),
    (0x343460, 0x36, "ac3dff9008975e211bc6025e39447b0abff77f073bcc87e91a3a1f32d825642e"),
    (0x6E450, 0x29, "64e4f5c9fe565afdf4468e893d46e5d6cd0ce9c2430e1a9355f92383f592e080"),
    (0x16AA10, 0x1F, "9593845e7f1ed72c863875db7487e4b2125d722cff22b27214c59da46ff7601c"),
    (0x16AB70, 0x71, "88b837948a533c94bb6af14d995a8a803d1f7bec9f257f081933ff5f87f7a9af"),
    (0x16E3F0, 0x14B, "975bbf703ffeba773e8b34537b4e02e5f28a6ccf3399238177ec035f6bbfb472"),
    (0x16E540, 0x1EF, "a7d4fa760fa0cb4fd797a4dc3b3471093ac2154c420a17ea2f36749938d06212"),
    (0x16E7AE, 0x71, "7d3d3666860a6348daa81b313b5bbe5220d49b6128703a9385aa7b4acf8b5e18"),
    (0x2D0790, 0x54D, "a029a5bda4cee93f703bd091e4c65560ad86f891578bd29821329fc0f5ecce0a"),
    (0x2D0CE0, 0x5BF, "34b056a98ddf75b530720faf510a51db15b44b33ff77ca46ff8839e4153166f6"),
)


def code_for(code_va, data_va):
    from . import nfl2k5_franchise_autosave_code as autosave_code
    from . import nfl2k5_my_career_progression as progression
    out = bytearray(assembly.CODE)
    labels = {name: code_va + offset for name, offset in assembly.LABELS.items()}

    def reserve(name, size):
        out.extend(bytes((-len(out)) % 4))
        at = len(out)
        labels[name] = code_va + at
        out.extend(bytes(size))
        return at

    text_pool = bytearray()

    def string(name, value):
        if name not in ("mode_text", "team_text") and not name.startswith("m3_"):
            labels[name] = data_va + 1408 + 2 * len(text_pool)
            text_pool.extend((value + "\0").encode("ascii"))
            return
        content = (value + "\0").encode("utf-16le")
        at = reserve(name, len(content))
        out[at:at + len(content)] = content

    for name, value in (
        ("mode_text", "MyCareer"), ("apartment_text", "Apartment"),
        ("draft_text", "Enter the draft"), ("udfa_text", "Undrafted free agent"),
        ("load_text", "Load career"), ("quit_text", "Quit to main menu"),
        ("team_text", "Choose team"), ("sign_text", "Sign"),
        ("play_text", "Play next game"), ("card_text", "MyPlayer"), ("save_text", "Save"),
        ("start_text", "Start MyPlayer"),
        ("advance_notice", "No game pending. Advancing."),
        ("watch_text", "Off field: CPU plays"),
        ("fixture_text", "%s at %s. %s"),
        ("draft_notice", "Draft preparation failed. Quit and try again."),
        ("refusal_notice", "Roster is full."),
        ("load_notice", "Career load failed."),
    ):
        string(name, value)
    for name, value in (
        ("m3_progress_text", "Preparing the prior season"),
        ("m3_progress_note", "The league is playing the year before your rookie season."),
        ("m3_prep_text", "Senior Bowl preparation"),
        ("m3_prep_note", "MyPlayer is selected. The game is not available yet."),
        ("m3_begin_text", "Continue to the draft"),
        ("m3_draft_text", "NFL Draft"),
        ("m3_draft_note", "Teams choose by ratings and need. Selection is not guaranteed."),
        ("m3_upgrade_text", "Upgrades"), ("m3_prev_text", "Previous attribute"),
        ("m3_next_text", "Next attribute"), ("m3_buy_text", "Buy one point"),
        ("m3_back_text", "Back"),
        ("m3_upgrade_format", "%s: %u. Cap %u. Cost %u XP. Balance %u XP."),
        ("m3_calendar_format", "Week %u. %u/%u/%u at %02u:%02u"),
        ("m3_pick_format", "Round %u, pick %u"),
        ("m3_confirm_text", "Buy one attribute point?"),
        ("m3_unavailable_text", "This point cannot be bought."),
        ("m3_unsigned_text", "Undrafted. Choose a club and sign."),
        ("m3_sign_text", "Sign with this club?"),
        ("m3_sign_cut_text", "Sign with this club and allow roster cuts?"),
    ):
        string(name, value)
    names = []
    for field, key, label in progression.FIELDS:
        name = "m3_rating_" + key
        string(name, label)
        names.append(labels[name])
    at = reserve("m3_rating_names", 4 * len(names))
    struct.pack_into("<" + "I" * len(names), out, at, *names)
    at = reserve("m3_fields", len(progression.FIELDS))
    out[at:at + len(progression.FIELDS)] = bytes(f for f, _, _ in progression.FIELDS)
    at = reserve("m3_caps", 17 * len(progression.FIELDS))
    out[at:at + 17 * len(progression.FIELDS)] = bytes(v for row in progression.CAPS for v in row)
    legacy.require(2 * len(text_pool) <= 1152, "MyCareer text RW exceeds 1408..2559")
    at = reserve("text_template", len(text_pool))
    out[at:at + len(text_pool)] = text_pool
    labels["text_bytes"] = len(text_pool)
    menu = bytearray()
    extra_menu = bytearray()

    def menu_reserve(name, size):
        at = len(menu)
        labels[name] = data_va + 200 + at
        menu.extend(bytes(size))
        return at

    def extra_reserve(name, size):
        at = len(extra_menu)
        labels[name] = EXTRA_VA + 256 + at
        extra_menu.extend(bytes(size))
        return at

    menu_reserve("club_menu", 56)
    for name in ("entry_menu", "apartment", "team_menu", "practice_menu"):
        menu_reserve(name, 44)
    for name in ("m3_progress_menu", "m3_prep_menu", "m3_draft_menu", "m3_upgrade_menu"):
        extra_reserve(name, 44)

    def rows(name, content, extra=False):
        at = (extra_reserve if extra else menu_reserve)(name, 52 * (len(content) + 1))
        target = extra_menu if extra else menu
        for i, (label, action) in enumerate(content):
            struct.pack_into("<13I", target, at + 52 * i, 9,
                             labels[label] if isinstance(label, str) else label,
                             *([0] * 8), labels[action], 0, 0)
        struct.pack_into("<I", target, at + 52 * len(content), 3)
        return at

    rows("entry_rows", (("draft_text", "mode_draft"), ("udfa_text", "mode_undrafted"),
                        ("load_text", "mode_load"), ("quit_text", "mode_quit")))
    rows("hub_rows", (("play_text", "mode_play"), (0xE9C3BC, "mode_practice"),
                      ("card_text", "mode_card"), ("start_text", "mode_start"),
                      ("save_text", "mode_save_menu"), ("quit_text", "mode_quit"),
                      ("m3_upgrade_text", "m3_upgrade_open")), extra=True)
    rows("team_rows", (("team_text", "mode_team_open"), ("sign_text", "mode_sign")))
    rows("m3_progress_rows", (("quit_text", "mode_quit"),), extra=True)
    rows("m3_draft_rows", (("save_text", "mode_save_menu"), ("quit_text", "mode_quit")), extra=True)
    rows("m3_prep_rows", (("m3_begin_text", "m3_begin_draft"), ("card_text", "mode_card"),
                         ("save_text", "mode_save_menu"), ("quit_text", "mode_quit")), extra=True)
    rows("m3_upgrade_rows", (("m3_prev_text", "m3_upgrade_previous"), ("m3_next_text", "m3_upgrade_next"),
                            ("m3_buy_text", "m3_upgrade_buy"), ("m3_back_text", "m3_back")), extra=True)
    for name, title, table in (("m3_progress_menu", "m3_progress_text", "m3_progress_rows"),
                                ("m3_prep_menu", "m3_prep_text", "m3_prep_rows"),
                                ("m3_draft_menu", "m3_draft_text", "m3_draft_rows"),
                                ("m3_upgrade_menu", "m3_upgrade_text", "m3_upgrade_rows")):
        struct.pack_into("<11I", extra_menu, labels[name] - EXTRA_VA - 256,
                         labels[title], 0, labels["mode_handler"], 0, labels[table], 0,
                         0xE7F928, 0xAA281C, 0x02400044, 0x018D0052, 3)
    legacy.require(len(extra_menu) <= 1900, "M3 menus exceed owned workspace")
    at = reserve("m3_menu_template", len(extra_menu))
    out[at:at + len(extra_menu)] = extra_menu
    labels["m3_menu_bytes"] = len(extra_menu)
    for name, title, table, flags in (("entry_menu", "mode_text", "entry_rows", 3),
                                      ("apartment", "apartment_text", "hub_rows", 3),
                                      ("team_menu", "team_text", "team_rows", 0x13)):
        struct.pack_into("<11I", menu, labels[name] - data_va - 200, labels[title], 0, labels["mode_handler"],
                         0, labels[table], 0, 0xE7F928,
                         0xAA281C, 0x02400044, 0x018D0052, flags)
    struct.pack_into("<11I", menu, 0, labels["team_text"], 0, labels["mode_handler"],
                     0, data_va + 432, 0, 0xE7F928, 0xAA281C, 0x02400044, 0x018D0052, 0x13)
    # Own Practice descriptor: native settings, teams, input and Back lifecycle.
    hooks = menu_reserve("practice_hooks", 20)
    # Native 6E578 reads the next command at +0x24. Keep its zero terminator.
    enter = menu_reserve("practice_enter", 40)
    struct.pack_into("<10I", menu, enter, 1, labels["mode_practice_init"], *([0] * 8))
    struct.pack_into("<5I", menu, hooks, 11, 0x5015F8, 1, labels["practice_enter"], 0)
    struct.pack_into("<11I", menu, labels["practice_menu"] - data_va - 200,
                     0xE7D8B0, labels["practice_hooks"], 0xF3FC0, 0,
                     0x5016C8, 0, 0xE7D7E0, 0xAC9800, 0x02400044, 0x018D0052, 0x55)
    legacy.require(len(menu) <= 1080, "MyCareer menu RW exceeds 200..1279")
    # Bounded LZ: 1..127 literal bytes; 128..255 encode length 3..130 and
    # a little-endian backward distance. Zero ends this immutable template.
    encoded = bytearray()
    literal = bytearray()

    def flush():
        if literal:
            encoded.append(len(literal))
            encoded.extend(literal)
            literal.clear()

    i = 0
    while i < len(menu):
        count = distance = 0
        for j in range(i):
            n = 0
            while n < 130 and i + n < len(menu) and menu[j + n] == menu[i + n]:
                n += 1
            if n > count:
                count, distance = n, i - j
        if count >= 4:
            flush()
            encoded.append(128 + count - 3)
            encoded.extend(struct.pack('<H', distance))
            i += count
        else:
            literal.append(menu[i])
            i += 1
            if len(literal) == 127:
                flush()
    flush()
    encoded.append(0)
    at = reserve("menu_template", len(encoded))
    out[at:at + len(encoded)] = encoded
    labels["menu_bytes"] = len(menu)
    symbols = {"code": code_va, "state": data_va, "m3": EXTRA_VA, "": 0,
               "autosave_completion_delta": autosave_code.LABELS["career_complete"] - autosave_code.LABELS["desk"],
               **labels}
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    legacy.require(len(out) <= TAG_OFFSET,
                   f"generic MyCareer needs {len(out) + len(TAG)} bytes; "
                   f"exceeds its {CODE_SIZE}-byte budget by {max(0, len(out) - TAG_OFFSET)} bytes")
    labels["content_end"] = code_va + len(out)
    return bytes(out).ljust(TAG_OFFSET, b"\xcc") + TAG, labels


def sites(code_va, data_va):
    labels = code_for(code_va, data_va)[1]
    hooks = [(name, va, pin, handler, op) for name, va, pin, handler, op in legacy.HOOKS if name in COMMON]
    hooks += [(name, va, pin, name, op) for name, va, pin, op in (*SAVE_HOOKS, *MODE_HOOKS)]
    edits = [(name, va, bytes.fromhex(pin), legacy.branch(va, labels["mode_camera_focus" if handler == "camera_focus" else handler], len(bytes.fromhex(pin)), op))
             for name, va, pin, handler, op in hooks]
    for name, va, before, after in (("entry_kind", 0x501494, 0, 9),
                                    ("entry_label", 0x501498, 0xE7D5C4, labels["mode_text"]),
                                    ("entry_target", 0x50149C, 0x526948, 0),
                                    ("entry_action", 0x5014BC, 0, labels["mode_entry"]),
                                    ("postgame_resume", 0x4F1994, 0xC74E0, labels["mode_postgame"])):
        edits.append((name, va, struct.pack("<I", before), struct.pack("<I", after)))
    return edits


def recognized(payload):
    """Cheap dispatch tag. Never substitutes for complete status validation."""
    try:
        code, _ = legacy.allocations(payload)
        return XbeImage(payload).read(code["va"] + TAG_OFFSET, len(TAG)) == TAG
    except (ValueError, IndexError, KeyError, struct.error):
        return False


def check_context(payload, edits, *, installed=False):
    image = XbeImage(payload)
    legacy.check_context(image)
    from . import nfl2k5_draft_ai as draft_ai
    legacy.require(draft_ai.status(payload) in ("retail", "applied"), "foreign draft AI owner")
    camera_edits = []
    from . import nfl2k5_franchise_autosave as autosave
    # Practice and music already validate MyCareer. Avoid a dependency cycle
    # by checking Auto Save on a private retail view of our fully validated
    # installation. Only our exact hooks and code are restored in that copy;
    # every companion hook/body/context still undergoes its complete status.
    # The original payload and allocator directory are never modified.
    companion_payload = payload
    if installed:
        from .nfl2k5_bump_strength import _sections, section_digest
        code, _ = legacy.allocations(payload)
        buf = bytearray(payload)
        for _, va, before, _ in edits:
            at = image.offset(va, len(before))
            buf[at:at + len(before)] = before
        buf[code["raw"]:code["raw"] + CODE_SIZE] = b"\xcc" * CODE_SIZE
        space._seal_scaleout(buf, space._validate(payload)[2])
        for section in _sections(buf):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        companion_payload = bytes(buf)
    autosave._recognize(companion_payload)
    from . import nfl2k5_practice_squad as practice_squad
    legacy.require(practice_squad.SYMBOLS["ps_limit"] == 0x3ee10c,
                   "Practice Squad capacity entry moved; rebuild the MyCareer runtime")
    # The existing squad owner guards the same native draft capacity, cut and
    # signing boundaries. Validate its complete installation before removing
    # just those exact branches from the native-context hash view.
    squad_sites = [s for s in practice_squad.sites()
                   if s.name in ("capacity_flags", "draft_sign_guard", "ps_cut", "ps_append")]
    if any(image.read(s.va, s.size) != s.retail for s in squad_sites):
        legacy.require(practice_squad.status(companion_payload) == "applied",
                       "foreign draft squad companion")
        camera_edits += [(s.name, s.va, s.retail, s.patched) for s in squad_sites]
    allocated = any(a["owner"] == autosave.OWNER for a in space.layout(payload)["allocations"])
    if allocated:
        owned = autosave.allocations(payload)
        camera_edits += autosave.sites(owned["code"]["va"], owned["read_only"]["va"])
    from . import nfl2k5_overtime as overtime, nfl2k5_kick_rules as kicks
    # Independently sealed owners change other branches of these functions.
    for module, sentinel, pin, selected in (
        (overtime, overtime.PRED_SITE_VA, overtime.RETAIL_PRED, ("sudden_death_hook",)),
        (kicks, kicks.PAT_STORE_SITE_VA, kicks.RETAIL_CALL_STORE, ("pat_store_hook", "pat_pick_hook")),
    ):
        if image.read(sentinel, len(pin)) != pin:
            legacy.require(module.status(payload) == "applied", "foreign play-call companion owner")
            if module is overtime:
                candidates = [(label, off, before, after) for _, label, off, before, after in
                              module._sites(payload, 10, True, True, True)]
            else:
                candidates = module._sites(payload, **{k:v for k,v in module.read_settings(payload).items() if k in ("kickoff_yard", "touchback_yard", "pat_yard", "max_fg_yards", "cpu_fg_range")})
            for name, off, before, after in candidates:
                if name in selected:
                    va = image.va_for_offset(off)
                    camera_edits.append((name, va, before, after))
    # This save-load call is already owned by the camera. Accept its exact
    # installed bytes only after that owner's full template/seal validation.
    if image.read(0x16E7B1, 5) != bytes.fromhex("e86a46f7ff"):
        from . import nfl2k5_camera as camera
        legacy.require(camera.status(payload) == "applied", "foreign camera/load boundary")
        camera_edits += [(name, camera.HOOKS[name][0], before, after)
                        for name, _, before, after in camera._sites(payload, camera.DEFAULT_PRESET)
                        if name == "franchise_load_select"]
    for va, size, digest in GUARDS:
        raw = bytearray(image.read(va, size))
        for _, hook, before, after in [*edits, *camera_edits]:
            if va <= hook and hook + len(before) <= va + size:
                at = hook - va
                legacy.require(bytes(raw[at:at + len(before)]) in (before, after), "foreign native career boundary")
                raw[at:at + len(before)] = before
        legacy.require(hashlib.sha256(raw).hexdigest() == digest, f"foreign native career context at {va:#x}")


def _recognize(payload):
    found = any(a["owner"] == OWNER for a in space.layout(payload)["allocations"])
    code, data = legacy.allocations(payload) if found else ({"va": 0}, {"va": 0})
    edits = sites(code["va"], data["va"])
    image = XbeImage(payload)
    own_sites = {va for _, va, _, _ in edits}
    legacy.require(all(image.read(va, len(before)) == before for _, va, before, _ in legacy.sites(0, 0)
                       if va not in own_sites), "legacy MyCareer hooks in generic build")
    state = "retail"
    if found:
        extra = [a for a in space.layout(payload)["allocations"] if a["owner"] == EXTRA_OWNER]
        legacy.require(len(extra) == 1 and (extra[0]["kind"], extra[0]["va"], extra[0]["size"], extra[0]["align"]) ==
                       ("data", EXTRA_VA, 4096, 16), "reserve MyCareer M3 state; rebuild from base")
        legacy.require(image.read(EXTRA_VA, 4096) == bytes(4096), "foreign initial MyCareer M3 RW")
        legacy.require(image.read(data["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign initial MyCareer RW")
        blob = image.read(code["va"], CODE_SIZE)
        if blob != b"\xcc" * CODE_SIZE:
            legacy.require(blob == code_for(code["va"], data["va"])[0], "mixed generic MyCareer install")
            state = "applied"
    legacy.require(rdata.status(payload, edits) == state, "mixed generic MyCareer hooks/code")
    check_context(payload, edits, installed=state == "applied")
    return state


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, KeyError, IndexError, TypeError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    state = status(payload)
    legacy.require(state != "foreign", "foreign/mixed generic MyCareer; rebuild from original")
    common = {"owner": OWNER, "experimental": True, "runtime_witnessed": False,
              "in_game_mode": True, "inline_save_version": 1, "save_growth": 128,
              "machine_code_bytes": len(assembly.CODE), "code_capacity": CODE_SIZE, "data_capacity": DATA_SIZE + 4096,
              "state_requests": REQUESTS[1:],
              "executable_seed_bytes": 0, "journal_files": 0}
    original = payload
    if space.status(payload) == "retail":
        payload, _ = space.apply(payload, REQUESTS, scaleout=True)
    code, data = legacy.allocations(payload)
    blob, labels = code_for(code["va"], data["va"])
    common["code_bytes"] = labels["content_end"] - code["va"]
    common["code_spare_bytes"] = TAG_OFFSET - common["code_bytes"]
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "edits": []}
    payload, install = space.install_code(payload, OWNER, blob)
    result, receipt = rdata.apply(payload, sites(code["va"], data["va"]), OWNER)
    legacy.require(status(result) == "applied", "generic MyCareer postcondition failed")
    return result, {**common, **receipt, "already_applied": False, "code_install": install,
                    "changed_bytes": sum(a != b for a, b in zip(original, result)) + len(result) - len(original),
                    "file_growth": len(result) - len(original),
                    "before_sha256": hashlib.sha256(original).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None):
    """Bounded generic XBE writer; it never accepts a player recipe."""
    import argparse
    import json
    import os
    from pathlib import Path
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("status", help="verify the complete generic owner")
    inspect.add_argument("input", type=Path)
    patch = sub.add_parser("apply", help="patch a separate default.xbe; EXPERIMENTAL / UNWITNESSED")
    patch.add_argument("input", type=Path)
    patch.add_argument("output", type=Path)
    patch.add_argument("--receipt", type=Path)
    patch.add_argument("--requests", type=Path, help="complete allocator request JSON union")
    args = parser.parse_args(argv)
    try:
        if not 0 < args.input.stat().st_size <= 16 * 1024**2:
            raise ValueError("input XBE must be at most 16 MiB")
        with args.input.open("rb") as stream:
            payload = stream.read(16 * 1024**2 + 1)
        if len(payload) > 16 * 1024**2:
            raise ValueError("input XBE exceeds 16 MiB")
        original = payload
        input_digest = hashlib.sha256(payload).hexdigest()
        if args.command == "status":
            found = status(payload)
            print(json.dumps({"status": found, "experimental": True, "runtime_witnessed": False}))
            return int(found == "foreign")
        if args.input.resolve() == args.output.resolve():
            raise ValueError("input and output must differ")
        if args.output.exists():
            raise ValueError("output already exists")
        if args.receipt and (args.receipt.exists() or args.receipt.resolve() in
                             (args.input.resolve(), args.output.resolve())):
            raise ValueError("receipt must be a separate new file")
        allocation_receipt = None
        if args.requests:
            if args.requests.stat().st_size > 1024**2:
                raise ValueError("allocator request file exceeds 1 MiB")
            with args.requests.open("rb") as stream:
                raw_requests = stream.read(1024**2 + 1)
            if len(raw_requests) > 1024**2:
                raise ValueError("allocator request file exceeds 1 MiB")
            requests = json.loads(raw_requests)
            if isinstance(requests, dict):
                requests = requests["requests"]
            payload, allocation_receipt = space.apply(payload, requests, scaleout=True)
        output, receipt = apply(payload)
        receipt["generic_disc"] = True
        receipt["input_sha256"] = input_digest
        receipt["output_sha256"] = hashlib.sha256(output).hexdigest()
        receipt["input_size"] = len(original)
        receipt["output_size"] = len(output)
        receipt["total_file_growth"] = len(output) - len(original)
        receipt["total_changed_bytes"] = sum(a != b for a, b in zip(original, output)) + len(output) - len(original)
        receipt["allocation"] = allocation_receipt
        receipt["status"] = status(output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".mycareer-", dir=args.output.parent)
        temporary = Path(temporary).resolve()
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
            if status(temporary.read_bytes()) != "applied":
                raise ValueError("written XBE failed verification")
            os.replace(temporary, args.output)
        finally:
            temporary.unlink(missing_ok=True)
        text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.receipt:
            args.receipt.write_text(text, encoding="utf-8", newline="\n")
        print(text, end="")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"MyCareer: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

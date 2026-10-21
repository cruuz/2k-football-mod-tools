"""User play-call limits and native draw coverage. No game-play witness."""
from pathlib import Path
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_playbook_lint as lint
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_nfl2k5_play_menu_walk import _body, _link


class UiRules(unittest.TestCase):
    def test_literal_names_keep_the_terminator_in_the_64_unit_slot(self):
        for value in ("Titans Post Wheel", "Kings Long", "Ace Long", "X" * 63,
                      "\U0001f3c8" * 31 + "X"):
            self.assertEqual(ip.playcall_name_problems(value), [])
        for value in ("X" * 64, "\U0001f3c8" * 32):
            self.assertIn("64 UTF-16", ip.playcall_name_problems(value)[0])

    def test_authoring_rejects_a_name_the_native_formatter_would_execute(self):
        for value in ("Pass %s", "%d", "%R", "%%"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "formatter"):
                    writer._clean_custom_name(value)
                with self.assertRaisesRegex(packs.PlaybookPackError, "formatter"):
                    packs._name(value, "play")
        self.assertEqual(writer._clean_custom_name("Titans Post Wheel"), "Titans Post Wheel")

    def test_eight_twelve_and_thirty_six_links_are_valid(self):
        for count in (8, 12, 36):
            body = _body({0: [_link(i) for i in range(count)]})
            self.assertEqual(ip.playcall_ui_problems(body), [])

    def test_labels_on_defense_and_categories_are_checked(self):
        from tests.mod_editor.test_nfl2k5_play_menu_walk import BuildGateTests
        body = _body({0: [_link(1)]})
        # A defense family play still needs a literal name. Names are deliberately
        # shared in this tiny fixture, as they can be in real books.
        struct.pack_into("<I", body, ip.PLAY_BASE + ip.PLAY_SIZE + 4, 1 << 6)
        body[ip.STRING_BASE:ip.STRING_BASE + 6] = "%s\0".encode("utf-16le")
        problems = ip.playcall_ui_problems(body)
        self.assertTrue(any(p.startswith("play 1 ") and "formatter" in p for p in problems))
        self.assertTrue(any(p.startswith("category 0 ") and "formatter" in p for p in problems))
        with self.assertRaisesRegex(RuntimeError, "formatter"):
            BuildGateTests()._gate({307: b"PLAY" + bytes(28) + body})

    def test_missing_terminator_and_invalid_counts_refuse(self):
        body = _body({0: [_link(1)]})
        body[ip.STRING_BASE:] = b"X\0" * ((ip.BODY_SIZE - ip.STRING_BASE) // 2)
        self.assertTrue(any("not terminated" in p for p in ip.playcall_ui_problems(body)))
        struct.pack_into("<I", body, 0x3C, 27)
        self.assertTrue(any("category count" in p for p in ip.playcall_ui_problems(body)))

    def test_category_code_25_is_a_menu_terminator_not_a_26th_type(self):
        body = _body({0: [_link(1)]})
        body[ip.CATEGORY_BASE + 4] = 24
        self.assertEqual(ip.playcall_ui_problems(body), [])
        for code in (25, 63):
            body[ip.CATEGORY_BASE + 4] = code
            self.assertTrue(any("native menu range" in p for p in ip.playcall_ui_problems(body)))


class NativeUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn
        except ImportError:
            raise unittest.SkipTest("native pane replay needs Unicorn")
        folder = os.environ.get("NFL2K5_UI_INPUT")
        if folder:
            p = Path(folder)
            cls.xbe, cls.book, cls.fonts = ((p / n).read_bytes() for n in
                                           ("default.xbe", "ARZ.play", "entry3.bin"))
        else:
            from tests.mod_editor.test_nfl2k5_play_menu_walk import _retail, XBE
            from nfl2k5_playbook_position_recode import OuterImage
            cls.xbe, books = _retail()
            cls.book = books[307]
            with OuterImage(XBE.parent) as archive:
                cls.fonts = archive.read_entry(3)
        from tests.nfl2k5_user_play_menu_native import UserPlayMenuMachine
        cls.machine_type = UserPlayMenuMachine

    def test_native_formatter_boundary_and_null_argument_conversion(self):
        import unicorn
        m = self.machine_type(self.xbe, self.book, self.fonts)
        source, dest = 0x2401400, 0x2401800
        for n in (17, 63, 64):
            m.uc.mem_write(source, ("X" * n + "\0").encode("utf-16le"))
            m.uc.mem_write(dest, b"G" * 256)
            m.call(0x4A400, ecx=dest, edx=source, args=(0,))
            intact = bytes(m.uc.mem_read(dest + 128, 128)) == b"G" * 128
            self.assertEqual(intact, n < 64)
        m.uc.mem_write(source, "%s\0".encode("utf-16le"))
        with self.assertRaises(unicorn.UcError):
            m.call(0x4A400, ecx=dest, edx=source, args=(0,))

    def test_native_category_code_limit(self):
        m = self.machine_type(self.xbe, self.book, self.fonts)
        for code in range(64):
            self.assertEqual(m.call(0x222390, ecx=code), int(code <= ip.PLAYCALL_MAX_CATEGORY_CODE))

    def test_native_offense_defense_and_special_formation_pages(self):
        m = self.machine_type(self.xbe, self.book, self.fonts)
        for order in m.CATEGORY_ORDERS:
            categories = m.categories(order)
            self.assertTrue(categories)
            for page in range((len(categories) + 2) // 3):
                self.assertEqual(m.formation_page(order, page), categories[page*3:page*3+3])

    def test_both_units_draw_repeatedly_with_native_fonts_routes_and_icons(self):
        m = self.machine_type(self.xbe, self.book, self.fonts)
        book = ip.parse_playbook_resource(self.book)
        from mod_editor.core import nfl2k5_play_library as lib
        body = self.book[32:]
        offense = next(f for f in book.formations if lib.formation_record(body, f.index).type_code < 4)
        defense = next(f for f in book.formations if lib.formation_record(body, f.index).type_code == 4)
        for _ in range(2):
            for flip in (0, 1):
                for f in (offense, defense):
                    m.pane(f.index, flip=flip)
                    for link in f.play_links:
                        m.pane(f.index, link.play_index, flip=flip)
        self.assertGreater(m.vertices, 100)
        self.assertGreater(m.hits[0x2CB50], 0)  # Geometry reached the GPU boundary.
        self.assertGreater(m.hits[0x2CA70], 0)  # Font vertices reached it as well.
        self.assertEqual(m.reg("FPTAG"), 0xFFFF)

    def test_linter_includes_ui_rules_for_a_defensive_play(self):
        raw = bytearray(self.book)
        book = ip.parse_playbook_resource(raw)
        p = next(p for p in book.plays if p.family_id == 1)
        field = 32 + ip.PLAY_BASE + p.index * ip.PLAY_SIZE
        pointer = struct.unpack_from("<i", raw, field)[0] + field - 1
        raw[pointer:pointer + 6] = "%s\0".encode("utf-16le")
        findings = [f for f in lint.lint_resource(bytes(raw)).findings if f.code == "PLAYCALL_UI"]
        self.assertTrue(any(f"play {p.index} " in f.message for f in findings))


if __name__ == "__main__":
    unittest.main()

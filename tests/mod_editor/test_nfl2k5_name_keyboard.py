"""b77-k1: spaces, periods, apostrophes and hyphens in the in-game player-name keyboard.

Build wiring and constants need nothing private.  The byte, native and font tests need the pinned retail
``default.xbe`` (and, for fonts and the roster, the retail packs) and skip precisely without them; the
native ones also need Unicorn.  They run the game's own key table, filter and name handlers
(tests/mod_editor/name_keyboard_probe.py).  Nothing here is a played-game result.
"""
from pathlib import Path
import gc
import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core import nfl2k5_name_keyboard as nk
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core.nfl2k5_practice_squad import RETAIL_SHA256

try:
    from tests.mod_editor import name_keyboard_probe as probe
except ImportError:                                 # Unicorn is optional; the native classes skip without it
    probe = None

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
GAME = EXTRACTION / "ESPN NFL 2K5 (USA)"
XBE = GAME / "default.xbe"
PACK0 = GAME / "vc_53450030" / "0"
HAVE_NATIVE = probe is not None and XBE.is_file() and importlib.util.find_spec("unicorn") is not None
NATIVE_REASON = "pinned retail default.xbe and Unicorn required"

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
FOUR = " .'-"
NO_ROOM = "There isn't enough room left in this roster to edit any more names."
MATCH = "Audio database name match found!"


class ConstantsTests(unittest.TestCase):
    def test_character_sets(self):
        self.assertEqual(nk.NAME_CHARSET, LETTERS + "-' .")
        self.assertEqual(sorted(nk.NAME_CHARSET), sorted(LETTERS + FOUR))
        self.assertEqual(len(nk.NAME_CHARSET), 56)
        self.assertEqual(nk.RETAIL_FIRST, LETTERS)
        self.assertEqual(nk.RETAIL_LAST, LETTERS + "-'")

    def test_window_bytes(self):
        self.assertEqual(len(nk.RETAIL_WINDOW), nk.WINDOW_SIZE)
        self.assertEqual(len(nk.PATCHED_WINDOW), nk.WINDOW_SIZE)
        self.assertEqual(nk.PATCHED_WINDOW[:114].decode("utf-16le").rstrip("\0"), nk.NAME_CHARSET)
        self.assertEqual(nk.PATCHED_WINDOW[114:], b"\0" * (nk.WINDOW_SIZE - 114))
        self.assertEqual(nk.RETAIL_WINDOW[:0x70].decode("utf-16le").rstrip("\0"), nk.RETAIL_FIRST)
        self.assertEqual(nk.RETAIL_WINDOW[0x70:].decode("utf-16le").rstrip("\0"), nk.RETAIL_LAST)
        # the new literal is longer than either retail slot (0x70 bytes), which is why the immediate moves
        self.assertGreater(len(nk.NAME_CHARSET) * 2 + 2, 0x70)

    def test_sites_declare_exact_ranges(self):
        self.assertEqual([(label, va, len(before)) for label, va, before, _ in nk.SITES],
                         [("name_charset_literal", 0xEACAB0, 0xE0), ("last_name_keyboard_charset", 0x3465BA, 4)])
        for _, _, before, after in nk.SITES:
            self.assertEqual(len(before), len(after))
            self.assertNotEqual(before, after)

    def test_text_has_no_em_dash_and_names_the_limit(self):
        for text in (nk.HELP_TEXT, nk.UI_LABEL, nk.BUILD_CAPTION):
            self.assertNotIn("—", text)
        self.assertIn("12 characters", nk.HELP_TEXT)

    def test_foreign_payloads_read_foreign(self):
        self.assertEqual(nk.status(b""), "foreign")
        self.assertEqual(nk.status(b"XBEH" + bytes(0x400)), "foreign")
        with self.assertRaises(ValueError):
            nk.apply(b"not an xbe")


class CommentarySurnameTests(unittest.TestCase):
    """Studio-side surname matching keeps punctuation exactly as typed (never infers one name from another)."""

    def test_exact_spelling_with_punctuation(self):
        surname = rr.commentary_surname
        self.assertEqual(surname("St. Brown"), "st. brown")
        self.assertEqual(surname("O'Neal"), "o'neal")
        self.assertEqual(surname("Smith-Njigba"), "smith-njigba")
        self.assertEqual(surname("Van Ness"), "van ness")
        self.assertNotEqual(surname("St. Brown"), surname("St Brown"))
        self.assertNotEqual(surname("McBride"), surname("Mc-Bride"))

    def test_generation_suffix_only_is_dropped(self):
        surname = rr.commentary_surname
        for text, expected in (("Harrison Jr.", "harrison"), ("Pittman Jr", "pittman"), ("Walker III", "walker"),
                               ("Jones IV", "jones"), ("Ellis Sr.", "ellis"), ("Smith-Jones", "smith-jones"),
                               ("Juniors", "juniors"), ("Si", "si")):
            self.assertEqual(surname(text), expected, text)

    def test_recorded_bank_keys_are_already_canonical(self):
        bank = rr.recorded_surname_ids()
        self.assertTrue(bank)
        for key in bank:
            self.assertEqual(rr.commentary_surname(key), key)
            self.assertEqual(key, key.strip())


class BuildWiringTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("PyQt5"), "PyQt5 required")
    def test_gui_flag_roundtrip_and_source_gating(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        app = QApplication.instance() or QApplication([])
        panel = BuildPanel()
        try:
            panel.apply_state({"name_keyboard": "retail"})
            panel.name_keyboard_check.setChecked(True)
            saved = panel.project_build_settings()
            self.assertTrue(saved["name_keyboard"])
            panel.name_keyboard_check.setChecked(False)
            panel.restore_project_build_settings(saved)
            self.assertTrue(panel.plan().name_keyboard)
            panel.apply_state({"name_keyboard": "applied"})
            self.assertFalse(panel.name_keyboard_check.isChecked())
            self.assertFalse(panel.name_keyboard_check.isEnabled())
        finally:
            panel.deleteLater()
            app.processEvents()

    def test_default_presets_and_persistence(self):
        plan = mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"))
        self.assertFalse(plan.name_keyboard)
        self.assertFalse(plan.wants_xbe_patch())
        for preset in mod_build.PRESETS:
            self.assertTrue(mod_build.apply_preset(plan, preset).name_keyboard, preset)
        self.assertTrue(mod_build.BuildPlan(source=plan.source, target=plan.target, name_keyboard=True).wants_xbe_patch())
        self.assertIn("name_keyboard", settings.FEATURE_KEYS)
        self.assertTrue(mod_build.availability()["name_keyboard"])

    def test_dispatcher_and_writers_accept_the_flag(self):
        import inspect
        for function in (tt._apply_all, tt.write_xbe_copy, tt.write_image_copy):
            self.assertIn("name_keyboard", inspect.signature(function).parameters, function.__name__)


@unittest.skipUnless(XBE.is_file(), NATIVE_REASON)
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.patched, cls.receipt = nk.apply(cls.retail)

    def test_status_apply_verify_and_replay(self):
        self.assertEqual(nk.status(self.retail), "retail")
        self.assertEqual(nk.status(self.patched), "applied")
        self.assertEqual(nk.verify(self.patched)["status"], "applied")
        again, receipt = nk.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(nk.apply(self.retail)[0], self.patched)
        self.assertEqual(self.receipt["owner"], nk.OWNER)
        self.assertEqual(self.receipt["file_growth"], 0)
        self.assertFalse(self.receipt["runtime_witnessed"])

    def test_allowed_characters_read_back_from_the_operands(self):
        self.assertEqual(nk.allowed_characters(self.retail), {"first_name": nk.RETAIL_FIRST, "last_name": nk.RETAIL_LAST})
        self.assertEqual(nk.allowed_characters(self.patched), {"first_name": nk.NAME_CHARSET, "last_name": nk.NAME_CHARSET})

    def test_only_declared_ranges_and_section_digests_change(self):
        self.assertEqual(len(self.retail), len(self.patched))
        spans = []
        for _, va, before, _ in nk.SITES:
            offset = rdata.offset_of(self.retail, va)
            spans.append((offset, offset + len(before)))
        digests = 0
        for section in strength._sections(self.patched):
            self.assertEqual(self.patched[section.header_offset + 36:section.header_offset + 56],
                             strength.section_digest(self.patched, section))
            if self.patched[section.header_offset + 36:section.header_offset + 56] != \
                    self.retail[section.header_offset + 36:section.header_offset + 56]:
                spans.append((section.header_offset + 36, section.header_offset + 56))
                digests += 1
        self.assertEqual(digests, 2)                           # .text and .string_
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b]
        self.assertTrue(changed)
        self.assertTrue(all(any(lo <= i < hi for lo, hi in spans) for i in changed))
        # the Last Name keyboard operand is the only code byte range that moves; the message-box flag at 0x346567 stays
        self.assertEqual(self.patched[rdata.offset_of(self.patched, 0x346567):][:4], bytes.fromhex("20cbea00"))
        self.assertEqual(self.patched[rdata.offset_of(self.patched, 0x3465BA):][:4], bytes.fromhex("b0caea00"))
        self.assertEqual(self.patched[rdata.offset_of(self.patched, 0x3464C1):][:4], bytes.fromhex("b0caea00"))

    def test_mixed_and_corrupt_inputs_are_refused(self):
        for label, va, before, after in nk.SITES:
            data = bytearray(self.retail)
            offset = rdata.offset_of(data, va)
            data[offset:offset + len(after)] = after
            self.assertEqual(nk.status(bytes(data)), "foreign", label)
            with self.assertRaises(ValueError):
                nk.apply(bytes(data))
        for va, size, _digest in nk.GUARDS:
            for payload in (self.retail, self.patched):
                data = bytearray(payload)
                data[rdata.offset_of(data, va) + size // 2] ^= 1
                self.assertEqual(nk.status(bytes(data)), "foreign", hex(va))
                with self.assertRaises(ValueError):
                    nk.apply(bytes(data))

    def test_dispatcher_option_off_on_and_copy_writer(self):
        unchanged, _ = tt._apply_all(self.retail, None, catch_slider=False, name_keyboard=False)
        self.assertEqual(unchanged, self.retail)
        patched, receipt = tt._apply_all(self.retail, None, catch_slider=False, name_keyboard=True)
        self.assertEqual(patched, self.patched)
        self.assertIn("name_keyboard_patch", receipt)
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "in.xbe", Path(tmp) / "out.xbe"
            source.write_bytes(self.retail)
            tt.write_xbe_copy(source, target, name_keyboard=True)
            self.assertEqual(target.read_bytes(), self.patched)
            self.assertEqual(source.read_bytes(), self.retail)
            self.assertEqual(tt.read_xbe(target)["name_keyboard"], "applied")
            self.assertEqual(mod_build.inspect(target)["name_keyboard"], "applied")

    def test_composes_with_other_in_place_patches_in_either_order(self):
        from mod_editor.core import nfl2k5_position_row as position_row
        from mod_editor.core import nfl2k5_resource_load_guard as guard
        from mod_editor.core import nfl2k5_display_list_stability as display_list
        for other in (position_row, guard, display_list):
            other_first, _ = nk.apply(other.apply(self.retail)[0])
            keyboard_first, _ = other.apply(self.patched)
            self.assertEqual(other_first, keyboard_first, other.__name__)
            self.assertEqual(nk.status(other_first), "applied", other.__name__)
            self.assertEqual(other.status(other_first), "applied", other.__name__)


@unittest.skipUnless(HAVE_NATIVE, NATIVE_REASON)
class NativeKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.patched, _ = nk.apply(cls.retail)

    def machine(self, payload):
        machine = probe.keyboard_machine(payload)
        self.addCleanup(self._close, machine)
        return machine

    @staticmethod
    def _close(machine):
        machine.close()
        gc.collect()

    def drive(self, payload, handler, script, *, created=True, jersey=7, pool_chars=0x1000, first="Placeholder",
              last="Name", extra=()):
        machine = self.machine(payload)
        roster = probe.Roster(machine, pool_chars)
        others = [roster.player(f, l, audio, jersey=j, created=c) for f, l, audio, j, c in extra]
        player = roster.player(first, last, 0, created=created, jersey=jersey, on_team=False,
                               capacity=16 if created else None)
        machine.put(probe.PLAYER, player)
        typist = probe.Typist(machine, script)
        return machine, roster, player, typist, others

    # -- the table and the filter
    def test_key_table_is_a_full_qwerty_layout_with_the_punctuation_keys(self):
        machine = self.machine(self.retail)
        chars = probe.key_chars(machine)
        self.assertEqual(len(chars), 54)
        for key, label in ((0, "Esc"), (14, "Del"), (15, "Clear"), (29, "Caps"), (41, "Enter"), (42, "Shift")):
            self.assertEqual(chars[key], (label, label))
        self.assertEqual(chars[11], ("-", "_"))
        self.assertEqual(chars[40], ("'", '"'))
        self.assertEqual(chars[50], (",", "<"))
        self.assertEqual(chars[51], (".", ">"))
        self.assertEqual(chars[53], (" ", " "))
        self.assertEqual(chars[30], ("a", "A"))
        special = {k for k in range(54) if k not in probe.character_keys(machine)}
        self.assertEqual(special, {0, 14, 15, 28, 29, 41, 42})
        self.assertEqual(len(probe.character_keys(machine)), 47)
        for key in (11, 40, 51, 53):
            self.assertIn(key, probe.character_keys(machine))
        letters = {c for low, high in chars for c in (low, high) if len(c) == 1 and c.isalpha()}
        self.assertEqual("".join(sorted(letters)), LETTERS)

    def test_every_key_is_reachable_with_the_dpad_from_the_default_selection(self):
        machine = self.machine(self.retail)
        self.assertEqual(probe.reachable(machine), set(range(54)))

    def test_retail_filter_blocks_space_and_period_everywhere_and_first_name_hyphen_apostrophe(self):
        machine = self.machine(self.retail)
        pointers = probe.charset_pointers(machine)
        self.assertEqual(pointers, {"first_name": 0xEACAB0, "last_name": 0xEACB20})
        self.assertEqual(probe.typeable(machine, pointers["first_name"]), "".join(sorted(LETTERS)))
        self.assertEqual(probe.typeable(machine, pointers["last_name"]), "".join(sorted(LETTERS + "-'")))
        first = probe.typed_table(machine, pointers["first_name"])
        for key in (11, 40, 51, 53):
            self.assertEqual(first[(key, 0)], None)
            self.assertEqual(first[(key, 1)], None)

    def test_patched_filter_types_exactly_the_fifty_six_characters(self):
        machine = self.machine(self.patched)
        pointers = probe.charset_pointers(machine)
        self.assertEqual(pointers, {"first_name": 0xEACAB0, "last_name": 0xEACAB0})
        table = probe.typed_table(machine, pointers["last_name"])
        self.assertEqual("".join(sorted({c for c in table.values() if c})), "".join(sorted(nk.NAME_CHARSET)))
        # unshifted and shifted presses of the four punctuation keys give the unshifted character
        self.assertEqual((table[(11, 0)], table[(11, 1)]), ("-", "-"))
        self.assertEqual((table[(40, 0)], table[(40, 1)]), ("'", "'"))
        self.assertEqual((table[(51, 0)], table[(51, 1)]), (".", "."))
        self.assertEqual((table[(53, 0)], table[(53, 1)]), (" ", " "))
        # letters keep their case from the shift state; digits, symbols and the comma stay blocked
        self.assertEqual((table[(30, 0)], table[(30, 1)]), ("a", "A"))
        for key in (1, 2, 10, 12, 13, 26, 27, 39, 50, 52):
            self.assertEqual((table[(key, 0)], table[(key, 1)]), (None, None), key)

    def test_patched_filter_matches_for_the_first_name_pointer_too(self):
        machine = self.machine(self.patched)
        pointers = probe.charset_pointers(machine)
        self.assertEqual(probe.typeable(machine, pointers["first_name"]), "".join(sorted(nk.NAME_CHARSET)))

    def test_cap_is_enforced_by_the_keyboard(self):
        machine = self.machine(self.patched)
        probe.setup_keyboard(machine, 0xEACAB0, maxlen=12)
        a = probe.find_key(machine, "a")
        for _ in range(15):
            probe.press(machine, *a)
        self.assertEqual(machine.text(machine.word(probe.BUFFER)), "a" * 12)

    # -- the name handlers, end to end through the real keys
    NAMES_FIRST = ("D.K.", "Ja'Marr", "John Michael", "Amon-Ra", "Van")
    NAMES_LAST = ("St. Brown", "O'Neill", "Van Ness", "Smith-Njigba", "van den Berg")

    def test_first_name_handler_retail_drops_and_patched_keeps_the_punctuation(self):
        expected_retail = ("DK", "JaMarr", "JohnMichael", "AmonRa", "Van")
        for label, payload, expected in (("retail", self.retail, expected_retail), ("patched", self.patched, self.NAMES_FIRST)):
            machine, roster, player, typist, _ = self.drive(payload, probe.FIRST_HANDLER, self.NAMES_FIRST)
            for typed, want in zip(self.NAMES_FIRST, expected):
                typist.drive(probe.FIRST_HANDLER)
                record = typist.calls[-1]
                self.assertEqual(record["title"], "Enter First Name")
                self.assertEqual(record["maxlen"], 12)
                self.assertEqual(record["charset_va"], 0xEACAB0)
                self.assertEqual(record["buffer"], want, (label, typed))
                self.assertEqual(record["result"], 1)
                self.assertEqual(machine.text(machine.word(player + 0x10)), want, (label, typed))
                self.assertTrue(roster.guard_intact(machine.word(player + 0x10), 16), (label, typed))
            self.assertEqual(machine.text(machine.word(player + 0x14)), "Name")

    def test_last_name_handler_retail_drops_and_patched_keeps_the_punctuation(self):
        expected_retail = ("StBrown", "O'Neill", "VanNess", "Smith-Njigba", "vandenBerg")
        for label, payload, expected in (("retail", self.retail, expected_retail), ("patched", self.patched, self.NAMES_LAST)):
            machine, roster, player, typist, _ = self.drive(payload, probe.LAST_HANDLER, self.NAMES_LAST)
            for typed, want in zip(self.NAMES_LAST, expected):
                typist.drive(probe.LAST_HANDLER)
                record = typist.calls[-1]
                self.assertEqual(record["title"], "Enter Last Name")
                self.assertEqual(record["maxlen"], 12)
                self.assertEqual(record["charset_va"], 0xEACB20 if label == "retail" else 0xEACAB0)
                self.assertEqual(record["buffer"], want, (label, typed))
                self.assertEqual(machine.text(machine.word(player + 0x14)), want, (label, typed))
                self.assertTrue(roster.guard_intact(machine.word(player + 0x14), 16), (label, typed))
                self.assertEqual(machine.word(probe.DIRTY), 1)
            self.assertEqual(machine.text(machine.word(player + 0x10)), "Placeholder")

    def test_names_longer_than_the_twelve_character_cap_are_cut_and_nothing_overruns(self):
        for payload in (self.retail, self.patched):
            machine, roster, player, typist, _ = self.drive(payload, probe.FIRST_HANDLER, ["Abcdefghijklmno"])
            typist.drive(probe.FIRST_HANDLER)
            self.assertEqual(machine.text(machine.word(player + 0x10)), "Abcdefghijkl")
            self.assertTrue(roster.guard_intact(machine.word(player + 0x10), 16))

    def test_escape_and_empty_names_leave_the_stored_name_alone(self):
        for payload in (self.retail, self.patched):
            machine, roster, player, typist, _ = self.drive(payload, probe.FIRST_HANDLER,
                                                            [("Zed", "esc"), ""], first="Keep")
            typist.drive(probe.FIRST_HANDLER)
            self.assertEqual(typist.calls[-1]["result"], 2)
            self.assertEqual(machine.text(machine.word(player + 0x10)), "Keep")
            typist.drive(probe.FIRST_HANDLER)                    # Clear, then Enter on nothing: the loop reports a cancel
            self.assertEqual(typist.calls[-1]["result"], 2)
            self.assertEqual(machine.text(machine.word(player + 0x10)), "Keep")

    def test_real_player_names_go_to_the_shared_pool_and_a_full_pool_refuses_before_the_keyboard(self):
        machine, roster, player, typist, _ = self.drive(self.patched, probe.FIRST_HANDLER, ["D.K. Jr."],
                                                        created=False, first="Old")
        old = machine.word(player + 0x10)
        cursor = roster.pool_cursor()
        typist.drive(probe.FIRST_HANDLER)
        new = machine.word(player + 0x10)
        self.assertEqual(machine.text(new), "D.K. Jr.")
        self.assertEqual(new, cursor)
        self.assertEqual(roster.pool_cursor(), cursor + 2 * len("D.K. Jr.") + 2)
        self.assertEqual(machine.text(old), "Old")
        machine, roster, player, typist, _ = self.drive(self.patched, probe.FIRST_HANDLER, [], created=False,
                                                        first="Old", pool_chars=12)
        typist.drive(probe.FIRST_HANDLER)
        self.assertEqual(typist.messages, [NO_ROOM])
        self.assertEqual(typist.calls, [])
        self.assertEqual(machine.text(machine.word(player + 0x10)), "Old")

    # -- commentary: the typed last name against every other player's last name
    ROSTER = (("Amon-Ra", "St. Brown", 1234, 8, False), ("Eric", "O'Neill", 2345, 9, False),
              ("Lukas", "Van Ness", 3456, 10, False), ("Jaxon", "Smith-Njigba", 4567, 11, False),
              ("Some", "Rookie", 9301, 12, False), ("Created", "Guy", 777, 13, True))

    def last_name_audio(self, payload, typed):
        machine, roster, player, typist, _ = self.drive(payload, probe.LAST_HANDLER, [typed], extra=self.ROSTER)
        typist.drive(probe.LAST_HANDLER)
        return machine.half(player + 4), typist.messages, machine.text(machine.word(player + 0x14))

    def test_commentary_surname_match_works_with_spaces_periods_apostrophes_and_hyphens(self):
        for typed, audio in (("St. Brown", 1234), ("st. brown", 1234), ("ST. BROWN", 1234), ("O'Neill", 2345),
                             ("o'neill", 2345), ("Van Ness", 3456), ("Smith-Njigba", 4567)):
            got, messages, stored = self.last_name_audio(self.patched, typed)
            self.assertEqual((got, messages, stored.lower()), (audio, [MATCH], typed.lower()), typed)

    def test_commentary_match_is_exact_spelling_and_otherwise_falls_back_to_the_jersey_number(self):
        for typed in ("St Brown", "St.Brown", "St. Brown ", " St. Brown", "Van  Ness", "Smith Njigba", "Brown",
                      "Rookie", "Guy", "Nobody"):
            got, messages, stored = self.last_name_audio(self.patched, typed)
            self.assertEqual((got, messages, stored), (9007, [], typed), typed)      # 9000 + jersey 7

    def test_retail_keyboard_still_matches_apostrophe_and_hyphen_names_and_cannot_type_the_rest(self):
        self.assertEqual(self.last_name_audio(self.retail, "O'Neill")[:2], (2345, [MATCH]))
        self.assertEqual(self.last_name_audio(self.retail, "Smith-Njigba")[:2], (4567, [MATCH]))
        got, messages, stored = self.last_name_audio(self.retail, "St. Brown")
        self.assertEqual((got, messages, stored), (9007, [], "StBrown"))

    # -- the keyboard's other users are untouched
    def test_other_keyboard_prompts_keep_their_character_lists(self):
        callers = []
        text = [s for s in probe.XbeImage(self.retail).sections if s.name == ".text"][0]
        raw = self.retail[text.raw:text.raw + min(text.size, text.raw_size)]
        i = raw.find(b"\xe8")
        while i >= 0 and i + 5 <= len(raw):
            rel = struct.unpack_from("<i", raw, i + 1)[0]
            if (text.start + i + 5 + rel) & 0xFFFFFFFF == probe.KEYBOARD:
                callers.append(text.start + i)
            i = raw.find(b"\xe8", i + 1)
        self.assertEqual(len(callers), 17)
        names = {0x3464DE, 0x3465D7}
        self.assertEqual(len([c for c in callers if c not in names]), 15)
        for call in callers:
            if call in names:
                continue
            offset = rdata.offset_of(self.retail, call - 0x40)
            window = self.retail[offset:offset + 0x40]
            self.assertEqual(window, self.patched[offset:offset + 0x40], hex(call))
            pushed = [struct.unpack_from("<I", window, i + 1)[0] for i in range(len(window) - 4) if window[i] == 0x68]
            self.assertFalse([v for v in pushed if 0xEACAB0 <= v < 0xEACB90], hex(call))


@unittest.skipUnless(XBE.is_file() and PACK0.is_file() and probe is not None, "retail packs required")
class FontCoverageTests(unittest.TestCase):
    """Every FONT the game draws names with has U+0021..U+007E; a space is the font's space advance."""

    @classmethod
    def setUpClass(cls):
        cls.fonts = probe.font_resources(probe.read_outer(PACK0, 3))
        cls.fonts.update(probe.font_resources(probe.read_outer(PACK0, 347)))

    def test_all_ten_fonts_are_present_with_the_printable_ascii_range(self):
        self.assertEqual(sorted(self.fonts), sorted([f"font{i}" for i in range(1, 10)] + ["FirstPersonComic"]))
        for name, (chunk, decoded) in self.fonts.items():
            layout = probe.font_layout(decoded)
            self.assertLessEqual(layout["minimum"], 0x21, name)
            self.assertGreaterEqual(layout["maximum"], 0x7E, name)
            self.assertNotIn(0x20, layout["glyphs"], name)             # a space is never a glyph
            self.assertGreater(layout["space_advance"], 0, name)
            for character in ".'-" + LETTERS:
                self.assertIn(ord(character), layout["glyphs"], (name, character))

    def test_period_apostrophe_and_hyphen_cells_carry_ink_in_every_font(self):
        for name, (chunk, decoded) in self.fonts.items():
            layout = probe.font_layout(decoded)
            pixels = chunk.video_bytes - 1024
            size = probe.atlas_size(layout, pixels)
            self.assertIsNotNone(size, name)
            for character in ".'-":
                ink = probe.glyph_ink(decoded, chunk.system_bytes, chunk.video_bytes, layout, ord(character), *size)
                self.assertGreater(ink, 0, (name, character))
                self.assertGreater(layout["glyphs"][ord(character)]["advance"], 0, (name, character))

    @unittest.skipUnless(HAVE_NATIVE, NATIVE_REASON)
    def test_native_advance_is_the_glyph_for_punctuation_and_the_space_width_for_a_space(self):
        machine = probe.Machine(XBE.read_bytes())
        self.addCleanup(machine.close)
        for name, (chunk, decoded) in self.fonts.items():
            layout = probe.font_layout(decoded)
            font = probe.load_font(machine, decoded, layout)
            self.assertEqual(probe.font_advance(machine, font, " "), layout["space_advance"], name)
            for character in ".'-A":
                self.assertEqual(probe.font_advance(machine, font, character),
                                 layout["glyphs"][ord(character)]["advance"], (name, character))
            # a character the font has no glyph for advances by the space width (the game's own fallback)
            self.assertEqual(probe.font_advance(machine, font, "é"), layout["space_advance"], name)


@unittest.skipUnless(HAVE_NATIVE, NATIVE_REASON)
class NameplateTests(unittest.TestCase):
    """Jersey name plates: A-Z a-z ' - draw, a space is a hyphen-wide gap, everything else is skipped."""

    @classmethod
    def setUpClass(cls):
        cls.machine = probe.Machine(XBE.read_bytes())
        cls.metrics = [(32 * (i + 1), 5 + i) for i in range(29)]          # synthetic NAME records: advance 5 + index

    @classmethod
    def tearDownClass(cls):
        cls.machine.close()

    def width(self, text):
        return probe.nameplate_width(self.machine, text, self.metrics)

    def test_mapper(self):
        index = lambda text: probe.nameplate_index(self.machine, text)
        self.assertEqual((index("'"), index("-")), (0, 1))
        self.assertEqual((index("A"), index("a"), index("Z"), index("z")), (2, 2, 27, 27))
        for character in ". 1,!_é":
            self.assertEqual(index(character), -1, repr(character))

    def test_period_is_skipped_and_space_is_as_wide_as_the_hyphen(self):
        self.assertEqual(self.width("D.K."), self.width("DK"))
        self.assertEqual(self.width("St. Brown"), self.width("St Brown"))
        self.assertEqual(self.width("A B"), self.width("A-B"))
        self.assertEqual(self.width("Ja'Marr"), sum(self.metrics[i][1] + 1 for i in (2 + 9, 2 + 0, 0, 2 + 12, 2 + 0, 2 + 17, 2 + 17)) - 1)


@unittest.skipUnless(XBE.is_file() and PACK0.is_file(), "retail packs required")
class RosterCharacterTests(unittest.TestCase):
    """The shipped rosters use exactly these four punctuation characters; the retail keyboards could not type them all."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(GAME)
        cls.players = [p for p in rr.load_image(GAME).players if (p.first or p.last) and "*" not in p.first + p.last]

    def test_every_character_of_every_retail_name_is_typeable_after_the_patch(self):
        used = {c for p in self.players for c in p.first + p.last}
        self.assertEqual({c for c in used if not (c.isascii() and c.isalpha())}, set(FOUR))
        self.assertTrue(used <= set(nk.NAME_CHARSET))

    def test_the_retail_keyboards_could_not_type_some_of_them(self):
        first_blocked = {c for p in self.players for c in p.first if c not in nk.RETAIL_FIRST}
        last_blocked = {c for p in self.players for c in p.last if c not in nk.RETAIL_LAST}
        self.assertEqual(first_blocked, set(FOUR))
        self.assertEqual(last_blocked, {" ", "."})

    def test_names_longer_than_the_cap_exist(self):
        self.assertTrue([p.last for p in self.players if len(p.last) > 12])


if __name__ == "__main__":
    unittest.main()

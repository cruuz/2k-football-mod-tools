"""Offscreen drive of the Create a Play wizard against the real facade (private cache + retail XISO required)."""
import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = pathlib.Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
CACHE = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9")


@unittest.skipUnless(SRC.exists() and CACHE.exists(), "retail XISO / private cache missing")
class CreatePlayWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication, QMessageBox
        cls.app = QApplication.instance() or QApplication([])
        cls.warnings: list[str] = []
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.warning = staticmethod(lambda _p, _t, text, *a, **k: cls.warnings.append(str(text)))
        QMessageBox.critical = staticmethod(lambda _p, _t, text, *a, **k: cls.warnings.append(str(text)))
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        cls.facade = Nfl2k5StudioFacade()
        cls.facade.load_source(SRC, lambda *a: None)

    def test_full_flow_stages_replacements(self):
        from PyQt5.QtCore import Qt
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard
        import mod_editor.core.nfl2k5_play_library as lib
        w = CreatePlayWizard(self.facade)
        w.show()
        tp = w.page_team
        for i in range(tp.list.count()):
            if tp.list.item(i).text().startswith("ATL"):
                tp.list.setCurrentRow(i)
                tp.list.item(i).setSelected(True)
        self.assertTrue(tp.isComplete())
        w.next()
        fp = w.page_formation
        fp._use_template("Pistol Ace")
        self.assertEqual(fp._issues, [])
        w.next()
        tpg = w.page_type
        tpg.radios["pass"].setChecked(True)
        for i in range(tpg.concepts.count()):
            if tpg.concepts.item(i).data(Qt.UserRole) == "Smash":
                tpg.concepts.setCurrentRow(i)
        w.next()
        ap = w.page_assign
        self.assertIsNone(ap._error)
        ap._set(6, lib.PlayerAssignment("route", route="Corner"))
        self.assertIsNone(ap._error)
        ap.name_edit.setText("Pistol Smash")
        w.next()
        fz = w.page_finalize
        self.assertEqual(fz.table.rowCount(), 2)
        # the two cheap wins: the QB read order and the audible slot live on the play row
        from mod_editor.gui.create_play_wizard_qt import AUDIBLE_GROUPS, read_order_of
        self.assertEqual(fz.table.horizontalHeaderItem(4).text(), "QB read order")
        self.assertEqual(fz.table.horizontalHeaderItem(5).text(), "Audible slot")
        self.assertIsNone(fz.table.cellWidget(0, 4), "a formation row has no read order")
        spins = fz._read_orders[1][1]
        self.assertEqual([s.value() for s in spins], [1, 4, 2, 3])
        for spin, value in zip(spins, (2, 1, 3, 4)):
            spin.setValue(value)
        group_combo = fz._groups[1][1]
        self.assertEqual(group_combo.count(), len(AUDIBLE_GROUPS))
        group_combo.setCurrentIndex(2)          # "Audible 2 (group 1)"
        self.assertEqual(group_combo.currentData(), 1)
        fz._apply()
        self.assertIn("Staged 2", fz.status.text())
        session = self.facade._session
        designed_play = w.designed[0].plays[0]
        self.assertEqual(read_order_of(designed_play.chains[0]), (2, 1, 3, 4))
        self.assertEqual([r.custom_name for r in session.formation_creates], ["Pistol Ace"])
        self.assertIsNotNone(session.formation_creates[0].replace_index)
        self.assertEqual([r.custom_name for r in session.play_creates], ["Pistol Smash"])
        staged_play = session.play_creates[0]
        self.assertEqual(lib.play_class_label(staged_play.play_flags), "pass",
                         "a wizard pass must be staged under a pass-class header, not the first offensive play's run header")
        self.assertEqual(lib.qb_signature(lib.play_chains(w.body, staged_play.donor_play_index)[1][0][1]), "pass")
        self.assertTrue(session.formation_links)
        self.assertEqual([l.group for l in session.formation_links], [1],
                         "the audible slot chosen on the link step reaches the link request")
        staged_qb = staged_play.assignments[0]
        self.assertEqual([int(v) for v in next(n for n in staged_qb if n[0] == 0x06)[1][1:5]],
                         [2, 1, 3, 4], "the read order reaches the staged chain")

    def test_position_swap_and_drawn_routes(self):
        from PyQt5.QtCore import Qt
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard
        import mod_editor.core.nfl2k5_play_library as lib
        YD = lib.YD
        w = CreatePlayWizard(self.facade)
        w.show()
        tp = w.page_team
        for i in range(tp.list.count()):
            if tp.list.item(i).text().startswith("ATL"):
                tp.list.setCurrentRow(i)
                tp.list.item(i).setSelected(True)
        w.next()
        fp = w.page_formation
        fp._use_template("I-Form Pro")
        self.assertIsNone(fp.category_positions, "I-Form Pro is stock 'Pro' personnel")
        fb = next(s for s in range(11) if fp.kinds[s] == lib.FB)
        fp._select(fb)
        self.assertTrue(fp.pos_combo.isEnabled())
        hb_row = next(k for k in range(fp.pos_combo.count()) if fp.pos_combo.itemData(k) == lib.HB)
        fp.pos_combo.setCurrentIndex(hb_row)
        fp._position_changed(hb_row)
        self.assertIsNotNone(fp.category_positions, "HB + HB2 is not a stock mix, so a group gets written")
        self.assertIn("Jacks", fp.note)
        self.assertEqual(sorted(fp.labels[6:]), sorted(["TE", "WR", "WR2", "HB", "HB2"]))
        self.assertEqual(fp._issues, [])
        fp.name_edit.setText("I Two RB")
        w.next()
        tpg = w.page_type
        tpg.radios["pass"].setChecked(True)
        for i in range(tpg.concepts.count()):
            if tpg.concepts.item(i).data(Qt.UserRole) == "Mesh":
                tpg.concepts.setCurrentRow(i)
        w.next()
        ap = w.page_assign
        self.assertIsNone(ap._error)
        wr = next(s for s in range(11) if ap.spec.kinds[s] == lib.WR)
        x0, z0 = ap.spec.positions[wr]
        side = 1 if x0 >= 0 else -1
        ap.scene.finish_drawing(wr, [(x0, z0), (x0, z0 + 10 * YD), (x0 - side * 6 * YD, z0 + 16 * YD)])
        a = ap.spec.assignments[wr]
        self.assertEqual(a.kind, "custom")
        self.assertIn("post", a.route)
        self.assertIsNone(ap._error, "a drawn post must pass the game validator")
        self.assertIn("drawn", ap.jobs.item(wr).text())
        ap._clear_drawn(wr)
        self.assertNotEqual(ap.spec.assignments[wr].kind, "custom")
        ap.scene.finish_drawing(wr, [(x0, z0), (x0, z0 + 8 * YD), (x0 + side * 8 * YD, z0 + 8 * YD)])
        self.assertEqual(ap.spec.assignments[wr].kind, "custom")
        self.assertIsNone(ap._error)
        ap.name_edit.setText("Mesh Drawn")
        w.next()
        fz = w.page_finalize
        fz._apply()
        self.assertEqual(self.warnings, [])
        self.assertIn("Staged 2", fz.status.text())
        session = self.facade._session
        mine = next(r for r in session.formation_creates if r.custom_name == "I Two RB")
        self.assertEqual(mine.category_index, 0)
        self.assertIsNotNone(mine.category_positions)
        self.assertEqual(sorted(mine.category_positions), sorted(fp.codes))


if __name__ == "__main__":
    unittest.main()

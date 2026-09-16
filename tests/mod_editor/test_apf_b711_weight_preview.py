"""Draft situational weights use real SPLB bytes and the existing CPU model."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tests.mod_editor.test_apf_b69_schemes import fixture


class WeightPreviewTests(FacadeFixture):
    def setUp(self):
        super().setUp()
        book, master, _ = fixture()
        self.backend.initial.master = master
        self.backend.initial.books = {name: clone.clone_body(book, name)
                                      for name in self.backend.initial.books}
        self.backend.model = model
        self.backend.splb = splb

    def test_real_weight_changes_match_confirm_in_every_situation_without_preview_writes(self):
        context = self.facade.playcalling_context()
        form = context['formations'][0]['id']
        before = self.facade.playcalling_snapshot()
        preview = self.facade.preview_playcalling_ratings(context, 'offense', form, [1, 2, 7])
        self.assertEqual(len(preview['after']), 23)
        self.assertNotEqual(preview['before'], preview['after'])
        self.assertEqual(self.facade.playcalling_snapshot(), before)
        self.assertFalse(self.facade.session.can_undo)
        self.assertEqual(self.facade.confirm_playcalling([
            dict(kind='ratings', book=context['book'], formation=form, ratings=[1, 2, 7])])['staged'], [0])
        after = self.facade.playcalling_context()
        self.assertEqual(splb.formation_ratings(after['state'].books[context['book']], form), (1, 2, 7))
        self.assertEqual(self.facade.playcalling_situations(after, 'offense'), preview['after'])
        weights = {c['formation_weight'] for row in preview['after'] for c in row['candidates']}
        self.assertGreater(len(weights), 1, 'Different situations must interpolate the three ratings')

    def test_pending_preview_is_read_only_and_rejects_invalid_ratings(self):
        context = self.facade.playcalling_context()
        form = context['formations'][0]['id']
        pending = [dict(kind='ratings', book=context['book'], formation=form, ratings=[7, 7, 7])]
        result = self.facade.preview_playcalling_ratings(context, 'offense', form, [1, 1, 1], pending)
        self.assertNotEqual(result['before'], result['after'])
        self.assertFalse(self.facade.session.modifications)
        for ratings in ([8, 0, 0], [1, 2], [1, 2, float('nan')]):
            with self.assertRaises(ValidationError):
                self.facade.preview_playcalling_ratings(context, 'offense', form, ratings)
        self.assertFalse(self.facade.session.modifications)


if __name__ == '__main__': unittest.main()

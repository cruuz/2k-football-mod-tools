"""Scheme/clone and ROST persistence through the actual archive finalizer."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import playcalling_build, playcalling_service as service
from mod_editor.apf_studio.book_content import book_catalog
from mod_editor.core import apf2k8_book_identity as identity, apf2k8_book_clone as clone
from mod_editor.core import apf2k8_splb_writer as splb, apf2k8_playcall_model as model
from mod_editor.core import apf2k8_team_tendency as tendency
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tests.mod_editor.test_apf_book_unlock import archive_fixture
from tests.mod_editor.test_apf_b69_schemes import fixture


class BuildTests(FacadeFixture):
    def setUp(self):
        super().setUp()
        self.index=archive_fixture(self.root/'game')
        self.facade.source=self.facade.session.source=type(self.facade.source)(self.index.parent,self.index.parent,self.index,'d'*64,0,'e'*64,'Synthetic')
        book,master,rost=fixture()
        for name_id,inner,kind,body in ((identity.filename_id('O-ManBlock'),'spb','SPLB',book),
                                       (tendency.apf_roster.OUTER_NAME_ID,'roster','ROST',rost)):
            source=identity.read_resource(self.index,name_id,inner,kind)
            payload,_=clone.rebuild_resource(source,body)
            cursor=0
            for segment in source[1].segments:
                with (self.index.parent/segment.pack_name).open('r+b') as stream:
                    stream.seek(segment.pack_offset);stream.write(payload[cursor:cursor+segment.size])
                cursor+=segment.size
        self.backend.splb=splb;self.backend.model=model;self.backend.clone=clone;self.backend.tendency=tendency
        def load(session):
            books=book_catalog(session.source.index_0a)
            roster=identity.read_disc_roster(session.source.index_0a)
            parsed=identity.parse_roster_identity(roster)
            labels={r.index:r for r in parsed.labels}
            return service.State({b.name:b.body for b in books.values()},master,roster,
                tuple({'team_index':t.index,'team_name':t.name,'offense':labels[t.offense].kind,'defense':labels[t.defense].kind} for t in parsed.teams[:24]),
                {**splb.BOOK_SIDES,**{r.kind:r.side for r in parsed.labels}},
                {'formations':[{'index':0,'name':'Formation 0'}],'plays':[]})
        self.backend.load=load

    def test_scheme_build_reparses_cloned_book_tendency_rows_and_donor(self):
        donor=identity.read_resource(self.index,identity.filename_id('O-ManBlock'),'spb','SPLB')[3]
        request=self.facade.playcalling_scheme_plan(0,'wide_zone')
        self.stage(request)
        preview=self.facade.playcalling_context()
        receipt=playcalling_build.finalize(self.index,self.facade.session.modifications[0],backend=self.backend)
        self.assertEqual(receipt['teams_now_own_books'],['Synthetic Team 0'])
        self.assertTrue(receipt['verification']['content_reparsed'])
        built=identity.read_resource(self.index,identity.filename_id(preview['book']),'spb','SPLB')[3]
        self.assertEqual(built,preview['state'].books[preview['book']])
        self.assertEqual(identity.read_disc_roster(self.index),preview['state'].rost)
        self.assertEqual(tendency.team_tendency(identity.read_disc_roster(self.index),0),57)
        self.assertEqual(identity.read_resource(self.index,identity.filename_id('O-ManBlock'),'spb','SPLB')[3],donor)


if __name__=='__main__':unittest.main(verbosity=2)

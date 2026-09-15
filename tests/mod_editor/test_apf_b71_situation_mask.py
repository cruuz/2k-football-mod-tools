"""Authored-data, strict transport and persistent-project regressions."""
from pathlib import Path
import hashlib,json,struct,sys,tempfile,tomllib,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_situation_mask as m
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import situation_masks as transport
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


def policy(name='O-ManBlock',key=8,formations=(14,)):
    rows=[[] for _ in range(12)];rows[key]=list(formations);return {name:rows}


class DataTests(unittest.TestCase):
    def test_exact_data_roundtrip_and_independent_bits(self):
        data=m.encode_data(policy())
        self.assertEqual(m.decode_data(data),policy())
        self.assertEqual(len(data),13824)
        self.assertEqual(data[16:44],b'O-ManBlock'.ljust(28,b'\0'))
        expected=struct.pack('>4I',0x41504634,1,1,268)+b'O-ManBlock'.ljust(28,b'\0')+bytes(8*20)+struct.pack('>5I',1<<14,0,0,0,0)+bytes(3*20)
        self.assertEqual(data,expected.ljust(13824,b'\0'))
        self.assertEqual(m.decode_data(m.encode_data({})),{})
        for form in (0,31,32,63,64,95,96,127,128,150):
            self.assertEqual(m.decode_data(m.encode_data(policy(formations=(form,)))),policy(formations=(form,)))

    def test_refuse_bad_data_names_versions_padding_and_specials(self):
        for name in ('','a'*28,'../book','Unicodeé'):
            with self.assertRaises(ValidationError):m.encode_data(policy(name))
        for values in ((151,),(14,14),(True,),(-1,)):
            with self.assertRaises(ValidationError):m.encode_data(policy(formations=values))
        for offset in (4,15,43,13823):
            data=bytearray(m.encode_data(policy()));data[offset]^=1
            with self.assertRaises(ValidationError):m.decode_data(bytes(data))
        with self.assertRaises(ValidationError):m.encode_data({str(i):policy()['O-ManBlock'] for i in range(49)})

    def test_exact_key_boundaries_sign_and_no_aliases(self):
        for down in range(1,5):
            for distance, bucket in ((0,0),(182.88,0),(182.9,1),(640.08,1),(640.1,2),(9144,2)):
                for sign in (-1,1):self.assertEqual(m.live_key(down,distance*sign),(down-1)*3+bucket)
        for distance in (float('nan'),float('inf')):
            with self.assertRaises(ValidationError):m.live_key(1,distance)

    def test_canonical_toml_rejects_foreign_and_duplicate_writes(self):
        for p in m.PROFILES:
            document=m.SituationPatch(p,m.encode_data(policy()))
            payload=document.as_toml().encode()
            self.assertEqual(m.canonical_payload(payload),(p,True))
            parsed=tomllib.loads(payload.decode());self.assertEqual(len(parsed['patch'][0]['be32']),len(document.words))
            for changed in (payload.replace(b'value = 0x4800',b'value = 0x4801',1),payload+b'\n[[patch.be32]]\naddress=1\nvalue=2\n',payload.replace(b'title_id = "54540807"',b'title_id = "00000000"')):
                if changed!=payload:
                    with self.assertRaises(ValidationError):m.canonical_payload(changed)
            self.assertEqual(m.canonical_payload(payload.replace(b'is_enabled = true',b'is_enabled = false')),(p,False))

    def test_leaf_decode_ownership_and_pass_fetch_composition(self):
        from mod_editor.core import apf2k8_playcall_patch as legacy
        for p in m.PROFILES:
            code,hooks=m.assemble(p);m.verify_code(p,code)
            self.assertLessEqual(m.CODE_START+len(code),m.CODE_LIMIT)
            self.assertLessEqual(legacy.CAVE_START+len(legacy.assemble_cave(p.hook)),m.CODE_START)
            authored=dict(m.SituationPatch(p,m.encode_data(policy())).words)
            old=dict(legacy.PlaycallPatch(p,legacy.assemble_cave(p.hook),{}).words)
            self.assertFalse(authored.keys()&old.keys())
            with self.assertRaises(ValidationError):m.verify_code(p,code[:-4])


class ProjectTests(FacadeFixture):
    def test_masks_default_off_stage_replay_undo_and_export(self):
        from mod_editor.apf_studio.situation_masks import prepare,export_build
        engine=self.facade._playcalling;session=self.facade.session
        initial=engine.state(session)
        self.assertFalse(initial.situation_masks_enabled);self.assertEqual(initial.situation_masks,{})
        requests=[{'kind':'situation_masks_enabled','enabled':True},
                  {'kind':'situation_mask','book':'O-ManBlock','key':8,'formation':62,'exclude':True}]
        for request in requests:self.facade.stage_playcalling(self.facade.playcalling_review(request))
        state=engine.state(session)
        self.assertEqual(state.books,initial.books)
        self.assertEqual(state.situation_masks['O-ManBlock'][8],[62])
        self.assertEqual(state.situation_masks['O-ManBlock'][7],[])
        self.assertEqual(m.decode_data(m.SituationPatch(m.PROFILES[0],m.encode_data(state.situation_masks)).data),state.situation_masks)
        with tempfile.TemporaryDirectory() as temporary:
            receipt=export_build(Path(temporary),state)
            self.assertEqual(len(receipt['patches']),2)
            for row in receipt['patches']:m.canonical_payload((Path(temporary)/row['file']).read_bytes())
            self.assertEqual(m.decode_data((Path(temporary)/'situation-masks.bin').read_bytes()),state.situation_masks)
        project=session.save_project(self.root/'situation-masks.apf2k8mod')
        session.undo();session.undo()
        self.assertFalse(engine.state(session).situation_masks_enabled)
        self.assertEqual(session.load_project(project),1)
        self.assertEqual(engine.state(session).situation_masks,state.situation_masks)
        # Exercise the product's existing event serialization contract.
        modification=next(x for x in session.modifications if x.kind=='apf_playcalling')
        from mod_editor.apf_studio.playcalling_service import read_profile,State
        events=read_profile(modification);replayed=initial
        for event in events:
            replayed,checked=engine.apply(replayed,event['request'],session.source.index_0a)
            self.assertEqual(checked,event)
        self.assertEqual(replayed.situation_masks,state.situation_masks)
        # Loading restores one project transaction; one undo returns to the
        # pre-load empty state, while per-edit undo was checked before save.
        session.undo();self.assertFalse(engine.state(session).situation_masks_enabled)
        with tempfile.TemporaryDirectory() as temporary:self.assertIsNone(export_build(Path(temporary),engine.state(session)))


if __name__=='__main__':unittest.main()

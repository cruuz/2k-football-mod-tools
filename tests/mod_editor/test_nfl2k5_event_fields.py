"""SoFi routing, calendar composition and event-field refusal contracts."""
import ast
import json
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core import nfl2k5_calendar_engine as calendar
from mod_editor.core import nfl2k5_stadium_shared_art as shared
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256

XBE = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')


def build_route(payload, sofi):
    """Execute the actual builder's executable-only season and SoFi blocks in RAM.

    AST selects whole production statements, stopping before schedule/archive
    I/O. This checks argument forwarding without invoking a disc build.
    """
    tree = ast.parse((ROOT / 'mod_editor/core/mod_build.py').read_text())
    block = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == 'plan.season_2026'
                 and any(isinstance(x, ast.Assign) and ast.unparse(x.targets[0]) == 'state'
                         for x in n.body))
    state = next(n for n in block.body if isinstance(n, ast.If) and ast.unparse(n.test) == "state == 'retail'")
    route = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == 'plan.modern_sofi'
                 and 'route_sofi_super_bowl' in ast.unparse(n))
    memory = [payload]
    env = dict(season=season, xbe=payload, state=season.simple_status(payload), target='memory',
               plan=SimpleNamespace(modern_sofi=sofi), receipt={'steps': []},
               _core_module=lambda _: season, _xbe_bytes=lambda _: memory[0],
               _write_xbe_bytes=lambda _, b: memory.__setitem__(0, b))
    exec(compile(ast.Module(body=[state, route], type_ignores=[]), 'mod_build routing blocks', 'exec'), env)
    return memory[0], env['receipt']


@unittest.skipUnless(XBE.is_file(), 'private retail XBE absent')
class Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        assert mv.sha(cls.retail) == RETAIL_SHA256

    def test_build_routes_and_later_rotation_with_calendar_overlay(self):
        for sofi, expected in [(False, 0x1332e1), (True, 0x1332c5)]:
            with self.subTest(sofi=sofi):
                out, _ = build_route(self.retail, sofi)
                self.assertEqual(season.simple_status(out), 'applied')
                self.assertEqual(XbeImage(out).read(season.SB_VENUE_TABLE_VA,20),
                                 struct.pack('<5I',expected,0x1332cc,0x1332d3,0x1332da,0x1332e1))
                self.assertEqual(XbeImage(out).read(0x1332b0,0xa1), XbeImage(self.retail).read(0x1332b0,0xa1))
                complete, _ = calendar.apply(out)
                self.assertEqual(calendar.status(complete),'applied')
                self.assertEqual(season.simple_status(complete),'applied')
                self.assertEqual(season.status(complete)['super_bowl_venue'],'s40' if sofi else 's44')

    def test_off_is_exact_legacy_default_and_reapplication_is_idempotent(self):
        old, _ = season.apply(self.retail)
        self.assertEqual(build_route(self.retail,False)[0],old)
        self.assertEqual(build_route(old,False)[0],old)
        new, _ = build_route(old,True)
        fresh, _ = build_route(self.retail,True)
        self.assertEqual(new,fresh)
        self.assertEqual(build_route(new,True)[0],new)
        self.assertEqual(build_route(new,False)[0],new)  # Off never undoes existing art/routing.

    def test_migrate_existing_calendar_overlay_and_preserve_other_bytes(self):
        old,_ = calendar.apply(season.apply(self.retail)[0])
        new, receipt = season.route_sofi_super_bowl(old)
        self.assertFalse(receipt['already_applied'])
        image = XbeImage(old)
        off=season._offset(old,season.SB_VENUE_TABLE_VA,season._sections(old))
        section=season._section_for_offset(season._sections(old),off)
        allowed=set(range(off,off+4)) | set(range(section.header_offset+36,section.header_offset+56))
        self.assertEqual(len(old),len(new))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(old,new)) if a!=b))
        self.assertEqual(calendar.status(new),'applied')
        self.assertEqual(season.simple_status(new),'applied')
        self.assertEqual(calendar.apply(new)[0],new)

    def test_foreign_route_refuses_even_for_noop_s40_calendar_site(self):
        good,_=season.apply(self.retail,super_bowl_venue=season.SOFI_SB_VENUE)
        off=season._offset(good,season.SB_VENUE_TABLE_VA,season._sections(good))
        bad=bytearray(good);bad[off:off+4]=b'FAIL';bad=bytes(bad)
        self.assertEqual(season.simple_status(bad),'foreign')
        self.assertEqual(season.group_status(bad,'calendar',super_bowl_venue=season.SOFI_SB_VENUE),'foreign')
        with self.assertRaises(ValueError):season.route_sofi_super_bowl(bad)
        with self.assertRaises(ValueError):calendar.apply(bad)


class FieldContract(unittest.TestCase):
    def test_variant_missing_material_and_size_changes_refuse(self):
        item=dict(dd={'scene':'field'},key='logo',kind='field-logo',variants={'ns':[2,256,256]})
        for mapped,row in [({},{}),({'logo':1},{1:dict(width=256,height=256)}),
                           ({'logo':2},{2:dict(width=128,height=256)})]:
            with patch.object(mv,'rows_by_material',return_value=mapped),patch.object(mv,'p8_rows',return_value=row):
                with self.assertRaises(ValueError):mv.variant_index(item,'ns',{})

    def test_registry_pins_event_policy_and_table(self):
        doc=json.loads((ROOT/'mod_editor/capabilities/registry.v1.json').read_text())
        rows=doc['capabilities']
        entry=next(r for r in rows if r['id']=='nfl2k5.stadiums_fields.modern_venues_2026')
        for path in (shared.EVENT_PATH,shared.TABLE_PATH):
            self.assertIn(mv.sha(path.read_bytes()),entry['source_container']['hash_pins'])
        self.assertIn('data/nfl2k5_stadium_shared_art/event_fields.json',entry['evidence'])


if __name__ == '__main__':
    unittest.main()

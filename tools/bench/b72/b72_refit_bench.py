"""Real refit on 24 staged synthetic items; measures full-project preflights."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
ROOT = Path(os.environ.get('B72_ROOT', Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from b71_t5_project_probe import Corpus
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core import nfl2k5_equipment_lz as lz
from mod_editor.core import equipment_staging as staging


def run(helper):
    with tempfile.TemporaryDirectory(prefix='b72-refit-') as folder:
        corpus = Corpus(Path(folder), 24)
        session = corpus.session()
        with corpus.context(), patch.object(writer, '_stage_disk_cache', side_effect=OSError('disabled')):
            session.load_shareable_project(corpus.project)
            writer._STAGED_CACHE.clear()
            writer._PARSE_CACHE.clear()
            counts = []
            original = writer.preflight_project_equipment
            def count(index, edits, **kwargs):
                edits = list(edits)
                counts.append(len(edits))
                return original(index, edits, **kwargs)
            with patch.object(writer, 'preflight_project_equipment', side_effect=count), \
                 (patch.object(lz, '_optimal_helper', return_value=None) if not helper
                  else patch.object(lz, 'OPTIMAL_SECONDS', lz.OPTIMAL_SECONDS)):
                started = time.perf_counter()
                result = staging.refit_equipment(session, corpus.rows[0].asset_id)
                return dict(helper=helper, items=24, seconds=time.perf_counter()-started,
                    preflight_rows=counts, full_project_preflights=counts.count(24),
                    outcome='fit', message=result.message)

if __name__ == '__main__':
    rows = [run(helper) for helper in (False, True)]
    print(json.dumps(rows, indent=2), flush=True)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(rows, indent=2))

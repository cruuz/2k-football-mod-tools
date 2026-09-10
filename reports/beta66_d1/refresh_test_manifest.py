"""Observe the full XBE gate into a scratch manifest; never build a disc.

Reuse the bounded recorder used for beta 65, with this job's explicit source
scope. The collection helper's instruction writes belong to the observed
metadata owner, just as generic read-only data writes belong to their caller.
The protected production manifest remains untouched.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.mycareer_mode import refresh_settings_manifest as projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".scratch/beta66_d1_manifest.json")
    args = parser.parse_args()
    non_xbe = dict(projection.NON_XBE)
    for name in ("nfl2k5_music_banks", "nfl2k5_music_build", "nfl2k5_save_rost"):
        non_xbe[f"mod_editor/core/{name}.py"] = "resource/recipe/save API; standalone suite evidence, no XBE ownership claim"
    with patch.object(projection, "NON_XBE", non_xbe), \
            patch.object(projection, "CHANGED_WRITERS", {
                "nfl2k5_music_metadata", "nfl2k5_music_policy", "nfl2k5_music_playlist"}), \
            patch.object(projection, "SHARED_HELPERS", projection.SHARED_HELPERS | {"nfl2k5_music_collections"}):
        summary = projection.refresh(args.output)
    document = json.loads(args.output.read_bytes())
    document["model"] = "BOUNDED BETA-66 D1 XBE PROJECTION; historical retail reservations and observed forward gate stack; no disc build"
    document["beta66_d1_projection"] = document.pop("settings_projection")
    document["beta66_d1_projection"]["collection_helper_owner"] = "nfl2k5_music_metadata"
    args.output.write_bytes((json.dumps(document, indent=2) + "\n").encode())
    summary["manifest_sha256"] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

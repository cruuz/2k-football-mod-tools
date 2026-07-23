#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/nfl-draft-weight-integrity.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1

source_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
source_hash='73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
before="$(sha256sum "$source_xbe" | cut -d' ' -f1)"
test "$before" = "$source_hash"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_draft_weight_xbe_integrity_probe.py \
  tests/nfl_draft_weight_xbe_integrity_probe_test.py
python3 -m unittest -v tests/nfl_draft_weight_xbe_integrity_probe_test.py
python3 tools/nfl_draft_weight_xbe_integrity_probe.py \
  --output "$temporary/probe.json"
cmp reports/gameplay_tuning/nfl_draft_weight_xbe_integrity_probe.json \
  "$temporary/probe.json"

python3 - <<'PY'
import json
from pathlib import Path

path = Path("reports/gameplay_tuning/nfl_draft_weight_xbe_integrity_probe.json")
payload = path.read_bytes()
report = json.loads(payload)
assert payload == (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
assert report["schema"] == "nfl2k5_draft_weight_xbe_integrity_probe/v1"
assert report["target"]["float_count"] == 17
assert report["target"]["table_sha256"] == \
    "bf53338927a98ffc13f5c591d8cdc216f16691975ef9f27144fdad98f282098e"
assert report["target"]["section"]["stored_digest"] == \
    "167a8c5810298ff4af2e297359328ad79210fc9b"
assert report["hypothetical_edit"]["changed_table_byte_count"] == 1

stale = report["integrity_branches"]["payload_only_stale_section_digest"]
assert stale["section_digest_matches"] is False
assert stale["signed_header_changed"] is False
assert stale["signed_header_digest_before"] == stale["signed_header_digest_after"]

updated = report["integrity_branches"]["payload_plus_updated_section_digest"]
assert updated["section_digest_matches"] is True
assert updated["signed_header_changed"] is True
assert updated["section_digest_header_byte_changes"] == 20
assert updated["original_rsa_signature_bytes_reused"] is True
assert updated["signed_header_digest_before"] != updated["signed_header_digest_after"]

assert report["scope"]["copied_xbe_created"] is False
assert report["claims"]["draft_weight_writer_proved"] is False
assert report["claims"]["integrity_blocker_reproduced_in_memory"] is True
doc = " ".join(Path("docs/research/nfl_draft_weight_xbe_integrity_probe.md").read_text().split())
for phrase in (
    "does not create a patched XBE",
    "payload-only branch",
    "digest-repaired branch",
    "not a writer",
    "Original Xbox hardware",
):
    assert phrase in doc, phrase
PY

after="$(sha256sum "$source_xbe" | cut -d' ' -f1)"
test "$after" = "$before"
echo 'NFL_DRAFT_WEIGHT_XBE_INTEGRITY_VALIDATION_PASS weights=17 payload_only=section_fail digest_repaired=signed_header_changed writer=false source_unchanged=yes'

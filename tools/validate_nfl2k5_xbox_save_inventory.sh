#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -v XEMU_XBOX_HDD_QCOW2 ]]; then
  QCOW_WAS_EXPLICIT=1
else
  QCOW_WAS_EXPLICIT=0
fi
QCOW=${XEMU_XBOX_HDD_QCOW2:-/home/noah/.var/app/app.xemu.xemu/data/xemu/xemu/xbox_hdd.qcow2}
QEMU_IMG=${NFL2K5_QEMU_IMG:-/usr/bin/qemu-img}
EXPECTED_QCOW_SIZE=1769668608
EXPECTED_QCOW_SHA256=ccd94e4f52b18ae7e171d95223e994a0028b13f22a2417d2bfb1175480e947b3
EXPECTED_IMAGE_SHA256=a495f735a6ca39ca7f476757d832fab5f535270cc675552c8c1ae9e32263fa13
EXPECTED_QEMU_IMG_SIZE=2480872
EXPECTED_QEMU_IMG_SHA256=fd095f52d483230c957fe48eea7ac19ef0bc85feb5db347be6a5a4c811d854c1
EXPECTED_XBE_SIZE=11948032
EXPECTED_XBE_SHA256=73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
EXPECTED_LEDGER_SIZE=9431836
EXPECTED_LEDGER_SHA256=902eb0e5f504bcc24ee55aa895d8fa65e4cb3db05409eb8daaf147e3d74f28f7
EXPECTED_REPORT_SIZE=31477
EXPECTED_REPORT_SHA256=e49d30bc9adb87faf1a592a9d3a529169659be8f926be9db9028c90009477e3c
EXPECTED_INVENTORY_TSV_SIZE=1441
EXPECTED_INVENTORY_TSV_SHA256=be6248fd86e880048aec8591dbc415251e18ca7556ed3c5ae41246813d26278e
EXPECTED_SLIDER_TSV_SIZE=1004
EXPECTED_SLIDER_TSV_SHA256=9a834b703801d82c695de5f4fee04fe38bf502f1b26201359dfa344beffac74a
RAW_NAME=xemu-hdd-readonly.raw

file_identity() {
  stat --printf='%d:%i:%s:%f:%y:%z:%h' "$1"
}

descriptor_identity() {
  stat --dereference --printf='%d:%i:%s:%f:%y:%z:%h' "$1"
}

pin_qemu_img() {
  case "$QEMU_IMG" in
    /*) ;;
    *) echo 'NFL2K5_QEMU_IMG must be an absolute path' >&2; return 2 ;;
  esac
  test -x "$QEMU_IMG" || return 1
  test -f "$QEMU_IMG" || return 1
  test ! -L "$QEMU_IMG" || return 1
  test "$(stat --printf='%h' "$QEMU_IMG")" = 1 || return 1
  test "$(stat --printf='%s' "$QEMU_IMG")" = "$EXPECTED_QEMU_IMG_SIZE" || return 1
  qemu_img_path_stat_before=$(file_identity "$QEMU_IMG") || return 1

  exec {QEMU_IMG_FD}<"$QEMU_IMG" || return 1
  qemu_img_fd_path="/proc/$$/fd/$QEMU_IMG_FD"
  qemu_img_fd_stat_before=$(descriptor_identity "$qemu_img_fd_path") || return 1
  test "$qemu_img_fd_stat_before" = "$qemu_img_path_stat_before" || return 1
  test -x "$qemu_img_fd_path" || return 1
  qemu_img_hash_before=$(sha256sum "$qemu_img_fd_path" | awk '{print $1}') || return 1
  test "$qemu_img_hash_before" = "$EXPECTED_QEMU_IMG_SHA256" || return 1
  QEMU_IMG_EXEC="/proc/self/fd/$QEMU_IMG_FD"
}

verify_qemu_img_unchanged() {
  qemu_img_hash_after=$(sha256sum "$qemu_img_fd_path" | awk '{print $1}') || return 1
  qemu_img_fd_stat_after=$(descriptor_identity "$qemu_img_fd_path") || return 1
  test ! -L "$QEMU_IMG" || return 1
  test "$(stat --printf='%h' "$QEMU_IMG")" = 1 || return 1
  qemu_img_path_stat_after=$(file_identity "$QEMU_IMG") || return 1
  test "$qemu_img_hash_after" = "$qemu_img_hash_before" || return 1
  test "$qemu_img_fd_stat_after" = "$qemu_img_fd_stat_before" || return 1
  test "$qemu_img_path_stat_after" = "$qemu_img_path_stat_before" || return 1
}

stage_pinned_copy() {
  local source=$1
  local destination=$2
  local expected_size=$3
  local expected_hash=$4
  test -f "$source"
  test ! -L "$source"
  test "$(stat --printf='%s' "$source")" = "$expected_size"
  local source_path_before
  source_path_before=$(file_identity "$source")
  exec {STAGE_FD}<"$source"
  local source_fd_path="/proc/$$/fd/$STAGE_FD"
  local source_fd_before
  source_fd_before=$(descriptor_identity "$source_fd_path")
  test "$source_fd_before" = "$source_path_before"
  test "$(sha256sum "$source_fd_path" | awk '{print $1}')" = "$expected_hash"

  cp --reflink=never -- "$source_fd_path" "$destination"
  chmod 0400 "$destination"
  test -f "$destination"
  test ! -L "$destination"
  test "$(stat --printf='%h' "$destination")" = 1
  test "$(stat --printf='%s' "$destination")" = "$expected_size"
  test "$(stat --printf='%a' "$destination")" = 400
  test "$(sha256sum "$destination" | awk '{print $1}')" = "$expected_hash"

  local source_fd_after source_path_after
  source_fd_after=$(descriptor_identity "$source_fd_path")
  source_path_after=$(file_identity "$source")
  test "$(sha256sum "$source_fd_path" | awk '{print $1}')" = "$expected_hash"
  test "$source_fd_after" = "$source_fd_before"
  test "$source_path_after" = "$source_path_before"
  exec {STAGE_FD}<&-
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

umask 077
TEMPORARY=$(mktemp -d /tmp/nfl2k5-save-inventory.XXXXXX)
trap 'rm -rf "$TEMPORARY"' EXIT
export PYTHONDONTWRITEBYTECODE=1

STAGED_XBE="$TEMPORARY/default.xbe"
STAGED_LEDGER="$TEMPORARY/functions.tsv"
stage_pinned_copy \
  "$ROOT/extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  "$STAGED_XBE" "$EXPECTED_XBE_SIZE" "$EXPECTED_XBE_SHA256"
stage_pinned_copy \
  "$ROOT/research/functions/nfl2k5/functions.tsv" \
  "$STAGED_LEDGER" "$EXPECTED_LEDGER_SIZE" "$EXPECTED_LEDGER_SHA256"

STAGED_REPORT="$TEMPORARY/committed-inventory.json"
STAGED_INVENTORY_TSV="$TEMPORARY/committed-inventory.tsv"
STAGED_SLIDER_TSV="$TEMPORARY/committed-sliders.tsv"
stage_pinned_copy \
  "$ROOT/reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json" \
  "$STAGED_REPORT" "$EXPECTED_REPORT_SIZE" "$EXPECTED_REPORT_SHA256"
stage_pinned_copy \
  "$ROOT/reports/gameplay_tuning/nfl2k5_xbox_save_inventory.tsv" \
  "$STAGED_INVENTORY_TSV" \
  "$EXPECTED_INVENTORY_TSV_SIZE" "$EXPECTED_INVENTORY_TSV_SHA256"
stage_pinned_copy \
  "$ROOT/reports/gameplay_tuning/nfl2k5_xbox_save_slider_snapshot.tsv" \
  "$STAGED_SLIDER_TSV" \
  "$EXPECTED_SLIDER_TSV_SIZE" "$EXPECTED_SLIDER_TSV_SHA256"

PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest tests.test_nfl2k5_xbox_save_inventory

python3 - "$STAGED_REPORT" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_xbox_save_inventory/v1"
assert report["summary"] == {
    "franchise_payload_size": 720044,
    "safe_writer_proved": False,
    "save_container_count": 8,
    "save_type_counts": {"FXG": 1, "STG": 1, "TMM": 5, "USR": 1},
    "settings_payload_size": 736,
    "settings_prefix_join_proved": True,
    "signature_owner_proved": True,
    "slider_field_count": 21,
    "title_id": "53450030",
}
assert report["scope"] == {
    "platform_keys_read_or_emitted": False,
    "read_only": True,
    "retail_or_save_bytes_emitted": False,
    "runtime_load_test_performed": False,
    "save_writer_exposed": False,
    "signature_writer_exposed": False,
    "source_image_modified": False,
}
snapshot = report["slider_snapshot"]
assert len(snapshot["rows"]) == 21
assert snapshot["settings1_sha256"] == "b4e40e69fa7014d5172a52ff3821b88485e3255272ad5a884687b2c48a7204d9"
assert snapshot["franchise1_sha256"] == "0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7"
assert snapshot["franchise1_settings_prefix_sha256"] == "71164badf9f2bd063ba4e7a9fb93da9c112a20b4a4e075c9b43673420444e75a"
assert [row["offset"] for row in snapshot["rows"]] == [
    "0x284", "0x288", "0x28C", "0x298", "0x29C", "0x2A0", "0x2A4",
    "0x2A8", "0x2AC", "0x2B0", "0x2B4", "0x2B8", "0x2BC", "0x2C0",
    "0x2C4", "0x2C8", "0x2CC", "0x2D0", "0x2D4", "0x2D8", "0x2DC",
]
signature = report["executable_evidence"]["signature_owner"]
assert signature["begin"]["XCalculateSignatureBegin_mode"] == 0
assert signature["stream_update_and_read_validation"]["reads_EXTRA_size"] == 20
assert signature["write_close"]["writes_EXTRA_size"] == 20
assert signature["current_EXTRA_cryptographically_recomputed"] is False
assert report["modding_boundary"]["read_only_slider_inspector_ready"] is True
assert report["modding_boundary"]["stock_range_writer_ready"] is False
PY

case "$QCOW" in
  /*) ;;
  *) echo 'XEMU_XBOX_HDD_QCOW2 must be an absolute path' >&2; exit 2 ;;
esac
fixture_reason=''
if test ! -e "$QCOW"; then
  fixture_reason=missing
elif test ! -f "$QCOW" || test -L "$QCOW"; then
  fixture_reason=not-regular
elif test "$(stat --printf='%h' "$QCOW")" != 1; then
  fixture_reason=link-count
elif test "$(stat --printf='%s' "$QCOW")" != "$EXPECTED_QCOW_SIZE"; then
  fixture_reason=size
else
  qcow_path_stat_before=$(file_identity "$QCOW")
  exec {QCOW_FD}<"$QCOW"
  qcow_fd_stat_before=$(descriptor_identity "/proc/$$/fd/$QCOW_FD")
  if test "$qcow_fd_stat_before" != "$qcow_path_stat_before"; then
    fixture_reason=identity
  else
    qcow_hash_before=$(sha256sum "/proc/$$/fd/$QCOW_FD" | awk '{print $1}')
    if test "$qcow_hash_before" != "$EXPECTED_QCOW_SHA256"; then
      fixture_reason=sha
    fi
  fi
  if test -n "$fixture_reason"; then
    exec {QCOW_FD}<&-
  fi
fi

if test -n "$fixture_reason"; then
  if test "$QCOW_WAS_EXPLICIT" = 1; then
    echo "NFL2K5_XBOX_SAVE_INVENTORY_ERROR explicit canonical QCOW refused reason=$fixture_reason" >&2
    exit 1
  fi
  echo "NFL2K5_XBOX_SAVE_INVENTORY_VALIDATION_PASS mode=committed-evidence-only containers=8 types=USR,STG,FXG,TMM sliders=21 writer=false committed_evidence=true private_reproduction=false canonical_private_fixture=unavailable reason=$fixture_reason"
  exit 0
fi

pin_qemu_img

"$QEMU_IMG_EXEC" info --output=json "/proc/self/fd/$QCOW_FD" \
  > "$TEMPORARY/qcow-info.json"
python3 - "$TEMPORARY/qcow-info.json" <<'PY'
import json
from pathlib import Path
import sys

info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert info["format"] == "qcow2"
assert info["virtual-size"] == 8 * 1024**3
assert info["cluster-size"] == 65_536
assert info["dirty-flag"] is False
assert "backing-filename" not in info
assert "full-backing-filename" not in info
specific = info["format-specific"]
assert specific["type"] == "qcow2"
assert specific["data"] == {
    "compat": "1.1",
    "compression-type": "zlib",
    "corrupt": False,
    "extended-l2": False,
    "lazy-refcounts": False,
    "refcount-bits": 16,
}
assert [(row["id"], row["name"]) for row in info["snapshots"]] == [
    ("1", "vm-20251230230718"),
    ("2", "vm-20251230230725"),
    ("3", "vm-20260106230659"),
]
PY

(
  cd "$TEMPORARY"
  "$QEMU_IMG_EXEC" convert -f qcow2 -O raw -S 4096 \
    "/proc/self/fd/$QCOW_FD" "$RAW_NAME"
  chmod 0400 "$RAW_NAME"
  test -f "$RAW_NAME"
  test ! -L "$RAW_NAME"
  test "$(stat --printf='%h' "$RAW_NAME")" = 1
  test "$(stat --printf='%s' "$RAW_NAME")" = $((8 * 1024**3))
  test "$(stat --printf='%a' "$RAW_NAME")" = 400
  raw_stat_before=$(stat --printf='%d:%i:%s:%Y:%Z:%h' "$RAW_NAME")

  python3 "$ROOT/tools/nfl2k5_xbox_save_inventory.py" \
    --image "$RAW_NAME" \
    --expected-image-sha256 "$EXPECTED_IMAGE_SHA256" \
    --xbe "$STAGED_XBE" \
    --ledger "$STAGED_LEDGER" \
    --json-out "$TEMPORARY/inventory.json" \
    --inventory-tsv-out "$TEMPORARY/inventory.tsv" \
    --slider-tsv-out "$TEMPORARY/sliders.tsv"

  raw_hash_after=$(sha256sum "$RAW_NAME" | awk '{print $1}')
  raw_stat_after=$(stat --printf='%d:%i:%s:%Y:%Z:%h' "$RAW_NAME")
  test "$raw_hash_after" = "$EXPECTED_IMAGE_SHA256"
  test "$raw_stat_after" = "$raw_stat_before"
)

cmp "$TEMPORARY/inventory.json" "$STAGED_REPORT"
cmp "$TEMPORARY/inventory.tsv" "$STAGED_INVENTORY_TSV"
cmp "$TEMPORARY/sliders.tsv" "$STAGED_SLIDER_TSV"

qcow_hash_after=$(sha256sum "/proc/$$/fd/$QCOW_FD" | awk '{print $1}')
qcow_fd_stat_after=$(
  descriptor_identity "/proc/$$/fd/$QCOW_FD"
)
test ! -L "$QCOW"
test "$(stat --printf='%h' "$QCOW")" = 1
qcow_path_stat_after=$(file_identity "$QCOW")
test "$qcow_hash_after" = "$qcow_hash_before"
test "$qcow_fd_stat_after" = "$qcow_fd_stat_before"
test "$qcow_path_stat_after" = "$qcow_path_stat_before"
exec {QCOW_FD}<&-

verify_qemu_img_unchanged
exec {QEMU_IMG_FD}<&-

echo 'NFL2K5_XBOX_SAVE_INVENTORY_VALIDATION_PASS mode=private-reproduction containers=8 types=USR,STG,FXG,TMM sliders=21 settings_prefix=0x2E0 signature_owner=true extra=20 writer=false committed_evidence=true private_reproduction=true qcow_pinned=true raw_rebuilt=true originals_unchanged=true'

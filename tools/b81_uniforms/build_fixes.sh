#!/bin/bash
# build_fixes.sh : compile every authored picture in work/fix/art (kit textures) and work/fix/all_digits (digits) against the
# released v0.9 disc into the two documents of the worktree, write the compiled pictures and the corrected kit folders.
set -euo pipefail
U=/home/noah/2k-worktrees/.b77-scratch/b81/uniforms; WT=/home/noah/2k-worktrees/b81-uniforms
DISC="/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"
cd "$WT"; rm -rf "$U/work/fix/decoded"; mkdir -p "$U/out"
nice -n 19 python3 tools/b81_uniform_pass.py build --image "$DISC" --art "$U/work/fix/art" --notes "$U/work/fix/notes/kits.json" \
  --out data/nfl2k5_kit_fixes_2026_b81u.json --receipt "$U/out/kits_receipt.json" --decoded "$U/work/fix/decoded"
nice -n 19 python3 tools/b81_uniform_pass.py digits --image "$DISC" --art "$U/work/fix/all_digits" --notes "$U/work/fix/notes/digits.json" \
  --out data/nfl2k5_glyph_fixes_2026_b81u.json --receipt "$U/out/digits_receipt.json" --decoded "$U/work/fix/decoded" | tail -1
python3 "$U/tools/mk_after.py" "$U/work/fix/decoded" "$U/work/fix/after" | awk '{print $1}' | tr '\n' ' '; echo

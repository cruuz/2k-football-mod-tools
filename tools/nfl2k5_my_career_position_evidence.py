#!/usr/bin/env python3
"""Read-only beta-65 per-position evidence. Outputs metadata, never retail bytes.

Native execution is in test_nfl2k5_my_career_position_inputs.py. A command
being decoded/dispatched does not prove movement, animation or a completed catch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage

# (name, start, size, SHA256), read-only USA executable evidence.
SPANS = (
    ('context_tables', 0xa99ec0, 0x1a94, '17610a4f79595587f8b0648749f1f5fe946c92ea9ef37f22d6f69248b5d0758e'),
    ('command_handlers', 0xaabef8, 0x274, 'c2d49816fbc3d7bd80b5f63c873eb18a20f6255c971547e2e268280aa64978d1'),
    ('input_walk', 0x1563f0, 0x175, '06ccb17132899bf9daeaa7dce6b7fc7f554c5866c15d92ffa28a46b93194c900'),
    ('body_context', 0x1565f0, 0x50, '148ec66bae26f22e654a2a6a2376ae13ecee310b182e7c857f039262ad62a2a1'),
    ('port_context', 0x120880, 0x10, '5cde7c15551a0914fbbd483a56c0be4b5c8e18a61374ac718b1f9739c9e3306a'),
    ('context_mask', 0x120730, 0x5f, '8811523c13ed41c7363904d8b25e885ab057da5bf59dd0d4b3ccc264d1431678'),
    ('stick_and_buttons', 0x1211e0, 0xd0, 'cdf04ccd4ba54547e9f51089891248244ccbd893c2d15d6e694827f2f1c2137c'),
    ('button_decoder', 0x120a20, 0x7c0, '3972d8e3b9250006f88b4e831309c432338b5674a3f6592b09a3e4ffc4c0eaa0'),
    ('snap_contexts', 0x1569e0, 0x77, '2e7ee4cae07dca2c339246776aca3d5438f923fb773ef1e43073a52338640e48'),
    ('alignment_contexts', 0xaf000, 0x88, '65640cb691d73c53a29988d1127b51029e017c785f7d8f14670b13c3bb9bf155'),
    ('presnap_contexts', 0x9f990, 0x100, '344446946fb729cf7d5b06db3f4d2388638c29d8dd9c97547e91e6a69cbac3d2'),
    ('qb_contexts', 0x1d0f20, 0x80, '02ed24517bcab7738f3aa0ca639e250b4d3f6c934505238bd31684a4ae4840e1'),
    ('dispatch', 0x18ec40, 0x5f, 'a6391fed20582d34d21034343c1ee11712a0fceb6f3eac7a3d8fd6ae28087da1'),
    ('offball_command67', 0x18fac0, 0x118, '17844da888618b83a6fe38ec29a0807c787d8ee2013f10eaff487e24e20ef31c'),
    ('offball_command68', 0x18df00, 0x37, '3958f45d5d8fced6cc56095ee58b6589d0a597c4f79953741cc89e6d6a111e2a'),
    ('engaged_moves', 0x18dbe0, 0x35, '6739f3708103a00c562c1afca77c52872b6b6f4e1e9a7722e9b5f10a160c1e07'),
    ('move_accumulator', 0x2324f0, 0x160, '34bdf0e4a31f04c5256662bd33b686740bcc6538f70f64c1a18de17ad4a8d4a6'),
    ('auto_switch', 0x1a7970, 0x140, 'dfc6e92d3fa8a6708f872d76b859bf4b26d15bbdf4ed8242754be187a9aaed88'),
    ('fpf_entry', 0x2c1fc0, 0xea, '295963ff88f45742858e40d64e5473ecb62fc7cfe278277ab7c855d1bd182f5b'),
    ('fpf_predicate', 0x627c0, 0x27, 'fdadb321f7e06421e44f9f07f071a726416b90d6ef651b55fe5ebe49abf8e03c'),
    ('fpf_receiver_selection', 0x1b7a90, 0x650, '118e62127212961f2989f42665e3542f0a0dc25b3c8b027a383b97e8100a71ee'),
    ('kick_handler', 0x18f8c0, 0x200, '4bf3816b4f7e32a2ba7483fb8d12da590795ff3634162b4a52aa0a40aa5bbf15'),
    ('playcall_owner', 0x1891b0, 0x120, 'a44fd0c91dc874aeb5b9f3f4f453258bdab780d435810bca5434e91e35ee2bc1'),
    ('switch_target_selector', 0x1a83b0, 0x60, 'd4e0dbb73c70937d3e05262bff980f84c303c8e52bc5abe972209f871f57da79'),
    ('manual_transfer', 0x1a85e0, 0x93, 'dac8d0dde27ea527f3cfb75afe89ca4cfe42c0fd9813458f806b961777548fff'),
    ('auto_request', 0x1a7ae0, 0xe7, '930eff63a067de88797f92be9b319bcb6985ea9a59ee338106137c1173d63069'),
 )
CONTEXTS = (2, 3, 4, 5, 6, 8, 9, 10, 11, 15, 16)


def inspect(payload):
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise ValueError("position evidence requires pinned USA retail default.xbe")
    im = XbeImage(payload)
    for name, va, size, digest in SPANS:
        if hashlib.sha256(im.read(va, size)).hexdigest() != digest:
            raise ValueError("position evidence span differs: " + name)
    layouts = {}
    for layout in range(3):
        layouts[str(layout)] = {str(context): list(struct.unpack('<27I', im.read(
            0xA99EC0 + (layout * 21 + context) * 108, 108))) for context in CONTEXTS}
    return {"retail_sha256": RETAIL_SHA256,
            "spans": [{"name": n, "va": hex(v), "size": s, "sha256": h} for n,v,s,h in SPANS],
            "layouts": layouts, "fpf_flag": "0xE5FFE4 (global)",
            "body_specific_fpf_route_mode_proved": False, "rendered_play_witnessed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xbe', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.xbe.read_bytes()), indent=2))


if __name__ == '__main__':
    main()

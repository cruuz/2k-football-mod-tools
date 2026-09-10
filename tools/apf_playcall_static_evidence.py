#!/usr/bin/env python3
"""Print selected instruction evidence and bounded direct-caller scans.

Read-only, BASE SHA-pinned, flat VA mapping. This is a static evidence index,
not a claim that indirect callers or all computed address loads were found.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core.apf2k8_playcall_patch import IMAGE_BASE, IMAGE_SIZE, PROFILES

SITES = {
    "Retry, category dispatch and actual CPU path": {
        0x8486CF74:"Formation/null argument to category chooser",
        0x8486CF78:"Increment retry ordinal (not a descriptor index)",
        0x8486CF84:"Call category chooser",
        0x8486D084:"Last retry ordinal 3",
        0x8486D088:"Retry branch",
        0x8486C958:"Formation family word",
        0x8486C95C:"Family shift by 26",
        0x8486C9E4:"Manager mode +0x34",
        0x8486C9B4:"Punt row 17",
        0x8486C9DC:"Generic special row 25",
        0x8486CA1C:"Kickoff row 21",
        0x8486CA44:"Onside row 22",
        0x8486CA70:"Field-goal row 19",
        0x8486CAB8:"Book-bound category chooser",
        0x8486CF94:"Returned category's row byte +4",
        0x8486D05C:"Ordinary CPU weighted play picker",
        0x8486D08C:"Emergency fetch subtype -1",
        0x8486D09C:"Emergency whole-book fetch",
    },
    "Output pointer, UI fields and live-state candidates": {
        0x84815608:"Output-global high half",
        0x8481560C:"Output-global signed low half",
        0x84815664:"r4 points at output staging +0x10",
        0x8481566C:"Tail branch to picker",
        0x8486CEA0:"Preserve output pointer in r23",
        0x8486CEC4:"UI tab +0x2BC",
        0x8486CEDC:"UI subtype +0x1F8",
        0x8486D0B8:"Write output category",
        0x8486D0C0:"Write output formation",
        0x8486D0C4:"Write output play",
        0x84A3752C:"Practice candidate down +0x254",
        0x84A37858:"Practice candidate down +0x254",
        0x84A3785C:"Practice candidate distance +0x25C",
        0x8486BF1C:"Live state pointer +0x6C",
        0x8486BF20:"Live state field +4",
        0x8486BF24:"Compare that field with 4; down meaning remains inference",
        0x84868D8C:"Live state float +0x18",
        0x84868D90:"Live state float +0x28",
        0x84868D98:"Distance-like subtraction, live units not proved",
        0x84868DA0:"Absolute value",
        0x84A3CED8:"Mode-9 override gate",
        0x84A3CEF4:"Override object pointer +0x118",
        0x84A3CF00:"Override object's requested row +6",
    },
    "Reverse lookup, secondary mask and regeneration": {
        0x84A8A2B8:"First entry of candidate record",
        0x84A8A2C0:"First-empty sentinel",
        0x84A8A2C4:"Return null at first empty",
        0x84A8A2C8:"Record formation index byte",
        0x84A8C5C4:"Reverse lookup through first matching record",
        0x84A8C5C8:"Primary trailer word A",
        0x84A8C5D0:"Primary category multiplied by 16",
        0x84A8C5D8:"MASTER category base +0x44",
        0x84A8A398:"Secondary category membership word B",
        0x84A8C7C0:"Normalizer addresses category cache +0x7E04",
        0x84A8C800:"Normalizer addresses formation cache +0x7D98",
        0x84A8C83C:"Normalizer addresses play cache +0x7DB0",
        0x84A8CB6C:"Read populated primary word A",
        0x84A8CBA0:"Store accumulated primary category mask",
        0x84A8CBB0:"Read word B, first unrolled bit",
        0x84A8CBF0:"OR secondary membership into book mask",
        0x84A8CC00:"Read word B, second unrolled bit",
        0x84A8CC4C:"Read word B, third unrolled bit",
        0x84A8CC90:"Read word B, fourth unrolled bit",
        0x84A8CCD0:"All 32 secondary category bits",
        0x84A8CCD4:"Continue secondary-mask folding",
        0x84A8CD00:"First tail array +0x7970",
        0x84A8CD0C:"Five items in tail array",
        0x84A8CD34:"Stored formation byte in tail item",
        0x84A8CD6C:"Stored play u16 in tail item",
        0x84A8CE64:"Repair from static row priorities through current book",
        0x84A8CF50:"Second five-item tail array +0x7984",
        0x84A9AE28:"Static priority list's first row",
        0x84A9AE4C:"Static priority list's next row",
        0x84A9AE58:"Priority row validity helper",
        0x84A8B508:"Resolve priority row through book category mask",
        0x84A8B90C:"Require candidate formation word-B compatibility",
    },
    "Special formation caches and their book-bound initialization": {
        0x84864D9C:"First formation from current book",
        0x84864E7C:"Cache special formation +0x50",
        0x84864E84:"Resolve its primary category from SPLB",
        0x84864E88:"Cache category +0x54",
        0x84864E94:"Cache offensive Hail Mary formation +0x58",
        0x84864E9C:"Resolve offensive Hail Mary category from SPLB",
        0x84864EA0:"Cache category +0x5C",
        0x84864EAC:"Cache defensive Hail Mary formation +0x60",
        0x84864EB4:"Resolve defensive Hail Mary category from SPLB",
        0x84864EB8:"Cache category +0x64",
        0x84864EC4:"Next formation iterator",
        0x8486D008:"Read cached offensive special formation",
        0x8486D01C:"Read cached defensive special formation",
        0x8486BD4C:"Safety Kick name lookup argument",
        0x8486BE1C:"Read cached formation +0x58",
        0x8486BE20:"Store temporary formation +0x684",
        0x8486BE30:"Store temporary play +0x680",
        0x8486D068:"Consume temporary formation +0x684",
        0x8486BE74:"Read cached special formation +0x50",
    },
    "Lineup role bytes and substitution inputs": {
        0x848605AC:"Category role-byte base +5",
        0x848605B4:"Read category role byte for slot",
        0x848605C0:"Role low five bits",
        0x848605CC:"Assign role to lineup slot",
        0x848608F8:"Wrapper reads category from caller object +0",
        0x84860900:"Wrapper reads formation from caller object +4",
        0x84A2734C:"UI preview reads cached category from object +0x4C",
        0x84A8ACE8:"Book substitution array +0x7998",
        0x84A8ACEC:"256 packed entries",
        0x84A8ACF0:"Packed substitution word",
        0x84A8ACF4:"Scope bits 12..13",
        0x84A8AD00:"Selector bits 2..11",
        0x84A8AD0C:"At most 12 matching overrides",
        0x847B2E54:"Category scope 1",
        0x847B2E60:"Collect category-scoped substitutions",
        0x847B2E80:"Formation scope 2",
        0x847B2E8C:"Collect formation-scoped substitutions",
        0x847B2EBC:"Global override table signed low half",
        0x847B2EC4:"Merge global overrides",
        0x84A9B1D8:"Category row selects preset family",
        0x84A9B2F4:"Packed operation kind",
        0x84A9B314:"Packed source role/slot bits 22..29",
        0x84A9B324:"Packed target role/slot bits 14..21",
        0x84A9B32C:"Reversal bit 1",
        0x847B2F3C:"Resolve role low five bits",
        0x847B2F50:"Resolve depth high three bits",
        0x847B2FEC:"Resolve roster player",
    },
    "Fetch, classifiers and audible initialization": {
        0x848699E4:"r27 = subtype argument",
        0x848699E8:"r29 = current book",
        0x848699EC:"r24 = family argument",
        0x848699F0:"r30 = optional formation argument",
        0x84869AA4:"40-candidate capacity",
        0x84869AAC:"Append MASTER play pointer",
        0x84869B20:"Displaced hook instruction",
        0x84869B28:"Existing RNG call",
        0x84869B34:"Existing divide by candidate count",
        0x848682E0:"Pass subtype 2 classifier",
        0x848682F8:"Pass subtype 3 classifier",
        0x84868310:"Pass subtype 4 classifier",
        0x84865180:"Pass classifier metadata load",
        0x8486518C:"Pass flag bit 1",
        0x8486519C:"Pass flag decision",
        0x84865078:"Run classifier metadata load",
        0x8486507C:"Run flag bit 3",
        0x84865084:"Run flag decision",
        0x84864BF4:"Extract existing audible tag",
        0x84864BF8:"Compare requested tag",
        0x84864BFC:"Skip filling an already present tag",
    },
}

CALLER_ORIGINS = {
    0x848608AC:"Row resolver: book-advertised category; null formation",
    0x84860910:"Caller state object +0 category, +4 formation; upstream ownership not closed",
    0x84861338:"Field-goal row 19 through book row lookup; special formation",
    0x84862530:"Existing formation iterator then primary category resolver",
    0x84868024:"First current-book formation then primary category resolver",
    0x84868104:"Selected formation then primary category resolver",
    0x84868174:"Next formation then primary category resolver",
    0x84A273A8:"UI preview: cached object +0x4C category or record resolution; virtual formation getter",
    0x84A2748C:"Second build in the same UI preview path",
    0x84A98FB0:"Dialog wrapper takes category argument unless formation supplies record category",
    0x84A992BC:"Second dialog wrapper; same conditional category argument",
}


def render(image):
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    if len(image) != IMAGE_SIZE or hashlib.sha256(image).hexdigest() != PROFILES[0].sha256:
        raise ValueError("Expected the pinned BASE flat image")
    md = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)

    def instruction(address):
        data = image[address-IMAGE_BASE:address-IMAGE_BASE+4]
        decoded = list(md.disasm(data,address))
        if len(decoded) != 1:
            raise ValueError(f"Undecodable evidence instruction {address:08X}")
        i = decoded[0]
        return f"`{address:08X}` | `{data.hex().upper()}` | `{i.mnemonic} {i.op_str}`"

    print("\n## Instruction appendix: selected BASE evidence\n")
    print("All rows are A_PROVEN for the displayed instruction/operation only; causal and mode-specific grades remain as stated above. Regenerate with `python3 tools/apf_playcall_static_evidence.py --image <pinned-apf.pe>`.\n")
    for group, sites in SITES.items():
        print(f"### {group}\n\n| VA | BE word | Capstone decode | Meaning / limit |\n| --- | --- | --- | --- |")
        for address, meaning in sites.items():
            print(f"| {instruction(address)} | {meaning} |")
        print()
    callers, normalizers, multiplies = [], [], []
    for address in range(0x84630000,0x84D10000,4):
        word = struct.unpack_from(">I",image,address-IMAGE_BASE)[0]
        if word>>26 == 18 and not word & 2:
            delta = word & 0x3FFFFFC
            if delta & 0x2000000: delta -= 0x4000000
            target = address + delta
            if target == 0x84860020: callers.append(address)
            if target == 0x84A8C790: normalizers.append(address)
        if word>>26 == 7 and word & 0xFFFF == 184:
            multiplies.append(address)
    if set(callers) != set(CALLER_ORIGINS):
        raise ValueError("Direct lineup-builder caller census differs from reviewed evidence")
    print("### Complete direct builder-call census in 84630000..84D10000\n\n| VA | BE word | Decode | Category / formation provenance |\n| --- | --- | --- | --- |")
    for address in callers:
        print(f"| {instruction(address)} | {CALLER_ORIGINS[address]} |")
    print("\nNormalizer direct callers ("+str(len(normalizers))+"): "+", ".join(f"`{a:08X}`" for a in normalizers)+".\n")
    print("Formation-stride mulli sites ("+str(len(multiplies))+"): "+", ".join(f"`{a:08X}`" for a in multiplies)+".\n")
    print("These scans enumerate these instruction encodings; computed or indirect references require separate tracing.\n")
    print("### Dispatch tables are code pointers\n")
    for address,count in ((0x8486C980,13),(0x8486CA0C,4)):
        targets=struct.unpack_from(f">{count}I",image,address-IMAGE_BASE)
        if not all(0x84630000 <= t < 0x84D10000 and t%4 == 0 for t in targets):
            raise ValueError("Dispatch table target outside text")
        print(f"`{address:08X}` ({count} BE code-address entries): "+", ".join(f"`{t:08X}`" for t in targets)+".\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    args = parser.parse_args()
    render(args.image.read_bytes())

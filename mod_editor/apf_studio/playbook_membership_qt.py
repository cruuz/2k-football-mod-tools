"""Edit the stock CPU playbooks APF 2K8 ships.

Reassigning which book a team calls from -- all the community's editor can do,
and all this product could do before -- is a coarse control: the 36 offensive
and 33 defensive book records in a roster save are *labels* that resolve to
seven offensive and four defensive real books, so the swap frequently changes
nothing at all.

This panel edits those real books.  Each is an on-disc ``SPLB`` resource of
exactly 32,288 bytes holding a 176-record array; a populated record names a
MASTER formation and stores a list of plays for it, as big-endian u16 entries
whose low ten bits are the MASTER play index.  Ticking a play rewrites only
that record's entry list.  The executable counts that list at ``0x84a8ac30``
and returns the nth play at ``0x84a8bd20``; runtime which-play-on-3rd-and-long
behaviour remains unproved.

Everything else is preserved and independently re-derived before publication:
the record trailer, every other record, the two tail regions whose meaning is
not established, and every other byte of the volume.

A formation also carries tagged slots -- ``min(4, plays)`` of them in every one
of the 209 populated retail records, with no exceptions -- and they are authored
per formation rather than falling out of position.  Three of them are the
formation's audibles: the game writes a slot number into bits 12-10 of an entry
at ``0x84864c78`` and runs that counter 0, 1, 2 while stepping 176 bytes -- one
SPLB record -- per formation, and swaps a slot between plays at ``0x84a8ab28``.
Slot 4 marks an untagged play.  The fourth tagged slot, 3, is never written by
that loop, but ``0x84a850f0`` looks it up with the other three (counter 0..3).
That is not a proof of 3rd-and-long CPU play-calling. MASTER categories
(Ace, 5 Wide, Flush) are personnel packages; ``0x8485bd38`` extracts the
SPLB trailer index. ``0x84a472d0`` is play-type UI, not down;
``0x8486ce88`` picks a play from situation word0 / ``+0x2BC`` (a tab).
Eligibility ANDs the map-role mask at ``0x820FC380`` with a personnel cell
(also at ``0x84862580`` in the 11-slot loop). ``0x84b694a8`` stores 1 or 2
to situation ``+8``. ``0x8499e3e8`` compares compact ``+0x18`` to 115, not
down. ``0x844dbe00`` is ``.pdata``, not a script table. ``0x84a89ea8``
maps a play onto an SPLB record, not a situation. Situation ``+0x1F8``
is a play-type filter. ``0x848699d8`` filters by type nibble, not down.
It reads the current book from playcall ``+0x20`` (global ``0x851A2780``).
``0x8493d968`` registers that object; ``0x8493e180`` is a packed ``+0x20``
setter with 0 ``bl`` callers. ``0x8485e7f8`` has 0 ``bl`` callers and the
assigner does not fall through into it. The in-game builder does not call
the eligibility AND. DRCT insert ``0x8466b998`` is type-list registration;
``0x8466af70`` loads ``dir_ingame.iff`` via ``0x8468da70``, not an opcode
walker. ``0x8466a818`` relocates DRCT pointers (NFL ``0x000dc700`` analog);
``0x8466aae0`` walks the relocated fixed table, not the instruction
consumer. ``0x8466abc0`` indexes fixed-record children via ``+0x18``;
``0x8466af28`` indexes strings via ``+0x14``. Picker ``0x8486ce88`` takes
the playcall object as ``r3`` (``0x8470c2c4``). Jump-table ``0x8470bf18``
takes a small integer mode 0..19 (``0x84712498``); case 2 (``li r3, 2``
at ``0x847163d4``) is frontend, not CPU down/ytg. ``0x84867938`` also reads
``+0x20``. Find-by-slot's book singleton is ``0x8520CDE0`` (init
``0x84a139d0``). UI ``0x84a28318`` reads playcall ``+0x1C``/``+0x20``.
Shadow ``0x84887e18`` writes bitmasks to ``0x8516C908+0x20``, not a book.
Slot ``+0`` can be type singleton ``0x850F1218`` (install
``0x84ad0048``); init ``0x847c6da8`` copies live MASTER from
``0x84F3F7D8+0x2C`` (``0x849fd6a8``) onto type ``+0x20``. Helper
``0x8486cd80`` is UI-only. Setter ``0x849fd6c8`` is bind/SPLB-select
(table ``0x851D9660`` via ``0x849fcf60``), not per-play.
``0x849d81d0`` is init-stored at ``0x84E28670+0x2C94`` (0 ``bl``).
``get_down`` lives only in packed property blob ``0x84EB0DE4``.
Property-get-by-id ``0x849c9c90`` uses ids 997..999, not down.
Relocator ``0x8466a994`` inlines the instruction directory at ``+0x20``.
NFL ``0x000dca40`` is a bitset/float lookup, not an instruction indexer.
``dir_ingame.iff`` (outer 153) has 1015 instruction records; 1014 begin
``0B 00 01 00`` then a token at +4 — bytecode, not a C++ vtable. The
relocator rewrites only the inline directory words; it does not follow
those pointers into record bodies. Packed ``lhz +6`` getter
``0x84ab2010`` has 0 ``bl`` and 0 inbound pointers. DRCT vtable[2]
``0x8466ba30`` unlinks a list. Byte-stream ``0x8466bd38`` compares
94/96/97 and 275–330, not instruction tokens. ``0x84bcd760`` is a
string classifier (0 ``bl``). 0 ``addi 32``/``lwzx``/``lbz 0(record)``
consumer. ``dir_wrapup.iff`` (outer 265) has 96 records, all ``0B 00``.
Groups are tagged fields (``0B 00`` + u16 field + u8), not a VM opcode
at +4. vtable[0] ``0x8466b8b0`` only relocates then walks the fixed
table (``bl 0x8466aae0`` at ``0x8466b8fc``). Packed +0x14/+0x18
indexers have 0 ``bl`` and 0 inbound pointers. ``0x8466af48`` is a
bounds check (r4 < +0x10), not a type mapper. ``0x84b162a8`` is an
embedded C++ object at +0x20. ``lbz``+``cmpwi 11`` then 12 is a
class-id, not tag ``0x0B``.
Field ids inside ``0B 00`` groups are BE u16 ``0x0100``/``0x0200``,
not 1/2. Nested lead bytes ``0x03``..``0x09`` appear after those
groups. 0 ``lhz``+``cmpwi 0x0100`` parser (``0x84c381e8`` is
stack/float). 0 skip-``0B 00`` then ``lhz``. 0 ``lhbrx`` in TEXT.
``0x84a87b38`` is play-type nibble ``srwi 28``. ``0x84bdfb00`` is
ASCII Y/I.
0 ``cmpwi 0x0B00`` in TEXT. ``0x848bb1a8`` is RTTI class 2 vs 11.
``0x8466b660`` is a map count vs 256, not field ``0x0100``.
``0x8466c7f0`` is a packed LE f32 (4×lbz, not lwbrx). 0 lis/addi of ``0x84EE65C0``.
``0x84671838`` is C++ vt[2] on r4+0x20, not a property registrar.
0B groups are tag + u8 variant + BE u16 field + u8 (variant 0 is
3589/3621; variants 1–5 use field ``0x0200``), not a 2-byte
``0B00`` tag. ``0x84842f48`` is RTTI class 3/4/5/6/7/11/12 via
+0x14/+4. ``0x8476ca80`` counts 10×5-byte slots at object
+0x13D9. ``0x8492bb24`` sums 5-byte windows then uses floats.
``0x84b0a4c0`` compact-int-indexes stride-12 table ``0x84EE65A8``
(max id ``0x35``) then ``bctrl`` get/set; 0 ``cmpwi 11`` in those
cases. ``0x849e7790`` copies a 12-byte record (``0xffff`` sentinel),
not a 0B group.
``0x847e2818`` is class-id 3/5/6/7/4 via +4, not leftover leads.
``0x84abb590`` copies 5 bytes with no tag check. ``0x84a9d7a0``
copies stride-32 floats at +0x1C, not NFL table ``0xB73BD0``.
NFL ``dir_ingame`` (outer 4) has 1310 instruction records, all
starting ``0B``; prefixes ``0B 00 01 00`` / ``01 01`` / ``01 02`` —
same tag+variant+u16 encoding as APF. ``0x84be2b48`` is an
ASCII/scanf 0..11 jump, not leftover leads. ``0x848777cc`` loads
one float from ``0x84F1A150+0x1C``, not a stride-32 bitset table.
``0x84b93b10`` reads a 5-byte header with no ``0x0B`` check;
caller ``0x84b94258`` switches on first byte 0..4.
Non-``0B`` leftovers are concatenated typed groups: type ``0x04`` is
tag + 4-byte LE float (size 5) on APF and NFL; types ``0x05``/``0x06``/
``0x07``/``0x08``/``0x09`` are 1-byte tags (a following ``00`` is the
terminator type, not a payload); type ``0x03`` is tag + u8 (size 2).
That walk consumes APF ingame 1015/1015 and NFL ingame 1310/1310.
``0x849277a8`` switches on a presentation byte (cases 4/11 store
floats), not those tags. ``0x84c4c480`` copies 1/2/4/8 bytes with
endian swap (``cmplwi`` 1/2/4/8 then ``lwbrx`` for width 4), not a
type-4 float reader. ``0x84ba2520`` walks a stride-12 table in r4
from a packed descriptor (``mulli`` 12 + ``lbz`` +8), not a property
``bctrl`` registrar. ``0x846c2068`` compares object +0x62 to 4 then
stores 5, not float-group size. ``0x8466c890`` is a float-expression
VM (opcodes 0..12, table ``0x8466c91c``, cursor ``0x84F1779C``);
case 4 is the LE f32 immediate (helper ``0x8466c7f0``); case 11
consumes 1 extra byte, not a leftover 0B group. Descriptor slot
``0x844dd260``. ``0x8477f950`` switches on a UI byte 0..12 (cases
5-10 just return). ``0x84a37850`` loads situation down and ytg
together and wraps ytg at 100, not a play picker. ``0x848864b0``
compares situation word0 to 4 (not down) and playcall+0x38 to 11.
``0x84a5eb08`` indexes 24-byte tables by type 3/4/8/9/11/12, not leftover.
``0x8475b7b0`` tweens ``0x84D58C70`` (``lfs`` +0x258, counter +0x25C), not
situation ytg. NFL xbe has 0 ``add r32,5`` within 80 bytes of ``cmp al, 0x0B``;
the only ``.text`` sites with both ``cmp al,4`` and ``cmp al,0x0B`` within 48
bytes are ``0x1138e0`` (object +0x35 enum) and killed play-type classifiers
``0x133fd1`` / ``0x27e830``. ``0x84a23bd0`` cycles situation +0x1F8 through
0..7 (UI play-type filter), not CPU 3rd-and-long. The only PE pointer to
picker ``0x8486ce88`` is its ``.pdata`` row ``0x844e8568`` (section
``0x844DBE00``), not a ``bctrl`` dispatch slot. Situation +0x1F8 setter
``0x849d36d8`` has 0 ``bl`` and 0 PE pointers. NFL relocator ``0x000dc700``
returns after fixing +0x14/+0x0c/+0x08 and does not walk instruction bodies.
``0x848631d0`` is the +0x1F8 getter used by the "Offensive Play calling"
widget (``0x845FE7D4``); ``0x849d36d8`` remains the packed setter (0 ``bl``).
NFL ``0x168ad0`` walks a SHAP list at +0x14 (stride 0xC, dword==3), not leftover
TLV. The only ``lhz`` +6 then ``addi`` 32 is relocator ``0x8466a994``.
``0x84a2ccd8`` reads situation +0x1F8 and +0x2BC (word0==2, filter==0,
tab==3), not down/ytg. The only TEXT sites with cmp 4, addi 5, and cmp 11
together are occupancy ``0x84961548`` and bit-pack ``0x849e3a24``, not leftover
sizes. Picker-caller neighborhood ``0x84814dcc`` / ``0x84816118`` compares
situation word0 to 4, not Fourth Down; the addi 5 is ``srawi``-3 index math.
``0x8485a04c`` switches word0 0/1/2/3/4/9 into mode immediates. Real
``addi r,r,5`` (not ``li 5``) plus cmp 4/11 is still not a leftover stream:
``0x84869e60`` is a 4-wide fill remainder and ``0x84a9adcc`` is an 11-slot
``lbzx`` at object+5 beside the role table. ``0x84a21298`` is a packed UI
formatter (0 ``bl``) that indexes the seven labels at ``0x84E446C8``
("First Down" … "Third and Long" ``0x845FD8B4`` … "Fourth and Long"); every
``lis``/``addi`` of its object ``0x85212B88`` sits in the same ``0x84a20xxx``
widget cluster, not a CPU picker. ``lbz``+``cmplwi`` 9 then ``bctr`` at
``0x84911750`` / ``0x849ecd48`` switch object fields, not leftover tags.
``0x847d7590`` / ``0x8480189c`` compare playcall ``0x851A2780+0x3C`` to 3/6,
not down. Every TEXT ``lis``/``addi`` of leftover cursor ``0x84F1779C`` /
``0x84F177AC`` sits in expr-VM ``0x8466c778``–``0x8466d888``; the VM entry
stores r5 to cursor+8 (``0x8466c8dc``). No TEXT site loads situation +0x254
and +0x25C together and yields D&D index 4; lookalikes ``0x8499e420`` /
``0x849a3b58`` compare script node +0x10/+0x14. Packed get_ytg ``0x84b68cd8``
(``lwz r3, +0x25C(r3)``) has 0 ``bl`` and 0 PE pointers; the situation
property blob that holds get_down ``0x84ad92e0`` has no +0x25C getter.
Expr VM ``0x8466c890`` has only desc slot ``0x844dd260`` (0 inbound PE ptrs,
0 TEXT ``lis``/``addi``). 0 ``lwz`` +0x20 then ``lbz`` and cmp 4/11 leftover
walk. ``0x84879bc0`` extracts ytg bit 1, not a D&D index. Packed object
get_down ``0x84b68cc8`` sits next to get_ytg (0 PE ptrs). ``0x84ad0348``
copies situation +0x254/+0x258/+0x25C onto a stack blob (only PE is
``.pdata`` ``0x844f72b0``); not a D&D index. 0 aligned inbound PE pointers
into get_down blob ``0x84EB0800``..``0x84EB0F00``. Other TEXT ``lwz``
+0x254/+0x25C pairs are stack slots, tween ``0x8475b7b0``, status query
``0x84b694a8``, or a non-situation object where +0x254 is a pointer
(``0x84b39458``). TEXT ``lis``/``addi`` of the blob only hit row base
``0x84EB02D0`` (packed ``0x84ad9f40``: ``mulli`` r4, 0x1C then ``lwz`` +4).
get_down's row ``0x84EB0DD0`` is not 0x1C-aligned from that base. 0
``addi`` 32 then ``lwz`` 0 then ``lbz`` 0(record) leftover walk. 8 ``lwz``
+0x20 then ``lbz`` 0 sites are string/ASCII. Only TEXT ``lis 0x0B00`` is
bitmask ``0x848ee750`` (``li r4, 11``). ``0x84b64c88`` walks a 4-byte window with UTF-8 extra-byte
table ``0x844C69C8`` (0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0), not leftover sizes.
That is still not the CPU 3rd-and-long picker.

This panel therefore never drops a slot below ``min(4, plays)``: it moves one
onto another play in the same formation, or carries it there when its play is
removed, and it will empty a formation (zero stored plays, zero tags) because
that is what the counted rule requires.  Two record-level edits are offered:
repoint a record's trailer at another MASTER formation and personnel package
(the director resolves requested personnel rows through the book category
mask and the ladder, so a book missing the 1TE/4WR "Straight" package falls
to 0-TE packages on pass downs), and fill the book's first empty record slot.
The whitelisted trailer bytes are the formation index, the category, and the
category bit gained in word B and in the book mask; the unproved 3-bit
situation fields and the low byte stay byte-exact.  Whether the director
then selects the repointed record is runtime-unproved; the receipt says so.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError


TaskRunner = Callable[[str, object, object, bool], None]
StagedChange = splb.MembershipChange | splb.TagMove | splb.TrailerReplace

#: What a user has to know before emptying a formation, in the order they need
#: it.  The static consumer facts stay below in the research pins; this is the
#: in-game consequence a real player measured, and it leads.
EMPTY_FORMATION_WARNING = (
    "Emptying a formation does not make the CPU skip it. The CPU still picks "
    "that formation, then calls plays and personnel that were never in the "
    "book.\n\n"
    "Measured in-game: O-ManBlock lined up packages the book does not contain; "
    "defense did the same except 4-3 / Bear in X-43Blitz; emptying only one "
    "of an Ace / Ace Flip pair hangs the load; and emptying a user book's "
    "base packages (every 20 and 10 formation in USER-o) left the game unable "
    "to boot at all under Xenia (spin, then exit). Do not use Empty as a way "
    "to get TEs on 3rd-and-long.\n\n"
    "Play names are not personnel. Personnel comes from the formation package "
    "map. The Who lines up tab edits those role bytes; whether the in-game "
    "look changes is unproved, and it is not a 3rd-and-long fix. Emptying "
    "every formation in a book is refused."
)

BOUNDARY = (
    "Fine-tune Plays changes which plays each stock CPU formation stores. It "
    "does not change the personnel who line up, and it does not guarantee which "
    "play the CPU will choose in a situation. A play name such as 50 TE Corner "
    "describes routes; it does not add a tight end to the formation.\n\n"
    "To edit that role map, open Who lines up. Three tagged slots are the "
    "formation's audibles. Mod Studio preserves all tagged slots unless you "
    "deliberately empty the formation. Empty formations are risky: the CPU then "
    "called plays that were not in the book. Mod Studio warns before doing that, "
    "will not empty a whole book, and keeps exact Flip twins together.\n\n"
    "Changes stay in your project until Build. Your original game remains "
    "untouched. Technical addresses are under Research pins."
)

THIRD_AND_LONG_STATUS = (
    "Which formation the CPU calls on 3rd-and-long is decided in default.xex, "
    "and Mod Studio does not patch the game program. But the lineup's "
    "personnel ladder is data: on pass downs the game asks for the 0 RB / "
    "1 TE / 4 WR row, and books without that Straight (01) package — like "
    "O-Ace — fall back to a 0-TE package. That is the WR-for-TE sub you see. "
    "'Change formation/package…' and 'Add a formation to this book…' give a "
    "CPU book the 1 TE / 4 WR package. Whether the CPU then calls it on "
    "3rd-and-long is unproved at runtime; after Build, check it in Xenia.\n\n"
    "The Who lines up tab edits a formation's 11 role bytes with the same "
    "caveat.\n\n"
    "Technical addresses are under Research pins."
)

#: The full static reverse-engineering record behind :data:`BOUNDARY`.
#:
#: It belongs in the product -- every claim the panel makes has to be checkable
#: against the executable, and withdrawing a wrong one has to be visible.  It
#: does not belong wrapped across the panel below the play list, which is where
#: it was: 11,360 characters of hex addresses between a user and the buttons
#: they came for.  The panel now shows the boundary and puts this behind
#: “Research pins”, so nothing is hidden and nothing is in the way.
RESEARCH_PINS = (
    "Static pins behind the boundary above. Decompressed PE, image base "
    "0x82000000, SHA-256 "
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf. "
    "Entries marked as *not* something are withdrawn candidates, kept so they "
    "are not re-chased.\n\n"
    "Down lives at "
    "object +0x254 (3 = Third Down, table 0x820E57C8); in-game 0x848d96e4 "
    "compares it, but that helper is not a play picker. The 11-player builder "
    "indexes the +0x11 map by slot at 0x848605b4. Role table 0x820FC320 "
    "(loaded at 0x84a9ae68) maps role 8 → TE and role 9 → WR. "
    "MASTER categories at +0x44 "
    "are personnel packages (Ace, 5 Wide, Flush); 0x8485bd38 extracts the "
    "SPLB trailer index. That is not a 3rd-and-long picker. 0x84a472d0 is "
    "play-type UI (obj+4 walks 0x84e4d810); 0x8486ce88 picks a play from "
    "situation word0 / +0x2BC (a 0..3 tab, not down). Eligibility at "
    "0x8485e810 ANDs the map-role word-mask (table 0x820FC380) with a "
    "personnel-table cell; the same AND runs at 0x84862580. 0x844dbe00 "
    "is .pdata unwind data, not a script table. 0x84a89ea8 maps a play "
    "onto an SPLB record (not a situation picker). Situation +0x1F8 is a "
    "play-type filter (table 0x84DCB2A8), not down. 0x848699d8 filters "
    "by play-type nibble, not down; it reads the current book from "
    "playcall +0x20 (global 0x851A2780). 0x8493d968 registers that object; "
    "0x8493e180 is a packed +0x20 setter with 0 bl callers. 0x8485e7f8 has 0 bl callers "
    "and the assigner does not fall through into it. The in-game builder "
    "does not call the eligibility AND. DRCT insert 0x8466b998 is "
    "type-list registration; 0x8466af70 loads dir_ingame.iff via 0x8468da70, "
    "not an opcode walker. 0x8466a818 relocates DRCT pointers (NFL 0x000dc700 "
    "analog); 0x8466aae0 walks the relocated fixed table, not the instruction "
    "consumer. 0x8466abc0 indexes fixed-record children via +0x18; 0x8466af28 "
    "indexes strings via +0x14. Picker 0x8486ce88 takes the playcall object "
    "as r3 (0x8470c2c4). Jump-table 0x8470bf18 takes a small integer mode "
    "0..19 (0x84712498); case 2 (li r3, 2 at 0x847163d4) is frontend, not "
    "CPU down/ytg. Find-by-slot's book singleton is 0x8520CDE0 "
    "(init 0x84a139d0). UI 0x84a28318 reads playcall +0x1C/+0x20. "
    "Shadow 0x84887e18 writes bitmasks to 0x8516C908+0x20, not a book. "
    "Slot+0 can be type singleton 0x850F1218 (install 0x84ad0048); "
    "init 0x847c6da8 copies live MASTER from 0x84F3F7D8+0x2C "
    "(0x849fd6a8) onto type +0x20. Helper 0x8486cd80 is UI-only. "
    "Setter 0x849fd6c8 is bind/SPLB-select (table 0x851D9660 via "
    "0x849fcf60), not per-play. "
    "0x849d81d0 is init-stored at 0x84E28670+0x2C94 (0 bl). "
    "get_down lives only in packed property blob 0x84EB0DE4. "
    "Property-get-by-id 0x849c9c90 uses ids 997..999, not down. "
    "Relocator 0x8466a994 inlines the instruction directory at +0x20. "
    "NFL 0x000dca40 is a bitset/float lookup, not an instruction indexer. "
    "dir_ingame.iff (outer 153) has 1015 instruction records; 1014 begin "
    "0B 00 01 00 then a token at +4 — bytecode, not a C++ vtable. The "
    "relocator rewrites only the inline directory words; it does not follow "
    "those pointers into record bodies. Packed lhz +6 getter 0x84ab2010 "
    "has 0 bl and 0 inbound pointers. DRCT vtable[2] 0x8466ba30 unlinks a "
    "list. Byte-stream 0x8466bd38 compares 94/96/97 and 275–330, not "
    "instruction tokens. 0x84bcd760 is a string classifier (0 bl). "
    "0 addi 32/lwzx/lbz 0(record) consumer. "
    "dir_wrapup.iff (outer 265) has 96 records, all 0B 00. Groups are "
    "tagged fields (0B 00 + u16 field + u8), not a VM opcode at +4. "
    "vtable[0] 0x8466b8b0 only relocates then walks the fixed table "
    "(bl 0x8466aae0 at 0x8466b8fc). Packed +0x14/+0x18 indexers have "
    "0 bl and 0 inbound pointers. 0x8466af48 is a bounds check "
    "(r4 < +0x10), not a type mapper. 0x84b162a8 is an embedded C++ "
    "object at +0x20. lbz+cmpwi 11 then 12 is a class-id, not tag 0x0B. "
    "Field ids inside 0B 00 groups are BE u16 0x0100/0x0200, not 1/2. "
    "Nested lead bytes 0x03..0x09 appear after those groups. "
    "0 lhz+cmpwi 0x0100 parser (0x84c381e8 is stack/float). "
    "0 skip-0B 00 then lhz. 0 lhbrx in TEXT. 0x84a87b38 is play-type "
    "nibble srwi 28. 0x84bdfb00 is ASCII Y/I. "
    "0 cmpwi 0x0B00 in TEXT. 0x848bb1a8 is RTTI class 2 vs 11. "
    "0x8466b660 is a map count vs 256, not field 0x0100. "
    "0x8466c7f0 is a packed LE f32 (4×lbz, not lwbrx). 0 lis/addi of 0x84EE65C0. "
    "0x84671838 is C++ vt[2] on r4+0x20, not a property registrar. "
    "0B groups are tag + u8 variant + BE u16 field + u8 (variant 0 is "
    "3589/3621; variants 1-5 use field 0x0200), not a 2-byte 0B00 tag. "
    "0x84842f48 is RTTI class 3/4/5/6/7/11/12 via +0x14/+4. "
    "0x8476ca80 counts 10x5-byte slots at object +0x13D9. "
    "0x8492bb24 sums 5-byte windows then uses floats. "
    "0x84b0a4c0 compact-int-indexes stride-12 table 0x84EE65A8 "
    "(max id 0x35) then bctrl get/set; 0 cmpwi 11 in those cases. "
    "0x849e7790 copies a 12-byte record (0xffff sentinel), not a 0B group. "
    "0x847e2818 is class-id 3/5/6/7/4 via +4, not leftover leads. "
    "0x84abb590 copies 5 bytes with no tag check. 0x84a9d7a0 copies "
    "stride-32 floats at +0x1C, not NFL table 0xB73BD0. "
    "NFL dir_ingame (outer 4) has 1310 instruction records, all starting "
    "0B; prefixes 0B 00 01 00 / 01 01 / 01 02 — same tag+variant+u16 "
    "encoding as APF. 0x84be2b48 is an ASCII/scanf 0..11 jump, not leftover "
    "leads. 0x848777cc loads one float from 0x84F1A150+0x1C, not a stride-32 "
    "bitset table. 0x84b93b10 reads a 5-byte header with no 0x0B check; "
    "caller 0x84b94258 switches on first byte 0..4. "
    "Non-0B leftovers are concatenated typed groups: type 0x04 is tag + "
    "4-byte LE float (size 5) on APF and NFL; types 0x05/0x06/0x07/0x08/0x09 "
    "are 1-byte tags (a following 00 is the terminator type, not a payload); "
    "type 0x03 is tag + u8 (size 2). That walk consumes APF ingame 1015/1015 "
    "and NFL ingame 1310/1310. 0x849277a8 switches on a presentation byte "
    "(cases 4/11 store floats), not those tags. 0x84c4c480 copies 1/2/4/8 "
    "bytes with endian swap (cmplwi 1/2/4/8 then lwbrx for width 4), not a "
    "type-4 float reader. 0x84ba2520 walks a stride-12 table in r4 from a "
    "packed descriptor (mulli 12 + lbz +8), not a property bctrl registrar. "
    "0x846c2068 compares object +0x62 to 4 then stores 5, not float-group "
    "size. 0x8466c890 is a float-expression VM (opcodes 0..12, table "
    "0x8466c91c, cursor 0x84F1779C); case 4 is the LE f32 immediate "
    "(helper 0x8466c7f0); case 11 consumes 1 extra byte, not a leftover "
    "0B group. Descriptor slot 0x844dd260. 0x8477f950 switches on a UI "
    "byte 0..12 (cases 5-10 just return). 0x84a37850 loads situation down "
    "and ytg together and wraps ytg at 100, not a play picker. "
    "0x848864b0 compares situation word0 to 4 (not down) and playcall+0x38 "
    "to 11. 0x84a5eb08 indexes 24-byte tables by type 3/4/8/9/11/12, not leftover. "
    "0x8475b7b0 tweens 0x84D58C70 (lfs +0x258, counter +0x25C), not situation ytg. "
    "NFL xbe has 0 add r32,5 within 80 bytes of cmp al, 0x0B; the only .text "
    "sites with both cmp al,4 and cmp al,0x0B within 48 bytes are 0x1138e0 "
    "(object +0x35 enum) and killed play-type classifiers 0x133fd1 / 0x27e830. "
    "0x84a23bd0 cycles situation +0x1F8 through 0..7 (UI play-type filter), "
    "not CPU 3rd-and-long. The only PE pointer to picker 0x8486ce88 is "
    "its .pdata row 0x844e8568 (section 0x844DBE00), not a bctrl dispatch "
    "slot. Situation +0x1F8 setter 0x849d36d8 has 0 bl and 0 PE pointers. "
    "NFL relocator 0x000dc700 returns after fixing +0x14/+0x0c/+0x08 and "
    "does not walk instruction bodies. "
    "0x848631d0 is the +0x1F8 getter used by the Offensive Play calling "
    "widget (0x845FE7D4); 0x849d36d8 remains the packed setter (0 bl). "
    "NFL 0x168ad0 walks a SHAP list at +0x14 (stride 0xC, dword==3), not leftover "
    "TLV. The only lhz +6 then addi 32 is relocator 0x8466a994. "
    "0x84a2ccd8 reads situation +0x1F8 and +0x2BC (word0==2, filter==0, "
    "tab==3), not down/ytg. The only TEXT sites with cmp 4, addi 5, and cmp 11 "
    "together are occupancy 0x84961548 and bit-pack 0x849e3a24, not leftover "
    "sizes. Picker-caller neighborhood 0x84814dcc / 0x84816118 compares "
    "situation word0 to 4, not Fourth Down; the addi 5 is srawi-3 index math. "
    "0x8485a04c switches word0 0/1/2/3/4/9 into mode immediates. Real "
    "addi r,r,5 (not li 5) plus cmp 4/11 is still not a leftover stream: "
    "0x84869e60 is a 4-wide fill remainder and 0x84a9adcc is an 11-slot "
    "lbzx at object+5 beside the role table. "
    "0x84a21298 is a packed UI formatter (0 bl) that indexes the seven "
    "labels at 0x84E446C8 (First Down … Third and Long 0x845FD8B4 … "
    "Fourth and Long); every lis/addi of its object 0x85212B88 sits in "
    "the same 0x84a20xxx widget cluster, not a CPU picker. "
    "lbz+cmplwi 9 then bctr at 0x84911750 / 0x849ecd48 switch object "
    "fields, not leftover tags. "
    "0x847d7590 / 0x8480189c compare playcall 0x851A2780+0x3C to 3/6, "
    "not down. Every TEXT lis/addi of leftover cursor 0x84F1779C / "
    "0x84F177AC sits in expr-VM 0x8466c778-0x8466d888; the VM entry "
    "stores r5 to cursor+8 (0x8466c8dc). No TEXT site loads situation +0x254 "
    "and +0x25C together and yields D&D index 4; lookalikes 0x8499e420 / "
    "0x849a3b58 compare script node +0x10/+0x14. "
    "Packed get_ytg 0x84b68cd8 (lwz r3, +0x25C(r3)) has 0 bl and 0 PE "
    "pointers; the situation property blob that holds get_down 0x84ad92e0 "
    "has no +0x25C getter. Expr VM 0x8466c890 has only desc slot "
    "0x844dd260 (0 inbound PE ptrs, 0 TEXT lis/addi). 0 lwz +0x20 then "
    "lbz and cmp 4/11 leftover walk. 0x84879bc0 extracts ytg bit 1, not "
    "a D&D index. Packed object get_down 0x84b68cc8 sits next to get_ytg "
    "(0 PE ptrs). 0x84ad0348 copies situation +0x254/+0x258/+0x25C onto a "
    "stack blob (only PE is .pdata 0x844f72b0); not a D&D index. 0 aligned "
    "inbound PE pointers into get_down blob 0x84EB0800..0x84EB0F00. Other "
    "TEXT lwz +0x254/+0x25C pairs are stack slots, tween 0x8475b7b0, "
    "status query 0x84b694a8, or a non-situation object where +0x254 is a "
    "pointer (0x84b39458). TEXT lis/addi of the blob only hit row base "
    "0x84EB02D0 (packed 0x84ad9f40: mulli r4, 0x1C then lwz +4). "
    "get_down's row 0x84EB0DD0 is not 0x1C-aligned from that base. 0 "
    "addi 32 then lwz 0 then lbz 0(record) leftover walk. 8 lwz +0x20 "
    "then lbz 0 sites are string/ASCII. Only TEXT lis 0x0B00 is bitmask "
    "0x848ee750 (li r4, 11). "
    "0x84b64c88 walks a 4-byte window with UTF-8 extra-byte table 0x844C69C8 "
    "(0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0), not leftover sizes. "
    "0x84b694a8 stores 1 or 2 to situation +8, not a play."
)

#: What is settled about the tagged slots, and what is only a reading. Kept as
#: one string so the panel, its tooltips and its tests all quote the same words.
TAG_BOUNDARY = (
    "Proved about the tagged slots: every populated formation in all fifteen "
    "books carries exactly min(4, plays) of them — 209 records, zero "
    "exceptions — and they are authored per formation, not positional. "
    "Singleback Ace and Ace Flip hold byte-identical 77-play lists, same plays "
    "and same X values, yet Ace tags entries 70–73 and Ace Flip tags 0–3; only "
    "137 of the 209 records tag their leading entries at all.\n\n"
    "What they DO is now proved too, in the game's own code. Community reporter "
    "Urianus read them as the formation's audibles — \"the user only gets 3 per "
    "formation\" — and the executable agrees. The game does not merely read "
    "these bits, it writes them: at 0x84864c78 it inserts a slot number into "
    "bits 12–10 of an entry and stores it back, and the loop around it runs that "
    "counter 0, 1, 2 — three slots per formation — stepping 176 bytes at a time, "
    "which is exactly one SPLB record. Slot 4 is what an untagged play carries, "
    "and the loop hunts for those as candidates. The game also ships the move "
    "this panel performs: 0x84a8ab28 takes a slot off one play and puts it on "
    "another.\n\n"
    "So three of the four are the audibles you set at the line. The fourth "
    "(slot 3) is a real tagged slot that the assign loop never writes. "
    "0x84a850f0 walks tagged slots 0, 1, 2, 3 (cmpwi r30, 4 at 0x84a851ec) "
    "and calls find-by-slot for each; that collector is reached from an "
    "in-game tick. That does not prove the CPU calls those four plays on "
    "3rd-and-long — 0x84a850f0 has no down or yards-to-go consumer. Down is "
    "object +0x254 (3 = Third Down at 0x820E57C8); 0x848d96e4 compares it "
    "in-game, and 0x84809898 is a type-id match, not a play picker. Ace tags "
    "four runs, Ace Flip four play-action passes, O-Shotgun empty/open includes "
    "90 TE Stop, and that book's base Gun tags are four runs, so the four tags "
    "are not a 3rd-and-long call set.\n\n"
    "The rest of the static record is under “Research pins”."
)

#: The remainder of the tagged-slot pins, split out of :data:`TAG_BOUNDARY` for
#: the same reason as :data:`RESEARCH_PINS`: a modal dialog a user has to read
#: to answer "can I move this slot" should not be eleven thousand characters of
#: withdrawn candidates.
TAG_RESEARCH_PINS = (
    "The 11-player builder loads map[slot] at "
    "0x848605b4. MASTER category records (Ace, 5 Wide, Flush) are personnel "
    "packages; 0x8485bd38 extracts the trailer index — still not a "
    "3rd-and-long picker. 0x84a472d0 is play-type UI; 0x8486ce88 uses "
    "situation word0 / +0x2BC (a tab), not down. Eligibility at 0x8485e810 "
    "ANDs table 0x820FC380 with a personnel cell. 0x8485e7f8 has 0 bl "
    "callers. 0x848699d8 reads playcall +0x20 (0x851A2780), not down. "
    "0x8493d968 registers that object. 0x8466af70 loads dir_ingame.iff. "
    "0x8466a818 relocates DRCT pointers. 0x8466abc0 indexes +0x18 children. "
    "Picker 0x8486ce88 takes the playcall object as r3 (0x8470c2c4). "
    "Jump-table 0x8470bf18 takes a small integer mode 0..19 "
    "(0x84712498); case 2 (li r3, 2 at 0x847163d4) is frontend, not "
    "CPU down/ytg. "
    "0x84867938 also reads +0x20. "
    "Find-by-slot's book singleton is 0x8520CDE0 (init 0x84a139d0). "
    "UI 0x84a28318 reads playcall +0x1C/+0x20. "
    "Shadow 0x84887e18 writes bitmasks to 0x8516C908+0x20, not a book. "
    "Slot+0 can be type singleton 0x850F1218 (install 0x84ad0048); "
    "init 0x847c6da8 copies live MASTER from 0x84F3F7D8+0x2C "
    "(0x849fd6a8) onto type +0x20. Helper 0x8486cd80 is UI-only. "
    "Setter 0x849fd6c8 is bind/SPLB-select (table 0x851D9660 via "
    "0x849fcf60), not per-play. "
    "0x849d81d0 is init-stored at 0x84E28670+0x2C94 (0 bl). "
    "get_down lives only in packed property blob 0x84EB0DE4. "
    "Property-get-by-id 0x849c9c90 uses ids 997..999, not down. "
    "Relocator 0x8466a994 inlines the instruction directory at +0x20. "
    "NFL 0x000dca40 is a bitset/float lookup, not an instruction indexer. "
    "dir_ingame.iff (outer 153) has 1015 instruction records; 1014 begin "
    "0B 00 01 00 then a token at +4 — bytecode, not a C++ vtable. The "
    "relocator rewrites only the inline directory words; it does not follow "
    "those pointers into record bodies. Packed lhz +6 getter 0x84ab2010 "
    "has 0 bl and 0 inbound pointers. DRCT vtable[2] 0x8466ba30 unlinks a "
    "list. Byte-stream 0x8466bd38 compares 94/96/97 and 275–330, not "
    "instruction tokens. 0x84bcd760 is a string classifier (0 bl). "
    "0 addi 32/lwzx/lbz 0(record) consumer. "
    "dir_wrapup.iff (outer 265) has 96 records, all 0B 00. Groups are "
    "tagged fields (0B 00 + u16 field + u8), not a VM opcode at +4. "
    "vtable[0] 0x8466b8b0 only relocates then walks the fixed table "
    "(bl 0x8466aae0 at 0x8466b8fc). Packed +0x14/+0x18 indexers have "
    "0 bl and 0 inbound pointers. 0x8466af48 is a bounds check "
    "(r4 < +0x10), not a type mapper. 0x84b162a8 is an embedded C++ "
    "object at +0x20. lbz+cmpwi 11 then 12 is a class-id, not tag 0x0B. "
    "Field ids inside 0B 00 groups are BE u16 0x0100/0x0200, not 1/2. "
    "Nested lead bytes 0x03..0x09 appear after those groups. "
    "0 lhz+cmpwi 0x0100 parser (0x84c381e8 is stack/float). "
    "0 skip-0B 00 then lhz. 0 lhbrx in TEXT. 0x84a87b38 is play-type "
    "nibble srwi 28. 0x84bdfb00 is ASCII Y/I. "
    "0 cmpwi 0x0B00 in TEXT. 0x848bb1a8 is RTTI class 2 vs 11. "
    "0x8466b660 is a map count vs 256, not field 0x0100. "
    "0x8466c7f0 is a packed LE f32 (4×lbz, not lwbrx). 0 lis/addi of 0x84EE65C0. "
    "0x84671838 is C++ vt[2] on r4+0x20, not a property registrar. "
    "0B groups are tag + u8 variant + BE u16 field + u8 (variant 0 is "
    "3589/3621; variants 1-5 use field 0x0200), not a 2-byte 0B00 tag. "
    "0x84842f48 is RTTI class 3/4/5/6/7/11/12 via +0x14/+4. "
    "0x8476ca80 counts 10x5-byte slots at object +0x13D9. "
    "0x8492bb24 sums 5-byte windows then uses floats. "
    "0x84b0a4c0 compact-int-indexes stride-12 table 0x84EE65A8 "
    "(max id 0x35) then bctrl get/set; 0 cmpwi 11 in those cases. "
    "0x849e7790 copies a 12-byte record (0xffff sentinel), not a 0B group. "
    "0x847e2818 is class-id 3/5/6/7/4 via +4, not leftover leads. "
    "0x84abb590 copies 5 bytes with no tag check. 0x84a9d7a0 copies "
    "stride-32 floats at +0x1C, not NFL table 0xB73BD0. "
    "NFL dir_ingame (outer 4) has 1310 instruction records, all starting "
    "0B; prefixes 0B 00 01 00 / 01 01 / 01 02 — same tag+variant+u16 "
    "encoding as APF. 0x84be2b48 is an ASCII/scanf 0..11 jump, not leftover "
    "leads. 0x848777cc loads one float from 0x84F1A150+0x1C, not a stride-32 "
    "bitset table. 0x84b93b10 reads a 5-byte header with no 0x0B check; "
    "caller 0x84b94258 switches on first byte 0..4. "
    "Non-0B leftovers are concatenated typed groups: type 0x04 is tag + "
    "4-byte LE float (size 5) on APF and NFL; types 0x05/0x06/0x07/0x08/0x09 "
    "are 1-byte tags (a following 00 is the terminator type, not a payload); "
    "type 0x03 is tag + u8 (size 2). That walk consumes APF ingame 1015/1015 "
    "and NFL ingame 1310/1310. 0x849277a8 switches on a presentation byte "
    "(cases 4/11 store floats), not those tags. 0x84c4c480 copies 1/2/4/8 "
    "bytes with endian swap (cmplwi 1/2/4/8 then lwbrx for width 4), not a "
    "type-4 float reader. 0x84ba2520 walks a stride-12 table in r4 from a "
    "packed descriptor (mulli 12 + lbz +8), not a property bctrl registrar. "
    "0x846c2068 compares object +0x62 to 4 then stores 5, not float-group "
    "size. 0x8466c890 is a float-expression VM (opcodes 0..12, table "
    "0x8466c91c, cursor 0x84F1779C); case 4 is the LE f32 immediate "
    "(helper 0x8466c7f0); case 11 consumes 1 extra byte, not a leftover "
    "0B group. Descriptor slot 0x844dd260. 0x8477f950 switches on a UI "
    "byte 0..12 (cases 5-10 just return). 0x84a37850 loads situation down "
    "and ytg together and wraps ytg at 100, not a play picker. "
    "0x848864b0 compares situation word0 to 4 (not down) and playcall+0x38 "
    "to 11. 0x84a5eb08 indexes 24-byte tables by type 3/4/8/9/11/12, not leftover. "
    "0x8475b7b0 tweens 0x84D58C70 (lfs +0x258, counter +0x25C), not situation ytg. "
    "NFL xbe has 0 add r32,5 within 80 bytes of cmp al, 0x0B; the only .text "
    "sites with both cmp al,4 and cmp al,0x0B within 48 bytes are 0x1138e0 "
    "(object +0x35 enum) and killed play-type classifiers 0x133fd1 / 0x27e830. "
    "0x84a23bd0 cycles situation +0x1F8 through 0..7 (UI play-type filter), "
    "not CPU 3rd-and-long. The only PE pointer to picker 0x8486ce88 is "
    "its .pdata row 0x844e8568 (section 0x844DBE00), not a bctrl dispatch "
    "slot. Situation +0x1F8 setter 0x849d36d8 has 0 bl and 0 PE pointers. "
    "NFL relocator 0x000dc700 returns after fixing +0x14/+0x0c/+0x08 and "
    "does not walk instruction bodies. "
    "0x848631d0 is the +0x1F8 getter used by the Offensive Play calling "
    "widget (0x845FE7D4); 0x849d36d8 remains the packed setter (0 bl). "
    "NFL 0x168ad0 walks a SHAP list at +0x14 (stride 0xC, dword==3), not leftover "
    "TLV. The only lhz +6 then addi 32 is relocator 0x8466a994. "
    "0x84a2ccd8 reads situation +0x1F8 and +0x2BC (word0==2, filter==0, "
    "tab==3), not down/ytg. The only TEXT sites with cmp 4, addi 5, and cmp 11 "
    "together are occupancy 0x84961548 and bit-pack 0x849e3a24, not leftover "
    "sizes. Picker-caller neighborhood 0x84814dcc / 0x84816118 compares "
    "situation word0 to 4, not Fourth Down; the addi 5 is srawi-3 index math. "
    "0x8485a04c switches word0 0/1/2/3/4/9 into mode immediates. Real "
    "addi r,r,5 (not li 5) plus cmp 4/11 is still not a leftover stream: "
    "0x84869e60 is a 4-wide fill remainder and 0x84a9adcc is an 11-slot "
    "lbzx at object+5 beside the role table. "
    "0x84a21298 is a packed UI formatter (0 bl) that indexes the seven "
    "labels at 0x84E446C8 (First Down … Third and Long 0x845FD8B4 … "
    "Fourth and Long); every lis/addi of its object 0x85212B88 sits in "
    "the same 0x84a20xxx widget cluster, not a CPU picker. "
    "lbz+cmplwi 9 then bctr at 0x84911750 / 0x849ecd48 switch object "
    "fields, not leftover tags. "
    "0x847d7590 / 0x8480189c compare playcall 0x851A2780+0x3C to 3/6, "
    "not down. Every TEXT lis/addi of leftover cursor 0x84F1779C / "
    "0x84F177AC sits in expr-VM 0x8466c778-0x8466d888; the VM entry "
    "stores r5 to cursor+8 (0x8466c8dc). No TEXT site loads situation +0x254 "
    "and +0x25C together and yields D&D index 4; lookalikes 0x8499e420 / "
    "0x849a3b58 compare script node +0x10/+0x14. "
    "Packed get_ytg 0x84b68cd8 (lwz r3, +0x25C(r3)) has 0 bl and 0 PE "
    "pointers; the situation property blob that holds get_down 0x84ad92e0 "
    "has no +0x25C getter. Expr VM 0x8466c890 has only desc slot "
    "0x844dd260 (0 inbound PE ptrs, 0 TEXT lis/addi). 0 lwz +0x20 then "
    "lbz and cmp 4/11 leftover walk. 0x84879bc0 extracts ytg bit 1, not "
    "a D&D index. Packed object get_down 0x84b68cc8 sits next to get_ytg "
    "(0 PE ptrs). 0x84ad0348 copies situation +0x254/+0x258/+0x25C onto a "
    "stack blob (only PE is .pdata 0x844f72b0); not a D&D index. 0 aligned "
    "inbound PE pointers into get_down blob 0x84EB0800..0x84EB0F00. Other "
    "TEXT lwz +0x254/+0x25C pairs are stack slots, tween 0x8475b7b0, "
    "status query 0x84b694a8, or a non-situation object where +0x254 is a "
    "pointer (0x84b39458). TEXT lis/addi of the blob only hit row base "
    "0x84EB02D0 (packed 0x84ad9f40: mulli r4, 0x1C then lwz +4). "
    "get_down's row 0x84EB0DD0 is not 0x1C-aligned from that base. 0 "
    "addi 32 then lwz 0 then lbz 0(record) leftover walk. 8 lwz +0x20 "
    "then lbz 0 sites are string/ASCII. Only TEXT lis 0x0B00 is bitmask "
    "0x848ee750 (li r4, 11). "
    "0x84b64c88 walks a 4-byte window with UTF-8 extra-byte table 0x844C69C8 "
    "(0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0), not leftover sizes. "
    "0x84b694a8 stores 1 or 2 "
    "to situation +8, not a play. The tag is preserved and editable.\n\n"
    "So the slots are never dropped below min(4, plays): one can be moved onto "
    "another play in the same formation, or carried onto one when its play is "
    "removed. Emptying a formation sheds every slot because min(4, 0) is 0; "
    "the record trailer is left untouched. Count 0x84a8ac30 and get-nth "
    "0x84a8bd20 then return 0/null for that record (static); which formation "
    "the director selects next is still runtime-unproved, and a community "
    "runtime report says an emptied record is not selected harmlessly. Only "
    "edits that "
    "would break the counted "
    "rule — fewer slots than min(4, plays) on a still-populated record, the "
    "same slot twice, or a slot value the retail books never use — are refused, "
    "along with emptying every populated formation in a book.\n\n"
    + EMPTY_FORMATION_WARNING
)


class ApfPlaybookMembershipPanel(QFrame):
    """Pick a stock book, pick a formation, tick plays in and out."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        self._book: splb.SplbBook | None = None
        #: Which volume ``_book`` was read from, so a repeated refresh for the
        #: same game and book does not re-read the MASTER play catalog.
        self._loaded_index: Path | None = None
        self._plays: list[str] = []
        self._formations: dict[int, str] = {}
        # record index -> {play index: wanted membership}
        self._staged: dict[int, dict[int, bool]] = {}
        # record index -> {play losing a tagged slot: play carrying it on}
        self._staged_heirs: dict[int, dict[int, int]] = {}
        # record index -> {play a tagged slot leaves: play it lands on}
        self._staged_moves: dict[int, dict[int, int]] = {}
        # record index -> (formation index, personnel category) trailer repoint
        self._staged_trailers: dict[int, tuple[int, int]] = {}
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel("Stock CPU playbooks")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)
        root.addLayout(heading)

        blurb = QLabel(
            "Reassigning a team's book usually changes nothing: the 36 offensive "
            "and 33 defensive book names in a save are labels over seven "
            "offensive and four defensive real books. These are those books."
        )
        blurb.setObjectName("mutedLabel")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        book_row = QHBoxLayout()
        book_row.setSpacing(8)
        book_row.addWidget(QLabel("Playbook:"))
        self.book_picker = QComboBox()
        self.book_picker.setObjectName("comboField")
        self.book_picker.setAccessibleName("Stock CPU playbook")
        self.book_picker.setToolTip(
            "The fifteen stock playbook resources the game ships. Eleven carry "
            "a name; four are unnamed and are shown by their archive entry."
        )
        for outer, name in sorted(splb.STOCK_BOOKS.items()):
            label = name or f"(unnamed book, entry {outer})"
            self.book_picker.addItem(label, outer)
        self.book_picker.currentIndexChanged.connect(lambda _i: self._load_book())
        book_row.addWidget(self.book_picker, 1)
        root.addLayout(book_row)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.formation_list = QListWidget()
        self.formation_list.setObjectName("assetList")
        self.formation_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.formation_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_plays()
        )
        left.addWidget(QLabel("Formations this book uses"))
        left.addWidget(self.formation_list, 1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.play_search = QLineEdit()
        self.play_search.setPlaceholderText("Search plays…")
        self.play_search.setClearButtonEnabled(True)
        self.play_search.setProperty("studioSearch", True)
        self.play_search.setAccessibleName("Search APF plays")
        self.play_search.textChanged.connect(lambda _text: self._refresh_plays())
        self.play_list = QListWidget()
        self.play_list.setObjectName("assetList")
        self.play_list.setToolTip(
            "Ticked plays are stored in this formation. Tick to add, untick "
            "to remove. Audibles stay on the formation unless you move them "
            "or empty it."
        )
        self.play_list.itemChanged.connect(self._play_toggled)
        self.play_header = QLabel("Plays")
        right.addWidget(self.play_header)
        right.addWidget(self.play_search)
        right.addWidget(self.play_list, 3)
        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        self.move_tag_button = QPushButton("Move tagged slot…")
        self.move_tag_button.setObjectName("quietButton")
        self.move_tag_button.setAccessibleName("Move a tagged slot to another play")
        self.move_tag_button.clicked.connect(self._move_tag)
        self.tag_help_button = QPushButton("What are tagged slots?")
        self.tag_help_button.setObjectName("quietButton")
        self.tag_help_button.clicked.connect(self._explain_tags)
        self.pins_button = QPushButton("Research pins")
        self.pins_button.setObjectName("quietButton")
        self.pins_button.setAccessibleName(
            "Show the static executable addresses behind these claims"
        )
        self.pins_button.setToolTip(
            "Every executable address behind what this panel claims, including "
            "the candidates that were checked and withdrawn. Nothing here "
            "changes what the buttons do."
        )
        self.pins_button.clicked.connect(self._show_research_pins)
        self.third_long_button = QPushButton("3rd-and-long editing status…")
        self.third_long_button.setObjectName("quietButton")
        self.third_long_button.setAccessibleName(
            "Explain why 3rd-and-long behavior cannot be edited"
        )
        self.third_long_button.setToolTip(
            "Mod Studio cannot change the reported user-team/CPU difference "
            "through APF's playbook data. Click for a plain-language explanation."
        )
        self.third_long_button.clicked.connect(self._refuse_third_and_long)
        tag_row.addWidget(self.move_tag_button)
        self.retarget_button = QPushButton("Change formation/package…")
        self.retarget_button.setObjectName("quietButton")
        self.retarget_button.setAccessibleName(
            "Repoint this record at another formation and personnel package"
        )
        self.retarget_button.clicked.connect(self._change_trailer)
        tag_row.addWidget(self.retarget_button)
        self.add_record_button = QPushButton("Add a formation to this book…")
        self.add_record_button.setObjectName("quietButton")
        self.add_record_button.setAccessibleName(
            "Fill the book's first empty record with a formation and plays"
        )
        self.add_record_button.clicked.connect(self._add_record)
        tag_row.addWidget(self.add_record_button)
        self.empty_button = QPushButton("Empty this formation…")
        self.empty_button.setObjectName("dangerQuietButton")
        self.empty_button.setAccessibleName("Remove every stored play from this formation")
        self.empty_button.clicked.connect(self._empty_formation)
        tag_row.addWidget(self.empty_button)
        tag_row.addWidget(self.tag_help_button)
        tag_row.addWidget(self.pins_button)
        tag_row.addWidget(self.third_long_button)
        tag_row.addStretch(1)
        right.addLayout(tag_row)
        columns.addLayout(right, 3)
        root.addLayout(columns, 1)

        note = QLabel(BOUNDARY)
        note.setObjectName("findingText")
        note.setWordWrap(True)
        root.addWidget(note)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.revert_button = QPushButton("Revert changes")
        self.revert_button.setObjectName("dangerQuietButton")
        self.build_button = QPushButton("Build copied 0A (playbook)…")
        self.build_button.setObjectName("primaryButton")
        self.revert_button.clicked.connect(self._revert)
        self.build_button.clicked.connect(self._build)
        actions.addStretch(1)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.build_button)
        root.addLayout(actions)

        self.set_context()

    # ---------------------------------------------------------------- context

    def _index_0a(self) -> Path | None:
        source = getattr(self.facade, "source", None)
        value = getattr(source, "index_0a", None) if source is not None else None
        return Path(value) if value is not None else None

    def _project_outers(self) -> tuple[int, ...]:
        reader = getattr(self.facade, "staged_splb_outers", None)
        if reader is not None:
            try:
                return tuple(int(item) for item in reader())
            except Exception:
                return ()
        single = getattr(self.facade, "staged_splb_book", None)
        if single is None:
            return ()
        try:
            value = single()
        except Exception:
            return ()
        return () if value is None else (int(value),)

    def _project_book(self) -> int | None:
        """Book to jump to on refresh. Stay put if the picker is already staged."""

        outers = self._project_outers()
        current = self.book_picker.currentData()
        if current is not None and int(current) in outers:
            return None
        if len(outers) == 1:
            return outers[0]
        return None

    def set_context(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            self._book = None
            self._loaded_index = None
            self._clear_staged()
            self.formation_list.clear()
            self.play_list.clear()
            self.status.setText("Not loaded")
            self._refresh_actions()
            return
        # An opened project may already carry Fine-tune Plays edits. Show the
        # book they belong to rather than the first one in the list, so the user
        # sees their own work instead of an apparently untouched playbook.
        staged_book = self._project_book()
        if staged_book is not None:
            row = self.book_picker.findData(staged_book)
            if row >= 0 and row != self.book_picker.currentIndex():
                self.book_picker.setCurrentIndex(row)   # triggers _load_book
                return
        index_0a = self._index_0a()
        outer = self.book_picker.currentData()
        if (
            self._book is not None
            and outer is not None
            and self._book.outer_index == int(outer)
            and self._loaded_index == index_0a
        ):
            # Same game, same book: re-reading the whole MASTER play catalog
            # would cost seconds for nothing. Only the staged set can have
            # changed underneath, so re-derive that and repaint.
            self._restore_from_project()
            self._refresh_formations()
            self._refresh_actions()
            return
        self._load_book()

    def _load_book(self) -> None:
        index_0a = self._index_0a()
        if index_0a is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        outer = self.book_picker.currentData()
        if outer is None:
            return
        # Other books stay staged in the project. This panel only edits one
        # book at a time; switching no longer discards them.
        self._clear_staged()

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            import playbook_inventory  # type: ignore

            progress("Reading the stock playbook", 0, 2)
            book = splb.read_book(index_0a, int(outer))
            progress("Reading MASTER play names", 1, 2)
            master = playbook_inventory.parse_apf(index_0a, 64 * 1024 * 1024)[0]
            progress("Playbook ready", 2, 2)
            return {
                "book": book,
                "plays": [str(p["name"]) for p in master["plays"]],
                "formations": {
                    int(f["index"]): str(f["name"]) for f in master["formations"]
                },
            }

        def done(result: object) -> None:
            payload = result  # type: ignore[assignment]
            self._book = payload["book"]  # type: ignore[index]
            self._plays = payload["plays"]  # type: ignore[index]
            self._formations = payload["formations"]  # type: ignore[index]
            self._loaded_index = index_0a
            self._restore_from_project()
            used = [r for r in self._book.records if r.populated]
            staged = len(self.staged_changes())
            self.status.setText(
                f"{self._book.name or 'unnamed'} · {len(used)} formations"
                + (f" · {staged} staged change{'s' if staged != 1 else ''}" if staged else "")
            )
            self._refresh_formations()
            self._refresh_actions()

        self.run_task("Opening the stock playbook", operation, done, False)

    def _book_label(self, outer: int) -> str:
        name = splb.STOCK_BOOKS.get(outer)
        return name or f"the unnamed book at entry {outer}"

    # ------------------------------------------------------------------- view

    def _refresh_formations(self) -> None:
        selected = self._selected_record_index()
        self.formation_list.blockSignals(True)
        self.formation_list.clear()
        row_to_select = -1
        if self._book is not None:
            for record in self._book.records:
                staged = self._staged_count(record.record_index)
                if not record.populated and not staged:
                    continue
                trailer = self._staged_trailers.get(record.record_index)
                if trailer is not None:
                    name = self._formations.get(trailer[0], "?")
                else:
                    name = self._formations.get(record.formation_index, "?")
                count = len(self._wanted_plays(record.record_index))
                label = f"{name}  ·  {count} plays"
                if trailer is not None:
                    label += f"   → repointed to {name}, package {trailer[1]}"
                if staged:
                    label += f"   ✎ {staged} changed"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, record.record_index)
                self.formation_list.addItem(item)
                if record.record_index == selected:
                    row_to_select = self.formation_list.count() - 1
        self.formation_list.blockSignals(False)
        if row_to_select < 0 and self.formation_list.count():
            row_to_select = 0
        if row_to_select >= 0:
            self.formation_list.setCurrentRow(row_to_select)
        else:
            self._refresh_plays()

    def _selected_record_index(self) -> int | None:
        item = self.formation_list.currentItem()
        return int(item.data(Qt.UserRole)) if item is not None else None

    def _record(self, record_index: int) -> splb.SplbRecord | None:
        if self._book is None:
            return None
        return self._book.records[record_index]

    def _wanted_plays(self, record_index: int) -> set[int]:
        record = self._record(record_index)
        if record is None:
            return set()
        base = {entry.play_index for entry in record.entries}
        for play_index, wanted in (self._staged.get(record_index) or {}).items():
            if wanted:
                base.add(play_index)
            else:
                base.discard(play_index)
        return base

    # ------------------------------------------------------------- tag staging

    def _clear_staged(self) -> None:
        self._staged = {}
        self._staged_heirs = {}
        self._staged_moves = {}
        self._staged_trailers = {}

    def _staged_count(self, record_index: int) -> int:
        return (
            len(self._staged.get(record_index) or {})
            + len(self._staged_moves.get(record_index) or {})
            + (1 if record_index in self._staged_trailers else 0)
        )

    def _record_changes(
        self, record_index: int, extra: tuple[StagedChange, ...] = ()
    ) -> tuple[list[splb.MembershipChange], list[splb.TagMove]]:
        staged = [
            change
            for change in self.staged_changes()
            if change.record_index == record_index
        ]
        memberships = [c for c in staged if isinstance(c, splb.MembershipChange)]
        moves = [c for c in staged if isinstance(c, splb.TagMove)]
        for change in extra:
            if isinstance(change, splb.MembershipChange):
                memberships = [
                    m for m in memberships if m.play_index != change.play_index
                ] + [change]
            else:
                moves = [m for m in moves if m.from_play != change.from_play] + [change]
        return memberships, moves

    def _preview(
        self, record_index: int, extra: tuple[StagedChange, ...] = ()
    ) -> tuple[splb.SplbEntry, ...] | None:
        """The record's entries as staged, or None if that state is not legal."""

        record = self._record(record_index)
        if record is None or self._book is None:
            return None
        memberships, moves = self._record_changes(record_index, extra)
        try:
            return splb.apply_record_changes(self._book, record, memberships, moves)
        except ValidationError:
            return None

    def _effective_tags(self, record_index: int) -> dict[int, int]:
        entries = self._preview(record_index)
        record = self._record(record_index)
        if entries is None:
            entries = record.entries if record is not None else ()
        return {entry.play_index: entry.y for entry in entries if entry.tagged}

    def _staged_play_indices(self, record_index: int) -> list[int]:
        entries = self._preview(record_index)
        if entries is not None:
            return [entry.play_index for entry in entries]
        return sorted(self._wanted_plays(record_index))

    def _carry_candidates(self, record_index: int, play_index: int) -> list[int]:
        """Plays that can take this play's tagged slot when it is removed.

        Each one is proved by running the real writer, so the picker never
        offers a choice that would fail at build time.
        """

        outer = self._book.outer_index if self._book is not None else 0
        candidates: list[int] = []
        for other in self._staged_play_indices(record_index):
            if other == play_index:
                continue
            change = splb.MembershipChange(outer, record_index, play_index, False, other)
            if self._preview(record_index, (change,)) is not None:
                candidates.append(other)
        return candidates

    def _move_candidates(self, record_index: int, play_index: int) -> list[int]:
        outer = self._book.outer_index if self._book is not None else 0
        candidates: list[int] = []
        for other in self._staged_play_indices(record_index):
            if other == play_index:
                continue
            move = splb.TagMove(outer, record_index, play_index, other)
            if self._preview(record_index, (move,)) is not None:
                candidates.append(other)
        return candidates

    def removal_needs_heir(self, record_index: int, play_index: int) -> bool:
        """Would dropping this play leave the formation short a tagged slot?"""

        outer = self._book.outer_index if self._book is not None else 0
        change = splb.MembershipChange(outer, record_index, play_index, False)
        return self._preview(record_index, (change,)) is None

    def stage_membership(
        self, record_index: int, play_index: int, wanted: bool, heir: int | None = None
    ) -> None:
        """Stage one add or remove, with an optional heir for its tagged slot."""

        record = self._record(record_index)
        if record is None:
            raise ValidationError("No formation is loaded")
        was_staged = dict(self._staged.get(record_index) or {})
        was_heirs = dict(self._staged_heirs.get(record_index) or {})
        staged = dict(was_staged)
        heirs = dict(was_heirs)
        base = {entry.play_index for entry in record.entries}
        if wanted == (play_index in base) and heir is None:
            staged.pop(play_index, None)
            heirs.pop(play_index, None)
        else:
            staged[play_index] = wanted
            heirs.pop(play_index, None)
            if heir is not None:
                heirs[play_index] = heir
        self._replace_staged(record_index, staged, heirs)
        if self._preview(record_index) is None:
            self._replace_staged(record_index, was_staged, was_heirs)
            raise ValidationError(
                "That change would leave the formation outside the proved tagged-slot "
                "rule, so it was not staged."
            )
        self._after_stage()

    def populated_records_after_staging(
        self, pending_empty: int | tuple[int, ...] | None = None
    ) -> int:
        """How many formations in this book would still hold a play.

        ``pending_empty`` names record(s) the caller is about to empty but has
        not staged yet, so the last-formation guard can answer before the edit
        is applied rather than after.
        """

        if self._book is None:
            return 0
        pending: set[int] = set()
        if isinstance(pending_empty, int):
            pending.add(pending_empty)
        elif pending_empty:
            pending.update(pending_empty)
        total = 0
        for record in self._book.records:
            if not record.populated:
                continue
            if record.record_index in pending:
                continue
            entries = self._preview(record.record_index)
            if entries is None:
                entries = record.entries
            if entries:
                total += 1
        return total

    def stage_empty_formation(self, record_index: int) -> None:
        """Stage removal of every stored play in this record, shedding all tags."""

        self.stage_empty_formations((record_index,))

    def stage_empty_formations(self, record_indexes: tuple[int, ...]) -> None:
        """Empty one or more records, then commit once."""

        if self._book is None:
            raise ValidationError("No playbook is loaded")
        records = []
        for record_index in record_indexes:
            record = self._record(record_index)
            if record is None or not record.entries:
                raise ValidationError("This formation already has no stored plays")
            records.append(record)
        pending = tuple(record.record_index for record in records)
        if self.populated_records_after_staging(pending_empty=pending) == 0:
            raise ValidationError(
                "This is the last formation in the book that still holds a play. "
                "A book with nothing stored anywhere leaves the CPU director "
                "nothing to select at all, so it is refused. Keep one formation "
                "populated, or edit a different book."
            )
        snapshots = []
        try:
            for record in records:
                record_index = record.record_index
                snapshots.append(
                    (
                        record_index,
                        dict(self._staged.get(record_index) or {}),
                        dict(self._staged_heirs.get(record_index) or {}),
                        dict(self._staged_moves.get(record_index) or {}),
                    )
                )
                staged = {entry.play_index: False for entry in record.entries}
                self._replace_staged(record_index, staged, {})
                self._staged_moves.pop(record_index, None)
                if self._preview(record_index) is None:
                    raise ValidationError(
                        "Emptying this formation was refused; the tagged-slot "
                        "rule still applies to a populated record."
                    )
        except ValidationError:
            for record_index, was_staged, was_heirs, was_moves in snapshots:
                self._replace_staged(record_index, was_staged, was_heirs)
                if was_moves:
                    self._staged_moves[record_index] = was_moves
                else:
                    self._staged_moves.pop(record_index, None)
            raise
        self._after_stage()

    def _replace_staged(
        self, record_index: int, staged: dict[int, bool], heirs: dict[int, int]
    ) -> None:
        for store, value in ((self._staged, staged), (self._staged_heirs, heirs)):
            if value:
                store[record_index] = value  # type: ignore[assignment]
            else:
                store.pop(record_index, None)

    def stage_tag_move(self, record_index: int, from_play: int, to_play: int) -> None:
        """Stage moving one tagged slot onto another play in the same formation."""

        if self._book is None:
            raise ValidationError("No playbook is loaded")
        move = splb.TagMove(self._book.outer_index, record_index, from_play, to_play)
        if self._preview(record_index, (move,)) is None:
            raise ValidationError(
                f"Play {from_play} cannot hand its tagged slot to play {to_play} in "
                "this formation."
            )
        moves = self._staged_moves.setdefault(record_index, {})
        moves[from_play] = to_play
        self._after_stage()

    # ------------------------------------------- record-level trailer staging

    def stage_trailer_replace(
        self, record_index: int, formation_index: int, category_index: int
    ) -> None:
        """Repoint one record's trailer at another formation and package."""

        if self._book is None:
            raise ValidationError("No playbook is loaded")
        if self._staged_trailers.get(record_index) == (
            formation_index,
            category_index,
        ):
            return
        self._staged_trailers[record_index] = (formation_index, category_index)
        self._after_stage()

    def stage_record_addition(
        self,
        record_index: int,
        formation_index: int,
        category_index: int,
        play_indices: tuple[int, ...],
    ) -> None:
        """Fill an empty record slot: trailer repoint plus play additions."""

        if self._book is None:
            raise ValidationError("No playbook is loaded")
        record = self._book.records[record_index]
        if record.populated:
            raise ValidationError(
                f"Record {record_index} already holds plays; repoint it instead "
                "or pick the first empty slot."
            )
        if record_index in self._staged_trailers:
            raise ValidationError(
                f"Record {record_index} is already staged as a new formation. "
                "Pick the next free slot, or revert the staged add first."
            )
        if not 1 <= len(play_indices) <= splb.ENTRY_CAPACITY:
            raise ValidationError(
                f"Pick 1..{splb.ENTRY_CAPACITY} plays for the new formation"
            )
        self._staged_trailers[record_index] = (formation_index, category_index)
        staged = dict(self._staged.get(record_index) or {})
        for play in play_indices:
            staged[int(play)] = True
        self._staged[record_index] = staged
        self._after_stage()

    def _package_labels(self) -> list[tuple[int, str]]:
        reader = getattr(self.facade, "master_categories", None)
        try:
            categories = tuple(reader()) if reader is not None else ()
        except Exception:
            categories = ()
        if not categories:
            return [(index, f"package {index}") for index in range(splb.CATEGORY_COUNT)]
        labels = []
        for item in categories:
            roles = tuple(item["roles"])
            te = roles.count(8)
            wr = roles.count(9)
            backs = roles.count(10) + roles.count(11)
            suffix = ""
            if te == 1 and wr == 4 and backs == 0:
                suffix = "  (the pass-friendly 01 set)"
            labels.append(
                (
                    int(item["index"]),
                    f"{int(item['index'])} {item['name']} — {backs} RB, "
                    f"{te} TE, {wr} WR{suffix}",
                )
            )
        return labels

    def _trailer_dialog(
        self,
        title: str,
        initial: tuple[int, int],
        allow_plays: bool,
        accept_label: str = "OK",
    ) -> tuple[int, int, tuple[int, ...]] | None:
        dialog = QDialog(self)
        dialog.setObjectName("formationTrailerDialog")
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Changes which formation this record lines up in, and which "
                "personnel package it joins. The game resolves a requested "
                "personnel row through the book's package mask, and a stored "
                "play per record entry — a play this record shares with other "
                "records can still resolve there. Which row the CPU requests, "
                "when, and which record it finally uses is runtime-unproved. "
                "Check it in Xenia."
            )
        )
        form = QVBoxLayout()
        formation_combo = QComboBox()
        for index in sorted(self._formations):
            formation_combo.addItem(f"{index} {self._formations[index]}", index)
        row = formation_combo.findData(initial[0])
        if row >= 0:
            formation_combo.setCurrentIndex(row)
        package_combo = QComboBox()
        for index, label in self._package_labels():
            package_combo.addItem(label, index)
        row = package_combo.findData(initial[1])
        if row >= 0:
            package_combo.setCurrentIndex(row)
        form.addWidget(QLabel("MASTER formation"))
        form.addWidget(formation_combo)
        form.addWidget(QLabel("Personnel package"))
        form.addWidget(package_combo)
        plays_list: QListWidget | None = None
        if allow_plays:
            plays_list = QListWidget()
            plays_list.setSelectionMode(QAbstractItemView.MultiSelection)
            for index, name in enumerate(self._plays):
                plays_list.addItem(f"{index} {name}")
            plays_list.setMaximumHeight(180)
            form.addWidget(QLabel("Plays the new formation stores (1-84)"))
            form.addWidget(plays_list)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText(accept_label)
            ok_button.setDefault(True)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        chosen_plays: tuple[int, ...] = ()
        if plays_list is not None:
            chosen_plays = tuple(
                sorted(plays_list.row(item) for item in plays_list.selectedItems())
            )
        return (
            int(formation_combo.currentData()),
            int(package_combo.currentData()),
            chosen_plays,
        )

    def _change_trailer(self) -> None:
        record_index = self._selected_record_index()
        record = (
            self._record(record_index) if record_index is not None else None
        )
        if record is None:
            QMessageBox.information(
                self, "Pick a formation", "Select a formation first."
            )
            return
        initial = self._staged_trailers.get(
            record_index, (record.formation_index, record.category_index)
        )
        result = self._trailer_dialog(
            "Change formation / personnel package",
            initial,
            allow_plays=False,
            accept_label="Apply change",
        )
        if result is None:
            return
        try:
            self.stage_trailer_replace(
                record_index, result[0], result[1]
            )
        except ValidationError as exc:
            QMessageBox.information(self, "Could not repoint the record", str(exc))

    def _first_empty_record(self) -> int | None:
        """The first free record slot after the book's populated run.

        New formations append past the last populated record -- never into a
        gap between populated records -- so every retail record stays exactly
        where the game expects it.  A slot already staged by an earlier add is
        taken, so several formations can be added in one session, one slot
        each (Urianus, 2026-08-22: the flow used to stop at one).
        """

        if self._book is None:
            return None
        used = [r.record_index for r in self._book.records if r.populated]
        start = (max(used) + 1) if used else 0
        for slot in range(start, splb.RECORD_COUNT):
            if slot not in self._staged_trailers:
                return slot
        return None

    def _add_record(self) -> None:
        if self._book is None:
            QMessageBox.information(
                self, "Pick a playbook", "Choose a stock playbook first."
            )
            return
        slot = self._first_empty_record()
        if slot is None:
            QMessageBox.information(
                self,
                "No free record slot",
                "Every record slot after this book's last formation is already "
                "staged as a new formation. Build or revert those additions "
                "before adding another one.",
            )
            return
        result = self._trailer_dialog(
            f"Add a formation (record {slot})",
            (133, 7),
            allow_plays=True,
            accept_label="Add formation",
        )
        if result is None:
            return
        if not result[2]:
            QMessageBox.information(
                self, "Pick plays", "The new formation needs at least one play."
            )
            return
        try:
            self.stage_record_addition(slot, result[0], result[1], result[2])
        except ValidationError as exc:
            QMessageBox.information(self, "Could not add the formation", str(exc))

    def _after_stage(self) -> None:
        self._commit_to_project()
        self._refresh_formations()
        self._refresh_plays()
        self._refresh_actions()
        self.modifiedChanged.emit()

    # --------------------------------------------------------- project storage

    def _commit_to_project(self) -> None:
        """Hand the whole staged set to the session so Save Project keeps it.

        Before this existed the panel was the only place the edits lived, so
        Save Project wrote a file that silently did not contain them (reported
        by Urianus against alpha.69 and again against alpha.70).  The session
        now holds one modification per staged change, exactly as the assignment
        route panel does, and the project archive round-trips them.
        """

        stage = getattr(self.facade, "stage_splb_membership", None)
        if stage is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        replace_outer = None if self._book is None else int(self._book.outer_index)
        try:
            stage(self.staged_changes(), replace_outer=replace_outer)
        except TypeError:
            stage(self.staged_changes())
        except Exception as exc:      # session/validation errors are user-facing
            QMessageBox.warning(
                self,
                "These playbook edits were not saved into the project",
                "The change is still shown here, but the project could not "
                f"store it:\n\n{exc}\n\nUse Revert changes and try again, or "
                "build the copied 0A now — otherwise Save Project will not "
                "carry these edits.",
            )

    def _restore_from_project(self) -> None:
        """Rebuild the panel's staged state from what the project already holds."""

        self._clear_staged()
        if self._book is None:
            return
        reader = getattr(self.facade, "staged_splb_changes", None)
        if reader is None:
            return
        try:
            changes = reader()
        except Exception:
            return
        for change in changes:
            if change.outer_index != self._book.outer_index:
                continue
            if isinstance(change, splb.MembershipChange):
                self._staged.setdefault(change.record_index, {})[
                    change.play_index
                ] = change.member
                if change.tag_heir is not None:
                    self._staged_heirs.setdefault(change.record_index, {})[
                        change.play_index
                    ] = change.tag_heir
            elif isinstance(change, splb.TagMove):
                self._staged_moves.setdefault(change.record_index, {})[
                    change.from_play
                ] = change.to_play
            elif isinstance(change, splb.TrailerReplace):
                self._staged_trailers[change.record_index] = (
                    change.formation_index,
                    change.category_index,
                )

    # ------------------------------------------------------------------- plays

    def _refresh_plays(self) -> None:
        self._loading = True
        try:
            self.play_list.clear()
            record_index = self._selected_record_index()
            record = self._record(record_index) if record_index is not None else None
            if record is None or not self._plays:
                self.play_header.setText("Plays")
                return
            tagged = self._effective_tags(record.record_index)
            wanted = self._wanted_plays(record.record_index)
            needle = self.play_search.text().strip().casefold()
            for play_index, name in enumerate(self._plays):
                if needle and needle not in name.casefold():
                    continue
                item = QListWidgetItem(
                    f"{name}   [tagged slot {tagged[play_index]}]"
                    if play_index in tagged
                    else name
                )
                item.setData(Qt.UserRole, play_index)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if play_index in wanted else Qt.Unchecked
                )
                if play_index in tagged:
                    slot = tagged[play_index]
                    audible = (
                        f"audible {slot + 1}"
                        if slot in {0, 1, 2}
                        else f"tagged slot {slot}"
                    )
                    item.setToolTip(
                        f"This play is {audible} for this formation. Untick it "
                        "and the studio will ask which other play should take "
                        "the audible, or use Move tagged slot first."
                    )
                self.play_list.addItem(item)
            self.play_header.setText(
                f"Stored plays for "
                f"{self._formations.get(record.formation_index, '?')} — "
                f"{len(wanted)} of {len(self._plays)}"
            )
        finally:
            self._loading = False
        self._refresh_actions()

    def _restore_tick(self, item: QListWidgetItem, checked: bool) -> None:
        self._loading = True
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._loading = False

    def _play_toggled(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        record_index = self._selected_record_index()
        record = self._record(record_index) if record_index is not None else None
        if record is None:
            return
        play_index = int(item.data(Qt.UserRole))
        wanted = item.checkState() == Qt.Checked
        heir: int | None = None
        if not wanted and self.removal_needs_heir(record.record_index, play_index):
            heir = self._ask_for_heir(record.record_index, play_index)
            if heir is None:
                self._restore_tick(item, True)
                return
        try:
            self.stage_membership(record.record_index, play_index, wanted, heir)
        except ValidationError as exc:
            self._restore_tick(item, not wanted)
            QMessageBox.information(self, "That edit was not staged", str(exc))

    def _ask_for_heir(self, record_index: int, play_index: int) -> int | None:
        """Offer to carry the tagged slot onto another play instead of refusing."""

        tagged = self._effective_tags(record_index)
        slot = tagged.get(play_index)
        candidates = self._carry_candidates(record_index, play_index)
        if slot is None:
            QMessageBox.information(
                self,
                "This play cannot be removed yet",
                f"{self._play_name(play_index)} is not an audible, but removing "
                "it would leave this formation with more audibles than plays. "
                "Add another play first, or move an audible with Move tagged "
                "slot, then remove this one.",
            )
            return None
        if not candidates:
            QMessageBox.information(
                self,
                "Move the audible first",
                f"{self._play_name(play_index)} is an audible, and no other "
                "play here can take it. Tick another play into this formation, "
                "or use Move tagged slot, then remove this one. Emptying the "
                "whole formation is a last resort and changes what the CPU "
                "calls — read that button's warning first.",
            )
            return None
        answer = QMessageBox.question(
            self,
            "Move the audible, then remove?",
            f"{self._play_name(play_index)} is an audible for this formation. "
            "Hand that audible to another play here and the removal goes through.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return None
        return self._pick_play(
            candidates,
            "Carry the tagged slot to",
            f"Which play takes tagged slot {slot}?",
        )

    def _pick_play(self, candidates: list[int], title: str, prompt: str) -> int | None:
        labels = [self._play_name(play) for play in candidates]
        choice, accepted = QInputDialog.getItem(self, title, prompt, labels, 0, False)
        if not accepted:
            return None
        return candidates[labels.index(choice)]

    def _play_name(self, play_index: int) -> str:
        if 0 <= play_index < len(self._plays):
            return self._plays[play_index]
        return f"play {play_index}"

    def _move_tag(self) -> None:
        record_index = self._selected_record_index()
        if record_index is None or self._book is None:
            QMessageBox.information(
                self,
                "Pick a formation first",
                "Load a playbook and select a formation, then select the play whose "
                "tagged slot you want to move.",
            )
            return
        item = self.play_list.currentItem()
        play_index = int(item.data(Qt.UserRole)) if item is not None else -1
        tagged = self._effective_tags(record_index)
        if play_index not in tagged:
            QMessageBox.information(
                self,
                "Select a tagged play",
                "Highlight the play that currently holds the tagged slot, then use "
                "this button to hand the slot to another play in the same "
                "formation.\n\n" + TAG_BOUNDARY,
            )
            return
        candidates = self._move_candidates(record_index, play_index)
        if not candidates:
            QMessageBox.information(
                self,
                "Nowhere to move it",
                "This formation has no other play that can hold the slot.",
            )
            return
        target = self._pick_play(
            candidates,
            "Move tagged slot",
            f"Move tagged slot {tagged[play_index]} from "
            f"{self._play_name(play_index)} to:",
        )
        if target is None:
            return
        try:
            self.stage_tag_move(record_index, play_index, target)
        except ValidationError as exc:
            QMessageBox.information(self, "That move was not staged", str(exc))

    def _explain_tags(self) -> None:
        QMessageBox.information(self, "Tagged slots", TAG_BOUNDARY)

    def _show_research_pins(self) -> None:
        """The full static record, on request rather than in the way.

        The panel used to word-wrap all of this under the play list. Keeping it
        reachable is the honesty requirement; keeping it inline was not.
        """

        box = QMessageBox(self)
        box.setWindowTitle("Research pins")
        box.setText(
            "Every executable address behind what this panel claims — including "
            "the candidates that were checked and withdrawn, so they are not "
            "re-chased. None of this changes what the buttons do."
        )
        box.setDetailedText(f"{RESEARCH_PINS}\n\n{TAG_RESEARCH_PINS}")
        box.setStandardButtons(QMessageBox.Close)
        box.exec_()

    def _empty_formation(self) -> None:
        reason = str(self.empty_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot empty this formation yet", reason)
            return
        record_index = self._selected_record_index()
        record = self._record(record_index) if record_index is not None else None
        if record is None:
            QMessageBox.information(
                self,
                "Pick a formation first",
                "Load a playbook and select a formation, then empty its stored "
                "play list.",
            )
            return
        if not record.entries and not (self._staged.get(record.record_index) or {}):
            QMessageBox.information(
                self,
                "Already empty",
                "This formation already has no stored plays.",
            )
            return
        partner = None
        if self._book is not None:
            partner = splb.find_flip_partner_record(
                self._book, record, self._formations
            )
            if partner is not None and not partner.populated:
                partner = None
        pending = (record.record_index,)
        if partner is not None:
            pending = (record.record_index, partner.record_index)
        remaining = self.populated_records_after_staging(pending_empty=pending)
        if remaining == 0:
            QMessageBox.information(
                self,
                "This is the book's last populated formation",
                "Emptying it would leave this playbook with no stored play in any "
                "formation, and the CPU director would have nothing at all to "
                "select. That is refused. Keep one formation populated, or edit a "
                "different book.",
            )
            return
        mine = self._formations.get(record.formation_index, "this formation")
        extra = ""
        if partner is not None:
            other = self._formations.get(partner.formation_index, "its Flip twin")
            extra = (
                f"\n\n{mine} has an exact “ Flip” twin: {other}. Emptying only "
                "one of that pair hangs on load (Urianus, 2026-08-14). Both "
                "will be emptied together."
            )
        answer = QMessageBox.question(
            self,
            "Empty this formation?" if partner is None else "Empty this Flip pair?",
            EMPTY_FORMATION_WARNING
            + "\n\n"
            f"Remove all stored plays from {mine}"
            + (f" and {other}" if partner is not None else "")
            + f". {remaining} formation"
            f"{'s' if remaining != 1 else ''} in this book would still hold "
            "plays. The audibles go with them. The formation name stays in "
            "the book, so the CPU can still pick it."
            + extra,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if partner is None:
                self.stage_empty_formation(record.record_index)
            else:
                self.stage_empty_formations(
                    (record.record_index, partner.record_index)
                )
        except ValidationError as exc:
            QMessageBox.information(self, "That edit was not staged", str(exc))

    # ---------------------------------------------------------------- actions

    def staged_changes(self) -> tuple[StagedChange, ...]:
        if self._book is None:
            return ()
        out: list[StagedChange] = []
        for record_index, plays in sorted(self._staged.items()):
            heirs = self._staged_heirs.get(record_index) or {}
            for play_index, wanted in sorted(plays.items()):
                out.append(
                    splb.MembershipChange(
                        self._book.outer_index,
                        record_index,
                        play_index,
                        wanted,
                        None if wanted else heirs.get(play_index),
                    )
                )
        for record_index, moves in sorted(self._staged_moves.items()):
            for from_play, to_play in sorted(moves.items()):
                out.append(
                    splb.TagMove(
                        self._book.outer_index, record_index, from_play, to_play
                    )
                )
        for record_index, (formation_index, category_index) in sorted(
            self._staged_trailers.items()
        ):
            out.append(
                splb.TrailerReplace(
                    self._book.outer_index,
                    record_index,
                    formation_index,
                    category_index,
                )
            )
        return tuple(out)

    def _refresh_actions(self) -> None:
        staged = self.staged_changes()
        # Never silent-gray: both stay clickable and explain.
        self.revert_button.setEnabled(True)
        self.build_button.setEnabled(True)
        if not bool(getattr(self.facade, "source_ready", False)):
            block = "Load your APF game first, then pick a playbook."
        elif self._book is None:
            block = "Choose a stock playbook first."
        elif not staged:
            block = (
                "Tick or untick plays for a formation, or move a tagged slot, first. "
                "Nothing is staged yet."
            )
        else:
            block = ""
        self.build_button.setProperty("disableReason", block)
        self.move_tag_button.setToolTip(
            "Hand the highlighted play's tagged slot to another play in the same "
            "formation, including one you just ticked in. The count of tagged "
            "slots never changes unless you empty the formation."
        )
        self.empty_button.setEnabled(True)
        empty_block = ""
        if not bool(getattr(self.facade, "source_ready", False)):
            empty_block = "Load your APF game first, then pick a playbook."
        elif self._book is None:
            empty_block = "Choose a stock playbook first."
        elif self._selected_record_index() is None:
            empty_block = "Select a formation first."
        self.empty_button.setProperty("disableReason", empty_block)
        self.empty_button.setToolTip(
            empty_block
            or "Remove every stored play from this formation in one request. "
            "Tagged slots are shed because min(4, 0) is 0. Reported in-game to "
            "make the CPU call plays and personnel packages this book does not "
            "contain — the confirmation explains what was seen. Emptying the "
            "book's last populated formation is refused."
        )
        self.build_button.setToolTip(
            block
            or f"Write {len(staged)} playbook change"
            f"{'s' if len(staged) != 1 else ''} into a copied 0A. Your source is "
            "never opened for writing."
        )
        revert_block = "" if staged else "There are no staged playbook changes."
        self.revert_button.setProperty("disableReason", revert_block)
        self.revert_button.setToolTip(
            revert_block or f"Discard {len(staged)} staged change(s)."
        )
        trailer_block = ""
        if not bool(getattr(self.facade, "source_ready", False)):
            trailer_block = "Load your APF game first, then pick a playbook."
        elif self._book is None:
            trailer_block = "Choose a stock playbook first."
        self.retarget_button.setEnabled(True)
        self.retarget_button.setProperty("disableReason", trailer_block)
        self.retarget_button.setToolTip(
            trailer_block
            or "Repoint the selected record's trailer at another MASTER "
            "formation and personnel package. Gives books like O-Ace the "
            "1 TE / 4 WR package the pass-down ladder looks for."
        )
        add_block = trailer_block
        if not add_block and self._first_empty_record() is None:
            add_block = (
                "Every record slot after this book's last formation is already "
                "staged as a new formation."
            )
        self.add_record_button.setEnabled(True)
        self.add_record_button.setProperty("disableReason", add_block)
        self.add_record_button.setToolTip(
            add_block
            or "Append a formation to the book's first free record slot. Each "
            "add takes the next slot, so several formations can be added one "
            "after another, each with a personnel package and stored plays."
        )
        self.third_long_button.setEnabled(True)
        self.third_long_button.setToolTip(
            "The CPU's 3rd-and-long choice itself stays in default.xex, but the "
            "personnel ladder is data — click for a plain-language explanation "
            "and the new package levers."
        )

    def _refuse_third_and_long(self) -> None:
        QMessageBox.information(
            self,
            "3rd-and-long: the XEX chooses; the ladder is data",
            THIRD_AND_LONG_STATUS,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Nothing to revert", reason)
            return
        self._clear_staged()
        self._after_stage()

    def _build(self) -> None:
        reason = str(self.build_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot build the playbook yet", reason)
            return
        index_0a = self._index_0a()
        if index_0a is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Choose the folder for the copied 0A", str(Path.home())
        )
        if not directory:
            return
        out_root = Path(directory)
        if any(out_root.iterdir()):
            answer = QMessageBox.question(
                self,
                "Replace files in this folder?",
                f"{out_root} is not empty. The copied 0A will be written here "
                "so Xenia can keep this path. Other files already here stay "
                "unless they share a name with the volume.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        changes = self.staged_changes()

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            progress("Compiling the stock playbook", 0, 2)
            entry = splb.build_book_patch(index_0a, changes)
            progress("Writing the copied volume", 1, 2)
            written = _publish_copied_volume(index_0a, out_root, entry)
            progress("Modded playbook ready", 2, 2)
            return {"path": written, "report": entry.report}

        def done(result: object) -> None:
            payload = result  # type: ignore[assignment]
            report = payload["report"]  # type: ignore[index]
            verification = report.get("verification", {})
            shared = [
                row
                for row in report.get("trailer_record_play_sharing", [])
                if row.get("shared_with_records")
            ]
            sharing_note = ""
            if shared:
                sharing_note = (
                    f"\n\n{len(shared)} of the repointed/added records store "
                    "plays that other records in this book store too. The game "
                    "resolves a stored play per record entry, and a personnel "
                    "row through the book's package mask — which record it "
                    "finally uses for a shared play is runtime-unproved, so "
                    "check this book in Xenia."
                )
            QMessageBox.information(
                self,
                "Modded playbook built",
                f"Wrote:\n{payload['path']}\n\n"  # type: ignore[index]
                f"{len(report['changes'])} change"
                f"{'s' if len(report['changes']) != 1 else ''} to "
                f"{report['book_name'] or 'an unnamed book'} · "
                f"{verification.get('changed_byte_count', 0)} byte(s) differ from "
                "your source." + sharing_note + "\n\n" + BOUNDARY,
            )

        self.run_task("Building the modded playbook", operation, done, True)


def _publish_copied_volume(index_path: Path, out_root: Path, entry) -> Path:
    """Copy the user's volume and replace only the one rebuilt entry."""

    from mod_editor.apf_studio.backend import ensure_tools_importable

    ensure_tools_importable()
    import apf_logo_patch  # type: ignore
    import apf_outer  # type: ignore

    source_root = index_path.parent
    for sibling in source_root.iterdir():
        if sibling.name == index_path.name or not sibling.is_file():
            continue
        target = out_root / sibling.name
        if target.exists() or target.is_symlink():
            continue
        failures: list[str] = []
        for linker in (os.symlink, os.link):
            try:
                linker(sibling, target)
                break
            except (OSError, NotImplementedError, AttributeError) as exc:
                failures.append(f"{getattr(linker, '__name__', 'link')}: {exc}")
        else:
            try:
                shutil.copyfile(sibling, target)
                if target.stat().st_size != sibling.stat().st_size:
                    raise OSError("copied sibling pack has the wrong size")
            except OSError as exc:
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Could not stage sibling pack {sibling.name} without "
                    f"administrator rights ({'; '.join(failures)}; copy: {exc}). "
                    "Choose a writable output folder and try again."
                ) from exc
    archive = apf_outer.parse_archive(index_path)
    outer_entry = archive.entries[entry.outer_index]
    destination = out_root / index_path.name
    write_to = destination
    if destination.exists() or destination.is_symlink():
        write_to = destination.with_name(destination.name + ".apf-new")
        if write_to.exists() or write_to.is_symlink():
            write_to.unlink()
    try:
        apf_logo_patch._write_copied_volume(
            index_path, write_to, outer_entry, entry.entry_bytes
        )
        if write_to != destination:
            os.replace(write_to, destination)
    except BaseException:
        if write_to != destination:
            write_to.unlink(missing_ok=True)
        raise
    return destination


__all__ = [
    "ApfPlaybookMembershipPanel",
    "BOUNDARY",
    "EMPTY_FORMATION_WARNING",
    "RESEARCH_PINS",
    "TAG_BOUNDARY",
    "TAG_RESEARCH_PINS",
]

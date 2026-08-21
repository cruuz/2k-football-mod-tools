"""Edit APF 2K8 stock CPU playbooks (``SPLB``) in a copied volume.

These are the stock playbook resources the game ships.  A roster save's 36
offensive and 33 defensive playbook records are only *labels*: they carry a
name, a type string and a side, with no content pointer at all, and they resolve
to seven offensive and four defensive real types.  The stored membership lives
here, on the disc, as fifteen ``SPLB`` resources of exactly 32,288 bytes each.
The decompressed executable **does** consume that list: ``0x84a8ac30`` counts
entries until play-index ``1023`` (cap 84), ``0x84a8bd20`` returns the nth
MASTER play or null, and ``0x84a8aa80`` finds a play by tagged slot. An empty
record (first entry ``0x13FF``) makes count return 0 and get-nth return null;
surveyed callers skip the play loop when count is 0, so the four tagged plays
cannot be returned from that record. Whether the director then selects a
different formation, and which play it calls on 3rd-and-long from a still-
populated list, remain runtime-unproved. Automatic WR3→TE package substitution
is not offered. The package-map byte at formation ``+0x11`` is consumed
(``lbz`` at ``0x84a19f04``) and stored on the on-field object at ``+0x34``
(``0x8485e7e0``). Byte table ``0x820FC320`` (loaded by ``0x84a9ae68``) converts
that role id: 8 → TE (roster 9), 9 → WR (roster 3). That is the WR3↔TE pair.
The 11-player builder at ``0x84860020`` indexes that map by slot 0..10
(``addi r29, r25, 5`` / ``lbzx`` at ``0x848605b4``, loop ``cmpwi r31, 44`` at
``0x848605d8``) and the assigner stores the role at on-field ``+0x34``.
Swapping map bytes 8 and 9 has not been runtime-proved. MASTER PLAY's 28
named categories at ``+0x44`` (stride ``0x10``) are personnel packages
(Ace, Pro Set, 5 Wide, Flush, …). SPLB trailer bits 23..17 index them;
``0x8485bd38`` extracts that field and returns the category record
(``addi +0x44``). After the slot loop, the builder ``lbz``'s category ``+4``
and indexes word table ``0x84E6C620`` (``mulli 11`` at ``0x84a9acc8``) into
on-field ``+0x35``. 5 Wide's table row is five 9s (WR); Ace's skill
slots are 8,9,9,8,10 (TE/WR). Eligibility at ``0x8485e810`` ANDs the map-role
word-mask from ``0x820FC380`` (role 8 = ``0xCD00``, role 9 = ``0xDD20``) with
a personnel-table cell. Both of those masks AND a 5 Wide skill cell
``0x200`` are 0, so that bit does not distinguish WR3 from TE. The same
AND also runs in the 11-slot loop at ``0x84862580``. ``0x844dbe00`` is
``.pdata`` unwind metadata, not a script opcode table. That is
static, not a runtime WR3→TE proof. That
second layer is not a 3rd-and-long picker.
``0x84a472d0`` walks the play-type UI table at ``0x84e4d810`` (obj+4 is the
page, not down). ``0x8486ce88`` is an in-game play picker gated on situation
word0 and ``+0x2BC`` (a 0..3 playcall tab the UI writes, including ``li 3``
at ``0x84a23ea0``), not ``+0x254``/``+0x25C``.
``0x84a89ea8`` maps a play pointer onto an SPLB record (index vs 176);
it is not a situation picker. Situation ``+0x1F8`` is a 0..7 play-type
filter (table ``0x84DCB2A8``), not down.
``0x848699d8`` filters SPLB plays by type nibble (``srwi 28``), not down.
It reads the current book from playcall ``+0x20`` (global ``0x851A2780``);
``0x8493d968`` registers that object. Packed setter ``0x8493e180`` has
0 ``bl`` callers. No surveyed store writes a book pointer there from
down. One-hop/two-hop from situation ``+0x254`` loaders to the picker
is empty.
``0x8485e7f8`` has 0 ``bl`` callers, no ``lis``/``addi`` of its address,
and the assigner does not fall through into it. The in-game builder does
not call the eligibility AND. The ``DRCT`` crc32 immediate is a
type-registry constructor; insert ``0x8466b998`` is type-list
registration; ``0x8466af70`` loads ``dir_ingame.iff`` via ``0x8468da70``,
not an instruction interpreter. ``0x8466a818`` relocates DRCT pointers
(NFL ``0x000dc700`` analog: ``+0x18`` / 217 slots / ``+0x20``
instructions / ``+0x14`` strings); ``0x8466aae0`` walks the relocated
fixed table. That is not the opcode consumer (NFL ``0x000dca40``).
``0x8466abc0`` indexes fixed-record children via ``+0x18`` (NFL
``0x000dc8e0`` analog); ``0x8466af28`` indexes strings via ``+0x14``
(NFL ``0x000dcba0`` analog). ``0x8466ac38`` consumes those relocated
fixed records, not instruction opcodes. Packed playcall ``+0x20``
setter ``0x8493e180`` has 0 ``bl``, 0 fullword, and 0 ``lis``/``addi``.
Picker ``0x8486ce88`` takes that playcall object as ``r3`` (``lwz`` from
``0x851A2780`` at ``0x8470c2c4``, jump-table case 2 of ``0x8470bf18``).
That jump table's ``r3`` is a small integer mode 0..19 (wrapper
``0x84712498``). Case 2 is only entered with ``li r3, 2`` at
``0x847163d4`` inside float-gated ``0x84716310`` — frontend, not CPU
down/ytg. ``0x84a254e0`` and ``0x84892df8`` are playcall UI.
``0x84867938`` also reads ``+0x20``. No surveyed store writes a book
pointer there. Packed ``stw r4, 32(r3); blr`` (16 sites) and
compare-and-set ``0x84a4c658`` have 0 ``bl`` / 0 fullword / 0
``lis``/``addi``. Find-by-slot's book comes from ``0x8520CDE0`` as
``r4`` (static init ``0x84a139d0`` / stw ``0x84a139f4``). UI
``0x84a28318`` reads playcall ``+0x1C`` and ``+0x20`` into
``0x85212D30`` — a reader. Shadow ``0x84887e18`` writes bitmasks to
``0x8516C908+0x20``, not the playcall object. 0 ``stw r3, 32(playcall)``
after a global load. 0 ``bctrl`` sites sit near both ``lhz +6``
and ``+0x20``. Slot ``+0`` can be type singleton ``0x850F1218`` or
``0x850F1260`` (install ``0x84ad0048``). Init ``0x847c6da8`` copies the
live MASTER pointer from ``0x84F3F7D8+0x2C`` (getter ``0x849fd6a8``)
onto that type object's ``+0x20``. ``0x84a89e08`` turns that pointer
into MASTER formation ``+0x244``. Helper ``0x8486cd80`` is UI-only
(caller ``0x84a254d0``). Remaining ``lhz +6`` functions that also
touch ``+0x20`` are gfx, not NFL ``0x000dca40``. ``lwz +0x254`` then
``cmpwi 3/4`` is only HUD/practice. Setter ``0x849fd6c8`` is bind/
SPLB-select (table ``0x851D9660``, stride 32288 via ``0x849fcf60``),
not per-play. 0 functions load down/ytg within ±80 insns of getter/
fetch/picker. DRCT property table ``0x84EE65C0`` is packed field
accessors, not the instruction consumer. ``0x849d81d0`` is stored into
``0x84E28670+0x2C94`` at init (0 ``bl``, 0 ``lwz`` of that slot).
0 of 74 ``0x849fcf60`` callers load down/ytg. ``get_down`` only
appears in table ``0x84EB0DE4``. That blob is packed situation
field getters (0 ``lis``/``addi``, 0 aligned inbound pointers).
addi-32/lwzx/bctrl is Altivec ``0x8484d488`` / vec-jump
``0x84878588``, not NFL ``0x000dca40``. Property-get-by-id
``0x849c9c90`` takes r4=997..999, not down. The only non-vtable
lwz+0x20/lwzx/bctrl is ``0x84880740`` (flag + jump table
``0x84DBB408``). Relocator ``0x8466a994`` relocates an
*inline* instruction directory at ``+0x20`` (not a pointer).
0 surveyed ``addi 32``/``lwzx`` function also has ``lhz +6``.
0 packed twin of string indexer ``0x8466af28`` for inline ``+0x20``.
NFL ``0x000dca40`` is a bitset/float lookup (table ``0xB73BD0``),
not a packed instruction-dir indexer. ``dir_ingame.iff`` (outer 153)
has 1015 instruction records; 1014 begin ``0B 00 01 00`` then a token
at +4 — bytecode, not a C++ vtable. The relocator rewrites only the
inline directory words; it does not follow those pointers into record
bodies. Packed ``lhz +6`` getter ``0x84ab2010`` has 0 ``bl`` and 0
inbound pointers. DRCT vtable[2] ``0x8466ba30`` unlinks a list.
Byte-stream ``0x8466bd38`` compares 94/96/97 and 275–330, not
instruction tokens. ``0x84bcd760`` is a string classifier (0 ``bl``).
0 ``addi 32``/``lwzx``/``lbz 0(record)`` consumer.
``dir_wrapup.iff`` (outer 265) has 96 records, all ``0B 00``. Groups
are tagged fields (``0B 00`` + u16 field + u8), not a VM opcode at
+4. vtable[0] ``0x8466b8b0`` only relocates then walks the fixed
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
ASCII Y/I. 0 ``cmpwi 0x0B00`` in TEXT. ``0x848bb1a8`` is RTTI class
2 vs 11. ``0x8466b660`` is a map count vs 256, not field ``0x0100``.
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
caller ``0x84b94258`` switches on first byte 0..4. Non-``0B``
leftovers are concatenated typed groups: type ``0x04`` is tag +
4-byte LE float (size 5) on APF and NFL; types ``0x05``/``0x06``/
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

Layout, established by decoding all fifteen books and checking every decoded
name against the MASTER ``PLAY`` resource:

* ``0x0C`` magic ``BLPS``; ``0x20`` inner name ``spb`` UTF-16BE; ``0x30`` book
  name UTF-16BE (``O-ZoneBlock``, ``X-43Cover2``, ...).
* A 176-record array covering ``0x0070``..``0x7970``, stride 176.  Record *k*
  is 168 bytes of entries at ``0x70 + 176k`` followed by an 8-byte trailer at
  ``0x118 + 176k``.  The trailer is a *trailer*, not a header: ``0x68..0x6F`` is
  zero in every book, and reading it as a leading header makes every book's
  record 0 claim formation 0.
* Trailer word A (``+0xA8``, big-endian u32): bits 31..24 are the MASTER
  formation index, bits 23..17 the primary category, and three 3-bit fields at
  16..14, 13..11 and 10..8 whose meaning is **not** established.  Trailer word
  B (``+0xAC``) is a category membership bitmask.
* Each entry is a big-endian u16: bits 15..13 ``X``, bits 12..10 ``Y``, bits
  9..0 the MASTER play index (0..585).  Entries are always a contiguous prefix
  followed by pure ``0x13FF`` filler -- no exceptions across 2,640 records --
  and ``0x13FF`` is simply an out-of-range play index used as a terminator.

Why the unproved fields do not block this writer: it only ever rewrites the
168-byte entry prefix of one record.  The trailer, both unmapped tail regions
(``0x7998``..``0x79E4`` and ``0x7D98``..``0x7E08``), every other record and
every other byte of the volume are preserved exactly, and an independent
verifier re-derives that before anything is published.

``Y`` marks a small set of distinguished plays per formation, and across all 209
populated records of the fifteen retail books one rule is exact with zero
exceptions: a formation carries ``min(4, plays)`` tagged slots.  The eight
formations carrying fewer than four are exactly the eight with fewer than four
plays.  Which values those short formations use is a distribution rather than a
rule -- one play carries 1, two carry 0 and 1, three carry 0, 1 and 2 -- so this
writer only follows that order when it has to pick a slot the user did not.

Those tags are authored per formation, not a side effect of position.  In
``O-SinglebackAce`` the ``Ace`` and ``Ace Flip`` records hold byte-identical
77-play lists -- same play indices, same ``X`` values -- yet ``Ace`` tags entry
slots 70..73 while ``Ace Flip`` tags 0..3, and only 137 of the 209 records tag
their leading entries at all.

Three of the tags are the formation's **audibles**, proved in the game's own
code rather than inferred from the data's shape.  Community reporter Urianus
read it off the data first -- "the user only gets 3 per formation" -- and the
decompressed executable agrees.  The game does not merely read these bits, it
writes them::

    0x84864c70  rlwinm r11, r31, 1, 0, 30    ; entry index * 2
    0x84864c74  lhzx   r10, r11, r29         ; load the SPLB entry
    0x84864c78  rlwimi r10, r28, 10, 19, 21  ; insert r28 into bits 12..10
    0x84864c7c  sthx   r10, r11, r29         ; store it back
    0x84864c80  addi   r28, r28, 0x1
    0x84864c84  cmpwi  cr6, r28, 2
    0x84864c88  bngt   cr6, 0x84864bd4       ; counter runs 0, 1, 2
    0x84864c90  addi   r29, r29, -0xb0       ; -176: one record per formation

Three slots per formation, stepping exactly one record.  ``Y == 4`` is what an
untagged play carries and the loop scans for those as candidates.  The move
this writer performs is the game's own: ``0x84a8ab28`` takes a slot off one play
and puts it on another.  Supporting accessors: ``0x848630e8`` returns
``(entry >> 10) & 7``, ``0x848630f8`` writes it back with ``rlwimi``/``sthx``,
and ``0x84a8aa80`` (mflr; walk at ``0x84a8aa84``) returns the play whose ``Y``
equals a caller-supplied slot -- masking ``& 0x3FF``, skipping ``1023``,
bounded at 84, every constant this module already pins.

Membership consumption, same image, same constants. ``0x84a8ac30`` walks the
entry list, increments a counter while the play index is not ``1023``, and
stops at 84. ``0x84a8bd20`` takes an index in r5, refuses ``>= 84``, loads
``halfword[base + index*2]``, masks 10 bits, and returns null on ``1023``.
Callers at ``0x84a14ce8``, ``0x84a47448``, ``0x84a2e8e8`` and ``0x84a8fe9c``
compare that count to 0 and skip the get-nth loop when it is empty. That is
static proof an emptied formation cannot yield a stored play. It is not a
runtime witness of which formation the CPU picks next.

The **fourth** tag, ``Y == 3``, is not written by the audible assign loop, but
it is a first-class lookup key. ``0x84a850f0`` walks tagged slots with a
counter that runs 0, 1, 2, 3 (``cmpwi r30, 4`` at ``0x84a851ec``) and calls
find-by-slot for each; it special-cases an incoming argument of 3 at
``0x84a851ac``. That collector is reached from an in-game tick, not only from
the audible writer. What it does **not** prove is that those four plays are
what the CPU calls on 3rd-and-long: that collector has no down or yards-to-go
consumer. Down and yards-to-go *are* pinned elsewhere. Practice Situation
Settings and the in-game object share the same layout on global
``0x84F3F8F8`` / object ``+0x254`` (down) and ``+0x25C`` (yards-to-go). The
name table at ``0x820E57C8`` is Kickoff, First, Second, Third, Fourth, PAT,
Safety Kick, so 3 is Third Down. In-game ``0x848d9470`` compares ``+0x254`` to
1..5 (``cmpwi r11, 3`` at ``0x848d96e4``); its helper ``0x84809898`` is a
type-id match, not a play picker. ``0x84a472d0`` is play-type UI (obj+4
walks ``0x84e4d810``); ``0x8486ce88`` picks a play from situation word0 /
``+0x2BC`` (a tab, not down). Eligibility at ``0x8485e810`` reads on-field
``+0x34`` (the map role) and ANDs a word-table mask with a personnel-table
cell; that is not a 3rd-and-long picker. ``0x84b694a8`` passes down and
yards-to-go into a vtable query and stores 1 or 2 to situation ``+8`` —
not a play. ``0x8499e3e8`` is a script leaf (compact ``+0x18`` compared to
115, not down) and is not a play picker. A tagged-play census also argues against
treating the four tags as the 3rd-and-long call set: ``O-SinglebackAce`` / Ace
tags four runs, Ace Flip tags four play-action passes, ``O-Shotgun`` empty/open
Gun tags include 90 TE Stop, and that book's base Gun tags are four runs.
The tag is preserved and movable.  A caution for whoever reads this next: the glyph tokens
``|SQUARE|``/``|CROSS|``/``|CIRCLE|`` really are in the image, but *nothing
builds their addresses* -- they resolve by name through text substitution.
String proximity is not a code path; find field access by scanning for the
instruction.  This writer therefore edits the tags only in ways that keep the
proved ``min(4, plays)`` rule exactly: a tag may be moved onto another play in
the same formation, or carried onto one when its play is removed. Emptying a
formation sheds every tag because ``min(4, 0)`` is 0; the record trailer is
left untouched. The executable's count/get-nth consumers then return 0/null
for that record (static).

**That static fact was never a safety proof, and a runtime report says the
opposite.** Community reporter Urianus, on alpha.70, emptied the formations
without a TE in ``O-ManBlock`` and watched the CPU line up personnel packages
that book does not contain (00, 10, 01, 12, 11) and one the game does not ship
at all (02), for plays that are not in the book. His reading: it happens
whenever the director selects an emptied record; the untouched books behave
normally. Plays are not bound to formations -- he moved an offensive play into
a defensive book and it ran -- so a record that returns nothing does not make
the director skip it, it makes the director call something the book never
listed. Emptying a formation is therefore an edit that changes in-game
behaviour in a way this project cannot yet predict, and the panel says so
before it stages one. A second runtime report (2026-08-15, Xenia debug log)
went further: emptying a user book's base packages -- every 20 and 10
formation in USER-o -- left the game unable to boot at all, spinning in the
display retrain loop and exiting. Emptied records are therefore treated as
behaviour-changing and possibly boot-breaking, never as a silence the game
skips. Emptying *every* populated record in a book is refused
outright: that leaves the director nothing at all to select.

A tag may never be duplicated or given a value the retail books never use.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from mod_editor.apf_studio.backend import ensure_tools_importable


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402
import playbook_inventory  # type: ignore  # noqa: E402


PROVIDER_KIND = "splb_book_membership"
REPORT_SCHEMA = "apf2k8_splb_book_membership/v1"
PAYLOAD_SCHEMA = "apf2k8_splb_book_membership_replacement/v1"

RECORD_BASE = 0x0070
RECORD_STRIDE = 176
RECORD_COUNT = 176
ENTRY_BYTES = 168
ENTRY_CAPACITY = ENTRY_BYTES // 2          # 84
TRAILER_OFFSET = 0xA8
TRAILER_WORD_B_DELTA = 4
BOOK_CATEGORY_MASK_OFFSET = 0x7E04
CATEGORY_COUNT = 28
MASTER_FORMATION_INDEX_MAX = 162
ARRAY_END = RECORD_BASE + RECORD_STRIDE * RECORD_COUNT   # 0x7970
RESOURCE_SIZE = 32_288
FILLER = 0x13FF
PLAY_MASK = 0x3FF
UNTAGGED_Y = 4
NEUTRAL_X = 2

#: The order retail spends tagged slots as a formation gains plays: the two
#: one-play formations carry only 1, the two two-play formations carry 0 and 1,
#: the four three-play formations carry 0, 1 and 2, and the other 201 carry all
#: four.  Used only to pick a slot the user has not picked; never to relabel one.
TAG_PRIORITY = (1, 0, 2, 3)
MAX_TAGS = len(TAG_PRIORITY)

#: Decompressed PE (``tools/xex_extract_pe.cpp``), image base ``0x82000000``,
#: SHA-256 ``cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf``.
#: File offset = VA − image base. Words are big-endian PowerPC.
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
APF_PE_IMAGE_BASE = 0x82000000
STATIC_CONSUMER_WORDS: Mapping[int, int] = {
    0x84864C78: 0x538A54EA,  # rlwimi r10, r28, 10, 19, 21  (audible Y write)
    0x84A8AA80: 0x7D8802A6,  # find-by-slot mflr
    0x84A8AAA8: 0x552705BE,  # clrlwi r7, r9, 22
    0x84A8AAAC: 0x2B0703FF,  # cmplwi r7, 1023
    0x84A8AAC8: 0x2F0B0054,  # cmpwi r11, 84
    0x84A8AC30: 0x7D8802A6,  # count-plays mflr
    0x84A8AC54: 0xA12B0000,  # lhz r9, 0(r11)
    0x84A8AC58: 0x552905BE,  # clrlwi r9, r9, 22
    0x84A8AC5C: 0x2B0903FF,  # cmplwi r9, 1023
    0x84A8AC64: 0x38630001,  # addi r3, r3, 1
    0x84A8AC6C: 0x2F030054,  # cmpwi r3, 84
    0x84A8BD20: 0x7D8802A6,  # get-nth mflr
    0x84A8BD34: 0x2F050054,  # cmpwi r5, 84
    0x84A8BD44: 0x54AB083C,  # slwi r11, r5, 1
    0x84A8BD48: 0x7D6B1A2E,  # lhzx r11, r11, r3
    0x84A8BD4C: 0x556B05BE,  # clrlwi r11, r11, 22
    0x84A8BD50: 0x2B0B03FF,  # cmplwi r11, 1023
    0x84A8BD7C: 0x38600000,  # li r3, 0  (empty / OOB)
    0x84A19F04: 0x896B0011,  # lbz r11, 17(r11)  package map +0x11
    0x8485E7E0: 0x997F0034,  # stb r11, 52(r31)  map role → on-field +0x34
    0x8485E7E4: 0x997F0035,  # stb r11, 53(r31)  mirror +0x35
    0x84A9AE68: 0x3D608210,  # lis r11, 0x8210  role→roster byte table
    0x84A9AE6C: 0x396BC320,  # addi r11, r11, -15584  → 0x820FC320
    0x84A9AE70: 0x7C6B18AE,  # lbzx r3, r11, r3
    0x8489E6D4: 0x897F0034,  # lbz r11, 52(r31)  read role into table
    0x8489E6E0: 0x481FC789,  # bl 0x84a9ae68
    0x8489E6FC: 0x2F0B0003,  # cmpwi r11, 3  roster WR
    0x8489E704: 0x2F0B0007,  # cmpwi r11, 7  roster HB
    0x8489E70C: 0x2F0B0009,  # cmpwi r11, 9  roster TE
    0x84A850F0: 0x7D8802A6,  # four-tag collector mflr
    0x84A851AC: 0x2F1E0003,  # cmpwi r30, 3  (Y==3 special case)
    0x84A851EC: 0x2F1E0004,  # cmpwi r30, 4  (loop Y=0..3)
    0x848605AC: 0x3BB90005,  # addi r29, r25, 5  map base (formation+0x0C+5)
    0x848605B4: 0x7D5DF0AE,  # lbzx r10, r29, r30  map[slot]
    0x848605C0: 0x554506FE,  # clrlwi r5, r10, 27  role id
    0x848605D8: 0x2F1F002C,  # cmpwi r31, 44  (11 slots × 4)
    0x84A37598: 0x3D6084F4,  # lis r11, 0x84F4  situation-menu global
    0x84A375A0: 0x806B0254,  # lwz r3, 596(r11)  down getter
    0x848D96E0: 0x816B0254,  # lwz r11, 596(r11)  in-game down
    0x848D96E4: 0x2F0B0003,  # cmpwi r11, 3  Third Down
    0x8485BD38: 0x816400A8,  # lwz r11, 168(r4)  trailer word A
    0x8485BD40: 0x556B9D76,  # rlwinm category extract
    0x8485BD48: 0x386B0044,  # addi r3, r11, 68  MASTER category base
    0x84860658: 0x816300A8,  # builder lwz trailer
    0x8486065C: 0x556B9D76,  # builder category extract
    0x84860664: 0x896B0048,  # lbz category +4
    0x84860674: 0x987F0035,  # stb r3, 53(r31)  on-field +0x35
    0x84A9ACC8: 0x1D63000B,  # mulli r11, r3, 11  personnel table
    0x84A8B8D4: 0x897D00A8,  # lbz formation index from trailer
    0x84A8B8DC: 0x1D6B00B8,  # mulli 184  FORMATION_SIZE
    0x84A472F0: 0x831D0004,  # lwz r24, 4(r29)  play-type UI page, not down
    0x84A47328: 0x3B2BD810,  # addi r25 → 0x84E4D810 Inside Run table
    0x8486CEB0: 0x814B0000,  # lwz r10, 0(r11)  situation word0
    0x8486CEB4: 0x2F0A0002,  # cmpwi r10, 2  (not down)
    0x8486CEDC: 0x814B01F8,  # lwz r10, 504(r11)  situation +0x1F8 play-type filter
    0x84A23BF4: 0x914B01F8,  # stw r10, 504(r11)  UI writes +0x1F8
    0x84A89EE0: 0x2F0B00B0,  # cmpwi r11, 176  SPLB record reverse-lookup
    0x84869A6C: 0x2F180008,  # cmpwi r24, 8  fetch play-type nibble, not down
    0x84869A78: 0x556B273E,  # srwi r11, r11, 28  play+4 type nibble
    0x848699E8: 0x83A30020,  # lwz r29, 32(r3)  fetch book from playcall+0x20
    0x8485E7F0: 0x48378648,  # assigner tail b (no fall-through into AND)
    0x8485E7F8: 0x7D8802A6,  # eligibility AND fn mflr (0 bl; pdata-only)
    0x8466B998: 0x3D40852B,  # lis r10, 0x852B  DRCT type-list insert
    0x8466B9A4: 0x396BB830,  # addi r11 → 0x84D1B830 DRCT type object
    0x8466B96C: 0x3D20ED58,  # lis r9, 0xED58  DRCT type-hash ctor
    0x8466B978: 0x61296383,  # ori r9, r9, 0x6383
    0x8466AF70: 0x7D8802A6,  # dir_ingame.iff load mflr
    0x8466AF94: 0x388BB7D0,  # addi r4 → 0x84D1B7D0 DRCT registry table
    0x8466AFC0: 0x48022AB1,  # bl 0x8468DA70 resource load
    0x8466A818: 0x38E30018,  # addi r7, r3, 24  DRCT relocator +0x18
    0x8466A97C: 0x2F060364,  # cmpwi r6, 868  217 slots × 4
    0x8466A984: 0xA1630006,  # lhz r11, 6(r3)  instruction count
    0x8466A994: 0x39630020,  # addi r11, r3, 32  instruction directory
    0x8466B8F4: 0x4BFFEF25,  # bl 0x8466A818 from vtable[0]
    0x8466B8FC: 0x4BFFF1E5,  # bl 0x8466AAE0 after reloc; no insn interpret
    0x8466AF48: 0x81630010,  # lwz +0x10 bounds check; not a type mapper
    0x84B162D8: 0x38630020,  # addi r3,32 embedded C++ object, not insn dir
    0x84A87B4C: 0x554A273E,  # srwi 28 play-type nibble, not tag 6
    0x84BDFB28: 0x2F0B0059,  # cmpwi 'Y'; not TLV
    0x84C38218: 0x39200064,  # li 100 in stack/float fn; not field 0x0100
    0x8466B660: 0x2F090100,  # cmpwi r9,256 map count; not field 0x0100
    0x8466C7F4: 0x394B779C,  # packed LE f32 cursor 0x84F1779C; not 0B-group
    0x84671838: 0x80840020,  # lwz r4,32(r4) then vt[2]; not registrar
    0x848BB1B4: 0x2F0B0002,  # RTTI class 2 vs 11; not tag 0x0B
    0x84842F54: 0x2B0B0003,  # RTTI class 3..12 via +0x14/+4; not TLV
    0x8476CA84: 0x396313D9,  # 10×5 occupancy at object +0x13D9
    0x8492BB04: 0x396518D5,  # 5-byte window sum + floats; not 0B parser
    0x84B0A4F0: 0x396B65A8,  # addi → 0x84EE65A8 stride-12 property table
    0x84B0A4FC: 0x2B090035,  # cmplwi id, 0x35
    0x849E77E0: 0x2B03FFFF,  # 12-byte copy 0xffff sentinel; not 0B
    0x847E2840: 0x2B0B0004,  # class-id 3/5/6/7/4 via +4; not leftover leads
    0x84ABB5B4: 0x99630004,  # 5-byte memcpy stb +4; no tag check
    0x84A9D7B8: 0x39260040,  # stride-32 float copy; not B73BD0
    0x84BE2C08: 0x80EA18F4,  # ASCII/scanf 0..11; not leftover leads
    0x848777C0: 0xC17E0000,  # lfs then one-shot +0x1C; not B73BD0
    0x84B93B1C: 0x89230001,  # codec 5-byte header lbz +1; no 0x0B check
    0x849277F8: 0x398C780C,  # byte JT table 0x8492780C; cases 4/11 gfx
    0x84C4C480: 0x7D8802A6,  # endian-width memcpy mflr; not type-4
    0x84C4C4C0: 0x2B0B0004,  # cmplwi r11, 4  copy width, not tag 0x04
    0x84C4C500: 0x7D605C2C,  # lwbrx of width-4 payload; not TLV walker
    0x84BA2538: 0x1D6A000C,  # mulli 12 of packed field; table in r4
    0x84BA253C: 0x7D6B2214,  # add r11, r11, r4  stride-12; not bctrl
    0x846C2094: 0x2B0B0004,  # cmplwi +0x62, 4  frontend state
    0x846C209C: 0x39600005,  # li 5 stored back; not float-group size
    0x8466C8F8: 0x2B09000C,  # cmplwi type, 12  expression VM
    0x8466C918: 0x4E800420,  # bctr  table 0x8466C91C
    0x8466CCDC: 0x7CCA28AE,  # case 11 lbzx 1 byte; not 0B group
    0x844DD260: 0x8466C890,  # mixed descriptor slot for the VM
    0x8477F980: 0x2B0B000C,  # cmplwi UI byte, 12; not leftover max
    0x84A37858: 0x812B0254,  # lwz down +0x254
    0x84A3785C: 0x814B025C,  # lwz ytg +0x25C
    0x84A37868: 0x2F0A0064,  # cmpwi ytg, 100; wrap, not picker
    0x848864F4: 0x816BF8F8,  # lwz situation word0
    0x848864F8: 0x2F0B0004,  # cmpwi word0, 4; not Fourth Down
    0x84886568: 0x2F0B000B,  # playcall+0x38 == 11
    0x84A5EB2C: 0x2F1E0004,  # type 4 in 24-wide table walker
    0x84A5EB38: 0x2B0A0018,  # cmplwi 24
    0x8475B7C0: 0x3D6084D5,  # lis tween object 0x84D58C70
    0x8475B7D8: 0xC01F0258,  # lfs +0x258; float, not integer ytg
    0x84A23BDC: 0x814B01F8,  # lwz play-type filter +0x1F8
    0x84A23BF4: 0x914B01F8,  # stw +0x1F8; UI clamp 0..7
    0x844E8568: 0x8486CE88,  # picker .pdata row, not bctrl slot
    0x849D36E0: 0x906B01F8,  # stw r3, situation +0x1F8; packed setter
    0x848631D8: 0x806B01F8,  # lwz r3, +0x1F8; Offensive Play calling getter
    0x84A2CCEC: 0x814B01F8,  # lwz +0x1F8; UI tab/filter gate, not CPU long
    0x84A2CCFC: 0x2F0B0003,  # cmpwi tab, 3
    0x849615A4: 0x397E0005,  # addi r11, r30, 5; occupancy index, not leftover
    0x849E3A94: 0x2F1A000B,  # cmpwi r26, 11; bit-pack, not leftover tag
    0x84814DCC: 0x2F0B0004,  # picker-neighbor cmpwi situation word0, 4
    0x84814E08: 0x396B0005,  # addi r11, 5; srawi-3 index math, not leftover
    0x84869EA0: 0x39230005,  # addi r9, r3, 5; 4-wide fill remainder
    0x84A9ADCC: 0x3B830005,  # addi r28, r3, 5; 11-slot lbzx, not TLV
    0x84A212D8: 0x2F0A0007,  # cmpwi index, 7; D&D label formatter
    0x84A212E8: 0x396B46C8,  # addi to name table 0x84E446C8
    0x84E446D8: 0x845FD8B4,  # ptr to "Third and Long"
    0x849ECD4C: 0x2B0B0009,  # cmplwi 9; object+0x34 JT, not leftover
    0x847D758C: 0x816B003C,  # lwz playcall+0x3C
    0x847D7590: 0x2F0B0003,  # cmpwi 3; not down
    0x8466C8DC: 0x90BF0008,  # stw r5, expr cursor+8
    0x849A3B68: 0x2F0A0008,  # cmpwi script +0x14, 8; not ytg
    0x84B68CD8: 0x8063025C,  # packed get_ytg; 0 bl, 0 PE ptrs
    0x84B68CC8: 0x80630254,  # packed object get_down; 0 PE ptrs
    0x84AD03B8: 0x814B025C,  # copy-out lwz ytg
    0x84AD0434: 0x812B0254,  # copy-out lwz down
    0x844F72B0: 0x84AD0348,  # copy-out .pdata slot
    0x84879BC0: 0x8163025C,  # ytg bit 1; not D&D index
    0x84AD9F40: 0x3D6084EB,  # packed blob-row indexer lis
    0x84AD9F48: 0x396B02D0,  # addi to 0x84EB02D0; not get_down row
    0x84EB02D4: 0x84AD8B90,  # row-0 getter; not get_down
    0x848EE750: 0x3D400B00,  # lis 0x0B00 bitmask, not leftover tag
    0x848EE790: 0x3880000B,  # li r4, 11
    0x84B64CAC: 0x3D60844C,  # lis UTF-8 extra-byte table
    0x84B64CD8: 0x2B1E0005,  # cmplwi extra, 5; UTF-8 max, not type-4
    0x8466AAE0: 0x7D8802A6,  # post-reloc fixed-table walk mflr
    0x8466ABC4: 0x81430018,  # lwz r10, 24(r3)  fixed-child indexer +0x18
    0x8466AF28: 0x81630014,  # lwz r11, 20(r3)  string indexer +0x14
    0x8466AF60: 0x8163001C,  # lwz r11, 28(r3)  auxiliary indexer +0x1C
    0x8466AC38: 0x7D8802A6,  # fixed-record consumer mflr
    0x8466AC9C: 0x81440018,  # lwz r10, 24(r4)  consumer uses +0x18 not +0x20
    0x8493D9AC: 0x906A0000,  # stw r3, 0(r10) register playcall object
    0x8493E180: 0x90830020,  # stw r4, 32(r3) packed playcall+0x20 setter
    0x8470C2C4: 0x806B2780,  # lwz r3, playcall global; then bl picker
    0x847163D4: 0x38600002,  # li r3, 2  only mode-2 entry into jump table
    0x847124A8: 0x7C7E1B78,  # mr r30, r3  mode wrapper (small int, not ptr)
    0x84A254E0: 0x807D2780,  # lwz r3, playcall global; UI picker path
    0x84892DF8: 0x807F2780,  # lwz r3, playcall global; playcall-UI picker
    0x84A139F4: 0x906BCDE0,  # stw r3, 0x8520CDE0  find-by-slot book singleton
    0x84A283E0: 0x812B001C,  # lwz r9, 28(playcall)  UI copies +0x1C
    0x84A283E8: 0x816B0020,  # lwz r11, 32(playcall)  UI copies +0x20
    0x84887E2C: 0x83CB0000,  # lwz r30, playcall object
    0x84887EA8: 0x907F0020,  # stw r3, 32(shadow 0x8516C908); bitmask not book
    0x847C6DA8: 0x7D8802A6,  # type-object init mflr
    0x847C6DF8: 0x907F0020,  # stw r3, 32(0x850F1218) live MASTER copy
    0x849FD6A8: 0x3D6084F4,  # lis live-MASTER getter → 0x84F3F7D8
    0x849FD6B0: 0x806B002C,  # lwz r3, 44(slot)  MASTER pointer
    0x84AD00A0: 0x93BF0000,  # stw type-A into playcall slot+0
    0x8486CD80: 0x7D8802A6,  # book-resolve helper mflr (UI-only)
    0x84A89E50: 0x386B0244,  # addi r3, r11, 580  MASTER +0x244
    0x849FD6C8: 0x3D6084F4,  # lis live-MASTER setter → 0x84F3F7D8
    0x849FD6D0: 0x906B002C,  # stw r3, 44(slot)
    0x849FCF60: 0x3D60851E,  # lis SPLB RAM indexer → 0x851D9660
    0x849FCF64: 0x1D437E20,  # mulli r10, r3, 32288
    0x849D81EC: 0x2F0B0004,  # cmpwi word0, 4  SPLB-select gate, not down
    0x84D01B14: 0x396A81D0,  # addi → 0x849D81D0 stored at object+0x2C94
    0x84D01B18: 0x917F2C94,  # stw r11, 0x2C94(r31)
    0x849D81B0: 0x2F0B0004,  # packed word0==4 thunk
    0x84EB0DE4: 0x84AD92E0,  # get_down pointer in property table
    0x847463C8: 0xA0630168,  # packed lhz +0x168 sibling; 0 bl
    0x8484D488: 0x7D8802A6,  # stvx presentation; not dca40
    0x84878594: 0x39630020,  # addi r11, r3, 32  vec compare, not insn dir
    0x849C9C90: 0x7D8802A6,  # property-get-by-id mflr
    0x849C9CAC: 0x2F1FFFFF,  # cmpwi r4-id, -1
    0x84880924: 0x814B0020,  # lwz +0x20 flag (cmpwi 1), not insn dir
    0x84880928: 0x2F0A0001,  # cmpwi r10, 1
    0x8466A994: 0x39630020,  # addi r11, r3, 32  reloc inline insn dir
    0x84AB2010: 0xA0630006,  # packed lhz r3, 6(r3) insn count; 0 bl
    0x8466BA40: 0x3D608200,  # lis in DRCT vt[2] unlink; not interpreter
    0x8466BD58: 0x8BCB0000,  # lbz r30, 0(r11) generic byte-stream
    0x84BCD78C: 0x89630004,  # lbz +4 string classifier; 0 bl
    0x84867958: 0x83DC0020,  # lwz r30, 32(r28)  second book reader
    0x84A23EA0: 0x39400003,  # li r10, 3  playcall tab +0x2BC, not down
    0x84AD92E0: 0x80630254,  # lwz r3, 0x254(r3)  situation get_down
    0x8485E810: 0x887D0034,  # lbz r3, 52(r29)  eligibility from +0x34
    0x8485E828: 0x7C6BE038,  # and r11, r3, r28  map-mask AND personnel cell
    0x84862568: 0x887E0034,  # lbz r3, 52(r30)  live 11-slot eligibility +0x34
    0x84862580: 0x7C6BE838,  # and r11, r3, r29  live 11-slot AND
    0x84A9AE90: 0x3D608210,  # lis  word table 0x820FC380
    0x84A9AE98: 0x396BC380,  # addi → 0x820FC380
    0x84A9ACA8: 0x1D63000B,  # mulli 11  personnel cell (eligibility)
    0x84B69550: 0x2F030000,  # cmpwi r3, 0  vtable+8 query, not a picker
    0x84B69560: 0x914B0008,  # stw r10, 8(r11)  stores 1 or 2
    0x8499E3E8: 0x81030018,  # lwz r8, 24(r3)  script leaf +0x18
    0x8499E3EC: 0x2F080073,  # cmpwi r8, 115  (not a down)
    0x846302F0: 0x886B0034,  # lbz r3, 52(r11)  first .text fn +0x34 (not a VM opcode)
    0x846302F4: 0x892B0035,  # lbz r9, 53(r11)  first .text fn +0x35
    0x844DBE00: 0x846302D8,  # .pdata[0] start == first .text function
    # Trailer consumption chain (trailer-replace feature): the lineup resolver
    # asks the book for a record matching a personnel row; the book walk tests
    # the category mask at book+0x7E04 and each record's word B; a miss walks
    # the row ladder at 0x820B9080 (clamped 0..10 on offense) and re-asks, so
    # a book lacking the requested package silently drops to a lighter row.
    0x84860730: 0x7D8802A6,  # lineup personnel resolver mflr
    0x8486076C: 0x4822ACCD,  # bl 0x84a8b438  book-row search
    0x84860788: 0x3BAB9080,  # addi r29 → ladder 0x820B9080
    0x84860790: 0x817E0000,  # lwz ladder offset word
    0x848607B8: 0x3880000A,  # li r4, 0xa  offense row clamp
    0x84A8B438: 0x7D8802A6,  # book-row search mflr
    0x84A8B45C: 0x89630004,  # lbz first category +4  personnel row
    0x84A8B46C: 0x83FE7E0C,  # lwz MASTER pointer book+0x7E0C
    0x84A89680: 0x7CAB2E70,  # srawi  mask bit walk
    0x84A896AC: 0x81470000,  # lwz mask word
}

#: outer entry -> book name, as shipped. Fifteen resources; four carry no name.
STOCK_BOOKS: Mapping[int, str] = {
    130: "O-ManBlock",
    134: "X-43Cover2",
    259: "O-TwoBack",
    293: "",
    369: "O-SinglebackAce",
    618: "X-34Base",
    656: "",
    767: "O-Singleback3WR",
    891: "O-WestCoast",
    943: "O-ZoneBlock",
    957: "X-43Blitz",
    1037: "",
    1405: "X-34ZoneBlitz",
    1411: "O-Shotgun",
    1439: "",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def entry_selector(outer_index: int, record_index: int, play_index: int) -> str:
    return f"splb:{outer_index}:r{record_index}:p{play_index}"


def tag_selector(
    outer_index: int, record_index: int, from_play: int, to_play: int
) -> str:
    return f"splb:{outer_index}:r{record_index}:tag:{from_play}->{to_play}"


def required_tag_count(entry_count: int) -> int:
    """How many tagged slots a formation with this many plays carries in retail."""

    return min(MAX_TAGS, entry_count)


#: Exact suffix that pairs a formation with its flipped twin. "Flip Pair" in
#: the middle of a name is not this suffix — Weak I Jokers Flip Pair is not
#: the partner of Weak I Jokers. Ace / Ace Flip is.
FLIP_SUFFIX = " Flip"


def flip_partner_name(name: str) -> str | None:
    """The other name in an exact ``' Flip'`` pair, or None if ``name`` is empty."""

    cleaned = name.strip()
    if not cleaned:
        return None
    if cleaned.endswith(FLIP_SUFFIX):
        return cleaned[: -len(FLIP_SUFFIX)]
    return cleaned + FLIP_SUFFIX


def find_flip_partner_record(
    book: "SplbBook",
    record: "SplbRecord",
    names: Mapping[int, str],
) -> "SplbRecord | None":
    """The same-book record whose formation name is the exact Flip twin."""

    mine = names.get(record.formation_index, "").strip()
    wanted = flip_partner_name(mine)
    if wanted is None:
        return None
    for other in book.records:
        if other.record_index == record.record_index:
            continue
        if names.get(other.formation_index, "").strip() == wanted:
            return other
    return None


@dataclass(frozen=True, slots=True)
class SplbEntry:
    x: int
    y: int
    play_index: int

    @property
    def tagged(self) -> bool:
        return self.y != UNTAGGED_Y

    def encode(self) -> int:
        return (self.x << 13) | (self.y << 10) | self.play_index


@dataclass(frozen=True, slots=True)
class SplbRecord:
    record_index: int
    formation_index: int
    category_index: int
    entries: tuple[SplbEntry, ...]
    trailer: bytes

    @property
    def populated(self) -> bool:
        return bool(self.entries)


@dataclass(frozen=True, slots=True)
class SplbBook:
    outer_index: int
    name: str
    body: bytes
    records: tuple[SplbRecord, ...]


@dataclass(frozen=True, slots=True)
class MembershipChange:
    """Add or remove one MASTER play from one record of one book.

    ``tag_heir`` answers the only question a removal can raise: when the play
    leaving holds a tagged slot the formation still needs, name the play in the
    same record that carries the slot on.  Leaving it ``None`` on such a removal
    is refused, because the writer will not pick a successor for the user.
    """

    outer_index: int
    record_index: int
    play_index: int
    member: bool
    tag_heir: int | None = None

    @property
    def selector(self) -> str:
        return entry_selector(self.outer_index, self.record_index, self.play_index)


@dataclass(frozen=True, slots=True)
class TagMove:
    """Move one tagged slot onto another play already in the same record.

    The two plays exchange their ``Y`` values, so the count of tagged slots is
    unchanged whether or not the destination already held one.
    """

    outer_index: int
    record_index: int
    from_play: int
    to_play: int

    @property
    def selector(self) -> str:
        return tag_selector(
            self.outer_index, self.record_index, self.from_play, self.to_play
        )


@dataclass(frozen=True, slots=True)
class TrailerReplace:
    """Repoint one record's trailer at another MASTER formation and package.

    Word A carries the formation index (bits 31..24) and the personnel
    category (bits 23..17); the director resolves a requested personnel row
    through the book's category mask at +0x7E04 and the record's membership
    bitmask (word B), so a retarget also ORs the category bit into both.
    The three unproved 3-bit situation fields and the low byte are preserved
    byte-exact.
    """

    outer_index: int
    record_index: int
    formation_index: int
    category_index: int

    def __post_init__(self) -> None:
        _bounded_int(self.outer_index, "Playbook entry", minimum=0, maximum=1_542)
        _bounded_int(
            self.record_index, "Formation record", minimum=0,
            maximum=RECORD_COUNT - 1,
        )
        _bounded_int(
            self.formation_index, "MASTER formation", minimum=0,
            maximum=MASTER_FORMATION_INDEX_MAX,
        )
        _bounded_int(
            self.category_index, "Personnel package", minimum=0,
            maximum=CATEGORY_COUNT - 1,
        )

    @property
    def selector(self) -> str:
        return trailer_selector(self.outer_index, self.record_index)


def trailer_selector(outer_index: int, record_index: int) -> str:
    return f"splb:{outer_index}:r{record_index}:trailer"


@dataclass(frozen=True, slots=True)
class _Request:
    outer_index: int
    memberships: tuple[MembershipChange, ...]
    moves: tuple[TagMove, ...]
    trailers: tuple[TrailerReplace, ...] = ()

    @property
    def record_indices(self) -> set[int]:
        return (
            {change.record_index for change in self.memberships}
            | {move.record_index for move in self.moves}
            | {trailer.record_index for trailer in self.trailers}
        )


def _bounded_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number")
    if not minimum <= value <= maximum:
        raise ValidationError(f"{label} is outside {minimum}..{maximum}")
    return int(value)


def change_metadata(change: MembershipChange | TagMove) -> dict[str, object]:
    """The small target coordinates a project may carry for one staged change."""

    if isinstance(change, MembershipChange):
        return {
            "change_kind": "membership",
            "outer_index": change.outer_index,
            "record_index": change.record_index,
            "play_index": change.play_index,
            "member": change.member,
            "tag_heir": change.tag_heir,
        }
    if isinstance(change, TagMove):
        return {
            "change_kind": "tag_move",
            "outer_index": change.outer_index,
            "record_index": change.record_index,
            "from_play": change.from_play,
            "to_play": change.to_play,
        }
    if isinstance(change, TrailerReplace):
        return {
            "change_kind": "trailer_replace",
            "outer_index": change.outer_index,
            "record_index": change.record_index,
            "formation_index": change.formation_index,
            "category_index": change.category_index,
        }
    raise ValidationError("A stock-playbook change is malformed")


def change_from_mapping(value: Mapping[str, object]) -> MembershipChange | TagMove:
    """Rebuild one staged change from project metadata or a stored payload."""

    kind = value.get("change_kind")
    if kind == "membership":
        if set(value) != {
            "change_kind",
            "outer_index",
            "record_index",
            "play_index",
            "member",
            "tag_heir",
        }:
            raise ValidationError(
                "A stock-playbook membership change has unsupported fields"
            )
        member = value.get("member")
        if type(member) is not bool:
            raise ValidationError("A stock-playbook membership flag must be a boolean")
        heir = value.get("tag_heir")
        if heir is not None:
            heir = _bounded_int(heir, "Tagged-slot heir play", minimum=0, maximum=PLAY_MASK)
        return MembershipChange(
            outer_index=_bounded_int(
                value.get("outer_index"), "Playbook entry", minimum=0, maximum=1_542
            ),
            record_index=_bounded_int(
                value.get("record_index"),
                "Formation record",
                minimum=0,
                maximum=RECORD_COUNT - 1,
            ),
            play_index=_bounded_int(
                value.get("play_index"), "MASTER play", minimum=0, maximum=PLAY_MASK
            ),
            member=bool(member),
            tag_heir=heir,
        )
    if kind == "tag_move":
        if set(value) != {
            "change_kind",
            "outer_index",
            "record_index",
            "from_play",
            "to_play",
        }:
            raise ValidationError(
                "A stock-playbook tagged-slot move has unsupported fields"
            )
        return TagMove(
            outer_index=_bounded_int(
                value.get("outer_index"), "Playbook entry", minimum=0, maximum=1_542
            ),
            record_index=_bounded_int(
                value.get("record_index"),
                "Formation record",
                minimum=0,
                maximum=RECORD_COUNT - 1,
            ),
            from_play=_bounded_int(
                value.get("from_play"), "Tagged-slot source play", minimum=0, maximum=PLAY_MASK
            ),
            to_play=_bounded_int(
                value.get("to_play"),
                "Tagged-slot destination play",
                minimum=0,
                maximum=PLAY_MASK,
            ),
        )
    if kind == "trailer_replace":
        if set(value) != {
            "change_kind",
            "outer_index",
            "record_index",
            "formation_index",
            "category_index",
        }:
            raise ValidationError(
                "A stock-playbook trailer replace has unsupported fields"
            )
        return TrailerReplace(
            outer_index=_bounded_int(
                value.get("outer_index"), "Playbook entry", minimum=0, maximum=1_542
            ),
            record_index=_bounded_int(
                value.get("record_index"),
                "Formation record",
                minimum=0,
                maximum=RECORD_COUNT - 1,
            ),
            formation_index=_bounded_int(
                value.get("formation_index"),
                "MASTER formation",
                minimum=0,
                maximum=MASTER_FORMATION_INDEX_MAX,
            ),
            category_index=_bounded_int(
                value.get("category_index"),
                "Personnel package",
                minimum=0,
                maximum=CATEGORY_COUNT - 1,
            ),
        )
    raise ValidationError("A stock-playbook change is malformed")


def encode_membership_payload(change: MembershipChange | TagMove) -> bytes:
    """Encode one staged change as canonical selector-only JSON.

    A project stores *what was asked for*, never a byte of the user's SPLB
    resource: an outer entry, a record, and the play indices involved.
    """

    normalized = change_from_mapping(change_metadata(change))
    return (
        json.dumps(
            {"schema": PAYLOAD_SCHEMA, "change": change_metadata(normalized)},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_membership_payload(
    payload: bytes, target_id: str = "APF playbook membership"
) -> MembershipChange | TagMove:
    """Validate one stored change and prove it still names ``target_id``."""

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(
                    f"APF playbook-membership payload repeats JSON key {key!r}: "
                    f"{target_id}"
                )
            result[key] = value
        return result

    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=no_duplicates)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            f"APF playbook-membership replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "change"}
        or document.get("schema") != PAYLOAD_SCHEMA
        or not isinstance(document.get("change"), dict)
    ):
        raise ValidationError(
            f"APF playbook-membership payload is invalid: {target_id}"
        )
    change = change_from_mapping(document["change"])
    if change.selector != target_id:
        raise ValidationError(
            f"APF playbook-membership payload target changed: {target_id}"
        )
    if encode_membership_payload(change) != payload:
        raise ValidationError(
            f"APF playbook-membership payload is not canonical: {target_id}"
        )
    return change


@dataclass(frozen=True, slots=True)
class CompiledBook:
    outer_index: int
    entry_bytes: bytes
    replacement: bytes
    report: Mapping[str, Any]


def _decode_entries(body: bytes, record_index: int) -> tuple[SplbEntry, ...]:
    base = RECORD_BASE + record_index * RECORD_STRIDE
    entries: list[SplbEntry] = []
    seen_filler = False
    for slot in range(ENTRY_CAPACITY):
        raw = struct.unpack_from(">H", body, base + slot * 2)[0]
        if raw == FILLER:
            seen_filler = True
            continue
        if seen_filler:
            raise ValidationError(
                f"SPLB record {record_index} has an entry after its terminator; "
                "this book does not match the proved layout"
            )
        entries.append(SplbEntry((raw >> 13) & 0x7, (raw >> 10) & 0x7, raw & PLAY_MASK))
    return tuple(entries)


def parse_book(body: bytes, outer_index: int) -> SplbBook:
    """Decode one stock playbook. Refuses anything that is not the proved shape."""

    if len(body) != RESOURCE_SIZE:
        raise ValidationError(
            f"An APF stock playbook is {RESOURCE_SIZE} bytes; this one is {len(body)}"
        )
    if body[0x0C:0x10] != b"BLPS":
        raise ValidationError("This resource is not an APF stock playbook (no BLPS)")
    name = body[0x30:0x68].decode("utf-16-be", errors="ignore").split("\x00")[0]
    records: list[SplbRecord] = []
    for index in range(RECORD_COUNT):
        trailer_at = RECORD_BASE + index * RECORD_STRIDE + TRAILER_OFFSET
        trailer = body[trailer_at : trailer_at + 8]
        word_a = struct.unpack_from(">I", trailer, 0)[0]
        records.append(
            SplbRecord(
                record_index=index,
                formation_index=word_a >> 24,
                category_index=(word_a >> 17) & 0x7F,
                entries=_decode_entries(body, index),
                trailer=trailer,
            )
        )
    return SplbBook(outer_index, name, body, tuple(records))


def read_book(index_path: Path, outer_index: int) -> SplbBook:
    """Read and validate one stock playbook out of the user's own game."""

    if outer_index not in STOCK_BOOKS:
        raise ValidationError(f"Outer entry {outer_index} is not a stock playbook")
    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[outer_index]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            if record.block_count != 1 or record.file_count != 1:
                raise ValidationError("APF stock playbook IFF ownership changed")
            item = record.files[0]
            if item.name != "spb" or item.type_name != "SPLB":
                raise ValidationError("APF stock playbook inner ownership changed")
            part = item.parts[0]
            decoded = apf_inner.decode_block(reader, record, part.block_index, 64 * 1024 * 1024)
            body = decoded[part.offset : part.offset + part.length]
    except ValidationError:
        raise
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open the APF stock playbook: {exc}") from exc
    return parse_book(body, outer_index)


def _normalize(
    changes: Iterable[MembershipChange | TagMove | TrailerReplace],
) -> _Request:
    resolved: dict[tuple[int, int, int], MembershipChange] = {}
    moves: dict[tuple[int, int, int], TagMove] = {}
    trailers: dict[tuple[int, int], TrailerReplace] = {}
    for change in changes:
        if isinstance(change, TrailerReplace):
            key = (change.outer_index, change.record_index)
            if key in trailers and trailers[key] != change:
                raise ValidationError(
                    "One formation record is repointed twice with different "
                    "outcomes in a single request"
                )
            trailers[key] = change
            continue
        if isinstance(change, MembershipChange):
            key = (change.outer_index, change.record_index, change.play_index)
            if key in resolved and resolved[key] != change:
                raise ValidationError(
                    "One stock-playbook slot is asked for twice with different "
                    "outcomes in a single request"
                )
            resolved[key] = change
        elif isinstance(change, TagMove):
            if change.from_play == change.to_play:
                raise ValidationError(
                    "A tagged slot cannot be moved onto the play that already holds it"
                )
            key = (change.outer_index, change.record_index, change.from_play)
            if key in moves and moves[key] != change:
                raise ValidationError(
                    "One tagged slot is moved to two different plays in a single request"
                )
            moves[key] = change
        else:
            raise ValidationError("A stock-playbook change is malformed")
    if not resolved and not moves and not trailers:
        raise ValidationError("No stock-playbook changes were supplied")
    outers = {change.outer_index for change in resolved.values()}
    outers |= {move.outer_index for move in moves.values()}
    outers |= {trailer.outer_index for trailer in trailers.values()}
    if len(outers) != 1:
        raise ValidationError("Compile one stock playbook at a time")
    # A move and a removal naming the same play compose in the fixed order
    # adds -> moves -> removals: the move first travels the tagged slot off
    # (or onto) the play, then the removal phase's heir / tag-count rules
    # decide what the record still owes.  Refusing the pair here punished
    # users for doing exactly what the carry dialog recommends, and the
    # panel's composable preview already accepted it, so Save Project and
    # the panel disagreed.  Unsafe residue is still refused below, with
    # actionable messages, by _check_tag_rule.
    return _Request(
        outers.pop(),
        tuple(resolved[key] for key in sorted(resolved)),
        tuple(moves[key] for key in sorted(moves)),
        tuple(trailers[key] for key in sorted(trailers)),
    )


def tags_of(entries: Iterable[SplbEntry]) -> list[int]:
    return [entry.y for entry in entries if entry.tagged]


def follows_tag_rule(entries: tuple[SplbEntry, ...]) -> bool:
    """Does this record obey the rule every retail record obeys?"""

    tags = tags_of(entries)
    return len(set(tags)) == len(tags) == required_tag_count(len(entries))


def retail_tag_shape(entries: tuple[SplbEntry, ...]) -> bool:
    """Is this record's tag *set* one of the four the retail books actually use?"""

    expected = TAG_PRIORITY[: required_tag_count(len(entries))]
    return sorted(tags_of(entries)) == sorted(expected)


def _next_free_tag(entries: Iterable[SplbEntry]) -> int | None:
    used = set(tags_of(entries))
    return next((tag for tag in TAG_PRIORITY if tag not in used), None)


def _check_tag_rule(
    record_index: int, before: tuple[SplbEntry, ...], after: list[SplbEntry]
) -> None:
    """Refuse anything that would put this record outside the proved rule.

    Records that already broke the rule before the edit -- nothing retail does,
    but a hand-built resource might -- are only held to not getting worse.
    """

    for entry in after:
        if entry.y > UNTAGGED_Y:
            raise ValidationError(
                f"Record {record_index} would give play {entry.play_index} Y={entry.y}; "
                f"only 0-3 (tagged) and {UNTAGGED_Y} (untagged) occur in the retail books"
            )
    tags = tags_of(after)
    if len(set(tags)) != len(tags):
        raise ValidationError(
            f"Record {record_index} would carry one tagged slot twice; each of 0-3 "
            "appears at most once in every retail record"
        )
    required = required_tag_count(len(after))
    if follows_tag_rule(before):
        if len(tags) != required:
            raise ValidationError(
                f"Record {record_index} would carry {len(tags)} tagged slots for "
                f"{len(after)} plays, and every retail formation carries {required}. "
                "Move the slot to another play in this formation, or name a play to "
                "carry it, instead of dropping it."
            )
    elif len(tags) < min(len(tags_of(before)), required):
        raise ValidationError(
            f"Record {record_index} already broke the tagged-slot rule and this edit "
            "would drop yet another slot"
        )
    if after and 1 in tags_of(before) and 1 not in tags:
        raise ValidationError(
            f"Record {record_index} would lose its slot-1 play, and every populated "
            "retail record has exactly one. Carry slot 1 onto another play in this "
            "formation instead."
        )


def apply_record_changes(
    book: SplbBook,
    record: SplbRecord,
    memberships: Iterable[MembershipChange] = (),
    moves: Iterable[TagMove] = (),
) -> tuple[SplbEntry, ...]:
    """Return one record's entries after the requested edits, or raise.

    Adds land first, then tagged-slot moves, then removals, so a play added in
    the same request can be named as the heir of a slot the request removes.
    """

    play_count = 586
    before = record.entries
    entries = list(before)

    def index_of(play: int) -> int | None:
        return next(
            (slot for slot, entry in enumerate(entries) if entry.play_index == play),
            None,
        )

    for change in memberships:
        if not 0 <= change.play_index < play_count:
            raise ValidationError(
                f"Play {change.play_index} is outside MASTER's {play_count} plays"
            )
        if not change.member or index_of(change.play_index) is not None:
            continue
        if len(entries) >= ENTRY_CAPACITY:
            raise ValidationError(
                f"Record {record.record_index} already holds the maximum "
                f"{ENTRY_CAPACITY} plays"
            )
        # X is constant for a (book, play) pair wherever it already appears;
        # reuse it so an added play behaves like the same play elsewhere in this
        # book. Otherwise take the neutral default the game writes into unused
        # records.
        x = next(
            (
                other.x
                for candidate in book.records
                for other in candidate.entries
                if other.play_index == change.play_index
            ),
            NEUTRAL_X,
        )
        # A formation short of plays is also short of tagged slots, so growing it
        # has to hand the new play the next slot or the min(4, plays) rule breaks.
        y = UNTAGGED_Y
        if len(tags_of(entries)) < required_tag_count(len(entries) + 1):
            free = _next_free_tag(entries)
            y = UNTAGGED_Y if free is None else free
        entries.append(SplbEntry(x, y, change.play_index))

    for move in moves:
        source = index_of(move.from_play)
        target = index_of(move.to_play)
        if source is None or target is None:
            missing = move.from_play if source is None else move.to_play
            raise ValidationError(
                f"Play {missing} is not in record {record.record_index}, so a tagged "
                "slot cannot be moved to or from it"
            )
        if not entries[source].tagged:
            raise ValidationError(
                f"Play {move.from_play} holds no tagged slot in record "
                f"{record.record_index}"
            )
        origin, destination = entries[source], entries[target]
        entries[source] = SplbEntry(origin.x, destination.y, origin.play_index)
        entries[target] = SplbEntry(destination.x, origin.y, destination.play_index)

    removing = {change.play_index for change in memberships if not change.member}
    if entries and all(entry.play_index in removing for entry in entries):
        # min(4, 0) is 0: a formation with no stored plays carries no tagged
        # slots. The trailer still names the formation; CPU selection of that
        # empty record is unproved.
        _check_tag_rule(record.record_index, before, [])
        return ()

    for change in memberships:
        if change.member:
            continue
        victim_at = index_of(change.play_index)
        if victim_at is None:
            continue
        victim = entries[victim_at]
        if victim.tagged and change.tag_heir is not None:
            heir_at = index_of(change.tag_heir)
            if heir_at is None or heir_at == victim_at:
                raise ValidationError(
                    f"Play {change.tag_heir} cannot carry tagged slot {victim.y}: it is "
                    f"not another play in record {record.record_index}"
                )
            heir = entries[heir_at]
            entries[heir_at] = SplbEntry(heir.x, victim.y, heir.play_index)
        elif victim.tagged and follows_tag_rule(before):
            surviving = len(tags_of(entries)) - 1
            if surviving != required_tag_count(len(entries) - 1):
                raise ValidationError(
                    f"Play {change.play_index} holds tagged slot {victim.y} in record "
                    f"{record.record_index}, and this formation has to keep "
                    f"{required_tag_count(len(entries) - 1)} tagged slots. Name another "
                    "play in the same formation to carry the slot, or move the slot "
                    "first — the studio offers both."
                )
        entries.pop(victim_at)

    if len(entries) > ENTRY_CAPACITY:
        raise ValidationError(
            f"Record {record.record_index} overflowed its {ENTRY_CAPACITY} entry slots"
        )
    _check_tag_rule(record.record_index, before, entries)
    return tuple(entries)


def compile_book(
    book: SplbBook, changes: Iterable[MembershipChange | TagMove]
) -> CompiledBook:
    """Rewrite only the entry prefixes the changes touch."""

    request = _normalize(changes)
    if request.outer_index != book.outer_index:
        raise ValidationError("These changes belong to a different stock playbook")
    replacement = bytearray(book.body)
    applied: list[dict[str, Any]] = []
    off_distribution: list[int] = []
    emptied: list[int] = []

    for record_index in sorted(request.record_indices):
        if not 0 <= record_index < RECORD_COUNT:
            raise ValidationError(f"Record {record_index} is outside this book")
        record = book.records[record_index]
        memberships = tuple(
            change
            for change in request.memberships
            if change.record_index == record_index
        )
        moves = tuple(
            move for move in request.moves if move.record_index == record_index
        )
        entries = apply_record_changes(book, record, memberships, moves)
        if not retail_tag_shape(entries):
            off_distribution.append(record_index)
        if record.populated and not entries:
            emptied.append(record_index)
        present = {entry.play_index for entry in record.entries}
        for change in memberships:
            if change.member == (change.play_index in present):
                continue    # asked for what the record already said
            applied.append(
                {
                    "kind": "membership",
                    "selector": change.selector,
                    "record_index": record_index,
                    "formation_index": record.formation_index,
                    "play_index": change.play_index,
                    "member_after": change.member,
                    "tag_heir": change.tag_heir,
                }
            )
        for move in moves:
            applied.append(
                {
                    "kind": "tag_move",
                    "selector": move.selector,
                    "record_index": record_index,
                    "formation_index": record.formation_index,
                    "from_play": move.from_play,
                    "to_play": move.to_play,
                }
            )
        base = RECORD_BASE + record_index * RECORD_STRIDE
        for slot in range(ENTRY_CAPACITY):
            value = entries[slot].encode() if slot < len(entries) else FILLER
            struct.pack_into(">H", replacement, base + slot * 2, value)

    trailer_replaced: list[dict[str, Any]] = []
    category_bits_added = 0
    for trailer in sorted(
        request.trailers, key=lambda item: item.record_index
    ):
        record = book.records[trailer.record_index]
        trailer_at = (
            RECORD_BASE + trailer.record_index * RECORD_STRIDE + TRAILER_OFFSET
        )
        before_a, before_b = struct.unpack_from(">2I", book.body, trailer_at)
        before_formation = before_a >> 24
        before_category = (before_a >> 17) & 0x7F
        if (
            before_formation == trailer.formation_index
            and before_category == trailer.category_index
            and before_b & (1 << trailer.category_index)
        ):
            raise ValidationError(
                f"Record {trailer.record_index} already lines up as MASTER "
                f"formation {trailer.formation_index} under personnel package "
                f"{trailer.category_index}; nothing to replace"
            )
        after_a = (before_a & 0x0001FFFF) | (
            trailer.formation_index << 24
        ) | (trailer.category_index << 17)
        after_b = before_b | (1 << trailer.category_index)
        struct.pack_into(">2I", replacement, trailer_at, after_a, after_b)
        category_bits_added |= 1 << trailer.category_index
        applied.append(
            {
                "kind": "trailer_replace",
                "selector": trailer.selector,
                "record_index": trailer.record_index,
                "formation_before": before_formation,
                "formation_after": trailer.formation_index,
                "category_before": before_category,
                "category_after": trailer.category_index,
                "word_b_before": before_b,
                "word_b_after": after_b,
            }
        )
        trailer_replaced.append(applied[-1])
    if request.trailers:
        mask_at = BOOK_CATEGORY_MASK_OFFSET
        before_mask = struct.unpack_from(">I", book.body, mask_at)[0]
        after_mask = before_mask | category_bits_added
        struct.pack_into(">I", replacement, mask_at, after_mask)

    if len(replacement) != len(book.body):
        raise ValidationError("A stock-playbook edit changed the resource length")
    populated_before = {
        record.record_index for record in book.records if record.populated
    }
    surviving = populated_before - set(emptied)
    if populated_before and not surviving:
        # Static: count 0x84a8ac30 returns 0 and get-nth 0x84a8bd20 returns null
        # for an empty record.  Runtime (Urianus, alpha.70): the director does
        # not skip that cleanly -- it lines up plays and personnel packages the
        # book does not contain.  A book with no formation left to call has no
        # honest reading at all, so it is refused rather than shipped.
        raise ValidationError(
            f"This request empties every populated formation in book "
            f"{book.outer_index}"
            + (f" ({book.name})" if book.name else "")
            + ". A book with no stored plays anywhere leaves the CPU director "
            "nothing to select, and emptied records are reported in-game to "
            "produce out-of-book plays and personnel packages. Keep at least one "
            "formation populated."
        )
    claims: dict[str, Any] = {
        "entry_prefix_only": not bool(request.trailers),
        "trailers_untouched": not bool(request.trailers),
        "unmapped_tail_untouched": True,
        "resource_length_unchanged": True,
        "tag_count_rule_held": True,
        "tag_meaning_proved": False,
        "cpu_membership_static_proved": True,
        "cpu_behaviour_runtime_proved": False,
        "empty_record_returns_no_plays": True,
        # Static count/get-nth returning 0/null was never a proof that the
        # director handles an empty record gracefully, and a community
        # runtime report says it does not.  Say so on every compile that
        # empties one.
        "empty_record_runtime_safe": False,
        "empty_record_reported_out_of_book_calls": bool(emptied),
        "wr3_te_package_sub_proved": False,
    }
    if request.trailers:
        # The trailer is consumed by the lineup chain exactly as pinned:
        # category extract 0x8485BD40, formation byte 0x84A8B8D4, book mask
        # walk 0x84A8B438/0x84A89680.  Whether the director SELECTS the
        # repointed record differently on any situation is runtime-unproved.
        claims.update(
            {
                "trailer_replace_whitelisted_only": True,
                "book_category_mask_untouched": False,
                "trailer_cde_fields_preserved": True,
                "trailer_low_byte_preserved": True,
                "book_category_mask_only_gained_bits": True,
                "formation_index_in_master": True,
                "category_index_in_table": True,
                "cpu_trailer_consumption_static_proved": True,
                "director_formation_choice_proved": False,
                "runtime_lineup_after_replace_proved": False,
            }
        )
    report = {
        "schema": REPORT_SCHEMA,
        "provider_kind": PROVIDER_KIND,
        "outer_index": book.outer_index,
        "book_name": book.name,
        "changes": applied,
        # Every retail record's tag set is a prefix of 1, 0, 2, 3. An edit can
        # leave a legal set that is still not one retail uses; say so rather than
        # quietly refusing or quietly shipping it.
        "records_outside_retail_tag_sets": off_distribution,
        "records_emptied": emptied,
        "records_trailer_replaced": trailer_replaced,
        "populated_records_remaining": len(surviving),
        "claims": claims,
    }
    return CompiledBook(book.outer_index, b"", bytes(replacement), report)


def verify_book(
    before: bytes,
    after: bytes,
    changes: Iterable[MembershipChange | TagMove | TrailerReplace],
) -> Mapping[str, Any]:
    """Re-derive every changed byte without trusting the compiler.

    Every difference must fall inside the 168-byte entry region of a record a
    change named, or inside the 8 trailer bytes / book category mask that a
    trailer replace named. Any other trailer byte, either unmapped tail
    region, or any other record fails here rather than in someone's game. The
    tagged-slot rule is re-derived from the output bytes too, so a compiler
    that lost or duplicated a slot cannot ship it.
    """

    request = _normalize(changes)
    if len(before) != len(after):
        raise ValidationError("Stock-playbook verification: resource length changed")
    touched = request.record_indices
    trailer_records = {trailer.record_index for trailer in request.trailers}
    allowed: set[int] = set()
    for record_index in touched:
        base = RECORD_BASE + record_index * RECORD_STRIDE
        allowed.update(range(base, base + ENTRY_BYTES))
    for record_index in trailer_records:
        base = RECORD_BASE + record_index * RECORD_STRIDE + TRAILER_OFFSET
        allowed.update(range(base, base + 8))
    if trailer_records:
        allowed.update(
            range(BOOK_CATEGORY_MASK_OFFSET, BOOK_CATEGORY_MASK_OFFSET + 4)
        )
    differing = [i for i in range(len(before)) if before[i] != after[i]]
    for offset in differing:
        if offset not in allowed:
            raise ValidationError(
                f"Stock-playbook verification: byte 0x{offset:x} changed outside the "
                "entry region of any record a change named"
            )
    # The decoded result must actually say what was asked. Isolated
    # original-vs-final checks on one TagMove or one heir break down once a
    # request composes an add with a move (the destination has no original Y)
    # or several removals (a later change can take the slot onward). Re-apply
    # the same request to the parsed-before book and demand the packed bytes
    # match that entry list.
    parsed_before = parse_book(before, request.outer_index)
    parsed_after = parse_book(after, request.outer_index)
    for change in request.memberships:
        record = parsed_after.records[change.record_index]
        present = any(e.play_index == change.play_index for e in record.entries)
        if present != change.member:
            raise ValidationError(
                "Stock-playbook verification: the reparsed book disagrees with the "
                f"request for record {change.record_index} play {change.play_index}"
            )
    for record_index in sorted(touched):
        memberships = tuple(
            change
            for change in request.memberships
            if change.record_index == record_index
        )
        moves = tuple(
            move for move in request.moves if move.record_index == record_index
        )
        expected = apply_record_changes(
            parsed_before, parsed_before.records[record_index], memberships, moves
        )
        actual = parsed_after.records[record_index].entries
        _check_tag_rule(
            record_index, parsed_before.records[record_index].entries, list(actual)
        )
        if actual == expected:
            continue
        was = {
            entry.play_index: entry.y
            for entry in parsed_before.records[record_index].entries
        }
        now = {entry.play_index: entry.y for entry in actual}
        for move in moves:
            if now.get(move.to_play) != was.get(move.from_play):
                raise ValidationError(
                    "Stock-playbook verification: the reparsed book does not show tagged "
                    f"slot {was.get(move.from_play)} moved from play {move.from_play} to "
                    f"{move.to_play} in record {move.record_index}"
                )
        for change in memberships:
            if change.tag_heir is None or change.member:
                continue
            origin = next(
                (
                    entry.y
                    for entry in parsed_before.records[record_index].entries
                    if entry.play_index == change.play_index
                ),
                None,
            )
            heir = next(
                (entry for entry in expected if entry.play_index == change.tag_heir),
                None,
            )
            if heir is not None and origin is not None and heir.y == origin:
                # The request still names this heir; the packed bytes lost it.
                packed = next(
                    (entry for entry in actual if entry.play_index == change.tag_heir),
                    None,
                )
                if packed is None or packed.y != origin:
                    raise ValidationError(
                        f"Stock-playbook verification: play {change.tag_heir} did not "
                        f"inherit tagged slot {origin} in record {record_index}"
                    )
        raise ValidationError(
            f"Stock-playbook verification: record {record_index} entries do not "
            "match the requested edits"
        )
    for trailer in request.trailers:
        trailer_at = (
            RECORD_BASE + trailer.record_index * RECORD_STRIDE + TRAILER_OFFSET
        )
        before_a, before_b = struct.unpack_from(">2I", before, trailer_at)
        after_a, after_b = struct.unpack_from(">2I", after, trailer_at)
        expected_a = (before_a & 0x0001FFFF) | (
            trailer.formation_index << 24
        ) | (trailer.category_index << 17)
        expected_b = before_b | (1 << trailer.category_index)
        if after_a != expected_a or after_b != expected_b:
            raise ValidationError(
                f"Stock-playbook verification: record {trailer.record_index} "
                "trailer does not match the requested formation/package"
            )
    expected_mask = struct.unpack_from(">I", before, BOOK_CATEGORY_MASK_OFFSET)[0]
    for trailer in request.trailers:
        expected_mask |= 1 << trailer.category_index
    after_mask = struct.unpack_from(">I", after, BOOK_CATEGORY_MASK_OFFSET)[0]
    if after_mask != expected_mask:
        raise ValidationError(
            "Stock-playbook verification: the book category mask does not match "
            "the requested packages"
        )
    for index, (a, b) in enumerate(zip(parsed_before.records, parsed_after.records)):
        if index not in trailer_records and a.trailer != b.trailer:
            raise ValidationError(
                f"Stock-playbook verification: record {index} trailer changed"
            )
        if index not in touched and a.entries != b.entries:
            raise ValidationError(
                f"Stock-playbook verification: untouched record {index} changed"
            )
        if index in touched:
            _check_tag_rule(index, a.entries, list(b.entries))
    return {
        "schema": REPORT_SCHEMA,
        "changed_byte_count": len(differing),
        "changed_records": sorted(touched),
        "trailer_records": sorted(trailer_records),
        "tag_rule_reverified": True,
        "independent_reparse": True,
    }


def build_book_patch(
    index_path: Path, changes: Iterable[MembershipChange | TagMove]
) -> CompiledBook:
    """Compile changes into a rebuilt outer entry without touching the source."""

    normalized = tuple(changes)
    outer_index = _normalize(normalized).outer_index
    book = read_book(Path(index_path), outer_index)
    compiled = compile_book(book, normalized)

    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[outer_index]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            original_blocks = [
                apf_inner.decode_block(reader, record, i, 64 * 1024 * 1024)
                for i in range(record.block_count)
            ]
            original_stored = [
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            ]
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open the APF stock playbook: {exc}") from exc

    target_part = record.files[0].parts[0]
    patched_block = bytearray(original_blocks[target_part.block_index])
    patched_block[target_part.offset : target_part.offset + target_part.length] = (
        compiled.replacement
    )
    new_block = bytes(patched_block)
    descriptor = record.blocks[target_part.block_index]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise ValidationError("The APF stock playbook block is no longer H7A-compressed")
    try:
        compressed, preservation = apf_inner.encode_h7a_preserving_tokens(
            original_stored[target_part.block_index][apf_inner.H7A_HEADER_SIZE :],
            original_blocks[target_part.block_index],
            new_block,
            descriptor.wrapper.shift,
        )
        stored = struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_block),
            apf_inner.H7A_HEADER_SIZE + len(compressed),
            descriptor.unknown_10,
            descriptor.wrapper.shift,
        ) + compressed
        roundtrip = apf_inner.decompress_h7a(
            compressed, len(new_block), descriptor.wrapper.shift
        )
    except apf_inner.FormatError as exc:
        raise ValidationError(f"Could not encode the stock playbook H7A: {exc}") from exc
    if roundtrip != new_block:
        raise ValidationError("Stock-playbook H7A round trip changed the edit")

    header = bytearray(original_entry[: record.header_size])
    struct.pack_into(
        ">8I",
        header,
        apf_inner.IFF_HEADER_SIZE,
        descriptor.name_hash,
        descriptor.type_hash,
        descriptor.unknown_08,
        descriptor.uncompressed_length,
        descriptor.unknown_10,
        record.header_size,
        len(stored),
        descriptor.indexed,
    )
    file_length = record.header_size + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    if any(original_entry[record.file_length + footer_size :]):
        raise ValidationError("The stock-playbook outer allocation has a nonzero tail")
    active = bytes(header) + stored + footer
    if len(active) > entry.size:
        raise ValidationError(
            "The edited stock playbook does not fit the game's fixed allocation"
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory = apf_texture_patch.BytesReader(rebuilt)
    try:
        reparsed = apf_inner.parse_iff(memory, entry)
        decoded = apf_inner.decode_block(
            memory, reparsed, target_part.block_index, 64 * 1024 * 1024
        )
    except apf_inner.FormatError as exc:
        raise ValidationError(f"The rebuilt stock playbook is invalid: {exc}") from exc
    if reparsed.warnings or decoded != new_block:
        raise ValidationError("The rebuilt stock playbook changed its decoded block")
    rebuilt_part = reparsed.files[0].parts[0]
    verified = decoded[rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length]
    verification = verify_book(book.body, verified, normalized)

    report = {
        **dict(compiled.report),
        "output_entry_size": len(rebuilt),
        "output_entry_sha256": _sha256(rebuilt),
        "verification": dict(verification),
        "h7a_transport": {"strategy": "retail-token-preserving", **preservation},
        "claims": {
            **dict(compiled.report["claims"]),
            "fixed_outer_allocation_preserved": True,
            "h7a_round_trip_exact": True,
        },
    }
    return CompiledBook(outer_index, rebuilt, compiled.replacement, report)


__all__ = [
    "ARRAY_END",
    "ENTRY_CAPACITY",
    "FILLER",
    "MAX_TAGS",
    "PAYLOAD_SCHEMA",
    "PROVIDER_KIND",
    "RECORD_BASE",
    "RECORD_COUNT",
    "RECORD_STRIDE",
    "REPORT_SCHEMA",
    "STOCK_BOOKS",
    "TAG_PRIORITY",
    "FLIP_SUFFIX",
    "BOOK_CATEGORY_MASK_OFFSET",
    "CATEGORY_COUNT",
    "MASTER_FORMATION_INDEX_MAX",
    "CompiledBook",
    "MembershipChange",
    "TrailerReplace",
    "trailer_selector",
    "find_flip_partner_record",
    "flip_partner_name",
    "SplbBook",
    "SplbEntry",
    "SplbRecord",
    "TagMove",
    "apply_record_changes",
    "build_book_patch",
    "change_from_mapping",
    "change_metadata",
    "compile_book",
    "decode_membership_payload",
    "encode_membership_payload",
    "entry_selector",
    "follows_tag_rule",
    "parse_book",
    "read_book",
    "required_tag_count",
    "retail_tag_shape",
    "tag_selector",
    "tags_of",
    "verify_book",
]

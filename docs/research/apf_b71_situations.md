# CPU situation candidates, beta 71

**PROVED** below means pinned data or bounded native execution. Editor tests are
reported separately as offline validation. Every in-game outcome is **UNWITNESSED**.

## Scope and remaining limit

CPU Play Calling now selects the book directly, lists candidate formations and
their selected personnel's TE count for all 23 spreadsheet situations, and
offers explicit addition, personnel edits and complete book removal. These edits
use the game's shared book data. They affect every situation that uses it.

**Independent per-situation formation whitelists are not implemented.** The
23 spreadsheet buckets are representative queries, not 23 stored candidate lists.
Openers, first-and-10 and sudden change have identical supplied inputs. Red-zone
queries share the ordinary row calculation. Two-point is explicitly a scrimmage
proxy. A new runtime selector and candidate-gate patch would be needed for
independent lists. A guessed mask, the unrelated lineup ladder, and low ratings
cannot supply that control. The editor labels this limitation at the edit point.

## Stored data and the native path

| Data | Native consumer | PROVED role |
| --- | --- | --- |
| SPLB record `0x70 + n*0xB0`, 84 big-endian halfwords | `84A8AC30`, `84A8BD20` | Contiguous play membership; low 10 bits are the play ID, `0x3FF` terminates it |
| Trailer A, record `+0xA8` | `84A8A258`, `84869058` | Formation ID bits 31..24; primary category ID bits 23..17; short/medium/long raw ratings at shifts 14/11/8 |
| Trailer B, record `+0xAC` | `84A8B660`, `84A8A330`, `848693F8` | Category membership bits; zero removes ordinary lottery membership |
| SPLB `+0x7E04` | `8486AEB0`; rebuilt by `84A8C790` | Derived advertised-category bitmap, not an independent situation list |
| MASTER category `+0x44 + id*16` | `8486AEB0`, `84860020` | Byte +4 low six bits are the personnel row; +5..+15 low five bits are eleven roles; role 8 is TE |
| MASTER formation `+0x244 + id*184` | `848693F8`, `84869058` | Family, flags and geometry. Selected category and formation are separate outputs |
| Live down/position/urgency | `84867600` | Requested personnel row, independent of book name |
| Category distance curve `820C88A8` | `8486AEB0` | Positive offensive distance weights, including the distant tail; not a cutoff |

The ordinary chain is `8486CE88 -> 8486C930 -> 8486AEB0` (category),
`8486BC08 -> 848693F8` (formation), then `8486B2D0` (play).
The separate `84860730` lineup resolver does not enter the bounded ordinary call.
Formation selection prefers primary memberships when any exist in the selected
category; merely adding a secondary membership need not make that formation enter
its formation draw. The candidate table displays category/formation pairs for
this reason. Its weights use neutral urgency and a neutral run share; they are
not frequencies. History, run/pass decisions, special calls and the 40-slot
candidate limit can change the eventual call.

## Minimum rating and tight ends

**PROVED, BASE and TU 1.1:** retain only Queens formation 14 in O-ManBlock, set
7/7/7 with the production writer, normalize natively, and request neutral
third-and-8. Category 6 weighs approximately 0.05; the formation weighs 0.1.
All eight full bounded selections (four RNG fractions on each image) return that
formation and a valid play. A one-element lottery selects its sole element.
Rating 7 is neither a zero weight nor a removal marker.

**PROVED, BASE and TU 1.1:** changing formation 14 to category 7 (Straight) and
removing the remaining category-6 formations removes Queens membership after
native normalization. Six tested third-and-8 tuples select formation 14 with
category 7, whose eleven roles contain one TE. This is a shared book edit, not a
third-down-only edit. Unchanged Queens/category 6 has zero TE roles.

**HYPOTHESIS / unresolved:** whether a later producer substitutes a zero-TE lineup
after a one-TE call tuple. The native tests stop at `8486D0CC`, after output tuple
stores and before the manager/current-call update. They do not execute the final
`84860020` eleven-player builder, saved USER-book overlay lifecycle, or subsequent
package substitutions. Existing BASE/TU tests show different primary preferences
at `84864AB8` / TU `84865758`, and at the `84867938` staging boundary. Those are
specific remaining boundaries, not evidence of on-field TE control. A selected
zero-TE category is a proved producer of a zero-TE *requested role list*; the
source of a divergent final on-field lineup remains unknown.

## The 23 bounded queries

On O-ManBlock, neutral urgency, uniform 0.5, explicit cold state. Each row and
every captured category/formation vector is compared on BASE and TU 1.1. The
two images give the same row/category pairs below. This does not model special
phase dispatch for a two-point try or clock-management overrides.

| Spreadsheet query | Requested row | Selected category ID |
| --- | ---: | ---: |
| Openers | 4 | 3 |
| 1st and 10 | 4 | 3 |
| 2nd and 2-3 | 0 | 1 |
| 2nd and 4-6 | 3 | 1 |
| 2nd and 7-10 | 4 | 3 |
| 2nd and 11+ | 7 | 6 |
| 3rd and 2-3 | 4 | 1 |
| 3rd and 4-6 | 7 | 6 |
| 3rd and 7-10 | 10 | 6 |
| 3rd and 11+ | 10 | 6 |
| 4th down | 4 | 1 |
| Short yardage | 1 | 1 |
| Red zone 25-21 | 4 | 3 |
| Red zone 20-16 | 4 | 3 |
| Red zone 15-11 | 4 | 3 |
| Red zone 10 and in | 4 | 3 |
| Goal line | 0 | 1 |
| 2pt (scrimmage proxy) | 4 | 1 |
| Backed-up | 4 | 3 |
| After negative play | 7 | 6 |
| Sudden change | 4 | 3 |
| 4-minute (cold proxy) | 4 | 3 |
| 2-minute (cold proxy) | 4 | 3 |

## Reproduction and identity

`tests/mod_editor/test_apf_playcall_research_native.py` retains all original 22
cases and adds four beta-71 cases. Native calls are bounded; selection functions
execute their actual instructions. RNG and kicker-range leaves remain explicit
test inputs; the existing PPC32 adapters implement the documented Xenon ABI and
instruction transports. No executable or retail resource is written to disk.

| Input | SHA-256 |
| --- | --- |
| Owned default.xex | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Flat BASE | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| Flat TU 1.1 | `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` |
| MASTER body | `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` |

Run with `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen`:

```
python3 tests/mod_editor/test_apf_playcall_research_native.py
python3 tests/mod_editor/test_apf_b71_situations.py
python3 tests/mod_editor/test_apf_playcalling_editor_qt.py
python3 tests/mod_editor/test_apf_book_identity_qt.py
```

The ordinary editor stages nothing on opening a page or choosing a book or
situation. No preset activates an edit. Book Identity in the integrated studio
points to CPU Play Calling; its duplicate edit workflow is hidden.

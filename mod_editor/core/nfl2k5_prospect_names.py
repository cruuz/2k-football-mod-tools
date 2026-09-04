"""Modern draft-prospect names: the generated-player name pool rewritten in place, plus a 27-byte
cave that keeps the recorded surname call-outs for every surname the rewrite leaves alone.

Where the names come from (retail pack ``vc_53450030/0``, outer entry 5 = the main ROST resource,
uncompressed, 0x20-byte wrapper + 0x90F60 body; studied 2026-09-04):

* The roster object is the body at +0x40.  Its ``+0x50/+0x54`` pair (body ``+0x90/+0x94``) is the
  generated-name pool: count **485** and a field-local relative pointer (``target = field + value - 1``)
  to the entry array at body **0x72FB4** (8 bytes per entry: relative pointer to the first name, then
  to the last name; 3,880 bytes).  The strings are zero-terminated UTF-16LE, interleaved
  ``first0, last0, first1, ...`` at body **0x8B7D0..0x8EB86** (13,238 bytes, all 970 unique, max 10
  characters).  The 272 zero bytes before them (0x8B6C0..0x8B7D0) are NOT free: they are the empty
  first/last names of the 68 spare player records after the 2,479 real ones (136 relative pointers
  land there, two bytes each), so the in-place budget is exactly the retail span, **13,238 bytes**.
  The team nicknames ("49ers", ...) start right after 0x8EB86.
* The retail lists are the 1990 US Census male first names in rank order (James, John, Robert, ...;
  "Wm" is a Census artefact) and the Census surname rank list (Smith, Johnson, ...) with three
  developer names spliced in (Horsley #171, Hamre #257, Zdyrko #483).  Drawn independently and
  uniformly, they put a Hispanic-origin first or last name on 21 % of generated players (1-2 % on
  2015-2025 NFL rosters) and no modern first name at all (no Jordan, Tyler, Isaiah, Jalen, ...).
* The only generator, ``FUN_002be6f0`` (0x2BE6F0), draws ``first = pool[rand % count].first`` and
  ``last = pool[rand2 % count].last`` (two independent uniform draws, no weights, no coupling to
  skin tone, college or face) and stores **player+0x04 = 9300 + surname index** (``add edx,0x2454 ;
  mov [esi+4],dx`` at **0x2BE7B8**).  That word is the commentary audio id: the resolver
  ``FUN_00067150`` classes 9000..10000 as player-name cues, so the announcer reads a generated
  rookie's surname from a 485-entry recorded bank indexed by pool position; ids without a cue fall
  back to "number NN" (9000 + jersey).  The Create Player "random name" and the getters at
  0x2422F0/0x242300/0x2BCE70/0x2BCE80 read the same pool and care about neither order nor count.

What the patch does (tier B of the 2026-09-04 study):

1. **Pool rewrite** (data, no VC-LZ refit).  485 ``(first, last)`` rows from
   ``data/nfl2k5_modern_names.csv`` (nflverse-data 2015-2025 rosters, CC-BY-4.0) or a user CSV are
   written back into the same 13,238 bytes: every surname that equals the retail surname at its index
   (433 of the shipped rows) is written FIRST, in index order, so it stays below a **boundary**; then
   the replacement surnames (52: the Hispanic-origin entries and the three developer names, taken by
   the most frequent modern surnames the recorded bank does not know) and all 485 first names.  The
   970 relative pointers are recomputed; the count word, the array offset and every byte outside the
   array and the string span are untouched.  Rules: ASCII letters plus ``' - .``, 1..12 characters
   (the UI copies names into 16-wchar buffers; retail's longest is 10), 485 rows, total <= 13,238 B.
2. **Executable cave** (27 bytes) hooked at 0x2BE7B8 (``add edx,0x2454`` -> ``call cave ; nop``).
   At the hook ``ecx`` is the entry's surname pointer (``mov ecx,[eax+4]`` at 0x2BE7B5), ``edx`` the
   index and ``eax`` dead (reloaded at 0x2BE7D3 after the ``call FUN_000e6780``)::

       mov eax,[0xB72918]        ; the live roster object (= body + 0x40)
       add eax,BOUNDARY - 0x40   ; the body offset where the replacement surnames begin
       cmp ecx,eax
       jae replacement
       add edx,0x2454 ; ret      ; retained surname: 9300 + index, the retail call-out
   replacement:
       mov edx,0x238C ; ret      ; 9100: no recorded cue, the resolver announces the number

   BOUNDARY is baked at apply time from the CSV layout, so the executable half and the pool half
   belong together: the build writes both, ``inspect`` reports ``applied`` only when both are present
   and the baked boundary agrees with the pool's layout, and ``partial`` when one is missing.
   Host: the tail of the dead ``FUN_000b4a60`` (0xB4A70..0xB4A8B; the penalties patch's Chop Block
   stub owns 0xB4A60..0xB4A70 of the same routine; zero rel32 / immediate / pointer references land
   anywhere in 0xB4A60..0xB4A8E in the retail image, and the routine's ``ret 8`` and nop padding at
   0xB4A8B..0xB4A90 stay retail).  The cave writes no memory, so both cave gates pass.

Consequences: a franchise created from the patched disc drafts 2020s-sounding classes; a rookie with
a retained surname (Smith, Jackson, Brown, ...) is announced by name as in retail, one with a
replacement surname (Diggs, Chubb, ...) by number.  Saves made before the patch carry their own roster copy
(new franchise needed; an old save on the patched executable would announce its own high-index
retail surnames by number, nothing worse).  Unwitnessed in game.
"""

from __future__ import annotations

import csv
import hashlib
import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from . import nfl2k5_team_history as _rost

ROOT = Path(__file__).resolve().parents[2]
IMAGE_BASE = 0x10000

# --- the pool inside the ROST body ------------------------------------------------------------
ROST_OUTER_INDEX = _rost.ROST_OUTER_INDEX
RESOURCE_HEADER_SIZE = _rost.RESOURCE_HEADER_SIZE
BODY_SIZE = _rost.BODY_SIZE
OBJ_OFF = _rost.OBJ_OFF             # the roster object inside the body (runtime [0xB72918] points here)
HEADER_COUNT_OFF = 0x90             # body + 0x90 = obj + 0x50: entry count
HEADER_ARRAY_OFF = 0x94             # body + 0x94 = obj + 0x54: relative pointer to the entry array
POOL_COUNT = 485
ARRAY_OFF = 0x72FB4
ARRAY_SIZE = POOL_COUNT * 8
STRINGS_START = 0x8B7D0
STRINGS_END = 0x8EB86
BUDGET = STRINGS_END - STRINGS_START        # 13,238 bytes: the retail span, see the module docstring
MAX_NAME_CHARS = 12
NAME_PUNCTUATION = "'-."
ROSTER_GLOBAL = 0x00B72918                  # -> the live roster object
RETAIL_AUDIO_BASE = 0x2454                  # 9300: player+0x04 = 9300 + surname index
NUMBER_AUDIO_ID = 0x238C                    # 9100: no recorded cue -> the resolver falls back to "number NN"

# sha256 of body[0x90:0x98] + the entry array + the string span, see pool_digest()
RETAIL_POOL_SHA256 = "1a4900797b05ecc9858f2663cf1afbce9d4dc1d33dd803559e3350b008d204ab"
SHIPPED_CSV = ROOT / "data" / "nfl2k5_modern_names.csv"
SHIPPED_CSV_SHA256 = "c94fb3b94aae5cccd831e43bb8939073446cf61cce8934ea454e4c129355794a"   # tools/nfl2k5_modern_names_generate.py, 2026-09-04
SHIPPED_POOL_SHA256 = "6e69e6423bc74c3a2a29dc0931261cb04bd0637874b1fa3332e6d9dfcf79d1ee"  # the pool digest after the shipped CSV is applied to the retail roster
SHIPPED_BOUNDARY = 0x8CFAA             # body offset of the first replacement surname under the shipped CSV
ATTRIBUTION = "nflverse-data (https://github.com/nflverse/nflverse-data), CC-BY-4.0"

CSV_COLUMNS = ("first", "last")
CSV_OPTIONAL = ("index", "audio", "note")

# The retail pool, in index order (the recorded surname bank is indexed by position: a surname equal to
# RETAIL_LASTS[i] at index i keeps its call-out).  Pinned by RETAIL_POOL_SHA256: the retail span is
# reproducible from these two tuples (test_nfl2k5_prospect_names).
RETAIL_LASTS = (
    'Smith', 'Johnson', 'Williams', 'Jones', 'Brown', 'Davis', 'Miller', 'Wilson', 'Moore', 'Taylor',
    'Anderson', 'Thomas', 'Jackson', 'White', 'Harris', 'Martin', 'Thompson', 'Garcia', 'Martinez',
    'Robinson', 'Clark', 'Rodriguez', 'Lewis', 'Lee', 'Walker', 'Hall', 'Allen', 'Young', 'King', 'Wright',
    'Lopez', 'Hill', 'Scott', 'Green', 'Adams', 'Baker', 'Nelson', 'Carter', 'Mitchell', 'Roberts', 'Turner',
    'Phillips', 'Campbell', 'Parker', 'Evans', 'Edwards', 'Collins', 'Stewart', 'Sanchez', 'Morris', 'Rogers',
    'Reed', 'Cook', 'Morgan', 'Bell', 'Murphy', 'Bailey', 'Rivera', 'Cooper', 'Richardson', 'Cox', 'Howard',
    'Ward', 'Torres', 'Peterson', 'Gray', 'Ramirez', 'James', 'Watson', 'Brooks', 'Kelly', 'Sanders', 'Price',
    'Bennett', 'Wood', 'Barnes', 'Ross', 'Henderson', 'Coleman', 'Jenkins', 'Perry', 'Powell', 'Long',
    'Patterson', 'Hughes', 'Flores', 'Washington', 'Butler', 'Simmons', 'Foster', 'Bryant', 'Alexander',
    'Russell', 'Griffin', 'Hayes', 'Myers', 'Ford', 'Hamilton', 'Graham', 'Sullivan', 'Wallace', 'Woods',
    'Cole', 'West', 'Jordan', 'Owens', 'Reynolds', 'Fisher', 'Ellis', 'Harrison', 'Gibson', 'McDonald',
    'Cruz', 'Marshall', 'Ortiz', 'Gomez', 'Murray', 'Freeman', 'Wells', 'Webb', 'Simpson', 'Stevens',
    'Tucker', 'Porter', 'Hunter', 'Hicks', 'Crawford', 'Henry', 'Boyd', 'Mason', 'Morales', 'Kennedy',
    'Warren', 'Dixon', 'Ramos', 'Reyes', 'Burns', 'Gordon', 'Shaw', 'Holmes', 'Rice', 'Robertson', 'Hunt',
    'Black', 'Daniels', 'Palmer', 'Mills', 'Nichols', 'Grant', 'Knight', 'Ferguson', 'Rose', 'Stone',
    'Hawkins', 'Dunn', 'Perkins', 'Hudson', 'Spencer', 'Gardner', 'Stephens', 'Payne', 'Pierce', 'Berry',
    'Matthews', 'Arnold', 'Wagner', 'Willis', 'Ray', 'Watkins', 'Olson', 'Carroll', 'Horsley', 'Duncan',
    'Snyder', 'Hart', 'Cunningham', 'Bradley', 'Lane', 'Andrews', 'Ruiz', 'Harper', 'Fox', 'Riley',
    'Armstrong', 'Carpenter', 'Weaver', 'Greene', 'Lawrence', 'Elliott', 'Chavez', 'Sims', 'Austin', 'Peters',
    'Kelley', 'Franklin', 'Lawson', 'Fields', 'Ryan', 'Schmidt', 'Carr', 'Wheeler', 'Chapman', 'Oliver',
    'Montgomery', 'Richards', 'Williamson', 'Johnston', 'Banks', 'Meyer', 'Bishop', 'McCoy', 'Howell',
    'Alvarez', 'Morrison', 'Hansen', 'Harvey', 'Little', 'Burton', 'Stanley', 'George', 'Jacobs', 'Reid',
    'Kim', 'Fuller', 'Lynch', 'Dean', 'Gilbert', 'Garrett', 'Larson', 'Romero', 'Welch', 'Frazier', 'Burke',
    'Hanson', 'Day', 'Mendoza', 'Moreno', 'Bowman', 'Medina', 'Fowler', 'Brewer', 'Hoffman', 'Carlson',
    'Silva', 'Pearson', 'Holland', 'Douglas', 'Fleming', 'Jensen', 'Vargas', 'Byrd', 'Davidson', 'Hopkins',
    'May', 'Terry', 'Herrera', 'Wade', 'Hamre', 'Soto', 'Walters', 'Curtis', 'Neal', 'Caldwell', 'Lowe',
    'Jennings', 'Barnett', 'Graves', 'Jimenez', 'Horton', 'Shelton', 'Barrett', "O'Brien", 'Castro', 'Sutton',
    'Gregory', 'McKinney', 'Lucas', 'Miles', 'Craig', 'Chambers', 'Holt', 'Lambert', 'Fletcher', 'Watts',
    'Bates', 'Hale', 'Rhodes', 'Pena', 'Beck', 'Newman', 'Haynes', 'McDaniel', 'Mendez', 'Bush', 'Vaughn',
    'Parks', 'Dawson', 'Santiago', 'Norris', 'Hardy', 'Love', 'Steele', 'Curry', 'Powers', 'Schultz',
    'Barker', 'Guzman', 'Page', 'Munoz', 'Ball', 'Keller', 'Chandler', 'Weber', 'Leonard', 'Walsh', 'Lyons',
    'Ramsey', 'Wolfe', 'Schneider', 'Mullins', 'Benson', 'Sharp', 'Bowen', 'Daniel', 'Barber', 'Cummings',
    'Hines', 'Baldwin', 'Griffith', 'Valdez', 'Hubbard', 'Salazar', 'Reeves', 'Warner', 'Stevenson',
    'Burgess', 'Santos', 'Tate', 'Cross', 'Garner', 'Mann', 'Mack', 'Moss', 'Thornton', 'Dennis', 'McGee',
    'Farmer', 'Delgado', 'Aguilar', 'Vega', 'Glover', 'Manning', 'Cohen', 'Harmon', 'Rodgers', 'Robbins',
    'Newton', 'Todd', 'Blair', 'Higgins', 'Ingram', 'Reese', 'Cannon', 'Strickland', 'Townsend', 'Potter',
    'Goodwin', 'Walton', 'Rowe', 'Hampton', 'Ortega', 'Patton', 'Swanson', 'Joseph', 'Francis', 'Goodman',
    'Yates', 'Becker', 'Erickson', 'Hodges', 'Conner', 'Adkins', 'Webster', 'Norman', 'Malone', 'Hammond',
    'Flowers', 'Cobb', 'Moody', 'Quinn', 'Blake', 'Maxwell', 'Pope', 'Floyd', 'Osborne', 'Paul', 'McCarthy',
    'Guerrero', 'Lindsey', 'Estrada', 'Sandoval', 'Gibbs', 'Tyler', 'Gross', 'Fitzgerald', 'Stokes', 'Doyle',
    'Sherman', 'Saunders', 'Wise', 'Colon', 'Gill', 'Alvarado', 'Greer', 'Padilla', 'Simon', 'Waters',
    'Nunez', 'Ballard', 'Schwartz', 'McBride', 'Houston', 'Klein', 'Pratt', 'Briggs', 'Parsons', 'Mclaughlin',
    'Zimmerman', 'French', 'Buchanan', 'Moran', 'Copeland', 'Roy', 'Pittman', 'Brady', 'McCormick',
    'Holloway', 'Brock', 'Poole', 'Frank', 'Logan', 'Owen', 'Bass', 'Marsh', 'Drake', 'Jefferson', 'Park',
    'Morton', 'Abbott', 'Sparks', 'Patrick', 'Norton', 'Huff', 'Clayton', 'Massey', 'Lloyd', 'Figueroa',
    'Carson', 'Bowers', 'Roberson', 'Barton', 'Lamb', 'Harrington', 'Casey', 'Boone', 'Clarke', 'Mathis',
    'Singleton', 'Wilkins', 'Cain', 'Bryan', 'Underwood', 'Hogan', 'McKenzie', 'Collier', 'Phelps', 'McGuire',
    'Allison', 'Bridges', 'Wilkerson', 'Nash', 'Summers', 'Atkins', 'Zdyrko', 'Navarro',
)
RETAIL_FIRSTS = (
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Charles', 'Joseph', 'Thomas',
    'Daniel', 'Paul', 'Mark', 'Donald', 'George', 'Kenneth', 'Steven', 'Edward', 'Brian', 'Ronald', 'Anthony',
    'Kevin', 'Jason', 'Matthew', 'Gary', 'Timothy', 'Jose', 'Larry', 'Jeffrey', 'Frank', 'Scott', 'Eric',
    'Stephen', 'Andrew', 'Raymond', 'Gregory', 'Joshua', 'Jerry', 'Dennis', 'Walter', 'Patrick', 'Peter',
    'Harold', 'Douglas', 'Henry', 'Carl', 'Arthur', 'Ryan', 'Roger', 'Joe', 'Juan', 'Jack', 'Albert',
    'Jonathan', 'Justin', 'Terry', 'Gerald', 'Keith', 'Samuel', 'Willie', 'Ralph', 'Lawrence', 'Nicholas',
    'Roy', 'Benjamin', 'Bruce', 'Brandon', 'Adam', 'Harry', 'Fred', 'Wayne', 'Billy', 'Steve', 'Louis',
    'Jeremy', 'Aaron', 'Randy', 'Howard', 'Eugene', 'Carlos', 'Russell', 'Bobby', 'Victor', 'Martin',
    'Ernest', 'Phillip', 'Todd', 'Jesse', 'Craig', 'Alan', 'Shawn', 'Clarence', 'Sean', 'Philip', 'Chris',
    'Johnny', 'Earl', 'Jimmy', 'Antonio', 'Danny', 'Bryan', 'Tony', 'Luis', 'Mike', 'Stanley', 'Leonard',
    'Nathan', 'Dale', 'Manuel', 'Rodney', 'Curtis', 'Norman', 'Allen', 'Marvin', 'Vincent', 'Glenn',
    'Jeffery', 'Travis', 'Jeff', 'Chad', 'Jacob', 'Lee', 'Melvin', 'Alfred', 'Kyle', 'Francis', 'Bradley',
    'Herbert', 'Frederick', 'Ray', 'Joel', 'Edwin', 'Don', 'Eddie', 'Ricky', 'Troy', 'Randall', 'Barry',
    'Alexander', 'Bernard', 'Mario', 'Leroy', 'Francisco', 'Marcus', 'Micheal', 'Theodore', 'Clifford',
    'Miguel', 'Oscar', 'Jay', 'Jim', 'Tom', 'Calvin', 'Alex', 'Jon', 'Ronnie', 'Bill', 'Lloyd', 'Tommy',
    'Leon', 'Derek', 'Warren', 'Darrell', 'Jerome', 'Floyd', 'Leo', 'Alvin', 'Tim', 'Wesley', 'Gordon',
    'Dean', 'Greg', 'Dustin', 'Pedro', 'Derrick', 'Dan', 'Lewis', 'Zachary', 'Corey', 'Herman', 'Maurice',
    'Vernon', 'Roberto', 'Clyde', 'Glen', 'Hector', 'Shane', 'Ricardo', 'Sam', 'Rick', 'Lester', 'Brent',
    'Ramon', 'Charlie', 'Tyler', 'Gilbert', 'Gene', 'Marc', 'Reginald', 'Ruben', 'Brett', 'Angel',
    'Nathaniel', 'Rafael', 'Leslie', 'Edgar', 'Milton', 'Raul', 'Ben', 'Chester', 'Cecil', 'Duane',
    'Franklin', 'Andre', 'Elmer', 'Brad', 'Gabriel', 'Ron', 'Mitchell', 'Roland', 'Arnold', 'Harvey', 'Jared',
    'Adrian', 'Karl', 'Cory', 'Claude', 'Erik', 'Darryl', 'Jamie', 'Neil', 'Jessie', 'Christian', 'Javier',
    'Fernando', 'Clinton', 'Ted', 'Mathew', 'Tyrone', 'Darren', 'Lonnie', 'Lance', 'Cody', 'Julio', 'Kelly',
    'Kurt', 'Allan', 'Nelson', 'Guy', 'Clayton', 'Hugh', 'Max', 'Dwayne', 'Dwight', 'Armando', 'Felix',
    'Jimmie', 'Everett', 'Jordan', 'Ian', 'Wallace', 'Ken', 'Bob', 'Jaime', 'Casey', 'Alfredo', 'Alberto',
    'Dave', 'Ivan', 'Johnnie', 'Sidney', 'Byron', 'Julian', 'Isaac', 'Morris', 'Clifton', 'Willard', 'Daryl',
    'Ross', 'Virgil', 'Andy', 'Marshall', 'Salvador', 'Perry', 'Kirk', 'Sergio', 'Marion', 'Tracy', 'Seth',
    'Kent', 'Terrance', 'Rene', 'Eduardo', 'Terrence', 'Enrique', 'Freddie', 'Wade', 'Austin', 'Stuart',
    'Fredrick', 'Arturo', 'Alejandro', 'Jackie', 'Joey', 'Nick', 'Luther', 'Wendell', 'Jeremiah', 'Evan',
    'Julius', 'Dana', 'Donnie', 'Otis', 'Shannon', 'Trevor', 'Oliver', 'Luke', 'Homer', 'Gerard', 'Doug',
    'Kenny', 'Hubert', 'Angelo', 'Shaun', 'Lyle', 'Matt', 'Lynn', 'Alfonso', 'Orlando', 'Rex', 'Carlton',
    'Ernesto', 'Cameron', 'Neal', 'Pablo', 'Lorenzo', 'Omar', 'Wilbur', 'Blake', 'Grant', 'Horace',
    'Roderick', 'Kerry', 'Abraham', 'Willis', 'Rickey', 'Jean', 'Ira', 'Andres', 'Cesar', 'Johnathan',
    'Malcolm', 'Rudolph', 'Damon', 'Kelvin', 'Rudy', 'Preston', 'Alton', 'Archie', 'Marco', 'Wm', 'Pete',
    'Randolph', 'Garry', 'Geoffrey', 'Jonathon', 'Felipe', 'Bennie', 'Gerardo', 'Ed', 'Dominic', 'Robin',
    'Loren', 'Delbert', 'Colin', 'Guillermo', 'Earnest', 'Lucas', 'Benny', 'Noel', 'Spencer', 'Rodolfo',
    'Myron', 'Edmund', 'Garrett', 'Salvatore', 'Cedric', 'Lowell', 'Gregg', 'Sherman', 'Wilson', 'Devin',
    'Sylvester', 'Roosevelt', 'Jermaine', 'Forrest', 'Wilbert', 'Leland', 'Simon', 'Guadalupe', 'Clark',
    'Irving', 'Carroll', 'Bryant', 'Owen', 'Rufus', 'Woodrow', 'Sammy', 'Kristopher', 'Mack', 'Levi',
    'Marcos', 'Jake', 'Lionel', 'Marty', 'Taylor', 'Ellis', 'Dallas', 'Clint', 'Nicolas', 'Laurence',
    'Ismael', 'Orville', 'Drew', 'Jody', 'Ervin', 'Dewey', 'Al', 'Wilfred', 'Josh', 'Hugo', 'Ignacio',
    'Caleb', 'Tomas', 'Sheldon', 'Erick', 'Frankie', 'Stewart', 'Doyle', 'Darrel', 'Rogelio', 'Terence',
    'Alonzo', 'Elias', 'Bert', 'Elbert', 'Ramiro', 'Conrad', 'Pat', 'Noah', 'Grady', 'Phil', 'Cornelius',
    'Lamar', 'Clay', 'Percy', 'Dexter', 'Bradford', 'Merle', 'Darin', 'Amos', 'Terrell', 'Moses', 'Irvin',
    'Saul', 'Roman', 'Darnell', 'Randal', 'Tommie', 'Timmy', 'Darrin', 'Winston', 'Brendan', 'Toby', 'Van',
    'Abel', 'Dominick', 'Boyd', 'Courtney', 'Jan', 'Elijah', 'Cary', 'Domingo', 'Abe', 'Stan',
)


class ProspectNamesError(ValueError):
    """The prospect-names patch cannot proceed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProspectNamesError(message)


def _u32(body: bytes, off: int) -> int:
    return struct.unpack_from("<I", body, off)[0]


def _s32(body: bytes, off: int) -> int:
    return struct.unpack_from("<i", body, off)[0]


def encoded_size(name: str) -> int:
    """Bytes a name costs in the pool: UTF-16LE plus the terminator."""

    return (len(name) + 1) * 2


# --------------------------------------------------------------------------------------------- csv
@dataclass(frozen=True)
class NameRow:
    index: int
    first: str
    last: str

    @property
    def retained(self) -> bool:
        """The surname is the recorded one at this index: its audio id keeps meaning."""

        return self.last == RETAIL_LASTS[self.index]


def validate_name(value: str, label: str) -> str:
    text = (value or "").strip()
    _require(bool(text), f"{label}: empty name (a null pool string crashes the generator)")
    _require(text.isascii(), f"{label}: {text!r} is not ASCII")
    _require(len(text) <= MAX_NAME_CHARS, f"{label}: {text!r} is longer than {MAX_NAME_CHARS} characters")
    _require(text[0].isalpha(), f"{label}: {text!r} must start with a letter")
    _require(all(c.isalpha() or c in NAME_PUNCTUATION for c in text),
             f"{label}: {text!r} may only use letters and {NAME_PUNCTUATION!r}")
    return text


def read_csv(text: str) -> list[NameRow]:
    """Parse a name-pool CSV: ``#`` comment lines allowed; columns ``first,last``; ``index`` optional
    (rows are index 0..484 in file order without it, and must cover 0..484 exactly once with it)."""

    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    _require(bool(lines), "the CSV has no rows")
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    missing = [c for c in CSV_COLUMNS if c not in fields]
    _require(not missing, f"the CSV lacks the columns {missing}")
    has_index = "index" in fields
    rows: list[NameRow] = []
    seen: set[int] = set()
    for k, item in enumerate(reader):
        item = {str(key).strip().lower(): value for key, value in item.items() if key is not None}
        label = f"row {k + 1}"
        if has_index:
            raw = str(item.get("index") or "").strip()
            try:
                index = int(raw)
            except ValueError as exc:
                raise ProspectNamesError(f"{label}: bad index {raw!r}") from exc
            _require(0 <= index < POOL_COUNT, f"{label}: index {index} is outside 0..{POOL_COUNT - 1}")
            _require(index not in seen, f"{label}: index {index} appears twice")
        else:
            index = k
        seen.add(index)
        rows.append(NameRow(index=index, first=validate_name(str(item.get("first") or ""), f"{label} first"),
                            last=validate_name(str(item.get("last") or ""), f"{label} last")))
    _require(len(rows) == POOL_COUNT, f"the CSV has {len(rows)} rows, the pool holds exactly {POOL_COUNT}")
    rows.sort(key=lambda r: r.index)
    return rows


def load_rows(source: Path | str | None = "modern") -> tuple[list[NameRow], dict[str, str]]:
    """The shipped CSV (``"modern"``/None/``""``, pinned) or a user file."""

    if source in (None, "", "modern"):
        _require(SHIPPED_CSV.is_file(), f"the built-in modern name list is missing: {SHIPPED_CSV}")
        data = SHIPPED_CSV.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        _require(not SHIPPED_CSV_SHA256 or digest == SHIPPED_CSV_SHA256, "the built-in modern name CSV does not match its pin")
        return read_csv(data.decode("utf-8")), {"source": "modern", "path": str(SHIPPED_CSV), "sha256": digest}
    path = Path(source).expanduser()
    _require(path.is_file(), f"prospect names CSV not found: {path}")
    data = path.read_bytes()
    return read_csv(data.decode("utf-8-sig")), {"source": "custom", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


# --------------------------------------------------------------------------------------------- layout
@dataclass(frozen=True)
class Layout:
    rows: tuple[NameRow, ...]
    strings: bytes              # the BUDGET-byte span (zero padded)
    array: bytes                # the ARRAY_SIZE-byte entry array
    boundary: int               # body offset where the replacement surnames begin
    retained: tuple[int, ...]   # indices whose surname keeps its recorded call-out
    replaced: tuple[int, ...]
    bytes_used: int
    log: tuple[str, ...]

    @property
    def spare(self) -> int:
        return BUDGET - self.bytes_used


def plan_layout(rows: Sequence[NameRow]) -> Layout:
    """Where every string and pointer goes: retained surnames first (index order), the boundary, the
    replacement surnames, then every first name.  Deterministic in the rows alone."""

    _require(len(rows) == POOL_COUNT and [r.index for r in rows] == list(range(POOL_COUNT)), "rows must be index 0..484 in order")
    span = bytearray(BUDGET)
    cursor = STRINGS_START
    first_off: dict[int, int] = {}
    last_off: dict[int, int] = {}

    def put(text: str) -> int:
        nonlocal cursor
        encoded = text.encode("utf-16-le") + b"\0\0"
        at = cursor
        _require(at + len(encoded) <= STRINGS_END,
                 f"the names need more than the pool's {BUDGET} bytes (shorten some names)")
        span[at - STRINGS_START: at - STRINGS_START + len(encoded)] = encoded
        cursor += len(encoded)
        return at

    retained = tuple(r.index for r in rows if r.retained)
    replaced = tuple(r.index for r in rows if not r.retained)
    for r in rows:
        if r.retained:
            last_off[r.index] = put(r.last)
    boundary = cursor
    for r in rows:
        if not r.retained:
            last_off[r.index] = put(r.last)
    for r in rows:
        first_off[r.index] = put(r.first)
    array = bytearray(ARRAY_SIZE)
    for r in rows:
        field = ARRAY_OFF + r.index * 8
        struct.pack_into("<ii", array, r.index * 8, first_off[r.index] - field + 1, last_off[r.index] - (field + 4) + 1)
    log: list[str] = []
    for r in rows:
        if r.retained:
            log.append(f"{r.index:3d}: last {r.last!r} kept (audio {RETAIL_AUDIO_BASE + r.index})")
        else:
            log.append(f"{r.index:3d}: last {RETAIL_LASTS[r.index]!r} -> {r.last!r} (announced by number)")
        if r.first != RETAIL_FIRSTS[r.index]:
            log.append(f"{r.index:3d}: first {RETAIL_FIRSTS[r.index]!r} -> {r.first!r}")
    return Layout(rows=tuple(rows), strings=bytes(span), array=bytes(array), boundary=boundary, retained=retained,
                  replaced=replaced, bytes_used=cursor - STRINGS_START, log=tuple(log))


def layout_for(source: Path | str | None = "modern") -> Layout:
    rows, _prov = load_rows(source)
    return plan_layout(rows)


# --------------------------------------------------------------------------------------------- pool
@dataclass(frozen=True)
class Pool:
    entries: tuple[tuple[int, int], ...]    # (first offset, last offset) per index
    firsts: tuple[str, ...]
    lasts: tuple[str, ...]


def _utf16(body: bytes, off: int) -> str:
    _require(STRINGS_START <= off < STRINGS_END and not off & 1, f"pool string pointer 0x{off:x} is outside the span")
    end = off
    while True:
        _require(end + 2 <= STRINGS_END, f"pool string at 0x{off:x} is not terminated inside the span")
        if body[end: end + 2] == b"\0\0":
            break
        end += 2
    _require(end > off, f"pool string at 0x{off:x} is empty")
    return body[off:end].decode("utf-16-le")


def header_ok(body: bytes) -> bool:
    return (len(body) == BODY_SIZE and body[0x0C:0x10] == b"ROST" and _u32(body, HEADER_COUNT_OFF) == POOL_COUNT
            and HEADER_ARRAY_OFF + _s32(body, HEADER_ARRAY_OFF) - 1 == ARRAY_OFF)


def parse_pool(body: bytes) -> Pool:
    """Decode the pool; raises when the count, the array or any string is not what the game expects."""

    _require(header_ok(body), "the roster's name pool header is not retail-shaped (count 485, array at 0x72FB4)")
    entries: list[tuple[int, int]] = []
    firsts: list[str] = []
    lasts: list[str] = []
    for i in range(POOL_COUNT):
        field = ARRAY_OFF + i * 8
        first = field + _s32(body, field) - 1
        last = field + 4 + _s32(body, field + 4) - 1
        firsts.append(_utf16(body, first))
        lasts.append(_utf16(body, last))
        entries.append((first, last))
    return Pool(entries=tuple(entries), firsts=tuple(firsts), lasts=tuple(lasts))


def pool_digest(body: bytes) -> str:
    h = hashlib.sha256(body[HEADER_COUNT_OFF: HEADER_ARRAY_OFF + 4])
    h.update(body[ARRAY_OFF: ARRAY_OFF + ARRAY_SIZE])
    h.update(body[STRINGS_START: STRINGS_END])
    return h.hexdigest()


def body_status(body: bytes) -> str:
    """retail | applied (the shipped CSV) | custom (a well-formed rewritten pool) | foreign."""

    try:
        if not header_ok(body):
            return "foreign"
    except struct.error:
        return "foreign"
    digest = pool_digest(body)
    if digest == RETAIL_POOL_SHA256:
        return "retail"
    if SHIPPED_POOL_SHA256 and digest == SHIPPED_POOL_SHA256:
        return "applied"
    try:
        parse_pool(body)
    except (ProspectNamesError, struct.error, UnicodeDecodeError):
        return "foreign"
    return "custom"


def boundary_range(body: bytes) -> tuple[int, int]:
    """``(lo, hi)``: every boundary the executable cave may carry for this pool.  A surname that equals
    the recorded one at its index must lie below the boundary, every other surname at or above it."""

    pool = parse_pool(body)
    lo, hi = STRINGS_START, STRINGS_END
    for i, (_first, last) in enumerate(pool.entries):
        if pool.lasts[i] == RETAIL_LASTS[i]:
            lo = max(lo, last + encoded_size(pool.lasts[i]))
        else:
            hi = min(hi, last)
    _require(lo <= hi, "the pool mixes retained and replacement surnames: no boundary separates them")
    return lo, hi


def apply_body(body: bytes, rows: Sequence[NameRow]) -> tuple[bytes, dict[str, Any]]:
    """A new body with the pool rewritten from ``rows``; only the entry array and the string span change."""

    _require(header_ok(body), "the roster's name pool header is not retail-shaped; refusing")
    layout = plan_layout(rows)
    out = bytearray(body)
    out[ARRAY_OFF: ARRAY_OFF + ARRAY_SIZE] = layout.array
    out[STRINGS_START: STRINGS_END] = layout.strings
    result = bytes(out)
    changed = [i for i in range(len(result)) if result[i] != body[i]]
    stray = [i for i in changed if not (ARRAY_OFF <= i < ARRAY_OFF + ARRAY_SIZE or STRINGS_START <= i < STRINGS_END)]
    _require(not stray, f"rewrite touched bytes outside the pool: {[hex(i) for i in stray[:5]]}")
    pool = parse_pool(result)
    _require(pool.firsts == tuple(r.first for r in rows) and pool.lasts == tuple(r.last for r in rows), "pool read-back differs")
    for i in layout.retained:
        _require(pool.entries[i][1] < layout.boundary, f"retained surname {i} landed above the boundary")
    for i in layout.replaced:
        _require(pool.entries[i][1] >= layout.boundary, f"replacement surname {i} landed below the boundary")
    return result, {"boundary": layout.boundary, "retained": len(layout.retained), "replaced": len(layout.replaced),
                    "bytes_before": BUDGET, "bytes_used": layout.bytes_used, "budget": BUDGET, "spare": layout.spare,
                    "pool_sha256": pool_digest(result), "log": list(layout.log)}


# --------------------------------------------------------------------------------------------- image (pool half)
def resource_status(resource: bytes) -> str:
    if len(resource) != _rost.RESOURCE_SIZE or resource[:4] != b"ROST" or _u32(resource, 4) != BODY_SIZE or _u32(resource, 8) != BODY_SIZE:
        return "foreign"
    return body_status(resource[RESOURCE_HEADER_SIZE:])


def _read_resource(path: Path | str) -> bytes:
    with _rost._outer_image()(path) as archive:
        entry = _rost._entry(archive)
        return archive.read(entry.virtual_offset, entry.size)


def status(path: Path | str) -> str:
    """The pool half: retail | applied | custom | foreign for a disc image or a loose pack folder."""

    return resource_status(_read_resource(path))


def apply(path: Path | str, source: Path | str | None = "modern", *,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Rewrite the name pool of the main roster in the disc image at ``path`` (a COPY)."""

    say = progress or (lambda _m: None)
    rows, provenance = load_rows(source)
    layout = plan_layout(rows)
    with _rost._outer_image()(path, writable=True) as archive:
        entry = _rost._entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        state = resource_status(before)
        body = before[RESOURCE_HEADER_SIZE:]
        if state in ("applied", "custom"):
            same = (body[ARRAY_OFF: ARRAY_OFF + ARRAY_SIZE] == layout.array and body[STRINGS_START: STRINGS_END] == layout.strings)
            _require(same, f"the roster's name pool is already rewritten ({state}) with other names; refusing")
            return {"status": state, "already_applied": True, "outer_index": ROST_OUTER_INDEX, "boundary": layout.boundary,
                    "retained": len(layout.retained), "replaced": len(layout.replaced), **provenance}
        _require(state == "retail", f"the roster's name pool is {state}, not retail; refusing")
        say("Rewriting the generated-player name pool")
        patched, receipt = apply_body(body, rows)
        replacement = before[:RESOURCE_HEADER_SIZE] + patched
        say("Writing the roster resource")
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the roster resource")
        check = archive.read(entry.virtual_offset, entry.size)
        _require(check == replacement, "read-back of the roster resource differs")
    return {"status": resource_status(replacement), "outer_index": ROST_OUTER_INDEX, "virtual_offset": f"0x{entry.virtual_offset:x}",
            "rows": len(rows), **provenance, **receipt}


# --------------------------------------------------------------------------------------------- executable half
HOOK_VA = 0x002BE7B8
RETAIL_HOOK = bytes.fromhex("81c254240000")                   # add edx,0x2454
HOOK_SIZE = len(RETAIL_HOOK)
HOOK_BEFORE_VA = 0x002BE7B5
RETAIL_HOOK_BEFORE = bytes.fromhex("8b4804")                  # mov ecx,[eax+4]: the entry's surname pointer
HOOK_AFTER_VA = HOOK_VA + HOOK_SIZE
RETAIL_HOOK_AFTER = bytes.fromhex("668956048b542410894e14528bd58bcee8ad7fe2ff")   # mov [esi+4],dx ... call FUN_000e6780
HOOK_RESUME_VA = HOOK_AFTER_VA                                # `mov [esi+4],dx`
HOST_VA = 0x000B4A70                                          # the tail of the dead FUN_000b4a60 (the penalties stub owns 0xB4A60..0xB4A70)
HOST_SIZE = 27
RETAIL_HOST = bytes.fromhex("240c2bce4957c1e90281e1feffff3f8d7e088916894604f3a55f5e")
HOST_AFTER_VA = HOST_VA + HOST_SIZE
RETAIL_HOST_AFTER = bytes.fromhex("c208009090")               # the routine's `ret 8` and nop padding up to 0xB4A90
assert len(RETAIL_HOST) == HOST_SIZE
PATCHED_HOOK = b"\xe8" + struct.pack("<i", HOST_VA - (HOOK_VA + 5)) + b"\x90"
BOUNDARY_IMM_OFFSET = 6                                       # the imm32 of `add eax,imm32` inside the cave


def cave_bytes(boundary: int) -> bytes:
    """The 27-byte cave with ``boundary`` (a body offset inside the string span) baked in."""

    _require(STRINGS_START <= boundary <= STRINGS_END, f"boundary 0x{boundary:x} is outside the pool's string span")
    code = (b"\xa1" + struct.pack("<I", ROSTER_GLOBAL)              # mov eax,[0xB72918]
            + b"\x05" + struct.pack("<I", boundary - OBJ_OFF)       # add eax,boundary-0x40
            + b"\x3b\xc8"                                           # cmp ecx,eax
            + b"\x73\x07"                                           # jae replacement
            + RETAIL_HOOK                                           # add edx,0x2454
            + b"\xc3"                                               # ret
            + b"\xba" + struct.pack("<I", NUMBER_AUDIO_ID)          # replacement: mov edx,0x238C
            + b"\xc3")                                              # ret
    assert len(code) == HOST_SIZE
    return code


def _cave_boundary(host: bytes) -> int | None:
    """The boundary a host span carries, or None when it is not this cave."""

    if len(host) != HOST_SIZE:
        return None
    boundary = struct.unpack_from("<I", host, BOUNDARY_IMM_OFFSET)[0] + OBJ_OFF
    if not STRINGS_START <= boundary <= STRINGS_END:
        return None
    return boundary if host == cave_bytes(boundary) else None


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise ProspectNamesError(f"VA 0x{va:x} is in no section")


def _spans(payload: bytes) -> dict[str, tuple[int, int]]:
    return {"hook": (_offset(payload, HOOK_VA), HOOK_SIZE), "host": (_offset(payload, HOST_VA), HOST_SIZE),
            "hook_before": (_offset(payload, HOOK_BEFORE_VA), len(RETAIL_HOOK_BEFORE)),
            "hook_after": (_offset(payload, HOOK_AFTER_VA), len(RETAIL_HOOK_AFTER)),
            "host_after": (_offset(payload, HOST_AFTER_VA), len(RETAIL_HOST_AFTER))}


def xbe_status(payload: bytes) -> str:
    """The executable half: retail | applied | foreign (the cave may carry any boundary)."""

    try:
        spans = _spans(payload)
    except (ProspectNamesError, ValueError, struct.error):
        return "foreign"
    for key, retail in (("hook_before", RETAIL_HOOK_BEFORE), ("hook_after", RETAIL_HOOK_AFTER), ("host_after", RETAIL_HOST_AFTER)):
        off, size = spans[key]
        if payload[off: off + size] != retail:
            return "foreign"
    hook_off, _ = spans["hook"]
    host_off, _ = spans["host"]
    hook, host = payload[hook_off: hook_off + HOOK_SIZE], payload[host_off: host_off + HOST_SIZE]
    if hook == RETAIL_HOOK and host == RETAIL_HOST:
        return "retail"
    if hook == PATCHED_HOOK and _cave_boundary(host) is not None:
        return "applied"
    return "foreign"


def xbe_boundary(payload: bytes) -> int | None:
    """The boundary baked into an applied executable, else None."""

    if xbe_status(payload) != "applied":
        return None
    host_off, _ = _spans(payload)["host"]
    return _cave_boundary(payload[host_off: host_off + HOST_SIZE])


def xbe_apply(payload: bytes, boundary: int) -> tuple[bytes, Mapping[str, object]]:
    """Hook the generator and host the cave with ``boundary`` baked in; the .text digest is recomputed."""

    state = xbe_status(payload)
    if state == "applied":
        _require(xbe_boundary(payload) == boundary,
                 f"the executable already carries the prospect-names cave with boundary 0x{xbe_boundary(payload):x}, not 0x{boundary:x}")
        return payload, {"already_applied": True, "changed_bytes": 0, "boundary": boundary}
    _require(state == "retail", f"prospect-names sites are {state}, not retail")
    cave = cave_bytes(boundary)
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, va, after in (("hook", HOOK_VA, PATCHED_HOOK), ("cave", HOST_VA, cave)):
        off = _offset(payload, va)
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(xbe_status(patched) == "applied" and xbe_boundary(patched) == boundary, "post-apply verification failed")
    return patched, {"edits": edits, "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b),
                     "sections_repinned": sorted(touched), "cave_va": f"0x{HOST_VA:x}", "cave_bytes": cave.hex(),
                     "hook_va": f"0x{HOOK_VA:x}", "boundary": boundary, "number_audio_id": NUMBER_AUDIO_ID}


# --------------------------------------------------------------------------------------------- both halves
def combined_status(pool_state: str, xbe_state: str, baked_boundary: int | None, boundary_bounds: tuple[int, int] | None) -> str:
    """retail | applied | applied-custom | partial | foreign for a disc image, from both halves.

    ``applied`` needs the executable cave AND a rewritten pool whose layout agrees with the baked
    boundary; one half without the other is ``partial`` (never ``applied``)."""

    if pool_state == "retail" and xbe_state == "retail":
        return "retail"
    if xbe_state == "applied" and pool_state in ("applied", "custom"):
        if baked_boundary is None or boundary_bounds is None or not (boundary_bounds[0] <= baked_boundary <= boundary_bounds[1]):
            return "foreign"
        if pool_state == "applied":
            return "applied" if baked_boundary == SHIPPED_BOUNDARY else "foreign"
        return "applied-custom"
    if pool_state in ("retail", "applied", "custom") and xbe_state in ("retail", "applied"):
        return "partial"
    return "foreign"


def image_status(path: Path | str) -> str:
    """Both halves of a disc image (default.xbe through its directory, the pool through pack 0)."""

    from . import nfl2k5_throw_tuning as tt          # lazy: nfl2k5_throw_tuning imports this module
    from . import platform_compat
    import os

    path = Path(path)
    try:
        resource = _read_resource(path)
        pool_state = resource_status(resource)
    except Exception:  # noqa: BLE001
        return "foreign"
    xbe_state, baked, bounds = "foreign", None, None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            off, length = tt.image_xbe_extent(fd, os.fstat(fd).st_size)
            payload = platform_compat.pread(fd, length, off)
        finally:
            os.close(fd)
        xbe_state = xbe_status(payload)
        baked = xbe_boundary(payload)
        if pool_state in ("applied", "custom"):
            bounds = boundary_range(resource[RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001
        pass
    return combined_status(pool_state, xbe_state, baked, bounds)


__all__ = ["ARRAY_OFF", "ARRAY_SIZE", "ATTRIBUTION", "BODY_SIZE", "BUDGET", "CSV_COLUMNS", "HOOK_SIZE", "HOOK_VA",
           "HOST_SIZE", "HOST_VA", "Layout", "MAX_NAME_CHARS", "NUMBER_AUDIO_ID", "NameRow", "OBJ_OFF", "PATCHED_HOOK",
           "POOL_COUNT", "Pool", "ProspectNamesError", "RETAIL_AUDIO_BASE", "RETAIL_FIRSTS", "RETAIL_HOOK",
           "RETAIL_HOST", "RETAIL_LASTS", "RETAIL_POOL_SHA256", "ROSTER_GLOBAL", "ROST_OUTER_INDEX", "SHIPPED_BOUNDARY",
           "SHIPPED_CSV", "SHIPPED_CSV_SHA256", "SHIPPED_POOL_SHA256", "STRINGS_END", "STRINGS_START", "apply",
           "apply_body", "body_status", "boundary_range", "cave_bytes", "combined_status", "encoded_size", "header_ok",
           "image_status", "layout_for", "load_rows", "parse_pool", "plan_layout", "pool_digest", "read_csv",
           "resource_status", "status", "validate_name", "xbe_apply", "xbe_boundary", "xbe_status"]

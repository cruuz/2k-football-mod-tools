"""MyCareer, any position, on native Franchise. EXPERIMENTAL / UNWITNESSED.

The setup service edits one existing prospect at the chosen position through
the roster writer. It requires a real draft-stage save; it never synthesizes
an offseason transition. The executable carries a sealed, pointer-free setup,
while a bounded native checkpoint journal pairs later MyCareer state with the
exact Franchise bytes. The Game Modes row that launched First Person Football
becomes the MyCareer action. No VIP field, roster padding, retail cave or
save-format extension is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import uuid
import zipfile

from . import nfl2k5_my_career_code as assembly
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_my_career"
CODE_SIZE, DATA_SIZE = 16384, 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
SCHEMA = "nfl2k5_my_career/v2"
MAGIC = b"MCQB0001"
STATE_SIZE, LEDGER_OFFSET, LEDGER_LIMIT = 1280, 256, 64
RECIPE_OFFSET, POSITION_OFFSET, STARTER_LOCK_OFFSET, STARTER_DONE_OFFSET = 96, 96 + 0x35, 180, 184
SAVE_SIZE = 720044
POSITION_COUNT = 17
PENDING, PROSPECT, ACTIVE, UNSIGNED, RESERVE, LOST = range(1, 7)
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: Franchise controls a team and Game Modes offers First Person Football. "
    "Patch: the First Person Football row becomes MyCareer. Enter the draft or create an undrafted free agent "
    "(the game's own Create Player screen, then a visible list of all 32 clubs), live in a visible Apartment with Play "
    "next game, Practice, MyPlayer, Save and Quit, and save the career inline. Play opens your next fixture after any "
    "required league processing; a game you quit stays playable. MyPlayer gets the retail indicator, receiver icons and "
    "play art. Off the field the CPU plays at normal speed and a footer says so; Supersim is not available. With Franchise "
    "Auto Save installed and on, completed results save to the slot chosen by a manual Save or Load. Draft entry "
    "advances the prior season, creates MyPlayer in the rookie class and lets the draft AI choose a club. "
    "Non-QB route, block and catch behavior remains unverified in play; native input behavior is retained. "
    "Senior Bowl preparation selects MyPlayer; its game is unavailable. Upgrades spend played-game XP with position caps. "
    "The Apartment shows the next fixture date. Rebuild older MyCareer executables from base. Experimental / Unwitnessed."
)
WITNESS_LIST = (
    "From Game Modes choose MyCareer, enter the draft, wait for league preparation and create MyPlayer.",
    "Save at Senior Bowl preparation; verify that the editor's default seed-1 selection includes MyPlayer.",
    "Complete the draft and verify both a drafted destination and an undrafted club choice, then cold reload.",
    "Earn XP by playing, cancel and confirm attribute purchases, reach a position cap, save and cold reload.",
    "Check the Apartment date and opponent before a bye, in preseason, and after a season rollover.",
    "Check the draft log, signing destination, roster identity, depth row and CPU roster decisions at the chosen position.",
    "At kickoff, snap, handoff, catch, interception, fumble, punt, PAT and overtime, input stays on MyPlayer.",
    "On the bench, injury, substitution and the other unit's plays, input reaches no replacement and the CPU keeps playing.",
    "Check what the sticks and buttons do for MyPlayer's position before the snap, during the play and after the whistle.",
    "Check CPU play selection, the other ten players and every GM shortcut and back path.",
    "Check Standard and Far tracking, sideline movement, replays and return to ordinary Franchise.",
    "Play every career-team fixture and simulate other fixtures through the normal schedule.",
    "Save, cold reload and replay a week: XP is credited once; test missing and damaged checkpoints.",
    "Check undrafted, unsigned, reserve, trade, release, retirement and a recycled roster slot.",
    "Finish a season, playoffs and offseason, then save and reload again.",
    "Confirm First Person Football still toggles from Franchise Settings.",
)
# Beta 65 evidence: tools/nfl2k5_my_career_position_evidence.py pins the
# native spans/tables; test_nfl2k5_my_career_position_inputs.py executes the
# input pipeline. Decoding a command is not proof of movement or animation.
# The same binder/Standard-Far camera ships for every group. No global FPF
# flag is borrowed and no unproved "Run your own routes" option is installed.
POSITION_CONTRACT = {
    "QB": (
        "proved: Noah reports QB play works; native pre-snap context 3, QB context 6 and carrier contexts 8/10; "
        "body-to-port restore 0x1565F0 -> 0x120880; three native QB templates",
        "hypothesis: snap, passing and scrambling remain reliable across all MyCareer formations and transitions; "
        "the new build still needs a play witness"),
    "RB": (
        "proved: HB/FB bind by identity; native phase walk 0x1569E0 assigns off-ball offense context 9 and "
        "carrier context 10; stick and off-ball command decode with FPF off; three native templates each",
        "hypothesis: pre-handoff stick overrides mesh-point AI, and a catch/handoff completes under that control; "
        "no body-specific human-back mode is proved; native behavior retained"),
    "WR": (
        "proved: native off-ball context 9 decodes stick and commands 0x67/0x68 outside FPF; "
        "0x18EC40 dispatches 0x67 to 0x18FAC0; carrier context 10; Speed/Hands/Balanced WR templates",
        "hypothesis: stick overrides route AI and a catch button completes the catch; FPF entry 0x2C1FC0 sets "
        "global 0xE5FFE4, not a proved per-receiver mode; run-your-own-routes option withheld"),
    "TE": (
        "proved: same native context 9 input/dispatch and carrier context 10 as WR; "
        "Catching/Blocking/Balanced TE templates; identity and camera remain on MyPlayer",
        "hypothesis: manual routes, catches and blocking animations work through every assignment; "
        "no safe body-specific FPF mode proved; native behavior retained"),
    "OL": (
        "proved: identity/camera binding and native context 9 stick/button decode also accept C/G/T; "
        "all nine native OL templates exist at 0x5561B8 + (3*position+variant)*0x74 and apply ratings",
        "hypothesis: steering changes locomotion or a button chooses pass-set/run-block; neither is proved. "
        "Ship existing MyPlayer camera with native blocking behavior; blocker-view auto-block is a witness target"),
    "DL": (
        "proved: DT/EDGE bind even when a different defender is requested; native context 11 after snap; "
        "engaged context 16 command 6 reaches 0x2324F0 and changes move state only in behavior 0x02000000; "
        "native DL templates, merged EDGE templates under pools",
        "hypothesis: alignment, rush and shed animations work in all plays; command/state proofs do not prove "
        "successful moves. Automatic/manual/transfer guards hold identity in bounded tests; live turnovers unwitnessed"),
    "LB": (
        "proved: LB and legacy OLB identity binding; native pre-snap 4/5 and post-snap 11/engaged 16 tables; "
        "switch guards retain the bound body; three LB templates; pools retires OLB from creation",
        "hypothesis: pre-snap shifts, coverage drops, blitz movement and shed animations respond as intended; "
        "no complete snapped-play witness at LB"),
    "DB": (
        "proved: CB/FS/SS identity binding; native pre-snap 4/5 and post-snap 11/engaged 16 command tables; "
        "switch guards retain the bound non-default defender; three templates per position",
        "hypothesis: alignment, coverage steering, swat and interception animations work as expected; "
        "complete catch/turnover sequences remain unwitnessed"),
    "K/P": (
        "proved: context 2 decodes kick commands; native 0x1891B0 returns CPU play-call ownership for K/P; "
        "binder detaches when MyPlayer has no active body; three native templates each",
        "hypothesis: rendered kick meter works in MyCareer; only-kicks field time is NOT established "
        "(formation/substitution assignments can differ); kick, punt, PAT and kickoff need witnesses"),
}


class MyCareerError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise MyCareerError(message)


def hash32(data, seed=0x811C9DC5):
    for value in data:
        seed = ((seed ^ value) * 0x01000193) & 0xFFFFFFFF
    return seed


def save_key(payload):
    require(len(payload) == SAVE_SIZE and payload[0x2E0:0x2E4] == b"ROST",
            "MyCareer needs a complete Franchise save")
    return hash32(payload), hash32(payload, 0x9E3779B9)


def seal_state(state):
    require(len(state) == STATE_SIZE, "MyCareer state must be 1280 bytes")
    out = bytearray(state)
    struct.pack_into("<I", out, 12, hash32(out[16:]))
    return bytes(out)


def validate_state(state, payload=None):
    require(isinstance(state, bytes) and len(state) == STATE_SIZE, "wrong MyCareer checkpoint length")
    require(state[:8] == MAGIC and struct.unpack_from("<I", state, 8)[0] == STATE_SIZE,
            "unsupported MyCareer checkpoint version")
    require(struct.unpack_from("<I", state, 12)[0] == hash32(state[16:]), "damaged MyCareer checkpoint")
    phase, index, port, camera = struct.unpack_from("<4I", state, 24)
    require(PENDING <= phase <= LOST and index < 4096 and port < 8 and camera < 2,
            "invalid MyCareer identity or preferences")
    require(any(state[40:56]), "MyPlayer creation token is missing")
    require(struct.unpack_from("<I", state, 60)[0] == 0, "checkpoint contains a runtime pointer")
    require(struct.unpack_from("<I", state, 56)[0] in (*range(32), 0xFFFFFFFF), "invalid MyPlayer club")
    require(struct.unpack_from("<I", state, 76)[0] <= 64, "MyCareer ledger count exceeds 64")
    require(struct.unpack_from("<I", state, 72)[0] < 64, "MyCareer ledger cursor exceeds 63")
    require(struct.unpack_from("<I", state, 64)[0] <= 1000000, "MyCareer XP exceeds its bound")
    require(all(struct.unpack_from("<I", state, off)[0] < 0x91000 for off in (84, 88, 92)),
            "MyPlayer name/college offsets escape the roster arena")
    require(all(struct.unpack_from("<I", state, recipe)[0] == struct.unpack_from("<I", state, identity)[0]
                for recipe, identity in ((96, 84), (112, 88), (116, 92))),
            "MyPlayer recipe pointer offsets differ from its identity")
    require(state[POSITION_OFFSET] < POSITION_COUNT, "MyPlayer position code is not one of the 17 retail codes")
    require(struct.unpack_from("<I", state, STARTER_LOCK_OFFSET)[0] <= 1
            and struct.unpack_from("<I", state, STARTER_DONE_OFFSET)[0] <= 1, "invalid MyPlayer starter lock flags")
    if payload is not None:
        require(struct.unpack_from("<2I", state, 16) == save_key(payload),
                "MyCareer checkpoint belongs to different Franchise bytes")
    return state


def checkpoint_name(payload):
    """A fixed 64-slot title journal, outside the game's signed save folders."""
    return f"MyCareer{save_key(payload)[0] & 63:02X}.dat"


def award_week(state, *, year, stage, week, fixture, committed, appeared):
    """Bounded weekly XP, with a monotonic watermark even after ring eviction.

    This ledger records participation, not invented performance statistics.
    Bye/bench/injury weeks receive zero. Only a committed fixture can advance it.
    """
    validate_state(state)
    require(type(committed) is bool and type(appeared) is bool, "XP outcomes must be booleans")
    require(all(type(x) is int for x in (year, stage, week, fixture)) and
            0 <= year <= 127 and 7 <= stage <= 9 and 0 <= week < 22 and 0 <= fixture < 17,
            "invalid MyCareer fixture key")
    key = 1 + (year << 16) + (stage << 12) + (week << 5) + fixture
    out = bytearray(state)
    total, watermark = struct.unpack_from("<2I", state, 64)
    # Count lives at +76; +72 is the ring cursor.
    cursor, count = struct.unpack_from("<2I", state, 72)
    if not committed or key <= watermark:
        return state, {"awarded": 0, "duplicate": key <= watermark, "committed": committed}
    phase = struct.unpack_from("<I", state, 24)[0]
    reward = 25 if appeared and phase == ACTIVE else 0
    total = min(1000000, total + reward)
    struct.pack_into("<4I", out, LEDGER_OFFSET + (cursor % LEDGER_LIMIT) * 16,
                     key, reward, total, int(appeared))
    struct.pack_into("<4I", out, 64, total, key, (cursor + 1) % LEDGER_LIMIT, min(count + 1, 64))
    return seal_state(out), {"awarded": reward, "duplicate": False, "committed": True, "key": key}


def position_of(state):
    """The MyPlayer position code sealed in a validated setup or checkpoint."""
    return validate_state(state)[POSITION_OFFSET]


def starter_lock_of(state):
    return bool(struct.unpack_from("<I", validate_state(state), STARTER_LOCK_OFFSET)[0])


def position_label(code):
    from . import nfl2k5_roster_records as rr
    return rr.position_name(code)


def position_group(code):
    from . import nfl2k5_roster_records as rr
    name = rr.position_name(code)
    for group, members in rr.POSITION_GROUPS.items():
        if name in members:
            return group
    raise MyCareerError(f"position {code} belongs to no group")


def describe_setup(state):
    state = validate_state(state)
    code = state[POSITION_OFFSET]
    proved, hypothesis = POSITION_CONTRACT[position_group(code)]
    return {"position": position_label(code), "position_code": code, "group": position_group(code),
            "starter_lock": starter_lock_of(state), "proved": proved, "hypothesis": hypothesis}


def read_setup(source):
    if source is None:
        return bytes(STATE_SIZE)
    if isinstance(source, bytes):
        return validate_state(source)
    if isinstance(source, (str, Path)):
        path = Path(source).resolve()
        require(path.stat().st_size <= 16384, "MyCareer setup exceeds 16 KiB")
        source = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(source, dict) and source.get("mode") == "MyCareer", "unsupported MyCareer setup")
    require(source.get("schema") != "nfl2k5_my_career/v1",
            "this MyCareer.json predates position choice; create MyPlayer again on the MyCareer page")
    require(set(source) == {"schema", "mode", "myplayer", "position", "state", "save_sha256"}
            and source["schema"] == SCHEMA, "unsupported MyCareer setup")
    require(isinstance(source["state"], str) and len(source["state"]) == STATE_SIZE * 2,
            "invalid MyCareer setup bytes")
    state = validate_state(bytes.fromhex(source["state"]))
    require(source["position"] == position_label(state[POSITION_OFFSET]),
            "MyCareer setup position label disagrees with its sealed state")
    return state


def position_choices(scheme="retail"):
    """Live position codes and labels for a picker; aliases never add rows."""
    from . import nfl2k5_roster_records as rr
    return tuple((code, rr.position_name(code, scheme), rr.position_long_name(code, scheme))
                 for code in rr.live_position_codes(scheme))


def templates_for(position, *, scheme="retail"):
    """All 51 native templates; pooled EDGE variants share the XBE writer's data."""
    from . import nfl2k5_roster_records as rr
    return rr.templates_for_position(position, scheme=scheme)


def prepare(payload, *, first, last, position=0, template=0, port=0, camera=0, starter_lock=True, token=None,
            scheme="retail"):
    """Prepare one existing prospect at the chosen position in a genuine draft save.

    Returns fixed-length save bytes, setup JSON and an exact receipt. Publication
    and EXTRA signing belong to prepare_save/SaveContainer. No team assignment.
    Every position takes one of three native templates or None to keep the
    generated ratings. The one_pool scheme hides OLB and uses EDGE templates.
    """
    from . import nfl2k5_roster_records as rr, nfl2k5_franchise_save as fs
    save_key(payload)
    require(payload[fs.SEASON_BLOCK + fs.S_MODE] == 2, "the save is not Franchise")
    # Retail stage table 0x515140: Combine is 4, Draft is 5, Signing is 6.
    require(payload[fs.SEASON_BLOCK + fs.S_STAGE] == 5, "MyCareer setup requires an existing NFL Draft stage save")
    code = rr.position_code(position)
    require(0 <= code < POSITION_COUNT, "choose one of the 17 retail positions")
    rr.check_position_code(code, scheme)
    choices = templates_for(code, scheme=scheme)
    require(template is None or (type(template) is int and 0 <= template < len(choices)),
            f"{rr.position_name(code)} offers {len(choices)} retail templates; choose one of them or None")
    require(type(port) is int and 0 <= port < 8 and type(camera) is int and camera in (0, 1)
            and type(starter_lock) is bool, "choose port 1..8, Standard/Far and a boolean starter lock")
    doc = rr.RosterDocument(payload, base=rr.find_block_base(payload))
    candidates = [p for p in doc.players if p.pool == "primary" and not p.teams and
                  p.offset not in doc.free_agents and p.record.get("position") == code and
                  p.record.get("player_type") & 0x10]
    require(bool(candidates), f"no unassigned eligible {rr.position_name(code)} prospect remains; "
            "regenerate through the game first or choose another position")
    player = candidates[0]
    before = bytes(payload[player.offset:player.offset + 84])
    doc.set_name(player, "first", first)
    doc.set_name(player, "last", last)
    if template is not None:
        rr.apply_template(player.record, choices[template])
    player.record.set("position", code)
    player.record.set("years_pro", 0)
    player.record.set("player_type", player.record.get("player_type") | 0x10)
    result = bytearray(doc.to_body())
    # Draft AI owns every club until the native destination is discovered.
    result[fs.SEASON_BLOCK + fs.S_USER_CONTROL:fs.SEASON_BLOCK + fs.S_USER_CONTROL + 34 * 4] = bytes(34 * 4)
    result = bytes(result)
    require(len(result) == len(payload), "MyCareer preparation changed the save span")
    reopened = rr.RosterDocument(result, base=rr.find_block_base(result))
    chosen = reopened.by_offset[player.offset]
    root = reopened.obj_base + rr.OBJ_OFF
    name_offsets = [reopened.rel(player.offset + field) - root for field in (0, 16, 20)]
    state = bytearray(STATE_SIZE)
    state[:8] = MAGIC
    struct.pack_into("<I", state, 8, STATE_SIZE)
    struct.pack_into("<2I", state, 16, *save_key(result))
    struct.pack_into("<4I", state, 24, PENDING, player.index, port, camera)
    creation = uuid.UUID(str(token)).bytes if token is not None else uuid.uuid4().bytes
    require(any(creation), "MyPlayer needs a nonzero creation token")
    state[40:56] = creation
    struct.pack_into("<I", state, 56, 0xFFFFFFFF)  # current club is discovered after the draft
    struct.pack_into("<3I", state, 84, *name_offsets)
    state[RECIPE_OFFSET:RECIPE_OFFSET + 84] = result[player.offset:player.offset + 84]
    # Serialized record pointers become root-relative integers in the recipe.
    for field, offset in zip((0, 16, 20), name_offsets):
        struct.pack_into("<I", state, RECIPE_OFFSET + field, offset)
    require(state[POSITION_OFFSET] == code, "MyPlayer recipe position disagrees with the chosen position")
    struct.pack_into("<2I", state, STARTER_LOCK_OFFSET, int(starter_lock), 0)
    state = seal_state(state)
    validate_state(state, result)
    setup = {"schema": SCHEMA, "mode": "MyCareer", "myplayer": chosen.display,
             "position": rr.position_name(code), "state": state.hex(),
             "save_sha256": hashlib.sha256(result).hexdigest()}
    receipt = {"mode": "MyCareer", "myplayer": chosen.display, "experimental": True,
               "runtime_witnessed": False, "pool": "primary", "index": player.index,
               "position": rr.position_name(code, scheme), "position_code": code,
               "position_scheme": rr.normalise_scheme(scheme),
               "position_group": position_group(code), "starter_lock": starter_lock,
               "contract": dict(zip(("proved", "hypothesis"), POSITION_CONTRACT[position_group(code)])),
               "token": str(uuid.UUID(bytes=creation)),
               "template": None if template is None else choices[template].label,
               "ratings": ("merged EDGE template" if template is not None and code == 16 and
                           rr.normalise_scheme(scheme) == "one_pool" else
                           "retail create-a-player template" if template is not None else "generated prospect ratings kept"),
               "record_offset": player.offset, "record_before": before.hex(),
               "record_after": result[player.offset:player.offset + 84].hex(),
               "changed_bytes": sum(a != b for a, b in zip(payload, result)),
               "before_sha256": hashlib.sha256(payload).hexdigest(),
               "after_sha256": setup["save_sha256"], "save_growth": 0,
               "class_count_before": sum(bool(p.record.get("player_type") & 0x10) for p in doc.players),
               "class_count_after": sum(bool(p.record.get("player_type") & 0x10) for p in reopened.players),
               "team_assignment": "normal draft", "witness_list": list(WITNESS_LIST)}
    return result, setup, receipt


def prepare_save(source, output, **options):
    """Publish a signed ZIP plus setup inside one atomic directory rename.

    The target must be new. Inputs and all SaveContainer handles close before
    publication. A setup never overwrites the source or partially publishes.
    """
    from . import nfl2k5_roster_records as rr
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists() and output.parent.is_dir(), "choose a new MyCareer output directory")
    # The shared save loader materializes small members, never a disc or pack.
    # Bound both compressed and expanded inputs before calling that loader.
    if source.is_file() and source.suffix.lower() == ".zip":
        require(source.stat().st_size <= 16 * 1024**2, "save ZIP exceeds 16 MiB")
        with zipfile.ZipFile(source) as archive:
            require(sum(item.file_size for item in archive.infolist()) <= 16 * 1024**2,
                    "expanded save exceeds 16 MiB")
    else:
        folder = source if source.is_dir() else source.parent
        require(sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) <= 16 * 1024**2,
                "save folder exceeds 16 MiB; choose the individual signed save folder")
    container = rr.SaveContainer.load(source)
    payload, setup, receipt = prepare(container.savegame, **options)
    with tempfile.TemporaryDirectory(prefix=".mycareer-", dir=output.parent) as temp:
        directory = Path(temp).resolve() / "result"
        directory.mkdir()
        signed = container.write(directory / "MyCareer.zip", payload)
        (directory / "MyCareer.json").write_text(json.dumps(setup, indent=2) + "\n", encoding="utf-8", newline="\n")
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
        require(read_setup(directory / "MyCareer.json") == read_setup(setup), "MyCareer setup readback failed")
        os.replace(directory, output)
    return {**receipt, "output": str(output), "signed": signed["signed"]}


# Whole displaced instructions, pinned to the USA executable. All handlers are
# outside retail sections. The assembler explicitly replays any relative call.
HOOKS = (
    ("attach", 0x156246, "8bc55dc20400", "attach", 0xE9),
    ("copy", 0xC3C60, "8a811c010000", "copy", 0xE9),
    ("reset", 0x156640, "568bf1e8c8d1f0ff", "reset", 0xE9),
    ("assign", 0x156870, "8b44240483ec08", "assign", 0xE9),
    ("automatic", 0x1A7970, "538bd98a432c", "automatic", 0xE9),
    ("team_reset", 0x1A77A0, "578b790485ff", "team_reset", 0xE9),
    ("manual", 0x1A85E0, "56578bf98b470c", "manual", 0xE9),
    ("transfer", 0x1A70E0, "8b4424048b4c2408", "transfer", 0xE9),
    ("generation", 0x2BE946, "e9b5ffffff", "generation", 0xE9),
    ("slot_generation", 0x2BE923, "e8c8fdffff", "overwrite_guard", 0xE8),
    ("draft", 0x325B90, "81ec10010000", "draft", 0xE9),
    ("sim", 0xC7A20, "81ec10010000", "sim", 0xE9),
    ("navigation", 0xC6D10, "56578bf28bf9", "navigation", 0xE9),
    ("cpu_management", 0xC4D50, "e84bffffff", "cpu_management", 0xE9),
    ("camera", 0xA5490, "53565733ff", "camera", 0xE9),
    ("camera_focus", 0xA5947, "e8149efbff", "camera_focus", 0xE8),
    ("screen_dispatch", 0x6E390, "568bf183be0001000020", "screen_dispatch", 0xE9),
    ("load_complete", 0xC5BF7, "e9a4ed0600", "load_complete", 0xE9),
    ("save_read", 0x1D8D2, "558bec83ec10", "save_read", 0xE9),
    ("save_write", 0x1D9BF, "558bec83ec10", "save_write", 0xE9),
)
# Mutating screen launchers; CPU transactions beneath them are left callable.
GM_HOOKS = (
    ("front_office", 0x142910), ("gameplan", 0x142950),
)


# Narrow dependent contexts; own detours are normalized only after hook checks.
GUARDS = (
    (0x1561A0, 24, "4ed7b83d85bfea593df002712bcee9cf70b2849b73ca907f4186a518b879738d"),
    (0x1565F0, 68, "57c6f11a102732fc135218290a82793f74c34b3a82ed96e69be11a626f762d09"),
    (0x7D550, 32, "26beb3e7536a529baef9279c0df3d10a91d3d06f262c96da101bddd84b8b5d5f"),
    (0x156246, 32, "f75c1e95a31fc9fc604a836e3ebda619d73855dc50b21d561f04d939d04a89e5"),
    (0xC3C60, 32, "7abeec968857f30da5940e378597fe43599baea60bcc4603e53e55fa7fdbfdd5"),
    (0x156640, 32, "4a0b0646a1cea6934b94fe36fc93778d98afbbe50e9a413e7214b071de5cb16f"),
    (0x156870, 32, "ff6a75e45934ca78d4053011c05574542f6d943f382b16532bb966e38a53c24d"),
    (0x1A7970, 32, "18cdabcba3265b59cfd24bac0239a91ab0222e8799ebafa5125a1389caa9a7cf"),
    (0x1A77A0, 32, "c907d7356c59b8dbacbceb1641115a6e80d32f4f950528822f2fdf26372a5f20"),
    (0x1A85E0, 32, "c586ab9e7bbedbbf2e4cb3b983bf434c4244a2beb94e90e3cabf8ea6bd31f105"),
    (0x1A70E0, 32, "166012ee15f88e1da4b3f12403e7de329aea39db522c7003b5e8c2902da5b67f"),
    (0x2BE946, 32, "02a1b1e7961fe1921f21d851ca72ee9385ba7f8fea206a611ae3d6a8e9674eb0"),
    (0x2BE923, 32, "aae87f06be12f5be0673f9193df0048d863e3e62e2617a00b1d720a05a14dfd5"),
    (0x325B90, 14, "3ba9d2d434c0ca5808a7be1993afd563f7c5f64587438ef6438f68cda22438b5"),
    (0xC7A20, 32, "94c9c3187e34d5307a0235c631c7b706c243af1ea8e08fce2f8dac32d8d5ce53"),
    (0xC6D10, 32, "3e10a1467a7fa453e9068fe937794050a105a7c5662480622da270f5e5d9f802"),
    (0xC4D50, 32, "5b89cd7e8f080f969a9e1963ce46a229f583918895dc2d414256b8e95d92e6e0"),
    (0xA5490, 32, "11ec9db23e8243ca3b33114903da65958aaaa63a97582ea23ce9b5de27a22ca6"),
    (0xA5947, 32, "6867d4f9a4689a9420b9e1c3b99541ff7a7a3937e8e7eb9dadaa9733512d876e"),
    (0x6E390, 32, "686561093db164e7bd3ad51c21c621ebf58c72b6689edb72e2416b14760d1a4d"),
    (0xC5BF7, 32, "40a14fd0c860614a469cb6214a60ed6a8c4c0a4313aa698bd2c2f5645877ab34"),
    (0x1D8D2, 32, "1756fdbacba3d180f6f5574a5149ad5c2e05762b87fed9c3f63726f5a0107c74"),
    (0x1D9BF, 32, "4519d1e89c2ccaa813c6c730f456f53d98406fd8ad2e234a1210de7e47339db3"),
    (0x142910, 40, "ec6a04ead601fd17b33c01cbe8c179bd09ad466ff543727c3d0a7ef1f6fbdb26"),
    (0x142950, 40, "861bbf7a0e77c4e519bc675c6fa88ee49b6f80f1e5b744a105bac54d7fa4aaa6"),
    (0xC4CA0, 57, "af965eeee0fe0eb4c18c35a77cfec936e426de3f6de4770cfacff41053ea7e11"),
    (0xC73B0, 299, "07fef36f39b8423857ac0c5cc693363c00752cd7bf06fe92dfefd490e8b83b86"),
    (0x5F760, 48, "060c8f2496fd06c558f712f1fa7f7a0b852446c5118742ef9b35d4fa0229c494"),
    (0x14E440, 47, "d60ded014278ec6b17d843deb5ba7a6a208e2b8a364a63ca9bffefd74e6cfcbd"),
    (0x501494, 52, "e09cc9b26643e8b80ad3699d7dac92615159016bfcc2ac23e693ef066b415538"),
    (0x515140, 4, "d90e7a0333b1c0cc2c1211c11217d1554e82014dc4144dba92b2f59eefca2342"),
    (0x515150, 4, "854e6d79326f89e3fd598db11201210b6bf6dc3433f017f54061d46b651d713b"),
    (0x515160, 4, "45d2c61125103f9d2d2592f63974f9693e3051769bd5a6b96a3dcd452f8b38a9"),
    (0x515170, 4, "a945f89bdc416392a3f7190f41a578375fb28126a467719a0052ad92f708b8e4"),
    (0x515180, 4, "3b447e7520847cca2f03b29294059228564a3c2052330c788a4ddf94e6629131"),
    (0x515190, 4, "35382504c816699b9a2c3b8041bb6d6c29fcd0eb73f70f3e044e529108310bf6"),
    (0x5151A0, 4, "bd7c5c112622d5995f7a77caa2f719fc3fabe2dfd1a1974641f4472390f7d05f"),
    (0x5151B0, 4, "67a0fb1de011581d2ea665bd2b334c6d7d0bf65abaacef5bd626a54798c970e5"),
    (0x5151C0, 4, "3ad6d21b7c1ddae3efedf7ad3a0b65b68ce48b7670ad5b67080692bd54efe54f"),
    (0x5151D0, 4, "859aa29b7e18f076e9e486248b6105f1409aa92d4f4e0d770241a9f022eb96c5"),
)

def allocations(payload):
    found = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    require(set(found) == {"code", "data"}, "reserve the complete MyCareer request union first")
    for _, kind, size, align in REQUESTS:
        require((found[kind]["size"], found[kind]["align"]) == (size, align), "foreign MyCareer allocation")
    return found["code"], found["data"]


def branch(va, target, size=5, opcode=0xE9):
    return bytes([opcode]) + struct.pack("<i", target - va - 5) + b"\x90" * (size - 5)


def code_for(code_va, data_va, setup=None):
    seed = read_setup(setup)
    blob = bytearray(assembly.CODE)
    labels = {k: code_va + v for k, v in assembly.LABELS.items()}
    symbols = {"code": code_va, "state": data_va, "seed": code_va + len(blob)}
    blob.extend(seed)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    require(len(blob) <= CODE_SIZE, "MyCareer exceeds its 16384-byte code and immutable-data budget")
    labels["seed"] = symbols["seed"]
    labels["content_end"] = code_va + len(blob)
    return bytes(blob).ljust(CODE_SIZE, b"\xcc"), labels


def sites(code_va, data_va):
    _, labels = code_for(code_va, data_va)
    edits = [(name, va, bytes.fromhex(pin), branch(va, labels[handler], len(bytes.fromhex(pin)), op))
             for name, va, pin, handler, op in HOOKS]
    edits += [(name, va, bytes.fromhex("6a006a006a00"), branch(va, labels[name], 6)) for name, va in GM_HOOKS]
    # A native action callback replaces the FPP row, preserving adjacent modes.
    edits += [("entry_kind", 0x501494, struct.pack("<I", 0), struct.pack("<I", 9)),
              ("entry_label", 0x501498, struct.pack("<I", 0xE7D5C4), struct.pack("<I", labels["mode_text"])),
              ("entry_target", 0x50149C, struct.pack("<I", 0x526948), struct.pack("<I", 0)),
              ("entry_action", 0x5014BC, struct.pack("<I", 0), struct.pack("<I", labels["entry"]))]
    return edits


def installed_setup(payload):
    code, _ = allocations(payload)
    raw = XbeImage(payload).read(code["va"] + len(assembly.CODE), STATE_SIZE)
    return None if raw == bytes(STATE_SIZE) else validate_state(raw)


def check_context(image):
    for va, size, digest in GUARDS:
        raw = bytearray(image.read(va, size))
        for _, hook, before, _ in sites(0, 0):
            if va <= hook and hook + len(before) <= va + size:
                raw[hook - va:hook - va + len(before)] = before
        require(hashlib.sha256(raw).hexdigest() == digest, "foreign MyCareer dependent context")


def status(payload):
    from . import nfl2k5_my_career_mode as mode
    if mode.recognized(payload):
        return mode.status(payload)
    try:
        layout = space.layout(payload)
        image = XbeImage(payload)
        check_context(image)
        found = any(a["owner"] == OWNER for a in layout["allocations"])
        if found:
            code, data = allocations(payload)
            require(image.read(data["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign MyCareer initial state")
            blob = image.read(code["va"], CODE_SIZE)
            if blob != b"\xcc" * CODE_SIZE:
                expected, _ = code_for(code["va"], data["va"], installed_setup(payload))
                require(blob == expected and rdata.status(payload, sites(code["va"], data["va"])) == "applied",
                        "mixed/foreign MyCareer code or hooks")
                return "applied"
        require(all(image.read(va, len(before)) == before for _, va, before, _ in sites(0, 0)),
                "MyCareer hook without its owned code")
        return "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload, *, setup=None):
    from . import nfl2k5_my_career_mode as mode
    if mode.recognized(payload):
        require(setup is None, "inline MyCareer cannot accept an executable player recipe")
        return mode.apply(payload)
    wanted = read_setup(setup)
    state = status(payload)
    require(state != "foreign", "foreign/mixed MyCareer bytes; refusing")
    common = {"owner": OWNER, "mode": "MyCareer", "experimental": True, "runtime_witnessed": False,
              "code_capacity": CODE_SIZE, "runtime_state_bytes": DATA_SIZE,
              "save_growth": 0, "checkpoint_bytes": STATE_SIZE, "checkpoint_slots": 64,
              "configured": wanted != bytes(STATE_SIZE), "witness_list": list(WITNESS_LIST)}
    if state == "applied":
        require(setup is None or read_setup(installed_setup(payload)) == wanted,
                "MyCareer setup changed; rebuild from the source image")
        return payload, {**common, "configured": installed_setup(payload) is not None,
                         "already_applied": True, "changed_bytes": 0, "edits": []}
    if space.status(payload) == "retail":
        allocated, allocation = space.apply(payload, REQUESTS, scaleout=True)
    else:
        allocations(payload)
        allocated, allocation = payload, {}
    code, data = allocations(allocated)
    blob, labels = code_for(code["va"], data["va"], setup)
    result, installed = space.install_code(allocated, OWNER, blob)
    result, receipt = rdata.apply(result, sites(code["va"], data["va"]), "MyCareer")
    require(status(result) == "applied", "MyCareer postcondition failed")
    return result, {**common, **receipt, "already_applied": False, "allocation": allocation,
                    "code_install": installed, "content_bytes": labels["content_end"] - code["va"],
                    "labels": {k: hex(v) for k, v in labels.items()},
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    inspect = sub.add_parser("status")
    inspect.add_argument("xbe", type=Path)
    create = sub.add_parser("prepare")
    create.add_argument("source", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--first", required=True)
    create.add_argument("--last", required=True)
    create.add_argument("--position", default="QB",
                        help="one of the 17 retail position names or codes (QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE)")
    create.add_argument("--scheme", choices=("retail", "one_pool"), default="retail",
                        help="one_pool offers EDGE/LB templates and refuses retired OLB (10)")
    create.add_argument("--template", default="0",
                        help="retail create-a-player template 0..2 for the position, or 'generated' to keep the prospect's ratings")
    create.add_argument("--port", type=int, choices=range(1, 9), default=1)
    create.add_argument("--camera", choices=("Standard", "Far"), default="Standard")
    create.add_argument("--no-starter-lock", action="store_true",
                        help="do not place MyPlayer on depth row 1 with a rank lock at his first active club")
    args = parser.parse_args(argv)
    if args.command == "info":
        result = {"mode": "MyCareer", "experimental": True, "runtime_witnessed": False,
                  "requests": REQUESTS, "help": HELP_TEXT, "witness_list": WITNESS_LIST,
                  "position_contract": POSITION_CONTRACT}
    elif args.command == "status":
        require(args.xbe.stat().st_size <= 16 * 1024**2, "XBE exceeds 16 MiB")
        result = {"MyCareer": status(args.xbe.read_bytes())}
    else:
        template = None if args.template == "generated" else int(args.template)
        result = prepare_save(args.source, args.output, first=args.first, last=args.last,
                              position=args.position, scheme=args.scheme, template=template, port=args.port - 1,
                              camera=(args.camera == "Far") * 1, starter_lock=not args.no_starter_lock)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

"""Formation substitutions behind SPECIAL; pure, bounded personnel planning.

GADGET = WR rank row 2 (ordinal 4); gunners = WR/CB side row 1
(ordinal 3); LS = C rank row 1 (ordinal 1); 3DB/PWR = HB rows 1/2.
Shared groups with incompatible requests are refused, never silently made
formation-specific. No plays, routes, formations, categories or nodes grow.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as insp

WR, CB, HB, FB, TE, C = 9, 18, 10, 11, 8, 6
RETAIL_SHA256: dict[str, str] = {
    "ARZ": "590ea15c4609fcd922e09b89e90d9742fc8b6b2c6619d8862e2eea3609f090d5",
    "ATL": "a321f20ffc2921734014bbc45fbcd112156718142110492e2f1c7cdbe8c66041",
    "BAL": "bd299c2d062e6c13c587c563b11b16da06e16cf33f5b602f6a536adfd8b28290",
    "BUF": "64fe5cb13493a2ce4c2925b48ea1b251d74ccd60aa4e5d68715ceafc289e42cc",
    "CAR": "7a0e419ec7f1e1a728250dfd6a21b6d32654f464ba55eb8d870ac72e8d6cc3fe",
    "CHI": "3bc885f02cfaf3b328c96063e3f3a3fb209349a64abe8c92abf9f47436d4bb38",
    "CIN": "acc0db6c913c5735d6d8435f481a8bce73c210f93389f255fbb80d7a5949d7b2",
    "CLE": "aab5d0bfb731faad7e237ea52db54464279263c3175cd739e5951c2a2a1faa15",
    "DAL": "1d414faf62b51232fd746f84de3f064c1dcebe153da6cdd98a2624f149c27d60",
    "DEN": "51888ec256a962fb7443b859a0274d98b1ea310ec36f8529dacec2588b3acf02",
    "DET": "b9dc116d3eb537092527bf8d0370ce8d959523b1b2149d336313c27fc6f5c816",
    "Editor": "39f043ed0d0bc4bae818f49c2c76bd6e18d43db07200353b64b371dda1f880ba",
    "GB": "29e80af1c7ecfc495abd6577147f08e8ef835b7326618fa446debf32f7ae1e24",
    "GEN": "dc172cee205fd3ca075c760453b518a7312b456c5e660f3def28d7068ee23b78",
    "HOU": "8f15e1d3194cce2012abdacf620d2832d15f3d552807f735d5faa899cbe19e4f",
    "IND": "a5f0230146c29cd1f399d000fa8215e6ded8a85c6ba48a0ef4ba6f1b955ee011",
    "JAX": "8cea919180ba038eb842722cc1de1a45aefc7d615ef45770a4934821c4dc1c39",
    "KC": "bd2e4c789f37c4de7e4fc782607ff2a2ac2f25f4644cf5697f05761b7e71dc58",
    "MIA": "bec5f10b68377e1a4b950d0f41bac11afb5dbcb2b79a53c00f2e8fbb3b4b5de8",
    "MIN": "6120640720a864e0438f30d6860fc35992cc65fc31cd6466f22fd7402dcea2ff",
    "NE": "1c6bd5c6feb9e596ef41717e5bcfc08fb0e0771b222ccb26b5c4e7faddc30d73",
    "NO": "472d811665e94d42738b576cd5bbaf6b9cf0ba96e102f3e2a6e4b1e41888cb67",
    "NYG": "6722e67eda027a7fe089621c6f831c10456f9ec5e2c8e98c636e48e018480b7f",
    "NYJ": "b5a714338f95a3a22480326a45e60d5cd2cab9fbfe110c7b6c3d122f1de70648",
    "OAK": "41b211b3f242bc48dae87fd893bbb0ae3384a401c545fa8f21630c33ab1ec8d0",
    "PHI": "aac4e2a866a8798218c58d789498cad7fc1c74d23cc0fb252ace2fbe7abb2b64",
    "PIT": "751efb4497ef6b34724ab0ce179b2e1e67c95891cdd9054eb5fd79507404e3bb",
    "PRACTICE": "e512bf7595baefd2d4d389149e88be03f41716705802175321b73b0c212e4281",
    "SD": "6a9877674d71fb213810d1fb713a99f687a5149c01cdea42d6091e2a2c5e1974",
    "SEA": "4215d79ec4b566ea643e9bcd97a026cf3af180e42524a227ad748665e925c74f",
    "SF": "3ea0073010eeaac079517d774369e78cfd5ea85ba69d6c55549bded26daf998e",
    "STL": "848b136ad4ecd1c46f459f95adba6eaf981b60315201c5740cec40633b26f743",
    "TB": "34b4fa628cd93b4666e25726fe44c96e3e1e05970544b2cb94377f06a79f2b23",
    "TEN": "1aa5a16c5fdf7e6853d9d6cb4b2f09ba893b67250557ff9e37819308f852c693",
    "WAS": "c1575b675aa0b12a91de56dd21c7760f92e962ca260240dadc5b01df53a60bb7",
    "WCO": "430b08127d6bf1f4e7d912b21b08c728251a6ded53b79f8e4d93a1487c8d1812",
    "reference": "7cfab0516cb7916a816176a394c047f44f58aba88f939f3444d2a57a76c82740"
}
APPLIED_SHA256: dict[str, str] = {
    "ARZ": "e305cb5632f9888698c8eab449a26a7300b288f6da44951ecd52b78d8a99d721",
    "ATL": "60e5ad74aceaacf56566398eadde28fa7f0a4f751252c8c67b307162830e8620",
    "BAL": "fd281c74ed0dae5047af93d568a2c934d969b6e4483cc3273a37021d1531eb64",
    "BUF": "dafdddc01d473be2be08f14936f56509c9a372a476be55915153907aaf0e9bf5",
    "CAR": "ee2370fde7ce0a142432184d62751cda92aebfb494677880808c7a4de8681143",
    "CHI": "a2749388104751d8b9f6ad184dcc23de90d732e464115ef7030dafa9774782db",
    "CIN": "cd4121a1344c2392855aca2e92a8ec429770282a16afe7f953cb5be5171c3938",
    "CLE": "b8179025d6388db9eab02c6c2896b4bb01a06822f516959a4064d73a5d208da7",
    "DAL": "dc44c7771e8a31977db00344db6790e5c98b0b3a513748f0540300ff307d993c",
    "DEN": "54089863d1f190c90da31f828a15f888c0d043f449e99dc5496774d0639fbe33",
    "DET": "3a4a86a2b89ea13ad94c951d8c8dfc693a69dc26e9d8533dcfe01c4bfef45883",
    "Editor": "a1a7db23ec6c191fa1eef1cb7681a9310144fbba2d4467f422661f1ede07f9ab",
    "GB": "0fa0fb9e884dff2f4cc7e27e7e31c24b8f0a4e96c9ad12d2a971e3a4beff376b",
    "GEN": "ef13ec3cc5d121e886dec17807b6c6fb6695223802105c720874260255367a8b",
    "HOU": "2a4469df82c1ed7052b6fa7556a472b0b4876888f1f0366c5087a6c7bacc95b4",
    "IND": "2eac2aab503fcf636a5924b563af2cb5b8aa6bbf9928b0494766d22830b478cf",
    "JAX": "6d1fb1ee6452407dab411134b81efab900d72c19e8023929fc282bff962bf429",
    "KC": "1ac9d2d5d014f4082d5bcfd07b69f2f46f5732c12a7dd75ffacdd89dbd01c5fe",
    "MIA": "867f72a8315231040d566a02e6668bcb41bbc0aaa9e53d8647e8f76f862510ce",
    "MIN": "935ea33b058936c05f65bd9ab67f9e6e7634b7a5240bfab0a6c2a96ed0c99615",
    "NE": "6b342752bec45333e5c8d9dc5b78c41782661c8f80d8a2d5815a2cebc9c0be87",
    "NO": "c17d756bd4dd4d454af493ec35aea8eaafcdb38a3f3f0015231e57d4a56c35b8",
    "NYG": "a1b9d37a4b8006f14880ce861a0bc2849ef796acfe28b2361e17ea3721fdc21c",
    "NYJ": "9772746d4b4908c08b53a64ca3261b8912a4d64b13c1ee81867e4d0e5fb82667",
    "OAK": "284af422da8ca6317e35a4cc359179040358557c56d25a5e61d2f8580687d730",
    "PHI": "a21432a699b89acd5edc7e9b03f277f082e6f5db81501aa425ad72279324023b",
    "PIT": "99d0926a3641a9612ff2802d07adfb1fba2d257e562efa101c94b4ad2eb0d36d",
    "PRACTICE": "38d25d540655eb93a8919311daa88052206b2e7248cdcc5d46cc3ddab6c9b4ad",
    "SD": "4c63654f8890220b8d2dbf730dc98435a1b1fe86ad618695626decd030791aa5",
    "SEA": "aa77638991aa661fd76874b0197127f0f66974e92925fd5b4a13e89900a37711",
    "SF": "fde64eea9e35ae36f1dedad71de69759da7994a57b68b3b1b7032510e2a48a40",
    "STL": "d871737b2a46040e36558e4e8da76b7b464801a6e2203bf2586be21db548574c",
    "TB": "ad132ee68878a20b09c8466b42b3f8558ec92a0d653f992ca4bc432647550f05",
    "TEN": "87626adaa1bb4e0391352b28bc7af55aea2c9f37394f6c15f1536d3f74a951c6",
    "WAS": "7142fdeb77e5f8536bb925cc94d4dfdd4a5a48f7d849a1107b67a8572e0887be",
    "WCO": "80086819ef649f03a7b55c29a70bc9ee257224231e00da2e5f62b6bac9be0ba3",
    "reference": "49608d6a21cd684597243a2e0277aa27dbac495b7fb53754871a2dea65a106be"
}


def _signals(body: bytes, form, codes: list[int]) -> dict:
    """Actual snap and handoff nodes, not play-name keyword guesses."""
    gadget, snaps, gadget_plays, direct = set(), set(), set(), set()
    for play in sorted({link.play_index for link in form.play_links}):
        _flags, chains = lib.play_chains(body, play)
        for slot, (_desc, nodes) in enumerate(chains):
            for node in nodes:
                if node[0] == 2:
                    snaps.add(slot)
                    target = int(codec.Node.from_bytes(node).operands[0])
                    if 0 <= target < 11 and codes[target] & 31 in (HB, WR):
                        direct.add(target)
                elif node[0] == 0x13:
                    target = int(codec.Node.from_bytes(node).operands[0])
                    if (0 <= target < 11 and codes[target] & 31 == WR
                            and any(n[0] == 0x16 for n in chains[target][1])):
                        gadget.add(target)
                        gadget_plays.add(play)
    return {"gadget_slots": sorted(gadget), "gadget_plays": sorted(gadget_plays),
            "snap_slots": sorted(snaps), "direct_snap_slots": sorted(direct)}


def formations(raw: bytes, book) -> list[dict]:
    body, result = raw[insp.RESOURCE_HEADER_SIZE:], []
    for form in book.formations:
        group = lib.formation_category(body, form.index)
        codes = lib.category_positions(body, group)
        record = lib.formation_record(body, form.index)
        offense = lib.is_offense_category(codes)
        # Type 10 is punt, type 12 is field goal/PAT; exclude their return/block
        # counterparts. Require actual snap nodes again before owning a slot.
        special = "punt" if record.type_code == 10 and codes[0] & 31 == 1 else (
            "field_goal" if record.type_code == 12 and codes[0] & 31 == 2 else "")
        if not offense and not special:
            continue
        kinds = [c & 31 for c in codes]
        hb_slots = [s for s, k in enumerate(kinds) if k == HB]
        receivers, tight_ends = kinds.count(WR), kinds.count(TE)
        qb = record.slots[0]
        gun = bool(record.flags & codec.FORMATION_FLAG_SHOTGUN)
        geometry_gun = qb.z[0] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM
        name = (form.name + " " + book.categories[group].name).lower()
        named_heavy = any(t in name for t in ("goalline", "goal line", "jumbo", "gl offense"))
        # Two TEs plus a fullback is the measurable I-heavy/short-yardage
        # definition. Ordinary I Pro (one TE) stays a base set.
        heavy = named_heavy or tight_ends >= 2 and FB in kinds
        receiving_hb = any(abs(record.slots[s].x[0]) >= 5 * codec.YD_CM
                           and record.slots[s].z[0] >= -3 * codec.YD_CM for s in hb_slots)
        passing = gun or receivers >= 3 or receivers + tight_ends >= 3 and receiving_hb
        role, reason = "base", ""
        if offense:
            if not hb_slots:
                role = "no_hb"
            elif len(hb_slots) != 1:
                role, reason = "ambiguous", "multiple_halfbacks"
            elif gun != geometry_gun:
                role, reason = "ambiguous", "shotgun_flag_geometry_disagree"
            elif heavy and passing:
                role, reason = "ambiguous", "passing_and_power_personnel"
            elif heavy:
                role = "pwr"
            elif passing:
                role = "3db"
        signals = _signals(body, form, codes)
        result.append({"index": form.index, "name": form.name, "group": group,
                       "codes": codes, "offense": offense, "special": special,
                       "positions": [(s.x[0], s.z[0]) for s in record.slots],
                       "shotgun": gun, "geometry_shotgun": geometry_gun,
                       "hb_slots": hb_slots, "hb_role": role, "hb_reason": reason, **signals})
    return result


def plan(raw: bytes, book) -> dict:
    forms = formations(raw, book)
    uses = defaultdict(list)
    for f in forms:
        uses[f["group"]].append(f)
    entries = []

    def add(group, role, targets, reason, fs):
        codes = lib.category_positions(raw[32:], group)
        entries.append({"group": group, "role": role, "before": {s: codes[s] for s in targets},
                        "after": targets, "refused_reason": reason,
                        "formations": [f["index"] for f in fs],
                        "affected_formations": [f["index"] for f in uses[group]]})

    for group, fs in uses.items():
        codes = fs[0]["codes"]
        offensive = [f for f in fs if f["offense"]]
        if offensive and offensive[0]["hb_slots"]:
            roles = {f["hb_role"] for f in offensive}
            reason = next((f["hb_reason"] for f in offensive if f["hb_reason"]), "")
            if len(roles) != 1:
                reason = "shared_group_hb_classes_disagree"
            role = next(iter(roles)) if len(roles) == 1 else "ambiguous"
            ordinal = {"base": 0, "3db": 1, "pwr": 2}.get(role, 0)
            targets = {s: HB | ordinal << 5 for s in offensive[0]["hb_slots"]}
            add(group, role, targets, reason, offensive)
        gadgets = [f for f in offensive if f["gadget_slots"] or f["direct_snap_slots"]]
        if gadgets:
            slots = {s for f in gadgets for s in f["gadget_slots"]}
            direct = {s for f in gadgets for s in f["direct_snap_slots"]}
            reason = ""
            if direct:
                reason = "direct_snap_requires_different_position_or_slot_role"
            elif len(slots) != 1:
                reason = "shared_group_gadget_carriers_disagree"
            elif sum(c & 31 == WR for c in codes) >= 3:
                reason = "gadget_conflicts_with_x_z_slot_ordinals"
            add(group, "gadget", {s: WR | 4 << 5 for s in slots}, reason, gadgets)
        specials = [f for f in fs if f["special"]]
        if specials:
            snap_slots = {s for f in specials for s in f["snap_slots"]}
            reason = ""
            if (len(snap_slots) != 1 or any(len(f["snap_slots"]) != 1 for f in specials)
                    or any(codes[s] & 31 != C or any(abs(f["positions"][s][0]) > 30
                        or abs(f["positions"][s][1]) > 30 for f in specials) for s in snap_slots)):
                reason = "snapper_nodes_position_geometry_disagree"
            add(group, "ls", {s: C | 1 << 5 for s in snap_slots}, reason, specials)
            punts = [f for f in specials if f["special"] == "punt"]
            if punts:
                pairs = [(min(range(11), key=lambda s: f["positions"][s][0]),
                          max(range(11), key=lambda s: f["positions"][s][0])) for f in punts]
                left, right = pairs[0]
                reason = ""
                if len(set(pairs)) != 1 or any(
                        f["positions"][left][0] > -10 * codec.YD_CM
                        or f["positions"][right][0] < 10 * codec.YD_CM
                        or abs(f["positions"][left][1]) > codec.YD_CM
                        or abs(f["positions"][right][1]) > codec.YD_CM for f in punts):
                    reason = "gunner_geometry_disagrees"
                add(group, "gunners", {left: WR | 3 << 5, right: CB | 3 << 5}, reason, punts)
    failures = []
    for e in entries:
        if not e["refused_reason"] and e["before"] != e["after"]:
            failures.append({"group": e["group"], "role": e["role"]})
    counts = Counter(f["hb_role"] for f in forms if f["offense"])
    assigned = Counter()
    for e in entries:
        if not e["refused_reason"]:
            assigned[e["role"]] += len(e["formations"])
    return {"formations": forms, "entries": entries, "classified": dict(counts),
            "accepted": dict(assigned), "gadget_formations": sum(bool(f["gadget_slots"]) for f in forms),
            "direct_snap_formations": sum(bool(f["direct_snap_slots"]) for f in forms),
            "refused": [e for e in entries if e["refused_reason"]],
            "gate": {"ok": not failures, "failures": failures}}


def digest(raw: bytes, book) -> str:
    """Pin classification inputs and owned codes; ignore unrelated front-seven recodes."""
    rows = []
    for f in formations(raw, book):
        if f["offense"]:
            wr_count = sum(code & 31 == WR for code in f["codes"])
            owned = [(s, code) for s, code in enumerate(f["codes"])
                     if code & 31 == HB or code & 31 == WR and wr_count < 3]
        else:
            # Punt blockers may be recoded by position pools; only snapping and
            # the two geometrically identified coverage slots belong here.
            xs = f["positions"]
            slots = set(f["snap_slots"])
            if f["special"] == "punt":
                slots.update((min(range(11), key=lambda s: xs[s][0]), max(range(11), key=lambda s: xs[s][0])))
            owned = [(s, f["codes"][s]) for s in sorted(slots)]
        rows.append([f["index"], f["group"], owned, f["positions"], f["shotgun"],
                     f["hb_role"], f["hb_reason"], f["gadget_slots"], f["gadget_plays"],
                     f["snap_slots"], f["direct_snap_slots"]])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()

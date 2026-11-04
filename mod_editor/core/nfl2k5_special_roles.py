"""Formation substitutions behind SPECIAL; pure, bounded personnel planning.

Gunners = WR/CB rank row 3 (ordinal 6, b780 sub1; was side row 1, ordinal 3);
LS = C rank row 1 (ordinal 1); 3DB sets keep the lead back (HB ordinal 0);
PWR = HB side row 0 (paired ordinal 1). GADGET (WR side row 3, ordinal 7) is
a per-play substitution in nfl2k5_lineup_roles; groups keep X/Z.
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
# b780 sub1 (Noah 11/03: a special-row pick never starts somewhere else): the punt gunners read rank row 3 of the WR and
# CB orders (ordinal 6, the SPECIAL LGUN / RGUN rows), which no other club formation asks for; before, WR/CB ordinal 3
# made the left gunner the 4th WR in four- and five-WR sets and the right gunner the dime corner. GADGET_ORDINAL (7,
# WR side row 3) is the SPECIAL GAD row; no book group carries it (the gadget player comes in per play).
GUNNER_ORDINAL, GADGET_ORDINAL = 6, 7
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
    "ARZ": "b42704074bdb588e53dbcba4d5edf56df6dfad6e4f86f4a33f781f156b40dc7e",
    "ATL": "fc94bfda288d1937576f41737c80390dd042ffbc4dfa948a84d16a45e299ce2d",
    "BAL": "3b1277442c8df35055a0d956757c2ad515861bf6a4fc48fccb591d77b8e46627",
    "BUF": "ecb57363063a361b48f455873270ae21f3a477ce3e593791be9671afff64b82f",
    "CAR": "f7fadd4299a373f65032a386f56f57f4731e8fe374834801c297f0c5121a6fb8",
    "CHI": "6b451fbff5d66248ffef6457acfc26d3e39f50f7bf7f7ebf8563d9d392410ab2",
    "CIN": "4b9352252bda970d89f17da57d4f354d8af51fa8308bcffcc2fffd248845ec75",
    "CLE": "8bfd1d004871aef0b8422a4da55928129f6188a0511a974e02f52d737ac8bc71",
    "DAL": "496aaab57d1686b801759e6409da18fffbae2f0f9eeeb79244f05032a8ea80ba",
    "DEN": "05be09be2ff0d9a1dde8f025b3e9a1b5644c8210e75daabb2519bba17b394ad7",
    "DET": "41f9fc0cfb41a0c025ed3b9f601fd42591f25d2676da2cd47eae4be825ccdac2",
    "Editor": "61f55da2646e88060a0f5f6960df15b6a932ebf0d799d933ffc3237def0abc24",
    "GB": "658c4ff498c91ec819f29a79b0de7a069fd85c638a9f7fe47aa4a472d2794c77",
    "GEN": "1fb00b9ca41e3e4ff51fd3110fd135b457a2123b85c738a845de9d4d96e685de",
    "HOU": "46ff3a1cc23379a09027e8621243b425fd505333a2b47f69bb7cdd73c0e6d5dd",
    "IND": "da597a813181af815e514e0912682dd736a212b7e9908d91f1c77381a3b1e67a",
    "JAX": "7335291e7353bcfe1b82c17435fa624ca54a722b489c25ef240d2a0d6bda8be1",
    "KC": "7e17c57899883382c7af42234f2474e2fe4ea52cef3263857b07d56694592b02",
    "MIA": "56af6764227935ee3d0850d8e0596b3d2ee5946bae3471b9c4134e3b67251895",
    "MIN": "969c122c72cac2f98ebdba4c51efb439f6edfd514bcd9ccc4fcf6685b78eec96",
    "NE": "24d36184d4aee148826e309d40971c77fd7ee86f131cc52b022eaa727f28b340",
    "NO": "5ba0b151324b1cbc8227734ffb91cf29080717c168f7949d91e51cb74d719b9f",
    "NYG": "eab350360a43d295b937e9c3aa17530f01cd73eef687a63a4ab1ef958bd380a6",
    "NYJ": "07d2924f5da269fe34cde5fc754c3f13b3879636bb004692695628b9d660c6b2",
    "OAK": "9b42a1a525693b96bb217e8e30b6242fd875e3249674ef68d940d39f0846c81a",
    "PHI": "105eb568f9b9df2229b65e9f4c1873aa8cf0f8eb9fcf60a0dfa5adcaed4ec10f",
    "PIT": "b9074e456561bc33c074762265cae335572c736e313db82c35109cf7722d8ee9",
    "PRACTICE": "b7d4955eb07e5528c296ae1373590e81b302fc1074cc26b2102996be1ba41d58",
    "SD": "40ce1a8bbaaddb088e15217eb5267ad3f8b3f764f25dd4c3d6637676dc7b6eaf",
    "SEA": "a89529ce4c24c0130bbe1cba09b4af3dca612d0c8869955a23fe0a283d3a99b0",
    "SF": "bd123e295a6f6ce7033b57cce58839957c41318b3c2bbfcd0c5c0c661cc4157a",
    "STL": "b07a72b76a64ce92a6a5da1ff509d6d0ea63e418516c0c823378443d15c1093e",
    "TB": "b4c1dfe433bc7d6db767eb574065e678f931c477618dbc751c9694bd3b7fec56",
    "TEN": "284d9c46226aa3eff6015e13d1f3ab3e5125e9704e6b33f31f8fb763c0acd1e7",
    "WAS": "027b3254ce75c66ca34284b1386c635fe3f786ae3d54a74039de857cc312af5f",
    "WCO": "6ed9efc8f9aa7b156a5cb5a0827e721fa282627057e972c0033f091b1d12db47",
    "reference": "08a815ee2cd754a6799326a5629849cf73470ae915e46c28f708451a7ce61ae1"
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
            # Personnel belongs to a formation, not a down. Shotgun and
            # spread runs need the lead back too; reserving them for HB2
            # removes HB1 from most of a modern offense's snaps.
            ordinal = {"base": 0, "3db": 0, "pwr": 1}.get(role, 0)
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
            else:
                # b780 sub1 (Q61): personnel belongs to the shared group, so a gadget ordinal here also put the gadget
                # receiver at WR in every base set of that group (35 formations: Cleveland and the GEN, WCO and
                # reference books). The gadget player now comes in per play (nfl2k5_lineup_roles); groups keep X/Z.
                reason = "gadget_is_a_per_play_substitution"
            add(group, "gadget", {s: WR | GADGET_ORDINAL << 5 for s in slots}, reason, gadgets)
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
                add(group, "gunners", {left: WR | GUNNER_ORDINAL << 5, right: CB | GUNNER_ORDINAL << 5}, reason, punts)
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

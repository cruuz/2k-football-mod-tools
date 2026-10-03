"""Formation substitutions behind SPECIAL; pure, bounded personnel planning.

GADGET = WR rank row 2 (ordinal 4); gunners = WR/CB side row 1
(ordinal 3); LS = C rank row 1 (ordinal 1); 3DB = HB rank row 0;
PWR = HB side row 0 (paired ordinal 1).
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
    "ARZ": "ca9d1391543b1c6eefae30837aadce9fee9c27a3b74f7271f90616270602f06f",
    "ATL": "c64b347220a35b5a9b55193ce81477e60bfc849581a8dc821e21f05cb9f22f12",
    "BAL": "405b059a14ee9c2d5efd81deba0c25fd53fe98dd9c982eb842aa3970284016d7",
    "BUF": "ae8840fa4bcd5ca8a9a3df8889a556852fe4b7448c8d057714063d10407ed7fb",
    "CAR": "306d1d7fc2ed5ee883d55df9d1de1aff967254de899b742abc5200d54b4e0c90",
    "CHI": "8c98e15d747ea66e8095cc283532be88aa6f213def934c99c739f3ae121c1127",
    "CIN": "60107bfbdb82dca42eaed89873b3f9461af88522080a96b7af9957ed3e7ef82a",
    "CLE": "cf43ba188a9b1f56fd59a326e7d4e05de84bb1a2594aa52ffff3a4a7955e2f65",
    "DAL": "ada513cd3a0bf6ec1c1b975e030882bb6aa2aac98c4fe0bbdabb6a84498e88a8",
    "DEN": "6c593ca1ef3ae395bc0d83db4b3511602fbb762befffe40cd805e4b60809ad7e",
    "DET": "ae883c68d695de0ca9b6375800995af258328430a29aeccaec751a322b2181e3",
    "Editor": "8011fa2c18428cddab931f39747ab13873eefe0a2fa7ab4116d90a739f111412",
    "GB": "85b8a175d58d6c7973172bcd7c13411bc116610c3bf8d85d902f1a80bf8f6cbc",
    "GEN": "b1a95032cea6704a34b2a9b3fe2643eebdb80b99dafcede9bf43949b9ebcf2df",
    "HOU": "514249a1163be9c501aed3c34e3efc91e44fc31bf015e46bff5cd919ac5b19a8",
    "IND": "a3b3b302751f77788cb4132778d4f1a32ee3a53068fb41bb68a274db6e2db534",
    "JAX": "47d713c499369524311fc776c8287265d8ab0b80c3e58b5d2ac0e993f8b17c5d",
    "KC": "4d95d3c760eb1a68f907c6bdee98a25403e8db207d29196d73095a52b5baad8a",
    "MIA": "a1c988ef93a93443d711006a42082207e273a6266095de0a05ec30aeaece8a81",
    "MIN": "d6609c7a11d9b6414444d9412571ec07494dcc275c44af505af0ba723e1a960b",
    "NE": "737fc94f1c3a0269a2e6c236a6f8756cd7370339949c1b6791806ba06d32f053",
    "NO": "871f0855b4e4f0b295df72164877e5de1e916b4bbc03415296a6e32fbee35d1c",
    "NYG": "a2934009da7afe8069d093c298264ad3251de35fab09a4230e9b1762d50aa498",
    "NYJ": "5cca62176f32f917b48fef5dc0b600117940483fc257594aebde3a407d0562e1",
    "OAK": "9abd267989025e64996cccd8aa25e3f9c06f740c93ef6515c6bb3679228e40b3",
    "PHI": "0e80ac3d527762041e1f2c6c14ce8ecfb72918fb8387ea47757b67fc05bc7e18",
    "PIT": "f79e8d1148620dff38564241db9a5bbdec9bfedb22aadb093f91979a4110ce1f",
    "PRACTICE": "b7d4955eb07e5528c296ae1373590e81b302fc1074cc26b2102996be1ba41d58",
    "SD": "2b27cf5c79bbfb93c2aea7fb344717650966c47b17ccebc4ce0a2181eacf2a14",
    "SEA": "a85aa116710c19254a9a22e1724c09b04a1b86ad06a8a0492bc120f8488658c0",
    "SF": "18eaff6c86c2642a538d2eebaefbfed8788e4e7182d38ba8bc00bbf0833c0f9b",
    "STL": "027c82f8f5ad7762aff024f9666fe50c9833820dea29611fd50cd001311c7cc4",
    "TB": "c1d5c83e38f77b7deb9cbd11c42dfb66e06edbb47eeabf700a2651e8b8499f39",
    "TEN": "fb1c5fc855096ec59d9fa6f0d6808826c67e2001d3b4282eab960d1fe17c0b19",
    "WAS": "9b0e3f1fc2c1ed743114f110eb92585d039eab81857204bd7476f31b9d86d03f",
    "WCO": "05a0eae92c7e580ddf162cc4c2f8d52abc8164340407562aa9c77b984d3f96c8",
    "reference": "e59b4da23c794d439e29f6308199e247a26ad291b99e76d1abbf72b5c53ce710"
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

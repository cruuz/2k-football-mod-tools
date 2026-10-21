"""All player rating displays on the existing F4 grade scale (lg2), except editing screens (lg3).

Fixed presentation edits only. The 65 descriptor kind bytes cover both complete
attribute column sets (roster lists and transaction lists), nine position-dependent
columns and the in-game substitution overall. Seven format pointers cover the player
card, depth panel, weekly prep/matchups, common overlay, and fully scouted player.
The F4b stub now selects %R for every Previous/Current row; numeric differences
remain differences. No getter, comparator, control callback or player record changes.

lg3 (Noah, 2026-10-20): "when you're editing a player's attributes, it should be
numbers. But when you're looking in any other window, then it converts to letters."
So the screens where the player changes a value stay numeric:

* the 26 attribute controls of the native player editor (``EDIT_CONTROLS``,
  descriptors 0x5639F0..0x564B20). One shared table drives Create Player, Edit
  Player (Rosters), Franchise Edit Player (Player Contracts, 346730) and the
  MyCareer Create Player hand-off (mode_creation_done in the same editor). These
  descriptors must stay retail; an image whose controls carry the grade kind
  (an lg2 build) is foreign and needs a rebuild from the original executable;
* the MyCareer Upgrades line ("Speed: 94. Cap 99. Cost 20 XP. ...") where XP buys
  one point, and the MyCareer prospect tier labels ("Prospect: 1st Day (74)") chosen
  while creating MyPlayer: ``nfl2k5_my_career_mode`` writes them numeric in either
  install order and this module no longer rewrites them.

No allocation growth. The progression owner is resealed after changing one
branch displacement. All sites and their surrounding descriptors/instructions are pinned.
Offline evidence does not establish live navigation or rendering coverage.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_letter_grades as lg
from . import nfl2k5_letter_grades_progress as progress
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_letter_grades_attributes"
REQUESTS = ()

# label, descriptor VA, SHA-256 of the complete retail descriptor (0xB0 bytes).
COLUMNS = (
    ('roster_0', 0x00541288, '6107452d91855b619da0bc3efc1283bc7e478d339aa3c0e2536119252ff312dd'),
    ('roster_1', 0x00541338, '54616ebba7c2af46737c0485144c73d625d22745c91ccd95872848958d88270e'),
    ('roster_2', 0x005413e8, '112d540578ec8163f72dd97a10fbf3b6c4478cd4d8fabf97df39dc2f72c1cd58'),
    ('roster_3', 0x00541498, 'c3f3a4d5cb0d28833b2c0b1d86588a7c06b389a1a59bb608632e549444636038'),
    ('roster_4', 0x00541548, '8f6f85f23b0106be0d581cd3a86a31f2b31421c2d2e562f27c9276b91f4febfc'),
    ('roster_5', 0x005415f8, 'd64164e8d85d532b76b06118e378a9ad4b103d1e607d4215e611215d93a79feb'),
    ('roster_6', 0x005416a8, '1a24409995ee596052636d0b11714e85a496a3a2825ec928778fc9fc5add3634'),
    ('roster_7', 0x00541758, '25e9dc5ab0c22bf93b47dad8ee1a885b0741b3283bb718e9f91e7fad25576500'),
    ('roster_8', 0x00541808, 'fc95437e45c685b22787f7737bedffcf0f67de600a668c9c013472a244491136'),
    ('roster_9', 0x005418b8, '3e072543ed1ee9b22f82c1847021df379986467cbd02f14036c1e9b03b747d83'),
    ('roster_10', 0x00541968, 'b5ce5aa16e7f8ba8c924383888eb9ca82292081cfcbacf2d02ee04a3c11ae010'),
    ('roster_11', 0x00541a18, '7e0ddf1ee320faf8fc464ad2d642bca7f504eda936581fc76f7ab654e3631b7b'),
    ('roster_12', 0x00541ac8, 'cc29e62d35b0a0024a9e714c4c5ae496d939761895d9b2fd0867a46f54b47c4d'),
    ('roster_13', 0x00541b78, '4426a04c99dea2b68f06842fa5c0c05f6ab117724f5b4c156c3d156f35e9657d'),
    ('roster_14', 0x00541c28, 'e7d113dac93d597496b682e1269e15d16e764b9e5968ca96b70a02e649a9c013'),
    ('roster_15', 0x00541cd8, '1d3d2c5241e2c47cf8f81872b93e492bfa4a59ce9717152d46a3bebc7b1d79fd'),
    ('roster_16', 0x00541d88, '806920fd63b17c36f96c3c4a409bf555706215304f6bceeeef5557ac3e6c1bea'),
    ('roster_17', 0x00541e38, '10be1472ef7c6a835e5dd82362ea153bb3293dc792c938e5c580541768ef41d5'),
    ('roster_18', 0x00541ee8, '1ca4babdb057659b5561cb8eb96c8ddfd50b10c86a2f7141f841591661948f19'),
    ('roster_19', 0x00541f98, 'f65ec1d8f85254131436f3e6650fff10f4cda43ab22775f39fe8c6ef88d8b7a0'),
    ('roster_20', 0x00542048, '4326cf3de8f6616397c85dc2973e88edda0570a110e6dec8fa7095817fcbeb46'),
    ('roster_21', 0x005420f8, 'eabab9e6f39964f2a374f8e18b2125986dcd882465c3c4aa7010796673a99ccc'),
    ('roster_22', 0x005421a8, '8b2d738a3826112da087617b35891671a97b6bf8dcf7703733ba213a7f396ff6'),
    ('roster_23', 0x00542258, '35eae3832a2c572566dc51dd1725b78685b4f24d3216c9cefd7f5df0ffd7c63d'),
    ('roster_24', 0x00542308, 'b10b9f7940b04b528a52386cba9f7264dd6b926a6ea5f6211da6d13e26995d72'),
    ('roster_25', 0x005423b8, '4de3f7d61cc7b55cdfc533eddd40763b77869040cfbe17fb87a9c60f6976768e'),
    ('roster_26', 0x00542468, '65e2ea5544a3f5cd1b674f84af6d3c05ea2063066bbcf7e7b5ad8381a06c30fe'),
    ('transaction_0', 0x0057dca8, '7f198f0a45a07abbe19388a7b197b9f40ead065b50ea39e5738654cc33667c46'),
    ('transaction_1', 0x0057dd58, '6ddfad9a236b3de9cc1bbfb9cd0a26baebdbe60e5dc7eceea6627042d2267774'),
    ('transaction_2', 0x0057de08, '551cdcfd97b83b67965036da75640670ff98d4eb5ed1dae550df100a69e92c57'),
    ('transaction_3', 0x0057deb8, 'b9269ef75322715149a3606ff440cbcafe3d0134d339961548403d76ed5b721b'),
    ('transaction_4', 0x0057df68, '8ee1bae5468389420ec623a25a85ce2b6743b6aae20d6380a1410a1289fdf021'),
    ('transaction_5', 0x0057e018, '2fa22793c166ea5692fb11356752c4cd36f4ab8c4e3a0a7505ea6b3e612647de'),
    ('transaction_6', 0x0057e0c8, '3f9dfc788622f3d6590772ed18728252440a5f9256a2b4fd650cbaa1f5f772d3'),
    ('transaction_7', 0x0057e178, '7cb87c736e165d80a38678c9ce8060b5922d8a064c0be7735832bed92e004807'),
    ('transaction_8', 0x0057e228, 'f423187921b77aab5001df7fa0b2d9c89ee3ced238e86c742dd08aa7576c16c6'),
    ('transaction_9', 0x0057e2d8, 'da68e6f85123a6b721892dedc784988025cbca383b49b453ccbcca6f9fe20a21'),
    ('transaction_10', 0x0057e388, 'b1abcebf07a4943da5665ecb9a9c5ea3b7403062f67f11eb458b80be8131d8b6'),
    ('transaction_11', 0x0057e438, '01e3625d0d0cf951f5ee735c418791b1f1009fa3540897b65c6249d1f48f4afa'),
    ('transaction_12', 0x0057e4e8, 'faba4fedbfb2d1dcfacb206c6ad295be24df90e0b37dd4e97547717aa8ead834'),
    ('transaction_13', 0x0057e598, 'e0dfc1eeea93c7e971c37ccc85081f60a8b827d0ce12b477e236b578db52c161'),
    ('transaction_14', 0x0057e648, 'b8b14c461657f5a1a1069f3d4434493f26b74424a83d3a7199c41736f67c5684'),
    ('transaction_15', 0x0057e6f8, 'eb8815b43cc63eab1f57575e529108c763ba3e8cbd7ff2cc1f73f2dd1882921a'),
    ('transaction_16', 0x0057e7a8, '07532d09fc39ce6b7e6c3169ba93cba1e3d0bd2026b92809f0999ccaf05a2756'),
    ('transaction_17', 0x0057e858, '3568ff89e36aa9d1c6c96aa976f17f84df2cde69c6849532a1b07c929f9c1086'),
    ('transaction_18', 0x0057e908, '13cac8a42852a5d9eba48306f471f6a45396d4eba82200772bb49908cc9d9114'),
    ('transaction_19', 0x0057e9b8, '587e376f3cad85aa066a990c6ecd2cff3d46d2f84a8acc73027d51e0c5a83a26'),
    ('transaction_20', 0x0057ea68, '0f734660411a9146d1161d5beafba194414569accc16d9106de3ca04dbd4a8f8'),
    ('transaction_21', 0x0057eb18, 'ded9a22bf3993f6318033fc18a7d9d8f640253fcc9d5ab35e4ede97560efc79e'),
    ('transaction_22', 0x0057ebc8, '61bfeeeeca31f4ad220685894e87e12f47006dcdc9674c7993a977e9c03c0d9f'),
    ('transaction_23', 0x0057ec78, '6cae95f05447514ee28e38ae041c942360d7883842c267428ca7441ffb7e90f6'),
    ('transaction_24', 0x0057ed28, '702054265e539c0a78670a55ce43f61b5f120424660eb32329727fc1de0073ca'),
    ('transaction_25', 0x0057edd8, '9a499fca8fccc589068c0b9c56ac37f1ca1d123758c30125a57108966c0541eb'),
    ('transaction_26', 0x0057ee88, 'f38d37cdbbf36c9ed4b3bbc88ab9effcbe880c1d319764d1670535ea929ed925'),
    ('transaction_27', 0x0057ef38, 'ae1b636f385abeff4588e7040729693a9028d16454a5a2abc6e41134abb5c436'),
    ('key_0', 0x0053cc48, '919826844c014fb40314ba43a5faf2c9a710ae15118b3f8ef99cdba60c1f420a'),
    ('key_1', 0x0053ccf8, '585361517e61c010bf6f911140d09d5777ee5ce2d1fa4f15c0a972d8af2632f4'),
    ('key_2', 0x0053cda8, '53210a430c6895e1031c66d0924b601701b14ff7b9d8d8b47f90d13b39d427c0'),
    ('key_3', 0x0053ce58, 'b9f3ce56eccc6ffdb0e71011382eac05eee21045c862ae843054120910cf9381'),
    ('key_4', 0x0053cf08, '36eba6785a9e23cb9f2ad88daf7c1031c8541361e9c850521a97ebef979da560'),
    ('select_0', 0x0055ae60, '1ed7946032eb22934b90aa92a9e74f53319f35528c0a747a05aa34b7247881cc'),
    ('select_1', 0x0055af10, '8956e614e7e4ffc38dd673fb30b9886d61a1c1e3f1964a321aa5710bdb1b9f7e'),
    ('select_2', 0x0055afc0, '0620e7d62b973a80ee76b9bef30fad0f248eaa0e448a353c857c33224f203b5d'),
    ('select_3', 0x0055b070, 'fa5edefa0cfa4644fbdd96b029ed0f491e3c6dc7466b9e6c32eb6b4a9c354568'),
    ('substitution_0', 0x00515928, 'd2a072b471745fdf2672eb7054c14e4bed8a3cbcc4edbb108521277d5dd30d8b'),
)

# lg3: the native player editor's 26 attribute controls stay numeric (Create Player, Edit Player,
# Franchise Edit Player, MyCareer Create Player). Same fields as COLUMNS; guarded as retail, never edited.
EDIT_CONTROLS = (
    ('edit_0', 0x005639f0, '2eff5720a5564b6f2410cd5e5372ed8b04b589e7c0cc8868648910c6180eafcf'),
    ('edit_1', 0x00563aa0, '603f9bac0870707fcfcf79113b1732eb63d2ca1f92abaae7ec19fb804835188e'),
    ('edit_2', 0x00563b50, 'ecf21b0d63f5f1d5d089727c66db4def4fc1c0079d326b5514d66112311d784f'),
    ('edit_3', 0x00563c00, '695e12c16eebf0f923af30039e35ebb8d4bc5025c87b867071b19dcfa351b38d'),
    ('edit_4', 0x00563cb0, '4ad71647d7310eb5e888176dffe920b072246f22afb4023f541cd5a7cfcded24'),
    ('edit_5', 0x00563d60, 'b60dc6e0c7eccbe4fe460b0f64fa6e54eb5135ec10a9c404e350929b54540a44'),
    ('edit_6', 0x00563e10, '23bc6dd58532e86837a787a31ef236f208f081f17fad4b2e411e4aadbf4a7e1a'),
    ('edit_7', 0x00563ec0, '2a73b307908ed5c921dfa71fd710b9abe5d09b43c08ee6f5f94f4a9c7ac6776f'),
    ('edit_8', 0x00563f70, 'f02b9cd6dc2c4ab3ac22f6334fad5142f2967299b304a8be7f6d9fe44334b0ee'),
    ('edit_9', 0x00564020, '8bf740cd3c56877c5471295fdc2cf8cff3ee2872f47ab4be0a88b55aac1e45f4'),
    ('edit_10', 0x005640d0, '9b6ec87406ca2315472a9bc568d8c434edc12d1e6943616c9470047c439efbd8'),
    ('edit_11', 0x00564180, '1834450be7be691ab8d74b73fc41b5f121e325181f4967fa10930ea5aa6b44a0'),
    ('edit_12', 0x00564230, 'f43c623c9841c5c1bece61d8853dff5bad74cd27288338e42588e704a67d6366'),
    ('edit_13', 0x005642e0, 'c7039bdbcaeb3ba251705692d5ae9715b45d65e7eaef4408fa9a30f48f6aafa1'),
    ('edit_14', 0x00564390, 'f9f2fe20b12a30cea23116c60dfd095e45c1fd2cbfa5f4d0fecde359bb2a631f'),
    ('edit_15', 0x00564440, 'b41bf6c3d116e8efc99c4fea3d39bdf917e9426c3572004c3e3bf1739c191aac'),
    ('edit_16', 0x005644f0, '36bcd8b844a4c0c24207d32107a69d78fbd1e4758638977b39bab4d78051aa52'),
    ('edit_17', 0x005645a0, '10c0ee8eeb0063d6faa03f0636d77c1aecaf6d6828f15cbf2e8c3f6fba8becaa'),
    ('edit_18', 0x00564650, '6280258a426cee47eb96eb057bf5b9336879bc1c7070a6e98badee72f29a5612'),
    ('edit_19', 0x00564700, '3566681b8adb6584d936a7ecc5d73dc73fa5587078a050ae83248e84d4132e61'),
    ('edit_20', 0x005647b0, 'b178f8b9207c8b33f388c3e7b64046262edb95ad9c597b62fe2214e65f2a4e7e'),
    ('edit_21', 0x00564860, '7dd23712f3219b8f79385d436c6e31720c0656c08e24142faeca9e333e9713ee'),
    ('edit_22', 0x00564910, '22a459c89c2ace980bd533fb569eab8b45cba79bf7a68a77e67d860e64ed6c32'),
    ('edit_23', 0x005649c0, 'ae2952e08c72f16c7e66b9412f831b28a28961de8dc993b501dd0e1cc03dc716'),
    ('edit_24', 0x00564a70, '5b379f324979cd80d48fb4478df8e02f9f7d50444a7ed95cc71b1735cbc8fc1e'),
    ('edit_25', 0x00564b20, '53f6d263007f95dcd193095d345e7779c033fcf78149d7e967173401fe1eb3bc'),
)

# label, immediate VA, original format VA, SHA-256 of opcode + immediate + 10 context bytes.
LITERALS = (
    ('player_card_attributes', 0x0032057e, 0x00ea2e58, '9693fab47abc9994865b806a0f8ed89a152ef7477b1ce2e0e9e723cf736a215c'),
    ('depth_chart_attributes', 0x00243641, 0x00e889a0, 'cc8addf6196d7c2dd4c997001fa806a5d0669dfcaefbba7725914629219ac999'),
    ('weekly_matchup_attributes', 0x002af287, 0x00e967e8, 'b946224fc20c5bd4644d3e0f2a4db2d53f545bafcfb286275c6ea7c3733892b9'),
    ('weekly_prep_second', 0x002b0a5b, 0x00e967e8, '5ce6af6984274d024664d2c8c501006d8dd20fb1982814d7ac89e2e0a652b89d'),
    ('weekly_prep_first_third', 0x002b0a7e, 0x00e967e8, 'f4eb26a41fe8240dfcc0cf070e81d843e3abf1b769cad57ccec5044aa48b7f0d'),
    ('overlay_ratings', 0x0006adac, 0x00e6226c, '33d8cd8c6178a3d3cf456587c4d0178418b4428cf3f287f34d8bf110fbbca025'),
    ('scouting_attributes', 0x0035ecc7, 0x00eb5b0c, '03caa2dd5d648166697bc220bcc645b15c55c10d9a2aea27ba6319fe3d986553'),
)

# lg3: the MyCareer Upgrades line and prospect tier labels are editing/creation text and stay numeric.
CAREER_NUMERIC = "%s: %u. Cap %u. Cost %u XP. Balance %u XP."


def _require(ok, message):
    if not ok:
        raise lg.LetterGradesError(message)


def format_va(payload):
    found = lg.allocations(payload)
    _require(bool(found), "install the base letter grades first")
    return lg.labels(found["code"]["va"], found["read_only"]["va"])["fmt_grade"]


def fixed_sites(fmt):
    return ([(name, va, lg.RETAIL_FLAGS, lg.GRADE_FLAGS) for name, va, _ in COLUMNS]
            + [(name, va, struct.pack("<I", old), struct.pack("<I", fmt))
               for name, va, old, _ in LITERALS])


def guideline_bytes(threshold, bands=lg.DEFAULT_BANDS):
    # Preserve the distinct 40/30 filters without printing numeric rating thresholds.
    qualifier = "higher" if threshold == 40 else "lower"
    return f"{lg.grade_for(threshold, bands)} ({qualifier})".encode("utf-16le").ljust(lg.GUIDELINE_SLOT_BYTES, b"\0")


def sites(payload):
    out = fixed_sites(format_va(payload))
    bands = lg._owned_state(payload)[2]
    for va, threshold in lg.GUIDELINE_SLOTS[-2:]:
        old, new = lg.guideline_slot_bytes(threshold, bands), guideline_bytes(threshold, bands)
        if old != new:
            out.append((f"trade_low_threshold_{threshold}", va, old, new))
    allocation = progress.allocation(payload)
    _require(allocation is not None, "install the progression owner first")
    # jnz +5 -> jnz +0: either branch now reaches mov edx, %R. Flags/registers unchanged.
    out.append(("progression_all_attributes", allocation["va"] + 8, b"\x05", b"\x00"))
    return out


def check_guards(payload):
    image = XbeImage(payload)
    fmt = format_va(payload)
    for name, va, digest in COLUMNS:
        raw = bytearray(image.read(va, 0xB0))
        _require(bytes(raw[:4]) in (lg.RETAIL_FLAGS, lg.GRADE_FLAGS), f"foreign {name} flags")
        raw[:4] = lg.RETAIL_FLAGS
        _require(hashlib.sha256(raw).hexdigest() == digest, f"foreign {name} descriptor")
    for name, va, digest in EDIT_CONTROLS:
        raw = image.read(va, 0xB0)
        _require(raw[:4] == lg.RETAIL_FLAGS, f"{name} is graded; editing controls stay numeric (rebuild from the original)")
        _require(hashlib.sha256(raw).hexdigest() == digest, f"foreign {name} descriptor")
    for name, va, old, digest in LITERALS:
        raw = bytearray(image.read(va - 1, 15))
        _require(bytes(raw[1:5]) in (struct.pack("<I", old), struct.pack("<I", fmt)), f"foreign {name} format")
        raw[1:5] = struct.pack("<I", old)
        _require(hashlib.sha256(raw).hexdigest() == digest, f"foreign {name} context")
    _require(lg.status(payload) == "applied", "foreign base letter grades")
    _require(progress.status(payload) == "applied", "foreign progression owner")
    from . import nfl2k5_my_career as career
    from . import nfl2k5_my_career_mode as mode
    if mode.recognized(payload):
        _require(career.status(payload) == "applied", "foreign MyCareer owner")


def status(payload):
    try:
        check_guards(payload)
        return rdata.status(payload, sites(payload))
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        return "foreign"


def reservations(payload):
    return [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                 basis="pinned presentation " + name)
            for name, va, before, _ in fixed_sites(0)]


def apply(payload):
    check_guards(payload)
    edits = sites(payload)
    state = rdata.status(payload, edits)
    _require(state != "foreign", "mixed/foreign all-rating display sites")
    if state == "applied":
        return payload, {"owner": OWNER, "already_applied": True, "changed_bytes": 0}
    # Validate everything before mutating, then reseal the two existing owners.
    requests = space._validate(payload)[2]
    result, receipt = rdata.apply(payload, edits, OWNER)
    buf = bytearray(result)
    space._seal_scaleout(buf, requests)
    result = bytes(buf)
    _require(status(result) == "applied", "all-rating presentation postcondition failed")
    return result, {**receipt, "owner": OWNER, "already_applied": False,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "columns": len(COLUMNS), "format_sites": len(LITERALS),
                    "numeric_edit_controls": len(EDIT_CONTROLS), "mycareer_text_numeric": True,
                    "gameplay_values_changed": False}

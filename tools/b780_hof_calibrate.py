#!/usr/bin/env python3
"""Hall of Fame rule calibration against real careers (job j6-hof, b780): data, fit, replay, seeds.

The rule itself lives in ``mod_editor/core/nfl2k5_hof_rules.py``; this tool builds the evidence it was fitted on and
re-checks it. Everything except ``fetch``, ``build-data`` and ``roster-check`` runs offline from the checked-in dataset
``data/nfl2k5_hof_calibration_2026.json`` (schema ``nfl2k5_hof_calibration/v1``: one row per retired player, 1999-2025).

  evaluate                      recall on real inductees and false positives on notable non-inductees, by split and position
  replay [--from Y --to Y]      the yearly Hall of Fame classes the rule makes from real retirees (default 2010 to 2026)
  franchise [--to Y]            the classes made from the real retirees the real committee has not judged yet (2021 on) and who are
                                not on the game roster, year by year from the first franchise close (season 2026)
  roster-check --image ISO      read the game roster (read-only) and write data/nfl2k5_hof_roster_check_2026.json: which retirees are
                                on it (same name and birth date), so they are not seeded twice
  candidates [--out FILE]       the seeded pending candidates as data/nfl2k5_hof_candidates_2026.json (for the history seed)
  search [--samples N]          reproducible random search of the weights under the acceptance limits; ranks the shipped rule
  sensitivity                   one weight at a time, +/-20 %
  sim-proxy --runs DIR          the same rule on the game's own simulated seasons (hn1 runs): the franchise-career regime
  fetch --cache DIR             download every pinned input (network); check-cache --cache DIR verifies them
  build-data --cache DIR        rebuild the dataset from the pinned inputs (deterministic) and write it

Sources are pinned by SHA-256: the Wikipedia pages at fixed revisions (Hall of Fame list, award lists, All-Pro and Pro Bowl
pages) and the nflverse release files (draft_picks, stats_player_reg 1999-2025, rosters 2000-2026, CC-BY-4.0). A text that
does not match its pin stops the build.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import io
import json
import random
import re
import sys
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions_history as champions  # noqa: E402
from mod_editor.core import nfl2k5_hof_rules as rules  # noqa: E402


# --------------------------------------------------------------------------------------------------------------------
# pinned inputs (SHA-256 of the exact text or file read; Wikipedia revisions are fixed oldids)
PINS_WIKI = {
    'hof_list': {'title': 'List of Pro Football Hall of Fame inductees', 'revision': 1373268870, 'sha256': 'fa4239c662c72d4e90ae2295bf8921f051661ce740329afca4cc88a31ebee303'},
    'mvp': {'title': 'AP NFL Most Valuable Player', 'revision': 1376867134, 'sha256': 'f4751b025145a585e9e7a195d8d42264561a53a24c58abc4aa72945618c67c2f'},
    'opoy': {'title': 'AP NFL Offensive Player of the Year', 'revision': 1352673809, 'sha256': '9787e2846d3b869b2653b0f0e99f0913fe33cc55321984766db0a180992f83cc'},
    'dpoy': {'title': 'AP NFL Defensive Player of the Year', 'revision': 1377718854, 'sha256': 'a8c8cd4a86dbf6ffe5075a8701f16fd43dcbac16cd949494c6b4c465df80f26d'},
    'roy': {'title': 'AP NFL Rookie of the Year', 'revision': 1370823405, 'sha256': '73fa8c2b85abc093fac0b600b341387acb21a236642765875062e132582554ee'},
    'rushing': {'title': 'List of NFL annual rushing yards leaders', 'revision': 1376209458, 'sha256': '3e1a7f8949e3b62e16c0768b215de47ff0330a3a86d2395ea14217189df47e4f'},
    'sbmvp': {'title': 'Super Bowl Most Valuable Player', 'revision': 1370881027, 'sha256': '1c48f3ae996e3ba4569eeb2a2c1833add144687a9d3af6c3a0d3191ac839bc6c'},
    'sbchamps': {'title': 'List of Super Bowl champions', 'revision': 1377491145, 'sha256': 'e6c0af384434e85a1481daa5021d2ed69e0b60c7450d44394a9d682b509f242f'},
    'allpro_1999': {'title': '1999 All-Pro Team', 'revision': 1361417825, 'sha256': '0ecd5ff51f1e564e9a6adef041f9ae1e6ce75aac3aa352d4722331f0fa0bfb24'},
    'allpro_2000': {'title': '2000 All-Pro Team', 'revision': 1382104193, 'sha256': '6e7264c3fb7f8e33184193f880bfac62b9b43193bc575532591992407a5af240'},
    'allpro_2001': {'title': '2001 All-Pro Team', 'revision': 1356228439, 'sha256': '1b975adf1148715aaf511c14dfb8df3b7c48c999a124b34cb4953874ecb460bd'},
    'allpro_2002': {'title': '2002 All-Pro Team', 'revision': 1360478942, 'sha256': 'e814953ba16741b034725d37ec49f4ddaca6cb961246d1dc53308f5c622a373f'},
    'allpro_2003': {'title': '2003 All-Pro Team', 'revision': 1355745347, 'sha256': '6ec69141de5413f6df6168f9f56ff4298b1a6067f2a997d2b1ab224f44f54056'},
    'allpro_2004': {'title': '2004 All-Pro Team', 'revision': 1356243996, 'sha256': '913e72ef34f2fb192e484289a3b9ea2a1492e3c17553cd364f4034aebae21f1c'},
    'allpro_2005': {'title': '2005 All-Pro Team', 'revision': 1365801931, 'sha256': 'e53cfec498f2ca83f8e1e973ca76c5f6003825ce21ce70411866318908f49d24'},
    'allpro_2006': {'title': '2006 All-Pro Team', 'revision': 1355753615, 'sha256': 'a51d130b0752690efa55a3c612a1cfbbe2c166cdf8ffe8f14901ca69fff528ca'},
    'allpro_2007': {'title': '2007 All-Pro Team', 'revision': 1365833129, 'sha256': 'b04dc8d8d6e3cf88f661122b27772576b02ad81412ea4b8580557781357fed86'},
    'allpro_2008': {'title': '2008 All-Pro Team', 'revision': 1355763536, 'sha256': '3ed4013ec9d5a9e27df79255868fa3fcd725b6f597a139d43421b955713b08c0'},
    'allpro_2009': {'title': '2009 All-Pro Team', 'revision': 1355770994, 'sha256': '153968625f9f27181c5ab27ec8f1ea39b01d7ca98193b5a1f7a7e25542dfe36c'},
    'allpro_2010': {'title': '2010 All-Pro Team', 'revision': 1365852029, 'sha256': '48ea6fab2011bfe9ef00e57bbcac4c1513699e49ae06d0301db36f945e30436c'},
    'allpro_2011': {'title': '2011 All-Pro Team', 'revision': 1355782233, 'sha256': '698b894217acfe9c65b3c3babd28a3fcda86c37aa3aa22339f5645482b1eeb58'},
    'allpro_2012': {'title': '2012 All-Pro Team', 'revision': 1365868396, 'sha256': '6117017c48585c16601b4807892bc4b872723f63bcbe904aaf82d8042649fdeb'},
    'allpro_2013': {'title': '2013 All-Pro Team', 'revision': 1365872775, 'sha256': '7ad6bfc713f1fe15fbafddaf7f286ed45c6fa214e490f8ab00530513bd75e6a2'},
    'allpro_2014': {'title': '2014 All-Pro Team', 'revision': 1365880786, 'sha256': '3fd8d6846b6ace2dae0718b08c91747fca733f7c54188e1b85b9d7c0b3e01430'},
    'allpro_2015': {'title': '2015 All-Pro Team', 'revision': 1365882548, 'sha256': 'f2c61a01b3e4ac2ea3b72f070cd32be80f8131014ef556cb47a73051fc67e810'},
    'allpro_2016': {'title': '2016 All-Pro Team', 'revision': 1365896928, 'sha256': 'ff69524c5a873ba796b73935522ed0d11c2afc75e9b5069886b6497112799532'},
    'allpro_2017': {'title': '2017 All-Pro Team', 'revision': 1355877219, 'sha256': 'c35a9e2253c30a6c0ae8679986657ea51c9dbd19b820b4590703132892b2acd6'},
    'allpro_2018': {'title': '2018 All-Pro Team', 'revision': 1378101433, 'sha256': 'f0b82718118d2cb9866773181386bc4c69c8b549311a2d86602daa2826a91978'},
    'allpro_2019': {'title': '2019 All-Pro Team', 'revision': 1355881242, 'sha256': '17bee4a1b361d1620d1aac069cd376a1cdd8425ffffe9794b721a5613d9009df'},
    'allpro_2020': {'title': '2020 All-Pro Team', 'revision': 1365947817, 'sha256': '70d9293a8ee6347616dfb38c2574e88b8d6ffda3dbc6cf5746e3d1163dcdf6d3'},
    'allpro_2021': {'title': '2021 All-Pro Team', 'revision': 1358493784, 'sha256': '0288302dcb0171fc7da5d42ddead01092849e2bfdb842d3ffb82fc09c49c3716'},
    'allpro_2022': {'title': '2022 All-Pro Team', 'revision': 1355887133, 'sha256': '5daa81613aa60666ab2f6a166e92c5fe376f0159c232fbb259f1f784923c57ca'},
    'allpro_2023': {'title': '2023 All-Pro Team', 'revision': 1355889686, 'sha256': '7705d4cc26c60f16709dcb9cca3a602995805357aaff6618afbc29592578e116'},
    'allpro_2024': {'title': '2024 All-Pro Team', 'revision': 1358523027, 'sha256': '86297cc899f673ae9d804e76a09d1e9c40926b2c39159cecacd13925600d2363'},
    'allpro_2025': {'title': '2025 All-Pro Team', 'revision': 1378101534, 'sha256': '8a7d975b686c8b6eb5ef8548fecdba0fdb8707c71ca735d250400d60b6badfb4'},
    'probowl_1999': {'title': '2000 Pro Bowl', 'revision': 1345335019, 'sha256': '45234817ba3ea165a7b504c1ddea71c0f67187b31c08cb638f34b2da1750f694'},
    'probowl_2000': {'title': '2001 Pro Bowl', 'revision': 1341513223, 'sha256': 'f493dc154e1e7231bf8b107a3bf2273faec585882fa8b835ac38d4ca9c9a33c9'},
    'probowl_2001': {'title': '2002 Pro Bowl', 'revision': 1341513242, 'sha256': 'bd9296059758e745320614557169238c20c87ce1a1342af3c5a50e716ef98ddd'},
    'probowl_2002': {'title': '2003 Pro Bowl', 'revision': 1341513270, 'sha256': '3dba1e620e0479a983ae62d45b5efda1c6adf81e1d667d86372235871c46dbdc'},
    'probowl_2003': {'title': '2004 Pro Bowl', 'revision': 1378765408, 'sha256': 'ea8899273b7a1df0584eda8e4780ef3b58625cb5d29b1e7570a4584c8208e07b'},
    'probowl_2004': {'title': '2005 Pro Bowl', 'revision': 1368422392, 'sha256': 'a2136684130e93cb8421c0fa7e605bd818db9005709556ed53cbdd410b88640a'},
    'probowl_2005': {'title': '2006 Pro Bowl', 'revision': 1378291603, 'sha256': '66bda1d899bb39c21d263e6902570ddd007b87d8f7bd2e9d9280ff390a401123'},
    'probowl_2006': {'title': '2007 Pro Bowl', 'revision': 1341513366, 'sha256': 'abfbae4b2378fc7ee0258a180f7eefee451199fed7738a56bc92098cff313d4c'},
    'probowl_2007': {'title': '2008 Pro Bowl', 'revision': 1341513400, 'sha256': '9536dd2f3b82b1a78945c40449ff6f4b048a8c36fdf3fcdb73206c3079f6176e'},
    'probowl_2008': {'title': '2009 Pro Bowl', 'revision': 1318540744, 'sha256': '1301a37ca1dc34ab1e8271c6cea6c38c5f24ac8bf8223997424f57ba918e5ae3'},
    'probowl_2009': {'title': '2010 Pro Bowl', 'revision': 1358256779, 'sha256': '22a9da83c2768298e7f4fe0372df111ace38460517d314ed519292f854810071'},
    'probowl_2010': {'title': '2011 Pro Bowl', 'revision': 1369248723, 'sha256': '4a99cb6ed55277d116998d5e21acefda448728fdc518f9a3adbc75029267b27b'},
    'probowl_2011': {'title': '2012 Pro Bowl', 'revision': 1341513654, 'sha256': 'd66353974fba8f7edd882ae68e33ebd5f837d7c5bb893f099a00816d3cd3d836'},
    'probowl_2012': {'title': '2013 Pro Bowl', 'revision': 1341513685, 'sha256': 'ff472fc301477af2e9a132dc9fa127e7274915c8960b0bfc984058a127f70f6c'},
    'probowl_2013': {'title': '2014 Pro Bowl', 'revision': 1341682180, 'sha256': 'ff6ab02bec238158387a15e4451e7617c5987dd75c4f383417468d9cc4d3ddc6'},
    'probowl_2014': {'title': '2015 Pro Bowl', 'revision': 1375436577, 'sha256': '6f63314884b5004fd78f938ce73c7e76147fb7443139567f01c188e738ac8754'},
    'probowl_2015': {'title': '2016 Pro Bowl', 'revision': 1371677922, 'sha256': '6ed7d4d0eb52857caa8bf125179dcb4614d7a2491aa0ce4ff4e5038297ab8a42'},
    'probowl_2016': {'title': '2017 Pro Bowl', 'revision': 1341513758, 'sha256': 'b05a1c865d3d18ef6fe5c3da27e675c9e0b59fc428477cd52f12eb4ace5b53b2'},
    'probowl_2017': {'title': '2018 Pro Bowl', 'revision': 1341513779, 'sha256': '616f53c68f06f9a63b7dae6219f0e2cccfc398a8e23a94ce12b0c6de2d739936'},
    'probowl_2018': {'title': '2019 Pro Bowl', 'revision': 1378101475, 'sha256': 'a017aacd42b2c0b577dd2be646f1f1e3ad8fb02d50c05cf760a40e78b5d4567d'},
    'probowl_2019': {'title': '2020 Pro Bowl', 'revision': 1341513816, 'sha256': '86614585fa950861727048c9bc32c82f774c6b9fa654eb4483518945e352cdc6'},
    'probowl_2020': {'title': '2021 Pro Bowl', 'revision': 1374788640, 'sha256': '66567dd280369824f94a432d52c1f763fb3226ec5703ce816344f5d56de6eff0'},
    'probowl_2021': {'title': '2022 Pro Bowl', 'revision': 1341513858, 'sha256': '28000225fa5d86351e86a62bec742bbce09658daa723df958485e00b6f316c1d'},
    'probowl_2022': {'title': '2023 Pro Bowl Games', 'revision': 1371725902, 'sha256': '50f864726341f77591b1c5d171fdf3538b6f050081e02769cbc450e05708bc7d'},
    'probowl_2023': {'title': '2024 Pro Bowl Games', 'revision': 1360066478, 'sha256': '5c5eaa29030b3577edd3b6bd223eacd1e95cf138827a01bfd5ccb05ec16cb35f'},
    'probowl_2024': {'title': '2025 Pro Bowl Games', 'revision': 1341513932, 'sha256': '9ed4ca5bca299e3218e147bc2be10da297645eac32fdab8d2071fe0b3d6cf7f3'},
    'probowl_2025': {'title': '2026 Pro Bowl Games', 'revision': 1378060126, 'sha256': 'b18deb8bc8943f70ccc2a0df592ea6af8c050a0a3bda1d5ec251a74252bf6f60'},
}

PINS_NFLVERSE = {
    'games': {'file': 'games.csv', 'sha256': 'dcad503d5395076fd5d54b44e7b2253970224bda8d6b14a3ccfd05021b75bb3a', 'extract': 'postseason through 2025: season, type, teams, scores, starting QB ids', 'url': 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'},
    'draft_picks': {'file': 'draft_picks.csv', 'sha256': 'cc35472c1b12b58ea9588e2174dfd92b3cd02cf6b4fc8d31cb9757a4ea3e5f9f', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.csv'},
    'stats_player_reg_1999': {'file': 'stats_player_reg_1999.csv', 'sha256': 'ea3f2092fcc04fa9141ef0976d51eec9e9f8f2448786605a3de03aa89837fc76', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_1999.csv'},
    'stats_player_reg_2000': {'file': 'stats_player_reg_2000.csv', 'sha256': '955a8b895920a2b01ecf02cb1eb29c2df7a9385c5e11385ae09107963dc0cf9a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2000.csv'},
    'stats_player_reg_2001': {'file': 'stats_player_reg_2001.csv', 'sha256': 'dfa161eb8a851c8cc3ff0088f24810daf47db4f098c3d920a60836cd7312bf4a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2001.csv'},
    'stats_player_reg_2002': {'file': 'stats_player_reg_2002.csv', 'sha256': 'd81c84f3694d8e3e5f228a854aa3caf72d9eeb52f4eb1d312f47d5cbc40d47d4', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2002.csv'},
    'stats_player_reg_2003': {'file': 'stats_player_reg_2003.csv', 'sha256': 'b25c71e80850a9b9abd1147eb073bd196b32f4a4ae83d2d2702abc83b0f147d3', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2003.csv'},
    'stats_player_reg_2004': {'file': 'stats_player_reg_2004.csv', 'sha256': 'e8c8353a2826e5cab14dc27c20cae9286bd671c6ddf7e0cf4eb244a07459d84b', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2004.csv'},
    'stats_player_reg_2005': {'file': 'stats_player_reg_2005.csv', 'sha256': '09968f4edcb50292741e1b3815e76a1e0d08ea97af5e697f2846b97085db733a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2005.csv'},
    'stats_player_reg_2006': {'file': 'stats_player_reg_2006.csv', 'sha256': 'e2489849c95d875326e73da0916550e73fe5393216423120b84560b93cc09979', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2006.csv'},
    'stats_player_reg_2007': {'file': 'stats_player_reg_2007.csv', 'sha256': '40545c443bdf4020d522b740f7ad16e441f23d08a7d726729e9b2be035366793', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2007.csv'},
    'stats_player_reg_2008': {'file': 'stats_player_reg_2008.csv', 'sha256': '1f79617f3448b0467e9cb4a1d73d171adb0f4fa8df92969d96c70030632d0c55', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2008.csv'},
    'stats_player_reg_2009': {'file': 'stats_player_reg_2009.csv', 'sha256': '1d18048fed34be4faf476b07de46f4c158e419e03cfb12deb54b93cc26fdd130', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2009.csv'},
    'stats_player_reg_2010': {'file': 'stats_player_reg_2010.csv', 'sha256': 'a0ea4f139f49cb0542a2f74a4a72a2a72a8eee37f80c81f073d878abc97159b8', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2010.csv'},
    'stats_player_reg_2011': {'file': 'stats_player_reg_2011.csv', 'sha256': 'f8a8e44ccf198570e3c1b05b7dd1430c7d05bdd977dd85a42398b3e97013dff4', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2011.csv'},
    'stats_player_reg_2012': {'file': 'stats_player_reg_2012.csv', 'sha256': '6cdfbf3b291cf1349b33fe8e90542d8ae54cca3726769866f94feaf866b329b5', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2012.csv'},
    'stats_player_reg_2013': {'file': 'stats_player_reg_2013.csv', 'sha256': '342fd27eef619a2aec4a74abf8f689e6b14fab526ae1300095b2654a3981882b', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2013.csv'},
    'stats_player_reg_2014': {'file': 'stats_player_reg_2014.csv', 'sha256': '9f7aee274dddd6b27ec66ae493507aebf5779ed81d4735a53b87bbf28030f7a1', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2014.csv'},
    'stats_player_reg_2015': {'file': 'stats_player_reg_2015.csv', 'sha256': '91cc6edbfe16bdc08c680c58ea6d8525c6b7668ef9b94ebdcc6ef9156fcd92d0', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2015.csv'},
    'stats_player_reg_2016': {'file': 'stats_player_reg_2016.csv', 'sha256': '17063fa01736c41b30ffbb15a284f64611fd8a517bfae5d4cdb0ebb19da78801', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2016.csv'},
    'stats_player_reg_2017': {'file': 'stats_player_reg_2017.csv', 'sha256': 'ee3ed8e1b9f7998b7b7b43ec1139e1d69186818ad3e2ce100e4467f163f1ca3c', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2017.csv'},
    'stats_player_reg_2018': {'file': 'stats_player_reg_2018.csv', 'sha256': '8d66bc2dde26951038f6cb68edfcc9082c36423ec7df8185aa7b1b61906c866b', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2018.csv'},
    'stats_player_reg_2019': {'file': 'stats_player_reg_2019.csv', 'sha256': '324b77e6027839c15bad5d32a6d83d07f998e71e0a1e682a37543efeb5219064', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2019.csv'},
    'stats_player_reg_2020': {'file': 'stats_player_reg_2020.csv', 'sha256': 'ac90bb97fd0cb8f8ae7783226c50f5db64bb375e99eaedbd32e97b8b16cf1a94', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2020.csv'},
    'stats_player_reg_2021': {'file': 'stats_player_reg_2021.csv', 'sha256': '2edb2190fa41c92eed8e997c0ba1ff6c737a0fe6d996129487fe34cb63264c6f', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2021.csv'},
    'stats_player_reg_2022': {'file': 'stats_player_reg_2022.csv', 'sha256': 'af2d534b208af43d4b17bcba242dc949f2d40b367253f78c882c19eee9dfc937', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2022.csv'},
    'stats_player_reg_2023': {'file': 'stats_player_reg_2023.csv', 'sha256': '0cc79526a678907817713a7f603b75c4424a1cd4dfc98daa2b3018af80312b9c', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2023.csv'},
    'stats_player_reg_2024': {'file': 'stats_player_reg_2024.csv', 'sha256': 'fbad4e9f1b892e3870a51a4eea808d692cde14ed6dbacd67cce3a0def8ddcbaa', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2024.csv'},
    'stats_player_reg_2025': {'file': 'stats_player_reg_2025.csv', 'sha256': 'aaa8559478dd8d58569c93e278239e70e9411e79ee649c99d8d506030cd42b12', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2025.csv'},
    'roster_2000': {'file': 'roster_2000.csv', 'sha256': 'c4b205ea7b5506c72ba38f246b7e812ffedc9612e320a4099f5c57ec26d0e30f', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2000.csv'},
    'roster_2001': {'file': 'roster_2001.csv', 'sha256': '33f2579b74b295f60186a5cc988f8b0292e0f9a302eeb20ce2e47ee90f40b445', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2001.csv'},
    'roster_2002': {'file': 'roster_2002.csv', 'sha256': 'a08b5d5fe070c0819bc27ac15ca3d47c7b2dd504fbd6c62d34e00c16a082021a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2002.csv'},
    'roster_2003': {'file': 'roster_2003.csv', 'sha256': '6d9f530bcbacbf9de2d2a220987d3beb55419155f8661355b1fbe405ab6722ca', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2003.csv'},
    'roster_2004': {'file': 'roster_2004.csv', 'sha256': '4d9c9041c1b1cca9eb757baa6c2d59a19c3c428a3ea094832231df37e219e078', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2004.csv'},
    'roster_2005': {'file': 'roster_2005.csv', 'sha256': 'c88034255064b5f1ec1aa76175ca6b69ad7857904d08e13eb77c23eef592ced2', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2005.csv'},
    'roster_2006': {'file': 'roster_2006.csv', 'sha256': '4ec3ed1331da5046fb4a3136720374a93d98ea502950c1c010e1d0535952b2d1', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2006.csv'},
    'roster_2007': {'file': 'roster_2007.csv', 'sha256': '1aa1dd25da3616e5ddf31de3b18d4731edb5032ea14c1803b35cc3413186d5dd', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2007.csv'},
    'roster_2008': {'file': 'roster_2008.csv', 'sha256': '6c7f2c475012defda7f260addabde03e90a9ae288ed2fc4aef53ea40ab76eeb9', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2008.csv'},
    'roster_2009': {'file': 'roster_2009.csv', 'sha256': 'd3f9373f22db37a2bb962ae3dc3d15c65f51c2b240f13d241b4fd292aff9721e', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2009.csv'},
    'roster_2010': {'file': 'roster_2010.csv', 'sha256': '0c9dfde110e6c989bbecd830602b2562124b89388e1aac39b5287376f2370dd1', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2010.csv'},
    'roster_2011': {'file': 'roster_2011.csv', 'sha256': '6acc11a2b5f692db03e1945e0329da93f6b5debed3f99feed39eca470ab4cee5', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2011.csv'},
    'roster_2012': {'file': 'roster_2012.csv', 'sha256': '90628fcdadd9f2dde083bc77d41139cedc9fefd1fcc09f2ce8675823de23291b', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2012.csv'},
    'roster_2013': {'file': 'roster_2013.csv', 'sha256': 'abf73c2b1ef10914af78f6b7397338508bd0c9f0372d2f0667a630e06a4484ed', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2013.csv'},
    'roster_2014': {'file': 'roster_2014.csv', 'sha256': 'f3c3e9cced60d99ebdcb410b76ffeda72b207b7045983b7a63f677ad9a34814f', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2014.csv'},
    'roster_2015': {'file': 'roster_2015.csv', 'sha256': '63807a50226a94f6724b3694198b41661c76211707115b2d52975237ebc4ecb6', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2015.csv'},
    'roster_2016': {'file': 'roster_2016.csv', 'sha256': 'c7a57a4816d05ef651f4c56b8209c38b98e3d60582ddd60cb8048ef657472ca1', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2016.csv'},
    'roster_2017': {'file': 'roster_2017.csv', 'sha256': '22584ad80445611edff6dcbc6dce9ab596bdc484430d8aac298725da15697fd4', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2017.csv'},
    'roster_2018': {'file': 'roster_2018.csv', 'sha256': '60c7f1dabb508acc800ef81b4f69892511b1f78246bdb2cca6115a506c523b0a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2018.csv'},
    'roster_2019': {'file': 'roster_2019.csv', 'sha256': 'b00259cfddf2146512569423275dc17e142d31ddb13bfba6b0b826c9d3d810da', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2019.csv'},
    'roster_2020': {'file': 'roster_2020.csv', 'sha256': 'dcf25143db7b54ac488d042b6c24142340effced1d6c8599b2084a9f412b3ed2', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2020.csv'},
    'roster_2021': {'file': 'roster_2021.csv', 'sha256': 'a95e57ebe1df25224a4d19ed43aaffc5c2097a8b369954178b8592537ff77d34', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2021.csv'},
    'roster_2022': {'file': 'roster_2022.csv', 'sha256': '864719595d14909c73bd14110adcdcfc304c6621de9ba34feafb83666fac43c9', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2022.csv'},
    'roster_2023': {'file': 'roster_2023.csv', 'sha256': 'f98283e6ef420babc597092b5483109a4570f9b5f63b7bfcce69643290960b6c', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2023.csv'},
    'roster_2024': {'file': 'roster_2024.csv', 'sha256': '97721aa9092edb15c1357f2dac359dba72f63c81cc0e69408c65c229c91f50c1', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2024.csv'},
    'roster_2025': {'file': 'roster_2025.csv', 'sha256': '531ee5de386037bb17de3e3e3d50f7b4ed08789526bbaae9876fdd3dfb4d04ad', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2025.csv'},
    'roster_2026': {'file': 'roster_2026.csv', 'sha256': 'ec6ad3959ea0846ab9badcf6aeff7a6c2dc83cd24070bbf6ce255b9112cb596a', 'url': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv'},
}

# --------------------------------------------------------------------------------------------------------------------
# inputs: a cache directory with the pinned files (fetch fills it; every file is checked against its pin)
UA = "2k5-mod-studio-hof-calibration/1.0 (offline research tool; https://github.com/cruuz/2k-football-mod-tools)"
FIRST_STATS, LAST_STATS = 1999, 2025
ATTRIBUTION = ("nflverse contributors (https://github.com/nflverse/nflverse-data), CC-BY-4.0; Wikipedia contributors, CC BY-SA 4.0 "
               "(facts only: award winners, All-Pro and Pro Bowl rosters, Hall of Fame classes)")


class CalibrationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise CalibrationError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wiki_url(pin: Mapping) -> str:
    return f"https://en.wikipedia.org/w/index.php?title={pin['title'].replace(' ', '_')}&oldid={pin['revision']}&action=raw"


POSTSEASON = ("WC", "DIV", "CON", "SB")


def games_extract(text: str) -> list[str]:
    """The postseason rows of the nflverse games file through 2025 (season, type, teams, scores, starting QB ids), sorted. The file
    is rewritten every week, so the pin is the digest of these rows, which do not change after the season."""

    rows = []
    for r in csv.DictReader(io.StringIO(text, newline="")):
        if r["game_type"] in POSTSEASON and int(r["season"]) <= LAST_STATS:
            rows.append(",".join([r["season"], r["game_type"], r["away_team"], r["away_score"], r["home_team"], r["home_score"],
                                  r["away_qb_id"], r["home_qb_id"]]))
    return sorted(rows)


def games_extract_digest(raw: bytes) -> str:
    return hashlib.sha256(("\n".join(games_extract(raw.decode("utf-8"))) + "\n").encode("utf-8")).hexdigest()


EXTRACT_DIGESTS = {"games.csv": games_extract_digest}          # files pinned by the digest of an extract, not of every byte


def digest_of(name: str, raw: bytes) -> str:
    return EXTRACT_DIGESTS[name](raw) if name in EXTRACT_DIGESTS else hashlib.sha256(raw).hexdigest()


def source_files() -> dict[str, tuple[str, str, str]]:
    """cache file name -> (pin key, url, sha256) for every input (the games file: the digest of its postseason extract)."""

    out = {}
    for key, pin in PINS_WIKI.items():
        out[f"wiki_{key}.txt"] = (f"wiki:{key}", wiki_url(pin), pin["sha256"])
    for key, pin in PINS_NFLVERSE.items():
        out[pin["file"]] = (f"nflverse:{key}", pin["url"], pin["sha256"])
    return out


def fetch(cache: Path, *, only_missing: bool = True, pause: float = 0.6) -> list[str]:
    """Download every input that is not in ``cache`` (network) and verify it. -> names fetched."""

    import time
    import urllib.request

    cache.mkdir(parents=True, exist_ok=True)
    fetched = []
    for name, (key, url, digest) in sorted(source_files().items()):
        path = cache / name
        if path.is_file() and only_missing:
            continue
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90) as response:
                    raw = response.read()
                break
            except OSError:
                time.sleep(2 * (attempt + 1))
        else:
            raise CalibrationError(f"could not fetch {url}")
        _require(digest_of(name, raw) == digest, f"{name}: the text read does not match its pin ({key})")
        path.write_bytes(raw)
        fetched.append(name)
        time.sleep(pause)
    return fetched


def check_cache(cache: Path) -> dict:
    """Verify every cached input against its pin. -> {"ok": n, "missing": [...], "bad": [...]}."""

    missing, bad, ok = [], [], 0
    for name, (key, _url, digest) in sorted(source_files().items()):
        path = cache / name
        if not path.is_file():
            missing.append(name)
        elif digest_of(name, path.read_bytes()) != digest:
            bad.append(name)
        else:
            ok += 1
    return {"ok": ok, "missing": missing, "bad": bad}


# --------------------------------------------------------------------------------------------------------------------
# parsers (pure text -> data; each is exercised on small fixtures by the unit tests)
def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


_SORTNAME = re.compile(r"\{\{sortname\|\s*([^|}]*?)\s*\|\s*([^|}]*?)\s*(?:\|[^}]*)?\}\}", re.I)
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _blocks(text: str) -> list[str]:
    return re.split(r"\n\|-[^\n]*\n", "\n" + text)


def parse_hof_list(text: str, *, first_row: int = 40, last_row: int = 1620) -> list[dict]:
    """Inductees of the wikitable (players, coaches and contributors alike): first, last, class, position, first/last season.
    The table sits between the ``== Inductees ==`` and ``== Inductees who have played for non-NFL teams ==`` headings."""

    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("{| class=\"wikitable sortable\"")), first_row - 1)
    stop = next((i for i, line in enumerate(lines) if line.startswith("== Inductees who have played for non-NFL teams")),
                last_row)
    body = "\n" + "\n".join(lines[start:stop])
    rows = []
    for block in re.split(r"\n\|-style=\"border-top: 2px solid gray\"[^\n]*\n", body)[1:]:
        m = _SORTNAME.search(block)
        if not m:
            continue
        after = block[m.end():]
        c = (re.search(r"\|\s*(?:rowspan=\d+\s*\|)?\s*(19[6-9]\d|20[0-2]\d)\s*\|\|", after)
             or re.search(r"\|\|\s*(?:rowspan=\d+\s*\|)?\s*(19[6-9]\d|20[0-2]\d)\s*\|\|", after)
             or re.search(r"\b(19[6-9]\d|20[0-2]\d)\b", after))
        p = re.search(r'data-sort-value="([^"]*?)\s+(\d{4})"', block)
        years = [int(y) for pair in re.findall(r"(\d{4})\s*(?:&ndash;|\u2013|-)\s*(\d{4})", block) for y in pair]
        years += [int(y) for y in re.findall(r"\|\|\s*(\d{4})\s*(?:\n|$|<)", block)]
        rows.append({"first": m.group(1).strip(), "last": m.group(2).strip(), "class": int(c.group(1)) if c else None,
                     "position": p.group(1).strip() if p else None,
                     "first_season": min(years) if years else None, "last_season": max(years) if years else None})
    return rows


def parse_award_seasons(text: str, *, lo: int = 1990) -> dict[int, list[str]]:
    """{season: [names]} from a table whose rows hold ``[[YYYY NFL season|YYYY]]`` and ``{{sortname|First|Last}}`` cells."""

    out: dict[int, list[str]] = {}
    for block in _blocks(text):
        s = re.search(r"\[\[(\d{4}) NFL season\|\d{4}\]\]", block)
        if not s or int(s.group(1)) < lo:
            continue
        names = [(m.group(1) + " " + m.group(2)).strip() for m in _SORTNAME.finditer(block)]
        if names:
            out.setdefault(int(s.group(1)), []).extend(names)
    return out


def parse_mvp(text: str) -> dict[int, list[str]]:
    marker = "List of AP NFL Most Valuable Player winners"
    return parse_award_seasons(text[text.index(marker):] if marker in text else text)


def parse_roy(text: str) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    split = text.index("===Defensive===")
    return parse_award_seasons(text[:split]), parse_award_seasons(text[split:])


def parse_dpoy(text: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for line in text.split("\n"):
        m = re.search(r"\{\{center\|\[\[(\d{4}) NFL season\|\d{4}\]\]\}\}\s*\|\|[^\[]*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", line)
        if m:
            out.setdefault(int(m.group(1)), []).append(re.sub(r"\s*\(.*?\)", "", m.group(3) or m.group(2)).strip())
    return out


def parse_rushing(text: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for block in _blocks(text):
        s = re.search(r"\[\[(\d{4}) NFL season\|\d{4}\]\]", block)
        names = [(m.group(1) + " " + m.group(2)).strip() for m in _SORTNAME.finditer(block)]
        if s and names:
            out.setdefault(int(s.group(1)), []).append(names[0])
    return out


def _seed_module():
    spec = importlib.util.spec_from_file_location("nfl2k5_champions_seed", Path(__file__).resolve().parent / "nfl2k5_champions_seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_sb_mvp(text: str) -> dict[int, list[str]]:
    """{season: [name]} for Super Bowls XXIX..LX through the champions seed's pinned parser."""

    return {1965 + n: [row["name"]] for n, row in _seed_module().sbmvp_rows(text).items()}


def parse_champions(text: str) -> dict[int, str]:
    return {row["season"]: row["champion"] for row in _seed_module().champions_rows(text).values()}


def parse_runners_up(text: str) -> dict[int, str]:
    return {row["season"]: row["runner_up"] for row in _seed_module().champions_rows(text).values()}


def _strip_links(text: str) -> str:
    return _LINK.sub(lambda m: m.group(2) or m.group(1), text)


def parse_allpro_first_team(text: str) -> list[str]:
    """Names with an AP first-team selection (selector ``AP`` or ``AP-t``) on one season's All-Pro page, once each."""

    m0 = re.search(r"^==\s*Teams\s*==", text, flags=re.M)
    body = text[m0.start():] if m0 else text
    names = []
    for row in re.split(r"\n\|-[^\n]*\n", body):
        cells = [c for c in re.split(r"\n\|(?!\|)", row) if c.strip()]
        if len(cells) < 2:
            continue
        for part in re.split(r"(?i)<br\s*/?>", cells[1]):
            plain = _strip_links(part).strip()
            sel = re.search(r"\(([^)]*)\)\s*$", plain) or re.search(r"\(([^)]*)\)", plain)
            if not sel:
                continue
            tokens = [t.strip().lower() for t in sel.group(1).split(",")]
            if "ap" in tokens or "ap-t" in tokens:
                name = plain.split(",")[0].strip().rstrip(".")
                if name and name.lower() != "none":
                    names.append(name)
    return sorted(set(names))


def pro_bowl_blob(text: str) -> str:
    """The normalised text of a Pro Bowl page's roster sections (names run together; used only to test a name's presence)."""

    m = re.search(r"^==\s*(AFC rosters?|Rosters)\s*==\s*$", text, flags=re.M | re.I)
    body = ""
    if m:
        end = re.search(r"^==\s*(Number of selections|Selections by team|Broadcasting|References|Officials|Fan balloting|"
                        r"Entertainment|Results|Broadcast)[^=]*==\s*$", text[m.end():], flags=re.M | re.I)
        body = text[m.start():m.end() + (end.start() if end else len(text))]
    if len(body) < 2500:                                     # a page whose rosters sit under another heading
        body = text.split("==References")[0]
    body = re.sub(r"\{\{\s*NFLplayer\s*\|[^|}]*\|\s*([^|}]+?)\s*(?:\|[^}]*)?\}\}", r" \1 ", body, flags=re.I)
    body = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", body)
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)
    return norm_name(re.sub(r"\{\{[^}]*\}\}|<[^>]+>", " ", body))


# --------------------------------------------------------------------------------------------------------------------
# the dataset
COLUMNS = ("name", "pos", "group", "first", "last", "hof", "src", "games", "ptd", "rtd", "ryds", "recy", "rectd", "sack2", "dint",
           "fgm", "ap", "pb", "mvp", "opoy", "dpoy", "oroy", "droy", "sbmvp", "rt", "sb", "active", "club", "birth", "gsis",
           "pyds", "rec", "tkl", "started", "sbl", "pw")
DATASET_SCHEMA = "nfl2k5_hof_calibration/v1"
DATASET = ROOT / "data" / "nfl2k5_hof_calibration_2026.json"
CANDIDATES = ROOT / "data" / "nfl2k5_hof_candidates_2026.json"
PERSON_SCHEMA = "nfl2k5_hof_candidates/v1"
ROSTER_CHECK = ROOT / "data" / "nfl2k5_hof_roster_check_2026.json"
ROSTER_CHECK_SCHEMA = "nfl2k5_hof_roster_check/v1"

CATEGORY_GROUP = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "OL": "OL", "DL": "DL", "LB": "LB", "DB": "DB", "K": "K", "P": "P"}
STATS_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL", "OL": "OL",
               "OT": "OL", "OG": "OL", "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "LB": "LB", "ILB": "LB", "OLB": "LB",
               "MLB": "LB", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB", "K": "K", "P": "P"}
# a source position -> one of the game's 17 position names (display only; the rule uses the group)
GAME_POSITION = {"QB": "QB", "RB": "HB", "HB": "HB", "FB": "FB", "WR": "WR", "TE": "TE", "T": "T", "OT": "T", "G": "G", "OG": "G",
                 "C": "C", "OL": "T", "DE": "DE", "DT": "DT", "NT": "DT", "DL": "DE", "LB": "OLB", "OLB": "OLB", "ILB": "ILB",
                 "MLB": "ILB", "CB": "CB", "S": "FS", "FS": "FS", "SS": "SS", "DB": "CB", "K": "K", "P": "P"}
TEAM_NICKNAME = {"ARI": "Cardinals", "ARZ": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BLT": "Ravens", "BUF": "Bills",
                 "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns", "CLV": "Browns", "DAL": "Cowboys",
                 "DEN": "Broncos", "DET": "Lions", "GB": "Packers", "GNB": "Packers", "HOU": "Texans", "HST": "Texans",
                 "IND": "Colts", "JAX": "Jaguars", "JAC": "Jaguars", "KC": "Chiefs", "KAN": "Chiefs", "LA": "Rams", "LAR": "Rams",
                 "STL": "Rams", "LAC": "Chargers", "SD": "Chargers", "SDG": "Chargers", "LV": "Raiders", "OAK": "Raiders",
                 "LVR": "Raiders", "MIA": "Dolphins", "MIN": "Vikings", "NE": "Patriots", "NWE": "Patriots", "NO": "Saints",
                 "NOR": "Saints", "NYG": "Giants", "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
                 "SF": "49ers", "SFO": "49ers", "TB": "Buccaneers", "TAM": "Buccaneers", "TEN": "Titans", "WAS": "Redskins",
                 "WSH": "Redskins"}
# a club's nickname (the last word of its name on the champions page) -> the roster file's team codes
CLUB_CODES = {"49ers": ("SF",), "Bears": ("CHI",), "Bengals": ("CIN",), "Bills": ("BUF",), "Broncos": ("DEN",), "Browns": ("CLE", "CLV"),
              "Buccaneers": ("TB",), "Cardinals": ("ARI", "ARZ"), "Chargers": ("LAC", "SD"), "Chiefs": ("KC",), "Colts": ("IND",),
              "Cowboys": ("DAL",), "Dolphins": ("MIA",), "Eagles": ("PHI",), "Falcons": ("ATL",), "Giants": ("NYG",),
              "Jaguars": ("JAX", "JAC"), "Jets": ("NYJ",), "Lions": ("DET",), "Packers": ("GB",), "Panthers": ("CAR",),
              "Patriots": ("NE",), "Raiders": ("OAK", "LV"), "Rams": ("LA", "STL", "LAR"), "Ravens": ("BAL", "BLT"),
              "Redskins": ("WAS",), "Commanders": ("WAS",), "Saints": ("NO",), "Seahawks": ("SEA",), "Steelers": ("PIT",),
              "Texans": ("HOU", "HST"), "Titans": ("TEN",), "Vikings": ("MIN",)}
ACTIVE_STATUS = ("ACT", "RES", "DEV", "EXE")                       # on a 2026 roster; "CUT" and "RET" are not


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def build_dataset(cache: Path) -> dict:
    """Rebuild the calibration dataset from the pinned inputs in ``cache`` (see ``fetch``). Deterministic."""

    state = check_cache(cache)
    _require(not state["missing"] and not state["bad"], f"cache is incomplete or does not match the pins: {state}")

    def text(key):
        return (cache / f"wiki_{key}.txt").read_text(encoding="utf-8")

    # ---- drafted players: career totals, All-Pro and Pro Bowl counts, the PFR hall of fame flag
    people = []
    for r in _read_csv(cache / "draft_picks.csv"):
        if not r["to"]:
            continue
        people.append({
            "name": r["pfr_player_name"], "norm": norm_name(r["pfr_player_name"]), "pos": r["position"], "group": CATEGORY_GROUP.get(r["category"], "?"),
            "draft": int(r["season"]), "first": int(r["season"]), "last": int(r["to"]), "gsis": r["gsis_id"], "hof": r["hof"] == "TRUE",
            "pfr_hof": r["hof"] == "TRUE",
            "ap": int(_num(r["allpro"])), "pb": int(_num(r["probowls"])), "wav": _num(r["w_av"]), "games": int(_num(r["games"])),
            "ptd": int(_num(r["pass_tds"])), "rtd": int(_num(r["rush_tds"])), "ryds": int(_num(r["rush_yards"])),
            "recy": int(_num(r["rec_yards"])), "rectd": int(_num(r["rec_tds"])), "sack2": int(round(2 * _num(r["def_sacks"]))),
            "dint": int(_num(r["def_ints"])), "src": "draft_picks",
            "pyds": int(_num(r["pass_yards"])), "rec": int(_num(r["receptions"])), "started": int(_num(r["seasons_started"])), "tkl": 0,
            **{k: 0 for k in ("fgm", "mvp", "opoy", "dpoy", "oroy", "droy", "sbmvp", "rt", "sb")}})
    by_norm = collections.defaultdict(list)
    for p in people:
        by_norm[p["norm"]].append(p)
    by_gsis = {p["gsis"]: p for p in people if p["gsis"]}

    # ---- awards by name and season; the same name in one season goes to the drafted player with the most career value
    unresolved = []

    def give(table, key, side=None):
        for season, names in sorted(table.items()):
            for name in names:
                cands = [p for p in by_norm.get(norm_name(name), []) if p["draft"] - 1 <= season <= p["last"]]
                if side:
                    cands = [p for p in cands if (p["group"] in ("QB", "RB", "WR", "TE", "OL")) == (side == "O")] or cands
                if not cands:
                    unresolved.append([key, season, name, "no drafted player"])
                    continue
                if len(cands) > 1:
                    cands.sort(key=lambda p: (-p["wav"], p["draft"]))
                    unresolved.append([key, season, name, f"ambiguous, gave to {cands[0]['name']} (drafted {cands[0]['draft']})"])
                cands[0][key] += 1

    award_tables = {"mvp": parse_mvp(text("mvp")), "opoy": parse_award_seasons(text("opoy")), "dpoy": parse_dpoy(text("dpoy")),
                    "sbmvp": parse_sb_mvp(text("sbmvp")), "rt": parse_rushing(text("rushing"))}
    oroy, droy = parse_roy(text("roy"))
    award_tables["oroy"], award_tables["droy"] = oroy, droy
    for key, table in award_tables.items():
        give(table, key, side="O" if key == "oroy" else "D" if key == "droy" else None)
    unresolved = [u for u in unresolved if u[1] >= FIRST_STATS - 9]       # older seasons belong to retired-before-1999 players

    # ---- Super Bowl rings and lost Super Bowls: each finalist's Super Bowl-week roster (2002 on; the season snapshot for 2000 and 2001)
    champions, runners_up = parse_champions(text("sbchamps")), parse_runners_up(text("sbchamps"))
    rings, losses = collections.Counter(), collections.Counter()
    notes = []
    for season in range(2000, 2026):
        rows = _read_csv(cache / f"roster_{season}.csv")
        if rows and "game_type" in rows[0]:
            rows = [r for r in rows if r["game_type"] == "SB"]
        else:
            notes.append(f"{season}: no Super Bowl-week rows in the roster file; the season snapshot of both finalists is used")
        teams = {r["team"] for r in rows}
        for club, tally in ((champions.get(season), rings), (runners_up.get(season), losses)):
            if not club:
                continue
            codes = CLUB_CODES.get(club.split()[-1], ())
            use = [c for c in codes if c in teams]
            _require(bool(use), f"{season}: {club} has no roster team among {sorted(teams)}")
            for gsis in {r["gsis_id"] for r in rows if r["team"] == use[0] and r["status"] in ("ACT", "INA") and r["gsis_id"]}:
                tally[gsis] += 1
    # ---- playoff wins of the starting quarterback (the nflverse games file, 1999-2025)
    qb_wins = collections.Counter()
    winning_qbs = {}                                                  # season -> the Super Bowl winner's starting quarterback
    for r in _read_csv(cache / "games.csv"):
        if r["game_type"] in POSTSEASON and int(r["season"]) <= LAST_STATS and r["home_score"] != "" and r["away_score"] != "":
            home, away = int(r["home_score"]), int(r["away_score"])
            qb = r["home_qb_id"] if home > away else r["away_qb_id"] if away > home else ""
            if qb:
                qb_wins[qb] += 1
                if r["game_type"] == "SB":
                    winning_qbs[int(r["season"])] = qb
    for p in people:
        p["sb"] = rings.get(p["gsis"], 0)
        p["sbl"] = losses.get(p["gsis"], 0)
        p["pw"] = qb_wins.get(p["gsis"], 0) if p["group"] == "QB" else 0

    # ---- Hall of Fame membership and class year (the Wikipedia list; the PFR flag is the second source)
    hall = parse_hof_list(text("hof_list"))
    members = []
    for entry in hall:
        if not entry["last_season"]:
            continue
        cands = [p for p in by_norm.get(norm_name(entry["first"] + " " + entry["last"]), [])
                 if abs(p["last"] - entry["last_season"]) <= 1 or (p["hof"] and abs(p["last"] - entry["last_season"]) <= 2)]
        members.append((entry, cands))
    for entry, cands in members:
        if cands:
            cands.sort(key=lambda p: not p["hof"])
            cands[0]["hof"], cands[0]["class"] = True, entry["class"]

    # ---- seasons of every player in the stats files (1999-2025)
    seasons = collections.defaultdict(dict)
    for year in range(FIRST_STATS, LAST_STATS + 1):
        for r in _read_csv(cache / f"stats_player_reg_{year}.csv"):
            if r["season_type"] == "REG":
                seasons[r["player_id"]][year] = r
    roster_rows = {}
    for year in range(2000, 2027):
        for r in _read_csv(cache / f"roster_{year}.csv"):
            if r["gsis_id"]:
                roster_rows[r["gsis_id"]] = r                      # the latest year wins (files are read in order)
    active = {r["gsis_id"] for r in _read_csv(cache / "roster_2026.csv") if r["gsis_id"] and r["status"] in ACTIVE_STATUS}

    # ---- honors from the pinned pages for players who were never drafted (All-Pro by table, Pro Bowl by name presence)
    ap_names = {s: {norm_name(n) for n in parse_allpro_first_team(text(f"allpro_{s}"))} for s in range(FIRST_STATS, LAST_STATS + 1)}
    pb_blobs = {s: pro_bowl_blob(text(f"probowl_{s}")) for s in range(FIRST_STATS, LAST_STATS + 1)}
    award_by_name = collections.defaultdict(list)
    for key, table in award_tables.items():
        for season, names in table.items():
            for name in names:
                award_by_name[(norm_name(name), season)].append(key)
    drafted_seasons = {(p["norm"], y) for p in people for y in range(max(FIRST_STATS, p["draft"]), p["last"] + 1)}

    careers = []
    for gsis, per_year in seasons.items():
        if gsis in by_gsis:
            continue
        years = sorted(per_year)
        name = per_year[years[-1]]["player_display_name"]
        n = norm_name(name)
        if any(abs(p["last"] - years[-1]) <= 1 and p["draft"] - 1 <= years[0] for p in by_norm.get(n, [])):
            continue                                                # the same man under another id
        pos = collections.Counter(per_year[y]["position"] for y in years).most_common(1)[0][0]

        def total(col, y=years):
            return sum(int(_num(per_year[k][col])) for k in y)

        c = {"name": name, "norm": n, "pos": pos, "group": STATS_GROUP.get(pos, "?"), "draft": None, "first": years[0], "last": years[-1],
             "gsis": gsis, "hof": False, "games": total("games"), "ptd": total("passing_tds"), "rtd": total("rushing_tds"),
             "ryds": total("rushing_yards"), "recy": total("receiving_yards"), "rectd": total("receiving_tds"),
             "sack2": int(round(2 * sum(_num(per_year[k]["def_sacks"]) for k in years))), "dint": total("def_interceptions"),
             "fgm": total("fg_made"), "src": "stats_player", "wav": 0.0, "pyds": total("passing_yards"), "rec": total("receptions"),
             "started": 0, "tkl": 0,
             **{k: 0 for k in ("mvp", "opoy", "dpoy", "oroy", "droy", "sbmvp", "rt")}, "sb": rings.get(gsis, 0), "ap": 0, "pb": 0,
             "sbl": losses.get(gsis, 0), "pw": qb_wins.get(gsis, 0) if STATS_GROUP.get(pos) == "QB" else 0}
        for y in years:
            if int(_num(per_year[y]["games"])) and (n, y) not in drafted_seasons:
                c["ap"] += n in ap_names[y]
                c["pb"] += bool(n) and n in pb_blobs[y]
                for key in award_by_name.get((n, y), ()):
                    c[key] += 1
        careers.append(c)
    by_norm_stats = collections.defaultdict(list)
    for c in careers:
        by_norm_stats[c["norm"]].append(c)
    for entry, cands in members:
        if cands or not entry["last_season"]:
            continue
        match = [c for c in by_norm_stats.get(norm_name(entry["first"] + " " + entry["last"]), [])
                 if abs(c["last"] - entry["last_season"]) <= 1]
        if len(match) == 1:
            match[0]["hof"], match[0]["class"] = True, entry["class"]
    for p in people:
        per_year = seasons.get(p["gsis"], {})
        p["fgm"] = sum(int(_num(per_year[y]["fg_made"])) for y in per_year)
    everyone = people + careers
    for c in everyone:                                               # tackles as the game's career card counts them (fh1 mapping)
        per_year = seasons.get(c["gsis"], {})
        c["tkl"] = sum(int(_num(r["def_tackles_solo"]) + _num(r["def_tackles_with_assist"]) + _num(r["def_tackle_assists"]))
                       for r in per_year.values())

    # ---- club, birth date and the active flag for the recent seasons
    def last_club(c):
        per_year = seasons.get(c["gsis"], {})
        team = per_year[max(per_year)]["recent_team"] if per_year else ""
        return TEAM_NICKNAME.get(team, "")

    out_rows, excluded = [], collections.Counter()
    excluded_max = 0
    for c in sorted(everyone, key=lambda c: (c["last"], c["name"], c["gsis"])):
        if not FIRST_STATS <= c["last"] <= LAST_STATS:
            continue
        if c["gsis"] in active and c["last"] >= 2025:
            continue                                                 # still playing: not a retiree
        group = c["group"]
        if group not in rules.GROUPS:
            continue
        career = rows_career({"group": group, **{k: c[k] for k in COLUMNS if k in c}})
        s = rules.score(career)
        notable = is_notable(c)
        if not (notable or c["hof"] or s >= KEEP_SCORE):
            if 2005 <= c["last"] <= 2019:
                excluded[c["last"]] += 1
                excluded_max = max(excluded_max, s)
            continue
        recent = c["last"] >= 2016
        club = last_club(c) if recent else ""
        r = roster_rows.get(c["gsis"]) if recent else None
        out_rows.append([c["name"], GAME_POSITION.get(c["pos"], c["pos"]), group, c["first"], c["last"], c.get("class", 0) if c["hof"] else 0,
                         c["src"], c["games"], c["ptd"], c["rtd"], c["ryds"], c["recy"], c["rectd"], c["sack2"], c["dint"], c["fgm"],
                         c["ap"], c["pb"], c["mvp"], c["opoy"], c["dpoy"], c["oroy"], c["droy"], c["sbmvp"], c["rt"], c["sb"],
                         1 if c["gsis"] in active else 0, club, (r or {}).get("birth_date", "") if recent else "",
                         c["gsis"] if recent else "", c["pyds"] if recent else 0, c["rec"],
                         c["tkl"] if recent else 0, c["started"] if recent else 0, c["sbl"], c["pw"]])
    # ---- two-source checks, recorded in the dataset so they can be re-read and re-run
    honors_doc = json.loads((ROOT / "data" / "nfl2k5_honors_2026.json").read_text(encoding="utf-8"))
    agree = {"all_pro": [0, 0], "pro_bowl": [0, 0]}
    disagree = []
    for pl in honors_doc["players"]:
        n = norm_name(pl["first"] + " " + pl["last"])
        for h in pl["honors"]:
            if h["honor"] == "all_pro" and FIRST_STATS <= h["season"] <= LAST_STATS:
                ok = n in ap_names[h["season"]]
            elif h["honor"] == "pro_bowl" and FIRST_STATS <= h["season"] <= LAST_STATS:
                ok = bool(n) and n in pb_blobs[h["season"]]
            else:
                continue
            agree[h["honor"]][1] += 1
            agree[h["honor"]][0] += ok
            if not ok:
                disagree.append([pl["first"] + " " + pl["last"], h["season"], h["honor"]])
    pfr_only = sorted(p["name"] for p in people if p["pfr_hof"] and "class" not in p and p["last"] >= FIRST_STATS)
    wiki_only = sorted(p["name"] for p in people if "class" in p and not p["pfr_hof"])
    # the rings come from the Super Bowl-week rosters and the champions page; two independent pages must agree with them: every Super Bowl MVP
    # (his own page) wears a ring, and so does the quarterback the games file says won each Super Bowl
    mvp_rings, mvp_missed = [0, 0], []
    for season, names in sorted(award_tables["sbmvp"].items()):
        for name in names if season >= 2000 else ():
            mvp_rings[1] += 1
            found = [p for p in by_norm.get(norm_name(name), []) if p["draft"] - 1 <= season <= p["last"]]
            if any(rings.get(p["gsis"], 0) for p in found):
                mvp_rings[0] += 1
            else:
                mvp_missed.append([season, name])
    qb_rings, qb_missed = [0, 0], []
    for season in range(2000, 2026):
        qb_rings[1] += 1
        if rings.get(winning_qbs.get(season, ""), 0):
            qb_rings[0] += 1
        else:
            qb_missed.append([season, winning_qbs.get(season, "")])
    checks = {"honors_pages_vs_the_game_honors_dataset": {"all_pro_matched": agree["all_pro"], "pro_bowl_matched": agree["pro_bowl"],
                                                          "not_matched": sorted(disagree)},
              "super_bowl_mvps_vs_champion_rosters": {"matched": mvp_rings, "not_matched": mvp_missed},
              "super_bowl_winning_quarterbacks_vs_champion_rosters": {"matched": qb_rings, "not_matched": qb_missed},
              "pfr_hall_of_fame_flag_vs_wikipedia_list": {"flagged_by_pfr_not_on_the_list": pfr_only, "on_the_list_not_flagged_by_pfr": wiki_only,
                                                          "drafted_members_on_both": sum(1 for p in people if p["pfr_hof"] and "class" in p)}}
    sources = {f"wiki:{k}": dict(v, url=wiki_url(v)) for k, v in sorted(PINS_WIKI.items())}
    sources.update({f"nflverse:{k}": dict(v) for k, v in sorted(PINS_NFLVERSE.items())})
    return {"schema": DATASET_SCHEMA, "attribution": ATTRIBUTION, "columns": list(COLUMNS), "rows": out_rows,
            "definitions": DEFINITIONS, "sources": sources,
            "counts": {"rows": len(out_rows), "retired_2005_2019_excluded_by_year": dict(sorted(excluded.items())),
                       "retired_2005_2019_excluded": sum(excluded.values()), "excluded_max_score": excluded_max,
                       "undrafted_careers_built": len(careers), "keep_score": KEEP_SCORE},
            "checks": checks, "notes": notes, "unresolved_awards": sorted(unresolved)}


KEEP_SCORE = 40
DEFINITIONS = {
    "row": "one retired player (last season 1999..2025; players on a 2026 roster who played in 2025 are not retired)",
    "ap": "AP first-team All-Pro seasons (PFR AP1 count for drafted players; the pinned All-Pro pages for the others)",
    "pb": "Pro Bowl selections (PFR for drafted players; name presence on the pinned Pro Bowl pages for the others); NOT used by the rule",
    "mvp opoy dpoy oroy droy sbmvp rt": "AP awards, Super Bowl MVP and rushing titles from the pinned Wikipedia pages, matched by name and season",
    "sb": "Super Bowl rings, 2000 onward only: the champion's Super Bowl-week roster (ACT or INA), a season snapshot for 2000-2001",
    "sbl": "Super Bowls reached and lost, 2000 onward: the runner-up's Super Bowl-week roster (a season snapshot for 2000-2001)",
    "pw": "quarterbacks only: postseason wins as the starting quarterback of the game, 1999-2025 (nflverse games file)",
    "rec": "career receptions (PFR through draft_picks for drafted players, nflverse stats_player for the others)",
    "games ptd rtd ryds recy rectd sack2 dint": "career totals (PFR through nflverse draft_picks for drafted players, nflverse stats_player 1999-2025 "
                                                "for the others); sack2 is half-sacks, dint is defensive interceptions",
    "fgm": "field goals made, nflverse stats_player 1999-2025 only (kickers who started before 1999 are short)",
    "hof": "the Pro Football Hall of Fame class year (Wikipedia list, through the Class of 2026), 0 when not a member",
    "group": "QB RB WR TE OL DL LB DB K P",
    "active": "1 when the player has a 2026 roster row with status ACT, RES, DEV or EXE (RET and CUT rows are not active)",
    "club birth gsis": "only for last season 2016 and later (the seed candidates need them)",
}


def is_notable(c: Mapping) -> bool:
    return c["ap"] >= 1 or c["pb"] >= 3 or c["mvp"] + c["opoy"] + c["dpoy"] + c["sbmvp"] >= 1 or bool(c["hof"])


def rows_career(row: Mapping) -> "rules.Career":
    """A dataset row (dict by column name) as the rule's Career."""

    return rules.Career(
        group=rules.GROUPS.index(row["group"]), games=row["games"], mvp=row["mvp"], opoy=row["opoy"], dpoy=row["dpoy"], oroy=row["oroy"],
        droy=row["droy"], super_bowl=row["sb"], super_bowl_mvp=row["sbmvp"], pro_bowl=row["pb"], all_pro=row["ap"],
        rushing_title=row["rt"], passing_touchdowns=row["ptd"], rushing_touchdowns=row["rtd"], rushing_yards=row["ryds"],
        receiving_yards=row["recy"], receiving_touchdowns=row["rectd"], sacks_half=row["sack2"], interceptions=row["dint"],
        field_goals_made=row["fgm"], receptions=row["rec"], super_bowl_loss=row["sbl"], playoff_wins=row["pw"])


def load_rows(path: Path | str | None = None) -> list[dict]:
    data = json.loads(Path(path or DATASET).read_text(encoding="utf-8"))
    cols = data["columns"]
    return [dict(zip(cols, r)) for r in data["rows"]]


# --------------------------------------------------------------------------------------------------------------------
# evaluation
IN_RANGE = (2005, 2019)             # the calibration range: retired 2005..2019
EXTENDED_RANGE = (2005, 2020)       # plus the retirees of 2020 (Fitzgerald, Brees): the Class of 2026 has seen them once
TRAIN_THROUGH = 2012                # retired 2005..2012 fit, 2013..2019 test
TARGET_RECALL, TARGET_FPR = 0.80, 0.10
# The coordinator's follow-up asks: these careers must reach the bar (with every input the sources give), this one must not.
REQUIRED_PASS = ("Ben Roethlisberger", "Larry Fitzgerald")
REQUIRED_FAIL = ("Eli Manning",)
NAMED_CASES = ("Ben Roethlisberger", "Larry Fitzgerald", "Eli Manning", "Philip Rivers", "Russell Wilson", "Matt Ryan", "Drew Brees",
               "Peyton Manning", "Tom Brady", "Isaac Bruce", "Jason Witten", "Steve Smith Sr.", "Reggie Wayne", "Anquan Boldin",
               "Tony Gonzalez", "Terrell Owens", "Randy Moss")


def live_only(career: "rules.Career") -> "rules.Career":
    """The same career without the two optional counters (Super Bowls lost, quarterback playoff wins): what a franchise player reads
    until the honors owner writes them."""

    import dataclasses
    return dataclasses.replace(career, super_bowl_loss=0, playoff_wins=0)


def named_cases(rows: Sequence[Mapping], names: Sequence[str] = NAMED_CASES) -> list[dict]:
    out = []
    for name in names:
        row = next((r for r in rows if r["name"] == name), None)
        if row is None:
            continue
        career = rows_career(row)
        out.append({"name": name, "group": row["group"], "last": row["last"], "hof": row["hof"], "score": rules.score(career),
                    "parts": rules.score_parts(career), "live_only": rules.score(live_only(career))})
    return out


def evaluate(rows: Sequence[Mapping], bar: int = rules.BAR, years: Sequence[int] = IN_RANGE) -> dict:
    scored = [(r, rules.score(rows_career(r))) for r in rows if years[0] <= r["last"] <= years[1]]
    hof = [(r, s) for r, s in scored if r["hof"]]
    peers = [(r, s) for r, s in scored if not r["hof"] and is_notable(r)]
    rest = [(r, s) for r, s in scored if not r["hof"] and not is_notable(r)]

    def frac(group, pred=lambda rs: rs[1] >= bar):
        return (sum(1 for rs in group if pred(rs)), len(group))

    out = {"bar": bar, "range": list(years), "inductees": len(hof), "notable_non_inductees": len(peers),
           "other_retirees_in_dataset": len(rest), "other_retirees_that_pass": frac(rest)[0]}
    out["recall"] = frac(hof)
    out["recall_train"] = frac([rs for rs in hof if rs[0]["last"] <= TRAIN_THROUGH])
    out["recall_test"] = frac([rs for rs in hof if rs[0]["last"] > TRAIN_THROUGH])
    out["false_positives"] = frac(peers)
    out["false_positives_train"] = frac([rs for rs in peers if rs[0]["last"] <= TRAIN_THROUGH])
    out["false_positives_test"] = frac([rs for rs in peers if rs[0]["last"] > TRAIN_THROUGH])
    out["by_group"] = {g: frac([rs for rs in hof if rs[0]["group"] == g]) for g in rules.GROUPS if any(rs[0]["group"] == g for rs in hof)}
    out["misses"] = [(r["name"], r["group"], r["last"], r["hof"], s) for r, s in sorted(hof, key=lambda rs: -rs[1]) if s < bar]
    out["false_positive_names"] = [(r["name"], r["group"], r["last"], s) for r, s in sorted(peers, key=lambda rs: -rs[1]) if s >= bar]
    return out


# --------------------------------------------------------------------------------------------------------------------
# table entries and the yearly replay
REPRESENTATIVE = {"QB": "QB", "RB": "HB", "WR": "WR", "TE": "TE", "OL": "T", "DL": "DE", "LB": "OLB", "DB": "CB", "K": "K", "P": "P"}
FIRST_FRANCHISE_SEASON = 2026
SEED_FIRST_RETIRED = 2021          # the real committee has judged everyone eligible through the Class of 2026 (retired 2020 or earlier)


def row_key_numbers(row: Mapping) -> tuple[int, int, int]:
    """The three display numbers of the footer's candidate entry (``nfl2k5_franchise_extension.HALL_KEYS``)."""

    g = row["group"]
    if g == "QB":
        return (row["ptd"] & 0xFFFF, (row["pyds"] // 1000) & 0xFFFF, 0)                  # wins are not in the sources
    if g == "RB":
        return (max(0, row["ryds"]) & 0xFFFF, row["rtd"] & 0xFFFF, row["rec"] & 0xFFFF)
    if g in ("WR", "TE"):
        return (row["rec"] & 0xFFFF, max(0, row["recy"]) & 0xFFFF, row["rectd"] & 0xFFFF)
    if g in ("DL", "LB", "DB"):
        return (row["tkl"] & 0xFFFF, row["sack2"] & 0xFFFF, row["dint"] & 0xFFFF)
    return (row["started"] & 0xFFFF, row["pb"] & 0xFFFF, row["ap"] & 0xFFFF)


def make_candidate(row: Mapping, *, real: bool = True) -> "rules.Candidate":
    """A dataset row as a table entry: what the retirement pass would store for him."""

    career = rows_career(row)
    pos = row["pos"] if row["pos"] in champions.POSITIONS else REPRESENTATIVE[row["group"]]
    club = champions.CLUBS.index(row["club"]) if row.get("club") in champions.CLUBS else None
    seasons = max(1, min(255, row["last"] - row["first"] + 1)) if row["first"] else rules.seasons_from_games(row["games"])
    return rules.Candidate(champions.pack_person(row["name"], pos), club, row["last"], rules.score(career), seasons,
                           rules.FLAG_VALID | (rules.FLAG_REAL if real else 0), row_key_numbers(row), rules.honors_count(career),
                           min(255, row["sb"]))


def replay(rows: Sequence[Mapping], first_close: int, last_close: int, *, retirees_from: int = 1999, seed_table: Sequence = (),
           include_members: bool = True) -> dict:
    """Run ``rules.close_season`` for each season from ``first_close`` to ``last_close`` on real retirees.

    Retirees of a season join the table at that season's close, after the class is chosen. ``include_members`` False leaves
    out the real Hall of Famers (the franchise timeline). -> {"classes": {class year: [row]}, "closes": [...], "table": [...]}."""

    by_season: dict[int, list] = collections.defaultdict(list)
    owner: dict[int, Mapping] = {}
    for row in sorted(rows, key=lambda r: (r["last"], r["name"], r["gsis"])):
        if row["last"] < retirees_from or (row["hof"] and not include_members):
            continue
        cand = make_candidate(row)
        owner[id(cand)] = row
        by_season[row["last"]].append(cand)
    table = rules.empty_table()
    for cand in seed_table:
        rules.admit(table, cand)
    classes, closes, occupancy, evictions = {}, [], {}, []
    for season in range(first_close, last_close + 1):
        # a season's own retirees can only join after the class; those older than the first close join before it
        pre = by_season.pop(first_close - 1, []) if season == first_close else []
        if season == first_close:
            for old in sorted(k for k in list(by_season) if k < first_close - 1):
                pre += by_season.pop(old)
            for cand in sorted(pre, key=lambda c: (-c.score, c.retired)):
                rules.admit(table, cand)
        result = rules.close_season(table, season, by_season.get(season, ()))
        classes[result.class_year] = [dict(owner.get(id(c)) or {"name": rules.person_line(c.person, c.club), "group": "?", "last": c.retired,
                                                                 "hof": 0}, _score=c.score) for c in result.sources]
        closes.append(result)
        occupancy[season] = sum(1 for c in table if c is not None)
        evictions += [(season, c) for c in result.evicted]
    return {"classes": classes, "closes": closes, "table": [c for c in table if c is not None], "owner": owner,
            "occupancy": occupancy, "evictions": evictions}


def class_lines(classes: Mapping[int, Sequence[Mapping]], years: Sequence[int]) -> list[str]:
    out = []
    for y in years:
        members = classes.get(y, [])
        names = "; ".join(f"{r['name']} ({r['group']}, retired {r['last']}, {r['_score']}{', real ' + str(r['hof']) if r.get('hof') else ''})"
                          for r in members)
        out.append(f"{y} [{len(members)}] {names}")
    return out


REAL_FIRST_CLOSE = 2004            # retirees from 1999 on are in the sources; the first of them is eligible at the 2004 close


def real_replay(rows: Sequence[Mapping], first: int = 2010, last: int = 2026) -> dict:
    """The rule on real retirees, one close per season from 2004: who it would have inducted each year (classes ``first``..``last``).

    Every close runs from 2004 so the table is filled year by year, as in a game, whatever class the caller asks to see."""

    result = replay(rows, REAL_FIRST_CLOSE, last - 1, retirees_from=1999)
    classes = {y: v for y, v in result["classes"].items() if first <= y <= last}
    sizes = collections.Counter(len(v) for v in classes.values())
    inducted = [r for v in classes.values() for r in v]
    occupancy = {s: n for s, n in result["occupancy"].items() if s >= first - 1}
    evicted = [(s, owner_name(result["owner"], c), c.score) for s, c in result["evictions"]]
    return {"classes": classes, "sizes": dict(sorted(sizes.items())), "inductees": len(inducted),
            "real_members": sum(1 for r in inducted if r.get("hof")), "result": result,
            "table_max": max(occupancy.values()) if occupancy else 0, "evictions": evicted}


def owner_name(owner: Mapping, cand: "rules.Candidate") -> str:
    row = owner.get(id(cand))
    return row["name"] if row else rules.person_line(cand.person, cand.club)


# --------------------------------------------------------------------------------------------------------------------
# the game roster: a seeded retiree must not also be a player there
LAST_CONFIRMED_SEASON = 2024        # a retiree whose last season is later is inferred: the 2026 roster files simply do not list him


def read_game_roster(image: Path | str) -> dict:
    """The identities on a built disc's roster, read-only: {"players": [(first, last, birth date or "")], "sha256", "bytes"}.

    Uses the Studio's own roster reader, so this one command needs the whole repository. Nothing is written to the image."""

    from mod_editor.core import nfl2k5_roster_records as records
    from mod_editor.core import nfl2k5_save_rost as save_rost
    _require(Path(image).is_file(), f"no disc image at {image}")
    try:
        with records._outer_image()(str(image)) as archive:
            entry = records._entry(archive)
            resource = archive.read(entry.virtual_offset, entry.size)
        body = resource[records.RESOURCE_HEADER_SIZE:]
        document = save_rost.decode(body, preamble=0, reference_year=FIRST_FRANCHISE_SEASON)
    except (OSError, ValueError) as exc:
        raise CalibrationError(f"the roster could not be read from {Path(image).name}: {exc}") from exc
    players = [(p.first, p.last, p.record.birth_date.isoformat() if p.record.birth_date else "") for p in document.players]
    return {"players": players, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def match_roster(rows: Sequence[Mapping], players: Sequence[tuple[str, str, str]]) -> dict:
    """The retirees a seed could come from (last season 2021 or later, not elected) against the roster, by name and birth date.

    -> {"on_roster": the same name and the same birth date,
        "name_only": the same name and a birth date missing on either side (not told apart: treated as the same man),
        "other_birth_date": the same name and different birth dates (a different man, kept)}."""

    dates: dict[str, list[str]] = collections.defaultdict(list)
    for first, last, born in players:
        dates[norm_name(f"{first} {last}")].append(born)
    out: dict[str, list] = {"on_roster": [], "name_only": [], "other_birth_date": []}
    for row in sorted(rows, key=lambda r: (r["last"], r["name"], r["gsis"])):
        if row["last"] < SEED_FIRST_RETIRED or row["hof"]:
            continue
        roster_dates = dates.get(norm_name(row["name"]))
        if not roster_dates:
            continue
        entry = {"name": row["name"], "position": row["pos"], "retired": row["last"], "birth_date": row["birth"] or None,
                 "gsis_id": row["gsis"] or None}
        if row["birth"] and row["birth"] in roster_dates:
            out["on_roster"].append(entry)
        elif row["birth"] and all(roster_dates):
            out["other_birth_date"].append(dict(entry, roster_birth_dates=sorted(set(roster_dates))))
        else:
            out["name_only"].append(entry)
    return out


def roster_check_document(rows: Sequence[Mapping], roster: Mapping, image_name: str) -> dict:
    found = match_roster(rows, roster["players"])
    return {"schema": ROSTER_CHECK_SCHEMA, "attribution": ATTRIBUTION,
            "rule": ("A retiree is on the game roster when his name (case, accents, punctuation and Jr, Sr, II, III ignored) and his birth "
                     "date both match a roster player. A name match where either side has no birth date cannot be told apart and counts "
                     "as the same man (name_only). A name match with two different birth dates is a different man and stays "
                     "(other_birth_date). Checked: every dataset row whose last season is 2021 or later and who is not a real Hall of Famer."),
            "roster": {"image": image_name, "resource_sha256": roster["sha256"], "resource_bytes": roster["bytes"],
                       "players": len(roster["players"]), "players_with_birth_date": sum(1 for _f, _l, born in roster["players"] if born),
                       "reference_year": FIRST_FRANCHISE_SEASON},
            "retirees_checked": sum(1 for r in rows if r["last"] >= SEED_FIRST_RETIRED and not r["hof"]),
            "counts": {k: len(v) for k, v in found.items()}, **found}


def load_roster_check(path: Path | str | None = None) -> dict:
    data = json.loads(Path(path or ROSTER_CHECK).read_text(encoding="utf-8"))
    _require(data.get("schema") == ROSTER_CHECK_SCHEMA, "not a roster check file")
    return data


def roster_keys(roster_check: Mapping | None) -> set[tuple[str, str]]:
    """(normalized name, birth date) of every retiree the check puts on the roster; empty without a check."""

    if not roster_check:
        return set()
    return {(norm_name(e["name"]), e["birth_date"] or "") for e in list(roster_check["on_roster"]) + list(roster_check["name_only"])}


def on_roster(row: Mapping, keys: set) -> bool:
    return (norm_name(row["name"]), row["birth"] or "") in keys


def franchise_replay(rows: Sequence[Mapping], last_close: int = 2035, roster_check: Mapping | None = None) -> dict:
    """The first franchise classes: seeds = real retirees from 2021 on that the real committee has not judged and that are not on the
    game roster; no later retirements."""

    keys = roster_keys(roster_check)
    seeds = [r for r in rows if r["last"] >= SEED_FIRST_RETIRED and not r["hof"] and not r["active"] and not on_roster(r, keys)]
    result = replay(seeds, FIRST_FRANCHISE_SEASON, last_close, retirees_from=SEED_FIRST_RETIRED, include_members=True)
    return {"classes": result["classes"], "sizes": dict(sorted(collections.Counter(len(v) for v in result["classes"].values()).items())),
            "left": result["table"], "result": result, "seeds": len(seeds)}


def retirement_text(last: int) -> tuple[bool, str]:
    if last <= LAST_CONFIRMED_SEASON:
        return True, f"confirmed: no season after {last} in the sources"
    return False, (f"INFERRED, not confirmed: last played {last} and has no {FIRST_FRANCHISE_SEASON} roster row in the sources; "
                   "check him before relying on it")


def seed_document(rows: Sequence[Mapping], roster_check: Mapping | None = None) -> dict:
    """The seeded pending candidates (real retirees the real committee has not judged), best first, without anyone on the game roster."""

    keys = roster_keys(roster_check)
    out, removed = [], []
    for row in sorted(rows, key=lambda r: (-rules.score(rows_career(r)), r["name"])):
        if row["last"] < SEED_FIRST_RETIRED or row["hof"] or row["active"]:
            continue
        career = rows_career(row)
        s = rules.score(career)
        if s < rules.FLOOR:
            continue
        confirmed, text = retirement_text(row["last"])
        if on_roster(row, keys):
            removed.append({"name": row["name"], "position": row["pos"], "retired": row["last"], "score": s,
                            "birth_date": row["birth"] or None, "retirement_confirmed": confirmed, "retirement": text,
                            "why_removed": "he is on the game roster (same name and birth date): he plays there, so he is not also a pending candidate"})
            continue
        cand = make_candidate(row)
        out.append({"name": row["name"], "position": row["pos"], "group": row["group"], "club": row["club"] or None, "club_index": cand.club,
                    "first_season": row["first"], "retired": row["last"], "eligible_class": row["last"] + rules.WAIT_SEASONS + 1,
                    "score": s, "parts": rules.score_parts(career), "seasons": cand.seasons, "honors": cand.honors, "super_bowls": cand.sb_wins,
                    "super_bowls_lost": row["sbl"], "playoff_wins": row["pw"], "keys": list(cand.keys), "all_pro": row["ap"],
                    "pro_bowl": row["pb"], "mvp": row["mvp"], "opoy": row["opoy"], "dpoy": row["dpoy"], "gsis_id": row["gsis"],
                    "birth_date": row["birth"], "retirement_confirmed": confirmed, "retirement": text,
                    "candidate_hex": rules.candidate_to_bytes(cand).hex()})
    inferred = [c["name"] for c in out if not c["retirement_confirmed"]]
    warnings = []
    if inferred:
        warnings.append(f"{len(inferred)} seeded retiree(s) have an INFERRED retirement (last played {LAST_CONFIRMED_SEASON + 1}, no "
                        f"{FIRST_FRANCHISE_SEASON} roster row in the sources): {', '.join(inferred)}. Check each before relying on it.")
    if roster_check is None:
        warnings.append("No roster check was applied: a seed may also be a player on the game roster.")
    return {"schema": PERSON_SCHEMA, "attribution": ATTRIBUTION,
            "rule": {"bar": rules.BAR, "floor": rules.FLOOR, "wait": rules.WAIT_SEASONS, "window": rules.WINDOW_SEASONS,
                     "max_class": rules.MAX_CLASS, "min_class": rules.MIN_CLASS},
            "policy": ("Real retirees whose last season is 2021 or later: the real committee has not judged them (its Class of 2026 "
                       "is the last one in the sources). Retirees up to 2020 who were not elected stay out: the real committee passed "
                       "on them, and the rule would only reproduce its false positives. A seeded player must not also exist on the "
                       "game roster: anyone whose name and birth date match a roster player (data/nfl2k5_hof_roster_check_2026.json, read "
                       "from the v0.8 disc) is left out and listed under removed_by_roster_check, and so is anyone the sources show on a "
                       "2026 roster (ACT, RES, DEV or EXE). A retirement whose last season is 2025 is INFERRED, not confirmed: it is marked "
                       "retirement_confirmed false and named in inferred_retirements."),
            "roster_check": ({"image": roster_check["roster"]["image"], "resource_sha256": roster_check["roster"]["resource_sha256"],
                              "players": roster_check["roster"]["players"], "counts": roster_check["counts"]} if roster_check else None),
            "inferred_retirements": inferred, "warnings": warnings, "removed_by_roster_check": removed,
            "count": len(out), "candidates": out}


# --------------------------------------------------------------------------------------------------------------------
# search and sensitivity: the same formula with the constants as parameters
DEFAULT_PARAMS = {"ap": rules.POINTS["all_pro"], "mvp": rules.POINTS["mvp"], "poy": rules.POINTS["player_of_year"],
                  "sbm": rules.POINTS["super_bowl_mvp"], "roy": rules.POINTS["rookie_of_year"], "rt": rules.POINTS["rushing_title"],
                  "sb": rules.POINTS["super_bowl"], "gpp": rules.GAMES_PER_POINT, "gcap": rules.GAMES_CAP,
                  "gcap0": rules.GAMES_CAP_LINEMEN, "pcap": rules.PRODUCTION_CAP, "bar": rules.BAR,
                  # championships and milestones (the follow-up): quarterback ring and lost Super Bowl, the other positions' lost Super
                  # Bowl, quarterback playoff win (and its cap), the 400-touchdown tier, the receivers' 15,000 and 17,000 yard tiers and the
                  # 1,300 catch tier
                  "ring_qb": rules.QB_RING_POINTS, "loss_qb": rules.QB_LOSS_POINTS, "loss": rules.LOSS_POINTS_DEFAULT,
                  "pw": rules.PLAYOFF_WIN_POINTS, "pwcap": rules.PLAYOFF_WIN_CAP, "td400": rules.QB_TOUCHDOWN_TIERS[0][1],
                  "y15": rules.RECEIVING_YARDS_TIERS[0][1], "y17": rules.RECEIVING_YARDS_TIERS[1][1], "r13": rules.RECEPTION_TIERS[0][1]}
GRID = {"ap": (20, 25, 30), "mvp": (15, 25, 35, 45), "poy": (10, 15, 20), "sbm": (10, 15, 20), "roy": (5, 10, 15), "rt": (10, 15, 20),
        "sb": (2, 3, 4), "gpp": (3, 4, 5, 6), "gcap": (15, 20, 25, 30), "gcap0": (25, 35, 45), "pcap": (20, 25, 30),
        "ring_qb": (3, 6, 9), "loss_qb": (0, 3, 5), "loss": (0, 1, 2), "pw": (0, 1, 2), "pwcap": (10, 15, 20),
        "td400": (25, 30, 35, 40, 45), "y15": (10, 15, 20), "y17": (10, 15, 20), "r13": (5, 10, 15)}
TD_AT = rules.QB_TOUCHDOWN_TIERS[0][0]
Y15_AT, Y17_AT = rules.RECEIVING_YARDS_TIERS[0][0], rules.RECEIVING_YARDS_TIERS[1][0]
R13_AT = rules.RECEPTION_TIERS[0][0]


def score_with(c: "rules.Career", p: Mapping) -> int:
    """``rules.score`` with the weights and caps taken from ``p`` (the unit tests pin it equal at the shipped values)."""

    n = rules._n
    honors = (p["ap"] * n(c.all_pro) + p["mvp"] * n(c.mvp) + p["poy"] * (n(c.opoy) + n(c.dpoy)) + p["sbm"] * n(c.super_bowl_mvp)
              + p["roy"] * min(n(c.oroy) + n(c.droy), rules.ROOKIE_OF_YEAR_CAP) + p["rt"] * min(n(c.rushing_title), rules.RUSHING_TITLE_CAP))
    games = min(p["gcap0"] if c.group in rules.BIG_GAMES_CAP else p["gcap"], n(c.games - rules.GAMES_FREE) // p["gpp"])
    prod = 0 if c.group in rules.NO_PRODUCTION else min(p["pcap"], p["pcap"] * rules.composite(c) // rules.PAR[rules.GROUPS[c.group]])
    qb = c.group == rules.G_QB
    champ = ((p["ring_qb"] if qb else p["sb"]) * min(n(c.super_bowl), rules.SUPER_BOWL_CAP)
             + (p["loss_qb"] if qb else p["loss"]) * min(n(c.super_bowl_loss), rules.SUPER_BOWL_CAP))
    miles = 0
    if qb:
        champ += min(p["pwcap"], p["pw"] * n(c.playoff_wins))
        miles = p["td400"] if c.passing_touchdowns >= TD_AT else 0
    elif c.group in (rules.G_WR, rules.G_TE):
        miles = (p["y15"] * (c.receiving_yards >= Y15_AT) + p["y17"] * (c.receiving_yards >= Y17_AT) + p["r13"] * (c.receptions >= R13_AT))
    return honors + games + prod + champ + miles


def _split_metrics(rows: Sequence[Mapping], careers: Sequence, p: Mapping) -> dict:
    inr = [(r, c) for r, c in zip(rows, careers) if IN_RANGE[0] <= r["last"] <= IN_RANGE[1]]
    hof = [(r, c) for r, c in inr if r["hof"]]
    peers = [(r, c) for r, c in inr if not r["hof"] and is_notable(r)]
    ok = lambda rc: score_with(rc[1], p) >= p["bar"]            # noqa: E731

    def part(group, lo, hi):
        sel = [rc for rc in group if lo <= rc[0]["last"] <= hi]
        return sum(1 for rc in sel if ok(rc)), len(sel)
    return {"recall": part(hof, 0, 9999), "recall_train": part(hof, 0, TRAIN_THROUGH), "recall_test": part(hof, TRAIN_THROUGH + 1, 9999),
            "fp": part(peers, 0, 9999), "fp_train": part(peers, 0, TRAIN_THROUGH), "fp_test": part(peers, TRAIN_THROUGH + 1, 9999)}


def feasible(m: Mapping, *, fpr: float = 0.055) -> bool:
    ratio = lambda t: t[0] / t[1] if t[1] else 0.0                    # noqa: E731
    return (ratio(m["recall_train"]) >= TARGET_RECALL and ratio(m["recall_test"]) >= TARGET_RECALL and ratio(m["fp"]) <= fpr
            and ratio(m["fp_train"]) <= fpr + 0.005 and ratio(m["fp_test"]) <= fpr + 0.01 and m.get("cases_ok", True))


def search(rows: Sequence[Mapping], samples: int = 20000, seed: int = 20261102) -> dict:
    """Reproducible random search over ``GRID`` (bar fixed at 100): how many parameter sets meet the limits AND the follow-up's named
    cases (``REQUIRED_PASS`` reach the bar, ``REQUIRED_FAIL`` stay under it) and where the shipped set ranks by (recall, then fewer
    false positives). Needs numpy."""

    import numpy as np

    inr = [r for r in rows if IN_RANGE[0] <= r["last"] <= IN_RANGE[1] and (r["hof"] or is_notable(r))]
    named = {name: next(r for r in rows if r["name"] == name) for name in REQUIRED_PASS + REQUIRED_FAIL}
    pool = inr + [r for r in named.values() if not any(r is x for x in inr)]
    careers = [rows_career(r) for r in pool]
    n_in = len(inr)
    index = {name: next(i for i, r in enumerate(pool) if r is named[name]) for name in named}
    hof = np.array([bool(r["hof"]) for r in inr])
    last = np.array([r["last"] for r in inr])
    # per-row vectors, so one parameter set is a handful of array operations
    A = {k: np.array([getattr(c, k) for c in careers], dtype=np.int64) for k in
         ("all_pro", "mvp", "opoy", "dpoy", "oroy", "droy", "super_bowl_mvp", "super_bowl", "super_bowl_loss", "playoff_wins",
          "rushing_title", "games", "passing_touchdowns", "receiving_yards", "receptions")}
    nostat = np.array([c.group in rules.NO_PRODUCTION for c in careers])
    linemen = np.array([c.group in rules.BIG_GAMES_CAP for c in careers])
    qb = np.array([c.group == rules.G_QB for c in careers])
    receiver = np.array([c.group in (rules.G_WR, rules.G_TE) for c in careers])
    par = np.array([rules.PAR.get(rules.GROUPS[c.group], 1) for c in careers], dtype=np.int64)
    comp = np.array([rules.composite(c) for c in careers], dtype=np.int64)

    def total(p):
        honors = (p["ap"] * A["all_pro"] + p["mvp"] * A["mvp"] + p["poy"] * (A["opoy"] + A["dpoy"]) + p["sbm"] * A["super_bowl_mvp"]
                  + p["roy"] * np.minimum(A["oroy"] + A["droy"], rules.ROOKIE_OF_YEAR_CAP)
                  + p["rt"] * np.minimum(A["rushing_title"], rules.RUSHING_TITLE_CAP))
        games = np.minimum(np.where(linemen, p["gcap0"], p["gcap"]), np.maximum(A["games"] - rules.GAMES_FREE, 0) // p["gpp"])
        prod = np.where(nostat, 0, np.minimum(p["pcap"], p["pcap"] * comp // par))
        champ = (np.where(qb, p["ring_qb"], p["sb"]) * np.minimum(A["super_bowl"], rules.SUPER_BOWL_CAP)
                 + np.where(qb, p["loss_qb"], p["loss"]) * np.minimum(A["super_bowl_loss"], rules.SUPER_BOWL_CAP)
                 + np.where(qb, np.minimum(p["pwcap"], p["pw"] * A["playoff_wins"]), 0))
        miles = (np.where(qb, p["td400"] * (A["passing_touchdowns"] >= TD_AT), 0)
                 + np.where(receiver, p["y15"] * (A["receiving_yards"] >= Y15_AT) + p["y17"] * (A["receiving_yards"] >= Y17_AT)
                            + p["r13"] * (A["receptions"] >= R13_AT), 0))
        return honors + games + prod + champ + miles

    def run(p):
        scores = total(p)
        passed = scores[:n_in] >= p["bar"]
        tr, te = last <= TRAIN_THROUGH, last > TRAIN_THROUGH
        cnt = lambda mask: (int(passed[mask].sum()), int(mask.sum()))      # noqa: E731
        return {"recall": cnt(hof), "recall_train": cnt(hof & tr), "recall_test": cnt(hof & te), "fp": cnt(~hof),
                "fp_train": cnt(~hof & tr), "fp_test": cnt(~hof & te),
                "cases_ok": bool(all(scores[index[x]] >= p["bar"] for x in REQUIRED_PASS)
                                 and all(scores[index[x]] < p["bar"] for x in REQUIRED_FAIL)),
                "cases": {x: int(scores[index[x]]) for x in named}}

    rng = random.Random(seed)
    results = []
    for _ in range(samples):
        p = {k: rng.choice(v) for k, v in GRID.items()}
        p["bar"] = rules.BAR
        m = run(p)
        if feasible(m):
            results.append((m["recall"][0] / m["recall"][1], -m["fp"][0], p, m))
    shipped = run(dict(DEFAULT_PARAMS))
    results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    better = sum(1 for r in results if (r[0], r[1]) > (shipped["recall"][0] / shipped["recall"][1], -shipped["fp"][0]))
    return {"samples": samples, "seed": seed, "feasible": len(results), "shipped": shipped, "shipped_feasible": feasible(shipped),
            "feasible_with_better_recall_or_fewer_fp": better, "best": [(round(r[0], 3), -r[1], r[2]) for r in results[:8]],
            "plateau": {k: sorted(collections.Counter(r[2][k] for r in results).items()) for k in GRID}}


def sensitivity(rows: Sequence[Mapping]) -> list[dict]:
    careers = [rows_career(r) for r in rows]
    base = dict(DEFAULT_PARAMS)
    named = {name: rows_career(next(r for r in rows if r["name"] == name)) for name in REQUIRED_PASS + REQUIRED_FAIL}
    m0 = _split_metrics(rows, careers, base)
    out = [{"parameter": "(shipped)", "value": None, "recall": m0["recall"], "fp": m0["fp"],
            "cases": {n: score_with(c, base) for n, c in named.items()}}]
    for key in GRID:
        for factor in (0.8, 1.2):
            p = dict(base)
            p[key] = int(round(base[key] * factor))
            if p[key] == base[key]:
                continue
            m = _split_metrics(rows, careers, p)
            out.append({"parameter": key, "value": p[key], "recall": m["recall"], "fp": m["fp"],
                        "delta_recall": m["recall"][0] - m0["recall"][0], "delta_fp": m["fp"][0] - m0["fp"][0],
                        "cases": {n: score_with(c, p) for n, c in named.items()}})
    return out


# --------------------------------------------------------------------------------------------------------------------
# the game's own simulated seasons (hn1 runs rel301..rel310: the same 2026 roster, ten different seeds)
SIM_GROUP = {0: "QB", 1: "K", 2: "P", 3: "WR", 4: "DB", 5: "DB", 6: "DB", 7: "RB", 8: "RB", 9: "TE", 10: "LB", 11: "LB", 12: "OL", 13: "OL",
             14: "OL", 15: "DL", 16: "DL"}


def sim_careers(runs: Path, seeds: Sequence[int]) -> list[tuple[str, int, "rules.Career"]]:
    """Each player's ten simulated seasons added up as one constant-ratings career (a stress case, not a continuous run).

    The five voted awards come from the native vote (the shipped hn1 rule); All-Pro, rushing title and Super Bowl MVP from the
    retail slots; a ring for every player of the champion club."""

    agg: dict = {}
    for seed in seeds:
        data = json.loads((runs / f"rel{seed}.json").read_text(encoding="utf-8"))
        text = data["advance"]["notices"][0]["text"] if data["advance"]["notices"] else ""
        m = re.match(r"(.+?) won Super Bowl \S+, \d+-\d+ over the (.+?)\.", text)
        champion, runner_up = (m.group(1), m.group(2)) if m else (None, None)
        clubs = {t["team"]: f"{t['city']} {t['nick']}" for t in data["teams"]}
        seen = set()
        for p in data["players"]:
            key = (p["name"], p["pos"])
            if key in seen:
                continue
            seen.add(key)
            a = agg.setdefault(key, collections.Counter())
            for src, dst in (("games", "games"), ("pass_td", "passing_touchdowns"), ("rush_td", "rushing_touchdowns"), ("rush_yds", "rushing_yards"),
                             ("rec_yds", "receiving_yards"), ("rec_td", "receiving_touchdowns"), ("sacks2", "sacks_half"), ("def_int", "interceptions")):
                a[dst] += p[src]
            if champion and clubs.get(p["team"]) == champion:
                a["super_bowl"] += 1
            elif runner_up and clubs.get(p["team"]) == runner_up:
                a["super_bowl_loss"] += 1

        def credit(slot, source, field):
            v = source.get(slot)
            if v and v.get("name") and (v["name"], v["pos"]) in agg:
                agg[(v["name"], v["pos"])][field] += 1
        for slot, field in (("mvp", "mvp"), ("opoy", "opoy"), ("dpoy", "dpoy"), ("oroy", "oroy"), ("droy", "droy")):
            credit(slot, data["native_award_names"], field)
        credit("rush", data["award_names"], "rushing_title")
        credit("sbmvp", data["award_names"], "super_bowl_mvp")
        for i in range(10):
            credit(f"best{i}", data["award_names"], "all_pro")
    return [(name, pos, rules.Career(group=rules.GROUPS.index(SIM_GROUP[pos]), **dict(a))) for (name, pos), a in sorted(agg.items())]


RECEIVING = ("receiving_yards", "receiving_touchdowns", "receptions")
SIM_SCALES = {"rushing x1.3": (("rushing_yards", "rushing_touchdowns"), 1.3), "rushing x0.8": (("rushing_yards", "rushing_touchdowns"), 0.8),
              "receiving x1.25": (RECEIVING, 1.25), "receiving x0.8": (RECEIVING, 0.8),
              "passing touchdowns x1.2": (("passing_touchdowns",), 1.2), "passing touchdowns x0.8": (("passing_touchdowns",), 0.8),
              "sacks and interceptions x1.2": (("sacks_half", "interceptions"), 1.2), "sacks and interceptions x0.8": (("sacks_half", "interceptions"), 0.8),
              "all production x0.5": (("*",), 0.5)}
PRODUCTION_FIELDS = ("passing_touchdowns", "rushing_touchdowns", "rushing_yards", "receptions", "receiving_yards", "receiving_touchdowns",
                     "sacks_half", "interceptions", "field_goals_made")


def _scaled(c: "rules.Career", spec) -> "rules.Career":
    import dataclasses
    fields, factor = spec
    fields = PRODUCTION_FIELDS if fields == ("*",) else fields
    return dataclasses.replace(c, **{f: int(getattr(c, f) * factor) for f in fields})


def sim_proxy(runs: Path, seasons: Sequence[int] = (5, 8, 10), first_seed: int = 301) -> dict:
    """Careers of the game's own sim at 5, 8 and 10 constant-ratings seasons: how many reach the bar and the floor, by position, and
    (ten seasons) how that count moves when the sim's production is scaled (the production term saturates, so it barely does).

    The sim credits a lost Super Bowl from the champion notice; it has no per-game playoff results, so quarterback playoff wins
    stay 0. ``*_live_only`` leaves out the lost Super Bowls as well: what a franchise player reads until the counters exist."""

    out = {}
    for n in seasons:
        careers = sim_careers(runs, range(first_seed, first_seed + n))
        scored = sorted(((rules.score(c), name, pos, c) for name, pos, c in careers), key=lambda x: (-x[0], x[1]))
        passed = [x for x in scored if x[0] >= rules.BAR]
        live = [rules.score(live_only(x[3])) for x in scored]            # a franchise player until the honors owner writes the counters
        out[n] = {"players": len(scored), "at_bar": len(passed), "at_floor": sum(1 for x in scored if x[0] >= rules.FLOOR),
                  "at_bar_live_only": sum(1 for v in live if v >= rules.BAR), "at_floor_live_only": sum(1 for v in live if v >= rules.FLOOR),
                  "by_group": dict(collections.Counter(rules.GROUPS[x[3].group] for x in passed)),
                  "top": [(x[1], rules.POSITIONS[x[2]], x[0]) for x in scored[:14]]}
        if n == max(seasons):
            out[n]["production_scale"] = {name: sum(1 for _n, _p, c in careers if rules.score(_scaled(c, spec)) >= rules.BAR)
                                          for name, spec in SIM_SCALES.items()}
    return out


# --------------------------------------------------------------------------------------------------------------------
def _print_evaluate(rows):
    pct = lambda t: f"{t[0]}/{t[1]} = {100 * t[0] / t[1]:.1f}%" if t[1] else "0/0"        # noqa: E731
    first = None
    for years in (IN_RANGE, EXTENDED_RANGE):
        e = evaluate(rows, years=years)
        first = first or e
        print(f"bar {e['bar']}, retired {years[0]}-{years[1]}: {e['inductees']} real inductees, {e['notable_non_inductees']} notable "
              f"non-inductees, {e['other_retirees_in_dataset']} other retirees in the dataset ({e['other_retirees_that_pass']} of them pass)")
        print(f"  inductees that pass: {pct(e['recall'])}   (retired <= {TRAIN_THROUGH}: {pct(e['recall_train'])}; later: {pct(e['recall_test'])})")
        print(f"  notable non-inductees that pass: {pct(e['false_positives'])}   ({pct(e['false_positives_train'])}; {pct(e['false_positives_test'])})")
        print("  by position:", {g: f"{a}/{b}" for g, (a, b) in e["by_group"].items()})
        print("  misses:", "; ".join(f"{n} ({g}, {y}) {s}" for n, g, y, _h, s in e["misses"]))
        print("  false positives:", "; ".join(f"{n} ({g}, {y}) {s}" for n, g, y, s in e["false_positive_names"]))
    print("named cases: score = honors + games + production + championships + milestones; live-only drops the two optional counters")
    for c in named_cases(rows):
        p = c["parts"]
        print(f"  {c['name']} ({c['group']}, retired {c['last']}{', real ' + str(c['hof']) if c['hof'] else ''}): {c['score']} = {p['honors']} + "
              f"{p['games']} + {p['production']} + {p['championships']} + {p['milestones']}; live-only {c['live_only']}")
    return first


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("evaluate", "sensitivity"):
        sub.add_parser(name).add_argument("--data", type=Path, default=DATASET)
    r = sub.add_parser("replay")
    r.add_argument("--data", type=Path, default=DATASET)
    r.add_argument("--from", dest="first", type=int, default=2010)
    r.add_argument("--to", dest="last", type=int, default=2026)
    f = sub.add_parser("franchise")
    f.add_argument("--data", type=Path, default=DATASET)
    f.add_argument("--to", dest="last", type=int, default=2035)
    c = sub.add_parser("candidates")
    c.add_argument("--data", type=Path, default=DATASET)
    c.add_argument("--out", type=Path, default=CANDIDATES)
    for q in (f, c):
        q.add_argument("--roster-check", type=Path, default=ROSTER_CHECK)
        q.add_argument("--no-roster-check", action="store_true", help="seed without the game roster dedupe (not what ships)")
    rc = sub.add_parser("roster-check")
    rc.add_argument("--data", type=Path, default=DATASET)
    rc.add_argument("--image", type=Path, required=True, help="a built disc image (read only)")
    rc.add_argument("--out", type=Path, default=ROSTER_CHECK)
    s = sub.add_parser("search")
    s.add_argument("--data", type=Path, default=DATASET)
    s.add_argument("--samples", type=int, default=20000)
    p = sub.add_parser("sim-proxy")
    p.add_argument("--runs", type=Path, required=True)
    for name in ("fetch", "check-cache", "build-data"):
        q = sub.add_parser(name)
        q.add_argument("--cache", type=Path, required=True)
        if name == "build-data":
            q.add_argument("--out", type=Path, default=DATASET)
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            print(json.dumps({"fetched": fetch(args.cache)}))
        elif args.command == "check-cache":
            state = check_cache(args.cache)
            print(json.dumps(state))
            return 0 if not state["missing"] and not state["bad"] else 1
        elif args.command == "build-data":
            data = build_dataset(args.cache)
            args.out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.out} ({data['counts']['rows']} rows)")
        elif args.command == "evaluate":
            _print_evaluate(load_rows(args.data))
        elif args.command == "replay":
            rows = load_rows(args.data)
            out = real_replay(rows, args.first, args.last)
            print("\n".join(class_lines(out["classes"], range(args.first, args.last + 1))))
            print(f"class sizes {out['sizes']}; {out['inductees']} inductees, {out['real_members']} of them real Hall of Famers")
        elif args.command == "roster-check":
            doc = roster_check_document(load_rows(args.data), read_game_roster(args.image), args.image.name)
            args.out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.out}: {doc['counts']}, {doc['retirees_checked']} retirees checked against {doc['roster']['players']} roster players")
        elif args.command == "franchise":
            out = franchise_replay(load_rows(args.data), args.last, None if args.no_roster_check else load_roster_check(args.roster_check))
            print("\n".join(class_lines(out["classes"], range(2027, args.last + 2))))
            print(f"seeds {out['seeds']}, class sizes {out['sizes']}, still waiting {len(out['left'])}")
        elif args.command == "candidates":
            doc = seed_document(load_rows(args.data), None if args.no_roster_check else load_roster_check(args.roster_check))
            args.out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.out} ({doc['count']} candidates)")
        elif args.command == "search":
            print(json.dumps(search(load_rows(args.data), args.samples), indent=1))
        elif args.command == "sensitivity":
            for row in sensitivity(load_rows(args.data)):
                print(row)
        elif args.command == "sim-proxy":
            print(json.dumps(sim_proxy(args.runs), indent=1))
    except (CalibrationError, rules.HofError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

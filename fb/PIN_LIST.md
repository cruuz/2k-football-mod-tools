PROVED OFFLINE: candidate E base is `c1a8a769580afefcb8d7bb6c6e5391f83faa9f8e`. All 12 affected model pin files are byte-identical to this base. No geometry, camera, model compilation or base texture-generator function changes. Only each owner's `apply_to_image`, `bundle_state` and `image_status` change.

| Evidence | Model pin file, unchanged | SHA-256 |
| --- | --- | --- |
| PROVED OFFLINE | `data/nfl2k5_state_farm_model/pins.json` | `8877a752ee4b9c78815e81c81246f6f19bd205c3d0eb058977eb67c9bbdce047` |
| PROVED OFFLINE | `data/nfl2k5_mercedes_benz_model/pins.json` | `793a9aced1a99400b13555070043e00db4ee95611553053ac91cedeba868cbfd` |
| PROVED OFFLINE | `data/nfl2k5_highmark_model/pins.json` | `bfb374ab8aa5c9c6a96eaadc4670f3d4c3c34d058f4b3c6ab1596883ad39ea49` |
| PROVED OFFLINE | `data/nfl2k5_att_model/pins.json` | `9753c4976554eb26d1e93a3960dc77f7bdaf987672ccfd2dc64ae8a8b54fbb98` |
| PROVED OFFLINE | `data/nfl2k5_lucas_oil_model/pins.json` | `3b61aa22272539d1f966315797f21e8e71297b98feeb8589ed19648c465dc489` |
| PROVED OFFLINE | `data/nfl2k5_everbank_model/pins.json` | `6845af59cf5fed3771d8fa3f3488f12e09b3668e235e01cc0ab22cd851c498a3` |
| PROVED OFFLINE | `data/nfl2k5_hard_rock_model/pins.json` | `7a3feb199e121949e349731d667928bad84aff2a15f473d072304d7cb389bb42` |
| PROVED OFFLINE | `data/nfl2k5_usbank_model/pins.json` | `1664f8ee1876e93e1c0dbcf30ed58f31ba01f3a5a3b640e423a85b5f4548f4fd` |
| PROVED OFFLINE | `data/nfl2k5_sofi_model/pins.json` | `c1b28ee29df0f99144eb24d1387d7dfe9aa5e32580d03c6f52700d0774207a2d` |
| PROVED OFFLINE | `data/nfl2k5_levis_model/pins.json` | `c3e2c3b746fca5b6f4cd246d436c3e5b0f3d0c76d3c75205381f24522b34d73b` |
| PROVED OFFLINE | `data/nfl2k5_allegiant_model/pins.json` | `28afcc8678a3036190a03497765e0f0659d5a803c85cefba76e156fdabf79ecf` |
| PROVED OFFLINE | `data/nfl2k5_lambeau_model/pins.json` | `17aaf65fbd12185e48170483fd44e7c8a56ebd58ee3071dfb9073531bc29282c` |

PROVED OFFLINE: every model capability retains its existing registry hash-pin array. The 2026 venue-art capability retains its four existing hashes and appends two:

| Evidence | New registry hash pin | SHA-256 |
| --- | --- | --- |
| PROVED OFFLINE | `data/nfl2k5_stadium_shared_art/special_venues.json` | `3ff1c086a715022c54e264e43de30db5b6ebed042190bac5ab16bb1aa527f516` |
| PROVED OFFLINE | `data/nfl2k5_stadium_shared_art/design.json` | `620bc9647348ffdd4ee5d349602cdb03b48880209bb4b0ddea0bf81396e69176` |

PROVED OFFLINE: source fingerprints and the packaging catalog change as follows. The reviewed PNG catalog adds 120 authored PNGs (60 native and 60 masters); its checker constant is updated. The catalog grows beyond 128 KiB, so the checker's bounded read limit becomes 256 KiB. Twelve model registry entries add helper evidence and input constraints without changing their hash pins.

| Evidence | Modified integration path | Before SHA-256 | After SHA-256 |
| --- | --- | --- | --- |
| PROVED OFFLINE | `mod_editor/capabilities/registry.v1.json` | `db66a57ccd326d94253d2d8cdfa180c5d817f48d57e2b6cd0c3a114a90bee44d` | `43cca835816ef707f776fbba4fd16ab67f37703898b308327aaec5b357743d58` |
| PROVED OFFLINE | `mod_editor/core/mod_build.py` | `d2f86b4b6a869cd1ac639f433552ac319526daaaf6346b53ab180821aa931ffc` | `ba1c8777ef8f5a302643dee4e372e97fb241669a4e2db330c43b9aac6e5a37f3` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_allegiant_model.py` | `c4e5a8d210ce23f70423a0fb260b8cacd1e1ef40f272ddc223ce4092e8b7bd53` | `8184a9440a01715d65049072121a240008114b5ef7d7739206d13cf5328349e0` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_att_model.py` | `e02e115ecec7947608002810f08ec418c48a7dd3db93c8cd4d21cd396195d6f5` | `07d4960fafeb4e20456d7fe028c5bbec42f0f454f7c27a3c9064f7595c73b1be` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_everbank_model.py` | `624e0e18f58453f7d53d690c8969a9ac244de3d0e99907564b20cd31abc0e1e8` | `ce038f1620c02364eeacfdc0683783b679529ebdad3a460152a03c1889344cfd` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_hard_rock_model.py` | `a5e5eddc42ff4027f0257214e4ed42d9076daf5796ece62641a07d4847a77fce` | `3610d2acebfebe3c6d60362430e6e27b6ea5dbcf365e203b631d544e36b72ca3` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_highmark_model.py` | `6e5b4e7d589ee9ff78cab32134483a01490e2fa0cca0385b977fd27c0e4eaa93` | `a3c998e354211437347852ec49d8f4cfaa3dcb2898d9f032e4fe2c4d6740f130` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_lambeau_model.py` | `12d20320ac338139739c1de10025e32b980965708c60f808e7964c6c5ec55619` | `80c432de74b48237508911cb158c78df384c337259385192096d5e8db9d70114` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_levis_model.py` | `d426ac305d33662cb232fa08517f8fcfce03c90ef0cb6f2d8a755b493555129d` | `404e9465ba58ba045220d5660e1b49774c3258dcd955cca5411578814ed50edb` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_lucas_oil_model.py` | `38251d4a281778c81b9385246b27408474192fd728bb407776a32405d8e119dd` | `62773ecfc7365510dbfb4960916be60fa01e1e666f9625da2c080217a9fac2b3` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_mercedes_benz_model.py` | `26f043708f28c81b633f967ac42ba4ccb135dd78c53b9000854819d375cb5725` | `dd93914aa137efb1b4ccbd9a55eeb33eab8fed16db69534a38b782b1b5c426b0` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_modern_venues_2026.py` | `27211f71a24cc08c024132897249983fef32be48f2f579694428c2ca91048603` | `068cdab0d69657077db8dbec34143d75a6c954f92bba898ed97f8e6c33efbb88` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_sofi_model.py` | `863d818a643fce662151b1895bcc32bf18742ac4d264eea4bbd2b9cae3d0ba46` | `1cc2d26f2edcb3ed0bc4a1271a30fce630be1634189eee9ce75d14cfa53e5471` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_state_farm_model.py` | `69c9e8dcd0d9c18cbb8ab75762fe5bd9de41b80ea8d0e1b822f235c24ea5f615` | `0c55b5935c2592f9a8b8e80bbec739a320a8a351d6f7dec92c9041da03b8ad1c` |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_usbank_model.py` | `fb651fb9c64f26b7786bcee197b70bda100f0a7612fbd4e2c6dcc2a6080ce769` | `c3d919292774221055c94f9b70eb230fcd059ddc1b8329e70211d1f824979fe9` |
| PROVED OFFLINE | `packaging/check_2k5_mod_studio_release.py` | `abf646b8a5b95bd3b43bc59b46a6d1be31783c277e33a37ee4e8730f18e6715c` | `2243b500d45b5d7f0b0c49903364533321c448883e186b7712210a9c6c97e559` |
| PROVED OFFLINE | `packaging/nfl2k5_scorebug_template_pngs.json` | `27ce8e36da6efa93070e883de22625f9b8707eb2469e5f7beb0444aff9e41de5` | `dfa63ed918cac8b3338008ade138afd5bf170f079376625708f9bc76d542b236` |
| PROVED OFFLINE | `packaging/release-allowlist.txt` | `7f8af430cae91a4af9482a1596a3a6b7065f94d599f9cf7e66fea824a1d84aaf` | `1ffcec42ce3d68867f65f5c969272dec1ca57612b49f19ccc0d89e2d46b20a58` |
| PROVED OFFLINE | `tests/mod_editor/test_nfl2k5_modern_venues_2026.py` | `b793c515749dfa95ae1b6677b374a3a7ecf1ac145d1fdfd24d42b44ec1cfea8c` | `9138ebad4799b167de0099b8fad0dd7201f9f929678dc5bfb28870db23829d41` |

PROVED OFFLINE: composed fan spans are dynamic receipt pins, since the user selects the u4 art root. Each records its exact parent model hash, offset, length, new hash, art digest and native texture receipt. Acceptance checks all of those span/parent fields. They are saved in the model sidecar and in `model_fan_art` inside the existing `.venues-2026.json` sidecar. The latter is already carried by `xdvdfs_compact.STUDIO_RECEIPTS`; the new regression test checks this persistence without compacting a disc.

PROVED OFFLINE: the three measured span changes, including all before/after hashes, are in [fan_proof.json](evidence/fan_proof.json). All other model/registry pin arrays are unchanged. The private art root is read directly; no new fan asset pin file or per-model fan art copy exists.

DESIGN: main must regenerate the observed-build cave reservation manifest after integration. Fourteen fingerprinted source files change, listed with exact old/new hashes in [cave_source_changes_fb2.json](evidence/cave_source_changes_fb2.json). Its generator performs a build, which this job explicitly forbids. No cave pin was edited by hand. Preserve the venue-art receipt beside exported images so composed model status can verify after copying or compaction.

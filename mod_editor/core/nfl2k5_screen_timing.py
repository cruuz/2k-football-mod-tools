"""EXPERIMENTAL / UNWITNESSED screen timing in fixed PLAY resource spans.

No executable patch or bundled game assets. The resource API does no file I/O.
The optional image adapter uses the existing archive reader/writer. Pins cover the declared
assignments of all 129 retail named screens in all 37 books, including skipped
plays. Names, flags, descriptors and node bytes are compared; relative pointers,
orphans and unrelated plays are deliberately excluded so earlier category recodes
and copy-on-write chains compose. Unknown, mixed or foreign screen data refuses.

A changes finite 0.5 holds to 0.8; B changes nominal -10 yard QB moves to -7;
C changes zero/default pass timers to explicit 0.6; D combines them. Other retail
values survive. Only full finite hold -> release -> type-3 block sequences qualify.
Timing and gameplay benefit remain hypotheses; see ASTRA_SCREEN_PASS_REPORT.md.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any

from .errors import ValidationError
from . import nfl2k5_play_codec as codec
from .nfl2k5_formation_play_writer import (
    NODE_CAPACITY, authored_node_cost, compile_formation_play_creations,
)
from .nfl2k5_playbook_inspector import (
    BODY_SIZE, NODE_BASE, NODE_SIZE, PLAY_BASE, PLAY_SIZE, RESOURCE_HEADER_SIZE,
    Nfl2k5Playbook, parse_playbook_resource,
)

LEVELS = ("A", "B", "C", "D")
DEFAULT_LEVEL = "D"
LEVEL_LABELS = {
    "A": "A: Line hold 0.8 seconds",
    "B": "B: Nominal QB drop 7 yards",
    "C": "C: Explicit pass delay 0.6 seconds",
    "D": "D: Combined line hold, QB drop and pass delay",
}
# Generated from the private retail census. SHA-256 only, no bundled PLAY data.
# book-name hash: (outer index, retail/A/B/C/D declared-screen hashes)
_RETAIL_PINS = {
    "c7921615df44df3e2b4e77358ab62fb2038d5a436faa50a7a2b15d62a2e5bd9f": (307, (
        "ed7da5c4cde7ee72900e6c9e2c23407335f2c566fd1ae9d05dfeb0bd74a42365",
        "5952169fd33c554eaaf58fc162002802ac377bc95f6aa2826c766605f3b90222",
        "1f2ff8ca18f986af834c5cc191391b4c2498806c4dbe007e9d389d5d3aabcded",
        "031bbdda95ae89a66fa12c85a027766754d4e19e35bafd4684de7fa56aec2734",
        "650208bb7eeaa073a3c963c4cf50160eabe8596b4454ba4d7bbac5e42256a563",
    )),
    "8d87f1663045641686255839674e224fb969575b898caf111e0c5e0581c2b2ca": (308, (
        "406c3bf042616067d7234a282ddaf670f0dcb27b442c93ae46c8576244e78787",
        "81189b036cdb257aa47ab513bc80f47a0a78056dbc652e88f2c6955651d7476c",
        "4a2a73f25dcdb243bb80f5b436ed0788d465400ce0d2bba53df807ab057b6f82",
        "771b7ecde7e53d4f8859c71f8ef7e440f35d31cd4081cdceda50af99049d6fb8",
        "d0430d230d5129d479bb95cc77000ae6f9713b0adb71d34b3e85974c918b8d51",
    )),
    "b27d564a40f4ca547cea9c6e4cd034a36b4e551d7110b319caee88553d0a5661": (309, (
        "8fdf1d34cf641ef8fec8f31db15ebf05547ba8170a7a40a2b527604dab155791",
        "f6e43a2dc52077c366cec0a0e20c54673dbd712fa8b39a23825fe3b8d9eda363",
        "43a3420c0b9c07d7995d8b579a728712fe49da95fb8bcf55163be287d0414cdc",
        "de45bb8c15058e9e402337d24228c4b3bb7bef193ace6ace23483c479c1f82ee",
        "d44cb2d08ed7adc4aeff3f8c9d1ac69e0c4b736f702f645b1a83a0ef1bed8ffd",
    )),
    "56a595b91294ca7c8b14f1c4ee6343645b829507e48862f2323cd6d074068e96": (310, (
        "e8950b0f75f726404b743b719d64737b1b3d9e615af0c46b7fba233792228762",
        "b47af19cad0da88dcf2fce16edeb96e8d410b2282eb6f71c50c3e6f4b3adf0a9",
        "c8c6c2746c1d4582f584dc30e0a62a9902929741f98c8c3c3ab43a5dbe4337b0",
        "c90eca872c7b50903a4d81da355a01b5e3aaf60d068d6c5dd55ba800e2d92398",
        "a0cd703fc3589d9c6b680339887758c24b8eabcc6ba67d0ae6783cd13734c434",
    )),
    "1c0d3a3a646a99cf5c25f7deec28d949a2c88a6a26e9ead82e7322477fb200fa": (311, (
        "29d7d9f51266b38147354263431baeb540462df7dc198754262a90cc585ce2ef",
        "a4f7b5abf2aa831543f4b6e0ae8282c70bf500fb00fe6551b6d1b7bf0fef68eb",
        "30ce0a4aef5a1c77685c6b60d98d387350f44cb464bf0ab967c0215a612c00c3",
        "4259ac6076d47b514d2872e22bafe4b58cfd80f43141affb518e2419477ef4e8",
        "58b14d166d5256e3feb789f1c29219af082e8458fc97274de9c31fad8c22af5e",
    )),
    "a85f4540a712162c6a4f04e3fb25a9863196ff63eaadf0d2a3e3b397e5f742d1": (312, (
        "d7569659b4f95c1cc7bff1bf340ecea6d490156532f0eede1299164c318c709e",
        "dcd51fde1bf65cc1de236a5c04356d24944296b652c89e93c7fe0742c24dd906",
        "e4e3273121eefcdccaf6f7e449880e02a32bc0d468140192c0045047d760fbe8",
        "05edd52c241b1fe206a641a5b6610520d50cff5e40b933a533ed59060da7ea52",
        "451555b600014c68fa96682b7f926c6935810f3d228b10909c61506c7fa7eb8b",
    )),
    "e778f9c8222683306760df6d48a2277a0bcac9d218d3e0225877a5c4f917845b": (313, (
        "26393886f840f513ad3e7ca78bbddebd7f3431f83d7c938a102891a95aa23c57",
        "4efd73e8194c182d5d1a54342ff5aeba29c83f33ea2b9f6a0c5686a371b22cf3",
        "c9427c0b84eafdb9982f0b0e41ed4f2d6edce2c982980792c025777b04c535f5",
        "6fb014f2a3c0c97d23397729140e55b30c2eaf548d7abf5ed0ed31667dd55ca1",
        "a84c86ec81666e140fa19ab653c0465ef3dd8651f998947986a4958bb8d3239e",
    )),
    "f79d30273e22c75096b989d2296b9c4cd38451359fd33c18e0d3817d288c1050": (314, (
        "e2c197acf03da27b60e95094193a41155d24960a5da5cabb7e345d0e0a79d5ed",
        "533891c26299426c89541cab28bd43d5098f0a187dfa707810ff441c16d796c6",
        "8a7c62e8e569c436422366f9691da6402b5d902f6d272b1492136bfb19cfce28",
        "d6c9c0686f1ff44c105025f6b36993ba938aadc59a7cc4aa0a2d599e97d8950e",
        "d506335f8588427a104882a6a3023440101f59f41ae27143743ca9848688cd93",
    )),
    "b0a8c8f2f15e6ed055f2755ea27bf96a68e1d484c1268d2bdb3dd341c7923103": (315, (
        "f36593b513f1641b44f06d5fdeba97946248f6b0fb469da9cf157c7aba21facd",
        "1801654e1ed7ccde88a8fcc883cb4fbfe5e557ac724160dc2c004c33d824b0ef",
        "58d707ad6326bc79d559ce37443f5ac0f5fb627cf244335735df569f76507551",
        "f0a7de338bf00f5a802b24b2e35f8596ad1a8aa905fdbaf6bf81fb66a74750ab",
        "a00b8e6e9e8838f0a452c8f94ff38ac7c1ec72d7882cf5a85e15474d19ded112",
    )),
    "2fcc32efa12bc6f248a98584b1e110f682b56f0b80154701975bea05bda90bcf": (316, (
        "6d9970c852ebfaa46eb7abca905ab2c38eceecd2be99af7f533955ea9fbb6f47",
        "4f0510b08f54484e2ee5e37022cc1edfba6ae9f76172f40003f62435fda9f0de",
        "2743b4edd7ff60c99b9fd609ac31ed4383b1ddb92a6351b575af151e55c37315",
        "4b939ee9a4c1dd4ce0c475c337631fe7235d978ac6058be943dd92d1baf0ae59",
        "08baa009d8c263e3f226f490060b00b1b950bc2c5b2483695b1ac5ba2b754761",
    )),
    "fdb299a1f0854938ff7c1c43e5182083907265d29d573b9eb0d7f5bc7785e7e7": (317, (
        "4aef6785d980051c46db8c2cfc23380595d1c46154394af1670449c4b9c3a295",
        "81d32d3c7d02dbb9c8c030276bbc2bb956aa95b0cae782b57345836ba667541c",
        "4cabe69a1ef15458a27682513771dbbfa35dbf5211a5a1823e45bff1f3f655bf",
        "6df700a93c63f0d78ab115921d01fdeb115c987863903c23c5556416f6e26912",
        "7410114f6e3fae5f30ed1c3ccc570c09329b7267e217c1ae762fdffd0a23d441",
    )),
    "936a161c39314b0540fe7415d2ad16cadb631568c4ebc57d6cff60f14edc099d": (318, (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )),
    "b4043b0b8297e379bc559ab33b6ae9c7a9b4ef6519d3baee53270f0c0dd3d960": (319, (
        "c901913fb0224c198a150e66dca17be9a7c575d857079443acd060c9f8061a6b",
        "c89f2bb07a9834987ea5a123651e8a0478c2effe9b9067c51d98095924d45e97",
        "b7ee93a47139bf64976cde99b32b567f09c5a5294a5a0a2d9b9bb9f26684c119",
        "b57510dc1a27dee6b0984de9c779d4e9d4d3bb667fa968d68efb24ea69f0648c",
        "7e456dae3f67d4327e70230518ffba24444734197d575a2fa03414c64a5295e4",
    )),
    "0ea1cffafb452cd87824d855743471724ba6eeafbebeba93c1b5117dafa6adfa": (320, (
        "e71418cf35a6db419ead3652b07e068cfd57e2dd16a8528e5532ee5ec50514b7",
        "53b16860b32c529e3effed2d6e19c82c68b8ddbe1e9a3c671d159a8973942da8",
        "14a9fb21076a6df7357fa8386ffe5e24692892f0b72cae10b864c50fd84918ee",
        "b8973a9e825aeddf9d6b23dd33121f44cb2b1e0ab96c51b8ee96ea50c9c72383",
        "2e931162a9465ca6a53a3f881b9c8e10df5447bda3b3e2bb10584a1220bce424",
    )),
    "4b92e66c84393de5952a938d14802eb9da8361267a071f53702be5bb2be9ced7": (321, (
        "534d10bade2ff818800ce0e299ada0271423e6b1efc0a54c1602098487a44d73",
        "78da9b5b756dd67440768d37165768d4e76ac3a1985e30a59d6e47bfb24496f4",
        "712a9625b6f101a282453a49e8b5bfaebb2a052efcb6aa11a910fafc6768b6a9",
        "ccfbc0711c486afbfe0a62fc0a37378e285efa4356a265aa103ad706feebd2d7",
        "cd6a6f8f5e0edd2a3ee88c9f5cfc2fbd5ef605ced7fdad3ec1435e8354c734cb",
    )),
    "c81ed803e323ad7f22e5e1c48f1cf07217457b2982b7ca85aa6f7e84c8758c86": (322, (
        "cad72f2ee297bd152c905e3f89fc06dca462c85905ac9bd166eb08d29cbbeb7e",
        "a58d281dee4c72e80ecfa0bb8dc56a098047e99507b9649f6fcbdece02843d33",
        "5074aa853753714abfaba220abac1f7d2c13e4f01d2c759027e141fa960b1bcd",
        "244796dd1b2dc79acd2e5b6cfde8ace78f9b56eda562bec382d8eb4df63a4a60",
        "d59d7d415d9a37316364b620bc8551a526e96e0843ab207827f26d129b342a2d",
    )),
    "cd8c07fdc045905b6ac54d264c02d8b1fc0d0601488c823f50fa02a6e50f10a8": (323, (
        "e4b6139b3aaf7e799030fe898280da683168d5f382880820c45eaa3a8795b0da",
        "f90d4d9463cc25a516b5d0c1e94768f7ee4fda9bcaee268eccdd655cca1e48dd",
        "e7d4ccd3335432d1a767a398ac1979c119dfc5d796b0dea45d387ad87302cf3b",
        "c019065ac240a2d30eccbc3f14535957077db5bf6577faab8d186186cc826123",
        "4ba773367e261151bfd9c8d09d4df44399370a51ec94a7f57edd1b666e375542",
    )),
    "3276fe5c35b66e289a64201ec43e950e7fd5a66bf059970d3ddd5aa34684150a": (324, (
        "730fdc865dac520fcab87946c296f40d0415928d4834a4f8861b0d062f4258c8",
        "297108a104f4edfbaa69539ba902fbe21ed6ac9159e64031eab9df0b599fba10",
        "3dd709a3ce14f844602b3e4ed0a1d421faab9f9843dc5b01aa02fa4b2878b1c1",
        "ad061eea54457a8278ec193f4460c43cf30dc3f79e011fb34e353dda73203e46",
        "06e5a9de50d7d202683901147f5416dbc6d09253501e68b89b5653844c1e5168",
    )),
    "6c7eaadf671470b35ee503e027a43fd044f544613cd9d9a1a2630f14f30a7646": (325, (
        "5852a893acf2808c5ff219119ce54887486472a89fc15864256d719ed162487a",
        "d03630a2c6a95201d403dddb06a1b18a9608a64db25d0a54c9ecf2dcb5812c72",
        "8c641b18a9f2bd8d57b51c613a4dcced222929292476fcd037b2346f64010025",
        "d366910f2b50d5d60cee2c7365d0701d57fb88eefd8ca0cce4e7a9e58fcd1e98",
        "18dfbbaa91ba2c47cc206e4aafffd67b1bffbdb33bcd145256c16284393cd024",
    )),
    "d319c28c2d23e115501524432e4ae591254394e799bf3e95c53f526525175e4c": (326, (
        "4610d9aed390416f3414af110692fd95f1ef7e50b1db51fada16a79bb7641e6a",
        "6a2815869ce11ea5541ff70006eede5f00ec6aa665c2e5e4f5593ce01bfede04",
        "f5c5e9eb45c5ab1088c5a84d3769f1dd2f5c50be4a929b3266ae907f64970ccb",
        "41146fe59d3cf3034b1432da34a8f2648516e519688e20ac34fb0b9a19ac66f3",
        "95628b8c6e4cedb9af6eb43bf5657da0ad994c754856af3feb702e75f1749e2e",
    )),
    "d539cd97ca1a108f9f5e3f611d7606d84c0aa35ea1973304e479b99025124e16": (327, (
        "63055d73f246bcfa431ee5b2a016a3c6c849b6d22d28f18f5d02139227ac584f",
        "a20f166549da39f6767a821532cb377c6675c56b9312b860f3d4bfddd944cf1e",
        "0d8d6a4cf105f13809f15766bfd1e2c2f414eb45ba88ade24777305603bc7999",
        "658935748cde0f8e6e538ed0d9d3a36f3272ec17f2d55dffbb5cb9f5412589b8",
        "f6259a72d64ea4f8516df8dea935bb28a55d10fe4bc2de1fb3b91e3a117cb36a",
    )),
    "23794d91c53ae875c8e247d72561e35d9d06ee07c70c9e0dbcc977a6d161504a": (328, (
        "fe98785a197b2044c0ee24026b2600fa5906de4051771767cf9819abd2327a37",
        "9755242785e5aca86f0712c8e0f6c8d7303f25193f3691000817f0766b9792c8",
        "11861d09862ab80c345034598c89bb0e727534bb519532e14fec75717d082b18",
        "8ef6fbb5b74fffbc5f58a27addda809882e169c1d43482bc14da9dd173447620",
        "6607b3416c2a1fea2192a07d2e4acf81dad43bf1648ec412e3f9018c1df4d1a8",
    )),
    "296e38f9bf3763f6662e1ca0419a09d176e7fffc18de551c7eb134035bf957fc": (329, (
        "3c5a05789e4fc424e31e6f5f9c6656337d86990c62b639715072dd768afc9e57",
        "0bb2a68badae5323b2b659878c62a8d3d8eaaa7d5177a9e85e354a5c26256d75",
        "e0b05df21edc5c822a647f2ed0978d1ad49d9c6c08a35f7207e4afc843b28448",
        "c96119f7cc42544106fe5a8de3a5221c8e7eea2e6d9f95c2397cbe47dfa3eb79",
        "54ddb6594d39b0763a9cfda40bfde855ca4067a1c91ddbea47b7d7f05f3aad1f",
    )),
    "7092ffd5d866d79c31d80f2c7dc184b6be02f32a5742fb4c1185978293b2713c": (330, (
        "a3f0d9327094e5d028a66b23990ef40e25f3e6ffece679fa4ffd2566ed90722c",
        "c5c5770a5435437a486ae1a09515e38b9bb75ed406d4933ab5fdb93d4bdd41e1",
        "947dca767b8919895be6f12a9421ebca8898d64edd2fb6771ef15377bf4ac3d4",
        "0b35c5e6e86605732a7992ece01e39f49f53f9ff65156b9ea94560a04d121bdb",
        "be6cb76a0ba495a958c3fe66fe8ab3f383d852a726bb9f1d69a951c193bab881",
    )),
    "02903988994c0f07023c469816cfafffd18404028d0f0068cebaab2ccf38a149": (331, (
        "626fdb465316689835ee32d6a80823982304285297caeb9eccffca879bbc9143",
        "f2c956da708da3fb677b946ad2c462f42ff0d57031d0eaef6c5058cf7f0ad5a9",
        "f2474d057eed05d09d3ff4b25dc874cc048e842e6a9be7f03a804cd55b9abf66",
        "f392593d4414347eaca376b2d8f89e5523a521d0b67a173d70a28e53a44d16f7",
        "ef15d53e1b86a143be36e0607ce37eda896d45b42a2dbef94ecaa2a44e678a83",
    )),
    "036240e37210e2eb49e90c0c05b39559b9772563ac3ea54de0bc129a6225b33b": (332, (
        "d6a3d7e64a2021792b8ed24b895c68ebaae7ce1a13554ab106ccb249e946f248",
        "9f2848e941917ad753e669d3549c334d56b067ce21ecbd38461de0a0c1c8b477",
        "3e820bd8cc01e0f8d8e78a32fcfbfea49bd3a7b03ccde18292d54e5a36b1c577",
        "e3affc5f80faeae7f79a532d4e1f37dfa927ced2881d3aa3531047a07f76380f",
        "ee6f94592921e877b8a4c66d50773f9a26b550756315069e7b0a948558f40247",
    )),
    "24c32f8b97218e6ae946901ea6e3cb2a151f94e7686a6ccd1d492cd76ad02a83": (333, (
        "6cf84859d1034e96f797da4f8f37e0445923e117623cf29926ca4d40dab58297",
        "4d194418732956440f82bcd2015d2a6ed31d9f1cec11781ac3cce95436ed7a27",
        "9e4159e0a016fe945fca05b0fd7b3f9cba4fa41c19e4faf8925f070489f743dc",
        "ddf0eae0c677225a71a72baabfbd4fe7553aa7eb217796f3ab24192944760bcb",
        "00c32a32c62783c8369afd2609e6f191abd048907d09ce81edf21bb26aa96781",
    )),
    "e7932041b7015d184f77bc5a4befcd13a1910a2735567c087c89afc794135c09": (334, (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )),
    "52367a6622b19f08825e915fad80c542ad4f4c34dbcebad9f5007994b3e39208": (335, (
        "3a2d6006a352bc3d67b4d94c92a2ce463b975e149fff815bc9c8a14b91dff805",
        "e6cc010add03f9daf5ca4eda483fb44c1c94a9a1ee61d2358c938f9bb56508f2",
        "73a5c57af92c1c20ef8a915eba7551d029978ee79f796ea1fab05b97fa92c084",
        "4df6e2a1a6c9b77dff48600d69e0fd7e8ce9b1517584dbdf666153dca01e8307",
        "a53028316862c420ab382e758b8d4238871580d62b11a2020b1778a10e107fcb",
    )),
    "495496f0156b1a6cf5cbebd2d575c02cc9c68884300c14a6a759bc4129d41057": (336, (
        "293420a3cf873e653a8ed73789c6772a7abd6fd8b4cef7c081c12ec65aeddbb1",
        "a5069c84b715f7c92d370592243c9d665c17b405428c5082d704df3ae918016f",
        "fc83cd466f4f09cdc7cdd22db318ee734b462a44594464764e30d6fc1ad10ac3",
        "322de979ab870242e69a636bea256801d7dad4d781fd6688fe2f8c5d8d7def44",
        "e55cf908dc3ba5bddc41d8c9c8f7de34d00c6694b9e91dafe2d3548379b6b33b",
    )),
    "08dd9890141cdccd3999d425a3492bfb742823adb8c56586370cd28ddf72f65b": (337, (
        "d26e8d1f38b5abf50ec6f0660530e10df20a6aced6b333ffa31dccefdb4b9085",
        "a34fa3f99aaccd59607ad35b02410bb2200ea828c08ec6000619406deabe2a89",
        "3e8117067355206752e5d7377a34793d3366b205b8241d48582a18dc74f48000",
        "1299b8b10171eda0babe2d873fd685fb20fdf9d61cbb9edc7ab46bf93b038d72",
        "c8e6e0062917c10c00fa9771e9d1f6cbfc8d4f6db3d22632b6b1fd8421622cff",
    )),
    "6612396204354eb1edad994b210abd2880588ea3879854626dd7ee9c106bb455": (338, (
        "7d3b31437237e74f4ae61afa074ed3139ef702778fe1381779ebce175f2c8a0f",
        "94b7c87b395d7e931643d6cf029b36dddd10bc643627e18c03f01f9414a66312",
        "009c269147859f02d06f26838410cd167939970cf8be65eb6f38c0791d205ade",
        "60467d9a7f9e0e827cb82e459d06e796bbdaa09bc50febe4fa6e6ffd06ded17d",
        "c7bd73321953799f2545939491265e8dcbed99b63287aed1f59135e3081256bb",
    )),
    "5505bbe316987e0796199859069bcff8a8bc71d1605da2abbbc8bb7ffdffc6e3": (339, (
        "7b2e224a373f28c08cf2268d0eae9014a540e72b0f446e06d19ee2fe2c739270",
        "d7825f019f533bab6afdca5bf0dcba69f03b15542e1716aac0f2dd6d606d917c",
        "5e89199639660fd35bda612e094f3f53df87106b87856b1b36c4bcf19016d1f3",
        "1be729501e98e30d24c61407e3c691bbcafa32cab4605a51923ee00a5d5052bf",
        "c0a6a9c7d7f8c8fedb3753923816d0c1d0be201078e4ebd470e1da32a84dc966",
    )),
    "791b0ac348749055f0aa77a0ba17854a031767621a242f6adabc87ac7ddef118": (340, (
        "3b81415ce6d315ec541629e306482c2d725f0fe71d398a29ece06e20cad1e43d",
        "595db16ae33baabe2f2efa40d6bb56af7a402040b4b9d5d6af3098b39b69a190",
        "c8ede674732470a43adeb31b4cc0434e9feb9051219cdb1397b642a09cdc64ce",
        "626623dd86007a3e6fc9b1cb70401ab0ba3c567302b12e26295d9f6015e04196",
        "3b7b215f97c05f900125bc4f0ebe31453e03c0f4fd3bfafae410d1aedec05cc5",
    )),
    "5a15b6c4e2f863171b809f269c66c5fa8abf9ffcac6f6ff79a83a26f1c59ee55": (341, (
        "f2fd22db67ba0776f002bc4ccd9e0b92565ad116b0a83d70e6f59bfd494ddf66",
        "02b28ff44a572db1d29257dced8ea843bf9cf2e343a49f7bc59dc4ccacbe8157",
        "466211c3097f8e54e6fd933d22b828e391e8a1d9b2313346f6acdbcb6d80e358",
        "f9a1b1471a599106172cd7cd1f086bdd6377ed65eb8e918947877b1c36c02610",
        "b2263825a1c19517f0c99c8ae6dc5d7fdaf6b6ed79b9822b2578990a2ad2cbbe",
    )),
    "2eabe007d86c4523f543a7ab0c3440c1655093a81f768ce94b2569dbe9d92423": (342, (
        "8ee063a63fbc41a64cc3cd7925297d4c941c638c073172466b54cbe039677a3e",
        "62d1a3f9c39817ef8ed411eaff72e33811df0638c20b26c2c1e358b9ba2b3858",
        "c816fa6464732a10d87ea831e8c32288d50abc8ac86764da0d0075e735a36e12",
        "a9b96d70b96516b94c0d3ae8408b701999698450c0e7242ba0fc3368d2db3d07",
        "794d784c2f38e4761a914c6ddacf230eb270f18da01e2534b3a0d8516c520b6f",
    )),
    "9bc36dea54a43d822e927460238742af8e9ab3ed55a72df9397b6e225a12fcca": (343, (
        "e71418cf35a6db419ead3652b07e068cfd57e2dd16a8528e5532ee5ec50514b7",
        "53b16860b32c529e3effed2d6e19c82c68b8ddbe1e9a3c671d159a8973942da8",
        "14a9fb21076a6df7357fa8386ffe5e24692892f0b72cae10b864c50fd84918ee",
        "b8973a9e825aeddf9d6b23dd33121f44cb2b1e0ab96c51b8ee96ea50c9c72383",
        "2e931162a9465ca6a53a3f881b9c8e10df5447bda3b3e2bb10584a1220bce424",
    )),
}


def _level(level: str) -> str:
    if level not in LEVELS:
        raise ValidationError("Screen timing level must be A, B, C or D.")
    return level


def _signature(book: Nfl2k5Playbook) -> str:
    digest = hashlib.sha256()
    for play in book.plays:
        if "screen" not in play.name.casefold():
            continue
        name = play.name.encode("utf-8")
        digest.update(struct.pack("<III", play.index, play.flags_or_id, len(name)))
        digest.update(name)
        for assignment in play.assignments:
            digest.update(struct.pack("<I", assignment.descriptor_word))
            for node in book.assignment_chain(assignment).nodes:
                digest.update(bytes.fromhex(node.raw_hex))
    return digest.hexdigest()


def _chains(book: Nfl2k5Playbook, play) -> list[list[codec.Node]]:
    return [[codec.Node.from_bytes(bytes.fromhex(n.raw_hex))
             for n in book.assignment_chain(a).nodes] for a in play.assignments]


def _hold_index(nodes: list[codec.Node]) -> int | None:
    # Start, optional center snap, finite block, release, terminal type-3 block.
    ops = [n.op for n in nodes]
    if ops not in ([1, 0x11, 0x18, 0x11], [1, 2, 0x11, 0x18, 0x11]):
        return None
    hold, release, block = nodes[-3:]
    if (hold.operands[0] not in (0, 1) or hold.operands[1] < 0.09
            or release.operands[0] != 0 or block.operands[0] != 3):
        return None
    return len(nodes) - 3


def _requests(book: Nfl2k5Playbook, level: str) -> tuple[list[dict], list[dict]]:
    requests, rows = [], []
    for play in book.plays:
        if "screen" not in play.name.casefold():
            continue
        chains = _chains(book, play)
        holds = {slot: index for slot in range(1, 6)
                 if (index := _hold_index(chains[slot])) is not None}
        row: dict[str, Any] = {"play_index": play.index, "play": play.name,
                              "release_slots": sorted(holds), "changed_slots": [],
                              "nodes_added": 0}
        rows.append(row)
        if not holds:
            row["reason"] = "No finite hold, release and type-3 block sequence; left unchanged."
            continue
        assignments: list[Any] = [None] * 11
        for slot, chain in enumerate(chains):
            changed = False
            if level in ("A", "D") and slot in holds:
                hold = chain[holds[slot]]
                if hold.operands[1] == 0.5:
                    hold.operands[1] = 0.8
                    changed = True
            if slot == 0:
                for node in chain:
                    if (level in ("B", "D") and node.op == 4
                            and node.operands[0] == 0
                            and abs(node.operands[2] + 10 * codec.YD_CM) < 0.01):
                        node.operands[2] = -7 * codec.YD_CM
                        changed = True
                    if level in ("C", "D") and node.op == 6 and node.operands[5] == 0:
                        node.operands[5] = 0.6
                        changed = True
            if changed:
                assignments[slot] = [(node.op, list(node.operands)) for node in chain]
        row["changed_slots"] = [s for s, chain in enumerate(assignments) if chain is not None]
        row["nodes_added"] = authored_node_cost(assignments)
        if not row["changed_slots"]:
            row["reason"] = "Release grammar present; this level has no matching retail value."
            continue
        row["reason"] = "EXPERIMENTAL / UNWITNESSED"
        requests.append({"asset_id": book.asset_id, "donor_play_index": play.index,
                         "replace_index": play.index, "assignments": assignments})
    return requests, rows


def inspect(payload: bytes, level: str = DEFAULT_LEVEL) -> dict[str, Any]:
    """Status, eligible/skipped play inventory and current capacity; no mutation."""
    level = _level(level)
    try:
        if payload[:RESOURCE_HEADER_SIZE] != struct.pack("<4s7I", b"PLAY", BODY_SIZE, BODY_SIZE, 0, 0, 0, 0, 0):
            raise ValidationError("Expected the retail uncompressed PLAY wrapper.")
        book = parse_playbook_resource(payload)
        identity = hashlib.sha256(book.book_name.encode("utf-8")).hexdigest()
        pin = _RETAIL_PINS.get(identity)
        if pin is None:
            raise ValidationError("Unknown retail PLAY book identity.")
        outer, hashes = pin
        signature = _signature(book)
        expected = hashes[LEVELS.index(level) + 1]
        if signature == expected:
            state = "applied"
        elif signature == hashes[0]:
            state = "retail"
        else:
            raise ValidationError("Mixed, foreign or different-level declared screen assignments.")
        requests, rows = _requests(book, level)
        if state == "applied":
            for row in rows:
                if row["release_slots"]:
                    row["reason"] = "Already at the requested level."
        need = sum(row["nodes_added"] for row in rows) if state == "retail" else 0
        remaining = NODE_CAPACITY - book.node_count
        start = RESOURCE_HEADER_SIZE + NODE_BASE + book.node_count * NODE_SIZE
        capacity_ok = need <= remaining and not any(payload[start:start + need * NODE_SIZE])
        return {"status": state, "level": level, "book": book.book_name,
                "outer_index": outer, "plays": rows, "nodes_added": need,
                "has_effect": hashes[0] != expected,
                "node_count": book.node_count, "remaining_nodes": remaining,
                "capacity_ok": capacity_ok, "experimental": True, "witnessed": False}
    except (ValidationError, ValueError, IndexError, struct.error) as exc:
        return {"status": "foreign", "level": level, "reason": str(exc),
                "experimental": True, "witnessed": False}


def status(payload: bytes, level: str = DEFAULT_LEVEL) -> str:
    return inspect(payload, level)["status"]


def _changes(before: bytes, after: bytes, start: int = 0, end: int | None = None) -> list[dict]:
    """Exact resource-relative byte runs, with both byte values for review."""
    end = len(before) if end is None else end
    rows = []
    cursor = start
    while cursor < end:
        if before[cursor] == after[cursor]:
            cursor += 1
            continue
        first = cursor
        while cursor < end and before[cursor] != after[cursor]:
            cursor += 1
        rows.append({"offset": first, "before": before[first:cursor].hex(),
                     "after": after[first:cursor].hex()})
    return rows


def apply(payload: bytes, level: str = DEFAULT_LEVEL) -> tuple[bytes, dict[str, Any]]:
    """Clone eligible assignments through the existing writer; refuse before mutation."""
    info = inspect(payload, level)
    if info["status"] == "foreign":
        raise ValidationError(f"Screen timing refused: {info['reason']}")
    if not info["capacity_ok"]:
        raise ValidationError("Screen timing refused: insufficient nodes or foreign node-pool padding.")
    before_book = parse_playbook_resource(payload)
    requests, _ = _requests(before_book, level)
    already = info["status"] == "applied"
    compiled = None
    if not already and requests:
        compiled = compile_formation_play_creations(payload, play_requests=requests)
    result = compiled.replacement if compiled else payload
    after_book = parse_playbook_resource(result)
    if status(result, level) != "applied":
        raise ValidationError("Screen timing post-apply signature did not match its pinned level.")
    # Runtime spans only: orphan tails may enlarge unrelated inspector extents.
    touched = {r["donor_play_index"]: r for r in requests} if not already else {}
    for play in before_book.plays:
        after = after_book.plays[play.index]
        if play.flags_or_id != after.flags_or_id or play.name != after.name:
            raise ValidationError("Screen timing changed an unowned play header.")
        for slot, assignment in enumerate(play.assignments):
            if play.index in touched and touched[play.index]["assignments"][slot] is not None:
                continue
            other = after.assignments[slot]
            if (assignment != other or before_book.assignment_chain(assignment).nodes
                    != after_book.assignment_chain(other).nodes):
                raise ValidationError("Screen timing changed an unowned declared assignment.")
    rows = []
    for row in info["plays"]:
        row = dict(row)
        play = after_book.plays[row["play_index"]]
        edits = []
        if not already and row["changed_slots"]:
            for slot in row["changed_slots"]:
                field = RESOURCE_HEADER_SIZE + PLAY_BASE + play.index * PLAY_SIZE + 8 + slot * 8
                edits.extend(_changes(payload, result, field, field + 8))
                assignment = play.assignments[slot]
                start = RESOURCE_HEADER_SIZE + NODE_BASE + assignment.chain_start_index * NODE_SIZE
                edits.extend(_changes(payload, result, start, start + assignment.declared_length * NODE_SIZE))
        row.update(changes=edits, changed_bytes=sum(len(e["after"]) // 2 for e in edits))
        if already:
            row.update(nodes_added=0, changed_slots=[])
        rows.append(row)
    changes = _changes(payload, result)
    receipt = {**info, "status": "applied", "already_applied": already, "plays": rows,
               "changes": changes, "changed_bytes": sum(len(e["after"]) // 2 for e in changes),
               "source_sha256": hashlib.sha256(payload).hexdigest(),
               "replacement_sha256": hashlib.sha256(result).hexdigest(),
               "new_node_count": after_book.node_count,
               "shared_changes": _changes(payload, result, RESOURCE_HEADER_SIZE + 0x40,
                                           RESOURCE_HEADER_SIZE + 0x44)}
    return result, receipt


def _archive_books(archive: Any) -> list[tuple[Any, bytes]]:
    entries = list(archive.entries_with_head(b"PLAY"))
    if len(entries) != 37 or {e.index for e in entries} != set(range(307, 344)):
        raise ValidationError("Screen timing needs all 37 retail PLAY entries (307 through 343).")
    return [(entry, archive.read_entry(entry.index)) for entry in sorted(entries, key=lambda e: e.index)]


def _aggregate(rows: list[dict]) -> str:
    if any(row["status"] == "foreign" or not row.get("capacity_ok", False) for row in rows):
        return "foreign"
    states = {row["status"] for row in rows if row["has_effect"]}
    if len(states) > 1:
        return "foreign"  # a partly installed archive must not be silently completed
    return next(iter(states), "applied")


def inspect_archive(archive: Any, level: str = DEFAULT_LEVEL) -> dict[str, Any]:
    """Read-only status across all books; reject misplaced or partly patched books."""
    _level(level)
    rows = []
    try:
        for entry, raw in _archive_books(archive):
            row = inspect(raw, level)
            if row.get("outer_index") != entry.index:
                row = {**row, "status": "foreign", "reason": "PLAY book is at the wrong archive entry."}
            rows.append(row)
        return {"status": _aggregate(rows), "level": level, "books": rows,
                "experimental": True, "witnessed": False}
    except ValidationError as exc:
        return {"status": "foreign", "level": level, "books": rows, "reason": str(exc)}


def apply_to_archive(archive: Any, level: str = DEFAULT_LEVEL, *, progress=None) -> dict[str, Any]:
    """Preflight all 37 resources, then write exact changed runs with rollback.

    The archive interface is the same as the existing PLAY pack/category passes.
    Attempted short writes are included in rollback; a failed rollback explicitly
    invalidates the output copy. No write is attempted until every resource fits.
    """
    _level(level)
    planned, states = [], []
    for entry, raw in _archive_books(archive):
        result, receipt = apply(raw, level)
        if receipt["outer_index"] != entry.index:
            raise ValidationError("Screen timing refused: PLAY book is at the wrong archive entry.")
        states.append({**receipt, "status": "applied" if receipt["already_applied"] else "retail"})
        planned.append((entry, raw, result, receipt))
        if progress:
            progress(f"Checked screen timing: {receipt['book']} ({receipt['changed_bytes']} bytes)")
    if _aggregate(states) == "foreign":
        raise ValidationError("Screen timing refused: mixed retail and applied books.")
    touched, writes = [], []
    try:
        # Check all preimages again before the first write, then each book at its turn.
        for entry, raw, _result, _receipt in planned:
            if archive.read_entry(entry.index) != raw:
                raise ValidationError("PLAY data changed since screen timing preflight.")
        for entry, raw, result, receipt in planned:
            if archive.read_entry(entry.index) != raw:
                raise ValidationError("PLAY data changed since screen timing preflight.")
            for change in receipt["changes"]:
                address = entry.virtual_offset + change["offset"]
                original, replacement = bytes.fromhex(change["before"]), bytes.fromhex(change["after"])
                touched.append((address, original))
                if archive.write(address, replacement) != len(replacement):
                    raise ValidationError("Screen timing archive short write.")
                writes.append({"outer_index": entry.index, "virtual_offset": address, **change})
            if archive.read_entry(entry.index) != result:
                raise ValidationError("Screen timing archive read-back differs.")
    except Exception as exc:
        failures = []
        for address, original in reversed(touched):
            try:
                if (archive.write(address, original) != len(original)
                        or archive.read(address, len(original)) != original):
                    raise ValidationError("short or mismatched rollback")
            except Exception as rollback:
                failures.append(str(rollback))
        if failures:
            raise ValidationError(f"{exc}; rollback failed: {'; '.join(failures)}; discard this output copy.") from exc
        raise
    return {"schema": "nfl2k5_screen_timing/v1", "status": "applied", "level": level,
            "books": [receipt for _entry, _raw, _result, receipt in planned],
            "changed_bytes": sum(receipt["changed_bytes"] for _e, _r, _n, receipt in planned),
            "writes": writes, "experimental": True, "witnessed": False}


def inspect_image(image, level: str = DEFAULT_LEVEL) -> dict[str, Any]:
    from .nfl2k5_playbook_pack import _outer_image
    with _outer_image().OuterImage(image) as archive:
        return inspect_archive(archive, level)


def apply_to_image(image, level: str = DEFAULT_LEVEL, *, progress=None) -> dict[str, Any]:
    """Write a disc COPY using the existing archive owner; never call on the source."""
    from .nfl2k5_playbook_pack import _outer_image
    with _outer_image().OuterImage(image, writable=True) as archive:
        return apply_to_archive(archive, level, progress=progress)

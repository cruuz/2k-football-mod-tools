#!/usr/bin/env python3
"""Read-only publication gate for the July 13 NFL 2K6 video dossier.

The validator deliberately reads only the named HTML document and the local
evidence files that document pins.  It never renders the HTML, launches an
emulator, opens a retail image, or writes project/game data.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterable, NoReturn
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ROOT_REAL = ROOT.resolve()
DOSSIER_REL = PurePosixPath(
    "docs/updates/NFL_2K6_That_Never_Was_Video_Dossier_2026-07-13.html"
)
DOSSIER = ROOT / Path(*DOSSIER_REL.parts)
EXPECTED_SECTION_COUNT = 26


def fail(message: str) -> NoReturn:
    raise SystemExit(f"FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def normalized(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+([,.;:?!])", r"\1", value)


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    parent: "Node | None" = None
    children: list["Node | str"] = field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").split())


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("__root__", {})
        self.stack = [self.root]

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        node = Node(
            tag.lower(),
            {key.lower(): value or "" for key, value in attrs},
            self.stack[-1],
        )
        self.stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        node = Node(
            tag.lower(),
            {key.lower(): value or "" for key, value in attrs},
            self.stack[-1],
        )
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if len(self.stack) == 1:
            fail(f"unmatched closing HTML tag </{tag}>")
        if self.stack[-1].tag != tag:
            fail(
                f"malformed HTML nesting: expected </{self.stack[-1].tag}>, "
                f"found </{tag}>"
            )
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def close(self) -> None:
        super().close()
        if len(self.stack) != 1:
            fail(
                "unclosed HTML tags: "
                + ", ".join(node.tag for node in self.stack[1:])
            )


def walk(node: Node) -> Iterable[Node]:
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def node_text(node: Node) -> str:
    if node.tag in {"style", "script"}:
        return ""
    return "".join(
        node_text(child) if isinstance(child, Node) else child
        for child in node.children
    )


def ancestors(node: Node) -> Iterable[Node]:
    current: Node | None = node
    while current is not None:
        yield current
        current = current.parent


def has_descendant_class(node: Node, *classes: str) -> bool:
    wanted = set(classes)
    return any(wanted.issubset(candidate.classes) for candidate in walk(node))


def nearest_ancestor(node: Node, tag: str) -> Node | None:
    return next((candidate for candidate in ancestors(node) if candidate.tag == tag), None)


def table_column_header(node: Node, table: Node) -> str:
    cell = next(
        (candidate for candidate in ancestors(node) if candidate.tag in {"th", "td"}),
        None,
    )
    row = nearest_ancestor(node, "tr")
    if cell is None or row is None:
        return ""
    cells = [
        child
        for child in row.children
        if isinstance(child, Node) and child.tag in {"th", "td"}
    ]
    if cell not in cells:
        return ""
    column = cells.index(cell)
    header_row = next((candidate for candidate in walk(table) if candidate.tag == "tr"), None)
    if header_row is None:
        return ""
    headers = [
        child
        for child in header_row.children
        if isinstance(child, Node) and child.tag in {"th", "td"}
    ]
    if column >= len(headers):
        return ""
    return normalized(node_text(headers[column])).casefold()


def direct_cells(row: Node) -> tuple[str, ...]:
    return tuple(
        normalized(node_text(child))
        for child in row.children
        if isinstance(child, Node) and child.tag in {"th", "td"}
    )


def project_file(relative: str) -> Path:
    posix = PurePosixPath(relative)
    require(not posix.is_absolute(), f"absolute pinned path: {relative}")
    require("\\" not in relative, f"non-POSIX pinned path: {relative}")
    candidate = ROOT / Path(*posix.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        fail(f"missing pinned artifact: {relative}")
    try:
        resolved.relative_to(ROOT_REAL)
    except ValueError:
        fail(f"pinned artifact escapes project root: {relative} -> {resolved}")
    require(resolved.is_file(), f"pinned artifact is not a file: {relative}")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


PINNED_VISUALS = {
    "reports/cut_content/apf_nfl_lineage/apf_xex_identity_card.png":
        "247d8431696bb91e3d6b9781a93b252df2378028e5bb16956cc5ca7ba28724f5",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identity_card.png":
        "e48c0bc42de1ae3e91015bd5ee0677a31e235e535bef2b32540b246b3b9aa357",
    "reports/cut_content/apf_nfl_lineage/reference_remnants/apf_reference_nfl_shield.png":
        "52a551831eeeb95e4f8ebbf8ad871304185592948ff2d7fdbd22c3b198aeca60",
    "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants/pregame_conference_textures_nfl_vs_apf.png":
        "08f2ea42969704b3eaf6c150d7882dbabc723efb18538e3358a8080d564a1d6f",
    "reports/cut_content/apf_nfl_lineage/sc_logo_2k5_vs_apf.png":
        "11d6823fa1043481aac311dd85266ee2daae63a0caacd07cda147d1448eab147",
    "reports/cut_content/apf_nfl_lineage/berman_2k5_vs_apf.png":
        "af12e6968c11a7c24ebb1ea8e0ced360877bb9da8a901681b58f2770552aa3b5",
    "reports/cut_content/apf_nfl_lineage/apf_franchise_texture_contact_sheet.png":
        "06be6b667fe11f6e1c0982d2fde672f3ca1283d921095eea545abf341e324e2d",
    "reports/cut_content/apf_nfl_lineage/apf_franchise_runtime_identity_card.png":
        "bf3ca33f2113172d490a3718a55fcc0db4d0c4a3a0144146a081d4426157c5ef",
    "reports/cut_content/apf_nfl_lineage/draft_logo_2k5_vs_apf.png":
        "6c24dd17325c95f7d73d7c30a47a239db365d2a2789f2fe54ddb85198ae0cf3f",
    "reports/assets/nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime/coin-toss-live-diagnostic.png":
        "e9cf835d8693ce5f1a203bbeccfb9fc4f3e6cb2df425520b2016f2c4b07fff75",
    "reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_xenia/control_vs_asymmetric_mask.png":
        "a3f6018beecd7b71e3ace11ced849d0cfe1cf065485df83c38b3a586bc8e552d",
    "reports/assets/nfl2k5_scorebug_xemu_runtime/score_buga-magenta-demo.png":
        "0329e564429e44873fab70ceee5470673e8e92539533869b17498960039ca9e2",
    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/control-s42nd-replay-matched.png":
        "201b4d68bd105f9548892254a62ab4e48162b25b6d548ef78972252698a9ba79",
    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/expanded-replay-zoomout30.png":
        "e67bf8627b0c3c7135d62143669ac6c94e2204973283971c967b0f46fb646f07",
}

PINNED_REPORTS = {
    "reports/cut_content/apf_nfl_lineage/lineage.json":
        "b263564991725d81ecd892727242f6821a2ce29d734eecdf7431a09f2984285b",
    "reports/cut_content/apf_nfl_lineage/manual_remnants.json":
        "9a27535464d4c08c7f580036e1950b31c61fec30797e1704513c7172daa6ddb2",
    "reports/cut_content/apf_nfl_lineage/reference_remnants.json":
        "7a79b04815a356787cd80814818d15a181f0633f6a24d7fe38b362fa63f97312",
    "reports/cut_content/apf_nfl_lineage/wrapup_followup.json":
        "fa05d0ce2048d17512e65b6c13844576ae18813a9056f2a4f122acfd086e34ed",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json":
        "f2e348386dc4c042252f766f5cf4046760ff6723e101ac9ab84b27bee9a33f4d",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime.json":
        "150c77bb0184e19f15920d912e3dd8e820356b7bbb06a67622c971b78abbbbd6",
    "reports/cross_title/cfg_candidates.json":
        "b3a459b87d3f0663719d780ca08a8d7e77835bf024c29e69adefd402f66f8526",
    "reports/assets/playbook_descriptor_lineage.json":
        "3f7f3f3bd27fe12177646eeb01a3b0116673875b01a50ec05ead9fa8962681ef",
    "reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json":
        "33d76b3bbc9d11b52af6cf2861cf2890574a6d5b6820df8972d8419a63459d60",
    "reports/assets/nfl_stadium_upper_deck_source_subset_roundtrip.v1.json":
        "dd9858e01e571a6bfc7fc9577caa1cf218390cb1f19b1436d1bb099805aeb4e0",
}

# These five identities are intentionally ledger-only: the dossier names no
# local retail paths, and this publication validator must not search for them.
RETAIL_IDENTITIES = {
    "APF retail default.xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "APF decompressed PE":
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf",
    "APF retail volume 0A":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "NFL retail default.xbe":
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
    "NFL retail XISO":
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
}

EXPECTED_EMBEDDED_IMAGES = Counter(
    {
        "reports/cut_content/apf_nfl_lineage/apf_xex_identity_card.png": 2,
        "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identity_card.png": 1,
        "reports/cut_content/apf_nfl_lineage/reference_remnants/apf_reference_nfl_shield.png": 1,
        "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants/pregame_conference_textures_nfl_vs_apf.png": 1,
        "reports/cut_content/apf_nfl_lineage/sc_logo_2k5_vs_apf.png": 1,
        "reports/cut_content/apf_nfl_lineage/berman_2k5_vs_apf.png": 1,
        "reports/cut_content/apf_nfl_lineage/apf_franchise_texture_contact_sheet.png": 1,
        "reports/cut_content/apf_nfl_lineage/apf_franchise_runtime_identity_card.png": 1,
        "reports/assets/nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime/coin-toss-live-diagnostic.png": 1,
        "reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_xenia/control_vs_asymmetric_mask.png": 1,
        "reports/assets/nfl2k5_scorebug_xemu_runtime/score_buga-magenta-demo.png": 1,
        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/control-s42nd-replay-matched.png": 1,
        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/expanded-replay-zoomout30.png": 1,
    }
)

REQUIRED_BOUNDARIES = (
    "They do not identify a formal, playable, or submission-stage product titled NFL 2K6.",
    "Branch ancestry does not supply a formal product title.",
    "Execution of every motion and a commercial NFL 2K6 identity remain unproved.",
    "These are decoded archive assets, not screens observed in retail APF.",
    "No complete reachable hidden franchise loop is proved.",
    "This is not a leaked NFL 2K6 build.",
    "FRAMES NOT PIXEL-ALIGNED; NO GPU TRACE",
    "XEMU DIAGNOSTIC — NOT ORIGINAL-HARDWARE CERTIFICATION",
    "No general mesh/audio/franchise/gameplay editor or hardware-certified suite exists yet.",
    "This exact diagnostic is not a general edited-glTF importer or production mesh writer.",
    "“Stage 2” does not mean the games are fully moddable.",
    "“Stage 3” does not mean a decomp or PC port is complete or imminent.",
    "Ghidra pseudocode is not recovered source, and compiled translated functions are not a playable port.",
    "Users will provide their own legally obtained game files.",
    "Pixel equality is not being claimed.",
    "The final completed-catch/drop branch and formula are not located; no single drop-rate constant is proved.",
    "No broad audible replacement witness; player-name routing remains unresolved.",
    "No general edited-glTF importer, arbitrary topology, or public mesh provider.",
    "Experimental executable and mesh capabilities remain hidden and non-dispatchable.",
)

AVOID_PHRASES = (
    "We found NFL 2K6.",
    "APF is NFL 2K6 with the license removed.",
    "All 519 animations run.",
    "We restored franchise mode.",
    "The games are fully moddable.",
    "It works on original hardware.",
    "We have a general model importer.",
    "We decompiled the game.",
    "The PC port is underway/near.",
    "These are leaked NFL 2K6 screenshots.",
    "“First ever” without a bounded historical survey.",
    "Everything is unlocked.",
)

# These patterns reject affirmative variants, not merely the exact examples in
# the red box.  Explicitly styled negative examples and mandatory-boundary
# contexts are exempted below.
FORBIDDEN_AFFIRMATIVE_PATTERNS = {
    "recovered NFL 2K6 product/build": re.compile(
        r"\bwe (?:found|recovered|have) (?:a )?(?:formal |finished |playable )?"
        r"NFL 2K6(?: build| game)?\b",
        re.IGNORECASE,
    ),
    "APF equals NFL 2K6": re.compile(
        r"\b(?:APF(?: 2K8)?|All-Pro Football 2K8) (?:is|was) (?:just )?NFL 2K6\b",
        re.IGNORECASE,
    ),
    "finished build license scrub": re.compile(
        r"\b(?:a finished NFL 2K6|NFL 2K6) was (?:simply|just) stripped\b",
        re.IGNORECASE,
    ),
    "all animations execute": re.compile(
        r"\ball (?:519 )?(?:2K6[- ]tagged )?animations (?:run|execute|work)\b",
        re.IGNORECASE,
    ),
    "franchise restored": re.compile(
        r"\bwe (?:restored|unlocked) (?:the )?franchise(?: mode)?\b",
        re.IGNORECASE,
    ),
    "fully moddable": re.compile(
        r"\b(?:the |both )?games? (?:are|is) fully moddable\b",
        re.IGNORECASE,
    ),
    "original-hardware support": re.compile(
        r"\b(?:it|this|the mod|the suite) works? on original hardware\b",
        re.IGNORECASE,
    ),
    "general model/mesh importer": re.compile(
        r"\bwe (?:have|built|finished) (?:a )?general (?:model|mesh) importer\b",
        re.IGNORECASE,
    ),
    "game decompiled": re.compile(
        r"\bwe (?:have )?(?:fully )?decompiled (?:the |both )?games?\b",
        re.IGNORECASE,
    ),
    "PC port is current/near": re.compile(
        r"\b(?:the )?PC port (?:is )?(?:underway|near|almost|imminent|playable|complete)\b",
        re.IGNORECASE,
    ),
    "leaked screenshots": re.compile(
        r"\b(?:these|those) are (?:leaked|actual) NFL 2K6 screenshots\b",
        re.IGNORECASE,
    ),
    "unbounded first-ever claim": re.compile(r"\bfirst[- ]ever\b", re.IGNORECASE),
    "everything unlocked": re.compile(
        r"\b(?:everything|the game|both games) is unlocked\b", re.IGNORECASE
    ),
    "affirmative leaked/playable build": re.compile(
        r"\bthis is (?:a )?(?:leaked|playable) NFL 2K6 build\b",
        re.IGNORECASE,
    ),
}


def is_negative_context(node: Node, avoid_box: Node) -> bool:
    chain = tuple(ancestors(node))
    if avoid_box in chain:
        return True
    for ancestor in chain:
        classes = ancestor.classes
        if {"callout", "red"}.issubset(classes):
            return True
        if "status-no" in classes or {"badge", "false"}.issubset(classes):
            return True
        if {"evidence", "n"}.issubset(classes):
            return True
        if ancestor.tag == "tr" and (
            has_descendant_class(ancestor, "evidence", "n")
            or has_descendant_class(ancestor, "status-no")
        ):
            return True
        if ancestor.tag == "table":
            header = table_column_header(node, ancestor)
            if header in {"what it does not support", "mandatory boundary"}:
                return True
    return False


def main() -> None:
    require(not sys.argv[1:], "this validator accepts no path overrides or arguments")
    require(DOSSIER.is_file(), f"exact dossier is missing: {DOSSIER_REL}")
    require(not DOSSIER.is_symlink(), f"exact dossier must not be a symlink: {DOSSIER_REL}")
    source = DOSSIER.read_text(encoding="utf-8")
    require(
        source.startswith("<!doctype html>"),
        f"unexpected document type in exact dossier: {DOSSIER_REL}",
    )

    parser = TreeParser()
    parser.feed(source)
    parser.close()
    nodes = tuple(walk(parser.root))

    titles = [normalized(node_text(node)) for node in nodes if node.tag == "title"]
    require(
        titles == ["The NFL 2K6 That Never Was? — Evidence & Video Production Dossier"],
        f"title drift in exact dossier: {titles!r}",
    )
    require(not any(node.tag == "base" for node in nodes), "HTML <base> is forbidden")
    require(not any(node.tag == "script" for node in nodes), "HTML <script> is forbidden")

    sections = [node for node in nodes if node.tag == "section"]
    require(
        len(sections) == EXPECTED_SECTION_COUNT,
        f"section count drift: {len(sections)} != {EXPECTED_SECTION_COUNT}",
    )
    require(
        source.count("</section>") == EXPECTED_SECTION_COUNT,
        "raw closing-section count does not match the structural count",
    )
    require(
        sum("cover" in node.classes for node in sections) == 1,
        "expected exactly one cover section",
    )
    require(
        all("page" in node.classes for node in sections),
        "every dossier section must remain a PDF page",
    )

    image_nodes = [node for node in nodes if node.tag == "img"]
    actual_images: Counter[str] = Counter()
    for image in image_nodes:
        src = image.attrs.get("src", "").strip()
        require(src, "image without a src attribute")
        parsed = urlsplit(src)
        require(
            not parsed.scheme and not parsed.netloc,
            f"non-local image source is forbidden: {src}",
        )
        require(
            not parsed.query and not parsed.fragment,
            f"image source must be an exact local path: {src}",
        )
        require("\\" not in parsed.path, f"non-POSIX image path: {src}")
        image_rel = PurePosixPath(parsed.path)
        require(not image_rel.is_absolute(), f"absolute image path: {src}")
        candidate = DOSSIER.parent / Path(*image_rel.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            fail(f"unresolved local image: {src}")
        try:
            project_relative = resolved.relative_to(ROOT_REAL).as_posix()
        except ValueError:
            fail(f"local image escapes project root: {src} -> {resolved}")
        require(resolved.is_file(), f"local image is not a file: {src}")
        actual_images[project_relative] += 1
    require(
        actual_images == EXPECTED_EMBEDDED_IMAGES,
        f"embedded image set/count drift: {actual_images!r}",
    )

    rows = [direct_cells(node) for node in nodes if node.tag == "tr"]
    all_cells = {cell for row in rows for cell in row}

    for relative, expected in PINNED_VISUALS.items():
        require(
            any(relative in row and expected in row for row in rows),
            f"visual path/hash pair is absent from one dossier row: {relative}",
        )
        actual = sha256_file(project_file(relative))
        require(
            actual == expected,
            f"visual hash drift for {relative}: {actual} != {expected}",
        )

    for relative, expected in PINNED_REPORTS.items():
        basename = PurePosixPath(relative).name
        require(relative in all_cells, f"core report path absent from dossier: {relative}")
        require(
            any(basename in row and expected in row for row in rows),
            f"core report name/hash pair is absent from one dossier row: {relative}",
        )
        actual = sha256_file(project_file(relative))
        require(
            actual == expected,
            f"core report hash drift for {relative}: {actual} != {expected}",
        )

    for label, expected in RETAIL_IDENTITIES.items():
        require(
            any(label in row and expected in row for row in rows),
            f"retail identity/hash pair absent from dossier ledger: {label}",
        )

    expected_full_hashes = set(PINNED_VISUALS.values()) | set(PINNED_REPORTS.values())
    expected_full_hashes |= set(RETAIL_IDENTITIES.values())
    found_full_hashes = {
        match.casefold() for match in re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])", source)
    }
    require(
        found_full_hashes == expected_full_hashes,
        "64-digit dossier hash ledger drift: "
        f"missing={sorted(expected_full_hashes - found_full_hashes)!r}, "
        f"unexpected={sorted(found_full_hashes - expected_full_hashes)!r}",
    )

    visible_text = normalized(node_text(parser.root))
    for phrase in REQUIRED_BOUNDARIES:
        require(phrase in visible_text, f"required claim boundary missing: {phrase!r}")

    avoid_headings = [
        node
        for node in nodes
        if node.tag == "h3" and normalized(node_text(node)) == "Phrases to avoid"
    ]
    require(len(avoid_headings) == 1, "expected exactly one 'Phrases to avoid' heading")
    avoid_heading = avoid_headings[0]
    require(avoid_heading.parent is not None, "orphaned 'Phrases to avoid' heading")
    siblings = avoid_heading.parent.children
    heading_index = siblings.index(avoid_heading)
    following_elements = [
        item for item in siblings[heading_index + 1 :] if isinstance(item, Node)
    ]
    require(following_elements, "missing phrases-to-avoid block")
    avoid_box = following_elements[0]
    require("grid2" in avoid_box.classes, "phrases-to-avoid block lost its grid2 boundary")
    avoid_text = normalized(node_text(avoid_box))
    for phrase in AVOID_PHRASES:
        require(phrase in avoid_text, f"required avoid-list phrase missing: {phrase!r}")

    unsafe_matches: list[str] = []
    block_tags = {"p", "li", "td", "th", "h1", "h2", "h3", "h4", "figcaption"}
    for node in nodes:
        if node.tag not in block_tags or is_negative_context(node, avoid_box):
            continue
        text = normalized(node_text(node))
        if not text:
            continue
        for label, pattern in FORBIDDEN_AFFIRMATIVE_PATTERNS.items():
            match = pattern.search(text)
            if match:
                unsafe_matches.append(f"{label}: {match.group(0)!r} in {text!r}")
    require(
        not unsafe_matches,
        "forbidden affirmative overclaim(s) outside explicit negative context:\n  "
        + "\n  ".join(unsafe_matches),
    )

    print(f"PASS exact dossier: {DOSSIER_REL}")
    print(f"PASS sections: {len(sections)} (1 cover + {len(sections) - 1} body pages)")
    print(
        f"PASS local images: {sum(actual_images.values())} references, "
        f"{len(actual_images)} unique files"
    )
    print(
        f"PASS disk-pinned evidence: {len(PINNED_VISUALS)} visuals + "
        f"{len(PINNED_REPORTS)} reports"
    )
    print(f"PASS retail identity ledger: {len(RETAIL_IDENTITIES)} hashes (ledger-only)")
    print(f"PASS required claim boundaries: {len(REQUIRED_BOUNDARIES)}")
    print(
        f"PASS affirmative-overclaim gate: {len(FORBIDDEN_AFFIRMATIVE_PATTERNS)} "
        "pattern families"
    )
    print("PASS dossier publication gate (read-only)")


if __name__ == "__main__":
    main()

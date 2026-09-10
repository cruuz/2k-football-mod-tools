"""Authored I Pro concept recipes using a pinned stock pass skeleton.

These are real compiler inputs, not claims of witnessed football behaviour.
Landmarks and breaks follow APF's drawing decoder. Five-step footfall timing,
receiver reactions and defensive match rules have not been proved.
"""
from .apf2k8_play_codec import Book, MASTER_SHA256
from .apf2k8_play_designer import empty_plan, sha
from .errors import ValidationError

FORMATION = 0  # I Pro; personnel and slot order are retained.
DONOR = 10     # Ordinary pass header, simple two-segment eligible assignments.
NOTICE = "I Pro landmark recipe; 7-yard QB movement; five-step cadence and gameplay UNWITNESSED."

# slot -> (stem feet, break kind, break distance feet). The 7 in a football
# '7 route' means a corner route, never a seven-yard corner stem.
RECIPES = {
    "Smash": {6: (30, 6, 45), 7: (15, 8, 6), 8: (36, 4, 45), 9: (3, 5, 15)},
    "Levels / Drive": {6: (30, 4, 60), 7: (9, 4, 60), 8: (18, 4, 60), 9: (9, 5, 30)},
    "Dagger": {6: (18, 0, 60), 7: (45, 4, 60), 8: (9, 4, 60), 9: (3, 5, 15)},
    "Curl-Flat": {6: (3, 5, 18), 7: (36, 8, 6), 8: (36, 8, 6), 9: (3, 5, 18)},
    "Mesh": {6: (12, 4, 60), 7: (30, 6, 45), 8: (15, 4, 60), 9: (3, 5, 30)},
}


def concept_request(source: bytes, concept: str, target: int, *, mode: str = "append") -> dict:
    if sha(source) != MASTER_SHA256:
        raise ValidationError("Concept recipes require the pinned APF retail MASTER.")
    if concept not in RECIPES:
        raise ValidationError("Unknown APF concept recipe.")
    book = Book.from_bytes(source)
    if book.formation_name(FORMATION) != "I Pro" or book.play_name(DONOR) != "50 TE/Z Curls":
        raise ValidationError("Concept donor identity changed.")
    if [n.op for n in book.chain(DONOR, 0)] != [1, 3, 4, 6]:
        raise ValidationError("Concept QB skeleton changed.")
    edits = [[0, 2, "y_ft", -21]]
    for slot, (stem, turn, distance) in RECIPES[concept].items():
        route_donor = 20 if slot == 9 else DONOR
        if [n.op for n in book.chain(route_donor, slot)] != [1, 18, 18]:
            raise ValidationError("Concept receiver skeleton changed.")
        edits.extend([[slot, 1, "segment_type", 0], [slot, 1, "distance_ft", stem],
                      [slot, 2, "segment_type", turn], [slot, 2, "distance_ft", distance]])
    return {"mode": mode, "target": target, "donor": DONOR, "name": concept.replace(" / ", " ") + " APF", "copies": [[9, 20]], "nodes": edits}


def concept_plan(source: bytes, concepts=tuple(RECIPES), *, cpu: bool = True) -> dict:
    plan = empty_plan(source)
    start = len(Book.from_bytes(source).plays)
    for i, concept in enumerate(concepts):
        target = start + i
        plan["plays"].append(concept_request(source, concept, target))
        if cpu:
            plan["cpu_calls"].append({"outer": 259, "record": 0, "play": target,
                                      "formation": FORMATION, "donor_record": None})
    return plan

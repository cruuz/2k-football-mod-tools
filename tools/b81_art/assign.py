"""Which cleaned texture each helmet slot gets (Carolina: silver by default, the black helmet on the blue alternate)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C
OUT = C.WORK.parent / 'out' / 'helmets'
REASSIGN = {'04H0': '04A0', '04H2': '04H0', '04A2': '04H0'}     # slot <- cleaned final texture of this slot
def new_tex_path(fam, sel):
    return OUT / f"{fam}_{REASSIGN.get(sel, sel)}.png"

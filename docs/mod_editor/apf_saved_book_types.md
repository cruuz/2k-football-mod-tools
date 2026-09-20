# Saved label book types

Save Assignments can write a label's book type into a separate raw Xbox 360
Roster.ROS. This lets an older roster refer to a clone already installed in a
built game folder. It does not create a clone or change the team's label
assignment. This is an explicit experimental action, off in every preset.

1. Keep the original roster and the game folder that already contains the clone.
2. Open Playbooks and Plays, then Save Assignments. Choose the raw Roster.ROS.
3. If team assignments are staged, write those first and load that new save.
4. Choose **Write a label's book type**, select the saved label, then select
   the built game's 0A file and a book type on the same side.
5. Choose a new output filename. Review the old and new types, affected team
   slots, game folder and destination. Confirm explicitly to write.

The action changes the label's four-byte relative type pointer. Like the disc
clone writer, it reuses a name already in the roster's string pool. Every team
using that label is affected; all 40 teams' assignment pointers stay unchanged.
Label display names and existing strings also stay unchanged. Types absent
from this save's string pool are refused. Choose a clone named after an existing
saved label or team. Allocating new save strings is unsupported.

The installed resource is looked up as CRC32 of uppercase ASCII
`<type>-spb.iff`, decoded, and checked against its SPLB header name. Strict
roster readers check the source and output. The new output and
`<output>.label-type.json` receipt must both be new files. The service rereads
them and compares every byte against the permitted edit. Signed containers,
PS3 payloads and season saves are not inputs to this action.

In-game status is **UNWITNESSED**. To witness it:

1. Load the new raw roster using the matching built game. If the platform needs
   a signed container, reinject and rehash/resign with the owner's save manager.
2. Select an affected team and inspect a distinctive formation or play that
   exists in the intended clone. Also inspect an unaffected team.
3. Save, exit and reload the roster; inspect that same team and distinctive play
   again. Record game build, title update, team slot, clone name and save hash.
4. Record any USER/UA/UB or mode override that replaces the saved assignment.

Offline verification establishes serialization and resource identity. A player
load is required before claiming that the save selects or retains the clone
in game. If the required clone is not already installed, build it first.

"""Complete allocator owner union shared by both XBE safety gates."""
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_momentum as momentum
from mod_editor.core import nfl2k5_defensive_try as defensive_try
from mod_editor.core import nfl2k5_zone_drop as zone_drop
from mod_editor.core import nfl2k5_music_metadata as music
from mod_editor.core import nfl2k5_music_policy as policy

REQUESTS = kickoff.REQUESTS + runtime.REQUESTS + momentum.REQUESTS + defensive_try.REQUESTS + zone_drop.REQUESTS
SONGS = [dict(title=f"Tone {i+1:03}", artist="Synthetic", frames=256) for i in range(200)]


def compose(payload, *, reverse=False):
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    payload, _ = scene.apply_xbe(payload)
    payload, policy_receipt = policy.apply(payload, music_unlock=True, music_userlist=True)
    payload, _ = space.apply(payload, REQUESTS)
    owners = ((defensive_try, {}), (kickoff, {}), (runtime, {}),
              (momentum, dict(momentum=100, momentum_contact=True)), (zone_drop, {}),
              (music, dict(song_records=SONGS)))
    order = tuple(reversed(owners)) if reverse else owners
    for module, kwargs in order:
        payload, _ = module.apply(payload, **kwargs)
    for module, kwargs in owners:
        if module.status(payload) != "applied" or module.apply(payload, **kwargs)[0] != payload:
            raise AssertionError(f"{module.OWNER} failed complete composition/replay")
    if space.apply(payload, REQUESTS)[0] != payload:
        raise AssertionError("allocator replay changed the complete owner union")
    return payload, policy_receipt

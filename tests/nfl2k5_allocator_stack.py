"""Complete allocator owner union shared by both XBE safety gates."""
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_momentum as momentum
from mod_editor.core import nfl2k5_defensive_try as defensive_try
from mod_editor.core import nfl2k5_zone_drop as zone_drop
from mod_editor.core import nfl2k5_music_metadata as music
from mod_editor.core import nfl2k5_music_policy as policy
from mod_editor.core import nfl2k5_roster_storage as roster_storage
from mod_editor.core import nfl2k5_coverage_slider as coverage
from mod_editor.core import nfl2k5_scramble_tuning as scramble
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core import nfl2k5_practice_squad_screen as practice_screen
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_qb_spy_runtime as qb_spy

LEGACY_REQUESTS = (kickoff.REQUESTS + runtime.REQUESTS + momentum.REQUESTS
                   + defensive_try.REQUESTS + zone_drop.REQUESTS)
REQUESTS = (LEGACY_REQUESTS + roster_storage.REQUESTS + coverage.REQUESTS + scramble.REQUESTS
            + playlist.REQUESTS + practice_screen.REQUESTS + abilities.REQUESTS + qb_spy.REQUESTS)
SONGS = [dict(title=f"Tone {i+1:03}", artist="Synthetic", frames=256) for i in range(200)]


def compose(payload, *, reverse=False, scaleout=False, extra_requests=()):
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    from mod_editor.core import nfl2k5_practice_squad as ps, nfl2k5_franchise_practice as fp
    from mod_editor.core import nfl2k5_practice_reserves as pr
    payload, _ = ps.apply(payload)
    payload, _ = fp.apply(payload)
    payload, _ = pr.apply(payload)
    payload, _ = scene.apply_xbe(payload)
    payload, policy_receipt = policy.apply(payload, music_unlock=True, music_userlist=True)
    payload, _ = space.apply(payload, REQUESTS + tuple(extra_requests), scaleout=scaleout)
    owners = ((defensive_try, {}), (kickoff, {}), (runtime, {}),
              (momentum, dict(momentum=100, momentum_contact=True)), (zone_drop, {}),
              (music, dict(song_records=SONGS)), (roster_storage, {}), (coverage, {}), (scramble, {}), (playlist, {}),
              (practice_screen, {}), (abilities, dict(abilities_off_week=7)), (qb_spy, {}))
    order = tuple(reversed(owners)) if reverse else owners
    for module, kwargs in order:
        payload, _ = module.apply(payload, **kwargs)
    for module, kwargs in owners:
        if module.status(payload) != "applied" or module.apply(payload, **kwargs)[0] != payload:
            raise AssertionError(f"{module.OWNER} failed complete composition/replay")
    if space.apply(payload, REQUESTS + tuple(extra_requests), scaleout=scaleout)[0] != payload:
        raise AssertionError("allocator replay changed the complete owner union")
    return payload, policy_receipt

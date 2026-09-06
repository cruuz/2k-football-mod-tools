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
from mod_editor.core import nfl2k5_calendar_engine as calendar

LEGACY_REQUESTS = (kickoff.REQUESTS + runtime.REQUESTS + momentum.REQUESTS
                   + defensive_try.REQUESTS[:2] + zone_drop.REQUESTS)
REQUESTS = (LEGACY_REQUESTS + roster_storage.REQUESTS + coverage.REQUESTS + scramble.REQUESTS
            + playlist.REQUESTS + practice_screen.REQUESTS + abilities.REQUESTS + qb_spy.REQUESTS + calendar.REQUESTS
            + defensive_try.REQUESTS[2:])
SONGS = [dict(title=f"Tone {i+1:03}", artist="Synthetic", frames=256) for i in range(200)]


def compose(payload, *, reverse=False, scaleout=False, extra_requests=()):
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    from mod_editor.core import nfl2k5_practice_squad as ps, nfl2k5_franchise_practice as fp
    from mod_editor.core import nfl2k5_practice_reserves as pr
    from mod_editor.core import nfl2k5_widescreen as wide
    # Both gate seeds already contain widescreen. In reverse mode defer its
    # complete install until after every allocator owner, so order equivalence
    # exercises the new marker/sky/culling sites as well as the grown owners.
    deferred_wide = wide.applied_aspect(payload) if reverse else None
    if deferred_wide:
        from mod_editor.core.nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
        sections = _sections(payload)
        buf = bytearray(payload)
        touched = set()
        for _label, off, retail, _patched in wide._sites(payload, deferred_wide):
            buf[off:off + len(retail)] = retail
            if off >= wide._header_size(payload):
                touched.add(_section_for_offset(sections, off).index)
        for section in sections:
            if section.index in touched:
                buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
        payload = bytes(buf)
        if wide.status(payload) != "retail":
            raise AssertionError("reverse gate could not prepare complete retail widescreen sites")
    payload, _ = ps.apply(payload)
    payload, _ = fp.apply(payload)
    payload, _ = pr.apply(payload)
    payload, _ = scene.apply_xbe(payload)
    payload, policy_receipt = policy.apply(payload, music_unlock=True, music_userlist=True)
    payload, _ = space.apply(payload, REQUESTS + tuple(extra_requests), scaleout=scaleout)
    # One apply/status transaction owns both try rules and the stat extension.
    owners = ((defensive_try, {}), (kickoff, {}), (runtime, {}),
              (momentum, dict(momentum=100, momentum_contact=True, momentum_collisions=True, momentum_collision_level=100)), (zone_drop, {}),
              (music, dict(song_records=SONGS)), (roster_storage, {}), (coverage, {}), (scramble, {}), (playlist, {}),
              (practice_screen, {}), (abilities, dict(abilities_off_week=7)), (qb_spy, {}), (calendar, {}))
    order = tuple(reversed(owners)) if reverse else owners
    for module, kwargs in order:
        payload, _ = module.apply(payload, **kwargs)
    if deferred_wide:
        payload, _ = wide.apply(payload, deferred_wide)
    for module, kwargs in owners:
        if module.status(payload) != "applied" or module.apply(payload, **kwargs)[0] != payload:
            raise AssertionError(f"{module.OWNER} failed complete composition/replay")
    if space.apply(payload, REQUESTS + tuple(extra_requests), scaleout=scaleout)[0] != payload:
        raise AssertionError("allocator replay changed the complete owner union")
    return payload, policy_receipt

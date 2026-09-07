"""Complete allocator owner union shared by both XBE safety gates."""
from mod_editor.core import nfl2k5_camera as camera
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
from mod_editor.core import nfl2k5_read_option_runtime as read_option
from mod_editor.core import nfl2k5_franchise_2026 as franchise_2026
from mod_editor.core import nfl2k5_senior_bowl as senior_bowl
from mod_editor.core import nfl2k5_animation_xbe as animation_xbe
from mod_editor.core import nfl2k5_guardian_overlay as guardian
from mod_editor.core import nfl2k5_my_career as my_career
from mod_editor.core import nfl2k5_crib_reclaim as crib_reclaim
from mod_editor.core import nfl2k5_screen_hooks as screen_hooks
from mod_editor.core import nfl2k5_roster_arena_growth as arena_growth


LEGACY_REQUESTS = (kickoff.REQUESTS + runtime.REQUESTS + momentum.REQUESTS
                   + defensive_try.REQUESTS[:2] + zone_drop.REQUESTS)
# Read option v2 grows the existing owner; its live REQUESTS include RW/RO.
# Both installation orders use this same union and require rebuild from base.
REQUESTS = (camera.REQUESTS + LEGACY_REQUESTS + roster_storage.REQUESTS + coverage.REQUESTS + scramble.REQUESTS
            + playlist.REQUESTS + practice_screen.REQUESTS + abilities.REQUESTS + qb_spy.REQUESTS + calendar.REQUESTS
            + defensive_try.REQUESTS[2:] + read_option.REQUESTS + franchise_2026.REQUESTS + senior_bowl.REQUESTS + animation_xbe.REQUESTS + guardian.REQUESTS + my_career.REQUESTS + screen_hooks.REQUESTS + arena_growth.REQUESTS)
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
    owners = ((camera, {}), (defensive_try, {}), (kickoff, {}), (runtime, {}),
              (momentum, dict(momentum=100, momentum_contact=True, momentum_collisions=True, momentum_collision_level=100)), (zone_drop, {}),
              (music, dict(song_records=SONGS)), (roster_storage, {}), (coverage, {}), (scramble, {}), (playlist, {}),
              (practice_screen, {}), (abilities, dict(abilities_off_week=7)), (qb_spy, {}), (calendar, {}), (read_option, {}), (franchise_2026, {}), (senior_bowl, {}), (animation_xbe, {}), (guardian, {}),
              (my_career, {}), (crib_reclaim, {}),
              (screen_hooks, {}),
              (arena_growth, dict(created_teams_extra=2)))
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


def manifest_for_allocated_union(manifest, retail, allocated):
    """Test-only relocation of proved named children to this request union.

    The protected release manifest records a different union. Keep every retail
    reservation and every parent page. Move a grown child span only if it lies
    wholly within its recorded owner/kind allocation, whose size/alignment must
    match the actual sealed directory. Unknown or changed ownership refuses.
    This is not a regenerated disc manifest and is never written to the product.
    """
    from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest, XbeImage
    old = manifest.document["allocator_layout"]["allocations"]
    layout = space.layout(allocated)
    current = {(a["owner"], a["kind"]): a for a in layout["allocations"]}
    spans = []
    for span in manifest.document["spans"]:
        start, end = int(span["start"], 0), int(span["end"], 0)
        if start < space.CODE_VA or span["owner"] == space.OWNER:
            spans.append(span)
            continue
        matches = [a for a in old if a["owner"] == span["owner"] and
                   a["va"] <= start < end <= a["va"] + a["size"]]
        if len(matches) != 1:
            raise AssertionError("manifest contains an unrecognized grown owner span")
        before = matches[0]
        after = current[(before["owner"], before["kind"])]
        if (before["size"], before["align"]) != (after["size"], after["align"]):
            raise AssertionError("manifest child size/alignment changed")
        delta = after["va"] - before["va"]
        spans.append({**span, "start": hex(start + delta), "end": hex(end + delta)})
    spans += space.reservations(allocated)
    document = {**manifest.document, "spans": spans, "allocator_layout": layout,
                "model": "Test-only named-allocation projection; retail reservations unchanged"}
    return ReservationManifest(document, XbeImage(retail))

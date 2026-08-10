"""The update notice, and the three ways it must not misbehave.

It is the only part of these editors that talks to the internet, so the tests
care less about the happy path than about what happens when things go wrong: a
failed check must be silence, not an error; a dismissal must apply to one
version rather than all future ones; and nothing may be downloaded or installed
on the user's behalf.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import update_check  # noqa: E402
from mod_editor.gui import update_ui  # noqa: E402


class _Response:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._payload if size < 0 else self._payload[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _release(tag: str, *, draft: bool = False, prerelease: bool = True) -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "name": f"{tag} notes",
        "html_url": (
            f"https://github.com/cruuz/2k-football-mod-tools/releases/tag/{tag}"
        ),
    }


def _serve(releases: list[dict]):
    payload = json.dumps(releases).encode("utf-8")
    return mock.patch.object(
        update_check.urllib.request, "urlopen",
        return_value=_Response(payload),
    )


class EndpointTests(unittest.TestCase):
    def test_it_asks_for_the_release_list_not_the_latest_release(self) -> None:
        """Every beta here is a pre-release, and /releases/latest skips those.

        Measured against the real repository: /releases/latest answers 404 while
        /releases returns the betas, so using the wrong endpoint means the check
        silently never fires.
        """

        self.assertIn("/releases", update_check.RELEASES_API)
        self.assertNotIn("/releases/latest", update_check.RELEASES_API)


class ComparisonTests(unittest.TestCase):
    def test_a_newer_tag_is_offered(self) -> None:
        with _serve([_release("beta-23")]):
            status = update_check.check("beta-22")
        self.assertTrue(status.available)
        self.assertEqual(status.latest_tag, "beta-23")
        self.assertIn("beta-23", status.headline)

    def test_the_same_tag_is_not_offered(self) -> None:
        with _serve([_release("beta-22")]):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)
        self.assertIn("up to date", status.headline)

    def test_the_shipped_build_does_not_offer_itself(self) -> None:
        tag = update_check.BUILD_RELEASE_TAG
        with _serve([_release(tag, prerelease=False)]):
            status = update_check.check()
        self.assertFalse(status.available)
        self.assertEqual(status.current_tag, tag)
        self.assertEqual(status.latest_tag, tag)

    def test_an_older_published_release_is_never_offered_as_an_update(self) -> None:
        """A re-published older tag must not tell people to move backwards."""

        with _serve([_release("beta-29"), _release("beta-32")]):
            status = update_check.check("beta-32")
        self.assertFalse(status.available)
        self.assertEqual(status.latest_tag, "beta-32")
        self.assertIn("up to date", status.headline)

    def test_the_highest_beta_wins_over_github_ordering(self) -> None:
        # GitHub lists by creation date, so refreshing an old release can put
        # it first. The highest beta number is still the newest release.
        with _serve([_release("beta-29"), _release("beta-30")]):
            status = update_check.check("beta-29")
        self.assertTrue(status.available)
        self.assertEqual(status.latest_tag, "beta-30")

    def test_an_unrecognised_tag_scheme_still_announces_a_change(self) -> None:
        with _serve([_release("2026.1")]):
            status = update_check.check("beta-32")
        self.assertTrue(status.available)
        self.assertEqual(status.latest_tag, "2026.1")

    def test_the_newest_entry_wins_and_drafts_are_skipped(self) -> None:
        with _serve([
            _release("beta-99", draft=True),
            _release("beta-23"),
            _release("beta-22"),
        ]):
            status = update_check.check("beta-22")
        self.assertEqual(status.latest_tag, "beta-23")

    def test_pre_releases_are_kept(self) -> None:
        with _serve([_release("beta-23", prerelease=True)]):
            status = update_check.check("beta-22")
        self.assertTrue(status.available)


class FailureIsSilenceTests(unittest.TestCase):
    """A broken check must never become the user's problem."""

    def test_a_network_error_reports_no_news(self) -> None:
        with mock.patch.object(
            update_check.urllib.request, "urlopen",
            side_effect=OSError("no route to host"),
        ):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)
        self.assertFalse(status.checked)

    def test_malformed_json_reports_no_news(self) -> None:
        with mock.patch.object(
            update_check.urllib.request, "urlopen",
            return_value=_Response(b"<html>rate limited</html>"),
        ):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)

    def test_an_empty_release_list_reports_no_news(self) -> None:
        with _serve([]):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)
        self.assertIn("No published releases", status.detail)

    def test_an_oversized_response_is_refused(self) -> None:
        payload = b"x" * (update_check.MAX_RESPONSE_BYTES + 10)
        with mock.patch.object(
            update_check.urllib.request, "urlopen",
            return_value=_Response(payload),
        ):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)

    def test_a_nonsense_tag_is_refused(self) -> None:
        with _serve([_release("../../etc/passwd")]):
            status = update_check.check("beta-22")
        self.assertFalse(status.available)

    def test_being_switched_off_makes_no_request_at_all(self) -> None:
        with mock.patch.object(
            update_check.urllib.request, "urlopen",
        ) as opened:
            status = update_check.check("beta-22", enabled=False)
        opened.assert_not_called()
        self.assertFalse(status.available)
        self.assertIn("turned off", status.headline)

    def test_finished_worker_is_quiet_when_qt_has_already_deleted_its_signal(self) -> None:
        task = update_ui._CheckTask("beta-22")
        deleted_signal = mock.Mock()
        deleted_signal.emit.side_effect = RuntimeError(
            "wrapped C/C++ object of type _Signals has been deleted"
        )
        task.signals = SimpleNamespace(done=deleted_signal)
        with mock.patch.object(
            update_check,
            "check",
            return_value=update_check.UpdateStatus(
                available=False,
                current_tag="beta-22",
                detail="done",
            ),
        ):
            task.run()
        deleted_signal.emit.assert_called_once()


class LinkSafetyTests(unittest.TestCase):
    def test_an_offsite_link_is_replaced_with_the_releases_page(self) -> None:
        """The response decides what to open, so it does not get free rein."""

        release = _release("beta-23")
        release["html_url"] = "https://example.invalid/not-us"
        with _serve([release]):
            status = update_check.check("beta-22")
        self.assertEqual(status.url, update_check.RELEASES_PAGE)

    def test_a_repository_link_is_kept(self) -> None:
        with _serve([_release("beta-23")]):
            status = update_check.check("beta-22")
        self.assertTrue(
            status.url.startswith(
                "https://github.com/cruuz/2k-football-mod-tools/"
            )
        )


class BuildTagTests(unittest.TestCase):
    def test_the_build_tag_looks_like_a_release_tag(self) -> None:
        self.assertTrue(update_check._TAG.match(update_check.BUILD_RELEASE_TAG))

    def test_the_build_tag_matches_beta_32(self) -> None:
        self.assertEqual(update_check.BUILD_RELEASE_TAG, "beta-32")


if __name__ == "__main__":
    unittest.main()

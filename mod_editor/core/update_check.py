"""Tell the user when a newer build exists.

Modders were running old builds without knowing newer ones had shipped, and the
only way to find out was to go and look. This checks once and says so.

Three rules it does not break:

* It never downloads or installs anything. It reports a version and a link.
* It never blocks the app. Callers run it on a worker; every failure -- offline,
  rate limited, garbage response -- returns "no news" rather than an error the
  user has to dismiss.
* It is disclosed and can be turned off. The check contacts GitHub, which means
  an outbound request the user did not personally type, so the setting is
  visible in the UI and honoured here.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.request

# The list endpoint, not /releases/latest. This project ships betas, GitHub
# marks those pre-releases, and /releases/latest excludes pre-releases outright
# -- it answers 404 here even though releases exist. The list returns newest
# first and includes them.
RELEASES_API = (
    "https://api.github.com/repos/cruuz/2k-football-mod-tools/releases?per_page=10"
)
RELEASES_PAGE = "https://github.com/cruuz/2k-football-mod-tools/releases"

#: The release this build was cut from. Packaging updates it when a release is
#: tagged; the check compares it with the newest published tag, which works
#: across the two products' different version schemes without parsing either.
BUILD_RELEASE_TAG = "beta-37"

DEFAULT_TIMEOUT_SECONDS = 6.0
MAX_RESPONSE_BYTES = 1024 * 1024
_TAG = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
#: Every release this project has ever published is ``beta-<n>``. Reading that
#: number lets the check refuse to advertise a *backwards* move.
_BETA = re.compile(r"^beta-(\d{1,6})$")


def _beta_number(tag: str) -> int | None:
    match = _BETA.match(tag.strip())
    return int(match.group(1)) if match else None


def _is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is genuinely ahead of the running build.

    Plain inequality was enough while the newest release was always the highest
    beta, and wrong the moment it was not: a re-published older tag, or a build
    running before its own release is public, would both have told the user to
    "update" to something behind them. When both tags are betas the numbers
    decide; anything unrecognised falls back to "different means newer" so an
    unforeseen tag scheme still gets announced rather than silently swallowed.
    """

    if latest == current:
        return False
    latest_number = _beta_number(latest)
    current_number = _beta_number(current)
    if latest_number is not None and current_number is not None:
        return latest_number > current_number
    return True


@dataclass(frozen=True)
class UpdateStatus:
    """What to show. ``available`` false means show nothing."""

    available: bool
    current_tag: str
    latest_tag: str = ""
    url: str = RELEASES_PAGE
    title: str = ""
    checked: bool = False
    detail: str = ""

    @property
    def headline(self) -> str:
        if not self.checked:
            return self.detail or "Could not check for updates."
        if not self.available:
            return f"You are up to date ({self.current_tag})."
        return f"Update available: {self.latest_tag}"


def _read(url: str, timeout: float) -> list | None:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub rejects requests without one, and naming the tool is more
            # honest than pretending to be a browser.
            "User-Agent": "2k-football-mod-tools-update-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return None
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    if len(payload) > MAX_RESPONSE_BYTES:
        return None
    try:
        document = json.loads(payload.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, list) else None


def check(
    current_tag: str = BUILD_RELEASE_TAG,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    enabled: bool = True,
) -> UpdateStatus:
    """Ask GitHub for the newest release. Never raises."""

    if not enabled:
        return UpdateStatus(
            available=False, current_tag=current_tag,
            detail="Update checks are turned off.",
        )

    releases = _read(RELEASES_API, timeout)
    if releases is None:
        return UpdateStatus(
            available=False, current_tag=current_tag,
            detail="No connection, or GitHub did not answer.",
        )

    # Drafts are not published to anyone, so they are skipped; pre-releases are
    # kept, because every beta this project ships is one.
    published = [
        item for item in releases
        if isinstance(item, dict) and not item.get("draft")
    ]
    # GitHub orders this list by creation date, which is only the same as
    # "highest release" until an older tag is re-published. Prefer the highest
    # beta number when the tags say so, and keep GitHub's own order otherwise.
    document = next(iter(published), None)
    numbered = [
        (number, item)
        for item in published
        for number in (_beta_number(str(item.get("tag_name") or "")),)
        if number is not None
    ]
    if numbered:
        document = max(numbered, key=lambda row: row[0])[1]
    if document is None:
        return UpdateStatus(
            available=False, current_tag=current_tag,
            detail="No published releases were found.",
        )

    latest = document.get("tag_name")
    if not isinstance(latest, str) or not _TAG.match(latest):
        return UpdateStatus(
            available=False, current_tag=current_tag,
            detail="GitHub returned an unexpected release.",
        )

    url = document.get("html_url")
    if not isinstance(url, str) or not url.startswith(
        "https://github.com/cruuz/2k-football-mod-tools/"
    ):
        url = RELEASES_PAGE

    title = document.get("name")
    if not isinstance(title, str):
        title = ""

    return UpdateStatus(
        available=_is_newer(latest, current_tag),
        current_tag=current_tag,
        latest_tag=latest,
        url=url,
        title=title.strip()[:200],
        checked=True,
    )

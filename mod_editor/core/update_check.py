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
#: tagged; the check is "does the newest tag differ from mine", which works
#: across the two products' different version schemes without parsing either.
BUILD_RELEASE_TAG = "beta-30"

DEFAULT_TIMEOUT_SECONDS = 6.0
MAX_RESPONSE_BYTES = 1024 * 1024
_TAG = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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

    # Newest first. Drafts are not published to anyone, so they are skipped;
    # pre-releases are kept, because every beta this project ships is one.
    document = next(
        (
            item for item in releases
            if isinstance(item, dict) and not item.get("draft")
        ),
        None,
    )
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
        available=latest != current_tag,
        current_tag=current_tag,
        latest_tag=latest,
        url=url,
        title=title.strip()[:200],
        checked=True,
    )

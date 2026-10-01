"""Probe filesystem fixtures without relaxing native Windows assertions."""
import ctypes
import os


def _under_wine():
    return os.name == "nt" and hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")


def directory_symlink(test, link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        test.skipTest(f"Directory symlink creation unavailable for this account/filesystem: {exc}")
    # Wine can report success without creating a link. Do not skip a native
    # Windows regression: successful creation there must produce a usable link.
    usable = link.is_symlink() and link.is_dir()
    if not usable and _under_wine():
        test.skipTest("Wine directory symlink creation returned success without a usable symbolic link")
    test.assertTrue(usable, "Directory symlink creation must produce a usable symbolic link")


def hardlink(test, link, target):
    try:
        os.link(target, link)
    except OSError as exc:
        test.skipTest(f"Hardlink creation unavailable for this filesystem: {exc}")
    same = os.path.samefile(target, link)
    if not same and _under_wine():
        test.skipTest("Wine does not expose shared file identity for this hardlink fixture")
    test.assertTrue(same, "Hardlinks must expose shared file identity")

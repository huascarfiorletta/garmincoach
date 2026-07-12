import getpass
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from setuptools import setup

APP_VERSION = datetime.now().strftime("%y%m%d%H%M%S")

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'garmincoach.icns',
    'packages': ['wx', 'requests', 'keyring', 'garminconnect'],
    'plist': {
        'CFBundleName': 'GarminCoach',
        'CFBundleDisplayName': 'Garmin Coach',
        'CFBundleGetInfoString': "Garmin Coach Assistant",
        'CFBundleIdentifier': "com.garmincoach.app",
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'NSHumanReadableCopyright': u"Copyright © 2024, All Rights Reserved"
    }
}


# ---------------------------------------------------------------------------
# python setup.py icon       -> converts icon.png into garmincoach.icns (run
#                                this once, or whenever you update icon.png,
#                                before building)
# python setup.py py2app     -> builds dist/Garmin Coach.app, using
#                                garmincoach.icns as the app icon (via
#                                OPTIONS['iconfile']), versioned as
#                                VERSION_CODE (today's date, YYMMDD)
# python setup.py publish    -> zips it and publishes it as the single asset
#                                on a reused GitHub release tagged "latest",
#                                overwriting the previous build. No gh CLI,
#                                no git history bloat.
# ---------------------------------------------------------------------------

ICON_PNG = "icon.png"
ICON_ICNS = "garmincoach.icns"
ICON_SIZES = [16, 32, 128, 256, 512]  # standard macOS iconset sizes


def build_icon():
    """
    Convert icon.png into a proper macOS .icns file using the built-in
    'sips' and 'iconutil' command-line tools -- no extra dependencies.
    Generates the full retina iconset (1x and 2x for each size) that
    macOS expects.
    """
    src = Path(ICON_PNG)
    if not src.exists():
        raise FileNotFoundError(
            f"{ICON_PNG} not found next to setup.py -- add your icon there first."
        )

    iconset_dir = Path("icon.iconset")
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir()

    for size in ICON_SIZES:
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(src),
             "--out", str(iconset_dir / f"icon_{size}x{size}.png")],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["sips", "-z", str(size * 2), str(size * 2), str(src),
             "--out", str(iconset_dir / f"icon_{size}x{size}@2x.png")],
            check=True, capture_output=True,
        )

    subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", ICON_ICNS], check=True)
    shutil.rmtree(iconset_dir)
    print(f"Created {ICON_ICNS} from {ICON_PNG}")

GITHUB_KEYRING_SERVICE = "GarminCoachGitHub"
RELEASE_TAG = "latest"
API_ROOT = "https://api.github.com"


def _get_github_token():
    """
    Look up a GitHub personal access token from the system keychain.
    If not found, prompt for it once and cache it -- same pattern as the
    Garmin credentials in garmin_manager.py.

    Create one at https://github.com/settings/tokens with either:
      - classic token, 'repo' scope, or
      - fine-grained token, 'Contents: Read and write' on this repo
    """
    import keyring
    token = keyring.get_password(GITHUB_KEYRING_SERVICE, "token")
    if not token:
        token = getpass.getpass("GitHub personal access token: ").strip()
        keyring.set_password(GITHUB_KEYRING_SERVICE, "token", token)
    return token


def _get_repo_slug():
    """Derive 'owner/repo' from the git 'origin' remote (SSH or HTTPS)."""
    url = subprocess.check_output(
        ["git", "config", "--get", "remote.origin.url"], text=True
    ).strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@"):
        _, path = url.split(":", 1)
    else:
        path = url.split("github.com/", 1)[1]
    return path


def _find_app_bundle() -> Path:
    """Auto-detect the built .app in dist/ so no name needs to be hardcoded."""
    candidates = list(Path("dist").glob("*.app"))
    if not candidates:
        raise FileNotFoundError(
            "No .app bundle found in dist/ -- build it first with "
            "'python setup.py py2app'"
        )
    if len(candidates) > 1:
        raise RuntimeError(f"Multiple .app bundles found in dist/: {candidates}")
    return candidates[0]


def _zip_app_bundle(app_bundle: Path) -> Path:
    """Zip the .app with 'ditto', which preserves macOS-specific metadata
    (resource forks, extended attributes) better than Python's zipfile."""
    zip_path = app_bundle.with_suffix(".zip")
    zip_path.unlink(missing_ok=True)
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
         str(app_bundle), str(zip_path)],
        check=True,
    )
    return zip_path


def _check(resp):
    """raise_for_status(), but print GitHub's actual error body first.
    A bare raise_for_status() only shows the generic reason phrase (e.g.
    '422 Unprocessable Entity') and hides the actually useful part --
    GitHub's JSON error body (e.g. {"errors": [{"code": "already_exists"}]})."""
    if not resp.ok:
        print(resp.status_code)
        try:
            print("GitHub API error response:", resp.json())
        except ValueError:
            print("GitHub API error response:", resp.text)
        resp.raise_for_status()


def _get_or_create_release(session, repo_slug):
    resp = session.get(f"{API_ROOT}/repos/{repo_slug}/releases/tags/{RELEASE_TAG}")
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        resp = session.post(
            f"{API_ROOT}/repos/{repo_slug}/releases",
            json={
                "tag_name": RELEASE_TAG,
                "name": "Latest build",
                "body": "Automatically updated latest build. Not versioned -- always overwritten.",
                "prerelease": True,
            },
        )
    _check(resp)
    return resp.json()


def _delete_existing_asset(session, repo_slug, release_id, filename):
    """Re-fetches the release fresh (rather than trusting a possibly-stale
    assets list) and deletes any existing asset with this filename. This
    guards against stray assets left behind by a previous interrupted
    upload, which otherwise cause a 422 'already_exists' on re-upload."""
    resp = session.get(f"{API_ROOT}/repos/{repo_slug}/releases/{release_id}")
    _check(resp)

    assets = resp.json().get("assets", [])
    print(f"Found {len(assets)} assets")


    for asset in assets:
        print(asset["id"], repr(asset["name"]), asset.get("state"))
        if asset["name"] == filename:
            del_resp = session.delete(
                f"{API_ROOT}/repos/{repo_slug}/releases/assets/{asset['id']}"
            )
            print(del_resp.status_code, del_resp.text)
            if del_resp.status_code not in (204, 404):
                _check(del_resp)


def _upload_asset(session, release, zip_path: Path):
    print("Uploading", repr(zip_path.name))
    upload_url = release["upload_url"].split("{", 1)[0]  # strip {?name,label}
    resp = session.post(
        upload_url,
        params={"name": zip_path.name},
        data=zip_path.read_bytes(),
        headers={"Content-Type": "application/zip"},
    )
    _check(resp)
    return resp.json()


def publish_app():
    import requests

    print(f"Publishing app version: {APP_VERSION}")
    session = requests.Session()
    app_bundle = _find_app_bundle()
    print(f"Zipping app bundle: {app_bundle}")
    zip_path = _zip_app_bundle(app_bundle)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {_get_github_token()}",
        "Accept": "application/vnd.github+json",
    })

    print(f"Creating release: {RELEASE_TAG}")
    repo_slug = _get_repo_slug()
    release = _get_or_create_release(session, repo_slug)
    _delete_existing_asset(session, repo_slug, release["id"], zip_path.name)

    try:
        asset = _upload_asset(session, release, zip_path)
    except requests.exceptions.HTTPError:
        # Most likely cause: a stray asset with the same name that the
        # delete above didn't catch (e.g. left over from an interrupted
        # earlier upload). Re-check for it and retry once.
        print("Upload failed -- re-checking for a stray asset and retrying once...")
        _delete_existing_asset(session, repo_slug, release["id"], zip_path.name)
        asset = _upload_asset(session, release, zip_path)

    print(f"Published version {APP_VERSION}: {asset['browser_download_url']}")


### When launching from terminal :

if len(sys.argv) > 1 and sys.argv[1] == "icon":
    build_icon()
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == "publish":
    publish_app()
    sys.exit(0)

if "py2app" in sys.argv and not Path(OPTIONS['iconfile']).exists():
    sys.exit(
        f"Error: {OPTIONS['iconfile']} not found -- run 'python setup.py icon' "
        f"first, or py2app will silently fall back to the generic app icon."
    )

print(f"Building version {APP_VERSION}")

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

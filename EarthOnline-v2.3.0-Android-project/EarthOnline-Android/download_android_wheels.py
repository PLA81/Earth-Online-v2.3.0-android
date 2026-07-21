from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

VERSION = "6.11.1"
BASE = "https://download.qt.io/official_releases/QtForPython"
FILES = {
    f"pyside6-{VERSION}-{VERSION}-cp311-cp311-android_aarch64.whl":
        f"{BASE}/pyside6/pyside6-{VERSION}-{VERSION}-cp311-cp311-android_aarch64.whl",
    f"shiboken6-{VERSION}-{VERSION}-cp311-cp311-android_aarch64.whl":
        f"{BASE}/shiboken6/shiboken6-{VERSION}-{VERSION}-cp311-cp311-android_aarch64.whl",
}


def main() -> int:
    destination = Path(__file__).resolve().parent / "android_wheels"
    destination.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        target = destination / name
        if target.exists() and target.stat().st_size > 100_000:
            print(f"Already present: {target}")
            continue
        print(f"Downloading {url}")
        urlretrieve(url, target)
        print(f"Saved: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

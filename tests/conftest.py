"""Shared fixtures. Every test runs against a throwaway home directory."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ONLY = (".github", "docs", "CONTRIBUTING.md")
"""Paths that exist in a clone but not in the source distribution."""

GROUP_CONTAINER = Path("Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings")


@pytest.fixture(autouse=True)
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the home directory at an empty temp folder so no test sees a real library."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """An empty recordings folder."""
    folder = tmp_path / "Recordings"
    folder.mkdir()
    return folder


@pytest.fixture
def default_library(fake_home: Path) -> Path:
    """An empty recordings folder at the first known macOS location under the fake home."""
    folder = fake_home / GROUP_CONTAINER
    folder.mkdir(parents=True)
    return folder


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the tests marked `repo_only` when the repository files they read are absent.

    The source distribution carries the package and its tests but not `.github/`, `docs/` or the
    community files, so a suite run from an extracted sdist must not fail on their absence.
    """
    missing = [name for name in REPOSITORY_ONLY if not (ROOT / name).exists()]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"the source distribution omits {', '.join(missing)}")
    for item in items:
        if "repo_only" in item.keywords:
            item.add_marker(skip)

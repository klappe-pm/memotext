"""Shared fixtures. Every test runs against a throwaway home directory."""

from __future__ import annotations

from pathlib import Path

import pytest

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

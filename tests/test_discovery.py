"""Tests for the four state probe and the optional Spotlight layer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType

import pytest

from voicememos import discovery
from voicememos.discovery import (
    KNOWN_PATHS,
    PathState,
    find_library,
    probe_library,
    probe_path,
    spotlight_search,
)

needs_non_root = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a directory with mode 000 is still listable by root",
)


def add_audio(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).write_bytes(b"x")


def fail_which(name: str) -> str:
    raise AssertionError("mdfind must be called by absolute path, not looked up on PATH")


class RaisingScandir:
    """A stand in for os.scandir that raises while the listing is read."""

    def __init__(self, error: OSError, *, on_iteration: bool = False) -> None:
        self.error = error
        self.on_iteration = on_iteration

    def __call__(self, path: object) -> RaisingScandir:
        if not self.on_iteration:
            raise self.error
        return self

    def __enter__(self) -> RaisingScandir:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def __iter__(self) -> Iterator[os.DirEntry[str]]:
        raise self.error


class TestProbePath:
    def test_missing(self, tmp_path: Path) -> None:
        probe = probe_path(tmp_path / "nope")
        assert probe.state is PathState.MISSING
        assert probe.recording_count == 0
        assert probe.path == tmp_path / "nope"

    def test_a_file_is_missing_not_readable(self, tmp_path: Path) -> None:
        target = tmp_path / "file"
        target.write_text("x")
        assert probe_path(target).state is PathState.MISSING

    def test_readable_counts_audio_files(self, library: Path) -> None:
        add_audio(library, "a.m4a", "b.m4a", "c.txt")
        probe = probe_path(library)
        assert probe.state is PathState.READABLE
        assert probe.recording_count == 2

    def test_suffix_is_case_insensitive(self, library: Path) -> None:
        add_audio(library, "a.M4A")
        assert probe_path(library).recording_count == 1

    def test_directories_named_like_audio_are_not_counted(self, library: Path) -> None:
        (library / "folder.m4a").mkdir()
        assert probe_path(library).state is PathState.EMPTY

    def test_empty_folder(self, library: Path) -> None:
        assert probe_path(library).state is PathState.EMPTY

    def test_folder_with_only_other_files_is_empty(self, library: Path) -> None:
        add_audio(library, "CloudRecordings.db", "notes.txt")
        assert probe_path(library).state is PathState.EMPTY

    def test_tilde_is_expanded(self, fake_home: Path) -> None:
        folder = fake_home / "Rec"
        folder.mkdir()
        add_audio(folder, "a.m4a")
        probe = probe_path("~/Rec")
        assert probe.path == folder
        assert probe.state is PathState.READABLE

    def test_accepts_str(self, library: Path) -> None:
        assert probe_path(str(library)).state is PathState.EMPTY

    def test_permission_error_is_blocked_not_found(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mocked, so it also runs as root."""
        error = PermissionError(1, "Operation not permitted", str(library))
        monkeypatch.setattr(os, "scandir", RaisingScandir(error))
        probe = probe_path(library)
        assert probe.state is PathState.BLOCKED
        assert probe.detail == "Operation not permitted"
        assert probe.recording_count == 0

    def test_permission_error_during_iteration_is_blocked(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        error = PermissionError(13, "Permission denied")
        monkeypatch.setattr(os, "scandir", RaisingScandir(error, on_iteration=True))
        assert probe_path(library).state is PathState.BLOCKED

    def test_other_os_errors_are_blocked(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(os, "scandir", RaisingScandir(OSError(5, "Input/output error")))
        probe = probe_path(library)
        assert probe.state is PathState.BLOCKED
        assert probe.detail == "Input/output error"

    def test_error_without_text_still_has_a_detail(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(os, "scandir", RaisingScandir(OSError()))
        assert probe_path(library).detail == "OSError"

    @needs_non_root
    def test_real_permission_denied_directory(self, library: Path) -> None:
        add_audio(library, "a.m4a")
        library.chmod(0o000)
        try:
            probe = probe_path(library)
        finally:
            library.chmod(0o755)
        assert probe.state is PathState.BLOCKED
        assert probe.recording_count == 0

    def test_to_dict(self, library: Path) -> None:
        add_audio(library, "a.m4a")
        assert probe_path(library).to_dict() == {
            "path": str(library),
            "state": "readable",
            "recording_count": 1,
            "detail": None,
        }


class TestProbeLibrary:
    def test_defaults_to_the_known_paths_in_order(self, fake_home: Path) -> None:
        probes = probe_library()
        assert [p.path for p in probes] == [
            Path(str(p).replace("~", str(fake_home), 1)) for p in KNOWN_PATHS
        ]
        assert {p.state for p in probes} == {PathState.MISSING}

    def test_known_paths_all_start_with_a_tilde(self) -> None:
        assert all(str(p).startswith("~") for p in KNOWN_PATHS)
        assert len(set(KNOWN_PATHS)) == len(KNOWN_PATHS)

    def test_reports_each_given_path(self, tmp_path: Path) -> None:
        readable = tmp_path / "readable"
        empty = tmp_path / "empty"
        readable.mkdir()
        empty.mkdir()
        add_audio(readable, "a.m4a")
        probes = probe_library([readable, str(empty), tmp_path / "missing"])
        assert [p.state for p in probes] == [PathState.READABLE, PathState.EMPTY, PathState.MISSING]

    def test_mixed_states_with_a_mocked_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blocked = tmp_path / "blocked"
        readable = tmp_path / "readable"
        blocked.mkdir()
        readable.mkdir()
        add_audio(readable, "a.m4a")
        real_scandir = os.scandir

        def fake(path: str | os.PathLike[str]) -> object:
            if Path(path) == blocked:
                raise PermissionError(1, "Operation not permitted")
            return real_scandir(path)

        monkeypatch.setattr(os, "scandir", fake)
        probes = probe_library([blocked, readable])
        assert [p.state for p in probes] == [PathState.BLOCKED, PathState.READABLE]

    def test_empty_list(self) -> None:
        assert probe_library([]) == []


class TestFindLibrary:
    def test_none_when_nothing_exists(self) -> None:
        assert find_library() is None

    def test_finds_a_known_path_under_the_home(self, default_library: Path) -> None:
        add_audio(default_library, "a.m4a")
        assert find_library() == default_library

    def test_first_readable_path_wins(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        add_audio(first, "a.m4a")
        add_audio(second, "a.m4a", "b.m4a")
        assert find_library([first, second]) == first

    def test_empty_folder_is_not_found(self, library: Path) -> None:
        assert find_library([library]) is None

    def test_blocked_folder_is_never_found(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_audio(library, "a.m4a")
        monkeypatch.setattr(
            os, "scandir", RaisingScandir(PermissionError(1, "Operation not permitted"))
        )
        assert find_library([library]) is None

    def test_a_blocked_path_does_not_hide_a_later_readable_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blocked = tmp_path / "blocked"
        good = tmp_path / "good"
        blocked.mkdir()
        good.mkdir()
        add_audio(good, "a.m4a")
        real_scandir = os.scandir

        def fake(path: str | os.PathLike[str]) -> object:
            if Path(path) == blocked:
                raise PermissionError(1, "Operation not permitted")
            return real_scandir(path)

        monkeypatch.setattr(os, "scandir", fake)
        assert find_library([blocked, good]) == good

    @needs_non_root
    def test_real_permission_denied_directory_is_not_found(self, library: Path) -> None:
        add_audio(library, "a.m4a")
        library.chmod(0o000)
        try:
            assert find_library([library]) is None
        finally:
            library.chmod(0o755)

    def test_spotlight_is_off_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail() -> list[Path]:
            raise AssertionError("spotlight must not run unless asked")

        monkeypatch.setattr(discovery, "spotlight_search", fail)
        assert find_library([tmp_path / "missing"]) is None

    def test_spotlight_picks_the_readable_folder_with_most_recordings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        small = tmp_path / "small"
        big = tmp_path / "big"
        empty = tmp_path / "empty"
        for folder in (small, big, empty):
            folder.mkdir()
        add_audio(small, "a.m4a")
        add_audio(big, "a.m4a", "b.m4a", "c.m4a")
        monkeypatch.setattr(
            discovery, "spotlight_search", lambda: [small, empty, big, tmp_path / "gone"]
        )
        assert find_library([tmp_path / "missing"], spotlight=True) == big

    def test_spotlight_ties_break_by_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        add_audio(a, "1.m4a")
        add_audio(b, "1.m4a")
        monkeypatch.setattr(discovery, "spotlight_search", lambda: [b, a])
        assert find_library([], spotlight=True) == a

    def test_spotlight_skips_paths_already_probed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(discovery, "spotlight_search", lambda: [empty])
        assert find_library([empty], spotlight=True) is None

    def test_spotlight_with_no_candidates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discovery, "spotlight_search", lambda: [])
        assert find_library([], spotlight=True) is None


class TestSpotlightSearch:
    def test_parent_folders_are_returned_once_in_order(self) -> None:
        output = {
            "-name": "/a/Recordings/CloudRecordings.db\n/b/Recordings/CloudRecordings.db\n\n",
            "kMDItem": "/a/Recordings/one.m4a\n  /c/Recordings/two.m4a  \n/a/Recordings/x.m4a\n",
        }

        def runner(args: list[str]) -> str:
            return output["-name"] if args[0] == "-name" else output["kMDItem"]

        assert spotlight_search(runner) == [
            Path("/a/Recordings"),
            Path("/b/Recordings"),
            Path("/c/Recordings"),
        ]

    def test_both_queries_are_sent(self) -> None:
        seen: list[list[str]] = []

        def runner(args: list[str]) -> str:
            seen.append(args)
            return ""

        assert spotlight_search(runner) == []
        assert seen[0] == ["-name", "CloudRecordings.db"]
        assert "com.apple.m4a-audio" in seen[1][0]
        assert "VoiceMemos" in seen[1][0]

    def test_skipped_off_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(os, "access", lambda path, mode: True)

        def no_run(*args: object, **kwargs: object) -> object:
            raise AssertionError("mdfind must not run off macOS")

        monkeypatch.setattr(subprocess, "run", no_run)
        assert spotlight_search() == []

    def test_skipped_when_mdfind_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(os, "access", lambda path, mode: False)
        assert spotlight_search() == []

    def test_runs_mdfind_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The subprocess is faked, so no real Spotlight index is read."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(os, "access", lambda path, mode: True)
        monkeypatch.setattr(shutil, "which", fail_which)
        calls: list[list[str]] = []

        class Result:
            stdout = "/x/Recordings/CloudRecordings.db\n"

        def fake_run(command: list[str], **kwargs: object) -> Result:
            calls.append(command)
            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert spotlight_search() == [Path("/x/Recordings")]
        assert calls[0][0] == "/usr/bin/mdfind"
        assert calls[0][0] == discovery.MDFIND
        assert len(calls) == 2

    def test_mdfind_failure_gives_no_candidates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(os, "access", lambda path, mode: True)

        def boom(*args: object, **kwargs: object) -> object:
            raise OSError("no such program")

        monkeypatch.setattr(subprocess, "run", boom)
        assert spotlight_search() == []

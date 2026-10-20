"""Regression tests for hostile input: files in a library are written by other programs.

Each test builds a small synthetic input. Tests that would hang or run for a very long time
without the fix run under a deadline, so they fail fast instead.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import plistlib
import shutil
import signal
import struct
import subprocess
import sys
import time
import unicodedata
import warnings
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.synthetic import box, make_m4a, mvhd, write_manifest
from voicememos import mp4, transcripts
from voicememos import recording as recording_module
from voicememos.cli import _dump, main
from voicememos.errors import (
    CompositionLimitError,
    RecordingSkippedWarning,
    UnsafeFileError,
    VoiceMemosError,
)
from voicememos.mp4 import read_duration_seconds, read_tsrp_payload
from voicememos.recording import Recording, content_hash, iter_recordings, local_time
from voicememos.safeio import close_dir, is_real_dir, open_dir, open_regular, scan_dir
from voicememos.textsafe import printable
from voicememos.transcripts import read_manifest, transcript_from_manifest

STEM = "20240101 120000-ABCD"


@contextlib.contextmanager
def deadline(seconds: float = 3.0) -> Iterator[None]:
    """Fail the test with TimeoutError if the block runs longer than `seconds`."""
    if not hasattr(signal, "setitimer"):
        pytest.skip("signal.setitimer is not available on this platform")

    def expire(signum: int, frame: object) -> None:
        raise TimeoutError(f"exceeded {seconds} seconds")

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def needs_fifo() -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo is not available on this platform")


def make_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")


@pytest.fixture
def set_timezone() -> Iterator[Callable[[str], None]]:
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    with pytest.MonkeyPatch.context() as patch:

        def apply(name: str) -> None:
            patch.setenv("TZ", name)
            time.tzset()

        yield apply
    time.tzset()


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def strict_json(text: str) -> object:
    def reject(name: str) -> object:
        raise AssertionError(f"non standard JSON constant {name}")

    return json.loads(text, parse_constant=reject)


# 1. box walking is lazy and bounded


class TestBoxBudgets:
    def test_many_tiny_boxes_stop_at_the_box_budget(self, tmp_path: Path) -> None:
        free = struct.pack(">I4s", 8, b"free") * (mp4._MAX_BOXES * 2)
        path = tmp_path / "a.m4a"
        path.write_bytes(box(b"ftyp", b"M4A ") + free + box(b"moov", mvhd(5.0)))
        with deadline():
            assert read_duration_seconds(path) is None

    def test_tsrp_behind_the_box_budget_is_not_found_or_scanned(self, tmp_path: Path) -> None:
        free = struct.pack(">I4s", 8, b"free") * (mp4._MAX_BOXES * 2)
        path = tmp_path / "a.m4a"
        path.write_bytes(box(b"ftyp", b"M4A ") + free + box(b"tsrp", b"{}"))
        with deadline():
            assert read_tsrp_payload(path) is None

    def test_the_walk_stops_at_the_first_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        free = struct.pack(">I4s", 8, b"free") * (mp4._MAX_BOXES - 10)
        path = tmp_path / "a.m4a"
        path.write_bytes(box(b"moov", mvhd(5.0)) + free)
        real = mp4._parse_header
        calls: list[int] = []

        def counting(f: object, pos: int, end: int) -> object:
            calls.append(pos)
            return real(f, pos, end)  # type: ignore[arg-type]

        monkeypatch.setattr(mp4, "_parse_header", counting)
        assert read_duration_seconds(path) == pytest.approx(5.0)
        assert len(calls) <= 3

    def test_byte_scan_stops_after_the_byte_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "a.m4a"
        path.write_bytes(b"JUNK" * 1000 + box(b"tsrp", b"{}"))
        monkeypatch.setattr(mp4, "_MAX_SCAN_BYTES", 2000)
        assert read_tsrp_payload(path) is None
        monkeypatch.setattr(mp4, "_MAX_SCAN_BYTES", 10_000)
        assert read_tsrp_payload(path) == b"{}"

    def test_byte_scan_stops_after_the_hit_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = struct.pack(">I", 2) + b"tsrp"
        path = tmp_path / "a.m4a"
        path.write_bytes(b"JUNK" + bad * (mp4._MAX_SCAN_HITS + 50) + box(b"tsrp", b"{}"))
        real = mp4._parse_header
        calls: list[int] = []

        def counting(f: object, pos: int, end: int) -> object:
            calls.append(pos)
            return real(f, pos, end)  # type: ignore[arg-type]

        monkeypatch.setattr(mp4, "_parse_header", counting)
        assert read_tsrp_payload(path) is None
        assert len(calls) <= mp4._MAX_SCAN_HITS + 10


# 2 and 3. the transcript search is iterative, bounded and visits shared values once


def nested(depth: int, leaf: object = "x") -> object:
    value: object = [leaf]
    for _ in range(depth):
        value = [value]
    return value


class TestSearchBounds:
    def test_deep_nesting_does_not_raise(self) -> None:
        assert transcript_from_manifest({"transcript": nested(3000)}) is None

    def test_deep_xml_plist_does_not_raise(self, tmp_path: Path) -> None:
        depth = 3000
        xml = (
            b"<plist><dict><key>transcript</key>"
            + b"<array>" * depth
            + b"</array>" * depth
            + b"</dict></plist>"
        )
        composition = tmp_path / "x.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(xml)
        manifest = read_manifest(composition)
        if manifest is not None:
            assert transcript_from_manifest(manifest) is None

    def test_text_within_the_depth_limit_is_found(self) -> None:
        value = nested(transcripts._MAX_SEARCH_DEPTH - 4, {"text": "deep words"})
        assert transcript_from_manifest({"transcript": value}) == "deep words"

    def test_text_beyond_the_depth_limit_is_not(self) -> None:
        value = nested(transcripts._MAX_SEARCH_DEPTH + 4, {"text": "too deep"})
        assert transcript_from_manifest({"transcript": value}) is None

    def test_shared_references_are_visited_once(self) -> None:
        value: list[object] = []
        for _ in range(30):
            value = [value, value]
        with deadline(2.0):
            assert transcript_from_manifest({"transcript": value}) is None

    def test_shared_references_in_a_binary_plist(self, tmp_path: Path) -> None:
        value: list[object] = []
        for _ in range(25):
            value = [value, value]
        composition = tmp_path / "x.composition"
        composition.mkdir()
        data = plistlib.dumps({"transcript": value}, fmt=plistlib.FMT_BINARY)
        (composition / "manifest.plist").write_bytes(data)
        assert len(data) < 2000
        with deadline(2.0):
            manifest = read_manifest(composition)
            assert manifest is not None
            assert transcript_from_manifest(manifest) is None

    def test_shared_values_do_not_use_up_the_visit_budget(self) -> None:
        """Without the seen set, 2**20 paths through the shared chain exhaust the budget."""
        shared: list[object] = []
        for _ in range(20):
            shared = [shared, shared]
        manifest = {"transcript": [shared, [{"text": "found after"}]]}
        with deadline(2.0):
            assert transcript_from_manifest(manifest) == "found after"

    def test_visit_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wide = [[] for _ in range(6)] + [[{"text": "found late"}]]
        manifest = {"transcript": wide}
        assert transcript_from_manifest(manifest) == "found late"
        monkeypatch.setattr(transcripts, "_MAX_SEARCH_VISITS", 5)
        assert transcript_from_manifest(manifest) is None


# 4. FIFOs and other special files never block


class TestSpecialFiles:
    def test_fifo_manifest_does_not_hang(self, tmp_path: Path) -> None:
        needs_fifo()
        composition = tmp_path / "x.composition"
        composition.mkdir()
        os.mkfifo(composition / "manifest.plist")
        with deadline():
            assert read_manifest(composition) is None

    def test_fifo_audio_does_not_hang(self, tmp_path: Path) -> None:
        needs_fifo()
        audio = tmp_path / "a.m4a"
        os.mkfifo(audio)
        with deadline():
            assert read_tsrp_payload(audio) is None
            assert read_duration_seconds(audio) is None

    def test_fifo_audio_is_not_hashed(self, tmp_path: Path) -> None:
        needs_fifo()
        audio = tmp_path / "a.m4a"
        os.mkfifo(audio)
        rec = Recording(
            id="a",
            audio_path=audio,
            composition_path=None,
            recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
            duration_seconds=None,
            title="t",
            transcript_text=None,
            transcript_source=None,
        )
        with deadline(), pytest.raises(UnsafeFileError):
            content_hash(rec)

    def test_fifo_named_like_audio_is_not_listed(self, library: Path) -> None:
        needs_fifo()
        os.mkfifo(library / "a.m4a")
        with deadline():
            assert list(iter_recordings(library)) == []

    def test_fifo_in_a_composition_is_not_hashed(self, library: Path) -> None:
        needs_fifo()
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "T"})
        rec = next(iter_recordings(library))
        before = content_hash(rec)
        os.mkfifo(library / "a.composition" / "pipe")
        with deadline():
            assert content_hash(rec) == before

    def test_open_regular_refuses_directories_and_missing_files(self, tmp_path: Path) -> None:
        with pytest.raises(UnsafeFileError):
            open_regular(tmp_path)
        with pytest.raises(FileNotFoundError):
            open_regular(tmp_path / "missing")

    def test_open_regular_closes_the_descriptor_on_refusal(self, tmp_path: Path) -> None:
        before = len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
        for _ in range(20):
            with pytest.raises(UnsafeFileError):
                open_regular(tmp_path)
        if before is not None:
            assert len(os.listdir("/proc/self/fd")) <= before + 1


# 5. non finite and huge durations


def raw_manifest(inner: str) -> bytes:
    return f'<?xml version="1.0"?><plist version="1.0"><dict>{inner}</dict></plist>'.encode()


class TestDurations:
    @pytest.mark.parametrize(
        "value",
        [
            "<real>nan</real>",
            "<real>inf</real>",
            "<real>-inf</real>",
            f"<integer>{10**400}</integer>",
        ],
    )
    def test_unusable_manifest_durations_are_ignored(self, library: Path, value: str) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=7.0)
        composition = library / f"{STEM}.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(raw_manifest(f"<key>duration</key>{value}"))
        rec = next(iter_recordings(library))
        assert rec.duration_seconds == pytest.approx(7.0)

    @pytest.mark.parametrize("value", ["<real>nan</real>", f"<integer>{10**400}</integer>"])
    def test_cli_json_survives_and_is_strict(
        self, library: Path, capsys: pytest.CaptureFixture[str], value: str
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        composition = library / f"{STEM}.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(raw_manifest(f"<key>duration</key>{value}"))
        for command in (["list"], ["show", STEM]):
            code, out, err = run(capsys, *command, "--library", str(library), "--json")
            assert code == 0, err
            data = strict_json(out)
            row = data[0] if isinstance(data, list) else data
            assert row["duration_seconds"] is None  # type: ignore[index]

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_recording_rejects_non_finite_durations(self, value: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            Recording(
                id="a",
                audio_path=Path("a.m4a"),
                composition_path=None,
                recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
                duration_seconds=value,
                title="t",
                transcript_text=None,
                transcript_source=None,
            )

    def test_json_output_refuses_nan(self) -> None:
        with pytest.raises(ValueError):
            _dump({"x": float("nan")})


# 6. dates at the edge of the supported range


class TestEdgeDates:
    @pytest.mark.parametrize(
        ("stem", "zone", "expected"),
        [
            ("99991231 235959-AA", "Etc/GMT+8", datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)),
            ("00010101 000000-AA", "Etc/GMT-14", datetime(1, 1, 1, 0, 0, 0, tzinfo=UTC)),
        ],
    )
    def test_extreme_file_name_dates(
        self,
        library: Path,
        set_timezone: Callable[[str], None],
        stem: str,
        zone: str,
        expected: datetime,
    ) -> None:
        set_timezone(zone)
        make_m4a(library / f"{stem}.m4a")
        rec = next(iter_recordings(library))
        assert rec.recorded_at == expected
        assert rec.title.startswith("Voice Memo")

    @pytest.mark.parametrize(
        ("date", "zone"),
        [
            (datetime(9999, 12, 31, 23, 59, 59), "Etc/GMT-14"),
            (datetime(1, 1, 1, 0, 0, 0), "Etc/GMT+8"),
        ],
    )
    def test_extreme_manifest_dates_do_not_crash_the_cli(
        self,
        library: Path,
        set_timezone: Callable[[str], None],
        capsys: pytest.CaptureFixture[str],
        date: datetime,
        zone: str,
    ) -> None:
        set_timezone(zone)
        make_m4a(library / "plain.m4a")
        write_manifest(library / "plain.composition", {"creationDate": date})
        for command in (["list"], ["show", "plain"]):
            code, out, err = run(capsys, *command, "--library", str(library))
            assert code == 0, err
            assert "Traceback" not in err
            assert out

    def test_local_time_falls_back_to_the_value_it_was_given(
        self, set_timezone: Callable[[str], None]
    ) -> None:
        set_timezone("Etc/GMT-14")
        moment = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)
        assert local_time(moment) == moment

    @pytest.mark.parametrize("seconds", [1e20, -1e20, float(2**62)])
    def test_out_of_range_file_times_become_the_epoch(self, seconds: float) -> None:
        assert recording_module._from_timestamp(seconds) == datetime(1970, 1, 1, tzinfo=UTC)

    def test_in_range_file_times_are_kept(self) -> None:
        assert recording_module._from_timestamp(86400.0) == datetime(1970, 1, 2, tzinfo=UTC)


# 7. one unreadable recording does not stop the rest


@pytest.fixture
def three_with_one_blocked(library: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("a", "b", "c"):
        make_m4a(library / f"{name}.m4a", transcript=f"words {name}")
        write_manifest(library / f"{name}.composition", {"title": name.upper()})
    real_open = os.open

    def guarded(path: str | os.PathLike[str], *args: object, **kwargs: object) -> int:
        if str(path).endswith("b.composition"):
            raise PermissionError(1, "Operation not permitted")
        return real_open(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", guarded)
    return library


class TestPerRecordingErrors:
    def test_on_skip_receives_the_error_and_the_rest_are_yielded(
        self, three_with_one_blocked: Path
    ) -> None:
        skipped: list[tuple[Path, OSError]] = []
        found = list(
            iter_recordings(three_with_one_blocked, on_skip=lambda p, e: skipped.append((p, e)))
        )
        assert [r.id for r in found] == ["a", "c"]
        assert [p.name for p, _ in skipped] == ["b.m4a"]
        assert isinstance(skipped[0][1], PermissionError)

    def test_a_warning_is_issued_without_a_handler(self, three_with_one_blocked: Path) -> None:
        with pytest.warns(RecordingSkippedWarning, match=r"skipped .*b\.m4a"):
            found = list(iter_recordings(three_with_one_blocked))
        assert [r.id for r in found] == ["a", "c"]

    def test_list_warns_on_stderr_and_still_prints_the_rest(
        self, three_with_one_blocked: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, err = run(capsys, "list", "--library", str(three_with_one_blocked))
        assert code == 0
        assert "warning: skipped" in err
        assert "b.m4a" in err
        assert "Traceback" not in err
        assert "a" in out and "c" in out
        assert out.count("\n") == 3

    def test_show_of_another_recording_still_works(
        self, three_with_one_blocked: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, err = run(capsys, "show", "c", "--library", str(three_with_one_blocked))
        assert code == 0
        assert "words c" in out
        assert "warning: skipped" in err

    def test_a_file_that_vanishes_after_listing_is_skipped(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "gone.m4a")
        make_m4a(library / "kept.m4a")
        real_lstat = os.lstat

        def racing(path: str | os.PathLike[str], *args: object, **kwargs: object) -> os.stat_result:
            if str(path).endswith("gone.m4a"):
                raise FileNotFoundError(2, "No such file or directory")
            return real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "lstat", racing)
        skipped: list[Path] = []
        found = list(iter_recordings(library, on_skip=lambda p, e: skipped.append(p)))
        assert [r.id for r in found] == ["kept"]
        assert [p.name for p in skipped] == ["gone.m4a"]

    def test_a_read_error_after_loading_is_reported_not_a_traceback(
        self, library: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a", transcript="words")

        def boom(recording: Recording) -> object:
            raise PermissionError(1, "Operation not permitted")

        monkeypatch.setattr("voicememos.cli.read_transcript", boom)
        code, _, err = run(capsys, "show", "a", "--library", str(library))
        assert code == 1
        assert err.startswith("voicememos:")
        assert "Traceback" not in err


# 8 and 9. text from files is made safe before it reaches a terminal


def binary_manifest(composition: Path, data: dict[str, object]) -> None:
    composition.mkdir(parents=True, exist_ok=True)
    (composition / "manifest.plist").write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))


HOSTILE_TITLE = (
    "Meeting\x1b]0;PWNED\x07\x1b[2J\x1b[31mred\n"
    "FAKEID  2099-01-01 00:00  0:01  tsrp  forged\r\x9b\x7f\u202e"
)
HOSTILE_TRANSCRIPT = "line one\x1b]52;c;ZWNjaG8=\x07\nline two\x00\x85 end"


class TestTerminalSafety:
    def test_printable_escapes_controls(self) -> None:
        assert printable("a\x1b[2Jb") == "a\\x1b[2Jb"
        assert printable("a\x07\x00\x7f\x9b") == "a\\x07\\x00\\x7f\\x9b"
        assert printable("a\nb\rc\td") == "a\\nb\\rc\\td"
        assert printable("\u2028\u202e\u2066\ufeff") == "\\u2028\\u202e\\u2066\\ufeff"
        assert (
            printable("plain text, with unicode: caf\u00e9")
            == "plain text, with unicode: caf\u00e9"
        )

    def test_printable_keeps_newlines_only_when_asked(self) -> None:
        assert printable("a\nb\x1b", keep_newlines=True) == "a\nb\\x1b"
        assert printable("a\nb") == "a\\nb"

    def test_printable_replaces_lone_surrogates(self) -> None:
        text = printable("ok\ud800end")
        assert text == "ok?end"
        text.encode("utf-8")

    def test_list_cannot_be_forged_or_scripted(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        binary_manifest(library / f"{STEM}.composition", {"title": HOSTILE_TITLE})
        code, out, _ = run(capsys, "list", "--library", str(library))
        assert code == 0
        assert len(out.splitlines()) == 2
        assert "FAKEID" in out
        assert out.splitlines()[1].startswith(STEM)
        for bad in ("\x1b", "\x07", "\x9b", "\x7f", "\r", "\u202e"):
            assert bad not in out
        assert "\\x1b]0;PWNED" in out

    def test_a_file_name_with_an_escape_is_escaped(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "20240102 120000-BB\x1b[2J.m4a")
        code, out, _ = run(capsys, "list", "--library", str(library))
        assert code == 0
        assert "\x1b" not in out
        assert "\\x1b[2J" in out

    def test_show_escapes_every_field_but_keeps_transcript_lines(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        binary_manifest(
            library / f"{STEM}.composition",
            {"title": HOSTILE_TITLE, "transcript": HOSTILE_TRANSCRIPT},
        )
        code, out, _ = run(capsys, "show", STEM, "--library", str(library))
        assert code == 0
        for bad in ("\x1b", "\x07", "\x9b", "\x7f", "\r", "\x00", "\x85", "\u202e"):
            assert bad not in out
        title_line = next(line for line in out.splitlines() if line.startswith("title:"))
        assert "FAKEID" in title_line
        assert "line one\\x1b]52;c;ZWNjaG8=\\x07\nline two\\x00\\x85 end" in out

    def test_error_messages_are_escaped(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(capsys, "show", "bad\x1b[2J\nforged", "--library", str(library))
        assert code == 1
        assert "\x1b" not in err
        assert err.count("\n") == 1

    def test_json_output_is_plain_ascii(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        binary_manifest(library / f"{STEM}.composition", {"title": HOSTILE_TITLE})
        _, out, _ = run(capsys, "list", "--library", str(library), "--json")
        assert out.isascii()
        assert strict_json(out)[0]["title"].startswith("Meeting")  # type: ignore[index]

    def test_lone_surrogate_in_a_transcript_does_not_crash_show(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = b'{"attributedString": {"runs": ["bad \\ud800 text", 0]}}'
        make_m4a(library / "a.m4a", tsrp=payload)
        for extra in ([], ["--json"]):
            code, out, err = run(capsys, "show", "a", "--library", str(library), *extra)
            assert code == 0, err
            out.encode("utf-8")
        assert "bad" in out

    def test_a_file_name_that_is_not_utf8_does_not_crash_list(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        name = os.fsencode(library) + b"/bad\xff.m4a"
        try:
            with open(name, "wb") as f:
                f.write(b"\x00" * 16)
        except OSError:
            pytest.skip("the file system does not allow non UTF-8 names")
        for extra in ([], ["--json"]):
            code, out, err = run(capsys, "list", "--library", str(library), *extra)
            assert code == 0, err
            out.encode("utf-8")


# 10. symlinks are never followed out of the library


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    folder = tmp_path / "outside"
    folder.mkdir()
    make_m4a(folder / "other.m4a", transcript="SECRET FROM OUTSIDE", duration=9.0)
    write_manifest(
        folder / "other.composition", {"title": "outside title", "transcript": "outside plist"}
    )
    return folder


class TestSymlinks:
    def test_a_symlinked_audio_file_is_not_a_recording(self, library: Path, outside: Path) -> None:
        make_symlink(library / "linked.m4a", outside / "other.m4a")
        assert list(iter_recordings(library)) == []

    def test_a_symlinked_audio_file_is_not_counted_by_the_probe(
        self, library: Path, outside: Path
    ) -> None:
        from voicememos import PathState, probe_path

        make_symlink(library / "linked.m4a", outside / "other.m4a")
        assert probe_path(library).state is PathState.EMPTY

    def test_a_symlinked_composition_folder_is_ignored(self, library: Path, outside: Path) -> None:
        make_m4a(library / "a.m4a")
        make_symlink(library / "a.composition", outside / "other.composition")
        rec = next(iter_recordings(library))
        assert rec.composition_path is None
        assert rec.title != "outside title"
        assert rec.transcript_text is None

    def test_a_symlinked_manifest_is_ignored(self, library: Path, outside: Path) -> None:
        make_m4a(library / "a.m4a")
        composition = library / "a.composition"
        composition.mkdir()
        make_symlink(
            composition / "manifest.plist", outside / "other.composition" / "manifest.plist"
        )
        rec = next(iter_recordings(library))
        assert rec.composition_path == composition
        assert rec.title != "outside title"
        assert rec.transcript_text is None

    def test_read_manifest_refuses_a_symlinked_folder(self, tmp_path: Path, outside: Path) -> None:
        make_symlink(tmp_path / "link.composition", outside / "other.composition")
        assert read_manifest(tmp_path / "link.composition") is None
        assert not is_real_dir(tmp_path / "link.composition")

    def test_symlinked_audio_is_not_read_by_the_parsers(
        self, tmp_path: Path, outside: Path
    ) -> None:
        link = tmp_path / "link.m4a"
        make_symlink(link, outside / "other.m4a")
        assert read_tsrp_payload(link) is None
        assert read_duration_seconds(link) is None

    def test_content_hash_refuses_symlinked_audio(self, library: Path, outside: Path) -> None:
        link = library / "link.m4a"
        make_symlink(link, outside / "other.m4a")
        rec = Recording(
            id="link",
            audio_path=link,
            composition_path=None,
            recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
            duration_seconds=None,
            title="t",
            transcript_text=None,
            transcript_source=None,
        )
        with pytest.raises(UnsafeFileError):
            content_hash(rec)

    def test_content_hash_ignores_symlinks_inside_a_composition(
        self, library: Path, outside: Path
    ) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "T"})
        rec = next(iter_recordings(library))
        before = content_hash(rec)
        make_symlink(library / "a.composition" / "extra", outside / "other.m4a")
        make_symlink(library / "a.composition" / "dir", outside)
        assert content_hash(rec) == before

    def test_the_cli_does_not_show_outside_data(
        self, library: Path, outside: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_symlink(library / "linked.m4a", outside / "other.m4a")
        _, out, _ = run(capsys, "list", "--library", str(library))
        assert "SECRET" not in out
        assert "linked" not in out


# lazy transcripts in list


class TestLazyTranscripts:
    def test_transcripts_false_keeps_the_source_but_not_the_text(self, library: Path) -> None:
        make_m4a(library / "a.m4a", transcript="long words")
        lazy = next(iter_recordings(library, transcripts=False))
        full = next(iter_recordings(library))
        assert lazy.transcript_text is None
        assert lazy.transcript_source == "tsrp"
        assert full.transcript_text == "long words"

    def test_list_asks_for_no_transcript_text(
        self, library: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a", transcript="long words")
        seen: list[dict[str, object]] = []
        real = recording_module.iter_recordings

        def spy(path: object, **kwargs: object) -> object:
            seen.append(kwargs)
            return real(path, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("voicememos.cli.iter_recordings", spy)
        for extra in ([], ["--json"]):
            code, out, _ = run(capsys, "list", "--library", str(library), *extra)
            assert code == 0
            assert "long words" not in out
        assert all(kwargs.get("transcripts") is False for kwargs in seen)
        assert len(seen) == 2


# hostile manifests that make plistlib raise unexpected exception types

HOSTILE_PLISTS = [
    pytest.param(
        b'<plist version="1.0"><dict><key>creationDate</key><date>x</date></dict></plist>',
        id="bad-date",
    ),
    pytest.param(b"<plist><key>a</key></plist>", id="key-outside-dict"),
    pytest.param(b'<?xml version="1.0" encoding="nope"?><plist/>', id="unknown-encoding"),
]


class TestHostilePlists:
    @pytest.mark.parametrize("data", HOSTILE_PLISTS)
    def test_read_manifest_treats_the_file_as_no_manifest(
        self, tmp_path: Path, data: bytes
    ) -> None:
        composition = tmp_path / "x.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(data)
        assert read_manifest(composition) is None

    @pytest.mark.parametrize("data", HOSTILE_PLISTS)
    def test_list_still_lists_the_good_memo(
        self, library: Path, capsys: pytest.CaptureFixture[str], data: bytes
    ) -> None:
        make_m4a(library / "good.m4a")
        make_m4a(library / "bad.m4a")
        composition = library / "bad.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(data)
        code, out, err = run(capsys, "list", "--library", str(library))
        assert code == 0, err
        assert "good" in out
        assert "bad" in out
        assert "Traceback" not in err

    def test_an_unexpected_error_skips_one_recording_and_reports_it(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a")
        make_m4a(library / "b.m4a")
        write_manifest(library / "b.composition", {"title": "B"})
        real = recording_module.read_manifest

        def explode(path: Path) -> object:
            if path.name == "b.composition":
                raise AttributeError("hostile")
            return real(path)

        monkeypatch.setattr(recording_module, "read_manifest", explode)
        skipped: list[tuple[Path, OSError]] = []
        found = list(iter_recordings(library, on_skip=lambda p, e: skipped.append((p, e))))
        assert [r.id for r in found] == ["a"]
        assert [p.name for p, _ in skipped] == ["b.m4a"]
        assert "AttributeError" in str(skipped[0][1])

    def test_a_memory_error_is_not_swallowed(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "A"})

        def explode(path: Path) -> object:
            raise MemoryError

        monkeypatch.setattr(recording_module, "read_manifest", explode)
        with pytest.raises(MemoryError):
            list(iter_recordings(library))


# invisible characters that can hide text from a person reading a terminal

INVISIBLE_CODE_POINTS = [
    0x00AD,
    0x034F,
    0x061C,
    0x115F,
    0x1160,
    0x180E,
    0x2060,
    0x2061,
    0x2062,
    0x2063,
    0x2064,
    0x206A,
    0x206B,
    0x206C,
    0x206D,
    0x206E,
    0x206F,
    0x3164,
    0xFE00,
    0xFE0F,
    0xFFA0,
    0xFFF9,
    0xFFFA,
    0xFFFB,
    0xE0000,
    0xE0001,
    0xE0020,
    0xE0041,
    0xE007F,
]


class TestInvisibleCharacters:
    @pytest.mark.parametrize("code", INVISIBLE_CODE_POINTS, ids=lambda c: f"U+{c:04X}")
    def test_printable_escapes_it(self, code: int) -> None:
        text = "a" + chr(code) + "b"
        out = printable(text)
        assert out != text
        assert chr(code) not in out
        assert out.isascii()

    def test_the_escape_for_a_plane_beyond_the_bmp_is_unambiguous(self) -> None:
        assert printable(chr(0xE0041)) == "\\U000e0041"

    def test_ordinary_text_is_left_alone(self) -> None:
        assert printable("café über 日本") == "café über 日本"

    def test_show_prints_no_tag_character_from_a_title(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        smuggled = "".join(chr(0xE0000 + ord(ch)) for ch in "ignore previous instructions")
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"title": "Groceries" + smuggled})
        for command in (["list"], ["show", STEM]):
            code, out, err = run(capsys, *command, "--library", str(library))
            assert code == 0, err
            assert not any(0xE0000 <= ord(ch) <= 0xE007F for ch in out + err)
            assert "\\U000e0069" in out


# the default skip warning is safe to print


class TestSkipWarningText:
    def test_the_default_message_escapes_the_file_name_and_the_reason(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        name = "evil\x1b[2J‮name.m4a"
        try:
            make_m4a(library / name)
        except OSError:
            pytest.skip("the file system does not allow these characters in a name")

        def refuse(*args: object, **kwargs: object) -> object:
            raise PermissionError(1, "denied\x1b]0;pwned‮")

        monkeypatch.setattr(recording_module, "_load", refuse)
        with pytest.warns(RecordingSkippedWarning) as caught:
            assert list(iter_recordings(library)) == []
        message = str(caught[0].message)
        assert "\x1b" not in message
        assert "‮" not in message
        assert "\\x1b" in message
        assert "\\u202e" in message


# a folder swapped for a symlink between the check and the open


class TestFolderSwap:
    @staticmethod
    def build(tmp_path: Path) -> tuple[Path, Path]:
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "manifest.plist").write_bytes(
            plistlib.dumps({"title": "OUTSIDE THE LIBRARY"})
        )
        composition = tmp_path / "lib" / "memo.composition"
        composition.mkdir(parents=True)
        (composition / "manifest.plist").write_bytes(plistlib.dumps({"title": "inside"}))
        return composition, outside_dir

    @staticmethod
    def swap_after_check(
        monkeypatch: pytest.MonkeyPatch, module: object, composition: Path, outside_dir: Path
    ) -> list[str]:
        real = module.is_real_dir  # type: ignore[attr-defined]
        swaps: list[str] = []

        def racing(path: Path) -> bool:
            ok: bool = real(path)
            if ok and path == composition:
                shutil.rmtree(composition)
                make_symlink(composition, outside_dir)
                swaps.append("swapped")
            return ok

        monkeypatch.setattr(module, "is_real_dir", racing)
        return swaps

    def test_read_manifest_does_not_follow_the_swapped_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        composition, outside_dir = self.build(tmp_path)
        swaps = self.swap_after_check(monkeypatch, transcripts, composition, outside_dir)
        assert read_manifest(composition) is None
        assert swaps == ["swapped"]

    def test_a_manifest_swapped_for_a_symlink_after_the_folder_is_open_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        composition, outside_dir = self.build(tmp_path)
        real_open_child = transcripts.open_child

        def racing(ref: object, name: str) -> object:
            (composition / name).unlink()
            make_symlink(composition / name, outside_dir / name)
            return real_open_child(ref, name)  # type: ignore[arg-type]

        monkeypatch.setattr(transcripts, "open_child", racing)
        assert read_manifest(composition) is None

    def test_open_dir_refuses_a_symlink_and_a_file(self, tmp_path: Path) -> None:
        _, outside_dir = self.build(tmp_path)
        link = tmp_path / "link"
        make_symlink(link, outside_dir)
        with pytest.raises(UnsafeFileError):
            open_dir(link)
        with pytest.raises(UnsafeFileError):
            open_dir(outside_dir / "manifest.plist")
        with pytest.raises(FileNotFoundError):
            open_dir(tmp_path / "missing")
        ref = open_dir(outside_dir)
        try:
            assert scan_dir(ref) == ([], ["manifest.plist"])
        finally:
            close_dir(ref)


# content_hash walks a hostile composition folder safely


@contextlib.contextmanager
def deep_folder(root: Path, levels: int) -> Iterator[Path]:
    """Create `levels` nested folders named `d` under `root`, and remove them afterwards.

    Paths this deep exceed the operating system limit, so the folders are made and removed one
    level at a time, relative to the current directory.
    """
    start = os.getcwd()
    root.mkdir(exist_ok=True)
    os.chdir(root)
    made = 0
    try:
        for _ in range(levels):
            os.mkdir("d")
            os.chdir("d")
            made += 1
        os.chdir(root)
        yield root
    finally:
        os.chdir(root)
        for _ in range(made):
            os.chdir("d")
        for _ in range(made):
            os.chdir("..")
            os.rmdir("d")
        os.chdir(start)


def one_recording(library: Path) -> Recording:
    return next(iter_recordings(library))


class TestContentHashWalk:
    def test_a_folder_nested_1100_levels_deep_raises_the_documented_error(
        self, library: Path
    ) -> None:
        make_m4a(library / "deep.m4a", duration=1.0)
        composition = library / "deep.composition"
        with deep_folder(composition, 1100):
            rec = one_recording(library)
            with deadline(10.0), pytest.raises(CompositionLimitError):
                content_hash(rec)

    def test_the_documented_error_is_a_voicememos_error(self) -> None:
        assert issubclass(CompositionLimitError, VoiceMemosError)

    def test_nesting_up_to_the_cap_is_hashed(self, library: Path) -> None:
        make_m4a(library / "ok.m4a", duration=1.0)
        composition = library / "ok.composition"
        with deep_folder(composition, recording_module._MAX_WALK_DEPTH):
            assert len(content_hash(one_recording(library))) == 64

    def test_more_entries_than_the_cap_raise(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "wide.m4a", duration=1.0)
        composition = library / "wide.composition"
        composition.mkdir()
        for index in range(6):
            (composition / f"f{index}").write_bytes(b"x")
        monkeypatch.setattr(recording_module, "_MAX_WALK_ENTRIES", 5)
        with pytest.raises(CompositionLimitError):
            content_hash(one_recording(library))
        monkeypatch.setattr(recording_module, "_MAX_WALK_ENTRIES", 6)
        assert len(content_hash(one_recording(library))) == 64

    def test_an_unreadable_subfolder_raises_instead_of_being_skipped(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a", duration=1.0)
        composition = library / "a.composition"
        (composition / "sub").mkdir(parents=True)
        (composition / "sub" / "inner.txt").write_bytes(b"x")
        (composition / "top.txt").write_bytes(b"y")
        rec = one_recording(library)
        real = os.scandir
        calls: list[object] = []

        def blocked_second(path: object) -> object:
            calls.append(path)
            if len(calls) == 2:
                raise PermissionError(13, "Permission denied")
            return real(path)  # type: ignore[call-overload]

        monkeypatch.setattr(os, "scandir", blocked_second)
        with pytest.raises(PermissionError):
            content_hash(rec)
        assert len(calls) == 2

    def test_descriptors_are_released_after_an_error(self, library: Path) -> None:
        make_m4a(library / "deep.m4a", duration=1.0)
        composition = library / "deep.composition"
        before = len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
        with deep_folder(composition, 80):
            rec = one_recording(library)
            with pytest.raises(CompositionLimitError):
                content_hash(rec)
        if before is not None:
            assert len(os.listdir("/proc/self/fd")) == before

    def test_the_digest_follows_the_order_of_the_sorted_relative_names(self, library: Path) -> None:
        make_m4a(library / "a.m4a", duration=1.0)
        composition = library / "a.composition"
        files = {"a.txt": b"1", "a/b.txt": b"2", "a/c/d.txt": b"3", "a-b": b"4", "z": b"5"}
        for relative, data in files.items():
            path = composition / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        hasher = hashlib.sha256()
        audio = (library / "a.m4a").read_bytes()
        hasher.update(f"audio:{len(audio)}\n".encode() + audio)
        for relative in sorted(files):
            data = files[relative]
            hasher.update(f"composition/{relative}:{len(data)}\n".encode() + data)
        assert content_hash(one_recording(library)) == hasher.hexdigest()

    def test_a_folder_swapped_for_a_symlink_after_the_check_is_not_hashed(
        self, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a", duration=1.0)
        composition = library / "a.composition"
        composition.mkdir()
        (composition / "inside.txt").write_bytes(b"inside")
        rec = one_recording(library)
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_bytes(b"outside")
        audio_only = tmp_path / "audio-only"
        audio_only.mkdir()
        shutil.copy(library / "a.m4a", audio_only / "a.m4a")
        expected = content_hash(one_recording(audio_only))
        real = recording_module.is_real_dir

        def racing(path: Path) -> bool:
            ok: bool = real(path)
            if ok and path == composition:
                shutil.rmtree(composition)
                make_symlink(composition, outside_dir)
            return ok

        monkeypatch.setattr(recording_module, "is_real_dir", racing)
        assert content_hash(rec) == expected


# output survives a terminal that cannot encode what a file name holds


class TestUndecodableOutput:
    def test_a_non_ascii_id_under_an_ascii_stream_exits_zero_without_a_traceback(
        self, library: Path
    ) -> None:
        name = "café 日本"
        try:
            make_m4a(library / f"{name}.m4a", transcript="plain words")
        except OSError:
            pytest.skip("the file system does not allow non ASCII names")
        env = {
            **os.environ,
            "PYTHONIOENCODING": "ascii",
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
        for command in (["list"], ["show", name], ["list", "--json"]):
            done = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "voicememos", *command, "--library", str(library)],
                capture_output=True,
                env=env,
                check=False,
                timeout=30,
            )
            assert done.returncode == 0, done.stderr
            assert b"Traceback" not in done.stderr
            assert done.stdout.isascii()
        text = done.stdout.decode("ascii")
        assert "\\u00e9" in text

    def test_main_reconfigures_both_streams(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, str]] = []

        class Stream:
            def __init__(self, name: str) -> None:
                self.name = name

            def reconfigure(self, *, errors: str) -> None:
                seen.append((self.name, errors))

            def write(self, text: str) -> int:
                return len(text)

            def flush(self) -> None:
                pass

        monkeypatch.setattr(sys, "stdout", Stream("stdout"))
        monkeypatch.setattr(sys, "stderr", Stream("stderr"))
        with pytest.raises(SystemExit):
            main(["--version"])
        assert ("stdout", "backslashreplace") in seen
        assert ("stderr", "backslashreplace") in seen


# listing does not decode transcripts it will discard


class TestListDoesNotDecodePayloads:
    def test_transcripts_false_never_decodes_the_tsrp_payload(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a", transcript="long words")
        decoded: list[bytes] = []
        real = transcripts.transcript_from_tsrp

        def spy(payload: bytes) -> str | None:
            decoded.append(payload)
            return real(payload)

        monkeypatch.setattr(transcripts, "transcript_from_tsrp", spy)
        lazy = next(iter_recordings(library, transcripts=False))
        assert decoded == []
        assert lazy.transcript_source == "tsrp"
        assert lazy.transcript_text is None
        full = next(iter_recordings(library))
        assert len(decoded) == 1
        assert full.transcript_text == "long words"

    def test_the_list_command_does_not_decode_payloads(
        self, library: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a", transcript="long words")

        def refuse(payload: bytes) -> str | None:
            raise AssertionError("list must not decode a transcript payload")

        monkeypatch.setattr(transcripts, "transcript_from_tsrp", refuse)
        code, out, _ = run(capsys, "list", "--library", str(library))
        assert code == 0
        assert "tsrp" in out

    def test_a_blank_payload_is_not_reported_as_a_transcript(self, library: Path) -> None:
        make_m4a(library / "a.m4a", tsrp=b"   ")
        assert next(iter_recordings(library, transcripts=False)).transcript_source is None

    def test_the_manifest_is_still_the_source_when_the_audio_has_none(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"transcript": "from the plist"})
        assert next(iter_recordings(library, transcripts=False)).transcript_source == "plist"

    def test_show_reports_the_source_it_actually_decoded(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a", tsrp=b"not json at all")
        write_manifest(library / "a.composition", {"transcript": "fallback words"})
        code, out, _ = run(capsys, "show", "a", "--library", str(library))
        assert code == 0
        assert "transcript source: plist" in out
        assert "fallback words" in out


# ids that look the same can be told apart

NFC_ID = "Café"
NFD_ID = "Café"


class TestLookAlikeIds:
    @pytest.fixture
    def twins(self, library: Path) -> Path:
        assert NFC_ID != NFD_ID
        try:
            make_m4a(library / f"{NFC_ID}.m4a")
            make_m4a(library / f"{NFD_ID}.m4a")
        except OSError:
            pytest.skip("the file system does not allow these names")
        if len(list(library.iterdir())) != 2:
            pytest.skip("the file system folds canonically equivalent names")
        return library

    def test_list_shows_both_ids_as_ascii_escapes(
        self, twins: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(capsys, "list", "--library", str(twins))
        assert code == 0
        assert ascii(NFC_ID) in out
        assert ascii(NFD_ID) in out
        assert ascii(NFC_ID) != ascii(NFD_ID)

    def test_ids_that_are_not_look_alikes_are_left_alone(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / f"{NFC_ID}.m4a")
        make_m4a(library / "plain.m4a")
        _, out, _ = run(capsys, "list", "--library", str(library))
        assert NFC_ID in out
        assert "plain" in out
        assert ascii(NFC_ID) not in out

    def test_an_ambiguous_prefix_error_tells_the_ids_apart(
        self, twins: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(capsys, "show", "Caf", "--library", str(twins))
        assert code == 1
        assert "ambiguous" in err
        assert ascii(NFC_ID) in err
        assert ascii(NFD_ID) in err

    def test_show_finds_each_twin_by_its_exact_id(
        self, twins: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for wanted in (NFC_ID, NFD_ID):
            code, out, err = run(capsys, "show", wanted, "--library", str(twins))
            assert code == 0, err
            assert f"id: {wanted}" in out


# --json is valid for a strict decoder even when a file name is not UTF-8


def assert_strictly_valid(value: object) -> None:
    """Fail if any string in a decoded document holds a lone surrogate."""
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, list):
        for item in value:
            assert_strictly_valid(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_strictly_valid(key)
            assert_strictly_valid(item)


class TestStrictJson:
    @pytest.fixture
    def bad_name(self, library: Path) -> Path:
        raw = os.fsencode(library) + b"/bad\xff\xfe.m4a"
        try:
            with open(raw, "wb") as f:
                f.write(b"\x00" * 16)
        except OSError:
            pytest.skip("the file system does not allow non UTF-8 names")
        make_m4a(library / "good.m4a")
        return library

    @pytest.mark.parametrize("command", [["list"], ["show", "bad"]])
    def test_output_has_no_lone_surrogate(
        self,
        bad_name: Path,
        capsys: pytest.CaptureFixture[str],
        command: list[str],
    ) -> None:
        code, out, err = run(capsys, *command, "--json", "--library", str(bad_name))
        assert code == 0, err
        assert_strictly_valid(strict_json(out))
        assert "\\udcff" not in out
        assert "\\udcfe" not in out

    def test_the_id_bytes_are_given_as_hex(
        self, bad_name: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = run(capsys, "list", "--library", str(bad_name), "--json")
        data = strict_json(out)
        assert isinstance(data, list)
        by_hex = [item for item in data if "id_bytes_hex" in item]
        assert [item["id_bytes_hex"] for item in by_hex] == [b"bad\xff\xfe".hex()]
        assert by_hex[0]["id"].startswith("bad")
        good = next(item for item in data if item["id"] == "good")
        assert "id_bytes_hex" not in good

    def test_a_valid_id_has_no_hex_field(self) -> None:
        moment = datetime(2024, 1, 1, tzinfo=UTC)
        rec = Recording("ok", Path("/x/ok.m4a"), None, moment, None, "t", None, None)
        assert "id_bytes_hex" not in rec.to_dict()

    def test_to_dict_adds_the_hex_for_an_undecodable_id(self) -> None:
        moment = datetime(2024, 1, 1, tzinfo=UTC)
        name = os.fsdecode(b"bad\xff")
        rec = Recording(name, Path(name), None, moment, None, "t", None, None)
        assert rec.to_dict()["id_bytes_hex"] == b"bad\xff".hex()

    def test_a_lone_surrogate_in_a_transcript_is_replaced_in_json(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = b'{"attributedString": {"runs": ["bad \\ud800 text", 0]}}'
        make_m4a(library / "a.m4a", tsrp=payload)
        code, out, err = run(capsys, "show", "a", "--json", "--library", str(library))
        assert code == 0, err
        data = strict_json(out)
        assert_strictly_valid(data)
        assert "\\ud800" not in out
        assert "bad" in data["transcript"]  # type: ignore[index]


# the walk and the openers on a platform without descriptor relative opens, and on a vanishing tree


class TestPathFallbackAndVanishingEntries:
    @pytest.fixture
    def no_descriptors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("voicememos.safeio.SUPPORTS_DIR_FD", False)

    def test_open_dir_falls_back_to_paths(self, tmp_path: Path, no_descriptors: None) -> None:
        folder = tmp_path / "real"
        folder.mkdir()
        (folder / "inner").mkdir()
        link = tmp_path / "link"
        make_symlink(link, folder)
        assert open_dir(folder) == folder
        assert open_dir("inner", parent=folder) == folder / "inner"
        with pytest.raises(UnsafeFileError):
            open_dir(link)
        with pytest.raises(FileNotFoundError):
            open_dir(tmp_path / "missing")
        close_dir(folder)

    def test_the_manifest_and_the_hash_still_work(
        self, library: Path, no_descriptors: None
    ) -> None:
        make_m4a(library / "a.m4a", duration=1.0)
        write_manifest(library / "a.composition", {"title": "A"})
        (library / "a.composition" / "sub").mkdir()
        (library / "a.composition" / "sub" / "x.txt").write_bytes(b"x")
        rec = one_recording(library)
        assert rec.title == "A"
        assert len(content_hash(rec)) == 64

    def test_a_file_that_vanishes_during_the_walk_is_skipped(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / "a.m4a", duration=1.0)
        composition = library / "a.composition"
        (composition / "sub").mkdir(parents=True)
        (composition / "sub" / "x.txt").write_bytes(b"x")
        (composition / "y.txt").write_bytes(b"y")
        rec = one_recording(library)
        before = content_hash(rec)
        real_dir, real_child = recording_module.open_dir, recording_module.open_child

        def gone_dir(name: object, **kwargs: object) -> object:
            if name == "sub":
                raise FileNotFoundError(2, "gone")
            return real_dir(name, **kwargs)  # type: ignore[arg-type]

        def gone_file(ref: object, name: str) -> object:
            if name == "y.txt":
                raise FileNotFoundError(2, "gone")
            return real_child(ref, name)  # type: ignore[arg-type]

        monkeypatch.setattr(recording_module, "open_dir", gone_dir)
        monkeypatch.setattr(recording_module, "open_child", gone_file)
        assert content_hash(rec) != before
        assert len(content_hash(rec)) == 64

    def test_a_stream_that_refuses_to_reconfigure_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Stubborn:
            def reconfigure(self, *, errors: str) -> None:
                raise ValueError(errors)

            def write(self, text: str) -> int:
                return len(text)

            def flush(self) -> None:
                pass

        class Plain:
            def write(self, text: str) -> int:
                return len(text)

            def flush(self) -> None:
                pass

        monkeypatch.setattr(sys, "stdout", Stubborn())
        monkeypatch.setattr(sys, "stderr", Plain())
        with pytest.raises(SystemExit):
            main(["--version"])


# a composition root that cannot be listed does not leak its descriptor


def open_descriptors() -> int:
    return len(os.listdir("/proc/self/fd"))


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="needs /proc to count descriptors")
class TestUnlistableRootDoesNotLeak:
    def test_a_listing_failure_closes_the_root_descriptor(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=1.0)
        (library / f"{STEM}.composition").mkdir()
        rec = next(iter_recordings(library))

        def fail(ref: object) -> object:
            raise OSError(5, "I/O error")

        monkeypatch.setattr(recording_module, "scan_dir", fail)
        before = open_descriptors()
        for _ in range(20):
            with pytest.raises(OSError, match="I/O error"):
                content_hash(rec)
        assert open_descriptors() == before


# a file name that is not UTF-8 is hashed, not a crash


PINNED_DIGEST = "be0f8030bbf24239985bd3342051a0884df6b725ae2ddc9681e0381707949d96"


class TestUndecodableNamesInComposition:
    def test_the_digest_of_valid_names_is_pinned(self, library: Path) -> None:
        make_m4a(library / "m.m4a", duration=1.0)
        folder = library / "m.composition"
        (folder / "sub").mkdir(parents=True)
        (folder / "a.bin").write_bytes(b"x")
        (folder / "sub" / "café.bin").write_bytes(b"yy")
        assert content_hash(next(iter_recordings(library))) == PINNED_DIGEST

    def test_names_that_differ_only_in_an_invalid_byte_give_different_digests(
        self, library: Path
    ) -> None:
        make_m4a(library / "m.m4a", duration=1.0)
        folder = os.fsencode(library / "m.composition")
        os.mkdir(folder)
        digests = []
        for raw in (b"\xff.bin", b"\xfe.bin"):
            for old in os.listdir(folder):
                os.unlink(os.path.join(folder, old))
            try:
                with open(os.path.join(folder, raw), "wb") as f:
                    f.write(b"x")
            except OSError:
                pytest.skip("the file system does not allow names that are not UTF-8")
            digests.append(content_hash(next(iter_recordings(library))))
        assert all(len(d) == 64 for d in digests)
        assert digests[0] != digests[1]

    def test_the_label_uses_the_original_bytes_of_the_name(self, library: Path) -> None:
        make_m4a(library / "m.m4a", duration=1.0)
        folder = os.fsencode(library / "m.composition")
        os.mkdir(folder)
        try:
            with open(os.path.join(folder, b"\xff.bin"), "wb") as f:
                f.write(b"x")
        except OSError:
            pytest.skip("the file system does not allow names that are not UTF-8")
        audio = (library / "m.m4a").read_bytes()
        expected = hashlib.sha256()
        expected.update(b"audio:%d\n" % len(audio) + audio)
        expected.update(b"composition/\xff.bin:1\nx")
        assert content_hash(next(iter_recordings(library))) == expected.hexdigest()


# a composition folder that may be searched but not listed still yields its manifest


def deny_listing(monkeypatch: pytest.MonkeyPatch, code: int = errno.EACCES) -> None:
    """Make opening the composition folder fail as a folder with mode 0311 does.

    The suite runs as root, which can open any folder, so the failure is simulated.
    """
    real = transcripts.open_dir

    def deny(path: object, **kwargs: object) -> object:
        if kwargs.get("parent") is None:
            raise PermissionError(code, os.strerror(code))
        return real(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(transcripts, "open_dir", deny)


class TestSearchOnlyCompositionFolder:
    def test_the_manifest_is_read_by_path_when_the_folder_cannot_be_opened(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_manifest(library / "m.composition", {"title": "Kept"})
        deny_listing(monkeypatch)
        manifest = read_manifest(library / "m.composition")
        assert manifest is not None
        assert manifest["title"] == "Kept"

    def test_the_recording_is_listed_with_its_manifest_title(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=1.0)
        write_manifest(library / f"{STEM}.composition", {"title": "Kept"})
        deny_listing(monkeypatch)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            recordings = list(iter_recordings(library))
        assert [r.title for r in recordings] == ["Kept"]

    def test_a_symlinked_manifest_is_still_refused_on_the_fallback(
        self, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = tmp_path / "outside.plist"
        outside.write_bytes(plistlib.dumps({"title": "Outside"}))
        folder = library / "m.composition"
        folder.mkdir()
        (folder / "manifest.plist").symlink_to(outside)
        deny_listing(monkeypatch)
        assert read_manifest(folder) is None

    def test_a_missing_manifest_is_absent_on_the_fallback(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (library / "m.composition").mkdir()
        deny_listing(monkeypatch)
        assert read_manifest(library / "m.composition") is None

    def test_a_refusal_that_is_not_access_denied_still_raises(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_manifest(library / "m.composition", {"title": "Kept"})
        deny_listing(monkeypatch, errno.EPERM)
        with pytest.raises(PermissionError):
            read_manifest(library / "m.composition")

    def test_a_readable_folder_still_opens_the_manifest_through_the_descriptor(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_manifest(library / "m.composition", {"title": "Kept"})
        paths: list[object] = []
        real = transcripts.open_regular

        def spy(path: object, **kwargs: object) -> object:
            paths.append(path)
            return real(path, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(transcripts, "open_regular", spy, raising=False)
        assert read_manifest(library / "m.composition") == {"title": "Kept"}
        assert paths == []


# every Default_Ignorable_Code_Point, unassigned, private use and noncharacter code point is escaped

# The Default_Ignorable_Code_Point ranges of Unicode 15.0 (DerivedCoreProperties.txt). The module
# under test keeps its own copy; this one is written out again so that a slip in one shows up.
DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
NONCHARACTERS = [
    *range(0xFDD0, 0xFDF0),
    *(plane + low for plane in range(0, 0x110000, 0x10000) for low in (0xFFFE, 0xFFFF)),
]
SAMPLED_UNASSIGNED = [
    0x0378,
    0x0380,
    0x2065,
    0x2FE0,
    0x1FFFF,
    0x2FA20,
    0xE00FF,
    0xE01F0,
    0x3FFFD,
    0xDFFFF,
]
SAMPLED_PRIVATE_USE = [0xE000, 0xF8FF, 0xF0000, 0xFFFFD, 0x100000, 0x10FFFD]
CONTEXT_DEPENDENT = {0xFE0E, 0xFE0F, 0x200D}


def escaped(code: int) -> bool:
    text = "a" + chr(code) + "b"
    out = printable(text)
    return out != text and chr(code) not in out and out.isascii()


class TestEveryInvisibleOrUndefinedCodePoint:
    def test_every_default_ignorable_code_point_is_escaped(self) -> None:
        missed = [
            hex(code)
            for low, high in DEFAULT_IGNORABLE_RANGES
            for code in range(low, high + 1)
            if code not in CONTEXT_DEPENDENT and not escaped(code)
        ]
        assert not missed, missed[:20]

    @pytest.mark.parametrize(
        "code",
        [0x17B4, 0x17B5, 0x180F, 0x2065, 0xFFF0, 0xFFF8, 0xE0080, 0xE00FF, 0xE01F0, 0xE0FFF],
        ids=hex,
    )
    def test_the_ranges_that_were_missed_before(self, code: int) -> None:
        assert escaped(code)

    def test_every_noncharacter_is_escaped(self) -> None:
        assert len(NONCHARACTERS) == 66
        missed = [hex(code) for code in NONCHARACTERS if not escaped(code)]
        assert not missed, missed

    @pytest.mark.parametrize("code", SAMPLED_UNASSIGNED, ids=hex)
    def test_an_unassigned_code_point_is_escaped(self, code: int) -> None:
        assert unicodedata.category(chr(code)) == "Cn"
        assert escaped(code)

    @pytest.mark.parametrize("code", SAMPLED_PRIVATE_USE, ids=hex)
    def test_a_private_use_code_point_is_escaped(self, code: int) -> None:
        assert unicodedata.category(chr(code)) == "Co"
        assert escaped(code)

    def test_no_code_point_in_a_checked_category_gets_through(self) -> None:
        checked = {"Cc", "Cf", "Cn", "Co", "Zl", "Zp"}
        missed = [
            hex(code)
            for code in range(0x110000)
            if not 0xD800 <= code <= 0xDFFF
            and code not in CONTEXT_DEPENDENT
            and unicodedata.category(chr(code)) in checked
            and not escaped(code)
        ]
        assert not missed, missed[:20]

    def test_assigned_letters_marks_and_symbols_are_left_alone(self) -> None:
        text = "A é 日本 ß ́ ☃ € ‰ Ω ๑ ، ◌"
        assert printable(text) == text


# emoji keep the selector and the joiner that make them, and nothing else does

ZWJ = "‍"
VS15 = "︎"
VS16 = "️"


class TestEmojiSequences:
    @pytest.mark.parametrize(
        "text",
        [
            "❤️",  # heart, VS16
            "☃︎",  # snowman, VS15 (text presentation)
            "™️",  # trade mark sign, VS16
            "👨‍👩‍👧",  # family: man, ZWJ, woman, ZWJ, girl
            "🏃‍♀️",  # runner, ZWJ, female sign, VS16
            "❤️‍🔥",  # heart, VS16, ZWJ, fire
            "👍🏽",  # thumbs up with a skin tone, no selector
            "1️⃣",  # keycap one
            "#️⃣",  # keycap number sign
            "🇯🇵",  # flag, two regional indicators
            "I ❤️ 日本 👨‍👩‍👧 ok",
        ],
        ids=lambda s: "-".join(f"{ord(c):x}" for c in s)[:40],
    )
    def test_a_real_emoji_prints_unchanged(self, text: str) -> None:
        assert printable(text) == text

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (VS16 + "abc", "\\ufe0fabc"),  # leading
            ("a" + VS16, "a\\ufe0f"),  # after a non-emoji
            ("日" + VS16, "日\\ufe0f"),
            ("1" + VS16, "1\\ufe0f"),  # a digit without the keycap
            ("❤" + VS16 + VS16, "❤" + VS16 + "\\ufe0f"),  # repeated
            ("❤" + VS16 + VS15, "❤" + VS16 + "\\ufe0e"),
            ("❤" + "︀", "❤\\ufe00"),  # other selectors are never kept
            ("❤" + "\U000e0100", "❤\\U000e0100"),
            ("᠋", "\\u180b"),
            (ZWJ + "❤", "\\u200d❤"),  # leading
            ("❤" + ZWJ, "❤\\u200d"),  # trailing
            ("a" + ZWJ + "b", "a\\u200db"),
            ("a" + ZWJ + "❤", "a\\u200d❤"),  # next to a non-emoji
            ("❤" + ZWJ + "a", "❤\\u200da"),
            ("❤" + ZWJ + ZWJ + "🔥", "❤\\u200d\\u200d🔥"),  # repeated
            ("❤" + VS16 + VS16 + ZWJ + "🔥", "❤" + VS16 + "\\ufe0f\\u200d🔥"),
            (ZWJ, "\\u200d"),
            (VS16, "\\ufe0f"),
        ],
        ids=lambda v: "-".join(f"{ord(c):x}" for c in v)[:40] if isinstance(v, str) else None,
    )
    def test_an_unattached_selector_or_joiner_is_escaped(self, text: str, expected: str) -> None:
        assert printable(text) == expected

    def test_nothing_hides_in_a_run_of_selectors(self) -> None:
        # One selector may follow an emoji. A longer run is how a payload would be carried.
        payload = "❤" + "".join(VS16 if bit else VS15 for bit in (1, 0, 1, 1, 0, 0, 1, 0))
        out = printable(payload)
        assert out.count("\\ufe0") == 7
        assert out[0] == "❤"
        assert sum(ch in {VS15, VS16} for ch in out) == 1

    def test_the_other_unsafe_characters_are_still_escaped_inside_an_emoji_run(self) -> None:
        assert printable("❤️‮❤️") == "❤️\\u202e❤️"
        assert printable("👨" + ZWJ + "⁠" + "👩") == "👨\\u200d\\u2060👩"
        assert printable("❤️\x1b❤️") == "❤️\\x1b❤️"

    def test_keep_newlines_still_applies_in_text_with_emoji(self) -> None:
        assert printable("❤️\n👨‍👩‍👧\r", keep_newlines=True) == "❤️\n👨‍👩‍👧\\r"

    def test_show_prints_an_emoji_title_unchanged(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"title": "I ❤️ 👨‍👩‍👧"})
        code, out, err = run(capsys, "show", STEM, "--library", str(library))
        assert code == 0, err
        assert "title: I ❤️ 👨‍👩‍👧\n" in out


# the check costs little on text that needs no escape


def reference_before_the_invisible_character_fix(text: str) -> str:
    """The per character loop `printable` used before it escaped invisible characters."""
    out = []
    for ch in text:
        code = ord(ch)
        if code < 0x20 or 0x7F <= code <= 0x9F or code in _OLD_FORMAT_CHARS:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    return "".join(out)


_OLD_FORMAT_CHARS = frozenset(
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
    | {0xFEFF}
)


class TestEscapingSpeed:
    def test_cjk_text_costs_no_more_than_one_and_a_half_times_the_old_loop(self) -> None:
        text = "日本語のメモ漢字" * 250_000
        timings = {}
        for name, function in (
            ("old", reference_before_the_invisible_character_fix),
            ("new", printable),
        ):
            best = float("inf")
            for _ in range(3):
                start = time.perf_counter()
                result = function(text)
                best = min(best, time.perf_counter() - start)
            assert result == text
            timings[name] = best
        assert timings["new"] <= 1.5 * timings["old"], timings

    def test_text_with_one_joiner_is_not_scanned_character_by_character(self) -> None:
        text = "日本語のメモ漢字" * 250_000 + "❤" + ZWJ + "🔥"
        start = time.perf_counter()
        out = printable(text)
        elapsed = time.perf_counter() - start
        assert out == text
        assert elapsed < 1.0

"""Regression tests for hostile input: files in a library are written by other programs.

Each test builds a small synthetic input. Tests that would hang or run for a very long time
without the fix run under a deadline, so they fail fast instead.
"""

from __future__ import annotations

import contextlib
import json
import os
import plistlib
import signal
import struct
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.synthetic import box, make_m4a, mvhd, write_manifest
from voicememos import mp4, transcripts
from voicememos import recording as recording_module
from voicememos.cli import _dump, main
from voicememos.errors import RecordingSkippedWarning, UnsafeFileError
from voicememos.mp4 import read_duration_seconds, read_tsrp_payload
from voicememos.recording import Recording, content_hash, iter_recordings, local_time
from voicememos.safeio import is_real_dir, open_regular
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
        if str(path).endswith("b.composition/manifest.plist"):
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

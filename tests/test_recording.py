"""Tests for Recording, iter_recordings, read_transcript and content_hash."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.synthetic import make_m4a, write_manifest
from voicememos import recording as recording_module
from voicememos.errors import LibraryBlockedError, LibraryNotFoundError, VoiceMemosError
from voicememos.recording import (
    Recording,
    Transcript,
    content_hash,
    iter_recordings,
    read_transcript,
)

STEM = "20250115 143022-ABCD1234"

needs_non_root = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a directory with mode 000 is still listable by root",
)


@pytest.fixture
def set_timezone() -> Iterator[Callable[[str], None]]:
    """Return a function that sets the local timezone, restored when the test ends."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    with pytest.MonkeyPatch.context() as patch:

        def apply(name: str) -> None:
            patch.setenv("TZ", name)
            time.tzset()

        yield apply
    time.tzset()


@pytest.fixture
def utc_timezone(set_timezone: Callable[[str], None]) -> None:
    """Run the test with the local timezone set to UTC."""
    set_timezone("UTC")


def one(library: Path) -> Recording:
    recordings = list(iter_recordings(library))
    assert len(recordings) == 1
    return recordings[0]


class TestRecordingModel:
    def make(self, **overrides: object) -> Recording:
        fields: dict[str, object] = {
            "id": "x",
            "audio_path": Path("x.m4a"),
            "composition_path": None,
            "recorded_at": datetime(2025, 1, 15, 14, 30, tzinfo=UTC),
            "duration_seconds": 3.0,
            "title": "T",
            "transcript_text": None,
            "transcript_source": None,
        }
        fields.update(overrides)
        return Recording(**fields)  # type: ignore[arg-type]

    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone aware"):
            self.make(recorded_at=datetime(2025, 1, 15, 14, 30))

    def test_aware_datetime_is_kept(self) -> None:
        zone = timezone(timedelta(hours=-8))
        moment = datetime(2025, 1, 15, 14, 30, tzinfo=zone)
        assert self.make(recorded_at=moment).recorded_at == moment

    def test_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            self.make().title = "other"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        rec = self.make(
            composition_path=Path("x.composition"),
            transcript_text="hello",
            transcript_source="tsrp",
        )
        assert rec.to_dict() == {
            "id": "x",
            "audio_path": "x.m4a",
            "composition_path": "x.composition",
            "recorded_at": "2025-01-15T14:30:00+00:00",
            "duration_seconds": 3.0,
            "title": "T",
            "transcript_source": "tsrp",
            "transcript": "hello",
        }

    def test_to_dict_without_transcript(self) -> None:
        data = self.make(transcript_text="hello").to_dict(include_transcript=False)
        assert "transcript" not in data
        assert data["composition_path"] is None


class TestIterRecordings:
    def test_empty_library(self, library: Path) -> None:
        assert list(iter_recordings(library)) == []

    def test_full_recording_from_the_manifest(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=99.0)
        write_manifest(
            library / f"{STEM}.composition",
            {
                "title": "Grocery list",
                "duration": 12.5,
                "creationDate": datetime(2025, 3, 1, 9, 0, 0),
                "transcript": "milk eggs bread",
            },
        )
        rec = one(library)
        assert rec.id == STEM
        assert rec.audio_path == library / f"{STEM}.m4a"
        assert rec.composition_path == library / f"{STEM}.composition"
        assert rec.recorded_at == datetime(2025, 3, 1, 9, 0, 0, tzinfo=UTC)
        assert rec.recorded_at.tzinfo is not None
        assert rec.duration_seconds == 12.5
        assert rec.title == "Grocery list"
        assert rec.transcript_text == "milk eggs bread"
        assert rec.transcript_source == "plist"

    def test_audio_only_uses_the_file_name_and_the_mp4_header(
        self, library: Path, utc_timezone: None
    ) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=61.0, transcript="from the audio")
        rec = one(library)
        assert rec.composition_path is None
        assert rec.recorded_at == datetime(2025, 1, 15, 14, 30, 22, tzinfo=UTC)
        assert rec.duration_seconds == pytest.approx(61.0)
        assert rec.transcript_text == "from the audio"
        assert rec.transcript_source == "tsrp"

    def test_filename_time_is_read_as_local_time(
        self, library: Path, set_timezone: Callable[[str], None]
    ) -> None:
        set_timezone("Etc/GMT+8")
        make_m4a(library / f"{STEM}.m4a")
        rec = one(library)
        assert rec.recorded_at == datetime(2025, 1, 15, 22, 30, 22, tzinfo=UTC)

    def test_tsrp_wins_over_the_manifest(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a", transcript="audio words")
        write_manifest(library / f"{STEM}.composition", {"transcript": "plist words"})
        rec = one(library)
        assert (rec.transcript_text, rec.transcript_source) == ("audio words", "tsrp")

    def test_no_transcript(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"title": "Quiet"})
        rec = one(library)
        assert rec.transcript_text is None
        assert rec.transcript_source is None

    def test_custom_label_is_the_second_choice_title(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"title": "  ", "customLabel": "Label"})
        assert one(library).title == "Label"

    def test_fallback_title_comes_from_the_recording_date(
        self, library: Path, utc_timezone: None
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        assert one(library).title == "Voice Memo Jan 15, 2025 2:30:22 PM"

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [(0, "12:05:09 AM"), (9, "9:05:09 AM"), (12, "12:05:09 PM"), (23, "11:05:09 PM")],
    )
    def test_fallback_title_clock(self, hour: int, expected: str) -> None:
        moment = datetime(2025, 8, 9, hour, 5, 9)
        assert recording_module._fallback_title(moment) == f"Voice Memo Aug 9, 2025 {expected}"

    def test_composition_without_a_manifest_still_pairs(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        (library / f"{STEM}.composition").mkdir()
        rec = one(library)
        assert rec.composition_path == library / f"{STEM}.composition"
        assert rec.transcript_text is None

    def test_stray_files_and_folders_are_ignored(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        (library / "notes.txt").write_text("x")
        (library / "CloudRecordings.db").write_bytes(b"x")
        (library / "dir.m4a").mkdir()
        (library / "orphan.composition").mkdir()
        assert [r.id for r in iter_recordings(library)] == ["a"]

    def test_results_are_in_file_name_order(self, library: Path) -> None:
        for stem in ("c", "a", "b"):
            make_m4a(library / f"{stem}.m4a")
        assert [r.id for r in iter_recordings(library)] == ["a", "b", "c"]

    def test_name_with_a_space_in_the_id(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        assert one(library).id == "20250115 143022-ABCD1234"

    def test_accepts_str_and_tilde(self, fake_home: Path) -> None:
        folder = fake_home / "Rec"
        folder.mkdir()
        make_m4a(folder / "a.m4a")
        assert [r.id for r in iter_recordings("~/Rec")] == ["a"]
        assert [r.id for r in iter_recordings(str(folder))] == ["a"]

    def test_unparseable_stem_falls_back_to_the_file_time(self, library: Path) -> None:
        audio = make_m4a(library / "plain-name.m4a")
        os.utime(audio, (1_700_000_000, 1_700_000_000))
        rec = one(library)
        assert rec.recorded_at.tzinfo is not None
        assert rec.recorded_at == datetime.fromtimestamp(
            recording_module._timestamp(audio.stat()), tz=UTC
        )

    def test_impossible_date_in_the_stem_falls_back_to_the_file_time(self, library: Path) -> None:
        audio = make_m4a(library / "20251345 143022-ABCD.m4a")
        os.utime(audio, (1_700_000_000, 1_700_000_000))
        rec = one(library)
        assert rec.recorded_at == datetime.fromtimestamp(
            recording_module._timestamp(audio.stat()), tz=UTC
        )

    @pytest.mark.parametrize("value", [True, "12", -1, None])
    def test_unusable_manifest_durations_fall_back_to_the_header(
        self, library: Path, value: object
    ) -> None:
        make_m4a(library / f"{STEM}.m4a", duration=7.0)
        data: dict[str, object] = {} if value is None else {"duration": value}
        write_manifest(library / f"{STEM}.composition", data)
        assert one(library).duration_seconds == pytest.approx(7.0)

    def test_duration_is_none_when_nothing_knows_it(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        assert one(library).duration_seconds is None

    def test_manifest_duration_as_an_integer(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"duration": 30})
        assert one(library).duration_seconds == 30.0

    def test_manifest_date_is_utc_aware(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(
            library / f"{STEM}.composition",
            {"creationDate": datetime(2025, 5, 5, 3, 5)},
        )
        rec = one(library)
        assert rec.recorded_at == datetime(2025, 5, 5, 3, 5, tzinfo=UTC)
        assert rec.recorded_at.utcoffset() == timedelta(0)

    def test_naive_manifest_date_is_read_as_utc(self, library: Path) -> None:
        audio = make_m4a(library / f"{STEM}.m4a")
        naive = {"creationDate": datetime(2025, 5, 5, 3, 5)}
        assert recording_module._recorded_at(audio, STEM, naive) == datetime(
            2025, 5, 5, 3, 5, tzinfo=UTC
        )
        zone = timezone(timedelta(hours=2))
        aware = {"creationDate": datetime(2025, 5, 5, 5, 5, tzinfo=zone)}
        assert recording_module._recorded_at(audio, STEM, aware) == datetime(
            2025, 5, 5, 3, 5, tzinfo=UTC
        )

    def test_non_date_creation_value_falls_back_to_the_stem(
        self, library: Path, utc_timezone: None
    ) -> None:
        make_m4a(library / f"{STEM}.m4a")
        write_manifest(library / f"{STEM}.composition", {"creationDate": "yesterday"})
        assert one(library).recorded_at == datetime(2025, 1, 15, 14, 30, 22, tzinfo=UTC)

    def test_corrupt_manifest_is_treated_as_absent(self, library: Path) -> None:
        make_m4a(library / f"{STEM}.m4a", transcript="audio words")
        composition = library / f"{STEM}.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(b"garbage")
        rec = one(library)
        assert rec.transcript_source == "tsrp"

    def test_listing_is_eager_for_errors(self, tmp_path: Path) -> None:
        with pytest.raises(LibraryNotFoundError):
            iter_recordings(tmp_path / "missing")

    def test_missing_library(self, tmp_path: Path) -> None:
        with pytest.raises(LibraryNotFoundError, match="not found") as info:
            iter_recordings(tmp_path / "missing")
        assert isinstance(info.value, FileNotFoundError)
        assert isinstance(info.value, VoiceMemosError)

    def test_library_that_is_a_file(self, tmp_path: Path) -> None:
        target = tmp_path / "file"
        target.write_text("x")
        with pytest.raises(LibraryNotFoundError):
            iter_recordings(target)

    def test_blocked_library_mocked(self, library: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mocked, so it also runs as root."""

        def deny(path: object) -> object:
            raise PermissionError(1, "Operation not permitted")

        monkeypatch.setattr(os, "scandir", deny)
        with pytest.raises(LibraryBlockedError, match="cannot be listed") as info:
            iter_recordings(library)
        assert isinstance(info.value, PermissionError)
        assert isinstance(info.value, VoiceMemosError)

    def test_blocked_library_with_an_error_that_has_no_text(
        self, library: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def deny(path: object) -> object:
            raise OSError()

        monkeypatch.setattr(os, "scandir", deny)
        with pytest.raises(LibraryBlockedError):
            iter_recordings(library)

    @needs_non_root
    def test_real_permission_denied_library(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        library.chmod(0o000)
        try:
            with pytest.raises(LibraryBlockedError):
                iter_recordings(library)
        finally:
            library.chmod(0o755)


class TestTimestamp:
    def test_prefers_birth_time(self) -> None:
        st = SimpleNamespace(st_birthtime=100.0, st_mtime=200.0)
        assert recording_module._timestamp(st) == 100.0

    def test_integer_birth_time(self) -> None:
        st = SimpleNamespace(st_birthtime=100, st_mtime=200.0)
        assert recording_module._timestamp(st) == 100.0

    def test_falls_back_to_mtime_when_there_is_no_birth_time(self) -> None:
        """Linux stat results have no st_birthtime."""
        assert recording_module._timestamp(SimpleNamespace(st_mtime=200.0)) == 200.0

    def test_falls_back_to_mtime_when_birth_time_is_not_a_number(self) -> None:
        st = SimpleNamespace(st_birthtime=None, st_mtime=200.0)
        assert recording_module._timestamp(st) == 200.0


class TestReadTranscript:
    def test_returns_text_and_source(self, library: Path) -> None:
        make_m4a(library / "a.m4a", transcript="hello there")
        assert read_transcript(one(library)) == Transcript("hello there", "tsrp")

    def test_reads_the_manifest_when_the_audio_has_none(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"speechTranscript": {"segments": ["x", "y"]}})
        assert read_transcript(one(library)) == Transcript("x y", "plist")

    def test_none_without_a_transcript(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        assert read_transcript(one(library)) is None

    def test_reflects_the_files_as_they_are_now(self, library: Path) -> None:
        audio = make_m4a(library / "a.m4a")
        rec = one(library)
        assert read_transcript(rec) is None
        make_m4a(audio, transcript="added later")
        assert read_transcript(rec) == Transcript("added later", "tsrp")


class TestContentHash:
    def test_is_a_sha256_hex_digest(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        digest = content_hash(one(library))
        assert len(digest) == 64
        int(digest, 16)

    def test_is_stable(self, library: Path) -> None:
        make_m4a(library / "a.m4a", transcript="same")
        write_manifest(library / "a.composition", {"title": "T"})
        rec = one(library)
        assert content_hash(rec) == content_hash(rec)

    def test_audio_change_changes_the_hash(self, library: Path) -> None:
        audio = make_m4a(library / "a.m4a", transcript="one")
        before = content_hash(one(library))
        make_m4a(audio, transcript="two")
        assert content_hash(one(library)) != before

    def test_composition_change_changes_the_hash(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        manifest = write_manifest(library / "a.composition", {"title": "One"})
        before = content_hash(one(library))
        write_manifest(manifest.parent, {"title": "Two"})
        assert content_hash(one(library)) != before

    def test_new_composition_file_changes_the_hash(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "One"})
        before = content_hash(one(library))
        (library / "a.composition" / "extra.bin").write_bytes(b"1")
        assert content_hash(one(library)) != before

    def test_nested_composition_files_are_included(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "One"})
        nested = library / "a.composition" / "sub"
        nested.mkdir()
        before = content_hash(one(library))
        (nested / "f.bin").write_bytes(b"1")
        assert content_hash(one(library)) != before

    def test_file_name_matters(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        composition = library / "a.composition"
        composition.mkdir()
        (composition / "one.bin").write_bytes(b"data")
        before = content_hash(one(library))
        (composition / "one.bin").rename(composition / "two.bin")
        assert content_hash(one(library)) != before

    def test_modification_time_does_not_matter(self, library: Path) -> None:
        audio = make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "T"})
        before = content_hash(one(library))
        os.utime(audio, (1_000_000_000, 1_000_000_000))
        os.utime(library / "a.composition" / "manifest.plist", (1_000_000_000, 1_000_000_000))
        assert content_hash(one(library)) == before

    def test_recording_without_a_composition(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        rec = one(library)
        assert rec.composition_path is None
        assert len(content_hash(rec)) == 64

    def test_missing_audio_raises(self, library: Path) -> None:
        audio = make_m4a(library / "a.m4a")
        rec = one(library)
        audio.unlink()
        with pytest.raises(FileNotFoundError):
            content_hash(rec)

    def test_vanished_composition_is_skipped(self, library: Path) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "T"})
        rec = one(library)
        (library / "a.composition" / "manifest.plist").unlink()
        (library / "a.composition").rmdir()
        assert len(content_hash(rec)) == 64

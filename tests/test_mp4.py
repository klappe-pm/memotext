"""Tests for the MP4 box reader."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from tests.synthetic import box, large_box, make_m4a, mvhd, tsrp_payload
from voicememos import mp4
from voicememos.mp4 import read_duration_seconds, read_tsrp_payload

PAYLOAD = b'{"hello": "world"}'


class TestReadDuration:
    def test_version_0_header(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", duration=12.5)
        assert read_duration_seconds(audio) == pytest.approx(12.5)

    def test_version_1_header(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(box(b"ftyp", b"M4A ") + box(b"moov", mvhd(90.0, 44100, version=1)))
        assert read_duration_seconds(audio) == pytest.approx(90.0)

    def test_none_without_a_movie_header(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a")
        assert read_duration_seconds(audio) is None

    def test_none_without_moov(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(box(b"ftyp", b"M4A ") + box(b"mdat", b"\x00" * 16))
        assert read_duration_seconds(audio) is None

    def test_none_for_zero_timescale(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        body = struct.pack(">B3xIIII", 0, 0, 0, 0, 100) + bytes(80)
        audio.write_bytes(box(b"moov", box(b"mvhd", body)))
        assert read_duration_seconds(audio) is None

    def test_none_for_unknown_version(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        body = struct.pack(">B3xIIII", 7, 0, 0, 1000, 100) + bytes(80)
        audio.write_bytes(box(b"moov", box(b"mvhd", body)))
        assert read_duration_seconds(audio) is None

    def test_none_for_short_header(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(box(b"moov", box(b"mvhd", b"\x00\x00\x00\x00\x00\x00")))
        assert read_duration_seconds(audio) is None

    def test_none_for_empty_header_payload(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(box(b"moov", box(b"mvhd")))
        assert read_duration_seconds(audio) is None

    @pytest.mark.parametrize("content", [b"", b"abc", b"\x00" * 7, b"\xff" * 64])
    def test_none_for_garbage(self, tmp_path: Path, content: bytes) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(content)
        assert read_duration_seconds(audio) is None

    def test_none_for_truncated_file(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", duration=5.0)
        data = audio.read_bytes()
        audio.write_bytes(data[:30])
        assert read_duration_seconds(audio) is None

    def test_none_for_missing_file_and_directory(self, tmp_path: Path) -> None:
        assert read_duration_seconds(tmp_path / "nope.m4a") is None
        assert read_duration_seconds(tmp_path) is None

    def test_permission_error_is_not_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio = make_m4a(tmp_path / "a.m4a", duration=1.0)

        def deny(*args: object, **kwargs: object) -> object:
            raise PermissionError(1, "Operation not permitted")

        monkeypatch.setattr(os, "open", deny)
        with pytest.raises(PermissionError):
            read_duration_seconds(audio)


class TestBoxHeaders:
    def test_header_past_the_end_of_the_file_is_unreadable(self, tmp_path: Path) -> None:
        path = tmp_path / "a.bin"
        path.write_bytes(b"\x00\x00\x00")
        with path.open("rb") as f:
            assert mp4._parse_header(f, 0, 100) is None

    def test_truncated_64_bit_size_is_unreadable(self, tmp_path: Path) -> None:
        path = tmp_path / "a.bin"
        path.write_bytes(struct.pack(">I4s", 1, b"moov") + b"\x00\x00\x00\x00")
        with path.open("rb") as f:
            assert mp4._parse_header(f, 0, 12) is None

    def test_declared_size_past_the_end_is_clamped_and_flagged(self, tmp_path: Path) -> None:
        path = tmp_path / "a.bin"
        path.write_bytes(struct.pack(">I4s", 500, b"moov") + b"\x00" * 8)
        with path.open("rb") as f:
            parsed = mp4._parse_header(f, 0, 16)
        assert parsed is not None
        box, truncated = parsed
        assert truncated is True
        assert (box.kind, box.payload_start, box.end) == (b"moov", 8, 16)

    def test_box_smaller_than_its_header_stops_the_walk(self, tmp_path: Path) -> None:
        path = tmp_path / "a.m4a"
        path.write_bytes(struct.pack(">I4s", 3, b"free") + bytes(16))
        assert read_duration_seconds(path) is None
        assert read_tsrp_payload(path) is None

    def test_truncated_64_bit_box_in_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "a.m4a"
        path.write_bytes(box(b"ftyp", b"M4A ") + struct.pack(">I4s", 1, b"moov") + b"\x00\x00")
        assert read_duration_seconds(path) is None


class TestReadTsrpPayload:
    @pytest.mark.parametrize("place", ["udta", "moov", "meta", "trak", "top"])
    def test_found_in_each_location(self, tmp_path: Path, place: str) -> None:
        audio = make_m4a(tmp_path / "a.m4a", tsrp=PAYLOAD, place=place, duration=1.0)
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_none_when_absent(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", duration=1.0)
        assert read_tsrp_payload(audio) is None

    def test_trailing_nul_padding_removed(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", tsrp=PAYLOAD + b"\x00\x00\x00")
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_meta_without_version_prefix(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        meta = box(b"meta", box(b"tsrp", PAYLOAD))
        audio.write_bytes(box(b"ftyp", b"M4A ") + box(b"moov", box(b"udta", meta)))
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_64_bit_box_size(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(
            box(b"ftyp", b"M4A ") + box(b"moov", box(b"udta", large_box(b"tsrp", PAYLOAD)))
        )
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_size_zero_box_runs_to_the_end(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(
            box(b"ftyp", b"M4A ")
            + box(b"moov", mvhd(1.0))
            + struct.pack(">I4s", 0, b"tsrp")
            + PAYLOAD
        )
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_clean_file_without_tsrp_is_not_scanned(self, tmp_path: Path) -> None:
        """A marker inside audio data must not be mistaken for a box in a well formed file."""
        audio = tmp_path / "a.m4a"
        fake = b"\x00\x00\x00\x20tsrp" + PAYLOAD
        audio.write_bytes(box(b"ftyp", b"M4A ") + box(b"moov", mvhd(1.0)) + box(b"mdat", fake))
        assert read_tsrp_payload(audio) is None

    def test_malformed_file_falls_back_to_a_byte_scan(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(b"JUNKJUNKJUNK" + box(b"tsrp", PAYLOAD) + b"more junk")
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_scan_skips_a_marker_with_an_impossible_size(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        bad = struct.pack(">I", 2) + b"tsrp"
        audio.write_bytes(b"JUNK" + bad + b"JUNK" + box(b"tsrp", PAYLOAD))
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_scan_skips_a_marker_at_the_very_start(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(b"tsrp" + b"JUNKJUNK" + box(b"tsrp", PAYLOAD))
        assert read_tsrp_payload(audio) == PAYLOAD

    @pytest.mark.parametrize("chunk", range(5, 21))
    def test_scan_finds_a_marker_across_chunk_boundaries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chunk: int
    ) -> None:
        monkeypatch.setattr(mp4, "_SCAN_CHUNK", chunk)
        audio = tmp_path / "a.m4a"
        audio.write_bytes(b"JUNK-JUNK-JUNK-" + box(b"tsrp", PAYLOAD))
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_scan_returns_none_when_marker_is_absent(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(b"JUNK" * 100)
        assert read_tsrp_payload(audio) is None

    def test_oversized_payload_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mp4, "_MAX_TSRP_BYTES", 4)
        audio = make_m4a(tmp_path / "a.m4a", tsrp=PAYLOAD)
        assert read_tsrp_payload(audio) is None

    def test_nesting_beyond_the_depth_limit_is_not_followed(self, tmp_path: Path) -> None:
        nested = box(b"tsrp", PAYLOAD)
        for _ in range(mp4._MAX_DEPTH + 2):
            nested = box(b"udta", nested)
        audio = tmp_path / "a.m4a"
        audio.write_bytes(box(b"ftyp", b"M4A ") + box(b"moov", nested))
        assert read_tsrp_payload(audio) is None

    def test_empty_container_is_skipped(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(
            box(b"ftyp", b"M4A ") + box(b"moov", box(b"udta") + box(b"tsrp", PAYLOAD))
        )
        assert read_tsrp_payload(audio) == PAYLOAD

    def test_missing_file_and_directory(self, tmp_path: Path) -> None:
        assert read_tsrp_payload(tmp_path / "nope.m4a") is None
        assert read_tsrp_payload(tmp_path) is None

    def test_empty_file(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.m4a"
        audio.write_bytes(b"")
        assert read_tsrp_payload(audio) is None

    def test_payload_round_trips_through_the_builder(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", transcript="one two three")
        assert read_tsrp_payload(audio) == tsrp_payload("one two three")

    def test_permission_error_is_not_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio = make_m4a(tmp_path / "a.m4a", tsrp=PAYLOAD)

        def deny(*args: object, **kwargs: object) -> object:
            raise PermissionError(1, "Operation not permitted")

        monkeypatch.setattr(os, "open", deny)
        with pytest.raises(PermissionError):
            read_tsrp_payload(audio)

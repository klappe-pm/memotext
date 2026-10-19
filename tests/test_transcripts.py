"""Tests for tsrp and manifest transcript decoding."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.synthetic import make_m4a, tsrp_payload, write_manifest
from voicememos import transcripts
from voicememos.transcripts import (
    read_manifest,
    read_tsrp_transcript,
    transcript_from_manifest,
    transcript_from_tsrp,
)


class TestTranscriptFromManifest:
    def test_direct_string(self) -> None:
        assert transcript_from_manifest({"transcript": "Hello world"}) == "Hello world"

    def test_string_is_stripped(self) -> None:
        assert transcript_from_manifest({"transcript": "  Hello  \n"}) == "Hello"

    def test_nested_attributed_string_runs(self) -> None:
        data = {"transcriptPayload": {"attributedString": {"runs": ["Hello", 0, " world", 1]}}}
        assert transcript_from_manifest(data) == "Hello world"

    def test_segments_with_text(self) -> None:
        data = {"speechTranscript": {"segments": [{"text": "Hello"}, {"text": "world"}]}}
        assert transcript_from_manifest(data) == "Hello world"

    def test_segments_use_alternate_text_keys_and_plain_strings(self) -> None:
        data = {"dictation": {"utterances": ["Hello", {"displayText": "there"}, {"x": 1}, 5]}}
        assert transcript_from_manifest(data) == "Hello there"

    def test_runs_directly_under_a_hinted_key(self) -> None:
        assert transcript_from_manifest({"captions": {"runs": ["Hi", 0]}}) == "Hi"

    def test_nested_text_keys(self) -> None:
        assert transcript_from_manifest({"speech": {"text": "Spoken"}}) == "Spoken"
        assert transcript_from_manifest({"speech": {"content": "Held"}}) == "Held"

    def test_attributed_text_key(self) -> None:
        data = {"transcript": {"attributedText": ["A", 0, "B", 1]}}
        assert transcript_from_manifest(data) == "AB"

    def test_list_of_segments_under_a_hinted_key(self) -> None:
        data = {"transcript": [{"text": "one"}, {"text": "two"}]}
        assert transcript_from_manifest(data) == "one two"

    def test_a_list_of_bare_strings_is_read_as_runs(self) -> None:
        """Inferred: a list of only strings is indistinguishable from attributed string runs."""
        assert transcript_from_manifest({"transcript": ["one", " two"]}) == "one two"
        assert transcript_from_manifest({"transcript": ["one", "two"]}) == "onetwo"

    def test_segment_list_key_that_is_not_a_list(self) -> None:
        assert transcript_from_manifest({"transcript": {"segments": "abc"}}) is None

    def test_list_of_nested_mappings(self) -> None:
        data = {"transcripts": [{"unrelated": 1}, {"transcript": "found"}]}
        assert transcript_from_manifest(data) == "found"

    def test_blank_values_are_ignored(self) -> None:
        assert transcript_from_manifest({"transcript": "   "}) is None
        assert transcript_from_manifest({"transcript": {"text": "  "}}) is None
        assert transcript_from_manifest({"transcript": {"runs": [1, 2]}}) is None
        assert transcript_from_manifest({"transcript": {"segments": [{"text": " "}]}}) is None
        assert transcript_from_manifest({"transcript": []}) is None
        assert transcript_from_manifest({"transcript": {"attributedString": {"runs": []}}}) is None

    def test_unrelated_keys_are_not_read(self) -> None:
        assert transcript_from_manifest({"title": "Voice Memo", "duration": 12.5}) is None
        assert transcript_from_manifest({"notes": "not a transcript"}) is None

    def test_non_string_keys_do_not_crash(self) -> None:
        assert transcript_from_manifest({1: "x", "transcript": "ok"}) == "ok"  # type: ignore[dict-item]

    def test_non_text_scalars(self) -> None:
        assert transcript_from_manifest({"transcript": 5}) is None


class TestTranscriptFromTsrp:
    def test_runs_in_an_object(self) -> None:
        assert (
            transcript_from_tsrp(tsrp_payload("Hello brave new world")) == "Hello brave new world"
        )

    def test_runs_as_a_bare_list(self) -> None:
        payload = json.dumps({"attributedString": ["Hi", 0, " you", 1]}).encode()
        assert transcript_from_tsrp(payload) == "Hi you"

    def test_text_is_stripped(self) -> None:
        assert transcript_from_tsrp(tsrp_payload(runs=["  hi ", 0])) == "hi"

    @pytest.mark.parametrize(
        "payload",
        [
            b"not json",
            b"\xff\xfe\xfa",
            b"[1, 2]",
            b'"text"',
            b"{}",
            b'{"attributedString": 5}',
            b'{"attributedString": {"runs": "abc"}}',
            b'{"attributedString": {"runs": []}}',
            b'{"attributedString": {"runs": [1, 2]}}',
            b'{"attributedString": {"runs": ["  "]}}',
            b"[" * 100000,
        ],
    )
    def test_none_for_unusable_payloads(self, payload: bytes) -> None:
        assert transcript_from_tsrp(payload) is None


class TestReadTsrpTranscript:
    def test_reads_from_a_file(self, tmp_path: Path) -> None:
        audio = make_m4a(tmp_path / "a.m4a", transcript="the quick brown fox")
        assert read_tsrp_transcript(audio) == "the quick brown fox"

    def test_none_without_the_box(self, tmp_path: Path) -> None:
        assert read_tsrp_transcript(make_m4a(tmp_path / "a.m4a")) is None

    def test_none_when_the_box_is_not_json(self, tmp_path: Path) -> None:
        assert read_tsrp_transcript(make_m4a(tmp_path / "a.m4a", tsrp=b"\x01\x02")) is None


class TestReadManifest:
    @pytest.mark.parametrize("binary", [False, True])
    def test_reads_xml_and_binary_plists(self, tmp_path: Path, binary: bool) -> None:
        composition = tmp_path / "x.composition"
        write_manifest(composition, {"title": "Hi", "duration": 3.5}, binary=binary)
        assert read_manifest(composition) == {"title": "Hi", "duration": 3.5}

    def test_none_when_the_folder_or_file_is_absent(self, tmp_path: Path) -> None:
        assert read_manifest(tmp_path / "nope.composition") is None
        (tmp_path / "empty.composition").mkdir()
        assert read_manifest(tmp_path / "empty.composition") is None

    def test_none_when_the_composition_is_a_file(self, tmp_path: Path) -> None:
        (tmp_path / "x.composition").write_text("not a folder")
        assert read_manifest(tmp_path / "x.composition") is None

    def test_none_when_the_manifest_is_a_directory(self, tmp_path: Path) -> None:
        (tmp_path / "x.composition" / "manifest.plist").mkdir(parents=True)
        assert read_manifest(tmp_path / "x.composition") is None

    @pytest.mark.parametrize(
        "content",
        [b"", b"garbage", b"<plist><dict><key>a</key>", b"bplist00\x00\x01"],
    )
    def test_none_for_corrupt_plists(self, tmp_path: Path, content: bytes) -> None:
        composition = tmp_path / "x.composition"
        composition.mkdir()
        (composition / "manifest.plist").write_bytes(content)
        assert read_manifest(composition) is None

    def test_oversized_manifest_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        composition = tmp_path / "x.composition"
        write_manifest(composition, {"title": "Hi"})
        monkeypatch.setattr(transcripts, "_MAX_MANIFEST_BYTES", 10)
        assert read_manifest(composition) is None

    def test_deeply_nested_plist_is_treated_as_corrupt(self, tmp_path: Path) -> None:
        composition = tmp_path / "x.composition"
        composition.mkdir()
        depth = 5000
        xml = "<plist>" + "<array>" * depth + "</array>" * depth + "</plist>"
        (composition / "manifest.plist").write_text(xml)
        assert read_manifest(composition) is None

    def test_none_when_the_top_level_is_not_a_dictionary(self, tmp_path: Path) -> None:
        composition = tmp_path / "x.composition"
        composition.mkdir()
        import plistlib

        (composition / "manifest.plist").write_bytes(plistlib.dumps([1, 2, 3]))
        assert read_manifest(composition) is None

    def test_permission_error_is_not_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        composition = tmp_path / "x.composition"
        write_manifest(composition, {"title": "Hi"})

        def deny(*args: object, **kwargs: object) -> object:
            raise PermissionError(1, "Operation not permitted")

        monkeypatch.setattr(os, "open", deny)
        with pytest.raises(PermissionError):
            read_manifest(composition)

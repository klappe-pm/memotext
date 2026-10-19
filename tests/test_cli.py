"""Tests for the command line interface."""

from __future__ import annotations

import json
import os
import runpy
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tests.synthetic import make_m4a, write_manifest
from voicememos import __version__, cli, discovery
from voicememos.cli import main

STEM_A = "20250115 143022-ABCD1234"
STEM_B = "20250116 081500-EF019876"


@pytest.fixture
def populated(default_library: Path) -> Path:
    make_m4a(default_library / f"{STEM_A}.m4a", duration=125.0, transcript="first memo words")
    write_manifest(default_library / f"{STEM_A}.composition", {"title": "First"})
    make_m4a(default_library / f"{STEM_B}.m4a", duration=3725.0)
    write_manifest(
        default_library / f"{STEM_B}.composition",
        {"title": "Second", "transcript": "second memo words"},
    )
    return default_library


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def deny_scandir(monkeypatch: pytest.MonkeyPatch, blocked: Path) -> None:
    real = os.scandir

    def fake(path: str | os.PathLike[str]) -> object:
        if Path(path) == blocked:
            raise PermissionError(1, "Operation not permitted")
        return real(path)

    monkeypatch.setattr(os, "scandir", fake)


class TestProbe:
    def test_nothing_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "probe")
        assert code == 1
        assert out.count("missing") == len(discovery.KNOWN_PATHS)
        assert "library: none readable" in out

    def test_found(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "probe")
        assert code == 0
        assert f"library: {populated}" in out
        assert "readable" in out
        assert "2" in out

    def test_blocked_prints_the_full_disk_access_hint(
        self,
        default_library: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        deny_scandir(monkeypatch, default_library)
        code, out, _ = run(capsys, "probe")
        assert code == 1
        assert "blocked" in out
        assert "Full Disk Access" in out
        assert "library: none readable" in out

    def test_json(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "probe", "--json")
        data = json.loads(out)
        assert code == 0
        assert data["library"] == str(populated)
        assert [p["state"] for p in data["paths"]][0] == "readable"
        assert len(data["paths"]) == len(discovery.KNOWN_PATHS)

    def test_json_when_nothing_is_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "probe", "--json")
        assert code == 1
        assert json.loads(out)["library"] is None

    def test_spotlight_flag_is_passed_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        extra = tmp_path / "elsewhere"
        extra.mkdir()
        make_m4a(extra / "a.m4a")
        monkeypatch.setattr(discovery, "spotlight_search", lambda: [extra])
        code, out, _ = run(capsys, "probe", "--spotlight")
        assert code == 0
        assert f"library: {extra}" in out


class TestList:
    def test_table_is_newest_first(
        self, populated: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(capsys, "list")
        lines = out.splitlines()
        assert code == 0
        assert lines[0].split() == ["ID", "RECORDED", "DURATION", "TRANSCRIPT", "TITLE"]
        assert STEM_B in lines[1]
        assert STEM_A in lines[2]
        assert "1:02:05" in lines[1]
        assert "2:05" in lines[2]
        assert "plist" in lines[1]
        assert "tsrp" in lines[2]

    def test_recorded_column_is_local_time(
        self, populated: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = run(capsys, "list", "--library", str(populated))
        first = datetime(2025, 1, 15, 14, 30, 22).astimezone().strftime("%Y-%m-%d %H:%M")
        assert first in out

    def test_json_omits_the_transcript_text(
        self, populated: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out, _ = run(capsys, "list", "--json")
        data = json.loads(out)
        assert code == 0
        assert [r["id"] for r in data] == [STEM_B, STEM_A]
        assert all("transcript" not in r for r in data)
        assert data[0]["transcript_source"] == "plist"
        assert data[1]["duration_seconds"] == pytest.approx(125.0)

    def test_empty_library(self, library: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "list", "--library", str(library))
        assert code == 0
        assert out.splitlines()[0].split()[0] == "ID"
        assert len(out.splitlines()) == 1
        code, out, _ = run(capsys, "list", "--library", str(library), "--json")
        assert json.loads(out) == []

    def test_unknown_duration_and_no_transcript(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a")
        _, out, _ = run(capsys, "list", "--library", str(library))
        assert "unknown" in out
        assert "none" in out

    def test_long_titles_are_shortened(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a")
        write_manifest(library / "a.composition", {"title": "x" * 80})
        _, out, _ = run(capsys, "list", "--library", str(library))
        assert "x" * 37 + "..." in out
        assert "x" * 38 not in out

    def test_no_library_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, err = run(capsys, "list")
        assert code == 1
        assert out == ""
        assert "no readable Voice Memos folder" in err
        assert "voicememos probe" in err

    def test_blocked_library_is_reported_not_called_missing(
        self,
        default_library: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        deny_scandir(monkeypatch, default_library)
        code, _, err = run(capsys, "list")
        assert code == 1
        assert "cannot be listed" in err
        assert str(default_library) in err
        assert "Full Disk Access" in err

    def test_missing_explicit_library(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run(capsys, "list", "--library", str(tmp_path / "gone"))
        assert code == 1
        assert "not found" in err

    def test_blocked_explicit_library(
        self,
        library: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        deny_scandir(monkeypatch, library)
        code, _, err = run(capsys, "list", "--library", str(library))
        assert code == 1
        assert "cannot be listed" in err

    def test_tilde_in_library_option(
        self, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = fake_home / "Rec"
        folder.mkdir()
        make_m4a(folder / "a.m4a")
        code, out, _ = run(capsys, "list", "--library", "~/Rec")
        assert code == 0
        assert "a" in out

    def test_spotlight_flag_finds_a_library_elsewhere(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        extra = tmp_path / "elsewhere"
        extra.mkdir()
        make_m4a(extra / "only.m4a")
        monkeypatch.setattr(discovery, "spotlight_search", lambda: [extra])
        code, out, _ = run(capsys, "list", "--spotlight")
        assert code == 0
        assert "only" in out


class TestShow:
    def test_text(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "show", STEM_A)
        assert code == 0
        assert "title: First" in out
        assert f"id: {STEM_A}" in out
        assert "duration: 2:05" in out
        assert f"audio: {populated / (STEM_A + '.m4a')}" in out
        assert "transcript source: tsrp" in out
        assert out.rstrip().endswith("first memo words")

    def test_text_without_transcript_or_composition(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "a.m4a")
        code, out, _ = run(capsys, "show", "a", "--library", str(library))
        assert code == 0
        assert "composition: none" in out
        assert "transcript source: none" in out
        assert "duration: unknown" in out

    def test_json(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "show", STEM_B, "--json")
        data = json.loads(out)
        assert code == 0
        assert data["id"] == STEM_B
        assert data["transcript"] == "second memo words"
        assert data["transcript_source"] == "plist"
        assert data["composition_path"].endswith(".composition")
        datetime.fromisoformat(data["recorded_at"])

    def test_unique_prefix(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, _ = run(capsys, "show", "20250116")
        assert code == 0
        assert f"id: {STEM_B}" in out

    def test_ambiguous_prefix(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, _, err = run(capsys, "show", "20250")
        assert code == 1
        assert "ambiguous" in err
        assert STEM_A in err
        assert STEM_B in err

    def test_exact_id_beats_a_longer_match(
        self, library: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_m4a(library / "memo.m4a", transcript="short")
        make_m4a(library / "memo2.m4a", transcript="long")
        code, out, _ = run(capsys, "show", "memo", "--library", str(library))
        assert code == 0
        assert out.rstrip().endswith("short")

    def test_unknown_id(self, populated: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code, out, err = run(capsys, "show", "nope")
        assert code == 1
        assert out == ""
        assert "no recording with id 'nope'" in err

    def test_no_library(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _, err = run(capsys, "show", "x")
        assert code == 1
        assert "voicememos:" in err


class TestEntryPoints:
    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as info:
            main(["--version"])
        assert info.value.code == 0
        assert capsys.readouterr().out.strip() == f"voicememos {__version__}"

    def test_a_command_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as info:
            main([])
        assert info.value.code == 2

    def test_unknown_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as info:
            main(["bogus"])
        assert info.value.code == 2

    def test_main_reads_sys_argv_by_default(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["voicememos", "probe", "--json"])
        assert main() == 1
        assert json.loads(capsys.readouterr().out)["library"] is None

    def test_python_dash_m_entry_point(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["voicememos", "probe", "--json"])
        with pytest.raises(SystemExit) as info:
            runpy.run_module("voicememos", run_name="__main__")
        assert info.value.code == 1
        assert json.loads(capsys.readouterr().out)["library"] is None


class TestFormatting:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(None, "unknown"), (0, "0:00"), (59.6, "1:00"), (125, "2:05"), (3725, "1:02:05")],
    )
    def test_duration(self, seconds: float | None, expected: str) -> None:
        assert cli._format_duration(seconds) == expected

    def test_shorten(self) -> None:
        assert cli._shorten("short", 10) == "short"
        assert cli._shorten("a" * 20, 10) == "a" * 7 + "..."

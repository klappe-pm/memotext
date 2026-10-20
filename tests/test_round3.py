"""Regression tests for the third verification round (voicememos only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.synthetic import make_m4a
from voicememos.cli import main
from voicememos.textsafe import printable

# --- vm3-01: characters that draw as blank without being Default_Ignorable -------------------

BLANK_DRAWING = {
    0x2800: "\\u2800",  # BRAILLE PATTERN BLANK
    0x1D159: "\\U0001d159",  # MUSICAL SYMBOL NULL NOTEHEAD
    0x115F: "\\u115f",  # HANGUL CHOSEONG FILLER
    0x1160: "\\u1160",  # HANGUL JUNGSEONG FILLER
    0x3164: "\\u3164",  # HANGUL FILLER
    0xFFA0: "\\uffa0",  # HALFWIDTH HANGUL FILLER
}


@pytest.mark.parametrize(("code", "escaped"), BLANK_DRAWING.items())
def test_a_character_that_draws_as_blank_is_escaped(code: int, escaped: str) -> None:
    text = f"a{chr(code)}b"
    assert printable(text) != text
    assert printable(text) == f"a{escaped}b"


def test_the_braille_blank_does_not_hide_inside_a_word() -> None:
    assert printable("a⠀b") != "a⠀b"
    assert "⠀" not in printable("⠀" * 5)


def test_other_braille_patterns_are_still_printed_as_themselves() -> None:
    assert printable("⠁⣿") == "⠁⣿"


def test_two_ids_that_differ_only_by_a_braille_blank_print_differently_in_list(
    library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_m4a(library / "memo.m4a")
    make_m4a(library / "memo⠀.m4a")
    code = main(["list", "--library", str(library)])
    out = capsys.readouterr().out
    assert code == 0
    assert "⠀" not in out
    ids = [line.split()[0] for line in out.splitlines()[1:]]
    assert sorted(ids) == ["memo", "memo\\u2800"]

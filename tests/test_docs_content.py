"""What the documentation says about voicememos stays true: the public names and the warning."""

from __future__ import annotations

import re

import pytest

from tests.conftest import ROOT

pytestmark = pytest.mark.repo_only

API_PAGE = ROOT / "docs" / "reference" / "python-api.md"


def test_every_documented_error_is_exported_from_the_top_level() -> None:
    import voicememos

    table = API_PAGE.read_text(encoding="utf-8").split("## Errors", 1)[1].split("## Version", 1)[0]
    names = re.findall(r"^\| `(\w+)` \|", table, flags=re.MULTILINE)
    assert names, "the errors table lists no class"
    missing = [name for name in names if name not in voicememos.__all__]
    assert not missing, missing
    for name in names:
        assert getattr(voicememos, name) is getattr(voicememos.errors, name)


def test_the_documented_import_block_is_exactly_the_public_names() -> None:
    import voicememos

    text = API_PAGE.read_text(encoding="utf-8")
    block = re.search(r"from voicememos import \((.*?)\)", text, flags=re.DOTALL)
    assert block is not None
    documented = {name.strip() for name in block.group(1).split(",") if name.strip()}
    assert documented == set(voicememos.__all__) - {"__version__"}


def test_the_warning_row_says_what_triggers_the_warning() -> None:
    table = API_PAGE.read_text(encoding="utf-8").split("## Errors", 1)[1]
    row = next(
        line for line in table.splitlines() if line.startswith("| `RecordingSkippedWarning`")
    )
    assert "`UserWarning`" in row
    assert "any" in row, "a recording is skipped for any exception, not only an OSError"
    assert "on_skip" in row

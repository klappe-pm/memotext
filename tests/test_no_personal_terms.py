"""The published tree names no owner detail, personal path or work item code.

The patterns are built from fragments so this file does not match itself. Private tool names and
any other private terms are kept outside the repository, in a file named by
VOICEMEMOS_FORBIDDEN_TERMS_FILE, so the published source never records them.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.conftest import ROOT

TERMS_FILE_VARIABLE = "VOICEMEMOS_FORBIDDEN_TERMS_FILE"

FORBIDDEN = {
    "owner login": "kl" + "appe" + r"(?!-pm\b)",
    "owner email": "kevin" + r"\d+",
    "owner name": "Kevin" + r"\s+Lap" + "pe",
    "work item code": r"\bW" + r"I-\d+",
    "work item term": "work" + r"[- ]item",
    "absolute home path": "/(?:Users|home)/" + r"[A-Za-z0-9._-]+",
}

# The published author appears where a licence and a package need one. PKG-INFO is the metadata
# that the build writes into a source distribution from pyproject.toml.
ALLOWED = {"owner name": {"LICENSE", "pyproject.toml", "PKG-INFO"}}

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
}
THIS_FILE = Path(__file__).resolve()


def tracked_files(root: Path = ROOT) -> list[Path]:
    """Every file git tracks; outside a clone (an extracted sdist) every file in the tree."""
    found: list[Path] = []
    if (root / ".git").exists():
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "ls-files", "-z"],  # noqa: S607
            capture_output=True,
            check=True,
        )
        found = [root / name for name in result.stdout.decode().split("\0") if name]
    else:
        for directory, folders, files in os.walk(root):
            folders[:] = [
                f
                for f in folders
                if f not in SKIP_DIRS
                and not f.endswith(".egg-info")
                and not (Path(directory) / f / "pyvenv.cfg").exists()
            ]
            found += [Path(directory) / name for name in files]
    return sorted(p for p in found if p.is_file() and p.resolve() != THIS_FILE)


def scan(files: list[Path], root: Path = ROOT) -> list[str]:
    compiled = {label: re.compile(pattern, re.IGNORECASE) for label, pattern in FORBIDDEN.items()}
    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(root)
        for label, pattern in compiled.items():
            if str(relative) in ALLOWED.get(label, ()):
                continue
            if pattern.search(str(relative)):
                hits.append(f"{relative}: path ({label})")
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{relative}:{number}: {label}")
    return hits


def test_no_tracked_file_names_a_private_term() -> None:
    hits = scan(tracked_files())
    assert not hits, "\n".join(hits[:400])


def test_the_scan_finds_each_kind_of_term(tmp_path: Path) -> None:
    samples = {
        "owner login": "github.com/" + "kl" + "appe" + "-other",
        "owner email": "kevin" + "1234" + "@example.org",
        "owner name": "Kevin " + "Lap" + "pe",
        "work item code": "see W" + "I-123",
        "absolute home path": "/Users/" + "someone/project",
    }
    for index, (label, line) in enumerate(samples.items()):
        path = tmp_path / f"sample-{index}.md"
        path.write_text(line + "\n", encoding="utf-8")
        hits = scan([path], tmp_path)
        assert any(label in hit for hit in hits), (label, hits)


def test_the_package_owner_is_allowed_only_where_a_licence_needs_one(tmp_path: Path) -> None:
    owner = "Kevin " + "Lap" + "pe"
    for name in ("LICENSE", "pyproject.toml"):
        (tmp_path / name).write_text(f"author {owner}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(f"author {owner}\n", encoding="utf-8")
    hits = scan(sorted(tmp_path.iterdir()), tmp_path)
    assert [hit.split(":")[0] for hit in hits] == ["README.md"]


def test_the_repository_owner_account_is_not_a_hit(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("https://github.com/" + "kl" + "appe" + "-pm/voicememos\n", encoding="utf-8")
    assert scan([path], tmp_path) == []


def test_no_extra_forbidden_terms() -> None:
    """Check a private list of terms kept outside the repository.

    The list is a text file, one term per line, named by VOICEMEMOS_FORBIDDEN_TERMS_FILE. The
    repository itself never records the terms.
    """
    location = os.environ.get(TERMS_FILE_VARIABLE)
    if not location:
        pytest.skip(f"{TERMS_FILE_VARIABLE} is not set")
    terms = [
        t.strip().lower()
        for t in Path(location).read_text(encoding="utf-8").splitlines()
        if t.strip()
    ]
    hits = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        hits += [
            f"{path.relative_to(ROOT)}: line {number}"
            for number, line in enumerate(text.splitlines(), 1)
            if any(term in line for term in terms)
        ]
        hits += [
            f"{path.relative_to(ROOT)}: path"
            for term in terms
            if term in str(path.relative_to(ROOT)).lower()
        ]
    assert not hits, "\n".join(hits[:400])


def test_the_extra_terms_file_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    terms = tmp_path / "terms.txt"
    secret_term = "zq" + "xv-private"
    terms.write_text(f"\n{secret_term}\n", encoding="utf-8")
    monkeypatch.setenv(TERMS_FILE_VARIABLE, str(terms))
    assert os.environ[TERMS_FILE_VARIABLE] == str(terms)
    # The repository does not contain the term, so the real check passes with the file set.
    test_no_extra_forbidden_terms()

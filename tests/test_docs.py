"""The documentation and the repository files around it stay accurate, linked and consistent."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import ROOT

pytestmark = pytest.mark.repo_only

PACKAGE = "voicememos"
DOCS = ROOT / "docs"
QUADRANTS = ("tutorials", "how-to-guides", "reference", "explanation")
COMMUNITY_FILES = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
)
GITHUB_FILES = {
    ".github/ISSUE_TEMPLATE/bug-report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/feature-request.yml",
    ".github/ISSUE_TEMPLATE/question.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    f".github/{PACKAGE}-banner.svg",
    ".github/workflows/release.yml",
}
# Pages kept out of the public tree. They are ignored by git and may exist in a working copy.
UNPUBLISHED = (DOCS / "documentation-guide",)

SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "the",
    "to",
    "vs",
    "via",
    "with",
    "into",
    "from",
}
FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_REFERENCE = re.compile(r'(?:href|src)="([^"]+)"')
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")
PROVENANCE_KEY = re.compile(r"^(?:models|providers|session-link)\s*:", re.MULTILINE)
ROBOT = chr(0x1F916)
BYLINE = re.compile(
    r"generated (?:with|by)\b.*claude|co-authored-by|claude-session|noreply@anthropic",
    re.IGNORECASE,
)
EM, EN = chr(0x2014), chr(0x2013)
TABLE_RULE = re.compile(r"^\|?[\s:|-]+\|?$")


def is_unpublished(path: Path) -> bool:
    return any(folder in path.parents for folder in UNPUBLISHED)


def markdown_files() -> list[Path]:
    found = [ROOT / name for name in COMMUNITY_FILES if name.endswith(".md")]
    found += [ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"]
    found += [p for p in DOCS.rglob("*.md") if not is_unpublished(p)]
    return sorted(p for p in found if p.is_file())


def docs_files() -> list[Path]:
    return [p for p in markdown_files() if DOCS in p.parents]


def label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


MARKDOWN = pytest.mark.parametrize("path", markdown_files(), ids=label)
DOCS_ONLY = pytest.mark.parametrize("path", docs_files(), ids=label)


def lines_of(path: Path) -> list[tuple[int, str, bool]]:
    """Every line as (number, text, inside a fence). The fence lines themselves count as inside."""
    result, fenced = [], False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            result.append((number, line, True))
            continue
        result.append((number, line, fenced))
    return result


def headings(path: Path) -> list[tuple[int, int, str]]:
    found = []
    for number, line, fenced in lines_of(path):
        match = None if fenced else HEADING.match(line)
        if match:
            found.append((number, len(match.group(1)), match.group(2)))
    return found


def prose(path: Path) -> list[tuple[int, str]]:
    """The lines outside code fences, with inline code spans removed."""
    return [(n, re.sub(r"`[^`]*`", "", line)) for n, line, fenced in lines_of(path) if not fenced]


def slug(text: str) -> str:
    text = re.sub(r"[`*]", "", text.lower())
    return re.sub(r"[^a-z0-9 _-]", "", text).strip().replace(" ", "-")


def test_the_community_files_exist() -> None:
    missing = [name for name in COMMUNITY_FILES if not (ROOT / name).is_file()]
    assert not missing, missing


def test_github_holds_only_the_allowed_files() -> None:
    present = {p.relative_to(ROOT).as_posix() for p in (ROOT / ".github").rglob("*") if p.is_file()}
    assert present == GITHUB_FILES


def test_there_is_one_docs_tree() -> None:
    assert not (ROOT / "developer-docs").exists()
    assert (DOCS / "README.md").is_file()
    for quadrant in QUADRANTS:
        assert (DOCS / quadrant / "README.md").is_file(), quadrant


def test_each_quadrant_index_lists_every_page_in_its_folder() -> None:
    for quadrant in QUADRANTS:
        folder = DOCS / quadrant
        index = (folder / "README.md").read_text(encoding="utf-8")
        for page in sorted(p for p in folder.glob("*.md") if p.name != "README.md"):
            assert f"]({page.name})" in index, f"{label(folder / 'README.md')} omits {page.name}"


def test_the_docs_index_links_every_quadrant() -> None:
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    for quadrant in QUADRANTS:
        assert f"]({quadrant}/README.md)" in index, quadrant


def test_the_docs_index_names_every_page() -> None:
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    for quadrant in QUADRANTS:
        for page in sorted(p for p in (DOCS / quadrant).glob("*.md") if p.name != "README.md"):
            assert f"]({quadrant}/{page.name})" in index, (
                f"docs/README.md omits {quadrant}/{page.name}"
            )


def test_no_published_page_links_into_the_unpublished_guide() -> None:
    hits = [label(p) for p in markdown_files() if "documentation-guide" in p.read_text("utf-8")]
    assert not hits, hits


@pytest.mark.parametrize(
    "path", [p for p in markdown_files() if p.name != "PULL_REQUEST_TEMPLATE.md"], ids=label
)
def test_the_page_has_exactly_one_h1(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    h1s = [text for _n, level, text in headings(path) if level == 1]
    html_h1s = re.findall(r"<h1[ >]", text)
    assert len(h1s) + len(html_h1s) == 1, f"{label(path)} has {len(h1s) + len(html_h1s)} H1"


@MARKDOWN
def test_every_heading_is_title_case(path: Path) -> None:
    bad = []
    for number, _level, text in headings(path):
        outside_code = re.sub(r"`[^`]*`", "", text)
        for index, word in enumerate(outside_code.split()):
            core = re.sub(r"^[^A-Za-z0-9]*|[^A-Za-z0-9]*$", "", word)
            if not core or any(ch.isupper() or ch.isdigit() for ch in core):
                continue
            if core.lower() in SMALL_WORDS and index > 0:
                continue
            bad.append(f"{number}: {text}")
            break
    assert not bad, f"{label(path)} has headings that are not Title Case: {bad}"


@MARKDOWN
def test_the_page_carries_no_provenance_keys(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    assert not PROVENANCE_KEY.search(front), label(path)
    assert not text.startswith("---"), f"{label(path)} has frontmatter, which no page needs"


@MARKDOWN
def test_the_page_has_no_robot_byline_or_agent_credit(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert ROBOT not in text, label(path)
    assert not BYLINE.search(text), label(path)


@MARKDOWN
def test_the_page_names_no_home_directory(path: Path) -> None:
    assert not HOME_PATH.search(path.read_text(encoding="utf-8")), label(path)


@MARKDOWN
def test_every_code_fence_has_a_language(path: Path) -> None:
    bad = []
    opening = True
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not FENCE.match(line):
            continue
        if opening and not line.strip().removeprefix("```").strip():
            bad.append(number)
        opening = not opening
    assert not bad, f"{label(path)} has fences without a language at lines {bad}"


@MARKDOWN
def test_no_dash_is_used_as_punctuation(path: Path) -> None:
    bad = []
    for number, line in prose(path):
        text = re.sub(r"\]\([^)]*\)", "]", line)
        text = re.sub(r"<[^>]*>", "", text)
        text = re.sub(r"https?://\S+", "", text)
        stripped = text.strip()
        if TABLE_RULE.match(stripped) or re.fullmatch(r"-{3,}", stripped):
            continue
        body = re.sub(r"^\s*(?:[-*] |\d+\. )", "", text)
        if EM in body or EN in body or " - " in body or "--" in body:
            bad.append(number)
    assert not bad, f"{label(path)} uses a dash as punctuation at lines {bad}"


@MARKDOWN
def test_the_page_is_not_hard_wrapped(path: Path) -> None:
    bad = []
    previous_is_text = False
    for number, line, fenced in lines_of(path):
        stripped = line.strip()
        if fenced or not stripped:
            previous_is_text = False
            continue
        starts_item = re.match(r"^([-*>|#]|\d+\.)\s|^\|", stripped) is not None
        structural = starts_item or stripped.startswith(("<", "---", "![")) or HEADING.match(line)
        if structural:
            # A list item or a quote is text that a following plain line would continue.
            previous_is_text = bool(re.match(r"^([-*>]|\d+\.)\s", stripped))
            continue
        if previous_is_text:
            bad.append(number)
        previous_is_text = True
    assert not bad, f"{label(path)} continues a paragraph or item on a new line at lines {bad}"


@DOCS_ONLY
def test_every_relative_link_resolves(path: Path) -> None:
    anchors_of: dict[Path, set[str]] = {}

    def anchors(target: Path) -> set[str]:
        if target not in anchors_of:
            anchors_of[target] = {slug(text) for _n, _level, text in headings(target)}
        return anchors_of[target]

    text = "\n".join(line for _n, line in prose(path))
    for target in LINK.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):
            continue
        name, _, fragment = target.partition("#")
        resolved = (path.parent / name).resolve() if name else path
        assert resolved.exists(), f"{label(path)} links to {target}, which does not exist"
        if fragment and resolved.suffix == ".md":
            assert fragment in anchors(resolved), (
                f"{label(path)} links to {target}: no such heading"
            )


def test_the_readme_uses_only_absolute_links() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    markdown = [t for t in LINK.findall(text) if not t.startswith("#")]
    html = [t for t in HTML_REFERENCE.findall(text) if not t.startswith("#")]
    relative = [t for t in markdown + html if not re.match(r"^(https://|mailto:)", t)]
    assert not relative, relative
    prefix = f"https://github.com/klappe-pm/{PACKAGE}/"
    own = [t for t in markdown + html if t.startswith(prefix)]
    assert own, "the README links nowhere inside the repository"


def test_the_readme_follows_the_skeleton() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    banner = (
        f"https://raw.githubusercontent.com/klappe-pm/{PACKAGE}/main/.github/{PACKAGE}-banner.svg"
    )
    assert text.startswith('<p align="center">'), "the banner comes first"
    assert banner in text.split("</p>", 1)[0]
    assert 'width="760"' in text.split("</p>", 1)[0]
    assert re.search(r'<h1 align="center">[A-Z][a-z]+</h1>', text)
    assert text.count("style=flat-square&") == 6
    assert text.count("labelColor=162233") == 6
    order = [
        "## Why ",
        "## Installation",
        "## Quick Start",
        "## How It Works",
        "## Commands",
        "## Documentation",
        "## Contributing",
        "## Security",
        "## License",
    ]
    positions = [text.index(heading) for heading in order]
    assert positions == sorted(positions)
    assert "\n---\n" in text


def test_the_banner_is_an_svg_with_a_label() -> None:
    banner = (ROOT / ".github" / f"{PACKAGE}-banner.svg").read_text(encoding="utf-8")
    assert banner.startswith("<svg")
    assert 'role="img"' in banner
    assert "aria-label=" in banner
    assert "<script" not in banner
    assert "http" not in banner.replace("http://www.w3.org/2000/svg", "")


def test_the_issue_templates_point_at_the_package() -> None:
    config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
    assert f"https://github.com/klappe-pm/{PACKAGE}/blob/main/SECURITY.md" in config
    assert "blank_issues_enabled: false" in config
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    for template in ("bug-report", "question", "feature-request"):
        assert f"issues/new?template={template}.yml" in support

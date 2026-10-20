"""The release workflow pins every action and confines the publish permission."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


def test_only_the_release_workflow_exists() -> None:
    workflows = sorted(p.name for p in WORKFLOW.parent.iterdir())
    assert workflows == ["release.yml"]


def test_every_action_is_pinned_to_a_full_commit() -> None:
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_id_token_is_granted_only_to_the_publish_job() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("id-token: write") == 1
    publish = text.split("\n  publish:\n", 1)[1]
    assert "id-token: write" in publish
    assert "environment: pypi" in publish
    assert re.search(r"^permissions:\n  contents: read$", text, re.MULTILINE)


def test_checkout_does_not_keep_credentials() -> None:
    assert "persist-credentials: false" in WORKFLOW.read_text(encoding="utf-8")

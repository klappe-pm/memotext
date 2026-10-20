"""Decode the transcripts that iOS and macOS already produced.

There are two places a transcript can live:

* the `tsrp` box inside the `.m4a` file, whose payload is JSON, and
* the `manifest.plist` inside the recording's `.composition` folder.

The `tsrp` JSON shape is taken from files the original tool handled. The plist layout is not
documented, so `transcript_from_manifest` searches the structure with a set of heuristics. Both
are inferred; see the file formats reference page.
"""

from __future__ import annotations

import errno
import json
import os
import plistlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from voicememos.mp4 import read_tsrp_payload
from voicememos.safeio import (
    ABSENT_ERRORS,
    DirRef,
    close_dir,
    is_real_dir,
    open_child,
    open_dir,
    open_regular,
)

SOURCE_TSRP = "tsrp"
SOURCE_PLIST = "plist"

_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_SEARCH_DEPTH = 32
_MAX_SEARCH_VISITS = 100_000

_TEXT_KEYS = ("text", "string", "content")
_SEGMENT_TEXT_KEYS = ("text", "string", "content", "utterance", "displayText")
_RUN_CONTAINER_KEYS = ("attributedString", "attributedText")
_SEGMENT_LIST_KEYS = ("segments", "utterances", "phrases")
_NAME_HINTS = ("transcript", "speech", "dictation", "caption")


def _clean(text: str) -> str | None:
    stripped = text.strip()
    return stripped or None


def _from_runs(value: Any) -> str | None:
    """Join the string items of an attributed string `runs` list.

    The list alternates text and integer attribute indexes, for example
    `["Hello", 0, " world", 1]`. Only the strings are kept.
    """
    if isinstance(value, dict):
        value = value.get("runs")
    if not isinstance(value, list):
        return None
    parts = [item for item in value if isinstance(item, str)]
    if not parts:
        return None
    return _clean("".join(parts))


def _from_segments(value: Any) -> str | None:
    """Join a list of segments, each a string or a mapping with a text field."""
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            for key in _SEGMENT_TEXT_KEYS:
                text = item.get(key)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                    break
    if not parts:
        return None
    return _clean(" ".join(parts))


def _inspect(value: Any) -> tuple[str | None, list[Any]]:
    """Look at one value without recursing.

    Returns the text found directly in it, if any, and the nested values to search next, in
    order.
    """
    if isinstance(value, str):
        return _clean(value), []

    candidate = _from_runs(value)
    if candidate:
        return candidate, []

    if isinstance(value, dict):
        for key in _TEXT_KEYS:
            nested = value.get(key)
            if isinstance(nested, str):
                candidate = _clean(nested)
                if candidate:
                    return candidate, []
        for key in _RUN_CONTAINER_KEYS:
            if key in value:
                candidate = _from_runs(value[key])
                if candidate:
                    return candidate, []
        for key in _SEGMENT_LIST_KEYS:
            if key in value:
                candidate = _from_segments(value[key])
                if candidate:
                    return candidate, []
        hinted = [
            nested
            for key, nested in value.items()
            if isinstance(key, str) and any(hint in key.lower() for hint in _NAME_HINTS)
        ]
        return None, hinted

    if isinstance(value, list):
        candidate = _from_segments(value)
        if candidate:
            return candidate, []
        return None, list(value)
    return None, []


def _search(root: Any) -> str | None:
    """Depth first search for transcript text, in the same order a recursive search would use.

    The search is iterative, so nesting cannot exhaust the Python stack. It stops descending at
    `_MAX_SEARCH_DEPTH`, looks at no more than `_MAX_SEARCH_VISITS` values, and never looks at
    the same list or dictionary twice, so a structure whose parts are shared (as a binary plist
    allows) costs time in proportion to its distinct objects, not to the paths through it.
    """
    stack: list[tuple[Any, int]] = [(root, 0)]
    seen: set[int] = set()
    visits = 0
    while stack:
        value, depth = stack.pop()
        visits += 1
        if visits > _MAX_SEARCH_VISITS:
            return None
        if isinstance(value, dict | list):
            if id(value) in seen:
                continue
            seen.add(id(value))
        text, children = _inspect(value)
        if text:
            return text
        if depth < _MAX_SEARCH_DEPTH:
            stack.extend((child, depth + 1) for child in reversed(children))
    return None


def transcript_from_manifest(manifest: Mapping[str, Any]) -> str | None:
    """Find transcript text in a parsed `manifest.plist`.

    A string value under a key whose name contains transcript, speech, dictation or caption is
    taken as the text. So are attributed string runs, and lists of segments whose items carry a
    `text`, `string`, `content`, `utterance` or `displayText` field. Returns None when nothing
    matches. The key names are inferred.
    """
    return _search(dict(manifest))


def transcript_from_tsrp(payload: bytes) -> str | None:
    """Decode the JSON payload of a `tsrp` box into plain text.

    The expected shape is `{"attributedString": {"runs": ["word", 0, " word", 1]}}`. A bare list
    in place of the object with `runs` is also accepted. Returns None when the payload is not
    JSON or carries no text.
    """
    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    attributed = data.get("attributedString", {})
    if isinstance(attributed, dict):
        runs = attributed.get("runs", [])
    elif isinstance(attributed, list):
        runs = attributed
    else:
        return None
    if not isinstance(runs, list):
        return None
    return _clean("".join(item for item in runs if isinstance(item, str)))


def read_tsrp_transcript(audio_path: Path) -> str | None:
    """Return the transcript embedded in an `.m4a` file, or None."""
    payload = read_tsrp_payload(audio_path)
    if payload is None:
        return None
    return transcript_from_tsrp(payload)


def read_manifest(composition_path: Path) -> dict[str, Any] | None:
    """Parse `manifest.plist` inside a `.composition` folder.

    Dates come back as `plistlib` returns them: naive datetimes that hold UTC. Returns None when
    the folder is a symlink, the file is absent, a symlink or not a regular file (a FIFO, say),
    is larger than 16 MiB, is not a valid plist, or its top level is not a dictionary. Whatever
    exception the plist parser raises on a hostile file is treated as an invalid plist. An `OSError`
    such as a permission error is not caught, so a blocked folder is never mistaken for a memo
    without metadata. A folder that may be searched but not opened (`EACCES`) has its manifest
    opened by path instead, still without following a symlink.
    """
    if not is_real_dir(composition_path):
        return None
    # The folder is opened without following a symlink, and the manifest is opened inside it by
    # descriptor. A folder swapped for a symlink after the check above is refused, not followed.
    folder: DirRef | None
    try:
        folder = open_dir(composition_path)
    except ABSENT_ERRORS:
        return None
    except PermissionError as exc:
        if exc.errno != errno.EACCES:
            raise
        # A folder with search permission only (mode 0311) cannot be opened for reading, but the
        # manifest inside it can still be opened by name. The final component is still opened with
        # `O_NOFOLLOW`, so a symlinked manifest is refused; only the swap protection for the folder
        # itself is lost, and only for a folder this process may not list.
        folder = None
    try:
        if folder is None:
            f = open_regular(composition_path / "manifest.plist")
        else:
            f = open_child(folder, "manifest.plist")
    except ABSENT_ERRORS:
        return None
    finally:
        if folder is not None:
            close_dir(folder)
    try:
        with f:
            if os.fstat(f.fileno()).st_size > _MAX_MANIFEST_BYTES:
                return None
            data = plistlib.load(f)
    except (OSError, MemoryError):
        raise
    except Exception:
        # plistlib and its XML parser raise whatever a hostile file provokes: AttributeError,
        # IndexError, LookupError and others, as well as the documented parse errors. None of
        # them is a reason to stop a run, so any such file counts as having no manifest.
        return None
    if not isinstance(data, dict):
        return None
    return data

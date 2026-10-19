"""Find the Voice Memos recordings folder on macOS.

Layer 1 checks a list of known paths and reports one of four states for each, so a folder that
exists but cannot be listed is never reported as found. Layer 2 asks Spotlight for other
candidates and only runs on macOS. There are no interactive layers: nothing here prompts, opens
System Settings or changes a permission.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PathLike = str | os.PathLike[str]

KNOWN_PATHS: tuple[Path, ...] = (
    Path("~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"),
    Path("~/Library/Mobile Documents/com~apple~VoiceMemos/Recordings"),
    Path("~/Library/Containers/com.apple.VoiceMemos/Data/Library/Application Support/Recordings"),
    Path("~/Library/Application Support/com.apple.voicememos/Recordings"),
    Path("~/Library/Application Support/com.apple.VoiceMemos/Recordings"),
)
"""Where Voice Memos has kept recordings, in order of preference. Each starts with `~`."""

AUDIO_SUFFIX = ".m4a"

MDFIND = "/usr/bin/mdfind"
"""The Spotlight command line program, called by absolute path."""


class PathState(StrEnum):
    """What probing one path found."""

    MISSING = "missing"
    """Nothing is there, or the path is not a directory."""
    READABLE = "readable"
    """The directory can be listed and holds at least one `.m4a` file."""
    BLOCKED = "blocked"
    """The path exists but listing it failed with a permission error or another OS error."""
    EMPTY = "empty"
    """The directory can be listed and holds no `.m4a` file."""


@dataclass(frozen=True)
class PathProbe:
    """The result of probing one path."""

    path: Path
    """The path with `~` expanded."""
    state: PathState
    recording_count: int = 0
    """Number of `.m4a` files. Only meaningful for `READABLE`."""
    detail: str | None = None
    """The OS error text for `BLOCKED`, or a reason for `MISSING`. None otherwise."""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON ready dictionary."""
        return {
            "path": str(self.path),
            "state": self.state.value,
            "recording_count": self.recording_count,
            "detail": self.detail,
        }


def probe_path(path: PathLike) -> PathProbe:
    """Probe one path and report which of the four states it is in.

    The directory is listed rather than tested with `exists`, because on macOS a folder that
    Full Disk Access protects can look present while listing it raises a permission error. That
    case is `BLOCKED`, never `MISSING` or `EMPTY`.
    """
    expanded = Path(path).expanduser()
    count = 0
    try:
        with os.scandir(expanded) as entries:
            for entry in entries:
                if entry.name.lower().endswith(AUDIO_SUFFIX) and entry.is_file(
                    follow_symlinks=False
                ):
                    count += 1
    except (FileNotFoundError, NotADirectoryError) as exc:
        return PathProbe(expanded, PathState.MISSING, detail=exc.strerror or type(exc).__name__)
    except OSError as exc:
        # PermissionError is the Full Disk Access case. Any other failure to list an existing
        # folder is blocked too: the folder is there and cannot be read.
        return PathProbe(expanded, PathState.BLOCKED, detail=exc.strerror or type(exc).__name__)
    if count == 0:
        return PathProbe(expanded, PathState.EMPTY)
    return PathProbe(expanded, PathState.READABLE, recording_count=count)


def probe_library(paths: Iterable[PathLike] | None = None) -> list[PathProbe]:
    """Probe each path and return the results in the same order.

    With no argument the paths in `KNOWN_PATHS` are probed.
    """
    candidates = KNOWN_PATHS if paths is None else tuple(Path(p) for p in paths)
    return [probe_path(p) for p in candidates]


Runner = Callable[[list[str]], str]


def _run_mdfind(args: list[str]) -> str:
    """Run `/usr/bin/mdfind` and return its standard output, or an empty string if it cannot run.

    The program is called by its absolute path and never looked up through `PATH`, so a program
    of the same name earlier on `PATH` is not run.
    """
    if sys.platform != "darwin" or not os.access(MDFIND, os.X_OK):
        return ""
    try:
        result = subprocess.run(
            [MDFIND, *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def spotlight_search(runner: Runner | None = None) -> list[Path]:
    """Ask Spotlight for folders that may hold Voice Memos recordings (layer 2).

    Two queries run: one for the `CloudRecordings.db` database and one for `.m4a` files whose
    path mentions VoiceMemos. The parent folder of each hit is returned once, in the order
    found. Without `runner` this only works on macOS and returns an empty list elsewhere, or if
    `mdfind` is missing or fails. A `runner` takes the `mdfind` arguments and returns its output,
    which lets tests supply canned output on any platform.

    The queries are inferred, not verified against a real Spotlight index.
    """
    run = runner if runner is not None else _run_mdfind
    queries = (
        ["-name", "CloudRecordings.db"],
        ['kMDItemContentType == "com.apple.m4a-audio" && kMDItemPath == "*VoiceMemos*"'],
    )
    folders: list[Path] = []
    for query in queries:
        for line in run(query).splitlines():
            line = line.strip()
            if not line:
                continue
            parent = Path(line).parent
            if parent not in folders:
                folders.append(parent)
    return folders


def find_library(
    paths: Iterable[PathLike] | None = None, *, spotlight: bool = False
) -> Path | None:
    """Return the first readable recordings folder, or None.

    Only a folder in the `READABLE` state counts as found. A blocked or empty folder is skipped;
    call `probe_library` to see why nothing was found. If no listed path is readable and
    `spotlight` is true, the folders from `spotlight_search` are probed and the readable one
    with the most recordings wins. The Spotlight pass never runs unless asked for.
    """
    probes = probe_library(paths)
    for probe in probes:
        if probe.state is PathState.READABLE:
            return probe.path
    if spotlight:
        seen = {p.path for p in probes}
        extra = [probe_path(c) for c in spotlight_search() if c not in seen]
        readable = [p for p in extra if p.state is PathState.READABLE]
        if readable:
            readable.sort(key=lambda p: (-p.recording_count, str(p.path)))
            return readable[0].path
    return None

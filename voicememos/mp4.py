"""A minimal reader for the MP4 boxes (atoms) that voicememos needs.

An MP4 or M4A file is a sequence of boxes. Each box starts with a four byte big endian size and a
four character type, followed by a payload. A size of 1 means a 64 bit size follows the type, and
a size of 0 means the box runs to the end of its parent. This module walks that structure with
seeks, so it never reads the audio payload (`mdat`) into memory.

Two things are read from a file:

* the payload of the `tsrp` box, which iOS and macOS use to embed a transcript, and
* the duration from the movie header box (`mvhd`).

Where `tsrp` sits inside the file is inferred, not documented by Apple. The walk looks in the
usual container boxes first. If the file's structure is damaged, it falls back to scanning the
bytes for the marker, which is what the tool this was extracted from did.

A file is untrusted, so every loop is bounded: at most `_MAX_BOXES` boxes are examined per file,
nesting stops at `_MAX_DEPTH`, the byte scan stops after `_MAX_SCAN_BYTES` bytes or
`_MAX_SCAN_HITS` marker hits, and a `tsrp` payload over `_MAX_TSRP_BYTES` is refused. Boxes are
visited one at a time and the walk stops at the first match.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from voicememos.safeio import ABSENT_ERRORS, open_regular

TSRP = b"tsrp"
MVHD = b"mvhd"
MOOV = b"moov"

# Boxes whose payload is a sequence of child boxes.
_CONTAINERS = (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta")
_META = b"meta"

_MAX_DEPTH = 8
_MAX_BOXES = 10_000
_MAX_TSRP_BYTES = 32 * 1024 * 1024
_MAX_SCAN_BYTES = 64 * 1024 * 1024
_MAX_SCAN_HITS = 1_000
_SCAN_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Box:
    """One box located in a file. All offsets are absolute byte positions."""

    kind: bytes
    start: int
    payload_start: int
    end: int


def _parse_header(f: BinaryIO, pos: int, end: int) -> tuple[Box, bool] | None:
    """Parse the box header at `pos`.

    Returns the box, with its end clamped to `end`, and whether the declared size ran past `end`.
    Returns None when the header is unreadable or declares a size smaller than the header.
    """
    f.seek(pos)
    header = f.read(8)
    if len(header) < 8:
        return None
    size, kind = struct.unpack(">I4s", header)
    header_len = 8
    if size == 1:
        extended = f.read(8)
        if len(extended) < 8:
            return None
        (size,) = struct.unpack(">Q", extended)
        header_len = 16
    elif size == 0:
        size = end - pos
    if size < header_len:
        return None
    truncated = pos + size > end
    return Box(kind, pos, pos + header_len, min(pos + size, end)), truncated


class _Walker:
    """Walks the box tree lazily under a shared budget of boxes."""

    def __init__(self, f: BinaryIO, size: int) -> None:
        self.f = f
        self.size = size
        self.examined = 0
        self.exhausted = False
        self.damaged = False

    def children(self, start: int, end: int, *, top: bool = False) -> Iterator[Box]:
        """Yield the sibling boxes between `start` and `end`, one at a time.

        Stops when the box budget is spent. Damage at the top level (an unreadable header, a
        box larger than the file, or bytes left over) sets `damaged`.
        """
        pos = start
        while pos + 8 <= end:
            if self.examined >= _MAX_BOXES:
                self.exhausted = True
                return
            self.examined += 1
            parsed = _parse_header(self.f, pos, end)
            if parsed is None:
                self.damaged = self.damaged or top
                return
            box, truncated = parsed
            yield box
            if truncated:
                self.damaged = self.damaged or top
                return
            pos = box.end
        if pos != end and top:
            self.damaged = True

    def _children_start(self, box: Box) -> int | None:
        """Return where a box's child boxes begin, or None if it is not a container."""
        if box.kind in _CONTAINERS:
            return box.payload_start
        if box.kind == _META:
            # Inferred: Apple writes `meta` as an ISO full box, four bytes of version and flags
            # before the children. A QuickTime style `meta` has no such prefix.
            self.f.seek(box.payload_start)
            prefix = self.f.read(4)
            return box.payload_start + 4 if prefix == b"\x00\x00\x00\x00" else box.payload_start
        return None

    def find(self, kind: bytes, start: int, end: int, depth: int = 0) -> tuple[Box | None, bool]:
        """Find the first box of `kind` in document order, descending into containers.

        Returns the box and whether a top level `moov` box was seen.
        """
        saw_moov = False
        for box in self.children(start, end, top=depth == 0):
            if box.kind == kind:
                return box, saw_moov
            if depth == 0 and box.kind == MOOV:
                saw_moov = True
            child_start = self._children_start(box)
            if child_start is not None and depth < _MAX_DEPTH and child_start < box.end:
                found, _ = self.find(kind, child_start, box.end, depth + 1)
                if found is not None:
                    return found, saw_moov
        return None, saw_moov


def _scan_for_box(f: BinaryIO, kind: bytes, file_size: int) -> Box | None:
    """Scan the start of the file for `kind` and parse the header just before each hit.

    Reads at most `_MAX_SCAN_BYTES` bytes and examines at most `_MAX_SCAN_HITS` hits.
    """
    f.seek(0)
    offset = 0
    carry = b""
    hits = 0
    while offset < _MAX_SCAN_BYTES:
        chunk = f.read(min(_SCAN_CHUNK, _MAX_SCAN_BYTES - offset))
        if not chunk:
            return None
        data = carry + chunk
        base = offset - len(carry)
        index = data.find(kind)
        while index != -1:
            hits += 1
            if hits > _MAX_SCAN_HITS:
                return None
            marker_pos = base + index
            if marker_pos >= 4:
                resume = f.tell()
                parsed = _parse_header(f, marker_pos - 4, file_size)
                f.seek(resume)
                if parsed is not None and parsed[0].kind == kind:
                    return parsed[0]
            index = data.find(kind, index + 1)
        carry = data[-(len(kind) - 1) :]
        offset += len(chunk)
    return None


def read_tsrp_payload(path: Path) -> bytes | None:
    """Return the raw payload of the `tsrp` box in an M4A file, or None.

    None means the file is absent, is a symlink or not a regular file, has no such box, is not a
    readable MP4 structure, exceeds a walking limit, or declares a payload larger than 32 MiB.
    Trailing NUL bytes are removed. A permission error is not caught.
    """
    try:
        f = open_regular(path)
    except ABSENT_ERRORS:
        return None
    with f:
        size = os.fstat(f.fileno()).st_size
        walker = _Walker(f, size)
        box, saw_moov = walker.find(TSRP, 0, size)
        # Scan the bytes only when the structure is damaged or has no movie box. A well formed
        # file with no tsrp has no transcript, and a file that spent its box budget is refused.
        if box is None and not walker.exhausted and (walker.damaged or not saw_moov):
            box = _scan_for_box(f, TSRP, size)
        if box is None:
            return None
        length = box.end - box.payload_start
        if length < 0 or length > _MAX_TSRP_BYTES:
            return None
        f.seek(box.payload_start)
        return f.read(length).rstrip(b"\x00")


def read_duration_seconds(path: Path) -> float | None:
    """Return the duration in seconds from the `mvhd` box, or None.

    Both the 32 bit (version 0) and 64 bit (version 1) layouts are read. None means the file is
    absent or not a regular file, has no movie header, the header is truncated, its time scale is
    zero, or a walking limit was reached. A permission error is not caught.
    """
    try:
        f = open_regular(path)
    except ABSENT_ERRORS:
        return None
    with f:
        size = os.fstat(f.fileno()).st_size
        walker = _Walker(f, size)
        moov = next((b for b in walker.children(0, size, top=True) if b.kind == MOOV), None)
        if moov is None:
            return None
        mvhd = next(
            (b for b in walker.children(moov.payload_start, moov.end) if b.kind == MVHD), None
        )
        if mvhd is None:
            return None
        f.seek(mvhd.payload_start)
        data = f.read(min(32, mvhd.end - mvhd.payload_start))
    if not data:
        return None
    version = data[0]
    if version == 0 and len(data) >= 20:
        _, _, timescale, duration = struct.unpack_from(">IIII", data, 4)
    elif version == 1 and len(data) >= 32:
        _, _, timescale, duration = struct.unpack_from(">QQIQ", data, 4)
    else:
        return None
    if timescale == 0:
        return None
    return float(duration) / float(timescale)

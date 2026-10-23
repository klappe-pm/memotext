"""Builders for synthetic Voice Memos fixtures.

Nothing here is a real recording. An `.m4a` is a minimal MP4 box structure: a `ftyp` box, a
`moov` box holding a movie header and optionally a `tsrp` box, and an `mdat` box of filler bytes.
"""

from __future__ import annotations

import json
import plistlib
import struct
from pathlib import Path
from typing import Any


def box(kind: bytes, payload: bytes = b"") -> bytes:
    """Build one box with a 32 bit size."""
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def large_box(kind: bytes, payload: bytes = b"") -> bytes:
    """Build one box that uses the 64 bit size form."""
    return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload


def mvhd(duration_seconds: float, timescale: int = 1000, version: int = 0) -> bytes:
    """Build a movie header box carrying a duration."""
    ticks = round(duration_seconds * timescale)
    if version == 0:
        body = struct.pack(">B3xIIII", 0, 0, 0, timescale, ticks)
    else:
        body = struct.pack(">B3xQQIQ", 1, 0, 0, timescale, ticks)
    return box(b"mvhd", body + bytes(80))


def tsrp_payload(text: str | None = None, *, runs: list[object] | None = None) -> bytes:
    """Build the JSON payload of a `tsrp` box."""
    if runs is None:
        words = (text or "").split(" ")
        runs = []
        for index, word in enumerate(words):
            runs.extend([word if index == 0 else f" {word}", index])
    data = {"locale": {"identifier": "en_US"}, "attributedString": {"runs": runs}}
    return json.dumps(data).encode("utf-8")


def make_m4a(
    path: Path,
    *,
    transcript: str | None = None,
    duration: float | None = None,
    tsrp: bytes | None = None,
    place: str = "udta",
    mdat_size: int = 256,
) -> Path:
    """Write a synthetic `.m4a` file and return its path.

    `transcript` builds a standard `tsrp` payload; `tsrp` supplies raw payload bytes instead.
    `place` is where the `tsrp` box goes: `udta` (moov/udta), `moov` (directly in moov), `meta`
    (moov/udta/meta with a version and flags prefix), `trak` (moov/trak) or `top` (after moov).
    """
    payload = tsrp if tsrp is not None else (tsrp_payload(transcript) if transcript else None)
    movie = mvhd(duration) if duration is not None else b""
    atom = box(b"tsrp", payload) if payload is not None else b""
    top_level = b""
    if place == "udta":
        movie += box(b"udta", atom) if atom else b""
    elif place == "moov":
        movie += atom
    elif place == "meta":
        movie += box(b"udta", box(b"meta", bytes(4) + atom)) if atom else b""
    elif place == "trak":
        movie += box(b"trak", box(b"mdia", atom)) if atom else b""
    elif place == "top":
        top_level = atom
    else:
        raise ValueError(place)
    data = box(b"ftyp", b"M4A \x00\x00\x00\x00M4A mp42isom")
    data += box(b"moov", movie)
    data += top_level
    data += box(b"mdat", b"\x01" * mdat_size)
    path.write_bytes(data)
    return path


def write_manifest(composition: Path, data: dict[str, Any], *, binary: bool = False) -> Path:
    """Create a `.composition` folder holding a `manifest.plist` and return the plist path."""
    composition.mkdir(parents=True, exist_ok=True)
    manifest = composition / "manifest.plist"
    fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
    manifest.write_bytes(plistlib.dumps(data, fmt=fmt))
    return manifest

"""The `Recording` model and the functions that read recordings from a library folder."""

from __future__ import annotations

import hashlib
import math
import os
import re
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from voicememos.discovery import AUDIO_SUFFIX, PathLike
from voicememos.errors import (
    CompositionLimitError,
    LibraryBlockedError,
    LibraryNotFoundError,
    RecordingSkippedWarning,
)
from voicememos.mp4 import read_duration_seconds, read_tsrp_payload
from voicememos.safeio import (
    ABSENT_ERRORS,
    DirRef,
    close_dir,
    is_real_dir,
    open_child,
    open_dir,
    open_regular,
    scan_dir,
)
from voicememos.textsafe import printable
from voicememos.transcripts import (
    SOURCE_PLIST,
    SOURCE_TSRP,
    read_manifest,
    read_tsrp_transcript,
    transcript_from_manifest,
)

COMPOSITION_SUFFIX = ".composition"

_MAX_WALK_DEPTH = 64
_MAX_WALK_ENTRIES = 100_000

# Voice Memos names files "YYYYMMDD HHMMSS-UUID". The UUID part is inferred to be hex digits and
# dashes. The time is inferred to be local time at the place of recording.
_STEM_DATE = re.compile(
    r"(\d{4})(\d{2})(\d{2}) (\d{2})(\d{2})(\d{2})-[0-9A-F-]+",
    re.IGNORECASE | re.ASCII,
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class Transcript:
    """Transcript text and where it came from."""

    text: str
    source: str
    """`"tsrp"` for the box in the audio file, `"plist"` for the composition manifest."""


@dataclass(frozen=True)
class Recording:
    """One Voice Memos recording."""

    id: str
    """The audio file name without its extension."""
    audio_path: Path
    composition_path: Path | None
    """The `.composition` folder next to the audio file, or None if there is none."""
    recorded_at: datetime
    """When the memo was recorded. Always timezone aware."""
    duration_seconds: float | None
    title: str
    """The title from the manifest, or one built from the recording date."""
    transcript_text: str | None
    transcript_source: str | None
    """`"tsrp"`, `"plist"` or None when there is no transcript."""

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone aware")
        if self.duration_seconds is not None and not math.isfinite(self.duration_seconds):
            raise ValueError("duration_seconds must be finite")

    def to_dict(self, *, include_transcript: bool = True) -> dict[str, Any]:
        """Return a JSON ready dictionary.

        `recorded_at` is an ISO 8601 string and paths are strings. Without `include_transcript`
        the `transcript` key is left out and only `transcript_source` remains.
        """
        data: dict[str, Any] = {
            "id": self.id,
            "audio_path": str(self.audio_path),
            "composition_path": str(self.composition_path) if self.composition_path else None,
            "recorded_at": self.recorded_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "title": self.title,
            "transcript_source": self.transcript_source,
        }
        if include_transcript:
            data["transcript"] = self.transcript_text
        return data


def local_time(moment: datetime) -> datetime:
    """Convert an aware datetime to local time, or return it unchanged if that overflows.

    A date near year 1 or year 9999 cannot always be shifted into the local zone; the aware value
    it already has is correct, so it is used as it is.
    """
    try:
        return moment.astimezone()
    except (OverflowError, ValueError, OSError):
        return moment


def _from_timestamp(seconds: float) -> datetime:
    """Convert a file system time to an aware UTC datetime; out of range values become the epoch."""
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, ValueError, OSError):
        return datetime.fromtimestamp(0, tz=UTC)


def _fallback_title(moment: datetime) -> str:
    moment = local_time(moment)
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return (
        f"Voice Memo {_MONTHS[moment.month - 1]} {moment.day}, {moment.year} "
        f"{hour}:{moment.minute:02d}:{moment.second:02d} {suffix}"
    )


def _date_from_stem(stem: str) -> datetime | None:
    match = _STEM_DATE.fullmatch(stem)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(g) for g in match.groups())
    try:
        naive = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None
    try:
        # A naive datetime converted with astimezone() is read as local time.
        return naive.astimezone()
    except (OverflowError, ValueError, OSError):
        # The local reading falls outside the supported years; read it as UTC instead.
        return naive.replace(tzinfo=UTC)


def _timestamp(st: Any) -> float:
    """Pick the creation time of a stat result, falling back to the modification time.

    `st_birthtime` exists on macOS but not on Linux, so it is read with `getattr`.
    """
    birth = getattr(st, "st_birthtime", None)
    if isinstance(birth, int | float):
        return float(birth)
    return float(st.st_mtime)


def _recorded_at(audio_path: Path, stem: str, manifest: dict[str, Any] | None) -> datetime:
    if manifest is not None:
        created = manifest.get("creationDate")
        if isinstance(created, datetime):
            # Plist dates are UTC by definition and plistlib returns them naive, so a naive
            # value is read as UTC. An aware value is kept as it is.
            return created.replace(tzinfo=UTC) if created.tzinfo is None else created
    from_stem = _date_from_stem(stem)
    if from_stem is not None:
        return from_stem
    # lstat, so a symlink is never followed. FileNotFoundError here means the file vanished after
    # it was listed; the caller skips the recording.
    return _from_timestamp(_timestamp(os.lstat(audio_path)))


def _manifest_duration(manifest: dict[str, Any] | None) -> float | None:
    if manifest is None:
        return None
    value = manifest.get("duration")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        seconds = float(value)
    except OverflowError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _manifest_title(manifest: dict[str, Any] | None) -> str | None:
    if manifest is None:
        return None
    for key in ("title", "customLabel"):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_transcript(audio_path: Path, manifest: dict[str, Any] | None) -> Transcript | None:
    text = read_tsrp_transcript(audio_path)
    if text:
        return Transcript(text, SOURCE_TSRP)
    if manifest is not None:
        text = transcript_from_manifest(manifest)
        if text:
            return Transcript(text, SOURCE_PLIST)
    return None


def _detect_source(audio_path: Path, manifest: dict[str, Any] | None) -> str | None:
    """Say where a transcript lives without decoding the `tsrp` payload.

    A non empty `tsrp` box counts as a transcript in the audio file. Whether its JSON holds text
    is learned only by decoding it, which `read_transcript` does; so for a damaged payload this
    names `tsrp` where `read_transcript` falls back to the manifest or finds nothing.
    """
    payload = read_tsrp_payload(audio_path)
    if payload is not None and payload.strip():
        return SOURCE_TSRP
    if manifest is not None and transcript_from_manifest(manifest):
        return SOURCE_PLIST
    return None


def _load(audio_path: Path, composition_path: Path | None, *, transcripts: bool) -> Recording:
    stem = audio_path.stem
    manifest = read_manifest(composition_path) if composition_path else None
    recorded_at = _recorded_at(audio_path, stem, manifest)
    duration = _manifest_duration(manifest)
    if duration is None:
        duration = read_duration_seconds(audio_path)
    title = _manifest_title(manifest) or _fallback_title(recorded_at)
    if transcripts:
        transcript = _read_transcript(audio_path, manifest)
        text = transcript.text if transcript else None
        source = transcript.source if transcript else None
    else:
        # The text is never decoded or kept, so a long list holds and parses no transcripts.
        text = None
        source = _detect_source(audio_path, manifest)
    return Recording(
        id=stem,
        audio_path=audio_path,
        composition_path=composition_path,
        recorded_at=recorded_at,
        duration_seconds=duration,
        title=title,
        transcript_text=text,
        transcript_source=source,
    )


def _list_audio(library: Path) -> list[Path]:
    try:
        with os.scandir(library) as entries:
            names = sorted(
                entry.name
                for entry in entries
                if entry.name.lower().endswith(AUDIO_SUFFIX)
                and entry.is_file(follow_symlinks=False)
            )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise LibraryNotFoundError(f"recordings folder not found: {library}") from exc
    except OSError as exc:
        raise LibraryBlockedError(
            f"recordings folder exists but cannot be listed: {library} ({exc.strerror or exc})"
        ) from exc
    return [library / name for name in names]


def iter_recordings(
    library_path: PathLike,
    *,
    transcripts: bool = True,
    on_skip: Callable[[Path, OSError], None] | None = None,
) -> Iterator[Recording]:
    """Yield every recording in a library folder, in file name order.

    The folder is listed when the function is called, so a missing or blocked folder raises
    `LibraryNotFoundError` or `LibraryBlockedError` here rather than yielding nothing. Each
    `.m4a` file is paired with a `.composition` folder of the same name when one exists. Files
    other than `.m4a` are ignored, and so is anything that is a symlink: a symlinked audio file
    is not a recording, and a symlinked composition folder is treated as absent. File names that
    start with the date are in time order.

    If an `OSError` stops one recording from being read (a permission error, or a file that
    vanished), that recording is skipped and the rest are still yielded. So is a recording whose
    parsing raises any other exception, which `on_skip` receives as an `OSError` that names the
    exception type. `on_skip` is called with the audio path and the error; without it a
    `RecordingSkippedWarning` is issued.

    With `transcripts=False` each recording's `transcript_text` is None to save memory, while
    `transcript_source` still says where a transcript was found. The `tsrp` payload is not
    decoded in that case, so a non empty `tsrp` box is reported as `"tsrp"` even if its JSON turns
    out to hold no text; `read_transcript` decodes it and gives the true source.
    """
    library = Path(library_path).expanduser()
    audio_files = _list_audio(library)

    def generate() -> Iterator[Recording]:
        for audio in audio_files:
            composition = library / f"{audio.stem}{COMPOSITION_SUFFIX}"
            try:
                recording = _load(
                    audio,
                    composition if is_real_dir(composition) else None,
                    transcripts=transcripts,
                )
            except MemoryError:
                raise
            except Exception as caught:
                # An OSError is the expected reason. Any other exception comes from parsing a
                # hostile file, and it must not end the run either.
                exc = (
                    caught
                    if isinstance(caught, OSError)
                    else OSError(None, f"unreadable ({type(caught).__name__})")
                )
                if on_skip is not None:
                    on_skip(audio, exc)
                else:
                    # The name and the reason come from files, so both are escaped before they can
                    # reach a terminal through the warning.
                    reason = exc.strerror or type(exc).__name__
                    warnings.warn(
                        f"skipped {printable(str(audio))}: {printable(reason)}",
                        RecordingSkippedWarning,
                        stacklevel=2,
                    )
                continue
            yield recording

    return generate()


def read_transcript(recording: Recording) -> Transcript | None:
    """Read the transcript for a recording from its files.

    The `tsrp` box in the audio file wins. If it is absent, the manifest in the composition
    folder is searched. Returns None when neither holds text. The files are read again, so the
    result reflects what is on disk now rather than what `recording` captured.
    """
    manifest = read_manifest(recording.composition_path) if recording.composition_path else None
    return _read_transcript(recording.audio_path, manifest)


def _hash_file(hasher: Any, label: str, f: BinaryIO) -> None:
    hasher.update(f"{label}:{os.fstat(f.fileno()).st_size}\n".encode())
    while chunk := f.read(65536):
        hasher.update(chunk)


def _hash_composition(hasher: Any, composition: Path) -> None:
    """Hash every regular file under a composition folder, in the order of their relative names.

    The walk is iterative, so nesting cannot exhaust the Python stack, and it holds the folders on
    the current path open as descriptors, so a folder swapped for a symlink during the walk is
    refused instead of followed. A folder or file that is a symlink, a FIFO or another special
    kind is ignored, and one that vanished is skipped. A folder that cannot be listed raises its
    `OSError`. A tree deeper than `_MAX_WALK_DEPTH` folders or holding more than
    `_MAX_WALK_ENTRIES` entries raises `CompositionLimitError`.

    Within a folder, files are taken by name and sub folders by name followed by a slash. That
    gives the same order as sorting the full relative names, which keeps the digest stable.
    """
    try:
        root = open_dir(composition)
    except ABSENT_ERRORS:
        return
    # Each frame is a held folder, its relative prefix and its entries still to visit, in reverse.
    frames: list[tuple[DirRef, str, list[tuple[str, bool]]]] = []
    seen = 0
    try:
        frames.append((root, "", _ordered_entries(root)))
        while frames:
            ref, prefix, pending = frames[-1]
            if not pending:
                frames.pop()
                close_dir(ref)
                continue
            name, is_folder = pending.pop()
            seen += 1
            if seen > _MAX_WALK_ENTRIES:
                raise CompositionLimitError(
                    f"composition folder holds more than {_MAX_WALK_ENTRIES} entries"
                )
            if is_folder:
                if len(frames) > _MAX_WALK_DEPTH:
                    raise CompositionLimitError(
                        f"composition folder is nested more than {_MAX_WALK_DEPTH} levels deep"
                    )
                try:
                    child = open_dir(name, parent=ref)
                except ABSENT_ERRORS:
                    continue
                try:
                    entries = _ordered_entries(child)
                except BaseException:
                    close_dir(child)
                    raise
                frames.append((child, f"{prefix}{name}/", entries))
            else:
                try:
                    f = open_child(ref, name)
                except ABSENT_ERRORS:
                    continue
                with f:
                    _hash_file(hasher, f"composition/{prefix}{name}", f)
    finally:
        for ref, _, _ in frames:
            close_dir(ref)


def _ordered_entries(ref: DirRef) -> list[tuple[str, bool]]:
    """List a held folder as `(name, is_folder)`, ordered so a walk visits the last item first.

    The list is in reverse of the visiting order, so `pop()` takes the next item cheaply.
    """
    folders, files = scan_dir(ref)
    keyed = [(f"{name}/", name, True) for name in folders] + [(n, n, False) for n in files]
    keyed.sort(reverse=True)
    return [(name, is_folder) for _, name, is_folder in keyed]


def content_hash(recording: Recording) -> str:
    """Return a SHA 256 hex digest of the recording's files, for change detection.

    The audio file and every file under the composition folder are hashed by content, with the
    relative names mixed in. Modification times are left out, so copying or touching a file does
    not change the digest. Symlinks and other files that are not regular files inside the
    composition folder are ignored. Raises `FileNotFoundError` if the audio file is gone,
    `UnsafeFileError` if it is a symlink or not a regular file, `PermissionError` (or another
    `OSError`) if a file or a folder under the composition folder cannot be read, and
    `CompositionLimitError` if the composition folder is nested deeper than 64 levels or holds
    more than 100,000 entries.
    """
    hasher = hashlib.sha256()
    with open_regular(recording.audio_path) as audio:
        _hash_file(hasher, "audio", audio)
    composition = recording.composition_path
    if composition is not None and is_real_dir(composition):
        _hash_composition(hasher, composition)
    return hasher.hexdigest()

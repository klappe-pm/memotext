# Python API

This page is the reference for the public Python API of the `memotext` package: everything importable from the top level `memotext` module. It lists each name with its signature, what it returns and what it raises. Anything not listed here, including the submodules `mp4` and `transcripts`, is internal and may change. The package has no configuration keys and reads no environment variable of its own; see [cli](cli.md) for the note on environment.

```python
from memotext import (
    KNOWN_PATHS,
    CompositionLimitError,
    LibraryBlockedError,
    LibraryNotFoundError,
    PathProbe,
    PathState,
    Recording,
    RecordingSkippedWarning,
    Transcript,
    UnsafeFileError,
    MemotextError,
    content_hash,
    find_library,
    iter_recordings,
    probe_library,
    probe_path,
    read_transcript,
    spotlight_search,
)
```

## `Recording`

`Recording` is a frozen dataclass describing one recording.

| field | type | meaning |
| --- | --- | --- |
| `id` | `str` | the audio file name without `.m4a`; for example `20250115 143022-ABCD1234` |
| `audio_path` | `Path` | the `.m4a` file |
| `composition_path` | `Path or None` | the `.composition` folder of the same name, or None if there is none |
| `recorded_at` | `datetime` | when the memo was recorded; always timezone aware |
| `duration_seconds` | `float or None` | the length, or None if neither the manifest nor the audio header gives it |
| `title` | `str` | the manifest title, then its `customLabel`, otherwise `Voice Memo Jan 15, 2025 2:30:22 PM` built from the date in local time |
| `transcript_text` | `str or None` | the transcript text, or None |
| `transcript_source` | `str or None` | `"tsrp"`, `"plist"` or None |

Constructing a `Recording` with a naive `recorded_at` raises `ValueError`.

`Recording.to_dict(*, include_transcript=True) -> dict[str, Any]` returns a JSON ready dictionary with the keys `id`, `audio_path`, `composition_path`, `recorded_at` (ISO 8601), `duration_seconds`, `title`, `transcript_source` and, unless `include_transcript` is false, `transcript`. Paths are strings. When the file name is not valid UTF-8 the dictionary also has `id_bytes_hex`, the raw bytes of the id as lowercase hexadecimal text; the key is absent for every other recording. The strings in that case still hold the lone surrogates Python uses for undecodable bytes, which the command line replaces before it writes JSON.

How `recorded_at`, `duration_seconds` and `title` are chosen is described in [file formats](file-formats.md).

## `Transcript`

`Transcript` is a frozen dataclass with `text: str` and `source: str`, where `source` is `"tsrp"` or `"plist"`.

## `iter_recordings`

`iter_recordings(library_path: str | PathLike[str], *, transcripts: bool = True, on_skip: Callable[[Path, OSError], None] | None = None) -> Iterator[Recording]`

Lists the folder immediately and returns an iterator over its recordings in file name order. A leading `~` is expanded. Only regular files ending in `.m4a` (any case) are recordings; each is paired with `<id>.composition` when that is a real folder. A symlink is never a recording and a symlinked `.composition` folder counts as absent.

With `transcripts=False`, `transcript_text` is None for every recording to save memory, while `transcript_source` still says where a transcript was found. The `tsrp` payload is not decoded in this mode, so a non empty `tsrp` box is reported as `"tsrp"` even if its JSON turns out to hold no text; `read_transcript` decodes it and gives the true source. The `list` command uses this.

Raises `LibraryNotFoundError` when the folder is missing or is not a directory, and `LibraryBlockedError` when it exists but cannot be listed. Both are raised by the call itself, not by iterating. A malformed manifest or audio file does not raise; the affected fields are None or fall back.

If an `OSError` stops one recording from being read, such as a permission error or a file that vanished after listing, that recording is skipped and the others are still yielded. So is a recording whose parsing raises any other exception (except `MemoryError`); `on_skip` then receives an `OSError` whose message names the exception type. `on_skip(audio_path, error)` is called for each skipped recording. Without `on_skip`, a `RecordingSkippedWarning` is issued, which Python prints on standard error.

## `read_transcript`

`read_transcript(recording: Recording) -> Transcript | None`

Reads the transcript from the files again. The `tsrp` atom in the audio file is tried first, then the manifest in the composition folder. Returns None when neither holds text. Unlike the `transcript_text` field, the result reflects the files as they are now.

## `content_hash`

`content_hash(recording: Recording) -> str`

Returns a SHA 256 hex digest (64 characters) of the audio file and of every file under the composition folder, in sorted relative path order. File sizes and relative names are part of the input, as UTF-8 bytes (a name that is not valid UTF-8 contributes its original bytes); modification times are not. Symlinks and other files that are not regular files inside the composition folder are ignored. The walk is iterative and holds the folders on its current path open as descriptors, so a folder swapped for a symlink during the walk is refused, not followed.

Raises `FileNotFoundError` if the audio file is gone, `UnsafeFileError` if it is a symlink or not a regular file, and `PermissionError` (or another `OSError`) if a file cannot be read or a folder under the composition folder cannot be listed. A subfolder that cannot be listed is never skipped silently. Raises `CompositionLimitError` if the composition folder is nested more than 64 levels deep or holds more than 100,000 entries. A composition folder that has vanished, or is a symlink, is skipped.

## `find_library`

`find_library(paths: Iterable[str | PathLike[str]] | None = None, *, spotlight: bool = False) -> Path | None`

Returns the first path in the `readable` state, with `~` expanded, or None. Blocked, empty and missing paths are skipped. With `paths=None`, `KNOWN_PATHS` is used. With `spotlight=True`, and only when no listed path is readable, the folders from `spotlight_search` that lie inside a known Voice Memos container under `~/Library` are probed and the readable one with the most recordings is returned, ties broken by path. A folder elsewhere is never adopted, however its path is spelled. See [library states](library-states.md).

## `probe_library`

`probe_library(paths: Iterable[str | PathLike[str]] | None = None) -> list[PathProbe]`

Probes each path and returns the results in the same order. With `paths=None`, `KNOWN_PATHS` is used.

## `probe_path`

`probe_path(path: str | PathLike[str]) -> PathProbe`

Probes one path by listing it. It does not raise for a missing or blocked path; the outcome is the returned state.

## `PathProbe`

`PathProbe` is a frozen dataclass.

| field | type | meaning |
| --- | --- | --- |
| `path` | `Path` | the path with `~` expanded |
| `state` | `PathState` | one of the four states |
| `recording_count` | `int` | number of `.m4a` files; 0 unless the state is `readable` |
| `detail` | `str or None` | the operating system's message for `missing` and `blocked`; None otherwise |

`PathProbe.to_dict() -> dict[str, object]` returns `path`, `state` (the string value), `recording_count` and `detail`.

## `PathState`

`PathState` is a `StrEnum` with the members `MISSING = "missing"`, `READABLE = "readable"`, `BLOCKED = "blocked"` and `EMPTY = "empty"`.

## `KNOWN_PATHS`

`KNOWN_PATHS: tuple[Path, ...]` holds the five default locations, each starting with `~`. The list is in [library states](library-states.md).

## `spotlight_search`

`spotlight_search(runner: Callable[[list[str]], str] | None = None) -> list[Path]`

Asks Spotlight for candidate folders and returns the parent folder of each hit, once each, in the order found. Without `runner` it runs `/usr/bin/mdfind`, by that absolute path and not through `PATH`, with a 30 second timeout, and works only on macOS; elsewhere, or when that program is missing or fails, it returns an empty list. A `runner` takes the `mdfind` arguments and returns its text output, which lets a test supply canned output on any platform. It never raises for a failed search.

## Errors

| class | bases | raised when |
| --- | --- | --- |
| `MemotextError` | `Exception` | base class of the errors below |
| `LibraryNotFoundError` | `MemotextError`, `FileNotFoundError` | the recordings folder does not exist or is not a directory |
| `LibraryBlockedError` | `MemotextError`, `PermissionError` | the recordings folder exists but listing it failed |
| `UnsafeFileError` | `MemotextError`, `OSError` | `content_hash` was given a recording whose audio file is a symlink or not a regular file; parsers treat such a file as absent instead |
| `CompositionLimitError` | `MemotextError` | `content_hash` was given a recording whose composition folder is nested more than 64 levels deep or holds more than 100,000 entries |
| `RecordingSkippedWarning` | `UserWarning` | issued by `iter_recordings` for a recording skipped because any exception other than `MemoryError` stopped it being read, an `OSError` or an error from parsing a hostile file; issued only when no `on_skip` callback is given; a warning, not an exception |

## Version

`memotext.__version__` is the version string, `"0.1.0"`.

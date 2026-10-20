"""Exceptions raised by voicememos.

Every error the library raises on purpose derives from `VoiceMemosError`, so a caller can catch
one class. The two library errors also derive from the matching built in `OSError` subclass, so
code that already handles `FileNotFoundError` or `PermissionError` keeps working.
"""

from __future__ import annotations


class VoiceMemosError(Exception):
    """Base class for every error voicememos raises on purpose."""


class UnsafeFileError(VoiceMemosError, OSError):
    """A file that must be a regular file is a symlink, a FIFO, a device or a directory.

    Parsers treat such a file as absent. `content_hash` raises it for the audio file.
    """


class RecordingSkippedWarning(UserWarning):
    """A recording was skipped because one of its files could not be read."""


class LibraryNotFoundError(VoiceMemosError, FileNotFoundError):
    """The recordings folder does not exist, or is not a directory."""


class LibraryBlockedError(VoiceMemosError, PermissionError):
    """The recordings folder exists but cannot be listed.

    On macOS this is what a missing Full Disk Access grant looks like. The folder is present, so
    it is never reported as missing or empty.
    """


class CompositionLimitError(VoiceMemosError):
    """A composition folder is nested too deeply or holds too many entries to hash.

    `content_hash` raises it when the folder is nested more than 64 levels deep or holds more than
    100,000 entries. A real composition folder holds a few files, so a folder over either limit is
    not a Voice Memos recording and its digest is refused rather than computed.
    """

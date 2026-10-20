"""Read the Apple Voice Memos library on macOS.

The package finds the recordings folder, lists recordings with their recorded date, duration and
title, and extracts the transcript that iOS already produced. It does not transcribe, call a
language model, write notes or use the network.
"""

from voicememos.discovery import (
    KNOWN_PATHS,
    PathProbe,
    PathState,
    find_library,
    probe_library,
    probe_path,
    spotlight_search,
)
from voicememos.errors import (
    CompositionLimitError,
    LibraryBlockedError,
    LibraryNotFoundError,
    RecordingSkippedWarning,
    UnsafeFileError,
    VoiceMemosError,
)
from voicememos.recording import (
    Recording,
    Transcript,
    content_hash,
    iter_recordings,
    read_transcript,
)

__version__ = "0.1.0"

__all__ = [
    "KNOWN_PATHS",
    "CompositionLimitError",
    "LibraryBlockedError",
    "LibraryNotFoundError",
    "PathProbe",
    "PathState",
    "Recording",
    "RecordingSkippedWarning",
    "Transcript",
    "UnsafeFileError",
    "VoiceMemosError",
    "__version__",
    "content_hash",
    "find_library",
    "iter_recordings",
    "probe_library",
    "probe_path",
    "read_transcript",
    "spotlight_search",
]

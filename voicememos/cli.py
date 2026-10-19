"""The `voicememos` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from voicememos import __version__
from voicememos.discovery import PathState, find_library, probe_library
from voicememos.errors import LibraryBlockedError, LibraryNotFoundError, VoiceMemosError
from voicememos.recording import Recording, iter_recordings, local_time, read_transcript
from voicememos.textsafe import printable

EXIT_OK = 0
EXIT_ERROR = 1

FULL_DISK_ACCESS_HINT = (
    "Grant Full Disk Access to the terminal or interpreter that runs this command: "
    "System Settings, Privacy and Security, Full Disk Access."
)


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--spotlight",
        action="store_true",
        help="when no known path is readable, also ask Spotlight (macOS only)",
    )

    parser = argparse.ArgumentParser(
        prog="voicememos",
        description="Read the Apple Voice Memos library: list recordings and show transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"voicememos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser(
        "probe", parents=[common], help="report the state of each known recordings folder"
    )
    probe.add_argument("--json", action="store_true", help="print machine readable JSON")

    listing = sub.add_parser("list", parents=[common], help="list recordings, newest first")
    listing.add_argument("--library", metavar="PATH", help="use this recordings folder")
    listing.add_argument("--json", action="store_true", help="print machine readable JSON")

    show = sub.add_parser("show", parents=[common], help="show one recording and its transcript")
    show.add_argument("id", help="a recording id, or a prefix that matches exactly one")
    show.add_argument("--library", metavar="PATH", help="use this recordings folder")
    show.add_argument("--json", action="store_true", help="print machine readable JSON")
    return parser


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_recorded(recording: Recording) -> str:
    return local_time(recording.recorded_at).strftime("%Y-%m-%d %H:%M")


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _dump(data: object) -> str:
    """Serialise to JSON that every parser accepts: no NaN or Infinity, ASCII only."""
    return json.dumps(data, indent=2, allow_nan=False)


def _warn_skipped(audio: Path, error: OSError) -> None:
    reason = error.strerror or type(error).__name__
    print(
        f"voicememos: warning: skipped {printable(str(audio))}: {printable(reason)}",
        file=sys.stderr,
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Format a table. Every cell is escaped first, so a cell can never hold a line break."""
    rows = [[printable(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row, strict=True)]
    lines = [
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip()
        for row in (headers, *rows)
    ]
    return "\n".join(lines)


def _library_for(explicit: str | None, spotlight: bool) -> Path:
    """Resolve the folder to read, or raise a library error that says why none was found."""
    if explicit:
        return Path(explicit).expanduser()
    found = find_library(spotlight=spotlight)
    if found is not None:
        return found
    blocked = [p for p in probe_library() if p.state is PathState.BLOCKED]
    if blocked:
        names = ", ".join(str(p.path) for p in blocked)
        raise LibraryBlockedError(
            f"found a recordings folder that cannot be listed: {names}. {FULL_DISK_ACCESS_HINT}"
        )
    raise LibraryNotFoundError(
        "no readable Voice Memos folder found. Run `voicememos probe` to see each path checked, "
        "or pass --library PATH."
    )


def _cmd_probe(args: argparse.Namespace) -> int:
    probes = probe_library()
    found = find_library(spotlight=args.spotlight)
    if args.json:
        payload = {
            "library": str(found) if found else None,
            "paths": [p.to_dict() for p in probes],
        }
        print(_dump(payload))
    else:
        rows = [
            [
                p.state.value,
                str(p.recording_count) if p.state is PathState.READABLE else "",
                str(p.path),
            ]
            for p in probes
        ]
        print(_table(("STATE", "RECORDINGS", "PATH"), rows))
        if any(p.state is PathState.BLOCKED for p in probes):
            print(f"\n{FULL_DISK_ACCESS_HINT}")
        print(f"\nlibrary: {printable(str(found))}" if found else "\nlibrary: none readable")
    return EXIT_OK if found else EXIT_ERROR


def _cmd_list(args: argparse.Namespace) -> int:
    library = _library_for(args.library, args.spotlight)
    # Transcript text is never needed for a list, so it is not kept: a library of long
    # transcripts would otherwise sit in memory until the table is printed.
    recordings = sorted(
        iter_recordings(library, transcripts=False, on_skip=_warn_skipped),
        key=lambda r: r.recorded_at,
        reverse=True,
    )
    if args.json:
        data = [r.to_dict(include_transcript=False) for r in recordings]
        print(_dump(data))
        return EXIT_OK
    rows = [
        [
            r.id,
            _format_recorded(r),
            _format_duration(r.duration_seconds),
            r.transcript_source or "none",
            _shorten(r.title, 40),
        ]
        for r in recordings
    ]
    print(_table(("ID", "RECORDED", "DURATION", "TRANSCRIPT", "TITLE"), rows))
    return EXIT_OK


def _match(recordings: list[Recording], wanted: str) -> Recording:
    for recording in recordings:
        if recording.id == wanted:
            return recording
    prefixed = [r for r in recordings if r.id.startswith(wanted)]
    if len(prefixed) == 1:
        return prefixed[0]
    if prefixed:
        ids = ", ".join(r.id for r in prefixed)
        raise VoiceMemosError(f"id {wanted!r} is ambiguous, it matches: {ids}")
    raise VoiceMemosError(f"no recording with id {wanted!r}")


def _cmd_show(args: argparse.Namespace) -> int:
    library = _library_for(args.library, args.spotlight)
    found = _match(
        list(iter_recordings(library, transcripts=False, on_skip=_warn_skipped)), args.id
    )
    transcript = read_transcript(found)
    recording = replace(found, transcript_text=transcript.text if transcript else None)
    if args.json:
        print(_dump(recording.to_dict()))
        return EXIT_OK
    recorded = local_time(recording.recorded_at).isoformat(timespec="seconds")
    print(f"title: {printable(recording.title)}")
    print(f"id: {printable(recording.id)}")
    print(f"recorded: {recorded}")
    print(f"duration: {_format_duration(recording.duration_seconds)}")
    print(f"audio: {printable(str(recording.audio_path))}")
    print(f"composition: {printable(str(recording.composition_path or 'none'))}")
    print(f"transcript source: {recording.transcript_source or 'none'}")
    if recording.transcript_text:
        print(f"\n{printable(recording.transcript_text, keep_newlines=True)}")
    return EXIT_OK


_COMMANDS = {"probe": _cmd_probe, "list": _cmd_list, "show": _cmd_show}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and return the exit status.

    Exit statuses: 0 on success, 1 when no readable library is found, a library cannot be
    listed, or a recording id does not match, and 2 for a usage error.
    """
    args = _build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (VoiceMemosError, OSError) as exc:
        print(f"voicememos: {printable(str(exc))}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

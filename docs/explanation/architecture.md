# Architecture

This page explains how voicememos turns a Voice Memos folder into `Recording` objects, for a contributor who needs the shape of the code before changing a layer. It describes the layers from the bottom up, the rule each layer follows for failures, and the places where the design deliberately keeps work lazy or eager. The module list is in [source layout](../reference/source-layout.md); the user-facing reasoning is in [design](design.md).

## The Layers

1. Bytes. `mp4.py` reads boxes from one `.m4a` file by seeking. It answers two questions: what is the payload of the `tsrp` box, and what is the `mvhd` duration. It knows nothing about transcripts or recordings.
2. Text. `transcripts.py` turns a `tsrp` payload into text, reads `manifest.plist` into a dictionary, and searches that dictionary for text. It knows the JSON and plist shapes and nothing about folders.
3. Recording. `recording.py` pairs an `.m4a` with its `.composition` folder, chooses each field by a fixed order of sources, and returns a frozen `Recording`.
4. Discovery. `discovery.py` decides which folder to read. It only lists directories and counts files; it never opens a recording.
5. Interface. `cli.py` calls the layers above and formats the result.

Dependencies point down only. Discovery and the byte layer do not know each other.

## Failure Rules

Each layer has one rule for what an error means, and the rule is what keeps a blocked folder visible.

- A malformed or absent file is a normal outcome of reading a library written by other programs. The byte and text layers return None for it: a missing box, a damaged structure, invalid JSON or an unreadable plist.
- A symlink, a FIFO or any file that is not a regular file is treated as absent. `safeio.open_regular` opens every file with `O_NOFOLLOW` and `O_NONBLOCK` and checks the type with `fstat`, so such a file is refused without blocking.
- A permission error is never normal. It means the process may not read something that exists, and it is not converted to None by the byte and text layers. Reading a file that cannot be opened raises `PermissionError`, so a recording whose files are blocked is never mistaken for one with no transcript. The recording layer catches the `OSError` for that one recording, skips it and reports it through `on_skip` or a `RecordingSkippedWarning`, so one bad file does not hide the rest.
- The two failures of listing a folder have their own exception classes. `iter_recordings` raises `LibraryNotFoundError` for a missing folder and `LibraryBlockedError` for a folder that exists and cannot be listed. `probe_path` does not raise for either; it returns the state.
- The interface catches `VoiceMemosError` and `OSError` and turns them into a message on standard error and exit status 1. Everything it prints from a file goes through `textsafe.printable`.

Every loop that a file's content controls is bounded; the limits are listed in the [security model](security-model.md).

## Lazy and Eager

`iter_recordings` lists the folder eagerly, when it is called, and builds each `Recording` lazily as the iterator advances. Listing eagerly puts the folder errors at the call site where the caller can handle them. Building lazily means a caller who stops early does not read the rest. The command-line `list` sorts by date, so it consumes the whole iterator.

Reading a recording opens the audio file once to find the `tsrp` atom and once more for the duration, and opens the manifest once. Both audio reads seek, so the cost is a handful of small reads per file regardless of its size.

## The Box Walker

The walker reads a header, records the box, and moves to the next sibling by the declared size. It descends only into a fixed list of container boxes. It returns the boxes it found together with a flag for whether they tiled their parent exactly. The flag is how the `tsrp` search decides whether a failed lookup means "this file has no transcript" or "this file is damaged, scan the bytes". Keep that distinction when changing the walker: scanning every file that has no transcript would read every audio file in full.

## Choosing Fields

`_load` in `recording.py` is the one place that decides which source wins for each field. The orders are listed in [file formats](../reference/file-formats.md#how-recording-fields-are-chosen). Change the order there and in that table together, and add a test for the new case.

## Time

All dates inside `Recording` are aware. Naive values are converted where they are read: `plistlib` dates as UTC, the date in a file name as local time through `datetime.astimezone()`, and file system times as UTC. Tests control the local zone through the `set_timezone` fixture.

## What the Tests Cannot Show

The tests prove the code handles the structures `tests/synthetic.py` builds. They cannot prove that real Voice Memos files look like those structures. Every claim about the real formats is marked inferred in the reference pages for that reason, and the first thing to do with a real failure is to describe the real structure and build the smallest synthetic file that has it.

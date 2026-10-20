# security-model

This page explains what voicememos reads, what it never does, how it treats files it did not create, and where the real privacy risk sits. Every claim here describes behaviour the code enforces and the tests check, and every limit is stated as a number. It is for a reader deciding whether to run the package against a personal Voice Memos library or to build on it. It is explanation, not procedure: to report a vulnerability, follow [security.md](../../security.md).

## what-it-reads

voicememos lists the recordings folder, opens the `.m4a` files and the `manifest.plist` file in each `.composition` folder for reading, and reads the home directory setting to expand `~`. With `--spotlight` on macOS it also runs one program, `/usr/bin/mdfind`. Nothing else is read.

## what-it-never-does

- It does not use the network. No module opens a socket or imports a network library.
- It does not write, move or delete any file, and it creates no configuration, cache or state file.
- It does not transcribe audio or send audio or text to any service.
- It does not change a permission, open System Settings or request elevated rights.
- It runs no program except `mdfind`. That program is called as `/usr/bin/mdfind`, not found through `PATH`, so a program of the same name elsewhere is never run. It is called with a fixed argument list, never through a shell, with a 30 second timeout, only on macOS, and only when asked for with `--spotlight` or `spotlight=True`.

## untrusted-files

A library is a folder of files that other programs and other devices wrote, so every file is treated as untrusted. The limits below are constants in the source; a file that exceeds one is read as having no value, not as an error.

### how-files-are-opened

Every file is opened with `O_NOFOLLOW` and `O_NONBLOCK` and then checked with `fstat` to be a regular file.

- A symlink as the final path component is refused. A symlinked `.m4a` is not listed as a recording and is not counted by `probe`. A symlinked `.composition` folder is treated as absent. A symlinked `manifest.plist` is treated as absent. Symlinks inside a composition folder are not hashed by `content_hash`, and a symlinked audio file makes `content_hash` raise `UnsafeFileError`. Nothing a symlink points to is read.
- A FIFO, socket, device or directory in place of a file is refused without blocking, because `O_NONBLOCK` makes the open return at once. Such a file is treated as absent.
- The folder you name, or the first known path that is readable, is itself followed if it is a symlink. That is your choice. Only the entries inside it are protected.
- A file can still be swapped between the check and the read by a process with write access to the folder. The open and the `fstat` use the same descriptor, which closes the gap for the file type, but not for its content.

### mp4-structure

| limit | value |
| --- | --- |
| boxes examined per file | 10,000 |
| nesting depth | 8 |
| `tsrp` payload size | 32 MiB (33,554,432 bytes); a larger payload is refused |
| `mvhd` bytes read | 32 |
| fallback byte scan, bytes read | 64 MiB (67,108,864 bytes) |
| fallback byte scan, marker hits examined | 1,000 |

Boxes are visited one at a time and the walk stops at the first match, so a file made of millions of tiny boxes costs 10,000 header reads, not memory for all of them. A box that claims to be larger than its parent is clamped to the parent and the file is treated as damaged. The audio data is never read during the walk. The byte scan runs only when the top level structure is damaged or has no movie box; a file that spends its box budget is not scanned.

### transcript-and-manifest

| limit | value |
| --- | --- |
| `manifest.plist` size | 16 MiB (16,777,216 bytes); a larger file is treated as absent |
| search depth in a parsed manifest | 32 levels |
| values examined in one search | 100,000 |
| times one list or dictionary is examined | once |

The `tsrp` payload is decoded with the standard library JSON parser and the manifest with `plistlib`. Neither runs code. A parser failure of any kind is caught and the file is treated as having no transcript or no manifest. That covers exhausting the Python stack on deeply nested input and the odd exceptions that `plistlib` raises on a hostile file (an `AttributeError` from a malformed date, an `IndexError`, a `LookupError` from an unknown encoding name). Only an `OSError` such as a permission error, and `MemoryError`, are allowed to escape. The manifest search is iterative, not recursive, so nesting cannot raise `RecursionError`. Because each list or dictionary is examined once, a binary plist in which many entries share the same object costs time in proportion to its distinct objects, not to the number of paths through it.

### numbers-and-dates

A manifest duration that is not a number, is a boolean, is negative, is not finite (`nan`, `inf`) or does not fit in a float is ignored, and the duration is read from the audio file instead. `Recording` refuses a non finite duration. JSON output is written with NaN and Infinity forbidden, so it is valid JSON for every parser. A date that cannot be converted to local time, such as year 1 or year 9999 near a timezone boundary, is kept in UTC instead of raising; a file time outside the supported range becomes 1970-01-01 UTC.

## what-is-not-limited

These are not capped, and a hostile library can use them.

- The number of files in the library folder. `list` and `show` read every `.m4a` file.
- The number of files under a composition folder, and the size of any file `content_hash` reads. Hashing streams each file in 64 KiB pieces, so memory stays small, but time grows with the data.
- Memory while decoding a `tsrp` payload. A payload of 32 MiB of JSON can use several times that while it is parsed. `list` keeps no transcript text between recordings; `show` holds the text of the one recording it prints.
- Time spent in the operating system reading a very large file from a slow disk or a stalled network volume.

## terminal-output

Titles, transcripts, file names and error messages come from files, and a terminal treats some bytes as commands. All human readable output goes through one function that escapes them.

- C0 control characters U+0000 to U+001F (including ESC, BEL and newline), DEL (U+007F) and the C1 controls U+0080 to U+009F are printed as `\xNN`, with `\n`, `\r` and `\t` for those three.
- The line and paragraph separators U+2028 and U+2029, the zero width characters U+200B to U+200F, the bidirectional controls U+202A to U+202E and U+2066 to U+2069, and U+FEFF are printed as `\uNNNN`.
- A lone surrogate, which cannot be encoded, is printed as `?`.
- Table cells in `list` and `probe` are escaped before they are laid out, so a cell never contains a line break and cannot forge another row.
- In `show`, every field is escaped. The transcript keeps its line feeds so it stays readable; every other control character in it is still escaped.
- Error messages, warnings and paths are escaped the same way.
- `--json` output is ASCII only, with every non ASCII character written as a `\u` escape.

A backslash in the source text is not escaped, so a title that literally contains `\x1b` looks the same as one that contains the escape character. Use `--json` when that difference matters.

## failures

- A permission error while reading one recording's files does not stop the run. The recording is skipped, a `RecordingSkippedWarning` is issued (the command line prints `voicememos: warning: skipped <path>: <reason>` on standard error), and the rest are listed. The command still exits 0, so a script that must notice skips should read standard error or call `iter_recordings` with `on_skip`.
- A folder that exists and cannot be listed is never reported as missing or empty: it raises `LibraryBlockedError`, or is reported `blocked` by `probe`.
- A file that vanishes between listing and reading is skipped the same way.
- A recording whose parsing raises any other unexpected exception is skipped the same way. `on_skip` receives an `OSError` whose message names the exception type, so one hostile file never ends the run.

## privacy

The risk with a Voice Memos library is its content, not the package. Recordings and transcripts are often personal or confidential, and a transcript is plain text that is easy to copy. The package returns that text to the program that called it; what that program does with it is outside this package's control. The package logs nothing, and the command prints transcript text only to your terminal when you run `show`.

Full Disk Access is a broad grant: the application that has it can read much of your account, not only Voice Memos. Grant it to the single application that runs the command, prefer a terminal you already trust, and revoke it if you no longer need it. A scheduled job that needs the grant gives it to its interpreter, so use a dedicated interpreter for such jobs.

## in-the-repository

Tests build synthetic recordings and never read a real library, the live home directory or the network. The hostile input cases are in `tests/test_hardening.py`, each with a deadline so a regression fails instead of hanging. Contributors are asked never to commit a real recording, transcript or manifest. Bug reports should describe a file's structure or attach a synthetic file instead.

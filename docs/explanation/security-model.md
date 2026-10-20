# Security Model

This page explains what voicememos reads, what it never does, how it treats files it did not create, and where the real privacy risk sits. Every claim here describes behaviour the code enforces and the tests check, and every limit is stated as a number. It is for a reader deciding whether to run the package against a personal Voice Memos library or to build on it. It is explanation, not procedure: to report a vulnerability, follow [security.md](../../SECURITY.md).

## What It Reads

voicememos lists the recordings folder, opens the `.m4a` files and the `manifest.plist` file in each `.composition` folder for reading, and reads the home directory setting to expand `~`. With `--spotlight` on macOS it also runs one program, `/usr/bin/mdfind`. Nothing else is read.

## What It Never Does

- It does not use the network. No module opens a socket or imports a network library.
- It does not write, move or delete any file, and it creates no configuration, cache or state file.
- It does not transcribe audio or send audio or text to any service.
- It does not change a permission, open System Settings or request elevated rights.
- It runs no program except `mdfind`. That program is called as `/usr/bin/mdfind`, not found through `PATH`, so a program of the same name elsewhere is never run. It is called with a fixed argument list, never through a shell, with a 30 second timeout, only on macOS, and only when asked for with `--spotlight` or `spotlight=True`. Its results are not trusted either: only a folder inside a known Voice Memos container under `~/Library` can be chosen, and the command line says on standard error when Spotlight chose the folder.

## Untrusted Files

A library is a folder of files that other programs and other devices wrote, so every file is treated as untrusted. The limits below are constants in the source; a file that exceeds one is read as having no value, not as an error.

### How Files Are Opened

Every file is opened with `O_NOFOLLOW` and `O_NONBLOCK` and then checked with `fstat` to be a regular file.

- A symlink as the final path component is refused. A symlinked `.m4a` is not listed as a recording and is not counted by `probe`. A symlinked `.composition` folder is treated as absent. A symlinked `manifest.plist` is treated as absent. Symlinks inside a composition folder are not hashed by `content_hash`, and a symlinked audio file makes `content_hash` raise `UnsafeFileError`. Nothing a symlink points to is read.
- A FIFO, socket, device or directory in place of a file is refused without blocking, because `O_NONBLOCK` makes the open return at once. Such a file is treated as absent.
- The folder you name, or the first known path that is readable, is itself followed if it is a symlink. That is your choice. Only the entries inside it are protected.
- A `.composition` folder is opened with `O_DIRECTORY` and `O_NOFOLLOW`, and `manifest.plist` is then opened relative to that descriptor with `O_NOFOLLOW`. A folder that a process with write access swaps for a symlink after the check is refused instead of followed, so nothing outside the library is read. `content_hash` walks the folder from a descriptor in the same way.
- A composition folder with search permission only (mode `0311`, which can be entered but not listed) cannot be opened for reading. When opening it fails with `EACCES`, `read_manifest` opens `manifest.plist` by its path with the same `O_NOFOLLOW` regular file opener, so the recording keeps its title and the manifest is not mistaken for a skipped file. A symlinked manifest is still refused. Only the swap protection for the folder itself is lost, and only for a folder the process may not list. Any other permission error still raises.
- The library folder you name is followed as given, as the previous point says. The `.m4a` files inside it are each opened with `O_NOFOLLOW`, so an entry swapped for a symlink after it was listed is refused.
- A file can still be modified between the check and the read by a process with write access to the folder. The open and the `fstat` use the same descriptor, which closes the gap for the file type, but not for its content.
- A platform without descriptor relative opens (Windows) falls back to paths and `lstat` checks, which cannot close the swap race. The race needs a hostile writer in the library folder.

### MP4 Structure

| limit | value |
| --- | --- |
| boxes examined per file | 10,000 |
| nesting depth | 8 |
| `tsrp` payload size | 32 MiB (33,554,432 bytes); a larger payload is refused |
| `mvhd` bytes read | 32 |
| fallback byte scan, bytes read | 64 MiB (67,108,864 bytes) |
| fallback byte scan, marker hits examined | 1,000 |

Boxes are visited one at a time and the walk stops at the first match, so a file made of millions of tiny boxes costs 10,000 header reads, not memory for all of them. A box that claims to be larger than its parent is clamped to the parent and the file is treated as damaged. The audio data is never read during the walk. The byte scan runs only when the top level structure is damaged or has no movie box; a file that spends its box budget is not scanned.

### Transcript and Manifest

| limit | value |
| --- | --- |
| `manifest.plist` size | 16 MiB (16,777,216 bytes); a larger file is treated as absent |
| search depth in a parsed manifest | 32 levels |
| values examined in one search | 100,000 |
| times one list or dictionary is examined | once |

The `tsrp` payload is decoded with the standard library JSON parser and the manifest with `plistlib`. Neither runs code. A parser failure of any kind is caught and the file is treated as having no transcript or no manifest. That covers exhausting the Python stack on deeply nested input and the odd exceptions that `plistlib` raises on a hostile file (an `AttributeError` from a malformed date, an `IndexError`, a `LookupError` from an unknown encoding name). Only an `OSError` such as a permission error, and `MemoryError`, are allowed to escape. The manifest search is iterative, not recursive, so nesting cannot raise `RecursionError`. Because each list or dictionary is examined once, a binary plist in which many entries share the same object costs time in proportion to its distinct objects, not to the number of paths through it.

### Numbers and Dates

A manifest duration that is not a number, is a boolean, is negative, is not finite (`nan`, `inf`) or does not fit in a float is ignored, and the duration is read from the audio file instead. `Recording` refuses a non finite duration. JSON output is written with NaN and Infinity forbidden, so it is valid JSON for every parser. A date that cannot be converted to local time, such as year 1 or year 9999 near a timezone boundary, is kept in UTC instead of raising; a file time outside the supported range becomes 1970-01-01 UTC.

### Composition Folder Walk

| limit | value |
| --- | --- |
| folder nesting depth under a composition folder | 64 |
| entries (files and folders) examined in one walk | 100,000 |

`content_hash` walks the composition folder iteratively, so deep nesting cannot raise `RecursionError`, and it holds only the folders on the current path open, at most 66 descriptors. A folder over either limit raises `CompositionLimitError`; a real composition folder holds a few files. Every descriptor is closed on every path out, including when the first listing fails. A folder that cannot be listed raises its `OSError` instead of being skipped, because a hash that silently leaves out an unreadable subfolder would miss a change inside it.

## What Is Not Limited

These are not capped, and a hostile library can use them.

- The number of files in the library folder. `list` and `show` read every `.m4a` file.
- The size of any file `content_hash` reads. Hashing streams each file in 64 KiB pieces, so memory stays small, but time grows with the data. The shape of the composition folder is limited, as the next section says.
- Memory while decoding a `tsrp` payload. A payload of 32 MiB of JSON can use several times that while it is parsed. `list` keeps no transcript text between recordings; `show` holds the text of the one recording it prints.
- Time spent in the operating system reading a very large file from a slow disk or a stalled network volume.

## Terminal Output

Titles, transcripts, file names and error messages come from files, and a terminal treats some bytes as commands. All human readable output goes through one function that escapes them.

- C0 control characters U+0000 to U+001F (including ESC, BEL and newline), DEL (U+007F) and the C1 controls U+0080 to U+009F are printed as `\xNN`, with `\n`, `\r` and `\t` for those three.
- Every character in the Unicode categories `Cf` (format), `Cn` (unassigned), `Co` (private use), `Zl` (line separator) and `Zp` (paragraph separator) is escaped. A character that is not assigned has no defined appearance, and a private use character is drawn as whatever the font says, so neither can be trusted to show what it seems to. The `Cf` category covers the line and paragraph separators U+2028 and U+2029, the soft hyphen U+00AD, the Arabic letter mark U+061C, the zero width characters U+200B to U+200F, the bidirectional controls U+202A to U+202E and U+2066 to U+2069, the invisible operators U+2060 to U+2064 and U+206A to U+206F, U+FEFF, the interlinear annotation marks U+FFF9 to U+FFFB and the tag characters U+E0001 and U+E0020 to U+E007F.
- Every code point with the Unicode property `Default_Ignorable_Code_Point` is escaped, whatever its category. These are the code points a renderer draws as nothing. Besides the format characters above they include the combining grapheme joiner U+034F, the Hangul fillers U+115F, U+1160, U+3164 and U+FFA0, the Khmer vowels U+17B4 and U+17B5, the variation selectors U+180B to U+180F, U+FE00 to U+FE0F and U+E0100 to U+E01EF, the unassigned code points U+2065 and U+FFF0 to U+FFF8, the musical and shorthand format controls U+1BCA0 to U+1BCA3 and U+1D173 to U+1D17A, and the whole tag block with the unassigned block after it, U+E0000 to U+E0FFF. The tag block matters most: each tag character mirrors an ASCII letter, so a title can carry hidden text that a person does not see but a program that reads the output does. The Unicode character database in the Python standard library does not expose the property, so the ranges are written out in `voicememos/textsafe.py` from Unicode 15.0.
- The 66 noncharacters, U+FDD0 to U+FDEF and the last two code points of each plane, are escaped too.
- Two assigned characters that draw as blank without being default ignorable are escaped as well: the braille pattern blank U+2800 and the musical symbol null notehead U+1D159. Left alone, a name that held one would print the same as the name without it. Other braille patterns draw dots and are printed as themselves.
- Three of those characters are printed as themselves where they make part of an emoji, because escaping them would break a heart or a family into pieces: the variation selectors U+FE0E and U+FE0F, and the zero width joiner U+200D. A selector is kept when it follows an emoji character directly, or follows a digit, `#` or `*` that a keycap (U+20E3) comes after. A joiner is kept when it sits between two emoji characters, where the first may carry a kept selector. So `❤️` and `👨‍👩‍👧` print unchanged. A selector or joiner that leads the text, trails it, follows a selector or a joiner, or stands beside a character that is not an emoji is escaped, so a run of them cannot carry hidden bits: after an emoji, at most one selector survives. Every other variation selector (U+180B to U+180F, U+FE00 to U+FE0D, U+E0100 to U+E01EF) is always escaped, which includes the ideographic variation selectors used for some Japanese names. The emoji set is the `Emoji` property of Unicode 15.0 written out in `voicememos/textsafe.py`. A character that the running Python's own Unicode database does not yet assign, such as an emoji added in a newer Unicode than that Python knows, is escaped as unassigned.
- The check is cheap. Each distinct character in a text is judged once and the text is rewritten in a single pass, so text with nothing to escape comes back as it is; escaping 11 million CJK characters takes about 0.4 seconds. A selector or joiner is judged where it stands, so the cost grows with their number, not with the length of the text.
- A character below U+0100 is written `\xNN`, one up to U+FFFF is written `\uNNNN`, and one above is written `\UNNNNNNNN`.
- A lone surrogate, which cannot be encoded, is printed as `?`.
- Spaces are printed as they are, because a name needs them, so two names that differ only by a space separator (a trailing space, a no-break space, an ideographic space or a figure space) would show as the same text. `list` and the ambiguity error of `show` compare ids with every space read as a plain space and trailing space dropped, and print each id of such a pair as an `ascii()` literal.
- Table cells in `list` and `probe` are escaped before they are laid out, so a cell never contains a line break and cannot forge another row.
- In `show`, every field is escaped. The transcript keeps its line feeds so it stays readable; every other control character in it is still escaped.
- Error messages, warnings and paths are escaped the same way. That includes the default `RecordingSkippedWarning` message that `iter_recordings` issues, so a file name with an escape sequence or a right-to-left override cannot reach standard error through Python's warning machinery.
- `--json` output is ASCII only, with every non ASCII character written as a `\u` escape. Lone surrogates, which stand for bytes that are not valid UTF-8, are replaced by U+FFFD so that no strict decoder rejects the document, and a recording with such a name carries `id_bytes_hex`.

A backslash in the source text is not escaped, so a title that literally contains `\x1b` looks the same as one that contains the escape character. Use `--json` when that difference matters.

## Failures

- A permission error while reading one recording's files does not stop the run. The recording is skipped, a `RecordingSkippedWarning` is issued (the command line prints `voicememos: warning: skipped <path>: <reason>` on standard error), and the rest are listed. The command still exits 0, so a script that must notice skips should read standard error or call `iter_recordings` with `on_skip`.
- A folder that exists and cannot be listed is never reported as missing or empty: it raises `LibraryBlockedError`, or is reported `blocked` by `probe`.
- A file that vanishes between listing and reading is skipped the same way.
- A recording whose parsing raises any other unexpected exception is skipped the same way. `on_skip` receives an `OSError` whose message names the exception type, so one hostile file never ends the run.

## Privacy

The risk with a Voice Memos library is its content, not the package. Recordings and transcripts are often personal or confidential, and a transcript is plain text that is easy to copy. The package returns that text to the program that called it; what that program does with it is outside this package's control. The package logs nothing, and the command prints transcript text only to your terminal when you run `show`.

Full Disk Access is a broad grant: the application that has it can read much of your account, not only Voice Memos. Grant it to the single application that runs the command, prefer a terminal you already trust, and revoke it if you no longer need it. A scheduled job that needs the grant gives it to its interpreter, so use a dedicated interpreter for such jobs.

## In the Repository

Tests build synthetic recordings and never read a real library, the live home directory or the network. The hostile input cases are in `tests/test_hardening.py`, each with a deadline so a regression fails instead of hanging. Contributors are asked never to commit a real recording, transcript or manifest. Bug reports should describe a file's structure or attach a synthetic file instead.

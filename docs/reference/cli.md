# cli

This page is the reference for the `voicememos` command: its subcommands, options, output shapes and exit statuses. The command is a thin layer over the functions in the [api reference](api.md). `python3 -m voicememos` runs the same command.

## synopsis

```text
voicememos [--version] <command> [options]
```

| command | effect |
| --- | --- |
| `voicememos probe` | report the state of each known recordings folder and name the library that would be read |
| `voicememos list` | list recordings, newest first |
| `voicememos show <id>` | show one recording with its transcript |

`--version` prints `voicememos <version>` and exits with status 0.

## options-shared-by-every-command

| option | effect |
| --- | --- |
| `--spotlight` | when no known path is readable, also ask Spotlight for candidate folders under `~/Library` that match a known Voice Memos container; macOS only |

When Spotlight chose the folder, `list` and `show` print `voicememos: using <path> (found by Spotlight)` on standard error, so a script that reads standard output is not disturbed, and `probe` appends `(chosen by Spotlight)` to its `library:` line.

## probe

`voicememos probe [--spotlight] [--json]`

Probes the five known paths. Plain output is a table with the columns `STATE`, `RECORDINGS` (the count, for readable folders) and `PATH`, then the Full Disk Access hint if any path is blocked, then a line `library: <path>` or `library: none readable`. With `--json` the output is:

```json
{
  "library": "/path/to/Recordings",
  "library_source": "known-path",
  "paths": [
    {"path": "/path/to/Recordings", "state": "readable", "recording_count": 2, "detail": null}
  ]
}
```

`library` is null when nothing is readable. `library_source` is `known-path` when one of the five known paths was chosen, `spotlight` when Spotlight chose the folder, and null when nothing is readable. `state` is one of `missing`, `readable`, `blocked` and `empty`.

## list

`voicememos list [--library PATH] [--spotlight] [--json]`

Without `--library`, the first readable known folder is used. Plain output is a table with the columns `ID`, `RECORDED` (local time, `YYYY-MM-DD HH:MM`), `DURATION` (`m:ss` or `h:mm:ss`, or `unknown`), `TRANSCRIPT` (`tsrp`, `plist` or `none`; `tsrp` means the audio file carries a non empty transcript box, which `list` does not decode, so `show` can report `plist` or `none` for a damaged box) and `TITLE` (shortened to 40 characters). With `--json` the output is an array of objects with the keys `id`, `audio_path`, `composition_path`, `recorded_at`, `duration_seconds`, `title` and `transcript_source`; the transcript text is left out, and is not kept in memory while listing. A recording that cannot be read is skipped with a warning on standard error, and the rest are listed; see [output and errors](#output-and-errors). When two ids are equal once both are normalised to Unicode form NFC (a precomposed and a decomposed spelling of the same name), `list` and the ambiguity error of `show` print them as Python `ascii()` literals, such as `'Caf\xe9'` and `'Cafe\u0301'`, so they can be told apart. Other ids are printed as they are.

## show

`voicememos show <id> [--library PATH] [--spotlight] [--json]`

`<id>` is a recording id, or a prefix that matches exactly one recording. An exact match wins over a longer one. A prefix that matches several ids fails with status 1 and lists them. Plain output prints `title`, `id`, `recorded`, `duration`, `audio`, `composition` and `transcript source` lines, then a blank line and the transcript text if there is one. With `--json` the output is one object with the same keys as `list --json` plus `transcript`.

## output-and-errors

- Text from files (titles, transcripts, ids, paths) is escaped in all plain output. Control characters, including ESC and newline, DEL, the C1 controls and invisible format characters are printed as `\xNN` or `\uNNNN`, so a file cannot move the cursor, set the window title, write to the clipboard or add a row to a table. In `show`, the transcript keeps its line feeds and every other control character in it is escaped. A lone surrogate prints as `?`. The full list is in the [security model](../explanation/security-model.md#terminal-output).
- Standard output and standard error are switched to `backslashreplace` before anything is printed, so a character the stream's encoding cannot represent, such as a non ASCII title under `PYTHONIOENCODING=ascii`, prints as a backslash escape instead of raising `UnicodeEncodeError`.
- `--json` output is ASCII only and never contains `NaN` or `Infinity`; a duration that is not a finite number is null.
- A recording that cannot be read (a permission error, or a file that vanished after listing) is skipped. For each one, `voicememos: warning: skipped <path>: <reason>` is printed on standard error and the exit status stays 0.
- Symlinks are never followed. A symlinked `.m4a` is not listed, and a symlinked `.composition` folder or `manifest.plist` is ignored.

## exit-statuses

| status | meaning |
| --- | --- |
| 0 | success; for `probe`, a readable library exists |
| 1 | no readable library was found, a folder exists but cannot be listed, a folder is missing, an id matched nothing or several recordings, or reading the chosen recording failed with an operating system error; `probe` also returns 1 when nothing is readable. The message is on standard error, prefixed `voicememos:` |
| 2 | usage error, such as an unknown command or a missing argument |

## configuration

There is no configuration file and no `voicememos` environment variable. The command reads the home directory (through `HOME`, to expand `~`) and the local timezone (through `TZ` or the system setting, to print local times). It writes nothing.

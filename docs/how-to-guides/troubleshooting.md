# Troubleshooting

This guide matches a symptom to its likely cause and fix. It covers a library that is not found, a folder reported as blocked or empty, missing transcripts, unexpected dates and durations, and failures that appear only in background jobs. Run `memotext probe` first; most of the entries below start from its output. The reasons behind the permission entries are in [where macOS keeps Voice Memos](../explanation/where-macos-keeps-voice-memos.md).

## Every Path Is Missing

`probe` shows `missing` for all five paths and ends with `library: none readable`.

- You may not be on macOS, or Voice Memos has never been opened for this user. Open the Voice Memos app once, record a short memo, and probe again.
- Your macOS version may keep recordings somewhere not in the list. Try `memotext probe --spotlight` on a Mac, or find the folder yourself and pass it: `memotext list --library "/path/to/Recordings"`.
- On Linux or Windows there is no library. Copy a folder of `.m4a` files and use `--library`.

## A Path Is Blocked

`probe` shows `blocked` and prints the Full Disk Access hint, and `list` fails with `found a recordings folder that cannot be listed`.

The folder exists and macOS refuses to let this process list it. Grant Full Disk Access to the application that runs the command: open System Settings, then Privacy and Security, then Full Disk Access, add your terminal app (or the editor that hosts the terminal), then quit it fully and start it again. The menu wording differs between macOS versions.

If it still reports `blocked`, the process that runs the command may not be the one you granted. See the entry on background jobs below.

## A Path Is Empty

`probe` shows `empty`: the folder can be listed and holds no `.m4a` file.

- Voice Memos may keep your recordings in a different known path. Look at the other lines of the output.
- Recordings made on another device appear only after iCloud syncs them. Check that Voice Memos is turned on in iCloud settings on the phone and on the Mac, and wait for the sync.
- A recording shared out of the app is not in the library folder.

## A Warning Says a Recording Was Skipped

`list` or `show` prints `memotext: warning: skipped <path>: <reason>` on standard error and leaves that recording out. The files of that one recording could not be read, for example because of a permission error on a single file or because the file vanished while the library was being read. The other recordings are listed and the exit status is 0. Check the permissions of the named file, or run the command again after sync finishes.

## A Recording Is Missing from the List

Files that are symlinks are not listed, and a symlinked `.composition` folder is ignored; memotext never follows a link out of the library. A file that is not a regular file, such as a FIFO, is not listed either. Copy the real file into the folder if you want it read.

## The Transcript Is None

`list` shows `none` in the transcript column, or `show` prints `transcript source: none`.

- Not every memo has a transcript. iOS and macOS produce one only when the feature is available for the device, language and OS version, and the memo has been processed. Open the memo in the Voice Memos app and check whether it shows a transcript there.
- The transcript may be stored in a form this package does not recognise. Where the transcript lives and how it is encoded are partly inferred; see [file formats](../reference/file-formats.md). If the app shows a transcript and memotext does not, open an issue with a description of the file structure and a synthetic file that behaves the same way. Never attach the real recording.

## The Title Looks Generated

A title such as `Voice Memo Jan 15, 2025 2:30:22 PM` is built from the recording date when the memo has no title in its manifest. Rename the memo in the app to give it a stored title.

## The Date Is Off by Hours

Recording dates are timezone aware and `list` prints them in your local time. When a memo has a `creationDate` in its manifest, that instant is used. Otherwise the date in the file name is read as local time, and as a last resort the file system time is used. A memo recorded in another timezone, or a file copied between machines, can therefore show a different local clock time than the one on the device that recorded it.

## The Duration Is Unknown

The duration is read from the manifest and, if that has none, from the movie header of the audio file. A file that is still downloading from iCloud or is not a valid M4A has neither. Wait for the sync, or check that the file plays.

## It Works in the Terminal but Not in a Background Job

A scheduled job (launchd, cron) runs as a different process from your terminal. Full Disk Access is granted per application, so the job's interpreter needs the grant itself. Add the exact Python executable that the job runs under Full Disk Access, or run the job through an application that already has it.

## The Command Exits with Status 1

Status 1 means no readable library was found, a folder could not be listed, or an id matched nothing. The message on standard error says which. [cli](../reference/cli.md) lists the statuses.

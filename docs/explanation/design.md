# design

This page explains why voicememos is built the way it is, for a reader deciding whether it fits their use or wondering why a behaviour is what it is. It covers the scope, the choice to have no dependencies, the four state probe, the timezone aware dates, the order in which transcripts are tried, and what is left out on purpose. It takes positions and names the alternatives. How the code is laid out is in the developer [architecture](../../developer-docs/explanation/architecture.md) page.

## scope

voicememos reads. It finds the recordings folder, lists recordings with their date, duration and title, and extracts the transcript iOS already produced. It does not transcribe audio, call a language model, write notes or touch the network. Each of those is a larger decision with its own dependencies and failure modes, and each belongs in the program that uses the library. Keeping the package to reading means it can be installed anywhere, tested on Linux and trusted with a library full of personal audio.

## no-runtime-dependencies

An obvious choice for reading an M4A file is a tag library such as `mutagen`. The package does not use one, because it needs only two things from the file, the duration and one custom box, and both come from a few dozen lines of box parsing. The box reader seeks past the audio data, so listing a few hundred recordings reads kilobytes from each file instead of the whole file. The cost is that the reader handles only what it needs. It does not decode tags, cover art or chapters, and a file that is damaged in an unusual way may read as having no duration. The alternative was a dependency that handles more and is a second thing to install, audit and keep compatible.

## four-states-not-two

The first design question for folder discovery is what to report when a folder exists but cannot be read. Treating existence as success makes that case look like a found library with no recordings. Treating a failed listing as missing hides the one thing the user can fix. The package therefore reports `missing`, `readable`, `blocked` and `empty` and lets only `readable` count as found. The explanation of why a folder can be blocked is in [where macOS keeps Voice Memos](where-macos-keeps-voice-memos.md).

The Spotlight search is a second, optional layer for the case where macOS moved the folder. It is off unless asked for, because it runs a program and because its queries are not verified. The interactive steps a friendly setup would add, such as opening the permissions pane or waiting while the user grants access, are not in the package.

## aware-dates

`Recording.recorded_at` is always timezone aware, and constructing a `Recording` with a naive datetime fails. A naive date is a bug waiting for a daylight saving change or a machine in another timezone. Each source of a date is converted at the point it is read: the manifest date is UTC by definition, the date in the file name is read as local time, and the file system time is UTC. The cost is that a date read from a file name is only as right as the assumption that the name uses local time, which is inferred.

## transcript-order

The `tsrp` atom in the audio file is tried before the manifest. The atom travels with the audio when a file is copied, and its shape is better understood. The manifest search is a heuristic over unknown key names, so it is the fallback. The result records which source produced the text, so a caller that distrusts the heuristic can ignore `plist` transcripts.

## content-hashes-ignore-time

`content_hash` hashes bytes and names and leaves out modification times. The aim is change detection: has this recording changed, not has someone touched it. A copy to another disk, a restore from backup or an iCloud re-download changes times without changing content, and should not look like an edit. The package stores no hashes; the caller decides where to keep them.

## left-out-on-purpose

- Waiting for a file to stop changing during iCloud sync. That needs time and a policy about how long to wait; the caller can do it with `content_hash`.
- A state file or cache. Reading is cheap, and a cache is a second source of truth that can drift.
- Writing, moving or deleting recordings. The package opens files for reading only.
- Reading `CloudRecordings.db`. Its structure is not understood, and the audio and manifest hold what is needed.

# getting-started

This tutorial takes you from an install to reading a transcript from your own Voice Memos library on a Mac. You install the command, check which folders it can see, list your recordings, show one with its transcript, and then do the same from Python. It follows one path and explains only what that path needs; the [reference](../reference/README.md) pages hold the detail and the [explanation](../explanation/where-macos-keeps-voice-memos.md) pages hold the reasons.

## what-you-need

- A Mac with the Voice Memos app and at least one recording that has a transcript.
- Python 3.11 or newer and `pipx`.
- A terminal. If it is your first time reading the Voice Memos folder, expect one permission step below.

## install

Until there is a release, install from the repository.

```bash
pipx install git+https://github.com/klappe-pm/voicememos
```

Check the command runs:

```bash
voicememos --version
```

## probe-the-library

`probe` tests each place Voice Memos has been known to keep recordings and says what it found.

```bash
voicememos probe
```

Each line shows a state, a count and a path. A folder you can use is `readable`. If you see `blocked` next to a path, the folder exists but macOS will not let this terminal list it. Open System Settings, go to Privacy and Security, then Full Disk Access, add your terminal app, quit the terminal completely and open it again. Then run `probe` again. [where macOS keeps Voice Memos](../explanation/where-macos-keeps-voice-memos.md) explains why.

The last line names the folder the other commands will read, for example `library: ~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings` (with your home folder written out in full).

## list-recordings

```bash
voicememos list
```

You get one row per recording, newest first, with its id, when it was recorded, its duration, where its transcript came from (`tsrp`, `plist` or `none`) and its title. The id is the file name without `.m4a`.

## show-one-recording

Copy an id from the list. Ids contain a space, so quote them. A start of the id is enough if it matches only one recording.

```bash
voicememos show "20250115 143022-ABCD1234"
```

The command prints the title, the dates and paths, and then the transcript text.

## use-json

Add `--json` to `list` or `show` to get output a script can read.

```bash
voicememos list --json
```

## use-it-from-python

The same steps in Python:

```python
from voicememos import find_library, iter_recordings

library = find_library()
if library is None:
    raise SystemExit("no readable Voice Memos folder; run `voicememos probe`")

for recording in iter_recordings(library):
    print(recording.recorded_at.isoformat(), recording.title)
    if recording.transcript_text:
        print(recording.transcript_text[:200])
```

## where-next

- [troubleshooting](../how-to-guides/troubleshooting.md) if `probe` finds nothing or a transcript is missing.
- [read transcripts from python](../how-to-guides/read-transcripts-from-python.md) for change detection and error handling.
- [cli reference](../reference/cli.md) and [api reference](../reference/api.md) for every option and function.

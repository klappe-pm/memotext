# Read Transcripts from Python

This guide shows how to use memotext from a script: find the library, read every recording, pick out the ones with transcripts, handle a blocked or missing folder, and tell which recordings changed since the last run. It assumes the package is installed and you know basic Python. The full signatures are in the [Python API reference](../reference/python-api.md).

## Find the Library

`find_library` returns the first readable folder, or None. It never returns a folder that exists but cannot be listed.

```python
from memotext import find_library

library = find_library()
```

To see why it returned None, probe the paths:

```python
from memotext import PathState, probe_library

for probe in probe_library():
    print(probe.state.value, probe.path)
    if probe.state is PathState.BLOCKED:
        print("grant Full Disk Access to the process running this script")
```

To search a different set of folders, pass them in. They are tried in order.

```python
from memotext import find_library

library = find_library(["~/exports/Recordings", "~/Desktop/Recordings"])
```

## Read Every Recording

```python
from memotext import iter_recordings

for recording in iter_recordings(library):
    print(recording.id, recording.recorded_at.isoformat(), recording.duration_seconds)
```

`iter_recordings` lists the folder as soon as you call it, so a missing or blocked folder raises at that line, not on the first loop step.

## Handle Errors

```python
from memotext import LibraryBlockedError, LibraryNotFoundError, iter_recordings

try:
    recordings = list(iter_recordings(library))
except LibraryBlockedError:
    print("the folder exists but macOS will not let this process list it")
    raise
except LibraryNotFoundError:
    print("the folder is gone")
    raise
```

Both errors also derive from `MemotextError`; `LibraryBlockedError` is a `PermissionError` and `LibraryNotFoundError` is a `FileNotFoundError`.

A single recording that cannot be read does not raise. It is skipped, and the loop continues with the others. Pass `on_skip` to see which, or a `RecordingSkippedWarning` is issued:

```python
skipped = []
recordings = list(iter_recordings(library, on_skip=lambda path, error: skipped.append(path)))
```

For a long list where you do not need the text, pass `transcripts=False` so no transcript is kept in memory. `transcript_source` is still set.

## Select Recordings with a Transcript

```python
with_text = [r for r in recordings if r.transcript_text]
from_audio = [r for r in with_text if r.transcript_source == "tsrp"]
```

`transcript_source` is `"tsrp"` when the text came from the audio file, `"plist"` when it came from the composition manifest, and None when there is no transcript.

## Reread a Transcript

`read_transcript` reads the files again, so it reflects what is on disk now.

```python
from memotext import read_transcript

transcript = read_transcript(recordings[0])
if transcript is not None:
    print(transcript.source, transcript.text)
```

## Detect Changed Recordings

`content_hash` returns a SHA 256 digest of the audio file and the composition folder. It ignores modification times, so copying a file does not change it. Keep the digests wherever suits your script; memotext stores nothing.

```python
import json
from pathlib import Path

from memotext import content_hash

seen_path = Path("seen.json")
seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}

changed = []
for recording in recordings:
    digest = content_hash(recording)
    if seen.get(recording.id) != digest:
        changed.append(recording)
        seen[recording.id] = digest

seen_path.write_text(json.dumps(seen, indent=2))
```

A recording that is still syncing from iCloud can change between two runs. If that matters, hash it twice a few seconds apart and act only when the digests match.

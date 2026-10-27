<p align="center">
  <a href="https://github.com/klappe-pm/memotext"><img src="https://raw.githubusercontent.com/klappe-pm/memotext/main/.github/memotext-banner.svg" alt="A terminal window: memotext list is typed, the memotext wordmark appears, and recordings are listed with their transcripts" width="760"></a>
</p>

<h1 align="center">Memotext</h1>

<p align="center">
  Read the Apple Voice Memos library and the transcripts iOS already made.
</p>

<p align="center">
  <a href="https://pypi.org/project/memotext/"><img src="https://img.shields.io/pypi/v/memotext?style=flat-square&color=3ddc84&labelColor=162233&label=PyPI" alt="PyPI version"></a>
  <a href="https://pypi.org/project/memotext/"><img src="https://img.shields.io/pypi/pyversions/memotext?style=flat-square&color=5aa9ff&labelColor=162233&label=Python" alt="Python versions"></a>
  <a href="https://github.com/klappe-pm/memotext/tags"><img src="https://img.shields.io/github/v/tag/klappe-pm/memotext?style=flat-square&color=3ddc84&labelColor=162233&label=release" alt="Latest release"></a>
  <a href="https://github.com/klappe-pm/memotext/blob/main/LICENSE"><img src="https://img.shields.io/github/license/klappe-pm/memotext?style=flat-square&color=5aa9ff&labelColor=162233&label=license" alt="MIT license"></a>
  <a href="https://github.com/klappe-pm/memotext/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/dependencies-none-3ddc84?style=flat-square&labelColor=162233" alt="No runtime dependencies"></a>
  <a href="https://github.com/klappe-pm/memotext/blob/main/docs/README.md"><img src="https://img.shields.io/badge/platform-macOS-5aa9ff?style=flat-square&labelColor=162233" alt="Reads the macOS Voice Memos library"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="#commands">Commands</a> ·
  <a href="https://github.com/klappe-pm/memotext/blob/main/docs/README.md">Docs</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

Your phone already transcribed your Voice Memos, but the transcripts sit inside files in a folder macOS protects. Finding that folder is guesswork, a folder you are not allowed to list can look empty, and a script that opens every file in a library other programs write has to be careful what it trusts.

Memotext finds the recordings folder, lists every recording with its recorded date, duration and title, and extracts the transcript iOS already produced, from the `tsrp` atom embedded in the `.m4a` file or from the `manifest.plist` in the `.composition` folder next to it. It does not transcribe audio, call a language model, write notes or use the network. It ships as a Python package and a `memotext` command.

## Why Memotext?

| Without Memotext | With Memotext |
| --- | --- |
| You search the Library folder for wherever this macOS version keeps recordings | `memotext probe` checks every known location and reports each as missing, readable, blocked or empty |
| A folder macOS will not let you list looks empty | A folder that exists but cannot be listed is reported as blocked, with the Full Disk Access hint |
| You open each memo in the app to read its transcript | `memotext show` prints the transcript iOS already made, from the audio file or the manifest |
| A script that reads a library other programs write trusts every file in it | Files are opened without following symlinks, sizes and depths are bounded, and text is escaped before it reaches a terminal |
| Reading a library pulls in a dependency tree | Standard library only, no dependencies |

## Who This Is For

- People who want their Voice Memos transcripts as text, on a Mac, without opening each memo.
- Developers who need a library call that lists recordings and returns transcripts for a script or another tool.
- Anyone who wants to know why `list` shows nothing and whether that is a permission problem.

## Highlights

- **Finds the folder.** Five known locations are probed in order, and an optional Spotlight search covers a folder macOS moved.
- **Blocked is not empty.** Listing the folder is what decides its state, so a missing Full Disk Access grant is never mistaken for an empty library.
- **The transcripts iOS made.** The `tsrp` atom in the `.m4a` file is read first, then the manifest in the `.composition` folder.
- **A command and a library.** `probe`, `list` and `show` on the command line, and `find_library`, `iter_recordings`, `read_transcript` and `content_hash` from Python.
- **Safe with hostile files.** Symlinks and FIFOs are never followed or waited on, the MP4 and plist readers are bounded in memory and time, and these are escaped before they reach a terminal: every control character, every format, unassigned and private use character, the line and paragraph separators, every default ignorable code point (the Hangul fillers and the variation selectors among them), every noncharacter, and the two blank drawing characters U+2800 and U+1D159. The variation selector and joiner inside an emoji are the only exception.
- **Read only.** It writes no file, keeps no state, runs no program except `mdfind` when you ask for the Spotlight search, and uses no network.
- **Nothing to install but Python.** Pure standard library at runtime, no dependencies.

## Installation

Memotext needs Python 3.11 or newer. [pipx](https://pipx.pypa.io/) is the easiest way to get a command-line tool onto your path:

```bash
pipx install memotext
```

Nothing is published to PyPI yet. Until the first release, install from GitHub:

```bash
pipx install git+https://github.com/klappe-pm/memotext
```

Then check which recordings folders Memotext can see:

```bash
memotext probe
```

## Quick Start

List the recordings, newest first:

```bash
memotext list
```

Show one recording with its transcript. The id is the audio file name without `.m4a`, or a prefix that matches exactly one recording:

```bash
memotext show "20250115 143022-ABCD1234"
```

Use `--json` on any command for machine readable output. If `probe` reports a folder as `blocked`, the folder exists but macOS will not let this process list it. Grant Full Disk Access to your terminal as [Where macOS Keeps Voice Memos](https://github.com/klappe-pm/memotext/blob/main/docs/explanation/where-macos-keeps-voice-memos.md) explains.

From Python:

```python
from memotext import find_library, iter_recordings

library = find_library()
if library is not None:
    for recording in iter_recordings(library):
        print(recording.recorded_at, recording.title, recording.transcript_source)
```

## How It Works

Voice Memos keeps a folder of `.m4a` recordings, and next to some of them a `.composition` folder with a `manifest.plist`. Memotext reads three things from that library and nothing else:

| Source | What it gives |
| --- | --- |
| the `.m4a` file | the duration, from the `mvhd` box, and the transcript, from the `tsrp` box |
| `<id>.composition/manifest.plist` | the title, the creation date, a duration, and a transcript when the audio file has none |
| the file name | the id, and a recorded date when the manifest has none |

The folder is found by probing these locations in order, and the first one that can be listed and holds at least one `.m4a` file wins:

| Location under `~/Library` |
| --- |
| `Group Containers/group.com.apple.VoiceMemos.shared/Recordings` |
| `Mobile Documents/com~apple~VoiceMemos/Recordings` |
| `Containers/com.apple.VoiceMemos/Data/Library/Application Support/Recordings` |
| `Application Support/com.apple.voicememos/Recordings` |
| `Application Support/com.apple.VoiceMemos/Recordings` |

The code is tested on Linux with synthetic fixtures. It has not been run against a real Mac: the known folder paths, the placement of the `tsrp` atom and the keys in `manifest.plist` are inferred, and the [File Formats](https://github.com/klappe-pm/memotext/blob/main/docs/reference/file-formats.md) reference marks each inferred part.

## Commands

| Command | What it does |
| --- | --- |
| `memotext probe` | Reports the state of each known recordings folder and which one would be used. |
| `memotext list` | Lists the recordings, newest first, with date, duration, transcript source and title. |
| `memotext show ID` | Shows one recording and its transcript. |

Every command accepts `--spotlight` to also ask Spotlight when no known path is readable (macOS only), and `--json` for machine readable output. `list` and `show` accept `--library PATH` to read a folder you point at. `memotext --version` prints the version. The command exits 0 on success, 1 when no readable library is found or an id matches nothing, and 2 for a usage error. The [CLI reference](https://github.com/klappe-pm/memotext/blob/main/docs/reference/cli.md) covers the full surface, and the [Python API reference](https://github.com/klappe-pm/memotext/blob/main/docs/reference/python-api.md) covers the library.

## Documentation

The docs live in one tree under `docs/`, following the [Diátaxis](https://diataxis.fr/) layout: tutorials, how-to guides, reference and explanation.

- **Using it:** start with [Getting Started](https://github.com/klappe-pm/memotext/blob/main/docs/tutorials/getting-started.md), then browse the rest of [docs](https://github.com/klappe-pm/memotext/blob/main/docs/README.md).
- **Hacking on it:** start with [First Contribution](https://github.com/klappe-pm/memotext/blob/main/docs/tutorials/first-contribution.md), which sits in the same tree.
- **What ships:** the [changelog](https://github.com/klappe-pm/memotext/blob/main/CHANGELOG.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](https://github.com/klappe-pm/memotext/blob/main/CONTRIBUTING.md) first; it will save you a round trip. If you are stuck or have found a bug, [SUPPORT.md](https://github.com/klappe-pm/memotext/blob/main/SUPPORT.md) says where to ask and where to file an issue.

## Security

Please report vulnerabilities privately as described in [SECURITY.md](https://github.com/klappe-pm/memotext/blob/main/SECURITY.md) rather than opening a public issue.

## License

Memotext is released under the [MIT License](https://github.com/klappe-pm/memotext/blob/main/LICENSE).

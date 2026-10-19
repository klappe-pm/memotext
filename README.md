# voicememos

voicememos reads the Apple Voice Memos library on macOS. It finds the recordings folder, lists recordings with their recorded date, duration and title, and extracts the transcript that iOS already produced, from the `tsrp` atom embedded in the `.m4a` file or from the `manifest.plist` in a `.composition` folder. It does not transcribe audio, call a language model, write notes or use the network. It ships as a Python package and a `voicememos` command, and needs only the Python 3.11 standard library at runtime.

## status

Nothing is released yet. The library functions `probe_library`, `find_library`, `iter_recordings`, `read_transcript` and `content_hash`, the `Recording` dataclass, and the commands `probe`, `list` and `show` are implemented and tested on Linux with synthetic fixtures. The behaviour on a real Mac has not been verified: the known folder paths, the placement of the `tsrp` atom and the keys in `manifest.plist` are inferred, and the [file formats reference](docs/reference/file-formats.md) marks each inferred part. [changelog.md](changelog.md) records changes.

## quickstart

Install the command. Until there is a release, install from the repository.

```bash
pipx install git+https://github.com/klappe-pm/voicememos
```

Check which recordings folders the tool can see:

```bash
voicememos probe
```

List the recordings, newest first, and show one with its transcript:

```bash
voicememos list
```

```bash
voicememos show "20250115 143022-ABCD1234"
```

If `probe` reports a folder as `blocked`, the folder exists but macOS will not let this process list it. Grant Full Disk Access to your terminal as [where macOS keeps Voice Memos](docs/explanation/where-macos-keeps-voice-memos.md) explains.

## documentation

Two trees, one per audience, each arranged by [Diátaxis](https://diataxis.fr/) quadrant: tutorials, how-to guides, reference and explanation.

- I use voicememos, where do I start: [getting started](docs/tutorials/getting-started.md), then the rest of [docs](docs/README.md).
- I change voicememos, where do I start: [first contribution](developer-docs/tutorials/first-contribution.md), then the rest of [developer-docs](developer-docs/README.md).

## support-and-contributing

[support.md](support.md) says where to ask for help and where to file an issue. [contributing.md](contributing.md) holds the contribution guidelines. Report vulnerabilities privately as described in [security.md](security.md).

## license

MIT. See [LICENSE](LICENSE).

# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Package scaffold: `pyproject.toml` with the hatchling build backend, no runtime dependencies and the `voicememos` console script.
- Library discovery, layer 1: `probe_library` and `probe_path` report each known path as `missing`, `readable`, `blocked` or `empty`, so a folder that exists but cannot be listed is never reported as found. `find_library` returns only a readable folder.
- Library discovery, layer 2: `spotlight_search` asks `mdfind` for candidate folders. It runs only on macOS and only when `find_library` is called with `spotlight=True` or a command is given `--spotlight`.
- `Recording`, `iter_recordings`, `read_transcript` and `content_hash`, with a standard library reader for the MP4 boxes that carry the duration (`mvhd`) and the iOS transcript (`tsrp`), and for the transcript in a `.composition` folder's `manifest.plist`.
- The `voicememos` command with `probe`, `list` and `show`, each with `--json`.
- Documentation in one `docs/` tree arranged by Diátaxis quadrant, for people who use Voicememos and for people who change it, including an explanation of where macOS keeps Voice Memos and why Full Disk Access matters, and a reference for the `tsrp` and plist formats that marks what is inferred.
- Repository documents: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, issue templates for a bug report, a feature request and a question, and a pull request template.
- Hardening against hostile files, with regression tests in `tests/test_hardening.py`: every file is opened without following symlinks or blocking on a FIFO; MP4 walking is lazy and bounded (10,000 boxes, 8 levels, a 64 MiB and 1,000 hit cap on the byte scan); the manifest search is iterative with a depth limit of 32 and a budget of 100,000 values, and visits shared values once; non finite and oversized durations are ignored and JSON output forbids NaN; dates outside the supported range no longer raise; a recording that cannot be read is skipped with a warning instead of aborting the run; text from files is escaped before it reaches a terminal; `list` keeps no transcript text; `mdfind` is called by absolute path. The [Security Model](docs/explanation/security-model.md) states each limit.
- A file system fallback for the recording date that reads `st_birthtime` with `getattr` and falls back to the modification time, because the attribute exists on macOS but not on Linux.

### Changed

- The documentation is one tree under `docs/`. The contributor pages moved there from `developer-docs/`, `release.md` is now `cut-a-release.md` and `api.md` is now `python-api.md`. Headings use Title Case, and the community files have uppercase names: `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` and `SUPPORT.md`.
- The README follows the Stratarc layout: a banner, a badge row, a navigation row, a table of what changes with Voicememos, and sections in a fixed order. Every link in it is absolute so that it works on PyPI.
- `docs/documentation-guide/` is no longer tracked and is listed in `.gitignore`.

### Fixed

- A hostile `manifest.plist` that made `plistlib` raise an `AttributeError`, `IndexError` or `LookupError` no longer aborts `list` and `show` with a traceback. `read_manifest` treats such a file as having no manifest, and `iter_recordings` skips a recording whose parsing raises any unexpected exception and reports it through `on_skip`.
- Terminal escaping now covers every character in the Unicode categories `Cf`, `Zl` and `Zp`, plus the combining grapheme joiner, the Hangul fillers, the variation selectors and the whole tag block U+E0000 to U+E007F. A title could previously smuggle hidden text, spelled in tag characters, into any program that read `show` output. Characters above U+FFFF are written `\UNNNNNNNN`.
- The default `RecordingSkippedWarning` message now escapes the file name and the reason, so an ESC or a right-to-left override in a file name no longer reaches standard error.
- A `.composition` folder swapped for a symlink between the directory check and the open is no longer followed. `read_manifest` opens the folder with `O_DIRECTORY` and `O_NOFOLLOW` and the manifest relative to that descriptor, so nothing outside the library is read.
- `content_hash` no longer recurses without bound. It walks the composition folder iteratively from a descriptor, refuses a folder swapped for a symlink during the walk, raises the new `CompositionLimitError` for a folder nested more than 64 levels deep or holding more than 100,000 entries, and raises when a subfolder cannot be listed instead of leaving it out of the digest.
- The `--spotlight` fallback no longer adopts any folder whose path contains "VoiceMemos". `find_library` accepts a Spotlight candidate only when it lies inside a known Voice Memos container under `~/Library`. `list` and `show` print which folder was chosen and that Spotlight chose it on standard error, and `probe` reports `library_source` in its JSON output and a note in its text output.
- The command line no longer raises `UnicodeEncodeError` when standard output or standard error cannot encode a character in a title or file name, for example under `PYTHONIOENCODING=ascii`. Both streams are switched to `backslashreplace` at the start of `main`.
- `list` no longer decodes the transcript payload it discards. With `transcripts=False`, `iter_recordings` detects the source from the presence of a non empty `tsrp` box and never calls the JSON decoder. `show` now reports the source it actually decoded.
- `list` and the ambiguous id error of `show` print ids that differ only in Unicode normalisation (NFC against NFD) as `ascii()` literals, so look-alike ids can be told apart.
- `--json` output is now valid for a strict decoder. A lone surrogate from a file name that is not UTF-8, or from a transcript, is replaced by U+FFFD, and a recording whose id was not valid UTF-8 carries a new `id_bytes_hex` field with the raw bytes of the id.

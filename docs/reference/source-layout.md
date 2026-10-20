# Source Layout

This page lists the repository tree and what each module holds, for a contributor looking for where a behaviour lives. It states which names are public and which are internal. The behaviour of the public names is in the [Python API reference](python-api.md).

## Tree

```text
voicememos/
  pyproject.toml          build, test, ruff and mypy configuration
  README.md               the project page that PyPI also shows
  CHANGELOG.md            what changed, in Keep a Changelog form
  CONTRIBUTING.md         rules every contribution follows
  CODE_OF_CONDUCT.md      expected conduct
  SECURITY.md             how to report a vulnerability
  SUPPORT.md              where to ask and where to file
  LICENSE                 the MIT license
  .github/                issue templates, pull request template, banner, release workflow
  requirements/           hash pinned lock files for the release workflow
  scripts/make-banner.py  regenerates .github/voicememos-banner.svg (needs fonttools)
  voicememos/
    __init__.py           public names and __version__
    __main__.py           python -m voicememos
    cli.py                the voicememos command
    discovery.py          known paths, the four states, Spotlight
    errors.py             exception classes
    mp4.py                MP4 box reader: tsrp payload and mvhd duration
    py.typed              marks the package as typed
    recording.py          Recording, iter_recordings, read_transcript, content_hash
    safeio.py             open files without following symlinks or blocking on FIFOs
    textsafe.py           escape control characters before printing
    transcripts.py        tsrp JSON, manifest.plist and the transcript search
  tests/                  one test module per source module, plus synthetic.py,
                          test_docs.py, test_no_personal_terms.py and test_release_workflow.py
  docs/                   documentation for users and contributors
```

## Modules

| module | holds | public |
| --- | --- | --- |
| `voicememos/__init__.py` | the names re-exported for users and `__version__` | yes |
| `voicememos/discovery.py` | `KNOWN_PATHS`, `PathState`, `PathProbe`, `probe_path`, `probe_library`, `find_library`, `spotlight_search`, `is_voicememos_container` | all but `is_voicememos_container` are exported |
| `voicememos/recording.py` | `Recording`, `Transcript`, `iter_recordings`, `read_transcript`, `content_hash` and the helpers that choose each field | the five names above are exported |
| `voicememos/errors.py` | `VoiceMemosError`, `LibraryNotFoundError`, `LibraryBlockedError`, `CompositionLimitError`, `UnsafeFileError`, `RecordingSkippedWarning` | all six are exported |
| `voicememos/safeio.py` | `open_regular`, `open_dir`, `open_child`, `scan_dir`, `close_dir`, `is_real_dir`, `ABSENT_ERRORS` | no |
| `voicememos/textsafe.py` | `printable` | no |
| `voicememos/mp4.py` | `read_tsrp_payload`, `read_duration_seconds` and the box walker | no |
| `voicememos/transcripts.py` | `transcript_from_tsrp`, `read_tsrp_transcript`, `read_manifest`, `transcript_from_manifest` | no |
| `voicememos/cli.py` | `main` and the three command functions | `main` is the console script entry point |

Internal modules and underscore names may change in any release. The tests import some of them directly to cover edge cases.

## Dependencies Between Modules

`errors`, `textsafe` and `discovery` import nothing from the package. `safeio` imports `errors`. `mp4` imports `safeio`. `transcripts` imports `mp4` and `safeio`. `recording` imports `discovery`, `errors`, `mp4`, `safeio`, `textsafe` and `transcripts`. `cli` imports `discovery`, `errors`, `recording` and `textsafe`. There are no cycles.

## Packaging

`pyproject.toml` uses hatchling and reads the version from `voicememos/__init__.py`. The wheel contains the `voicememos` package including `py.typed`. The source distribution adds `tests`, `README.md`, `LICENSE` and `pyproject.toml`; the tests that need repository-only files are marked `repo_only` and skip when those files are absent, so the suite passes from an extracted sdist. The package has no data files, so nothing is read through `importlib.resources` today; if a data file is added, read it that way and never through a path built from `__file__`.

## The Console Script

`voicememos = "voicememos.cli:main"` in `pyproject.toml`. `main(argv=None)` returns the exit status; the module guard and `__main__.py` pass it to `SystemExit`.

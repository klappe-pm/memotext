# Run the Tests

This guide lists every check a change must pass and how to run it. It assumes the development install from [First Contribution](../tutorials/first-contribution.md), and its commands use `/path/to/voicememos` for your clone, which is also where the virtual environment lives. There is no CI service for changes, so these commands are the gate: a change that passes them all is ready for review. The release workflow runs the suite once more, against the built wheel, before it publishes.

## Test Suite

```bash
/path/to/voicememos/.venv/bin/python -m pytest /path/to/voicememos/tests
```

Install the `test` and `lint` extras first: `pip install -e '/path/to/voicememos[test,lint]'`. `pytest` and `pytest-cov` are the `test` extra, with `pytest` at 9.0.3 or newer because earlier releases carry CVE-2025-71176, and `ruff` and `mypy` are the `lint` extra.

## Coverage

```bash
/path/to/voicememos/.venv/bin/python -m pytest /path/to/voicememos/tests --cov=voicememos --cov-report=term-missing
```

The target is at least 90 percent line coverage of the package. The report lists the lines that no test reached. Report the real number in the pull request.

## Lint and Format

```bash
/path/to/voicememos/.venv/bin/ruff check /path/to/voicememos
```

```bash
/path/to/voicememos/.venv/bin/ruff format --check /path/to/voicememos
```

The configuration is in `pyproject.toml`: line length 100, target Python 3.11, and the rule sets `E`, `F`, `I`, `UP`, `B`, `SIM`, `W`, `S` and `RUF`. The `S` rules are the security rules, and a `noqa` for one must say why it is safe. To fix formatting, run `ruff format` without `--check`.

## Type Checking

```bash
/path/to/voicememos/.venv/bin/mypy --config-file /path/to/voicememos/pyproject.toml /path/to/voicememos/voicememos
```

The configuration runs `mypy --strict` on the `voicememos` package. Tests are not type checked.

## Source Distribution

The source distribution leaves out `.github/`, `docs/` and the community files. Tests marked `repo_only` read those files, so they skip themselves when the files are missing, and the tests that ship in the sdist pass when run from an extracted copy. To check that, build the distributions, extract the sdist, install the wheel and run the tests there with the source package out of the way, so that the wheel is what gets imported:

```bash
cd /path/to/voicememos && python3 -m build --outdir /path/to/dist
```

```bash
tar -xzf /path/to/dist/voicememos-<version>.tar.gz -C /path/to/sdist && python3 -m venv /path/to/venv && /path/to/venv/bin/pip install /path/to/dist/voicememos-<version>-py3-none-any.whl pytest && rm -r /path/to/sdist/voicememos-<version>/voicememos && cd /path/to/sdist/voicememos-<version> && /path/to/venv/bin/python -m pytest
```

## Repository Tests

Three modules check the repository around the code.

- `tests/test_docs.py` checks the documentation and the files beside it: Title Case headings in every Markdown file, including the pull request template, one H1 per page, a purpose paragraph under each title, no frontmatter or provenance keys, no agent credit, no home directory in any page, a language tag on every code fence, relative links that resolve, absolute links in the README and its skeleton, one line per paragraph, no dash used as punctuation, no em or en dash in any text file, a final newline, the Keep a Changelog shape of the changelog, lowercase kebab-case filenames, no agent instruction files, the required community files, and a `.github` folder that holds only the templates, the banner and the release workflow.
- `tests/test_no_personal_terms.py` reads every tracked file and rejects the owner's email, private tool names, tracker ticket codes and absolute home paths. To check a private list of further terms, put one term per line in a text file outside the repository and name it in `VOICEMEMOS_FORBIDDEN_TERMS_FILE`; the test skips when the variable is not set, which is the case on GitHub, so the release guide runs it locally before every release.
- `tests/test_release_workflow.py` checks that every action is pinned to a full commit, that the build, test and publish jobs are separate, that only the publish job can request an identity token, that every `pip install` in the workflow uses hashes or installs the local artifact with `--no-deps`, and that the lock files pin every requirement with hashes. It also checks the packaging metadata.

`test_docs.py` and `test_release_workflow.py` carry the `repo_only` marker.

## The Banner

`.github/voicememos-banner.svg` is written by `scripts/make-banner.py`, which needs `fonttools` and the DejaVu Sans Mono font files. `fonttools` is a script-only dependency and is not a dependency of the package. Edit the script, never the SVG:

```bash
cd /path/to/voicememos && python3 -m pip install fonttools && python3 scripts/make-banner.py
```

## Running One Test

To run one file or one test:

```bash
/path/to/voicememos/.venv/bin/python -m pytest /path/to/voicememos/tests/test_discovery.py -k blocked
```

## The Permission Denied Tests

The blocked folder case is tested twice. One test patches `os.scandir` to raise `PermissionError`, so it runs everywhere, including as root. The other makes a real directory unreadable with `chmod 000` and is skipped when you run as root or on Windows, because root can still list such a directory. To see it run, use an ordinary user account. Skips are listed with their reasons:

```bash
/path/to/voicememos/.venv/bin/python -m pytest /path/to/voicememos/tests -rs
```

## Other Python Versions

The package supports Python 3.11 and newer. To check the oldest supported version, create a virtual environment with it and run the same commands:

```bash
uv venv --python 3.11 /path/to/voicememos/.venv311 && uv pip install --python /path/to/voicememos/.venv311/bin/python -e '/path/to/voicememos[test]' && /path/to/voicememos/.venv311/bin/python -m pytest /path/to/voicememos/tests
```

## Timezone Tests

A few tests change the local timezone with `time.tzset` through the `set_timezone` fixture, which restores it afterwards. They skip on platforms without `tzset`.

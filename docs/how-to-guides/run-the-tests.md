# Run the Tests

This guide covers running the checks that a change must pass: the test suite, coverage, the lint and format checks, the type check, the repository tests, and the test of the permission denied case. It assumes you have a development install as [first contribution](../tutorials/first-contribution.md) describes. The default suite runs on Linux and macOS, reads only synthetic fixtures and never touches the live home directory.

## The Suite

```bash
python3 -m pytest
```

To run one file or one test:

```bash
python3 -m pytest tests/test_discovery.py -k blocked
```

## Coverage

Line coverage of the package must stay at 90 percent or higher.

```bash
python3 -m pytest --cov=voicememos --cov-report=term-missing
```

`--cov-report=term-missing` lists the lines no test reached.

## Lint, Format and Types

```bash
ruff check .
```

```bash
ruff format --check .
```

```bash
mypy
```

`ruff format .` rewrites files, including Python code fences in Markdown. `mypy` runs in strict mode on the `voicememos` package, as `pyproject.toml` configures. To check the tests too, run `mypy --strict tests`.

## The Repository Tests

Three modules check the repository around the code, and the tests in them carry the `repo_only` marker because they read files that a source distribution omits.

- `tests/test_docs.py` checks the documentation and the files beside it: Title Case headings, one H1 per page, links that resolve, absolute links in the README, no hard-wrapped paragraphs, no dash used as punctuation, a language tag on every code fence, no provenance keys, no home directory in any page, the required community files, and that `.github/` holds only the issue templates, the pull request template, the banner and the release workflow.
- `tests/test_no_personal_terms.py` reads every tracked file and rejects the owner's email, private tool names, internal ticket codes and absolute home directories. To check a private list of extra terms that must never be published, put one term per line in a file outside the repository and name it in `VOICEMEMOS_FORBIDDEN_TERMS_FILE`; the test is skipped when the variable is not set.
- `tests/test_release_workflow.py` checks that every action is pinned to a full commit, that the build, test and publish jobs are separate, that only the publish job can request an identity token, that every `pip install` in the workflow uses hashes, and that the lock files pin every requirement with hashes.

## The Source Distribution

The sdist carries the package and its tests but not `.github/`, `docs/` or the community files, so the `repo_only` tests skip there. Prove that the tests shipped in the sdist pass against the wheel by building both, installing the wheel in a clean environment and running the extracted sdist's tests with the source package out of the way:

```bash
cd voicememos
work="$(mktemp -d)"
python3 -m build --outdir "$work/dist"
python3 -m venv "$work/venv"
"$work/venv/bin/pip" install "$work"/dist/*.whl 'pytest>=9.0.3' 'pytest-cov>=7'
mkdir "$work/sdist"
tar -xzf "$work"/dist/*.tar.gz -C "$work/sdist" --strip-components=1
rm -r "$work/sdist/voicememos"
cd "$work/sdist" && "$work/venv/bin/python" -m pytest -q
```

## The Banner

`.github/voicememos-banner.svg` is written by `scripts/make-banner.py`, which needs `fonttools` and the DejaVu Sans Mono font files. `fonttools` is a script-only dependency and is not a dependency of the package. Edit the script, never the SVG:

```bash
cd voicememos && python3 -m pip install fonttools && python3 scripts/make-banner.py
```

## The Permission Denied Tests

The blocked folder case is tested twice. One test patches `os.scandir` to raise `PermissionError`, so it runs everywhere, including as root. The other makes a real directory unreadable with `chmod 000` and is skipped when you run as root or on Windows, because root can still list such a directory. To see it run, use an ordinary user account. Skips are listed with their reasons:

```bash
python3 -m pytest -rs
```

## Other Python Versions

The package supports Python 3.11 and newer. To check the oldest supported version, create a virtual environment with it and run the same commands:

```bash
uv venv --python 3.11 .venv311 && uv pip install --python .venv311/bin/python -e '.[test]' && .venv311/bin/python -m pytest
```

## Timezone Tests

A few tests change the local timezone with `time.tzset` through the `set_timezone` fixture, which restores it afterwards. They skip on platforms without `tzset`.

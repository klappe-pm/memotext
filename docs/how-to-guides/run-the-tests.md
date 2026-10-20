# Run the Tests

This guide covers running the checks that a change must pass: the test suite, coverage, the lint and format checks, the type check, and the test of the permission denied case. It assumes you have a development install as [first contribution](../tutorials/first-contribution.md) describes. The default suite runs on Linux and macOS, reads only synthetic fixtures and never touches the live home directory.

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

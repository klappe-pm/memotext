# First Contribution

This tutorial takes you from a fresh clone to a change that is ready for review. You set up a development environment, run the test suite, make one small change and check it. It follows one path and explains only what that path needs; [Contributing](../../CONTRIBUTING.md) holds the guidelines it applies, and the [how-to guides](../how-to-guides/README.md) cover each step in more depth.

## What You Need

- Python 3.11 or newer.
- `git`, and a GitHub account if you intend to open a pull request.
- No Mac. The default suite runs on Linux and uses only synthetic files.

The commands use `/path/to/memotext` for your clone. Replace it with the real location.

## Clone and Install

```bash
git clone https://github.com/klappe-pm/memotext /path/to/memotext && python3 -m venv /path/to/memotext/.venv && /path/to/memotext/.venv/bin/pip install -e '/path/to/memotext[test,lint]'
```

This installs Memotext as an editable package with the `test` extra (`pytest` and `pytest-cov`) and the `lint` extra (`ruff` and `mypy`). The package itself has no runtime dependencies.

## Run the Tests

```bash
/path/to/memotext/.venv/bin/python -P -m pytest /path/to/memotext/tests
```

The suite finishes in a couple of seconds. Skips are normal: tests that need a non-root user to make a directory unreadable skip when you run as root, and each says why. See [Run the Tests](../how-to-guides/run-the-tests.md) for the other checks.

## Make a Change

Pick something small. This example makes the table in `memotext list` show a different title length. The limit is the number passed to `_shorten` in `memotext/cli.py`, in the `_cmd_list` function:

```text
_shorten(r.title, 40),
```

Change `40` to `30`. Run the tests again. One test fails, because `test_long_titles_are_shortened` in `tests/test_cli.py` expects the old length. A test that fails when behaviour changes is doing its job. Update the expectation in that test to match the new length, and update the number in [CLI](../reference/cli.md), which says where the title is shortened.

Update the page in `docs/` that describes the behaviour. A page goes in the folder for its kind: `tutorials/`, `how-to-guides/`, `reference/` or `explanation/`.

## Check It

```bash
/path/to/memotext/.venv/bin/python -P -m pytest /path/to/memotext/tests --cov=memotext --cov-report=term-missing
```

```bash
/path/to/memotext/.venv/bin/ruff check /path/to/memotext && /path/to/memotext/.venv/bin/ruff format --check /path/to/memotext && /path/to/memotext/.venv/bin/mypy --config-file /path/to/memotext/pyproject.toml /path/to/memotext/memotext
```

Coverage should stay at 90 percent or higher and every check should pass.

## Commit

Commit with a [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) message, for example `fix: shorten list titles to 30 characters` or `docs: clarify the blocked state`. Add a line under Unreleased in [the changelog](../../CHANGELOG.md) if the change is visible to a user. Keep the change to one thing, and say in the pull request what it does and how you tested it.

## Next Steps

- Read [Architecture](../explanation/architecture.md) before a change that touches more than one module.
- Read [Build a Synthetic Recording](../how-to-guides/build-a-synthetic-recording.md) to make a test file of your own.
- Read [Design](../explanation/design.md) before proposing a change to something it settles.

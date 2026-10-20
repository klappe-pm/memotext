# First Contribution

This tutorial takes you from a fresh clone to a pull request that is ready to merge. You set up a development environment, run the test suite, make one small change with a test that fails without it, check it the way a reviewer will, and open the pull request. It follows one path and explains only what that path needs; [contributing](../../CONTRIBUTING.md) holds the guidelines it applies, and the [how-to guides](../how-to-guides/README.md) cover each step in more depth.

## What You Need

- Python 3.11 or newer.
- `git`, and a GitHub account if you intend to open the pull request.
- No Mac. The default suite runs on Linux and uses only synthetic files.

## Clone and Install

```bash
git clone https://github.com/klappe-pm/voicememos && cd voicememos && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test,lint]'
```

This installs voicememos as an editable package with `pytest`, `pytest-cov`, `ruff` and `mypy`. The package itself has no runtime dependencies.

## Run the Tests

```bash
python3 -m pytest
```

The suite finishes in a couple of seconds. Skips are normal: tests that need a non-root user to make a directory unreadable skip when you run as root, and each says why.

## Make a Small Change

Pick something small. This example makes the table in `voicememos list` show a different title length. The limit is the number passed to `_shorten` in `voicememos/cli.py`, in the `_cmd_list` function:

```text
_shorten(r.title, 40),
```

Change `40` to `30`. Run the tests again. One test fails, because `test_long_titles_are_shortened` in `tests/test_cli.py` expects the old length. A test that fails when behaviour changes is doing its job. Update the expectation in that test to match the new length, and update the number in [cli](../reference/cli.md), which says where the title is shortened.

## Check It Like a Reviewer

```bash
python3 -m pytest --cov=voicememos --cov-report=term-missing
```

```bash
ruff check . && ruff format --check . && mypy
```

Coverage should stay at 90 percent or higher and every check should pass. [run the tests](../how-to-guides/run-the-tests.md) explains each.

## Document It

Add a line under Unreleased in [the changelog](../../CHANGELOG.md) for any user-visible change, and update the page in `docs/` that describes the behaviour. A page goes in the folder for its kind: `tutorials/`, `how-to-guides/`, `reference/` or `explanation/`. Write one line per paragraph, use no dashes as punctuation, and give headings Title Case.

## Open the Pull Request

Commit with a Conventional Commits message, push a branch and open a pull request that says what changed and how you tested it. Do not add an agent or a session link to the message or the description.

```bash
git switch -c fix/title-length && git add voicememos/cli.py tests/test_cli.py docs/reference/cli.md CHANGELOG.md && git commit -m "fix: shorten list titles to 30 characters" && git push -u origin fix/title-length
```

# Contributing

Thank you for helping improve Memotext. Open an issue to discuss a change before writing a large pull request, so the effort goes where it will be merged. This page holds the rules every contribution follows; the walkthroughs and reference live under [docs](docs/README.md), starting with [First Contribution](docs/tutorials/first-contribution.md). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

```bash
git clone https://github.com/klappe-pm/memotext && cd memotext && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test,lint]'
```

## Tests

Run the suite before every commit. [Run the Tests](docs/how-to-guides/run-the-tests.md) covers the other checks.

```bash
python3 -m pytest
```

```bash
python3 -m pytest --cov=memotext
```

## Guidelines

- Python 3.11 or newer, standard library only at runtime. `pytest` and `pytest-cov` are the `test` extra, and `ruff` and `mypy` are the `lint` extra.
- Tests read synthetic fixtures only: never the live home directory, a real Voice Memos library or a real recording. Tests that need macOS or a network are skipped with a reason, and the default suite passes on Linux.
- Every public function has a test, and line coverage of the package stays at 90 percent or higher.
- No hardcoded user paths. Use `Path.home()` or a parameter.
- Never commit a real recording, a real transcript or a real `manifest.plist`. Build synthetic ones as [Build a Synthetic Recording](docs/how-to-guides/build-a-synthetic-recording.md) describes.
- Every security fix gets a test that fails without the fix. Revert the fix once to watch the test fail, then restore it.
- Documentation goes in `docs/`, in the folder for its kind: `tutorials/`, `how-to-guides/`, `reference/` or `explanation/`. Headings use Title Case, and each paragraph and list item is one line, not hard-wrapped. Filenames are lowercase kebab-case, apart from the community files and `README.md`.
- Do not use a dash as punctuation. Use a comma, colon, semicolon, period or parentheses, and write ranges as "3 to 5".
- The banner in `.github/` is made by `scripts/make-banner.py`, which needs `fonttools` and nothing else. `fonttools` is a script-only dependency and is not a dependency of the package.
- Everything committed here is public. Never add `models`, `providers` or `session-link` keys to the frontmatter of a Markdown file, never add a session link anywhere, and never credit an agent, model, model provider or agent runtime as author or contributor.
- Agent instruction files and runtime directories at the repository root are gitignored and never tracked.
- Do not copy anything from a private repository: no client names, personal paths, notes, plans or prompts. Examples and fixtures are synthetic.
- Keep any list of private terms to check for (client names, project names, private tool names) in a file outside the repository, and point `MEMOTEXT_FORBIDDEN_TERMS_FILE` at it when you run the tests. Never write such terms in the repository.
- Never commit a secret, credential, private key, `.env` file or `settings.local.json`. `.env.example` with placeholder values is allowed.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## Pull Requests

Keep each pull request to one change, describe what it does and how you tested it, and make sure the test suite, `ruff check`, `ruff format --check` and `mypy` pass. Add a line under Unreleased in [CHANGELOG.md](CHANGELOG.md) for any user-visible change.

## Roadmap

Open an issue before starting on one of these, so the approach can be agreed first.

- [ ] Check the known folder paths, the placement of the `tsrp` atom and the keys in `manifest.plist` against a real Mac library
- [ ] First release on PyPI

## License

By contributing, you agree that your contributions are licensed under the MIT license in [LICENSE](LICENSE).

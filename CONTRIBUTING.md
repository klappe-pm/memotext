# Contributing

Thank you for helping improve Voicememos. Open an issue to discuss a change before writing a large pull request, so the effort goes where it will be merged. This page holds the rules every contribution follows; the walkthroughs and reference live under [docs](docs/README.md), starting with [First Contribution](docs/tutorials/first-contribution.md). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

```bash
git clone https://github.com/klappe-pm/voicememos && cd voicememos && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test,lint]'
```

## Tests

Run the suite before every commit. [Run the Tests](docs/how-to-guides/run-the-tests.md) covers coverage, lint and type checks.

```bash
python3 -m pytest
```

## Guidelines

- Python 3.11 or newer, standard library only at runtime. `pytest` and `pytest-cov` are test dependencies; `ruff` and `mypy` are lint dependencies. `fonttools` is needed only to regenerate the banner with `scripts/make-banner.py` and is not a dependency of the package.
- Tests read synthetic fixtures only: never the live home directory, a real Voice Memos library or a real recording. Tests that need macOS or a network are skipped with a reason, and the default suite passes on Linux.
- Every public function has a test, and line coverage of the package stays at 90 percent or higher.
- `ruff check`, `ruff format --check` and `mypy` pass.
- No hardcoded user paths. Use `Path.home()` or a parameter.
- Filenames are lowercase kebab-case, apart from the uppercase community files and `README.md`. Markdown headings use Title Case, each paragraph and list item is one line, not hard-wrapped, and a dash is never used as punctuation.
- Documentation goes in `docs/`, in the folder for its kind: `tutorials/`, `how-to-guides/`, `reference/` or `explanation/`.
- Never commit a secret, credential, private key, `.env` file or `settings.local.json`. `.env.example` with placeholder values is allowed.
- Never commit a real recording, a real transcript or a real `manifest.plist`. Build synthetic ones as [Build a Synthetic Recording](docs/how-to-guides/build-a-synthetic-recording.md) describes.
- Everything committed here is visible to anyone, so treat every file, commit, pull request and comment as published. Never add `models`, `providers` or `session-link` keys to the frontmatter of any Markdown file, never add a session link anywhere, and never credit an agent, model, model provider or agent runtime as author or contributor. No co-author trailers and no "generated with" lines.
- Agent instruction files and runtime directories at the repository root (`AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `GEMINI.md`, `.claude/` and the like) are gitignored and never tracked; a contributor's own agent configuration stays on their machine.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## Pull Requests

Keep each pull request to one change, describe what it does and how you tested it, and make sure the test suite, `ruff check`, `ruff format --check` and `mypy` pass. Add a line under Unreleased in [CHANGELOG.md](CHANGELOG.md) for any user-visible change.

## Roadmap

Open an issue before starting on one of these, so the approach can be agreed first.

- [ ] Check the known folder paths, the placement of the `tsrp` atom and the keys in `manifest.plist` against a real Mac library
- [ ] First release on PyPI

## License

By contributing, you agree that your contributions are licensed under the MIT license in [LICENSE](LICENSE).

# contributing

Thank you for helping improve voicememos. Open an issue to discuss a change before writing a large pull request. This page holds the rules every contribution follows; the walkthroughs and reference live under [developer-docs](developer-docs/README.md), starting with [first contribution](developer-docs/tutorials/first-contribution.md).

## setup

```bash
git clone https://github.com/klappe-pm/voicememos && cd voicememos && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test,lint]'
```

## tests

Run the suite before every commit. [run the tests](developer-docs/how-to-guides/run-the-tests.md) covers coverage, lint and type checks.

```bash
python3 -m pytest
```

## guidelines

- Python 3.11 or newer, standard library only at runtime. `pytest` and `pytest-cov` are test dependencies; `ruff` and `mypy` are lint dependencies.
- Tests read synthetic fixtures only: never the live home directory, a real Voice Memos library or a real recording. Tests that need macOS or a network are skipped with a reason, and the default suite passes on Linux.
- Every public function has a test, and line coverage of the package stays at 90 percent or higher.
- `ruff check`, `ruff format --check` and `mypy` pass.
- No hardcoded user paths. Use `Path.home()` or a parameter.
- Filenames and Markdown headings are lowercase kebab-case. Reserved names such as `README.md` and `LICENSE` keep their spelling.
- Write one line per Markdown paragraph and list item; do not hard-wrap prose. Do not use a dash as punctuation.
- Documentation goes in `docs/` for people who use voicememos and `developer-docs/` for people who change it, in the folder the [documentation guide](docs/documentation-guide/README.md) names for its kind.
- Never commit a secret, credential, private key, `.env` file or `settings.local.json`. `.env.example` with placeholder values is allowed.
- Never commit a real recording, a real transcript or a real `manifest.plist`. Build synthetic ones as [build a synthetic recording](developer-docs/how-to-guides/build-a-synthetic-recording.md) describes.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## public-repository

Everything committed here is visible to anyone, so treat every file, commit, pull request and comment as published.

- Never add `models`, `providers` or `session-link` keys to the frontmatter of any Markdown file, and never add a session link anywhere: files, commit messages, pull request titles or bodies, or comments.
- Never credit an agent, model, model provider or agent runtime as author or contributor in files, commits, pull requests or comments. No co-author trailers and no "generated with" lines.
- Agent instruction files and runtime directories at the repository root (`AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `GEMINI.md`, `.claude/` and the like) are gitignored and never tracked; a contributor's own agent configuration stays on their machine.

## pull-requests

Keep each pull request to one change, describe what it does and how you tested it, and make sure the test suite passes. Add a line under `unreleased` in [changelog.md](changelog.md) for any user-visible change.

## license

By contributing, you agree that your contributions are licensed under the MIT license in [LICENSE](LICENSE).

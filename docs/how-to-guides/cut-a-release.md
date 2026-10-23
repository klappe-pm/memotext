# Cut a Release

This guide is for a maintainer releasing a new version of Memotext: bumping the version, settling the changelog, tagging, and publishing the package to PyPI and as a GitHub release. It assumes a clean checkout of `main` with the test suite green. It differs from the Stratarc release guide in one way, on purpose: Stratarc uploads by hand with `twine`, while Memotext publishes through PyPI trusted publishing from a pinned, approval gated workflow, so no upload token exists to leak and a required approval stands between a pushed tag and PyPI. The commands use `/path/to/memotext` for your clone.

## Where the Version Lives

The version is `__version__` in `memotext/__init__.py`. `pyproject.toml` declares the version as dynamic and reads it from that file through hatchling, so it is set in one place. The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## One-Time Setup

Do this once, before the first release.

1. On PyPI, open your account's publishing settings and add a pending trusted publisher with project name `memotext`, owner `klappe-pm`, repository `memotext`, workflow `release.yml` and environment `pypi`.
2. On GitHub, open the repository settings and create an environment named `pypi`. Add yourself as a required reviewer, so every upload waits for your approval. Under deployment branches and tags, allow only tags that match `v*`. Turn off the option that lets administrators bypass the protection rules, so the approval cannot be skipped.
3. In the repository's rulesets, add a tag ruleset that targets `v*` and restricts who can create those tags to the maintainers. Restrict updating and deleting them too, so a published tag cannot be moved.

## Steps

1. Decide the new version from the Unreleased section of [the changelog](../../CHANGELOG.md): a breaking change bumps the major version, a new capability bumps the minor, a fix bumps the patch. A version number that was ever uploaded to PyPI can never be reused, even after it is deleted.
2. Set `__version__` in `memotext/__init__.py`.
3. In the changelog, rename Unreleased to the version and the date, written `## 0.1.0 (2026-10-20)` with no dash, and open a new empty Unreleased section above it.
4. Check the README, which PyPI shows as the project page. Every link in it must be absolute, because a relative link breaks there, and the text of a published version can never be changed, so a fix ships as a new version. For the first release, delete the sentence that says nothing is published yet and the install-from-GitHub block after it in the README, and rewrite the places in [Install](install.md) that say there is no release yet.
5. Run the full set of checks:

```bash
cd /path/to/memotext && python3 -m pytest --cov=memotext && ruff check . && ruff format --check . && mypy
```

6. Run the private terms test. It skips on GitHub, because the list of terms never leaves your machine, so run it here before every release. Put one term per line in a text file outside the repository:

```bash
cd /path/to/memotext && MEMOTEXT_FORBIDDEN_TERMS_FILE=/path/to/private-terms.txt python3 -m pytest tests/test_no_personal_terms.py
```

7. Build the distributions and check them. `twine check` fails on a README that PyPI cannot render:

```bash
cd /path/to/memotext && python3 -m pip install build twine && python3 -m build --outdir dist && python3 -m twine check dist/*
```

8. Commit as `chore: release <version>` and merge it through a pull request like any other change.
9. Tag the merge commit `v<version>` and push the tag. Pushing the tag starts the release workflow:

```bash
git -C /path/to/memotext tag -a v<version> -m "memotext <version>"
```

```bash
git -C /path/to/memotext push origin v<version>
```

10. Open the workflow run on GitHub. When the build and test jobs have passed, approve the `pypi` environment. The publish job then uploads the distributions the build job made, and nothing else.
11. Create a GitHub release on the tag with the changelog section as its notes.

## What the Workflow Does

`.github/workflows/release.yml` has three jobs, and `tests/test_release_workflow.py` fails if any of these properties is lost.

- **Build.** Installs only the hash pinned `build` and `hatchling` from `requirements/build.txt`, fails unless the tagged commit is an ancestor of `origin/main`, fails unless the tag equals `v` plus the package version, builds the sdist and wheel without build isolation, and writes `sha256sum dist/*` to the job summary so you can compare the checksums with your local build.
- **Test.** Installs the hash pinned test tools from `requirements/ci.txt` and the wheel the build job made, removes the checkout's `memotext` folder so the tests import the wheel and not the source tree, and runs the suite.
- **Publish.** Needs both, runs in the `pypi` environment, and is the only job that can request an identity token.

## What the Workflow Is Allowed to Do

Every action is pinned to a full commit hash with its version in a comment, and `tests/test_release_workflow.py` fails if one is not. The workflow can read the repository and nothing else, except the publish job, which alone holds the `id-token: write` permission that trusted publishing needs. Checkout does not keep the GitHub token on disk. Every `pip install` in the workflow either uses `--require-hashes` or installs the local wheel with `--no-deps`, and the same test checks that too.

## Updating the Pinned Tools

The lock files are compiled with hashes by `pip-compile` from the small `.in` files next to them, for Python 3.11 on Linux. Regenerate them with a Python 3.11 environment that has `pip-tools`:

```bash
cd /path/to/memotext && pip-compile --generate-hashes --strip-extras --output-file=requirements/ci.txt requirements/ci.in
```

```bash
cd /path/to/memotext && pip-compile --generate-hashes --strip-extras --output-file=requirements/build.txt requirements/build.in
```

To move an action to a new release, look up the commit its tag points at, using the commit the annotated tag dereferences to when there is one, and keep the version comment in step:

```bash
git ls-remote --tags https://github.com/actions/checkout "refs/tags/v7.0.1*"
```

## After the Release

Confirm that `pipx install memotext==<version>` works, that `memotext --version` prints the version, and that the project page on pypi.org renders the README with working links.

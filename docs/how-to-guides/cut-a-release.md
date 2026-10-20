# Cut a Release

This guide publishes a new version to PyPI. Releases use PyPI trusted publishing: the workflow in `.github/workflows/release.yml` proves its identity to PyPI with a short lived token GitHub issues for that one run, so no PyPI token is stored in the repository or in GitHub settings.

## One-Time Setup

1. On PyPI, open your account's publishing settings and add a pending trusted publisher with project name `voicememos`, owner `klappe-pm`, repository `voicememos`, workflow `release.yml` and environment `pypi`.
2. On GitHub, open the repository settings, create an environment named `pypi` and add yourself as a required reviewer, so every upload waits for your approval.

## Each Release

1. Set the new version in `voicememos/__init__.py`.
2. Move the unreleased entries in `CHANGELOG.md` under a heading for that version.
3. Run every check in [run the tests](run-the-tests.md) and merge the change to `main`.
4. Tag the merged commit with the version prefixed by `v` and push the tag:

```bash
git -C /path/to/voicememos tag v0.1.0
```

```bash
git -C /path/to/voicememos push origin v0.1.0
```

5. Open the workflow run on GitHub and approve the `pypi` environment when the build job has passed.

The build job runs the full test suite and refuses to continue when the tag does not equal `v` plus the package version, so a mistyped tag never reaches PyPI.

## What the Workflow Is Allowed to Do

Every action is pinned to a full commit hash, and `tests/test_release_workflow.py` fails if one is not. The workflow can read the repository and nothing else, except the publish job, which alone holds the `id-token: write` permission that trusted publishing needs. Checkout does not keep the GitHub token on disk.

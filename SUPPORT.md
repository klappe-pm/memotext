# Support

This page says where to get help with Memotext and where to file what. Memotext is maintained in the open on GitHub and has no paid or private support channel; every question and report goes through the repository, where it is visible to the next person with the same problem.

## Before You Ask

- Match your symptom against [Troubleshooting](docs/how-to-guides/troubleshooting.md).
- Check the [changelog](CHANGELOG.md) for what has shipped.
- Search the existing [issues](https://github.com/klappe-pm/memotext/issues), open and closed.

## Where to File

| what you have | where it goes |
| --- | --- |
| a bug: Memotext did something other than what the documentation says | a [bug report](https://github.com/klappe-pm/memotext/issues/new?template=bug-report.yml) with the command you ran, what you expected, what happened and the output of `memotext --version` and `memotext probe` |
| a question about using Memotext | a [question](https://github.com/klappe-pm/memotext/issues/new?template=question.yml) with what you are trying to do and what you tried |
| a request for a feature | a [feature request](https://github.com/klappe-pm/memotext/issues/new?template=feature-request.yml) describing the need before any code; see [Contributing](CONTRIBUTING.md) |
| a suspected security vulnerability | a private report as described in [SECURITY.md](SECURITY.md); never a public issue |
| a mistake or gap in the documentation | an issue, or a pull request against the page; the [docs index](docs/README.md) shows where a page goes |

## What to Include

Paste command output as text inside a code fence rather than as a screenshot. Recording ids contain a date and time, and titles and transcripts are personal; remove or change anything you do not want public before posting. Never attach a real recording, transcript or `manifest.plist`. If the problem is a file the package cannot read, describe its structure or build a synthetic file that behaves the same way.

## Response Times

The project is maintained by one person alongside other work. Issues are read within a few days; fixes land as time allows and in order of impact.

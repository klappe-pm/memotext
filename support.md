# support

This page says where to get help with voicememos and where to file what. voicememos is maintained in the open on GitHub and has no paid or private support channel; every question and report goes through the repository, where it is visible to the next person with the same problem.

## before-you-ask

- Match your symptom against [troubleshooting](docs/how-to-guides/troubleshooting.md).
- Check the [changelog](changelog.md) for what has shipped.
- Search the existing [issues](https://github.com/klappe-pm/voicememos/issues), open and closed.

## where-to-file

| what you have | where it goes |
| --- | --- |
| a bug: voicememos did something other than what the documentation says | an [issue](https://github.com/klappe-pm/voicememos/issues/new) with the command you ran, what you expected, what happened and the output of `voicememos --version` and `voicememos probe` |
| a question about using voicememos | an [issue](https://github.com/klappe-pm/voicememos/issues/new) with what you are trying to do and what you tried |
| a request for a feature | an [issue](https://github.com/klappe-pm/voicememos/issues/new) describing the need before any code; see [contributing](contributing.md) |
| a suspected security vulnerability | a private report as described in [security.md](security.md); never a public issue |
| a mistake or gap in the documentation | an issue, or a pull request against the page; [documentation guide](docs/documentation-guide/README.md) says where a page goes |

## what-to-include

Paste command output as text inside a code fence rather than as a screenshot. Recording ids contain a date and time, and titles and transcripts are personal; remove or change anything you do not want public before posting. Never attach a real recording, transcript or `manifest.plist`. If the problem is a file the package cannot read, describe its structure or build a synthetic file that behaves the same way.

## response-times

The project is maintained by one person alongside other work. Issues are read within a few days; fixes land as time allows and in order of impact.

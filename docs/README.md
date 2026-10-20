# Documentation

Voicememos reads the Apple Voice Memos library: it finds your recordings, lists them and extracts the transcripts iOS already produced. These pages cover installing and using it, looking things up, and changing the code. They follow the four [Diátaxis](https://diataxis.fr/) quadrants, so the folder a page sits in tells you what kind of page it is.

## Tutorials

Lessons that take you through a task from start to finish. [Getting Started](tutorials/getting-started.md) goes from an install to listing a recording and reading its transcript. [First Contribution](tutorials/first-contribution.md) goes from a fresh clone to a passing test suite and a change ready for review. Index: [Tutorials](tutorials/README.md).

## How-To Guides

Recipes for a specific goal, for someone who already knows the basics.

- Use: [Install](how-to-guides/install.md), [Read Transcripts from Python](how-to-guides/read-transcripts-from-python.md), [Troubleshooting](how-to-guides/troubleshooting.md).
- Contribute: [Run the Tests](how-to-guides/run-the-tests.md), [Build a Synthetic Recording](how-to-guides/build-a-synthetic-recording.md), [Cut a Release](how-to-guides/cut-a-release.md).

Index: [How-To Guides](how-to-guides/README.md).

## Reference

Lookup pages that describe the machinery as it is. [CLI](reference/cli.md) lists every command, option, output shape and exit status, [Python API](reference/python-api.md) lists every public function, class and exception, [Library States](reference/library-states.md) lists the known folders and the four states, and [File Formats](reference/file-formats.md) describes the `tsrp` atom and the plist as far as the code understands them, marking what is inferred. [Source Layout](reference/source-layout.md) lists each module and [Test Fixtures](reference/test-fixtures.md) describes the synthetic builders. Index: [Reference](reference/README.md).

## Explanation

Background and reasons, for a reader who wants to understand rather than act. [Where macOS Keeps Voice Memos](explanation/where-macos-keeps-voice-memos.md) explains the folders and why Full Disk Access matters, [Design](explanation/design.md) explains the choices behind the package, [Security Model](explanation/security-model.md) explains what it reads, what it never does and what it trusts, and [Architecture](explanation/architecture.md) explains how a library folder becomes a list of recordings. Index: [Explanation](explanation/README.md).

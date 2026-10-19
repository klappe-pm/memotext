# developer-docs

Documentation for people who change voicememos: you clone the repository, run its tests, fix a parser or add a command, and open a pull request. It uses the same four [Diátaxis](https://diataxis.fr/) quadrants as the user documentation under [docs](../docs/README.md), so the folder a page sits in tells you what kind of page it is. Nothing here is needed to use voicememos; everything here assumes you have read the user documentation for the part you are changing.

## tutorials

Lessons that take you through a task from start to finish, for someone new to the codebase. Start with [first contribution](tutorials/first-contribution.md), which goes from a fresh clone to a passing test suite, a small change and a pull request. Index: [tutorials](tutorials/README.md).

## how-to-guides

Recipes for a specific development goal. [run the tests](how-to-guides/run-the-tests.md) covers the suite, coverage, lint and type checks, and [build a synthetic recording](how-to-guides/build-a-synthetic-recording.md) covers making fixtures without a real Voice Memos file. Index: [how-to guides](how-to-guides/README.md).

## reference

Lookup pages that describe the codebase as it is. [source layout](reference/source-layout.md) lists each module and what it holds, and [test fixtures](reference/test-fixtures.md) describes the synthetic builders and the shared pytest fixtures. Index: [reference](reference/README.md).

## explanation

Discussion of why voicememos is built the way it is. [architecture](explanation/architecture.md) explains how a library folder becomes a list of recordings, layer by layer. Index: [explanation](explanation/README.md).

# security

## reporting-a-vulnerability

Report vulnerabilities privately through GitHub security advisories: open the repository's Security tab and choose "Report a vulnerability", or go to <https://github.com/klappe-pm/voicememos/security/advisories/new>. Do not open a public issue, pull request or discussion for a suspected vulnerability.

Include the affected version or commit, the steps to reproduce, and the impact you observed. Do not attach a real recording, transcript or `manifest.plist`; describe the file structure or build a synthetic file that reproduces the problem. You will receive an acknowledgement, and the fix and disclosure are coordinated with you through the advisory.

## scope

- The `voicememos` command and the Python package.
- The parsers for the MP4 structure, the `tsrp` payload and `manifest.plist`, including any crafted file that makes them read outside the file, use unbounded memory or time, or run code.
- The optional Spotlight search, which runs the `mdfind` program on macOS.

Vulnerabilities in macOS, in the Voice Memos app, or in the Python interpreter are out of scope; report those to their maintainers. The [security model](docs/explanation/security-model.md) explains what the package reads, what it never does and what it trusts.

## supported-versions

Until the first release, only the `main` branch receives security fixes.

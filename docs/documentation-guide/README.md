# documentation-guide

This guide says where a document goes in this repository and what each kind of page is for, so a new page lands where its readers will look for it. The documentation follows [Diátaxis](https://diataxis.fr/): every page is one of four kinds, and the folder it sits in names the kind. Two trees hold the same folders, [docs](../README.md) for people who use voicememos and [developer-docs](../../developer-docs/README.md) for people who change it. Pick the tree by audience first, then the folder by kind.

## where-a-document-goes

- `tutorials/`: a lesson that takes a newcomer through a task from start to finish on one path. Written to be followed in order; links out for detail instead of including it.
- `how-to-guides/`: a recipe for one goal, for a reader who knows the basics. Steps first, explanation only where a step would otherwise surprise.
- `reference/`: a description of the machinery as it is, structured around the thing described, complete and free of instruction.
- `explanation/`: background and reasoning, read away from the keyboard; the place for why, for tradeoffs and for alternatives.
- `documentation-guide/`: this folder, holding the conventions for the documentation itself.

A page that would need to be two of these is two pages. A reference table inside a tutorial moves to `reference/` and is linked; a paragraph of rationale inside a how-to guide moves to `explanation/`.

## conventions

- Filenames and headings are lowercase kebab-case; `README.md` keeps its name, and its H1 is the folder name.
- Every page opens with a paragraph stating its purpose and what it covers, written for its audience.
- Every `README.md` in a quadrant lists the pages in that quadrant with one line each, and the tree's top-level `README.md` has one paragraph per quadrant naming every page.
- One line per paragraph and per list item; no hard-wrapped prose.
- Every code fence carries a language tag.
- No dashes as punctuation; use a comma, colon, semicolon, period or parentheses. Write ranges as "3 to 5".
- Links are relative paths within the repository.
- Facts about macOS, Voice Memos or file layouts that were not checked against a real Mac are marked as inferred where they appear.
- No frontmatter is required. The provenance keys `models`, `providers` and `session-link` are forbidden.

# Reference

Reference pages describe the machinery: the functions, the commands, the states, the file formats and the modules. They are for looking something up while you work, so they are structured around the thing they describe rather than around a task, they state facts without instruction, and they aim to be complete rather than friendly. A reference page says what an option does; the how-to guides say when to reach for it.

## Pages

- [CLI](cli.md): every command of `memotext` with its options, output shapes, exit statuses, and a note on configuration.
- [Python API](python-api.md): every public function, class, constant and exception in the `memotext` package, with signatures, return values and errors.
- [Library States](library-states.md): the known folder paths, the four states a path can be in, how a path is probed, and the Spotlight search.
- [File Formats](file-formats.md): the MP4 boxes, the `tsrp` atom and `manifest.plist` as far as the code understands them, with each inferred part marked.
- [Source Layout](source-layout.md): the repository tree, each module and its responsibility, and which functions are public.
- [Test Fixtures](test-fixtures.md): the builders in `tests/synthetic.py` and the shared pytest fixtures in `tests/conftest.py`.

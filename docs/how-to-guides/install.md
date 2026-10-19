# install

This guide covers installing voicememos for someone who already knows they want it: the supported install methods, the Python versions it runs on, and how to upgrade and uninstall. If you have never used it, start with [getting started](../tutorials/getting-started.md), which walks the install as one step among several.

## requirements

Python 3.11 or newer. voicememos has no runtime dependencies beyond the standard library. To read a real Voice Memos library you need macOS. On Linux or Windows the package installs and runs, and you can point it at a folder you copied with `--library PATH`.

## install-from-the-repository

There is no release and no PyPI package yet, so install from the repository:

```bash
pipx install git+https://github.com/klappe-pm/voicememos
```

To pin a commit or tag, add it after an `@`:

```bash
pipx install git+https://github.com/klappe-pm/voicememos@main
```

## install-into-a-virtual-environment

Use this when you want the library in a project rather than the command on your path.

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install git+https://github.com/klappe-pm/voicememos
```

## install-for-development

```bash
git clone https://github.com/klappe-pm/voicememos && cd voicememos && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test,lint]'
```

## verify

```bash
voicememos --version
```

The command prints `voicememos` and the version. `python3 -m voicememos --version` does the same without the console script on your path.

## upgrade

```bash
pipx upgrade voicememos
```

## uninstall

```bash
pipx uninstall voicememos
```

Nothing else is left behind: voicememos writes no configuration, cache or state file.

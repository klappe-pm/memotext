# Test Fixtures

This page describes the helpers that tests use to build synthetic Voice Memos files and a safe environment: the functions in `tests/synthetic.py` and the pytest fixtures in `tests/conftest.py` and `tests/test_recording.py`. No fixture is a real recording. For how to use them, see [build a synthetic recording](../how-to-guides/build-a-synthetic-recording.md).

## Synthetic Builders

| function | returns | purpose |
| --- | --- | --- |
| `box(kind, payload=b"")` | `bytes` | one MP4 box with a 32 bit size |
| `large_box(kind, payload=b"")` | `bytes` | one MP4 box using the 64 bit size form |
| `mvhd(duration_seconds, timescale=1000, version=0)` | `bytes` | a movie header box; `version=1` uses the 64 bit layout |
| `tsrp_payload(text=None, *, runs=None)` | `bytes` | the JSON payload of a `tsrp` box; `text` is split into runs alternating text and an integer index, or pass `runs` directly |
| `make_m4a(path, *, transcript, duration, tsrp, place, mdat_size)` | `Path` | write a synthetic `.m4a`; `transcript` builds a standard payload, `tsrp` gives raw payload bytes, `place` is `udta`, `moov`, `meta`, `trak` or `top` |
| `write_manifest(composition, data, *, binary=False)` | `Path` | create a `.composition` folder holding a `manifest.plist` written with `plistlib` |

`make_m4a` writes `ftyp`, then `moov` (with the movie header if `duration` is given and the `tsrp` box if a payload is given and `place` is not `top`), then the `tsrp` box if `place` is `top`, then `mdat` filled with `0x01` bytes.

## Pytest Fixtures

| fixture | scope | purpose |
| --- | --- | --- |
| `fake_home` | every test (autouse) | points `HOME` and `USERPROFILE` at an empty temp folder, so `~` never reaches the real home directory |
| `library` | test | an empty folder named `Recordings` in the test's temp directory |
| `default_library` | test | an empty folder at the first known macOS path under `fake_home` |
| `set_timezone` | test | returns a function that sets the local timezone with `time.tzset`; restored when the test ends; skips where `tzset` is missing |
| `utc_timezone` | test | `set_timezone("UTC")` |

## Patching Conventions

Tests that simulate a blocked folder patch `os.scandir` with a function or a `RaisingScandir` object that raises `PermissionError`. This runs as root, unlike a `chmod 000` directory. Tests that simulate an unreadable file patch `os.open`, which every file read goes through. Tests that simulate macOS or Linux patch `sys.platform` and `os.access`, and replace `subprocess.run`, so no test ever runs the real `mdfind`; `shutil.which` is patched to fail, to prove `mdfind` is not looked up on `PATH`.

## Deadlines

`tests/test_hardening.py` holds the hostile input tests. Those that would hang or run for minutes without their fix run inside its `deadline(seconds)` context manager, which uses `signal.setitimer` to raise `TimeoutError`, so a regression fails in seconds. The helper skips where `setitimer` is missing. Tests that need a FIFO or a symlink skip where the platform lacks them. Use `monkeypatch` for every patch so it is undone at the end of the test. A test that needs a folder nested too deeply for a path uses the `deep_folder` helper, which makes and removes the levels one at a time relative to the current directory.

## Skips

A skip must carry a reason. Tests marked `repo_only` skip when `.github/`, `docs/` or `CONTRIBUTING.md` is missing, which is the case in an extracted sdist; the hook that does this is in `tests/conftest.py`. The skips today are the three tests that use a real unreadable directory (skipped as root or on Windows), the timezone tests (skipped without `time.tzset`), and the FIFO, symlink and deadline tests (skipped without `os.mkfifo`, symlink support or `signal.setitimer`).

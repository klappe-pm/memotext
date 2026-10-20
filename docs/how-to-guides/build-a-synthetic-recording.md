# Build a Synthetic Recording

This guide shows how to make a fixture for a test: an `.m4a` file with a duration and a transcript, and a `.composition` folder with a `manifest.plist`, all built in code. Every fixture in this repository is synthetic. Never commit a real recording, transcript or manifest, and never copy one into a test. The builders are in `tests/synthetic.py`; [test fixtures](../reference/test-fixtures.md) lists them.

## A Recording with a Transcript

```python
from pathlib import Path

from tests.synthetic import make_m4a, write_manifest


def test_example(library: Path) -> None:
    make_m4a(library / "20250115 143022-ABCD1234.m4a", duration=61.0, transcript="hello there")
    write_manifest(library / "20250115 143022-ABCD1234.composition", {"title": "Example"})
```

`library` is the shared fixture for an empty recordings folder. `make_m4a` writes a minimal MP4: a `ftyp` box, a `moov` box holding a movie header and the `tsrp` atom, and an `mdat` box of filler bytes.

## Put the Atom Somewhere Else

The `place` argument moves the `tsrp` box, which tests the reader's search:

```python
make_m4a(path, transcript="words", place="meta")
```

The places are `udta` (the default), `moov`, `meta`, `trak` and `top`.

## Write a Raw Payload

To test malformed or unusual payloads, pass the bytes yourself:

```python
make_m4a(path, tsrp=b"not json")
make_m4a(path, tsrp=tsrp_payload(runs=["Hello", 0, " world", 1]))
```

## Build Boxes by Hand

For a damaged file, build the bytes and write them:

```python
import struct

from tests.synthetic import box

path.write_bytes(box(b"ftyp", b"M4A ") + struct.pack(">I4s", 3, b"free"))
```

`box` builds a box with a 32 bit size, and `large_box` builds one with the 64 bit size form.

## Write a Manifest

`write_manifest(folder, data)` creates the folder and writes `manifest.plist` with `plistlib`. Pass `binary=True` for a binary plist. Dates in `data` are written as plist dates, and read back as naive UTC datetimes.

```python
from datetime import datetime

write_manifest(folder, {"creationDate": datetime(2025, 3, 1, 9, 0), "duration": 12.5})
```

## Keep Fixtures Honest

A synthetic file proves the reader handles the structure you built, not that real files look like it. When you add a fixture because of a real file that failed, describe the structure of the real file in the issue, build the smallest synthetic file with that structure, and mark any assumption about the real format as inferred in [file formats](../reference/file-formats.md).

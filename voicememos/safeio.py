"""Open files from a library without following symlinks or blocking on special files.

A Voice Memos folder is written by other programs, so a name in it may be a symlink that points
outside the folder, or a FIFO that blocks any reader forever. Every file voicememos reads is
opened here: with `O_NOFOLLOW` so a symlink is refused, with `O_NONBLOCK` so a FIFO cannot hang
the open, and then checked with `fstat` to be a regular file.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import BinaryIO

from voicememos.errors import UnsafeFileError

_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)

ABSENT_ERRORS = (FileNotFoundError, NotADirectoryError, IsADirectoryError, UnsafeFileError)
"""Exceptions that parsers treat as an absent file. `PermissionError` is not among them."""


def open_regular(path: Path) -> BinaryIO:
    """Open `path` for reading and return the file object.

    Raises `FileNotFoundError` if nothing is there, `UnsafeFileError` if the final component is a
    symlink or the file is not a regular file, and `PermissionError` if it may not be read.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENXIO, errno.EISDIR):
            raise UnsafeFileError(exc.errno, "not a regular file", str(path)) from exc
        raise
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise UnsafeFileError(errno.EINVAL, "not a regular file", str(path))
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def is_real_dir(path: Path) -> bool:
    """True if `path` is a directory and not a symlink to one."""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False

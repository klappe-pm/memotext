"""Open files from a library without following symlinks or blocking on special files.

A Voice Memos folder is written by other programs, so a name in it may be a symlink that points
outside the folder, or a FIFO that blocks any reader forever. Every file voicememos reads is
opened here: with `O_NOFOLLOW` so a symlink is refused, with `O_NONBLOCK` so a FIFO cannot hang
the open, and then checked with `fstat` to be a regular file.

A folder inside a library is opened the same way, with `O_DIRECTORY` and `O_NOFOLLOW`, and the
files in it are then opened relative to that descriptor. A folder that is swapped for a symlink
after it was checked is refused, and a name cannot be redirected once the folder is open. A
platform without `dir_fd` support (Windows) falls back to paths and `lstat` checks, which cannot
close that race.
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

_DIR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)

SUPPORTS_DIR_FD = os.open in os.supports_dir_fd and os.scandir in os.supports_fd
"""True where folders can be held as descriptors and entries opened relative to them."""

DirRef = int | Path
"""A held folder: a descriptor where `SUPPORTS_DIR_FD`, otherwise the path."""

ABSENT_ERRORS = (FileNotFoundError, NotADirectoryError, IsADirectoryError, UnsafeFileError)
"""Exceptions that parsers treat as an absent file. `PermissionError` is not among them."""


def open_regular(path: Path | str, *, dir_fd: int | None = None) -> BinaryIO:
    """Open `path` for reading and return the file object.

    With `dir_fd` the path is read relative to that open folder. Raises `FileNotFoundError` if
    nothing is there, `UnsafeFileError` if the final component is a symlink or the file is not a
    regular file, and `PermissionError` if it may not be read.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS, dir_fd=dir_fd)
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


def open_dir(path: Path | str, *, parent: DirRef | None = None) -> DirRef:
    """Open a folder without following a symlink and return it as a `DirRef`.

    With `parent`, `path` is a name inside that open folder. Raises `FileNotFoundError` if
    nothing is there, `UnsafeFileError` if the final component is a symlink or not a folder, and
    `PermissionError` if it may not be opened. Close the result with `close_dir`.
    """
    if not SUPPORTS_DIR_FD:
        full = parent / path if isinstance(parent, Path) else Path(path)
        if not is_real_dir(full):
            if not os.path.lexists(full):
                raise FileNotFoundError(errno.ENOENT, "no such folder", str(full))
            raise UnsafeFileError(errno.ENOTDIR, "not a real folder", str(full))
        return full
    try:
        return os.open(path, _DIR_FLAGS, dir_fd=parent if isinstance(parent, int) else None)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafeFileError(exc.errno, "not a real folder", str(path)) from exc
        raise


def close_dir(ref: DirRef) -> None:
    """Close a folder returned by `open_dir`. A path needs no closing."""
    if isinstance(ref, int):
        os.close(ref)


def open_child(ref: DirRef, name: str) -> BinaryIO:
    """Open the regular file `name` inside the held folder `ref`, as `open_regular` does."""
    if isinstance(ref, int):
        return open_regular(name, dir_fd=ref)
    return open_regular(ref / name)


def scan_dir(ref: DirRef) -> tuple[list[str], list[str]]:
    """List a held folder as sorted names of real folders and of regular files.

    Symlinks, FIFOs and every other kind of entry are left out. An error from listing the folder
    is raised, never ignored.
    """
    folders: list[str] = []
    files: list[str] = []
    with os.scandir(ref) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                folders.append(entry.name)
            elif entry.is_file(follow_symlinks=False):
                files.append(entry.name)
    return sorted(folders), sorted(files)

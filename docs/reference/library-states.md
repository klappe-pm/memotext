# Library States

This page describes how memotext decides whether a Voice Memos folder is usable: the known folder paths, the four states a path can be in, how a path is probed, and the optional Spotlight search. It is the reference for layer 1 (the known paths) and layer 2 (Spotlight) of folder discovery. There are no interactive layers: nothing here prompts, opens System Settings or changes a permission. The reasoning is in [where macOS keeps Voice Memos](../explanation/where-macos-keeps-voice-memos.md).

## Known Paths

`KNOWN_PATHS`, in order of preference. Each is relative to the user's home directory.

| order | path | status |
| --- | --- | --- |
| 1 | `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings` | inferred; the location on current macOS releases |
| 2 | `~/Library/Mobile Documents/com~apple~VoiceMemos/Recordings` | inferred; an iCloud Drive staging location |
| 3 | `~/Library/Containers/com.apple.VoiceMemos/Data/Library/Application Support/Recordings` | inferred; a sandbox container location |
| 4 | `~/Library/Application Support/com.apple.voicememos/Recordings` | inferred; older macOS releases |
| 5 | `~/Library/Application Support/com.apple.VoiceMemos/Recordings` | inferred; a spelling variant of the previous path |

The list was carried over from the code this package was extracted from. It has not been checked against a real Mac while writing this package.

## The Four States

| state | condition | `recording_count` | `detail` |
| --- | --- | --- | --- |
| `missing` | listing the path failed because nothing exists there, or the path is not a directory | 0 | the operating system message |
| `readable` | the directory can be listed and holds at least one `.m4a` file | the number of `.m4a` files | None |
| `blocked` | listing the path failed with a permission error or any other operating system error | 0 | the operating system message |
| `empty` | the directory can be listed and holds no `.m4a` file | 0 | None |

A path whose parent is missing is `missing`. A path whose parent cannot be searched is `blocked`.

## How a Path Is Probed

The path is expanded (`~` becomes the home directory) and the directory is listed with `os.scandir`. It is not tested with `exists`. Listing is the operation that fails under a missing permission, so using it is what keeps a blocked folder from being reported as missing or found.

- `FileNotFoundError` and `NotADirectoryError` give `missing`.
- Every other `OSError`, which includes `PermissionError`, gives `blocked`.
- Otherwise the entries are counted. An entry counts when its name ends in `.m4a` in any letter case and it is a regular file. A directory, a symlink or a FIFO named like an audio file does not count.

A permission error that appears part way through the listing is also `blocked`.

## What Find Library Accepts

`find_library` accepts only `readable`. A `blocked` path is never returned, and neither is an `empty` one. To learn why nothing was found, call `probe_library`.

## Spotlight

`spotlight_search` runs two queries with `/usr/bin/mdfind`, by that absolute path and not through `PATH`, and returns the parent folder of every hit, once each, in the order found.

| query | status |
| --- | --- |
| `mdfind -name CloudRecordings.db` | inferred; assumes the database sits in the recordings folder |
| `mdfind 'kMDItemContentType == "com.apple.m4a-audio" && kMDItemPath == "*VoiceMemos*"'` | inferred; assumes the path of a recording mentions VoiceMemos |

Neither query has been run against a real Spotlight index while writing this package. The search runs only on macOS, only when `mdfind` is found, and only when `find_library(spotlight=True)` or `--spotlight` asks for it. It runs `mdfind` with a 30 second timeout and treats any failure as no results. The candidates are probed like any other path and ranked by recording count; recency is not used.

`find_library` considers a candidate only when it lies inside one of four containers under `~/Library`, compared without regard to case:

- `Group Containers/group.com.apple.VoiceMemos.shared`
- `Mobile Documents/com~apple~VoiceMemos`
- `Containers/com.apple.VoiceMemos`
- `Application Support/com.apple.voicememos`

The path as Spotlight reported it and the same path with symlinks resolved must both lie inside one of them, and the path may not contain `..`. A folder that Spotlight indexed elsewhere whose path merely contains "VoiceMemos", such as `~/Downloads/VoiceMemos-shared`, is never adopted, because the first folder with recordings in it would otherwise become the one `list` and `show` read. `spotlight_search` itself still returns every hit; the filter is `memotext.discovery.is_voice_memos_container`, applied by `find_library`.

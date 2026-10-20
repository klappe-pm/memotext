# Where macOS Keeps Voice Memos

This page explains where the Voice Memos app keeps recordings on a Mac, what is in that folder, how iCloud changes what you find there, and why Full Disk Access decides whether a program can read it at all. It is background for a reader who sees `blocked` or `empty` in `voicememos probe` and wants to know why. It states plainly what is inferred: no Mac was used to write this package, so the folder names and behaviours below come from the code it was extracted from and from general knowledge of how macOS protects user data. The steps to fix a blocked folder are in [troubleshooting](../how-to-guides/troubleshooting.md), and the exact list of paths is in [library states](../reference/library-states.md).

## The Folder

Voice Memos does not keep recordings in the Music or Documents folder where you can browse them in Finder as ordinary files. It keeps them in the user's Library folder, inside a location that belongs to the app. Which location depends on the macOS version. The package checks five, in order, and the first one on current macOS releases is a group container: `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings`. Older releases used a folder under `~/Library/Application Support`, and an iCloud related folder under `~/Library/Mobile Documents` also exists. All five are inferred. If your macOS moved the folder, `voicememos probe --spotlight` asks Spotlight for other candidates, and `--library PATH` accepts any folder you point it at.

## What Is in It

The inferred layout is one `.m4a` audio file per recording, named with the date and a short identifier, such as `20250115 143022-ABCD1234.m4a`. A recording may have a folder of the same name ending in `.composition`, which holds a `manifest.plist` with the title, dates, duration and sometimes the transcript. There is also a database file, `CloudRecordings.db`, that the app uses to index recordings. voicememos does not read the database. It reads the audio files and the manifests, and finds the transcript in whichever of the two holds it. [file formats](../reference/file-formats.md) describes both and marks what is inferred.

## iCloud

When Voice Memos syncs through iCloud, a recording made on the phone reaches the Mac some time later. Until it arrives, the Mac has either nothing or a partial file. Two consequences follow. A folder can be `empty` simply because sync has not run, and a file can change between two reads while it downloads. voicememos does not wait for a file to settle. A script that cares should compare [content_hash](../reference/python-api.md#content_hash) values across two reads a few seconds apart.

## Why Full Disk Access Matters

macOS protects some folders in your own Library from programs you run, even though your user owns them. The protection is by application, not by user: a program can list the folder only if the application it runs under has been granted the permission. In a terminal session that application is the terminal. In a scheduled job it is whatever launches the job. The setting that grants this is Full Disk Access, under Privacy and Security in System Settings. That the Voice Memos folders fall under this protection is inferred from the way the original tool reported failures; the fact that the protection applies to an application and not to a user is general macOS behaviour.

Without the grant, the folder is present but listing it fails with a permission error. This is the case that decides how the package works. If a program only asks whether the folder exists, it sees a folder and concludes it has found the library. The failure then shows up later, as an unexplained empty result or a crash, far from the cause. voicememos instead lists the folder, which is the operation the permission governs, and reports four states:

- `missing`: there is nothing there.
- `readable`: it can be listed and holds recordings.
- `blocked`: it is there and cannot be listed.
- `empty`: it can be listed and holds no recordings.

A blocked folder is never reported as found, missing or empty. `find_library` skips it, `list` and `show` refuse to read it and say that it exists but cannot be listed, and `probe` prints the hint for granting access. This is deliberate: the one thing a person can do about `blocked` is different from what they can do about `missing` or `empty`, so the tool must not blur them.

## What Voicememos Does Not Do

It does not open System Settings, ask you to type a path, check iCloud sync or change any permission. Those are interactive steps, and this package is a non interactive library and command. It tells you the state and leaves the decision to you.

## What Is Not Verified

One point matters for correctness and has not been checked on a real Mac: that listing a protected folder without the grant raises a permission error rather than returning an empty list. The tests cover the logic with a mocked permission error and with a real directory whose mode forbids listing, both on Linux. If macOS returns an empty listing instead, a protected folder would show as `empty`. Open an issue if you see that on your Mac.

Because Full Disk Access is a broad grant, grant it to the one application that needs it, and revoke it when you are done if you do not need it. The [security model](security-model.md) discusses this.

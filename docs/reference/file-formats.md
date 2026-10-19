# file-formats

This page describes the files voicememos reads, as far as the code understands them: the MP4 box structure of an `.m4a` recording, the `tsrp` atom that carries the iOS transcript, the movie header that carries the duration, the `manifest.plist` in a `.composition` folder, and the file naming. It also states how each field of a `Recording` is chosen. Each statement is marked. No real Voice Memos file was available while this package was written, so the tests use synthetic files built to match these descriptions.

## how-to-read-the-status-column

| status | meaning |
| --- | --- |
| defined | fixed by the MP4 or property list format itself, independent of Voice Memos |
| inferred | taken from the code this package was extracted from, or reasoned from it; not verified against a real file |
| design | a choice made by this package, not a property of the files |

## mp4-boxes

An `.m4a` file is a sequence of boxes (also called atoms). The reader walks them with seeks and never loads the audio.

| item | detail | status |
| --- | --- | --- |
| header | a 4 byte big endian size, then a 4 character type | defined |
| size 1 | an 8 byte big endian size follows the type | defined |
| size 0 | the box runs to the end of its parent | defined |
| containers followed | `moov`, `trak`, `mdia`, `minf`, `stbl`, `udta` and `meta` | design |
| `meta` prefix | four bytes of version and flags are skipped when they are all zero | inferred |
| nesting limit | 8 levels | design |
| box larger than its parent | clamped to the parent and treated as a damaged file | design |

## duration

The duration comes from the movie header box, `mvhd`, found directly inside `moov`.

| layout | version 0 | version 1 | status |
| --- | --- | --- | --- |
| after 1 byte version and 3 bytes flags | creation time (4), modification time (4), time scale (4), duration (4) | creation time (8), modification time (8), time scale (4), duration (8) | defined |

The duration in seconds is the duration divided by the time scale. A time scale of 0, a short header or another version gives no duration. That the `mvhd` duration matches the recording length for Voice Memos files is inferred.

## tsrp

The `tsrp` atom holds the transcript iOS and macOS produced.

| item | detail | status |
| --- | --- | --- |
| box type | `tsrp` | inferred |
| location | anywhere in the container boxes above, usually under `moov`; the exact parent is not known | inferred |
| payload | UTF-8 JSON, starting directly after the 8 byte box header, with no version and flags | inferred |
| padding | trailing NUL bytes are ignored | design |
| size limit | a payload over 32 MiB is refused | design |

The JSON shape the reader accepts:

```json
{
  "locale": {"identifier": "en_US"},
  "attributedString": {"runs": ["Hello", 0, " world", 1]}
}
```

`attributedString` may also be a bare list in place of the object with `runs`. The list alternates text and integer attribute indexes. The reader keeps the strings, joins them with nothing in between, and strips the ends. The integers are ignored. The `locale` key and any other key are not read. All of this shape is inferred.

### when-the-box-is-not-found

If the box tree parses cleanly (the top level boxes tile the file exactly and include `moov`) and no `tsrp` is found, the file has no transcript and the bytes are not searched. If the structure is damaged, the reader falls back to scanning the file for the four bytes `tsrp`, and treats the four bytes before a hit as the box size. The scan reads at most the first 64 MiB and examines at most 1,000 hits. If the walk spent its budget of 10,000 boxes, the file is refused and not scanned. This fallback keeps the behaviour of the tool this package was extracted from, which searched the bytes. It is a design choice, and it may read a hit that is not a real box when the file is damaged. The limits are collected in the [security model](../explanation/security-model.md).

## composition-folders

Next to `<id>.m4a` there may be a folder `<id>.composition`. That the folder holds the memo's metadata is inferred. The reader looks for one file in it, `manifest.plist`, and hashes every file under it for [content_hash](api.md#content-hash).

## manifest-plist

`manifest.plist` is a property list, either XML or binary; both are read with the standard library `plistlib` (defined). Voice Memos writes real files in whichever form it chooses; which one is not known. A file that is not a valid plist, or whose top level is not a dictionary, is treated as absent.

Keys read, all inferred:

| key | type | used for |
| --- | --- | --- |
| `title` | string | the title |
| `customLabel` | string | the title, when `title` is blank or absent |
| `creationDate` | date | the recording time. `plistlib` returns a naive datetime that holds UTC, and the reader treats it as UTC |
| `duration` | number | the duration in seconds, ahead of the audio header. A boolean, a negative number or a non-number is ignored |

### the-transcript-in-the-plist

The layout of a transcript in the plist is not known. The reader searches the whole structure with these rules, in this order, and returns the first text it finds. Every rule is inferred, and the whole search is a heuristic.

1. A string value is the text, stripped.
2. A dictionary's `text`, `string` or `content` string.
3. A dictionary's `attributedString` or `attributedText` value read as `runs`, as in the tsrp payload above.
4. A dictionary's `segments`, `utterances` or `phrases` list, where each item is a string or a dictionary with one of `text`, `string`, `content`, `utterance` or `displayText`. Segments are joined with a single space.
5. Any dictionary entry whose key contains `transcript`, `speech`, `dictation` or `caption` (any letter case), searched with the same rules.
6. A list is tried as segments, then each item is searched.

A list made only of strings is read as attributed string runs and joined with nothing between them, because the two cannot be told apart. Blank text counts as no text.

## file-names

| item | detail | status |
| --- | --- | --- |
| audio file | `<id>.m4a`; a recording is any file whose name ends in `.m4a` in any letter case | design |
| id | the file name without the extension | design |
| date in the name | `YYYYMMDD HHMMSS-UUID`, for example `20250115 143022-ABCD1234`; the part after the dash is hex digits and dashes | inferred |
| time zone of that date | local time at the place of recording | inferred |

A file whose name does not match, for example a name made only of a UUID, has no date in its name.

## how-recording-fields-are-chosen

| field | first choice | then | then |
| --- | --- | --- | --- |
| `recorded_at` | manifest `creationDate`, as UTC | the date in the file name, read as local time | the file creation time (`st_birthtime`, which exists on macOS only), else the modification time, as UTC |
| `duration_seconds` | manifest `duration` | the `mvhd` box | None |
| `title` | manifest `title` | manifest `customLabel` | `Voice Memo Jan 15, 2025 2:30:22 PM`, built from `recorded_at` in local time with English month names |
| transcript | the `tsrp` atom | the manifest search above | None |

All of these orders are design choices, kept from the original tool except that the title text uses no dash and the duration needs no third party reader.

## not-read

`CloudRecordings.db`, any other file in the library folder, and every other key in the plist are not read.

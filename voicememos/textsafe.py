"""Make text from untrusted files safe to print on a terminal."""

from __future__ import annotations

import unicodedata

# Characters that are not in a Unicode category the check below catches, but that are invisible or
# that change how nearby text is shown: the combining grapheme joiner, the Hangul fillers (category
# Lo, drawn as blanks), the variation selectors, and the whole tag block, which can carry hidden
# ASCII text.
_EXTRA_CHARS = frozenset(
    {0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0}
    | set(range(0x180B, 0x180E))
    | set(range(0xFE00, 0xFE10))
    | set(range(0xE0000, 0xE0080))
    | set(range(0xE0100, 0xE01F0))
)

# Categories escaped whatever the code point: Cf (format, which includes the bidirectional
# controls, the zero width characters, the invisible operators and the interlinear annotation
# marks), Zl (line separator) and Zp (paragraph separator).
_ESCAPED_CATEGORIES = frozenset({"Cf", "Zl", "Zp"})

_MNEMONIC = {0x0A: "\\n", 0x0D: "\\r", 0x09: "\\t"}


def _escape(code: int) -> str:
    if code in _MNEMONIC:
        return _MNEMONIC[code]
    if code <= 0xFF:
        return f"\\x{code:02x}"
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


def _needs_escape(code: int) -> bool:
    if code < 0x20 or 0x7F <= code <= 0x9F:
        return True
    if code < 0xAD:
        return False
    return code in _EXTRA_CHARS or unicodedata.category(chr(code)) in _ESCAPED_CATEGORIES


def printable(text: str, *, keep_newlines: bool = False) -> str:
    """Return `text` with everything unsafe for a terminal replaced by a visible escape.

    C0 control characters (including ESC, BEL and newline), DEL, the C1 controls U+0080 to U+009F,
    and invisible format and separator characters become `\\xNN`, `\\uNNNN` or `\\UNNNNNNNN`, with
    `\\n`, `\\r` and `\\t` for those three. The invisible characters are every character in the
    Unicode categories `Cf`, `Zl` and `Zp` (bidirectional controls, zero width characters, the soft
    hyphen, the invisible operators, the Arabic letter mark, the line and paragraph separators),
    the combining grapheme joiner, the Hangul filler characters, the variation selectors and the
    tag block U+E0000 to U+E007F.
    A lone surrogate, which cannot be encoded as UTF-8, becomes a question mark. With
    `keep_newlines`, line feeds pass through so multi line text keeps its shape; every other
    control character is still escaped. Backslashes are left alone, so the output cannot be told
    apart from text that contains a literal backslash sequence.
    """
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if keep_newlines and code == 0x0A:
            out.append(ch)
        elif _needs_escape(code):
            out.append(_escape(code))
        else:
            out.append(ch)
    return "".join(out)

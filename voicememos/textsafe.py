"""Make text from untrusted files safe to print on a terminal."""

from __future__ import annotations

import unicodedata
from functools import lru_cache

# The Default_Ignorable_Code_Point property of Unicode 15.0 (DerivedCoreProperties.txt): code points
# that a renderer draws as nothing, assigned or not. The `unicodedata` module does not expose the
# property, so the ranges are written out. They cover the soft hyphen, the combining grapheme
# joiner, the Arabic letter mark, the Hangul fillers, the Khmer and Mongolian invisible vowels and
# selectors, the zero width and bidirectional controls, the invisible operators, the variation
# selectors, the byte order mark, the unassigned gaps next to them, and the whole tag block with
# the unassigned block after it (U+E0000 to U+E0FFF).
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)

# Noncharacters: U+FDD0 to U+FDEF and the last two code points of every plane. They are never
# assigned, and no renderer is required to draw them.
_NONCHARACTERS = (
    *range(0xFDD0, 0xFDF0),
    *(plane + low for plane in range(0, 0x110000, 0x10000) for low in (0xFFFE, 0xFFFF)),
)

_ESCAPED_CODES = frozenset(
    code for low, high in _DEFAULT_IGNORABLE for code in range(low, high + 1)
) | frozenset(_NONCHARACTERS)

# Categories escaped whatever the code point: Cf (format, which includes the bidirectional
# controls, the zero width characters, the invisible operators and the interlinear annotation
# marks), Cn (unassigned, so a renderer's behaviour is unknown), Co (private use, which a font can
# draw as anything), Zl (line separator) and Zp (paragraph separator).
_ESCAPED_CATEGORIES = frozenset({"Cf", "Cn", "Co", "Zl", "Zp"})

_MNEMONIC = {0x0A: "\\n", 0x0D: "\\r", 0x09: "\\t"}


def _escape(code: int) -> str:
    if code in _MNEMONIC:
        return _MNEMONIC[code]
    if code <= 0xFF:
        return f"\\x{code:02x}"
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


@lru_cache(maxsize=65536)
def _needs_escape(ch: str) -> bool:
    """True if the character must not reach a terminal as itself. Cached per character."""
    code = ord(ch)
    if code < 0x20 or 0x7F <= code <= 0x9F:
        return True
    if code < 0xAD:
        return False
    return code in _ESCAPED_CODES or unicodedata.category(ch) in _ESCAPED_CATEGORIES


def printable(text: str, *, keep_newlines: bool = False) -> str:
    """Return `text` with everything unsafe for a terminal replaced by a visible escape.

    C0 control characters (including ESC, BEL and newline), DEL, the C1 controls U+0080 to U+009F,
    and invisible, undefined and separator characters become `\\xNN`, `\\uNNNN` or
    `\\UNNNNNNNN`, with `\\n`, `\\r` and `\\t` for those three. The invisible and undefined
    characters are every character in the Unicode categories `Cf` (format), `Cn` (unassigned), `Co`
    (private use), `Zl` and `Zp`; every code point with the Default_Ignorable_Code_Point property
    (the soft hyphen, the combining grapheme joiner, the Hangul fillers, the variation selectors,
    the tag block U+E0000 to U+E0FFF and the rest); and every noncharacter.
    A lone surrogate, which cannot be encoded as UTF-8, becomes a question mark. With
    `keep_newlines`, line feeds pass through so multi line text keeps its shape; every other
    control character is still escaped. Backslashes are left alone, so the output cannot be told
    apart from text that contains a literal backslash sequence.
    """
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    # Decide once per distinct character, then rewrite the text in one pass. Most text holds
    # nothing to escape, and is returned as it is.
    distinct = set(text)
    if keep_newlines:
        distinct.discard("\n")
    unsafe = [ch for ch in distinct if _needs_escape(ch)]
    if not unsafe:
        return text
    return text.translate({ord(ch): _escape(ord(ch)) for ch in unsafe})

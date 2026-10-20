"""Make text from untrusted files safe to print on a terminal."""

from __future__ import annotations

import re
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

# The Emoji property of Unicode 15.0 (emoji-data.txt), above U+007F. The digits, the number sign
# and the asterisk have the property too, but they are emoji only inside a keycap sequence, so they
# are handled apart (`_KEYCAP_BASES`). The ranges are written out because `unicodedata` does not
# expose the property.
_EMOJI_RANGES = (
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x231A, 0x231B),
    (0x2328, 0x2328),
    (0x23CF, 0x23CF),
    (0x23E9, 0x23F3),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2600, 0x2604),
    (0x260E, 0x260E),
    (0x2611, 0x2611),
    (0x2614, 0x2615),
    (0x2618, 0x2618),
    (0x261D, 0x261D),
    (0x2620, 0x2620),
    (0x2622, 0x2623),
    (0x2626, 0x2626),
    (0x262A, 0x262A),
    (0x262E, 0x262F),
    (0x2638, 0x263A),
    (0x2640, 0x2640),
    (0x2642, 0x2642),
    (0x2648, 0x2653),
    (0x265F, 0x2660),
    (0x2663, 0x2663),
    (0x2665, 0x2666),
    (0x2668, 0x2668),
    (0x267B, 0x267B),
    (0x267E, 0x267F),
    (0x2692, 0x2697),
    (0x2699, 0x2699),
    (0x269B, 0x269C),
    (0x26A0, 0x26A1),
    (0x26A7, 0x26A7),
    (0x26AA, 0x26AB),
    (0x26B0, 0x26B1),
    (0x26BD, 0x26BE),
    (0x26C4, 0x26C5),
    (0x26C8, 0x26C8),
    (0x26CE, 0x26CF),
    (0x26D1, 0x26D1),
    (0x26D3, 0x26D4),
    (0x26E9, 0x26EA),
    (0x26F0, 0x26F5),
    (0x26F7, 0x26FA),
    (0x26FD, 0x26FD),
    (0x2702, 0x2702),
    (0x2705, 0x2705),
    (0x2708, 0x270D),
    (0x270F, 0x270F),
    (0x2712, 0x2712),
    (0x2714, 0x2714),
    (0x2716, 0x2716),
    (0x271D, 0x271D),
    (0x2721, 0x2721),
    (0x2728, 0x2728),
    (0x2733, 0x2734),
    (0x2744, 0x2744),
    (0x2747, 0x2747),
    (0x274C, 0x274C),
    (0x274E, 0x274E),
    (0x2753, 0x2755),
    (0x2757, 0x2757),
    (0x2763, 0x2764),
    (0x2795, 0x2797),
    (0x27A1, 0x27A1),
    (0x27B0, 0x27B0),
    (0x27BF, 0x27BF),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x1F004, 0x1F004),
    (0x1F0CF, 0x1F0CF),
    (0x1F170, 0x1F171),
    (0x1F17E, 0x1F17F),
    (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A),
    (0x1F1E6, 0x1F1FF),
    (0x1F201, 0x1F202),
    (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F23A),
    (0x1F250, 0x1F251),
    (0x1F300, 0x1F321),
    (0x1F324, 0x1F393),
    (0x1F396, 0x1F397),
    (0x1F399, 0x1F39B),
    (0x1F39E, 0x1F3F0),
    (0x1F3F3, 0x1F3F5),
    (0x1F3F7, 0x1F4FD),
    (0x1F4FF, 0x1F53D),
    (0x1F549, 0x1F54E),
    (0x1F550, 0x1F567),
    (0x1F56F, 0x1F570),
    (0x1F573, 0x1F57A),
    (0x1F587, 0x1F587),
    (0x1F58A, 0x1F58D),
    (0x1F590, 0x1F590),
    (0x1F595, 0x1F596),
    (0x1F5A4, 0x1F5A5),
    (0x1F5A8, 0x1F5A8),
    (0x1F5B1, 0x1F5B2),
    (0x1F5BC, 0x1F5BC),
    (0x1F5C2, 0x1F5C4),
    (0x1F5D1, 0x1F5D3),
    (0x1F5DC, 0x1F5DE),
    (0x1F5E1, 0x1F5E1),
    (0x1F5E3, 0x1F5E3),
    (0x1F5E8, 0x1F5E8),
    (0x1F5EF, 0x1F5EF),
    (0x1F5F3, 0x1F5F3),
    (0x1F5FA, 0x1F64F),
    (0x1F680, 0x1F6C5),
    (0x1F6CB, 0x1F6D2),
    (0x1F6D5, 0x1F6D7),
    (0x1F6DC, 0x1F6E5),
    (0x1F6E9, 0x1F6E9),
    (0x1F6EB, 0x1F6EC),
    (0x1F6F0, 0x1F6F0),
    (0x1F6F3, 0x1F6FC),
    (0x1F7E0, 0x1F7EB),
    (0x1F7F0, 0x1F7F0),
    (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945),
    (0x1F947, 0x1F9FF),
    (0x1FA70, 0x1FA7C),
    (0x1FA80, 0x1FA88),
    (0x1FA90, 0x1FABD),
    (0x1FABF, 0x1FAC5),
    (0x1FACE, 0x1FADB),
    (0x1FAE0, 0x1FAE8),
    (0x1FAF0, 0x1FAF8),
)
_EMOJI = frozenset(code for low, high in _EMOJI_RANGES for code in range(low, high + 1))
_KEYCAP_BASES = frozenset("#*0123456789")
_KEYCAP = "\u20e3"

# Characters that are escaped except where they make part of an emoji: the variation selectors 15
# and 16, which choose between a text and a picture form, and the zero width joiner, which joins
# the parts of one emoji.
_VARIATION_SELECTORS = frozenset({"\ufe0e", "\ufe0f"})
_JOINER = "\u200d"
_CONTEXT_PATTERN = re.compile("[\u200d\ufe0e\ufe0f]")

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


def _is_emoji(ch: str) -> bool:
    return ord(ch) in _EMOJI


def _selector_is_attached(text: str, index: int) -> bool:
    """True if the variation selector 15 or 16 at `index` follows a character it can modify.

    It must come straight after an emoji character, or after a digit, `#` or `*` that a keycap
    follows. A selector that leads the text, follows another selector or a joiner, or follows
    anything else, is not attached.
    """
    if index == 0:
        return False
    base = text[index - 1]
    if _is_emoji(base):
        return True
    return base in _KEYCAP_BASES and text[index + 1 : index + 2] == _KEYCAP


def _joiner_is_attached(text: str, index: int) -> bool:
    """True if the zero width joiner at `index` sits between two emoji characters.

    The character before it may be an emoji followed by an attached selector, as in a heart that
    is joined to a flame. The character after it must be an emoji. A joiner next to a joiner, a
    leading or a trailing joiner, or one beside any other character, is not attached.
    """
    before = index - 1
    if before >= 0 and text[before] in _VARIATION_SELECTORS and _selector_is_attached(text, before):
        before -= 1
    if before < 0 or not _is_emoji(text[before]):
        return False
    after = text[index + 1 : index + 2]
    return bool(after) and _is_emoji(after)


def _kept_in_context(text: str, index: int) -> bool:
    """True if the selector or joiner at `index` is part of an emoji and is printed as itself."""
    if text[index] == _JOINER:
        return _joiner_is_attached(text, index)
    return _selector_is_attached(text, index)


def printable(text: str, *, keep_newlines: bool = False) -> str:
    """Return `text` with everything unsafe for a terminal replaced by a visible escape.

    C0 control characters (including ESC, BEL and newline), DEL, the C1 controls U+0080 to U+009F,
    and invisible, undefined and separator characters become `\\xNN`, `\\uNNNN` or
    `\\UNNNNNNNN`, with `\\n`, `\\r` and `\\t` for those three. The invisible and undefined
    characters are every character in the Unicode categories `Cf` (format), `Cn` (unassigned), `Co`
    (private use), `Zl` and `Zp`; every code point with the Default_Ignorable_Code_Point property
    (the soft hyphen, the combining grapheme joiner, the Hangul fillers, the variation selectors,
    the tag block U+E0000 to U+E0FFF and the rest); and every noncharacter.

    Three of those are kept where they make part of an emoji, so that a heart or a family prints
    as one picture: a variation selector 15 or 16 (U+FE0E, U+FE0F) straight after an emoji
    character, or after a digit, `#` or `*` that a keycap (U+20E3) follows, and a zero width
    joiner (U+200D) between two emoji characters, where the first may carry such a selector. One
    selector may follow a character; a second, a leading one, one after a joiner or after a
    character that is not an emoji, and a joiner that is leading, trailing, repeated or beside a
    character that is not an emoji, are escaped like the rest. Every other variation selector is
    always escaped.

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
    unsafe = {ch: _escape(ord(ch)) for ch in distinct if _needs_escape(ch)}
    if not unsafe:
        return text
    if _JOINER not in unsafe and not _VARIATION_SELECTORS & unsafe.keys():
        return text.translate({ord(ch): escape for ch, escape in unsafe.items()})
    # The selectors and the joiner depend on their neighbours, so they are decided where they
    # stand. The text between them is rewritten in one pass, so the cost follows their number.
    table = {ord(ch): escape for ch, escape in unsafe.items()}
    pieces: list[str] = []
    last = 0
    for match in _CONTEXT_PATTERN.finditer(text):
        start = match.start()
        pieces.append(text[last:start].translate(table))
        pieces.append(match.group() if _kept_in_context(text, start) else unsafe[match.group()])
        last = match.end()
    pieces.append(text[last:].translate(table))
    return "".join(pieces)

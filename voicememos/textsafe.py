"""Make text from untrusted files safe to print on a terminal."""

from __future__ import annotations

# Characters that can change how text is shown without being visible themselves: line and
# paragraph separators, and the bidirectional controls that can reorder what follows.
_FORMAT_CHARS = frozenset(
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
    | {0xFEFF}
)

_MNEMONIC = {0x0A: "\\n", 0x0D: "\\r", 0x09: "\\t"}


def _escape(code: int) -> str:
    if code in _MNEMONIC:
        return _MNEMONIC[code]
    return f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}"


def _needs_escape(code: int) -> bool:
    return code < 0x20 or 0x7F <= code <= 0x9F or code in _FORMAT_CHARS


def printable(text: str, *, keep_newlines: bool = False) -> str:
    """Return `text` with everything unsafe for a terminal replaced by a visible escape.

    C0 control characters (including ESC, BEL and newline), DEL, the C1 controls U+0080 to U+009F,
    and invisible format and separator characters become `\\xNN` or `\\uNNNN`, with `\\n`, `\\r`
    and `\\t` for those three. A lone surrogate, which cannot be encoded as UTF-8, becomes a
    question mark. With `keep_newlines`, line feeds pass through so multi line text keeps its
    shape; every other control character is still escaped. Backslashes are left alone, so the
    output cannot be told apart from text that contains a literal backslash sequence.
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

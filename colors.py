"""ANSI colour helpers shared by the parser and the renderer.

The palette lives here, in a module that depends on nothing else, for
two reasons:

* the parser must be able to reject an unknown ``color=`` metadata,
* the renderer must be able to turn a colour name into an escape code.

Putting the table anywhere else would create a circular import between
those two modules.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

_CODES: Dict[str, str] = {
    "black": "\033[38;5;240m",
    "red": "\033[38;5;196m",
    "green": "\033[38;5;46m",
    "yellow": "\033[38;5;226m",
    "blue": "\033[38;5;33m",
    "magenta": "\033[38;5;201m",
    "cyan": "\033[38;5;51m",
    "white": "\033[38;5;255m",
    "grey": "\033[38;5;245m",
    "gray": "\033[38;5;245m",
    "orange": "\033[38;5;208m",
    "purple": "\033[38;5;135m",
    "pink": "\033[38;5;213m",
    "brown": "\033[38;5;130m",
}

SUPPORTED_COLORS = frozenset(_CODES)


def is_supported(name: str) -> bool:
    """Tell whether a colour name is part of the palette."""
    return name in _CODES


def code(name: Optional[str]) -> str:
    """Return the escape sequence of a colour, or an empty string."""
    if name is None:
        return ""
    return _CODES.get(name, "")


def supports_color() -> bool:
    """Guess whether the output stream can display colours.

    Honours the de-facto standard ``NO_COLOR`` environment variable and
    disables colours when the output is redirected to a file or a pipe,
    so that piping the program into ``diff`` stays readable.
    """
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize(text: str, color: Optional[str], enabled: bool = True) -> str:
    """Wrap ``text`` in the escape codes of ``color``.

    Args:
        text: the text to decorate.
        color: a colour name of the palette, or None.
        enabled: when False the text is returned untouched.

    Returns:
        The decorated text, or the original text when no colour applies.
    """
    escape = code(color)
    if not enabled or not escape:
        return text
    return f"{escape}{text}{RESET}"

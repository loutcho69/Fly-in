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
    "gold": "\033[38;5;220m",
    "lime": "\033[38;5;118m",
    "crimson": "\033[38;5;161m",
    "darkred": "\033[38;5;88m",
    "maroon": "\033[38;5;52m",
    "violet": "\033[38;5;177m",
    "silver": "\033[38;5;250m",
    "navy": "\033[38;5;18m",
    "teal": "\033[38;5;30m",
    "olive": "\033[38;5;100m",
    "rainbow": "\033[38;5;213m",
}

_HEX: Dict[str, str] = {
    "black": "#3a3a3a",
    "red": "#e03131",
    "green": "#2f9e44",
    "yellow": "#f0c000",
    "blue": "#1971c2",
    "magenta": "#d6336c",
    "cyan": "#0ca678",
    "white": "#e9ecef",
    "grey": "#868e96",
    "gray": "#868e96",
    "orange": "#f76707",
    "purple": "#7048e8",
    "pink": "#f06595",
    "brown": "#8d6e3a",
    "gold": "#d4a017",
    "lime": "#66a80f",
    "crimson": "#c2255c",
    "darkred": "#a51111",
    "maroon": "#7b1e1e",
    "violet": "#9c36b5",
    "silver": "#adb5bd",
    "navy": "#1c3c78",
    "teal": "#0b7285",
    "olive": "#6d7d21",
    "rainbow": "#e64980",
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


def hex_code(name: Optional[str]) -> Optional[str]:
    """Return the RGB code of a colour, for the graphical viewer.

    Args:
        name: a colour name, or None.

    Returns:
        A ``#rrggbb`` string, or None when the name is unknown.
    """
    if name is None:
        return None
    return _HEX.get(name)


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

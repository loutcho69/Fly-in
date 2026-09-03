"""Exception hierarchy used across the whole project.

Having a single base class (:class:`FlyInError`) lets ``main.py`` catch
every expected failure in one place and print a clean message instead of
letting a raw traceback reach the user, as required by the subject.
"""

from __future__ import annotations


class FlyInError(Exception):
    """Base class of every error raised by this project."""


class ParseError(FlyInError):
    """Raised when a line of the map file is syntactically invalid.

    The subject requires the error message to indicate both the line and
    the cause, so both are stored on the exception itself.
    """

    def __init__(self, line_number: int, line: str, reason: str) -> None:
        """Build a parse error.

        Args:
            line_number: 1-based index of the offending line.
            line: raw content of the offending line.
            reason: human readable explanation of the problem.
        """
        self._line_number = line_number
        self._line = line
        self._reason = reason
        super().__init__(
            f"line {line_number}: {reason}\n  >>> {line.strip()}"
        )

    @property
    def line_number(self) -> int:
        """1-based index of the offending line."""
        return self._line_number

    @property
    def line(self) -> str:
        """Raw content of the offending line."""
        return self._line

    @property
    def reason(self) -> str:
        """Human readable explanation of the problem."""
        return self._reason


class ValidationError(FlyInError):
    """Raised when the map is well formed but semantically invalid.

    Typical cases: duplicate zone name, duplicate connection, missing
    start or end hub. These checks do not know about line numbers; the
    parser catches them and re-raises a :class:`ParseError` when it can
    attach one.
    """


class SimulationError(FlyInError):
    """Raised when the simulation cannot be run or cannot progress.

    Typical cases: no valid path between the start and the end hub, or a
    deadlock detected at runtime.
    """

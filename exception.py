from ABC import Exception
"""Custom exceptions for the Fly-in project."""


class FlyInError(Exception):
    """Base exception for all Fly-in errors."""
    pass


class ParseError(FlyInError):
    """Raised when the map file cannot be parsed correctly."""

    def __init__(self, message: str, line_number: int) -> None:
        super().__init__(f"line {line_number}: {message}")
        self.line_number = line_number
        self.message = message


class SimulationError(FlyInError):
    """Raised when the simulation encounters an invalid state."""
    pass
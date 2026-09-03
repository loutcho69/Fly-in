"""Reading and validating a ``.map`` file.

The parser is deliberately strict: any deviation from the expected
syntax raises a :class:`~errors.ParseError` carrying the line number and
the reason, as demanded by the subject. It never guesses and never
silently ignores a malformed instruction.

Grammar handled (blank lines and ``#`` comments are skipped):

    nb_drones: <positive integer>
    start_hub: <name> <x> <y> [{key=value, ...}]
    end_hub:   <name> <x> <y> [{key=value, ...}]
    hub:       <name> <x> <y> [{key=value, ...}]
    connection: <name>-<name>  [{key=value, ...}]

Every literal of that grammar is a module level constant, so adapting
the parser to a slightly different spelling means editing one line.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Tuple

import colors
from errors import FlyInError, ParseError, ValidationError
from network import Network
from zone import Zone, ZoneType

COMMENT_PREFIX = "#"
METADATA_OPEN = "{"
METADATA_CLOSE = "}"
KEYWORD_SEPARATOR = ":"
CONNECTION_SEPARATOR = "-"

KEY_NB_DRONES = "nb_drones"
KEY_START_HUB = "start_hub"
KEY_END_HUB = "end_hub"
KEY_HUB = "hub"
KEY_CONNECTION = "connection"

ZONE_KEYWORDS = (KEY_START_HUB, KEY_END_HUB, KEY_HUB)
ZONE_META_KEYS: FrozenSet[str] = frozenset({"zone", "color", "max_drones"})
LINK_META_KEYS: FrozenSet[str] = frozenset(
    {"color", "max_link_capacity"}
)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.]+$")
INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")


class MapParser:
    """Turn a ``.map`` file into a validated :class:`~network.Network`."""

    def __init__(self, path: str) -> None:
        """Store the path of the file to read.

        Args:
            path: path of the ``.map`` file.
        """
        self._path = path

    @property
    def path(self) -> str:
        """Path of the file being parsed."""
        return self._path

    def parse(self) -> Network:
        """Read the file and build the network.

        Returns:
            A fully validated network.

        Raises:
            FlyInError: if the file cannot be read, if a line is
                malformed, or if the map is semantically invalid.
        """
        lines = self._read_lines()
        network = self._build(lines)
        network.validate()
        return network

    def _read_lines(self) -> List[str]:
        """Load the file as a list of raw lines.

        Returns:
            The lines of the file, newline characters removed.

        Raises:
            FlyInError: if the file is missing or unreadable.
        """
        try:
            with open(self._path, "r", encoding="utf-8") as stream:
                return stream.read().splitlines()
        except OSError as error:
            raise FlyInError(
                f"cannot read map file {self._path!r}: {error.strerror}"
            ) from error
        except UnicodeDecodeError as error:
            raise FlyInError(
                f"map file {self._path!r} is not valid UTF-8 text"
            ) from error

    def _build(self, lines: List[str]) -> Network:
        """Walk the file once and fill a network.

        The first meaningful line must be the ``nb_drones`` declaration,
        because the network object cannot be created without it.

        Args:
            lines: raw lines of the file.

        Returns:
            The network described by the file.

        Raises:
            ParseError: on any malformed line.
            ValidationError: if the file holds no instruction at all.
        """
        network: Optional[Network] = None
        for index, raw in enumerate(lines, start=1):
            content = self._strip_comment(raw)
            if not content:
                continue
            if network is None:
                network = self._parse_header(content, index, raw)
            else:
                self._parse_statement(network, content, index, raw)
        if network is None:
            raise ValidationError(
                f"map file {self._path!r} contains no instruction"
            )
        return network

    @staticmethod
    def _strip_comment(raw: str) -> str:
        """Remove the comment part of a line and the surrounding spaces.

        Args:
            raw: a raw line of the file.

        Returns:
            The meaningful part of the line, possibly empty.
        """
        content, _, _ = raw.partition(COMMENT_PREFIX)
        return content.strip()

    def _parse_header(self, content: str, index: int, raw: str) -> Network:
        """Parse the ``nb_drones`` declaration.

        Args:
            content: the line without comment nor surrounding spaces.
            index: 1-based line number, used for error messages.
            raw: the original line, used for error messages.

        Returns:
            A brand new empty network.

        Raises:
            ParseError: if the first instruction is not a valid
                ``nb_drones`` declaration.
        """
        keyword, payload = self._split_keyword(content, index, raw)
        if keyword != KEY_NB_DRONES:
            raise ParseError(
                index, raw,
                f"the first instruction must be {KEY_NB_DRONES!r}, "
                f"got {keyword!r}",
            )
        nb_drones = self._to_positive_int(payload, KEY_NB_DRONES, index, raw)
        return Network(nb_drones)

    def _parse_statement(
        self, network: Network, content: str, index: int, raw: str
    ) -> None:
        """Dispatch one instruction to the right specialised parser.

        Args:
            network: the network being filled.
            content: the line without comment nor surrounding spaces.
            index: 1-based line number.
            raw: the original line.

        Raises:
            ParseError: on an unknown or duplicated keyword.
        """
        keyword, payload = self._split_keyword(content, index, raw)
        if keyword in ZONE_KEYWORDS:
            self._parse_zone(network, keyword, payload, index, raw)
        elif keyword == KEY_CONNECTION:
            self._parse_connection(network, payload, index, raw)
        elif keyword == KEY_NB_DRONES:
            raise ParseError(
                index, raw, f"{KEY_NB_DRONES!r} is declared more than once"
            )
        else:
            expected = ", ".join(
                (*ZONE_KEYWORDS, KEY_CONNECTION)
            )
            raise ParseError(
                index, raw,
                f"unknown instruction {keyword!r} (expected: {expected})",
            )

    def _split_keyword(
        self, content: str, index: int, raw: str
    ) -> Tuple[str, str]:
        """Split an instruction into its keyword and its payload.

        Args:
            content: the meaningful part of the line.
            index: 1-based line number.
            raw: the original line.

        Returns:
            A ``(keyword, payload)`` pair, both already stripped.

        Raises:
            ParseError: if the ``:`` separator or the payload is missing.
        """
        keyword, separator, payload = content.partition(KEYWORD_SEPARATOR)
        if not separator:
            raise ParseError(
                index, raw,
                f"missing {KEYWORD_SEPARATOR!r} separator after the keyword",
            )
        keyword = keyword.strip()
        payload = payload.strip()
        if not keyword:
            raise ParseError(index, raw, "missing keyword")
        if not payload:
            raise ParseError(
                index, raw, f"instruction {keyword!r} has no argument"
            )
        return keyword, payload

    def _parse_zone(
        self,
        network: Network,
        keyword: str,
        payload: str,
        index: int,
        raw: str,
    ) -> None:
        """Parse a ``hub``, ``start_hub`` or ``end_hub`` declaration.

        Args:
            network: the network being filled.
            keyword: the keyword that introduced the line.
            payload: everything written after the ``:``.
            index: 1-based line number.
            raw: the original line.

        Raises:
            ParseError: on a malformed declaration, an invalid name,
                non-integer coordinates or invalid metadata.
        """
        body, meta_raw = self._split_metadata(payload, index, raw)
        fields = body.split()
        if len(fields) != 3:
            raise ParseError(
                index, raw,
                f"{keyword!r} expects '<name> <x> <y>', "
                f"got {len(fields)} field(s)",
            )
        name, x_raw, y_raw = fields
        self._check_name(name, index, raw)
        x = self._to_int(x_raw, "x coordinate", index, raw)
        y = self._to_int(y_raw, "y coordinate", index, raw)
        meta = self._parse_metadata(meta_raw, ZONE_META_KEYS, index, raw)
        zone = Zone(
            name,
            x,
            y,
            zone_type=self._zone_type_from(meta, index, raw),
            color=self._color_from(meta, index, raw),
            max_drones=self._max_drones_from(meta, index, raw),
            is_start=keyword == KEY_START_HUB,
            is_end=keyword == KEY_END_HUB,
        )
        try:
            network.add_zone(zone)
        except ValidationError as error:
            raise ParseError(index, raw, str(error)) from error

    def _parse_connection(
        self, network: Network, payload: str, index: int, raw: str
    ) -> None:
        """Parse a ``connection`` declaration.

        Because zone names may not contain a dash, splitting on ``-``
        can only produce the two endpoints; any other count is a syntax
        error.

        Args:
            network: the network being filled.
            payload: everything written after the ``:``.
            index: 1-based line number.
            raw: the original line.

        Raises:
            ParseError: on a malformed declaration, an unknown zone or a
                duplicated connection.
        """
        body, meta_raw = self._split_metadata(payload, index, raw)
        if body.split() != [body]:
            raise ParseError(
                index, raw,
                "a connection must be written '<name>-<name>' "
                "without spaces",
            )
        endpoints = body.split(CONNECTION_SEPARATOR)
        if len(endpoints) != 2:
            raise ParseError(
                index, raw,
                "a connection must join exactly two zones "
                f"('<name>{CONNECTION_SEPARATOR}<name>')",
            )
        first, second = endpoints
        self._check_name(first, index, raw)
        self._check_name(second, index, raw)
        meta = self._parse_metadata(meta_raw, LINK_META_KEYS, index, raw)
        capacity = self._link_capacity_from(meta, index, raw)
        try:
            network.add_link(first, second, capacity)
        except ValidationError as error:
            raise ParseError(index, raw, str(error)) from error

    def _split_metadata(
        self, payload: str, index: int, raw: str
    ) -> Tuple[str, str]:
        """Separate the mandatory fields from the optional metadata.

        Args:
            payload: everything written after the ``:``.
            index: 1-based line number.
            raw: the original line.

        Returns:
            A ``(body, metadata)`` pair; ``metadata`` is the content of
            the braces, without the braces, and is empty when the line
            carries no metadata.

        Raises:
            ParseError: if the braces are unbalanced or if something
                follows the closing brace.
        """
        opening = payload.find(METADATA_OPEN)
        closing = payload.find(METADATA_CLOSE)
        if opening == -1 and closing == -1:
            return payload.strip(), ""
        if opening == -1:
            raise ParseError(
                index, raw,
                f"unexpected {METADATA_CLOSE!r} without a matching "
                f"{METADATA_OPEN!r}",
            )
        if closing == -1:
            raise ParseError(
                index, raw, f"unterminated metadata block, missing "
                f"{METADATA_CLOSE!r}",
            )
        if closing < opening:
            raise ParseError(index, raw, "metadata braces are inverted")
        trailing = payload[closing + 1:].strip()
        if trailing:
            raise ParseError(
                index, raw,
                f"unexpected text {trailing!r} after the metadata block",
            )
        return payload[:opening].strip(), payload[opening + 1:closing].strip()

    def _parse_metadata(
        self, meta_raw: str, allowed: FrozenSet[str], index: int, raw: str
    ) -> Dict[str, str]:
        """Turn a metadata block into a dictionary.

        Args:
            meta_raw: content of the braces, without the braces.
            allowed: the keys accepted on this kind of line.
            index: 1-based line number.
            raw: the original line.

        Returns:
            The parsed key/value pairs; an empty dict when there is no
            metadata.

        Raises:
            ParseError: on a malformed entry, an unknown key or a key
                repeated twice.
        """
        meta: Dict[str, str] = {}
        if not meta_raw:
            return meta
        for entry in meta_raw.split(","):
            entry = entry.strip()
            if not entry:
                raise ParseError(
                    index, raw, "empty entry in the metadata block"
                )
            key, separator, value = entry.partition("=")
            key = key.strip()
            value = value.strip()
            if not separator or not key or not value:
                raise ParseError(
                    index, raw,
                    f"malformed metadata {entry!r} (expected 'key=value')",
                )
            if key not in allowed:
                expected = ", ".join(sorted(allowed))
                raise ParseError(
                    index, raw,
                    f"unknown metadata key {key!r} "
                    f"(allowed here: {expected})",
                )
            if key in meta:
                raise ParseError(
                    index, raw, f"metadata key {key!r} is given twice"
                )
            meta[key] = value
        return meta

    @staticmethod
    def _check_name(name: str, index: int, raw: str) -> None:
        """Validate a zone name.

        Names may not be empty and may only hold letters, digits,
        underscores and dots: this forbids the spaces and the dashes
        that would make the grammar ambiguous.

        Args:
            name: the candidate name.
            index: 1-based line number.
            raw: the original line.

        Raises:
            ParseError: if the name breaks one of those rules.
        """
        if not name:
            raise ParseError(index, raw, "empty zone name")
        if not NAME_PATTERN.match(name):
            raise ParseError(
                index, raw,
                f"invalid zone name {name!r}: only letters, digits, "
                "'_' and '.' are allowed (no space, no dash)",
            )

    @staticmethod
    def _to_int(value: str, field: str, index: int, raw: str) -> int:
        """Convert a field to an integer.

        Args:
            value: the raw text of the field.
            field: name of the field, used in the error message.
            index: 1-based line number.
            raw: the original line.

        Returns:
            The parsed integer.

        Raises:
            ParseError: if the text is not a valid integer.
        """
        if not INTEGER_PATTERN.match(value):
            raise ParseError(
                index, raw, f"{field} must be an integer, got {value!r}"
            )
        return int(value)

    def _to_positive_int(
        self, value: str, field: str, index: int, raw: str
    ) -> int:
        """Convert a field to a strictly positive integer.

        Args:
            value: the raw text of the field.
            field: name of the field, used in the error message.
            index: 1-based line number.
            raw: the original line.

        Returns:
            The parsed integer, guaranteed to be >= 1.

        Raises:
            ParseError: if the text is not a strictly positive integer.
        """
        number = self._to_int(value, field, index, raw)
        if number < 1:
            raise ParseError(
                index, raw,
                f"{field} must be strictly positive, got {number}",
            )
        return number

    @staticmethod
    def _zone_type_from(
        meta: Dict[str, str], index: int, raw: str
    ) -> ZoneType:
        """Read the ``zone`` metadata, defaulting to ``normal``.

        Raises:
            ParseError: if the value is not a known zone type.
        """
        value = meta.get("zone")
        if value is None:
            return ZoneType.NORMAL
        try:
            return ZoneType.parse(value)
        except ValueError as error:
            raise ParseError(index, raw, str(error)) from error

    @staticmethod
    def _color_from(
        meta: Dict[str, str], index: int, raw: str
    ) -> Optional[str]:
        """Read the ``color`` metadata, defaulting to None.

        Raises:
            ParseError: if the colour is not part of the palette.
        """
        value = meta.get("color")
        if value is None:
            return None
        if not colors.is_supported(value):
            available = ", ".join(sorted(colors.SUPPORTED_COLORS))
            raise ParseError(
                index, raw,
                f"unknown color {value!r} (available: {available})",
            )
        return value

    def _max_drones_from(
        self, meta: Dict[str, str], index: int, raw: str
    ) -> int:
        """Read the ``max_drones`` metadata, defaulting to 1."""
        value = meta.get("max_drones")
        if value is None:
            return 1
        return self._to_positive_int(value, "max_drones", index, raw)

    def _link_capacity_from(
        self, meta: Dict[str, str], index: int, raw: str
    ) -> int:
        """Read the ``max_link_capacity`` metadata, defaulting to 1."""
        value = meta.get("max_link_capacity")
        if value is None:
            return 1
        return self._to_positive_int(
            value, "max_link_capacity", index, raw
        )


def parse_map(path: str) -> Network:
    """Convenience wrapper around :class:`MapParser`.

    Args:
        path: path of the ``.map`` file.

    Returns:
        The validated network described by the file.
    """
    return MapParser(path).parse()

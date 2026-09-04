"""Zones: the nodes of the network graph.

A :class:`Zone` is a *static* description of a place: name, coordinates,
type, colour and capacity. It deliberately does **not** know how many
drones are currently standing inside it: that runtime state belongs to
the simulation engine. Keeping the graph immutable makes it safe to
share between the pathfinder and the simulator.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ZoneType(Enum):
    """The four zone types allowed by the subject."""

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @classmethod
    def parse(cls, raw: str) -> "ZoneType":
        """Convert the raw value of a ``zone=`` tag into a ZoneType.

        Args:
            raw: value found after ``zone=`` in a metadata block.

        Returns:
            The matching member of the enumeration.

        Raises:
            ValueError: if the value is not one of the four valid types.
        """
        for member in cls:
            if member.value == raw:
                return member
        allowed = ", ".join(member.value for member in cls)
        raise ValueError(
            f"invalid zone type {raw!r} (expected one of: {allowed})"
        )

    @property
    def entry_cost(self) -> int:
        """Number of turns needed to *enter* a zone of this type.

        ``restricted`` costs 2 turns, every other reachable type costs 1.
        """
        return 2 if self is ZoneType.RESTRICTED else 1

    @property
    def is_accessible(self) -> bool:
        """Whether a drone may enter or cross a zone of this type."""
        return self is not ZoneType.BLOCKED

    @property
    def preference(self) -> int:
        """Tie-break weight used by the pathfinder: lower is better.

        The subject says a ``priority`` zone costs 1 turn but "should be
        prioritized". The cost stays 1 so the turn count remains exact;
        the preference is only used to break ties between two paths of
        identical duration.
        """
        return 0 if self is ZoneType.PRIORITY else 1


class Zone:
    """One node of the network.

    Instances are treated as immutable: every attribute is exposed
    through a read-only property. Equality and hashing are based on the
    zone name, which the parser guarantees to be unique.
    """

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        *,
        zone_type: ZoneType = ZoneType.NORMAL,
        color: Optional[str] = None,
        max_drones: int = 1,
        is_start: bool = False,
        is_end: bool = False,
    ) -> None:
        """Build a zone.

        Args:
            name: unique identifier of the zone.
            x: integer abscissa, used by the renderer only.
            y: integer ordinate, used by the renderer only.
            zone_type: type of the zone (default ``normal``).
            color: optional colour name used for the display.
            max_drones: simultaneous occupancy limit (default 1).
            is_start: True for the ``start_hub`` zone.
            is_end: True for the ``end_hub`` zone.
        """
        self._name = name
        self._x = x
        self._y = y
        self._zone_type = zone_type
        self._color = color
        self._max_drones = max_drones
        self._is_start = is_start
        self._is_end = is_end

    @property
    def name(self) -> str:
        """Unique name of the zone."""
        return self._name

    @property
    def x(self) -> int:
        """Integer abscissa of the zone."""
        return self._x

    @property
    def y(self) -> int:
        """Integer ordinate of the zone."""
        return self._y

    @property
    def zone_type(self) -> ZoneType:
        """Type of the zone."""
        return self._zone_type

    @property
    def color(self) -> Optional[str]:
        """Colour requested in the map file, if any."""
        return self._color

    @property
    def is_start(self) -> bool:
        """True if this zone is the start hub."""
        return self._is_start

    @property
    def is_end(self) -> bool:
        """True if this zone is the end hub."""
        return self._is_end

    @property
    def is_terminal(self) -> bool:
        """True for the start and end hubs (the unlimited zones)."""
        return self._is_start or self._is_end

    @property
    def capacity(self) -> Optional[int]:
        """Maximum simultaneous occupancy, ``None`` meaning unlimited.

        The subject states that ``max_drones`` is ignored on the start
        and end hubs, hence the special case here rather than in the
        parser: the metadata is still parsed and validated, it simply
        has no effect.
        """
        return None if self.is_terminal else self._max_drones

    @property
    def entry_cost(self) -> int:
        """Number of turns needed to enter this zone."""
        return self._zone_type.entry_cost

    @property
    def is_accessible(self) -> bool:
        """False for ``blocked`` zones, which no path may use."""
        return self._zone_type.is_accessible

    @property
    def preference(self) -> int:
        """Tie-break weight of the zone (0 for ``priority``)."""
        return self._zone_type.preference

    def has_room_for(self, occupancy: int, incoming: int = 1) -> bool:
        """Tell whether ``incoming`` drones may enter this zone.

        Args:
            occupancy: number of drones already inside the zone *after*
                the ones that leave during this turn have been removed.
            incoming: number of drones that want to enter.

        Returns:
            True if the move is allowed by the capacity rules.
        """
        if not self.is_accessible:
            return False
        capacity = self.capacity
        if capacity is None:
            return True
        return occupancy + incoming <= capacity

    def __eq__(self, other: object) -> bool:
        """Two zones are equal when they share the same name.

        Args:
            other: the object to compare with.

        Returns:
            True when both are zones with the same name.
        """
        if not isinstance(other, Zone):
            return NotImplemented
        return self._name == other.name

    def __hash__(self) -> int:
        """Hash on the name so zones can be used in sets and dicts."""
        return hash(self._name)

    def __repr__(self) -> str:
        """Developer friendly representation, handy in pdb."""
        return (
            f"Zone({self._name!r}, {self._x}, {self._y}, "
            f"type={self._zone_type.value}, capacity={self.capacity})"
        )

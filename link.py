"""Links: the bidirectional connections (edges) of the network.

A link owns its own capacity (``max_link_capacity``) and, exactly like
:class:`~zone.Zone`, stays free of any runtime state. The simulator
counts how many drones use a link during a given turn, the link only
knows the limit.
"""

from __future__ import annotations

from typing import Tuple

from zone import Zone


class Link:
    """A bidirectional connection between two distinct zones."""

    def __init__(self, first: Zone, second: Zone, capacity: int = 1) -> None:
        """Build a link.

        Args:
            first: zone written on the left of the dash in the map file.
            second: zone written on the right of the dash.
            capacity: value of ``max_link_capacity`` (default 1).
        """
        self._first = first
        self._second = second
        self._capacity = capacity
        low, high = sorted((first.name, second.name))
        self._key: Tuple[str, str] = (low, high)

    @property
    def first(self) -> Zone:
        """Left-hand endpoint, as declared in the map file."""
        return self._first

    @property
    def second(self) -> Zone:
        """Right-hand endpoint, as declared in the map file."""
        return self._second

    @property
    def key(self) -> Tuple[str, str]:
        """Canonical identifier of the link.

        The two names are sorted so that ``a-b`` and ``b-a`` produce the
        same key: this is what makes duplicate detection trivial, as
        required by the parser constraints.
        """
        return self._key

    @property
    def name(self) -> str:
        """Display name of the link, e.g. ``corridorA-tunnelB``.

        Used by the output format when a drone is still in flight on a
        connection leading to a ``restricted`` zone (``D1-a-b``).
        """
        return f"{self._first.name}-{self._second.name}"

    @property
    def capacity(self) -> int:
        """Maximum number of drones traversing the link in one turn."""
        return self._capacity

    @property
    def is_usable(self) -> bool:
        """False as soon as one endpoint is a ``blocked`` zone."""
        return self._first.is_accessible and self._second.is_accessible

    def other_end(self, zone: Zone) -> Zone:
        """Return the endpoint opposite to ``zone``.

        Args:
            zone: one of the two endpoints of the link.

        Returns:
            The other endpoint.

        Raises:
            KeyError: if ``zone`` is not an endpoint of this link.
        """
        if zone == self._first:
            return self._second
        if zone == self._second:
            return self._first
        raise KeyError(
            f"zone {zone.name!r} is not an endpoint of link {self.name!r}"
        )

    def has_room_for(self, usage: int, incoming: int = 1) -> bool:
        """Tell whether ``incoming`` more drones may use the link.

        Args:
            usage: number of drones already using the link this turn.
            incoming: number of drones that want to use it.

        Returns:
            True if the link capacity is not exceeded.
        """
        if not self.is_usable:
            return False
        return usage + incoming <= self._capacity

    def __eq__(self, other: object) -> bool:
        """Two links are equal when they join the same pair of zones."""
        if not isinstance(other, Link):
            return NotImplemented
        return self._key == other.key

    def __hash__(self) -> int:
        """Hash on the canonical key."""
        return hash(self._key)

    def __repr__(self) -> str:
        """Developer friendly representation, handy in pdb."""
        return f"Link({self.name!r}, capacity={self._capacity})"

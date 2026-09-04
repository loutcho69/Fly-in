"""A path: an ordered sequence of zones linked by connections.

A :class:`Path` is produced by the pathfinder and consumed by the
router, the simulator and the renderer. Like the graph it describes, it
is immutable: it holds no drone and no runtime state.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from errors import ValidationError
from link import Link
from zone import Zone


class Path:
    """An ordered route from the start hub to the end hub."""

    def __init__(self, zones: Sequence[Zone], links: Sequence[Link]) -> None:
        """Build a path.

        Args:
            zones: the zones to cross, in order, hubs included.
            links: the connections joining them, in the same order.

        Raises:
            ValidationError: if the two sequences are inconsistent, i.e.
                if ``links`` does not hold exactly one link fewer than
                ``zones``, or if a link does not join its two zones.
        """
        if len(zones) < 2:
            raise ValidationError("a path needs at least two zones")
        if len(links) != len(zones) - 1:
            raise ValidationError(
                f"inconsistent path: {len(zones)} zones "
                f"but {len(links)} links"
            )
        for step, link in enumerate(links):
            pair = {zones[step].name, zones[step + 1].name}
            if set(link.key) != pair:
                raise ValidationError(
                    f"link {link.name!r} does not join "
                    f"{zones[step].name!r} and {zones[step + 1].name!r}"
                )
        self._zones: Tuple[Zone, ...] = tuple(zones)
        self._links: Tuple[Link, ...] = tuple(links)

    @property
    def zones(self) -> Tuple[Zone, ...]:
        """Every zone of the path, hubs included."""
        return self._zones

    @property
    def links(self) -> Tuple[Link, ...]:
        """Every connection of the path, in traversal order."""
        return self._links

    @property
    def start(self) -> Zone:
        """First zone of the path."""
        return self._zones[0]

    @property
    def end(self) -> Zone:
        """Last zone of the path."""
        return self._zones[-1]

    @property
    def intermediates(self) -> Tuple[Zone, ...]:
        """Zones between the two hubs.

        These are the only zones subject to a capacity limit, which is
        why they get their own accessor: the router and the simulator
        use it constantly.
        """
        return self._zones[1:-1]

    @property
    def moves(self) -> int:
        """Number of connections to cross."""
        return len(self._links)

    @property
    def travel_time(self) -> int:
        """Number of turns one lone drone needs to reach the end hub.

        Entering a zone costs :attr:`~zone.Zone.entry_cost` turns, which
        is 2 for a ``restricted`` zone and 1 otherwise, so the duration
        is the sum of the costs of every zone except the start hub.
        """
        return sum(zone.entry_cost for zone in self._zones[1:])

    @property
    def preference(self) -> int:
        """Tie-break weight of the path: lower means more priority zones."""
        return sum(zone.preference for zone in self._zones[1:])

    def step_cost(self, step: int) -> int:
        """Cost in turns of the move number ``step``.

        Args:
            step: index of the move, 0 being the departure from the
                start hub.

        Returns:
            The number of turns needed to reach the next zone.
        """
        return self._zones[step + 1].entry_cost

    def zone_names(self) -> Tuple[str, ...]:
        """Names of the zones, in order.

        Returns:
            The names of the zones, in order.
        """
        return tuple(zone.name for zone in self._zones)

    def shares_zone_with(self, other: "Path") -> bool:
        """Tell whether two paths cross a common intermediate zone.

        Args:
            other: the path to compare with.

        Returns:
            True when both cross a common intermediate zone.
        """
        mine = {zone.name for zone in self.intermediates}
        theirs = {zone.name for zone in other.intermediates}
        return not mine.isdisjoint(theirs)

    def __len__(self) -> int:
        """Number of zones in the path."""
        return len(self._zones)

    def __eq__(self, other: object) -> bool:
        """Two paths are equal when they cross the same zones in order.

        Args:
            other: the object to compare with.

        Returns:
            True when both cross the same zones in the same order.
        """
        if not isinstance(other, Path):
            return NotImplemented
        return self.zone_names() == other.zone_names()

    def __hash__(self) -> int:
        """Hash on the ordered tuple of zone names."""
        return hash(self.zone_names())

    def __str__(self) -> str:
        """Readable representation such as ``base -> alpha -> hangar``."""
        return " -> ".join(self.zone_names())

    def __repr__(self) -> str:
        """Developer friendly representation, handy in pdb."""
        return f"Path({str(self)!r}, travel_time={self.travel_time})"

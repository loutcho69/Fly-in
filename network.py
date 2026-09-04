"""The network: zones, links, adjacency and global validation.

This class is the only place where the graph is stored. No third-party
graph library is used (and none is allowed): the adjacency structure is
a plain dictionary mapping a zone name to the list of links that touch
it, which gives O(1) access to the neighbours of a zone.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple

from errors import ValidationError
from link import Link
from zone import Zone


class Network:
    """Graph of zones plus the number of drones to route through it."""

    def __init__(self, nb_drones: int) -> None:
        """Build an empty network.

        Args:
            nb_drones: number of drones declared by the map file.

        Raises:
            ValidationError: if ``nb_drones`` is not strictly positive.
        """
        if nb_drones <= 0:
            raise ValidationError(
                f"nb_drones must be a positive integer, got {nb_drones}"
            )
        self._nb_drones = nb_drones
        self._zones: Dict[str, Zone] = {}
        self._links: Dict[Tuple[str, str], Link] = {}
        self._adjacency: Dict[str, List[Link]] = {}
        self._start: Optional[Zone] = None
        self._end: Optional[Zone] = None

    @property
    def nb_drones(self) -> int:
        """Number of drones to move from the start to the end hub."""
        return self._nb_drones

    @property
    def zones(self) -> Tuple[Zone, ...]:
        """All the zones, in declaration order."""
        return tuple(self._zones.values())

    @property
    def links(self) -> Tuple[Link, ...]:
        """All the connections, in declaration order."""
        return tuple(self._links.values())

    @property
    def start(self) -> Zone:
        """The unique start hub.

        Raises:
            ValidationError: if no start hub has been declared.
        """
        if self._start is None:
            raise ValidationError("no start_hub zone defined")
        return self._start

    @property
    def end(self) -> Zone:
        """The unique end hub.

        Raises:
            ValidationError: if no end hub has been declared.
        """
        if self._end is None:
            raise ValidationError("no end_hub zone defined")
        return self._end

    def add_zone(self, zone: Zone) -> None:
        """Register a new zone.

        Args:
            zone: the zone to add.

        Raises:
            ValidationError: on duplicate names, or on a second start or
                end hub.
        """
        if zone.name in self._zones:
            raise ValidationError(f"duplicate zone name {zone.name!r}")
        if zone.is_start and self._start is not None:
            raise ValidationError(
                "several start_hub zones defined "
                f"({self._start.name!r} and {zone.name!r})"
            )
        if zone.is_end and self._end is not None:
            raise ValidationError(
                "several end_hub zones defined "
                f"({self._end.name!r} and {zone.name!r})"
            )
        self._zones[zone.name] = zone
        self._adjacency[zone.name] = []
        if zone.is_start:
            self._start = zone
        if zone.is_end:
            self._end = zone

    def add_link(self, first: str, second: str, capacity: int = 1) -> Link:
        """Register a new bidirectional connection.

        Args:
            first: name of the first zone, already declared.
            second: name of the second zone, already declared.
            capacity: value of ``max_link_capacity``.

        Returns:
            The link that has just been created.

        Raises:
            ValidationError: if a zone is unknown, if the link is a self
                loop, or if the same connection is declared twice.
        """
        if first == second:
            raise ValidationError(
                f"connection {first}-{second} links a zone to itself"
            )
        for name in (first, second):
            if name not in self._zones:
                raise ValidationError(
                    f"connection {first}-{second} uses the undefined "
                    f"zone {name!r}"
                )
        link = Link(self._zones[first], self._zones[second], capacity)
        if link.key in self._links:
            raise ValidationError(
                f"connection {first}-{second} is declared twice"
            )
        self._links[link.key] = link
        self._adjacency[first].append(link)
        self._adjacency[second].append(link)
        return link

    def has_zone(self, name: str) -> bool:
        """Tell whether a zone with this name exists.

        Args:
            name: the name to look for.

        Returns:
            True when the zone exists.
        """
        return name in self._zones

    def zone(self, name: str) -> Zone:
        """Return the zone called ``name``.

        Raises:
            ValidationError: if no such zone exists.

        Args:
            name: name of the zone.

        Returns:
            The matching zone.
        """
        try:
            return self._zones[name]
        except KeyError:
            raise ValidationError(f"unknown zone {name!r}") from None

    def link_between(self, first: str, second: str) -> Optional[Link]:
        """Return the link joining two zones, or None if there is none.

        Args:
            first: name of one endpoint.
            second: name of the other endpoint.

        Returns:
            The link, or None when the two are not connected.
        """
        low, high = sorted((first, second))
        return self._links.get((low, high))

    def neighbours(self, name: str) -> Iterator[Tuple[Link, Zone]]:
        """Iterate over the neighbours of a zone.

        Args:
            name: name of the zone whose neighbours are wanted.

        Yields:
            Pairs ``(link, neighbour_zone)``.
        """
        source = self.zone(name)
        for link in self._adjacency[name]:
            yield link, link.other_end(source)

    def validate(self) -> None:
        """Run the global checks that need the whole map to be loaded.

        Raises:
            ValidationError: if the start or the end hub is missing, if
                they are the same zone, or if one of them is blocked.
        """
        start = self.start
        end = self.end
        if start.name == end.name:
            raise ValidationError(
                "the start and end hubs must be two different zones"
            )
        for zone in (start, end):
            if not zone.is_accessible:
                raise ValidationError(
                    f"the hub {zone.name!r} cannot be of type blocked"
                )

    def __len__(self) -> int:
        """Number of zones in the network."""
        return len(self._zones)

    def __repr__(self) -> str:
        """Developer friendly summary, handy in pdb."""
        return (
            f"Network(zones={len(self._zones)}, "
            f"links={len(self._links)}, drones={self._nb_drones})"
        )

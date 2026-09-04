"""Shortest path search on the network.

The cost of a path is the number of *turns* it takes, not the number of
connections: entering a ``restricted`` zone costs 2 turns, entering any
other reachable zone costs 1. Because the weights differ from one zone
to another, a plain breadth-first search would return wrong answers;
Dijkstra's algorithm is used instead.

The distance is a pair ``(turns, preference)`` compared
lexicographically. The first component is the real duration, the second
counts the zones that are *not* ``priority``. Two routes of equal
duration are therefore ranked by the number of priority zones they use,
which implements the "priority zones should be prioritized" rule
without ever falsifying the turn count.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from errors import SimulationError
from link import Link
from network import Network
from path import Path
from zone import Zone

Distance = Tuple[int, int]

NO_ZONE: FrozenSet[str] = frozenset()
NO_LINK: FrozenSet[Tuple[str, str]] = frozenset()


class PathFinder:
    """Search engine for routes between the two hubs of a network."""

    def __init__(self, network: Network) -> None:
        """Bind the finder to a network.

        Args:
            network: the network to explore. It is never modified.
        """
        self._network = network

    @property
    def network(self) -> Network:
        """The network being explored."""
        return self._network

    def shortest_path(
        self,
        forbidden_zones: FrozenSet[str] = NO_ZONE,
        forbidden_links: FrozenSet[Tuple[str, str]] = NO_LINK,
    ) -> Optional[Path]:
        """Return the fastest route between the hubs, if any.

        Args:
            forbidden_zones: names of the zones that must not be used,
                typically because they are already full.
            forbidden_links: canonical keys of the connections that must
                not be used, typically because they are saturated.

        Returns:
            The fastest path, or None when the end hub cannot be
            reached under those restrictions.
        """
        previous = self._dijkstra(forbidden_zones, forbidden_links)
        if self._network.end.name not in previous:
            return None
        return self._rebuild(previous)

    def require_shortest_path(
        self,
        forbidden_zones: FrozenSet[str] = NO_ZONE,
        forbidden_links: FrozenSet[Tuple[str, str]] = NO_LINK,
    ) -> Path:
        """Same as :meth:`shortest_path` but never returns None.

        Returns:
            The fastest path.

        Raises:
            SimulationError: when no route exists at all.

        Args:
            forbidden_zones: zones that must not be used.
            forbidden_links: connections that must not be used.

        Returns:
            The fastest path.
        """
        path = self.shortest_path(forbidden_zones, forbidden_links)
        if path is None:
            raise SimulationError(
                f"no route from {self._network.start.name!r} to "
                f"{self._network.end.name!r}: the map has no solution "
                "(check for blocked zones or missing connections)"
            )
        return path

    def _dijkstra(
        self,
        forbidden_zones: FrozenSet[str],
        forbidden_links: FrozenSet[Tuple[str, str]],
    ) -> Dict[str, Link]:
        """Run Dijkstra's algorithm from the start hub.

        The priority queue holds ``(turns, preference, tick, zone)``.
        The ``tick`` field is a strictly increasing counter: it makes
        the ordering total, so the heap never has to compare two zone
        names and the result is reproducible from one run to the next.

        Args:
            forbidden_zones: zones that must not be traversed.
            forbidden_links: connections that must not be used.

        Returns:
            A dictionary mapping a zone name to the link used to reach
            it. It contains the end hub only when a route exists.
        """
        start = self._network.start
        end = self._network.end
        distances: Dict[str, Distance] = {start.name: (0, 0)}
        previous: Dict[str, Link] = {}
        settled: Set[str] = set()
        tick = itertools.count()
        queue: List[Tuple[int, int, int, str]] = [
            (0, 0, next(tick), start.name)
        ]
        while queue:
            turns, preference, _, name = heapq.heappop(queue)
            if name in settled:
                continue
            settled.add(name)
            if name == end.name:
                break
            for link, neighbour in self._network.neighbours(name):
                if neighbour.name in settled:
                    continue
                if not self._is_open(
                    link, neighbour, forbidden_zones, forbidden_links
                ):
                    continue
                candidate: Distance = (
                    turns + neighbour.entry_cost,
                    preference + neighbour.preference,
                )
                known = distances.get(neighbour.name)
                if known is not None and known <= candidate:
                    continue
                distances[neighbour.name] = candidate
                previous[neighbour.name] = link
                heapq.heappush(
                    queue,
                    (candidate[0], candidate[1], next(tick), neighbour.name),
                )
        return previous

    @staticmethod
    def _is_open(
        link: Link,
        neighbour: Zone,
        forbidden_zones: FrozenSet[str],
        forbidden_links: FrozenSet[Tuple[str, str]],
    ) -> bool:
        """Tell whether a move may be considered by the search.

        Args:
            link: the connection about to be crossed.
            neighbour: the zone about to be entered.
            forbidden_zones: zones excluded by the caller.
            forbidden_links: connections excluded by the caller.

        Returns:
            True when the move breaks no rule and no restriction.
        """
        if not link.is_usable or link.key in forbidden_links:
            return False
        if not neighbour.is_accessible:
            return False
        return neighbour.name not in forbidden_zones

    def _rebuild(self, previous: Dict[str, Link]) -> Path:
        """Walk the ``previous`` chain backwards to build the path.

        Args:
            previous: output of :meth:`_dijkstra`, which must contain
                the end hub.

        Returns:
            The reconstructed path, ordered from the start hub.
        """
        start = self._network.start
        current = self._network.end
        zones: List[Zone] = [current]
        links: List[Link] = []
        while current.name != start.name:
            link = previous[current.name]
            links.append(link)
            current = link.other_end(current)
            zones.append(current)
        zones.reverse()
        links.reverse()
        return Path(zones, links)

    def reachable_zones(self) -> FrozenSet[str]:
        """Names of the zones a drone can actually reach from the start.

        Blocked zones and the zones lying behind them are excluded. Used
        by the renderer to report the dead parts of a map.

        Returns:
            The names of the zones a drone can reach.
        """
        start = self._network.start
        seen: Set[str] = {start.name}
        queue: List[str] = [start.name]
        while queue:
            name = queue.pop()
            for link, neighbour in self._network.neighbours(name):
                if neighbour.name in seen or not link.is_usable:
                    continue
                seen.add(neighbour.name)
                queue.append(neighbour.name)
        return frozenset(seen)

    def unusable_zones(self) -> Tuple[str, ...]:
        """Zones that no drone will ever be able to use.

        A zone is unusable when it is blocked, when it cannot be reached
        from the start hub, or when the end hub cannot be reached from
        it. The last case is detected by searching backwards, which the
        graph allows since every connection is bidirectional.

        Returns:
            The names of the zones no drone can ever use.
        """
        forward = self.reachable_zones()
        backward = self._reachable_from_end()
        return tuple(
            zone.name
            for zone in self._network.zones
            if zone.name not in forward or zone.name not in backward
        )

    def _reachable_from_end(self) -> FrozenSet[str]:
        """Names of the zones from which the end hub can be reached.

        Returns:
            The names of the zones the end hub is reachable from.
        """
        end = self._network.end
        seen: Set[str] = {end.name}
        queue: List[str] = [end.name]
        while queue:
            name = queue.pop()
            for link, neighbour in self._network.neighbours(name):
                if neighbour.name in seen or not link.is_usable:
                    continue
                seen.add(neighbour.name)
                queue.append(neighbour.name)
        return frozenset(seen)

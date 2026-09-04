"""Finding several simultaneous routes: a minimum cost flow problem.

Sending every drone through the single fastest route is wrong as soon
as that route is narrow: a corridor whose ``max_drones`` is 1 lets one
drone through per turn, so twenty drones would queue for twenty turns
while a slightly longer parallel corridor stays empty.

What we really need is a *set* of routes that can be used at the same
time, which is exactly a flow problem:

* a zone that accepts ``max_drones`` drones at once can serve that many
  routes simultaneously,
* a connection whose ``max_link_capacity`` is ``c`` can serve ``c``
  routes,
* the cost of a route is its duration in turns.

The classical modelling trick is **node splitting**: a capacity that sits
on a *node* cannot be expressed by an edge capacity, so every zone ``v``
becomes two nodes ``v_in`` and ``v_out`` joined by a single arc carrying
the capacity of the zone and the cost of entering it. Every constraint
of the subject then lives on an arc, and a standard minimum cost flow
algorithm applies.

Why not simply run Dijkstra again while forbidding the zones of the
previous route? Because that greedy approach can get stuck. On this map

    s-A, A-B, B-e, s-C, C-B, A-D, D-e

the fastest route is ``s A B e``; removing ``A`` and ``B`` leaves ``C``
with no exit, so the greedy method finds a single route. Yet two
disjoint routes exist, ``s A D e`` and ``s C B e``. Reaching them means
*undoing* the use of the connection ``A-B``, which is precisely what the
residual (backward) arcs of a flow algorithm allow.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from errors import SimulationError
from link import Link
from network import Network
from path import Path
from zone import Zone

INFINITE_CAPACITY = 10 ** 9
UNREACHABLE = 10 ** 15


class _Arc:
    """One directed arc of the residual graph."""

    def __init__(self, target: int, capacity: int, cost: int) -> None:
        """Build an arc.

        Args:
            target: index of the node the arc points to.
            capacity: remaining capacity of the arc.
            cost: cost, in turns, of pushing one unit through the arc.
        """
        self.target = target
        self.capacity = capacity
        self.cost = cost


class MinCostFlow:
    """Minimum cost flow solver, one unit of flow at a time.

    Arcs are stored in a flat list, a forward arc at an even index and
    its backward twin right after it. Index ``i ^ 1`` therefore gives
    the twin of arc ``i``, and the flow currently carried by a forward
    arc is simply the capacity accumulated by its backward twin.
    """

    def __init__(self, size: int) -> None:
        """Create an empty graph.

        Args:
            size: number of nodes.
        """
        self._arcs: List[_Arc] = []
        self._adjacency: List[List[int]] = [[] for _ in range(size)]

    @property
    def size(self) -> int:
        """Number of nodes of the graph."""
        return len(self._adjacency)

    def add_arc(self, source: int, target: int, capacity: int,
                cost: int) -> int:
        """Add a forward arc and its backward twin.

        Args:
            source: index of the origin node.
            target: index of the destination node.
            capacity: maximum number of units the arc can carry.
            cost: cost in turns of one unit.

        Returns:
            The index of the forward arc.
        """
        index = len(self._arcs)
        self._adjacency[source].append(index)
        self._arcs.append(_Arc(target, capacity, cost))
        self._adjacency[target].append(index + 1)
        self._arcs.append(_Arc(source, 0, -cost))
        return index

    def flow_on(self, arc: int) -> int:
        """Number of units currently carried by a forward arc.

        Args:
            arc: index of a forward arc.

        Returns:
            The number of units it carries.
        """
        return self._arcs[arc ^ 1].capacity

    def outgoing(self, node: int) -> List[int]:
        """Indices of the arcs leaving a node.

        Args:
            node: index of a node.

        Returns:
            The indices of the arcs leaving it.
        """
        return self._adjacency[node]

    def target_of(self, arc: int) -> int:
        """Index of the node an arc points to.

        Args:
            arc: index of an arc.

        Returns:
            The index of the node it points to.
        """
        return self._arcs[arc].target

    def augment(self, source: int, sink: int) -> bool:
        """Push one more unit of flow along a cheapest path.

        Backward arcs carry negative costs, so Dijkstra cannot be used
        here: the shortest path is computed with the Bellman-Ford
        variant known as SPFA, which tolerates negative weights.

        Args:
            source: index of the source node.
            sink: index of the sink node.

        Returns:
            True if one unit could be pushed, False if the sink has
            become unreachable, meaning the maximum flow is reached.
        """
        incoming = self._spfa(source, sink)
        if incoming is None:
            return False
        node = sink
        while node != source:
            arc = incoming[node]
            self._arcs[arc].capacity -= 1
            self._arcs[arc ^ 1].capacity += 1
            node = self._arcs[arc ^ 1].target
        return True

    def _spfa(self, source: int, sink: int) -> Optional[List[int]]:
        """Find a cheapest augmenting path from ``source`` to ``sink``.

        Args:
            source: index of the source node.
            sink: index of the sink node.

        Returns:
            For every node, the index of the arc used to reach it, or
            None when the sink cannot be reached any more.
        """
        distances = [UNREACHABLE] * self.size
        incoming = [-1] * self.size
        queued = [False] * self.size
        distances[source] = 0
        pending: Deque[int] = deque([source])
        queued[source] = True
        while pending:
            node = pending.popleft()
            queued[node] = False
            for arc in self._adjacency[node]:
                candidate = self._arcs[arc]
                if candidate.capacity <= 0:
                    continue
                distance = distances[node] + candidate.cost
                if distance >= distances[candidate.target]:
                    continue
                distances[candidate.target] = distance
                incoming[candidate.target] = arc
                if not queued[candidate.target]:
                    queued[candidate.target] = True
                    pending.append(candidate.target)
        if distances[sink] >= UNREACHABLE:
            return None
        return incoming


class RouteSolver:
    """Build sets of simultaneously usable routes for a network."""

    def __init__(self, network: Network) -> None:
        """Model the network as a flow graph.

        Args:
            network: the network to solve. It is never modified.
        """
        self._network = network
        self._zones: Tuple[Zone, ...] = network.zones
        self._index: Dict[str, int] = {
            zone.name: position for position, zone in enumerate(self._zones)
        }
        self._flow = MinCostFlow(2 * len(self._zones))
        self._split_arc: Dict[int, int] = {}
        self._link_of_arc: Dict[int, Link] = {}
        self._crossing_arcs: List[int] = []
        self._build()

    @staticmethod
    def _entry(position: int) -> int:
        """Index of the ``in`` node of the zone at ``position``.

        Args:
            position: index of the zone.

        Returns:
            The index of its ``in`` node.
        """
        return 2 * position

    @staticmethod
    def _exit(position: int) -> int:
        """Index of the ``out`` node of the zone at ``position``.

        Args:
            position: index of the zone.

        Returns:
            The index of its ``out`` node.
        """
        return 2 * position + 1

    @property
    def _source(self) -> int:
        """Source of the flow: the ``out`` node of the start hub."""
        return self._exit(self._index[self._network.start.name])

    @property
    def _sink(self) -> int:
        """Sink of the flow: the ``out`` node of the end hub."""
        return self._exit(self._index[self._network.end.name])

    def _build(self) -> None:
        """Create the arcs of the flow graph.

        Each zone gives one arc ``in -> out`` carrying its capacity and
        its entry cost; the start hub is free since a drone does not
        *enter* it. Each connection gives two arcs, one per direction,
        because the connections of the map are bidirectional.
        """
        for zone in self._zones:
            position = self._index[zone.name]
            capacity = (
                INFINITE_CAPACITY if zone.capacity is None else zone.capacity
            )
            if not zone.is_accessible:
                capacity = 0
            cost = 0 if zone.is_start else zone.entry_cost
            arc = self._flow.add_arc(
                self._entry(position), self._exit(position), capacity, cost
            )
            self._split_arc[position] = arc
        for link in self._network.links:
            if not link.is_usable:
                continue
            first = self._index[link.first.name]
            second = self._index[link.second.name]
            for origin, destination in (
                (first, second), (second, first)
            ):
                arc = self._flow.add_arc(
                    self._exit(origin),
                    self._entry(destination),
                    link.capacity,
                    0,
                )
                self._link_of_arc[arc] = link
                self._crossing_arcs.append(arc)

    def route_sets(self, max_routes: Optional[int] = None) -> List[List[Path]]:
        """Compute the best route set for every possible width.

        The flow is grown one unit at a time. After each augmentation
        the whole flow is decomposed again, which is the point of the
        method: adding a route may *reroute* the previous ones, and the
        decomposition always reflects the current optimum.

        Args:
            max_routes: maximum number of parallel routes to look for.
                Defaults to the number of drones, since more routes than
                drones can never help.

        Returns:
            A list whose element ``k - 1`` holds a set of ``k`` routes,
            each set being of minimal total duration for that width.

        Raises:
            SimulationError: when not a single route exists.
        """
        limit = self._network.nb_drones if max_routes is None else max_routes
        sets: List[List[Path]] = []
        for _ in range(max(limit, 1)):
            if not self._flow.augment(self._source, self._sink):
                break
            sets.append(self._decompose())
        if not sets:
            raise SimulationError(
                f"no route from {self._network.start.name!r} to "
                f"{self._network.end.name!r}: the map has no solution "
                "(check for blocked zones or missing connections)"
            )
        return sets

    def _decompose(self) -> List[Path]:
        """Split the current flow into a list of independent routes.

        Returns:
            One :class:`~path.Path` per unit of flow, sorted by
            duration so that the router sees the fastest route first.
        """
        remaining = {
            arc: self._flow.flow_on(arc) for arc in self._crossing_arcs
        }
        routes: List[Path] = []
        while True:
            route = self._extract(remaining)
            if route is None:
                break
            routes.append(route)
        routes.sort(key=lambda route: (route.travel_time, route.preference))
        return routes

    def _extract(self, remaining: Dict[int, int]) -> Optional[Path]:
        """Pull one route out of the remaining flow.

        Args:
            remaining: units of flow left on each crossing arc; the
                consumed units are removed by this method.

        Returns:
            A path from the start hub to the end hub, or None when the
            flow is exhausted.

        Raises:
            SimulationError: if the flow cannot be decomposed, which
                would mean the solver produced an inconsistent result.
        """
        end_name = self._network.end.name
        zones: List[Zone] = [self._network.start]
        links: List[Link] = []
        node = self._source
        for _ in range(len(self._zones)):
            arc = self._pick(node, remaining)
            if arc is None:
                if not links:
                    return None
                raise SimulationError(
                    "internal error: the flow could not be decomposed "
                    "into complete routes"
                )
            remaining[arc] -= 1
            links.append(self._link_of_arc[arc])
            position = self._flow.target_of(arc) // 2
            zone = self._zones[position]
            zones.append(zone)
            if zone.name == end_name:
                return Path(zones, links)
            node = self._exit(position)
        raise SimulationError(
            "internal error: a cycle was found while decomposing the flow"
        )

    def _pick(self, node: int, remaining: Dict[int, int]) -> Optional[int]:
        """Choose an arc still carrying flow out of ``node``.

        Args:
            node: index of an ``out`` node.
            remaining: units of flow left on each crossing arc.

        Returns:
            The index of a usable arc, or None if there is none.
        """
        for arc in self._flow.outgoing(node):
            if remaining.get(arc, 0) > 0:
                return arc
        return None

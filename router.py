"""Deciding how many drones take which route.

Two questions are answered here.

**How long does a route set take?** A route can swallow one drone per
turn: a drone that leaves a zone frees it for the very same turn, so the
drones of a route advance in lockstep, one behind the other. A route of
duration ``t`` carrying ``n`` drones therefore delivers its last drone
at turn ``t + n - 1``, and the mission ends when the slowest route is
done::

    turns = max(t_i + n_i - 1)

That formula is only valid because the route sets come from a flow: the
flow guarantees that ``k`` routes never ask more of a zone or of a
connection than its capacity allows, so the ``k`` routes really can run
in parallel. This is the pay-off of the modelling done in ``flow.py``.

**How many drones on each route?** Minimising the formula above is done
by binary search on the answer. If the mission lasts ``T`` turns, a
route of duration ``t`` can deliver ``T - t + 1`` drones (none at all
when ``t > T``). Summing that over the routes gives the number of drones
deliverable in ``T`` turns, a quantity that grows with ``T``, so the
smallest ``T`` able to carry every drone is found by dichotomy.

Finally, more routes is not always better: opening a fifth route that is
ten turns long is pointless for three drones. Every route set produced
by the flow solver is therefore evaluated, and the cheapest wins.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from errors import SimulationError
from flow import RouteSolver
from network import Network
from path import Path


class RoutePlan:
    """The final decision: which drone flies on which route."""

    def __init__(self, routes: Sequence[Path], counts: Sequence[int]) -> None:
        """Build a plan from a route set and its drone counts.

        Routes receiving no drone are dropped, so a plan never carries a
        useless route.

        Args:
            routes: the routes of the set.
            counts: number of drones on each route, same order.

        Raises:
            SimulationError: if the two sequences have different lengths
                or if no drone is assigned at all.
        """
        if len(routes) != len(counts):
            raise SimulationError(
                "internal error: routes and counts have different sizes"
            )
        kept = [
            (route, count)
            for route, count in zip(routes, counts)
            if count > 0
        ]
        if not kept:
            raise SimulationError("internal error: empty route plan")
        self._routes: Tuple[Path, ...] = tuple(route for route, _ in kept)
        self._counts: Tuple[int, ...] = tuple(count for _, count in kept)
        self._lanes, self._departures = self._assign()

    @property
    def routes(self) -> Tuple[Path, ...]:
        """The routes actually used, fastest first."""
        return self._routes

    @property
    def counts(self) -> Tuple[int, ...]:
        """Number of drones flying on each route."""
        return self._counts

    @property
    def nb_drones(self) -> int:
        """Total number of drones covered by the plan."""
        return sum(self._counts)

    @property
    def estimated_turns(self) -> int:
        """Number of turns the plan should take.

        The simulator remains the reference: this value is what the
        model predicts, and the two are compared in the final report.
        """
        return max(
            route.travel_time + count - 1
            for route, count in zip(self._routes, self._counts)
        )

    def lane_of(self, drone_index: int) -> int:
        """Return the lane a drone flies in.

        A lane is one slot of the plan: two lanes may follow the very
        same zones when a corridor is wide enough to host two routes.
        Each lane accepts one departure per turn, which is exactly the
        throughput the duration formula assumes.

        Args:
            drone_index: 0-based index of the drone.

        Returns:
            The index of the lane, in ``self.routes`` order.
        """
        return self._lanes[drone_index]

    def departure_of(self, drone_index: int) -> int:
        """Return the turn at which a drone leaves the start hub.

        A lane accepts one departure per turn, so the drone that is
        ``k``-th on its lane takes off on turn ``k``. Those turns form
        the schedule the simulator plays.

        Args:
            drone_index: 0-based index of the drone.

        Returns:
            The 1-based turn number of its departure.
        """
        return self._departures[drone_index]

    def route_of(self, drone_index: int) -> Path:
        """Return the route of a drone.

        Args:
            drone_index: 0-based index of the drone, so drone ``D1`` is
                at index 0.

        Returns:
            The route the drone must follow.
        """
        return self._routes[self._lanes[drone_index]]

    def _assign(self) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
        """Spread the drones over the routes in departure order.

        The routes are served round-robin rather than one after the
        other, so that ``D1``, ``D2`` and ``D3`` leave together on three
        different routes during the first turn. The numbering of the
        drones then follows the order in which they take off, which
        makes the trace far easier to read.

        Returns:
            Two tuples indexed by drone number minus one: the lane of
            each drone, and the turn it takes off on.
        """
        remaining = list(self._counts)
        lanes: List[int] = []
        departures: List[int] = []
        sent = [0] * len(self._counts)
        while any(remaining):
            for position, left in enumerate(remaining):
                if left > 0:
                    lanes.append(position)
                    sent[position] += 1
                    departures.append(sent[position])
                    remaining[position] -= 1
        return tuple(lanes), tuple(departures)

    def __str__(self) -> str:
        """Human readable summary of the plan."""
        lines = [
            f"{count} drone(s) | {route.travel_time} turn(s) | {route}"
            for route, count in zip(self._routes, self._counts)
        ]
        return "\n".join(lines)


class Router:
    """Turn a network into a route plan."""

    def __init__(self, network: Network) -> None:
        """Bind the router to a network.

        Args:
            network: the network to solve.
        """
        self._network = network
        self._solver = RouteSolver(network)

    def plan(self) -> RoutePlan:
        """Compute the fastest plan for the whole fleet.

        Every route set produced by the flow solver is evaluated and the
        one leading to the smallest number of turns is kept. Ties are
        broken in favour of the set using fewer routes, because a
        simpler plan is easier to read and to check.

        Returns:
            The best plan found.

        Raises:
            SimulationError: when the map has no solution.
        """
        nb_drones = self._network.nb_drones
        best: Optional[RoutePlan] = None
        for routes in self._solver.route_sets():
            counts = self._distribute(routes, nb_drones)
            candidate = RoutePlan(routes, counts)
            if best is None:
                best = candidate
            elif candidate.estimated_turns < best.estimated_turns:
                best = candidate
        if best is None:
            raise SimulationError("no route plan could be built")
        return best

    def _distribute(
        self, routes: Sequence[Path], nb_drones: int
    ) -> List[int]:
        """Spread ``nb_drones`` drones over ``routes``.

        Args:
            routes: the route set to fill, sorted by duration.
            nb_drones: number of drones to place.

        Returns:
            The number of drones for each route, in the same order.
        """
        turns = self._minimal_turns(routes, nb_drones)
        counts = [
            max(0, turns - route.travel_time + 1) for route in routes
        ]
        return self._trim(routes, counts, nb_drones)

    @staticmethod
    def _throughput(routes: Sequence[Path], turns: int) -> int:
        """Number of drones deliverable in ``turns`` turns.

        Args:
            routes: the route set.
            turns: the duration budget.

        Returns:
            The total number of drones the set can deliver in time.
        """
        return sum(
            max(0, turns - route.travel_time + 1) for route in routes
        )

    def _minimal_turns(
        self, routes: Sequence[Path], nb_drones: int
    ) -> int:
        """Binary search the smallest workable duration.

        The lower bound is the duration of the fastest route, which no
        plan can beat. The upper bound is that same duration increased
        by the number of drones, which is what a single route would
        need, hence always enough.

        Args:
            routes: the route set, sorted by duration.
            nb_drones: number of drones to deliver.

        Returns:
            The smallest number of turns able to carry every drone.
        """
        low = routes[0].travel_time
        high = low + nb_drones
        while low < high:
            middle = (low + high) // 2
            if self._throughput(routes, middle) >= nb_drones:
                high = middle
            else:
                low = middle + 1
        return low

    @staticmethod
    def _trim(
        routes: Sequence[Path], counts: List[int], nb_drones: int
    ) -> List[int]:
        """Remove the drones the binary search added in excess.

        The chosen duration is often able to carry a little more than
        the fleet; the surplus is taken away from the slowest routes
        first, since emptying a slow route can only help.

        Args:
            routes: the route set, sorted by duration.
            counts: the raw counts, modified in place.
            nb_drones: the exact number of drones to place.

        Returns:
            The corrected counts.
        """
        excess = sum(counts) - nb_drones
        for position in reversed(range(len(routes))):
            if excess <= 0:
                break
            removed = min(excess, counts[position])
            counts[position] -= removed
            excess -= removed
        return counts

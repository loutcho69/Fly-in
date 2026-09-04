"""Statistics about a finished mission.

Nothing here decides anything: the class only reads a simulation that
already happened and derives the figures the final report displays. It
is kept apart from the renderer so that the numbers can be reused, for
instance by a test comparing two maps.
"""

from __future__ import annotations

from typing import Dict, Tuple

from network import Network
from router import RoutePlan
from simulator import SimulationResult


class Metrics:
    """Figures describing how well a mission went."""

    def __init__(
        self,
        network: Network,
        plan: RoutePlan,
        result: SimulationResult,
    ) -> None:
        """Collect the three objects a mission produced.

        Args:
            network: the map that was flown over.
            plan: the plan the router chose.
            result: the trace the simulator produced.
        """
        self._network = network
        self._plan = plan
        self._result = result

    @property
    def network(self) -> Network:
        """The map the mission was flown on."""
        return self._network

    @property
    def nb_drones(self) -> int:
        """Number of drones in the fleet."""
        return self._network.nb_drones

    @property
    def nb_routes(self) -> int:
        """Number of routes the plan used."""
        return len(self._plan.routes)

    @property
    def total_turns(self) -> int:
        """Number of turns the mission actually took."""
        return self._result.total_turns

    @property
    def total_moves(self) -> int:
        """Number of moves printed in the trace."""
        return self._result.total_moves

    @property
    def estimated_turns(self) -> int:
        """Number of turns the router predicted."""
        return self._plan.estimated_turns

    @property
    def prediction_matches(self) -> bool:
        """True when the simulation confirms the prediction.

        The router computes the duration with a closed formula while the
        simulator plays every turn. The two are independent, so a
        mismatch is a bug, and this flag is a free self-check.
        """
        return self.estimated_turns == self.total_turns

    @property
    def solo_turns(self) -> int:
        """Turns one drone alone would need on the fastest route."""
        return self._plan.routes[0].travel_time

    @property
    def single_route_turns(self) -> int:
        """Turns the whole fleet would need on the fastest route only.

        This is the naive solution, kept as a reference point: the ratio
        between it and the real duration measures what running several
        routes in parallel actually bought us.
        """
        return self.solo_turns + self.nb_drones - 1

    @property
    def speedup(self) -> float:
        """How many times faster than the naive single-route solution."""
        if self.total_turns == 0:
            return 0.0
        return self.single_route_turns / self.total_turns

    @property
    def idle_turns(self) -> int:
        """Total number of turns drones spent waiting.

        A drone that never waits arrives after exactly the duration of
        its route; anything beyond that is congestion.
        """
        wasted = 0
        for drone in self._result.drones:
            arrival = drone.arrival_turn
            if arrival is not None:
                wasted += arrival - drone.route.travel_time
        return wasted

    @property
    def last_arrival(self) -> int:
        """Turn at which the last drone landed on the end hub."""
        return max(
            drone.arrival_turn or 0 for drone in self._result.drones
        )

    @property
    def moves_per_turn(self) -> float:
        """Average number of drones moved per turn.

        One of the secondary metrics the subject suggests: it measures
        how well the plan fills each turn instead of leaving drones
        idle.
        """
        if self.total_turns == 0:
            return 0.0
        return self.total_moves / self.total_turns

    @property
    def turns_per_drone(self) -> float:
        """Average number of turns a drone spent in the air.

        A second metric suggested by the subject. It counts from the
        take-off of the first drone, so a large fleet on a narrow map
        raises it even when every drone flies a short route.
        """
        arrivals = [
            drone.arrival_turn
            for drone in self._result.drones
            if drone.arrival_turn is not None
        ]
        if not arrivals:
            return 0.0
        return sum(arrivals) / len(arrivals)

    @property
    def total_path_cost(self) -> int:
        """Sum of the weighted movement costs across all drones.

        The third metric the subject suggests. A ``restricted`` zone
        counts double, so the figure is the total number of turns the
        fleet would need with no congestion at all, and the difference
        with :attr:`idle_turns` is exactly what the queues cost.
        """
        return sum(
            drone.route.travel_time for drone in self._result.drones
        )

    def peak_occupancy(self) -> Dict[str, int]:
        """Largest number of drones each zone held at once.

        The two hubs are left out: they have no capacity limit, so they
        would always top the list and hide the zones that actually
        constrain the mission.

        Returns:
            A dictionary mapping a zone name to its peak occupancy,
            busiest first.
        """
        peaks: Dict[str, int] = {}
        for turn in self._result.turns:
            for name, count in turn.states.items():
                if self._is_hub(name):
                    continue
                peaks[name] = max(peaks.get(name, 0), count)
        return dict(
            sorted(peaks.items(), key=lambda item: (-item[1], item[0]))
        )

    def zone_visits(self) -> Dict[str, int]:
        """Count how many drones went through each zone.

        The two hubs are left out for the same reason as in
        :meth:`peak_occupancy`: every drone starts on one and ends on
        the other, so counting them says nothing about the map.

        Returns:
            A dictionary mapping a zone name to a number of visits,
            sorted from the busiest zone to the quietest.
        """
        visits: Dict[str, int] = {}
        for turn in self._result.turns:
            for move in turn.moves:
                if move.in_flight or self._is_hub(move.location):
                    continue
                visits[move.location] = visits.get(move.location, 0) + 1
        return dict(
            sorted(visits.items(), key=lambda item: (-item[1], item[0]))
        )

    def _is_hub(self, name: str) -> bool:
        """Tell whether a name is one of the two unlimited hubs.

        Args:
            name: the name of a zone.

        Returns:
            True for the start hub and the end hub.
        """
        return name in (
            self._network.start.name, self._network.end.name
        )

    def busiest_zones(self, count: int = 3) -> Tuple[Tuple[str, int], ...]:
        """The most crossed zones of the map.

        Args:
            count: how many zones to return.

        Returns:
            Pairs ``(zone name, visits)``, busiest first.
        """
        return tuple(list(self.zone_visits().items())[:count])

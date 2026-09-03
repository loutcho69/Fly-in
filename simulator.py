"""The turn by turn engine.

The router does not only pick the routes, it produces a **schedule**:
every drone knows the lane it flies on and the turn it takes off. The
engine plays that schedule and checks it.

Three rules of the subject shape the design.

**A drone in transit must land on the very next turn.** The subject is
explicit: a drone that entered a connection towards a ``restricted``
zone cannot wait there for a free slot. So a drone that has left the
start hub advances every single turn until it is delivered. Only the
drones still standing on the start hub may be held back, and holding
them costs nothing since the start hub has no capacity limit.

**Leaving frees a slot for the same turn.** Every drone already on its
way advances during the same pass, so a zone released on turn ``t`` is
free on turn ``t`` for the drone entering it.

**One departure per lane per turn.** That is the throughput the duration
formula of ``router.py`` assumes, and the flow computed in ``flow.py``
proves those lanes fit in the network at once. The engine nevertheless
verifies every capacity at the end of every turn: a schedule breaking a
rule is rejected, never printed.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from drone import Drone
from errors import SimulationError
from network import Network
from router import RoutePlan


class Move:
    """One drone changing place during one turn."""

    def __init__(self, drone: str, location: str, in_flight: bool) -> None:
        """Record a move.

        Args:
            drone: display name of the drone, such as ``D1``.
            location: zone name, or connection name while in transit.
            in_flight: True when the drone is on a connection.
        """
        self._drone = drone
        self._location = location
        self._in_flight = in_flight

    @property
    def drone(self) -> str:
        """Display name of the drone."""
        return self._drone

    @property
    def location(self) -> str:
        """Zone or connection the drone is on at the end of the turn."""
        return self._location

    @property
    def in_flight(self) -> bool:
        """True when the drone is still crossing a connection."""
        return self._in_flight

    def __str__(self) -> str:
        """Trace format of a move, such as ``D1-corridorA``."""
        return f"{self._drone}-{self._location}"


class Turn:
    """Every move performed during a single turn."""

    def __init__(self, number: int, moves: Sequence[Move]) -> None:
        """Record a turn.

        Args:
            number: 1-based turn number.
            moves: the moves performed, in drone order.
        """
        self._number = number
        self._moves: Tuple[Move, ...] = tuple(moves)

    @property
    def number(self) -> int:
        """1-based number of the turn."""
        return self._number

    @property
    def moves(self) -> Tuple[Move, ...]:
        """The moves performed during the turn."""
        return self._moves

    def __len__(self) -> int:
        """Number of moves performed during the turn."""
        return len(self._moves)

    def __str__(self) -> str:
        """Trace format of a turn, such as ``D1-a D2-b``."""
        return " ".join(str(move) for move in self._moves)


class SimulationResult:
    """The outcome of a run: the trace plus what it cost."""

    def __init__(self, turns: Sequence[Turn], drones: Sequence[Drone]) -> None:
        """Store the result of a simulation.

        Args:
            turns: the turns played, in order.
            drones: the fleet, in identifier order.
        """
        self._turns: Tuple[Turn, ...] = tuple(turns)
        self._drones: Tuple[Drone, ...] = tuple(drones)

    @property
    def turns(self) -> Tuple[Turn, ...]:
        """The turns played, in order."""
        return self._turns

    @property
    def drones(self) -> Tuple[Drone, ...]:
        """The fleet, in identifier order."""
        return self._drones

    @property
    def total_turns(self) -> int:
        """Number of turns the mission took."""
        return len(self._turns)

    @property
    def total_moves(self) -> int:
        """Number of individual moves performed."""
        return sum(len(turn) for turn in self._turns)


class Simulator:
    """Play a route plan turn by turn on a network."""

    def __init__(self, network: Network, plan: RoutePlan) -> None:
        """Prepare a simulation.

        Args:
            network: the network to fly over.
            plan: the plan produced by the router.

        Raises:
            SimulationError: if the plan does not cover the fleet.
        """
        if plan.nb_drones != network.nb_drones:
            raise SimulationError(
                f"the plan carries {plan.nb_drones} drone(s) but the map "
                f"declares {network.nb_drones}"
            )
        self._network = network
        self._plan = plan
        self._drones: Tuple[Drone, ...] = tuple(
            Drone(
                number + 1,
                plan.route_of(number),
                plan.lane_of(number),
                plan.departure_of(number),
            )
            for number in range(network.nb_drones)
        )

    @property
    def drones(self) -> Tuple[Drone, ...]:
        """The fleet, in identifier order."""
        return self._drones

    def run(self, turn_limit: int = 100_000) -> SimulationResult:
        """Play the whole mission.

        Args:
            turn_limit: safety net against an endless loop; a correct
                plan never reaches it.

        Returns:
            The trace and the statistics of the mission.

        Raises:
            SimulationError: if a turn moves nobody while drones are
                still on their way, or if a capacity is exceeded.
        """
        turns: List[Turn] = []
        number = 0
        while not self._everyone_arrived():
            number += 1
            if number > turn_limit:
                raise SimulationError(
                    f"the simulation exceeded {turn_limit} turns and was "
                    "stopped"
                )
            turn = self._play(number)
            if not turn.moves:
                raise SimulationError(
                    f"deadlock at turn {number}: no drone can move while "
                    f"{self._pending()} of them have not arrived"
                )
            turns.append(turn)
        return SimulationResult(turns, self._drones)

    def _play(self, number: int) -> Turn:
        """Play one turn.

        Two passes. Every drone already on its way advances, because the
        rules forbid it to stop in transit. Then the drones still
        waiting on the start hub take off, if their scheduled turn has
        come and if the capacities allow it; they are the only ones that
        can be delayed.

        Args:
            number: 1-based number of the turn.

        Returns:
            The turn, holding every move that took place.

        Raises:
            SimulationError: if a capacity was exceeded, which would
                mean the plan is not feasible.
        """
        occupancy: Dict[str, int] = {}
        usage: Dict[Tuple[str, str], int] = {}
        moves: List[Move] = []
        for drone in self._drones:
            if drone.has_arrived or not drone.has_started:
                continue
            moves.append(self._advance(drone, number, occupancy, usage))
        for drone in self._drones:
            if drone.has_started or drone.has_arrived:
                continue
            if self._may_take_off(drone, number, occupancy, usage):
                moves.append(self._advance(drone, number, occupancy, usage))
        moves.sort(key=lambda move: int(move.drone[1:]))
        self._verify(number, occupancy, usage)
        return Turn(number, moves)

    def _advance(
        self,
        drone: Drone,
        number: int,
        occupancy: Dict[str, int],
        usage: Dict[Tuple[str, str], int],
    ) -> Move:
        """Move one drone one step forward and book what it uses.

        A drone landing at the end of a two turn move consumed the
        connection on the *previous* turn, so it does not count against
        that connection now.

        Args:
            drone: the drone to move.
            number: 1-based number of the turn.
            occupancy: drones per zone at the end of the turn, updated
                in place.
            usage: drones per connection during the turn, updated in
                place.

        Returns:
            The move that was performed.
        """
        if drone.is_flying:
            location = drone.land(number)
            self._book(occupancy, location)
            return Move(drone.name, location, False)
        link = drone.next_link
        immediate = drone.next_cost == 1
        location = drone.depart(number)
        if link is not None:
            usage[link.key] = usage.get(link.key, 0) + 1
        if immediate:
            self._book(occupancy, location)
        return Move(drone.name, location, not immediate)

    @staticmethod
    def _book(occupancy: Dict[str, int], name: str) -> None:
        """Record that one more drone stands in a zone."""
        occupancy[name] = occupancy.get(name, 0) + 1

    @staticmethod
    def _may_take_off(
        drone: Drone,
        number: int,
        occupancy: Dict[str, int],
        usage: Dict[Tuple[str, str], int],
    ) -> bool:
        """Tell whether a waiting drone may leave the start hub now.

        The destination zone is only checked for a one turn move. A two
        turn move lands on the *next* turn, when the drone ahead on the
        same lane will have moved on, so testing the zone now would hold
        the fleet back for nothing; the final check of the turn catches
        a real conflict anyway.

        Args:
            drone: a drone still standing on the start hub.
            number: 1-based number of the turn.
            occupancy: drones per zone at the end of the turn.
            usage: drones per connection during the turn.

        Returns:
            True if the drone takes off during this turn.
        """
        if number < drone.departure_turn:
            return False
        target = drone.destination
        link = drone.next_link
        if target is None or link is None:
            return False
        if not link.has_room_for(usage.get(link.key, 0)):
            return False
        if drone.next_cost > 1:
            return True
        return target.has_room_for(occupancy.get(target.name, 0))

    def _verify(
        self,
        number: int,
        occupancy: Dict[str, int],
        usage: Dict[Tuple[str, str], int],
    ) -> None:
        """Check every capacity at the end of a turn.

        Args:
            number: 1-based number of the turn.
            occupancy: drones per zone at the end of the turn.
            usage: drones per connection during the turn.

        Raises:
            SimulationError: on the first capacity that is exceeded.
        """
        for name, count in occupancy.items():
            zone = self._network.zone(name)
            if not zone.has_room_for(count - 1):
                raise SimulationError(
                    f"turn {number}: zone {name!r} would hold {count} "
                    f"drone(s) for a capacity of {zone.capacity}"
                )
        for key, count in usage.items():
            link = self._network.link_between(*key)
            if link is not None and count > link.capacity:
                raise SimulationError(
                    f"turn {number}: connection {link.name!r} would carry "
                    f"{count} drone(s) for a capacity of {link.capacity}"
                )

    def _everyone_arrived(self) -> bool:
        """True once every drone reached the end hub."""
        return all(drone.has_arrived for drone in self._drones)

    def _pending(self) -> int:
        """Number of drones still on their way."""
        return sum(1 for drone in self._drones if not drone.has_arrived)

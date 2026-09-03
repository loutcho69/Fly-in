"""Drones: the only objects of the project that carry a mutable state.

A drone is a small state machine walking along the route the router
assigned to it:

* ``WAITING`` -- it sits in a zone, ready to take the next connection;
* ``FLYING`` -- it is half way through a connection leading to a
  ``restricted`` zone, which takes two turns to enter;
* ``ARRIVED`` -- it reached the end hub and never moves again.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from errors import SimulationError
from link import Link
from path import Path
from zone import Zone


class DroneState(Enum):
    """The three states a drone can be in."""

    WAITING = "waiting"
    FLYING = "flying"
    ARRIVED = "arrived"


class Drone:
    """One drone flying along one route."""

    def __init__(
        self, identifier: int, route: Path, lane: int, departure: int
    ) -> None:
        """Build a drone standing on the first zone of its route.

        Args:
            identifier: 1-based number of the drone, so the first one
                is displayed as ``D1``.
            route: the route the drone must follow.
            lane: index of the lane of the plan it belongs to.
            departure: turn on which it must leave the start hub.
        """
        self._identifier = identifier
        self._route = route
        self._lane = lane
        self._departure = departure
        self._step = 0
        self._state = DroneState.WAITING
        self._arrival_turn: Optional[int] = None

    @property
    def identifier(self) -> int:
        """1-based number of the drone."""
        return self._identifier

    @property
    def name(self) -> str:
        """Display name of the drone, such as ``D1``."""
        return f"D{self._identifier}"

    @property
    def lane(self) -> int:
        """Index of the lane of the plan the drone flies in."""
        return self._lane

    @property
    def departure_turn(self) -> int:
        """Turn on which the drone is scheduled to leave the start hub."""
        return self._departure

    @property
    def has_started(self) -> bool:
        """True once the drone left the start hub."""
        return self._step > 0 or self.is_flying

    @property
    def route(self) -> Path:
        """The route assigned to the drone."""
        return self._route

    @property
    def state(self) -> DroneState:
        """Current state of the drone."""
        return self._state

    @property
    def step(self) -> int:
        """Index of the zone the drone stands on, or has just left."""
        return self._step

    @property
    def is_flying(self) -> bool:
        """True while the drone is in transit on a connection."""
        return self._state is DroneState.FLYING

    @property
    def has_arrived(self) -> bool:
        """True once the drone reached the end hub."""
        return self._state is DroneState.ARRIVED

    @property
    def arrival_turn(self) -> Optional[int]:
        """Turn at which the drone landed on the end hub, if it did."""
        return self._arrival_turn

    @property
    def zone(self) -> Zone:
        """Zone the drone currently occupies.

        Raises:
            SimulationError: if the drone is in flight, in which case it
                occupies a connection and not a zone.
        """
        if self.is_flying:
            raise SimulationError(
                f"{self.name} is in flight and occupies no zone"
            )
        return self._route.zones[self._step]

    @property
    def destination(self) -> Optional[Zone]:
        """Next zone on the route, or None if the drone is done."""
        if self._step + 1 >= len(self._route):
            return None
        return self._route.zones[self._step + 1]

    @property
    def next_link(self) -> Optional[Link]:
        """Next connection to cross, or None if the drone is done."""
        if self._step >= self._route.moves:
            return None
        return self._route.links[self._step]

    @property
    def location(self) -> str:
        """Name of the zone or of the connection holding the drone.

        This is what the trace displays after the drone name: a zone
        name in the usual case, a connection name while the drone is in
        transit towards a ``restricted`` zone.
        """
        if self.is_flying:
            link = self._route.links[self._step]
            return link.name
        return self.zone.name

    @property
    def next_cost(self) -> int:
        """Number of turns the next move takes, 1 or 2.

        Raises:
            SimulationError: if the drone has no move left.
        """
        if self._step >= self._route.moves:
            raise SimulationError(f"{self.name} has no move left")
        return self._route.step_cost(self._step)

    @property
    def remaining_moves(self) -> int:
        """Number of connections left before the end hub."""
        return self._route.moves - self._step

    def can_move(self) -> bool:
        """True when the drone is waiting and still has a move to make."""
        if self._state is not DroneState.WAITING:
            return False
        return self.destination is not None

    def depart(self, turn: int) -> str:
        """Leave the current zone for the next one.

        A one turn move lands the drone immediately; a two turn move
        (an entry into a ``restricted`` zone) leaves it on the
        connection until the next turn.

        Args:
            turn: number of the current turn, recorded when the move
                ends on the end hub.

        Returns:
            The location to display in the trace for this turn.

        Raises:
            SimulationError: if the drone cannot move right now.
        """
        if self._state is not DroneState.WAITING:
            raise SimulationError(f"{self.name} is not ready to move")
        if self.destination is None:
            raise SimulationError(f"{self.name} has no move left")
        if self._route.step_cost(self._step) > 1:
            self._state = DroneState.FLYING
            return self.location
        self._advance()
        self._record_arrival(turn)
        return self.location

    def land(self, turn: int) -> str:
        """Finish a two turn move and settle in the destination zone.

        Args:
            turn: number of the current turn, recorded when the drone
                reaches the end hub.

        Returns:
            The location to display in the trace for this turn.

        Raises:
            SimulationError: if the drone is not in flight.
        """
        if self._state is not DroneState.FLYING:
            raise SimulationError(f"{self.name} is not in flight")
        self._state = DroneState.WAITING
        self._advance()
        self._record_arrival(turn)
        return self.location

    def _advance(self) -> None:
        """Move the cursor one zone forward along the route."""
        self._step += 1

    def _record_arrival(self, turn: int) -> None:
        """Mark the drone as arrived when it stands on the end hub.

        Args:
            turn: number of the current turn.
        """
        if self._state is DroneState.WAITING and self.destination is None:
            self._state = DroneState.ARRIVED
            self._arrival_turn = turn

    def __repr__(self) -> str:
        """Developer friendly representation, handy in pdb."""
        return (
            f"Drone({self.name!r}, at={self.location!r}, "
            f"state={self._state.value})"
        )

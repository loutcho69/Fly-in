"""An independent referee for the simulator.

The simulator enforces the rules while it plays; this module checks them
again *afterwards*, reading nothing but the map and the printed trace.
The two never share any code, so a rule broken by the engine cannot be
missed by the referee. It also generates random maps, which is how the
two ordering bugs of the engine were found.

Usage::

    python3 check.py              # all maps of maps/ plus 200 random ones
    python3 check.py maps/hard_1.map    # one map
    python3 check.py --fuzz 1000 --seed 42
"""

from __future__ import annotations

import argparse
import itertools
import os
import random
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Set, Tuple

from errors import FlyInError
from mission import Mission
from network import Network
from simulator import SimulationResult

MAPS_DIRECTORY = "maps"
INVALID_DIRECTORY = "invalid"


class CheckError(Exception):
    """Raised when a trace breaks a rule of the subject."""


class TraceChecker:
    """Replay a trace against a map and validate every rule."""

    def __init__(self, network: Network, result: SimulationResult) -> None:
        """Prepare the replay.

        Args:
            network: the map the trace was produced on.
            result: the trace to validate.
        """
        self._network = network
        self._result = result
        self._position: Dict[str, str] = {}
        self._flying: Dict[str, str] = {}

    def verify(self) -> None:
        """Replay the whole trace.

        Raises:
            CheckError: on the first rule violation found.
        """
        start = self._network.start.name
        for drone in self._result.drones:
            self._position[drone.name] = start
        for turn in self._result.turns:
            self._replay_turn(turn.number, [
                (move.drone, move.location) for move in turn.moves
            ])
        self._check_everyone_arrived()

    def _replay_turn(
        self, number: int, moves: Sequence[Tuple[str, str]]
    ) -> None:
        """Replay one turn and check it.

        Args:
            number: 1-based turn number.
            moves: pairs ``(drone name, location)``.

        Raises:
            CheckError: on any violation.
        """
        moved: Set[str] = set()
        must_land = set(self._flying)
        link_usage: Dict[Tuple[str, str], int] = {}
        for drone, location in moves:
            if drone in moved:
                raise CheckError(
                    f"turn {number}: {drone} moves twice in the same turn"
                )
            moved.add(drone)
            self._apply(number, drone, location, link_usage)
        # Every drone still in flight took off during this very turn,
        # and _take_off already counted it against the connection: no
        # drone can linger from a previous turn, as checked below.
        stranded = must_land & set(self._flying)
        if stranded:
            names = ", ".join(sorted(stranded))
            raise CheckError(
                f"turn {number}: {names} stayed on a connection, which "
                "the rules forbid: a drone in transit must land on the "
                "next turn"
            )
        self._check_zone_capacity(number)
        self._check_link_capacity(number, link_usage)

    def _apply(
        self,
        number: int,
        drone: str,
        location: str,
        link_usage: Dict[Tuple[str, str], int],
    ) -> None:
        """Apply one move and check that it was legal.

        A location holding a dash can only be a connection, since zone
        names may not contain one: the two namespaces never overlap.

        Args:
            number: 1-based turn number.
            drone: name of the drone that moved.
            location: where it is at the end of the turn.
            link_usage: connection usage of this turn, updated in place.

        Raises:
            CheckError: on any violation.
        """
        if drone in self._flying:
            self._land(number, drone, location)
            return
        origin = self._position[drone]
        if origin == self._network.end.name:
            raise CheckError(
                f"turn {number}: {drone} moves after reaching the end hub"
            )
        if "-" in location:
            self._take_off(number, drone, location, link_usage)
            return
        link = self._network.link_between(origin, location)
        if link is None:
            raise CheckError(
                f"turn {number}: {drone} jumps from {origin!r} to "
                f"{location!r} with no connection between them"
            )
        target = self._network.zone(location)
        if not target.is_accessible:
            raise CheckError(
                f"turn {number}: {drone} enters the blocked zone "
                f"{location!r}"
            )
        if target.entry_cost != 1:
            raise CheckError(
                f"turn {number}: {drone} enters {location!r} in one turn "
                f"but that zone costs {target.entry_cost} turns"
            )
        link_usage[link.key] = link_usage.get(link.key, 0) + 1
        self._position[drone] = location

    def _take_off(
        self,
        number: int,
        drone: str,
        location: str,
        link_usage: Dict[Tuple[str, str], int],
    ) -> None:
        """Check the first half of a two turn move.

        Args:
            number: 1-based turn number.
            drone: name of the drone.
            location: name of the connection it is flying on.
            link_usage: connection usage of this turn, updated in place.

        Raises:
            CheckError: on any violation.
        """
        key = self._key_of(location)
        link = self._network.link_between(*key)
        if link is None:
            raise CheckError(
                f"turn {number}: {drone} flies on the unknown connection "
                f"{location!r}"
            )
        origin = self._position[drone]
        if origin not in key:
            raise CheckError(
                f"turn {number}: {drone} takes the connection "
                f"{location!r} while standing in {origin!r}"
            )
        target = link.other_end(self._network.zone(origin))
        if target.entry_cost == 1:
            raise CheckError(
                f"turn {number}: {drone} spends a turn in flight towards "
                f"{target.name!r}, which is reachable in one turn"
            )
        link_usage[key] = link_usage.get(key, 0) + 1
        self._flying[drone] = location

    def _land(self, number: int, drone: str, location: str) -> None:
        """Check the second half of a two turn move.

        Args:
            number: 1-based turn number.
            drone: name of the drone.
            location: zone it claims to land in.

        Raises:
            CheckError: on any violation.
        """
        link = self._network.link_between(*self._key_of(self._flying[drone]))
        assert link is not None
        origin = self._network.zone(self._position[drone])
        expected = link.other_end(origin).name
        if location != expected:
            raise CheckError(
                f"turn {number}: {drone} lands in {location!r} but was "
                f"flying towards {expected!r}"
            )
        del self._flying[drone]
        self._position[drone] = location

    def _check_zone_capacity(self, number: int) -> None:
        """Check that no zone holds more drones than it may.

        Args:
            number: 1-based turn number.

        Raises:
            CheckError: if a zone is over capacity.
        """
        counts: Dict[str, int] = {}
        for drone, name in self._position.items():
            if drone in self._flying:
                continue
            counts[name] = counts.get(name, 0) + 1
        for name, count in counts.items():
            zone = self._network.zone(name)
            capacity = zone.capacity
            if capacity is not None and count > capacity:
                raise CheckError(
                    f"turn {number}: zone {name!r} holds {count} drones "
                    f"for a capacity of {capacity}"
                )

    def _check_link_capacity(
        self, number: int, link_usage: Dict[Tuple[str, str], int]
    ) -> None:
        """Check that no connection carried too many drones.

        Args:
            number: 1-based turn number.
            link_usage: connection usage of this turn.

        Raises:
            CheckError: if a connection is over capacity.
        """
        for key, count in link_usage.items():
            link = self._network.link_between(*key)
            if link is not None and count > link.capacity:
                raise CheckError(
                    f"turn {number}: connection {link.name!r} carried "
                    f"{count} drones for a capacity of {link.capacity}"
                )

    def _check_everyone_arrived(self) -> None:
        """Check that the whole fleet reached the end hub.

        Raises:
            CheckError: if a drone is missing or still in flight.
        """
        end = self._network.end.name
        for drone, name in self._position.items():
            if drone in self._flying:
                raise CheckError(f"{drone} is still in flight at the end")
            if name != end:
                raise CheckError(
                    f"{drone} ended in {name!r} instead of {end!r}"
                )

    @staticmethod
    def _key_of(link_name: str) -> Tuple[str, str]:
        """Canonical key of a connection given its display name.

        Args:
            link_name: display name of a connection, ``first-second``.

        Returns:
            The two zone names, sorted.
        """
        first, _, second = link_name.partition("-")
        low, high = sorted((first, second))
        return low, high


class Suite:
    """The whole verification campaign: maps, error paths and fuzzing."""

    def __init__(self, maps_directory: str = MAPS_DIRECTORY) -> None:
        """Prepare a campaign.

        Args:
            maps_directory: root directory holding the maps.
        """
        self._directory = maps_directory

    @staticmethod
    def check_map(path: str) -> str:
        """Run and validate one map.

        Args:
            path: path of the map file.

        Returns:
            A one line report.

        Raises:
            CheckError: if the trace breaks a rule, or if the duration
                the router predicted differs from the one played.
        """
        mission = Mission.load(path)
        TraceChecker(mission.network, mission.result).verify()
        predicted = mission.plan.estimated_turns
        played = mission.result.total_turns
        if predicted != played:
            raise CheckError(
                f"{path}: the router predicted {predicted} turns but the "
                f"simulation took {played}"
            )
        return (
            f"{mission.name:<30} "
            f"{mission.network.nb_drones:>3} drones  "
            f"{len(mission.plan.routes):>2} route(s)  "
            f"{played:>3} turns"
        )

    def check_invalid(self) -> int:
        """Check that every deliberately broken map is rejected.

        A parser that accepts everything is as wrong as one that accepts
        nothing, so the error paths deserve a test of their own.

        Returns:
            The number of maps that were correctly rejected.

        Raises:
            CheckError: if one of them is accepted.
        """
        rejected = 0
        broken = os.path.join(self._directory, INVALID_DIRECTORY)
        for path in self.collect_maps(broken):
            try:
                self.check_map(path)
            except FlyInError:
                rejected += 1
                continue
            except CheckError:
                pass
            raise CheckError(f"{path}: this map should have been rejected")
        return rejected

    @staticmethod
    def collect_maps(directory: str) -> List[str]:
        """List the map files of a directory tree, sorted by path.

        Args:
            directory: the directory to scan.

        Returns:
            The paths of the map files it holds.
        """
        if not os.path.isdir(directory):
            return []
        found: List[str] = []
        for root, _, names in os.walk(directory):
            if os.path.basename(root) == INVALID_DIRECTORY:
                if root != directory:
                    continue
            found.extend(
                os.path.join(root, name)
                for name in names
                if name.endswith((".map", ".txt"))
            )
        return sorted(found)

    def playable_maps(self) -> List[str]:
        """Every map meant to be solvable, broken ones excluded.

        Returns:
            The paths of the maps meant to be solvable.
        """
        return [
            path
            for path in self.collect_maps(self._directory)
            if INVALID_DIRECTORY not in path.split(os.sep)
        ]

    @staticmethod
    def random_map(generator: random.Random) -> str:
        """Build the text of a random map.

        Args:
            generator: the seeded random source.

        Returns:
            The content of a map file.
        """
        count = generator.randint(2, 7)
        names = [f"z{number}" for number in range(count)]
        lines = [
            f"nb_drones: {generator.randint(1, 15)}",
            "start_hub: start 0 0",
            "end_hub: finish 30 0",
        ]
        for position, name in enumerate(names):
            options: List[str] = []
            kind = generator.choice(
                ["normal", "normal", "priority", "restricted", "blocked"]
            )
            if kind != "normal":
                options.append(f"zone={kind}")
            if generator.random() < 0.3:
                options.append(f"max_drones={generator.randint(1, 3)}")
            suffix = " [" + " ".join(options) + "]" if options else ""
            lines.append(f"hub: {name} {position} {position % 5}{suffix}")
        for first, second in itertools.combinations(
            ["start", "finish"] + names, 2
        ):
            if generator.random() < 0.35:
                capacity = ""
                if generator.random() < 0.3:
                    capacity = (
                        " [max_link_capacity="
                        f"{generator.randint(1, 3)}]"
                    )
                lines.append(f"connection: {first}-{second}{capacity}")
        return "\n".join(lines) + "\n"

    def fuzz(self, rounds: int, seed: int) -> int:
        """Generate random maps and validate every solvable one.

        Args:
            rounds: how many maps to generate.
            seed: seed of the random source, for reproducibility.

        Returns:
            The number of maps that were solvable and checked.

        Raises:
            CheckError: on the first trace that breaks a rule.
        """
        generator = random.Random(seed)
        checked = 0
        for _ in range(rounds):
            content = self.random_map(generator)
            handle, path = tempfile.mkstemp(suffix=".map")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(content)
            try:
                self.check_map(path)
                checked += 1
            except CheckError as error:
                print(content)
                raise CheckError(f"{error} on the map above") from error
            except FlyInError:
                pass
            finally:
                os.remove(path)
        return checked

    @staticmethod
    def _pipe_closed() -> int:
        """Leave quietly when the reader of the output went away.

        ``check.py | head`` closes the pipe early; the report is not
        worth a traceback. Mirrors the guard of ``main.py``.

        Returns:
            141, the conventional status for a closed pipe.
        """
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(devnull, sys.stdout.fileno())
            finally:
                os.close(devnull)
        except OSError:
            pass
        return 141

    @classmethod
    def main(cls, argv: Optional[List[str]] = None) -> int:
        """Entry point of the checker.

        Args:
            argv: command line arguments, defaulting to ``sys.argv``.

        Returns:
            0 when everything passes, 1 otherwise.
        """
        parser = argparse.ArgumentParser(
            prog="check",
            description="Validate the simulator against the rules.",
        )
        parser.add_argument("maps", nargs="*", help="maps to check")
        parser.add_argument(
            "--fuzz", type=int, default=200, help="number of random maps"
        )
        parser.add_argument(
            "--seed", type=int, default=1234, help="random seed"
        )
        options = parser.parse_args(argv)
        suite = cls()
        paths = options.maps or suite.playable_maps()
        try:
            for path in paths:
                print("  " + suite.check_map(path))
            if not options.maps:
                rejected = suite.check_invalid()
                print(f"  invalid maps: {rejected} correctly rejected")
                checked = suite.fuzz(options.fuzz, options.seed)
                print(
                    f"  fuzzing: {checked} solvable random maps validated"
                )
        except (CheckError, FlyInError) as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
        except BrokenPipeError:
            return cls._pipe_closed()
        print("all checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(Suite.main())

"""One mission: a map, the plan chosen for it, and the trace it gave.

The four steps of the program — parse, plan, simulate, measure — always
go together, and both front ends need the four results. Wrapping them in
a single object means the command line and the graphical viewer share
one pipeline instead of each rebuilding it, and that adding a third
front end tomorrow would need nothing new.
"""

from __future__ import annotations

import os
from typing import List, Optional

from map_parser import MapParser
from metrics import Metrics
from network import Network
from router import RoutePlan, Router
from simulator import SimulationResult, Simulator

MAP_SUFFIXES = (".map", ".txt")
EXCLUDED_DIRECTORY = "invalid"


class Mission:
    """A map solved from end to end."""

    def __init__(
        self,
        path: str,
        network: Network,
        plan: RoutePlan,
        result: SimulationResult,
    ) -> None:
        """Store the four results of a run.

        Args:
            path: path of the map file.
            network: the parsed network.
            plan: the plan the router chose.
            result: the trace the simulator produced.
        """
        self._path = path
        self._network = network
        self._plan = plan
        self._result = result
        self._metrics: Optional[Metrics] = None

    @classmethod
    def load(cls, path: str) -> "Mission":
        """Read a map, plan it and simulate it.

        Args:
            path: path of the map file.

        Returns:
            The finished mission.

        Raises:
            FlyInError: if the map is invalid or has no solution.
        """
        network = MapParser(path).parse()
        plan = Router(network).plan()
        result = Simulator(network, plan).run()
        return cls(path, network, plan, result)

    @property
    def path(self) -> str:
        """Path of the map file."""
        return self._path

    @property
    def name(self) -> str:
        """File name of the map, without its directory."""
        return os.path.basename(self._path)

    @property
    def network(self) -> Network:
        """The parsed network."""
        return self._network

    @property
    def plan(self) -> RoutePlan:
        """The plan the router chose."""
        return self._plan

    @property
    def result(self) -> SimulationResult:
        """The trace the simulator produced."""
        return self._result

    @property
    def metrics(self) -> Metrics:
        """Statistics of the mission, computed on first access."""
        if self._metrics is None:
            self._metrics = Metrics(
                self._network, self._plan, self._result
            )
        return self._metrics


class MapLibrary:
    """The maps available on disk, offered by the graphical browser."""

    def __init__(self, directory: str) -> None:
        """Scan a directory tree for map files.

        Args:
            directory: the root directory to scan.
        """
        self._directory = directory
        self._paths = self._scan(directory)

    @property
    def directory(self) -> str:
        """The directory that was scanned."""
        return self._directory

    @property
    def paths(self) -> List[str]:
        """Paths of the map files found, sorted."""
        return list(self._paths)

    @staticmethod
    def _scan(directory: str) -> List[str]:
        """List the map files of a directory tree, sorted by path.

        The ``invalid`` directory is skipped: it holds the deliberately
        broken maps used to test the error messages, which have no
        reason to appear in a map browser.

        Args:
            directory: the directory to scan.

        Returns:
            The paths of the map files it holds.
        """
        if not os.path.isdir(directory):
            return []
        found: List[str] = []
        for root, folders, names in os.walk(directory):
            folders[:] = [
                folder
                for folder in folders
                if folder != EXCLUDED_DIRECTORY
            ]
            found.extend(
                os.path.join(root, name)
                for name in names
                if name.endswith(MAP_SUFFIXES)
            )
        return sorted(found)

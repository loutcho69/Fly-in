"""Entry point of the Fly-in simulator.

Usage::

    python3 main.py maps/easy/01_linear_path.txt
    python3 main.py maps/hard/02_capacity_hell.txt --gui
    python3 main.py maps/medium/01_dead_end_trap.txt --quiet

The module reads the command line, runs the pipeline through
:class:`~mission.Mission`, and turns any expected failure into a clean
message. Every piece of logic lives in its own module, so this file
stays short enough to read in one go.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional, Sequence

from colors import PALETTE
from errors import FlyInError
from mission import MapLibrary, Mission
from pathfinder import PathFinder
from renderer import Renderer
from simulator import Turn

MAPS_DIRECTORY = "maps"
MAX_DELAY = 10.0
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130


class Application:
    """The command line front end of the simulator."""

    def __init__(self, options: argparse.Namespace) -> None:
        """Prepare a run from an already parsed command line.

        Args:
            options: the parsed command line.
        """
        self._options = options
        colored = PALETTE.terminal_supports_color() and not options.no_color
        self._renderer = Renderer(colored)

    @property
    def renderer(self) -> Renderer:
        """The renderer used for every message."""
        return self._renderer

    @classmethod
    def build_parser(cls) -> argparse.ArgumentParser:
        """Describe the command line interface.

        Returns:
            The configured argument parser.
        """
        parser = argparse.ArgumentParser(
            prog="fly-in",
            description="Route a fleet of drones across a network.",
        )
        parser.add_argument("map", help="path to the map file to simulate")
        parser.add_argument(
            "--gui",
            action="store_true",
            help="open the graphical viewer once the log is printed",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="print only the flight log, in the format of the subject",
        )
        parser.add_argument(
            "--zones",
            action="store_true",
            help="show the state of every zone after each turn",
        )
        parser.add_argument(
            "--no-map",
            action="store_true",
            help="skip the ASCII view of the network",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="disable the ANSI colours",
        )
        parser.add_argument(
            "--delay",
            type=cls._delay,
            default=0.0,
            metavar="SECONDS",
            help=(
                "pause between two turns, to watch the fleet move "
                f"(0 to {MAX_DELAY:g} seconds)"
            ),
        )
        return parser

    @staticmethod
    def _delay(value: str) -> float:
        """Read and bound the ``--delay`` option.

        A negative pause is meaningless and used to be silently ignored,
        and a huge one turns the program into what looks like a freeze;
        both are rejected with a message instead.

        Args:
            value: the raw text given on the command line.

        Returns:
            The pause in seconds.

        Raises:
            argparse.ArgumentTypeError: if the value is not a number
                between 0 and :data:`MAX_DELAY`.
        """
        try:
            seconds = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"{value!r} is not a number of seconds"
            ) from None
        if not 0.0 <= seconds <= MAX_DELAY:
            raise argparse.ArgumentTypeError(
                f"the pause must be between 0 and {MAX_DELAY:g} seconds, "
                f"got {seconds:g}"
            )
        return seconds

    def run(self) -> int:
        """Run the whole pipeline on one map.

        Returns:
            The exit code of the program.

        Raises:
            FlyInError: propagated to :meth:`main`, which reports it.
        """
        mission = Mission.load(self._options.map)
        verbose = not self._options.quiet
        if verbose:
            self._show(self._renderer.summary(self._options.map,
                                              mission.network))
            self._warn_dead_zones(mission)
            if not self._options.no_map:
                self._show(self._renderer.map_view(mission.network))
            self._show(self._renderer.plan(mission.plan))
            print(self._renderer.title("Flight log"))
        self._print_log(mission, verbose)
        if verbose:
            self._show(self._renderer.report(mission.metrics))
        if self._options.gui:
            self._open_viewer(mission)
        return EXIT_SUCCESS

    @staticmethod
    def _show(lines: Sequence[str]) -> None:
        """Print a block of lines.

        Args:
            lines: the lines to print.
        """
        for line in lines:
            print(line)

    def _print_log(self, mission: Mission, verbose: bool) -> None:
        """Print the flight log, one line per turn.

        Args:
            mission: the mission to print.
            verbose: False to emit the bare format of the subject.
        """
        for turn in mission.result.turns:
            if verbose:
                print(self._renderer.turn(turn, mission.network))
                self._print_states(turn, mission)
            else:
                print(turn)
            if self._options.delay > 0:
                sys.stdout.flush()
                time.sleep(self._options.delay)

    def _print_states(self, turn: Turn, mission: Mission) -> None:
        """Print the occupancy of the zones after a turn, if asked.

        The line is opt-in because the flight log must stay in the exact
        format defined by the subject by default.

        Args:
            turn: the turn that has just been printed.
            mission: the mission being displayed.
        """
        if not self._options.zones:
            return
        line = self._renderer.zone_states(turn.states, mission.network)
        if line:
            print(line)

    def _warn_dead_zones(self, mission: Mission) -> None:
        """Warn about the zones no drone will ever be able to use.

        A zone is useless when it is blocked, unreachable from the start
        hub or unable to reach the end hub. Saying so is friendlier than
        letting the user wonder why a branch of the map stays empty.

        Args:
            mission: the mission whose map is inspected.
        """
        unusable = PathFinder(mission.network).unusable_zones()
        if unusable:
            listed = ", ".join(unusable)
            print(self._renderer.warning(f"unusable zone(s): {listed}"))

    def _open_viewer(self, mission: Mission) -> None:
        """Open the graphical viewer, if the toolkit is available.

        ``tkinter`` ships with the standard library but some systems
        package it separately, and it needs a display. It is imported
        here rather than at the top of the module, and a failure is only
        a warning: the log has already been printed, so the program
        stays useful on a terminal-only machine.

        Args:
            mission: the mission to show when the window opens.
        """
        try:
            from viewer import Viewer
        except ImportError:
            self._warn(
                "the graphical viewer needs tkinter, which is missing "
                "(macOS: brew install python-tk, "
                "Debian: sudo apt install python3-tk)"
            )
            return
        catalogue = MapLibrary(MAPS_DIRECTORY).paths
        if mission.path not in catalogue:
            catalogue.insert(0, mission.path)
        try:
            window = Viewer(mission, catalogue)
        except Exception as error:
            self._warn(f"the viewer could not open a window: {error}")
            return
        print(
            self._renderer.note(
                "viewer open; close the window to get the prompt back"
            )
        )
        try:
            window.run()
        except Exception as error:
            self._warn(f"the viewer stopped: {error}")

    def _warn(self, message: str) -> None:
        """Print a warning on the error stream.

        Args:
            message: the text to print.
        """
        print(self._renderer.warning(message), file=sys.stderr)

    @classmethod
    def main(cls, argv: Optional[List[str]] = None) -> int:
        """Parse the command line, run, and report any expected failure.

        Args:
            argv: command line arguments, defaulting to ``sys.argv``.

        Returns:
            0 on success, 1 on an expected failure, 130 on an interrupt.
        """
        options = cls.build_parser().parse_args(argv)
        application = cls(options)
        try:
            return application.run()
        except FlyInError as error:
            print(
                application.renderer.error(str(error)), file=sys.stderr
            )
            return EXIT_FAILURE
        except KeyboardInterrupt:
            application._warn("interrupted")
            return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(Application.main())

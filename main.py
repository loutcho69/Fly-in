"""Entry point of the Fly-in simulator.

Usage::

    python3 main.py maps/easy/01_linear_path.txt
    python3 main.py maps/hard/02_capacity_hell.txt --gui
    python3 main.py maps/medium/01_dead_end_trap.txt --quiet

The module does three things and nothing else: read the command line,
run the pipeline through :class:`~mission.Mission`, and turn any expected
failure into a clean message. Every piece of logic lives in its own
module, so this file stays short enough to read in one go.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional, Sequence

import colors
from errors import FlyInError
from mission import Mission, find_maps
from network import Network
from pathfinder import PathFinder
from renderer import Renderer

MAPS_DIRECTORY = "maps"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130


def build_argument_parser() -> argparse.ArgumentParser:
    """Describe the command line interface.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="fly-in",
        description="Route a fleet of drones across a delivery network.",
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
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="pause between two turns, to watch the fleet move",
    )
    return parser


def show(lines: Sequence[str]) -> None:
    """Print a block of lines.

    Args:
        lines: the lines to print.
    """
    for line in lines:
        print(line)


def report_dead_zones(network: Network, renderer: Renderer) -> None:
    """Warn about the zones no drone will ever be able to use.

    A zone is useless when it is blocked, unreachable from the start hub
    or unable to reach the end hub. Saying so is friendlier than letting
    the user wonder why a whole branch of the map stays empty.

    Args:
        network: the parsed network.
        renderer: the renderer used for the message.
    """
    unusable = PathFinder(network).unusable_zones()
    if unusable:
        listed = ", ".join(unusable)
        print(renderer.warning(f"unusable zone(s): {listed}"))


def open_viewer(mission: Mission, renderer: Renderer) -> None:
    """Open the graphical viewer, if the toolkit is available.

    ``tkinter`` ships with the standard library but some systems package
    it separately, and it needs a display. It is therefore imported here
    rather than at the top of the module, and a failure is only a
    warning: the mission has already been printed, so the program stays
    useful on a terminal-only machine.

    Args:
        mission: the mission to show when the window opens.
        renderer: the renderer used for the warning.
    """
    try:
        import viewer
    except ImportError:
        print(
            renderer.warning(
                "the graphical viewer needs tkinter, which is missing "
                "(macOS: brew install python-tk, "
                "Debian: sudo apt install python3-tk)"
            ),
            file=sys.stderr,
        )
        return
    catalogue = find_maps(MAPS_DIRECTORY)
    if mission.path not in catalogue:
        catalogue = [mission.path] + catalogue
    try:
        viewer.launch(mission, catalogue)
    except Exception as error:
        print(
            renderer.warning(f"the viewer could not open a window: {error}"),
            file=sys.stderr,
        )


def run(options: argparse.Namespace, renderer: Renderer) -> int:
    """Run the whole pipeline on one map.

    Args:
        options: the parsed command line.
        renderer: the renderer to print with.

    Returns:
        The exit code of the program.

    Raises:
        FlyInError: propagated to :func:`main`, which reports it.
    """
    mission = Mission.load(options.map)
    verbose = not options.quiet
    if verbose:
        show(renderer.summary(options.map, mission.network))
        report_dead_zones(mission.network, renderer)
        if not options.no_map:
            show(renderer.map_view(mission.network))
        show(renderer.plan(mission.plan))
        print(renderer.title("Flight log"))
    for turn in mission.result.turns:
        if verbose:
            print(renderer.turn(turn, mission.network))
        else:
            print(turn)
        if options.delay > 0:
            sys.stdout.flush()
            time.sleep(options.delay)
    if verbose:
        show(renderer.report(mission.metrics))
    if options.gui:
        open_viewer(mission, renderer)
    return EXIT_SUCCESS


def main(argv: Optional[List[str]] = None) -> int:
    """Program entry point.

    Args:
        argv: command line arguments, defaulting to ``sys.argv``.

    Returns:
        0 on success, 1 on an expected failure, 130 on an interrupt.
    """
    options = build_argument_parser().parse_args(argv)
    use_color = colors.supports_color() and not options.no_color
    renderer = Renderer(use_color)
    try:
        return run(options, renderer)
    except FlyInError as error:
        print(renderer.error(str(error)), file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print(renderer.warning("interrupted"), file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())

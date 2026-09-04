"""Everything the program prints.

Every escape code, every alignment and every wording lives here. No
other module writes to the terminal, which means the whole simulation
can be reused by a test, a web front end or a file exporter without
touching a line of logic.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from colors import BOLD, PALETTE, RESET
from metrics import Metrics
from network import Network
from router import RoutePlan
from simulator import SimulationResult, Turn
from zone import Zone, ZoneType

MAP_WIDTH = 76
MAP_HEIGHT = 19

TYPE_COLORS: Dict[ZoneType, str] = {
    ZoneType.NORMAL: "white",
    ZoneType.BLOCKED: "grey",
    ZoneType.RESTRICTED: "orange",
    ZoneType.PRIORITY: "green",
}

TYPE_MARKERS: Dict[ZoneType, str] = {
    ZoneType.NORMAL: "o",
    ZoneType.BLOCKED: "x",
    ZoneType.RESTRICTED: "~",
    ZoneType.PRIORITY: "*",
}

START_MARKER = "A"
END_MARKER = "Z"


class Renderer:
    """Format the objects of the project for a terminal."""

    def __init__(self, use_color: bool = True) -> None:
        """Create a renderer.

        Args:
            use_color: False to emit plain text, which is what happens
                when the output is piped or when ``--no-color`` is
                given.
        """
        self._use_color = use_color

    def paint(self, text: str, color: Optional[str]) -> str:
        """Colour a fragment of text if colours are enabled.

        Args:
            text: the fragment to colour.
            color: a colour name, or None to leave it alone.

        Returns:
            The decorated text.
        """
        return PALETTE.colorize(text, color, self._use_color)

    def emphasise(self, text: str) -> str:
        """Render a fragment in bold if colours are enabled.

        Args:
            text: the fragment to render in bold.

        Returns:
            The decorated text.
        """
        if not self._use_color:
            return text
        return f"{BOLD}{text}{RESET}"

    def title(self, text: str) -> str:
        """Render a section title underlined by dashes.

        Args:
            text: the title to render.

        Returns:
            The two lines to print.
        """
        return f"\n{self.emphasise(text)}\n{'-' * len(text)}"

    def error(self, message: str) -> str:
        """Render an error message.

        Args:
            message: the text to render.

        Returns:
            The line to print.
        """
        return self.paint(f"error: {message}", "red")

    def note(self, message: str) -> str:
        """Render an informative note.

        Used to tell the user that the graphical window is about to
        open and that the terminal stays busy until it is closed, which
        would otherwise look like the program hanging.

        Args:
            message: the text to render.

        Returns:
            The decorated line.
        """
        return self.paint(f"note: {message}", "cyan")

    def warning(self, message: str) -> str:
        """Render a warning message.

        Args:
            message: the text to render.

        Returns:
            The line to print.
        """
        return self.paint(f"warning: {message}", "yellow")

    def zone_color(self, zone: Zone) -> str:
        """Colour of a zone.

        The colour written in the map wins, unless this terminal has no
        code for it, in which case the colour of the zone type is used
        instead. A map is never rejected for naming an exotic colour.

        Args:
            zone: the zone to colour.

        Returns:
            The name of the colour to use.
        """
        chosen = zone.color
        if chosen is not None and PALETTE.knows(chosen):
            return chosen
        return TYPE_COLORS[zone.zone_type]

    def summary(self, path: str, network: Network) -> List[str]:
        """Describe the map that was loaded.

        Args:
            path: path of the map file.
            network: the parsed network.

        Returns:
            The lines to print.
        """
        return [
            self.title(f"Map {path}"),
            f"  drones     : {network.nb_drones}",
            f"  zones      : {len(network)}",
            f"  connections: {len(network.links)}",
            f"  start hub  : {self.paint(network.start.name, 'cyan')}",
            f"  end hub    : {self.paint(network.end.name, 'cyan')}",
        ]

    def legend(self) -> str:
        """One line explaining the markers of the ASCII map.

        Returns:
            The line to print.
        """
        parts = [
            f"{START_MARKER} start", f"{END_MARKER} end",
            f"{TYPE_MARKERS[ZoneType.NORMAL]} normal",
            f"{TYPE_MARKERS[ZoneType.PRIORITY]} priority",
            f"{TYPE_MARKERS[ZoneType.RESTRICTED]} restricted",
            f"{TYPE_MARKERS[ZoneType.BLOCKED]} blocked",
        ]
        return "  " + "   ".join(parts)

    def map_view(self, network: Network) -> List[str]:
        """Draw the zones on a character grid using their coordinates.

        The coordinates of a map are arbitrary integers, so they are
        rescaled to fit the terminal. The grid is never taller than the
        vertical spread of the map, which keeps a flat network flat
        instead of stretching it over twenty empty lines. When two zones
        land on the same spot the second one is pushed to a nearby free
        line, so every label stays readable.

        Args:
            network: the network to draw.

        Returns:
            The lines to print, legend included.
        """
        bounds = self._bounds(network)
        height = min(MAP_HEIGHT, max(1, bounds[3] - bounds[2] + 1))
        grid: List[List[Tuple[str, Optional[str]]]] = [
            [(" ", None) for _ in range(MAP_WIDTH)] for _ in range(height)
        ]
        for zone in network.zones:
            label = f"{self._marker(zone)}{zone.name}{self._badge(zone)}"
            column, row = self._project(zone, bounds, height)
            self._write(grid, label, column, row, self.zone_color(zone))
        lines = [self._render_row(row) for row in grid]
        return [self.title("Map view"), self.legend(), ""] + lines

    @staticmethod
    def _bounds(network: Network) -> Tuple[int, int, int, int]:
        """Bounding box of the map as ``(min x, max x, min y, max y)``.

        Args:
            network: the network to measure.

        Returns:
            The bounding box of its coordinates.
        """
        xs = [zone.x for zone in network.zones]
        ys = [zone.y for zone in network.zones]
        return min(xs), max(xs), min(ys), max(ys)

    @staticmethod
    def _badge(zone: Zone) -> str:
        """Capacity suffix written after a zone name on the map view.

        Only zones that hold more than one drone get one, so a plain
        map stays uncluttered while a bottleneck is visible.

        Args:
            zone: the zone to describe.

        Returns:
            A string such as ``(x3)``, or an empty string.
        """
        capacity = zone.capacity
        if capacity is None or capacity <= 1:
            return ""
        return f"(x{capacity})"

    @staticmethod
    def _marker(zone: Zone) -> str:
        """Character standing for a zone on the ASCII map.

        Args:
            zone: the zone to represent.

        Returns:
            The single character standing for it.
        """
        if zone.is_start:
            return START_MARKER
        if zone.is_end:
            return END_MARKER
        return TYPE_MARKERS[zone.zone_type]

    @staticmethod
    def _project(
        zone: Zone, bounds: Tuple[int, int, int, int], height: int
    ) -> Tuple[int, int]:
        """Rescale the coordinates of a zone to the character grid.

        Args:
            zone: the zone to place.
            bounds: bounding box of the map.
            height: number of rows of the grid.

        Returns:
            A ``(column, row)`` pair inside the grid.
        """
        min_x, max_x, min_y, max_y = bounds
        usable = MAP_WIDTH - 14
        column = 0
        if max_x > min_x:
            column = (zone.x - min_x) * usable // (max_x - min_x)
        row = 0
        if max_y > min_y:
            row = (zone.y - min_y) * (height - 1) // (max_y - min_y)
        return column, row

    @staticmethod
    def _write(
        grid: List[List[Tuple[str, Optional[str]]]],
        label: str,
        column: int,
        row: int,
        color: str,
    ) -> None:
        """Write a label on the grid, avoiding what is already there.

        A label too long for the grid is truncated, and a label that
        finds no free room grows the grid by one line rather than being
        dropped: a zone missing from the map view would be a silent lie
        about the network, which is worse than a slightly taller
        drawing.

        Args:
            grid: the character grid, modified in place; it may gain
                lines.
            label: the text to write.
            column: preferred column.
            row: preferred row.
            color: colour of the label.
        """
        width = len(grid[0])
        if len(label) > width:
            label = label[:width]
        column = max(0, min(column, width - len(label)))
        for offset in range(len(grid)):
            for candidate in (row + offset, row - offset):
                if not 0 <= candidate < len(grid):
                    continue
                if Renderer._fits(grid[candidate], label, column):
                    Renderer._stamp(grid[candidate], label, column, color)
                    return
        grid.append([(" ", None) for _ in range(width)])
        Renderer._stamp(grid[-1], label, column, color)

    @staticmethod
    def _fits(
        line: List[Tuple[str, Optional[str]]], label: str, column: int
    ) -> bool:
        """Tell whether a label can be written at a place, plus a blank.

        Args:
            line: the row of the grid to test.
            label: the text to write.
            column: where the text would start.

        Returns:
            True when every cell it would need is still empty.
        """
        return all(
            line[column + step][0] == " "
            for step in range(len(label) + 1)
            if column + step < len(line)
        )

    @staticmethod
    def _stamp(
        line: List[Tuple[str, Optional[str]]],
        label: str,
        column: int,
        color: str,
    ) -> None:
        """Write a label on a row of the grid.

        Args:
            line: the row to write on, modified in place.
            label: the text to write.
            column: where the text starts.
            color: colour of the label.
        """
        for step, character in enumerate(label):
            if column + step < len(line):
                line[column + step] = (character, color)

    def _render_row(self, row: List[Tuple[str, Optional[str]]]) -> str:
        """Turn one row of the grid into a printable string.

        Args:
            row: the cells of one row, as character and colour pairs.

        Returns:
            The printable line.
        """
        return "".join(
            self.paint(character, color) for character, color in row
        ).rstrip()

    def plan(self, plan: RoutePlan) -> List[str]:
        """Describe the routes chosen by the router.

        Args:
            plan: the plan to describe.

        Returns:
            The lines to print.
        """
        lines = [self.title("Flight plan")]
        for index, (route, count) in enumerate(
            zip(plan.routes, plan.counts), start=1
        ):
            names = " -> ".join(
                self.paint(zone.name, self.zone_color(zone))
                for zone in route.zones
            )
            lines.append(
                f"  route {index}: {count:>3} drone(s), "
                f"{route.travel_time:>3} turn(s)  {names}"
            )
        lines.append(f"  predicted duration: {plan.estimated_turns} turn(s)")
        return lines

    def turn(self, turn: Turn, network: Network) -> str:
        """Render one turn of the trace.

        The line holds the moves and nothing else, in the exact format
        required by the subject: ``D<ID>-<zone>`` entries separated by
        single spaces, or ``D<ID>-<connection>`` while a drone is still
        in flight. Only the colours are added, which the subject
        explicitly allows as the visual representation.

        Args:
            turn: the turn to render.
            network: the network, used to colour the zone names.

        Returns:
            The line to print.
        """
        parts = []
        for move in turn.moves:
            drone = self.emphasise(move.drone)
            if move.in_flight:
                location = self.paint(move.location, "grey")
            else:
                zone = network.zone(move.location)
                location = self.paint(move.location, self.zone_color(zone))
            parts.append(f"{drone}-{location}")
        return " ".join(parts)

    def zone_states(self, states: Dict[str, int], network: Network) -> str:
        """Render the occupancy of every busy zone at the end of a turn.

        This is the "zone states" half of the visual representation the
        subject asks for: which zone holds how many drones, out of how
        many it can hold. A zone shown in red is full.

        Args:
            states: number of drones per zone at the end of the turn.
            network: the network, used for the colours and capacities.

        Returns:
            The line to print, empty when no zone is occupied.
        """
        parts = []
        for name in sorted(states):
            count = states[name]
            if count <= 0:
                continue
            zone = network.zone(name)
            capacity = zone.capacity
            limit = "*" if capacity is None else str(capacity)
            full = capacity is not None and count >= capacity
            text = f"{name} {count}/{limit}"
            parts.append(self.paint(text, "red" if full else "grey"))
        if not parts:
            return ""
        return "        " + "  ".join(parts)

    def trace(
        self, result: SimulationResult, network: Network
    ) -> List[str]:
        """Render the whole trace.

        Args:
            result: the simulation to render.
            network: the network, used to colour the zone names.

        Returns:
            The lines to print.
        """
        lines = [self.title("Flight log")]
        for turn in result.turns:
            lines.append(self.turn(turn, network))
        return lines

    @staticmethod
    def _limit(metrics: Metrics, name: str) -> str:
        """Capacity of a zone, ``*`` when it has none.

        Args:
            metrics: the metrics holding the network.
            name: name of the zone.

        Returns:
            The capacity as text.
        """
        capacity = metrics.network.zone(name).capacity
        return "*" if capacity is None else str(capacity)

    def report(self, metrics: Metrics) -> List[str]:
        """Render the closing statistics.

        Args:
            metrics: the figures of the mission.

        Returns:
            The lines to print.
        """
        check = (
            self.paint("matches the prediction", "green")
            if metrics.prediction_matches
            else self.paint("DOES NOT match the prediction", "red")
        )
        busiest = ", ".join(
            f"{name} ({visits})" for name, visits in metrics.busiest_zones()
        )
        crowded = ", ".join(
            f"{name} {count}/{self._limit(metrics, name)}"
            for name, count in list(metrics.peak_occupancy().items())[:3]
        )
        return [
            self.title("Report"),
            f"  turns played   : {self.emphasise(str(metrics.total_turns))}"
            f"  ({check})",
            f"  moves          : {metrics.total_moves}"
            f"  ({metrics.moves_per_turn:.2f} drone(s) moved per turn)",
            f"  turns per drone: {metrics.turns_per_drone:.2f} on average",
            f"  total path cost: {metrics.total_path_cost} turn(s) "
            f"of flight, {metrics.idle_turns} lost waiting",
            f"  routes used    : {metrics.nb_routes}",
            f"  single route   : {metrics.single_route_turns} turn(s) "
            f"-> speedup x{metrics.speedup:.2f}",
            f"  busiest zones  : {busiest or 'none'}",
            f"  peak occupancy : {crowded or 'none'}",
        ]

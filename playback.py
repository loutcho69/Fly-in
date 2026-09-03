"""Turning a trace into animation frames and pixel positions.

This module holds every computation the graphical viewer needs, and
imports no graphical toolkit at all. Keeping it separate has two
benefits: the geometry can be tested in a terminal, on a machine
without a display, and a different front end could reuse it as is.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from network import Network
from simulator import SimulationResult

Point = Tuple[float, float]


PER_RING = 8


def spread(anchor: Point, rank: int, total: int, orbit: float) -> Point:
    """Place the ``rank``-th of ``total`` drones around a point.

    A lone drone sits on the point itself. A group is laid out on
    concentric rings of at most :data:`PER_RING` drones each, rather
    than on a single circle: twenty-five drones on one ring would
    overlap, which is exactly what happens on the start hub of the
    challenger map before the first take-off.

    Args:
        anchor: the point to spread around.
        rank: index of the drone inside its group.
        total: size of the group.
        orbit: radius of the first ring, in pixels.

    Returns:
        The position of that drone.
    """
    if total <= 1:
        return anchor
    ring = rank // PER_RING
    on_ring = min(PER_RING, total - ring * PER_RING)
    angle = 2 * math.pi * (rank % PER_RING) / on_ring + ring * 0.4
    radius = orbit * (1 + 0.55 * ring)
    return (
        anchor[0] + radius * math.cos(angle),
        anchor[1] + radius * math.sin(angle),
    )


def blend(start: Point, end: Point, ratio: float) -> Point:
    """Interpolate between two points.

    This is what turns the trace into a smooth animation: instead of
    teleporting from one zone to the next when the turn changes, a drone
    is drawn somewhere along the way, at the fraction ``ratio`` of its
    journey.

    Args:
        start: position at the beginning of the turn.
        end: position at the end of the turn.
        ratio: 0 gives ``start``, 1 gives ``end``.

    Returns:
        The intermediate position.
    """
    eased = ratio * ratio * (3 - 2 * ratio)
    return (
        start[0] + (end[0] - start[0]) * eased,
        start[1] + (end[1] - start[1]) * eased,
    )


class Playback:
    """The frames of a mission and the geometry needed to draw them."""

    def __init__(self, network: Network, result: SimulationResult) -> None:
        """Precompute every frame of the animation.

        Args:
            network: the map that was flown over.
            result: the trace to replay.
        """
        self._network = network
        self._result = result
        self._frames = self._build_frames()

    @property
    def frames(self) -> List[Dict[str, str]]:
        """One frame per turn, frame 0 being the initial state.

        A frame maps a drone name to the zone or the connection it
        stands on at the end of that turn.
        """
        return self._frames

    @property
    def length(self) -> int:
        """Number of turns, which is the number of frames minus one."""
        return len(self._frames) - 1

    def _build_frames(self) -> List[Dict[str, str]]:
        """Rebuild the position of every drone after every turn.

        The trace only lists the drones that moved, so a frame is the
        previous one updated with the moves of the turn.

        Returns:
            The list of frames, starting with the whole fleet on the
            start hub.
        """
        start = self._network.start.name
        current = {drone.name: start for drone in self._result.drones}
        frames = [dict(current)]
        for turn in self._result.turns:
            for move in turn.moves:
                current[move.drone] = move.location
            frames.append(dict(current))
        return frames

    def layout(
        self, width: int, height: int, margin: int
    ) -> Dict[str, Point]:
        """Map every zone to a pixel position on a canvas.

        The coordinates of a map are arbitrary integers, so they are
        rescaled to the canvas. A map whose zones share one coordinate
        stays on a single row or column instead of collapsing into a
        point.

        Args:
            width: width of the canvas in pixels.
            height: height of the canvas in pixels.
            margin: empty border to keep on every side.

        Returns:
            A dictionary mapping a zone name to its pixel position.
        """
        xs = [zone.x for zone in self._network.zones]
        ys = [zone.y for zone in self._network.zones]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        usable_width = width - 2 * margin
        usable_height = height - 2 * margin
        places: Dict[str, Point] = {}
        for zone in self._network.zones:
            if span_x:
                horizontal = margin + (
                    (zone.x - min(xs)) * usable_width / span_x
                )
            else:
                horizontal = width / 2
            if span_y:
                vertical = margin + (
                    (zone.y - min(ys)) * usable_height / span_y
                )
            else:
                vertical = height / 2
            places[zone.name] = (horizontal, vertical)
        return places

    @staticmethod
    def anchor(place: str, layout: Dict[str, Point]) -> Optional[Point]:
        """Position of a zone, or middle of a connection.

        A place holding a dash can only be a connection, since zone
        names may not contain one.

        Args:
            place: a zone name or a connection name.
            layout: the output of :meth:`layout`.

        Returns:
            The position, or None when the place cannot be resolved.
        """
        if place in layout:
            return layout[place]
        first, _, second = place.partition("-")
        if first in layout and second in layout:
            start = layout[first]
            end = layout[second]
            return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        return None

    def spots(
        self, index: int, layout: Dict[str, Point], orbit: float
    ) -> Dict[str, Point]:
        """Pixel position of every drone at a given frame.

        Drones sharing a place are spread around it so that none hides
        another, and a drone in transit sits on the middle of the
        connection it is crossing.

        Args:
            index: index of the frame.
            layout: the output of :meth:`layout`.
            orbit: radius of the first ring of a group.

        Returns:
            A dictionary mapping a drone name to its position.
        """
        grouped: Dict[str, List[str]] = {}
        for drone, place in self._frames[index].items():
            grouped.setdefault(place, []).append(drone)
        places: Dict[str, Point] = {}
        for place, names in grouped.items():
            anchor = self.anchor(place, layout)
            if anchor is None:
                continue
            names.sort(key=lambda name: int(name[1:]))
            for rank, name in enumerate(names):
                places[name] = spread(anchor, rank, len(names), orbit)
        return places

    def delivered(self, index: int) -> int:
        """Number of drones already on the end hub at a given frame.

        Args:
            index: index of the frame.

        Returns:
            How many drones are standing on the end hub.
        """
        end = self._network.end.name
        return sum(
            1 for place in self._frames[index].values() if place == end
        )

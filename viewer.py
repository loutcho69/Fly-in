"""Graphical viewer: browse the maps and watch the drones fly.

The subject accepts a colored terminal output *or* a graphical
interface; this module provides the second one, so the project offers
both. It relies on :mod:`tkinter`, which ships with the standard
library, so no dependency is added and no graph library is involved:
the drawing is plain circles and lines on a canvas.

The window has two halves. On the left, the list of the maps found in
``maps/``: picking one solves it and loads it straight away. On the
right, the network drawn at the real coordinates of its zones, with the
fleet moving turn by turn.

Every computation is done elsewhere: :class:`~mission.Mission` runs the
pipeline and :class:`~playback.Playback` turns a trace into frames and
pixel positions. This module only draws and reacts to clicks.
"""

from __future__ import annotations

import math
import os
import tkinter as tk
from typing import Dict, List, Sequence, Tuple

import colors
from errors import FlyInError
from mission import Mission
from network import Network
from playback import Playback, blend
from zone import Zone, ZoneType

CANVAS_WIDTH = 860
CANVAS_HEIGHT = 560
MARGIN = 60
ZONE_RADIUS = 18
DRONE_BODY = 6
DRONE_ARM = 8
DRONE_ROTOR = 4.5
DRONE_ORBIT = 30
SIDEBAR_WIDTH = 30

BACKGROUND = "#14161a"
PANEL = "#1c1f26"
LINK_COLOR = "#3d444d"
LINK_ACTIVE = "#f0c000"
TEXT_COLOR = "#e9ecef"
DIM_TEXT = "#868e96"
ALERT_TEXT = "#ff8787"
DRONE_COLOR = "#ffffff"
DRONE_TEXT = "#14161a"
DRONE_FRAME = "#0b0d10"
ROTOR_COLOR = "#74c0fc"

TYPE_FILL: Dict[ZoneType, str] = {
    ZoneType.NORMAL: "#495057",
    ZoneType.BLOCKED: "#2b2f36",
    ZoneType.RESTRICTED: "#f76707",
    ZoneType.PRIORITY: "#2f9e44",
}

TYPE_MARK: Dict[ZoneType, str] = {
    ZoneType.NORMAL: "",
    ZoneType.BLOCKED: "x",
    ZoneType.RESTRICTED: "~",
    ZoneType.PRIORITY: "*",
}

START_OUTLINE = "#2f9e44"
END_OUTLINE = "#e03131"
DEFAULT_PERIOD_MS = 600
REFRESH_MS = 40
ROTOR_SPEED = 1.1


class Viewer:
    """A tkinter window browsing maps and replaying missions."""

    def __init__(self, mission: Mission, catalogue: Sequence[str]) -> None:
        """Build the window on a first, already solved mission.

        Args:
            mission: the mission to show when the window opens.
            catalogue: paths of the maps offered in the browser.
        """
        self._mission = mission
        self._catalogue = list(catalogue)
        self._index = 0
        self._progress = 0.0
        self._phase = 0.0
        self._playing = False
        self._stop_at_turn = False
        self._alive = True
        self._period = DEFAULT_PERIOD_MS
        self._root = tk.Tk()
        self._root.title("Fly-in")
        self._root.configure(bg=BACKGROUND)
        self._status = tk.StringVar()
        self._headline = tk.StringVar()
        self._play_label = tk.StringVar(value="Play")
        self._canvas = self._build_layout()
        self._playback = Playback(mission.network, mission.result)
        self._positions = self._playback.layout(
            CANVAS_WIDTH, CANVAS_HEIGHT, MARGIN
        )
        self._select_current()
        self._bind_keys()
        self._root.protocol("WM_DELETE_WINDOW", self._close)
        self._draw_scene()
        self._animate()

    def run(self) -> None:
        """Open the window and hand control to tkinter."""
        self._root.mainloop()

    def _build_layout(self) -> tk.Canvas:
        """Create the sidebar, the canvas and the controls.

        Returns:
            The canvas the network is drawn on.
        """
        frame = tk.Frame(self._root, bg=BACKGROUND)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._build_sidebar(frame)
        right = tk.Frame(frame, bg=BACKGROUND)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            right, textvariable=self._headline, bg=BACKGROUND,
            fg=TEXT_COLOR, anchor="w", font=("TkDefaultFont", 12, "bold"),
        ).pack(fill=tk.X, pady=(0, 6))
        canvas = tk.Canvas(
            right, width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
            bg=BACKGROUND, highlightthickness=0,
        )
        canvas.pack()
        self._build_controls(right)
        return canvas

    def _build_sidebar(self, parent: tk.Frame) -> None:
        """Create the list of maps.

        Args:
            parent: the frame the sidebar is packed into.
        """
        panel = tk.Frame(parent, bg=PANEL)
        panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        tk.Label(
            panel, text="Maps", bg=PANEL, fg=TEXT_COLOR,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 4))
        self._listbox = tk.Listbox(
            panel, width=SIDEBAR_WIDTH, height=22, bg=PANEL,
            fg=TEXT_COLOR, selectbackground="#1971c2",
            highlightthickness=0, borderwidth=0, activestyle="none",
            font=("TkFixedFont", 10),
        )
        self._listbox.pack(fill=tk.Y, expand=True, padx=10, pady=(0, 10))
        for path in self._catalogue:
            self._listbox.insert(tk.END, self._short(path))
        self._listbox.bind("<<ListboxSelect>>", self._on_pick)

    def _build_controls(self, parent: tk.Frame) -> None:
        """Create the buttons, the speed slider and the status line.

        Args:
            parent: the frame the controls are packed into.
        """
        bar = tk.Frame(parent, bg=BACKGROUND)
        bar.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            bar, textvariable=self._play_label, width=8,
            command=self._toggle,
        ).pack(side=tk.LEFT)
        tk.Button(
            bar, text="Step", width=6, command=self._step,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            bar, text="Reset", width=6, command=self._reset,
        ).pack(side=tk.LEFT)
        tk.Label(
            bar, textvariable=self._status, bg=BACKGROUND, fg=TEXT_COLOR,
            font=("TkDefaultFont", 11),
        ).pack(side=tk.LEFT, padx=14)
        scale = tk.Scale(
            bar, from_=100, to=1500, resolution=50, orient=tk.HORIZONTAL,
            label="ms per turn", bg=BACKGROUND, fg=DIM_TEXT,
            highlightthickness=0, length=180, command=self._set_period,
        )
        scale.set(DEFAULT_PERIOD_MS)
        scale.pack(side=tk.RIGHT)

    def _bind_keys(self) -> None:
        """Add the keyboard shortcuts: space, right arrow, escape."""
        self._root.bind("<space>", lambda _event: self._toggle())
        self._root.bind("<Right>", lambda _event: self._step())
        self._root.bind("<Escape>", lambda _event: self._root.destroy())

    @staticmethod
    def _short(path: str) -> str:
        """Shorten a map path for the sidebar.

        Args:
            path: the path of a map file.

        Returns:
            The path without its top directory and its extension.
        """
        trimmed = os.path.splitext(path)[0]
        parts = trimmed.split(os.sep)
        return os.sep.join(parts[1:]) if len(parts) > 1 else trimmed

    def _select_current(self) -> None:
        """Highlight the map currently shown, if it is in the list."""
        if self._mission.path not in self._catalogue:
            return
        position = self._catalogue.index(self._mission.path)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(position)
        self._listbox.activate(position)
        self._listbox.see(position)

    def _on_pick(self, _event: "tk.Event[tk.Listbox]") -> None:
        """Load the map the user just clicked on.

        A map that cannot be solved is reported in the status line and
        the previous mission stays on screen, so a misclick never closes
        the window.

        Args:
            _event: the tkinter event, unused.
        """
        position = self._listbox.index(tk.ACTIVE)
        if not 0 <= position < len(self._catalogue):
            return
        path = self._catalogue[position]
        if path == self._mission.path:
            return
        try:
            mission = Mission.load(path)
        except FlyInError as error:
            self._playing = False
            self._play_label.set("Play")
            self._status.set(f"{os.path.basename(path)}: {error}")
            return
        self._mission = mission
        self._playback = Playback(mission.network, mission.result)
        self._positions = self._playback.layout(
            CANVAS_WIDTH, CANVAS_HEIGHT, MARGIN
        )
        self._reset()

    def _set_period(self, value: str) -> None:
        """Change the delay between two turns.

        Args:
            value: the slider value, given by tkinter as a string.
        """
        self._period = int(float(value))

    def _toggle(self) -> None:
        """Start or stop the playback, rewinding when it is finished."""
        if self._finished():
            self._index = 0
            self._progress = 0.0
            self._draw_scene()
        self._stop_at_turn = False
        self._playing = not self._playing
        self._play_label.set("Pause" if self._playing else "Play")

    def _step(self) -> None:
        """Play exactly one more turn, then stop.

        The turn is animated like any other: the drones glide to their
        next zone instead of jumping there, which is the whole point of
        stepping through a bottleneck.
        """
        if self._finished():
            return
        self._stop_at_turn = True
        self._playing = True
        self._play_label.set("Pause")

    def _reset(self) -> None:
        """Go back to the first frame and stop the playback."""
        self._playing = False
        self._stop_at_turn = False
        self._play_label.set("Play")
        self._index = 0
        self._progress = 0.0
        self._draw_scene()
        self._draw_drones()

    def _finished(self) -> bool:
        """True once the last turn has been played."""
        return self._index >= self._playback.length

    def _close(self) -> None:
        """Stop the animation loop and close the window."""
        self._alive = False
        self._root.destroy()

    def _animate(self) -> None:
        """Advance the animation by one refresh and schedule the next.

        The loop runs even while the playback is paused, so the rotors
        keep spinning and the window never looks frozen. Only the drones
        are redrawn on each refresh; the network itself is redrawn once
        per turn, which keeps the whole thing cheap.
        """
        if not self._alive:
            return
        self._phase += ROTOR_SPEED
        if self._playing:
            self._progress += REFRESH_MS / max(self._period, REFRESH_MS)
            while self._progress >= 1.0:
                self._progress -= 1.0
                self._index += 1
                self._draw_scene()
                if self._stop_at_turn or self._finished():
                    self._stop_at_turn = False
                    self._playing = False
                    self._play_label.set("Play")
                    self._progress = 0.0
                    break
        self._draw_drones()
        self._root.after(REFRESH_MS, self._animate)

    def _draw_scene(self) -> None:
        """Redraw the network for the current turn.

        Only called when the turn changes: the links that light up and
        the zones do not move within a turn, so there is no reason to
        rebuild them forty times a second.
        """
        self._canvas.delete("scene")
        frame = self._playback.frames[self._index]
        self._draw_links(frame)
        self._draw_zones()
        self._update_labels()

    def _draw_links(self, frame: Dict[str, str]) -> None:
        """Draw the connections, lighting up the ones being flown over.

        Args:
            frame: the positions of the drones for this turn.
        """
        busy = {place for place in frame.values() if "-" in place}
        for link in self._network.links:
            first = self._positions[link.first.name]
            second = self._positions[link.second.name]
            active = link.name in busy
            self._canvas.create_line(
                first[0], first[1], second[0], second[1],
                fill=LINK_ACTIVE if active else LINK_COLOR,
                width=3 if active else 2, tags="scene",
            )

    def _draw_zones(self) -> None:
        """Draw every zone as a labelled disc."""
        offsets = self._label_offsets()
        for zone in self._network.zones:
            horizontal, vertical = self._positions[zone.name]
            radius = ZONE_RADIUS + (6 if zone.is_terminal else 0)
            self._canvas.create_oval(
                horizontal - radius, vertical - radius,
                horizontal + radius, vertical + radius,
                fill=self._fill(zone), outline=self._outline(zone),
                width=3 if zone.is_terminal else 1, tags="scene",
            )
            self._canvas.create_text(
                horizontal, vertical + radius + offsets[zone.name],
                text=self._caption(zone), fill=DIM_TEXT,
                font=("TkDefaultFont", 8), tags="scene",
            )

    def _label_offsets(self) -> Dict[str, float]:
        """Choose how far below each zone its label is written.

        On a dense map several zones share a row and their labels would
        overlap, so the labels of neighbouring zones are written on three
        alternating levels.

        Returns:
            A dictionary mapping a zone name to a vertical offset.
        """
        rows: Dict[int, List[str]] = {}
        for zone in self._network.zones:
            row = round(self._positions[zone.name][1] / 20)
            rows.setdefault(row, []).append(zone.name)
        offsets: Dict[str, float] = {}
        for names in rows.values():
            names.sort(key=lambda name: self._positions[name][0])
            for index, name in enumerate(names):
                offsets[name] = 12 + 13 * (index % 3)
        return offsets

    @staticmethod
    def _fill(zone: Zone) -> str:
        """Colour of the disc of a zone."""
        chosen = colors.hex_code(zone.color)
        if chosen is not None:
            return chosen
        return TYPE_FILL[zone.zone_type]

    @staticmethod
    def _outline(zone: Zone) -> str:
        """Outline of the disc: hubs and blocked zones stand out."""
        if zone.is_start:
            return START_OUTLINE
        if zone.is_end or not zone.is_accessible:
            return END_OUTLINE
        return "#000000"

    @staticmethod
    def _caption(zone: Zone) -> str:
        """Label written under a zone.

        The type and the capacity are abbreviated to single symbols,
        because a dense map has no room for full words: ``~`` marks a
        restricted zone, ``*`` a priority one, ``x`` a blocked one, and
        ``xN`` a capacity larger than one.
        """
        marks = TYPE_MARK[zone.zone_type]
        capacity = zone.capacity
        if capacity is not None and capacity > 1:
            marks += f" x{capacity}"
        return f"{zone.name} {marks}".strip()

    def _draw_drones(self) -> None:
        """Draw the fleet at its current, possibly intermediate, place.

        Each drone is drawn between where it stood at the beginning of
        the turn and where it will stand at the end of it, so the fleet
        glides instead of teleporting. A drone that does not move stays
        put, and one crossing towards a ``restricted`` zone drifts to
        the middle of the connection during the first turn, then onto
        the zone during the second one.
        """
        self._canvas.delete("drone")
        current = self._playback.spots(
            self._index, self._positions, DRONE_ORBIT
        )
        nxt = self._playback.spots(
            min(self._index + 1, self._playback.length),
            self._positions,
            DRONE_ORBIT,
        )
        for rank, (name, spot) in enumerate(sorted(current.items())):
            target = nxt.get(name, spot)
            self._draw_drone(
                blend(spot, target, self._progress),
                name[1:],
                self._phase + rank * 0.7,
            )

    def _draw_drone(
        self, spot: Tuple[float, float], label: str, phase: float
    ) -> None:
        """Draw one quadcopter: a body, four arms and four rotors.

        The rotors are short blades rotating with ``phase``, which is
        what makes a paused window still look alive and a moving drone
        read as flying rather than sliding.

        Args:
            spot: where to draw the drone.
            label: the number written on its body.
            phase: rotation angle of the blades, in radians.
        """
        left, top = spot
        blade = (
            DRONE_ROTOR * math.cos(phase),
            DRONE_ROTOR * math.sin(phase),
        )
        for way_x, way_y in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            arm_x = left + way_x * DRONE_ARM
            arm_y = top + way_y * DRONE_ARM
            self._canvas.create_line(
                left, top, arm_x, arm_y,
                fill=DRONE_FRAME, width=2, tags="drone",
            )
            self._canvas.create_oval(
                arm_x - DRONE_ROTOR, arm_y - DRONE_ROTOR,
                arm_x + DRONE_ROTOR, arm_y + DRONE_ROTOR,
                outline=ROTOR_COLOR, tags="drone",
            )
            self._canvas.create_line(
                arm_x - blade[0], arm_y - blade[1],
                arm_x + blade[0], arm_y + blade[1],
                fill=ROTOR_COLOR, width=2, tags="drone",
            )
        self._canvas.create_oval(
            left - DRONE_BODY, top - DRONE_BODY,
            left + DRONE_BODY, top + DRONE_BODY,
            fill=DRONE_COLOR, outline=DRONE_FRAME, tags="drone",
        )
        self._canvas.create_text(
            left, top, text=label, fill=DRONE_TEXT,
            font=("TkDefaultFont", 7, "bold"), tags="drone",
        )

    @property
    def _network(self) -> Network:
        """The network of the mission currently shown."""
        return self._mission.network

    def _update_labels(self) -> None:
        """Refresh the title and the status line."""
        metrics = self._mission.metrics
        self._headline.set(
            f"{self._mission.name}   "
            f"{self._network.nb_drones} drones   "
            f"{len(self._network)} zones   "
            f"{metrics.nb_routes} lane(s)   "
            f"{metrics.total_turns} turns"
        )
        self._status.set(
            f"turn {self._index} / {self._playback.length}    "
            f"delivered {self._playback.delivered(self._index)}"
            f" / {self._network.nb_drones}"
        )


def launch(mission: Mission, catalogue: Sequence[str]) -> None:
    """Open the graphical viewer.

    Args:
        mission: the mission shown when the window opens.
        catalogue: paths of the maps offered in the browser.
    """
    Viewer(mission, catalogue).run()

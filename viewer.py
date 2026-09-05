"""Graphical viewer: an arcade-style front end for the simulator.

The subject accepts a colored terminal output *or* a graphical
interface; this module provides the second one, so the project offers
both. It relies on :mod:`tkinter`, which ships with the standard
library, so no dependency is added and no graph library is involved:
the drawing is plain circles, lines and text on a canvas.

The window has three screens, in the order an arcade cabinet would use
them. The **title** screen waits for a start. The **level select**
screen lays the maps out as numbered tiles, one row per directory of
``maps/``, walkable with the arrow keys. The **mission** screen draws
the network at the real coordinates of its zones and plays the fleet
turn by turn, forwards or backwards.

Every computation is done elsewhere: :class:`~mission.Mission` runs the
pipeline and :class:`~playback.Playback` turns a trace into frames and
pixel positions. This module only draws and reacts to the player.
"""

from __future__ import annotations

import math
import os
import tkinter as tk
from typing import Callable, Dict, List, Sequence, Tuple

from colors import PALETTE
from errors import FlyInError
from map_parser import MapParser
from mission import Mission
from network import Network
from playback import Geometry, Playback
from zone import Zone, ZoneType

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 540
MARGIN = 60
ZONE_RADIUS = 18
DRONE_BODY = 6
DRONE_ARM = 8
DRONE_ROTOR = 4.5
DRONE_ORBIT = 30

TITLE_WIDTH = 940
TITLE_HEIGHT = 420
BOARD_WIDTH = 940
BOARD_HEIGHT = 430
TILE_WIDTH = 20
TILES_PER_ROW = 4

BACKGROUND = "#0b0d13"
PANEL = "#141824"
CARD = "#1b2030"
CARD_ACTIVE = "#242c42"
ACCENT = "#4dabf7"
NEON = "#22d3ee"
NEON_SHADOW = "#c026d3"
LINK_COLOR = "#3d444d"
LINK_ACTIVE = "#f0c000"
TEXT_COLOR = "#e9ecef"
DIM_TEXT = "#7b8494"
ALERT_TEXT = "#ff8787"
DRONE_COLOR = "#ffffff"
DRONE_TEXT = "#14161a"
DRONE_FRAME = "#0b0d10"
ROTOR_COLOR = "#74c0fc"

ARCADE = "Courier"

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

FAMILY_ORDER = ("easy", "medium", "hard", "challenger", "custom")

FAMILY_COLORS: Dict[str, str] = {
    "easy": "#51cf66",
    "medium": "#fcc419",
    "hard": "#ff922b",
    "challenger": "#ff6b6b",
    "custom": "#4dabf7",
}

START_OUTLINE = "#2f9e44"
END_OUTLINE = "#e03131"
DEFAULT_PERIOD_MS = 600
REFRESH_MS = 40
ROTOR_SPEED = 1.1
BLINK_MS = 500
FORWARD = 1
BACKWARD = -1

TITLE_SCREEN = "title"
SELECT_SCREEN = "select"
MISSION_SCREEN = "mission"


class MapCard:
    """One entry of the level select: a map, described without solving.

    Only the parser runs here. Solving twenty maps to build a menu would
    make the window slow to open, while reading them is instant and
    already gives the two numbers a player wants before choosing.
    """

    def __init__(self, path: str) -> None:
        """Read a map and keep what the level select displays.

        Args:
            path: path of the map file.
        """
        self._path = path
        self._family = self._family_of(path)
        self._title = self._title_of(path)
        try:
            network = MapParser(path).parse()
            self._detail = (
                f"{network.nb_drones} DRONES  {len(network)} ZONES"
            )
            self._readable = True
        except FlyInError:
            self._detail = "UNREADABLE"
            self._readable = False

    @property
    def path(self) -> str:
        """Path of the map file."""
        return self._path

    @property
    def family(self) -> str:
        """Name of the directory holding the map, its difficulty."""
        return self._family

    @property
    def title(self) -> str:
        """Readable title of the map."""
        return self._title

    @property
    def detail(self) -> str:
        """Second line of the tile: fleet and network size."""
        return self._detail

    @property
    def readable(self) -> bool:
        """False when the map could not even be parsed."""
        return self._readable

    @staticmethod
    def _family_of(path: str) -> str:
        """Difficulty of a map, taken from its parent directory.

        Any directory dropped into ``maps/`` becomes a row of its own,
        named after the folder, so a reviewer can add a batch of
        evaluation maps without touching the code.

        Args:
            path: path of the map file.

        Returns:
            The name of the parent directory, or ``maps`` at the root.
        """
        parent = os.path.basename(os.path.dirname(path))
        return parent or "maps"

    @staticmethod
    def _title_of(path: str) -> str:
        """Turn a file name into a readable title.

        ``01_linear_path.txt`` becomes ``LINEAR PATH``: the numbering
        that orders the files on disk becomes the tile number instead.

        Args:
            path: path of the map file.

        Returns:
            The title to print on the tile.
        """
        stem = os.path.splitext(os.path.basename(path))[0]
        parts = stem.split("_")
        if parts and parts[0].isdigit():
            parts = parts[1:]
        return (" ".join(parts) or stem).upper()


class Viewer:
    """A tkinter window: title, level select, then the mission."""

    def __init__(self, mission: Mission, catalogue: Sequence[str]) -> None:
        """Build the three screens on an already solved mission.

        Args:
            mission: the mission the command line asked for, offered as
                the first highlighted level.
            catalogue: paths of the maps offered in the level select.
        """
        self._mission = mission
        self._cards = self._ordered(
            [MapCard(path) for path in catalogue]
        )
        self._playback = Playback(mission.network, mission.result)
        self._positions = self._playback.layout(
            CANVAS_WIDTH, CANVAS_HEIGHT, MARGIN
        )
        self._index = 0
        self._progress = 0.0
        self._phase = 0.0
        self._blink = 0
        self._playing = False
        self._direction = FORWARD
        self._stop_at_turn = False
        self._alive = True
        self._period = DEFAULT_PERIOD_MS
        self._screen = TITLE_SCREEN
        self._cursor = self._cards.index(
            next(
                (card for card in self._cards
                 if card.path == mission.path),
                self._cards[0],
            )
        ) if self._cards else 0
        self._tiles: List[tk.Frame] = []
        self._rows: List[List[int]] = []
        self._root = tk.Tk()
        self._root.title("Fly-in")
        self._root.configure(bg=BACKGROUND)
        self._status = tk.StringVar()
        self._headline = tk.StringVar()
        self._select_status = tk.StringVar()
        self._play_label = tk.StringVar(value="PLAY")
        self._start_prompt = tk.StringVar(value="")
        self._title_screen = self._build_title()
        self._select_screen, self._board = self._build_select()
        self._fill_board()
        self._mission_screen, self._canvas = self._build_mission()
        self._bind_keys()
        self._root.protocol("WM_DELETE_WINDOW", self._close)
        self._show(TITLE_SCREEN)
        self._animate()

    def run(self) -> None:
        """Open the window and hand control to tkinter."""
        self._root.mainloop()

    @property
    def _network(self) -> Network:
        """The network of the mission currently loaded."""
        return self._mission.network

    def _build_title(self) -> tk.Frame:
        """Build the title screen.

        Returns:
            The frame holding it.
        """
        frame = tk.Frame(self._root, bg=BACKGROUND)
        canvas = tk.Canvas(
            frame, width=TITLE_WIDTH, height=TITLE_HEIGHT,
            bg=BACKGROUND, highlightthickness=0,
        )
        canvas.pack()
        middle = TITLE_WIDTH // 2
        for offset, color in ((4, NEON_SHADOW), (-3, ACCENT), (0, NEON)):
            canvas.create_text(
                middle + offset, 150 + offset // 2, text="FLY-IN",
                fill=color, font=(ARCADE, 72, "bold"),
            )
        canvas.create_text(
            middle, 215, text="D R O N E   R O U T I N G",
            fill=TEXT_COLOR, font=(ARCADE, 16, "bold"),
        )
        canvas.create_line(
            middle - 220, 240, middle + 220, 240, fill=PANEL, width=2,
        )
        canvas.create_text(
            middle, 268,
            text="move every drone home in as few turns as possible",
            fill=DIM_TEXT, font=(ARCADE, 11),
        )
        tk.Label(
            frame, textvariable=self._start_prompt, bg=BACKGROUND,
            fg=NEON, font=(ARCADE, 20, "bold"),
        ).pack(pady=(4, 8))
        tk.Button(
            frame, text="START", width=14, relief=tk.FLAT, bg=CARD,
            fg=NEON, activebackground=CARD_ACTIVE, activeforeground=NEON,
            font=(ARCADE, 14, "bold"), command=self._enter_select,
        ).pack(pady=(0, 10))
        tk.Label(
            frame, text="ENTER  START      ESC  QUIT", bg=BACKGROUND,
            fg=DIM_TEXT, font=(ARCADE, 10),
        ).pack(pady=(0, 24))
        return frame

    def _build_select(self) -> Tuple[tk.Frame, tk.Frame]:
        """Build the level select screen and its scrollable board.

        Returns:
            The frame holding the screen, and the inner frame the rows
            are gridded into.
        """
        frame = tk.Frame(self._root, bg=BACKGROUND)
        tk.Label(
            frame, text="SELECT LEVEL", bg=BACKGROUND, fg=NEON,
            font=(ARCADE, 22, "bold"),
        ).pack(pady=(22, 2))
        tk.Label(
            frame, text="arrows move      enter launches      esc back",
            bg=BACKGROUND, fg=DIM_TEXT, font=(ARCADE, 10),
        ).pack(pady=(0, 14))
        holder = tk.Frame(frame, bg=BACKGROUND)
        holder.pack(fill=tk.BOTH, expand=True, padx=20)
        canvas = tk.Canvas(
            holder, bg=BACKGROUND, highlightthickness=0,
            width=BOARD_WIDTH, height=BOARD_HEIGHT,
        )
        bar = tk.Scrollbar(
            holder, orient=tk.VERTICAL, command=canvas.yview,
        )
        board = tk.Frame(canvas, bg=BACKGROUND)
        canvas.create_window((0, 0), window=board, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        board.bind(
            "<Configure>",
            lambda _event: canvas.configure(
                scrollregion=canvas.bbox("all")
            ),
        )
        self._select_canvas = canvas
        tk.Label(
            frame, textvariable=self._select_status, bg=BACKGROUND,
            fg=ALERT_TEXT, font=(ARCADE, 10),
        ).pack(pady=(10, 18))
        return frame, board

    def _fill_board(self) -> None:
        """Lay the levels out, one row per family, and index them.

        A family holding more tiles than a row can show is continued on
        the next line: a level that never appears would be a level the
        player cannot reach.
        """
        line = 0
        position = 0
        for family, cards in self._grouped():
            row: List[int] = []
            for chunk in range(0, len(cards), TILES_PER_ROW):
                strip = cards[chunk:chunk + TILES_PER_ROW]
                label = family.upper() if chunk == 0 else ""
                self._build_row(line, label, family, strip, position)
                row.extend(range(position, position + len(strip)))
                position += len(strip)
                line += 1
            self._rows.append(row)
        self._highlight()

    def _build_row(
        self, line: int, label: str, family: str,
        cards: List[MapCard], first: int,
    ) -> None:
        """Build one line of the level select.

        Args:
            line: index of the line in the board.
            label: heading shown on the left, empty on a continuation.
            family: name of the family, used for the colour.
            cards: the levels of that line.
            first: index of the first card, in the flat order.
        """
        strip = tk.Frame(self._board, bg=BACKGROUND)
        strip.grid(row=line, column=0, sticky="w", pady=(0, 12))
        tk.Label(
            strip, text=label or "", width=11, anchor="w", bg=BACKGROUND,
            fg=FAMILY_COLORS.get(family, ACCENT),
            font=(ARCADE, 12, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 10))
        for step, card in enumerate(cards):
            self._tiles.append(
                self._build_tile(strip, card, first + step)
            )

    def _build_tile(
        self, strip: tk.Frame, card: MapCard, position: int
    ) -> tk.Frame:
        """Build one level tile.

        Args:
            strip: the line the tile belongs to.
            card: the map the tile stands for.
            position: index of the tile in the flat order.

        Returns:
            The frame of the tile, kept to highlight it later.
        """
        tile = tk.Frame(
            strip, bg=CARD, highlightthickness=2,
            highlightbackground=CARD, width=190, height=64,
        )
        tile.pack(side=tk.LEFT, padx=5)
        tile.pack_propagate(False)
        number = tk.Label(
            tile, text=f"{position + 1:02d}", bg=CARD,
            fg=FAMILY_COLORS.get(card.family, ACCENT),
            font=(ARCADE, 15, "bold"),
        )
        number.pack(side=tk.LEFT, padx=(10, 8))
        body = tk.Frame(tile, bg=CARD)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        title = tk.Label(
            body, text=card.title[:TILE_WIDTH], bg=CARD, anchor="w",
            fg=TEXT_COLOR if card.readable else DIM_TEXT,
            font=(ARCADE, 10, "bold"),
        )
        title.pack(anchor="w", pady=(12, 0))
        detail = tk.Label(
            body, text=card.detail, bg=CARD, fg=DIM_TEXT, anchor="w",
            font=(ARCADE, 9),
        )
        detail.pack(anchor="w")
        for widget in (tile, number, body, title, detail):
            widget.bind("<Button-1>", self._picker(position))
            widget.bind("<Enter>", self._hoverer(position))
        return tile

    def _picker(self, position: int) -> Callable[["tk.Event[tk.Misc]"], None]:
        """Build the click handler of one tile.

        Args:
            position: index of the tile in the flat order.

        Returns:
            The function bound to the mouse button.
        """
        def pick(_event: "tk.Event[tk.Misc]") -> None:
            """Select this level and launch it.

            Args:
                _event: the tkinter event, unused.
            """
            self._cursor = position
            self._highlight()
            self._launch()

        return pick

    def _hoverer(self, position: int) -> Callable[["tk.Event[tk.Misc]"], None]:
        """Build the hover handler of one tile.

        Args:
            position: index of the tile in the flat order.

        Returns:
            The function bound to the pointer entering the tile.
        """
        def hover(_event: "tk.Event[tk.Misc]") -> None:
            """Move the selection under the pointer.

            Args:
                _event: the tkinter event, unused.
            """
            self._cursor = position
            self._highlight()

        return hover

    def _highlight(self) -> None:
        """Repaint the tiles so that only the selected one stands out."""
        for position, tile in enumerate(self._tiles):
            chosen = position == self._cursor
            background = CARD_ACTIVE if chosen else CARD
            tile.configure(
                bg=background,
                highlightbackground=NEON if chosen else CARD,
            )
            self._repaint(tile, background)

    def _repaint(self, widget: tk.Misc, background: str) -> None:
        """Give a widget and its children the same background.

        The children of a tile are labels and frames, all of which take
        a ``bg`` option, but the type stubs only promise the options
        common to every widget; the assignment form is used instead of
        ``configure`` so the code stays checkable.

        Args:
            widget: the widget to repaint.
            background: the colour to apply.
        """
        for child in widget.winfo_children():
            child["bg"] = background
            self._repaint(child, background)

    @classmethod
    def _ordered(cls, cards: List[MapCard]) -> List[MapCard]:
        """Sort the cards the way the board lays them out.

        The tiles are built family by family while the catalogue comes
        sorted by path, so the two orders would disagree and the cursor
        would highlight the wrong level. Sorting the cards once, here,
        keeps ``_cards[i]`` and ``_tiles[i]`` the same level for good.

        Args:
            cards: the cards, in catalogue order.

        Returns:
            The cards, in board order.
        """
        ordered: List[MapCard] = []
        for _, group in cls._group(cards):
            ordered.extend(group)
        return ordered

    @staticmethod
    def _group(
        cards: List[MapCard],
    ) -> List[Tuple[str, List[MapCard]]]:
        """Group cards by family, known difficulties first.

        Args:
            cards: the cards to group.

        Returns:
            Pairs ``(family, cards)``, easy first and unknown families
            last, so the board reads as a difficulty ladder.
        """
        families: Dict[str, List[MapCard]] = {}
        for card in cards:
            families.setdefault(card.family, []).append(card)
        known = [
            (name, families.pop(name))
            for name in FAMILY_ORDER
            if name in families
        ]
        return known + sorted(families.items())

    def _grouped(self) -> List[Tuple[str, List[MapCard]]]:
        """Group the cards by family, in the order of the subject.

        Returns:
            Pairs ``(family, cards)``, in board order.
        """
        return self._group(self._cards)

    def _build_mission(self) -> Tuple[tk.Frame, tk.Canvas]:
        """Build the mission screen: the network and its controls.

        Returns:
            The frame holding the screen, and the canvas to draw on.
        """
        frame = tk.Frame(self._root, bg=BACKGROUND)
        top = tk.Frame(frame, bg=BACKGROUND)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))
        tk.Button(
            top, text="\u25c0 LEVELS", width=10, relief=tk.FLAT, bg=CARD,
            fg=NEON, activebackground=CARD_ACTIVE, activeforeground=NEON,
            font=(ARCADE, 10, "bold"),
            command=self._enter_select,
        ).pack(side=tk.LEFT)
        tk.Label(
            top, textvariable=self._headline, bg=BACKGROUND,
            fg=TEXT_COLOR, font=(ARCADE, 12, "bold"),
        ).pack(side=tk.LEFT, padx=16)
        canvas = tk.Canvas(
            frame, width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
            bg=BACKGROUND, highlightthickness=0,
        )
        canvas.pack(padx=12)
        self._build_controls(frame)
        return frame, canvas

    def _build_controls(self, parent: tk.Frame) -> None:
        """Build the transport bar under the canvas.

        Args:
            parent: the frame the bar is packed into.
        """
        bar = tk.Frame(parent, bg=BACKGROUND)
        bar.pack(fill=tk.X, padx=12, pady=(8, 4))
        for text, action in (
            ("\u25c0\u25c0", self._reset),
            ("\u25c0", self._step_back),
        ):
            self._transport(bar, text, action, 4)
        tk.Button(
            bar, textvariable=self._play_label, width=8, relief=tk.FLAT,
            bg=CARD, fg=NEON, activebackground=CARD_ACTIVE,
            activeforeground=NEON, font=(ARCADE, 11, "bold"),
            command=self._toggle,
        ).pack(side=tk.LEFT, padx=2)
        self._transport(bar, "\u25b6", self._step_forward, 4)
        tk.Label(
            bar, textvariable=self._status, bg=BACKGROUND, fg=TEXT_COLOR,
            font=(ARCADE, 11),
        ).pack(side=tk.LEFT, padx=14)
        scale = tk.Scale(
            bar, from_=100, to=1500, resolution=50, orient=tk.HORIZONTAL,
            label="ms per turn", bg=BACKGROUND, fg=DIM_TEXT,
            troughcolor=PANEL, highlightthickness=0, length=170,
            font=(ARCADE, 8), command=self._set_period,
        )
        scale.set(DEFAULT_PERIOD_MS)
        scale.pack(side=tk.RIGHT)
        tk.Label(
            parent,
            text="\u2190 \u2192 STEP     SPACE PLAY/PAUSE     ESC BACK",
            bg=BACKGROUND, fg=DIM_TEXT, font=(ARCADE, 9),
        ).pack(pady=(0, 12))

    @staticmethod
    def _transport(
        bar: tk.Frame, text: str, action: Callable[[], None], width: int
    ) -> None:
        """Add one button to the transport bar.

        Args:
            bar: the bar the button belongs to.
            text: the glyph written on it.
            action: what it does when pressed.
            width: width of the button, in characters.
        """
        tk.Button(
            bar, text=text, width=width, relief=tk.FLAT, bg=CARD,
            fg=TEXT_COLOR, activebackground=CARD_ACTIVE,
            activeforeground=TEXT_COLOR, font=(ARCADE, 11, "bold"),
            command=action,
        ).pack(side=tk.LEFT, padx=2)

    def _bind_keys(self) -> None:
        """Bind the keyboard, dispatching on the visible screen."""
        self._root.bind("<Left>", lambda _event: self._on_arrow(-1, 0))
        self._root.bind("<Right>", lambda _event: self._on_arrow(1, 0))
        self._root.bind("<Up>", lambda _event: self._on_arrow(0, -1))
        self._root.bind("<Down>", lambda _event: self._on_arrow(0, 1))
        self._root.bind("<Return>", lambda _event: self._on_enter())
        self._root.bind("<space>", lambda _event: self._on_space())
        self._root.bind("<Escape>", lambda _event: self._on_escape())

    def _on_arrow(self, sideways: int, vertical: int) -> None:
        """React to an arrow key on whichever screen is visible.

        On the level select the arrows walk the tiles; on the mission
        screen the horizontal ones step through the trace, backwards as
        well as forwards.

        Args:
            sideways: -1 for left, 1 for right, 0 otherwise.
            vertical: -1 for up, 1 for down, 0 otherwise.
        """
        if self._screen == SELECT_SCREEN:
            self._move_cursor(sideways, vertical)
        elif self._screen == MISSION_SCREEN and sideways:
            self._single_step(FORWARD if sideways > 0 else BACKWARD)

    def _move_cursor(self, sideways: int, vertical: int) -> None:
        """Move the level selection.

        Args:
            sideways: -1 for left, 1 for right, 0 otherwise.
            vertical: -1 for up, 1 for down, 0 otherwise.
        """
        if not self._tiles:
            return
        if sideways:
            self._cursor = (self._cursor + sideways) % len(self._tiles)
        elif vertical:
            self._cursor = self._jump(vertical)
        self._highlight()
        self._reveal()

    def _jump(self, vertical: int) -> int:
        """Find the tile one family up or down from the current one.

        Args:
            vertical: -1 for up, 1 for down.

        Returns:
            The index of the tile to select.
        """
        for number, row in enumerate(self._rows):
            if self._cursor in row:
                target = (number + vertical) % len(self._rows)
                place = min(row.index(self._cursor),
                            len(self._rows[target]) - 1)
                return self._rows[target][place]
        return self._cursor

    def _reveal(self) -> None:
        """Scroll the board so that the selected tile stays visible."""
        tile = self._tiles[self._cursor]
        height = max(self._board.winfo_height(), 1)
        top = max(0.0, (tile.winfo_y() - 40) / height)
        self._select_canvas.yview_moveto(min(top, 1.0))

    def _on_enter(self) -> None:
        """React to the enter key: start, or launch the level."""
        if self._screen == TITLE_SCREEN:
            self._enter_select()
        elif self._screen == SELECT_SCREEN:
            self._launch()

    def _on_space(self) -> None:
        """Space bar: play or pause, on the mission screen."""
        if self._screen == MISSION_SCREEN:
            self._toggle()
        elif self._screen == TITLE_SCREEN:
            self._enter_select()

    def _on_escape(self) -> None:
        """Escape: one screen back, or quit from the title."""
        if self._screen == TITLE_SCREEN:
            self._close()
        elif self._screen == SELECT_SCREEN:
            self._show(TITLE_SCREEN)
        else:
            self._enter_select()

    def _show(self, screen: str) -> None:
        """Display one of the three screens.

        Args:
            screen: the screen to show.
        """
        self._playing = False
        self._play_label.set("PLAY")
        for name, frame in (
            (TITLE_SCREEN, self._title_screen),
            (SELECT_SCREEN, self._select_screen),
            (MISSION_SCREEN, self._mission_screen),
        ):
            if name == screen:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()
        self._screen = screen

    def _enter_select(self) -> None:
        """Leave the title or the mission for the level select."""
        self._show(SELECT_SCREEN)
        self._highlight()

    def _launch(self) -> None:
        """Solve the selected level and switch to the mission screen.

        A map that cannot be solved is reported under the board and the
        level select stays open, so a misclick never loses anything.
        """
        if not self._cards:
            return
        card = self._cards[self._cursor]
        if card.path != self._mission.path:
            try:
                mission = Mission.load(card.path)
            except FlyInError as error:
                self._select_status.set(f"{card.title}: {error}")
                return
            self._mission = mission
            self._playback = Playback(mission.network, mission.result)
            self._positions = self._playback.layout(
                CANVAS_WIDTH, CANVAS_HEIGHT, MARGIN
            )
        self._select_status.set("")
        self._show(MISSION_SCREEN)
        self._reset()

    def _set_period(self, value: str) -> None:
        """Change the delay between two turns.

        Args:
            value: the slider value, given by tkinter as a string.
        """
        self._period = int(float(value))

    def _toggle(self) -> None:
        """Play or pause, rewinding when the trace is finished."""
        if self._playing:
            self._playing = False
            self._play_label.set("PLAY")
            return
        if self._index >= self._playback.length:
            self._index = 0
            self._progress = 0.0
            self._draw_scene()
        self._direction = FORWARD
        self._stop_at_turn = False
        self._playing = True
        self._play_label.set("PAUSE")

    def _step_forward(self) -> None:
        """Play exactly one more turn, then stop."""
        self._single_step(FORWARD)

    def _step_back(self) -> None:
        """Rewind exactly one turn, then stop."""
        self._single_step(BACKWARD)

    def _single_step(self, direction: int) -> None:
        """Move one turn in a direction and stop there.

        The two directions are not symmetrical. A drone is always drawn
        between the frame of ``_index`` and the next one, at the
        fraction ``_progress`` of the way, so playing a turn forwards
        means running that fraction from 0 to 1 while the index stands
        still. Rewinding the same turn means running it from 1 back to
        0 *after* stepping the index back, which is what this method
        sets up. Doing it the other way round, letting the clock cross
        the boundary on its own, collapsed the whole rewind into the
        first refresh and the drones jumped instead of gliding.

        Args:
            direction: ``FORWARD`` or ``BACKWARD``.
        """
        if direction == FORWARD:
            if self._index >= self._playback.length:
                return
        else:
            if not self._rewind_one():
                return
        self._direction = direction
        self._stop_at_turn = True
        self._playing = True
        self._play_label.set("PAUSE")

    def _rewind_one(self) -> bool:
        """Place the playhead at the end of the previous turn.

        Returns:
            False when there is no previous turn to rewind into, in
            which case nothing was changed.
        """
        if self._progress > 0.0:
            return True
        if self._index <= 0:
            return False
        self._index -= 1
        self._progress = 1.0
        self._draw_scene()
        return True

    def _advance_clock(self) -> None:
        """Move the playhead by one refresh, in the current direction."""
        step = REFRESH_MS / max(self._period, REFRESH_MS)
        self._progress += self._direction * step
        if self._direction == FORWARD:
            self._clock_forward()
        else:
            self._clock_backward()

    def _clock_forward(self) -> None:
        """Handle the playhead running past the end of a turn."""
        while self._progress >= 1.0:
            self._progress -= 1.0
            self._index += 1
            self._draw_scene()
            if self._stop_at_turn or self._index >= self._playback.length:
                self._index = min(self._index, self._playback.length)
                self._progress = 0.0
                self._halt()
                return

    def _clock_backward(self) -> None:
        """Handle the playhead running back past the start of a turn.

        Stopping happens when the fraction reaches zero, not when a
        boundary is crossed: that is the point the drones are back on
        the zones they started the turn from.
        """
        while self._progress <= 0.0:
            self._progress = 0.0
            if self._stop_at_turn or not self._rewind_more():
                self._halt()
                return

    def _rewind_more(self) -> bool:
        """Step one more turn back during a continuous rewind.

        Returns:
            False once the first turn is reached.
        """
        if self._index <= 0:
            return False
        self._index -= 1
        self._progress = 1.0
        self._draw_scene()
        return True

    def _halt(self) -> None:
        """Stop the playback and release the single-step request."""
        self._stop_at_turn = False
        self._playing = False
        self._play_label.set("PLAY")

    def _reset(self) -> None:
        """Go back to the first turn and stop."""
        self._playing = False
        self._stop_at_turn = False
        self._play_label.set("PLAY")
        self._index = 0
        self._progress = 0.0
        self._draw_scene()
        self._draw_drones()

    def _close(self) -> None:
        """Stop the animation loop and close the window."""
        self._alive = False
        self._root.destroy()

    def _animate(self) -> None:
        """Advance the animation by one refresh and schedule the next.

        The loop runs on every screen: it spins the rotors of the drones
        on the mission screen and blinks the prompt on the title screen,
        so the window never looks frozen. Only the drones are redrawn on
        each refresh; the network itself is redrawn once per turn, which
        keeps the whole thing cheap.
        """
        if not self._alive:
            return
        self._phase += ROTOR_SPEED
        self._blink += REFRESH_MS
        if self._screen == TITLE_SCREEN:
            lit = (self._blink // BLINK_MS) % 2 == 0
            self._start_prompt.set("\u25b6 PRESS START" if lit else "")
        elif self._screen == MISSION_SCREEN:
            if self._playing:
                self._advance_clock()
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
        """Colour of the disc of a zone.

        Args:
            zone: the zone to paint.

        Returns:
            The RGB code of its disc.
        """
        chosen = PALETTE.rgb(zone.color)
        if chosen is not None:
            return chosen
        return TYPE_FILL[zone.zone_type]

    @staticmethod
    def _outline(zone: Zone) -> str:
        """Outline of the disc: hubs and blocked zones stand out.

        Args:
            zone: the zone to paint.

        Returns:
            The RGB code of its outline.
        """
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

        Args:
            zone: the zone to label.

        Returns:
            The text written under its disc.
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
                Geometry.blend(spot, target, self._progress),
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

    def _update_labels(self) -> None:
        """Refresh the title and the status line."""
        metrics = self._mission.metrics
        self._headline.set(
            f"{self._mission.name}   "
            f"{self._network.nb_drones} DRONES   "
            f"{len(self._network)} ZONES   "
            f"{metrics.nb_routes} LANE(S)   "
            f"{metrics.total_turns} TURNS"
        )
        self._status.set(
            f"TURN {self._index} / {self._playback.length}    "
            f"HOME {self._playback.delivered(self._index)}"
            f" / {self._network.nb_drones}"
        )

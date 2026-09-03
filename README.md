*This project has been created as part of the 42 curriculum by \<login1\>.*

# Fly-in

## Description

Fly-in routes a fleet of drones from a start hub to an end hub across a
network of zones, in as few simulation turns as possible, while
respecting the capacity of every zone and of every connection.

The map is a graph: zones are the nodes, connections are the
bidirectional edges. Zones have a type that changes what entering them
costs (`normal`, `priority`, `restricted`, `blocked`) and a maximum
occupancy; connections have a maximum number of drones that may cross
them at the same time. The program reads such a map, computes a routing
plan, plays the mission turn by turn and prints the resulting flight
log.

The project is written in Python 3.10+ and uses **no third party
library**: the graph, the shortest path search, the flow solver, the
scheduler and the terminal renderer are all part of the code, as the
subject requires. `flake8` and `mypy` are only needed by the `lint`
rules. Everything is object-oriented and fully type annotated.

## Instructions

```sh
make install                                  # flake8 and mypy, in .venv
make run                                      # graphical viewer + log
make run MAP=maps/hard/02_capacity_hell.txt   # opens on that map
make log                                      # terminal output only
make test                                     # replay + fuzz the solver
make lint                                     # flake8 + mypy
make lint-strict                              # flake8 + mypy --strict
make debug                                    # runs under pdb
make clean                                    # remove caches
```

`make` on its own runs `make run`, which opens the graphical viewer and
prints the flight log at the same time. The viewer lists every map of
`maps/` in a sidebar, so one window is enough to browse them all;
`make log` gives the terminal output alone, and the program falls back
to it automatically when no display or no `tkinter` is available. The simulator needs nothing but the
standard library; `install` only fetches the two linters, and it puts
them in a local virtual environment because recent Python distributions
refuse a system-wide `pip install` (PEP 668). `setup.cfg` keeps that
environment out of the reach of `flake8 .` and `mypy .`.

Direct invocation:

```
python3 main.py MAP [--gui] [--quiet] [--no-map] [--no-color]
                   [--delay SECONDS]
```

| Option | Effect |
| --- | --- |
| `--gui` | open the graphical viewer once the log is printed |

| `--quiet` | print only the flight log, in the exact format of the subject |
| `--no-map` | skip the ASCII view of the network |
| `--no-color` | plain text output |
| `--delay S` | pause between two turns, to watch the fleet move |

The graphical viewer uses `tkinter`, which belongs to the standard
library but is packaged separately on some distributions. When it is
missing the program says so and keeps working without it, so `--gui` is
never a hard requirement:

```
$ python3 main.py maps/easy/02_simple_fork.txt --gui
error: the graphical viewer needs tkinter, which is missing
(on Debian or Ubuntu: sudo apt install python3-tk)
```

Exit codes: `0` success, `1` invalid map or unsolvable network, `130`
interrupted. No unhandled exception can reach the user: every expected
failure is an exception deriving from `FlyInError`, caught in one place
in `main.py`.

## Example input and expected output

Input, `maps/medium/03_priority_puzzle.txt`:

```
nb_drones: 5

start_hub: start 0 0 [color=green]
hub: slow_path1 1 -1 [zone=restricted color=red]
hub: slow_path2 2 -1 [color=red]
hub: fast_junction 1 0 [zone=priority color=blue max_drones=2]
hub: fast_path 2 0 [zone=priority color=blue]
hub: merge_point 3 0 [color=yellow max_drones=3]
end_hub: goal 4 0 [color=green]

connection: start-slow_path1
connection: start-fast_junction
connection: slow_path1-slow_path2
connection: slow_path2-merge_point
connection: fast_junction-fast_path
connection: fast_path-merge_point
connection: merge_point-goal [max_link_capacity=2]
```

Output of `python3 main.py maps/medium/03_priority_puzzle.txt --quiet`,
which is the format defined by the subject: one line per turn, moves
separated by spaces, `D<ID>-<zone>`, or `D<ID>-<connection>` while a
drone is still in flight towards a `restricted` zone.

```
D1-fast_junction D2-start-slow_path1
D1-fast_path D2-slow_path1 D3-fast_junction D4-start-slow_path1
D1-merge_point D2-slow_path2 D3-fast_path D4-slow_path1 D5-fast_junction
D1-goal D2-merge_point D3-merge_point D4-slow_path2 D5-fast_path
D2-goal D3-goal D4-merge_point D5-merge_point
D4-goal D5-goal
```

Without `--quiet` the same run also prints the map summary, the ASCII
view, the flight plan and a report:

```
Flight plan
-----------
  route 1:   3 drone(s),   4 turn(s)  start -> fast_junction -> fast_path -> merge_point -> goal
  route 2:   2 drone(s),   5 turn(s)  start -> slow_path1 -> slow_path2 -> merge_point -> goal
  predicted duration: 6 turn(s)

Report
------
  turns played   : 6  (matches the prediction)
  moves          : 22
  routes used    : 2
  single route   : 8 turn(s) -> speedup x1.33
  waiting turns  : 4
  busiest zones  : goal (5), merge_point (5), fast_junction (3)
```

## Map format

Blank lines are ignored and everything after a `#` is a comment.

* `nb_drones: <positive integer>` must be the first instruction.
* Exactly one `start_hub:` and one `end_hub:`, plus any number of
  `hub:`, each written `<name> <x> <y> [metadata]`.
* `connection: <name>-<name> [metadata]` links two already declared
  zones. The same pair may not be declared twice in either order.
* Zone names may hold any character except spaces, dashes and the
  symbols that delimit metadata (`[`, `]`, `=`, `,`, `#`).
* Coordinates are integers, used by the display only.

| Key | Where | Values | Default |
| --- | --- | --- | --- |
| `zone` | zones | `normal`, `priority`, `restricted`, `blocked` | `normal` |
| `color` | zones | any single word | none |
| `max_drones` | zones | positive integer, ignored on the two hubs | `1` |
| `max_link_capacity` | connections | positive integer | `1` |

| Zone type | Entering costs | Notes |
| --- | --- | --- |
| `normal` | 1 turn | |
| `priority` | 1 turn | preferred when two routes take the same time |
| `restricted` | 2 turns | one turn on the connection, then the landing |
| `blocked` | never | no drone may enter or cross |

Any deviation stops the program with the line and the cause:

```
$ python3 main.py maps/invalid/bad_type.map
error: line 4: invalid zone type 'lava' (expected one of: normal, blocked, restricted, priority)
  >>> hub: a 1 1 [zone=lava]
```

## Technical choices: architecture

Every source file sits at the root of the repository; `maps/` only holds
data.

| File | Responsibility |
| --- | --- |
| `errors.py` | exception hierarchy, one base class for the whole project |
| `colors.py` | ANSI palette, shared by the parser and the renderer |
| `zone.py` | `ZoneType` and `Zone`: the nodes and their rules |
| `link.py` | `Link`: the bidirectional connections |
| `network.py` | the graph, its adjacency and its global validation |
| `map_parser.py` | strict reading of a map file |
| `path.py` | `Path`: an ordered route and its duration |
| `pathfinder.py` | Dijkstra weighted by the entry cost of the zones |
| `flow.py` | minimum cost flow: several simultaneous routes |
| `router.py` | how many drones on which route, and when they take off |
| `drone.py` | the state machine of one drone |
| `simulator.py` | the turn by turn engine |
| `metrics.py` | statistics of a finished mission |
| `renderer.py` | every line the program prints |
| `mission.py` | the pipeline as one object, shared by both front ends |
| `playback.py` | animation frames and canvas geometry, toolkit free |
| `viewer.py` | the graphical viewer, built on `tkinter` |
| `main.py` | command line and error reporting |
| `check.py` | independent referee and random map fuzzer |

The graph, the paths and the plan are **immutable**; the drones are the
only objects carrying a mutable state, and the simulator is the only
module that changes them. The renderer is the only module that prints.
That separation is what lets the checker replay a whole mission without
touching the engine.

## Technical choices: algorithms

**1. Parsing.** One pass over the file, one specialised method per
instruction. Syntax errors carry a line number; semantic errors detected
by the graph itself (duplicate name, second start hub) are caught and
re-raised with that line number attached.

**2. Shortest route.** The cost of a route is a number of *turns*, not a
number of connections, because entering a `restricted` zone costs 2. A
breadth-first search would therefore return wrong answers; Dijkstra is
used instead, with a distance made of a pair `(turns, preference)`
compared lexicographically. The second component counts the zones that
are not `priority`, so priority zones win ties without ever falsifying
the turn count. Complexity: `O(E log V)`.

**3. Several simultaneous routes.** Sending the whole fleet down the
fastest route is pointless when that route is narrow, so a *set* of
routes is needed. Choosing them greedily — take the fastest, ban its
zones, start again — is not enough. On

```
s-A, A-B, B-e, s-C, C-B, A-D, D-e
```

the greedy method finds one route where two exist, because reaching the
second one means *undoing* the use of the connection `A-B`. That is
exactly what the residual arcs of a flow algorithm do, so the problem is
modelled as a minimum cost flow:

* every zone is split into `v_in -> v_out`, one arc carrying the
  capacity of the zone (`max_drones`) and the cost of entering it, which
  is how a capacity sitting on a *node* becomes an arc capacity;
* every connection becomes two arcs, one per direction, carrying
  `max_link_capacity`;
* a `blocked` zone is simply a zone whose arc has a capacity of zero, so
  it needs no special case anywhere else.

The flow grows one unit at a time and is decomposed after each
augmentation, which yields the best set of 1 route, then of 2 routes,
and so on. Augmenting paths are found with SPFA rather than Dijkstra,
because residual arcs carry negative costs. Complexity: `O(F * V * E)`,
where `F` is the number of lanes, itself bounded by the number of
drones.

**4. Spreading the fleet.** A lane swallows one drone per turn, so a
route of duration `t` carrying `n` drones ends at turn `t + n - 1`, and
the mission ends with the slowest lane. Minimising that is done by
binary search: if the mission lasts `T` turns, a route of duration `t`
can deliver `T - t + 1` drones, a quantity that grows with `T`. Every
route set produced in step 3 is evaluated this way and the fastest wins,
which is what makes the program ignore an extra slow route when the
fleet is small. The router also fixes *when* each drone takes off, so
its output is a schedule, not merely an allocation.

**Caching.** Routes are computed once, before the simulation starts, and
never recomputed: the schedule is fixed and each turn only reads it.
Memory is linear in the size of the graph plus the number of drones.

**5. Simulation.** The engine plays the schedule and enforces the rules
again. Every drone that has left the start hub advances on every turn,
because the subject forbids a drone to wait on a connection while
heading for a `restricted` zone. Only drones still standing on the start
hub, which has no capacity limit, can be delayed. At the end of each
turn every zone and every connection is checked against its capacity, so
an infeasible plan is rejected instead of printed.

## Visual representation

The program offers **both** forms the subject mentions: a colored
terminal output, and a graphical interface.

### Terminal

Four parts.

* **A map view.** The zones are drawn on a character grid at their real
  coordinates, rescaled to the terminal, each with a marker for its role
  (`A` start, `Z` end, `*` priority, `~` restricted, `x` blocked) and
  its colour. Labels that would collide are pushed to a nearby free line
  so none is ever overwritten. Seeing the topology before the log is
  what makes the flight plan readable at a glance.
* **A flight plan**, listing each route with its length, its duration
  and the number of drones it carries, so a reader can predict the log
  before reading it.
* **A colored flight log.** Every zone name is printed in the colour
  given in the map, or in the colour of its type when the map gives
  none, so a `restricted` detour or a `priority` lane stands out
  immediately. Drones in transit are dimmed and show a connection name
  instead of a zone name, which makes two turn movements obvious.
  `--delay` replays the log one turn at a time, turning the trace into
  an animation.
* **A report** with the secondary metrics the subject mentions: number
  of moves, routes used, waiting turns, busiest zones, and the speedup
  against the naive single-route solution.

Colours are disabled automatically when the output is redirected, and by
`--no-color` or the `NO_COLOR` environment variable, so a piped log
stays readable. `--quiet` prints the bare format required by the subject
and nothing else.

### Graphical viewer

`--gui` opens a window that replays the mission on the real topology,
with **a sidebar listing every map of `maps/`**: clicking one solves it
and loads it immediately, so a reviewer can walk through the easy,
medium, hard and challenger maps without ever touching the command
line. A map that cannot be solved is reported in the status line and the
previous one stays on screen, so a misclick never closes the window.
Zones are discs placed at their map coordinates and painted with the
colour the map gives them, or with the colour of their type when it
gives none; the two hubs are larger and outlined, and a label recalls
the type and the capacity (`~` restricted, `*` priority, `x` blocked,
`xN` capacity). Labels of neighbouring zones alternate between three
levels so that a dense map stays readable.

Drones are drawn as small quadcopters — a body carrying its number,
four arms and four rotors whose blades keep spinning — and they **glide
from zone to zone** instead of jumping: the window refreshes every 40 ms
and each drone is drawn between where it stood at the start of the turn
and where it will stand at the end of it, on a smoothed trajectory.
Watching *which* drone moves and *where* it goes needs no effort, and a
drone that has to wait is obvious because it is the one standing still.

A group sharing a zone is laid out on concentric rings around it, so
nothing is hidden even on the start hub of the challenger map where
twenty-five drones wait together. A drone crossing towards a
`restricted` zone drifts to the middle of the connection during the
first turn and onto the zone during the second, while the connection
lights up: two turn movements become visible rather than merely
readable.

The window has Play, Step and Reset buttons, a speed slider and the
shortcuts space, right arrow and escape, plus a header giving the map
name, the fleet size, the number of lanes and the total number of turns,
and a status line giving the current turn and how many drones are
already delivered. Stepping through a bottleneck
one turn at a time is the fastest way to see *why* a map costs what it
costs, which is exactly what the terminal log cannot show.

Only the drones are redrawn on each refresh; the network is rebuilt
once per turn. On the heaviest map, 62 zones and 25 drones, a refresh
costs about 3 ms out of a 40 ms budget.

The animation itself is computed in `playback.py`, which imports no
toolkit: frames are rebuilt from the trace, positions are rescaled to
the canvas, and `viewer.py` only draws them. That split is what allows
the geometry to be tested on a machine with no display.

## Performance

| Map | Drones | Target | Ours | Lower bound |
| --- | --- | --- | --- | --- |
| easy/01_linear_path | 2 | <= 6 | **4** | 4 |
| easy/02_simple_fork | 4 | <= 8 | **4** | 4 |
| easy/03_basic_capacity | 4 | <= 6 | **4** | 4 |
| medium/01_dead_end_trap | 5 | <= 12 | **8** | 8 |
| medium/02_circular_loop | 6 | <= 15 | **10** | 10 |
| medium/03_priority_puzzle | 5 | <= 12 | **6** | 6 |
| hard/01_maze_nightmare | 8 | <= 30 | **13** | 13 |
| hard/02_capacity_hell | 12 | <= 35 | **16** | 16 |
| hard/03_ultimate_challenge | 15 | <= 45 | **26** | 26 |
| challenger/01_the_impossible_dream | 25 | 45 (record) | **43** | 43 |

The lower bound is `d_min + ceil(n / k) - 1`, where `d_min` is the
duration of the fastest route and `k` is the maximum number of lanes the
network can host at once, that is the value of the maximum flow. No
schedule can beat it, and the program reaches it on every provided map,
so these results are not merely good, they are optimal.

Several hard maps are solved with a single lane. That is not a weakness
of the solver: they chain zones declared `max_drones=1`, so their
maximum flow really is 1 and no second lane exists. The reference record
for "The Impossible Dream" is 45 turns; this implementation delivers the
25 drones in **43**.

## Testing

`make test` runs `check.py`, which does three things.

It **replays** each trace against the map with code that shares nothing
with the simulator, checking that no drone moves twice in a turn, that
every move follows an existing connection, that a two turn move is used
if and only if the destination is `restricted`, that a drone in flight
lands on the very next turn, that no zone and no connection is ever over
capacity, and that the whole fleet reaches the end hub.

It checks that every map of `maps/invalid/` **is** rejected: a parser
that accepts everything is as wrong as one that accepts nothing.

It then **fuzzes** hundreds of random maps mixing blocked, restricted
and priority zones with random capacities, and verifies that the
duration predicted by the router equals the duration the simulator
measures. Those two numbers come from independent computations, so any
mismatch is a bug. This is how three real bugs were found during
development: a drone landing and taking off in the same turn, a
departure towards a `restricted` zone refused one turn too early, and a
lane injecting two drones at once and clogging a narrow segment further
down.

```
$ make test
  01_the_impossible_dream.txt   25 drones   1 route(s)   43 turns
  ...
  invalid maps: 6 correctly rejected
  fuzzing: 504 solvable random maps validated
all checks passed
```

## Resources

* Cormen, Leiserson, Rivest, Stein, *Introduction to Algorithms* —
  chapters on Dijkstra's algorithm, maximum flow and minimum cost flow.
* Ahuja, Magnanti, Orlin, *Network Flows: Theory, Algorithms and
  Applications* — node splitting, successive shortest paths and flow
  decomposition.
* The SPFA (Shortest Path Faster Algorithm) variant of Bellman-Ford,
  used because residual arcs carry negative costs.
* Python documentation: `heapq`, `collections.deque`, `argparse`,
  `typing`, `enum`.
* PEP 257 and the Google docstring style guide.
* `flake8` and `mypy` documentation.

### Use of AI

An AI assistant was used during this project, for the following tasks:

* discussing how to model `max_drones` — a capacity carried by a node —
  as a flow problem, which led to the node splitting used in `flow.py`;
* reviewing the code and the docstrings for clarity and consistency;
* generating the random map fuzzer in `check.py`.

The generated material was read, questioned and reworked; the three bugs
listed in the Testing section were found by testing rather than accepted
on trust. Every algorithm, design decision and line of the final code is
understood and owned by the author, who can explain, modify and extend
any part of it.

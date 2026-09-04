*This project has been created as part of the 42 curriculum by lobroue.*

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
make states                                   # log plus zone occupancy
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
python3 main.py MAP [--gui] [--quiet] [--zones] [--no-map] [--no-color]
                   [--delay SECONDS]
```

| Option | Effect |
| --- | --- |
| `--gui` | open the graphical viewer once the log is printed |

| `--quiet` | print only the flight log, in the exact format of the subject |
| `--zones` | show the state of every zone after each turn |
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
  moves          : 22  (3.67 drone(s) moved per turn)
  turns per drone: 5.20 on average
  total path cost: 22 turn(s) of flight, 4 lost waiting
  routes used    : 2
  single route   : 8 turn(s) -> speedup x1.33
  busiest zones  : goal (5), merge_point (5), fast_junction (3)
  peak occupancy : goal 2/*, merge_point 2/3, fast_junction 1/2
```

## Map format

Blank lines are ignored and everything after a `#` is a comment.

* `nb_drones: <positive integer>` must be the first instruction.
* Exactly one `start_hub:` and one `end_hub:`, plus any number of
  `hub:`, each written `<name> <x> <y> [metadata]`.
* `connection: <name>-<name> [metadata]` links two already declared
  zones. The same pair may not be declared twice in either order.
* Zone names may hold any character except spaces and dashes, exactly as
  the subject states. Brackets, colons and hashes are accepted: a `#`
  only opens a comment at the start of a line or after a blank, and a
  metadata block has to close at the end of the line, so the grammar
  stays unambiguous.
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

**Known limitation.** A minimum cost flow minimises the *sum* of the
lane durations, while the mission time depends on the *longest* lane, so
in theory a route set of equal total cost but better balance could be
missed. Evaluating every width from 1 to the maximum flow removes the
common cases, since a single lane is always the true shortest route.
The point was checked rather than assumed: on 86 small graphs the
optimum was computed by exhaustively enumerating every set of
vertex-disjoint paths, and the router matched it every time.

**Caching.** Routes are computed once, before the simulation starts, and
never recomputed: the schedule is fixed and each turn only reads it.
Memory is linear in the size of the graph plus the number of drones.

**Large fleets.** The fleet is kept in three groups: waiting in a lane
queue, in the air, delivered. A turn only touches the head of each lane
queue and the drones currently flying, so its cost is the number of
drones in the air, not the size of the fleet. A hundred thousand drones
queueing behind a single corridor are simulated in about 3 seconds,
against 18 seconds for ten thousand before that change.

**5. Simulation.** The engine plays the schedule and enforces the rules
again. Drones already on their way are handled from the closest to the
end hub to the furthest, which is what makes "a drone moving out frees
the zone for the same turn" work without a two phase update. A drone in
transit towards a `restricted` zone always lands, because the subject
forbids it to wait on a connection; any other drone stays where it is
when the next zone is full or the connection saturated, which is the
strategic waiting the subject asks for. On a plan built from the flow
that never happens, but the engine degrades instead of failing if it
ever did. At the end of each turn every zone and every connection is
checked against its capacity, so an infeasible plan would be rejected
rather than printed.

## Visual representation

The program offers **both** forms the subject mentions: a colored
terminal output, and a graphical interface.

### Terminal

Five parts.

* **A map view.** The zones are drawn on a character grid at their real
  coordinates, rescaled to the terminal, each with a marker for its role
  (`A` start, `Z` end, `*` priority, `~` restricted, `x` blocked), its
  capacity when it holds more than one drone (`(x3)`), and its colour.
  Labels that would collide are pushed to a nearby free line so none is
  ever overwritten. Seeing the topology before the log is what makes the
  flight plan readable at a glance.
* **A flight plan**, listing each route with its length, its duration
  and the number of drones it carries, so a reader can predict the log
  before reading it.
* **A colored flight log.** Each line holds the moves of one turn and
  nothing else, in the exact format required by the subject; the only
  addition is colour, which the subject explicitly allows. Every zone
  name is printed in the colour given in the map, or in the colour of
  its type when the map gives none, so a `restricted` detour or a
  `priority` lane stands out immediately. Drones in transit are dimmed
  and show a connection name instead of a zone name, which makes two
  turn movements obvious. `--delay` replays the log one turn at a time,
  turning the trace into an animation.
* **Zone states**, with `--zones` or `make states`: after each turn, the
  occupancy of every busy zone against its capacity, a full zone being
  shown in red.

  ```
  D1-merge_point D2-slow_path2 D3-fast_path D4-slow_path1 D5-fast_junction
          fast_junction 1/2  fast_path 1/1  merge_point 1/3  slow_path1 1/1
  ```

  It is opt-in so that the default log keeps the exact shape the subject
  defines, and it answers the "why is this drone waiting" question
  immediately.
* **A report** with the three secondary metrics the subject suggests —
  drones moved per turn, average turns per drone, total path cost — plus
  the routes used, the busiest zones, the peak occupancy of each against
  its capacity, and the speedup against the naive single-route solution.

Colours are disabled automatically when the output is redirected, and by
`--no-color` or the `NO_COLOR` environment variable, so a piped log
stays readable. `--quiet` prints the bare format required by the subject
and nothing else.

### Graphical viewer

`--gui` opens a window built like an arcade cabinet, with three
screens.

**Title.** The name in neon, a one-line rule of the game, and a
blinking `PRESS START`. Enter, space or the button move on; Escape
quits.

**Level select.** Every map of `maps/` laid out as a numbered tile, one
row per directory holding them — easy, medium, hard, challenger, custom
first, then any other folder in alphabetical order, each row in its own
colour. Dropping a folder of evaluation maps into `maps/` is therefore
enough for it to appear as its own row, named after the folder;
sub-directories are scanned too, and only `maps/invalid/` is skipped.
Each tile gives the size of the fleet and of the network, read from the
file without solving it so the screen opens instantly. The arrow keys
walk the tiles, left and right within a row and up and down between
families, Enter launches, and the board scrolls to keep the selection
in view, so no level is ever out of reach however many are added. A map
that cannot be solved is reported under the board and the screen stays
open, so a misclick never loses anything.

**Mission.** The network drawn at the real coordinates of its zones,
with the fleet flying over it.

The transport bar holds Reset, a step-backwards button, Play/Pause and
a step-forwards button, plus a speed slider. **The left and right arrow
keys move one turn backwards and forwards**, and a rewound turn is
animated like any other, so the drones glide back to where they came
from instead of jumping: watching a bottleneck build up and then undoing
it, one turn at a time, is the fastest way to understand why a map costs
what it costs. Space plays and pauses, Escape steps back one screen — mission to level
select, level select to title, title to quit. The header gives the map name, the fleet size,
the number of lanes and the total number of turns; the status line gives
the current turn and how many drones are already delivered. Stepping through a bottleneck
one turn at a time is the fastest way to see *why* a map costs what it
costs, which is exactly what the terminal log cannot show.

Only the drones are redrawn on each refresh; the network is rebuilt
once per turn. On the heaviest map, 54 zones and 25 drones, a refresh
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

The lower bound in the table is `d_min + ceil(n / k) - 1`, where
`d_min` is the duration of the fastest route and `k` is the maximum
number of lanes the network can host at once, that is the value of the
maximum flow. No schedule can beat it, and the program reaches it on
every provided map, so these results are not merely good, they are
optimal there.

That bound is only *tight* when every lane has the same length. On a map
whose lanes differ — say three lanes of 2, 3 and 4 turns for 12 drones —
the formula gives 5 while the real optimum is 6, because the two slow
lanes cannot deliver as much as the fast one. The true optimum is what
the binary search of `router.py` computes; the formula above is a quick
sanity check, not the objective.

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

It checks that every map of `maps/invalid/` **is** rejected. There is one
file per rule of the parser constraints, named after it — a missing
`nb_drones`, a second `start_hub`, a dash inside a zone name, a
connection to a zone defined later, `a-b` declared twice as `b-a`, an
unterminated metadata block, an unknown zone type, a `max_drones` of
zero, and so on. A parser that accepts everything is as wrong as one
that accepts nothing, so each rule has its own test.

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

import sys

def main() ->int:
    if len(sys.argv) < 2:
        print("Usage: python main.py <map_file>", file=sys.stderr)
        return 1
    try:
        filepath = sys.argv[1]
        graph = Parser(filepath).parse()
        paths = Pathfinder(graph).find_paths()
        log = Simulator(graph, paths, nb_drones).run()
        Visualizer(graph, log).display()
        return 0
    except ParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Cannot open file: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    main()